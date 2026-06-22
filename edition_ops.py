from copy import deepcopy
from datetime import datetime, timezone
from urllib.parse import quote_plus

import streamlit as st

import shopify_sync


ROWS_KEY = "edition_ops_rows"
ORIGINAL_ROWS_KEY = "edition_ops_original_rows"
ERRORS_KEY = "edition_ops_sync_errors"
NOTICE_KEY = "edition_ops_notice"
DEFINITIONS_KEY = "edition_ops_definition_status"
EDITOR_VERSION_KEY = "edition_ops_editor_version"

EDITABLE_FIELDS = (
    "Enabled",
    "Edition total",
    "Next edition number",
    "Edition label",
    "Status override",
)

TABLE_COLUMNS = (
    "Thumbnail",
    "Product title",
    "Handle",
    "Status",
    "Enabled",
    "Edition total",
    "Next edition number",
    "Edition label",
    "Status override",
    "Remaining",
    "Widget status",
    "Last saved / Synced",
    "Open Shopify",
    "Open live product",
)


def _now_label():
    return datetime.now(timezone.utc).astimezone().strftime("%d %b %Y %I:%M %p")


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
    return str(value or "").strip().lower() in {"true", "1", "yes", "on"}


def _coerce_int(value, default):
    try:
        return max(int(value), 1)
    except (TypeError, ValueError):
        return default


def _ensure_state():
    st.session_state.setdefault(ROWS_KEY, [])
    st.session_state.setdefault(ORIGINAL_ROWS_KEY, [])
    st.session_state.setdefault(ERRORS_KEY, {})
    st.session_state.setdefault(NOTICE_KEY, "")
    st.session_state.setdefault(DEFINITIONS_KEY, None)
    st.session_state.setdefault(EDITOR_VERSION_KEY, 0)


def _bump_editor_version():
    st.session_state[EDITOR_VERSION_KEY] = int(st.session_state.get(EDITOR_VERSION_KEY) or 0) + 1


def _row_from_product(product):
    edition = product.get("edition") or {}
    total = _coerce_int(edition.get("edition_total"), 100)
    next_number = _coerce_int(edition.get("edition_next_number"), 1)
    remaining = _remaining(total, next_number)
    return {
        "Product ID": product.get("shopify_product_id") or "",
        "Legacy ID": product.get("legacy_resource_id") or "",
        "Thumbnail": product.get("thumbnail_url") or "",
        "Product title": product.get("title") or "Untitled Shopify Product",
        "Handle": product.get("handle") or "",
        "Status": product.get("status") or "UNKNOWN",
        "Enabled": _coerce_bool(edition.get("edition_enabled")),
        "Edition total": total,
        "Next edition number": next_number,
        "Edition label": edition.get("edition_label") or "Numbered Edition",
        "Status override": edition.get("edition_status_override") or "",
        "Remaining": remaining,
        "Widget status": _widget_status(remaining, edition.get("edition_status_override")),
        "Last saved / Synced": "Loaded from Shopify",
        "Open Shopify": product.get("admin_url") or "",
        "Open live product": product.get("online_store_url") or "",
    }


def _recalculate_row(row):
    updated = dict(row)
    updated["Enabled"] = _coerce_bool(updated.get("Enabled"))
    updated["Edition total"] = _coerce_int(updated.get("Edition total"), 100)
    updated["Next edition number"] = _coerce_int(updated.get("Next edition number"), 1)
    updated["Edition label"] = str(updated.get("Edition label") or "Numbered Edition").strip() or "Numbered Edition"
    updated["Status override"] = str(updated.get("Status override") or "").strip()
    remaining = _remaining(updated["Edition total"], updated["Next edition number"])
    updated["Remaining"] = remaining
    updated["Widget status"] = _widget_status(remaining, updated["Status override"])
    return updated


def _rows_from_editor(value):
    if hasattr(value, "to_dict"):
        return [dict(row) for row in value.to_dict("records")]
    return [dict(row) for row in (value or [])]


def _merge_editor_rows(edited_rows, source_rows):
    merged = []
    for index, row in enumerate(edited_rows):
        source = source_rows[index] if index < len(source_rows) else {}
        updated = dict(source)
        updated.update(row)
        merged.append(updated)
    return merged


def _editable_snapshot(row):
    recalculated = _recalculate_row(row)
    return {field: recalculated.get(field) for field in EDITABLE_FIELDS}


def _changed_rows(rows, originals):
    original_by_id = {row.get("Product ID"): row for row in originals}
    changed = []
    for row in rows:
        product_id = row.get("Product ID")
        original = original_by_id.get(product_id)
        if not original or _editable_snapshot(row) != _editable_snapshot(original):
            changed.append(row)
    return changed


def _shopify_values_from_row(row):
    recalculated = _recalculate_row(row)
    return {
        "shopify_product_id": recalculated.get("Product ID"),
        "title": recalculated.get("Product title"),
        "edition_enabled": recalculated.get("Enabled"),
        "edition_total": recalculated.get("Edition total"),
        "edition_next_number": recalculated.get("Next edition number"),
        "edition_label": recalculated.get("Edition label"),
        "edition_status_override": recalculated.get("Status override"),
    }


def _mark_synced(rows, originals, results):
    ok_ids = {result["shopify_product_id"] for result in results if result.get("ok")}
    failed = {
        result["shopify_product_id"]: result.get("message") or "Sync failed"
        for result in results
        if not result.get("ok")
    }
    synced_label = f"Synced {_now_label()}"
    new_rows = []
    new_originals = []
    original_by_id = {row.get("Product ID"): row for row in originals}

    for row in rows:
        product_id = row.get("Product ID")
        updated = _recalculate_row(row)
        if product_id in ok_ids:
            updated["Last saved / Synced"] = synced_label
            new_originals.append(deepcopy(updated))
        elif product_id in failed:
            updated["Last saved / Synced"] = "Error"
            new_originals.append(deepcopy(original_by_id.get(product_id, updated)))
        else:
            new_originals.append(deepcopy(original_by_id.get(product_id, updated)))
        new_rows.append(updated)

    st.session_state[ROWS_KEY] = new_rows
    st.session_state[ORIGINAL_ROWS_KEY] = new_originals
    st.session_state[ERRORS_KEY] = failed
    _bump_editor_version()


def _load_active_products():
    config = shopify_sync.get_config()
    if not config.get("configured"):
        raise ValueError(
            "Shopify is not configured. Set SHOPIFY_STORE_DOMAIN, SHOPIFY_API_VERSION, "
            "and Shopify admin credentials."
        )
    loaded = shopify_sync.fetch_edition_ops_active_products(
        max_products=config.get("edition_ops_max_products", 500),
        page_size=50,
        config=config,
    )
    rows = [_recalculate_row(_row_from_product(product)) for product in loaded.get("products") or []]
    st.session_state[ROWS_KEY] = rows
    st.session_state[ORIGINAL_ROWS_KEY] = deepcopy(rows)
    st.session_state[ERRORS_KEY] = {}
    st.session_state[NOTICE_KEY] = f"Loaded {len(rows)} ACTIVE Shopify products."
    _bump_editor_version()


def _sync_rows(rows, success_prefix):
    if not rows:
        st.session_state[NOTICE_KEY] = "No rows selected for sync."
        return
    config = shopify_sync.get_config()
    result = shopify_sync.sync_limited_edition_metafields_for_products(
        [_shopify_values_from_row(row) for row in rows],
        config=config,
    )
    all_rows = [_recalculate_row(row) for row in st.session_state.get(ROWS_KEY, [])]
    _mark_synced(all_rows, st.session_state.get(ORIGINAL_ROWS_KEY, []), result.get("results") or [])
    if result.get("failed"):
        st.session_state[NOTICE_KEY] = (
            f"{success_prefix}: synced {result.get('synced', 0)} rows, "
            f"{result.get('failed', 0)} failed."
        )
    else:
        st.session_state[NOTICE_KEY] = f"{success_prefix}: synced {result.get('synced', 0)} rows."


def _orders_url(config):
    return shopify_sync.build_orders_admin_url(config.get("store_domain"))


def _orders_search_url(config, query):
    base = _orders_url(config)
    if not base or not str(query or "").strip():
        return base
    return f"{base}?query={quote_plus(str(query).strip())}"


def _definition_rows(status):
    return [
        {
            "Name": item.get("name"),
            "Namespace / key": f"{item.get('namespace')}.{item.get('key')}",
            "Owner": item.get("ownerType"),
            "Type": item.get("type"),
            "Status": item.get("status"),
        }
        for item in ((status or {}).get("definitions") or [])
    ]


def _render_definition_panel(config):
    with st.expander("Shopify Metafield Setup", expanded=False):
        st.caption("Definitions are checked or created only when you press a button.")
        cols = st.columns([1, 1, 2])
        if cols[0].button("Check Metafield Definitions", use_container_width=True, disabled=not config.get("configured")):
            with st.spinner("Checking Shopify metafield definitions..."):
                st.session_state[DEFINITIONS_KEY] = shopify_sync.list_edition_ops_metafield_definitions(config=config)
        if cols[1].button("Create Missing Metafield Definitions", type="primary", use_container_width=True, disabled=not config.get("configured")):
            with st.spinner("Creating missing Shopify metafield definitions..."):
                st.session_state[DEFINITIONS_KEY] = shopify_sync.create_missing_edition_ops_metafield_definitions(config=config)
        cols[2].caption("Needed: enabled, total, next number, label, and status override on PRODUCT.")

        status = st.session_state.get(DEFINITIONS_KEY)
        if status:
            rows = _definition_rows(status)
            if rows:
                st.dataframe(rows, hide_index=True, use_container_width=True)
            for error in status.get("errors") or []:
                st.error(f"{error.get('namespace')}.{error.get('key')}: {error.get('message')}")


def _render_orders_shortcut(config):
    with st.container(border=True):
        st.subheader("Shopify Orders")
        st.caption(
            "Orders sync is paused for the Edition Ops MVP. Use Shopify as the order source while this page only controls product edition metafields."
        )
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


def _column_config():
    return {
        "Thumbnail": st.column_config.ImageColumn("Thumbnail", width="small"),
        "Enabled": st.column_config.CheckboxColumn("Enabled"),
        "Edition total": st.column_config.NumberColumn("Edition total", min_value=1, max_value=100000, step=1),
        "Next edition number": st.column_config.NumberColumn("Next edition number", min_value=1, max_value=100000, step=1),
        "Edition label": st.column_config.TextColumn("Edition label"),
        "Status override": st.column_config.TextColumn("Status override"),
        "Remaining": st.column_config.NumberColumn("Remaining"),
        "Open Shopify": st.column_config.LinkColumn("Open Shopify", display_text="Open"),
        "Open live product": st.column_config.LinkColumn("Open live product", display_text="Open"),
        "Product ID": None,
        "Legacy ID": None,
    }


def render_page():
    started = datetime.now(timezone.utc)
    _ensure_state()
    config = shopify_sync.get_config()

    st.title("Edition Ops")
    st.caption(
        "Configure Shopify limited-edition display data and jump to Shopify orders. Shopify metafields are the source of truth for this MVP."
    )

    notice = st.session_state.get(NOTICE_KEY)
    if notice:
        st.info(notice)
        st.session_state[NOTICE_KEY] = ""

    if not config.get("configured"):
        st.warning("Shopify is not configured yet. Product loading and syncing stay disabled until credentials are present.")

    action_cols = st.columns([1, 1, 1, 2])
    if action_cols[0].button("Load Active Shopify Products", type="primary", use_container_width=True, disabled=not config.get("configured")):
        with st.spinner("Loading ACTIVE Shopify products..."):
            _load_active_products()
        st.rerun()
    if action_cols[1].button("Refresh From Shopify", use_container_width=True, disabled=not config.get("configured")):
        with st.spinner("Refreshing ACTIVE Shopify products..."):
            _load_active_products()
        st.rerun()
    if action_cols[2].button("Clear Loaded Table", use_container_width=True, disabled=not bool(st.session_state.get(ROWS_KEY))):
        st.session_state[ROWS_KEY] = []
        st.session_state[ORIGINAL_ROWS_KEY] = []
        st.session_state[ERRORS_KEY] = {}
        st.session_state[NOTICE_KEY] = "Loaded Edition Ops table cleared."
        _bump_editor_version()
        st.rerun()
    action_cols[3].caption(
        f"ACTIVE products only. Page size 50. Max {config.get('edition_ops_max_products', 500)} via SHOPIFY_EDITION_OPS_MAX_PRODUCTS."
    )

    rows = [_recalculate_row(row) for row in st.session_state.get(ROWS_KEY, [])]
    if rows:
        st.caption(f"{len(rows)} active Shopify products loaded. Edit the chart, then save changed rows.")
        edited = st.data_editor(
            rows,
            hide_index=True,
            use_container_width=True,
            num_rows="fixed",
            key=f"edition-ops-editor-{st.session_state[EDITOR_VERSION_KEY]}",
            column_order=TABLE_COLUMNS,
            column_config=_column_config(),
            disabled=[
                "Thumbnail",
                "Product title",
                "Handle",
                "Status",
                "Remaining",
                "Widget status",
                "Last saved / Synced",
                "Open Shopify",
                "Open live product",
            ],
        )
        current_rows = [_recalculate_row(row) for row in _merge_editor_rows(_rows_from_editor(edited), rows)]
        st.session_state[ROWS_KEY] = current_rows
        changed = _changed_rows(current_rows, st.session_state.get(ORIGINAL_ROWS_KEY, []))

        labels = {
            row["Product ID"]: f"{row.get('Product title')} ({row.get('Handle')})"
            for row in current_rows
        }
        selected_ids = st.multiselect(
            "Select rows for Sync Selected Rows",
            options=[row["Product ID"] for row in current_rows],
            format_func=lambda product_id: labels.get(product_id, product_id),
        )

        sync_cols = st.columns([1, 1, 1, 2])
        if sync_cols[0].button("Save Changed Rows to Shopify", type="primary", use_container_width=True, disabled=not bool(changed)):
            with st.spinner("Syncing changed rows to Shopify metafields..."):
                _sync_rows(changed, "Changed rows saved")
            st.rerun()
        if sync_cols[1].button("Sync Selected Rows", use_container_width=True, disabled=not bool(selected_ids)):
            selected_rows = [row for row in current_rows if row.get("Product ID") in set(selected_ids)]
            with st.spinner("Syncing selected rows to Shopify metafields..."):
                _sync_rows(selected_rows, "Selected rows synced")
            st.rerun()
        if sync_cols[2].button("Sync All Loaded Rows", use_container_width=True, disabled=not bool(current_rows)):
            with st.spinner("Syncing all loaded rows to Shopify metafields..."):
                _sync_rows(current_rows, "All loaded rows synced")
            st.rerun()
        sync_cols[3].caption(
            f"{len(changed)} changed rows detected. Sync batches are capped at 5 products / 25 metafields per GraphQL mutation."
        )

        errors = st.session_state.get(ERRORS_KEY) or {}
        if errors:
            st.error("Some products failed to sync.")
            for product_id, message in errors.items():
                st.caption(f"{labels.get(product_id, product_id)}: {message}")
    else:
        st.info("No products loaded yet. Press Load Active Shopify Products when you are ready.")

    _render_definition_panel(config)
    _render_orders_shortcut(config)

    with st.expander("Storefront Widget Reminder", expanded=False):
        st.write(
            "The storefront widget must read only `product.metafields.sports_cave`, render nothing when disabled, "
            "calculate remaining in Liquid, and avoid Sports Cave OS, Supabase, inventory, or external API calls."
        )
        st.caption("Display: Numbered Edition of 100 | Only 48 remaining | No reprints once sold out")

    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    print(f"PERF Edition Ops total={elapsed:.3f}s rows={len(st.session_state.get(ROWS_KEY, []))}", flush=True)
