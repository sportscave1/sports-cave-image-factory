ALTER TABLE seo_sync_runs
    ADD COLUMN IF NOT EXISTS sync_scope TEXT NOT NULL DEFAULT 'full';

CREATE INDEX IF NOT EXISTS idx_seo_sync_runs_scope_status
    ON seo_sync_runs(workspace_key, source, sync_scope, status, created_at);
