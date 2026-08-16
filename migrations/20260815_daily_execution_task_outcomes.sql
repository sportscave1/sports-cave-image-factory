BEGIN;

ALTER TABLE daily_execution_task_timers
    ADD COLUMN IF NOT EXISTS completion_method TEXT,
    ADD COLUMN IF NOT EXISTS skip_reason TEXT,
    ADD COLUMN IF NOT EXISTS completed_before_expiry BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS time_saved_seconds INTEGER;

ALTER TABLE daily_execution_task_timers
    DROP CONSTRAINT IF EXISTS daily_execution_task_timers_outcome_check;

ALTER TABLE daily_execution_task_timers
    ADD CONSTRAINT daily_execution_task_timers_outcome_check
    CHECK (outcome IS NULL OR outcome IN ('completed', 'did_not_finish', 'skipped'));

COMMIT;
