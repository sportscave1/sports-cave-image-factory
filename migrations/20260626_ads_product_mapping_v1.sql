-- Ads Intelligence Product Mapping V1.
-- Additive only. Does not alter edition/order data or Meta entities.

ALTER TABLE ads_product_mapping ADD COLUMN IF NOT EXISTS mapping_status TEXT DEFAULT 'unmapped';
ALTER TABLE ads_product_mapping ADD COLUMN IF NOT EXISTS suggested_product_handle TEXT;
ALTER TABLE ads_product_mapping ADD COLUMN IF NOT EXISTS suggested_product_title TEXT;
ALTER TABLE ads_product_mapping ADD COLUMN IF NOT EXISTS suggestion_confidence NUMERIC DEFAULT 0;
ALTER TABLE ads_product_mapping ADD COLUMN IF NOT EXISTS suggestion_reason TEXT;
ALTER TABLE ads_product_mapping ADD COLUMN IF NOT EXISTS confirmed_at TIMESTAMPTZ;
ALTER TABLE ads_product_mapping ADD COLUMN IF NOT EXISTS confirmed_by TEXT DEFAULT 'sports_cave_os';

ALTER TABLE meta_creative_tags ADD COLUMN IF NOT EXISTS room_type TEXT;
ALTER TABLE meta_creative_tags ADD COLUMN IF NOT EXISTS hook_style TEXT;
ALTER TABLE meta_creative_tags ADD COLUMN IF NOT EXISTS creative_format TEXT;

CREATE INDEX IF NOT EXISTS idx_ads_product_mapping_ad_id ON ads_product_mapping(ad_id);
CREATE INDEX IF NOT EXISTS idx_ads_product_mapping_product_handle ON ads_product_mapping(product_handle);
CREATE INDEX IF NOT EXISTS idx_ads_product_mapping_status ON ads_product_mapping(mapping_status);
CREATE INDEX IF NOT EXISTS idx_meta_creative_tags_sport ON meta_creative_tags(sport);
CREATE INDEX IF NOT EXISTS idx_meta_creative_tags_country_focus ON meta_creative_tags(country_focus);
