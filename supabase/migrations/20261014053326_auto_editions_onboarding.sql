-- Product preparation is separate from order rendering. No original tables are changed.
CREATE TABLE public.auto_edition_onboarding (
    product_gid text PRIMARY KEY,
    file_id text NOT NULL,
    source jsonb,
    edition_total integer,
    status text NOT NULL DEFAULT 'Awaiting preparation' CHECK(status IN
      ('Awaiting preparation','Preparing','Needs PSD Repair','Blocked','Cloud Ready')),
    reason text NOT NULL DEFAULT '',
    preparation_hash text REFERENCES public.auto_edition_preparations(hash),
    attempts integer NOT NULL DEFAULT 0,
    priority integer NOT NULL DEFAULT 0 CHECK(priority BETWEEN 0 AND 10),
    lease_token uuid,
    lease_until timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE public.auto_edition_onboarding_audit (
    id bigserial PRIMARY KEY,
    product_gid text NOT NULL,
    actor_id text NOT NULL,
    event text NOT NULL,
    detail jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.auto_edition_onboarding ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.auto_edition_onboarding_audit ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.auto_edition_onboarding,public.auto_edition_onboarding_audit FROM PUBLIC,anon,authenticated;
REVOKE ALL ON SEQUENCE public.auto_edition_onboarding_audit_id_seq FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON public.auto_edition_onboarding TO service_role;
GRANT SELECT,INSERT ON public.auto_edition_onboarding_audit TO service_role;
GRANT USAGE,SELECT ON SEQUENCE public.auto_edition_onboarding_audit_id_seq TO service_role;
CREATE INDEX auto_edition_onboarding_pending ON public.auto_edition_onboarding(status,updated_at);

-- A preparation host receives only short-lived, single-PSD transfer grants.
-- The raw host capability stays encrypted on the authorised Windows computer.
CREATE TABLE public.auto_edition_preparation_hosts (
    token_hash text PRIMARY KEY,
    actor_id text NOT NULL,
    session_version text NOT NULL,
    expires_at timestamptz NOT NULL DEFAULT now()+interval '30 days',
    revoked_at timestamptz,
    last_seen_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.auto_edition_preparation_hosts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.auto_edition_preparation_hosts FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON public.auto_edition_preparation_hosts TO service_role;
