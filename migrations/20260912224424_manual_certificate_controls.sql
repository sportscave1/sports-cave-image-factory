-- Certificate-only controls. No allocation, reservation, run, or counter writes.
BEGIN;
ALTER TABLE manual_order_line_editions ADD COLUMN IF NOT EXISTS duplicate_confirmed BOOLEAN NOT NULL DEFAULT FALSE;
CREATE TABLE IF NOT EXISTS manual_certificate_audit (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    manual_id UUID NOT NULL,
    action TEXT NOT NULL,
    actor_id UUID NOT NULL REFERENCES os_users(id),
    old_value JSONB,
    new_value JSONB,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE manual_certificate_audit ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON manual_certificate_audit FROM PUBLIC, anon, authenticated;
CREATE INDEX IF NOT EXISTS manual_certificate_audit_record ON manual_certificate_audit(manual_id, occurred_at);
DROP TRIGGER IF EXISTS manual_order_line_editions_immutable ON manual_order_line_editions;
DROP TRIGGER IF EXISTS manual_order_line_editions_insert_guard ON manual_order_line_editions;
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

    IF TG_OP='UPDATE' AND (NEW.id, NEW.source_channel, NEW.external_order_id,
        NEW.external_line_item_id, NEW.canonical_product_gid, NEW.edition_total)
        IS DISTINCT FROM (OLD.id, OLD.source_channel, OLD.external_order_id,
        OLD.external_line_item_id, OLD.canonical_product_gid, OLD.edition_total) THEN
        RAISE EXCEPTION 'Manual certificate identity cannot be changed';
    END IF;
    IF EXISTS (
        SELECT 1 FROM edition_orders eo
        WHERE COALESCE(eo.allocation_valid, TRUE)
          AND eo.edition_number=NEW.edition_number
          AND eo.edition_number BETWEEN 1 AND eo.edition_total
          AND (REGEXP_REPLACE(COALESCE(eo.shopify_product_id, ''), '^gid://shopify/Product/', '')
               =REGEXP_REPLACE(NEW.canonical_product_gid, '^gid://shopify/Product/', '')
               OR eo.shopify_handle=v_product.shopify_handle)
    ) AND NOT NEW.duplicate_confirmed THEN
        RAISE EXCEPTION 'Edition already exists in allocation history. Confirm the duplicate certificate number';
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
    NEW.created_at := CASE WHEN TG_OP='UPDATE' THEN OLD.created_at ELSE now() END;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION enforce_manual_order_line_edition_insert() FROM PUBLIC;


CREATE TRIGGER manual_order_line_editions_insert_guard BEFORE INSERT OR UPDATE
ON manual_order_line_editions FOR EACH ROW EXECUTE FUNCTION enforce_manual_order_line_edition_insert();

CREATE OR REPLACE FUNCTION guard_manual_certificate_removal() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE v_actor UUID;
BEGIN
    v_actor := NULLIF(current_setting('sports_cave.manual_certificate_actor', true), '')::uuid;
    IF NOT EXISTS (SELECT 1 FROM os_users WHERE id=v_actor AND role='admin'
        AND is_active IS TRUE AND COALESCE(account_status, 'active') <> 'removed') THEN
        RAISE EXCEPTION 'An active administrator is required';
    END IF;
    IF EXISTS (SELECT 1 FROM certificates
        WHERE edition_order_id='manual-edition:' || OLD.id::text
        OR (REGEXP_REPLACE(shopify_order_id, '^gid://shopify/Order/', '')
            =REGEXP_REPLACE(OLD.external_order_id, '^gid://shopify/Order/', '')
        AND REGEXP_REPLACE(shopify_line_item_id, '^gid://shopify/LineItem/', '')
            =REGEXP_REPLACE(OLD.external_line_item_id, '^gid://shopify/LineItem/', ''))) THEN
        RAISE EXCEPTION 'A certificate already exists; use the certificate replacement workflow';
    END IF;
    RETURN OLD;
END; $$;
CREATE TRIGGER manual_certificate_remove_guard BEFORE DELETE ON manual_order_line_editions
FOR EACH ROW EXECUTE FUNCTION guard_manual_certificate_removal();
REVOKE ALL ON FUNCTION guard_manual_certificate_removal() FROM PUBLIC;

CREATE OR REPLACE FUNCTION audit_manual_certificate_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO manual_certificate_audit(manual_id, action, actor_id, old_value, new_value)
    VALUES (COALESCE(NEW.id, OLD.id), TG_OP,
        CASE WHEN TG_OP='DELETE' THEN current_setting('sports_cave.manual_certificate_actor')::uuid
             ELSE NEW.created_by_user_id END,
        CASE WHEN TG_OP <> 'INSERT' THEN to_jsonb(OLD) END,
        CASE WHEN TG_OP <> 'DELETE' THEN to_jsonb(NEW) END);
    RETURN COALESCE(NEW, OLD);
END; $$;
CREATE TRIGGER manual_certificate_audit_changes AFTER INSERT OR UPDATE OR DELETE
ON manual_order_line_editions FOR EACH ROW EXECUTE FUNCTION audit_manual_certificate_change();
CREATE TRIGGER manual_certificate_audit_immutable BEFORE UPDATE OR DELETE
ON manual_certificate_audit FOR EACH ROW EXECUTE FUNCTION enforce_manual_order_line_edition_immutability();
REVOKE ALL ON FUNCTION audit_manual_certificate_change() FROM PUBLIC;
COMMIT;
