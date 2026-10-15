-- V16 additive local proposal. Apply only after explicit release approval.
-- No existing mappings, layouts, onboarding, allocations or assets are modified.
CREATE TABLE public.auto_edition_quality_checks (
 preparation_hash text PRIMARY KEY REFERENCES public.auto_edition_preparations(hash),
 product_gid text NOT NULL CHECK(product_gid ~ '^gid://shopify/Product/[1-9][0-9]*$'),
 source jsonb NOT NULL,
 status text NOT NULL CHECK(status IN ('Needs Review','Needs Repair','Failed','Production Ready')),
 assessment jsonb NOT NULL,
 policy_hash text NOT NULL CHECK(policy_hash ~ '^[a-f0-9]{64}$'),
 checked_at timestamptz NOT NULL DEFAULT now(),
 next_check_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX auto_edition_quality_due ON public.auto_edition_quality_checks(next_check_at);
CREATE INDEX auto_edition_quality_product ON public.auto_edition_quality_checks(product_gid);
CREATE TABLE public.auto_edition_quality_audit (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 preparation_hash text NOT NULL REFERENCES public.auto_edition_preparations(hash),
 event text NOT NULL,
 detail jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.auto_edition_quality_checks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.auto_edition_quality_audit ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.auto_edition_quality_checks,public.auto_edition_quality_audit FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT,INSERT,UPDATE ON public.auto_edition_quality_checks TO service_role;
GRANT SELECT,INSERT ON public.auto_edition_quality_audit TO service_role;
GRANT USAGE,SELECT ON SEQUENCE public.auto_edition_quality_audit_id_seq TO service_role;
