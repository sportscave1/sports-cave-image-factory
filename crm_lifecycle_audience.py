"""Local paginated reads and preview staging; never enroll or send."""
import json
from datetime import timedelta
from crm_logic import date, now, consent, recipient_hash
from crm_navigation import require
from crm_lifecycle_policy import order_from_ledger, preview

SORTS={'Newest':'audience_at DESC NULLS LAST','Oldest':'audience_at ASC NULLS LAST',
       'Longest inactivity':'last_paid_at ASC NULLS LAST','Last purchase':'last_paid_at DESC NULLS LAST',
       'Customer value':'lifetime_value DESC NULLS LAST','Sequence stage':'stage DESC NULLS LAST'}
FILTERS=('All','New','Queued','Completed','Unsubscribed','Purchased','Suppressed')

def cache_customer(store, customer, at):
    """Only verified Shopify customer responses; checkout identity is never consent."""
    changed=date(customer.get('updatedAt'))
    if not customer.get('id') or not changed:return
    # Signed privacy events remain authoritative across reconciliation retries.
    if store.q("SELECT 1 FROM crm_suppressions WHERE (shopify_customer_id=%s OR recipient_hash=%s) AND reason='redacted' LIMIT 1",(customer['id'],recipient_hash(customer.get('email'))),True):return
    state=consent(customer)
    subscription=date((customer.get('emailMarketingConsent') or {}).get('consentUpdatedAt'))
    saved=store.q('''INSERT INTO crm_lifecycle_customers(customer_id,email,recipient_hash,name,subscribed_at,
      created_at,source_updated_at,verified_at,consent,profile)
      VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
      ON CONFLICT(customer_id) DO UPDATE SET email=excluded.email,recipient_hash=excluded.recipient_hash,
      name=excluded.name,subscribed_at=CASE WHEN crm_lifecycle_customers.consent='SUBSCRIBED' AND excluded.consent='SUBSCRIBED'
      THEN COALESCE(crm_lifecycle_customers.subscribed_at,excluded.subscribed_at) ELSE excluded.subscribed_at END,
      source_updated_at=excluded.source_updated_at,verified_at=excluded.verified_at,consent=excluded.consent,profile=excluded.profile
      WHERE crm_lifecycle_customers.source_updated_at<=excluded.source_updated_at RETURNING customer_id''',
      (customer['id'],str(customer.get('email') or '').lower(),recipient_hash(customer.get('email')),
       ' '.join(filter(None,[customer.get('firstName'),customer.get('lastName')])),subscription,
       date(customer.get('createdAt')),changed,at,state,json.dumps(customer)))
    return bool(saved)

def sync_page(store, shop, at=None):
    """One 50-customer page through the existing adapter, with incremental watermark.

    This is a display cache only. Historical reconciliation cannot enroll anyone.
    The caller is the existing worker, never a page render.
    """
    at=at or now();state=store.state('lifecycle-audience-sync')
    if date(state.get('next_at')) and date(state['next_at'])>at:return False
    start=state.get('started_at') or at.isoformat()
    query='updated_at:>='+state['since'] if state.get('since') else None
    page=shop.customers(after=state.get('cursor'),query=query,fresh=True)
    for customer in page['nodes']:cache_customer(store,customer,at)
    more=page['pageInfo'].get('hasNextPage')
    store.set_state('lifecycle-audience-sync',dict(cursor=page['pageInfo'].get('endCursor') if more else None,
        since=state.get('since') if more else (date(start)-timedelta(minutes=5)).isoformat(),
        started_at=start if more else None,next_at=(at+timedelta(seconds=2 if more else 300)).isoformat(),
        verified_at=at.isoformat(),historical_complete=bool(not more or state.get('historical_complete'))))
    return True


def enrich_orders(store,shop,at=None):
    """Bounded priority customer reads, independent of the directory cursor."""
    at=at or now()
    rows=store.q('''SELECT COALESCE(NULLIF(o.shopify_customer_id,''),o.customer_id) AS customer_id,max(o.created_at) AS newest
      FROM shopify_orders o LEFT JOIN crm_lifecycle_customers c
      ON c.customer_id=COALESCE(NULLIF(o.shopify_customer_id,''),o.customer_id)
      LEFT JOIN crm_runtime_state r ON r.key='lifecycle-enrich:'||COALESCE(NULLIF(o.shopify_customer_id,''),o.customer_id)
      WHERE COALESCE(NULLIF(o.shopify_customer_id,''),o.customer_id) IS NOT NULL
      AND (c.customer_id IS NULL OR c.verified_at<GREATEST(o.created_at,o.remote_updated_at) OR c.verified_at<%s OR r.value->>'state'='QUEUED')
      AND COALESCE((r.value->>'retry_at')::timestamptz,'-infinity')<=%s
      AND NOT EXISTS(SELECT 1 FROM crm_suppressions s WHERE s.shopify_customer_id=COALESCE(NULLIF(o.shopify_customer_id,''),o.customer_id) AND s.reason='redacted')
      GROUP BY COALESCE(NULLIF(o.shopify_customer_id,''),o.customer_id)
      ORDER BY max(CASE WHEN r.value->>'state'='QUEUED' THEN 1 ELSE 0 END) DESC,newest DESC LIMIT 5''',(at-timedelta(hours=6),at))
    for row in rows:
        key='lifecycle-enrich:'+row['customer_id']
        with store.db() as conn:
            claim=conn.execute('''INSERT INTO crm_runtime_state AS prior(key,value) VALUES(%s,%s::jsonb)
              ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=now()
              WHERE COALESCE((prior.value->>'retry_at')::timestamptz,'-infinity')<=%s RETURNING key''',
              (key,json.dumps({'retry_at':(at+timedelta(minutes=5)).isoformat(),'state':'CHECKING'}),at)).fetchone()
        if not claim:continue
        try:
            customer=shop.customer(row['customer_id'],fresh=True)
            if not customer or customer.get('id')!=row['customer_id']:raise ValueError('Customer verification unavailable')
            if not cache_customer(store,customer,at):raise ValueError('Verified profile could not be cached')
            store.set_state(key,{'state':'VERIFIED','retry_at':(at+timedelta(minutes=5)).isoformat()})
        except Exception:
            store.set_state(key,{'state':'RETRY','retry_at':(at+timedelta(minutes=5)).isoformat()})
    return bool(rows)


def refresh_customers(store,user,customers):
    require(user,'crm_automations_manage')
    for customer in set(customers):
        if not customer or not customer.startswith('gid://shopify/Customer/'):continue
        store.q('''INSERT INTO crm_runtime_state AS prior(key,value) VALUES(%s,'{"state":"QUEUED"}'::jsonb)
          ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=now()
          WHERE prior.value->>'state'<>'CHECKING' ''',('lifecycle-enrich:'+customer,))

def listing(store, row, *, search='', filter_by='All', sort=None, start=None, end=None, page=0, at=None):
    kind=row['trigger_type'];at=at or now()
    sort=sort or ('Longest inactivity' if kind=='win_back' else 'Newest')
    if kind=='post_purchase':
        from crm_post_purchase_audience import listing as orders
        return orders(store,row,search=search,filter_by=filter_by,sort=sort,start=start,end=end,page=page,at=at)
    if sort not in SORTS or filter_by not in FILTERS:raise ValueError('Invalid audience filter')
    if type(page) is not int or not 0<=page<=20000:raise ValueError('Invalid page')
    order_kind=kind=='post_purchase'
    extra="JOIN shopify_orders o ON COALESCE(NULLIF(o.shopify_customer_id,''),o.customer_id)=c.customer_id" if order_kind else ''
    audience_at='o.created_at' if order_kind else 'p.last_paid_at' if kind=='win_back' else 'c.subscribed_at'
    identity='o.shopify_order_id' if order_kind else 'c.customer_id'
    order_fields=",o.order_name,o.financial_status,o.fulfillment_status,o.cancelled_at" if order_kind else ",NULL::text AS order_name,NULL::text AS financial_status,NULL::text AS fulfillment_status,NULL::timestamptz AS cancelled_at"
    guards=["upper(o.financial_status) IN ('PAID','PARTIALLY_REFUNDED','REFUNDED')"] if order_kind else ["c.subscribed_at IS NOT NULL"] if kind=='welcome' else ["p.last_paid_at<=%s"]
    args=[row['id']]
    if kind=='win_back':args.append(at-timedelta(days=row['config']['draft'].get('inactive_days',90)))
    if search.strip():
        guards.append("(c.name ILIKE %s OR c.email ILIKE %s OR c.customer_id ILIKE %s"+(" OR o.order_name ILIKE %s OR o.shopify_order_id ILIKE %s)" if order_kind else ')'))
        needle='%'+search.strip().replace('\\','\\\\').replace('%','\\%').replace('_','\\_')[:200]+'%'
        args.extend([needle]*(5 if order_kind else 3))
    if start:guards.append(audience_at+'>=%s');args.append(start)
    if end:guards.append(audience_at+'<%s');args.append(end)
    filters={'New':'j.id IS NULL','Queued':"j.status='ACTIVE'",'Completed':"j.status='COMPLETED'",'Unsubscribed':"c.consent<>'SUBSCRIBED'",'Purchased':'p.order_count>0',
             'Suppressed':"EXISTS(SELECT 1 FROM crm_suppressions x WHERE x.shopify_customer_id=c.customer_id OR x.recipient_hash=c.recipient_hash)"}
    if filter_by in filters:guards.append(filters[filter_by])
    sql='''WITH paid_events AS (
      SELECT object_id,min(occurred_at) AS paid_at FROM crm_webhook_events
      WHERE provider='shopify' AND topic='orders/paid' GROUP BY object_id), purchases AS (
      SELECT COALESCE(NULLIF(shopify_customer_id,''),customer_id) AS customer_id,
      max(COALESCE(e.paid_at,o.created_at)) AS last_paid_at,count(*) AS order_count,
      sum(CASE WHEN total_price ~ '^[0-9]+([.][0-9]+)?$' THEN total_price::numeric ELSE 0 END) AS lifetime_value,
      CASE WHEN count(DISTINCT currency)=1 THEN min(currency) ELSE 'Mixed currencies' END AS currency
      FROM shopify_orders o LEFT JOIN paid_events e ON e.object_id=o.shopify_order_id
      WHERE upper(financial_status) IN ('PAID','PARTIALLY_REFUNDED') AND cancelled_at IS NULL
      GROUP BY COALESCE(NULLIF(shopify_customer_id,''),customer_id))
      ,picked AS MATERIALIZED (SELECT '''+identity+''' AS key,c.customer_id,c.name,c.email,c.consent,c.verified_at,c.source,
      '''+audience_at+''' AS audience_at,p.last_paid_at,COALESCE(p.order_count,0) AS order_count,
      CASE WHEN c.profile->'amountSpent'->>'amount' ~ '^[0-9]+([.][0-9]+)?$'
           THEN (c.profile->'amountSpent'->>'amount')::numeric ELSE NULL END AS lifetime_value,
      c.profile->'amountSpent'->>'currencyCode' AS currency,
      j.id AS enrollment_id,j.status AS flow_state,j.current_step+1 AS stage,j.next_due_at,j.current_step,j.steps,j.stop_reason,
      s.status AS last_email,s.first_submitted_at,
      EXISTS(SELECT 1 FROM crm_suppressions x WHERE x.shopify_customer_id=c.customer_id OR x.recipient_hash=c.recipient_hash) AS suppressed
      '''+order_fields+''' FROM crm_lifecycle_customers c LEFT JOIN purchases p ON p.customer_id=c.customer_id
      '''+extra+''' LEFT JOIN LATERAL(SELECT id,status,current_step,next_due_at,steps,stop_reason FROM crm_automation_enrollments
      WHERE automation_id=%s AND (shopify_customer_id=c.customer_id OR steps->0->>'recipient_hash'=c.recipient_hash) '''+("AND trigger_shopify_id=o.shopify_order_id " if order_kind else '')+'''ORDER BY created_at DESC,id DESC LIMIT 1) j ON true
      LEFT JOIN LATERAL(SELECT status,first_submitted_at FROM crm_marketing_sends WHERE enrollment_id=j.id
      AND NOT test_send ORDER BY created_at DESC LIMIT 1) s ON true
      WHERE '''+' AND '.join(guards)+' ORDER BY '+SORTS[sort]+''',key LIMIT 51 OFFSET %s)
      SELECT picked.*,COALESCE(receipts.sends,'[]'::jsonb) AS sends FROM picked
      LEFT JOIN LATERAL(SELECT jsonb_agg(jsonb_build_object(
        'enrollment_id',s.enrollment_id,'step',s.step_index,'status',s.status,
        'provider_id',s.provider_email_id,'submitted_at',s.first_submitted_at,'due_at',s.due_at,'error',s.error_code,
        'opened',EXISTS(SELECT 1 FROM crm_delivery_events e WHERE e.send_id=s.id AND e.event_type='email.opened'),
        'clicked',EXISTS(SELECT 1 FROM crm_delivery_events e WHERE e.send_id=s.id AND e.event_type='email.clicked'))
        ORDER BY s.step_index) AS sends FROM crm_marketing_sends s
        WHERE s.enrollment_id=picked.enrollment_id AND NOT s.test_send) receipts ON true
      ORDER BY '''+SORTS[sort]+',key'
    args.append(page*50)
    return store.q(sql,tuple(args))

def customer_preview(store,row,customer_id,order_id=None,at=None):
    customer=store.q('SELECT * FROM crm_lifecycle_customers WHERE customer_id=%s',(customer_id,),True)
    if not customer:raise ValueError('Customer data unavailable; refresh the audience cache.')
    records=store.q('''SELECT * FROM shopify_orders WHERE COALESCE(NULLIF(shopify_customer_id,''),customer_id)=%s
      ORDER BY created_at DESC,shopify_order_id DESC LIMIT 1001''',(customer_id,))
    if len(records)>1000:raise ValueError('Order history exceeds preview bound; review manually before staging.')
    events=store.q("SELECT object_id,topic,occurred_at FROM crm_webhook_events WHERE provider='shopify' AND object_id=ANY(%s) AND topic IN ('orders/paid','orders/fulfilled')",([o['shopify_order_id'] for o in records],)) if records else []
    by_id={}
    for event in events:by_id.setdefault(event['object_id'],[]).append(event)
    orders=[order_from_ledger(o,by_id.get(o['shopify_order_id'],[])) for o in records]
    result=preview(row['config']['draft'],customer['profile'],orders,at or now(),
        suppressed=store.suppressed(customer_id,customer['recipient_hash']),subscribed_at=customer['subscribed_at'],order_id=order_id)
    result['orders']=orders
    result['verified_at']=customer['verified_at']
    return result

def stage(store,user,row,customer_id,order_id=None):
    require(user,'crm_automations_manage')
    result=customer_preview(store,row,customer_id,order_id)
    if not result['eligible']:raise ValueError('Not eligible: '+result['reason'])
    # The same transaction locks definition/revision; this creates an audit preview only.
    with store.db() as conn:
        current=conn.execute('SELECT * FROM crm_automations WHERE id=%s FOR UPDATE',(row['id'],)).fetchone()
        if not current or current['status']!='DRAFT' or current['config']['revision']!=row['config']['revision']:
            raise ValueError('Draft changed; reload before staging.')
        conn.execute('''INSERT INTO crm_lifecycle_staged(automation_id,customer_id,cycle,revision,actor,preview)
          VALUES(%s,%s,%s,%s,%s,%s::jsonb) ON CONFLICT DO NOTHING''',
          (row['id'],customer_id,result['cycle'],row['config']['revision'],str(user.get('id','')),json.dumps(result,default=str)))
    return result
