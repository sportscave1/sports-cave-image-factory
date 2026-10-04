-- Add identity metadata without moving or inventing identity for legacy saves.
ALTER TABLE public.wall_previews
    ADD COLUMN IF NOT EXISTS customer_email TEXT NOT NULL DEFAULT ''
        CHECK (char_length(customer_email) <= 254 AND customer_email = lower(btrim(customer_email))),
    ADD COLUMN IF NOT EXISTS customer_name TEXT NOT NULL DEFAULT ''
        CHECK (char_length(customer_name) <= 200),
    ADD COLUMN IF NOT EXISTS shopify_customer_id TEXT NOT NULL DEFAULT ''
        CHECK (char_length(shopify_customer_id) <= 100
            AND (shopify_customer_id = '' OR shopify_customer_id ~ '^gid://shopify/Customer/[0-9]+$')),
    ADD COLUMN IF NOT EXISTS identity_source TEXT NOT NULL DEFAULT ''
        CHECK (identity_source IN ('', 'guest', 'logged_in')),
    ADD COLUMN IF NOT EXISTS email_marketing_state TEXT NOT NULL DEFAULT 'UNKNOWN'
        CHECK (email_marketing_state IN ('UNKNOWN', 'SUBSCRIBED', 'UNSUBSCRIBED',
            'NOT_SUBSCRIBED', 'PENDING', 'REDACTED', 'INVALID')),
    ADD COLUMN IF NOT EXISTS customer_folder TEXT NOT NULL DEFAULT ''
        CHECK (char_length(customer_folder) <= 1500);

-- Identical bytes belonging to different customers must never share identity,
-- consent or the other customer's archive. Legacy rows retain their blank owner.
CREATE UNIQUE INDEX IF NOT EXISTS idx_wall_previews_customer_image
    ON public.wall_previews(customer_email, image_sha256);
ALTER TABLE public.wall_previews DROP CONSTRAINT IF EXISTS wall_previews_image_sha256_key;
CREATE INDEX IF NOT EXISTS idx_wall_previews_customer_email_search
    ON public.wall_previews(customer_email text_pattern_ops);
CREATE INDEX IF NOT EXISTS idx_wall_previews_customer_name_search
    ON public.wall_previews(lower(customer_name) text_pattern_ops);

ALTER TABLE public.wall_previews ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.wall_previews FROM PUBLIC, anon, authenticated;
