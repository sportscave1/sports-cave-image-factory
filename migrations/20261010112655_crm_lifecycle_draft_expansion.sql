-- Additive draft audience projection. No writes to automations or delivery queues.
CREATE TABLE IF NOT EXISTS crm_lifecycle_customers (
 customer_id text PRIMARY KEY, email text NOT NULL DEFAULT '', recipient_hash text NOT NULL,
 name text NOT NULL DEFAULT '', subscribed_at timestamptz, created_at timestamptz,
 source_updated_at timestamptz NOT NULL, verified_at timestamptz NOT NULL,
 consent text NOT NULL, profile jsonb NOT NULL DEFAULT '{}', source text NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS crm_lifecycle_subscribed ON crm_lifecycle_customers(subscribed_at DESC,customer_id);
CREATE INDEX IF NOT EXISTS crm_lifecycle_email ON crm_lifecycle_customers(email);
CREATE TABLE IF NOT EXISTS crm_lifecycle_staged (
 automation_id uuid NOT NULL REFERENCES crm_automations(id), customer_id text NOT NULL,
 cycle text NOT NULL, revision integer NOT NULL, actor text NOT NULL,
 preview jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(automation_id,customer_id,cycle,revision)
);
ALTER TABLE crm_lifecycle_customers ENABLE ROW LEVEL SECURITY;
ALTER TABLE crm_lifecycle_staged ENABLE ROW LEVEL SECURITY;
CREATE TABLE IF NOT EXISTS crm_lifecycle_revisions (
 automation_id uuid NOT NULL REFERENCES crm_automations(id),revision integer NOT NULL,
 definition jsonb NOT NULL,actor text NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(automation_id,revision)
);
ALTER TABLE crm_lifecycle_revisions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON crm_lifecycle_revisions FROM PUBLIC,anon,authenticated;
REVOKE ALL ON crm_lifecycle_customers,crm_lifecycle_staged FROM PUBLIC,anon,authenticated;
CREATE INDEX IF NOT EXISTS crm_lifecycle_order_customer_date
 ON shopify_orders((COALESCE(NULLIF(shopify_customer_id,''),customer_id)),created_at DESC)
 WHERE upper(financial_status) IN ('PAID','PARTIALLY_REFUNDED') AND cancelled_at IS NULL;
CREATE INDEX IF NOT EXISTS crm_lifecycle_order_event
 ON crm_webhook_events(object_id,topic,occurred_at) WHERE provider='shopify';
