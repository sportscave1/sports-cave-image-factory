BEGIN;
CREATE OR REPLACE FUNCTION crm_campaign_preparation_lock() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE previous_snapshot crm_campaign_snapshots%ROWTYPE; replacement crm_campaign_snapshots%ROWTYPE;
BEGIN
 IF TG_TABLE_NAME='crm_campaign_preparation' THEN
  IF TG_OP='UPDATE' AND OLD.status='FAILED' AND NEW.status='PREPARING'
    AND current_setting('crm.campaign_recovery_operation',true)=OLD.operation_id::text
    AND NEW.campaign_id=OLD.campaign_id AND NEW.campaign_version=OLD.campaign_version
    AND NEW.operation_id<>OLD.operation_id AND NEW.snapshot_id<>OLD.snapshot_id
    AND NEW.attempts=0 AND NEW.lease_token IS NULL AND NEW.lease_until IS NULL
    AND NOT EXISTS(SELECT 1 FROM crm_campaigns WHERE id=OLD.campaign_id)
    AND NOT EXISTS(SELECT 1 FROM crm_marketing_sends WHERE campaign_id=OLD.campaign_id)
  THEN
   SELECT * INTO previous_snapshot FROM crm_campaign_snapshots WHERE id=OLD.snapshot_id;
   SELECT * INTO replacement FROM crm_campaign_snapshots WHERE id=NEW.snapshot_id;
   IF replacement.campaign_id=OLD.campaign_id AND replacement.campaign_version=OLD.campaign_version
     AND replacement.document-'counts' = previous_snapshot.document-'counts'
     AND previous_snapshot.recipients @> replacement.recipients
     AND jsonb_array_length(replacement.recipients)=NEW.reviewed_count
     AND replacement.created_at>clock_timestamp()-interval '5 minutes'
     AND replacement.counts->>'complete'='true'
     AND NEW.timing=replacement.document->'send_timing'
   THEN RETURN NEW; END IF;
   RAISE EXCEPTION 'Campaign recovery must preserve content and only remove reviewed recipients';
  END IF;
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
COMMIT;
