-- Shopify Markets context is not a verified residential or commerce address.
ALTER TABLE public.wall_previews
 ADD COLUMN IF NOT EXISTS market_country_code TEXT,
 ADD COLUMN IF NOT EXISTS market_country_name TEXT;
-- Existing privileges, RLS, metadata and indexes remain unchanged.
ALTER TABLE public.wall_previews ENABLE ROW LEVEL SECURITY;
