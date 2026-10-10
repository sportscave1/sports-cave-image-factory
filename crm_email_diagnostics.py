"""On-demand, aggregate-only operational reads; never enroll, queue or send."""
from datetime import timezone
from crm_logic import date, now


def utc(value):
    stamp=date(value)
    return stamp.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC') if stamp else 'None recorded'


def worker_label(state,at=None):
    stamp=date(state.get('checked_at'));at=at or now()
    if not stamp:return 'No completed cycle recorded'
    age=(at-stamp).total_seconds()
    health='Recent completed cycle' if 0<=age<=300 else 'Heartbeat stale — inspect worker'
    return health+' · '+utc(stamp)+' · marketing '+('enabled' if state.get('marketing_enabled') else 'disabled')


def automation_status(store,row):
    topics={'abandoned':['checkouts/create','checkouts/update'], 'welcome':['customers_email_marketing_consent/update'],
            'post_purchase':['orders/paid'],'fulfilled':['orders/fulfilled'],'win_back':['orders/paid']}
    result=store.q("""SELECT
      (SELECT max(received_at) FROM crm_webhook_events WHERE provider='shopify' AND topic=ANY(%s)) AS latest_event,
      (SELECT value FROM crm_runtime_state WHERE key='worker_health') AS worker,
      (SELECT value FROM crm_runtime_state WHERE key='campaign_schedule_health') AS schedule_health,
      (SELECT value FROM crm_runtime_state WHERE key='checkout-cache-v2') AS reconciliation,
      (SELECT min(next_due_at) FROM crm_automation_enrollments WHERE automation_id=%s AND status='ACTIVE') AS next_due,
      (SELECT min(retry_after) FROM crm_automation_enrollments WHERE automation_id=%s AND status='ACTIVE' AND retry_after>now()) AS retry_after,
      (SELECT count(*) FROM crm_automation_enrollments WHERE automation_id=%s) AS enrolled,
      (SELECT jsonb_object_agg(status,n) FROM (
        SELECT s.status,count(*) AS n FROM crm_marketing_sends s JOIN crm_automation_enrollments j ON j.id=s.enrollment_id
        WHERE j.automation_id=%s AND NOT s.test_send GROUP BY s.status) x) AS sends,
      (SELECT count(*) FROM crm_marketing_sends s JOIN crm_automation_enrollments j ON j.id=s.enrollment_id
        WHERE j.automation_id=%s AND NOT s.test_send AND s.status='ACCEPTED' AND s.provider_email_id IS NOT NULL) AS accepted,
      (SELECT jsonb_object_agg(result,n) FROM (
        SELECT value->>'result' AS result,count(*) AS n FROM (
          SELECT value FROM crm_runtime_state WHERE starts_with(key,'checkout-evaluation:') AND key LIKE %s
          ORDER BY updated_at DESC LIMIT 100) recent GROUP BY value->>'result') x WHERE result IS NOT NULL) AS evaluations
      """,(topics.get(row['trigger_type'],[]),row['id'],row['id'],row['id'],row['id'],row['id'],'%:'+str(row['id'])),True)
    from crm_automation_timing import enrollment_steps
    result['steps']=enrollment_steps(row) if row['config'].get('published_version') else []
    result['draft_steps']=[{'name':s.get('name') or 'Email '+str(i+1),'enabled':s.get('enabled',True),'delay_seconds':s['delay_seconds']}
                           for i,s in enumerate(row['config'].get('draft',{}).get('emails',[]))]
    return result


def campaign_status(store,identity):
    return store.q("""SELECT
      (SELECT value FROM crm_runtime_state WHERE key='worker_health') AS worker,
      (SELECT value FROM crm_runtime_state WHERE key='campaign_schedule_health') AS schedule_health,
      COALESCE(t.value->'timing',v.content->'document'->'send_timing') AS timing,
      (SELECT jsonb_agg(z) FROM (SELECT
        CASE WHEN t.value->'timing'->>'time_basis'='campaign_timezone' THEN t.value->'timing'->>'timezone'
          ELSE v.content->'schedule'->s.recipient_hash->>'timezone' END AS timezone,
        count(*) AS recipients,min(s.due_at) AS due_at FROM crm_marketing_sends s
        WHERE s.campaign_id=c.id AND NOT s.test_send GROUP BY 1) z) AS zones,
      (SELECT count(*) FROM crm_marketing_sends WHERE campaign_id=c.id AND NOT test_send AND status='ACCEPTED'
        AND provider_email_id IS NOT NULL) AS accepted,
      (SELECT count(DISTINCT e.send_id) FROM crm_delivery_events e JOIN crm_marketing_sends s ON s.id=e.send_id
        WHERE s.campaign_id=c.id AND NOT s.test_send AND e.event_type='email.delivered') AS delivered,
      (SELECT count(DISTINCT e.send_id) FROM crm_delivery_events e JOIN crm_marketing_sends s ON s.id=e.send_id
        WHERE s.campaign_id=c.id AND NOT s.test_send AND e.event_type IN ('email.bounced','email.failed','email.suppressed','email.complained')) AS delivery_problems
      FROM crm_campaigns c JOIN crm_template_versions v ON v.template_id=c.template_id AND v.version=c.template_version
      LEFT JOIN crm_runtime_state t ON t.key='campaign-timing:'||c.id::text
      WHERE c.id=%s""",(identity,),True)
