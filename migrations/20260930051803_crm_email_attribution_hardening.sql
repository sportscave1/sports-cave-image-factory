BEGIN;
-- Pending Shopify journeys use the existing one-row-per-order attribution ledger.
ALTER TABLE crm_order_attribution ALTER COLUMN campaign_id DROP NOT NULL;
ALTER TABLE crm_order_attribution ALTER COLUMN campaign_key DROP NOT NULL;
ALTER TABLE crm_order_attribution ALTER COLUMN order_created_at DROP NOT NULL;
ALTER TABLE crm_order_attribution ALTER COLUMN visit_at DROP NOT NULL;
ALTER TABLE crm_order_attribution ALTER COLUMN amount DROP NOT NULL;
ALTER TABLE crm_order_attribution ALTER COLUMN currency DROP NOT NULL;
ALTER TABLE crm_order_attribution ALTER COLUMN eligible SET DEFAULT false;
ALTER TABLE crm_order_attribution ADD COLUMN attribution_status text NOT NULL DEFAULT 'UNCHECKED';
ALTER TABLE crm_order_attribution ADD COLUMN evidence jsonb NOT NULL DEFAULT '{}';
ALTER TABLE crm_order_attribution ADD COLUMN gross_revenue numeric(18,2);
ALTER TABLE crm_order_attribution ADD COLUMN refund_amount numeric(18,2);
ALTER TABLE crm_order_attribution ADD COLUMN retry_at timestamptz;
ALTER TABLE crm_order_attribution ADD COLUMN attempts integer NOT NULL DEFAULT 0;
ALTER TABLE crm_order_attribution ADD COLUMN mirror_error text;
ALTER TABLE crm_order_attribution ADD COLUMN created_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE crm_order_attribution ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now();
UPDATE crm_order_attribution SET attribution_status='ATTRIBUTED' WHERE method IS NOT NULL;
UPDATE crm_order_attribution SET mirror_status=CASE mirror_status WHEN 'SYNCED' THEN 'UPDATED'
 WHEN 'UNAVAILABLE' THEN 'FAILED' ELSE 'PENDING' END;
CREATE INDEX crm_attribution_retry ON crm_order_attribution(retry_at) WHERE retry_at IS NOT NULL;
-- Existing RLS/revoked browser roles remain unchanged; no new exposed table.
COMMIT;
