-- Private application records. No anon/authenticated Data API access.
CREATE TABLE IF NOT EXISTS public.product_upload_intakes (
    id uuid PRIMARY KEY,
    actor_id text NOT NULL,
    mode text NOT NULL CHECK (mode IN ('DRAFT','LIVE','UPDATE')),
    data jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS product_upload_intakes_actor_created
    ON public.product_upload_intakes(actor_id,created_at DESC);
CREATE INDEX IF NOT EXISTS product_upload_intakes_product
    ON public.product_upload_intakes((data->>'product_gid'));
ALTER TABLE public.product_upload_intakes ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.product_upload_intakes FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON public.product_upload_intakes TO service_role;
