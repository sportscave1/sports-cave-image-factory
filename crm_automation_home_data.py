"""Bounded automation projections over the existing send/event/order ledgers."""
from crm_campaign_home_data import PAGE_SIZE, TTL, reporting_window

VISIBLE="a.config->>'deleted_at' IS NULL"
CATEGORY="CASE WHEN a.config->>'archived_at' IS NOT NULL THEN 'Archived' WHEN a.status='DRAFT' THEN 'Drafts' WHEN a.status='ACTIVE' THEN 'Active' ELSE 'Paused' END"


def counts(store):
    return store.q("SELECT count(*) AS all_count,count(*) FILTER(WHERE category='Drafts') AS drafts,count(*) FILTER(WHERE category='Active') AS active,count(*) FILTER(WHERE category='Paused') AS paused,count(*) FILTER(WHERE category='Archived') AS archived FROM (SELECT "+CATEGORY+" AS category FROM crm_automations a WHERE "+VISIBLE+") t",one=True)


def delivery_summary(store,window):
    # Same verified per-message event semantics and accepted denominator as Home.
    return store.q("""WITH recipients AS (
      SELECT j.automation_id,s.id,bool_or(e.event_type='email.delivered') AS delivered,
        bool_or(e.event_type='email.clicked') AS clicked,
        bool_or(e.event_type='email.bounced' AND e.occurred_at>=%s AND e.occurred_at<%s) AS bounced
      FROM crm_marketing_sends s JOIN crm_automation_enrollments j ON j.id=s.enrollment_id
      LEFT JOIN crm_delivery_events e ON e.send_id=s.id
      WHERE NOT s.test_send AND s.status='ACCEPTED' AND s.first_submitted_at>=%s AND s.first_submitted_at<%s
      GROUP BY j.automation_id,s.id
    ), rates AS (SELECT automation_id,100.0*count(*) FILTER(WHERE delivered AND clicked)/NULLIF(count(*) FILTER(WHERE delivered),0) AS rate FROM recipients GROUP BY automation_id)
    SELECT count(*) AS sent_emails,100.0*count(*) FILTER(WHERE bounced)/NULLIF(count(*),0) AS bounce_rate,
      (SELECT avg(rate) FROM rates) AS click_rate FROM recipients""",(*window,*window),one=True)


def orders_summary(store,window):
    return store.q("SELECT count(*) AS orders FROM crm_order_attribution WHERE eligible AND evidence->>'automation_id' IS NOT NULL AND order_created_at>=%s AND order_created_at<%s",window,one=True)


def rows(store,*,tab='All automations',search='',trigger='All',oldest=False,offset=0):
    return store.q("""WITH page AS (
      SELECT a.id,a.name,a.trigger_type,a.updated_at,a.config->>'format' AS format,"""+CATEGORY+""" AS category FROM crm_automations a
      WHERE """+VISIBLE+" AND (%s='All automations' OR ("+CATEGORY+""" )=%s)
        AND position(lower(%s) in lower(a.name))>0 AND (%s='All' OR a.trigger_type=%s)
      ORDER BY a.updated_at """+('ASC' if oldest else 'DESC')+""",a.id LIMIT %s OFFSET %s
    ), recipients AS (
      SELECT j.automation_id,s.id,s.status,bool_or(e.event_type='email.delivered') AS delivered,
        bool_or(e.event_type='email.opened') AS opened,bool_or(e.event_type='email.clicked') AS clicked
      FROM crm_automation_enrollments j JOIN page p ON p.id=j.automation_id
      JOIN crm_marketing_sends s ON s.enrollment_id=j.id AND NOT s.test_send
      LEFT JOIN crm_delivery_events e ON e.send_id=s.id GROUP BY j.automation_id,s.id,s.status
    ), totals AS (SELECT automation_id,count(*) FILTER(WHERE status='ACCEPTED') AS sent,
      count(*) FILTER(WHERE delivered) AS delivered,count(*) FILTER(WHERE delivered AND opened) AS opened,
      count(*) FILTER(WHERE delivered AND clicked) AS clicked FROM recipients GROUP BY automation_id)
    SELECT p.*,COALESCE(t.sent,0) AS sent,COALESCE(t.delivered,0) AS delivered,COALESCE(t.opened,0) AS opened,COALESCE(t.clicked,0) AS clicked,
      (SELECT count(*) FROM crm_automation_enrollments j WHERE j.automation_id=p.id) AS entered,
      (SELECT count(*) FROM crm_order_attribution o WHERE o.eligible AND o.evidence->>'automation_id'=p.id::text) AS orders
      FROM page p LEFT JOIN totals t ON t.automation_id=p.id ORDER BY p.updated_at """+('ASC' if oldest else 'DESC')+",p.id",
      (tab,tab,search[:150],trigger,trigger,PAGE_SIZE+1,max(0,int(offset))))


def step_metrics(store,identity):
    return store.q("""WITH executions AS (SELECT s.*,v.content->>'step_id' AS step_id FROM crm_marketing_sends s
      JOIN crm_automation_enrollments j ON j.id=s.enrollment_id JOIN crm_template_versions v
      ON v.template_id=s.template_id AND v.version=s.template_version WHERE j.automation_id=%s AND NOT s.test_send)
      SELECT s.step_id,count(DISTINCT s.id) FILTER(WHERE s.status='ACCEPTED') AS sent,
      count(DISTINCT s.id) FILTER(WHERE e.event_type='email.delivered') AS delivered,
      count(DISTINCT s.id) FILTER(WHERE e.event_type='email.opened') AS opened,
      count(DISTINCT s.id) FILTER(WHERE e.event_type='email.clicked') AS clicked,
      count(DISTINCT s.id) FILTER(WHERE e.event_type='email.bounced') AS bounced,
      (SELECT count(*) FROM crm_order_attribution o WHERE o.eligible AND o.evidence->>'automation_id'=%s
        AND o.evidence->>'step_id'=s.step_id) AS orders
      FROM executions s LEFT JOIN crm_delivery_events e ON e.send_id=s.id GROUP BY s.step_id""",(identity,str(identity)))
