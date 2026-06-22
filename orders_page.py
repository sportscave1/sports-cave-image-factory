from copy import deepcopy
from datetime import datetime, timezone
import re

import streamlit as st

import order_allocator
import shopify_sync


ROWS_KEY = "orders_allocation_rows"
ORIGINAL_ROWS_KEY = "orders_allocation_original_rows"
META_KEY = "orders_allocation_meta"
EDITOR_VERSION_KEY = "orders_allocation_editor_version"
SNAPSHOT_LOADED_KEY = "orders_allocation_snapshot_loaded"
NOTICE_KEY = "orders_allocation_notice"
SNAPSHOT_FILE_NAME = "orders_allocation_snapshot.json"

VISIBLE_COLUMNS = (
    "selected",
    "order",
    "date",
    "customer",
    "product",
    "variant",
    "qty",
    "current_product_next_number",
    "assigned_edition_number",
    "edition_total",
    "allocation_status",
    "sync_status",
    "admin_url",
)

EDITABLE_FIELDS = ("assigned_edition_number",)


def _format_time(value):
    if not value:
        return "Never"
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone().strftime("%d %b %Y %I:%M %p")
    except ValueError:
        return str(value)


def _ensure_state():
    st.session_state.setdefault(ROWS_KEY, [])
    st.session_state.setdefault(ORIGINAL_ROWS_KEY, [])
    st.session_state.setdefault(META_KEY, {"last_refreshed": "", "saved_at": ""})
    st.session_state.setdefault(EDITOR_VERSION_KEY, 0)
    st.session_state.setdefault(NOTICE_KEY, "")


def _bump_editor_version():
    st.session_state[EDITOR_VERSION_KEY] = int(st.session_state.get(EDITOR_VERSION_KEY) or 0) + 1


def _normalise_row(row):
    updated = dict(row or {})
    updated["selected"] = bool(updated.get("selected", False))
    updated["order"] = str(updated.get("order") or "")
    updated["date"] = str(updated.get("date") or "")
    updated["customer"] = str(updated.get("customer") or "")
    updated["product"] = str(updated.get("product") or "")
    updated["variant"] = str(updated.get("variant") or "")
    updated["qty"] = int(updated.get("qty") or 1)
    updated["current_product_next_number"] = updated.get("current_product_next_number") or ""
    updated["assigned_edition_number"] = str(updated.get("assigned_edition_number") or "")
    updated["edition_total"] = updated.get("edition_total") or ""
    updated["allocation_status"] = str(updated.get("allocation_status") or "Needs Allocation")
    updated["sync_status"] = str(updated.get("sync_status") or "Loaded")
    updated["admin_url"] = str(updated.get("admin_url") or "")
    updated["shopify_order_id"] = str(updated.get("shopify_order_id") or "")
    updated["legacy_resource_id"] = str(updated.get("legacy_resource_id") or "")
    updated["shopify_line_item_id"] = str(updated.get("shopify_line_item_id") or "")
    updated["shopify_product_id"] = str(updated.get("shopify_product_id") or "")
    updated["customer_email"] = str(updated.get("customer_email") or "")
    updated["sync_error"] = str(updated.get("sync_error") or "")
    return updated


def _load_snapshot_once():
    if st.session_state.get(SNAPSHOT_LOADED_KEY):
        return
    payload = order_allocator.load_orders_snapshot()
    rows = [_normalise_row(row) for row in payload.get("rows") or []]
    st.session_state[ROWS_KEY] = rows
    st.session_state[ORIGINAL_ROWS_KEY] = deepcopy(rows)
    st.session_state[META_KEY] = {
        "last_refreshed": payload.get("last_refreshed") or "",
        "saved_at": payload.get("saved_at") or "",
    }
    st.session_state[SNAPSHOT_LOADED_KEY] = True


def _write_snapshot(rows, meta=None):
    payload = order_allocator.save_orders_snapshot(
        [_normalise_row(row) for row in rows],
        meta=meta or st.session_state.get(META_KEY) or {},
    )
    st.session_state[META_KEY] = {
        "last_refreshed": payload.get("last_refreshed") or "",
        "saved_at": payload.get("saved_at") or "",
    }


def _parse_assigned_numbers(value):
    text = str(value or "").strip()
    if not text:
        return []
    digits = [int(match) for match in re.findall(r"\d+", text)]
    if not digits:
        return []
    if len(digits) >= 3 and "/" in text:
        digits = digits[:-1]
    if len(digits) >= 2 and "-" in text:
        start, end = digits[0], digits[1]
        if end >= start:
            return list(range(start, end + 1))
    return [digits[0]]


def _assigned_display(numbers, total):
    if not numbers:
        return ""
    return order_allocator.format_edition_numbers(numbers, total)


def _allocation_for_line(order, line_item):
    allocations = order_allocator.allocation_payload_from_metafields(order.get("metafields") or [])
    return (allocations.get("line_items") or {}).get(line_item.get("shopify_line_item_id")) or {}


def _product_edition(product_id, cache, config):
    if not product_id:
        return {}
    if product_id in cache:
        return cache[product_id]
    try:
        metafields = shopify_sync.fetch_metafields(
            product_id,
            namespace="sports_cave",
            config=config,
        ).get("metafields") or []
        edition = shopify_sync.normalize_limited_edition_metafields(metafields)
        by_key = {item.get("key"): item for item in metafields if item.get("namespace") == "sports_cave"}
        enabled_value = (by_key.get("edition_enabled") or {}).get("value")
        enabled = str(enabled_value or "").strip().casefold() in {"true", "1", "yes", "on"}
        edition["edition_enabled"] = enabled
    except Exception as error:
        edition = {"error": str(error), "edition_enabled": False}
    cache[product_id] = edition
    return edition


def _row_from_order_line(order, line_item, edition):
    allocation = _allocation_for_line(order, line_item)
    numbers = allocation.get("edition_numbers") or []
    edition_total = int(
        allocation.get("edition_total")
        or edition.get("edition_total")
        or 0
    )
    if allocation:
        status = "Assigned"
    elif edition.get("edition_enabled"):
        status = "Needs Allocation"
    elif edition.get("error"):
        status = "Product Error"
    else:
        status = "Not Limited"
    return _normalise_row(
        {
            "order": order.get("order_name") or "",
            "date": (order.get("processed_at") or order.get("created_at") or "")[:10],
            "customer": order.get("customer_name") or order.get("customer_email") or "",
            "customer_email": order.get("customer_email") or "",
            "product": line_item.get("product_title") or "",
            "variant": line_item.get("variant_title") or "",
            "qty": line_item.get("quantity") or 1,
            "current_product_next_number": edition.get("edition_next_number") or "",
            "assigned_edition_number": allocation.get("edition_display") or _assigned_display(numbers, edition_total),
            "edition_total": edition_total or "",
            "allocation_status": status,
            "sync_status": "Loaded",
            "admin_url": order.get("admin_url") or "",
            "shopify_order_id": order.get("shopify_order_id") or "",
            "legacy_resource_id": order.get("legacy_resource_id") or "",
            "shopify_line_item_id": line_item.get("shopify_line_item_id") or "",
            "shopify_product_id": line_item.get("shopify_product_id") or "",
        }
    )


def _refresh_orders():
    config = shopify_sync.get_config()
    if not config.get("configured"):
        st.session_state[NOTICE_KEY] = "Store connection is not configured yet. Ask a developer before refreshing orders."
        return
    rows = []
    product_cache = {}
    for page in shopify_sync.iter_order_pages(
        days=30,
        page_size=50,
        max_orders=100,
        query="financial_status:paid",
        default_paid_unfulfilled_filter=False,
        config=config,
    ):
        for order in page.get("orders") or []:
            for line_item in order.get("line_items") or []:
                edition = _product_edition(line_item.get("shopify_product_id"), product_cache, config)
                rows.append(_row_from_order_line(order, line_item, edition))
    refreshed_at = order_allocator.now_iso()
    st.session_state[ROWS_KEY] = rows
    st.session_state[ORIGINAL_ROWS_KEY] = deepcopy(rows)
    _write_snapshot(rows, meta={"last_refreshed": refreshed_at})
    st.session_state[NOTICE_KEY] = f"Refreshed {len(rows)} paid order lines."
    _bump_editor_version()


def _merge_editor_rows(edited_rows, source_rows, originals):
    original_by_line = {row.get("shopify_line_item_id"): row for row in originals}
    merged = []
    for index, edited in enumerate(edited_rows):
        source = source_rows[index] if index < len(source_rows) else {}
        updated = _normalise_row({**source, **dict(edited)})
        original = original_by_line.get(updated.get("shopify_line_item_id"))
        if original and updated.get("assigned_edition_number") != original.get("assigned_edition_number"):
            updated["sync_status"] = "Needs Sync"
            updated["allocation_status"] = "Manual Edit"
        merged.append(updated)
    return merged


def _rows_to_save(rows, originals):
    original_by_line = {row.get("shopify_line_item_id"): row for row in originals}
    output = []
    for row in rows:
        original = original_by_line.get(row.get("shopify_line_item_id"))
        if str(row.get("sync_status") or "").casefold() == "needs sync":
            output.append(row)
        elif original and row.get("assigned_edition_number") != original.get("assigned_edition_number"):
            output.append(row)
    return output


def _group_rows_by_order(rows):
    grouped = {}
    for row in rows:
        grouped.setdefault(row.get("shopify_order_id"), []).append(row)
    return grouped


def _allocation_record_from_row(row):
    numbers = _parse_assigned_numbers(row.get("assigned_edition_number"))
    total = int(row.get("edition_total") or 0)
    return {
        "line_item_id": row.get("shopify_line_item_id"),
        "product_id": row.get("shopify_product_id"),
        "product_title": row.get("product"),
        "variant_title": row.get("variant"),
        "quantity": int(row.get("qty") or 1),
        "edition_numbers": numbers,
        "edition_number": numbers[0] if numbers else None,
        "edition_total": total,
        "edition_display": _assigned_display(numbers, total),
        "order_name": row.get("order"),
        "allocated_at": order_allocator.now_iso(),
        "manual": True,
    }


def _save_order_rows(rows_to_save):
    if not rows_to_save:
        st.session_state[NOTICE_KEY] = "No changed order editions to save."
        return
    config = shopify_sync.get_config()
    if not config.get("configured"):
        st.session_state[NOTICE_KEY] = "Store connection is not configured yet. Ask a developer before saving orders."
        return

    saved_lines = set()
    errors = {}
    for order_id, order_rows in _group_rows_by_order(rows_to_save).items():
        if not order_id:
            continue
        try:
            state = order_allocator.read_order_allocation_state(order_id, config=config)
            payload = state.get("payload") or {}
            payload.update(
                {
                    "version": order_allocator.SNAPSHOT_VERSION,
                    "source": "sports_cave_os_manual",
                    "order_id": order_id,
                    "order_name": order_rows[0].get("order") or "",
                    "updated_at": order_allocator.now_iso(),
                }
            )
            line_items = dict(payload.get("line_items") or {})
            for row in order_rows:
                numbers = _parse_assigned_numbers(row.get("assigned_edition_number"))
                if not numbers:
                    continue
                line_items[row.get("shopify_line_item_id")] = _allocation_record_from_row(row)
                saved_lines.add(row.get("shopify_line_item_id"))
            payload["line_items"] = line_items
            shopify_sync.sync_order_allocation_metafield(
                order_id,
                payload,
                compare_digest=state.get("compare_digest"),
                config=config,
            )
        except Exception as error:
            for row in order_rows:
                errors[row.get("shopify_line_item_id")] = str(error)

    rows = [_normalise_row(row) for row in st.session_state.get(ROWS_KEY, [])]
    updated_rows = []
    originals = []
    for row in rows:
        line_id = row.get("shopify_line_item_id")
        updated = dict(row)
        if line_id in saved_lines:
            updated["sync_status"] = "Synced"
            updated["allocation_status"] = "Assigned"
            updated["sync_error"] = ""
        elif line_id in errors:
            updated["sync_status"] = "Error"
            updated["sync_error"] = errors[line_id]
        updated_rows.append(_normalise_row(updated))
        originals.append(_normalise_row(updated if line_id in saved_lines else row))

    st.session_state[ROWS_KEY] = updated_rows
    st.session_state[ORIGINAL_ROWS_KEY] = originals
    _write_snapshot(updated_rows, meta=st.session_state.get(META_KEY) or {})
    st.session_state[NOTICE_KEY] = (
        f"Saved {len(saved_lines)} order line allocation(s)."
        if not errors
        else f"Saved {len(saved_lines)} order line allocation(s). {len(errors)} line(s) need review."
    )
    _bump_editor_version()


def _allocate_selected_from_product_counter():
    rows = [_normalise_row(row) for row in st.session_state.get(ROWS_KEY, [])]
    selected_rows = [row for row in rows if row.get("selected")]
    if not selected_rows:
        st.session_state[NOTICE_KEY] = "Select one or more order lines first."
        return
    config = shopify_sync.get_config()
    if not config.get("configured"):
        st.session_state[NOTICE_KEY] = "Store connection is not configured yet. Ask a developer before allocating."
        return

    product_updates = {}
    product_counter_cache = {}
    updated_rows = []
    for row in rows:
        if not row.get("selected"):
            updated_rows.append(row)
            continue
        product_id = row.get("shopify_product_id")
        if not product_id:
            row["sync_status"] = "Error"
            row["sync_error"] = "Product missing."
            updated_rows.append(row)
            continue
        if product_id not in product_counter_cache:
            metafields = shopify_sync.fetch_metafields(product_id, namespace="sports_cave", config=config).get("metafields") or []
            edition = shopify_sync.normalize_limited_edition_metafields(metafields)
            product_counter_cache[product_id] = {
                "edition": edition,
                "next_number": int(edition.get("edition_next_number") or 1),
            }
        product_state = product_counter_cache[product_id]
        edition = product_state["edition"]
        current_next = int(product_state["next_number"] or 1)
        qty = int(row.get("qty") or 1)
        total = int(edition.get("edition_total") or 100)
        numbers = list(range(current_next, current_next + qty))
        row["assigned_edition_number"] = _assigned_display(numbers, total)
        row["edition_total"] = total
        row["current_product_next_number"] = current_next + qty
        row["allocation_status"] = "Manual Edit"
        row["sync_status"] = "Needs Sync"
        row["selected"] = False
        product_updates[product_id] = {
            "shopify_product_id": product_id,
            "title": row.get("product"),
            "edition_enabled": True,
            "edition_total": total,
            "edition_next_number": current_next + qty,
            "edition_label": edition.get("edition_label") or "Numbered Edition",
        }
        product_state["next_number"] = current_next + qty
        updated_rows.append(_normalise_row(row))

    if product_updates:
        shopify_sync.sync_limited_edition_metafields_for_products(list(product_updates.values()), config=config)
    st.session_state[ROWS_KEY] = updated_rows
    _write_snapshot(updated_rows, meta=st.session_state.get(META_KEY) or {})
    st.session_state[NOTICE_KEY] = f"Allocated {len(product_updates)} selected line(s) from product counters. Click Save Changed Order Editions to write order allocations."
    _bump_editor_version()


def _column_config():
    return {
        "selected": st.column_config.CheckboxColumn("Select"),
        "order": st.column_config.TextColumn("Order"),
        "date": st.column_config.TextColumn("Date"),
        "customer": st.column_config.TextColumn("Customer"),
        "product": st.column_config.TextColumn("Product"),
        "variant": st.column_config.TextColumn("Variant"),
        "qty": st.column_config.NumberColumn("Qty"),
        "current_product_next_number": st.column_config.NumberColumn("Current product next number"),
        "assigned_edition_number": st.column_config.TextColumn("Assigned edition number"),
        "edition_total": st.column_config.NumberColumn("Edition total"),
        "allocation_status": st.column_config.TextColumn("Allocation status"),
        "sync_status": st.column_config.TextColumn("Sync status"),
        "admin_url": st.column_config.LinkColumn("Open Order", display_text="Open"),
    }


def render_page():
    _ensure_state()
    _load_snapshot_once()
    rows = [_normalise_row(row) for row in st.session_state.get(ROWS_KEY, [])]
    originals = [_normalise_row(row) for row in st.session_state.get(ORIGINAL_ROWS_KEY, [])]
    rows_to_save = _rows_to_save(rows, originals)
    meta = st.session_state.get(META_KEY) or {}

    st.title("Orders")
    st.caption("Lightweight paid-order edition allocation mirror. Saved rows show instantly; refresh only when needed.")
    st.caption(f"Last refreshed: {_format_time(meta.get('last_refreshed'))}")

    notice = st.session_state.get(NOTICE_KEY)
    if notice:
        st.success(notice)
        st.session_state[NOTICE_KEY] = ""

    action_cols = st.columns([1, 1, 1, 1])
    if action_cols[0].button("Refresh Orders", type="primary", use_container_width=True):
        with st.spinner("Refreshing recent paid orders..."):
            _refresh_orders()
        st.rerun()
    if action_cols[1].button(
        "Save Changed Order Editions",
        use_container_width=True,
        disabled=not bool(rows_to_save),
    ):
        with st.spinner("Saving order edition allocations..."):
            _save_order_rows(rows_to_save)
        st.rerun()
    if action_cols[2].button("Allocate Selected From Product Counter", use_container_width=True, disabled=not bool(rows)):
        with st.spinner("Allocating selected order lines..."):
            _allocate_selected_from_product_counter()
        st.rerun()
    with action_cols[3].popover("Overwrite Selected Order Allocation", use_container_width=True):
        st.warning("This writes the selected assigned edition numbers to the order allocation field.")
        if st.button("Overwrite Selected Now", use_container_width=True):
            selected = [row for row in rows if row.get("selected")]
            _save_order_rows(selected)
            st.rerun()

    if not rows:
        st.info("No saved orders yet. Use Refresh Orders to load recent paid orders.")
        return

    st.caption(f"{len(rows)} order lines shown. {len(rows_to_save)} changed line(s) waiting to save.")
    edited = st.data_editor(
        rows,
        hide_index=True,
        use_container_width=True,
        num_rows="fixed",
        key=f"orders-allocation-editor-{st.session_state[EDITOR_VERSION_KEY]}",
        column_order=VISIBLE_COLUMNS,
        column_config=_column_config(),
        disabled=[
            "order",
            "date",
            "customer",
            "product",
            "variant",
            "qty",
            "current_product_next_number",
            "edition_total",
            "allocation_status",
            "sync_status",
            "admin_url",
        ],
    )
    edited_rows = [dict(row) for row in edited.to_dict("records")] if hasattr(edited, "to_dict") else list(edited or [])
    current_rows = _merge_editor_rows(edited_rows, rows, originals)
    st.session_state[ROWS_KEY] = current_rows
    st.session_state[ORIGINAL_ROWS_KEY] = originals
    if current_rows != rows:
        _write_snapshot(current_rows, meta=meta)

    errors = [row for row in current_rows if row.get("sync_error")]
    if errors:
        st.error("Some order lines need review.")
        for row in errors[:20]:
            st.caption(f"{row.get('order')} {row.get('product')}: {row.get('sync_error')}")
