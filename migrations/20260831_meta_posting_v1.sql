CREATE TABLE IF NOT EXISTS meta_posting_submissions (
    submission_id UUID PRIMARY KEY,
    request_fingerprint TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'VALIDATING',
    campaign_id TEXT NOT NULL,
    campaign_name TEXT NOT NULL DEFAULT '',
    adset_id TEXT NOT NULL,
    adset_name TEXT NOT NULL DEFAULT '',
    ad_name TEXT NOT NULL,
    destination_url TEXT NOT NULL,
    image_checksum TEXT NOT NULL,
    meta_image_hash TEXT,
    meta_creative_id TEXT,
    meta_ad_id TEXT,
    meta_status TEXT,
    safe_error TEXT,
    lease_token UUID,
    lease_expires_at TIMESTAMPTZ,
    CHECK (status IN (
        'VALIDATING', 'IMAGE_UPLOADED', 'CREATIVE_CREATED', 'AD_CREATED',
        'COMPLETE', 'FAILED', 'AMBIGUOUS'
    ))
);

CREATE INDEX IF NOT EXISTS idx_meta_posting_created
ON meta_posting_submissions(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_meta_posting_status
ON meta_posting_submissions(status, updated_at DESC);
