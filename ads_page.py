import csv
import hashlib
import html
import io
import importlib
import json
import logging
import random
import re
import secrets
import time
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import streamlit as st
import streamlit.components.v1 as components

from activity_log import record_activity_log
from ads_image_contracts import INSTANT_EXPERIENCE_CONCEPTS
from ads_product_catalog import load_live_edition_product_rows
import dropbox_integration
import os_accounts
from sports_cave_prompt_blocks import (
    SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER,
    build_sports_cave_image_realism_rules,
)
from ui_option_ordering import alphabetize_options


class _LazyModuleProxy:
    def __init__(self, module_name):
        self._module_name = module_name
        self._module = None

    def __getattr__(self, attribute):
        if self._module is None:
            self._module = importlib.import_module(self._module_name)
        return getattr(self._module, attribute)


ads_final_review = _LazyModuleProxy("ads_final_review")
ads_image_workflow = _LazyModuleProxy("ads_image_workflow")
image_factory = _LazyModuleProxy("image_factory")


CATEGORY_OPTIONS = list(alphabetize_options([
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
]))

COUNTRY_OPTIONS = list(alphabetize_options([
    "Select country",
    "Australia",
    "USA",
    "UK",
    "Canada",
    "New Zealand",
]))

CAMPAIGN_TYPE_OPTIONS = list(alphabetize_options([
    "Select campaign type",
    "Carousel",
    "Instant Experience",
    "Single Image / Video",
]))

CAMPAIGN_MOMENT_TYPE_OPTIONS = list(alphabetize_options([
    "Gifting Occasion",
    "Sporting Event",
    "Sale Period",
    "Product Drop",
    "Seasonal Moment",
    "Other",
]))

CAMPAIGN_MOMENT_MARKET_OPTIONS = list(alphabetize_options([
    "Use selected ad country",
    "Australia",
    "USA",
    "UK",
    "Canada",
    "New Zealand",
    "Global",
], first=("Use selected ad country",)))

CAMPAIGN_MOMENT_STRENGTH_OPTIONS = [
    "Subtle",
    "Moderate",
    "Campaign-led",
]

CAMPAIGN_MOMENT_SESSION_KEYS = (
    "ads_campaign_moment_type",
    "ads_campaign_moment_name",
    "ads_campaign_moment_market",
    "ads_campaign_moment_date",
    "ads_campaign_moment_promotion",
    "ads_campaign_moment_strength",
    "ads_campaign_moment_include_images",
)

EDITION_OPS_SNAPSHOT_PATH = Path(__file__).resolve().parent / "output" / "_cache" / "edition_ops_products_snapshot.json"
EDITION_OPS_ROWS_SESSION_KEY = "edition_ops_rows"

CAROUSEL_CARD_MAX_CHARACTERS = 17
CAROUSEL_CARD_COUNT = 5
META_WINNER_COPY_BLOCK_VERSION = "SPORTS CAVE META WINNER COPY UPGRADE V1"
ADS_PROMPT_CONTRACT_VERSION = "ADS FULL VISUAL PROMPTS V5"
ADS_RESULT_STATE_KEY = "ads_generated_result"
ADS_IMAGE_STATE_KEY = "ads_generated_image_workflow"
ADS_REVIEW_STATE_KEY = "ads_final_review_workflow"
ADS_INSTANT_EXPERIENCE_COPY_CONTRACT_VERSION = "ADS INSTANT EXPERIENCE COPY V7"
ADS_INSTANT_EXPERIENCE_ROUTE_CONTRACT_VERSION = "ADS INSTANT EXPERIENCE ROUTES V1"
ADS_INSTANT_EXPERIENCE_STANDARD_CONTRACT_VERSION = "ADS INSTANT EXPERIENCE STANDARD V8 PREMIUM ROOM V4"
INSTANT_EXPERIENCE_ON_IMAGE_HEADLINE_MAX_WORDS = 6
INSTANT_EXPERIENCE_ON_IMAGE_HEADLINE_MAX_CHARACTERS = 28
INSTANT_EXPERIENCE_ON_IMAGE_SUPPORTING_MAX_WORDS = 12
INSTANT_EXPERIENCE_ON_IMAGE_SUPPORTING_MAX_CHARACTERS = 70
INSTANT_EXPERIENCE_ON_IMAGE_CTA_MAX_WORDS = 4
INSTANT_EXPERIENCE_ON_IMAGE_CTA_MAX_CHARACTERS = 24
INSTANT_EXPERIENCE_APPROVED_ON_IMAGE_CTAS = (
    "CLAIM YOUR EDITION",
    "SECURE YOUR EDITION",
    "CLAIM THIS EDITION",
    "SECURE THIS EDITION",
)
ADS_COPY_FILENAME = "Ad Copy.txt"
CAROUSEL_COPY_FILENAME = "Carousel Copy.csv"
ADS_DIRECTORY_CACHE_SECONDS = 3 * 60
ADS_PRODUCT_IMAGES_FOLDER = "04_OUTPUT/product-images"
PRODUCT_URL_ERROR = "Enter a valid product page URL before submitting."
NO_EDITION_OPS_PRODUCT_URL_MESSAGE = (
    "No product URL is saved in Edition Ops. Add it there or enter it manually."
)
ADS_PRODUCT_NAME_KEY = "ads_product_name"
ADS_PRODUCT_SELECTOR_KEY = "ads_product_selector"
ADS_PRODUCT_URL_KEY = "ads_product_url"
ADS_PRODUCT_URL_AUTOFILL_PRODUCT_KEY = "ads_product_url_autofill_product_key"
ADS_PRODUCT_URL_AUTOFILL_SELECTION_KEY = "ads_product_url_autofill_selection"
ADS_PRODUCT_URL_PREVIOUS_PRODUCT_KEY = "ads_product_url_previous_product_key"
ADS_PRODUCT_URL_LAST_AUTO_VALUE_KEY = "ads_product_url_last_auto_value"
ADS_PRODUCT_URL_MANUALLY_EDITED_KEY = "ads_product_url_manually_edited"
ADS_PRODUCT_URL_INITIALIZED_KEY = "ads_product_url_initialized"
ADS_IE_RECENT_FINGERPRINTS_KEY = "ads_instant_experience_recent_fingerprints"

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
BASEBALL_INSTANT_EXPERIENCE_COVER_LINES = (
    "LIMITED TO 100 WORLDWIDE",
    "Once it sells out, it’s gone.",
    "CLAIM YOUR EDITION",
)
COLLECTOR_PROOF_COVER_LINES = (
    "ONLY 100 WILL EVER EXIST",
    "COLLECTOR CERTIFICATE INCLUDED",
    "OWN THIS EDITION",
)
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

INSTANT_EXPERIENCE_COPY_FIELDS = (
    ("primary_text", "Description"),
    ("headline", "Headline"),
    ("cta", "CTA"),
)
INSTANT_EXPERIENCE_DESCRIPTION_VARIANTS = (
    {
        "key": "legacy_standard",
        "label": "Description 1 — Legacy Standard",
        "style": "Legacy Standard",
    },
    {
        "key": "framed_greatness",
        "label": "Description 2 — Framed Greatness",
        "style": "Framed Greatness",
    },
    {
        "key": "choose_a_side",
        "label": "Description 3 — Choose a Side",
        "style": "Choose a Side",
    },
)
INSTANT_EXPERIENCE_COPY_VARIATION_COUNT = len(INSTANT_EXPERIENCE_DESCRIPTION_VARIANTS)
INSTANT_EXPERIENCE_PREVIEW_DISPLAY_WIDTH = 300
INSTANT_EXPERIENCE_COPY_CSV_SCHEMA_VERSION = "2"
INSTANT_EXPERIENCE_COPY_CSV_CAMPAIGN_TYPE = "instant_experience"
INSTANT_EXPERIENCE_COPY_CSV_STANDARD_OUTPUT_MODE = "standard_three_descriptions"
INSTANT_EXPERIENCE_COPY_CSV_HEADERS = (
    "schema_version",
    "campaign_type",
    "output_mode",
    "route_key",
    "route_label",
    "variation",
    "description_key",
    "description_label",
    "primary_text",
    "headline",
    "cta",
)
INSTANT_EXPERIENCE_APPROVED_CREATIVE_CTAS = (
    "Claim Your Edition",
    "Secure Your Edition",
    "Own This Edition",
)
INSTANT_EXPERIENCE_PRIMARY_TEXT_CTA_ENDINGS = {
    "Claim Your Edition": "Claim your edition.",
    "Secure Your Edition": "Secure your edition.",
    "Own This Edition": "Own this edition.",
}
INSTANT_EXPERIENCE_PRIMARY_IMAGE_CTAS = {
    "premium_scarcity_right": "Claim Your Edition",
    "premium_scarcity_front": "Claim Your Edition",
    "premium_scarcity_left": "Claim Your Edition",
    "nostalgia": "Secure Your Edition",
    "ownership": "Claim Your Edition",
    "scarcity": "Own This Edition",
}
INSTANT_EXPERIENCE_COPY_CSV_SUPPORT_INSTRUCTION = (
    "If a Sports Cave Instant Experience copy CSV template is attached in this conversation, "
    "transfer the matching Description Copy into the primary_text column and complete the "
    "headline and cta columns. Match by route_key, variation and description_key. Preserve "
    "all headers, schema fields, row order and identity "
    "columns exactly. Return the completed CSV as a downloadable .csv file. Do not place "
    "image-prompt wording inside the copy columns."
)

CAROUSEL_COPY_VARIATION_COUNT = 5
CAROUSEL_COPY_CSV_SCHEMA_VERSION = "1"
CAROUSEL_COPY_CSV_CAMPAIGN_TYPE = "carousel"
CAROUSEL_COPY_CSV_HEADERS = (
    "schema_version",
    "campaign_type",
    "row_type",
    "position",
    "slot_id",
    "image_filename",
    "headline",
    "description",
    "primary_text",
    "destination_url",
    "cta",
    "setup_notes",
)
CAROUSEL_COPY_ROW_TYPES = (
    "headline",
    "description",
    "primary_text",
    "card",
    "setup_notes",
)
CAROUSEL_CARD_FIELDS = (
    "headline",
    "description",
    "destination_url",
    "cta",
    "setup_notes",
)
CAROUSEL_COPY_CSV_SUPPORT_INSTRUCTION = (
    "If a Sports Cave Carousel CSV template is attached in this conversation, complete all five "
    "headline rows, all five description rows, all five primary_text rows, the five ordered card "
    "rows and the final setup_notes row. Match every card by position and slot_id. Preserve all "
    "headers, schema fields, row types, row order and slot identities exactly. Return the completed "
    "CSV as a downloadable .csv file. Do not combine multiple cards into one cell."
)

SPORTS_CAVE_ADS_FACTUAL_WORDING_GATE_V1 = """SPORTS_CAVE_ADS_FACTUAL_WORDING_GATE_V1

FACTUAL AND CONTEXTUAL WORDING CHECK — MANDATORY

Before finalizing any customer-visible Primary Text, Headline, Description, CTA, copy variation, Carousel card, Instant Experience cover, Single Image / Video ad, setup wording, image-generation prompt or on-image wording, read the complete product title and all supplied artwork, sport/category, market, campaign, route, offer, scarcity and verified product variables. Identify what the artwork genuinely represents: an athlete, team, teammates, opponents, event, era, achievement, vehicle, record, emotional theme or collector subject.

Validate every line against that exact context and against every other line. A sporting claim may be used only when supported by the complete product title, user-supplied verified facts, authoritative product or catalogue data, clearly readable artwork wording, or authoritative external verification when browsing is available. Never guess a fact from an image, and never treat an ambiguous title as proof.

Two named people or a title containing "vs" does not by itself prove rivalry, opposition, hostility or a historical head-to-head event. The subjects may be teammates, contemporaries, comparisons or opposing subjects. Rivalry, enemies, battle, duel, went head-to-head or equivalent relationship wording is permitted only when that relationship is explicitly supported by verified facts. Teammate context must never be contradicted by invented rivalry or hostility.

Never invent or imply a victory, championship, record, historic moment, venue, date, rivalry status, hostile relationship, greatest-ever status or achievement. Do not use relive, remember, historic, legacy or similar past-event language unless the product genuinely represents a confirmed past moment or era. Exact user-provided wording remains authoritative only when it is factually supported.

If a line is uncertain, misleading, overly specific or inconsistent, rewrite only that line with a simpler emotional phrase that remains specific to the product, sport and selected creative route. Safe territory may include pressure, anticipation, identity, pride, loyalty, atmosphere, race day, game day, collector ownership, display and the feeling of being a fan, but it must still be tailored to the actual product. Do not fall back to generic retail language such as "Elevate your space", "Ultimate tribute", "Must-have" or "Perfect addition". Do not hardcode one replacement phrase or universal CTA; resolve truthful wording dynamically for each ad.

After validation, propagate the exact approved wording consistently everywhere it appears, including copy tables, setup copy where relevant and the corresponding image-generation prompt. The exact Headline, CTA and supporting wording approved for an image must match the wording written inside that image prompt. Perform this check silently when generating the ad output. Do not output warnings, research notes, rejected alternatives or internal reasoning. In review requests, apply the same factual check inside the existing review fields without adding or removing review sections."""

INSTANT_EXPERIENCE_COPY_GROUPS = (
    ("primary_text", "PRIMARY TEXT", "Primary Text", "Primary text option {index}"),
    ("headlines", "HEADLINE", "Headline", "Headline option {index}"),
    ("call_to_action", "CALL TO ACTION", "Call to Action", "Shop Now"),
)
INSTANT_EXPERIENCE_COPY_OPTION_COUNT = 5

IE_MODE_SMART = "Smart 3-Pack — Recommended"
IE_MODE_SELECTED = "One Selected Route"
IE_MODE_CLASSIC = "Classic Collector — Current Control"
IE_CREATIVE_OUTPUT_MODES = (
    IE_MODE_SMART,
    IE_MODE_SELECTED,
    IE_MODE_CLASSIC,
)
IE_AUDIENCE_MINDSETS = (
    "Auto-match",
    "Lifelong fan",
    "Active fan",
    "Collector",
    "Gift buyer",
    "Wall upgrader",
    "Multi-buy shopper",
    "Warm product viewer",
    "Hot retargeting visitor",
)
IE_PRIMARY_CREATIVE_ANGLES = (
    "Auto-match",
    "Moment / Memory",
    "Fan Identity",
    "Ownership / Display",
    "Legacy / Achievement",
    "Milestone",
    "Rivalry / Allegiance",
    "Collector / Rarity",
    "Gift",
    "Build a Collection",
    "Offer / Sale",
)
IE_URGENCY_PLACEMENTS = (
    "Auto-match route",
    "None in feed creative",
    "Meta description only",
    "Soft final line in primary text",
    "Strong cover and primary text",
)
IE_DESTINATION_SCOPES = (
    "Featured product page + catalogue",
    "Curated collection page + catalogue",
)
IE_VISUAL_DIRECTIONS = (
    "Auto — Match the Creative Route",
    "Manual Overrides",
)
IE_FIXED_BUTTON_CTA_MODES = (
    "Hold fixed-button CTA constant across all routes",
    "Auto-match fixed-button CTA",
)
IE_ROUTE_IDS = ("FEEL", "BELONG", "ACT", "BUILD")
IE_SMART_ROUTE_KEYS = ("route_a", "route_b", "route_c")
IE_ROUTE_LABELS = {
    "FEEL": "FEEL — Moment / Memory",
    "BELONG": "BELONG — Fan Identity / Ownership",
    "ACT": "ACT — Collector Scarcity / Current Conversion Control",
    "BUILD": "BUILD — Build a Collection / Offer",
}
IE_SMART_OPTION_HEADINGS = {
    "route_a": "OPTION A",
    "route_b": "OPTION B",
    "route_c": "OPTION C",
}
IE_DEFAULT_SMART_ROUTES = {
    "route_a": "FEEL",
    "route_b": "BELONG",
    "route_c": "ACT",
}
IE_SCARCITY_TERMS = (
    "limited",
    "only",
    "gone",
    "miss out",
    "claim",
    "secure",
    "rare",
    "last chance",
    "selling fast",
    "countdown",
)
IE_AUTO_FRESH_MATCH = "Auto — Choose a Fresh Match"
IE_ADVANCED_VISUAL_OPTION_SETS = {
    "room_type": (
        IE_AUTO_FRESH_MATCH,
        "Premium Living Room",
        "Collector Study",
        "Home Office",
        "Media Room",
        "Restrained Home Bar",
        "Garage Lounge",
        "Foyer / Entry Gallery",
        "Library",
        "Sports Room",
    ),
    "wall_colour_family": (
        IE_AUTO_FRESH_MATCH,
        "Warm Off-White",
        "Deep Charcoal",
        "Graphite",
        "Soft Greige",
        "Walnut Brown",
        "Deep Navy",
        "Muted Olive",
        "Stone Beige",
    ),
    "wall_material": (
        IE_AUTO_FRESH_MATCH,
        "Smooth Painted Plaster",
        "Mineral Plaster",
        "Limewash",
        "Microcement",
        "Restrained Brick",
        "Pale Stone",
        "Dark Oak Panels",
        "Walnut Slats",
        "Charcoal Masonry",
    ),
    "camera_family": (
        IE_AUTO_FRESH_MATCH,
        "Near-Front",
        "Mild Left Three-Quarter",
        "Mild Right Three-Quarter",
        "Asymmetrical Editorial",
        "Straight-On Control",
        "Corner Reveal",
    ),
    "camera_height": (
        IE_AUTO_FRESH_MATCH,
        "Eye Level",
        "Slightly Below Eye Level",
        "Chest Height",
        "Slightly Elevated",
    ),
    "shot_distance": (
        IE_AUTO_FRESH_MATCH,
        "Close Hero 65–75%",
        "Product-Dominant 60–70%",
        "Medium Room Context 50–60%",
        "Editorial Detail 65–80%",
    ),
    "lens_character": (
        IE_AUTO_FRESH_MATCH,
        "45–55mm Natural",
        "65–85mm Natural Portrait",
        "50mm Editorial",
        "70mm Compressed Interior",
    ),
    "lighting_direction": (
        IE_AUTO_FRESH_MATCH,
        "Warm Side Light",
        "Soft Window Light",
        "Dusk Practical Light",
        "Directional Gallery Light",
        "Diffuse Daylight",
    ),
    "time_of_day": (
        IE_AUTO_FRESH_MATCH,
        "Morning",
        "Late Afternoon",
        "Dusk",
        "Overcast Day",
        "Evening",
    ),
    "cover_layout": (
        IE_AUTO_FRESH_MATCH,
        "Full-Bleed Editorial",
        "Editorial Caption Region",
        "Asymmetrical Room Negative Space",
        "Classic Scarcity Panel",
        "Collection Wall",
    ),
    "overlay_text_treatment": (
        IE_AUTO_FRESH_MATCH,
        "Short Editorial Hook",
        "Identity Hook + CTA",
        "Classic Three-Line Scarcity",
        "Minimal Caption",
        "Collection Offer",
    ),
}

INSTANT_EXPERIENCE_ROUTE_CONFIGS = {
    "FEEL": {
        "name": "FEEL",
        "angle": "Moment / Memory",
        "psychological_job": "Make the correct fan remember why the athlete, era, race, match, achievement or moment mattered.",
        "funnel": "Cold to warm audiences where emotional recall and product-specific memory matter more than urgency.",
        "primary_text_structure": "Lead with a sensory memory, defining feeling or verified product-specific moment. No generic product-description opening.",
        "headline_style": "Memory-led, editorial and product-specific.",
        "meta_description_role": "Supporting context only; do not hide essential commercial information here unless the user selected Meta description only.",
        "proof_intensity": "No proof checklist.",
        "scarcity_intensity": "No scarcity in feed creative when urgency is disabled.",
        "on_image_message_type": "One short product-specific hook and at most one supporting line.",
        "creative_cta_family": INSTANT_EXPERIENCE_APPROVED_CREATIVE_CTAS,
        "fixed_button_cta": "Shop Now",
        "cover_composition": "Full-bleed or near-full-bleed editorial lifestyle composition with no hard black scarcity panel.",
        "panel_treatment": "No large hard black scarcity panel.",
        "product_prominence": "Frame occupies approximately 65–75% of usable width.",
        "room_family": "Intimate office, reading room or lived-in residential wall.",
        "wall_family": "Walnut, mineral plaster, limewash or warm neutral architectural finish.",
        "camera_family": "Eye-level or slightly below eye-level; near-front or very mild three-quarter perspective.",
        "lens_family": "65–85mm natural lens character.",
        "lighting_family": "Intimate morning or late-afternoon natural light.",
        "destination": "Featured product page preferred.",
        "required_data": "Verified product identity and completed/past event before using relive language.",
        "prohibited_language": "Greatness doesn’t fade; proof checklist; discount language; hard-sell language.",
    },
    "BELONG": {
        "name": "BELONG",
        "angle": "Fan Identity / Ownership",
        "psychological_job": "Make the fan feel that owning the artwork says something real about who they are and what the subject means to them.",
        "funnel": "Cold, warm and retargeting audiences where identity, wall ownership and display desire matter.",
        "primary_text_structure": "Lead with belonging, recognition or shared fan identity, then show the product in the customer’s life.",
        "headline_style": "Identity-led, direct and human.",
        "meta_description_role": "A small supporting proof or display cue.",
        "proof_intensity": "No proof checklist; use no more than one verified proof or scarcity cue.",
        "scarcity_intensity": "Restrained unless strong urgency is deliberately selected.",
        "on_image_message_type": "Identity-led hook, one short support line and one restrained creative CTA.",
        "creative_cta_family": INSTANT_EXPERIENCE_APPROVED_CREATIVE_CTAS,
        "fixed_button_cta": "Shop Now",
        "cover_composition": "Wider real-room context with asymmetrical editorial composition and architectural negative space.",
        "panel_treatment": "Avoid the current centered black scarcity panel.",
        "product_prominence": "Frame occupies approximately 50–60% of usable width.",
        "room_family": "Den, home office, sports room, restrained home bar or collection wall.",
        "wall_family": "Contemporary plaster, dark timber, restrained brick or material contrast.",
        "camera_family": "Chest-height restrained left or right three-quarter view.",
        "lens_family": "45–55mm natural lens character.",
        "lighting_family": "Dusk daylight plus restrained practical lighting is allowed.",
        "destination": "Featured product page preferred.",
        "required_data": "Verified product identity and audience mindset that supports ownership or fan identity.",
        "prohibited_language": "Aggressive gone-forever language unless explicitly selected; interior-design ad copy.",
    },
    "ACT": {
        "name": "ACT",
        "angle": "Collector Scarcity / Current Conversion Control",
        "psychological_job": "Convert established desire through verified edition scarcity and collector proof.",
        "funnel": "Warm product viewers, hot retargeting visitors and current conversion-control testing.",
        "primary_text_structure": "Classic Sports Cave collector opener, product-specific paragraph, approved proof and scarcity close.",
        "headline_style": "Collector-conversion headline tied to the exact product.",
        "meta_description_role": "Supporting scarcity or proof line.",
        "proof_intensity": "Approved proof checklist only.",
        "scarcity_intensity": "Strong verified scarcity.",
        "on_image_message_type": "Exact three-line bottom scarcity strip.",
        "creative_cta_family": INSTANT_EXPERIENCE_APPROVED_CREATIVE_CTAS,
        "fixed_button_cta": "Shop Now",
        "cover_composition": "Full-width upper lifestyle/product image region approximately 77-79% of the square canvas, with a fixed opaque matte-black footer across the bottom approximately 21-23%.",
        "panel_treatment": "Deep matte-black bottom strip with a thin restrained metallic-gold divider across its top edge.",
        "product_prominence": "Frame occupies approximately 74-82% of usable canvas width inside the upper image region.",
        "room_family": "Current premium collector-room control.",
        "wall_family": "Restrained residential palette from the current control.",
        "camera_family": "Natural interior-photography camera position.",
        "lens_family": "Natural interior lens.",
        "lighting_family": "Soft natural light plus restrained warm practical lighting.",
        "destination": "Featured product page plus catalogue.",
        "required_data": "Approved edition claim path and product URL.",
        "prohibited_language": "Only X remaining unless current timestamped inventory data exists.",
    },
    "BUILD": {
        "name": "BUILD",
        "angle": "Build a Collection / Offer",
        "psychological_job": "Make customers want to choose more than one relevant edition and build a collection.",
        "funnel": "Multi-buy, offer-aware and collection-browsing audiences only.",
        "primary_text_structure": "Lead with collection intent and the exact verified offer when supplied.",
        "headline_style": "Collection-building headline, not single-product scarcity.",
        "meta_description_role": "Exact offer or collection support when verified.",
        "proof_intensity": "No invented product count, discount or catalogue breadth.",
        "scarcity_intensity": "Offer-led only when exact offer is entered and verified.",
        "on_image_message_type": "Collection or offer message, never fake multi-product artwork.",
        "creative_cta_family": INSTANT_EXPERIENCE_APPROVED_CREATIVE_CTAS,
        "fixed_button_cta": "Shop Now",
        "cover_composition": "Collection-wall or collection-browsing cover only when exact reference assets are supplied.",
        "panel_treatment": "No fake scarcity panel; offer treatment only when exact offer is supplied.",
        "product_prominence": "The featured product remains exact; multi-product promises require exact product references.",
        "room_family": "Collection wall, study or premium gallery area.",
        "wall_family": "Structured gallery wall with believable material finish.",
        "camera_family": "Editorial collection view without making products small.",
        "lens_family": "50mm editorial or 70mm compressed interior.",
        "lighting_family": "Controlled gallery or soft residential light.",
        "destination": "Curated collection page plus catalogue only.",
        "required_data": "Collection name, collection URL, exact product-set name, at least four eligible products, and exact offer for offer routes.",
        "prohibited_language": "Broad collection URL, invented products, lookalike artwork or multi-product wall without references.",
    },
}

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


def _normalise_product_match_value(value):
    return (
        _normalise_option_label(value)
        .translate(
            str.maketrans(
                {
                    "\u2018": "'",
                    "\u2019": "'",
                    "\u02bc": "'",
                    "\u2010": "-",
                    "\u2011": "-",
                    "\u2012": "-",
                    "\u2013": "-",
                    "\u2014": "-",
                }
            )
        )
        .casefold()
    )


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


def _edition_ops_product_page_url_from_row(row):
    if not isinstance(row, dict):
        return ""
    for field in (
        "online_store_url",
        "Open live product",
        "live_product_url",
        "product_page_url",
        "product_url",
        "storefront_url",
        "url",
    ):
        clean_url = _clean_product_url(row.get(field))
        if clean_url and is_valid_product_page_url(clean_url):
            return clean_url
    return ""


def _positive_int_or_none(value):
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _edition_ops_product_collections_from_row(row):
    if not isinstance(row, dict):
        return []
    raw = row.get("collections") or row.get("Collections") or row.get("collection_titles")
    if isinstance(raw, str):
        values = re.split(r"[,;|]", raw)
    elif isinstance(raw, (list, tuple, set)):
        values = list(raw)
    else:
        values = []
    return [
        _normalise_option_label(
            value.get("title") if isinstance(value, dict) else value
        )
        for value in values
        if _normalise_option_label(value.get("title") if isinstance(value, dict) else value)
    ][:12]


def instant_experience_product_metadata_from_selection(selection, *, category=""):
    row = dict(selection.get("row") or {}) if isinstance(selection, dict) else {}
    edition_limit = _positive_int_or_none(
        row.get("edition_limit")
        or row.get("edition_total")
        or row.get("Edition limit")
        or row.get("Edition total")
    )
    edition_limit_source = _normalise_option_label(
        row.get("edition_limit_source")
        or row.get("edition_total_source")
        or ("Edition Ops product ledger" if edition_limit else "")
    )
    return {
        "product_sport": _normalise_option_label(category),
        "product_type": _normalise_option_label(row.get("product_type") or row.get("Product type")),
        "collections": _edition_ops_product_collections_from_row(row),
        "edition_limit": edition_limit,
        "edition_limit_source": edition_limit_source,
    }


def _edition_ops_product_option_label(row, duplicate_titles=None):
    product_name = _product_name_from_edition_ops_row(row)
    handle = _edition_ops_product_handle_from_row(row)
    duplicate_titles = duplicate_titles or set()
    if product_name and handle and product_name.casefold() in duplicate_titles:
        return f"{product_name} ({handle})"
    return product_name or handle


def _edition_ops_duplicate_title_keys(rows):
    title_counts = {}
    for row in rows or ():
        product_name = _product_name_from_edition_ops_row(row)
        if product_name:
            key = product_name.casefold()
            title_counts[key] = title_counts.get(key, 0) + 1
    return {key for key, count in title_counts.items() if count > 1}


def _edition_ops_product_record_key(row):
    if not isinstance(row, dict):
        return ""
    for value in (
        _edition_ops_product_id_from_row(row),
        row.get("shopify_product_gid"),
        row.get("product_gid"),
        _edition_ops_product_handle_from_row(row),
    ):
        clean = _normalise_option_label(value)
        if clean:
            return clean
    return ""


def _edition_ops_product_explicit_id_from_row(row):
    if not isinstance(row, dict):
        return ""
    return _normalise_option_label(
        row.get("product_id")
        or row.get("Product ID")
        or row.get("shopify_product_id")
        or row.get("shopify_product_gid")
        or row.get("product_gid")
        or row.get("id")
    )


def _edition_ops_product_selector_identity(row):
    product_id = _edition_ops_product_explicit_id_from_row(row)
    if product_id:
        return f"id::{product_id}"
    record_key = _edition_ops_product_record_key(row)
    if record_key:
        return f"key::{record_key}"
    handle = _edition_ops_product_handle_from_row(row)
    if handle:
        return f"handle::{handle}"
    product_name = _product_name_from_edition_ops_row(row)
    if product_name:
        return f"label::{_normalise_product_match_value(product_name)}"
    return ""


@st.cache_data(show_spinner=False)
def build_ads_product_selector_records(rows):
    rows = list(rows or ())
    duplicate_titles = _edition_ops_duplicate_title_keys(rows)
    records = []
    seen_identities = set()
    for row in rows:
        identity = _edition_ops_product_selector_identity(row)
        label = _edition_ops_product_option_label(row, duplicate_titles)
        if not identity or not label or identity in seen_identities:
            continue
        records.append(
            {
                "identity": identity,
                "label": label,
                "row": row,
                "record_key": _edition_ops_product_record_key(row),
                "product_id": _edition_ops_product_id_from_row(row),
                "product_url": _edition_ops_product_page_url_from_row(row),
            }
        )
        seen_identities.add(identity)
    return records


def resolve_ads_product_selector_value(selector_value, *, rows=None, records=None):
    selected_value = _normalise_option_label(selector_value)
    records = list(
        build_ads_product_selector_records(rows)
        if records is None
        else records
    )
    for record in records:
        if selected_value == record["identity"]:
            return {
                "selected_label": record["label"],
                "selector_identity": record["identity"],
                "row": record["row"],
                "record_key": record["record_key"],
                "product_id": record["product_id"],
                "product_url": record["product_url"],
            }

    selection = resolve_edition_ops_product_selection(selected_value, rows=rows)
    if selection.get("row"):
        selection["selector_identity"] = _edition_ops_product_selector_identity(
            selection["row"]
        )
    else:
        selection["selector_identity"] = (
            f"manual::{_normalise_product_match_value(selected_value)}"
            if selected_value
            else ""
        )
    return selection


def resolve_edition_ops_product_row(
    product_name,
    *,
    rows=None,
    product_id="",
    record_key="",
    handle="",
):
    selected = _normalise_option_label(product_name)
    if not selected:
        return None
    rows = list(load_edition_ops_product_rows() if rows is None else rows)
    duplicate_titles = _edition_ops_duplicate_title_keys(rows)
    selected_key = _normalise_product_match_value(selected)

    stable_lookups = (
        (product_id, _edition_ops_product_id_from_row),
        (record_key, _edition_ops_product_record_key),
        (handle, _edition_ops_product_handle_from_row),
    )
    for identity, getter in stable_lookups:
        identity_key = _normalise_product_match_value(identity)
        if not identity_key:
            continue
        for row in rows:
            if identity_key == _normalise_product_match_value(getter(row)):
                return row

    for getter in (
        _edition_ops_product_id_from_row,
        _edition_ops_product_record_key,
        _edition_ops_product_handle_from_row,
    ):
        matches = [
            row
            for row in rows
            if selected_key == _normalise_product_match_value(getter(row))
        ]
        if len(matches) == 1:
            return matches[0]

    option_matches = [
        row
        for row in rows
        if selected_key
        == _normalise_product_match_value(
            _edition_ops_product_option_label(row, duplicate_titles)
        )
    ]
    if len(option_matches) == 1:
        return option_matches[0]

    title_matches = [
        row
        for row in rows
        if selected_key
        == _normalise_product_match_value(_product_name_from_edition_ops_row(row))
    ]
    if len(title_matches) == 1:
        return title_matches[0]
    return None


def resolve_edition_ops_product_selection(
    product_name,
    *,
    rows=None,
    product_id="",
    record_key="",
    handle="",
):
    selected = _normalise_option_label(product_name)
    row = resolve_edition_ops_product_row(
        selected,
        rows=rows,
        product_id=product_id,
        record_key=record_key,
        handle=handle,
    )
    if not row:
        manual_key = f"manual::{selected.casefold()}" if selected else ""
        return {
            "selected_label": selected,
            "row": None,
            "record_key": manual_key,
            "product_id": "",
            "product_url": "",
        }
    record_key = _edition_ops_product_record_key(row)
    return {
        "selected_label": selected,
        "row": row,
        "record_key": record_key,
        "product_id": _edition_ops_product_id_from_row(row),
        "product_url": _edition_ops_product_page_url_from_row(row),
    }


@st.cache_data(show_spinner=False)
def _read_edition_ops_snapshot_rows(snapshot_path, modified_ns, size):
    del modified_ns, size
    try:
        payload = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return []
    rows = payload.get("rows") if isinstance(payload, dict) else []
    return rows if isinstance(rows, list) else []


def _edition_ops_rows_from_local_snapshot(snapshot_path=EDITION_OPS_SNAPSHOT_PATH):
    snapshot_path = Path(snapshot_path)
    try:
        snapshot_stat = snapshot_path.stat()
    except OSError:
        return []
    return _read_edition_ops_snapshot_rows(
        str(snapshot_path),
        snapshot_stat.st_mtime_ns,
        snapshot_stat.st_size,
    )


@st.cache_data(show_spinner=False)
def _merge_edition_ops_product_rows(live_rows, session_rows, snapshot_rows):
    rows = [*list(live_rows or ()), *list(session_rows or ()), *list(snapshot_rows or ())]
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


def load_edition_ops_product_rows(
    snapshot_path=EDITION_OPS_SNAPSHOT_PATH,
    *,
    live_loader=None,
):
    live_rows = []
    snapshot_path = Path(snapshot_path)
    should_load_live = live_loader is not None or snapshot_path == EDITION_OPS_SNAPSHOT_PATH
    if should_load_live:
        loader = live_loader or load_live_edition_product_rows
        try:
            loaded_rows = loader()
        except Exception:
            loaded_rows = []
        if isinstance(loaded_rows, list):
            live_rows = loaded_rows

    session_rows = st.session_state.get(EDITION_OPS_ROWS_SESSION_KEY, [])
    if not isinstance(session_rows, list):
        session_rows = []
    return _merge_edition_ops_product_rows(
        live_rows,
        session_rows,
        _edition_ops_rows_from_local_snapshot(snapshot_path),
    )


def load_edition_ops_product_name_options(
    snapshot_path=EDITION_OPS_SNAPSHOT_PATH,
    *,
    live_loader=None,
    rows=None,
):
    unique_rows = list(rows) if rows is not None else load_edition_ops_product_rows(
        snapshot_path,
        live_loader=live_loader,
    )

    options = []
    seen = set()
    duplicate_titles = _edition_ops_duplicate_title_keys(unique_rows)

    for row in unique_rows:
        option_label = _edition_ops_product_option_label(row, duplicate_titles)
        key = option_label.casefold()
        if option_label and key not in seen:
            options.append(option_label)
            seen.add(key)
    return options


def resolve_edition_ops_product_id(product_name, *, rows=None):
    return resolve_edition_ops_product_selection(product_name, rows=rows).get("product_id") or ""


def _ads_result_matches_selection(result, selection, product_name):
    if not isinstance(result, dict):
        return False
    result_product_id = _normalise_option_label(result.get("product_id"))
    selection_product_id = _normalise_option_label(selection.get("product_id"))
    if result_product_id and selection_product_id:
        return result_product_id.casefold() == selection_product_id.casefold()
    return _clean_product_name(result.get("product_name")).casefold() == _clean_product_name(product_name).casefold()


def _synchronise_ads_product_url_state(selection):
    selected_label = selection.get("selected_label") or ""
    selected_identity = selection.get("selector_identity") or ""
    selected_url = selection.get("product_url") or ""
    current_identity = str(
        st.session_state.get(ADS_PRODUCT_URL_AUTOFILL_PRODUCT_KEY) or ""
    )
    selection_changed = selected_identity != current_identity

    if not selected_label:
        st.session_state[ADS_PRODUCT_URL_PREVIOUS_PRODUCT_KEY] = current_identity
        st.session_state[ADS_PRODUCT_URL_KEY] = ""
        st.session_state[ADS_PRODUCT_URL_AUTOFILL_PRODUCT_KEY] = ""
        st.session_state[ADS_PRODUCT_URL_AUTOFILL_SELECTION_KEY] = ""
        st.session_state[ADS_PRODUCT_URL_LAST_AUTO_VALUE_KEY] = ""
        st.session_state[ADS_PRODUCT_URL_MANUALLY_EDITED_KEY] = False
        st.session_state[ADS_PRODUCT_URL_INITIALIZED_KEY] = False
        return

    initialized = bool(st.session_state.get(ADS_PRODUCT_URL_INITIALIZED_KEY))
    manually_edited = bool(
        st.session_state.get(ADS_PRODUCT_URL_MANUALLY_EDITED_KEY)
    )
    if selection_changed:
        st.session_state[ADS_PRODUCT_URL_PREVIOUS_PRODUCT_KEY] = current_identity
        st.session_state[ADS_PRODUCT_URL_AUTOFILL_PRODUCT_KEY] = selected_identity
        st.session_state[ADS_PRODUCT_URL_AUTOFILL_SELECTION_KEY] = selected_label
        st.session_state[ADS_PRODUCT_URL_KEY] = selected_url
        st.session_state[ADS_PRODUCT_URL_LAST_AUTO_VALUE_KEY] = selected_url
        st.session_state[ADS_PRODUCT_URL_MANUALLY_EDITED_KEY] = False
        st.session_state[ADS_PRODUCT_URL_INITIALIZED_KEY] = True
        return

    if not initialized or not manually_edited:
        st.session_state[ADS_PRODUCT_URL_KEY] = selected_url
        st.session_state[ADS_PRODUCT_URL_LAST_AUTO_VALUE_KEY] = selected_url
        st.session_state[ADS_PRODUCT_URL_MANUALLY_EDITED_KEY] = False
        st.session_state[ADS_PRODUCT_URL_INITIALIZED_KEY] = True


def prepare_ads_product_url_state(
    product_name,
    *,
    result=None,
    rows=None,
    selection=None,
):
    del result
    if selection is None:
        selection = resolve_edition_ops_product_selection(product_name, rows=rows)
        selection["selector_identity"] = (
            _edition_ops_product_selector_identity(selection.get("row"))
            if selection.get("row")
            else (
                f"manual::{_normalise_product_match_value(product_name)}"
                if _normalise_option_label(product_name)
                else ""
            )
        )
    _synchronise_ads_product_url_state(selection)

    selected_label = selection.get("selected_label") or ""
    selected_url = selection.get("product_url") or ""
    message = NO_EDITION_OPS_PRODUCT_URL_MESSAGE if selected_label and not selected_url else ""
    return {**selection, "message": message}


def _on_ads_product_url_changed():
    if st.session_state.get(ADS_PRODUCT_URL_AUTOFILL_PRODUCT_KEY):
        st.session_state[ADS_PRODUCT_URL_MANUALLY_EDITED_KEY] = True
        st.session_state[ADS_PRODUCT_URL_INITIALIZED_KEY] = True


def _on_ads_product_selector_changed(rows):
    selection = resolve_ads_product_selector_value(
        st.session_state.get(ADS_PRODUCT_SELECTOR_KEY),
        rows=rows,
    )
    st.session_state[ADS_PRODUCT_NAME_KEY] = selection.get("selected_label") or ""
    _synchronise_ads_product_url_state(selection)


def prepare_ads_product_selector_state(rows, *, result=None):
    if ADS_PRODUCT_SELECTOR_KEY in st.session_state:
        return
    saved_name = _normalise_option_label(
        st.session_state.get(ADS_PRODUCT_NAME_KEY)
        or ((result or {}).get("product_name") if isinstance(result, dict) else "")
    )
    saved_product_id = (
        (result or {}).get("product_id") if isinstance(result, dict) else ""
    )
    selection = resolve_edition_ops_product_selection(
        saved_name,
        rows=rows,
        product_id=saved_product_id,
    )
    if selection.get("row"):
        st.session_state[ADS_PRODUCT_SELECTOR_KEY] = (
            _edition_ops_product_selector_identity(selection["row"])
        )
    elif saved_name:
        st.session_state[ADS_PRODUCT_SELECTOR_KEY] = saved_name


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


def _clean_campaign_moment_value(value):
    cleaned = re.sub(r"[\x00-\x1f\x7f]", " ", str(value or ""))
    return re.sub(r"\s+", " ", cleaned).strip()


def _parse_campaign_moment_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = _clean_campaign_moment_value(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _normalise_campaign_moment_option(value, options, default=""):
    clean_value = _clean_campaign_moment_value(value)
    for option in options:
        if clean_value.casefold() == option.casefold():
            return option
    return default


def empty_campaign_moment():
    return {
        "type": "",
        "name": "",
        "market": "Use selected ad country",
        "date": "",
        "promotion": "",
        "strength": "Subtle",
        "include_in_image_prompts": False,
    }


def normalize_campaign_moment(campaign_moment=None, *, selected_country=""):
    moment = empty_campaign_moment()
    if isinstance(campaign_moment, dict):
        moment_type = _normalise_campaign_moment_option(
            campaign_moment.get("type"),
            CAMPAIGN_MOMENT_TYPE_OPTIONS,
            "",
        )
        market = _normalise_campaign_moment_option(
            campaign_moment.get("market"),
            CAMPAIGN_MOMENT_MARKET_OPTIONS,
            "Use selected ad country",
        )
        strength = _normalise_campaign_moment_option(
            campaign_moment.get("strength"),
            CAMPAIGN_MOMENT_STRENGTH_OPTIONS,
            "Subtle",
        )
        parsed_date = _parse_campaign_moment_date(campaign_moment.get("date"))
        moment.update(
            {
                "type": moment_type,
                "name": _clean_campaign_moment_value(campaign_moment.get("name")),
                "market": market,
                "date": parsed_date.isoformat() if parsed_date else "",
                "promotion": _clean_campaign_moment_value(campaign_moment.get("promotion")),
                "strength": strength,
                "include_in_image_prompts": bool(
                    campaign_moment.get("include_in_image_prompts")
                ),
            }
        )
    resolved_market = (
        _clean_campaign_moment_value(selected_country)
        if moment["market"] == "Use selected ad country"
        else moment["market"]
    )
    moment["resolved_market"] = resolved_market or "not supplied"
    return moment


def campaign_moment_has_user_values(campaign_moment):
    moment = normalize_campaign_moment(campaign_moment)
    return any(
        (
            bool(moment["type"]),
            bool(moment["name"]),
            bool(moment["date"]),
            bool(moment["promotion"]),
            moment["market"] != "Use selected ad country",
            moment["strength"] != "Subtle",
            bool(moment["include_in_image_prompts"]),
        )
    )


def campaign_moment_is_active(campaign_moment):
    moment = normalize_campaign_moment(campaign_moment)
    return bool(moment["name"])


def campaign_moment_today(user=None):
    timezone_name = os_accounts.timezone_for_user(user or {}) if user else os_accounts.ADMIN_TIMEZONE
    try:
        return datetime.now(ZoneInfo(timezone_name)).date()
    except Exception:
        return date.today()


def campaign_moment_is_expired(campaign_moment, *, today=None):
    moment = normalize_campaign_moment(campaign_moment)
    parsed_date = _parse_campaign_moment_date(moment.get("date"))
    if not parsed_date:
        return False
    check_date = today or campaign_moment_today()
    return parsed_date < check_date


def validate_campaign_moment(campaign_moment, *, selected_country="", today=None):
    moment = normalize_campaign_moment(campaign_moment, selected_country=selected_country)
    if moment["type"] and not moment["name"]:
        return "Enter the specific campaign moment, such as Father’s Day or NBA Playoffs."
    if campaign_moment_has_user_values(moment) and campaign_moment_is_expired(moment, today=today):
        return "This campaign moment has expired. Update the date or remove the moment before generating timely copy."
    return ""


def campaign_moment_from_result(result, *, selected_country=""):
    if not isinstance(result, dict):
        return empty_campaign_moment()
    return normalize_campaign_moment(
        result.get("campaign_moment"),
        selected_country=selected_country,
    )


def _campaign_moment_context_key(campaign_moment, selected_country=""):
    moment = normalize_campaign_moment(campaign_moment, selected_country=selected_country)
    if not campaign_moment_is_active(moment) and not moment["promotion"]:
        return {}
    key = {"promotion": moment["promotion"]}
    if campaign_moment_is_active(moment):
        key.update(
            {
                "type": moment["type"],
                "name": moment["name"],
                "market": moment["market"],
                "date": moment["date"],
                "strength": moment["strength"],
                "include_in_image_prompts": bool(moment["include_in_image_prompts"]),
            }
        )
    return key


def build_campaign_moment_copy_relevance_block(
    campaign_moment,
    *,
    selected_country="",
    campaign_type="",
):
    moment = normalize_campaign_moment(campaign_moment, selected_country=selected_country)
    if not campaign_moment_is_active(moment):
        return ""
    promotion_line = moment["promotion"] or "none supplied"
    date_line = moment["date"] or "not supplied"
    type_line = moment["type"] or "not supplied"
    strength = moment["strength"]
    if campaign_type == "Instant Experience":
        field_rules = """HEADLINE AND CALL-TO-ACTION RULES

The selected moment may influence headlines and call-to-action button-label choices only when it improves relevance, sounds natural and does not replace the product identity or scarcity message across the entire set.

For Instant Experience campaigns:
- Preserve exactly three ordered description options per route.
- Preserve exactly three Headlines per route.
- Preserve exactly three Call To Action button-label options per route.
- Do not create or request Meta link-description or Meta Ad Description fields.
- Do not force the event into every option.
- Use the Campaign Moment only when it safely improves one of the three product-aware description archetypes.
- Even when Campaign-led is selected, retain product identity and edition scarcity across the set.
- Use valid Instant Experience creative CTA labels in the CTA field rather than sentence-style buttons."""
    else:
        field_rules = f"""HEADLINE AND DESCRIPTION RULES

The selected moment may influence headlines and description lines only when it improves relevance, fits the existing character limits, sounds natural and does not replace the product identity or scarcity message across the entire set.

For Carousel campaigns:
- Preserve all existing {CAROUSEL_CARD_MAX_CHARACTERS}-character headline and description limits.
- Do not force the event into every card.
- Use the Campaign Moment on no more than one carousel card unless the user selects Campaign-led.
- Even when Campaign-led is selected, retain product identity and edition scarcity across the sequence.
- Do not weaken the existing five-card roles or product-dominance rules.
- Never lengthen text beyond existing platform limits to fit an event name."""
    return f"""CAMPAIGN MOMENT — OPTIONAL RELEVANCE LAYER

A campaign moment has been supplied for timely relevance.

- Moment type: {type_line}
- Moment name: {moment["name"]}
- Relevant market: {moment["resolved_market"]}
- Event/end date: {date_line}
- Confirmed promotion: {promotion_line}
- Relevance strength: {strength}

Use this moment in exactly one primary ad-text variation by default.

Required variation structure:

1. Evergreen emotional/nostalgia angle — no campaign-moment reference.
2. Evergreen collector, product or fan-identity angle — no campaign-moment reference.
3. Timely angle — naturally incorporate the supplied campaign moment.

Do not force the moment into every variation.

Even when "Campaign-led" is selected:
- Only one primary-text variation should be campaign-led.
- At least two evergreen primary-text variations must remain available for testing.
- The framed artwork, fan identity, nostalgia and limited-edition value must remain central.

Usage by strength:

SUBTLE:
Mention the moment naturally and briefly in one variation. Do not lead with a sale. The reference should feel like a timely reason to buy rather than the entire ad concept.

MODERATE:
Make one variation clearly connected to the moment, while keeping the sporting memory, product and collector value central.

CAMPAIGN-LED:
Make one variation primarily built around the selected moment or buying occasion. Preserve two evergreen alternatives.

The timely variation must sound human and emotionally relevant. Avoid mechanical lines such as "Father’s Day is approaching. Buy now." Do not hard-code examples into every generated result.

{field_rules}

ACCURACY AND OFFER SAFETY

- Never invent event dates, match results, teams, participants or competition outcomes.
- Never claim a product is officially licensed, endorsed by or affiliated with an event unless that information is explicitly supplied and verified elsewhere in the existing product data.
- Never invent a discount, free-shipping offer, sale deadline or scarcity figure.
- Only use the exact promotion entered by the user.
- If Confirmed promotion is "none supplied", do not create a discount, free-shipping claim, sale deadline, coupon, bundle offer or savings claim.
- Do not convert a normal product into a "Father’s Day Edition", "World Cup Edition" or similar unless that is the product’s verified name.
- Do not claim "ends soon", "last chance" or "final hours" unless supported by the supplied date or offer data.
- Use market-appropriate terminology already established in the Ads system, including "soccer" for the USA and "football" for the UK where relevant.
- If the selected moment is weakly connected to the product, make the reference about the buying occasion or fan experience rather than inventing a sporting connection.
- Ensure any promotion referenced in the ad can be matched by the landing page. Flag any potential offer mismatch instead of assuming the offer exists on the page."""


def build_campaign_moment_visual_context(campaign_moment, *, selected_country=""):
    moment = normalize_campaign_moment(campaign_moment, selected_country=selected_country)
    if not campaign_moment_is_active(moment) or not moment["include_in_image_prompts"]:
        return ""
    return f"""CAMPAIGN MOMENT VISUAL CONTEXT — OPTIONAL:
The selected campaign moment is {moment["name"]} for {moment["resolved_market"]}. Use it only as restrained, premium and believable visual context when it naturally supports the product. The framed artwork must remain the visual hero. Do not make an event prop or seasonal decoration more prominent than the framed artwork. Do not automatically place the event name as text inside the image. Do not add official event logos, trademarks, branded graphics, athlete endorsements, prices, discounts, buttons, banners or promotional stickers. Do not make every room look themed. Preserve all current product locks, square-format locks, card composition rules, room variation rules and photorealism requirements."""


def apply_campaign_moment_copy_relevance_layer(
    prompt,
    campaign_moment,
    *,
    selected_country="",
    campaign_type="",
):
    if not prompt:
        return prompt
    block = build_campaign_moment_copy_relevance_block(
        campaign_moment,
        selected_country=selected_country,
        campaign_type=campaign_type,
    )
    if not block or "CAMPAIGN MOMENT — OPTIONAL RELEVANCE LAYER" in prompt:
        return prompt
    return f"{prompt.rstrip()}\n\n{block}"


def campaign_moment_from_form_state():
    return normalize_campaign_moment(
        {
            "type": st.session_state.get("ads_campaign_moment_type"),
            "name": st.session_state.get("ads_campaign_moment_name"),
            "market": st.session_state.get(
                "ads_campaign_moment_market",
                "Use selected ad country",
            ),
            "date": st.session_state.get("ads_campaign_moment_date"),
            "promotion": st.session_state.get("ads_campaign_moment_promotion"),
            "strength": st.session_state.get("ads_campaign_moment_strength", "Subtle"),
            "include_in_image_prompts": st.session_state.get(
                "ads_campaign_moment_include_images",
                False,
            ),
        }
    )


def clear_campaign_moment_state():
    for key in CAMPAIGN_MOMENT_SESSION_KEYS:
        st.session_state.pop(key, None)


def _normalise_ie_option(value, options, default):
    clean_value = _normalise_option_label(value)
    for option in options:
        if clean_value.casefold() == str(option).casefold():
            return option
    return default


def _normalise_ie_route(value, default="FEEL", *, allow_build=True):
    route = str(value or "").strip().upper()
    if route not in IE_ROUTE_IDS:
        route = default
    if route == "BUILD" and not allow_build:
        route = default if default != "BUILD" else "ACT"
    return route


def _normalise_positive_int(value, default=0):
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return default


def default_instant_experience_settings(*, output_mode=IE_MODE_CLASSIC):
    return {
        "output_mode": output_mode,
        "audience_mindset": "Auto-match",
        "primary_angle": "Auto-match",
        "urgency_placement": "Auto-match route",
        "destination_scope": "Featured product page + catalogue",
        "collection_name": "",
        "collection_url": "",
        "collection_product_set_name": "",
        "collection_exact_offer": "",
        "eligible_product_count": 0,
        "multi_product_reference_count": 0,
        "visual_direction": "Auto — Match the Creative Route",
        "fixed_button_cta_mode": "Hold fixed-button CTA constant across all routes",
        "route_a": "FEEL",
        "route_b": "BELONG",
        "route_c": "ACT",
        "advanced_visual": {
            key: IE_AUTO_FRESH_MATCH for key in IE_ADVANCED_VISUAL_OPTION_SETS
        },
    }


def normalize_instant_experience_settings(settings=None):
    source = settings if isinstance(settings, dict) else {}
    normalized = default_instant_experience_settings()
    normalized["output_mode"] = _normalise_ie_option(
        source.get("output_mode"),
        IE_CREATIVE_OUTPUT_MODES,
        normalized["output_mode"],
    )
    normalized["audience_mindset"] = _normalise_ie_option(
        source.get("audience_mindset"),
        IE_AUDIENCE_MINDSETS,
        normalized["audience_mindset"],
    )
    normalized["primary_angle"] = _normalise_ie_option(
        source.get("primary_angle"),
        IE_PRIMARY_CREATIVE_ANGLES,
        normalized["primary_angle"],
    )
    normalized["urgency_placement"] = _normalise_ie_option(
        source.get("urgency_placement"),
        IE_URGENCY_PLACEMENTS,
        normalized["urgency_placement"],
    )
    normalized["destination_scope"] = _normalise_ie_option(
        source.get("destination_scope"),
        IE_DESTINATION_SCOPES,
        normalized["destination_scope"],
    )
    normalized["visual_direction"] = _normalise_ie_option(
        source.get("visual_direction"),
        IE_VISUAL_DIRECTIONS,
        normalized["visual_direction"],
    )
    normalized["fixed_button_cta_mode"] = _normalise_ie_option(
        source.get("fixed_button_cta_mode"),
        IE_FIXED_BUTTON_CTA_MODES,
        normalized["fixed_button_cta_mode"],
    )
    for text_key in (
        "collection_name",
        "collection_url",
        "collection_product_set_name",
        "collection_exact_offer",
    ):
        normalized[text_key] = _clean_campaign_moment_value(source.get(text_key))
    normalized["eligible_product_count"] = _normalise_positive_int(
        source.get("eligible_product_count")
    )
    normalized["multi_product_reference_count"] = _normalise_positive_int(
        source.get("multi_product_reference_count")
    )
    collection_valid = instant_experience_collection_destination_is_valid(normalized)
    used_routes = set()
    for key in IE_SMART_ROUTE_KEYS:
        default_route = IE_DEFAULT_SMART_ROUTES[key]
        route = _normalise_ie_route(
            source.get(key, default_route),
            default_route,
            allow_build=key == "route_c" and collection_valid,
        )
        if route in used_routes:
            route = next(
                candidate
                for candidate in ("FEEL", "BELONG", "ACT", "BUILD")
                if candidate not in used_routes
                and (candidate != "BUILD" or (key == "route_c" and collection_valid))
            )
        normalized[key] = route
        used_routes.add(route)
    advanced_source = source.get("advanced_visual") if isinstance(source.get("advanced_visual"), dict) else {}
    for key, options in IE_ADVANCED_VISUAL_OPTION_SETS.items():
        normalized["advanced_visual"][key] = _normalise_ie_option(
            advanced_source.get(key),
            options,
            IE_AUTO_FRESH_MATCH,
        )
    return normalized


def instant_experience_collection_destination_is_valid(settings):
    return (
        settings.get("destination_scope") == "Curated collection page + catalogue"
        and bool(settings.get("collection_name"))
        and is_valid_product_page_url(settings.get("collection_url"))
        and bool(settings.get("collection_product_set_name"))
    )


def exact_offer_from_inputs(campaign_moment=None, instant_experience_settings=None):
    settings = normalize_instant_experience_settings(instant_experience_settings)
    collection_offer = _clean_campaign_moment_value(settings.get("collection_exact_offer"))
    moment = normalize_campaign_moment(campaign_moment)
    return collection_offer or moment.get("promotion") or ""


def instant_experience_route_supports_offer(route_id):
    return route_id == "BUILD"


def instant_experience_selected_routes(settings):
    settings = normalize_instant_experience_settings(settings)
    if settings["output_mode"] == IE_MODE_CLASSIC:
        return [("CLASSIC COLLECTOR", "ACT")]
    if settings["output_mode"] == IE_MODE_SELECTED:
        return [("SELECTED ROUTE", route_for_primary_angle(settings["primary_angle"], settings))]
    return [
        (IE_SMART_OPTION_HEADINGS[key], settings[key])
        for key in IE_SMART_ROUTE_KEYS
    ]


def route_for_primary_angle(primary_angle, settings=None):
    settings = normalize_instant_experience_settings(settings)
    if primary_angle in {"Moment / Memory", "Legacy / Achievement", "Milestone"}:
        return "FEEL"
    if primary_angle in {"Fan Identity", "Ownership / Display", "Rivalry / Allegiance", "Gift"}:
        return "BELONG"
    if primary_angle in {"Collector / Rarity"}:
        return "ACT"
    if primary_angle in {"Build a Collection", "Offer / Sale"}:
        return "BUILD" if instant_experience_collection_destination_is_valid(settings) else "ACT"
    return "FEEL"


def instant_experience_settings_context_key(settings):
    settings = normalize_instant_experience_settings(settings)
    payload = {
        "output_mode": settings["output_mode"],
        "audience_mindset": settings["audience_mindset"],
        "primary_angle": settings["primary_angle"],
        "urgency_placement": settings["urgency_placement"],
        "destination_scope": settings["destination_scope"],
        "collection_name": settings["collection_name"],
        "collection_url": settings["collection_url"],
        "collection_product_set_name": settings["collection_product_set_name"],
        "collection_exact_offer": settings["collection_exact_offer"],
        "eligible_product_count": settings["eligible_product_count"],
        "multi_product_reference_count": settings["multi_product_reference_count"],
        "visual_direction": settings["visual_direction"],
        "fixed_button_cta_mode": settings["fixed_button_cta_mode"],
        "fixed_routes": {key: settings[key] for key in IE_SMART_ROUTE_KEYS},
        "advanced_visual": settings["advanced_visual"],
    }
    return payload


def instant_experience_output_suffix(settings):
    settings = normalize_instant_experience_settings(settings)
    if settings["output_mode"] == IE_MODE_SMART:
        route_names = [
            settings[key]
            for key in IE_SMART_ROUTE_KEYS
        ]
        return (
            "Which Instant Experience cover would you like me to generate: "
            f"{', '.join(route_names[:-1])} or {route_names[-1]}?"
        )
    if settings["output_mode"] == IE_MODE_SELECTED:
        route = route_for_primary_angle(settings["primary_angle"], settings)
        return f"Would you like me to generate the {route} Instant Experience cover?"
    return "Would you like me to generate the Classic Collector Instant Experience cover?"


def validate_instant_experience_settings(settings, campaign_moment=None):
    settings = normalize_instant_experience_settings(settings)
    if settings["output_mode"] == IE_MODE_CLASSIC:
        return ""
    exact_offer = exact_offer_from_inputs(campaign_moment, settings)
    routes = [route for _label, route in instant_experience_selected_routes(settings)]
    if settings["destination_scope"] == "Curated collection page + catalogue":
        if not settings["collection_name"]:
            return "Enter a collection name for the Instant Experience collection destination."
        if not is_valid_product_page_url(settings["collection_url"]):
            return "Enter a valid collection URL for the Instant Experience collection destination."
        if not settings["collection_product_set_name"]:
            return "Enter the exact product-set name for the Instant Experience collection destination."
    if "BUILD" in routes:
        if not instant_experience_collection_destination_is_valid(settings):
            return "Build a Collection requires a valid collection name, collection URL and exact product-set name."
        if settings["eligible_product_count"] < 4:
            return "Build a Collection requires at least four eligible catalogue products."
        if settings["multi_product_reference_count"] < 2:
            return "Build a Collection requires at least two exact product reference assets for multi-product cover promises."
    if settings["primary_angle"] == "Offer / Sale" and not exact_offer:
        return "Offer / Sale requires an exact verified offer."
    if "BUILD" in routes and settings["primary_angle"] == "Offer / Sale" and not exact_offer:
        return "Build offer routes require the exact verified offer."
    if settings["primary_angle"] == "Gift" and settings["audience_mindset"] not in {"Gift buyer", "Auto-match"}:
        return "Gift language requires Gift buyer targeting or Auto-match."
    return ""


def instant_experience_sport_direction(category):
    category_key = str(category or "").strip()
    directions = {
        "Baseball": "ballpark memory, generations, swing and legacy; walnut, mineral plaster, intimate office or reading room, warm side light",
        "NBA": "mentality, energy, greatness and identity; charcoal limewash, concrete and oak, contemporary media room or home office, dusk",
        "Football": "history, rivalry and club belonging; limewash, restrained brick or stone, study or stair landing, diffuse light",
        "Motorsport": "speed, raw memory and rivalry; microcement, blackened steel and walnut, garage lounge without vehicles or novelty props, directional light",
        "Cricket": "summer memory, heritage and national pride only when verified; linen, plaster and warm timber, calm daylight",
        "Golf": "prestige, history and reverence; pale stone or dark oak, foyer, library or study, soft formal light",
        "Horse Racing": "prestige, history and reverence; pale stone or dark oak, foyer, library or study, soft formal light",
        "Ice Hockey": "grit, loyalty and resilience; masonry, charcoal and oak, media room or basement lounge, cool daylight plus restrained practical light",
        "Combat": "grit, loyalty and resilience; masonry, charcoal and oak, media room or basement lounge, cool daylight plus restrained practical light",
        "NFL": "loyalty, tradition and game-day belonging; plaster, dark timber, den or restrained home bar, warm evening",
        "Rugby Union": "loyalty, tradition and game-day belonging; plaster, dark timber, den or restrained home bar, warm evening",
        "Tennis": "prestige, focus and sporting reverence; mineral plaster, pale stone and warm timber, study or gallery landing, soft daylight",
    }
    return directions.get(
        category_key,
        "collector memory, identity and premium ownership; believable residential architecture, restrained wall material, natural light",
    )


def resolved_instant_experience_sport_atmosphere(category):
    category_key = str(category or "").strip()
    directions = {
        "Baseball": "ballpark memory, generations, swing and legacy expressed through restrained warmth; no sporting props",
        "NBA": "basketball mentality, energy, greatness and fan identity expressed through contemporary restraint; no sporting props",
        "Football": "club history, rivalry, matchday belonging and supporter loyalty expressed through architectural confidence; no sporting props",
        "Motorsport": "speed, mechanical precision, raw race memory and rivalry expressed through controlled material tension; no vehicles or novelty props",
        "Cricket": "summer memory, heritage and verified national connection expressed through calm natural character; no sporting props",
        "Golf": "prestige, history, focus and reverence expressed through quiet formal restraint; no sporting props",
        "Horse Racing": "race-day prestige, history and reverence expressed through quiet formal restraint; no sporting props",
        "Ice Hockey": "grit, loyalty and resilience expressed through cool controlled atmosphere; no sporting props",
        "Combat": "discipline, pressure, grit and resilience expressed through controlled architectural weight; no sporting props",
        "NFL": "tradition, Sunday intensity and game-day belonging expressed through warm restrained atmosphere; no sporting props",
        "Rugby Union": "tradition, test-match pressure and supporter belonging expressed through warm restrained atmosphere; no sporting props",
        "Tennis": "focus, pressure, sporting poise and reverence expressed through quiet refined atmosphere; no sporting props",
    }
    return directions.get(
        category_key,
        "collector memory, identity and premium ownership expressed through quiet believable atmosphere; no sporting props",
    )


def instant_experience_fingerprint(
    route_id,
    *,
    settings=None,
    category="",
    sub_angle="",
    creative_cta="",
):
    settings = normalize_instant_experience_settings(settings)
    route = INSTANT_EXPERIENCE_ROUTE_CONFIGS.get(route_id, INSTANT_EXPERIENCE_ROUTE_CONFIGS["ACT"])
    advanced = settings["advanced_visual"]
    return {
        "route": route_id,
        "sub_angle": sub_angle or route["angle"],
        "hook_family": route["primary_text_structure"],
        "cover_layout": advanced.get("cover_layout")
        if settings["visual_direction"] == "Manual Overrides"
        else route["cover_composition"],
        "urgency_placement": settings["urgency_placement"],
        "creative_cta": creative_cta or route["creative_cta_family"][0],
        "room_type": advanced.get("room_type")
        if settings["visual_direction"] == "Manual Overrides"
        else route["room_family"],
        "wall_colour_family": advanced.get("wall_colour_family")
        if settings["visual_direction"] == "Manual Overrides"
        else route["wall_family"],
        "wall_material": advanced.get("wall_material")
        if settings["visual_direction"] == "Manual Overrides"
        else route["wall_family"],
        "camera_family": advanced.get("camera_family")
        if settings["visual_direction"] == "Manual Overrides"
        else route["camera_family"],
        "shot_distance": advanced.get("shot_distance")
        if settings["visual_direction"] == "Manual Overrides"
        else route["product_prominence"],
        "lighting_direction": advanced.get("lighting_direction")
        if settings["visual_direction"] == "Manual Overrides"
        else route["lighting_family"],
        "time_of_day": advanced.get("time_of_day")
        if settings["visual_direction"] == "Manual Overrides"
        else route["lighting_family"],
        "sport_family": resolved_instant_experience_sport_atmosphere(category),
    }


def build_instant_experience_fingerprints(settings, *, category=""):
    return [
        instant_experience_fingerprint(route, settings=settings, category=category)
        for _label, route in instant_experience_selected_routes(settings)
    ]


def update_recent_instant_experience_fingerprints(fingerprints):
    if not fingerprints:
        return
    recent = st.session_state.get(ADS_IE_RECENT_FINGERPRINTS_KEY)
    recent = list(recent) if isinstance(recent, list) else []
    for fingerprint in fingerprints:
        if fingerprint not in recent:
            recent.insert(0, fingerprint)
    st.session_state[ADS_IE_RECENT_FINGERPRINTS_KEY] = recent[:12]


def _fingerprints_text(fingerprints):
    if not fingerprints:
        return "No recent Instant Experience fingerprints are available in this session."
    return json.dumps(fingerprints[:12], ensure_ascii=False, indent=2)


IE_WIDGET_KEYS = {
    "output_mode": "ads_ie_output_mode",
    "audience_mindset": "ads_ie_audience_mindset",
    "primary_angle": "ads_ie_primary_angle",
    "urgency_placement": "ads_ie_urgency_placement",
    "destination_scope": "ads_ie_destination_scope",
    "collection_name": "ads_ie_collection_name",
    "collection_url": "ads_ie_collection_url",
    "collection_product_set_name": "ads_ie_collection_product_set_name",
    "collection_exact_offer": "ads_ie_collection_exact_offer",
    "eligible_product_count": "ads_ie_eligible_product_count",
    "multi_product_reference_count": "ads_ie_multi_product_reference_count",
    "visual_direction": "ads_ie_visual_direction",
    "fixed_button_cta_mode": "ads_ie_fixed_button_cta_mode",
    "route_a": "ads_ie_route_a",
    "route_b": "ads_ie_route_b",
    "route_c": "ads_ie_route_c",
}
for _advanced_key in IE_ADVANCED_VISUAL_OPTION_SETS:
    IE_WIDGET_KEYS[f"advanced_{_advanced_key}"] = f"ads_ie_advanced_{_advanced_key}"


def initialise_instant_experience_widget_defaults():
    defaults = default_instant_experience_settings(output_mode=IE_MODE_SMART)
    for key, widget_key in IE_WIDGET_KEYS.items():
        if key.startswith("advanced_"):
            advanced_key = key.removeprefix("advanced_")
            st.session_state.setdefault(widget_key, defaults["advanced_visual"][advanced_key])
        else:
            st.session_state.setdefault(widget_key, defaults.get(key, ""))
    current = collect_instant_experience_settings_from_state()
    normalized = normalize_instant_experience_settings(current)
    for key in IE_SMART_ROUTE_KEYS:
        widget_key = IE_WIDGET_KEYS[key]
        if st.session_state.get(widget_key) != normalized[key]:
            st.session_state[widget_key] = normalized[key]


def collect_instant_experience_settings_from_state():
    advanced = {
        key: st.session_state.get(IE_WIDGET_KEYS[f"advanced_{key}"], IE_AUTO_FRESH_MATCH)
        for key in IE_ADVANCED_VISUAL_OPTION_SETS
    }
    return normalize_instant_experience_settings(
        {
            "output_mode": st.session_state.get(IE_WIDGET_KEYS["output_mode"]),
            "audience_mindset": st.session_state.get(IE_WIDGET_KEYS["audience_mindset"]),
            "primary_angle": st.session_state.get(IE_WIDGET_KEYS["primary_angle"]),
            "urgency_placement": st.session_state.get(IE_WIDGET_KEYS["urgency_placement"]),
            "destination_scope": st.session_state.get(IE_WIDGET_KEYS["destination_scope"]),
            "collection_name": st.session_state.get(IE_WIDGET_KEYS["collection_name"]),
            "collection_url": st.session_state.get(IE_WIDGET_KEYS["collection_url"]),
            "collection_product_set_name": st.session_state.get(IE_WIDGET_KEYS["collection_product_set_name"]),
            "collection_exact_offer": st.session_state.get(IE_WIDGET_KEYS["collection_exact_offer"]),
            "eligible_product_count": st.session_state.get(IE_WIDGET_KEYS["eligible_product_count"]),
            "multi_product_reference_count": st.session_state.get(IE_WIDGET_KEYS["multi_product_reference_count"]),
            "visual_direction": st.session_state.get(IE_WIDGET_KEYS["visual_direction"]),
            "fixed_button_cta_mode": st.session_state.get(IE_WIDGET_KEYS["fixed_button_cta_mode"]),
            "route_a": st.session_state.get(IE_WIDGET_KEYS["route_a"]),
            "route_b": st.session_state.get(IE_WIDGET_KEYS["route_b"]),
            "route_c": st.session_state.get(IE_WIDGET_KEYS["route_c"]),
            "advanced_visual": advanced,
        }
    )


def _route_options_for_position(position_key, selected_routes, *, collection_valid):
    base = ["FEEL", "BELONG", "ACT"]
    if position_key == "route_c" and collection_valid:
        base.append("BUILD")
    blocked = {
        route
        for key, route in selected_routes.items()
        if key != position_key
    }
    options = [route for route in base if route not in blocked]
    current = selected_routes.get(position_key)
    if current and current not in options and (current != "BUILD" or collection_valid):
        options.insert(0, current)
    return options or [IE_DEFAULT_SMART_ROUTES[position_key]]


def render_instant_experience_creative_panel(campaign_type):
    return None


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

Use the supplied product reference as the exact framed Sports Cave product.

Keep the uploaded artwork and frame exactly the same.

Do not redesign, repaint, redraw, replace, reinterpret or regenerate the artwork inside the frame.

Do not change the athlete or subject, face, team, vehicle, uniform, livery, colours, typography, text, badge, edition number, edition plate, plaque, signature, layout, crop, composition, frame colour, frame shape or landscape proportions.

Do not blur, stretch, warp, bend, squash or distort the artwork or frame.

The artwork must remain sharp, rectangular, correctly aligned and physically believable inside the frame.

Do not generate a lookalike version of the artwork.

Do not add additional artwork, fake branding, unofficial logos or competing focal points."""


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
    return (
        "FINAL VERIFICATION: Output one true 1024 × 1024 image only. Width must equal height. "
        "Never output a landscape or portrait image. Confirm that the complete supplied product and outer frame "
        "remain visible and that the artwork, frame, typography, badge, plaque and edition details are unchanged."
    )


def build_carousel_card_one_mockups_close_up_foundation():
    foundation = image_factory.get_close_up_wall_prompt_foundation()
    if not foundation:
        return ""
    replacements = {
        "Using the uploaded artwork and frame as the exact reference, create a 1024 x 1024 ultra-realistic close-up lifestyle mockup. Use a different angle and different wall colour so it looks like a different house and camera angle to the previous generation.": (
            "Using the uploaded artwork and frame as the exact reference, create a 1024 x 1024 ultra-realistic close-up product mockup. Use a restrained wall colour, material and lighting treatment that fits the selected product, sport and market while keeping the frame extremely large."
        ),
        "Create a close-up shot of the framed artwork mounted on a premium wall, as if it is hanging in someone's real home.": (
            "Create a close-up shot of the framed artwork mounted on a premium wall, as if it is hanging in someone's real home."
        ),
        "Slight natural angle from one side.": (
            "Almost perfectly straight-on camera position, with only a very subtle 2-4 degree natural angle when required for realistic frame depth."
        ),
        "close-up lifestyle mockup": "close-up product mockup",
        "different house and camera angle": "different premium wall context",
    }
    for old, new in replacements.items():
        foundation = foundation.replace(old, new)
    return foundation.strip()


def build_carousel_card_one_product_hero_lock():
    close_up_foundation = build_carousel_card_one_mockups_close_up_foundation()
    foundation_block = (
        f"\n\nMOCKUPS CLOSE-UP WALL SHOT FOUNDATION — REUSED:\n{close_up_foundation}"
        if close_up_foundation
        else ""
    )
    return f"""CARD 1 CLOSE-UP PRODUCT HERO LOCK — MANDATORY:
Carousel Card 1 must use the existing Mockups/Reel Close-Up Premium Wall Shot as its close-up composition foundation, then obey the stricter Carousel Card 1 rules below. Carousel Card 1 must be a premium close-up product photograph, not a lifestyle room photograph.{foundation_block}

The complete framed product must occupy approximately 65-80% of the useful square composition and should fill most of the available visual area while preserving its correct landscape proportions.

Keep all four outer frame edges and all four corners completely visible. Leave natural breathing room around the frame. Never crop the frame, artwork, border, plaque or shadow.

Use an almost perfectly straight-on camera position, level with the centre of the artwork. Allow no more than a very subtle 2-4 degree natural angle when required for realistic frame depth.

Use the visual character of a premium 70-85 mm product-photography lens:
- No wide-angle room view.
- No distant camera position.
- No exaggerated perspective.
- No large foreground.
- No visible ceiling.
- No doorway framing.
- No long floor area.
- No large furniture.
- No room-establishing composition.

Show only enough environment to prove the frame is physically mounted in a real premium home. The background should mainly be a realistic wall surface. At most, allow a small restrained edge of a console, cabinet or surface at the bottom of the image, but only if it does not reduce the frame's required product dominance.

The frame and artwork must be immediately readable at Facebook carousel thumbnail size. The viewer should first see the product, then notice the wall and atmosphere afterward.

CARD 1 SCENE RULE — MANDATORY:
Preserve the selected sport, country and product-specific visual adaptation, but express it through restrained wall material, lighting and colour rather than a full room scene. Do not generate an entry gallery, living room, office, man cave, home bar or other wide lifestyle environment for Card 1.

Card 1 should feel like a high-end framed-art campaign photograph:
- Exact framed product as the hero.
- Narrow wall context.
- Sharp artwork detail.
- Visible physical frame depth.
- Controlled real-glass reflections.
- Realistic mounting and contact shadow.
- Premium natural light.
- Photorealistic materials.
- No obvious AI appearance.

Card 1 must:
- Predominantly display the framed product.
- Show the complete outer frame without cropping any edge.
- Keep the artwork large, sharp and readable.
- Use an extreme close-up product-photography camera distance.
- Show only narrow wall context around it.
- Avoid wide establishing shots.
- Avoid furniture blocking or visually competing with the frame.
- Retain all existing product-lock and artwork-preservation instructions.

STRICT PRODUCT PRESERVATION — CARD 1:
Use the uploaded framed product as the exact compositing source. Preserve the entire original frame and everything inside it exactly: artwork, athletes and faces, vehicles, colours, typography, names, signatures, Sports Cave branding, borders, edition plaque and number, internal crop and composition, frame colour, thickness and proportions. Do not regenerate, reinterpret, redraw or create a lookalike of the artwork. Do not blur, stretch, warp, bend, squash or distort the artwork or frame. The artwork must never extend beyond its original border.

CARD 1 REALISM UPGRADE — MANDATORY:
Card 1 must resemble genuine commercial product photography. Require physically convincing premium timber frame depth, sharp square corners and clean joins, natural glass thickness, subtle reflections that match the light source, controlled glare that never hides important artwork details, realistic contact shadow behind and slightly below the frame, accurate scale and perspective, fine wall texture, natural highlight falloff and realistic sharpness without oversharpening.

Reject flat pasted-on artwork, fake or missing glass, plastic frame materials, artificial HDR, excessive glow, warped frame edges, curved walls, impossible reflections, melted textures, fake luxury styling, AI-generated-looking artwork, excessive depth of field, blurred product detail, compact entry gallery compositions, visible flooring, furniture-led composition or any room-setting instruction that would make the framed product smaller than 65% of the useful composition."""


def build_carousel_product_dominance_principle_lock():
    return """PRODUCT DOMINANCE PRINCIPLE — MANDATORY:
We are selling the framed Sports Cave edition, not the room. The room may enhance the product, provide scale and create aspiration, but it must never overpower the framed artwork or make it look small. In every carousel card, the framed edition must be dominant, instantly recognizable and readable as a small Facebook carousel card on a phone. Use varied rooms, wall colours, camera positions and viewing angles without creating distant product shots. Maintain a cohesive premium campaign while ensuring every card works independently as a Facebook advertisement."""


def build_carousel_card_camera_distance_lock(index):
    if index == 1:
        return build_carousel_card_one_product_hero_lock()
    if index in {2, 3, 4}:
        return """CARDS 2-4 PRODUCT-DOMINANT LIFESTYLE COMPOSITION — MANDATORY:
Use a medium or medium-close lifestyle composition, not a distant wide-angle room shot. The complete framed artwork should generally occupy approximately 45-65% of the useful square composition. The product must remain instantly recognizable and readable when viewed as a small Facebook carousel card on a phone. Show enough of the room to create variety, context, ownership appeal and atmosphere, but do not place the frame far away, at the end of a large room or as a small background decoration. Never use an extreme wide shot, excessive empty space or oversized furniture that visually reduces the product. Keep the complete outer frame visible with breathing room around it and do not crop any part of the artwork or frame."""
    return """CARD 5 PRODUCT-PROMINENT SCARCITY COMPOSITION — MANDATORY:
Finish with a dramatic product-led scarcity image using a close or medium-close composition. Keep the framed edition prominent even when the card focuses on scarcity, edition details or a different environment. The framed edition must remain one of the largest elements in the composition and must not become secondary to scarcity messaging, furniture, architecture or atmosphere. Make the existing edition badge, plaque or numbered-edition detail visible when it exists in the supplied product, but never invent, replace or modify an edition number. Do not zoom out significantly farther than Cards 2-4. Keep the complete outer frame visible with breathing room around it and do not crop any part of the artwork or frame."""


def build_carousel_strict_product_lock():
    return """STRICT PRODUCT LOCK — MANDATORY:
Use the uploaded product image as the exact compositing source. Preserve the exact artwork, outer frame, colours, text, typography, badges, edition details, crop and internal composition. Do not redraw, regenerate, reinterpret or replace anything inside the frame. Do not change the frame colour, thickness, shape, proportions or material. Do not crop, stretch, warp, bend, blur or distort the artwork or frame. Keep the complete outer frame visible. The artwork must remain sharp and visually legible. Ensure the frame is mounted at a believable height and realistic scale."""


def build_carousel_photorealism_lock():
    return """CAROUSEL PHOTOREALISM REQUIREMENTS — MANDATORY:
Make the room, frame and product placement resemble a genuine high-end interior photograph, not an AI-generated room or digital render. Use believable architecture, correct perspective, natural proportions and physically accurate scale. Create realistic contact shadows behind and below the frame. Use subtle, controlled glass reflections without obscuring the artwork. Give the frame convincing timber depth, sharp corners, natural texture and accurate mounting. Use realistic natural or practical lighting with consistent direction and colour temperature. Avoid plastic-looking surfaces, excessive HDR, artificial glow, oversharpening and cinematic effects that make the image look generated. Avoid warped walls, bent furniture, duplicate objects, melted textures, impossible shadows, distorted decor, floating objects and inconsistent reflections. Keep room styling restrained and believable with a small number of purposeful objects rather than AI-generated clutter. Do not add people unless the individual carousel concept explicitly requires them; if people are required, they must look anatomically and photographically realistic."""


def build_carousel_sequential_photo_variation_lock(index):
    preceding_card_rule = (
        "As Card 1, establish the sequence's closest and most product-dominant viewpoint."
        if index == 1
        else (
            f"As Card {index}, use a camera viewpoint and artwork placement that are visibly "
            f"different from the preceding Card {index - 1}."
        )
    )
    return f"""SEQUENTIAL PHOTO VARIATION — MANDATORY

This image must look like a genuinely different photograph from the other carousel cards—not the same room mockup with minor styling changes. Give this card a clearly distinct camera viewpoint, artwork position and composition. Vary naturally between perspectives such as a subtle left three-quarter angle, right three-quarter angle, straight-on view, slightly higher or lower camera position, or a different off-centre placement. These are examples only; choose the most realistic premium composition for each card.

Every card after Card 1 must be visibly different from the preceding card in camera angle and frame placement. Do not repeat nearly identical crops, wall positions, room layouts or viewing angles.

{preceding_card_rule}

The framed artwork must remain dominant and large enough to recognise immediately in a Facebook carousel. Never create variation by zooming too far out or making the product smaller. The room should enhance the artwork, never compete with it. Preserve all existing product-lock, photorealism, square-format and card-specific prominence requirements."""


def build_carousel_image_prompt_schema(
    index,
    role,
    campaign_moment=None,
    *,
    product_name="",
    category="",
    selected_country="",
):
    product_name = _clean_product_name(product_name)
    category = _normalise_option_label(category) or "selected sport category"
    selected_country = _normalise_option_label(selected_country) or "selected market"
    required_purposes = {
        1: "Product identity and a scroll-stopping product hero.",
        2: "The verified moment, era or legacy connected to the product.",
        3: "An emotional collector hook rooted in memory, identity or pride.",
        4: "Fan ownership and how the framed edition commands the wall.",
        5: "Scarcity, limited edition and no second run, using only verified claims.",
    }
    square_lock = build_carousel_square_format_lock()
    product_dominance_lock = build_carousel_product_dominance_principle_lock()
    camera_distance_lock = build_carousel_card_camera_distance_lock(index)
    strict_product_lock = build_carousel_strict_product_lock()
    product_lock = build_product_lock_visual_rules()
    frame_and_glass_rules = build_frame_and_glass_visual_rules()
    room_realism_rules = build_room_realism_visual_rules()
    photorealism_lock = build_carousel_photorealism_lock()
    variation_lock = build_last_image_variation_visual_rules()
    sequential_variation_lock = build_carousel_sequential_photo_variation_lock(index)
    sport_country_adaptation = build_sport_country_visual_adaptation(
        category,
        selected_country,
    )
    campaign_moment_visual_context = build_campaign_moment_visual_context(
        campaign_moment,
        selected_country=selected_country,
    )
    campaign_moment_visual_block = (
        f"\n\n{campaign_moment_visual_context}"
        if campaign_moment_visual_context
        else ""
    )
    final_check = build_carousel_final_square_format_check()
    return f"""CARD {index} IMAGE GENERATION PROMPT

Create a complete, production-ready image for Carousel Card {index}. Create a 1024 × 1024 square image.

Selected Sports Cave product: {product_name}
Selected sport: {category}
Selected market: {selected_country}
Approved card role: {role}
Required card purpose: {required_purposes[index]}

Use the exact Card {index} headline, description and supplementary creative direction generated earlier in this campaign to shape one concrete scene. Do not render the Meta headline or description inside the image unless the approved card concept explicitly requires on-image text. The creative-direction line is additional context only and must never replace or shorten this complete prompt.

Describe the concrete room or wall, wall colour and material, camera position, lens character, lighting direction, furniture context and emotional atmosphere in full. Do not return a summary, shorthand variation, shared base prompt, list of changes or reference to instructions elsewhere.

{square_lock}

Card-specific visual purpose: {required_purposes[index]}

{product_dominance_lock}

{camera_distance_lock}

{strict_product_lock}

{product_lock}

{frame_and_glass_rules}

{room_realism_rules}

{photorealism_lock}

{variation_lock}

{sequential_variation_lock}

{sport_country_adaptation}{campaign_moment_visual_block}

{final_check}"""


def build_carousel_visual_output_requirements(
    template_key,
    campaign_moment=None,
    *,
    product_name="",
    category="",
    selected_country="",
):
    roles = get_carousel_visual_roles(template_key)
    schema = []
    for index, role in enumerate(roles, start=1):
        schema.append(
            build_carousel_image_prompt_schema(
                index,
                role,
                campaign_moment,
                product_name=product_name,
                category=category,
                selected_country=selected_country,
            )
        )
    schema_text = "\n".join(schema).rstrip()
    return f"""CAROUSEL VISUAL STORY REQUIREMENTS

After every existing Carousel copy, card, primary-text, CTA, setup and URL-parameter field, output exactly {CAROUSEL_CARD_COUNT} complete image-generation prompts. Map one prompt to each generated card in the existing approved order and role structure.

The response is incomplete unless it contains the exact image-generation section heading shown below followed by all five exact card-prompt headings. Under each card heading, write the entire detailed prompt in full. A Creative direction line may remain in the card-copy section as supplementary context, but it can never substitute for, abbreviate or satisfy the required standalone image prompt.

Do not output only Creative direction. Do not output one shared prompt followed by five short variations. Do not use "same as above", "apply the shared rules", "use the previous prompt" or a list of differences. Do not shorten the prompts to save response length. Each card prompt must work when copied by itself into a fresh ChatGPT conversation with the supplied product image.

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

The five images must form one premium visual story, not five random mockups. Maintain compatible colour restraint, ultra-realistic premium lifestyle photography, related lighting character, correct black-frame presentation and a shared Sports Cave collector tone without making the rooms identical.

Each visual must clearly support its assigned card message while the framed product remains the unmistakable hero. Card 1 must deliver the strongest immediate product presentation and be the most zoomed-in card: a close-up wall product photograph with the frame occupying approximately 65-80% of the useful square composition. Cards 2-5 may show more of the environment, but only moderately; none may become a distant room shot. Card 5 must deliver the strongest truthful scarcity or final-claim presentation while keeping the product prominent.

Use this direct conversion-focused visual progression while preserving the selected template's approved role labels:

- Card 1: product identity and a scroll-stopping close-up hero based on the Mockups/Reel Close-Up Premium Wall Shot.
- Card 2: the verified moment, era or legacy.
- Card 3: an emotional collector hook.
- Card 4: fan ownership and how the framed edition commands the wall.
- Card 5: scarcity, limited edition and no second run, using only verified claims and edition details.

For every card, make the exact generated headline, exact generated description, creative direction and image prompt communicate the same clear selling idea. The room, wall, lighting, angle and composition must visibly support that idea. Favour premium but believable homes and ownership environments that help shoppers imagine owning the artwork. Do not use abstract room symbolism when it weakens a direct commercial presentation.

Privately develop a fresh visual concept from the selected product before writing the five prompts. Do not output that reasoning.

Across the five prompts deliberately vary room type, architecture, wall finish, material palette, furniture style, lighting direction, time of day, camera height, camera distance, camera angle, artwork placement, emotional intensity, negative space, framing and composition, and how the room expresses the card's message without zooming out so far that the framed artwork becomes small. For Card 1, variation means restrained wall material, wall colour, lighting and frame-depth treatment only; do not create a full room scene for Card 1.

Coordinate the five prompts as a deliberately varied photographic sequence. Each card after Card 1 must use a visibly different camera viewpoint and artwork placement from the preceding card while preserving Card 1 as the closest product hero, Cards 2-4 as product-dominant medium or medium-close lifestyle images, and Card 5 as a close, dramatic scarcity image.

No two cards may repeat the room type, house architecture, wall treatment, wall colour family, main furniture layout, lighting setup, time-of-day treatment, camera composition, camera height or artwork placement. Card 1 is intentionally a close-up wall product shot, so do not force it into a living room, entry gallery, office, man cave, home bar or other room type for the sake of variety.

Do not merely recolour the same room. Do not default to a generic office, living room, man cave, collector room and close-up sequence.

Treat this as a new creative run. Do not default to room combinations you have previously supplied for Sports Cave. Build a fresh set from the product title, sport, country, card copy and emotional story. Within this run, do not repeat a room type, wall treatment, principal furniture arrangement, lighting setup or camera composition.

Visual variety must never alter, regenerate, crop or distort the supplied artwork or frame. Never crop the outer frame or let the artwork extend beyond its border. Never let room variety, furniture scale, architecture, negative space, sport atmosphere, country adaptation or scarcity emphasis make the framed product secondary. Avoid five near-identical framed mockups with only minor furniture changes.

Normally do not place the card headline or description inside the image because Meta supplies those fields separately. Only include in-image card text if the existing approved campaign template explicitly requires it.

Do not add prices, discounts, fake buttons, fake UI, watermarks, promotional stickers, unsupported text, fake edition details or random copy.

Every image prompt must be fully standalone. Repeat the complete product-lock, frame-and-glass, room-realism, LAST-IMAGE VARIATION LOCK, sport-and-country adaptation and relevant visual-story requirements inside every prompt. Never write "same as above", "use the previous room" or "keep the same settings".

IMAGE GENERATION PROMPTS — COPY ONE AT A TIME

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

Use a stacked full-width square composition with two precisely separated sections:

Upper lifestyle/product image region: approximately 77-79% of the square canvas.
Fixed black footer: approximately 21-23% of the square canvas.

Do not create a left/right split, right sidebar, vertical scarcity panel or any copy beside the product image.
Do not allow the bottom strip to overpower the product.

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

The framed artwork must dominate the upper lifestyle/product image region.

It should occupy approximately 74-82% of the usable canvas width inside the upper region, depending on the room and camera angle.

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

FIXED BLACK FOOTER

Add an integrated collector-grade full-width matte-black footer across the bottom 21-23% of the square canvas.

The strip must feel like part of a premium Sports Cave campaign--not a separate cheap promotional banner.

Strip styling:

* Deep matte black.
* Subtle black material texture.
* Refined dark tonal variation.
* Very subtle metallic-gold detailing.
* Clean spacing.
* No excessive shine.
* No gradient, transparency, feathering, vignette or fade.
* No neon effects.
* No discount-store styling.

Separate the upper lifestyle/product image region and bottom strip with one thin restrained metallic-gold divider across the top edge of the black strip.

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

Use the full width of the bottom strip so the wording never looks squeezed.
Centre the complete text hierarchy horizontally and vertically inside the strip.
Keep "LIMITED TO 100 WORLDWIDE" together as one unified single-line headline.
Do not isolate or unnaturally enlarge "100".
Keep all text centred, correctly spelled and safely inside the mobile margins.
Do not compress, squash, stretch or use excessively narrow typography.
Do not break individual words.

The strip must feel urgent through restraint, spacing and hierarchy--not through oversized graphics or aggressive sales styling.

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
* The bottom scarcity strip feels premium rather than promotional.
* The overall image remains clear and persuasive at mobile size.

Avoid warped walls, impossible windows, crooked ceilings, bent furniture, floating objects, duplicate objects, plastic materials, fake luxury, excessive blur, overprocessed HDR, unrealistic reflections, malformed lighting, perfect artificial symmetry and any obvious AI-showroom appearance.

FINAL RESULT

Create a photorealistic, premium 1024 × 1024 Sports Cave Instant Experience cover featuring the exact uploaded framed artwork displayed prominently in a genuine high-end residential interior.

The final image must make the artwork feel like a real limited-edition collector piece already hanging in a desirable home, then use the restrained full-width black-and-gold bottom scarcity strip to make the viewer feel they should claim one of the 100 editions before it is gone."""


def build_default_instant_experience_cover_prompt_requirements(product_name, category, country):
    product_name = _clean_product_name(product_name)
    category = _normalise_option_label(category) or "selected sport category"
    country = _normalise_option_label(country) or "selected market"
    base_prompt = (
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
    return "\n\n".join(
        (
            base_prompt,
            build_instant_experience_fixed_opaque_footer_rules(),
            build_instant_experience_on_image_copy_fit_rules(),
        )
    )


SPORTS_CAVE_IE_CORE_IMAGE_QUALITY_RULES_V2 = """SPORTS_CAVE_IE_CORE_IMAGE_QUALITY_RULES_V2
INSTANT EXPERIENCE CORE IMAGE QUALITY - MANDATORY

VARIABLE PRECEDENCE

Apply requirements in this order:
1. Product fidelity and factual accuracy.
2. Exact user-provided wording and verified claims.
3. Explicit user-selected Instant Experience variables.
4. The active route layout contract.
5. These shared quality principles.
6. Route defaults and automatic creative choices.

An explicit selected value must be used exactly unless it conflicts with product preservation, factual accuracy or platform safety. Every Auto or Smart value must be resolved to one specific choice before the final standalone image prompt is returned. Never leave paired alternatives such as "room A or room B", "colour A or colour B", "morning or evening" or "beside or beneath" in the final prompt.

PRODUCT SOURCE-ASSET FIDELITY

- Treat the uploaded full-resolution Sports Cave product as one immutable photographic source asset.
- Isolate the complete product from its original surrounding wall, then composite that exact isolated product into the resolved environment.
- Retain the uploaded product pixels wherever technically possible instead of regenerating, approximating or reconstructing the artwork.
- Preserve every face, person, vehicle, colour, word, letter, number, name, title, signature graphic, badge, plaque, border, crop and edition detail.
- Preserve the exact frame colour, timber character, depth, thickness, mitred corners, proportions and landscape geometry.
- Keep all four outside frame edges visible.
- Apply natural perspective to the complete framed product only as one rigid rectangular object.
- Never redraw, repair, reinterpret, sharpen, recolour, mirror, crop, zoom, stretch, bend, taper, bow, squash, blur or warp the artwork or frame.
- Never change a visible edition number.
- Never add a frame to an unframed or solid-border product unless explicitly requested.
- Never create competing artwork.
- The installed product must look physically present in the room, never pasted on, floating, embedded in the wall or intersecting another object.

PROFESSIONAL INTERIOR-PHOTOGRAPHY REALISM

- Produce genuine premium interior photography, never AI art, CGI, illustration or a 3D render.
- Use physically possible room geometry, believable product scale and natural perspective matching the resolved camera and lens.
- Render plaster, timber, metal, fabric and glass with real material response, subtle imperfections and ordinary signs of a constructed room.
- Keep exposure, white balance and colour temperature consistent.
- Use restrained depth of field appropriate to the resolved lens and shot distance; the artwork and frame must remain readable.
- Preserve visible detail in the black frame without crushing it into the artwork.
- Use realistic contact shadows, ambient occlusion and object weight.
- No excessive HDR, artificial bloom, fake blur, heavy vignette, over-sharpening, plastic material, synthetic orange-and-teal grade, warped architecture, distorted furniture, duplicated objects, nonsensical decor, fake branding or unreadable environmental signage.

LIGHTING, GLASS AND MOUNTING PHYSICS

- Use premium natural side lighting around 4000-4700K, with one identifiable primary light source and no more than one secondary practical light source unless an explicit selected variable requires more.
- All wall shadows, frame shadows, highlights and reflections must agree with those light sources.
- Mount the frame with believable separation approximately 6-10 mm from the wall.
- Add a narrow contact shadow, a softer secondary wall shadow and a slightly stronger shadow beneath the frame, all following the room lighting direction.
- Preserve realistic frame depth, ambient occlusion, wall contact, natural material response and visible detail in the black timber frame.
- Framed products require clear gallery-style glass that is always visible, with subtle realistic partial reflections covering approximately 8-15% of the glass at approximately 3-6% opacity.
- Glass reflections must originate from visible or physically plausible room light sources, match the room's real light source, remain confined to the glass surface, stop at the inner frame edge and never continue across the timber frame or wall.
- For near-front views use extremely restrained broad reflections. For three-quarter views allow a slightly stronger reflection on the far side only.
- No glare may obscure faces, wording, vehicles, signatures, plaques, badges or edition details.
- Never allow full-surface glare, plastic haze, fake bloom, glowing edges, conflicting light directions, a uniform black drop shadow, or a product that looks flat, floating or digitally pasted on.
- A dramatic wall sunbeam without a corresponding physically consistent glass response is a realism failure.

ANTI-AI INTERIOR CONTROL

- Do not use the generic AI luxury-room formula of greige plaster, perfect walnut desk, black metal shelving, potted plant, stacked books, notebook, coffee cup, decorative pen and a dramatic diagonal golden-hour beam.
- Use no more than two secondary decorative objects unless an explicit selected variable genuinely requires more.
- Avoid perfectly spaced objects, symmetrical catalogue styling, repeated procedural textures, meaningless luxury clutter, oversized filler plants, generic object-filled shelving, competing furniture and impossibly pristine surfaces.
- The environment must remain quiet, believable and secondary to the Sports Cave product; it must not resemble a showroom, furniture catalogue or AI staging template."""


SPORTS_CAVE_IE_CORE_COPY_QUALITY_RULES_V2 = """SPORTS_CAVE_IE_CORE_COPY_QUALITY_RULES_V2
INSTANT EXPERIENCE CORE FACEBOOK COPY QUALITY - PREMIUM ROOM SYSTEM V4

Preserve the approved three-group response structure, the current three description options per route, the existing long-copy, Headline and CTA fields and the shared setup block.

Every copy option must:
- sound written by a knowledgeable human sports fan
- be product-specific and match the selected sport and market
- use only verified facts from the product name, supplied facts, visible artwork or an approved claim path
- give a clear reason to own the selected Sports Cave product
- use short, natural, mobile-readable lines with intentional blank-line breaks
- keep the description ending required by its archetype
- keep the CTA field separate from the long description copy
- preserve exact user-provided wording character-for-character when supplied

The three V4 routes are:
- Premium Scarcity — Right Angle
- Premium Scarcity — Straight On
- Premium Scarcity — Left Angle

All three routes share the same on-image headline and CTA system. Description 1 for every route must use CTA field Claim Your Edition so the copy table and image CTA remain aligned, but the long description text must follow its archetype ending.

Never invent history, achievements, product facts, athlete names, teams, rivalries, edition limits, remaining quantities, sales velocity, certificates, offers, delivery claims, discounts, restocks or availability.

When verified edition limit data is available, use it exactly. When it is not available, use evidence-gated non-numeric collector wording rather than fabricating 100 or a no-second-run claim.

The three route copy tables must use the same ordered product-aware description set: Description 1 — Legacy Standard, Description 2 — Framed Greatness and Description 3 — Choose a Side. The descriptions are driven by the selected product, not by camera angle or room background.

Each Description must preserve its required line-break structure, remain approximately 35-65 words and avoid dense paragraph blocks. Headlines must be concise, natural, emotionally clear on first read, product-specific where possible and no longer than the approved 4-6 word limit. Creative CTAs must follow the central Instant Experience CTA contract.

Reject generic AI retail language including: Elevate your space; Transform your room; Perfect addition; Ultimate tribute; Stunning masterpiece; Must-have; Wall worthy; Your wall deserves this; Don't miss this one; Another print; Once gone it stays gone; unleash; conversation starter; bring your walls to life; celebrate in style.

Before returning the response, silently compare the three description options. Rewrite any option that is generic, repetitive, fact-unsafe, weak on mobile, missing line breaks or mismatched to the product. Do not print candidates, scores or reasoning."""


SPORTS_CAVE_IE_CREATIVE_CTA_RULES_V1 = "SPORTS_CAVE_IE_CREATIVE_CTA_RULES_V1"


def build_instant_experience_creative_cta_rules(concept_id=None):
    approved_ctas = ", ".join(INSTANT_EXPERIENCE_APPROVED_CREATIVE_CTAS)
    approved_endings = "; ".join(
        f'{cta} -> "{ending}"'
        for cta, ending in INSTANT_EXPERIENCE_PRIMARY_TEXT_CTA_ENDINGS.items()
    )
    shared_rules = f"""{SPORTS_CAVE_IE_CREATIVE_CTA_RULES_V1}
INSTANT EXPERIENCE CREATIVE CTA CONTRACT - MANDATORY

- Every customer-facing Instant Experience creative CTA must be exactly one of: {approved_ctas}.
- The rule applies to every copy-table CTA, every on-image CTA, every standalone image-generation prompt, every exact-wording block, every copy correction and every package-ready copy value.
- For the V4 Premium Scarcity room system, Description 1 in all three routes must use CTA field Claim Your Edition.
- The long description text does not have to end with the CTA field; it must end according to its description archetype.
- Preserve CTA capitalisation by location: title case in the CTA field; render the on-image CTA exactly as CLAIM YOUR EDITION.
- The native Meta/Instant Experience platform button remains Shop Now. Never replace Shop Now with a creative CTA.
- Headlines remain route-specific and emotional; do not force CTA wording into every Headline.
- Silently correct any CTA outside this contract before returning the response. Do not expose rejected wording or reasoning."""

    if concept_id in {
        "premium_scarcity_right",
        "premium_scarcity_front",
        "premium_scarcity_left",
    }:
        route_rules = """PREMIUM SCARCITY ROOM CTA APPLICATION

- All three Instant Experience image routes use one consistent on-image CTA: CLAIM YOUR EDITION.
- Description 1 for every route must use CTA field Claim Your Edition so the copy table and image CTA remain aligned.
- Use verified edition limits and retirement/finality only when supplied by product metadata, explicit product title wording or approved claim path.
- Never invent remaining quantity, edition number, certificate, restock, delivery, discount, offer, athlete fact, rivalry fact or availability claim."""
    else:
        route_rules = """COPY-SET APPLICATION

- Generate only Premium Scarcity Right Angle, Premium Scarcity Straight On and Premium Scarcity Left Angle.
- The three routes share one CTA and scarcity headline system while varying camera, room profile, wall colour, cues and FOMO supporting line.
- Description 1 uses Claim Your Edition so its image wording and CTA field agree.
- Validate all completed rows before returning them. If a CTA is non-compliant, correct that route and description option only."""
    return f"{shared_rules}\n\n{route_rules}"


SPORTS_CAVE_IE_FIXED_OPAQUE_FOOTER_RULES_V1 = """SPORTS_CAVE_IE_FIXED_OPAQUE_FOOTER_RULES_V1
FIXED BLACK FOOTER — ABSOLUTE

Create one solid rectangular black footer panel anchored flush to the bottom edge of the 1024 x 1024 image.

The panel must:
- span the complete image width from the left edge to the right edge
- occupy approximately the bottom 21–23% of the canvas
- begin at one precise horizontal boundary
- have a perfectly straight, hard top edge
- be fully opaque
- use solid premium near-black or matte black
- completely conceal the room photograph behind it
- include the existing thin restrained gold separator along its top boundary
- retain the existing Sports Cave Instant Experience headline, supporting-line and CTA hierarchy

The footer must never:
- fade upward or blend into the room
- use a black gradient, transparency, feathering, vignette or soft edge
- reveal furniture, flooring, walls or any part of the room through the panel
- become a floating text overlay
- become a curved, angled or irregular shape
- extend inconsistently behind only part of the wording

A very subtle premium black material texture is permitted only when it remains visually opaque and does not weaken the clean rectangular panel. The room photograph occupies only the upper image area. The footer is a separate graphic panel with a clearly visible hard boundary and must match the established successful Sports Cave USA Instant Experience template.

COUNTRY-INVARIANT INSTANT EXPERIENCE TEMPLATE

Country selection may localise spelling, terminology, fan language and subtle room relevance only. Country must never change footer geometry, footer opacity, footer height, the gold separator, text hierarchy, typography scale, copy-length limits, safe margins, CTA style or the overall Instant Experience template. Australia, USA, UK, Canada, New Zealand and every other market use this identical professional footer system. Never create separate Australian layout behaviour.

Do not describe or render the footer as an overlay, fade, gradient, vignette or blended text area."""


SPORTS_CAVE_IE_ON_IMAGE_COPY_FIT_RULES_V1 = """SPORTS_CAVE_IE_ON_IMAGE_COPY_FIT_RULES_V1
INSTANT EXPERIENCE ON-IMAGE COPY FIT — ABSOLUTE

These limits apply only to wording rendered inside the Instant Experience cover image. They do not apply to Meta Primary Text, Meta headlines or Meta descriptions.

HEADLINE
- Use no more than six words and no more than 28 characters including spaces and punctuation.
- Keep the headline on exactly one line, centred inside the existing 64–72 px safe margins and at the existing Instant Experience headline scale.
- Never wrap, squeeze, condense, stretch or reduce the headline to an unusually small font.
- Never let the headline touch or approach the side edges; it must remain readable at mobile size.
- Do not force the complete product name into the on-image headline. Use a short product reference only when it fits naturally.
- If proposed wording exceeds either limit, shorten it before returning the standalone image-generation prompt while preserving the same emotional angle. Never solve overflow by shrinking typography.
- Valid: ONLY 100 WILL EVER EXIST
- Reject and shorten any longer product-specific scarcity wording before it reaches an image-generation prompt.

SUPPORTING LINE
- Use no more than 12 words and no more than 70 characters including spaces and punctuation.
- Express one clean supporting thought on exactly one line at the existing supporting-copy size.
- Never wrap or compress the supporting typography.

CTA
- Use no more than four words and no more than 24 characters including spaces and punctuation.
- Keep the CTA on exactly one line and use an approved collector-led action: CLAIM YOUR EDITION, SECURE YOUR EDITION, CLAIM THIS EDITION or SECURE THIS EDITION.
- Do not use a longer explanatory CTA.

The three existing covers may vary their wording only within their existing route contracts. Every on-image variation must satisfy these same one-line limits before an image-generation prompt is returned."""


def _normalise_instant_experience_on_image_line(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _instant_experience_on_image_line_errors(
    value,
    *,
    label,
    max_words,
    max_characters,
):
    raw = str(value or "")
    clean = _normalise_instant_experience_on_image_line(raw)
    errors = []
    if not clean:
        errors.append(f"{label} is required.")
        return errors
    if "\n" in raw or "\r" in raw:
        errors.append(f"{label} must remain on one line.")
    if len(clean.split()) > max_words:
        errors.append(f"{label} exceeds {max_words} words.")
    if len(clean) > max_characters:
        errors.append(f"{label} exceeds {max_characters} characters.")
    return errors


def instant_experience_on_image_headline_errors(headline):
    return tuple(
        _instant_experience_on_image_line_errors(
            headline,
            label="Instant Experience on-image headline",
            max_words=INSTANT_EXPERIENCE_ON_IMAGE_HEADLINE_MAX_WORDS,
            max_characters=INSTANT_EXPERIENCE_ON_IMAGE_HEADLINE_MAX_CHARACTERS,
        )
    )


def instant_experience_on_image_headline_is_valid(headline):
    return not instant_experience_on_image_headline_errors(headline)


def shorten_instant_experience_on_image_headline(
    headline,
    *,
    fallback="COLLECTOR EDITION",
):
    clean = _normalise_instant_experience_on_image_line(headline)
    if instant_experience_on_image_headline_is_valid(clean):
        return clean
    quantities = re.findall(r"\b\d[\d,]*\b", clean)
    if quantities:
        for candidate in (
            f"ONLY {quantities[-1]} WILL EVER EXIST",
            f"ONLY {quantities[-1]} EXIST",
        ):
            if instant_experience_on_image_headline_is_valid(candidate):
                return candidate
    clean_fallback = _normalise_instant_experience_on_image_line(fallback)
    if instant_experience_on_image_headline_is_valid(clean_fallback):
        return clean_fallback
    raise ValueError("A concise Instant Experience on-image headline could not be resolved.")


def validate_instant_experience_on_image_copy(headline, supporting_line, cta):
    errors = list(instant_experience_on_image_headline_errors(headline))
    errors.extend(
        _instant_experience_on_image_line_errors(
            supporting_line,
            label="Instant Experience on-image supporting line",
            max_words=INSTANT_EXPERIENCE_ON_IMAGE_SUPPORTING_MAX_WORDS,
            max_characters=INSTANT_EXPERIENCE_ON_IMAGE_SUPPORTING_MAX_CHARACTERS,
        )
    )
    errors.extend(
        _instant_experience_on_image_line_errors(
            cta,
            label="Instant Experience on-image CTA",
            max_words=INSTANT_EXPERIENCE_ON_IMAGE_CTA_MAX_WORDS,
            max_characters=INSTANT_EXPERIENCE_ON_IMAGE_CTA_MAX_CHARACTERS,
        )
    )
    clean_cta = _normalise_instant_experience_on_image_line(cta).upper()
    if clean_cta and clean_cta not in INSTANT_EXPERIENCE_APPROVED_ON_IMAGE_CTAS:
        errors.append("Instant Experience on-image CTA must use an approved collector-led action.")
    return tuple(errors)


def resolve_instant_experience_on_image_copy(headline, supporting_line, cta):
    resolved = {
        "headline_text": shorten_instant_experience_on_image_headline(headline),
        "supporting_line": _normalise_instant_experience_on_image_line(supporting_line),
        "cta_text": _normalise_instant_experience_on_image_line(cta).upper(),
    }
    errors = validate_instant_experience_on_image_copy(
        resolved["headline_text"],
        resolved["supporting_line"],
        resolved["cta_text"],
    )
    if errors:
        raise ValueError(" ".join(errors))
    return resolved


def build_instant_experience_fixed_opaque_footer_rules():
    return SPORTS_CAVE_IE_FIXED_OPAQUE_FOOTER_RULES_V1


def build_instant_experience_on_image_copy_fit_rules():
    return SPORTS_CAVE_IE_ON_IMAGE_COPY_FIT_RULES_V1


SPORTS_CAVE_IE_TYPOGRAPHY_RULES_V2 = "SPORTS_CAVE_IE_TYPOGRAPHY_RULES_V2"
SPORTS_CAVE_IE_SET_DIFFERENTIATION_RULES_V2 = "SPORTS_CAVE_IE_SET_DIFFERENTIATION_RULES_V2"


SPORTS_CAVE_IE_FINAL_REJECTION_GATE_V2 = """SPORTS_CAVE_IE_FINAL_REJECTION_GATE_V2
MANDATORY FINAL CORRECTION AND 10/10 QUALITY GATE

Inspect and correct the composed image before returning it. Reject and regenerate or correct the result when:
- the artwork or frame changed, looks regenerated or loses any outside frame edge
- the frame is warped, incorrectly proportioned, missing black timber depth or not rigid
- the product misses the required approximately 82-88% canvas width or complete-frame visibility
- the room does not match every resolved scene variable or looks like generic AI staging
- architecture, furniture, lighting direction, shadows or reflections are physically inconsistent
- glass is missing, unrealistic, crosses onto the frame or wall, or hides artwork details
- reflections obscure faces, wording, signatures, plaques, badges or edition details
- mounting gap, narrow contact shadow, softer secondary wall shadow or stronger lower frame shadow is missing
- frame and wall shadows conflict with the room lighting direction
- the frame floats, intersects objects, sits flush without believable 6-10 mm mounting depth, looks flat or looks digitally pasted on
- the overall result does not look like premium professional interior photography
- on-image wording is misspelled, incomplete, duplicated, re-punctuated, substituted or joined by extra text
- the on-image CTA is not exactly CLAIM YOUR EDITION
- a CTA field is outside the approved direct edition-acquisition family
- another route's Headline, CTA or supporting wording appears
- typography is generated inside the room, painted, engraved, embossed, glowing or physically attached to the wall instead of added as a deterministic flat post-production layer inside the fixed footer
- mobile readability, safe margins, visual hierarchy or product dominance is weak
- essential wording is not immediately readable in an approximately 256 x 256 preview
- any essential wording sits within 64 pixels of a canvas edge or touches the product, furniture or an architectural line
- scarcity quantity, numbering, certificate inclusion or another proof claim is not verified by supplied product data or a visible immutable source detail
- a secondary prop competes with the product
- the gold underline floats away from the edition number or becomes an arbitrary decorative dash
- the wall has horizontal lines, vertical lines, tile seams, panel joins, grooves, moulding, bricks, slab divisions, wallpaper stripes or unexplained shadow bands
- the fixed black footer fades into the room, is translucent, uses a gradient, has a soft or feathered edge, or reveals any room detail through it
- the fixed black footer is not full width, is not anchored flush to the bottom, lacks a clean horizontal top boundary, becomes irregular, or lacks the required thin restrained gold separator
- the fixed black footer falls outside approximately 21–23% of the canvas height
- the on-image headline exceeds six words or 28 characters, wraps, is squeezed, is stretched or is abnormally reduced
- the supporting line exceeds 12 words or 70 characters, wraps or becomes too small
- the on-image CTA exceeds four words or 24 characters, wraps or leaves the approved collector-led action family
- any footer wording approaches or crosses the 64–72 px safe margins
- Australia or another country changes the established country-invariant Instant Experience footer template
- the three routes use the same camera angle, identical wall colour, identical cue or effectively identical room composition
- the left route is merely a mirrored version of the right route
- the setting becomes a commercial sports bar, themed memorabilia wall, showroom or office lobby
- the output is not a true square or the final delivered file is not exactly 1024 x 1024 pixels

If native generation returns another square size, resize the approved square composition deterministically to exactly 1024 x 1024 sRGB before delivery. Never stretch a non-square image; regenerate or correct its square composition first.

When footer geometry or copy fit is the only failure, correct only the footer and wording fit. Preserve the product, room, camera angle, lighting, typography character and every other successful element. Shorten overlong wording; never shrink, condense or stretch the existing typography to force it into the footer.

Silently assess the finished route against this production rubric: product fidelity 25 points, photographic realism 20, route distinctness 15, exact typography and wording 15, mobile hierarchy and product prominence 10, copy quality 10, brand and factual compliance 5. Revise every hard failure and anything below the intended production-ready 10/10 standard. Do not print the score, checklist result or reasoning. The workflow must correct failures, not merely claim the checks passed."""



INSTANT_EXPERIENCE_ROUTE_CONFIGS_V4 = (
    {
        "concept_id": "premium_scarcity_right",
        "route_key": "premium_scarcity_right",
        "group_heading": "GROUP 1 — PREMIUM SCARCITY — RIGHT ANGLE",
        "prompt_heading": "IMAGE GENERATION PROMPT",
        "route": "Premium Scarcity — Right Angle",
        "supporting_label": "Slight right-angle product photograph",
        "copy_row": "Premium Scarcity — Right Angle Copy Variation 1",
        "purpose": "Create a premium scarcity hero from a slight right-angle residential product photograph while preserving the exact supplied framed artwork.",
        "camera_role": "right",
        "camera_side": "camera 4-6 degrees to the viewer's right of centre, looking back naturally toward the product",
        "camera_instruction": "Position the camera approximately 4-6 degrees to the viewer's right of centre. Look back naturally toward the product. Show a restrained amount of the frame's right-hand timber return and mounting depth. Keep verticals straight. Preserve the product's proportions. No fisheye effect, dramatic perspective or noticeably larger artwork side. The angle must look like a genuine room photograph, not a stylised product render.",
        "fomo_line": "Once they're claimed, this edition retires forever.",
        "default_room_profile": "refined masculine collector lounge",
        "room_type": "refined masculine collector lounge",
        "wall_colour": "warm mushroom mineral plaster",
        "wall_material": "fine seamless mineral plaster",
        "primary_cue": "architectural doorway",
        "secondary_cue": "cropped dark leather chair",
        "camera_height": "eye level with the centre of the frame",
        "shot_distance": "large framed-product dominance, with the product approximately 82-88% of canvas width",
        "lens": "70mm natural interior-photography character",
        "lighting": "soft side daylight from camera-left with restrained ambient fill",
        "time_of_day": "quiet late morning",
        "overlay_position": "fixed opaque footer across the bottom 21–23% only",
        "product_position": "dominant and centred in the upper 77–79% room scene",
        "architectural_cue": "architectural doorway near the outer scene edge",
        "composition": "1024 x 1024 square, upper photographed room scene approximately 77–79%, fixed opaque black footer approximately 21–23%",
        "typography_mode": "premium_room_panel",
    },
    {
        "concept_id": "premium_scarcity_front",
        "route_key": "premium_scarcity_front",
        "group_heading": "GROUP 2 — PREMIUM SCARCITY — STRAIGHT ON",
        "prompt_heading": "IMAGE GENERATION PROMPT",
        "route": "Premium Scarcity — Straight On",
        "supporting_label": "Straight-on product photograph",
        "copy_row": "Premium Scarcity — Straight On Copy Variation 1",
        "purpose": "Create the clearest and most direct scarcity hero from a predominantly straight-on residential product photograph.",
        "camera_role": "front",
        "camera_side": "predominantly straight-on camera with maximum 0-2 degree natural offset",
        "camera_instruction": "Use a predominantly straight-on view with a maximum natural offset of 0-2 degrees. Keep the complete product geometrically balanced. Avoid artificial showroom symmetry by placing the room cue primarily toward one outer edge. This must be the clearest and most direct scarcity hero of the three.",
        "fomo_line": "When the final one is claimed, it's gone for good.",
        "default_room_profile": "refined masculine collector lounge",
        "room_type": "refined masculine collector lounge",
        "wall_colour": "refined warm taupe matte plaster",
        "wall_material": "premium seamless matte-painted plaster",
        "primary_cue": "partial bookcase",
        "secondary_cue": "timber console",
        "camera_height": "eye level and geometrically balanced",
        "shot_distance": "large framed-product dominance, with the product approximately 82-88% of canvas width",
        "lens": "75mm natural interior-photography character",
        "lighting": "soft daylight from camera-right with slightly brighter room falloff",
        "time_of_day": "clean midday daylight",
        "overlay_position": "fixed opaque footer across the bottom 21–23% only",
        "product_position": "dominant and centred in the upper 77–79% room scene",
        "architectural_cue": "partial bookcase near one outer edge",
        "composition": "1024 x 1024 square, upper photographed room scene approximately 77–79%, fixed opaque black footer approximately 21–23%",
        "typography_mode": "premium_room_panel",
    },
    {
        "concept_id": "premium_scarcity_left",
        "route_key": "premium_scarcity_left",
        "group_heading": "GROUP 3 — PREMIUM SCARCITY — LEFT ANGLE",
        "prompt_heading": "IMAGE GENERATION PROMPT",
        "route": "Premium Scarcity — Left Angle",
        "supporting_label": "Slight left-angle product photograph",
        "copy_row": "Premium Scarcity — Left Angle Copy Variation 1",
        "purpose": "Create a complementary scarcity hero from a slight left-angle residential product photograph without mirroring the right-angle route.",
        "camera_role": "left",
        "camera_side": "camera 4-6 degrees to the viewer's left of centre, looking back naturally toward the product",
        "camera_instruction": "Position the camera approximately 4-6 degrees to the viewer's left of centre. Look back naturally toward the product. Show a restrained amount of the frame's left-hand timber return and mounting depth. Keep verticals straight. Preserve the product's original dimensions and proportions. The angle must complement Route 1 without appearing artificially mirrored.",
        "fomo_line": "Released once. When they're gone, they stay gone.",
        "default_room_profile": "refined masculine collector lounge",
        "room_type": "refined masculine collector lounge",
        "wall_colour": "soft greige limewash",
        "wall_material": "subtle seamless limewash",
        "primary_cue": "window edge with natural curtains",
        "secondary_cue": "partial lounge chair",
        "camera_height": "eye level with a natural residential viewpoint",
        "shot_distance": "large framed-product dominance, with the product approximately 82-88% of canvas width",
        "lens": "70mm natural interior-photography character",
        "lighting": "soft daylight from camera-right with quieter peripheral furniture",
        "time_of_day": "soft afternoon daylight",
        "overlay_position": "fixed opaque footer across the bottom 21–23% only",
        "product_position": "dominant and centred in the upper 77–79% room scene",
        "architectural_cue": "window edge with natural curtains near the outer scene edge",
        "composition": "1024 x 1024 square, upper photographed room scene approximately 77–79%, fixed opaque black footer approximately 21–23%",
        "typography_mode": "premium_room_panel",
    },
)

INSTANT_EXPERIENCE_STANDARD_VISUALS = INSTANT_EXPERIENCE_ROUTE_CONFIGS_V4

INSTANT_EXPERIENCE_ROOM_PROFILES_V4 = {
    "collector_lounge": {
        "label": "refined masculine collector lounge or media room",
        "room_type": "refined masculine collector lounge",
        "materials": "black timber, dark leather, restrained stone and quiet architectural detailing",
        "baseline_weight": 50,
    },
    "heritage_study": {
        "label": "warm vintage study or heritage collector room",
        "room_type": "warm vintage study",
        "materials": "walnut timber, cognac leather, muted antique-stone details and quiet side lighting",
        "baseline_weight": 25,
    },
    "neutral_living": {
        "label": "premium neutral living room",
        "room_type": "premium neutral living room",
        "materials": "warm timber, natural curtains, soft greige plaster and welcoming daylight",
        "baseline_weight": 15,
    },
    "modern_man_cave": {
        "label": "tasteful modern man cave",
        "room_type": "tasteful modern man cave",
        "materials": "deep warm charcoal, partial leather seating, black timber and controlled residential contrast",
        "baseline_weight": 10,
    },
}

INSTANT_EXPERIENCE_WALL_PALETTES_V4 = {
    "default": (
        ("fine seamless mineral plaster", "warm mushroom mineral plaster"),
        ("premium seamless matte-painted plaster", "refined warm taupe matte plaster"),
        ("subtle seamless limewash", "soft greige limewash"),
    ),
    "dark": (
        ("premium seamless matte-painted plaster", "restrained warm charcoal"),
        ("smooth seamless stone-toned render", "muted stone grey"),
        ("fine seamless mineral plaster", "dark mushroom"),
    ),
    "heritage": (
        ("fine seamless mineral plaster", "muted olive-grey"),
        ("smooth seamless stone-toned render", "antique-stone taupe"),
        ("subtle seamless limewash", "warm greige limewash"),
    ),
    "neutral": (
        ("smooth seamless stone-toned render", "light greige"),
        ("fine seamless mineral plaster", "warm stone"),
        ("subtle seamless limewash", "soft taupe limewash"),
    ),
}

INSTANT_EXPERIENCE_PRIMARY_CUES_V4 = (
    "architectural doorway",
    "cropped room corner",
    "window edge with natural curtains",
    "partial bookcase",
    "low media cabinet",
    "open-plan room opening",
    "restrained collector cabinet",
    "partial timber shelving",
)

INSTANT_EXPERIENCE_SECONDARY_CUES_V4 = (
    "cropped leather sofa",
    "partial lounge chair",
    "timber console",
    "desk edge",
    "restrained lamp",
    "curtain edge",
    "low shelf",
    "small rug section",
    "softly blurred furniture edge",
)


INSTANT_EXPERIENCE_DIFFERENTIATION_FIELDS = (
    "room_type",
    "wall_colour",
    "wall_material",
    "camera_side",
    "shot_distance",
    "lighting",
    "overlay_position",
    "architectural_cue",
    "primary_cue",
    "secondary_cue",
)


def _contains_any_word(text, words):
    haystack = str(text or "").casefold()
    for word in words:
        needle = str(word or "").strip().casefold()
        if not needle:
            continue
        if needle.isdigit():
            if needle in haystack:
                return True
            continue
        if re.search(r"[^a-z0-9]", needle):
            if needle in haystack:
                return True
            continue
        if re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", haystack):
            return True
    return False


def _instant_experience_seed(*parts):
    source = "|".join(str(part or "") for part in parts)
    return int(hashlib.sha256(source.encode("utf-8")).hexdigest()[:12], 16)


def _verified_edition_limit_from_text(product_name):
    text = str(product_name or "")
    patterns = (
        r"\bonly\s+(\d{1,4})\s+(?:will\s+ever\s+exist|exist|made|editions|worldwide)\b",
        r"\blimited\s+to\s+(\d{1,4})\s+(?:editions|worldwide|made)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return _positive_int_or_none(match.group(1))
    return None


def resolve_instant_experience_product_context(
    product_name,
    category,
    *,
    product_metadata=None,
    campaign_moment=None,
):
    metadata = dict(product_metadata or {})
    collections = [
        _normalise_option_label(value)
        for value in metadata.get("collections", [])
        if _normalise_option_label(value)
    ]
    product_sport = (
        _normalise_option_label(metadata.get("product_sport"))
        or _normalise_option_label(category)
        or "safe universal fallback"
    )
    if product_sport.casefold() in {"select category", "other"}:
        product_sport = "safe universal fallback"
    combined = " ".join(
        [
            str(product_name or ""),
            str(product_sport or ""),
            str(metadata.get("product_type") or ""),
            " ".join(collections),
        ]
    )
    era = "current"
    if _contains_any_word(
        combined,
        (
            "historic",
            "history",
            "heritage",
            "legend",
            "legacy",
            "classic",
            "vintage",
            "retro",
            "nostalgic",
            "nostalgia",
            "retired",
            "farewell",
            "tribute",
            "197",
            "198",
            "199",
        ),
    ):
        era = "historic"
    elif _contains_any_word(combined, ("modern", "current", "contemporary", "rookie", "2024", "2025", "2026")):
        era = "modern"

    mood = "clean"
    if _contains_any_word(combined, ("rivalry", "rival", " vs ", "versus", "dark", "aggressive", "battle", "duel")):
        mood = "rivalry"
    elif _contains_any_word(combined, ("celebration", "champion", "title", "trophy", "win", "victory")):
        mood = "celebratory"
    elif _contains_any_word(combined, ("heritage", "legacy", "legend", "nostalgic", "nostalgia")):
        mood = "heritage"
    elif _contains_any_word(combined, ("energy", "energetic", "dynamic", "modern")):
        mood = "energetic"

    moment = normalize_campaign_moment(campaign_moment)
    context_hint = "standard collector campaign"
    if campaign_moment_is_active(moment):
        context_hint = _normalise_option_label(moment.get("type") or moment.get("name")) or context_hint
    if _contains_any_word(combined + " " + context_hint, ("gift", "gifting", "father", "mother", "christmas")):
        context_hint = "gifting"

    edition_limit = _positive_int_or_none(metadata.get("edition_limit"))
    edition_limit_source = _normalise_option_label(metadata.get("edition_limit_source"))
    if edition_limit is None:
        edition_limit = _verified_edition_limit_from_text(product_name)
        if edition_limit:
            edition_limit_source = "explicit product title"
    if edition_limit is None and product_sport == "Baseball":
        edition_limit = 100
        edition_limit_source = "approved Baseball Instant Experience claim path"

    return {
        "product_sport": product_sport,
        "product_era": era,
        "artwork_mood": mood,
        "campaign_context": context_hint,
        "edition_limit": edition_limit,
        "edition_limit_source": edition_limit_source if edition_limit else "",
        "collections": collections,
    }


def _metadata_bool(metadata, *keys):
    for key in keys:
        if key not in metadata:
            continue
        value = metadata.get(key)
        if isinstance(value, bool):
            return value
        clean = str(value or "").strip().casefold()
        if clean in {"1", "true", "yes", "y", "verified", "included", "numbered"}:
            return True
        if clean in {"0", "false", "no", "n", "not verified", "unknown"}:
            return False
    return False


def _metadata_text(metadata, *keys):
    for key in keys:
        value = _normalise_option_label(metadata.get(key))
        if value:
            return value
    return ""


def _metadata_list(metadata, *keys):
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, str):
            parts = re.split(r"\s*(?:,|;|\||/|\band\b|\bvs\.?\b|\bversus\b)\s*", value, flags=re.IGNORECASE)
        elif isinstance(value, (list, tuple, set)):
            parts = list(value)
        else:
            parts = []
        cleaned = [
            _normalise_option_label(item.get("name") if isinstance(item, dict) else item)
            for item in parts
        ]
        cleaned = [item for item in cleaned if item]
        if cleaned:
            return cleaned[:4]
    return []


def _title_side_candidates(product_name):
    title = str(product_name or "")
    for separator in (" vs ", " vs. ", " versus ", " v "):
        if separator in title.casefold():
            parts = re.split(separator, title, maxsplit=1, flags=re.IGNORECASE)
            return [_normalise_option_label(part) for part in parts if _normalise_option_label(part)][:2]
    if " & " in title:
        parts = title.split(" & ", 1)
        return [_normalise_option_label(part) for part in parts if _normalise_option_label(part)][:2]
    return []


def _single_word_name(name):
    clean = _normalise_option_label(name)
    if not clean:
        return ""
    words = clean.replace("—", " ").replace("-", " ").split()
    return words[-1] if len(words) > 1 else clean


def _classified_description_value(value, allowed, fallback):
    clean = _normalise_option_label(value)
    for allowed_value in allowed:
        if clean.casefold() == allowed_value.casefold():
            return allowed_value
    return fallback


INSTANT_EXPERIENCE_ARTWORK_TYPES = (
    "Single athlete",
    "Two connected legends",
    "Direct rivalry",
    "Two-team rivalry",
    "Teammates or partnership",
    "Multi-athlete legacy",
    "Team or championship",
    "Historic sporting moment",
    "Motorsport rivalry",
    "Generic sport or collector artwork",
)

INSTANT_EXPERIENCE_RELATIONSHIP_TYPES = (
    "Inspiration or succession",
    "Shared standard",
    "Teammates",
    "Rivals",
    "Opposing teams",
    "Same-era legends",
    "Different-era legends",
    "Shared achievement",
    "Single-subject",
    "Unknown",
)


def resolve_instant_experience_description_context(
    product_name,
    category,
    *,
    product_metadata=None,
    campaign_moment=None,
    country="",
):
    metadata = dict(product_metadata or {})
    base_context = resolve_instant_experience_product_context(
        product_name,
        category,
        product_metadata=metadata,
        campaign_moment=campaign_moment,
    )
    athletes = _metadata_list(
        metadata,
        "athlete_names",
        "athletes",
        "featured_athletes",
        "player_names",
        "drivers",
    )
    teams = _metadata_list(
        metadata,
        "team_names",
        "teams",
        "featured_teams",
        "clubs",
    )
    title_sides = _title_side_candidates(product_name)
    side_a = _metadata_text(metadata, "side_a", "athlete_a", "team_a")
    side_b = _metadata_text(metadata, "side_b", "athlete_b", "team_b")
    if not side_a and title_sides:
        side_a = title_sides[0]
    if not side_b and len(title_sides) > 1:
        side_b = title_sides[1]
    if not athletes and side_a and side_b and not teams:
        athletes = [side_a, side_b]

    featured_moment = _metadata_text(
        metadata,
        "featured_moment",
        "moment",
        "historic_moment",
        "achievement",
        "event",
    )
    explicit_artwork_type = metadata.get("artwork_type")
    explicit_relationship = metadata.get("relationship_type")
    relationship = _classified_description_value(
        explicit_relationship,
        INSTANT_EXPERIENCE_RELATIONSHIP_TYPES,
        "",
    )
    if not relationship:
        combined = " ".join(
            [
                str(product_name or ""),
                " ".join(base_context.get("collections") or []),
                str(metadata.get("creative_brief") or ""),
                str(metadata.get("relationship") or ""),
            ]
        )
        if _contains_any_word(combined, ("rivalry", "rivals", "opposing", "vs", "versus", "derby")):
            relationship = "Opposing teams" if len(teams) >= 2 else "Rivals"
        elif _contains_any_word(combined, ("teammates", "partnership", "duo", "together")):
            relationship = "Teammates"
        elif _contains_any_word(combined, ("succession", "inspired", "inspiration", "carried forward")):
            relationship = "Inspiration or succession"
        elif len(athletes) == 1:
            relationship = "Single-subject"
        elif len(athletes) >= 2:
            relationship = "Shared standard"
        else:
            relationship = "Unknown"

    artwork_type = _classified_description_value(
        explicit_artwork_type,
        INSTANT_EXPERIENCE_ARTWORK_TYPES,
        "",
    )
    sport_lower = str(base_context.get("product_sport") or "").casefold()
    if not artwork_type:
        if ("motorsport" in sport_lower or "v8" in sport_lower or "f1" in sport_lower) and relationship in {"Rivals", "Opposing teams"}:
            artwork_type = "Motorsport rivalry"
        elif relationship == "Rivals":
            artwork_type = "Direct rivalry"
        elif relationship == "Opposing teams":
            artwork_type = "Two-team rivalry"
        elif relationship == "Teammates":
            artwork_type = "Teammates or partnership"
        elif relationship in {"Inspiration or succession", "Shared standard", "Same-era legends", "Different-era legends"} and len(athletes) >= 2:
            artwork_type = "Two connected legends"
        elif len(athletes) == 1:
            artwork_type = "Single athlete"
        elif len(athletes) > 2:
            artwork_type = "Multi-athlete legacy"
        elif teams:
            artwork_type = "Team or championship"
        elif featured_moment or base_context.get("product_era") == "historic":
            artwork_type = "Historic sporting moment"
        else:
            artwork_type = "Generic sport or collector artwork"

    pronoun_mode = _metadata_text(metadata, "pronoun_mode", "pronouns", "gender").casefold()
    if pronoun_mode in {"male", "man", "he", "he/his", "his"}:
        pronoun_mode = "male"
    elif pronoun_mode in {"female", "woman", "she", "she/her", "her"}:
        pronoun_mode = "female"
    elif len(athletes) != 1 or artwork_type not in {"Single athlete"}:
        pronoun_mode = "plural_or_neutral"
    else:
        pronoun_mode = "neutral"

    is_numbered = _metadata_bool(
        metadata,
        "is_numbered",
        "numbered",
        "numbering_verified",
        "hand_numbered",
        "numbered_certificate",
    )
    retires_when_sold_out = _metadata_bool(
        metadata,
        "retires_when_sold_out",
        "retirement_verified",
        "permanent_retirement_verified",
        "sold_out_retires",
    )
    no_reprint_verified = _metadata_bool(
        metadata,
        "no_reprint_verified",
        "no_reprint",
        "no_second_run_verified",
        "no_second_run",
    )
    return {
        "PRODUCT_NAME": _clean_product_name(product_name),
        "SPORT": base_context.get("product_sport") or _normalise_option_label(category),
        "ATHLETE_NAMES": athletes,
        "TEAM_NAMES": teams,
        "SIDE_A": side_a or (teams[0] if teams else athletes[0] if athletes else ""),
        "SIDE_B": side_b or (teams[1] if len(teams) > 1 else athletes[1] if len(athletes) > 1 else ""),
        "FEATURED_MOMENT": featured_moment,
        "ERA": _metadata_text(metadata, "era") or base_context.get("product_era") or "Unknown",
        "ARTWORK_TYPE": artwork_type,
        "RELATIONSHIP_TYPE": relationship,
        "PRONOUN_MODE": pronoun_mode,
        "EDITION_LIMIT": base_context.get("edition_limit"),
        "IS_NUMBERED": bool(is_numbered),
        "RETIRES_WHEN_SOLD_OUT": bool(retires_when_sold_out),
        "NO_REPRINT_VERIFIED": bool(no_reprint_verified),
        "CAMPAIGN_MARKET": _normalise_option_label(country),
        "SCARCITY_VERIFIED": bool(base_context.get("edition_limit")),
        "EDITION_LIMIT_SOURCE": base_context.get("edition_limit_source") or "",
    }


def _edition_exists_line(context):
    limit = _positive_int_or_none(context.get("EDITION_LIMIT"))
    if limit:
        noun = "exists" if limit == 1 else "exist"
        return f"Only {limit} {noun}."
    return "A limited collector release."


def _edition_limited_line(context):
    limit = _positive_int_or_none(context.get("EDITION_LIMIT"))
    if limit:
        return f"Limited to {limit} worldwide."
    return "A limited collector release."


def _scarcity_second_line(context):
    if context.get("RETIRES_WHEN_SOLD_OUT") or context.get("NO_REPRINT_VERIFIED"):
        return "When they're gone, they're gone."
    return "Made for fans who know why it matters."


def _representation_line(context):
    artwork_type = context.get("ARTWORK_TYPE")
    relationship = context.get("RELATIONSHIP_TYPE")
    sport = str(context.get("SPORT") or "").casefold()
    if "motorsport" in sport or artwork_type == "Motorsport rivalry":
        return "It's a reminder of what real racing felt like."
    if artwork_type in {"Direct rivalry", "Two-team rivalry"} or relationship in {"Rivals", "Opposing teams"}:
        return "It's a reminder of why the rivalry still matters."
    if artwork_type == "Historic sporting moment":
        return "It's a reminder of the night everything changed."
    if context.get("ERA") == "historic":
        return "It's a reminder of what that era meant."
    if relationship in {"Inspiration or succession", "Shared standard", "Different-era legends"}:
        return "It's a reminder of the standard they left behind."
    return "It's a reminder of what greatness looks like."


def _legacy_standard_opening(context):
    artwork_type = context.get("ARTWORK_TYPE")
    relationship = context.get("RELATIONSHIP_TYPE")
    sport = str(context.get("SPORT") or "").casefold()
    athlete = (context.get("ATHLETE_NAMES") or [""])[0]
    team = (context.get("TEAM_NAMES") or [""])[0]
    moment = context.get("FEATURED_MOMENT")
    if artwork_type == "Single athlete":
        if context.get("PRONOUN_MODE") == "male":
            return ["He didn't follow the standard.", "He set it.", "Then raised it again.", "That's why they still remember."]
        if context.get("PRONOUN_MODE") == "female":
            return ["She didn't follow the standard.", "She set it.", "Then raised it again.", "That's why they still remember."]
        subject = _single_word_name(athlete) or athlete or "The name"
        return [f"{subject} didn't follow the standard.", f"{subject} set it.", "Then raised it again.", "That's why they still remember."]
    if "motorsport" in sport or artwork_type == "Motorsport rivalry":
        return ["They didn't race for second.", "They raced to be remembered.", "One corner.", "One rivalry that still lives."]
    if artwork_type in {"Direct rivalry", "Two-team rivalry"} or relationship in {"Rivals", "Opposing teams"}:
        return ["They didn't connect.", "They collided.", "One drew the line.", "The other refused to step back."]
    if artwork_type == "Teammates or partnership" or relationship == "Teammates":
        return ["They didn't just share the field.", "They lifted the standard.", "One created the opening.", "The other made it count."]
    if artwork_type == "Team or championship":
        return ["They didn't wait for history.", "They took it.", "One team.", "One moment that never left the fans."]
    if artwork_type == "Historic sporting moment" or moment:
        return ["It wasn't just another game.", "It became the moment.", "The crowd remembers.", "The sport never forgot."]
    if relationship in {"Inspiration or succession", "Different-era legends"}:
        return ["Different eras.", "The same standard.", "One showed what was possible.", "The other kept pushing it."]
    return ["They weren't defined by rivalry.", "They were connected by the standard.", "One set it.", "One refused to lower it."]


def _framed_greatness_hook(context):
    artwork_type = context.get("ARTWORK_TYPE")
    relationship = context.get("RELATIONSHIP_TYPE")
    sport = str(context.get("SPORT") or "").casefold()
    if "motorsport" in sport or artwork_type == "Motorsport rivalry":
        return "The race ended. The rivalry never did."
    if artwork_type in {"Direct rivalry", "Two-team rivalry"} or relationship in {"Rivals", "Opposing teams"}:
        return "Rivalries don't disappear. They get framed."
    if artwork_type == "Historic sporting moment":
        return "Some moments never leave you. This one gets framed."
    return "Greatness doesn't fade. It gets framed."


def _collector_identity_lines(context):
    if context.get("IS_NUMBERED"):
        first = "A numbered collector drop."
    else:
        first = "A limited collector release."
    artwork_type = context.get("ARTWORK_TYPE")
    relationship = context.get("RELATIONSHIP_TYPE")
    sport = str(context.get("SPORT") or "").casefold()
    if "motorsport" in sport or artwork_type == "Motorsport rivalry":
        second = "Made for the fans who remember what real racing felt like."
    elif artwork_type in {"Direct rivalry", "Two-team rivalry"} or relationship in {"Rivals", "Opposing teams"}:
        second = "Made for the fans who never stopped choosing a side."
    elif context.get("FEATURED_MOMENT"):
        second = "Made for the fans who know what this moment means."
    else:
        second = "Made for the fans who know why this name still matters."
    return [first, second]


def _framed_scarcity_lines(context):
    if context.get("RETIRES_WHEN_SOLD_OUT") or context.get("NO_REPRINT_VERIFIED"):
        lines = ["Once this edition sells out, it's gone."]
        if context.get("NO_REPRINT_VERIFIED"):
            lines.extend(["No reprint.", "No second run."])
        else:
            lines.extend(["Made for serious collectors.", "Built for the fans who know why it matters."])
        return lines
    if context.get("EDITION_LIMIT"):
        return [_edition_limited_line(context), "Made for serious collectors.", "Built for the fans who know why it matters."]
    return ["A limited collector release.", "Made for serious collectors.", "Built for the fans who know why it matters."]


def _choose_a_side_copy(context):
    athlete_names = context.get("ATHLETE_NAMES") or []
    team_names = context.get("TEAM_NAMES") or []
    side_a = context.get("SIDE_A") or (team_names[0] if team_names else athlete_names[0] if athlete_names else "")
    side_b = context.get("SIDE_B") or (team_names[1] if len(team_names) > 1 else athlete_names[1] if len(athlete_names) > 1 else "")
    athlete_a = _single_word_name(athlete_names[0]) if athlete_names else side_a
    athlete_b = _single_word_name(athlete_names[1]) if len(athlete_names) > 1 else side_b
    moment = context.get("FEATURED_MOMENT")
    artwork_type = context.get("ARTWORK_TYPE")
    relationship = context.get("RELATIONSHIP_TYPE")
    sport = str(context.get("SPORT") or "").casefold()
    scarcity = _edition_exists_line(context)
    ownership_action = "Choose it…" if relationship in {"Rivals", "Opposing teams"} else "Claim it…"
    if "motorsport" in sport or artwork_type == "Motorsport rivalry":
        if side_a and side_b:
            return "\n\n".join(
                [
                    f"{side_a} or {side_b}?",
                    "No middle ground.",
                    "One mountain.\nTwo names that still divide the fans.",
                    scarcity,
                    "Choose it…\nor watch it end up on someone else's wall.",
                ]
            )
        return "\n\n".join(
            [
                "Remember when racing felt like this?",
                "You do.",
                "Raw speed.\nNo second chances.",
                scarcity,
                "Claim it…\nor watch it end up on someone else's wall.",
            ]
        )
    if artwork_type in {"Direct rivalry", "Two-team rivalry"} or relationship in {"Rivals", "Opposing teams"}:
        first_question = f"{side_a} or {side_b}?" if side_a and side_b else "Which side are you on?"
        second_question = f"{athlete_a}… or {athlete_b}?" if athlete_a and athlete_b else "You know the rivalry."
        return "\n\n".join(
            [
                first_question,
                "No middle ground.",
                second_question,
                "You already picked a side.",
                scarcity,
                f"{ownership_action}\nor watch it end up on someone else's wall.",
            ]
        )
    if relationship in {"Inspiration or succession", "Shared standard", "Same-era legends", "Different-era legends"} and len(athlete_names) >= 2:
        return "\n\n".join(
            [
                f"{_single_word_name(athlete_names[0])} or {_single_word_name(athlete_names[1])}?",
                "Wrong question.",
                "One set the standard.\nThe other carried it forward.",
                "You know what they meant.",
                scarcity,
                "Claim it…\nor watch it end up on someone else's wall.",
            ]
        )
    if artwork_type == "Single athlete":
        subject = _single_word_name(athlete_names[0]) if athlete_names else _clean_product_name(context.get("PRODUCT_NAME"))
        if moment:
            moment_block = f"{moment}?\n\nNo explanation needed."
        else:
            moment_block = "You know the standard.\n\nNo explanation needed."
        return "\n\n".join(
            [
                f"{subject}?",
                "You remember." if moment else "You know the name.",
                moment_block,
                scarcity,
                "Claim it…\nor watch it end up on someone else's wall.",
            ]
        )
    if artwork_type == "Team or championship":
        subject = team_names[0] if team_names else side_a or _clean_product_name(context.get("PRODUCT_NAME"))
        moment_line = moment or str(context.get("ERA") or "That era")
        return "\n\n".join(
            [
                f"{subject}?",
                "You never stopped believing.",
                f"{moment_line}?",
                "You still remember where you were.",
                scarcity,
                "Claim it…\nor watch it end up on someone else's wall.",
            ]
        )
    if artwork_type == "Historic sporting moment":
        moment_line = moment or "That moment"
        return "\n\n".join(
            [
                "Remember where you were?",
                "You do.",
                f"{moment_line}?",
                "Some moments never leave.",
                scarcity,
                "Claim it…\nor watch it end up on someone else's wall.",
            ]
        )
    return "\n\n".join(
        [
            "You know why it matters?",
            "You do.",
            "The product tells the story.",
            "No explanation needed.",
            scarcity,
            "Claim it…\nor watch it end up on someone else's wall.",
        ]
    )


def build_instant_experience_description_variants(description_context):
    context = dict(description_context or {})
    legacy_copy = "\n".join(_legacy_standard_opening(context))
    legacy_copy = "\n\n".join(
        [
            legacy_copy,
            "This isn't wall art.\n" + _representation_line(context),
            _edition_limited_line(context) + "\n" + _scarcity_second_line(context),
            "Secure yours.",
        ]
    )
    collector_lines = _collector_identity_lines(context)
    framed_copy = "\n\n".join(
        [
            _framed_greatness_hook(context),
            "\n".join(collector_lines),
            "\n".join(_framed_scarcity_lines(context)),
            "Secure yours.",
        ]
    )
    choose_copy = _choose_a_side_copy(context)
    copies = (legacy_copy, framed_copy, choose_copy)
    return {
        "description_variants": [
            {
                "key": variant["key"],
                "label": variant["label"],
                "copy": copies[index],
            }
            for index, variant in enumerate(INSTANT_EXPERIENCE_DESCRIPTION_VARIANTS)
        ]
    }


def validate_instant_experience_description_variants(payload):
    variants = list((payload or {}).get("description_variants") or [])
    if len(variants) != len(INSTANT_EXPERIENCE_DESCRIPTION_VARIANTS):
        return False
    copies = []
    for expected, variant in zip(INSTANT_EXPERIENCE_DESCRIPTION_VARIANTS, variants):
        if variant.get("key") != expected["key"]:
            return False
        if variant.get("label") != expected["label"]:
            return False
        copy = _preserve_multiline_text(variant.get("copy"))
        if not copy.strip() or re.search(r"\{\{[^}]+\}\}", copy):
            return False
        copies.append(copy.strip())
    return len(set(copies)) == len(copies)


def build_instant_experience_description_generation_prompt(description_context):
    context = dict(description_context or {})
    preview = build_instant_experience_description_variants(context)
    context_json = json.dumps(context, ensure_ascii=False, indent=2)
    schema_json = json.dumps(
        {
            "description_variants": [
                {"key": item["key"], "label": item["label"], "copy": "..."}
                for item in INSTANT_EXPERIENCE_DESCRIPTION_VARIANTS
            ]
        },
        ensure_ascii=False,
        indent=2,
    )
    fallback_json = json.dumps(preview, ensure_ascii=False, indent=2)
    return f"""INSTANT EXPERIENCE DESCRIPTION COPY SYSTEM V1

Generate the long advertising description copy once for the selected product, then associate the same three ordered descriptions with all three Instant Experience image routes. These descriptions are not the short image FOMO line, image headline, image CTA, Meta headline field or Meta link-description field.

Resolved product context:
{context_json}

Return exactly three ordered description options:
1. Description 1 — Legacy Standard (`legacy_standard`)
2. Description 2 — Framed Greatness (`framed_greatness`)
3. Description 3 — Choose a Side (`choose_a_side`)

Use this response schema:
{schema_json}

Shared rules:
- Product data, supplied creative brief and structured metadata are the source of truth.
- Do not invent edition limits, remaining quantities, numbering, certificates, no-reprint policies, no-second-run policies, availability, achievements, rivalries, relationships, team affiliations, nicknames, dates, scores or championships.
- If the verified edition limit is 100, use either "Limited to 100 worldwide." or "Only 100 exist."
- If the exact edition limit is unavailable, use "A limited collector release."
- Use "A numbered collector drop." only when IS_NUMBERED is true.
- Use "No reprint." and "No second run." only when NO_REPRINT_VERIFIED is true.
- Use "When they're gone, they're gone" or permanent retirement language only when RETIRES_WHEN_SOLD_OUT or NO_REPRINT_VERIFIED is true.
- Use the ellipsis character "…" rather than three periods.
- Preserve intentional blank lines.
- Keep each option human, raw, collector-driven and approximately 35-65 words.
- Never use: Elevate, Transform, Ultimate, Stunning, Breathtaking, Must-have, Perfect addition, Take your space to the next level, emojis, hashtags, fake quotes, prices, discounts or generic interior-design language.

Description 1 — Legacy Standard:
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

Description 2 — Framed Greatness:
- One short greatness/framed hook.
- Blank line.
- Two collector-identity lines.
- Blank line.
- Three short scarcity lines.
- Blank line.
- "Secure yours."
- Prefer "Greatness doesn't fade. It gets framed." unless a rivalry, historic moment or motorsport hook is more product-accurate.

Description 3 — Choose a Side:
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

If model output fails validation, use this safe deterministic fallback and adapt only verified names/facts:
{fallback_json}"""


def _instant_experience_room_weights(context):
    weights = {
        key: profile["baseline_weight"]
        for key, profile in INSTANT_EXPERIENCE_ROOM_PROFILES_V4.items()
    }
    sport = str(context.get("product_sport") or "").casefold()
    era = context.get("product_era")
    mood = context.get("artwork_mood")
    campaign_context = str(context.get("campaign_context") or "").casefold()

    if sport in {"nba", "basketball", "nfl"} and era != "historic":
        weights["collector_lounge"] += 20
        weights["modern_man_cave"] += 5
    if sport in {"baseball", "boxing", "combat"} or era == "historic":
        weights["heritage_study"] += 30
        weights["collector_lounge"] += 5
    if "motorsport" in sport or "v8" in sport or "f1" in sport:
        if era == "modern":
            weights["collector_lounge"] += 20
        else:
            weights["heritage_study"] += 20
    if sport in {"soccer", "afl", "football", "rugby", "rugby union", "cricket"}:
        weights["collector_lounge"] += 14
        weights["heritage_study"] += 8
    if sport in {"horse racing", "golf", "tennis"}:
        weights["neutral_living"] += 18
        weights["heritage_study"] += 10
    if "women" in sport or "womens" in sport or "gifting" in campaign_context:
        weights["neutral_living"] += 22
        weights["collector_lounge"] += 8
    if mood == "rivalry":
        weights["modern_man_cave"] += 18
        weights["collector_lounge"] += 10
    return {key: max(1, int(value)) for key, value in weights.items()}


def _weighted_room_profile_key(weights, rng):
    total = sum(weights.values())
    cursor = rng.uniform(0, total)
    running = 0
    for key, weight in weights.items():
        running += weight
        if cursor <= running:
            return key
    return "collector_lounge"


def _preferred_room_profile_key(context):
    sport = str(context.get("product_sport") or "").casefold()
    era = context.get("product_era")
    mood = context.get("artwork_mood")
    campaign_context = str(context.get("campaign_context") or "").casefold()
    if "gifting" in campaign_context or sport in {"horse racing", "golf", "tennis"}:
        return "neutral_living"
    if era == "historic" or sport in {"baseball", "boxing", "combat"}:
        return "heritage_study"
    if mood == "rivalry":
        return "modern_man_cave"
    return "collector_lounge"


def _wall_palette_key(context):
    if context.get("artwork_mood") == "rivalry":
        return "dark"
    if context.get("product_era") == "historic" or context.get("artwork_mood") == "heritage":
        return "heritage"
    sport = str(context.get("product_sport") or "").casefold()
    if sport in {"horse racing", "golf", "tennis"} or "gifting" in str(context.get("campaign_context") or "").casefold():
        return "neutral"
    return "default"


def _resolved_overlay_copy(context, route):
    edition_limit = context.get("edition_limit")
    if edition_limit:
        resolved = {
            "headline_text": f"ONLY {edition_limit} WILL EVER EXIST",
            "supporting_line": route["fomo_line"],
            "cta_text": "CLAIM YOUR EDITION",
            "edition_limit_used": str(edition_limit),
            "edition_limit_source": context.get("edition_limit_source") or "verified product metadata",
            "scarcity_verified": True,
        }
    else:
        resolved = {
            "headline_text": "SPORTS CAVE COLLECTOR",
            "supporting_line": "Premium collector-home presentation for the selected product.",
            "cta_text": "CLAIM YOUR EDITION",
            "edition_limit_used": "not verified",
            "edition_limit_source": "safe evidence-gated fallback",
            "scarcity_verified": False,
        }
    resolved.update(
        resolve_instant_experience_on_image_copy(
            resolved["headline_text"],
            resolved["supporting_line"],
            resolved["cta_text"],
        )
    )
    return resolved


def resolve_standard_instant_experience_visuals(
    *,
    product_name="",
    category="",
    product_metadata=None,
    campaign_moment=None,
    variation_token="",
):
    context = resolve_instant_experience_product_context(
        product_name,
        category,
        product_metadata=product_metadata,
        campaign_moment=campaign_moment,
    )
    seed = _instant_experience_seed(
        product_name,
        category,
        context.get("product_era"),
        context.get("artwork_mood"),
        variation_token or "standard",
    )
    rng = random.Random(seed)
    weights = _instant_experience_room_weights(context)
    preferred_key = _preferred_room_profile_key(context)
    palette = INSTANT_EXPERIENCE_WALL_PALETTES_V4[_wall_palette_key(context)]
    primary_cues = list(INSTANT_EXPERIENCE_PRIMARY_CUES_V4)
    secondary_cues = list(INSTANT_EXPERIENCE_SECONDARY_CUES_V4)
    rng.shuffle(primary_cues)
    rng.shuffle(secondary_cues)
    resolved = []
    for index, route in enumerate(INSTANT_EXPERIENCE_ROUTE_CONFIGS_V4):
        visual = dict(route)
        profile_key = preferred_key if index == 0 else _weighted_room_profile_key(weights, rng)
        profile = INSTANT_EXPERIENCE_ROOM_PROFILES_V4[profile_key]
        wall_material, wall_colour = palette[index % len(palette)]
        primary_cue = primary_cues[index % len(primary_cues)]
        secondary_cue = secondary_cues[index % len(secondary_cues)]
        if context["product_sport"] == "safe universal fallback" and index == 0:
            profile_key = "collector_lounge"
            profile = INSTANT_EXPERIENCE_ROOM_PROFILES_V4[profile_key]
            wall_material = "fine seamless mineral plaster"
            wall_colour = "warm taupe seamless mineral-plaster wall"
            primary_cue = "partial doorway"
            secondary_cue = "cropped dark leather chair"
        overlay_copy = _resolved_overlay_copy(context, route)
        visual.update(
            {
                "product_sport": context["product_sport"],
                "product_era": context["product_era"],
                "artwork_mood": context["artwork_mood"],
                "campaign_context": context["campaign_context"],
                "room_profile_key": profile_key,
                "room_profile": profile["label"],
                "room_type": profile["room_type"],
                "room_materials": profile["materials"],
                "wall_material": wall_material,
                "wall_colour": wall_colour,
                "wall_finish": wall_material,
                "primary_cue": primary_cue,
                "secondary_cue": secondary_cue,
                "architectural_cue": primary_cue,
                "resolved_seed": seed,
                **overlay_copy,
            }
        )
        resolved.append(visual)
    sibling_summaries = [
        {
            "route": visual["route"],
            "camera_side": visual["camera_side"],
            "room_profile": visual["room_profile"],
            "wall_colour": visual["wall_colour"],
            "wall_material": visual["wall_material"],
            "primary_cue": visual["primary_cue"],
            "secondary_cue": visual["secondary_cue"],
            "lighting": visual["lighting"],
            "supporting_line": visual["supporting_line"],
        }
        for visual in resolved
    ]
    for visual in resolved:
        visual["sibling_summaries"] = [
            summary
            for summary in sibling_summaries
            if summary["route"] != visual["route"]
        ]
    return tuple(resolved)


def _instant_experience_pairwise_difference_count(first, second):
    return sum(
        str(first.get(field) or "").casefold()
        != str(second.get(field) or "").casefold()
        for field in INSTANT_EXPERIENCE_DIFFERENTIATION_FIELDS
    )


def validate_instant_experience_set_differentiation(visuals=None):
    visuals = tuple(visuals or INSTANT_EXPERIENCE_STANDARD_VISUALS)
    for index, first in enumerate(visuals):
        for second in visuals[index + 1 :]:
            difference_count = _instant_experience_pairwise_difference_count(
                first,
                second,
            )
            if difference_count < 5:
                raise ValueError(
                    "Instant Experience routes must differ across at least five "
                    f"resolved visual dimensions: {first['route']} and {second['route']} "
                    f"differ across {difference_count}."
                )
    return True



def build_instant_experience_image_quality_contract(visual):
    validate_instant_experience_set_differentiation()
    return "\n\n".join(
        (
            SPORTS_CAVE_IE_CORE_IMAGE_QUALITY_RULES_V2,
            build_instant_experience_fixed_opaque_footer_rules(),
            build_instant_experience_on_image_copy_fit_rules(),
            build_instant_experience_creative_cta_rules(visual["concept_id"]),
            build_instant_experience_typography_quality_rules(visual),
            build_instant_experience_set_differentiation_rules(visual),
            SPORTS_CAVE_IE_FINAL_REJECTION_GATE_V2,
        )
    )


def build_instant_experience_typography_quality_rules(visual):
    return f"""{SPORTS_CAVE_IE_TYPOGRAPHY_RULES_V2}
INSTANT EXPERIENCE ON-IMAGE TYPOGRAPHY - PREMIUM ROOM SYSTEM V4

- Add promotional typography as a deterministic post-production layer inside the fixed opaque footer after the room/product photograph is composed. Do not rely on the image model to invent text organically inside the room.
- Use the fixed footer geometry and opacity contract exactly. Keep its one thin 1-pixel muted-gold top separator. No glowing centre point, decorative border, marble, glitter, brushed metal or heavy concrete texture.
- Use a premium Sports Cave editorial serif for the headline, Montserrat Regular or Medium for the supporting line and Montserrat SemiBold or Bold for the CTA.
- Headline colour is warm ivory. The verified edition number, if present, is muted antique gold. Supporting text is warm off-white. CTA is muted antique gold.
- Exact resolved headline: {visual.get("headline_text")}.
- Exact resolved supporting line: {visual.get("supporting_line")}.
- Exact resolved CTA: {visual.get("cta_text")}.
- Keep the headline, supporting line and CTA on one line each and maintain 64-72 px safe margins. Apply the centralized on-image copy-fit limits before returning this prompt.
- Ensure all essential wording is clearly readable in a 256 x 256 preview.

MEANINGFUL SPORTS CAVE GOLD UNDERLINE

- If the resolved headline contains an edition number, render that number in restrained antique gold and place the gold underline directly beneath the measured glyph bounds of the number only.
- Use the actual rendered position and width of the edition number. Width is visible number width plus approximately 4-8 px. Gap beneath the number is approximately 5-7 px. Thickness is 2 px. Colour is close to #C7A15A.
- Use clean or subtly tapered underline ends. No bright yellow or orange. No glitter, metallic gradient or strong glow.
- The underline must move automatically when the edition limit changes.
- If exact number-level positioning cannot be guaranteed, underline approximately 96-100% of the complete measured headline. Never place an arbitrary decorative line beneath empty space.
- No fake button, price, discount, arrow, second CTA, paragraph or extra promotional text."""


def _instant_experience_route_wording_rules(visual):
    return f"""ROUTE WORDING LOCK - RESOLVE BEFORE RETURNING

Route identity: {visual["route"]}
Route key: {visual["route_key"]}

Permitted on-image words for this cover:
- Headline: {visual.get("headline_text")}
- Supporting line: {visual.get("supporting_line")}
- CTA: {visual.get("cta_text")}

These are the only permitted advertising words for this cover. Never place Primary Text on the image.

If edition limit used is "not verified", the supporting FOMO line for this route must not be used. Use the resolved safe fallback line above. Never invent an edition limit, remaining quantity, certificate, restock, availability, discount, offer or delivery claim."""


def build_instant_experience_set_differentiation_rules(visual):
    sibling_lines = []
    for sibling in visual.get("sibling_summaries", ()):
        sibling_lines.append(
            "- {route}: camera={camera}; room={room}; wall={wall}; finish={finish}; "
            "primary cue={primary}; secondary cue={secondary}; light={light}; FOMO={fomo}.".format(
                route=sibling["route"],
                camera=sibling["camera_side"],
                room=sibling["room_profile"],
                wall=sibling["wall_colour"],
                finish=sibling["wall_material"],
                primary=sibling["primary_cue"],
                secondary=sibling["secondary_cue"],
                light=sibling["lighting"],
                fomo=sibling["supporting_line"],
            )
        )
    return f"""{SPORTS_CAVE_IE_SET_DIFFERENTIATION_RULES_V2}
INSTANT EXPERIENCE SET DIFFERENTIATION - PREMIUM ROOM SYSTEM V4

This route's advertising job is: {visual["purpose"]}

Resolved sibling fingerprints supplied for comparison:
{chr(10).join(sibling_lines)}

Within one three-image package:
- Every route keeps the same exact product, Sports Cave identity, upper room scene, fixed bottom 21–23% opaque footer, product dominance, black timber frame, realistic glazing and one CTA.
- The three routes must differ in camera angle, room profile, wall colour, environmental cue, furniture crop and natural light direction or intensity.
- Never use the same exact wall colour twice.
- Never use the same primary environmental cue twice.
- Never use the same furniture arrangement twice.
- Never reuse an identical room composition.
- Never simply mirror the right route to create the left route.
- A broad room category may repeat only when wall colour, cue, furniture crop and lighting clearly change.
- Use exactly one primary cue and no more than one secondary cue.

{_instant_experience_route_wording_rules(visual)}"""


def _standard_instant_experience_exact_offer(campaign_moment=None):
    moment = normalize_campaign_moment(campaign_moment)
    return moment.get("promotion") or ""


def standard_instant_experience_fingerprint(index, visual, *, category=""):
    return {
        "route": visual["route"],
        "route_key": visual.get("route_key") or visual.get("concept_id"),
        "sub_angle": visual["copy_row"],
        "hook_family": visual["purpose"],
        "cover_layout": visual["composition"],
        "urgency_placement": "fixed opaque footer across bottom 21–23%",
        "creative_cta": visual["copy_row"],
        "room_type": visual["room_type"],
        "room_profile": visual.get("room_profile", visual["room_type"]),
        "wall_colour_family": visual["wall_colour"],
        "wall_material": visual["wall_material"],
        "wall_finish": visual.get("wall_finish", visual["wall_material"]),
        "camera_family": visual["camera_side"],
        "camera_angle": visual["camera_side"],
        "shot_distance": visual["shot_distance"],
        "lighting_direction": visual["lighting"],
        "time_of_day": visual["time_of_day"],
        "overlay_position": visual["overlay_position"],
        "product_position": visual["product_position"],
        "architectural_cue": visual["architectural_cue"],
        "primary_cue": visual.get("primary_cue") or visual["architectural_cue"],
        "secondary_cue": visual.get("secondary_cue") or "",
        "cover_composition": visual["composition"],
        "product_sport": visual.get("product_sport") or category,
        "product_era_or_mood": f"{visual.get('product_era', 'current')} / {visual.get('artwork_mood', 'clean')}",
        "fomo_line": visual.get("supporting_line") or visual.get("fomo_line"),
        "edition_limit_used": visual.get("edition_limit_used", "not verified"),
        "sport_family": resolved_instant_experience_sport_atmosphere(visual.get("product_sport") or category),
        "prompt_number": index,
    }


def build_standard_instant_experience_fingerprints(
    *,
    product_name="",
    category="",
    product_metadata=None,
    campaign_moment=None,
    variation_token="",
):
    validate_instant_experience_set_differentiation()
    visuals = resolve_standard_instant_experience_visuals(
        product_name=product_name,
        category=category,
        product_metadata=product_metadata,
        campaign_moment=campaign_moment,
        variation_token=variation_token,
    )
    return [
        standard_instant_experience_fingerprint(index, visual, category=category)
        for index, visual in enumerate(visuals, start=1)
    ]


def build_standard_instant_experience_freshness_block(
    *,
    product_name="",
    category="",
    product_metadata=None,
    campaign_moment=None,
    variation_token="",
    recent_fingerprints=None,
):
    current_fingerprints = build_standard_instant_experience_fingerprints(
        product_name=product_name,
        category=category,
        product_metadata=product_metadata,
        campaign_moment=campaign_moment,
        variation_token=variation_token,
    )
    return f"""STRUCTURED INSTANT EXPERIENCE VISUAL FRESHNESS

Current automatic cover fingerprints:
{_fingerprints_text(current_fingerprints)}

Recent Instant Experience fingerprints to avoid repeating:
{_fingerprints_text(recent_fingerprints or [])}

Resolve three covers that visibly differ at thumbnail size. They must differ in camera angle, room profile, wall colour/material, primary cue, secondary cue, furniture crop, lighting/time of day and FOMO supporting line while preserving the same premium Sports Cave campaign.

Avoid repeating the same scene combination across the most recent six Instant Experience packs when recent fingerprints are supplied."""



def build_instant_experience_canonical_prompt_v4(
    index,
    visual,
    *,
    product_name,
    category,
    country,
    product_url="",
    campaign_moment=None,
):
    product_name = _clean_product_name(product_name)
    category = _normalise_option_label(category) or "selected sport category"
    country = _normalise_option_label(country) or "selected market"
    product_url = _clean_product_url(product_url)
    shared_realism_rules = build_sports_cave_image_realism_rules(include_product_lock=True)
    ie_quality_contract = build_instant_experience_image_quality_contract(visual)
    campaign_moment_visual_context = build_campaign_moment_visual_context(
        campaign_moment,
        selected_country=country,
    )
    campaign_moment_visual_block = (
        f"\n\n{campaign_moment_visual_context}"
        if campaign_moment_visual_context
        else ""
    )
    fingerprint = standard_instant_experience_fingerprint(
        index,
        visual,
        category=category,
    )
    resolved_json = json.dumps(fingerprint, ensure_ascii=False, indent=2)
    scarcity_note = (
        "The edition limit is verified. Use the resolved headline and route FOMO line exactly."
        if visual.get("scarcity_verified")
        else (
            "No verified edition limit is available in the supplied metadata. Use the resolved safe fallback headline "
            "and supporting line exactly. Do not use the route FOMO line or invent a number."
        )
    )
    return f"""{visual["prompt_heading"]}

Copy this prompt into a fresh image-generation conversation with the exact uploaded Sports Cave product image attached.

Do not generate the image automatically from this Ads-planning response.

SPORTS CAVE INSTANT EXPERIENCE PREMIUM ROOM SYSTEM V4

PRODUCT AND VERIFIED METADATA

- Product name: {product_name}
- Sport/category: {category}
- Country/market: {country}
- Destination URL for ad setup only: {product_url or "[exact product-page URL from the Ads form]"}
- Route key: {visual["route_key"]}
- Route name: {visual["route"]}
- Camera role: {visual["camera_role"]}
- Product sport used for room selection: {visual.get("product_sport")}
- Product era/mood classification: {visual.get("product_era")} / {visual.get("artwork_mood")}
- Edition limit used: {visual.get("edition_limit_used")}
- Edition limit source: {visual.get("edition_limit_source")}

{scarcity_note}

RESOLVED ROUTE VARIABLES — FOLLOW EXACTLY

- Camera angle: {visual["camera_side"]}
- Camera instruction: {visual["camera_instruction"]}
- Room profile: {visual["room_profile"]}
- Room type: {visual["room_type"]}
- Room materials: {visual["room_materials"]}
- Wall finish: {visual["wall_finish"]}
- Wall colour: {visual["wall_colour"]}
- Primary cue: {visual["primary_cue"]}
- Secondary cue: {visual["secondary_cue"]}
- Natural light: {visual["lighting"]}
- Time of day: {visual["time_of_day"]}
- Product dominance: {visual["shot_distance"]}
- Lens character: {visual["lens"]}
- Fixed footer: {visual["overlay_position"]}

Resolved prompt metadata:
{resolved_json}

CANONICAL SPORTS CAVE MASTER PROMPT

Create one ultra-realistic 1024 x 1024 Meta Instant Experience cover for Sports Cave.

The final image must be:
- exactly 1024 x 1024 pixels
- true 1:1 square
- sRGB
- designed for mobile viewing
- clear and readable at a 256 x 256 preview

Composition is locked:
- Upper photographed residential room scene: approximately 77–79% of the canvas.
- Fixed opaque black footer: approximately the bottom 21–23% of the canvas.
- Framed product width: approximately 82-88% of the canvas.
- Complete frame visible with no cropped outer frame edges.
- Safe margins: 64-72 pixels.
- The supplied framed product is the largest and most important visual element.

The three-image package must produce:
1. Slight right-angle product photograph.
2. Straight-on product photograph.
3. Slight left-angle product photograph.

This route must deliver only its assigned camera role: {visual["route"]}.

PRODUCT LOCK — ABSOLUTE

The selected product and artwork are protected assets. Use original supplied product pixels wherever the current pipeline supports compositing.

Preserve exactly:
- athletes and facial features
- bodies, hands, hairstyles, uniforms and poses
- all existing words, numbers and signatures
- existing badges and logos
- artwork colours and contrast
- artwork composition
- frame proportions
- complete product boundaries

Never recreate, redraw, mirror, crop, extend, stretch, warp, blur, recolour or replace the artwork. Never place promotional copy inside the supplied artwork. Never add competing sports artwork to the room.

ROOM SELECTION AND ENVIRONMENT

Use the resolved room profile because it was selected from the product's available sport, era, artwork mood, palette and campaign context. The product supplies the sport. The room supplies the lifestyle.

Room direction:
- {visual["room_profile"]}
- {visual["room_materials"]}
- Primary cue: {visual["primary_cue"]}
- Secondary cue: {visual["secondary_cue"]}

Use exactly one primary cue and no more than one secondary cue. Do not add team flags, jerseys, additional athlete pictures, readable televisions, sport-specific logos, neon signs, alcohol displays, pool tables, excessive trophies or memorabilia.

MANDATORY SEAMLESS WALL SYSTEM

Every wall must be seamless, residential, premium, matte, realistically textured, visually quiet and free from unexplained lines.

Approved wall finish for this route: {visual["wall_finish"]}.
Resolved wall colour for this route: {visual["wall_colour"]}.

Include extremely subtle natural microtexture, gentle organic tonal variation, realistic light falloff, soft brightness variation and approximately 2-4% visible mottling. No obvious repeated pattern.

Never generate horizontal wall lines, vertical wall lines, tile lines, grout, stone-slab divisions, concrete formwork divisions, panel joins, timber slats, decorative panels, geometric grooves, repeated seams, wainscoting, moulding behind the artwork, brick outlines, wallpaper stripes, rectangular wall sections, artificial shadow bands, lines passing behind the frame, commercial hotel-lobby walls, office walls or property-showroom walls.

A genuine doorway, window edge or room corner is allowed only near the outer part of the scene. It must follow correct perspective and must not pass behind or visually divide the framed product. Reject an otherwise strong generation if an unexplained line appears anywhere on the wall.

FRAME, GLASS AND MOUNTING REALISM

Frame:
- slim-to-medium black timber moulding
- approximately 18-22 mm visible front face
- approximately 28-34 mm wall projection
- sharp 45-degree mitred corners
- restrained satin-black finish
- subtle irregular timber grain
- physically consistent construction
- natural frame depth appropriate to the selected camera angle

Mounting:
- believable 6-10 mm mounting gap
- narrow contact shadow
- softer secondary shadow
- slightly more shadow beneath the frame
- shadow direction consistent with room lighting
- no black halo, uniform digital drop shadow or floating product

Glass:
- clear gallery-style glazing
- approximately 8-15% partial reflection coverage
- approximately 3-6% reflection opacity
- one believable room or window reflection
- reflection stops at the inner frame edge
- artwork remains crisp
- no plastic film, wrinkles, full-surface haze or glare over important faces, text or signatures

LIGHTING

Use one physically consistent source of soft daylight with restrained interior ambient light.
- Approximate temperature: 4000-4700K.
- Match lighting across wall, furniture, frame and glass.
- Use realistic falloff.
- Keep peripheral room elements slightly softer than the product.
- Do not darken or recolour the protected artwork.

Never use a spotlight directly above the frame, glowing outlines, rim lighting, fog, smoke, light rays, heavy vignettes, conflicting light directions or excessive golden lighting.

FIXED BLACK FOOTER AND DETERMINISTIC TYPOGRAPHY

Use the centralized fixed opaque footer and on-image copy-fit contracts below without altering the existing typography hierarchy:
- deep matte charcoal near #101112 or #121314
- extremely subtle premium paper or fine-grain texture
- one 1-pixel muted-gold boundary line across the scene transition
- no glowing centre point, decorative border, marble, glitter, brushed metal or heavy concrete texture

Add all promotional typography as a deterministic flat post-production layer inside the footer using real fonts after the room/product photograph is composed. Do not rely on the image-generation model to organically render copy in the photographed scene.

Resolved on-image copy:
HEADLINE: {visual.get("headline_text")}
SUPPORTING LINE: {visual.get("supporting_line")}
CTA: {visual.get("cta_text")}

Use the headline and CTA consistently across the package. The supporting line is route-specific and must be the resolved line above.

Typography:
- Headline: premium Sports Cave editorial serif, warm ivory.
- Supporting line: Montserrat Regular or Medium, warm off-white.
- CTA: Montserrat SemiBold or Bold, muted antique gold.
- No fake button, price, discount, arrow or second CTA.

Meaningful gold underline:
- If the headline contains an edition number, render that number in restrained antique gold and place the gold underline directly beneath the measured glyph bounds of the number.
- Width: visible number width plus approximately 4-8 pixels.
- Gap beneath the number: approximately 5-7 pixels.
- Thickness: 2 pixels.
- Colour close to #C7A15A.
- Use clean or subtly tapered ends.
- No floating centred dash, bright yellow, orange, glitter, metallic gradient or strong glow.
- The underline must move automatically when the edition limit changes.
- If exact number-level positioning cannot be guaranteed, underline approximately 96-100% of the complete measured headline. Never place an arbitrary decorative line beneath empty space.

INSTANT EXPERIENCE CORE QUALITY CONTRACTS

{ie_quality_contract}

AUTHORITATIVE APP-WIDE PRODUCT AND REALISM LOCK

{shared_realism_rules}

{build_sport_country_visual_adaptation(category, country)}{campaign_moment_visual_block}

FINAL ROUTE CHECK

- Right, front and left camera directions are distinct across the package.
- This route uses its exact camera role and is not a mirrored duplicate of another route.
- Wall colour and cues differ from the other routes.
- Room variation remains subtle and product-led.
- The room never becomes a themed sports bar.
- The fixed black footer remains within approximately 21–23% of the canvas height.
- No unresolved placeholders remain.
- No unverified quantity or scarcity fact is introduced."""


def build_standard_instant_experience_image_prompt(
    index,
    visual,
    *,
    product_name,
    category,
    country,
    product_url="",
    campaign_moment=None,
    recent_fingerprints=None,
):
    return build_instant_experience_canonical_prompt_v4(
        index,
        visual,
        product_name=product_name,
        category=category,
        country=country,
        product_url=product_url,
        campaign_moment=campaign_moment,
    )


def build_standard_instant_experience_visual_prompts(
    *,
    product_name,
    category,
    country,
    product_url="",
    campaign_moment=None,
    product_metadata=None,
    variation_token="",
    recent_fingerprints=None,
):
    visuals = resolve_standard_instant_experience_visuals(
        product_name=product_name,
        category=category,
        product_metadata=product_metadata,
        campaign_moment=campaign_moment,
        variation_token=variation_token,
    )
    prompts = [
        build_standard_instant_experience_image_prompt(
            index,
            visual,
            product_name=product_name,
            category=category,
            country=country,
            product_url=product_url,
            campaign_moment=campaign_moment,
            recent_fingerprints=recent_fingerprints,
        )
        for index, visual in enumerate(visuals, start=1)
    ]
    return "\n\n".join(prompts)


def build_instant_experience_copy_variation_table_contract(route_name):
    return f"""COPY VARIATIONS

| Description | Description Key | Description Label | Description Copy | Headline | CTA |
| ----------- | --------------- | ----------------- | ---------------- | -------- | --- |
| 1 | legacy_standard | Description 1 — Legacy Standard | Complete {route_name} Legacy Standard description copy | Complete {route_name} headline | Complete {route_name} CTA |
| 2 | framed_greatness | Description 2 — Framed Greatness | Complete {route_name} Framed Greatness description copy | Complete {route_name} headline | Complete {route_name} CTA |
| 3 | choose_a_side | Description 3 — Choose a Side | Complete {route_name} Choose a Side description copy | Complete {route_name} headline | Complete {route_name} CTA |"""


def build_standard_instant_experience_group_output_contract(
    *,
    product_name,
    category,
    country,
    product_url="",
    campaign_moment=None,
    product_metadata=None,
    variation_token="",
    recent_fingerprints=None,
):
    group_sections = []
    visuals = resolve_standard_instant_experience_visuals(
        product_name=product_name,
        category=category,
        product_metadata=product_metadata,
        campaign_moment=campaign_moment,
        variation_token=variation_token,
    )
    for index, visual in enumerate(visuals, start=1):
        image_prompt = build_standard_instant_experience_image_prompt(
            index,
            visual,
            product_name=product_name,
            category=category,
            country=country,
            product_url=product_url,
            campaign_moment=campaign_moment,
            recent_fingerprints=recent_fingerprints,
        )
        group_sections.append(
            f"""{visual["group_heading"]}

{image_prompt}

{build_instant_experience_copy_variation_table_contract(visual["route"])}"""
        )
    return "\n\n".join(group_sections)


def _ie_visual_value(settings, key, fallback):
    settings = normalize_instant_experience_settings(settings)
    if settings["visual_direction"] == "Manual Overrides":
        value = settings.get("advanced_visual", {}).get(key)
        if value and value != IE_AUTO_FRESH_MATCH:
            return value
    return fallback


def instant_experience_creative_cta_for_route(route_id, *, settings=None, exact_offer=""):
    route = INSTANT_EXPERIENCE_ROUTE_CONFIGS.get(route_id, INSTANT_EXPERIENCE_ROUTE_CONFIGS["ACT"])
    return route["creative_cta_family"][0]


def instant_experience_fixed_button_cta_for_route(route_id, *, settings=None):
    settings = normalize_instant_experience_settings(settings)
    route = INSTANT_EXPERIENCE_ROUTE_CONFIGS.get(route_id, INSTANT_EXPERIENCE_ROUTE_CONFIGS["ACT"])
    if settings["fixed_button_cta_mode"] == "Hold fixed-button CTA constant across all routes":
        return "Shop Now"
    return route["fixed_button_cta"]


def build_instant_experience_offer_serialization_block(
    campaign_moment=None,
    settings=None,
    *,
    selected_routes=None,
):
    exact_offer = exact_offer_from_inputs(campaign_moment, settings)
    route_ids = selected_routes or [route for _label, route in instant_experience_selected_routes(settings)]
    supported_routes = [
        route_id for route_id in route_ids if instant_experience_route_supports_offer(route_id)
    ]
    offer_value = exact_offer or "None supplied"
    if exact_offer and supported_routes:
        use_rule = (
            "The exact offer may be used only inside these active offer-compatible routes: "
            f"{', '.join(supported_routes)}."
        )
    elif exact_offer:
        use_rule = (
            "The exact offer is serialized for review, but no active route supports offer language. "
            "Do not use it in primary text, headline, cover, creative CTA or Meta Description."
        )
    else:
        use_rule = "No offer may be invented or implied."
    return f"""EXACT OFFER SERIALIZATION

Exact offer entered: {offer_value}

This field is serialized independently of Moment Type. If it is non-empty, preserve the wording exactly.

{use_rule}"""


def build_instant_experience_route_gate_block(settings=None):
    settings = normalize_instant_experience_settings(settings)
    return f"""INSTANT EXPERIENCE ANGLE GATES

- Destination scope selected: {settings["destination_scope"]}.
- Rivalry requires a verified dual-subject or rivalry product.
- Milestone requires a verified milestone, number or event.
- Collector/Rarity requires verified edition information.
- Gift requires Gift Buyer targeting or an explicitly selected gifting strategy.
- Sale requires an exact entered offer.
- National-pride language requires a verified connection between the subject and nation; selected advertising country alone is insufficient.
- "Made in the USA" must come from approved manufacturing data, never the selected target market.
- Country selection controls language, terminology and residential cues. It must not alter product facts.
- Sport selection controls emotional vocabulary and visual atmosphere. It must not introduce fake sporting props or unsupported history.
- "Only X remaining" requires current timestamped inventory data.
- Numbered certificate language requires approved product data.
- Never invent scarcity, offers, sporting details or product facts."""


def build_instant_experience_freshness_block(
    settings=None,
    *,
    category="",
    recent_fingerprints=None,
):
    current_fingerprints = build_instant_experience_fingerprints(settings, category=category)
    return f"""STRUCTURED INSTANT EXPERIENCE CREATIVE FRESHNESS

Current route fingerprints:
{_fingerprints_text(current_fingerprints)}

Recent Instant Experience fingerprints to avoid repeating:
{_fingerprints_text(recent_fingerprints or [])}

A new creative should differ from recent work in at least five of these dimensions: psychological angle, opening-hook structure, cover layout, urgency placement, room type, wall colour/material family, camera family, lighting/time of day.

Within a Smart 3-Pack:
- Use three distinct layout/camera families.
- Use at least two different room categories.
- Do not repeat the same wall material.
- Do not repeat the same time of day.
- Do not use the same overlay hierarchy.
- Make the difference visible at thumbnail size."""


def build_instant_experience_route_visual_brief(
    route_id,
    *,
    settings=None,
    category="",
):
    route = INSTANT_EXPERIENCE_ROUTE_CONFIGS.get(route_id, INSTANT_EXPERIENCE_ROUTE_CONFIGS["ACT"])
    room_type = _ie_visual_value(settings, "room_type", route["room_family"])
    wall_colour = _ie_visual_value(settings, "wall_colour_family", route["wall_family"])
    wall_material = _ie_visual_value(settings, "wall_material", route["wall_family"])
    camera_family = _ie_visual_value(settings, "camera_family", route["camera_family"])
    camera_height = _ie_visual_value(settings, "camera_height", route["camera_family"])
    shot_distance = _ie_visual_value(settings, "shot_distance", route["product_prominence"])
    lens_character = _ie_visual_value(settings, "lens_character", route["lens_family"])
    lighting_direction = _ie_visual_value(settings, "lighting_direction", route["lighting_family"])
    time_of_day = _ie_visual_value(settings, "time_of_day", route["lighting_family"])
    cover_layout = _ie_visual_value(settings, "cover_layout", route["cover_composition"])
    overlay_treatment = _ie_visual_value(settings, "overlay_text_treatment", route["on_image_message_type"])
    return f"""Route visual brief:
- Room type: {room_type}
- Wall colour family: {wall_colour}
- Wall material/finish: {wall_material}
- Camera side and angle: {camera_family}
- Camera height: {camera_height}
- Shot distance/product prominence: {shot_distance}
- Lens character: {lens_character}
- Lighting direction: {lighting_direction}
- Time of day: {time_of_day}
- Cover layout: {cover_layout}
- Overlay text treatment: {overlay_treatment}
- Sport atmosphere guide: {instant_experience_sport_direction(category)}
- No generated sporting props, fake memorabilia, team-coloured clutter, extra artwork, neon signs or unofficial branding."""


def build_instant_experience_route_copy_rules(
    route_id,
    *,
    settings=None,
    campaign_moment=None,
):
    settings = normalize_instant_experience_settings(settings)
    route = INSTANT_EXPERIENCE_ROUTE_CONFIGS.get(route_id, INSTANT_EXPERIENCE_ROUTE_CONFIGS["ACT"])
    exact_offer = exact_offer_from_inputs(campaign_moment, settings)
    if route_id == "FEEL":
        urgency_line = (
            "When urgency placement is None in feed creative or Meta description only, keep the primary text, headline and cover free of FOMO wording."
            if settings["urgency_placement"] in {"None in feed creative", "Meta description only"}
            else "Use urgency only if it remains soft, verified and secondary to the memory-led hook."
        )
        return f"""FEEL ROUTE RULES

Psychological job: {route["psychological_job"]}

Copy:
- Lead with a sensory memory, defining feeling or verified product-specific moment.
- No generic product description opening.
- No proof checklist.
- No discount language.
- No hard-sell language.
- Do not use "Greatness doesn't fade" in this route.
- Do not force nostalgia onto a future or current event.
- For a current achievement, adapt FEEL to awe, triumph or anticipation.
- "Relive" may only be used for a completed event.
- {urgency_line}

Cover:
- Full-bleed or near-full-bleed editorial lifestyle composition.
- No large hard black panel.
- Lifestyle/product region approximately 78-84%.
- Optional restrained editorial caption region approximately 16-22%.
- The frame should occupy approximately 65-75% of the usable width.
- Eye-level or slightly below eye-level.
- Near-front or very mild three-quarter perspective.
- 65-85mm natural lens character.
- Intimate morning or late-afternoon natural light.
- Use one short product-specific hook and, at most, one supporting line.
- Maximum approximately 14 total overlay words.
- Use only an approved This Edition creative CTA; the acquisition CTA does not add scarcity language to the emotional route."""
    if route_id == "BELONG":
        return f"""BELONG ROUTE RULES

Psychological job: {route["psychological_job"]}

Copy:
- Lead with belonging, recognition or shared fan identity.
- Help the customer picture the artwork in their home, office, sports room or collection.
- Do not make the room the product.
- Do not use a proof checklist.
- Use no more than one verified proof or scarcity cue.
- Do not use aggressive gone-forever language unless explicitly selected.
- Do not reuse the FEEL opening structure.
- Do not use "Greatness doesn't fade" unless this route has explicitly been chosen as the one permitted route to use it.
- Do not invent an offer. Exact offer entered for this run: {exact_offer or "None"}.

Cover:
- Wider real-room context than FEEL.
- Asymmetrical editorial composition.
- Use genuine architectural negative space for typography.
- Avoid the current centered black scarcity panel.
- Frame approximately 50-60% of usable width.
- Chest-height camera.
- Restrained left or right three-quarter view.
- 45-55mm natural lens character.
- Contemporary but believable wall/material contrast.
- Dusk daylight plus restrained practical lighting is allowed.
- Use an identity-led hook, one short support line and one approved This Edition creative CTA.
- Maximum approximately 16 total overlay words."""
    if route_id == "BUILD":
        return f"""BUILD ROUTE RULES

Psychological job: {route["psychological_job"]}

Copy:
- Only use this route for a precise curated collection destination.
- Lead with choosing more than one relevant edition and building a collection.
- Use the exact entered multi-buy or collection offer only when supplied and verified: {exact_offer or "None supplied"}.
- Do not generate invented or lookalike artworks to create a multi-product wall.
- A multi-product promise must not link to one unrelated PDP.
- Use only an approved This Edition creative CTA. Keep collection or offer wording in the route copy, not in a replacement CTA.

Cover:
- If the cover displays multiple products, two to four exact product reference assets must be supplied.
- Never invent additional framed editions.
- Keep the featured product exact and dominant enough to understand on mobile.
- Use collection-wall or collection-browsing composition only when exact references are supplied."""
    overlay_lines = "\n".join(BASEBALL_INSTANT_EXPERIENCE_COVER_LINES)
    return f"""ACT ROUTE RULES

Psychological job: {route["psychological_job"]}

This is the Classic Collector current conversion control.

Preserve the existing:
- Copy opener.
- Product-specific paragraph rules.
- Approved proof checklist.
- Scarcity close.
- Headline logic.
- CTA.
- Setup.
- Black-and-gold bottom scarcity strip.
- Existing room direction and visual safeguards.

Use this current-control opening:
Greatness doesn't fade. It gets framed.

Use this current-control creative CTA:
{BASEBALL_INSTANT_EXPERIENCE_CTA}

Use these exact cover lines:
{overlay_lines}

Cover:
- Full-width upper lifestyle/product image region across approximately 77-79% of the square canvas.
- Fixed full-width opaque matte-black footer across the bottom approximately 21-23% of the square canvas.
- Thin restrained metallic-gold divider across the top edge of the black strip.
- No left/right split, no right sidebar and no vertical scarcity panel.
- Current black-and-gold visual treatment.
- Never invent scarcity.
- "Only X remaining" requires current timestamped inventory data."""


def build_instant_experience_route_package_contract(
    label,
    route_id,
    *,
    settings=None,
    product_name="",
    category="",
    country="",
    product_url="",
    campaign_moment=None,
):
    settings = normalize_instant_experience_settings(settings)
    route = INSTANT_EXPERIENCE_ROUTE_CONFIGS.get(route_id, INSTANT_EXPERIENCE_ROUTE_CONFIGS["ACT"])
    exact_offer = exact_offer_from_inputs(campaign_moment, settings)
    creative_cta = instant_experience_creative_cta_for_route(
        route_id,
        settings=settings,
        exact_offer=exact_offer,
    )
    fixed_button_cta = instant_experience_fixed_button_cta_for_route(
        route_id,
        settings=settings,
    )
    option_heading = f"{label} — {route_id}"
    if label == "CLASSIC COLLECTOR":
        option_heading = "CLASSIC COLLECTOR — CURRENT CONTROL"
    elif label == "SELECTED ROUTE":
        option_heading = f"SELECTED ROUTE — {route_id}"
    return f"""{option_heading}

Route name: {IE_ROUTE_LABELS.get(route_id, route_id)}
Psychological job: {route["psychological_job"]}
Funnel suitability: {route["funnel"]}
Creative CTA family: {", ".join(route["creative_cta_family"])}
Default creative CTA for this route: {creative_cta}
Fixed button CTA for this route: {fixed_button_cta}
Destination compatibility: {route["destination"]}
Required data: {route["required_data"]}
Prohibited language: {route["prohibited_language"]}

{build_instant_experience_route_copy_rules(route_id, settings=settings, campaign_moment=campaign_moment)}

{build_instant_experience_route_visual_brief(route_id, settings=settings, category=category)}

OUTPUT EXACTLY FOR THIS OPTION

PRIMARY TEXT
[one complete primary text]

HEADLINE
[one headline]

META AD DESCRIPTION
[one supporting Meta ad description]

CREATIVE CTA
[{creative_cta} or another valid creative CTA from the route family]

FIXED BUTTON CTA
[{fixed_button_cta}]

CAMPAIGN STRATEGY
[one concise route-specific strategy summary]

INSTANT EXPERIENCE SETUP
[one complete setup block using product.name as the catalogue product headline, Limited Edition as the catalogue descriptor, the exact destination URL, and {META_AD_URL_PARAMETERS}]

IMAGE GENERATION PROMPTS — COPY ONE AT A TIME

INSTANT EXPERIENCE COVER IMAGE PROMPT
[one complete standalone cover prompt for {product_name}, {category}, {country}, active route {route_id}, exact route overlay wording, exact destination scope and the exact uploaded framed product reference]"""


def build_instant_experience_route_prompt(
    product_name,
    category,
    country,
    campaign_type,
    product_url="",
    *,
    instant_experience_settings=None,
    campaign_moment=None,
    recent_instant_experience_fingerprints=None,
    specific_pattern=False,
):
    return build_standard_instant_experience_prompt(
        product_name,
        category,
        country,
        campaign_type,
        product_url=product_url,
        specific_pattern=specific_pattern,
        campaign_moment=campaign_moment,
    )
    product_name = _clean_product_name(product_name)
    product_url = _clean_product_url(product_url)
    settings = normalize_instant_experience_settings(instant_experience_settings)
    selected_routes = instant_experience_selected_routes(settings)
    route_ids = [route for _label, route in selected_routes]
    if specific_pattern:
        pattern_heading = f"SPORTS CAVE {str(category or '').upper()} INSTANT EXPERIENCE ROUTE SYSTEM"
    else:
        pattern_heading = "SPORTS CAVE INSTANT EXPERIENCE ROUTE SYSTEM"
    if settings["output_mode"] == IE_MODE_SMART:
        objective = "Create exactly three complete Instant Experience ads, one per selected route. These are separate concepts, not five rewrites inside one ad."
    else:
        objective = "Create exactly one complete Instant Experience ad for the selected route."
    route_contracts = "\n\n".join(
        build_instant_experience_route_package_contract(
            label,
            route,
            settings=settings,
            product_name=product_name,
            category=category,
            country=country,
            product_url=product_url,
            campaign_moment=campaign_moment,
        )
        for label, route in selected_routes
    )
    smart_rule = (
        "\nSMART 3-PACK ORDER\nReturn exactly three complete packages in the selected route order. Do not output rejected alternatives inside any option.\n"
        if settings["output_mode"] == IE_MODE_SMART
        else ""
    )
    collection_block = ""
    if settings["destination_scope"] == "Curated collection page + catalogue":
        collection_block = f"""
CURATED COLLECTION DESTINATION

Collection name: {settings["collection_name"]}
Collection URL: {settings["collection_url"]}
Exact product-set name: {settings["collection_product_set_name"]}
Eligible catalogue products: {settings["eligible_product_count"]}
Exact product reference assets supplied: {settings["multi_product_reference_count"]}

Never silently use a broad collection URL. A multi-product promise must use this collection destination and exact product set."""
    fixed_button_rule = (
        "Hold the fixed button CTA constant across all returned routes. The creative/on-image CTA may vary by route."
        if settings["fixed_button_cta_mode"] == "Hold fixed-button CTA constant across all routes"
        else "Auto-match the fixed button CTA to each active route using valid Meta or Instant Experience button labels."
    )
    return f"""{pattern_heading}

PRODUCT
Product name: {product_name}
Category: {category}
Market: {country}
Campaign type: {campaign_type}
Destination guidance: {build_product_url_instruction(product_url)}
Creative output mode: {settings["output_mode"]}
Audience mindset: {settings["audience_mindset"]}
Primary creative angle override: {settings["primary_angle"]}
Urgency placement: {settings["urgency_placement"]}
Destination scope: {settings["destination_scope"]}
Visual direction: {settings["visual_direction"]}
Fixed-button CTA handling: {settings["fixed_button_cta_mode"]}

I have attached the exact Sports Cave product image being advertised.

Analyse the attached image and product title before writing.

Use the supplied product name as the source of identity. Do not identify or guess a person, club, country, achievement, year, record, final, trophy or rivalry solely from the image.

{build_country_campaign_localisation_note(category, country, campaign_type="Instant Experience")}

{build_universal_sports_cave_rules(category)}

{build_category_winner_angle_block(category, campaign_type, country)}

OBJECTIVE

{objective}
{smart_rule}
Do not generate images. Return text, setup and production-ready cover prompts only.

SEPARATE CTA TYPES

- Emotional angle: controlled by the active route.
- On-image creative CTA: generated under CREATIVE CTA.
- Meta/Instant Experience fixed-button CTA: generated under FIXED BUTTON CTA.
- Description archetype: must match the ordered product-aware description system.
- Offer: may be used only when the active route supports it and the exact offer is supplied.
- Destination: use the exact product or collection destination supplied in this prompt.

{fixed_button_rule}

{build_instant_experience_offer_serialization_block(campaign_moment, settings, selected_routes=route_ids)}

{build_instant_experience_route_gate_block(settings)}
{collection_block}

COPY DIVERSITY RULES

- Each option must have one dominant psychological job.
- No shared opening sentence.
- No duplicated headline.
- Every creative CTA must use the approved This Edition family.
- Only ACT may use the black-and-gold bottom scarcity strip.
- Only one option may use "Greatness doesn't fade."
- FEEL must not sound like ACT with urgency lines removed.
- BELONG must not sound like an interior-design advertisement.
- Do not repeat the same proof sentence across all options.
- Use short mobile-readable paragraphs.
- Avoid generic AI language including elevate, transform, ultimate, unleash, must-have, masterpiece, conversation starter and bring your walls to life.
- Every product claim must remain fact-safe.
- Use natural selected-country English.

{build_instant_experience_freshness_block(settings, category=category, recent_fingerprints=recent_instant_experience_fingerprints)}

ROUTE OUTPUT CONTRACTS

{route_contracts}

FINAL QUALITY CHECK

- The output count matches the selected Creative output mode.
- Every route contains exactly one image-generation prompt and one three-row table with Description Key, Description Label, Description Copy, Headline and CTA.
- No separate Meta link-description or Meta Ad Description field is used.
- product.name is used as the catalogue product headline.
- Limited Edition is used as the catalogue product description.
- The exact supplied destination URL is used: {product_url or "[selected product URL]"}.
- The exact URL parameters are used: {META_AD_URL_PARAMETERS}.
- Product, artwork, frame, glass and realism safeguards are preserved.
- No automatic image generation is triggered."""


def build_instant_experience_visual_output_requirements(
    template_key,
    *,
    product_name="",
    category="",
    country="",
    product_url="",
    campaign_moment=None,
    product_metadata=None,
    variation_token="",
    instant_experience_settings=None,
    recent_instant_experience_fingerprints=None,
):
    product_name = _clean_product_name(product_name)
    product_url = _clean_product_url(product_url)
    campaign_moment_visual_context = build_campaign_moment_visual_context(
        campaign_moment,
        selected_country=country,
    )
    campaign_moment_visual_block = (
        f"\n\n{campaign_moment_visual_context}"
        if campaign_moment_visual_context
        else ""
    )
    return f"""INSTANT EXPERIENCE VISUAL REQUIREMENTS

Return exactly three complete grouped Instant Experience routes in the standard order: Premium Scarcity — Right Angle, Premium Scarcity — Straight On, then Premium Scarcity — Left Angle.

Do not output a fourth prompt.
Do not output one shared prompt with variations.
Do not use "same as above", "use the rules above", "refer to the earlier image", "use the selected route" or any cross-reference.
Do not output route labels, multi-route mode sections, old control-mode sections or Campaign Strategy packages.
Do not ask which cover to generate.
Do not generate images.

Each standalone prompt must contain the shared Sports Cave product/realism lock exactly once and remain fully copyable into a fresh ChatGPT conversation.

The three covers must visibly differ in camera angle, room profile, wall colour/material, environmental cue, furniture crop, light direction or intensity and FOMO supporting line while preserving one premium Sports Cave campaign.

{build_standard_instant_experience_freshness_block(
    product_name=product_name,
    category=category,
    product_metadata=product_metadata,
    campaign_moment=campaign_moment,
    variation_token=variation_token,
    recent_fingerprints=recent_instant_experience_fingerprints,
)}
{campaign_moment_visual_block}

GROUPED INSTANT EXPERIENCE OUTPUT — COPY ONE ROUTE AT A TIME

{build_standard_instant_experience_group_output_contract(
    product_name=product_name,
    category=category,
    country=country,
    product_url=product_url,
    campaign_moment=campaign_moment,
    product_metadata=product_metadata,
    variation_token=variation_token,
    recent_fingerprints=recent_instant_experience_fingerprints,
)}

FINAL INSTANT EXPERIENCE IMAGE CHECK

- Exactly three group sections are present.
- Each group contains exactly one IMAGE GENERATION PROMPT and exactly one three-row COPY VARIATIONS table.
- Premium Scarcity — Right Angle uses the slight right-angle camera role and its route FOMO line when edition-limit data is verified.
- Premium Scarcity — Straight On uses the straight-on camera role and its route FOMO line when edition-limit data is verified.
- Premium Scarcity — Left Angle uses the slight left-angle camera role and its route FOMO line when edition-limit data is verified.
- Each prompt includes exact product identity, selected sport, selected country, resolved route variables, product/artwork lock, frame and glass realism, physical mounting, seamless wall rules, square 1024 x 1024 composition, the country-invariant fixed 21–23% opaque footer, deterministic on-image wording and no automatic image generation.
- Each prompt includes the shared Sports Cave image-realism marker exactly once."""

    settings = normalize_instant_experience_settings(instant_experience_settings)
    if settings["output_mode"] != IE_MODE_CLASSIC:
        selected_routes = instant_experience_selected_routes(settings)
        route_prompt_count = len(selected_routes)
        route_labels = ", ".join(
            f"{label} — {route}" for label, route in selected_routes
        )
        package_count_rule = (
            "Return exactly three complete Instant Experience packages and three standalone cover prompts."
            if settings["output_mode"] == IE_MODE_SMART
            else "Return exactly one complete Instant Experience package and one standalone cover prompt."
        )
        route_visuals = "\n\n".join(
            f"""{label} — {route} COVER DIRECTION

{build_instant_experience_route_copy_rules(route, settings=settings, campaign_moment=campaign_moment)}

{build_instant_experience_route_visual_brief(route, settings=settings, category=category)}"""
            for label, route in selected_routes
        )
        shared_realism_rules = build_sports_cave_image_realism_rules(
            include_product_lock=True
        )
        campaign_moment_visual_context = build_campaign_moment_visual_context(
            campaign_moment,
            selected_country=country,
        )
        campaign_moment_visual_block = (
            f"\n\n{campaign_moment_visual_context}"
            if campaign_moment_visual_context
            else ""
        )
        return f"""INSTANT EXPERIENCE VISUAL REQUIREMENTS

Active route outputs: {route_labels}

{package_count_rule}

Each returned cover prompt must remain fully standalone and must contain:
- Exact product identity: {product_name}
- Exact selected sport and country: {category}, {country}
- Active creative route.
- Exact approved overlay wording for that option.
- Route-specific room, wall, material, camera, shot, lens and lighting direction.
- Product/artwork lock.
- Frame and glass realism.
- Correct physical mounting.
- Room realism.
- Structured freshness instructions.
- Sport/country adaptation.
- Exact 1:1 composition for a 1024 x 1024 square cover.
- No automatic image generation.

Do not claim that prompt wording alone guarantees exact pixels. The returned asset must be checked before upload; if Sports Cave OS imports the generated image, it must validate that the asset is square before export.

IMAGE GENERATION PROMPTS — COPY ONE AT A TIME

Print one complete "INSTANT EXPERIENCE COVER IMAGE PROMPT" inside each returned option. Do not merge the prompts. Do not refer to rules elsewhere in the returned cover prompt.

SHARED PRODUCT AND REALISM BLOCK — COPY INTO EACH RETURNED COVER PROMPT EXACTLY ONCE

{shared_realism_rules}

{build_instant_experience_freshness_block(settings, category=category, recent_fingerprints=recent_instant_experience_fingerprints)}

{build_instant_experience_route_gate_block(settings)}
{campaign_moment_visual_block}

ROUTE-SPECIFIC COVER REQUIREMENTS

{route_visuals}

Never invent edition quantities, sale prices, discounts, signatures, logos, athlete names, achievements, dates, rivalries, product details or scarcity facts.

The response is incomplete unless it contains {route_prompt_count} complete standalone Instant Experience cover prompt(s)."""

    layout_rules = build_default_instant_experience_cover_prompt_requirements(
        product_name,
        category,
        country,
    )
    product_lock = build_product_lock_visual_rules()
    frame_and_glass_rules = build_frame_and_glass_visual_rules()
    room_realism_rules = build_room_realism_visual_rules()
    variation_lock = build_last_image_variation_visual_rules()
    sport_country_adaptation = build_sport_country_visual_adaptation(
        category,
        country,
    )
    shared_realism_rules = build_sports_cave_image_realism_rules(
        include_product_lock=True
    )
    scarcity_rules = """Use the exact default overlay text supplied above. Do not replace it with generated copy, alternate scarcity wording, a different CTA, a fake button or an inferred edition claim."""
    campaign_moment_visual_context = build_campaign_moment_visual_context(
        campaign_moment,
        selected_country=country,
    )
    campaign_moment_visual_block = (
        f"\n\n{campaign_moment_visual_context}"
        if campaign_moment_visual_context
        else ""
    )

    return f"""INSTANT EXPERIENCE VISUAL REQUIREMENTS

After every existing Instant Experience primary-text, headline, call-to-action, setup and URL-parameter field, output exactly one complete cover-image prompt. Do not output five prompts.

Tailor the cover to the selected product name, selected sport, selected country, generated Instant Experience headline, generated primary text, approved scarcity claim, selected CTA, emotional theme and uploaded framed artwork. It must not be a generic reusable collector-room prompt.

The response is incomplete unless it contains the exact image-generation section heading shown below followed by the complete Instant Experience cover prompt heading. Write the entire production-ready cover prompt in full. Do not replace it with Creative direction, a short cover brief, a shared base prompt, a list of changes or a reference to rules elsewhere.

IMAGE GENERATION PROMPTS — COPY ONE AT A TIME

INSTANT EXPERIENCE COVER IMAGE PROMPT

{layout_rules}

{product_lock}

{frame_and_glass_rules}

{room_realism_rules}

{variation_lock}

{sport_country_adaptation}

{shared_realism_rules}

{scarcity_rules}{campaign_moment_visual_block}

Never invent edition quantities, sale prices, discounts, signatures, logos, athlete names, achievements, dates, rivalries, product details or scarcity facts.

The one cover prompt must be fully standalone and must contain the complete product-lock, frame-and-glass, room-realism, LAST-IMAGE VARIATION LOCK, sport-and-country adaptation and cover-layout requirements printed above. Do not refer to shared rules elsewhere in the response.

Return exactly one cover-image prompt and no additional image prompts."""


def build_single_image_video_visual_output_requirements(campaign_moment=None, *, selected_country=""):
    campaign_moment_visual_context = build_campaign_moment_visual_context(
        campaign_moment,
        selected_country=selected_country,
    )
    campaign_moment_visual_block = (
        f"\n\n{campaign_moment_visual_context}"
        if campaign_moment_visual_context
        else ""
    )
    return """SINGLE IMAGE / VIDEO VISUAL REQUIREMENTS

Preserve the existing Single Image / Video route and output fields.

Upgrade its existing creative brief into exactly one complete standalone creative prompt using the dynamic room-realism, product-lock, frame-and-glass, LAST-IMAGE VARIATION LOCK and sport-and-country adaptation rules. Do not create a five-prompt Carousel sequence.

Place this one enhanced creative prompt after every existing copy, headline, description, CTA, setup and URL-parameter field.

{campaign_moment_visual_block}

CREATIVE PROMPT FOR SINGLE IMAGE/VIDEO

[one complete standalone image or video prompt that repeats the complete LAST-IMAGE VARIATION LOCK instructions]

Return exactly one creative prompt.""".format(
        campaign_moment_visual_block=campaign_moment_visual_block
    )


def build_ads_text_first_image_generation_gate(campaign_type, instant_experience_settings=None):
    campaign_type = _normalise_option_label(campaign_type) or "selected campaign"
    if campaign_type == "Carousel":
        format_detail = (
            "For Carousel campaigns, the first text-only response must include the full campaign strategy, "
            "all primary text, all headlines, all descriptions, CTA, the purpose and hook of Cards 1-5, "
            "the exact on-image text for each card where applicable, and five complete, separately copyable "
            "image prompts. Card 1 must remain the strongest, closest and most scroll-stopping product hero; "
            "Cards 2-4 may show more environment while keeping the framed artwork dominant; Card 5 must focus "
            "on scarcity and final conversion while keeping the product prominent. Preserve the existing "
            "17-character Carousel headline and description validation, country terminology, optional event "
            "relevance, strict artwork lock, frame realism, product dominance and photorealism rules."
        )
    elif campaign_type == "Instant Experience":
        format_detail = (
            "For Instant Experience campaigns, the first text-only response must include exactly one easy-to-copy "
            "grouped package for Premium Scarcity Right Angle, Premium Scarcity Straight On and Premium Scarcity Left Angle. Each group must contain one complete standalone "
            "cover image prompt followed by a three-row Markdown table for Description Key, Description Label, Description Copy, Headline and CTA. The response "
            "must contain nine total ad-copy combinations and one shared Instant Experience setup block after the groups. "
            "Do not include Meta link-description fields, Meta Ad Description fields, "
            "Campaign Strategy essays, route-selection packages, rejected alternatives or follow-up generation questions."
        )
    elif campaign_type == "Single Image / Video":
        format_detail = (
            "For Single Image / Video campaigns, the first text-only response must include the complete campaign "
            "strategy, copy package and one complete, separately copyable, production-ready creative prompt before "
            "asking for approval to generate anything."
        )
    else:
        format_detail = (
            "For this campaign, the first text-only response must include the complete campaign strategy, copy "
            "package and every complete, separately copyable, production-ready visual prompt before asking for "
            "approval to generate anything."
        )

    if campaign_type == "Instant Experience":
        ad_package_items = """1. GROUP 1 — PREMIUM SCARCITY — RIGHT ANGLE with one IMAGE GENERATION PROMPT and one three-row COPY VARIATIONS table.
2. GROUP 2 — PREMIUM SCARCITY — STRAIGHT ON with one IMAGE GENERATION PROMPT and one three-row COPY VARIATIONS table.
3. GROUP 3 — PREMIUM SCARCITY — LEFT ANGLE with one IMAGE GENERATION PROMPT and one three-row COPY VARIATIONS table.
4. Exactly nine complete ad-copy combinations total using the ordered description keys legacy_standard, framed_greatness and choose_a_side.
5. Exactly one shared INSTANT EXPERIENCE SETUP block after the three groups.
6. Relevant placement, sizing, export, consistency, artwork-preservation and realism instructions.

No separate Meta link-description or Meta Ad Description field is allowed."""
    else:
        ad_package_items = """1. Campaign objective and funnel stage.
2. Target market and audience.
3. Main emotional/creative angle.
4. Primary ad text variants.
5. Headlines.
6. Description lines.
7. CTA recommendation.
8. Optional event or seasonal integration, when supplied.
9. Card-by-card or creative-by-creative strategy.
10. The text shown on each creative, where applicable.
11. A complete production-ready image prompt for every required image.
12. Relevant placement, sizing, export, consistency, artwork-preservation and realism instructions."""

    approval_question = "Would you like me to generate Card 1?"
    if campaign_type == "Instant Experience":
        completion_instruction = (
            "After GROUP 3 — PREMIUM SCARCITY — LEFT ANGLE and the shared INSTANT EXPERIENCE SETUP block are complete, stop. "
            "Do not ask which cover to generate and do not ask a follow-up generation question."
        )
    else:
        completion_instruction = (
            "After presenting the entire campaign package and every required image prompt, "
            "finish the response with exactly:\n"
            f'"{approval_question}"'
        )
    direct_instruction_examples = (
        '"generate the image now", "generate the Premium Scarcity Right Angle cover" or "generate the Premium Scarcity Left Angle cover"'
        if campaign_type == "Instant Experience"
        else '"generate the image now", "generate Card 1" or "generate FEEL"'
    )

    return f"""TEXT-FIRST IMAGE-GENERATION GATE - MANDATORY

Your first response must be text and planning only. Do not call, invoke, open or use any image-generation tool in the first response, even if artwork or product images are attached, even if this Ads prompt describes an image, and even if this Ads prompt contains the words "image prompt", "create", "generate", "cover prompt" or "creative prompt".

Having artwork attached, describing an image or including production-ready image prompt wording must not be treated as permission to create an image automatically. Any imperative wording inside an image-prompt block is copy that you must print for the user; it is not an instruction to generate an image during the first response.

The first response must provide the complete ad campaign package in chat before any image generation:
{ad_package_items}

Print every image prompt in full in clearly separated, copyable blocks. Do not shorten, summarise, collapse or hide them behind buttons. Every image prompt must be self-contained so the user can copy and paste any individual prompt into a fresh ChatGPT conversation without relying on earlier messages.

{format_detail}

{completion_instruction}

Then wait for explicit approval before generating anything. If the user later asks for a specific cover or card, generate only that requested image, then ask whether to proceed. Continue one image at a time unless the user explicitly requests multiple images.

A direct and unmistakable instruction such as {direct_instruction_examples} is permission to generate only that requested image immediately. Do not treat general campaign setup, attached artwork, image-prompt text or pasted Ads prompts as that permission."""


def build_campaign_visual_output_contract(
    product_name,
    category,
    country,
    campaign_type,
    *,
    product_url="",
    template_key=None,
    variation_token="",
    campaign_moment=None,
    product_metadata=None,
    instant_experience_settings=None,
    recent_instant_experience_fingerprints=None,
):
    product_name = _clean_product_name(product_name)
    variation_token = _normalise_option_label(variation_token) or "standard"
    if campaign_type == "Carousel":
        campaign_requirements = build_carousel_visual_output_requirements(
            template_key,
            campaign_moment,
            product_name=product_name,
            category=category,
            selected_country=country,
        )
    elif campaign_type == "Instant Experience":
        campaign_requirements = build_instant_experience_visual_output_requirements(
            template_key,
            product_name=product_name,
            category=category,
            country=country,
            product_url=product_url,
            campaign_moment=campaign_moment,
            product_metadata=product_metadata,
            variation_token=variation_token,
            instant_experience_settings=instant_experience_settings,
            recent_instant_experience_fingerprints=recent_instant_experience_fingerprints,
        )
    elif campaign_type == "Single Image / Video":
        campaign_requirements = build_single_image_video_visual_output_requirements(
            campaign_moment,
            selected_country=country,
        )
    else:
        return ""
    contract_version = ads_prompt_contract_version_for_campaign(campaign_type).replace("; ", "\n")
    if campaign_type == "Instant Experience":
        copy_schema_preservation = (
            "Return the finished standard Instant Experience output in this order: GROUP 1 — PREMIUM SCARCITY — RIGHT ANGLE, "
            "GROUP 2 — PREMIUM SCARCITY — STRAIGHT ON, GROUP 3 — PREMIUM SCARCITY — LEFT ANGLE, then one shared INSTANT EXPERIENCE SETUP block. "
            "Each group must contain one standalone image-generation prompt followed by three matching "
            "Description Copy, Headline and CTA rows in the ordered keys legacy_standard, framed_greatness and choose_a_side. Preserve every setup instruction, destination rule and URL parameter. "
            "Do not add Meta link-description, Meta Ad Description, route-package, multi-route mode or old control-mode sections.\n\n"
            f"{INSTANT_EXPERIENCE_COPY_CSV_SUPPORT_INSTRUCTION}"
        )
    elif campaign_type == "Carousel":
        copy_schema_preservation = (
            "Return the finished existing ad-copy output first, in its existing required schema and order. "
            "Preserve all five primary-text variations, five headlines, five descriptions, five ordered "
            "carousel cards, each card CTA and destination, final setup instructions and URL parameters.\n\n"
            f"{CAROUSEL_COPY_CSV_SUPPORT_INSTRUCTION}"
        )
    else:
        copy_schema_preservation = (
            "Return the finished existing ad-copy output first, in its existing required schema and order. "
            "Preserve every existing copy field, card role, primary-text variation, headline, description, CTA, "
            "setup instruction, destination rule and URL parameter."
        )
    if campaign_type == "Instant Experience":
        visual_section_intro = (
            "Use the campaign-specific grouped route section below as the single final Instant Experience output. "
            "It already contains the standalone image-generation prompt and three matching ordered description rows for each route. "
            "Do not output a separate duplicate copy package before or after it."
        )
        final_output_instruction = (
            "Do not repeat the research, explain decisions, show internal reasoning, provide rejected alternatives "
            "or give general creative advice. Return only the three grouped route sections and the shared setup block."
        )
    else:
        visual_section_intro = "Directly beneath that complete existing output, return the campaign-specific visual section required below."
        final_output_instruction = (
            "Do not repeat the research, explain decisions, show internal reasoning, provide rejected alternatives "
            "or give general creative advice. Return only the finished ad output followed by the finished visual prompt or prompts."
        )

    if campaign_type == "Instant Experience":
        visual_safeguards = ""
        final_question = ""
    else:
        visual_safeguards = f"""{build_product_lock_visual_rules()}

{build_frame_and_glass_visual_rules()}

{build_room_realism_visual_rules()}

{build_last_image_variation_visual_rules()}

{build_sport_country_visual_adaptation(category, country)}

{build_sports_cave_image_realism_rules(include_product_lock=True)}"""
        final_question = "Would you like me to generate Card 1?"
    if campaign_type == "Instant Experience":
        final_response_termination = (
            "Only after GROUP 1 — PREMIUM SCARCITY — RIGHT ANGLE, GROUP 2 — PREMIUM SCARCITY — STRAIGHT ON, "
            "GROUP 3 — PREMIUM SCARCITY — LEFT ANGLE "
            "and the shared INSTANT EXPERIENCE SETUP block have been printed, stop. "
            "Do not ask a follow-up question and do not generate images."
        )
    else:
        final_response_termination = (
            "Only after the complete campaign package and every full image-generation prompt above "
            "have been printed, end the first response with exactly this sentence and nothing after it:\n\n"
            f"{final_question}"
        )

    return f"""MASTER RESPONSE AND VISUAL OUTPUT CONTRACT

{contract_version}

Selected product name: {product_name}
Selected sport category: {category}
Selected country: {country}
Selected campaign type: {campaign_type}
Creative variation token: {variation_token}

{SPORTS_CAVE_ADS_FACTUAL_WORDING_GATE_V1}

{copy_schema_preservation}

{visual_section_intro}

This response-order rule controls placement only. It does not replace, rewrite, weaken or omit any earlier approved copy instruction.

FINAL OUTPUT OVERRIDE - HIGHEST PRIORITY

Any earlier "OUTPUT EXACTLY IN THIS FORMAT" instruction controls only the ad-copy portion. It is not permission to stop after card copy, Creative direction, CTA guidance or a short visual brief. The response is incomplete until the complete campaign-specific image-generation prompt section below has also been printed in full.

If an earlier campaign schema already names an image prompt, cover prompt, creative prompt or Creative direction field, treat that earlier field as supplementary specification for the final visual section below. Move and upgrade that visual guidance to the final position. Do not output a preliminary brief, duplicate visual field or second prompt. The final campaign-specific visual heading, exact headings and prompt count below are authoritative.

{final_output_instruction}

Treat the creative variation token only as a cue for a fresh interpretation. Never display it in ad copy or inside an image.

{build_ads_text_first_image_generation_gate(campaign_type, instant_experience_settings)}

{visual_safeguards}

{campaign_requirements}

FINAL RESPONSE TERMINATION - MANDATORY

{final_response_termination}"""


def apply_campaign_visual_output_contract(
    prompt,
    *,
    product_name,
    category,
    country,
    campaign_type,
    product_url="",
    template_key=None,
    variation_token="",
    campaign_moment=None,
    product_metadata=None,
    instant_experience_settings=None,
    recent_instant_experience_fingerprints=None,
):
    if not prompt:
        return prompt
    marker = "MASTER RESPONSE AND VISUAL OUTPUT CONTRACT"
    expected_version = ads_prompt_contract_version_for_campaign(campaign_type)
    if expected_version in prompt:
        return prompt
    if campaign_type != "Instant Experience" and ADS_PROMPT_CONTRACT_VERSION in prompt:
        return prompt
    if marker in prompt:
        prompt = prompt[:prompt.index(marker)].rstrip()
    contract = build_campaign_visual_output_contract(
        product_name,
        category,
        country,
        campaign_type,
        product_url=product_url,
        template_key=template_key,
        variation_token=variation_token,
        campaign_moment=campaign_moment,
        product_metadata=product_metadata,
        instant_experience_settings=instant_experience_settings,
        recent_instant_experience_fingerprints=recent_instant_experience_fingerprints,
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


def build_instant_experience_route_copy_diversity_rules(settings=None):
    settings = normalize_instant_experience_settings(settings)
    selected_routes = ", ".join(route for _label, route in instant_experience_selected_routes(settings))
    return f"""{META_WINNER_COPY_BLOCK_VERSION}

This block strengthens Instant Experience route selection only. Preserve the active route output schema, CTA separation, URL parameters, localisation, claim safeguards and all product-accuracy protections.

INSTANT EXPERIENCE ROUTE COPY DIVERSITY

- Active route set: {selected_routes}.
- Each returned option must have one dominant psychological job.
- No shared opening sentence.
- No duplicated headline.
- No duplicated creative CTA.
- Only ACT may use the black-and-gold bottom scarcity strip.
- Only one option may use "Greatness doesn't fade."
- FEEL must not sound like ACT with scarcity lines removed.
- BELONG must not sound like an interior-design advertisement.
- Reject identical first-four-word openings.
- Reject high phrase overlap.
- Do not repeat the same proof sentence across every option.
- Do not blend nostalgia, gifting, ownership, discount and scarcity into every option.
- Use short mobile-readable paragraphs.
- Avoid generic AI language including elevate, transform, ultimate, unleash, must-have, masterpiece, conversation starter and bring your walls to life.
- Every product claim must remain fact-safe.
- Use natural selected-country English.

CLAIM AND OFFER SAFETY

- Never invent edition quantities, remaining inventory, certificates, signatures, manufacturing claims, sport details, milestones, rivalry details, discounts or product facts.
- Only use an offer when the active route explicitly supports offer language and the exact offer has been supplied.
- Treat the Meta Ad Description as supporting copy because it may not display in every placement.
- Do not place essential commercial information only in the Description unless the selected urgency placement deliberately chooses Meta description only.

SILENT COPY SELECTION

Before returning the campaign, privately compare several product-specific candidates for each active route. Reject generic, repetitive, fact-unsafe or unnatural writing. Return only the strongest finished copy in the current approved output format. Do not expose candidates, scoring notes, research or reasoning."""


def build_shared_meta_winner_copy_upgrade(campaign_type="", instant_experience_settings=None):
    if campaign_type == "Instant Experience":
        return f"""{META_WINNER_COPY_BLOCK_VERSION}

This block strengthens the standard Instant Experience grouped route output only. Preserve the approved output order, three route groups, three ordered description options per route, Headline and CTA columns, setup block, URL parameters, localisation, claim safeguards and all product-accuracy protections.

{SPORTS_CAVE_IE_CORE_COPY_QUALITY_RULES_V2}

{build_instant_experience_creative_cta_rules()}

STANDARD INSTANT EXPERIENCE PREMIUM ROOM V4 COPY DIVERSITY

- Return exactly three grouped routes: GROUP 1 - PREMIUM SCARCITY - RIGHT ANGLE, GROUP 2 - PREMIUM SCARCITY - STRAIGHT ON and GROUP 3 - PREMIUM SCARCITY - LEFT ANGLE.
- Each route must contain exactly one IMAGE GENERATION PROMPT and one COPY VARIATIONS table.
- Each route table must contain exactly three completed description rows in this order: legacy_standard, framed_greatness, choose_a_side.
- Each row must contain one complete Description Copy, one Headline and one CTA.
- The full response must contain exactly nine complete ad-copy combinations.
- No separate Meta link-description or Meta Ad Description field is allowed.
- No row may be placeholder copy.
- The same three product-aware Description Copy values must be associated with all three image routes; do not rewrite the long description merely because the camera angle changes.
- All three routes share the same premium Sports Cave scarcity headline system and CTA while using different camera angles, room details, environmental cues and supporting FOMO lines.
- Route 1 must resolve the Slight Right Angle cover with the supporting FOMO line: Once they're claimed, this edition retires forever.
- Route 2 must resolve the Straight On cover with the supporting FOMO line: When the final one is claimed, it's gone for good.
- Route 3 must resolve the Slight Left Angle cover with the supporting FOMO line: Released once. When they're gone, they stay gone.
- No duplicated headline.
- Every CTA must be one approved direct edition-acquisition CTA. Description 1 in each route must use CTA field Claim Your Edition.
- All three routes must remain scarcity-first while using the same ordered product-aware description archetypes and materially different image scene compositions.
- Description 1 must follow Legacy Standard.
- Description 2 must follow Framed Greatness.
- Description 3 must follow Choose a Side.
- The on-image headline must be ONLY {{verified edition limit}} WILL EVER EXIST only when the edition limit is verified by supplied product data or an approved claim path.
- When the verified limit is 100, the headline must resolve exactly to ONLY 100 WILL EVER EXIST.
- If a verified edition limit is unavailable, use the existing safe evidence-gated fallback instead of inventing a quantity or finality claim.
- A supplied offer may be used only when exact, fact-safe and permitted by the existing campaign contract; never let it replace the edition scarcity.
- Every claim must remain supported by the product title, supplied facts, visible artwork or approved claim path.
- Use natural selected-country English.
- Generate the three description variants once from product context, then reuse the same ordered description set for the right, front and left route tables. Generate all copy first in working memory so each standalone image prompt can print its exact permitted wording and the exact forbidden Headline/CTA strings assigned to the other routes. Do not expose this working order or change the approved response order."""
    single_primary_rule = (
        "Instant Experience must always preserve exactly three route groups with three Description Copy, "
        "three Headline and three CTA options inside each group."
        if campaign_type == "Instant Experience"
        else (
            "If the approved campaign-specific template requires exactly one primary text rather than five, "
            "preserve that quantity. Silently consider these angles and return only the strongest compatible "
            "final version in the existing schema."
        )
    )
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

Greatness doesn't fade.
It gets framed.

- Do not repeat greatness in the middle or closing.
- Write one compact product-specific paragraph using the supplied product name, supported people, team, vehicle, event or moment, selected sport, selected country, fan emotion and any verified era, rivalry, mentality or memory.
- Follow with one short emotional paragraph about collector ownership or display appeal.
- Close with: Limited to {{authentic edition limit}} worldwide. Secure your edition before it's gone.
- Replace {{authentic edition limit}} with the confirmed edition quantity from the approved claim path, supplied product information or visible artwork. Never leave the placeholder in final copy.
- When the confirmed edition limit is 100, write exactly: Limited to 100 worldwide. Secure your edition before it's gone.
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

{single_primary_rule}

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
- Never invent edition quantities, remaining inventory, certificates, signatures, manufacturing claims, sport details, milestones, rivalry details, discounts or product facts."""


def apply_shared_meta_winner_copy_upgrade(prompt, campaign_type, instant_experience_settings=None):
    if campaign_type not in {"Carousel", "Instant Experience"} or not prompt:
        return prompt
    if META_WINNER_COPY_BLOCK_VERSION in prompt:
        return prompt
    return f"{prompt.rstrip()}\n\n{build_shared_meta_winner_copy_upgrade(campaign_type, instant_experience_settings)}"


def compose_final_ads_prompt(
    prompt,
    *,
    category,
    country,
    campaign_type,
    include_primary_text_variations=False,
    product_name="",
    product_url="",
    template_key=None,
    variation_token="",
    campaign_moment=None,
    product_metadata=None,
    instant_experience_settings=None,
    recent_instant_experience_fingerprints=None,
):
    if not prompt:
        return prompt
    prompt = apply_campaign_copy_rule_blocks(
        prompt,
        campaign_type,
        include_primary_text_variations=include_primary_text_variations,
        category=category,
    )
    prompt = apply_shared_meta_winner_copy_upgrade(
        prompt,
        campaign_type,
        instant_experience_settings,
    )
    prompt = apply_country_language_guidance(prompt, country)
    prompt = apply_campaign_moment_copy_relevance_layer(
        prompt,
        campaign_moment,
        selected_country=country,
        campaign_type=campaign_type,
    )
    prompt = apply_meta_url_parameters_guidance(prompt)
    if product_name:
        prompt = apply_campaign_visual_output_contract(
            prompt,
            product_name=product_name,
            category=category,
            country=country,
            campaign_type=campaign_type,
            product_url=product_url,
            template_key=template_key,
            variation_token=variation_token,
            campaign_moment=campaign_moment,
            product_metadata=product_metadata,
            instant_experience_settings=instant_experience_settings,
            recent_instant_experience_fingerprints=recent_instant_experience_fingerprints,
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

OUTPUT THE AD-COPY PORTION IN THIS FORMAT

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
    return build_standard_instant_experience_prompt(
        product_name,
        category,
        country,
        campaign_type,
        product_url=product_url,
        specific_pattern=True,
    )
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

Generate exactly:

- five complete Primary Text options
- five Headline options
- five Call To Action button-label options
- one clear Meta Instant Experience setup guide

Do not generate descriptions, carousel cards, optional rejected alternatives or writing notes.

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

Use this exact Sports Cave line in at least one Primary Text option unless an existing protected brand-setting system supplies an approved alternative.

Across the five options, create five genuinely different product-specific identity and legacy angles.

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

Use the exact closing line in at least one option unless the shared country-language rules require only a minor spelling or terminology adjustment. Do not repeat the same closing line or scarcity sentence across every option.

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

Choose the strongest distinct angles or compatible blends for the actual artwork.

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

FIVE OPTION QUALITY RULE

Before answering, internally consider several possible angles:

- fan identity
- nostalgia
- milestone
- rivalry
- legacy
- historic moment
- collector ownership
- scarcity

Choose the five strongest distinct angles or compatible blends.

Return exactly five finished Primary Text options.

Do not show rejected alternatives or writing notes.

Apply this test:

If this copy could work for almost any baseball artwork, rewrite it with stronger product-specific identity.

HEADLINE RULES

Generate exactly five headline options.

The headline must be:

- product-specific
- emotionally strong
- easy to read in Meta
- suitable beneath an Instant Experience cover
- connected to the artwork
- stronger than generic phrases such as Baseball History or Limited Edition

Good headline directions include the product title, recognised milestone, rivalry identity, era identity, ownership or scarcity.

Use the actual product and make the five options meaningfully different.

Do not invent facts.

Do not apply Carousel character limits to the Instant Experience headline.

CALL TO ACTION

Generate exactly five creative CTA options using only Claim Your Edition, Secure Your Edition or Own This Edition.

The Description Copy must follow its assigned archetype ending. Keep Meta's native fixed button as Shop Now.

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

9. Under any catalogue descriptor or subtitle field that Meta requires, use:
   Limited Edition

10. Under Fixed button, set the label to:
    Shop Now

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

OUTPUT THE AD-COPY PORTION IN THIS FORMAT

PRIMARY TEXT

1. [complete primary text]
2. [complete primary text]
3. [complete primary text]
4. [complete primary text]
5. [complete primary text]

HEADLINES

1. [headline]
2. [headline]
3. [headline]
4. [headline]
5. [headline]

CALL TO ACTION

1. [Meta CTA label]
2. [Meta CTA label]
3. [Meta CTA label]
4. [Meta CTA label]
5. [Meta CTA label]

INSTANT EXPERIENCE SETUP

[the required setup instructions]

FINAL QUALITY CHECK

Before returning the output, confirm:

- Exactly 5 Primary Text options are provided.
- Exactly 5 Headlines are provided.
- Exactly 5 Call To Action button-label options are provided.
- No separate Meta link-description or Meta Ad Description field is present.
- Instant Experience setup instructions are included.
- The generated Instant Experience cover upload step is specified.
- Shopify Product Catalog is specified.
- {BASEBALL_INSTANT_EXPERIENCE_PRODUCT_SET_NAME} product set is specified.
- Product headline is product.name.
- Catalogue descriptor is Limited Edition when Meta requires one.
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
- No Carousel rules have been applied to the Instant Experience headline."""


def build_product_url_instruction(product_url):
    product_url = _clean_product_url(product_url)
    if product_url:
        return f"Use this selected product page URL where a destination URL is required: {product_url}"
    return "Use the selected product's live product page URL where a destination URL is required. Do not invent a URL."


def build_country_campaign_localisation_note(category, country, *, campaign_type=""):
    country_key = normalize_country_language_key(country)
    category_key = str(category or "").strip()
    if category_key == "Football":
        if country_key == "Australia":
            if campaign_type == "Instant Experience":
                return "AU football/soccer localisation: use football or soccer depending on the product context. Keep the approved This Edition creative CTA."
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
- Additional short copy cues for this category: {angle["description_examples"]}.
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


def build_standard_instant_experience_prompt(
    product_name,
    category,
    country,
    campaign_type,
    product_url="",
    *,
    specific_pattern=False,
    campaign_moment=None,
    product_metadata=None,
    variation_token="",
):
    product_name = _clean_product_name(product_name)
    product_url = _clean_product_url(product_url)
    category_label = str(category or "").upper()
    pattern_heading = (
        f"SPORTS CAVE {category_label} INSTANT EXPERIENCE STANDARD WORKFLOW"
        if specific_pattern
        else "SPORTS CAVE STANDARD INSTANT EXPERIENCE WORKFLOW"
    )
    if category == "Baseball":
        pattern_heading = "SPORTS CAVE BASEBALL INSTANT EXPERIENCE AD"
    fallback_note = (
        ""
        if specific_pattern or category in {"Baseball", "Football"}
        else "\nINTERNAL NOTE\nUsing generic Sports Cave winner pattern for this category. Do not include this note in customer-facing copy blocks.\n"
    )
    category_block = build_category_winner_angle_block(category, campaign_type, country)
    exact_offer = _standard_instant_experience_exact_offer(campaign_moment)
    product_context = resolve_instant_experience_product_context(
        product_name,
        category,
        product_metadata=product_metadata,
        campaign_moment=campaign_moment,
    )
    description_context = resolve_instant_experience_description_context(
        product_name,
        category,
        product_metadata=product_metadata,
        campaign_moment=campaign_moment,
        country=country,
    )
    edition_context_line = (
        f"Verified edition limit: {product_context['edition_limit']} "
        f"({product_context['edition_limit_source']})."
        if product_context.get("edition_limit")
        else "Verified edition limit: not supplied; use evidence-gated non-numeric fallback wording."
    )
    claim_block = (
        build_baseball_instant_experience_claim_block()
        if category == "Baseball"
        else "Use only verified edition, certificate, manufacturing, review or scarcity claims supplied by the product data or visible artwork. Never invent proof."
    )
    product_set_guidance = (
        BASEBALL_INSTANT_EXPERIENCE_PRODUCT_SET_NAME
        if category == "Baseball"
        else f"the connected {category} product set"
    )
    baseball_fact_safety = (
        "\nBASEBALL FACT-SAFETY\n\n"
        "Authentic baseball terms must remain baseball-specific in every country, including home run, "
        "stolen base, at the plate, swing, inning, score, baseball fan, ballpark and postseason where appropriate.\n\n"
        "Country-language rules change spelling, phrasing, retail language and tone. They do not change player identity, "
        "baseball facts, official product title, artwork text or verified commercial claims.\n"
        if category == "Baseball"
        else ""
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

Use the supplied product name as the source of identity. Do not identify or guess a person, club, country, achievement, year, record, final, trophy, rivalry or manufacturing origin solely from the image or selected country.

{build_country_campaign_localisation_note(category, country, campaign_type="Instant Experience")}

{build_universal_sports_cave_rules(category)}

{category_block}
{baseball_fact_safety}

APPROVED CLAIM PATH

{claim_block}

PRODUCT-AWARE ROOM AND SCARCITY METADATA

- Product sport used for room matching: {product_context['product_sport']}
- Product era classification: {product_context['product_era']}
- Artwork mood classification: {product_context['artwork_mood']}
- Campaign or gifting context: {product_context['campaign_context']}
- {edition_context_line}

PRODUCT-AWARE DESCRIPTION SYSTEM

{build_instant_experience_description_generation_prompt(description_context)}

PROMOTION OR OFFER

Exact Promotion or Offer entered: {exact_offer or "None supplied"}

Serialize this field independently of Moment Type. If a non-empty offer is supplied, preserve it exactly in copy only when the product facts and campaign context support it. Never place an offer in the on-image prompt, never let it replace verified edition scarcity and never invent, rewrite, improve or expand the offer.

OBJECTIVE

Create one standard Meta Instant Experience package grouped into three clear routes:

1. PREMIUM SCARCITY — RIGHT ANGLE
2. PREMIUM SCARCITY — STRAIGHT ON
3. PREMIUM SCARCITY — LEFT ANGLE

Return exactly these sections in this order:

1. GROUP 1 — PREMIUM SCARCITY — RIGHT ANGLE
2. GROUP 2 — PREMIUM SCARCITY — STRAIGHT ON
3. GROUP 3 — PREMIUM SCARCITY — LEFT ANGLE
4. INSTANT EXPERIENCE SETUP

Do not output five global copy variations.
Do not output one global copy table disconnected from the images.
Do not output Campaign Strategy essays, rejected alternatives, placeholder copy, Meta link-description fields, Meta Ad Description fields, separate creative/fixed CTA fields, FEEL/BELONG/ACT packages, route selectors, multi-route mode language, old control-mode labels or collection-page routing.
Do not ask which image to generate.
Do not generate images.

GROUP OUTPUT CONTRACT

For each group, output exactly this structure:

GROUP [number] — [ROUTE]

IMAGE GENERATION PROMPT

[one complete standalone image-generation prompt for this route]

COPY VARIATIONS

| Description | Description Key | Description Label | Description Copy | Headline | CTA |
| ----------- | --------------- | ----------------- | ---------------- | -------- | --- |
| 1 | legacy_standard | Description 1 — Legacy Standard | Complete Legacy Standard description copy | Complete headline | Complete CTA |
| 2 | framed_greatness | Description 2 — Framed Greatness | Complete Framed Greatness description copy | Complete headline | Complete CTA |
| 3 | choose_a_side | Description 3 — Choose a Side | Complete Choose a Side description copy | Complete headline | Complete CTA |

Every group table must contain exactly three completed rows in the fixed description order. Across all groups, output exactly nine complete ad-copy combinations.

Table rules:
- Keep each table cell on one line so Nathan can copy and paste into the matching route section in the app.
- Escape any vertical-bar characters that would break the Markdown table.
- Preserve paragraph breaks inside each Description Copy cell where the platform supports multiline cells, or use visible line breaks that can be pasted into the matching description field.
- Never leave placeholders such as Description copy option 2, Headline option 3, Shop Now repeated, Add copy here, Complete copy or To be generated in the returned answer.
- Description 1 in each route supplies copy aligned with that route's exact on-image CTA field.
- Descriptions 2 and 3 are alternative product-aware description options for testing with the same route image.
- The three Description Copy values must be the same ordered product-aware set in every route table.
- Do not put the full Description Copy on any image.

ROUTE-SPECIFIC COPY RULES

PREMIUM SCARCITY — RIGHT ANGLE:
- Purpose: convert through a slight right-angle product photograph, a premium collector-home setting and verified scarcity when available.
- Camera-supporting line: Once they're claimed, this edition retires forever.
- Use the route FOMO line only when a verified finite edition limit exists.
- When no verified edition limit exists, use non-numeric collector-release wording and do not imply retirement or final stock.
- Description 1 must use CTA field Claim Your Edition.

PREMIUM SCARCITY — STRAIGHT ON:
- Purpose: deliver the clearest direct scarcity hero, using the most balanced and readable front-facing product photograph.
- Camera-supporting line: When the final one is claimed, it's gone for good.
- Use the route FOMO line only when a verified finite edition limit exists.
- When no verified edition limit exists, use non-numeric collector-release wording and do not imply retirement or final stock.
- Description 1 must use CTA field Claim Your Edition.

PREMIUM SCARCITY — LEFT ANGLE:
- Purpose: complete the package with a complementary left-angle product photograph that is not a mirrored duplicate of the right-angle route.
- Camera-supporting line: Released once. When they're gone, they stay gone.
- Use the route FOMO line only when a verified finite edition limit exists.
- When no verified edition limit exists, use non-numeric collector-release wording and do not imply retirement or final stock.
- Description 1 must use CTA field Claim Your Edition.

COPY FIELD FORMAT RULES

- Every Description Copy must follow its assigned archetype structure and preserve intentional blank lines.
- Every Headline must contain no more than 4-6 words. 4 to 6 words max.
- Every CTA must use one exact approved direct edition-acquisition phrase from the central contract.
- Every CTA must pass the central Instant Experience creative CTA contract.
- Keep the fixed Meta/Instant Experience button as: Shop Now.
- Preserve the current Headline and CTA columns and all existing row counts. The long copy column is the Instant Experience Description Copy, stored internally as the existing primary_text field for compatibility.

INSTANT EXPERIENCE SETUP

After the three grouped route packages, output one shared setup block only.

The setup block must include:
- Use the Meta Instant Experience Product template.
- Generate and upload the three covers from the three image prompts below.
- Featured product headline uses the exact product name: {product_name}
- Catalogue product headline field uses: product.name
- Product descriptor/subtitle uses: Limited Edition when approved.
- Keep the connected category catalogue attached.
- Exact product-set guidance: {product_set_guidance}
- Fixed button label remains: Shop Now.
- Fixed button destination uses the exact supplied product-page URL: {product_url or "[exact supplied product-page URL]"}
- URL parameters use exactly: {META_AD_URL_PARAMETERS}
- Maintain the current product-page-plus-catalogue sales path.
- Do not introduce collection-page routing in this workflow.

FINAL COPY CHECK

- The output contains exactly three grouped route sections.
- Each route contains one image-generation prompt and one three-row description table.
- The output contains exactly nine complete ad-copy combinations.
- No separate Meta link-description or Meta Ad Description field is present.
- No placeholder copy remains.
- All three groups are premium scarcity-led routes with distinct camera roles, room variables and supporting FOMO lines.
- Premium Scarcity — Right Angle uses the slight right-angle camera role.
- Premium Scarcity — Straight On uses the clear straight-on camera role.
- Premium Scarcity — Left Angle uses the slight left-angle camera role and is not a mirror of the right route.
- Every creative CTA belongs to the approved direct edition-acquisition family.
- Description 1 for all three routes uses Claim Your Edition.
- The ordered description keys are legacy_standard, framed_greatness and choose_a_side in every route.
- Promotion or Offer has been preserved exactly when used.
- Product URL and UTM parameters remain exact."""


def build_generic_instant_experience_prompt(
    product_name,
    category,
    country,
    campaign_type,
    product_url="",
    *,
    specific_pattern=False,
):
    return build_standard_instant_experience_prompt(
        product_name,
        category,
        country,
        campaign_type,
        product_url=product_url,
        specific_pattern=specific_pattern,
    )


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

OUTPUT THE AD-COPY PORTION IN THIS FORMAT

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

Claim Your Edition

Do not stop after CTA guidance or after the five Creative direction lines. Continue with the authoritative full visual-output section appended at the end of this master prompt. That final section must be headed:

IMAGE GENERATION PROMPTS — COPY ONE AT A TIME

It must then contain:

CARD 1 IMAGE GENERATION PROMPT
CARD 2 IMAGE GENERATION PROMPT
CARD 3 IMAGE GENERATION PROMPT
CARD 4 IMAGE GENERATION PROMPT
CARD 5 IMAGE GENERATION PROMPT

Each heading must be followed by its complete standalone prompt in full."""


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

OUTPUT THE AD-COPY PORTION IN THIS FORMAT

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
    campaign_moment=None,
    product_metadata=None,
    instant_experience_settings=None,
    recent_instant_experience_fingerprints=None,
):
    template_key = get_template_key(category, campaign_type)
    settings = None
    if campaign_type == "Instant Experience":
        prompt = build_standard_instant_experience_prompt(
            product_name,
            category,
            country,
            campaign_type,
            product_url=product_url,
            specific_pattern=bool(template_key),
            campaign_moment=campaign_moment,
            product_metadata=product_metadata,
            variation_token=variation_token,
        )
    elif template_key == "motorsport_carousel":
        prompt = build_motorsport_carousel_prompt(product_name, category, country, campaign_type)
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
        product_url=product_url,
        template_key=template_key,
        variation_token=variation_token,
        campaign_moment=campaign_moment,
        product_metadata=product_metadata,
        instant_experience_settings=settings,
        recent_instant_experience_fingerprints=recent_instant_experience_fingerprints,
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


def render_product_name_input(*, rows=None, result=None):
    rows = list(rows or ())
    records = build_ads_product_selector_records(rows)
    records_by_identity = {record["identity"]: record for record in records}
    prepare_ads_product_selector_state(rows, result=result)
    if records:
        selector_value = st.selectbox(
            "Product name",
            options=alphabetize_options(
                records_by_identity,
                label=lambda identity: records_by_identity.get(identity, {}).get("label") or identity,
            ),
            index=None,
            placeholder="Example: Six Laps Ahead",
            accept_new_options=True,
            filter_mode="fuzzy",
            format_func=lambda identity: (
                records_by_identity.get(identity, {}).get("label") or identity
            ),
            key=ADS_PRODUCT_SELECTOR_KEY,
            on_change=_on_ads_product_selector_changed,
            args=(rows,),
        )
    else:
        selector_value = st.text_input(
            "Product name",
            placeholder="Example: Six Laps Ahead",
            key=ADS_PRODUCT_SELECTOR_KEY,
            on_change=_on_ads_product_selector_changed,
            args=(rows,),
        )
    selection = resolve_ads_product_selector_value(
        selector_value,
        rows=rows,
        records=records,
    )
    product_name = selection.get("selected_label") or ""
    st.session_state[ADS_PRODUCT_NAME_KEY] = product_name
    return product_name, selection


def render_campaign_moment_section():
    with st.expander("Campaign Moment (Optional)", expanded=False):
        st.caption(
            "Add an occasion, sporting event or promotional period to make one copy variation more timely. Leave blank for fully evergreen ads."
        )
        type_col, name_col = st.columns([1, 2])
        with type_col:
            st.selectbox(
                "Moment Type",
                [""] + CAMPAIGN_MOMENT_TYPE_OPTIONS,
                index=0,
                format_func=lambda option: "Select a moment type" if not option else option,
                key="ads_campaign_moment_type",
            )
        with name_col:
            st.text_input(
                "Moment Name",
                placeholder="Father’s Day, NBA Playoffs, World Cup, Bathurst, Black Friday",
                key="ads_campaign_moment_name",
            )
        market_col, date_col = st.columns(2)
        with market_col:
            st.selectbox(
                "Relevant Country or Market",
                CAMPAIGN_MOMENT_MARKET_OPTIONS,
                index=0,
                key="ads_campaign_moment_market",
            )
        with date_col:
            st.date_input(
                "Event Date or End Date",
                value=None,
                key="ads_campaign_moment_date",
            )
            st.caption("Used to prevent outdated or misleading event references.")
        offer_col, strength_col = st.columns([2, 1])
        with offer_col:
            st.text_input(
                "Promotion or Offer",
                placeholder="Free shipping, 15% off 2+ editions, no offer",
                key="ads_campaign_moment_promotion",
            )
            st.caption(
                "Only the exact entered offer may be used. Leave blank to prevent discount or free-shipping claims."
            )
        with strength_col:
            st.selectbox(
                "Relevance Strength",
                CAMPAIGN_MOMENT_STRENGTH_OPTIONS,
                index=0,
                key="ads_campaign_moment_strength",
            )
        st.caption(
            "Subtle: Mention the moment naturally in one copy variation. Moderate: Make one variation clearly timely while keeping the product and collector story central. Campaign-led: Make one variation primarily about the moment, while keeping the other variations evergreen."
        )
        st.checkbox(
            "Use this moment in image prompts",
            value=False,
            key="ads_campaign_moment_include_images",
            help="Leave off to keep the event limited to ad copy. Enable only when the room, styling or visual context should subtly support the moment.",
        )
        st.caption(
            "Do not add event text, promotional overlays, prices, logos, event branding or sale stickers to generated images unless separately and explicitly requested by the existing workflow."
        )
        moment = campaign_moment_from_form_state()
        if campaign_moment_is_active(moment):
            st.caption(
                f"{moment['name']} · {moment['resolved_market']} · {moment['strength']}"
            )
        if st.button("Clear moment", key="ads-clear-campaign-moment"):
            clear_campaign_moment_state()
            st.rerun()
    return campaign_moment_from_form_state()


def record_ad_prompt_generated(
    product_name,
    category,
    country,
    campaign_type,
    *,
    instant_experience_settings=None,
    instant_experience_fingerprints=None,
):
    metadata = {
        "category": category,
        "country": country,
        "campaign_type": campaign_type,
    }
    if campaign_type == "Instant Experience":
        if instant_experience_fingerprints:
            metadata["instant_experience_fingerprints"] = instant_experience_fingerprints
    record_activity_log(
        "ad_prompt_generated",
        "Ads",
        f"Generated ad prompt: {product_name}",
        entity_type="ad_prompt",
        metadata=metadata,
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


def ads_result_context_key(
    product_id,
    product_name,
    category,
    country,
    campaign_type,
    campaign_moment=None,
    instant_experience_settings=None,
    product_metadata=None,
):
    payload_data = {
        "product_id": str(product_id or ""),
        "product_name": _clean_product_name(product_name),
        "category": str(category or ""),
        "country": str(country or ""),
        "campaign_type": str(campaign_type or ""),
    }
    moment_key = _campaign_moment_context_key(
        campaign_moment,
        selected_country=country,
    )
    if moment_key:
        payload_data["campaign_moment"] = moment_key
    if campaign_type == "Instant Experience" and isinstance(product_metadata, dict):
        payload_data["instant_experience_product_metadata"] = {
            "edition_limit": product_metadata.get("edition_limit"),
            "edition_limit_source": product_metadata.get("edition_limit_source"),
            "collections": product_metadata.get("collections"),
            "product_type": product_metadata.get("product_type"),
        }
    payload = json.dumps(payload_data, sort_keys=True, ensure_ascii=False)
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
    campaign_moment=None,
    product_metadata=None,
    instant_experience_settings=None,
    recent_instant_experience_fingerprints=None,
):
    clean_product_name = _clean_product_name(product_name)
    clean_product_id = str(product_id or "").strip()
    clean_variation_token = str(variation_token or "").strip() or build_visual_variation_token()
    clean_campaign_moment = normalize_campaign_moment(
        campaign_moment,
        selected_country=country,
    )
    clean_product_metadata = (
        dict(product_metadata)
        if isinstance(product_metadata, dict)
        else {"product_sport": _normalise_option_label(category)}
    )
    clean_instant_experience_settings = None
    instant_experience_fingerprints = (
        build_standard_instant_experience_fingerprints(
            product_name=clean_product_name,
            category=category,
            product_metadata=clean_product_metadata,
            campaign_moment=clean_campaign_moment,
            variation_token=clean_variation_token,
        )
        if campaign_type == "Instant Experience"
        else []
    )
    master_prompt = build_ads_prompt(
        clean_product_name,
        category,
        country,
        campaign_type,
        product_url=product_url,
        variation_token=clean_variation_token,
        campaign_moment=clean_campaign_moment,
        product_metadata=clean_product_metadata,
        instant_experience_settings=clean_instant_experience_settings,
        recent_instant_experience_fingerprints=recent_instant_experience_fingerprints,
    )
    return {
        "context_key": ads_result_context_key(
            clean_product_id,
            clean_product_name,
            category,
            country,
            campaign_type,
            clean_campaign_moment,
            product_metadata=clean_product_metadata,
        ),
        "product_id": clean_product_id,
        "product_name": clean_product_name,
        "category": str(category or ""),
        "country": str(country or ""),
        "campaign_type": str(campaign_type or ""),
        "product_url": _clean_product_url(product_url),
        "variation_token": clean_variation_token,
        "campaign_moment": clean_campaign_moment,
        "product_metadata": clean_product_metadata,
        "instant_experience_fingerprints": instant_experience_fingerprints,
        "recent_instant_experience_fingerprints": (
            list(recent_instant_experience_fingerprints or [])
            if campaign_type == "Instant Experience"
            else []
        ),
        "prompt_contract_version": ads_prompt_contract_version_for_campaign(campaign_type),
        "master_prompt": master_prompt,
        "generated_ad_output": master_prompt,
    }


def ads_prompt_contract_version_for_campaign(campaign_type):
    if campaign_type == "Instant Experience":
        return (
            f"{ADS_PROMPT_CONTRACT_VERSION}; "
            f"{ADS_INSTANT_EXPERIENCE_COPY_CONTRACT_VERSION}; "
            f"{ADS_INSTANT_EXPERIENCE_STANDARD_CONTRACT_VERSION}"
        )
    return ADS_PROMPT_CONTRACT_VERSION


def ensure_current_ads_result_prompt(result):
    if not isinstance(result, dict) or not result.get("master_prompt"):
        return result
    expected_version = ads_prompt_contract_version_for_campaign(result.get("campaign_type"))
    if result.get("prompt_contract_version") == expected_version:
        return result
    old_master_prompt = str(result.get("master_prompt") or "")
    old_generated_output = str(result.get("generated_ad_output") or "")
    refreshed = build_ads_result_record(
        result.get("product_name"),
        result.get("category"),
        result.get("country"),
        result.get("campaign_type"),
        product_id=result.get("product_id"),
        product_url=result.get("product_url"),
        variation_token=result.get("variation_token"),
        campaign_moment=result.get("campaign_moment"),
        product_metadata=result.get("product_metadata"),
        instant_experience_settings=result.get("instant_experience_settings"),
        recent_instant_experience_fingerprints=result.get("recent_instant_experience_fingerprints", []),
    )
    merged = {**result, **refreshed}
    if old_generated_output and old_generated_output != old_master_prompt:
        merged["generated_ad_output"] = old_generated_output
    return merged


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
        "ad_notes": {},
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
    "instant-experience-01",
    "instant-experience-02",
    "instant-experience-03",
    "instant-experience-nostalgia",
    "instant-experience-ownership",
    "instant-experience-scarcity",
)

INSTANT_EXPERIENCE_LEGACY_SLOT_MAP = {
    "instant-experience": "instant-experience-premium-scarcity-right",
    "instant_experience": "instant-experience-premium-scarcity-right",
    "instant_experience_image": "instant-experience-premium-scarcity-right",
    "instant-experience-01": "instant-experience-premium-scarcity-right",
    "instant-experience-02": "instant-experience-premium-scarcity-front",
    "instant-experience-03": "instant-experience-premium-scarcity-left",
    "instant-experience-nostalgia": "instant-experience-premium-scarcity-right",
    "instant-experience-ownership": "instant-experience-premium-scarcity-front",
    "instant-experience-scarcity": "instant-experience-premium-scarcity-left",
}

INSTANT_EXPERIENCE_LEGACY_CONCEPT_ID_MAP = {
    "nostalgia": "premium_scarcity_right",
    "ownership": "premium_scarcity_front",
    "scarcity": "premium_scarcity_left",
}


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
        slots = {"instant-experience": dict(slots)}
    slot_specs = _instant_experience_slots_by_position()
    slot_by_id = {slot["id"]: slot for slot in slot_specs}
    outcomes = workflow.setdefault("outcomes", {})
    new_slots = {}
    new_outcomes = {}
    for slot in slot_specs:
        slot_id = slot["id"]
        if slot_id in slots:
            slot_data = dict(slots[slot_id])
            slot_data.update(
                {
                    "slot_id": slot["id"],
                    "label": slot["label"],
                    "concept_id": slot.get("concept_id"),
                    "display_name": slot.get("display_name"),
                    "supporting_label": slot.get("supporting_label"),
                    "position": slot["position"],
                }
            )
            new_slots[slot_id] = slot_data
            outcome = dict(outcomes.get(slot_id) or {})
            if outcome:
                outcome.update(
                    {
                        "label": slot["label"],
                        "concept_id": slot.get("concept_id"),
                        "concept": slot.get("display_name"),
                    }
                )
                new_outcomes[slot_id] = outcome
    for slot_id in INSTANT_EXPERIENCE_LEGACY_SLOT_IDS:
        mapped_slot_id = INSTANT_EXPERIENCE_LEGACY_SLOT_MAP.get(slot_id)
        if slot_id in slots and mapped_slot_id and mapped_slot_id not in new_slots:
            slot = slot_by_id.get(mapped_slot_id) or slot_specs[0]
            slot_data = dict(slots[slot_id])
            slot_data.update(
                {
                    "slot_id": slot["id"],
                    "label": slot["label"],
                    "concept_id": slot.get("concept_id"),
                    "display_name": slot.get("display_name"),
                    "supporting_label": slot.get("supporting_label"),
                    "position": slot["position"],
                }
            )
            new_slots[slot["id"]] = slot_data
            outcome = dict(outcomes.get(slot_id) or {})
            if outcome:
                outcome.update(
                    {
                        "label": slot["label"],
                        "concept_id": slot.get("concept_id"),
                        "concept": slot.get("display_name"),
                    }
                )
                new_outcomes[slot["id"]] = outcome
    workflow["slots"] = new_slots
    workflow["outcomes"] = new_outcomes


def _ads_image_slot_specs_for_render(result, workflow):
    slot_specs = ads_image_workflow.campaign_image_slots(result.get("campaign_type"))
    if not _is_instant_experience_result(result):
        return slot_specs
    _compact_instant_experience_slots(workflow)
    return slot_specs


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


def _ads_image_saved_count(result, workflow):
    slot_ids = {
        slot["id"]
        for slot in ads_image_workflow.campaign_image_slots(result.get("campaign_type"))
    }
    return sum(
        1
        for slot_id, outcome in (workflow.get("outcomes") or {}).items()
        if slot_id in slot_ids and outcome.get("status") == "saved"
    )


def _ads_image_failed_count(result, workflow):
    slot_ids = {
        slot["id"]
        for slot in ads_image_workflow.campaign_image_slots(result.get("campaign_type"))
    }
    return sum(
        1
        for slot_id, outcome in (workflow.get("outcomes") or {}).items()
        if slot_id in slot_ids and outcome.get("status") == "failed"
    )


def _ads_image_required_count(result):
    return len(ads_image_workflow.campaign_image_slots(result.get("campaign_type")))


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
        is_instant_experience = _is_instant_experience_result(result)
        if is_instant_experience:
            original_details = ads_image_workflow.inspect_instant_experience_original(
                source_bytes,
                original_name=uploaded_file.name,
            )
            preview_details = {}
            preview_error = ""
            try:
                preview_details = ads_image_workflow.build_instant_experience_preview_thumbnail(
                    source_bytes,
                    source_hash=original_details["source_hash"],
                )
            except Exception as error:
                logging.warning("Instant Experience preview generation failed: %s", error)
                preview_error = "Preview could not be generated. The original full-resolution image is still available."
            processed = {
                **original_details,
                **preview_details,
                "data": source_bytes,
                "output_format": original_details["source_format"],
                "output_width": original_details["source_width"],
                "output_height": original_details["source_height"],
                "output_size": original_details["source_size"],
                "preview_error": preview_error,
            }
        else:
            processed = ads_image_workflow.optimize_meta_image(
                source_bytes,
                original_name=uploaded_file.name,
            )
        processed.update(
            {
                "slot_id": slot["id"],
                "label": slot["label"],
                "concept_id": slot.get("concept_id"),
                "display_name": slot.get("display_name"),
                "supporting_label": slot.get("supporting_label"),
                "position": slot["position"],
                "valid": True,
                "error": "",
            }
        )
    except ads_image_workflow.AdsImageValidationError as error:
        processed = {
            "slot_id": slot["id"],
            "label": slot["label"],
            "concept_id": slot.get("concept_id"),
            "display_name": slot.get("display_name"),
            "supporting_label": slot.get("supporting_label"),
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
        return bool(slot_specs) and all(
            (slots.get(slot["id"]) or {}).get("valid") for slot in slot_specs
        )
    return bool(slot_specs) and all((slots.get(slot["id"]) or {}).get("valid") for slot in slot_specs)


def _meta_output_filename(result, workflow, slot):
    if _is_instant_experience_result(result):
        saved_slot = (workflow.get("slots") or {}).get(slot.get("id")) or {}
        return ads_image_workflow.build_instant_experience_original_filename(
            slot,
            saved_slot.get("original_name"),
            saved_slot.get("source_format") or saved_slot.get("output_format"),
        )
    filename = ads_image_workflow.build_meta_image_filename(
        result["product_name"],
        result["campaign_type"],
        position=slot["position"],
        iso_date=workflow["export_date"],
    )
    saved_slot = (workflow.get("slots") or {}).get(slot.get("id")) or {}
    if saved_slot.get("output_format") == "PNG":
        return re.sub(r"\.jpg$", ".png", filename)
    return filename


def _ads_export_date_compact(workflow):
    export_date = str((workflow or {}).get("export_date") or "").strip()
    try:
        parsed = date.fromisoformat(export_date)
    except ValueError:
        parsed = campaign_moment_today()
    return parsed.strftime("%d%m%y")


def build_ads_export_folder_name(result, workflow):
    date_code = _ads_export_date_compact(workflow)
    product = ads_image_workflow.sanitize_product_filename(
        result.get("product_name"),
        max_length=80,
    )
    category = ads_image_workflow.sanitize_product_filename(
        result.get("category"),
        max_length=40,
    )
    country = ads_image_workflow.sanitize_product_filename(
        result.get("country"),
        max_length=40,
    )
    return ads_image_workflow.sanitize_product_filename(
        f"Ad({date_code}) {product} ({category}) {country}",
        max_length=180,
    )


def build_ads_notes_filename(result, workflow):
    return ADS_COPY_FILENAME


def _ads_export_folder_path(destination, result, workflow):
    clean_destination = dropbox_integration.normalize_dropbox_path(destination)
    folder_name = build_ads_export_folder_name(result, workflow)
    if PurePosixPath(clean_destination).name.casefold() == folder_name.casefold():
        return clean_destination
    return dropbox_integration.join_upload_path(clean_destination, folder_name)


def _ads_notes_for_workflow(workflow):
    notes = dict((workflow or {}).get("ad_notes") or {})

    def preserve_multiline(value):
        return str(value or "").replace("\r\n", "\n").replace("\r", "\n")

    return {
        "headlines": preserve_multiline(notes.get("headlines")),
        "descriptions": preserve_multiline(notes.get("descriptions")),
        "primary_text_variations": preserve_multiline(notes.get("primary_text_variations")),
        "cards": preserve_multiline(notes.get("cards")),
    }


def _preserve_multiline_text(value):
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n")


class CarouselCopyCSVError(ValueError):
    pass


def _carousel_copy_widget_key(context_key, group_key, position):
    return f"ads-carousel-copy::{context_key}::{group_key}::{int(position)}"


def _carousel_card_widget_key(context_key, position, field_key):
    return f"ads-carousel-card::{context_key}::{int(position)}::{field_key}"


def _carousel_setup_notes_widget_key(context_key):
    return f"ads-carousel-setup::{context_key}"


def _normalise_carousel_variations(raw_values, *, paragraph_mode=False):
    if isinstance(raw_values, str):
        normalized = _preserve_multiline_text(raw_values)
        values = (
            re.split(r"\n\s*\n", normalized)
            if paragraph_mode
            else normalized.splitlines()
        )
    elif isinstance(raw_values, (list, tuple)):
        values = list(raw_values)
    else:
        values = []
    values = [_preserve_multiline_text(value) for value in values]
    values.extend([""] * CAROUSEL_COPY_VARIATION_COUNT)
    return values[:CAROUSEL_COPY_VARIATION_COUNT]


def _blank_carousel_card(position):
    slot = ads_image_workflow.campaign_image_slots("Carousel")[int(position) - 1]
    return {
        "position": int(position),
        "slot_id": slot["id"],
        "image_filename": "",
        **{field_key: "" for field_key in CAROUSEL_CARD_FIELDS},
    }


def _normalise_carousel_card(raw_card, position):
    card = _blank_carousel_card(position)
    if isinstance(raw_card, dict):
        card["image_filename"] = _preserve_multiline_text(
            raw_card.get("image_filename")
        ).strip()
        for field_key in CAROUSEL_CARD_FIELDS:
            card[field_key] = _preserve_multiline_text(raw_card.get(field_key))
    return card


def _carousel_actual_image_filename(result, workflow, slot, fallback=""):
    slot_data = ((workflow or {}).get("slots") or {}).get(slot["id"]) or {}
    outcome = ((workflow or {}).get("outcomes") or {}).get(slot["id"]) or {}
    if outcome.get("filename"):
        return str(outcome["filename"])
    if slot_data.get("valid"):
        try:
            return _meta_output_filename(result, workflow, slot)
        except (KeyError, TypeError, ValueError):
            return str(slot_data.get("original_name") or fallback or "")
    return str(fallback or "")


def _carousel_copy_notes_from_workflow(result, workflow):
    notes = dict((workflow or {}).get("ad_notes") or {})
    structured = notes.get("carousel")
    structured = dict(structured) if isinstance(structured, dict) else {}
    headlines = _normalise_carousel_variations(
        structured.get("headlines", notes.get("headlines"))
    )
    descriptions = _normalise_carousel_variations(
        structured.get("descriptions", notes.get("descriptions"))
    )
    primary_texts = _normalise_carousel_variations(
        structured.get("primary_texts", notes.get("primary_text_variations")),
        paragraph_mode=True,
    )
    raw_cards = structured.get("cards")
    raw_cards = list(raw_cards) if isinstance(raw_cards, (list, tuple)) else []
    cards = []
    for position, slot in enumerate(
        ads_image_workflow.campaign_image_slots("Carousel"),
        start=1,
    ):
        raw_card = raw_cards[position - 1] if position <= len(raw_cards) else {}
        card = _normalise_carousel_card(raw_card, position)
        card["image_filename"] = _carousel_actual_image_filename(
            result,
            workflow,
            slot,
            fallback=card.get("image_filename"),
        )
        cards.append(card)
    return {
        "headlines": headlines,
        "descriptions": descriptions,
        "primary_texts": primary_texts,
        "cards": cards,
        "setup_notes": _preserve_multiline_text(
            structured.get("setup_notes", notes.get("cards"))
        ),
    }


def _carousel_copy_notes_with_widget_state(result, workflow):
    carousel = _carousel_copy_notes_from_workflow(result, workflow)
    context_key = str((result or {}).get("context_key") or "")
    for group_key in ("headlines", "descriptions", "primary_texts"):
        for position in range(1, CAROUSEL_COPY_VARIATION_COUNT + 1):
            widget_key = _carousel_copy_widget_key(context_key, group_key, position)
            if widget_key in st.session_state:
                carousel[group_key][position - 1] = _preserve_multiline_text(
                    st.session_state.get(widget_key)
                )
    for card in carousel["cards"]:
        for field_key in CAROUSEL_CARD_FIELDS:
            widget_key = _carousel_card_widget_key(
                context_key,
                card["position"],
                field_key,
            )
            if widget_key in st.session_state:
                card[field_key] = _preserve_multiline_text(
                    st.session_state.get(widget_key)
                )
    setup_key = _carousel_setup_notes_widget_key(context_key)
    if setup_key in st.session_state:
        carousel["setup_notes"] = _preserve_multiline_text(
            st.session_state.get(setup_key)
        )
    return carousel


def _store_carousel_copy_notes(workflow, carousel):
    clean = {
        "headlines": _normalise_carousel_variations(carousel.get("headlines")),
        "descriptions": _normalise_carousel_variations(carousel.get("descriptions")),
        "primary_texts": _normalise_carousel_variations(
            carousel.get("primary_texts")
        ),
        "cards": [
            _normalise_carousel_card(card, position)
            for position, card in enumerate(
                list(carousel.get("cards") or ())[:CAROUSEL_CARD_COUNT],
                start=1,
            )
        ],
        "setup_notes": _preserve_multiline_text(carousel.get("setup_notes")),
    }
    while len(clean["cards"]) < CAROUSEL_CARD_COUNT:
        clean["cards"].append(_blank_carousel_card(len(clean["cards"]) + 1))
    notes = dict((workflow or {}).get("ad_notes") or {})
    notes["carousel"] = clean
    notes["headlines"] = "\n".join(clean["headlines"])
    notes["descriptions"] = "\n".join(clean["descriptions"])
    notes["primary_text_variations"] = "\n\n".join(clean["primary_texts"])
    notes["cards"] = clean["setup_notes"]
    workflow["ad_notes"] = notes
    return clean


def _carousel_csv_row(**updates):
    row = {header: "" for header in CAROUSEL_COPY_CSV_HEADERS}
    row.update(
        {
            "schema_version": CAROUSEL_COPY_CSV_SCHEMA_VERSION,
            "campaign_type": CAROUSEL_COPY_CSV_CAMPAIGN_TYPE,
        }
    )
    row.update(updates)
    return row


def build_carousel_copy_csv(
    result,
    workflow=None,
    *,
    template=False,
    carousel_notes=None,
):
    if carousel_notes is None:
        carousel_notes = (
            {
                "headlines": [f"Headline option {index}" for index in range(1, 6)],
                "descriptions": [f"Description option {index}" for index in range(1, 6)],
                "primary_texts": [
                    f"Example primary text variation {index}."
                    for index in range(1, 6)
                ],
                "cards": [
                    {
                        **_blank_carousel_card(index),
                        "image_filename": f"carousel-card-{index:02d}.jpg",
                        "headline": f"Example hook {index}",
                        "description": f"Example detail {index}",
                        "destination_url": "https://example.com/products/example",
                        "cta": "Shop Now",
                        "setup_notes": "",
                    }
                    for index in range(1, 6)
                ],
                "setup_notes": "Example overall carousel setup notes.",
            }
            if template
            else _carousel_copy_notes_with_widget_state(result, workflow or {})
        )
    normalized = {
        "headlines": _normalise_carousel_variations(carousel_notes.get("headlines")),
        "descriptions": _normalise_carousel_variations(carousel_notes.get("descriptions")),
        "primary_texts": _normalise_carousel_variations(carousel_notes.get("primary_texts")),
        "cards": [
            _normalise_carousel_card(card, position)
            for position, card in enumerate(
                list(carousel_notes.get("cards") or ())[:CAROUSEL_CARD_COUNT],
                start=1,
            )
        ],
        "setup_notes": _preserve_multiline_text(carousel_notes.get("setup_notes")),
    }
    while len(normalized["cards"]) < CAROUSEL_CARD_COUNT:
        normalized["cards"].append(_blank_carousel_card(len(normalized["cards"]) + 1))

    rows = []
    for row_type, group_key, field_key in (
        ("headline", "headlines", "headline"),
        ("description", "descriptions", "description"),
        ("primary_text", "primary_texts", "primary_text"),
    ):
        for position, value in enumerate(normalized[group_key], start=1):
            rows.append(
                _carousel_csv_row(
                    row_type=row_type,
                    position=str(position),
                    **{field_key: _preserve_multiline_text(value)},
                )
            )
    for card in normalized["cards"]:
        rows.append(
            _carousel_csv_row(
                row_type="card",
                position=str(card["position"]),
                slot_id=card["slot_id"],
                image_filename=card["image_filename"],
                headline=card["headline"],
                description=card["description"],
                destination_url=card["destination_url"],
                cta=card["cta"],
                setup_notes=card["setup_notes"],
            )
        )
    rows.append(
        _carousel_csv_row(
            row_type="setup_notes",
            setup_notes=normalized["setup_notes"],
        )
    )

    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=CAROUSEL_COPY_CSV_HEADERS,
        lineterminator="\r\n",
    )
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8-sig")


def parse_carousel_copy_csv(data, result=None):
    source_bytes = bytes(data or b"")
    if not source_bytes:
        raise CarouselCopyCSVError("Choose a Carousel CSV file.")
    if len(source_bytes) > 2 * 1024 * 1024:
        raise CarouselCopyCSVError("The Carousel CSV must be smaller than 2 MB.")
    try:
        decoded = source_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise CarouselCopyCSVError("Save the Carousel CSV as UTF-8 and try again.") from error
    if "\x00" in decoded:
        raise CarouselCopyCSVError("The Carousel CSV contains invalid text data.")
    try:
        reader = csv.DictReader(io.StringIO(decoded, newline=""))
        headers = list(reader.fieldnames or ())
        if len(headers) != len(set(headers)):
            raise CarouselCopyCSVError("The Carousel CSV contains duplicate column headers.")
        if frozenset(headers) != frozenset(CAROUSEL_COPY_CSV_HEADERS):
            required = ", ".join(CAROUSEL_COPY_CSV_HEADERS)
            raise CarouselCopyCSVError(
                f"Use the Carousel CSV headers exactly: {required}."
            )
        rows = list(reader)
    except csv.Error as error:
        raise CarouselCopyCSVError(
            "The Carousel CSV could not be read. Check its quoting and line breaks."
        ) from error

    expected_keys = {
        *((row_type, position) for row_type in ("headline", "description", "primary_text") for position in range(1, 6)),
        *(("card", position) for position in range(1, 6)),
        ("setup_notes", 0),
    }
    parsed = {
        "headlines": [""] * CAROUSEL_COPY_VARIATION_COUNT,
        "descriptions": [""] * CAROUSEL_COPY_VARIATION_COUNT,
        "primary_texts": [""] * CAROUSEL_COPY_VARIATION_COUNT,
        "cards": [_blank_carousel_card(position) for position in range(1, 6)],
        "setup_notes": "",
    }
    seen = set()
    slot_specs = ads_image_workflow.campaign_image_slots("Carousel")
    group_by_type = {
        "headline": ("headlines", "headline"),
        "description": ("descriptions", "description"),
        "primary_text": ("primary_texts", "primary_text"),
    }
    for row_number, row in enumerate(rows, start=2):
        if None in row or any(value is None for value in row.values()):
            raise CarouselCopyCSVError(
                f"CSV row {row_number} has an unexpected or missing value."
            )
        if str(row.get("schema_version") or "").strip() != CAROUSEL_COPY_CSV_SCHEMA_VERSION:
            raise CarouselCopyCSVError(
                f"CSV row {row_number} has an incompatible schema_version. Download a fresh template."
            )
        if str(row.get("campaign_type") or "").strip() != CAROUSEL_COPY_CSV_CAMPAIGN_TYPE:
            raise CarouselCopyCSVError(
                f"CSV row {row_number} is not a Carousel row. Download a fresh template."
            )
        row_type = str(row.get("row_type") or "").strip()
        if row_type not in CAROUSEL_COPY_ROW_TYPES:
            raise CarouselCopyCSVError(
                f"CSV row {row_number} has unsupported row_type {row_type!r}."
            )
        raw_position = str(row.get("position") or "").strip()
        if row_type == "setup_notes":
            if raw_position not in {"", "0"}:
                raise CarouselCopyCSVError(
                    f"CSV row {row_number} setup_notes position must be blank."
                )
            position = 0
        else:
            try:
                position = int(raw_position)
            except ValueError as error:
                raise CarouselCopyCSVError(
                    f"CSV row {row_number} position must be a number from 1 to 5."
                ) from error
            if position not in range(1, CAROUSEL_COPY_VARIATION_COUNT + 1):
                raise CarouselCopyCSVError(
                    f"CSV row {row_number} position must be a number from 1 to 5."
                )
        row_key = (row_type, position)
        if row_key in seen:
            raise CarouselCopyCSVError(
                f"CSV row {row_number} duplicates {row_type} position {position}."
            )
        seen.add(row_key)

        if row_type in group_by_type:
            group_key, field_key = group_by_type[row_type]
            parsed[group_key][position - 1] = _preserve_multiline_text(row.get(field_key))
        elif row_type == "card":
            expected_slot_id = slot_specs[position - 1]["id"]
            if str(row.get("slot_id") or "").strip() != expected_slot_id:
                raise CarouselCopyCSVError(
                    f"CSV row {row_number} slot_id must be {expected_slot_id} for card {position}."
                )
            card = _blank_carousel_card(position)
            card["image_filename"] = _preserve_multiline_text(
                row.get("image_filename")
            ).strip()
            for field_key in CAROUSEL_CARD_FIELDS:
                card[field_key] = _preserve_multiline_text(row.get(field_key))
            for field_key in ("headline", "description"):
                if len(card[field_key]) > CAROUSEL_CARD_MAX_CHARACTERS:
                    raise CarouselCopyCSVError(
                        f"Card {position} {field_key} exceeds {CAROUSEL_CARD_MAX_CHARACTERS} characters."
                    )
            destination = card["destination_url"].strip()
            if destination:
                parsed_url = urlparse(destination)
                if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
                    raise CarouselCopyCSVError(
                        f"Card {position} destination_url must be a complete http or https URL."
                    )
            parsed["cards"][position - 1] = card
        else:
            parsed["setup_notes"] = _preserve_multiline_text(row.get("setup_notes"))

    missing = expected_keys - seen
    unexpected = seen - expected_keys
    if missing or unexpected or len(rows) != len(expected_keys):
        raise CarouselCopyCSVError(
            "The Carousel CSV must contain exactly five headline rows, five description rows, "
            "five primary_text rows, five card rows and one setup_notes row."
        )
    return parsed


def apply_carousel_copy_csv(result, workflow, data):
    parsed = parse_carousel_copy_csv(data, result)
    context_key = str((result or {}).get("context_key") or "")
    widget_updates = {}
    for group_key in ("headlines", "descriptions", "primary_texts"):
        for position, value in enumerate(parsed[group_key], start=1):
            widget_updates[
                _carousel_copy_widget_key(context_key, group_key, position)
            ] = value
    for card in parsed["cards"]:
        for field_key in CAROUSEL_CARD_FIELDS:
            widget_updates[
                _carousel_card_widget_key(
                    context_key,
                    card["position"],
                    field_key,
                )
            ] = card[field_key]
    widget_updates[_carousel_setup_notes_widget_key(context_key)] = parsed["setup_notes"]

    for widget_key, value in widget_updates.items():
        st.session_state[widget_key] = value
    _store_carousel_copy_notes(workflow, parsed)
    return {
        "carousel_notes": parsed,
        "row_count": 21,
        "field_count": len(widget_updates),
    }


def _process_carousel_copy_csv_upload(result, workflow, uploaded_file):
    if uploaded_file is None:
        return None
    source_bytes = bytes(uploaded_file.getvalue() or b"")
    digest = hashlib.sha256(source_bytes).hexdigest()
    if workflow.get("carousel_csv_import_digest") == digest:
        return workflow.get("carousel_csv_import_status")
    try:
        imported = apply_carousel_copy_csv(result, workflow, source_bytes)
        status = {
            "ok": True,
            "message": (
                f"Imported {imported['row_count']} Carousel rows into "
                f"{imported['field_count']} editable fields."
            ),
        }
    except CarouselCopyCSVError as error:
        status = {"ok": False, "message": str(error)}
    workflow["carousel_csv_import_digest"] = digest
    workflow["carousel_csv_import_status"] = status
    st.session_state[ADS_IMAGE_STATE_KEY] = workflow
    return status


def _carousel_current_copy_csv_filename(result):
    product_name = ads_image_workflow.sanitize_product_filename(
        (result or {}).get("product_name"),
        max_length=90,
    )
    return f"Sports Cave - {product_name} - Carousel Copy.csv"


def _carousel_copy_csv_signature(result, workflow):
    return hashlib.sha256(
        build_carousel_copy_csv(result, workflow)
    ).hexdigest()


def _human_file_size(size):
    try:
        size = int(size or 0)
    except (TypeError, ValueError):
        size = 0
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.2f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} B"


def _blank_instant_experience_variations():
    return [
        _with_instant_experience_description_metadata(
            {field_key: "" for field_key, _label in INSTANT_EXPERIENCE_COPY_FIELDS},
            variation_number,
        )
        for variation_number in range(1, INSTANT_EXPERIENCE_COPY_VARIATION_COUNT + 1)
    ]


class InstantExperienceCopyCSVError(ValueError):
    pass


def _instant_experience_description_variant(variation_number):
    try:
        index = int(variation_number) - 1
    except (TypeError, ValueError):
        index = 0
    if 0 <= index < len(INSTANT_EXPERIENCE_DESCRIPTION_VARIANTS):
        return INSTANT_EXPERIENCE_DESCRIPTION_VARIANTS[index]
    return INSTANT_EXPERIENCE_DESCRIPTION_VARIANTS[0]


def _with_instant_experience_description_metadata(variation, variation_number):
    variant = _instant_experience_description_variant(variation_number)
    clean = dict(variation or {})
    clean["description_key"] = variant["key"]
    clean["description_label"] = variant["label"]
    for field_key, _label in INSTANT_EXPERIENCE_COPY_FIELDS:
        clean[field_key] = _preserve_multiline_text(clean.get(field_key))
    return clean


def _instant_experience_copy_variation_error(
    variation,
    *,
    concept_id="",
    variation_number=0,
):
    variation = variation or {}
    expected_variant = _instant_experience_description_variant(variation_number)
    supplied_key = str(variation.get("description_key") or expected_variant["key"]).strip()
    supplied_label = str(variation.get("description_label") or expected_variant["label"]).strip()
    if supplied_key != expected_variant["key"]:
        return f'Description key must be "{expected_variant["key"]}".'
    if supplied_label != expected_variant["label"]:
        return f'Description label must be "{expected_variant["label"]}".'

    for field_key, label in INSTANT_EXPERIENCE_COPY_FIELDS:
        if not str(variation.get(field_key) or "").strip():
            return f"{label} is required."
        if re.search(r"\{\{[^}]+\}\}", str(variation.get(field_key) or "")):
            return f"{label} contains an unresolved template variable."

    cta = str(variation.get("cta") or "").strip()
    if cta not in INSTANT_EXPERIENCE_APPROVED_CREATIVE_CTAS:
        allowed = ", ".join(INSTANT_EXPERIENCE_APPROVED_CREATIVE_CTAS)
        return f"CTA must be exactly one of: {allowed}."

    expected_primary_image_cta = INSTANT_EXPERIENCE_PRIMARY_IMAGE_CTAS.get(concept_id)
    if variation_number == 1 and expected_primary_image_cta and cta != expected_primary_image_cta:
        concept = next(
            (item for item in INSTANT_EXPERIENCE_CONCEPTS if item["id"] == concept_id),
            None,
        )
        display_name = concept["display_name"] if concept else concept_id
        return (
            f"CTA must be {expected_primary_image_cta} so it matches the fixed "
            f"{display_name} cover."
        )
    return ""


def _instant_experience_copy_widget_key(
    context_key,
    concept_id,
    field_key,
    variation,
):
    return (
        f"ads-ie-concept-copy-field::{context_key}::"
        f"{concept_id}::{field_key}::{variation}"
    )


def _instant_experience_copy_csv_output_mode(result):
    settings = (
        (result or {}).get("instant_experience_settings")
        if isinstance(result, dict)
        else None
    )
    raw_mode = (
        settings.get("output_mode")
        if isinstance(settings, dict)
        else (result or {}).get("output_mode")
        if isinstance(result, dict)
        else ""
    )
    known_modes = {
        IE_MODE_SMART: "smart_3_pack",
        IE_MODE_SELECTED: "one_selected_route",
        IE_MODE_CLASSIC: "classic_collector",
    }
    if raw_mode in known_modes:
        return known_modes[raw_mode]
    if raw_mode:
        normalized = re.sub(r"[^a-z0-9]+", "_", str(raw_mode).casefold()).strip("_")
        if normalized:
            return normalized
    return INSTANT_EXPERIENCE_COPY_CSV_STANDARD_OUTPUT_MODE


def _instant_experience_copy_csv_route_label(concept):
    return (
        f"{str(concept.get('display_name') or '').upper()} \u2014 "
        f"{concept.get('supporting_label') or ''}"
    )


def _instant_experience_copy_notes_with_widget_state(result, workflow):
    notes = _instant_experience_concept_copy_notes_from_workflow(workflow)
    context_key = str((result or {}).get("context_key") or "")
    merged = {
        concept["id"]: [dict(variation) for variation in notes.get(concept["id"], [])]
        for concept in INSTANT_EXPERIENCE_CONCEPTS
    }
    for concept in INSTANT_EXPERIENCE_CONCEPTS:
        variations = merged[concept["id"]]
        for variation_number in range(1, INSTANT_EXPERIENCE_COPY_VARIATION_COUNT + 1):
            variation = _with_instant_experience_description_metadata(
                variations[variation_number - 1],
                variation_number,
            )
            for field_key, _label in INSTANT_EXPERIENCE_COPY_FIELDS:
                widget_key = _instant_experience_copy_widget_key(
                    context_key,
                    concept["id"],
                    field_key,
                    variation_number,
                )
                if widget_key in st.session_state:
                    variation[field_key] = _preserve_multiline_text(
                        st.session_state.get(widget_key)
                    )
            variations[variation_number - 1] = variation
    return merged


def build_instant_experience_copy_csv(
    result,
    workflow=None,
    *,
    blank=False,
    concept_notes=None,
):
    if concept_notes is None:
        concept_notes = (
            {
                concept["id"]: _blank_instant_experience_variations()
                for concept in INSTANT_EXPERIENCE_CONCEPTS
            }
            if blank
            else _instant_experience_copy_notes_with_widget_state(result, workflow or {})
        )
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=INSTANT_EXPERIENCE_COPY_CSV_HEADERS,
        lineterminator="\r\n",
    )
    writer.writeheader()
    output_mode = _instant_experience_copy_csv_output_mode(result)
    for concept in INSTANT_EXPERIENCE_CONCEPTS:
        variations = _normalise_instant_experience_variations(
            concept_notes.get(concept["id"])
        )
        for variation_number, variation in enumerate(variations, start=1):
            writer.writerow(
                {
                    "schema_version": INSTANT_EXPERIENCE_COPY_CSV_SCHEMA_VERSION,
                    "campaign_type": INSTANT_EXPERIENCE_COPY_CSV_CAMPAIGN_TYPE,
                    "output_mode": output_mode,
                    "route_key": concept["id"],
                    "route_label": _instant_experience_copy_csv_route_label(concept),
                    "variation": str(variation_number),
                    "description_key": _instant_experience_description_variant(variation_number)["key"],
                    "description_label": _instant_experience_description_variant(variation_number)["label"],
                    "primary_text": "" if blank else _preserve_multiline_text(variation.get("primary_text")),
                    "headline": "" if blank else _preserve_multiline_text(variation.get("headline")),
                    "cta": "" if blank else _preserve_multiline_text(variation.get("cta")),
                }
            )
    return output.getvalue().encode("utf-8-sig")


def _instant_experience_copy_csv_expected_rows(result):
    output_mode = _instant_experience_copy_csv_output_mode(result)
    return [
        {
            "schema_version": INSTANT_EXPERIENCE_COPY_CSV_SCHEMA_VERSION,
            "campaign_type": INSTANT_EXPERIENCE_COPY_CSV_CAMPAIGN_TYPE,
            "output_mode": output_mode,
            "route_key": concept["id"],
            "route_label": _instant_experience_copy_csv_route_label(concept),
            "variation": str(variation_number),
            "description_key": _instant_experience_description_variant(variation_number)["key"],
            "description_label": _instant_experience_description_variant(variation_number)["label"],
        }
        for concept in INSTANT_EXPERIENCE_CONCEPTS
        for variation_number in range(1, INSTANT_EXPERIENCE_COPY_VARIATION_COUNT + 1)
    ]


def parse_instant_experience_copy_csv(data, result):
    source_bytes = bytes(data or b"")
    if not source_bytes:
        raise InstantExperienceCopyCSVError("Choose a completed Instant Experience CSV file.")
    if len(source_bytes) > 2 * 1024 * 1024:
        raise InstantExperienceCopyCSVError("The copy CSV must be smaller than 2 MB.")
    try:
        decoded = source_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise InstantExperienceCopyCSVError("Save the copy CSV as UTF-8 and try again.") from error
    if "\x00" in decoded:
        raise InstantExperienceCopyCSVError("The copy CSV contains invalid text data.")
    try:
        reader = csv.DictReader(io.StringIO(decoded, newline=""))
        headers = list(reader.fieldnames or ())
        if len(headers) != len(set(headers)):
            raise InstantExperienceCopyCSVError("The copy CSV contains duplicate column headers.")
        legacy_headers = tuple(
            header
            for header in INSTANT_EXPERIENCE_COPY_CSV_HEADERS
            if header not in {"description_key", "description_label"}
        )
        supported_header_sets = {
            frozenset(INSTANT_EXPERIENCE_COPY_CSV_HEADERS),
            frozenset(legacy_headers),
        }
        if frozenset(headers) not in supported_header_sets:
            required = ", ".join(INSTANT_EXPERIENCE_COPY_CSV_HEADERS)
            raise InstantExperienceCopyCSVError(
                f"Use the Instant Experience CSV headers exactly: {required}."
            )
        rows = list(reader)
    except csv.Error as error:
        raise InstantExperienceCopyCSVError(
            "The copy CSV could not be read. Check its quoting and line breaks."
        ) from error

    expected_rows = _instant_experience_copy_csv_expected_rows(result)
    if len(rows) != len(expected_rows):
        raise InstantExperienceCopyCSVError(
            f"The copy CSV must contain exactly {len(expected_rows)} copy rows."
        )

    parsed = {
        concept["id"]: _blank_instant_experience_variations()
        for concept in INSTANT_EXPERIENCE_CONCEPTS
    }
    concepts_by_id = {
        concept["id"]: concept
        for concept in INSTANT_EXPERIENCE_CONCEPTS
    }
    seen = set()
    for row_number, (row, expected) in enumerate(zip(rows, expected_rows), start=2):
        if None in row or any(value is None for value in row.values()):
            raise InstantExperienceCopyCSVError(
                f"CSV row {row_number} has an unexpected or missing value."
            )
        identity_fields = [
            "schema_version",
            "campaign_type",
            "output_mode",
            "route_key",
            "route_label",
            "variation",
        ]
        if "description_key" in headers:
            identity_fields.append("description_key")
        if "description_label" in headers:
            identity_fields.append("description_label")
        for field in identity_fields:
            row_value = str(row.get(field) or "").strip()
            if (
                field == "schema_version"
                and row_value == "1"
                and frozenset(headers) == frozenset(legacy_headers)
            ):
                continue
            if row_value != expected[field]:
                raise InstantExperienceCopyCSVError(
                    f"CSV row {row_number} has an incompatible {field}. Download a fresh template."
                )
        row_key = (expected["route_key"], int(expected["variation"]))
        if row_key in seen:
            raise InstantExperienceCopyCSVError(
                f"CSV row {row_number} duplicates {expected['route_key']} variation {expected['variation']}."
            )
        seen.add(row_key)
        variation = {
            field_key: _preserve_multiline_text(row.get(field_key))
            for field_key, _label in INSTANT_EXPERIENCE_COPY_FIELDS
        }
        variation = _with_instant_experience_description_metadata(
            variation,
            row_key[1],
        )
        validation_error = _instant_experience_copy_variation_error(
            variation,
            concept_id=expected["route_key"],
            variation_number=row_key[1],
        )
        if validation_error:
            route_name = concepts_by_id[expected["route_key"]]["display_name"]
            raise InstantExperienceCopyCSVError(
                f"{route_name} variation {expected['variation']}: {validation_error}"
            )
        parsed[expected["route_key"]][row_key[1] - 1] = variation
    return parsed


def apply_instant_experience_copy_csv(result, workflow, data):
    parsed = parse_instant_experience_copy_csv(data, result)
    context_key = str((result or {}).get("context_key") or "")
    widget_updates = {}
    for concept in INSTANT_EXPERIENCE_CONCEPTS:
        for variation_number, variation in enumerate(
            parsed[concept["id"]],
            start=1,
        ):
            for field_key, _label in INSTANT_EXPERIENCE_COPY_FIELDS:
                widget_updates[
                    _instant_experience_copy_widget_key(
                        context_key,
                        concept["id"],
                        field_key,
                        variation_number,
                    )
                ] = variation[field_key]

    for widget_key, value in widget_updates.items():
        st.session_state[widget_key] = value
    notes = dict((workflow or {}).get("ad_notes") or {})
    notes["instant_experience_concepts"] = parsed
    workflow["ad_notes"] = notes
    return {
        "concept_notes": parsed,
        "variation_count": len(INSTANT_EXPERIENCE_CONCEPTS)
        * INSTANT_EXPERIENCE_COPY_VARIATION_COUNT,
        "field_count": len(widget_updates),
    }


def _process_instant_experience_copy_csv_upload(result, workflow, uploaded_file):
    if uploaded_file is None:
        return None
    source_bytes = bytes(uploaded_file.getvalue() or b"")
    digest = hashlib.sha256(source_bytes).hexdigest()
    if workflow.get("copy_csv_import_digest") == digest:
        return workflow.get("copy_csv_import_status")
    try:
        imported = apply_instant_experience_copy_csv(result, workflow, source_bytes)
        status = {
            "ok": True,
            "message": (
                f"Imported {imported['variation_count']} description options into "
                f"{imported['field_count']} fields."
            ),
        }
    except InstantExperienceCopyCSVError as error:
        status = {"ok": False, "message": str(error)}
    workflow["copy_csv_import_digest"] = digest
    workflow["copy_csv_import_status"] = status
    st.session_state[ADS_IMAGE_STATE_KEY] = workflow
    return status


def _instant_experience_current_copy_csv_filename(result):
    product_name = ads_image_workflow.sanitize_product_filename(
        (result or {}).get("product_name"),
        max_length=90,
    )
    return f"Sports Cave - {product_name} - Instant Experience Copy.csv"


def _normalise_instant_experience_variations(raw_variations):
    variations = []
    if isinstance(raw_variations, (list, tuple)):
        for index, raw in enumerate(raw_variations, start=1):
            if isinstance(raw, dict):
                variations.append(
                    _with_instant_experience_description_metadata(raw, index)
                )
    variations.extend(_blank_instant_experience_variations())
    return variations[:INSTANT_EXPERIENCE_COPY_VARIATION_COUNT]


def _legacy_instant_experience_copy_notes(workflow):
    notes = dict((workflow or {}).get("ad_notes") or {})
    instant_notes = notes.get("instant_experience")
    instant_notes = dict(instant_notes) if isinstance(instant_notes, dict) else {}

    def values_for(group_key):
        raw_values = instant_notes.get(group_key)
        if raw_values is None and group_key == "primary_text":
            raw_values = instant_notes.get("primary_texts")
        if isinstance(raw_values, str):
            values = raw_values.splitlines()
        elif isinstance(raw_values, (list, tuple)):
            values = list(raw_values)
        else:
            values = []
        values = [str(value or "").replace("\r\n", "\n").replace("\r", "\n") for value in values]
        values.extend([""] * (INSTANT_EXPERIENCE_COPY_OPTION_COUNT - len(values)))
        return values[:INSTANT_EXPERIENCE_COPY_OPTION_COUNT]

    return {
        group_key: values_for(group_key)
        for group_key, _heading, _label, _placeholder in INSTANT_EXPERIENCE_COPY_GROUPS
    }


def _instant_experience_concept_copy_notes_from_workflow(workflow):
    notes = dict((workflow or {}).get("ad_notes") or {})
    concept_notes = notes.get("instant_experience_concepts")
    if isinstance(concept_notes, dict):
        mapped_notes = {}
        for concept in INSTANT_EXPERIENCE_CONCEPTS:
            concept_id = concept["id"]
            raw_variations = concept_notes.get(concept_id)
            if raw_variations is None:
                legacy_ids = [
                    legacy_id
                    for legacy_id, mapped_id in INSTANT_EXPERIENCE_LEGACY_CONCEPT_ID_MAP.items()
                    if mapped_id == concept_id
                ]
                for legacy_id in legacy_ids:
                    if legacy_id in concept_notes:
                        raw_variations = concept_notes.get(legacy_id)
                        break
            mapped_notes[concept_id] = _normalise_instant_experience_variations(raw_variations)
        return mapped_notes

    legacy = _legacy_instant_experience_copy_notes(workflow)
    primary = legacy.get("primary_text") or []
    headlines = legacy.get("headlines") or []
    ctas = legacy.get("call_to_action") or []
    mapped = {
        concept["id"]: _blank_instant_experience_variations()
        for concept in INSTANT_EXPERIENCE_CONCEPTS
    }
    legacy_rows = {
        "premium_scarcity_right": [0],
        "premium_scarcity_front": [1, 2],
        "premium_scarcity_left": [4],
    }
    for concept_id, source_indexes in legacy_rows.items():
        for target_index, source_index in enumerate(source_indexes):
            if target_index >= INSTANT_EXPERIENCE_COPY_VARIATION_COUNT:
                break
            mapped[concept_id][target_index] = {
                "description_key": _instant_experience_description_variant(target_index + 1)["key"],
                "description_label": _instant_experience_description_variant(target_index + 1)["label"],
                "primary_text": _preserve_multiline_text(
                    primary[source_index] if source_index < len(primary) else ""
                ),
                "headline": _preserve_multiline_text(
                    headlines[source_index] if source_index < len(headlines) else ""
                ),
                "cta": _preserve_multiline_text(
                    ctas[source_index] if source_index < len(ctas) else ""
                ),
            }
    return mapped


def _instant_experience_variation_complete(
    variation,
    *,
    concept_id="",
    variation_number=0,
):
    return not _instant_experience_copy_variation_error(
        variation,
        concept_id=concept_id,
        variation_number=variation_number,
    )


def _instant_experience_concept_complete_count(workflow, concept_id):
    notes = _instant_experience_concept_copy_notes_from_workflow(workflow)
    return sum(
        1
        for variation_number, variation in enumerate(notes.get(concept_id, []), start=1)
        if _instant_experience_variation_complete(
            variation,
            concept_id=concept_id,
            variation_number=variation_number,
        )
    )


def instant_experience_copy_complete(workflow):
    notes = _instant_experience_concept_copy_notes_from_workflow(workflow)
    return all(
        _instant_experience_variation_complete(
            variation,
            concept_id=concept["id"],
            variation_number=variation_number,
        )
        for concept in INSTANT_EXPERIENCE_CONCEPTS
        for variation_number, variation in enumerate(
            notes.get(concept["id"], []),
            start=1,
        )
    )


def _instant_experience_concept_ad_copy_text(result, workflow, concept):
    notes = _instant_experience_concept_copy_notes_from_workflow(workflow)
    variations = notes.get(concept["id"]) or _blank_instant_experience_variations()
    lines = [
        "SPORTS CAVE INSTANT EXPERIENCE",
        "",
        "PRODUCT:",
        str(result.get("product_name") or ""),
        "",
        "ROUTE:",
        str(concept.get("display_name") or ""),
        "",
    ]
    for index, variation in enumerate(variations, start=1):
        variant = _instant_experience_description_variant(index)
        lines.extend(
            [
                variant["label"],
                "",
                "DESCRIPTION KEY:",
                variant["key"],
                "",
                "DESCRIPTION COPY:",
                _preserve_multiline_text(variation.get("primary_text")),
                "",
                "HEADLINE:",
                _preserve_multiline_text(variation.get("headline")),
                "",
                "CTA:",
                _preserve_multiline_text(variation.get("cta")),
                "",
            ]
        )
    return "\n".join(lines).rstrip("\n").replace("\n", "\r\n") + "\r\n"


def _instant_experience_copy_export_lines(workflow):
    notes = _instant_experience_concept_copy_notes_from_workflow(workflow)
    lines = ["INSTANT EXPERIENCE AD COPY", ""]
    for concept in INSTANT_EXPERIENCE_CONCEPTS:
        lines.extend(
            [
                f"{concept['display_name'].upper()} — {concept['supporting_label']}",
                "",
            ]
        )
        for index, variation in enumerate(notes.get(concept["id"], []), start=1):
            variant = _instant_experience_description_variant(index)
            lines.extend(
                [
                    variant["label"],
                    "DESCRIPTION KEY:",
                    variant["key"],
                    "DESCRIPTION COPY:",
                    _preserve_multiline_text(variation.get("primary_text")),
                    "HEADLINE:",
                    _preserve_multiline_text(variation.get("headline")),
                    "CTA:",
                    _preserve_multiline_text(variation.get("cta")),
                    "",
                ]
            )
    return lines


def build_ads_setup_notes_text(result, workflow, *, image_outcomes=None):
    notes = _ads_notes_for_workflow(workflow)
    campaign_type = str(result.get("campaign_type") or "")
    image_outcomes = dict(image_outcomes or (workflow or {}).get("outcomes") or {})
    slot_specs = ads_image_workflow.campaign_image_slots(campaign_type)
    lines = [
        "Sports Cave Ad Setup Notes",
        "",
        f"Product: {result.get('product_name') or ''}",
        f"Category: {result.get('category') or ''}",
        f"Country/market: {result.get('country') or ''}",
        f"Campaign type: {campaign_type}",
        f"Product URL: {result.get('product_url') or ''}",
        f"Meta URL parameters: {META_AD_URL_PARAMETERS}",
        f"Export date: {(workflow or {}).get('export_date') or ''}",
        "",
        "Uploaded images",
    ]
    if slot_specs:
        for slot in slot_specs:
            outcome = image_outcomes.get(slot["id"]) or {}
            filename = outcome.get("filename") or _meta_output_filename(result, workflow, slot)
            status = outcome.get("status") or (
                "ready to save"
                if ((workflow.get("slots") or {}).get(slot["id"]) or {}).get("valid")
                else "not supplied"
            )
            lines.append(f"- {slot['label']}: {filename} ({status})")
    else:
        lines.append("- No generated image upload slots for this campaign type.")

    if campaign_type == "Instant Experience":
        lines.extend(["", *_instant_experience_copy_export_lines(workflow)])
        moment = normalize_campaign_moment(
            result.get("campaign_moment"),
            selected_country=result.get("country"),
        )
        if campaign_moment_is_active(moment):
            lines.extend(
                [
                    "Campaign moment",
                    f"- Type: {moment.get('type') or 'not supplied'}",
                    f"- Name: {moment.get('name') or 'not supplied'}",
                    f"- Market: {moment.get('resolved_market') or 'not supplied'}",
                    f"- Date/end date: {moment.get('date') or 'not supplied'}",
                    f"- Promotion: {moment.get('promotion') or 'none supplied'}",
                    f"- Strength: {moment.get('strength') or 'Subtle'}",
                    f"- Included in image prompts: {'yes' if moment.get('include_in_image_prompts') else 'no'}",
                ]
            )
        return "\n".join(lines).rstrip("\n").replace("\n", "\r\n") + "\r\n"

    lines.extend(["", "HEADLINES", ""])
    lines.append(notes["headlines"] or "[not supplied]")
    lines.extend(["", "DESCRIPTIONS", ""])
    lines.append(notes["descriptions"] or "[not supplied]")
    lines.extend(["", "PRIMARY TEXT VARIATIONS", ""])
    lines.append(notes["primary_text_variations"] or "[not supplied]")
    lines.extend(["", "CAROUSEL CARDS / AD SETUP", ""])
    lines.append(notes["cards"] or "[not supplied]")

    if campaign_type == "Carousel":
        carousel = _carousel_copy_notes_from_workflow(result, workflow)
        lines.extend(["", "STRUCTURED CAROUSEL CARDS"])
        for card in carousel["cards"]:
            slot = slot_specs[card["position"] - 1]
            outcome = image_outcomes.get(slot["id"]) or {}
            image_filename = (
                outcome.get("filename")
                or card.get("image_filename")
                or _meta_output_filename(result, workflow, slot)
            )
            lines.extend(
                [
                    "",
                    f"CARD {card['position']}",
                    f"- Image slot: {card['slot_id']}",
                    f"- Image filename: {image_filename or '[not supplied]'}",
                    f"- Headline: {card['headline'] or '[not supplied]'}",
                    f"- Description: {card['description'] or '[not supplied]'}",
                    f"- Destination URL: {card['destination_url'] or '[not supplied]'}",
                    f"- CTA: {card['cta'] or '[not supplied]'}",
                    "- Card setup notes:",
                    card["setup_notes"] or "[not supplied]",
                ]
            )
        lines.extend(
            [
                "",
                "Carousel setup checklist",
                "- Use exactly 5 carousel cards in the generated order.",
                f"- Keep each carousel headline and description within {CAROUSEL_CARD_MAX_CHARACTERS} characters.",
                "- Match each saved image to its corresponding card number.",
                "- Use the pasted primary text, card copy, CTA and URL parameters from the ChatGPT output.",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "Single Image / Video setup checklist",
                "- Use the pasted primary text, headline, description, CTA and URL parameters from the ChatGPT output.",
                "- Keep product identity, scarcity and landing-page claims aligned.",
            ]
        )

    moment = normalize_campaign_moment(
        result.get("campaign_moment"),
        selected_country=result.get("country"),
    )
    if campaign_moment_is_active(moment):
        lines.extend(
            [
                "",
                "Campaign moment",
                f"- Type: {moment.get('type') or 'not supplied'}",
                f"- Name: {moment.get('name') or 'not supplied'}",
                f"- Market: {moment.get('resolved_market') or 'not supplied'}",
                f"- Date/end date: {moment.get('date') or 'not supplied'}",
                f"- Promotion: {moment.get('promotion') or 'none supplied'}",
                f"- Strength: {moment.get('strength') or 'Subtle'}",
                f"- Included in image prompts: {'yes' if moment.get('include_in_image_prompts') else 'no'}",
            ]
        )
    return "\n".join(lines).rstrip("\n").replace("\n", "\r\n") + "\r\n"


def _ads_setup_notes_signature(result, workflow, *, image_outcomes=None):
    return hashlib.sha256(
        build_ads_setup_notes_text(
            result,
            workflow,
            image_outcomes=image_outcomes,
        ).encode("utf-8")
    ).hexdigest()


def _instant_experience_slot_for_concept(concept):
    return {
        slot["concept_id"]: slot
        for slot in ads_image_workflow.campaign_image_slots("Instant Experience")
    }.get(concept["id"], {})


def _instant_experience_image_ready_count(workflow):
    _compact_instant_experience_slots(workflow)
    slots = workflow.get("slots") or {}
    return sum(
        1
        for slot in ads_image_workflow.campaign_image_slots("Instant Experience")
        if (slots.get(slot["id"]) or {}).get("valid")
        and (slots.get(slot["id"]) or {}).get("data")
    )


def _instant_experience_status_rows(workflow):
    rows = []
    slots = workflow.get("slots") or {}
    for concept in INSTANT_EXPERIENCE_CONCEPTS:
        slot = _instant_experience_slot_for_concept(concept)
        slot_data = slots.get(slot.get("id")) or {}
        rows.append(
            {
                "concept": concept,
                "slot": slot,
                "slot_data": slot_data,
                "image_ready": bool(slot_data.get("valid") and slot_data.get("data")),
                "copy_complete_count": _instant_experience_concept_complete_count(
                    workflow,
                    concept["id"],
                ),
            }
        )
    return rows


def instant_experience_package_ready(result, workflow):
    if not _is_instant_experience_result(result):
        return False
    return _instant_experience_image_ready_count(workflow) == len(INSTANT_EXPERIENCE_CONCEPTS) and instant_experience_copy_complete(workflow)


def _instant_experience_package_items(result, workflow):
    _compact_instant_experience_slots(workflow)
    if not instant_experience_copy_complete(workflow):
        raise ValueError(
            "Instant Experience copy must be complete and use approved This Edition CTAs before packaging."
        )
    slots = workflow.get("slots") or {}
    items = []
    for concept in INSTANT_EXPERIENCE_CONCEPTS:
        slot = _instant_experience_slot_for_concept(concept)
        slot_data = slots.get(slot.get("id")) or {}
        if not slot_data.get("valid") or not slot_data.get("data"):
            raise ValueError(f"{concept['display_name']} needs a valid full-resolution cover.")
        copy_text = _instant_experience_concept_ad_copy_text(result, workflow, concept)
        copy_bytes = copy_text.encode("utf-8")
        image_filename = ads_image_workflow.build_instant_experience_original_filename(
            concept,
            slot_data.get("original_name"),
            slot_data.get("source_format") or slot_data.get("output_format"),
        )
        image_relative_path = f"{concept['folder']}/{image_filename}"
        copy_relative_path = f"{concept['folder']}/ad-copy.txt"
        items.append(
            {
                "kind": "image",
                "asset_type": "meta_ads",
                "slot_id": slot["id"],
                "concept_id": concept["id"],
                "concept": concept["display_name"],
                "label": slot["label"],
                "relative_path": image_relative_path,
                "filename": image_filename,
                "data": slot_data["data"],
                "size": len(slot_data["data"]),
                "original_name": slot_data.get("original_name") or "",
                "source_hash": slot_data.get("source_hash") or "",
                "source_format": slot_data.get("source_format") or slot_data.get("output_format") or "",
                "source_width": slot_data.get("source_width") or slot_data.get("output_width") or 0,
                "source_height": slot_data.get("source_height") or slot_data.get("output_height") or 0,
                "copy_variation_count": INSTANT_EXPERIENCE_COPY_VARIATION_COUNT,
            }
        )
        items.append(
            {
                "kind": "copy",
                "asset_type": "meta_ads_copy",
                "slot_id": f"{concept['id']}:ad-copy",
                "concept_id": concept["id"],
                "concept": concept["display_name"],
                "label": f"{concept['display_name']} ad copy",
                "relative_path": copy_relative_path,
                "filename": "ad-copy.txt",
                "data": copy_bytes,
                "size": len(copy_bytes),
                "copy_variation_count": INSTANT_EXPERIENCE_COPY_VARIATION_COUNT,
            }
        )
    return items


def _instant_experience_package_signature(result, workflow):
    digest = hashlib.sha256()
    digest.update(str(result.get("context_key") or "").encode("utf-8"))
    for item in _instant_experience_package_items(result, workflow):
        digest.update(item["relative_path"].encode("utf-8"))
        digest.update(hashlib.sha256(item["data"]).hexdigest().encode("ascii"))
    return digest.hexdigest()


def _save_instant_experience_package_to_dropbox(
    access_token,
    export_folder,
    result,
    workflow,
    *,
    progress_callback=None,
):
    items = _instant_experience_package_items(result, workflow)
    items_by_path = {item["relative_path"]: item for item in items}

    def on_upload_progress(row_index, row_total, relative_path, uploaded, file_total):
        if progress_callback:
            item = items_by_path.get(relative_path) or {}
            progress_callback(
                row_index,
                row_total,
                item.get("label") or relative_path,
                uploaded,
                file_total,
            )

    upload_result = dropbox_integration.upload_batch(
        access_token,
        export_folder,
        items,
        conflict="replace",
        progress_callback=on_upload_progress,
    )
    outcomes = dict(workflow.get("outcomes") or {})
    successes = list(upload_result.get("successes") or ())
    failures = list(upload_result.get("failures") or ())
    for success in successes:
        relative_path = str(success.get("relative_path") or "")
        item = items_by_path.get(relative_path) or {}
        metadata = dict(success.get("metadata") or {})
        saved_path = str(
            metadata.get("path_display")
            or metadata.get("path_lower")
            or dropbox_integration.join_upload_path(export_folder, relative_path)
        )
        outcomes[item.get("slot_id") or relative_path] = {
            "status": "saved",
            "label": item.get("label") or relative_path,
            "filename": item.get("filename") or PurePosixPath(relative_path).name,
            "relative_path": relative_path,
            "path": saved_path,
            "metadata": metadata,
            "asset_type": item.get("asset_type") or "meta_ads",
            "concept_id": item.get("concept_id"),
            "concept": item.get("concept"),
            "source_hash": item.get("source_hash") or "",
            "source_format": item.get("source_format") or "",
            "source_width": item.get("source_width") or 0,
            "source_height": item.get("source_height") or 0,
            "copy_variation_count": item.get("copy_variation_count") or 0,
        }
    for failure in failures:
        relative_path = str(failure.get("relative_path") or "")
        item = items_by_path.get(relative_path) or {}
        outcomes[item.get("slot_id") or relative_path] = {
            "status": "failed",
            "label": item.get("label") or relative_path,
            "filename": item.get("filename") or PurePosixPath(relative_path).name,
            "relative_path": relative_path,
            "error": str(failure.get("error") or "Upload failed."),
            "asset_type": item.get("asset_type") or "meta_ads",
            "concept_id": item.get("concept_id"),
            "concept": item.get("concept"),
        }
    package_saved = not failures and len(successes) == len(items)
    if package_saved:
        outcomes["_instant_experience_package"] = {
            "status": "saved",
            "label": "Instant Experience package",
            "filename": build_ads_export_folder_name(result, workflow),
            "path": export_folder,
            "asset_type": "meta_ads_package",
            "signature": _instant_experience_package_signature(result, workflow),
        }
    else:
        outcomes["_instant_experience_package"] = {
            "status": "failed",
            "label": "Instant Experience package",
            "filename": build_ads_export_folder_name(result, workflow),
            "path": export_folder,
            "asset_type": "meta_ads_package",
            "error": "One or more concept files failed to upload.",
        }
    workflow["saved_folder_path"] = export_folder
    workflow["instant_experience_package_signature"] = (
        outcomes.get("_instant_experience_package") or {}
    ).get("signature") or ""
    return outcomes


def _render_carousel_copy_csv_control(result, workflow):
    context_key = str(result.get("context_key") or "")
    import_key = f"ads-carousel-copy-csv-import::{context_key}"
    pending_upload = st.session_state.get(import_key)
    if pending_upload is not None:
        _process_carousel_copy_csv_upload(result, workflow, pending_upload)

    heading_column, control_column = st.columns(
        [5, 1],
        vertical_alignment="center",
    )
    heading_column.subheader("Generated Ad Images")
    with control_column:
        with st.popover("Carousel CSV", icon=":material/table_view:"):
            st.download_button(
                "Download Carousel CSV Template",
                data=build_carousel_copy_csv(result, workflow, template=True),
                file_name="sports-cave-carousel-copy-template.csv",
                mime="text/csv",
                key=f"ads-carousel-copy-csv-template::{context_key}",
                use_container_width=True,
            )
            current_download_slot = st.empty()
            uploaded_file = st.file_uploader(
                "Import Carousel CSV",
                type=["csv"],
                key=import_key,
                label_visibility="visible",
            )
            if uploaded_file is not None:
                _process_carousel_copy_csv_upload(
                    result,
                    workflow,
                    uploaded_file,
                )
            current_download_slot.download_button(
                "Export Carousel CSV",
                data=build_carousel_copy_csv(result, workflow),
                file_name=_carousel_current_copy_csv_filename(result),
                mime="text/csv",
                key=f"ads-carousel-copy-csv-current::{context_key}",
                use_container_width=True,
            )
            status = workflow.get("carousel_csv_import_status")
            if isinstance(status, dict) and status.get("message"):
                if status.get("ok"):
                    st.success(status["message"])
                else:
                    st.error(status["message"])


def _carousel_text_area(label, value, *, key, height=68, placeholder=""):
    widget_args = {
        "key": key,
        "height": height,
        "placeholder": placeholder,
    }
    if key not in st.session_state:
        widget_args["value"] = _preserve_multiline_text(value)
    return st.text_area(label, **widget_args)


def _carousel_text_input(label, value, *, key, placeholder=""):
    widget_args = {
        "key": key,
        "placeholder": placeholder,
    }
    if key not in st.session_state:
        widget_args["value"] = str(value or "")
    return st.text_input(label, **widget_args)


def _render_carousel_setup_notes(result, workflow):
    carousel = _carousel_copy_notes_with_widget_state(result, workflow)
    context_key = str(result.get("context_key") or "")
    slot_specs = ads_image_workflow.campaign_image_slots("Carousel")
    with st.container(key="ads-setup-notes"):
        with st.expander("Ad setup notes (optional)", expanded=False):
            st.caption(
                "Edit the five ad-copy variations and the five card records. "
                "Every card remains permanently mapped to its numbered image slot."
            )
            st.markdown("**Ad copy variations**")
            for position in range(1, CAROUSEL_COPY_VARIATION_COUNT + 1):
                copy_columns = st.columns(3)
                with copy_columns[0]:
                    carousel["headlines"][position - 1] = _carousel_text_area(
                        f"Headline variation {position}",
                        carousel["headlines"][position - 1],
                        key=_carousel_copy_widget_key(
                            context_key,
                            "headlines",
                            position,
                        ),
                        placeholder=f"Headline option {position}",
                    )
                with copy_columns[1]:
                    carousel["descriptions"][position - 1] = _carousel_text_area(
                        f"Description variation {position}",
                        carousel["descriptions"][position - 1],
                        key=_carousel_copy_widget_key(
                            context_key,
                            "descriptions",
                            position,
                        ),
                        placeholder=f"Description option {position}",
                    )
                with copy_columns[2]:
                    carousel["primary_texts"][position - 1] = _carousel_text_area(
                        f"Primary text variation {position}",
                        carousel["primary_texts"][position - 1],
                        key=_carousel_copy_widget_key(
                            context_key,
                            "primary_texts",
                            position,
                        ),
                        height=90,
                        placeholder=f"Primary text option {position}",
                    )

            st.markdown("**Carousel cards**")
            for position, slot in enumerate(slot_specs, start=1):
                card = carousel["cards"][position - 1]
                saved_slot = ((workflow.get("slots") or {}).get(slot["id"]) or {})
                role, _role_description = IMAGE_ORDER[position - 1]
                with st.container(
                    border=True,
                    key=f"ads-carousel-card-copy::{context_key}::{slot['id']}",
                ):
                    st.markdown(f"**Card {position} — {role}**")
                    image_filename = _carousel_actual_image_filename(
                        result,
                        workflow,
                        slot,
                        fallback=card.get("image_filename"),
                    )
                    card["image_filename"] = image_filename
                    st.caption(
                        f"Image slot: {slot['id']} · "
                        f"File: {image_filename or 'No image uploaded yet'}"
                    )
                    image_column, details_column = st.columns([1, 3])
                    with image_column:
                        if saved_slot.get("valid") and saved_slot.get("data"):
                            st.image(saved_slot["data"], width="stretch")
                        else:
                            st.caption(f"Upload Carousel {position} above.")
                    with details_column:
                        first, second = st.columns(2)
                        with first:
                            card["headline"] = _carousel_text_input(
                                f"Card {position} headline",
                                card["headline"],
                                key=_carousel_card_widget_key(
                                    context_key,
                                    position,
                                    "headline",
                                ),
                                placeholder=f"Up to {CAROUSEL_CARD_MAX_CHARACTERS} characters",
                            )
                        with second:
                            card["description"] = _carousel_text_input(
                                f"Card {position} description",
                                card["description"],
                                key=_carousel_card_widget_key(
                                    context_key,
                                    position,
                                    "description",
                                ),
                                placeholder=f"Up to {CAROUSEL_CARD_MAX_CHARACTERS} characters",
                            )
                        third, fourth = st.columns([2, 1])
                        with third:
                            card["destination_url"] = _carousel_text_input(
                                f"Card {position} destination URL",
                                card["destination_url"],
                                key=_carousel_card_widget_key(
                                    context_key,
                                    position,
                                    "destination_url",
                                ),
                                placeholder="https://www.sportscaveshop.com/products/...",
                            )
                        with fourth:
                            card["cta"] = _carousel_text_input(
                                f"Card {position} CTA",
                                card["cta"],
                                key=_carousel_card_widget_key(
                                    context_key,
                                    position,
                                    "cta",
                                ),
                                placeholder="Shop Now",
                            )
                        card["setup_notes"] = _carousel_text_area(
                            f"Card {position} setup notes (optional)",
                            card["setup_notes"],
                            key=_carousel_card_widget_key(
                                context_key,
                                position,
                                "setup_notes",
                            ),
                            height=68,
                            placeholder="Optional card-specific Meta setup notes",
                        )
                carousel["cards"][position - 1] = card

            carousel["setup_notes"] = _carousel_text_area(
                "Carousel cards / ad setup",
                carousel["setup_notes"],
                key=_carousel_setup_notes_widget_key(context_key),
                height=120,
                placeholder="Overall Carousel or final Meta ad setup notes.",
            )
    _store_carousel_copy_notes(workflow, carousel)
    st.session_state[ADS_IMAGE_STATE_KEY] = workflow


def _render_ads_setup_notes(result, workflow):
    if not ads_image_workflow.campaign_image_slots(result.get("campaign_type")):
        return
    if _is_instant_experience_result(result):
        return
    if result.get("campaign_type") == "Carousel":
        _render_carousel_setup_notes(result, workflow)
        return

    notes = dict(workflow.get("ad_notes") or {})
    with st.container(key="ads-setup-notes"):
        with st.expander("Ad setup notes (optional)", expanded=False):
            st.caption("Paste the final ChatGPT ad copy here. A text file will save beside the uploaded images.")
            first, second = st.columns(2)
            with first:
                notes["headlines"] = st.text_area(
                    "Headlines",
                    value=str(notes.get("headlines") or ""),
                    placeholder="Paste the 5 headlines, one per line.",
                    height=90,
                    key=f"ads-notes-headlines::{result['context_key']}",
                )
            with second:
                notes["descriptions"] = st.text_area(
                    "Descriptions",
                    value=str(notes.get("descriptions") or ""),
                    placeholder="Paste the 5 descriptions, one per line.",
                    height=90,
                    key=f"ads-notes-descriptions::{result['context_key']}",
                )
            third, fourth = st.columns(2)
            with third:
                notes["cards"] = st.text_area(
                    "Carousel cards / ad setup",
                    value=str(notes.get("cards") or ""),
                    placeholder=(
                        "Paste carousel card copy, CTA, Instant Experience setup, "
                        "or any final Meta build details from ChatGPT."
                    ),
                    height=120,
                    key=f"ads-notes-cards::{result['context_key']}",
                )
            with fourth:
                notes["primary_text_variations"] = st.text_area(
                    "Primary Text Variations",
                    value=str(notes.get("primary_text_variations") or ""),
                    placeholder="Paste the primary ad text variations.",
                    height=120,
                    key=f"ads-notes-primary-text::{result['context_key']}",
                )
    workflow["ad_notes"] = notes
    st.session_state[ADS_IMAGE_STATE_KEY] = workflow


def _render_instant_experience_copy_csv_control(result, workflow):
    context_key = str(result.get("context_key") or "")
    import_key = f"ads-ie-copy-csv-import::{context_key}"
    pending_upload = st.session_state.get(import_key)
    if pending_upload is not None:
        _process_instant_experience_copy_csv_upload(
            result,
            workflow,
            pending_upload,
        )

    heading_column, control_column = st.columns(
        [5, 1],
        vertical_alignment="center",
    )
    heading_column.subheader("Generated Ad Images")
    with control_column:
        with st.popover("Copy CSV", icon=":material/table_view:"):
            st.download_button(
                "Download blank CSV",
                data=build_instant_experience_copy_csv(
                    result,
                    workflow,
                    blank=True,
                ),
                file_name="sports-cave-instant-experience-copy-template.csv",
                mime="text/csv",
                key=f"ads-ie-copy-csv-blank::{context_key}",
                use_container_width=True,
            )
            current_download_slot = st.empty()
            uploaded_file = st.file_uploader(
                "Import completed CSV",
                type=["csv"],
                key=import_key,
                label_visibility="visible",
            )
            if uploaded_file is not None:
                _process_instant_experience_copy_csv_upload(
                    result,
                    workflow,
                    uploaded_file,
                )
            current_download_slot.download_button(
                "Download current CSV",
                data=build_instant_experience_copy_csv(result, workflow),
                file_name=_instant_experience_current_copy_csv_filename(result),
                mime="text/csv",
                key=f"ads-ie-copy-csv-current::{context_key}",
                use_container_width=True,
            )
            status = workflow.get("copy_csv_import_status")
            if isinstance(status, dict) and status.get("message"):
                if status.get("ok"):
                    st.success(status["message"])
                else:
                    st.error(status["message"])


def _render_instant_experience_concepts(result, workflow):
    _compact_instant_experience_slots(workflow)
    slot_specs = ads_image_workflow.campaign_image_slots("Instant Experience")
    slot_by_concept = {slot.get("concept_id"): slot for slot in slot_specs}
    concept_notes = _instant_experience_concept_copy_notes_from_workflow(workflow)
    _render_instant_experience_copy_csv_control(result, workflow)
    concept_notes = _instant_experience_concept_copy_notes_from_workflow(workflow)
    st.caption("Upload one cover for each Instant Experience route, then paste the three matching description options beneath it.")

    for concept in INSTANT_EXPERIENCE_CONCEPTS:
        concept_id = concept["id"]
        slot = slot_by_concept.get(concept_id) or {}
        heading = f"{concept['display_name'].upper()} — {concept['supporting_label']}"
        with st.container(border=True, key=f"ads-ie-concept::{result['context_key']}::{concept_id}"):
            st.markdown(f"**{heading}**")
            image_column, copy_column = st.columns([1, 2])
            with image_column:
                uploaded_file = st.file_uploader(
                    slot.get("label") or f"{concept['display_name']} Cover",
                    type=["jpg", "jpeg", "png", "webp"],
                    key=_slot_upload_key(result, workflow, slot["id"]),
                    max_upload_size=20,
                    label_visibility="collapsed",
                )
                _process_ads_image_upload(result, workflow, slot, uploaded_file)
                saved_slot = (workflow.get("slots") or {}).get(slot["id"]) or {}
                if saved_slot.get("valid"):
                    preview_data = saved_slot.get("preview_data")
                    if preview_data:
                        st.image(
                            preview_data,
                            width=INSTANT_EXPERIENCE_PREVIEW_DISPLAY_WIDTH,
                        )
                    elif saved_slot.get("preview_error"):
                        st.warning(saved_slot["preview_error"])
                    else:
                        st.caption("Preview not available. The original image is still retained.")
                    original_name = saved_slot.get("original_name") or "Uploaded cover"
                    st.caption(f"Filename: {original_name}")
                    st.caption(
                        "Original: "
                        f"{saved_slot.get('source_width') or saved_slot.get('output_width')} x "
                        f"{saved_slot.get('source_height') or saved_slot.get('output_height')} px"
                    )
                    st.caption(f"Original size: {_human_file_size(saved_slot.get('source_size') or len(saved_slot.get('data') or b''))}")
                    output_filename = _meta_output_filename(result, workflow, slot)
                    st.download_button(
                        "Download Full-Resolution Cover",
                        data=saved_slot["data"],
                        file_name=output_filename,
                        mime=ads_image_workflow.mime_type_for_image_filename(
                            output_filename,
                            source_format=saved_slot.get("source_format") or saved_slot.get("output_format") or "",
                        ),
                        key=f"ads-ie-cover-download::{result['context_key']}::{concept_id}",
                        use_container_width=True,
                    )
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
                else:
                    st.caption("Upload the finished full-resolution cover for this route.")

            with copy_column:
                variations = concept_notes.get(concept_id) or _blank_instant_experience_variations()
                for index in range(1, INSTANT_EXPERIENCE_COPY_VARIATION_COUNT + 1):
                    variation = _with_instant_experience_description_metadata(
                        variations[index - 1],
                        index,
                    )
                    st.markdown(f"**{variation['description_label']}**")
                    field_columns = st.columns([2, 1, 1])
                    for field_column, (field_key, field_label) in zip(
                        field_columns,
                        INSTANT_EXPERIENCE_COPY_FIELDS,
                    ):
                        with field_column:
                            widget_key = _instant_experience_copy_widget_key(
                                result["context_key"],
                                concept_id,
                                field_key,
                                index,
                            )
                            widget_args = {
                                "placeholder": (
                                    f"Description option {index}"
                                    if field_key == "primary_text"
                                    else f"Headline option {index}"
                                    if field_key == "headline"
                                    else f"CTA option {index}"
                                ),
                                "height": 50,
                                "key": widget_key,
                            }
                            if widget_key not in st.session_state:
                                widget_args["value"] = _preserve_multiline_text(
                                    variation.get(field_key)
                                )
                            variation[field_key] = st.text_area(field_label, **widget_args)
                            if field_key == "primary_text":
                                render_prompt_copy_button(
                                    _preserve_multiline_text(variation[field_key]),
                                    key=f"{widget_key}::copy",
                                    label="Copy Description",
                                    success_label="Description copied",
                                )
                    variations[index - 1] = variation
                concept_notes[concept_id] = variations
                complete_count = sum(
                    1
                    for variation_number, variation in enumerate(variations, start=1)
                    if _instant_experience_variation_complete(
                        variation,
                        concept_id=concept_id,
                        variation_number=variation_number,
                    )
                )
                image_ready = bool(
                    ((workflow.get("slots") or {}).get(slot["id"]) or {}).get("valid")
                    and ((workflow.get("slots") or {}).get(slot["id"]) or {}).get("data")
                )
                st.caption(
                    f"{concept['display_name']}: "
                    f"{'Image ready' if image_ready else 'Image needed'} · "
                    f"{complete_count} of {INSTANT_EXPERIENCE_COPY_VARIATION_COUNT} description options complete"
                )

    notes = dict(workflow.get("ad_notes") or {})
    notes["instant_experience_concepts"] = concept_notes
    workflow["ad_notes"] = notes
    st.session_state[ADS_IMAGE_STATE_KEY] = workflow


def _render_ads_image_slots(result, workflow):
    slot_specs = _ads_image_slot_specs_for_render(result, workflow)
    if not slot_specs:
        return
    if result.get("campaign_type") == "Carousel":
        _render_carousel_copy_csv_control(result, workflow)
    else:
        st.subheader("Generated Ad Images")
    if _is_instant_experience_result(result):
        st.caption(
            "Upload the three Instant Experience covers generated from the prompt above."
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
                output_label = (
                    f"{saved_slot.get('output_width')} x {saved_slot.get('output_height')} "
                    f"{saved_slot.get('output_format')}"
                )
                st.caption(
                    f"{output_label} | {saved_slot['output_size'] / (1024 * 1024):.2f} MB"
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
        for index, slot in enumerate(slot_specs):
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


def _render_ads_folder_picker(
    access_token,
    root_path,
    result,
    workflow,
    *,
    state_key=ADS_IMAGE_STATE_KEY,
    key_prefix="ads-picker",
    container_key="ads-dropbox-picker",
):
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
    st.session_state[state_key] = workflow
    folders = [
        entry
        for entry in _ads_directory_entries(access_token, current_path)
        if str(entry.get(".tag") or "").casefold() == "folder"
    ]

    with st.container(key=container_key):
        st.markdown('<div class="sc-mockups-dropbox-picker">', unsafe_allow_html=True)
        breadcrumb = dropbox_integration.breadcrumb_items(current_path, root_path)
        breadcrumb_columns = st.columns([1] * max(1, len(breadcrumb)))
        for index, (label, path) in enumerate(breadcrumb):
            target = root_path if not path else path
            with breadcrumb_columns[index]:
                if st.button(
                    str(label),
                    key=f"{key_prefix}-crumb::{result['context_key']}::{index}::{target}",
                    use_container_width=True,
                ):
                    workflow["picker_path"] = target
                    st.session_state[state_key] = workflow
                    st.rerun()

        if folders:
            for folder in folders:
                path = dropbox_integration.normalize_dropbox_path(
                    folder.get("path_display") or folder.get("path_lower") or ""
                )
                if st.button(
                    str(folder.get("name") or "Folder"),
                    icon=":material/folder:",
                    key=f"{key_prefix}-folder::{result['context_key']}::{path}",
                    use_container_width=True,
                ):
                    workflow["picker_path"] = path
                    st.session_state[state_key] = workflow
                    st.rerun()
        else:
            st.caption("No subfolders here.")

        with st.popover("New folder", icon=":material/create_new_folder:"):
            folder_name = st.text_input(
                "Folder name",
                key=f"{key_prefix}-new-name::{result['context_key']}::{current_path}",
            )
            if st.button(
                "Create",
                key=f"{key_prefix}-new-submit::{result['context_key']}::{current_path}",
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
                        st.session_state[state_key] = workflow
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
    export_folder = _ads_export_folder_path(clean_destination, result, workflow)
    if not dropbox_integration.path_is_within_root(export_folder, clean_root):
        raise ValueError("The export folder is outside the approved Files folder.")
    dropbox_integration.ensure_folder_path(
        access_token,
        export_folder,
        root_path=clean_root,
    )
    if _is_instant_experience_result(result):
        _compact_instant_experience_slots(workflow)
        return _save_instant_experience_package_to_dropbox(
            access_token,
            export_folder,
            result,
            workflow,
            progress_callback=progress_callback,
        )
    slot_specs = ads_image_workflow.campaign_image_slots(result.get("campaign_type"))
    valid_slot_ids = {slot["id"] for slot in _ads_image_valid_slots(result, workflow)}
    outcomes = dict(workflow.get("outcomes") or {})
    pending_slots = [
        slot
        for slot in slot_specs
        if slot["id"] in valid_slot_ids
        and (outcomes.get(slot["id"]) or {}).get("status") != "saved"
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
            proposed_path = dropbox_integration.join_upload_path(export_folder, filename)
            if dropbox_integration.get_metadata_if_exists(access_token, proposed_path):
                proposed_path = dropbox_integration.windows_numbered_path(access_token, proposed_path)
            resolved_filename = PurePosixPath(proposed_path).name

            def on_upload_progress(_row_index, _row_total, _name, uploaded, file_total):
                if progress_callback:
                    progress_callback(index, total, slot["label"], uploaded, file_total)

            upload_result = dropbox_integration.upload_batch(
                access_token,
                export_folder,
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
    notes_filename = build_ads_notes_filename(result, workflow)
    notes_text = build_ads_setup_notes_text(result, workflow, image_outcomes=outcomes)
    notes_bytes = notes_text.encode("utf-8")
    notes_result = dropbox_integration.upload_batch(
        access_token,
        export_folder,
        [
            {
                "relative_path": notes_filename,
                "data": notes_bytes,
                "size": len(notes_bytes),
            }
        ],
        conflict="replace",
    )
    notes_successes = list(notes_result.get("successes") or ())
    notes_failures = list(notes_result.get("failures") or ())
    if notes_successes:
        metadata = dict(notes_successes[0].get("metadata") or {})
        outcomes["_ad_setup_notes"] = {
            "status": "saved",
            "label": "Ad setup notes",
            "filename": notes_filename,
            "path": str(
                metadata.get("path_display")
                or metadata.get("path_lower")
                or dropbox_integration.join_upload_path(export_folder, notes_filename)
            ),
            "metadata": metadata,
            "asset_type": "meta_ads_notes",
            "signature": _ads_setup_notes_signature(result, workflow, image_outcomes=outcomes),
        }
    else:
        outcomes["_ad_setup_notes"] = {
            "status": "failed",
            "label": "Ad setup notes",
            "filename": notes_filename,
            "error": str((notes_failures[0] if notes_failures else {}).get("error") or "Upload failed."),
            "asset_type": "meta_ads_notes",
        }
    if result.get("campaign_type") == "Carousel":
        carousel_csv_bytes = build_carousel_copy_csv(result, workflow)
        carousel_csv_result = dropbox_integration.upload_batch(
            access_token,
            export_folder,
            [
                {
                    "relative_path": CAROUSEL_COPY_FILENAME,
                    "data": carousel_csv_bytes,
                    "size": len(carousel_csv_bytes),
                }
            ],
            conflict="replace",
        )
        carousel_csv_successes = list(carousel_csv_result.get("successes") or ())
        carousel_csv_failures = list(carousel_csv_result.get("failures") or ())
        if carousel_csv_successes:
            metadata = dict(carousel_csv_successes[0].get("metadata") or {})
            outcomes["_carousel_copy_csv"] = {
                "status": "saved",
                "label": "Carousel copy CSV",
                "filename": CAROUSEL_COPY_FILENAME,
                "path": str(
                    metadata.get("path_display")
                    or metadata.get("path_lower")
                    or dropbox_integration.join_upload_path(
                        export_folder,
                        CAROUSEL_COPY_FILENAME,
                    )
                ),
                "metadata": metadata,
                "asset_type": "meta_ads_copy_csv",
                "signature": hashlib.sha256(carousel_csv_bytes).hexdigest(),
            }
        else:
            outcomes["_carousel_copy_csv"] = {
                "status": "failed",
                "label": "Carousel copy CSV",
                "filename": CAROUSEL_COPY_FILENAME,
                "error": str(
                    (carousel_csv_failures[0] if carousel_csv_failures else {}).get("error")
                    or "Upload failed."
                ),
                "asset_type": "meta_ads_copy_csv",
            }
    workflow["saved_folder_path"] = export_folder
    workflow["ad_notes_saved_signature"] = (
        outcomes.get("_ad_setup_notes") or {}
    ).get("signature") or ""
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
                    asset_type=outcome.get("asset_type") or "meta_ads",
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


def _render_instant_experience_package_save(result, workflow):
    _compact_instant_experience_slots(workflow)
    ready_count = _instant_experience_image_ready_count(workflow)
    required_count = len(INSTANT_EXPERIENCE_CONCEPTS)
    st.caption(f"{ready_count} of {required_count} images ready.")
    for row in _instant_experience_status_rows(workflow):
        concept = row["concept"]
        st.caption(
            f"{concept['display_name']}: "
            f"{'Image ready' if row['image_ready'] else 'Image needed'} · "
            f"{row['copy_complete_count']} of {INSTANT_EXPERIENCE_COPY_VARIATION_COUNT} description options complete"
        )

    package_ready = instant_experience_package_ready(result, workflow)
    package_signature = ""
    package_saved = False
    if package_ready:
        package_signature = _instant_experience_package_signature(result, workflow)
        package_outcome = (workflow.get("outcomes") or {}).get("_instant_experience_package") or {}
        package_saved = (
            package_outcome.get("status") == "saved"
            and package_outcome.get("signature") == package_signature
        )
    if not package_ready:
        st.caption("Complete all three covers and all nine description options before saving the package.")

    if st.button(
        "Save Instant Experience Package",
        type="primary",
        icon=":material/save:",
        key=f"ads-images-save-open::{result['context_key']}",
        disabled=bool(workflow.get("saving")) or package_saved or not package_ready,
        use_container_width=True,
    ):
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
    action_label = "All concepts saved" if package_saved else "Save Instant Experience Package here"
    action_columns = st.columns([1, 1])
    if action_columns[0].button(
        action_label,
        key=f"ads-images-save-confirm::{result['context_key']}",
        disabled=bool(workflow.get("saving")) or package_saved or not package_ready,
        use_container_width=True,
    ):
        workflow["saving"] = True
        st.session_state[ADS_IMAGE_STATE_KEY] = workflow
        progress = st.progress(0, text="Saving Instant Experience package...")

        def update_progress(index, total, label, uploaded, file_total):
            file_fraction = uploaded / file_total if file_total else 1
            overall = ((index - 1) + min(1, file_fraction)) / max(1, total)
            progress.progress(min(1.0, overall), text=f"Saving {label}")

        try:
            workflow["destination_path"] = destination
            previous_saved = {
                slot_id
                for slot_id, outcome in (workflow.get("outcomes") or {}).items()
                if outcome.get("status") == "saved" and not str(slot_id).startswith("_")
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
            workflow["destination_path"] = workflow.get("saved_folder_path") or destination
            _save_ads_upload_metadata(
                {
                    slot_id: outcome
                    for slot_id, outcome in outcomes.items()
                    if slot_id not in previous_saved
                },
                user,
            )
            slot_ids = {
                slot["id"]
                for slot in ads_image_workflow.campaign_image_slots("Instant Experience")
            }
            successful = [
                row
                for slot_id, row in outcomes.items()
                if slot_id in slot_ids and row.get("status") == "saved"
            ]
            failed = [
                row
                for slot_id, row in outcomes.items()
                if slot_id in slot_ids and row.get("status") == "failed"
            ]
            _ads_clear_directory_cache(destination, workflow["destination_path"])
            record_activity_log(
                "ad_images_saved",
                "Ads",
                f"Saved Instant Experience package: {result['product_name']}",
                entity_type="dropbox_folder",
                entity_id=workflow["destination_path"],
                metadata={
                    "count": len(successful),
                    "failed_count": len(failed),
                    "campaign_type": result["campaign_type"],
                    "destination": workflow["destination_path"],
                    "concepts": [
                        {
                            "concept": row.get("concept"),
                            "filename": row.get("filename"),
                            "original_dimensions": [
                                row.get("source_width") or 0,
                                row.get("source_height") or 0,
                            ],
                            "copy_variations": row.get("copy_variation_count") or 0,
                            "path": row.get("relative_path") or row.get("path"),
                        }
                        for row in successful
                    ],
                    "files": [row.get("relative_path") or row.get("filename") for row in successful],
                },
            )
        except Exception as error:
            logging.warning("Instant Experience package save failed: %s", error)
            st.warning("The Instant Experience package could not be saved.")
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
    package_outcome = outcomes.get("_instant_experience_package") or {}
    if package_outcome.get("status") == "saved":
        st.success(f"Instant Experience package saved to {workflow['destination_path']}.")
        if st.button(
            "Open folder",
            icon=":material/folder_open:",
            key=f"ads-images-open-folder::{result['context_key']}",
        ):
            _open_ads_files_folder(workflow["destination_path"])
    elif package_outcome.get("status") == "failed":
        st.error(package_outcome.get("error") or "The Instant Experience package could not be saved.")
    for row in (workflow.get("outcomes") or {}).values():
        if row.get("status") == "failed" and row.get("concept"):
            st.error(f"{row.get('concept')}: {row.get('error') or 'Upload failed.'}")


def _render_ads_image_save(result, workflow):
    if not ads_image_workflow.campaign_image_slots(result.get("campaign_type")):
        return
    if _is_instant_experience_result(result):
        _render_instant_experience_package_save(result, workflow)
        return
    ready = ads_images_ready(result, workflow)
    valid_slots = _ads_image_valid_slots(result, workflow)
    has_valid_upload = bool(valid_slots)
    saved_count = _ads_image_saved_count(result, workflow)
    required_count = _ads_image_required_count(result)
    save_target_count = len(valid_slots)
    failed_count = _ads_image_failed_count(result, workflow)
    notes_current_signature = _ads_setup_notes_signature(result, workflow)
    notes_outcome = (workflow.get("outcomes") or {}).get("_ad_setup_notes") or {}
    notes_saved = (
        notes_outcome.get("status") == "saved"
        and notes_outcome.get("signature") == notes_current_signature
    )
    carousel_csv_saved = True
    if result.get("campaign_type") == "Carousel":
        carousel_csv_outcome = (
            (workflow.get("outcomes") or {}).get("_carousel_copy_csv") or {}
        )
        carousel_csv_saved = (
            carousel_csv_outcome.get("status") == "saved"
            and carousel_csv_outcome.get("signature")
            == _carousel_copy_csv_signature(result, workflow)
        )
    images_saved = saved_count >= len(valid_slots) and bool(valid_slots) and not failed_count
    all_saved = images_saved and notes_saved and carousel_csv_saved
    if not has_valid_upload:
        st.caption(f"0 of {required_count} images ready.")
    elif not ready:
        st.caption(f"{len(valid_slots)} of {required_count} images ready. You can save now and add more later.")
    else:
        st.caption(f"{len(valid_slots)} of {required_count} images ready.")
    if st.button(
        "Save Images",
        type="primary",
        icon=":material/save:",
        key=f"ads-images-save-open::{result['context_key']}",
        disabled=(
            bool(workflow.get("saving"))
            or all_saved
        ),
        use_container_width=True,
    ):
        if not has_valid_upload and not any(_ads_notes_for_workflow(workflow).values()):
            st.warning("Upload at least one valid generated image or add setup notes before saving.")
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
        "All images and notes saved"
        if all_saved
        else "Retry failed images"
        if failed_count
        else "Update setup notes"
        if images_saved and (not notes_saved or not carousel_csv_saved)
        else "Save setup notes here"
        if not has_valid_upload
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
                if outcome.get("status") == "saved" and not str(slot_id).startswith("_")
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
            workflow["destination_path"] = workflow.get("saved_folder_path") or destination
            _save_ads_upload_metadata(
                {
                    slot_id: outcome
                    for slot_id, outcome in outcomes.items()
                    if slot_id not in previously_saved
                },
                user,
            )
            slot_ids = {
                slot["id"]
                for slot in ads_image_workflow.campaign_image_slots(result.get("campaign_type"))
            }
            successful = [
                row
                for slot_id, row in outcomes.items()
                if slot_id in slot_ids and row.get("status") == "saved"
            ]
            failed = [
                row
                for slot_id, row in outcomes.items()
                if slot_id in slot_ids and row.get("status") == "failed"
            ]
            _ads_clear_directory_cache(destination, workflow["destination_path"])
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
    slot_ids = {
        slot["id"]
        for slot in ads_image_workflow.campaign_image_slots(result.get("campaign_type"))
    }
    successful = [
        row
        for slot_id, row in outcomes.items()
        if slot_id in slot_ids and row.get("status") == "saved"
    ]
    failed = [
        row
        for slot_id, row in outcomes.items()
        if slot_id in slot_ids and row.get("status") == "failed"
    ]
    notes_outcome = outcomes.get("_ad_setup_notes") or {}
    carousel_csv_outcome = outcomes.get("_carousel_copy_csv") or {}
    if successful:
        if failed:
            st.warning(f"{len(successful)} of {save_target_count} images saved. {len(failed)} need attention.")
        else:
            st.success(f"{len(successful)} images saved to {workflow['destination_path']}.")
        if notes_outcome.get("status") == "saved":
            st.caption(f"Ad setup notes saved: {notes_outcome.get('filename')}")
        elif notes_outcome.get("status") == "failed":
            st.warning(f"Ad setup notes were not saved: {notes_outcome.get('error') or 'Upload failed.'}")
        if result.get("campaign_type") == "Carousel":
            if carousel_csv_outcome.get("status") == "saved":
                st.caption(
                    f"Structured Carousel CSV saved: {carousel_csv_outcome.get('filename')}"
                )
            elif carousel_csv_outcome.get("status") == "failed":
                st.warning(
                    "Structured Carousel CSV was not saved: "
                    f"{carousel_csv_outcome.get('error') or 'Upload failed.'}"
                )
        if st.button(
            "Open folder",
            icon=":material/folder_open:",
            key=f"ads-images-open-folder::{result['context_key']}",
        ):
            _open_ads_files_folder(workflow["destination_path"])
    elif notes_outcome.get("status") == "saved":
        st.success(f"Ad setup notes saved to {workflow['destination_path']}.")
        if result.get("campaign_type") == "Carousel":
            if carousel_csv_outcome.get("status") == "saved":
                st.caption(
                    f"Structured Carousel CSV saved: {carousel_csv_outcome.get('filename')}"
                )
            elif carousel_csv_outcome.get("status") == "failed":
                st.warning(
                    "Structured Carousel CSV was not saved: "
                    f"{carousel_csv_outcome.get('error') or 'Upload failed.'}"
                )
        if st.button(
            "Open folder",
            icon=":material/folder_open:",
            key=f"ads-notes-open-folder::{result['context_key']}",
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
        f"{SPORTS_CAVE_ADS_FACTUAL_WORDING_GATE_V1}\n\n"
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

        _render_instant_experience_concepts(result, workflow)
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

        _render_instant_experience_concepts(result, workflow)
        _render_ads_image_save(result, workflow)
        st.subheader("2. Build it in Meta")
        st.caption("Upload the three Instant Experience covers generated from the prompt above.")
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
    _render_ads_setup_notes(result, workflow)
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
        div[data-testid="stMainBlockContainer"] {
            padding-top: 4rem !important;
        }
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
        div[class*="st-key-ads-ie-copy-field"] textarea {
            min-height: 42px !important;
            height: 42px !important;
            max-height: 42px !important;
            overflow-y: auto !important;
            resize: none !important;
            line-height: 1.35 !important;
            white-space: pre-wrap !important;
        }
        div[class*="st-key-ads-ie-concept-copy-field"] textarea {
            min-height: 50px !important;
            height: 50px !important;
            max-height: 50px !important;
            overflow-y: auto !important;
            resize: none !important;
            line-height: 1.35 !important;
            white-space: pre-wrap !important;
        }
        div[data-testid="stExpander"] details summary {
            min-height: 42px;
        }
        div[data-testid="stExpander"] details summary p {
            margin: 0;
        }
        @media (max-width: 720px) {
            .sc-ad-review-score {
                align-items: flex-start;
                flex-direction: column;
            }
            .st-key-ads-setup-notes [data-testid="stHorizontalBlock"] {
                flex-direction: column;
            }
            .st-key-ads-setup-notes [data-testid="stColumn"] {
                flex: 1 1 100% !important;
                min-width: 0 !important;
                width: 100% !important;
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

    result = st.session_state.get(ADS_RESULT_STATE_KEY)
    if (
        ADS_PRODUCT_NAME_KEY not in st.session_state
        and isinstance(result, dict)
        and result.get("product_name")
    ):
        st.session_state[ADS_PRODUCT_NAME_KEY] = result.get("product_name")

    product_rows = load_edition_ops_product_rows()
    product_name, product_selection = render_product_name_input(
        rows=product_rows,
        result=result,
    )
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
    product_url_state = prepare_ads_product_url_state(
        product_name,
        result=result,
        rows=product_rows,
        selection=product_selection,
    )
    product_url = st.text_input(
        "Product page URL *",
        placeholder="https://sportscave.com.au/products/example",
        key=ADS_PRODUCT_URL_KEY,
        on_change=_on_ads_product_url_changed,
    )
    if product_url_state.get("message") and not _clean_product_url(product_url):
        st.caption(product_url_state["message"])
    if product_url and not is_valid_product_page_url(product_url):
        st.error(PRODUCT_URL_ERROR)
    campaign_moment = render_campaign_moment_section()
    submitted = st.button(
        "Submit",
        type="primary",
        use_container_width=True,
    )

    if submitted:
        validation_message = validate_ads_inputs(
            product_name,
            category,
            country,
            campaign_type,
            product_url=product_url,
        )
        campaign_moment_message = validate_campaign_moment(
            campaign_moment,
            selected_country=country,
        )
        if campaign_moment_message:
            st.warning(campaign_moment_message)
        elif validation_message:
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
            product_id = product_url_state.get("product_id") or ""
            product_metadata = instant_experience_product_metadata_from_selection(
                product_selection,
                category=category,
            )
            context_key = ads_result_context_key(
                product_id,
                product_name,
                category,
                country,
                campaign_type,
                campaign_moment,
                product_metadata=product_metadata,
            )
            existing_result = result if isinstance(result, dict) else {}
            if existing_result.get("context_key") == context_key:
                if (
                    _clean_product_url(product_url) != existing_result.get("product_url")
                    or normalize_campaign_moment(
                        campaign_moment,
                        selected_country=country,
                    )
                    != campaign_moment_from_result(
                        existing_result,
                        selected_country=country,
                    )
                ):
                    result = build_ads_result_record(
                        product_name,
                        category,
                        country,
                        campaign_type,
                        product_id=product_id,
                        product_url=product_url,
                        variation_token=existing_result.get("variation_token"),
                        campaign_moment=campaign_moment,
                        product_metadata=product_metadata,
                        recent_instant_experience_fingerprints=st.session_state.get(
                            ADS_IE_RECENT_FINGERPRINTS_KEY,
                            [],
                        ),
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
                    campaign_moment=campaign_moment,
                    product_metadata=product_metadata,
                    recent_instant_experience_fingerprints=st.session_state.get(
                        ADS_IE_RECENT_FINGERPRINTS_KEY,
                        [],
                    ),
                )
                _reset_ads_image_workflow(result)
            st.session_state[ADS_RESULT_STATE_KEY] = result
            if campaign_type == "Instant Experience":
                update_recent_instant_experience_fingerprints(
                    result.get("instant_experience_fingerprints")
                )
            record_ad_prompt_generated(
                product_name,
                category,
                country,
                campaign_type,
                instant_experience_fingerprints=(
                    result.get("instant_experience_fingerprints")
                    if isinstance(result, dict)
                    else None
                ),
            )

    result = st.session_state.get(ADS_RESULT_STATE_KEY)
    refreshed_result = ensure_current_ads_result_prompt(result)
    if refreshed_result is not result:
        result = refreshed_result
        st.session_state[ADS_RESULT_STATE_KEY] = result
    if isinstance(result, dict) and result.get("master_prompt"):
        render_supported_result(result)
        _render_final_ad_review(result)


render_ads_page = render_page
render_marketing_factory_page = render_page
