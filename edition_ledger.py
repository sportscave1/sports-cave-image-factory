"""Channel-aware policy helpers for the Edition Ops allocation ledger.

This module contains no Shopify or database I/O.  It keeps source identity,
eligibility, historical-order policy, and marketplace mapping rules consistent
across webhook, reconciliation, import, and repair entry points.
"""

from __future__ import annotations

from datetime import datetime, timezone
import re
import threading


SOURCE_CHANNEL_SHOPIFY = "shopify"
SOURCE_CHANNEL_ETSY = "etsy"
SOURCE_CHANNEL_EBAY = "ebay"
SUPPORTED_SOURCE_CHANNELS = frozenset(
    {SOURCE_CHANNEL_SHOPIFY, SOURCE_CHANNEL_ETSY, SOURCE_CHANNEL_EBAY}
)
MARKETPLACE_SOURCE_CHANNELS = frozenset({SOURCE_CHANNEL_ETSY, SOURCE_CHANNEL_EBAY})

_CHANNEL_ALIASES = {
    "etsy": SOURCE_CHANNEL_ETSY,
    "etsy marketplace": SOURCE_CHANNEL_ETSY,
    "ebay": SOURCE_CHANNEL_EBAY,
    "e bay": SOURCE_CHANNEL_EBAY,
    "shopify": SOURCE_CHANNEL_SHOPIFY,
    "web": SOURCE_CHANNEL_SHOPIFY,
    "online store": SOURCE_CHANNEL_SHOPIFY,
    "shopify draft order": SOURCE_CHANNEL_SHOPIFY,
    "draft order": SOURCE_CHANNEL_SHOPIFY,
    "pos": SOURCE_CHANNEL_SHOPIFY,
    "shopify pos": SOURCE_CHANNEL_SHOPIFY,
}

_SHOPIFY_SOURCE_DISPLAY = {
    "web": "Online Store",
    "online store": "Online Store",
    "shop": "Shop",
    "pos": "Shopify POS",
    "shopify pos": "Shopify POS",
    "shopify draft order": "Draft order",
    "draft order": "Draft order",
}


def _normalized_text(value):
    return re.sub(r"\s+", " ", str(value or "").strip().casefold().replace("_", " ").replace("-", " "))


def canonical_external_id(value):
    """Return an immutable identity value without changing its namespace."""
    return str(value or "").strip()


def canonical_shopify_gid(resource_type, value):
    raw = canonical_external_id(value)
    if not raw:
        return ""
    match = re.match(r"^gid://shopify/[^/]+/([^/?#]+)", raw, flags=re.IGNORECASE)
    identifier = match.group(1) if match else raw
    if identifier.isdigit():
        return f"gid://shopify/{resource_type}/{identifier}"
    return raw


def _attribute_values(payload):
    """Return normalized key/value pairs from Shopify custom attributes."""
    values = {}
    for field in ("custom_attributes", "note_attributes", "properties"):
        for item in (payload or {}).get(field) or []:
            if not isinstance(item, dict):
                continue
            key = _normalized_text(item.get("key") or item.get("name"))
            value = canonical_external_id(item.get("value"))
            if key and value and key not in values:
                values[key] = value
    return values


def _first_identity(payload, direct_keys, attribute_keys=()):
    for key in direct_keys:
        value = canonical_external_id((payload or {}).get(key))
        if value:
            return value
    attributes = _attribute_values(payload)
    for key in attribute_keys:
        value = canonical_external_id(attributes.get(_normalized_text(key)))
        if value:
            return value
    return ""


def normalize_source_channel(value):
    """Map known Shopify sourceName values to the durable ledger channel."""
    normalized = _normalized_text(value)
    if re.search(r"(?:^|\s)etsy(?:\s|$)", normalized):
        return SOURCE_CHANNEL_ETSY
    if re.search(r"(?:^|\s)e\s*bay(?:\s|$)", normalized):
        return SOURCE_CHANNEL_EBAY
    return _CHANNEL_ALIASES.get(normalized, SOURCE_CHANNEL_SHOPIFY)


def source_display_name(value, *, tags=()):
    """Return stable channel attribution without using it as order identity."""
    normalized = _normalized_text(value)
    normalized_tags = {_normalized_text(tag) for tag in (tags or ()) if str(tag or "").strip()}
    channel = normalize_source_channel(normalized)
    if channel == SOURCE_CHANNEL_EBAY:
        is_australia = (
            "australia" in normalized
            or normalized.endswith(" au")
            or "ebay au" in normalized_tags
            or "ebay australia" in normalized_tags
        )
        return "eBay Australia" if is_australia else "eBay"
    if channel == SOURCE_CHANNEL_ETSY:
        return "Etsy"
    return _SHOPIFY_SOURCE_DISPLAY.get(
        normalized,
        str(value or "Shopify").replace("_", " ").replace("-", " ").strip().title() or "Shopify",
    )


def source_channel_for_order(order):
    order = order or {}
    explicit = _normalized_text(order.get("source_channel"))
    if explicit in SUPPORTED_SOURCE_CHANNELS:
        return explicit
    attributes = _attribute_values(order)
    if any(
        canonical_external_id(order.get(key))
        for key in ("etsy_order_id", "etsy_receipt_id")
    ) or any("etsy" in key and ("order" in key or "receipt" in key) for key in attributes):
        return SOURCE_CHANNEL_ETSY
    if any(
        canonical_external_id(order.get(key))
        for key in ("ebay_order_id", "ebay_sales_record_id")
    ) or any("ebay" in key and ("order" in key or "sales record" in key) for key in attributes):
        return SOURCE_CHANNEL_EBAY
    return normalize_source_channel(
        order.get("source_name")
        or order.get("sourceName")
        or order.get("source_display")
        or order.get("source")
    )


def durable_source_identity(
    source_channel,
    external_order_id,
    external_line_item_id,
    unit_ordinal,
):
    channel = normalize_source_channel(source_channel)
    order_id = canonical_external_id(external_order_id)
    line_id = canonical_external_id(external_line_item_id)
    try:
        ordinal = int(unit_ordinal)
    except (TypeError, ValueError):
        ordinal = 0
    if channel not in SUPPORTED_SOURCE_CHANNELS:
        raise ValueError(f"Unsupported source channel: {source_channel}")
    if not order_id or not line_id or ordinal < 1:
        raise ValueError("A source channel, external order ID, external line item ID, and positive unit ordinal are required.")
    return f"{channel}:{order_id}:{line_id}:{ordinal}"


def external_order_id_for_order(order):
    order = order or {}
    # Marketplace Connect orders are canonical Shopify orders.  Webhook,
    # reconciliation and manual retry must therefore converge on the same
    # immutable Shopify GID even when a marketplace sales-record ID is also
    # present.  Direct Etsy/eBay payloads still fall back to their native ID.
    channel = source_channel_for_order(order)
    raw_id = canonical_external_id(order.get("id"))
    shopify_identity = _first_identity(order, ("shopify_order_id", "admin_graphql_api_id"))
    if not shopify_identity and raw_id.casefold().startswith("gid://shopify/order/"):
        shopify_identity = raw_id
    if not shopify_identity and channel == SOURCE_CHANNEL_SHOPIFY:
        shopify_identity = raw_id
    shopify_id = canonical_shopify_gid("Order", shopify_identity)
    if shopify_id:
        return shopify_id
    channel_specific = {
        SOURCE_CHANNEL_ETSY: ("etsy_order_id", "marketplace_order_id", "id"),
        SOURCE_CHANNEL_EBAY: ("ebay_order_id", "marketplace_order_id", "id"),
        SOURCE_CHANNEL_SHOPIFY: (),
    }
    marketplace_id = _first_identity(
        order,
        ("external_order_id", "source_identifier", *channel_specific.get(channel, ())),
        (
            "external order id",
            "marketplace order id",
            f"{channel} order id",
            f"{channel} receipt id",
        ),
    )
    if marketplace_id:
        return marketplace_id
    return ""


def external_line_item_id_for_line(order, line_item, fallback_position=None):
    order = order or {}
    line_item = line_item or {}
    channel = source_channel_for_order(order)
    raw_id = canonical_external_id(line_item.get("id"))
    shopify_id = _first_identity(line_item, ("shopify_line_item_id", "admin_graphql_api_id"))
    if not shopify_id and raw_id.casefold().startswith("gid://shopify/lineitem/"):
        shopify_id = raw_id
    if not shopify_id and channel == SOURCE_CHANNEL_SHOPIFY:
        shopify_id = raw_id
    if shopify_id:
        return canonical_shopify_gid("LineItem", shopify_id)
    channel_specific = {
        SOURCE_CHANNEL_ETSY: ("etsy_line_item_id", "transaction_id", "id"),
        SOURCE_CHANNEL_EBAY: ("ebay_line_item_id", "transaction_id", "id"),
        SOURCE_CHANNEL_SHOPIFY: (),
    }
    external_id = _first_identity(
        line_item,
        ("external_line_item_id", *channel_specific.get(channel, ())),
        (
            "external line item id",
            "marketplace line item id",
            f"{channel} line item id",
            f"{channel} transaction id",
            "transaction id",
        ),
    )
    if external_id:
        return external_id
    # A synthesized position is stable only when the upstream immutable order ID
    # and line ordering are stable. Marketplace orders are therefore quarantined
    # instead of accepting this fallback.
    if channel == SOURCE_CHANNEL_SHOPIFY and fallback_position:
        order_id = external_order_id_for_order(order)
        if order_id:
            return f"{order_id}:line:{int(fallback_position)}"
    return ""


def marketplace_mapping_identity_candidates(line_item):
    """Return explicit mapping keys; titles and handles are deliberately absent."""
    line_item = line_item or {}
    candidates = []
    attributes = _attribute_values(line_item)
    for identity_type, keys, attribute_keys in (
        (
            "listing_id",
            ("listing_id", "etsy_listing_id", "ebay_item_id", "item_id"),
            ("listing id", "etsy listing id", "ebay item id", "ebay itemid", "item id", "itemid"),
        ),
        (
            "external_variant_id",
            ("external_variant_id", "etsy_variant_id", "ebay_variant_id"),
            ("external variant id", "etsy variant id", "ebay variant id"),
        ),
        ("sku", ("sku",), ("sku",)),
    ):
        for key in keys:
            value = canonical_external_id(line_item.get(key))
            if value and (identity_type, value) not in candidates:
                candidates.append((identity_type, value))
        for key in attribute_keys:
            value = canonical_external_id(attributes.get(_normalized_text(key)))
            if value and (identity_type, value) not in candidates:
                candidates.append((identity_type, value))
    return candidates


def parse_datetime(value):
    if isinstance(value, datetime):
        parsed = value
    else:
        raw = str(value or "").strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def order_effective_datetime(order):
    order = order or {}
    for key in ("processed_at", "created_at", "createdAt"):
        parsed = parse_datetime(order.get(key))
        if parsed:
            return parsed
    return None


def paid_order_eligibility(order, *, tracking_start=None, allow_historical=False):
    """Apply the allocation policy shared by every ingestion path."""
    if not isinstance(order, dict):
        return {"eligible": False, "reason": "invalid_payload"}
    if not external_order_id_for_order(order):
        return {"eligible": False, "reason": "missing_external_order_id"}
    test_value = order.get("test")
    if test_value is True or str(test_value or "").strip().casefold() in {"1", "true", "yes"}:
        return {"eligible": False, "reason": "test_order"}
    if str(order.get("cancelled_at") or order.get("cancelledAt") or "").strip():
        return {"eligible": False, "reason": "cancelled_order"}
    financial_status = str(
        order.get("financial_status") or order.get("displayFinancialStatus") or ""
    ).strip().upper()
    if financial_status != "PAID":
        return {
            "eligible": False,
            "reason": "financial_status_missing" if not financial_status else f"financial_status_{financial_status.casefold()}",
        }
    if not list(order.get("line_items") or []):
        return {"eligible": False, "reason": "no_line_items"}
    tracking = parse_datetime(tracking_start)
    effective = order_effective_datetime(order)
    if tracking and effective and effective < tracking and not allow_historical:
        return {"eligible": False, "reason": "historical_order_requires_explicit_backfill"}
    return {"eligible": True, "reason": "eligible_paid_non_cancelled_order"}


def is_marketplace_order(order):
    return source_channel_for_order(order) in MARKETPLACE_SOURCE_CHANNELS


class EditionLimitReached(ValueError):
    pass


class AtomicLedgerModel:
    """Small executable model of the SQL allocation contract.

    Production allocation is performed by ``allocate_edition_line_units_atomic``
    in PostgreSQL.  This model is used by dry-run validation and deterministic
    concurrency regressions without requiring a production database.
    """

    def __init__(self, edition_total=100):
        self.edition_total = int(edition_total)
        self._lock = threading.RLock()
        self._source_units = {}
        self._source_lines = {}
        self._product_numbers = {}

    def allocate(self, source_channel, external_order_id, external_line_item_id, product_gid, quantity=1):
        quantity = int(quantity)
        if quantity < 1:
            raise ValueError("quantity must be positive")
        with self._lock:
            channel = normalize_source_channel(source_channel)
            line_key = (
                channel,
                canonical_external_id(external_order_id),
                canonical_external_id(external_line_item_id),
            )
            existing_line = self._source_lines.get(line_key)
            if existing_line and existing_line != (product_gid, quantity):
                raise ValueError("A replay cannot change a source line's product or quantity")
            self._source_lines[line_key] = (product_gid, quantity)
            keys = [
                durable_source_identity(channel, external_order_id, external_line_item_id, ordinal)
                for ordinal in range(1, quantity + 1)
            ]
            existing = [self._source_units.get(key) for key in keys]
            missing = sum(number is None for number in existing)
            used = self._product_numbers.setdefault(product_gid, set())
            next_number = max(used, default=0) + 1
            if next_number + missing - 1 > self.edition_total:
                raise EditionLimitReached(f"Edition limit {self.edition_total} reached")
            result = []
            for key, number in zip(keys, existing):
                if number is None:
                    number = next_number
                    next_number += 1
                    if number in used:
                        raise AssertionError("product edition number was consumed twice")
                    self._source_units[key] = number
                    used.add(number)
                result.append(number)
            return result

    def state(self, product_gid):
        with self._lock:
            used = set(self._product_numbers.get(product_gid) or set())
            highest = max(used, default=0)
            sold = len(used)
            return {
                "sold_count": sold,
                "remaining_count": max(self.edition_total - sold, 0),
                "next_edition_number": highest + 1,
                "edition_total": self.edition_total,
                "numbers": sorted(used),
            }
