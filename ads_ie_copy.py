"""New Instant Experience copy selection; visual rendering stays independent."""
import hashlib
import json

VERSION = "INSTANT EXPERIENCE COPY V2"
OUTPUT_MODE = "three_visual_copy_v2"
ROUTES = {
    "premium_scarcity_right": ("Premium Scarcity — Smart Hybrid", "Product-aware scarcity hero", "premium_scarcity_smart_hybrid", "Claim Your Edition"),
    "premium_scarcity_front": ("Private Gallery", "For the room that remembers", "private_gallery", "Secure Your Edition"),
    "premium_scarcity_left": ("The Cave", "Premium fan sanctuary", "the_cave", "Own This Edition"),
}
POOLS = (
    ("legacy_standard", "moment_pressure", "collector_pride", "identity_callout"),
    ("remembered_moment", "era_memory", "framed_greatness", "quiet_collector"),
    ("ownership_belonging", "generational_fandom", "identity_callout", "collector_pride"),
)


def cues(product, sport, market, token, context, recent=()):
    relationship = str(context.get("RELATIONSHIP_TYPE", "")).casefold()
    rivalry = relationship in {"rivalry", "opposition", "rivals"} or str(context.get("ARTWORK_TYPE", "")).casefold() in {"rivalry", "opposition"}
    lens = "identity_belonging" if market == "USA" else "supported_memory" if market == "Australia" else "existing_localisation"
    output = []
    for i, (key, (_, _, family, _)) in enumerate(ROUTES.items()):
        pool = list(POOLS[i])
        if rivalry:
            pool.append("rivalry_challenge")
        if str(context.get("ERA", "")).casefold() in {"current", "modern", "contemporary"}:
            pool = [hook for hook in pool if hook not in {"remembered_moment", "era_memory", "generational_fandom"}]
        digest = int(hashlib.sha256(f"{token}|{family}|{product}|{market}".encode()).hexdigest(), 16)
        prior = {r.get("opening_hook_family") for r in recent if r.get("market") == market and r.get("sport") == sport and r.get("visual_family") == family}
        choices = [hook for hook in pool if hook not in prior] or pool
        output.append(dict(route_key=key, visual_family=family, opening_hook_family=choices[digest % len(choices)],
                           headline_family=(("product_identity", "collector_ownership", "defining_phrase"), ("collector_meaning", "legacy_identity", "subject_preservation"), ("fan_identity", "belonging", "ownership_pride"))[i][(digest // 7) % 3],
                           sentence_rhythm=("short opening then flowing meaning", "two concise paragraphs", "recognition then ownership")[digest % 3],
                           scarcity_close=("brief finite-edition close", "collector availability close", "understated edition close")[(digest // 3) % 3],
                           market_lens=lens, market=market, sport=sport))
    return output


def ad_copy(route):
    value = next((v for v in ROUTES.values() if v[0] == route), None)
    if value is None:
        raise ValueError(f"Unknown copy route: {route}")
    return f"AD COPY\n\nDescription:\n[one final personalised description]\n\nHeadline:\n[one final complementary headline]\n\nCTA:\n{value[3]}"


def instructions(product, sport, market, token, context, recent=()):
    return f"""{VERSION} — ONE PERSONALISED COPY SET PER VISUAL
Return exactly THREE active ad-copy combinations total. Each group contains AD COPY with one Description, one Headline and one CTA. No copy tables, numbered description options, candidates, scores or reasoning.

PRODUCT UNDERSTANDING — MANDATORY BEFORE COPY
Read PRODUCT_NAME: {product}. Read structured metadata and inspect the attached artwork. Empty ATHLETE_NAMES or FEATURED_MOMENT fields do not erase identity explicitly supplied in the product title. Extract safe title identity anchors and clearly readable immutable artwork wording. Resolve principal subject, verified team/club, event/moment, supplied or visible era/date, verified rivalry, artwork title/defining phrase, collector facts, sport and market. Do not identify anyone solely by their face. Do not extrapolate affiliations, achievements, dates, relationships or viewer memories.
Resolved supplied context:
{json.dumps(context, ensure_ascii=False, indent=2)}

OPTIONAL MICRO-RESEARCH — INTERNAL CONTEXT ONLY
If browsing is available, use at most 2–4 focused searches on product name, principal subject, sport and supplied event/era. Prefer official league, team, athlete and hall-of-fame sources or reputable sports sources. Find only a few contextual anchors to inform fan vocabulary, emotional angle, era understanding and identity versus nostalgia. External research cannot override the factual wording gate. Do not automatically insert new web facts: customer-facing claims require supplied title, metadata, clearly readable artwork or an explicitly approved claim path. No research report or citations inside Description, Headline or CTA. If browsing is unavailable, continue from supplied context.

INTERNAL COPY-ANGLE LIBRARY
Retain Legacy Standard, Framed Greatness, nostalgia, fan identity, legacy, collector ownership, remembered moment, quiet collector and scarcity close as writing patterns, never user-visible options. Choose-a-Side / rivalry_challenge is permitted ONLY with verified rivalry/opposition or two explicitly supplied opposing sides. Never infer rivalry from multiple names or use it for a single athlete. If a selected cue conflicts with product truth, choose the strongest fact-safe cue in that route's job.

ROUTE COPY JOBS
Smart Hybrid: CONVERSION + COLLECTOR URGENCY + PRODUCT MEANING. Explain why this specific product matters, then truthful scarcity. WHY BUY NOW. Add meaning instead of repeating the image headline. Product/collector headline. CTA exactly Claim Your Edition.
Private Gallery: MEMORY + LEGACY + COLLECTOR PRESTIGE. WHY REMEMBER IT. Connect the supplied subject/era with collector preservation; no invented historical moment, no furniture or generic interior-design copy. Complement FOR THE ROOM THAT REMEMBERS. with a personalised memory/legacy headline. CTA exactly Secure Your Edition.
The Cave: FAN IDENTITY + BELONGING + OWNERSHIP. WHAT OWNING IT SAYS ABOUT ME. Show loyalty to this supplied subject, collector pride and what made the sport theirs without inventing a viewer biography. Complement the image with an identity/ownership headline. CTA exactly Own This Edition.

MARKET EMOTIONAL LENS — {market}
USA: generally favour identity, belonging, loyalty, fan ownership and recognition. Historic American subjects can lead with nostalgia when product truth makes it stronger. Never invent a team/city relationship or force patriotism/America language.
Australia: favour nostalgia, remembered moments, era and shared sporting memory for verified historical subjects. Current Australian athletes without historical context fall back to identity and collector ownership. Never invent where the viewer was, childhood, TV channel, pub, suburb, race, weekend or summer. Other markets retain existing localisation. These are creative priors, not facts or stereotypes; product truth always wins.

CONTROLLED FRESHNESS
CREATIVE_VARIATION_TOKEN: {token}
Route cues derived deterministically from token + visual family + product identity + market:
{json.dumps(cues(product, sport, market, token, context, recent), ensure_ascii=False, indent=2)}
Recent same-market/sport copy fingerprints:
{json.dumps([r for r in recent if r.get('market') == market and r.get('sport') == sport], ensure_ascii=False)}
Vary opening-hook family, rhythm, emotional entry, headline structure, secondary phrase and scarcity closing. Never randomise synonyms, verified facts, identity or edition limits. Avoid recent exact headlines, opening sentences and hook families where suitable; do not weaken specificity just for novelty. Freshness applies to new packages only, never rewrite live winning ads.

INTERNAL SELECTION AND FINAL REVIEW
Silently consider several approaches and select one winner per route for product specificity, factual safety, visual alignment, market fit, fan authenticity, mobile readability and distinction from siblings/recent copy. Return only winners.
Descriptions normally 35–65 words, slightly shorter if stronger. Use short paragraphs, intentional mobile line breaks, natural restrained fan language and one idea per paragraph. Each description needs a meaningful verified product anchor; reject copy that could fit five unrelated products unchanged. Three different opening sentences and emotional propositions, three different complementary headlines, at most six words each (normally 4–6).
No generic luxury language, marketing essays, fake quotes, emojis, hashtags, excessive questions, Transform your space, Elevate your room, Perfect addition or Man cave must-have. Do not repeat the image text verbatim.
Use Limited to {{verified limit}}., Only {{verified limit}} exist., or Only {{verified limit}} editions. Never append worldwide or world wide. Without verified edition facts, use fact-safe non-numeric collector wording without inventing limited status. Never invent remaining stock, numbering, no reprint, no second run, retirement or sellout timing; those require existing verified claim paths.
One approved CTA per ad, no alternatives. Native Meta Instant Experience button remains Shop Now. Preserve exact URL parameters, product template, catalogue and offer safeguards. Do not put this Meta description or headline on the images; retain the existing image prompts unchanged.
"""
