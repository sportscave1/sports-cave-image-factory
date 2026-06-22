from datetime import datetime, timezone
import json
from pathlib import Path

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


def _allocation_record(order_payload, line_item, product_id, edition_numbers, edition_total):
    line_id = _line_identity(line_item)
    quantity = _coerce_quantity(line_item.get("quantity"))
    display = format_edition_numbers(edition_numbers, edition_total)
    return {
        "line_item_id": line_id,
        "product_id": product_id,
        "product_title": line_item.get("title") or line_item.get("name") or "",
        "variant_title": line_item.get("variant_title") or line_item.get("variantTitle") or "",
        "quantity": quantity,
        "edition_numbers": edition_numbers,
        "edition_number": edition_numbers[0] if edition_numbers else None,
        "edition_total": int(edition_total or 0),
        "edition_display": display,
        "order_name": order_payload.get("name") or "",
        "allocated_at": now_iso(),
    }


def build_order_allocation_payload(order_payload, existing_payload, new_allocations):
    payload = parse_allocation_payload(existing_payload)
    payload.update(
        {
            "version": SNAPSHOT_VERSION,
            "source": "sports_cave_os",
            "order_id": _order_identity(order_payload),
            "order_name": order_payload.get("name") or payload.get("order_name") or "",
            "updated_at": now_iso(),
        }
    )
    line_items = dict(payload.get("line_items") or {})
    for line_id, allocation in new_allocations.items():
        line_items[str(line_id)] = allocation
    payload["line_items"] = line_items
    return payload


def process_shopify_order_for_editions(order_payload, config=None, request_post=None):
    config = config or shopify_sync.get_config()
    if not _is_paid_order(order_payload):
        return {"processed": False, "reason": "Order is not paid.", "assignments_created": 0, "issues": []}

    shopify_order_id = _order_identity(order_payload)
    if not shopify_order_id:
        raise shopify_sync.ShopifyAPIError("Order ID is missing from webhook payload.")

    assignments_created = 0
    issues = []
    product_updates = {}
    product_state_cache = {}

    for attempt in range(2):
        state = read_order_allocation_state(shopify_order_id, config=config, request_post=request_post)
        existing_payload = state.get("payload") or {}
        existing_lines = existing_payload.get("line_items") or {}
        new_allocations = {}
        product_updates.clear()
        product_state_cache.clear()

        for line_item in _line_items(order_payload):
            line_id = _line_identity(line_item)
            if not line_id or line_id in existing_lines:
                continue
            product_id = _line_product_gid(line_item)
            if not product_id:
                issues.append({"line_item_id": line_id, "status": "Product Not Found"})
                continue
            if product_id not in product_state_cache:
                product_metafields = shopify_sync.fetch_metafields(
                    product_id,
                    namespace="sports_cave",
                    config=config,
                    request_post=request_post,
                ).get("metafields") or []
                edition = _product_edition_from_metafields(product_metafields)
                product_state_cache[product_id] = {
                    "edition": edition,
                    "next_number": int(edition.get("edition_next_number") or 1),
                }
            product_state = product_state_cache[product_id]
            edition = product_state["edition"]
            if not edition.get("edition_enabled"):
                issues.append({"line_item_id": line_id, "product_id": product_id, "status": "Edition Disabled"})
                continue

            quantity = _coerce_quantity(line_item.get("quantity"))
            next_number = int(product_state.get("next_number") or 1)
            edition_total = int(edition.get("edition_total") or 100)
            remaining = max(edition_total - next_number + 1, 0)
            if remaining < quantity:
                issues.append({"line_item_id": line_id, "product_id": product_id, "status": "Sold Out Issue"})
                continue

            numbers = list(range(next_number, next_number + quantity))
            new_allocations[line_id] = _allocation_record(
                order_payload,
                line_item,
                product_id,
                numbers,
                edition_total,
            )
            product_updates[product_id] = {
                "shopify_product_id": product_id,
                "title": line_item.get("title") or "",
                "edition_enabled": True,
                "edition_total": edition_total,
                "edition_next_number": next_number + quantity,
                "edition_label": edition.get("edition_label") or "Numbered Edition",
            }
            product_state["next_number"] = next_number + quantity

        if not new_allocations:
            return {
                "processed": True,
                "assignments_created": 0,
                "issues": issues,
                "skipped_existing": len(existing_lines),
            }

        payload = build_order_allocation_payload(order_payload, existing_payload, new_allocations)
        try:
            shopify_sync.sync_order_allocation_metafield(
                shopify_order_id,
                payload,
                compare_digest=state.get("compare_digest"),
                config=config,
                request_post=request_post,
            )
            assignments_created = sum(
                len(item.get("edition_numbers") or [])
                for item in new_allocations.values()
            )
            break
        except shopify_sync.ShopifyAPIError as error:
            if attempt == 0 and "compare" in str(error).casefold():
                continue
            raise

    if product_updates:
        shopify_sync.sync_limited_edition_metafields_for_products(
            list(product_updates.values()),
            config=config,
            request_post=request_post,
        )

    return {
        "processed": True,
        "assignments_created": assignments_created,
        "issues": issues,
        "updated_products": len(product_updates),
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
