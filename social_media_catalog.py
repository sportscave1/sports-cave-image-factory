import streamlit as st

from ads_product_catalog import load_live_edition_product_rows


SOCIAL_CATALOG_CACHE_SECONDS = 300


def _clean_product(row):
    row = dict(row or {})
    title = str(row.get("product_title") or row.get("title") or "").strip()
    handle = str(
        row.get("product_handle")
        or row.get("shopify_handle")
        or row.get("handle")
        or ""
    ).strip()
    product_id = str(
        row.get("shopify_product_id")
        or row.get("product_id")
        or row.get("id")
        or ""
    ).strip()
    return {
        "id": product_id,
        "title": title or handle,
        "handle": handle,
        "url": str(row.get("online_store_url") or row.get("product_url") or "").strip(),
        "image_url": str(
            row.get("image_url")
            or row.get("featured_image_url")
            or ""
        ).strip(),
        "product_type": str(row.get("product_type") or "").strip(),
        "collections": tuple(
            str(value or "").strip()
            for value in row.get("collections") or ()
            if str(value or "").strip()
        ),
    }


def _database_products():
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


@st.cache_data(ttl=SOCIAL_CATALOG_CACHE_SECONDS, show_spinner=False)
def load_social_product_catalog():
    rows = _database_products()
    if not rows:
        rows = list(load_live_edition_product_rows() or ())
    products = []
    seen = set()
    for row in rows:
        product = _clean_product(row)
        identity = (
            product["id"].casefold(),
            product["handle"].casefold(),
            product["title"].casefold(),
        )
        if not product["title"] or identity in seen:
            continue
        products.append(product)
        seen.add(identity)
    products.sort(key=lambda item: (item["title"].casefold(), item["handle"].casefold()))
    return products


def collection_options(products):
    values = set()
    for product in products or ():
        values.update(product.get("collections") or ())
        if product.get("product_type"):
            values.add(str(product["product_type"]).strip())
    return tuple(sorted((value for value in values if value), key=str.casefold))
