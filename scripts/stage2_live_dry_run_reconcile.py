#!/usr/bin/env python3
"""Read-only Stage 2 live reconciliation for Sports Cave OS.

This script is intended for Render Shell or a Render one-off job where the
live DATABASE_URL and Shopify Admin credentials are present. It only performs
Postgres SELECTs and Shopify Admin GraphQL queries.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import psycopg
import requests
from psycopg.rows import dict_row


REQUIRED_ENV_VARS = (
    "DATABASE_URL",
    "SHOPIFY_STORE_DOMAIN",
    "SHOPIFY_ADMIN_ACCESS_TOKEN",
    "SHOPIFY_API_VERSION",
)

REQUIRED_TABLES = (
    "edition_products",
    "edition_orders",
    "shopify_orders",
    "shopify_order_lines",
    "certificates",
    "app_sync_state",
    "audit_logs",
)

ORDER_METAFIELD_KEYS = (
    "edition_allocations",
    "certificates_json",
    "certificates",
    "certificate_status",
    "certificate_count",
)

PRODUCT_METAFIELD_KEYS = (
    "edition_enabled",
    "edition_total",
    "edition_next_number",
    "edition_sold_count",
    "edition_remaining",
    "edition_status",
    "edition_label",
)

FOCUS_PRODUCT_TITLES = (
    "GOAT Debate Wall Art",
    "Legends Never Die Messi vs Ronaldo Wall Art",
    "Greg Murphy Lap of the Gods Wall Art",
    "Peter Brock Tribute Wall Art",
    "Lionel Messi The Final Crown Wall Art",
)

SEQUENCE_CHECKS = {
    "GOAT Debate Wall Art": (50, 51, 94, 95),
    "Legends Never Die Messi vs Ronaldo Wall Art": tuple(range(32, 46)),
    "Greg Murphy Lap of the Gods Wall Art": tuple(range(1, 18)),
}

FORBIDDEN_ARGS = {
    "--apply",
    "apply",
    "--write",
    "write",
    "--sync",
    "sync",
    "--backfill",
    "backfill",
    "--repair",
    "repair",
}


ORDERS_QUERY = """
query Stage2DryRunOrders($first: Int!, $after: String, $query: String) {
  orders(first: $first, after: $after, query: $query, sortKey: UPDATED_AT, reverse: true) {
    pageInfo { hasNextPage endCursor }
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


PRODUCT_BY_ID_QUERY = """
query Stage2DryRunProductById($id: ID!) {
  node(id: $id) {
    ... on Product {
      id
      legacyResourceId
      title
      handle
      status
      metafields(first: 50, namespace: "sports_cave") {
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


PRODUCT_SEARCH_QUERY = """
query Stage2DryRunProductSearch($first: Int!, $query: String) {
  products(first: $first, query: $query) {
    nodes {
      id
      legacyResourceId
      title
      handle
      status
      metafields(first: 50, namespace: "sports_cave") {
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


def parse_args(argv: list[str]) -> argparse.Namespace:
    forbidden = [arg for arg in argv if arg.strip().lower() in FORBIDDEN_ARGS]
    if forbidden:
        print("Refusing to run: this Stage 2 tool is dry-run/read-only only.")
        print("Forbidden argument(s): " + ", ".join(forbidden))
        sys.exit(2)

    parser = argparse.ArgumentParser(
        description="Read-only Supabase + Shopify Stage 2 reconciliation dry-run."
    )
    parser.add_argument("--limit", type=int, default=250, help="Maximum Shopify orders to read.")
    parser.add_argument("--order-name", default="", help="Specific order name to include, e.g. SC2843.")
    parser.add_argument(
        "--product-title",
        action="append",
        default=[],
        help="Specific product title to inspect. Can be passed more than once.",
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help="Report output directory. Defaults to output/stage2_live_dry_run_YYYYMMDD_HHMM.",
    )
    return parser.parse_args(argv)


def missing_env_report() -> bool:
    missing = [key for key in REQUIRED_ENV_VARS if not os.getenv(key, "").strip()]
    if not missing:
        return False

    print("Stage 2 live dry-run cannot run because required env vars are missing.")
    print("Missing:")
    for key in missing:
        print(f"  - {key}")
    print("No Supabase connection was opened.")
    print("No Shopify request was made.")
    print("No report files were written.")
    return True


def normalize_store_domain(value: str) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    if "://" not in raw:
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    return (parsed.hostname or "").strip(".")


def safe_database_label(database_url: str) -> str:
    parsed = urlparse(database_url)
    host = parsed.hostname or "unknown-host"
    database = (parsed.path or "").strip("/") or "unknown-db"
    return f"{host}/{database}"


def ensure_output_dir(value: str) -> Path:
    if value:
        output_dir = Path(value)
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M")
        output_dir = Path("output") / f"stage2_live_dry_run_{stamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def connect_postgres_readonly(database_url: str):
    return psycopg.connect(
        database_url,
        autocommit=True,
        row_factory=dict_row,
        options="-c default_transaction_read_only=on",
    )


def read_supabase_table_counts(database_url: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    status = {
        "configured": True,
        "connected": False,
        "database": safe_database_label(database_url),
        "error": "",
    }
    rows: list[dict[str, Any]] = []
    try:
        with connect_postgres_readonly(database_url) as conn:
            status["connected"] = True
            with conn.cursor() as cur:
                for table in REQUIRED_TABLES:
                    cur.execute(
                        """
                        SELECT EXISTS (
                            SELECT 1
                            FROM information_schema.tables
                            WHERE table_schema = current_schema()
                              AND table_name = %s
                        ) AS exists
                        """,
                        (table,),
                    )
                    exists = bool(cur.fetchone()["exists"])
                    count: int | None = None
                    count_error = ""
                    if exists:
                        try:
                            cur.execute(f'SELECT COUNT(*) AS count FROM "{table}"')
                            count = int(cur.fetchone()["count"] or 0)
                        except Exception as error:  # pragma: no cover - live diagnostics only
                            count_error = str(error)
                    rows.append(
                        {
                            "table_name": table,
                            "exists": "yes" if exists else "no",
                            "row_count": "" if count is None else count,
                            "error": count_error,
                        }
                    )
    except Exception as error:
        status["error"] = str(error)
    return status, rows


def graphql_request(
    *,
    store_domain: str,
    api_version: str,
    access_token: str,
    query: str,
    variables: dict[str, Any],
) -> dict[str, Any]:
    if re.search(r"\bmutation\b", query, flags=re.IGNORECASE):
        raise RuntimeError("Refusing to run Shopify mutation in Stage 2 dry-run script.")

    url = f"https://{store_domain}/admin/api/{api_version}/graphql.json"
    response = requests.post(
        url,
        headers={
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": access_token,
        },
        json={"query": query, "variables": variables},
        timeout=30,
    )
    if response.status_code == 429:
        retry_after = int(response.headers.get("Retry-After") or "2")
        time.sleep(max(retry_after, 1))
        response = requests.post(
            url,
            headers={
                "Content-Type": "application/json",
                "X-Shopify-Access-Token": access_token,
            },
            json={"query": query, "variables": variables},
            timeout=30,
        )
    response.raise_for_status()
    payload = response.json()
    if payload.get("errors"):
        raise RuntimeError(json.dumps(payload["errors"], ensure_ascii=True))
    return payload.get("data") or {}


def order_search_query(order_name: str) -> str:
    raw = str(order_name or "").strip()
    if not raw:
        return ""
    normalized = raw if raw.startswith("#") else f"#{raw}"
    return f"name:{normalized}"


def fetch_shopify_orders(
    *,
    store_domain: str,
    api_version: str,
    access_token: str,
    limit: int,
    query: str = "",
) -> list[dict[str, Any]]:
    orders: list[dict[str, Any]] = []
    after = None
    remaining = max(int(limit or 0), 0)
    while remaining > 0:
        first = min(50, remaining)
        data = graphql_request(
            store_domain=store_domain,
            api_version=api_version,
            access_token=access_token,
            query=ORDERS_QUERY,
            variables={"first": first, "after": after, "query": query or None},
        )
        connection = data.get("orders") or {}
        nodes = connection.get("nodes") or []
        orders.extend(nodes)
        remaining -= len(nodes)
        page_info = connection.get("pageInfo") or {}
        if not nodes or not page_info.get("hasNextPage"):
            break
        after = page_info.get("endCursor")
    return orders


def dedupe_orders(orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for order in orders:
        order_id = order.get("id") or order.get("legacyResourceId") or order.get("name")
        if order_id in seen:
            continue
        seen.add(order_id)
        deduped.append(order)
    return deduped


def fetch_product_by_id(
    *,
    store_domain: str,
    api_version: str,
    access_token: str,
    product_id: str,
) -> dict[str, Any] | None:
    if not product_id:
        return None
    data = graphql_request(
        store_domain=store_domain,
        api_version=api_version,
        access_token=access_token,
        query=PRODUCT_BY_ID_QUERY,
        variables={"id": product_id},
    )
    node = data.get("node")
    return node if isinstance(node, dict) else None


def fetch_products_by_title(
    *,
    store_domain: str,
    api_version: str,
    access_token: str,
    title: str,
) -> list[dict[str, Any]]:
    title = str(title or "").strip()
    if not title:
        return []
    escaped_title = title.replace('"', '\\"')
    data = graphql_request(
        store_domain=store_domain,
        api_version=api_version,
        access_token=access_token,
        query=PRODUCT_SEARCH_QUERY,
        variables={"first": 10, "query": f'title:"{escaped_title}"'},
    )
    return (data.get("products") or {}).get("nodes") or []


def metafield_nodes(owner: dict[str, Any]) -> list[dict[str, Any]]:
    return ((owner.get("metafields") or {}).get("nodes") or [])


def metafields_by_key(owner: dict[str, Any] | list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    nodes = owner if isinstance(owner, list) else metafield_nodes(owner)
    return {
        str(item.get("key") or ""): item
        for item in nodes
        if item.get("namespace") == "sports_cave" and item.get("key")
    }


def parse_json_value(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value or "")
    except (TypeError, ValueError):
        return default


def parse_allocation_payload(value: Any) -> dict[str, Any]:
    payload = parse_json_value(value, {})
    if not isinstance(payload, dict):
        payload = {}
    line_items = payload.get("line_items")
    if isinstance(line_items, dict):
        payload["line_items"] = line_items
    elif isinstance(line_items, list):
        mapped: dict[str, Any] = {}
        for item in line_items:
            if not isinstance(item, dict):
                continue
            line_id = item.get("line_item_id") or item.get("shopify_line_item_id")
            if line_id:
                mapped[str(line_id)] = item
        payload["line_items"] = mapped
    else:
        payload["line_items"] = {}
    return payload


def parse_certificate_payload(value: Any) -> list[dict[str, Any]]:
    parsed = parse_json_value(value, [])
    if isinstance(parsed, dict):
        rows = parsed.get("certificates") if isinstance(parsed.get("certificates"), list) else []
    elif isinstance(parsed, list):
        rows = parsed
    else:
        rows = []
    return [dict(item) for item in rows if isinstance(item, dict)]


def normalize_gid_tail(value: Any) -> str:
    raw = str(value or "").strip()
    if "/" in raw:
        return raw.rsplit("/", 1)[-1]
    return raw


def line_item_lookup(order: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for index, line in enumerate(((order.get("lineItems") or {}).get("nodes") or []), start=1):
        line = dict(line or {})
        line["_position"] = index
        keys = {str(line.get("id") or ""), normalize_gid_tail(line.get("id"))}
        for key in keys:
            if key:
                lookup[key] = line
    return lookup


def customer_name(order: dict[str, Any]) -> str:
    customer = order.get("customer") or {}
    shipping = order.get("shippingAddress") or {}
    billing = order.get("billingAddress") or {}
    return (
        customer.get("displayName")
        or " ".join(
            item
            for item in (customer.get("firstName"), customer.get("lastName"))
            if item
        ).strip()
        or shipping.get("name")
        or billing.get("name")
        or ""
    )


def customer_email(order: dict[str, Any]) -> str:
    customer = order.get("customer") or {}
    return order.get("email") or customer.get("email") or ""


def positive_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def allocation_numbers(allocation: dict[str, Any], quantity: int) -> list[int | None]:
    numbers: list[int | None] = []
    raw_numbers = allocation.get("edition_numbers")
    if isinstance(raw_numbers, list):
        numbers = [positive_int(item) for item in raw_numbers]

    unit_allocations = allocation.get("unit_allocations")
    if isinstance(unit_allocations, list):
        for unit in unit_allocations:
            if not isinstance(unit, dict):
                continue
            unit_index = positive_int(unit.get("unit_index")) or (len(numbers) + 1)
            while len(numbers) < unit_index:
                numbers.append(None)
            numbers[unit_index - 1] = positive_int(unit.get("edition_number"))

    if not numbers:
        single = positive_int(allocation.get("edition_number"))
        if single:
            numbers = [single]

    target_length = max(quantity, len(numbers), 1)
    while len(numbers) < target_length:
        numbers.append(None)
    return numbers


def product_key(product_handle: str, product_title: str, product_id: str) -> str:
    return (
        str(product_handle or "").strip().lower()
        or str(product_title or "").strip().lower()
        or str(product_id or "").strip().lower()
    )


def recover_allocations(orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for order in orders:
        order_metafields = metafields_by_key(order)
        allocation_mf = order_metafields.get("edition_allocations")
        if not allocation_mf:
            continue
        payload = parse_allocation_payload(allocation_mf.get("value"))
        lookup = line_item_lookup(order)
        for line_id, allocation_raw in (payload.get("line_items") or {}).items():
            allocation = allocation_raw if isinstance(allocation_raw, dict) else {}
            line = lookup.get(str(line_id)) or lookup.get(normalize_gid_tail(line_id)) or {}
            product = line.get("product") or {}
            quantity = positive_int(line.get("quantity")) or positive_int(allocation.get("quantity")) or 1
            numbers = allocation_numbers(allocation, quantity)
            product_title = (
                allocation.get("product_title")
                or allocation.get("product")
                or product.get("title")
                or line.get("title")
                or ""
            )
            product_handle = allocation.get("product_handle") or allocation.get("handle") or product.get("handle") or ""
            product_id = allocation.get("product_id") or allocation.get("shopify_product_id") or product.get("id") or ""
            variant = line.get("variant") or {}
            for quantity_index, edition_number in enumerate(numbers, start=1):
                if not edition_number:
                    if quantity_index > quantity and any(numbers):
                        continue
                rows.append(
                    {
                        "source": "shopify_order_metafield",
                        "order_id": order.get("id") or "",
                        "order_legacy_id": order.get("legacyResourceId") or "",
                        "order_name": order.get("name") or "",
                        "order_created_at": order.get("createdAt") or "",
                        "order_processed_at": order.get("processedAt") or "",
                        "customer_name": customer_name(order),
                        "customer_email": customer_email(order),
                        "line_item_id": str(line_id),
                        "line_item_shopify_id": line.get("id") or "",
                        "line_item_position": line.get("_position") or "",
                        "line_item_title": line.get("title") or "",
                        "variant_id": variant.get("id") or "",
                        "variant_title": line.get("variantTitle") or variant.get("title") or "",
                        "sku": line.get("sku") or variant.get("sku") or "",
                        "quantity": quantity,
                        "quantity_index": quantity_index,
                        "product_id": product_id,
                        "product_handle": product_handle,
                        "product_title": product_title,
                        "product_key": product_key(product_handle, product_title, product_id),
                        "edition_number": edition_number or "",
                        "edition_total": allocation.get("edition_total") or "",
                        "edition_display": allocation.get("edition_display") or "",
                        "status": allocation.get("status") or "",
                        "allocation_payload": json.dumps(allocation, ensure_ascii=True, separators=(",", ":")),
                    }
                )
    return rows


def recover_certificates(orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for order in orders:
        order_metafields = metafields_by_key(order)
        certificate_sources = [
            ("certificates_json", order_metafields.get("certificates_json")),
            ("certificates", order_metafields.get("certificates")),
        ]
        status = (order_metafields.get("certificate_status") or {}).get("value") or ""
        count = (order_metafields.get("certificate_count") or {}).get("value") or ""
        for source_key, metafield in certificate_sources:
            if not metafield:
                continue
            for index, cert in enumerate(parse_certificate_payload(metafield.get("value")), start=1):
                rows.append(
                    {
                        "source": f"shopify_order_metafield:{source_key}",
                        "order_id": order.get("id") or "",
                        "order_legacy_id": order.get("legacyResourceId") or "",
                        "order_name": order.get("name") or "",
                        "customer_name": customer_name(order),
                        "customer_email": customer_email(order),
                        "certificate_index": index,
                        "certificate_status_metafield": status,
                        "certificate_count_metafield": count,
                        "shopify_line_item_id": cert.get("shopify_line_item_id") or cert.get("line_item_id") or "",
                        "product_handle": cert.get("product_handle") or cert.get("handle") or "",
                        "product_title": cert.get("product_title") or cert.get("product") or "",
                        "edition_number": cert.get("edition_number") or "",
                        "edition_total": cert.get("edition_total") or "",
                        "certificate_status": cert.get("certificate_status") or cert.get("status") or "",
                        "certificate_file_url": (
                            cert.get("certificate_file_url")
                            or cert.get("certificate_pdf_url")
                            or cert.get("pdf_url")
                            or ""
                        ),
                        "certificate_payload": json.dumps(cert, ensure_ascii=True, separators=(",", ":")),
                    }
                )
    return rows


def extract_metafield_presence(orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for order in orders:
        by_key = metafields_by_key(order)
        row = {
            "order_id": order.get("id") or "",
            "order_legacy_id": order.get("legacyResourceId") or "",
            "order_name": order.get("name") or "",
            "created_at": order.get("createdAt") or "",
            "processed_at": order.get("processedAt") or "",
            "customer_name": customer_name(order),
            "customer_email": customer_email(order),
        }
        for key in ORDER_METAFIELD_KEYS:
            metafield = by_key.get(key) or {}
            row[f"{key}_present"] = "yes" if metafield else "no"
            row[f"{key}_type"] = metafield.get("type") or ""
            row[f"{key}_value"] = metafield.get("value") or ""
        rows.append(row)
    return rows


def product_metafield_summary(products: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for product in sorted(products, key=lambda item: (item.get("title") or "", item.get("id") or "")):
        by_key = metafields_by_key(product)
        fields = [
            f"{key}={(by_key.get(key) or {}).get('value', '')}"
            for key in PRODUCT_METAFIELD_KEYS
            if by_key.get(key)
        ]
        lines.append(
            f"- {product.get('title') or 'Untitled'} "
            f"({product.get('handle') or product.get('id') or 'no handle'}): "
            + (", ".join(fields) if fields else "no sports_cave edition metafields found")
        )
    return lines


def classify_allocations(
    allocations: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    safe: list[dict[str, Any]] = []
    by_product_edition: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)

    for row in allocations:
        edition_number = positive_int(row.get("edition_number"))
        if edition_number:
            by_product_edition[(row.get("product_key") or "", edition_number)].append(row)

    duplicate_keys = {
        key: rows
        for key, rows in by_product_edition.items()
        if key[0] and len(rows) > 1
    }

    duplicate_row_ids = {
        (row.get("order_id"), row.get("line_item_id"), row.get("quantity_index"))
        for rows in duplicate_keys.values()
        for row in rows
    }

    for row in allocations:
        problems: list[str] = []
        if not row.get("order_id"):
            problems.append("missing_order_id")
        if not row.get("line_item_id"):
            problems.append("missing_line_item_id")
        if not row.get("product_key"):
            problems.append("missing_product")
        if not positive_int(row.get("edition_number")):
            problems.append("missing_edition_number")
        row_id = (row.get("order_id"), row.get("line_item_id"), row.get("quantity_index"))
        if row_id in duplicate_row_ids:
            problems.append("duplicate_product_edition_number")
        if problems:
            conflicts.append(
                {
                    **row,
                    "conflict_type": ";".join(sorted(set(problems))),
                    "review_note": "Needs manual review before import.",
                }
            )
        else:
            safe.append(row)

    found_by_title: dict[str, set[int]] = defaultdict(set)
    for row in allocations:
        number = positive_int(row.get("edition_number"))
        title = str(row.get("product_title") or "")
        if number:
            found_by_title[title].add(number)

    sequence_summary: dict[str, Any] = {}
    for title, expected_numbers in SEQUENCE_CHECKS.items():
        found = sorted(found_by_title.get(title, set()))
        expected = set(expected_numbers)
        sequence_summary[title] = {
            "expected": sorted(expected),
            "found_expected": [number for number in found if number in expected],
            "missing_expected": sorted(expected - set(found)),
            "all_found": found,
        }
        for missing in sorted(expected - set(found)):
            conflicts.append(
                {
                    "source": "sequence_check",
                    "order_id": "",
                    "order_name": "",
                    "line_item_id": "",
                    "product_title": title,
                    "product_handle": "",
                    "edition_number": missing,
                    "conflict_type": "sequence_number_not_found_in_fetched_shopify_order_metafields",
                    "review_note": "May be outside the fetched order window or absent from Shopify metafields.",
                }
            )

    return safe, conflicts, {"duplicates": duplicate_keys, "sequences": sequence_summary}


def goat_investigation_rows(allocations: list[dict[str, Any]], sequences: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in allocations:
        title = str(row.get("product_title") or "")
        if "goat debate" not in title.lower():
            continue
        number = positive_int(row.get("edition_number"))
        rows.append(
            {
                "order_name": row.get("order_name") or "",
                "customer_name": row.get("customer_name") or "",
                "line_item_id": row.get("line_item_id") or "",
                "product_title": title,
                "quantity_index": row.get("quantity_index") or "",
                "edition_number": number or "",
                "is_intended_manual_override_050_051": "yes" if number in (50, 51) else "no",
                "is_current_reported_094_095": "yes" if number in (94, 95) else "no",
                "source": row.get("source") or "",
            }
        )
    goat_sequence = sequences.get("GOAT Debate Wall Art") or {}
    for expected in (50, 51, 94, 95):
        if expected not in set(goat_sequence.get("all_found") or []):
            rows.append(
                {
                    "order_name": "",
                    "customer_name": "",
                    "line_item_id": "",
                    "product_title": "GOAT Debate Wall Art",
                    "quantity_index": "",
                    "edition_number": expected,
                    "is_intended_manual_override_050_051": "yes" if expected in (50, 51) else "no",
                    "is_current_reported_094_095": "yes" if expected in (94, 95) else "no",
                    "source": "not_found_in_fetched_shopify_order_metafields",
                }
            )
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]], preferred_fields: list[str] | None = None) -> None:
    fields: list[str] = []
    for field in preferred_fields or []:
        if field not in fields:
            fields.append(field)
    for row in rows:
        for field in row.keys():
            if field not in fields:
                fields.append(field)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields or ["empty"])
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def markdown_count_table(rows: list[dict[str, Any]]) -> str:
    lines = ["| Table | Exists | Rows | Error |", "|---|---:|---:|---|"]
    for row in rows:
        lines.append(
            f"| {row.get('table_name', '')} | {row.get('exists', '')} | "
            f"{row.get('row_count', '')} | {row.get('error', '')} |"
        )
    return "\n".join(lines)


def write_summary(
    *,
    path: Path,
    supabase_status: dict[str, Any],
    supabase_counts: list[dict[str, Any]],
    shopify_status: dict[str, Any],
    orders: list[dict[str, Any]],
    allocations: list[dict[str, Any]],
    certificates: list[dict[str, Any]],
    safe: list[dict[str, Any]],
    conflicts: list[dict[str, Any]],
    goat_rows: list[dict[str, Any]],
    product_lines: list[str],
    sequence_summary: dict[str, Any],
) -> None:
    orders_with_allocations = {
        row.get("order_id") for row in allocations if row.get("order_id")
    }
    orders_with_certificates = {
        row.get("order_id") for row in certificates if row.get("order_id")
    }
    recovered_count = len([row for row in allocations if positive_int(row.get("edition_number"))])
    allocation_status = (
        "Potentially complete for the 205 rows."
        if recovered_count >= 205
        else "Below 205 recovered edition rows from fetched Shopify order metafields."
    )
    goat_050_051 = [
        row for row in goat_rows if positive_int(row.get("edition_number")) in (50, 51) and row.get("source") != "not_found_in_fetched_shopify_order_metafields"
    ]
    goat_094_095 = [
        row for row in goat_rows if positive_int(row.get("edition_number")) in (94, 95) and row.get("source") != "not_found_in_fetched_shopify_order_metafields"
    ]

    lines = [
        "# Stage 2 Live Dry-Run Reconciliation",
        "",
        "Dry-run only. No Supabase writes, Shopify mutations, certificate generation, repairs, or syncs were attempted.",
        "",
        "## A. Supabase connection status",
        f"- Configured: {'yes' if supabase_status.get('configured') else 'no'}",
        f"- Connected read-only: {'yes' if supabase_status.get('connected') else 'no'}",
        f"- Database: {supabase_status.get('database') or ''}",
        f"- Error: {supabase_status.get('error') or 'none'}",
        "",
        "## B. Shopify connection status",
        f"- Store: {shopify_status.get('store_domain')}",
        f"- API version: {shopify_status.get('api_version')}",
        f"- Orders fetched: {len(orders)}",
        f"- Error: {shopify_status.get('error') or 'none'}",
        "",
        "## C. Supabase table counts",
        markdown_count_table(supabase_counts),
        "",
        "## D. Shopify order metafield recovery status",
        f"- Orders with `sports_cave.edition_allocations`: {len(orders_with_allocations)}",
        f"- Recovered edition allocation unit rows: {recovered_count}",
        f"- Recovery status versus 205 expected artwork rows: {allocation_status}",
        "",
        "## E. Orders/edition rows recovered by source",
        f"- Shopify order metafields: {len(allocations)} raw allocation rows, {recovered_count} with edition numbers",
        "- Local snapshot/session: not inspected by this live script; Stage 2B is intentionally Shopify/Supabase read-only.",
        "- Supabase ledger: see table counts above; expected pre-backfill counts may be zero.",
        "",
        "## F. Certificate/customer vault metafield findings",
        f"- Orders with certificate/customer vault metafields: {len(orders_with_certificates)}",
        f"- Recovered certificate rows: {len(certificates)}",
        "",
        "## G. Safe-to-import rows",
        f"- Safe allocation candidates: {len(safe)}",
        "- Criteria: order id, line item id, product identity, edition number present, and no duplicate active product/edition number within fetched data.",
        "",
        "## H. Conflict rows / needs review",
        f"- Needs review: {len(conflicts)}",
        "- Review CSV includes duplicate product edition numbers, missing identifiers, missing edition numbers, and focused sequence numbers not found in fetched Shopify metafields.",
        "",
        "## I. GOAT Debate #050/#051 investigation",
        f"- GOAT #050/#051 found in fetched Shopify order metafields: {'yes' if goat_050_051 else 'no'}",
        f"- GOAT #094/#095 found in fetched Shopify order metafields: {'yes' if goat_094_095 else 'no'}",
        "- See `goat_debate_investigation.csv` for order-level evidence.",
        "",
        "## Focused sequence checks",
    ]
    for title, summary in sequence_summary.items():
        lines.append(
            f"- {title}: found expected {summary.get('found_expected') or []}; "
            f"missing expected {summary.get('missing_expected') or []}; "
            f"all fetched editions {summary.get('all_found') or []}"
        )
    lines.extend(
        [
            "",
            "## Product metafield findings",
            *(product_lines or ["- No product metafields fetched."]),
            "",
            "## J. Proposed import/backfill plan",
            "1. Review `conflicts_needs_review.csv` and the GOAT investigation first.",
            "2. Import only `safe_import_candidates.csv` into Supabase in a separate approved write stage.",
            "3. Keep conflicting or ambiguous rows out of the first import until manually resolved.",
            "4. After import, run a second dry-run comparing Supabase counts and duplicate constraints before any Shopify sync.",
            "",
            "## K. Whether it is safe to sync new orders",
            "No. Do not sync new orders until the approved backfill/import has completed and conflicts have been resolved or explicitly quarantined.",
            "",
            "## L. Whether it is safe to generate certificates",
            "No. Do not generate certificates until Supabase contains the approved imported edition ledger and GOAT/manual review outcomes are resolved.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv if argv is not None else sys.argv[1:]))
    if missing_env_report():
        return 0

    store_domain = normalize_store_domain(os.environ["SHOPIFY_STORE_DOMAIN"])
    access_token = os.environ["SHOPIFY_ADMIN_ACCESS_TOKEN"].strip()
    api_version = os.environ["SHOPIFY_API_VERSION"].strip()
    database_url = os.environ["DATABASE_URL"].strip()
    output_dir = ensure_output_dir(args.output_dir)

    supabase_status, supabase_counts = read_supabase_table_counts(database_url)

    shopify_status = {
        "store_domain": store_domain,
        "api_version": api_version,
        "error": "",
    }
    orders: list[dict[str, Any]] = []
    products_by_id: dict[str, dict[str, Any]] = {}
    searched_products: list[dict[str, Any]] = []

    try:
        orders = fetch_shopify_orders(
            store_domain=store_domain,
            api_version=api_version,
            access_token=access_token,
            limit=max(args.limit, 1),
        )
        focus_order_names = ["SC2843"]
        if args.order_name:
            focus_order_names.append(args.order_name)
        for order_name in focus_order_names:
            orders.extend(
                fetch_shopify_orders(
                    store_domain=store_domain,
                    api_version=api_version,
                    access_token=access_token,
                    limit=10,
                    query=order_search_query(order_name),
                )
            )
        orders = dedupe_orders(orders)

        product_ids = sorted(
            {
                ((line.get("product") or {}).get("id") or "")
                for order in orders
                for line in ((order.get("lineItems") or {}).get("nodes") or [])
                if (line.get("product") or {}).get("id")
            }
        )
        for product_id in product_ids:
            product = fetch_product_by_id(
                store_domain=store_domain,
                api_version=api_version,
                access_token=access_token,
                product_id=product_id,
            )
            if product:
                products_by_id[product_id] = product

        for title in sorted(set(FOCUS_PRODUCT_TITLES + tuple(args.product_title or []))):
            searched_products.extend(
                fetch_products_by_title(
                    store_domain=store_domain,
                    api_version=api_version,
                    access_token=access_token,
                    title=title,
                )
            )
        time.sleep(0.1)
    except Exception as error:
        shopify_status["error"] = str(error)

    raw_payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "store_domain": store_domain,
        "api_version": api_version,
        "orders": orders,
        "products_by_id": products_by_id,
        "searched_products": searched_products,
    }
    allocations = recover_allocations(orders)
    certificates = recover_certificates(orders)
    metafield_rows = extract_metafield_presence(orders)
    safe, conflicts, classification = classify_allocations(allocations)
    goat_rows = goat_investigation_rows(allocations, classification["sequences"])

    products = list(products_by_id.values())
    seen_product_ids = {product.get("id") for product in products}
    for product in searched_products:
        if product.get("id") not in seen_product_ids:
            products.append(product)
            seen_product_ids.add(product.get("id"))
    product_lines = product_metafield_summary(products)

    write_csv(output_dir / "supabase_table_counts.csv", supabase_counts)
    write_json(output_dir / "shopify_orders_metafields_raw.json", raw_payload)
    write_csv(output_dir / "recovered_edition_allocations.csv", allocations)
    write_csv(output_dir / "recovered_certificates.csv", certificates)
    write_csv(output_dir / "safe_import_candidates.csv", safe)
    write_csv(output_dir / "conflicts_needs_review.csv", conflicts)
    write_csv(output_dir / "goat_debate_investigation.csv", goat_rows)
    write_csv(output_dir / "shopify_order_metafield_presence.csv", metafield_rows)

    write_summary(
        path=output_dir / "summary.md",
        supabase_status=supabase_status,
        supabase_counts=supabase_counts,
        shopify_status=shopify_status,
        orders=orders,
        allocations=allocations,
        certificates=certificates,
        safe=safe,
        conflicts=conflicts,
        goat_rows=goat_rows,
        product_lines=product_lines,
        sequence_summary=classification["sequences"],
    )
    proposed = [
        "# Proposed Next Steps",
        "",
        "Dry-run results were written without Supabase writes or Shopify mutations.",
        "",
        "1. Review `summary.md`, `conflicts_needs_review.csv`, and `goat_debate_investigation.csv`.",
        "2. Approve a separate import stage only for `safe_import_candidates.csv` after conflict review.",
        "3. Keep GOAT Debate #050/#051 manual repair separate from the first bulk import unless the evidence CSV proves those numbers exist in Shopify metafields.",
        "4. Do not sync new orders or generate certificates until the approved Supabase ledger import has completed and been dry-run verified.",
        "",
        "Suggested next approval prompt:",
        "",
        "```",
        "STAGE 3 APPROVED IMPORT ONLY - Import reviewed safe_import_candidates.csv into Supabase.",
        "Use the Stage 2B report folder generated in Render.",
        "Do not update Shopify metafields.",
        "Do not generate certificates.",
        "Do not repair GOAT Debate unless separately approved.",
        "```",
    ]
    (output_dir / "proposed_next_steps.md").write_text("\n".join(proposed) + "\n", encoding="utf-8")

    print(f"Stage 2 live dry-run report written to: {output_dir}")
    print("No Supabase writes, Shopify mutations, syncs, repairs, or certificate generation were performed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
