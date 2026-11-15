CREATE TABLE IF NOT EXISTS seo_technical_audit_runs (
    id text PRIMARY KEY,
    workspace_key text NOT NULL,
    trigger_source text NOT NULL DEFAULT 'background',
    mode text NOT NULL DEFAULT 'daily',
    status text NOT NULL DEFAULT 'starting',
    lease_owner text NOT NULL DEFAULT '',
    lease_expires_at timestamptz,
    lock_state text NOT NULL DEFAULT 'pending',
    pages_scheduled integer NOT NULL DEFAULT 0,
    pages_fetched integer NOT NULL DEFAULT 0,
    head_requests integer NOT NULL DEFAULT 0,
    get_requests integer NOT NULL DEFAULT 0,
    cache_hits integer NOT NULL DEFAULT 0,
    duplicate_urls_skipped integer NOT NULL DEFAULT 0,
    redirects integer NOT NULL DEFAULT 0,
    failed_requests integer NOT NULL DEFAULT 0,
    total_storefront_requests integer NOT NULL DEFAULT 0,
    runtime_seconds double precision NOT NULL DEFAULT 0,
    error_summary text NOT NULL DEFAULT '',
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_seo_technical_audit_runs_workspace_started
    ON seo_technical_audit_runs(workspace_key, started_at DESC);

CREATE TABLE IF NOT EXISTS seo_technical_audit_leases (
    workspace_key text PRIMARY KEY,
    audit_run_id text NOT NULL,
    lease_owner text NOT NULL,
    acquired_at timestamptz NOT NULL DEFAULT now(),
    lease_expires_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_seo_technical_audit_leases_expiry
    ON seo_technical_audit_leases(lease_expires_at);

CREATE TABLE IF NOT EXISTS seo_technical_page_state (
    workspace_key text NOT NULL,
    normalized_url text NOT NULL,
    canonical_url text NOT NULL,
    page_type text NOT NULL DEFAULT '',
    shopify_resource_id text NOT NULL DEFAULT '',
    last_audited_at timestamptz NOT NULL DEFAULT now(),
    last_status integer NOT NULL DEFAULT 0,
    content_fingerprint text NOT NULL DEFAULT '',
    last_technical_result jsonb NOT NULL DEFAULT '[]'::jsonb,
    next_eligible_at timestamptz NOT NULL DEFAULT now(),
    last_audit_run_id text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_key, normalized_url)
);

CREATE INDEX IF NOT EXISTS idx_seo_technical_page_state_eligibility
    ON seo_technical_page_state(workspace_key, next_eligible_at, last_audited_at);
