-- Generic correction for sparse pre-cutover rows attached to active edition runs.
-- Installing this function does not allocate editions or alter product counters.

BEGIN;

-- Legacy rows remain replay-blocking and run-number unique. Only rows written
-- by the atomic allocator (identity_enforced=TRUE) form the strict suffix.
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
    v_ledger_count INTEGER;
    v_ledger_min INTEGER;
    v_ledger_max INTEGER;
    v_baseline INTEGER;
    v_expected_baseline INTEGER;
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

    IF v_run.id IS NULL THEN
        RAISE EXCEPTION 'Edition product % has no active edition run', p_shopify_product_gid;
    END IF;

    v_total := LEAST(GREATEST(COALESCE(v_run.edition_total, v_product.edition_total, 100), 1), 100);
    SELECT COUNT(*), COALESCE(MIN(eo.edition_number), 0), COALESCE(MAX(eo.edition_number), 0)
    INTO v_ledger_count, v_ledger_min, v_ledger_max
    FROM edition_orders eo
    WHERE eo.edition_run_id = v_run.id
      AND eo.identity_enforced
      AND eo.allocation_valid
      AND COALESCE(eo.status, '') NOT IN ('voided', 'refunded', 'cancelled', 'superseded');

    -- The product counter existed before the durable atomic ledger. Deriving
    -- the opening floor from the locked product counter and the enforced rows
    -- is safe only when those enforced rows are a contiguous suffix ending at
    -- the currently issued number. Sparse legacy rows are intentionally absent.
    v_expected_baseline := COALESCE(v_product.sold_count, 0) - v_ledger_count;
    IF v_expected_baseline < 0
       OR (v_ledger_count > 0 AND (
            v_ledger_min <> v_expected_baseline + 1
            OR v_ledger_max <> COALESCE(v_product.sold_count, 0)
            OR v_ledger_max - v_ledger_min + 1 <> v_ledger_count
       ))
       OR COALESCE(v_product.sold_count, 0) <> COALESCE(v_product.last_assigned_edition, 0)
       OR COALESCE(v_product.next_edition_number, 1) <> COALESCE(v_product.sold_count, 0) + 1
       OR COALESCE(v_run.next_edition_number, 1) <> COALESCE(v_product.sold_count, 0) + 1 THEN
        RAISE EXCEPTION 'Atomic edition suffix is not contiguous for %; enforced rows %, min %, max %, product sold %, next %. Repair is required before allocation',
            p_shopify_product_gid, v_ledger_count, v_ledger_min, v_ledger_max,
            v_product.sold_count, v_product.next_edition_number;
    END IF;

    IF COALESCE(v_run.allocation_baseline_sold_count, 0) <> v_expected_baseline THEN
        UPDATE edition_runs
        SET allocation_baseline_sold_count = v_expected_baseline,
            allocation_baseline_recorded_at = now(),
            allocation_baseline_reason = 'Corrected from locked sold count minus identity-enforced atomic rows',
            updated_at = now()
        WHERE id = v_run.id;
    END IF;
    v_baseline := v_expected_baseline;
    v_sold := v_baseline + v_ledger_count;
    v_next := v_sold + 1;

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
            source_channel, external_order_id, external_line_item_id, unit_ordinal, identity_enforced,
            allocation_key, shopify_product_gid,
            shopify_order_id, shopify_order_name, shopify_line_item_id,
            shopify_product_id, shopify_variant_id, shopify_handle,
            product_title, edition_run_id, edition_name, variant_title, sku,
            customer_name, customer_email, shopify_customer_name, shopify_customer_email,
            edition_number, edition_total, allocation_index, quantity,
            assigned_at, certificate_status, status, source, mirror_status, updated_at
        ) VALUES (
            p_source_channel, p_external_order_id, p_external_line_item_id, v_ordinal, TRUE,
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

    SELECT v_baseline + COUNT(*), COALESCE(MAX(eo.edition_number), v_baseline)
    INTO v_sold, v_next
    FROM edition_orders eo
    WHERE eo.edition_run_id = v_run.id
      AND eo.identity_enforced
      AND eo.allocation_valid
      AND COALESCE(eo.status, '') NOT IN ('voided', 'refunded', 'cancelled', 'superseded');

    IF v_sold <> v_next THEN
        RAISE EXCEPTION 'Atomic allocation produced a non-contiguous enforced suffix for %; sold %, highest %',
            p_shopify_product_gid, v_sold, v_next;
    END IF;

    UPDATE edition_products
    SET next_edition_number = v_next + 1,
        last_assigned_edition = v_next,
        sold_count = v_sold,
        remaining_count = GREATEST(v_total - v_sold, 0),
        sold_out = v_next >= v_total,
        is_sold_out = v_next >= v_total,
        updated_at = now()
    WHERE id = v_product.id;

    UPDATE edition_runs
    SET next_edition_number = v_next + 1,
        status = CASE WHEN v_next >= v_total THEN 'sold_out' ELSE 'active' END,
        updated_at = now()
    WHERE id = v_run.id;

    RETURN;
END;
$$;

COMMIT;
