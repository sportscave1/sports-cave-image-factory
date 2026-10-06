-- Additive scheduler metadata only. Does not enqueue, enrol, or send mail.
BEGIN;
ALTER TABLE crm_automation_enrollments ADD COLUMN IF NOT EXISTS retry_after timestamptz;
CREATE INDEX IF NOT EXISTS crm_enrollment_due_active ON crm_automation_enrollments(next_due_at,id) WHERE status='ACTIVE';
CREATE INDEX IF NOT EXISTS crm_checkout_trigger_candidates ON crm_shopify_checkouts(activity_at,checkout_key)
 WHERE admin_checkout_id IS NOT NULL AND status<>'RECOVERED';
-- Frozen existing journeys already have qualification included in trigger_at.
-- Repair only missing deadlines, never move an existing one or replay a send.
UPDATE crm_automation_enrollments e SET next_due_at =
 CASE WHEN e.current_step=0 THEN e.trigger_at ELSE (
   SELECT s.updated_at FROM crm_marketing_sends s WHERE s.enrollment_id=e.id
    AND s.step_index=e.current_step-1 AND s.status='ACCEPTED' AND s.provider_email_id IS NOT NULL
   ORDER BY s.updated_at DESC LIMIT 1) END
 + make_interval(secs => (e.steps->e.current_step->>'delay_seconds')::int)
 WHERE e.status='ACTIVE' AND e.next_due_at IS NULL
   AND e.steps->e.current_step->>'automation_version' IS NOT NULL
   AND e.steps->e.current_step->>'delay_seconds' ~ '^[0-9]+$';
COMMIT;
