-- One sparse row per design, created only when a manual field is saved.
-- OS accounts are server-authenticated, not Supabase Auth identities.
CREATE TABLE IF NOT EXISTS public.edition_design_tracking (
    edition_product_id BIGINT PRIMARY KEY REFERENCES public.edition_products(id),
    designed_by TEXT NOT NULL DEFAULT '' CHECK (length(designed_by) <= 120),
    bonus_paid_on DATE,
    paid_order_id TEXT,
    paid_order_name TEXT,
    bonus_paid_by UUID REFERENCES public.os_users(id),
    updated_by UUID NOT NULL REFERENCES public.os_users(id),
    version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT design_bonus_order_required CHECK (
        (bonus_paid_on IS NULL AND paid_order_id IS NULL AND paid_order_name IS NULL AND bonus_paid_by IS NULL)
        OR (bonus_paid_on IS NOT NULL AND NULLIF(paid_order_id,'') IS NOT NULL
            AND NULLIF(paid_order_name,'') IS NOT NULL AND bonus_paid_by IS NOT NULL)
    )
);
ALTER TABLE public.edition_design_tracking ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.edition_design_tracking FROM PUBLIC, anon, authenticated;
-- Reuse the existing product_id index and add the canonical-ID counterpart so
-- opening the tracker does not repeatedly scan the allocation ledger.
CREATE INDEX IF NOT EXISTS idx_edition_orders_product_gid
    ON public.edition_orders (shopify_product_gid) WHERE shopify_product_gid IS NOT NULL;
COMMENT ON TABLE public.edition_design_tracking IS
    'Server-only manual VA design attribution and first-sale bonus receipt. App rechecks OS account permissions on every read/write.';
