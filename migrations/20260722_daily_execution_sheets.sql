CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS daily_execution_sheets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT,
    user_name TEXT DEFAULT '',
    sheet_date DATE NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'Australia/Sydney',
    status TEXT NOT NULL DEFAULT 'active',
    top_tasks JSONB DEFAULT '[]'::jsonb,
    additional_items JSONB DEFAULT '[]'::jsonb,
    no_grey_zone JSONB DEFAULT '{}'::jsonb,
    ratings JSONB DEFAULT '{}'::jsonb,
    planning_data JSONB DEFAULT '{}'::jsonb,
    review_data JSONB DEFAULT '{}'::jsonb,
    archived_snapshot JSONB DEFAULT '{}'::jsonb,
    daily_summary TEXT DEFAULT '',
    tomorrow_intention TEXT DEFAULT '',
    generated_prompt TEXT DEFAULT '',
    activated_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    archived_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, sheet_date)
);

ALTER TABLE daily_execution_sheets ADD COLUMN IF NOT EXISTS planning_data JSONB DEFAULT '{}'::jsonb;
ALTER TABLE daily_execution_sheets ADD COLUMN IF NOT EXISTS review_data JSONB DEFAULT '{}'::jsonb;
ALTER TABLE daily_execution_sheets ADD COLUMN IF NOT EXISTS archived_snapshot JSONB DEFAULT '{}'::jsonb;
ALTER TABLE daily_execution_sheets ADD COLUMN IF NOT EXISTS activated_at TIMESTAMPTZ;
ALTER TABLE daily_execution_sheets ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_daily_execution_user_date
    ON daily_execution_sheets(user_id, sheet_date DESC);

CREATE INDEX IF NOT EXISTS idx_daily_execution_status_date
    ON daily_execution_sheets(status, sheet_date DESC);
