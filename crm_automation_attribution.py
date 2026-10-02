"""Project automation sends into the canonical email attribution matcher."""
from crm_tracking import send_identity


def candidates(store,order,days):
    from datetime import timedelta
    from crm_logic import date
    # Only this customer's accepted sends in the canonical attribution window.
    rows=store.q("""SELECT s.id,s.provider_email_id,s.shopify_customer_id,s.first_submitted_at,
      e.id AS journey_id,e.automation_id,e.source_event_id,e.checkout_key,a.name,v.content->>'step_id' AS step_id,
      v.content->>'automation_version' AS automation_version
      FROM crm_marketing_sends s JOIN crm_automation_enrollments e ON e.id=s.enrollment_id
      JOIN crm_automations a ON a.id=e.automation_id
      JOIN crm_template_versions v ON v.template_id=s.template_id AND v.version=s.template_version
      WHERE NOT s.test_send AND s.status='ACCEPTED' AND v.content->>'format'='automation_delivery_v1'
        AND s.shopify_customer_id=%s AND s.first_submitted_at<=%s AND s.first_submitted_at>=%s""",
      ((order.get('customer') or {}).get('id'),date(order['createdAt']),date(order['createdAt'])-timedelta(days=days)))
    return [{**r,'campaign_key':'auto_'+str(r['id']).replace('-',''),'campaign_send_id':send_identity(r['id']),
             'status':'SENT','sending_started_at':r['first_submitted_at']} for r in rows]


def clicks(store,order,days):
    from datetime import timedelta
    from crm_logic import date
    return store.q("""SELECT s.id AS send_id,s.provider_email_id,s.shopify_customer_id,e.occurred_at,e.clicked_url
      FROM crm_delivery_events e JOIN crm_marketing_sends s ON s.id=e.send_id
      JOIN crm_template_versions v ON v.template_id=s.template_id AND v.version=s.template_version
      WHERE e.event_type='email.clicked' AND NOT s.test_send AND s.status='ACCEPTED'
        AND v.content->>'format'='automation_delivery_v1' AND s.shopify_customer_id=%s
        AND e.occurred_at<=%s AND e.occurred_at>=%s""",
        ((order.get('customer') or {}).get('id'),date(order['createdAt']),date(order['createdAt'])-timedelta(days=days)))
