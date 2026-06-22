from datetime import datetime, timezone
import json
from pathlib import Path
import re

import streamlit as st

import order_allocator
import shopify_sync


BASE_DIR = Path(__file__).resolve().parent
EDITION_OPS_SNAPSHOT_PATH = BASE_DIR / "output" / "_cache" / "edition_ops_products_snapshot.json"

ROWS_KEY = "orders_allocation_rows"
META_KEY = "orders_allocation_meta"
SNAPSHOT_LOADED_KEY = "orders_allocation_snapshot_loaded"
NOTICE_KEY = "orders_allocation_notice"
SNAPSHOT_FILE_NAME = "orders_allocation_snapshot.json"

VISIBLE_COLUMNS = (
    "order",
    "date",
    "customer",
    "shipping",
    "product",
    "variant",
    "edition",
)


def _format_time(value):
    if not value:
        return "Never"
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone().strftime("%d %b %Y %I:%M %p")
    except ValueError:
        return str(value)


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _ensure_state():
    st.session_state.setdefault(ROWS_KEY, [])
    st.session_state.setdefault(META_KEY, {"last_refreshed": "", "saved_at": ""})
    st.session_state.setdefault(NOTICE_KEY, "")


def _parse_datetime(value):
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)


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


def _allocation_numbers(allocation):
    values = allocation.get("edition_numbers")
    if isinstance(values, list):
        numbers = []
        for number in values:
            normalised = _normalise_edition_number(number)
            if normalised:
                numbers.append(normalised)
        return numbers
    single = _normalise_edition_number(
        allocation.get("edition_number")
        or allocation.get("edition_display")
        or allocation.get("edition")
    )
    return [single] if single else []


def _normalise_row(row):
    updated = dict(row or {})
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
    updated["edition"] = _format_edition(edition_number)
    updated["has_saved_allocation"] = bool(updated.get("has_saved_allocation"))
    updated["edition_offset"] = int(updated.get("edition_offset") or 0)
    updated["shopify_order_id"] = str(updated.get("shopify_order_id") or "")
    updated["legacy_resource_id"] = str(updated.get("legacy_resource_id") or "")
    updated["shopify_line_item_id"] = str(updated.get("shopify_line_item_id") or "")
    updated["shopify_product_id"] = str(updated.get("shopify_product_id") or "")
    updated["customer_email"] = str(updated.get("customer_email") or "")
    updated["processed_at"] = str(updated.get("processed_at") or "")
    updated["created_at"] = str(updated.get("created_at") or "")
    updated["order_number_sort"] = int(updated.get("order_number_sort") or _parse_order_number(updated["order"]))
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


def _load_snapshot_once():
    if st.session_state.get(SNAPSHOT_LOADED_KEY):
        return
    payload = order_allocator.load_orders_snapshot()
    st.session_state[ROWS_KEY] = _sort_rows(payload.get("rows") or [])
    st.session_state[META_KEY] = {
        "last_refreshed": payload.get("last_refreshed") or "",
        "saved_at": payload.get("saved_at") or "",
    }
    st.session_state[SNAPSHOT_LOADED_KEY] = True


def _write_snapshot(rows, meta=None):
    sorted_rows = _sort_rows(rows)
    payload = order_allocator.save_orders_snapshot(
        sorted_rows,
        meta=meta or st.session_state.get(META_KEY) or {},
    )
    st.session_state[META_KEY] = {
        "last_refreshed": payload.get("last_refreshed") or "",
        "saved_at": payload.get("saved_at") or "",
    }


def _edition_ops_next_numbers():
    if not EDITION_OPS_SNAPSHOT_PATH.exists():
        return {}
    try:
        payload = json.loads(EDITION_OPS_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    lookup = {}
    for row in payload.get("rows") or []:
        product_id = str(row.get("shopify_product_gid") or row.get("shopify_product_id") or "").strip()
        if not product_id:
            continue
        next_number = _normalise_edition_number(row.get("edition_next_number"))
        if next_number:
            lookup[product_id] = next_number
    return lookup


def _apply_latest_product_numbers(rows):
    next_numbers = _edition_ops_next_numbers()
    if not next_numbers:
        return _sort_rows(rows)
    refreshed = []
    for row in rows:
        updated = _normalise_row(row)
        if not updated.get("has_saved_allocation"):
            product_next = next_numbers.get(updated.get("shopify_product_id"))
            if product_next:
                updated["edition_number"] = product_next + int(updated.get("edition_offset") or 0)
                updated["edition"] = _format_edition(updated["edition_number"])
        refreshed.append(updated)
    return _sort_rows(refreshed)


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
    except Exception:
        edition = {}
    cache[product_id] = edition
    return edition


def _rows_from_order_line(order, line_item, edition):
    quantity = max(int(line_item.get("quantity") or 1), 1)
    allocation = _allocation_for_line(order, line_item)
    allocation_numbers = _allocation_numbers(allocation)
    product_next_number = _normalise_edition_number(edition.get("edition_next_number"))
    rows = []
    for index in range(quantity):
        saved_number = allocation_numbers[index] if index < len(allocation_numbers) else None
        edition_number = saved_number or (product_next_number + index if product_next_number else None)
        rows.append(
            _normalise_row(
                {
                    "order": order.get("order_name") or "",
                    "date": (order.get("processed_at") or order.get("created_at") or "")[:10],
                    "customer": order.get("customer_name") or order.get("customer_email") or "",
                    "customer_email": order.get("customer_email") or "",
                    "shipping": order.get("shipping_method") or order.get("shipping_title") or "",
                    "product": line_item.get("product_title") or "",
                    "variant": line_item.get("variant_title") or "",
                    "edition_number": edition_number,
                    "has_saved_allocation": bool(saved_number),
                    "edition_offset": index,
                    "shopify_order_id": order.get("shopify_order_id") or "",
                    "legacy_resource_id": order.get("legacy_resource_id") or "",
                    "shopify_line_item_id": line_item.get("shopify_line_item_id") or "",
                    "shopify_product_id": line_item.get("shopify_product_id") or "",
                    "processed_at": order.get("processed_at") or "",
                    "created_at": order.get("created_at") or "",
                    "order_number_sort": _parse_order_number(order.get("order_name")),
                }
            )
        )
    return rows


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
                rows.extend(_rows_from_order_line(order, line_item, edition))
    refreshed_at = _now_iso()
    sorted_rows = _sort_rows(rows)
    st.session_state[ROWS_KEY] = sorted_rows
    _write_snapshot(sorted_rows, meta={"last_refreshed": refreshed_at})
    st.session_state[NOTICE_KEY] = f"Refreshed {len(sorted_rows)} artwork rows."


def _display_rows(rows):
    return [
        {column: _normalise_row(row).get(column, "") for column in VISIBLE_COLUMNS}
        for row in _apply_latest_product_numbers(rows)
    ]


def _column_config():
    return {
        "order": st.column_config.TextColumn("Order"),
        "date": st.column_config.TextColumn("Date"),
        "customer": st.column_config.TextColumn("Customer"),
        "shipping": st.column_config.TextColumn("Shipping"),
        "product": st.column_config.TextColumn("Product"),
        "variant": st.column_config.TextColumn("Variant"),
        "edition": st.column_config.TextColumn("Edition"),
    }


def render_page():
    _ensure_state()
    _load_snapshot_once()
    rows = _apply_latest_product_numbers(st.session_state.get(ROWS_KEY, []))
    st.session_state[ROWS_KEY] = rows
    meta = st.session_state.get(META_KEY) or {}

    st.title("Orders")
    st.caption("Clean fulfilment mirror. Edition numbers are controlled from Edition Ops.")
    st.caption(f"Last refreshed: {_format_time(meta.get('last_refreshed'))}")

    notice = st.session_state.get(NOTICE_KEY)
    if notice:
        st.success(notice)
        st.session_state[NOTICE_KEY] = ""

    if st.button("Refresh Orders", type="primary", use_container_width=True):
        with st.spinner("Refreshing recent paid orders..."):
            _refresh_orders()
        st.rerun()

    if not rows:
        st.info("No saved orders yet. Use Refresh Orders to load recent paid orders.")
        return

    st.caption(f"{len(rows)} artwork rows shown.")
    st.dataframe(
        _display_rows(rows),
        hide_index=True,
        use_container_width=True,
        column_order=VISIBLE_COLUMNS,
        column_config=_column_config(),
    )
