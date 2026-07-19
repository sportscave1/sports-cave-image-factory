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

SUPPORTED_TEMPLATES = {
    ("Motorsport", "Carousel"): "motorsport_carousel",
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


def build_motorsport_carousel_prompt(product_name, category, country, campaign_type):
    product_name = _clean_product_name(product_name)
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

Headline rules:

- Maximum 32 characters including spaces.
- Ideally two to five words.
- Clear when viewed quickly on mobile.
- Title Case or natural sentence case.
- No emojis.
- No all-capital shouting.
- No unnecessary punctuation.
- Do not repeat the product title on every card.
- Do not repeat “Limited Edition” on every card.

Description rules:

- Maximum 24 characters including spaces.
- Ideally two to four words.
- Must support rather than repeat the headline.
- No full sentences unless extremely short.
- No generic filler.

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

Final quality check before answering:

- Exactly five carousel cards.
- Exactly five primary-text variations.
- Every headline is 32 characters or fewer.
- Every description is 24 characters or fewer.
- Copy is specific to the supplied product.
- The five cards flow as one story.
- The five primary texts use different selling angles.
- No facts have been invented.
- No generic filler remains."""


def build_ads_prompt(product_name, category, country, campaign_type):
    template_key = get_template_key(category, campaign_type)
    if template_key == "motorsport_carousel":
        return build_motorsport_carousel_prompt(product_name, category, country, campaign_type)
    return ""


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
