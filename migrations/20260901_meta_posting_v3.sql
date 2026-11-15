ALTER TABLE meta_posting_submissions
    ADD COLUMN IF NOT EXISTS ad_results JSONB NOT NULL DEFAULT '[]'::jsonb;
