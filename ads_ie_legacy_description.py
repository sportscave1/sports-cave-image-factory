"""Description style rules recovered from ads_page.py at 844a0c5.

Historical numbered option headings are unnumbered here: styles are an internal
library, not additional output rows. No historical fallback claims are generated.
"""

VERSION = "WINNER REFINEMENT LEGACY DESCRIPTION STYLE V1"

HISTORICAL_STYLES = """Legacy Standard:
- Four short opening lines establishing the safe relationship or product meaning.
- Blank line.
- "This isn't wall art."
- One short representation line.
- Blank line.
- Verified scarcity in two short lines.
- Blank line.
- "Secure yours."
- Do not use "They didn't compete" for real rivals.
- Use singular language for a single athlete. Use female pronouns only when verified.

Framed Greatness:
- One short greatness/framed hook.
- Blank line.
- Two collector-identity lines.
- Blank line.
- Three short scarcity lines.
- Blank line.
- "Secure yours."
- Prefer "Greatness doesn't fade. It gets framed." unless a rivalry, historic moment or motorsport hook is more product-accurate.

Choose a Side:
- A short question or fan-identity challenge.
- Blank line.
- One sharp response.
- Blank line.
- A second athlete, team, moment or identity question.
- Blank line.
- A line showing the fan already knows their answer.
- Blank line.
- Verified scarcity.
- Blank line.
- A two-line ownership challenge.
- Use rivalry framing only when ARTWORK_TYPE or RELATIONSHIP_TYPE verifies rivalry/opposition.
"""


def build_description_style_rules():
    return f"""{VERSION}
RESTORED SPORTS CAVE INSTANT EXPERIENCE DESCRIPTION STYLE
Choose the historical framework that best fits the winning ad and verified product. Use it for one finished description per ad. The three ads remain close siblings: do not force a different framework or emotional proposition onto each sibling. Keep the winner's hook and meaning; restore concise Sports Cave wording, not explanatory marketing prose.

{HISTORICAL_STYLES}

HISTORICAL CHOOSE-A-SIDE ADAPTATION
This was not a generic third slogan. For verified rivalry/opposition use the supplied sides, a question, "No middle ground.", "You already picked a side.", verified scarcity and "Choose it…\nor watch it end up on someone else's wall."
For a single athlete, use the supplied subject: "You know the name."; use "You remember." only with a supported moment, then "No explanation needed." and the historical "Claim it…\nor watch it end up on someone else's wall." close.
For verified connected legends the original contrast was "Wrong question." rather than invented rivalry. Team, historic-moment and motorsport variants must follow verified product context. Never invent a relationship, mountain, race, viewer memory or nostalgia merely to reproduce an old example. Choose another historical framework if this one does not fit the winner.

APPLICATION TO THE EXISTING SINGLE-COPY CONTRACT
Return only the selected finished wording. Never print these three templates as three options under one ad. Each ad has exactly one primary text, one headline and one Instant Experience description: Primary Text / Description is the existing shared copy field, stored once in primary_text, not two alternative versions or a new CSV column. Exactly three complete ad combinations total.
Use short, strong, collector-led lines and intentional blank lines; approximately 35–65 words only when useful, never pad. Preserve "This isn't wall art.", "Greatness doesn't fade. It gets framed." and "Secure yours." where the selected historical framework calls for them. No generic ecommerce explanation, bloated sentences or AI luxury language. The description's closing words do not replace the existing CTA field.
Keep current factual safeguards: supplied identity only, rivalry only when verified, exact verified edition limit, no invented remaining stock, no reprint, no second run or retirement. Never append worldwide or world wide to scarcity. Do not change the winning urgency, scarcity style, headline count, image briefs, CSV identities or output row count.
"""


# New Ads uses all three historical frameworks in fixed slot order. The winner
# refinement helper above deliberately retains its existing selection behaviour.
NEW_AD_STYLE_KEYS = ("legacy_standard", "framed_greatness", "choose_a_side")
NEW_AD_TEMPLATES = (
    """[SUBJECT / ATHLETE / TEAM].
[DEFINING MOMENT / PRODUCT IDENTITY].
[SHORT EMOTIONAL OR SPORT-SPECIFIC LINE].
Made for {sport} collectors.

This isn't wall art.
It's a statement of {identity} identity.

Limited to {limit} worldwide.
Made for fans who know why it matters.

Secure yours.""",
    """Greatness doesn't fade.
It gets framed.

[ATHLETE / TEAM / MOMENT].
[SHORT LINE CONNECTING THE PRODUCT TO THE COLLECTOR].

Made for collectors who want their {sport} identity on display.

Limited to {limit} worldwide.
Built for serious collectors.
Made for fans who know why it matters.

Secure yours.""",
    """What deserves the centre of your {sport} wall?

Something that actually means something.

[PRODUCT / SUBJECT / MOMENT]
or another forgettable {comparison} print?

You already know the answer.

Only {limit} exist.

Claim this edition for your collection…
or leave it for another collector.""",
)


def new_ad_sport_language(sport, context):
    """Natural category vocabulary, never an inferred sporting fact."""
    key = str(sport or "").strip().casefold()
    if key in {"nba", "basketball"}:
        words = ("basketball", "basketball", "basketball")
    elif key in {"nfl", "football", "nrl", "afl", "rugby", "rugby league", "rugby union"}:
        name = "football" if key in {"nfl", "football", "afl"} else "rugby"
        words = (name, name, name)
    elif key in {"motorsport", "formula one", "formula 1", "f1"}:
        words = ("motorsport", "racing", "racing")
    elif key in {"cricket", "baseball", "tennis", "golf", "hockey"}:
        words = (key, key, key)
    elif key in {"horse racing", "horse-racing", "racing"}:
        words = ("racing", "racing", "racing")
    else:
        words = ("sports", "sporting", "sports")
    if str(context.get("ARTWORK_TYPE", "")).casefold() in {"team", "team product", "single team"}:
        return (words[0], "club", "team")
    return words


def build_new_ad_style_rules(product, sport, context):
    sport_word, identity, comparison = new_ad_sport_language(sport, context)
    # User-approved New Ads copy baseline is 100; explicit verified facts win.
    limit = context.get("EDITION_LIMIT") or 100
    blocks = []
    for index, (key, template, cta) in enumerate(zip(
        NEW_AD_STYLE_KEYS, NEW_AD_TEMPLATES,
        ("Claim Your Edition", "Secure Your Edition", "Own This Edition"),
    ), 1):
        body = template.format(sport=sport_word, identity=identity, comparison=comparison, limit=limit)
        blocks.append(f"AD {index} — {key}\nDescription framework:\n{body}\n\nHeadline: ONE short product-specific collector/ownership headline.\nCTA: {cta}")
    return f"""LOCKED SPORTS CAVE LEGACY COPY FRAMEWORKS — NEW ADS ONLY
Product being personalised: {product}
Use exactly one framework per creative in this permanent order: legacy_standard, framed_greatness, choose_a_side. These are the three copy styles, not three options for each image.

{chr(10).join(chr(10) + block + chr(10) for block in blocks)}

PRODUCT ADAPTATION
Resolve bracketed writing cues using the supplied title, athlete/team, product identity, moment, sport, event, rivalry, era and market where available. Never print brackets or unresolved placeholders. Omit an unavailable factual line or replace it with a short product-identity line; never invent achievements, events, years, relationships or viewer memories. Empty ATHLETE_NAMES does not erase a name explicitly supplied in the title. Write naturally, not as mechanical placeholder substitution. For team artwork use club/fan identity where natural. For awkward categories use sporting identity or fan identity.
The defining hooks and short-line/blank-line structure are locked. legacy_standard preserves "This isn't wall art."; framed_greatness always opens "Greatness doesn't fade.\nIt gets framed." including motorsport; choose_a_side always uses the collector challenge, product-versus-forgettable-print choice, "You already know the answer.", and two-line ownership close. Choose-a-Side is valid for every product; athlete-versus-athlete rivalry requires verified rivalry/opposition and must never be invented. Do not substitute three random advertising concepts.

DESCRIPTION SCARCITY ONLY
The user-approved catalogue copy baseline is Limited to 100 worldwide. / Only 100 exist. Use that 100-edition baseline unless a separately supplied verified edition limit explicitly differs, in which case use its exact value. Do not invent other quantities, remaining stock, near-sellout claims, countdowns, discounts, percentages, numbered status, no reprint or retirement. Worldwide belongs to these descriptions only; do not transfer it or the description wording into the unchanged image prompts.

FINAL COPY CONTRACT
Return exactly THREE active ad-copy combinations total. Each group contains AD COPY with one Description, one Headline and one CTA. No extra options or tables. Preserve intentional short lines and blank lines; concise, collector-first, confident, premium, emotional without filler. Nostalgia only where product truth supports it. No perfect for, elevate your space, transform your room, generic home-decor language, corporate explanation, emojis or excessive exclamation marks. Keep each headline product-specific and at most six words. One approved CTA per ad, no alternatives. Native Meta Instant Experience button remains Shop Now.
The three style keys are unchanged. CSV description identity cells and variation=1 are compatibility fields: preserve the exported template cells exactly, even where an existing single-copy row uses legacy_standard. They do not override the slot's assigned writing framework. No new CSV columns, rows or image instructions.
"""
