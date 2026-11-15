BEGIN;
-- Reuse the shared test-send audit. Production journeys and executions already
-- reside in crm_automation_enrollments / crm_marketing_sends.
ALTER TABLE crm_internal_tests ALTER COLUMN campaign_id DROP NOT NULL;
ALTER TABLE crm_internal_tests ADD COLUMN automation_id uuid REFERENCES crm_automations(id);
ALTER TABLE crm_internal_tests ADD COLUMN automation_step_id uuid;
ALTER TABLE crm_internal_tests ADD CONSTRAINT crm_internal_test_source CHECK
 ((campaign_id IS NOT NULL AND automation_id IS NULL AND automation_step_id IS NULL)
  OR (campaign_id IS NULL AND automation_id IS NOT NULL AND automation_step_id IS NOT NULL));
CREATE INDEX crm_internal_tests_automation ON crm_internal_tests(automation_id,created_at DESC);
-- Bounded automation reporting uses the existing verified event and order ledger.
CREATE INDEX crm_enrollment_automation_customer ON crm_automation_enrollments(automation_id,shopify_customer_id,created_at DESC);
CREATE INDEX crm_attribution_automation ON crm_order_attribution((evidence->>'automation_id'),order_created_at) WHERE eligible;
-- Existing server-only RLS and browser-role revocations remain in effect.
COMMIT;
