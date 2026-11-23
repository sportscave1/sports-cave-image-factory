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


def render_certificate_frame(content, color, *, output_width=1000):
    if color not in ("black", "oak", "white"):
        raise ValueError("Unknown frame")
    if output_width not in (400, 1000):
        raise ValueError("Unknown frame preview size")
    template = Path(__file__).resolve().parent / "templates" / f"{color}-frame-template.jpg"
    with Image.open(io.BytesIO(content)) as source, Image.open(template) as background:
        if source.width * source.height > 40_000_000:
            raise ValueError("Certificate image is too large")
        x, y, width, height = FRAME_BOX
        # Contain preserves every word and the full certificate border.
        with source.convert("RGB") as rgb, ImageOps.pad(rgb, (width, height), color="white") as fitted:
            canvas = background.convert("RGB")
            try:
                canvas.paste(fitted, (x, y))
                output = io.BytesIO()
                if output_width == canvas.width:
                    canvas.save(output, "WEBP", quality=88)
                else:
                    with canvas.resize((output_width, round(canvas.height * output_width / canvas.width)), Image.Resampling.LANCZOS) as resized:
                        resized.save(output, "WEBP", quality=88)
                return output.getvalue()
            finally:
                canvas.close()


def recommendations(customer_id, country=None, seed_product_id=None):
    from crm_smart_catalogue import histories, lines
    from crm_smart_candidates import memberships, collection_products, balanced
    from crm_catalogue import Catalogue, product_id, product_issues, edition_available
    from crm_collector_transport import bounded
    from crm_shopify import Shopify
    from crm_store import Store
    from collector_vault import list_owned_certificates, customer_id_candidates
    import supabase_backend
    import logging
    store = Store(connect=supabase_backend.connect)
    aliases = customer_id_candidates(customer_id)
    ledger = histories(store, aliases)  # A failed/incomplete history never relaxes ownership.
    orders = [order for alias in aliases for order in ledger.get(alias, [])]
    owned = set()
    for order in orders:
        for item in lines(order):
            variant = item.get("variant") or {}
            product = item.get("product") or variant.get("product") or {}
            identity = product_id(product.get("id") or item.get("product_id"))
            if identity:
                owned.add(identity)
    for certificate in list_owned_certificates(customer_id):
        identity = product_id(certificate.get("shopify_product_id"))
        if identity:
            owned.add(identity)
    if not owned:
        return []
    seed = product_id(seed_product_id) if seed_product_id else None
    if seed_product_id and (not seed or seed not in owned):
        from collector_vault import CollectorVaultError
        raise CollectorVaultError("Choose an owned edition for recommendations.")
    shop = bounded(Shopify(), seconds=12)
    country = country or next((order.get("_country") for order in orders if order.get("_country")), "AU")
    market = {"GB": "UK"}.get(country, country)
    if market not in ("AU", "US", "UK", "CA", "NZ"):
        market = "Global"
    catalogue = Catalogue(shop, connect=supabase_backend.connect)
    def load_candidates():
        groups = [collection_products(shop, collection["id"] if isinstance(collection, dict) else collection)
                  for collection in memberships(shop, [seed] if seed else sorted(owned))]
        candidates = list(dict.fromkeys(identity for group in groups for identity in group if identity not in owned))[:120]
        if seed:
            # Same explicit subject/team/event/league/sport signals as the live
            # storefront. Never infer an athlete from a title or cross customers.
            tags = {}
            identities = [seed, *candidates]
            query = "query AccountEditionAffinity($ids:[ID!]!) { nodes(ids:$ids) { ... on Product { id tags } } }"
            for start in range(0, len(identities), 25):
                nodes = shop.query(query, {"ids": identities[start:start+25]}, "account edition affinity", 300).get("nodes") or []
                tags.update({node["id"]: node.get("tags") or [] for node in nodes if node})
            try:
                from website_recommendation_analytics import _ranking_snapshot
                signals = (_ranking_snapshot() or {}).get(country, {})
            except Exception:
                signals = {}
            from collector_collection_ranking import rank_candidates
            candidates = rank_candidates(seed, candidates, tags, signals)
        allowed = set(candidates)
        return {'candidates': candidates, 'groups': [[identity for identity in group if identity in allowed] for group in groups]}
    from collector_recommendation_cache import ranked_candidates
    packet = ranked_candidates(shop, customer_id, owned, seed, country, load_candidates)
    candidates = [identity for identity in packet['candidates'] if identity not in owned]
    groups = packet['groups']
    eligible = {}
    for start in range(0, len(candidates), 20):
        for product in catalogue.resolve(candidates[start:start + 20], market, allow_missing=True):
            if product["id"] not in owned and edition_available(product.get("edition")) and not product_issues(product, {"display": {"image": True, "price": True}}):
                eligible[product["id"]] = product
        if len(eligible) >= 8:
            break
    # Use the same exact sport memberships, edition eligibility, verified sales
    # ranking and balancing as Smart catalogue. The authenticated account client
    # performs Storefront publication/variant/price checks using its native token,
    # so this endpoint never needs a separate server Storefront credential.
    chosen = [eligible[identity] for identity in candidates if identity in eligible][:8] if seed else balanced(groups, eligible, 8)
    logging.getLogger(__name__).info("Account recommendations candidates=%s eligible=%s returned=%s", len(candidates), len(eligible), len(chosen))
    return chosen
