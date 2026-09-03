-- Persist the independent Posting Ad Type without rewriting historical runs.
ALTER TABLE meta_posting_submissions
    ADD COLUMN IF NOT EXISTS ad_type TEXT NOT NULL DEFAULT 'Instant Experience';

ALTER TABLE meta_posting_submissions
    DROP CONSTRAINT IF EXISTS meta_posting_submissions_ad_type_check;

ALTER TABLE meta_posting_submissions
    ADD CONSTRAINT meta_posting_submissions_ad_type_check
        CHECK (ad_type IN ('Instant Experience', 'Carousel'));

COMMENT ON COLUMN meta_posting_submissions.ad_type IS
    'Instant Experience uses the immutable template-copy route; Carousel uses the isolated five-card standard website creative path.';
