-- Private companion upload journal and durable processing queue. No client role
-- access, customer allocations or source mapping changes.
CREATE TABLE public.companion_package_uploads (
    id text PRIMARY KEY CHECK (id ~ '^[a-f0-9]{64}$'),
    owner_id text NOT NULL,
    host_hash text NOT NULL,
    shop_origin text NOT NULL,
    context jsonb NOT NULL,
    descriptor jsonb NOT NULL,
    state text NOT NULL DEFAULT 'Receiving' CHECK (state IN ('Receiving','Queued','Complete','Blocked','Expired')),
    data jsonb NOT NULL DEFAULT '{}'::jsonb,
    result jsonb,
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts BETWEEN 0 AND 3),
    retry_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL DEFAULT now()+interval '6 days',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX companion_package_uploads_pending ON public.companion_package_uploads(retry_at,created_at) WHERE state='Queued';
CREATE INDEX companion_package_uploads_expiry ON public.companion_package_uploads(expires_at);
ALTER TABLE public.companion_package_uploads ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.companion_package_uploads FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE ON public.companion_package_uploads TO service_role;
