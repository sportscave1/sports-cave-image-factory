DROP INDEX IF EXISTS idx_edition_orders_run_number_unique;

CREATE INDEX IF NOT EXISTS idx_edition_orders_run_number
ON edition_orders(edition_run_id, edition_number)
WHERE edition_run_id IS NOT NULL AND edition_number IS NOT NULL;
