def _safe_int(value, default):
    try:
        if value in (None, ""):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def build_edition_display_text(product):
    """Build the exact public edition wording from Sports Cave OS values only."""
    edition_limit = _safe_int(product.get("edition_limit"), 100)
    next_available = _safe_int(product.get("next_available_edition"), 1)
    editions_sold = _safe_int(product.get("editions_sold"), 0)
    fallback_remaining = max(edition_limit - editions_sold, 0)
    editions_remaining = _safe_int(product.get("editions_remaining"), fallback_remaining)
    edition_status = str(product.get("edition_status") or "").strip()

    if edition_status == "Sold Out" or editions_remaining <= 0 or next_available > edition_limit:
        return "SOLD OUT EDITION"
    if editions_remaining <= 3:
        return f"FINAL EDITION #{next_available} OF {edition_limit} AVAILABLE"
    return f"EDITION #{next_available} OF {edition_limit} AVAILABLE"
