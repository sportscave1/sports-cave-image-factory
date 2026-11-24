-- Review media uses revision-pinned Dropbox originals and WebP variants.
ALTER TABLE sc_review_media ADD COLUMN IF NOT EXISTS storage jsonb NOT NULL DEFAULT '{}';
CREATE INDEX IF NOT EXISTS sc_review_rewards_due ON sc_review_rewards(status,created_at);
