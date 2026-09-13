-- Meta Review extends the existing Ads Intelligence read model. No live ad writes.
BEGIN;
CREATE TABLE IF NOT EXISTS meta_review_asset_daily (
    account_id text NOT NULL, ad_id text NOT NULL, date date NOT NULL,
    breakdown text NOT NULL, asset_key text NOT NULL, raw jsonb NOT NULL,
    synced_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(account_id, ad_id, date, breakdown, asset_key)
);
-- Only selected winner reference images are retained here (maximum 8 MiB each).
-- Existing reporting JSON retains Meta URLs/hashes; this small archive survives URL expiry.
CREATE TABLE IF NOT EXISTS meta_review_media (
    sha256 text PRIMARY KEY, content_type text NOT NULL,
    data bytea NOT NULL CHECK(octet_length(data) <= 8388608),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS meta_review_creative_observations (
    account_id text NOT NULL, ad_id text NOT NULL, creative_id text NOT NULL,
    content_hash text NOT NULL, raw jsonb NOT NULL,
    observed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(account_id,ad_id,content_hash)
);
ALTER TABLE meta_review_asset_daily ENABLE ROW LEVEL SECURITY;
ALTER TABLE meta_review_media ENABLE ROW LEVEL SECURITY;
ALTER TABLE meta_review_creative_observations ENABLE ROW LEVEL SECURITY;
-- Access remains through the existing server-side Postgres connection only.
REVOKE ALL ON meta_review_asset_daily, meta_review_media FROM anon, authenticated;
REVOKE ALL ON meta_review_creative_observations FROM anon, authenticated;
CREATE INDEX IF NOT EXISTS meta_review_assets_account_date ON meta_review_asset_daily(account_id,date);
CREATE INDEX IF NOT EXISTS meta_review_action_lookup ON ads_action_log(action_type,created_at DESC);
CREATE INDEX IF NOT EXISTS meta_review_daily_account_date ON meta_ad_insights_daily(account_id,date);
COMMIT;
