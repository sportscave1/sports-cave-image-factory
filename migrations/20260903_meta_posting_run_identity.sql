-- submission_id is the durable identity of one intentional Posting campaign run.
-- request_fingerprint remains non-unique content/audit evidence.
ALTER TABLE meta_posting_submissions
    DROP CONSTRAINT IF EXISTS meta_posting_submissions_status_check;

ALTER TABLE meta_posting_submissions
    ADD COLUMN IF NOT EXISTS posting_mode TEXT NOT NULL DEFAULT 'NEW',
    ADD COLUMN IF NOT EXISTS campaign_ownership TEXT NOT NULL DEFAULT 'CREATED_BY_RUN',
    ADD COLUMN IF NOT EXISTS adset_ownership TEXT NOT NULL DEFAULT 'CREATED_BY_RUN',
    ADD COLUMN IF NOT EXISTS campaign_configured_status TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS adset_configured_status TEXT NOT NULL DEFAULT '';

ALTER TABLE meta_posting_submissions
    ADD CONSTRAINT meta_posting_submissions_status_check CHECK (status IN (
        'VALIDATING', 'CAMPAIGN_CREATED', 'ADSET_CREATED', 'IMAGE_UPLOADED',
        'PAGE_PHOTO_CREATED', 'INSTANT_EXPERIENCE_CREATED', 'CREATIVE_CREATED',
        'AD_CREATED', 'COMPLETE', 'FAILED', 'AMBIGUOUS',
        'ABANDONED_EXTERNALLY'
    ));

COMMENT ON COLUMN meta_posting_submissions.submission_id IS
    'Unique identity for one intentional Posting campaign run; never derived from request_fingerprint.';

COMMENT ON COLUMN meta_posting_submissions.request_fingerprint IS
    'Content fingerprint for audit and same-run mutation detection; never a campaign-run identity.';

COMMENT ON COLUMN meta_posting_submissions.posting_mode IS
    'NEW creates a run-owned Campaign/Ad Set; EXISTING targets a selected external Campaign/Ad Set.';

COMMENT ON COLUMN meta_posting_submissions.campaign_ownership IS
    'CREATED_BY_RUN or EXISTING_TARGET; prevents run-owned and externally-owned Meta objects being confused.';

COMMENT ON COLUMN meta_posting_submissions.adset_ownership IS
    'CREATED_BY_RUN or EXISTING_TARGET; existing targets are never mutated by Posting.';

ALTER TABLE meta_posting_submissions
    DROP CONSTRAINT IF EXISTS meta_posting_submissions_posting_mode_check,
    DROP CONSTRAINT IF EXISTS meta_posting_submissions_campaign_ownership_check,
    DROP CONSTRAINT IF EXISTS meta_posting_submissions_adset_ownership_check;

ALTER TABLE meta_posting_submissions
    ADD CONSTRAINT meta_posting_submissions_posting_mode_check
        CHECK (posting_mode IN ('NEW', 'EXISTING')),
    ADD CONSTRAINT meta_posting_submissions_campaign_ownership_check
        CHECK (campaign_ownership IN ('CREATED_BY_RUN', 'EXISTING_TARGET')),
    ADD CONSTRAINT meta_posting_submissions_adset_ownership_check
        CHECK (adset_ownership IN ('CREATED_BY_RUN', 'EXISTING_TARGET'));
