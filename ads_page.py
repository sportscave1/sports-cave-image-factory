import hashlib
import html
import json
import re
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components


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

EDITION_OPS_SNAPSHOT_PATH = Path(__file__).resolve().parent / "output" / "_cache" / "edition_ops_products_snapshot.json"
EDITION_OPS_ROWS_SESSION_KEY = "edition_ops_rows"

CAROUSEL_CARD_MAX_CHARACTERS = 13
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
    "Framed",
    "Framed Art",
    "Wall Art",
    "Collector",
    "Collector Piece",
    "Garage Pride",
    "Fan Favourite",
    "Motorsport Art",
    "Racing Art",
    "Must Have",
    "Shop Now",
    "Own It Now",
)

PRODUCT_SPECIFIC_CAROUSEL_EXAMPLES = (
    "Six Laps",
    "Peter Brock",
    "Bathurst 1979",
    "Mt Panorama",
    "Brock Legacy",
    "Still Roars",
    "Ford v Holden",
    "Lap Of Gods",
    "Race Legend",
    "Only 100 Made",
    "No Second Run",
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
    ("Baseball", "Instant Experience"): "baseball_instant_experience",
}

TEMPLATES_WITH_PRIMARY_TEXT_VARIATIONS = {
    "motorsport_carousel",
}

BASEBALL_INSTANT_EXPERIENCE_PRODUCT_SET_NAME = "Baseball Wall Art"
BASEBALL_INSTANT_EXPERIENCE_CTA = "Claim Your Edition"
BASEBALL_INSTANT_EXPERIENCE_APPROVED_CLAIMS = (
    "✔ Only 100 editions.",
    "✔ Numbered C.O.A. included.",
    "✔ Made in the USA.",
    "✔ Rated 4.9 / 5 by thousands of collectors.",
)

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

META_AD_URL_PARAMETERS = (
    "utm_source=facebook&utm_medium=paid_social&utm_campaign={{campaign.name}}"
    "&utm_content={{ad.name}}&utm_term={{adset.name}}&placement={{placement}}"
)

COUNTRY_LANGUAGE_PROFILES = {
    "Australia": {
        "heading": "COUNTRY LANGUAGE AND LOCALISATION — AUSTRALIA",
        "english_variant": "natural Australian English",
        "spellings": "colour, favourite, organise, personalised, centre, licence as a noun, licensed as a verb or adjective, travelled, travelling",
        "terminology": "delivery, free delivery, add to cart, shop, order, collector, limited edition, framed artwork, race day, and footy only when the selected sport and context make it genuinely appropriate",
        "sports": "For Australian motorsport, cricket, AFL and other categories, use terminology Australian fans naturally expect. Motorsport may reference Bathurst, the Mountain, race day, touring-car heritage or Australian motorsport history only when supported by the selected product. AFL may use footy where natural. Cricket language should sound Australian rather than American. Association football should normally be called football or soccer according to the specific Australian audience and existing category naming.",
        "avoid": "Do not force words such as mate, Aussie, bloody, legend or reckon. Do not use American spelling such as color, favorite, center, personalize, organize or license as a noun when licence is required. Do not use American retail terminology where it would feel unnatural.",
        "quality": "Australian spelling throughout. No accidental American spelling.",
    },
    "USA": {
        "heading": "COUNTRY LANGUAGE AND LOCALISATION — UNITED STATES",
        "english_variant": "natural American English",
        "spellings": "color, favorite, organize, personalized, center, license, traveled, traveling",
        "terminology": "shipping, free shipping, add to cart, shop now, game day, home, fan, collector, limited edition, framed artwork, sports room, and man cave",
        "sports": "Use the terminology American fans expect for each sport. Association football should normally be called soccer. American football should be called football or NFL when factually appropriate. Baseball copy should use natural American baseball terminology. Basketball copy should sound like copy written for an American NBA audience. Motorsport language should match the actual product and racing category.",
        "avoid": "Do not use British or Australian spellings such as colour, favourite, centre, personalised, organise or licence as the noun form. Do not use add to basket. Do not use Australian or British fan terminology where it would sound foreign to the intended US audience.",
        "quality": "American spelling throughout. No accidental British or Australian spelling.",
    },
    "UK": {
        "heading": "COUNTRY LANGUAGE AND LOCALISATION — UNITED KINGDOM",
        "english_variant": "natural British English",
        "spellings": "colour, favourite, organise, personalised, centre, licence as a noun, licensed as a verb or adjective, travelled, travelling",
        "terminology": "delivery, free delivery, add to basket, shop, order, supporter, fan, collector, limited edition, framed artwork, and matchday",
        "sports": "Use the terminology UK sports fans naturally expect. Association football must normally be called football, not soccer. Use club, supporter, match, matchday, fixture, season and derby where natural and factually appropriate. Motorsport and cricket terminology should sound natural to UK audiences. Do not use American sports vocabulary where it conflicts with UK usage.",
        "avoid": "Do not use American spelling such as color, favorite, center, personalized or organize. Do not use add to cart when the intended UI or copy context should naturally use basket. Do not use soccer for UK football audiences. Avoid forced British slang such as mate, proper, brilliant or cheeky unless genuinely natural, commercially appropriate and aligned with Sports Cave's premium tone.",
        "quality": "British spelling throughout. Football terminology instead of soccer where association football is intended. No accidental American spelling.",
    },
    "Canada": {
        "heading": "COUNTRY LANGUAGE AND LOCALISATION — CANADA",
        "english_variant": "natural Canadian English",
        "spellings": "colour, favourite, centre, travelled and travelling, while using clear North American phrasing where it is natural",
        "terminology": "shipping, delivery, add to cart, shop, order, fan, collector, limited edition, framed artwork, sports room, and man cave where appropriate",
        "sports": "Use terminology Canadian fans naturally expect for the selected sport. Hockey language should sound Canadian when hockey is selected. Basketball, baseball, football, motorsport and other categories must stay tied to the supplied product rather than imported from another market.",
        "avoid": "Do not force American, British or Australian slang. Do not mix spelling systems within the same response. Do not invent Canadian local facts or shipping claims.",
        "quality": "Canadian English throughout. No mixed-market terminology.",
    },
    "New Zealand": {
        "heading": "COUNTRY LANGUAGE AND LOCALISATION — NEW ZEALAND",
        "english_variant": "natural New Zealand English",
        "spellings": "colour, favourite, organise, personalised, centre, licence as a noun, travelled and travelling",
        "terminology": "delivery, shop, order, add to cart where natural, supporter, fan, collector, limited edition, and framed artwork",
        "sports": "Use terminology New Zealand fans naturally expect for the selected sport. Rugby, cricket, motorsport and football language must fit the selected product and should not borrow Australian stereotypes.",
        "avoid": "Do not force Kiwi slang, Australian slang or stereotypes. Do not use American spelling unless it is part of a protected official name.",
        "quality": "New Zealand English throughout. No forced slang or mixed dialect.",
    },
}

COUNTRY_LANGUAGE_ALIASES = {
    "United States": "USA",
    "US": "USA",
    "United Kingdom": "UK",
    "Great Britain": "UK",
}

COUNTRY_LANGUAGE_FALLBACK = {
    "heading": "COUNTRY LANGUAGE AND LOCALISATION — NEUTRAL INTERNATIONAL ENGLISH",
    "english_variant": "neutral international English",
    "spellings": "consistent English spelling appropriate to the selected country when known, without mixing Australian, American and British forms",
    "terminology": "clear international retail language such as shop, order, collector, limited edition and framed artwork",
    "sports": "Use factual product terminology and the selected sport's natural vocabulary without importing unsupported local references.",
    "avoid": "Do not force slang, stereotypes or region-specific claims. Do not silently treat unknown countries as American English.",
    "quality": "Consistent neutral international English. No mixed dialects.",
}


def _clean_product_name(product_name):
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", product_name or "").strip()


def _clean_product_url(product_url):
    return re.sub(r"[\x00-\x20\x7f]", "", product_url or "").strip()


def _normalise_option_label(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _product_name_from_edition_ops_row(row):
    if not isinstance(row, dict):
        return ""
    return _normalise_option_label(
        row.get("product_title")
        or row.get("Product title")
        or row.get("edition_name")
        or row.get("product_name")
        or row.get("title")
        or row.get("name")
    )


def _edition_ops_rows_from_local_snapshot(snapshot_path=EDITION_OPS_SNAPSHOT_PATH):
    snapshot_path = Path(snapshot_path)
    if not snapshot_path.exists():
        return []
    try:
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return []
    rows = payload.get("rows") if isinstance(payload, dict) else []
    return rows if isinstance(rows, list) else []


def load_edition_ops_product_name_options(snapshot_path=EDITION_OPS_SNAPSHOT_PATH):
    rows = []
    session_rows = st.session_state.get(EDITION_OPS_ROWS_SESSION_KEY, [])
    if isinstance(session_rows, list):
        rows.extend(session_rows)
    rows.extend(_edition_ops_rows_from_local_snapshot(snapshot_path))

    options = []
    seen = set()
    for row in rows:
        product_name = _product_name_from_edition_ops_row(row)
        key = product_name.casefold()
        if product_name and key not in seen:
            options.append(product_name)
            seen.add(key)
    return options


def render_prompt_copy_button(prompt_text, key, label="Copy Prompt"):
    prompt_text_json = json.dumps(str(prompt_text or ""))
    safe_label = html.escape(label)
    button_id = f"ads-copy-prompt-{hashlib.sha1(str(key).encode('utf-8')).hexdigest()[:12]}"
    components.html(
        f"""
        <div style="padding:2px 0;">
          <button
            id="{button_id}"
            type="button"
            style="width:100%;border:1px solid rgba(11,11,13,0.55);border-radius:14px;padding:12px 14px;background:#FFFFFF;color:#0B0B0D;font-weight:700;font-size:0.95rem;cursor:pointer;box-sizing:border-box;"
          >
            {safe_label}
          </button>
        </div>
        <script>
        (() => {{
          const button = document.getElementById("{button_id}");
          const promptText = {prompt_text_json};
          const originalLabel = button.innerText;

          async function copyPrompt(event) {{
            event.preventDefault();
            try {{
              if (navigator.clipboard && window.isSecureContext) {{
                await navigator.clipboard.writeText(promptText);
              }} else {{
                const textarea = document.createElement("textarea");
                textarea.value = promptText;
                textarea.style.position = "fixed";
                textarea.style.opacity = "0";
                document.body.appendChild(textarea);
                textarea.focus();
                textarea.select();
                document.execCommand("copy");
                document.body.removeChild(textarea);
              }}
              button.innerText = "Prompt copied";
            }} catch (error) {{
              button.innerText = "Copy failed";
            }}
            setTimeout(() => {{
              button.innerText = originalLabel;
            }}, 1400);
          }}

          button.addEventListener("click", copyPrompt);
        }})();
        </script>
        """,
        height=64,
    )


def validate_ads_inputs(product_name, category, country, campaign_type, product_url=""):
    if not _clean_product_name(product_name):
        return "Enter a product name and choose a category, country and campaign type."
    if category == "Select category" or country == "Select country" or campaign_type == "Select campaign type":
        return "Enter a product name and choose a category, country and campaign type."
    if get_template_key(category, campaign_type) == "baseball_instant_experience" and not _clean_product_url(product_url):
        return "Enter the exact product page URL for this Baseball Instant Experience campaign."
    return ""


def get_template_key(category, campaign_type):
    return SUPPORTED_TEMPLATES.get((category, campaign_type))


def normalize_country_language_key(country):
    country_value = str(country or "").strip()
    return COUNTRY_LANGUAGE_ALIASES.get(country_value, country_value)


def get_country_language_profile(country):
    country_key = normalize_country_language_key(country)
    return COUNTRY_LANGUAGE_PROFILES.get(country_key, COUNTRY_LANGUAGE_FALLBACK)


def build_country_language_guidance(country):
    selected_country = str(country or "").strip() or "Unknown"
    profile = get_country_language_profile(country)
    return f"""COUNTRY LANGUAGE AND LOCALISATION RULES

Selected country: {selected_country}

{profile["heading"]}

Write every customer-facing field in {profile["english_variant"]}.

Required spelling:
- {profile["spellings"]}

Natural terminology and retail language:
- {profile["terminology"]}

Sports vocabulary:
- {profile["sports"]}

Prohibited mixed-market usage:
- {profile["avoid"]}

Global localisation instruction:
- Write every customer-facing field in the natural spelling, terminology and phrasing expected in the selected country.
- Do not mix Australian, American and British English in the same response.
- Do not force stereotypes, fake accents, excessive slang or caricatured local phrases.
- Country localisation controls language and terminology only. It must not invent product facts, local facts, delivery claims, shipping claims, edition quantities or scarcity claims.
- Treat product names, athlete names, official event names, artwork text, URLs, handles, brand names and official competition names as protected content. Do not rewrite protected content merely to localise spelling.

Before answering, proofread every customer-facing field for the selected country. Correct any spelling, terminology, sports vocabulary or retail language that belongs to a different market.

Country-localisation quality check:
- Every customer-facing field uses the selected country's spelling.
- Every customer-facing field uses terminology natural to the selected market.
- Sports terminology matches both the selected sport and selected country.
- Retail and delivery terminology matches the selected country.
- Australian, American and British English are not mixed.
- No forced slang or market stereotypes are used.
- No unsupported local facts or commercial claims are invented.
- All existing campaign-specific character and formatting rules are still satisfied.
- {profile["quality"]}"""


def apply_country_language_guidance(prompt, country):
    if not prompt:
        return prompt
    guidance = build_country_language_guidance(country)
    if "COUNTRY LANGUAGE AND LOCALISATION RULES" in prompt:
        return prompt
    return f"{prompt.rstrip()}\n\n{guidance}"


def build_meta_url_parameters_guidance():
    return f"""META URL PARAMETERS

For every Meta ad created from this prompt, paste this exact string into the Meta URL parameters field:

{META_AD_URL_PARAMETERS}

Do not rewrite, localise, encode, shorten, remove, or add to these URL parameters."""


def apply_meta_url_parameters_guidance(prompt):
    if not prompt:
        return prompt
    if "META URL PARAMETERS" in prompt:
        return prompt
    return f"{prompt.rstrip()}\n\n{build_meta_url_parameters_guidance()}"


def mask_protected_terms(text, protected_terms=()):
    masked = str(text or "")
    for index, term in enumerate(protected_terms or ()):
        term_text = str(term or "")
        if term_text:
            masked = masked.replace(term_text, f"__PROTECTED_TERM_{index}__")
    return masked


def validate_country_localisation(generated_text, country, protected_terms=(), sport_category=""):
    text = mask_protected_terms(generated_text, protected_terms).casefold()
    country_key = normalize_country_language_key(country)
    issues = []

    if country_key in {"Australia", "UK", "New Zealand"}:
        for term in ("color", "favorite", "center", "personalize", "organize"):
            if re.search(rf"\b{term}\b", text):
                issues.append(f"{country_key} copy contains non-local spelling: {term}.")
        if country_key == "UK" and "add to cart" in text:
            issues.append("UK copy uses add to cart where basket language is expected.")
        if country_key == "UK" and "football" in str(sport_category or "").casefold() and re.search(r"\bsoccer\b", text):
            issues.append("UK association-football copy uses soccer instead of football.")

    if country_key == "USA":
        for term in ("colour", "favourite", "centre", "personalised", "organise"):
            if re.search(rf"\b{term}\b", text):
                issues.append(f"USA copy contains non-local spelling: {term}.")
        if "add to basket" in text:
            issues.append("USA copy uses add to basket where cart language is expected.")

    return issues


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
        r"Card\s+(\d+)(?:\s+[—-]\s+[^\r\n]+)?\s*[\r\n]+Headline:\s*(.*?)\s*[\r\n]+Description:\s*(.*?)(?=\s*[\r\n]+Card\s+\d+(?:\s+[—-]\s+[^\r\n]+)?|\s*[\r\n]+PRIMARY TEXT|\Z)",
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

The five cards must work as one connected sequence rather than five unrelated sales labels.

Card 1 — Product Identity
- Immediately identify the artwork, driver, rivalry, car or defining phrase.
- Use the strongest recognisable phrase from the product name or attached artwork.

Card 2 — Race Or Moment
- Trigger a recognisable motorsport memory.
- Prioritise race name, circuit, year, car number, rivalry, famous lap or defining event.
- Use only details confirmed by the supplied product name or attached artwork.

Card 3 — Legacy
- Express why the subject still matters to fans.
- Make the legacy or nostalgia specific to the actual product whenever possible.

Card 4 — Fan Ownership
- Make the correct fan imagine displaying it proudly.
- Prioritise fan identity over generic room descriptions.
- Do not use Garage Pride or similarly generic wording unless it is clearly the strongest product-specific option.

Card 5 — Scarcity
- Close with genuine limited-edition scarcity.
- Communicate only 100 numbered editions, no second run, and no restock once sold out.
- Keep it premium and controlled. Do not use cheap urgency.

PRODUCT SPECIFICITY TEST

- At least four of the five card pairs must include a product-specific anchor across the headline or description.
- A product-specific anchor may be a supplied person name, artwork title, confirmed circuit, confirmed year, rivalry, car identity, era or product-specific phrase.
- Every card pair must pass this test: could this card be copied unchanged onto an unrelated sports artwork?
- If yes, rewrite it.
- Do not force the full product name onto multiple cards. Use different pieces of supplied identity across the sequence.

QUALITY SELECTION

- Analyse the product name and attached artwork.
- Identify the most recognisable verified product details.
- Silently create several possible headline and description options for each strategic card role.
- Reject anything generic, unclear or over 13 characters.
- Select the strongest final combination.
- Do not output rejected alternatives.
- Do not display the internal candidate list or reasoning.
- The final sequence must feel connected, avoid repetition, become progressively more emotional and finish with credible scarcity.

GENERIC FILLER TO REJECT UNLESS CLEARLY MODIFIED BY PRODUCT-SPECIFIC IDENTITY

{banned_phrases}

{category_cues}"""


def build_carousel_card_copy_rules():
    examples = "\n".join(f"- {example}" for example in PRODUCT_SPECIFIC_CAROUSEL_EXAMPLES)
    generic_phrases = "\n".join(f"- {phrase}" for phrase in BANNED_GENERIC_CAROUSEL_PHRASES)
    return f"""CAROUSEL CARD CHARACTER LIMIT

For all five Motorsport carousel cards:

Headline:
- Maximum {CAROUSEL_CARD_MAX_CHARACTERS} characters including spaces and punctuation.

Description:
- Maximum {CAROUSEL_CARD_MAX_CHARACTERS} characters including spaces and punctuation.

This is a strict limit.

- Do not truncate text to make it fit.
- Do not cut words in half.
- Do not silently allow text longer than {CAROUSEL_CARD_MAX_CHARACTERS} characters.
- Count every character before returning the final output.
- Use Python len(value) semantics: spaces and punctuation count.
- Never contain a comma or full stop.
- Use complete words only.

QUALITY PRIORITY

Within the {CAROUSEL_CARD_MAX_CHARACTERS}-character limit, choose the most emotionally powerful and product-specific wording possible.

Priority order:

1. Exact product identity.
2. Recognisable driver, car, race, circuit, rivalry or year.
3. Motorsport nostalgia.
4. Fan identity.
5. Collector ownership.
6. Genuine scarcity.

A specific term is stronger than a generic term.

Prefer product-specific language such as:

{examples}

Avoid weak standalone labels such as:

{generic_phrases}

These generic phrases may only be used when no more specific verified product language is available.

Do not force generic room language into a card when stronger product history or fan identity is available."""


def build_carousel_final_quality_check(include_primary_text_variations=False):
    checks = [
        "Exactly five carousel cards are present.",
        "Every headline is 13 characters or fewer including spaces and punctuation.",
        "Every description is 13 characters or fewer including spaces and punctuation.",
        "Spaces and punctuation are included in the count.",
        "No words have been truncated.",
        "Card 1 identifies the product.",
        "Card 2 triggers a race, place, year or moment.",
        "Card 3 communicates legacy or nostalgia.",
        "Card 4 communicates fan ownership.",
        "Card 5 communicates genuine scarcity.",
        "The cards read as one connected story.",
        "The wording is specific to the supplied product.",
        "Generic labels have been replaced wherever stronger verified wording exists.",
        "No duplicate headlines.",
        "No duplicate descriptions.",
    ]
    if include_primary_text_variations:
        checks.extend(
            [
                "Exactly five primary-text variations are present.",
                "Every primary-text variation contains deliberate paragraph spacing.",
                "No variation is displayed as one massive paragraph.",
                "The five variations use genuinely different selling angles.",
            ]
        )
    checks.append("No unverified facts have been invented.")
    check_lines = "\n".join(f"- {check}" for check in checks)
    return f"""FINAL CHECK

Before returning the answer, verify:

{check_lines}

If any carousel field exceeds 13 characters, rewrite it before answering."""


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


def compose_final_ads_prompt(
    prompt,
    *,
    category,
    country,
    campaign_type,
    include_primary_text_variations=False,
):
    if not prompt:
        return prompt
    prompt = apply_campaign_copy_rule_blocks(
        prompt,
        campaign_type,
        include_primary_text_variations=include_primary_text_variations,
        category=category,
    )
    prompt = apply_country_language_guidance(prompt, country)
    return apply_meta_url_parameters_guidance(prompt)


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

CAROUSEL COPY RULES

Create exactly five cards.

Each card requires:

Headline
Description

{carousel_card_copy_rules}

Use the five strategic roles exactly as defined above: Product Identity, Race Or Moment, Legacy, Fan Ownership, and Scarcity.

PRIMARY TEXT VARIATIONS

Create exactly five genuinely different Meta primary-text variations.

The five variations must be equal in quality.

Do not use one strong advertisement followed by weaker filler variations.

Silently develop several candidates for every angle. Score them for:

- immediate stopping power
- Australian motorsport nostalgia
- product specificity
- emotional recognition
- collector desire
- credible scarcity
- natural human writing

Only return variations that would score at least 9 out of 10 across those criteria.

If one variation feels weaker than the others, rewrite it before returning the final output.

CORE AUSTRALIAN MOTORSPORT EMOTION

Write specifically for Australian motorsport fans who remember the people, machines, circuits and eras represented by the supplied product.

The copy should feel written by someone who understands why Bathurst, the Mountain, the noise, the pressure, the rivalry and the old racing eras still matter.

Only use those cues when supported by the supplied product name, artwork or visible text.

Favour:

- the Mountain
- Bathurst memory
- the roar and pressure of the race
- the driver and machine
- Australian racing identity
- the era fans grew up watching
- the feeling of remembering exactly what the title means
- pride in displaying that memory
- the finality of a numbered edition

Avoid generic sports language that could be pasted onto another artwork.

PRIMARY-TEXT FORMATTING

Every variation must be intentionally broken into short, readable sections.

Preserve blank lines in the generated output.

Each longer variation should use this visual structure:

HOOK

One short opening line or two very short opening lines.

STORY

One short paragraph containing no more than three sentences.

PRODUCT / COLLECTOR VALUE

One short paragraph, or a compact proof block when confirmed.

SCARCITY CLOSE

One or two short closing lines.

This demonstrates spacing only. Do not hardcode the same wording for every product.

IMMEDIATE HOOK RULE

The first sentence or fragment of every variation must immediately use a product-specific memory anchor.

Suitable anchors include:

- supplied driver name
- artwork title
- confirmed circuit
- confirmed year
- confirmed rivalry
- confirmed vehicle or team identity
- a phrase clearly tied to the supplied product

Do not begin with generic statements such as:

- Some walls carry decoration
- This is for sports fans
- History deserves a frame
- A collector piece for your wall
- This legend needs no introduction
- This product does not need hype
- Celebrate the passion
- Own a piece of greatness

The first line must make the correct motorsport fan stop before the Meta See More cut.

REAL SCARCITY IN EVERY VARIATION

All five primary-text variations must include the real scarcity naturally.

For Sports Cave numbered releases, communicate:

- only 100 numbered editions
- no second run

Do not repeat the exact same scarcity sentence five times.

Vary the expression while keeping the fact unmistakable.

Examples of acceptable approaches:

- Limited to 100 numbered editions with no second run.
- Once the 100 editions are claimed this release is finished.
- One hundred numbers only and this series will not return.
- The run ends at 100 with no second release.
- Only 100 collectors will secure an edition.

Do not use fake countdowns, false stock claims or unsupported urgency.

The scarcity must feel controlled, final and collector-focused rather than cheap or desperate.

PRODUCT-SPECIFICITY RULE

Every variation must contain at least two different product-specific anchors.

At least three variations must include a product-specific anchor within the first eight words.

Do not repeatedly force the entire product title into every variation.

Use different pieces of the supplied identity across the five versions.

Every variation must fail this test:

Could this copy be pasted unchanged onto unrelated football, cricket, basketball or boxing artwork?

If yes, rewrite it.

FIVE DISTINCT HIGH-STRENGTH ANGLES

Variation 1 — Short Cinematic

- Approximately 25 to 45 words.
- Use two or three short text blocks.
- Open with the artwork title, driver, circuit or defining moment.
- Recreate the memory in sharp cinematic fragments.
- Focus on the instant emotional hit.
- Finish with concise edition scarcity.
- Every sentence must earn its place.

Variation 2 — Fan Recognition

- Approximately 60 to 100 words.
- Use three or four short text blocks.
- Speak directly to the Australian fan who remembers the era.
- Make the reader feel recognised rather than marketed to.
- Use specific motorsport atmosphere and identity.
- Connect the memory to the framed collector artwork.
- End with a separate scarcity line.

Variation 3 — Race Memory And Legacy

- Approximately 70 to 105 words.
- Use three or four short text blocks.
- Build around the confirmed race, circuit, year, rivalry, driver or machine.
- Use sensory race language without inventing historical details.
- Explain why this exact moment or era still carries emotional weight.
- Transition naturally into ownership.
- Include controlled scarcity before the final sentence.
- No paragraph longer than three sentences.

Variation 4 — Collector Pride And Display

- Approximately 80 to 120 words.
- Use three or four short text blocks.
- Begin with the supplied driver, race, title or circuit rather than a generic statement about walls.
- Sell identity and pride before mentioning the room.
- Position the artwork as something that belongs in a serious collector’s office, garage, home bar, man cave or display wall.
- Connect the artwork to the man cave, office, garage, home bar or collector wall.
- A compact bullet block may be used only for verified product benefits.
- Do not turn this into generic interior-decor copy.
- Make the numbered plaque and edition limit part of the collector meaning.
- Finish with a strong no-second-run line.
- Never create one large paragraph.

Variation 5 — Numbered Finality

- Approximately 60 to 95 words.
- Use three or four short text blocks.
- Lead with emotional relevance rather than marketing language.
- Make the edition limit feel permanent and meaningful.
- Clearly state that only 100 numbered editions exist and there is no second run.
- Place the edition scarcity in its own final block.
- End with a controlled collector CTA such as secure your number, claim your edition or choose your number while the run remains open.
- Do not use desperate or bargain-store urgency.

EQUAL-STRENGTH RULE

Each variation must have:

- a product-specific opening
- an emotional motorsport memory
- a reason the artwork matters to a genuine fan
- premium collector positioning
- real edition scarcity
- a clear final action or sense of finality

No variation may exist merely to fill an angle.

Variation 4 must be as emotionally powerful as Variations 1 and 2.

Variation 5 must still contain nostalgia and cannot consist only of scarcity language.

BULLET FORMATTING

When a variation includes product proof, use a short bullet block with a blank line before and after it.

Example:

• Individually numbered
• Limited to 100 editions
• Premium framed presentation
• Ready to display

Do not include unsupported claims.

Do not automatically claim:

- made in Australia
- hand-crafted in Australia
- dispatch in one to three days
- trusted by over 1,000 collectors
- worldwide edition
- free shipping
- no import fees

These may only be included when separately supplied and verified.

Use no more than five bullets.

Do not use bullets in every variation. The five variations must look and feel different.

READABILITY RULES

Apply these rules to every primary-text variation:

- Insert a blank line between the hook, story, product value and scarcity close.
- No paragraph longer than three sentences.
- Avoid sentences longer than approximately 22 words where possible.
- Do not begin every variation with the product name.
- Do not repeat the same hook.
- Do not repeat the same scarcity sentence.
- Do not use all-capital opening lines.
- Do not use excessive exclamation marks.
- Do not use emojis.
- Do not use hashtags.
- Do not produce a single uninterrupted wall of text.
- Preserve the line breaks when copied from Sports Cave OS.

STYLE RULES

Write like an Australian motorsport fan speaking to another fan.

The tone must be:

- nostalgic
- masculine
- direct
- premium
- collector-driven
- emotionally controlled
- specific to the artwork

Use short paragraphs and occasional fragments.

Avoid long polished explanations.

Avoid repeatedly using:

- premium collector piece
- displayed with pride
- powerful composition
- the weight it deserves
- more than décor
- defines the space
- centrepiece
- iconic
- legendary

These phrases may only appear when made unmistakably specific to the supplied product.

Do not use:

- emojis
- hashtags
- fake quotations
- unsupported historical facts
- fake stock counts
- fake customer numbers
- manufacturing claims
- delivery promises
- all-capital shouting
- generic AI language
- cheap urgency
- buy now before it is too late
- the ultimate collector’s item

SPORTS CAVE BRAND FEEL

The writing should carry the spirit of:

- Greatness doesn’t fade. It gets framed.
- Legends never die.
- Only 100 editions.
- No second run.

Do not force those exact lines into every advertisement.

Use their emotional direction while keeping each variation original.

FINAL PRIMARY-TEXT QUALITY CHECK

Before returning the result confirm:

- Exactly five primary-text variations.
- All five use different opening hooks.
- All five use meaningfully different selling angles.
- All five open with product-specific identity or memory.
- All five contain at least two product-specific anchors.
- All five include the real edition of 100.
- All five communicate no second run.
- All five trigger Australian motorsport nostalgia.
- All five are equally strong.
- No variation begins with generic wall-art language.
- No variation becomes an interior-design advertisement.
- No unsupported facts have been invented.
- No two variations feel like minor rewrites of one another.

Keep the current output format exactly unchanged.
Do not add scoring notes or internal quality commentary to the generated customer-facing result.

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

Card 1 — Product Identity
Headline:
Description:

Card 2 — Race Or Moment
Headline:
Description:

Card 3 — Legacy
Headline:
Description:

Card 4 — Fan Ownership
Headline:
Description:

Card 5 — Scarcity
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


def build_baseball_instant_experience_claim_block(approved_claims=BASEBALL_INSTANT_EXPERIENCE_APPROVED_CLAIMS):
    if not approved_claims:
        return """No proof/scarcity claim lines have been supplied or approved for this campaign.

Do not invent edition quantities, C.O.A. details, manufacturing origin, review ratings or collector counts.
Omit unconfirmed proof lines from the primary text."""
    claim_lines = "\n".join(approved_claims)
    return f"""Use this approved Baseball Instant Experience proof/scarcity section exactly:

{claim_lines}

These claim lines are supplied through the approved Baseball Instant Experience claim path.
Do not add, remove, localise, reinterpret or invent proof claims.
Do not replace Made in the USA with another manufacturing country because the advertising market changes."""


def build_baseball_instant_experience_prompt(
    product_name,
    category,
    country,
    campaign_type,
    product_url="",
):
    product_name = _clean_product_name(product_name)
    product_url = _clean_product_url(product_url)
    claim_block = build_baseball_instant_experience_claim_block()
    return f"""SPORTS CAVE BASEBALL INSTANT EXPERIENCE AD

PRODUCT
Product name: {product_name}
Category: {category}
Market: {country}
Campaign type: {campaign_type}
Product page URL: {product_url}

I have attached the exact Sports Cave product image being advertised.

Analyse the attached image before writing.

Use the supplied product name as the source of identity. Do not identify or guess a player, rivalry, achievement, team, season, date or milestone solely from the image.

Study every usable product detail, including:

- visible artwork title
- player or players supplied by the product name or visible artwork text
- milestone, rivalry, season, era, team, moment or legacy only when safely confirmed
- colours and visual mood
- framed presentation
- edition plaque or collector details
- emotional meaning to a genuine baseball fan

Do not invent statistics, dates, records, teams, achievements, quotes, nicknames, championships, rivalry details, production claims, review figures, delivery promises or edition information.

When a specific fact cannot be confirmed from the product name, artwork or approved campaign inputs, avoid it rather than guessing.

OBJECTIVE

Create one ultimate high-converting Sports Cave Meta Instant Experience ad package for a Baseball product.

This is not a five-variation campaign.

Generate exactly:

- one best primary text
- one best headline
- one CTA
- one clear Meta Instant Experience setup guide

Do not generate multiple primary-text versions, alternate headlines, carousel cards, optional copy, rejected alternatives or writing notes.

The copy must feel:

- product-specific
- emotionally strong
- identity-driven
- ownership-triggering
- premium
- collector-focused
- written for genuine baseball fans
- commercially strong without sounding cheap or desperate

This is not generic sports wall art.

PRIMARY TEXT STRUCTURE

Opening brand line:

Greatness doesn’t fade. It gets framed.

Keep this exact Sports Cave line as the opening unless an existing protected brand-setting system supplies an approved alternative.

Then add one short product-specific identity and legacy paragraph.

Analyse:

- product name
- visible artwork title
- player or players supplied by the product information
- milestone, rivalry, season, era, team, moment or legacy only when confirmed
- emotional meaning to a real baseball fan
- whether the artwork is about achievement, rivalry, nostalgia, greatness, pressure, legacy or history

For a milestone product, use the strongest confirmed achievement language from the product.

For a rivalry or dual-player product, use the strongest confirmed rivalry or dual-identity language from the product.

For a heritage product, lean into the era, silence before the swing, pressure of the moment, baseball history, memories real fans recognise, and why the artwork belongs on the wall.

Do not copy examples blindly.

Analyse the actual selected product and write the strongest product-specific line.

APPROVED PROOF AND SCARCITY

{claim_block}

Close with this line:

Strictly limited. Claim your number before the next one is gone.

Use the exact closing line unless the shared country-language rules require only a minor spelling or terminology adjustment.

IDENTITY AND OWNERSHIP RULES

The primary text must trigger genuine baseball-fan identity.

Make the reader feel:

- this is for people who truly remember
- this is for fans who understand the moment
- this artwork represents part of their baseball identity
- owning it proves what the era, player, rivalry or achievement meant to them
- the framed artwork belongs in their home, office, sports room, man cave, garage or collection
- waiting may mean losing their edition

Create the emotional thought:

- That moment matters to me.
- That belongs on my wall.
- That is part of my baseball history.
- I do not want to miss my edition.

Use selective identity language where appropriate, such as:

- This is not for casual fans
- For the fans who remember
- Real fans know
- If you felt that moment
- If you lived that era
- You already know why this belongs on your wall

Do not force the same phrase into every product.

Choose the strongest single angle or strongest compatible blend for the actual artwork.

BASEBALL-SPECIFIC WRITING DIRECTION

The copy must sound like it was written by someone who understands baseball culture.

Use authentic baseball emotion where supported:

- the silence before the swing
- pressure at the plate
- the crack of the bat
- game-changing moments
- historic seasons
- home-run power
- rivalries
- legendary eras
- postseason pressure
- records
- baseball history
- memories passed between generations

Authentic baseball terms must remain baseball-specific in every country, including home run, stolen base, at the plate, swing, inning, score, baseball fan, ballpark and postseason where appropriate.

Country-language rules change spelling, phrasing, retail language and tone. They do not change player identity, baseball facts, official product title, artwork text or verified commercial claims.

ONE BEST VERSION RULE

Before answering, internally consider several possible angles:

- fan identity
- nostalgia
- milestone
- rivalry
- legacy
- historic moment
- collector ownership
- scarcity

Choose only the strongest angle or strongest compatible blend.

Return one final primary text only.

Do not show rejected alternatives.

Apply this test:

If this copy could work for almost any baseball artwork, rewrite it with stronger product-specific identity.

HEADLINE RULES

Generate exactly one headline.

The headline must be:

- product-specific
- emotionally strong
- easy to read in Meta
- suitable beneath an Instant Experience cover
- connected to the artwork
- stronger than generic phrases such as Baseball History or Limited Edition

Good headline directions include the product title, recognised milestone, rivalry identity, era identity, ownership or scarcity.

Use the actual product.

Do not invent facts.

Do not apply Carousel character limits to the Instant Experience headline.

CALL TO ACTION

Use exactly:

{BASEBALL_INSTANT_EXPERIENCE_CTA}

INSTANT EXPERIENCE SETUP GUIDE

Use this exact workflow in the generated setup section:

1. In the Mockups download, use:
   06 - Instant Experience Cover Banner (Social)

2. In Meta Ads Manager, create or edit the Instant Experience using the Product template.

3. Select the connected Shopify Product Catalog.

4. Select the product set matching the chosen sport:
   {BASEBALL_INSTANT_EXPERIENCE_PRODUCT_SET_NAME}
   Use the actual connected Baseball product-set name if stored in the app.

5. Set products to Order dynamically unless the campaign requires a manually chosen product order.

6. Upload the Instant Experience Cover Banner from the Mockups ZIP as the cover image.

7. Keep Automatically group into relevant sections turned OFF unless the campaign specifically requires it.

8. Under Product headline, use:
   product.name

9. Under Product description, use:
   Limited Edition

10. Under Fixed button, set the label to:
    {BASEBALL_INSTANT_EXPERIENCE_CTA}

11. Set the Fixed button destination to the exact selected product-page URL supplied in the campaign form:
    {product_url}

12. Under URL parameters, use:
    {META_AD_URL_PARAMETERS}

13. Confirm the correct Baseball product catalogue/product set is attached.

14. Preview the Instant Experience on both Facebook and Instagram before publishing.

Do not invent the destination URL.

Use the exact product URL supplied by the user or selected product record.

INSTANT EXPERIENCE BANNER RULE

The how-to section must specifically tell the user to use:

06 - Instant Experience Cover Banner (Social)

from the Mockups ZIP download.

Do not tell the user to use a random lifestyle image, product-page frame, Reel, carousel card or unlabelled image.

OUTPUT EXACTLY IN THIS FORMAT

PRIMARY TEXT

[one complete primary-text ad]

HEADLINE

[one strongest headline]

CALL TO ACTION

{BASEBALL_INSTANT_EXPERIENCE_CTA}

INSTANT EXPERIENCE SETUP

[the required setup instructions]

FINAL QUALITY CHECK

Before returning the output, confirm:

- Exactly one primary text is provided.
- Exactly one headline is provided.
- CTA is {BASEBALL_INSTANT_EXPERIENCE_CTA}.
- Instant Experience setup instructions are included.
- The Mockups Instant Experience Cover Banner is specified.
- Shopify Product Catalog is specified.
- {BASEBALL_INSTANT_EXPERIENCE_PRODUCT_SET_NAME} product set is specified.
- Product headline is product.name.
- Product description is Limited Edition.
- The fixed-button destination uses the supplied product URL.
- The URL parameters field uses the exact supplied Meta URL parameters.
- The copy feels written for genuine baseball fans.
- The product or rivalry identity is clear.
- The opening is strong enough to stop attention.
- Ownership desire is present.
- Scarcity is clear.
- The copy is product-specific rather than generic.
- Country spelling and terminology are correct.
- Baseball terminology remains authentic.
- No unsupported fact has been invented.
- No five-copy variation block is returned.
- No Carousel rules have been applied to the Instant Experience headline."""


def build_ads_prompt(product_name, category, country, campaign_type, product_url=""):
    template_key = get_template_key(category, campaign_type)
    if template_key == "motorsport_carousel":
        prompt = build_motorsport_carousel_prompt(product_name, category, country, campaign_type)
    elif template_key == "baseball_instant_experience":
        prompt = build_baseball_instant_experience_prompt(
            product_name,
            category,
            country,
            campaign_type,
            product_url=product_url,
        )
    else:
        prompt = ""
    return compose_final_ads_prompt(
        prompt,
        category=category,
        country=country,
        campaign_type=campaign_type,
        include_primary_text_variations=template_key in TEMPLATES_WITH_PRIMARY_TEXT_VARIATIONS,
    )


def render_insufficient_winner_data():
    st.subheader("Insufficient winner data")
    st.caption("Approved winner examples have not been added for this category and campaign type yet.")


def render_meta_url_parameters_section(section_number):
    st.subheader(f"{section_number}. URL parameters")
    st.caption("Paste this into the Meta URL parameters field for every ad.")
    st.code(META_AD_URL_PARAMETERS, language="text")


def render_product_name_input():
    product_options = load_edition_ops_product_name_options()
    if product_options:
        return st.selectbox(
            "Product name",
            options=product_options,
            index=None,
            placeholder="Example: Six Laps Ahead",
            accept_new_options=True,
            filter_mode="fuzzy",
        )
    return st.text_input("Product name", placeholder="Example: Six Laps Ahead")


def render_supported_result(product_name, category, country, campaign_type, product_url=""):
    if get_template_key(category, campaign_type) == "baseball_instant_experience":
        st.subheader("1. Copy this ChatGPT prompt")
        render_prompt_copy_button(
            build_ads_prompt(product_name, category, country, campaign_type, product_url=product_url),
            f"ads-prompt::{category}::{country}::{campaign_type}::{product_name}",
        )

        st.subheader("2. Build it in Meta")
        st.caption("Follow the INSTANT EXPERIENCE SETUP section inside the generated prompt.")
        render_meta_url_parameters_section(3)
        return

    st.subheader("1. Upload these five images")
    for index, (title, body) in enumerate(IMAGE_ORDER, start=1):
        st.markdown(f"**Card {index} — {title}**")
        st.caption(body)
    st.caption("Upload them to Meta in this exact order before adding the carousel copy.")

    st.subheader("2. Copy this ChatGPT prompt")
    render_prompt_copy_button(
        build_ads_prompt(product_name, category, country, campaign_type, product_url=product_url),
        f"ads-prompt::{category}::{country}::{campaign_type}::{product_name}",
    )

    st.subheader("3. Build it in Meta")
    for index, step in enumerate(META_BUILD_ORDER, start=1):
        st.markdown(f"{index}. {step}")
    st.caption("Review every fact before publishing. Remove anything that cannot be confirmed from the product or artwork.")
    render_meta_url_parameters_section(4)


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
        product_name = render_product_name_input()
        category_col, country_col, campaign_col = st.columns(3)
        with category_col:
            category = st.selectbox("Category", CATEGORY_OPTIONS)
        with country_col:
            country = st.selectbox("Country", COUNTRY_OPTIONS)
        with campaign_col:
            campaign_type = st.selectbox("Campaign type", CAMPAIGN_TYPE_OPTIONS)
        product_url = ""
        if get_template_key(category, campaign_type) == "baseball_instant_experience":
            product_url = st.text_input(
                "Product page URL",
                placeholder="https://sportscave.com.au/products/example",
            )
        submitted = st.form_submit_button("Submit", type="primary")

    if not submitted:
        return

    validation_message = validate_ads_inputs(product_name, category, country, campaign_type, product_url=product_url)
    if validation_message:
        st.warning(validation_message)
        return

    if not get_template_key(category, campaign_type):
        render_insufficient_winner_data()
        return

    render_supported_result(product_name, category, country, campaign_type, product_url=product_url)


render_ads_page = render_page
render_marketing_factory_page = render_page
