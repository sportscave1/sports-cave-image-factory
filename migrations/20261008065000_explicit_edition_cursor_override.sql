-- Explicit admin authorisation scopes number reuse; order-unit identity remains unique.
BEGIN;
CREATE TABLE edition_cursor_overrides (
 id uuid PRIMARY KEY, run_id uuid NOT NULL REFERENCES edition_runs(id),
 actor_id uuid NOT NULL REFERENCES os_users(id), previous_number integer NOT NULL,
 next_number integer NOT NULL CHECK(next_number>0), duplicate_acknowledged boolean NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE edition_cursor_overrides ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON edition_cursor_overrides FROM PUBLIC, anon, authenticated;
ALTER TABLE edition_products ADD COLUMN manual_override_id uuid REFERENCES edition_cursor_overrides(id);
ALTER TABLE edition_runs ADD COLUMN manual_override_id uuid REFERENCES edition_cursor_overrides(id);
ALTER TABLE edition_orders ADD COLUMN manual_override_id uuid REFERENCES edition_cursor_overrides(id);
CREATE FUNCTION immutable_edition_cursor_audit() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Edition override audit is immutable'; END $$;
CREATE TRIGGER edition_cursor_audit_guard BEFORE UPDATE OR DELETE ON edition_cursor_overrides
 FOR EACH ROW EXECUTE FUNCTION immutable_edition_cursor_audit();
DROP INDEX edition_orders_run_edition_uidx;
CREATE UNIQUE INDEX edition_orders_run_edition_uidx ON edition_orders
 (edition_run_id,edition_number,COALESCE(manual_override_id,'00000000-0000-0000-0000-000000000000'::uuid))
 WHERE edition_run_id IS NOT NULL AND allocation_valid;

CREATE FUNCTION override_edition_cursor(p_handle text,p_run uuid,p_expected integer,p_next integer,
 p_request uuid,p_actor uuid,p_ack boolean) RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE p edition_products%ROWTYPE; r edition_runs%ROWTYPE; a edition_cursor_overrides%ROWTYPE;
 gid text; conflict boolean; units integer;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM os_users WHERE id=p_actor AND role='admin' AND is_active
 AND COALESCE(account_status,'active')<>'removed') THEN RAISE EXCEPTION 'Active administrator required'; END IF;
 IF p_request IS NULL OR p_run IS NULL OR p_next IS NULL OR p_expected IS NULL OR p_ack IS NULL
 THEN RAISE EXCEPTION 'Complete override identity required'; END IF;
 SELECT COALESCE(NULLIF(shopify_product_gid,''),shopify_product_id) INTO STRICT gid
 FROM edition_products WHERE shopify_handle=p_handle;
 PERFORM pg_advisory_xact_lock(hashtextextended(gid,0));
 SELECT * INTO STRICT p FROM edition_products WHERE shopify_handle=p_handle FOR UPDATE;
 SELECT * INTO a FROM edition_cursor_overrides WHERE id=p_request;
 IF FOUND THEN
 IF NOT EXISTS(SELECT 1 FROM edition_runs WHERE id=a.run_id AND edition_product_id=p.id)
 OR a.run_id<>p_run OR a.next_number<>p_next OR a.actor_id<>p_actor OR a.previous_number<>p_expected
 OR a.duplicate_acknowledged<>p_ack THEN RAISE EXCEPTION 'Submission identity reused with different values'; END IF;
 RETURN to_jsonb(a); END IF;
 SELECT * INTO STRICT r FROM edition_runs WHERE id=p.active_edition_run_id FOR UPDATE;
 IF r.id<>p_run OR r.edition_product_id IS DISTINCT FROM p.id OR p.next_edition_number<>p_expected
 THEN RAISE EXCEPTION 'Edition changed; refresh before saving'; END IF;
 IF r.status IN ('expired','pending_sync','inactive') THEN RAISE EXCEPTION 'Release is not available for override'; END IF;
 IF p.edition_total IS NULL OR p.edition_total IS DISTINCT FROM r.edition_total
 OR p_next NOT BETWEEN 1 AND p.edition_total OR p.sold_count>=p.edition_total
 THEN RAISE EXCEPTION 'Invalid next number or edition sales cap reached'; END IF;
 SELECT count(*) INTO units FROM edition_orders WHERE edition_run_id=r.id AND identity_enforced
 AND allocation_valid AND COALESCE(status,'') NOT IN ('voided','refunded','cancelled','superseded');
 IF p.sold_count IS NULL OR p.remaining_count IS NULL OR p.sold_count<units OR p.sold_count<0
 OR p.remaining_count<>p.edition_total-p.sold_count
 THEN RAISE EXCEPTION 'Actual sales counters require review'; END IF;
 conflict:=p_next<=COALESCE(p.last_assigned_edition,0) OR EXISTS(
 SELECT 1 FROM edition_orders WHERE (edition_run_id=r.id OR (edition_run_id IS NULL
 AND regexp_replace(COALESCE(NULLIF(shopify_product_gid,''),shopify_product_id,''),'^.*/','')=regexp_replace(gid,'^.*/','')))
 AND edition_number>=p_next)
 OR EXISTS(SELECT 1 FROM edition_allocation_tombstones WHERE shopify_product_gid=gid
 AND (edition_run_id=r.id OR edition_run_id IS NULL) AND former_edition_number>=p_next);
 IF conflict AND NOT p_ack THEN RAISE EXCEPTION 'DUPLICATE_ACK_REQUIRED: This number may already have been allocated. Continue with manual override?'; END IF;
 INSERT INTO edition_cursor_overrides VALUES(p_request,r.id,p_actor,p_expected,p_next,p_ack,now());
 PERFORM set_config('sports_cave.cursor_action','override',true);
 UPDATE edition_runs SET manual_override_id=p_request,next_edition_number=p_next,status='active',
 allocation_baseline_sold_count=p.sold_count-units,sync_attempts=0,sync_retry_at=now(),sync_error='',updated_at=now() WHERE id=r.id;
 UPDATE edition_products SET manual_override_id=p_request,next_edition_number=p_next,
 sold_out=false,is_sold_out=false,metafields_sync_status='Pending',last_metafield_error='',updated_at=now() WHERE id=p.id;
 INSERT INTO edition_version_audit(run_id,actor_id,action,before_state,after_state,reason)
 VALUES(r.id,p_actor,'NEXT NUMBER OVERRIDE',to_jsonb(p),jsonb_build_object('next',p_next,'request',p_request,'duplicate_acknowledged',p_ack),
 'Explicit administrator cursor override; sales and certificates preserved');
 RETURN (SELECT to_jsonb(x) FROM edition_cursor_overrides x WHERE id=p_request);
END $$;
REVOKE ALL ON FUNCTION override_edition_cursor(text,uuid,integer,integer,uuid,uuid,boolean) FROM PUBLIC, anon, authenticated;

CREATE FUNCTION guard_manual_edition_cursor() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.manual_override_id IS DISTINCT FROM OLD.manual_override_id
 AND COALESCE(current_setting('sports_cave.cursor_action',true),'')<>'override'
 AND COALESCE(current_setting('sports_cave.edition_version_action',true),'')<>'transition'
 THEN RAISE EXCEPTION 'Explicit administrator override required'; END IF;
 IF TG_TABLE_NAME='edition_products' THEN
 IF NEW.active_edition_run_id IS DISTINCT FROM OLD.active_edition_run_id THEN
 NEW.manual_override_id:=NULL; RETURN NEW; END IF; END IF;
 IF OLD.manual_override_id IS NOT NULL AND NEW.next_edition_number IS DISTINCT FROM OLD.next_edition_number
 AND COALESCE(current_setting('sports_cave.cursor_action',true),'')<>'override'
 AND COALESCE(current_setting('sports_cave.atomic_edition_allocation',true),'')<>'1'
 THEN RAISE EXCEPTION 'Persisted administrator cursor cannot be overwritten by reconciliation'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER manual_cursor_product_guard BEFORE UPDATE ON edition_products FOR EACH ROW EXECUTE FUNCTION guard_manual_edition_cursor();
CREATE TRIGGER manual_cursor_run_guard BEFORE UPDATE ON edition_runs FOR EACH ROW EXECUTE FUNCTION guard_manual_edition_cursor();
CREATE FUNCTION bind_edition_cursor_allocation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='UPDATE' THEN
 IF NEW.manual_override_id IS DISTINCT FROM OLD.manual_override_id THEN RAISE EXCEPTION 'Issued override identity is immutable'; END IF;
 ELSE
 SELECT manual_override_id INTO NEW.manual_override_id FROM edition_runs WHERE id=NEW.edition_run_id;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER bind_cursor_allocation BEFORE INSERT OR UPDATE ON edition_orders FOR EACH ROW EXECUTE FUNCTION bind_edition_cursor_allocation();
-- Extend the existing allocator, retaining source/order replay, cap and transaction logic.
DO $$ DECLARE f text; before_part text; after_part text; BEGIN
 SELECT pg_get_functiondef(oid) INTO STRICT f FROM pg_proc WHERE proname='allocate_edition_line_units_atomic';
 f:=replace(f,chr(13),'');
 before_part:='IF EXISTS (SELECT 1 FROM edition_orders eo';
 after_part:='IF (v_run.manual_override_id IS NULL AND (EXISTS (SELECT 1 FROM edition_orders eo';
 IF position(before_part IN f)=0 THEN RAISE EXCEPTION 'Allocator guard anchor missing'; END IF;
 -- Parenthesise the existing historical boundary checks; add pass-scoped uniqueness.
 f:=replace(f,before_part,after_part);
 before_part:='THEN'||chr(10)||'        RAISE EXCEPTION ''Allocation cursor conflicts with an issued or reserved edition'';';
 after_part:=')) OR EXISTS (SELECT 1 FROM edition_orders eo WHERE eo.edition_run_id=v_run.id AND v_run.manual_override_id IS NOT NULL AND eo.manual_override_id=v_run.manual_override_id AND eo.edition_number>=v_next) THEN'||chr(10)||'        RAISE EXCEPTION ''Allocation cursor conflicts with an issued or reserved edition'';';
 IF position(before_part IN f)=0 THEN RAISE EXCEPTION 'Allocator conflict anchor missing'; END IF;
 f:=replace(f,before_part,after_part);
 EXECUTE f;
END $$;
COMMIT;
