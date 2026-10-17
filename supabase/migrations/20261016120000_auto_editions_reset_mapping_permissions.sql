-- Clear only active associations through the existing authenticated admin reset.
-- Audit/preparation records and all source assets remain retained. No client grants.
GRANT DELETE ON public.product_psd_mappings,public.auto_edition_layouts TO service_role;
