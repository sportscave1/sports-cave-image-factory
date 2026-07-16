from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime, timedelta, timezone
import importlib
import json
from pathlib import Path
import re
import time
from zoneinfo import ZoneInfo

import streamlit as st
import streamlit.components.v1 as components
try:
    import pandas as pd
except Exception:  # pragma: no cover - optional at import time
    pd = None

import certificate_engine
import certificate_job
import order_allocator
import shopify_sync
from certificate_logging import certificate_stage_log


BASE_DIR = Path(__file__).resolve().parent
try:
    SYDNEY_TZ = ZoneInfo("Australia/Sydney")
except Exception:  # pragma: no cover - fallback for minimal local Python installs
    SYDNEY_TZ = timezone(timedelta(hours=10), "AEST")

ROWS_KEY = "orders_allocation_rows"
META_KEY = "orders_allocation_meta"
SNAPSHOT_LOADED_KEY = "orders_allocation_snapshot_loaded"
NOTICE_KEY = "orders_allocation_notice"
CERTIFICATE_ACTION_LOADING_KEY = "orders_certificate_action_loading"
CERTIFICATE_ACTION_STATE_KEY = "orders_certificate_action_state"
CERTIFICATE_ACTION_STALE_SECONDS = 300
SNAPSHOT_FILE_NAME = "orders_allocation_snapshot.json"
GRID_KEY = "orders-fulfilment-grid"
COPY_ORDER_ICON = "\u29c9"
SYNC_RESULT_KEY = "orders_sync_result"
BACKFILL_RESULT_KEY = "orders_backfill_result"
LATEST_FETCH_PREVIEW_KEY = "orders_latest_fetch_preview"
REPAIR_RESULT_KEY = "orders_missing_edition_repair_result"
ORDER_SYNC_BACKFILL_KEY = "orders_sync_backfill_latest_paid"
ORDERS_SYNC_TIMEOUT_SECONDS = 90
ORDERS_SUPABASE_LIVE_MARKER_KEY = "orders_supabase_live_visibility_marker"
ORDERS_SUPABASE_LIVE_CHECK_SECONDS = 25
SEARCH_KEY = "orders_search_text"
LOADED_QUERY_KEY = "orders_loaded_query"
SHOW_ALL_KEY = "orders_show_all_rows"
LOAD_ERROR_KEY = "orders_load_error"
LOAD_FUTURE_KEY = "orders_load_future"
LOAD_REQUEST_KEY = "orders_load_request"
LOAD_STARTED_KEY = "orders_load_started_at"
DEFAULT_VISIBLE_ROW_LIMIT = 50
ORDERS_PAGE_LOAD_TIMEOUT_SECONDS = 8
HYBRID_FAST_ORDERS_ENABLED = True
_ORDERS_LOAD_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="orders-ledger-read")
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
    "edition",
    "certificate",
    "customer",
    "product",
    "variant",
    "shipping",
    "date",
    "prodigi",
)


def _format_time(value):
    if not value:
        return "Never"
    parsed = order_allocator.normalize_datetime_utc(value)
    if parsed == order_allocator.DATETIME_MIN_UTC:
        return str(value)
    return parsed.astimezone(SYDNEY_TZ).strftime("%d %b %Y %I:%M %p %Z (Sydney)")


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _perf_log(label, start_time, **extra):
    elapsed = time.perf_counter() - start_time
    details = " ".join(f"{key}={value}" for key, value in extra.items())
    suffix = f" {details}" if details else ""
    print(f"PERF Orders {label} {elapsed:.3f}s{suffix}", flush=True)


def _certificate_action_log(event, *, row=None, source="Orders", **extra):
    normalised = _normalise_row(row or {}) if row else {}
    details = {
        "source": source,
        "order": normalised.get("order") or normalised.get("order_name") or "",
        "selected_row_found": bool(row),
        **extra,
    }
    safe_details = " ".join(f"{key}={value}" for key, value in details.items() if value not in (None, ""))
    print(f"CERTIFICATE ACTION: {event} {safe_details}", flush=True)


def _certificate_action_key(row):
    normalised = _normalise_row(row or {})
    parts = (
        normalised.get("edition_order_id"),
        normalised.get("shopify_order_id"),
        normalised.get("shopify_line_item_id"),
        normalised.get("edition_number"),
        normalised.get("order"),
    )
    return "|".join(str(part or "").strip() for part in parts if str(part or "").strip())


def _certificate_action_started_at(state):
    try:
        return float((state or {}).get("started_at") or 0)
    except (TypeError, ValueError):
        return 0.0


def _clear_stale_certificate_action_state(source="Orders"):
    state = st.session_state.get(CERTIFICATE_ACTION_STATE_KEY) or {}
    started_at = _certificate_action_started_at(state)
    if started_at and time.time() - started_at > CERTIFICATE_ACTION_STALE_SECONDS:
        _certificate_action_log(
            "stale loading state cleared",
            source=source,
            action_key=state.get("action_key") or "",
            order=state.get("order") or "",
        )
        st.session_state[CERTIFICATE_ACTION_STATE_KEY] = {}
        st.session_state[CERTIFICATE_ACTION_LOADING_KEY] = False


def _set_certificate_action_state(row, source="Orders"):
    _clear_stale_certificate_action_state(source=source)
    action_key = _certificate_action_key(row)
    state = st.session_state.get(CERTIFICATE_ACTION_STATE_KEY) or {}
    active_key = str(state.get("action_key") or "")
    if active_key and active_key == action_key:
        raise RuntimeError("Certificate upload is already in progress for this order. You can retry in a moment.")
    normalised = _normalise_row(row or {})
    st.session_state[CERTIFICATE_ACTION_STATE_KEY] = {
        "action_key": action_key,
        "order": normalised.get("order") or normalised.get("order_name") or "",
        "edition_order_id": normalised.get("edition_order_id") or "",
        "source": source,
        "started_at": time.time(),
    }
    st.session_state[CERTIFICATE_ACTION_LOADING_KEY] = True


def _clear_certificate_action_state(source="Orders"):
    st.session_state[CERTIFICATE_ACTION_STATE_KEY] = {}
    st.session_state[CERTIFICATE_ACTION_LOADING_KEY] = False
    certificate_stage_log("loading_state_cleared", "completed", source_page=source)
    _certificate_action_log("loading state cleared", source=source)


def _ensure_state():
    st.session_state.setdefault(ROWS_KEY, [])
    st.session_state.setdefault(META_KEY, {"last_refreshed": "", "saved_at": ""})
    st.session_state.setdefault(NOTICE_KEY, "")
    st.session_state.setdefault(CERTIFICATE_ACTION_LOADING_KEY, False)
    st.session_state.setdefault(CERTIFICATE_ACTION_STATE_KEY, {})
    _clear_stale_certificate_action_state(source="Orders")
    st.session_state.setdefault(SYNC_RESULT_KEY, {})
    st.session_state.setdefault(BACKFILL_RESULT_KEY, {})
    st.session_state.setdefault(REPAIR_RESULT_KEY, {})
    st.session_state.setdefault(LATEST_FETCH_PREVIEW_KEY, {})
    st.session_state.setdefault(ORDER_SYNC_BACKFILL_KEY, False)
    st.session_state.setdefault(SEARCH_KEY, "")
    st.session_state.setdefault(LOADED_QUERY_KEY, "")
    st.session_state.setdefault(SHOW_ALL_KEY, False)
    st.session_state.setdefault(LOAD_ERROR_KEY, "")
    st.session_state.setdefault(LOAD_FUTURE_KEY, None)
    st.session_state.setdefault(LOAD_REQUEST_KEY, "")
    st.session_state.setdefault(LOAD_STARTED_KEY, 0.0)


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


def _read_orders_snapshot(search="", limit=DEFAULT_VISIBLE_ROW_LIMIT):
    backend = _configured_supabase_backend()
    if backend:
        if HYBRID_FAST_ORDERS_ENABLED and hasattr(order_allocator, "load_hybrid_orders_snapshot"):
            return order_allocator.load_hybrid_orders_snapshot(
                limit=max(int(limit or DEFAULT_VISIBLE_ROW_LIMIT), 1),
                search=str(search or "").strip(),
            )
        return order_allocator.load_supabase_orders_snapshot(
            limit=max(int(limit or DEFAULT_VISIBLE_ROW_LIMIT), 1),
            include_summary=False,
        )
    return order_allocator.load_orders_snapshot()


def _database_load_diagnostic(error):
    diagnostic = dict(getattr(error, "diagnostic", {}) or {})
    diagnostic.setdefault("operation", "orders.load")
    diagnostic.setdefault("category", "database_unavailable")
    diagnostic.setdefault("exception_class", error.__class__.__name__)
    diagnostic.setdefault("duration_ms", 0)
    return diagnostic


def _record_snapshot_load_error(error, query):
    diagnostic = _database_load_diagnostic(error)
    safe_error = str(error) or "Orders database read failed."
    existing_rows = list(st.session_state.get(ROWS_KEY) or [])
    existing_meta = dict(st.session_state.get(META_KEY) or {})
    existing_meta.update(
        {
            "order_count": existing_meta.get("order_count") or 0,
            "row_count": len(existing_rows),
            "source": existing_meta.get("source") or "supabase_error",
            "error": safe_error,
            "database_read": diagnostic,
            "search": query,
        }
    )
    st.session_state[ROWS_KEY] = existing_rows
    st.session_state[META_KEY] = existing_meta
    st.session_state[LOAD_ERROR_KEY] = safe_error
    st.session_state[LOADED_QUERY_KEY] = query
    st.session_state[SNAPSHOT_LOADED_KEY] = True
    print(
        "ERROR Orders Supabase snapshot failed "
        f"operation={diagnostic.get('operation')} category={diagnostic.get('category')} "
        f"exception_class={diagnostic.get('exception_class')} "
        f"duration_ms={diagnostic.get('duration_ms')}",
        flush=True,
    )


def _start_snapshot_load(search="", *, force=False):
    query = str(search or "").strip()
    current = st.session_state.get(LOAD_FUTURE_KEY)
    current_query = str(st.session_state.get(LOAD_REQUEST_KEY) or "")
    if current is not None and not current.done() and current_query == query and not force:
        print(f"PERF Orders cache hit query={bool(query)} state=pending", flush=True)
        return current
    if current is not None and not current.done():
        current.cancel()
    st.session_state[LOAD_ERROR_KEY] = ""
    st.session_state[LOAD_REQUEST_KEY] = query
    st.session_state[LOAD_STARTED_KEY] = time.monotonic()
    future = _ORDERS_LOAD_EXECUTOR.submit(
        _read_orders_snapshot,
        search=query,
        limit=DEFAULT_VISIBLE_ROW_LIMIT,
    )
    st.session_state[LOAD_FUTURE_KEY] = future
    print(
        "PERF Orders cache miss "
        f"query={bool(query)} limit={DEFAULT_VISIBLE_ROW_LIMIT} source=supabase",
        flush=True,
    )
    return future


def _consume_snapshot_load():
    future = st.session_state.get(LOAD_FUTURE_KEY)
    if future is None:
        return "idle"
    query = str(st.session_state.get(LOAD_REQUEST_KEY) or "")
    started = float(st.session_state.get(LOAD_STARTED_KEY) or time.monotonic())
    elapsed = time.monotonic() - started
    if not future.done():
        if elapsed < ORDERS_PAGE_LOAD_TIMEOUT_SECONDS:
            return "loading"
        future.cancel()
        timeout_error = TimeoutError("The database read timed out. Please retry.")
        timeout_error.diagnostic = {
            "operation": "orders.search" if query else "orders.latest_50",
            "category": "request_timeout",
            "exception_class": "TimeoutError",
            "duration_ms": int(elapsed * 1000),
        }
        _record_snapshot_load_error(timeout_error, query)
        st.session_state[LOAD_FUTURE_KEY] = None
        _perf_log("load snapshot timeout", time.perf_counter() - elapsed)
        return "error"
    try:
        payload = future.result()
    except Exception as error:
        _record_snapshot_load_error(error, query)
        status = "error"
    else:
        st.session_state[LOAD_ERROR_KEY] = ""
        _apply_snapshot_payload(payload)
        st.session_state[LOADED_QUERY_KEY] = query
        st.session_state[SNAPSHOT_LOADED_KEY] = True
        _perf_log("load snapshot async", time.perf_counter() - elapsed, rows=len(st.session_state[ROWS_KEY]))
        status = "ready"
    st.session_state[LOAD_FUTURE_KEY] = None
    return status


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


def _format_edition_with_total(number, total=None):
    edition = _format_edition(number)
    total_number = int(total or 0)
    if not edition:
        return ""
    if total_number > 0:
        return f"{edition}/{total_number}"
    return edition


def _coerce_positive_int(value, default=0):
    try:
        number = int(value or 0)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


def _placeholder_text(value, *, missing="Missing from ledger"):
    text = str(value or "").strip()
    return text if text else missing


def _display_shipping_label(value):
    text = str(value or "").strip()
    if not text:
        return "Missing shipping"
    lowered = text.casefold()
    if any(token in lowered for token in ("express", "priority", "rush")):
        return "Express"
    if any(token in lowered for token in ("standard", "economy", "regular")):
        return "Standard"
    return text


def _compact_variant_label(value):
    text = str(value or "").strip()
    if not text:
        return "Missing variant"
    for separator in (" - ", " – ", " — "):
        if separator in text:
            compact = text.split(separator, 1)[0].strip()
            if compact:
                return compact
    if len(text) > 34:
        return f"{text[:31].rstrip()}..."
    return text


def _display_variant_label(value):
    text = str(value or "").strip()
    return text if text else "Missing variant"


def _display_prodigi_status(value):
    status = str(value or "").strip()
    if not status:
        return "Not started"
    lowered = status.casefold()
    if lowered in {"needs review", "hold / issue"} or "issue" in lowered:
        return "Issue"
    if lowered in {"ready to send", "submitted"}:
        return "In progress"
    if lowered in {"submitted to prodigi", "in production", "awaiting tracking", "shipped"}:
        return "Sent to Prodigi"
    if lowered == "fulfilled in shopify":
        return "Complete"
    return status


def _developer_mode():
    return bool(st.session_state.get("developer_unlocked"))


def _certificate_is_uploaded(row):
    return bool(
        str(row.get("certificate_pdf_url") or row.get("shopify_file_url") or "").strip()
        or str(row.get("certificate_shopify_file_id") or "").strip()
    )


def _certificate_is_ready(row):
    status = str(row.get("certificate_status") or "").strip().casefold()
    if _certificate_is_uploaded(row):
        return True
    if "ready" in status or "generated" in status:
        return True
    return bool(str(row.get("certificate_pdf_path") or "").strip())


def _certificate_label(row):
    status = str(row.get("certificate_status") or row.get("edition") or row.get("assignment_status") or "").strip()
    if status in ALLOCATION_BLOCKER_STATUSES and status not in {"Needs allocation", "Historical backfill required"}:
        return status
    if _certificate_is_uploaded(row):
        return "Uploaded"
    lowered = status.casefold()
    if any(token in lowered for token in ("error", "failed", "missing template")):
        return "Upload failed"
    if _certificate_is_ready(row):
        return "Ready"
    return "Needs certificate"


def _prodigi_label(row):
    dispatch_status = _display_prodigi_status(row.get("prodigi_status"))
    if str(row.get("prodigi_status") or "").strip():
        return dispatch_status
    if not _certificate_is_ready(row):
        return "Needs certificate"
    if _certificate_is_uploaded(row):
        return "Ready to dispatch"
    return "Certificate ready"


def _can_start_prodigi(row):
    status = _prodigi_label(row)
    return status in {"Ready to dispatch", "Not started", "In progress", "Sent to Prodigi", "Complete", "Issue"}


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
    raw_edition = str(updated.get("edition") or updated.get("assignment_status") or "").strip()
    edition_number = _normalise_edition_number(
        updated.get("edition_number")
        or updated.get("edition")
        or updated.get("assigned_edition_number")
    )
    updated["order"] = str(updated.get("order") or "")
    updated["date"] = str(updated.get("date") or "")
    updated["customer"] = _placeholder_text(updated.get("customer"))
    updated["shipping_method"] = str(
        updated.get("shipping_method")
        or updated.get("shipping_title")
        or updated.get("shipping_line")
        or updated.get("shipping")
        or ""
    )
    updated["shipping"] = _display_shipping_label(updated.get("shipping_method"))
    updated["product"] = _placeholder_text(updated.get("product"))
    updated["variant_full"] = _display_variant_label(updated.get("variant") or updated.get("variant_title"))
    updated["variant"] = _compact_variant_label(updated.get("variant_full"))
    updated["edition_number"] = edition_number
    updated["edition_total"] = _coerce_positive_int(
        updated.get("edition_total")
        or updated.get("edition_limit")
        or updated.get("run_edition_total")
        or 0,
        default=0,
    )
    updated["edition"] = (
        _format_edition_with_total(edition_number, updated["edition_total"])
        if edition_number
        else raw_edition
        if raw_edition in ALLOCATION_BLOCKER_STATUSES and raw_edition not in {"Needs allocation", "Historical backfill required"}
        else "Needs edition"
    )
    updated["has_saved_allocation"] = bool(updated.get("has_saved_allocation"))
    updated["edition_offset"] = int(updated.get("edition_offset") or 0)
    updated["allocation_index"] = _coerce_positive_int(updated.get("allocation_index") or updated.get("line_item_unit_index") or 1, default=1)
    updated["line_quantity"] = int(updated.get("line_quantity") or 1)
    assignments = updated.get("assignments") if isinstance(updated.get("assignments"), list) else []
    updated["assignments_count"] = int(
        updated.get("assignments_count")
        or len(assignments)
        or (1 if updated.get("edition_order_id") else 0)
    )
    updated["shopify_order_id"] = str(updated.get("shopify_order_id") or "")
    updated["legacy_resource_id"] = str(updated.get("legacy_resource_id") or "")
    updated["shopify_line_item_id"] = str(updated.get("shopify_line_item_id") or "")
    updated["duplicate_allocation_warning"] = bool(
        updated.get("duplicate_allocation_warning")
        or (
            updated.get("shopify_line_item_id")
            and updated["assignments_count"] > max(updated["line_quantity"], 1)
        )
    )
    updated["shopify_product_id"] = str(updated.get("shopify_product_id") or "")
    updated["variant_id"] = str(updated.get("variant_id") or "")
    updated["product_handle"] = str(updated.get("product_handle") or updated.get("handle") or "")
    updated["shopify_customer_id"] = str(updated.get("shopify_customer_id") or updated.get("customer_id") or "")
    updated["customer_email"] = _placeholder_text(updated.get("customer_email"), missing="")
    updated["processed_at"] = str(updated.get("processed_at") or "")
    updated["created_at"] = str(updated.get("created_at") or "")
    updated["order_number_sort"] = int(updated.get("order_number_sort") or _parse_order_number(updated["order"]))
    updated["admin_url"] = str(updated.get("admin_url") or "")
    updated["edition_order_id"] = str(updated.get("edition_order_id") or "")
    updated["assignment_status"] = str(updated.get("assignment_status") or "")
    updated["prodigi_status"] = str(updated.get("prodigi_status") or "")
    updated["prodigi_row_id"] = str(updated.get("prodigi_row_id") or "")
    updated["certificate_id"] = str(updated.get("certificate_id") or "")
    updated["certificate_status"] = str(updated.get("certificate_status") or "")
    updated["certificate_pdf_path"] = str(updated.get("certificate_pdf_path") or "")
    updated["certificate_pdf_url"] = str(updated.get("certificate_pdf_url") or updated.get("shopify_file_url") or "")
    updated["certificate_shopify_file_id"] = str(updated.get("certificate_shopify_file_id") or "")
    updated["certificate_generated_at"] = str(updated.get("certificate_generated_at") or "")
    updated["certificate_error"] = str(updated.get("certificate_error") or "")
    updated["certificate_preview_path"] = str(updated.get("certificate_preview_path") or updated.get("preview_path") or "")
    updated["certificate"] = _certificate_label(updated)
    updated["certificate_tone"] = {
        "Uploaded": "uploaded",
        "Upload failed": "failed",
        "Ready": "ready",
        "Needs certificate": "muted",
    }.get(updated["certificate"], "default")
    updated["prodigi"] = _prodigi_label(updated)
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


def _load_snapshot_once(search="", *, force=False):
    query = str(search or "").strip()
    if (
        not force
        and st.session_state.get(SNAPSHOT_LOADED_KEY)
        and st.session_state.get(LOADED_QUERY_KEY, "") == query
        and not st.session_state.get(LOAD_ERROR_KEY)
    ):
        print(f"Orders load cached rows: {len(st.session_state.get(ROWS_KEY) or [])}", flush=True)
        print("Shopify fetch skipped on initial load", flush=True)
        print("Allocation skipped on initial load", flush=True)
        print("Metafield sync skipped on initial load", flush=True)
        print("Certificate status load skipped on initial load", flush=True)
        return
    start = time.perf_counter()
    try:
        payload = _read_orders_snapshot(search=query, limit=DEFAULT_VISIBLE_ROW_LIMIT)
    except Exception as error:
        _record_snapshot_load_error(error, query)
        _perf_log("load snapshot failed", start)
        return
    st.session_state[LOAD_ERROR_KEY] = ""
    _apply_snapshot_payload(payload)
    st.session_state[LOADED_QUERY_KEY] = query
    st.session_state[SNAPSHOT_LOADED_KEY] = True
    _perf_log("load snapshot", start, rows=len(st.session_state[ROWS_KEY]))
    print("Orders load persisted rows: {:.0f} ms".format((time.perf_counter() - start) * 1000), flush=True)
    print("Shopify fetch skipped on initial load", flush=True)
    print("Allocation skipped on initial load", flush=True)
    print("Metafield sync skipped on initial load", flush=True)
    print("Certificate status load skipped on initial load", flush=True)


def _apply_snapshot_payload(payload):
    payload = payload or {"rows": [], "source": "local_snapshot", "row_count": 0}
    st.session_state[ROWS_KEY] = _sort_rows(payload.get("rows") or [])
    st.session_state[META_KEY] = {
        "last_refreshed": payload.get("last_refreshed") or "",
        "saved_at": payload.get("saved_at") or "",
        "last_synced": payload.get("last_synced") or payload.get("last_refreshed") or "",
        "order_count": payload.get("order_count") or 0,
        "row_count": payload.get("row_count") or len(payload.get("rows") or []),
        "source": payload.get("source") or "local_snapshot",
        "error": payload.get("error") or "",
        "database_read": dict(payload.get("database_read") or {}),
        "search": str(payload.get("search") or ""),
    }


def _reload_orders_from_source():
    query = str(st.session_state.get(LOADED_QUERY_KEY) or "").strip()
    payload = _read_orders_snapshot(search=query, limit=DEFAULT_VISIBLE_ROW_LIMIT)
    _apply_snapshot_payload(payload)
    st.session_state[LOADED_QUERY_KEY] = query
    st.session_state[SNAPSHOT_LOADED_KEY] = True


def _certificate_action_in_progress():
    _clear_stale_certificate_action_state(source="Orders")
    state = st.session_state.get(CERTIFICATE_ACTION_STATE_KEY) or {}
    return bool(st.session_state.get(CERTIFICATE_ACTION_LOADING_KEY) or state.get("order_key"))


def _orders_supabase_visibility_marker():
    backend = _configured_supabase_backend()
    if not backend or not hasattr(backend, "orders_visibility_marker"):
        return ""
    marker = backend.orders_visibility_marker(ensure_schema_first=False)
    return str((marker or {}).get("marker") or "").strip()


def _check_orders_supabase_live_refresh():
    if _certificate_action_in_progress():
        return
    try:
        marker = _orders_supabase_visibility_marker()
    except Exception as error:
        print(f"ORDERS SYNC: orders_page_live_refresh_check_failed status=failed error={error}", flush=True)
        return
    if not marker:
        return
    previous = str(st.session_state.get(ORDERS_SUPABASE_LIVE_MARKER_KEY) or "").strip()
    if not previous:
        st.session_state[ORDERS_SUPABASE_LIVE_MARKER_KEY] = marker
        return
    if marker == previous:
        return
    print(
        "ORDERS SYNC: orders_page_live_refresh_detected_change "
        f"status=completed old_marker={previous} new_marker={marker}",
        flush=True,
    )
    st.session_state[ORDERS_SUPABASE_LIVE_MARKER_KEY] = marker
    _reload_orders_from_source()
    print("ORDERS SYNC: orders_snapshot_invalidated source=supabase_live_refresh", flush=True)
    st.rerun()


def _render_orders_supabase_live_refresh():
    fragment = getattr(st, "fragment", None)
    if callable(fragment):
        @fragment(run_every=f"{ORDERS_SUPABASE_LIVE_CHECK_SECONDS}s")
        def _orders_live_refresh_fragment():
            _check_orders_supabase_live_refresh()

        _orders_live_refresh_fragment()
    else:
        _check_orders_supabase_live_refresh()


def _order_match_tokens(row):
    normalised = _normalise_row(row)
    return {
        str(normalised.get("order") or "").strip(),
        str(normalised.get("shopify_order_id") or "").strip(),
    }


def _sync_result_visible_refresh_needed(result):
    if not result:
        return False
    return bool(
        int(result.get("new_orders_inserted") or 0)
        or int(result.get("new_lines_inserted") or 0)
        or int(result.get("edition_allocations_created") or 0)
        or result.get("affected_order_names")
        or result.get("affected_shopify_order_ids")
    )


def _affected_rows_count(result):
    names = {str(value or "").strip() for value in (result or {}).get("affected_order_names") or [] if str(value or "").strip()}
    ids = {str(value or "").strip() for value in (result or {}).get("affected_shopify_order_ids") or [] if str(value or "").strip()}
    if not names and not ids:
        return 0
    count = 0
    for row in st.session_state.get(ROWS_KEY, []) or []:
        tokens = _order_match_tokens(row)
        if tokens & names or tokens & ids:
            count += 1
    return count


def _refresh_visible_rows_after_sync(result):
    start = time.perf_counter()
    print("ORDERS SYNC: orders_visible_rows_refresh_started status=started", flush=True)
    print("ORDERS SYNC: snapshot_cache_invalidated yes", flush=True)
    st.session_state[SNAPSHOT_LOADED_KEY] = False
    _reload_orders_from_source()
    merged_count = _affected_rows_count(result)
    print(
        "ORDERS SYNC: orders_visible_rows_refresh_completed "
        f"status=completed duration_ms={int((time.perf_counter() - start) * 1000)} "
        f"affected_rows_merged_count={merged_count}",
        flush=True,
    )
    print(f"ORDERS SYNC: affected_rows_merged_count {merged_count}", flush=True)
    return merged_count


def _run_sync_with_timeout(callable_):
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(callable_)
    try:
        result = future.result(timeout=ORDERS_SYNC_TIMEOUT_SECONDS)
        executor.shutdown(wait=True)
        return result
    except FutureTimeoutError as error:
        future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)
        message = "Orders sync failed: sync timed out at backend_sync. You can retry."
        print(
            "ORDERS SYNC: orders_sync_failed status=failed "
            f"last_stage_on_timeout=backend_sync timeout_seconds={ORDERS_SYNC_TIMEOUT_SECONDS}",
            flush=True,
        )
        raise TimeoutError(message) from error


def _write_snapshot(rows, meta=None):
    sorted_rows = _sort_rows(rows)
    payload = order_allocator.save_orders_snapshot(
        sorted_rows,
        meta=meta or st.session_state.get(META_KEY) or {},
    )
    st.session_state[META_KEY] = {
        "last_refreshed": (meta or {}).get("last_refreshed") or payload.get("last_refreshed") or "",
        "saved_at": payload.get("saved_at") or "",
        "last_synced": (meta or {}).get("last_synced") or payload.get("last_synced") or payload.get("last_refreshed") or "",
        "order_count": (meta or {}).get("order_count") or payload.get("order_count") or 0,
        "row_count": (meta or {}).get("row_count") or payload.get("row_count") or len(payload.get("rows") or []),
        "source": (meta or {}).get("source") or payload.get("source") or "local_snapshot",
        "error": (meta or {}).get("error") or "",
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


def _refresh_orders(*, latest_paid_only=True, max_orders=50, backfill_latest_paid=False, reload_table=False):
    total_started = time.perf_counter()
    backend = _configured_supabase_backend()
    if not backend:
        st.session_state[NOTICE_KEY] = "Supabase is not configured. Stage 4B sync cannot run from local fallback mode."
        return
    sync_started = time.perf_counter()
    try:
        def run_backend_sync():
            if latest_paid_only:
                return backend.sync_latest_paid_orders_to_supabase(
                    limit=max_orders,
                    backfill_latest_paid=backfill_latest_paid,
                    ensure_schema_first=False,
                )
            return backend.sync_shopify_orders_to_supabase(
                max_orders=max_orders,
                generate_certificates=False,
                sync_product_metafields=False,
            )

        result = _run_sync_with_timeout(run_backend_sync)
    except Exception as error:
        message = str(error) or "Orders sync failed."
        if not message.startswith("Orders sync failed:") and "missing required database schema" not in message:
            message = f"Orders sync failed: {message}"
        st.session_state[NOTICE_KEY] = message
        print(f"ORDERS SYNC: orders_sync_failed status=failed error={message}", flush=True)
        print("ORDERS SYNC: loading_state_cleared status=completed", flush=True)
        return
    print(
        "PERF Sync Orders: backend sync returned "
        f"elapsed_ms={int((time.perf_counter() - sync_started) * 1000)} "
        f"mode={result.get('mode') or ('latest_paid' if latest_paid_only else 'incremental')} "
        f"orders={int(result.get('shopify_orders_fetched') or result.get('orders_seen') or 0)} "
        f"new_orders={int(result.get('new_orders_inserted') or 0)}",
        flush=True,
    )
    st.session_state[SYNC_RESULT_KEY] = result
    if result.get("sync_blocked"):
        st.session_state[NOTICE_KEY] = result.get("block_reason") or "Orders sync blocked before allocation."
        print("ORDERS SYNC: snapshot_cache_invalidated no", flush=True)
        return
    cache_started = time.perf_counter()
    refresh_needed = reload_table or _sync_result_visible_refresh_needed(result)
    affected_rows_merged_count = 0
    if refresh_needed:
        try:
            affected_rows_merged_count = _refresh_visible_rows_after_sync(result)
            result["affected_rows_merged_count"] = affected_rows_merged_count
            reload_mode = "full" if reload_table else "refreshed"
        except Exception as refresh_error:
            reload_mode = "refresh failed"
            result["visible_refresh_error"] = str(refresh_error)
            print(
                "ORDERS SYNC: orders_visible_rows_refresh_failed "
                f"status=failed error={refresh_error}",
                flush=True,
            )
    else:
        print("ORDERS SYNC: snapshot_cache_invalidated no", flush=True)
        reload_mode = "deferred"
    print(
        "PERF Sync Orders: cache rebuild time "
        f"elapsed_ms={int((time.perf_counter() - cache_started) * 1000)} "
        f"mode={reload_mode}",
        flush=True,
    )
    mode_label = "Backfill" if backfill_latest_paid else "Cursor check"
    notice_parts = [
        f"{mode_label} complete. Shopify fetched: {int(result.get('shopify_orders_fetched') or 0)} orders",
        f"New orders imported: {int(result.get('new_orders_inserted') or 0)}",
        f"Existing orders preserved/skipped: {int(result.get('existing_orders_skipped') or 0)}",
        f"Existing allocation units skipped: {int(result.get('existing_allocation_units_skipped') or result.get('existing_assignments_skipped') or 0)}",
        f"Edition numbers assigned: {int(result.get('edition_allocations_created') or 0)}",
        f"Duplicate-risk units blocked: {int(result.get('duplicate_risk_units_blocked') or 0)}",
        f"Missing product mapping: {int(result.get('missing_mapping_skipped') or 0)}",
        f"Errors: {len(result.get('errors') or [])}",
    ]
    if not int(result.get("shopify_orders_fetched") or 0) and result.get("empty_fetch_reason"):
        notice_parts.append(f"Reason: {result.get('empty_fetch_reason')}")
    if result.get("cursor_warning"):
        notice_parts.append(f"Warning: {result.get('cursor_warning')}")
    st.session_state[NOTICE_KEY] = (
        " | ".join(notice_parts) + ". "
        f"Table refresh: {reload_mode}."
    )
    print(
        "PERF Sync Orders: total sync time "
        f"elapsed_ms={int((time.perf_counter() - total_started) * 1000)} "
        "streamlit_rerun_trigger=after_button_handler",
        flush=True,
    )
    print("ORDERS SYNC: loading_state_cleared status=completed", flush=True)


def _backfill_missing_order_details(*, dry_run=True, limit=100):
    backend = _configured_supabase_backend()
    if not backend:
        st.session_state[NOTICE_KEY] = "Supabase is not configured. Shopify detail backfill cannot run from local fallback mode."
        return
    result = backend.backfill_missing_shopify_order_details(limit=limit, dry_run=dry_run)
    st.session_state[BACKFILL_RESULT_KEY] = result
    if not dry_run:
        _reload_orders_from_source()
    mode_label = "Dry-run" if dry_run else "Backfill applied"
    st.session_state[NOTICE_KEY] = (
        f"{mode_label}: {int(result.get('orders_updated') or 0)} order(s) with missing details "
        f"and {int(result.get('variant_rows_filled') or 0)} variant row(s) improved."
    )


def _preview_latest_paid_orders(*, limit=50):
    total_started = time.perf_counter()
    backend = _configured_supabase_backend()
    if not backend:
        st.session_state[NOTICE_KEY] = "Supabase is not configured. Latest Shopify fetch preview is unavailable."
        return
    result = backend.preview_latest_paid_orders_sync(limit=limit)
    print(
        "PERF Sync Orders: preview backend returned "
        f"elapsed_ms={int((time.perf_counter() - total_started) * 1000)} "
        f"orders={int(result.get('shopify_orders_fetched') or 0)} "
        f"new_orders={int(result.get('new_orders_inserted') or 0)}",
        flush=True,
    )
    st.session_state[LATEST_FETCH_PREVIEW_KEY] = result
    st.session_state[NOTICE_KEY] = (
        f"Fetched preview for {int(result.get('shopify_orders_fetched') or 0)} latest paid Shopify order(s)."
    )


def _repair_missing_editions(*, dry_run=True, limit=100):
    backend = _configured_supabase_backend()
    if not backend:
        st.session_state[NOTICE_KEY] = "Supabase is not configured. Missing-edition repair is unavailable."
        return
    if dry_run:
        result = backend.preview_missing_edition_repairs(limit=limit)
    else:
        result = backend.repair_missing_edition_orders(limit=limit)
        _reload_orders_from_source()
    st.session_state[REPAIR_RESULT_KEY] = result
    st.session_state[NOTICE_KEY] = (
        f"{'Previewed' if dry_run else 'Applied'} missing-edition repair for "
        f"{int(result.get('candidate_rows') or 0)} ledger row(s)."
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
        "customer_email": st.column_config.TextColumn("Email", width="medium"),
        "edition": st.column_config.TextColumn("Edition", width="small"),
        "edition_total": st.column_config.NumberColumn("Edition total", width="small"),
        "certificate": st.column_config.TextColumn("Certificate status", width="small"),
        "shipping": st.column_config.TextColumn("Shipping summary", width="large"),
        "product": st.column_config.TextColumn("Product", width="large"),
        "variant": st.column_config.TextColumn("Variant", width="large"),
        "admin_url": st.column_config.LinkColumn("Open Admin", display_text="Open"),
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


def _generate_certificate_for_row(row, *, raise_errors=False):
    backend = _configured_supabase_backend()
    config = shopify_sync.get_config()
    row = _normalise_row(row)
    try:
        if not row.get("edition_number"):
            raise ValueError("This row still needs an edition number before a certificate can be generated.")
        if not row.get("edition_order_id"):
            raise ValueError("This row is missing its Supabase edition record. Ask a developer to repair missing editions first.")
        if backend:
            generated_path = backend.generate_certificate_for_edition_order(row.get("edition_order_id"))
            generated_path = str(generated_path or "").strip()
            updates = {
                "certificate_status": "Generated",
                "certificate_pdf_path": row.get("certificate_pdf_path") or "",
                "certificate_error": "",
            }
            if generated_path.startswith(("http://", "https://")):
                updates["certificate_pdf_url"] = generated_path
            elif generated_path and Path(generated_path).exists():
                updates["certificate_pdf_path"] = generated_path
            updates["certificate"] = _certificate_label({**row, **updates})
            _update_matching_row(row, updates)
            refreshed = _current_row_for(row)
            st.session_state[NOTICE_KEY] = (
                f"Generated certificate for {refreshed.get('order')} {refreshed.get('edition')}."
            )
            return True
        if not config.get("configured"):
            message = "Store connection is not configured yet. Ask a developer before generating certificates."
            st.session_state[NOTICE_KEY] = message
            if raise_errors:
                raise RuntimeError(message)
            return False
        if not row.get("has_saved_allocation"):
            raise ValueError("This order needs an edition allocation before generating a certificate.")
        existing = _existing_uploaded_certificate(row, config)
        if existing:
            record = {**certificate_engine.certificate_record_from_order_row(row), **existing, "status": "Uploaded"}
            _update_row_from_certificate(row, record)
            st.session_state[NOTICE_KEY] = f"Certificate already uploaded for {row.get('order')} {row.get('edition')}."
            return True
        record = certificate_engine.certificate_record_from_order_row(row)
        generated = certificate_engine.generate_local_certificate_for_record(record)
        _update_row_from_certificate(row, generated)
        if generated.get("status") == "Generated":
            st.session_state[NOTICE_KEY] = f"Generated certificate for {row.get('order')} {row.get('edition')}."
            return True
        else:
            message = generated.get("sync_error") or "Certificate generation needs review."
            st.session_state[NOTICE_KEY] = message
            if raise_errors:
                raise RuntimeError(message)
            return False
    except Exception as error:
        _update_matching_row(row, {"certificate_status": "Error", "certificate_error": str(error), "certificate": "Error"})
        st.session_state[NOTICE_KEY] = f"Certificate generation failed: {error}"
        if raise_errors:
            raise
        return False


def _upload_certificate_for_row(row, *, raise_errors=False):
    backend = _configured_supabase_backend()
    config = shopify_sync.get_config()
    if not config.get("configured"):
        message = "Store connection is not configured yet. Ask a developer before uploading certificates."
        st.session_state[NOTICE_KEY] = message
        if raise_errors:
            raise RuntimeError(message)
        return False
    row = _normalise_row(row)
    try:
        if not row.get("edition_number"):
            raise ValueError("This row still needs an edition number before a certificate can be uploaded.")
        if not row.get("edition_order_id"):
            raise ValueError("This row is missing its Supabase edition record. Ask a developer to repair missing editions first.")
        existing = _existing_uploaded_certificate(row, config)
        if existing:
            record = {**certificate_engine.certificate_record_from_order_row(row), **existing, "status": "Uploaded"}
            _update_row_from_certificate(row, record)
            st.session_state[NOTICE_KEY] = f"Certificate already uploaded for {row.get('order')} {row.get('edition')}."
            return True
        if backend and not str(row.get("certificate_pdf_path") or "").strip():
            generated_path = backend.generate_certificate_for_edition_order(row.get("edition_order_id"))
            generated_path = str(generated_path or "").strip()
            updates = {
                "certificate_status": "Generated",
                "certificate_pdf_path": row.get("certificate_pdf_path") or "",
                "certificate_error": "",
            }
            if generated_path.startswith(("http://", "https://")):
                updates["certificate_pdf_url"] = generated_path
            elif generated_path and Path(generated_path).exists():
                updates["certificate_pdf_path"] = generated_path
            updates["certificate"] = _certificate_label({**row, **updates})
            _update_matching_row(row, updates)
            row = _current_row_for(row)
        record = certificate_engine.certificate_record_from_order_row(row)
        record["local_pdf_path"] = row.get("certificate_pdf_path") or record.get("local_pdf_path") or ""
        if not record.get("local_pdf_path"):
            record = certificate_engine.generate_local_certificate_for_record(record)
        uploaded = certificate_engine.upload_generated_certificate_record(record, config=config)
        saved = certificate_engine.save_certificate_record_to_order(uploaded, config=config)
        _update_row_from_certificate(row, saved.get("record") or uploaded)
        if saved.get("metafields_synced") is False:
            st.session_state[NOTICE_KEY] = (
                f"Uploaded certificate for {row.get('order')} {row.get('edition')}, "
                "but the Shopify mirror failed and needs retry."
            )
        else:
            st.session_state[NOTICE_KEY] = f"Uploaded certificate for {row.get('order')} {row.get('edition')}."
        return True
    except Exception as error:
        _update_matching_row(row, {"certificate_status": "Upload failed", "certificate_error": str(error), "certificate": "Upload failed"})
        st.session_state[NOTICE_KEY] = f"Certificate upload failed: {error}"
        if raise_errors:
            raise
        return False


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


def _search_blob(row):
    normalised = _normalise_row(row)
    fields = (
        normalised.get("order"),
        normalised.get("customer"),
        normalised.get("product"),
        normalised.get("variant"),
        normalised.get("variant_full"),
        normalised.get("edition"),
    )
    return " ".join(str(value or "").casefold() for value in fields)


def _filter_rows(rows, search_text):
    query = str(search_text or "").strip().casefold()
    if not query:
        return [_normalise_row(row) for row in rows or []]
    return [row for row in [_normalise_row(item) for item in rows or []] if query in _search_blob(row)]


def _open_prodigi_for_row(row):
    target_order = str((row or {}).get("order") or "").strip()
    if not target_order:
        st.session_state[NOTICE_KEY] = "Select one order row first."
        return
    st.session_state["selected_page"] = "Prodigi"
    st.session_state["prodigi_dispatch_autoload_query"] = target_order
    st.session_state["prodigi-dispatch-order-search"] = target_order


def _selected_admin_url(rows):
    for row in rows or []:
        admin_url = str((_normalise_row(row)).get("admin_url") or "").strip()
        if admin_url:
            return admin_url
    return ""


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
        return False
    for row in rows:
        normalised = _normalise_row(row)
        if not (normalised.get("order") or normalised.get("shopify_order_id")):
            message = "Selected order row is missing its order identity. You can retry after refreshing the row."
            st.session_state[NOTICE_KEY] = message
            st.error(message)
            return False
    start = time.perf_counter()
    completed = 0
    try:
        for row in rows:
            _set_certificate_action_state(row, source="Orders")
            _certificate_action_log("certificate action started", row=row, source="Orders")
            result = certificate_job.run_certificate_job_with_timeout(row, source_page="Orders", upload=True)
            if not result.get("ok"):
                raise RuntimeError(result.get("error") or "Certificate upload failed.")
            record = result.get("record") or {}
            if record:
                _update_row_from_certificate(row, record)
            _certificate_action_log("row refresh started", row=row, source="Orders")
            certificate_stage_log(
                "selected_row_refresh",
                "started",
                source_page="Orders",
                order_name=_normalise_row(row).get("order") or "",
                edition_order_id=_normalise_row(row).get("edition_order_id") or "",
            )
            refreshed_row = _current_row_for(row)
            certificate_stage_log(
                "selected_row_refresh",
                "completed",
                source_page="Orders",
                order_name=refreshed_row.get("order") or "",
                edition_order_id=refreshed_row.get("edition_order_id") or "",
            )
            _certificate_action_log("row refresh finished", row=refreshed_row, source="Orders")
            _certificate_action_log("certificate action finished", row=row, source="Orders")
            completed += 1
        _perf_log("generate selected certificates", start, rows=len(rows), mode="generate_upload")
        _perf_log("upload selected certificates", start, rows=len(rows), mode="generate_upload")
        st.session_state[NOTICE_KEY] = f"Generated and uploaded {len(rows)} selected certificate(s)."
        return True
    except Exception as error:
        _certificate_action_log("certificate action failed", row=rows[completed] if completed < len(rows) else None, source="Orders", error=error)
        message = f"Certificate upload failed: {error}. You can retry this order."
        st.session_state[NOTICE_KEY] = message
        st.error(message)
        return False
    finally:
        _clear_certificate_action_state(source="Orders")


def _duplicate_diagnostics_snapshot(limit=10):
    backend = _configured_supabase_backend()
    if not backend or not hasattr(backend, "edition_allocation_duplicate_diagnostics"):
        return {
            "available": False,
            "duplicate_group_count": 0,
            "duplicate_row_count": 0,
            "sync_allowed": False,
            "blocked_reasons": ["Supabase duplicate diagnostics are unavailable"],
            "groups": [],
        }
    try:
        return backend.edition_allocation_duplicate_diagnostics(limit=limit)
    except Exception as error:
        return {
            "error": str(error),
            "available": False,
            "duplicate_group_count": 0,
            "duplicate_row_count": 0,
            "sync_allowed": False,
            "blocked_reasons": ["Supabase duplicate diagnostics failed"],
            "groups": [],
        }


def _render_duplicate_warning_panel(duplicates):
    return


def _render_top_actions(rows, duplicate_diagnostics=None):
    selected_rows = _selected_rows_from_state(rows)
    selected_count = len(selected_rows)
    open_url = _first_pdf_url(selected_rows)
    locked_help = "Locked until Stage 4B/Certificate stage"
    backend = _configured_supabase_backend()
    stage4b_enabled = st.checkbox(
        "Enable Stage 4B order sync controls",
        key=SYNC_ENABLE_KEY,
        help="Required before any dry-run or apply action can run.",
    )
    dry_run_only = st.checkbox(
        "Dry run only — show what would be imported.",
        key=SYNC_DRY_RUN_KEY,
        value=True,
    )
    sync_confirmed = st.checkbox(
        "I understand this will import new paid Shopify orders into Supabase.",
        key=SYNC_CONFIRM_KEY,
        disabled=dry_run_only,
    )
    backfill_confirmed = st.checkbox(
        "I understand this will backfill missing Shopify order details in Supabase.",
        key=BACKFILL_CONFIRM_KEY,
        disabled=dry_run_only,
    )

    sync_disabled = (not backend) or (not stage4b_enabled) or (not dry_run_only and not sync_confirmed)
    backfill_disabled = (not backend) or (not stage4b_enabled) or (not dry_run_only and not backfill_confirmed)

    action_cols = st.columns([1.2, 1.55, 1.55, 1.45, 1.55, 1.2])
    if action_cols[0].button("Sync New Orders", type="primary", use_container_width=True, disabled=sync_disabled):
        with st.spinner("Reviewing new paid Shopify orders..."):
            _refresh_orders(dry_run=dry_run_only)
        st.rerun()
    if action_cols[1].button(
        "Backfill Missing Details",
        use_container_width=True,
        disabled=backfill_disabled,
    ):
        with st.spinner("Reviewing missing Shopify order details..."):
            _backfill_missing_order_details(dry_run=dry_run_only)
        st.rerun()
    if action_cols[2].button(
        "Generate Selected Certificates",
        use_container_width=True,
        disabled=True,
        help=locked_help,
    ):
        with st.spinner("Generating selected certificates..."):
            _generate_selected_certificates(selected_rows)
        st.rerun()
    if action_cols[3].button(
        "Upload Selected to Shopify",
        use_container_width=True,
        disabled=True,
        help=locked_help,
    ):
        with st.spinner("Uploading selected certificates..."):
            _upload_selected_certificates(selected_rows)
        st.rerun()
    if action_cols[4].button(
        "Generate + Upload Selected",
        use_container_width=True,
        disabled=True,
        help=locked_help,
    ):
        with st.spinner("Generating and uploading selected certificates..."):
            _generate_upload_selected_certificates(selected_rows)
        st.rerun()
    if open_url:
        action_cols[5].link_button("Open Selected PDF", open_url, use_container_width=True)
    else:
        action_cols[5].button("Open Selected PDF", use_container_width=True, disabled=True, help=locked_help)
    st.caption(f"{selected_count} row(s) selected. Tip: scroll sideways to view all fulfilment fields.")
    if not backend:
        st.caption("Supabase ledger is not available in this runtime, so Stage 4B sync controls stay disabled.")
    elif not stage4b_enabled:
        st.caption("Sync and backfill stay disabled until the Stage 4B control flag is enabled.")
    elif dry_run_only:
        st.caption("Dry-run mode is active. No Supabase writes or Shopify updates will be made.")
    else:
        st.caption("Apply mode is armed. Only Supabase ledger rows will be written; Shopify remains read-only here.")


def _render_stage4b_result(title, result):
    if not result:
        return
    expander = getattr(st, "expander", None)
    if not expander:
        return
    with expander(title, expanded=False):
        for label, key in (
            ("Mode", "mode"),
            ("Shopify orders fetched", "shopify_orders_fetched"),
            ("Existing orders skipped", "existing_orders_skipped"),
            ("New orders inserted", "new_orders_inserted"),
            ("New lines inserted", "new_lines_inserted"),
            ("Edition allocations created", "edition_allocations_created"),
            ("Existing allocations preserved", "existing_allocations_preserved"),
            ("Missing mapping skipped", "missing_mapping_skipped"),
            ("Historical orders skipped", "historical_orders_skipped"),
            ("Orders updated", "orders_updated"),
            ("Variant rows filled", "variant_rows_filled"),
            ("Shipping rows filled", "shipping_rows_filled"),
            ("Email rows filled", "email_rows_filled"),
        ):
            if key in result:
                st.caption(f"{label}: {result.get(key)}")
        errors = result.get("errors") or []
        if errors:
            st.caption(f"Errors: {len(errors)}")
            for error in errors[:5]:
                st.caption(f"- {error}")


def _missing_data_counts(rows):
    counts = {
        "missing_variant": 0,
        "missing_shipping": 0,
        "missing_customer": 0,
        "missing_product": 0,
        "missing_edition_number": 0,
    }
    for row in [_normalise_row(item) for item in (rows or [])]:
        if row.get("variant") == "Missing from ledger":
            counts["missing_variant"] += 1
        if row.get("shipping") == "Missing from ledger":
            counts["missing_shipping"] += 1
        if row.get("customer") == "Missing from ledger":
            counts["missing_customer"] += 1
        if row.get("product") == "Missing from ledger":
            counts["missing_product"] += 1
        if not row.get("edition_number"):
            counts["missing_edition_number"] += 1
    return counts


def _render_missing_data_diagnostics(rows):
    counts = _missing_data_counts(rows)
    expander = getattr(st, "expander", None)
    if not expander:
        return
    with expander("Orders read completeness diagnostics", expanded=False):
        st.caption(f"Rows with missing variant: {counts['missing_variant']}")
        st.caption(f"Rows with missing shipping: {counts['missing_shipping']}")
        st.caption(f"Rows with missing customer: {counts['missing_customer']}")
        st.caption(f"Rows with missing product title: {counts['missing_product']}")
        st.caption(f"Rows with missing edition number: {counts['missing_edition_number']}")


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
        backend = _configured_supabase_backend()
        if backend and hasattr(backend, "edition_allocation_duplicate_diagnostics"):
            try:
                duplicates = backend.edition_allocation_duplicate_diagnostics(limit=10)
                duplicate_groups = int(duplicates.get("duplicate_group_count") or 0)
                duplicate_rows = int(duplicates.get("duplicate_row_count") or 0)
                st.caption(f"duplicate allocation groups: {duplicate_groups}")
                st.caption(f"duplicate-risk edition rows: {duplicate_rows}")
                if duplicate_groups:
                    st.warning("Duplicate allocation warning: review duplicate diagnostics before running more allocation syncs.")
                    for group in (duplicates.get("groups") or [])[:5]:
                        st.caption(
                            f"{group.get('shopify_order_name') or group.get('shopify_order_id')}: "
                            f"{group.get('product_title') or group.get('shopify_handle')} / "
                            f"{group.get('variant_title') or 'variant not shown'} - "
                            f"{int(group.get('actual_allocation_count') or 0)} allocation rows"
                        )
            except Exception as error:
                st.caption(f"Duplicate allocation diagnostics unavailable: {error}")


def _display_rows(rows):
    output = []
    for row in [_normalise_row(item) for item in rows or []]:
        display_row = {column: row.get(column, "") for column in VISIBLE_COLUMNS}
        if display_row.get("order"):
            display_row["order"] = f"{COPY_ORDER_ICON} {display_row['order']}"
        output.append(display_row)
    return output


def _order_copy_click_handler_html():
    return f"""
<script>
(() => {{
  const icon = {json.dumps(COPY_ORDER_ICON)};
  const marker = "sports-cave-order-copy-handler";
  const parentWindow = window.parent || window;
  const doc = parentWindow.document;
  if (doc.body.dataset[marker] === "1") return;
  doc.body.dataset[marker] = "1";

  function cleanOrder(text) {{
    return String(text || "").replace(icon, "").trim();
  }}

  function copyOrder(value) {{
    const clipboard = parentWindow.navigator && parentWindow.navigator.clipboard;
    if (!value || !clipboard) return;
    clipboard.writeText(value);
  }}

  doc.addEventListener("click", (event) => {{
    const target = event.target;
    const cell = target && target.closest ? target.closest('[role="gridcell"], [data-testid="stDataFrameCell"]') : null;
    if (!cell) return;
    const text = cell.textContent || "";
    if (!text.includes(icon)) return;
    const rect = cell.getBoundingClientRect();
    if (event.clientX - rect.left > 28) return;
    const orderNumber = cleanOrder(text);
    if (!/^#?SC\\d+/i.test(orderNumber)) return;
    event.preventDefault();
    event.stopPropagation();
    copyOrder(orderNumber);
  }}, true);

  doc.addEventListener("mouseover", (event) => {{
    const cell = event.target && event.target.closest ? event.target.closest('[role="gridcell"], [data-testid="stDataFrameCell"]') : null;
    if (!cell || !(cell.textContent || "").includes(icon)) return;
    cell.title = "Copy order number";
    cell.style.cursor = "copy";
  }}, true);
}})();
</script>
"""


def _render_order_copy_click_handler():
    if getattr(st, "__name__", "") != "streamlit":
        return
    components.html(_order_copy_click_handler_html(), height=0, width=0)


def _column_config():
    return {
        "order": st.column_config.TextColumn("Order", width="small"),
        "edition": st.column_config.TextColumn("Edition", width="small"),
        "certificate": st.column_config.TextColumn("Certificate", width="small"),
        "customer": st.column_config.TextColumn("Customer", width="medium"),
        "product": st.column_config.TextColumn("Product", width="medium"),
        "variant": st.column_config.TextColumn("Variant", width="small"),
        "shipping": st.column_config.TextColumn("Shipping", width="small"),
        "date": st.column_config.TextColumn("Date", width="small"),
        "prodigi": st.column_config.TextColumn("Prodigi", width="small"),
    }


def _display_table_payload(rows):
    display_rows = _display_rows(rows)
    if pd is None or getattr(st, "__name__", "") != "streamlit":
        return display_rows
    frame = pd.DataFrame(display_rows, columns=VISIBLE_COLUMNS)
    def row_style(row):
        if row.get("certificate") == "Uploaded" and row.get("prodigi") == "Complete":
            return ["background-color: rgba(47, 158, 68, 0.14); color: #123c24;" for _ in row]
        return ["" for _ in row]

    return frame.style.apply(row_style, axis=1).map(
        lambda value: (
            "color: #2f9e44; font-weight: 600;"
            if value == "Uploaded"
            else "color: #c92a2a; font-weight: 600;"
            if value == "Upload failed"
            else "color: #2f9e44; font-weight: 600;"
            if value == "Complete"
            else "color: #495057;"
            if value == "Needs certificate"
            else "color: #1d4ed8; font-weight: 500;"
            if value == "Ready"
            else ""
        ),
        subset=["certificate", "prodigi"],
    )


def _render_top_actions(rows, duplicate_diagnostics=None):
    selected_rows = _selected_rows_from_state(rows)
    selected_count = len(selected_rows)
    backend = _configured_supabase_backend()
    open_url = _first_pdf_url(selected_rows)
    can_dispatch = selected_count == 1 and _can_start_prodigi(selected_rows[0]) if selected_rows else False
    can_generate = selected_count > 0 and all(_normalise_row(row).get("edition_number") for row in selected_rows)
    can_upload = can_generate
    upload_label = "Reupload Certificate" if selected_rows and all(_certificate_is_uploaded(row) for row in selected_rows) else "Generate + Upload Certificate"
    st.session_state[ORDER_SYNC_BACKFILL_KEY] = False
    action_cols = st.columns([1.35, 1.15, 1.4, 1.15, 1.35, 1.2])
    if action_cols[1].button(
        "Preview Certificate",
        use_container_width=True,
        disabled=not can_generate,
    ):
        with st.spinner("Generating selected certificates..."):
            _generate_selected_certificates(selected_rows)
        st.rerun()
    if action_cols[2].button(
        upload_label,
        use_container_width=True,
        disabled=not can_upload,
    ):
        with st.spinner("Generating and uploading selected certificates..."):
            certificate_action_ok = _generate_upload_selected_certificates(selected_rows)
        if certificate_action_ok:
            st.rerun()
    if open_url:
        action_cols[3].link_button("Open Certificate", open_url, use_container_width=True)
    else:
        action_cols[3].button("Open Certificate", use_container_width=True, disabled=True)
    if action_cols[4].button(
        "Start Prodigi QA",
        use_container_width=True,
        disabled=not can_dispatch,
    ):
        _open_prodigi_for_row(selected_rows[0])
        st.rerun()
    action_cols[5].caption(f"{selected_count} selected")
    if not backend:
        st.caption("Orders are temporarily unavailable.")
    if selected_rows and not can_generate:
        st.caption("Assign edition number before certificate generation.")


def _render_sync_diagnostics(result):
    if not result:
        return

    def compact_metafields(rows):
        by_key = {
            str(row.get("key") or ""): str(row.get("value") or "")
            for row in rows or []
        }
        parts = [
            f"{key}={by_key[key]}"
            for key in (
                "edition_next_number",
                "edition_remaining",
                "edition_total",
                "edition_sold_count",
            )
            if key in by_key
        ]
        return "; ".join(parts)

    query_parameters = result.get("query_parameters") or {}
    mode = "backfill" if result.get("backfill_latest_paid") else "cursor"
    cursor_used = result.get("sync_from") or ""
    newest_processed = result.get("newest_shopify_updated_at_processed") or ""
    with st.expander("Sync diagnostics", expanded=False):
        if result.get("sync_blocked"):
            st.caption(f"blocked: {result.get('block_reason') or 'Duplicate allocation risk detected.'}")
        duplicate_diagnostics = result.get("duplicate_diagnostics") or {}
        if duplicate_diagnostics:
            st.caption(
                "duplicate allocation warning: "
                f"{int(duplicate_diagnostics.get('duplicate_group_count') or 0)} group(s); "
                f"{int(duplicate_diagnostics.get('duplicate_row_count') or 0)} row(s)"
            )
        if result.get("cursor_warning"):
            st.caption(f"warning: {result.get('cursor_warning')}")
        st.caption(f"mode: {mode}")
        st.caption(f"cursor used: {_format_time(cursor_used) if cursor_used else 'None'}")
        st.caption(f"cursor source: {result.get('cursor_source') or 'none'}")
        st.caption(f"cursor timezone: {result.get('cursor_timezone') or 'UTC'}")
        st.caption("displayed timezone: Australia/Sydney")
        st.caption(f"Shopify query: {result.get('query') or 'None'}")
        st.caption(
            "Shopify query params: "
            f"status={query_parameters.get('status') or 'any'}; "
            f"financial_status={query_parameters.get('financial_status') or 'paid'}; "
            f"fulfillment_status={query_parameters.get('fulfillment_status') or 'none'}; "
            f"updated_at_min={query_parameters.get('updated_at_min') or 'none'}; "
            f"created_at_min={query_parameters.get('created_at_min') or 'none'}; "
            f"limit={query_parameters.get('limit') or result.get('limit') or 50}; "
            f"sort={query_parameters.get('sort') or 'UPDATED_AT'}; "
            f"order={query_parameters.get('order') or 'asc'}"
        )
        st.caption(f"Shopify orders fetched: {int(result.get('shopify_orders_fetched') or 0)}")
        st.caption(f"existing order lines skipped: {int(result.get('existing_lines_skipped') or result.get('lines_already_existing') or 0)}")
        st.caption(f"existing allocation units skipped: {int(result.get('existing_allocation_units_skipped') or result.get('existing_assignments_skipped') or 0)}")
        st.caption(f"new allocation units inserted: {int(result.get('new_allocation_units_inserted') or result.get('edition_allocations_created') or 0)}")
        st.caption(f"duplicate-risk units blocked: {int(result.get('duplicate_risk_units_blocked') or 0)}")
        st.caption(f"edition counters incremented: {int(result.get('edition_counters_incremented') or 0)}")
        if result.get("fetch_strategy"):
            st.caption(f"fetch strategy: {result.get('fetch_strategy')}")
        if result.get("cursor_orders_fetched") is not None or result.get("latest_created_orders_fetched") is not None:
            st.caption(
                "fetch breakdown: "
                f"cursor={int(result.get('cursor_orders_fetched') or 0)}; "
                f"latest_created={int(result.get('latest_created_orders_fetched') or 0)}; "
                f"deduped={int(result.get('duplicate_orders_removed') or 0)}"
            )
        latest_params = result.get("latest_created_query_parameters") or {}
        if latest_params:
            st.caption(
                "Latest-created catch-up params: "
                f"status={latest_params.get('status') or 'any'}; "
                f"financial_status={latest_params.get('financial_status') or 'paid'}; "
                f"limit={latest_params.get('limit') or result.get('limit') or 50}; "
                f"sort={latest_params.get('sort') or 'CREATED_AT'}; "
                f"order={latest_params.get('order') or 'desc'}"
            )
        st.caption(f"Shopify lines fetched: {int(result.get('line_items_fetched') or 0)}")
        st.caption(f"Supabase rows inserted: {int(result.get('supabase_rows_inserted') or 0)}")
        st.caption(f"existing rows skipped: {int(result.get('existing_lines_skipped') or result.get('lines_already_existing') or 0)}")
        st.caption(f"missing mappings: {int(result.get('missing_mapping_skipped') or 0)}")
        st.caption(
            "skipped unpaid/cancelled/refunded: "
            f"{int(result.get('skipped_unpaid_cancelled_refunded_lines') or 0)} lines"
        )
        st.caption(
            f"newest Shopify updated_at processed: "
            f"{_format_time(newest_processed) if newest_processed else 'None'}"
        )
        st.caption(f"cursor updated: {'yes' if result.get('cursor_updated') else 'no'}")
        if result.get("cursor_update_reason"):
            st.caption(f"cursor update reason: {result.get('cursor_update_reason')}")
        if not int(result.get("shopify_orders_fetched") or 0) and result.get("empty_fetch_reason"):
            st.caption(f"empty fetch reason: {result.get('empty_fetch_reason')}")
        mirror = result.get("product_metafield_mirror") or {}
        affected_handles = mirror.get("affected_product_handles") or result.get("affected_product_handles") or []
        if mirror or affected_handles:
            st.caption(
                "Shopify product mirror: "
                f"updated={int(mirror.get('synced') or 0)}; "
                f"skipped/failed={int(mirror.get('skipped') or 0)}; "
                f"attempted={int(mirror.get('attempted') or 0)}"
            )
            st.caption(
                "affected product handles: "
                f"{', '.join(str(handle) for handle in affected_handles) if affected_handles else 'None'}"
            )
            st.caption(
                "Storefront main tracker reads: "
                f"{', '.join(mirror.get('storefront_main_tracker_reads') or []) or 'sports_cave.edition_next_number'}"
            )
            st.caption(
                "Storefront badge reads: "
                f"{', '.join(mirror.get('storefront_badge_reads') or []) or 'sports_cave.edition_remaining'}"
            )
            for item in (mirror.get("results") or [])[:5]:
                st.caption(
                    f"mirror {item.get('handle') or 'product'}: {item.get('status') or 'unknown'}; "
                    f"Supabase next={item.get('supabase_next_edition') or 'n/a'}; "
                    f"highest={item.get('supabase_highest_assigned') or 'n/a'}; "
                    f"remaining={item.get('supabase_remaining') or 'n/a'}; "
                    f"Shopify product ID={item.get('shopify_product_id') or 'n/a'}"
                )
                before_values = compact_metafields(item.get("metafields_before") or [])
                after_values = compact_metafields(item.get("metafields_after") or [])
                if before_values:
                    st.caption(f"metafields before update: {before_values}")
                if after_values:
                    st.caption(f"metafields after update: {after_values}")
                stale_46 = [
                    f"{row.get('namespace')}.{row.get('key')}={row.get('value')}"
                    for row in (item.get("metafields_containing_46_before") or [])
                ]
                if stale_46:
                    st.caption(f"metafields containing 46 before update: {', '.join(stale_46[:8])}")
                stale_keys = [
                    f"{row.get('namespace')}.{row.get('key')}={row.get('value')}"
                    for row in (item.get("stale_metafields_found") or [])
                ]
                if stale_keys:
                    st.caption(f"stale edition metafields found: {', '.join(stale_keys[:8])}")
                if item.get("metafields_before_error"):
                    st.caption(f"metafields before-read warning: {item.get('metafields_before_error')}")
                if item.get("metafields_after_error"):
                    st.caption(f"metafields after-read warning: {item.get('metafields_after_error')}")
                if item.get("error"):
                    st.caption(f"mirror warning: {item.get('error')}")


def _render_admin_result(title, result):
    if not result:
        return
    st.markdown(f"**{title}**")
    for label, key in (
        ("Mode", "mode"),
        ("Shopify orders fetched", "shopify_orders_fetched"),
        ("Existing orders skipped", "existing_orders_skipped"),
        ("New orders inserted", "new_orders_inserted"),
        ("New lines inserted", "new_lines_inserted"),
        ("Edition allocations created", "edition_allocations_created"),
        ("Existing allocations preserved", "existing_allocations_preserved"),
        ("Missing mapping skipped", "missing_mapping_skipped"),
        ("Historical orders skipped", "historical_orders_skipped"),
        ("Orders updated", "orders_updated"),
        ("Variant rows filled", "variant_rows_filled"),
        ("Shipping rows filled", "shipping_rows_filled"),
        ("Email rows filled", "email_rows_filled"),
        ("Candidate rows", "candidate_rows"),
        ("Candidate orders", "candidate_orders"),
        ("Orders reprocessed", "orders_reprocessed"),
        ("Query", "query"),
    ):
        if key in result:
            st.caption(f"{label}: {result.get(key)}")
    errors = result.get("errors") or []
    if errors:
        st.caption(f"Errors: {len(errors)}")
        for error in errors[:5]:
            st.caption(f"- {error}")


def _missing_data_counts(rows):
    counts = {
        "missing_variant": 0,
        "missing_shipping": 0,
        "missing_customer": 0,
        "missing_product": 0,
        "missing_edition_number": 0,
    }
    for row in [_normalise_row(item) for item in (rows or [])]:
        if row.get("variant") == "Missing variant":
            counts["missing_variant"] += 1
        if row.get("shipping") == "Missing shipping":
            counts["missing_shipping"] += 1
        if row.get("customer") == "Missing from ledger":
            counts["missing_customer"] += 1
        if row.get("product") == "Missing from ledger":
            counts["missing_product"] += 1
        if not row.get("edition_number"):
            counts["missing_edition_number"] += 1
    return counts


def _render_missing_data_diagnostics(rows):
    counts = _missing_data_counts(rows)
    st.caption(f"Rows with missing variant: {counts['missing_variant']}")
    st.caption(f"Rows with missing shipping: {counts['missing_shipping']}")
    st.caption(f"Rows with missing customer: {counts['missing_customer']}")
    st.caption(f"Rows with missing product title: {counts['missing_product']}")
    st.caption(f"Rows with missing edition number: {counts['missing_edition_number']}")


def _render_ledger_diagnostics():
    status = _ledger_status()
    if not status.get("configured"):
        return
    counts = _ledger_counts()
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


def _render_orders_load_diagnostics(rows):
    meta = st.session_state.get(META_KEY) or {}
    search_text = str(st.session_state.get(SEARCH_KEY) or "")
    filtered_count = len(_filter_rows(rows, search_text))
    st.caption(f"Orders rows loaded: {len(st.session_state.get(ROWS_KEY, []) or [])}")
    st.caption(f"Last Supabase read: {_format_time(meta.get('saved_at'))}")
    st.caption(f"Last Supabase read error: {meta.get('error') or 'None'}")
    st.caption(f"Current filter/search: {search_text or 'None'}")
    st.caption(f"Rows after filtering: {filtered_count}")
    st.caption(f"Snapshot source: {meta.get('source') or 'unknown'}")


def _render_admin_panel(rows):
    if not _developer_mode():
        return
    backend = _configured_supabase_backend()
    with st.expander("Admin Order Sync + Diagnostics", expanded=False):
        admin_cols = st.columns([1.05, 1.05, 1.05, 1.05, 1, 1])
        if admin_cols[0].button("Preview Latest Paid Fetch", use_container_width=True, disabled=not backend):
            with st.spinner("Previewing latest paid Shopify orders..."):
                _preview_latest_paid_orders(limit=50)
            st.rerun()
        if admin_cols[1].button("Apply Latest Paid Sync", use_container_width=True, disabled=not backend):
            with st.spinner("Applying latest paid Shopify sync..."):
                _refresh_orders(latest_paid_only=True, max_orders=50)
            st.rerun()
        if admin_cols[2].button("Backfill Missing Shopify Details", use_container_width=True, disabled=not backend):
            with st.spinner("Backfilling missing Shopify details..."):
                _backfill_missing_order_details(dry_run=False, limit=100)
            st.rerun()
        if admin_cols[3].button("Backfill Dry Run", use_container_width=True, disabled=not backend):
            with st.spinner("Previewing missing Shopify details..."):
                _backfill_missing_order_details(dry_run=True, limit=100)
            st.rerun()
        if admin_cols[4].button("Preview Missing Edition Mapping Repair", use_container_width=True, disabled=not backend):
            with st.spinner("Previewing missing edition repairs..."):
                _repair_missing_editions(dry_run=True, limit=100)
            st.rerun()
        if admin_cols[5].button("Apply Missing Edition Mapping Repair", use_container_width=True, disabled=not backend):
            with st.spinner("Assigning missing editions..."):
                _repair_missing_editions(dry_run=False, limit=100)
            st.rerun()
        preview = st.session_state.get(LATEST_FETCH_PREVIEW_KEY) or {}
        if preview:
            _render_admin_result("Latest paid fetch preview", preview)
            preview_rows = preview.get("preview_rows") or []
            if preview_rows:
                st.dataframe(preview_rows, hide_index=True, use_container_width=True)
        _render_admin_result("Latest sync summary", st.session_state.get(SYNC_RESULT_KEY) or {})
        _render_admin_result("Latest backfill summary", st.session_state.get(BACKFILL_RESULT_KEY) or {})
        repair = st.session_state.get(REPAIR_RESULT_KEY) or {}
        if repair:
            _render_admin_result("Missing-edition repair summary", repair)
            preview_rows = repair.get("preview_rows") or []
            if preview_rows:
                st.dataframe(preview_rows, hide_index=True, use_container_width=True)
        st.markdown("**Supabase diagnostics**")
        _render_ledger_diagnostics()
        st.markdown("**Orders read completeness diagnostics**")
        _render_missing_data_diagnostics(rows)


def _render_orders_table(rows):
    start = time.perf_counter()
    rows = [_normalise_row(row) for row in rows]
    with st.container(border=True):
        st.dataframe(
            _display_table_payload(rows),
            hide_index=True,
            use_container_width=True,
            height=min(760, max(420, 28 * (len(rows) + 1))),
            column_order=VISIBLE_COLUMNS,
            column_config=_column_config(),
            selection_mode="multi-row",
            on_select="rerun",
            row_height=28,
            key=GRID_KEY,
        )
        _render_order_copy_click_handler()
    _perf_log("render table", start, rows=len(rows))
    print("Table render: {:.0f} ms".format((time.perf_counter() - start) * 1000), flush=True)


def _render_orders_search_form():
    if hasattr(st, "form") and hasattr(st, "form_submit_button"):
        with st.form("orders-search-form", clear_on_submit=False):
            search_cols = st.columns([3.2, 1])
            query = search_cols[0].text_input(
                "Search orders",
                key=SEARCH_KEY,
                placeholder="Order, customer, product, variant, edition",
            )
            search_cols[1].caption("Latest 50")
            submitted = st.form_submit_button("Search", use_container_width=False)
        return str(query or "").strip(), bool(submitted)

    search_cols = st.columns([3.2, 1])
    query = search_cols[0].text_input(
        "Search orders",
        key=SEARCH_KEY,
        placeholder="Order, customer, product, variant, edition",
    )
    search_cols[1].caption("Latest 50")
    return str(query or "").strip(), False


def _async_orders_load_supported():
    return callable(getattr(st, "fragment", None)) and bool(_configured_supabase_backend())


def _render_orders_load_failure(query):
    st.error("Orders could not be loaded. Please retry.")
    if st.button("Retry", key="orders-load-retry", use_container_width=False):
        if _async_orders_load_supported():
            _start_snapshot_load(query, force=True)
        else:
            _load_snapshot_once(query, force=True)
        st.rerun()


def _render_orders_data_area():
    prep_started = time.perf_counter()
    rows = _apply_latest_product_numbers(st.session_state.get(ROWS_KEY, []))
    st.session_state[ROWS_KEY] = rows
    _perf_log("table render prep", prep_started, rows=len(rows))

    meta = st.session_state.get(META_KEY) or {}
    load_error = st.session_state.get(LOAD_ERROR_KEY) or meta.get("error") or ""
    if load_error:
        _render_orders_load_failure(str(st.session_state.get(LOAD_REQUEST_KEY) or st.session_state.get(LOADED_QUERY_KEY) or ""))
    read_diagnostic = dict(meta.get("database_read") or {})
    if read_diagnostic.get("recovered"):
        st.info("A stale database connection was replaced automatically. These results are current.")

    notice = st.session_state.get(NOTICE_KEY)
    if notice:
        st.success(notice)
        st.session_state[NOTICE_KEY] = ""
    if _developer_mode():
        _render_sync_diagnostics(st.session_state.get(SYNC_RESULT_KEY) or {})

    if not rows:
        if not load_error:
            st.info("No saved orders are available in the operational ledger yet.")
        elif _developer_mode():
            st.caption(
                "Database diagnostic: "
                f"{read_diagnostic.get('category') or 'database_unavailable'}; "
                f"exception={read_diagnostic.get('exception_class') or 'Unknown'}; "
                f"operation={read_diagnostic.get('operation') or 'orders.load'}; "
                f"duration={int(read_diagnostic.get('duration_ms') or 0)} ms."
            )
        return

    # The database is already bounded to 50 orders. Keep every fulfilment unit for
    # those orders so a quantity-2 line can never lose its second allocation here.
    visible_rows = rows

    _render_top_actions(visible_rows, None)

    if st.session_state.get(LOADED_QUERY_KEY):
        st.caption(f"{len(visible_rows)} matching fulfilment row(s) shown from Supabase.")
    else:
        st.caption(f"{len(visible_rows)} fulfilment row(s) shown from the latest 50 orders.")

    _render_orders_table(visible_rows)


def _render_orders_loading_fragment():
    fragment = getattr(st, "fragment")

    @fragment(run_every="1s")
    def _orders_loading_fragment():
        status = _consume_snapshot_load()
        if status == "loading":
            with st.container(border=True):
                st.info("Loading orders...")
            return
        st.rerun()

    _orders_loading_fragment()


def render_page():
    page_started = time.perf_counter()
    _ensure_state()
    print("PERF Orders page entry", flush=True)
    st.title("Orders")
    st.caption("Orders sync automatically after payment.")
    search_text, search_submitted = _render_orders_search_form()
    if _async_orders_load_supported():
        if search_submitted:
            _start_snapshot_load(search_text, force=True)
        elif not st.session_state.get(SNAPSHOT_LOADED_KEY) and st.session_state.get(LOAD_FUTURE_KEY) is None:
            _start_snapshot_load("")
        if st.session_state.get(LOAD_FUTURE_KEY) is not None:
            _render_orders_loading_fragment()
            _perf_log("page shell", page_started, state="loading")
            return
    else:
        if search_submitted:
            _load_snapshot_once(search_text, force=True)
        elif not st.session_state.get(SNAPSHOT_LOADED_KEY):
            _load_snapshot_once("")

    _render_orders_data_area()
    _perf_log("total page load", page_started, rows=len(st.session_state.get(ROWS_KEY) or []))
