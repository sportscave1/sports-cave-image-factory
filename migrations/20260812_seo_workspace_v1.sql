CREATE TABLE IF NOT EXISTS seo_workspace_state (
    workspace_key TEXT PRIMARY KEY,
    schema_version INTEGER NOT NULL DEFAULT 1,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_by TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_seo_workspace_state_updated
    ON seo_workspace_state(updated_at DESC);

ALTER TABLE seo_workspace_state ENABLE ROW LEVEL SECURITY;
