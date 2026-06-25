from datetime import datetime, timezone
import importlib
import json
from pathlib import Path
import re
import time

import streamlit as st

import certificate_engine
import order_allocator
import shopify_sync


BASE_DIR = Path(__file__).resolve().parent

ROWS_KEY = "orders_allocation_rows"
META_KEY = "orders_allocation_meta"
SNAPSHOT_LOADED_KEY = "orders_allocation_snapshot_loaded"
NOTICE_KEY = "orders_allocation_notice"
SNAPSHOT_FILE_NAME = "orders_allocation_snapshot.json"
GRID_KEY = "orders-fulfilment-grid"
DEFAULT_VISIBLE_ROW_LIMIT = 150
ALLOCATION_BLOCKER_STATUSES = {
    "Needs allocation",
    "Needs Review - Sold Out",
    "Missing Shopify ID",
    "Product not matched",
    "Edition disabled",
    "Product inactive",
    "Historical backfill required",
    "Allocation error",
}
VISIBLE_COLUMNS = (
    "order",
    "date",
    "customer",
    "edition",
    "certificate",
    "shipping",
    "product",
    "variant",
)


def _format_time(value):
    if not value:
        return "Never"
    parsed = order_allocator.normalize_datetime_utc(value)
    if parsed == order_allocator.DATETIME_MIN_UTC:
        return str(value)
    return parsed.astimezone().strftime("%d %b %Y %I:%M %p")


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _perf_log(label, start_time, **extra):
    elapsed = time.perf_counter() - start_time
    details = " ".join(f"{key}={value}" for key, value in extra.items())
    suffix = f" {details}" if details else ""
    print(f"PERF Orders {label} {elapsed:.3f}s{suffix}", flush=True)


def _ensure_state():
    st.session_state.setdefault(ROWS_KEY, [])
    st.session_state.setdefault(META_KEY, {"last_refreshed": "", "saved_at": ""})
    st.session_state.setdefault(NOTICE_KEY, "")


def _configured_supabase_backend():
    try:
        backend = importlib.import_module("supabase_backend")
    except Exception:
        return None
    try:
        if not backend.is_configured():
            return None
    except Exception:
        return None
    return backend


def _read_orders_snapshot():
    backend = _configured_supabase_backend()
    if backend:
        try:
            payload = order_allocator.load_supabase_orders_snapshot(limit=1000)
        except Exception as error:
            print(f"WARN Orders Supabase snapshot fallback: {error}", flush=True)
        else:
            if payload is not None:
                return payload
    return order_allocator.load_orders_snapshot()


def _ledger_status():
    backend = _configured_supabase_backend()
    if not backend:
        return {"configured": False, "connected": False, "mode": "Local/fallback only", "warning": ""}
    try:
        return backend.database_status(run_schema_check=False)
    except Exception as error:
        return {
            "configured": True,
            "connected": False,
            "mode": "Supabase/Postgres configured",
            "warning": str(error),
        }


def _ledger_counts():
    backend = _configured_supabase_backend()
    if not backend:
        return {}
    try:
        return backend.persistence_counts()
    except Exception:
        return {}


def _parse_datetime(value):
    return order_allocator.normalize_datetime_utc(value)


def _parse_order_number(value):
    digits = re.findall(r"\d+", str(value or ""))
    return int(digits[-1]) if digits else 0


def _digits(value):
    return [int(match) for match in re.findall(r"\d+", str(value or ""))]


def _normalise_edition_number(value):
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        number = int(value)
        return number if number > 0 else None
    numbers = _digits(value)
    if not numbers:
        return None
    return numbers[0] if numbers[0] > 0 else None


def _format_edition(value):
    number = _normalise_edition_number(value)
    return f"#{number:03d}" if number else ""


def _certificate_label(row):
    if row.get("certificate_pdf_url"):
        return "Uploaded"
    status = str(row.get("certificate_status") or "").strip()
    if status in ALLOCATION_BLOCKER_STATUSES:
        return status
    if status in {"Generated", "Uploaded", "Error", "Template missing", "Upload error"}:
        return "Error" if status in {"Template missing", "Upload error"} else status
    if row.get("certificate_pdf_path"):
        return "Generated"
    return "Generate"


def _allocation_numbers(allocation):
    unit_allocations = allocation.get("unit_allocations")
    if isinstance(unit_allocations, list) and unit_allocations:
        quantity = max(int(allocation.get("quantity") or 0), len(unit_allocations))
        numbers = [None] * quantity
        for unit in unit_allocations:
            if not isinstance(unit, dict):
                continue
            try:
                unit_index = int(unit.get("line_item_unit_index") or 0)
            except (TypeError, ValueError):
                unit_index = 0
            number = _normalise_edition_number(unit.get("edition_number"))
            if unit_index <= 0 or not number:
                continue
            while len(numbers) < unit_index:
                numbers.append(None)
            numbers[unit_index - 1] = number
        if any(numbers):
            return numbers
    values = allocation.get("edition_numbers")
    if isinstance(values, list):
        numbers = []
        for number in values:
            numbers.append(_normalise_edition_number(number))
        return numbers
    single = _normalise_edition_number(
        allocation.get("edition_number")
        or allocation.get("edition_display")
        or allocation.get("edition")
    )
    return [single] if single else []


def _normalise_row(row):
    updated = dict(row or {})
    raw_edition = str(updated.get("edition") or "").strip()
    edition_number = _normalise_edition_number(
        updated.get("edition_number")
        or updated.get("edition")
        or updated.get("assigned_edition_number")
    )
    updated["order"] = str(updated.get("order") or "")
    updated["date"] = str(updated.get("date") or "")
    updated["customer"] = str(updated.get("customer") or "")
    updated["shipping"] = str(updated.get("shipping") or updated.get("shipping_method") or "")
    updated["product"] = str(updated.get("product") or "")
    updated["variant"] = str(updated.get("variant") or "")
    updated["edition_number"] = edition_number
    updated["edition"] = _format_edition(edition_number) if edition_number else raw_edition
    updated["edition_total"] = int(updated.get("edition_total") or 100)
    updated["has_saved_allocation"] = bool(updated.get("has_saved_allocation"))
    updated["edition_offset"] = int(updated.get("edition_offset") or 0)
    updated["line_quantity"] = int(updated.get("line_quantity") or 1)
    updated["shopify_order_id"] = str(updated.get("shopify_order_id") or "")
    updated["legacy_resource_id"] = str(updated.get("legacy_resource_id") or "")
    updated["shopify_line_item_id"] = str(updated.get("shopify_line_item_id") or "")
    updated["shopify_product_id"] = str(updated.get("shopify_product_id") or "")
    updated["variant_id"] = str(updated.get("variant_id") or "")
    updated["product_handle"] = str(updated.get("product_handle") or updated.get("handle") or "")
    updated["shopify_customer_id"] = str(updated.get("shopify_customer_id") or updated.get("customer_id") or "")
    updated["customer_email"] = str(updated.get("customer_email") or "")
    updated["processed_at"] = str(updated.get("processed_at") or "")
    updated["created_at"] = str(updated.get("created_at") or "")
    updated["order_number_sort"] = int(updated.get("order_number_sort") or _parse_order_number(updated["order"]))
    updated["certificate_id"] = str(updated.get("certificate_id") or "")
    updated["certificate_status"] = str(updated.get("certificate_status") or "")
    updated["certificate"] = _certificate_label(updated)
    updated["certificate_pdf_path"] = str(updated.get("certificate_pdf_path") or "")
    updated["certificate_pdf_url"] = str(updated.get("certificate_pdf_url") or "")
    updated["certificate_shopify_file_id"] = str(updated.get("certificate_shopify_file_id") or "")
    updated["certificate_generated_at"] = str(updated.get("certificate_generated_at") or "")
    updated["certificate_error"] = str(updated.get("certificate_error") or "")
    updated["certificate_preview_path"] = str(updated.get("certificate_preview_path") or updated.get("preview_path") or "")
    return updated


def _sort_rows(rows):
    return sorted(
        [_normalise_row(row) for row in rows],
        key=lambda row: (
            _parse_datetime(row.get("processed_at")),
            _parse_datetime(row.get("created_at")),
            row.get("order_number_sort") or 0,
        ),
        reverse=True,
    )


def _row_key(row):
    normalised = _normalise_row(row)
    return "|".join(
        [
            normalised.get("shopify_order_id") or normalised.get("order") or "",
            normalised.get("shopify_line_item_id") or "",
            str(normalised.get("edition_offset") or 0),
            str(normalised.get("edition_number") or ""),
        ]
    )


def _certificate_fields(row):
    normalised = _normalise_row(row)
    return {
        "certificate_id": normalised.get("certificate_id") or "",
        "certificate_status": normalised.get("certificate_status") or "",
        "certificate_pdf_path": normalised.get("certificate_pdf_path") or "",
        "certificate_pdf_url": normalised.get("certificate_pdf_url") or "",
        "certificate_shopify_file_id": normalised.get("certificate_shopify_file_id") or "",
        "certificate_generated_at": normalised.get("certificate_generated_at") or "",
        "certificate_error": normalised.get("certificate_error") or "",
        "certificate_preview_path": normalised.get("certificate_preview_path") or "",
    }


def _merge_local_certificate_fields(refreshed_rows, existing_rows):
    existing_by_key = {_row_key(row): _certificate_fields(row) for row in existing_rows or []}
    output = []
    for row in refreshed_rows:
        updated = _normalise_row(row)
        existing = existing_by_key.get(_row_key(updated)) or {}
        if existing:
            for key in ("certificate_pdf_path", "certificate_preview_path"):
                if existing.get(key) and not updated.get(key):
                    updated[key] = existing[key]
        if existing and not updated.get("certificate_pdf_url"):
            updated.update({key: value for key, value in existing.items() if value})
            updated["certificate"] = _certificate_label(updated)
        output.append(_normalise_row(updated))
    return output


def _update_matching_row(target_row, updates):
    target_key = _row_key(target_row)
    rows = []
    for row in st.session_state.get(ROWS_KEY, []):
        normalised = _normalise_row(row)
        if _row_key(normalised) == target_key:
            normalised.update(updates)
        rows.append(_normalise_row(normalised))
    st.session_state[ROWS_KEY] = _sort_rows(rows)
    _write_snapshot(st.session_state[ROWS_KEY], meta=st.session_state.get(META_KEY) or {})


def _load_snapshot_once():
    if st.session_state.get(SNAPSHOT_LOADED_KEY):
        return
    start = time.perf_counter()
    payload = _read_orders_snapshot()
    st.session_state[ROWS_KEY] = _sort_rows(payload.get("rows") or [])
    st.session_state[META_KEY] = {
        "last_refreshed": payload.get("last_refreshed") or "",
        "saved_at": payload.get("saved_at") or "",
        "last_synced": payload.get("last_synced") or payload.get("last_refreshed") or "",
        "order_count": payload.get("order_count") or 0,
        "row_count": payload.get("row_count") or len(payload.get("rows") or []),
        "source": payload.get("source") or "local_snapshot",
    }
    st.session_state[SNAPSHOT_LOADED_KEY] = True
    _perf_log("load snapshot", start, rows=len(st.session_state[ROWS_KEY]))
    print("Orders load cached rows: {:.0f} ms".format((time.perf_counter() - start) * 1000), flush=True)
    print("Shopify fetch skipped on initial load", flush=True)
    print("Allocation skipped on initial load", flush=True)
    print("Metafield sync skipped on initial load", flush=True)
    print("Certificate status load skipped on initial load", flush=True)


def _write_snapshot(rows, meta=None):
    sorted_rows = _sort_rows(rows)
    payload = order_allocator.save_orders_snapshot(
        sorted_rows,
        meta=meta or st.session_state.get(META_KEY) or {},
    )
    st.session_state[META_KEY] = {
        "last_refreshed": payload.get("last_refreshed") or "",
        "saved_at": payload.get("saved_at") or "",
        "last_synced": payload.get("last_synced") or payload.get("last_refreshed") or "",
        "order_count": payload.get("order_count") or 0,
        "row_count": payload.get("row_count") or len(payload.get("rows") or []),
        "source": payload.get("source") or "local_snapshot",
    }


def _apply_latest_product_numbers(rows):
    return _sort_rows(rows)


def _allocation_for_line(order, line_item):
    allocations = order_allocator.allocation_payload_from_metafields(order.get("metafields") or [])
    return (allocations.get("line_items") or {}).get(line_item.get("shopify_line_item_id")) or {}


def _certificate_for_unit(order, line_id, edition_number, unit_index):
    certificates = certificate_engine.certificate_payload_from_metafields(order.get("metafields") or [])
    for certificate in certificates:
        if str(certificate.get("line_item_id") or "") != str(line_id or ""):
            continue
        if _normalise_edition_number(certificate.get("edition_number")) != _normalise_edition_number(edition_number):
            continue
        if int(certificate.get("line_item_unit_index") or 1) != int(unit_index or 1):
            continue
        return certificate
    return {}


def _product_is_sold_out(edition):
    try:
        total = int(edition.get("edition_total") or 100)
        sold = int(edition.get("edition_sold_count") or 0)
        remaining = int(edition.get("edition_remaining") if edition.get("edition_remaining") is not None else total - sold)
    except (TypeError, ValueError):
        return False
    return remaining <= 0 or sold >= total


def _allocation_status_for_unit(allocation, unit_index):
    unit_statuses = allocation.get("unit_statuses")
    if isinstance(unit_statuses, list) and unit_index - 1 < len(unit_statuses):
        status = str(unit_statuses[unit_index - 1] or "").strip()
        if status:
            return status
    return str(allocation.get("status") or "").strip()


def _rows_from_order_line(order, line_item, edition):
    quantity = max(int(line_item.get("quantity") or 1), 1)
    allocation = _allocation_for_line(order, line_item)
    allocation_numbers = _allocation_numbers(allocation)
    edition_total = int(allocation.get("edition_total") or edition.get("edition_total") or 100)
    rows = []
    for index in range(quantity):
        saved_number = allocation_numbers[index] if index < len(allocation_numbers) else None
        edition_number = saved_number
        allocation_status = _allocation_status_for_unit(allocation, index + 1)
        if not saved_number:
            allocation_status = allocation_status if allocation_status != "Allocated" else ""
            allocation_status = allocation_status or (
                "Needs Review - Sold Out" if _product_is_sold_out(edition) else "Needs allocation"
            )
        certificate = _certificate_for_unit(
            order,
            line_item.get("shopify_line_item_id"),
            edition_number,
            index + 1,
        )
        rows.append(
            _normalise_row(
                {
                    "order": order.get("order_name") or "",
                    "date": (order.get("processed_at") or order.get("created_at") or "")[:10],
                    "customer": order.get("customer_name") or order.get("customer_email") or "",
                    "shopify_customer_id": order.get("shopify_customer_id") or order.get("customer_id") or "",
                    "customer_email": order.get("customer_email") or "",
                    "shipping": order.get("shipping_method") or order.get("shipping_title") or "",
                    "product": line_item.get("product_title") or "",
                    "variant": line_item.get("variant_title") or "",
                    "edition_number": edition_number,
                    "edition": _format_edition(edition_number) if edition_number else allocation_status,
                    "edition_total": edition_total,
                    "has_saved_allocation": bool(saved_number),
                    "edition_offset": index,
                    "line_quantity": quantity,
                    "shopify_order_id": order.get("shopify_order_id") or "",
                    "legacy_resource_id": order.get("legacy_resource_id") or "",
                    "shopify_line_item_id": line_item.get("shopify_line_item_id") or "",
                    "shopify_product_id": line_item.get("shopify_product_id") or "",
                    "product_handle": line_item.get("product_handle") or "",
                    "variant_id": line_item.get("variant_id") or "",
                    "processed_at": order.get("processed_at") or "",
                    "created_at": order.get("created_at") or "",
                    "order_number_sort": _parse_order_number(order.get("order_name")),
                    "certificate_id": certificate.get("certificate_id") or "",
                    "certificate_status": (
                        "Uploaded"
                        if certificate.get("pdf_url")
                        else certificate.get("status") or ("" if saved_number else allocation_status)
                    ),
                    "certificate_pdf_path": certificate.get("local_pdf_path") or "",
                    "certificate_pdf_url": certificate.get("pdf_url") or certificate.get("certificate_url") or "",
                    "certificate_shopify_file_id": certificate.get("pdf_shopify_file_id") or "",
                    "certificate_generated_at": certificate.get("generated_at") or "",
                    "certificate_error": certificate.get("sync_error") or "",
                    "certificate_preview_path": certificate.get("preview_path") or "",
                }
            )
        )
    return rows


def _order_identity(order):
    return order_allocator.order_gid(order.get("shopify_order_id") or order.get("admin_graphql_api_id") or order.get("id"))


def _replace_allocation_metafield(order, allocation_payload):
    if not allocation_payload:
        return order
    updated = dict(order or {})
    metafields = []
    replaced = False
    for metafield in updated.get("metafields") or []:
        if metafield.get("namespace") == "sports_cave" and metafield.get("key") == "edition_allocations":
            metafields.append(
                {
                    **metafield,
                    "type": "json",
                    "value": json.dumps(allocation_payload, ensure_ascii=True, separators=(",", ":")),
                }
            )
            replaced = True
        else:
            metafields.append(metafield)
    if not replaced:
        metafields.append(
            {
                "namespace": "sports_cave",
                "key": "edition_allocations",
                "type": "json",
                "value": json.dumps(allocation_payload, ensure_ascii=True, separators=(",", ":")),
            }
        )
    updated["metafields"] = metafields
    return updated


def _fetch_recent_paid_orders(config):
    start = time.perf_counter()
    orders = []
    for page in shopify_sync.iter_order_pages(
        days=30,
        page_size=50,
        max_orders=100,
        query="financial_status:paid",
        default_paid_unfulfilled_filter=False,
        config=config,
    ):
        orders.extend(page.get("orders") or [])
    _perf_log("refresh Shopify", start, orders=len(orders))
    _perf_log("fetch allocations", start, source="orders_query")
    _perf_log("fetch certificates", start, source="orders_query")
    return orders


def _rows_from_orders(orders, allocation_payloads=None):
    rows = []
    allocation_payloads = allocation_payloads or {}
    for order in orders or []:
        order = _replace_allocation_metafield(order, allocation_payloads.get(_order_identity(order)))
        for line_item in order.get("line_items") or []:
            rows.extend(_rows_from_order_line(order, line_item, {}))
    return rows


def _allocation_issue_status(issue, default_status="Needs allocation"):
    status = str((issue or {}).get("status") or default_status or "").strip()
    lowered = status.casefold()
    if "sold out" in lowered:
        return "Needs Review - Sold Out"
    if "missing shopify id" in lowered or "missing product" in lowered:
        return "Missing Shopify ID"
    if "product not matched" in lowered or "product not found" in lowered:
        return "Product not matched"
    if "edition disabled" in lowered:
        return "Edition disabled"
    if "product inactive" in lowered:
        return "Product inactive"
    if "historical" in lowered:
        return "Historical backfill required"
    if "error" in lowered:
        return "Allocation error"
    return status or default_status or "Needs allocation"


def _status_payload_for_order(order, result):
    payload = order_allocator.allocation_payload_from_metafields(order.get("metafields") or [])
    payload.update(
        {
            "version": order_allocator.SNAPSHOT_VERSION,
            "source": "sports_cave_os_refresh_status",
            "order_id": _order_identity(order),
            "order_name": order.get("order_name") or order.get("name") or payload.get("order_name") or "",
            "updated_at": _now_iso(),
        }
    )
    line_items = dict(payload.get("line_items") or {})
    issue_statuses = {}
    for issue in result.get("issues") or []:
        line_id = order_allocator.line_item_gid(issue.get("line_item_id") or issue.get("line_item_gid"))
        if line_id:
            issue_statuses[line_id] = _allocation_issue_status(issue)
    default_status = "Allocation error" if result.get("error") else ""
    for line_item in order.get("line_items") or []:
        line_id = order_allocator.line_item_gid(line_item.get("shopify_line_item_id") or line_item.get("id"))
        if not line_id:
            continue
        status = issue_statuses.get(line_id) or default_status
        if not status:
            continue
        existing = dict(line_items.get(line_id) or {})
        if _positive_numbers(existing.get("edition_numbers")):
            continue
        quantity = max(int(line_item.get("quantity") or existing.get("quantity") or 1), 1)
        existing.update(
            {
                "line_item_id": line_id,
                "product_id": order_allocator.product_gid(line_item.get("shopify_product_id") or line_item.get("product_id")),
                "variant_id": line_item.get("variant_id") or line_item.get("shopify_variant_id") or "",
                "handle": line_item.get("product_handle") or line_item.get("handle") or existing.get("handle") or "",
                "product_title": line_item.get("product_title") or line_item.get("title") or existing.get("product_title") or "",
                "variant_title": line_item.get("variant_title") or existing.get("variant_title") or "",
                "quantity": quantity,
                "edition_numbers": existing.get("edition_numbers") or [None] * quantity,
                "status": status,
            }
        )
        line_items[line_id] = existing
    payload["line_items"] = line_items
    return payload


def _allocation_payloads_from_refresh(orders, allocation_result):
    by_order = {_order_identity(order): order for order in orders or []}
    payloads = {}
    for result in (allocation_result or {}).get("results") or []:
        order_id = order_allocator.order_gid(result.get("order_id"))
        if not order_id:
            continue
        if result.get("allocation_payload"):
            payloads[order_id] = result["allocation_payload"]
            continue
        if result.get("issues") or result.get("error"):
            order = by_order.get(order_id)
            if order:
                payloads[order_id] = _status_payload_for_order(order, result)
    return payloads


def _save_refreshed_rows(rows, existing_rows, refreshed_at=None):
    refreshed_at = refreshed_at or _now_iso()
    sorted_rows = _sort_rows(_merge_local_certificate_fields(rows, existing_rows))
    st.session_state[ROWS_KEY] = sorted_rows
    _write_snapshot(sorted_rows, meta={"last_refreshed": refreshed_at})
    return sorted_rows


def _refresh_orders():
    st.session_state[NOTICE_KEY] = (
        "Sync New Orders is locked for this stage. Orders are loading from the Supabase ledger only."
    )


def _display_rows(rows):
    return [
        {column: _normalise_row(row).get(column, "") for column in VISIBLE_COLUMNS}
        for row in _apply_latest_product_numbers(rows)
    ]


def _column_config():
    return {
        "order": st.column_config.TextColumn("Order", width="small"),
        "date": st.column_config.TextColumn("Date", width="small"),
        "customer": st.column_config.TextColumn("Customer", width="medium"),
        "edition": st.column_config.TextColumn("Edition", width="small"),
        "certificate": st.column_config.TextColumn("Certificate", width="small"),
        "shipping": st.column_config.TextColumn("Shipping", width="medium"),
        "product": st.column_config.TextColumn("Product", width="large"),
        "variant": st.column_config.TextColumn("Variant", width="large"),
    }


def _positive_numbers(values):
    output = []
    for value in values or []:
        number = _normalise_edition_number(value)
        if number:
            output.append(number)
    return output


def _lock_allocation_for_row(row, config):
    row = _normalise_row(row)
    if not row.get("shopify_order_id") or not row.get("shopify_line_item_id"):
        raise shopify_sync.ShopifyAPIError("Order or line item ID is missing.")
    edition_number = _normalise_edition_number(row.get("edition_number"))
    if not edition_number:
        raise ValueError("This row has no edition number to lock yet.")

    state = order_allocator.read_order_allocation_state(row["shopify_order_id"], config=config)
    payload = order_allocator.parse_allocation_payload(state.get("payload") or {})
    payload.update(
        {
            "version": order_allocator.SNAPSHOT_VERSION,
            "source": "sports_cave_os_orders_generate",
            "order_id": order_allocator.order_gid(row["shopify_order_id"]),
            "order_name": row.get("order") or payload.get("order_name") or "",
            "updated_at": _now_iso(),
        }
    )
    line_items = dict(payload.get("line_items") or {})
    line_id = order_allocator.line_item_gid(row["shopify_line_item_id"])
    allocation = dict(line_items.get(line_id) or {})
    quantity = max(int(row.get("line_quantity") or 1), int(row.get("edition_offset") or 0) + 1)
    numbers = list(allocation.get("edition_numbers") or [])
    while len(numbers) < quantity:
        numbers.append(None)
    unit_index = int(row.get("edition_offset") or 0)
    if not _normalise_edition_number(numbers[unit_index]):
        numbers[unit_index] = edition_number

    allocation.update(
        {
            "line_item_id": line_id,
            "product_id": order_allocator.product_gid(row.get("shopify_product_id")),
            "variant_id": row.get("variant_id") or "",
            "handle": row.get("product_handle") or "",
            "product_title": row.get("product") or "",
            "variant_title": row.get("variant") or "",
            "quantity": quantity,
            "edition_numbers": numbers,
            "edition_number": _positive_numbers(numbers)[0] if _positive_numbers(numbers) else edition_number,
            "edition_total": int(row.get("edition_total") or 100),
            "edition_display": order_allocator.format_edition_numbers(_positive_numbers(numbers), row.get("edition_total") or 100),
            "order_name": row.get("order") or "",
            "allocated_at": allocation.get("allocated_at") or _now_iso(),
        }
    )
    line_items[line_id] = allocation
    payload["line_items"] = line_items
    shopify_sync.sync_order_allocation_metafield(
        row["shopify_order_id"],
        payload,
        compare_digest=state.get("compare_digest"),
        config=config,
    )
    return allocation


def _update_row_from_certificate(row, record):
    updates = {
        "has_saved_allocation": True,
        "certificate_id": record.get("certificate_id") or "",
        "certificate_status": record.get("status") or "",
        "certificate_pdf_path": record.get("local_pdf_path") or "",
        "certificate_pdf_url": record.get("pdf_url") or "",
        "certificate_shopify_file_id": record.get("pdf_shopify_file_id") or "",
        "certificate_generated_at": record.get("generated_at") or "",
        "certificate_error": record.get("sync_error") or "",
        "certificate_preview_path": record.get("preview_path") or "",
    }
    updates["certificate"] = _certificate_label(updates)
    _update_matching_row(row, updates)


def _existing_uploaded_certificate(row, config):
    record = certificate_engine.certificate_record_from_order_row(row)
    start = time.perf_counter()
    state = certificate_engine.read_order_certificate_state(row.get("shopify_order_id"), config=config)
    _perf_log("fetch certificates", start, source="certificate_action")
    existing = certificate_engine.find_existing_certificate(state.get("certificates") or [], record)
    if existing and (existing.get("pdf_url") or existing.get("certificate_url")):
        return existing
    return {}


def _generate_certificate_for_row(row):
    config = shopify_sync.get_config()
    if not config.get("configured"):
        st.session_state[NOTICE_KEY] = "Store connection is not configured yet. Ask a developer before generating certificates."
        return
    row = _normalise_row(row)
    try:
        if not row.get("has_saved_allocation"):
            raise ValueError("Refresh Orders to allocate this row before generating a certificate.")
        existing = _existing_uploaded_certificate(row, config)
        if existing:
            record = {**certificate_engine.certificate_record_from_order_row(row), **existing, "status": "Uploaded"}
            _update_row_from_certificate(row, record)
            st.session_state[NOTICE_KEY] = f"Certificate already uploaded for {row.get('order')} {row.get('edition')}."
            return
        record = certificate_engine.certificate_record_from_order_row(row)
        generated = certificate_engine.generate_local_certificate_for_record(record)
        _update_row_from_certificate(row, generated)
        if generated.get("status") == "Generated":
            st.session_state[NOTICE_KEY] = f"Generated certificate for {row.get('order')} {row.get('edition')}."
        else:
            st.session_state[NOTICE_KEY] = generated.get("sync_error") or "Certificate generation needs review."
    except Exception as error:
        _update_matching_row(row, {"certificate_status": "Error", "certificate_error": str(error), "certificate": "Error"})
        st.session_state[NOTICE_KEY] = f"Certificate generation failed: {error}"


def _upload_certificate_for_row(row):
    config = shopify_sync.get_config()
    if not config.get("configured"):
        st.session_state[NOTICE_KEY] = "Store connection is not configured yet. Ask a developer before uploading certificates."
        return
    row = _normalise_row(row)
    try:
        if not row.get("has_saved_allocation"):
            raise ValueError("Refresh Orders to allocate this row before uploading a certificate.")
        existing = _existing_uploaded_certificate(row, config)
        if existing:
            record = {**certificate_engine.certificate_record_from_order_row(row), **existing, "status": "Uploaded"}
            _update_row_from_certificate(row, record)
            st.session_state[NOTICE_KEY] = f"Certificate already uploaded for {row.get('order')} {row.get('edition')}."
            return
        record = certificate_engine.certificate_record_from_order_row(row)
        record["local_pdf_path"] = row.get("certificate_pdf_path") or record.get("local_pdf_path") or ""
        if not record.get("local_pdf_path"):
            record = certificate_engine.generate_local_certificate_for_record(record)
        uploaded = certificate_engine.upload_generated_certificate_record(record, config=config)
        saved = certificate_engine.save_certificate_record_to_order(uploaded, config=config)
        saved_record = {**uploaded, **(saved.get("record") or {}), "status": "Uploaded"}
        _update_row_from_certificate(row, saved_record)
        if saved.get("metafields_synced") is False:
            st.session_state[NOTICE_KEY] = (
                f"Uploaded certificate for {row.get('order')} {row.get('edition')}, "
                "but the order metafield push needs retry."
            )
        else:
            st.session_state[NOTICE_KEY] = f"Uploaded certificate for {row.get('order')} {row.get('edition')}."
    except Exception as error:
        _update_matching_row(row, {"certificate_status": "Error", "certificate_error": str(error), "certificate": "Error"})
        st.session_state[NOTICE_KEY] = f"Certificate upload failed: {error}"


def _file_link(path):
    try:
        pdf_path = Path(path)
        if pdf_path.exists():
            return pdf_path.resolve().as_uri()
    except Exception:
        return ""
    return ""


def _selected_indices_from_state():
    state = st.session_state.get(GRID_KEY)
    if isinstance(state, dict):
        selection = state.get("selection") or {}
        raw_rows = selection.get("rows") or []
    else:
        selection = getattr(state, "selection", None)
        raw_rows = getattr(selection, "rows", []) if selection else []
    indices = []
    for value in raw_rows or []:
        try:
            indices.append(int(value))
        except (TypeError, ValueError):
            continue
    return indices


def _selected_rows_from_state(rows):
    normalised_rows = [_normalise_row(row) for row in rows or []]
    selected = []
    for index in _selected_indices_from_state():
        if 0 <= index < len(normalised_rows):
            selected.append(normalised_rows[index])
    return selected


def _current_row_for(row):
    target_key = _row_key(row)
    for current in st.session_state.get(ROWS_KEY, []):
        normalised = _normalise_row(current)
        if _row_key(normalised) == target_key:
            return normalised
    return _normalise_row(row)


def _first_pdf_url(rows):
    for row in rows or []:
        normalised = _normalise_row(row)
        if normalised.get("certificate_pdf_url"):
            return normalised["certificate_pdf_url"]
        local_link = _file_link(normalised.get("certificate_pdf_path"))
        if local_link:
            return local_link
    return ""


def _generate_selected_certificates(rows):
    if not rows:
        st.session_state[NOTICE_KEY] = "Select one or more order rows first."
        return
    start = time.perf_counter()
    for row in rows:
        _generate_certificate_for_row(row)
    _perf_log("generate selected certificates", start, rows=len(rows))
    st.session_state[NOTICE_KEY] = f"Generated or checked {len(rows)} selected certificate(s)."


def _upload_selected_certificates(rows):
    if not rows:
        st.session_state[NOTICE_KEY] = "Select one or more order rows first."
        return
    start = time.perf_counter()
    for row in rows:
        _upload_certificate_for_row(row)
    _perf_log("upload selected certificates", start, rows=len(rows))
    st.session_state[NOTICE_KEY] = f"Uploaded or checked {len(rows)} selected certificate(s)."


def _generate_upload_selected_certificates(rows):
    if not rows:
        st.session_state[NOTICE_KEY] = "Select one or more order rows first."
        return
    start = time.perf_counter()
    for row in rows:
        _generate_certificate_for_row(row)
        _upload_certificate_for_row(_current_row_for(row))
    _perf_log("generate selected certificates", start, rows=len(rows), mode="generate_upload")
    _perf_log("upload selected certificates", start, rows=len(rows), mode="generate_upload")
    st.session_state[NOTICE_KEY] = f"Generated and uploaded {len(rows)} selected certificate(s)."


def _render_top_actions(rows):
    selected_rows = _selected_rows_from_state(rows)
    selected_count = len(selected_rows)
    open_url = _first_pdf_url(selected_rows)

    action_cols = st.columns([1.1, 1.55, 1.45, 1.55, 1.2])
    if action_cols[0].button("Sync New Orders", type="primary", use_container_width=True, disabled=True):
        with st.spinner("Syncing new paid orders..."):
            _refresh_orders()
        st.rerun()
    if action_cols[1].button(
        "Generate Selected Certificates",
        use_container_width=True,
        disabled=selected_count == 0,
    ):
        with st.spinner("Generating selected certificates..."):
            _generate_selected_certificates(selected_rows)
        st.rerun()
    if action_cols[2].button(
        "Upload Selected to Shopify",
        use_container_width=True,
        disabled=selected_count == 0,
    ):
        with st.spinner("Uploading selected certificates..."):
            _upload_selected_certificates(selected_rows)
        st.rerun()
    if action_cols[3].button(
        "Generate + Upload Selected",
        use_container_width=True,
        disabled=selected_count == 0,
    ):
        with st.spinner("Generating and uploading selected certificates..."):
            _generate_upload_selected_certificates(selected_rows)
        st.rerun()
    if open_url:
        action_cols[4].link_button("Open Selected PDF", open_url, use_container_width=True)
    else:
        action_cols[4].button("Open Selected PDF", use_container_width=True, disabled=True)
    st.caption(f"{selected_count} row(s) selected. Tip: scroll sideways to view all fulfilment fields.")
    st.caption("New-order sync stays locked here until the backfill and verification stages are approved.")


def _render_ledger_diagnostics():
    status = _ledger_status()
    if not status.get("configured"):
        return
    counts = _ledger_counts()
    expander = getattr(st, "expander", None)
    if not expander:
        return
    with expander("Supabase ledger diagnostics", expanded=False):
        st.caption("Supabase connected" if status.get("connected") else "Supabase connection failed")
        st.caption("Source: Supabase ledger" if status.get("connected") else "Source: fallback cache")
        if status.get("warning"):
            st.caption(status.get("warning"))
        for label, key in (
            ("shopify_orders", "shopify_orders"),
            ("shopify_order_lines", "shopify_order_lines"),
            ("edition_orders", "edition_orders"),
            ("edition_products", "edition_products"),
            ("audit_logs", "audit_logs"),
        ):
            st.caption(f"{label}: {int(counts.get(key) or 0)}")


def _render_orders_table(rows):
    start = time.perf_counter()
    rows = [_normalise_row(row) for row in rows]
    with st.container(border=True):
        st.dataframe(
            _display_rows(rows),
            hide_index=True,
            use_container_width=True,
            height=min(840, max(440, 32 * (len(rows) + 1))),
            column_order=VISIBLE_COLUMNS,
            column_config=_column_config(),
            selection_mode="multi-row",
            on_select="rerun",
            row_height=30,
            key=GRID_KEY,
        )
    _perf_log("render table", start, rows=len(rows))
    print("Table render: {:.0f} ms".format((time.perf_counter() - start) * 1000), flush=True)


def render_page():
    _ensure_state()
    _load_snapshot_once()
    rows = _apply_latest_product_numbers(st.session_state.get(ROWS_KEY, []))
    st.session_state[ROWS_KEY] = rows
    visible_rows = rows[:DEFAULT_VISIBLE_ROW_LIMIT]
    meta = st.session_state.get(META_KEY) or {}
    ledger_status = _ledger_status()
    source_label = "Supabase ledger" if meta.get("source") == "supabase" and ledger_status.get("connected") else "Local fallback cache"

    st.title("Orders")
    st.caption("Operational orders ledger. Edition numbers load from Supabase first.")
    st.caption("Supabase connected" if ledger_status.get("connected") else "Supabase connection failed")
    st.caption(f"Source: {source_label}")
    order_count = int(meta.get("order_count") or 0)
    count_label = f" | Cached orders: {order_count}" if order_count else ""
    st.caption(f"Last synced: {_format_time(meta.get('last_synced') or meta.get('last_refreshed'))}{count_label}")

    notice = st.session_state.get(NOTICE_KEY)
    if notice:
        st.success(notice)
        st.session_state[NOTICE_KEY] = ""

    _render_top_actions(rows)
    _render_ledger_diagnostics()

    if not rows:
        st.info("No saved orders are available in the operational ledger yet.")
        return

    if len(rows) > len(visible_rows):
        st.caption(f"Showing latest {len(visible_rows)} of {len(rows)} saved artwork rows.")
    else:
        st.caption(f"{len(rows)} artwork rows shown.")
    _render_orders_table(visible_rows)
