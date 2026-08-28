-- Admin-only display/certificate values for genuinely blocked expired editions.
--
-- These rows are deliberately outside edition_orders. They are not allocations,
-- never reserve an edition, and never participate in counters or uniqueness for
-- normal allocation. The insert trigger repeats every eligibility guard inside
-- the database transaction so a UI label alone can never authorize an override.

BEGIN;

CREATE TABLE IF NOT EXISTS manual_order_line_editions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_channel TEXT NOT NULL
        CHECK (source_channel IN ('shopify', 'etsy', 'ebay')),
    external_order_id TEXT NOT NULL CHECK (BTRIM(external_order_id) <> ''),
    external_line_item_id TEXT NOT NULL CHECK (BTRIM(external_line_item_id) <> ''),
    canonical_product_gid TEXT NOT NULL
        CHECK (canonical_product_gid ~ '^gid://shopify/Product/[0-9]+$'),
    edition_number INTEGER NOT NULL CHECK (edition_number > 0),
    edition_total INTEGER NOT NULL CHECK (edition_total > 0 AND edition_total <= 100),
    reason TEXT NOT NULL CHECK (BTRIM(reason) <> ''),
    created_by_user_id UUID NOT NULL REFERENCES os_users(id) ON DELETE RESTRICT,
    created_by_email TEXT NOT NULL,
    created_by_display_name TEXT NOT NULL,
    verified_order_name TEXT NOT NULL,
    verified_product_title TEXT NOT NULL,
    verified_assignment_status TEXT NOT NULL,
    verified_last_error TEXT NOT NULL,
    verified_series_status TEXT NOT NULL,
    verified_sold_count INTEGER NOT NULL,
    verified_remaining_count INTEGER NOT NULL,
    verified_next_edition_number INTEGER NOT NULL,
    verified_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (edition_number <= edition_total),
    UNIQUE (source_channel, external_order_id, external_line_item_id)
);

CREATE INDEX IF NOT EXISTS idx_manual_order_line_editions_line_item
    ON manual_order_line_editions(external_line_item_id);

-- This table is an internal backend capability, not a Supabase Data API surface.
REVOKE ALL ON TABLE manual_order_line_editions FROM PUBLIC;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
        EXECUTE 'REVOKE ALL ON TABLE manual_order_line_editions FROM anon';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
        EXECUTE 'REVOKE ALL ON TABLE manual_order_line_editions FROM authenticated';
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION enforce_manual_order_line_edition_insert()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_actor os_users%ROWTYPE;
    v_order shopify_orders%ROWTYPE;
    v_line shopify_order_lines%ROWTYPE;
    v_product edition_products%ROWTYPE;
    v_run edition_runs%ROWTYPE;
    v_product_count INTEGER;
    v_source_channel TEXT;
    v_product_gid TEXT;
    v_total INTEGER;
    v_series_status TEXT;
    v_failure_text TEXT;
    v_fulfilment_status TEXT;
    v_line_fulfilment_status TEXT;
BEGIN
    SELECT * INTO v_actor
    FROM os_users
    WHERE id=NEW.created_by_user_id
      AND role='admin'
      AND is_active IS TRUE
      AND COALESCE(account_status, 'active') <> 'removed'
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Only an active administrator may save a manual edition value';
    END IF;

    SELECT * INTO v_order
    FROM shopify_orders
    WHERE shopify_order_id=NEW.external_order_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Immutable order identity was not found';
    END IF;

    SELECT * INTO v_line
    FROM shopify_order_lines
    WHERE shopify_order_id=NEW.external_order_id
      AND shopify_line_item_id=NEW.external_line_item_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Immutable order-line identity was not found on the expected order';
    END IF;

    v_source_channel := CASE
        WHEN LOWER(BTRIM(COALESCE(NULLIF(to_jsonb(v_order)->>'source_name', ''), v_order.raw_json->>'source_name', ''))) LIKE '%etsy%' THEN 'etsy'
        WHEN LOWER(BTRIM(COALESCE(NULLIF(to_jsonb(v_order)->>'source_name', ''), v_order.raw_json->>'source_name', ''))) LIKE '%ebay%' THEN 'ebay'
        ELSE 'shopify'
    END;
    IF NEW.source_channel <> v_source_channel THEN
        RAISE EXCEPTION 'Source channel does not match the immutable order';
    END IF;

    v_product_gid := CASE
        WHEN COALESCE(v_line.shopify_product_id, '') ~ '^gid://shopify/Product/[0-9]+$'
            THEN v_line.shopify_product_id
        WHEN COALESCE(v_line.shopify_product_id, '') ~ '^[0-9]+$'
            THEN 'gid://shopify/Product/' || v_line.shopify_product_id
        ELSE ''
    END;
    IF v_product_gid = '' OR NEW.canonical_product_gid <> v_product_gid THEN
        RAISE EXCEPTION 'Canonical product identity does not match the immutable order line';
    END IF;

    -- Serialize against the normal atomic allocator for this canonical design.
    PERFORM pg_advisory_xact_lock(hashtextextended(v_product_gid, 0));

    SELECT COUNT(*) INTO v_product_count
    FROM edition_products
    WHERE COALESCE(NULLIF(shopify_product_gid, ''), NULLIF(shopify_product_id, ''))=v_product_gid;
    IF v_product_count <> 1 THEN
        RAISE EXCEPTION 'Canonical edition design identity is missing or ambiguous';
    END IF;

    SELECT * INTO v_product
    FROM edition_products
    WHERE COALESCE(NULLIF(shopify_product_gid, ''), NULLIF(shopify_product_id, ''))=v_product_gid
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Canonical edition design was not found';
    END IF;

    SELECT * INTO v_run
    FROM edition_runs
    WHERE id=v_product.active_edition_run_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Canonical edition run was not found';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM edition_orders eo
        WHERE COALESCE(eo.allocation_valid, TRUE)
          AND eo.edition_number BETWEEN 1 AND eo.edition_total
          AND (
              (eo.source_channel=NEW.source_channel
               AND eo.external_order_id=NEW.external_order_id
               AND eo.external_line_item_id=NEW.external_line_item_id)
              OR eo.shopify_line_item_id=NEW.external_line_item_id
          )
    ) THEN
        RAISE EXCEPTION 'A valid normal allocation already exists for this order line';
    END IF;

    v_fulfilment_status := LOWER(BTRIM(COALESCE(
        NULLIF(v_order.fulfillment_status, ''),
        NULLIF(v_order.raw_json->>'fulfillment_status', ''),
        NULLIF(v_order.raw_json->>'displayFulfillmentStatus', ''),
        ''
    )));
    v_line_fulfilment_status := LOWER(BTRIM(COALESCE(
        NULLIF(to_jsonb(v_line)->>'fulfillment_status', ''),
        NULLIF(v_line.raw_json->>'fulfillment_status', ''),
        NULLIF(v_line.raw_json->>'displayFulfillmentStatus', ''),
        ''
    )));
    IF v_fulfilment_status IN ('fulfilled', 'complete', 'completed')
       OR v_line_fulfilment_status IN ('fulfilled', 'complete', 'completed')
       OR EXISTS (
           SELECT 1
           FROM prodigi_dispatch_rows dispatch
           WHERE dispatch.shopify_line_item_id=NEW.external_line_item_id
             AND LOWER(BTRIM(COALESCE(dispatch.prodigi_status, ''))) IN
                 ('complete', 'completed', 'fulfilled', 'fulfilled in shopify')
       ) THEN
        RAISE EXCEPTION 'Fulfilled order lines cannot receive a manual edition value';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM certificates certificate
        WHERE certificate.shopify_order_id=NEW.external_order_id
          AND certificate.shopify_line_item_id=NEW.external_line_item_id
    ) THEN
        RAISE EXCEPTION 'A certificate already exists for this order line';
    END IF;

    v_total := LEAST(GREATEST(COALESCE(v_run.edition_total, v_product.edition_total, 100), 1), 100);
    IF NEW.edition_total <> v_total THEN
        RAISE EXCEPTION 'Manual edition total must match the canonical edition total';
    END IF;

    v_series_status := LOWER(BTRIM(
        COALESCE(v_run.status, '') || ' ' || COALESCE(v_product.edition_status, '')
    ));
    IF NOT (
        COALESCE(v_product.sold_out, FALSE)
        OR COALESCE(v_product.is_sold_out, FALSE)
        OR NOT COALESCE(v_product.active, v_product.is_active, TRUE)
        OR v_series_status ~ '(^| )(sold_out|sold out|expired|disabled|archived|inactive)( |$)'
        OR COALESCE(v_product.sold_count, 0) >= v_total
        OR COALESCE(v_product.remaining_count, v_total) <= 0
        OR COALESCE(v_product.next_edition_number, 1) > v_total
    ) THEN
        RAISE EXCEPTION 'The canonical edition design is still available for normal allocation';
    END IF;

    v_failure_text := LOWER(BTRIM(
        COALESCE(v_line.assignment_status, '') || ' ' || COALESCE(v_line.last_error, '')
    ));
    IF LOWER(BTRIM(COALESCE(v_line.assignment_status, ''))) IN
       ('assigned', 'allocated', 'complete', 'completed') THEN
        RAISE EXCEPTION 'The order line already reports a completed assignment state';
    END IF;
    IF v_failure_text ~ '(mapping|not found|not matched|missing shopify|identity mismatch|product mismatch|invalid product|malformed|corrupt|contiguous|database)' THEN
        RAISE EXCEPTION 'The allocation failure has a non-edition-state cause and cannot be manually overridden';
    END IF;

    NEW.created_by_email := COALESCE(v_actor.email, '');
    NEW.created_by_display_name := COALESCE(NULLIF(v_actor.display_name, ''), NULLIF(v_actor.username, ''), 'Administrator');
    NEW.verified_order_name := COALESCE(NULLIF(v_order.order_name, ''), NULLIF(v_order.shopify_order_name, ''), NEW.external_order_id);
    NEW.verified_product_title := COALESCE(NULLIF(v_product.product_title, ''), NULLIF(v_line.product_title, ''), v_product_gid);
    NEW.verified_assignment_status := COALESCE(v_line.assignment_status, '');
    NEW.verified_last_error := COALESCE(v_line.last_error, '');
    NEW.verified_series_status := COALESCE(NULLIF(BTRIM(v_series_status), ''), 'blocked');
    NEW.verified_sold_count := COALESCE(v_product.sold_count, 0);
    NEW.verified_remaining_count := COALESCE(v_product.remaining_count, 0);
    NEW.verified_next_edition_number := COALESCE(v_product.next_edition_number, 1);
    NEW.verified_at := now();
    NEW.created_at := now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS manual_order_line_editions_insert_guard
    ON manual_order_line_editions;
CREATE TRIGGER manual_order_line_editions_insert_guard
BEFORE INSERT ON manual_order_line_editions
FOR EACH ROW EXECUTE FUNCTION enforce_manual_order_line_edition_insert();

REVOKE ALL ON FUNCTION enforce_manual_order_line_edition_insert() FROM PUBLIC;

CREATE OR REPLACE FUNCTION enforce_manual_order_line_edition_immutability()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'Manual order-line edition values are immutable audit evidence';
END;
$$;

DROP TRIGGER IF EXISTS manual_order_line_editions_immutable
    ON manual_order_line_editions;
CREATE TRIGGER manual_order_line_editions_immutable
BEFORE UPDATE OR DELETE ON manual_order_line_editions
FOR EACH ROW EXECUTE FUNCTION enforce_manual_order_line_edition_immutability();

REVOKE ALL ON FUNCTION enforce_manual_order_line_edition_immutability() FROM PUBLIC;

COMMIT;
