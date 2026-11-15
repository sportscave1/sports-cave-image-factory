ALTER TABLE seo_google_connections
    ADD COLUMN IF NOT EXISTS gsc_earliest_stored_date DATE,
    ADD COLUMN IF NOT EXISTS ga4_earliest_stored_date DATE,
    ADD COLUMN IF NOT EXISTS ga4_property_timezone TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS ga4_property_currency TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS gsc_import_status TEXT NOT NULL DEFAULT 'not_started',
    ADD COLUMN IF NOT EXISTS ga4_import_status TEXT NOT NULL DEFAULT 'not_started',
    ADD COLUMN IF NOT EXISTS gsc_import_error TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS ga4_import_error TEXT NOT NULL DEFAULT '';

CREATE TABLE IF NOT EXISTS seo_sync_runs (
    id TEXT PRIMARY KEY,
    workspace_key TEXT NOT NULL REFERENCES seo_google_connections(workspace_key),
    source TEXT NOT NULL CHECK (source IN ('GSC', 'GA4', 'Shopify')),
    property_identifier TEXT NOT NULL DEFAULT '',
    mode TEXT NOT NULL CHECK (mode IN ('historical', 'daily', 'manual')),
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'partial', 'failed')),
    requested_start_date DATE,
    requested_end_date DATE,
    completed_start_date DATE,
    completed_end_date DATE,
    active_slice_date DATE,
    checkpoint_date DATE,
    latest_stored_data_date DATE,
    rows_received BIGINT NOT NULL DEFAULT 0,
    rows_inserted BIGINT NOT NULL DEFAULT 0,
    rows_replaced BIGINT NOT NULL DEFAULT 0,
    rows_rejected BIGINT NOT NULL DEFAULT 0,
    requested_by TEXT NOT NULL DEFAULT '',
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    lease_owner TEXT NOT NULL DEFAULT '',
    lease_expires_at TIMESTAMPTZ,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    error_code TEXT NOT NULL DEFAULT '',
    error_summary TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_seo_sync_runs_one_active_source
    ON seo_sync_runs(workspace_key, source)
    WHERE status IN ('queued', 'running');

CREATE INDEX IF NOT EXISTS idx_seo_sync_runs_claim
    ON seo_sync_runs(status, lease_expires_at, created_at);

CREATE INDEX IF NOT EXISTS idx_seo_sync_runs_history
    ON seo_sync_runs(workspace_key, source, created_at DESC);

CREATE TABLE IF NOT EXISTS seo_sync_errors (
    id TEXT PRIMARY KEY,
    sync_run_id TEXT NOT NULL REFERENCES seo_sync_runs(id),
    workspace_key TEXT NOT NULL REFERENCES seo_google_connections(workspace_key),
    source TEXT NOT NULL CHECK (source IN ('GSC', 'GA4', 'Shopify')),
    slice_date DATE,
    error_code TEXT NOT NULL DEFAULT '',
    error_message TEXT NOT NULL DEFAULT '',
    retry_count INTEGER NOT NULL DEFAULT 0,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_seo_sync_errors_run
    ON seo_sync_errors(sync_run_id, slice_date, last_seen_at DESC);

CREATE TABLE IF NOT EXISTS seo_data_inventories (
    workspace_key TEXT NOT NULL REFERENCES seo_google_connections(workspace_key),
    source TEXT NOT NULL CHECK (source IN ('GSC', 'GA4', 'Shopify')),
    property_identifier TEXT NOT NULL,
    rows_stored BIGINT NOT NULL DEFAULT 0,
    earliest_stored_date DATE,
    latest_stored_date DATE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_key, source, property_identifier)
);

CREATE TABLE IF NOT EXISTS seo_gsc_daily_totals (
    workspace_key TEXT NOT NULL REFERENCES seo_google_connections(workspace_key),
    gsc_site_url TEXT NOT NULL,
    date DATE NOT NULL,
    search_type TEXT NOT NULL DEFAULT 'web',
    clicks NUMERIC(20,6) NOT NULL DEFAULT 0,
    impressions NUMERIC(20,6) NOT NULL DEFAULT 0,
    ctr NUMERIC(20,10) NOT NULL DEFAULT 0,
    average_position NUMERIC(20,10) NOT NULL DEFAULT 0,
    is_final BOOLEAN NOT NULL DEFAULT TRUE,
    is_complete BOOLEAN NOT NULL DEFAULT TRUE,
    is_truncated BOOLEAN NOT NULL DEFAULT FALSE,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_key, gsc_site_url, date, search_type)
);

CREATE INDEX IF NOT EXISTS idx_seo_gsc_daily_totals_date
    ON seo_gsc_daily_totals(workspace_key, gsc_site_url, date DESC);

CREATE TABLE IF NOT EXISTS seo_gsc_daily_details (
    workspace_key TEXT NOT NULL REFERENCES seo_google_connections(workspace_key),
    gsc_site_url TEXT NOT NULL,
    date DATE NOT NULL,
    dimension_key_hash CHAR(64) NOT NULL,
    query TEXT NOT NULL DEFAULT '',
    page_url TEXT NOT NULL DEFAULT '',
    country_code TEXT NOT NULL DEFAULT '',
    device TEXT NOT NULL DEFAULT '',
    search_type TEXT NOT NULL DEFAULT 'web',
    clicks NUMERIC(20,6) NOT NULL DEFAULT 0,
    impressions NUMERIC(20,6) NOT NULL DEFAULT 0,
    ctr NUMERIC(20,10) NOT NULL DEFAULT 0,
    average_position NUMERIC(20,10) NOT NULL DEFAULT 0,
    is_final BOOLEAN NOT NULL DEFAULT TRUE,
    is_complete BOOLEAN NOT NULL DEFAULT TRUE,
    is_truncated BOOLEAN NOT NULL DEFAULT FALSE,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_key, gsc_site_url, date, dimension_key_hash)
);

CREATE INDEX IF NOT EXISTS idx_seo_gsc_daily_details_date
    ON seo_gsc_daily_details(workspace_key, gsc_site_url, date DESC);

CREATE INDEX IF NOT EXISTS idx_seo_gsc_daily_details_page
    ON seo_gsc_daily_details(workspace_key, page_url, date DESC);

CREATE TABLE IF NOT EXISTS seo_ga4_daily_landing_pages (
    workspace_key TEXT NOT NULL REFERENCES seo_google_connections(workspace_key),
    ga4_property_id TEXT NOT NULL,
    date DATE NOT NULL,
    dimension_key_hash CHAR(64) NOT NULL,
    landing_page_path_query TEXT NOT NULL DEFAULT '',
    hostname TEXT NOT NULL DEFAULT '',
    country_id TEXT NOT NULL DEFAULT '',
    device_category TEXT NOT NULL DEFAULT '',
    session_channel_group TEXT NOT NULL DEFAULT 'Organic Search',
    sessions NUMERIC(20,6) NOT NULL DEFAULT 0,
    engaged_sessions NUMERIC(20,6) NOT NULL DEFAULT 0,
    engagement_rate NUMERIC(20,10) NOT NULL DEFAULT 0,
    user_engagement_duration NUMERIC(20,6) NOT NULL DEFAULT 0,
    transactions NUMERIC(20,6) NOT NULL DEFAULT 0,
    purchase_revenue NUMERIC(20,6) NOT NULL DEFAULT 0,
    property_currency TEXT NOT NULL DEFAULT '',
    revenue_basis TEXT NOT NULL DEFAULT 'GA4 attributed/unconfirmed',
    is_complete BOOLEAN NOT NULL DEFAULT TRUE,
    is_thresholded BOOLEAN NOT NULL DEFAULT FALSE,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_key, ga4_property_id, date, dimension_key_hash)
);

CREATE INDEX IF NOT EXISTS idx_seo_ga4_daily_landing_pages_date
    ON seo_ga4_daily_landing_pages(workspace_key, ga4_property_id, date DESC);

CREATE INDEX IF NOT EXISTS idx_seo_ga4_daily_landing_pages_path
    ON seo_ga4_daily_landing_pages(workspace_key, landing_page_path_query, date DESC);

CREATE TABLE IF NOT EXISTS seo_shopify_url_mappings (
    id TEXT PRIMARY KEY,
    workspace_key TEXT NOT NULL REFERENCES seo_google_connections(workspace_key),
    canonical_url TEXT NOT NULL,
    shopify_resource_type TEXT NOT NULL DEFAULT '',
    shopify_resource_id TEXT NOT NULL DEFAULT '',
    shopify_handle TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'unmatched',
    created_by TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (workspace_key, canonical_url)
);

CREATE TABLE IF NOT EXISTS seo_opportunities (
    id TEXT PRIMARY KEY,
    workspace_key TEXT NOT NULL REFERENCES seo_google_connections(workspace_key),
    url_mapping_id TEXT REFERENCES seo_shopify_url_mappings(id),
    status TEXT NOT NULL DEFAULT 'draft',
    opportunity_type TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by TEXT NOT NULL DEFAULT '',
    reviewed_by TEXT NOT NULL DEFAULT '',
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS seo_ai_plans (
    id TEXT PRIMARY KEY,
    workspace_key TEXT NOT NULL REFERENCES seo_google_connections(workspace_key),
    opportunity_id TEXT REFERENCES seo_opportunities(id),
    status TEXT NOT NULL DEFAULT 'draft',
    model_name TEXT NOT NULL DEFAULT '',
    prompt_version TEXT NOT NULL DEFAULT '',
    plan_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by TEXT NOT NULL DEFAULT '',
    approved_by TEXT NOT NULL DEFAULT '',
    approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS seo_va_tasks (
    id TEXT PRIMARY KEY,
    workspace_key TEXT NOT NULL REFERENCES seo_google_connections(workspace_key),
    opportunity_id TEXT REFERENCES seo_opportunities(id),
    ai_plan_id TEXT REFERENCES seo_ai_plans(id),
    status TEXT NOT NULL DEFAULT 'draft',
    title TEXT NOT NULL DEFAULT '',
    task_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    approved_by TEXT NOT NULL DEFAULT '',
    approved_at TIMESTAMPTZ,
    assigned_user_id TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS seo_measurement_snapshots (
    id TEXT PRIMARY KEY,
    workspace_key TEXT NOT NULL REFERENCES seo_google_connections(workspace_key),
    opportunity_id TEXT REFERENCES seo_opportunities(id),
    snapshot_date DATE NOT NULL,
    measurement_window TEXT NOT NULL DEFAULT '',
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (workspace_key, opportunity_id, snapshot_date, measurement_window)
);

ALTER TABLE seo_sync_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE seo_sync_errors ENABLE ROW LEVEL SECURITY;
ALTER TABLE seo_data_inventories ENABLE ROW LEVEL SECURITY;
ALTER TABLE seo_gsc_daily_totals ENABLE ROW LEVEL SECURITY;
ALTER TABLE seo_gsc_daily_details ENABLE ROW LEVEL SECURITY;
ALTER TABLE seo_ga4_daily_landing_pages ENABLE ROW LEVEL SECURITY;
ALTER TABLE seo_shopify_url_mappings ENABLE ROW LEVEL SECURITY;
ALTER TABLE seo_opportunities ENABLE ROW LEVEL SECURITY;
ALTER TABLE seo_ai_plans ENABLE ROW LEVEL SECURITY;
ALTER TABLE seo_va_tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE seo_measurement_snapshots ENABLE ROW LEVEL SECURITY;
