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
    edition_limit = row.get("edition_limit") or row.get("edition_total")
    try:
        edition_limit = int(edition_limit)
    except (TypeError, ValueError):
        edition_limit = None
    if edition_limit is not None and edition_limit <= 0:
        edition_limit = None
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
        "edition_limit": edition_limit,
        "edition_limit_verified": bool(edition_limit),
        "edition_limit_source": (
            str(row.get("edition_limit_source") or "").strip()
            or ("Edition Ops product ledger" if edition_limit else "")
        ),
        "collections": tuple(
            str(value or "").strip()
            for value in row.get("collections") or ()
            if str(value or "").strip()
        ),
    }


def _database_products():
    return list(load_live_edition_product_rows() or ())


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
