import streamlit as st


ADS_PRODUCT_CATALOG_CACHE_SECONDS = 300


@st.cache_data(ttl=ADS_PRODUCT_CATALOG_CACHE_SECONDS, show_spinner=False)
def load_live_edition_product_rows():
    """Return Edition Ops products joined to their authoritative Shopify URLs."""
    try:
        import supabase_backend

        if not supabase_backend.is_configured():
            return []
        with supabase_backend.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        COALESCE(ep.shopify_product_id, sp.shopify_product_id) AS shopify_product_id,
                        COALESCE(ep.product_title, sp.title, ep.shopify_handle, sp.handle) AS product_title,
                        COALESCE(ep.shopify_handle, sp.handle) AS product_handle,
                        COALESCE(sp.online_store_url, '') AS online_store_url,
                        COALESCE(sp.image_url, '') AS image_url,
                        COALESCE(sp.product_type, '') AS product_type,
                        ep.edition_total AS edition_limit,
                        CASE
                            WHEN ep.edition_total IS NOT NULL
                            THEN 'Edition Ops product ledger'
                            ELSE ''
                        END AS edition_limit_source,
                        COALESCE(
                            (
                                SELECT array_agg(DISTINCT collection->>'title' ORDER BY collection->>'title')
                                FROM jsonb_array_elements(
                                    CASE
                                        WHEN jsonb_typeof(sp.raw_json->'collections') = 'array'
                                        THEN sp.raw_json->'collections'
                                        ELSE '[]'::jsonb
                                    END
                                ) collection
                                WHERE COALESCE(collection->>'title', '') <> ''
                            ),
                            ARRAY[]::text[]
                        ) AS collections
                    FROM edition_products ep
                    FULL OUTER JOIN shopify_products sp
                        ON sp.handle = ep.shopify_handle
                    WHERE
                        COALESCE(ep.product_title, sp.title, ep.shopify_handle, sp.handle, '') <> ''
                    ORDER BY COALESCE(ep.product_title, sp.title, ep.shopify_handle, sp.handle)
                    LIMIT 1500
                    """
                )
                return list(cur.fetchall() or ())
    except Exception:
        return []
