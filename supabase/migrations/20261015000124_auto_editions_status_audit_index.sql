-- Additive performance index for the 25-second, product-scoped status snapshot.
-- Explicit release only; never applied by application startup.
CREATE INDEX auto_edition_onboarding_audit_product_latest
    ON public.auto_edition_onboarding_audit(product_gid,created_at DESC,id DESC);
