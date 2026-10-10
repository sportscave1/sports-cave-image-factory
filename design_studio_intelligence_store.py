"""Bounded, SELECT-only projections of existing operational records.

Never call schema/discovery/sync helpers here: some existing 'list' helpers write.
Customer data and order raw JSON never leave PostgreSQL through this adapter.
"""
from contextlib import contextmanager


PRODUCTS_SQL = """
SELECT shopify_product_id AS id,title,handle,product_type,status,image_url,synced_at,
       raw_json->'tags' AS tags,raw_json->'collections' AS collections,raw_json->'images' AS images,
       COALESCE(raw_json->>'published_at',raw_json->>'publishedAt') AS published_at
FROM shopify_products ORDER BY shopify_product_id LIMIT 5001
"""

# The order webhook retains REST payloads, while the GraphQL operational sync
# retains only quantities. Project both explicitly; do not assume absent = zero.
LINES_SQL = """
SELECT o.shopify_order_id AS order_id,l.shopify_line_item_id AS line_id,
       l.shopify_product_id AS product_id,l.variant_title,l.quantity,
       o.created_at,o.cancelled_at,o.financial_status,o.currency,o.synced_at,
       COALESCE(o.raw_json->'test',o.raw_json#>'{raw_payload,test}') AS test,
       COALESCE(o.raw_json->>'shipping_country',
                o.raw_json#>>'{raw_payload,shipping_address,country_code}') AS market,
       COALESCE(o.raw_json->>'source_name',o.raw_json#>>'{raw_payload,source_name}') AS source_name,
       COALESCE(item->>'price',l.raw_json->>'price') AS price,
       COALESCE(item->>'total_discount',l.raw_json->>'total_discount') AS discount,
       item->'discount_allocations' AS discount_allocations,
       o.raw_json#>'{raw_payload,refunds}' IS NOT NULL AS refunds_known,
       (SELECT jsonb_agg(jsonb_build_object(
           'quantity',rline->'quantity','subtotal',rline->'subtotal'))
        FROM jsonb_array_elements(COALESCE(o.raw_json#>'{raw_payload,refunds}','[]')) refund,
             jsonb_array_elements(COALESCE(refund->'refund_line_items','[]')) rline
        WHERE rline->>'line_item_id'=regexp_replace(l.shopify_line_item_id,'^gid://shopify/LineItem/','')) AS refunds,
       EXISTS(SELECT 1 FROM jsonb_array_elements(COALESCE(o.raw_json#>'{raw_payload,refunds}','[]')) refund
              WHERE jsonb_array_length(COALESCE(refund->'order_adjustments','[]'))>0
                 OR jsonb_array_length(COALESCE(refund->'refund_line_items','[]'))=0) AS unallocated_refund
FROM shopify_orders o JOIN shopify_order_lines l ON l.shopify_order_id=o.shopify_order_id
LEFT JOIN LATERAL (
    SELECT value AS item FROM jsonb_array_elements(COALESCE(o.raw_json#>'{raw_payload,line_items}','[]'))
    WHERE value->>'id'=regexp_replace(l.shopify_line_item_id,'^gid://shopify/LineItem/','') LIMIT 1
) payload ON TRUE
WHERE o.created_at >= %s AND o.created_at < %s
ORDER BY o.created_at,o.shopify_order_id,l.shopify_line_item_id LIMIT 50001
"""

META_SQL = """
SELECT m.product_handle,a.currency,MIN(i.date) AS since,MAX(i.date) AS through,
       MAX(i.synced_at) AS refreshed_at,COUNT(DISTINCT i.date) AS observed_days,
       SUM(i.spend) AS spend,SUM(i.impressions) AS impressions,SUM(i.clicks) AS clicks,
       SUM(i.purchases) AS attributed_purchases,SUM(i.purchase_value) AS attributed_value,
       SUM(i.add_to_cart) AS add_to_cart,SUM(i.initiate_checkout) AS checkouts
FROM meta_ad_insights_daily i JOIN ads_product_mapping m ON m.ad_id=i.ad_id
JOIN meta_ad_accounts a ON a.account_id=i.account_id
WHERE i.date >= %s AND i.date < %s AND COALESCE(i.country,'')='' AND COALESCE(i.placement,'')=''
  AND COALESCE(m.product_handle,'')<>''
GROUP BY m.product_handle,a.currency ORDER BY m.product_handle,a.currency LIMIT 5001
"""

# These are landing-session signals, NOT product-view conversion denominators.
GA4_SQL = """
SELECT g.landing_page_path_query AS path,g.country_id AS country,g.device_category AS device,
       g.session_channel_group AS channel,MIN(g.date) AS since,MAX(g.date) AS through,
       MAX(g.imported_at) AS refreshed_at,SUM(g.sessions) AS sessions,
       SUM(g.engaged_sessions) AS engaged_sessions,SUM(g.transactions) AS attributed_transactions,
       BOOL_OR(g.is_thresholded) AS thresholded
FROM seo_ga4_daily_landing_pages g JOIN seo_google_connections c
  ON c.workspace_key=g.workspace_key AND c.ga4_property_id=g.ga4_property_id
WHERE g.date >= %s AND g.date < %s AND g.is_complete=TRUE
  AND g.landing_page_path_query LIKE '%%/products/%%'
GROUP BY g.landing_page_path_query,g.country_id,g.device_category,g.session_channel_group
ORDER BY g.landing_page_path_query LIMIT 10001
"""

TRACKING_SQL = """
SELECT p.shopify_product_id AS product_id,p.shopify_handle AS handle,
       t.date_created,p.active,p.sold_out,p.edition_total
FROM edition_products p LEFT JOIN edition_design_tracking t ON t.edition_product_id=p.id
ORDER BY p.id LIMIT 5001
"""


@contextmanager
def read_cursor(connect):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute('SET TRANSACTION READ ONLY')
            cur.execute("SET LOCAL statement_timeout='4000ms'")
            yield cur


def load_sources(start, end, *, connect=None):
    if connect is None:
        from supabase_backend import connect
    result = {"limitations": []}
    with read_cursor(connect) as cur:
        for name, sql, params, limit in (
            ('products', PRODUCTS_SQL, (), 5000),
            ('lines', LINES_SQL, (start, end), 50000),
            ('meta', META_SQL, (start.date(), end.date()), 5000),
            ('ga4', GA4_SQL, (start.date(), end.date()), 10000),
            ('tracking', TRACKING_SQL, (), 5000),
        ):
            cur.execute('SAVEPOINT intelligence_source')
            try:
                cur.execute(sql, params)
                rows = cur.fetchall()
                if len(rows) > limit:
                    raise ValueError('Source exceeds reviewed bound')
                result[name] = rows
            except Exception:
                # No exception strings: driver diagnostics can contain secrets.
                cur.execute('ROLLBACK TO SAVEPOINT intelligence_source')
                result[name] = []
                result['limitations'].append(f'{name}: unavailable or exceeds bounded read limit; no ranking from this source.')
            finally:
                cur.execute('RELEASE SAVEPOINT intelligence_source')
    return result
