#!/usr/bin/env python3
"""Apply approved Stage 2D rows into Supabase.

Default mode is dry-run. Writes occur only when --apply is passed.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row


DATABASE_ENV_VAR = "DATABASE_URL"
DEFAULT_STAGE2D_GLOB = "stage2d_manual_truth_compare_*"
DEFAULT_OUTPUT_PREFIX = "stage3_supabase_import_"

APPROVED_INPUTS = (
    ("import_ready_manual_matches_shopify.csv", "manual_truth_matches_shopify_20260625"),
    ("import_ready_manual_overrides_shopify.csv", "manual_truth_overrides_shopify_20260625"),
    ("import_ready_shopify_only_no_manual_conflict.csv", "shopify_metafield_no_manual_conflict_20260625"),
)

REQUIRED_STAGE2D_FILES = (
    "import_ready_manual_matches_shopify.csv",
    "import_ready_manual_overrides_shopify.csv",
    "import_ready_shopify_only_no_manual_conflict.csv",
    "proposed_supabase_import_preview.csv",
    "proposed_manual_repairs_preview.csv",
    "stage2d_summary.md",
)

TOUCHED_TABLES = (
    "shopify_orders",
    "shopify_order_lines",
    "edition_orders",
    "edition_products",
    "audit_logs",
)

FORBIDDEN_ARGS = {
    "--write",
    "write",
    "--sync",
    "sync",
    "--repair",
    "repair",
    "--shopify",
    "shopify",
}


def parse_args(argv: list[str]) -> argparse.Namespace:
    forbidden = [arg for arg in argv if arg.strip().lower() in FORBIDDEN_ARGS]
    if forbidden:
        print("Refusing to run: this Stage 3 importer only supports dry-run or --apply to Supabase.")
        print("Forbidden argument(s): " + ", ".join(forbidden))
        raise SystemExit(2)

    parser = argparse.ArgumentParser(
        description="Apply approved Stage 2D rows into Supabase. Default mode is dry-run."
    )
    parser.add_argument("--apply", action="store_true", help="Apply writes to Supabase.")
    parser.add_argument(
        "--stage2d-dir",
        default="",
        help="Specific Stage 2D folder. Defaults to latest output/stage2d_manual_truth_compare_*.",
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help="Output folder. Defaults to output/stage3_supabase_import_YYYYMMDD_HHMM.",
    )
    return parser.parse_args(argv)


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M")


def normalize_whitespace(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\r", " ").replace("\n", " ")).strip()


def positive_int(value: Any) -> int | None:
    try:
        number = int(str(value or "").strip())
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def find_latest_stage2d_dir(explicit: str) -> Path | None:
    if explicit:
        path = Path(explicit)
        return path if path.exists() and path.is_dir() else None
    candidates = [path for path in Path("output").glob(DEFAULT_STAGE2D_GLOB) if path.is_dir()]
    if not candidates:
        return None
    return sorted(candidates, key=lambda path: (path.name, path.stat().st_mtime), reverse=True)[0]


def ensure_output_dir(explicit: str) -> Path:
    if explicit:
        path = Path(explicit)
    else:
        path = Path("output") / f"{DEFAULT_OUTPUT_PREFIX}{now_stamp()}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_csv_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_csv(path: Path, rows: list[dict[str, Any]], preferred_fields: list[str] | None = None) -> None:
    fields: list[str] = []
    for field in preferred_fields or []:
        if field not in fields:
            fields.append(field)
    for row in rows:
        for field in row.keys():
            if field not in fields:
                fields.append(field)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields or ["empty"])
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


def load_stage2d_inputs(stage2d_dir: Path) -> dict[str, Any]:
    missing = [name for name in REQUIRED_STAGE2D_FILES if not (stage2d_dir / name).exists()]
    if missing:
        print("Stage 3 importer cannot run because the Stage 2D folder is incomplete.")
        for name in missing:
            print(f"Missing: {stage2d_dir / name}")
        raise SystemExit(0)

    data: dict[str, Any] = {
        "stage2d_dir": stage2d_dir,
        "summary_md": (stage2d_dir / "stage2d_summary.md").read_text(encoding="utf-8"),
        "proposed_supabase_import_preview": load_csv_rows(stage2d_dir / "proposed_supabase_import_preview.csv"),
        "proposed_manual_repairs_preview": load_csv_rows(stage2d_dir / "proposed_manual_repairs_preview.csv"),
    }
    for filename, assignment_source in APPROVED_INPUTS:
        data[filename] = load_csv_rows(stage2d_dir / filename)
        data[f"{filename}:assignment_source"] = assignment_source
    return data


def parse_order_number(value: Any) -> str:
    text = normalize_whitespace(value)
    if not text:
        return ""
    match = re.search(r"(SC\d+|\d+)", text, flags=re.IGNORECASE)
    return match.group(1) if match else text


def source_defaults(assignment_source: str) -> dict[str, Any]:
    return {
        "assignment_source": assignment_source,
        "manual_override": assignment_source == "manual_truth_overrides_shopify_20260625",
    }


def normalize_input_row(row: dict[str, Any], assignment_source: str, source_file: str) -> dict[str, Any]:
    defaults = source_defaults(assignment_source)
    edition_number = positive_int(row.get("manual_edition_number")) or positive_int(row.get("shopify_edition_number"))
    quantity_index = positive_int(row.get("quantity_index")) or 1
    product_handle = normalize_whitespace(row.get("product_handle"))
    product_id = normalize_whitespace(row.get("product_id"))
    order_id = normalize_whitespace(row.get("order_id"))
    line_item_id = normalize_whitespace(row.get("line_item_shopify_id") or row.get("shopify_line_item_id"))
    order_name = normalize_whitespace(row.get("order_name"))
    customer_name = normalize_whitespace(row.get("customer_name"))
    customer_email = normalize_whitespace(row.get("customer_email"))
    product_title = normalize_whitespace(row.get("product_title"))
    variant_title = normalize_whitespace(row.get("variant_title"))
    variant_id = normalize_whitespace(row.get("variant_id") or row.get("shopify_variant_id"))
    sku = normalize_whitespace(row.get("sku"))
    edition_total = positive_int(row.get("edition_total")) or 100
    manual_override = truthy(row.get("shopify_manual_override")) or defaults["manual_override"]
    return {
        "source_file": source_file,
        "assignment_source": assignment_source,
        "assignment_status": "assigned",
        "order_id": order_id,
        "order_name": order_name,
        "order_number": parse_order_number(order_name),
        "line_item_id": line_item_id,
        "quantity_index": quantity_index,
        "quantity": 1,
        "product_handle": product_handle,
        "product_id": product_id,
        "product_title": product_title,
        "variant_id": variant_id,
        "variant_title": variant_title,
        "sku": sku,
        "customer_name": customer_name,
        "customer_email": customer_email,
        "edition_number": edition_number,
        "edition_total": edition_total,
        "purchase_date": normalize_whitespace(row.get("order_created_at") or row.get("purchase_date")),
        "manual_override": manual_override,
        "has_certificate_payload": truthy(row.get("has_certificate_payload")),
        "row_json": dict(row),
    }


def load_approved_rows(stage2d_data: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for filename, assignment_source in APPROVED_INPUTS:
        for raw_row in stage2d_data[filename]:
            rows.append(normalize_input_row(raw_row, assignment_source, filename))
    return rows


def input_identity_key(row: dict[str, Any]) -> tuple[str, str, int]:
    return (
        str(row.get("order_id") or ""),
        str(row.get("line_item_id") or ""),
        int(row.get("quantity_index") or 1),
    )


def line_dedupe_key(row: dict[str, Any]) -> tuple[str, str, str, int, str]:
    return (
        str(row.get("order_id") or ""),
        str(row.get("line_item_id") or ""),
        str(row.get("product_handle") or row.get("product_id") or ""),
        int(row.get("quantity_index") or 1),
        str(row.get("edition_number") or ""),
    )


def product_identity_key(row: dict[str, Any]) -> str:
    return str(row.get("product_handle") or row.get("product_id") or "").strip().lower()


def product_edition_key(row: dict[str, Any]) -> tuple[str, int]:
    return (product_identity_key(row), int(row.get("edition_number") or 0))


def validate_and_prepare_inputs(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    ready: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []

    grouped_by_identity: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped_by_identity[input_identity_key(row)].append(row)

    kept: list[dict[str, Any]] = []
    for identity, group in grouped_by_identity.items():
        order_id, line_item_id, quantity_index = identity
        for row in group:
            if not order_id or not line_item_id:
                skipped.append(
                    {
                        **row,
                        "reason": "missing_identifier",
                        "detail": "order_id or line_item_id is missing.",
                    }
                )
                continue
            if not product_identity_key(row):
                skipped.append(
                    {
                        **row,
                        "reason": "missing_identifier",
                        "detail": "product_handle/product_id is missing.",
                    }
                )
                continue
            if not positive_int(row.get("edition_number")):
                skipped.append(
                    {
                        **row,
                        "reason": "missing_or_invalid_edition_number",
                        "detail": "edition_number is missing or invalid.",
                    }
                )
                continue

        valid_group = [
            row for row in group
            if order_id and line_item_id and product_identity_key(row) and positive_int(row.get("edition_number"))
        ]
        if not valid_group:
            continue

        unique_values = {
            (int(row.get("edition_number") or 0), str(row.get("assignment_source") or ""))
            for row in valid_group
        }
        if len(unique_values) > 1:
            for row in valid_group:
                conflicts.append(
                    {
                        **row,
                        "reason": "batch_identity_conflict",
                        "detail": "The same order line/allocation index appears more than once with different edition_number or assignment_source.",
                    }
                )
            continue

        kept.append(valid_group[0])
        for extra_row in valid_group[1:]:
            skipped.append(
                {
                    **extra_row,
                    "reason": "duplicate_input_row",
                    "detail": "Identical duplicate row in approved inputs was ignored.",
                }
            )

    grouped_by_product_edition: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in kept:
        grouped_by_product_edition[product_edition_key(row)].append(row)

    conflicted_identity_keys: set[tuple[str, str, int]] = set()
    for key, group in grouped_by_product_edition.items():
        identity_keys = {input_identity_key(row) for row in group}
        if key[0] and len(identity_keys) > 1:
            conflicted_identity_keys |= identity_keys
            for row in group:
                conflicts.append(
                    {
                        **row,
                        "reason": "batch_product_edition_conflict",
                        "detail": "The approved input set assigns the same product/edition to multiple order line identities.",
                    }
                )

    for row in kept:
        if input_identity_key(row) in conflicted_identity_keys:
            continue
        ready.append(row)
    return ready, skipped, conflicts


def connect_db(database_url: str, *, readonly: bool):
    options = "-c default_transaction_read_only=on" if readonly else None
    return psycopg.connect(
        database_url,
        row_factory=dict_row,
        autocommit=readonly,
        options=options,
    )


def verify_required_tables(conn) -> None:
    with conn.cursor() as cur:
        for table_name in TOUCHED_TABLES:
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = current_schema()
                      AND table_name = %s
                ) AS exists
                """,
                (table_name,),
            )
            exists = bool((cur.fetchone() or {}).get("exists"))
            if not exists:
                raise RuntimeError(f"Required table is missing: {table_name}")


def get_counts(conn) -> dict[str, int]:
    counts: dict[str, int] = {}
    with conn.cursor() as cur:
        for table_name in TOUCHED_TABLES:
            cur.execute(f'SELECT COUNT(*) AS count FROM "{table_name}"')
            counts[table_name] = int((cur.fetchone() or {}).get("count") or 0)
    return counts


def load_existing_state(conn, rows: list[dict[str, Any]]) -> dict[str, Any]:
    line_item_ids = sorted({str(row.get("line_item_id") or "") for row in rows if row.get("line_item_id")})
    product_handles = sorted({str(row.get("product_handle") or "") for row in rows if row.get("product_handle")})
    product_ids = sorted({str(row.get("product_id") or "") for row in rows if row.get("product_id")})
    edition_numbers = sorted({int(row.get("edition_number") or 0) for row in rows if row.get("edition_number")})

    edition_orders: list[dict[str, Any]] = []
    edition_products: list[dict[str, Any]] = []
    shopify_orders: list[dict[str, Any]] = []
    shopify_order_lines: list[dict[str, Any]] = []

    with conn.cursor() as cur:
        if line_item_ids or product_handles or product_ids:
            cur.execute(
                """
                SELECT
                    eo.id::text AS id,
                    eo.shopify_order_id,
                    eo.shopify_order_name,
                    eo.shopify_line_item_id,
                    eo.shopify_product_id,
                    eo.shopify_variant_id,
                    eo.shopify_handle,
                    eo.product_handle,
                    eo.product_title,
                    eo.variant_title,
                    eo.sku,
                    eo.customer_name,
                    eo.customer_email,
                    eo.edition_number,
                    eo.edition_total,
                    eo.allocation_index,
                    eo.purchase_date,
                    eo.source,
                    eo.status,
                    eo.manual_override
                FROM edition_orders eo
                WHERE (
                    array_length(%s::text[], 1) IS NOT NULL
                    AND eo.shopify_line_item_id = ANY(%s)
                ) OR (
                    array_length(%s::text[], 1) IS NOT NULL
                    AND COALESCE(NULLIF(eo.shopify_handle, ''), NULLIF(eo.product_handle, '')) = ANY(%s)
                    AND (
                        array_length(%s::int[], 1) IS NULL
                        OR eo.edition_number = ANY(%s)
                    )
                ) OR (
                    array_length(%s::text[], 1) IS NOT NULL
                    AND COALESCE(NULLIF(eo.shopify_product_id, ''), '') = ANY(%s)
                    AND (
                        array_length(%s::int[], 1) IS NULL
                        OR eo.edition_number = ANY(%s)
                    )
                )
                """,
                (
                    line_item_ids or None,
                    line_item_ids or None,
                    product_handles or None,
                    product_handles or None,
                    edition_numbers or None,
                    edition_numbers or None,
                    product_ids or None,
                    product_ids or None,
                    edition_numbers or None,
                    edition_numbers or None,
                ),
            )
            edition_orders = cur.fetchall()

        if product_handles or product_ids:
            cur.execute(
                """
                SELECT *
                FROM edition_products
                WHERE (
                    array_length(%s::text[], 1) IS NOT NULL
                    AND shopify_handle = ANY(%s)
                ) OR (
                    array_length(%s::text[], 1) IS NOT NULL
                    AND shopify_product_id = ANY(%s)
                )
                """,
                (
                    product_handles or None,
                    product_handles or None,
                    product_ids or None,
                    product_ids or None,
                ),
            )
            edition_products = cur.fetchall()

        order_ids = sorted({str(row.get("order_id") or "") for row in rows if row.get("order_id")})
        if order_ids:
            cur.execute(
                "SELECT * FROM shopify_orders WHERE shopify_order_id = ANY(%s)",
                (order_ids,),
            )
            shopify_orders = cur.fetchall()

        if line_item_ids:
            cur.execute(
                "SELECT * FROM shopify_order_lines WHERE shopify_line_item_id = ANY(%s)",
                (line_item_ids,),
            )
            shopify_order_lines = cur.fetchall()

    existing_line_index = {
        (
            str(row.get("shopify_line_item_id") or ""),
            int(row.get("allocation_index") or 1),
        ): dict(row)
        for row in edition_orders
    }
    existing_product_edition_index: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in edition_orders:
        handle = str(row.get("shopify_handle") or row.get("product_handle") or row.get("shopify_product_id") or "").strip().lower()
        number = positive_int(row.get("edition_number"))
        if handle and number:
            existing_product_edition_index[(handle, number)].append(dict(row))

    edition_products_by_handle = {
        str(row.get("shopify_handle") or "").strip().lower(): dict(row)
        for row in edition_products
        if str(row.get("shopify_handle") or "").strip()
    }
    edition_products_by_product_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in edition_products:
        product_id = str(row.get("shopify_product_id") or "").strip()
        if product_id:
            edition_products_by_product_id[product_id].append(dict(row))

    return {
        "existing_line_index": existing_line_index,
        "existing_product_edition_index": existing_product_edition_index,
        "edition_products_by_handle": edition_products_by_handle,
        "edition_products_by_product_id": edition_products_by_product_id,
        "shopify_orders_by_id": {
            str(row.get("shopify_order_id") or "").strip(): dict(row)
            for row in shopify_orders
            if str(row.get("shopify_order_id") or "").strip()
        },
        "shopify_lines_by_id": {
            str(row.get("shopify_line_item_id") or "").strip(): dict(row)
            for row in shopify_order_lines
            if str(row.get("shopify_line_item_id") or "").strip()
        },
    }


def same_source_consistent(existing_source: str, incoming_source: str) -> bool:
    current = str(existing_source or "").strip()
    target = str(incoming_source or "").strip()
    return current in {"", target}


def mutable_order_fields_changed(existing: dict[str, Any], incoming: dict[str, Any]) -> bool:
    checks = (
        ("shopify_order_id", "order_id"),
        ("shopify_order_name", "order_name"),
        ("shopify_product_id", "product_id"),
        ("shopify_variant_id", "variant_id"),
        ("shopify_handle", "product_handle"),
        ("product_handle", "product_handle"),
        ("product_title", "product_title"),
        ("variant_title", "variant_title"),
        ("sku", "sku"),
        ("customer_name", "customer_name"),
        ("customer_email", "customer_email"),
        ("edition_total", "edition_total"),
        ("purchase_date", "purchase_date"),
    )
    for existing_key, incoming_key in checks:
        new_value = incoming.get(incoming_key)
        old_value = existing.get(existing_key)
        if existing_key in {"edition_total"}:
            if positive_int(new_value) and positive_int(new_value) != positive_int(old_value):
                return True
            continue
        if existing_key in {"purchase_date"}:
            if normalize_whitespace(new_value) and normalize_whitespace(new_value) != normalize_whitespace(old_value):
                return True
            continue
        if normalize_whitespace(new_value) and normalize_whitespace(new_value) != normalize_whitespace(old_value):
            return True
    if truthy(existing.get("manual_override")) != bool(incoming.get("manual_override")):
        return True
    if str(existing.get("source") or "").strip() != str(incoming.get("assignment_source") or "").strip():
        return True
    return False


def build_plan(rows: list[dict[str, Any]], existing_state: dict[str, Any]) -> dict[str, Any]:
    to_apply: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []

    existing_line_index = existing_state["existing_line_index"]
    existing_product_edition_index = existing_state["existing_product_edition_index"]

    for row in rows:
        line_key = (str(row.get("line_item_id") or ""), int(row.get("quantity_index") or 1))
        existing_line = existing_line_index.get(line_key)
        product_key = product_identity_key(row)
        prod_edition_key = (product_key, int(row.get("edition_number") or 0))
        conflicting_existing_rows = [
            existing
            for existing in existing_product_edition_index.get(prod_edition_key, [])
            if not (
                str(existing.get("shopify_line_item_id") or "") == line_key[0]
                and int(existing.get("allocation_index") or 1) == line_key[1]
            )
        ]

        if existing_line:
            existing_edition_number = positive_int(existing_line.get("edition_number"))
            if existing_edition_number != positive_int(row.get("edition_number")):
                conflicts.append(
                    {
                        **row,
                        "reason": "existing_line_different_edition",
                        "detail": (
                            f"Line already exists with edition {existing_edition_number}; "
                            f"incoming row wants {row.get('edition_number')}."
                        ),
                        "existing_edition_order_id": existing_line.get("id") or "",
                    }
                )
                continue
            if not same_source_consistent(existing_line.get("source"), row.get("assignment_source")):
                conflicts.append(
                    {
                        **row,
                        "reason": "existing_line_different_source",
                        "detail": (
                            f"Line already exists with source {existing_line.get('source')}; "
                            f"incoming row uses {row.get('assignment_source')}."
                        ),
                        "existing_edition_order_id": existing_line.get("id") or "",
                    }
                )
                continue
            if conflicting_existing_rows:
                conflicts.append(
                    {
                        **row,
                        "reason": "existing_product_edition_on_different_line",
                        "detail": "The same product/edition already exists on a different order line in Supabase.",
                        "existing_edition_order_id": conflicting_existing_rows[0].get("id") or "",
                    }
                )
                continue
            if mutable_order_fields_changed(existing_line, row):
                to_apply.append(
                    {
                        **row,
                        "planned_action": "update_existing_line",
                        "existing_edition_order_id": existing_line.get("id") or "",
                    }
                )
            else:
                skipped.append(
                    {
                        **row,
                        "reason": "already_present_consistent",
                        "detail": "Supabase already contains the same line/edition/source combination.",
                        "existing_edition_order_id": existing_line.get("id") or "",
                    }
                )
            continue

        if conflicting_existing_rows:
            conflicts.append(
                {
                    **row,
                    "reason": "existing_product_edition_on_different_line",
                    "detail": "The same product/edition already exists on a different order line in Supabase.",
                    "existing_edition_order_id": conflicting_existing_rows[0].get("id") or "",
                }
            )
            continue

        to_apply.append({**row, "planned_action": "insert_new_line", "existing_edition_order_id": ""})

    return {
        "to_apply": to_apply,
        "skipped": skipped,
        "conflicts": conflicts,
    }


def group_line_quantities(rows: list[dict[str, Any]]) -> dict[str, int]:
    quantities: dict[str, int] = {}
    for row in rows:
        line_item_id = str(row.get("line_item_id") or "").strip()
        if not line_item_id:
            continue
        quantities[line_item_id] = max(quantities.get(line_item_id, 1), int(row.get("quantity_index") or 1))
    return quantities


def upsert_shopify_order(cur, row: dict[str, Any]) -> None:
    raw_json = json_dumps(
        {
            "stage3_import": True,
            "assignment_source": row.get("assignment_source"),
            "source_file": row.get("source_file"),
            "approved_row": row.get("row_json") or {},
        }
    )
    cur.execute(
        """
        INSERT INTO shopify_orders(
            shopify_order_id, order_name, shopify_order_name,
            order_number, shopify_order_number,
            customer_name, customer_email, email,
            created_at, processed_at,
            raw_json, raw, synced_at, updated_at
        )
        VALUES (
            %s, %s, %s,
            %s, %s,
            %s, %s, %s,
            NULLIF(%s, '')::timestamptz, NULLIF(%s, '')::timestamptz,
            %s::jsonb, %s::jsonb, now(), now()
        )
        ON CONFLICT (shopify_order_id) DO UPDATE SET
            order_name=COALESCE(NULLIF(EXCLUDED.order_name, ''), shopify_orders.order_name),
            shopify_order_name=COALESCE(NULLIF(EXCLUDED.shopify_order_name, ''), shopify_orders.shopify_order_name),
            order_number=COALESCE(NULLIF(EXCLUDED.order_number, ''), shopify_orders.order_number),
            shopify_order_number=COALESCE(NULLIF(EXCLUDED.shopify_order_number, ''), shopify_orders.shopify_order_number),
            customer_name=COALESCE(NULLIF(EXCLUDED.customer_name, ''), shopify_orders.customer_name),
            customer_email=COALESCE(NULLIF(EXCLUDED.customer_email, ''), shopify_orders.customer_email),
            email=COALESCE(NULLIF(EXCLUDED.email, ''), shopify_orders.email),
            created_at=COALESCE(EXCLUDED.created_at, shopify_orders.created_at),
            processed_at=COALESCE(EXCLUDED.processed_at, shopify_orders.processed_at),
            raw_json=EXCLUDED.raw_json,
            raw=EXCLUDED.raw,
            synced_at=now(),
            updated_at=now()
        """,
        (
            row.get("order_id"),
            row.get("order_name"),
            row.get("order_name"),
            row.get("order_number"),
            row.get("order_number"),
            row.get("customer_name"),
            row.get("customer_email"),
            row.get("customer_email"),
            row.get("purchase_date") or "",
            row.get("purchase_date") or "",
            raw_json,
            raw_json,
        ),
    )


def upsert_shopify_order_line(cur, row: dict[str, Any], line_quantity: int) -> None:
    raw_json = json_dumps(
        {
            "stage3_import": True,
            "assignment_source": row.get("assignment_source"),
            "source_file": row.get("source_file"),
            "approved_row": row.get("row_json") or {},
        }
    )
    cur.execute(
        """
        INSERT INTO shopify_order_lines(
            shopify_line_item_id, shopify_order_id, shopify_product_id, shopify_handle,
            product_title, variant_title, sku, quantity, assignment_status, last_error,
            raw_json, synced_at, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'Assigned', '', %s::jsonb, now(), now())
        ON CONFLICT (shopify_line_item_id) DO UPDATE SET
            shopify_order_id=COALESCE(NULLIF(EXCLUDED.shopify_order_id, ''), shopify_order_lines.shopify_order_id),
            shopify_product_id=COALESCE(NULLIF(EXCLUDED.shopify_product_id, ''), shopify_order_lines.shopify_product_id),
            shopify_handle=COALESCE(NULLIF(EXCLUDED.shopify_handle, ''), shopify_order_lines.shopify_handle),
            product_title=COALESCE(NULLIF(EXCLUDED.product_title, ''), shopify_order_lines.product_title),
            variant_title=COALESCE(NULLIF(EXCLUDED.variant_title, ''), shopify_order_lines.variant_title),
            sku=COALESCE(NULLIF(EXCLUDED.sku, ''), shopify_order_lines.sku),
            quantity=GREATEST(COALESCE(shopify_order_lines.quantity, 1), EXCLUDED.quantity),
            assignment_status='Assigned',
            last_error='',
            raw_json=EXCLUDED.raw_json,
            synced_at=now(),
            updated_at=now()
        """,
        (
            row.get("line_item_id"),
            row.get("order_id"),
            row.get("product_id"),
            row.get("product_handle"),
            row.get("product_title"),
            row.get("variant_title"),
            row.get("sku"),
            max(int(line_quantity or 1), 1),
            raw_json,
        ),
    )


def find_existing_product_row(cur, row: dict[str, Any]) -> dict[str, Any] | None:
    handle = str(row.get("product_handle") or "").strip()
    product_id = str(row.get("product_id") or "").strip()
    if handle:
        cur.execute(
            "SELECT * FROM edition_products WHERE shopify_handle = %s LIMIT 1",
            (handle,),
        )
        result = cur.fetchone()
        if result:
            return dict(result)
    if product_id:
        cur.execute(
            "SELECT * FROM edition_products WHERE shopify_product_id = %s ORDER BY updated_at DESC NULLS LAST, id DESC",
            (product_id,),
        )
        rows = [dict(found) for found in cur.fetchall()]
        if len(rows) == 1:
            return rows[0]
        if len(rows) > 1:
            raise RuntimeError(
                f"Multiple edition_products rows exist for shopify_product_id={product_id}; manual resolution required."
            )
    return None


def upsert_edition_product(cur, row: dict[str, Any]) -> None:
    handle = str(row.get("product_handle") or "").strip()
    product_id = str(row.get("product_id") or "").strip()
    desired_last = int(row.get("edition_number") or 0)
    desired_next = desired_last + 1 if desired_last else 1
    edition_total = int(row.get("edition_total") or 100)

    if handle:
        cur.execute(
            """
            INSERT INTO edition_products(
                shopify_product_id, shopify_handle, product_title,
                edition_total, next_edition_number, last_assigned_edition, sold_count,
                remaining_count, edition_status, active, is_active, sold_out, is_sold_out,
                raw, synced_at, updated_at
            )
            VALUES (
                %s, %s, %s,
                %s, %s, %s, %s,
                GREATEST(%s - %s, 0), 'limited_release', TRUE, TRUE, %s, %s,
                %s::jsonb, now(), now()
            )
            ON CONFLICT (shopify_handle) DO UPDATE SET
                shopify_product_id=COALESCE(NULLIF(EXCLUDED.shopify_product_id, ''), edition_products.shopify_product_id),
                product_title=COALESCE(NULLIF(EXCLUDED.product_title, ''), edition_products.product_title),
                edition_total=GREATEST(COALESCE(edition_products.edition_total, 100), EXCLUDED.edition_total),
                next_edition_number=GREATEST(COALESCE(edition_products.next_edition_number, 1), EXCLUDED.next_edition_number),
                last_assigned_edition=GREATEST(COALESCE(edition_products.last_assigned_edition, 0), EXCLUDED.last_assigned_edition),
                sold_count=GREATEST(COALESCE(edition_products.sold_count, 0), EXCLUDED.sold_count),
                remaining_count=GREATEST(
                    GREATEST(COALESCE(edition_products.edition_total, EXCLUDED.edition_total), EXCLUDED.edition_total)
                    - GREATEST(COALESCE(edition_products.sold_count, 0), EXCLUDED.sold_count),
                    0
                ),
                sold_out=GREATEST(COALESCE(edition_products.next_edition_number, 1), EXCLUDED.next_edition_number)
                    > GREATEST(COALESCE(edition_products.edition_total, EXCLUDED.edition_total), EXCLUDED.edition_total),
                is_sold_out=GREATEST(COALESCE(edition_products.next_edition_number, 1), EXCLUDED.next_edition_number)
                    > GREATEST(COALESCE(edition_products.edition_total, EXCLUDED.edition_total), EXCLUDED.edition_total),
                raw=EXCLUDED.raw,
                updated_at=now()
            """,
            (
                product_id or None,
                handle,
                row.get("product_title"),
                edition_total,
                desired_next,
                desired_last,
                desired_last,
                edition_total,
                desired_last,
                desired_next > edition_total,
                desired_next > edition_total,
                json_dumps(
                    {
                        "stage3_import": True,
                        "assignment_source": row.get("assignment_source"),
                        "approved_row": row.get("row_json") or {},
                    }
                ),
            ),
        )
        return

    existing = find_existing_product_row(cur, row)
    raw_json = json_dumps(
        {
            "stage3_import": True,
            "assignment_source": row.get("assignment_source"),
            "approved_row": row.get("row_json") or {},
        }
    )
    if existing:
        cur.execute(
            """
            UPDATE edition_products
            SET product_title=COALESCE(NULLIF(%s, ''), product_title),
                edition_total=GREATEST(COALESCE(edition_total, 100), %s),
                next_edition_number=GREATEST(COALESCE(next_edition_number, 1), %s),
                last_assigned_edition=GREATEST(COALESCE(last_assigned_edition, 0), %s),
                sold_count=GREATEST(COALESCE(sold_count, 0), %s),
                remaining_count=GREATEST(GREATEST(COALESCE(edition_total, %s), %s) - GREATEST(COALESCE(sold_count, 0), %s), 0),
                sold_out=GREATEST(COALESCE(next_edition_number, 1), %s) > GREATEST(COALESCE(edition_total, %s), %s),
                is_sold_out=GREATEST(COALESCE(next_edition_number, 1), %s) > GREATEST(COALESCE(edition_total, %s), %s),
                raw=%s::jsonb,
                updated_at=now()
            WHERE id=%s
            """,
            (
                row.get("product_title"),
                edition_total,
                desired_next,
                desired_last,
                desired_last,
                edition_total,
                edition_total,
                desired_last,
                desired_next,
                edition_total,
                edition_total,
                desired_next,
                edition_total,
                edition_total,
                raw_json,
                existing.get("id"),
            ),
        )
    else:
        cur.execute(
            """
            INSERT INTO edition_products(
                shopify_product_id, product_title, edition_total, next_edition_number,
                last_assigned_edition, sold_count, remaining_count,
                edition_status, active, is_active, sold_out, is_sold_out,
                raw, synced_at, updated_at
            )
            VALUES (
                %s, %s, %s, %s,
                %s, %s, GREATEST(%s - %s, 0),
                'limited_release', TRUE, TRUE, %s, %s,
                %s::jsonb, now(), now()
            )
            """,
            (
                product_id or None,
                row.get("product_title"),
                edition_total,
                desired_next,
                desired_last,
                desired_last,
                edition_total,
                desired_last,
                desired_next > edition_total,
                desired_next > edition_total,
                raw_json,
            ),
        )


def insert_or_update_edition_order(cur, row: dict[str, Any]) -> dict[str, Any]:
    existing_id = row.get("existing_edition_order_id")
    if row.get("planned_action") == "update_existing_line" and existing_id:
        cur.execute(
            """
            UPDATE edition_orders
            SET shopify_order_id=COALESCE(NULLIF(%s, ''), shopify_order_id),
                shopify_order_name=COALESCE(NULLIF(%s, ''), shopify_order_name),
                shopify_product_id=COALESCE(NULLIF(%s, ''), shopify_product_id),
                shopify_variant_id=COALESCE(NULLIF(%s, ''), shopify_variant_id),
                shopify_handle=COALESCE(NULLIF(%s, ''), shopify_handle),
                product_handle=COALESCE(NULLIF(%s, ''), product_handle),
                product_title=COALESCE(NULLIF(%s, ''), product_title),
                variant_title=COALESCE(NULLIF(%s, ''), variant_title),
                sku=COALESCE(NULLIF(%s, ''), sku),
                customer_name=COALESCE(NULLIF(%s, ''), customer_name),
                customer_email=COALESCE(NULLIF(%s, ''), customer_email),
                shopify_customer_name=COALESCE(NULLIF(%s, ''), shopify_customer_name),
                shopify_customer_email=COALESCE(NULLIF(%s, ''), shopify_customer_email),
                edition_total=GREATEST(COALESCE(edition_total, 100), %s),
                edition_display=%s,
                purchase_date=COALESCE(NULLIF(%s, '')::timestamptz, purchase_date),
                source=COALESCE(NULLIF(%s, ''), source),
                status='assigned',
                manual_override=%s,
                updated_at=now()
            WHERE id::text=%s
            RETURNING id::text AS id
            """,
            (
                row.get("order_id"),
                row.get("order_name"),
                row.get("product_id"),
                row.get("variant_id"),
                row.get("product_handle"),
                row.get("product_handle"),
                row.get("product_title"),
                row.get("variant_title"),
                row.get("sku"),
                row.get("customer_name"),
                row.get("customer_email"),
                row.get("customer_name"),
                row.get("customer_email"),
                int(row.get("edition_total") or 100),
                f"#{int(row.get('edition_number') or 0):03d}/{int(row.get('edition_total') or 100)}",
                row.get("purchase_date") or "",
                row.get("assignment_source"),
                bool(row.get("manual_override")),
                existing_id,
            ),
        )
        return dict(cur.fetchone() or {"id": existing_id})

    cur.execute(
        """
        INSERT INTO edition_orders(
            shopify_order_id, shopify_order_name, shopify_line_item_id,
            shopify_product_id, shopify_variant_id, shopify_handle, product_handle,
            product_title, variant_title, sku,
            customer_name, customer_email, shopify_customer_name, shopify_customer_email,
            edition_number, edition_total, edition_display, allocation_index, quantity,
            assigned_at, certificate_status, purchase_date, source, status, manual_override,
            created_at, updated_at
        )
        VALUES (
            %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s, 1,
            now(), 'Certificate Missing', NULLIF(%s, '')::timestamptz, %s, 'assigned', %s,
            now(), now()
        )
        RETURNING id::text AS id
        """,
        (
            row.get("order_id"),
            row.get("order_name"),
            row.get("line_item_id"),
            row.get("product_id"),
            row.get("variant_id"),
            row.get("product_handle"),
            row.get("product_handle"),
            row.get("product_title"),
            row.get("variant_title"),
            row.get("sku"),
            row.get("customer_name"),
            row.get("customer_email"),
            row.get("customer_name"),
            row.get("customer_email"),
            int(row.get("edition_number") or 0),
            int(row.get("edition_total") or 100),
            f"#{int(row.get('edition_number') or 0):03d}/{int(row.get('edition_total') or 100)}",
            int(row.get("quantity_index") or 1),
            row.get("purchase_date") or "",
            row.get("assignment_source"),
            bool(row.get("manual_override")),
        ),
    )
    return dict(cur.fetchone() or {})


def insert_audit_log(cur, *, event_type: str, row: dict[str, Any], entity_id: str = "", reason: str = "", old_value: Any = None, new_value: Any = None) -> None:
    cur.execute(
        """
        INSERT INTO audit_logs(
            event_type, entity_type, entity_id, shopify_order_id, shopify_line_item_id,
            shopify_handle, old_value, new_value, reason, actor, source, created_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, 'sports_cave_os', %s, now())
        """,
        (
            event_type,
            "edition_order",
            entity_id or "",
            row.get("order_id") or "",
            row.get("line_item_id") or "",
            row.get("product_handle") or "",
            json_dumps(old_value or {}),
            json_dumps(new_value or {}),
            reason or "",
            row.get("assignment_source") or "sports_cave_os",
        ),
    )


def fetch_edition_products_after(conn, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    handles = sorted({str(row.get("product_handle") or "").strip() for row in rows if row.get("product_handle")})
    product_ids = sorted({str(row.get("product_id") or "").strip() for row in rows if row.get("product_id")})
    if not handles and not product_ids:
        return []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                id::text AS id,
                shopify_product_id,
                shopify_handle,
                product_title,
                edition_total,
                next_edition_number,
                last_assigned_edition,
                sold_count,
                remaining_count,
                sold_out,
                updated_at
            FROM edition_products
            WHERE (
                array_length(%s::text[], 1) IS NOT NULL
                AND shopify_handle = ANY(%s)
            ) OR (
                array_length(%s::text[], 1) IS NOT NULL
                AND shopify_product_id = ANY(%s)
            )
            ORDER BY COALESCE(shopify_handle, shopify_product_id, product_title)
            """,
            (
                handles or None,
                handles or None,
                product_ids or None,
                product_ids or None,
            ),
        )
        return [dict(row) for row in cur.fetchall()]


def projected_product_states(rows_to_apply: list[dict[str, Any]], existing_state: dict[str, Any]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows_to_apply:
        grouped[product_identity_key(row)].append(row)

    projected: list[dict[str, Any]] = []
    by_handle = existing_state["edition_products_by_handle"]
    by_product_id = existing_state["edition_products_by_product_id"]

    for key, rows in sorted(grouped.items()):
        first = rows[0]
        current = {}
        if first.get("product_handle"):
            current = dict(by_handle.get(str(first.get("product_handle")).lower()) or {})
        elif first.get("product_id"):
            current_rows = by_product_id.get(str(first.get("product_id")), [])
            if len(current_rows) == 1:
                current = dict(current_rows[0])
        imported_max = max(int(row.get("edition_number") or 0) for row in rows)
        edition_total = max([int(first.get("edition_total") or 100)] + [int(current.get("edition_total") or 100)])
        current_next = int(current.get("next_edition_number") or 1)
        current_last = int(current.get("last_assigned_edition") or 0)
        current_sold = int(current.get("sold_count") or 0)
        projected_next = max(current_next, imported_max + 1 if imported_max else 1)
        projected_last = max(current_last, imported_max)
        projected_sold = max(current_sold, imported_max)
        projected_remaining = max(edition_total - projected_sold, 0)
        projected.append(
            {
                "product_key": key,
                "shopify_handle": first.get("product_handle") or current.get("shopify_handle") or "",
                "shopify_product_id": first.get("product_id") or current.get("shopify_product_id") or "",
                "product_title": first.get("product_title") or current.get("product_title") or "",
                "edition_total": edition_total,
                "current_next_edition_number": current_next,
                "projected_next_edition_number": projected_next,
                "current_last_assigned_edition": current_last,
                "projected_last_assigned_edition": projected_last,
                "current_sold_count": current_sold,
                "projected_sold_count": projected_sold,
                "projected_remaining_count": projected_remaining,
            }
        )
    return projected


def projected_counts(counts_before: dict[str, int], plan: dict[str, Any], existing_state: dict[str, Any]) -> dict[str, dict[str, int]]:
    line_keys_existing = set(existing_state["existing_line_index"].keys())
    inserts = sum(
        1
        for row in plan["to_apply"]
        if row.get("planned_action") == "insert_new_line"
    )
    order_ids_new = {
        str(row.get("order_id") or "")
        for row in plan["to_apply"]
        if str(row.get("order_id") or "")
        and str(row.get("order_id") or "") not in existing_state["shopify_orders_by_id"]
    }
    line_ids_new = {
        str(row.get("line_item_id") or "")
        for row in plan["to_apply"]
        if str(row.get("line_item_id") or "")
        and str(row.get("line_item_id") or "") not in existing_state["shopify_lines_by_id"]
    }
    product_keys_existing = {
        key for key in existing_state["edition_products_by_handle"].keys()
    }
    for product_id, rows in existing_state["edition_products_by_product_id"].items():
        if len(rows) == 1:
            product_keys_existing.add(product_id.lower())
    product_keys_new = {
        product_identity_key(row)
        for row in plan["to_apply"]
        if product_identity_key(row) and product_identity_key(row) not in product_keys_existing
    }
    conflict_logs = len(plan["conflicts"])
    applied_logs = len(plan["to_apply"])
    return {
        "shopify_orders": {
            "before": counts_before["shopify_orders"],
            "after": counts_before["shopify_orders"] + len(order_ids_new),
        },
        "shopify_order_lines": {
            "before": counts_before["shopify_order_lines"],
            "after": counts_before["shopify_order_lines"] + len(line_ids_new),
        },
        "edition_orders": {
            "before": counts_before["edition_orders"],
            "after": counts_before["edition_orders"] + inserts,
        },
        "edition_products": {
            "before": counts_before["edition_products"],
            "after": counts_before["edition_products"] + len(product_keys_new),
        },
        "audit_logs": {
            "before": counts_before["audit_logs"],
            "after": counts_before["audit_logs"] + conflict_logs + applied_logs,
        },
    }


def execute_apply(conn, plan: dict[str, Any], existing_state: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, int], str]:
    line_quantities = group_line_quantities(plan["to_apply"])
    applied_rows: list[dict[str, Any]] = []
    skipped_rows: list[dict[str, Any]] = list(plan["skipped"])
    conflicts: list[dict[str, Any]] = list(plan["conflicts"])
    cache_status = "not_attempted"

    with conn.cursor() as cur:
        for row in plan["conflicts"]:
            insert_audit_log(
                cur,
                event_type="stage3_import_conflict_skipped",
                row=row,
                reason=row.get("reason") or "",
                new_value={"detail": row.get("detail") or ""},
            )

        for row in plan["to_apply"]:
            upsert_shopify_order(cur, row)
            upsert_shopify_order_line(cur, row, line_quantities.get(str(row.get("line_item_id") or ""), 1))
            upsert_edition_product(cur, row)
            before_state = {}
            if row.get("existing_edition_order_id"):
                before_state = {
                    "edition_order_id": row.get("existing_edition_order_id"),
                    "planned_action": row.get("planned_action"),
                }
            result = insert_or_update_edition_order(cur, row)
            applied_rows.append(
                {
                    **row,
                    "applied_action": row.get("planned_action"),
                    "edition_order_id": result.get("id") or row.get("existing_edition_order_id") or "",
                }
            )
            insert_audit_log(
                cur,
                event_type="stage3_import_applied",
                row=row,
                entity_id=result.get("id") or row.get("existing_edition_order_id") or "",
                reason=row.get("planned_action") or "",
                old_value=before_state,
                new_value={
                    "edition_number": row.get("edition_number"),
                    "assignment_source": row.get("assignment_source"),
                    "manual_override": bool(row.get("manual_override")),
                },
            )

    conn.commit()
    counts_after = get_counts(conn)

    try:
        import order_allocator  # Local safe cache writer; no Shopify writes.

        payload = order_allocator.load_supabase_orders_snapshot(limit=5000)
        if payload and payload.get("source") == "supabase":
            order_allocator.save_orders_snapshot(
                payload.get("rows") or [],
                meta={"last_refreshed": payload.get("last_refreshed") or ""},
            )
            cache_status = "rebuilt_from_supabase_only"
        else:
            cache_status = "skipped_no_supabase_snapshot_payload"
    except Exception as error:  # pragma: no cover - local optional cache rebuild
        cache_status = f"skipped_cache_rebuild_error: {error}"

    return applied_rows, skipped_rows, conflicts, counts_after, cache_status


def write_summary(
    path: Path,
    *,
    mode: str,
    rows_attempted: int,
    rows_applied: int,
    rows_skipped: int,
    conflicts_skipped: int,
    product_counter_rows: int,
    counts_rows: list[dict[str, Any]],
    cache_status: str,
) -> None:
    lines = [
        "# Stage 3 Supabase Import Summary",
        "",
        f"- Mode: {mode}",
        f"- Rows attempted: {rows_attempted}",
        f"- Rows applied: {rows_applied}",
        f"- Rows skipped: {rows_skipped}",
        f"- Conflicts skipped: {conflicts_skipped}",
        f"- Product counters updated: {product_counter_rows}",
        f"- Cache rebuild: {cache_status}",
        "",
        "## Supabase table counts",
    ]
    for row in counts_rows:
        lines.append(
            f"- {row.get('table_name')}: before={row.get('before_count')} after={row.get('after_count')} mode={row.get('mode')}"
        )
    lines.extend(
        [
            "",
            "## Safety",
            "- Safe to sync new orders: no",
            "- Safe to generate certificates: no",
            "- Another dry-run should be run: yes",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_next_steps(path: Path, *, mode: str) -> None:
    lines = [
        "# Next Steps",
        "",
        f"Mode completed: {mode}",
        "",
        "1. Review `conflicts_not_applied.csv` and `skipped_rows.csv` before any follow-on import stage.",
        "2. Re-run Stage 2D compare against the latest Supabase-backed snapshot before considering any new-order sync.",
        "3. Do not sync new Shopify orders yet.",
        "4. Do not generate certificates yet.",
        "5. Resolve duplicate conflicts and unmatched manual rows in a separate approved stage.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv if argv is not None else sys.argv[1:]))
    database_url = os.getenv(DATABASE_ENV_VAR, "").strip()
    if not database_url:
        print("DATABASE_URL is required.")
        return 0

    stage2d_dir = find_latest_stage2d_dir(args.stage2d_dir)
    if not stage2d_dir:
        print("No Stage 2D folder was found under output/stage2d_manual_truth_compare_*.")
        print("Pass --stage2d-dir explicitly if the folder exists elsewhere.")
        return 0

    output_dir = ensure_output_dir(args.output_dir)
    stage2d_data = load_stage2d_inputs(stage2d_dir)
    input_rows = load_approved_rows(stage2d_data)
    ready_rows, pre_skipped_rows, pre_conflicts = validate_and_prepare_inputs(input_rows)

    mode = "apply" if args.apply else "dry-run"
    cache_status = "skipped_in_dry_run"

    with connect_db(database_url, readonly=not args.apply) as conn:
        verify_required_tables(conn)
        counts_before = get_counts(conn)
        existing_state = load_existing_state(conn, ready_rows)
        plan = build_plan(ready_rows, existing_state)
        plan["skipped"] = pre_skipped_rows + plan["skipped"]
        plan["conflicts"] = pre_conflicts + plan["conflicts"]

        if args.apply:
            applied_rows, skipped_rows, conflicts, counts_after, cache_status = execute_apply(conn, plan, existing_state)
            product_rows = fetch_edition_products_after(conn, applied_rows)
        else:
            applied_rows = [
                {
                    **row,
                    "applied_action": row.get("planned_action"),
                    "edition_order_id": row.get("existing_edition_order_id") or "",
                }
                for row in plan["to_apply"]
            ]
            skipped_rows = list(plan["skipped"])
            conflicts = list(plan["conflicts"])
            projected = projected_counts(counts_before, plan, existing_state)
            counts_after = {table_name: row["after"] for table_name, row in projected.items()}
            product_rows = projected_product_states(plan["to_apply"], existing_state)

    counts_csv_rows: list[dict[str, Any]] = []
    if args.apply:
        for table_name in TOUCHED_TABLES:
            counts_csv_rows.append(
                {
                    "table_name": table_name,
                    "before_count": counts_before.get(table_name, 0),
                    "after_count": counts_after.get(table_name, 0),
                    "mode": mode,
                }
            )
    else:
        projected = projected_counts(counts_before, plan, existing_state)
        for table_name in TOUCHED_TABLES:
            counts_csv_rows.append(
                {
                    "table_name": table_name,
                    "before_count": counts_before.get(table_name, 0),
                    "after_count": projected[table_name]["after"],
                    "mode": mode,
                }
            )

    write_summary(
        output_dir / "stage3_summary.md",
        mode=mode,
        rows_attempted=len(ready_rows),
        rows_applied=len(applied_rows),
        rows_skipped=len(skipped_rows),
        conflicts_skipped=len(conflicts),
        product_counter_rows=len(product_rows),
        counts_rows=counts_csv_rows,
        cache_status=cache_status,
    )
    write_csv(output_dir / "applied_edition_orders.csv", applied_rows)
    write_csv(output_dir / "skipped_rows.csv", skipped_rows)
    write_csv(output_dir / "conflicts_not_applied.csv", conflicts)
    write_csv(output_dir / "edition_products_after_import.csv", product_rows)
    write_csv(output_dir / "supabase_counts_after_import.csv", counts_csv_rows)
    write_next_steps(output_dir / "next_steps.md", mode=mode)

    print(f"Stage 3 importer completed in {mode} mode.")
    print(f"Stage 2D source folder: {stage2d_dir}")
    print(f"Output folder: {output_dir}")
    if args.apply:
        print("Supabase writes were applied. Shopify was not updated.")
    else:
        print("No Supabase writes were made.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
