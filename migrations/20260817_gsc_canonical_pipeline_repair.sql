ALTER TABLE seo_google_connections
    ADD COLUMN IF NOT EXISTS gsc_canonical_property_key TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS gsc_connection_test_status TEXT NOT NULL DEFAULT 'not_tested',
    ADD COLUMN IF NOT EXISTS gsc_connection_tested_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS gsc_connection_test_error_code TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS gsc_connection_test_error_message TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS gsc_connection_permission_level TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS gsc_canonical_sync_status TEXT NOT NULL DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS gsc_canonical_sync_error_code TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS gsc_canonical_sync_error_message TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS gsc_canonical_data_through_date DATE,
    ADD COLUMN IF NOT EXISTS gsc_canonical_synced_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS gsc_canonical_revision BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS gsc_canonical_row_counts JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE seo_gsc_property_totals_v2
    ADD COLUMN IF NOT EXISTS property_key TEXT NOT NULL DEFAULT '';

ALTER TABLE seo_gsc_query_daily_v2
    ADD COLUMN IF NOT EXISTS property_key TEXT NOT NULL DEFAULT '';

ALTER TABLE seo_gsc_page_daily_v2
    ADD COLUMN IF NOT EXISTS property_key TEXT NOT NULL DEFAULT '';

ALTER TABLE seo_gsc_query_page_daily_v2
    ADD COLUMN IF NOT EXISTS property_key TEXT NOT NULL DEFAULT '';

ALTER TABLE seo_gsc_search_appearance_daily_v2
    ADD COLUMN IF NOT EXISTS property_key TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_seo_gsc_totals_v2_canonical_range
    ON seo_gsc_property_totals_v2(
        workspace_key, property_key, search_type, data_state, source_date DESC
    );

CREATE INDEX IF NOT EXISTS idx_seo_gsc_query_v2_canonical_range
    ON seo_gsc_query_daily_v2(
        workspace_key, property_key, search_type, data_state, source_date DESC,
        country_code, device, normalized_query
    );

CREATE INDEX IF NOT EXISTS idx_seo_gsc_page_v2_canonical_range
    ON seo_gsc_page_daily_v2(
        workspace_key, property_key, search_type, data_state, source_date DESC,
        country_code, device, page_hash
    );

CREATE INDEX IF NOT EXISTS idx_seo_gsc_query_page_v2_canonical_range
    ON seo_gsc_query_page_daily_v2(
        workspace_key, property_key, search_type, data_state, source_date DESC,
        query_hash, page_hash
    );

CREATE TABLE IF NOT EXISTS seo_gsc_canonical_date_status (
    workspace_key TEXT NOT NULL REFERENCES seo_google_connections(workspace_key),
    property_id TEXT NOT NULL,
    property_key TEXT NOT NULL,
    source_date DATE NOT NULL,
    search_type TEXT NOT NULL DEFAULT 'web',
    data_state TEXT NOT NULL DEFAULT 'final',
    aggregation_type TEXT NOT NULL DEFAULT '',
    property_total_rows BIGINT NOT NULL DEFAULT 0,
    query_rows BIGINT NOT NULL DEFAULT 0,
    page_rows BIGINT NOT NULL DEFAULT 0,
    query_page_rows BIGINT NOT NULL DEFAULT 0,
    search_appearance_rows BIGINT NOT NULL DEFAULT 0,
    canonical_complete BOOLEAN NOT NULL DEFAULT FALSE,
    source_method TEXT NOT NULL DEFAULT 'api',
    error_code TEXT NOT NULL DEFAULT '',
    error_summary TEXT NOT NULL DEFAULT '',
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_key, property_id, source_date, search_type, data_state)
);

CREATE INDEX IF NOT EXISTS idx_seo_gsc_canonical_status_range
    ON seo_gsc_canonical_date_status(
        workspace_key, property_key, search_type, data_state,
        canonical_complete, source_date DESC
    );

ALTER TABLE seo_gsc_canonical_date_status ENABLE ROW LEVEL SECURITY;
