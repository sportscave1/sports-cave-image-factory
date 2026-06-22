from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re

import shopify_sync


BASE_DIR = Path(__file__).resolve().parent
SNAPSHOT_PATH = BASE_DIR / "output" / "_cache" / "orders_allocation_snapshot.json"
CUTOVER_PATH = BASE_DIR / "output" / "_cache" / "limited_edition_cutover.json"
SNAPSHOT_VERSION = 1
CUTOVER_VERSION = 1
AUTOMATION_STARTED_ENV = "LIMITED_EDITION_AUTOMATION_STARTED_AT"


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _safe_iso(value):
    parsed = _parse_datetime(value)
    if parsed == datetime.min.replace(tzinfo=timezone.utc):
        return ""
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


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


def _order_processed_datetime(order_payload):
    processed = _parse_datetime(order_payload.get("processedAt") or order_payload.get("processed_at"))
    if processed != datetime.min.replace(tzinfo=timezone.utc):
        return processed
    return _parse_datetime(order_payload.get("createdAt") or order_payload.get("created_at"))


def _line_position(line_item, fallback):
    for key in ("position", "line_item_position", "index"):
        try:
            value = int(line_item.get(key))
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return fallback


def _empty_cutover_state():
    return {
        "version": CUTOVER_VERSION,
        "automation_started_at": "",
        "baselines": {},
        "updated_at": "",
    }


def load_cutover_state():
    state = _empty_cutover_state()
    if CUTOVER_PATH.exists():
        try:
            loaded = json.loads(CUTOVER_PATH.read_text(encoding="utf-8"))
        except Exception:
            loaded = {}
        if isinstance(loaded, dict):
            state.update(loaded)
    state["version"] = CUTOVER_VERSION
    state.setdefault("baselines", {})
    env_started_at = _safe_iso(os.getenv(AUTOMATION_STARTED_ENV, ""))
    if env_started_at:
        state["automation_started_at"] = env_started_at
    return state


def save_cutover_state(state):
    payload = _empty_cutover_state()
    payload.update(state or {})
    payload["version"] = CUTOVER_VERSION
    payload["automation_started_at"] = _safe_iso(payload.get("automation_started_at")) or ""
    payload["baselines"] = payload.get("baselines") or {}
    payload["updated_at"] = now_iso()
    CUTOVER_PATH.parent.mkdir(parents=True, exist_ok=True)
    CUTOVER_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def enable_live_allocation_from_now(started_at=None):
    state = load_cutover_state()
    state["automation_started_at"] = _safe_iso(started_at or now_iso())
    return save_cutover_state(state)


def _baseline_product_gid(row):
    return product_gid(
        row.get("shopify_product_gid")
        or row.get("shopify_product_id")
        or row.get("product_gid")
        or row.get("product_id")
    )


def _baseline_from_product_row(row, captured_at):
    product_id = _baseline_product_gid(row)
    if not product_id:
        return None
    next_number = _positive_int(row.get("edition_next_number"), 1)
    total = _positive_int(row.get("edition_total"), 100)
    sold = _positive_int(row.get("edition_sold_count"), max(next_number - 1, 0))
    remaining = max(total - sold, 0)
    if row.get("edition_remaining") not in (None, ""):
        remaining = max(_positive_int(row.get("edition_remaining"), remaining), 0)
    return {
        "product_gid": product_id,
        "shopify_handle": str(row.get("handle") or row.get("shopify_handle") or "").strip(),
        "product_title": str(row.get("product_title") or row.get("title") or "").strip(),
        "baseline_next_number": next_number,
        "baseline_sold_count": sold,
        "baseline_remaining": remaining,
        "baseline_total": total,
        "baseline_captured_at": captured_at,
    }


def capture_product_baselines(product_rows, captured_at=None):
    captured = _safe_iso(captured_at or now_iso())
    state = load_cutover_state()
    baselines = dict(state.get("baselines") or {})
    count = 0
    for row in product_rows or []:
        if not isinstance(row, dict):
            continue
        baseline = _baseline_from_product_row(row, captured)
        if not baseline:
            continue
        baselines[baseline["product_gid"]] = baseline
        count += 1
    state["baselines"] = baselines
    state.setdefault("automation_started_at", "")
    saved = save_cutover_state(state)
    saved["captured_count"] = count
    return saved


def automation_started_at(cutover_state=None):
    state = cutover_state or load_cutover_state()
    started_at = _safe_iso((state or {}).get("automation_started_at") or os.getenv(AUTOMATION_STARTED_ENV, ""))
    return started_at


def _automation_started_datetime(cutover_state=None):
    started_at = automation_started_at(cutover_state)
    if not started_at:
        return None
    parsed = _parse_datetime(started_at)
    if parsed == datetime.min.replace(tzinfo=timezone.utc):
        return None
    return parsed


def _is_before_automation_start(order_payload, cutover_state=None):
    started = _automation_started_datetime(cutover_state)
    if not started:
        return False
    return _order_processed_datetime(order_payload) < started


def _allocated_unit_count(payload):
    total = 0
    for allocation in (parse_allocation_payload(payload).get("line_items") or {}).values():
        if not isinstance(allocation, dict):
            continue
        total += sum(1 for number in _allocation_numbers(allocation, _coerce_quantity(allocation.get("quantity"))) if number)
    return total


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


def _apply_allocated_numbers_to_product_state(product_state, edition_numbers):
    before = (
        int(product_state.get("next_number") or 1),
        int(product_state.get("sold_count") or 0),
        int(product_state.get("remaining") or 0),
        product_state.get("status") or "",
    )
    edition_total = int(product_state.get("edition_total") or 100)
    for number in sorted(number for number in edition_numbers or [] if number):
        sold_count = min(max(int(product_state.get("sold_count") or 0), int(number)), edition_total)
        remaining = max(edition_total - sold_count, 0)
        if remaining <= 0:
            next_number = edition_total
        else:
            next_number = min(max(int(product_state.get("next_number") or 1), int(number) + 1), edition_total)
        product_state["sold_count"] = sold_count
        product_state["remaining"] = remaining
        product_state["next_number"] = max(next_number, 1)
        product_state["status"] = shopify_sync.calculate_limited_edition_status(remaining)
    after = (
        int(product_state.get("next_number") or 1),
        int(product_state.get("sold_count") or 0),
        int(product_state.get("remaining") or 0),
        product_state.get("status") or "",
    )
    return after != before


def _product_updates_from_allocation_records(allocation_records, config=None, request_post=None):
    product_state_cache = {}
    product_updates = {}
    for allocation in allocation_records or []:
        if not isinstance(allocation, dict):
            continue
        product_id = product_gid(allocation.get("product_id") or allocation.get("shopify_product_id"))
        if not product_id:
            continue
        numbers = [
            number
            for number in _allocation_numbers(allocation, _coerce_quantity(allocation.get("quantity")))
            if number
        ]
        if not numbers:
            continue
        product_state = _fetch_product_state(
            product_id,
            product_state_cache,
            config=config,
            request_post=request_post,
        )
        if _apply_allocated_numbers_to_product_state(product_state, numbers):
            product_updates[product_id] = _product_update_from_state(product_state, allocation)
    return product_updates


def _sync_product_updates_with_retry(product_updates, allocation_records, config=None, request_post=None):
    updates = dict(product_updates or {})
    last_error = None
    for attempt in range(3):
        if not updates:
            return 0
        try:
            shopify_sync.sync_limited_edition_metafields_for_products(
                list(updates.values()),
                config=config,
                request_post=request_post,
            )
            return len(updates)
        except shopify_sync.ShopifyAPIError as error:
            last_error = error
            if attempt < 2 and _is_compare_error(error):
                updates = _product_updates_from_allocation_records(
                    allocation_records,
                    config=config,
                    request_post=request_post,
                )
                continue
            raise
    raise last_error


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


def process_shopify_order_for_editions(
    order_payload,
    config=None,
    request_post=None,
    *,
    require_cutover=False,
    cutover_state=None,
):
    config = config or shopify_sync.get_config()
    if not _is_paid_order(order_payload):
        return {"processed": False, "reason": "Order is not paid.", "assignments_created": 0, "issues": []}

    shopify_order_id = _order_identity(order_payload)
    if not shopify_order_id:
        raise shopify_sync.ShopifyAPIError("Order ID is missing from webhook payload.")

    cutover = cutover_state or load_cutover_state()
    started_at = automation_started_at(cutover)
    if require_cutover and not started_at:
        return {
            "processed": False,
            "reason": "Live allocation is not enabled. Set the automation start time first.",
            "assignments_created": 0,
            "issues": [{"order_id": shopify_order_id, "status": "Live allocation not enabled"}],
            "order_id": shopify_order_id,
        }

    if started_at and _is_before_automation_start(order_payload, cutover):
        state = read_order_allocation_state(shopify_order_id, config=config, request_post=request_post)
        existing_payload = state.get("payload") or {}
        return {
            "processed": True,
            "assignments_created": 0,
            "issues": [{"order_id": shopify_order_id, "status": "Historical - Backfill required"}],
            "skipped_existing": _allocated_unit_count(existing_payload),
            "allocation_payload": existing_payload,
            "order_id": shopify_order_id,
            "reason": "Order is before the live allocation cutover.",
        }

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
            updated_products = 0
            if require_cutover and plan["skipped_existing"]:
                updated_products = _sync_product_updates_with_retry(
                    _product_updates_from_allocation_records(
                        (existing_payload.get("line_items") or {}).values(),
                        config=config,
                        request_post=request_post,
                    ),
                    (existing_payload.get("line_items") or {}).values(),
                    config=config,
                    request_post=request_post,
                )
            return {
                "processed": True,
                "assignments_created": 0,
                "issues": plan["issues"],
                "skipped_existing": plan["skipped_existing"],
                "allocation_payload": existing_payload,
                "order_id": shopify_order_id,
                "updated_products": updated_products,
            }

        payload = _sync_order_allocations_with_retry(
            shopify_order_id,
            order_payload,
            new_allocations,
            state,
            config=config,
            request_post=request_post,
        )
        try:
            updated_products = _sync_product_updates_with_retry(
                product_updates,
                new_allocations.values(),
                config=config,
                request_post=request_post,
            )
        except shopify_sync.ShopifyAPIError as error:
            if attempt < 2 and _is_compare_error(error):
                last_compare_error = error
                continue
            raise
        return {
            "processed": True,
            "assignments_created": plan["assignments_created"],
            "issues": plan["issues"],
            "skipped_existing": plan["skipped_existing"],
            "updated_products": updated_products,
            "allocation_payload": payload,
            "order_id": shopify_order_id,
        }

    raise last_compare_error or shopify_sync.ShopifyAPIError("Could not allocate editions after compareDigest retries.")


def process_shopify_orders_for_editions(
    orders,
    config=None,
    request_post=None,
    *,
    require_cutover=False,
    cutover_state=None,
):
    results = []
    errors = []
    assignments_created = 0
    cutover = cutover_state or load_cutover_state()
    for order_payload in sorted(orders or [], key=allocation_order_key):
        try:
            result = process_shopify_order_for_editions(
                order_payload,
                config=config,
                request_post=request_post,
                require_cutover=require_cutover,
                cutover_state=cutover,
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


def _row_unit_index(row):
    try:
        return int(row.get("line_item_unit_index") or int(row.get("edition_offset") or 0) + 1)
    except (TypeError, ValueError):
        return 1


def _row_quantity(row):
    return _coerce_quantity(row.get("line_quantity") or row.get("quantity"))


def _row_allocation_key(row):
    return (
        _parse_datetime(row.get("processed_at") or row.get("processedAt")),
        _parse_datetime(row.get("created_at") or row.get("createdAt")),
        _parse_order_number(row.get("order") or row.get("order_name") or row.get("order_number")),
        str(row.get("shopify_line_item_id") or row.get("line_item_id") or ""),
        _row_unit_index(row),
    )


def _row_order_payload(row):
    return {
        "shopify_order_id": order_gid(row.get("shopify_order_id") or row.get("order_gid")),
        "id": order_gid(row.get("shopify_order_id") or row.get("order_gid")),
        "order_name": row.get("order") or row.get("order_name") or "",
        "name": row.get("order") or row.get("order_name") or "",
        "processed_at": row.get("processed_at") or "",
        "created_at": row.get("created_at") or "",
    }


def _row_line_item(row):
    return {
        "shopify_line_item_id": line_item_gid(row.get("shopify_line_item_id") or row.get("line_item_gid")),
        "id": line_item_gid(row.get("shopify_line_item_id") or row.get("line_item_gid")),
        "shopify_product_id": product_gid(row.get("shopify_product_id") or row.get("product_gid")),
        "product_id": product_gid(row.get("shopify_product_id") or row.get("product_gid")),
        "variant_id": row.get("variant_id") or row.get("variant_gid") or "",
        "product_handle": row.get("product_handle") or row.get("handle") or "",
        "product_title": row.get("product") or row.get("product_title") or "",
        "title": row.get("product") or row.get("product_title") or "",
        "variant_title": row.get("variant") or row.get("variant_title") or "",
        "quantity": _row_quantity(row),
    }


def _existing_unit_number(payload, row):
    line_id = line_item_gid(row.get("shopify_line_item_id") or row.get("line_item_gid"))
    allocation = (parse_allocation_payload(payload).get("line_items") or {}).get(line_id) or {}
    numbers = _allocation_numbers(allocation, _row_quantity(row))
    unit_index = _row_unit_index(row)
    if unit_index <= len(numbers):
        return numbers[unit_index - 1]
    return None


def _row_is_before_automation_start(row, cutover_state):
    started = _automation_started_datetime(cutover_state)
    if not started:
        return False
    return _order_processed_datetime(_row_order_payload(row)) < started


def _historical_candidate_rows(rows, order_states, cutover_state):
    candidates = []
    skipped_existing = 0
    skipped_not_historical = 0
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        if row.get("has_saved_allocation") or _positive_int(row.get("edition_number")):
            skipped_existing += 1
            continue
        if not _row_is_before_automation_start(row, cutover_state):
            skipped_not_historical += 1
            continue
        order_id = order_gid(row.get("shopify_order_id") or row.get("order_gid"))
        line_id = line_item_gid(row.get("shopify_line_item_id") or row.get("line_item_gid"))
        product_id = product_gid(row.get("shopify_product_id") or row.get("product_gid"))
        if not order_id or not line_id or not product_id:
            continue
        state = order_states.get(order_id) or {}
        if _existing_unit_number(state.get("payload") or {}, row):
            skipped_existing += 1
            continue
        candidates.append({**row, "shopify_order_id": order_id, "shopify_line_item_id": line_id, "shopify_product_id": product_id})
    return candidates, skipped_existing, skipped_not_historical


def historical_backfill_order_rows(rows, config=None, request_post=None, cutover_state=None):
    config = config or shopify_sync.get_config()
    cutover = cutover_state or load_cutover_state()
    baselines = cutover.get("baselines") or {}
    if not _automation_started_datetime(cutover):
        return {
            "assignments_created": 0,
            "skipped_existing": 0,
            "skipped_not_historical": 0,
            "errors": [{"status": "Missing automation start"}],
            "order_payloads": {},
            "assigned_rows": [],
        }
    order_ids = sorted(
        {
            order_gid(row.get("shopify_order_id") or row.get("order_gid"))
            for row in rows or []
            if isinstance(row, dict) and (row.get("shopify_order_id") or row.get("order_gid"))
        }
    )
    order_states = {
        order_id: read_order_allocation_state(order_id, config=config, request_post=request_post)
        for order_id in order_ids
    }
    candidates, skipped_existing, skipped_not_historical = _historical_candidate_rows(rows, order_states, cutover)
    by_product = {}
    for row in candidates:
        by_product.setdefault(product_gid(row.get("shopify_product_id") or row.get("product_gid")), []).append(row)

    assignments = []
    errors = []
    for product_id, product_rows in sorted(by_product.items()):
        baseline = baselines.get(product_id) or {}
        baseline_next = _positive_int(baseline.get("baseline_next_number"))
        if not baseline_next:
            errors.append({"product_id": product_id, "status": "Missing baseline"})
            continue
        sorted_rows = sorted(product_rows, key=_row_allocation_key)
        start_number = baseline_next - len(sorted_rows)
        if start_number < 1:
            errors.append({"product_id": product_id, "status": "Baseline does not have enough historical numbers"})
            continue
        for offset, row in enumerate(sorted_rows):
            assignments.append(
                {
                    "row": row,
                    "edition_number": start_number + offset,
                    "baseline_next_number": baseline_next,
                }
            )

    by_order = {}
    for assignment in assignments:
        row = assignment["row"]
        by_order.setdefault(order_gid(row.get("shopify_order_id")), []).append(assignment)

    synced_payloads = {}
    created = 0
    for order_id, order_assignments in sorted(by_order.items()):
        state = order_states.get(order_id) or read_order_allocation_state(order_id, config=config, request_post=request_post)
        new_allocations = {}
        order_payload = _row_order_payload(order_assignments[0]["row"])
        for assignment in order_assignments:
            row = assignment["row"]
            if _existing_unit_number(state.get("payload") or {}, row):
                skipped_existing += 1
                continue
            line_item = _row_line_item(row)
            quantity = _row_quantity(row)
            numbers = [None] * quantity
            unit_index = _row_unit_index(row)
            while len(numbers) < unit_index:
                numbers.append(None)
            numbers[unit_index - 1] = assignment["edition_number"]
            line_id = _line_identity(line_item)
            incoming = _allocation_record(
                order_payload,
                line_item,
                _line_product_gid(line_item),
                numbers,
                row.get("edition_total") or 100,
                status="Historical Backfill",
            )
            new_allocations[line_id] = _merge_line_allocation(new_allocations.get(line_id) or {}, incoming)
        if not new_allocations:
            continue
        payload = _sync_order_allocations_with_retry(
            order_id,
            order_payload,
            new_allocations,
            state,
            config=config,
            request_post=request_post,
        )
        synced_payloads[order_id] = payload
        created += sum(
            1
            for allocation in new_allocations.values()
            for number in allocation.get("edition_numbers") or []
            if number
        )

    return {
        "assignments_created": created,
        "skipped_existing": skipped_existing,
        "skipped_not_historical": skipped_not_historical,
        "errors": errors,
        "order_payloads": synced_payloads,
        "assigned_rows": [
            {
                **assignment["row"],
                "edition_number": assignment["edition_number"],
                "edition_display": f"#{assignment['edition_number']:03d}",
            }
            for assignment in assignments
            if order_gid(assignment["row"].get("shopify_order_id")) in synced_payloads
        ],
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
