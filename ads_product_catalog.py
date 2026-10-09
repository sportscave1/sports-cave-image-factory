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


def product_reference_image_url(row):
    """Use the same catalog row as New Ads; never invent an image from a handle."""
    from urllib.parse import urlparse
    value = str((row or {}).get("image_url") or "").strip()
    parsed = urlparse(value)
    return value if parsed.scheme == "https" and parsed.hostname else ""


def verify_live_black_frame_variant(shopify_product_id, expected_handle):
    """Read one product from live Shopify only after an explicit user click.

    Metadata verification is NOT proof that ChatGPT inspected the real image pixels.
    Never change Shopify, product variants, or the selected product's saved state.
    """
    import re
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
    from shopify_sync import fetch_product_by_shopify_id
    from meta_review_products import product_url_handle

    expected_handle = str(expected_handle or "").strip().lower()
    product_id = str(shopify_product_id or "").strip()
    if not expected_handle or not re.fullmatch(r"[a-z0-9-]+", expected_handle):
        raise ValueError("Select a verified Shopify product before checking its Black variant.")
    if not re.fullmatch(r"(?:gid://shopify/Product/)?[0-9]+", product_id):
        raise ValueError("A valid Shopify product ID is required for live verification.")
    product = fetch_product_by_shopify_id(product_id)
    if str(product.get("handle") or "").strip().lower() != expected_handle:
        raise ValueError("Live Shopify product handle does not match the selected Sports Cave product.")
    page = str(product.get("online_store_url") or "").strip()
    if product_url_handle(page) != expected_handle:
        raise ValueError("The live storefront URL could not be verified for this product.")
    variants = product.get("variants") or []
    def is_black(variant):
        title = str(variant.get("title") or "").strip()
        if re.match(r"^Black\s*(?:/|[-–]|$)", title, re.I):
            return True
        return any(str(opt.get("value") or "").strip().casefold() == "black"
                   for opt in (variant.get("selected_options") or []) if isinstance(opt, dict))
    blacks = [v for v in variants if isinstance(v, dict) and is_black(v)]
    if not blacks:
        raise ValueError("No explicitly Black framed variant was found in the live Shopify data.")
    # Prefer the largest verified framed variant, not an inferred size or price.
    xl = [v for v in blacks if re.search(r"\b(?:XL|EXTRA LARGE)\b", str(v.get("title") or ""), re.I)]
    variant = (xl or blacks)[0]
    legacy_id = str(variant.get("legacy_resource_id") or "").strip()
    raw_gid = str(variant.get("id") or "").strip()
    variant_id = legacy_id if legacy_id.isdigit() else (
        raw_gid.rsplit("/", 1)[-1] if re.fullmatch(r"gid://shopify/ProductVariant/[0-9]+", raw_gid) else "")
    if not variant_id or not variant_id.isdigit():
        raise ValueError("The Black variant ID could not be confirmed.")
    parsed = urlsplit(page)
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k != "variant"]
    query.append(("variant", variant_id))
    variant_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), ""))
    images = product.get("images") or []
    def black_image(media):
        name = " ".join((str(media.get("alt") or ""), str(media.get("url") or ""))).lower()
        return "black-framed" in name or "black framed" in name or "black frame" in name
    candidates = [media for media in images if isinstance(media, dict) and black_image(media)]
    image_url = str(candidates[0].get("url") or "").strip() if candidates else ""
    if image_url and not image_url.startswith("https://"):
        image_url = ""
    return {
        "shopify_product_id": product_id,
        "product_handle": expected_handle,
        "variant_title": str(variant.get("title") or ""),
        "variant_id": variant_id,
        "variant_url": variant_url,
        "original_black_image_url": image_url,
        "verification_source": "live Shopify Admin product read; visual confirmation still required",
    }
