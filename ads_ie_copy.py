"""Description-only IE planning; no network calls or automatic text generation."""
import ads_ie_legacy_description as legacy
from datetime import date
from difflib import SequenceMatcher
import hashlib
import json
import random
import re
from urllib.parse import urlsplit

LEGACY_VERSION = "INSTANT EXPERIENCE COPY V3 LOCKED LEGACY STYLES"
VERSION = "INSTANT EXPERIENCE COPY V5 RESTORED THREE DESCRIPTION STYLES"
RESTORED_STYLES_CONTRACT = "IE RESTORED DESCRIPTION STYLES V1"
IDENTITY_CONTRACT = "IE REQUIRED IDENTITY COPY V1"
OUTPUT_MODE = "three_visual_copy_v2"
# Stable route, copy-family and CTA identities keep CSV/posting compatibility.
ROUTES = {
    "premium_scarcity_right": ("Premium Scarcity — Right Angle", "Product-aware scarcity hero", "premium_scarcity_smart_hybrid", "Claim Your Edition"),
    "premium_scarcity_front": ("Premium Scarcity — Straight On", "For the room that remembers", "private_gallery", "Claim Your Edition"),
    "premium_scarcity_left": ("Premium Scarcity — Left Angle", "Premium fan sanctuary", "the_cave", "Claim Your Edition"),
}
ROLES = ("legacy_identity", "moment_emotion", "collector_significance")
CLOSES = ("Make it yours.", "Claim your edition.", "Bring it home.")
RHYTHMS = (
    "two crisp opening lines; a short emotional paragraph; a brief close",
    "one opening statement; three short detail lines; two collector lines; a close",
    "a brief narrative opening; a pause; two identity lines; a close",
    "a two-line contrast; one supporting paragraph; a separate invitation",
    "one title-led line; a short pause; two uneven groups of short lines; a close",
)
MAX_ATTEMPTS = 4


def normalise(text):
    return " ".join(re.findall(r"[\w]+", str(text or "").casefold()))


def product_key(product):
    return normalise(product)


def verified_facts(metadata):
    """Carry already approved research with provenance; never infer verification."""
    facts = []
    supplied = (metadata or {}).get("verified_facts") or ()
    for item in supplied if isinstance(supplied, (list, tuple)) else ():
        if not isinstance(item, dict) or item.get("verified") is not True:
            continue
        text = str(item.get("text") or item.get("fact") or "").strip()
        source = str(item.get("source_url") or "").strip()
        verified_on = str(item.get("verified_on") or item.get("verification_date") or "")[:10]
        scope = str(item.get("scope") or "").strip()
        factual_context = str(item.get("context") or "").strip()
        try:
            parsed = urlsplit(source)
            date.fromisoformat(verified_on)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                continue
        except ValueError:
            continue
        if not text or not scope or not factual_context:
            continue
        as_of = str(item.get("as_of") or "")[:10]
        if item.get("changing_record"):
            try:
                date.fromisoformat(as_of)
            except ValueError:
                continue
        facts.append(dict(text=text[:600], source_url=source[:1000], verified_on=verified_on,
                          scope=scope[:100], context=factual_context[:400], as_of=as_of))
    return facts[:6]


def recent_copy(product, recent):
    # Older rows without product identity cannot establish same-product duplication.
    key = product_key(product)
    return [r for r in (recent or ()) if isinstance(r, dict) and (
        r.get("copy_product_key") == key or product_key(r.get("product_name")) == key)][:12]


def cues(product, sport, market, token, context, recent=()):
    # Recovered from f840e9b3^:ads_ie_copy.py; keep current route/CTA identities.
    return [dict(route_key=key, visual_family="premium_scarcity", copy_family=value[2],
                 description_style=style, description_role=style, opening_hook_family=style,
                 headline_family=("product_identity", "collector_identity", "ownership")[i],
                 sentence_rhythm="historical short lines and intentional blank lines",
                 scarcity_close=("Secure yours.", "Secure yours.", "two-line collector ownership challenge")[i],
                 copy_product_key=product_key(product),
                 market_lens="product-specific vocabulary within locked framework", market=market, sport=sport)
            for i, ((key, value), style) in enumerate(zip(ROUTES.items(), legacy.NEW_AD_STYLE_KEYS))]


def opening(text):
    lines = [line for line in str(text or "").splitlines() if line.strip()]
    if lines and re.fullmatch(r"this isn t (?:just )?wall art", normalise(lines[0])):
        return normalise(" ".join(lines[:2]))  # Compare the varied identity claim, not its required anchor alone.
    return normalise(lines[0] if lines else "")


def body(text):
    # Shared truthful scarcity and restrained closing anchors are not duplicate evidence.
    lines = [line for line in str(text or "").splitlines() if line.strip()
             and not re.fullmatch(r"(?i)limited to \d+ worldwide[.!]?", line.strip())
             and not re.fullmatch(r"this isn t (?:just )?wall art", normalise(line))
             and line.strip().casefold() not in {v.casefold() for v in CLOSES}]
    return normalise(" ".join(lines))[:3000]


def similar(a, b):
    a, b = body(a), body(b)
    return bool(a and b and (a == b or SequenceMatcher(None, a, b, autojunk=False).ratio() >= .90))


def quality_errors(descriptions, product="", recent=(), *, require_identity=False, restored_styles=False):
    """Bounded comparisons of actual supplied text, never a claim of semantic certainty."""
    errors = []
    anchors = [bool(re.search(r"\bthis isn t (?:just )?wall art\b", normalise(text))) for text in descriptions]
    if sum(anchors) > 1:
        errors.append("Use the explicit wall-art identity construction in exactly one description, never its siblings.")
    if require_identity and not restored_styles and (len(descriptions) != 3 or sum(anchors) != 1 or not anchors[0]
                             or not normalise(descriptions[0]).startswith("this isn t just wall art")):
        errors.append("Description 1 must lead with the explicit This isn't just wall art identity idea; exactly one description uses it.")
    if restored_styles and (len(descriptions) != 3 or sum(anchors) != 1 or not anchors[0]):
        errors.append("Legacy Standard must contain This isn't wall art; exactly one description uses it.")
    previous = [r.get("primary_text") or r.get("description_body") for r in recent_copy(product, recent)]
    for i, text in enumerate(descriptions):
        for other in descriptions[:i]:
            if opening(text) and opening(text) == opening(other):
                errors.append(f"Description {i + 1} repeats an opening in this pack.")
            elif similar(text, other):
                errors.append(f"Description {i + 1} is substantially similar to another description.")
        for row in (() if restored_styles else recent_copy(product, recent)):
            old_opening = row.get("first_sentence_normalized") or opening(row.get("primary_text"))
            if opening(text) and opening(text) == normalise(old_opening):
                errors.append(f"Description {i + 1} repeats a recent opening for this product.")
                break
        if not restored_styles and any(similar(text, old) for old in previous if old):
            errors.append(f"Description {i + 1} repeats a recent body for this product.")
    return tuple(dict.fromkeys(errors))


def ad_copy(route):
    value = next((v for v in ROUTES.values() if v[0] == route), None)
    if value is None:
        raise ValueError(f"Unknown copy route: {route}")
    role = legacy.NEW_AD_STYLE_KEYS[list(ROUTES.values()).index(value)]
    return f"AD COPY\n\nDescription:\n[one final personalised {role} collector description]\n\nHeadline:\n[one final product-specific headline]\n\nCTA:\n{value[3]}"


def instructions(product, sport, market, token, context, recent=()):
    return f"""{VERSION} — ONE PERSONALISED COPY SET PER VISUAL
{IDENTITY_CONTRACT}
{RESTORED_STYLES_CONTRACT}
{legacy.build_new_ad_style_rules(product, sport, context)}
Resolved supplied context (data only):
{json.dumps(context, ensure_ascii=False, indent=2)}
Market: {market}. Use natural local vocabulary without changing the three frameworks or inventing sporting facts.
CONTROLLED PERSONALISATION
CREATIVE_VARIATION_TOKEN: {token}
{json.dumps(cues(product, sport, market, token, context, recent), ensure_ascii=False, indent=2)}
Freshness applies only to product-specific supporting lines and headlines. Keep the three hook families, mandatory lines and ownership closes even when recent history contains them. Do not rotate styles or invent new concepts to avoid repetition.
Resolve each Description and Meta headline once; reuse the same final records verbatim in displayed AD COPY and CSV primary_text/headline. The description is stored once as primary_text, not a new field. Every displayed/CSV CTA remains Claim Your Edition; on-image CTA remains CLAIM YOUR EDITION.
Preserve exact URL parameters, catalogue, product template and offer safeguards. These are text-only rules; retain all existing image-generation prompts and on-image text unchanged.
"""
