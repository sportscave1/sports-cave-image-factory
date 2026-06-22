from datetime import datetime, timezone
import json
from pathlib import Path

import certificate_service
import order_allocator
import shopify_sync


BASE_DIR = Path(__file__).resolve().parent
CERTIFICATE_OUTPUT_DIR = BASE_DIR / "output" / "certificates"
SNAPSHOT_PATH = BASE_DIR / "output" / "_cache" / "certificates_snapshot.json"
SNAPSHOT_VERSION = 1


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def padded_edition(value):
    try:
        number = int(value or 0)
    except (TypeError, ValueError):
        number = 0
    return f"#{number:03d}" if number > 0 else ""


def _parse_certificate_payload(value):
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        rows = value.get("certificates") if isinstance(value.get("certificates"), list) else []
        return [dict(item) for item in rows if isinstance(item, dict)]
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, ValueError):
        parsed = []
    return _parse_certificate_payload(parsed)


def certificate_metafield_from_list(metafields):
    for metafield in metafields or []:
        if metafield.get("namespace") == "sports_cave" and metafield.get("key") == "certificates":
            return metafield
    return {}


def certificate_payload_from_metafields(metafields):
    return _parse_certificate_payload((certificate_metafield_from_list(metafields) or {}).get("value"))


def read_order_certificate_state(order_id, config=None, request_post=None):
    fetched = shopify_sync.fetch_metafields(
        order_allocator.order_gid(order_id),
        namespace="sports_cave",
        config=config,
        request_post=request_post,
    )
    metafield = certificate_metafield_from_list(fetched.get("metafields") or [])
    return {
        "certificates": _parse_certificate_payload((metafield or {}).get("value")),
        "compare_digest": (metafield or {}).get("compareDigest"),
        "api_version": fetched.get("api_version"),
    }


def _customer_name(order_payload):
    customer = order_payload.get("customer") if isinstance(order_payload.get("customer"), dict) else {}
    first_last = " ".join(
        part
        for part in (
            customer.get("firstName") or customer.get("first_name"),
            customer.get("lastName") or customer.get("last_name"),
        )
        if part
    ).strip()
    shipping = order_payload.get("shippingAddress") or order_payload.get("shipping_address") or {}
    return (
        order_payload.get("customer_name")
        or customer.get("displayName")
        or first_last
        or shipping.get("name")
        or order_payload.get("customer_email")
        or customer.get("email")
        or ""
    )


def _customer_email(order_payload):
    customer = order_payload.get("customer") if isinstance(order_payload.get("customer"), dict) else {}
    return order_payload.get("customer_email") or customer.get("email") or order_payload.get("email") or ""


def _purchase_date(order_payload):
    return (
        order_payload.get("processed_at")
        or order_payload.get("processedAt")
        or order_payload.get("created_at")
        or order_payload.get("createdAt")
        or ""
    )


def _line_items(order_payload):
    raw_line_items = order_payload.get("line_items")
    if isinstance(raw_line_items, list):
        return raw_line_items
    if isinstance(raw_line_items, dict):
        return raw_line_items.get("nodes") or []
    return []


def _line_lookup(order_payload):
    output = {}
    for line_item in _line_items(order_payload):
        line_id = order_allocator._line_identity(line_item)
        if line_id:
            output[str(line_id)] = line_item
    return output


def _variant_gid(line_item):
    variant = line_item.get("variant") if isinstance(line_item.get("variant"), dict) else {}
    raw = line_item.get("variant_id") or line_item.get("variantId") or variant.get("id")
    if not raw:
        return ""
    if str(raw).startswith("gid://"):
        return str(raw)
    return shopify_sync.shopify_gid("ProductVariant", raw)


def _line_product_title(allocation, line_item):
    return (
        allocation.get("product_title")
        or line_item.get("product_title")
        or line_item.get("title")
        or line_item.get("name")
        or ""
    )


def _line_variant_title(allocation, line_item):
    variant = line_item.get("variant") if isinstance(line_item.get("variant"), dict) else {}
    return allocation.get("variant_title") or line_item.get("variant_title") or line_item.get("variantTitle") or variant.get("title") or ""


def _line_handle(allocation, line_item, product_title):
    product = line_item.get("product") if isinstance(line_item.get("product"), dict) else {}
    return (
        allocation.get("handle")
        or allocation.get("shopify_handle")
        or line_item.get("product_handle")
        or line_item.get("handle")
        or product.get("handle")
        or certificate_service.safe_filename_part(product_title)
    )


def _certificate_key(record):
    return (
        str(record.get("line_item_id") or ""),
        int(record.get("edition_number") or 0),
        int(record.get("line_item_unit_index") or 1),
    )


def _existing_ready_certificate(existing, line_id, edition_number, unit_index):
    key = (str(line_id or ""), int(edition_number or 0), int(unit_index or 1))
    record = existing.get(key)
    if not record:
        return None
    if str(record.get("status") or "").casefold() == "ready" and (record.get("pdf_url") or record.get("certificate_url")):
        return record
    return None


def _replace_certificate(existing_records, replacement):
    replacement_key = _certificate_key(replacement)
    rows = [row for row in existing_records if _certificate_key(row) != replacement_key]
    rows.append(replacement)
    return rows


def _certificate_base_record(order_payload, line_id, allocation, line_item, edition_number, unit_index):
    order_gid = order_allocator._order_identity(order_payload)
    order_name = order_payload.get("order_name") or order_payload.get("name") or ""
    product_title = _line_product_title(allocation, line_item)
    variant_title = _line_variant_title(allocation, line_item)
    handle = _line_handle(allocation, line_item, product_title)
    edition_total = int(allocation.get("edition_total") or 0)
    product_gid = allocation.get("product_id") or line_item.get("shopify_product_id") or order_allocator._line_product_gid(line_item)
    certificate_id = certificate_service.certificate_id(order_name, edition_number, handle)
    return {
        "certificate_id": certificate_id,
        "order_gid": order_gid,
        "order_name": order_name,
        "line_item_id": line_id,
        "line_item_unit_index": int(unit_index or 1),
        "product_gid": product_gid,
        "variant_gid": _variant_gid(line_item),
        "product_title": product_title,
        "variant_title": variant_title,
        "handle": handle,
        "edition_number": int(edition_number or 0),
        "edition_display": padded_edition(edition_number),
        "edition_total": edition_total,
        "customer_name": _customer_name(order_payload),
        "customer_email": _customer_email(order_payload),
        "purchase_date": _purchase_date(order_payload),
        "pdf_shopify_file_id": "",
        "pdf_url": "",
        "generated_at": "",
        "status": "Generating",
    }


def certificate_records_from_allocations(order_payload, allocation_payload):
    line_lookup = _line_lookup(order_payload)
    output = []
    for line_id, allocation in (allocation_payload.get("line_items") or {}).items():
        if not isinstance(allocation, dict):
            continue
        line_item = line_lookup.get(str(line_id), {})
        for index, edition_number in enumerate(allocation.get("edition_numbers") or [], start=1):
            try:
                number = int(edition_number or 0)
            except (TypeError, ValueError):
                number = 0
            if number > 0:
                output.append(_certificate_base_record(order_payload, line_id, allocation, line_item, number, index))
    return output


def certificate_status_for_order(order_payload):
    allocations = order_allocator.allocation_payload_from_metafields(order_payload.get("metafields") or [])
    if not (allocations.get("line_items") or {}):
        return "Waiting for edition allocation"
    certificates = certificate_payload_from_metafields(order_payload.get("metafields") or [])
    existing = {_certificate_key(item): item for item in certificates}
    for record in certificate_records_from_allocations(order_payload, allocations):
        ready = _existing_ready_certificate(
            existing,
            record.get("line_item_id"),
            record.get("edition_number"),
            record.get("line_item_unit_index"),
        )
        if not ready:
            return "Template missing" if not certificate_service.CERTIFICATE_TEMPLATE_PRINT_PATH.exists() else "Generating"
    return "Ready"


def generate_missing_certificates_for_order(
    order_payload,
    *,
    config=None,
    request_post=None,
    upload_post=None,
    output_dir=None,
    force=False,
    selected_certificate_ids=None,
):
    config = config or shopify_sync.get_config()
    order_gid = order_allocator._order_identity(order_payload)
    if not order_gid:
        raise shopify_sync.ShopifyAPIError("Order ID is missing for certificate generation.")

    allocation_state = order_allocator.read_order_allocation_state(
        order_gid,
        config=config,
        request_post=request_post,
    )
    allocation_payload = allocation_state.get("payload") or {}
    if not (allocation_payload.get("line_items") or {}):
        return {
            "processed": False,
            "status": "Waiting for edition allocation",
            "generated": 0,
            "skipped": 0,
            "errors": [],
            "certificates": [],
        }

    certificate_state = read_order_certificate_state(order_gid, config=config, request_post=request_post)
    certificates = certificate_state.get("certificates") or []
    existing = {_certificate_key(item): item for item in certificates}
    selected = {str(item) for item in (selected_certificate_ids or []) if item}
    output_dir = Path(output_dir or CERTIFICATE_OUTPUT_DIR)
    generated = 0
    skipped = 0
    errors = []
    changed = False

    for record in certificate_records_from_allocations(order_payload, allocation_payload):
        if selected and record.get("certificate_id") not in selected:
            continue
        ready = _existing_ready_certificate(
            existing,
            record.get("line_item_id"),
            record.get("edition_number"),
            record.get("line_item_unit_index"),
        )
        if ready and not force:
            skipped += 1
            continue

        filename = certificate_service.certificate_pdf_filename(
            record.get("order_name"),
            record.get("handle"),
            record.get("edition_number"),
            record.get("edition_total"),
        )
        if not certificate_service.CERTIFICATE_TEMPLATE_PRINT_PATH.exists():
            record["status"] = "Template missing"
            record["sync_error"] = f"Certificate template missing: {certificate_service.CERTIFICATE_TEMPLATE_PRINT_PATH}"
            record["generated_at"] = now_iso()
            certificates = _replace_certificate(certificates, record)
            existing[_certificate_key(record)] = record
            errors.append(record["sync_error"])
            changed = True
            continue

        try:
            pdf_path = certificate_service.generate_certificate_pdf(
                output_dir,
                product_title=record.get("product_title"),
                edition_number=record.get("edition_number"),
                edition_total=record.get("edition_total"),
                order_name=record.get("order_name"),
                customer_name=record.get("customer_name"),
                assigned_at=record.get("purchase_date"),
                shopify_handle=record.get("handle"),
                filename=filename,
            )
            upload_result = shopify_sync.upload_pdf_to_shopify_files(
                pdf_path,
                filename=filename,
                alt=f"{record.get('certificate_id')} certificate",
                config=config,
                request_post=request_post,
                upload_post=upload_post,
            )
            if not upload_result.get("file_id") or not upload_result.get("url"):
                raise shopify_sync.ShopifyAPIError("Shopify file upload did not return a ready PDF URL.")
            record["pdf_shopify_file_id"] = upload_result.get("file_id") or ""
            record["pdf_url"] = upload_result.get("url") or ""
            record["generated_at"] = now_iso()
            record["status"] = "Ready"
            record["sync_error"] = ""
            generated += 1
        except FileNotFoundError as error:
            record["status"] = "Template missing"
            record["sync_error"] = str(error)
            record["generated_at"] = now_iso()
            errors.append(str(error))
        except Exception as error:
            record["status"] = "Upload error"
            record["sync_error"] = str(error)
            record["generated_at"] = now_iso()
            errors.append(str(error))

        certificates = _replace_certificate(certificates, record)
        existing[_certificate_key(record)] = record
        changed = True

    if changed:
        shopify_sync.sync_order_certificate_metafields(
            order_gid,
            certificates,
            compare_digest=certificate_state.get("compare_digest"),
            config=config,
            request_post=request_post,
        )

    return {
        "processed": True,
        "status": "Ready" if generated and not errors else ("Needs review" if errors else "Already ready"),
        "generated": generated,
        "skipped": skipped,
        "errors": errors,
        "certificates": certificates,
    }


def certificate_rows_from_order(order_payload):
    allocations = order_allocator.allocation_payload_from_metafields(order_payload.get("metafields") or [])
    certificates = certificate_payload_from_metafields(order_payload.get("metafields") or [])
    existing = {_certificate_key(item): item for item in certificates}
    rows = []
    if not (allocations.get("line_items") or {}):
        for line_item in _line_items(order_payload):
            rows.append(
                {
                    "order": order_payload.get("order_name") or order_payload.get("name") or "",
                    "date": (_purchase_date(order_payload) or "")[:10],
                    "customer": _customer_name(order_payload),
                    "product": line_item.get("product_title") or line_item.get("title") or "",
                    "variant": line_item.get("variant_title") or line_item.get("variantTitle") or "",
                    "edition": "",
                    "certificate": "Waiting for edition allocation",
                    "certificate_id": "",
                    "pdf_url": "",
                    "order_gid": order_allocator._order_identity(order_payload),
                    "processed_at": _purchase_date(order_payload),
                }
            )
        return rows

    for record in certificate_records_from_allocations(order_payload, allocations):
        certificate = existing.get(_certificate_key(record)) or {}
        status = certificate.get("status") or "Generating"
        if status == "Ready" and not (certificate.get("pdf_url") or certificate.get("certificate_url")):
            status = "Upload error"
        rows.append(
            {
                "order": record.get("order_name") or "",
                "date": (record.get("purchase_date") or "")[:10],
                "customer": record.get("customer_name") or record.get("customer_email") or "",
                "product": record.get("product_title") or "",
                "variant": record.get("variant_title") or "",
                "edition": record.get("edition_display") or padded_edition(record.get("edition_number")),
                "certificate": "Ready" if status == "Ready" else status,
                "certificate_id": record.get("certificate_id") or "",
                "pdf_url": certificate.get("pdf_url") or certificate.get("certificate_url") or "",
                "order_gid": record.get("order_gid") or "",
                "processed_at": record.get("purchase_date") or "",
            }
        )
    return rows


def _sort_rows(rows):
    def parse(value):
        try:
            return datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        except ValueError:
            return datetime.min.replace(tzinfo=timezone.utc)

    return sorted(rows or [], key=lambda row: parse(row.get("processed_at") or row.get("date")), reverse=True)


def save_certificates_snapshot(rows, meta=None):
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": SNAPSHOT_VERSION,
        "saved_at": now_iso(),
        "last_refreshed": (meta or {}).get("last_refreshed") or "",
        "rows": _sort_rows(rows),
    }
    SNAPSHOT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def load_certificates_snapshot():
    if not SNAPSHOT_PATH.exists():
        return {"version": SNAPSHOT_VERSION, "saved_at": "", "last_refreshed": "", "rows": []}
    try:
        payload = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"version": SNAPSHOT_VERSION, "saved_at": "", "last_refreshed": "", "rows": []}
    payload.setdefault("rows", [])
    payload.setdefault("saved_at", "")
    payload.setdefault("last_refreshed", "")
    return payload


def refresh_certificates_snapshot(config=None, request_post=None, *, max_orders=100):
    config = config or shopify_sync.get_config()
    rows = []
    for page in shopify_sync.iter_order_pages(
        days=30,
        page_size=50,
        max_orders=max_orders,
        query="financial_status:paid",
        default_paid_unfulfilled_filter=False,
        config=config,
        request_post=request_post,
    ):
        for order in page.get("orders") or []:
            rows.extend(certificate_rows_from_order(order))
    refreshed_at = now_iso()
    return save_certificates_snapshot(rows, {"last_refreshed": refreshed_at})


def generate_missing_certificates_for_recent_orders(config=None, request_post=None, upload_post=None, *, max_orders=100):
    config = config or shopify_sync.get_config()
    totals = {"processed_orders": 0, "generated": 0, "skipped": 0, "errors": []}
    for page in shopify_sync.iter_order_pages(
        days=30,
        page_size=50,
        max_orders=max_orders,
        query="financial_status:paid",
        default_paid_unfulfilled_filter=False,
        config=config,
        request_post=request_post,
    ):
        for order in page.get("orders") or []:
            result = generate_missing_certificates_for_order(
                order,
                config=config,
                request_post=request_post,
                upload_post=upload_post,
            )
            totals["processed_orders"] += 1
            totals["generated"] += result.get("generated", 0)
            totals["skipped"] += result.get("skipped", 0)
            totals["errors"].extend(result.get("errors") or [])
    refresh_certificates_snapshot(config=config, request_post=request_post, max_orders=max_orders)
    return totals


def regenerate_certificate_by_id(certificate_id, config=None, request_post=None, upload_post=None, *, max_orders=100):
    config = config or shopify_sync.get_config()
    target = str(certificate_id or "").strip()
    if not target:
        return {"found": False, "generated": 0, "errors": ["No certificate selected."]}
    for page in shopify_sync.iter_order_pages(
        days=30,
        page_size=50,
        max_orders=max_orders,
        query="financial_status:paid",
        default_paid_unfulfilled_filter=False,
        config=config,
        request_post=request_post,
    ):
        for order in page.get("orders") or []:
            allocations = order_allocator.allocation_payload_from_metafields(order.get("metafields") or [])
            candidate_ids = {
                record.get("certificate_id")
                for record in certificate_records_from_allocations(order, allocations)
            }
            if target not in candidate_ids:
                continue
            result = generate_missing_certificates_for_order(
                order,
                config=config,
                request_post=request_post,
                upload_post=upload_post,
                force=True,
                selected_certificate_ids=[target],
            )
            refresh_certificates_snapshot(config=config, request_post=request_post, max_orders=max_orders)
            return {"found": True, **result}
    return {"found": False, "generated": 0, "errors": [f"Certificate not found in recent paid orders: {target}"]}
