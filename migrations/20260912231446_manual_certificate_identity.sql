-- Certificate-only identity constraint. Existing records are never rewritten.
-- Ambiguous pre-existing aliases fail safely rather than deleting audit evidence.
BEGIN;
CREATE UNIQUE INDEX IF NOT EXISTS manual_certificate_canonical_line_unique
ON manual_order_line_editions (
    source_channel,
    (regexp_replace(external_order_id, '^gid://shopify/Order/', '')),
    (regexp_replace(external_line_item_id, '^gid://shopify/LineItem/', ''))
);
COMMIT;
