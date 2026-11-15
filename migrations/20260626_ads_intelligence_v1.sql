CREATE TABLE IF NOT EXISTS meta_ad_accounts (
    account_id TEXT PRIMARY KEY,
    name TEXT,
    currency TEXT,
    timezone_name TEXT,
    account_status TEXT,
    business_name TEXT,
    raw JSONB DEFAULT '{}'::jsonb,
    synced_at TIMESTAMPTZ DEFAULT now(),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS meta_campaigns (
    campaign_id TEXT PRIMARY KEY,
    account_id TEXT,
    campaign_name TEXT,
    status TEXT,
    effective_status TEXT,
    objective TEXT,
    meta_created_at TIMESTAMPTZ,
    meta_updated_at TIMESTAMPTZ,
    raw JSONB DEFAULT '{}'::jsonb,
    synced_at TIMESTAMPTZ DEFAULT now(),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS meta_adsets (
    adset_id TEXT PRIMARY KEY,
    account_id TEXT,
    campaign_id TEXT,
    adset_name TEXT,
    status TEXT,
    effective_status TEXT,
    optimization_goal TEXT,
    billing_event TEXT,
    daily_budget NUMERIC,
    lifetime_budget NUMERIC,
    meta_created_at TIMESTAMPTZ,
    meta_updated_at TIMESTAMPTZ,
    raw JSONB DEFAULT '{}'::jsonb,
    synced_at TIMESTAMPTZ DEFAULT now(),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS meta_ads (
    ad_id TEXT PRIMARY KEY,
    account_id TEXT,
    campaign_id TEXT,
    adset_id TEXT,
    ad_name TEXT,
    status TEXT,
    effective_status TEXT,
    creative_id TEXT,
    meta_created_at TIMESTAMPTZ,
    meta_updated_at TIMESTAMPTZ,
    raw JSONB DEFAULT '{}'::jsonb,
    synced_at TIMESTAMPTZ DEFAULT now(),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS meta_ad_insights_daily (
    id BIGSERIAL PRIMARY KEY,
    date DATE NOT NULL,
    account_id TEXT,
    campaign_id TEXT,
    campaign_name TEXT,
    adset_id TEXT,
    adset_name TEXT,
    ad_id TEXT NOT NULL,
    ad_name TEXT,
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
    country TEXT DEFAULT '',
    placement TEXT DEFAULT '',
    raw JSONB DEFAULT '{}'::jsonb,
    synced_at TIMESTAMPTZ DEFAULT now(),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(date, ad_id, country, placement)
);

CREATE TABLE IF NOT EXISTS meta_creatives (
    creative_id TEXT PRIMARY KEY,
    ad_id TEXT,
    account_id TEXT,
    name TEXT,
    thumbnail_url TEXT,
    object_story_id TEXT,
    raw JSONB DEFAULT '{}'::jsonb,
    synced_at TIMESTAMPTZ DEFAULT now(),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS meta_creative_tags (
    ad_id TEXT PRIMARY KEY,
    creative_id TEXT,
    product_handle TEXT,
    product_title TEXT,
    sport TEXT,
    country_focus TEXT,
    mockup_type TEXT,
    ad_angle TEXT,
    funnel_stage TEXT,
    notes TEXT,
    tagged_by TEXT DEFAULT 'sports_cave_os',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ads_product_mapping (
    ad_id TEXT PRIMARY KEY,
    product_handle TEXT,
    product_title TEXT,
    sport TEXT,
    country_focus TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ads_analysis_exports (
    id BIGSERIAL PRIMARY KEY,
    export_type TEXT,
    date_range TEXT,
    prompt_text TEXT,
    row_count INTEGER DEFAULT 0,
    created_by TEXT DEFAULT 'sports_cave_os',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ads_action_log (
    id BIGSERIAL PRIMARY KEY,
    action_type TEXT,
    status TEXT,
    summary TEXT,
    context JSONB DEFAULT '{}'::jsonb,
    created_by TEXT DEFAULT 'sports_cave_os',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ads_sync_logs (
    id BIGSERIAL PRIMARY KEY,
    source TEXT DEFAULT 'meta_ads_api',
    sync_type TEXT,
    date_range TEXT,
    started_at TIMESTAMPTZ DEFAULT now(),
    finished_at TIMESTAMPTZ,
    status TEXT DEFAULT 'started',
    rows_fetched INTEGER DEFAULT 0,
    rows_upserted INTEGER DEFAULT 0,
    error_message TEXT,
    context JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_meta_ad_insights_daily_date ON meta_ad_insights_daily(date DESC);
CREATE INDEX IF NOT EXISTS idx_meta_ad_insights_daily_ad ON meta_ad_insights_daily(ad_id);
CREATE INDEX IF NOT EXISTS idx_meta_ad_insights_daily_campaign ON meta_ad_insights_daily(campaign_id);
CREATE INDEX IF NOT EXISTS idx_meta_ads_campaign_adset ON meta_ads(campaign_id, adset_id);
CREATE INDEX IF NOT EXISTS idx_meta_creative_tags_product ON meta_creative_tags(product_handle);
CREATE INDEX IF NOT EXISTS idx_ads_action_log_created_at ON ads_action_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ads_sync_logs_started_at ON ads_sync_logs(started_at DESC);
