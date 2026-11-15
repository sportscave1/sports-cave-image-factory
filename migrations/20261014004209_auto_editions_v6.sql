-- Additive Auto Editions V6 records. Applied explicitly; never by application startup.
-- Existing PSD mappings, edition allocations and certificates are untouched.
CREATE TABLE public.auto_edition_jobs (
    id text PRIMARY KEY CHECK (id ~ '^[a-f0-9]{64}$'),
    payload jsonb NOT NULL,
    actor_id text NOT NULL,
    status text NOT NULL DEFAULT 'Queued' CHECK (status IN ('Queued','Generating','Ready','Blocked')),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts BETWEEN 0 AND 3),
    lease_token uuid,
    lease_until timestamptz,
    error_code text,
    result jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX auto_edition_jobs_claim ON public.auto_edition_jobs(status,created_at);
CREATE TABLE public.auto_edition_job_audit (
    id bigserial PRIMARY KEY,
    job_id text NOT NULL REFERENCES public.auto_edition_jobs(id),
    actor_id text NOT NULL,
    event text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.auto_edition_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.auto_edition_job_audit ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.auto_edition_jobs,public.auto_edition_job_audit FROM PUBLIC,anon,authenticated;
REVOKE ALL ON SEQUENCE public.auto_edition_job_audit_id_seq FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON public.auto_edition_jobs TO service_role;
GRANT SELECT,INSERT ON public.auto_edition_job_audit TO service_role;
GRANT USAGE,SELECT ON SEQUENCE public.auto_edition_job_audit_id_seq TO service_role;

CREATE TABLE public.auto_edition_preparations (
    hash text PRIMARY KEY CHECK(hash ~ '^[a-f0-9]{64}$'),
    manifest jsonb NOT NULL,
    proofs jsonb NOT NULL,
    receipts jsonb NOT NULL,
    created_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE public.auto_edition_layouts (
    product_gid text NOT NULL,
    variant_id text NOT NULL,
    preparation_hash text NOT NULL REFERENCES public.auto_edition_preparations(hash),
    approval jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(product_gid,variant_id)
);
CREATE TABLE public.auto_edition_setup_audit (
    id bigserial PRIMARY KEY,
    actor_id text NOT NULL,
    preparation_hash text NOT NULL REFERENCES public.auto_edition_preparations(hash),
    event text NOT NULL,
    detail jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.auto_edition_preparations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.auto_edition_layouts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.auto_edition_setup_audit ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.auto_edition_preparations,public.auto_edition_layouts,public.auto_edition_setup_audit FROM PUBLIC,anon,authenticated;
REVOKE ALL ON SEQUENCE public.auto_edition_setup_audit_id_seq FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT ON public.auto_edition_preparations,public.auto_edition_setup_audit TO service_role;
GRANT SELECT,INSERT,UPDATE ON public.auto_edition_layouts TO service_role;
GRANT USAGE,SELECT ON SEQUENCE public.auto_edition_setup_audit_id_seq TO service_role;
