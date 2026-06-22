from datetime import datetime, timezone
import json
from pathlib import Path
import re

import shopify_sync


BASE_DIR = Path(__file__).resolve().parent
SNAPSHOT_PATH = BASE_DIR / "output" / "_cache" / "orders_allocation_snapshot.json"
SNAPSHOT_VERSION = 1


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def format_edition_numbers(numbers, total):
    values = [int(number) for number in numbers or [] if int(number or 0) > 0]
    if not values:
        return ""
    if len(values) == 1:
        return f"#{values[0]:03d}/{int(total or 0)}"
    return f"#{values[0]:03d}-{values[-1]:03d}/{int(total or 0)}"


def parse_allocation_payload(value):
    if isinstance(value, dict):
        payload = dict(value)
    else:
        try:
            payload = json.loads(value or "{}")
        except (TypeError, ValueError):
            payload = {}
    line_items = payload.get("line_items")
    if isinstance(line_items, dict):
        payload["line_items"] = line_items
        return payload
    mapped = {}
    if isinstance(line_items, list):
        for item in line_items:
            if not isinstance(item, dict):
                continue
            line_id = item.get("line_item_id") or item.get("shopify_line_item_id")
            if line_id:
                mapped[str(line_id)] = item
    payload["line_items"] = mapped
    return payload


def allocation_metafield_from_list(metafields):
    for metafield in metafields or []:
        if metafield.get("namespace") == "sports_cave" and metafield.get("key") == "edition_allocations":
            return metafield
    return {}


def allocation_payload_from_metafields(metafields):
    return parse_allocation_payload((allocation_metafield_from_list(metafields) or {}).get("value"))


def line_item_gid(value):
    raw = str(value or "").strip()
    if raw.startswith("gid://"):
        return raw
    return shopify_sync.shopify_gid("LineItem", raw)


def product_gid(value):
    raw = str(value or "").strip()
    if raw.startswith("gid://"):
        return raw
    return shopify_sync.shopify_gid("Product", raw)


def order_gid(value):
    raw = str(value or "").strip()
    if raw.startswith("gid://"):
        return raw
    return shopify_sync.shopify_gid("Order", raw)


def _coerce_quantity(value):
    try:
        return max(int(value or 1), 1)
    except (TypeError, ValueError):
        return 1


def _order_identity(order_payload):
    return order_gid(
        order_payload.get("admin_graphql_api_id")
        or order_payload.get("shopify_order_id")
        or order_payload.get("id")
    )


def _line_identity(line_item):
    return line_item_gid(
        line_item.get("admin_graphql_api_id")
        or line_item.get("shopify_line_item_id")
        or line_item.get("id")
    )


def _line_product_gid(line_item):
    product = line_item.get("product") if isinstance(line_item.get("product"), dict) else {}
    return product_gid(
        line_item.get("shopify_product_id")
        or line_item.get("product_id")
        or product.get("id")
    )


def _line_variant_gid(line_item):
    variant = line_item.get("variant") if isinstance(line_item.get("variant"), dict) else {}
    raw = (
        line_item.get("variant_id")
        or line_item.get("variantId")
        or line_item.get("shopify_variant_id")
        or variant.get("id")
    )
    return shopify_sync.shopify_gid("ProductVariant", raw)


def _order_name(order_payload):
    return order_payload.get("name") or order_payload.get("order_name") or ""


def _line_product_title(line_item):
    product = line_item.get("product") if isinstance(line_item.get("product"), dict) else {}
    return (
        line_item.get("product_title")
        or line_item.get("title")
        or line_item.get("name")
        or product.get("title")
        or ""
    )


def _line_variant_title(line_item):
    variant = line_item.get("variant") if isinstance(line_item.get("variant"), dict) else {}
    return line_item.get("variant_title") or line_item.get("variantTitle") or variant.get("title") or ""


def _line_product_handle(line_item):
    product = line_item.get("product") if isinstance(line_item.get("product"), dict) else {}
    return line_item.get("product_handle") or line_item.get("handle") or product.get("handle") or ""


def _parse_datetime(value):
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_order_number(value):
    digits = re.findall(r"\d+", str(value or ""))
    return int(digits[-1]) if digits else 0


def allocation_order_key(order_payload):
    return (
        _parse_datetime(order_payload.get("processedAt") or order_payload.get("processed_at")),
        _parse_datetime(order_payload.get("createdAt") or order_payload.get("created_at")),
        _parse_order_number(order_payload.get("name") or order_payload.get("order_name") or order_payload.get("order_number")),
    )


def _line_position(line_item, fallback):
    for key in ("position", "line_item_position", "index"):
        try:
            value = int(line_item.get(key))
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return fallback


def _financial_status(order_payload):
    return str(
        order_payload.get("financial_status")
        or order_payload.get("displayFinancialStatus")
        or ""
    ).strip().casefold()


def _is_paid_order(order_payload):
    status = _financial_status(order_payload)
    return status in {"paid", "paid_status", "displayfinancialstatus.paid"} or status.upper() == "PAID"


def _is_enabled(value):
    if isinstance(value, bool):
        return value
    return str(value or "").strip().casefold() in {"true", "1", "yes", "on"}


def _metafields_by_key(metafields):
    return {
        item.get("key"): item
        for item in metafields or []
        if item.get("namespace") == "sports_cave" and item.get("key")
    }


def _product_edition_from_metafields(metafields):
    by_key = _metafields_by_key(metafields)
    edition = shopify_sync.normalize_limited_edition_metafields(metafields)
    edition["edition_enabled"] = _is_enabled((by_key.get("edition_enabled") or {}).get("value"))
    return edition


def read_order_allocation_state(order_id, config=None, request_post=None):
    fetched = shopify_sync.fetch_metafields(
        order_gid(order_id),
        namespace="sports_cave",
        config=config,
        request_post=request_post,
    )
    metafield = allocation_metafield_from_list(fetched.get("metafields") or [])
    return {
        "payload": parse_allocation_payload((metafield or {}).get("value")),
        "compare_digest": (metafield or {}).get("compareDigest"),
        "api_version": fetched.get("api_version"),
    }


def _line_items(order_payload):
    raw_line_items = order_payload.get("line_items")
    if isinstance(raw_line_items, list):
        return raw_line_items
    if isinstance(raw_line_items, dict):
        return raw_line_items.get("nodes") or []
    return []


def _positive_int(value, default=0):
    try:
        number = int(value or default)
    except (TypeError, ValueError):
        digits = re.findall(r"\d+", str(value or ""))
        number = int(digits[0]) if digits else int(default)
    return number if number > 0 else int(default)


def _metafield_compare_digests(metafields):
    return {
        item.get("key"): item.get("compareDigest")
        for item in metafields or []
        if item.get("namespace") == "sports_cave" and item.get("key") and item.get("compareDigest") is not None
    }


def _normalise_edition_numbers(values, quantity=0):
    numbers = []
    if isinstance(values, list):
        raw_values = values
    elif values not in (None, ""):
        raw_values = [values]
    else:
        raw_values = []
    for value in raw_values:
        number = _positive_int(value)
        numbers.append(number or None)
    while len(numbers) < int(quantity or 0):
        numbers.append(None)
    return numbers


def _allocation_numbers(allocation, quantity=0):
    numbers = _normalise_edition_numbers((allocation or {}).get("edition_numbers"), quantity)
    for unit in (allocation or {}).get("unit_allocations") or []:
        if not isinstance(unit, dict):
            continue
        unit_index = _positive_int(unit.get("line_item_unit_index"))
        edition_number = _positive_int(unit.get("edition_number"))
        if not unit_index or not edition_number:
            continue
        while len(numbers) < unit_index:
            numbers.append(None)
        numbers[unit_index - 1] = numbers[unit_index - 1] or edition_number
    if not any(numbers):
        single = _positive_int(
            (allocation or {}).get("edition_number")
            or (allocation or {}).get("edition")
            or (allocation or {}).get("edition_display")
        )
        if single:
            numbers = [single]
    while len(numbers) < int(quantity or 0):
        numbers.append(None)
    return numbers


def _unit_allocation_record(order_payload, line_item, product_id, variant_id, edition_number, unit_index):
    return {
        "order_gid": _order_identity(order_payload),
        "line_item_gid": _line_identity(line_item),
        "line_item_unit_index": int(unit_index),
        "product_gid": product_id,
        "variant_gid": variant_id or "",
        "edition_number": int(edition_number),
    }


def _allocation_record(order_payload, line_item, product_id, edition_numbers, edition_total, status="Allocated"):
    line_id = _line_identity(line_item)
    quantity = _coerce_quantity(line_item.get("quantity"))
    numbers = _normalise_edition_numbers(edition_numbers, quantity)
    positive_numbers = [number for number in numbers if number]
    display = format_edition_numbers(positive_numbers, edition_total)
    variant_id = _line_variant_gid(line_item)
    unit_allocations = [
        _unit_allocation_record(order_payload, line_item, product_id, variant_id, number, index)
        for index, number in enumerate(numbers, start=1)
        if number
    ]
    return {
        "line_item_id": line_id,
        "order_id": _order_identity(order_payload),
        "product_id": product_id,
        "variant_id": variant_id,
        "handle": _line_product_handle(line_item),
        "product_title": _line_product_title(line_item),
        "variant_title": _line_variant_title(line_item),
        "quantity": quantity,
        "edition_numbers": numbers,
        "edition_number": positive_numbers[0] if positive_numbers else None,
        "edition_total": int(edition_total or 0),
        "edition_display": display,
        "unit_allocations": unit_allocations,
        "status": status,
        "order_name": _order_name(order_payload),
        "allocated_at": now_iso(),
    }


def _merge_unit_allocations(existing_units, new_units):
    merged = []
    seen_units = set()
    for unit in existing_units or []:
        if not isinstance(unit, dict):
            continue
        merged.append(unit)
        unit_index = _positive_int(unit.get("line_item_unit_index"))
        if unit_index:
            seen_units.add(unit_index)
    for unit in new_units or []:
        if not isinstance(unit, dict):
            continue
        unit_index = _positive_int(unit.get("line_item_unit_index"))
        if unit_index and unit_index in seen_units:
            continue
        merged.append(unit)
        if unit_index:
            seen_units.add(unit_index)
    return merged


def _merge_line_allocation(existing, incoming):
    existing = dict(existing or {})
    incoming = dict(incoming or {})
    quantity = max(
        _coerce_quantity(existing.get("quantity")),
        _coerce_quantity(incoming.get("quantity")),
    )
    existing_numbers = _allocation_numbers(existing, quantity)
    incoming_numbers = _allocation_numbers(incoming, quantity)
    numbers = []
    for index in range(quantity):
        existing_number = existing_numbers[index] if index < len(existing_numbers) else None
        incoming_number = incoming_numbers[index] if index < len(incoming_numbers) else None
        numbers.append(existing_number or incoming_number)

    merged = dict(existing)
    for key, value in incoming.items():
        if key in {"edition_numbers", "edition_number", "edition_display", "unit_allocations", "status"}:
            continue
        if value not in (None, "") and not merged.get(key):
            merged[key] = value
    positive_numbers = [number for number in numbers if number]
    merged["quantity"] = quantity
    merged["edition_numbers"] = numbers
    merged["edition_number"] = positive_numbers[0] if positive_numbers else None
    merged["edition_display"] = format_edition_numbers(
        positive_numbers,
        merged.get("edition_total") or incoming.get("edition_total") or 0,
    )
    merged["unit_allocations"] = _merge_unit_allocations(
        existing.get("unit_allocations") or [],
        incoming.get("unit_allocations") or [],
    )
    incoming_status = incoming.get("status")
    if positive_numbers and len(positive_numbers) >= quantity:
        merged["status"] = "Allocated"
    elif incoming_status and incoming_status != "Allocated":
        merged["status"] = incoming_status
    else:
        merged["status"] = merged.get("status") or incoming_status or "Needs allocation"
    return merged


def build_order_allocation_payload(order_payload, existing_payload, new_allocations):
    payload = parse_allocation_payload(existing_payload)
    payload.update(
        {
            "version": SNAPSHOT_VERSION,
            "source": "sports_cave_os",
            "order_id": _order_identity(order_payload),
            "order_name": _order_name(order_payload) or payload.get("order_name") or "",
            "updated_at": now_iso(),
        }
    )
    line_items = dict(payload.get("line_items") or {})
    for line_id, allocation in new_allocations.items():
        line_items[str(line_id)] = _merge_line_allocation(line_items.get(str(line_id)) or {}, allocation)
    payload["line_items"] = line_items
    return payload


def _is_compare_error(error):
    text = str(error or "").casefold()
    return "compare" in text or "digest" in text or "stale" in text


def _product_state_from_metafields(product_id, metafields):
    edition = _product_edition_from_metafields(metafields)
    edition_total = max(int(edition.get("edition_total") or 100), 1)
    sold_count = min(max(int(edition.get("edition_sold_count") or 0), 0), edition_total)
    remaining_value = edition.get("edition_remaining")
    remaining = min(
        max(int(remaining_value if remaining_value is not None else max(edition_total - sold_count, 0)), 0),
        edition_total,
    )
    next_number = max(int(edition.get("edition_next_number") or 1), 1)
    return {
        "product_id": product_id,
        "edition": edition,
        "edition_enabled": bool(edition.get("edition_enabled")),
        "edition_total": edition_total,
        "next_number": next_number,
        "sold_count": sold_count,
        "remaining": remaining,
        "status": edition.get("edition_status") or shopify_sync.calculate_limited_edition_status(remaining),
        "edition_label": edition.get("edition_label") or "Numbered Edition",
        "compare_digests": _metafield_compare_digests(metafields),
        "allocated_numbers": [],
    }


def _product_is_sold_out(product_state):
    return (
        int(product_state.get("remaining") or 0) <= 0
        or int(product_state.get("sold_count") or 0) >= int(product_state.get("edition_total") or 0)
        or int(product_state.get("next_number") or 1) > int(product_state.get("edition_total") or 0)
    )


def _advance_product_state(product_state, edition_number):
    edition_total = int(product_state.get("edition_total") or 100)
    sold_count = min(max(int(product_state.get("sold_count") or 0), int(edition_number)), edition_total)
    remaining = max(edition_total - sold_count, 0)
    next_number = int(edition_number) + 1
    if remaining <= 0:
        next_number = edition_total
    product_state["sold_count"] = sold_count
    product_state["remaining"] = remaining
    product_state["next_number"] = max(next_number, 1)
    product_state["status"] = shopify_sync.calculate_limited_edition_status(remaining)
    product_state.setdefault("allocated_numbers", []).append(int(edition_number))


def _product_update_from_state(product_state, line_item):
    return {
        "shopify_product_id": product_state["product_id"],
        "title": _line_product_title(line_item),
        "edition_enabled": True,
        "edition_total": product_state["edition_total"],
        "edition_next_number": product_state["next_number"],
        "edition_sold_count": product_state["sold_count"],
        "edition_remaining": product_state["remaining"],
        "edition_status": product_state["status"],
        "edition_label": product_state.get("edition_label") or "Numbered Edition",
        "metafield_compare_digests": product_state.get("compare_digests") or {},
    }


def _fetch_product_state(product_id, product_state_cache, config=None, request_post=None):
    if product_id not in product_state_cache:
        product_metafields = shopify_sync.fetch_metafields(
            product_id,
            namespace="sports_cave",
            config=config,
            request_post=request_post,
        ).get("metafields") or []
        product_state_cache[product_id] = _product_state_from_metafields(product_id, product_metafields)
    return product_state_cache[product_id]


def _sorted_line_items(order_payload):
    return [
        line_item
        for fallback, line_item in sorted(
            enumerate(_line_items(order_payload), start=1),
            key=lambda item: (_line_position(item[1], item[0]), item[0]),
        )
    ]


def _plan_order_allocations(order_payload, existing_payload, product_state_cache, config=None, request_post=None):
    existing_lines = (existing_payload or {}).get("line_items") or {}
    new_allocations = {}
    product_updates = {}
    assignments_created = 0
    skipped_existing = 0
    issues = []

    for line_item in _sorted_line_items(order_payload):
        line_id = _line_identity(line_item)
        if not line_id:
            continue
        quantity = _coerce_quantity(line_item.get("quantity"))
        existing_allocation = existing_lines.get(line_id) or {}
        existing_numbers = _allocation_numbers(existing_allocation, quantity)
        new_numbers = [None] * quantity
        line_status = ""

        product_id = _line_product_gid(line_item)
        if not product_id:
            issues.append({"line_item_id": line_id, "status": "Product Not Found"})
            continue

        product_state = None
        for unit_index in range(1, quantity + 1):
            if unit_index <= len(existing_numbers) and existing_numbers[unit_index - 1]:
                skipped_existing += 1
                continue
            if product_state is None:
                product_state = _fetch_product_state(
                    product_id,
                    product_state_cache,
                    config=config,
                    request_post=request_post,
                )
            if not product_state.get("edition_enabled"):
                issues.append({"line_item_id": line_id, "product_id": product_id, "status": "Edition Disabled"})
                line_status = line_status or "Needs allocation"
                continue
            if _product_is_sold_out(product_state):
                issues.append({"line_item_id": line_id, "product_id": product_id, "status": "Needs Review - Sold Out"})
                line_status = "Needs Review - Sold Out"
                continue

            edition_number = int(product_state.get("next_number") or 1)
            if edition_number > int(product_state.get("edition_total") or 0):
                issues.append({"line_item_id": line_id, "product_id": product_id, "status": "Needs Review - Sold Out"})
                line_status = "Needs Review - Sold Out"
                continue

            new_numbers[unit_index - 1] = edition_number
            assignments_created += 1
            _advance_product_state(product_state, edition_number)
            product_updates[product_id] = _product_update_from_state(product_state, line_item)

        if any(new_numbers) or line_status == "Needs Review - Sold Out":
            new_allocations[line_id] = _allocation_record(
                order_payload,
                line_item,
                product_id,
                new_numbers,
                (product_state or {}).get("edition_total") or (existing_allocation or {}).get("edition_total") or 100,
                status=line_status or "Allocated",
            )

    return {
        "new_allocations": new_allocations,
        "product_updates": product_updates,
        "assignments_created": assignments_created,
        "skipped_existing": skipped_existing,
        "issues": issues,
    }


def _sync_order_allocations_with_retry(
    shopify_order_id,
    order_payload,
    new_allocations,
    initial_state,
    config=None,
    request_post=None,
):
    state = initial_state or {}
    last_error = None
    for attempt in range(3):
        payload = build_order_allocation_payload(order_payload, state.get("payload") or {}, new_allocations)
        try:
            shopify_sync.sync_order_allocation_metafield(
                shopify_order_id,
                payload,
                compare_digest=state.get("compare_digest"),
                config=config,
                request_post=request_post,
            )
            return payload
        except shopify_sync.ShopifyAPIError as error:
            last_error = error
            if attempt < 2 and _is_compare_error(error):
                state = read_order_allocation_state(shopify_order_id, config=config, request_post=request_post)
                continue
            raise
    raise last_error


def process_shopify_order_for_editions(order_payload, config=None, request_post=None):
    config = config or shopify_sync.get_config()
    if not _is_paid_order(order_payload):
        return {"processed": False, "reason": "Order is not paid.", "assignments_created": 0, "issues": []}

    shopify_order_id = _order_identity(order_payload)
    if not shopify_order_id:
        raise shopify_sync.ShopifyAPIError("Order ID is missing from webhook payload.")

    last_compare_error = None
    for attempt in range(3):
        state = read_order_allocation_state(shopify_order_id, config=config, request_post=request_post)
        existing_payload = state.get("payload") or {}
        plan = _plan_order_allocations(
            order_payload,
            existing_payload,
            {},
            config=config,
            request_post=request_post,
        )
        new_allocations = plan["new_allocations"]
        product_updates = plan["product_updates"]

        if not new_allocations:
            return {
                "processed": True,
                "assignments_created": 0,
                "issues": plan["issues"],
                "skipped_existing": plan["skipped_existing"],
                "allocation_payload": existing_payload,
                "order_id": shopify_order_id,
            }

        try:
            if product_updates:
                shopify_sync.sync_limited_edition_metafields_for_products(
                    list(product_updates.values()),
                    config=config,
                    request_post=request_post,
                )
        except shopify_sync.ShopifyAPIError as error:
            if attempt < 2 and _is_compare_error(error):
                last_compare_error = error
                continue
            raise

        payload = _sync_order_allocations_with_retry(
            shopify_order_id,
            order_payload,
            new_allocations,
            state,
            config=config,
            request_post=request_post,
        )
        return {
            "processed": True,
            "assignments_created": plan["assignments_created"],
            "issues": plan["issues"],
            "skipped_existing": plan["skipped_existing"],
            "updated_products": len(product_updates),
            "allocation_payload": payload,
            "order_id": shopify_order_id,
        }

    raise last_compare_error or shopify_sync.ShopifyAPIError("Could not allocate editions after compareDigest retries.")


def process_shopify_orders_for_editions(orders, config=None, request_post=None):
    results = []
    errors = []
    assignments_created = 0
    for order_payload in sorted(orders or [], key=allocation_order_key):
        try:
            result = process_shopify_order_for_editions(
                order_payload,
                config=config,
                request_post=request_post,
            )
        except Exception as error:
            order_id = _order_identity(order_payload)
            result = {
                "processed": False,
                "order_id": order_id,
                "assignments_created": 0,
                "issues": [],
                "error": str(error),
            }
            errors.append({"order_id": order_id, "error": str(error)})
        assignments_created += int(result.get("assignments_created") or 0)
        results.append(result)
    return {
        "processed_orders": len(results),
        "assignments_created": assignments_created,
        "errors": errors,
        "results": results,
    }


def save_orders_snapshot(rows, meta=None):
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": SNAPSHOT_VERSION,
        "saved_at": now_iso(),
        "last_refreshed": (meta or {}).get("last_refreshed") or "",
        "rows": rows or [],
    }
    SNAPSHOT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def load_orders_snapshot():
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
