from copy import deepcopy
import csv
from datetime import datetime, timezone
import io
import json
from pathlib import Path
from urllib.parse import quote_plus

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

EDITABLE_FIELDS = (
    "edition_enabled",
    "edition_total",
    "edition_next_number",
    "edition_label",
    "edition_status_override",
)

VISIBLE_COLUMNS = (
    "product_title",
    "handle",
    "edition_enabled",
    "edition_total",
    "edition_next_number",
    "remaining",
    "widget_status",
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
    "edition_label",
    "edition_status_override",
    "remaining",
    "widget_status",
    "online_store_url",
    "admin_url",
    "last_synced_at",
    "sync_status",
    "sync_error",
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


def _widget_status(remaining, override=""):
    override_text = str(override or "").strip()
    if override_text:
        return override_text
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


def _normalise_row(row):
    updated = dict(row or {})
    updated["shopify_product_gid"] = str(
        updated.get("shopify_product_gid")
        or updated.get("Product ID")
        or updated.get("shopify_product_id")
        or ""
    )
    updated["legacy_resource_id"] = str(updated.get("legacy_resource_id") or updated.get("Legacy ID") or "")
    updated["thumbnail_url"] = str(updated.get("thumbnail_url") or updated.get("Thumbnail") or "")
    updated["product_title"] = str(updated.get("product_title") or updated.get("Product title") or "Untitled Shopify Product")
    updated["handle"] = str(updated.get("handle") or updated.get("Handle") or "")
    updated["status"] = str(updated.get("status") or updated.get("Status") or "ACTIVE")
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
    updated["edition_status_override"] = str(
        updated.get("edition_status_override", updated.get("Status override", ""))
        or ""
    ).strip()
    updated["remaining"] = _remaining(updated["edition_total"], updated["edition_next_number"])
    updated["widget_status"] = _widget_status(updated["remaining"], updated["edition_status_override"])
    updated["online_store_url"] = str(updated.get("online_store_url") or updated.get("Open live product") or "")
    updated["admin_url"] = str(updated.get("admin_url") or updated.get("Open Shopify") or "")
    updated["last_synced_at"] = str(updated.get("last_synced_at") or "")
    updated["sync_status"] = str(updated.get("sync_status") or updated.get("Last saved / Synced") or "Loaded").strip() or "Loaded"
    updated["sync_error"] = str(updated.get("sync_error") or "")
    return updated


def _row_from_product(product):
    edition = product.get("edition") or {}
    row = {
        "shopify_product_gid": product.get("shopify_product_id") or "",
        "legacy_resource_id": product.get("legacy_resource_id") or "",
        "thumbnail_url": product.get("thumbnail_url") or "",
        "product_title": product.get("title") or "Untitled Shopify Product",
        "handle": product.get("handle") or "",
        "status": product.get("status") or "ACTIVE",
        "edition_enabled": _coerce_bool(edition.get("edition_enabled")),
        "edition_total": _coerce_int(edition.get("edition_total"), 100),
        "edition_next_number": _coerce_int(edition.get("edition_next_number"), 1),
        "edition_label": edition.get("edition_label") or "Numbered Edition",
        "edition_status_override": edition.get("edition_status_override") or "",
        "online_store_url": product.get("online_store_url") or "",
        "admin_url": product.get("admin_url") or "",
        "last_synced_at": "",
        "sync_status": "Loaded from Shopify",
        "sync_error": "",
    }
    return _normalise_row(row)


def _ensure_state():
    st.session_state.setdefault(ROWS_KEY, [])
    st.session_state.setdefault(ORIGINAL_ROWS_KEY, [])
    st.session_state.setdefault(
        META_KEY,
        {
            "last_refreshed_from_shopify": "",
            "saved_at": "",
        },
    )
    st.session_state.setdefault(ERRORS_KEY, {})
    st.session_state.setdefault(IMPORT_WARNINGS_KEY, [])
    st.session_state.setdefault(NOTICE_KEY, "")
    st.session_state.setdefault(EDITOR_VERSION_KEY, 0)


def _bump_editor_version():
    st.session_state[EDITOR_VERSION_KEY] = int(st.session_state.get(EDITOR_VERSION_KEY) or 0) + 1


def _load_snapshot():
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
        }
    st.session_state[SNAPSHOT_LOADED_KEY] = True


def _editable_snapshot(row):
    recalculated = _normalise_row(row)
    return {field: recalculated.get(field) for field in EDITABLE_FIELDS}


def _changed_rows(rows, originals):
    original_by_id = {row.get("shopify_product_gid"): row for row in originals}
    changed = []
    for row in rows:
        product_id = row.get("shopify_product_gid")
        original = original_by_id.get(product_id)
        if not original or _editable_snapshot(row) != _editable_snapshot(original):
            changed.append(row)
    return changed


def _mark_current_changes(rows, originals):
    original_by_id = {row.get("shopify_product_gid"): row for row in originals}
    updated_rows = []
    for row in rows:
        updated = _normalise_row(row)
        original = original_by_id.get(updated.get("shopify_product_gid"))
        changed = not original or _editable_snapshot(updated) != _editable_snapshot(original)
        if changed and updated.get("sync_status") != "Unsaved import":
            updated["sync_status"] = "Unsaved"
            updated["sync_error"] = ""
        elif not changed and updated.get("sync_status") in {"Unsaved", "Unsaved import"}:
            updated["sync_status"] = original.get("sync_status", "Loaded") if original else "Loaded"
            updated["sync_error"] = original.get("sync_error", "") if original else ""
        updated_rows.append(updated)
    return updated_rows


def _shopify_values_from_row(row):
    recalculated = _normalise_row(row)
    return {
        "shopify_product_id": recalculated.get("shopify_product_gid"),
        "title": recalculated.get("product_title"),
        "edition_enabled": recalculated.get("edition_enabled"),
        "edition_total": recalculated.get("edition_total"),
        "edition_next_number": recalculated.get("edition_next_number"),
        "edition_label": recalculated.get("edition_label"),
        "edition_status_override": recalculated.get("edition_status_override"),
    }


def _load_active_products_from_shopify():
    config = shopify_sync.get_config()
    if not config.get("configured"):
        raise ValueError(
            "Shopify is not connected yet. Ask a developer to configure Shopify before refreshing products."
        )
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
    st.session_state[NOTICE_KEY] = f"Refreshed {len(rows)} ACTIVE Shopify products."
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
            updated["sync_status"] = "Synced"
            updated["sync_error"] = ""
            updated["last_synced_at"] = now
            new_originals.append(deepcopy(updated))
        elif product_id in failed:
            updated["sync_status"] = "Error"
            updated["sync_error"] = failed[product_id]
            new_originals.append(deepcopy(original_by_id.get(product_id, updated)))
        else:
            new_originals.append(deepcopy(original_by_id.get(product_id, updated)))
        new_rows.append(updated)

    st.session_state[ROWS_KEY] = new_rows
    st.session_state[ORIGINAL_ROWS_KEY] = new_originals
    st.session_state[ERRORS_KEY] = failed
    _write_snapshot(new_rows, new_originals)
    _bump_editor_version()


def _save_changed_rows():
    rows = [_normalise_row(row) for row in st.session_state.get(ROWS_KEY, [])]
    originals = [_normalise_row(row) for row in st.session_state.get(ORIGINAL_ROWS_KEY, [])]
    changed = _changed_rows(rows, originals)
    if not changed:
        st.session_state[NOTICE_KEY] = "No changed rows to save."
        return
    config = shopify_sync.get_config()
    result = shopify_sync.sync_limited_edition_metafields_for_products(
        [_shopify_values_from_row(row) for row in changed],
        config=config,
    )
    _mark_synced(rows, originals, result.get("results") or [])
    if result.get("failed"):
        st.session_state[NOTICE_KEY] = (
            f"Saved {result.get('synced', 0)} changed rows. "
            f"{result.get('failed', 0)} rows need review."
        )
    else:
        st.session_state[NOTICE_KEY] = f"Saved {result.get('synced', 0)} changed rows."


def _rows_from_editor(value):
    if hasattr(value, "to_dict"):
        return [dict(row) for row in value.to_dict("records")]
    return [dict(row) for row in (value or [])]


def _merge_visible_rows(edited_rows, source_rows):
    merged = []
    for index, row in enumerate(edited_rows):
        source = source_rows[index] if index < len(source_rows) else {}
        updated = dict(source)
        updated.update(row)
        merged.append(_normalise_row(updated))
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
    try:
        value = int(str(raw_value).strip())
    except ValueError:
        warnings.append(f"{row_label}: {field_name} must be a whole number.")
        return "invalid"
    if value < 1:
        warnings.append(f"{row_label}: {field_name} must be 1 or higher.")
        return "invalid"
    return value


def _apply_csv_import(uploaded_file):
    if uploaded_file is None:
        st.session_state[IMPORT_WARNINGS_KEY] = ["Choose a CSV file first."]
        return

    rows = [_normalise_row(row) for row in st.session_state.get(ROWS_KEY, [])]
    by_gid = {row.get("shopify_product_gid"): index for index, row in enumerate(rows) if row.get("shopify_product_gid")}
    by_handle = {row.get("handle"): index for index, row in enumerate(rows) if row.get("handle")}
    warnings = []
    changed_count = 0

    text = uploaded_file.getvalue().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    for line_number, csv_row in enumerate(reader, start=2):
        gid = str(csv_row.get("shopify_product_gid") or "").strip()
        handle = str(csv_row.get("handle") or "").strip()
        match_index = by_gid.get(gid) if gid else None
        if match_index is None and handle:
            match_index = by_handle.get(handle)
        row_label = handle or gid or f"CSV line {line_number}"
        if match_index is None:
            warnings.append(f"{row_label}: not in the loaded table, ignored.")
            continue

        total = _validate_import_int(csv_row.get("edition_total"), "edition_total", row_label, warnings)
        next_number = _validate_import_int(csv_row.get("edition_next_number"), "edition_next_number", row_label, warnings)
        if total == "invalid" or next_number == "invalid":
            continue

        updated = dict(rows[match_index])
        if str(csv_row.get("edition_enabled") or "").strip():
            updated["edition_enabled"] = _coerce_bool(csv_row.get("edition_enabled"))
        if total is not None:
            updated["edition_total"] = total
        if next_number is not None:
            updated["edition_next_number"] = next_number
        if str(csv_row.get("edition_label") or "").strip():
            updated["edition_label"] = str(csv_row.get("edition_label")).strip()
        if "edition_status_override" in csv_row:
            updated["edition_status_override"] = str(csv_row.get("edition_status_override") or "").strip()
        updated["sync_status"] = "Unsaved import"
        updated["sync_error"] = ""
        rows[match_index] = _normalise_row(updated)
        changed_count += 1

    st.session_state[ROWS_KEY] = rows
    st.session_state[NOTICE_KEY] = f"Imported updates for {changed_count} visible rows. Click Save Changed Rows to write them to Shopify."
    st.session_state[IMPORT_WARNINGS_KEY] = warnings
    _write_snapshot(rows, st.session_state.get(ORIGINAL_ROWS_KEY, []))
    _bump_editor_version()


def _orders_url(config):
    return shopify_sync.build_orders_admin_url(config.get("store_domain"))


def _orders_search_url(config, query):
    base = _orders_url(config)
    if not base or not str(query or "").strip():
        return base
    return f"{base}?query={quote_plus(str(query).strip())}"


def _column_config():
    return {
        "product_title": st.column_config.TextColumn("Product title"),
        "handle": st.column_config.TextColumn("Handle"),
        "edition_enabled": st.column_config.CheckboxColumn("Enabled"),
        "edition_total": st.column_config.NumberColumn("Edition total", min_value=1, max_value=100000, step=1),
        "edition_next_number": st.column_config.NumberColumn("Next edition number", min_value=1, max_value=100000, step=1),
        "remaining": st.column_config.NumberColumn("Remaining"),
        "widget_status": st.column_config.TextColumn("Widget status"),
        "sync_status": st.column_config.TextColumn("Sync status"),
        "admin_url": st.column_config.LinkColumn("Open Shopify", display_text="Open"),
        "online_store_url": st.column_config.LinkColumn("Open live product", display_text="Open"),
    }


def _render_orders_shortcut(config):
    with st.container(border=True):
        st.subheader("Shopify Orders")
        st.caption("No order sync runs here. Use Shopify as the order source.")
        orders_url = _orders_url(config)
        if orders_url:
            st.link_button("Open Shopify Orders", orders_url, use_container_width=False)
        else:
            st.caption("Set SHOPIFY_STORE_DOMAIN to enable the Shopify Orders shortcut.")
        order_query = st.text_input(
            "Optional Shopify order search shortcut",
            placeholder="#SC2824 or customer name",
            key="edition-ops-order-search",
        )
        if orders_url and order_query.strip():
            st.link_button("Open Shopify Orders Search", _orders_search_url(config, order_query), use_container_width=False)


def render_page():
    started = datetime.now(timezone.utc)
    _ensure_state()
    _hydrate_from_snapshot_once()
    config = shopify_sync.get_config()
    rows = [_normalise_row(row) for row in st.session_state.get(ROWS_KEY, [])]
    originals = [_normalise_row(row) for row in st.session_state.get(ORIGINAL_ROWS_KEY, [])]
    changed = _changed_rows(rows, originals)
    meta = st.session_state.get(META_KEY) or {}

    st.title("Edition Ops")
    st.caption("Use this page to manage limited edition numbers.")
    st.markdown(
        "1. Refresh products when new products are added in Shopify.\n"
        "2. Edit Enabled, Edition Total, and Next Edition Number.\n"
        "3. Save changed rows.\n"
        "4. Export a CSV backup after major edits."
    )
    st.info("Shopify is the permanent record. The table below is a fast saved copy of the last refresh/save.")
    st.caption(f"Last refreshed from Shopify: {_format_time(meta.get('last_refreshed_from_shopify'))}")

    notice = st.session_state.get(NOTICE_KEY)
    if notice:
        st.success(notice)
        st.session_state[NOTICE_KEY] = ""

    warnings = st.session_state.get(IMPORT_WARNINGS_KEY) or []
    for warning in warnings:
        st.warning(warning)
    st.session_state[IMPORT_WARNINGS_KEY] = []

    action_cols = st.columns([1, 1, 1, 1, 1])
    if action_cols[0].button("Refresh Products From Shopify", type="primary", use_container_width=True, disabled=not config.get("configured")):
        with st.spinner("Refreshing active Shopify products..."):
            _load_active_products_from_shopify()
        st.rerun()
    if action_cols[1].button("Save Changed Rows", use_container_width=True, disabled=not bool(changed)):
        with st.spinner("Saving changed rows to Shopify..."):
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
    with action_cols[3].popover("Import CSV Updates", use_container_width=True):
        st.caption("Imports update the visible table only. Click Save Changed Rows afterwards to write to Shopify.")
        uploaded_csv = st.file_uploader(
            "Choose CSV backup",
            type=["csv"],
            key="edition-ops-import-csv",
        )
        if st.button("Update Visible Table", use_container_width=True, disabled=uploaded_csv is None):
            _apply_csv_import(uploaded_csv)
            st.rerun()
    if action_cols[4].button("Clear Table", use_container_width=True, disabled=not bool(rows)):
        st.session_state[ROWS_KEY] = []
        st.session_state[ORIGINAL_ROWS_KEY] = []
        st.session_state[ERRORS_KEY] = {}
        st.session_state[META_KEY] = {"last_refreshed_from_shopify": "", "saved_at": ""}
        if SNAPSHOT_PATH.exists():
            SNAPSHOT_PATH.unlink()
        st.session_state[NOTICE_KEY] = "Edition Ops table cleared."
        _bump_editor_version()
        st.rerun()

    if rows:
        st.caption(f"{len(rows)} saved products shown. {len(changed)} changed rows waiting to save.")
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
                "remaining",
                "widget_status",
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
        st.info("No products loaded yet. Refresh products from Shopify to build the first fast saved table.")

    _render_orders_shortcut(config)

    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    print(f"PERF Edition Ops total={elapsed:.3f}s rows={len(st.session_state.get(ROWS_KEY, []))}", flush=True)
