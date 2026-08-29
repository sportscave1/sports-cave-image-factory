-- Canonicalize legacy numeric Shopify identities for the guarded manual-edition path.
--
-- Historical order-line mirrors may store the same immutable Shopify ID as either
-- a numeric value or a gid:// value. This replaces only the manual-entry insert
-- guard so those representations compare as one identity while source-channel,
-- sold-out, allocation, certificate and fulfilment checks remain fail closed.

BEGIN;

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
    v_line_count INTEGER;
    v_line_product_count INTEGER;
    v_source_channel TEXT;
    v_product_gid TEXT;
    v_total INTEGER;
    v_series_status TEXT;
    v_failure_text TEXT;
    v_fulfilment_status TEXT;
    v_line_fulfilment_status TEXT;
BEGIN
    IF NEW.external_order_id ~ '^[0-9]+$' THEN
        NEW.external_order_id := 'gid://shopify/Order/' || NEW.external_order_id;
    END IF;
    IF NEW.external_line_item_id ~ '^[0-9]+$' THEN
        NEW.external_line_item_id := 'gid://shopify/LineItem/' || NEW.external_line_item_id;
    END IF;

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
    WHERE REGEXP_REPLACE(
            COALESCE(shopify_order_id, ''),
            '^gid://shopify/Order/', ''
          )=REGEXP_REPLACE(
            NEW.external_order_id,
            '^gid://shopify/Order/', ''
          )
    ORDER BY CASE WHEN shopify_order_id=NEW.external_order_id THEN 0 ELSE 1 END
    LIMIT 1
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Immutable order identity was not found';
    END IF;

    SELECT
        COUNT(*),
        COUNT(DISTINCT CASE
            WHEN COALESCE(shopify_product_id, '') ~ '^gid://shopify/Product/[0-9]+$'
                THEN shopify_product_id
            WHEN COALESCE(shopify_product_id, '') ~ '^[0-9]+$'
                THEN 'gid://shopify/Product/' || shopify_product_id
            ELSE NULL
        END)
    INTO v_line_count, v_line_product_count
    FROM shopify_order_lines
    WHERE shopify_order_id=v_order.shopify_order_id
      AND REGEXP_REPLACE(
            COALESCE(shopify_line_item_id, ''),
            '^gid://shopify/LineItem/', ''
          )=REGEXP_REPLACE(
            NEW.external_line_item_id,
            '^gid://shopify/LineItem/', ''
          );
    IF v_line_count < 1 THEN
        RAISE EXCEPTION 'Immutable order-line identity was not found on the expected order';
    END IF;
    IF v_line_product_count <> 1 THEN
        RAISE EXCEPTION 'Immutable order-line mirrors have missing or conflicting product identities';
    END IF;

    SELECT * INTO v_line
    FROM shopify_order_lines
    WHERE shopify_order_id=v_order.shopify_order_id
      AND REGEXP_REPLACE(
            COALESCE(shopify_line_item_id, ''),
            '^gid://shopify/LineItem/', ''
          )=REGEXP_REPLACE(
            NEW.external_line_item_id,
            '^gid://shopify/LineItem/', ''
          )
    ORDER BY CASE WHEN shopify_line_item_id=NEW.external_line_item_id THEN 0 ELSE 1 END,
             id DESC
    LIMIT 1
    FOR UPDATE;

    v_source_channel := CASE
        WHEN LOWER(BTRIM(COALESCE(
            NULLIF(to_jsonb(v_order)->>'source_name', ''),
            v_order.raw_json->>'source_name', ''
        ))) LIKE '%etsy%' THEN 'etsy'
        WHEN LOWER(BTRIM(COALESCE(
            NULLIF(to_jsonb(v_order)->>'source_name', ''),
            v_order.raw_json->>'source_name', ''
        ))) LIKE '%ebay%' THEN 'ebay'
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
               AND REGEXP_REPLACE(
                     COALESCE(eo.external_order_id, ''),
                     '^gid://shopify/Order/', ''
                   )=REGEXP_REPLACE(
                     NEW.external_order_id,
                     '^gid://shopify/Order/', ''
                   )
               AND REGEXP_REPLACE(
                     COALESCE(eo.external_line_item_id, ''),
                     '^gid://shopify/LineItem/', ''
                   )=REGEXP_REPLACE(
                     NEW.external_line_item_id,
                     '^gid://shopify/LineItem/', ''
                   ))
              OR REGEXP_REPLACE(
                   COALESCE(eo.shopify_line_item_id, ''),
                   '^gid://shopify/LineItem/', ''
                 )=REGEXP_REPLACE(
                   NEW.external_line_item_id,
                   '^gid://shopify/LineItem/', ''
                 )
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
           FROM shopify_order_lines candidate
           WHERE candidate.shopify_order_id=v_order.shopify_order_id
             AND REGEXP_REPLACE(
                   COALESCE(candidate.shopify_line_item_id, ''),
                   '^gid://shopify/LineItem/', ''
                 )=REGEXP_REPLACE(
                   NEW.external_line_item_id,
                   '^gid://shopify/LineItem/', ''
                 )
             AND LOWER(BTRIM(COALESCE(
                   NULLIF(to_jsonb(candidate)->>'fulfillment_status', ''),
                   NULLIF(candidate.raw_json->>'fulfillment_status', ''),
                   NULLIF(candidate.raw_json->>'displayFulfillmentStatus', ''),
                   ''
                 ))) IN ('fulfilled', 'complete', 'completed')
       )
       OR EXISTS (
           SELECT 1
           FROM prodigi_dispatch_rows dispatch
           WHERE REGEXP_REPLACE(
                   COALESCE(dispatch.shopify_line_item_id, ''),
                   '^gid://shopify/LineItem/', ''
                 )=REGEXP_REPLACE(
                   NEW.external_line_item_id,
                   '^gid://shopify/LineItem/', ''
                 )
             AND LOWER(BTRIM(COALESCE(dispatch.prodigi_status, ''))) IN
                 ('complete', 'completed', 'fulfilled', 'fulfilled in shopify')
       ) THEN
        RAISE EXCEPTION 'Fulfilled order lines cannot receive a manual edition value';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM certificates certificate
        WHERE REGEXP_REPLACE(
                COALESCE(certificate.shopify_order_id, ''),
                '^gid://shopify/Order/', ''
              )=REGEXP_REPLACE(
                NEW.external_order_id,
                '^gid://shopify/Order/', ''
              )
          AND REGEXP_REPLACE(
                COALESCE(certificate.shopify_line_item_id, ''),
                '^gid://shopify/LineItem/', ''
              )=REGEXP_REPLACE(
                NEW.external_line_item_id,
                '^gid://shopify/LineItem/', ''
              )
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

    IF EXISTS (
        SELECT 1
        FROM shopify_order_lines candidate
        WHERE candidate.shopify_order_id=v_order.shopify_order_id
          AND REGEXP_REPLACE(
                COALESCE(candidate.shopify_line_item_id, ''),
                '^gid://shopify/LineItem/', ''
              )=REGEXP_REPLACE(
                NEW.external_line_item_id,
                '^gid://shopify/LineItem/', ''
              )
          AND LOWER(BTRIM(COALESCE(candidate.assignment_status, ''))) IN
              ('assigned', 'allocated', 'complete', 'completed')
    ) THEN
        RAISE EXCEPTION 'The order line already reports a completed assignment state';
    END IF;

    v_failure_text := LOWER(BTRIM(
        COALESCE(v_line.assignment_status, '') || ' ' || COALESCE(v_line.last_error, '')
    ));
    IF v_failure_text ~ '(mapping|not found|not matched|missing shopify|identity mismatch|product mismatch|invalid product|malformed|corrupt|contiguous|database)' THEN
        RAISE EXCEPTION 'The allocation failure has a non-edition-state cause and cannot be manually overridden';
    END IF;

    NEW.created_by_email := COALESCE(v_actor.email, '');
    NEW.created_by_display_name := COALESCE(
        NULLIF(v_actor.display_name, ''),
        NULLIF(v_actor.username, ''),
        'Administrator'
    );
    NEW.verified_order_name := COALESCE(
        NULLIF(v_order.order_name, ''),
        NULLIF(v_order.shopify_order_name, ''),
        NEW.external_order_id
    );
    NEW.verified_product_title := COALESCE(
        NULLIF(v_product.product_title, ''),
        NULLIF(v_line.product_title, ''),
        v_product_gid
    );
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

REVOKE ALL ON FUNCTION enforce_manual_order_line_edition_insert() FROM PUBLIC;

COMMIT;
