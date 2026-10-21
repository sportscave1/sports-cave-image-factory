BEGIN;
-- A manual terminal receipt retires an individual hold without deleting it.
-- The application writes the receipt and verified manual link in one transaction.
CREATE OR REPLACE FUNCTION public.product_upload_mapping_complete(op uuid,pid text,fid text) RETURNS boolean
LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 SELECT EXISTS(SELECT 1 FROM public.product_upload_intakes u
 WHERE u.id=op AND (
 (u.data->'upload_operation'->>'product_id'=pid
 AND u.data->'upload_operation'->'sync_map'->>'state'='Mapped'
 AND u.data->'upload_operation'->'sync_map'->>'verified_at' IS NOT NULL
 AND u.data->'upload_operation'->'sync_map'->>'run_id' IS NOT NULL
 AND u.data->'upload_operation'->'sync_map'->>'edition_id' IS NOT NULL
 AND u.data->'upload_operation'->'sync_map'->'moved'->>'id'=fid
 AND u.data->'upload_operation'->'sync_map'->'moved'->>'rev' IS NOT NULL
 AND u.data->'upload_operation'->'sync_map'->'moved'->>'content_hash' IS NOT NULL)
 OR (u.data->'upload_operation'->'sync_map'->'manual_takeover'->>'hold_operation_id'=op::text
 AND u.data->'upload_operation'->'sync_map'->'manual_takeover'->>'product_gid'=pid
 AND u.data->'upload_operation'->'sync_map'->'manual_takeover'->>'file_id'=fid
 AND u.data->'upload_operation'->'sync_map'->'manual_takeover'->>'verified_at' IS NOT NULL
 AND u.data->'upload_operation'->'sync_map'->'manual_takeover'->>'edition_id' IS NOT NULL
 AND u.data->'upload_operation'->'sync_map'->'manual_takeover'->>'actor_id' IS NOT NULL
 AND u.data->'upload_operation'->'sync_map'->'manual_takeover'->'source'->>'id'=fid
 AND u.data->'upload_operation'->'sync_map'->'manual_takeover'->'source'->>'rev' IS NOT NULL
 AND u.data->'upload_operation'->'sync_map'->'manual_takeover'->'source'->>'content_hash' IS NOT NULL)));
$$;
REVOKE ALL ON FUNCTION public.product_upload_mapping_complete(uuid,text,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.product_upload_mapping_complete(uuid,text,text) TO service_role;

-- Fence older processes as well as current Map: neither a new lease nor a stale
-- callback can replace a retired operation. Preserve recovery history permanently.
CREATE FUNCTION public.guard_upload_manual_takeover() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN
 IF OLD.data->'upload_operation'->'sync_map'->'manual_takeover' IS NOT NULL THEN
   IF TG_OP='DELETE' THEN
     RAISE EXCEPTION 'This upload was retired by explicit manual PSD mapping';
   END IF;
   IF NEW.data->'upload_operation' IS DISTINCT FROM OLD.data->'upload_operation'
      OR NEW.data->'source' IS DISTINCT FROM OLD.data->'source' OR NEW.mode IS DISTINCT FROM OLD.mode THEN
     RAISE EXCEPTION 'This upload was retired by explicit manual PSD mapping';
   END IF;
 END IF;
 RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
END;
$$;
REVOKE ALL ON FUNCTION public.guard_upload_manual_takeover() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.guard_upload_manual_takeover() TO service_role;
CREATE TRIGGER upload_manual_takeover_terminal BEFORE UPDATE OR DELETE ON public.product_upload_intakes
 FOR EACH ROW EXECUTE FUNCTION public.guard_upload_manual_takeover();
COMMIT;
