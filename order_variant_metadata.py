"""Conservative fallback for Shopify custom lines without a variant object."""
import re

MEDIUM_UNFRAMED = "Unframed / M - 30 × 45 cm (11.8 × 17.7 in)"


def variant_title(title, attributes):
    if str(title or "").strip():
        return title
    values = {}
    for item in attributes or []:
        key = str(item.get("key") or item.get("name") or "").strip().casefold()
        value = str(item.get("value") or "").strip().casefold()
        if key in values and values[key] != value:
            return ""  # Conflicting upstream options require review.
        values[key] = value
    size = re.sub(r"\s+", "", values.get("size", "").replace("×", "x"))
    if values.get("frame") == "unframed" and size in {"30x45cm", "medium", "m"}:
        return MEDIUM_UNFRAMED
    return ""
