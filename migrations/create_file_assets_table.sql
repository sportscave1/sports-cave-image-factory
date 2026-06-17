CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS file_assets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_type text NOT NULL,
    bucket text NOT NULL,
    object_key text NOT NULL,
    filename text,
    mime_type text,
    size_bytes bigint,
    related_shopify_product_id text,
    related_shopify_order_id text,
    related_shopify_handle text,
    related_edition_order_id uuid NULL,
    source text DEFAULT 'r2',
    status text DEFAULT 'active',
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now(),
    UNIQUE (bucket, object_key)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_file_assets_bucket_key_unique
    ON file_assets(bucket, object_key);

CREATE INDEX IF NOT EXISTS idx_file_assets_handle
    ON file_assets(related_shopify_handle);

CREATE INDEX IF NOT EXISTS idx_file_assets_order
    ON file_assets(related_shopify_order_id);

ALTER TABLE edition_orders
    ADD COLUMN IF NOT EXISTS certificate_r2_bucket text,
    ADD COLUMN IF NOT EXISTS certificate_r2_key text,
    ADD COLUMN IF NOT EXISTS certificate_preview_r2_bucket text,
    ADD COLUMN IF NOT EXISTS certificate_preview_r2_key text;

ALTER TABLE certificates
    ADD COLUMN IF NOT EXISTS certificate_r2_bucket text,
    ADD COLUMN IF NOT EXISTS certificate_r2_key text,
    ADD COLUMN IF NOT EXISTS certificate_preview_r2_bucket text,
    ADD COLUMN IF NOT EXISTS certificate_preview_r2_key text;
