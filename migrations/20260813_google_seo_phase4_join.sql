ALTER TABLE seo_google_connections
    ADD COLUMN IF NOT EXISTS shopify_data_through_date DATE,
    ADD COLUMN IF NOT EXISTS phase4_last_mapping_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS phase4_last_reconciliation_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS phase4_error_code TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS phase4_error_summary TEXT NOT NULL DEFAULT '';

CREATE TABLE IF NOT EXISTS seo_phase4_runs (
    id TEXT PRIMARY KEY,
    workspace_key TEXT NOT NULL REFERENCES seo_google_connections(workspace_key),
    source TEXT NOT NULL CHECK (source IN (
        'shopify_pages', 'shopify_orders', 'ga4_transactions', 'mapping', 'reconciliation'
    )),
    mode TEXT NOT NULL CHECK (mode IN ('historical', 'daily', 'manual')),
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'partial', 'failed')),
    requested_start_date DATE,
    requested_end_date DATE,
    active_slice_date DATE,
    checkpoint_date DATE,
    cursor_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    rows_received BIGINT NOT NULL DEFAULT 0,
    rows_written BIGINT NOT NULL DEFAULT 0,
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

CREATE UNIQUE INDEX IF NOT EXISTS idx_seo_phase4_runs_one_active_source
    ON seo_phase4_runs(workspace_key, source)
    WHERE status IN ('queued', 'running');

CREATE INDEX IF NOT EXISTS idx_seo_phase4_runs_claim
    ON seo_phase4_runs(status, lease_expires_at, created_at);

CREATE TABLE IF NOT EXISTS seo_phase4_source_state (
    workspace_key TEXT NOT NULL REFERENCES seo_google_connections(workspace_key),
    source TEXT NOT NULL,
    resource_type TEXT NOT NULL DEFAULT '',
    checkpoint_value TEXT NOT NULL DEFAULT '',
    cursor_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    latest_completed_date DATE,
    last_success_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'not_started',
    error_code TEXT NOT NULL DEFAULT '',
    error_summary TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_key, source, resource_type)
);

CREATE TABLE IF NOT EXISTS seo_canonical_pages (
    page_key TEXT PRIMARY KEY,
    workspace_key TEXT NOT NULL REFERENCES seo_google_connections(workspace_key),
    canonical_url TEXT NOT NULL,
    normalized_host TEXT NOT NULL,
    normalized_path TEXT NOT NULL,
    locale_prefix TEXT NOT NULL DEFAULT '',
    market_code TEXT NOT NULL DEFAULT '',
    page_type TEXT NOT NULL,
    shopify_resource_id TEXT NOT NULL DEFAULT '',
    shopify_handle TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    resource_status TEXT NOT NULL DEFAULT '',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    source_updated_at TIMESTAMPTZ,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (workspace_key, canonical_url),
    UNIQUE (workspace_key, page_type, shopify_resource_id)
);

CREATE INDEX IF NOT EXISTS idx_seo_canonical_pages_lookup
    ON seo_canonical_pages(workspace_key, normalized_host, normalized_path);

CREATE TABLE IF NOT EXISTS seo_url_aliases (
    alias_key TEXT PRIMARY KEY,
    workspace_key TEXT NOT NULL REFERENCES seo_google_connections(workspace_key),
    source TEXT NOT NULL CHECK (source IN ('GSC', 'GA4', 'Shopify')),
    property_identifier TEXT NOT NULL DEFAULT '',
    raw_url TEXT NOT NULL,
    normalized_url TEXT NOT NULL DEFAULT '',
    normalized_host TEXT NOT NULL DEFAULT '',
    normalized_path TEXT NOT NULL DEFAULT '',
    raw_query_string TEXT NOT NULL DEFAULT '',
    locale_prefix TEXT NOT NULL DEFAULT '',
    market_code TEXT NOT NULL DEFAULT '',
    canonical_page_key TEXT REFERENCES seo_canonical_pages(page_key),
    mapping_status TEXT NOT NULL CHECK (mapping_status IN ('matched', 'unmapped', 'ambiguous', 'invalid')),
    mapping_reason TEXT NOT NULL DEFAULT '',
    candidate_page_keys JSONB NOT NULL DEFAULT '[]'::jsonb,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (workspace_key, source, property_identifier, raw_url)
);

CREATE INDEX IF NOT EXISTS idx_seo_url_aliases_mapping
    ON seo_url_aliases(workspace_key, mapping_status, normalized_host, normalized_path);

ALTER TABLE seo_gsc_daily_details
    ADD COLUMN IF NOT EXISTS canonical_page_key TEXT REFERENCES seo_canonical_pages(page_key),
    ADD COLUMN IF NOT EXISTS mapping_status TEXT NOT NULL DEFAULT 'unmapped';

ALTER TABLE seo_ga4_daily_landing_pages
    ADD COLUMN IF NOT EXISTS canonical_page_key TEXT REFERENCES seo_canonical_pages(page_key),
    ADD COLUMN IF NOT EXISTS mapping_status TEXT NOT NULL DEFAULT 'unmapped';

CREATE INDEX IF NOT EXISTS idx_seo_gsc_daily_details_page_key
    ON seo_gsc_daily_details(workspace_key, canonical_page_key, date);

CREATE INDEX IF NOT EXISTS idx_seo_ga4_daily_landing_pages_page_key
    ON seo_ga4_daily_landing_pages(workspace_key, canonical_page_key, date);

CREATE TABLE IF NOT EXISTS seo_ga4_transactions (
    workspace_key TEXT NOT NULL REFERENCES seo_google_connections(workspace_key),
    ga4_property_id TEXT NOT NULL,
    transaction_id TEXT NOT NULL,
    transaction_date DATE NOT NULL,
    raw_landing_page TEXT NOT NULL DEFAULT '',
    hostname TEXT NOT NULL DEFAULT '',
    normalized_url TEXT NOT NULL DEFAULT '',
    canonical_page_key TEXT REFERENCES seo_canonical_pages(page_key),
    mapping_status TEXT NOT NULL DEFAULT 'unmapped',
    country_id TEXT NOT NULL DEFAULT '',
    device_category TEXT NOT NULL DEFAULT '',
    session_channel_group TEXT NOT NULL DEFAULT 'Organic Search',
    transaction_count NUMERIC(20,6) NOT NULL DEFAULT 0,
    attributed_purchase_revenue NUMERIC(20,6) NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT '',
    conflict_state TEXT NOT NULL DEFAULT '',
    is_complete BOOLEAN NOT NULL DEFAULT TRUE,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_key, ga4_property_id, transaction_id, transaction_date)
);

CREATE INDEX IF NOT EXISTS idx_seo_ga4_transactions_date
    ON seo_ga4_transactions(workspace_key, ga4_property_id, transaction_date);

CREATE TABLE IF NOT EXISTS seo_shopify_order_facts (
    workspace_key TEXT NOT NULL REFERENCES seo_google_connections(workspace_key),
    shopify_order_id TEXT NOT NULL,
    display_order_name TEXT NOT NULL DEFAULT '',
    legacy_resource_id TEXT NOT NULL DEFAULT '',
    order_date DATE NOT NULL,
    financial_status TEXT NOT NULL DEFAULT '',
    is_test BOOLEAN NOT NULL DEFAULT FALSE,
    is_cancelled BOOLEAN NOT NULL DEFAULT FALSE,
    is_fully_refunded BOOLEAN NOT NULL DEFAULT FALSE,
    gross_revenue NUMERIC(20,6) NOT NULL DEFAULT 0,
    refunded_revenue NUMERIC(20,6) NOT NULL DEFAULT 0,
    net_revenue NUMERIC(20,6) NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT '',
    source_updated_at TIMESTAMPTZ,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_key, shopify_order_id)
);

CREATE INDEX IF NOT EXISTS idx_seo_shopify_order_facts_date
    ON seo_shopify_order_facts(workspace_key, order_date, currency);

CREATE TABLE IF NOT EXISTS seo_shopify_order_match_keys (
    workspace_key TEXT NOT NULL REFERENCES seo_google_connections(workspace_key),
    match_key TEXT NOT NULL,
    shopify_order_id TEXT NOT NULL,
    key_type TEXT NOT NULL,
    is_conflicting BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_key, match_key, shopify_order_id),
    FOREIGN KEY (workspace_key, shopify_order_id)
        REFERENCES seo_shopify_order_facts(workspace_key, shopify_order_id)
);

CREATE INDEX IF NOT EXISTS idx_seo_shopify_order_match_keys_lookup
    ON seo_shopify_order_match_keys(workspace_key, match_key, is_conflicting);

CREATE TABLE IF NOT EXISTS seo_revenue_reconciliations (
    workspace_key TEXT NOT NULL REFERENCES seo_google_connections(workspace_key),
    ga4_property_id TEXT NOT NULL,
    transaction_id TEXT NOT NULL,
    transaction_date DATE NOT NULL,
    shopify_order_id TEXT,
    reconciliation_state TEXT NOT NULL CHECK (reconciliation_state IN (
        'confirmed_shopify_match', 'ga4_transaction_unmatched',
        'duplicate_or_conflicting_transaction', 'excluded_test_order',
        'excluded_cancelled_order', 'excluded_fully_refunded_order', 'currency_mismatch'
    )),
    ga4_attributed_revenue NUMERIC(20,6) NOT NULL DEFAULT 0,
    shopify_confirmed_revenue NUMERIC(20,6) NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT '',
    reconciled_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_key, ga4_property_id, transaction_id, transaction_date),
    FOREIGN KEY (workspace_key, ga4_property_id, transaction_id, transaction_date)
        REFERENCES seo_ga4_transactions(workspace_key, ga4_property_id, transaction_id, transaction_date),
    FOREIGN KEY (workspace_key, shopify_order_id)
        REFERENCES seo_shopify_order_facts(workspace_key, shopify_order_id)
);

CREATE INDEX IF NOT EXISTS idx_seo_revenue_reconciliations_state
    ON seo_revenue_reconciliations(workspace_key, reconciliation_state, reconciled_at);

CREATE TABLE IF NOT EXISTS seo_reporting_settings (
    workspace_key TEXT PRIMARY KEY REFERENCES seo_google_connections(workspace_key),
    brand_terms JSONB NOT NULL DEFAULT '[]'::jsonb,
    known_locale_prefixes JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_by TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS seo_phase4_health (
    workspace_key TEXT PRIMARY KEY REFERENCES seo_google_connections(workspace_key),
    latest_gsc_date DATE,
    latest_ga4_date DATE,
    latest_shopify_date DATE,
    common_reporting_date DATE,
    last_mapping_at TIMESTAMPTZ,
    last_reconciliation_at TIMESTAMPTZ,
    unmapped_page_count BIGINT NOT NULL DEFAULT 0,
    unmatched_transaction_count BIGINT NOT NULL DEFAULT 0,
    ambiguous_page_count BIGINT NOT NULL DEFAULT 0,
    data_status TEXT NOT NULL DEFAULT 'not_ready',
    error_summary TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE seo_phase4_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE seo_phase4_source_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE seo_canonical_pages ENABLE ROW LEVEL SECURITY;
ALTER TABLE seo_url_aliases ENABLE ROW LEVEL SECURITY;
ALTER TABLE seo_ga4_transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE seo_shopify_order_facts ENABLE ROW LEVEL SECURITY;
ALTER TABLE seo_shopify_order_match_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE seo_revenue_reconciliations ENABLE ROW LEVEL SECURITY;
ALTER TABLE seo_reporting_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE seo_phase4_health ENABLE ROW LEVEL SECURITY;
