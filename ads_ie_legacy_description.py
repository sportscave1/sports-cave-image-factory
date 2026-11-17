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


DESCRIPTION_WORDING_INSTRUCTIONS = """WORDING WITHIN THE EXISTING DESCRIPTION STYLE — NEW GENERATION ONLY
Keep each existing or explicitly selected description style, slot order, structure, short-line and blank-line pattern, rhythm, approximate length, distinct approach, signature phrases, approved scarcity wording and existing CTA unchanged. Improve only the product-specific wording inside the available supporting lines. Never replace the three styles with one shared storytelling formula, add narrative paragraphs or assign a new style.
Use supplied product details, artwork and approved research to connect those lines to the exact athlete/team, depicted sporting story and why its supporters care. Make the emotional payoff concrete: the mentality a supporter admires, the meaning of this verified moment or relationship, or the allegiance it represents. Use plain, confident words; no generic praise, interchangeable motivation, invented quotes, rivalries, achievements, comeback stories or personal memories. When context is missing, use grounded subject/fan identity within the same line structure, not an invented story.
For Legacy Standard, strengthen the subject/moment opening and identity payoff around the existing “This isn't wall art.” anchor. For Framed Greatness, strengthen the subject-to-collector connection within its existing framed-greatness hook and collector lines. For Choose a Side, make the existing collector choice matter through the exact subject; retain its question/response rhythm, answer line and ownership close, without inventing athlete-versus-athlete rivalry. These are refinements only when that framework is already selected, never instructions to reassign styles.
The written headline's emotional angle must fit its assigned description style. Reassign the internal headline angle when necessary, never restructure the description to fit the headline. Keep all signature and fixed template lines verbatim, including “This isn't wall art.”, “Greatness doesn't fade.”, “It gets framed.”, “You already know the answer.” and the selected closing lines wherever the existing format uses them.
Before returning copy, compare each description with its assigned framework: same ordered line/paragraph roles and approximate length, same signature/scarcity/CTA wording, stronger product-specific meaning in the flexible lines. Keep the three approaches distinct. Do not print this check or add output fields. Apply only to fresh generation or explicitly requested regeneration; never rewrite existing saved ads. Images, on-image text, generation count, formats, CSV and export behaviour remain unchanged.
"""


def build_description_style_rules():
    return f"""{VERSION}
Always describe the product as an ‘edition’, never ‘artwork’; use ‘edition’ or ‘editions’ wherever you would otherwise use ‘artwork’ or ‘artworks’.
RESTORED SPORTS CAVE INSTANT EXPERIENCE DESCRIPTION STYLE
Choose the historical framework that best fits the winning ad and verified product. Use it for one finished description per ad. The three ads remain close siblings: do not force a different framework or emotional proposition onto each sibling. Keep the winner's hook and meaning; restore concise Sports Cave wording, not explanatory marketing prose.

{HISTORICAL_STYLES}

{DESCRIPTION_WORDING_INSTRUCTIONS}

HISTORICAL CHOOSE-A-SIDE ADAPTATION
This was not a generic third slogan. For verified rivalry/opposition use the supplied sides, a question, "No middle ground.", "You already picked a side.", verified scarcity and "Choose it…\nor watch it end up on someone else's wall."
For a single athlete, use the supplied subject: "You know the name."; use "You remember." only with a supported moment, then "No explanation needed." and the historical "Claim it…\nor watch it end up on someone else's wall." close.
For verified connected legends the original contrast was "Wrong question." rather than invented rivalry. Team, historic-moment and motorsport variants must follow verified product context. Never invent a relationship, mountain, race, viewer memory or nostalgia merely to reproduce an old example. Choose another historical framework if this one does not fit the winner.

APPLICATION TO THE EXISTING SINGLE-COPY CONTRACT
Return only the selected finished wording. Never print these three templates as three options under one ad. Each ad has exactly one primary text, one headline and one Instant Experience description: Primary Text / Description is the existing shared copy field, stored once in primary_text, not two alternative versions or a new CSV column. Exactly three complete ad combinations total.
Use short, strong, collector-led lines and intentional blank lines; approximately 35–65 words only when useful, never pad. Preserve "This isn't wall art.", "Greatness doesn't fade. It gets framed." and "Secure yours." where the selected historical framework calls for them. No generic ecommerce explanation, bloated sentences or AI luxury language. The description's closing words do not replace the existing CTA field.
Keep current factual safeguards: supplied identity only, rivalry only when verified, owner-confirmed 100 worldwide edition limit, no invented remaining stock, no reprint, no second run or retirement. The 100 worldwide edition limit is owner-confirmed and needs no additional verification or confirmation. Do not change the winning urgency, scarcity style, headline count, image briefs, CSV identities or output row count.
"""


# New Ads uses all three historical frameworks in fixed slot order. The winner
# refinement helper above deliberately retains its existing selection behaviour.
NEW_AD_STYLE_KEYS = ("legacy_standard", "framed_greatness", "choose_a_side")
NEW_AD_TEMPLATES = (
    """[SUBJECT / ATHLETE / TEAM].
[DEFINING MOMENT / PRODUCT IDENTITY].
[SHORT EMOTIONAL OR SPORT-SPECIFIC LINE].
Made for collectors.

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
    """Every collection needs a centrepiece.
Only {limit} collectors can own this one.

[PRODUCT / SUBJECT / MOMENT].
[SHORT PRODUCT-SPECIFIC LINE EVOKING ITS VERIFIED ERA, SPORTING MEANING OR SUPPORTER CONNECTION].

[SHORT EMOTIONAL LINE SHOWING WHY THIS EDITION BELONGS IN THIS COLLECTOR'S COLLECTION].

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
    limit = 100  # Owner-confirmed worldwide edition policy.
    scarcity = "Limited to 100 worldwide."

    blocks = []
    for index, (key, template, cta) in enumerate(zip(
        NEW_AD_STYLE_KEYS, NEW_AD_TEMPLATES,
        ("Claim Your Edition",) * 3,
    ), 1):
        body = template.format(sport=sport_word, identity=identity, comparison=comparison, limit=limit)
        body = body.replace(f"Limited to {limit} worldwide.", scarcity)
        if not limit:
            body = body.replace(f"Only {limit} exist.", "")
        headline_rule = "ONE short product-specific emotional headline fitted to this description style."
        if index == 3:
            headline_rule += " For this collector-centrepiece description, make the written Meta headline collector-focused: express why this exact subject, verified sporting memory or legacy deserves a lasting place in a meaningful collection. Add a complementary emotional idea rather than repeating or paraphrasing the opening, centrepiece wording or 100-collector scarcity claim. Keep it premium, natural and product-specific, with nostalgia only where supported; no generic collector slogan or purchase CTA. This is the third written headline only, in every market; preserve the description and all on-image headline assignments."
        blocks.append(f"AD {index} — {key}\nDescription framework:\n{body}\n\nHeadline: {headline_rule}\nCTA: {cta}")
    return f"""LOCKED SPORTS CAVE LEGACY COPY FRAMEWORKS — NEW ADS ONLY
Always describe the product as an ‘edition’, never ‘artwork’; use ‘edition’ or ‘editions’ wherever you would otherwise use ‘artwork’ or ‘artworks’.
Product being personalised: {product}
Use exactly one framework per creative in this permanent order: legacy_standard, framed_greatness, choose_a_side. These are the three copy styles, not three options for each image.

{chr(10).join(chr(10) + block + chr(10) for block in blocks)}

{DESCRIPTION_WORDING_INSTRUCTIONS}

THIRD DESCRIPTION — COLLECTOR CENTREPIECE OVERRIDE
For New Ads slot 3 only, the choose_a_side compatibility key now uses the collector-centrepiece framework printed above. This replaces the old question/response, forgettable-print comparison and answer-line requirements for this slot. Open verbatim with "Every collection needs a centrepiece. Only 100 collectors can own this one." on the two short lines shown. Never use the old wall-centre question, "Something that actually means something.", "or another forgettable ... print?" or "You already know the answer." in this slot. Keep the two-line ownership close. Make the flexible lines nostalgic and emotional through this exact subject, verified era or sporting moment and its meaning to supporters; when no historical moment is supplied, use grounded fan connection without inventing memories. Connect that feeling to owning this limited edition as a meaningful premium collector piece, not generic luxury or home-decor language. Slots 1 and 2 retain all existing rules.

PRODUCT ADAPTATION
Resolve bracketed writing cues using the supplied title, athlete/team, product identity, moment, sport, event, rivalry, era and market where available. Never print brackets or unresolved placeholders. Omit an unavailable factual line or replace it with a short product-identity line; never invent achievements, events, years, relationships or viewer memories. Empty ATHLETE_NAMES does not erase a name explicitly supplied in the title. Write naturally, not as mechanical placeholder substitution. For team edition use club/fan identity where natural. For awkward categories use sporting identity or fan identity.
The defining hooks and short-line/blank-line structure are locked. legacy_standard preserves "This isn't wall art."; framed_greatness always opens "Greatness doesn't fade.\nIt gets framed." including motorsport; choose_a_side uses the collector-centrepiece opening, product-specific emotional supporting lines and two-line ownership close defined above. Choose-a-Side is valid for every product; athlete-versus-athlete rivalry requires verified rivalry/opposition and must never be invented. Do not substitute three random advertising concepts.

DESCRIPTION SCARCITY ONLY
All Sports Cave editions are owner-confirmed as limited to 100 worldwide. Use this approved claim without verification flags, blocking or confirmation questions. Do not invent remaining stock, near-sellout claims, countdowns, discounts, percentages, numbered status, no reprint or retirement. Description wording must not alter the selected image footer.

FINAL COPY CONTRACT
Return exactly THREE active ad-copy combinations total. Each group contains AD COPY with one Description, one Headline and one CTA. No extra options or tables. Preserve intentional short lines and blank lines; concise, collector-first, confident, premium, emotional without filler. Nostalgia only where product truth supports it. No perfect for, elevate your space, transform your room, generic home-decor language, corporate explanation, emojis or excessive exclamation marks. Keep each headline product-specific; aim for 2–6 words, preferring natural phrasing over a rigid count. One approved CTA per ad, no alternatives. Native Meta Instant Experience button remains Shop Now.
The three style keys are unchanged. CSV description identity cells and variation=1 are compatibility fields: preserve the exported template cells exactly, even where an existing single-copy row uses legacy_standard. They do not override the slot's assigned writing framework. No new CSV columns, rows or image instructions.
"""
