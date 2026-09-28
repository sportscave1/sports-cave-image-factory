-- Local review only; NOT added to the deployment manifest.
-- Isolated authoring records: the legacy worker never reads these tables.
BEGIN;
CREATE TABLE crm_campaign_drafts (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), name text NOT NULL,
 status text NOT NULL DEFAULT 'DRAFT' CHECK(status IN
 ('DRAFT','NEEDS REVIEW','TEST READY','TESTED','COMPLIANCE BLOCKED','CANCELED')),
 document jsonb NOT NULL DEFAULT '{}', version integer NOT NULL DEFAULT 1,
 created_by text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(), archived_at timestamptz,
 last_tested_at timestamptz, last_test_resend_id text, tested_version integer
);
CREATE TABLE crm_campaign_history (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 campaign_id uuid NOT NULL REFERENCES crm_campaign_drafts(id),
 version integer NOT NULL, action text NOT NULL, actor text NOT NULL,
 before_value jsonb NOT NULL DEFAULT '{}', after_value jsonb NOT NULL DEFAULT '{}',
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX crm_campaign_drafts_updated_idx ON crm_campaign_drafts(updated_at DESC) WHERE archived_at IS NULL;
CREATE INDEX crm_campaign_history_campaign_idx ON crm_campaign_history(campaign_id,created_at DESC);
ALTER TABLE crm_campaign_drafts ENABLE ROW LEVEL SECURITY;
ALTER TABLE crm_campaign_history ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON crm_campaign_drafts,crm_campaign_history FROM PUBLIC,anon,authenticated;
REVOKE ALL ON SEQUENCE crm_campaign_history_id_seq FROM PUBLIC,anon,authenticated;
ALTER TABLE crm_suppressions DROP CONSTRAINT crm_suppressions_reason_check;
ALTER TABLE crm_suppressions ADD CONSTRAINT crm_suppressions_reason_check CHECK(reason IN
 ('unsubscribe','bounce','complaint','manual','suppressed','redacted',
 'manual_unsubscribe','provider_unsubscribe','hard_bounce','spam_complaint','invalid_address','admin_suppression'));
ALTER TABLE crm_suppressions ADD COLUMN active boolean NOT NULL DEFAULT true;
ALTER TABLE crm_suppressions ADD COLUMN provider_reference text;
ALTER TABLE crm_suppressions ADD COLUMN campaign_reference uuid REFERENCES crm_campaign_drafts(id);
-- Existing readers conservatively suppress any stored record, even if marked inactive.
-- No campaign code clears suppression records or changes Shopify consent.
COMMIT;
