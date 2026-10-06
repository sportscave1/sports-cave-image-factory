"""Private checkout-ledger projections. No Shopify calls in list/report reads."""
from datetime import timedelta
import json
from crm_logic import now, date

RECONCILE_QUERY='''query AutomationCheckoutReconciliation($after:String,$query:String) {
 abandonedCheckouts(first:100,after:$after,query:$query,sortKey:CREATED_AT,reverse:true) { nodes {
 id name createdAt updatedAt completedAt abandonedCheckoutUrl customer { id firstName lastName email }
 shippingAddress { name firstName lastName country countryCodeV2 } billingAddress { name firstName lastName country countryCodeV2 }
 totalPriceSet { shopMoney { amount currencyCode } }
 } pageInfo { hasNextPage endCursor } } }'''

PERIODS={'Last 7 days':7,'Last 30 days':30,'Last 90 days':90,'Last year':365,'All time':None}

def window(period,at=None):
    """Rolling UTC, inclusive start/exclusive end; checkout cohort uses created_at."""
    at=at or now();days=PERIODS[period]
    return (at-timedelta(days=days) if days else None,at)

def details(store,checkout):
    """Idempotent Admin-source mirror/repair. Never enroll or submit mail."""
    import os
    from crm_checkout_identity import identity
    from crm_shopify_automation_events import key_from_recovery_url
    key=key_from_recovery_url(checkout.get('abandonedCheckoutUrl'),os.getenv('SHOPIFY_STORE_DOMAIN',''))
    created=date(checkout.get('createdAt'));activity=date(checkout.get('updatedAt')) or created
    if not key or not checkout.get('id') or not created:raise ValueError('Checkout identity unavailable')
    customer=(checkout.get('customer') or {}).get('id') or ''
    data={k:v for k,v in identity(checkout).items() if v}
    if any(k in (checkout.get('customer') or {}) for k in ('firstName','lastName','email')) or (checkout.get('shippingAddress') or {}).get('name'):
        data['name']=identity(checkout)['name']
    price=(checkout.get('totalPriceSet') or {}).get('shopMoney') or {}
    data.update({k:str(v) for k,v in {'amount':price.get('amount'),'currency':price.get('currencyCode')}.items() if v})
    data.update(shopify_abandoned=True,completed_at=checkout.get('completedAt'))
    with store.db() as conn:
        prior=conn.execute('SELECT * FROM crm_shopify_checkouts WHERE checkout_key=%s FOR UPDATE',(key,)).fetchone()
        if prior and prior['customer_id'] and customer and prior['customer_id']!=customer:raise ValueError('Checkout customer identity changed')
        if prior and date((prior.get('analytics') or {}).get('completed_at')):data['completed_at']=prior['analytics']['completed_at']
        if conn.execute("SELECT 1 FROM crm_suppressions WHERE shopify_customer_id=%s AND reason='redacted'",(customer or (prior or {}).get('customer_id',''),)).fetchone():return 'Unchanged'
        conn.execute("""INSERT INTO crm_shopify_checkouts(checkout_key,shop,customer_id,source_event_id,created_at,activity_at,status,admin_checkout_id,analytics)
          VALUES(%s,%s,%s,%s,%s,%s,'ABANDONED',%s,'{}') ON CONFLICT DO NOTHING""",
          (key,os.getenv('SHOPIFY_STORE_DOMAIN',''),customer,'admin:'+checkout['id'],created,activity,checkout['id']))
        # Preserve signed completion/order evidence. Cached status alone is not evidence.
        changed=conn.execute("""UPDATE crm_shopify_checkouts c SET admin_checkout_id=%s,
          customer_id=COALESCE(NULLIF(%s,''),customer_id),analytics=analytics||%s::jsonb,
          activity_at=GREATEST(activity_at,%s),status=CASE WHEN order_id IS NOT NULL OR %s OR
          EXISTS(SELECT 1 FROM crm_webhook_events e WHERE e.normalized->>'checkout_key'=c.checkout_key AND e.normalized->>'completed'='true')
          THEN 'RECOVERED' WHEN EXISTS(SELECT 1 FROM crm_marketing_sends s JOIN crm_automation_enrollments j ON j.id=s.enrollment_id
          WHERE j.checkout_key=c.checkout_key AND s.status='ACCEPTED' AND s.provider_email_id IS NOT NULL AND NOT s.test_send)
          THEN 'RECOVERY_EMAIL_SENT' ELSE 'ABANDONED' END
          WHERE checkout_key=%s RETURNING *""",(checkout['id'],customer,json.dumps(data),activity,bool(date(data.get('completed_at'))),key)).fetchone()
        comparable=('admin_checkout_id','customer_id','analytics','activity_at','status')
        return 'Unchanged' if prior and all(prior[k]==changed[k] for k in comparable) else 'Updated'


def reconcile(shop,store,period):
    """Resumable bounded repair; historical rows are cache-only, never enrolled."""
    slot='checkout-repair:'+period;state=store.state(slot);cursor=state.get('cursor')
    start,_=window(period);counts={'Updated':0,'Unchanged':0,'Failed':0};seen=set()
    for _ in range(4):
        page=shop.query(RECONCILE_QUERY,{'after':cursor,'query':'created_at:>='+start.isoformat() if start else None},'automation checkout reconciliation',20,True)['abandonedCheckouts']
        for checkout in page['nodes']:
            try:counts[details(store,checkout)]+=1
            except Exception:counts['Failed']+=1
        info=page['pageInfo'];end=info.get('endCursor')
        if not info.get('hasNextPage'):
            store.set_state(slot,{'cursor':None});return counts,False
        if not end or end==cursor or end in seen:raise ValueError('Checkout refresh did not advance.')
        seen.add(end);cursor=end
        store.set_state(slot,{'cursor':cursor})
    return counts,True


def sync_cache(shop,store,at=None):
    """One persistent page per worker cycle, even with sending disabled."""
    at=at or now();slot='checkout-cache-v2';state=store.state(slot)
    if date(state.get('next_at')) and date(state['next_at'])>at:return
    page=shop.query(RECONCILE_QUERY,{'after':state.get('cursor'),'query':None},'checkout identity sync',0,True)['abandonedCheckouts']
    for checkout in page['nodes']:details(store,checkout)
    info=page['pageInfo'];cursor=info.get('endCursor') if info.get('hasNextPage') else None
    if info.get('hasNextPage') and (not cursor or cursor==state.get('cursor')):raise ValueError('Checkout sync pagination did not advance')
    store.set_state(slot,{'cursor':cursor,'next_at':(at+timedelta(seconds=2 if cursor else 300)).isoformat()})


LIST_SQL="""WITH selected AS MATERIALIZED (
 SELECT checkout_key,customer_id,created_at,activity_at,status,admin_checkout_id,analytics,order_id,
 EXISTS(SELECT 1 FROM crm_webhook_events e WHERE e.normalized->>'checkout_key'=crm_shopify_checkouts.checkout_key AND e.normalized->>'completed'='true') AS completion_verified
 FROM crm_shopify_checkouts WHERE analytics->>'shopify_abandoned'='true' AND (%s::timestamptz IS NULL OR created_at>=%s) AND created_at<%s
 AND (%s::text IS NULL OR checkout_key=%s)
), journeys AS MATERIALIZED (
 SELECT DISTINCT ON(j.checkout_key) j.* FROM crm_automation_enrollments j JOIN selected c USING(checkout_key)
 WHERE j.automation_id=%s ORDER BY j.checkout_key,j.trigger_at DESC
), messages AS MATERIALIZED (
 SELECT s.id,s.enrollment_id,j.checkout_key,s.step_index,s.status,s.first_submitted_at,s.updated_at,s.provider_email_id,s.error_code
 FROM crm_marketing_sends s JOIN crm_automation_enrollments j ON j.id=s.enrollment_id
 JOIN selected c ON c.checkout_key=j.checkout_key JOIN crm_automations a ON a.id=j.automation_id
 WHERE NOT s.test_send AND a.trigger_type='abandoned'
), events AS (
 SELECT e.send_id,count(*) FILTER(WHERE event_type='email.opened') AS opened,
 count(*) FILTER(WHERE event_type='email.clicked') AS clicked,max(occurred_at) AS last_event
 FROM crm_delivery_events e JOIN messages s ON s.id=e.send_id GROUP BY e.send_id
), receipts AS (
 SELECT s.checkout_key,jsonb_agg(jsonb_build_object('id',s.id,'enrollment_id',s.enrollment_id,'step',step_index,'status',status,'submitted_at',first_submitted_at,'updated_at',updated_at,'provider_id',provider_email_id,'error',error_code) ORDER BY step_index) AS sends,
 sum(COALESCE(e.opened,0)) AS opened,sum(COALESCE(e.clicked,0)) AS clicked,max(e.last_event) AS last_event
 FROM messages s LEFT JOIN events e ON e.send_id=s.id GROUP BY s.checkout_key
)
SELECT c.*,v.value AS evaluation,request.value-'history' AS enrollment_request,a.status AS automation_status,a.config->>'archived_at' AS archived_at,
 a.config->'published'->>'abandonment_seconds' AS abandonment_seconds,
 j.id AS enrollment_id,j.status AS flow_status,j.stop_reason,j.current_step,j.steps,j.next_due_at,
 GREATEST(c.activity_at,j.updated_at,r.last_event) AS last_activity_at,
 COALESCE(r.sends,'[]') AS sends,COALESCE(r.opened,0) AS opened,COALESCE(r.clicked,0) AS clicked
FROM selected c JOIN crm_automations a ON a.id=%s LEFT JOIN journeys j USING(checkout_key)
LEFT JOIN receipts r ON r.checkout_key=c.checkout_key
LEFT JOIN crm_runtime_state v ON v.key='checkout-evaluation:'||c.checkout_key||':'||a.id::text
LEFT JOIN crm_runtime_state request ON request.key='checkout-enroll:'||a.id::text||':'||c.checkout_key
ORDER BY c.created_at DESC,c.checkout_key"""

def checkouts(store,identity,bounds,key=None):
    start,end=bounds
    return store.q(LIST_SQL,(start,start,end,key,key,identity,identity))

def report(store,identity,bounds):
    """One message/event aggregate shared by KPI and chart; no event fanout totals.

    Sends/orders use their occurrence time. Checkout list/recovered count use
    checkout creation time, clearly labelled as a separate cohort in the UI.
    """
    start,end=bounds
    return store.q("""WITH messages AS (
      SELECT s.id,date_trunc('day',s.first_submitted_at AT TIME ZONE 'UTC') AS day,
      bool_or(e.event_type='email.delivered') AS delivered,bool_or(e.event_type='email.opened') AS opened,
      bool_or(e.event_type='email.clicked') AS clicked FROM crm_marketing_sends s
      JOIN crm_automation_enrollments j ON j.id=s.enrollment_id LEFT JOIN crm_delivery_events e ON e.send_id=s.id
      WHERE j.automation_id=%s AND s.status='ACCEPTED' AND NOT s.test_send
      AND (%s::timestamptz IS NULL OR s.first_submitted_at>=%s) AND s.first_submitted_at<%s GROUP BY s.id
    ), daily AS (SELECT day,count(*) AS sent,count(*) FILTER(WHERE delivered) AS delivered,
      count(*) FILTER(WHERE opened) AS opened,count(*) FILTER(WHERE clicked) AS clicked FROM messages GROUP BY day),
    orders AS (SELECT currency,sum(amount) AS amount,count(*) AS n FROM crm_order_attribution
      WHERE eligible AND evidence->>'automation_id'=%s AND (%s::timestamptz IS NULL OR order_created_at>=%s)
      AND order_created_at<%s GROUP BY currency)
    SELECT COALESCE((SELECT jsonb_agg(d ORDER BY day) FROM daily d),'[]') AS history,
      (SELECT count(*) FROM messages) AS sent,(SELECT count(*) FROM messages WHERE delivered) AS delivered,
      (SELECT count(*) FROM messages WHERE opened) AS opened,(SELECT count(*) FROM messages WHERE clicked) AS clicked,
      COALESCE((SELECT sum(n) FROM orders),0)::bigint AS conversions,
      COALESCE((SELECT jsonb_object_agg(currency,amount) FROM orders),'{}') AS revenue""",
      (identity,start,start,end,str(identity),start,start,end),True)

def disabled_reason(checkout,row,at=None):
    at=at or now()
    from crm_checkout_identity import recovered
    if recovered(checkout):return 'Recovered'
    if checkout.get('enrollment_id'):return 'Already in flow'
    if row['status']!='ACTIVE' or not row.get('steps') or row['config'].get('archived_at') or row['config'].get('deleted_at'):return 'Flow is not live'
    if not checkout.get('admin_checkout_id'):return 'Not eligible: Shopify identity unavailable'
    if (checkout.get('analytics') or {}).get('email_state')=='invalid':return 'Invalid email'
    if not (checkout.get('analytics') or {}).get('email'):return 'Missing email'
    activity=date(checkout.get('activity_at'))
    threshold=int(row['config'].get('published',{}).get('abandonment_seconds',3600))
    if not activity or activity+timedelta(seconds=threshold)>at:return 'Checkout still inside abandonment wait period'
    return None
