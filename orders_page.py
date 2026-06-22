from datetime import datetime, timezone
import json
from pathlib import Path
import re

import streamlit as st

import certificate_engine
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
    "certificate",
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


def _certificate_label(row):
    if row.get("certificate_pdf_url"):
        return "Uploaded"
    status = str(row.get("certificate_status") or "").strip()
    if status in {"Generated", "Uploaded", "Error", "Template missing", "Upload error"}:
        return "Error" if status in {"Template missing", "Upload error"} else status
    if row.get("certificate_pdf_path"):
        return "Generated"
    return "Generate"


def _allocation_numbers(allocation):
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
    edition_total = int(allocation.get("edition_total") or edition.get("edition_total") or 100)
    rows = []
    for index in range(quantity):
        saved_number = allocation_numbers[index] if index < len(allocation_numbers) else None
        edition_number = saved_number or (product_next_number + index if product_next_number else None)
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
                    "customer_email": order.get("customer_email") or "",
                    "shipping": order.get("shipping_method") or order.get("shipping_title") or "",
                    "product": line_item.get("product_title") or "",
                    "variant": line_item.get("variant_title") or "",
                    "edition_number": edition_number,
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
                    "certificate_status": "Uploaded" if certificate.get("pdf_url") else certificate.get("status") or "",
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


def _refresh_orders():
    config = shopify_sync.get_config()
    if not config.get("configured"):
        st.session_state[NOTICE_KEY] = "Store connection is not configured yet. Ask a developer before refreshing orders."
        return
    existing_rows = st.session_state.get(ROWS_KEY, [])
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
    sorted_rows = _sort_rows(_merge_local_certificate_fields(rows, existing_rows))
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
        "certificate": st.column_config.TextColumn("Certificate"),
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
    state = certificate_engine.read_order_certificate_state(row.get("shopify_order_id"), config=config)
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
            _lock_allocation_for_row(row, config)
            row["has_saved_allocation"] = True
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


def _pdf_bytes(path):
    try:
        pdf_path = Path(path)
        if pdf_path.exists() and pdf_path.is_file():
            return pdf_path.read_bytes()
    except Exception:
        return b""
    return b""


def _selected_row_from_event(event, rows):
    try:
        selected_rows = list(event.selection.rows or [])
    except Exception:
        selected_rows = []
    if not selected_rows:
        return _normalise_row(rows[0]) if rows else {}
    index = int(selected_rows[0])
    if index < 0 or index >= len(rows):
        return _normalise_row(rows[0]) if rows else {}
    return _normalise_row(rows[index])


def _certificate_filename(row):
    record = certificate_engine.certificate_record_from_order_row(row)
    return f"{record.get('certificate_id') or 'sports-cave-certificate'}.pdf".lower()


def _render_certificate_actions(row):
    row = _normalise_row(row)
    key_base = f"order-cert-{row.get('shopify_order_id')}-{row.get('shopify_line_item_id')}-{row.get('edition_offset')}"
    st.subheader("Selected Order")
    st.caption(
        f"{row.get('order') or 'Order'} | {row.get('customer') or 'Customer'} | "
        f"{row.get('product') or 'Artwork'} | {row.get('edition') or 'No edition'}"
    )
    if row.get("certificate_preview_path") and Path(row.get("certificate_preview_path")).exists():
        st.image(row.get("certificate_preview_path"), caption="Certificate preview", use_container_width=True)

    action_cols = st.columns(4)
    if row.get("certificate_pdf_url"):
        action_cols[0].success("Uploaded")
        if row.get("certificate_pdf_path") and Path(row.get("certificate_pdf_path")).exists():
            action_cols[1].download_button(
                "Download PDF",
                data=_pdf_bytes(row.get("certificate_pdf_path")),
                file_name=_certificate_filename(row),
                mime="application/pdf",
                use_container_width=True,
                key=f"{key_base}-download-uploaded",
            )
        action_cols[2].link_button("Open PDF", row["certificate_pdf_url"], use_container_width=True)
        return
    if row.get("certificate_pdf_path") and Path(row.get("certificate_pdf_path")).exists():
        action_cols[0].success("Generated")
        action_cols[1].download_button(
            "Download PDF",
            data=_pdf_bytes(row.get("certificate_pdf_path")),
            file_name=_certificate_filename(row),
            mime="application/pdf",
            use_container_width=True,
            key=f"{key_base}-download-generated",
        )
        if action_cols[2].button("Upload", key=f"{key_base}-upload", use_container_width=True):
            _upload_certificate_for_row(row)
            st.rerun()
        local_link = _file_link(row.get("certificate_pdf_path"))
        if local_link:
            action_cols[3].link_button("Open PDF", local_link, use_container_width=True)
        return
    if str(row.get("certificate_status") or "").casefold() in {"error", "template missing", "upload error"}:
        action_cols[0].error("Error")
        if row.get("certificate_error"):
            st.caption(row.get("certificate_error"))
        if action_cols[1].button("Retry", key=f"{key_base}-retry", use_container_width=True):
            _generate_certificate_for_row(row)
            st.rerun()
        return
    if action_cols[0].button("Generate", key=f"{key_base}-generate", use_container_width=True, disabled=not bool(row.get("edition_number"))):
        _generate_certificate_for_row(row)
        st.rerun()
    if not row.get("edition_number"):
        st.caption("This row needs an edition before a certificate can be generated.")


def _render_orders_table(rows):
    rows = [_normalise_row(row) for row in rows]
    with st.container(border=True):
        event = st.dataframe(
            _display_rows(rows),
            hide_index=True,
            use_container_width=True,
            height=min(720, max(320, 42 * (len(rows) + 1))),
            column_order=VISIBLE_COLUMNS,
            column_config=_column_config(),
            selection_mode="single-row",
            on_select="rerun",
            key="orders-fulfilment-grid",
        )
    if rows:
        st.caption("Select an order row above to generate, upload, download, or open its certificate.")
        selected = _selected_row_from_event(event, rows)
        with st.container(border=True):
            _render_certificate_actions(selected)


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
    _render_orders_table(rows)
