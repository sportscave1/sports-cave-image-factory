CREATE TABLE IF NOT EXISTS daily_execution_task_timers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    sheet_id UUID NOT NULL REFERENCES daily_execution_sheets(id) ON DELETE CASCADE,
    task_type TEXT NOT NULL,
    task_index INTEGER NOT NULL,
    allocated_seconds INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'idle',
    started_at TIMESTAMPTZ,
    deadline_at TIMESTAMPTZ,
    paused_at TIMESTAMPTZ,
    remaining_seconds INTEGER,
    halfway_notified_at TIMESTAMPTZ,
    expiry_notified_at TIMESTAMPTZ,
    outcome_required BOOLEAN NOT NULL DEFAULT false,
    outcome TEXT,
    outcome_at TIMESTAMPTZ,
    actual_elapsed_seconds INTEGER,
    stopped_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    version INTEGER NOT NULL DEFAULT 0,
    CHECK (task_type IN ('top', 'additional')),
    CHECK (task_index >= 0),
    CHECK (allocated_seconds >= 0),
    CHECK (status IN ('idle', 'running', 'paused', 'expired', 'stopped', 'completed')),
    CHECK (outcome IS NULL OR outcome IN ('completed', 'did_not_finish'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_daily_task_timers_task
    ON daily_execution_task_timers(sheet_id, task_type, task_index);

CREATE UNIQUE INDEX IF NOT EXISTS idx_daily_task_timers_one_active
    ON daily_execution_task_timers(user_id)
    WHERE status IN ('running', 'paused', 'expired') AND outcome IS NULL;

CREATE INDEX IF NOT EXISTS idx_daily_task_timers_user_updated
    ON daily_execution_task_timers(user_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_daily_task_timers_sheet
    ON daily_execution_task_timers(sheet_id, task_type, task_index);
