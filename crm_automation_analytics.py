"""On-demand reporting and guarded manual enrollment. No provider sends here."""
from datetime import timedelta
from crm_logic import now, date
from crm_automation_home_data import delivery_summary, reporting_window


def revenue(store, window, identity=None):
    return store.q("""SELECT COALESCE(jsonb_object_agg(currency,amount),'{}') AS revenue FROM
      (SELECT currency,sum(amount) AS amount FROM crm_order_attribution WHERE eligible
      AND evidence->>'automation_id' IS NOT NULL AND order_created_at>=%s AND order_created_at<%s
      AND (%s::text IS NULL OR evidence->>'automation_id'=%s) GROUP BY currency) t""",
      (*window,str(identity) if identity else None,str(identity) if identity else None),True)


def conversions(store, identity, window):
    return store.q("""SELECT count(*) AS conversions FROM crm_order_attribution WHERE eligible
      AND evidence->>'automation_id'=%s AND order_created_at>=%s AND order_created_at<%s""",
      (str(identity),*window),True)['conversions']


def summary(store, window):
    # Both periods use the same rolling UTC boundary; never mix currencies.
    prior=(window[0]-timedelta(days=30),window[0])
    current=delivery_summary(store,window);previous=delivery_summary(store,prior)
    current.update(revenue(store,window));previous.update(revenue(store,prior))
    current['previous']=previous
    return current


def performance(store, identity, window):
    return store.q("""WITH messages AS (
      SELECT s.id,date_trunc('day',s.first_submitted_at AT TIME ZONE 'UTC') AS day,
      bool_or(e.event_type='email.delivered') AS delivered,bool_or(e.event_type='email.opened') AS opened,
      bool_or(e.event_type='email.clicked') AS clicked FROM crm_marketing_sends s
      JOIN crm_automation_enrollments j ON j.id=s.enrollment_id LEFT JOIN crm_delivery_events e ON e.send_id=s.id
      WHERE j.automation_id=%s AND s.status='ACCEPTED' AND NOT s.test_send
      AND s.first_submitted_at>=%s AND s.first_submitted_at<%s GROUP BY s.id)
      SELECT day,count(*) AS sent,count(*) FILTER(WHERE delivered) AS delivered,
      count(*) FILTER(WHERE opened) AS opened,count(*) FILTER(WHERE clicked) AS clicked
      FROM messages GROUP BY day ORDER BY day""",(identity,*window))


def activity(store, identity=None, limit=24, *, bounds=None):
    # Indexed ledgers, independent bounded branches. No bodies/customer scans.
    return store.q("""SELECT * FROM (
      (SELECT j.automation_id,a.name,j.shopify_customer_id AS customer_id,j.trigger_at AS occurred_at,
      'Added to flow' AS event,j.id::text AS reference FROM crm_automation_enrollments j
      JOIN crm_automations a ON a.id=j.automation_id WHERE (%s::uuid IS NULL OR a.id=%s::uuid)
      ORDER BY j.trigger_at DESC LIMIT %s)
      UNION ALL (SELECT j.automation_id,a.name,j.shopify_customer_id,s.first_submitted_at,'Email sent',s.id::text
      FROM crm_marketing_sends s JOIN crm_automation_enrollments j ON j.id=s.enrollment_id
      JOIN crm_automations a ON a.id=j.automation_id WHERE s.status='ACCEPTED' AND NOT s.test_send
      AND (%s::uuid IS NULL OR a.id=%s::uuid) ORDER BY s.first_submitted_at DESC LIMIT %s)
      UNION ALL (SELECT j.automation_id,a.name,j.shopify_customer_id,e.occurred_at,
      CASE e.event_type WHEN 'email.opened' THEN 'Email opened' WHEN 'email.clicked' THEN 'Link clicked' ELSE 'Email delivered' END,e.event_id::text
      FROM crm_delivery_events e JOIN crm_marketing_sends s ON s.id=e.send_id
      JOIN crm_automation_enrollments j ON j.id=s.enrollment_id JOIN crm_automations a ON a.id=j.automation_id
      WHERE NOT s.test_send AND e.event_type IN ('email.opened','email.clicked','email.delivered')
      AND (%s::uuid IS NULL OR a.id=%s::uuid) ORDER BY e.occurred_at DESC LIMIT %s)
      UNION ALL (SELECT j.automation_id,a.name,j.shopify_customer_id,j.updated_at,
      CASE j.status WHEN 'RECOVERED' THEN 'Recovered checkout' ELSE 'Flow completed' END,j.id::text
      FROM crm_automation_enrollments j JOIN crm_automations a ON a.id=j.automation_id
      WHERE j.status IN ('RECOVERED','COMPLETED') AND (%s::uuid IS NULL OR a.id=%s::uuid)
      ORDER BY j.updated_at DESC LIMIT %s)
      UNION ALL (SELECT (o.evidence->>'automation_id')::uuid,a.name,o.customer_id,o.order_created_at,'Order placed',o.shopify_order_id
      FROM crm_order_attribution o JOIN crm_automations a ON a.id::text=o.evidence->>'automation_id'
      WHERE o.eligible AND (%s::uuid IS NULL OR a.id=%s::uuid) ORDER BY o.order_created_at DESC LIMIT %s)
      UNION ALL (SELECT j.automation_id,a.name,j.shopify_customer_id,s.updated_at,
      CASE WHEN s.status IN ('PENDING','CLAIMED','SUBMITTING') THEN 'Email queued'
           WHEN s.status='BLOCKED' THEN 'Email skipped' ELSE 'Email failed' END,s.id::text
      FROM crm_marketing_sends s JOIN crm_automation_enrollments j ON j.id=s.enrollment_id
      JOIN crm_automations a ON a.id=j.automation_id WHERE NOT s.test_send AND s.status IN ('PENDING','CLAIMED','SUBMITTING','BLOCKED','FAILED','UNCERTAIN')
      AND (%s::uuid IS NULL OR a.id=%s::uuid) ORDER BY s.updated_at DESC LIMIT %s)
      ) events WHERE (%s::timestamptz IS NULL OR occurred_at>=%s) AND (%s::timestamptz IS NULL OR occurred_at<%s) ORDER BY occurred_at DESC LIMIT %s""",(*(identity,identity,limit)*6,*(bounds[:1]*2+bounds[1:]*2 if bounds else (None,)*4),limit))


CHECKOUTS='''query AutomationCheckoutAnalytics($after:String) {
 abandonedCheckouts(first:25,after:$after,sortKey:CREATED_AT,reverse:true) { nodes {
 id createdAt updatedAt completedAt abandonedCheckoutUrl customer { id firstName lastName email }
 shippingAddress { countryCodeV2 } billingAddress { countryCodeV2 }
 totalPriceSet { shopMoney { amount currencyCode } }
 } pageInfo { hasNextPage endCursor } } }'''


def checkout_page(shop, store, identity, cursor=None):
    import os
    from crm_shopify_automation_events import key_from_recovery_url
    page=shop.query(CHECKOUTS,{'after':cursor},'automation checkout analytics',60)['abandonedCheckouts']
    keys=[key_from_recovery_url(c.get('abandonedCheckoutUrl'),os.getenv('SHOPIFY_STORE_DOMAIN','')) for c in page['nodes']]
    overlay=store.q("""SELECT c.*,a.status AS automation_status,a.config->>'archived_at' AS archived_at,
      j.id AS enrollment_id,j.status AS flow_status,j.current_step,j.steps,j.next_due_at,
      GREATEST(c.activity_at,j.updated_at,(SELECT max(e.occurred_at) FROM crm_delivery_events e
      JOIN crm_marketing_sends s ON s.id=e.send_id WHERE s.enrollment_id=j.id AND NOT s.test_send)) AS last_activity_at,
      COALESCE((SELECT jsonb_agg(jsonb_build_object('step',s.step_index,'status',s.status,'submitted_at',s.first_submitted_at,'updated_at',s.updated_at))
      FROM crm_marketing_sends s WHERE s.enrollment_id=j.id AND NOT s.test_send),'[]') AS sends,
      (SELECT count(*) FROM crm_delivery_events e JOIN crm_marketing_sends s ON s.id=e.send_id
      WHERE s.enrollment_id=j.id AND NOT s.test_send AND e.event_type='email.opened') AS opened,
      (SELECT count(*) FROM crm_delivery_events e JOIN crm_marketing_sends s ON s.id=e.send_id
      WHERE s.enrollment_id=j.id AND NOT s.test_send AND e.event_type='email.clicked') AS clicked
      FROM crm_shopify_checkouts c JOIN crm_automations a ON a.id=%s LEFT JOIN LATERAL (SELECT * FROM crm_automation_enrollments j
      WHERE j.checkout_key=c.checkout_key AND j.automation_id=%s ORDER BY j.trigger_at DESC LIMIT 1) j ON true
      WHERE c.checkout_key=ANY(%s::text[])""",(identity,identity,[k for k in keys if k]))
    indexed={c['checkout_key']:c for c in overlay}
    return {**page,'nodes':[{**c,'ledger':indexed.get(k,{}),'checkout_key':k} for c,k in zip(page['nodes'],keys)]}


def flow_state(checkout, at=None):
    at=at or now();ledger=checkout.get('ledger') or {}
    if checkout.get('completedAt') or ledger.get('status')=='RECOVERED' or ledger.get('flow_status')=='RECOVERED':return 'Recovered','Future sends suppressed'
    state=ledger.get('flow_status')
    if state=='COMPLETED':return 'Flow complete','—'
    if state=='ACTIVE':
        if ledger.get('automation_status')=='PAUSED':return 'Archived' if ledger.get('archived_at') else 'Paused','Future sends held'
        if ledger.get('steps') and int(ledger.get('current_step') or 0)>=len(ledger['steps']):return 'All live emails sent','Waiting for a new published stage'
        due=date(ledger.get('next_due_at'));index=int(ledger.get('current_step') or 0)+1
        receipt=next((s for s in ledger.get('sends',[]) if s['step']==index-1),None)
        if receipt and receipt['status']=='ACCEPTED':
            steps=ledger.get('steps') or []
            if index>=len(steps):return 'All emails sent','Awaiting flow completion'
            # Same clock as runtime.advance: accepted receipt updated_at + the
            # following frozen step delay, while the worker advances its cursor.
            accepted=date(receipt.get('updated_at'))
            if not accepted:return 'Email '+str(index)+' sent','Next step awaiting worker'
            due=accepted+timedelta(seconds=steps[index]['delay_seconds']);index+=1
        elif receipt and receipt['status'] not in ('PENDING','CLAIMED','SUBMITTING'):
            return 'Email '+str(index)+' '+receipt['status'].lower(),'Future sends held'
        seconds=max(0,int((due-at).total_seconds())) if due else None
        countdown=f'{seconds//3600:02}:{seconds%3600//60:02}:{seconds%60:02}' if seconds is not None else '—'
        return 'In Flow — Email '+str(index)+' pending',('Due · awaiting worker' if seconds==0 else 'Sends in '+countdown)
    if state:return state.title(),'No pending action'
    return 'Not in flow','Add to flow' if ledger else 'Awaiting signed checkout receipt'


def add_to_flow(shop, store, user, identity, checkout_id):
    """Fresh exact Shopify checkout + persistent mirror + published policy; no inline sends."""
    from crm_navigation import require
    require(user,'crm_automations_manage')
    return _authorized_add_to_flow(shop,store,identity,checkout_id)


def _authorized_add_to_flow(shop,store,identity,checkout_id,expected_key=None):
    """Server-only continuation of an explicitly authorized durable request."""
    from crm_automation_definition import native
    from crm_automation_capabilities import require as ready
    from crm_shopify_automation_events import key_from_recovery_url
    from crm_automation_rule_facts import checkout_facts
    from crm_automation_runtime import enter
    from crm_engine import Engine
    import os
    row=store.get('automations',identity)
    if not row or not native(row) or row['status']!='ACTIVE' or row['config'].get('archived_at') or row['config'].get('deleted_at') or row['trigger_type']!='abandoned':
        raise ValueError('Use an active, published abandoned-checkout flow. Drafts cannot send.')
    ready(store,'abandoned')
    checkout=shop.checkout(checkout_id,fresh=True)
    if not checkout:raise ValueError('Error: Shopify checkout verification unavailable')
    if checkout.get('id')!=checkout_id:raise ValueError('Not eligible: checkout identity changed')
    if date(checkout.get('completedAt')):raise ValueError('Recovered')
    customer=(checkout.get('customer') or {}).get('id')
    key=key_from_recovery_url(checkout.get('abandonedCheckoutUrl'),os.getenv('SHOPIFY_STORE_DOMAIN',''))
    if not key:raise ValueError('Verified checkout identity required.')
    if expected_key is not None and key!=expected_key:raise ValueError('Not eligible: checkout identity changed')
    from crm_checkout_analytics import details
    details(store,checkout)
    ledger=store.q('SELECT * FROM crm_shopify_checkouts WHERE checkout_key=%s',(key,),True)
    if not ledger:raise ValueError('Error: checkout persistence unavailable')
    if ledger['status']=='RECOVERED':raise ValueError('Recovered')
    if store.q('SELECT id FROM crm_automation_enrollments WHERE automation_id=%s AND checkout_key=%s',(identity,key),True):raise ValueError('Already in flow')
    from crm_checkout_identity import recipient,block_label
    from crm_logic import eligibility,recipient_hash
    c=recipient(shop,store,checkout,ledger)
    if not (c or {}).get('email'):raise ValueError('Missing email')
    purchased=date((c.get('lastOrder') or {}).get('createdAt'))
    if purchased and date(checkout.get('createdAt')) and purchased>=date(checkout['createdAt']):raise ValueError('Recovered')
    from crm_checkout_eligibility import recovery_eligibility,policy
    eligible,reason=recovery_eligibility(checkout,c,policy(store),suppressed=store.suppressed(c['id'],recipient_hash(c.get('email'))),manual=True)
    if not eligible:raise ValueError(block_label(reason))
    from crm_native_unsubscribe import native_unsubscribe_url
    if not native_unsubscribe_url(c,recovery=True):raise ValueError('Not eligible: unsubscribe link unavailable')
    customer=c['id']
    at=now();threshold=0  # Explicit manual action bypasses the initial automation wait.
    created=date(checkout.get('createdAt'));activated=date(row.get('activated_at'))
    if not created or not activated:raise ValueError('Verified checkout and activation dates are required.')
    # Manual selection is intentional historical enrollment, not automatic backfill.
    # Shopify Admin identity is matched using its exact recovery key.
    # Admin abandonment creation can differ from the original checkout webhook time.
    # Match the exact recovery token and customer, never timestamp equality.
    updated=date(checkout.get('updatedAt'))
    if not updated:raise ValueError('Verified checkout activity date is required.')
    if max(date(ledger['activity_at']),updated)+timedelta(seconds=threshold)>at:raise ValueError('Checkout is not yet abandoned. Wait for the configured inactivity period.')
    result=enter(Engine(store,shop),row,customer,checkout_id,'checkout:'+key,at,checkout_key=key,
                 source_event_id=ledger['source_event_id'],event_facts=checkout_facts(checkout),manual_checkout=True,recipient=c,checkout_source=checkout)
    if not result:
        if store.q('SELECT id FROM crm_automation_enrollments WHERE automation_id=%s AND checkout_key=%s',(identity,key),True):raise ValueError('Already in flow')
        raise ValueError('Not eligible: flow rules, re-entry policy or checkout state changed')
    return result
