"""Read-only home projections. Persisted analytics only; no campaign bodies or APIs."""
from crm_campaign_analytics import rate
from decimal import Decimal
from datetime import datetime, timedelta, timezone

TTL = 20
PAGE_SIZE = 12


def invalidate(state):
    # Detach in-flight reads without discarding last-good display values. An old
    # future can finish, but only the newly registered future may be published.
    state.pop('campaign_home_cache', None)
    state.pop('campaign_home_window', None)
    state.pop('campaign_home_reported_errors', None)


def reporting_window():
    """One UTC [start, end) window shared by every 30-day summary group."""
    end = datetime.now(timezone.utc)
    return end - timedelta(days=30), end


def counts(store):
    return store.q("""SELECT count(*) AS all_count,
      count(*) FILTER(WHERE d.archived_at IS NULL AND c.status IS NULL) AS drafts,
      count(*) FILTER(WHERE d.archived_at IS NULL AND c.status IS NOT NULL AND c.status<>'SENT') AS active,
      count(*) FILTER(WHERE d.archived_at IS NULL AND c.status='SENT') AS sent,
      count(*) FILTER(WHERE d.archived_at IS NOT NULL) AS archived
      FROM crm_campaign_drafts d LEFT JOIN crm_campaigns c ON c.id=d.id""", one=True)


def delivery_summary(store, window):
    # Provider facts come from the verified Resend webhook ledger, counted once
    # per production recipient. Preserve the existing mean campaign click rate.
    return store.q("""WITH recent AS (
      SELECT id FROM crm_campaigns WHERE status='SENT' AND sent_at>=%s AND sent_at<%s
    ), recipients AS (
      SELECT s.campaign_id,s.id,bool_or(e.event_type='email.delivered') AS delivered,
        bool_or(e.event_type='email.clicked') AS clicked
      FROM crm_marketing_sends s JOIN recent c ON c.id=s.campaign_id
      LEFT JOIN crm_delivery_events e ON e.send_id=s.id WHERE NOT s.test_send
      GROUP BY s.campaign_id,s.id
    ), rates AS (
      SELECT campaign_id,100.0*count(*) FILTER(WHERE delivered AND clicked)/
        NULLIF(count(*) FILTER(WHERE delivered),0) AS rate FROM recipients GROUP BY campaign_id
    ) SELECT (SELECT count(*) FROM crm_marketing_sends s JOIN crm_campaigns c ON c.id=s.campaign_id
      WHERE NOT s.test_send AND s.status='ACCEPTED' AND s.first_submitted_at>=%s AND s.first_submitted_at<%s) AS sent_emails,
      (SELECT avg(rate) FROM rates) AS click_rate""", (*window, *window), one=True)


def attribution_summary(store, window):
    # Eligible Shopify-derived attribution is the canonical app record, not a
    # fresh Shopify order scan. Aggregate the bounded period once for both cards.
    return store.q("""WITH amounts AS (
      SELECT a.currency,sum(a.amount) AS amount,count(*) AS orders FROM crm_order_attribution a
      JOIN crm_campaigns c ON c.id=a.campaign_id WHERE a.eligible
      AND a.order_created_at>=%s AND a.order_created_at<%s GROUP BY a.currency
    ) SELECT COALESCE(jsonb_object_agg(currency,amount),'{}') AS revenue,
      COALESCE(sum(orders),0)::bigint AS orders FROM amounts""", window, one=True)


def summary(store):
    """Compatibility projection; the Home UI schedules these groups independently."""
    window = reporting_window()
    return {**counts(store), **delivery_summary(store, window), **attribution_summary(store, window)}


def top_identity(store):
    # Currency amounts cannot safely be compared across markets. Rank transparently
    # by the existing factual attributed-order count, never an invented score.
    row = store.q("""SELECT c.id FROM crm_campaigns c JOIN crm_campaign_drafts d ON d.id=c.id
      JOIN crm_order_attribution a ON a.campaign_id=c.id AND a.eligible
      WHERE c.status='SENT' AND d.archived_at IS NULL
      GROUP BY c.id,c.sent_at HAVING count(*)>0 ORDER BY count(*) DESC,c.sent_at DESC,c.id LIMIT 1""", one=True)
    return str(row['id']) if row else None


def rows(store, *, tab='All campaigns', search='', market='All', status='All', oldest=False, offset=0, top=None, detail=None):
    # The page and top-performer projections share one metrics statement. No N+1.
    order = 'ASC' if oldest else 'DESC'
    result = store.q("""WITH base AS (
      SELECT d.id,d.name,d.version,d.status AS draft_status,d.archived_at,d.last_tested_at,
        d.document->>'market' AS market,
        GREATEST(d.updated_at,c.updated_at) AS updated_at,c.sent_at,c.status AS delivery_status,
        c.template_id,c.template_version,c.final_recipient_count,
        CASE WHEN d.archived_at IS NOT NULL THEN 'Archived' WHEN c.status='SENT' THEN 'Sent'
          WHEN c.status IS NULL THEN 'Drafts' ELSE 'Active' END AS category
      FROM crm_campaign_drafts d LEFT JOIN crm_campaigns c ON c.id=d.id
    ), page AS (
      SELECT * FROM base WHERE (%s='All campaigns' OR category=%s)
        AND position(lower(%s) in lower(name))>0 AND (%s='All' OR market=%s)
        AND (%s='All' OR COALESCE(delivery_status,draft_status)=%s)
      ORDER BY updated_at """+order+""",id LIMIT %s OFFSET %s
    ), selected AS (
      SELECT *,true AS in_page FROM page
      UNION ALL SELECT *,false AS in_page FROM base WHERE id=ANY(%s::uuid[]) AND id NOT IN (SELECT id FROM page)
    ), recipients AS (
      SELECT s.campaign_id,s.id,bool_or(e.event_type='email.delivered') AS delivered,
        bool_or(e.event_type='email.opened') AS opened,bool_or(e.event_type='email.clicked') AS clicked,
        bool_or(e.event_type='email.bounced') AS bounced,bool_or(e.event_type='email.complained') AS complained,
        bool_or(e.event_type='email.suppressed') AS suppressed
      FROM crm_marketing_sends s JOIN selected c ON c.id=s.campaign_id
      LEFT JOIN crm_delivery_events e ON e.send_id=s.id WHERE NOT s.test_send GROUP BY s.campaign_id,s.id
    ), totals AS (
      SELECT campaign_id,count(*) AS planned,count(*) FILTER(WHERE delivered) AS delivered,
        count(*) FILTER(WHERE delivered AND opened) AS opens,count(*) FILTER(WHERE delivered AND clicked) AS clicks,
        count(*) FILTER(WHERE bounced) AS bounces,count(*) FILTER(WHERE complained) AS complaints,
        count(*) FILTER(WHERE suppressed) AS suppressed FROM recipients GROUP BY campaign_id
    ), amounts AS (
      SELECT a.campaign_id,a.currency,sum(a.amount) AS amount,count(*) AS orders
      FROM crm_order_attribution a JOIN selected c ON c.id=a.campaign_id WHERE a.eligible GROUP BY a.campaign_id,a.currency
    ), revenue AS (
      SELECT campaign_id,jsonb_object_agg(currency,amount) AS revenue,sum(orders) AS orders FROM amounts GROUP BY campaign_id
    ) SELECT c.*,d.document->'content'->>'subject' AS subject,
      jsonb_path_query_first(d.document,'$.middle_sections[*] ? (@.type == "catalogue" && @.visible == true).products[*].image') #>> '{}' AS thumbnail,
      CASE WHEN delivery_status IS NOT NULL THEN COALESCE(final_recipient_count,t.planned,0) END AS recipients,
      CASE WHEN delivery_status IS NOT NULL THEN COALESCE(t.delivered,0) END AS delivered,
      CASE WHEN delivery_status IS NOT NULL THEN COALESCE(t.opens,0) END AS opens,
      CASE WHEN delivery_status IS NOT NULL THEN COALESCE(t.clicks,0) END AS clicks,
      COALESCE(t.bounces,0) AS bounces,COALESCE(t.complaints,0) AS complaints,COALESCE(t.suppressed,0) AS suppressed,
      COALESCE(r.orders,0)::bigint AS orders,COALESCE(r.revenue,'{}') AS revenue
      FROM selected c JOIN crm_campaign_drafts d ON d.id=c.id LEFT JOIN totals t ON t.campaign_id=c.id LEFT JOIN revenue r ON r.campaign_id=c.id
      ORDER BY c.updated_at """+order+""",c.id""",
      (tab,tab,search[:150],market,market,status,status,PAGE_SIZE+1,max(0,int(offset)),list(dict.fromkeys(i for i in (top,detail) if i))))
    for row in result:
        row['status'] = row['delivery_status'] or row['draft_status']
        row['delivery_rate'] = rate(row['delivered'] or 0,row['recipients'] or 0)
        row['open_rate'] = rate(row['opens'] or 0,row['delivered'] or 0)
        row['click_rate'] = rate(row['clicks'] or 0,row['delivered'] or 0)
        row['conversion_rate'] = rate(row['orders'],row['recipients'] or 0)
        row['revenue_per_click'] = {c:str(Decimal(str(v))/row['clicks']) if row['clicks'] else None for c,v in row['revenue'].items()}
    return result
