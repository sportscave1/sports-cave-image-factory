-- Additive, covering indexes for the compact reporting model used by SEO pages.
-- No source rows, OAuth state, snapshots, or reporting definitions are modified.
CREATE INDEX IF NOT EXISTS idx_seo_reporting_query_interactive
    ON seo_reporting_query_daily(
        workspace_key, search_class, date, market_code, device_category, query
    )
    INCLUDE (
        query_hash, canonical_page_key, organic_clicks,
        organic_impressions, position_weight
    );

CREATE INDEX IF NOT EXISTS idx_seo_reporting_landing_interactive
    ON seo_reporting_landing_page_daily(
        workspace_key, date, market_code, device_category, canonical_page_key
    )
    INCLUDE (
        organic_clicks, organic_impressions, position_weight,
        organic_sessions, engaged_sessions
    );

CREATE INDEX IF NOT EXISTS idx_seo_reporting_snapshot_last_good
    ON seo_reporting_snapshot_runs(workspace_key, status, refreshed_at DESC)
    INCLUDE (id, common_reporting_date, error_code);
