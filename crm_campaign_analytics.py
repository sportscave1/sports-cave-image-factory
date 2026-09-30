"""Persisted campaign reporting. No Shopify or Resend calls on the UI path."""
from decimal import Decimal

def rate(n,d):return round(100*n/d,1) if d else None

def sent_page(store,offset=0,limit=25,*,archived=False):
    rows=store.q('''WITH campaigns AS (
      SELECT c.*,d.document->>'market' AS market,d.archived_at FROM crm_campaigns c
      JOIN crm_campaign_drafts d ON d.id=c.id WHERE c.status='SENT' AND (d.archived_at IS NOT NULL)=%s
      ORDER BY c.sent_at DESC NULLS LAST,c.id LIMIT %s OFFSET %s
    ), recipients AS (
      SELECT s.campaign_id,s.id,
        bool_or(e.event_type='email.delivered') AS delivered,
        bool_or(e.event_type='email.opened') AS opened,
        bool_or(e.event_type='email.clicked') AS clicked,
        bool_or(e.event_type='email.bounced') AS bounced,
        bool_or(e.event_type='email.complained') AS complained,
        bool_or(e.event_type='email.suppressed') AS suppressed
      FROM crm_marketing_sends s JOIN campaigns c ON c.id=s.campaign_id
      LEFT JOIN crm_delivery_events e ON e.send_id=s.id WHERE NOT s.test_send
      GROUP BY s.campaign_id,s.id
    ), totals AS (
      SELECT campaign_id,count(*) AS planned,
        count(*) FILTER(WHERE delivered) AS delivered,
        count(*) FILTER(WHERE delivered AND opened) AS opens,
        count(*) FILTER(WHERE delivered AND clicked) AS clicks,
        count(*) FILTER(WHERE bounced) AS bounces,
        count(*) FILTER(WHERE complained) AS complaints,
        count(*) FILTER(WHERE suppressed) AS suppressed FROM recipients GROUP BY campaign_id
    ), revenue AS (
      SELECT a.campaign_id,a.currency,sum(a.amount) AS amount,count(*) AS orders
      FROM crm_order_attribution a JOIN campaigns c ON c.id=a.campaign_id
      WHERE a.eligible GROUP BY a.campaign_id,a.currency
    ) SELECT c.*,COALESCE(c.final_recipient_count,t.planned,0) AS recipients,
      COALESCE(t.delivered,0) AS delivered,COALESCE(t.opens,0) AS opens,COALESCE(t.clicks,0) AS clicks,
      COALESCE(t.bounces,0) AS bounces,COALESCE(t.complaints,0) AS complaints,COALESCE(t.suppressed,0) AS suppressed,
      COALESCE((SELECT sum(r.orders) FROM revenue r WHERE r.campaign_id=c.id),0)::bigint AS orders,
      COALESCE((SELECT jsonb_object_agg(r.currency,r.amount) FROM revenue r WHERE r.campaign_id=c.id),'{}') AS revenue
      FROM campaigns c LEFT JOIN totals t ON t.campaign_id=c.id
      ORDER BY c.sent_at DESC NULLS LAST,c.id''',(archived,limit,offset))
    for row in rows:
        row['delivery_rate']=rate(row['delivered'],row['recipients'])
        row['open_rate']=rate(row['opens'],row['delivered'])
        row['click_rate']=rate(row['clicks'],row['delivered'])
        row['conversion_rate']=rate(row['orders'],row['recipients'])
        for label,denominator in (('revenue_per_recipient',row['recipients']),('revenue_per_click',row['clicks'])):
            row[label]={c:str(Decimal(str(amount))/denominator) if denominator else None for c,amount in row['revenue'].items()}
    return rows

def details(store,identity):
    products=store.q('''SELECT p->>'product_id' AS product_id,max(p->>'title') AS product,a.currency,
      count(DISTINCT a.shopify_order_id) AS orders,sum((p->>'quantity')::int) AS units,
      CASE WHEN bool_and(p->>'revenue' IS NOT NULL) THEN sum((p->>'revenue')::numeric) END AS revenue
      FROM crm_order_attribution a CROSS JOIN LATERAL jsonb_array_elements(a.products) p
      WHERE a.campaign_id=%s AND a.eligible GROUP BY p->>'product_id',a.currency ORDER BY revenue DESC NULLS LAST''',(identity,))
    timing=store.q('''SELECT avg(extract(epoch FROM order_created_at-click_at)) AS seconds,
      count(*) FILTER(WHERE mirror_status='UNAVAILABLE') AS mirror_unavailable
      FROM crm_order_attribution WHERE campaign_id=%s AND eligible''',(identity,),True)
    recipients=store.q('''SELECT s.shopify_customer_id,s.status,s.error_code,s.provider_email_id,
      min(e.occurred_at) FILTER(WHERE e.event_type='email.sent') AS sent,
      min(e.occurred_at) FILTER(WHERE e.event_type='email.delivered') AS delivered,
      min(e.occurred_at) FILTER(WHERE e.event_type='email.opened') AS first_open,
      min(e.occurred_at) FILTER(WHERE e.event_type='email.clicked') AS first_click,
      bool_or(e.event_type='email.bounced') AS bounced,bool_or(e.event_type='email.complained') AS complained,
      bool_or(e.event_type='email.suppressed') AS suppressed
      FROM crm_marketing_sends s LEFT JOIN crm_delivery_events e ON e.send_id=s.id
      WHERE s.campaign_id=%s AND NOT s.test_send GROUP BY s.id ORDER BY s.created_at LIMIT 100''',(identity,))
    return {'products':products,'timing':timing,'recipients':recipients}

def money(values):
    symbols={'AUD':'A$','USD':'US$','GBP':'£','CAD':'C$','NZD':'NZ$'}
    return ' · '.join(symbols.get(c,c+' ')+format(Decimal(str(v)),',.2f') if v is not None else '—' for c,v in values.items()) or '—'
