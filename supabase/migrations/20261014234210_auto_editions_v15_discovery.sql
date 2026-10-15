-- Local V15 proposal. Apply only in an explicitly approved release.
-- No allocation, source artwork, mapping or approval records are rewritten.
CREATE TABLE public.auto_edition_discovery (
    product_gid text PRIMARY KEY CHECK(product_gid ~ '^gid://shopify/Product/[1-9][0-9]*$'),
    status text NOT NULL DEFAULT 'Waiting for PSD'
      CHECK(status IN ('Waiting for PSD','Needs mapping review','Mapped')),
    reason text NOT NULL DEFAULT '',
    event_id text NOT NULL,
    source_identity jsonb,
    next_check_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX auto_edition_discovery_due ON public.auto_edition_discovery(next_check_at)
    WHERE status <> 'Mapped';
CREATE TABLE public.auto_edition_source_inventory (
    file_id text PRIMARY KEY,
    name_key text NOT NULL,
    path_lower text NOT NULL,
    metadata jsonb NOT NULL
);
CREATE INDEX auto_edition_source_name ON public.auto_edition_source_inventory(name_key);
CREATE INDEX auto_edition_source_path ON public.auto_edition_source_inventory(path_lower);
CREATE TABLE public.auto_edition_discovery_cursor (
    id integer PRIMARY KEY CHECK(id=1),
    cursor text NOT NULL DEFAULT '',
    complete boolean NOT NULL DEFAULT false,
    seed_finished boolean NOT NULL DEFAULT false,
    lease_token uuid,
    lease_until timestamptz,
    next_poll_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO public.auto_edition_discovery_cursor(id) VALUES(1);
ALTER TABLE public.auto_edition_discovery ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.auto_edition_source_inventory ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.auto_edition_discovery_cursor ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.auto_edition_discovery,public.auto_edition_source_inventory,
    public.auto_edition_discovery_cursor FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON public.auto_edition_discovery,
    public.auto_edition_discovery_cursor TO service_role;
GRANT SELECT,INSERT,UPDATE,DELETE ON public.auto_edition_source_inventory TO service_role;
ALTER TABLE public.auto_edition_onboarding ADD COLUMN priority_checked_at timestamptz;
CREATE INDEX auto_edition_priority_due ON public.auto_edition_onboarding(priority_checked_at NULLS FIRST)
    WHERE status='Awaiting preparation';
