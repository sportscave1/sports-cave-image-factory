CREATE TABLE IF NOT EXISTS analytics_ga4_report_snapshots (
    id TEXT NOT NULL,
    workspace_key TEXT NOT NULL REFERENCES seo_google_connections(workspace_key),
    property_id TEXT NOT NULL,
    contract_key TEXT NOT NULL,
    request_hash CHAR(64) NOT NULL,
    request_spec JSONB NOT NULL DEFAULT '{}'::jsonb,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    property_timezone TEXT NOT NULL DEFAULT '',
    property_currency TEXT NOT NULL DEFAULT '',
    response_rows JSONB NOT NULL DEFAULT '[]'::jsonb,
    response_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    quality_status TEXT NOT NULL DEFAULT 'Unavailable',
    row_count BIGINT NOT NULL DEFAULT 0,
    expected_row_count BIGINT NOT NULL DEFAULT 0,
    pagination_complete BOOLEAN NOT NULL DEFAULT FALSE,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_key, property_id, request_hash)
);

CREATE INDEX IF NOT EXISTS idx_analytics_ga4_contract_range
    ON analytics_ga4_report_snapshots(
        workspace_key, property_id, contract_key, start_date, end_date, fetched_at DESC
    );

CREATE TABLE IF NOT EXISTS analytics_ga4_sync_failures (
    id TEXT PRIMARY KEY,
    workspace_key TEXT NOT NULL REFERENCES seo_google_connections(workspace_key),
    property_id TEXT NOT NULL,
    contract_key TEXT NOT NULL,
    request_hash CHAR(64) NOT NULL,
    error_code TEXT NOT NULL DEFAULT '',
    error_summary TEXT NOT NULL DEFAULT '',
    failed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_analytics_ga4_failures
    ON analytics_ga4_sync_failures(workspace_key, property_id, contract_key, failed_at DESC);

CREATE TABLE IF NOT EXISTS analytics_ga4_report_queue (
    id TEXT PRIMARY KEY,
    workspace_key TEXT NOT NULL REFERENCES seo_google_connections(workspace_key),
    property_id TEXT NOT NULL,
    contract_key TEXT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    property_currency TEXT NOT NULL DEFAULT '',
    requested_by TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'queued',
    error_summary TEXT NOT NULL DEFAULT '',
    requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    UNIQUE (workspace_key, property_id, contract_key, start_date, end_date)
);

CREATE INDEX IF NOT EXISTS idx_analytics_ga4_queue_status
    ON analytics_ga4_report_queue(workspace_key, status, requested_at);

CREATE TABLE IF NOT EXISTS seo_gsc_property_totals_v2 (
    workspace_key TEXT NOT NULL REFERENCES seo_google_connections(workspace_key),
    property_id TEXT NOT NULL,
    source_date DATE NOT NULL,
    search_type TEXT NOT NULL DEFAULT 'web',
    aggregation_type TEXT NOT NULL DEFAULT 'property',
    data_state TEXT NOT NULL DEFAULT 'final',
    clicks NUMERIC(20,6) NOT NULL DEFAULT 0,
    impressions NUMERIC(20,6) NOT NULL DEFAULT 0,
    ctr NUMERIC(20,10) NOT NULL DEFAULT 0,
    average_position NUMERIC(20,10) NOT NULL DEFAULT 0,
    is_complete BOOLEAN NOT NULL DEFAULT TRUE,
    is_truncated BOOLEAN NOT NULL DEFAULT FALSE,
    row_count BIGINT NOT NULL DEFAULT 0,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_key, property_id, source_date, search_type, data_state)
);

CREATE TABLE IF NOT EXISTS seo_gsc_query_daily_v2 (
    workspace_key TEXT NOT NULL REFERENCES seo_google_connections(workspace_key),
    property_id TEXT NOT NULL,
    source_date DATE NOT NULL,
    search_type TEXT NOT NULL DEFAULT 'web',
    data_state TEXT NOT NULL DEFAULT 'final',
    query_hash CHAR(64) NOT NULL,
    raw_query TEXT NOT NULL DEFAULT '',
    normalized_query TEXT NOT NULL DEFAULT '',
    country_code TEXT NOT NULL DEFAULT '',
    device TEXT NOT NULL DEFAULT '',
    clicks NUMERIC(20,6) NOT NULL DEFAULT 0,
    impressions NUMERIC(20,6) NOT NULL DEFAULT 0,
    position_weight NUMERIC(24,10) NOT NULL DEFAULT 0,
    is_complete BOOLEAN NOT NULL DEFAULT TRUE,
    is_truncated BOOLEAN NOT NULL DEFAULT FALSE,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (
        workspace_key, property_id, source_date, search_type, data_state,
        query_hash, country_code, device
    )
);

CREATE INDEX IF NOT EXISTS idx_seo_gsc_query_v2_filters
    ON seo_gsc_query_daily_v2(
        workspace_key, property_id, source_date, search_type, country_code, device, normalized_query
    );

CREATE TABLE IF NOT EXISTS seo_gsc_page_daily_v2 (
    workspace_key TEXT NOT NULL REFERENCES seo_google_connections(workspace_key),
    property_id TEXT NOT NULL,
    source_date DATE NOT NULL,
    search_type TEXT NOT NULL DEFAULT 'web',
    data_state TEXT NOT NULL DEFAULT 'final',
    page_hash CHAR(64) NOT NULL,
    page_url TEXT NOT NULL DEFAULT '',
    country_code TEXT NOT NULL DEFAULT '',
    device TEXT NOT NULL DEFAULT '',
    clicks NUMERIC(20,6) NOT NULL DEFAULT 0,
    impressions NUMERIC(20,6) NOT NULL DEFAULT 0,
    position_weight NUMERIC(24,10) NOT NULL DEFAULT 0,
    is_complete BOOLEAN NOT NULL DEFAULT TRUE,
    is_truncated BOOLEAN NOT NULL DEFAULT FALSE,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (
        workspace_key, property_id, source_date, search_type, data_state,
        page_hash, country_code, device
    )
);

CREATE INDEX IF NOT EXISTS idx_seo_gsc_page_v2_filters
    ON seo_gsc_page_daily_v2(
        workspace_key, property_id, source_date, search_type, country_code, device, page_hash
    );

CREATE TABLE IF NOT EXISTS seo_gsc_query_page_daily_v2 (
    workspace_key TEXT NOT NULL REFERENCES seo_google_connections(workspace_key),
    property_id TEXT NOT NULL,
    source_date DATE NOT NULL,
    search_type TEXT NOT NULL DEFAULT 'web',
    data_state TEXT NOT NULL DEFAULT 'final',
    query_hash CHAR(64) NOT NULL,
    page_hash CHAR(64) NOT NULL,
    raw_query TEXT NOT NULL DEFAULT '',
    page_url TEXT NOT NULL DEFAULT '',
    clicks NUMERIC(20,6) NOT NULL DEFAULT 0,
    impressions NUMERIC(20,6) NOT NULL DEFAULT 0,
    position_weight NUMERIC(24,10) NOT NULL DEFAULT 0,
    is_complete BOOLEAN NOT NULL DEFAULT TRUE,
    is_truncated BOOLEAN NOT NULL DEFAULT FALSE,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (
        workspace_key, property_id, source_date, search_type, data_state, query_hash, page_hash
    )
);

CREATE INDEX IF NOT EXISTS idx_seo_gsc_query_page_v2
    ON seo_gsc_query_page_daily_v2(workspace_key, property_id, source_date, query_hash, page_hash);

CREATE TABLE IF NOT EXISTS seo_gsc_search_appearance_daily_v2 (
    workspace_key TEXT NOT NULL REFERENCES seo_google_connections(workspace_key),
    property_id TEXT NOT NULL,
    source_date DATE NOT NULL,
    search_type TEXT NOT NULL DEFAULT 'web',
    data_state TEXT NOT NULL DEFAULT 'final',
    appearance TEXT NOT NULL DEFAULT '',
    clicks NUMERIC(20,6) NOT NULL DEFAULT 0,
    impressions NUMERIC(20,6) NOT NULL DEFAULT 0,
    position_weight NUMERIC(24,10) NOT NULL DEFAULT 0,
    is_complete BOOLEAN NOT NULL DEFAULT TRUE,
    is_truncated BOOLEAN NOT NULL DEFAULT FALSE,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_key, property_id, source_date, search_type, data_state, appearance)
);

CREATE TABLE IF NOT EXISTS seo_blog_projects_v2 (
    project_id TEXT PRIMARY KEY,
    workspace_key TEXT NOT NULL REFERENCES seo_google_connections(workspace_key),
    owner_id TEXT NOT NULL DEFAULT '',
    owner_name TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'Idea',
    title TEXT NOT NULL DEFAULT '',
    primary_keyword TEXT NOT NULL DEFAULT '',
    target_url TEXT NOT NULL DEFAULT '',
    brief JSONB NOT NULL DEFAULT '{}'::jsonb,
    opportunity_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    prompt_1 TEXT NOT NULL DEFAULT '',
    prompt_1_hash CHAR(64) NOT NULL DEFAULT '',
    content_package JSONB NOT NULL DEFAULT '{}'::jsonb,
    image_manifest JSONB NOT NULL DEFAULT '[]'::jsonb,
    prompt_2 TEXT NOT NULL DEFAULT '',
    prompt_2_hash CHAR(64) NOT NULL DEFAULT '',
    shopify_article_id TEXT NOT NULL DEFAULT '',
    shopify_handle TEXT NOT NULL DEFAULT '',
    draft_url TEXT NOT NULL DEFAULT '',
    live_url TEXT NOT NULL DEFAULT '',
    qa_results JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_error TEXT NOT NULL DEFAULT '',
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_seo_blog_projects_owner_status
    ON seo_blog_projects_v2(workspace_key, owner_id, status, updated_at DESC);

CREATE TABLE IF NOT EXISTS seo_blog_project_events_v2 (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES seo_blog_projects_v2(project_id),
    actor_id TEXT NOT NULL DEFAULT '',
    actor_name TEXT NOT NULL DEFAULT '',
    action_type TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    safe_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (project_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS seo_technical_url_audits_v2 (
    workspace_key TEXT NOT NULL REFERENCES seo_google_connections(workspace_key),
    canonical_url TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT '',
    severity TEXT NOT NULL DEFAULT 'Info',
    issue_code TEXT NOT NULL DEFAULT '',
    issue_summary TEXT NOT NULL DEFAULT '',
    correction_steps TEXT NOT NULL DEFAULT '',
    likely_impact TEXT NOT NULL DEFAULT '',
    affected_urls JSONB NOT NULL DEFAULT '[]'::jsonb,
    http_status INTEGER,
    redirect_url TEXT NOT NULL DEFAULT '',
    robots_state TEXT NOT NULL DEFAULT '',
    index_state TEXT NOT NULL DEFAULT '',
    coverage_state TEXT NOT NULL DEFAULT '',
    fetch_state TEXT NOT NULL DEFAULT '',
    last_crawl TIMESTAMPTZ,
    google_canonical TEXT NOT NULL DEFAULT '',
    user_canonical TEXT NOT NULL DEFAULT '',
    sitemap JSONB NOT NULL DEFAULT '[]'::jsonb,
    crawler_type TEXT NOT NULL DEFAULT '',
    rich_result_issues JSONB NOT NULL DEFAULT '[]'::jsonb,
    inspection_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    status TEXT NOT NULL DEFAULT 'Open',
    PRIMARY KEY (workspace_key, canonical_url, source, issue_code)
);

ALTER TABLE seo_technical_url_audits_v2
    ADD COLUMN IF NOT EXISTS likely_impact TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS affected_urls JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS http_status INTEGER,
    ADD COLUMN IF NOT EXISTS redirect_url TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS robots_state TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS index_state TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS coverage_state TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS fetch_state TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS last_crawl TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS google_canonical TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS user_canonical TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS sitemap JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS crawler_type TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS rich_result_issues JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS checked_at TIMESTAMPTZ NOT NULL DEFAULT now();

CREATE TABLE IF NOT EXISTS seo_technical_recheck_queue_v2 (
    id TEXT PRIMARY KEY,
    workspace_key TEXT NOT NULL REFERENCES seo_google_connections(workspace_key),
    canonical_url TEXT NOT NULL,
    requested_by TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'queued',
    requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    error_summary TEXT NOT NULL DEFAULT ''
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_seo_technical_recheck_active
    ON seo_technical_recheck_queue_v2(workspace_key, canonical_url)
    WHERE status IN ('queued', 'running');

ALTER TABLE analytics_ga4_report_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE analytics_ga4_sync_failures ENABLE ROW LEVEL SECURITY;
ALTER TABLE analytics_ga4_report_queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE seo_gsc_property_totals_v2 ENABLE ROW LEVEL SECURITY;
ALTER TABLE seo_gsc_query_daily_v2 ENABLE ROW LEVEL SECURITY;
ALTER TABLE seo_gsc_page_daily_v2 ENABLE ROW LEVEL SECURITY;
ALTER TABLE seo_gsc_query_page_daily_v2 ENABLE ROW LEVEL SECURITY;
ALTER TABLE seo_gsc_search_appearance_daily_v2 ENABLE ROW LEVEL SECURITY;
ALTER TABLE seo_blog_projects_v2 ENABLE ROW LEVEL SECURITY;
ALTER TABLE seo_blog_project_events_v2 ENABLE ROW LEVEL SECURITY;
ALTER TABLE seo_technical_url_audits_v2 ENABLE ROW LEVEL SECURITY;
ALTER TABLE seo_technical_recheck_queue_v2 ENABLE ROW LEVEL SECURITY;
