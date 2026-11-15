CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS daily_planner_cycles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    overall_objective TEXT NOT NULL DEFAULT '',
    start_date DATE NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'Australia/Sydney',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by TEXT NOT NULL DEFAULT '',
    UNIQUE (user_id, start_date)
);

CREATE TABLE IF NOT EXISTS daily_planner_weekly_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cycle_id UUID NOT NULL REFERENCES daily_planner_cycles(id),
    user_id TEXT NOT NULL,
    week_start DATE NOT NULL,
    week_number INTEGER NOT NULL CHECK (week_number BETWEEN 1 AND 12),
    theme TEXT NOT NULL DEFAULT '',
    quote_text TEXT NOT NULL DEFAULT '',
    quote_author TEXT NOT NULL DEFAULT '',
    review_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    review_submitted_at TIMESTAMPTZ,
    version INTEGER NOT NULL DEFAULT 1,
    last_request_id TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, week_start),
    UNIQUE (cycle_id, week_number)
);

CREATE TABLE IF NOT EXISTS daily_planner_weekly_objectives (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_id UUID NOT NULL REFERENCES daily_planner_weekly_plans(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    position INTEGER NOT NULL CHECK (position BETWEEN 0 AND 2),
    title TEXT NOT NULL DEFAULT '',
    measurable_target TEXT NOT NULL DEFAULT '',
    deadline DATE,
    result TEXT CHECK (result IS NULL OR result IN ('achieved', 'partly_achieved', 'not_achieved')),
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (plan_id, position)
);

CREATE TABLE IF NOT EXISTS daily_planner_weekly_tactics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    objective_id UUID NOT NULL REFERENCES daily_planner_weekly_objectives(id) ON DELETE CASCADE,
    plan_id UUID NOT NULL REFERENCES daily_planner_weekly_plans(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    position INTEGER NOT NULL CHECK (position BETWEEN 0 AND 49),
    action TEXT NOT NULL DEFAULT '',
    due_day INTEGER NOT NULL DEFAULT 0 CHECK (due_day BETWEEN 0 AND 6),
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'completed', 'not_completed')),
    estimated_minutes INTEGER NOT NULL DEFAULT 0 CHECK (estimated_minutes BETWEEN 0 AND 10080),
    linked_sheet_id UUID REFERENCES daily_execution_sheets(id) ON DELETE SET NULL,
    linked_task_type TEXT CHECK (linked_task_type IS NULL OR linked_task_type IN ('top', 'additional')),
    linked_task_index INTEGER CHECK (linked_task_index IS NULL OR linked_task_index >= 0),
    completed_at TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (objective_id, position)
);

CREATE TABLE IF NOT EXISTS daily_planner_monthly_reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cycle_id UUID NOT NULL REFERENCES daily_planner_cycles(id),
    user_id TEXT NOT NULL,
    month_start DATE NOT NULL,
    summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    submitted_at TIMESTAMPTZ,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, cycle_id, month_start)
);

CREATE INDEX IF NOT EXISTS idx_daily_planner_cycles_user_dates
    ON daily_planner_cycles(user_id, start_date DESC);

CREATE INDEX IF NOT EXISTS idx_daily_planner_weekly_plans_user_date
    ON daily_planner_weekly_plans(user_id, week_start DESC);

CREATE INDEX IF NOT EXISTS idx_daily_planner_weekly_objectives_plan
    ON daily_planner_weekly_objectives(plan_id, position)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_daily_planner_weekly_tactics_plan
    ON daily_planner_weekly_tactics(plan_id, objective_id, position)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_daily_planner_weekly_tactics_linked_task
    ON daily_planner_weekly_tactics(linked_sheet_id, linked_task_type, linked_task_index)
    WHERE deleted_at IS NULL AND linked_sheet_id IS NOT NULL;
