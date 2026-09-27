-- Shopify-first CRM control plane ONLY. Generated locally with Supabase CLI.
-- Not part of the automatic deployment manifest. Apply only after approval.
BEGIN;
CREATE TABLE IF NOT EXISTS crm_segment_definitions (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), system_key text UNIQUE, name text NOT NULL,
 rules jsonb NOT NULL, created_by text NOT NULL DEFAULT '', updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS crm_templates (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), template_key text UNIQUE, name text NOT NULL,
 kind text NOT NULL CHECK(kind IN ('Automation','Campaign')), version integer NOT NULL DEFAULT 1,
 content jsonb NOT NULL, updated_at timestamptz NOT NULL DEFAULT now()
);
-- Immutable template versions are configuration, never per-recipient message copies.
CREATE TABLE IF NOT EXISTS crm_template_versions (
 template_id uuid NOT NULL REFERENCES crm_templates(id), version integer NOT NULL,
 content jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(template_id,version)
);
CREATE TABLE IF NOT EXISTS crm_automations (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), automation_key text NOT NULL UNIQUE, name text NOT NULL,
 status text NOT NULL DEFAULT 'DRAFT' CHECK(status IN ('DRAFT','ACTIVE','PAUSED')),
 trigger_type text NOT NULL, config jsonb NOT NULL DEFAULT '{}', steps jsonb NOT NULL DEFAULT '[]',
 activated_at timestamptz, updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS crm_automation_enrollments (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), automation_id uuid NOT NULL REFERENCES crm_automations(id),
 shopify_customer_id text NOT NULL, trigger_shopify_id text NOT NULL, trigger_key text NOT NULL,
 trigger_at timestamptz NOT NULL, steps jsonb NOT NULL, current_step integer NOT NULL DEFAULT 0,
 status text NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE','COMPLETED','STOPPED','RECOVERED')),
 next_due_at timestamptz NOT NULL, last_checked_at timestamptz, stop_reason text NOT NULL DEFAULT '',
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(automation_id,trigger_key)
);
CREATE TABLE IF NOT EXISTS crm_campaigns (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), name text NOT NULL,
 shopify_segment_id text, segment_definition_id uuid REFERENCES crm_segment_definitions(id),
 template_id uuid NOT NULL, template_version integer NOT NULL,
 status text NOT NULL DEFAULT 'DRAFT' CHECK(status IN ('DRAFT','SCHEDULED','BUILDING','SENDING','SENT','PAUSED','CANCELLED')),
 scheduled_at timestamptz, recipient_cursor text, snapshot_at timestamptz, resume_status text,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 CHECK ((shopify_segment_id IS NULL) <> (segment_definition_id IS NULL)),
 FOREIGN KEY(template_id,template_version) REFERENCES crm_template_versions(template_id,version)
);
-- Also serves as campaign recipient / automation step-run records: IDs and state only.
CREATE TABLE IF NOT EXISTS crm_marketing_sends (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), idempotency_key text NOT NULL UNIQUE,
 shopify_customer_id text, recipient_hash text, campaign_id uuid REFERENCES crm_campaigns(id),
 enrollment_id uuid REFERENCES crm_automation_enrollments(id), step_index integer,
 test_send boolean NOT NULL DEFAULT false, test_recipient text,
 template_id uuid NOT NULL, template_version integer NOT NULL, request_hash text NOT NULL DEFAULT '',
 status text NOT NULL DEFAULT 'PENDING' CHECK(status IN
   ('PENDING','CLAIMED','SUBMITTING','ACCEPTED','BLOCKED','FAILED','UNCERTAIN')),
 due_at timestamptz NOT NULL DEFAULT now(), attempts integer NOT NULL DEFAULT 0,
 lease_token uuid, lease_until timestamptz, first_submitted_at timestamptz,
 provider_email_id text UNIQUE, error_code text NOT NULL DEFAULT '',
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 CHECK(test_send OR test_recipient IS NULL),
 FOREIGN KEY(template_id,template_version) REFERENCES crm_template_versions(template_id,version),
 UNIQUE(campaign_id,shopify_customer_id), UNIQUE(campaign_id,recipient_hash), UNIQUE(enrollment_id,step_index)
);
CREATE TABLE IF NOT EXISTS crm_marketing_events (
 event_id text PRIMARY KEY, provider_email_id text, event_type text NOT NULL,
 recipient_hash text, occurred_at timestamptz NOT NULL, link_host text NOT NULL DEFAULT '',
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS crm_suppressions (
 recipient_hash text PRIMARY KEY, shopify_customer_id text,
 reason text NOT NULL CHECK(reason IN ('unsubscribe','bounce','complaint','manual','suppressed','redacted')),
 source text NOT NULL, provider_synced boolean NOT NULL DEFAULT false,
 -- Only suppressions retain an address when necessary for provider stop-state sync.
 email_for_provider text, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS crm_webhook_events (
 provider text NOT NULL, event_id text NOT NULL, topic text NOT NULL,
 object_id text NOT NULL DEFAULT '', related_customer_id text NOT NULL DEFAULT '',
 occurred_at timestamptz NOT NULL, status text NOT NULL DEFAULT 'PENDING'
   CHECK(status IN ('PENDING','CLAIMED','DONE','FAILED')),
 lease_token uuid, lease_until timestamptz, attempts integer NOT NULL DEFAULT 0,
 received_at timestamptz NOT NULL DEFAULT now(), processed_at timestamptz, error_code text NOT NULL DEFAULT '',
 PRIMARY KEY(provider,event_id)
);
CREATE TABLE IF NOT EXISTS crm_runtime_state (
 key text PRIMARY KEY, value jsonb NOT NULL DEFAULT '{}', updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS crm_enrollment_due_idx ON crm_automation_enrollments(next_due_at) WHERE status='ACTIVE';
CREATE INDEX IF NOT EXISTS crm_enrollment_customer_idx ON crm_automation_enrollments(shopify_customer_id);
CREATE INDEX IF NOT EXISTS crm_enrollment_trigger_idx ON crm_automation_enrollments(trigger_shopify_id);
CREATE INDEX IF NOT EXISTS crm_campaign_status_idx ON crm_campaigns(status,scheduled_at);
CREATE INDEX IF NOT EXISTS crm_send_due_idx ON crm_marketing_sends(status,due_at,lease_until);
CREATE INDEX IF NOT EXISTS crm_send_customer_idx ON crm_marketing_sends(shopify_customer_id);
CREATE INDEX IF NOT EXISTS crm_event_provider_idx ON crm_marketing_events(provider_email_id,event_type);
CREATE INDEX IF NOT EXISTS crm_event_date_idx ON crm_marketing_events(occurred_at);
CREATE INDEX IF NOT EXISTS crm_suppression_customer_idx ON crm_suppressions(shopify_customer_id);
CREATE INDEX IF NOT EXISTS crm_webhook_pending_idx ON crm_webhook_events(status,received_at,lease_until);
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['crm_segment_definitions','crm_templates','crm_template_versions','crm_automations',
  'crm_automation_enrollments','crm_campaigns','crm_marketing_sends','crm_marketing_events',
  'crm_suppressions','crm_webhook_events','crm_runtime_state'] LOOP
   EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',t);
   EXECUTE format('REVOKE ALL ON %I FROM PUBLIC, anon, authenticated',t);
 END LOOP;
END $$;
COMMIT;
