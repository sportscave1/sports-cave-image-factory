CREATE TABLE IF NOT EXISTS seo_google_connections (
    workspace_key TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL DEFAULT '',
    encrypted_refresh_token TEXT,
    granted_scopes JSONB NOT NULL DEFAULT '[]'::jsonb,
    connection_status TEXT NOT NULL DEFAULT 'Not connected',
    reconnect_required BOOLEAN NOT NULL DEFAULT FALSE,
    gsc_site_url TEXT NOT NULL DEFAULT '',
    gsc_property_name TEXT NOT NULL DEFAULT '',
    ga4_property_id TEXT NOT NULL DEFAULT '',
    ga4_property_name TEXT NOT NULL DEFAULT '',
    available_gsc_properties JSONB NOT NULL DEFAULT '[]'::jsonb,
    available_ga4_properties JSONB NOT NULL DEFAULT '[]'::jsonb,
    properties_checked_at TIMESTAMPTZ,
    last_successful_sync_at TIMESTAMPTZ,
    gsc_data_through_date DATE,
    ga4_data_through_date DATE,
    last_error_code TEXT NOT NULL DEFAULT '',
    last_error_message TEXT NOT NULL DEFAULT '',
    last_error_at TIMESTAMPTZ,
    sync_lock_token TEXT NOT NULL DEFAULT '',
    sync_started_at TIMESTAMPTZ,
    connected_at TIMESTAMPTZ,
    disconnected_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_seo_google_connections_owner
    ON seo_google_connections(owner_user_id);

CREATE INDEX IF NOT EXISTS idx_seo_google_connections_status
    ON seo_google_connections(connection_status, updated_at DESC);

CREATE TABLE IF NOT EXISTS seo_google_oauth_states (
    state_hash TEXT PRIMARY KEY,
    workspace_key TEXT NOT NULL,
    user_id TEXT NOT NULL,
    return_page TEXT NOT NULL DEFAULT 'seo',
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_seo_google_oauth_states_expiry
    ON seo_google_oauth_states(expires_at);

CREATE INDEX IF NOT EXISTS idx_seo_google_oauth_states_user
    ON seo_google_oauth_states(user_id, created_at DESC);

ALTER TABLE seo_google_connections ENABLE ROW LEVEL SECURITY;
ALTER TABLE seo_google_oauth_states ENABLE ROW LEVEL SECURITY;
