import os
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import requests

from edition_display import build_edition_display_text as build_sports_cave_edition_display_text


DEFAULT_API_VERSION = "2026-04"
DEFAULT_PAGE_SIZE = 10
DEFAULT_MAX_PRODUCTS = 500
DEFAULT_MAX_ORDERS = 250
TOKEN_REFRESH_BUFFER_SECONDS = 300


_TOKEN_CACHE = {}
_TOKEN_CACHE_LOCK = threading.Lock()


class ShopifyConfigurationError(ValueError):
    pass


class ShopifyAPIError(RuntimeError):
    pass


class ShopifyAuthenticationError(ShopifyAPIError):
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
    client_id = os.getenv("SHOPIFY_CLIENT_ID", "").strip()
    client_secret = os.getenv("SHOPIFY_CLIENT_SECRET", "").strip()
    api_version = os.getenv("SHOPIFY_API_VERSION", "").strip()
    max_products_raw = os.getenv("SHOPIFY_SYNC_MAX_PRODUCTS", str(DEFAULT_MAX_PRODUCTS)).strip()
    max_orders_raw = os.getenv("SHOPIFY_SYNC_MAX_ORDERS", str(DEFAULT_MAX_ORDERS)).strip()
    try:
        max_products = max(1, int(max_products_raw))
    except ValueError:
        max_products = DEFAULT_MAX_PRODUCTS
    try:
        max_orders = max(1, int(max_orders_raw))
    except ValueError:
        max_orders = DEFAULT_MAX_ORDERS

    if access_token:
        auth_mode = "Admin access token mode"
    elif client_id and client_secret:
        auth_mode = "Client credentials mode"
    else:
        auth_mode = "Missing credentials"

    return {
        "store_domain": store_domain,
        "access_token": access_token,
        "client_id": client_id,
        "client_secret": client_secret,
        "api_version": api_version,
        "max_products": max_products,
        "max_orders": max_orders,
        "auth_mode": auth_mode,
        "configured": bool(store_domain and api_version and auth_mode != "Missing credentials"),
    }


def validate_config(config):
    if not config.get("store_domain"):
        raise ShopifyConfigurationError("Missing SHOPIFY_STORE_DOMAIN.")
    if not config.get("store_domain", "").endswith(".myshopify.com"):
        raise ShopifyConfigurationError(
            "SHOPIFY_STORE_DOMAIN must be the store's .myshopify.com domain."
        )
    if not config.get("api_version"):
        raise ShopifyConfigurationError("Missing SHOPIFY_API_VERSION.")
    if not config.get("access_token") and not (
        config.get("client_id") and config.get("client_secret")
    ):
        raise ShopifyConfigurationError(
            "Missing Shopify authentication. Add SHOPIFY_ADMIN_ACCESS_TOKEN or "
            "SHOPIFY_CLIENT_ID and SHOPIFY_CLIENT_SECRET."
        )


def clear_access_token_cache():
    with _TOKEN_CACHE_LOCK:
        _TOKEN_CACHE.clear()


def _token_cache_key(config):
    return (config.get("store_domain", ""), config.get("client_id", ""))


def get_token_status(config=None):
    config = config or get_config()
    if config.get("access_token"):
        return {
            "auth_mode": "Admin access token mode",
            "last_refresh": None,
            "cached": False,
        }

    with _TOKEN_CACHE_LOCK:
        cached = _TOKEN_CACHE.get(_token_cache_key(config)) or {}
    return {
        "auth_mode": config.get("auth_mode", "Missing credentials"),
        "last_refresh": cached.get("refreshed_at"),
        "cached": bool(cached.get("access_token")),
    }


def get_access_token(config=None, timeout=15, request_post=None):
    config = config or get_config()
    validate_config(config)
    if config.get("access_token"):
        return config["access_token"]

    cache_key = _token_cache_key(config)
    with _TOKEN_CACHE_LOCK:
        cached = _TOKEN_CACHE.get(cache_key)
        if cached and cached["expires_at"] - TOKEN_REFRESH_BUFFER_SECONDS > time.monotonic():
            return cached["access_token"]

    request_post = request_post or requests.post
    endpoint = f"https://{config['store_domain']}/admin/oauth/access_token"
    try:
        response = request_post(
            endpoint,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "client_credentials",
                "client_id": config["client_id"],
                "client_secret": config["client_secret"],
            },
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        access_token = str(payload.get("access_token") or "").strip()
        if not access_token:
            raise ValueError("Access token missing")
        try:
            expires_in = max(60, int(payload.get("expires_in") or 86400))
        except (TypeError, ValueError):
            expires_in = 86400
    except (requests.RequestException, TypeError, ValueError) as error:
        raise ShopifyAuthenticationError(
            "Shopify client credentials authentication failed. Check app release, scopes, "
            "store domain, Client ID, and Client Secret."
        ) from error

    refreshed_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    with _TOKEN_CACHE_LOCK:
        _TOKEN_CACHE[cache_key] = {
            "access_token": access_token,
            "expires_at": time.monotonic() + expires_in,
            "refreshed_at": refreshed_at,
        }
    return access_token


def graphql_request(query, variables=None, timeout=30, config=None, request_post=None):
    config = config or get_config()
    validate_config(config)
    request_post = request_post or requests.post
    access_token = get_access_token(
        config=config,
        timeout=min(timeout, 15),
        request_post=request_post,
    )
    endpoint = (
        f"https://{config['store_domain']}/admin/api/"
        f"{config['api_version']}/graphql.json"
    )
    try:
        response = request_post(
            endpoint,
            headers={
                "Content-Type": "application/json",
                "X-Shopify-Access-Token": access_token,
            },
            json={"query": query, "variables": variables or {}},
            timeout=timeout,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        raise ShopifyAPIError(
            "Shopify GraphQL sync failed. Check access scopes and API version."
        ) from error

    try:
        payload = response.json()
    except ValueError as error:
        raise ShopifyAPIError(
            "Shopify GraphQL sync failed. Check access scopes and API version."
        ) from error

    if payload.get("errors"):
        raise ShopifyAPIError(
            "Shopify GraphQL sync failed. Check access scopes and API version."
        )
    if not isinstance(payload.get("data"), dict):
        raise ShopifyAPIError(
            "Shopify GraphQL sync failed. Check access scopes and API version."
        )

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


METAFIELDS_SET_MUTATION = """
mutation SportsCaveSetEditionMetafields($metafields: [MetafieldsSetInput!]!) {
  metafieldsSet(metafields: $metafields) {
    metafields {
      id
      namespace
      key
    }
    userErrors {
      field
      message
    }
  }
}
"""


ORDERS_QUERY = """
query SportsCaveOrders($first: Int!, $after: String, $query: String) {
  orders(first: $first, after: $after, query: $query, sortKey: CREATED_AT, reverse: true) {
    pageInfo {
      hasNextPage
      endCursor
    }
    nodes {
      id
      legacyResourceId
      name
      createdAt
      processedAt
      cancelledAt
      displayFinancialStatus
      displayFulfillmentStatus
      email
      totalPriceSet {
        shopMoney {
          amount
          currencyCode
        }
      }
      customer {
        displayName
        firstName
        lastName
        email
      }
      shippingAddress {
        name
        firstName
        lastName
      }
      billingAddress {
        name
        firstName
        lastName
      }
      lineItems(first: 100) {
        nodes {
          id
          title
          quantity
          variantTitle
          sku
          product {
            id
            title
            handle
          }
        }
      }
    }
  }
}
"""

ORDERS_SAFE_QUERY = """
query SportsCaveOrdersSafe($first: Int!, $after: String, $query: String) {
  orders(first: $first, after: $after, query: $query, sortKey: CREATED_AT, reverse: true) {
    pageInfo {
      hasNextPage
      endCursor
    }
    nodes {
      id
      legacyResourceId
      name
      createdAt
      processedAt
      cancelledAt
      displayFinancialStatus
      displayFulfillmentStatus
      lineItems(first: 100) {
        nodes {
          id
          title
          quantity
          variantTitle
          product {
            id
            title
            handle
          }
        }
      }
    }
  }
}
"""


def edition_metafield_inputs(product):
    owner_id = product["shopify_product_id"]
    display_text = product.get("edition_display_text") or build_edition_display_text(product)
    metafields = [
        {
            "ownerId": owner_id,
            "namespace": "sports_cave",
            "key": "edition_limit",
            "type": "number_integer",
            "value": str(product.get("edition_limit") or 100),
        },
        {
            "ownerId": owner_id,
            "namespace": "sports_cave",
            "key": "next_available_edition",
            "type": "number_integer",
            "value": str(product.get("next_available_edition") or 1),
        },
        {
            "ownerId": owner_id,
            "namespace": "sports_cave",
            "key": "editions_sold",
            "type": "number_integer",
            "value": str(product.get("editions_sold") or 0),
        },
        {
            "ownerId": owner_id,
            "namespace": "sports_cave",
            "key": "editions_remaining",
            "type": "number_integer",
            "value": str(product.get("editions_remaining") or 0),
        },
        {
            "ownerId": owner_id,
            "namespace": "sports_cave",
            "key": "edition_status",
            "type": "single_line_text_field",
            "value": product.get("edition_status") or "Available",
        },
        {
            "ownerId": owner_id,
            "namespace": "sports_cave",
            "key": "edition_display_text",
            "type": "single_line_text_field",
            "value": display_text,
        },
    ]
    if product.get("psd_file_url"):
        metafields.append(
            {
                "ownerId": owner_id,
                "namespace": "sports_cave",
                "key": "psd_file_url",
                "type": "url",
                "value": product["psd_file_url"],
            }
        )
    if product.get("prodigi_url"):
        metafields.append(
            {
                "ownerId": owner_id,
                "namespace": "sports_cave",
                "key": "prodigi_url",
                "type": "url",
                "value": product["prodigi_url"],
            }
        )
    return metafields


def build_edition_display_text(product):
    return build_sports_cave_edition_display_text(product)


def sync_edition_metafields(product, config=None, request_post=None):
    try:
        data, served_version = graphql_request(
            METAFIELDS_SET_MUTATION,
            variables={"metafields": edition_metafield_inputs(product)},
            config=config,
            request_post=request_post,
        )
        result = data.get("metafieldsSet") or {}
        if result.get("userErrors"):
            raise ShopifyAPIError(
                "Could not sync storefront edition display. Check Shopify scopes and product metafields."
            )
        return {
            "count": len(result.get("metafields") or []),
            "api_version": served_version or (config or get_config()).get("api_version"),
        }
    except ShopifyAPIError:
        raise ShopifyAPIError(
            "Could not sync storefront edition display. Check Shopify scopes and product metafields."
        )


def build_order_admin_url(store_domain, legacy_resource_id):
    if not store_domain or not legacy_resource_id:
        return ""
    store_slug = store_domain.split(".", 1)[0]
    return f"https://admin.shopify.com/store/{store_slug}/orders/{legacy_resource_id}"


def normalize_order(node, store_domain):
    customer = node.get("customer") or {}
    shipping_address = node.get("shippingAddress") or {}
    billing_address = node.get("billingAddress") or {}
    total_price = ((node.get("totalPriceSet") or {}).get("shopMoney") or {})
    customer_full_name = " ".join(
        part for part in (customer.get("firstName"), customer.get("lastName")) if part
    ).strip()
    shipping_full_name = " ".join(
        part for part in (shipping_address.get("firstName"), shipping_address.get("lastName")) if part
    ).strip()
    billing_full_name = " ".join(
        part for part in (billing_address.get("firstName"), billing_address.get("lastName")) if part
    ).strip()
    customer_email = customer.get("email") or node.get("email") or ""
    customer_name = (
        customer.get("displayName")
        or customer_full_name
        or shipping_address.get("name")
        or shipping_full_name
        or billing_address.get("name")
        or billing_full_name
        or customer_email
        or ""
    )
    line_items = []
    for item in (node.get("lineItems") or {}).get("nodes") or []:
        product = item.get("product") or {}
        line_items.append(
            {
                "shopify_line_item_id": item.get("id") or "",
                "shopify_product_id": product.get("id") or "",
                "product_title": product.get("title") or item.get("title") or "",
                "product_handle": product.get("handle") or "",
                "variant_title": item.get("variantTitle") or "",
                "sku": item.get("sku") or "",
                "quantity": int(item.get("quantity") or 1),
            }
        )
    legacy_resource_id = str(node.get("legacyResourceId") or "")
    financial_status = node.get("displayFinancialStatus") or ""
    return {
        "shopify_order_id": node.get("id") or "",
        "legacy_resource_id": legacy_resource_id,
        "order_name": node.get("name") or "",
        "order_number": (node.get("name") or "").lstrip("#"),
        "admin_url": build_order_admin_url(store_domain, legacy_resource_id),
        "created_at": node.get("createdAt") or "",
        "processed_at": node.get("processedAt") or "",
        "paid_at": node.get("processedAt") if financial_status == "PAID" else "",
        "financial_status": financial_status,
        "fulfillment_status": node.get("displayFulfillmentStatus") or "",
        "customer_name": customer_name,
        "customer_email": customer_email,
        "total_price": str(total_price.get("amount") or ""),
        "currency": total_price.get("currencyCode") or "",
        "cancelled_at": node.get("cancelledAt") or "",
        "line_items": line_items,
    }


def fetch_orders_page(after=None, days=60, page_size=DEFAULT_PAGE_SIZE, config=None, request_post=None):
    config = config or get_config()
    first = min(max(int(page_size), 1), 25)
    created_after = (datetime.now(timezone.utc) - timedelta(days=max(int(days), 1))).date().isoformat()
    query = f"created_at:>={created_after}"
    variables = {"first": first, "after": after, "query": query}
    try:
        data, served_version = graphql_request(
            ORDERS_QUERY,
            variables=variables,
            config=config,
            request_post=request_post,
        )
    except ShopifyAPIError:
        data, served_version = graphql_request(
            ORDERS_SAFE_QUERY,
            variables=variables,
            config=config,
            request_post=request_post,
        )
    connection = data.get("orders") or {}
    nodes = connection.get("nodes") or []
    orders = [normalize_order(node, config["store_domain"]) for node in nodes]
    page_info = connection.get("pageInfo") or {}
    return {
        "orders": orders,
        "has_next_page": bool(page_info.get("hasNextPage")),
        "end_cursor": page_info.get("endCursor"),
        "api_version": served_version or config.get("api_version"),
    }


def iter_order_pages(days=60, page_size=DEFAULT_PAGE_SIZE, config=None, request_post=None):
    config = config or get_config()
    after = None
    orders_seen = 0
    while orders_seen < config["max_orders"]:
        page = fetch_orders_page(
            after=after,
            days=days,
            page_size=min(page_size, config["max_orders"] - orders_seen),
            config=config,
            request_post=request_post,
        )
        if not page["orders"]:
            break
        orders_seen += len(page["orders"])
        yield page
        if not page["has_next_page"] or not page["end_cursor"]:
            break
        after = page["end_cursor"]


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
