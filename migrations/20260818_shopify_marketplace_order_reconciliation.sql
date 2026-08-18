-- Additive Shopify order ingestion metadata and lookup indexes.
-- Existing orders, line items, allocations, certificates, and edition numbers are untouched.

ALTER TABLE IF EXISTS shopify_orders
    ADD COLUMN IF NOT EXISTS source_name TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS ingestion_status TEXT NOT NULL DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS ingestion_method TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS ingestion_result TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS ingestion_reason TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS ingestion_duration_ms INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS last_ingested_at TIMESTAMPTZ;

ALTER TABLE IF EXISTS shopify_order_lines
    ADD COLUMN IF NOT EXISTS shopify_variant_id TEXT,
    ADD COLUMN IF NOT EXISTS mapping_method TEXT NOT NULL DEFAULT '';

ALTER TABLE IF EXISTS webhook_events
    ADD COLUMN IF NOT EXISTS source_name TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS import_result TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS rejection_reason TEXT NOT NULL DEFAULT '';

-- The existing order-ID, line-item-ID, created/updated-at, and raw SKU indexes
-- already cover reconciliation reads. This expression index is the one missing
-- access path used by the exact, case-insensitive marketplace SKU mapper.
CREATE INDEX IF NOT EXISTS idx_shopify_variants_sku_normalized
    ON shopify_variants(LOWER(BTRIM(sku)))
    WHERE COALESCE(BTRIM(sku), '') <> '';
