BEGIN;
CREATE FUNCTION public.product_upload_mapping_complete(op uuid,pid text,fid text) RETURNS boolean
LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 -- A durable completion receipt: subsequent explicit edition restarts and
 -- administrator PSD replacements must not resurrect the original move hold.
 -- The application writes this only after locked product/run verification,
 -- destination metadata verification and mapping persistence, in one transaction.
 SELECT EXISTS(SELECT 1 FROM public.product_upload_intakes u
 WHERE u.id=op AND u.data->'upload_operation'->>'product_id'=pid
 AND u.data->'upload_operation'->'sync_map'->>'state'='Mapped'
 AND u.data->'upload_operation'->'sync_map'->>'verified_at' IS NOT NULL
 AND u.data->'upload_operation'->'sync_map'->>'run_id' IS NOT NULL
 AND u.data->'upload_operation'->'sync_map'->>'edition_id' IS NOT NULL
 AND u.data->'upload_operation'->'sync_map'->'moved'->>'id'=fid
 AND u.data->'upload_operation'->'sync_map'->'moved'->>'rev' IS NOT NULL
 AND u.data->'upload_operation'->'sync_map'->'moved'->>'content_hash' IS NOT NULL);
$$;
REVOKE ALL ON FUNCTION public.product_upload_mapping_complete(uuid,text,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.product_upload_mapping_complete(uuid,text,text) TO service_role;
CREATE OR REPLACE FUNCTION public.guard_upload_mapping_only() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE h public.product_upload_mapping_holds; value jsonb:=to_jsonb(NEW);pid text;fid text;
BEGIN
 pid:=COALESCE(value->>'product_gid',value->>'shopify_product_gid',value->'payload'->'identity'->'source'->>'product_gid');
 fid:=COALESCE(value->>'file_id',value->>'dropbox_file_id',value->'payload'->'identity'->'source'->>'file_id');
 SELECT * INTO h FROM public.product_upload_mapping_holds WHERE product_gid=pid OR file_id=fid LIMIT 1;
 IF NOT FOUND THEN RETURN NEW; END IF;
 IF TG_TABLE_NAME='product_psd_mappings' THEN
   IF public.product_upload_mapping_complete(h.operation_id,h.product_gid,h.file_id)
      AND value->>'source'='manual' AND NULLIF(value->>'actor_id','') IS NOT NULL THEN
     RETURN NEW; -- Existing explicit administrator replacement flow.
   END IF;
   IF pid<>h.product_gid OR fid<>h.file_id OR value->>'actor_id'<>h.actor_id OR value->>'source'<>'manual'
     OR NOT EXISTS(SELECT 1 FROM public.product_upload_intakes u WHERE u.id=h.operation_id
       AND u.data->'upload_operation'->>'product_id'=pid
       AND u.data->'upload_operation'->'sync_map'->'moved'->>'id'=fid
       AND u.data->'upload_operation'->'sync_map'->'moved'->>'path_display'=value->>'file_path') THEN
     RAISE EXCEPTION 'PSD is held for verified upload mapping only';
   END IF;
   RETURN NEW;
 END IF;
 IF public.product_upload_mapping_complete(h.operation_id,h.product_gid,h.file_id) THEN RETURN NEW; END IF;
 RETURN NULL;
END;
$$;
COMMIT;
