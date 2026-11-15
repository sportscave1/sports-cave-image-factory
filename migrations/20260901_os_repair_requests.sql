CREATE TABLE IF NOT EXISTS os_repair_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    section TEXT NOT NULL,
    request_type TEXT NOT NULL DEFAULT 'repair_improvement',
    problem_description TEXT NOT NULL,
    desired_result TEXT NOT NULL,
    scope_choice TEXT NOT NULL,
    scope_notes TEXT NOT NULL DEFAULT '',
    submitted_by TEXT NOT NULL,
    submitted_by_name TEXT NOT NULL DEFAULT '',
    submitted_by_role TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'submitted',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    completed_by TEXT,
    completed_by_name TEXT NOT NULL DEFAULT '',
    admin_notes TEXT NOT NULL DEFAULT '',
    generated_prompt_version TEXT NOT NULL DEFAULT '1',
    CHECK (scope_choice IN ('section_only', 'related_sections', 'not_sure')),
    CHECK (status IN ('submitted', 'complete'))
);

CREATE INDEX IF NOT EXISTS idx_os_repair_requests_created
ON os_repair_requests(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_os_repair_requests_submitter_created
ON os_repair_requests(submitted_by, created_at DESC);
