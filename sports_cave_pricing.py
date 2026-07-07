from decimal import Decimal, InvalidOperation
import re


SPORTS_CAVE_AU_PRICE_LADDER = {
    "framed": {
        "XL": {"price": "349.00", "compare_at_price": "429.00"},
        "L": {"price": "269.00", "compare_at_price": "329.00"},
        "M": {"price": "209.00", "compare_at_price": "259.00"},
        "S": {"price": "159.00", "compare_at_price": "199.00"},
    },
    "unframed": {
        "XL": {"price": "159.00", "compare_at_price": "199.00"},
        "L": {"price": "119.00", "compare_at_price": "149.00"},
        "M": {"price": "89.00", "compare_at_price": "109.00"},
        "S": {"price": "55.00", "compare_at_price": "69.00"},
    },
}

FRAME_PRICE_GROUPS = {
    "black": "framed",
    "oak": "framed",
    "white": "framed",
    "unframed": "unframed",
}
FRAME_ORDER = ("Black", "Oak", "White", "Unframed")
SIZE_ORDER = ("XL", "L", "M", "S")


def normalize_money(value):
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        return f"{Decimal(raw):.2f}"
    except (InvalidOperation, ValueError):
        return raw


def price_ladder_rows():
    rows = []
    for frame in FRAME_ORDER:
        group = FRAME_PRICE_GROUPS[frame.casefold()]
        for size in SIZE_ORDER:
            ladder = SPORTS_CAVE_AU_PRICE_LADDER[group][size]
            rows.append(
                {
                    "Frame": frame,
                    "Size": size,
                    "Price": ladder["price"],
                    "Compare-at/RRP": ladder["compare_at_price"],
                }
            )
    return rows


def price_ladder_prompt_text():
    lines = [
        "CENTRAL SPORTS CAVE AUD PRICE LADDER",
        "Use these exact Shopify Price and Compare-at/RRP values.",
        "",
        "Black, Oak, and White framed variants:",
    ]
    for size in SIZE_ORDER:
        ladder = SPORTS_CAVE_AU_PRICE_LADDER["framed"][size]
        lines.append(
            f"- {size}: Price {ladder['price']} | Compare-at/RRP {ladder['compare_at_price']}"
        )
    lines.extend(["", "Unframed variants:"])
    for size in SIZE_ORDER:
        ladder = SPORTS_CAVE_AU_PRICE_LADDER["unframed"][size]
        lines.append(
            f"- {size}: Price {ladder['price']} | Compare-at/RRP {ladder['compare_at_price']}"
        )
    return "\n".join(lines)


def price_group_for_frame(frame):
    key = str(frame or "").strip().casefold()
    return FRAME_PRICE_GROUPS.get(key)


def parse_size(value):
    text = str(value or "").strip().upper()
    if not text:
        return ""
    compact = re.sub(r"\s+", " ", text)
    if re.match(r"^XL(?:\b|[\s\-–—/])", compact):
        return "XL"
    if re.match(r"^L(?:\b|[\s\-–—/])", compact):
        return "L"
    if re.match(r"^M(?:\b|[\s\-–—/])", compact):
        return "M"
    if re.match(r"^S(?:\b|[\s\-–—/])", compact):
        return "S"
    match = re.search(r"(?:^|[/\s])((?:XL)|L|M|S)(?=\s*[-–—]|\s|$)", compact)
    return match.group(1) if match else ""


def _selected_option_value(variant, option_name):
    wanted = str(option_name or "").casefold()
    for option in variant.get("selected_options") or variant.get("selectedOptions") or []:
        if str(option.get("name") or "").strip().casefold() == wanted:
            return str(option.get("value") or "").strip()
    return ""


def _parse_title_parts(title):
    parts = [part.strip() for part in str(title or "").split("/")]
    if len(parts) < 2:
        return "", ""
    return parts[0], parts[1]


def parse_variant_identity(variant):
    title = str((variant or {}).get("title") or "")
    frame = _selected_option_value(variant, "Frame")
    size_value = _selected_option_value(variant, "Size")
    if not frame or not size_value:
        title_frame, title_size = _parse_title_parts(title)
        frame = frame or title_frame
        size_value = size_value or title_size

    frame_key = str(frame or "").strip()
    group = price_group_for_frame(frame_key)
    size = parse_size(size_value)
    if not group:
        return {"ok": False, "reason": f"Unknown frame/finish: {frame_key or title}"}
    if not size:
        return {"ok": False, "reason": f"Unknown size: {size_value or title}"}
    return {
        "ok": True,
        "frame": frame_key.title() if frame_key.casefold() != "unframed" else "Unframed",
        "price_group": group,
        "size": size,
    }


def expected_price_for_variant(variant):
    parsed = parse_variant_identity(variant)
    if not parsed.get("ok"):
        return parsed
    ladder = SPORTS_CAVE_AU_PRICE_LADDER[parsed["price_group"]][parsed["size"]]
    return {
        **parsed,
        "price": ladder["price"],
        "compare_at_price": ladder["compare_at_price"],
    }


def is_price_correct(variant, expected):
    old_price = normalize_money(variant.get("price"))
    old_compare = normalize_money(
        variant.get("compare_at_price")
        or variant.get("compareAtPrice")
        or variant.get("compare_at")
    )
    return old_price == expected["price"] and old_compare == expected["compare_at_price"]


def analyze_product_price_updates(product):
    variants = list((product or {}).get("variants") or [])
    product_summary = {
        "product_id": (product or {}).get("shopify_product_id") or (product or {}).get("id") or "",
        "title": (product or {}).get("title") or "",
        "handle": (product or {}).get("handle") or "",
        "admin_url": (product or {}).get("admin_url") or "",
        "variants_scanned": len(variants),
        "already_correct": 0,
        "needs_update": [],
        "skipped_variants": [],
        "skipped_product_reason": "",
    }
    if len(variants) != 16:
        product_summary["skipped_product_reason"] = "Product does not have the Sports Cave 16-variant structure."
        return product_summary

    seen = set()
    for variant in variants:
        expected = expected_price_for_variant(variant)
        if not expected.get("ok"):
            product_summary["skipped_variants"].append(
                {
                    "product": product_summary["title"],
                    "variant": variant.get("title") or variant.get("id") or "",
                    "reason": expected.get("reason") or "Variant could not be parsed.",
                }
            )
            continue
        seen.add((expected["frame"].casefold(), expected["size"]))
        old_price = normalize_money(variant.get("price"))
        old_compare = normalize_money(
            variant.get("compare_at_price")
            or variant.get("compareAtPrice")
            or variant.get("compare_at")
        )
        if old_price == expected["price"] and old_compare == expected["compare_at_price"]:
            product_summary["already_correct"] += 1
            continue
        product_summary["needs_update"].append(
            {
                "product_id": product_summary["product_id"],
                "product": product_summary["title"],
                "handle": product_summary["handle"],
                "variant_id": variant.get("id") or variant.get("shopify_variant_id") or "",
                "variant": variant.get("title") or "",
                "frame": expected["frame"],
                "size": expected["size"],
                "old_price": old_price,
                "new_price": expected["price"],
                "old_compare_at_price": old_compare,
                "new_compare_at_price": expected["compare_at_price"],
            }
        )

    expected_seen = {(frame.casefold(), size) for frame in FRAME_ORDER for size in SIZE_ORDER}
    if product_summary["skipped_variants"]:
        product_summary["skipped_product_reason"] = "One or more variants could not be confidently parsed."
    elif seen != expected_seen:
        product_summary["skipped_product_reason"] = "Variant frame/size combinations do not match the Sports Cave 16-variant structure."
    return product_summary


def summarize_price_backfill(products):
    summaries = [analyze_product_price_updates(product) for product in products or []]
    skipped_products = [item for item in summaries if item.get("skipped_product_reason")]
    changes = [
        change
        for item in summaries
        if not item.get("skipped_product_reason")
        for change in item.get("needs_update") or []
    ]
    skipped_variants = [
        skipped
        for item in summaries
        for skipped in item.get("skipped_variants") or []
    ]
    return {
        "products_scanned": len(summaries),
        "variants_scanned": sum(item.get("variants_scanned") or 0 for item in summaries),
        "variants_already_correct": sum(item.get("already_correct") or 0 for item in summaries),
        "variants_needing_update": len(changes),
        "skipped_products": skipped_products,
        "skipped_variants": skipped_variants,
        "changes": changes,
        "product_summaries": summaries,
    }
