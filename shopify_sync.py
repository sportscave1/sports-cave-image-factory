import os
from urllib.parse import urlparse

import requests


DEFAULT_API_VERSION = "2026-04"
DEFAULT_PAGE_SIZE = 10
DEFAULT_MAX_PRODUCTS = 250


class ShopifyConfigurationError(ValueError):
    pass


class ShopifyAPIError(RuntimeError):
    pass


def normalize_store_domain(value):
    raw_value = str(value or "").strip().lower()
    if not raw_value:
        return ""

    if "://" not in raw_value:
        raw_value = f"https://{raw_value}"
    parsed = urlparse(raw_value)
    domain = (parsed.hostname or "").strip(".")
    return domain


def get_config():
    store_domain = normalize_store_domain(os.getenv("SHOPIFY_STORE_DOMAIN", ""))
    access_token = os.getenv("SHOPIFY_ADMIN_ACCESS_TOKEN", "").strip()
    api_version = os.getenv("SHOPIFY_API_VERSION", DEFAULT_API_VERSION).strip() or DEFAULT_API_VERSION
    max_products_raw = os.getenv("SHOPIFY_SYNC_MAX_PRODUCTS", str(DEFAULT_MAX_PRODUCTS)).strip()
    try:
        max_products = max(1, int(max_products_raw))
    except ValueError:
        max_products = DEFAULT_MAX_PRODUCTS

    return {
        "store_domain": store_domain,
        "access_token": access_token,
        "api_version": api_version,
        "max_products": max_products,
        "configured": bool(store_domain and access_token),
    }


def validate_config(config):
    if not config.get("store_domain"):
        raise ShopifyConfigurationError("SHOPIFY_STORE_DOMAIN is missing.")
    if not config.get("store_domain", "").endswith(".myshopify.com"):
        raise ShopifyConfigurationError(
            "SHOPIFY_STORE_DOMAIN must be the store's .myshopify.com domain."
        )
    if not config.get("access_token"):
        raise ShopifyConfigurationError("SHOPIFY_ADMIN_ACCESS_TOKEN is missing.")


def graphql_request(query, variables=None, timeout=30, config=None, request_post=None):
    config = config or get_config()
    validate_config(config)
    request_post = request_post or requests.post
    endpoint = (
        f"https://{config['store_domain']}/admin/api/"
        f"{config['api_version']}/graphql.json"
    )
    response = request_post(
        endpoint,
        headers={
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": config["access_token"],
        },
        json={"query": query, "variables": variables or {}},
        timeout=timeout,
    )
    try:
        response.raise_for_status()
    except requests.RequestException as error:
        status_code = getattr(response, "status_code", "unknown")
        raise ShopifyAPIError(f"Shopify returned HTTP {status_code}.") from error

    try:
        payload = response.json()
    except ValueError as error:
        raise ShopifyAPIError("Shopify returned a response that was not JSON.") from error

    if payload.get("errors"):
        messages = [str(item.get("message") or item) for item in payload["errors"]]
        raise ShopifyAPIError("Shopify GraphQL error: " + "; ".join(messages))
    if not isinstance(payload.get("data"), dict):
        raise ShopifyAPIError("Shopify response did not contain GraphQL data.")

    return payload["data"], response.headers.get("X-Shopify-API-Version")


SHOP_QUERY = """
query SportsCaveShopConnection {
  shop {
    id
    name
    myshopifyDomain
    primaryDomain {
      host
      url
    }
  }
}
"""


PRODUCTS_QUERY = """
query SportsCaveProducts($first: Int!, $after: String, $query: String) {
  products(first: $first, after: $after, query: $query, sortKey: UPDATED_AT, reverse: true) {
    pageInfo {
      hasNextPage
      endCursor
    }
    nodes {
      id
      legacyResourceId
      title
      handle
      status
      vendor
      productType
      tags
      updatedAt
      onlineStoreUrl
      media(first: 10) {
        nodes {
          ... on MediaImage {
            id
            alt
            image {
              url
              width
              height
            }
          }
        }
      }
      variants(first: 100) {
        nodes {
          id
          legacyResourceId
          title
          sku
          price
          inventoryQuantity
          selectedOptions {
            name
            value
          }
        }
      }
      collections(first: 20) {
        nodes {
          id
          title
          handle
        }
      }
      metafields(first: 50) {
        nodes {
          namespace
          key
          type
          value
        }
      }
    }
  }
}
"""


def test_connection(config=None, request_post=None):
    data, served_version = graphql_request(
        SHOP_QUERY,
        config=config,
        request_post=request_post,
    )
    shop = data.get("shop") or {}
    if not shop.get("id"):
        raise ShopifyAPIError("Shopify connection succeeded but shop details were missing.")
    return {
        "id": shop.get("id"),
        "name": shop.get("name") or "Shopify store",
        "myshopify_domain": shop.get("myshopifyDomain") or "",
        "primary_domain": (shop.get("primaryDomain") or {}).get("host") or "",
        "primary_url": (shop.get("primaryDomain") or {}).get("url") or "",
        "api_version": served_version or (config or get_config()).get("api_version"),
    }


def build_admin_url(store_domain, legacy_resource_id):
    if not store_domain or not legacy_resource_id:
        return ""
    store_slug = store_domain.split(".", 1)[0]
    return f"https://admin.shopify.com/store/{store_slug}/products/{legacy_resource_id}"


def normalize_product(node, store_domain):
    media = []
    for item in (node.get("media") or {}).get("nodes") or []:
        image = item.get("image") or {}
        if not image.get("url"):
            continue
        media.append(
            {
                "id": item.get("id") or "",
                "alt": item.get("alt") or "",
                "url": image.get("url") or "",
                "width": image.get("width"),
                "height": image.get("height"),
            }
        )

    variants = []
    for item in (node.get("variants") or {}).get("nodes") or []:
        variants.append(
            {
                "id": item.get("id") or "",
                "legacy_resource_id": str(item.get("legacyResourceId") or ""),
                "title": item.get("title") or "",
                "sku": item.get("sku") or "",
                "price": str(item.get("price") or ""),
                "inventory_quantity": item.get("inventoryQuantity"),
                "selected_options": item.get("selectedOptions") or [],
            }
        )

    collections = [
        {
            "id": item.get("id") or "",
            "title": item.get("title") or "",
            "handle": item.get("handle") or "",
        }
        for item in (node.get("collections") or {}).get("nodes") or []
    ]
    metafields = [
        {
            "namespace": item.get("namespace") or "",
            "key": item.get("key") or "",
            "type": item.get("type") or "",
            "value": item.get("value") or "",
        }
        for item in (node.get("metafields") or {}).get("nodes") or []
    ]
    legacy_resource_id = str(node.get("legacyResourceId") or "")

    return {
        "shopify_product_id": node.get("id") or "",
        "legacy_resource_id": legacy_resource_id,
        "title": node.get("title") or "Untitled Shopify Product",
        "handle": node.get("handle") or "",
        "status": node.get("status") or "UNKNOWN",
        "vendor": node.get("vendor") or "",
        "product_type": node.get("productType") or "",
        "tags": node.get("tags") or [],
        "collections": collections,
        "variants": variants,
        "images": media,
        "metafields": metafields,
        "online_store_url": node.get("onlineStoreUrl") or "",
        "admin_url": build_admin_url(store_domain, legacy_resource_id),
        "remote_updated_at": node.get("updatedAt") or "",
    }


def fetch_catalog_page(after=None, search="", page_size=DEFAULT_PAGE_SIZE, config=None, request_post=None):
    config = config or get_config()
    first = min(max(int(page_size), 1), 25)
    data, served_version = graphql_request(
        PRODUCTS_QUERY,
        variables={
            "first": first,
            "after": after,
            "query": search.strip() or None,
        },
        config=config,
        request_post=request_post,
    )
    connection = data.get("products") or {}
    nodes = connection.get("nodes") or []
    products = [normalize_product(node, config["store_domain"]) for node in nodes]
    page_info = connection.get("pageInfo") or {}
    return {
        "products": products,
        "has_next_page": bool(page_info.get("hasNextPage")),
        "end_cursor": page_info.get("endCursor"),
        "api_version": served_version or config.get("api_version"),
    }


def iter_catalog_pages(search="", page_size=DEFAULT_PAGE_SIZE, config=None, request_post=None):
    config = config or get_config()
    after = None
    products_seen = 0
    while products_seen < config["max_products"]:
        page = fetch_catalog_page(
            after=after,
            search=search,
            page_size=min(page_size, config["max_products"] - products_seen),
            config=config,
            request_post=request_post,
        )
        if not page["products"]:
            break
        products_seen += len(page["products"])
        yield page
        if not page["has_next_page"] or not page["end_cursor"]:
            break
        after = page["end_cursor"]
