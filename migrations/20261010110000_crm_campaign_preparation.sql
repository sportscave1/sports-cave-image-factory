BEGIN;
-- Acceptance is not delivery. No recipient work exists until verification commits.
CREATE TABLE crm_campaign_preparation (
 campaign_id uuid PRIMARY KEY REFERENCES crm_campaign_drafts(id),
 operation_id uuid NOT NULL UNIQUE,
 snapshot_id uuid NOT NULL REFERENCES crm_campaign_snapshots(id),
 campaign_version integer NOT NULL,
 actor jsonb NOT NULL,
 reviewed_count integer NOT NULL CHECK(reviewed_count>0),
 timing jsonb NOT NULL,
 status text NOT NULL DEFAULT 'PREPARING' CHECK(status IN ('PREPARING','READY','FAILED')),
 accepted_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 attempts integer NOT NULL DEFAULT 0,
 lease_token uuid, lease_until timestamptz,
 retry_at timestamptz NOT NULL DEFAULT now(),
 error_code text NOT NULL DEFAULT '',
 CHECK((lease_token IS NULL)=(lease_until IS NULL))
);
CREATE INDEX crm_campaign_preparation_pending ON crm_campaign_preparation(retry_at,accepted_at) WHERE status='PREPARING';
ALTER TABLE crm_campaign_preparation ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON crm_campaign_preparation FROM PUBLIC,anon,authenticated;
CREATE FUNCTION crm_campaign_preparation_lock() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_TABLE_NAME='crm_campaign_preparation' THEN
  IF TG_OP='DELETE' OR ROW(NEW.campaign_id,NEW.operation_id,NEW.snapshot_id,NEW.campaign_version,NEW.actor,NEW.reviewed_count,NEW.timing,NEW.accepted_at)
    IS DISTINCT FROM ROW(OLD.campaign_id,OLD.operation_id,OLD.snapshot_id,OLD.campaign_version,OLD.actor,OLD.reviewed_count,OLD.timing,OLD.accepted_at)
    OR (OLD.status IN ('READY','FAILED') AND NEW.status IS DISTINCT FROM OLD.status)
  THEN RAISE EXCEPTION 'Accepted campaign preparation identity is immutable'; END IF;
 ELSE
  IF EXISTS(SELECT 1 FROM crm_campaign_preparation WHERE campaign_id=OLD.id)
   AND (TG_OP='DELETE' OR ROW(NEW.name,NEW.document) IS DISTINCT FROM ROW(OLD.name,OLD.document)
     OR (ROW(NEW.version,NEW.archived_at,NEW.status) IS DISTINCT FROM ROW(OLD.version,OLD.archived_at,OLD.status)
       AND NOT (EXISTS(SELECT 1 FROM crm_campaign_preparation WHERE campaign_id=OLD.id AND status='FAILED')
         OR EXISTS(SELECT 1 FROM crm_campaigns WHERE id=OLD.id AND status='SENT'))))
  THEN RAISE EXCEPTION 'Accepted campaign draft is immutable; duplicate to revise'; END IF;
 END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION crm_campaign_preparation_lock() FROM PUBLIC,anon,authenticated;
CREATE TRIGGER crm_campaign_preparation_lock BEFORE UPDATE OR DELETE ON crm_campaign_preparation FOR EACH ROW EXECUTE FUNCTION crm_campaign_preparation_lock();
CREATE TRIGGER crm_campaign_preparation_draft_lock BEFORE UPDATE OR DELETE ON crm_campaign_drafts FOR EACH ROW EXECUTE FUNCTION crm_campaign_preparation_lock();
-- Fence old UI/server instances as well as stale workers. This adds protection;
-- it does not replace or exempt the existing crm_production_lock.
CREATE FUNCTION crm_campaign_preparation_publish() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE accepted crm_campaign_preparation%ROWTYPE; frozen jsonb; reviewed crm_campaign_snapshots%ROWTYPE;
BEGIN
 SELECT * INTO accepted FROM crm_campaign_preparation WHERE campaign_id=NEW.id FOR UPDATE;
 IF NOT FOUND THEN RETURN NEW; END IF;
 IF accepted.status<>'PREPARING' OR accepted.lease_token IS NULL OR accepted.lease_until<=clock_timestamp()
   OR current_setting('crm.campaign_preparation_token',true) IS DISTINCT FROM accepted.lease_token::text
   OR NEW.audience_snapshot_id IS DISTINCT FROM accepted.snapshot_id
 THEN RAISE EXCEPTION 'Accepted campaign publication requires its current preparation lease'; END IF;
 SELECT content INTO frozen FROM crm_template_versions WHERE template_id=NEW.template_id AND version=NEW.template_version;
 SELECT * INTO reviewed FROM crm_campaign_snapshots WHERE id=accepted.snapshot_id;
 IF frozen->>'operation_id' IS DISTINCT FROM accepted.operation_id::text
   OR frozen->'document' IS DISTINCT FROM reviewed.document
   OR frozen->'render_settings' IS DISTINCT FROM reviewed.render_settings
   OR frozen->'schedule' IS DISTINCT FROM reviewed.schedule
 THEN RAISE EXCEPTION 'Accepted campaign publication must preserve the confirmed snapshot'; END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION crm_campaign_preparation_publish() FROM PUBLIC,anon,authenticated;
CREATE TRIGGER crm_campaign_preparation_publish BEFORE INSERT ON crm_campaigns FOR EACH ROW EXECUTE FUNCTION crm_campaign_preparation_publish();
COMMIT;
