-- Local proposal: deploy this migration before enabling upload MAP.
-- Preserve the main-folder policy; Review PSDs require persisted upload proof.
BEGIN;
ALTER TABLE public.product_psd_mappings DROP CONSTRAINT product_psd_mappings_file_path_check;
ALTER TABLE public.product_psd_mappings ADD CONSTRAINT product_psd_mappings_file_path_check
 CHECK (file_path ~* '^/Sportscave Team Folder/02_TASKS/03_DESIGNS-LIVE-ONLINE-UPLOADED/(99_PSD_NEEDS_REVIEW_DO_NOT_DELETE/)?[^/]+[.]psd$');

CREATE FUNCTION public.verify_upload_psd_mapping() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
BEGIN
  IF NEW.file_path ~* '/99_PSD_NEEDS_REVIEW_DO_NOT_DELETE/' AND NOT EXISTS (
    SELECT 1 FROM public.product_upload_intakes u
    WHERE u.actor_id = NEW.actor_id
      AND u.data->>'product_gid' = NEW.shopify_product_gid
      AND u.data->>'mockups_exported' = 'true'
      AND u.data->'upload_operation'->>'product_id' = NEW.shopify_product_gid
      AND u.data->'upload_operation'->>'binding' IN ('correlation','existing_mapping','operator')
      AND u.data->'upload_operation'->'source'->>'id' = NEW.dropbox_file_id
      AND u.data->'upload_operation'->'source'->>'path_display' = NEW.file_path
      AND u.data->'upload_operation'->'source'->>'rev' ~ '^[a-f0-9]+$'
      AND u.data->'upload_operation'->'source'->>'content_hash' ~ '^[a-f0-9]{64}$'
      AND u.data->'source'->>'id' = NEW.dropbox_file_id
      AND u.data->'source'->>'rev' = u.data->'upload_operation'->'source'->>'rev'
      AND u.data->'source'->>'content_hash' = u.data->'upload_operation'->'source'->>'content_hash'
  ) THEN
    RAISE EXCEPTION 'Review PSD mapping requires verified saved upload identity';
  END IF;
  RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION public.verify_upload_psd_mapping() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.verify_upload_psd_mapping() TO service_role;
CREATE TRIGGER product_upload_verified_psd_mapping
 BEFORE INSERT OR UPDATE ON public.product_psd_mappings
 FOR EACH ROW EXECUTE FUNCTION public.verify_upload_psd_mapping();
COMMIT;
