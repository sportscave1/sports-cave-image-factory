-- REVIEW REQUIRED: install only with explicit deployment approval.
-- Uses the existing durable order locks. No orders or counters change on install.
BEGIN;
CREATE OR REPLACE FUNCTION public.guard_cancelled_edition_order()
RETURNS trigger LANGUAGE plpgsql SET search_path=public,pg_temp AS $$
DECLARE order_id text; cancellation timestamptz; unit edition_orders%ROWTYPE;
BEGIN
  order_id := regexp_replace(COALESCE(NEW.shopify_order_id,''),'^.*/','');
  IF TG_TABLE_NAME='certificates' THEN
    IF NULLIF(NEW.edition_order_id,'') IS NOT NULL THEN
      SELECT * INTO unit FROM edition_orders WHERE id::text=NEW.edition_order_id;
      order_id := COALESCE(NULLIF(order_id,''),regexp_replace(unit.shopify_order_id,'^.*/',''));
    END IF;
  END IF;
  -- Certificate/dispatch writers serialize with the repair's order row lock.
  IF TG_TABLE_NAME IN ('certificates','prodigi_dispatch_rows') THEN
    PERFORM 1 FROM shopify_orders
      WHERE regexp_replace(shopify_order_id,'^.*/','')=order_id FOR SHARE;
  END IF;
  SELECT updated_at INTO cancellation FROM edition_order_sync_locks
    WHERE canonical_order_key='id:'||order_id AND lower(status)='cancelled'
      AND reason='sc3303-release-019-20261015';
  IF cancellation IS NULL THEN RETURN NEW; END IF;
  IF TG_TABLE_NAME='shopify_orders' THEN
    NEW.cancelled_at := cancellation;
    NEW.fulfillment_status := 'CANCELLED';
    NEW.total_price := '0.00';
    NEW.raw_json := COALESCE(NEW.raw_json,'{}'::jsonb)||jsonb_build_object(
      'cancelled_at',cancellation,'sports_cave_fulfilment_status','CANCELLED',
      '_edition_cancellation','sc3303-release-019-20261015');
    NEW.raw := COALESCE(NEW.raw,'{}'::jsonb)||jsonb_build_object(
      'cancelled_at',cancellation,'sports_cave_fulfilment_status','CANCELLED',
      '_edition_cancellation','sc3303-release-019-20261015');
  ELSIF TG_TABLE_NAME='shopify_order_lines' THEN
    NEW.quantity := 0;
    NEW.assignment_status := 'Cancelled';
    NEW.last_error := 'Cancelled in Sports Cave OS; allocation released by audited repair';
  ELSIF TG_TABLE_NAME='edition_orders' THEN
    IF NEW.allocation_valid OR NEW.status IS DISTINCT FROM 'cancelled'
       OR NEW.certificate_status IS DISTINCT FROM 'Cancelled' THEN
      RAISE EXCEPTION 'Cancelled order allocation cannot be restored';
    END IF;
  ELSE
    RAISE EXCEPTION 'Cancelled order cannot create certificate or dispatch work';
  END IF;
  RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION public.guard_cancelled_edition_order() FROM PUBLIC,anon,authenticated;

CREATE TRIGGER cancelled_edition_order_guard BEFORE INSERT OR UPDATE ON shopify_orders
  FOR EACH ROW EXECUTE FUNCTION guard_cancelled_edition_order();
CREATE TRIGGER cancelled_edition_line_guard BEFORE INSERT OR UPDATE ON shopify_order_lines
  FOR EACH ROW EXECUTE FUNCTION guard_cancelled_edition_order();
CREATE TRIGGER cancelled_edition_allocation_guard BEFORE INSERT OR UPDATE ON edition_orders
  FOR EACH ROW EXECUTE FUNCTION guard_cancelled_edition_order();
CREATE TRIGGER cancelled_edition_certificate_guard BEFORE INSERT OR UPDATE ON certificates
  FOR EACH ROW EXECUTE FUNCTION guard_cancelled_edition_order();
CREATE TRIGGER cancelled_edition_dispatch_guard BEFORE INSERT OR UPDATE ON prodigi_dispatch_rows
  FOR EACH ROW EXECUTE FUNCTION guard_cancelled_edition_order();
COMMIT;
