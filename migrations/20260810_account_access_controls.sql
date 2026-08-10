-- Server-side session revocation and permanent account-removal tombstones.
-- Existing users remain active with session_version 1 after this migration.

ALTER TABLE os_users
    ADD COLUMN IF NOT EXISTS session_version INTEGER DEFAULT 1;

UPDATE os_users
SET session_version = 1
WHERE session_version IS NULL OR session_version < 1;

ALTER TABLE os_users
    ALTER COLUMN session_version SET DEFAULT 1,
    ALTER COLUMN session_version SET NOT NULL;

ALTER TABLE os_users
    ADD COLUMN IF NOT EXISTS account_status TEXT DEFAULT 'active';

UPDATE os_users
SET account_status = 'active'
WHERE account_status IS NULL
   OR account_status NOT IN ('active', 'removed');

ALTER TABLE os_users
    ALTER COLUMN account_status SET DEFAULT 'active',
    ALTER COLUMN account_status SET NOT NULL;

DO $$
BEGIN
    ALTER TABLE os_users
    ADD CONSTRAINT os_users_account_status_check
    CHECK (account_status IN ('active', 'removed'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

ALTER TABLE os_users
    ADD COLUMN IF NOT EXISTS removed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS removed_by UUID;

CREATE INDEX IF NOT EXISTS idx_os_users_active_accounts
    ON os_users (account_status, is_active, role);
