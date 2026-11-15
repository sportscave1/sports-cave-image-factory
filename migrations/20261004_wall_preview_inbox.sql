CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public.wall_previews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    image_sha256 TEXT NOT NULL UNIQUE
        CHECK (image_sha256 ~ '^[0-9a-f]{64}$'),
    product_id TEXT NOT NULL DEFAULT ''
        CHECK (char_length(product_id) <= 80),
    variant_id TEXT NOT NULL DEFAULT ''
        CHECK (char_length(variant_id) <= 80),
    product_handle TEXT NOT NULL DEFAULT ''
        CHECK (char_length(product_handle) <= 255),
    product_title TEXT NOT NULL DEFAULT ''
        CHECK (char_length(product_title) <= 500),
    product_url TEXT NOT NULL DEFAULT ''
        CHECK (char_length(product_url) <= 1200),
    frame_label TEXT NOT NULL DEFAULT ''
        CHECK (char_length(frame_label) <= 120),
    size_label TEXT NOT NULL DEFAULT ''
        CHECK (char_length(size_label) <= 160),
    measurement_unit TEXT NOT NULL DEFAULT ''
        CHECK (measurement_unit IN ('', 'cm', 'in')),
    marketing_permission BOOLEAN NOT NULL DEFAULT FALSE,
    status TEXT NOT NULL DEFAULT 'new'
        CHECK (status IN ('new', 'approved', 'used', 'archived')),
    dropbox_file_id TEXT NOT NULL DEFAULT ''
        CHECK (char_length(dropbox_file_id) <= 500),
    dropbox_path TEXT NOT NULL
        CHECK (char_length(dropbox_path) <= 1500),
    content_type TEXT NOT NULL DEFAULT 'image/jpeg'
        CHECK (content_type IN ('image/jpeg', 'image/png')),
    image_width INTEGER NOT NULL
        CHECK (image_width > 0 AND image_width <= 10000),
    image_height INTEGER NOT NULL
        CHECK (image_height > 0 AND image_height <= 10000),
    image_bytes INTEGER NOT NULL
        CHECK (image_bytes > 0 AND image_bytes <= 12582912),
    save_count INTEGER NOT NULL DEFAULT 1
        CHECK (save_count >= 1),
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_saved_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_by UUID REFERENCES public.os_users(id),
    reviewed_at TIMESTAMPTZ,
    notes TEXT NOT NULL DEFAULT ''
        CHECK (char_length(notes) <= 2000)
);

CREATE INDEX IF NOT EXISTS idx_wall_previews_status_received
    ON public.wall_previews(status, received_at DESC);

CREATE INDEX IF NOT EXISTS idx_wall_previews_permission_received
    ON public.wall_previews(marketing_permission, received_at DESC);

CREATE INDEX IF NOT EXISTS idx_wall_previews_product_received
    ON public.wall_previews(product_handle, received_at DESC);

ALTER TABLE public.wall_previews ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.wall_previews FROM PUBLIC, anon, authenticated;
