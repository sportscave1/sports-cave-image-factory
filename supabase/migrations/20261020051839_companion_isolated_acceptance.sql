-- Private release acceptance only. Search path never falls back to customer rows.
CREATE SCHEMA companion_acceptance_v1;
REVOKE ALL ON SCHEMA companion_acceptance_v1 FROM PUBLIC,anon,authenticated;
GRANT USAGE ON SCHEMA companion_acceptance_v1 TO service_role;
CREATE TABLE companion_acceptance_v1.companion_package_uploads (LIKE public.companion_package_uploads INCLUDING ALL);
ALTER TABLE companion_acceptance_v1.companion_package_uploads ENABLE ROW LEVEL SECURITY;
CREATE TABLE companion_acceptance_v1.runs (
 id text PRIMARY KEY CHECK(id ~ '^[a-f0-9]{32}$'),owner_id text NOT NULL,host_hash text NOT NULL,
 evidence jsonb NOT NULL DEFAULT '{}',created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE companion_acceptance_v1.runs ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON ALL TABLES IN SCHEMA companion_acceptance_v1 FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA companion_acceptance_v1 TO service_role;
