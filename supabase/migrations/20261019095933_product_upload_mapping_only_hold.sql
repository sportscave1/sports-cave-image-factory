-- Mapping only: no future runnable preparation is inserted for a held upload.
BEGIN;
CREATE TABLE public.product_upload_mapping_holds (
 operation_id uuid PRIMARY KEY REFERENCES public.product_upload_intakes(id),
 actor_id text NOT NULL,
 product_gid text NOT NULL UNIQUE CHECK(product_gid ~ '^gid://shopify/Product/[1-9][0-9]*$'),
 file_id text NOT NULL UNIQUE CHECK(file_id ~ '^id:[A-Za-z0-9_-]+$'),
 created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.product_upload_mapping_holds ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.product_upload_mapping_holds FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT,INSERT ON public.product_upload_mapping_holds TO service_role;
GRANT DELETE ON public.auto_edition_discovery TO service_role;

CREATE FUNCTION public.guard_upload_mapping_only() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
 h public.product_upload_mapping_holds;
 value jsonb := to_jsonb(NEW);
 pid text;
 fid text;
BEGIN
 pid := COALESCE(value->>'product_gid',value->>'shopify_product_gid',value->'payload'->'identity'->'source'->>'product_gid');
 fid := COALESCE(value->>'file_id',value->>'dropbox_file_id',value->'payload'->'identity'->'source'->>'file_id');
 SELECT * INTO h FROM public.product_upload_mapping_holds WHERE product_gid=pid OR file_id=fid LIMIT 1;
 IF NOT FOUND THEN RETURN NEW; END IF;
 IF TG_TABLE_NAME='product_psd_mappings' THEN
   IF pid<>h.product_gid OR fid<>h.file_id OR value->>'actor_id'<>h.actor_id OR value->>'source'<>'manual'
     OR NOT EXISTS(SELECT 1 FROM public.product_upload_intakes u WHERE u.id=h.operation_id
       AND u.data->'upload_operation'->>'product_id'=pid
       AND u.data->'upload_operation'->'sync_map'->'moved'->>'id'=fid
       AND u.data->'upload_operation'->'sync_map'->'moved'->>'path_display'=value->>'file_path') THEN
     RAISE EXCEPTION 'PSD is held for verified upload mapping only';
   END IF;
   RETURN NEW;
 END IF;
 -- Old callers, scanners, direct inserts and claim updates cannot bypass this.
 RETURN NULL;
END;
$$;
REVOKE ALL ON FUNCTION public.guard_upload_mapping_only() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.guard_upload_mapping_only() TO service_role;
CREATE TRIGGER upload_hold_onboarding BEFORE INSERT OR UPDATE ON public.auto_edition_onboarding
 FOR EACH ROW EXECUTE FUNCTION public.guard_upload_mapping_only();
CREATE TRIGGER upload_hold_discovery BEFORE INSERT OR UPDATE ON public.auto_edition_discovery
 FOR EACH ROW EXECUTE FUNCTION public.guard_upload_mapping_only();
CREATE TRIGGER upload_hold_inventory BEFORE INSERT OR UPDATE ON public.auto_edition_source_inventory
 FOR EACH ROW EXECUTE FUNCTION public.guard_upload_mapping_only();
CREATE TRIGGER upload_hold_mapping BEFORE INSERT OR UPDATE ON public.product_psd_mappings
 FOR EACH ROW EXECUTE FUNCTION public.guard_upload_mapping_only();
CREATE TRIGGER upload_hold_render BEFORE INSERT OR UPDATE ON public.auto_edition_jobs
 FOR EACH ROW EXECUTE FUNCTION public.guard_upload_mapping_only();
COMMIT;
