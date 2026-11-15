ALTER TABLE IF EXISTS webhook_events
    ADD COLUMN IF NOT EXISTS new_order_inserted BOOLEAN DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_webhook_events_new_paid_order_notifications
    ON webhook_events (processed_at, webhook_id)
    WHERE new_order_inserted IS TRUE
      AND status IN ('processed', 'processed_with_warnings', 'skipped_duplicate');

CREATE INDEX IF NOT EXISTS idx_order_action_shopify_lines_order
    ON shopify_order_lines (shopify_order_id, shopify_line_item_id);

CREATE INDEX IF NOT EXISTS idx_order_action_edition_orders_line
    ON edition_orders (shopify_line_item_id, edition_number);

CREATE INDEX IF NOT EXISTS idx_order_action_prodigi_line
    ON prodigi_dispatch_rows (shopify_line_item_id, edition_number, updated_at DESC);
