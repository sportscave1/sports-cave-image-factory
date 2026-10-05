"""Private checkout-ledger projections. No Shopify calls in list/report reads."""
from datetime import timedelta
import json
from crm_logic import now, date

RECONCILE_QUERY='''query AutomationCheckoutReconciliation($after:String,$query:String) {
 abandonedCheckouts(first:100,after:$after,query:$query,sortKey:CREATED_AT,reverse:true) { nodes {
 id createdAt updatedAt completedAt abandonedCheckoutUrl customer { id firstName lastName email }
 shippingAddress { countryCodeV2 } billingAddress { countryCodeV2 }
 totalPriceSet { shopMoney { amount currencyCode } }
 } pageInfo { hasNextPage endCursor } } }'''

PERIODS={'Last 7 days':7,'Last 30 days':30,'Last 90 days':90,'Last year':365,'All time':None}

def window(period,at=None):
    """Rolling UTC, inclusive start/exclusive end; checkout cohort uses created_at."""
    at=at or now();days=PERIODS[period]
    return (at-timedelta(days=days) if days else None,at)

def details(store,checkout):
    """Cache only an exact Admin object matched to an existing signed ledger.

    Names/email are private admin display facts, never identity/consent authority.
    No recovery token, address or line item body is persisted here.
    """
    import os
    from crm_shopify_automation_events import key_from_recovery_url
    key=key_from_recovery_url(checkout.get('abandonedCheckoutUrl'),os.getenv('SHOPIFY_STORE_DOMAIN',''))
    customer=checkout.get('customer') or {};price=(checkout.get('totalPriceSet') or {}).get('shopMoney') or {}
    data={'name':' '.join(str(customer.get(k) or '')[:100] for k in ('firstName','lastName')).strip(),
          'email':str(customer.get('email') or '')[:254],
          'country':str((checkout.get('shippingAddress') or checkout.get('billingAddress') or {}).get('countryCodeV2') or '')[:2],
          'amount':str(price.get('amount') or '')[:40],'currency':str(price.get('currencyCode') or '')[:3]}
    if not key or not checkout.get('id') or not customer.get('id'):return
    # Narrow worker objects omit profile/price fields. Never erase richer values.
    data={k:v for k,v in data.items() if v}
    store.q("""UPDATE crm_shopify_checkouts SET admin_checkout_id=%s,analytics=analytics||%s::jsonb
      WHERE checkout_key=%s AND customer_id=%s AND
      NOT EXISTS(SELECT 1 FROM crm_suppressions WHERE shopify_customer_id=%s AND reason='redacted') AND
      (admin_checkout_id IS DISTINCT FROM %s OR analytics IS DISTINCT FROM analytics||%s::jsonb)""",
      (checkout['id'],json.dumps(data),key,customer['id'],customer['id'],checkout['id'],json.dumps(data)))

def reconcile(shop,store,period):
    """Explicit bounded refresh, not initial loading or typing. No enrollments."""
    start,_=window(period);cursor=None;count=0
    for _ in range(4):
        page=shop.query(RECONCILE_QUERY,{'after':cursor,'query':'created_at:>='+start.isoformat() if start else None},'automation checkout reconciliation',20,True)['abandonedCheckouts']
        for checkout in page['nodes']:details(store,checkout);count+=1
        info=page['pageInfo'];end=info.get('endCursor')
        if not info.get('hasNextPage'):return count,False
        if not end or end==cursor:raise ValueError('Checkout refresh did not advance.')
        cursor=end
    return count,True

LIST_SQL="""WITH selected AS MATERIALIZED (
 SELECT checkout_key,customer_id,created_at,activity_at,status,admin_checkout_id,analytics
 FROM crm_shopify_checkouts WHERE (%s::timestamptz IS NULL OR created_at>=%s) AND created_at<%s
 AND (%s::text IS NULL OR checkout_key=%s)
), journeys AS MATERIALIZED (
 SELECT DISTINCT ON(j.checkout_key) j.* FROM crm_automation_enrollments j JOIN selected c USING(checkout_key)
 WHERE j.automation_id=%s ORDER BY j.checkout_key,j.trigger_at DESC
), messages AS MATERIALIZED (
 SELECT s.id,s.enrollment_id,s.step_index,s.status,s.first_submitted_at,s.updated_at
 FROM crm_marketing_sends s JOIN journeys j ON j.id=s.enrollment_id WHERE NOT s.test_send
), events AS (
 SELECT e.send_id,count(*) FILTER(WHERE event_type='email.opened') AS opened,
 count(*) FILTER(WHERE event_type='email.clicked') AS clicked,max(occurred_at) AS last_event
 FROM crm_delivery_events e JOIN messages s ON s.id=e.send_id GROUP BY e.send_id
), receipts AS (
 SELECT s.enrollment_id,jsonb_agg(jsonb_build_object('step',step_index,'status',status,'submitted_at',first_submitted_at,'updated_at',updated_at) ORDER BY step_index) AS sends,
 sum(COALESCE(e.opened,0)) AS opened,sum(COALESCE(e.clicked,0)) AS clicked,max(e.last_event) AS last_event
 FROM messages s LEFT JOIN events e ON e.send_id=s.id GROUP BY s.enrollment_id
)
SELECT c.*,a.status AS automation_status,a.config->>'archived_at' AS archived_at,
 a.config->'published'->>'abandonment_seconds' AS abandonment_seconds,
 j.id AS enrollment_id,j.status AS flow_status,j.current_step,j.steps,j.next_due_at,
 GREATEST(c.activity_at,j.updated_at,r.last_event) AS last_activity_at,
 COALESCE(r.sends,'[]') AS sends,COALESCE(r.opened,0) AS opened,COALESCE(r.clicked,0) AS clicked
FROM selected c JOIN crm_automations a ON a.id=%s LEFT JOIN journeys j USING(checkout_key)
LEFT JOIN receipts r ON r.enrollment_id=j.id ORDER BY c.created_at DESC,c.checkout_key"""

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
    if checkout['status']=='RECOVERED' or checkout.get('flow_status')=='RECOVERED':return 'Recovered'
    if checkout.get('enrollment_id'):return 'Already in flow'
    if row['status']!='ACTIVE' or not row.get('steps') or row['config'].get('archived_at') or row['config'].get('deleted_at'):return 'Flow is not live'
    if not checkout.get('admin_checkout_id') or not checkout.get('customer_id'):return 'Refresh checkout details to verify identity'
    activity=date(checkout.get('activity_at'))
    threshold=int(row['config'].get('published',{}).get('abandonment_seconds',3600))
    if not activity or activity+timedelta(seconds=threshold)>at:return 'Checkout still inside abandonment wait period'
    return None
