CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS dropbox_assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dropbox_file_id TEXT,
    dropbox_path TEXT NOT NULL,
    name TEXT NOT NULL,
    file_extension TEXT,
    size BIGINT DEFAULT 0,
    asset_type TEXT,
    status TEXT DEFAULT 'uploaded',
    uploaded_by_user_name TEXT,
    uploaded_by_user_email TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_dropbox_assets_created_at
ON dropbox_assets(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_dropbox_assets_asset_type
ON dropbox_assets(asset_type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_dropbox_assets_path
ON dropbox_assets(dropbox_path);
