import re

import streamlit as st


CATEGORY_OPTIONS = [
    "Select category",
    "NBA",
    "Motorsport",
    "Football",
    "Cricket",
    "Horse Racing",
    "Baseball",
    "Combat",
    "Ice Hockey",
    "NFL",
    "Tennis",
]

COUNTRY_OPTIONS = [
    "Select country",
    "Australia",
    "USA",
    "UK",
    "Canada",
    "New Zealand",
]

CAMPAIGN_TYPE_OPTIONS = [
    "Select campaign type",
    "Carousel",
    "Instant Experience",
    "Single Image / Video",
]

CAROUSEL_CARD_MAX_CHARACTERS = 17
CAROUSEL_CARD_COUNT = 5

BANNED_GENERIC_CAROUSEL_PHRASES = (
    "History Framed",
    "Those Who Know",
    "Claim The Wall",
    "Collector Legacy",
    "Iconic Moment",
    "Built For Fans",
    "Made For Fans",
    "Man Cave Must Have",
    "Own The Moment",
    "Legendary Art",
    "Sports Glory",
    "Wall Worthy",
    "Premium Piece",
)

SCARCITY_TERMS = (
    "only",
    "limited",
    "edition",
    "editions",
    "numbered",
    "scarce",
    "scarcity",
    "no second run",
    "second run",
    "100",
)

CATEGORY_COPY_CUES = {
    "Motorsport": "circuit, machine, rivalry, pressure, noise, era, mountain and race memory",
    "AFL": "club era, captaincy, rivalry, finals pressure, jumper pride and matchday memory",
    "Cricket": "crease, spell, innings, summer, Ashes, ground, session pressure and era",
    "NBA": "mentality, rivalry, dynasty, final shot, court presence and legacy",
    "Baseball": "diamond, home run, October, rivalry, ballpark memory and legacy",
    "NFL": "Sunday pressure, franchise era, rivalry, quarterback moment, gridiron memory and legacy",
    "Football": "matchday, captain, final, club era, rivalry, last dance and terrace memory",
    "Golf": "major pressure, Sunday calm, fairway memory, champion rhythm and clubhouse legacy",
    "Tennis": "court pressure, final set, rivalry, grass or hardcourt era and champion poise",
    "Combat": "walkout, fight night, rivalry, discipline, pressure, legacy and champion mentality",
    "Horse Racing": "track, cup day, final straight, stable pride, racing era and winning memory",
    "Ice Hockey": "rink pressure, playoff moment, rivalry, captaincy, cold arena noise and legacy",
}

SUPPORTED_TEMPLATES = {
    ("Motorsport", "Carousel"): "motorsport_carousel",
}

TEMPLATES_WITH_PRIMARY_TEXT_VARIATIONS = {
    "motorsport_carousel",
}

IMAGE_ORDER = [
    ("Hero", "Cleanest, strongest front-facing product mockup."),
    ("Story", "A mockup that supports the race, rivalry, driver, car or historic moment."),
    ("Collector", "Premium room, gallery, office or close wall presentation."),
    ("The Cave", "Man cave, home bar, garage or masculine collector setting."),
    ("Scarcity", "Artwork close-up, edition badge, plaque or numbered-run detail."),
]

META_BUILD_ORDER = [
    "Create a Carousel ad.",
    "Upload the five mockups in the displayed order.",
    "Paste one generated headline and description into each matching card.",
    "Add the five primary-text variations and allow Meta to test them.",
]


def _clean_product_name(product_name):
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", product_name or "").strip()


def validate_ads_inputs(product_name, category, country, campaign_type):
    if not _clean_product_name(product_name):
        return "Enter a product name and choose a category, country and campaign type."
    if category == "Select category" or country == "Select country" or campaign_type == "Select campaign type":
        return "Enter a product name and choose a category, country and campaign type."
    return ""


def get_template_key(category, campaign_type):
    return SUPPORTED_TEMPLATES.get((category, campaign_type))


def normalize_carousel_field(value):
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_phrase(value):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", value.casefold())).strip()


def is_banned_generic_carousel_phrase(value):
    return normalize_phrase(value) in {
        normalize_phrase(phrase) for phrase in BANNED_GENERIC_CAROUSEL_PHRASES
    }


def card_uses_scarcity(card):
    combined = normalize_phrase(
        f"{card.get('headline', '')} {card.get('description', '')}"
    )
    return any(term in combined for term in SCARCITY_TERMS)


def validate_carousel_cards(cards, *, edition_info_supplied=False):
    errors = []
    if len(cards or []) != CAROUSEL_CARD_COUNT:
        errors.append(f"Carousel output must contain exactly {CAROUSEL_CARD_COUNT} cards.")
        return errors

    seen_headlines = set()
    seen_descriptions = set()
    for index, card in enumerate(cards, start=1):
        headline = normalize_carousel_field(card.get("headline", ""))
        description = normalize_carousel_field(card.get("description", ""))
        fields = (("headline", headline), ("description", description))
        for field_name, value in fields:
            label = f"Card {index} {field_name}"
            if not value:
                errors.append(f"{label} is blank.")
            if len(value) > CAROUSEL_CARD_MAX_CHARACTERS:
                errors.append(
                    f"{label} exceeds {CAROUSEL_CARD_MAX_CHARACTERS} characters."
                )
            if "," in value:
                errors.append(f"{label} contains a comma.")
            if "." in value:
                errors.append(f"{label} contains a full stop.")
            if is_banned_generic_carousel_phrase(value):
                errors.append(f"{label} uses banned generic filler: {value}.")

        normalized_headline = normalize_phrase(headline)
        normalized_description = normalize_phrase(description)
        if normalized_headline in seen_headlines:
            errors.append(f"Card {index} headline duplicates another headline.")
        if normalized_description in seen_descriptions:
            errors.append(f"Card {index} description duplicates another description.")
        seen_headlines.add(normalized_headline)
        seen_descriptions.add(normalized_description)

        if index == CAROUSEL_CARD_COUNT and card_uses_scarcity(card) and not edition_info_supplied:
            errors.append("Card 5 uses scarcity without supplied edition information.")

    return errors


def parse_carousel_cards(output_text):
    cards = []
    card_pattern = re.compile(
        r"Card\s+(\d+)\s*[\r\n]+Headline:\s*(.*?)\s*[\r\n]+Description:\s*(.*?)(?=\s*[\r\n]+Card\s+\d+|\s*[\r\n]+PRIMARY TEXT|\Z)",
        re.IGNORECASE | re.DOTALL,
    )
    for match in card_pattern.finditer(output_text or ""):
        cards.append(
            {
                "card": int(match.group(1)),
                "headline": normalize_carousel_field(match.group(2)),
                "description": normalize_carousel_field(match.group(3)),
            }
        )
    return sorted(cards, key=lambda card: card["card"])


def build_carousel_repair_instruction(errors):
    if not errors:
        return ""
    error_lines = "\n".join(f"- {error}" for error in errors)
    return f"""Rewrite only the invalid carousel-card fields below while preserving the five-card connected story.

Do not silently truncate text. Replace invalid fields with natural one-to-three-word alternatives that fit the product.

Validation issues:
{error_lines}"""


def build_category_specific_carousel_cues(category):
    category = category if category in CATEGORY_COPY_CUES else "the selected sport"
    cues = CATEGORY_COPY_CUES.get(category, "category-specific people, rivalries, venues, eras, pressure and fan memory")
    return f"""Category adaptation:

- For {category}, favour language drawn from {cues}.
- Only use a cue when it is supported by the product name, supplied details or visible artwork text.
- Do not hardcode examples or famous names from another product.
- Keep each card tied to the actual supplied product rather than the category in general."""


def build_carousel_story_and_specificity_rules(category):
    category_cues = build_category_specific_carousel_cues(category)
    banned_phrases = "\n".join(f"- {phrase}" for phrase in BANNED_GENERIC_CAROUSEL_PHRASES)
    return f"""CONNECTED STORY STRUCTURE

Create exactly {CAROUSEL_CARD_COUNT} carousel cards.

The five cards must read as one deliberate sequence:

Card 1 Hero Identity
- Lead with the strongest supplied identity: athlete, driver, rivalry, artwork title, car, team, era or defining product idea.

Card 2 Memory Anchor
- Trigger the specific memory using a confirmed circuit, year, era, rivalry, machine, match, race pressure, venue or atmosphere.

Card 3 Collector Meaning
- Turn the memory into emotional meaning. Make history, era or legacy specific to this product.

Card 4 Ownership
- Make the viewer imagine owning and displaying the piece. Sell identity, pride and presence before mentioning the room.
- It may reference a collector wall, office, garage, home bar or man cave, but it must not sound like cheap decor advertising.

Card 5 Real Scarcity
- Use only confirmed scarcity. For Sports Cave numbered editions, use the edition of 100 and no second run.
- Do not invent scarcity when it has not been supplied.

PRODUCT SPECIFICITY TEST

- At least four of the five card pairs must include a product-specific anchor across the headline or description.
- A product-specific anchor may be a supplied person name, artwork title, confirmed circuit, confirmed year, rivalry, car identity, era or product-specific phrase.
- Every card pair must pass this test: could this card be copied unchanged onto an unrelated sports artwork?
- If yes, rewrite it.
- Do not force the full product name onto multiple cards. Use different pieces of supplied identity across the sequence.

QUALITY SELECTION

- Silently create multiple candidate options for each card.
- Choose the strongest connected five-card combination.
- Do not output rejected alternatives.
- The final sequence must feel connected, avoid repetition, become progressively more emotional and finish with credible scarcity.

GENERIC FILLER TO REJECT UNLESS CLEARLY MODIFIED BY PRODUCT-SPECIFIC IDENTITY

{banned_phrases}

{category_cues}"""


def build_carousel_card_copy_rules():
    return f"""Headline rules:

- Maximum {CAROUSEL_CARD_MAX_CHARACTERS} characters including spaces.
- Aim for one to three short words.
- Must be clear on mobile.
- Do not use commas.
- Do not use full stops.
- No emojis.
- No all-capital shouting.
- Do not repeat another card headline.
- Do not repeat the product title on every card.
- Do not repeat Limited Edition on every card.
- Do not use generic filler.

Description rules:

- Maximum {CAROUSEL_CARD_MAX_CHARACTERS} characters including spaces.
- Aim for one to three short words.
- Must support rather than repeat the headline.
- Do not use commas.
- Do not use full stops.
- No emojis.
- Do not repeat another card description.
- Do not use generic filler."""


def build_carousel_final_quality_check(include_primary_text_variations=False):
    primary_text_line = "- Exactly five primary-text variations where required."
    if include_primary_text_variations:
        primary_text_line = "- Exactly five primary-text variations."
    return f"""Before answering count every headline and description including spaces. Rewrite any carousel field that exceeds {CAROUSEL_CARD_MAX_CHARACTERS} characters or contains a comma or full stop.

Final quality check before answering:

- Exactly five carousel cards.
{primary_text_line}
- Every carousel headline is {CAROUSEL_CARD_MAX_CHARACTERS} characters or fewer including spaces.
- Every carousel description is {CAROUSEL_CARD_MAX_CHARACTERS} characters or fewer including spaces.
- No carousel headline contains a comma.
- No carousel headline contains a full stop.
- No carousel description contains a comma.
- No carousel description contains a full stop.
- No duplicate carousel headlines.
- No duplicate carousel descriptions.
- No generic filler.
- At least four card pairs include a product-specific anchor.
- Every card pair is specific enough that it cannot be copied unchanged onto unrelated sports artwork.
- The cards flow as one connected story progression.
- Card 5 uses real scarcity only.
- The five primary texts use different selling angles.
- No unsupported facts have been invented.
- If any check fails, rewrite the invalid carousel fields before answering."""


def apply_campaign_copy_rule_blocks(prompt, campaign_type, include_primary_text_variations=False, category=None):
    if campaign_type != "Carousel" or not prompt:
        return prompt

    story_rules = build_carousel_story_and_specificity_rules(category)
    card_rules = build_carousel_card_copy_rules()
    final_quality_check = build_carousel_final_quality_check(
        include_primary_text_variations=include_primary_text_variations
    )
    if story_rules not in prompt:
        prompt = f"{prompt.rstrip()}\n\n{story_rules}"
    if card_rules not in prompt:
        prompt = f"{prompt.rstrip()}\n\nCAROUSEL COPY RULES\n\n{card_rules}"
    if final_quality_check not in prompt:
        prompt = f"{prompt.rstrip()}\n\n{final_quality_check}"
    return prompt


def build_motorsport_carousel_prompt(product_name, category, country, campaign_type):
    product_name = _clean_product_name(product_name)
    carousel_story_rules = build_carousel_story_and_specificity_rules(category)
    carousel_card_copy_rules = build_carousel_card_copy_rules()
    carousel_final_quality_check = build_carousel_final_quality_check(include_primary_text_variations=True)
    return f"""SPORTS CAVE MOTORSPORT CAROUSEL AD

PRODUCT
Product name: {product_name}
Category: {category}
Market: {country}
Campaign type: {campaign_type}

I have attached the exact Sports Cave product image being advertised.

Analyse the attached image before writing.

Use the supplied product name as the source of identity. Do not identify or guess a person solely from the image.

Study every usable product detail, including:

- visible artwork title
- driver, team, car or rivalry supplied by the product name
- race, circuit, era or moment that is safely confirmed
- colours and visual mood
- framed presentation
- edition plaque or collector details
- emotional meaning to a genuine motorsport fan

Do not invent race results, records, dates, quotations, achievements, car numbers, teams, production locations, dispatch times or historical facts.

When a specific fact cannot be confirmed from the product name or image, avoid it rather than guessing.

OBJECTIVE

Create a high-converting Sports Cave Meta carousel copy pack based on the proven Australian motorsport winner formula.

The ad must feel:

- nostalgic
- specific
- premium
- masculine
- collector-focused
- emotionally written for real motorsport fans
- commercially strong without sounding cheap or desperate

This is not generic wall décor.

Position it as a premium framed collector piece that preserves a person, rivalry, race, era or moment fans still remember.

{carousel_story_rules}

CAROUSEL STORY FLOW

The five cards must form one connected sequence:

1. Introduce the hero product, person or moment.
2. Trigger a specific motorsport memory.
3. Turn that memory into collector meaning.
4. Show why it belongs on the fan’s wall, in the man cave, office, garage or home bar.
5. Close with genuine numbered-edition scarcity.

CAROUSEL COPY RULES

Create exactly five cards.

Each card requires:

Headline
Description

{carousel_card_copy_rules}

Use this strategic role for each card:

Card 1 — Hero identity
Name or frame the product, person, rivalry, car or iconic moment.

Card 2 — Motorsport memory
Use the race, circuit, rivalry, era, pressure, noise, machine or moment that makes the product meaningful.

Card 3 — Collector emotion
Use ideas such as history framed, captured forever, immortalised, for those who remember or collector legacy, but write something specific to this product.

Card 4 — Wall ownership
Position it for a man cave, collector wall, office, garage or home bar without making it sound like cheap décor.

Card 5 — Scarcity
Use the real numbered-edition fact: only 100 editions. Make the ending controlled, credible and premium.

PRIMARY TEXT

Create exactly five genuinely different Meta primary-text variations.

Do not create five minor rewrites of the same advertisement.

Variation 1 — Short cinematic hook
- Approximately 25 to 45 words.
- Begin with a memorable, product-specific line.
- Strong enough to work before “See more.”
- Focus on nostalgia and the moment.

Variation 2 — Fan identity
- Approximately 60 to 100 words.
- Speak directly to the correct supporter, driver fan, team fan, rivalry fan or motorsport generation.
- Make the reader feel recognised.

Variation 3 — Story and legacy
- Approximately 70 to 110 words.
- Explain why the subject, race, rivalry, car or era is still remembered.
- Transition naturally into the framed collector piece.

Variation 4 — Collector and wall ownership
- Approximately 80 to 120 words.
- Position the artwork as the centrepiece of a man cave, office, garage, collector wall or home bar.
- Include concise product proof only where confirmed.

Variation 5 — Numbered scarcity
- Approximately 60 to 100 words.
- Lead with emotional relevance rather than fake urgency.
- Close with only 100 numbered editions and no second run.
- Keep the scarcity credible and controlled.

PRIMARY-TEXT RULES

Every variation must:

- Have a strong first one or two lines before the Meta “See more” cut.
- Relate specifically to this product.
- Sound like it was written by someone who understands the fan.
- Use concrete motorsport language rather than generic hype.
- Position the product as premium and wall-worthy.
- Mention the numbered edition naturally where appropriate.
- Avoid emojis.
- Avoid hashtags.
- Avoid fake quotations.
- Avoid all-capital shouting.
- Avoid “buy now before it is too late.”
- Avoid “the ultimate collector’s item.”
- Avoid generic AI phrases such as “celebrate the passion.”
- Avoid unsupported claims.
- Avoid describing the product as merely a poster.
- Avoid using the same opening hook twice.

Sports Cave tone:

- “Greatness doesn’t fade. It gets framed.”
- “Legends never die.”
- premium rather than cheap
- emotional rather than exaggerated
- scarcity based on a real edition of 100
- written for collectors, not impulse décor shoppers

VERIFIED PRODUCT POSITIONING

You may safely use these general concepts:

- premium framed collector artwork
- individually numbered edition
- limited to 100
- designed to be displayed proudly
- suitable for a man cave, office, garage, home bar or collector wall

Do not state manufacturing location, delivery time, customer count or shipping offer unless that information is separately supplied.

OUTPUT EXACTLY IN THIS FORMAT

CAROUSEL CARDS

Card 1
Headline:
Description:

Card 2
Headline:
Description:

Card 3
Headline:
Description:

Card 4
Headline:
Description:

Card 5
Headline:
Description:

PRIMARY TEXT VARIATIONS

Variation 1 — Short Cinematic
[copy]

Variation 2 — Fan Identity
[copy]

Variation 3 — Story And Legacy
[copy]

Variation 4 — Collector Ownership
[copy]

Variation 5 — Numbered Scarcity
[copy]

{carousel_final_quality_check}
"""


def build_ads_prompt(product_name, category, country, campaign_type):
    template_key = get_template_key(category, campaign_type)
    if template_key == "motorsport_carousel":
        prompt = build_motorsport_carousel_prompt(product_name, category, country, campaign_type)
    else:
        prompt = ""
    return apply_campaign_copy_rule_blocks(
        prompt,
        campaign_type,
        include_primary_text_variations=template_key in TEMPLATES_WITH_PRIMARY_TEXT_VARIATIONS,
        category=category,
    )


def render_insufficient_winner_data():
    st.subheader("Insufficient winner data")
    st.caption("Approved winner examples have not been added for this category and campaign type yet.")


def render_supported_result(product_name, category, country, campaign_type):
    st.subheader("1. Upload these five images")
    for index, (title, body) in enumerate(IMAGE_ORDER, start=1):
        st.markdown(f"**Card {index} — {title}**")
        st.caption(body)
    st.caption("Upload them to Meta in this exact order before adding the carousel copy.")

    st.subheader("2. Copy this ChatGPT prompt")
    st.code(build_ads_prompt(product_name, category, country, campaign_type), language="text")

    st.subheader("3. Build it in Meta")
    for index, step in enumerate(META_BUILD_ORDER, start=1):
        st.markdown(f"{index}. {step}")
    st.caption("Review every fact before publishing. Remove anything that cannot be confirmed from the product or artwork.")


def render_page():
    st.title("Ads")
    st.caption("Build Meta ad instructions from approved Sports Cave winner patterns.")

    with st.expander("How to use", expanded=False):
        st.markdown(
            "1. Enter the exact product name.\n"
            "2. Choose the category, country and campaign type.\n"
            "3. Select Submit.\n"
            "4. Copy the generated ChatGPT prompt.\n"
            "5. Open ChatGPT and attach the exact product image being advertised.\n"
            "6. Paste the prompt so ChatGPT can analyse the artwork, title, subject, event and collector details.\n"
            "7. Upload the five chosen mockups to Meta in the displayed order.\n"
            "8. Add the five carousel headlines and descriptions.\n"
            "9. Test the five primary-text variations separately."
        )
        st.warning(
            "Use the product name as the identity source. ChatGPT must not guess a person, event or achievement from the image."
        )

    with st.form("ads-builder-form"):
        product_name = st.text_input("Product name", placeholder="Example: Six Laps Ahead")
        category_col, country_col, campaign_col = st.columns(3)
        with category_col:
            category = st.selectbox("Category", CATEGORY_OPTIONS)
        with country_col:
            country = st.selectbox("Country", COUNTRY_OPTIONS)
        with campaign_col:
            campaign_type = st.selectbox("Campaign type", CAMPAIGN_TYPE_OPTIONS)
        submitted = st.form_submit_button("Submit", type="primary")

    if not submitted:
        return

    validation_message = validate_ads_inputs(product_name, category, country, campaign_type)
    if validation_message:
        st.warning(validation_message)
        return

    if not get_template_key(category, campaign_type):
        render_insufficient_winner_data()
        return

    render_supported_result(product_name, category, country, campaign_type)


render_ads_page = render_page
render_marketing_factory_page = render_page
