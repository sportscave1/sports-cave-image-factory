-- Upgrade the existing rows in place. Keep the product-ID unique key so the
-- previous release remains compatible during the rolling deployment.
ALTER TABLE public.edition_design_tracking
    ADD COLUMN IF NOT EXISTS id UUID NOT NULL DEFAULT gen_random_uuid(),
    ADD COLUMN IF NOT EXISTS product_title TEXT CHECK (length(product_title) <= 500),
    ADD COLUMN IF NOT EXISTS date_created DATE,
    ADD COLUMN IF NOT EXISTS first_order TEXT CHECK (length(first_order) <= 120),
    ADD COLUMN IF NOT EXISTS added_by UUID REFERENCES public.os_users(id),
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_constraint
        WHERE conrelid='public.edition_design_tracking'::regclass
          AND contype='p' AND pg_get_constraintdef(oid)='PRIMARY KEY (edition_product_id)') THEN
        ALTER TABLE public.edition_design_tracking
            ADD CONSTRAINT edition_design_tracking_product_unique UNIQUE (edition_product_id);
        ALTER TABLE public.edition_design_tracking DROP CONSTRAINT edition_design_tracking_pkey;
        ALTER TABLE public.edition_design_tracking ADD PRIMARY KEY (id);
    END IF;
END $$;

ALTER TABLE public.edition_design_tracking
    ALTER COLUMN edition_product_id DROP NOT NULL,
    ALTER COLUMN updated_by DROP NOT NULL;

-- A one-time snapshot of existing displayed first orders is appended below.
-- Subsequent product discovery inserts a blank first_order and never replaces
-- manually entered values, including deliberately cleared cells.

INSERT INTO public.edition_design_tracking
    (edition_product_id,product_title,date_created,first_order,created_at)
SELECT p.id,p.product_title,(p.created_at AT TIME ZONE 'Australia/Sydney')::date,
       COALESCE(f.order_name,''),p.created_at
FROM public.edition_products p
LEFT JOIN LATERAL (
SELECT order_id, order_name, order_at FROM (
    SELECT o.shopify_order_id AS order_id,
           COALESCE(NULLIF(o.order_name,''), NULLIF(o.shopify_order_name,''),
                    NULLIF(o.order_number,''), o.shopify_order_id) AS order_name,
           COALESCE(o.created_at,o.processed_at) AS order_at
    FROM shopify_order_lines l JOIN shopify_orders o
      ON o.shopify_order_id=l.shopify_order_id
    WHERE l.shopify_product_id IN (NULLIF(p.shopify_product_gid,''),NULLIF(p.shopify_product_id,''),
          NULLIF(regexp_replace(p.shopify_product_id,'^gid://shopify/Product/',''),''))
      AND l.quantity > 0 AND o.cancelled_at IS NULL
      AND COALESCE(o.raw_json->>'test',o.raw->>'test','false') <> 'true'
    UNION ALL
    SELECT COALESCE(NULLIF(e.shopify_order_id,''),NULLIF(e.external_order_id,'')),
           COALESCE(NULLIF(e.shopify_order_name,''),NULLIF(e.external_order_id,'')),
           COALESCE(o.created_at,e.purchase_date,e.assigned_at)
    FROM edition_orders e LEFT JOIN shopify_orders o
      ON o.shopify_order_id=e.shopify_order_id
    WHERE (e.shopify_product_gid=NULLIF(p.shopify_product_gid,'')
           OR e.shopify_product_id IN (NULLIF(p.shopify_product_gid,''),NULLIF(p.shopify_product_id,''),
              NULLIF(regexp_replace(p.shopify_product_id,'^gid://shopify/Product/',''),'')))
      AND e.allocation_valid IS DISTINCT FROM false
      AND o.cancelled_at IS NULL
      AND COALESCE(o.raw_json->>'test',o.raw->>'test','false') <> 'true'
) orders
WHERE order_id IS NOT NULL AND order_name IS NOT NULL
ORDER BY order_at NULLS LAST, order_id
LIMIT 1
) f ON true
WHERE p.created_at >= '2026-09-01 00:00:00 Australia/Sydney'::timestamptz
ON CONFLICT (edition_product_id) DO UPDATE SET
    product_title=COALESCE(edition_design_tracking.product_title,excluded.product_title),
    date_created=COALESCE(edition_design_tracking.date_created,excluded.date_created),
    first_order=COALESCE(edition_design_tracking.first_order,edition_design_tracking.paid_order_name,excluded.first_order);

ALTER TABLE public.edition_design_tracking ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.edition_design_tracking FROM PUBLIC, anon, authenticated;
COMMENT ON TABLE public.edition_design_tracking IS
    'Server-only editable design tracker; first orders are manual. Existing bonuses retained. No row deletion through the UI.';
