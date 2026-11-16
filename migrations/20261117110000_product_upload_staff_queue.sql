CREATE TABLE IF NOT EXISTS public.product_upload_desktop (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    actor_id text NOT NULL,
    token_hash text NOT NULL,
    seen_at timestamptz
);

CREATE TABLE IF NOT EXISTS public.product_upload_staff_jobs (
    id uuid PRIMARY KEY,
    source_id text NOT NULL,
    source_rev text NOT NULL,
    title text NOT NULL,
    sport text,
    stage smallint NOT NULL DEFAULT 0 CHECK (stage BETWEEN 0 AND 7),
    worker_actor text,
    intake_id uuid,
    message text NOT NULL DEFAULT '',
    storefront text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_id, source_rev)
);
CREATE UNIQUE INDEX IF NOT EXISTS product_upload_one_active_desktop_job
    ON public.product_upload_staff_jobs ((true)) WHERE stage BETWEEN 1 AND 5;
CREATE INDEX IF NOT EXISTS product_upload_waiting_jobs
    ON public.product_upload_staff_jobs (created_at, id) WHERE stage = 0;

CREATE TABLE IF NOT EXISTS public.product_upload_staff_requests (
    requester text NOT NULL,
    job_id uuid NOT NULL REFERENCES public.product_upload_staff_jobs(id),
    requested_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (requester, job_id)
);

ALTER TABLE public.product_upload_desktop ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.product_upload_staff_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.product_upload_staff_requests ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.product_upload_desktop, public.product_upload_staff_jobs,
    public.product_upload_staff_requests FROM PUBLIC;
DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON public.product_upload_desktop, public.product_upload_staff_jobs,
            public.product_upload_staff_requests FROM anon;
    END IF;
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticated') THEN
        REVOKE ALL ON public.product_upload_desktop, public.product_upload_staff_jobs,
            public.product_upload_staff_requests FROM authenticated;
    END IF;
END $$;
