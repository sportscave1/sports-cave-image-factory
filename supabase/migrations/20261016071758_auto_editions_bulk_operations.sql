-- Isolated TEST approval operations and derived previews. No allocation or certificate writes.
CREATE TABLE public.auto_edition_review_batches (
 id text PRIMARY KEY, actor_id text NOT NULL, payload_hash text NOT NULL,
 confirmed_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE public.auto_edition_review_jobs (
 id text PRIMARY KEY, product_gid text NOT NULL, preparation_hash text NOT NULL,
 actor_id text NOT NULL, state text NOT NULL DEFAULT 'Pending',
 reason text NOT NULL DEFAULT '', attempts int NOT NULL DEFAULT 0,
 lease_token text, lease_until timestamptz, next_attempt_at timestamptz NOT NULL DEFAULT now(),
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 CHECK(state IN ('Pending','Processing','Approved','Skipped','Needs Attention','Failed'))
);
CREATE UNIQUE INDEX auto_edition_review_active_product ON public.auto_edition_review_jobs(product_gid)
 WHERE state IN ('Pending','Processing');
CREATE INDEX auto_edition_review_due ON public.auto_edition_review_jobs(next_attempt_at,created_at)
 WHERE state IN ('Pending','Processing');
CREATE INDEX auto_edition_review_product_history ON public.auto_edition_review_jobs(product_gid,created_at DESC,id DESC);
CREATE TABLE public.auto_edition_review_items (
 batch_id text NOT NULL REFERENCES public.auto_edition_review_batches(id),
 product_gid text NOT NULL, job_id text NOT NULL REFERENCES public.auto_edition_review_jobs(id),
 PRIMARY KEY(batch_id,product_gid)
);
CREATE INDEX auto_edition_review_items_job ON public.auto_edition_review_items(job_id);
CREATE TABLE public.auto_edition_review_previews (
 identity text PRIMARY KEY, jpeg bytea NOT NULL CHECK(octet_length(jpeg)<=524288),
 created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.auto_edition_review_batches ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.auto_edition_review_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.auto_edition_review_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.auto_edition_review_previews ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.auto_edition_review_batches,public.auto_edition_review_jobs,
 public.auto_edition_review_items,public.auto_edition_review_previews FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON public.auto_edition_review_batches,public.auto_edition_review_jobs,
 public.auto_edition_review_items,public.auto_edition_review_previews TO service_role;
