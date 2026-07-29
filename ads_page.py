import hashlib
import html
import json
import logging
import re
import secrets
import time
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

import streamlit as st
import streamlit.components.v1 as components

from activity_log import record_activity_log
import ads_final_review
import ads_image_workflow
from ads_product_catalog import load_live_edition_product_rows
import dropbox_integration
import os_accounts


CATEGORY_OPTIONS = [
    "Select category",
    "NBA",
    "Motorsport",
    "Football",
    "Cricket",
    "Golf",
    "Horse Racing",
    "Baseball",
    "Combat",
    "Ice Hockey",
    "NFL",
    "Rugby Union",
    "Tennis",
    "Other",
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

CAROUSEL_CARD_MAX_CHARACTERS = 17
CAROUSEL_CARD_COUNT = 5
META_WINNER_COPY_BLOCK_VERSION = "SPORTS CAVE META WINNER COPY UPGRADE V1"
ADS_RESULT_STATE_KEY = "ads_generated_result"
ADS_IMAGE_STATE_KEY = "ads_generated_image_workflow"
ADS_REVIEW_STATE_KEY = "ads_final_review_workflow"
ADS_DIRECTORY_CACHE_SECONDS = 3 * 60
ADS_PRODUCT_IMAGES_FOLDER = "04_OUTPUT/product-images"
PRODUCT_URL_ERROR = "Enter a valid product page URL before submitting."

FINAL_REVIEW_HOW_TO_STEPS = (
    "1. Finish setting up the complete campaign in Meta Ads Manager.",
    "2. Take screenshots showing every part of the finished ad: primary text, headline, description, CTA, every creative or carousel card in order, and all relevant placement previews.",
    "3. For Instant Experience campaigns, also include the Instant Experience cover, catalogue setup and finished mobile preview.",
    "4. Open ChatGPT and upload all screenshots into the same conversation.",
    "5. Wait until every screenshot has finished uploading, then copy and paste the Final Ad Review prompt.",
    "The Product page URL will already be included in the copied prompt.",
)

FINAL_REVIEW_LANDING_PAGE_BLOCK_TEMPLATE = """PRODUCT LANDING PAGE

Product page URL: `{product_page_url}`

Open and inspect the live product landing page at the URL above.

Review every attached screenshot as one complete finished Meta advertising campaign. Inspect all screenshots before reaching a verdict. Treat the ad and the linked product page as one continuous customer journey rather than two separate pieces.

In addition to the existing campaign review, assess whether the product landing page flows naturally from the ad.

Check:

* Whether the product, artwork and promise shown in the ad immediately match the landing page
* Whether the strongest ad hook continues above the fold
* Whether the landing page preserves the same emotional angle, fan identity and collector positioning
* Whether the scarcity and edition messaging are consistent and believable
* Whether the target market, currency, price, shipping and delivery information feel aligned
* Whether framed and unframed options are easy to understand
* Whether the primary CTA is clear and continues the action promised by the ad
* Whether reviews, guarantees, payment security and other trust signals appear at the right stage
* Whether the product media supports the same premium impression created by the ad
* Whether the mobile page hierarchy creates unnecessary friction before the customer can choose a variant or buy
* Whether any copy, offer, image or expectation changes between the ad and landing page could cause hesitation or abandonment

Identify any disconnect where the ad creates a desire or expectation that the landing page fails to continue.

Recommend exact landing-page changes that would make the product page flow more naturally from this specific campaign and improve conversion without making Sports Cave look like a discount store.

Prioritise recommendations by likely sales impact. Clearly separate:

1. Changes required before launching
2. Strong improvements worth making
3. Optional tests for later

Give a final verdict on whether the complete ad-to-landing-page journey is ready to launch.

If the live product page cannot be accessed, state that clearly. Do not invent page content. Complete the ad review from the attached screenshots and specify which product-page screenshots are needed to finish the landing-page assessment.

Integrate these findings into the existing review structure. Do not duplicate sections or replace the existing scoring format."""

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
    "NBA": "mentality, rivalry, dynasty, final shot, court presence, championship nights and legacy",
    "Motorsport": "circuit, machine, rivalry, pressure, noise, era, mountain and race memory, F1, V8 Supercars, MotoGP and NASCAR only when supported",
    "Football": "matchday, captain, final, club era, rivalry, last dance, national pride and terrace memory",
    "Cricket": "crease, spell, innings, summer, Ashes, ground, session pressure and era",
    "Golf": "major pressure, Sunday calm, fairway memory, final putt, champion rhythm and clubhouse legacy",
    "Horse Racing": "track, cup day, final straight, stable pride, racing era and winning memory",
    "Baseball": "diamond, home run, October, rivalry, ballpark memory and legacy",
    "Combat": "walkout, fight night, boxing, UFC, rivalry, discipline, pressure, legacy and champion mentality",
    "Ice Hockey": "rink pressure, playoff moment, rivalry, captaincy, cold arena noise and legacy",
    "NFL": "Sunday pressure, franchise era, rivalry, quarterback moment, gridiron memory and legacy",
    "Rugby Union": "test match pressure, national pride, tours, rivalry, jersey pride, final whistle and rugby legacy",
    "Tennis": "court pressure, final set, rivalry, grass or hardcourt era and champion poise",
    "Other": "identity, memory, era, rivalry, pressure, fan pride, collector ownership and the defining moment",
}

SUPPORTED_AD_CATEGORIES = tuple(CATEGORY_OPTIONS[1:])
CATEGORY_SPECIFIC_CAMPAIGN_TYPES = ("Carousel", "Instant Experience", "Single Image / Video")

CATEGORY_WINNER_ANGLES = {
    "Football": {
        "audience": "real football supporters, soccer fans where the market expects that term, national-team fans, club-era collectors and serious football collectors",
        "emotion": "football legacy, matchday memory, finals, rivalries, national pride, club eras, last dances, supporters and wall-worthy moments",
        "carousel_flow": "product hero -> football moment or legacy -> supporter identity -> wall, cave or home bar ownership -> only-100 scarcity",
        "ie_setting": "premium football collector room, home bar, collection wall or sports room",
        "headline_examples": "Football Glory; Only 100 Made; For Real Fans; Claim Yours; Legends Framed",
        "description_examples": "Limited Edition; Matchday Memory; Supporter Wall; Claim Edition; No Second Run",
        "country_note": "UK must use football and supporters, not soccer. USA should use soccer when association football is intended. AU, Canada and NZ should use football or soccer according to product context.",
    },
    "NBA": {
        "audience": "NBA fans, basketball collectors, era-debate fans and people who grew up watching basketball icons",
        "emotion": "greatness, rivalry, mentality, icons, championship nights, clutch moments, legacy and era debates",
        "carousel_flow": "icon -> moment -> mentality -> wall ownership -> only-100 scarcity",
        "ie_setting": "premium sports room, office, collector lounge or man cave",
        "headline_examples": "Hoops Legacy; Only 100 Made; Clutch Era; Claim Yours; Icons Framed",
        "description_examples": "Court Memory; For NBA Fans; Numbered Art; Sports Room; No Second Run",
        "country_note": "Keep basketball language natural for the selected market. Do not invent stats, rings, teams or records unless the product title confirms them.",
    },
    "Motorsport": {
        "audience": "race fans, garage collectors, motorsport loyalists and fans who remember the sound, pressure, machine and rivalry",
        "emotion": "raw speed, Bathurst-style nostalgia where supported, F1 precision, V8 Supercars, MotoGP aggression, NASCAR intensity, race-day memory, legends, rivalry and garage pride",
        "carousel_flow": "machine or driver identity -> race-day memory -> legacy -> garage, cave or home bar ownership -> only-100 scarcity",
        "ie_setting": "premium garage, workshop, home bar or motorsport collector wall",
        "headline_examples": "Race Legacy; Only 100 Made; Still Roars; Claim Yours; Garage Wall",
        "description_examples": "Race Day Art; Engine Memory; Numbered Run; Cave Ready; No Second Run",
        "country_note": "Use Bathurst, the Mountain, F1, V8 Supercars, MotoGP, NASCAR, track, driver, year or result only when supported by the product title or artwork.",
    },
    "Cricket": {
        "audience": "cricket fans, cricket tragics, collectors, Test-match obsessives and summer-sport loyalists",
        "emotion": "summer sound, Test match memory, Ashes-style rivalry only when supported, innings, wickets, heroes and backyard-to-stadium nostalgia",
        "carousel_flow": "product identity -> innings or match memory -> cricket identity -> study, home bar or sports-room ownership -> only-100 scarcity",
        "ie_setting": "premium home bar, study, sports room or cricket collection wall",
        "headline_examples": "Cricket Memory; Only 100 Made; Final Session; Claim Yours; Heroes Framed",
        "description_examples": "For Cricket Fans; Summer Wall; Numbered Art; Home Bar Ready; No Second Run",
        "country_note": "AU and UK can lean into serious cricket-fan language, but avoid forced slang and do not invent Ashes, innings, wickets or venues unless confirmed.",
    },
    "Golf": {
        "audience": "golf fans, major-week watchers, Sunday-pressure fans, clubhouse collectors and people who love the calm before the final putt",
        "emotion": "major pressure, Sunday calm, final putts, fairway memory, rivalries, eras, course atmosphere and clubhouse pride",
        "carousel_flow": "product identity -> major, round or final-putt memory -> golf identity -> office, study or clubhouse wall ownership -> only-100 scarcity",
        "ie_setting": "premium study, clubhouse lounge, office, bar or golf collector wall",
        "headline_examples": "Major Week; Only 100 Made; Sunday Calm; Claim Yours; Final Putt",
        "description_examples": "For Golf Fans; Numbered Art; Study Wall; Clubhouse Ready; No Second Run",
        "country_note": "Do not invent tournament, course, score, ranking, major title, trophy or champion status unless the product title confirms it.",
    },
    "Horse Racing": {
        "audience": "race-day fans, punters, racing collectors and people who remember the thunder down the straight",
        "emotion": "race day, legendary finishes, cup-day emotion, silks, turf, winning post, punters and collectors",
        "carousel_flow": "runner or race identity -> straight or finish memory -> racing emotion -> lounge, bar or collector-wall ownership -> only-100 scarcity",
        "ie_setting": "premium lounge, bar, racing collection wall or timber and leather interior",
        "headline_examples": "Race Day Framed; Only 100 Made; Final Straight; Claim Yours; Turf Memory",
        "description_examples": "Racing Wall; Cup Day Feel; Numbered Art; Bar Ready; No Second Run",
        "country_note": "Do not invent horse, race, jockey, trophy, odds or result. Use cup-day cues only when the product supports them.",
    },
    "Baseball": {
        "audience": "baseball fans, collectors, rivalry fans and people who grew up with ballpark memory",
        "emotion": "legends, rivalry, home runs, ballpark memory, generational icons, collectors and America's game",
        "carousel_flow": "product identity -> ballpark or swing memory -> fan emotion -> sports-room or collector-wall ownership -> only-100 scarcity",
        "ie_setting": "premium sports room, office, collector lounge, home bar or baseball wall",
        "headline_examples": "Ballpark Memory; Only 100 Made; Baseball Glory; Claim Yours; Legends Framed",
        "description_examples": "For Baseball Fans; Numbered Art; Sports Room; Wall Ready; No Second Run",
        "country_note": "Keep baseball terms baseball-specific in every market. Do not invent stats, records, seasons or licensing claims.",
    },
    "Combat": {
        "audience": "boxing fans, UFC fans, combat-sport collectors and fans who remember the walkout, pressure and tension",
        "emotion": "fight night, walkout, boxing pressure, UFC intensity, rivalry, legacy, warrior mentality and one-shot moments",
        "carousel_flow": "fighter or event identity -> fight-night pressure -> fan tension -> fight room, gym or wall ownership -> only-100 scarcity",
        "ie_setting": "dark premium gym, fight room, home bar or combat collector wall",
        "headline_examples": "Fight Night Art; Only 100 Made; Walkout Ready; Claim Yours; Legacy Framed",
        "description_examples": "For Fight Fans; Numbered Art; Fight Room; Wall Ready; No Second Run",
        "country_note": "Use boxing, UFC, belts, opponent, result, title, record or sanctioning body only when supported by the product title or artwork.",
    },
    "Ice Hockey": {
        "audience": "hockey fans, loyal supporters, playoff-night obsessives and cold-arena collectors",
        "emotion": "frozen arenas, overtime, rivalries, legends, team pride, playoff nights, cold-blooded moments and loyal fans",
        "carousel_flow": "product identity -> rink or overtime memory -> fan loyalty -> basement bar, sports room or wall ownership -> only-100 scarcity",
        "ie_setting": "premium sports room, basement bar, collector wall or hockey room",
        "headline_examples": "Rink Legacy; Only 100 Made; Overtime Feel; Claim Yours; Hockey Wall",
        "description_examples": "For Hockey Fans; Numbered Art; Sports Room; Wall Ready; No Second Run",
        "country_note": "Do not invent cup wins, team names, scores or playoff facts unless the product title confirms them.",
    },
    "NFL": {
        "audience": "NFL fans, game-day loyalists, gridiron collectors and fans who live for the season",
        "emotion": "Sunday memory, gridiron legacy, game-day pride, rivalries, championship pressure and helmet-era nostalgia",
        "carousel_flow": "product identity -> Sunday or game-day memory -> fan pride -> sports-room or home-theatre ownership -> only-100 scarcity",
        "ie_setting": "premium sports room, home theatre, basement bar or NFL collector wall",
        "headline_examples": "Sunday Legacy; Only 100 Made; Game Day Wall; Claim Yours; Gridiron Art",
        "description_examples": "For NFL Fans; Numbered Art; Sports Room; Wall Ready; No Second Run",
        "country_note": "Do not invent Super Bowl, stats, teams, scores or records unless the product title confirms them.",
    },
    "Rugby Union": {
        "audience": "rugby supporters, national-team loyalists, tour watchers, test-match fans and collectors who understand the pressure of the jersey",
        "emotion": "test-match pressure, national pride, tours, rivalry, final whistle, jersey pride, tradition and rugby legacy",
        "carousel_flow": "product identity -> test, tour or rivalry memory -> rugby identity -> clubroom, sports-room or home-bar ownership -> only-100 scarcity",
        "ie_setting": "premium clubroom, home bar, sports room, study or rugby collector wall",
        "headline_examples": "Test Match Art; Only 100 Made; Jersey Pride; Claim Yours; Rugby Legacy",
        "description_examples": "For Rugby Fans; Numbered Art; Clubroom Wall; Supporter Ready; No Second Run",
        "country_note": "Keep rugby union language distinct from rugby league. Do not invent caps, tries, scores, tours, trophies, teams or World Cup claims unless confirmed.",
    },
    "Tennis": {
        "audience": "tennis fans, rivalry watchers, collectors and fans who remember match point pressure",
        "emotion": "rivalries, match point, grace, pressure, eras, icons, farewell moments and collectors",
        "carousel_flow": "product identity -> match-point or era memory -> tennis emotion -> office, lounge or study ownership -> only-100 scarcity",
        "ie_setting": "premium office, lounge, gallery wall or collector study",
        "headline_examples": "Match Point Art; Only 100 Made; Court Legacy; Claim Yours; Icons Framed",
        "description_examples": "For Tennis Fans; Numbered Art; Study Wall; Gallery Ready; No Second Run",
        "country_note": "Use Centre Court style for UK only when supported. Do not invent tournament, title, ranking or record.",
    },
    "Other": {
        "audience": "sports fans, collectors and buyers who recognise the selected subject, era, rivalry, person, venue or defining moment",
        "emotion": "identity, memory, legacy, rivalry, pressure, pride, nostalgia, a verified moment, collector ownership and the feeling that the moment deserves the wall",
        "carousel_flow": "product identity -> verified moment or subject memory -> fan identity -> wall, cave, home bar or office ownership -> only-100 scarcity",
        "ie_setting": "premium collector room, sports room, home bar, office, study or gallery wall",
        "headline_examples": "Moment Framed; Only 100 Made; Claim Yours; Fan Memory; Wall Ready",
        "description_examples": "Numbered Art; Collector Wall; Limited Run; Cave Ready; No Second Run",
        "country_note": "Use only facts confirmed by the product title, artwork or supplied notes. Do not borrow terminology from another sport just to sound specific.",
    },
}

SUPPORTED_TEMPLATES = {
    ("Motorsport", "Carousel"): "motorsport_carousel",
    ("Baseball", "Instant Experience"): "baseball_instant_experience",
    ("Football", "Instant Experience"): "football_instant_experience",
}

GENERIC_CAMPAIGN_TEMPLATES = {
    "Carousel": "generic_carousel",
    "Instant Experience": "generic_instant_experience",
    "Single Image / Video": "generic_single_image_video",
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

CAROUSEL_VISUAL_ROLES = {
    "motorsport_carousel": (
        "Product Identity",
        "Race Or Moment",
        "Legacy",
        "Fan Ownership",
        "Scarcity",
    ),
    "default": (
        "Product Identity",
        "Moment / Legacy",
        "Emotional Hook",
        "Fan Ownership",
        "Scarcity",
    ),
}

VISUAL_COUNTRY_DIRECTIONS = {
    "Australia": (
        "Use grounded contemporary Australian residential architecture, honest material texture "
        "and natural Australian light. Do not use forced slang or novelty Australiana."
    ),
    "USA": (
        "Use premium American residential scale and collector styling with believable proportions. "
        "Do not turn the setting into a retail sports display."
    ),
    "UK": (
        "Use a refined British period or contemporary interior as the product mood requires, with "
        "credible local architecture and restrained natural light."
    ),
    "Canada": (
        "Use authentic Canadian residential material warmth and light without assuming hockey or "
        "adding stereotyped cabin styling."
    ),
    "New Zealand": (
        "Use authentic New Zealand residential architecture, natural light and material restraint "
        "without borrowing Australian identity language."
    ),
}

COUNTRY_LANGUAGE_PROFILES = {
    "Australia": {
        "heading": "COUNTRY LANGUAGE AND LOCALISATION — AUSTRALIA",
        "english_variant": "natural Australian English",
        "spellings": "colour, favourite, organise, personalised, centre, licence as a noun, licensed as a verb or adjective, travelled, travelling",
        "terminology": "delivery, free delivery, add to cart, shop, order, collector, limited edition, framed artwork, race day, and footy only when the selected sport and context make it genuinely appropriate",
        "sports": "For Australian motorsport, cricket, basketball, combat, golf, tennis, horse racing and other categories, use terminology Australian fans naturally expect. Motorsport may reference Bathurst, the Mountain, race day, touring-car heritage, Supercars, F1, MotoGP or NASCAR only when supported by the selected product. Cricket language should sound Australian rather than American. Association football should normally be called football or soccer according to the specific Australian audience and existing category naming.",
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
    "AU": "Australia",
    "United States": "USA",
    "US": "USA",
    "United Kingdom": "UK",
    "Great Britain": "UK",
    "NZ": "New Zealand",
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
    cleaned = re.sub(r"[\x00-\x1f\x7f]", " ", str(product_name or ""))
    return re.sub(r"\s+", " ", cleaned).strip()


def _clean_product_url(product_url):
    return str(product_url or "").strip()


def is_valid_product_page_url(product_url):
    clean_url = _clean_product_url(product_url)
    if not clean_url:
        return False
    if re.search(r"\s", clean_url):
        return False
    parsed = urlparse(clean_url)
    if parsed.scheme not in {"http", "https"}:
        return False
    if not parsed.netloc:
        return False
    return True


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


def _edition_ops_product_handle_from_row(row):
    if not isinstance(row, dict):
        return ""
    return _normalise_option_label(
        row.get("shopify_handle")
        or row.get("Shopify handle")
        or row.get("product_handle")
        or row.get("handle")
        or row.get("Handle")
    )


def _edition_ops_product_id_from_row(row):
    if not isinstance(row, dict):
        return ""
    return _normalise_option_label(
        row.get("product_id")
        or row.get("Product ID")
        or row.get("shopify_product_id")
        or row.get("id")
        or _edition_ops_product_handle_from_row(row)
    )


def _edition_ops_product_option_label(row, duplicate_titles=None):
    product_name = _product_name_from_edition_ops_row(row)
    handle = _edition_ops_product_handle_from_row(row)
    duplicate_titles = duplicate_titles or set()
    if product_name and handle and product_name.casefold() in duplicate_titles:
        return f"{product_name} ({handle})"
    return product_name or handle


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


def load_edition_ops_product_rows(
    snapshot_path=EDITION_OPS_SNAPSHOT_PATH,
    *,
    live_loader=None,
):
    rows = []
    snapshot_path = Path(snapshot_path)
    should_load_live = live_loader is not None or snapshot_path == EDITION_OPS_SNAPSHOT_PATH
    if should_load_live:
        loader = live_loader or load_live_edition_product_rows
        try:
            live_rows = loader()
        except Exception:
            live_rows = []
        if isinstance(live_rows, list):
            rows.extend(live_rows)

    session_rows = st.session_state.get(EDITION_OPS_ROWS_SESSION_KEY, [])
    if isinstance(session_rows, list):
        rows.extend(session_rows)
    rows.extend(_edition_ops_rows_from_local_snapshot(snapshot_path))

    unique_rows = []
    seen_rows = set()
    for row in rows:
        product_name = _product_name_from_edition_ops_row(row)
        handle = _edition_ops_product_handle_from_row(row)
        row_key = (product_name.casefold(), handle.casefold())
        if row_key == ("", "") or row_key in seen_rows:
            continue
        unique_rows.append(row)
        seen_rows.add(row_key)
    return unique_rows


def load_edition_ops_product_name_options(
    snapshot_path=EDITION_OPS_SNAPSHOT_PATH,
    *,
    live_loader=None,
):
    unique_rows = load_edition_ops_product_rows(
        snapshot_path,
        live_loader=live_loader,
    )

    options = []
    seen = set()
    title_counts = {}
    for row in unique_rows:
        product_name = _product_name_from_edition_ops_row(row)
        if product_name:
            key = product_name.casefold()
            title_counts[key] = title_counts.get(key, 0) + 1
    duplicate_titles = {key for key, count in title_counts.items() if count > 1}

    for row in unique_rows:
        option_label = _edition_ops_product_option_label(row, duplicate_titles)
        key = option_label.casefold()
        if option_label and key not in seen:
            options.append(option_label)
            seen.add(key)
    return options


def resolve_edition_ops_product_id(product_name):
    selected = _normalise_option_label(product_name)
    if not selected:
        return ""
    rows = load_edition_ops_product_rows()
    title_counts = {}
    for row in rows:
        title = _product_name_from_edition_ops_row(row)
        if title:
            title_counts[title.casefold()] = title_counts.get(title.casefold(), 0) + 1
    duplicate_titles = {key for key, count in title_counts.items() if count > 1}
    for row in rows:
        option_label = _edition_ops_product_option_label(row, duplicate_titles)
        if selected.casefold() == option_label.casefold():
            return _edition_ops_product_id_from_row(row)
    return ""


def render_prompt_copy_button(prompt_text, key, label="Copy Prompt", success_label="Prompt copied"):
    prompt_text_json = json.dumps(str(prompt_text or ""))
    safe_label = html.escape(label)
    safe_success_label = html.escape(success_label)
    button_id = f"ads-copy-prompt-{hashlib.sha1(str(key).encode('utf-8')).hexdigest()[:12]}"
    status_id = f"{button_id}-status"
    components.html(
        f"""
        <div style="padding:2px 0;">
          <button
            id="{button_id}"
            type="button"
            aria-label="{safe_label}"
            aria-describedby="{status_id}"
            style="width:100%;border:1px solid rgba(11,11,13,0.55);border-radius:14px;padding:12px 14px;background:#FFFFFF;color:#0B0B0D;font-weight:700;font-size:0.95rem;cursor:pointer;box-sizing:border-box;"
          >
            {safe_label}
          </button>
          <div id="{status_id}" role="status" aria-live="polite" style="margin-top:6px;min-height:18px;color:#5C4309;font-size:0.82rem;"></div>
        </div>
        <script>
        (() => {{
          const button = document.getElementById("{button_id}");
          const status = document.getElementById("{status_id}");
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
              button.innerText = "{safe_success_label}";
              status.innerText = "{safe_success_label}";
            }} catch (error) {{
              button.innerText = "Copy failed";
              status.innerText = "Copy failed";
            }}
            setTimeout(() => {{
              button.innerText = originalLabel;
              status.innerText = "";
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
    if not is_valid_product_page_url(product_url):
        return PRODUCT_URL_ERROR
    return ""


def _template_slug(value):
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").casefold()).strip("_")


def get_category_specific_template_key(category, campaign_type):
    if category in SUPPORTED_AD_CATEGORIES and campaign_type in CATEGORY_SPECIFIC_CAMPAIGN_TYPES:
        return f"{_template_slug(category)}_{_template_slug(campaign_type)}"
    return None


def get_template_key(category, campaign_type):
    return SUPPORTED_TEMPLATES.get((category, campaign_type)) or get_category_specific_template_key(
        category,
        campaign_type,
    )


def get_winner_pattern_key(category, campaign_type):
    return get_template_key(category, campaign_type) or GENERIC_CAMPAIGN_TEMPLATES.get(campaign_type)


def uses_generic_winner_pattern(category, campaign_type):
    return not bool(get_template_key(category, campaign_type)) and bool(GENERIC_CAMPAIGN_TEMPLATES.get(campaign_type))


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


def build_product_lock_visual_rules():
    return """PRODUCT LOCK - INCLUDE IN EVERY RETURNED IMAGE PROMPT

Use the uploaded Sports Cave product image as the exact reference.

Keep the uploaded artwork and frame exactly the same.

Do not redesign, repaint, redraw, replace, reinterpret or regenerate the artwork inside the frame.

Do not change the athlete or subject, face, vehicle, uniform, livery, colours, text, badge, edition plate, plaque, signature, layout, crop, composition, frame colour, frame shape or landscape proportions.

Do not blur, stretch, warp, bend, squash or distort the artwork or frame.

The artwork must remain sharp, rectangular, correctly aligned and physically believable inside the frame.

Do not generate a lookalike version of the artwork."""


def build_frame_and_glass_visual_rules():
    return """FRAME AND GLASS REALISM - INCLUDE IN EVERY RETURNED IMAGE PROMPT

The black frame must appear to be a real premium framed product with:

- realistic black timber or frame depth
- sharp square corners
- subtle physical texture
- clean joins
- correct landscape proportions
- believable mounting hardware or wall placement
- accurate perspective
- correct scale for the room
- real glass over the artwork
- soft environmental reflections
- subtle controlled glare
- realistic highlight streaks
- a natural shadow behind and below the frame
- reflections consistent with the room's windows and lighting

The glare must make the frame feel expensive and real without obscuring the artwork.

The artwork must look mounted naturally. It must not look pasted onto the wall."""


def build_room_realism_visual_rules():
    return """DYNAMIC ROOM REALISM - INCLUDE IN EVERY RETURNED IMAGE PROMPT

Create an interior that looks like real architectural and residential photography, not a glossy AI showroom render.

The room must feel physically believable, premium but lived-in, masculine without becoming cliched, clean but not sterile, collector-worthy, subtly imperfect and appropriate for a discerning 30-50-year-old fan.

Require believable residential proportions, plausible room depth, correct ceiling and wall geometry, straight vertical architecture, realistic furniture scale, natural furniture placement, genuinely textured materials, subtle signs that a real person lives there, realistic daylight and practical-light interaction, natural wall shadows, realistic floor and wall joins, controlled cinematic contrast and a natural interior-photography lens and perspective.

Do not use an excessively wide or distorted camera angle, perfect artificial symmetry unless architecturally justified, an empty computer-generated showroom feeling or a repeated generic stock-room composition.

Avoid warped walls, impossible windows, bent shelves, floating furniture, malformed lamps, unusable layouts, inconsistent reflections, duplicate objects, random decorative objects, fake luxury, plastic materials, oversized rooms with no believable function, excessive blur, overprocessed HDR, unrealistic orange lighting and any obvious AI-room appearance."""


def build_last_image_variation_visual_rules():
    return """LAST-IMAGE VARIATION LOCK - INCLUDE IN EVERY RETURNED IMAGE PROMPT

Before choosing this visual setting:

- Analyze the uploaded Sports Cave product image.
- Inspect every previously generated image for this same product that is visible in the current ChatGPT conversation.
- Identify the room types, houses, architecture, wall colours, wall materials, furniture layouts, lighting, time of day, camera angles, camera heights, camera distances, artwork placements and compositions already used.
- Create a noticeably different house and visual setting from the recent images.
- Use a new room type or architectural area.
- Use a new wall colour and wall material.
- Use a new principal furniture arrangement.
- Use a new lighting direction and preferably a different time of day.
- Use a new camera height, camera distance and camera angle.
- Change the artwork's placement and surrounding negative space while keeping the supplied frame geometrically correct.
- Make the difference obvious at thumbnail size.
- Do not merely recolour the same room, move one item, shift the camera slightly or reuse a generic stock-room layout.
- Continue conveying the exact emotional purpose of this card or campaign image.
- Never sacrifice the product lock, artwork accuracy, frame proportions or glass realism to create variation.
- Do not invent product facts or add unapproved sports props.

If previous images for this product are unavailable in the conversation, create a fresh interpretation and ensure every image within the current run is strongly differentiated from the others.

Repeat this complete LAST-IMAGE VARIATION LOCK inside the returned standalone image prompt. Do not refer to rules elsewhere in the response."""


def build_sport_country_visual_adaptation(category, country):
    category_label = _normalise_option_label(category) or "selected sport"
    country_label = normalize_country_language_key(country) or _normalise_option_label(country) or "selected country"
    angle = get_category_winner_angle(category)
    category_mood = angle.get("emotion") or CATEGORY_COPY_CUES.get(category, CATEGORY_COPY_CUES["Other"])
    country_direction = VISUAL_COUNTRY_DIRECTIONS.get(
        country_label,
        "Use credible residential architecture, natural light and materials appropriate to the selected country without stereotypes.",
    )
    return f"""SPORT AND COUNTRY VISUAL ADAPTATION - INCLUDE IN EVERY RETURNED IMAGE PROMPT

Selected sport category: {category_label}
Selected country: {country_label}

Build the visual mood from the selected product title and its verified emotional meaning. A nostalgic title, rivalry, championship, tribute, comeback, record, iconic moment or modern achievement must not receive the same generic room direction.

For {category_label}, express the atmosphere through architecture, materiality, restrained colour, wall finish, furniture tone, lighting, mood, composition, energy and the relationship between the room and the artwork. Relevant emotional territory: {category_mood}.

Country direction: {country_direction}

Do not create sporting atmosphere through obvious props. Do not add sports balls, bats, helmets, jerseys, trophies, figurines, toy cars, novelty signs, fake memorabilia, recognisable team logos, random athlete photographs, team-coloured clutter, extra framed sports art, retail display fixtures, fake collector items or neon signs unless an existing approved creative direction explicitly requires an extremely subtle one.

Do not use forced slang, cultural stereotypes or novelty sport decor."""


def get_carousel_visual_roles(template_key):
    return CAROUSEL_VISUAL_ROLES.get(template_key, CAROUSEL_VISUAL_ROLES["default"])


def build_carousel_square_format_lock():
    return """SQUARE FORMAT — MANDATORY:
Generate this image on a true 1:1 square canvas at exactly 1024 × 1024 pixels. The final delivered image must be square—not landscape, portrait, widescreen or cropped from another aspect ratio. Compose the entire room, framed product and negative space specifically for a square canvas. Before delivering the image, verify that its width and height are identical. If the result is not exactly 1:1, regenerate it as a true 1024 × 1024 square image."""


def build_carousel_final_square_format_check():
    return "FINAL FORMAT CHECK: Output one true 1024 × 1024 image only. Width must equal height. Never output a landscape or portrait image."


def build_carousel_card_one_product_hero_lock():
    return """CARD 1 PRODUCT-HERO COMPOSITION — MANDATORY:
This is the first and most important carousel image and must be the closest and most product-focused image in the complete five-card sequence. Use a premium close or medium-close product-hero composition in which the complete framed artwork is the dominant visual subject and immediately stops the viewer at thumbnail size. The complete framed artwork should occupy approximately 65-80% of the square image's width while remaining fully visible with breathing room around it, including all four outer edges and corners. Use a premium, realistic room setting, but keep furniture and architectural details secondary. Do not use a wide room view. Do not place the frame far away, make it small or allow the environment to compete with the product. Photograph it almost straight-on or from a very restrained natural angle so the artwork, frame depth and design remain easy to inspect. Preserve enough surrounding wall and setting to feel aspirational and physically believable.

Card 1 must:
- Predominantly display the framed product.
- Show the complete outer frame without cropping any edge.
- Keep the artwork large, sharp and readable.
- Use a close or medium-close camera distance.
- Still show a tasteful portion of the room around it.
- Avoid wide establishing shots.
- Avoid furniture blocking or visually competing with the frame.
- Retain all existing product-lock and artwork-preservation instructions."""


def build_carousel_product_dominance_principle_lock():
    return """PRODUCT DOMINANCE PRINCIPLE — MANDATORY:
We are selling the framed Sports Cave edition, not the room. The room may enhance the product, provide scale and create aspiration, but it must never overpower the framed artwork or make it look small. In every carousel card, the framed edition must be dominant, instantly recognizable and readable as a small Facebook carousel card on a phone. Use varied rooms, wall colours, camera positions and viewing angles without creating distant product shots. Maintain a cohesive premium campaign while ensuring every card works independently as a Facebook advertisement."""


def build_carousel_card_camera_distance_lock(index):
    if index == 1:
        return build_carousel_card_one_product_hero_lock()
    if index in {2, 3, 4}:
        return """CARDS 2-4 PRODUCT-DOMINANT LIFESTYLE COMPOSITION — MANDATORY:
Use a medium lifestyle composition, not a distant wide-angle room shot. The complete framed artwork should generally occupy approximately 50-70% of the square image's width. The product must remain instantly recognizable and readable when viewed as a small Facebook carousel card on a phone. Show enough of the room to create variety, context, ownership appeal and atmosphere, but do not place the frame far away, at the end of a large room or as a small background decoration. Never use an extreme wide shot, excessive empty space or oversized furniture that visually reduces the product. Keep the complete outer frame visible with breathing room around it and do not crop any part of the artwork or frame."""
    return """CARD 5 PRODUCT-PROMINENT SCARCITY COMPOSITION — MANDATORY:
Keep the framed edition prominent even when the card focuses on scarcity, edition details or a different environment. The framed edition must remain one of the largest elements in the composition and must not become secondary to scarcity messaging, furniture, architecture or atmosphere. Do not zoom out significantly farther than Cards 2-4. Keep the complete outer frame visible with breathing room around it and do not crop any part of the artwork or frame."""


def build_carousel_strict_product_lock():
    return """STRICT PRODUCT LOCK — MANDATORY:
Use the uploaded product image as the exact compositing source. Preserve the exact artwork, outer frame, colours, text, typography, badges, edition details, crop and internal composition. Do not redraw, regenerate, reinterpret or replace anything inside the frame. Do not change the frame colour, thickness, shape, proportions or material. Do not crop, stretch, warp, bend, blur or distort the artwork or frame. Keep the complete outer frame visible. The artwork must remain sharp and visually legible. Ensure the frame is mounted at a believable height and realistic scale."""


def build_carousel_photorealism_lock():
    return """CAROUSEL PHOTOREALISM REQUIREMENTS — MANDATORY:
Make the room, frame and product placement resemble a genuine high-end interior photograph, not an AI-generated room or digital render. Use believable architecture, correct perspective, natural proportions and physically accurate scale. Create realistic contact shadows behind and below the frame. Use subtle, controlled glass reflections without obscuring the artwork. Give the frame convincing timber depth, sharp corners, natural texture and accurate mounting. Use realistic natural or practical lighting with consistent direction and colour temperature. Avoid plastic-looking surfaces, excessive HDR, artificial glow, oversharpening and cinematic effects that make the image look generated. Avoid warped walls, bent furniture, duplicate objects, melted textures, impossible shadows, distorted decor, floating objects and inconsistent reflections. Keep room styling restrained and believable with a small number of purposeful objects rather than AI-generated clutter. Do not add people unless the individual carousel concept explicitly requires them; if people are required, they must look anatomically and photographically realistic."""


def build_carousel_image_prompt_schema(index, role):
    square_lock = build_carousel_square_format_lock()
    product_dominance_lock = build_carousel_product_dominance_principle_lock()
    camera_distance_lock = build_carousel_card_camera_distance_lock(index)
    strict_product_lock = build_carousel_strict_product_lock()
    photorealism_lock = build_carousel_photorealism_lock()
    final_check = build_carousel_final_square_format_check()
    return f"""Card {index} — [exact generated Card {index} headline]
Matching description: [exact generated Card {index} description]
Visual purpose: {role}
Image prompt:
{square_lock}

Card-specific visual purpose: {role}

{product_dominance_lock}

{camera_distance_lock}

{strict_product_lock}

{photorealism_lock}

[Then continue this same standalone prompt with the exact uploaded-product/artwork lock, room, camera, lighting and realism instructions, previous-image variation lock, sport and country adaptation, prohibited elements, and any relevant card-specific selling idea.]

{final_check}"""


def build_carousel_visual_output_requirements(template_key):
    roles = get_carousel_visual_roles(template_key)
    schema = []
    for index, role in enumerate(roles, start=1):
        schema.append(build_carousel_image_prompt_schema(index, role))
    schema_text = "\n".join(schema).rstrip()
    return f"""CAROUSEL VISUAL STORY REQUIREMENTS

After every existing Carousel copy, card, primary-text, CTA, setup and URL-parameter field, output exactly {CAROUSEL_CARD_COUNT} complete image-generation prompts. Map one prompt to each generated card in the existing approved order and role structure.

Every generated carousel image prompt must begin with the mandatory square-format lock below, then follow the required prompt order. No carousel image prompt may omit, weaken, paraphrase or contradict the square-format lock, product-dominance principle, card camera-distance lock, strict product lock or carousel photorealism requirements. No card-specific template, sport adaptation, country direction, previous-image variation instruction, scarcity idea or room-composition idea may override the 1:1 square requirement, product prominence, complete-frame visibility, artwork accuracy or photorealism requirements.

For every generated carousel prompt, use this priority order:

1. Mandatory 1:1 square-format lock
2. Card-specific visual purpose
3. Product-dominance principle
4. Card camera-distance lock
5. Strict product lock
6. Carousel photorealism requirements
7. Exact uploaded-product/artwork lock
8. Room, camera, lighting and realism instructions
9. Previous-image variation lock
10. Sport and country adaptation
11. Prohibited elements
12. Final mandatory square-format check

Each prompt must be based on the selected product name, selected sport, selected country, the emotional meaning of that specific card, that card's exact generated headline, that card's exact generated description, its role and position in the overall story, the uploaded product artwork, and only verified product and scarcity information already permitted by the copy system.

The five images must form one premium visual story, not five random mockups. Maintain compatible colour restraint, premium photographic quality, related lighting character, correct black-frame presentation and a shared Sports Cave collector tone without making the rooms identical.

Each visual must clearly support its assigned card message while the framed product remains the unmistakable hero. Card 1 must deliver the strongest immediate product presentation and be the most zoomed-in card. Cards 2-5 may show more of the environment, but only moderately; none may become a distant room shot. Card 5 must deliver the strongest truthful scarcity or final-claim presentation while keeping the product prominent.

Use this direct conversion-focused visual progression while preserving the selected template's approved role labels:

- Card 1: a clean product-hero presentation.
- Card 2: a desirable ownership setting.
- Card 3: a premium collector display suited to the selected category.
- Card 4: an emotional lifestyle, memory or legacy presentation.
- Card 5: a scarcity-focused view that gives the existing edition plate or numbered detail prominence when verified while keeping the complete outer frame visible.

For every card, make the exact generated headline, exact generated description, creative direction and image prompt communicate the same clear selling idea. The room, wall, lighting, angle and composition must visibly support that idea. Favour premium but believable homes and ownership environments that help shoppers imagine owning the artwork. Do not use abstract room symbolism when it weakens a direct commercial presentation.

Privately develop a fresh visual concept from the selected product before writing the five prompts. Do not output that reasoning.

Across the five prompts deliberately vary room type, architecture, wall finish, material palette, furniture style, lighting direction, time of day, camera height, camera distance, camera angle, artwork placement, emotional intensity, negative space, framing and composition, and how the room expresses the card's message without zooming out so far that the framed artwork becomes small.

No two cards may repeat the room type, house architecture, wall treatment, wall colour family, main furniture layout, lighting setup, time-of-day treatment, camera composition, camera height or artwork placement.

Do not merely recolour the same room. Do not default to a generic office, living room, man cave, collector room and close-up sequence.

Treat this as a new creative run. Do not default to room combinations you have previously supplied for Sports Cave. Build a fresh set from the product title, sport, country, card copy and emotional story. Within this run, do not repeat a room type, wall treatment, principal furniture arrangement, lighting setup or camera composition.

Visual variety must never alter, regenerate, crop or distort the supplied artwork or frame. Never crop the outer frame or let the artwork extend beyond its border. Never let room variety, furniture scale, architecture, negative space, sport atmosphere, country adaptation or scarcity emphasis make the framed product secondary. Avoid five near-identical framed mockups with only minor furniture changes.

Normally do not place the card headline or description inside the image because Meta supplies those fields separately. Only include in-image card text if the existing approved campaign template explicitly requires it.

Do not add prices, discounts, fake buttons, fake UI, watermarks, promotional stickers, unsupported text, fake edition details or random copy.

Every image prompt must be fully standalone. Repeat the complete product-lock, frame-and-glass, room-realism, LAST-IMAGE VARIATION LOCK, sport-and-country adaptation and relevant visual-story requirements inside every prompt. Never write "same as above", "use the previous room" or "keep the same settings".

IMAGE PROMPTS — GENERATE IN THIS ORDER

{schema_text}

Return exactly these five image-prompt entries and no sixth prompt."""


INSTANT_EXPERIENCE_REFERENCE_IMAGE_INSTRUCTION = (
    "the selected framed Sports Cave product reference image uploaded through the Ads section"
)


INSTANT_EXPERIENCE_MASTER_IMAGE_PROMPT_TEMPLATE = """06 — INSTANT EXPERIENCE COVER — 1:1 SOCIAL

Use the product information and uploaded reference image already supplied through the Sports Cave Ads section:

Product name: {{PRODUCT_NAME}}
Sport category: {{SPORT_CATEGORY}}
Target market: {{TARGET_MARKET}}
Reference image: {{UPLOADED_FRAMED_PRODUCT_IMAGE}}

Do not ask for these details again.

OBJECTIVE

Using the uploaded Sports Cave product image as the exact product reference, create one ultra-realistic 1024 × 1024 Meta Instant Experience cover.

The output must always be:

* Exactly 1024 × 1024 pixels.
* Exactly 1:1 square.
* Designed for mobile viewing.
* Suitable for the top of a Meta Instant Experience, with the product catalogue appearing underneath.

Never generate a landscape or portrait canvas. If the result is not exactly 1:1, regenerate it before returning the final image.

The cover must instantly communicate:

* Premium collector value.
* Authentic limited-edition scarcity.
* Emotional fan ownership.
* The feeling that this artwork belongs in a real home.
* A clear reason to claim an edition before all 100 are gone.

The artwork must remain the unmistakable hero.

APPROVED COMPOSITION

Divide the square canvas into two visually connected sections:

Top lifestyle section: approximately 64–68% of the canvas.
Bottom scarcity panel: approximately 32–36% of the canvas.

Do not allow the bottom panel to overpower the product.

The framed artwork must be the largest and most immediately recognizable element in the image.

TOP LIFESTYLE SECTION

Place the exact uploaded framed artwork prominently on the wall of a genuine premium residential interior.

The setting must resemble a real house photographed by a professional interior photographer—not a showroom, retail display, studio set or AI-generated luxury room.

Select one believable residential area appropriate to the product and target market, such as:

* A refined living-room feature wall.
* An intimate home office.
* A renovated gallery landing.
* A premium hallway or stair landing.
* A collector’s reading room.
* A restrained media or entertainment room.
* A sophisticated man cave without sports-themed clutter.

Use only one setting. Do not combine multiple room concepts.

The room should feel premium, masculine, minimal and lived-in without becoming cold, clichéd or excessively luxurious.

Use a restrained residential palette such as:

* Warm off-white.
* Muted taupe.
* Soft concrete.
* Natural plaster.
* Warm grey.
* Charcoal.
* Lightly textured beige.
* Subtle timber and neutral architectural finishes.

REAL-HOUSE PHOTOGRAPHY REQUIREMENTS

The environment must include believable residential architecture:

* Correct room dimensions and ceiling height.
* Straight vertical walls and doorways.
* Accurate floor-to-wall joins.
* Natural furniture scale.
* Realistic frame size relative to the wall.
* Plausible mounting height.
* Correct perspective and viewing distance.
* Natural space around the artwork.
* Genuinely textured plaster, timber, fabric, leather or concrete.
* Subtle signs that somebody lives in the house.
* Controlled imperfection rather than artificial symmetry.

Use a limited number of carefully placed residential details, such as one bench, console, chair, book or ceramic object.

Do not fill the room with decorative clutter.

Do not use sports props to explain the sport. The supplied artwork must carry the sporting identity.

ARTWORK PROMINENCE

The framed artwork must dominate the lifestyle section.

It should occupy approximately 48–62% of the available width in the top section, depending on the room and camera angle.

It must remain:

* Large at thumbnail size.
* Fully visible.
* Instantly recognizable.
* Clearly separated from surrounding furniture.
* The primary focal point.
* More visually important than the architecture.

Do not place the artwork far away on a large empty wall.

Do not make the room more prominent than the product.

Do not crop any part of the artwork or frame.

PRODUCT LOCK — NON-NEGOTIABLE

Treat the uploaded Sports Cave framed product image as a locked photographic product asset.

Keep the uploaded artwork and frame exactly the same.

Do not:

* Redesign, repaint or redraw the artwork.
* Regenerate or reinterpret the artwork.
* Create a similar or lookalike version.
* Change the athlete, subject or identity.
* Change faces, bodies, uniforms or equipment.
* Change any colours.
* Change the composition or layout.
* Change any wording inside the artwork.
* Change the badge, seal, plaque or edition plate.
* Add fake signatures.
* Add fake logos.
* Add fake edition numbers.
* Add invented artwork details.
* Crop the artwork.
* Blur or soften the artwork.
* Mirror the artwork.
* Stretch, warp, bend, squash or distort it.
* Change its landscape proportions.
* Change the frame colour, shape or design.
* Replace the supplied product with newly generated artwork.

The artwork must remain sharp, rectangular, correctly aligned and completely visible inside the frame.

FRAME AND GLASS REALISM

The frame must look like a genuine physical product mounted on a real wall.

Preserve the supplied frame colour and design.

Show:

* Premium timber construction.
* Believable frame depth.
* Sharp square corners.
* Clean frame joins.
* Subtle material texture.
* Correct landscape proportions.
* Accurate perspective.
* A natural gap or shadow between the frame and wall.
* Realistic weight and mounting.

Add physically believable glass over the artwork.

The glass should show:

* Soft environmental reflections.
* Subtle premium glare.
* Restrained highlight streaks.
* Reflections consistent with the room’s windows and lighting.
* Controlled transparency that keeps the entire artwork readable.

Glass reflections must enhance the realism without obscuring, changing or washing out the artwork.

The frame must look mounted—not pasted, floating or digitally overlaid.

LIGHTING AND CAMERA

Use authentic residential lighting.

Combine:

* Soft natural light entering from one believable direction.
* Restrained warm practical or architectural lighting.
* Natural shadows behind and beneath the frame.
* Subtle shadow falloff across the wall.
* Controlled contrast.
* Realistic highlights on timber, plaster and glass.

Avoid bright orange lighting, extreme spotlights, artificial glow and overprocessed HDR.

Use a natural interior-photography camera position.

A subtle three-quarter angle is allowed, but the frame must remain geometrically correct and easy to see.

Avoid:

* Extreme wide-angle lenses.
* Distorted walls.
* Dramatic Dutch angles.
* Excessive perspective.
* Bent architecture.
* Perfect front-facing artificial symmetry.
* Camera positions that make the artwork appear small.

BOTTOM SCARCITY PANEL

Add an integrated collector-grade panel across the bottom 32–36% of the square canvas.

The panel must feel like part of a premium Sports Cave campaign—not a separate cheap promotional banner.

Panel styling:

* Deep matte black.
* Subtle black material texture.
* Restrained vignette.
* Refined dark tonal variation.
* Very subtle metallic-gold detailing.
* Clean spacing.
* No excessive shine.
* No loud gradients.
* No neon effects.
* No discount-store styling.

Separate the lifestyle section and panel with one restrained gold hairline, subtle metallic edge or controlled warm light transition.

Do not use a large artificial lens flare.

SCARCITY COPY

Use only these three lines:

LIMITED TO 100 WORLDWIDE

Once it sells out, it’s gone.

CLAIM YOUR EDITION

Do not add any other overlay copy.

Do not add:

* Product names.
* Prices.
* Discounts.
* Percentage savings.
* Shipping claims.
* Product features.
* Paragraphs.
* Countdown timers.
* “Shop Now” buttons.
* Fake clickable UI.
* Additional scarcity claims.

TEXT HIERARCHY

Line one:

“LIMITED TO 100 WORLDWIDE”

* Largest line.
* Uppercase.
* Premium collector-style serif or refined high-end display typeface.
* Soft metallic gold, warm ivory or premium white.
* Strong enough to stop the scroll.
* Fully readable on mobile.

Line two:

“Once it sells out, it’s gone.”

* Smaller.
* Clean and understated.
* White or warm ivory.
* Use the apostrophes exactly as written.
* Give the line breathing room.

Line three:

“CLAIM YOUR EDITION”

* Uppercase.
* Refined metallic gold or warm gold.
* Clearly readable.
* Slightly smaller than the main scarcity headline.
* Styled as a premium campaign command, not a fake website button.

Keep all text centred, correctly spelled and safely inside the mobile margins.

The panel must feel urgent through restraint, spacing and hierarchy—not through oversized graphics or aggressive sales styling.

SPORT AND MARKET ADAPTATION

Use the supplied sport category and target market only to guide the architectural atmosphere and emotional tone.

The setting should feel appropriate for a serious fan and collector in that market without using stereotypes.

Do not introduce:

* Sports equipment.
* Balls.
* Bats.
* Helmets.
* Jerseys.
* Trophies.
* Figurines.
* Team flags.
* Novelty signs.
* Team-coloured rooms.
* Extra athlete photographs.
* Extra sports artwork.
* Fake memorabilia.
* Retail fixtures.
* Neon signs.

The framed artwork alone must communicate the sport, athlete, team, rivalry or moment.

FINAL REALISM CHECK

Before returning the image, confirm that:

* The canvas is exactly 1024 × 1024.
* The output is a true 1:1 square.
* The framed artwork is completely visible.
* The artwork remains the dominant visual element.
* The original artwork has not been altered.
* The frame has correct landscape proportions.
* The room resembles a genuine lived-in house.
* The frame appears physically mounted.
* Glass reflections are realistic and controlled.
* Wall, floor, ceiling and furniture geometry are believable.
* The three approved text lines are spelled correctly.
* No additional text or claims have been introduced.
* The scarcity panel feels premium rather than promotional.
* The overall image remains clear and persuasive at mobile size.

Avoid warped walls, impossible windows, crooked ceilings, bent furniture, floating objects, duplicate objects, plastic materials, fake luxury, excessive blur, overprocessed HDR, unrealistic reflections, malformed lighting, perfect artificial symmetry and any obvious AI-showroom appearance.

FINAL RESULT

Create a photorealistic, premium 1024 × 1024 Sports Cave Instant Experience cover featuring the exact uploaded framed artwork displayed prominently in a genuine high-end residential interior.

The final image must make the artwork feel like a real limited-edition collector piece already hanging in a desirable home—then use the restrained black-and-gold scarcity panel to make the viewer feel they should claim one of the 100 editions before it is gone."""


def build_default_instant_experience_cover_prompt_requirements(product_name, category, country):
    product_name = _clean_product_name(product_name)
    category = _normalise_option_label(category) or "selected sport category"
    country = _normalise_option_label(country) or "selected market"
    return (
        INSTANT_EXPERIENCE_MASTER_IMAGE_PROMPT_TEMPLATE.replace(
            "{{PRODUCT_NAME}}",
            product_name,
        )
        .replace("{{SPORT_CATEGORY}}", category)
        .replace("{{TARGET_MARKET}}", country)
        .replace(
            "{{UPLOADED_FRAMED_PRODUCT_IMAGE}}",
            INSTANT_EXPERIENCE_REFERENCE_IMAGE_INSTRUCTION,
        )
    )


def build_instant_experience_visual_output_requirements(
    template_key,
    *,
    product_name="",
    category="",
    country="",
):
    layout_rules = build_default_instant_experience_cover_prompt_requirements(
        product_name,
        category,
        country,
    )
    scarcity_rules = """Use the exact default overlay text supplied above. Do not replace it with generated copy, alternate scarcity wording, a different CTA, a fake button or an inferred edition claim."""

    return f"""INSTANT EXPERIENCE VISUAL REQUIREMENTS

After every existing Instant Experience copy, headline, description, CTA, setup and URL-parameter field, output exactly one complete cover-image prompt. Do not output five prompts.

Tailor the cover to the selected product name, selected sport, selected country, generated Instant Experience headline, generated supporting copy, approved scarcity claim, existing CTA, emotional theme and uploaded framed artwork. It must not be a generic reusable collector-room prompt.

{layout_rules}

{scarcity_rules}

Never invent edition quantities, sale prices, discounts, signatures, logos, athlete names, achievements, dates, rivalries, product details or scarcity facts.

The one cover prompt must be fully standalone. Repeat the complete product-lock, frame-and-glass, room-realism, LAST-IMAGE VARIATION LOCK, sport-and-country adaptation and cover-layout requirements inside it. Do not refer to shared rules elsewhere in the response.

INSTANT EXPERIENCE COVER IMAGE PROMPT

[one complete standalone cover-image prompt that repeats the complete LAST-IMAGE VARIATION LOCK instructions]

Return exactly one cover-image prompt and no additional image prompts."""


def build_single_image_video_visual_output_requirements():
    return """SINGLE IMAGE / VIDEO VISUAL REQUIREMENTS

Preserve the existing Single Image / Video route and output fields.

Upgrade its existing creative brief into exactly one complete standalone creative prompt using the dynamic room-realism, product-lock, frame-and-glass, LAST-IMAGE VARIATION LOCK and sport-and-country adaptation rules. Do not create a five-prompt Carousel sequence.

Place this one enhanced creative prompt after every existing copy, headline, description, CTA, setup and URL-parameter field.

CREATIVE PROMPT FOR SINGLE IMAGE/VIDEO

[one complete standalone image or video prompt that repeats the complete LAST-IMAGE VARIATION LOCK instructions]

Return exactly one creative prompt."""


def build_campaign_visual_output_contract(
    product_name,
    category,
    country,
    campaign_type,
    *,
    template_key=None,
    variation_token="",
):
    product_name = _clean_product_name(product_name)
    variation_token = _normalise_option_label(variation_token) or "standard"
    if campaign_type == "Carousel":
        campaign_requirements = build_carousel_visual_output_requirements(template_key)
    elif campaign_type == "Instant Experience":
        campaign_requirements = build_instant_experience_visual_output_requirements(
            template_key,
            product_name=product_name,
            category=category,
            country=country,
        )
    elif campaign_type == "Single Image / Video":
        campaign_requirements = build_single_image_video_visual_output_requirements()
    else:
        return ""

    return f"""MASTER RESPONSE AND VISUAL OUTPUT CONTRACT

Selected product name: {product_name}
Selected sport category: {category}
Selected country: {country}
Selected campaign type: {campaign_type}
Creative variation token: {variation_token}

Return the finished existing ad-copy output first, in its existing required schema and order. Preserve every existing copy field, card role, primary-text variation, headline, description, CTA, setup instruction, destination rule and URL parameter.

Directly beneath that complete existing output, return the campaign-specific visual section required below.

This response-order rule controls placement only. It does not replace, rewrite, weaken or omit any earlier approved copy instruction.

If an earlier campaign schema already names an image prompt, cover prompt or creative prompt, treat that earlier section as specification for the single final visual section below. Move and upgrade that one visual field to the final position. Do not output a preliminary brief, duplicate visual field or second prompt. The final campaign-specific visual heading and prompt count below are authoritative.

Do not repeat the research, explain decisions, show internal reasoning, provide rejected alternatives or give general creative advice. Return only the finished ad output followed by the finished visual prompt or prompts.

Treat the creative variation token only as a cue for a fresh interpretation. Never display it in ad copy or inside an image.

{build_product_lock_visual_rules()}

{build_frame_and_glass_visual_rules()}

{build_room_realism_visual_rules()}

{build_last_image_variation_visual_rules()}

{build_sport_country_visual_adaptation(category, country)}

{campaign_requirements}"""


def apply_campaign_visual_output_contract(
    prompt,
    *,
    product_name,
    category,
    country,
    campaign_type,
    template_key=None,
    variation_token="",
):
    if not prompt or "MASTER RESPONSE AND VISUAL OUTPUT CONTRACT" in prompt:
        return prompt
    contract = build_campaign_visual_output_contract(
        product_name,
        category,
        country,
        campaign_type,
        template_key=template_key,
        variation_token=variation_token,
    )
    return f"{prompt.rstrip()}\n\n{contract}" if contract else prompt


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


def validate_carousel_card_length(
    cards,
    max_characters=CAROUSEL_CARD_MAX_CHARACTERS,
):
    errors = []
    for index, card in enumerate(cards or [], start=1):
        for field_name in ("headline", "description"):
            value = normalize_carousel_field(card.get(field_name, ""))
            if len(value) > max_characters:
                errors.append(f"Card {index} {field_name} exceeds {max_characters} characters.")
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

The headings below define each card's commercial function. Keep the selected approved template's existing role labels in the final output schema.

Card 1 — Product Identity
- Immediately identify the artwork, athlete, team, rivalry, vehicle, event or defining phrase.
- Use the strongest recognisable phrase from the product name or attached artwork.

Card 2 — Display Desire
- Show a commercially desirable and category-relevant ownership setting.
- Help the customer imagine the product in a home, sports room, office, bar, garage or collection.
- Keep the product central rather than selling the room itself.

Card 3 — Collector Appeal
- Communicate premium display value, collector status or a category-relevant ownership environment.
- Add a distinct ownership reason rather than repeating Card 2.
- Do not invent product quality or manufacturing claims.

Card 4 — Emotional Meaning
- Express the verified relationship, legacy, era, memory, mentality or fan connection.
- Do not repeat names already used on Card 1.
- Make the emotional meaning specific to the supplied product.

Card 5 — Scarcity
- Close with genuine limited-edition scarcity.
- Communicate an edition quantity, numbered run, no second run or no restock only when confirmed by the approved claim path, supplied product information or visible artwork.
- When no quantity is confirmed, use only the strongest truthful non-numeric scarcity already permitted by the campaign.
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
- Reject anything generic, unclear or over {CAROUSEL_CARD_MAX_CHARACTERS} characters.
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

For all five carousel cards:

Headline:
- Maximum {CAROUSEL_CARD_MAX_CHARACTERS} characters including spaces and punctuation.

Description:
- Maximum {CAROUSEL_CARD_MAX_CHARACTERS} characters including spaces and punctuation.

This is a strict limit.

- Treat {CAROUSEL_CARD_MAX_CHARACTERS} characters as the absolute limit, not the target.
- Do not truncate text to make it fit.
- Do not cut words in half.
- Do not silently allow text longer than {CAROUSEL_CARD_MAX_CHARACTERS} characters.
- Count every character before returning the final output.
- Use Python len(value) semantics: spaces and punctuation count.
- Never contain a comma or full stop.
- Use complete words only.
- Never make wording unnatural, abbreviated or confusing merely to fit the limit.

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


def build_carousel_high_conversion_quality_rules():
    return f"""HIGH-CONVERSION CAROUSEL QUALITY

Preserve the exact approved five-card output schema and order required by the selected campaign template. Make the five cards work as one connected persuasion journey rather than five unrelated captions.

Card 1 - Product Identity
- State clearly who or what the artwork celebrates.
- Use the full product identity only here when it fits naturally within the character limit. Otherwise use the strongest unmistakable verified identity.
- Make the reader want to continue scrolling.
- Do not waste this card on generic wording such as Premium Art.

Card 2 - Display Desire
- Show the result of ownership and where the artwork belongs.
- Choose a product-relevant man cave, sports room, office, home bar, garage or believable home setting.
- Make the setting commercially desirable without relying on generic room wording.

Card 3 - Collector Appeal
- Communicate premium display value, collector status or a category-relevant ownership environment.
- Give a distinct collector reason rather than repeating Card 2's room benefit.
- Do not make unsupported product-quality or manufacturing claims.

Card 4 - Emotional Meaning
- Distil the verified relationship, legacy, era, memory, mentality or fan connection.
- Do not repeat names already used on Card 1.
- Do not invent achievements, dates, teams, rivalries or events.

Card 5 - Authentic Scarcity
- Finish with the strongest truthful reason to act now.
- Use the confirmed edition limit, numbered run, once gone or no second run only when supported by supplied product information or the existing approved-claim path.
- Make this card decisive without sounding cheap, aggressive or spammy.

CONNECTED COPY QUALITY

- Every card must communicate a different buying reason.
- The headline and description on the same card must complement one another rather than repeat the same idea.
- Across all ten card lines, do not repeat any meaningful word. Treat singular and plural forms as the same word.
- Use athlete, team, event or product names only once, normally on Card 1.
- Use the edition number only on Card 5.
- Do not repeat legend, legacy, icon, collector, edition, wall, made, pride, greatness or similar keywords across multiple cards.
- Avoid forced fan language such as Who Did You Back, Your Legends Wall or similarly unnatural phrases.
- Do not hard-code names or reference copy from another product.
- Use one clear idea per line.
- Write for fast mobile scanning.
- Use natural spoken language, not compressed advertising jargon.
- Keep the Sports Cave voice emotional, nostalgic, urgent, premium and collector-driven.
- Connect the product to fan identity, memory, rivalry, pride, legacy or ownership.
- Prefer specific product-supported emotion over generic luxury language.
- Do not sound corporate, poetic for its own sake or obviously AI-generated.
- Do not invent players, teams, dates, trophies, records, signatures, licensing, edition quantities or product features.
- Preserve the selected country's localisation and the selected sport's terminology.
- Preserve all current CTAs, URLs, UTM parameters and output quantities.
- Do not turn all five cards into direct sales commands.
- Use scarcity strongly once, normally on Card 5, rather than weakening it through repetition.

COPY AND CREATIVE ALIGNMENT

- The headline, description, creative direction and generated image prompt for each card must communicate the same selling idea.
- Card 1 uses a clean product-hero presentation.
- Card 2 uses a desirable ownership setting.
- Card 3 uses a premium collector display suited to the selected category.
- Card 4 uses an emotional lifestyle, memory or legacy presentation.
- Card 5 uses a scarcity-focused view that gives an existing edition plate or numbered detail prominence when verified while keeping the complete outer frame visible.
- The room, wall, lighting, angle and composition must visibly support the exact headline and description.
- Favour premium but believable homes and ownership environments that help shoppers imagine owning the artwork.
- Do not use abstract visual metaphors when they weaken a clear commercial product presentation.
- Never place the Meta headline or description inside the generated image.
- Never crop the outer frame or let artwork extend beyond its border.

INTERNAL SELECTION - DO NOT OUTPUT

Before returning the campaign, silently:

1. Generate several candidate headline and description pairs for each role.
2. Count every character, including spaces.
3. Reject anything exceeding {CAROUSEL_CARD_MAX_CHARACTERS} characters.
4. Reject awkward abbreviations and incomplete phrases.
5. Reject repetitive or generic card combinations.
6. Check that every card has a distinct conversion purpose.
7. Select only the strongest connected five-card sequence.
8. Output only the final campaign in the existing format.

Do not expose candidate lines, scoring notes or internal reasoning in the generated output."""


def build_carousel_final_quality_check(include_primary_text_variations=False):
    checks = [
        "Exactly five carousel cards are present.",
        f"Every headline is {CAROUSEL_CARD_MAX_CHARACTERS} characters or fewer including spaces and punctuation.",
        f"Every description is {CAROUSEL_CARD_MAX_CHARACTERS} characters or fewer including spaces and punctuation.",
        "Spaces and punctuation are included in the count.",
        "No words have been truncated.",
        "Card 1 identifies the product.",
        "Card 2 communicates display desire in a product-relevant ownership setting.",
        "Card 3 communicates premium collector appeal without repeating Card 2.",
        "Card 4 communicates verified emotional meaning without repeating names from Card 1.",
        "Card 5 communicates genuine scarcity.",
        "The cards read as one connected story.",
        "Every card communicates a different buying reason.",
        "Each headline and description complement one another without repeating the same idea.",
        "No meaningful word is repeated across the ten card lines unless unavoidable for clarity.",
        "Product names appear only on Card 1 and the edition number appears only on Card 5.",
        "Each card's copy, creative direction and image prompt communicate the same selling idea.",
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

If any carousel field exceeds {CAROUSEL_CARD_MAX_CHARACTERS} characters, rewrite it before answering."""


def build_carousel_cta_guidance():
    return """CTA GUIDANCE

Use:
Claim Your Edition"""


def apply_campaign_copy_rule_blocks(prompt, campaign_type, include_primary_text_variations=False, category=None):
    if campaign_type != "Carousel" or not prompt:
        return prompt

    story_rules = build_carousel_story_and_specificity_rules(category)
    card_rules = build_carousel_card_copy_rules()
    high_conversion_rules = build_carousel_high_conversion_quality_rules()
    final_quality_check = build_carousel_final_quality_check(
        include_primary_text_variations=include_primary_text_variations
    )
    cta_guidance = build_carousel_cta_guidance()
    if story_rules not in prompt:
        prompt = f"{prompt.rstrip()}\n\n{story_rules}"
    if card_rules not in prompt:
        prompt = f"{prompt.rstrip()}\n\nCAROUSEL COPY RULES\n\n{card_rules}"
    if high_conversion_rules not in prompt:
        prompt = f"{prompt.rstrip()}\n\n{high_conversion_rules}"
    if "CTA GUIDANCE" not in prompt:
        prompt = f"{prompt.rstrip()}\n\n{cta_guidance}"
    if final_quality_check not in prompt:
        prompt = f"{prompt.rstrip()}\n\n{final_quality_check}"
    return prompt


def build_shared_meta_winner_copy_upgrade():
    return f"""{META_WINNER_COPY_BLOCK_VERSION}

This block strengthens copy selection only. Preserve the current campaign's approved output schema, field count, card labels, CTA, URL parameters, localisation, claim safeguards and all campaign-specific winner instructions.

PRIMARY-TEXT ANGLE BALANCE

When the approved campaign template requests five primary-text variations, use these five genuinely different conversion angles in their existing numbered output positions. Keep the template's existing variation labels and output formatting unchanged.

Variation 1 - Staccato Legacy Story

- Begin with two to four short sharp lines.
- Build product-specific contrast, progression, rivalry, connection, achievement or emotional tension.
- Follow with a two-line reframe that moves the product from decoration to memory, identity, mentality or legacy.
- Finish with authentic scarcity and a direct collector CTA.
- Keep individual lines immediately readable on mobile. Fragments are encouraged.
- Make every line specific to the supplied product.
- Do not reuse example wording from another campaign.
- Do not mechanically force they or a rivalry structure onto a single athlete, team, car, horse, event or championship product.
- Adapt the grammar to the actual product type.
- Never invent a rivalry, achievement, record, number, trophy, team, year or historical fact.
- The result must feel raw, restrained and confident rather than like conventional ad copy.

Variation 2 - Framed Greatness

Use this exact two-line opening once:

Greatness doesn’t fade.
It gets framed.

- Do not repeat greatness in the middle or closing.
- Write one compact product-specific paragraph using the supplied product name, supported people, team, vehicle, event or moment, selected sport, selected country, fan emotion and any verified era, rivalry, mentality or memory.
- Follow with one short emotional paragraph about collector ownership or display appeal.
- Close with: Limited to {{authentic edition limit}} worldwide. Secure your edition before it’s gone.
- Replace {{authentic edition limit}} with the confirmed edition quantity from the approved claim path, supplied product information or visible artwork. Never leave the placeholder in final copy.
- When the confirmed edition limit is 100, write exactly: Limited to 100 worldwide. Secure your edition before it’s gone.
- When no edition quantity is confirmed, use the strongest truthful scarcity already permitted by the campaign instead. Never fabricate 100, a numbered edition or a no-second-run claim.

Variation 3 - Nostalgia And Remembered Moment

- Lead with a verified memory, era, atmosphere or defining feeling tied to the supplied product.
- Make the correct fan remember why the subject mattered.
- Keep the writing compact, natural and fact-safe.

Variation 4 - Fan Identity And Ownership

- Connect the product to belonging, pride and the feeling of owning and displaying it.
- Help the customer picture it in a relevant home, sports room, office, bar, garage or collection without turning the copy into an interior-design advertisement.

Variation 5 - Collector Scarcity Or Gifting

- Lead with collector meaning and finish with the strongest authentic urgency.
- Use gifting only when it naturally strengthens the selected product and audience.
- Do not repeat the scarcity sentence used by another variation.

If the approved campaign-specific template requires exactly one primary text rather than five, preserve that quantity. Silently consider these angles and return only the strongest compatible final version in the existing schema.

UNIVERSAL PRIMARY-TEXT QUALITY

- Lead with the emotional hook rather than a product description.
- Write for a mobile Meta feed using short paragraphs and deliberate line breaks.
- Connect the product to verified memory, identity, rivalry, legacy, mentality, pride or belonging.
- Make the writing human, direct, premium and collector-driven.
- Use the product title and supplied artwork as the factual source of truth.
- Localise terminology using the existing selected-country rules.
- Keep scarcity premium, authentic and believable.
- End with a natural action such as Secure yours or Claim your edition.
- Avoid long explanations, excessive rhetorical questions and repeated hooks or scarcity sentences.
- Avoid generic AI language including elevate, transform, ultimate, unleash, must-have, masterpiece, conversation starter and bring your walls to life.
- Do not name unsupported athletes, teams, records, years, trophies, events, numbers or achievements.
- Do not claim licensing, signatures or authenticity unless supplied.
- Do not use discount language unless the campaign variables explicitly support it.
- The five variations must feel like five distinct human selling angles rather than rewrites of one message.

SILENT COPY SELECTION

Before returning the campaign, privately compare several product-specific candidates for each required angle. Reject generic, repetitive, fact-unsafe or unnatural writing. Return only the strongest finished copy in the current approved output format. Do not expose candidates, scoring notes, research or reasoning."""


def apply_shared_meta_winner_copy_upgrade(prompt, campaign_type):
    if campaign_type not in {"Carousel", "Instant Experience"} or not prompt:
        return prompt
    if META_WINNER_COPY_BLOCK_VERSION in prompt:
        return prompt
    return f"{prompt.rstrip()}\n\n{build_shared_meta_winner_copy_upgrade()}"


def compose_final_ads_prompt(
    prompt,
    *,
    category,
    country,
    campaign_type,
    include_primary_text_variations=False,
    product_name="",
    template_key=None,
    variation_token="",
):
    if not prompt:
        return prompt
    prompt = apply_campaign_copy_rule_blocks(
        prompt,
        campaign_type,
        include_primary_text_variations=include_primary_text_variations,
        category=category,
    )
    prompt = apply_shared_meta_winner_copy_upgrade(prompt, campaign_type)
    prompt = apply_country_language_guidance(prompt, country)
    prompt = apply_meta_url_parameters_guidance(prompt)
    if product_name:
        prompt = apply_campaign_visual_output_contract(
            prompt,
            product_name=product_name,
            category=category,
            country=country,
            campaign_type=campaign_type,
            template_key=template_key,
            variation_token=variation_token,
        )
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

CAROUSEL COPY RULES

Create exactly five cards.

Each card requires:

Headline
Description

{carousel_card_copy_rules}

Keep the approved output role labels Product Identity, Race Or Moment, Legacy, Fan Ownership and Scarcity exactly as shown in the output schema. Apply the commercial functions in the shared high-conversion block below to Cards 1 through 5 without renaming these output fields.

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

1. Generate the Instant Experience cover from the Instant Experience Cover Prompt above.

2. In Meta Ads Manager, create or edit the Instant Experience using the Product template.

3. Select the connected Shopify Product Catalog.

4. Select the product set matching the chosen sport:
   {BASEBALL_INSTANT_EXPERIENCE_PRODUCT_SET_NAME}
   Use the actual connected Baseball product-set name if stored in the app.

5. Set products to Order dynamically unless the campaign requires a manually chosen product order.

6. Upload the Instant Experience cover generated from the prompt above.

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

INSTANT EXPERIENCE COVER RULE

The how-to section must specifically tell the user:

Upload the Instant Experience cover generated from the prompt above.

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
- The generated Instant Experience cover upload step is specified.
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


def build_product_url_instruction(product_url):
    product_url = _clean_product_url(product_url)
    if product_url:
        return f"Use this selected product page URL where a destination URL is required: {product_url}"
    return "Use the selected product's live product page URL where a destination URL is required. Do not invent a URL."


def build_country_campaign_localisation_note(category, country):
    country_key = normalize_country_language_key(country)
    category_key = str(category or "").strip()
    if category_key == "Football":
        if country_key == "Australia":
            return "AU football/soccer localisation: use football or soccer depending on the product context. Keep Claim Your Edition."
        if country_key == "UK":
            return "UK football localisation: use football, supporters, wall, home bar, collection and proper fans where natural."
        if country_key == "USA":
            return "USA soccer localisation: use soccer, fans, collector wall art, sports room and claim yours where natural."
        if country_key in {"Canada", "New Zealand"}:
            return "Canada/NZ football localisation: use football or soccer depending on the product context. Keep the tone natural and unforced."
    return "Country localisation should adjust wording, spelling and audience language only. It must not decide whether output exists."


def build_universal_sports_cave_rules(category):
    cues = CATEGORY_COPY_CUES.get(
        category,
        "identity, memory, legacy, rivalry, pride, pressure and the defining moment",
    )
    return f"""UNIVERSAL SPORTS CAVE WINNER RULES

- Make every customer-facing line emotional, nostalgic, urgent and collector-driven.
- Connect the selected product to identity, memory, legacy, rivalry, pride or the moment.
- Use category cues only when supported by the product title or artwork: {cues}.
- Include authentic scarcity naturally when relevant: limited edition, only 100, numbered edition, once gone it is gone.
- Keep copy short, human and direct. Do not over-explain.
- Do not invent facts, teams, years, trophies, signatures, licensing, records, shipping claims, review counts or manufacturing claims not present in the product title/context.
- Avoid these generic AI phrases: elevate your space; ultimate tribute; perfect addition; must-have; transform your room."""


def get_category_winner_angle(category):
    return CATEGORY_WINNER_ANGLES.get(category, {})


def build_carousel_winner_examples(example_text):
    examples = []
    for example in str(example_text or "").split(";"):
        example = example.strip()
        if len(example) > CAROUSEL_CARD_MAX_CHARACTERS:
            raise ValueError(
                f"Carousel winner example exceeds {CAROUSEL_CARD_MAX_CHARACTERS} characters: {example}"
            )
        examples.append(example)
    return "; ".join(example for example in examples if example)


def build_category_winner_angle_block(category, campaign_type, country):
    angle = get_category_winner_angle(category)
    if not angle:
        return ""

    category_label = str(category or "").upper()
    if campaign_type == "Carousel":
        headline_examples = build_carousel_winner_examples(angle["headline_examples"])
        description_examples = build_carousel_winner_examples(angle["description_examples"])
        strategy = f"""CATEGORY-SPECIFIC CAROUSEL WINNER ANGLE

- Category decides the ad structure and emotional angle. Country only localises spelling, terminology and language flavour.
- Audience: {angle["audience"]}.
- Emotional territory: {angle["emotion"]}.
- Category-specific emotional cues: {angle["carousel_flow"]}. Use these cues only where they support the required commercial card journey and verified product facts.
- Keep the selected template's existing five role labels and output order unchanged.
- Card 1 must show the product clearly.
- Card 2 must create display desire in a product-relevant ownership setting.
- Card 3 must communicate premium collector appeal suited to the category.
- Card 4 must distil the verified emotional meaning, memory or fan connection without repeating names from Card 1.
- Card 5 must make scarcity feel final and collector-led.
- Strong short-line examples for this category: {headline_examples}.
- Short description examples for this category: {description_examples}.
- {angle["country_note"]}"""
    elif campaign_type == "Instant Experience":
        strategy = f"""CATEGORY-SPECIFIC INSTANT EXPERIENCE WINNER ANGLE

- Category decides the ad structure and emotional angle. Country only localises spelling, terminology and language flavour.
- Lead with the selected product as the hero, framed as premium {category} collector wall art.
- Audience: {angle["audience"]}.
- Emotional territory: {angle["emotion"]}.
- If the product is narrow to a team, player, rivalry, country or event, use that as the hook while keeping enough category-wide appeal for cold audiences.
- Instant Experience setting: {angle["ie_setting"]}.
- Catalogue/cards underneath should feel like a connected {category} collector range, not one isolated product.
- Strong short-line examples for this category: {angle["headline_examples"]}.
- Short description examples for this category: {angle["description_examples"]}.
- {angle["country_note"]}"""
    else:
        strategy = f"""CATEGORY-SPECIFIC SINGLE IMAGE / VIDEO WINNER ANGLE

- Category decides the emotional angle. Country only localises spelling, terminology and language flavour.
- Lead with the selected product as the hero, framed as premium {category} collector wall art.
- Audience: {angle["audience"]}.
- Emotional territory: {angle["emotion"]}.
- Creative setting: {angle["ie_setting"]}.
- Primary text should connect the exact product to identity, memory, ownership and limited-edition scarcity.
- Headlines should be short, product-specific and sharper than generic wall-art labels.
- Strong short-line examples for this category: {angle["headline_examples"]}.
- Short description examples for this category: {angle["description_examples"]}.
- {angle["country_note"]}"""

    return f"""{category_label} WINNER PATTERN

{strategy}"""


def get_instant_experience_setting(category):
    return get_category_winner_angle(category).get(
        "ie_setting",
        "premium collector room, wall, sports room, home bar, office or man cave",
    )


def build_generic_instant_experience_prompt(
    product_name,
    category,
    country,
    campaign_type,
    product_url="",
    *,
    specific_pattern=False,
):
    product_name = _clean_product_name(product_name)
    if specific_pattern:
        pattern_heading = f"SPORTS CAVE {str(category or '').upper()} INSTANT EXPERIENCE WINNER PATTERN"
    else:
        pattern_heading = "SPORTS CAVE GENERIC INSTANT EXPERIENCE WINNER PATTERN"
    fallback_note = (
        ""
        if specific_pattern
        else "\nINTERNAL NOTE\nUsing generic Sports Cave winner pattern for this category. Do not include this note in customer-facing copy blocks.\n"
    )
    football_block = ""
    if category == "Football":
        football_block = f"""
FOOTBALL INSTANT EXPERIENCE DIRECTION

- Lead with {product_name} as the hero, framed as premium football collector wall art.
- Adapt the copy to the selected product title, moment, player, team, rivalry, final, farewell or event.
- If the product is about a country or team, use that as the emotional hook while keeping wider appeal around football legacy, World Cup nights, iconic moments and serious collectors.
- Output must work for World Cup, national teams, Ronaldo, Messi, Mbappe, Beckham, Arsenal, rivalries, finals, farewells and iconic football moments without inventing facts.
"""
    category_block = build_category_winner_angle_block(category, campaign_type, country)
    default_cover_prompt = build_default_instant_experience_cover_prompt_requirements(
        product_name,
        category,
        country,
    )

    return f"""{pattern_heading}

PRODUCT
Product name: {product_name}
Category: {category}
Market: {country}
Campaign type: {campaign_type}
Destination guidance: {build_product_url_instruction(product_url)}
{fallback_note}
I have attached the exact Sports Cave product image being advertised.

Analyse the attached image and product title before writing.

Use the supplied product name as the source of identity. Do not identify or guess a person, club, country, achievement, year, record, final, trophy or rivalry solely from the image.

{build_country_campaign_localisation_note(category, country)}

{build_universal_sports_cave_rules(category)}

{category_block}
{football_block}
OBJECTIVE

Create a premium Meta Instant Experience ad package for the selected Sports Cave product.

Generate exactly these sections:

1. Primary Text
2. Headline
3. Description
4. Instant Experience Cover Prompt
5. CTA Guidance

PRIMARY TEXT

Create 5 strong variants.

Rules:
- Each variant must be short, emotional and collector-driven.
- Use nostalgia, identity, scarcity and ownership.
- Mention limited editions naturally.
- Adapt each variant to the selected product title, moment, player, team, rivalry, event or visual identity.
- Do not use generic AI phrases such as elevate your space, ultimate tribute or perfect addition.
- Do not over-explain.

HEADLINE

Create 5 headline options.

Rules:
- 4 to 6 words max.
- Urgent and specific to the selected category.
- For Football, use football-specific urgency.
- Strong style examples: Football Glory Framed; Only 100 Made; Claim Your Edition; For Real Football Fans; Legends Belong Framed.

DESCRIPTION

Create 5 short description lines.

Rules:
- Scarcity-driven and premium.
- Examples of style: Limited collector wall art; Once gone it's gone; Built for real fans; Claim your numbered edition; Premium football wall art.

INSTANT EXPERIENCE COVER PROMPT

Create one image prompt for the selected product.

The image prompt must use this upgraded default Instant Experience cover prompt:

{default_cover_prompt}

CTA GUIDANCE

Use:
Claim Your Edition

Catalogue/cards below the Instant Experience should feel like a connected collector range, not one isolated product.

OUTPUT EXACTLY IN THIS FORMAT

PRIMARY TEXT

Variant 1:
[copy]

Variant 2:
[copy]

Variant 3:
[copy]

Variant 4:
[copy]

Variant 5:
[copy]

HEADLINE

1. [headline]
2. [headline]
3. [headline]
4. [headline]
5. [headline]

DESCRIPTION

1. [description]
2. [description]
3. [description]
4. [description]
5. [description]

INSTANT EXPERIENCE COVER PROMPT

[one image prompt]

CTA GUIDANCE

Claim Your Edition

FINAL QUALITY CHECK

- Exactly 5 primary text variants are present.
- Exactly 5 headline options are present.
- Exactly 5 description lines are present.
- Instant Experience Cover Prompt is present.
- CTA guidance is present.
- The cover prompt uses top 60-68% hero artwork and bottom 32-40% black/gold CTA panel.
- The cover prompt includes Claim Your Edition and uses LIMITED TO 100 WORLDWIDE only when the quantity is verified.
- The cover prompt may use Once it sells out, it's gone. only when it matches the approved generated copy.
- Country wording is localised naturally.
- No unsupported facts are invented."""


def build_generic_carousel_prompt(product_name, category, country, campaign_type, *, specific_pattern=False):
    product_name = _clean_product_name(product_name)
    pattern_heading = (
        f"SPORTS CAVE {str(category or '').upper()} CAROUSEL WINNER PATTERN"
        if specific_pattern
        else "SPORTS CAVE GENERIC CAROUSEL WINNER PATTERN"
    )
    fallback_note = (
        ""
        if specific_pattern
        else "\nINTERNAL NOTE\nUsing generic Sports Cave winner pattern for this category. Do not include this note in customer-facing copy blocks.\n"
    )
    category_block = build_category_winner_angle_block(category, campaign_type, country)
    return f"""{pattern_heading}

PRODUCT
Product name: {product_name}
Category: {category}
Market: {country}
Campaign type: {campaign_type}
{fallback_note}

I have attached the exact Sports Cave product image being advertised.

Analyse the attached image and product title before writing.

Use the supplied product name as the source of identity. Do not guess unsupported people, teams, dates, trophies, records or achievements from the image.

{build_country_campaign_localisation_note(category, country)}

{build_universal_sports_cave_rules(category)}

{category_block}

Create a Meta Carousel ad package.

PRIMARY TEXT

Create exactly 5 primary text variants.

Rules:
- Short, emotional, nostalgic and collector-driven.
- Each variation must connect the product to identity, memory, legacy, rivalry, pride, ownership or the moment.
- Mention limited editions naturally.
- Do not over-explain.

CAROUSEL CARDS

Create exactly 5 carousel cards using these roles:

1. Product Identity
2. Moment / Legacy
3. Emotional Hook
4. Fan Ownership
5. Scarcity

Each card must include:
- role
- headline
- description
- creative direction

Carousel headline and description rules:
- Maximum {CAROUSEL_CARD_MAX_CHARACTERS} characters each.
- No commas.
- No full stops.
- Keep them punchy and readable on mobile.
- Use fragments if needed.
- No duplicate headlines.
- No duplicate descriptions.
- Do not truncate words.
- Count every character before returning the final output.

Creative rules:
- Each card should feel like a sequence, not five random ads.
- Card 1: show the selected framed product clearly.
- Card 2: connect to the sport moment, memory or legacy.
- Card 3: focus on emotional fan identity.
- Card 4: show ownership on a wall, cave, home bar, office or sports room.
- Card 5: make the limited edition feel final.
- Always keep framed artwork unchanged in image prompts.
- No fake logos, fake club marks, fake sponsors, extra text, clutter or competing artwork.

CTA GUIDANCE

Use:
Claim Your Edition

OUTPUT EXACTLY IN THIS FORMAT

CAROUSEL CARDS

Card 1 - Product Identity
Headline:
Description:
Creative direction:

Card 2 - Moment / Legacy
Headline:
Description:
Creative direction:

Card 3 - Emotional Hook
Headline:
Description:
Creative direction:

Card 4 - Fan Ownership
Headline:
Description:
Creative direction:

Card 5 - Scarcity
Headline:
Description:
Creative direction:

PRIMARY TEXT VARIATIONS

Variation 1:
[copy]

Variation 2:
[copy]

Variation 3:
[copy]

Variation 4:
[copy]

Variation 5:
[copy]

CTA GUIDANCE

Claim Your Edition"""


def build_generic_single_image_video_prompt(product_name, category, country, campaign_type):
    product_name = _clean_product_name(product_name)
    specific_pattern = bool(get_category_winner_angle(category))
    pattern_heading = (
        f"SPORTS CAVE {str(category or '').upper()} SINGLE IMAGE VIDEO WINNER PATTERN"
        if specific_pattern
        else "SPORTS CAVE GENERIC SINGLE IMAGE VIDEO WINNER PATTERN"
    )
    fallback_note = (
        ""
        if specific_pattern
        else "\nINTERNAL NOTE\nUsing generic Sports Cave winner pattern for this category. Do not include this note in customer-facing copy blocks.\n"
    )
    category_block = build_category_winner_angle_block(category, campaign_type, country)
    category_setting = get_instant_experience_setting(category)
    return f"""{pattern_heading}

PRODUCT
Product name: {product_name}
Category: {category}
Market: {country}
Campaign type: {campaign_type}
{fallback_note}

I have attached the exact Sports Cave product image being advertised.

Analyse the attached image and product title before writing.

Use the supplied product name as the source of identity. Do not invent unsupported facts, teams, years, trophies, signatures, licensing, records or stock claims.

{build_country_campaign_localisation_note(category, country)}

{build_universal_sports_cave_rules(category)}

{category_block}

Create a Meta Single Image/Video ad package.

PRIMARY TEXT

Create 5 strong primary text variants.

Rules:
- Short, human, emotional and collector-driven.
- Use identity, nostalgia, scarcity and ownership.
- Mention limited editions naturally.
- Do not use generic AI phrases such as elevate your space, ultimate tribute or perfect addition.

HEADLINE

Create 5 headline options.

Rules:
- Short, urgent and category-specific.
- Make them feel like Sports Cave collector advertising, not generic wall art.

DESCRIPTION

Create 5 short description lines.

Rules:
- Scarcity-driven and premium.
- Keep each line compact and human.

CREATIVE PROMPT FOR SINGLE IMAGE/VIDEO

Create one creative prompt for the selected product.

The prompt must instruct the image/video generator:
- Use the uploaded image as the exact reference for the framed Sports Cave artwork.
- Keep the exact artwork, colours, text, frame, badge, crop and layout unchanged.
- Make the selected framed product the hero.
- Use this category-relevant setting: {category_setting}.
- Style: cinematic, premium, masculine, collector-focused and believable.
- No fake logos, fake team branding, clutter, extra artwork competing with the product or unsupported text overlays.

CTA GUIDANCE

Use:
Claim Your Edition

OUTPUT EXACTLY IN THIS FORMAT

PRIMARY TEXT

Variant 1:
[copy]

Variant 2:
[copy]

Variant 3:
[copy]

Variant 4:
[copy]

Variant 5:
[copy]

HEADLINE

1. [headline]
2. [headline]
3. [headline]
4. [headline]
5. [headline]

DESCRIPTION

1. [description]
2. [description]
3. [description]
4. [description]
5. [description]

CREATIVE PROMPT FOR SINGLE IMAGE/VIDEO

[one creative prompt]

CTA GUIDANCE

Claim Your Edition"""


def build_visual_variation_token():
    return secrets.token_hex(6)


def build_ads_prompt(
    product_name,
    category,
    country,
    campaign_type,
    product_url="",
    *,
    variation_token="",
):
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
    elif template_key == "football_instant_experience":
        prompt = build_generic_instant_experience_prompt(
            product_name,
            category,
            country,
            campaign_type,
            product_url=product_url,
            specific_pattern=True,
        )
    elif campaign_type == "Instant Experience":
        prompt = build_generic_instant_experience_prompt(
            product_name,
            category,
            country,
            campaign_type,
            product_url=product_url,
            specific_pattern=bool(template_key),
        )
    elif campaign_type == "Carousel":
        prompt = build_generic_carousel_prompt(
            product_name,
            category,
            country,
            campaign_type,
            specific_pattern=bool(template_key),
        )
    elif campaign_type == "Single Image / Video":
        prompt = build_generic_single_image_video_prompt(product_name, category, country, campaign_type)
    else:
        prompt = ""
    return compose_final_ads_prompt(
        prompt,
        category=category,
        country=country,
        campaign_type=campaign_type,
        include_primary_text_variations=campaign_type == "Carousel",
        product_name=product_name,
        template_key=template_key,
        variation_token=variation_token,
    )


def render_insufficient_winner_data():
    st.subheader("Insufficient winner data")
    st.caption("Approved winner examples have not been added for this category and campaign type yet.")


def render_generic_winner_pattern_note(category, campaign_type):
    if uses_generic_winner_pattern(category, campaign_type):
        st.caption("Using generic Sports Cave winner pattern for this category.")


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
            key="ads_product_name",
        )
    return st.text_input(
        "Product name",
        placeholder="Example: Six Laps Ahead",
        key="ads_product_name",
    )


def record_ad_prompt_generated(product_name, category, country, campaign_type):
    record_activity_log(
        "ad_prompt_generated",
        "Ads",
        f"Generated ad prompt: {product_name}",
        entity_type="ad_prompt",
        metadata={
            "category": category,
            "country": country,
            "campaign_type": campaign_type,
        },
    )


def current_ads_user():
    user = st.session_state.get("sports_cave_current_user")
    if user:
        return dict(user)
    if st.session_state.get("sports_cave_authenticated"):
        return {
            "id": "legacy-master-admin",
            "display_name": "Sports Cave Admin",
            "role": os_accounts.ROLE_ADMIN,
            "timezone": os_accounts.ADMIN_TIMEZONE,
            "page_permissions": [],
            "legacy": True,
        }
    return {}


def ads_result_context_key(product_id, product_name, category, country, campaign_type):
    payload = json.dumps(
        {
            "product_id": str(product_id or ""),
            "product_name": _clean_product_name(product_name),
            "category": str(category or ""),
            "country": str(country or ""),
            "campaign_type": str(campaign_type or ""),
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def build_ads_result_record(
    product_name,
    category,
    country,
    campaign_type,
    *,
    product_id="",
    product_url="",
    variation_token="",
):
    clean_product_name = _clean_product_name(product_name)
    clean_product_id = str(product_id or "").strip()
    clean_variation_token = str(variation_token or "").strip() or build_visual_variation_token()
    master_prompt = build_ads_prompt(
        clean_product_name,
        category,
        country,
        campaign_type,
        product_url=product_url,
        variation_token=clean_variation_token,
    )
    return {
        "context_key": ads_result_context_key(
            clean_product_id,
            clean_product_name,
            category,
            country,
            campaign_type,
        ),
        "product_id": clean_product_id,
        "product_name": clean_product_name,
        "category": str(category or ""),
        "country": str(country or ""),
        "campaign_type": str(campaign_type or ""),
        "product_url": _clean_product_url(product_url),
        "variation_token": clean_variation_token,
        "master_prompt": master_prompt,
        "generated_ad_output": master_prompt,
    }


def _new_ads_image_workflow(result):
    user = current_ads_user()
    timezone_name = os_accounts.timezone_for_user(user) if user else os_accounts.ADMIN_TIMEZONE
    return {
        "context_key": result["context_key"],
        "campaign_type": result["campaign_type"],
        "slots": {},
        "widget_nonces": {},
        "export_date": ads_image_workflow.account_iso_date(timezone_name),
        "save_open": False,
        "saving": False,
        "destination_path": "",
        "picker_path": "",
        "outcomes": {},
    }


def _reset_ads_image_workflow(result):
    current_context = str(result.get("context_key") or "")
    for key in list(st.session_state):
        if str(key).startswith("ads-image-upload::") and current_context not in str(key):
            st.session_state.pop(key, None)
    workflow = _new_ads_image_workflow(result)
    st.session_state[ADS_IMAGE_STATE_KEY] = workflow
    return workflow


def _ads_image_workflow(result):
    workflow = st.session_state.get(ADS_IMAGE_STATE_KEY)
    if not isinstance(workflow, dict) or workflow.get("context_key") != result.get("context_key"):
        workflow = _new_ads_image_workflow(result)
        st.session_state[ADS_IMAGE_STATE_KEY] = workflow
    return workflow


def _slot_upload_key(result, workflow, slot_id):
    nonce = int((workflow.get("widget_nonces") or {}).get(slot_id) or 0)
    return f"ads-image-upload::{result['context_key']}::{slot_id}::{nonce}"


INSTANT_EXPERIENCE_LEGACY_SLOT_IDS = (
    "instant-experience",
    "instant_experience",
    "instant_experience_image",
)


def _is_instant_experience_result(result):
    return result.get("campaign_type") == "Instant Experience"


def _instant_experience_slots_by_position():
    return ads_image_workflow.campaign_image_slots("Instant Experience")


def _compact_instant_experience_slots(workflow):
    slots = workflow.setdefault("slots", {})
    if not isinstance(slots, dict):
        workflow["slots"] = {}
        return
    if slots.get("data") or slots.get("valid"):
        slots = {"instant-experience-01": dict(slots)}
    slot_specs = _instant_experience_slots_by_position()
    ordered = []
    outcomes = workflow.setdefault("outcomes", {})
    ordered_outcomes = []
    seen_ids = set()
    for slot in slot_specs:
        slot_id = slot["id"]
        if slot_id in slots:
            ordered.append(dict(slots[slot_id]))
            ordered_outcomes.append(dict(outcomes.get(slot_id) or {}))
            seen_ids.add(slot_id)
    for slot_id in INSTANT_EXPERIENCE_LEGACY_SLOT_IDS:
        if slot_id in slots and slot_id not in seen_ids:
            ordered.append(dict(slots[slot_id]))
            ordered_outcomes.append(dict(outcomes.get(slot_id) or {}))
            seen_ids.add(slot_id)

    new_slots = {}
    new_outcomes = {}
    for index, slot_data in enumerate(ordered[: len(slot_specs)], start=1):
        slot = slot_specs[index - 1]
        slot_data.update(
            {
                "slot_id": slot["id"],
                "label": slot["label"],
                "position": slot["position"],
            }
        )
        new_slots[slot["id"]] = slot_data
        outcome = ordered_outcomes[index - 1] if index - 1 < len(ordered_outcomes) else {}
        if outcome:
            outcome.update({"label": slot["label"]})
            new_outcomes[slot["id"]] = outcome
    workflow["slots"] = new_slots
    workflow["outcomes"] = new_outcomes


def _ads_image_slot_specs_for_render(result, workflow):
    slot_specs = ads_image_workflow.campaign_image_slots(result.get("campaign_type"))
    if not _is_instant_experience_result(result):
        return slot_specs
    _compact_instant_experience_slots(workflow)
    slots = workflow.get("slots") or {}
    last_valid_position = 0
    for slot in slot_specs:
        if (slots.get(slot["id"]) or {}).get("valid"):
            last_valid_position = max(last_valid_position, int(slot["position"]))
    visible_count = min(len(slot_specs), max(1, last_valid_position + 1))
    return slot_specs[:visible_count]


def _ads_image_valid_slots(result, workflow):
    if _is_instant_experience_result(result):
        _compact_instant_experience_slots(workflow)
    slot_specs = ads_image_workflow.campaign_image_slots(result.get("campaign_type"))
    slots = workflow.get("slots") or {}
    return [
        slot
        for slot in slot_specs
        if (slots.get(slot["id"]) or {}).get("valid") and (slots.get(slot["id"]) or {}).get("data")
    ]


def _ads_image_required_count(result):
    return 1 if _is_instant_experience_result(result) else len(
        ads_image_workflow.campaign_image_slots(result.get("campaign_type"))
    )


def _remove_ads_image_slot(result, slot_id):
    workflow = _ads_image_workflow(result)
    has_other_saved = any(
        outcome.get("status") == "saved"
        for key, outcome in (workflow.get("outcomes") or {}).items()
        if key != slot_id
    )
    workflow.setdefault("slots", {}).pop(slot_id, None)
    workflow.setdefault("outcomes", {}).pop(slot_id, None)
    nonces = workflow.setdefault("widget_nonces", {})
    nonces[slot_id] = int(nonces.get(slot_id) or 0) + 1
    workflow["save_open"] = False
    if not has_other_saved:
        workflow["destination_path"] = ""
    if _is_instant_experience_result(result):
        _compact_instant_experience_slots(workflow)
    st.session_state[ADS_IMAGE_STATE_KEY] = workflow


def _process_ads_image_upload(result, workflow, slot, uploaded_file):
    if uploaded_file is None:
        return
    source_bytes = uploaded_file.getvalue()
    source_hash = ads_image_workflow.source_image_signature(source_bytes)
    existing = (workflow.get("slots") or {}).get(slot["id"]) or {}
    if existing.get("source_hash") == source_hash:
        return
    try:
        processed = ads_image_workflow.optimize_meta_image(
            source_bytes,
            original_name=uploaded_file.name,
        )
        processed.update(
            {
                "slot_id": slot["id"],
                "label": slot["label"],
                "position": slot["position"],
                "valid": True,
                "error": "",
            }
        )
    except ads_image_workflow.AdsImageValidationError as error:
        processed = {
            "slot_id": slot["id"],
            "label": slot["label"],
            "position": slot["position"],
            "source_hash": source_hash,
            "original_name": str(uploaded_file.name or "image"),
            "valid": False,
            "error": str(error),
        }
    workflow.setdefault("slots", {})[slot["id"]] = processed
    outcomes = workflow.setdefault("outcomes", {})
    has_other_saved = any(
        outcome.get("status") == "saved"
        for key, outcome in outcomes.items()
        if key != slot["id"]
    )
    outcomes.pop(slot["id"], None)
    workflow["save_open"] = False
    if not has_other_saved:
        workflow["destination_path"] = ""
    if _is_instant_experience_result(result):
        _compact_instant_experience_slots(workflow)
    st.session_state[ADS_IMAGE_STATE_KEY] = workflow


def ads_images_ready(result, workflow=None):
    workflow = workflow or _ads_image_workflow(result)
    slot_specs = ads_image_workflow.campaign_image_slots(result.get("campaign_type"))
    slots = workflow.get("slots") or {}
    if _is_instant_experience_result(result):
        _compact_instant_experience_slots(workflow)
        slots = workflow.get("slots") or {}
        first_slot = slot_specs[0] if slot_specs else {}
        return bool((slots.get(first_slot.get("id")) or {}).get("valid"))
    return bool(slot_specs) and all((slots.get(slot["id"]) or {}).get("valid") for slot in slot_specs)


def _meta_output_filename(result, workflow, slot):
    return ads_image_workflow.build_meta_image_filename(
        result["product_name"],
        result["campaign_type"],
        position=slot["position"],
        iso_date=workflow["export_date"],
    )


def _render_ads_image_slots(result, workflow):
    slot_specs = _ads_image_slot_specs_for_render(result, workflow)
    if not slot_specs:
        return
    st.subheader("Generated Ad Images")
    if _is_instant_experience_result(result):
        st.caption(
            "Upload the Instant Experience cover generated from the prompt above. Cover 1 is required; cover variations 2-5 are optional."
        )
    else:
        st.caption(
            "Upload the images generated from the prompt above. They will be optimized and saved as individual Meta-ready files."
        )

    def render_slot(slot, index):
        with st.container(border=True, key=f"ads-image-slot::{result['context_key']}::{slot['id']}"):
            st.markdown(f"**{slot['label']}**")
            if result.get("campaign_type") == "Carousel" and index < len(IMAGE_ORDER):
                title, body = IMAGE_ORDER[index]
                st.caption(f"Card {index + 1}: {title}")
                st.caption(body)
            uploaded_file = st.file_uploader(
                slot["label"],
                type=["jpg", "jpeg", "png", "webp"],
                key=_slot_upload_key(result, workflow, slot["id"]),
                max_upload_size=20,
                label_visibility="collapsed",
            )
            _process_ads_image_upload(result, workflow, slot, uploaded_file)
            saved_slot = (workflow.get("slots") or {}).get(slot["id"]) or {}
            if saved_slot.get("valid"):
                st.image(saved_slot["data"], width="stretch")
                st.caption(
                    f"1080 x 1080 JPEG | {saved_slot['output_size'] / (1024 * 1024):.2f} MB"
                )
                st.caption(_meta_output_filename(result, workflow, slot))
                outcome = (workflow.get("outcomes") or {}).get(slot["id"]) or {}
                if outcome.get("status") == "saved":
                    st.success("Saved")
                elif outcome.get("status") == "failed":
                    st.error(outcome.get("error") or "Upload failed.")
                if st.button(
                    "Remove",
                    icon=":material/delete:",
                    key=f"ads-image-remove::{result['context_key']}::{slot['id']}",
                    use_container_width=True,
                ):
                    _remove_ads_image_slot(result, slot["id"])
                    st.rerun()
                st.caption("Drop or browse for a replacement at any time.")
            elif saved_slot.get("error"):
                st.error(saved_slot["error"])
                if st.button(
                    "Remove",
                    icon=":material/delete:",
                    key=f"ads-image-remove-invalid::{result['context_key']}::{slot['id']}",
                    use_container_width=True,
                ):
                    _remove_ads_image_slot(result, slot["id"])
                    st.rerun()

    if _is_instant_experience_result(result):
        for index, slot in enumerate(ads_image_workflow.campaign_image_slots("Instant Experience")):
            if index > 0:
                previous_slot = ads_image_workflow.campaign_image_slots("Instant Experience")[index - 1]
                if not ((workflow.get("slots") or {}).get(previous_slot["id"]) or {}).get("valid"):
                    break
            render_slot(slot, index)
        return

    columns = st.columns(len(slot_specs))
    for index, slot in enumerate(slot_specs):
        with columns[index]:
            render_slot(slot, index)


def _ads_dropbox_connection():
    cached = st.session_state.get("files_access_token") or {}
    if cached.get("token") and float(cached.get("expires_at") or 0) > time.monotonic():
        access_token = cached["token"]
    else:
        auth = dropbox_integration.resolve_server_auth()
        access_token = auth["access_token"]
        source = auth.get("source") or "refresh_token"
        st.session_state["files_access_token"] = {
            "token": access_token,
            "source": source,
            "expires_at": time.monotonic() + (25 * 60 if source == "refresh_token" else 5 * 60),
        }
    root_cache = st.session_state.get("files_team_root") or {}
    if (
        root_cache.get("path")
        and float(root_cache.get("loaded_at") or 0) + 15 * 60 > time.monotonic()
    ):
        root_path = str(root_cache["path"])
    else:
        root_path = dropbox_integration.find_team_folder(access_token)
        st.session_state["files_team_root"] = {
            "path": root_path,
            "loaded_at": time.monotonic(),
        }
    return access_token, root_path


def _ads_directory_entries(access_token, path):
    clean_path = dropbox_integration.normalize_dropbox_path(path)
    cache = st.session_state.setdefault("files_directory_cache", {})
    cached = cache.get(clean_path) or {}
    if float(cached.get("loaded_at") or 0) + ADS_DIRECTORY_CACHE_SECONDS > time.monotonic():
        return list(cached.get("entries") or ())
    entries = dropbox_integration.sort_folder_entries(
        dropbox_integration.list_folder(access_token, clean_path)
    )
    cache[clean_path] = {"loaded_at": time.monotonic(), "entries": entries}
    return entries


def _ads_clear_directory_cache(*paths):
    cache = st.session_state.setdefault("files_directory_cache", {})
    for path in paths:
        cache.pop(dropbox_integration.normalize_dropbox_path(path), None)


def _render_ads_folder_picker(access_token, root_path, result, workflow):
    default_path = dropbox_integration.normalize_dropbox_path(
        f"{root_path}/{ADS_PRODUCT_IMAGES_FOLDER}"
    )
    current_path = dropbox_integration.normalize_dropbox_path(
        workflow.get("picker_path") or default_path
    )
    if not dropbox_integration.path_is_within_root(current_path, root_path):
        current_path = default_path
    dropbox_integration.ensure_folder_path(
        access_token,
        default_path,
        root_path=root_path,
    )
    workflow["picker_path"] = current_path
    st.session_state[ADS_IMAGE_STATE_KEY] = workflow
    folders = [
        entry
        for entry in _ads_directory_entries(access_token, current_path)
        if str(entry.get(".tag") or "").casefold() == "folder"
    ]

    with st.container(key="ads-dropbox-picker"):
        st.markdown('<div class="sc-mockups-dropbox-picker">', unsafe_allow_html=True)
        breadcrumb = dropbox_integration.breadcrumb_items(current_path, root_path)
        breadcrumb_columns = st.columns([1] * max(1, len(breadcrumb)))
        for index, (label, path) in enumerate(breadcrumb):
            target = root_path if not path else path
            with breadcrumb_columns[index]:
                if st.button(
                    str(label),
                    key=f"ads-picker-crumb::{result['context_key']}::{index}::{target}",
                    use_container_width=True,
                ):
                    workflow["picker_path"] = target
                    st.session_state[ADS_IMAGE_STATE_KEY] = workflow
                    st.rerun()

        if folders:
            for folder in folders:
                path = dropbox_integration.normalize_dropbox_path(
                    folder.get("path_display") or folder.get("path_lower") or ""
                )
                if st.button(
                    str(folder.get("name") or "Folder"),
                    icon=":material/folder:",
                    key=f"ads-picker-folder::{result['context_key']}::{path}",
                    use_container_width=True,
                ):
                    workflow["picker_path"] = path
                    st.session_state[ADS_IMAGE_STATE_KEY] = workflow
                    st.rerun()
        else:
            st.caption("No subfolders here.")

        with st.popover("New folder", icon=":material/create_new_folder:"):
            folder_name = st.text_input(
                "Folder name",
                key=f"ads-picker-new-name::{result['context_key']}::{current_path}",
            )
            if st.button(
                "Create",
                key=f"ads-picker-new-submit::{result['context_key']}::{current_path}",
                use_container_width=True,
            ):
                try:
                    metadata = dropbox_integration.create_folder(
                        access_token,
                        current_path,
                        folder_name,
                        conflict="keep_both",
                    )
                    if metadata:
                        _ads_clear_directory_cache(current_path)
                        workflow["picker_path"] = str(
                            metadata.get("path_display")
                            or metadata.get("path_lower")
                            or current_path
                        )
                        st.session_state[ADS_IMAGE_STATE_KEY] = workflow
                        record_activity_log(
                            "files_folder_created",
                            "Ads",
                            f"Folder created: {metadata.get('name') or folder_name}",
                            entity_type="dropbox_folder",
                            entity_id=workflow["picker_path"],
                        )
                        st.rerun()
                except Exception as error:
                    logging.warning("Ads destination folder creation failed: %s", error)
                    st.warning("This folder could not be created.")
        st.markdown("</div>", unsafe_allow_html=True)
    return current_path


def save_ads_images_to_dropbox(
    access_token,
    root_path,
    destination,
    result,
    workflow,
    *,
    progress_callback=None,
):
    clean_root = dropbox_integration.normalize_dropbox_path(root_path)
    clean_destination = dropbox_integration.normalize_dropbox_path(destination)
    if not dropbox_integration.path_is_within_root(clean_destination, clean_root):
        raise ValueError("The selected destination is outside the approved Files folder.")
    slot_specs = ads_image_workflow.campaign_image_slots(result.get("campaign_type"))
    if _is_instant_experience_result(result):
        _compact_instant_experience_slots(workflow)
        slot_specs = tuple(_ads_image_valid_slots(result, workflow))
    outcomes = dict(workflow.get("outcomes") or {})
    pending_slots = [
        slot for slot in slot_specs if (outcomes.get(slot["id"]) or {}).get("status") != "saved"
    ]
    total = len(pending_slots)
    for index, slot in enumerate(pending_slots, start=1):
        slot_data = (workflow.get("slots") or {}).get(slot["id"]) or {}
        if not slot_data.get("valid") or not slot_data.get("data"):
            outcomes[slot["id"]] = {
                "status": "failed",
                "error": "A valid optimized image is required.",
                "label": slot["label"],
            }
            continue
        resolved_filename = ""
        try:
            filename = _meta_output_filename(result, workflow, slot)
            proposed_path = dropbox_integration.join_upload_path(clean_destination, filename)
            if dropbox_integration.get_metadata_if_exists(access_token, proposed_path):
                proposed_path = dropbox_integration.windows_numbered_path(access_token, proposed_path)
            resolved_filename = PurePosixPath(proposed_path).name

            def on_upload_progress(_row_index, _row_total, _name, uploaded, file_total):
                if progress_callback:
                    progress_callback(index, total, slot["label"], uploaded, file_total)

            upload_result = dropbox_integration.upload_batch(
                access_token,
                clean_destination,
                [
                    {
                        "relative_path": resolved_filename,
                        "data": slot_data["data"],
                        "size": len(slot_data["data"]),
                    }
                ],
                conflict="cancel",
                progress_callback=on_upload_progress,
            )
            successes = list(upload_result.get("successes") or ())
            failures = list(upload_result.get("failures") or ())
            if successes:
                metadata = dict(successes[0].get("metadata") or {})
                saved_path = str(
                    metadata.get("path_display")
                    or metadata.get("path_lower")
                    or proposed_path
                )
                outcomes[slot["id"]] = {
                    "status": "saved",
                    "label": slot["label"],
                    "filename": resolved_filename,
                    "path": saved_path,
                    "metadata": metadata,
                }
            else:
                outcomes[slot["id"]] = {
                    "status": "failed",
                    "label": slot["label"],
                    "filename": resolved_filename,
                    "error": str(
                        (failures[0] if failures else {}).get("error") or "Upload failed."
                    ),
                }
        except Exception as error:
            outcomes[slot["id"]] = {
                "status": "failed",
                "label": slot["label"],
                "filename": resolved_filename,
                "error": str(error)[:300] or "Upload failed.",
            }
    return outcomes


def _save_ads_upload_metadata(outcomes, user):
    try:
        import supabase_backend
    except Exception:
        return
    for outcome in outcomes.values():
        if outcome.get("status") != "saved":
            continue
        metadata = dict(outcome.get("metadata") or {})
        if not metadata:
            continue
        try:
            supabase_backend.save_dropbox_asset_metadata(
                dropbox_integration.normalise_asset_metadata(
                    dropbox_file_id=metadata.get("id"),
                    dropbox_path=outcome.get("path"),
                    name=metadata.get("name") or outcome.get("filename"),
                    size=metadata.get("size"),
                    asset_type="meta_ads",
                    uploaded_by_user_name=str(
                        user.get("display_name")
                        or user.get("email")
                        or user.get("username")
                        or "sports_cave_os"
                    ),
                    uploaded_by_user_email=user.get("email") or "",
                )
            )
        except Exception:
            continue


def _open_ads_files_folder(path):
    clean_path = dropbox_integration.normalize_dropbox_path(path)
    st.session_state["files_browser_path"] = clean_path
    st.session_state.pop("files_preview_path", None)
    st.session_state["current_page"] = "Files"
    st.session_state["selected_page"] = "Files"
    st.session_state["current_page_source"] = "ads-image-export"
    try:
        st.query_params["page"] = "files"
        st.query_params["files_path"] = clean_path
    except Exception:
        pass
    st.rerun()


def _render_ads_image_save(result, workflow):
    if not ads_image_workflow.campaign_image_slots(result.get("campaign_type")):
        return
    if _is_instant_experience_result(result):
        _compact_instant_experience_slots(workflow)
    ready = ads_images_ready(result, workflow)
    valid_slots = _ads_image_valid_slots(result, workflow)
    saved_count = sum(
        1 for outcome in (workflow.get("outcomes") or {}).values() if outcome.get("status") == "saved"
    )
    required_count = _ads_image_required_count(result)
    save_target_count = max(required_count, len(valid_slots))
    failed_count = sum(
        1 for outcome in (workflow.get("outcomes") or {}).values() if outcome.get("status") == "failed"
    )
    all_saved = ready and saved_count >= len(valid_slots) and bool(valid_slots) and not failed_count
    if not ready:
        st.caption(f"{len(valid_slots)} of {required_count} images ready.")
    elif _is_instant_experience_result(result):
        st.caption(
            f"{len(valid_slots)} Instant Experience {'cover' if len(valid_slots) == 1 else 'covers'} ready."
        )
    if st.button(
        "Save Images",
        type="primary",
        icon=":material/save:",
        key=f"ads-images-save-open::{result['context_key']}",
        disabled=(
            bool(workflow.get("saving"))
            or all_saved
            or (not _is_instant_experience_result(result) and not ready)
        ),
        use_container_width=True,
    ):
        if _is_instant_experience_result(result) and not ready:
            st.warning("Upload Instant Experience cover 1 before saving.")
            return
        workflow["save_open"] = True
        st.session_state[ADS_IMAGE_STATE_KEY] = workflow
        st.rerun()
    if not workflow.get("save_open"):
        return

    user = current_ads_user()
    if not os_accounts.can_access_page(user, "Files"):
        st.info("Files access is not approved for this account.")
        return
    try:
        access_token, root_path = _ads_dropbox_connection()
        locked_destination = str(workflow.get("destination_path") or "")
        destination = locked_destination or _render_ads_folder_picker(
            access_token,
            root_path,
            result,
            workflow,
        )
    except Exception as error:
        logging.warning("Ads Dropbox destination unavailable: %s", error)
        st.info("Dropbox is unavailable right now.")
        return

    st.caption(f"Destination: {destination}")
    remaining_count = max(0, save_target_count - saved_count)
    action_label = (
        "All images saved"
        if all_saved
        else "Retry failed images"
        if failed_count
        else f"Save {remaining_count} {'image' if remaining_count == 1 else 'images'} here"
    )
    action_columns = st.columns([1, 1])
    if action_columns[0].button(
        action_label,
        key=f"ads-images-save-confirm::{result['context_key']}",
        disabled=bool(workflow.get("saving")) or all_saved,
        use_container_width=True,
    ):
        workflow["saving"] = True
        st.session_state[ADS_IMAGE_STATE_KEY] = workflow
        progress = st.progress(0, text="Saving Meta-ready images...")

        def update_progress(index, total, label, uploaded, file_total):
            file_fraction = uploaded / file_total if file_total else 1
            overall = ((index - 1) + min(1, file_fraction)) / max(1, total)
            progress.progress(min(1.0, overall), text=f"Saving {label}")

        try:
            workflow["destination_path"] = destination
            previously_saved = {
                slot_id
                for slot_id, outcome in (workflow.get("outcomes") or {}).items()
                if outcome.get("status") == "saved"
            }
            outcomes = save_ads_images_to_dropbox(
                access_token,
                root_path,
                destination,
                result,
                workflow,
                progress_callback=update_progress,
            )
            workflow["outcomes"] = outcomes
            _save_ads_upload_metadata(
                {
                    slot_id: outcome
                    for slot_id, outcome in outcomes.items()
                    if slot_id not in previously_saved
                },
                user,
            )
            successful = [row for row in outcomes.values() if row.get("status") == "saved"]
            failed = [row for row in outcomes.values() if row.get("status") == "failed"]
            _ads_clear_directory_cache(destination)
            record_activity_log(
                "ad_images_saved",
                "Ads",
                f"Saved {len(successful)} Meta-ready images: {result['product_name']}",
                entity_type="dropbox_folder",
                entity_id=destination,
                metadata={
                    "count": len(successful),
                    "failed_count": len(failed),
                    "campaign_type": result["campaign_type"],
                    "destination": destination,
                    "files": [row.get("filename") for row in successful],
                },
            )
        except Exception as error:
            logging.warning("Ads image save failed: %s", error)
            st.warning("The Meta-ready images could not be saved.")
        finally:
            progress.empty()
            workflow["saving"] = False
            st.session_state[ADS_IMAGE_STATE_KEY] = workflow
        st.rerun()
    if action_columns[1].button(
        "Cancel",
        key=f"ads-images-save-cancel::{result['context_key']}",
        use_container_width=True,
    ):
        workflow["save_open"] = False
        st.session_state[ADS_IMAGE_STATE_KEY] = workflow
        st.rerun()

    outcomes = workflow.get("outcomes") or {}
    successful = [row for row in outcomes.values() if row.get("status") == "saved"]
    failed = [row for row in outcomes.values() if row.get("status") == "failed"]
    if successful:
        if failed:
            st.warning(f"{len(successful)} of {save_target_count} images saved. {len(failed)} need attention.")
        else:
            st.success(f"{len(successful)} images saved to {workflow['destination_path']}.")
        if st.button(
            "Open folder",
            icon=":material/folder_open:",
            key=f"ads-images-open-folder::{result['context_key']}",
        ):
            _open_ads_files_folder(workflow["destination_path"])
    for outcome in failed:
        st.error(f"{outcome.get('label')}: {outcome.get('error') or 'Upload failed.'}")


def _ads_review_prefill(result):
    generated_output = str(result.get("generated_ad_output") or "").strip()
    master_prompt = str(result.get("master_prompt") or "").strip()
    return generated_output if generated_output and generated_output != master_prompt else ""


def build_ads_review_context(result):
    winner_angle = get_category_winner_angle(result.get("category")) or {}
    generated_copy = _ads_review_prefill(result)
    return {
        "product_name": str(result.get("product_name") or ""),
        "category": str(result.get("category") or ""),
        "country": str(result.get("country") or ""),
        "campaign_type": str(result.get("campaign_type") or ""),
        "campaign_angle": str(
            result.get("selected_campaign_angle")
            or winner_angle.get("emotion")
            or ""
        ),
        "generated_primary_text": str(
            result.get("generated_primary_text") or generated_copy
        ),
        "headlines": list(result.get("headlines") or ()),
        "descriptions": list(result.get("descriptions") or ()),
        "cta": str(result.get("cta") or ""),
        "product_url": str(result.get("product_url") or ""),
        "carousel_character_limit": CAROUSEL_CARD_MAX_CHARACTERS,
    }


def build_final_ad_review_landing_page_block(product_page_url):
    clean_url = _clean_product_url(product_page_url)
    return FINAL_REVIEW_LANDING_PAGE_BLOCK_TEMPLATE.format(product_page_url=clean_url)


def build_final_ad_review_copy_prompt(result, *, resolved_prompt=None):
    context = build_ads_review_context(result)
    base_prompt = str(
        resolved_prompt
        if resolved_prompt is not None
        else ads_final_review.build_review_instructions(CAROUSEL_CARD_MAX_CHARACTERS)
    )
    context_text = ads_final_review.build_review_context(context, "")
    landing_page_block = build_final_ad_review_landing_page_block(context.get("product_url") or "")
    return (
        f"{base_prompt.rstrip()}\n\n"
        "CAMPAIGN CONTEXT\n\n"
        f"{context_text}\n\n"
        f"{landing_page_block}"
    )


def _new_ads_review_workflow(result):
    return {
        "context_key": str(result.get("context_key") or ""),
        "screenshots": [],
        "creatives": [],
        "upload_nonces": {"screenshots": 0, "creatives": 0},
        "errors": {"screenshots": [], "creatives": []},
        "final_copy": _ads_review_prefill(result),
        "running": False,
        "request_id": "",
        "review": None,
        "error": "",
    }


def _clear_ads_review_widget_state(context_key):
    prefixes = (
        f"ads-review-screenshots::{context_key}",
        f"ads-review-creatives::{context_key}",
        f"ads-review-final-copy::{context_key}",
    )
    for key in list(st.session_state):
        if any(str(key).startswith(prefix) for prefix in prefixes):
            st.session_state.pop(key, None)


def _ads_review_workflow(result):
    workflow = st.session_state.get(ADS_REVIEW_STATE_KEY)
    if not isinstance(workflow, dict) or workflow.get("context_key") != result.get("context_key"):
        if isinstance(workflow, dict):
            _clear_ads_review_widget_state(str(workflow.get("context_key") or ""))
        workflow = _new_ads_review_workflow(result)
        st.session_state[ADS_REVIEW_STATE_KEY] = workflow
    return workflow


def _review_upload_key(result, workflow, kind):
    nonce = int((workflow.get("upload_nonces") or {}).get(kind) or 0)
    return f"ads-review-{kind}::{result['context_key']}::{nonce}"


def _process_review_uploads(result, workflow, kind, uploaded_files):
    if not uploaded_files:
        return
    existing = list(workflow.get(kind) or ())
    signatures = {str(item.get("signature") or "") for item in existing}
    errors = []
    changed = False
    limit = (
        ads_final_review.MAX_SCREENSHOTS
        if kind == "screenshots"
        else ads_final_review.MAX_CREATIVES
    )
    for uploaded_file in uploaded_files:
        if len(existing) >= limit:
            errors.append(f"Upload no more than {limit} images in this area.")
            break
        try:
            item = ads_final_review.validate_review_image(
                uploaded_file.getvalue(),
                filename=uploaded_file.name,
            )
            if item["signature"] not in signatures:
                existing.append(item)
                signatures.add(item["signature"])
                changed = True
        except ads_final_review.AdsReviewValidationError as error:
            errors.append(f"{ads_final_review.sanitize_review_filename(uploaded_file.name)}: {error}")
    try:
        candidate_screenshots = existing if kind == "screenshots" else workflow.get("screenshots")
        candidate_creatives = existing if kind == "creatives" else workflow.get("creatives")
        ads_final_review.validate_review_upload_set(candidate_screenshots, candidate_creatives)
    except ads_final_review.AdsReviewValidationError as error:
        errors.append(str(error))
    else:
        workflow[kind] = existing
    previous_errors = list((workflow.get("errors") or {}).get(kind) or ())
    workflow.setdefault("errors", {})[kind] = errors
    if changed or errors != previous_errors:
        workflow["review"] = None
        workflow["error"] = ""
        st.session_state[ADS_REVIEW_STATE_KEY] = workflow


def _remove_review_image(result, kind, index):
    workflow = _ads_review_workflow(result)
    items = list(workflow.get(kind) or ())
    if 0 <= index < len(items):
        items.pop(index)
    workflow[kind] = items
    nonces = workflow.setdefault("upload_nonces", {})
    nonces[kind] = int(nonces.get(kind) or 0) + 1
    workflow["review"] = None
    workflow["error"] = ""
    st.session_state[ADS_REVIEW_STATE_KEY] = workflow


def _move_review_image(result, kind, index, offset):
    workflow = _ads_review_workflow(result)
    items = list(workflow.get(kind) or ())
    target = index + offset
    if 0 <= index < len(items) and 0 <= target < len(items):
        items[index], items[target] = items[target], items[index]
        workflow[kind] = items
        workflow["review"] = None
        workflow["error"] = ""
        st.session_state[ADS_REVIEW_STATE_KEY] = workflow


def _render_review_image_list(result, workflow, kind):
    items = list(workflow.get(kind) or ())
    if not items:
        return
    for index, item in enumerate(items):
        with st.container(
            border=True,
            key=f"ads-review-{kind}-item::{result['context_key']}::{item['id']}::{index}",
        ):
            image_column, detail_column = st.columns([1, 2])
            with image_column:
                st.image(item["data"], width="stretch")
            with detail_column:
                st.markdown(f"**{html.escape(item['filename'])}**")
                st.caption(
                    f"{item['width']} x {item['height']} | "
                    f"{item['format']} | {item['size'] / (1024 * 1024):.2f} MB"
                )
                controls = st.columns(3)
                if controls[0].button(
                    "Earlier",
                    icon=":material/arrow_upward:",
                    key=f"ads-review-{kind}-up::{result['context_key']}::{item['id']}::{index}",
                    disabled=index == 0,
                    help="Move this image earlier in the review order.",
                    use_container_width=True,
                ):
                    _move_review_image(result, kind, index, -1)
                    st.rerun()
                if controls[1].button(
                    "Later",
                    icon=":material/arrow_downward:",
                    key=f"ads-review-{kind}-down::{result['context_key']}::{item['id']}::{index}",
                    disabled=index == len(items) - 1,
                    help="Move this image later in the review order.",
                    use_container_width=True,
                ):
                    _move_review_image(result, kind, index, 1)
                    st.rerun()
                if controls[2].button(
                    "Remove",
                    icon=":material/delete:",
                    key=f"ads-review-{kind}-remove::{result['context_key']}::{item['id']}::{index}",
                    help="Remove this image. Upload its replacement above if needed.",
                    use_container_width=True,
                ):
                    _remove_review_image(result, kind, index)
                    st.rerun()


def _render_review_upload_area(result, workflow, kind, label, help_text):
    with st.container(border=True, key=f"ads-review-upload-area::{kind}::{result['context_key']}"):
        st.markdown(f"**{label}**")
        st.caption(help_text)
        uploaded_files = st.file_uploader(
            label,
            type=["png", "jpg", "jpeg", "webp"],
            accept_multiple_files=True,
            key=_review_upload_key(result, workflow, kind),
            max_upload_size=20,
            label_visibility="collapsed",
        )
        _process_review_uploads(result, workflow, kind, uploaded_files)
        for error in (workflow.get("errors") or {}).get(kind) or ():
            st.error(error)
        _render_review_image_list(result, workflow, kind)


def _review_ready(workflow):
    has_screenshot = bool(workflow.get("screenshots"))
    has_copy_and_creative = bool(
        str(workflow.get("final_copy") or "").strip() and workflow.get("creatives")
    )
    return has_screenshot or has_copy_and_creative


def _render_review_score(review):
    score = float(review.get("overall_score") or 0)
    verdict = html.escape(str(review.get("verdict") or "Needs Work"))
    st.markdown(
        f"""
        <div class="sc-ad-review-score">
            <div>
                <span class="sc-ad-review-score-label">Overall Score</span>
                <strong>{score:.1f} / 10</strong>
            </div>
            <span class="sc-ad-review-verdict">{verdict}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("#### Brutal Truth")
    st.write(str(review.get("brutal_truth") or ""))
    st.markdown("#### Score Breakdown")
    for row in review.get("score_breakdown") or ():
        columns = st.columns([4, 1])
        columns[0].write(str(row.get("category") or ""))
        columns[1].markdown(
            f"**{float(row.get('points_earned') or 0):g} / {int(row.get('points_available') or 0)}**"
        )


def _render_review_result(result, workflow):
    review = workflow.get("review")
    if not isinstance(review, dict):
        return
    _render_review_score(review)

    st.markdown("#### What Is Working")
    strengths = review.get("strengths") or ()
    if strengths:
        for strength in strengths:
            st.markdown(f"- {strength}")
    else:
        st.caption("No strength was confirmed strongly enough to preserve.")

    st.markdown("#### Highest-Impact Final Changes")
    changes = review.get("priority_changes") or ()
    if not changes:
        st.success("No high-impact changes are required.")
    for index, change in enumerate(changes, start=1):
        priority = str(change.get("priority") or "Medium")
        with st.container(
            border=True,
            key=f"ads-review-change::{result['context_key']}::{index}",
        ):
            st.markdown(
                f'<span class="sc-ad-review-priority sc-ad-review-priority-{priority.casefold()}">'
                f"{html.escape(priority)}</span>",
                unsafe_allow_html=True,
            )
            st.markdown(f"**What is wrong:** {change.get('what_is_wrong') or ''}")
            st.write(f"Why it could reduce conversions: {change.get('conversion_risk') or ''}")
            st.write(f"Exact correction: {change.get('exact_correction') or ''}")
            st.caption(f"Expected impact: {change.get('expected_impact') or ''}")

    st.markdown("#### Creative-by-Creative Review")
    creatives = list(workflow.get("creatives") or ())
    for index, creative_review in enumerate(review.get("creative_reviews") or (), start=1):
        image_number = int(creative_review.get("image_number") or index)
        with st.container(
            border=True,
            key=f"ads-review-creative-result::{result['context_key']}::{index}",
        ):
            columns = st.columns([1, 2])
            if 1 <= image_number <= len(creatives):
                columns[0].image(creatives[image_number - 1]["data"], width="stretch")
            else:
                columns[0].caption("Creative preview unavailable")
            with columns[1]:
                st.markdown(
                    f"**Card/image {image_number} | "
                    f"{float(creative_review.get('score') or 0):.1f} / 10**"
                )
                st.caption(f"Purpose: {creative_review.get('purpose') or ''}")
                st.write(f"Visual verdict: {creative_review.get('visual_verdict') or ''}")
                st.write(f"Copy-to-image alignment: {creative_review.get('copy_alignment') or ''}")
                st.write(
                    f"Required correction: "
                    f"{creative_review.get('required_correction') or 'Keep as is'}"
                )

    st.markdown("#### Copy Review")
    for index, copy_item in enumerate(review.get("copy_review") or (), start=1):
        with st.container(
            border=True,
            key=f"ads-review-copy-result::{result['context_key']}::{index}",
        ):
            st.markdown(f"**{copy_item.get('field') or 'Copy'}**")
            st.write(str(copy_item.get("verdict") or ""))
            if copy_item.get("unsupported_claims"):
                st.warning(str(copy_item["unsupported_claims"]))
            original = str(copy_item.get("original") or "")
            replacement = str(copy_item.get("replacement") or "")
            if replacement and replacement != original:
                st.caption("Original")
                st.code(original, language="text")
                st.caption("Replace with")
                st.code(replacement, language="text")
                render_prompt_copy_button(
                    replacement,
                    f"ads-review-copy-replacement::{result['context_key']}::{index}",
                    label="Copy replacement",
                )
                maximum = int(copy_item.get("maximum_character_count") or 0)
                if maximum:
                    st.caption(
                        f"{int(copy_item.get('current_character_count') or 0)} / {maximum} characters | "
                        f"replacement {int(copy_item.get('replacement_character_count') or 0)} / {maximum}"
                    )

    recommended_copy = str(review.get("recommended_final_copy") or "").strip()
    if recommended_copy:
        st.markdown("#### Recommended Final Version")
        st.code(recommended_copy, language="text")
        render_prompt_copy_button(
            recommended_copy,
            f"ads-review-final-copy::{result['context_key']}",
            label="Copy final version",
        )

    st.markdown("#### Launch Decision")
    st.markdown(f"**{review.get('launch_decision') or ''}**")
    for action in (review.get("next_actions") or ())[:3]:
        st.markdown(f"- {action}")

    st.markdown("#### Test Recommendation")
    st.write(str(review.get("test_recommendation") or ""))
    unverified = review.get("unverified_items") or ()
    if unverified:
        st.markdown("**Unable to verify from the supplied ad**")
        for item in unverified:
            st.markdown(f"- {item}")


def _submit_ads_review(result, workflow):
    request_id = secrets.token_hex(12)
    workflow["running"] = True
    workflow["request_id"] = request_id
    workflow["error"] = ""
    st.session_state[ADS_REVIEW_STATE_KEY] = workflow
    try:
        with st.spinner("Reviewing the complete ad..."):
            review = ads_final_review.request_final_ad_review(
                build_ads_review_context(result),
                workflow.get("screenshots") or (),
                workflow.get("creatives") or (),
                workflow.get("final_copy") or "",
            )
        current = st.session_state.get(ADS_REVIEW_STATE_KEY)
        if (
            isinstance(current, dict)
            and current.get("context_key") == result.get("context_key")
            and current.get("request_id") == request_id
        ):
            current["review"] = review
            current["error"] = ""
            current["running"] = False
            st.session_state[ADS_REVIEW_STATE_KEY] = current
    except (
        ads_final_review.AdsReviewError,
        ads_final_review.AdsReviewValidationError,
    ) as error:
        current = st.session_state.get(ADS_REVIEW_STATE_KEY)
        if isinstance(current, dict) and current.get("request_id") == request_id:
            current["error"] = str(error)
            current["running"] = False
            st.session_state[ADS_REVIEW_STATE_KEY] = current
    except Exception:
        current = st.session_state.get(ADS_REVIEW_STATE_KEY)
        if isinstance(current, dict) and current.get("request_id") == request_id:
            current["error"] = (
                "The review could not be completed. Your uploads are still available to retry."
            )
            current["running"] = False
            st.session_state[ADS_REVIEW_STATE_KEY] = current


def _render_final_ad_review(result):
    st.markdown('<div class="sc-ad-review-heading">Final Ad Review</div>', unsafe_allow_html=True)
    st.caption(
        "Upload screenshots of the finished Meta campaign to ChatGPT, then paste the review prompt below."
    )
    with st.expander("How to complete the final review", expanded=False):
        st.markdown("\n\n".join(FINAL_REVIEW_HOW_TO_STEPS))
    render_prompt_copy_button(
        build_final_ad_review_copy_prompt(result),
        f"ads-final-review-prompt::{result['context_key']}",
        label="Copy Final Review Prompt",
        success_label="Final review prompt copied",
    )


def render_supported_result(result):
    product_name = result["product_name"]
    category = result["category"]
    country = result["country"]
    campaign_type = result["campaign_type"]
    render_generic_winner_pattern_note(category, campaign_type)
    master_prompt = result["master_prompt"]
    workflow = _ads_image_workflow(result)

    if get_template_key(category, campaign_type) == "baseball_instant_experience":
        st.subheader("1. Copy this ChatGPT prompt")
        render_prompt_copy_button(
            master_prompt,
            f"ads-prompt::{category}::{country}::{campaign_type}::{product_name}",
        )

        _render_ads_image_slots(result, workflow)
        _render_ads_image_save(result, workflow)
        st.subheader("2. Build it in Meta")
        st.caption("Follow the INSTANT EXPERIENCE SETUP section inside the generated prompt.")
        render_meta_url_parameters_section(3)
        return

    if campaign_type == "Instant Experience":
        st.subheader("1. Copy this ChatGPT prompt")
        render_prompt_copy_button(
            master_prompt,
            f"ads-prompt::{category}::{country}::{campaign_type}::{product_name}",
        )

        _render_ads_image_slots(result, workflow)
        _render_ads_image_save(result, workflow)
        st.subheader("2. Build it in Meta")
        st.caption("Upload the Instant Experience cover generated from the prompt above.")
        render_meta_url_parameters_section(3)
        return

    if campaign_type == "Single Image / Video":
        st.subheader("1. Copy this ChatGPT prompt")
        render_prompt_copy_button(
            master_prompt,
            f"ads-prompt::{category}::{country}::{campaign_type}::{product_name}",
        )

        st.subheader("2. Build it in Meta")
        st.caption("Use the generated creative prompt, copy variants, headlines, descriptions and CTA guidance.")
        render_meta_url_parameters_section(3)
        return

    st.subheader("1. Copy this ChatGPT prompt")
    render_prompt_copy_button(
        master_prompt,
        f"ads-prompt::{category}::{country}::{campaign_type}::{product_name}",
    )

    _render_ads_image_slots(result, workflow)
    _render_ads_image_save(result, workflow)
    st.caption("Upload them to Meta in this exact order before adding the carousel copy.")

    st.subheader("2. Build it in Meta")
    for index, step in enumerate(META_BUILD_ORDER, start=1):
        st.markdown(f"{index}. {step}")
    st.caption("Review every fact before publishing. Remove anything that cannot be confirmed from the product or artwork.")
    render_meta_url_parameters_section(3)


def render_page():
    st.markdown(
        """
        <style>
        div[class*="st-key-ads-image-slot"] {
            min-width: 0;
        }
        div[class*="st-key-ads-image-slot"] [data-testid="stFileUploaderDropzone"] {
            min-height: 92px;
            padding: 0.45rem;
        }
        .st-key-ads-dropbox-picker button {
            background: transparent !important;
            border: 1px solid transparent !important;
            border-radius: 4px !important;
            box-shadow: none !important;
            min-height: 30px !important;
        }
        .st-key-ads-dropbox-picker button:hover {
            background: #EAF2F8 !important;
            border-color: #C5D5E0 !important;
        }
        .sc-ad-review-heading {
            margin-top: 2.25rem;
            padding-top: 1.5rem;
            border-top: 1px solid #E2E2E2;
            color: #161616;
            font-size: 1.55rem;
            font-weight: 700;
        }
        .sc-ad-review-score {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            margin: 1rem 0;
            padding: 1rem 1.1rem;
            border: 1px solid #D9D9D9;
            border-left: 4px solid #D7A33D;
            border-radius: 6px;
            background: #FFFFFF;
        }
        .sc-ad-review-score-label {
            display: block;
            margin-bottom: 0.15rem;
            color: #686868;
            font-size: 0.8rem;
        }
        .sc-ad-review-score strong {
            color: #111111;
            font-size: 2rem;
        }
        .sc-ad-review-verdict,
        .sc-ad-review-priority {
            display: inline-block;
            padding: 0.22rem 0.48rem;
            border: 1px solid #C9A24E;
            border-radius: 4px;
            background: #FFF8E6;
            color: #5C4309;
            font-size: 0.78rem;
            font-weight: 700;
        }
        .sc-ad-review-priority-critical {
            border-color: #C53A3A;
            background: #FFF0F0;
            color: #8D1515;
        }
        .sc-ad-review-priority-high {
            border-color: #D48329;
            background: #FFF5E8;
            color: #7A4100;
        }
        .sc-ad-review-priority-optional {
            border-color: #A8A8A8;
            background: #F5F5F5;
            color: #555555;
        }
        @media (max-width: 720px) {
            .sc-ad-review-score {
                align-items: flex-start;
                flex-direction: column;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.title("Ads")
    st.caption("Build Meta ad instructions from approved Sports Cave winner patterns.")

    with st.expander("How to use", expanded=False):
        st.markdown(
            "1. Enter the product and select the sport, country and campaign type.\n"
            "2. Select Submit.\n"
            "3. Upload the black-framed Sports Cave product WebP into ChatGPT.\n"
            "4. Copy and paste the generated master prompt.\n"
            "5. ChatGPT will return the ad copy first and the matching image prompt or prompts underneath.\n"
            "6. Generate and upload the images in the displayed order."
        )
        st.warning(
            "Use the product name as the identity source. ChatGPT must not guess a person, event or achievement from the image."
        )

    with st.form("ads-builder-form"):
        product_name = render_product_name_input()
        category_col, country_col, campaign_col = st.columns(3)
        with category_col:
            category = st.selectbox("Category", CATEGORY_OPTIONS, key="ads_category")
        with country_col:
            country = st.selectbox("Country", COUNTRY_OPTIONS, key="ads_country")
        with campaign_col:
            campaign_type = st.selectbox(
                "Campaign type",
                CAMPAIGN_TYPE_OPTIONS,
                key="ads_campaign_type",
            )
        product_url = st.text_input(
            "Product page URL *",
            placeholder="https://sportscave.com.au/products/example",
            key="ads_product_url",
        )
        if product_url and not is_valid_product_page_url(product_url):
            st.error(PRODUCT_URL_ERROR)
        submitted = st.form_submit_button(
            "Submit",
            type="primary",
        )

    result = st.session_state.get(ADS_RESULT_STATE_KEY)
    if submitted:
        validation_message = validate_ads_inputs(
            product_name,
            category,
            country,
            campaign_type,
            product_url=product_url,
        )
        if validation_message:
            if validation_message == PRODUCT_URL_ERROR:
                st.error(validation_message)
                components.html(
                    """
                    <script>
                    (() => {
                      const labels = Array.from(window.parent.document.querySelectorAll('label'));
                      const targetLabel = labels.find((label) => label.textContent.trim() === 'Product page URL *');
                      const input = targetLabel
                        ? window.parent.document.getElementById(targetLabel.getAttribute('for'))
                        : null;
                      if (input) input.focus();
                    })();
                    </script>
                    """,
                    height=0,
                )
            else:
                st.warning(validation_message)
        elif not get_winner_pattern_key(category, campaign_type):
            render_insufficient_winner_data()
        else:
            product_id = resolve_edition_ops_product_id(product_name)
            context_key = ads_result_context_key(
                product_id,
                product_name,
                category,
                country,
                campaign_type,
            )
            existing_result = result if isinstance(result, dict) else {}
            if existing_result.get("context_key") == context_key:
                if _clean_product_url(product_url) != existing_result.get("product_url"):
                    result = build_ads_result_record(
                        product_name,
                        category,
                        country,
                        campaign_type,
                        product_id=product_id,
                        product_url=product_url,
                        variation_token=existing_result.get("variation_token"),
                    )
                else:
                    result = existing_result
            else:
                result = build_ads_result_record(
                    product_name,
                    category,
                    country,
                    campaign_type,
                    product_id=product_id,
                    product_url=product_url,
                    variation_token=build_visual_variation_token(),
                )
                _reset_ads_image_workflow(result)
            st.session_state[ADS_RESULT_STATE_KEY] = result
            record_ad_prompt_generated(product_name, category, country, campaign_type)

    result = st.session_state.get(ADS_RESULT_STATE_KEY)
    if isinstance(result, dict) and result.get("master_prompt"):
        render_supported_result(result)
        _render_final_ad_review(result)


render_ads_page = render_page
render_marketing_factory_page = render_page
