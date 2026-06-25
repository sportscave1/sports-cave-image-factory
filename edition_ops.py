from copy import deepcopy
import csv
from datetime import datetime, timezone
import importlib
import io
import json
import os
from pathlib import Path
import re

import streamlit as st

import shopify_sync


BASE_DIR = Path(__file__).resolve().parent
SNAPSHOT_PATH = BASE_DIR / "output" / "_cache" / "edition_ops_products_snapshot.json"
SNAPSHOT_VERSION = 1

ROWS_KEY = "edition_ops_rows"
ORIGINAL_ROWS_KEY = "edition_ops_original_rows"
META_KEY = "edition_ops_snapshot_meta"
ERRORS_KEY = "edition_ops_sync_errors"
NOTICE_KEY = "edition_ops_notice"
IMPORT_WARNINGS_KEY = "edition_ops_import_warnings"
EDITOR_VERSION_KEY = "edition_ops_editor_version"
SNAPSHOT_LOADED_KEY = "edition_ops_snapshot_loaded"
ORDERS_CACHE_VERSION_KEY = "orders-ledger-cache-version"
EDITION_OPS_CACHE_VERSION_KEY = "edition-ops-ledger-cache-version"
EDITION_OPS_CACHE_TTL_SECONDS = max(int(os.getenv("SUPABASE_EDITION_OPS_CACHE_TTL_SECONDS", "180")), 30)

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


def _render_import_popover_styles():
    st.markdown(
        """
        <style>
        div[data-testid="stPopover"] div[role="dialog"],
        div[data-testid="stPopover"] [data-testid="stPopoverBody"] {
            background: #FFFFFF !important;
            color: #111111 !important;
        }

        div[data-testid="stPopover"] div[role="dialog"] *,
        div[data-testid="stPopover"] [data-testid="stPopoverBody"] *,
        div[data-testid="stPopover"] [data-testid="stFileUploader"] *,
        div[data-testid="stPopover"] section[data-testid="stFileUploaderDropzone"] * {
            color: #111111 !important;
            -webkit-text-fill-color: #111111 !important;
            fill: #111111 !important;
            stroke: #111111 !important;
        }

        div[data-testid="stPopover"] [data-testid="stFileUploader"],
        div[data-testid="stPopover"] section[data-testid="stFileUploaderDropzone"],
        div[data-testid="stPopover"] [data-testid="stFileUploaderFile"],
        div[data-testid="stPopover"] [data-baseweb="tag"] {
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
    backend = _configured_supabase_backend()
    if not backend:
        return None
    products = backend.list_edition_products(search="", limit=5000)
    rows = [_row_from_supabase_product(product) for product in products or []]
    try:
        sync_state = backend.get_sync_state()
    except Exception:
        sync_state = {}
    last_synced = sync_state.get("last_successful_product_sync_at") or max(
        (str(row.get("last_synced_at") or "") for row in rows),
        default="",
    )
    return {
        "version": SNAPSHOT_VERSION,
        "rows": rows,
        "original_rows": deepcopy(rows),
        "last_refreshed_from_shopify": last_synced,
        "saved_at": last_synced,
        "source": "supabase",
        "mirror_status": "",
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
        "sync_status": "Loaded from Supabase",
        "sync_error": "",
    }
    return _normalise_row(row)


def _load_supabase_snapshot():
    return _cached_supabase_products_snapshot(_cache_version(EDITION_OPS_CACHE_VERSION_KEY))


def _ensure_state():
    st.session_state.setdefault(ROWS_KEY, [])
    st.session_state.setdefault(ORIGINAL_ROWS_KEY, [])
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
    st.session_state.setdefault(EDITOR_VERSION_KEY, 0)


def _bump_editor_version():
    st.session_state[EDITOR_VERSION_KEY] = int(st.session_state.get(EDITOR_VERSION_KEY) or 0) + 1


def _load_snapshot():
    try:
        supabase_snapshot = _load_supabase_snapshot()
    except Exception as error:
        print(f"WARN Edition Ops Supabase snapshot fallback: {error}", flush=True)
        supabase_snapshot = None
    if supabase_snapshot is not None:
        return supabase_snapshot
    if not SNAPSHOT_PATH.exists():
        return None
    try:
        payload = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
    rows = [_normalise_row(row) for row in payload.get("rows") or []]
    original_rows = payload.get("original_rows")
    if isinstance(original_rows, list):
        originals = [_normalise_row(row) for row in original_rows]
    else:
        originals = deepcopy(rows)
    return {
        "version": payload.get("version") or SNAPSHOT_VERSION,
        "rows": rows,
        "original_rows": originals,
        "last_refreshed_from_shopify": payload.get("last_refreshed_from_shopify") or "",
        "saved_at": payload.get("saved_at") or "",
    }


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
        st.session_state[META_KEY] = {
            "last_refreshed_from_shopify": snapshot.get("last_refreshed_from_shopify") or "",
            "saved_at": snapshot.get("saved_at") or "",
            "mirror_status": snapshot.get("mirror_status") or "",
        }
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


def _rows_to_save(rows, originals):
    by_product_id = {}
    for row in _changed_rows(rows, originals):
        key = _stable_row_key(row)
        if key:
            by_product_id[key] = _normalise_row(row)
    for row in rows:
        if str(row.get("sync_status") or "").strip().casefold() == "needs sync":
            key = _stable_row_key(row)
            if key:
                by_product_id[key] = _normalise_row(row)
    return list(by_product_id.values())


def _mark_current_changes(rows, originals):
    original_by_id = {_stable_row_key(row): _normalise_row(row) for row in originals if _stable_row_key(row)}
    updated_rows = []
    for row in rows:
        updated = _normalise_row(row)
        original = original_by_id.get(_stable_row_key(updated))
        changed = not original or _editable_snapshot(updated) != _editable_snapshot(original)
        if changed and updated.get("sync_status") not in {"Unsaved import", "Needs Sync"}:
            updated["sync_status"] = "Unsaved"
            updated["sync_error"] = ""
        elif not changed and updated.get("sync_status") in {"Unsaved", "Unsaved import"}:
            updated["sync_status"] = original.get("sync_status", "Loaded") if original else "Loaded"
            updated["sync_error"] = original.get("sync_error", "") if original else ""
        updated_rows.append(updated)
    return updated_rows


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
    st.session_state[ERRORS_KEY] = {}
    st.session_state[IMPORT_WARNINGS_KEY] = []
    _write_snapshot(
        rows,
        deepcopy(rows),
        meta={"last_refreshed_from_shopify": refreshed_at},
    )
    _invalidate_edition_ops_cache(bump_orders=True)
    st.session_state[NOTICE_KEY] = f"Refreshed {len(rows)} active products."
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
    st.session_state[ERRORS_KEY] = {}
    st.session_state[IMPORT_WARNINGS_KEY] = []
    st.session_state[META_KEY] = {
        "last_refreshed_from_shopify": snapshot.get("last_refreshed_from_shopify") or "",
        "saved_at": snapshot.get("saved_at") or _now_iso(),
        "mirror_status": snapshot.get("mirror_status") or "",
    }
    _write_snapshot(rows, originals, meta=st.session_state[META_KEY])
    st.session_state[NOTICE_KEY] = f"Reloaded {len(rows)} product row(s) from Supabase."
    _bump_editor_version()


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
    st.session_state[ERRORS_KEY] = failed
    _write_snapshot(
        new_rows,
        new_originals,
        meta={"mirror_status": "failed" if failed else "updated"},
    )
    _invalidate_edition_ops_cache(bump_orders=True)
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
            updated["sync_status"] = "Shopify mirror pending"
            updated["sync_error"] = ""
            updated["last_synced_at"] = now
            new_originals.append(deepcopy(updated))
        else:
            new_originals.append(deepcopy(_normalise_row(row)))
        new_rows.append(updated)
    st.session_state[ROWS_KEY] = new_rows
    st.session_state[ORIGINAL_ROWS_KEY] = new_originals
    st.session_state[ERRORS_KEY] = {}
    _write_snapshot(new_rows, new_originals, meta={"mirror_status": "pending"})
    _invalidate_edition_ops_cache(bump_orders=True)
    _bump_editor_version()


def _save_changed_rows():
    rows = [_normalise_row(row) for row in st.session_state.get(ROWS_KEY, [])]
    originals = [_normalise_row(row) for row in st.session_state.get(ORIGINAL_ROWS_KEY, [])]
    rows_to_save = _rows_to_save(rows, originals)
    if not rows_to_save:
        st.session_state[NOTICE_KEY] = "No changes to save."
        return
    backend = _configured_supabase_backend()
    if not backend:
        st.session_state[NOTICE_KEY] = (
            "Supabase is not configured. Edition Ops saves stay locked until the ledger is available."
        )
        return
    config = shopify_sync.get_config()
    supabase_errors = {}
    changed_count = len(rows_to_save)
    unchanged_count = max(len(rows) - changed_count, 0)
    if hasattr(backend, "update_edition_products_batch"):
        batch_rows = []
        for row in rows_to_save:
            normalised = _normalise_row(row, preserve_derived=False)
            batch_rows.append(
                {
                    "edition_product_id": normalised.get("edition_product_id"),
                    "handle": normalised.get("handle"),
                    "edition_name": normalised.get("edition_label"),
                    "edition_total": normalised.get("edition_total"),
                    "next_edition_number": normalised.get("edition_next_number"),
                    "active": bool(normalised.get("edition_enabled")),
                    "sold_out": normalised.get("edition_remaining") <= 0,
                }
            )
        results = backend.update_edition_products_batch(batch_rows, reason="Edition Ops save")
        for result in results or []:
            if not result.get("ok"):
                supabase_errors[result.get("key") or result.get("handle") or ""] = result.get("message") or "Save failed"
    else:
        for row in rows_to_save:
            normalised = _normalise_row(row, preserve_derived=False)
            try:
                backend.update_edition_product(
                    normalised.get("handle"),
                    edition_name=normalised.get("edition_label"),
                    edition_total=normalised.get("edition_total"),
                    next_edition_number=normalised.get("edition_next_number"),
                    active=bool(normalised.get("edition_enabled")),
                    sold_out=normalised.get("edition_remaining") <= 0,
                    reason="Edition Ops save",
                )
            except Exception as error:
                supabase_errors[_stable_row_key(normalised) or normalised.get("handle")] = str(error)
    if supabase_errors:
        updated_rows = []
        for row in rows:
            normalised = _normalise_row(row)
            key = _stable_row_key(normalised)
            if key in supabase_errors:
                normalised["sync_status"] = "Error"
                normalised["sync_error"] = supabase_errors[key]
            updated_rows.append(normalised)
        st.session_state[ROWS_KEY] = updated_rows
        st.session_state[ERRORS_KEY] = supabase_errors
        _write_snapshot(updated_rows, originals)
        st.session_state[NOTICE_KEY] = (
            f"Changed rows saved: {changed_count - len(supabase_errors)}. "
            f"Unchanged rows skipped: {unchanged_count}. "
            f"Errors: {len(supabase_errors)}."
        )
        return
    if not config.get("configured"):
        _mark_supabase_saved_without_shopify(
            rows,
            originals,
            [_stable_row_key(row) for row in rows_to_save],
        )
        st.session_state[NOTICE_KEY] = (
            f"Changed rows saved: {changed_count}. Unchanged rows skipped: {unchanged_count}. Errors: 0."
        )
        return
    result = shopify_sync.sync_limited_edition_metafields_for_products(
        [_shopify_values_from_row(row) for row in rows_to_save],
        config=config,
    )
    _mark_synced(rows, originals, result.get("results") or [])
    st.session_state[NOTICE_KEY] = (
        f"Changed rows saved: {changed_count}. "
        f"Unchanged rows skipped: {unchanged_count}. "
        f"Errors: {int(result.get('failed', 0) or 0)}."
    )


def _rows_from_editor(value):
    if hasattr(value, "to_dict"):
        return [dict(row) for row in value.to_dict("records")]
    return [dict(row) for row in (value or [])]


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
    st.session_state[NOTICE_KEY] = f"Imported and replaced edition fields for {changed_count} rows. Click Save Changed Rows to sync."
    st.session_state[IMPORT_WARNINGS_KEY] = warnings
    st.session_state[ORIGINAL_ROWS_KEY] = originals
    _write_snapshot(rows, originals)
    _bump_editor_version()
    return True


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


def render_page():
    started = datetime.now(timezone.utc)
    _ensure_state()
    _hydrate_from_snapshot_once()
    _render_import_popover_styles()
    backend = _configured_supabase_backend()
    rows = [_normalise_row(row) for row in st.session_state.get(ROWS_KEY, [])]
    originals = [_normalise_row(row) for row in st.session_state.get(ORIGINAL_ROWS_KEY, [])]
    rows_to_save = _rows_to_save(rows, originals)
    meta = st.session_state.get(META_KEY) or {}

    st.title("Edition Ops")
    st.caption("Manage edition limits, next numbers, and active limited-edition products.")
    st.caption(f"Last refreshed: {_format_time(meta.get('last_refreshed_from_shopify'))}")

    notice = st.session_state.get(NOTICE_KEY)
    if notice:
        st.success(notice)
        st.session_state[NOTICE_KEY] = ""

    warnings = st.session_state.get(IMPORT_WARNINGS_KEY) or []
    for warning in warnings:
        st.warning(warning)
    st.session_state[IMPORT_WARNINGS_KEY] = []

    action_cols = st.columns([1, 1, 1, 1])
    if action_cols[0].button("Refresh Products", type="primary", use_container_width=True, disabled=not backend):
        with st.spinner("Reloading products from Supabase..."):
            _reload_products_from_supabase()
        st.rerun()
    if action_cols[1].button(
        "Save Changed Rows",
        use_container_width=True,
        disabled=not bool(rows_to_save),
    ):
        with st.spinner("Saving changed rows..."):
            _save_changed_rows()
        st.rerun()
    action_cols[2].download_button(
        "Export CSV Backup",
        data=_export_csv(rows),
        file_name=f"edition-ops-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.csv",
        mime="text/csv",
        use_container_width=True,
        disabled=not bool(rows),
    )
    with action_cols[3].popover("Import CSV and Replace Table", use_container_width=True):
        st.caption("CSV values replace the edition fields and mark rows Needs Sync. They are not saved until you click Save Changed Rows.")
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

    if rows:
        rows_to_save = _rows_to_save(rows, originals)
        st.caption(f"{len(rows)} saved products shown. {len(rows_to_save)} rows waiting to save.")
        edited = st.data_editor(
            rows,
            hide_index=True,
            use_container_width=True,
            num_rows="fixed",
            key=f"edition-ops-editor-{st.session_state[EDITOR_VERSION_KEY]}",
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
        current_rows = _mark_current_changes(_merge_visible_rows(_rows_from_editor(edited), rows), originals)
        st.session_state[ROWS_KEY] = current_rows
        st.session_state[ORIGINAL_ROWS_KEY] = originals
        if current_rows != rows:
            _write_snapshot(current_rows, originals)

        errors = {row["product_title"]: row["sync_error"] for row in current_rows if row.get("sync_error")}
        if errors:
            st.error("Some rows need review before they are fully synced.")
            for product_title, message in errors.items():
                st.caption(f"{product_title}: {message}")
    else:
        st.info("No products loaded yet. Refresh products to build the first fast saved table.")

    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    print(f"PERF Edition Ops total={elapsed:.3f}s rows={len(st.session_state.get(ROWS_KEY, []))}", flush=True)
