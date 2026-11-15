ALTER TABLE meta_posting_submissions
    ALTER COLUMN campaign_id DROP NOT NULL,
    ALTER COLUMN adset_id DROP NOT NULL;

ALTER TABLE meta_posting_submissions
    ADD COLUMN IF NOT EXISTS product_id TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS product_title TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS product_handle TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS country TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS sport TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS catalog_id TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS catalog_name TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS product_set_id TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS product_set_name TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS audience_type TEXT NOT NULL DEFAULT 'broad',
    ADD COLUMN IF NOT EXISTS audience_id TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS audience_name TEXT NOT NULL DEFAULT 'Broad',
    ADD COLUMN IF NOT EXISTS pixel_id TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS pixel_name TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS account_currency TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS meta_page_photo_id TEXT,
    ADD COLUMN IF NOT EXISTS meta_canvas_photo_element_id TEXT,
    ADD COLUMN IF NOT EXISTS meta_canvas_product_element_id TEXT,
    ADD COLUMN IF NOT EXISTS meta_canvas_button_element_id TEXT,
    ADD COLUMN IF NOT EXISTS meta_canvas_footer_element_id TEXT,
    ADD COLUMN IF NOT EXISTS meta_instant_experience_id TEXT;

ALTER TABLE meta_posting_submissions
    DROP CONSTRAINT IF EXISTS meta_posting_submissions_status_check;

ALTER TABLE meta_posting_submissions
    ADD CONSTRAINT meta_posting_submissions_status_check CHECK (status IN (
        'VALIDATING', 'CAMPAIGN_CREATED', 'ADSET_CREATED', 'IMAGE_UPLOADED',
        'PAGE_PHOTO_CREATED', 'INSTANT_EXPERIENCE_CREATED', 'CREATIVE_CREATED',
        'AD_CREATED', 'COMPLETE', 'FAILED', 'AMBIGUOUS'
    ));

CREATE INDEX IF NOT EXISTS idx_meta_posting_fingerprint
ON meta_posting_submissions(request_fingerprint, created_at DESC);
