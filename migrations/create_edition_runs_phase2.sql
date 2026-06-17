CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS edition_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    edition_product_id BIGINT REFERENCES edition_products(id) ON DELETE SET NULL,
    shopify_product_id TEXT,
    shopify_handle TEXT NOT NULL,
    product_title TEXT,
    edition_name TEXT DEFAULT 'Original Edition',
    edition_total INTEGER DEFAULT 100,
    next_edition_number INTEGER DEFAULT 1,
    status TEXT DEFAULT 'active',
    started_at TIMESTAMPTZ DEFAULT now(),
    archived_at TIMESTAMPTZ NULL,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS edition_adjustments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    edition_product_id BIGINT REFERENCES edition_products(id) ON DELETE SET NULL,
    edition_run_id uuid NULL REFERENCES edition_runs(id) ON DELETE SET NULL,
    shopify_product_id TEXT,
    shopify_handle TEXT,
    old_next_edition_number INTEGER,
    new_next_edition_number INTEGER,
    old_edition_total INTEGER,
    new_edition_total INTEGER,
    reason TEXT,
    source TEXT DEFAULT 'manual_app',
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE edition_products ADD COLUMN IF NOT EXISTS active_edition_run_id UUID;
ALTER TABLE edition_products ADD COLUMN IF NOT EXISTS edition_name TEXT DEFAULT 'Original Edition';

ALTER TABLE edition_orders ADD COLUMN IF NOT EXISTS edition_run_id UUID;
ALTER TABLE edition_orders ADD COLUMN IF NOT EXISTS edition_name TEXT;

CREATE INDEX IF NOT EXISTS idx_edition_orders_run_id ON edition_orders(edition_run_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_edition_orders_run_number_unique
ON edition_orders(edition_run_id, edition_number)
WHERE edition_run_id IS NOT NULL AND edition_number IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_edition_runs_handle_status ON edition_runs(shopify_handle, status);

CREATE UNIQUE INDEX IF NOT EXISTS idx_edition_runs_one_active_per_handle
ON edition_runs(shopify_handle)
WHERE status='active';

CREATE INDEX IF NOT EXISTS idx_edition_adjustments_handle
ON edition_adjustments(shopify_handle, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_edition_adjustments_run
ON edition_adjustments(edition_run_id, created_at DESC);

INSERT INTO edition_runs(
    edition_product_id,
    shopify_product_id,
    shopify_handle,
    product_title,
    edition_name,
    edition_total,
    next_edition_number,
    status,
    started_at,
    updated_at
)
SELECT
    ep.id,
    ep.shopify_product_id,
    ep.shopify_handle,
    ep.product_title,
    COALESCE(NULLIF(ep.edition_name, ''), 'Original Edition'),
    COALESCE(ep.edition_total, 100),
    GREATEST(COALESCE(ep.next_edition_number, 1), 1),
    CASE
        WHEN COALESCE(ep.sold_out, ep.is_sold_out, FALSE) THEN 'sold_out'
        WHEN COALESCE(ep.active, ep.is_active, TRUE) THEN 'active'
        ELSE 'inactive'
    END,
    now(),
    now()
FROM edition_products ep
WHERE ep.shopify_handle IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM edition_runs er
      WHERE er.shopify_handle = ep.shopify_handle
        AND er.status IN ('active', 'sold_out', 'inactive')
  );

UPDATE edition_products ep
SET active_edition_run_id=er.id,
    edition_name=er.edition_name,
    updated_at=now()
FROM edition_runs er
WHERE er.shopify_handle=ep.shopify_handle
  AND er.id = (
      SELECT er2.id
      FROM edition_runs er2
      WHERE er2.shopify_handle=ep.shopify_handle
        AND er2.status IN ('active', 'sold_out', 'inactive')
      ORDER BY CASE
          WHEN er2.status='active' THEN 0
          WHEN er2.status='sold_out' THEN 1
          ELSE 2
      END,
      er2.started_at DESC NULLS LAST,
      er2.created_at DESC NULLS LAST
      LIMIT 1
  );
