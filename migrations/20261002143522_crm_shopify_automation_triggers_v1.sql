-- Minimal server-only facts. No email addresses, raw payloads or checkout tokens.
BEGIN;
ALTER TABLE crm_webhook_events ADD COLUMN IF NOT EXISTS normalized jsonb NOT NULL DEFAULT '{}';
ALTER TABLE crm_automation_enrollments ADD COLUMN IF NOT EXISTS checkout_key text;
ALTER TABLE crm_automation_enrollments ADD COLUMN IF NOT EXISTS source_event_id text;
CREATE TABLE IF NOT EXISTS crm_shopify_checkouts (
 checkout_key text PRIMARY KEY, shop text NOT NULL, customer_id text NOT NULL DEFAULT '', source_event_id text NOT NULL,
 created_at timestamptz NOT NULL, activity_at timestamptz NOT NULL,
 status text NOT NULL CHECK(status IN ('OPEN','ABANDONED','RECOVERY_EMAIL_SENT','RECOVERED')),
 admin_checkout_id text, order_id text, updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS crm_checkout_due ON crm_shopify_checkouts(shop,activity_at) WHERE status<>'RECOVERED';
CREATE INDEX IF NOT EXISTS crm_enrollment_checkout ON crm_automation_enrollments(checkout_key) WHERE checkout_key IS NOT NULL;
CREATE TABLE IF NOT EXISTS crm_shopify_pixel_events (
 event_id text PRIMARY KEY, shop text NOT NULL, event_name text NOT NULL,
 client_hash text NOT NULL, product_id text, occurred_at timestamptz NOT NULL,
 received_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS crm_pixel_received ON crm_shopify_pixel_events(received_at);
-- Consent transition control only, never a customer profile mirror.
CREATE TABLE IF NOT EXISTS crm_shopify_consent_versions (
 customer_id text PRIMARY KEY, state text NOT NULL, changed_at timestamptz NOT NULL
);
ALTER TABLE crm_shopify_checkouts ENABLE ROW LEVEL SECURITY;
ALTER TABLE crm_shopify_pixel_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE crm_shopify_consent_versions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON crm_shopify_checkouts,crm_shopify_pixel_events,crm_shopify_consent_versions FROM PUBLIC,anon,authenticated;
COMMIT;
