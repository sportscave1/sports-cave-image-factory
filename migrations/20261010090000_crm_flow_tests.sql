-- Dedicated internal tests: no customer, checkout, marketing-send or attribution FK.
CREATE TABLE IF NOT EXISTS crm_flow_tests (
 id uuid PRIMARY KEY, automation_id uuid NOT NULL, actor text NOT NULL,
 recipient text NOT NULL, operation uuid NOT NULL, snapshot jsonb NOT NULL,
 source text NOT NULL CHECK(source IN ('TEST — Draft','TEST — LIVE')),
 created_at timestamptz NOT NULL, cancelled_at timestamptz,
 UNIQUE(actor,operation)
);
CREATE TABLE IF NOT EXISTS crm_flow_test_stages (
 id uuid PRIMARY KEY, test_id uuid NOT NULL REFERENCES crm_flow_tests(id),
 position integer NOT NULL, delay_seconds integer NOT NULL CHECK(delay_seconds>=0),
 message jsonb NOT NULL, status text NOT NULL CHECK(status IN
 ('WAITING','SCHEDULED','SUBMITTED','ACCEPTED','FAILED','CANCELLED')),
 due_at timestamptz, submitted_at timestamptz, accepted_at timestamptz,
 provider_id text, error text, UNIQUE(test_id,position)
);
CREATE INDEX IF NOT EXISTS crm_flow_test_due ON crm_flow_test_stages(due_at)
 WHERE status='SCHEDULED';
CREATE INDEX IF NOT EXISTS crm_flow_test_actor ON crm_flow_tests(actor,created_at);
ALTER TABLE crm_flow_tests ENABLE ROW LEVEL SECURITY;
ALTER TABLE crm_flow_test_stages ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON crm_flow_tests,crm_flow_test_stages FROM PUBLIC;
REVOKE ALL ON crm_flow_tests,crm_flow_test_stages FROM anon,authenticated;
CREATE OR REPLACE FUNCTION crm_flow_test_snapshot_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (NEW.automation_id,NEW.actor,NEW.recipient,NEW.operation,NEW.snapshot,NEW.source,NEW.created_at)
    IS DISTINCT FROM (OLD.automation_id,OLD.actor,OLD.recipient,OLD.operation,OLD.snapshot,OLD.source,OLD.created_at)
 THEN RAISE EXCEPTION 'Test snapshot is immutable'; END IF;
 RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS crm_flow_test_snapshot_guard ON crm_flow_tests;
CREATE TRIGGER crm_flow_test_snapshot_guard BEFORE UPDATE ON crm_flow_tests
 FOR EACH ROW EXECUTE FUNCTION crm_flow_test_snapshot_guard();
CREATE OR REPLACE FUNCTION crm_flow_test_message_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (NEW.test_id,NEW.position,NEW.delay_seconds,NEW.message)
    IS DISTINCT FROM (OLD.test_id,OLD.position,OLD.delay_seconds,OLD.message)
 THEN RAISE EXCEPTION 'Test message and timing are immutable'; END IF;
 RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS crm_flow_test_message_guard ON crm_flow_test_stages;
CREATE TRIGGER crm_flow_test_message_guard BEFORE UPDATE ON crm_flow_test_stages
 FOR EACH ROW EXECUTE FUNCTION crm_flow_test_message_guard();
-- No browser policies: access only through the existing trusted server DB role.
