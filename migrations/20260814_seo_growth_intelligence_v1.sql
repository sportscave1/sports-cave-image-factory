ALTER TABLE seo_url_aliases
    ADD COLUMN IF NOT EXISTS canonical_url TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS page_type TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS shopify_handle TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS mapping_confidence NUMERIC(8,6) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS manual_override BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS manual_override_by TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS manual_override_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_seo_url_aliases_manual_review
    ON seo_url_aliases(workspace_key, mapping_status, manual_override, last_seen_at DESC);

ALTER TABLE seo_revenue_reconciliations
    ADD COLUMN IF NOT EXISTS reconciliation_status TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS match_method TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS match_confidence NUMERIC(8,6) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS matched_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS dispute_reason TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS ga4_attributed_order_count NUMERIC(20,6) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS shopify_confirmed_order_count BIGINT NOT NULL DEFAULT 0;

ALTER TABLE seo_phase4_health
    ADD COLUMN IF NOT EXISTS latest_common_gsc_ga4_date DATE,
    ADD COLUMN IF NOT EXISTS latest_confirmed_revenue_date DATE,
    ADD COLUMN IF NOT EXISTS earliest_historical_date DATE,
    ADD COLUMN IF NOT EXISTS last_successful_joined_refresh_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_failed_joined_refresh_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS joined_refresh_error_code TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS joined_refresh_error_summary TEXT NOT NULL DEFAULT '';

ALTER TABLE seo_reporting_opportunities
    ADD COLUMN IF NOT EXISTS target_keyword TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS keyword_cluster TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS target_market TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS current_page TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS recommended_page TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS current_position NUMERIC(20,10),
    ADD COLUMN IF NOT EXISTS previous_position NUMERIC(20,10),
    ADD COLUMN IF NOT EXISTS impressions NUMERIC(20,6) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS clicks NUMERIC(20,6) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS ctr NUMERIC(20,10),
    ADD COLUMN IF NOT EXISTS sessions NUMERIC(20,6) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS engagement_rate NUMERIC(20,10),
    ADD COLUMN IF NOT EXISTS orders_evidence NUMERIC(20,6) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS revenue_evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS recommended_action TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS deterministic_reason TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS confidence NUMERIC(8,6) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS rule_version TEXT NOT NULL DEFAULT 'phase5-v1',
    ADD COLUMN IF NOT EXISTS detection_start_date DATE,
    ADD COLUMN IF NOT EXISTS detection_end_date DATE,
    ADD COLUMN IF NOT EXISTS first_detected_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_detected_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS dismissed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS snoozed_until DATE;

CREATE INDEX IF NOT EXISTS idx_seo_reporting_opportunities_detail
    ON seo_reporting_opportunities(workspace_key, opportunity_type, target_market, status, measurement_date DESC);

CREATE TABLE IF NOT EXISTS seo_growth_pipeline_runs (
    id TEXT PRIMARY KEY,
    workspace_key TEXT NOT NULL REFERENCES seo_google_connections(workspace_key),
    mode TEXT NOT NULL DEFAULT 'daily',
    status TEXT NOT NULL DEFAULT 'queued',
    requested_by TEXT NOT NULL DEFAULT '',
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    lease_owner TEXT NOT NULL DEFAULT '',
    lease_expires_at TIMESTAMPTZ,
    gsc_data_through_date DATE,
    ga4_data_through_date DATE,
    shopify_data_through_date DATE,
    common_reporting_date DATE,
    confirmed_revenue_through_date DATE,
    error_code TEXT NOT NULL DEFAULT '',
    error_summary TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_seo_growth_pipeline_one_active
    ON seo_growth_pipeline_runs(workspace_key)
    WHERE status IN ('queued', 'running');

CREATE INDEX IF NOT EXISTS idx_seo_growth_pipeline_latest
    ON seo_growth_pipeline_runs(workspace_key, created_at DESC);

CREATE TABLE IF NOT EXISTS seo_growth_pipeline_stages (
    id TEXT PRIMARY KEY,
    pipeline_run_id TEXT NOT NULL REFERENCES seo_growth_pipeline_runs(id),
    workspace_key TEXT NOT NULL REFERENCES seo_google_connections(workspace_key),
    stage_key TEXT NOT NULL,
    stage_order INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'queued',
    source_status TEXT NOT NULL DEFAULT '',
    data_through_date DATE,
    rows_processed BIGINT NOT NULL DEFAULT 0,
    rows_written BIGINT NOT NULL DEFAULT 0,
    error_code TEXT NOT NULL DEFAULT '',
    error_summary TEXT NOT NULL DEFAULT '',
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (pipeline_run_id, stage_key)
);

CREATE INDEX IF NOT EXISTS idx_seo_growth_pipeline_stage_latest
    ON seo_growth_pipeline_stages(workspace_key, stage_order, updated_at DESC);

CREATE TABLE IF NOT EXISTS seo_growth_analysis_snapshots (
    id TEXT PRIMARY KEY,
    workspace_key TEXT NOT NULL REFERENCES seo_google_connections(workspace_key),
    snapshot_version TEXT NOT NULL DEFAULT '',
    prompt_version TEXT NOT NULL DEFAULT '',
    analysis_mode TEXT NOT NULL DEFAULT '',
    filters JSONB NOT NULL DEFAULT '{}'::jsonb,
    data_through DATE,
    source_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    summary_text TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_seo_growth_analysis_snapshots_latest
    ON seo_growth_analysis_snapshots(workspace_key, analysis_mode, created_at DESC);

CREATE TABLE IF NOT EXISTS seo_growth_reports (
    id TEXT PRIMARY KEY,
    workspace_key TEXT NOT NULL REFERENCES seo_google_connections(workspace_key),
    snapshot_id TEXT REFERENCES seo_growth_analysis_snapshots(id),
    report_type TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft',
    model_name TEXT NOT NULL DEFAULT '',
    response_id TEXT NOT NULL DEFAULT '',
    report_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_code TEXT NOT NULL DEFAULT '',
    error_summary TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL DEFAULT '',
    archived_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_seo_growth_reports_latest
    ON seo_growth_reports(workspace_key, report_type, archived_at, created_at DESC);

CREATE TABLE IF NOT EXISTS seo_growth_recommendations (
    id TEXT PRIMARY KEY,
    workspace_key TEXT NOT NULL REFERENCES seo_google_connections(workspace_key),
    report_id TEXT REFERENCES seo_growth_reports(id),
    opportunity_key TEXT REFERENCES seo_reporting_opportunities(opportunity_key),
    status TEXT NOT NULL DEFAULT 'draft',
    target_keyword TEXT NOT NULL DEFAULT '',
    keyword_cluster TEXT NOT NULL DEFAULT '',
    target_market TEXT NOT NULL DEFAULT '',
    current_page TEXT NOT NULL DEFAULT '',
    recommended_page TEXT NOT NULL DEFAULT '',
    current_position NUMERIC(20,10),
    previous_position NUMERIC(20,10),
    impressions NUMERIC(20,6) NOT NULL DEFAULT 0,
    clicks NUMERIC(20,6) NOT NULL DEFAULT 0,
    revenue_or_conversion_evidence TEXT NOT NULL DEFAULT '',
    recommended_action TEXT NOT NULL DEFAULT '',
    priority TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    confidence NUMERIC(8,6) NOT NULL DEFAULT 0,
    measurement_date DATE,
    requires_approval BOOLEAN NOT NULL DEFAULT TRUE,
    proposed_owner TEXT NOT NULL DEFAULT '',
    edited_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    approved_by TEXT NOT NULL DEFAULT '',
    approved_at TIMESTAMPTZ,
    snoozed_until DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_seo_growth_recommendations_status
    ON seo_growth_recommendations(workspace_key, status, priority, updated_at DESC);

CREATE TABLE IF NOT EXISTS seo_growth_tasks (
    id TEXT PRIMARY KEY,
    workspace_key TEXT NOT NULL REFERENCES seo_google_connections(workspace_key),
    recommendation_id TEXT REFERENCES seo_growth_recommendations(id),
    status TEXT NOT NULL DEFAULT 'approved',
    title TEXT NOT NULL DEFAULT '',
    target_keyword TEXT NOT NULL DEFAULT '',
    target_market TEXT NOT NULL DEFAULT '',
    target_page TEXT NOT NULL DEFAULT '',
    recommended_action TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    supporting_evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    completion_requirements TEXT NOT NULL DEFAULT '',
    required_proof TEXT NOT NULL DEFAULT '',
    owner TEXT NOT NULL DEFAULT '',
    due_date DATE,
    approved_by TEXT NOT NULL DEFAULT '',
    approved_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_seo_growth_tasks_status_due
    ON seo_growth_tasks(workspace_key, status, due_date, updated_at DESC);

CREATE TABLE IF NOT EXISTS seo_growth_measurements (
    id TEXT PRIMARY KEY,
    workspace_key TEXT NOT NULL REFERENCES seo_google_connections(workspace_key),
    task_id TEXT REFERENCES seo_growth_tasks(id),
    recommendation_id TEXT REFERENCES seo_growth_recommendations(id),
    window_days INTEGER NOT NULL,
    measurement_status TEXT NOT NULL DEFAULT 'scheduled',
    baseline_date DATE,
    due_date DATE NOT NULL,
    measured_at TIMESTAMPTZ,
    baseline_metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    measurement_metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    change_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    measurement_confidence TEXT NOT NULL DEFAULT '',
    known_limitations TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (workspace_key, task_id, window_days)
);

CREATE INDEX IF NOT EXISTS idx_seo_growth_measurements_due
    ON seo_growth_measurements(workspace_key, measurement_status, due_date);

ALTER TABLE seo_growth_pipeline_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE seo_growth_pipeline_stages ENABLE ROW LEVEL SECURITY;
ALTER TABLE seo_growth_analysis_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE seo_growth_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE seo_growth_recommendations ENABLE ROW LEVEL SECURITY;
ALTER TABLE seo_growth_tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE seo_growth_measurements ENABLE ROW LEVEL SECURITY;
