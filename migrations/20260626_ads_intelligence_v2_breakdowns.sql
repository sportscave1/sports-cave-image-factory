-- Ads Intelligence V2: separate safe breakdown tables and creative/tag metadata.
-- These are read-model tables for Meta Ads reporting. Meta remains read-only.

CREATE TABLE IF NOT EXISTS meta_ad_insights_country_daily (
    id BIGSERIAL PRIMARY KEY,
    date DATE NOT NULL,
    account_id TEXT,
    campaign_id TEXT,
    campaign_name TEXT,
    adset_id TEXT,
    adset_name TEXT,
    ad_id TEXT NOT NULL,
    ad_name TEXT,
    country TEXT NOT NULL DEFAULT '',
    spend NUMERIC DEFAULT 0,
    impressions INTEGER DEFAULT 0,
    reach INTEGER DEFAULT 0,
    clicks INTEGER DEFAULT 0,
    inline_link_clicks INTEGER DEFAULT 0,
    ctr NUMERIC DEFAULT 0,
    cpc NUMERIC DEFAULT 0,
    cpm NUMERIC DEFAULT 0,
    frequency NUMERIC DEFAULT 0,
    purchases NUMERIC DEFAULT 0,
    purchase_value NUMERIC DEFAULT 0,
    cost_per_purchase NUMERIC DEFAULT 0,
    roas NUMERIC DEFAULT 0,
    add_to_cart NUMERIC DEFAULT 0,
    initiate_checkout NUMERIC DEFAULT 0,
    raw JSONB DEFAULT '{}'::jsonb,
    synced_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(date, ad_id, country)
);

CREATE TABLE IF NOT EXISTS meta_ad_insights_age_gender_daily (
    id BIGSERIAL PRIMARY KEY,
    date DATE NOT NULL,
    account_id TEXT,
    campaign_id TEXT,
    campaign_name TEXT,
    adset_id TEXT,
    adset_name TEXT,
    ad_id TEXT NOT NULL,
    ad_name TEXT,
    age TEXT NOT NULL DEFAULT '',
    gender TEXT NOT NULL DEFAULT '',
    spend NUMERIC DEFAULT 0,
    impressions INTEGER DEFAULT 0,
    reach INTEGER DEFAULT 0,
    clicks INTEGER DEFAULT 0,
    inline_link_clicks INTEGER DEFAULT 0,
    ctr NUMERIC DEFAULT 0,
    cpc NUMERIC DEFAULT 0,
    cpm NUMERIC DEFAULT 0,
    frequency NUMERIC DEFAULT 0,
    purchases NUMERIC DEFAULT 0,
    purchase_value NUMERIC DEFAULT 0,
    cost_per_purchase NUMERIC DEFAULT 0,
    roas NUMERIC DEFAULT 0,
    add_to_cart NUMERIC DEFAULT 0,
    initiate_checkout NUMERIC DEFAULT 0,
    raw JSONB DEFAULT '{}'::jsonb,
    synced_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(date, ad_id, age, gender)
);

CREATE TABLE IF NOT EXISTS meta_ad_insights_platform_daily (
    id BIGSERIAL PRIMARY KEY,
    date DATE NOT NULL,
    account_id TEXT,
    campaign_id TEXT,
    campaign_name TEXT,
    adset_id TEXT,
    adset_name TEXT,
    ad_id TEXT NOT NULL,
    ad_name TEXT,
    publisher_platform TEXT NOT NULL DEFAULT '',
    platform_position TEXT NOT NULL DEFAULT '',
    spend NUMERIC DEFAULT 0,
    impressions INTEGER DEFAULT 0,
    reach INTEGER DEFAULT 0,
    clicks INTEGER DEFAULT 0,
    inline_link_clicks INTEGER DEFAULT 0,
    ctr NUMERIC DEFAULT 0,
    cpc NUMERIC DEFAULT 0,
    cpm NUMERIC DEFAULT 0,
    frequency NUMERIC DEFAULT 0,
    purchases NUMERIC DEFAULT 0,
    purchase_value NUMERIC DEFAULT 0,
    cost_per_purchase NUMERIC DEFAULT 0,
    roas NUMERIC DEFAULT 0,
    add_to_cart NUMERIC DEFAULT 0,
    initiate_checkout NUMERIC DEFAULT 0,
    raw JSONB DEFAULT '{}'::jsonb,
    synced_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(date, ad_id, publisher_platform, platform_position)
);

CREATE INDEX IF NOT EXISTS idx_meta_country_insights_date ON meta_ad_insights_country_daily(date);
CREATE INDEX IF NOT EXISTS idx_meta_country_insights_ad_id ON meta_ad_insights_country_daily(ad_id);
CREATE INDEX IF NOT EXISTS idx_meta_country_insights_campaign_id ON meta_ad_insights_country_daily(campaign_id);
CREATE INDEX IF NOT EXISTS idx_meta_country_insights_country ON meta_ad_insights_country_daily(country);

CREATE INDEX IF NOT EXISTS idx_meta_age_gender_insights_date ON meta_ad_insights_age_gender_daily(date);
CREATE INDEX IF NOT EXISTS idx_meta_age_gender_insights_ad_id ON meta_ad_insights_age_gender_daily(ad_id);
CREATE INDEX IF NOT EXISTS idx_meta_age_gender_insights_campaign_id ON meta_ad_insights_age_gender_daily(campaign_id);
CREATE INDEX IF NOT EXISTS idx_meta_age_gender_insights_age_gender ON meta_ad_insights_age_gender_daily(age, gender);

CREATE INDEX IF NOT EXISTS idx_meta_platform_insights_date ON meta_ad_insights_platform_daily(date);
CREATE INDEX IF NOT EXISTS idx_meta_platform_insights_ad_id ON meta_ad_insights_platform_daily(ad_id);
CREATE INDEX IF NOT EXISTS idx_meta_platform_insights_campaign_id ON meta_ad_insights_platform_daily(campaign_id);
CREATE INDEX IF NOT EXISTS idx_meta_platform_insights_platform ON meta_ad_insights_platform_daily(publisher_platform, platform_position);

ALTER TABLE meta_creative_tags ADD COLUMN IF NOT EXISTS room_type TEXT;
ALTER TABLE meta_creative_tags ADD COLUMN IF NOT EXISTS hook_style TEXT;
ALTER TABLE meta_creative_tags ADD COLUMN IF NOT EXISTS creative_format TEXT;

ALTER TABLE ads_product_mapping ADD COLUMN IF NOT EXISTS room_type TEXT;
ALTER TABLE ads_product_mapping ADD COLUMN IF NOT EXISTS mockup_type TEXT;
ALTER TABLE ads_product_mapping ADD COLUMN IF NOT EXISTS ad_angle TEXT;
ALTER TABLE ads_product_mapping ADD COLUMN IF NOT EXISTS hook_style TEXT;
ALTER TABLE ads_product_mapping ADD COLUMN IF NOT EXISTS creative_format TEXT;
ALTER TABLE ads_product_mapping ADD COLUMN IF NOT EXISTS funnel_stage TEXT;

ALTER TABLE meta_creatives ADD COLUMN IF NOT EXISTS primary_text TEXT;
ALTER TABLE meta_creatives ADD COLUMN IF NOT EXISTS headline TEXT;
ALTER TABLE meta_creatives ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE meta_creatives ADD COLUMN IF NOT EXISTS call_to_action TEXT;
ALTER TABLE meta_creatives ADD COLUMN IF NOT EXISTS link_url TEXT;
ALTER TABLE meta_creatives ADD COLUMN IF NOT EXISTS creative_format TEXT;
ALTER TABLE meta_creatives ADD COLUMN IF NOT EXISTS image_url TEXT;
ALTER TABLE meta_creatives ADD COLUMN IF NOT EXISTS video_id TEXT;
ALTER TABLE meta_creatives ADD COLUMN IF NOT EXISTS image_hash TEXT;
ALTER TABLE meta_creatives ADD COLUMN IF NOT EXISTS effective_object_story_id TEXT;
ALTER TABLE meta_creatives ADD COLUMN IF NOT EXISTS page_id TEXT;
ALTER TABLE meta_creatives ADD COLUMN IF NOT EXISTS instagram_actor_id TEXT;
ALTER TABLE meta_creatives ADD COLUMN IF NOT EXISTS object_story_spec JSONB DEFAULT '{}'::jsonb;
ALTER TABLE meta_creatives ADD COLUMN IF NOT EXISTS asset_feed_spec JSONB DEFAULT '{}'::jsonb;
ALTER TABLE meta_creatives ADD COLUMN IF NOT EXISTS asset_texts JSONB DEFAULT '[]'::jsonb;
ALTER TABLE meta_creatives ADD COLUMN IF NOT EXISTS asset_titles JSONB DEFAULT '[]'::jsonb;
ALTER TABLE meta_creatives ADD COLUMN IF NOT EXISTS asset_descriptions JSONB DEFAULT '[]'::jsonb;

CREATE INDEX IF NOT EXISTS idx_meta_creatives_ad_id ON meta_creatives(ad_id);
CREATE INDEX IF NOT EXISTS idx_meta_creatives_format ON meta_creatives(creative_format);
