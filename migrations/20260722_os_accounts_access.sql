CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS os_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username TEXT NOT NULL,
    email TEXT,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'worker' CHECK (role IN ('admin', 'worker')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS os_user_page_permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES os_users(id) ON DELETE CASCADE,
    page_key TEXT NOT NULL,
    can_access BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, page_key)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_os_users_username_unique
    ON os_users (lower(username));

CREATE UNIQUE INDEX IF NOT EXISTS idx_os_users_email_unique
    ON os_users (lower(email))
    WHERE email IS NOT NULL AND email <> '';

CREATE UNIQUE INDEX IF NOT EXISTS idx_os_users_single_admin
    ON os_users (role)
    WHERE role = 'admin';

CREATE INDEX IF NOT EXISTS idx_os_user_permissions_user
    ON os_user_page_permissions (user_id, can_access);
