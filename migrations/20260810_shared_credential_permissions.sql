-- Shared credential access uses os_user_page_permissions.page_key.
-- Only permission identifiers such as credential_prodigi are stored here;
-- credential values remain exclusively in Render environment variables.

CREATE INDEX IF NOT EXISTS idx_os_user_permissions_page_key
    ON os_user_page_permissions (page_key, can_access);
