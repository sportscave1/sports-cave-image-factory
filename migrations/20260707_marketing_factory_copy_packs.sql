CREATE TABLE IF NOT EXISTS ads_copy_packs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_handle TEXT,
    product_title TEXT,
    shopify_product_id TEXT,
    country TEXT,
    ad_format TEXT,
    funnel_stage TEXT,
    edition_stage TEXT,
    next_edition_number INTEGER,
    edition_total INTEGER,
    edition_remaining INTEGER,
    primary_angle TEXT,
    secondary_angles JSONB DEFAULT '[]'::jsonb,
    input_payload JSONB DEFAULT '{}'::jsonb,
    generated_prompt TEXT,
    generated_preview JSONB DEFAULT '{}'::jsonb,
    status TEXT DEFAULT 'Draft',
    created_by TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ads_copy_pack_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pack_id UUID REFERENCES ads_copy_packs(id) ON DELETE CASCADE,
    version_number INTEGER,
    generated_prompt TEXT,
    generated_preview JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ads_copy_packs_product_handle ON ads_copy_packs(product_handle);
CREATE INDEX IF NOT EXISTS idx_ads_copy_packs_created_at ON ads_copy_packs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ads_copy_packs_status ON ads_copy_packs(status);
