-- Private read projection: no tokens/addresses, no historical enrollment.
ALTER TABLE crm_shopify_checkouts ADD COLUMN IF NOT EXISTS analytics jsonb NOT NULL DEFAULT '{}';
CREATE INDEX IF NOT EXISTS crm_checkout_created ON crm_shopify_checkouts(created_at DESC,checkout_key);
-- Existing checkout/flow, send(enrollment_id,step_index) and delivery(send_id)
-- indexes already cover the bulk joins. Keep existing RLS and grants unchanged.
