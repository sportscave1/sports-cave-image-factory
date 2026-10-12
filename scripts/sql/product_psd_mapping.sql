-- Additive proposal. Apply only after separate owner approval; never run at startup.
CREATE TABLE IF NOT EXISTS public.product_psd_mappings (
    shopify_product_gid text PRIMARY KEY CHECK (shopify_product_gid ~ '^gid://shopify/Product/[1-9][0-9]*$'),
    dropbox_file_id text NOT NULL UNIQUE CHECK (dropbox_file_id ~ '^id:[A-Za-z0-9_-]+$'),
    file_path text NOT NULL CHECK (file_path ~* '^/Sportscave Team Folder/02_TASKS/03_DESIGNS-LIVE-ONLINE-UPLOADED/[^/]+[.]psd$'),
    namespace_path text NOT NULL DEFAULT '',
    source text NOT NULL CHECK (source IN ('automatic','manual')),
    actor_id text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.product_psd_mapping_audit (
    id bigserial PRIMARY KEY,
    shopify_product_gid text NOT NULL,
    action text NOT NULL CHECK (action IN ('automatic','attach','replace')),
    actor_id text NOT NULL,
    before_state jsonb,
    after_state jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.product_psd_mappings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.product_psd_mapping_audit ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.product_psd_mappings, public.product_psd_mapping_audit FROM PUBLIC, anon, authenticated;
REVOKE ALL ON SEQUENCE public.product_psd_mapping_audit_id_seq FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON public.product_psd_mappings TO service_role;
GRANT SELECT, INSERT ON public.product_psd_mapping_audit TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.product_psd_mapping_audit_id_seq TO service_role;
-- No client RLS policy: access is through the existing authenticated server only.
