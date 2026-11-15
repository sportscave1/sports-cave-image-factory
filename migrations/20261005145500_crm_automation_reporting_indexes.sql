-- Read-only reporting indexes. No data, consent, RLS or runtime changes.
CREATE INDEX IF NOT EXISTS crm_auto_sent_time
 ON crm_marketing_sends(first_submitted_at DESC,enrollment_id)
 WHERE status='ACCEPTED' AND NOT test_send AND enrollment_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS crm_auto_entry_time
 ON crm_automation_enrollments(trigger_at DESC,automation_id);
CREATE INDEX IF NOT EXISTS crm_auto_terminal_time
 ON crm_automation_enrollments(updated_at DESC,automation_id)
 WHERE status IN ('RECOVERED','COMPLETED');
CREATE INDEX IF NOT EXISTS crm_auto_delivery_time
 ON crm_delivery_events(occurred_at DESC,send_id)
 WHERE event_type IN ('email.delivered','email.opened','email.clicked');
CREATE INDEX IF NOT EXISTS crm_auto_checkout_flow
 ON crm_automation_enrollments(checkout_key,automation_id,trigger_at DESC)
 WHERE checkout_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS crm_attribution_auto_time
 ON crm_order_attribution(order_created_at DESC)
 WHERE eligible AND evidence->>'automation_id' IS NOT NULL;
