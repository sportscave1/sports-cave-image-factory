CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGSERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    entity_type TEXT,
    entity_id TEXT,
    shopify_order_id TEXT,
    shopify_line_item_id TEXT,
    shopify_handle TEXT,
    old_value JSONB DEFAULT '{}'::jsonb,
    new_value JSONB DEFAULT '{}'::jsonb,
    reason TEXT,
    actor TEXT DEFAULT 'sports_cave_os',
    source TEXT DEFAULT 'sports_cave_os',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dashboard_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    section TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    completed_by TEXT,
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_dashboard_tasks_status_created
    ON dashboard_tasks(status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_dashboard_tasks_section_status
    ON dashboard_tasks(section, status);

CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at
    ON audit_logs(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_audit_logs_entity
    ON audit_logs(entity_type, entity_id);
