"""New Instant Experience copy selection; visual rendering stays independent."""
import ads_ie_legacy_description as legacy
import json

VERSION = "INSTANT EXPERIENCE COPY V3 LOCKED LEGACY STYLES"
OUTPUT_MODE = "three_visual_copy_v2"
# Legacy family tokens below preserve compatibility with saved copy history.
# They are copy identities only; every current visual uses premium_scarcity.
ROUTES = {
    "premium_scarcity_right": ("Premium Scarcity — Right Angle", "Product-aware scarcity hero", "premium_scarcity_smart_hybrid", "Claim Your Edition"),
    "premium_scarcity_front": ("Premium Scarcity — Straight On", "For the room that remembers", "private_gallery", "Secure Your Edition"),
    "premium_scarcity_left": ("Premium Scarcity — Left Angle", "Premium fan sanctuary", "the_cave", "Own This Edition"),
}

def cues(product, sport, market, token, context, recent=()):
    return [dict(route_key=key, visual_family="premium_scarcity", copy_family=value[2],
                 description_style=style, opening_hook_family=style,
                 headline_family=("product_identity", "collector_identity", "ownership")[i],
                 sentence_rhythm="historical short lines and intentional blank lines",
                 scarcity_close=("Secure yours.", "Secure yours.", "two-line collector ownership challenge")[i],
                 market_lens="product-specific vocabulary within locked framework", market=market, sport=sport)
            for i, ((key, value), style) in enumerate(zip(ROUTES.items(), legacy.NEW_AD_STYLE_KEYS))]


def ad_copy(route):
    value = next((v for v in ROUTES.values() if v[0] == route), None)
    if value is None:
        raise ValueError(f"Unknown copy route: {route}")
    style = legacy.NEW_AD_STYLE_KEYS[list(ROUTES.values()).index(value)]
    return f"AD COPY\n\nDescription:\n[one final personalised {style} description from its locked framework]\n\nHeadline:\n[one final product-specific headline]\n\nCTA:\n{value[3]}"


def instructions(product, sport, market, token, context, recent=()):
    return f"""{VERSION} — ONE PERSONALISED COPY SET PER VISUAL
{legacy.build_new_ad_style_rules(product, sport, context)}

Resolved supplied context:
{json.dumps(context, ensure_ascii=False, indent=2)}
Market: {market}. Use natural local vocabulary without changing the three frameworks or inventing sporting facts.

CONTROLLED PERSONALISATION
CREATIVE_VARIATION_TOKEN: {token}
{json.dumps(cues(product, sport, market, token, context, recent), ensure_ascii=False, indent=2)}
Freshness applies only to product-specific supporting lines and headlines. Keep the three hook families, mandatory lines and ownership closes even when recent history contains them. Do not rotate styles or invent new concepts to avoid repetition.
Preserve exact URL parameters, catalogue, product template and offer safeguards. These are text-only rules; retain all existing image-generation prompts unchanged.
"""
