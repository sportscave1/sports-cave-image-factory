import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import requests


DEFAULT_API_VERSION = "2026-04"
DEFAULT_PAGE_SIZE = 50
DEFAULT_MAX_PRODUCTS = 500
DEFAULT_MAX_ORDERS = 250
DEFAULT_EDITION_OPS_MAX_PRODUCTS = 500
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
    edition_ops_max_products_raw = os.getenv(
        "SHOPIFY_EDITION_OPS_MAX_PRODUCTS",
        str(DEFAULT_EDITION_OPS_MAX_PRODUCTS),
    ).strip()
    try:
        max_products = max(1, int(max_products_raw))
    except ValueError:
        max_products = DEFAULT_MAX_PRODUCTS
    try:
        max_orders = max(1, int(max_orders_raw))
    except ValueError:
        max_orders = DEFAULT_MAX_ORDERS
    try:
        edition_ops_max_products = max(1, int(edition_ops_max_products_raw))
    except ValueError:
        edition_ops_max_products = DEFAULT_EDITION_OPS_MAX_PRODUCTS

    if client_id and client_secret:
        auth_mode = "Client credentials mode"
    elif access_token:
        auth_mode = "Admin access token mode"
    else:
        auth_mode = "Missing credentials"

    return {
        "store_domain": store_domain,
        "access_token": access_token,
        "has_legacy_admin_token": bool(access_token),
        "client_id": client_id,
        "client_secret": client_secret,
        "api_version": api_version,
        "max_products": max_products,
        "max_orders": max_orders,
        "edition_ops_max_products": edition_ops_max_products,
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
    if config.get("client_id") and config.get("client_secret"):
        with _TOKEN_CACHE_LOCK:
            cached = _TOKEN_CACHE.get(_token_cache_key(config)) or {}
        return {
            "auth_mode": "Client credentials mode",
            "last_refresh": cached.get("refreshed_at"),
            "cached": bool(cached.get("access_token")),
            "scopes": cached.get("scopes") or [],
        }
    if config.get("access_token"):
        return {
            "auth_mode": "Admin access token mode",
            "last_refresh": None,
            "cached": False,
            "scopes": [],
        }

    return {
        "auth_mode": config.get("auth_mode", "Missing credentials"),
        "last_refresh": None,
        "cached": False,
        "scopes": [],
    }


def _sanitize_shopify_error_text(value, config):
    text = str(value or "")
    for secret_value in (
        config.get("client_secret"),
        config.get("access_token"),
    ):
        if secret_value:
            text = text.replace(str(secret_value), "[redacted]")
    return text[:2000]


def _parse_scopes(value):
    if isinstance(value, (list, tuple, set)):
        return sorted({str(item).strip() for item in value if str(item).strip()})
    return sorted({part.strip() for part in str(value or "").replace(",", " ").split() if part.strip()})


def _scope_status(scopes):
    scope_set = set(scopes or [])
    return {
        "read_orders": "read_orders" in scope_set,
        "write_orders": "write_orders" in scope_set,
        "read_products": "read_products" in scope_set,
        "write_products": "write_products" in scope_set,
        "read_customers": "read_customers" in scope_set,
        "write_files": "write_files" in scope_set,
    }


def get_shopify_access_token_details(config=None, timeout=10, request_post=None, force_refresh=False):
    config = config or get_config()
    validate_config(config)
    if not (config.get("client_id") and config.get("client_secret")):
        return {
            "access_token": config["access_token"],
            "auth_mode": "Admin access token mode",
            "scope": "",
            "scopes": [],
            "scope_status": {},
            "expires_in": None,
            "refreshed_at": None,
            "cached": False,
        }

    cache_key = _token_cache_key(config)
    with _TOKEN_CACHE_LOCK:
        cached = _TOKEN_CACHE.get(cache_key)
        if (
            not force_refresh
            and cached
            and cached["expires_at"] - TOKEN_REFRESH_BUFFER_SECONDS > time.monotonic()
        ):
            return {
                "access_token": cached["access_token"],
                "auth_mode": "Client credentials mode",
                "scope": cached.get("scope", ""),
                "scopes": cached.get("scopes") or [],
                "scope_status": _scope_status(cached.get("scopes") or []),
                "expires_in": cached.get("expires_in"),
                "refreshed_at": cached.get("refreshed_at"),
                "cached": True,
            }

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
        scope = str(payload.get("scope") or "")
        scopes = _parse_scopes(scope)
        try:
            expires_in = max(60, int(payload.get("expires_in") or 86400))
        except (TypeError, ValueError):
            expires_in = 86400
    except requests.RequestException as error:
        response = getattr(error, "response", None)
        status_code = getattr(response, "status_code", None) or getattr(
            locals().get("response", None),
            "status_code",
            "unknown",
        )
        response_body = ""
        if response is not None:
            response_body = getattr(response, "text", "") or ""
        elif "response" in locals():
            response_body = getattr(locals()["response"], "text", "") or ""
        raise ShopifyAuthenticationError(
            "Shopify client credentials authentication failed. "
            f"Token request status: {status_code}. "
            f"Response: {_sanitize_shopify_error_text(response_body, config)}"
        ) from error
    except (TypeError, ValueError) as error:
        response_body = ""
        if "response" in locals():
            response_body = getattr(locals()["response"], "text", "") or ""
        raise ShopifyAuthenticationError(
            "Shopify client credentials authentication failed. "
            f"Token response was invalid. Response: {_sanitize_shopify_error_text(response_body, config)}"
        ) from error

    refreshed_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    with _TOKEN_CACHE_LOCK:
        _TOKEN_CACHE[cache_key] = {
            "access_token": access_token,
            "expires_at": time.monotonic() + expires_in,
            "expires_in": expires_in,
            "refreshed_at": refreshed_at,
            "scope": scope,
            "scopes": scopes,
        }
    return {
        "access_token": access_token,
        "auth_mode": "Client credentials mode",
        "scope": scope,
        "scopes": scopes,
        "scope_status": _scope_status(scopes),
        "expires_in": expires_in,
        "refreshed_at": refreshed_at,
        "cached": False,
    }


def get_shopify_access_token(config=None, timeout=10, request_post=None):
    return get_shopify_access_token_details(
        config=config,
        timeout=timeout,
        request_post=request_post,
    )["access_token"]


def get_access_token(config=None, timeout=10, request_post=None):
    return get_shopify_access_token(
        config=config,
        timeout=timeout,
        request_post=request_post,
    )


def graphql_request(query, variables=None, timeout=10, config=None, request_post=None):
    config = config or get_config()
    validate_config(config)
    request_post = request_post or requests.post
    access_token = get_shopify_access_token(
        config=config,
        timeout=min(timeout, 10),
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
        response = getattr(error, "response", None)
        status_code = getattr(response, "status_code", None) or getattr(
            locals().get("response", None),
            "status_code",
            "unknown",
        )
        response_body = ""
        if response is not None:
            response_body = getattr(response, "text", "") or ""
        elif "response" in locals():
            response_body = getattr(locals()["response"], "text", "") or ""
        raise ShopifyAPIError(
            "Shopify GraphQL sync failed. "
            f"Status: {status_code}. Response: {_sanitize_shopify_error_text(response_body, config)}"
        ) from error

    try:
        payload = response.json()
    except ValueError as error:
        raise ShopifyAPIError(
            "Shopify GraphQL sync failed. Check access scopes and API version."
        ) from error

    if payload.get("errors"):
        error_text = _sanitize_shopify_error_text(payload.get("errors"), config)
        raise ShopifyAPIError(
            f"Shopify GraphQL sync failed. Errors: {error_text}"
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


LIMITED_EDITION_PRODUCTS_QUERY = """
query SportsCaveLimitedEditionProducts($first: Int!, $after: String, $query: String) {
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
      media(first: 1) {
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
      metafields(first: 10, namespace: "sports_cave") {
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


EDITION_OPS_ACTIVE_PRODUCTS_QUERY = """
query EditionOpsActiveProducts($first: Int!, $after: String, $query: String) {
  products(first: $first, after: $after, query: $query, sortKey: TITLE) {
    pageInfo { hasNextPage endCursor }
    nodes {
      id
      legacyResourceId
      title
      handle
      status
      onlineStoreUrl
      media(first: 1) {
        nodes {
          ... on MediaImage {
            image { url }
          }
        }
      }
      metafields(first: 20, namespace: "sports_cave") {
        nodes { namespace key type value }
      }
    }
  }
}
"""


PRODUCT_BY_ID_QUERY = """
query SportsCaveProductById($id: ID!) {
  product(id: $id) {
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
"""


def test_connection(config=None, request_post=None):
    config = config or get_config()
    token_details = get_shopify_access_token_details(
        config=config,
        request_post=request_post,
    )
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
        "api_version": served_version or config.get("api_version"),
        "auth_mode": token_details.get("auth_mode") or config.get("auth_mode"),
        "scopes": token_details.get("scopes") or [],
        "scope_status": token_details.get("scope_status") or {},
        "ok": True,
        "message": "Shopify connection works.",
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


LIMITED_EDITION_DEFAULTS = {
    "edition_enabled": False,
    "edition_total": 100,
    "edition_next_number": 1,
    "edition_label": "Numbered Edition",
}
EDITION_OPS_METAFIELDS_PER_PRODUCT = 7
SHOPIFY_METAFIELDS_SET_LIMIT = 25


EDITION_OPS_METAFIELD_DEFINITIONS = [
    {
        "name": "Sports Cave Edition Enabled",
        "namespace": "sports_cave",
        "key": "edition_enabled",
        "type": "boolean",
        "ownerType": "PRODUCT",
    },
    {
        "name": "Sports Cave Edition Total",
        "namespace": "sports_cave",
        "key": "edition_total",
        "type": "number_integer",
        "ownerType": "PRODUCT",
    },
    {
        "name": "Sports Cave Next Edition Number",
        "namespace": "sports_cave",
        "key": "edition_next_number",
        "type": "number_integer",
        "ownerType": "PRODUCT",
    },
    {
        "name": "Sports Cave Edition Sold Count",
        "namespace": "sports_cave",
        "key": "edition_sold_count",
        "type": "number_integer",
        "ownerType": "PRODUCT",
    },
    {
        "name": "Sports Cave Edition Remaining",
        "namespace": "sports_cave",
        "key": "edition_remaining",
        "type": "number_integer",
        "ownerType": "PRODUCT",
    },
    {
        "name": "Sports Cave Edition Status",
        "namespace": "sports_cave",
        "key": "edition_status",
        "type": "single_line_text_field",
        "ownerType": "PRODUCT",
    },
    {
        "name": "Sports Cave Edition Label",
        "namespace": "sports_cave",
        "key": "edition_label",
        "type": "single_line_text_field",
        "ownerType": "PRODUCT",
    },
]

ORDER_ALLOCATION_METAFIELD_DEFINITIONS = [
    {
        "name": "Sports Cave Edition Allocations",
        "namespace": "sports_cave",
        "key": "edition_allocations",
        "type": "json",
        "ownerType": "ORDER",
    },
]


def _metafields_by_key(metafields):
    return {
        item.get("key"): item
        for item in (metafields or [])
        if item.get("namespace") == "sports_cave" and item.get("key")
    }


def _parse_bool_metafield(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return bool(default)
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    return bool(default)


def _parse_int_metafield(value, default):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return int(default)


def calculate_limited_edition_remaining(edition_total, edition_next_number):
    total = max(_parse_int_metafield(edition_total, LIMITED_EDITION_DEFAULTS["edition_total"]), 1)
    next_number = max(_parse_int_metafield(edition_next_number, LIMITED_EDITION_DEFAULTS["edition_next_number"]), 1)
    return max(total - next_number + 1, 0)


def calculate_limited_edition_sold_count(edition_next_number):
    next_number = max(_parse_int_metafield(edition_next_number, LIMITED_EDITION_DEFAULTS["edition_next_number"]), 1)
    return max(next_number - 1, 0)


def calculate_limited_edition_status(remaining):
    remaining = max(_parse_int_metafield(remaining, 0), 0)
    if remaining <= 0:
        return "Sold Out Archive"
    if remaining <= 5:
        return "Final Editions"
    if remaining <= 12:
        return "Selling Quickly"
    return "Limited Edition"


def normalize_limited_edition_metafields(metafields):
    by_key = _metafields_by_key(metafields)
    edition_total = max(
        _parse_int_metafield(
            (by_key.get("edition_total") or {}).get("value"),
            LIMITED_EDITION_DEFAULTS["edition_total"],
        ),
        1,
    )
    edition_next_number = max(
        _parse_int_metafield(
            (by_key.get("edition_next_number") or {}).get("value"),
            LIMITED_EDITION_DEFAULTS["edition_next_number"],
        ),
        1,
    )
    edition_label = str(
        (by_key.get("edition_label") or {}).get("value")
        or LIMITED_EDITION_DEFAULTS["edition_label"]
    ).strip() or LIMITED_EDITION_DEFAULTS["edition_label"]
    sold_count = calculate_limited_edition_sold_count(edition_next_number)
    remaining = max(edition_total - sold_count, 0)
    status = calculate_limited_edition_status(remaining)
    enabled = _parse_bool_metafield(
        (by_key.get("edition_enabled") or {}).get("value"),
        LIMITED_EDITION_DEFAULTS["edition_enabled"],
    )
    return {
        "edition_enabled": enabled,
        "edition_total": edition_total,
        "edition_next_number": edition_next_number,
        "edition_sold_count": sold_count,
        "edition_remaining": remaining,
        "edition_status": status,
        "edition_label": edition_label,
        "remaining": remaining,
    }


def normalize_limited_edition_product(node, store_domain):
    media_nodes = (node.get("media") or {}).get("nodes") or []
    thumbnail_url = ""
    if media_nodes:
        image = (media_nodes[0].get("image") or {})
        thumbnail_url = image.get("url") or ""
    metafields = ((node.get("metafields") or {}).get("nodes") or [])
    legacy_resource_id = str(node.get("legacyResourceId") or "")
    return {
        "shopify_product_id": node.get("id") or "",
        "legacy_resource_id": legacy_resource_id,
        "title": node.get("title") or "Untitled Shopify Product",
        "handle": node.get("handle") or "",
        "status": node.get("status") or "UNKNOWN",
        "thumbnail_url": thumbnail_url,
        "admin_url": build_admin_url(store_domain, legacy_resource_id),
        "metafields": metafields,
        "edition": normalize_limited_edition_metafields(metafields),
    }


def normalize_edition_ops_product(node, store_domain):
    media_nodes = (node.get("media") or {}).get("nodes") or []
    thumbnail_url = ""
    if media_nodes:
        thumbnail_url = ((media_nodes[0].get("image") or {}).get("url") or "")
    metafields = ((node.get("metafields") or {}).get("nodes") or [])
    legacy_resource_id = str(node.get("legacyResourceId") or "")
    return {
        "shopify_product_id": node.get("id") or "",
        "legacy_resource_id": legacy_resource_id,
        "title": node.get("title") or "Untitled Shopify Product",
        "handle": node.get("handle") or "",
        "status": node.get("status") or "UNKNOWN",
        "thumbnail_url": thumbnail_url,
        "online_store_url": node.get("onlineStoreUrl") or "",
        "admin_url": build_admin_url(store_domain, legacy_resource_id),
        "metafields": metafields,
        "edition": normalize_limited_edition_metafields(metafields),
    }


def shopify_gid(resource_type, value):
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.startswith("gid://"):
        return raw
    return f"gid://shopify/{resource_type}/{raw}"


def fetch_product_by_shopify_id(shopify_product_id, config=None, request_post=None):
    config = config or get_config()
    product_gid = shopify_gid("Product", shopify_product_id)
    if not product_gid:
        raise ShopifyAPIError("Shopify product ID is missing.")
    data, served_version = graphql_request(
        PRODUCT_BY_ID_QUERY,
        variables={"id": product_gid},
        config=config,
        request_post=request_post,
    )
    product = data.get("product")
    if not product:
        raise ShopifyAPIError("Shopify product could not be found.")
    normalized = normalize_product(product, config["store_domain"])
    normalized["api_version"] = served_version or config.get("api_version")
    return normalized


METAFIELDS_SET_MUTATION = """
mutation SportsCaveSetEditionMetafields($metafields: [MetafieldsSetInput!]!) {
  metafieldsSet(metafields: $metafields) {
    metafields {
      id
      namespace
      key
      type
      value
      compareDigest
    }
    userErrors {
      field
      message
    }
  }
}
"""


METAFIELD_DEFINITIONS_QUERY = """
query SportsCaveEditionMetafieldDefinitions($ownerType: MetafieldOwnerType!, $namespace: String!) {
  metafieldDefinitions(first: 50, ownerType: $ownerType, namespace: $namespace) {
    nodes {
      id
      name
      namespace
      key
      ownerType
      type {
        name
      }
    }
  }
}
"""


METAFIELD_DEFINITION_CREATE_MUTATION = """
mutation SportsCaveEditionMetafieldDefinitionCreate($definition: MetafieldDefinitionInput!) {
  metafieldDefinitionCreate(definition: $definition) {
    createdDefinition {
      id
      name
      namespace
      key
      ownerType
      type {
        name
      }
    }
    userErrors {
      field
      message
      code
    }
  }
}
"""


METAFIELDS_BY_OWNER_QUERY = """
query SportsCaveMetafieldsByOwner($id: ID!, $namespace: String!) {
  node(id: $id) {
    ... on Product {
      id
      metafields(first: 50, namespace: $namespace) {
        nodes {
          namespace
          key
          type
          value
          compareDigest
        }
      }
    }
    ... on Order {
      id
      metafields(first: 50, namespace: $namespace) {
        nodes {
          namespace
          key
          type
          value
          compareDigest
        }
      }
    }
  }
}
"""


ORDERS_QUERY = """
query SportsCaveOrders($first: Int!, $after: String, $query: String) {
  orders(first: $first, after: $after, query: $query, sortKey: UPDATED_AT, reverse: true) {
    pageInfo {
      hasNextPage
      endCursor
    }
    nodes {
      id
      legacyResourceId
      name
      createdAt
      updatedAt
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
        id
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
      shippingLine {
        title
        code
      }
      shippingLines(first: 1) {
        nodes {
          title
          code
        }
      }
      billingAddress {
        name
        firstName
        lastName
      }
      metafields(first: 20, namespace: "sports_cave") {
        nodes {
          namespace
          key
          type
          value
          compareDigest
        }
      }
      lineItems(first: 100) {
        nodes {
          id
          title
          quantity
          variantTitle
          sku
          variant {
            id
            title
            sku
          }
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
  orders(first: $first, after: $after, query: $query, sortKey: UPDATED_AT, reverse: true) {
    pageInfo {
      hasNextPage
      endCursor
    }
    nodes {
      id
      legacyResourceId
      name
      createdAt
      updatedAt
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
        id
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
      shippingLine {
        title
        code
      }
      shippingLines(first: 1) {
        nodes {
          title
          code
        }
      }
      metafields(first: 20, namespace: "sports_cave") {
        nodes {
          namespace
          key
          type
          value
          compareDigest
        }
      }
      lineItems(first: 100) {
        nodes {
          id
          title
          quantity
          variantTitle
          sku
          variant {
            id
            title
            sku
          }
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


def _string_value(value, default=""):
    if value is None:
        return str(default)
    return str(value)


def _bool_value(value):
    return "true" if bool(value) else "false"


def _metafield_input(owner_id, key, metafield_type, value, namespace="sports_cave", compare_digest=None):
    data = {
        "ownerId": owner_id,
        "namespace": namespace,
        "key": key,
        "type": metafield_type,
        "value": _string_value(value),
    }
    if compare_digest is not None:
        data["compareDigest"] = compare_digest
    return data


def _metafields_user_error_text(errors):
    messages = []
    for error in errors or []:
        field = ", ".join(str(item) for item in (error.get("field") or []))
        message = error.get("message") or "Unknown Shopify metafield error"
        messages.append(f"{field}: {message}" if field else message)
    return "; ".join(messages)


def metafields_set(metafields, config=None, request_post=None):
    inputs = [item for item in (metafields or []) if item.get("ownerId") and item.get("key")]
    if not inputs:
        return {"count": 0, "metafields": [], "api_version": (config or get_config()).get("api_version")}
    data, served_version = graphql_request(
        METAFIELDS_SET_MUTATION,
        variables={"metafields": inputs},
        config=config,
        request_post=request_post,
    )
    result = data.get("metafieldsSet") or {}
    if result.get("userErrors"):
        raise ShopifyAPIError(_metafields_user_error_text(result.get("userErrors")))
    metafields = result.get("metafields") or []
    return {
        "count": len(metafields),
        "metafields": metafields,
        "api_version": served_version or (config or get_config()).get("api_version"),
    }


def fetch_metafields(owner_id, namespace="sports_cave", config=None, request_post=None):
    if not owner_id:
        raise ShopifyAPIError("Shopify owner ID is missing.")
    data, served_version = graphql_request(
        METAFIELDS_BY_OWNER_QUERY,
        variables={"id": owner_id, "namespace": namespace},
        config=config,
        request_post=request_post,
    )
    node = data.get("node") or {}
    metafields = ((node.get("metafields") or {}).get("nodes") or [])
    return {"metafields": metafields, "api_version": served_version or (config or get_config()).get("api_version")}


def fetch_limited_edition_products_page(after=None, search="", page_size=25, config=None, request_post=None):
    config = config or get_config()
    first = min(max(int(page_size), 1), 50)
    data, served_version = graphql_request(
        LIMITED_EDITION_PRODUCTS_QUERY,
        variables={
            "first": first,
            "after": after or None,
            "query": str(search or "").strip() or None,
        },
        config=config,
        request_post=request_post,
    )
    connection = data.get("products") or {}
    nodes = connection.get("nodes") or []
    products = [normalize_limited_edition_product(node, config["store_domain"]) for node in nodes]
    page_info = connection.get("pageInfo") or {}
    return {
        "products": products,
        "has_next_page": bool(page_info.get("hasNextPage")),
        "end_cursor": page_info.get("endCursor"),
        "api_version": served_version or config.get("api_version"),
    }


def fetch_edition_ops_active_products_page(after=None, page_size=50, config=None, request_post=None):
    config = config or get_config()
    first = min(max(int(page_size), 1), 50)
    data, served_version = graphql_request(
        EDITION_OPS_ACTIVE_PRODUCTS_QUERY,
        variables={
            "first": first,
            "after": after or None,
            "query": "status:active",
        },
        config=config,
        request_post=request_post,
    )
    connection = data.get("products") or {}
    nodes = connection.get("nodes") or []
    products = [normalize_edition_ops_product(node, config["store_domain"]) for node in nodes]
    page_info = connection.get("pageInfo") or {}
    return {
        "products": products,
        "has_next_page": bool(page_info.get("hasNextPage")),
        "end_cursor": page_info.get("endCursor"),
        "api_version": served_version or config.get("api_version"),
    }


def fetch_edition_ops_active_products(max_products=None, page_size=50, config=None, request_post=None):
    config = config or get_config()
    limit = max(1, int(max_products if max_products is not None else config.get("edition_ops_max_products", DEFAULT_EDITION_OPS_MAX_PRODUCTS)))
    after = None
    products = []
    served_version = config.get("api_version")
    while len(products) < limit:
        page = fetch_edition_ops_active_products_page(
            after=after,
            page_size=min(int(page_size or 50), limit - len(products)),
            config=config,
            request_post=request_post,
        )
        products.extend(page.get("products") or [])
        served_version = page.get("api_version") or served_version
        if not page.get("has_next_page") or not page.get("end_cursor"):
            break
        after = page.get("end_cursor")
    return {
        "products": products[:limit],
        "api_version": served_version,
        "max_products": limit,
    }


def limited_edition_metafield_inputs(product_id, values):
    owner_id = shopify_gid("Product", product_id)
    if not owner_id:
        raise ShopifyAPIError("Shopify product ID is missing.")
    edition_total = max(
        _parse_int_metafield(values.get("edition_total"), LIMITED_EDITION_DEFAULTS["edition_total"]),
        1,
    )
    edition_next_number = max(
        _parse_int_metafield(values.get("edition_next_number"), LIMITED_EDITION_DEFAULTS["edition_next_number"]),
        1,
    )
    edition_sold_count = calculate_limited_edition_sold_count(edition_next_number)
    edition_remaining = max(edition_total - edition_sold_count, 0)
    edition_status = calculate_limited_edition_status(edition_remaining)
    return [
        _metafield_input(
            owner_id,
            "edition_enabled",
            "boolean",
            _bool_value(values.get("edition_enabled")),
        ),
        _metafield_input(owner_id, "edition_total", "number_integer", edition_total),
        _metafield_input(owner_id, "edition_next_number", "number_integer", edition_next_number),
        _metafield_input(owner_id, "edition_sold_count", "number_integer", edition_sold_count),
        _metafield_input(owner_id, "edition_remaining", "number_integer", edition_remaining),
        _metafield_input(owner_id, "edition_status", "single_line_text_field", edition_status),
        _metafield_input(
            owner_id,
            "edition_label",
            "single_line_text_field",
            str(values.get("edition_label") or LIMITED_EDITION_DEFAULTS["edition_label"]).strip()
            or LIMITED_EDITION_DEFAULTS["edition_label"],
        ),
    ]


def save_limited_edition_metafields(product_id, values, config=None, request_post=None):
    owner_id = shopify_gid("Product", product_id)
    metafields_set(
        limited_edition_metafield_inputs(owner_id, values),
        config=config,
        request_post=request_post,
    )
    readback = fetch_metafields(
        owner_id,
        namespace="sports_cave",
        config=config,
        request_post=request_post,
    )
    metafields = readback.get("metafields") or []
    return {
        "metafields": metafields,
        "edition": normalize_limited_edition_metafields(metafields),
        "api_version": readback.get("api_version"),
    }


def sync_limited_edition_metafields_for_products(products, config=None, request_post=None):
    config = config or get_config()
    rows = [row for row in (products or []) if row.get("shopify_product_id")]
    results = []
    synced = 0
    failed = 0

    products_per_batch = max(1, SHOPIFY_METAFIELDS_SET_LIMIT // EDITION_OPS_METAFIELDS_PER_PRODUCT)
    for index in range(0, len(rows), products_per_batch):
        chunk = rows[index : index + products_per_batch]
        inputs = []
        for row in chunk:
            inputs.extend(limited_edition_metafield_inputs(row["shopify_product_id"], row))

        try:
            metafields_set(inputs, config=config, request_post=request_post)
            for row in chunk:
                results.append(
                    {
                        "shopify_product_id": row["shopify_product_id"],
                        "title": row.get("title") or row.get("handle") or row["shopify_product_id"],
                        "ok": True,
                        "message": "Synced",
                    }
                )
                synced += 1
        except Exception as batch_error:
            for row in chunk:
                try:
                    metafields_set(
                        limited_edition_metafield_inputs(row["shopify_product_id"], row),
                        config=config,
                        request_post=request_post,
                    )
                    results.append(
                        {
                            "shopify_product_id": row["shopify_product_id"],
                            "title": row.get("title") or row.get("handle") or row["shopify_product_id"],
                            "ok": True,
                            "message": "Synced",
                        }
                    )
                    synced += 1
                except Exception as product_error:
                    results.append(
                        {
                            "shopify_product_id": row["shopify_product_id"],
                            "title": row.get("title") or row.get("handle") or row["shopify_product_id"],
                            "ok": False,
                            "message": str(product_error) or str(batch_error),
                        }
                    )
                    failed += 1

    return {"synced": synced, "failed": failed, "results": results}


def list_edition_ops_metafield_definitions(config=None, request_post=None):
    config = config or get_config()
    data, served_version = graphql_request(
        METAFIELD_DEFINITIONS_QUERY,
        variables={"ownerType": "PRODUCT", "namespace": "sports_cave"},
        config=config,
        request_post=request_post,
    )
    existing = {}
    for node in ((data.get("metafieldDefinitions") or {}).get("nodes") or []):
        key = node.get("key") or ""
        type_node = node.get("type") or {}
        existing[key] = {
            "id": node.get("id") or "",
            "name": node.get("name") or "",
            "namespace": node.get("namespace") or "",
            "key": key,
            "ownerType": node.get("ownerType") or "",
            "type": type_node.get("name") or "",
        }

    definitions = []
    for required in EDITION_OPS_METAFIELD_DEFINITIONS:
        found = existing.get(required["key"])
        ready = bool(
            found
            and found.get("namespace") == required["namespace"]
            and found.get("ownerType") == required["ownerType"]
            and found.get("type") == required["type"]
        )
        definitions.append(
            {
                **required,
                "id": (found or {}).get("id", ""),
                "found_type": (found or {}).get("type", ""),
                "status": "Ready" if ready else ("Type mismatch" if found else "Missing"),
            }
        )
    return {"definitions": definitions, "api_version": served_version or config.get("api_version")}


def list_order_allocation_metafield_definitions(config=None, request_post=None):
    config = config or get_config()
    data, served_version = graphql_request(
        METAFIELD_DEFINITIONS_QUERY,
        variables={"ownerType": "ORDER", "namespace": "sports_cave"},
        config=config,
        request_post=request_post,
    )
    existing = {}
    for node in ((data.get("metafieldDefinitions") or {}).get("nodes") or []):
        key = node.get("key") or ""
        type_node = node.get("type") or {}
        existing[key] = {
            "id": node.get("id") or "",
            "name": node.get("name") or "",
            "namespace": node.get("namespace") or "",
            "key": key,
            "ownerType": node.get("ownerType") or "",
            "type": type_node.get("name") or "",
        }

    definitions = []
    for required in ORDER_ALLOCATION_METAFIELD_DEFINITIONS:
        found = existing.get(required["key"])
        ready = bool(
            found
            and found.get("namespace") == required["namespace"]
            and found.get("ownerType") == required["ownerType"]
            and found.get("type") == required["type"]
        )
        definitions.append(
            {
                **required,
                "id": (found or {}).get("id", ""),
                "found_type": (found or {}).get("type", ""),
                "status": "Ready" if ready else ("Type mismatch" if found else "Missing"),
            }
        )
    return {"definitions": definitions, "api_version": served_version or config.get("api_version")}


def create_edition_ops_metafield_definition(definition, config=None, request_post=None):
    config = config or get_config()
    data, served_version = graphql_request(
        METAFIELD_DEFINITION_CREATE_MUTATION,
        variables={
            "definition": {
                "name": definition["name"],
                "namespace": definition["namespace"],
                "key": definition["key"],
                "type": definition["type"],
                "ownerType": definition["ownerType"],
            }
        },
        config=config,
        request_post=request_post,
    )
    result = data.get("metafieldDefinitionCreate") or {}
    if result.get("userErrors"):
        raise ShopifyAPIError(_metafields_user_error_text(result.get("userErrors")))
    created = result.get("createdDefinition") or {}
    return {"definition": created, "api_version": served_version or config.get("api_version")}


def create_order_allocation_metafield_definition(definition, config=None, request_post=None):
    return create_edition_ops_metafield_definition(definition, config=config, request_post=request_post)


def create_missing_edition_ops_metafield_definitions(config=None, request_post=None):
    config = config or get_config()
    checked = list_edition_ops_metafield_definitions(config=config, request_post=request_post)
    created = []
    skipped = []
    errors = []
    for definition in checked.get("definitions") or []:
        if definition.get("status") == "Ready":
            skipped.append({**definition, "message": "Already exists"})
            continue
        if definition.get("status") == "Type mismatch":
            errors.append({**definition, "message": "Definition exists with a different type"})
            continue
        try:
            created_result = create_edition_ops_metafield_definition(
                definition,
                config=config,
                request_post=request_post,
            )
            created.append({**definition, "message": "Created", "created": created_result.get("definition")})
        except Exception as error:
            errors.append({**definition, "message": str(error)})
    refreshed = list_edition_ops_metafield_definitions(config=config, request_post=request_post)
    return {
        "created": created,
        "skipped": skipped,
        "errors": errors,
        "definitions": refreshed.get("definitions") or [],
        "api_version": refreshed.get("api_version") or checked.get("api_version"),
    }


def create_missing_order_allocation_metafield_definitions(config=None, request_post=None):
    config = config or get_config()
    checked = list_order_allocation_metafield_definitions(config=config, request_post=request_post)
    created = []
    skipped = []
    errors = []
    for definition in checked.get("definitions") or []:
        if definition.get("status") == "Ready":
            skipped.append({**definition, "message": "Already exists"})
            continue
        if definition.get("status") == "Type mismatch":
            errors.append({**definition, "message": "Definition exists with a different type"})
            continue
        try:
            created_result = create_order_allocation_metafield_definition(
                definition,
                config=config,
                request_post=request_post,
            )
            created.append({**definition, "message": "Created", "created": created_result.get("definition")})
        except Exception as error:
            errors.append({**definition, "message": str(error)})
    refreshed = list_order_allocation_metafield_definitions(config=config, request_post=request_post)
    return {
        "created": created,
        "skipped": skipped,
        "errors": errors,
        "definitions": refreshed.get("definitions") or [],
        "api_version": refreshed.get("api_version") or checked.get("api_version"),
    }


def product_edition_metafield_inputs(product):
    owner_id = shopify_gid(
        "Product",
        product.get("shopify_product_gid") or product.get("shopify_product_id") or product.get("product_gid"),
    )
    display_text = product.get("edition_display_text") or build_edition_display_text(product)
    edition_total = product.get("edition_total") or product.get("edition_limit") or 100
    next_number = product.get("next_edition_number") or product.get("next_available_edition") or 1
    last_assigned = product.get("last_assigned_edition") or 0
    sold_count = product.get("sold_count") or product.get("editions_sold") or 0
    remaining = product.get("remaining_count")
    if remaining is None:
        remaining = product.get("remaining_editions")
    if remaining is None:
        remaining = product.get("editions_remaining") or 0
    is_sold_out = product.get("is_sold_out")
    if is_sold_out is None:
        is_sold_out = product.get("sold_out") or False
    status = product.get("edition_status") or "limited_release"
    return [
        _metafield_input(owner_id, "edition_total", "number_integer", edition_total),
        _metafield_input(owner_id, "next_edition_number", "number_integer", next_number),
        _metafield_input(owner_id, "last_assigned_edition", "number_integer", last_assigned),
        _metafield_input(owner_id, "sold_count", "number_integer", sold_count),
        _metafield_input(owner_id, "remaining_count", "number_integer", remaining),
        _metafield_input(owner_id, "is_sold_out", "boolean", _bool_value(is_sold_out)),
        _metafield_input(owner_id, "edition_status", "single_line_text_field", status),
        _metafield_input(owner_id, "edition_display_text", "single_line_text_field", display_text),
    ]


def edition_metafield_inputs(product):
    owner_id = shopify_gid("Product", product["shopify_product_id"])
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
    limit = int(product.get("edition_limit") or 100)
    next_number = int(product.get("next_available_edition") or 1)
    remaining = int(product.get("editions_remaining") or max(limit - int(product.get("editions_sold") or 0), 0))
    status = product.get("edition_status") or "Available"
    if status == "Sold Out" or remaining <= 0 or next_number > limit:
        return "SOLD OUT EDITION"
    if remaining <= 3:
        return f"FINAL EDITION #{next_number} OF {limit} AVAILABLE"
    return f"EDITION #{next_number} OF {limit} AVAILABLE"


def sync_product_edition_metafields(product, config=None, request_post=None):
    try:
        return metafields_set(
            product_edition_metafield_inputs(product),
            config=config,
            request_post=request_post,
        )
    except ShopifyAPIError as error:
        raise ShopifyAPIError(
            f"Could not sync storefront edition display. {error}"
        ) from error


def sync_edition_metafields(product, config=None, request_post=None):
    try:
        return metafields_set(
            edition_metafield_inputs(product),
            config=config,
            request_post=request_post,
        )
    except ShopifyAPIError as error:
        raise ShopifyAPIError(
            f"Could not sync storefront edition display. {error}"
        ) from error


def _certificate_display(item):
    number = int(item.get("edition_number") or 0)
    total = int(item.get("edition_total") or 100)
    if not number:
        return ""
    return f"#{number:03d}/{total}"


def order_allocation_metafield_input(order_gid, allocations, compare_digest=None):
    owner_id = shopify_gid("Order", order_gid)
    payload = allocations if isinstance(allocations, dict) else {"line_items": allocations or {}}
    return _metafield_input(
        owner_id,
        "edition_allocations",
        "json",
        json.dumps(payload, ensure_ascii=True, separators=(",", ":")),
        compare_digest=compare_digest,
    )


def sync_order_allocation_metafield(order_gid, allocations, compare_digest=None, config=None, request_post=None):
    try:
        return metafields_set(
            [order_allocation_metafield_input(order_gid, allocations, compare_digest=compare_digest)],
            config=config,
            request_post=request_post,
        )
    except ShopifyAPIError as error:
        raise ShopifyAPIError(
            f"Could not sync order edition allocations. {error}"
        ) from error


def order_certificate_metafield_inputs(order_gid, certificates):
    owner_id = shopify_gid("Order", order_gid)
    items = []
    for certificate in certificates or []:
        items.append(
            {
                "product_title": certificate.get("product_title") or "",
                "shopify_handle": certificate.get("shopify_handle") or "",
                "edition_number": int(certificate.get("edition_number") or 0),
                "edition_total": int(certificate.get("edition_total") or 100),
                "edition_display": certificate.get("edition_display") or _certificate_display(certificate),
                "certificate_id": certificate.get("certificate_id") or "",
                "certificate_url": certificate.get("certificate_url") or "",
                "generated_at": certificate.get("generated_at") or "",
            }
        )
    metafields = [
        _metafield_input(owner_id, "certificates", "json", json.dumps(items, ensure_ascii=True, separators=(",", ":")))
    ]
    if len(items) == 1:
        item = items[0]
        certificate_url = str(item.get("certificate_url") or "").strip()
        if certificate_url.startswith(("http://", "https://")):
            metafields.append(_metafield_input(owner_id, "certificate_url", "url", certificate_url))
        metafields.extend(
            [
                _metafield_input(owner_id, "certificate_id", "single_line_text_field", item.get("certificate_id") or ""),
                _metafield_input(owner_id, "edition_number", "single_line_text_field", item.get("edition_display") or ""),
                _metafield_input(owner_id, "product_title", "single_line_text_field", item.get("product_title") or ""),
            ]
        )
    return metafields


def sync_order_certificate_metafields(order_gid, certificates, config=None, request_post=None):
    try:
        return metafields_set(
            order_certificate_metafield_inputs(order_gid, certificates),
            config=config,
            request_post=request_post,
        )
    except ShopifyAPIError as error:
        raise ShopifyAPIError(
            f"Could not sync order certificate metafields. {error}"
        ) from error


def build_order_admin_url(store_domain, legacy_resource_id):
    if not store_domain or not legacy_resource_id:
        return ""
    store_slug = store_domain.split(".", 1)[0]
    return f"https://admin.shopify.com/store/{store_slug}/orders/{legacy_resource_id}"


def build_orders_admin_url(store_domain):
    if not store_domain:
        return ""
    store_slug = store_domain.split(".", 1)[0]
    return f"https://admin.shopify.com/store/{store_slug}/orders"


def normalize_order(node, store_domain):
    customer = node.get("customer") or {}
    shipping_address = node.get("shippingAddress") or {}
    shipping_lines = ((node.get("shippingLines") or {}).get("nodes") or [])
    shipping_line = node.get("shippingLine") or (shipping_lines[0] if shipping_lines else {})
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
        variant = item.get("variant") or {}
        line_items.append(
            {
                "shopify_line_item_id": item.get("id") or "",
                "shopify_product_id": product.get("id") or "",
                "product_title": product.get("title") or item.get("title") or "",
                "product_handle": product.get("handle") or "",
                "variant_title": item.get("variantTitle") or variant.get("title") or "",
                "variant_id": variant.get("id") or "",
                "sku": item.get("sku") or variant.get("sku") or "",
                "quantity": int(item.get("quantity") or 1),
            }
        )
    legacy_resource_id = str(node.get("legacyResourceId") or "")
    financial_status = node.get("displayFinancialStatus") or ""
    metafields = ((node.get("metafields") or {}).get("nodes") or [])
    return {
        "shopify_order_id": node.get("id") or "",
        "legacy_resource_id": legacy_resource_id,
        "order_name": node.get("name") or "",
        "order_number": (node.get("name") or "").lstrip("#"),
        "admin_url": build_order_admin_url(store_domain, legacy_resource_id),
        "customer_id": customer.get("id") or customer_email or "",
        "created_at": node.get("createdAt") or "",
        "remote_updated_at": node.get("updatedAt") or "",
        "processed_at": node.get("processedAt") or "",
        "paid_at": node.get("processedAt") if financial_status == "PAID" else "",
        "financial_status": financial_status,
        "fulfillment_status": node.get("displayFulfillmentStatus") or "",
        "customer_name": customer_name,
        "customer_email": customer_email,
        "customer_raw": customer,
        "shipping_title": shipping_line.get("title") or shipping_line.get("code") or "",
        "shipping_method": shipping_line.get("title") or shipping_line.get("code") or "",
        "shipping_line": shipping_line,
        "total_price": str(total_price.get("amount") or ""),
        "currency": total_price.get("currencyCode") or "",
        "cancelled_at": node.get("cancelledAt") or "",
        "metafields": metafields,
        "line_items": line_items,
    }


def fetch_orders_page(
    after=None,
    days=60,
    page_size=DEFAULT_PAGE_SIZE,
    config=None,
    request_post=None,
    query=None,
    default_paid_unfulfilled_filter=True,
):
    config = config or get_config()
    first = min(max(int(page_size), 1), 100)
    if query is None and default_paid_unfulfilled_filter:
        created_after = (datetime.now(timezone.utc) - timedelta(days=max(int(days), 1))).date().isoformat()
        query = f"financial_status:paid fulfillment_status:unfulfilled updated_at:>={created_after}"
    elif query is not None:
        query = str(query).strip() or None
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


def iter_order_pages(
    days=60,
    page_size=DEFAULT_PAGE_SIZE,
    config=None,
    request_post=None,
    query=None,
    max_orders=None,
    default_paid_unfulfilled_filter=True,
):
    config = config or get_config()
    after = None
    orders_seen = 0
    order_limit = max(1, int(max_orders if max_orders is not None else config.get("max_orders", DEFAULT_MAX_ORDERS)))
    while orders_seen < order_limit:
        page = fetch_orders_page(
            after=after,
            days=days,
            page_size=min(page_size, order_limit - orders_seen),
            config=config,
            request_post=request_post,
            query=query,
            default_paid_unfulfilled_filter=default_paid_unfulfilled_filter,
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
    first = min(max(int(page_size), 1), 100)
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
