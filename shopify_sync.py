import json
import os
import threading
import time
import base64
import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

from certificate_logging import certificate_stage_log


DEFAULT_API_VERSION = "2026-04"
DEFAULT_PAGE_SIZE = 50
EDITION_OPS_CATALOG_PAGE_SIZE = 250
DEFAULT_MAX_PRODUCTS = 500
DEFAULT_MAX_ORDERS = 250
DEFAULT_EDITION_OPS_MAX_PRODUCTS = 500
TOKEN_REFRESH_BUFFER_SECONDS = 300
DEFAULT_FILE_POLL_ATTEMPTS = 12
MAX_FILE_POLL_ATTEMPTS = 30
MAX_FILE_POLL_SLEEP_SECONDS = 2.0
ORDERS_PAID_WEBHOOK_TOPICS = {"orders/paid", "orders_paid"}
PRODUCTS_CREATE_WEBHOOK_TOPICS = {"products/create", "products_create"}
PRODUCTS_UPDATE_WEBHOOK_TOPICS = {"products/update", "products_update"}
PRODUCTS_WEBHOOK_TOPICS = PRODUCTS_CREATE_WEBHOOK_TOPICS | PRODUCTS_UPDATE_WEBHOOK_TOPICS


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
        "read_files": "read_files" in scope_set,
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


def get_shopify_webhook_secret(config=None):
    config = config or get_config()
    return (
        os.getenv("SHOPIFY_WEBHOOK_SECRET", "").strip()
        or str(config.get("client_secret") or "").strip()
    )


def verify_shopify_webhook_hmac(raw_body: bytes, hmac_header: str, secret: str) -> bool:
    if not raw_body or not hmac_header or not secret:
        return False
    try:
        digest = hmac.new(str(secret).encode("utf-8"), raw_body, hashlib.sha256).digest()
        calculated = base64.b64encode(digest).decode("utf-8")
    except Exception:
        return False
    return hmac.compare_digest(calculated, str(hmac_header or "").strip())


def is_orders_paid_webhook_topic(topic):
    normalised = str(topic or "").strip().replace("/", "_").casefold()
    return normalised in ORDERS_PAID_WEBHOOK_TOPICS


def is_products_create_webhook_topic(topic):
    normalised = str(topic or "").strip().replace("/", "_").casefold()
    return normalised in PRODUCTS_WEBHOOK_TOPICS


def is_products_update_webhook_topic(topic):
    normalised = str(topic or "").strip().replace("/", "_").casefold()
    return normalised in PRODUCTS_UPDATE_WEBHOOK_TOPICS


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
      createdAt
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
          compareAtPrice
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
    }
  }
}
"""


NEWEST_PRODUCTS_DISCOVERY_QUERY = """
query SportsCaveNewestProducts($first: Int!, $query: String) {
  products(first: $first, query: $query, sortKey: CREATED_AT, reverse: true) {
    pageInfo { hasNextPage endCursor }
    nodes {
      id
      legacyResourceId
      title
      handle
      status
      createdAt
      updatedAt
      onlineStoreUrl
      media(first: 1) {
        nodes {
          ... on MediaImage {
            id
            alt
            image { url width height }
          }
        }
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
        compareAtPrice
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
                "compare_at_price": str(item.get("compareAtPrice") or ""),
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
        "created_at": node.get("createdAt") or "",
        "remote_updated_at": node.get("updatedAt") or "",
    }


LIMITED_EDITION_DEFAULTS = {
    "edition_enabled": False,
    "edition_total": 100,
    "edition_next_number": 1,
    "edition_label": "Numbered Edition",
}
EDITION_OPS_METAFIELDS_PER_PRODUCT = 7
EDITION_OPS_SAVE_METAFIELD_KEYS = (
    "edition_enabled",
    "edition_total",
    "edition_next_number",
    "edition_remaining",
)
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
    {
        "name": "Sports Cave Certificates",
        "namespace": "sports_cave",
        "key": "certificates",
        "type": "json",
        "ownerType": "ORDER",
    },
    {
        "name": "Sports Cave Certificates JSON",
        "namespace": "sports_cave",
        "key": "certificates_json",
        "type": "json",
        "ownerType": "ORDER",
    },
    {
        "name": "Sports Cave Certificate Status",
        "namespace": "sports_cave",
        "key": "certificate_status",
        "type": "single_line_text_field",
        "ownerType": "ORDER",
    },
    {
        "name": "Sports Cave Certificate Count",
        "namespace": "sports_cave",
        "key": "certificate_count",
        "type": "number_integer",
        "ownerType": "ORDER",
    },
]

ORDER_CERTIFICATE_METAFIELD_KEYS = {
    "certificates",
    "certificates_json",
    "certificate_status",
    "certificate_count",
}


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
    sold_value = (by_key.get("edition_sold_count") or {}).get("value")
    remaining_value = (by_key.get("edition_remaining") or {}).get("value")
    sold_count = (
        _parse_int_metafield(sold_value, calculate_limited_edition_sold_count(edition_next_number))
        if sold_value not in (None, "")
        else calculate_limited_edition_sold_count(edition_next_number)
    )
    sold_count = min(max(sold_count, 0), edition_total)
    remaining = (
        _parse_int_metafield(remaining_value, max(edition_total - sold_count, 0))
        if remaining_value not in (None, "")
        else max(edition_total - sold_count, 0)
    )
    remaining = min(max(remaining, 0), edition_total)
    status_value = str((by_key.get("edition_status") or {}).get("value") or "").strip()
    status = status_value or calculate_limited_edition_status(remaining)
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


def update_product_variant_prices(product_id, variant_updates, config=None, request_post=None):
    product_gid = shopify_gid("Product", product_id)
    if not product_gid:
        raise ShopifyAPIError("Shopify product ID is missing.")
    variants = []
    for update in variant_updates or []:
        variant_id = str(update.get("variant_id") or update.get("id") or "").strip()
        price = str(update.get("new_price") or update.get("price") or "").strip()
        compare_at_price = str(
            update.get("new_compare_at_price")
            or update.get("compare_at_price")
            or update.get("compareAtPrice")
            or ""
        ).strip()
        if not variant_id:
            raise ShopifyAPIError("Shopify variant ID is missing.")
        variants.append(
            {
                "id": variant_id,
                "price": price,
                "compareAtPrice": compare_at_price,
            }
        )
    if not variants:
        return {"updated": 0, "variants": []}
    data, served_version = graphql_request(
        PRODUCT_VARIANTS_BULK_UPDATE_PRICES_MUTATION,
        variables={"productId": product_gid, "variants": variants},
        config=config,
        request_post=request_post,
    )
    result = data.get("productVariantsBulkUpdate") or {}
    errors = result.get("userErrors") or []
    if errors:
        raise ShopifyAPIError(_metafields_user_error_text(errors))
    return {
        "updated": len(result.get("productVariants") or variants),
        "variants": result.get("productVariants") or [],
        "api_version": served_version or (config or {}).get("api_version"),
    }


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


PRODUCT_VARIANTS_BULK_UPDATE_PRICES_MUTATION = """
mutation SportsCaveUpdateVariantPrices($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
  productVariantsBulkUpdate(productId: $productId, variants: $variants) {
    productVariants {
      id
      price
      compareAtPrice
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


ORDERS_PAID_WEBHOOK_SUBSCRIPTIONS_QUERY = """
query SportsCaveOrdersPaidWebhookSubscriptions($first: Int!, $topics: [WebhookSubscriptionTopic!]) {
  webhookSubscriptions(first: $first, topics: $topics) {
    nodes {
      id
      topic
      format
      createdAt
      updatedAt
      endpoint {
        __typename
        ... on WebhookHttpEndpoint {
          callbackUrl
        }
      }
    }
  }
}
"""


WEBHOOK_SUBSCRIPTION_CREATE_MUTATION = """
mutation SportsCaveCreateWebhookSubscription($topic: WebhookSubscriptionTopic!, $webhookSubscription: WebhookSubscriptionInput!) {
  webhookSubscriptionCreate(topic: $topic, webhookSubscription: $webhookSubscription) {
    webhookSubscription {
      id
      topic
      endpoint {
        __typename
        ... on WebhookHttpEndpoint {
          callbackUrl
        }
      }
    }
    userErrors {
      field
      message
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


STAGED_UPLOADS_CREATE_MUTATION = """
mutation SportsCaveStagedUploadsCreate($input: [StagedUploadInput!]!) {
  stagedUploadsCreate(input: $input) {
    stagedTargets {
      url
      resourceUrl
      parameters {
        name
        value
      }
    }
    userErrors {
      field
      message
    }
  }
}
"""


FILE_CREATE_MUTATION = """
mutation SportsCaveFileCreate($files: [FileCreateInput!]!) {
  fileCreate(files: $files) {
    files {
      id
      alt
      fileStatus
      createdAt
      ... on GenericFile {
        url
      }
      ... on MediaImage {
        image {
          url
          width
          height
        }
      }
    }
    userErrors {
      field
      message
    }
  }
}
"""


FILE_BY_ID_QUERY = """
query SportsCaveFileById($id: ID!) {
  node(id: $id) {
    ... on GenericFile {
      id
      alt
      fileStatus
      createdAt
      url
    }
    ... on MediaImage {
      id
      alt
      fileStatus
      createdAt
      image {
        url
        width
        height
      }
    }
  }
}
"""


ORDERS_QUERY = """
query SportsCaveOrders($first: Int!, $after: String, $query: String, $sortKey: OrderSortKeys!, $reverse: Boolean!) {
  orders(first: $first, after: $after, query: $query, sortKey: $sortKey, reverse: $reverse) {
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
      note
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
        address1
        address2
        city
        province
        provinceCode
        zip
        country
        countryCodeV2
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
        address1
        address2
        city
        province
        provinceCode
        zip
        country
        countryCodeV2
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
      customAttributes {
        key
        value
      }
      lineItems(first: 100) {
        nodes {
          id
          title
          quantity
          variantTitle
          sku
          customAttributes {
            key
            value
          }
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
query SportsCaveOrdersSafe($first: Int!, $after: String, $query: String, $sortKey: OrderSortKeys!, $reverse: Boolean!) {
  orders(first: $first, after: $after, query: $query, sortKey: $sortKey, reverse: $reverse) {
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
      note
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
        address1
        address2
        city
        province
        provinceCode
        zip
        country
        countryCodeV2
      }
      billingAddress {
        name
        firstName
        lastName
        address1
        address2
        city
        province
        provinceCode
        zip
        country
        countryCodeV2
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
      customAttributes {
        key
        value
      }
      lineItems(first: 100) {
        nodes {
          id
          title
          quantity
          variantTitle
          sku
          customAttributes {
            key
            value
          }
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

ORDERS_LIGHT_QUERY = """
query SportsCaveOrdersLight($first: Int!, $after: String, $query: String, $sortKey: OrderSortKeys!, $reverse: Boolean!) {
  orders(first: $first, after: $after, query: $query, sortKey: $sortKey, reverse: $reverse) {
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
      displayFinancialStatus
      displayFulfillmentStatus
      email
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
        address1
        address2
        city
        province
        provinceCode
        zip
        country
        countryCodeV2
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
      customAttributes {
        key
        value
      }
      lineItems(first: 100) {
        nodes {
          id
          title
          quantity
          variantTitle
          sku
          customAttributes {
            key
            value
          }
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

ORDERS_BY_IDS_QUERY = """
query SportsCaveOrdersByIds($ids: [ID!]!) {
  nodes(ids: $ids) {
    ... on Order {
      id
      legacyResourceId
      name
      createdAt
      updatedAt
      processedAt
      cancelledAt
      note
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
        address1
        address2
        city
        province
        provinceCode
        zip
        country
        countryCodeV2
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
        address1
        address2
        city
        province
        provinceCode
        zip
        country
        countryCodeV2
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
      customAttributes {
        key
        value
      }
      lineItems(first: 100) {
        nodes {
          id
          title
          quantity
          variantTitle
          sku
          customAttributes {
            key
            value
          }
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


def _certificate_upload_log(event, **details):
    safe_details = " ".join(f"{key}={value}" for key, value in details.items() if value not in (None, ""))
    suffix = f" {safe_details}" if safe_details else ""
    print(f"CERTIFICATE ACTION: Shopify {event}{suffix}", flush=True)


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


def create_staged_upload(filename, mime_type="application/pdf", config=None, request_post=None):
    config = config or get_config()
    data, served_version = graphql_request(
        STAGED_UPLOADS_CREATE_MUTATION,
        variables={
            "input": [
                {
                    "resource": "FILE",
                    "filename": filename,
                    "mimeType": mime_type,
                    "httpMethod": "POST",
                }
            ]
        },
        config=config,
        request_post=request_post,
    )
    result = data.get("stagedUploadsCreate") or {}
    if result.get("userErrors"):
        raise ShopifyAPIError(_metafields_user_error_text(result.get("userErrors")))
    targets = result.get("stagedTargets") or []
    if not targets:
        raise ShopifyAPIError("Shopify did not return a staged upload target.")
    return {"target": targets[0], "api_version": served_version or config.get("api_version")}


def upload_to_staged_target(target, file_path, mime_type="application/pdf", upload_post=None):
    upload_post = upload_post or requests.post
    file_path = Path(file_path)
    if not file_path.exists():
        raise ShopifyAPIError(f"Upload file is missing: {file_path}")
    parameters = {item.get("name"): item.get("value") for item in target.get("parameters") or [] if item.get("name")}
    with file_path.open("rb") as file_handle:
        response = upload_post(
            target.get("url"),
            data=parameters,
            files={"file": (file_path.name, file_handle, mime_type)},
            timeout=30,
        )
    if getattr(response, "status_code", 200) >= 400:
        raise ShopifyAPIError(f"Shopify staged upload failed with HTTP {response.status_code}.")
    if hasattr(response, "raise_for_status"):
        response.raise_for_status()
    return {"resource_url": target.get("resourceUrl") or "", "filename": file_path.name}


def create_shopify_file(original_source, filename, alt="", content_type="FILE", config=None, request_post=None):
    config = config or get_config()
    data, served_version = graphql_request(
        FILE_CREATE_MUTATION,
        variables={
            "files": [
                {
                    "originalSource": original_source,
                    "contentType": content_type,
                    "filename": filename,
                    "alt": alt or filename,
                }
            ]
        },
        config=config,
        request_post=request_post,
    )
    result = data.get("fileCreate") or {}
    if result.get("userErrors"):
        raise ShopifyAPIError(_metafields_user_error_text(result.get("userErrors")))
    files = result.get("files") or []
    if not files:
        raise ShopifyAPIError("Shopify did not create a file record.")
    return {"file": files[0], "api_version": served_version or config.get("api_version")}


def _shopify_file_url(file_node):
    image = file_node.get("image") or {}
    return file_node.get("url") or image.get("url") or ""


def fetch_shopify_file(file_id, config=None, request_post=None):
    if not file_id:
        raise ShopifyAPIError("Shopify file ID is missing.")
    config = config or get_config()
    data, served_version = graphql_request(
        FILE_BY_ID_QUERY,
        variables={"id": file_id},
        config=config,
        request_post=request_post,
    )
    node = data.get("node") or {}
    return {"file": node, "api_version": served_version or config.get("api_version")}


def upload_file_to_shopify_files(
    file_path,
    *,
    filename="",
    alt="",
    mime_type="application/pdf",
    content_type="FILE",
    config=None,
    request_post=None,
    upload_post=None,
    poll_attempts=DEFAULT_FILE_POLL_ATTEMPTS,
    poll_sleep_seconds=0.5,
):
    file_path = Path(file_path)
    filename = filename or file_path.name
    poll_limit = min(max(int(poll_attempts or 0), 0), MAX_FILE_POLL_ATTEMPTS)
    poll_sleep = min(max(float(poll_sleep_seconds or 0), 0), MAX_FILE_POLL_SLEEP_SECONDS)
    try:
        _certificate_upload_log("staged upload create started", filename=filename, mime_type=mime_type)
        stage_started = time.perf_counter()
        certificate_stage_log("Shopify_stagedUploadsCreate", "started")
        try:
            staged = create_staged_upload(filename, mime_type, config=config, request_post=request_post)
        except Exception as error:
            _certificate_upload_log("staged upload create failed", filename=filename, error=error)
            certificate_stage_log("Shopify_stagedUploadsCreate", "failed", started_at=stage_started, error=error)
            raise
        _certificate_upload_log("staged upload create completed", filename=filename)
        certificate_stage_log("Shopify_stagedUploadsCreate", "completed", started_at=stage_started)
        _certificate_upload_log("staged upload started", filename=filename)
        stage_started = time.perf_counter()
        certificate_stage_log("HTTP_staged_upload", "started")
        try:
            upload_to_staged_target(staged["target"], file_path, mime_type, upload_post=upload_post)
        except Exception as error:
            _certificate_upload_log("staged upload failed", filename=filename, error=error)
            certificate_stage_log("HTTP_staged_upload", "failed", started_at=stage_started, error=error)
            raise
        _certificate_upload_log("staged upload completed", filename=filename)
        certificate_stage_log("HTTP_staged_upload", "completed", started_at=stage_started)
        _certificate_upload_log("fileCreate started", filename=filename, content_type=content_type)
        stage_started = time.perf_counter()
        certificate_stage_log("Shopify_fileCreate", "started")
        try:
            created = create_shopify_file(
                staged["target"].get("resourceUrl") or "",
                filename,
                alt=alt or filename,
                content_type=content_type,
                config=config,
                request_post=request_post,
            )
        except Exception as error:
            _certificate_upload_log("fileCreate failed", filename=filename, error=error)
            certificate_stage_log("Shopify_fileCreate", "failed", started_at=stage_started, error=error)
            raise
        _certificate_upload_log("fileCreate completed", filename=filename)
        certificate_stage_log("Shopify_fileCreate", "completed", started_at=stage_started)
    except Exception as error:
        _certificate_upload_log("upload failed", filename=filename, error=error)
        raise
    file_node = created.get("file") or {}
    file_id = file_node.get("id") or ""
    if not file_id:
        _certificate_upload_log("file polling failed", filename=filename, error="missing_file_id")
        certificate_stage_log("Shopify_file_polling", "failed", error="missing_file_id")
        raise ShopifyAPIError("Shopify fileCreate did not return a file ID.")
    _certificate_upload_log("file polling started", filename=filename, attempts=poll_limit)
    poll_started = time.perf_counter()
    certificate_stage_log("Shopify_file_polling", "started", attempts=poll_limit)
    if _shopify_file_url(file_node) and str(file_node.get("fileStatus") or "").upper() in {"READY", "UPLOADED"}:
        _certificate_upload_log(
            "file polling completed",
            filename=filename,
            attempt=0,
            status=file_node.get("fileStatus") or "",
        )
        certificate_stage_log(
            "Shopify_file_READY",
            "completed",
            started_at=poll_started,
            shopify_file_status=file_node.get("fileStatus") or "",
            attempt=0,
        )
    else:
        for attempt in range(1, poll_limit + 1):
            time.sleep(poll_sleep)
            file_node = fetch_shopify_file(file_id, config=config, request_post=request_post).get("file") or file_node
            if _shopify_file_url(file_node) and str(file_node.get("fileStatus") or "").upper() in {"READY", "UPLOADED"}:
                _certificate_upload_log(
                    "file polling completed",
                    filename=filename,
                    attempt=attempt,
                    status=file_node.get("fileStatus") or "",
                )
                certificate_stage_log(
                    "Shopify_file_READY",
                    "completed",
                    started_at=poll_started,
                    shopify_file_status=file_node.get("fileStatus") or "",
                    attempt=attempt,
                )
                break
        else:
            _certificate_upload_log(
                "file polling failed",
                filename=filename,
                status=file_node.get("fileStatus") or "",
                attempts=poll_limit,
            )
            certificate_stage_log(
                "Shopify_file_polling_timeout",
                "failed",
                started_at=poll_started,
                shopify_file_status=file_node.get("fileStatus") or "",
                attempts=poll_limit,
            )
            raise ShopifyAPIError(
                "Shopify file upload timed out waiting for a ready file URL. "
                f"Last status: {file_node.get('fileStatus') or 'unknown'}."
            )
    if not _shopify_file_url(file_node):
        _certificate_upload_log(
            "file polling failed",
            filename=filename,
            status=file_node.get("fileStatus") or "",
            error="missing_ready_url",
        )
        certificate_stage_log(
            "Shopify_file_polling",
            "failed",
            started_at=poll_started,
            error="missing_ready_url",
            shopify_file_status=file_node.get("fileStatus") or "",
        )
        raise ShopifyAPIError(
            "Shopify file upload finished without a permanent file URL. "
            f"Last status: {file_node.get('fileStatus') or 'unknown'}."
        )
    return {
        "file_id": file_id,
        "url": _shopify_file_url(file_node),
        "status": file_node.get("fileStatus") or "",
        "filename": filename,
        "resource_url": staged["target"].get("resourceUrl") or "",
    }


def upload_pdf_to_shopify_files(
    pdf_path,
    *,
    filename="",
    alt="",
    config=None,
    request_post=None,
    upload_post=None,
    poll_attempts=DEFAULT_FILE_POLL_ATTEMPTS,
    poll_sleep_seconds=0.5,
):
    return upload_file_to_shopify_files(
        pdf_path,
        filename=filename,
        alt=alt,
        mime_type="application/pdf",
        content_type="FILE",
        config=config,
        request_post=request_post,
        upload_post=upload_post,
        poll_attempts=poll_attempts,
        poll_sleep_seconds=poll_sleep_seconds,
    )


def upload_image_to_shopify_files(
    image_path,
    *,
    filename="",
    alt="",
    mime_type="image/jpeg",
    config=None,
    request_post=None,
    upload_post=None,
    poll_attempts=DEFAULT_FILE_POLL_ATTEMPTS,
    poll_sleep_seconds=0.5,
):
    image_path = Path(image_path)
    suffix = image_path.suffix.lower()
    if suffix == ".webp":
        mime_type = "image/webp"
    elif suffix in {".jpg", ".jpeg"}:
        mime_type = "image/jpeg"
    elif suffix == ".png":
        mime_type = "image/png"
    return upload_file_to_shopify_files(
        image_path,
        filename=filename or image_path.name,
        alt=alt,
        mime_type=mime_type,
        content_type="IMAGE",
        config=config,
        request_post=request_post,
        upload_post=upload_post,
        poll_attempts=poll_attempts,
        poll_sleep_seconds=poll_sleep_seconds,
    )


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


def fetch_edition_ops_active_products_page(
    after=None,
    page_size=EDITION_OPS_CATALOG_PAGE_SIZE,
    config=None,
    request_post=None,
):
    config = config or get_config()
    first = min(max(int(page_size), 1), EDITION_OPS_CATALOG_PAGE_SIZE)
    data, served_version = graphql_request(
        EDITION_OPS_ACTIVE_PRODUCTS_QUERY,
        variables={
            "first": first,
            "after": after or None,
            "query": "(status:active OR status:draft)",
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


def fetch_edition_ops_active_products(
    max_products=None,
    page_size=EDITION_OPS_CATALOG_PAGE_SIZE,
    config=None,
    request_post=None,
    progress_callback=None,
):
    config = config or get_config()
    limit = max(1, int(max_products)) if max_products is not None else None
    requested_page_size = min(
        max(int(page_size or EDITION_OPS_CATALOG_PAGE_SIZE), 1),
        EDITION_OPS_CATALOG_PAGE_SIZE,
    )
    after = None
    products = []
    served_version = config.get("api_version")
    page_count = 0
    seen_cursors = set()
    complete = False
    while limit is None or len(products) < limit:
        remaining = limit - len(products) if limit is not None else requested_page_size
        page = fetch_edition_ops_active_products_page(
            after=after,
            page_size=min(requested_page_size, remaining),
            config=config,
            request_post=request_post,
        )
        page_count += 1
        page_products = page.get("products") or []
        products.extend(page_products)
        served_version = page.get("api_version") or served_version
        if progress_callback:
            progress_callback(len(products))
        if not page.get("has_next_page"):
            complete = True
            break
        next_cursor = str(page.get("end_cursor") or "").strip()
        if not next_cursor:
            raise ShopifyAPIError("Shopify catalogue pagination stopped before the final page.")
        if next_cursor in seen_cursors:
            raise ShopifyAPIError("Shopify catalogue pagination returned a repeated cursor.")
        seen_cursors.add(next_cursor)
        after = next_cursor
    selected_products = products if limit is None else products[:limit]
    return {
        "products": selected_products,
        "api_version": served_version,
        "max_products": limit,
        "page_count": page_count,
        "complete": complete,
    }


def fetch_newest_products_for_edition_ops(
    *,
    created_after="",
    page_size=50,
    config=None,
    request_post=None,
):
    """Fetch one lightweight, newest-first product page for Edition Ops discovery."""
    config = config or get_config()
    first = min(max(int(page_size or 50), 1), 50)
    search_parts = ["(status:active OR status:draft)"]
    watermark = str(created_after or "").strip().replace("'", "")
    if watermark:
        # Include the watermark second. Immutable product IDs resolve timestamp ties.
        search_parts.append(f"created_at:>='{watermark}'")
    search = " ".join(search_parts)
    data, served_version = graphql_request(
        NEWEST_PRODUCTS_DISCOVERY_QUERY,
        variables={"first": first, "query": search},
        config=config,
        request_post=request_post,
    )
    connection = data.get("products") or {}
    products = [
        normalize_product(node, config["store_domain"])
        for node in (connection.get("nodes") or [])
    ]
    page_info = connection.get("pageInfo") or {}
    return {
        "products": products,
        "has_next_page": bool(page_info.get("hasNextPage")),
        "end_cursor": page_info.get("endCursor"),
        "api_version": served_version or config.get("api_version"),
        "query": search,
        "page_size": first,
    }


def limited_edition_metafield_inputs(product_id, values):
    owner_id = shopify_gid("Product", product_id)
    if not owner_id:
        raise ShopifyAPIError("Shopify product ID is missing.")
    compare_digests = (
        values.get("metafield_compare_digests")
        or values.get("compare_digests")
        or {}
    )

    def edition_input(key, metafield_type, value):
        return _metafield_input(
            owner_id,
            key,
            metafield_type,
            value,
            compare_digest=compare_digests.get(key),
        )

    edition_total = max(
        _parse_int_metafield(values.get("edition_total"), LIMITED_EDITION_DEFAULTS["edition_total"]),
        1,
    )
    edition_next_number = max(
        _parse_int_metafield(values.get("edition_next_number"), LIMITED_EDITION_DEFAULTS["edition_next_number"]),
        1,
    )
    derived_sold_count = calculate_limited_edition_sold_count(edition_next_number)
    edition_sold_count = (
        _parse_int_metafield(values.get("edition_sold_count"), derived_sold_count)
        if "edition_sold_count" in values
        else derived_sold_count
    )
    edition_sold_count = min(max(edition_sold_count, 0), edition_total)
    derived_remaining = max(edition_total - edition_sold_count, 0)
    edition_remaining = (
        _parse_int_metafield(values.get("edition_remaining"), derived_remaining)
        if "edition_remaining" in values
        else derived_remaining
    )
    edition_remaining = min(max(edition_remaining, 0), edition_total)
    edition_status = str(
        values.get("edition_status") or calculate_limited_edition_status(edition_remaining)
    ).strip() or calculate_limited_edition_status(edition_remaining)
    return [
        edition_input(
            "edition_enabled",
            "boolean",
            _bool_value(values.get("edition_enabled")),
        ),
        edition_input("edition_total", "number_integer", edition_total),
        edition_input("edition_next_number", "number_integer", edition_next_number),
        edition_input("edition_sold_count", "number_integer", edition_sold_count),
        edition_input("edition_remaining", "number_integer", edition_remaining),
        edition_input("edition_status", "single_line_text_field", edition_status),
        edition_input(
            "edition_label",
            "single_line_text_field",
            str(values.get("edition_label") or LIMITED_EDITION_DEFAULTS["edition_label"]).strip()
            or LIMITED_EDITION_DEFAULTS["edition_label"],
        ),
    ]


def edition_ops_save_metafield_inputs(product_id, values):
    owner_id = shopify_gid("Product", product_id)
    if not owner_id:
        raise ShopifyAPIError("Shopify product ID is missing.")

    def edition_input(key, metafield_type, value):
        return _metafield_input(owner_id, key, metafield_type, value)

    edition_total = max(
        _parse_int_metafield(values.get("edition_total"), LIMITED_EDITION_DEFAULTS["edition_total"]),
        1,
    )
    edition_next_number = max(
        _parse_int_metafield(values.get("edition_next_number"), LIMITED_EDITION_DEFAULTS["edition_next_number"]),
        1,
    )
    derived_remaining = calculate_limited_edition_remaining(edition_total, edition_next_number)
    edition_remaining = (
        _parse_int_metafield(values.get("edition_remaining"), derived_remaining)
        if "edition_remaining" in values
        else derived_remaining
    )
    edition_remaining = max(edition_remaining, 0)
    return [
        edition_input("edition_enabled", "boolean", _bool_value(values.get("edition_enabled"))),
        edition_input("edition_total", "number_integer", edition_total),
        edition_input("edition_next_number", "number_integer", edition_next_number),
        edition_input("edition_remaining", "number_integer", edition_remaining),
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


def sync_edition_ops_save_metafields_for_products(
    products,
    config=None,
    request_post=None,
    *,
    raise_on_failure=False,
):
    config = config or get_config()
    rows = [row for row in (products or []) if row.get("shopify_product_id")]
    results = []
    synced = 0
    failed = 0

    fields_per_product = max(len(EDITION_OPS_SAVE_METAFIELD_KEYS), 1)
    products_per_batch = max(1, SHOPIFY_METAFIELDS_SET_LIMIT // fields_per_product)
    for index in range(0, len(rows), products_per_batch):
        chunk = rows[index : index + products_per_batch]
        inputs = []
        for row in chunk:
            inputs.extend(edition_ops_save_metafield_inputs(row["shopify_product_id"], row))

        try:
            metafields_set(inputs, config=config, request_post=request_post)
            for row in chunk:
                results.append(
                    {
                        "shopify_product_id": shopify_gid("Product", row["shopify_product_id"]),
                        "handle": row.get("handle") or "",
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
                        edition_ops_save_metafield_inputs(row["shopify_product_id"], row),
                        config=config,
                        request_post=request_post,
                    )
                    results.append(
                        {
                            "shopify_product_id": shopify_gid("Product", row["shopify_product_id"]),
                            "handle": row.get("handle") or "",
                            "title": row.get("title") or row.get("handle") or row["shopify_product_id"],
                            "ok": True,
                            "message": "Synced",
                        }
                    )
                    synced += 1
                except Exception as product_error:
                    results.append(
                        {
                            "shopify_product_id": shopify_gid("Product", row["shopify_product_id"]),
                            "handle": row.get("handle") or "",
                            "title": row.get("title") or row.get("handle") or row["shopify_product_id"],
                            "ok": False,
                            "message": str(product_error) or str(batch_error),
                        }
                    )
                    failed += 1

    result = {"synced": synced, "failed": failed, "results": results}
    if failed and raise_on_failure:
        raise ShopifyAPIError(f"Shopify metafield sync failed: {_limited_edition_sync_error_text(results)}")
    return result


def _limited_edition_sync_error_text(results):
    messages = []
    for item in results or []:
        if item.get("ok"):
            continue
        title = item.get("title") or item.get("shopify_product_id") or "Product"
        message = item.get("message") or "Unknown Shopify metafield sync error"
        messages.append(f"{title}: {message}")
    return "; ".join(messages) or "Unknown Shopify metafield sync error"


def sync_limited_edition_metafields_for_products(
    products,
    config=None,
    request_post=None,
    *,
    raise_on_failure=False,
):
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

    result = {"synced": synced, "failed": failed, "results": results}
    if failed and raise_on_failure:
        raise ShopifyAPIError(f"Shopify metafield sync failed: {_limited_edition_sync_error_text(results)}")
    return result


def public_app_base_url():
    for key in (
        "SPORTS_CAVE_OS_BASE_URL",
        "SPORTS_CAVE_APP_URL",
        "PUBLIC_APP_URL",
        "APP_BASE_URL",
        "RENDER_EXTERNAL_URL",
        "RENDER_EXTERNAL_HOSTNAME",
    ):
        value = str(os.getenv(key, "") or "").strip()
        if not value:
            continue
        if key == "RENDER_EXTERNAL_HOSTNAME" and "://" not in value:
            value = f"https://{value}"
        if "://" not in value:
            value = f"https://{value}"
            return value.rstrip("/")
    return ""


def public_webhook_base_url():
    for key in (
        "SPORTS_CAVE_WEBHOOK_BASE_URL",
        "SPORTS_CAVE_OS_BASE_URL",
        "PUBLIC_APP_URL",
        "RENDER_EXTERNAL_URL",
        "RENDER_EXTERNAL_HOSTNAME",
    ):
        value = str(os.getenv(key, "") or "").strip()
        if not value:
            continue
        if key == "RENDER_EXTERNAL_HOSTNAME" and "://" not in value:
            value = f"https://{value}"
        if "://" not in value:
            value = f"https://{value}"
        return value.rstrip("/")
    return ""


def orders_paid_webhook_callback_url(base_url=None):
    base = str(base_url or public_webhook_base_url() or "").strip().rstrip("/")
    if not base:
        return ""
    if "://" not in base:
        base = f"https://{base}"
    if base.rstrip("/").endswith("/webhooks/shopify/orders-paid"):
        return base.rstrip("/")
    return f"{base}/webhooks/shopify/orders-paid"


def products_create_webhook_callback_url(base_url=None):
    base = str(base_url or public_webhook_base_url() or "").strip().rstrip("/")
    if not base:
        return ""
    if "://" not in base:
        base = f"https://{base}"
    if base.rstrip("/").endswith("/webhooks/shopify/products-create"):
        return base.rstrip("/")
    return f"{base}/webhooks/shopify/products-create"


def products_update_webhook_callback_url(base_url=None):
    base = str(base_url or public_webhook_base_url() or "").strip().rstrip("/")
    if not base:
        return ""
    if "://" not in base:
        base = f"https://{base}"
    if base.rstrip("/").endswith("/webhooks/shopify/products-update"):
        return base.rstrip("/")
    return f"{base}/webhooks/shopify/products-update"


def _webhook_callback_url(subscription):
    endpoint = (subscription or {}).get("endpoint") or {}
    return str(endpoint.get("callbackUrl") or "").strip()


def list_orders_paid_webhook_subscriptions(config=None, request_post=None):
    config = config or get_config()
    data, served_version = graphql_request(
        ORDERS_PAID_WEBHOOK_SUBSCRIPTIONS_QUERY,
        variables={"first": 50, "topics": ["ORDERS_PAID"]},
        config=config,
        request_post=request_post,
    )
    nodes = ((data.get("webhookSubscriptions") or {}).get("nodes") or [])
    return {
        "subscriptions": nodes,
        "api_version": served_version or config.get("api_version"),
    }


def list_products_create_webhook_subscriptions(config=None, request_post=None):
    config = config or get_config()
    data, served_version = graphql_request(
        ORDERS_PAID_WEBHOOK_SUBSCRIPTIONS_QUERY,
        variables={"first": 50, "topics": ["PRODUCTS_CREATE"]},
        config=config,
        request_post=request_post,
    )
    nodes = ((data.get("webhookSubscriptions") or {}).get("nodes") or [])
    return {
        "subscriptions": nodes,
        "api_version": served_version or config.get("api_version"),
    }


def list_products_update_webhook_subscriptions(config=None, request_post=None):
    config = config or get_config()
    data, served_version = graphql_request(
        ORDERS_PAID_WEBHOOK_SUBSCRIPTIONS_QUERY,
        variables={"first": 50, "topics": ["PRODUCTS_UPDATE"]},
        config=config,
        request_post=request_post,
    )
    nodes = ((data.get("webhookSubscriptions") or {}).get("nodes") or [])
    return {
        "subscriptions": nodes,
        "api_version": served_version or config.get("api_version"),
    }


def ensure_orders_paid_webhook_subscription(callback_url=None, config=None, request_post=None):
    config = config or get_config()
    target_url = orders_paid_webhook_callback_url(callback_url)
    if not target_url:
        raise ShopifyConfigurationError(
            "Webhook URL is missing. Set SPORTS_CAVE_WEBHOOK_BASE_URL, SPORTS_CAVE_OS_BASE_URL, "
            "PUBLIC_APP_URL, or RENDER_EXTERNAL_URL before registering the Shopify orders/paid webhook."
        )
    existing = list_orders_paid_webhook_subscriptions(config=config, request_post=request_post)
    for subscription in existing.get("subscriptions") or []:
        if _webhook_callback_url(subscription).rstrip("/") == target_url.rstrip("/"):
            return {
                "created": False,
                "subscription": subscription,
                "callback_url": target_url,
                "api_version": existing.get("api_version"),
            }

    data, served_version = graphql_request(
        WEBHOOK_SUBSCRIPTION_CREATE_MUTATION,
        variables={
            "topic": "ORDERS_PAID",
            "webhookSubscription": {
                "callbackUrl": target_url,
                "format": "JSON",
            },
        },
        config=config,
        request_post=request_post,
    )
    result = data.get("webhookSubscriptionCreate") or {}
    if result.get("userErrors"):
        raise ShopifyAPIError(_metafields_user_error_text(result.get("userErrors")))
    subscription = result.get("webhookSubscription") or {}
    if not subscription.get("id"):
        raise ShopifyAPIError("Shopify did not return the created orders/paid webhook subscription.")
    return {
        "created": True,
        "subscription": subscription,
        "callback_url": target_url,
        "api_version": served_version or config.get("api_version"),
    }


def ensure_products_create_webhook_subscription(callback_url=None, config=None, request_post=None):
    config = config or get_config()
    target_url = products_create_webhook_callback_url(callback_url)
    if not target_url:
        raise ShopifyConfigurationError(
            "Webhook URL is missing. Set SPORTS_CAVE_WEBHOOK_BASE_URL, SPORTS_CAVE_OS_BASE_URL, "
            "PUBLIC_APP_URL, or RENDER_EXTERNAL_URL before registering the Shopify products/create webhook."
        )
    existing = list_products_create_webhook_subscriptions(config=config, request_post=request_post)
    for subscription in existing.get("subscriptions") or []:
        if _webhook_callback_url(subscription).rstrip("/") == target_url.rstrip("/"):
            return {
                "created": False,
                "subscription": subscription,
                "callback_url": target_url,
                "api_version": existing.get("api_version"),
            }

    data, served_version = graphql_request(
        WEBHOOK_SUBSCRIPTION_CREATE_MUTATION,
        variables={
            "topic": "PRODUCTS_CREATE",
            "webhookSubscription": {
                "callbackUrl": target_url,
                "format": "JSON",
            },
        },
        config=config,
        request_post=request_post,
    )
    result = data.get("webhookSubscriptionCreate") or {}
    if result.get("userErrors"):
        raise ShopifyAPIError(_metafields_user_error_text(result.get("userErrors")))
    subscription = result.get("webhookSubscription") or {}
    if not subscription.get("id"):
        raise ShopifyAPIError("Shopify did not return the created products/create webhook subscription.")
    return {
        "created": True,
        "subscription": subscription,
        "callback_url": target_url,
        "api_version": served_version or config.get("api_version"),
    }


def ensure_products_update_webhook_subscription(callback_url=None, config=None, request_post=None):
    config = config or get_config()
    target_url = products_update_webhook_callback_url(callback_url)
    if not target_url:
        raise ShopifyConfigurationError(
            "Webhook URL is missing. Set SPORTS_CAVE_WEBHOOK_BASE_URL, SPORTS_CAVE_OS_BASE_URL, "
            "PUBLIC_APP_URL, or RENDER_EXTERNAL_URL before registering the Shopify products/update webhook."
        )
    existing = list_products_update_webhook_subscriptions(config=config, request_post=request_post)
    for subscription in existing.get("subscriptions") or []:
        if _webhook_callback_url(subscription).rstrip("/") == target_url.rstrip("/"):
            return {
                "created": False,
                "subscription": subscription,
                "callback_url": target_url,
                "api_version": existing.get("api_version"),
            }

    data, served_version = graphql_request(
        WEBHOOK_SUBSCRIPTION_CREATE_MUTATION,
        variables={
            "topic": "PRODUCTS_UPDATE",
            "webhookSubscription": {
                "callbackUrl": target_url,
                "format": "JSON",
            },
        },
        config=config,
        request_post=request_post,
    )
    result = data.get("webhookSubscriptionCreate") or {}
    if result.get("userErrors"):
        raise ShopifyAPIError(_metafields_user_error_text(result.get("userErrors")))
    subscription = result.get("webhookSubscription") or {}
    if not subscription.get("id"):
        raise ShopifyAPIError("Shopify did not return the created products/update webhook subscription.")
    return {
        "created": True,
        "subscription": subscription,
        "callback_url": target_url,
        "api_version": served_version or config.get("api_version"),
    }


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


def _positive_int(value, default=0):
    try:
        number = int(value or 0)
    except (TypeError, ValueError):
        number = int(default or 0)
    return number if number > 0 else int(default or 0)


def _clean_certificate_status(record):
    url = (
        record.get("certificate_file_url")
        or record.get("certificate_pdf_url")
        or record.get("pdf_url")
        or record.get("certificate_url")
        or record.get("shopify_file_url")
        or ""
    )
    raw_status = str(record.get("certificate_status") or record.get("status") or "").strip()
    raw_key = raw_status.casefold()
    if url and raw_key in {"ready", "uploaded", "certificate ready", "local pdf", ""}:
        return "Ready"
    if url and (
        record.get("shopify_file_id")
        or record.get("pdf_shopify_file_id")
        or record.get("shopify_pdf_file_id")
    ):
        return "Ready"
    if raw_key in {"upload error", "template missing", "error", "missing", "certificate missing"}:
        return "Missing"
    return "Processing"


def _certificate_file_status(record, certificate_status):
    raw = str(record.get("shopify_file_status") or record.get("file_status") or "").strip().upper()
    if raw:
        return raw
    if certificate_status == "Ready":
        return "READY"
    if certificate_status == "Missing":
        return "MISSING"
    return "PROCESSING"


def order_certificate_account_record(record):
    record = dict(record or {})
    certificate_status = _clean_certificate_status(record)
    url = (
        record.get("certificate_file_url")
        or record.get("certificate_pdf_url")
        or record.get("pdf_url")
        or record.get("certificate_url")
        or record.get("shopify_file_url")
        or ""
    )
    if certificate_status != "Ready":
        url = ""
    print_jpg_url = (
        record.get("certificate_print_jpg_url")
        or record.get("print_jpg_url")
        or ""
    )
    preview_image_url = (
        record.get("certificate_preview_image_url")
        or record.get("preview_image_url")
        or ""
    )
    if certificate_status != "Ready":
        print_jpg_url = ""
        preview_image_url = ""
    edition_total = _positive_int(record.get("edition_total"), 100) or 100
    edition_number = _positive_int(record.get("edition_number"), 0)
    created_at = (
        record.get("created_at")
        or record.get("generated_at")
        or record.get("purchase_date")
        or ""
    )
    shopify_order_name = str(record.get("shopify_order_name") or record.get("order_name") or "").strip()
    edition_display = _certificate_display({"edition_number": edition_number, "edition_total": edition_total})
    display_edition = f"Edition #{edition_number:03d} of {edition_total}" if edition_number else ""
    return {
        "shopify_customer_id": str(record.get("shopify_customer_id") or record.get("customer_id") or "").strip(),
        "customer_email": str(record.get("customer_email") or "").strip(),
        "customer_name": str(record.get("customer_name") or "").strip(),
        "shopify_order_id": shopify_gid("Order", record.get("shopify_order_id") or record.get("order_gid")),
        "shopify_order_name": shopify_order_name,
        "order_name": shopify_order_name,
        "shopify_line_item_id": shopify_gid("LineItem", record.get("shopify_line_item_id") or record.get("line_item_id")),
        "shopify_product_id": shopify_gid("Product", record.get("shopify_product_id") or record.get("product_gid")),
        "shopify_variant_id": shopify_gid("ProductVariant", record.get("shopify_variant_id") or record.get("variant_gid")),
        "product_title": str(record.get("product_title") or "").strip(),
        "product_handle": str(record.get("product_handle") or record.get("handle") or record.get("shopify_handle") or "").strip(),
        "variant_title": str(record.get("variant_title") or "").strip(),
        "edition_number": edition_number,
        "edition_total": edition_total,
        "edition_limit": edition_total,
        "edition_display": edition_display,
        "display_edition": display_edition or edition_display,
        "certificate_id": str(record.get("certificate_id") or "").strip(),
        "shopify_file_id": str(record.get("shopify_file_id") or record.get("pdf_shopify_file_id") or record.get("certificate_shopify_file_id") or "").strip(),
        "shopify_pdf_file_id": str(record.get("shopify_pdf_file_id") or record.get("pdf_shopify_file_id") or record.get("shopify_file_id") or "").strip(),
        "shopify_print_jpg_file_id": str(record.get("shopify_print_jpg_file_id") or "").strip(),
        "shopify_preview_file_id": str(record.get("shopify_preview_file_id") or record.get("certificate_preview_shopify_file_id") or "").strip(),
        "certificate_file_url": str(url or "").strip(),
        "certificate_pdf_url": str(url or "").strip(),
        "certificate_print_jpg_url": str(print_jpg_url or "").strip(),
        "certificate_preview_image_url": str(preview_image_url or "").strip(),
        "certificate_status": certificate_status,
        "shopify_file_status": _certificate_file_status(record, certificate_status),
        "purchase_date": str(record.get("purchase_date") or record.get("processed_at") or "").strip(),
        "created_at": str(created_at or "").strip(),
        "source": "sports_cave_os",
    }


def order_certificates_json_payload(certificates):
    records_by_key = {}
    for certificate in certificates or []:
        record = order_certificate_account_record(certificate)
        key = (
            record.get("shopify_order_id") or "",
            record.get("shopify_line_item_id") or "",
            record.get("edition_number") or 0,
            str((certificate or {}).get("line_item_unit_index") or (certificate or {}).get("allocation_index") or 1),
            record.get("certificate_id") or "",
        )
        records_by_key[key] = record
    return {
        "certificates": list(records_by_key.values()),
        "version": 1,
        "source": "sports_cave_os",
    }


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


def order_certificate_metafield_input(order_gid, certificates, compare_digest=None):
    owner_id = shopify_gid("Order", order_gid)
    items = []
    for certificate in certificates or []:
        record = dict(certificate or {})
        if record.get("edition_number"):
            record["edition_number"] = int(record.get("edition_number") or 0)
        if record.get("edition_total"):
            record["edition_total"] = int(record.get("edition_total") or 0)
        record.setdefault("edition_display", _certificate_display(record))
        items.append(record)
    return _metafield_input(
        owner_id,
        "certificates",
        "json",
        json.dumps(items, ensure_ascii=True, separators=(",", ":")),
        compare_digest=compare_digest,
    )


def order_certificates_json_metafield_input(order_gid, certificates):
    owner_id = shopify_gid("Order", order_gid)
    return _metafield_input(
        owner_id,
        "certificates_json",
        "json",
        json.dumps(order_certificates_json_payload(certificates), ensure_ascii=True, separators=(",", ":")),
    )


def order_certificate_status_value(certificates):
    records = [order_certificate_account_record(certificate) for certificate in certificates or []]
    if not records:
        return "missing"
    if all(record.get("certificate_status") == "Ready" for record in records):
        return "ready"
    if any(record.get("certificate_status") == "Missing" for record in records):
        return "missing"
    return "processing"


def order_certificate_count_value(certificates):
    return len([certificate for certificate in certificates or [] if certificate])


def order_certificate_status_metafield_input(order_gid, certificates):
    owner_id = shopify_gid("Order", order_gid)
    return _metafield_input(
        owner_id,
        "certificate_status",
        "single_line_text_field",
        order_certificate_status_value(certificates),
    )


def order_certificate_count_metafield_input(order_gid, certificates):
    owner_id = shopify_gid("Order", order_gid)
    return _metafield_input(
        owner_id,
        "certificate_count",
        "number_integer",
        order_certificate_count_value(certificates),
    )


def order_certificate_metafield_inputs(order_gid, certificates, compare_digest=None):
    return [
        order_certificate_metafield_input(order_gid, certificates, compare_digest=compare_digest),
        order_certificates_json_metafield_input(order_gid, certificates),
        order_certificate_status_metafield_input(order_gid, certificates),
        order_certificate_count_metafield_input(order_gid, certificates),
    ]


def sync_order_certificate_metafields(order_gid, certificates, compare_digest=None, config=None, request_post=None):
    inputs = order_certificate_metafield_inputs(order_gid, certificates, compare_digest=compare_digest)
    try:
        result = metafields_set(inputs, config=config, request_post=request_post)
        written_keys = {
            item.get("key")
            for item in (result.get("metafields") or [])
            if item.get("namespace") == "sports_cave"
        }
        missing_inputs = [
            item
            for item in inputs
            if item.get("key") in ORDER_CERTIFICATE_METAFIELD_KEYS and item.get("key") not in written_keys
        ]
        if missing_inputs:
            fallback_metafields = list(result.get("metafields") or [])
            for item in missing_inputs:
                fallback = metafields_set([item], config=config, request_post=request_post)
                fallback_metafields.extend(fallback.get("metafields") or [])
            result = {
                **result,
                "count": len(fallback_metafields),
                "metafields": fallback_metafields,
            }
        return result
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


def _compact_address_parts(*parts):
    values = []
    seen = set()
    for part in parts:
        cleaned = str(part or "").strip()
        if not cleaned:
            continue
        lowered = cleaned.casefold()
        if lowered in seen:
            continue
        seen.add(lowered)
        values.append(cleaned)
    return values


def _address_summary(address):
    if not isinstance(address, dict):
        return ""
    return ", ".join(
        _compact_address_parts(
            address.get("address1"),
            address.get("address2"),
            address.get("city"),
            address.get("provinceCode") or address.get("province"),
            address.get("zip"),
            address.get("countryCodeV2") or address.get("country"),
        )
    )


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
    shipping_name = (
        shipping_address.get("name")
        or shipping_full_name
        or customer_name
        or ""
    )
    shipping_address_summary = _address_summary(shipping_address)
    line_items = []
    for item in (node.get("lineItems") or {}).get("nodes") or []:
        product = item.get("product") or {}
        variant = item.get("variant") or {}
        custom_attributes = item.get("customAttributes") or []
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
                "custom_attributes": custom_attributes,
                "properties": custom_attributes,
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
        "shopify_customer_id": customer.get("id") or "",
        "created_at": node.get("createdAt") or "",
        "remote_updated_at": node.get("updatedAt") or "",
        "processed_at": node.get("processedAt") or "",
        "paid_at": node.get("processedAt") if financial_status == "PAID" else "",
        "financial_status": financial_status,
        "fulfillment_status": node.get("displayFulfillmentStatus") or "",
        "customer_name": customer_name,
        "customer_email": customer_email,
        "customer_raw": customer,
        "shipping_name": shipping_name,
        "shipping_address": shipping_address,
        "shipping_address_summary": shipping_address_summary,
        "shipping_country": shipping_address.get("countryCodeV2") or shipping_address.get("country") or "",
        "shipping_state": shipping_address.get("provinceCode") or shipping_address.get("province") or "",
        "shipping_postcode": shipping_address.get("zip") or "",
        "shipping_title": shipping_line.get("title") or shipping_line.get("code") or "",
        "shipping_method": shipping_line.get("title") or shipping_line.get("code") or "",
        "shipping_line": shipping_line,
        "billing_address": billing_address,
        "total_price": str(total_price.get("amount") or ""),
        "currency": total_price.get("currencyCode") or "",
        "cancelled_at": node.get("cancelledAt") or "",
        "note": node.get("note") or "",
        "custom_attributes": node.get("customAttributes") or [],
        "note_attributes": node.get("customAttributes") or [],
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
    sort_key="UPDATED_AT",
    reverse=True,
    lightweight=False,
):
    config = config or get_config()
    first = min(max(int(page_size), 1), 100)
    if query is None and default_paid_unfulfilled_filter:
        created_after = (datetime.now(timezone.utc) - timedelta(days=max(int(days), 1))).date().isoformat()
        query = f"financial_status:paid fulfillment_status:unfulfilled updated_at:>={created_after}"
    elif query is not None:
        query = str(query).strip() or None
    variables = {
        "first": first,
        "after": after,
        "query": query,
        "sortKey": str(sort_key or "UPDATED_AT"),
        "reverse": bool(reverse),
    }
    try:
        data, served_version = graphql_request(
            ORDERS_LIGHT_QUERY if lightweight else ORDERS_QUERY,
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
    sort_key="UPDATED_AT",
    reverse=True,
    lightweight=False,
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
            sort_key=sort_key,
            reverse=reverse,
            lightweight=lightweight,
        )
        if not page["orders"]:
            break
        orders_seen += len(page["orders"])
        yield page
        if not page["has_next_page"] or not page["end_cursor"]:
            break
        after = page["end_cursor"]


def fetch_orders_by_ids(order_ids, config=None, request_post=None):
    config = config or get_config()
    ids = [str(order_id or "").strip() for order_id in (order_ids or []) if str(order_id or "").strip()]
    if not ids:
        return []
    all_orders = []
    for offset in range(0, len(ids), 50):
        batch_ids = ids[offset : offset + 50]
        data, served_version = graphql_request(
            ORDERS_BY_IDS_QUERY,
            variables={"ids": batch_ids},
            config=config,
            request_post=request_post,
        )
        _ = served_version
        nodes = data.get("nodes") or []
        for node in nodes:
            if not isinstance(node, dict) or not node.get("id"):
                continue
            all_orders.append(normalize_order(node, config["store_domain"]))
    return all_orders


def fetch_latest_paid_orders(
    *,
    limit=50,
    lookback_days=14,
    query=None,
    sort_key="CREATED_AT",
    reverse=True,
    lightweight=False,
    config=None,
    request_post=None,
):
    config = config or get_config()
    order_limit = max(1, int(limit or DEFAULT_MAX_ORDERS))
    lookback = max(1, int(lookback_days or 14))
    queries = [str(query).strip()] if str(query or "").strip() else ["financial_status:paid"]
    orders = []
    query_used = queries[-1]
    last_error = None
    for candidate_query in queries:
        fetched = []
        pages_fetched = 0
        try:
            for page in iter_order_pages(
                query=candidate_query,
                days=lookback,
                max_orders=order_limit,
                page_size=min(DEFAULT_PAGE_SIZE, order_limit),
                config=config,
                request_post=request_post,
                default_paid_unfulfilled_filter=False,
                sort_key=sort_key,
                reverse=reverse,
                lightweight=lightweight,
            ):
                pages_fetched += 1
                fetched.extend(page.get("orders") or [])
        except ShopifyAPIError as error:
            last_error = error
            continue
        if fetched:
            orders = fetched[:order_limit]
            query_used = candidate_query
            break
    if not orders and last_error:
        raise last_error
    return {
        "orders": orders,
        "query": query_used,
        "lookback_days": lookback,
        "limit": order_limit,
        "pages_fetched": pages_fetched if orders else 0,
        "line_items_fetched": sum(len(order.get("line_items") or []) for order in orders),
        "metafields_fetched": sum(len(order.get("metafields") or []) for order in orders),
    }


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
