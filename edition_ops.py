from copy import deepcopy
import csv
from datetime import datetime, timezone
import importlib
import io
import json
import os
from pathlib import Path
import re
import time

import streamlit as st

import shopify_sync


BASE_DIR = Path(__file__).resolve().parent
SNAPSHOT_PATH = BASE_DIR / "output" / "_cache" / "edition_ops_products_snapshot.json"
SNAPSHOT_VERSION = 1

ROWS_KEY = "edition_ops_rows"
ORIGINAL_ROWS_KEY = "edition_ops_original_rows"
EDITOR_ROWS_KEY = "edition_ops_editor_rows"
META_KEY = "edition_ops_snapshot_meta"
ERRORS_KEY = "edition_ops_sync_errors"
NOTICE_KEY = "edition_ops_notice"
NOTICE_LEVEL_KEY = "edition_ops_notice_level"
IMPORT_WARNINGS_KEY = "edition_ops_import_warnings"
SHOPIFY_MIRROR_PREVIEW_KEY = "edition_ops_shopify_mirror_preview"
SHOPIFY_MIRROR_RESULT_KEY = "edition_ops_shopify_mirror_result"
MANUAL_PRODUCT_SYNC_RESULT_KEY = "edition_ops_manual_product_sync_result"
EDITOR_VERSION_KEY = "edition_ops_editor_version"
EDITOR_KEY = "edition_ops_editor_v3"
SNAPSHOT_LOADED_KEY = "edition_ops_snapshot_loaded"
LOADED_AT_KEY = "edition_ops_loaded_at"
LOAD_ERROR_KEY = "edition_ops_load_error"
LOAD_DIAGNOSTIC_KEY = "edition_ops_load_diagnostic"
EDITOR_PAGE_SELECTION_KEY = "edition_ops_editor_page_selection"
EDITOR_RENDERED_PAGE_KEY = "edition_ops_editor_rendered_page"
ORDERS_CACHE_VERSION_KEY = "orders-ledger-cache-version"
EDITION_OPS_CACHE_VERSION_KEY = "edition-ops-ledger-cache-version"
EDITION_OPS_CACHE_TTL_SECONDS = max(int(os.getenv("SUPABASE_EDITION_OPS_CACHE_TTL_SECONDS", "180")), 30)
EDITION_OPS_PRODUCT_LIMIT = max(min(int(os.getenv("SUPABASE_EDITION_OPS_PRODUCT_LIMIT", "500")), 1000), 1)
EDITION_OPS_EDITOR_PAGE_SIZE = max(min(int(os.getenv("EDITION_OPS_EDITOR_PAGE_SIZE", "50")), 100), 10)

EDITABLE_FIELDS = (
    "edition_enabled",
    "edition_total",
    "edition_next_number",
)

VISIBLE_COLUMNS = (
    "product_title",
    "handle",
    "edition_enabled",
    "edition_total",
    "edition_next_number",
    "edition_sold_count",
    "edition_remaining",
    "edition_status",
    "sync_status",
    "admin_url",
    "online_store_url",
)

CSV_COLUMNS = (
    "shopify_product_gid",
    "legacy_resource_id",
    "product_title",
    "handle",
    "status",
    "edition_enabled",
    "edition_total",
    "edition_next_number",
    "edition_sold_count",
    "edition_remaining",
    "edition_status",
    "edition_label",
    "online_store_url",
    "admin_url",
    "last_synced_at",
    "sync_status",
    "sync_error",
)

SHOPIFY_MIRROR_METAFIELD_KEYS = (
    "edition_enabled",
    "edition_total",
    "edition_remaining",
    "edition_next_number",
    "edition_sold_count",
    "edition_status",
    "edition_label",
)
SHOPIFY_RETRY_STATUSES = {
    "needs sync",
    "needs_shopify_sync",
    "shopify mirror failed",
    "shopify mirror pending",
    "saved locally",
    "saved in supabase",
}


def _render_import_popover_styles():
    st.markdown(
        """
        <style>
        div[data-testid="stPopover"] div[role="dialog"],
        div[data-testid="stPopover"] [data-testid="stPopoverBody"],
        div[data-baseweb="popover"],
        div[data-baseweb="popover"] > div {
            background: #FFFFFF !important;
            color: #111111 !important;
        }

        div[data-testid="stPopover"] div[role="dialog"] *,
        div[data-testid="stPopover"] [data-testid="stPopoverBody"] *,
        div[data-testid="stPopover"] [data-testid="stFileUploader"] *,
        div[data-testid="stPopover"] section[data-testid="stFileUploaderDropzone"] *,
        div[data-baseweb="popover"] *,
        div[data-baseweb="popover"] label,
        div[data-baseweb="popover"] p,
        div[data-baseweb="popover"] span {
            color: #111111 !important;
            -webkit-text-fill-color: #111111 !important;
        }

        div[data-testid="stPopover"] [data-testid="stFileUploader"],
        div[data-testid="stPopover"] section[data-testid="stFileUploaderDropzone"],
        div[data-testid="stPopover"] [data-testid="stFileUploaderFile"],
        div[data-testid="stPopover"] [data-baseweb="tag"],
        div[data-baseweb="popover"] input,
        div[data-baseweb="popover"] textarea,
        div[data-baseweb="popover"] [role="listbox"],
        div[data-baseweb="popover"] [data-baseweb="select"] > div {
            background: #FFFFFF !important;
            color: #111111 !important;
            border-color: #D5D5D5 !important;
        }

        div[data-testid="stPopover"] > button,
        div[data-testid="stPopover"] div[data-testid="stButton"] button,
        div[data-testid="stPopover"] div[data-testid="stFileUploader"] button:not([aria-label*="Delete"]):not([aria-label*="Remove"]),
        div[data-testid="stPopover"] section[data-testid="stFileUploaderDropzone"] button:not([aria-label*="Delete"]):not([aria-label*="Remove"]) {
            background: #111111 !important;
            border-color: #111111 !important;
            color: #FFFFFF !important;
            -webkit-text-fill-color: #FFFFFF !important;
        }

        div[data-testid="stPopover"] > button *,
        div[data-testid="stPopover"] div[data-testid="stButton"] button *,
        div[data-testid="stPopover"] div[data-testid="stButton"] button p,
        div[data-testid="stPopover"] div[data-testid="stButton"] button span,
        div[data-testid="stPopover"] div[data-testid="stFileUploader"] button:not([aria-label*="Delete"]):not([aria-label*="Remove"]) *,
        div[data-testid="stPopover"] section[data-testid="stFileUploaderDropzone"] button:not([aria-label*="Delete"]):not([aria-label*="Remove"]) * {
            color: #FFFFFF !important;
            -webkit-text-fill-color: #FFFFFF !important;
            fill: #FFFFFF !important;
            stroke: #FFFFFF !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _format_time(value):
    if not value:
        return "Never"
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone().strftime("%d %b %Y %I:%M %p")
    except ValueError:
        return str(value)


def _remaining(total, next_number):
    try:
        total_value = max(int(total), 1)
    except (TypeError, ValueError):
        total_value = 100
    try:
        next_value = max(int(next_number), 1)
    except (TypeError, ValueError):
        next_value = 1
    return max(total_value - next_value + 1, 0)


def _sold_count(next_number):
    return max(_coerce_int(next_number, 1) - 1, 0)


def _remaining_from_sold(total, sold_count):
    return max(_coerce_int(total, 100) - _coerce_nonnegative_int(sold_count, 0), 0)


def _widget_status(remaining):
    if remaining <= 0:
        return "Sold Out Archive"
    if remaining <= 5:
        return "Final Editions"
    if remaining <= 12:
        return "Selling Quickly"
    return "Limited Edition"


def _coerce_bool(value):
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"true", "1", "yes", "on", "y"}


def _coerce_int(value, default):
    try:
        return max(int(str(value).strip()), 1)
    except (TypeError, ValueError):
        return default


def _coerce_nonnegative_int(value, default):
    text = "" if value is None else str(value).strip().replace(",", "")
    if text == "":
        return default
    try:
        numeric = float(text)
    except ValueError:
        return default
    if not numeric.is_integer() or numeric < 0:
        return default
    return int(numeric)


def _normalise_title(value):
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def _normalise_text(value):
    return re.sub(r"\s+", " ", str(value or "").strip())


def _first_present(mapping, *keys):
    for key in keys:
        value = mapping.get(key)
        if value is not None and str(value).strip() != "":
            return value
    return ""


def _normalise_csv_header(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def _csv_value(row, *aliases):
    if not row:
        return ""
    normalised = {_normalise_csv_header(key): value for key, value in row.items()}
    for alias in aliases:
        key = _normalise_csv_header(alias)
        if key in normalised:
            return normalised[key]
    return ""


def _csv_has(row, *aliases):
    if not row:
        return False
    headers = {_normalise_csv_header(key) for key in row}
    return any(_normalise_csv_header(alias) in headers for alias in aliases)


def _parse_positive_int(raw_value):
    text = str(raw_value or "").strip().replace(",", "")
    if text == "":
        return None
    try:
        numeric = float(text)
    except ValueError:
        return "invalid"
    if not numeric.is_integer() or numeric < 1:
        return "invalid"
    return int(numeric)


def _normalise_row(row, *, preserve_derived=True):
    updated = dict(row or {})
    updated["edition_product_id"] = str(
        updated.get("edition_product_id")
        or updated.get("id")
        or ""
    ).strip()
    updated["shopify_product_gid"] = str(
        updated.get("shopify_product_gid")
        or updated.get("Product ID")
        or updated.get("shopify_product_id")
        or ""
    ).strip()
    updated["legacy_resource_id"] = str(updated.get("legacy_resource_id") or updated.get("Legacy ID") or "").strip()
    updated["thumbnail_url"] = str(updated.get("thumbnail_url") or updated.get("Thumbnail") or "").strip()
    updated["product_title"] = _normalise_text(updated.get("product_title") or updated.get("Product title") or "Untitled Product")
    updated["shopify_handle"] = _normalise_text(
        updated.get("shopify_handle")
        or updated.get("Shopify handle")
        or updated.get("handle")
        or updated.get("Handle")
        or ""
    )
    updated["handle"] = updated["shopify_handle"]
    updated["status"] = _normalise_text(updated.get("status") or updated.get("Status") or "ACTIVE")
    updated["edition_enabled"] = _coerce_bool(updated.get("edition_enabled", updated.get("Enabled")))
    updated["edition_total"] = _coerce_int(updated.get("edition_total", updated.get("Edition total")), 100)
    updated["edition_next_number"] = _coerce_int(
        updated.get("edition_next_number", updated.get("Next edition number")),
        1,
    )
    updated["edition_label"] = (
        str(updated.get("edition_label") or updated.get("Edition label") or "Numbered Edition").strip()
        or "Numbered Edition"
    )
    default_sold = _sold_count(updated["edition_next_number"])
    default_remaining = _remaining_from_sold(updated["edition_total"], default_sold)
    if preserve_derived:
        sold_source = _first_present(updated, "edition_sold_count", "Sold count")
        remaining_source = _first_present(updated, "edition_remaining", "Edition remaining", "remaining", "Remaining")
        status_source = _first_present(updated, "edition_status", "Edition status", "widget_status", "Widget status")
        updated["edition_sold_count"] = _coerce_nonnegative_int(sold_source, default_sold)
        updated["edition_remaining"] = _coerce_nonnegative_int(
            remaining_source,
            _remaining_from_sold(updated["edition_total"], updated["edition_sold_count"]),
        )
        updated["edition_status"] = str(status_source or _widget_status(updated["edition_remaining"])).strip()
    else:
        updated["edition_sold_count"] = default_sold
        updated["edition_remaining"] = default_remaining
        updated["edition_status"] = _widget_status(default_remaining)
    updated["remaining"] = updated["edition_remaining"]
    updated["widget_status"] = updated["edition_status"]
    updated["online_store_url"] = str(updated.get("online_store_url") or updated.get("Open live product") or "")
    updated["admin_url"] = str(updated.get("admin_url") or updated.get("Open Admin") or "")
    updated["last_synced_at"] = str(updated.get("last_synced_at") or "")
    updated["sync_status"] = str(updated.get("sync_status") or updated.get("Last saved / Synced") or "Loaded").strip() or "Loaded"
    updated["sync_error"] = str(updated.get("sync_error") or "")
    return updated


def _stable_row_key(row):
    normalised = _normalise_row(row)
    edition_product_id = _normalise_text(normalised.get("edition_product_id"))
    if edition_product_id:
        return f"edition_product:{edition_product_id}"
    shopify_handle = _normalise_title(normalised.get("shopify_handle") or normalised.get("handle"))
    if shopify_handle:
        return f"handle:{shopify_handle}"
    shopify_product_gid = _normalise_text(normalised.get("shopify_product_gid"))
    if shopify_product_gid:
        return f"product_gid:{shopify_product_gid}"
    product_title = _normalise_title(normalised.get("product_title"))
    if product_title:
        return f"title:{product_title}"
    return ""


def _row_from_product(product):
    edition = product.get("edition") or {}
    row = {
        "shopify_product_gid": product.get("shopify_product_id") or "",
        "legacy_resource_id": product.get("legacy_resource_id") or "",
        "thumbnail_url": product.get("thumbnail_url") or "",
        "product_title": product.get("title") or "Untitled Product",
        "handle": product.get("handle") or "",
        "status": product.get("status") or "ACTIVE",
        "edition_enabled": _coerce_bool(edition.get("edition_enabled")),
        "edition_total": _coerce_int(edition.get("edition_total"), 100),
        "edition_next_number": _coerce_int(edition.get("edition_next_number"), 1),
        "edition_sold_count": _coerce_nonnegative_int(edition.get("edition_sold_count"), 0),
        "edition_remaining": _coerce_nonnegative_int(edition.get("edition_remaining"), 0),
        "edition_status": edition.get("edition_status") or "",
        "edition_label": edition.get("edition_label") or "Numbered Edition",
        "online_store_url": product.get("online_store_url") or "",
        "admin_url": product.get("admin_url") or "",
        "last_synced_at": "",
        "sync_status": "Loaded",
        "sync_error": "",
    }
    return _normalise_row(row)


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


def _cache_version(key):
    st.session_state.setdefault(key, 0)
    return int(st.session_state[key])


def _bump_cache_versions(*keys):
    for key in keys:
        st.session_state[key] = int(st.session_state.get(key, 0)) + 1


def _invalidate_edition_ops_cache(*, bump_orders=False):
    _bump_cache_versions(EDITION_OPS_CACHE_VERSION_KEY, *( [ORDERS_CACHE_VERSION_KEY] if bump_orders else []))
    st.session_state[SNAPSHOT_LOADED_KEY] = False


@st.cache_data(ttl=EDITION_OPS_CACHE_TTL_SECONDS, show_spinner=False)
def _cached_supabase_products_snapshot(cache_version):
    started = time.perf_counter()
    backend = _configured_supabase_backend()
    if not backend:
        return None
    if hasattr(backend, "list_edition_products_read_only"):
        products = backend.list_edition_products_read_only(
            search="",
            limit=EDITION_OPS_PRODUCT_LIMIT,
        )
    else:
        products = backend.list_edition_products(search="", limit=EDITION_OPS_PRODUCT_LIMIT)
    rows = [_row_from_supabase_product(product) for product in products or []]
    last_synced = max(
        (str(row.get("last_synced_at") or "") for row in rows),
        default="",
    )
    diagnostic = {}
    if hasattr(backend, "get_last_database_read_diagnostic"):
        diagnostic = backend.get_last_database_read_diagnostic()
    print(
        "PERF Edition Ops snapshot "
        f"duration_ms={int((time.perf_counter() - started) * 1000)} "
        f"rows={len(rows)} queries={int(diagnostic.get('query_count') or 1)}",
        flush=True,
    )
    return {
        "version": SNAPSHOT_VERSION,
        "rows": rows,
        "original_rows": deepcopy(rows),
        "last_refreshed_from_shopify": last_synced,
        "saved_at": last_synced,
        "source": "supabase",
        "cached": False,
        "mirror_status": "",
        "database_read": diagnostic,
        "limit": EDITION_OPS_PRODUCT_LIMIT,
    }


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


def _row_from_supabase_product(product):
    next_number = _coerce_int(
        product.get("run_next_edition_number") or product.get("next_edition_number"),
        1,
    )
    total = _coerce_int(product.get("edition_total"), 100)
    sold = _coerce_nonnegative_int(
        product.get("sold_count"),
        _coerce_nonnegative_int(product.get("last_assigned_edition"), _sold_count(next_number)),
    )
    remaining = _coerce_nonnegative_int(
        product.get("remaining_count"),
        _coerce_nonnegative_int(product.get("remaining_editions"), _remaining_from_sold(total, sold)),
    )
    status = str(product.get("status") or "").strip()
    sold_out = bool(product.get("sold_out")) or status.casefold() == "sold_out"
    mirror_status = str(product.get("metafields_sync_status") or "").strip()
    sync_status = "Loaded from Supabase"
    sync_error = ""
    if mirror_status.casefold() == "failed":
        sync_status = "needs_shopify_sync"
        sync_error = str(product.get("last_metafield_error") or "")
    elif mirror_status.casefold() in {"pending", "never synced"}:
        sync_status = "needs_shopify_sync"
    row = {
        "edition_product_id": product.get("id") or product.get("edition_product_id") or "",
        "shopify_product_gid": product.get("shopify_product_id") or product.get("shopify_product_gid") or "",
        "legacy_resource_id": product.get("legacy_resource_id") or "",
        "thumbnail_url": product.get("display_image_url") or product.get("featured_image_url") or "",
        "product_title": product.get("product_title") or product.get("title") or "Untitled Product",
        "shopify_handle": product.get("shopify_handle") or product.get("handle") or "",
        "handle": product.get("shopify_handle") or product.get("handle") or "",
        "status": product.get("shopify_status") or "ACTIVE",
        "edition_enabled": status != "inactive" and bool(product.get("active", True)),
        "edition_total": total,
        "edition_next_number": next_number,
        "edition_sold_count": sold,
        "edition_remaining": remaining,
        "edition_status": "Sold Out Archive" if sold_out else _widget_status(remaining),
        "edition_label": product.get("edition_name") or product.get("edition_label") or "Numbered Edition",
        "online_store_url": product.get("online_store_url") or "",
        "admin_url": product.get("admin_url") or "",
        "last_synced_at": product.get("updated_at") or "",
        "sync_status": sync_status,
        "sync_error": sync_error,
    }
    return _normalise_row(row)


def _load_supabase_snapshot():
    return _cached_supabase_products_snapshot(_cache_version(EDITION_OPS_CACHE_VERSION_KEY))


def _ensure_state():
    st.session_state.setdefault(ROWS_KEY, [])
    st.session_state.setdefault(ORIGINAL_ROWS_KEY, [])
    st.session_state.setdefault(EDITOR_ROWS_KEY, deepcopy(st.session_state.get(ROWS_KEY, [])))
    st.session_state.setdefault(
        META_KEY,
        {
            "last_refreshed_from_shopify": "",
            "saved_at": "",
            "mirror_status": "",
        },
    )
    st.session_state.setdefault(ERRORS_KEY, {})
    st.session_state.setdefault(IMPORT_WARNINGS_KEY, [])
    st.session_state.setdefault(NOTICE_KEY, "")
    st.session_state.setdefault(NOTICE_LEVEL_KEY, "success")
    st.session_state.setdefault(SHOPIFY_MIRROR_PREVIEW_KEY, None)
    st.session_state.setdefault(SHOPIFY_MIRROR_RESULT_KEY, None)
    st.session_state.setdefault(EDITOR_VERSION_KEY, 0)
    st.session_state.setdefault(LOADED_AT_KEY, "")
    st.session_state.setdefault(LOAD_ERROR_KEY, "")
    st.session_state.setdefault(LOAD_DIAGNOSTIC_KEY, {})
    st.session_state.setdefault(EDITOR_RENDERED_PAGE_KEY, -1)


def _bump_editor_version():
    st.session_state[EDITOR_VERSION_KEY] = int(st.session_state.get(EDITOR_VERSION_KEY) or 0) + 1


def _clear_editor_state():
    try:
        st.session_state.pop(EDITOR_KEY, None)
    except AttributeError:
        pass


def _safe_edition_ops_load_failure(error=None, *, diagnostic=None):
    details = dict(diagnostic or getattr(error, "diagnostic", {}) or {})
    category = str(details.get("category") or "database_unavailable")
    message = {
        "request_timeout": "Edition Ops could not refresh because the database read timed out.",
        "stale_connection": "Edition Ops could not refresh because the database connection closed.",
        "database_unavailable": "Edition Ops could not refresh because Supabase is temporarily unavailable.",
        "sql_query_error": "Edition Ops could not refresh because its database query failed.",
    }.get(category, "Edition Ops could not refresh from Supabase.")
    details.update(
        {
            "category": category,
            "exception_class": details.get("exception_class") or (error.__class__.__name__ if error else ""),
            "operation": details.get("operation") or "edition_ops.products.latest",
            "message": message,
        }
    )
    return details


def _session_cached_snapshot():
    meta = dict(st.session_state.get(META_KEY) or {})
    rows = st.session_state.get(ROWS_KEY)
    if not isinstance(rows, list) or (not rows and not meta.get("source")):
        return None
    originals = st.session_state.get(ORIGINAL_ROWS_KEY)
    originals = originals if isinstance(originals, list) else rows
    return {
        "version": SNAPSHOT_VERSION,
        "rows": [_normalise_row(row) for row in rows],
        "original_rows": [_normalise_row(row) for row in originals],
        "last_refreshed_from_shopify": meta.get("last_refreshed_from_shopify") or "",
        "saved_at": meta.get("saved_at") or "",
        "source": "session_cache",
        "cached": True,
        "mirror_status": meta.get("mirror_status") or "",
    }


def _local_cached_snapshot():
    if not SNAPSHOT_PATH.exists():
        return None
    try:
        payload = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
    rows = [_normalise_row(row) for row in payload.get("rows") or []]
    original_rows = payload.get("original_rows")
    originals = (
        [_normalise_row(row) for row in original_rows]
        if isinstance(original_rows, list)
        else deepcopy(rows)
    )
    return {
        "version": payload.get("version") or SNAPSHOT_VERSION,
        "rows": rows,
        "original_rows": originals,
        "last_refreshed_from_shopify": payload.get("last_refreshed_from_shopify") or "",
        "saved_at": payload.get("saved_at") or "",
        "source": "local_cache",
        "cached": True,
        "mirror_status": payload.get("mirror_status") or "",
    }


def _load_snapshot():
    started = time.perf_counter()
    failure = None
    try:
        supabase_snapshot = _load_supabase_snapshot()
    except Exception as error:
        backend = _configured_supabase_backend()
        diagnostic = {}
        if backend and hasattr(backend, "get_last_database_read_diagnostic"):
            diagnostic = backend.get_last_database_read_diagnostic()
        failure = _safe_edition_ops_load_failure(error, diagnostic=diagnostic)
        supabase_snapshot = None
    if supabase_snapshot is not None:
        print(
            "PERF Edition Ops load complete "
            f"duration_ms={int((time.perf_counter() - started) * 1000)} "
            f"rows={len(supabase_snapshot.get('rows') or [])} source=supabase",
            flush=True,
        )
        return supabase_snapshot
    if failure is None:
        failure = _safe_edition_ops_load_failure()
    cached_snapshot = _session_cached_snapshot() or _local_cached_snapshot()
    if cached_snapshot is None:
        cached_snapshot = {
            "version": SNAPSHOT_VERSION,
            "rows": [],
            "original_rows": [],
            "last_refreshed_from_shopify": "",
            "saved_at": "",
            "source": "supabase_error",
            "cached": False,
            "mirror_status": "",
        }
    cached_snapshot["load_error"] = failure.get("message") or "Edition Ops could not refresh from Supabase."
    cached_snapshot["database_read"] = failure
    print(
        "WARN Edition Ops load failed "
        f"operation={failure.get('operation')} category={failure.get('category')} "
        f"exception_class={failure.get('exception_class') or 'unknown'} "
        f"duration_ms={int((time.perf_counter() - started) * 1000)} "
        f"cached={str(bool(cached_snapshot.get('cached'))).lower()}",
        flush=True,
    )
    return cached_snapshot


def _write_snapshot(rows, originals=None, meta=None):
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    metadata = dict(st.session_state.get(META_KEY) or {})
    metadata.update(meta or {})
    metadata["saved_at"] = _now_iso()
    payload = {
        "version": SNAPSHOT_VERSION,
        "last_refreshed_from_shopify": metadata.get("last_refreshed_from_shopify") or "",
        "saved_at": metadata["saved_at"],
        "rows": [_normalise_row(row) for row in rows],
        "original_rows": [_normalise_row(row) for row in (originals if originals is not None else rows)],
    }
    SNAPSHOT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    st.session_state[META_KEY] = {
        "last_refreshed_from_shopify": payload["last_refreshed_from_shopify"],
        "saved_at": payload["saved_at"],
        "mirror_status": metadata.get("mirror_status") or "",
    }


def _hydrate_from_snapshot_once():
    if st.session_state.get(SNAPSHOT_LOADED_KEY):
        return
    snapshot = _load_snapshot()
    if snapshot:
        st.session_state[ROWS_KEY] = snapshot["rows"]
        st.session_state[ORIGINAL_ROWS_KEY] = snapshot["original_rows"]
        st.session_state[EDITOR_ROWS_KEY] = deepcopy(snapshot["rows"])
        st.session_state[LOADED_AT_KEY] = _now_iso()
        st.session_state[META_KEY] = {
            "last_refreshed_from_shopify": snapshot.get("last_refreshed_from_shopify") or "",
            "saved_at": snapshot.get("saved_at") or "",
            "mirror_status": snapshot.get("mirror_status") or "",
            "source": snapshot.get("source") or "supabase",
            "cached": bool(snapshot.get("cached")),
            "limit": snapshot.get("limit") or EDITION_OPS_PRODUCT_LIMIT,
        }
        st.session_state[LOAD_ERROR_KEY] = snapshot.get("load_error") or ""
        st.session_state[LOAD_DIAGNOSTIC_KEY] = dict(snapshot.get("database_read") or {})
    st.session_state[SNAPSHOT_LOADED_KEY] = True


def _editable_snapshot(row):
    recalculated = _normalise_row(row)
    return {
        "edition_enabled": bool(recalculated.get("edition_enabled")),
        "edition_total": _coerce_int(recalculated.get("edition_total"), 100),
        "edition_next_number": _coerce_int(recalculated.get("edition_next_number"), 1),
    }


def _changed_rows(rows, originals):
    original_by_id = {_stable_row_key(row): _normalise_row(row) for row in originals if _stable_row_key(row)}
    changed = []
    for row in rows:
        key = _stable_row_key(row)
        original = original_by_id.get(key)
        if not key or not original or _editable_snapshot(row) != _editable_snapshot(original):
            changed.append(row)
    return changed


def _editable_changed_keys(rows, originals):
    return [_stable_row_key(row) for row in _changed_rows(rows, originals) if _stable_row_key(row)]


def _rows_to_save(rows, originals):
    by_product_id = {}
    for row in _changed_rows(rows, originals):
        key = _stable_row_key(row)
        if key:
            by_product_id[key] = _normalise_row(row)
    return list(by_product_id.values())


def _pending_shopify_sync_rows(rows):
    pending = []
    seen = set()
    for row in rows:
        normalised = _normalise_row(row)
        if str(normalised.get("sync_status") or "").strip().casefold() not in SHOPIFY_RETRY_STATUSES:
            continue
        key = _stable_row_key(normalised)
        if key and key not in seen:
            pending.append(normalised)
            seen.add(key)
    return pending


def _mark_current_changes(rows, originals):
    original_by_id = {_stable_row_key(row): _normalise_row(row) for row in originals if _stable_row_key(row)}
    updated_rows = []
    for row in rows:
        updated = _normalise_row(row)
        original = original_by_id.get(_stable_row_key(updated))
        changed = not original or _editable_snapshot(updated) != _editable_snapshot(original)
        status = str(updated.get("sync_status") or "").strip()
        if changed and status not in {"Unsaved import", "Needs Sync", "needs_shopify_sync"}:
            updated["sync_status"] = "Unsaved"
            updated["sync_error"] = ""
        elif not changed and status in {"Unsaved", "Unsaved import"}:
            updated["sync_status"] = original.get("sync_status", "Loaded") if original else "Loaded"
            updated["sync_error"] = original.get("sync_error", "") if original else ""
        updated_rows.append(updated)
    return updated_rows


def _original_rows_by_key(originals):
    return {
        _stable_row_key(row): _normalise_row(row)
        for row in originals
        if _stable_row_key(row)
    }


def _product_label(row):
    normalised = _normalise_row(row)
    title = normalised.get("product_title") or ""
    handle = normalised.get("handle") or ""
    if title and handle:
        return f"{title} ({handle})"
    return title or handle or "Edition row"


def _prepare_rows_for_save(rows, originals):
    original_by_key = _original_rows_by_key(originals)
    prepared = []
    for row in rows:
        updated = _normalise_row(row, preserve_derived=False)
        original = original_by_key.get(_stable_row_key(updated))
        old_enabled = bool(original.get("edition_enabled")) if original else bool(updated.get("edition_enabled"))
        new_enabled = bool(updated.get("edition_enabled"))
        if old_enabled and not new_enabled:
            total = _coerce_int(updated.get("edition_total"), 100)
            protected_next = _coerce_nonnegative_int((original or {}).get("edition_sold_count"), 0) + 1
            updated["edition_next_number"] = max(total + 1, protected_next)
            updated["edition_sold_count"] = max(total, protected_next - 1)
            updated["edition_remaining"] = 0
            updated["edition_status"] = "Sold Out Archive"
            updated["sync_status"] = "Unsaved"
            updated["sync_error"] = ""
        prepared.append(_normalise_row(updated, preserve_derived=True))
    return prepared


def _shopify_values_from_row(row):
    recalculated = _normalise_row(row, preserve_derived=False)
    return {
        "shopify_product_id": recalculated.get("shopify_product_gid"),
        "title": recalculated.get("product_title"),
        "edition_enabled": recalculated.get("edition_enabled"),
        "edition_total": recalculated.get("edition_total"),
        "edition_next_number": recalculated.get("edition_next_number"),
        "edition_label": recalculated.get("edition_label"),
    }


def _save_validation_error(row, original=None):
    normalised = _normalise_row(row, preserve_derived=False)
    original = _normalise_row(original) if original else None
    label = _product_label(normalised)
    if not normalised.get("handle"):
        return f"{label}: Shopify handle is required."
    total = _coerce_int(normalised.get("edition_total"), 0)
    next_number = _coerce_int(normalised.get("edition_next_number"), 0)
    enabled = bool(normalised.get("edition_enabled"))
    if total < 1:
        return f"{label}: edition_total must be 1 or higher."
    if next_number < 1:
        return f"{label}: next_edition_number must be 1 or higher."
    if original and bool(original.get("edition_enabled")) is False and enabled and next_number > total:
        return "This edition is archived. To reopen it, set Next edition number back within the edition total first."
    if enabled and next_number > total:
        return f"{label}: next_edition_number must be between 1 and edition_total for enabled editions."
    if next_number > total + 1:
        return f"{label}: next_edition_number cannot be more than one past edition_total."
    remaining = total - max(next_number - 1, 0)
    if remaining < 0:
        return f"{label}: remaining cannot be negative."
    return ""


def _mirror_options(rows):
    options = []
    seen = set()
    for row in rows:
        normalised = _normalise_row(row)
        handle = str(normalised.get("handle") or "").strip()
        if not handle or handle in seen:
            continue
        label = f"{normalised.get('product_title') or handle} ({handle})"
        options.append((label, handle))
        seen.add(handle)
    return options


def _mirror_preview_table(preview):
    rows = []
    for product in (preview or {}).get("previews") or []:
        handle = product.get("handle") or ""
        title = product.get("product_title") or handle
        last_synced = _format_time(product.get("last_mirror_synced_at"))
        if product.get("error"):
            rows.append(
                {
                    "Product": title,
                    "Handle": handle,
                    "Metafield": "error",
                    "Shopify before": "",
                    "Supabase source": product.get("error"),
                    "Will update": "No",
                    "Last mirror synced": last_synced,
                }
            )
            continue
        for change in product.get("changes") or []:
            if change.get("key") not in SHOPIFY_MIRROR_METAFIELD_KEYS:
                continue
            rows.append(
                {
                    "Product": title,
                    "Handle": handle,
                    "Metafield": change.get("key") or "",
                    "Shopify before": change.get("shopify_before", ""),
                    "Supabase source": change.get("supabase_after", ""),
                    "Will update": "Yes" if change.get("will_update") else "No",
                    "Last mirror synced": last_synced,
                }
            )
    return rows


def _mirror_result_table(result):
    rows = []
    for item in (result or {}).get("results") or []:
        source = item.get("source_values") or {}
        before = {
            row.get("key"): row.get("value")
            for row in item.get("metafields_before") or []
            if row.get("key")
        }
        after = {
            row.get("key"): row.get("value")
            for row in item.get("metafields_after") or []
            if row.get("key")
        }
        for key in SHOPIFY_MIRROR_METAFIELD_KEYS:
            rows.append(
                {
                    "Handle": item.get("handle") or "",
                    "Status": "Shopify mirror updated" if item.get("status") == "updated" else "Shopify mirror failed",
                    "Metafield": key,
                    "Supabase source": source.get(key, ""),
                    "Shopify before": before.get(key, ""),
                    "Shopify after": after.get(key, ""),
                    "Error": item.get("error") or "",
                    "Last mirror synced": _format_time(item.get("last_mirror_synced_at")),
                }
            )
    return rows


def _selected_mirror_handles(selected_labels, options):
    by_label = {label: handle for label, handle in options}
    return [by_label[label] for label in selected_labels or [] if by_label.get(label)]


def _preview_shopify_mirror(backend, handles, *, sync_all_active=False):
    config = shopify_sync.get_config()
    if not config.get("configured"):
        raise ValueError("Shopify is not configured.")
    if sync_all_active:
        return backend.preview_shopify_edition_metafield_mirror_for_active_products(
            config=config,
            limit=5000,
        )
    return backend.preview_shopify_edition_metafield_mirror_for_handles(
        handles,
        config=config,
    )


def _push_shopify_mirror(backend, handles, *, sync_all_active=False):
    config = shopify_sync.get_config()
    if not config.get("configured"):
        raise ValueError("Shopify is not configured.")
    if sync_all_active:
        return backend.reconcile_shopify_edition_metafields(
            config=config,
            limit=5000,
        )
    return backend.sync_product_edition_metafields_for_handles(
        handles,
        config=config,
    )


def _apply_shopify_mirror_result(rows, originals, result):
    now = _now_iso()
    by_handle = {
        str(item.get("handle") or "").strip(): item
        for item in (result or {}).get("results") or []
        if str(item.get("handle") or "").strip()
    }
    original_by_key = {
        _stable_row_key(row): _normalise_row(row)
        for row in originals
        if _stable_row_key(row)
    }
    updated_rows = []
    updated_originals = []
    errors = {}
    for row in rows:
        updated = _normalise_row(row)
        handle = str(updated.get("handle") or "").strip()
        key = _stable_row_key(updated)
        mirror = by_handle.get(handle)
        if mirror:
            if mirror.get("status") == "updated":
                updated["sync_status"] = "Shopify mirror updated"
                updated["sync_error"] = ""
            else:
                updated["sync_status"] = "Shopify mirror failed"
                updated["sync_error"] = mirror.get("error") or "Shopify mirror failed"
                errors[key or handle] = updated["sync_error"]
            updated["last_synced_at"] = now
            updated_originals.append(deepcopy(updated))
        else:
            updated_originals.append(deepcopy(original_by_key.get(key, updated)))
        updated_rows.append(updated)
    st.session_state[ROWS_KEY] = updated_rows
    st.session_state[ORIGINAL_ROWS_KEY] = updated_originals
    st.session_state[EDITOR_ROWS_KEY] = deepcopy(updated_rows)
    st.session_state[ERRORS_KEY] = errors
    _write_snapshot(updated_rows, updated_originals, meta={"mirror_status": "failed" if errors else "updated"})
    _invalidate_edition_ops_cache(bump_orders=False)
    _bump_editor_version()


def _pending_shopify_mirror_handles(rows):
    handles = []
    seen = set()
    pending_statuses = {"saved in supabase", "shopify mirror failed", "shopify mirror pending"}
    for row in rows:
        normalised = _normalise_row(row)
        status = str(normalised.get("sync_status") or "").strip().casefold()
        handle = str(normalised.get("handle") or "").strip()
        if status in pending_statuses and handle and handle not in seen:
            handles.append(handle)
            seen.add(handle)
    return handles


def _render_shopify_mirror_controls(backend, rows, rows_to_save):
    pending_handles = _pending_shopify_mirror_handles(rows)
    disabled = not backend or bool(rows_to_save) or not pending_handles
    if st.button("Push Metafield", use_container_width=True, disabled=disabled):
        try:
            result = _push_shopify_mirror(
                backend,
                pending_handles,
                sync_all_active=False,
            )
            st.session_state[SHOPIFY_MIRROR_RESULT_KEY] = result
            st.session_state[SHOPIFY_MIRROR_PREVIEW_KEY] = None
            _apply_shopify_mirror_result(
                [_normalise_row(row) for row in st.session_state.get(ROWS_KEY, [])],
                [_normalise_row(row) for row in st.session_state.get(ORIGINAL_ROWS_KEY, [])],
                result,
            )
            st.session_state[NOTICE_KEY] = (
                f"Shopify metafield pushed for {result.get('synced') or 0} saved product(s). "
                f"Failed: {result.get('skipped') or result.get('failed') or 0}. "
                "Supabase remained the source of truth."
            )
            st.rerun()
        except Exception as error:
            st.session_state[SHOPIFY_MIRROR_RESULT_KEY] = {"errors": [str(error)], "results": []}
            st.error(f"Shopify metafield push failed: {error}")


def _apply_save_errors(rows, originals, rows_to_save, errors):
    now = _now_iso()
    attempted_keys = {_stable_row_key(row) for row in rows_to_save if _stable_row_key(row)}
    original_by_key = {
        _stable_row_key(row): _normalise_row(row)
        for row in originals
        if _stable_row_key(row)
    }
    updated_rows = []
    updated_originals = []
    for row in rows:
        normalised = _normalise_row(row)
        key = _stable_row_key(normalised)
        if key in errors:
            normalised["sync_status"] = "Error"
            normalised["sync_error"] = errors[key]
            updated_originals.append(deepcopy(original_by_key.get(key, normalised)))
        elif key in attempted_keys:
            normalised["sync_status"] = "Saved in Supabase"
            normalised["sync_error"] = ""
            normalised["last_synced_at"] = now
            updated_originals.append(deepcopy(normalised))
        else:
            updated_originals.append(deepcopy(original_by_key.get(key, normalised)))
        updated_rows.append(normalised)
    st.session_state[ROWS_KEY] = updated_rows
    st.session_state[ORIGINAL_ROWS_KEY] = updated_originals
    st.session_state[EDITOR_ROWS_KEY] = deepcopy(updated_rows)
    st.session_state[ERRORS_KEY] = errors
    _write_snapshot(updated_rows, updated_originals, meta={"mirror_status": "failed" if errors else "pending"})
    _invalidate_edition_ops_cache(bump_orders=True)
    _bump_editor_version()


def _load_active_products_from_shopify():
    config = shopify_sync.get_config()
    if not config.get("configured"):
        raise ValueError(
            "Store connection is not configured yet. Ask a developer before refreshing products."
        )
    backend = _configured_supabase_backend()
    if backend:
        result = backend.sync_shopify_products_to_supabase(config=config, mode="incremental")
        _invalidate_edition_ops_cache(bump_orders=True)
        snapshot = _load_supabase_snapshot() or {
            "rows": [],
            "original_rows": [],
            "last_refreshed_from_shopify": _now_iso(),
        }
        st.session_state[ROWS_KEY] = snapshot["rows"]
        st.session_state[ORIGINAL_ROWS_KEY] = snapshot["original_rows"]
        st.session_state[EDITOR_ROWS_KEY] = deepcopy(snapshot["rows"])
        st.session_state[ERRORS_KEY] = {}
        st.session_state[IMPORT_WARNINGS_KEY] = []
        st.session_state[META_KEY] = {
            "last_refreshed_from_shopify": snapshot.get("last_refreshed_from_shopify") or _now_iso(),
            "saved_at": snapshot.get("saved_at") or _now_iso(),
        }
        _write_snapshot(snapshot["rows"], snapshot["original_rows"], meta=st.session_state[META_KEY])
        st.session_state[NOTICE_KEY] = (
            f"Synced products into Supabase. {result.get('products_seen', len(snapshot['rows']))} product(s) checked."
        )
        _clear_editor_state()
        _bump_editor_version()
        return
    loaded = shopify_sync.fetch_edition_ops_active_products(
        max_products=config.get("edition_ops_max_products", 500),
        page_size=50,
        config=config,
    )
    refreshed_at = _now_iso()
    rows = [_row_from_product(product) for product in loaded.get("products") or []]
    st.session_state[ROWS_KEY] = rows
    st.session_state[ORIGINAL_ROWS_KEY] = deepcopy(rows)
    st.session_state[EDITOR_ROWS_KEY] = deepcopy(rows)
    st.session_state[ERRORS_KEY] = {}
    st.session_state[IMPORT_WARNINGS_KEY] = []
    _write_snapshot(
        rows,
        deepcopy(rows),
        meta={"last_refreshed_from_shopify": refreshed_at},
    )
    _invalidate_edition_ops_cache(bump_orders=True)
    st.session_state[NOTICE_KEY] = f"Refreshed {len(rows)} active products."
    _clear_editor_state()
    _bump_editor_version()


def _reload_products_from_supabase():
    backend = _configured_supabase_backend()
    if not backend:
        raise ValueError("Supabase is not configured for Edition Ops.")
    _invalidate_edition_ops_cache()
    snapshot = _load_supabase_snapshot() or {
        "rows": [],
        "original_rows": [],
        "last_refreshed_from_shopify": "",
        "saved_at": _now_iso(),
    }
    rows = [_normalise_row(row) for row in snapshot.get("rows") or []]
    originals = [_normalise_row(row) for row in (snapshot.get("original_rows") or rows)]
    st.session_state[ROWS_KEY] = rows
    st.session_state[ORIGINAL_ROWS_KEY] = deepcopy(originals)
    st.session_state[EDITOR_ROWS_KEY] = deepcopy(rows)
    st.session_state[LOADED_AT_KEY] = _now_iso()
    st.session_state[ERRORS_KEY] = {}
    st.session_state[IMPORT_WARNINGS_KEY] = []
    st.session_state[META_KEY] = {
        "last_refreshed_from_shopify": snapshot.get("last_refreshed_from_shopify") or "",
        "saved_at": snapshot.get("saved_at") or _now_iso(),
        "mirror_status": snapshot.get("mirror_status") or "",
        "source": "supabase",
        "cached": False,
        "limit": snapshot.get("limit") or EDITION_OPS_PRODUCT_LIMIT,
    }
    st.session_state[LOAD_ERROR_KEY] = ""
    st.session_state[LOAD_DIAGNOSTIC_KEY] = dict(snapshot.get("database_read") or {})
    _write_snapshot(rows, originals, meta=st.session_state[META_KEY])
    st.session_state[NOTICE_KEY] = f"Reloaded {len(rows)} product row(s) from Supabase."
    st.session_state[SNAPSHOT_LOADED_KEY] = True
    _clear_editor_state()
    _bump_editor_version()


def _format_shopify_product_sync_summary(result):
    result = result or {}
    errors = list(result.get("errors") or [])
    errors.extend(result.get("variant_sync_errors") or [])
    message = " · ".join(
        (
            f"{int(result.get('new_products_inserted') or 0)} new products added",
            f"{int(result.get('existing_products_skipped') or 0)} existing products skipped",
            f"{int(result.get('shopify_metafields_pushed') or 0)} metafield mirrors updated",
            f"{len(errors)} failures",
            f"Completed in {float(result.get('duration_seconds') or 0):.1f} seconds",
        )
    )
    if errors:
        first_errors = " | ".join(str(error)[:180] for error in errors[:3])
        message = f"{message} First errors: {first_errors}"
    return message


def _format_full_product_reconciliation_summary(result):
    result = result or {}
    errors = list(result.get("errors") or [])
    errors.extend(result.get("variant_sync_errors") or [])
    return (
        "Full Product Reconciliation complete. "
        f"{int(result.get('products_fetched') or 0)} fetched; "
        f"{int(result.get('new_products_inserted') or 0)} added; "
        f"{int(result.get('existing_products_updated') or 0)} identity/display updates; "
        f"{int(result.get('existing_products_skipped') or 0)} unchanged; "
        f"{len(errors)} failures."
    )


def _mark_synced(rows, originals, results):
    now = _now_iso()
    ok_ids = {result["shopify_product_id"] for result in results if result.get("ok")}
    failed = {
        result["shopify_product_id"]: result.get("message") or "Sync failed"
        for result in results
        if not result.get("ok")
    }
    original_by_id = {row.get("shopify_product_gid"): row for row in originals}
    new_rows = []
    new_originals = []

    for row in rows:
        product_id = row.get("shopify_product_gid")
        updated = _normalise_row(row)
        if product_id in ok_ids:
            updated["sync_status"] = "Shopify mirror updated"
            updated["sync_error"] = ""
            updated["last_synced_at"] = now
            new_originals.append(deepcopy(updated))
        elif product_id in failed:
            updated["sync_status"] = "Shopify mirror failed / retry"
            updated["sync_error"] = failed[product_id]
            updated["last_synced_at"] = now
            new_originals.append(deepcopy(updated))
        else:
            new_originals.append(deepcopy(original_by_id.get(product_id, updated)))
        new_rows.append(updated)

    st.session_state[ROWS_KEY] = new_rows
    st.session_state[ORIGINAL_ROWS_KEY] = new_originals
    st.session_state[EDITOR_ROWS_KEY] = deepcopy(new_rows)
    st.session_state[ERRORS_KEY] = failed
    _write_snapshot(
        new_rows,
        new_originals,
        meta={"mirror_status": "failed" if failed else "updated"},
    )
    _invalidate_edition_ops_cache(bump_orders=True)
    _bump_editor_version()


def _apply_row_errors_only(rows, originals, errors):
    original_by_key = {
        _stable_row_key(row): _normalise_row(row)
        for row in originals
        if _stable_row_key(row)
    }
    updated_rows = []
    updated_originals = []
    for row in rows:
        normalised = _normalise_row(row, preserve_derived=False)
        key = _stable_row_key(normalised)
        if key in errors:
            normalised["sync_status"] = "Error"
            normalised["sync_error"] = errors[key]
        updated_rows.append(normalised)
        updated_originals.append(deepcopy(original_by_key.get(key, normalised)))
    st.session_state[ROWS_KEY] = updated_rows
    st.session_state[ORIGINAL_ROWS_KEY] = updated_originals
    st.session_state[EDITOR_ROWS_KEY] = deepcopy(updated_rows)
    st.session_state[ERRORS_KEY] = dict(errors or {})
    _write_snapshot(updated_rows, updated_originals, meta={"mirror_status": "validation_failed"})


def _apply_combined_save_result(rows, originals, rows_to_save, supabase_errors, shopify_errors, shopify_success_keys):
    now = _now_iso()
    attempted_keys = {_stable_row_key(row) for row in rows_to_save if _stable_row_key(row)}
    original_by_key = {
        _stable_row_key(row): _normalise_row(row)
        for row in originals
        if _stable_row_key(row)
    }
    errors = {}
    updated_rows = []
    updated_originals = []
    for row in rows:
        normalised = _normalise_row(row, preserve_derived=False)
        key = _stable_row_key(normalised)
        if key in supabase_errors:
            normalised["sync_status"] = "Error"
            normalised["sync_error"] = supabase_errors[key]
            errors[key] = normalised["sync_error"]
            updated_originals.append(deepcopy(original_by_key.get(key, normalised)))
        elif key in shopify_errors:
            normalised["sync_status"] = "needs_shopify_sync"
            normalised["sync_error"] = shopify_errors[key]
            normalised["last_synced_at"] = now
            errors[key] = normalised["sync_error"]
            updated_originals.append(deepcopy(normalised))
        elif key in shopify_success_keys:
            normalised["sync_status"] = "Synced"
            normalised["sync_error"] = ""
            normalised["last_synced_at"] = now
            updated_originals.append(deepcopy(normalised))
        elif key in attempted_keys:
            normalised["sync_status"] = "Saved locally"
            normalised["sync_error"] = ""
            normalised["last_synced_at"] = now
            updated_originals.append(deepcopy(normalised))
        else:
            updated_originals.append(deepcopy(original_by_key.get(key, normalised)))
        updated_rows.append(normalised)
    st.session_state[ROWS_KEY] = updated_rows
    st.session_state[ORIGINAL_ROWS_KEY] = updated_originals
    st.session_state[EDITOR_ROWS_KEY] = deepcopy(updated_rows)
    st.session_state[ERRORS_KEY] = errors
    _write_snapshot(updated_rows, updated_originals, meta={"mirror_status": "failed" if errors else "updated"})
    if not supabase_errors:
        _clear_editor_state()
        _invalidate_edition_ops_cache(bump_orders=False)
        _bump_editor_version()


def _mark_supabase_saved_without_shopify(rows, originals, row_ids):
    now = _now_iso()
    saved_ids = set(row_ids or [])
    new_rows = []
    new_originals = []
    for row in rows:
        updated = _normalise_row(row)
        row_key = _stable_row_key(updated)
        if row_key in saved_ids:
            updated["sync_status"] = "Saved in Supabase"
            updated["sync_error"] = ""
            updated["last_synced_at"] = now
            new_originals.append(deepcopy(updated))
        else:
            new_originals.append(deepcopy(_normalise_row(row)))
        new_rows.append(updated)
    st.session_state[ROWS_KEY] = new_rows
    st.session_state[ORIGINAL_ROWS_KEY] = new_originals
    st.session_state[EDITOR_ROWS_KEY] = deepcopy(new_rows)
    st.session_state[ERRORS_KEY] = {}
    _write_snapshot(new_rows, new_originals, meta={"mirror_status": "not_mirrored"})


def _is_archive_transition(row, original):
    if not original:
        return False
    return bool(original.get("edition_enabled")) and not bool(_normalise_row(row).get("edition_enabled"))


def _highest_assigned_from_original(original):
    if not original:
        return 0
    return _coerce_nonnegative_int(original.get("edition_sold_count"), 0)


def _is_manual_lower_correction(row, original):
    if not original or _is_archive_transition(row, original):
        return False
    normalised = _normalise_row(row, preserve_derived=False)
    highest_assigned = _highest_assigned_from_original(original)
    return highest_assigned > 0 and _coerce_int(normalised.get("edition_next_number"), 1) < highest_assigned + 1


def _manual_lower_warning(row, original):
    if not _is_manual_lower_correction(row, original):
        return ""
    return "Warning: this product has assigned editions above this next number. Manual correction saved."


def _save_changed_rows(edited_rows=None, source_rows=None):
    current_rows = [_normalise_row(row) for row in st.session_state.get(ROWS_KEY, [])]
    originals = [deepcopy(_normalise_row(row)) for row in st.session_state.get(ORIGINAL_ROWS_KEY, [])]
    if edited_rows is not None:
        submitted_source_rows = (
            [_normalise_row(row) for row in source_rows]
            if source_rows is not None
            else current_rows
        )
        submitted_rows = _submitted_editor_rows(edited_rows, submitted_source_rows)
        if source_rows is None:
            current_rows = submitted_rows
        else:
            submitted_by_key = {
                _stable_row_key(row): _normalise_row(row)
                for row in submitted_rows
                if _stable_row_key(row)
            }
            current_rows = [
                submitted_by_key.get(_stable_row_key(row), row)
                for row in current_rows
            ]
    rows = _mark_current_changes(_prepare_rows_for_save(current_rows, originals), originals)
    st.session_state[ROWS_KEY] = rows
    st.session_state[EDITOR_ROWS_KEY] = deepcopy(rows)
    st.session_state[ORIGINAL_ROWS_KEY] = originals

    dirty_rows = [_normalise_row(row, preserve_derived=False) for row in _changed_rows(rows, originals)]
    dirty_rows_by_key = {
        _stable_row_key(row): row
        for row in dirty_rows
        if _stable_row_key(row)
    }
    rows_to_save = list(dirty_rows_by_key.values())
    dirty_keys_for_log = sorted(dirty_rows_by_key)
    st.session_state["edition_ops_last_dirty_count"] = len(dirty_keys_for_log)
    st.session_state["edition_ops_last_dirty_keys"] = dirty_keys_for_log
    print(
        f"PERF Edition Ops save dirty_count={len(dirty_keys_for_log)} dirty_keys={','.join(dirty_keys_for_log[:12])}",
        flush=True,
    )
    if not dirty_rows_by_key:
        st.session_state[NOTICE_KEY] = "No changes to save."
        st.session_state[NOTICE_LEVEL_KEY] = "warning"
        return
    backend = _configured_supabase_backend()
    if not backend:
        st.session_state[NOTICE_KEY] = (
            "Supabase is not configured. Edition Ops saves stay locked until the ledger is available."
        )
        st.session_state[NOTICE_LEVEL_KEY] = "error"
        return
    supabase_errors = {}
    shopify_errors = {}
    dirty_keys = set(dirty_rows_by_key)
    original_by_key = _original_rows_by_key(originals)
    for row in rows_to_save:
        message = _save_validation_error(row, original_by_key.get(_stable_row_key(row)))
        if message:
            supabase_errors[_stable_row_key(row)] = message
    if supabase_errors:
        _apply_row_errors_only(rows, originals, supabase_errors)
        st.session_state[NOTICE_KEY] = " ".join(supabase_errors.values())
        st.session_state[NOTICE_LEVEL_KEY] = "error"
        return

    supabase_saved_keys = set()
    manual_lower_warnings = {}
    dirty_rows_to_save = [row for row in rows_to_save if _stable_row_key(row) in dirty_keys]
    if dirty_rows_to_save and hasattr(backend, "update_edition_products_batch"):
        batch_rows = []
        for row in dirty_rows_to_save:
            normalised = _normalise_row(row, preserve_derived=False)
            original = original_by_key.get(_stable_row_key(normalised))
            archive_transition = _is_archive_transition(normalised, original)
            manual_lower = _is_manual_lower_correction(normalised, original)
            if manual_lower:
                manual_lower_warnings[_stable_row_key(normalised)] = _manual_lower_warning(normalised, original)
            batch_rows.append(
                {
                    "row_key": _stable_row_key(normalised),
                    "edition_product_id": normalised.get("edition_product_id"),
                    "handle": normalised.get("handle"),
                    "edition_name": normalised.get("edition_label"),
                    "edition_total": normalised.get("edition_total"),
                    "next_edition_number": normalised.get("edition_next_number"),
                    "active": bool(normalised.get("edition_enabled")),
                    "sold_out": normalised.get("edition_remaining") <= 0,
                    "status": "sold_out" if normalised.get("edition_remaining") <= 0 else None,
                    "reason": (
                        "Edition archived from Edition Ops"
                        if archive_transition
                        else "manual_next_number_lowered"
                        if manual_lower
                        else "Edition Ops save"
                    ),
                    "manual_next_number_lowered": manual_lower,
                    "highest_assigned_edition": _highest_assigned_from_original(original),
                }
            )
        try:
            results = backend.update_edition_products_batch(batch_rows, reason="Edition Ops save")
        except Exception as error:
            results = [
                {
                    "ok": False,
                    "handle": row.get("handle"),
                    "key": row.get("row_key"),
                    "message": str(error),
                }
                for row in batch_rows
            ]
        for result in results or []:
            if not result.get("ok"):
                supabase_errors[result.get("key") or result.get("handle") or ""] = result.get("message") or "Save failed"
            else:
                supabase_saved_keys.add(result.get("key") or result.get("handle") or "")
    elif dirty_rows_to_save:
        for row in dirty_rows_to_save:
            normalised = _normalise_row(row, preserve_derived=False)
            key = _stable_row_key(normalised) or normalised.get("handle")
            original = original_by_key.get(_stable_row_key(normalised))
            archive_transition = _is_archive_transition(normalised, original)
            manual_lower = _is_manual_lower_correction(normalised, original)
            if manual_lower:
                manual_lower_warnings[key] = _manual_lower_warning(normalised, original)
            try:
                backend.update_edition_product(
                    normalised.get("handle"),
                    edition_name=normalised.get("edition_label"),
                    edition_total=normalised.get("edition_total"),
                    next_edition_number=normalised.get("edition_next_number"),
                    active=bool(normalised.get("edition_enabled")),
                    sold_out=normalised.get("edition_remaining") <= 0,
                    status="sold_out" if normalised.get("edition_remaining") <= 0 else None,
                    reason=(
                        "Edition archived from Edition Ops"
                        if archive_transition
                        else "manual_next_number_lowered"
                        if manual_lower
                        else "Edition Ops save"
                    ),
                )
                supabase_saved_keys.add(key)
            except Exception as error:
                supabase_errors[key] = str(error)

    mirror_rows = []
    mirror_keys = set()
    for row in rows_to_save:
        key = _stable_row_key(row)
        if not key or key in supabase_errors:
            continue
        if key in dirty_keys and key not in supabase_saved_keys:
            continue
        if key in dirty_keys:
            mirror_rows.append(_normalise_row(row, preserve_derived=False))
            mirror_keys.add(key)

    mirror_success_keys = set()
    if mirror_rows:
        try:
            config = shopify_sync.get_config()
            if not config.get("configured"):
                raise ValueError("Shopify is not configured.")
            if not hasattr(backend, "sync_edition_ops_metafields_for_rows"):
                raise ValueError("Edition Ops Shopify metafield sync is not available.")
            mirror_result = backend.sync_edition_ops_metafields_for_rows(
                mirror_rows,
                config=config,
                ensure_schema_first=False,
            )
            result_by_key = {
                str(item.get("row_key") or item.get("handle") or "").strip(): item
                for item in mirror_result.get("results") or []
                if str(item.get("row_key") or item.get("handle") or "").strip()
            }
            for row in mirror_rows:
                key = _stable_row_key(row)
                item = result_by_key.get(key) or result_by_key.get(row.get("handle"))
                if item and item.get("status") == "updated":
                    mirror_success_keys.add(key)
                else:
                    shopify_errors[key] = (
                        (item or {}).get("error")
                        or (item or {}).get("message")
                        or "Shopify metafield push failed."
                    )
        except Exception as error:
            for row in mirror_rows:
                shopify_errors[_stable_row_key(row)] = str(error)

    _apply_combined_save_result(
        rows,
        originals,
        rows_to_save,
        supabase_errors,
        shopify_errors,
        mirror_success_keys,
    )
    if supabase_errors:
        saved_count = max(len(dirty_keys) - len(supabase_errors), 0)
        st.session_state[NOTICE_KEY] = f"Saved {saved_count} Edition Ops change(s). {len(supabase_errors)} product(s) could not be saved."
        st.session_state[NOTICE_LEVEL_KEY] = "error"
    elif shopify_errors:
        lower_warning_text = " ".join(
            manual_lower_warnings[key]
            for key in sorted(manual_lower_warnings)
            if key in supabase_saved_keys
        )
        suffix = f" {lower_warning_text}" if lower_warning_text else ""
        st.session_state[NOTICE_KEY] = f"Supabase saved, Shopify mirror failed / retry needed for {len(shopify_errors)} product(s).{suffix}"
        st.session_state[NOTICE_LEVEL_KEY] = "warning"
    elif manual_lower_warnings:
        warnings = []
        for key in sorted(manual_lower_warnings):
            if key in supabase_saved_keys:
                warnings.append(manual_lower_warnings[key])
        st.session_state[NOTICE_KEY] = f"Saved {len(supabase_saved_keys)} Edition Ops change(s). " + " ".join(warnings)
        st.session_state[NOTICE_LEVEL_KEY] = "warning"
    else:
        st.session_state[NOTICE_KEY] = f"Saved {len(supabase_saved_keys)} Edition Ops change(s)."
        st.session_state[NOTICE_LEVEL_KEY] = "success"


def _rows_from_editor(value):
    if hasattr(value, "to_dict"):
        return [dict(row) for row in value.to_dict("records")]
    return [dict(row) for row in (value or [])]


def _editor_widget_edited_rows():
    try:
        state = st.session_state.get(EDITOR_KEY)
    except AttributeError:
        return {}
    if not isinstance(state, dict):
        return {}
    edited = state.get("edited_rows") or {}
    return edited if isinstance(edited, dict) else {}


def _apply_editor_widget_edits(rows):
    edited_by_index = _editor_widget_edited_rows()
    if not edited_by_index:
        return [_normalise_row(row, preserve_derived=False) for row in rows]
    merged = [_normalise_row(row, preserve_derived=False) for row in rows]
    for raw_index, changes in edited_by_index.items():
        if not isinstance(changes, dict):
            continue
        try:
            index = int(raw_index)
        except (TypeError, ValueError):
            continue
        if index < 0 or index >= len(merged):
            continue
        updated = dict(merged[index])
        updated.update(changes)
        merged[index] = _normalise_row(updated, preserve_derived=False)
    return merged


def _submitted_editor_rows(edited_rows, source_rows):
    merged_rows = _merge_visible_rows(_rows_from_editor(edited_rows), source_rows)
    return _apply_editor_widget_edits(merged_rows)


def _merge_visible_rows(edited_rows, source_rows):
    source_by_key = {
        _stable_row_key(row): _normalise_row(row)
        for row in source_rows
        if _stable_row_key(row)
    }
    merged = []
    for index, row in enumerate(edited_rows):
        key = _stable_row_key(row)
        source = source_by_key.get(key) if key else None
        if source is None:
            source = source_rows[index] if index < len(source_rows) else {}
        updated = dict(source)
        updated.update(row)
        merged.append(_normalise_row(updated, preserve_derived=False))
    return merged


def _export_csv(rows):
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        normalised = _normalise_row(row)
        export_row = {field: normalised.get(field, "") for field in CSV_COLUMNS}
        export_row["edition_enabled"] = "true" if normalised.get("edition_enabled") else "false"
        writer.writerow(export_row)
    return buffer.getvalue().encode("utf-8-sig")


def _validate_import_int(raw_value, field_name, row_label, warnings):
    if str(raw_value or "").strip() == "":
        return None
    value = _parse_positive_int(raw_value)
    if value == "invalid":
        warnings.append(f"{row_label}: {field_name} must be 1 or higher.")
        return "invalid"
    return value


def _validate_import_nonnegative_int(raw_value, field_name, row_label, warnings):
    if str(raw_value or "").strip() == "":
        return None
    value = _coerce_nonnegative_int(raw_value, None)
    if value is None:
        warnings.append(f"{row_label}: {field_name} must be 0 or higher.")
        return "invalid"
    return value


def _apply_csv_updates_to_rows(rows, csv_text):
    rows = [_normalise_row(row) for row in rows]
    by_gid = {row.get("shopify_product_gid"): index for index, row in enumerate(rows) if row.get("shopify_product_gid")}
    by_handle = {row.get("handle"): index for index, row in enumerate(rows) if row.get("handle")}
    by_title = {
        _normalise_title(row.get("product_title")): index
        for index, row in enumerate(rows)
        if _normalise_title(row.get("product_title"))
    }
    warnings = []
    imported_count = 0
    changed_rows = []
    allow_new_rows = not rows

    reader = csv.DictReader(io.StringIO(csv_text))
    for line_number, csv_row in enumerate(reader, start=2):
        gid = str(_csv_value(csv_row, "shopify_product_gid", "shopify product gid", "product id") or "").strip()
        handle = str(_csv_value(csv_row, "handle", "Handle") or "").strip()
        product_title = str(_csv_value(csv_row, "product_title", "Product title", "title") or "").strip()
        match_index = by_gid.get(gid) if gid else None
        if match_index is None and handle:
            match_index = by_handle.get(handle)
        if match_index is None and product_title:
            match_index = by_title.get(_normalise_title(product_title))
        row_label = handle or product_title or gid or f"CSV line {line_number}"
        if match_index is None:
            if not allow_new_rows:
                warnings.append(f"{row_label}: not in the loaded table, ignored.")
                continue
            match_index = len(rows)
            rows.append(
                _normalise_row(
                    {
                        "shopify_product_gid": gid,
                        "legacy_resource_id": _csv_value(csv_row, "legacy_resource_id", "Legacy ID"),
                        "product_title": product_title,
                        "handle": handle,
                        "status": _csv_value(csv_row, "status", "Status") or "ACTIVE",
                        "online_store_url": _csv_value(csv_row, "online_store_url", "Open live product"),
                        "admin_url": _csv_value(csv_row, "admin_url", "Open Admin"),
                    }
                )
            )
            if gid:
                by_gid[gid] = match_index
            if handle:
                by_handle[handle] = match_index
            if product_title:
                by_title[_normalise_title(product_title)] = match_index

        total = _validate_import_int(
            _csv_value(csv_row, "edition_total", "Edition total", "edition total"),
            "edition_total",
            row_label,
            warnings,
        )
        next_number = _validate_import_int(
            _csv_value(csv_row, "edition_next_number", "Next edition number", "edition next number", "next edition"),
            "edition_next_number",
            row_label,
            warnings,
        )
        if total == "invalid" or next_number == "invalid":
            continue
        enabled_value = _csv_value(csv_row, "edition_enabled", "Enabled", "edition enabled")
        missing_required = []
        if str(enabled_value or "").strip() == "":
            missing_required.append("edition_enabled")
        if total is None:
            missing_required.append("edition_total")
        if next_number is None:
            missing_required.append("edition_next_number")
        if missing_required:
            warnings.append(f"{row_label}: missing required field(s): {', '.join(missing_required)}.")
            continue

        sold_count = _validate_import_nonnegative_int(
            _csv_value(csv_row, "edition_sold_count", "Edition sold count", "Sold count", "sold_count"),
            "edition_sold_count",
            row_label,
            warnings,
        )
        edition_remaining = _validate_import_nonnegative_int(
            _csv_value(csv_row, "edition_remaining", "Edition remaining", "remaining", "Remaining"),
            "edition_remaining",
            row_label,
            warnings,
        )
        if sold_count == "invalid" or edition_remaining == "invalid":
            continue
        if sold_count is None:
            sold_count = max(next_number - 1, 0)
        if edition_remaining is None:
            edition_remaining = max(total - sold_count, 0)
        edition_status = str(
            _csv_value(csv_row, "edition_status", "Edition status", "widget_status", "Widget status")
            or ""
        ).strip() or _widget_status(edition_remaining)

        updated = dict(rows[match_index])
        updated["edition_enabled"] = _coerce_bool(enabled_value)
        updated["edition_total"] = total
        updated["edition_next_number"] = next_number
        updated["edition_sold_count"] = sold_count
        updated["edition_remaining"] = edition_remaining
        updated["edition_status"] = edition_status
        label_value = _csv_value(csv_row, "edition_label", "Edition label", "edition label")
        if str(label_value or "").strip():
            updated["edition_label"] = str(label_value).strip()
        normalised = _normalise_row(updated)
        original = _normalise_row(rows[match_index])
        if _editable_snapshot(normalised) != _editable_snapshot(original):
            normalised["sync_status"] = "Needs Sync"
            normalised["sync_error"] = ""
            imported_count += 1
            changed_rows.append(normalised)
            rows[match_index] = normalised

    return rows, changed_rows, imported_count, warnings


def _apply_csv_import(uploaded_file):
    if uploaded_file is None:
        st.session_state[IMPORT_WARNINGS_KEY] = ["Choose a CSV file first."]
        return False

    try:
        raw_csv = uploaded_file.getvalue()
        try:
            text = raw_csv.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw_csv.decode("utf-8", errors="replace")
        rows, changed_rows, changed_count, warnings = _apply_csv_updates_to_rows(
            st.session_state.get(ROWS_KEY, []),
            text,
        )
    except Exception as error:
        st.session_state[IMPORT_WARNINGS_KEY] = [f"CSV import failed: {error}"]
        return False

    originals = [_normalise_row(row) for row in st.session_state.get(ORIGINAL_ROWS_KEY, [])]
    st.session_state[ROWS_KEY] = rows
    st.session_state[NOTICE_KEY] = f"Imported and replaced edition fields for {changed_count} rows. Click Save Changes to sync."
    st.session_state[IMPORT_WARNINGS_KEY] = warnings
    st.session_state[ORIGINAL_ROWS_KEY] = originals
    st.session_state[EDITOR_ROWS_KEY] = deepcopy(rows)
    _clear_editor_state()
    _write_snapshot(rows, originals)
    _bump_editor_version()
    return True


def _editor_payload(row):
    normalised = _normalise_row(row)
    keys = ("edition_product_id", "shopify_product_gid", *VISIBLE_COLUMNS)
    return {key: normalised.get(key) for key in keys}


def _editor_page_rows(rows):
    total_rows = len(rows)
    page_count = max((total_rows + EDITION_OPS_EDITOR_PAGE_SIZE - 1) // EDITION_OPS_EDITOR_PAGE_SIZE, 1)
    page_index = 0
    if page_count > 1 and hasattr(st, "selectbox"):
        labels = []
        for index in range(page_count):
            start = index * EDITION_OPS_EDITOR_PAGE_SIZE + 1
            end = min((index + 1) * EDITION_OPS_EDITOR_PAGE_SIZE, total_rows)
            labels.append(f"Products {start}-{end} of {total_rows}")
        selected = st.selectbox(
            "Product rows",
            labels,
            key=EDITOR_PAGE_SELECTION_KEY,
            label_visibility="collapsed",
        )
        if selected in labels:
            page_index = labels.index(selected)
    previous_page = int(st.session_state.get(EDITOR_RENDERED_PAGE_KEY, -1))
    if previous_page != page_index:
        st.session_state.pop(EDITOR_KEY, None)
        st.session_state[EDITOR_RENDERED_PAGE_KEY] = page_index
    start = page_index * EDITION_OPS_EDITOR_PAGE_SIZE
    end = min(start + EDITION_OPS_EDITOR_PAGE_SIZE, total_rows)
    return rows[start:end], page_index, page_count


def _column_config():
    return {
        "product_title": st.column_config.TextColumn("Product title"),
        "handle": st.column_config.TextColumn("Handle"),
        "edition_enabled": st.column_config.CheckboxColumn("Enabled"),
        "edition_total": st.column_config.NumberColumn("Edition total", min_value=1, max_value=100000, step=1),
        "edition_next_number": st.column_config.NumberColumn("Next edition number", min_value=1, max_value=100000, step=1),
        "edition_sold_count": st.column_config.NumberColumn("Sold count"),
        "edition_remaining": st.column_config.NumberColumn("Remaining"),
        "edition_status": st.column_config.TextColumn("Status"),
        "sync_status": st.column_config.TextColumn("Sync status"),
        "admin_url": st.column_config.LinkColumn("Open Admin", display_text="Open"),
        "online_store_url": st.column_config.LinkColumn("Open live product", display_text="Open"),
    }


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


def _render_product_sync_diagnostics(backend, rows):
    ui_count = len(rows or [])
    if not backend or not hasattr(backend, "get_product_sync_diagnostics"):
        st.caption("Source: Supabase ledger")
        st.caption("Supabase connected: no")
        st.caption(f"Current table count shown in UI: {ui_count}")
        return
    try:
        diagnostics = backend.get_product_sync_diagnostics(ensure_schema_first=False)
    except Exception as error:
        st.caption("Source: Supabase ledger")
        st.caption("Supabase connected: no")
        st.caption(f"Product sync diagnostics unavailable: {error}")
        st.caption(f"Current table count shown in UI: {ui_count}")
        return

    supabase_count = int(diagnostics.get("edition_products_count") or 0)
    manual_result = st.session_state.get(MANUAL_PRODUCT_SYNC_RESULT_KEY) or diagnostics.get("last_product_sync_result") or {}
    manual_errors = list((manual_result or {}).get("errors") or [])
    manual_errors.extend((manual_result or {}).get("variant_sync_errors") or [])
    st.caption(f"Source: {diagnostics.get('source') or 'Supabase ledger'}")
    st.caption(f"Supabase connected: {'yes' if diagnostics.get('supabase_connected') else 'no'}")
    st.caption(f"edition_products count: {supabase_count}")
    st.caption(f"last product sync timestamp: {_format_time(diagnostics.get('last_product_sync_timestamp'))}")
    st.caption(f"last product sync status: {diagnostics.get('last_product_sync_status') or 'Unknown'}")
    st.caption(f"last product webhook timestamp: {_format_time(diagnostics.get('last_product_webhook_timestamp'))}")
    st.caption(f"last product webhook status: {diagnostics.get('last_product_webhook_status') or 'Unknown'}")
    if diagnostics.get("last_product_webhook_handle") or diagnostics.get("last_product_webhook_product"):
        st.caption(
            "last product webhook product: "
            f"{diagnostics.get('last_product_webhook_handle') or diagnostics.get('last_product_webhook_product')}"
        )
    st.caption(
        "manual sync result: "
        f"fetched {int((manual_result or {}).get('products_fetched') or (manual_result or {}).get('products_checked') or 0)}, "
        f"created {int((manual_result or {}).get('new_products_inserted') or 0)}, "
        f"updated {int((manual_result or {}).get('existing_products_updated') or 0)}, "
        f"skipped {int((manual_result or {}).get('existing_products_skipped') or 0)}, "
        f"errors {len(manual_errors)}"
    )
    st.caption(f"current table count shown in UI: {ui_count}")
    if diagnostics.get("error"):
        st.warning(f"Product sync diagnostics warning: {diagnostics.get('error')}")
    if diagnostics.get("last_product_webhook_error"):
        st.warning(f"Last product webhook error: {diagnostics.get('last_product_webhook_error')}")
    if supabase_count and supabase_count != ui_count:
        st.warning(
            f"UI table may be stale: Supabase has {supabase_count} edition product(s), "
            f"but this page is showing {ui_count}."
        )


def _plural(value, singular, plural=None):
    return f"{value} {singular if int(value) == 1 else (plural or singular + 's')}"


def _edition_ops_summary(rows, changed_rows, retry_rows):
    parts = [
        _plural(len(rows), "product") + " synced",
        _plural(len(changed_rows), "unsaved change"),
    ]
    retry_count = len(retry_rows)
    if retry_count:
        parts.append(_plural(retry_count, "needs Shopify sync", "need Shopify sync"))
    return " · ".join(parts)


def _render_notice():
    notice = st.session_state.get(NOTICE_KEY)
    if not notice:
        return
    level = str(st.session_state.get(NOTICE_LEVEL_KEY) or "success").strip().casefold()
    if level == "error":
        st.error(notice)
    elif level == "warning":
        st.warning(notice)
    else:
        st.success(notice)
    st.session_state[NOTICE_KEY] = ""
    st.session_state[NOTICE_LEVEL_KEY] = "success"


def _slot_caption(slot, message):
    if slot is not None and hasattr(slot, "caption"):
        slot.caption(message)
    else:
        st.caption(message)


def _render_save_changes_button(slot, *, disabled):
    target = slot if slot is not None and hasattr(slot, "button") else st
    if not hasattr(target, "button"):
        return
    clicked = target.button(
        "Save Changes",
        type="primary",
        use_container_width=True,
        disabled=disabled,
        key="edition-ops-save-changes",
    )
    if not clicked:
        return
    if slot is not None and hasattr(slot, "button"):
        slot.button(
            "Saving...",
            type="primary",
            use_container_width=True,
            disabled=True,
            key="edition-ops-save-changes-saving",
        )
    with st.spinner("Saving..."):
        _save_changed_rows()
    st.rerun()


def _render_advanced_controls(backend, rows):
    if not hasattr(st, "expander"):
        return
    with st.expander("Advanced", expanded=False):
        if st.button(
            "Load Sync Diagnostics",
            key="edition-ops-load-sync-diagnostics",
            use_container_width=True,
        ):
            diagnostic_started = time.perf_counter()
            print("PERF Edition Ops diagnostics start", flush=True)
            _render_product_sync_diagnostics(backend, rows)
            print(
                "PERF Edition Ops diagnostics done "
                f"duration_ms={int((time.perf_counter() - diagnostic_started) * 1000)}",
                flush=True,
            )
        else:
            st.caption("Sync diagnostics load only when requested.")
        st.caption("Checks only the newest Shopify products and adds products not already in Sports Cave OS.")
        action_cols = st.columns([1, 1, 1, 1])
        if action_cols[0].button("Pull New Products", use_container_width=True, disabled=not backend):
            sync_completed = False
            try:
                with st.spinner("Checking the newest Shopify products..."):
                    if not backend or not hasattr(backend, "sync_new_shopify_products_to_edition_ops"):
                        raise ValueError("New-product pull is not available.")
                    config = shopify_sync.get_config()
                    if not config.get("configured"):
                        raise ValueError("Shopify is not configured.")
                    sync_result = backend.sync_new_shopify_products_to_edition_ops(config=config)
                    st.session_state[MANUAL_PRODUCT_SYNC_RESULT_KEY] = sync_result
                    _reload_products_from_supabase()
                    st.session_state[NOTICE_KEY] = _format_shopify_product_sync_summary(sync_result)
                    sync_errors = list(sync_result.get("errors") or [])
                    sync_errors.extend(sync_result.get("variant_sync_errors") or [])
                    st.session_state[NOTICE_LEVEL_KEY] = "warning" if sync_errors else "success"
                    sync_completed = True
            except Exception as error:
                st.session_state[NOTICE_KEY] = f"Shopify new-product pull failed: {error}"
                st.session_state[NOTICE_LEVEL_KEY] = "error"
            if sync_completed:
                st.rerun()
        if action_cols[1].button(
            "Reload Supabase Table",
            use_container_width=True,
            disabled=not backend,
        ):
            try:
                with st.spinner("Reloading products from Supabase..."):
                    _reload_products_from_supabase()
            except Exception as error:
                failure = _safe_edition_ops_load_failure(error)
                st.session_state[LOAD_ERROR_KEY] = failure["message"]
                st.session_state[LOAD_DIAGNOSTIC_KEY] = failure
                st.session_state[NOTICE_KEY] = failure["message"]
                st.session_state[NOTICE_LEVEL_KEY] = "error"
                st.error(failure["message"])
            else:
                st.rerun()
        action_cols[2].download_button(
            "Export CSV Backup",
            data=_export_csv(rows),
            file_name=f"edition-ops-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.csv",
            mime="text/csv",
            use_container_width=True,
            disabled=not bool(rows),
        )
        popover_target = action_cols[3] if hasattr(action_cols[3], "popover") else st
        if hasattr(popover_target, "popover"):
            with popover_target.popover("Import CSV and Replace Table", use_container_width=True):
                st.caption("CSV values replace the edition fields and mark rows Needs Sync. They are not saved until you click Save Changes.")
                uploaded_csv = st.file_uploader(
                    "Choose CSV backup",
                    type=["csv"],
                    key="edition-ops-import-csv",
                )
                if uploaded_csv is not None:
                    st.caption(f"Ready to import: {uploaded_csv.name}")
                if st.button("Replace Table From CSV", use_container_width=True):
                    if _apply_csv_import(uploaded_csv):
                        st.rerun()

        st.caption("Full Product Reconciliation is a recovery action and may inspect the complete Shopify catalogue.")
        reconciliation_confirmed = False
        if hasattr(st, "checkbox"):
            reconciliation_confirmed = st.checkbox(
                "I confirm I want to inspect the complete Shopify product catalogue.",
                key="edition-ops-confirm-full-product-reconciliation",
            )
        if st.button(
            "Full Product Reconciliation",
            key="edition-ops-full-product-reconciliation",
            use_container_width=True,
            disabled=not backend or not reconciliation_confirmed,
        ):
            reconciliation_completed = False
            try:
                with st.spinner("Reconciling the complete Shopify product catalogue..."):
                    if not hasattr(backend, "reconcile_all_shopify_products_to_edition_ops"):
                        raise ValueError("Full product reconciliation is not available.")
                    config = shopify_sync.get_config()
                    if not config.get("configured"):
                        raise ValueError("Shopify is not configured.")
                    reconciliation_result = backend.reconcile_all_shopify_products_to_edition_ops(config=config)
                    _reload_products_from_supabase()
                    st.session_state[NOTICE_KEY] = _format_full_product_reconciliation_summary(
                        reconciliation_result
                    )
                    reconciliation_errors = list(reconciliation_result.get("errors") or [])
                    reconciliation_errors.extend(reconciliation_result.get("variant_sync_errors") or [])
                    st.session_state[NOTICE_LEVEL_KEY] = "warning" if reconciliation_errors else "success"
                    reconciliation_completed = True
            except Exception as error:
                st.session_state[NOTICE_KEY] = f"Full product reconciliation failed: {error}"
                st.session_state[NOTICE_LEVEL_KEY] = "error"
            if reconciliation_completed:
                st.rerun()


def render_page():
    started = time.perf_counter()
    _ensure_state()
    st.title("Edition Ops")
    st.caption("Manage edition limits, next numbers, and active limited-edition products.")
    print("PERF Edition Ops render start", flush=True)

    load_started = time.perf_counter()
    _hydrate_from_snapshot_once()
    print(
        "PERF Edition Ops hydrate "
        f"duration_ms={int((time.perf_counter() - load_started) * 1000)}",
        flush=True,
    )
    _render_import_popover_styles()
    backend = _configured_supabase_backend()
    rows = [_normalise_row(row) for row in st.session_state.get(ROWS_KEY, [])]
    originals = [_normalise_row(row) for row in st.session_state.get(ORIGINAL_ROWS_KEY, [])]
    rows_to_save = _rows_to_save(rows, originals)
    meta = st.session_state.get(META_KEY) or {}
    load_error = str(st.session_state.get(LOAD_ERROR_KEY) or "")
    load_diagnostic = dict(st.session_state.get(LOAD_DIAGNOSTIC_KEY) or {})

    if meta.get("cached"):
        st.caption("Source: cached Supabase snapshot")
    else:
        st.caption("Source: Supabase ledger")
    st.caption(f"Last refreshed: {_format_time(meta.get('last_refreshed_from_shopify'))}")
    if load_error:
        if meta.get("cached"):
            st.warning(f"{load_error} Showing the last successfully loaded cached display.")
        else:
            st.error(load_error)
        if hasattr(st, "expander"):
            with st.expander("Developer diagnostics", expanded=False):
                st.caption(f"Operation: {load_diagnostic.get('operation') or 'edition_ops.products.latest'}")
                st.caption(f"Category: {load_diagnostic.get('category') or 'database_unavailable'}")
                st.caption(f"Exception: {load_diagnostic.get('exception_class') or 'Unavailable'}")
                st.caption(f"Duration: {int(load_diagnostic.get('duration_ms') or 0)} ms")

    _render_notice()

    warnings = st.session_state.get(IMPORT_WARNINGS_KEY) or []
    for warning in warnings:
        st.warning(warning)
    st.session_state[IMPORT_WARNINGS_KEY] = []

    summary_slot = st.empty() if hasattr(st, "empty") else None
    advanced_slot = st.empty() if hasattr(st, "empty") else None

    if rows:
        st.caption("Unticking Enabled archives the edition and sets remaining to 0.")
        current_rows = _mark_current_changes(rows, originals)
        st.session_state[ROWS_KEY] = current_rows
        st.session_state[EDITOR_ROWS_KEY] = deepcopy(current_rows)
        st.session_state[ORIGINAL_ROWS_KEY] = originals
        changed_rows = _changed_rows(current_rows, originals)
        retry_rows = _pending_shopify_sync_rows(current_rows)
        rows_to_save = _rows_to_save(current_rows, originals)
        _slot_caption(summary_slot, _edition_ops_summary(current_rows, changed_rows, retry_rows))
        page_rows, page_index, page_count = _editor_page_rows(current_rows)
        editor_rows = [_editor_payload(row) for row in page_rows]
        if page_count > 1:
            st.caption(
                f"Editing page {page_index + 1} of {page_count}. "
                f"Each page is limited to {EDITION_OPS_EDITOR_PAGE_SIZE} products for stability."
            )
        editor_started = time.perf_counter()
        print(
            "PERF Edition Ops editor start "
            f"rows={len(editor_rows)} total_rows={len(current_rows)} page={page_index + 1}",
            flush=True,
        )
        with st.form("edition-ops-editor-form", clear_on_submit=False):
            save_clicked = st.form_submit_button(
                "Save Changes",
                type="primary",
                use_container_width=True,
                disabled=not backend or not bool(current_rows),
                key="edition-ops-save-changes",
            )
            edited = st.data_editor(
                editor_rows,
                hide_index=True,
                width="stretch",
                num_rows="fixed",
                key=EDITOR_KEY,
                column_order=VISIBLE_COLUMNS,
                column_config=_column_config(),
                disabled=[
                    "product_title",
                    "handle",
                    "edition_sold_count",
                    "edition_remaining",
                    "edition_status",
                    "sync_status",
                    "admin_url",
                    "online_store_url",
                ],
            )
        print(
            "PERF Edition Ops editor done "
            f"duration_ms={int((time.perf_counter() - editor_started) * 1000)} "
            f"rows={len(editor_rows)}",
            flush=True,
        )
        if save_clicked:
            with st.spinner("Saving..."):
                _save_changed_rows(edited, source_rows=page_rows)
            _render_notice()
            current_rows = [_normalise_row(row) for row in st.session_state.get(ROWS_KEY, [])]
            changed_rows = _changed_rows(current_rows, originals)
            retry_rows = _pending_shopify_sync_rows(current_rows)
            rows_to_save = _rows_to_save(current_rows, originals)
        if advanced_slot is not None and hasattr(advanced_slot, "container"):
            with advanced_slot.container():
                _render_advanced_controls(backend, current_rows)
        else:
            _render_advanced_controls(backend, current_rows)

        errors = {row["product_title"]: row["sync_error"] for row in current_rows if row.get("sync_error")}
        if errors:
            st.error("Some rows need review before they are fully synced.")
            for product_title, message in errors.items():
                st.caption(f"{product_title}: {message}")
    else:
        _slot_caption(summary_slot, _edition_ops_summary([], [], []))
        if advanced_slot is not None and hasattr(advanced_slot, "container"):
            with advanced_slot.container():
                _render_advanced_controls(backend, [])
        else:
            _render_advanced_controls(backend, [])
        if not load_error:
            st.info("No products loaded yet. Products are added by Shopify webhooks or Advanced sync.")

    elapsed = time.perf_counter() - started
    print(
        "PERF Edition Ops total="
        f"{elapsed:.3f}s rows={len(st.session_state.get(ROWS_KEY, []))} "
        f"queries={int(load_diagnostic.get('query_count') or (1 if rows and not meta.get('cached') else 0))} "
        f"cached={str(bool(meta.get('cached'))).lower()}",
        flush=True,
    )
