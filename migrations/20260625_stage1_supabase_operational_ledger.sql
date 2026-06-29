CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS edition_products (
    id BIGSERIAL PRIMARY KEY,
    shopify_product_id TEXT,
    shopify_product_gid TEXT,
    shopify_handle TEXT UNIQUE,
    product_title TEXT,
    edition_total INTEGER DEFAULT 100,
    next_edition_number INTEGER DEFAULT 1,
    last_assigned_edition INTEGER DEFAULT 0,
    sold_count INTEGER DEFAULT 0,
    remaining_count INTEGER DEFAULT 100,
    edition_status TEXT DEFAULT 'limited_release',
    edition_display_text TEXT,
    active_edition_run_id UUID,
    edition_name TEXT DEFAULT 'Original Edition',
    allow_counter_history_override BOOLEAN DEFAULT FALSE,
    active BOOLEAN DEFAULT TRUE,
    is_active BOOLEAN DEFAULT TRUE,
    sold_out BOOLEAN DEFAULT FALSE,
    is_sold_out BOOLEAN DEFAULT FALSE,
    metafields_synced_at TIMESTAMPTZ,
    metafields_sync_status TEXT DEFAULT 'Never Synced',
    last_metafield_error TEXT,
    raw JSONB DEFAULT '{}'::jsonb,
    synced_at TIMESTAMPTZ DEFAULT now(),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS shopify_orders (
    shopify_order_id TEXT PRIMARY KEY,
    legacy_resource_id TEXT,
    order_name TEXT,
    shopify_order_name TEXT,
    order_number TEXT,
    shopify_order_number TEXT,
    admin_url TEXT,
    customer_id TEXT,
    shopify_customer_id TEXT,
    customer_name TEXT,
    customer_email TEXT,
    email TEXT,
    financial_status TEXT,
    fulfillment_status TEXT,
    total_price TEXT,
    currency TEXT,
    created_at TIMESTAMPTZ,
    remote_updated_at TIMESTAMPTZ,
    processed_at TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ,
    raw_json JSONB DEFAULT '{}'::jsonb,
    raw JSONB DEFAULT '{}'::jsonb,
    synced_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS shopify_order_lines (
    id BIGSERIAL PRIMARY KEY,
    shopify_line_item_id TEXT UNIQUE,
    shopify_order_id TEXT,
    shopify_product_id TEXT,
    shopify_handle TEXT,
    product_title TEXT,
    variant_title TEXT,
    sku TEXT,
    quantity INTEGER DEFAULT 1,
    assignment_status TEXT DEFAULT 'Needs Edition',
    last_error TEXT DEFAULT '',
    raw_json JSONB DEFAULT '{}'::jsonb,
    synced_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS edition_orders (
    id BIGSERIAL PRIMARY KEY,
    shopify_customer_id TEXT,
    shopify_order_id TEXT,
    shopify_order_name TEXT,
    shopify_line_item_id TEXT,
    shopify_product_id TEXT,
    shopify_variant_id TEXT,
    shopify_handle TEXT,
    product_handle TEXT,
    product_title TEXT,
    variant_title TEXT,
    sku TEXT,
    customer_name TEXT,
    customer_email TEXT,
    shopify_customer_name TEXT,
    shopify_customer_email TEXT,
    edition_run_id UUID,
    edition_name TEXT,
    edition_number INTEGER,
    edition_total INTEGER,
    edition_display TEXT,
    allocation_key TEXT,
    allocation_index INTEGER DEFAULT 1,
    quantity INTEGER DEFAULT 1,
    assigned_at TIMESTAMPTZ DEFAULT now(),
    certificate_status TEXT DEFAULT 'Certificate Missing',
    certificate_id TEXT,
    shopify_file_id TEXT,
    shopify_file_status TEXT,
    certificate_file_url TEXT,
    purchase_date TIMESTAMPTZ,
    source TEXT DEFAULT 'sports_cave_os',
    status TEXT DEFAULT 'assigned',
    manual_override BOOLEAN DEFAULT FALSE,
    override_old_edition_number INTEGER,
    override_new_edition_number INTEGER,
    override_timestamp TIMESTAMPTZ,
    override_reason TEXT,
    certificate_r2_bucket TEXT,
    certificate_r2_key TEXT,
    certificate_preview_r2_bucket TEXT,
    certificate_preview_r2_key TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (shopify_line_item_id, allocation_index)
);

CREATE TABLE IF NOT EXISTS certificates (
    id BIGSERIAL PRIMARY KEY,
    edition_order_id TEXT UNIQUE,
    related_edition_order_id UUID NULL,
    shopify_customer_id TEXT,
    customer_email TEXT,
    customer_name TEXT,
    shopify_order_id TEXT,
    shopify_order_name TEXT,
    shopify_line_item_id TEXT,
    shopify_handle TEXT,
    product_handle TEXT,
    shopify_product_id TEXT,
    shopify_variant_id TEXT,
    product_title TEXT,
    variant_title TEXT,
    certificate_id TEXT,
    edition_number INTEGER,
    edition_total INTEGER,
    edition_limit INTEGER,
    edition_display TEXT,
    display_edition TEXT,
    line_item_unit_index INTEGER DEFAULT 1,
    pdf_filename TEXT,
    local_file_path TEXT,
    shopify_file_id TEXT,
    shopify_file_status TEXT,
    shopify_file_url TEXT,
    certificate_file_url TEXT,
    certificate_pdf_url TEXT,
    certificate_print_jpg_url TEXT,
    certificate_preview_image_url TEXT,
    shopify_pdf_file_id TEXT,
    shopify_print_jpg_file_id TEXT,
    shopify_preview_file_id TEXT,
    asset_sync_status TEXT DEFAULT 'pending',
    asset_sync_error TEXT,
    certificate_shopify_file_id TEXT,
    certificate_status TEXT DEFAULT 'Processing',
    order_metafields_synced_at TIMESTAMPTZ,
    order_metafields_sync_status TEXT DEFAULT 'Never Synced',
    order_metafields_error TEXT,
    sync_status TEXT DEFAULT 'pending',
    last_sync_error TEXT,
    purchase_date TIMESTAMPTZ,
    source TEXT DEFAULT 'sports_cave_os',
    status TEXT DEFAULT 'Local PDF',
    generated_at TIMESTAMPTZ DEFAULT now(),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app_sync_state (
    key TEXT PRIMARY KEY,
    value JSONB DEFAULT '{}'::jsonb,
    cursor_value TEXT,
    last_success_at TIMESTAMPTZ,
    last_attempt_at TIMESTAMPTZ,
    status TEXT DEFAULT 'idle',
    error_message TEXT,
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGSERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    entity_type TEXT,
    entity_id TEXT,
    shopify_order_id TEXT,
    shopify_line_item_id TEXT,
    shopify_handle TEXT,
    old_value JSONB DEFAULT '{}'::jsonb,
    new_value JSONB DEFAULT '{}'::jsonb,
    reason TEXT,
    actor TEXT DEFAULT 'sports_cave_os',
    source TEXT DEFAULT 'sports_cave_os',
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE IF EXISTS edition_products ADD COLUMN IF NOT EXISTS shopify_product_gid TEXT;
ALTER TABLE IF EXISTS edition_products ADD COLUMN IF NOT EXISTS last_assigned_edition INTEGER DEFAULT 0;
ALTER TABLE IF EXISTS edition_products ADD COLUMN IF NOT EXISTS active_edition_run_id UUID;
ALTER TABLE IF EXISTS edition_products ADD COLUMN IF NOT EXISTS edition_name TEXT DEFAULT 'Original Edition';
ALTER TABLE IF EXISTS edition_products ADD COLUMN IF NOT EXISTS allow_counter_history_override BOOLEAN DEFAULT FALSE;

ALTER TABLE IF EXISTS edition_orders ADD COLUMN IF NOT EXISTS edition_run_id UUID;
ALTER TABLE IF EXISTS edition_orders ADD COLUMN IF NOT EXISTS edition_name TEXT;
ALTER TABLE IF EXISTS edition_orders ADD COLUMN IF NOT EXISTS allocation_key TEXT;
ALTER TABLE IF EXISTS edition_orders ADD COLUMN IF NOT EXISTS quantity INTEGER DEFAULT 1;
ALTER TABLE IF EXISTS edition_orders ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'assigned';
ALTER TABLE IF EXISTS edition_orders ADD COLUMN IF NOT EXISTS manual_override BOOLEAN DEFAULT FALSE;
ALTER TABLE IF EXISTS edition_orders ADD COLUMN IF NOT EXISTS override_old_edition_number INTEGER;
ALTER TABLE IF EXISTS edition_orders ADD COLUMN IF NOT EXISTS override_new_edition_number INTEGER;
ALTER TABLE IF EXISTS edition_orders ADD COLUMN IF NOT EXISTS override_timestamp TIMESTAMPTZ;
ALTER TABLE IF EXISTS edition_orders ADD COLUMN IF NOT EXISTS override_reason TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_edition_products_handle_unique
    ON edition_products(shopify_handle)
    WHERE shopify_handle IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_shopify_orders_id_unique
    ON shopify_orders(shopify_order_id)
    WHERE shopify_order_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_shopify_order_lines_line_id_unique
    ON shopify_order_lines(shopify_line_item_id)
    WHERE shopify_line_item_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_edition_orders_line_allocation_unique
    ON edition_orders(shopify_line_item_id, allocation_index)
    WHERE shopify_line_item_id IS NOT NULL AND allocation_index IS NOT NULL;

UPDATE edition_orders
SET allocation_key =
    COALESCE(NULLIF(regexp_replace(shopify_order_id, '^gid://shopify/[^/]+/', '', 'i'), ''), shopify_order_id)
    || ':' ||
    COALESCE(NULLIF(regexp_replace(shopify_line_item_id, '^gid://shopify/[^/]+/', '', 'i'), ''), shopify_line_item_id)
    || ':' ||
    GREATEST(COALESCE(allocation_index, 1), 1)::text
WHERE COALESCE(allocation_key, '') = ''
  AND COALESCE(shopify_order_id, '') <> ''
  AND COALESCE(shopify_line_item_id, '') <> '';

CREATE INDEX IF NOT EXISTS idx_edition_orders_allocation_key
    ON edition_orders(allocation_key)
    WHERE COALESCE(allocation_key, '') <> '';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_indexes
        WHERE schemaname = 'public'
          AND indexname = 'idx_edition_orders_allocation_key_unique'
    ) AND NOT EXISTS (
        SELECT 1
        FROM edition_orders
        WHERE COALESCE(allocation_key, '') <> ''
        GROUP BY allocation_key
        HAVING COUNT(*) > 1
    ) THEN
        CREATE UNIQUE INDEX idx_edition_orders_allocation_key_unique
            ON edition_orders(allocation_key)
            WHERE COALESCE(allocation_key, '') <> '';
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_indexes
        WHERE schemaname = 'public'
          AND indexname = 'idx_edition_orders_run_number_active_unique'
    ) AND NOT EXISTS (
        SELECT 1
        FROM edition_orders
        WHERE edition_run_id IS NOT NULL
          AND edition_number IS NOT NULL
          AND COALESCE(status, '') NOT IN ('voided', 'refunded', 'cancelled')
        GROUP BY edition_run_id, edition_number
        HAVING COUNT(*) > 1
    ) THEN
        CREATE UNIQUE INDEX idx_edition_orders_run_number_active_unique
            ON edition_orders(edition_run_id, edition_number)
            WHERE edition_run_id IS NOT NULL
              AND edition_number IS NOT NULL
              AND COALESCE(status, '') NOT IN ('voided', 'refunded', 'cancelled');
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_indexes
        WHERE schemaname = 'public'
          AND indexname = 'idx_edition_orders_handle_number_unrun_unique'
    ) AND NOT EXISTS (
        SELECT 1
        FROM edition_orders
        WHERE edition_run_id IS NULL
          AND shopify_handle IS NOT NULL
          AND edition_number IS NOT NULL
          AND COALESCE(status, '') NOT IN ('voided', 'refunded', 'cancelled')
        GROUP BY shopify_handle, edition_number
        HAVING COUNT(*) > 1
    ) THEN
        CREATE UNIQUE INDEX idx_edition_orders_handle_number_unrun_unique
            ON edition_orders(shopify_handle, edition_number)
            WHERE edition_run_id IS NULL
              AND shopify_handle IS NOT NULL
              AND edition_number IS NOT NULL
              AND COALESCE(status, '') NOT IN ('voided', 'refunded', 'cancelled');
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_shopify_orders_created_at
    ON shopify_orders(created_at ASC NULLS LAST, processed_at ASC NULLS LAST, order_number ASC NULLS LAST);

CREATE INDEX IF NOT EXISTS idx_shopify_orders_updated_at
    ON shopify_orders(remote_updated_at DESC NULLS LAST);

CREATE INDEX IF NOT EXISTS idx_shopify_order_lines_order_id
    ON shopify_order_lines(shopify_order_id);

CREATE INDEX IF NOT EXISTS idx_shopify_order_lines_handle
    ON shopify_order_lines(shopify_handle);

CREATE INDEX IF NOT EXISTS idx_edition_orders_order_id
    ON edition_orders(shopify_order_id);

CREATE INDEX IF NOT EXISTS idx_edition_orders_handle
    ON edition_orders(shopify_handle);

CREATE INDEX IF NOT EXISTS idx_edition_orders_edition_number
    ON edition_orders(edition_number);

CREATE INDEX IF NOT EXISTS idx_edition_orders_assigned_at
    ON edition_orders(assigned_at DESC NULLS LAST);

CREATE INDEX IF NOT EXISTS idx_certificates_edition_order
    ON certificates(edition_order_id);

CREATE INDEX IF NOT EXISTS idx_certificates_related_edition_order
    ON certificates(related_edition_order_id);

CREATE INDEX IF NOT EXISTS idx_certificates_shopify_order_id
    ON certificates(shopify_order_id);

CREATE INDEX IF NOT EXISTS idx_certificates_line_unit
    ON certificates(shopify_line_item_id, line_item_unit_index);

CREATE UNIQUE INDEX IF NOT EXISTS idx_app_sync_state_key_unique
    ON app_sync_state(key);

CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at
    ON audit_logs(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_audit_logs_entity
    ON audit_logs(entity_type, entity_id);

CREATE INDEX IF NOT EXISTS idx_audit_logs_order_line
    ON audit_logs(shopify_order_id, shopify_line_item_id);

CREATE INDEX IF NOT EXISTS idx_audit_logs_handle
    ON audit_logs(shopify_handle);
