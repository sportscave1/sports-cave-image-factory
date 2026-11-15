ALTER TABLE seo_phase4_source_state
    ADD COLUMN IF NOT EXISTS rows_processed BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS rows_written BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS rows_rejected BIGINT NOT NULL DEFAULT 0;

ALTER TABLE seo_url_aliases
    ADD COLUMN IF NOT EXISTS source_url TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS shopify_resource_type TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS shopify_resource_id TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS shopify_stable_identifier TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS mapping_method TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS review_reason TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS last_checked_at TIMESTAMPTZ;

ALTER TABLE seo_phase4_health
    ADD COLUMN IF NOT EXISTS mapping_source_url_count BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS mapped_page_count BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS invalid_page_count BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS reconciled_transaction_count BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS confirmed_transaction_count BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS disputed_transaction_count BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS ga4_transaction_through_date DATE,
    ADD COLUMN IF NOT EXISTS reconciliation_through_date DATE,
    ADD COLUMN IF NOT EXISTS reporting_snapshot_refreshed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS health_reason TEXT NOT NULL DEFAULT '';

CREATE TABLE IF NOT EXISTS seo_reporting_snapshot_runs (
    id TEXT PRIMARY KEY,
    workspace_key TEXT NOT NULL REFERENCES seo_google_connections(workspace_key),
    status TEXT NOT NULL CHECK (status IN ('completed', 'failed', 'partial')),
    common_reporting_date DATE,
    gsc_rows BIGINT NOT NULL DEFAULT 0,
    ga4_rows BIGINT NOT NULL DEFAULT 0,
    ga4_transaction_rows BIGINT NOT NULL DEFAULT 0,
    shopify_order_rows BIGINT NOT NULL DEFAULT 0,
    mapped_url_rows BIGINT NOT NULL DEFAULT 0,
    reconciled_transaction_rows BIGINT NOT NULL DEFAULT 0,
    error_code TEXT NOT NULL DEFAULT '',
    error_summary TEXT NOT NULL DEFAULT '',
    refreshed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_seo_reporting_snapshot_runs_latest
    ON seo_reporting_snapshot_runs(workspace_key, refreshed_at DESC);

CREATE TABLE IF NOT EXISTS seo_reporting_daily_metrics (
    workspace_key TEXT NOT NULL REFERENCES seo_google_connections(workspace_key),
    date DATE NOT NULL,
    country_code TEXT NOT NULL DEFAULT '',
    market_code TEXT NOT NULL DEFAULT '',
    device_category TEXT NOT NULL DEFAULT '',
    search_class TEXT NOT NULL DEFAULT 'all',
    organic_clicks NUMERIC(20,6) NOT NULL DEFAULT 0,
    organic_impressions NUMERIC(20,6) NOT NULL DEFAULT 0,
    position_weight NUMERIC(24,10) NOT NULL DEFAULT 0,
    organic_sessions NUMERIC(20,6) NOT NULL DEFAULT 0,
    engaged_sessions NUMERIC(20,6) NOT NULL DEFAULT 0,
    ga4_attributed_purchases NUMERIC(20,6) NOT NULL DEFAULT 0,
    ga4_attributed_revenue NUMERIC(20,6) NOT NULL DEFAULT 0,
    ga4_currency TEXT NOT NULL DEFAULT '',
    source_gsc_rows BIGINT NOT NULL DEFAULT 0,
    source_ga4_rows BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_key, date, country_code, device_category, search_class)
);

CREATE INDEX IF NOT EXISTS idx_seo_reporting_daily_metrics_filters
    ON seo_reporting_daily_metrics(workspace_key, date, market_code, device_category, search_class);

CREATE TABLE IF NOT EXISTS seo_reporting_revenue_daily (
    workspace_key TEXT NOT NULL REFERENCES seo_google_connections(workspace_key),
    date DATE NOT NULL,
    country_code TEXT NOT NULL DEFAULT '',
    market_code TEXT NOT NULL DEFAULT '',
    device_category TEXT NOT NULL DEFAULT '',
    currency TEXT NOT NULL DEFAULT '',
    confirmed_organic_orders BIGINT NOT NULL DEFAULT 0,
    confirmed_organic_revenue NUMERIC(20,6) NOT NULL DEFAULT 0,
    unmatched_or_disputed_transactions BIGINT NOT NULL DEFAULT 0,
    source_reconciliation_rows BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_key, date, country_code, device_category, currency)
);

CREATE INDEX IF NOT EXISTS idx_seo_reporting_revenue_daily_filters
    ON seo_reporting_revenue_daily(workspace_key, date, market_code, device_category, currency);

CREATE TABLE IF NOT EXISTS seo_reporting_landing_page_daily (
    workspace_key TEXT NOT NULL REFERENCES seo_google_connections(workspace_key),
    date DATE NOT NULL,
    canonical_page_key TEXT NOT NULL REFERENCES seo_canonical_pages(page_key),
    country_code TEXT NOT NULL DEFAULT '',
    market_code TEXT NOT NULL DEFAULT '',
    device_category TEXT NOT NULL DEFAULT '',
    organic_clicks NUMERIC(20,6) NOT NULL DEFAULT 0,
    organic_impressions NUMERIC(20,6) NOT NULL DEFAULT 0,
    position_weight NUMERIC(24,10) NOT NULL DEFAULT 0,
    organic_sessions NUMERIC(20,6) NOT NULL DEFAULT 0,
    engaged_sessions NUMERIC(20,6) NOT NULL DEFAULT 0,
    ga4_attributed_purchases NUMERIC(20,6) NOT NULL DEFAULT 0,
    ga4_attributed_revenue NUMERIC(20,6) NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_key, date, canonical_page_key, country_code, device_category)
);

CREATE INDEX IF NOT EXISTS idx_seo_reporting_landing_page_daily_filters
    ON seo_reporting_landing_page_daily(workspace_key, date, market_code, device_category);

CREATE TABLE IF NOT EXISTS seo_reporting_landing_page_revenue_daily (
    workspace_key TEXT NOT NULL REFERENCES seo_google_connections(workspace_key),
    date DATE NOT NULL,
    canonical_page_key TEXT NOT NULL REFERENCES seo_canonical_pages(page_key),
    country_code TEXT NOT NULL DEFAULT '',
    market_code TEXT NOT NULL DEFAULT '',
    device_category TEXT NOT NULL DEFAULT '',
    currency TEXT NOT NULL DEFAULT '',
    confirmed_organic_orders BIGINT NOT NULL DEFAULT 0,
    confirmed_organic_revenue NUMERIC(20,6) NOT NULL DEFAULT 0,
    unmatched_or_disputed_transactions BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_key, date, canonical_page_key, country_code, device_category, currency)
);

CREATE INDEX IF NOT EXISTS idx_seo_reporting_landing_page_revenue_daily_filters
    ON seo_reporting_landing_page_revenue_daily(workspace_key, date, market_code, device_category);

CREATE TABLE IF NOT EXISTS seo_reporting_query_daily (
    workspace_key TEXT NOT NULL REFERENCES seo_google_connections(workspace_key),
    date DATE NOT NULL,
    query_hash TEXT NOT NULL,
    query TEXT NOT NULL DEFAULT '',
    canonical_page_key TEXT NOT NULL DEFAULT '',
    country_code TEXT NOT NULL DEFAULT '',
    market_code TEXT NOT NULL DEFAULT '',
    device_category TEXT NOT NULL DEFAULT '',
    search_class TEXT NOT NULL DEFAULT 'all',
    organic_clicks NUMERIC(20,6) NOT NULL DEFAULT 0,
    organic_impressions NUMERIC(20,6) NOT NULL DEFAULT 0,
    position_weight NUMERIC(24,10) NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_key, date, query_hash, canonical_page_key, country_code, device_category, search_class)
);

CREATE INDEX IF NOT EXISTS idx_seo_reporting_query_daily_filters
    ON seo_reporting_query_daily(workspace_key, date, market_code, device_category, search_class);

CREATE TABLE IF NOT EXISTS seo_reporting_opportunities (
    opportunity_key TEXT PRIMARY KEY,
    workspace_key TEXT NOT NULL REFERENCES seo_google_connections(workspace_key),
    opportunity_type TEXT NOT NULL DEFAULT '',
    priority_score NUMERIC(20,6) NOT NULL DEFAULT 0,
    title TEXT NOT NULL DEFAULT '',
    query TEXT NOT NULL DEFAULT '',
    canonical_page_key TEXT REFERENCES seo_canonical_pages(page_key),
    normalized_path TEXT NOT NULL DEFAULT '',
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'open',
    measurement_date DATE,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_seo_reporting_opportunities_rank
    ON seo_reporting_opportunities(workspace_key, status, priority_score DESC, opportunity_type);

ALTER TABLE seo_reporting_snapshot_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE seo_reporting_daily_metrics ENABLE ROW LEVEL SECURITY;
ALTER TABLE seo_reporting_revenue_daily ENABLE ROW LEVEL SECURITY;
ALTER TABLE seo_reporting_landing_page_daily ENABLE ROW LEVEL SECURITY;
ALTER TABLE seo_reporting_landing_page_revenue_daily ENABLE ROW LEVEL SECURITY;
ALTER TABLE seo_reporting_query_daily ENABLE ROW LEVEL SECURITY;
ALTER TABLE seo_reporting_opportunities ENABLE ROW LEVEL SECURITY;
