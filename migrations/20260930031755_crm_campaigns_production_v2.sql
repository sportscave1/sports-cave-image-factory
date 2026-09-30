BEGIN;
-- Reviewed snapshots hold identities/hashes only, never a customer profile mirror.
CREATE TABLE crm_campaign_snapshots (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 campaign_id uuid NOT NULL REFERENCES crm_campaign_drafts(id),
 campaign_version integer NOT NULL, document jsonb NOT NULL, render_settings jsonb NOT NULL,
 counts jsonb NOT NULL, recipients jsonb NOT NULL, schedule jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 CHECK(jsonb_typeof(recipients)='array')
);
CREATE INDEX crm_campaign_snapshots_campaign ON crm_campaign_snapshots(campaign_id,created_at DESC);
ALTER TABLE crm_campaign_snapshots ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON crm_campaign_snapshots FROM PUBLIC,anon,authenticated;
CREATE FUNCTION crm_snapshot_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Reviewed audience snapshots are immutable'; END $$;
REVOKE ALL ON FUNCTION crm_snapshot_immutable() FROM PUBLIC,anon,authenticated;
CREATE TRIGGER crm_snapshot_immutable BEFORE UPDATE OR DELETE ON crm_campaign_snapshots
 FOR EACH ROW EXECUTE FUNCTION crm_snapshot_immutable();

ALTER TABLE crm_campaigns ADD COLUMN audience_snapshot_id uuid REFERENCES crm_campaign_snapshots(id);
ALTER TABLE crm_campaigns ADD COLUMN campaign_key text;
ALTER TABLE crm_campaigns ADD COLUMN campaign_send_id uuid NOT NULL DEFAULT gen_random_uuid();
ALTER TABLE crm_campaigns ADD COLUMN sending_started_at timestamptz;
ALTER TABLE crm_campaigns ADD COLUMN sent_at timestamptz;
ALTER TABLE crm_campaigns ADD COLUMN locked_at timestamptz;
ALTER TABLE crm_campaigns ADD COLUMN final_recipient_count integer;
CREATE UNIQUE INDEX crm_campaign_tracking_key ON crm_campaigns(campaign_key) WHERE campaign_key IS NOT NULL;
CREATE UNIQUE INDEX crm_campaign_send_identity ON crm_campaigns(campaign_send_id);
CREATE INDEX crm_campaign_sent ON crm_campaigns(sent_at DESC) WHERE status='SENT';
-- Existing recipient table already enforces unique (campaign_id,recipient_hash),
-- unique (campaign_id,shopify_customer_id), provider ID and transport idempotency.
CREATE INDEX crm_delivery_events_send_type ON crm_delivery_events(send_id,event_type,occurred_at);
ALTER TABLE crm_delivery_events ADD COLUMN clicked_url text;
ALTER TABLE crm_order_attribution ADD COLUMN campaign_send_id uuid REFERENCES crm_campaigns(campaign_send_id);
ALTER TABLE crm_order_attribution ADD COLUMN order_name text;
ALTER TABLE crm_order_attribution ADD COLUMN customer_id text;
ALTER TABLE crm_order_attribution ADD COLUMN click_at timestamptz;
ALTER TABLE crm_order_attribution ADD COLUMN method text;
ALTER TABLE crm_order_attribution ADD COLUMN source_updated_at timestamptz;
ALTER TABLE crm_order_attribution ADD COLUMN products jsonb NOT NULL DEFAULT '[]';
ALTER TABLE crm_order_attribution ADD COLUMN mirror_status text NOT NULL DEFAULT 'NOT_REQUESTED';
CREATE INDEX crm_attribution_checked ON crm_order_attribution(checked_at,shopify_order_id);
-- Lock the actual persisted source, not just the browser controls. Archive metadata
-- remains editable; analytic counters and lifecycle transitions remain writable.
CREATE FUNCTION crm_production_lock() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_TABLE_NAME='crm_campaigns' THEN
  IF OLD.locked_at IS NOT NULL AND OLD.status='SENT' AND TG_OP='UPDATE'
    AND NEW.status IS DISTINCT FROM OLD.status THEN RAISE EXCEPTION 'Sent campaign cannot be reopened'; END IF;
  IF OLD.locked_at IS NOT NULL AND (TG_OP='DELETE' OR
    ROW(NEW.name,NEW.template_id,NEW.template_version,NEW.audience_snapshot_id,NEW.campaign_key,NEW.campaign_send_id,NEW.segment_definition_id,NEW.shopify_segment_id,NEW.scheduled_at,NEW.locked_at)
    IS DISTINCT FROM ROW(OLD.name,OLD.template_id,OLD.template_version,OLD.audience_snapshot_id,OLD.campaign_key,OLD.campaign_send_id,OLD.segment_definition_id,OLD.shopify_segment_id,OLD.scheduled_at,OLD.locked_at))
  THEN RAISE EXCEPTION 'Production campaign content and audience are locked'; END IF;
 ELSIF TG_TABLE_NAME='crm_campaign_drafts' THEN
  IF EXISTS(SELECT 1 FROM crm_campaigns WHERE id=OLD.id AND locked_at IS NOT NULL)
   AND (TG_OP='DELETE' OR ROW(NEW.name,NEW.document) IS DISTINCT FROM ROW(OLD.name,OLD.document))
  THEN RAISE EXCEPTION 'Production campaign draft is locked'; END IF;
 ELSE
  IF EXISTS(SELECT 1 FROM crm_campaigns WHERE template_id=OLD.template_id AND template_version=OLD.version AND locked_at IS NOT NULL)
  THEN RAISE EXCEPTION 'Production template snapshot is locked'; END IF;
 END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION crm_production_lock() FROM PUBLIC,anon,authenticated;
CREATE TRIGGER crm_production_lock BEFORE UPDATE OR DELETE ON crm_campaigns FOR EACH ROW EXECUTE FUNCTION crm_production_lock();
CREATE TRIGGER crm_production_draft_lock BEFORE UPDATE OR DELETE ON crm_campaign_drafts FOR EACH ROW EXECUTE FUNCTION crm_production_lock();
CREATE TRIGGER crm_production_template_lock BEFORE UPDATE OR DELETE ON crm_template_versions FOR EACH ROW EXECUTE FUNCTION crm_production_lock();
COMMIT;
