ALTER TABLE daily_execution_sheets
    ADD COLUMN IF NOT EXISTS planning_data JSONB DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS review_data JSONB DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS archived_snapshot JSONB DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS activated_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ;

CREATE UNIQUE INDEX IF NOT EXISTS idx_daily_execution_owner_date
    ON daily_execution_sheets(user_id, sheet_date);

CREATE INDEX IF NOT EXISTS idx_daily_execution_owner_status_date
    ON daily_execution_sheets(user_id, status, sheet_date DESC);
