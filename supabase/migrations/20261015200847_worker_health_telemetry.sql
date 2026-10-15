-- Explicit additive release only; never installed by application startup.
CREATE TABLE public.auto_edition_worker_heartbeats (
 component text NOT NULL CHECK(component IN ('Render','Companion')),
 instance_id text NOT NULL CHECK(length(instance_id) BETWEEN 1 AND 96),
 seen_at timestamptz NOT NULL DEFAULT now(),
 payload jsonb NOT NULL DEFAULT '{}'::jsonb CHECK(jsonb_typeof(payload)='object' AND octet_length(payload::text)<=4096),
 PRIMARY KEY(component,instance_id)
);
ALTER TABLE public.auto_edition_worker_heartbeats ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.auto_edition_worker_heartbeats FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON public.auto_edition_worker_heartbeats TO service_role;
CREATE INDEX auto_edition_worker_heartbeats_recent ON public.auto_edition_worker_heartbeats(seen_at DESC);
CREATE INDEX auto_edition_worker_diagnostics_recent ON public.auto_edition_onboarding_audit(event,created_at DESC,id DESC);
