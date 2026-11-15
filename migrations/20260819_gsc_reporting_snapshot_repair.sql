-- Additive repair for the compact GSC reporting read model.
-- Pure Search Console reporting has its own watermark and revision; joined
-- GA4/Shopify reporting may continue to use common_reporting_date.

ALTER TABLE seo_reporting_snapshot_runs
    ADD COLUMN IF NOT EXISTS gsc_reporting_through_date DATE,
    ADD COLUMN IF NOT EXISTS gsc_source_revision BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS trigger_source TEXT NOT NULL DEFAULT 'background',
    ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS daily_metric_rows BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS query_metric_rows BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS page_metric_rows BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS opportunity_rows BIGINT NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_seo_reporting_snapshot_runs_gsc_latest
    ON seo_reporting_snapshot_runs(
        workspace_key, status, gsc_reporting_through_date DESC, refreshed_at DESC
    );

ALTER TABLE seo_phase4_health
    ADD COLUMN IF NOT EXISTS gsc_reporting_through_date DATE,
    ADD COLUMN IF NOT EXISTS gsc_snapshot_source_revision BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS gsc_snapshot_status TEXT NOT NULL DEFAULT 'not_built',
    ADD COLUMN IF NOT EXISTS gsc_snapshot_error_code TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS gsc_snapshot_error_summary TEXT NOT NULL DEFAULT '';

-- GSC landing-page reporting must not depend on a Shopify canonical-page map.
CREATE TABLE IF NOT EXISTS seo_reporting_page_daily (
    workspace_key TEXT NOT NULL REFERENCES seo_google_connections(workspace_key),
    date DATE NOT NULL,
    page_hash TEXT NOT NULL,
    page_url TEXT NOT NULL,
    country_code TEXT NOT NULL DEFAULT '',
    market_code TEXT NOT NULL DEFAULT '',
    device_category TEXT NOT NULL DEFAULT '',
    organic_clicks NUMERIC(20,6) NOT NULL DEFAULT 0,
    organic_impressions NUMERIC(20,6) NOT NULL DEFAULT 0,
    position_weight NUMERIC(24,10) NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (
        workspace_key, date, page_hash, country_code, device_category
    )
);

CREATE INDEX IF NOT EXISTS idx_seo_reporting_page_daily_filters
    ON seo_reporting_page_daily(
        workspace_key, date, market_code, device_category, page_hash
    );

-- Durable, expiring work queue. A dependency is optional: manual repair jobs
-- can wait for their bounded GSC import before rebuilding the read model.
CREATE TABLE IF NOT EXISTS seo_reporting_repair_jobs (
    id TEXT PRIMARY KEY,
    workspace_key TEXT NOT NULL REFERENCES seo_google_connections(workspace_key),
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed')),
    trigger_source TEXT NOT NULL DEFAULT 'background',
    gsc_sync_run_id TEXT,
    requested_by TEXT NOT NULL DEFAULT '',
    requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    lease_owner TEXT NOT NULL DEFAULT '',
    lease_expires_at TIMESTAMPTZ,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    snapshot_run_id TEXT,
    error_code TEXT NOT NULL DEFAULT '',
    error_summary TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE seo_reporting_repair_jobs
    ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now();

CREATE UNIQUE INDEX IF NOT EXISTS idx_seo_reporting_repair_one_active
    ON seo_reporting_repair_jobs(workspace_key)
    WHERE status IN ('queued', 'running');

CREATE INDEX IF NOT EXISTS idx_seo_reporting_repair_claim
    ON seo_reporting_repair_jobs(workspace_key, status, requested_at);

ALTER TABLE seo_reporting_page_daily ENABLE ROW LEVEL SECURITY;
ALTER TABLE seo_reporting_repair_jobs ENABLE ROW LEVEL SECURITY;
