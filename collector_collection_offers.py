"""Read-only account offers using the existing smart catalogue and frame templates."""
import io
from pathlib import Path

from PIL import Image, ImageOps


FRAME_SKUS = {"SC-FCC-A4-BLK": "Black", "SC-FCC-A4-OAK": "Oak", "SC-FCC-A4-WHT": "White"}
FRAME_BOX = (84, 204, 824, 583)  # image_factory.MASTER_FRAMED_BOX


def frame_variants(product):
    result = []
    for variant in (product.get("variants") or {}).get("nodes") or []:
        color = FRAME_SKUS.get(variant.get("sku"))
        price = (variant.get("contextualPricing") or {}).get("price") or {}
        if color and variant.get("availableForSale") and price.get("amount") and price.get("currencyCode"):
            result.append({"variant_id": variant["id"], "color": color,
                           "contextual_price": {"amount": price["amount"], "currency_code": price["currencyCode"]}})
    return result


def render_certificate_frame(content, color):
    if color not in ("black", "oak", "white"):
        raise ValueError("Unknown frame")
    template = Path(__file__).resolve().parent / "templates" / f"{color}-frame-template.jpg"
    with Image.open(io.BytesIO(content)) as source, Image.open(template) as background:
        if source.width * source.height > 40_000_000:
            raise ValueError("Certificate image is too large")
        x, y, width, height = FRAME_BOX
        # Contain preserves every word and the full certificate border.
        with ImageOps.pad(source.convert("RGB"), (width, height), color="white") as fitted:
            canvas = background.convert("RGB")
            try:
                canvas.paste(fitted, (x, y))
                output = io.BytesIO()
                canvas.save(output, "WEBP", quality=88)
                return output.getvalue()
            finally:
                canvas.close()


def recommendations(customer_id):
    from crm_smart_catalogue import hydrate
    from crm_shopify import Shopify
    from crm_store import Store
    import supabase_backend
    doc = {"market": "AU", "middle_sections": [{"type": "catalogue", "visible": True,
           "settings": {"smart": True, "smart_count": 4, "display": {"image": True, "price": True}}, "products": []}]}
    resolved = hydrate(doc, Store(connect=supabase_backend.connect), Shopify(), {"id": customer_id})
    section = resolved["middle_sections"][0]
    return section.get("products", [])[:4] if section.get("visible") else []
