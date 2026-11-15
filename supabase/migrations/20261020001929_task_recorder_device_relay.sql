-- Recorder-only relay. No edition, Photoshop, customer or worker queue changes.
CREATE SCHEMA IF NOT EXISTS task_recorder_private;
REVOKE ALL ON SCHEMA task_recorder_private FROM PUBLIC;
CREATE TABLE IF NOT EXISTS task_recorder_private.devices (
 id text PRIMARY KEY, owner_id text NOT NULL, key_hash text NOT NULL UNIQUE,
 name text NOT NULL, revoked boolean NOT NULL DEFAULT false,
 last_seen double precision NOT NULL DEFAULT 0, boot_id text NOT NULL DEFAULT '',
 epoch bigint NOT NULL DEFAULT 0, active_run text, needs_review boolean NOT NULL DEFAULT false,
 fence bigint NOT NULL DEFAULT 0, seq bigint NOT NULL DEFAULT 0, state_version bigint NOT NULL DEFAULT 0,
 state jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS recorder_devices_owner ON task_recorder_private.devices(owner_id,revoked);
CREATE TABLE IF NOT EXISTS task_recorder_private.pairings (
 id text PRIMARY KEY, owner_id text NOT NULL, code_hash text NOT NULL UNIQUE,
 expires double precision NOT NULL, device_id text, created double precision NOT NULL
);
CREATE INDEX IF NOT EXISTS recorder_pairing_expiry ON task_recorder_private.pairings(expires);
CREATE TABLE IF NOT EXISTS task_recorder_private.commands (
 id text PRIMARY KEY, device_id text NOT NULL REFERENCES task_recorder_private.devices(id),
 owner_id text NOT NULL, kind text NOT NULL, request_hash text NOT NULL,
 payload jsonb NOT NULL, status text NOT NULL DEFAULT 'queued',
 boot_id text NOT NULL, fence bigint NOT NULL, created double precision NOT NULL,
 expires double precision NOT NULL, receipt jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS recorder_pending ON task_recorder_private.commands(device_id,status,created);
ALTER TABLE task_recorder_private.devices ENABLE ROW LEVEL SECURITY;
ALTER TABLE task_recorder_private.pairings ENABLE ROW LEVEL SECURITY;
ALTER TABLE task_recorder_private.commands ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON ALL TABLES IN SCHEMA task_recorder_private FROM PUBLIC;
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
  REVOKE ALL ON SCHEMA task_recorder_private FROM anon;
  REVOKE ALL ON ALL TABLES IN SCHEMA task_recorder_private FROM anon;
 END IF;
 IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
  REVOKE ALL ON SCHEMA task_recorder_private FROM authenticated;
  REVOKE ALL ON ALL TABLES IN SCHEMA task_recorder_private FROM authenticated;
 END IF;
END $$;
