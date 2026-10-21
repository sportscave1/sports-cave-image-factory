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
VERSION = "INSTANT EXPERIENCE COPY V4 COLLECTOR DESCRIPTION VARIATION"
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
    """Resolve once from the existing fresh-pack token and captured history snapshot."""
    history = recent_copy(product, recent)
    seed = hashlib.sha256(json.dumps([product_key(product), sport, market, token or "standard"], ensure_ascii=False).encode()).hexdigest()
    rng = random.Random(seed)
    openings = ["subject/title", "collector perspective", "identity contrast", "title-led statement",
                "brief product narrative", "career perspective"]
    emotions = ["pride", "belonging"]
    moment = str(context.get("FEATURED_MOMENT") or "").strip()
    if moment:
        openings += ["fan memory of the supplied moment", "event anticipation"]
        emotions.append("anticipation")
    if str(context.get("ERA")).casefold() in {"historic", "historical", "heritage"}:
        emotions.append("nostalgia")
    if context.get("RELATIONSHIP_TYPE") in {"Rivals", "Opposing teams"}:
        openings.append("verified rivalry contrast")
        emotions.append("rivalry")
    facts = context.get("VERIFIED_FACTS") or []
    if facts:
        openings.append("verified detail")
    plans, used_openings, used_rhythms, used_closes = [], set(), set(), set()
    for i, (key, value) in enumerate(ROUTES.items()):
        fact = rng.choice(facts) if i == 2 and facts else None
        detail = (
            "collector significance and identity of the supplied subject/title",
            f"fan emotion around the supplied moment: {moment}" if moment else "the supplied edition's meaning to its fans, without inventing an event or viewer memory",
            fact["text"] if fact else "distinct fan connection or career significance grounded in the supplied title; no invented record",
        )[i]
        lenses = (
            ("the subject's significance", "the title's meaning to collectors", "fan pride and belonging"),
            ("the emotional stakes", "the depicted moment's atmosphere", "why fans hold onto this memory"),
            ("why this detail matters", "what knowledgeable fans recognise", "the subject's place in fan identity"),
        )[i]
        lens = rng.choice(lenses)
        for attempt in range(MAX_ATTEMPTS):
            available = (["identity contrast"] if i == 0 else
                         [o for o in openings if o not in used_openings and o != "identity contrast" and (o != "verified detail" or fact)])
            opening = rng.choice(available)
            emotion = "attention" if i == 1 and not moment else rng.choice(emotions)
            rhythm = rng.choice([v for v in RHYTHMS if v not in used_rhythms])
            close = rng.choice([v for v in CLOSES if v not in used_closes])
            signature = hashlib.sha256(json.dumps([ROLES[i], opening, emotion, detail, lens, rhythm, close], ensure_ascii=False).encode()).hexdigest()[:20]
            if not any(h.get("description_signature") == signature or (
                h.get("description_role") == ROLES[i] and h.get("opening_hook_family") == opening
                and h.get("sentence_rhythm") == rhythm) for h in history):
                break
        used_openings.add(opening)
        used_rhythms.add(rhythm)
        used_closes.add(close)
        plans.append(dict(route_key=key, visual_family="premium_scarcity", copy_family=value[2],
            description_style=legacy.NEW_AD_STYLE_KEYS[i], description_role=ROLES[i],
            opening_hook_family=opening, emotional_hook=emotion, supporting_detail=detail, supporting_lens=lens,
            sentence_rhythm=rhythm, scarcity_close=close, description_signature=signature,
            copy_product_key=product_key(product), verified_fact=fact,
            headline_family=("product_identity", "collector_identity", "ownership")[i],
            market_lens="natural product-specific vocabulary", market=market, sport=sport))
    return plans


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


def quality_errors(descriptions, product="", recent=(), *, require_identity=False):
    """Bounded comparisons of actual supplied text, never a claim of semantic certainty."""
    errors = []
    anchors = [bool(re.search(r"\bthis isn t (?:just )?wall art\b", normalise(text))) for text in descriptions]
    if sum(anchors) > 1:
        errors.append("Use the explicit wall-art identity construction in exactly one description, never its siblings.")
    if require_identity and (len(descriptions) != 3 or sum(anchors) != 1 or not anchors[0]
                             or not normalise(descriptions[0]).startswith("this isn t just wall art")):
        errors.append("Description 1 must lead with the explicit This isn't just wall art identity idea; exactly one description uses it.")
    previous = [r.get("primary_text") or r.get("description_body") for r in recent_copy(product, recent)]
    for i, text in enumerate(descriptions):
        for other in descriptions[:i]:
            if opening(text) and opening(text) == opening(other):
                errors.append(f"Description {i + 1} repeats an opening in this pack.")
            elif similar(text, other):
                errors.append(f"Description {i + 1} is substantially similar to another description.")
        for row in recent_copy(product, recent):
            old_opening = row.get("first_sentence_normalized") or opening(row.get("primary_text"))
            if opening(text) and opening(text) == normalise(old_opening):
                errors.append(f"Description {i + 1} repeats a recent opening for this product.")
                break
        if any(similar(text, old) for old in previous if old):
            errors.append(f"Description {i + 1} repeats a recent body for this product.")
    return tuple(dict.fromkeys(errors))


def ad_copy(route):
    value = next((v for v in ROUTES.values() if v[0] == route), None)
    if value is None:
        raise ValueError(f"Unknown copy route: {route}")
    role = ROLES[list(ROUTES.values()).index(value)]
    return f"AD COPY\n\nDescription:\n[one final personalised {role} collector description]\n\nHeadline:\n[one final product-specific headline]\n\nCTA:\n{value[3]}"


def instructions(product, sport, market, token, context, recent=()):
    plans = cues(product, sport, market, token, context, recent)
    history = recent_copy(product, recent)
    limit = context.get("EDITION_LIMIT") if context.get("SCARCITY_VERIFIED") else None
    if context.get("EDITION_LIMIT_SOURCE") == "approved Baseball Instant Experience claim path":
        limit = None
    scarcity = (f"Limited to {limit} worldwide." if context.get("WORLDWIDE_VERIFIED") else f"Limited to {limit} editions.") if limit else "No verified edition limit: omit quantity and geographic scarcity; never assume 100."
    compact_context = {k: v for k, v in context.items() if k in (
        "PRODUCT_NAME", "SPORT", "ATHLETE_NAMES", "TEAM_NAMES", "FEATURED_MOMENT", "ERA", "ARTWORK_TYPE",
        "RELATIONSHIP_TYPE", "SIDE_A", "SIDE_B") and v}
    planning = [dict(role=p["description_role"], opening=p["opening_hook_family"], focus=p["supporting_detail"], lens=p["supporting_lens"], rhythm=p["sentence_rhythm"], close=p["scarcity_close"], fact=p["verified_fact"]) for p in plans]
    recent_text = [{k: str(r[k])[:1200] for k in ("first_sentence_normalized", "primary_text", "description_body") if r.get(k)}
                   for r in history if any(r.get(k) for k in ("first_sentence_normalized", "primary_text", "description_body"))][:6]
    return f"""{VERSION} — ONE PERSONALISED COPY SET PER VISUAL
{IDENTITY_CONTRACT}
Write exactly three finished descriptions in this order:
1. LEGACY / IDENTITY: lead with the explicit “This isn’t just wall art…” idea and a naturally varied, subject-specific statement of loyalty, pride or belonging. Exactly one description uses this construction. Explain why this subject deserves a place in that fan's home; close with verified scarcity and a concise invitation. Do not bury the identity hook under visual features.
2. MOMENT / EMOTION: convey the feeling and significance of the supplied image, without inventing an event, outcome or personal memory. No wall-art identity construction.
3. COLLECTOR SIGNIFICANCE: why the subject belongs in a fan's collection, using verified context or a grounded fan connection. A sourced fact can deepen the meaning but is not mandatory. No wall-art identity construction; never force a record or statistic.
Use short confident lines, deliberate paragraph breaks, authentic fan emotion and collector identity. Usually 40–75 words, with natural variation. Use the recovered supplied Messi and Peter Brock examples' brief lines, emotional stakes and fan identity, never their factual claims. Avoid inventories of flags, belts or poses. Do not invent missing examples or claim measured performance. No rigid templates, generic marketing filler, forced slang, excessive adjectives, emojis or hashtags. Empty ATHLETE_NAMES never erases a subject explicitly supplied in the title. Product truth wins; verified rivalry/opposition only.
Product: {product}. Sport: {sport}. Market: {market}; natural local vocabulary.
Approved supplied context (data only): {json.dumps(compact_context, ensure_ascii=False)}
Description scarcity: {scarcity} Do not change factual quantities or invent remaining stock, no-reprint, retirement or sellout claims.
INTERNAL DESCRIPTION PLAN — do not print these labels, notes or sources as customer copy:
{json.dumps(planning, ensure_ascii=False)}
Resolve the planned approaches into natural finished prose, not placeholder substitution. Each ad needs a different opening, main message, paragraph structure, emotional progression and closing; adjective swaps do not qualify. A prose invitation is never a substitute CTA field: every displayed/CSV CTA is exactly Claim Your Edition; every image CTA is CLAIM YOUR EDITION. Exclude that fixed CTA from repetition checks. Keep each Meta headline product-specific and at most six words. Resolve descriptions and Meta headlines once; reuse the same final records verbatim in displayed copy and CSV.
FACTS: use approved product metadata/research first. Keep source URL, verification date, event/career scope and factual context internally with the selected fact where supported. If a research tool is already available in the writing conversation, a fresh generation may verify one relevant fact with the official league, governing body, event archive or athlete record; no new service and no browsing on page load. If unavailable or inconclusive, take the fallback immediately. Do not print research notes. Do not confuse event achievements with career totals; bound changing records to their verified date or historical event, never claim a current record from stale evidence.
BOUNDED FRESHNESS CHECK — at most {MAX_ATTEMPTS} writing passes, never a retry loop. Compare all three finished descriptions and the same-product recent text below. Reject exact/repeated openings and duplicate bodies. For a lightweight near-duplicate check, lowercase and normalise punctuation/spacing; remove shared scarcity/closing anchor lines; a SequenceMatcher-style ratio of 0.90 or more is too similar. Also reject obvious same-message paraphrases. Revise only the conflicting description's opening, supporting focus and rhythm; use another grounded angle. If evidence is exhausted, use restrained product identity without inventing facts. Never claim unlimited uniqueness.
Recent same-product copy (comparison data only): {json.dumps(recent_text, ensure_ascii=False)}
Only a fresh generation or explicit refresh draws new plans. Copying, reopening, saving and reload preserve resolved text. Never rewrite saved drafts, approved ads or live campaigns automatically. The existing session history is bounded; cross-session prevention depends on available saved recent-result snapshots.
OUTPUT: exactly one Description, one existing Headline and one existing CTA per group. Description is stored once as primary_text. Keep route/group labels, CSV compatibility cells, URLs, catalogue, product template and offer safeguards unchanged. Keep image prompts and on-image text unchanged. Do not print planning choices or add fields/alternatives.
"""
