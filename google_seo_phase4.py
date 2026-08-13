"""Persistent canonical mapping and trusted SEO reporting joins for Phase 4."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import html
import json
from pathlib import Path
import re
import secrets
import time
from urllib.parse import quote, urlsplit
import uuid

from activity_log import record_activity_log
import google_seo
from google_seo_import import GoogleSEOReportingClient, SEOImportError, date_sequence
import os_accounts
import shopify_sync


PHASE4_MIGRATION = "20260813_google_seo_phase4_join.sql"
WORKSPACE_KEY = google_seo.GOOGLE_SEO_WORKSPACE_KEY
BASE_DIR = Path(__file__).resolve().parent
PHASE4_SOURCES = (
    "shopify_pages",
    "shopify_orders",
    "ga4_transactions",
    "mapping",
    "reconciliation",
)
EXTERNAL_PHASE4_SOURCES = {"shopify_pages", "shopify_orders", "ga4_transactions"}
ACTIVE_STATUSES = ("queued", "running")
LEASE_SECONDS = 10 * 60
GA4_PAGE_SIZE = 250_000
GA4_TRANSACTION_REQUIRED_DIMENSIONS = (
    "date",
    "transactionId",
    "landingPagePlusQueryString",
    "countryId",
    "deviceCategory",
    "sessionDefaultChannelGroup",
)
GA4_TRANSACTION_OPTIONAL_DIMENSION = "hostname"
GA4_TRANSACTION_METRICS = ("transactions", "purchaseRevenue")
INVALID_LANDING_VALUES = {
    "",
    "(not set)",
    "not set",
    "(not provided)",
    "(entrance)",
    "(other)",
}
UNRESERVED = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
)
DEFAULT_MARKET_COUNTRIES = {
    "Australia": {"AU", "AUS"},
    "United States": {"US", "USA"},
    "United Kingdom": {"GB", "GBR", "UK"},
}
DEVICE_VALUES = {
    "Desktop": {"desktop", "DESKTOP"},
    "Mobile": {"mobile", "MOBILE"},
}


class SEOPhase4Error(RuntimeError):
    def __init__(self, message, *, code="seo_phase4_error", retryable=True):
        super().__init__(str(message or "SEO Phase 4 could not be completed."))
        self.public_message = str(message or "SEO Phase 4 could not be completed.")[:300]
        self.code = str(code or "seo_phase4_error")[:100]
        self.retryable = bool(retryable)


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0)


def _as_date(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError) as error:
        raise SEOPhase4Error(
            "The saved reporting date is invalid.",
            code="invalid_reporting_date",
            retryable=False,
        ) from error


def _decimal(value):
    try:
        return Decimal(str(value or "0"))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _integer(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _iso(value):
    if not value:
        return ""
    if isinstance(value, (date, datetime)):
        return value.isoformat().replace("+00:00", "Z")
    return str(value)


def _decode_unreserved(path):
    def replace(match):
        value = chr(int(match.group(1), 16))
        return value if value in UNRESERVED else f"%{match.group(1).upper()}"

    return re.sub(r"%([0-9A-Fa-f]{2})", replace, str(path or ""))


def _clean_path(path):
    path = _decode_unreserved(path or "/")
    path = quote(path, safe="/%:@!$&'()*+,;=-._~")
    path = re.sub(r"/{2,}", "/", path)
    segments = []
    for segment in path.split("/"):
        if segment in {"", "."}:
            continue
        if segment == "..":
            if segments:
                segments.pop()
            continue
        segments.append(segment)
    clean = "/" + "/".join(segments)
    return clean if clean == "/" else clean.rstrip("/")


def _locale_details(path, known_locale_prefixes=()):
    first = next((part for part in str(path or "").split("/") if part), "")
    configured = {str(item or "").strip("/").casefold() for item in known_locale_prefixes}
    looks_like_locale = bool(re.fullmatch(r"[a-z]{2}(?:-[a-z]{2})?", first.casefold()))
    if not first or (first.casefold() not in configured and not looks_like_locale):
        return "", ""
    pieces = first.casefold().split("-")
    country = pieces[-1].upper() if len(pieces) == 2 else ""
    if country == "UK":
        country = "GB"
    return first, country


def normalize_seo_url(raw_url, *, primary_host="", known_locale_prefixes=()):
    raw = html.unescape(str(raw_url or "").strip())
    if raw.casefold() in INVALID_LANDING_VALUES:
        return {
            "valid": False,
            "raw_url": raw,
            "normalized_url": "",
            "normalized_host": "",
            "normalized_path": "",
            "query_string": "",
            "locale_prefix": "",
            "market_code": "",
            "reason": "invalid_or_not_set",
        }
    if raw.startswith("//"):
        raw = "https:" + raw
    elif "://" not in raw:
        if not primary_host:
            return {
                "valid": False,
                "raw_url": raw,
                "normalized_url": "",
                "normalized_host": "",
                "normalized_path": "",
                "query_string": "",
                "locale_prefix": "",
                "market_code": "",
                "reason": "relative_url_without_host",
            }
        raw = f"https://{str(primary_host).strip().strip('/')}/{raw.lstrip('/')}"
    try:
        parsed = urlsplit(raw)
        if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
            raise ValueError("unsupported URL")
        host = parsed.hostname.encode("idna").decode("ascii").casefold().strip(".")
    except (UnicodeError, ValueError):
        return {
            "valid": False,
            "raw_url": str(raw_url or "").strip(),
            "normalized_url": "",
            "normalized_host": "",
            "normalized_path": "",
            "query_string": "",
            "locale_prefix": "",
            "market_code": "",
            "reason": "invalid_url",
        }
    if host.startswith("www."):
        host = host[4:]
    port = parsed.port
    if port and not ((parsed.scheme.casefold() == "http" and port == 80) or (parsed.scheme.casefold() == "https" and port == 443)):
        host = f"{host}:{port}"
    path = _clean_path(parsed.path)
    locale_prefix, market_code = _locale_details(path, known_locale_prefixes)
    normalized_url = f"https://{host}{path}"
    return {
        "valid": True,
        "raw_url": str(raw_url or "").strip(),
        "normalized_url": normalized_url,
        "normalized_host": host,
        "normalized_path": path,
        "query_string": parsed.query or "",
        "locale_prefix": locale_prefix,
        "market_code": market_code,
        "reason": "",
    }


def stable_page_key(page_type, shopify_resource_id, canonical_url):
    stable_identity = str(shopify_resource_id or "") or str(canonical_url or "")
    payload = "|".join(
        (
            WORKSPACE_KEY,
            str(page_type or "").casefold(),
            stable_identity,
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def stable_alias_key(source, raw_url, property_identifier=""):
    payload = (
        f"{WORKSPACE_KEY}|{str(source or '').upper()}|"
        f"{str(property_identifier or '')}|{str(raw_url or '')}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def canonical_page_from_shopify(resource, *, primary_host, known_locale_prefixes=()):
    page_type = str(resource.get("page_type") or "other").casefold()
    handle = str(resource.get("handle") or "").strip("/")
    raw_url = str(resource.get("canonical_url") or "").strip()
    if not raw_url:
        path_templates = {
            "product": f"/products/{handle}",
            "collection": f"/collections/{handle}",
            "page": f"/pages/{handle}",
            "blog": f"/blogs/{handle}",
            "article": f"/blogs/{str(resource.get('blog_handle') or '').strip('/')}/{handle}",
        }
        raw_url = path_templates.get(page_type, "")
    normalized = normalize_seo_url(
        raw_url,
        primary_host=primary_host,
        known_locale_prefixes=known_locale_prefixes,
    )
    if not normalized["valid"]:
        raise SEOPhase4Error(
            "Shopify returned a page without a usable canonical URL.",
            code="shopify_canonical_url_invalid",
            retryable=False,
        )
    resource_id = str(resource.get("shopify_resource_id") or resource.get("id") or "")
    if not resource_id:
        raise SEOPhase4Error(
            "Shopify returned a page without a stable resource identifier.",
            code="shopify_resource_id_missing",
            retryable=False,
        )
    return {
        "page_key": stable_page_key(page_type, resource_id, normalized["normalized_url"]),
        "canonical_url": normalized["normalized_url"],
        "normalized_host": normalized["normalized_host"],
        "normalized_path": normalized["normalized_path"],
        "locale_prefix": normalized["locale_prefix"],
        "market_code": normalized["market_code"],
        "page_type": page_type,
        "shopify_resource_id": resource_id,
        "shopify_handle": handle,
        "title": str(resource.get("title") or "")[:500],
        "resource_status": str(resource.get("status") or "")[:100],
        "is_active": bool(resource.get("is_active", True)),
        "source_updated_at": resource.get("updated_at") or None,
    }


def map_alias_to_pages(alias, pages):
    if not alias.get("valid"):
        return {"status": "invalid", "page_key": None, "candidates": [], "reason": alias.get("reason") or "invalid_url"}
    candidates = [
        page
        for page in pages
        if page.get("normalized_host") == alias.get("normalized_host")
        and page.get("normalized_path") == alias.get("normalized_path")
    ]
    if len(candidates) == 1:
        return {"status": "matched", "page_key": candidates[0]["page_key"], "candidates": [], "reason": "exact_canonical_path"}
    if len(candidates) > 1:
        return {
            "status": "ambiguous",
            "page_key": None,
            "candidates": sorted(page["page_key"] for page in candidates),
            "reason": "multiple_exact_canonical_pages",
        }
    reason = "locale_alias_requires_explicit_shopify_mapping" if alias.get("locale_prefix") else "no_exact_shopify_canonical_page"
    return {"status": "unmapped", "page_key": None, "candidates": [], "reason": reason}


def _match_key(value):
    return re.sub(r"\s+", "", str(value or "").strip().casefold())


def shopify_order_match_keys(order):
    values = {
        "shopify_gid": str(order.get("shopify_order_id") or ""),
        "display_name": str(order.get("display_order_name") or order.get("order_name") or ""),
        "legacy_id": str(order.get("legacy_resource_id") or ""),
    }
    result = []
    for key_type, value in values.items():
        clean = _match_key(value)
        if not clean:
            continue
        result.append((clean, key_type))
        if key_type == "display_name" and clean.startswith("#"):
            result.append((clean[1:], "display_name_without_hash"))
        if key_type == "shopify_gid" and "/" in clean:
            result.append((clean.rsplit("/", 1)[-1], "shopify_gid_legacy_id"))
    return sorted(set(result))


def transaction_match_keys(transaction_id):
    clean = _match_key(transaction_id)
    if not clean:
        return []
    keys = {clean}
    if clean.startswith("#"):
        keys.add(clean[1:])
    return sorted(keys)


def reconcile_transaction(transaction, candidate_orders):
    ga4_revenue = _decimal(transaction.get("attributed_purchase_revenue"))
    currency = str(transaction.get("currency") or "").upper()
    if transaction.get("conflict_state"):
        return {
            "state": "duplicate_or_conflicting_transaction",
            "shopify_order_id": None,
            "ga4_attributed_revenue": ga4_revenue,
            "shopify_confirmed_revenue": Decimal("0"),
            "currency": currency,
        }
    unique = {str(row.get("shopify_order_id") or ""): row for row in candidate_orders if row.get("shopify_order_id")}
    if len(unique) != 1:
        return {
            "state": "duplicate_or_conflicting_transaction" if len(unique) > 1 else "ga4_transaction_unmatched",
            "shopify_order_id": None,
            "ga4_attributed_revenue": ga4_revenue,
            "shopify_confirmed_revenue": Decimal("0"),
            "currency": currency,
        }
    order = next(iter(unique.values()))
    state = "confirmed_shopify_match"
    if order.get("is_test"):
        state = "excluded_test_order"
    elif order.get("is_cancelled"):
        state = "excluded_cancelled_order"
    elif order.get("is_fully_refunded"):
        state = "excluded_fully_refunded_order"
    elif currency and order.get("currency") and currency != str(order.get("currency")).upper():
        state = "currency_mismatch"
    confirmed = _decimal(order.get("net_revenue")) if state == "confirmed_shopify_match" else Decimal("0")
    return {
        "state": state,
        "shopify_order_id": order.get("shopify_order_id"),
        "ga4_attributed_revenue": ga4_revenue,
        "shopify_confirmed_revenue": confirmed,
        "currency": str(order.get("currency") or currency).upper(),
    }


def aggregate_gsc_rows(rows):
    clicks = sum((_decimal(row.get("clicks")) for row in rows), Decimal("0"))
    impressions = sum((_decimal(row.get("impressions")) for row in rows), Decimal("0"))
    weighted_position = sum(
        (_decimal(row.get("average_position")) * _decimal(row.get("impressions")) for row in rows),
        Decimal("0"),
    )
    return {
        "clicks": clicks,
        "impressions": impressions,
        "ctr": clicks / impressions if impressions else Decimal("0"),
        "average_position": weighted_position / impressions if impressions else Decimal("0"),
    }


@dataclass(frozen=True)
class ReportingPeriod:
    start_date: date
    end_date: date
    previous_start_date: date
    previous_end_date: date


def reporting_period(preset, *, through_date, custom_start=None, custom_end=None):
    end = _as_date(custom_end) if str(preset) == "Custom dates" else _as_date(through_date)
    if not end:
        raise SEOPhase4Error("No complete reporting date is available.", code="reporting_date_unavailable", retryable=False)
    lengths = {"Last 28 days": 28, "Last 90 days": 90, "Last 12 months": 365}
    if str(preset) == "Custom dates":
        start = _as_date(custom_start)
        if not start or start > end:
            raise SEOPhase4Error("Choose a valid custom reporting period.", code="invalid_custom_period", retryable=False)
    else:
        days = lengths.get(str(preset), 28)
        start = end - timedelta(days=days - 1)
    days = (end - start).days + 1
    previous_end = start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=days - 1)
    return ReportingPeriod(start, end, previous_start, previous_end)


def classify_brand_query(query, brand_terms):
    clean = re.sub(r"\s+", " ", str(query or "").casefold()).strip()
    return any(str(term or "").casefold().strip() in clean for term in brand_terms if str(term or "").strip())


@dataclass(frozen=True)
class ReportingFilters:
    period: ReportingPeriod
    market: str = "All markets"
    device: str = "All devices"
    search: str = "All searches"

    def country_values(self):
        return DEFAULT_MARKET_COUNTRIES.get(self.market, set())

    def device_values(self):
        return DEVICE_VALUES.get(self.device, set())


SHOPIFY_SEO_SHOP_QUERY = """
query SportsCaveSEOShop {
  shop { primaryDomain { host url } }
}
"""

SHOPIFY_SEO_RESOURCE_QUERIES = {
    "product": """
      query SEOProducts($first: Int!, $after: String, $query: String) {
        resources: products(first: $first, after: $after, query: $query, sortKey: UPDATED_AT) {
          pageInfo { hasNextPage endCursor }
          nodes { id title handle status updatedAt onlineStoreUrl }
        }
      }
    """,
    "collection": """
      query SEOCollections($first: Int!, $after: String, $query: String) {
        resources: collections(first: $first, after: $after, query: $query, sortKey: UPDATED_AT) {
          pageInfo { hasNextPage endCursor }
          nodes { id title handle updatedAt onlineStoreUrl }
        }
      }
    """,
    "page": """
      query SEOPages($first: Int!, $after: String, $query: String) {
        resources: pages(first: $first, after: $after, query: $query, sortKey: UPDATED_AT) {
          pageInfo { hasNextPage endCursor }
          nodes { id title handle isPublished updatedAt }
        }
      }
    """,
    "article": """
      query SEOArticles($first: Int!, $after: String, $query: String) {
        resources: articles(first: $first, after: $after, query: $query, sortKey: UPDATED_AT) {
          pageInfo { hasNextPage endCursor }
          nodes { id title handle publishedAt updatedAt blog { id handle title } }
        }
      }
    """,
}

SHOPIFY_SEO_ORDERS_QUERY = """
query SEOOrders($first: Int!, $after: String, $query: String) {
  orders(first: $first, after: $after, query: $query, sortKey: UPDATED_AT) {
    pageInfo { hasNextPage endCursor }
    nodes {
      id
      legacyResourceId
      name
      processedAt
      updatedAt
      cancelledAt
      test
      displayFinancialStatus
      totalPriceSet { shopMoney { amount currencyCode } }
      currentTotalPriceSet { shopMoney { amount currencyCode } }
      totalRefundedSet { shopMoney { amount currencyCode } }
    }
  }
}
"""


class ShopifySEOClient:
    def __init__(self, *, config=None, graphql_request=None):
        self.config = config or shopify_sync.get_config()
        self.graphql_request = graphql_request or shopify_sync.graphql_request

    def _query(self, query, variables=None):
        data, _served_version = self.graphql_request(
            query,
            variables=variables or {},
            config=self.config,
        )
        return data

    def primary_host(self):
        shop = (self._query(SHOPIFY_SEO_SHOP_QUERY).get("shop") or {})
        domain = shop.get("primaryDomain") or {}
        return str(domain.get("host") or urlsplit(str(domain.get("url") or "")).hostname or "").strip()

    def iter_resources(self, page_type, *, updated_after="", page_size=100):
        if page_type not in SHOPIFY_SEO_RESOURCE_QUERIES:
            raise SEOPhase4Error("Unsupported Shopify page type.", code="unsupported_shopify_page_type", retryable=False)
        after = None
        query_filter = f"updated_at:>'{updated_after}'" if updated_after else None
        while True:
            data = self._query(
                SHOPIFY_SEO_RESOURCE_QUERIES[page_type],
                {"first": min(max(int(page_size), 1), 250), "after": after, "query": query_filter},
            )
            connection = data.get("resources") or {}
            nodes = list(connection.get("nodes") or [])
            for node in nodes:
                blog = node.get("blog") or {}
                yield {
                    "page_type": page_type,
                    "shopify_resource_id": node.get("id") or "",
                    "title": node.get("title") or "",
                    "handle": node.get("handle") or "",
                    "blog_handle": blog.get("handle") or "",
                    "blog_id": blog.get("id") or "",
                    "blog_title": blog.get("title") or "",
                    "canonical_url": node.get("onlineStoreUrl") or "",
                    "status": node.get("status") or ("ACTIVE" if node.get("isPublished", node.get("publishedAt")) else "UNPUBLISHED"),
                    "is_active": str(node.get("status") or "ACTIVE").upper() not in {"ARCHIVED", "DRAFT"}
                    and bool(node.get("isPublished", node.get("publishedAt", True))),
                    "updated_at": node.get("updatedAt") or "",
                }
            page_info = connection.get("pageInfo") or {}
            if not nodes or not page_info.get("hasNextPage") or not page_info.get("endCursor"):
                break
            after = page_info["endCursor"]

    def iter_order_facts(self, *, updated_after="", page_size=100):
        after = None
        query_filter = f"updated_at:>'{updated_after}'" if updated_after else None
        while True:
            data = self._query(
                SHOPIFY_SEO_ORDERS_QUERY,
                {"first": min(max(int(page_size), 1), 250), "after": after, "query": query_filter},
            )
            connection = data.get("orders") or {}
            nodes = list(connection.get("nodes") or [])
            for node in nodes:
                yield normalize_shopify_order_fact(node)
            page_info = connection.get("pageInfo") or {}
            if not nodes or not page_info.get("hasNextPage") or not page_info.get("endCursor"):
                break
            after = page_info["endCursor"]


def _shop_money(node, field):
    return ((node.get(field) or {}).get("shopMoney") or {})


def normalize_shopify_order_fact(node):
    gross_money = _shop_money(node, "totalPriceSet")
    current_money = _shop_money(node, "currentTotalPriceSet")
    refunded_money = _shop_money(node, "totalRefundedSet")
    gross = _decimal(gross_money.get("amount"))
    net = _decimal(current_money.get("amount"))
    refunded = _decimal(refunded_money.get("amount"))
    currency = str(
        current_money.get("currencyCode")
        or gross_money.get("currencyCode")
        or refunded_money.get("currencyCode")
        or ""
    ).upper()
    financial_status = str(node.get("displayFinancialStatus") or "").upper()
    return {
        "shopify_order_id": str(node.get("id") or ""),
        "display_order_name": str(node.get("name") or ""),
        "legacy_resource_id": str(node.get("legacyResourceId") or ""),
        "order_date": _as_date(node.get("processedAt") or node.get("updatedAt")),
        "financial_status": financial_status,
        "is_test": bool(node.get("test")),
        "is_cancelled": bool(node.get("cancelledAt")),
        "is_fully_refunded": financial_status == "REFUNDED" or bool(gross > 0 and net <= 0 and refunded >= gross),
        "gross_revenue": gross,
        "refunded_revenue": refunded,
        "net_revenue": net,
        "currency": currency,
        "source_updated_at": node.get("updatedAt") or None,
    }


def _ga4_transaction_filter():
    return {
        "andGroup": {
            "expressions": [
                GoogleSEOReportingClient._organic_filter(),
                {
                    "filter": {
                        "fieldName": "transactionId",
                        "stringFilter": {"matchType": "FULL_REGEXP", "value": ".+"},
                    }
                },
            ]
        }
    }


def compatible_ga4_transaction_dimensions(client, property_id):
    property_id = str(property_id or "")
    if not property_id.startswith("properties/"):
        property_id = f"properties/{property_id}"
    dimensions = (*GA4_TRANSACTION_REQUIRED_DIMENSIONS, GA4_TRANSACTION_OPTIONAL_DIMENSION)
    payload = client._post(
        f"{google_seo.GA4_DATA_ENDPOINT}/{property_id}:checkCompatibility",
        {
            "dimensions": [{"name": name} for name in dimensions],
            "metrics": [{"name": name} for name in GA4_TRANSACTION_METRICS],
            "dimensionFilter": _ga4_transaction_filter(),
        },
        stage="ga4_transaction_compatibility",
    )
    compatible_dimensions = {
        str(((row or {}).get("dimensionMetadata") or {}).get("apiName") or "")
        for row in payload.get("dimensionCompatibilities") or []
        if str((row or {}).get("compatibility") or "") == "COMPATIBLE"
    }
    compatible_metrics = {
        str(((row or {}).get("metricMetadata") or {}).get("apiName") or "")
        for row in payload.get("metricCompatibilities") or []
        if str((row or {}).get("compatibility") or "") == "COMPATIBLE"
    }
    if not set(GA4_TRANSACTION_REQUIRED_DIMENSIONS).issubset(compatible_dimensions):
        raise SEOPhase4Error(
            "The selected Analytics property does not support transaction-level organic landing-page reconciliation.",
            code="ga4_transaction_dimensions_incompatible",
            retryable=False,
        )
    if not set(GA4_TRANSACTION_METRICS).issubset(compatible_metrics):
        raise SEOPhase4Error(
            "The selected Analytics property does not support the required transaction metrics.",
            code="ga4_transaction_metrics_incompatible",
            retryable=False,
        )
    return (*GA4_TRANSACTION_REQUIRED_DIMENSIONS, *(
        (GA4_TRANSACTION_OPTIONAL_DIMENSION,)
        if GA4_TRANSACTION_OPTIONAL_DIMENSION in compatible_dimensions else ()
    ))


def fetch_ga4_transactions_date(client, property_id, slice_date, *, currency="", dimensions=None):
    property_id = str(property_id or "")
    if not property_id.startswith("properties/"):
        property_id = f"properties/{property_id}"
    slice_date = _as_date(slice_date)
    dimensions = tuple(dimensions or (*GA4_TRANSACTION_REQUIRED_DIMENSIONS, GA4_TRANSACTION_OPTIONAL_DIMENSION))
    metrics = GA4_TRANSACTION_METRICS
    offset = 0
    row_count = None
    rows_by_transaction = {}
    metadata = {}
    while row_count is None or offset < row_count:
        payload = client._post(
            f"{google_seo.GA4_DATA_ENDPOINT}/{property_id}:runReport",
            {
                "dateRanges": [{"startDate": slice_date.isoformat(), "endDate": slice_date.isoformat()}],
                "dimensions": [{"name": name} for name in dimensions],
                "metrics": [{"name": name} for name in metrics],
                "dimensionFilter": _ga4_transaction_filter(),
                "limit": str(GA4_PAGE_SIZE),
                "offset": str(offset),
                "keepEmptyRows": False,
            },
            stage="ga4_daily_transactions",
        )
        metadata = dict(payload.get("metadata") or metadata)
        row_count = _integer(payload.get("rowCount"))
        rows = list(payload.get("rows") or [])
        if not rows:
            break
        dimension_headers = [str(item.get("name") or "") for item in payload.get("dimensionHeaders") or []]
        metric_headers = [str(item.get("name") or "") for item in payload.get("metricHeaders") or []]
        for row in rows:
            dimension_values = [str((item or {}).get("value") or "") for item in row.get("dimensionValues") or []]
            metric_values = [str((item or {}).get("value") or "0") for item in row.get("metricValues") or []]
            dims = dict(zip(dimension_headers, dimension_values))
            values = dict(zip(metric_headers, metric_values))
            transaction_id = str(dims.get("transactionId") or "").strip()
            if transaction_id.casefold() in INVALID_LANDING_VALUES:
                continue
            candidate = {
                "transaction_id": transaction_id,
                "transaction_date": slice_date,
                "raw_landing_page": dims.get("landingPagePlusQueryString", ""),
                "hostname": dims.get("hostname", ""),
                "country_id": dims.get("countryId", ""),
                "device_category": dims.get("deviceCategory", ""),
                "session_channel_group": dims.get("sessionDefaultChannelGroup", "Organic Search"),
                "transaction_count": _decimal(values.get("transactions")),
                "attributed_purchase_revenue": _decimal(values.get("purchaseRevenue")),
                "currency": str(metadata.get("currencyCode") or currency or "").upper(),
                "conflict_state": "",
                "is_complete": True,
            }
            existing = rows_by_transaction.get(transaction_id)
            if existing:
                identity_fields = (
                    "transaction_date",
                    "raw_landing_page",
                    "hostname",
                    "country_id",
                    "device_category",
                    "session_channel_group",
                    "currency",
                )
                if any(existing.get(field) != candidate.get(field) for field in identity_fields):
                    existing["conflict_state"] = "duplicate_dimension_rows"
                existing["transaction_count"] = max(existing["transaction_count"], candidate["transaction_count"])
                existing["attributed_purchase_revenue"] = max(
                    existing["attributed_purchase_revenue"],
                    candidate["attributed_purchase_revenue"],
                )
            else:
                rows_by_transaction[transaction_id] = candidate
        offset += len(rows)
    return {
        "date": slice_date,
        "rows": list(rows_by_transaction.values()),
        "rows_received": sum(1 for _ in rows_by_transaction.values()),
        "currency": str(metadata.get("currencyCode") or currency or "").upper(),
    }


def _clean_run(row):
    row = dict(row or {})
    for field in (
        "requested_start_date",
        "requested_end_date",
        "active_slice_date",
        "checkpoint_date",
        "started_at",
        "completed_at",
        "lease_expires_at",
        "created_at",
        "updated_at",
    ):
        row[field] = _iso(row.get(field))
    for field in ("rows_received", "rows_written", "rows_rejected", "attempt_count"):
        row[field] = _integer(row.get(field))
    return row


class PostgresSEOPhase4Store:
    def __init__(self, backend=None):
        self.backend = backend
        self._schema_ready = False

    def _backend(self):
        if self.backend is not None:
            return self.backend
        import supabase_backend

        return supabase_backend

    def ensure_schema(self):
        if self._schema_ready:
            return
        migration = BASE_DIR / "migrations" / PHASE4_MIGRATION
        if not migration.is_file():
            raise SEOPhase4Error("SEO Phase 4 storage is unavailable.", code="migration_missing")
        try:
            with self._backend().connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(migration.read_text(encoding="utf-8"))
                connection.commit()
        except Exception as error:
            raise SEOPhase4Error("SEO Phase 4 storage could not be prepared.", code="storage_unavailable") from error
        self._schema_ready = True

    def phase3_health(self, *, now=None):
        now = now or utc_now()
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT source, status, mode, checkpoint_date, active_slice_date,
                           lease_expires_at, completed_start_date, completed_end_date,
                           rows_received, updated_at
                    FROM seo_sync_runs
                    WHERE workspace_key=%s AND source IN ('GSC', 'GA4')
                    ORDER BY created_at DESC
                    """,
                    (WORKSPACE_KEY,),
                )
                runs = [dict(row) for row in cursor.fetchall() or []]
                cursor.execute(
                    """
                    SELECT source, earliest_stored_date, latest_stored_date, rows_stored
                    FROM seo_data_inventories
                    WHERE workspace_key=%s AND source IN ('GSC', 'GA4')
                    """,
                    (WORKSPACE_KEY,),
                )
                inventories = {str(row.get("source") or ""): dict(row) for row in cursor.fetchall() or []}
        result = {}
        safe = True
        for source in ("GSC", "GA4"):
            source_runs = [row for row in runs if row.get("source") == source]
            active = [row for row in source_runs if row.get("status") in ACTIVE_STATUSES]
            latest = source_runs[0] if source_runs else {}
            lease = latest.get("lease_expires_at")
            lease_current = bool(lease and lease > now) if isinstance(lease, datetime) else False
            duplicate_active = len(active) > 1
            stalled = bool(latest.get("status") == "running" and not lease_current)
            inventory = inventories.get(source, {})
            healthy_complete = bool(
                inventory.get("latest_stored_date")
                and not active
                and latest.get("status") == "completed"
            )
            advancing = bool(latest.get("status") == "running" and lease_current and latest.get("active_slice_date"))
            safe = safe and not duplicate_active
            result[source] = {
                "status": latest.get("status") or "not_started",
                "mode": latest.get("mode") or "",
                "checkpoint_date": _iso(latest.get("checkpoint_date")),
                "active_slice_date": _iso(latest.get("active_slice_date")),
                "latest_stored_date": _iso(inventory.get("latest_stored_date")),
                "earliest_stored_date": _iso(inventory.get("earliest_stored_date")),
                "rows_stored": _integer(inventory.get("rows_stored")),
                "active_run_count": len(active),
                "duplicate_active": duplicate_active,
                "healthy_complete": healthy_complete,
                "advancing": advancing,
                "restart_safe": bool(latest.get("checkpoint_date") or not active),
                "stalled_reclaimable": stalled,
            }
        result["safe_to_start_phase4"] = safe and bool(inventories.get("GSC", {}).get("latest_stored_date"))
        return result

    def queue_run(self, source, mode, *, requested_by="", start_date=None, end_date=None):
        source = str(source or "")
        mode = str(mode or "").casefold()
        if source not in PHASE4_SOURCES or mode not in {"historical", "daily", "manual"}:
            raise SEOPhase4Error("The Phase 4 job request is invalid.", code="invalid_phase4_job", retryable=False)
        self.ensure_schema()
        run_id = str(uuid.uuid4())
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"seo-phase4:{WORKSPACE_KEY}:{source}",))
                cursor.execute(
                    """
                    SELECT * FROM seo_phase4_runs
                    WHERE workspace_key=%s AND source=%s AND status IN ('queued', 'running')
                    ORDER BY created_at LIMIT 1
                    """,
                    (WORKSPACE_KEY, source),
                )
                row = cursor.fetchone()
                if not row:
                    cursor.execute(
                        """
                        INSERT INTO seo_phase4_runs(
                            id, workspace_key, source, mode, status,
                            requested_start_date, requested_end_date, requested_by
                        ) VALUES (%s, %s, %s, %s, 'queued', %s, %s, %s)
                        RETURNING *
                        """,
                        (
                            run_id,
                            WORKSPACE_KEY,
                            source,
                            mode,
                            _as_date(start_date),
                            _as_date(end_date),
                            str(requested_by or "")[:200],
                        ),
                    )
                    row = cursor.fetchone()
            connection.commit()
        return _clean_run(row)

    def claim_next_run(self, lease_owner, *, source="", now=None):
        self.ensure_schema()
        now = now or utc_now()
        source_clause = " AND source=%s" if source else ""
        params = [now]
        if source:
            params.append(source)
        params.extend((str(lease_owner or "")[:200], now, now + timedelta(seconds=LEASE_SECONDS)))
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    WITH candidate AS (
                        SELECT id FROM seo_phase4_runs
                        WHERE status IN ('queued', 'running')
                          AND (status='queued' OR lease_expires_at IS NULL OR lease_expires_at < %s)
                          AND (
                              source<>'mapping' OR NOT EXISTS (
                                  SELECT 1 FROM seo_phase4_runs AS dependency
                                  WHERE dependency.workspace_key=seo_phase4_runs.workspace_key
                                    AND dependency.source IN ('shopify_pages', 'ga4_transactions')
                                    AND dependency.status IN ('queued', 'running')
                              )
                          )
                          AND (
                              source<>'reconciliation' OR NOT EXISTS (
                                  SELECT 1 FROM seo_phase4_runs AS dependency
                                  WHERE dependency.workspace_key=seo_phase4_runs.workspace_key
                                    AND dependency.source IN ('shopify_orders', 'ga4_transactions', 'mapping')
                                    AND dependency.status IN ('queued', 'running')
                              )
                          )
                          {source_clause}
                        ORDER BY CASE source
                            WHEN 'shopify_pages' THEN 1
                            WHEN 'shopify_orders' THEN 2
                            WHEN 'ga4_transactions' THEN 3
                            WHEN 'mapping' THEN 4
                            WHEN 'reconciliation' THEN 5
                            ELSE 6 END,
                            created_at
                        FOR UPDATE SKIP LOCKED
                        LIMIT 1
                    )
                    UPDATE seo_phase4_runs AS run
                    SET status='running', lease_owner=%s,
                        started_at=COALESCE(started_at, %s), lease_expires_at=%s,
                        attempt_count=attempt_count + 1, updated_at=now()
                    FROM candidate WHERE run.id=candidate.id
                    RETURNING run.*
                    """,
                    params,
                )
                row = cursor.fetchone()
            connection.commit()
        return _clean_run(row) if row else None

    def renew_lease(self, run_id, lease_owner, *, active_slice_date=None):
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE seo_phase4_runs
                    SET lease_expires_at=%s, active_slice_date=%s, updated_at=now()
                    WHERE id=%s AND status='running' AND lease_owner=%s RETURNING id
                    """,
                    (utc_now() + timedelta(seconds=LEASE_SECONDS), _as_date(active_slice_date), run_id, lease_owner),
                )
                ok = bool(cursor.fetchone())
            connection.commit()
        return ok

    def checkpoint_run(self, run_id, lease_owner, *, checkpoint_date=None, cursor_payload=None, received=0, written=0, rejected=0):
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE seo_phase4_runs
                    SET checkpoint_date=COALESCE(%s, checkpoint_date),
                        active_slice_date=COALESCE(%s, active_slice_date),
                        cursor_payload=COALESCE(%s, cursor_payload),
                        rows_received=rows_received + %s,
                        rows_written=rows_written + %s,
                        rows_rejected=rows_rejected + %s,
                        lease_expires_at=%s, updated_at=now()
                    WHERE id=%s AND status='running' AND lease_owner=%s RETURNING id
                    """,
                    (
                        _as_date(checkpoint_date),
                        _as_date(checkpoint_date),
                        json.dumps(cursor_payload) if cursor_payload is not None else None,
                        int(received or 0),
                        int(written or 0),
                        int(rejected or 0),
                        utc_now() + timedelta(seconds=LEASE_SECONDS),
                        run_id,
                        lease_owner,
                    ),
                )
                ok = bool(cursor.fetchone())
            connection.commit()
        if not ok:
            raise SEOPhase4Error("The Phase 4 job lease was lost.", code="phase4_lease_lost")

    def complete_run(self, run_id, lease_owner, *, status="completed"):
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE seo_phase4_runs
                    SET status=%s, completed_at=now(), active_slice_date=NULL,
                        lease_owner='', lease_expires_at=NULL,
                        error_code='', error_summary='', updated_at=now()
                    WHERE id=%s AND status='running' AND lease_owner=%s RETURNING *
                    """,
                    (status, run_id, lease_owner),
                )
                row = cursor.fetchone()
            connection.commit()
        return _clean_run(row)

    def fail_run(self, run_id, lease_owner, error, *, partial=False):
        code = str(getattr(error, "code", "seo_phase4_failed"))[:100]
        message = str(getattr(error, "public_message", "The Phase 4 job could not be completed safely."))[:300]
        status = "partial" if partial else "failed"
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE seo_phase4_runs
                    SET status=%s, completed_at=now(), lease_owner='', lease_expires_at=NULL,
                        error_code=%s, error_summary=%s, updated_at=now()
                    WHERE id=%s AND status='running' AND lease_owner=%s RETURNING *
                    """,
                    (status, code, message, run_id, lease_owner),
                )
                row = cursor.fetchone()
                cursor.execute(
                    """
                    UPDATE seo_google_connections
                    SET phase4_error_code=%s, phase4_error_summary=%s, updated_at=now()
                    WHERE workspace_key=%s
                    """,
                    (code, message, WORKSPACE_KEY),
                )
            connection.commit()
        return _clean_run(row)

    def source_state(self, source, resource_type=""):
        self.ensure_schema()
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT * FROM seo_phase4_source_state
                    WHERE workspace_key=%s AND source=%s AND resource_type=%s
                    """,
                    (WORKSPACE_KEY, source, resource_type),
                )
                return dict(cursor.fetchone() or {})

    def save_source_state(self, source, resource_type="", *, checkpoint_value="", latest_completed_date=None, status="completed"):
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO seo_phase4_source_state(
                        workspace_key, source, resource_type, checkpoint_value,
                        latest_completed_date, last_success_at, status, error_code, error_summary
                    ) VALUES (%s, %s, %s, %s, %s, now(), %s, '', '')
                    ON CONFLICT (workspace_key, source, resource_type) DO UPDATE SET
                        checkpoint_value=EXCLUDED.checkpoint_value,
                        latest_completed_date=COALESCE(EXCLUDED.latest_completed_date, seo_phase4_source_state.latest_completed_date),
                        last_success_at=now(), status=EXCLUDED.status,
                        error_code='', error_summary='', updated_at=now()
                    """,
                    (
                        WORKSPACE_KEY,
                        source,
                        resource_type,
                        str(checkpoint_value or "")[:500],
                        _as_date(latest_completed_date),
                        status,
                    ),
                )
                if source == "shopify_orders" and latest_completed_date:
                    cursor.execute(
                        """
                        UPDATE seo_google_connections
                        SET shopify_data_through_date=%s, updated_at=now()
                        WHERE workspace_key=%s
                        """,
                        (_as_date(latest_completed_date), WORKSPACE_KEY),
                    )
            connection.commit()

    def connection_record(self):
        self.ensure_schema()
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT gsc_site_url, ga4_property_id, ga4_property_timezone,
                           ga4_property_currency, gsc_data_through_date,
                           ga4_data_through_date, shopify_data_through_date
                    FROM seo_google_connections WHERE workspace_key=%s
                    """,
                    (WORKSPACE_KEY,),
                )
                return dict(cursor.fetchone() or {})

    def ga4_completed_bounds(self, property_id):
        self.ensure_schema()
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT MIN(date) AS earliest_date, MAX(date) AS latest_date
                    FROM seo_ga4_daily_landing_pages
                    WHERE workspace_key=%s AND ga4_property_id=%s AND is_complete=TRUE
                    """,
                    (WORKSPACE_KEY, property_id),
                )
                row = dict(cursor.fetchone() or {})
        return _as_date(row.get("earliest_date")), _as_date(row.get("latest_date"))

    def replace_ga4_transactions_date(self, property_id, slice_data):
        slice_date = _as_date(slice_data.get("date"))
        rows = list(slice_data.get("rows") or [])
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT COUNT(*) AS count FROM seo_ga4_transactions
                    WHERE workspace_key=%s AND ga4_property_id=%s AND transaction_date=%s
                    """,
                    (WORKSPACE_KEY, property_id, slice_date),
                )
                previous = _integer((cursor.fetchone() or {}).get("count"))
                cursor.execute(
                    """
                    DELETE FROM seo_revenue_reconciliations
                    WHERE workspace_key=%s AND ga4_property_id=%s AND transaction_date=%s
                    """,
                    (WORKSPACE_KEY, property_id, slice_date),
                )
                cursor.execute(
                    """
                    DELETE FROM seo_ga4_transactions
                    WHERE workspace_key=%s AND ga4_property_id=%s AND transaction_date=%s
                    """,
                    (WORKSPACE_KEY, property_id, slice_date),
                )
                if rows:
                    cursor.executemany(
                        """
                        INSERT INTO seo_ga4_transactions(
                            workspace_key, ga4_property_id, transaction_id, transaction_date,
                            raw_landing_page, hostname, country_id, device_category,
                            session_channel_group, transaction_count,
                            attributed_purchase_revenue, currency, conflict_state, is_complete
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        [
                            (
                                WORKSPACE_KEY,
                                property_id,
                                str(row.get("transaction_id") or "")[:500],
                                slice_date,
                                str(row.get("raw_landing_page") or "")[:2000],
                                str(row.get("hostname") or "")[:500],
                                str(row.get("country_id") or "")[:20],
                                str(row.get("device_category") or "")[:50],
                                str(row.get("session_channel_group") or "Organic Search")[:100],
                                _decimal(row.get("transaction_count")),
                                _decimal(row.get("attributed_purchase_revenue")),
                                str(row.get("currency") or "")[:20].upper(),
                                str(row.get("conflict_state") or "")[:100],
                                bool(row.get("is_complete", True)),
                            )
                            for row in rows
                            if str(row.get("transaction_id") or "").strip()
                        ],
                    )
            connection.commit()
        return {"inserted": len(rows), "replaced": previous}

    def upsert_canonical_pages(self, pages):
        pages = list(pages or [])
        if not pages:
            return 0
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO seo_canonical_pages(
                        page_key, workspace_key, canonical_url, normalized_host,
                        normalized_path, locale_prefix, market_code, page_type,
                        shopify_resource_id, shopify_handle, title, resource_status,
                        is_active, source_updated_at, last_seen_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                    ON CONFLICT (workspace_key, page_type, shopify_resource_id) DO UPDATE SET
                        canonical_url=EXCLUDED.canonical_url,
                        normalized_host=EXCLUDED.normalized_host,
                        normalized_path=EXCLUDED.normalized_path,
                        locale_prefix=EXCLUDED.locale_prefix,
                        market_code=EXCLUDED.market_code,
                        shopify_handle=EXCLUDED.shopify_handle,
                        title=EXCLUDED.title,
                        resource_status=EXCLUDED.resource_status,
                        is_active=EXCLUDED.is_active,
                        source_updated_at=EXCLUDED.source_updated_at,
                        last_seen_at=now(), updated_at=now()
                    """,
                    [
                        (
                            page["page_key"], WORKSPACE_KEY, page["canonical_url"],
                            page["normalized_host"], page["normalized_path"],
                            page.get("locale_prefix", ""), page.get("market_code", ""),
                            page["page_type"], page.get("shopify_resource_id", ""),
                            page.get("shopify_handle", ""), page.get("title", ""),
                            page.get("resource_status", ""), bool(page.get("is_active", True)),
                            page.get("source_updated_at") or None,
                        )
                        for page in pages
                    ],
                )
                cursor.executemany(
                    """
                    INSERT INTO seo_url_aliases(
                        alias_key, workspace_key, source, property_identifier, raw_url, normalized_url,
                        normalized_host, normalized_path, locale_prefix, market_code,
                        canonical_page_key, mapping_status, mapping_reason
                    ) VALUES (%s, %s, 'Shopify', %s, %s, %s, %s, %s, %s, %s, %s, 'matched', 'shopify_canonical')
                    ON CONFLICT (workspace_key, source, property_identifier, raw_url) DO UPDATE SET
                        normalized_url=EXCLUDED.normalized_url,
                        normalized_host=EXCLUDED.normalized_host,
                        normalized_path=EXCLUDED.normalized_path,
                        locale_prefix=EXCLUDED.locale_prefix,
                        market_code=EXCLUDED.market_code,
                        canonical_page_key=EXCLUDED.canonical_page_key,
                        mapping_status='matched', mapping_reason='shopify_canonical',
                        last_seen_at=now(), updated_at=now()
                    """,
                    [
                        (
                            stable_alias_key("Shopify", page["canonical_url"], page["normalized_host"]),
                            WORKSPACE_KEY, page["normalized_host"],
                            page["canonical_url"], page["canonical_url"],
                            page["normalized_host"], page["normalized_path"],
                            page.get("locale_prefix", ""), page.get("market_code", ""),
                            page["page_key"],
                        )
                        for page in pages
                    ],
                )
            connection.commit()
        return len(pages)

    def upsert_shopify_order_facts(self, orders):
        orders = list(orders or [])
        if not orders:
            return 0
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO seo_shopify_order_facts(
                        workspace_key, shopify_order_id, display_order_name,
                        legacy_resource_id, order_date, financial_status, is_test,
                        is_cancelled, is_fully_refunded, gross_revenue,
                        refunded_revenue, net_revenue, currency, source_updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (workspace_key, shopify_order_id) DO UPDATE SET
                        display_order_name=EXCLUDED.display_order_name,
                        legacy_resource_id=EXCLUDED.legacy_resource_id,
                        order_date=EXCLUDED.order_date,
                        financial_status=EXCLUDED.financial_status,
                        is_test=EXCLUDED.is_test,
                        is_cancelled=EXCLUDED.is_cancelled,
                        is_fully_refunded=EXCLUDED.is_fully_refunded,
                        gross_revenue=EXCLUDED.gross_revenue,
                        refunded_revenue=EXCLUDED.refunded_revenue,
                        net_revenue=EXCLUDED.net_revenue,
                        currency=EXCLUDED.currency,
                        source_updated_at=EXCLUDED.source_updated_at,
                        imported_at=now(), updated_at=now()
                    """,
                    [
                        (
                            WORKSPACE_KEY, order["shopify_order_id"],
                            order.get("display_order_name", ""), order.get("legacy_resource_id", ""),
                            _as_date(order.get("order_date")), order.get("financial_status", ""),
                            bool(order.get("is_test")), bool(order.get("is_cancelled")),
                            bool(order.get("is_fully_refunded")), _decimal(order.get("gross_revenue")),
                            _decimal(order.get("refunded_revenue")), _decimal(order.get("net_revenue")),
                            str(order.get("currency") or "")[:20].upper(),
                            order.get("source_updated_at") or None,
                        )
                        for order in orders
                    ],
                )
                order_ids = [order["shopify_order_id"] for order in orders]
                cursor.execute(
                    "DELETE FROM seo_shopify_order_match_keys WHERE workspace_key=%s AND shopify_order_id=ANY(%s)",
                    (WORKSPACE_KEY, order_ids),
                )
                key_rows = [
                    (WORKSPACE_KEY, match_key, order["shopify_order_id"], key_type)
                    for order in orders
                    for match_key, key_type in shopify_order_match_keys(order)
                ]
                if key_rows:
                    cursor.executemany(
                        """
                        INSERT INTO seo_shopify_order_match_keys(
                            workspace_key, match_key, shopify_order_id, key_type
                        ) VALUES (%s, %s, %s, %s)
                        ON CONFLICT (workspace_key, match_key, shopify_order_id) DO UPDATE SET
                            key_type=EXCLUDED.key_type, updated_at=now()
                        """,
                        key_rows,
                    )
                cursor.execute(
                    """
                    UPDATE seo_shopify_order_match_keys AS key
                    SET is_conflicting=(
                        SELECT COUNT(DISTINCT other.shopify_order_id) > 1
                        FROM seo_shopify_order_match_keys AS other
                        WHERE other.workspace_key=key.workspace_key
                          AND other.match_key=key.match_key
                    ), updated_at=now()
                    WHERE key.workspace_key=%s
                    """,
                    (WORKSPACE_KEY,),
                )
                cursor.execute(
                    """
                    UPDATE seo_google_connections
                    SET shopify_data_through_date=(
                        SELECT MAX(order_date) FROM seo_shopify_order_facts WHERE workspace_key=%s
                    ), updated_at=now()
                    WHERE workspace_key=%s
                    """,
                    (WORKSPACE_KEY, WORKSPACE_KEY),
                )
            connection.commit()
        return len(orders)

    def get_settings(self):
        self.ensure_schema()
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT brand_terms, known_locale_prefixes, updated_by, updated_at FROM seo_reporting_settings WHERE workspace_key=%s",
                    (WORKSPACE_KEY,),
                )
                row = dict(cursor.fetchone() or {})
        row["brand_terms"] = list(row.get("brand_terms") or [])
        row["known_locale_prefixes"] = list(row.get("known_locale_prefixes") or [])
        return row

    def save_settings(self, *, brand_terms, known_locale_prefixes, updated_by=""):
        clean_terms = sorted({str(value or "").strip().casefold() for value in brand_terms if str(value or "").strip()})
        clean_locales = sorted({str(value or "").strip().strip("/").casefold() for value in known_locale_prefixes if str(value or "").strip()})
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO seo_reporting_settings(
                        workspace_key, brand_terms, known_locale_prefixes, updated_by
                    ) VALUES (%s, %s, %s, %s)
                    ON CONFLICT (workspace_key) DO UPDATE SET
                        brand_terms=EXCLUDED.brand_terms,
                        known_locale_prefixes=EXCLUDED.known_locale_prefixes,
                        updated_by=EXCLUDED.updated_by, updated_at=now()
                    """,
                    (WORKSPACE_KEY, json.dumps(clean_terms), json.dumps(clean_locales), str(updated_by or "")[:200]),
                )
            connection.commit()
        return {"brand_terms": clean_terms, "known_locale_prefixes": clean_locales}

    def map_saved_urls(self):
        settings = self.get_settings()
        known_locales = settings.get("known_locale_prefixes") or []
        connection_record = self.connection_record()
        gsc_property = str(connection_record.get("gsc_site_url") or "")
        ga4_property = str(connection_record.get("ga4_property_id") or "")
        gsc_site = normalize_seo_url(gsc_property)
        primary_host = gsc_site.get("normalized_host") if gsc_site.get("valid") else ""
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT page_key, canonical_url, normalized_host, normalized_path,
                           locale_prefix, market_code, page_type, title
                    FROM seo_canonical_pages
                    WHERE workspace_key=%s AND is_active=TRUE
                    """,
                    (WORKSPACE_KEY,),
                )
                pages = [dict(row) for row in cursor.fetchall() or []]
                cursor.execute(
                    """
                    SELECT DISTINCT page_url FROM seo_gsc_daily_details
                    WHERE workspace_key=%s AND gsc_site_url=%s
                    """,
                    (WORKSPACE_KEY, gsc_property),
                )
                gsc_rows = [str(row.get("page_url") or "") for row in cursor.fetchall() or []]
                cursor.execute(
                    """
                    SELECT DISTINCT hostname, landing_page_path_query
                    FROM seo_ga4_daily_landing_pages
                    WHERE workspace_key=%s AND ga4_property_id=%s
                    """,
                    (WORKSPACE_KEY, ga4_property),
                )
                ga4_rows = [dict(row) for row in cursor.fetchall() or []]

                alias_rows = []
                source_updates = []
                for raw_url in gsc_rows:
                    normalized = normalize_seo_url(
                        raw_url,
                        primary_host=primary_host,
                        known_locale_prefixes=known_locales,
                    )
                    mapping = map_alias_to_pages(normalized, pages)
                    alias_rows.append(self._alias_row("GSC", gsc_property, raw_url, normalized, mapping))
                    source_updates.append(("GSC", raw_url, "", mapping))
                for row in ga4_rows:
                    hostname = str(row.get("hostname") or primary_host)
                    landing = str(row.get("landing_page_path_query") or "")
                    raw_url = f"https://{hostname}/{landing.lstrip('/')}" if hostname else landing
                    normalized = normalize_seo_url(
                        raw_url,
                        primary_host=primary_host,
                        known_locale_prefixes=known_locales,
                    )
                    mapping = map_alias_to_pages(normalized, pages)
                    alias_rows.append(self._alias_row("GA4", ga4_property, raw_url, normalized, mapping))
                    source_updates.append(("GA4", str(row.get("hostname") or ""), landing, mapping))

                if alias_rows:
                    cursor.executemany(
                        """
                        INSERT INTO seo_url_aliases(
                            alias_key, workspace_key, source, property_identifier, raw_url, normalized_url,
                            normalized_host, normalized_path, raw_query_string,
                            locale_prefix, market_code, canonical_page_key,
                            mapping_status, mapping_reason, candidate_page_keys
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (workspace_key, source, property_identifier, raw_url) DO UPDATE SET
                            normalized_url=EXCLUDED.normalized_url,
                            normalized_host=EXCLUDED.normalized_host,
                            normalized_path=EXCLUDED.normalized_path,
                            raw_query_string=EXCLUDED.raw_query_string,
                            locale_prefix=EXCLUDED.locale_prefix,
                            market_code=EXCLUDED.market_code,
                            canonical_page_key=EXCLUDED.canonical_page_key,
                            mapping_status=EXCLUDED.mapping_status,
                            mapping_reason=EXCLUDED.mapping_reason,
                            candidate_page_keys=EXCLUDED.candidate_page_keys,
                            last_seen_at=now(), updated_at=now()
                        """,
                        alias_rows,
                    )
                gsc_updates = [
                    (update[3].get("page_key"), update[3]["status"], WORKSPACE_KEY, update[1])
                    for update in source_updates if update[0] == "GSC"
                ]
                if gsc_updates:
                    cursor.executemany(
                        """
                        UPDATE seo_gsc_daily_details
                        SET canonical_page_key=%s, mapping_status=%s
                        WHERE workspace_key=%s AND gsc_site_url=%s AND page_url=%s
                        """,
                        [(*row[:3], gsc_property, row[3]) for row in gsc_updates],
                    )
                ga4_updates = [
                    (update[3].get("page_key"), update[3]["status"], WORKSPACE_KEY, update[1], update[2])
                    for update in source_updates if update[0] == "GA4"
                ]
                if ga4_updates:
                    cursor.executemany(
                        """
                        UPDATE seo_ga4_daily_landing_pages
                        SET canonical_page_key=%s, mapping_status=%s
                        WHERE workspace_key=%s AND ga4_property_id=%s
                          AND hostname=%s AND landing_page_path_query=%s
                        """,
                        [(*row[:3], ga4_property, row[3], row[4]) for row in ga4_updates],
                    )
                cursor.execute(
                    """
                    SELECT transaction_id, transaction_date, hostname, raw_landing_page
                    FROM seo_ga4_transactions
                    WHERE workspace_key=%s AND ga4_property_id=%s
                    """,
                    (WORKSPACE_KEY, ga4_property),
                )
                transaction_updates = []
                for row in cursor.fetchall() or []:
                    hostname = str(row.get("hostname") or primary_host)
                    landing = str(row.get("raw_landing_page") or "")
                    raw_url = f"https://{hostname}/{landing.lstrip('/')}" if hostname else landing
                    normalized = normalize_seo_url(
                        raw_url,
                        primary_host=primary_host,
                        known_locale_prefixes=known_locales,
                    )
                    mapping = map_alias_to_pages(normalized, pages)
                    transaction_updates.append(
                        (
                            normalized.get("normalized_url", ""), mapping.get("page_key"),
                            mapping["status"], WORKSPACE_KEY, ga4_property,
                            row.get("transaction_id"),
                            row.get("transaction_date"),
                        )
                    )
                if transaction_updates:
                    cursor.executemany(
                        """
                        UPDATE seo_ga4_transactions
                        SET normalized_url=%s, canonical_page_key=%s,
                            mapping_status=%s, updated_at=now()
                        WHERE workspace_key=%s AND ga4_property_id=%s
                          AND transaction_id=%s AND transaction_date=%s
                        """,
                        transaction_updates,
                    )
                cursor.execute(
                    """
                    UPDATE seo_google_connections
                    SET phase4_last_mapping_at=now(), phase4_error_code='',
                        phase4_error_summary='', updated_at=now()
                    WHERE workspace_key=%s
                    """,
                    (WORKSPACE_KEY,),
                )
            connection.commit()
        matched = sum(1 for row in alias_rows if row[12] == "matched")
        return {"received": len(alias_rows), "written": len(alias_rows), "matched": matched}

    @staticmethod
    def _alias_row(source, property_identifier, raw_url, normalized, mapping):
        return (
            stable_alias_key(source, raw_url, property_identifier), WORKSPACE_KEY,
            source, property_identifier, raw_url,
            normalized.get("normalized_url", ""), normalized.get("normalized_host", ""),
            normalized.get("normalized_path", ""), normalized.get("query_string", ""),
            normalized.get("locale_prefix", ""), normalized.get("market_code", ""),
            mapping.get("page_key"), mapping["status"], mapping.get("reason", ""),
            json.dumps(mapping.get("candidates") or []),
        )

    def reconcile_revenue(self):
        selected_property = str(self.connection_record().get("ga4_property_id") or "")
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT * FROM seo_ga4_transactions
                    WHERE workspace_key=%s AND ga4_property_id=%s AND is_complete=TRUE
                    """,
                    (WORKSPACE_KEY, selected_property),
                )
                transactions = [dict(row) for row in cursor.fetchall() or []]
                cursor.execute(
                    """
                    SELECT key.match_key, fact.*
                    FROM seo_shopify_order_match_keys AS key
                    JOIN seo_shopify_order_facts AS fact
                      ON fact.workspace_key=key.workspace_key
                     AND fact.shopify_order_id=key.shopify_order_id
                    WHERE key.workspace_key=%s
                    """,
                    (WORKSPACE_KEY,),
                )
                orders_by_key = {}
                for row in cursor.fetchall() or []:
                    orders_by_key.setdefault(str(row.get("match_key") or ""), []).append(dict(row))
                results = []
                transaction_counts = {}
                for transaction in transactions:
                    key = (
                        transaction.get("ga4_property_id"),
                        str(transaction.get("transaction_id") or ""),
                    )
                    transaction_counts[key] = transaction_counts.get(key, 0) + 1
                for transaction in transactions:
                    key = (
                        transaction.get("ga4_property_id"),
                        str(transaction.get("transaction_id") or ""),
                    )
                    if transaction_counts.get(key, 0) > 1:
                        transaction = {**transaction, "conflict_state": "duplicate_across_dates"}
                    candidates = []
                    for match_key in transaction_match_keys(transaction.get("transaction_id")):
                        candidates.extend(orders_by_key.get(match_key, []))
                    result = reconcile_transaction(transaction, candidates)
                    results.append((transaction, result))
                if results:
                    cursor.executemany(
                        """
                        INSERT INTO seo_revenue_reconciliations(
                            workspace_key, ga4_property_id, transaction_id,
                            transaction_date, shopify_order_id, reconciliation_state,
                            ga4_attributed_revenue, shopify_confirmed_revenue, currency
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (workspace_key, ga4_property_id, transaction_id, transaction_date) DO UPDATE SET
                            shopify_order_id=EXCLUDED.shopify_order_id,
                            reconciliation_state=EXCLUDED.reconciliation_state,
                            ga4_attributed_revenue=EXCLUDED.ga4_attributed_revenue,
                            shopify_confirmed_revenue=EXCLUDED.shopify_confirmed_revenue,
                            currency=EXCLUDED.currency, reconciled_at=now(), updated_at=now()
                        """,
                        [
                            (
                                WORKSPACE_KEY, transaction.get("ga4_property_id"),
                                transaction.get("transaction_id"), transaction.get("transaction_date"),
                                result.get("shopify_order_id"),
                                result["state"], result["ga4_attributed_revenue"],
                                result["shopify_confirmed_revenue"], result.get("currency", ""),
                            )
                            for transaction, result in results
                        ],
                    )
                cursor.execute(
                    """
                    UPDATE seo_google_connections
                    SET phase4_last_reconciliation_at=now(), phase4_error_code='',
                        phase4_error_summary='', updated_at=now()
                    WHERE workspace_key=%s
                    """,
                    (WORKSPACE_KEY,),
                )
            connection.commit()
        unmatched = sum(1 for _transaction, result in results if result["state"] != "confirmed_shopify_match")
        return {"received": len(transactions), "written": len(results), "unmatched": unmatched}

    def refresh_health(self):
        self.ensure_schema()
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT gsc_site_url, ga4_property_id, phase4_last_mapping_at,
                           phase4_last_reconciliation_at, phase4_error_summary
                    FROM seo_google_connections WHERE workspace_key=%s
                    """,
                    (WORKSPACE_KEY,),
                )
                saved = dict(cursor.fetchone() or {})
                cursor.execute(
                    """
                    SELECT
                        (SELECT MAX(date) FROM seo_gsc_daily_totals
                         WHERE workspace_key=%s AND gsc_site_url=%s
                           AND is_complete=TRUE AND is_final=TRUE) AS latest_gsc_date,
                        (SELECT MAX(date) FROM seo_ga4_daily_landing_pages
                         WHERE workspace_key=%s AND ga4_property_id=%s
                           AND is_complete=TRUE) AS latest_ga4_date,
                        (SELECT latest_completed_date FROM seo_phase4_source_state
                         WHERE workspace_key=%s AND source='shopify_orders'
                           AND resource_type='') AS latest_shopify_date
                    """,
                    (
                        WORKSPACE_KEY, str(saved.get("gsc_site_url") or ""),
                        WORKSPACE_KEY, str(saved.get("ga4_property_id") or ""),
                        WORKSPACE_KEY,
                    ),
                )
                completed_dates = dict(cursor.fetchone() or {})
                cursor.execute(
                    """
                    SELECT
                        COUNT(*) FILTER (WHERE mapping_status='unmapped') AS unmapped_count,
                        COUNT(*) FILTER (WHERE mapping_status='ambiguous') AS ambiguous_count
                    FROM seo_url_aliases
                    WHERE workspace_key=%s AND (
                        (source='GSC' AND property_identifier=%s) OR
                        (source='GA4' AND property_identifier=%s)
                    )
                    """,
                    (
                        WORKSPACE_KEY, str(saved.get("gsc_site_url") or ""),
                        str(saved.get("ga4_property_id") or ""),
                    ),
                )
                mapping = dict(cursor.fetchone() or {})
                cursor.execute(
                    """
                    SELECT COUNT(*) AS unmatched_count
                    FROM seo_revenue_reconciliations
                    WHERE workspace_key=%s AND ga4_property_id=%s
                      AND reconciliation_state<>'confirmed_shopify_match'
                    """,
                    (WORKSPACE_KEY, str(saved.get("ga4_property_id") or "")),
                )
                unmatched = _integer((cursor.fetchone() or {}).get("unmatched_count"))
                dates = [
                    _as_date(completed_dates.get("latest_gsc_date")),
                    _as_date(completed_dates.get("latest_ga4_date")),
                    _as_date(completed_dates.get("latest_shopify_date")),
                ]
                common = min(dates) if all(dates) else None
                cursor.execute(
                    """
                    SELECT COUNT(*) FILTER (WHERE status IN ('failed', 'partial')) AS failed,
                           COUNT(*) FILTER (WHERE status IN ('queued', 'running')) AS active
                    FROM seo_phase4_runs WHERE workspace_key=%s
                    """,
                    (WORKSPACE_KEY,),
                )
                run_state = dict(cursor.fetchone() or {})
                if _integer(run_state.get("failed")):
                    data_status = "failed_or_partial"
                elif _integer(run_state.get("active")) or not common:
                    data_status = "partial"
                elif common < utc_now().date() - timedelta(days=3):
                    data_status = "stale"
                else:
                    data_status = "ready"
                cursor.execute(
                    """
                    INSERT INTO seo_phase4_health(
                        workspace_key, latest_gsc_date, latest_ga4_date,
                        latest_shopify_date, common_reporting_date, last_mapping_at,
                        last_reconciliation_at, unmapped_page_count,
                        unmatched_transaction_count, ambiguous_page_count,
                        data_status, error_summary
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (workspace_key) DO UPDATE SET
                        latest_gsc_date=EXCLUDED.latest_gsc_date,
                        latest_ga4_date=EXCLUDED.latest_ga4_date,
                        latest_shopify_date=EXCLUDED.latest_shopify_date,
                        common_reporting_date=EXCLUDED.common_reporting_date,
                        last_mapping_at=EXCLUDED.last_mapping_at,
                        last_reconciliation_at=EXCLUDED.last_reconciliation_at,
                        unmapped_page_count=EXCLUDED.unmapped_page_count,
                        unmatched_transaction_count=EXCLUDED.unmatched_transaction_count,
                        ambiguous_page_count=EXCLUDED.ambiguous_page_count,
                        data_status=EXCLUDED.data_status,
                        error_summary=EXCLUDED.error_summary, updated_at=now()
                    RETURNING *
                    """,
                    (
                        WORKSPACE_KEY, dates[0], dates[1], dates[2], common,
                        saved.get("phase4_last_mapping_at"), saved.get("phase4_last_reconciliation_at"),
                        _integer(mapping.get("unmapped_count")), unmatched,
                        _integer(mapping.get("ambiguous_count")), data_status,
                        str(saved.get("phase4_error_summary") or "")[:300],
                    ),
                )
                result = dict(cursor.fetchone() or {})
            connection.commit()
        return self._clean_health(result)

    def saved_health(self):
        self.ensure_schema()
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM seo_phase4_health WHERE workspace_key=%s", (WORKSPACE_KEY,))
                return self._clean_health(dict(cursor.fetchone() or {}))

    @staticmethod
    def _clean_health(row):
        row = dict(row or {})
        for field in (
            "latest_gsc_date", "latest_ga4_date", "latest_shopify_date",
            "common_reporting_date", "last_mapping_at", "last_reconciliation_at", "updated_at",
        ):
            row[field] = _iso(row.get(field))
        for field in ("unmapped_page_count", "unmatched_transaction_count", "ambiguous_page_count"):
            row[field] = _integer(row.get(field))
        return row

    def recent_status(self):
        self.ensure_schema()
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT DISTINCT ON (source) * FROM seo_phase4_runs
                    WHERE workspace_key=%s ORDER BY source, created_at DESC
                    """,
                    (WORKSPACE_KEY,),
                )
                return {str(row.get("source") or ""): _clean_run(row) for row in cursor.fetchall() or []}


_DEFAULT_PHASE4_STORE = None


def default_phase4_store():
    global _DEFAULT_PHASE4_STORE
    if _DEFAULT_PHASE4_STORE is None:
        _DEFAULT_PHASE4_STORE = PostgresSEOPhase4Store()
    return _DEFAULT_PHASE4_STORE


def queue_phase4_pipeline(user, mode, *, phase4_store=None, connection_store=None):
    google_seo.require_admin(user)
    store = phase4_store or default_phase4_store()
    connection_store = connection_store or google_seo.default_store()
    saved = connection_store.get_connection_secret()
    if not saved.get("encrypted_refresh_token"):
        raise SEOPhase4Error(
            "Connect Google before importing joined SEO data.",
            code="google_connection_required",
            retryable=False,
        )
    if not saved.get("gsc_site_url") or not saved.get("ga4_property_id"):
        raise SEOPhase4Error(
            "Select both Google properties before importing joined SEO data.",
            code="property_selection_required",
            retryable=False,
        )
    health = store.phase3_health()
    if health.get("GSC", {}).get("duplicate_active") or health.get("GA4", {}).get("duplicate_active"):
        raise SEOPhase4Error(
            "Resolve the duplicate Google import job before starting Phase 4.",
            code="phase3_duplicate_job",
            retryable=False,
        )
    if health.get("GSC", {}).get("stalled_reclaimable") or health.get("GA4", {}).get("stalled_reclaimable"):
        raise SEOPhase4Error(
            "Resume the interrupted Google history worker from its saved checkpoint before starting Phase 4.",
            code="phase3_worker_stalled",
            retryable=False,
        )
    if not health.get("GSC", {}).get("latest_stored_date"):
        raise SEOPhase4Error(
            "Complete the Search Console import before starting Phase 4.",
            code="gsc_history_required",
            retryable=False,
        )
    requested_by = str(user.get("id") or "")[:200]
    runs = [store.queue_run(source, mode, requested_by=requested_by) for source in PHASE4_SOURCES]
    record_activity_log(
        "seo_phase4_queued",
        "SEO / Overview",
        f"SEO Phase 4 {mode} pipeline queued",
        entity_type="seo_phase4_run",
        entity_id=",".join(str(run.get("id") or "") for run in runs),
        metadata={"mode": mode, "sources": list(PHASE4_SOURCES)},
        actor=str(user.get("display_name") or user.get("id") or "sports_cave_os")[:200],
    )
    return runs


def queue_daily_pipeline(*, phase4_store=None, connection_store=None, requested_by="render-cron"):
    store = phase4_store or default_phase4_store()
    connection_store = connection_store or google_seo.default_store()
    saved = connection_store.get_connection_secret()
    if not saved.get("encrypted_refresh_token") or not saved.get("ga4_property_id"):
        raise SEOPhase4Error(
            "Google must remain connected with a selected GA4 property.",
            code="google_connection_required",
            retryable=False,
        )
    return [
        store.queue_run(source, "daily", requested_by=requested_by)
        for source in PHASE4_SOURCES
    ]


class PostgresSEOReportingReader:
    """Database-only Phase 4 read model; it never constructs external clients."""

    def __init__(self, phase4_store=None):
        self.store = phase4_store or default_phase4_store()

    @staticmethod
    def _detail_filters(filters, brand_terms, *, date_start, date_end, date_column="date"):
        clauses = [f"{date_column} BETWEEN %s AND %s", "is_complete=TRUE"]
        params = [date_start, date_end]
        countries = sorted(filters.country_values())
        devices = sorted(str(value).upper() for value in filters.device_values())
        if countries:
            clauses.append("UPPER(country_code)=ANY(%s)")
            params.append(countries)
        if devices:
            clauses.append("UPPER(device)=ANY(%s)")
            params.append(devices)
        term_clauses = []
        if filters.search in {"Brand", "Non-brand"}:
            for term in brand_terms:
                term_clauses.append("LOWER(query) LIKE %s")
                params.append(f"%{str(term).casefold()}%")
        if term_clauses:
            group = "(" + " OR ".join(term_clauses) + ")"
            clauses.append(group if filters.search == "Brand" else f"NOT {group}")
        elif filters.search == "Brand" and not term_clauses:
            clauses.append("FALSE")
        return clauses, params

    @staticmethod
    def _ga4_filters(filters, *, date_start, date_end, alias=""):
        prefix = f"{alias}." if alias else ""
        clauses = [f"{prefix}date BETWEEN %s AND %s", f"{prefix}is_complete=TRUE"]
        params = [date_start, date_end]
        countries = sorted(filters.country_values())
        devices = sorted(str(value).upper() for value in filters.device_values())
        if countries:
            clauses.append(f"UPPER({prefix}country_id)=ANY(%s)")
            params.append(countries)
        if devices:
            clauses.append(f"UPPER({prefix}device_category)=ANY(%s)")
            params.append(devices)
        return clauses, params

    def snapshot(self, *, preset="Last 28 days", market="All markets", device="All devices", search="All searches", custom_start=None, custom_end=None):
        health = self.store.saved_health()
        through = _as_date(health.get("common_reporting_date"))
        if not through:
            return {"ready": False, "health": health, "reason": "common_reporting_date_unavailable"}
        period = reporting_period(
            preset, through_date=through,
            custom_start=custom_start, custom_end=custom_end,
        )
        filters = ReportingFilters(period, market=market, device=device, search=search)
        settings = self.store.get_settings()
        current = self._period_metrics(filters, settings.get("brand_terms") or [], period.start_date, period.end_date)
        previous = self._period_metrics(
            filters, settings.get("brand_terms") or [],
            period.previous_start_date, period.previous_end_date,
        )
        search_scoped = filters.search in {"Brand", "Non-brand"}
        return {
            "ready": True,
            "health": health,
            "filters": {
                "preset": preset, "market": market, "device": device, "search": search,
                "start_date": period.start_date.isoformat(), "end_date": period.end_date.isoformat(),
                "previous_start_date": period.previous_start_date.isoformat(),
                "previous_end_date": period.previous_end_date.isoformat(),
            },
            "current": current,
            "previous": previous,
            "top_pages": self._top_pages(filters, period.start_date, period.end_date),
            "top_queries": self._top_queries(filters, settings.get("brand_terms") or [], period.start_date, period.end_date),
        }

    def _period_metrics(self, filters, brand_terms, start_date, end_date):
        connection_record = self.store.connection_record()
        gsc_site_url = str(connection_record.get("gsc_site_url") or "")
        ga4_property_id = str(connection_record.get("ga4_property_id") or "")
        with self.store._backend().connect() as connection:
            with connection.cursor() as cursor:
                if filters.market == "All markets" and filters.device == "All devices" and filters.search == "All searches":
                    cursor.execute(
                        """
                        SELECT COALESCE(SUM(clicks), 0) AS clicks,
                               COALESCE(SUM(impressions), 0) AS impressions,
                               CASE WHEN SUM(impressions)>0 THEN SUM(clicks)/SUM(impressions) ELSE 0 END AS ctr,
                               CASE WHEN SUM(impressions)>0
                                    THEN SUM(average_position*impressions)/SUM(impressions) ELSE 0 END AS average_position
                        FROM seo_gsc_daily_totals
                        WHERE workspace_key=%s AND gsc_site_url=%s
                          AND date BETWEEN %s AND %s AND is_complete=TRUE AND is_final=TRUE
                        """,
                        (WORKSPACE_KEY, gsc_site_url, start_date, end_date),
                    )
                else:
                    clauses, params = self._detail_filters(
                        filters, brand_terms, date_start=start_date, date_end=end_date,
                    )
                    cursor.execute(
                        f"""
                        SELECT COALESCE(SUM(clicks), 0) AS clicks,
                               COALESCE(SUM(impressions), 0) AS impressions,
                               CASE WHEN SUM(impressions)>0 THEN SUM(clicks)/SUM(impressions) ELSE 0 END AS ctr,
                               CASE WHEN SUM(impressions)>0
                                    THEN SUM(average_position*impressions)/SUM(impressions) ELSE 0 END AS average_position
                        FROM seo_gsc_daily_details
                        WHERE workspace_key=%s AND gsc_site_url=%s AND {' AND '.join(clauses)}
                        """,
                        [WORKSPACE_KEY, gsc_site_url, *params],
                    )
                gsc = dict(cursor.fetchone() or {})

                ga4_clauses, ga4_params = self._ga4_filters(
                    filters, date_start=start_date, date_end=end_date,
                )
                cursor.execute(
                    f"""
                    SELECT COALESCE(SUM(sessions), 0) AS organic_sessions,
                           COALESCE(SUM(transactions), 0) AS ga4_attributed_purchases,
                           COALESCE(SUM(purchase_revenue), 0) AS ga4_attributed_revenue,
                           ARRAY_REMOVE(ARRAY_AGG(DISTINCT property_currency), '') AS ga4_currencies
                    FROM seo_ga4_daily_landing_pages
                    WHERE workspace_key=%s AND ga4_property_id=%s
                      AND {' AND '.join(ga4_clauses)}
                    """,
                    [WORKSPACE_KEY, ga4_property_id, *ga4_params],
                )
                ga4 = dict(cursor.fetchone() or {})

                transaction_clauses = [
                    "tx.transaction_date BETWEEN %s AND %s", "tx.is_complete=TRUE",
                ]
                transaction_params = [start_date, end_date]
                countries = sorted(filters.country_values())
                devices = sorted(str(value).upper() for value in filters.device_values())
                if countries:
                    transaction_clauses.append("UPPER(tx.country_id)=ANY(%s)")
                    transaction_params.append(countries)
                if devices:
                    transaction_clauses.append("UPPER(tx.device_category)=ANY(%s)")
                    transaction_params.append(devices)
                cursor.execute(
                    f"""
                    SELECT reconciliation.currency,
                           COUNT(*) FILTER (
                               WHERE reconciliation.reconciliation_state='confirmed_shopify_match'
                           ) AS confirmed_orders,
                           COALESCE(SUM(reconciliation.shopify_confirmed_revenue) FILTER (
                               WHERE reconciliation.reconciliation_state='confirmed_shopify_match'
                           ), 0) AS confirmed_revenue,
                           COUNT(*) FILTER (
                               WHERE reconciliation.reconciliation_state<>'confirmed_shopify_match'
                           ) AS unmatched_or_disputed
                    FROM seo_revenue_reconciliations AS reconciliation
                    JOIN seo_ga4_transactions AS tx
                      ON tx.workspace_key=reconciliation.workspace_key
                     AND tx.ga4_property_id=reconciliation.ga4_property_id
                     AND tx.transaction_id=reconciliation.transaction_id
                     AND tx.transaction_date=reconciliation.transaction_date
                    WHERE reconciliation.workspace_key=%s
                      AND reconciliation.ga4_property_id=%s
                      AND {' AND '.join(transaction_clauses)}
                    GROUP BY reconciliation.currency
                    ORDER BY reconciliation.currency
                    """,
                    [WORKSPACE_KEY, ga4_property_id, *transaction_params],
                )
                currency_rows = [dict(row) for row in cursor.fetchall() or []]
        return {
            "organic_clicks": _decimal(gsc.get("clicks")),
            "organic_impressions": _decimal(gsc.get("impressions")),
            "ctr": _decimal(gsc.get("ctr")),
            "average_position": _decimal(gsc.get("average_position")),
            "organic_sessions": None if search_scoped else _decimal(ga4.get("organic_sessions")),
            "ga4_attributed_purchases": None if search_scoped else _decimal(ga4.get("ga4_attributed_purchases")),
            "ga4_attributed_revenue": None if search_scoped else _decimal(ga4.get("ga4_attributed_revenue")),
            "ga4_revenue_basis": "GA4 attributed/unconfirmed",
            "ga4_currencies": [] if search_scoped else list(ga4.get("ga4_currencies") or []),
            "shopify_confirmed_by_currency": [] if search_scoped else currency_rows,
            "search_scope_note": (
                "Brand classification applies to GSC query metrics only; GA4 and Shopify are not query-grain datasets."
                if search_scoped else ""
            ),
        }

    def _top_pages(self, filters, start_date, end_date, limit=25):
        gsc_countries = sorted(filters.country_values())
        devices = sorted(str(value).upper() for value in filters.device_values())
        gsc_extra = []
        ga4_extra = []
        gsc_params = [WORKSPACE_KEY, start_date, end_date]
        ga4_params = [WORKSPACE_KEY, start_date, end_date]
        if gsc_countries:
            gsc_extra.append("UPPER(country_code)=ANY(%s)")
            ga4_extra.append("UPPER(country_id)=ANY(%s)")
            gsc_params.append(gsc_countries)
            ga4_params.append(gsc_countries)
        if devices:
            gsc_extra.append("UPPER(device)=ANY(%s)")
            ga4_extra.append("UPPER(device_category)=ANY(%s)")
            gsc_params.append(devices)
            ga4_params.append(devices)
        gsc_where = "" if not gsc_extra else " AND " + " AND ".join(gsc_extra)
        ga4_where = "" if not ga4_extra else " AND " + " AND ".join(ga4_extra)
        if filters.search in {"Brand", "Non-brand"}:
            ga4_where += " AND FALSE"
        with self.store._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    WITH gsc AS (
                        SELECT canonical_page_key, SUM(clicks) AS clicks, SUM(impressions) AS impressions,
                               CASE WHEN SUM(impressions)>0
                                    THEN SUM(average_position*impressions)/SUM(impressions) ELSE 0 END AS average_position
                        FROM seo_gsc_daily_details
                        WHERE workspace_key=%s AND date BETWEEN %s AND %s
                          AND is_complete=TRUE AND canonical_page_key IS NOT NULL{gsc_where}
                        GROUP BY canonical_page_key
                    ), ga4 AS (
                        SELECT canonical_page_key, SUM(sessions) AS sessions,
                               SUM(transactions) AS attributed_purchases,
                               SUM(purchase_revenue) AS attributed_revenue
                        FROM seo_ga4_daily_landing_pages
                        WHERE workspace_key=%s AND date BETWEEN %s AND %s
                          AND is_complete=TRUE AND canonical_page_key IS NOT NULL{ga4_where}
                        GROUP BY canonical_page_key
                    )
                    SELECT page.page_key, page.canonical_url, page.title, page.page_type,
                           COALESCE(gsc.clicks, 0) AS clicks,
                           COALESCE(gsc.impressions, 0) AS impressions,
                           COALESCE(gsc.average_position, 0) AS average_position,
                           COALESCE(ga4.sessions, 0) AS sessions,
                           COALESCE(ga4.attributed_purchases, 0) AS attributed_purchases,
                           COALESCE(ga4.attributed_revenue, 0) AS attributed_revenue
                    FROM gsc FULL OUTER JOIN ga4 USING (canonical_page_key)
                    JOIN seo_canonical_pages AS page
                      ON page.page_key=COALESCE(gsc.canonical_page_key, ga4.canonical_page_key)
                    ORDER BY COALESCE(gsc.clicks, 0) DESC, COALESCE(ga4.sessions, 0) DESC
                    LIMIT %s
                    """,
                    [*gsc_params, *ga4_params, int(limit)],
                )
                return [dict(row) for row in cursor.fetchall() or []]

    def _top_queries(self, filters, brand_terms, start_date, end_date, limit=25):
        clauses, params = self._detail_filters(
            filters, brand_terms, date_start=start_date, date_end=end_date,
        )
        with self.store._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT query, SUM(clicks) AS clicks, SUM(impressions) AS impressions,
                           CASE WHEN SUM(impressions)>0 THEN SUM(clicks)/SUM(impressions) ELSE 0 END AS ctr,
                           CASE WHEN SUM(impressions)>0
                                THEN SUM(average_position*impressions)/SUM(impressions) ELSE 0 END AS average_position
                    FROM seo_gsc_daily_details
                    WHERE workspace_key=%s AND {' AND '.join(clauses)}
                    GROUP BY query ORDER BY clicks DESC, impressions DESC LIMIT %s
                    """,
                    [WORKSPACE_KEY, *params, int(limit)],
                )
                return [dict(row) for row in cursor.fetchall() or []]


class SEOPhase4Worker:
    def __init__(
        self,
        *,
        phase4_store=None,
        connection_store=None,
        config_loader=google_seo.load_config,
        access_token_loader=google_seo.access_token_for_connection,
        google_client_factory=GoogleSEOReportingClient,
        shopify_client_factory=ShopifySEOClient,
        worker_id="",
    ):
        self.store = phase4_store or default_phase4_store()
        self.connection_store = connection_store or google_seo.default_store()
        self.config_loader = config_loader
        self.access_token_loader = access_token_loader
        self.google_client_factory = google_client_factory
        self.shopify_client_factory = shopify_client_factory
        self.worker_id = str(worker_id or f"seo-phase4-{secrets.token_hex(6)}")[:200]

    def run_once(self, *, source=""):
        run = self.store.claim_next_run(self.worker_id, source=source)
        if not run:
            return None
        try:
            result = self._process(run)
            self.store.refresh_health()
            return result
        except Exception as error:
            safe_error = self._safe_error(error)
            return self.store.fail_run(
                run["id"], self.worker_id, safe_error,
                partial=bool(run.get("checkpoint_date") or run.get("rows_written")),
            )

    @staticmethod
    def _safe_error(error):
        if isinstance(error, SEOPhase4Error):
            return error
        if isinstance(error, SEOImportError):
            return SEOPhase4Error(error.public_message, code=error.code, retryable=error.retryable)
        return SEOPhase4Error(
            "The Phase 4 background job could not be completed safely.",
            code="phase4_worker_failed",
        )

    def _process(self, run):
        source = str(run.get("source") or "")
        if source == "shopify_pages":
            return self._process_shopify_pages(run)
        if source == "shopify_orders":
            return self._process_shopify_orders(run)
        if source == "ga4_transactions":
            return self._process_ga4_transactions(run)
        if source == "mapping":
            result = self.store.map_saved_urls()
        elif source == "reconciliation":
            result = self.store.reconcile_revenue()
        else:
            raise SEOPhase4Error("The Phase 4 source is unsupported.", code="phase4_source_unsupported")
        self.store.checkpoint_run(
            run["id"], self.worker_id,
            received=result.get("received", 0), written=result.get("written", 0),
        )
        return self.store.complete_run(run["id"], self.worker_id)

    def _process_shopify_pages(self, run):
        client = self.shopify_client_factory()
        primary_host = client.primary_host()
        if not primary_host:
            raise SEOPhase4Error("Shopify did not return a primary store domain.", code="shopify_domain_unavailable")
        settings = self.store.get_settings()
        locales = settings.get("known_locale_prefixes") or []
        received = written = rejected = 0
        for page_type in ("product", "collection", "page", "article"):
            state = self.store.source_state("shopify_pages", page_type)
            updated_after = str(state.get("checkpoint_value") or "")
            batch = []
            latest_checkpoint = updated_after
            for resource in client.iter_resources(page_type, updated_after=updated_after):
                received += 1
                try:
                    page = canonical_page_from_shopify(
                        resource,
                        primary_host=primary_host,
                        known_locale_prefixes=locales,
                    )
                except SEOPhase4Error:
                    rejected += 1
                    continue
                batch.append(page)
                if page_type == "article" and resource.get("blog_id") and resource.get("blog_handle"):
                    batch.append(
                        canonical_page_from_shopify(
                            {
                                "page_type": "blog",
                                "shopify_resource_id": resource["blog_id"],
                                "handle": resource["blog_handle"],
                                "title": resource.get("blog_title") or resource["blog_handle"],
                                "status": "ACTIVE",
                                "is_active": True,
                                "updated_at": resource.get("updated_at"),
                            },
                            primary_host=primary_host,
                            known_locale_prefixes=locales,
                        )
                    )
                latest_checkpoint = max(latest_checkpoint, str(resource.get("updated_at") or ""))
                if len(batch) >= 100:
                    written += self.store.upsert_canonical_pages(batch)
                    batch = []
                    self.store.renew_lease(run["id"], self.worker_id)
            if batch:
                written += self.store.upsert_canonical_pages(batch)
            self.store.save_source_state("shopify_pages", page_type, checkpoint_value=latest_checkpoint)
        self.store.checkpoint_run(
            run["id"], self.worker_id, received=received, written=written, rejected=rejected,
        )
        return self.store.complete_run(run["id"], self.worker_id, status="partial" if rejected else "completed")

    def _process_shopify_orders(self, run):
        client = self.shopify_client_factory()
        state = self.store.source_state("shopify_orders")
        updated_after = str(state.get("checkpoint_value") or "")
        batch = []
        latest_checkpoint = updated_after
        received = written = 0
        latest_order_date = None
        for order in client.iter_order_facts(updated_after=updated_after):
            received += 1
            batch.append(order)
            latest_checkpoint = max(latest_checkpoint, str(order.get("source_updated_at") or ""))
            order_date = _as_date(order.get("order_date"))
            latest_order_date = max(latest_order_date, order_date) if latest_order_date else order_date
            if len(batch) >= 100:
                written += self.store.upsert_shopify_order_facts(batch)
                batch = []
                self.store.renew_lease(run["id"], self.worker_id)
        if batch:
            written += self.store.upsert_shopify_order_facts(batch)
        self.store.save_source_state(
            "shopify_orders", checkpoint_value=latest_checkpoint,
            latest_completed_date=utc_now().date(),
        )
        self.store.checkpoint_run(run["id"], self.worker_id, received=received, written=written)
        return self.store.complete_run(run["id"], self.worker_id)

    def _process_ga4_transactions(self, run):
        config = self.config_loader()
        access_token, connection = self.access_token_loader(self.connection_store, config)
        property_id = str(connection.get("ga4_property_id") or "")
        if not property_id:
            raise SEOPhase4Error("Select a GA4 property before importing transactions.", code="ga4_property_required")
        earliest, latest = self.store.ga4_completed_bounds(property_id)
        if not earliest or not latest:
            return self.store.complete_run(run["id"], self.worker_id, status="partial")
        start = _as_date(run.get("requested_start_date")) or earliest
        end = _as_date(run.get("requested_end_date")) or latest
        if run.get("mode") in {"daily", "manual"}:
            start = max(earliest, latest - timedelta(days=6))
        checkpoint = _as_date(run.get("checkpoint_date"))
        if checkpoint:
            start = max(start, checkpoint + timedelta(days=1))
        if start > end:
            return self.store.complete_run(run["id"], self.worker_id)
        client = self.google_client_factory(access_token)
        currency = str(connection.get("ga4_property_currency") or "")
        dimensions = compatible_ga4_transaction_dimensions(client, property_id)
        for slice_date in date_sequence(start, end):
            if not self.store.renew_lease(run["id"], self.worker_id, active_slice_date=slice_date):
                raise SEOPhase4Error("The Phase 4 job lease was lost.", code="phase4_lease_lost")
            slice_data = fetch_ga4_transactions_date(
                client, property_id, slice_date, currency=currency, dimensions=dimensions,
            )
            result = self.store.replace_ga4_transactions_date(property_id, slice_data)
            self.store.checkpoint_run(
                run["id"], self.worker_id, checkpoint_date=slice_date,
                received=slice_data.get("rows_received", 0), written=result["inserted"],
            )
            run["checkpoint_date"] = slice_date
        self.store.save_source_state(
            "ga4_transactions", latest_completed_date=end,
            checkpoint_value=end.isoformat(),
        )
        return self.store.complete_run(run["id"], self.worker_id)


def _run_worker_loop(worker, *, once=False, poll_seconds=15, source=""):
    while True:
        result = worker.run_once(source=source)
        if once:
            return result
        if result is None:
            time.sleep(max(1, int(poll_seconds)))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Sports Cave SEO Phase 4 background jobs")
    subparsers = parser.add_subparsers(dest="command", required=True)
    worker_parser = subparsers.add_parser("worker")
    worker_parser.add_argument("--once", action="store_true")
    worker_parser.add_argument("--poll-seconds", type=int, default=15)
    worker_parser.add_argument("--source", choices=PHASE4_SOURCES, default="")
    subparsers.add_parser("daily")
    subparsers.add_parser("health")
    arguments = parser.parse_args(argv)
    if arguments.command == "health":
        store = default_phase4_store()
        print(json.dumps({"phase3": store.phase3_health(), "phase4": store.saved_health()}))
        return 0
    if arguments.command == "daily":
        runs = queue_daily_pipeline()
        print(json.dumps([{"id": run.get("id"), "source": run.get("source")} for run in runs]))
        return 0
    _run_worker_loop(
        SEOPhase4Worker(), once=arguments.once,
        poll_seconds=arguments.poll_seconds, source=arguments.source,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
