-- Local review only. No page-load DDL and no Shopify customer mirror.
BEGIN;
ALTER TABLE crm_campaign_drafts DROP CONSTRAINT IF EXISTS crm_campaign_drafts_status_check;
UPDATE crm_campaign_drafts SET status=CASE status WHEN 'NEEDS REVIEW' THEN 'NEEDS_REVIEW' WHEN 'TEST READY' THEN 'TEST_READY' WHEN 'COMPLIANCE BLOCKED' THEN 'NEEDS_REVIEW' WHEN 'CANCELED' THEN 'ARCHIVED' ELSE status END;
ALTER TABLE crm_campaign_drafts ADD CONSTRAINT crm_campaign_drafts_status_check CHECK(status IN ('DRAFT','NEEDS_REVIEW','TEST_READY','TESTED','ARCHIVED'));
ALTER TABLE crm_templates ADD COLUMN IF NOT EXISTS archived_at timestamptz;
ALTER TABLE crm_suppressions ADD COLUMN IF NOT EXISTS shopify_sync_state text NOT NULL DEFAULT 'PENDING';
ALTER TABLE crm_suppressions ADD COLUMN IF NOT EXISTS shopify_sync_attempts integer NOT NULL DEFAULT 0;
ALTER TABLE crm_suppressions ADD COLUMN IF NOT EXISTS shopify_sync_error text;
ALTER TABLE crm_suppressions ADD COLUMN IF NOT EXISTS shopify_sync_checked_at timestamptz;
CREATE TABLE crm_workspace_settings (
 key text PRIMARY KEY, value jsonb NOT NULL, version integer NOT NULL DEFAULT 1,
 updated_by text NOT NULL, updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE crm_settings_history (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, key text NOT NULL, version integer NOT NULL,
 value jsonb NOT NULL, actor text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE crm_internal_tests (
 id uuid PRIMARY KEY, campaign_id uuid NOT NULL REFERENCES crm_campaign_drafts(id),
 campaign_version integer NOT NULL, render_hash text NOT NULL, recipient text NOT NULL,
 sender text NOT NULL, actor text NOT NULL, status text NOT NULL CHECK(status IN ('REQUESTED','ACCEPTED','FAILED','UNCERTAIN')),
 provider_id text UNIQUE, error_category text, created_at timestamptz NOT NULL DEFAULT now(), accepted_at timestamptz
);
CREATE INDEX crm_internal_tests_campaign ON crm_internal_tests(campaign_id,created_at DESC);
CREATE TABLE crm_delivery_events (
 event_id text PRIMARY KEY, provider_id text NOT NULL, event_type text NOT NULL,
 occurred_at timestamptz NOT NULL, received_at timestamptz NOT NULL DEFAULT now(),
 hard_bounce boolean NOT NULL DEFAULT false,
 test_id uuid REFERENCES crm_internal_tests(id), send_id uuid REFERENCES crm_marketing_sends(id),
 CHECK (test_id IS NULL OR send_id IS NULL)
);
CREATE INDEX crm_delivery_events_provider ON crm_delivery_events(provider_id,occurred_at);
CREATE TABLE crm_website_events (
 event_id text PRIMARY KEY, event_type text NOT NULL, session_ref uuid NOT NULL,
 campaign_key text, product_ref text, occurred_at timestamptz NOT NULL,
 test_context boolean NOT NULL, received_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX crm_website_events_campaign ON crm_website_events(campaign_key,test_context,occurred_at);
CREATE INDEX crm_website_events_received ON crm_website_events(received_at);
CREATE TABLE crm_order_attribution (
 shopify_order_id text PRIMARY KEY, campaign_id uuid NOT NULL REFERENCES crm_campaign_drafts(id),
 campaign_key text NOT NULL, order_created_at timestamptz NOT NULL, visit_at timestamptz NOT NULL,
 amount numeric(18,2) NOT NULL, currency text NOT NULL, eligible boolean NOT NULL,
 model text NOT NULL DEFAULT 'shopify_last_recorded_visit_30d', checked_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX crm_order_attribution_campaign ON crm_order_attribution(campaign_id,order_created_at);
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['crm_workspace_settings','crm_settings_history','crm_internal_tests','crm_delivery_events','crm_website_events','crm_order_attribution'] LOOP
  EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('REVOKE ALL ON TABLE %I FROM PUBLIC, anon, authenticated',t);
 END LOOP;
END $$;
REVOKE ALL ON SEQUENCE crm_settings_history_id_seq FROM PUBLIC, anon, authenticated;
COMMIT;
