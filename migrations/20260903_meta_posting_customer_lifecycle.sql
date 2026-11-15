-- Customer lifecycle is request/audit state for one Posting run.
-- Existing Meta objects and historical Posting rows are not rewritten.
ALTER TABLE meta_posting_submissions
    ADD COLUMN IF NOT EXISTS requested_lifecycle_strategy TEXT,
    ADD COLUMN IF NOT EXISTS verified_lifecycle_strategy TEXT NOT NULL DEFAULT 'UNKNOWN',
    ADD COLUMN IF NOT EXISTS lifecycle_verification_source TEXT NOT NULL DEFAULT '';

ALTER TABLE meta_posting_submissions
    DROP CONSTRAINT IF EXISTS meta_posting_submissions_requested_lifecycle_check,
    DROP CONSTRAINT IF EXISTS meta_posting_submissions_verified_lifecycle_check;

ALTER TABLE meta_posting_submissions
    ADD CONSTRAINT meta_posting_submissions_requested_lifecycle_check
        CHECK (
            requested_lifecycle_strategy IS NULL
            OR requested_lifecycle_strategy IN ('ALL_AUDIENCES', 'ACQUIRE_NEW_CUSTOMERS')
        ),
    ADD CONSTRAINT meta_posting_submissions_verified_lifecycle_check
        CHECK (
            verified_lifecycle_strategy IN (
                'ALL_AUDIENCES', 'ACQUIRE_NEW_CUSTOMERS', 'UNKNOWN'
            )
        );

COMMENT ON COLUMN meta_posting_submissions.requested_lifecycle_strategy IS
    'Explicit lifecycle strategy selected for a NEW Posting run; NULL for an inherited existing Ad Set.';

COMMENT ON COLUMN meta_posting_submissions.verified_lifecycle_strategy IS
    'Sanitized three-state lifecycle classification from Meta Graph read-back.';

COMMENT ON COLUMN meta_posting_submissions.lifecycle_verification_source IS
    'Safe description of the Graph evidence used for lifecycle verification; never contains credentials.';
