-- Explicit releases on the existing ledger. No product is reset by installation.
BEGIN;
ALTER TABLE edition_runs
 ADD COLUMN IF NOT EXISTS starting_number integer NOT NULL DEFAULT 1 CHECK(starting_number BETWEEN 1 AND 100),
 ADD COLUMN IF NOT EXISTS sold_count integer,
 ADD COLUMN IF NOT EXISTS last_allocated_number integer,
 ADD COLUMN IF NOT EXISTS revision_reason text,
 ADD COLUMN IF NOT EXISTS retired_reason text,
 ADD COLUMN IF NOT EXISTS activated_at timestamptz,
 ADD COLUMN IF NOT EXISTS created_by uuid REFERENCES os_users(id),
 ADD COLUMN IF NOT EXISTS request_id uuid UNIQUE,
 ADD COLUMN IF NOT EXISTS sync_attempts integer NOT NULL DEFAULT 0,
 ADD COLUMN IF NOT EXISTS sync_retry_at timestamptz,
 ADD COLUMN IF NOT EXISTS sync_error text NOT NULL DEFAULT '';
ALTER TABLE edition_allocation_tombstones ADD COLUMN IF NOT EXISTS edition_run_id uuid REFERENCES edition_runs(id);
ALTER TABLE edition_orders ADD COLUMN IF NOT EXISTS edition_release_label text;
CREATE UNIQUE INDEX IF NOT EXISTS edition_runs_current_release ON edition_runs(edition_product_id)
 WHERE edition_product_id IS NOT NULL AND status IN ('active','pending_sync');
CREATE INDEX IF NOT EXISTS edition_runs_expiry_page ON edition_runs(archived_at DESC,id) WHERE status='expired';
CREATE INDEX IF NOT EXISTS edition_runs_pending_sync ON edition_runs(sync_retry_at) WHERE status='pending_sync';

CREATE TABLE IF NOT EXISTS edition_version_audit (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 run_id uuid NOT NULL REFERENCES edition_runs(id), actor_id uuid REFERENCES os_users(id),
 action text NOT NULL, before_state jsonb, after_state jsonb, reason text NOT NULL,
 occurred_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE edition_version_audit ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON edition_version_audit FROM PUBLIC,anon,authenticated;
CREATE INDEX IF NOT EXISTS edition_version_audit_run ON edition_version_audit(run_id,id DESC);
CREATE OR REPLACE FUNCTION edition_version_audit_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Edition version audit is immutable'; END $$;
CREATE TRIGGER edition_version_audit_immutable BEFORE UPDATE OR DELETE ON edition_version_audit
 FOR EACH ROW EXECUTE FUNCTION edition_version_audit_guard();

CREATE OR REPLACE FUNCTION start_edition_version(p_handle text,p_expected_run uuid,p_request uuid,
 p_name text,p_start integer,p_total integer,p_reason text,p_actor uuid) RETURNS jsonb
LANGUAGE plpgsql AS $$
DECLARE p edition_products%ROWTYPE; old edition_runs%ROWTYPE; fresh edition_runs%ROWTYPE; gid text;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM os_users WHERE id=p_actor AND role='admin' AND is_active
   AND COALESCE(account_status,'active')<>'removed') THEN RAISE EXCEPTION 'Active administrator required'; END IF;
 IF p_request IS NULL OR p_expected_run IS NULL OR length(btrim(p_name)) NOT BETWEEN 1 AND 80
   OR length(btrim(p_reason)) NOT BETWEEN 5 AND 500 OR p_start NOT BETWEEN 1 AND p_total
   OR p_total NOT BETWEEN 1 AND 100 THEN RAISE EXCEPTION 'Version label, revision reason and valid start/total required'; END IF;
 SELECT COALESCE(NULLIF(shopify_product_gid,''),shopify_product_id) INTO STRICT gid FROM edition_products WHERE shopify_handle=p_handle;
 PERFORM pg_advisory_xact_lock(hashtextextended(gid,0));
 SELECT * INTO STRICT p FROM edition_products WHERE shopify_handle=p_handle FOR UPDATE;
 SELECT * INTO fresh FROM edition_runs WHERE request_id=p_request;
 IF FOUND THEN
   IF fresh.edition_product_id<>p.id OR fresh.edition_name<>btrim(p_name) OR fresh.starting_number<>p_start
     OR fresh.edition_total<>p_total OR fresh.revision_reason<>btrim(p_reason) THEN RAISE EXCEPTION 'Submission identity reused with different values'; END IF;
   RETURN to_jsonb(fresh);
 END IF;
 IF p.active_edition_run_id IS DISTINCT FROM p_expected_run THEN RAISE EXCEPTION 'Edition changed; reload before creating a version'; END IF;
 SELECT * INTO STRICT old FROM edition_runs WHERE id=p.active_edition_run_id FOR UPDATE;
 IF old.status IN ('pending_sync','expired') THEN RAISE EXCEPTION 'Finish the current transition before starting another version'; END IF;
 IF EXISTS(SELECT 1 FROM edition_runs WHERE edition_product_id=p.id AND lower(edition_name)=lower(btrim(p_name)))
 THEN RAISE EXCEPTION 'Choose a distinct release label'; END IF;
 -- Ambiguous legacy evidence must be reviewed, never silently reassigned.
 IF EXISTS(SELECT 1 FROM edition_orders WHERE edition_run_id IS NULL AND
   regexp_replace(COALESCE(NULLIF(shopify_product_gid,''),shopify_product_id,''),'^.*/','')=regexp_replace(gid,'^.*/',''))
 OR EXISTS(SELECT 1 FROM edition_allocation_tombstones WHERE shopify_product_gid=gid AND edition_run_id IS NULL)
 THEN RAISE EXCEPTION 'Unversioned allocation or repair evidence requires an audited historical reconciliation first'; END IF;
 PERFORM set_config('sports_cave.edition_version_action','transition',true);
 UPDATE edition_runs SET status='expired',archived_at=now(),retired_reason=btrim(p_reason),
   sold_count=p.sold_count,last_allocated_number=p.last_assigned_edition,updated_at=now() WHERE id=old.id;
 INSERT INTO edition_runs(edition_product_id,shopify_product_id,shopify_handle,product_title,edition_name,
  starting_number,next_edition_number,edition_total,sold_count,last_allocated_number,status,revision_reason,
  created_by,request_id,sync_retry_at,allocation_baseline_sold_count,allocation_baseline_reason)
 VALUES(p.id,gid,p_handle,p.product_title,btrim(p_name),p_start,p_start,p_total,0,0,'pending_sync',btrim(p_reason),
  p_actor,p_request,now(),0,'New release; no historical sales carried forward') RETURNING * INTO fresh;
 UPDATE edition_products SET active_edition_run_id=fresh.id,edition_name=fresh.edition_name,
  edition_total=p_total,next_edition_number=p_start,sold_count=0,last_assigned_edition=0,remaining_count=p_total,
  active=false,is_active=false,sold_out=false,is_sold_out=false,metafields_sync_status='Pending',last_metafield_error='',updated_at=now()
 WHERE id=p.id;
 INSERT INTO edition_version_audit(run_id,actor_id,action,before_state,after_state,reason)
 VALUES(old.id,p_actor,'EXPIRED',to_jsonb(old),jsonb_build_object('replacement',fresh.id),btrim(p_reason)),
 (fresh.id,p_actor,'PENDING SYNC',to_jsonb(p),to_jsonb(fresh),btrim(p_reason));
 RETURN to_jsonb(fresh);
END $$;

CREATE OR REPLACE FUNCTION guard_edition_release() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF OLD.status='expired' AND COALESCE(current_setting('sports_cave.edition_repair_key',true),'')='' THEN
   RAISE EXCEPTION 'Expired edition versions are read-only; an audited repair is required'; END IF;
 IF OLD.revision_reason IS NOT NULL AND (NEW.edition_name IS DISTINCT FROM OLD.edition_name
   OR NEW.edition_product_id IS DISTINCT FROM OLD.edition_product_id OR NEW.starting_number IS DISTINCT FROM OLD.starting_number
   OR NEW.revision_reason IS DISTINCT FROM OLD.revision_reason OR NEW.request_id IS DISTINCT FROM OLD.request_id) THEN
   RAISE EXCEPTION 'Release identity is immutable'; END IF;
 IF OLD.status='pending_sync' AND NEW.status<>'pending_sync'
   AND COALESCE(current_setting('sports_cave.edition_version_action',true),'')<>'activate'
 THEN RAISE EXCEPTION 'Shopify confirmation is required before activation'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER edition_release_guard BEFORE UPDATE ON edition_runs FOR EACH ROW EXECUTE FUNCTION guard_edition_release();

CREATE OR REPLACE FUNCTION guard_edition_release_allocation() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r edition_runs%ROWTYPE; current_run uuid; ordered timestamptz;
BEGIN
 IF TG_OP='UPDATE' THEN
   IF (NEW.edition_run_id IS DISTINCT FROM OLD.edition_run_id OR NEW.edition_release_label IS DISTINCT FROM OLD.edition_release_label)
    AND COALESCE(current_setting('sports_cave.edition_repair_key',true),'')='' THEN
    RAISE EXCEPTION 'Issued edition release identity is immutable'; END IF;
   RETURN NEW;
 END IF;
 SELECT * INTO r FROM edition_runs WHERE id=NEW.edition_run_id;
 IF r.revision_reason IS NOT NULL THEN
   SELECT active_edition_run_id INTO current_run FROM edition_products WHERE id=r.edition_product_id FOR UPDATE;
   IF current_run IS DISTINCT FROM r.id OR r.status<>'active' THEN RAISE EXCEPTION 'Release is not active'; END IF;
   SELECT created_at INTO ordered FROM shopify_orders WHERE shopify_order_id=NEW.shopify_order_id;
   IF ordered IS NULL OR ordered<r.activated_at THEN
     RAISE EXCEPTION 'Order predates this release or has no verified purchase time; review its original design allocation'; END IF;
   NEW.edition_release_label:=r.edition_name||' · Release '||r.id::text;
 ELSIF r.status='expired' AND COALESCE(current_setting('sports_cave.edition_repair_key',true),'')='' THEN
   RAISE EXCEPTION 'Expired editions cannot receive new allocations';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER edition_release_allocation_guard BEFORE INSERT OR UPDATE ON edition_orders
 FOR EACH ROW EXECUTE FUNCTION guard_edition_release_allocation();

CREATE OR REPLACE FUNCTION guard_edition_release_product() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r edition_runs%ROWTYPE; operation text:=COALESCE(current_setting('sports_cave.edition_version_action',true),'');
BEGIN
 SELECT * INTO r FROM edition_runs WHERE id=OLD.active_edition_run_id;
 IF r.revision_reason IS NOT NULL THEN
   IF NEW.active_edition_run_id IS DISTINCT FROM OLD.active_edition_run_id AND operation<>'transition'
   THEN RAISE EXCEPTION 'Only an explicit edition transition may replace a release'; END IF;
   IF r.status='pending_sync' AND operation NOT IN ('activate','transition') AND
    (NEW.next_edition_number IS DISTINCT FROM OLD.next_edition_number OR NEW.sold_count IS DISTINCT FROM OLD.sold_count
     OR NEW.edition_total IS DISTINCT FROM OLD.edition_total OR NEW.active IS DISTINCT FROM OLD.active)
   THEN RAISE EXCEPTION 'Edition is pending Shopify sync; allocation and counter changes are paused'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER edition_release_product_guard BEFORE UPDATE ON edition_products
 FOR EACH ROW EXECUTE FUNCTION guard_edition_release_product();

-- Product counters remain the allocator's authoritative current-run projection.
CREATE OR REPLACE FUNCTION record_edition_release_counters() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 UPDATE edition_runs SET sold_count=NEW.sold_count,last_allocated_number=NEW.last_assigned_edition
 WHERE id=NEW.active_edition_run_id AND status<>'expired'
  AND (sold_count IS DISTINCT FROM NEW.sold_count OR last_allocated_number IS DISTINCT FROM NEW.last_assigned_edition);
 RETURN NEW;
END $$;
CREATE TRIGGER edition_release_counters AFTER UPDATE OF sold_count,last_assigned_edition ON edition_products
 FOR EACH ROW EXECUTE FUNCTION record_edition_release_counters();

-- Keep global source replay tombstones, but number reservations belong to a release.
DO $$ DECLARE definition text; signature regprocedure;
BEGIN
 SELECT p.oid::regprocedure INTO STRICT signature FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
 WHERE n.nspname='public' AND p.proname='allocate_edition_line_units_atomic';
 definition:=pg_get_functiondef(signature);
 IF position('t.former_edition_number BETWEEN v_next' IN definition)=0 THEN
   RAISE EXCEPTION 'Install independent edition cursor migration before edition versioning'; END IF;
 definition:=replace(definition,'AND t.former_edition_number BETWEEN v_next',
   'AND (t.edition_run_id = v_run.id OR t.edition_run_id IS NULL) AND t.former_edition_number BETWEEN v_next');
 EXECUTE definition;
END $$;
REVOKE ALL ON FUNCTION start_edition_version(text,uuid,uuid,text,integer,integer,text,uuid) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION edition_version_audit_guard(),guard_edition_release(),guard_edition_release_allocation(),
 guard_edition_release_product(),record_edition_release_counters() FROM PUBLIC,anon,authenticated;
COMMIT;
