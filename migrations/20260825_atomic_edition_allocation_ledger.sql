-- Edition Ops allocation ledger hardening.
--
-- This migration is intentionally fail-closed.  It never deletes, merges, or
-- renumbers existing allocations.  If production contains duplicate source
-- units, duplicate product/edition numbers, or ambiguous product GIDs, the
-- unique indexes below abort the transaction.  Run the read-only reconciliation
-- report and an explicitly approved repair before retrying the migration.

BEGIN;

ALTER TABLE edition_orders
    ADD COLUMN IF NOT EXISTS source_channel TEXT,
    ADD COLUMN IF NOT EXISTS external_order_id TEXT,
    ADD COLUMN IF NOT EXISTS external_line_item_id TEXT,
    ADD COLUMN IF NOT EXISTS unit_ordinal INTEGER,
    ADD COLUMN IF NOT EXISTS shopify_product_gid TEXT,
    ADD COLUMN IF NOT EXISTS allocation_valid BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS invalidated_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS invalidation_reason TEXT NOT NULL DEFAULT '',
    -- Existing rows are not bulk-mirrored by normal order processing. Repairs
    -- explicitly reconcile affected products; newly allocated rows insert
    -- mirror_status='pending'.
    ADD COLUMN IF NOT EXISTS mirror_status TEXT NOT NULL DEFAULT 'synced',
    ADD COLUMN IF NOT EXISTS mirror_attempted_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS mirror_error TEXT NOT NULL DEFAULT '';

UPDATE edition_orders eo
SET source_channel = COALESCE(NULLIF(eo.source_channel, ''), CASE
        WHEN LOWER(BTRIM(COALESCE((
            SELECT so.source_name FROM shopify_orders so
            WHERE so.shopify_order_id = eo.shopify_order_id
            LIMIT 1
        ), ''))) LIKE '%etsy%' THEN 'etsy'
        WHEN LOWER(BTRIM(COALESCE((
            SELECT so.source_name FROM shopify_orders so
            WHERE so.shopify_order_id = eo.shopify_order_id
            LIMIT 1
        ), ''))) LIKE '%ebay%' THEN 'ebay'
        ELSE 'shopify'
    END),
    external_order_id = COALESCE(
        NULLIF(eo.external_order_id, ''),
        CASE
            WHEN eo.shopify_order_id ~ '^gid://shopify/Order/[0-9]+$' THEN eo.shopify_order_id
            WHEN eo.shopify_order_id ~ '^[0-9]+$' THEN 'gid://shopify/Order/' || eo.shopify_order_id
            ELSE NULLIF(eo.shopify_order_id, '')
        END
    ),
    external_line_item_id = COALESCE(
        NULLIF(eo.external_line_item_id, ''),
        CASE
            WHEN eo.shopify_line_item_id ~ '^gid://shopify/LineItem/[0-9]+$' THEN eo.shopify_line_item_id
            WHEN eo.shopify_line_item_id ~ '^[0-9]+$' THEN 'gid://shopify/LineItem/' || eo.shopify_line_item_id
            ELSE NULLIF(eo.shopify_line_item_id, '')
        END
    ),
    unit_ordinal = GREATEST(COALESCE(eo.unit_ordinal, eo.allocation_index, 1), 1),
    shopify_product_gid = COALESCE(
        NULLIF(eo.shopify_product_gid, ''),
        CASE
            WHEN eo.shopify_product_id ~ '^gid://shopify/Product/[0-9]+$' THEN eo.shopify_product_id
            WHEN eo.shopify_product_id ~ '^[0-9]+$' THEN 'gid://shopify/Product/' || eo.shopify_product_id
            ELSE NULL
        END
    );

-- Source-channel/order identities are enriched from the stored order snapshot;
-- product identity remains direct GID/run based and never uses handle or title.
UPDATE edition_orders eo
SET source_channel = COALESCE(NULLIF(eo.source_channel, ''), CASE
        WHEN LOWER(BTRIM(COALESCE(so.source_name, ''))) LIKE '%etsy%' THEN 'etsy'
        WHEN LOWER(BTRIM(COALESCE(so.source_name, ''))) LIKE '%ebay%' THEN 'ebay'
        ELSE 'shopify'
    END),
    external_order_id = COALESCE(
        NULLIF(eo.external_order_id, ''),
        CASE
            WHEN eo.shopify_order_id ~ '^gid://shopify/Order/[0-9]+$' THEN eo.shopify_order_id
            WHEN eo.shopify_order_id ~ '^[0-9]+$' THEN 'gid://shopify/Order/' || eo.shopify_order_id
            ELSE NULLIF(eo.shopify_order_id, '')
        END
    ),
    external_line_item_id = COALESCE(
        NULLIF(eo.external_line_item_id, ''),
        CASE
            WHEN eo.shopify_line_item_id ~ '^gid://shopify/LineItem/[0-9]+$' THEN eo.shopify_line_item_id
            WHEN eo.shopify_line_item_id ~ '^[0-9]+$' THEN 'gid://shopify/LineItem/' || eo.shopify_line_item_id
            ELSE NULLIF(eo.shopify_line_item_id, '')
        END
    ),
    unit_ordinal = GREATEST(COALESCE(eo.unit_ordinal, eo.allocation_index, 1), 1),
    shopify_product_gid = COALESCE(
        NULLIF(eo.shopify_product_gid, ''),
        CASE
            WHEN eo.shopify_product_id ~ '^gid://shopify/Product/[0-9]+$' THEN eo.shopify_product_id
            WHEN eo.shopify_product_id ~ '^[0-9]+$' THEN 'gid://shopify/Product/' || eo.shopify_product_id
            ELSE NULL
        END
    )
FROM shopify_orders so
WHERE so.shopify_order_id = eo.shopify_order_id;

-- Preserve order history across product renames by following the immutable
-- edition-product/run relationship, never the old handle or title.
UPDATE edition_orders eo
SET shopify_product_gid = COALESCE(
        NULLIF(ep.shopify_product_gid, ''),
        CASE
            WHEN ep.shopify_product_id ~ '^gid://shopify/Product/[0-9]+$' THEN ep.shopify_product_id
            WHEN ep.shopify_product_id ~ '^[0-9]+$' THEN 'gid://shopify/Product/' || ep.shopify_product_id
            ELSE NULL
        END
    )
FROM edition_runs er
JOIN edition_products ep ON ep.id = er.edition_product_id
WHERE eo.edition_run_id = er.id
  AND COALESCE(eo.shopify_product_gid, '') = '';

UPDATE edition_orders
SET allocation_key = source_channel || ':' || external_order_id || ':' || external_line_item_id || ':' || unit_ordinal::text
WHERE COALESCE(source_channel, '') <> ''
  AND COALESCE(external_order_id, '') <> ''
  AND COALESCE(external_line_item_id, '') <> ''
  AND unit_ordinal > 0;

ALTER TABLE edition_orders
    ADD CONSTRAINT edition_orders_source_channel_check
        CHECK (source_channel IN ('shopify', 'etsy', 'ebay')),
    ADD CONSTRAINT edition_orders_unit_ordinal_check
        CHECK (unit_ordinal >= 1),
    ADD CONSTRAINT edition_orders_edition_range_check
        CHECK (edition_number >= 1 AND edition_number <= edition_total AND edition_total <= 100);

ALTER TABLE edition_orders
    ALTER COLUMN source_channel SET NOT NULL,
    ALTER COLUMN external_order_id SET NOT NULL,
    ALTER COLUMN external_line_item_id SET NOT NULL,
    ALTER COLUMN unit_ordinal SET NOT NULL,
    ALTER COLUMN shopify_product_gid SET NOT NULL;

UPDATE edition_products ep
SET shopify_product_gid = CASE
        WHEN ep.shopify_product_gid ~ '^gid://shopify/Product/[0-9]+$' THEN ep.shopify_product_gid
        WHEN ep.shopify_product_id ~ '^gid://shopify/Product/[0-9]+$' THEN ep.shopify_product_id
        WHEN ep.shopify_product_id ~ '^[0-9]+$' THEN 'gid://shopify/Product/' || ep.shopify_product_id
        ELSE ep.shopify_product_gid
    END
WHERE COALESCE(ep.shopify_product_gid, '') !~ '^gid://shopify/Product/[0-9]+$';

-- A product rename cannot create a new identity.  This index intentionally
-- fails if existing catalogue rows map one GID to multiple Edition Ops rows.
CREATE UNIQUE INDEX edition_products_shopify_gid_uidx
    ON edition_products ((COALESCE(NULLIF(shopify_product_gid, ''), NULLIF(shopify_product_id, ''))))
    WHERE COALESCE(NULLIF(shopify_product_gid, ''), NULLIF(shopify_product_id, '')) IS NOT NULL;

-- A source unit is immutable and a product edition number is never reusable.
CREATE UNIQUE INDEX edition_orders_source_unit_uidx
    ON edition_orders (source_channel, external_order_id, external_line_item_id, unit_ordinal);

CREATE UNIQUE INDEX edition_orders_product_edition_uidx
    ON edition_orders (shopify_product_gid, edition_number);

CREATE TABLE IF NOT EXISTS edition_marketplace_mappings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_channel TEXT NOT NULL CHECK (source_channel IN ('etsy', 'ebay')),
    identity_type TEXT NOT NULL CHECK (identity_type IN ('listing_id', 'external_variant_id', 'sku')),
    external_identity TEXT NOT NULL,
    shopify_product_gid TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by TEXT NOT NULL DEFAULT 'manual_mapping',
    notes TEXT NOT NULL DEFAULT '',
    UNIQUE (source_channel, identity_type, external_identity)
);

CREATE TABLE IF NOT EXISTS edition_allocation_quarantine (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_channel TEXT NOT NULL,
    external_order_id TEXT NOT NULL,
    external_line_item_id TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    warning TEXT NOT NULL,
    redacted_context JSONB NOT NULL DEFAULT '{}'::jsonb,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    occurrence_count INTEGER NOT NULL DEFAULT 1,
    resolved_at TIMESTAMPTZ,
    resolution_notes TEXT NOT NULL DEFAULT '',
    UNIQUE (source_channel, external_order_id, external_line_item_id, reason_code)
);

CREATE TABLE IF NOT EXISTS edition_repair_audits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repair_key TEXT NOT NULL UNIQUE,
    product_gid TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('dry_run', 'apply', 'rollback')),
    snapshot_sha256 TEXT NOT NULL,
    report JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    applied_at TIMESTAMPTZ,
    rolled_back_at TIMESTAMPTZ,
    actor TEXT NOT NULL DEFAULT 'local_reconciliation_script'
);

CREATE TABLE IF NOT EXISTS edition_repair_archive (
    repair_key TEXT NOT NULL,
    edition_order_id TEXT NOT NULL,
    row_snapshot JSONB NOT NULL,
    archived_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (repair_key, edition_order_id)
);

CREATE TABLE IF NOT EXISTS edition_allocation_tombstones (
    source_channel TEXT NOT NULL,
    external_order_id TEXT NOT NULL,
    external_line_item_id TEXT NOT NULL,
    unit_ordinal INTEGER NOT NULL,
    shopify_product_gid TEXT NOT NULL,
    former_edition_number INTEGER NOT NULL,
    repair_key TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT 'invalid allocation archived',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (source_channel, external_order_id, external_line_item_id, unit_ordinal)
);

UPDATE edition_orders eo
SET mirror_status='pending', mirror_error='Approved database repair is awaiting Shopify mirror.'
WHERE eo.shopify_product_gid IN (
    SELECT era.product_gid
    FROM edition_repair_audits era
    WHERE era.applied_at IS NOT NULL
      AND era.rolled_back_at IS NULL
);

CREATE OR REPLACE FUNCTION enforce_edition_order_ledger_writes()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_atomic TEXT := COALESCE(current_setting('sports_cave.atomic_edition_allocation', TRUE), '');
    v_repair TEXT := COALESCE(current_setting('sports_cave.edition_repair_key', TRUE), '');
BEGIN
    IF TG_OP = 'INSERT' AND v_atomic <> '1' AND v_repair = '' THEN
        RAISE EXCEPTION 'edition_orders inserts must use allocate_edition_line_units_atomic or an approved repair';
    END IF;
    IF TG_OP = 'DELETE' AND v_repair = '' THEN
        RAISE EXCEPTION 'edition_orders rows are immutable outside an approved repair';
    END IF;
    IF TG_OP = 'UPDATE' AND v_repair = '' AND (
        NEW.source_channel IS DISTINCT FROM OLD.source_channel
        OR NEW.external_order_id IS DISTINCT FROM OLD.external_order_id
        OR NEW.external_line_item_id IS DISTINCT FROM OLD.external_line_item_id
        OR NEW.unit_ordinal IS DISTINCT FROM OLD.unit_ordinal
        OR NEW.allocation_index IS DISTINCT FROM OLD.allocation_index
        OR NEW.shopify_product_gid IS DISTINCT FROM OLD.shopify_product_gid
        OR NEW.edition_number IS DISTINCT FROM OLD.edition_number
        OR NEW.edition_total IS DISTINCT FROM OLD.edition_total
    ) THEN
        RAISE EXCEPTION 'Edition source identity, product GID, issued number, and issued total are immutable';
    END IF;
    IF TG_OP = 'UPDATE'
       AND NEW.allocation_valid IS DISTINCT FROM OLD.allocation_valid
       AND v_repair = '' THEN
        RAISE EXCEPTION 'Allocation validity may change only inside an approved repair';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS edition_orders_ledger_write_guard ON edition_orders;
CREATE TRIGGER edition_orders_ledger_write_guard
BEFORE INSERT OR UPDATE OR DELETE ON edition_orders
FOR EACH ROW EXECUTE FUNCTION enforce_edition_order_ledger_writes();

-- Allocate every unit on one order line in one database transaction.  The
-- advisory transaction lock is keyed by permanent Shopify product GID and is
-- used in addition to the product row lock, so simultaneous workers cannot
-- interleave a quantity-two line or consume the same number.
CREATE OR REPLACE FUNCTION allocate_edition_line_units_atomic(
    p_source_channel TEXT,
    p_external_order_id TEXT,
    p_external_line_item_id TEXT,
    p_shopify_product_gid TEXT,
    p_quantity INTEGER,
    p_shopify_order_id TEXT,
    p_shopify_order_name TEXT,
    p_shopify_line_item_id TEXT,
    p_shopify_variant_id TEXT DEFAULT '',
    p_product_title TEXT DEFAULT '',
    p_variant_title TEXT DEFAULT '',
    p_sku TEXT DEFAULT '',
    p_customer_name TEXT DEFAULT '',
    p_customer_email TEXT DEFAULT '',
    p_allocation_status TEXT DEFAULT 'assigned'
)
RETURNS SETOF JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    v_product edition_products%ROWTYPE;
    v_run edition_runs%ROWTYPE;
    v_allocation edition_orders%ROWTYPE;
    v_existing_count INTEGER;
    v_existing_min_ordinal INTEGER;
    v_existing_max_ordinal INTEGER;
    v_existing_product_count INTEGER;
    v_total INTEGER;
    v_next INTEGER;
    v_ordinal INTEGER;
    v_sold INTEGER;
BEGIN
    p_source_channel := LOWER(BTRIM(COALESCE(p_source_channel, '')));
    p_external_order_id := BTRIM(COALESCE(p_external_order_id, ''));
    p_external_line_item_id := BTRIM(COALESCE(p_external_line_item_id, ''));
    p_shopify_product_gid := BTRIM(COALESCE(p_shopify_product_gid, ''));
    p_quantity := COALESCE(p_quantity, 0);

    IF p_source_channel NOT IN ('shopify', 'etsy', 'ebay') THEN
        RAISE EXCEPTION 'Unsupported edition source channel: %', p_source_channel;
    END IF;
    IF p_external_order_id = '' OR p_external_line_item_id = '' THEN
        RAISE EXCEPTION 'Durable external order and line item identities are required';
    END IF;
    IF p_shopify_product_gid !~ '^gid://shopify/Product/[0-9]+$' THEN
        RAISE EXCEPTION 'A canonical Shopify product GID is required';
    END IF;
    IF p_quantity < 1 OR p_quantity > 100 THEN
        RAISE EXCEPTION 'Edition line quantity must be between 1 and 100';
    END IF;

    PERFORM set_config('sports_cave.atomic_edition_allocation', '1', TRUE);

    PERFORM pg_advisory_xact_lock(hashtextextended(p_shopify_product_gid, 0));

    SELECT ep.* INTO STRICT v_product
    FROM edition_products ep
    WHERE COALESCE(NULLIF(ep.shopify_product_gid, ''), NULLIF(ep.shopify_product_id, '')) = p_shopify_product_gid
    ORDER BY ep.updated_at DESC NULLS LAST
    LIMIT 1
    FOR UPDATE;

    SELECT COUNT(*), MIN(eo.unit_ordinal), MAX(eo.unit_ordinal),
           COUNT(*) FILTER (WHERE eo.shopify_product_gid = p_shopify_product_gid)
    INTO v_existing_count, v_existing_min_ordinal, v_existing_max_ordinal, v_existing_product_count
    FROM edition_orders eo
    WHERE eo.source_channel = p_source_channel
      AND eo.external_order_id = p_external_order_id
      AND eo.external_line_item_id = p_external_line_item_id;

    IF EXISTS (
        SELECT 1
        FROM edition_allocation_tombstones tombstone
        WHERE tombstone.source_channel = p_source_channel
          AND tombstone.external_order_id = p_external_order_id
          AND tombstone.external_line_item_id = p_external_line_item_id
    ) THEN
        RAISE EXCEPTION 'Source line was archived by an approved repair and may not be reallocated: %:%:%',
            p_source_channel, p_external_order_id, p_external_line_item_id;
    END IF;

    IF v_existing_count > 0 THEN
        IF v_existing_count <> p_quantity
           OR v_existing_min_ordinal <> 1
           OR v_existing_max_ordinal <> p_quantity THEN
            RAISE EXCEPTION 'Source line quantity/ordinal mismatch for %:%:%; existing %, requested %',
                p_source_channel, p_external_order_id, p_external_line_item_id,
                v_existing_count, p_quantity;
        END IF;
        IF v_existing_product_count <> v_existing_count THEN
            RAISE EXCEPTION 'Source line is already allocated to a different Shopify product GID';
        END IF;
        FOR v_allocation IN
            SELECT eo.*
            FROM edition_orders eo
            WHERE eo.source_channel = p_source_channel
              AND eo.external_order_id = p_external_order_id
              AND eo.external_line_item_id = p_external_line_item_id
            ORDER BY eo.unit_ordinal
        LOOP
            RETURN NEXT jsonb_build_object(
                'allocation', to_jsonb(v_allocation),
                'was_created', FALSE
            );
        END LOOP;
        RETURN;
    END IF;

    SELECT er.* INTO v_run
    FROM edition_runs er
    WHERE er.id = v_product.active_edition_run_id
    FOR UPDATE;

    v_total := LEAST(GREATEST(COALESCE(v_run.edition_total, v_product.edition_total, 100), 1), 100);
    SELECT COUNT(*), COALESCE(MAX(eo.edition_number), 0)
    INTO v_sold, v_next
    FROM edition_orders eo
    WHERE eo.shopify_product_gid = p_shopify_product_gid
      AND eo.allocation_valid;

    IF v_sold <> v_next THEN
        RAISE EXCEPTION 'Edition ledger sequence is not contiguous for %; valid rows %, highest %. Repair is required before allocation',
            p_shopify_product_gid, v_sold, v_next;
    END IF;
    v_next := v_next + 1;

    IF v_next + (p_quantity - v_existing_count) - 1 > v_total THEN
        RAISE EXCEPTION 'Edition limit reached for %: next %, requested %, total %',
            p_shopify_product_gid, v_next, p_quantity - v_existing_count, v_total;
    END IF;

    FOR v_ordinal IN 1..p_quantity LOOP
        SELECT eo.* INTO v_allocation
        FROM edition_orders eo
        WHERE eo.source_channel = p_source_channel
          AND eo.external_order_id = p_external_order_id
          AND eo.external_line_item_id = p_external_line_item_id
          AND eo.unit_ordinal = v_ordinal;

        IF FOUND THEN
            RETURN NEXT jsonb_build_object(
                'allocation', to_jsonb(v_allocation),
                'was_created', FALSE
            );
            CONTINUE;
        END IF;

        INSERT INTO edition_orders (
            source_channel, external_order_id, external_line_item_id, unit_ordinal,
            allocation_key, shopify_product_gid,
            shopify_order_id, shopify_order_name, shopify_line_item_id,
            shopify_product_id, shopify_variant_id, shopify_handle,
            product_title, edition_run_id, edition_name, variant_title, sku,
            customer_name, customer_email, shopify_customer_name, shopify_customer_email,
            edition_number, edition_total, allocation_index, quantity,
            assigned_at, certificate_status, status, source, mirror_status, updated_at
        ) VALUES (
            p_source_channel, p_external_order_id, p_external_line_item_id, v_ordinal,
            p_source_channel || ':' || p_external_order_id || ':' || p_external_line_item_id || ':' || v_ordinal::text,
            p_shopify_product_gid,
            p_shopify_order_id, p_shopify_order_name, p_shopify_line_item_id,
            p_shopify_product_gid, p_shopify_variant_id, v_product.shopify_handle,
            COALESCE(NULLIF(p_product_title, ''), v_product.product_title), v_run.id,
            COALESCE(NULLIF(v_run.edition_name, ''), 'Original Edition'), p_variant_title, p_sku,
            p_customer_name, p_customer_email, p_customer_name, p_customer_email,
            v_next, v_total, v_ordinal, p_quantity,
            now(), 'Certificate Missing', p_allocation_status,
            p_source_channel || '_atomic_ledger', 'pending', now()
        )
        RETURNING * INTO v_allocation;

        RETURN NEXT jsonb_build_object(
            'allocation', to_jsonb(v_allocation),
            'was_created', TRUE
        );
        v_next := v_next + 1;
    END LOOP;

    SELECT COUNT(*), COALESCE(MAX(eo.edition_number), 0)
    INTO v_sold, v_next
    FROM edition_orders eo
    WHERE eo.shopify_product_gid = p_shopify_product_gid
      AND eo.allocation_valid;

    UPDATE edition_products
    SET next_edition_number = v_next + 1,
        last_assigned_edition = v_next,
        sold_count = v_sold,
        remaining_count = GREATEST(v_total - v_sold, 0),
        sold_out = v_next >= v_total,
        is_sold_out = v_next >= v_total,
        updated_at = now()
    WHERE id = v_product.id;

    IF v_run.id IS NOT NULL THEN
        UPDATE edition_runs
        SET next_edition_number = v_next + 1,
            status = CASE WHEN v_next >= v_total THEN 'sold_out' ELSE 'active' END,
            updated_at = now()
        WHERE id = v_run.id;
    END IF;

    RETURN;
END;
$$;

COMMIT;
