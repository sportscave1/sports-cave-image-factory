from datetime import datetime, timezone
import importlib
import json
import os
from pathlib import Path
import re
import time

import shopify_sync


BASE_DIR = Path(__file__).resolve().parent
SNAPSHOT_PATH = BASE_DIR / "output" / "_cache" / "orders_allocation_snapshot.json"
CUTOVER_PATH = BASE_DIR / "output" / "_cache" / "limited_edition_cutover.json"
SNAPSHOT_VERSION = 1
CUTOVER_VERSION = 1
AUTOMATION_STARTED_ENV = "LIMITED_EDITION_AUTOMATION_STARTED_AT"
DATETIME_MIN_UTC = datetime.min.replace(tzinfo=timezone.utc)


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _safe_iso(value):
    parsed = normalize_datetime_utc(value)
    if parsed == DATETIME_MIN_UTC:
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


def normalize_datetime_utc(value):
    if not value:
        return DATETIME_MIN_UTC
    if isinstance(value, datetime):
        parsed = value
    else:
        raw = str(value or "").strip()
        if not raw:
            return DATETIME_MIN_UTC
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return DATETIME_MIN_UTC
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_datetime(value):
    return normalize_datetime_utc(value)


def is_missing_datetime(value):
    try:
        return normalize_datetime_utc(value) == DATETIME_MIN_UTC
    except Exception:
        return True


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
    if processed != DATETIME_MIN_UTC:
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
        "active": False,
        "allocation_enabled": True,
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
    state["active"] = bool(state.get("active") or state.get("automation_started_at"))
    state["allocation_enabled"] = bool(state.get("allocation_enabled", True))
    return state


def save_cutover_state(state):
    payload = _empty_cutover_state()
    payload.update(state or {})
    for key in list(payload):
        if str(key).startswith("_"):
            payload.pop(key, None)
    payload["version"] = CUTOVER_VERSION
    payload["automation_started_at"] = _safe_iso(payload.get("automation_started_at")) or ""
    payload["baselines"] = payload.get("baselines") or {}
    payload["allocation_enabled"] = bool(payload.get("allocation_enabled", True))
    payload["active"] = bool(payload.get("active") or payload.get("automation_started_at"))
    payload["updated_at"] = now_iso()
    CUTOVER_PATH.parent.mkdir(parents=True, exist_ok=True)
    CUTOVER_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def enable_live_allocation_from_now(started_at=None):
    state = load_cutover_state()
    state["automation_started_at"] = _safe_iso(started_at or now_iso())
    state["active"] = True
    state["allocation_enabled"] = True
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


def _baselines_from_product_rows(product_rows, captured_at):
    baselines = {}
    count = 0
    for row in product_rows or []:
        if not isinstance(row, dict):
            continue
        baseline = _baseline_from_product_row(row, captured_at)
        if not baseline:
            continue
        baselines[baseline["product_gid"]] = baseline
        count += 1
    return baselines, count


def capture_product_baselines(product_rows, captured_at=None):
    captured = _safe_iso(captured_at or now_iso())
    state = load_cutover_state()
    baselines, count = _baselines_from_product_rows(product_rows, captured)
    state["baselines"] = baselines
    state.setdefault("automation_started_at", "")
    state["baseline_captured_at"] = captured
    saved = save_cutover_state(state)
    saved["captured_count"] = count
    return saved


def activate_live_allocation(product_rows, started_at=None):
    captured = _safe_iso(started_at or now_iso())
    baselines, count = _baselines_from_product_rows(product_rows, captured)
    state = load_cutover_state()
    state["active"] = True
    state["allocation_enabled"] = True
    state["automation_started_at"] = captured
    state["baseline_captured_at"] = captured
    state["baselines"] = baselines
    saved = save_cutover_state(state)
    saved["captured_count"] = count
    return saved


def automation_started_at(cutover_state=None):
    state = cutover_state or load_cutover_state()
    started_at = _safe_iso((state or {}).get("automation_started_at") or os.getenv(AUTOMATION_STARTED_ENV, ""))
    return started_at


def live_allocation_active(cutover_state=None):
    state = cutover_state or load_cutover_state()
    return bool((state or {}).get("allocation_enabled", True) and (state or {}).get("active") and automation_started_at(state))


def ensure_allocation_settings(cutover_state=None, started_at=None):
    state = cutover_state if isinstance(cutover_state, dict) else load_cutover_state()
    auto_created = False
    if not automation_started_at(state):
        state["active"] = True
        state["allocation_enabled"] = True
        state["automation_started_at"] = _safe_iso(started_at or now_iso())
        state.setdefault("baselines", {})
        state = save_cutover_state(state)
        auto_created = True
    else:
        state["active"] = True
        state["allocation_enabled"] = bool(state.get("allocation_enabled", True))
    state["_auto_created"] = bool(auto_created or state.get("_auto_created"))
    if isinstance(cutover_state, dict):
        cutover_state.update(state)
    return state


def _automation_started_datetime(cutover_state=None):
    started_at = automation_started_at(cutover_state)
    if not started_at:
        return None
    parsed = _parse_datetime(started_at)
    if parsed == DATETIME_MIN_UTC:
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


def _baseline_from_product_state(product_state, line_item, captured_at):
    return {
        "product_gid": product_state["product_id"],
        "shopify_handle": _line_product_handle(line_item),
        "product_title": _line_product_title(line_item),
        "baseline_next_number": int(product_state.get("next_number") or 1),
        "baseline_sold_count": int(product_state.get("sold_count") or 0),
        "baseline_remaining": int(product_state.get("remaining") or 0),
        "baseline_total": int(product_state.get("edition_total") or 100),
        "baseline_captured_at": captured_at,
    }


def _ensure_product_baseline(cutover_state, product_state, line_item):
    if not isinstance(cutover_state, dict):
        return
    product_id = product_state.get("product_id")
    if not product_id:
        return
    baselines = dict(cutover_state.get("baselines") or {})
    if product_id in baselines:
        return
    captured_at = now_iso()
    baselines[product_id] = _baseline_from_product_state(product_state, line_item, captured_at)
    cutover_state["baselines"] = baselines
    cutover_state["baseline_captured_at"] = cutover_state.get("baseline_captured_at") or captured_at
    saved = save_cutover_state(cutover_state)
    cutover_state.update(saved)


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
            result = shopify_sync.sync_limited_edition_metafields_for_products(
                list(updates.values()),
                config=config,
                request_post=request_post,
            )
            if isinstance(result, dict) and int(result.get("failed") or 0):
                error_text = shopify_sync._limited_edition_sync_error_text(result.get("results") or [])
                raise shopify_sync.ShopifyAPIError(f"Shopify metafield sync failed: {error_text}")
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


def _product_metafield_sync_failure(error, order_id):
    message = f"Shopify metafield sync failed: {error}"
    print(
        json.dumps(
            {
                "event": "shopify_product_metafield_sync_failed",
                "order_id": order_id,
                "error": str(error),
            }
        ),
        flush=True,
    )
    return message


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


def _fetch_limited_edition_product_by_handle(handle, config=None, request_post=None):
    handle = str(handle or "").strip()
    if not handle:
        return None
    page = shopify_sync.fetch_limited_edition_products_page(
        search=f"handle:{handle}",
        page_size=10,
        config=config,
        request_post=request_post,
    )
    for product in page.get("products") or []:
        if str(product.get("handle") or "").strip().casefold() == handle.casefold():
            return product
    return None


def _fetch_product_state_for_line(line_item, product_state_cache, config=None, request_post=None):
    product_id = _line_product_gid(line_item)
    handle = _line_product_handle(line_item)
    if product_id:
        try:
            return _fetch_product_state(
                product_id,
                product_state_cache,
                config=config,
                request_post=request_post,
            )
        except shopify_sync.ShopifyAPIError:
            if not handle:
                raise

    if not handle:
        return None

    cache_key = f"handle:{handle.casefold()}"
    if cache_key not in product_state_cache:
        product = _fetch_limited_edition_product_by_handle(
            handle,
            config=config,
            request_post=request_post,
        )
        if not product or not product.get("shopify_product_id"):
            product_state_cache[cache_key] = None
        else:
            state = _product_state_from_metafields(product["shopify_product_id"], product.get("metafields") or [])
            state["product_status"] = product.get("status") or ""
            product_state_cache[cache_key] = state
            product_state_cache[state["product_id"]] = state
    return product_state_cache.get(cache_key)


def _sorted_line_items(order_payload):
    return [
        line_item
        for fallback, line_item in sorted(
            enumerate(_line_items(order_payload), start=1),
            key=lambda item: (_line_position(item[1], item[0]), item[0]),
        )
    ]


def _plan_order_allocations(order_payload, existing_payload, product_state_cache, config=None, request_post=None, cutover_state=None):
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
        if not product_id and not _line_product_handle(line_item):
            issues.append({"line_item_id": line_id, "status": "Missing Shopify ID"})
            continue

        product_state = None
        for unit_index in range(1, quantity + 1):
            if unit_index <= len(existing_numbers) and existing_numbers[unit_index - 1]:
                skipped_existing += 1
                continue
            if product_state is None:
                product_state = _fetch_product_state_for_line(
                    line_item,
                    product_state_cache,
                    config=config,
                    request_post=request_post,
                )
                if not product_state:
                    issues.append({"line_item_id": line_id, "status": "Product not matched"})
                    line_status = line_status or "Product not matched"
                    continue
                _ensure_product_baseline(cutover_state, product_state, line_item)
                product_id = product_state.get("product_id") or product_id
            if str(product_state.get("product_status") or "").strip().upper() not in {"", "ACTIVE"}:
                issues.append({"line_item_id": line_id, "product_id": product_id, "status": "Product inactive"})
                line_status = line_status or "Product inactive"
                continue
            if not product_state.get("edition_enabled"):
                issues.append({"line_item_id": line_id, "product_id": product_id, "status": "Edition Disabled"})
                line_status = line_status or "Edition disabled"
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
    if require_cutover:
        cutover = ensure_allocation_settings(cutover)
    started_at = automation_started_at(cutover)
    if require_cutover and not started_at:
        return {
            "processed": False,
            "reason": "Live allocation is not enabled. Set the automation start time first.",
            "assignments_created": 0,
            "issues": [{"order_id": shopify_order_id, "status": "Live allocation not enabled"}],
            "order_id": shopify_order_id,
        }

    if started_at and not cutover.get("_auto_created") and _is_before_automation_start(order_payload, cutover):
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
            cutover_state=cutover if require_cutover else None,
        )
        new_allocations = plan["new_allocations"]
        product_updates = plan["product_updates"]

        if not new_allocations:
            updated_products = 0
            sync_errors = []
            if require_cutover and plan["skipped_existing"]:
                try:
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
                except shopify_sync.ShopifyAPIError as error:
                    sync_errors.append(_product_metafield_sync_failure(error, shopify_order_id))
            return {
                "processed": True,
                "assignments_created": 0,
                "issues": [*plan["issues"], *({"status": message} for message in sync_errors)],
                "skipped_existing": plan["skipped_existing"],
                "allocation_payload": existing_payload,
                "order_id": shopify_order_id,
                "updated_products": updated_products,
                "product_metafield_sync_error": sync_errors[0] if sync_errors else "",
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
            sync_error = _product_metafield_sync_failure(error, shopify_order_id)
            return {
                "processed": True,
                "assignments_created": plan["assignments_created"],
                "issues": [*plan["issues"], {"order_id": shopify_order_id, "status": sync_error}],
                "skipped_existing": plan["skipped_existing"],
                "updated_products": 0,
                "allocation_payload": payload,
                "order_id": shopify_order_id,
                "product_metafield_sync_error": sync_error,
            }
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
    if require_cutover:
        cutover = ensure_allocation_settings(cutover)
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


def process_recent_paid_orders_for_editions(orders, config=None, request_post=None):
    return process_shopify_orders_for_editions(
        orders,
        config=config,
        request_post=request_post,
        require_cutover=True,
    )


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


def _as_dict(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _raw_line_for_id(order_raw, line_item_id):
    raw_line_id = str(line_item_id or "").strip()
    for line in (_as_dict(order_raw).get("line_items") or []):
        if not isinstance(line, dict):
            continue
        candidate = str(
            line.get("shopify_line_item_id")
            or line.get("admin_graphql_api_id")
            or line.get("id")
            or ""
        ).strip()
        if candidate == raw_line_id or line_item_gid(candidate) == raw_line_id:
            return line
    return {}


def _shipping_method_from_raw(order_raw):
    payload = _as_dict(order_raw)
    shipping = (
        payload.get("shipping_method")
        or payload.get("shippingMethod")
        or payload.get("shipping_title")
        or payload.get("shippingTitle")
        or ""
    )
    if shipping:
        return str(shipping)
    shipping_lines = payload.get("shipping_lines") or payload.get("shippingLines") or []
    if isinstance(shipping_lines, dict):
        shipping_lines = shipping_lines.get("nodes") or []
    first = shipping_lines[0] if shipping_lines and isinstance(shipping_lines[0], dict) else {}
    return str(first.get("title") or first.get("code") or "")


def _shipping_summary_from_raw(order_raw):
    payload = _as_dict(order_raw)
    shipping_method = _shipping_method_from_raw(payload)
    shipping_address = payload.get("shipping_address") or payload.get("shippingAddress") or {}
    if not isinstance(shipping_address, dict):
        shipping_address = {}
    name = str(
        shipping_address.get("name")
        or " ".join(
            part
            for part in (
                shipping_address.get("first_name"),
                shipping_address.get("last_name"),
            )
            if part
        ).strip()
        or ""
    ).strip()
    location_parts = [
        str(shipping_address.get("city") or "").strip(),
        str(shipping_address.get("province") or shipping_address.get("province_code") or "").strip(),
        str(shipping_address.get("zip") or shipping_address.get("postal_code") or "").strip(),
        str(shipping_address.get("country") or shipping_address.get("country_code") or "").strip(),
    ]
    location = ", ".join(part for part in location_parts if part)
    summary_parts = [part for part in (shipping_method, name, location) if part]
    return " | ".join(summary_parts)


def _date_label(value):
    parsed = normalize_datetime_utc(value)
    if parsed == DATETIME_MIN_UTC:
        return ""
    return parsed.date().isoformat()


def _assignment_list(value):
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return []
        return _assignment_list(parsed)
    return []


def _certificate_status_from_assignment(assignment):
    status = str((assignment or {}).get("certificate_status") or "").strip()
    if status and status != "Certificate Missing":
        return status
    return ""


def _snapshot_rows_from_supabase_order_rows(raw_rows):
    rows = []
    for raw in raw_rows or []:
        row = dict(raw or {})
        order_raw = _as_dict(row.get("order_raw_json"))
        line_id = str(row.get("shopify_line_item_id") or "").strip()
        line_raw = _raw_line_for_id(order_raw, line_id)
        quantity = _coerce_quantity(row.get("quantity") or line_raw.get("quantity") or 1)
        order_name = str(row.get("order_name") or row.get("shopify_order_name") or "")
        processed_at = _safe_iso(row.get("processed_at") or order_raw.get("processed_at") or order_raw.get("processedAt"))
        created_at = _safe_iso(row.get("created_at") or order_raw.get("created_at") or order_raw.get("createdAt"))
        date_value = _date_label(processed_at or created_at)
        shipping = _shipping_summary_from_raw(order_raw) or _shipping_method_from_raw(order_raw)
        shipping_method = _shipping_method_from_raw(order_raw)
        product_title = str(row.get("product_title") or line_raw.get("product_title") or line_raw.get("title") or "")
        variant_title = str(row.get("variant_title") or line_raw.get("variant_title") or line_raw.get("variantTitle") or "")
        product_handle = str(row.get("shopify_handle") or line_raw.get("product_handle") or line_raw.get("handle") or "")
        product_id = str(row.get("shopify_product_id") or line_raw.get("shopify_product_id") or line_raw.get("product_id") or "")
        variant_id = str(
            row.get("shopify_variant_id")
            or line_raw.get("shopify_variant_id")
            or line_raw.get("variant_id")
            or ""
        )
        base = {
            "order": order_name,
            "date": date_value,
            "customer": str(row.get("customer_name") or order_raw.get("customer_name") or ""),
            "customer_email": str(row.get("customer_email") or order_raw.get("customer_email") or order_raw.get("email") or ""),
            "shipping": shipping,
            "shipping_method": shipping_method,
            "product": product_title,
            "variant": variant_title,
            "admin_url": str(row.get("admin_url") or ""),
            "prodigi_status": str(row.get("prodigi_status") or ""),
            "prodigi_row_id": str(row.get("prodigi_row_id") or ""),
            "line_quantity": quantity,
            "shopify_order_id": str(row.get("shopify_order_id") or ""),
            "legacy_resource_id": str(order_raw.get("legacy_resource_id") or ""),
            "shopify_line_item_id": line_id,
            "shopify_product_id": product_id,
            "variant_id": variant_id,
            "product_handle": product_handle,
            "shopify_customer_id": str(row.get("shopify_customer_id") or order_raw.get("shopify_customer_id") or order_raw.get("customer_id") or ""),
            "processed_at": processed_at,
            "created_at": created_at,
            "order_number_sort": _parse_order_number(order_name or row.get("order_number")),
        }
        assignments = _assignment_list(row.get("assignments"))
        if assignments:
            for assignment in assignments:
                edition_number = _positive_int(assignment.get("edition_number"))
                if not edition_number:
                    continue
                allocation_index = _positive_int(assignment.get("allocation_index"), 1)
                certificate_url = str(assignment.get("shopify_file_url") or "")
                certificate_path = str(assignment.get("local_file_path") or "")
                rows.append(
                    {
                        **base,
                        "edition_order_id": str(assignment.get("edition_order_id") or ""),
                        "edition_number": edition_number,
                        "edition": f"#{edition_number:03d}",
                        "edition_total": _positive_int(assignment.get("edition_total"), 100),
                        "has_saved_allocation": True,
                        "edition_offset": max(allocation_index - 1, 0),
                        "allocation_index": allocation_index,
                        "assignment_status": str(assignment.get("assignment_status") or "Assigned"),
                        "certificate_id": str(assignment.get("certificate_id") or ""),
                        "certificate_status": _certificate_status_from_assignment(assignment),
                        "certificate_pdf_path": certificate_path,
                        "certificate_pdf_url": certificate_url,
                        "shopify_file_url": certificate_url,
                        "certificate_shopify_file_id": str(assignment.get("shopify_file_id") or ""),
                        "certificate_generated_at": _safe_iso(assignment.get("generated_at") or assignment.get("assigned_at")),
                        "certificate_preview_path": str(assignment.get("certificate_preview_r2_key") or ""),
                    }
                )
            continue

        status = str(row.get("assignment_status") or "").strip()
        blocker = ""
        if status in {"Product Not Found"}:
            blocker = "Product not matched"
        elif status in {"Needs Edition Setup"}:
            blocker = "Edition disabled"
        elif status in {"Sold Out"}:
            blocker = "Needs Review - Sold Out"
        elif status in {"Error"}:
            blocker = "Allocation error"
        elif status == "Historical Order":
            blocker = "Historical backfill required"
        else:
            blocker = "Needs allocation"
        for index in range(quantity):
            rows.append(
                {
                    **base,
                    "edition_order_id": "",
                    "edition_number": None,
                    "edition": blocker,
                    "edition_total": 100,
                    "has_saved_allocation": False,
                    "edition_offset": index,
                    "allocation_index": index + 1,
                    "assignment_status": status or "Needs Edition",
                    "certificate_status": blocker,
                    "certificate_error": str(row.get("last_error") or ""),
                }
            )
    return sorted(rows, key=_row_allocation_key, reverse=True)


def load_supabase_orders_snapshot(limit=1000, *, include_summary=True):
    backend = _configured_supabase_backend()
    if not backend:
        return None
    raw_rows = backend.list_orders(search="", sort="Date newest", status_filter="All", limit=max(int(limit or 1000), 1))
    sync_state = backend.get_sync_state()
    summary = {}
    if include_summary:
        try:
            summary = backend.get_order_summary()
        except Exception:
            summary = {}
    last_synced = (
        sync_state.get("last_successful_order_fetch_at")
        or sync_state.get("last_successful_order_sync_at")
        or ""
    )
    rows = _snapshot_rows_from_supabase_order_rows(raw_rows)
    order_count = int(summary.get("orders_synced") or 0)
    if not order_count:
        order_count = len({str(row.get("shopify_order_id") or "") for row in raw_rows if row.get("shopify_order_id")})
    return {
        "version": SNAPSHOT_VERSION,
        "saved_at": now_iso(),
        "last_refreshed": last_synced,
        "last_synced": last_synced,
        "source": "supabase",
        "order_count": order_count,
        "row_count": len(rows),
        "rows": rows,
    }


def load_hybrid_orders_snapshot(limit=50, search=""):
    backend = _configured_supabase_backend()
    if not backend:
        return None
    started = time.perf_counter()
    raw_rows = backend.list_hybrid_order_rows(
        limit=max(int(limit or 50), 1),
        search=str(search or "").strip(),
    )
    list_elapsed = time.perf_counter() - started
    convert_started = time.perf_counter()
    rows = _snapshot_rows_from_supabase_order_rows(raw_rows)
    print(f"PERF Orders row conversion {time.perf_counter() - convert_started:.3f}s rows={len(rows)}", flush=True)
    last_synced = max(
        (_safe_iso(row.get("synced_at")) for row in raw_rows if row.get("synced_at")),
        default="",
    )
    order_count = len({str(row.get("shopify_order_id") or "") for row in raw_rows if row.get("shopify_order_id")})
    read_diagnostic = (
        backend.get_last_database_read_diagnostic()
        if hasattr(backend, "get_last_database_read_diagnostic")
        else {}
    )
    return {
        "version": SNAPSHOT_VERSION,
        "saved_at": now_iso(),
        "last_refreshed": last_synced,
        "last_synced": last_synced,
        "source": "shopify_mirror_supabase_edition_ledger",
        "order_count": order_count,
        "row_count": len(rows),
        "rows": rows,
        "search": str(search or "").strip(),
        "database_read": read_diagnostic,
        "timing": {
            "base_overlay_seconds": round(list_elapsed, 3),
        },
    }


def sync_new_orders_to_persistent_cache(config=None, *, max_orders=100, sync_product_metafields=True):
    backend = _configured_supabase_backend()
    if not backend:
        return {"source": "local_snapshot", "skipped": True, "reason": "Supabase is not configured."}
    return {
        "source": "supabase",
        **backend.sync_shopify_orders_to_supabase(
            config=config,
            max_orders=max_orders,
            generate_certificates=False,
            sync_product_metafields=sync_product_metafields,
        ),
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
    try:
        supabase_payload = load_supabase_orders_snapshot()
    except Exception as error:
        print(f"WARN Orders Supabase snapshot fallback: {error}", flush=True)
        supabase_payload = None
    if supabase_payload is not None:
        return supabase_payload
    return load_local_orders_snapshot()


def load_local_orders_snapshot():
    """Read only the saved display cache without attempting another backend call."""
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


def _snapshot_row_unit_index(row):
    try:
        return int(row.get("line_item_unit_index") or int(row.get("edition_offset") or 0) + 1)
    except (TypeError, ValueError):
        return 1


def _snapshot_row_quantity(row):
    try:
        return max(int(row.get("line_quantity") or row.get("quantity") or 1), _snapshot_row_unit_index(row), 1)
    except (TypeError, ValueError):
        return max(_snapshot_row_unit_index(row), 1)


def snapshot_override_row_id(row):
    return "snapshot|" + "|".join(
        [
            order_gid(row.get("shopify_order_id") or row.get("order_gid")),
            line_item_gid(row.get("shopify_line_item_id") or row.get("line_item_gid")),
            str(_snapshot_row_unit_index(row)),
            product_gid(row.get("shopify_product_id") or row.get("product_gid")),
        ]
    )


def _snapshot_edition_number(row):
    return _positive_int(row.get("edition_number") or row.get("edition") or row.get("assigned_edition_number"))


def _snapshot_certificate_status(row):
    status = str(row.get("certificate_status") or "").strip()
    label = str(row.get("certificate") or "").strip()
    if status:
        return status
    if label:
        return f"Certificate {label}" if label == "Generate" else label
    return "Certificate Generate"


def _snapshot_row_to_override_record(row):
    edition_number = _snapshot_edition_number(row)
    if not edition_number:
        return {}
    return {
        "id": snapshot_override_row_id(row),
        "source": "snapshot_allocation",
        "shopify_order_id": order_gid(row.get("shopify_order_id") or row.get("order_gid")),
        "shopify_order_name": row.get("order") or row.get("order_name") or "",
        "order_name": row.get("order") or row.get("order_name") or "",
        "shopify_line_item_id": line_item_gid(row.get("shopify_line_item_id") or row.get("line_item_gid")),
        "shopify_product_id": product_gid(row.get("shopify_product_id") or row.get("product_gid")),
        "shopify_variant_id": row.get("variant_id") or row.get("variant_gid") or "",
        "shopify_handle": row.get("product_handle") or row.get("handle") or "",
        "product_handle": row.get("product_handle") or row.get("handle") or "",
        "product_title": row.get("product") or row.get("product_title") or "",
        "variant_title": row.get("variant") or row.get("variant_title") or "",
        "customer_name": row.get("customer") or row.get("customer_name") or "",
        "customer_email": row.get("customer_email") or "",
        "edition_number": edition_number,
        "edition_total": int(row.get("edition_total") or 100),
        "allocation_index": _snapshot_row_unit_index(row),
        "quantity": _snapshot_row_quantity(row),
        "certificate_status": _snapshot_certificate_status(row),
        "certificate_pdf_url": row.get("certificate_pdf_url") or "",
        "certificate_pdf_path": row.get("certificate_pdf_path") or "",
        "shopify_file_id": row.get("certificate_shopify_file_id") or "",
        "created_at": row.get("created_at") or "",
        "processed_at": row.get("processed_at") or "",
        "_snapshot_row": dict(row),
    }


def _snapshot_search_matches(record, search):
    raw = str(search or "").strip()
    if not raw:
        return True
    haystack = " ".join(
        str(record.get(key) or "")
        for key in (
            "id",
            "shopify_order_name",
            "order_name",
            "shopify_order_id",
            "customer_name",
            "customer_email",
            "product_title",
            "variant_title",
            "shopify_line_item_id",
            "shopify_handle",
            "product_handle",
        )
    ).casefold()
    terms = {raw.casefold()}
    if raw.startswith("#"):
        terms.add(raw[1:].casefold())
    else:
        terms.add(f"#{raw}".casefold())
    if any(term and term in haystack for term in terms):
        return True
    edition_match = re.fullmatch(r"#?0*(\d+)", raw)
    return bool(edition_match and int(edition_match.group(1)) == int(record.get("edition_number") or 0))


def snapshot_allocated_order_rows(search="", limit=50):
    payload = load_orders_snapshot()
    records = []
    seen = set()
    for row in payload.get("rows") or []:
        record = _snapshot_row_to_override_record(row)
        if not record or not _snapshot_search_matches(record, search):
            continue
        record_id = record.get("id")
        if record_id in seen:
            continue
        seen.add(record_id)
        records.append(record)
    records.sort(
        key=lambda row: (
            _parse_datetime(row.get("processed_at")),
            _parse_datetime(row.get("created_at")),
            _parse_order_number(row.get("shopify_order_name") or row.get("order_name")),
        ),
        reverse=True,
    )
    return records[: max(int(limit or 50), 1)]


def _snapshot_same_product(left, right):
    left_product_id = product_gid(left.get("shopify_product_id") or left.get("product_gid"))
    right_product_id = product_gid(right.get("shopify_product_id") or right.get("product_gid"))
    if left_product_id and right_product_id:
        return left_product_id == right_product_id
    left_handle = str(left.get("product_handle") or left.get("shopify_handle") or left.get("handle") or "").casefold()
    right_handle = str(right.get("product_handle") or right.get("shopify_handle") or right.get("handle") or "").casefold()
    return bool(left_handle and right_handle and left_handle == right_handle)


def _snapshot_row_matches_identity(row, selected):
    return (
        order_gid(row.get("shopify_order_id") or row.get("order_gid")) == order_gid(selected.get("shopify_order_id"))
        and line_item_gid(row.get("shopify_line_item_id") or row.get("line_item_gid")) == line_item_gid(selected.get("shopify_line_item_id"))
        and _snapshot_row_unit_index(row) == int(selected.get("allocation_index") or selected.get("line_item_unit_index") or 1)
    )


def _snapshot_line_numbers(rows, selected, replacement_number):
    quantity = _snapshot_row_quantity(selected)
    numbers = [None] * quantity
    for row in rows:
        if (
            order_gid(row.get("shopify_order_id") or row.get("order_gid")) != order_gid(selected.get("shopify_order_id"))
            or line_item_gid(row.get("shopify_line_item_id") or row.get("line_item_gid")) != line_item_gid(selected.get("shopify_line_item_id"))
        ):
            continue
        unit_index = _snapshot_row_unit_index(row)
        while len(numbers) < unit_index:
            numbers.append(None)
        numbers[unit_index - 1] = _positive_int(row.get("edition_number") or row.get("edition"))
    selected_index = int(selected.get("allocation_index") or selected.get("line_item_unit_index") or 1)
    while len(numbers) < selected_index:
        numbers.append(None)
    numbers[selected_index - 1] = int(replacement_number)
    return numbers


def _snapshot_product_state(rows, selected):
    edition_total = int(selected.get("edition_total") or 100)
    max_assigned = 0
    for row in rows:
        if not _snapshot_same_product(row, selected):
            continue
        number = _positive_int(row.get("edition_number") or row.get("edition"))
        if number:
            max_assigned = max(max_assigned, number)
    next_number = max_assigned + 1
    sold_out = next_number > edition_total
    if sold_out:
        next_number = edition_total
    remaining = max(edition_total - (next_number - 1), 0)
    return {
        "shopify_product_id": product_gid(selected.get("shopify_product_id")),
        "shopify_handle": selected.get("shopify_handle") or selected.get("product_handle") or "",
        "product_title": selected.get("product_title") or selected.get("product") or "",
        "edition_total": edition_total,
        "max_assigned": max_assigned,
        "next_edition_number": next_number,
        "remaining_count": remaining,
        "sold_out": sold_out,
    }


def _sync_snapshot_product_metafields(product_state, config=None, request_post=None):
    product_id = product_state.get("shopify_product_id")
    if not product_id:
        return {"ok": False, "warning": "Shopify product ID is missing; product metafields were not synced."}
    result = shopify_sync.sync_limited_edition_metafields_for_products(
        [
            {
                "shopify_product_id": product_id,
                "handle": product_state.get("shopify_handle") or "",
                "title": product_state.get("product_title") or product_state.get("shopify_handle") or "",
                "edition_enabled": True,
                "edition_total": product_state.get("edition_total"),
                "edition_next_number": product_state.get("next_edition_number"),
                "edition_sold_count": product_state.get("max_assigned"),
                "edition_remaining": product_state.get("remaining_count"),
                "edition_status": shopify_sync.calculate_limited_edition_status(product_state.get("remaining_count")),
            }
        ],
        config=config,
        request_post=request_post,
        raise_on_failure=True,
    )
    return {"ok": True, **result}


def override_snapshot_allocation_row(selected_row, new_edition_number, *, reason="", config=None, sync_shopify=True, request_post=None):
    selected = dict(selected_row or {})
    new_number = _positive_int(new_edition_number)
    if not new_number:
        raise ValueError("New edition number must be at least 1.")
    edition_total = int(selected.get("edition_total") or 100)
    if new_number > edition_total:
        raise ValueError(f"Edition number must be between 1 and {edition_total}.")

    payload = load_orders_snapshot()
    rows = [dict(row or {}) for row in payload.get("rows") or []]
    target_index = None
    for index, row in enumerate(rows):
        if _snapshot_row_matches_identity(row, selected):
            target_index = index
            break
    if target_index is None:
        raise ValueError("Snapshot allocation row was not found.")

    for row in rows:
        if _snapshot_row_matches_identity(row, selected):
            continue
        if not _snapshot_same_product(row, selected):
            continue
        if _positive_int(row.get("edition_number") or row.get("edition")) == new_number:
            order_label = row.get("order") or row.get("order_name") or row.get("shopify_order_id") or "another order"
            raise ValueError(f"Edition #{new_number:03d} is already used by {order_label} for this product.")

    old_number = _positive_int(rows[target_index].get("edition_number") or rows[target_index].get("edition"))
    certificate_uploaded = bool(
        rows[target_index].get("certificate_pdf_url")
        or rows[target_index].get("certificate_shopify_file_id")
        or str(rows[target_index].get("certificate") or "").strip() == "Uploaded"
    )
    certificate_status = "Needs regeneration" if certificate_uploaded else (rows[target_index].get("certificate_status") or "")
    rows[target_index].update(
        {
            "edition_number": new_number,
            "edition": f"#{new_number:03d}",
            "has_saved_allocation": True,
            "certificate_status": certificate_status,
            "certificate": "Needs regeneration" if certificate_uploaded else rows[target_index].get("certificate") or "Generate",
            "manual_override": True,
            "override_old_edition_number": old_number,
            "override_new_edition_number": new_number,
            "override_timestamp": now_iso(),
            "override_reason": reason or "Manual edition override",
        }
    )
    if certificate_uploaded:
        rows[target_index].update(
            {
                "certificate_pdf_url": "",
                "certificate_pdf_path": "",
                "certificate_shopify_file_id": "",
                "certificate_file_url": "",
                "shopify_file_status": "STALE",
            }
        )
    product_state = _snapshot_product_state(rows, {**selected, "edition_number": new_number})
    saved = save_orders_snapshot(rows, meta={"last_refreshed": payload.get("last_refreshed") or ""})

    shopify_results = {}
    warning = ""
    if sync_shopify:
        config = config or shopify_sync.get_config()
        try:
            state = read_order_allocation_state(selected.get("shopify_order_id"), config=config, request_post=request_post)
            allocation_payload = parse_allocation_payload(state.get("payload") or {})
            allocation_payload.update(
                {
                    "version": SNAPSHOT_VERSION,
                    "source": "sports_cave_os_manual_override",
                    "order_id": order_gid(selected.get("shopify_order_id")),
                    "order_name": selected.get("shopify_order_name") or selected.get("order_name") or "",
                    "updated_at": now_iso(),
                }
            )
            line_id = line_item_gid(selected.get("shopify_line_item_id"))
            line_items = dict(allocation_payload.get("line_items") or {})
            allocation = dict(line_items.get(line_id) or {})
            numbers = _snapshot_line_numbers(rows, selected, new_number)
            positive_numbers = [number for number in numbers if number]
            unit_index = int(selected.get("allocation_index") or selected.get("line_item_unit_index") or 1)
            unit_allocations = [unit for unit in allocation.get("unit_allocations") or [] if isinstance(unit, dict)]
            replaced_unit = False
            for unit in unit_allocations:
                if _positive_int(unit.get("line_item_unit_index")) == unit_index:
                    unit.update(
                        {
                            "edition_number": new_number,
                            "manual_override": True,
                            "override_old_edition_number": old_number,
                            "override_new_edition_number": new_number,
                            "override_reason": reason or "Manual edition override",
                            "override_timestamp": now_iso(),
                        }
                    )
                    replaced_unit = True
            if not replaced_unit:
                unit_allocations.append(
                    {
                        "order_gid": order_gid(selected.get("shopify_order_id")),
                        "line_item_gid": line_id,
                        "line_item_unit_index": unit_index,
                        "product_gid": product_gid(selected.get("shopify_product_id")),
                        "variant_gid": selected.get("shopify_variant_id") or "",
                        "edition_number": new_number,
                        "manual_override": True,
                        "override_old_edition_number": old_number,
                        "override_new_edition_number": new_number,
                        "override_reason": reason or "Manual edition override",
                        "override_timestamp": now_iso(),
                    }
                )
            allocation.update(
                {
                    "line_item_id": line_id,
                    "order_id": order_gid(selected.get("shopify_order_id")),
                    "product_id": product_gid(selected.get("shopify_product_id")),
                    "variant_id": selected.get("shopify_variant_id") or "",
                    "handle": selected.get("shopify_handle") or selected.get("product_handle") or "",
                    "product_title": selected.get("product_title") or "",
                    "variant_title": selected.get("variant_title") or "",
                    "quantity": max(len(numbers), int(selected.get("quantity") or 1)),
                    "edition_numbers": numbers,
                    "edition_number": positive_numbers[0] if positive_numbers else new_number,
                    "edition_total": edition_total,
                    "edition_display": format_edition_numbers(positive_numbers, edition_total),
                    "status": "Manual Override",
                    "manual_override": True,
                    "override_reason": reason or "Manual edition override",
                    "override_timestamp": now_iso(),
                    "unit_allocations": unit_allocations,
                }
            )
            line_items[line_id] = allocation
            allocation_payload["line_items"] = line_items
            shopify_sync.sync_order_allocation_metafield(
                selected.get("shopify_order_id"),
                allocation_payload,
                compare_digest=state.get("compare_digest"),
                config=config,
                request_post=request_post,
            )
            shopify_results["order_allocation"] = {"ok": True, "payload": allocation_payload}
        except Exception as error:
            warning = f"Shopify order allocation metafield sync failed: {error}"
        try:
            shopify_results["product_metafields"] = _sync_snapshot_product_metafields(
                product_state,
                config=config,
                request_post=request_post,
            )
        except Exception as error:
            product_warning = f"Shopify product metafield sync failed: {error}"
            warning = f"{warning} {product_warning}".strip()

    return {
        "edition_order": rows[target_index],
        "old_edition_number": old_number,
        "new_edition_number": new_number,
        "certificate_status": rows[target_index].get("certificate_status") or rows[target_index].get("certificate") or "Generate",
        "product": product_state,
        "shopify": shopify_results,
        "snapshot": saved,
        "warning": warning,
    }


def recalculate_snapshot_product_next_number(selected_row, *, config=None, sync_shopify=True, request_post=None):
    selected = dict(selected_row or {})
    rows = [dict(row or {}) for row in load_orders_snapshot().get("rows") or []]
    product_state = _snapshot_product_state(rows, selected)
    warning = ""
    result = {"ok": False, "skipped": True}
    if sync_shopify:
        config = config or shopify_sync.get_config()
        try:
            result = _sync_snapshot_product_metafields(product_state, config=config, request_post=request_post)
        except Exception as error:
            warning = f"Shopify product metafield sync failed: {error}"
    return {
        **product_state,
        "shopify": result,
        "warning": warning,
    }
