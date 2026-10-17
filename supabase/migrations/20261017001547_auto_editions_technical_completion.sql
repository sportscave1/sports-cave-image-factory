-- Isolated technical verification jobs. No artwork approval or customer writes.
CREATE TABLE public.auto_edition_technical_checks (
 product_gid text NOT NULL,
 preparation_hash text NOT NULL REFERENCES public.auto_edition_preparations(hash),
 checkpoint_at timestamptz NOT NULL,
 state text NOT NULL DEFAULT 'Pending' CHECK(state IN ('Pending','Processing','Succeeded','Failed','Superseded')),
 attempts integer NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 3),
 lease_token uuid, lease_until timestamptz,
 retry_at timestamptz NOT NULL DEFAULT now(),
 reason text NOT NULL DEFAULT '',
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(product_gid,preparation_hash,checkpoint_at)
);
CREATE INDEX auto_edition_technical_pending ON public.auto_edition_technical_checks(state,retry_at,created_at);
ALTER TABLE public.auto_edition_technical_checks ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.auto_edition_technical_checks FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON public.auto_edition_technical_checks TO service_role;
