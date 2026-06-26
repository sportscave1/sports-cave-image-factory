from contextlib import suppress
import csv
from datetime import datetime, timedelta
from functools import lru_cache
import io
from pathlib import Path
import gc
import hashlib
import html
import importlib
import json
import logging
import os
import re
import shutil
import tempfile
import time
import traceback
from urllib.parse import parse_qs, urlparse

APP_START_TIME = time.perf_counter()
LAST_STARTUP_STAGE_TIME = APP_START_TIME


def safe_startup_print(message):
    try:
        print(message, flush=True)
    except (OSError, ValueError):
        pass


safe_startup_print("STARTUP APP START total=0.000s stage=0.000s")

from dotenv import load_dotenv
import streamlit as st

import prompt_store

db = None
image_factory = None
os_pages = None
shopify_sync = None
edition_ops_module = None
orders_page_module = None
ads_intelligence_module = None
requests_module = None
components_module = None
pillow_modules = None


load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def log_startup_stage(stage, extra=""):
    global LAST_STARTUP_STAGE_TIME
    now = time.perf_counter()
    stage_elapsed = now - LAST_STARTUP_STAGE_TIME
    total_elapsed = now - APP_START_TIME
    suffix = f" {extra}" if extra else ""
    message = (
        f"STARTUP {stage} total={total_elapsed:.3f}s "
        f"stage={stage_elapsed:.3f}s{suffix}"
    )
    safe_startup_print(message)
    logging.info(message)
    if stage == "PAGE RENDER DONE":
        perf_message = f"PERF startup total={total_elapsed:.3f}s page={extra}"
        safe_startup_print(perf_message)
        logging.info(perf_message)
    if stage_elapsed > 3:
        warning = f"WARNING startup stage slow: {stage} took {stage_elapsed:.3f}s"
        safe_startup_print(warning)
        logging.warning(warning)
    LAST_STARTUP_STAGE_TIME = now

log_startup_stage("APP IMPORTS DONE")


def get_db():
    global db
    if db is None:
        log_startup_stage("DB MODULE IMPORT START")
        db = importlib.import_module("db")
        log_startup_stage("DB MODULE IMPORT DONE")
    return db


def get_image_factory():
    global image_factory
    if image_factory is None:
        log_startup_stage("IMAGE FACTORY IMPORT START")
        image_factory = importlib.import_module("image_factory")
        log_startup_stage("IMAGE FACTORY IMPORT DONE")
    return image_factory


def get_os_pages():
    global os_pages
    if os_pages is None:
        log_startup_stage("OS PAGES IMPORT START")
        os_pages = importlib.import_module("os_pages")
        log_startup_stage("OS PAGES IMPORT DONE")
    return os_pages


def get_shopify_sync():
    global shopify_sync
    if shopify_sync is None:
        log_startup_stage("SHOPIFY MODULE IMPORT START")
        shopify_sync = importlib.import_module("shopify_sync")
        log_startup_stage("SHOPIFY MODULE IMPORT DONE")
    return shopify_sync


def get_edition_ops():
    global edition_ops_module
    if edition_ops_module is None:
        log_startup_stage("EDITION OPS IMPORT START")
        edition_ops_module = importlib.import_module("edition_ops")
        log_startup_stage("EDITION OPS IMPORT DONE")
    return edition_ops_module


def get_orders_page():
    global orders_page_module
    if orders_page_module is None:
        log_startup_stage("ORDERS PAGE IMPORT START")
        orders_page_module = importlib.import_module("orders_page")
        log_startup_stage("ORDERS PAGE IMPORT DONE")
    return orders_page_module


def get_ads_intelligence_page():
    global ads_intelligence_module
    if ads_intelligence_module is None:
        log_startup_stage("ADS INTELLIGENCE IMPORT START")
        ads_intelligence_module = importlib.import_module("ads_intelligence_page")
        log_startup_stage("ADS INTELLIGENCE IMPORT DONE")
    return ads_intelligence_module


def get_requests_module():
    global requests_module
    if requests_module is None:
        requests_module = importlib.import_module("requests")
    return requests_module


def get_components_module():
    global components_module
    if components_module is None:
        components_module = importlib.import_module("streamlit.components.v1")
    return components_module


def get_pillow_modules():
    global pillow_modules
    if pillow_modules is None:
        from PIL import Image, ImageOps, UnidentifiedImageError

        pillow_modules = (Image, ImageOps, UnidentifiedImageError)
    return pillow_modules


BASE_DIR = Path(__file__).resolve().parent
RUNS_DIR = BASE_DIR / "output" / "runs"
UPLOAD_PREVIEW_DIR = BASE_DIR / "output" / "_ui-upload-previews"
EDITION_LOG_CACHE_PATH = BASE_DIR / "output" / "_cache" / "edition-log-snapshot.json"
EDITION_LOG_HEADER_ROW = 4
EDITION_LOG_DATA_START_ROW = 5
EDITION_LOG_SHEET_NAME = "Edition Log"
UPLOAD_PREVIEW_MAX_FILE_SIZE_BYTES = 6 * 1024 * 1024
UPLOAD_PREVIEW_MAX_SOURCE_EDGE = 4000
ENABLE_GOOGLE_DRIVE = os.getenv("ENABLE_GOOGLE_DRIVE", "false").lower() == "true"
GOOGLE_SHEET_URL = os.getenv(
    "GOOGLE_SHEET_URL",
    "https://docs.google.com/spreadsheets/d/1fe5OggyDdmgNw-LrLviA0B6JfD3wEqzuH6LA0JF_FR4/edit?gid=634918132#gid=634918132",
)
EDITION_LOG_JSON_URL = os.getenv("EDITION_LOG_JSON_URL", "").strip()
SHOPIFY_STORE_BASE_URL = os.getenv("SHOPIFY_STORE_BASE_URL", "https://sportscaveshop.com").rstrip("/")
ZIP_SAVE_DRIVE_FOLDER_URL = os.getenv(
    "ZIP_SAVE_DRIVE_FOLDER_URL",
    "https://drive.google.com/drive/folders/1FfXmTVuVGkD7PFhRjAtvPDZOn7Gpk3q_",
).strip()
# File Hub hidden until PSD/Drive asset workflow is active.
MENU_OPTIONS = [
    "Dashboard",
    "Mockups",
    "Product Uploads",
    "Edition Ops",
    "Orders",
    "Prodigi",
    "Ads Intelligence",
    "Marketing Factory",
    "VA Training",
    "Developer",
]
HIDDEN_PAGE_OPTIONS = [
    "Files",
    "Products",
    "Product Assets",
    "Webhook Events",
    "Sync Runs",
    "App Errors",
    "Persistence Check",
]
ALL_PAGE_OPTIONS = [*MENU_OPTIONS, *HIDDEN_PAGE_OPTIONS]
APP_VERSION = "Sports Cave OS Edition Fields MVP - 2026-06-22"
DEVELOPER_PAGE_PASSWORD = os.getenv("DEVELOPER_PAGE_PASSWORD", "sportscave1993")
DRIVE_SECTION_NAMES = {
    "mockups": "Mockups",
    "edition_ops": "Edition Ops",
    "product_uploads": "Product Uploads",
    "system_logs": "System Logs",
}
PASSWORD_ENV_KEYS = (
    "APP_PASSWORD",
    "STREAMLIT_PASSWORD",
    "SPORTS_CAVE_PASSWORD",
    "SITE_PASSWORD",
)
DATABASE_URL_ENV_KEYS = (
    "DATABASE_URL",
    "SUPABASE_DATABASE_URL",
    "SUPABASE_DB_URL",
    "POSTGRES_URL",
    "POSTGRES_PRISMA_URL",
    "POSTGRES_URL_NON_POOLING",
    "DATABASE_PRIVATE_URL",
    "DATABASE_PUBLIC_URL",
    "RENDER_DATABASE_URL",
)
LEGACY_BASE_ASSET_SPECS = [
    ("black", "Black Framed"),
    ("size-guide", "Size Guide"),
    ("oak", "Oak Framed"),
    ("white", "White Framed"),
    ("unframed", "Unframed"),
]
SPORT_OPTIONS = [
    "Soccer",
    "Motorsport",
    "Basketball",
    "AFL",
    "NRL",
    "Rugby Union",
    "Cricket",
    "NFL",
    "Baseball",
    "Hockey",
    "Tennis",
    "Custom",
]
PROMPT_LABELS = {
    "01-man-cave-prompt.txt": "01 - Man Cave (Product Page)",
    "02-office-prompt.txt": "02 - Office (Product Page)",
    "03-living-room-prompt.txt": "03 - Living Room (Product Page)",
    "04-close-up-wall-prompt.txt": "04 - Close-Up Premium Wall Shot (Social)",
    "05-limited-edition-detail-prompt.txt": "05 - Limited Edition Detail Shot (Social)",
    "06-instant-experience-cover-prompt.txt": "06 - Instant Experience Cover Banner (Social)",
    "07-home-sports-bar-prompt.txt": "07 - Premium Home Sports Bar (Social)",
    "08-collector-display-room-prompt.txt": "08 - Collector Display Room (Social)",
    "09-luxury-entry-wall-prompt.txt": "09 - Luxury Entry Statement Wall (Social)",
    "10-premium-unboxing-prompt.txt": "10 - Premium Unboxing / Collector Arrival (Social)",
    "11-wall-upgrade-moment-prompt.txt": "11 - The Wall Upgrade Moment (Social)",
    "12-fireplace-feature-wall-prompt.txt": "12 - Luxury Fireplace Feature Wall (Social)",
    "13-premium-bedroom-prompt.txt": "13 - Premium Bedroom / Private Retreat (Social)",
    "14-home-gym-prompt.txt": "14 - Home Gym / Motivation Wall (Social)",
    "15-premium-gift-reveal-prompt.txt": "15 - Premium Gift Reveal Scene (Social)",
}
PRODUCT_PAGE_PROMPT_NAMES = {
    "01-man-cave-prompt.txt",
    "02-office-prompt.txt",
    "03-living-room-prompt.txt",
}
EDITION_LOG_REQUEST_HEADERS = {
    "Accept": "application/json,text/plain,*/*",
    "User-Agent": "SportsCaveImageFactory/1.0",
}
EDITION_LOG_HTML_WARNING = (
    "The Edition Log URL returned an HTML page instead of JSON. Open the URL in an incognito browser. "
    "If you do not see raw JSON, redeploy Apps Script as a Web App with Execute as: Me and "
    "Who has access: Anyone with the link."
)
EXPECTED_APPS_SCRIPT_JSON_CODE = """function doGet(e) {
const SHEET_NAME = "Edition Log";
const HEADER_ROW = 4;
const DATA_START_ROW = 5;

const ss = SpreadsheetApp.getActiveSpreadsheet();
const sheet = ss.getSheetByName(SHEET_NAME);

if (!sheet) {
return jsonResponse({ error: "Sheet not found: " + SHEET_NAME });
}

const lastRow = sheet.getLastRow();
const lastCol = sheet.getLastColumn();

if (lastRow < DATA_START_ROW) {
return jsonResponse([]);
}

const headers = sheet
.getRange(HEADER_ROW, 1, 1, lastCol)
.getValues()[0]
.map(String);

const rows = sheet
.getRange(DATA_START_ROW, 1, lastRow - DATA_START_ROW + 1, lastCol)
.getDisplayValues();

const safeColumns = [
"Date Sent",
"Edition Name",
"Edition No.",
"Frame",
"Size",
"Shipping",
"Status",
"Notes",
"Product URL",
"Shopify Handle"
];

const output = rows
.map(row => {
const item = {};
headers.forEach((header, index) => {
if (safeColumns.includes(header)) {
item[header] = row[index] || "";
}
});
return item;
})
.filter(item => {
return Object.values(item).some(value => String(value).trim() !== "");
});

return jsonResponse(output);
}

function jsonResponse(data) {
return ContentService
.createTextOutput(JSON.stringify(data))
.setMimeType(ContentService.MimeType.JSON);
}"""

NEW_SHOPIFY_PRODUCT_PROMPT = """SOP 07B — Sports Cave Shopify Product Creation Using ChatGPT + Shopify Connector
Direct Draft Product Upload — Current Sports Cave Standard

PURPOSE
Create one complete new Sports Cave product directly in Shopify from final approved WebP assets.
Do not create a CSV. Do not ask for manual Shopify image uploads. Do not publish automatically.

NON-NEGOTIABLE OUTCOME
- Create the product as Draft.
- Published: false.
- Upload all required final WebP images to Shopify.
- Apply the exact Sports Cave gallery order.
- Create the exact 16-variant Frame × Size matrix.
- Apply current selling prices and the existing RRP compare-at prices.
- Map the correct frame image to every frame variant.
- Set every variant to continue selling when out of stock.
- Select the exact Shopify product category shown below.
- Write a complete, grounded Shopify description rather than short ad copy.
- Apply commercial SEO metadata and unique, accurate image alt text.
- Leave the product ready for manual review and publishing.

BRUTAL DRAFT RULE
Never publish a new product automatically.
Every new product must be created as:
- Status: Draft
- Published: false
Only the user may approve publication after checking the full draft.

REQUIRED ASSETS
The standard gallery requires these final approved WebP roles:
1. Black frame product image
2. Lifestyle mockup 1
3. Lifestyle mockup 2
4. Lifestyle mockup 3
5. Size guide
6. Oak frame product image
7. White frame product image
8. Unframed product image

All files must already be final, correctly cropped, optimised, and visually approved.
Do not redesign, crop, resize, relight, stylise, regenerate, or otherwise modify product media during this workflow.
Identify each image by its filename and visible role, not merely by upload sequence.
If a required role is missing or ambiguous, stop and ask before creating the draft.
If extra approved lifestyle images are supplied, place them after the first three lifestyle images and before the size guide only when the user explicitly wants them included.
Never silently omit a supplied approved image and never use exact duplicate files.

REQUIRED PRODUCT INPUTS
Use the supplied product files and context to identify:
- Product subject
- Athlete, team, rivalry, vehicle, event, or sporting moment
- Sport/category
- Product title idea, if supplied
- Target collection, if supplied
- Edition limit, if supplied
- Required or prohibited wording, if supplied
If the subject or moment is unclear, ask before creating the draft. Do not guess identities, events, dates, achievements, signatures, licensing, or edition facts.

DEFAULT SHOPIFY PRODUCT FIELDS
- Vendor: Sports Cave
- Product type: Framed Art
- Status: Draft
- Published: false
- Gift card: false
- Requires shipping: true
- Taxable: true
- Condition: New

EXACT SHOPIFY PRODUCT CATEGORY
Select the Shopify category result whose visible label is exactly:
Prints in Posters, Prints, & Visual Artwork
Do not leave the product assigned only to the parent category.
Do not substitute a nearby category.
If the connector cannot set this exact category, create the draft without an approximation and report this single manual action clearly.

SHOPIFY-CONTROLLED METAFIELDS
Do not invent values for controlled taxonomy metafields.
Leave controlled category metafields blank unless Shopify returns an accepted value for the selected category.
This includes, but is not limited to:
- Art movement
- Art style
- Artwork authenticity
- Artwork frame material
- Colour
- Frame style
- Material
- Orientation
- Painting medium
- Print edition type
- Rarity
- Signature placement
- Sports logo
- Suitable space
- Theme
- Printing method
Category selection must not be allowed to block creation of the draft.

PRODUCT TITLE AND H1
The Shopify product title is the page H1.
Create a concise, premium, search-intent-led title.
Rules:
- Put the subject or sporting moment first.
- Include Wall Art naturally.
- Aim for 10 words or fewer where practical.
- Make the title specific enough for both buyers and search engines.
- Do not keyword stuff.
- Do not use cheap marketplace strings such as poster print canvas gift decor.
- Do not rely on a poetic campaign name alone.
Preferred pattern:
[Subject or Moment] Wall Art
Optional when useful:
[Subject or Moment] [Sport/Location] Wall Art

SHOPIFY HANDLE
Create a clean lowercase, hyphenated handle.
Rules:
- Lowercase letters and hyphens only.
- Include the principal subject and wall-art intent.
- Remove filler words.
- Do not add random numbers or repeated keywords.
Preferred pattern:
[subject-or-moment]-wall-art

VISIBLE PRODUCT DESCRIPTION — COMPLETE SHOPIFY COPY
The description must be emotionally engaging but must read like a complete Shopify product description, not like a Meta ad.

Length:
- 90–130 words total.
- Never exceed 130 words.

Required structure — exactly four paragraphs:
1. One bold hook.
2. Concise story paragraph one.
3. Concise story paragraph two.
4. One bold scarcity close.

Required HTML format:
<p><strong>[One grounded, product-specific hook.]</strong></p>
<p>[Story paragraph one: identify the subject/moment and explain the sporting context clearly.]</p>
<p>[Story paragraph two: explain why the moment matters to the fan or collector, using specific and supportable details.]</p>
<p><strong>[Short scarcity close based only on the confirmed edition limit.]</strong></p>

Description rules:
- Use one bold hook only and one bold scarcity close only.
- Use two concise story paragraphs between them.
- Name the athlete, team, event, rivalry, car, track, or moment naturally where supported.
- Be specific, grounded, and readable on mobile.
- Emotion should come from recognisable details, not exaggerated claims.
- Vary sentence length naturally.
- Write unique copy for the actual product; do not reuse a stock hook across products.
- Keep the tone premium, collector-focused, and human.
- State a numbered or limited edition only when the edition limit is confirmed.
- Use the exact confirmed limit when supplied.

Do not:
- Write a sequence of advertising slogans.
- Overstate the cultural importance of the subject.
- Use vague claims such as a nation's memory, sacred, changed everything, defined a generation, or the greatest ever unless objectively supported and appropriate.
- Use generic clichés such as greatness never fades, more than a game, history on your wall, elevate your space, must-have, the ultimate tribute, or a moment frozen in time.
- Invent specifications, materials, paper stock, glaze type, frame construction, dimensions, certificates, authentication, hand-numbering, signatures, licensing, shipping details, production methods, or included hardware.
- Present an inferred detail as fact.
- Mention a reprint, second run, or sell-out consequence unless that policy is confirmed.
- Fill the visible description with SEO keywords.
- Use emoji, bullet lists, tables, inline CSS, classes, <div>, or <section>.

Allowed visible-description HTML:
- <p>
- <strong>
- <em> only when genuinely needed

SEO PRINCIPLE
SEO fields must be search-intent first and premium second.
They must tell Google and the buyer:
- Who or what the product features
- What the product is
- Which sport or category it belongs to
- Where or why a buyer would display or collect it
Do not make SEO fields poetic at the expense of clarity.

PRIMARY KEYWORD SELECTION
Select one primary commercial keyword based on the product subject.
Examples of keyword patterns:
- [Athlete] wall art
- [Moment/Event] wall art
- [Team] wall art
- Bathurst wall art
- football wall art / soccer wall art
- NBA wall art / basketball wall art
- cricket wall art
- motorsport wall art
Use closely related secondary terms naturally, but never stack them unnaturally.
Use sports posters Australia only for Australian subjects and markets where it is genuinely relevant.

SEO META TITLE
Rules:
- Target 50–60 characters; never exceed 60 characters unless Shopify itself requires otherwise.
- Put the primary keyword near the beginning.
- Clearly identify the subject and product type.
- Include Wall Art.
- Add Limited Edition, Framed Print, the sport, or Sports Cave only when it fits naturally within the limit.
- Do not use a poetic campaign title by itself.
- Do not keyword stuff.
Preferred pattern:
[Subject/Moment] Wall Art | Limited Edition [Sport] Print
Alternative when shorter:
[Subject/Moment] Wall Art | Sports Cave

SEO META DESCRIPTION
Rules:
- Target 145–160 characters.
- Mention the subject or moment.
- Use the primary keyword naturally once.
- Include limited-edition or collector intent only when confirmed.
- Mention a relevant use such as collectors, man caves, offices, bars, or homes when space allows.
- Sound commercial and human, not robotic.
- Do not use hashtags, emoji, fake urgency, keyword lists, or the phrase elevate your space.
- Do not include the store URL.
Preferred structure:
Shop premium [primary keyword] featuring [subject/moment]. [Confirmed collector/edition angle] for [relevant buyer or room intent].

OPEN GRAPH FIELDS
If the connector exposes Open Graph fields safely:
- Use a buyer-friendly OG title based on the product title.
- Use a concise OG description based on the visible description.
- Do not duplicate a keyword-stuffed SEO field.
If unsupported, leave for manual review.

IMAGE FILE NAMING BEFORE UPLOAD
Where file renaming is possible, use:
[subject]-[sport]-wall-art-[image-role]-sports-cave.webp
Rules:
- Lowercase letters and hyphens only.
- Product-specific and accurate.
- Do not use final, compressed, v2, copy, new, test, or random numbers.
Examples of image-role suffixes:
- black-frame
- man-cave
- office
- living-room
- size-guide
- oak-frame
- white-frame
- unframed
Do not rename a file in a way that changes or misstates its content.

IMAGE ALT TEXT — COMMERCIAL SEO STANDARD
Write unique alt text for every product image.
Rules:
- Usually 80–140 characters; aim for clarity rather than forcing a length.
- Describe the actual image accurately.
- Use the primary keyword naturally no more than once.
- Mention the athlete, team, moment, or sport only when supplied or clearly verified.
- Mention the visible setting for lifestyle images.
- Mention frame colour for frame product images.
- Mention size guide for the size guide.
- Keep each alt text meaningfully different.
- Write for accessibility first and SEO second.
- Do not begin with image of unless natural context requires it.
- Do not include sales hype, edition scarcity, hashtags, emoji, or keyword strings.
- Do not heavily describe irrelevant furniture.
- Never invent a person, team, event, logo, trophy, signature, or room detail.

Recommended alt-text pattern by role:
- Black frame: Black framed [subject] [sport] wall art for [relevant collector context].
- Lifestyle: [Subject] wall art in a [visible setting], styled for [relevant fan or collector context].
- Size guide: [Subject] wall art size guide showing the available framed and unframed dimensions.
- Oak frame: Oak framed [subject] wall art for [relevant collector context].
- White frame: White framed [subject] wall art for [relevant collector context].
- Unframed: Unframed [subject] [sport] wall art design for [relevant fan or collector context].
Use these as structures, not copy-and-paste templates.

EXACT PRODUCT GALLERY ORDER
After all images are uploaded and processed, order the Shopify media exactly as follows:
1. Black frame product image
2. Lifestyle mockup 1
3. Lifestyle mockup 2
4. Lifestyle mockup 3
5. Size guide
6. Oak frame product image
7. White frame product image
8. Unframed product image

The black frame must always be first.
The three primary lifestyle mockups must immediately follow it.
The size guide must come before all alternative frame product images.
Oak, White, and Unframed must be the final three images in that exact order.
Do not place the size guide second.
Do not intermix alternative frame images with lifestyle mockups.
Use Shopify-hosted media only after upload succeeds.
If any required upload fails, stop and identify the exact failed file.

VARIANT STRUCTURE — EXACTLY 16 VARIANTS
Option 1 name:
Frame
Option 1 values in this exact order:
1. Black
2. Oak
3. White
4. Unframed

Option 2 name:
Size
Option 2 values in this exact order:
1. XL - 62 × 87 cm (24.4 × 34.3 in)
2. L - 45 × 62 cm (17.7 × 24.4 in)
3. M - 30 × 45 cm (11.8 × 17.7 in)
4. S - 21 × 30 cm (8.3 × 11.8 in)

Create the variants in this exact order:
1. Black / XL
2. Black / L
3. Black / M
4. Black / S
5. Oak / XL
6. Oak / L
7. Oak / M
8. Oak / S
9. White / XL
10. White / L
11. White / M
12. White / S
13. Unframed / XL
14. Unframed / L
15. Unframed / M
16. Unframed / S

Do not abbreviate, reorder, or alter the visible option values.

CURRENT SELLING PRICES AND RRP
Currency: AUD
The Shopify Price field is the current selling price.
The Shopify Compare-at price field is the RRP.
Keep the RRP values below unchanged.

Black, Oak, and White framed variants:
- XL: Price 349.00 | Compare-at/RRP 428.00
- L: Price 269.00 | Compare-at/RRP 324.00
- M: Price 209.00 | Compare-at/RRP 259.00
- S: Price 159.00 | Compare-at/RRP 194.00

Unframed variants:
- XL: Price 159.00 | Compare-at/RRP 194.00
- L: Price 119.00 | Compare-at/RRP 142.00
- M: Price 89.00 | Compare-at/RRP 103.00
- S: Price 55.00 | Compare-at/RRP 64.00

Do not reverse Price and Compare-at price.
Do not apply the unframed price to a framed variant.
Do not calculate new RRPs.

INVENTORY AND CONTINUE-SELLING RULE
For every one of the 16 variants:
- Track inventory: true when supported.
- Inventory policy: continue.
- The Shopify checkbox Continue selling when out of stock must be ticked.
- Requires shipping: true.
- Taxable: true.
Do not use inventory policy deny.
If the connector cannot set or verify inventory policy, report all affected variants for manual review.
Do not invent stock quantities.

SKU RULES
Create 16 unique uppercase SKUs using a short product-specific prefix and these suffixes:
- Black: A1B, A2B, A3B, A4B
- Oak: A1O, A2O, A3O, A4O
- White: A1W, A2W, A3W, A4W
- Unframed: A1, A2, A3, A4
A1 = XL, A2 = L, A3 = M, A4 = S.
Use uppercase letters and numbers only. No spaces or punctuation.
Check that no SKU is duplicated in the store before finalising.

VARIANT IMAGE MAPPING
After media upload and variant creation:
- Assign the black frame product image to all four Black variants.
- Assign the oak frame product image to all four Oak variants.
- Assign the white frame product image to all four White variants.
- Assign the unframed product image to all four Unframed variants.
Do not assign lifestyle images or the size guide to variants.
After mapping, verify each selector visually:
- Clicking Black shows the black frame image.
- Clicking Oak shows the oak frame image.
- Clicking White shows the white frame image.
- Clicking Unframed shows the unframed image.

TAGS AND COLLECTION INTENT
Use 8–16 clean tags based on confirmed product facts.
Core tags when applicable:
- Collector Series
- Limited Edition, only when confirmed
- Sports Wall Art
- Limited Edition Sports Prints, only when confirmed
- Framed Sports Art
- Man Cave Wall Art
Add sport, athlete, team, event, and category tags naturally.
Do not use performance claims such as Best Seller, Best Selling, Popular, Viral, Trending, Featured, or New Arrival unless proven or explicitly instructed.
Use tags to support the correct automated sport and collector collections.
Do not assign an unrelated collection.

GOOGLE SHOPPING
When safely supported:
- Condition: New
- Custom product: true
- Age group: Adult only if required
- Gender: Unisex only if required
Do not guess unsupported Google taxonomy values.

PRE-CREATION VALIDATION
Before creating the draft, confirm internally:
- The product subject and sport are clear.
- All eight required image roles are present and distinct.
- Gallery order is planned exactly.
- The title/H1 is specific and search-led.
- The handle is clean.
- The description is 90–130 words.
- The description has exactly one bold hook, two story paragraphs, and one bold scarcity close.
- No product specifications were invented.
- The primary keyword is selected.
- SEO title is 60 characters or fewer.
- Meta description is 145–160 characters where possible and never keyword stuffed.
- Every image has unique, accurate alt text.
- The exact Shopify category is planned.
- All 16 variants are planned in the correct order.
- The selling prices and RRP values match this SOP.
- Inventory policy is continue for all variants.
- Variant image mapping is planned.
- All SKUs are unique.
- Product will remain Draft and unpublished.

CREATION WORKFLOW — USE THIS ORDER
1. Identify the product subject, sport, and primary keyword.
2. Classify all uploaded images by role.
3. Create the product title/H1 and handle.
4. Write the four-paragraph 90–130-word description.
5. Create the SEO title and meta description.
6. Create unique alt text for every image.
7. Create clean tags.
8. Upload all required WebP files to Shopify.
9. Confirm every upload processed successfully.
10. Create the product as Draft and unpublished.
11. Select Prints in Posters, Prints, & Visual Artwork.
12. Attach and order all product media exactly.
13. Create all 16 variants in the exact option and variant order.
14. Set selling prices and Compare-at/RRP values exactly.
15. Set inventory policy to continue for every variant.
16. Add unique SKUs.
17. Assign the correct frame image to each variant group.
18. Apply SEO fields and alt text where supported.
19. Validate the complete draft.
20. Return the Shopify draft/admin link and a concise manual-review list.

POST-CREATION VALIDATION
Verify all of the following:
- Correct product exists once; no duplicate was created.
- Status is Draft.
- Published is false.
- Product title and handle are correct.
- Category displays Prints in Posters, Prints, & Visual Artwork.
- Description is clean HTML and 90–130 words.
- Description structure is correct and not generic ad copy.
- SEO title and meta description are present and within limits.
- All required images uploaded.
- Gallery order is Black, Lifestyle 1, Lifestyle 2, Lifestyle 3, Size Guide, Oak, White, Unframed.
- Every image has unique, accurate alt text where supported.
- Frame options display Black, Oak, White, Unframed.
- Size options display XL, L, M, S with the exact dimensions.
- All 16 variants exist in the correct order.
- Current selling prices are correct.
- Existing RRP compare-at prices are unchanged and correct.
- Continue selling when out of stock is enabled for every variant.
- SKUs are unique.
- Black, Oak, White, and Unframed variant image mappings work correctly.
- No unsupported taxonomy metafields were invented.
If the connector cannot verify any item, state exactly what requires manual review.

FAILURE RULES
Do not guess or retry blindly.
If creation fails, determine whether the cause is:
- Ambiguous product identity
- Missing required image role
- Failed media upload
- Existing handle conflict
- Duplicate SKU
- Variant creation failure
- Category rejection
- Unsupported controlled metafield
- Missing connector permission
- Inventory policy failure
Create the draft without risky optional taxonomy fields when necessary, but never substitute a wrong category or publish the product.
Do not create a second product as a workaround for a failed update during the same run.

FINAL EXECUTION PROMPT
I have uploaded the final approved Sports Cave WebP assets for one product.
Use SOP 07B and create the Shopify product directly through the connected Shopify tool.
Create it as Draft and keep it unpublished.
Use the exact gallery order: Black frame, three lifestyle mockups, Size Guide, Oak frame, White frame, Unframed.
Write a complete 90–130-word product description with one bold hook, two concise story paragraphs, and one bold scarcity close. Keep it specific and grounded, avoid generic clichés, and invent no specifications.
Apply search-intent-led SEO metadata and unique, accurate image alt text.
Select the exact category Prints in Posters, Prints, & Visual Artwork.
Create the exact 16 variants with Frame ordered Black, Oak, White, Unframed and Size ordered XL, L, M, S.
Use the current Sports Cave selling-price matrix and preserve the listed RRP compare-at prices.
Enable Continue selling when out of stock for all variants.
Map each frame image to its matching variants.
Do not publish. Return the draft link and validation results.
"""
UPDATE_EXISTING_PRODUCT_PROMPT = """SOP 07C — Sports Cave Existing Shopify Product Update and Standardisation
Direct Existing-Product Update — No CSV Import Required

PURPOSE
Update the correct existing Sports Cave Shopify product without creating a duplicate.
This SOP supports two modes:
1. Media Update Mode — replace and reorder product images, update image alt text, and repair variant image mapping.
2. Full Standardisation Mode — apply Media Update Mode plus current Sports Cave category, description, SEO, variant-order, pricing, inventory-policy, and variant-image standards when the user explicitly requests a full refresh or standardisation.

BRUTAL EXISTING-PRODUCT RULE
Never create a new product when the task is to update an existing product.
Find and verify the exact existing product using at least one of:
- Shopify product URL
- Product ID
- Exact handle
- Exact product title
- One unambiguous Shopify search result matching the supplied subject
If more than one product could match, stop and ask for confirmation.

STATUS RULE
Keep the existing product status and publication state unchanged unless the user explicitly instructs otherwise.
- Active stays Active.
- Draft stays Draft.
- Archived requires confirmation before editing.
Never publish automatically.

REQUIRED REPLACEMENT ASSETS
The standard final gallery contains:
1. Black frame product image
2. Lifestyle mockup 1
3. Lifestyle mockup 2
4. Lifestyle mockup 3
5. Size guide
6. Oak frame product image
7. White frame product image
8. Unframed product image
All replacement files must be final approved WebP assets.
Do not redesign, crop, resize, relight, regenerate, or otherwise edit them.
Identify roles from filename and content. If a role is missing or ambiguous, ask before replacing media.

SAFE MEDIA REPLACEMENT SEQUENCE
1. Find and verify the correct existing product.
2. Review current media and current variant-image mapping.
3. Upload all new WebP files first.
4. Confirm new Shopify-hosted media exists and has processed successfully.
5. Attach the new media to the existing product.
6. Apply unique SEO alt text.
7. Reorder the gallery.
8. Reassign variant images.
9. Confirm the new gallery and variant mappings work.
10. Remove only the old media being replaced.
Never remove old media before replacement media is confirmed.

EXACT PRODUCT GALLERY ORDER
Use this exact order:
1. Black frame product image
2. Lifestyle mockup 1
3. Lifestyle mockup 2
4. Lifestyle mockup 3
5. Size guide
6. Oak frame product image
7. White frame product image
8. Unframed product image
The black frame must be first.
The three lifestyles must follow it immediately.
The size guide must be fifth.
Oak, White, and Unframed must be the final three images in that order.
If extra approved lifestyle images are explicitly retained, place them after the first three lifestyle images and before the size guide.
Do not omit a retained image or keep an obsolete duplicate.

IMAGE FILE NAMING
Where safe and possible, use:
[subject]-[sport]-wall-art-[image-role]-sports-cave.webp
Use lowercase letters and hyphens only.
Do not use final, compressed, v2, copy, new, test, or random numbers.
Do not mislabel image content.

IMAGE ALT TEXT — APPLY TO EVERY REPLACEMENT IMAGE
Rules:
- Usually 80–140 characters.
- Accurately describe the actual image.
- Use the main commercial keyword naturally no more than once.
- Mention the athlete, event, team, or sport only when verified.
- Mention visible room setting for lifestyle mockups.
- Mention frame colour for Black, Oak, and White product images.
- Identify the size guide as a size guide.
- Keep every alt text unique.
- Do not include sales hype, hashtags, emoji, keyword stuffing, or invented details.
- Do not overdescribe irrelevant furniture.
- Write for accessibility first and SEO second.

VARIANT IMAGE MAPPING — ALWAYS REPAIR WHEN MEDIA IS UPDATED
- All Black variants use the black frame product image.
- All Oak variants use the oak frame product image.
- All White variants use the white frame product image.
- All Unframed variants use the unframed product image.
Never map lifestyle images or the size guide to variants.
Visually verify each Frame selector after mapping.

MEDIA UPDATE MODE — DEFAULT SCOPE
Unless the user asks for a full standardisation, change only:
- Product images
- Gallery order
- Image alt text
- Variant image mapping
Preserve:
- Product title
- Handle
- Description
- SEO title and meta description
- Tags and collections
- Category
- Product type and vendor
- Variant option names and values
- Prices and compare-at prices
- SKUs
- Inventory quantities and inventory policy
- Product status and publication state
Report any visible mismatch against the current Sports Cave standard, but do not silently change protected fields in Media Update Mode.

FULL STANDARDISATION MODE
Use this mode only when the user explicitly asks to standardise, fully refresh, or bring the existing product to the current Sports Cave setup.
Before applying it, confirm the product is intended to use the standard 16-variant Frame × Size model.
In Full Standardisation Mode, apply all rules below.

EXACT SHOPIFY CATEGORY IN FULL STANDARDISATION MODE
Select the Shopify category result whose visible label is exactly:
Prints in Posters, Prints, & Visual Artwork
Do not use only the parent category or a nearby substitute.
If the connector cannot set the exact category, preserve the current category and report the manual action.
Do not invent controlled taxonomy metafields.

VISIBLE PRODUCT DESCRIPTION IN FULL STANDARDISATION MODE
Rewrite only when requested.
Requirements:
- 90–130 words total.
- Exactly four paragraphs.
- Paragraph 1: one bold, grounded, product-specific hook.
- Paragraph 2: concise story paragraph identifying the subject or moment and context.
- Paragraph 3: concise story paragraph explaining collector/fan significance through supportable details.
- Paragraph 4: one bold scarcity close based only on confirmed edition facts.
- Exactly one bold hook and one bold close.
- Clean Shopify-safe HTML using <p>, <strong>, and <em> only when necessary.
- Specific and human, not a series of ad slogans.
- No generic clichés such as greatness never fades, more than a game, history on your wall, elevate your space, must-have, ultimate tribute, or moment frozen in time.
- No overstated claims such as a nation's memory or sacred unless objectively justified.
- No invented materials, dimensions, paper, glazing, authentication, signatures, edition facts, shipping details, production methods, or included hardware.

SEO IN FULL STANDARDISATION MODE
SEO must be search-intent first and premium second.
SEO title:
- 50–60 characters preferred; 60 maximum.
- Primary commercial keyword near the beginning.
- Include subject and Wall Art.
- Add Limited Edition, Framed Print, sport, or Sports Cave only when it fits naturally.
- Do not use a poetic campaign title alone.
Meta description:
- 145–160 characters preferred.
- Mention subject/moment and primary keyword naturally.
- Include confirmed collector/edition intent and a relevant buyer or room use when space allows.
- No keyword stuffing, hashtags, emoji, store URL, or elevate your space.
Handle:
- Preserve the existing handle unless the user explicitly asks to change it.
- If changed, use a clean lowercase hyphenated subject-wall-art handle and warn about redirect requirements.

EXACT STANDARD VARIANT OPTIONS IN FULL STANDARDISATION MODE
Option 1:
Frame
Values in this exact order:
1. Black
2. Oak
3. White
4. Unframed

Option 2:
Size
Values in this exact order:
1. XL - 62 × 87 cm (24.4 × 34.3 in)
2. L - 45 × 62 cm (17.7 × 24.4 in)
3. M - 30 × 45 cm (11.8 × 17.7 in)
4. S - 21 × 30 cm (8.3 × 11.8 in)

Exact variant order:
Black / XL
Black / L
Black / M
Black / S
Oak / XL
Oak / L
Oak / M
Oak / S
White / XL
White / L
White / M
White / S
Unframed / XL
Unframed / L
Unframed / M
Unframed / S

Do not delete and recreate variants until current orders, SKUs, fulfilment references, and app dependencies have been considered.
When Shopify cannot safely reorder existing variants in place, report the limitation before destructive changes.

CURRENT SELLING PRICES AND RRP IN FULL STANDARDISATION MODE
Currency: AUD
Price = current selling price.
Compare-at price = RRP.

Black, Oak, and White framed variants:
- XL: Price 349.00 | Compare-at/RRP 428.00
- L: Price 269.00 | Compare-at/RRP 324.00
- M: Price 209.00 | Compare-at/RRP 259.00
- S: Price 159.00 | Compare-at/RRP 194.00

Unframed variants:
- XL: Price 159.00 | Compare-at/RRP 194.00
- L: Price 119.00 | Compare-at/RRP 142.00
- M: Price 89.00 | Compare-at/RRP 103.00
- S: Price 55.00 | Compare-at/RRP 64.00

Keep the RRP values unchanged.
Do not reverse Price and Compare-at price.
Apply the entire matrix consistently; do not partially update only some frame colours or sizes.

CONTINUE SELLING IN FULL STANDARDISATION MODE
For all 16 variants:
- Track inventory: true when supported.
- Inventory policy: continue.
- Continue selling when out of stock must be ticked.
- Requires shipping: true.
- Taxable: true.
Do not invent inventory quantities.
If the connector cannot set or verify the policy, report each affected variant.

SKU PROTECTION
Preserve existing unique SKUs unless the user asks to rebuild them or a SKU is missing/invalid.
When rebuilding, use an uppercase product prefix and:
- Black: A1B, A2B, A3B, A4B
- Oak: A1O, A2O, A3O, A4O
- White: A1W, A2W, A3W, A4W
- Unframed: A1, A2, A3, A4
A1 = XL, A2 = L, A3 = M, A4 = S.
Check store-wide uniqueness before saving.

TAGS, COLLECTIONS, AND CONTROLLED METAFIELDS
Preserve existing tags and collections unless the user asks for SEO or collection cleanup.
Never add unproven performance tags such as Best Seller, Best Selling, Popular, Viral, Trending, Featured, or New Arrival.
Do not fill controlled category metafields with guessed values.

EXISTING PRODUCT WORKFLOW
1. Identify and verify the exact existing product.
2. Confirm update mode: Media Update or Full Standardisation.
3. Review current media, variants, prices, inventory policy, category, SEO, and variant image mappings as required by the selected mode.
4. Classify uploaded replacement images.
5. Generate unique, accurate alt text.
6. Upload all replacement media first.
7. Confirm uploads processed successfully.
8. Attach and order media exactly.
9. Repair frame variant image mappings.
10. In Full Standardisation Mode, apply the exact category, description/SEO rules, option order, pricing matrix, RRP, and continue-selling policy.
11. Verify all changes.
12. Remove old replaced media only after the new setup is confirmed.
13. Keep status and publication state unchanged.
14. Return the existing product/admin link and a concise validation report.

POST-UPDATE VALIDATION
Always verify:
- Correct existing product was updated.
- No duplicate product was created.
- Product status and publication state did not change.
- New media uploaded successfully before old media was removed.
- Gallery order is Black, Lifestyle 1, Lifestyle 2, Lifestyle 3, Size Guide, Oak, White, Unframed.
- All replacement images have unique accurate alt text where supported.
- Black, Oak, White, and Unframed variant image mappings work.
In Full Standardisation Mode also verify:
- Category is Prints in Posters, Prints, & Visual Artwork.
- Description is 90–130 words with the required four-paragraph structure.
- SEO fields meet length and search-intent rules.
- Frame values are Black, Oak, White, Unframed.
- Size values are XL, L, M, S with exact dimensions.
- 16 variants are present in the intended order.
- Current selling prices and RRP values match the SOP.
- Continue selling when out of stock is enabled for all variants.
- SKUs remain unique.
If any field cannot be verified, list it for manual review.

FAILURE RULES
Do not guess and do not create a new product as a workaround.
If the update fails, first check:
- Wrong or ambiguous product match
- Failed media upload or processing
- Missing connector permission
- Variant image assignment failure
- Variant reorder limitation
- Category rejection
- Duplicate SKU
- Inventory policy failure
- Media deletion failure
Keep old media until replacement media is safely attached.
Retry a failed upload once; if it still fails, report the exact file.

FINAL EXECUTION PROMPT — MEDIA UPDATE MODE
I have uploaded final approved replacement Sports Cave WebP assets.
Use SOP 07C in Media Update Mode.
Update the existing Shopify product only; do not create a new product.
Upload new media first, apply the exact gallery order, write unique accurate SEO alt text, repair Black/Oak/White/Unframed variant image mappings, confirm the result, and only then remove the replaced old media.
Keep title, handle, description, SEO, category, variants, prices, RRPs, SKUs, inventory, tags, collections, status, and publication state unchanged.

FINAL EXECUTION PROMPT — FULL STANDARDISATION MODE
I have uploaded final approved replacement Sports Cave WebP assets.
Use SOP 07C in Full Standardisation Mode.
Update the existing Shopify product only; do not create a duplicate.
Apply the exact gallery order, current description and commercial SEO rules, exact category Prints in Posters, Prints, & Visual Artwork, exact Frame and Size ordering, current Sports Cave selling prices, unchanged RRP compare-at prices, Continue selling when out of stock for every variant, and correct frame variant image mappings.
Keep the existing status and publication state unchanged.
Return the product link and full validation results.
"""


st.set_page_config(
    page_title="Sports Cave OS",
    layout="wide",
    initial_sidebar_state="expanded",
)
log_startup_stage("SET PAGE CONFIG DONE")


def inject_styles():
    st.markdown(
        """
        <style>
        :root {
            --sc-bg: #0B0B0D;
            --sc-panel: #141416;
            --sc-panel-soft: #1B1B1E;
            --sc-text: #F5F2EA;
            --sc-muted: #A6A19A;
            --sc-gold: #D4A54C;
            --sc-border: #343238;
            --sc-danger: #D56A4A;
        }

        @keyframes sc-status-progress {
            0% { transform: translateX(-120%); }
            100% { transform: translateX(260%); }
        }

        [data-testid="stAppViewContainer"] {
            background:
                radial-gradient(circle at 82% 4%, rgba(212, 165, 76, 0.10), transparent 28rem),
                linear-gradient(180deg, #0B0B0D 0%, #111114 100%);
            color: var(--sc-text);
        }

        header[data-testid="stHeader"],
        header[data-testid="stHeader"] > div,
        [data-testid="stToolbar"] {
            background: var(--sc-bg) !important;
        }

        header[data-testid="stHeader"] {
            border-bottom: 1px solid rgba(212, 165, 76, 0.16);
        }

        div[data-testid="stStatusWidget"] {
            width: 148px !important;
            height: 8px !important;
            min-height: 8px !important;
            border: 1px solid rgba(212, 165, 76, 0.44) !important;
            border-radius: 999px !important;
            background: rgba(245, 242, 234, 0.12) !important;
            overflow: hidden !important;
            position: relative !important;
            padding: 0 !important;
            box-shadow: none !important;
        }

        div[data-testid="stStatusWidget"] * {
            display: none !important;
        }

        div[data-testid="stStatusWidget"]::after {
            content: "";
            position: absolute;
            inset: 0 auto 0 0;
            width: 42%;
            border-radius: 999px;
            background: linear-gradient(90deg, transparent, #D4A54C, transparent);
            animation: sc-status-progress 1.15s ease-in-out infinite;
        }

        header[data-testid="stHeader"] button,
        header[data-testid="stHeader"] svg,
        [data-testid="stToolbar"] button,
        [data-testid="stToolbar"] svg {
            color: var(--sc-text) !important;
            fill: var(--sc-text) !important;
        }

        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #09090B 0%, #151518 100%);
            border-right: 1px solid rgba(212, 165, 76, 0.20);
        }

        [data-testid="stSidebar"] * {
            color: var(--sc-text);
        }

        div[data-testid="stRadio"] label p {
            font-weight: 600;
        }

        h1, h2, h3, p, label, [data-testid="stCaptionContainer"] {
            color: var(--sc-text);
        }

        [data-testid="stCaptionContainer"], .sc-muted {
            color: var(--sc-muted) !important;
        }

        [data-testid="stMetric"] {
            background: linear-gradient(145deg, rgba(27, 27, 30, 0.96), rgba(17, 17, 20, 0.96));
            border: 1px solid var(--sc-border);
            border-top: 2px solid rgba(212, 165, 76, 0.75);
            border-radius: 14px;
            padding: 1rem;
        }

        [data-testid="stVerticalBlockBorderWrapper"] {
            background: rgba(20, 20, 22, 0.86);
            border-color: var(--sc-border) !important;
        }

        [data-testid="stDataFrame"], [data-testid="stExpander"] {
            border-color: var(--sc-border) !important;
        }

        [data-testid="stExpander"] details,
        [data-testid="stExpander"] details[open] {
            background: rgba(20, 20, 22, 0.92) !important;
            border: 1px solid var(--sc-border) !important;
            border-radius: 16px !important;
            overflow: hidden !important;
        }

        [data-testid="stExpander"] summary,
        [data-testid="stExpander"] summary:hover,
        [data-testid="stExpander"] details[open] summary,
        [data-testid="stExpander"] details[open] summary:hover {
            background: rgba(20, 20, 22, 0.96) !important;
            color: var(--sc-text) !important;
            border: none !important;
            box-shadow: none !important;
        }

        [data-testid="stExpander"] summary *,
        [data-testid="stExpander"] summary svg,
        [data-testid="stExpander"] summary p,
        [data-testid="stExpander"] details[open] summary *,
        [data-testid="stExpander"] details[open] summary svg,
        [data-testid="stExpander"] details[open] summary p {
            color: var(--sc-text) !important;
            fill: var(--sc-text) !important;
            stroke: var(--sc-text) !important;
        }

        [data-testid="stExpander"] details > div,
        [data-testid="stExpander"] details[open] > div {
            background: rgba(20, 20, 22, 0.96) !important;
            color: var(--sc-text) !important;
        }

        [data-testid="stExpander"] details > div * ,
        [data-testid="stExpander"] details[open] > div * {
            color: var(--sc-text) !important;
        }

        /*
        Sports Cave readability contract:
        light/cream/white controls always use black text; dark panels keep warm white.
        Keep this near the end of the core theme so page-specific CSS cannot make
        prompt boxes, buttons, upload cards, or admin tools unreadable.
        */
        textarea,
        textarea:focus,
        textarea:hover,
        input,
        input:focus,
        input:hover,
        [data-testid="stTextArea"] textarea,
        [data-testid="stTextArea"] textarea:focus,
        [data-testid="stTextArea"] textarea:hover,
        [data-testid="stTextInput"] input,
        [data-testid="stTextInput"] input:focus,
        [data-testid="stTextInput"] input:hover,
        [data-testid="stNumberInput"] input,
        [data-testid="stNumberInput"] input:focus,
        [data-testid="stNumberInput"] input:hover,
        [data-testid="stSelectbox"] div[data-baseweb="select"] *,
        [data-testid="stMultiSelect"] div[data-baseweb="select"] *,
        [data-testid="stDateInput"] input,
        [data-testid="stTimeInput"] input,
        [data-testid="stFileUploader"] [data-baseweb="tag"] *,
        section[data-testid="stFileUploaderDropzone"] *,
        [data-testid="stExpander"] details > div textarea,
        [data-testid="stExpander"] details > div textarea:focus,
        [data-testid="stExpander"] details > div textarea:hover,
        [data-testid="stExpander"] details > div input,
        [data-testid="stExpander"] details > div input:focus,
        [data-testid="stExpander"] details > div input:hover,
        [data-testid="stExpander"] details > div [data-testid="stTextArea"] textarea,
        [data-testid="stExpander"] details > div [data-testid="stTextInput"] input,
        [data-testid="stExpander"] details > div [data-testid="stNumberInput"] input,
        [data-testid="stExpander"] details > div [data-testid="stSelectbox"] div[data-baseweb="select"] *,
        [data-testid="stExpander"] details > div [data-testid="stFileUploader"] [data-baseweb="tag"] *,
        [data-testid="stExpander"] details > div section[data-testid="stFileUploaderDropzone"] * {
            color: #000000 !important;
            -webkit-text-fill-color: #000000 !important;
            caret-color: #000000 !important;
        }

        textarea::placeholder,
        input::placeholder,
        [data-testid="stTextArea"] textarea::placeholder,
        [data-testid="stTextInput"] input::placeholder {
            color: #4B4B4D !important;
            -webkit-text-fill-color: #4B4B4D !important;
            opacity: 1 !important;
        }

        textarea,
        [data-testid="stTextArea"] textarea,
        input,
        [data-testid="stTextInput"] input,
        [data-testid="stNumberInput"] input,
        [data-testid="stDateInput"] input,
        [data-testid="stTimeInput"] input,
        [data-testid="stSelectbox"] div[data-baseweb="select"],
        [data-testid="stMultiSelect"] div[data-baseweb="select"],
        section[data-testid="stFileUploaderDropzone"],
        pre,
        code,
        [data-testid="stCodeBlock"],
        [data-testid="stCodeBlock"] * {
            background-color: #F5F2EA !important;
            color: #000000 !important;
            -webkit-text-fill-color: #000000 !important;
        }

        [data-testid="stExpander"] details > div .stButton > button,
        [data-testid="stExpander"] details > div .stButton > button:hover,
        [data-testid="stExpander"] details > div .stButton > button:focus,
        [data-testid="stExpander"] details > div div[data-testid="stButton"] button,
        [data-testid="stExpander"] details > div div[data-testid="stButton"] button:hover,
        [data-testid="stExpander"] details > div div[data-testid="stButton"] button:focus,
        [data-testid="stExpander"] details > div .stDownloadButton > button,
        [data-testid="stExpander"] details > div .stDownloadButton > button:hover,
        [data-testid="stExpander"] details > div .stDownloadButton > button:focus,
        [data-testid="stExpander"] details > div div[data-testid="stDownloadButton"] button,
        [data-testid="stExpander"] details > div div[data-testid="stDownloadButton"] button:hover,
        [data-testid="stExpander"] details > div div[data-testid="stDownloadButton"] button:focus,
        [data-testid="stExpander"] details > div .stLinkButton > a,
        [data-testid="stExpander"] details > div .stLinkButton > a:hover,
        [data-testid="stExpander"] details > div .stLinkButton > a:focus,
        [data-testid="stExpander"] details > div a[data-testid="stLinkButton"] {
            background: #F5F2EA !important;
            color: #000000 !important;
            -webkit-text-fill-color: #000000 !important;
            border-color: rgba(212, 165, 76, 0.55) !important;
            filter: none !important;
            transform: none !important;
        }

        [data-testid="stExpander"] details > div .stButton > button *,
        [data-testid="stExpander"] details > div div[data-testid="stButton"] button *,
        [data-testid="stExpander"] details > div div[data-testid="stButton"] button p,
        [data-testid="stExpander"] details > div div[data-testid="stButton"] button span,
        [data-testid="stExpander"] details > div .stDownloadButton > button *,
        [data-testid="stExpander"] details > div div[data-testid="stDownloadButton"] button *,
        [data-testid="stExpander"] details > div .stLinkButton > a *,
        [data-testid="stExpander"] details > div a[data-testid="stLinkButton"] * {
            color: #000000 !important;
            -webkit-text-fill-color: #000000 !important;
            fill: #000000 !important;
            stroke: #000000 !important;
        }

        .stButton > button,
        div[data-testid="stButton"] button,
        .stLinkButton > a,
        .stDownloadButton > button,
        div[data-testid="stDownloadButton"] button,
        div[data-testid="stPopover"] button,
        div[data-testid="stFileUploader"] button,
        section[data-testid="stFileUploaderDropzone"] button {
            background: #F5F2EA !important;
            color: #000000 !important;
            -webkit-text-fill-color: #000000 !important;
            border: 1px solid rgba(212, 165, 76, 0.55) !important;
            box-shadow: none !important;
            text-shadow: none !important;
        }

        .stButton > button *,
        div[data-testid="stButton"] button *,
        div[data-testid="stButton"] button p,
        div[data-testid="stButton"] button span,
        .stLinkButton > a *,
        .stDownloadButton > button *,
        div[data-testid="stDownloadButton"] button *,
        div[data-testid="stPopover"] button *,
        div[data-testid="stFileUploader"] button *,
        section[data-testid="stFileUploaderDropzone"] button *,
        .stButton > button p,
        .stLinkButton > a p,
        .stDownloadButton > button p,
        div[data-testid="stPopover"] button p,
        div[data-testid="stFileUploader"] button p,
        section[data-testid="stFileUploaderDropzone"] button p,
        .stButton > button span,
        .stLinkButton > a span,
        .stDownloadButton > button span,
        div[data-testid="stPopover"] button span,
        div[data-testid="stFileUploader"] button span,
        section[data-testid="stFileUploaderDropzone"] button span {
            color: #000000 !important;
            -webkit-text-fill-color: #000000 !important;
            fill: #000000 !important;
            stroke: #000000 !important;
        }

        .stButton > button:hover,
        .stButton > button:focus,
        .stButton > button:active,
        div[data-testid="stButton"] button:hover,
        div[data-testid="stButton"] button:focus,
        div[data-testid="stButton"] button:active,
        .stLinkButton > a:hover,
        .stLinkButton > a:focus,
        .stLinkButton > a:active,
        .stDownloadButton > button:hover,
        .stDownloadButton > button:focus,
        .stDownloadButton > button:active,
        div[data-testid="stDownloadButton"] button:hover,
        div[data-testid="stDownloadButton"] button:focus,
        div[data-testid="stDownloadButton"] button:active,
        div[data-testid="stPopover"] button:hover,
        div[data-testid="stPopover"] button:focus,
        div[data-testid="stPopover"] button:active,
        div[data-testid="stPopover"] button[aria-expanded="true"],
        div[data-testid="stFileUploader"] button:hover,
        section[data-testid="stFileUploaderDropzone"] button:hover {
            background: #F5F2EA !important;
            border-color: rgba(212, 165, 76, 0.55) !important;
            color: #000000 !important;
            -webkit-text-fill-color: #000000 !important;
            box-shadow: none !important;
            filter: none !important;
            transform: none !important;
        }

        .stButton > button[kind="primary"],
        div[data-testid="stButton"] button[kind="primary"] {
            background: var(--sc-gold) !important;
            border-color: var(--sc-gold) !important;
            color: #000000 !important;
            font-weight: 700;
        }

        .stButton > button[kind="primary"] *,
        .stButton > button[kind="primary"] p,
        .stButton > button[kind="primary"] span,
        div[data-testid="stButton"] button[kind="primary"] *,
        div[data-testid="stButton"] button[kind="primary"] p,
        div[data-testid="stButton"] button[kind="primary"] span {
            color: #000000 !important;
            -webkit-text-fill-color: #000000 !important;
            fill: #000000 !important;
            stroke: #000000 !important;
        }

        .stButton > button:disabled,
        div[data-testid="stButton"] button:disabled,
        .stLinkButton > a[aria-disabled="true"],
        .stDownloadButton > button:disabled,
        div[data-testid="stDownloadButton"] button:disabled,
        div[data-testid="stFileUploader"] button:disabled,
        section[data-testid="stFileUploaderDropzone"] button:disabled {
            background: #2A2A2D !important;
            border-color: #444149 !important;
            color: #C2BBB0 !important;
            opacity: 1 !important;
        }

        .stButton > button:disabled *,
        div[data-testid="stButton"] button:disabled *,
        .stLinkButton > a[aria-disabled="true"] *,
        .stDownloadButton > button:disabled *,
        div[data-testid="stDownloadButton"] button:disabled *,
        div[data-testid="stFileUploader"] button:disabled *,
        section[data-testid="stFileUploaderDropzone"] button:disabled * {
            color: #C2BBB0 !important;
            fill: #C2BBB0 !important;
            stroke: #C2BBB0 !important;
        }

        .stButton > button[kind="primary"]:hover,
        div[data-testid="stButton"] button[kind="primary"]:hover {
            background: var(--sc-gold) !important;
            border-color: var(--sc-gold) !important;
            color: #000000 !important;
            filter: none;
            transform: none !important;
        }

        [data-testid="stFileUploader"] {
            background: rgba(20, 20, 22, 0.90);
            border: 1px solid var(--sc-border);
            border-radius: 16px;
            padding: 0.75rem 0.85rem 0.95rem;
        }

        [data-testid="stFileUploader"] label,
        [data-testid="stFileUploader"] [data-testid="stWidgetLabel"] * {
            color: #F5F2EA !important;
            fill: #F5F2EA !important;
            stroke: #F5F2EA !important;
        }

        [data-testid="stFileUploader"] .stTooltipIcon {
            display: none !important;
        }

        [data-testid="stFileUploader"] [data-testid="stTooltipHoverTarget"],
        [data-testid="stFileUploader"] [data-baseweb="tooltip"],
        [data-testid="stFileUploader"] [role="tooltip"],
        [data-testid="stFileUploader"] [aria-describedby],
        [data-testid="stFileUploader"] [title] {
            pointer-events: auto !important;
        }

        [data-testid="stFileUploader"] button {
            font-weight: 700 !important;
        }

        [data-testid="stFileUploader"] button[aria-label="Add files"] {
            display: none !important;
        }

        [data-testid="stFileUploader"] button:not([aria-label*="Delete"]):not([aria-label*="Remove"]),
        section[data-testid="stFileUploaderDropzone"] button:not([aria-label*="Delete"]):not([aria-label*="Remove"]) {
            background: #0B0B0D !important;
            border-color: #0B0B0D !important;
            color: #F5F2EA !important;
            -webkit-text-fill-color: #F5F2EA !important;
            border-radius: 999px !important;
        }

        [data-testid="stFileUploader"] button:not([aria-label*="Delete"]):not([aria-label*="Remove"]) *,
        [data-testid="stFileUploader"] button:not([aria-label*="Delete"]):not([aria-label*="Remove"]) svg,
        [data-testid="stFileUploader"] button:not([aria-label*="Delete"]):not([aria-label*="Remove"]) span,
        [data-testid="stFileUploader"] button:not([aria-label*="Delete"]):not([aria-label*="Remove"]) p,
        section[data-testid="stFileUploaderDropzone"] button:not([aria-label*="Delete"]):not([aria-label*="Remove"]) *,
        section[data-testid="stFileUploaderDropzone"] button:not([aria-label*="Delete"]):not([aria-label*="Remove"]) svg,
        section[data-testid="stFileUploaderDropzone"] button:not([aria-label*="Delete"]):not([aria-label*="Remove"]) span,
        section[data-testid="stFileUploaderDropzone"] button:not([aria-label*="Delete"]):not([aria-label*="Remove"]) p {
            color: #F5F2EA !important;
            -webkit-text-fill-color: #F5F2EA !important;
            fill: #F5F2EA !important;
            stroke: #F5F2EA !important;
        }

        [data-testid="stFileUploader"] button[aria-label]:not([aria-label*="Delete"]):not([aria-label*="Remove"]) {
            background: #0B0B0D !important;
            border-color: #0B0B0D !important;
            color: #F5F2EA !important;
            -webkit-text-fill-color: #F5F2EA !important;
            border-radius: 999px !important;
        }

        [data-testid="stFileUploader"] button[aria-label]:not([aria-label*="Delete"]):not([aria-label*="Remove"]) *,
        [data-testid="stFileUploader"] button[aria-label]:not([aria-label*="Delete"]):not([aria-label*="Remove"]) svg,
        [data-testid="stFileUploader"] button[aria-label]:not([aria-label*="Delete"]):not([aria-label*="Remove"]) span {
            color: #F5F2EA !important;
            -webkit-text-fill-color: #F5F2EA !important;
            fill: #F5F2EA !important;
            stroke: #F5F2EA !important;
        }

        [data-testid="stFileUploader"] [data-baseweb="tag"],
        [data-testid="stFileUploader"] [data-baseweb="tag"] *,
        [data-testid="stFileUploader"] [data-baseweb="tag"] span,
        [data-testid="stFileUploader"] [data-baseweb="tag"] div {
            color: #000000 !important;
            fill: #000000 !important;
            stroke: #000000 !important;
        }

        [data-testid="stFileUploader"] [data-baseweb="tag"] button,
        [data-testid="stFileUploader"] [data-baseweb="tag"] button:hover,
        [data-testid="stFileUploader"] [data-baseweb="tag"] button:focus,
        [data-testid="stFileUploader"] [data-baseweb="tag"] button:active,
        [data-testid="stFileUploader"] button[aria-label*="Delete"],
        [data-testid="stFileUploader"] button[aria-label*="Delete"]:hover,
        [data-testid="stFileUploader"] button[aria-label*="Delete"]:focus,
        [data-testid="stFileUploader"] button[aria-label*="Delete"]:active,
        [data-testid="stFileUploader"] button[aria-label*="Remove"],
        [data-testid="stFileUploader"] button[aria-label*="Remove"]:hover,
        [data-testid="stFileUploader"] button[aria-label*="Remove"]:focus,
        [data-testid="stFileUploader"] button[aria-label*="Remove"]:active,
        [data-testid="stFileUploaderFile"] button,
        [data-testid="stFileUploaderFile"] button:hover,
        [data-testid="stFileUploaderFile"] button:focus,
        [data-testid="stFileUploaderFile"] button:active {
            background: transparent !important;
            border: none !important;
            border-radius: 0 !important;
            box-shadow: none !important;
            width: auto !important;
            min-width: 0 !important;
            height: auto !important;
            min-height: 0 !important;
            padding: 0 !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            filter: none !important;
            transform: none !important;
        }

        [data-testid="stFileUploader"] [data-baseweb="tag"] button *,
        [data-testid="stFileUploader"] [data-baseweb="tag"] button svg,
        [data-testid="stFileUploader"] [data-baseweb="tag"] button span,
        [data-testid="stFileUploader"] button[aria-label*="Delete"] *,
        [data-testid="stFileUploader"] button[aria-label*="Delete"] svg,
        [data-testid="stFileUploader"] button[aria-label*="Delete"] span,
        [data-testid="stFileUploader"] button[aria-label*="Remove"] *,
        [data-testid="stFileUploader"] button[aria-label*="Remove"] svg,
        [data-testid="stFileUploader"] button[aria-label*="Remove"] span,
        [data-testid="stFileUploaderFile"] button *,
        [data-testid="stFileUploaderFile"] button svg,
        [data-testid="stFileUploaderFile"] button span {
            color: #000000 !important;
            fill: #000000 !important;
            stroke: #000000 !important;
        }

        [data-testid="stFileUploader"] [data-baseweb="tag"] button svg,
        [data-testid="stFileUploader"] [data-baseweb="tag"] button span,
        [data-testid="stFileUploader"] button[aria-label*="Delete"] svg,
        [data-testid="stFileUploader"] button[aria-label*="Delete"] span,
        [data-testid="stFileUploader"] button[aria-label*="Remove"] svg,
        [data-testid="stFileUploader"] button[aria-label*="Remove"] span,
        [data-testid="stFileUploaderFile"] button svg,
        [data-testid="stFileUploaderFile"] button span {
            display: none !important;
        }

        [data-testid="stFileUploader"] [data-baseweb="tag"] button::before,
        [data-testid="stFileUploader"] button[aria-label*="Delete"]::before,
        [data-testid="stFileUploader"] button[aria-label*="Remove"]::before,
        [data-testid="stFileUploaderFile"] button::before {
            content: "x";
            color: #000000 !important;
            font-size: 1rem !important;
            font-weight: 700 !important;
            line-height: 1 !important;
        }

        [data-testid="stFileUploader"] button[aria-label]:not([aria-label*="Delete"]):not([aria-label*="Remove"]):hover,
        [data-testid="stFileUploader"] button[aria-label]:not([aria-label*="Delete"]):not([aria-label*="Remove"]):focus,
        [data-testid="stFileUploader"] button[aria-label]:not([aria-label*="Delete"]):not([aria-label*="Remove"]):active {
            background: #0B0B0D !important;
            border-color: #0B0B0D !important;
            color: #F5F2EA !important;
            -webkit-text-fill-color: #F5F2EA !important;
            box-shadow: none !important;
            filter: none !important;
            transform: none !important;
        }

        section[data-testid="stFileUploaderDropzone"] [data-testid="stFileUploaderDropzoneInstructions"],
        section[data-testid="stFileUploaderDropzone"] [data-testid="stFileUploaderDropzoneInstructions"] *,
        section[data-testid="stFileUploaderDropzone"] [data-testid="stFileUploaderDropzoneInstructions"] span,
        section[data-testid="stFileUploaderDropzone"] [data-testid="stFileUploaderDropzoneInstructions"] p {
            color: #000000 !important;
            fill: #000000 !important;
            stroke: #000000 !important;
        }

        [data-testid="stTooltipContent"],
        .stTooltipContent,
        div[role="tooltip"] {
            display: none !important;
            visibility: hidden !important;
            pointer-events: none !important;
            opacity: 0 !important;
        }

        [data-testid="stTooltipContent"] *,
        .stTooltipContent *,
        div[role="tooltip"] * {
            color: #000000 !important;
            fill: #000000 !important;
            stroke: #000000 !important;
        }

        .sc-status {
            display: inline-block;
            border: 1px solid var(--sc-border);
            border-radius: 999px;
            padding: 0.22rem 0.62rem;
            background: #202024;
            color: var(--sc-text);
            font-size: 0.78rem;
            font-weight: 700;
            white-space: nowrap;
        }

        .sc-status-live,
        .sc-status-available,
        .sc-status-mockups-ready,
        .sc-status-connected,
        .sc-status-all-files-connected,
        .sc-status-core-files-ready,
        .sc-status-ready-for-upload,
        .sc-status-live-link-added,
        .sc-status-prodigi-connected {
            border-color: #527A63;
            color: #BFE3C9;
        }

        .sc-status-shopify-active {
            border-color: #527A63;
            color: #BFE3C9;
        }

        .sc-status-approved,
        .sc-status-asset-pack-approved,
        .sc-status-core-assets-connected {
            border-color: #527A63;
            color: #BFE3C9;
        }

        .sc-status-ready-for-review,
        .sc-status-needs-fixing,
        .sc-status-final-editions,
        .sc-status-sold-out,
        .sc-status-missing,
        .sc-status-missing-files,
        .sc-status-needs-files,
        .sc-status-needs-prodigi,
        .sc-status-needs-edition-setup,
        .sc-status-prodigi-missing {
            border-color: var(--sc-danger);
            color: #F0B4A1;
        }

        .sc-status-not-matched {
            border-color: var(--sc-danger);
            color: #F0B4A1;
        }

        .sc-status-needs-review,
        .sc-status-core-assets-missing,
        .sc-status-live-product-missing-files {
            border-color: var(--sc-danger);
            color: #F0B4A1;
        }

        .sc-status-selling-quickly,
        .sc-status-upload-in-progress,
        .sc-status-artwork-ready,
        .sc-status-admin-link-added {
            border-color: var(--sc-gold);
            color: #E9C980;
        }

        .sc-status-shopify-draft,
        .sc-status-id-not-synced {
            border-color: var(--sc-gold);
            color: #E9C980;
        }

        .sc-check {
            margin: 0.35rem 0;
            padding: 0.72rem 0.85rem;
            border: 1px solid var(--sc-border);
            border-radius: 10px;
            background: #171719;
        }

        .sc-check-ready strong {
            color: #8CC9A0;
        }

        .sc-check-missing strong {
            color: #E38A6E;
        }

        .sc-shell-card {
            background: rgba(20, 20, 22, 0.94);
            border: 1px solid var(--sc-border);
            border-radius: 18px;
            padding: 1rem 1.15rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def init_session_state():
    if "selected_page" not in st.session_state:
        st.session_state.selected_page = "Dashboard"

    if "startup_shell_loaded" not in st.session_state:
        st.session_state.selected_page = "Dashboard"
        st.session_state.startup_shell_loaded = True

    pending_page = st.session_state.pop("pending_page", None)
    if pending_page == "Settings":
        pending_page = "Developer"
    if pending_page in ALL_PAGE_OPTIONS:
        st.session_state.selected_page = pending_page

    if st.session_state.selected_page == "Settings":
        st.session_state.selected_page = "Developer"

    if st.session_state.selected_page not in ALL_PAGE_OPTIONS:
        st.session_state.selected_page = "Dashboard"

    if "selected_product_id" not in st.session_state:
        st.session_state.selected_product_id = None

    if "show_add_product" not in st.session_state:
        st.session_state.show_add_product = False

    if "product_name" not in st.session_state:
        st.session_state.product_name = ""

    if "last_uploaded_file_name" not in st.session_state:
        st.session_state.last_uploaded_file_name = None

    if "last_autofilled_product_name" not in st.session_state:
        st.session_state.last_autofilled_product_name = ""

    if "last_generation_result" not in st.session_state:
        st.session_state.last_generation_result = None

    if "uploaded_preview_signature" not in st.session_state:
        st.session_state.uploaded_preview_signature = None

    if "uploaded_preview_path" not in st.session_state:
        st.session_state.uploaded_preview_path = None


def log_app_memory(stage):
    try:
        import psutil

        process = psutil.Process(os.getpid())
        print(f"MEMORY MB {stage}: {process.memory_info().rss / 1024 / 1024:.1f}", flush=True)
    except Exception:
        safe_startup_print(f"MEMORY LOG SKIPPED {stage}")


def normalize_whitespace(value):
    return re.sub(r"\s+", " ", str(value or "").strip())


def normalize_sheet_header_name(value):
    normalized = re.sub(r"[^a-z0-9]+", "_", normalize_whitespace(value).lower())
    return normalized.strip("_")


def canonicalize_sheet_key(normalized_key):
    header_aliases = {
        "date_sent": {"date_sent", "sent_date", "date"},
        "shopify_order": {
            "shopify_order",
            "shopify_order_number",
            "shopify_order_no",
            "shopify_order_",
            "order_number",
            "order_no",
        },
        "customer_name": {"customer_name", "customer"},
        "edition_name": {"edition_name", "product_name", "product", "name"},
        "edition_no": {"edition_no", "edition_number", "edition"},
        "frame": {"frame"},
        "size": {"size"},
        "prodigi_product_option": {
            "prodigi_product_option",
            "prodigi_option",
            "prodigi_product",
        },
        "shipping": {"shipping", "shipping_method"},
        "status": {"status"},
        "notes": {"notes", "note"},
        "shopify_handle": {"shopify_handle", "handle"},
        "product_url": {"product_url", "shopify_product_url", "url"},
        "email": {"email", "customer_email"},
        "address": {"address", "shipping_address", "customer_address"},
        "phone": {"phone", "customer_phone", "phone_number"},
        "tracking_number": {"tracking_number", "tracking", "tracking_no"},
    }

    for canonical_key, aliases in header_aliases.items():
        if normalized_key in aliases:
            return canonical_key

    return normalized_key


def parse_sheet_date(value):
    text_value = normalize_whitespace(value)
    if not text_value:
        return None

    for date_format in (
        "%d/%m/%Y",
        "%d/%m/%y",
        "%d-%m-%Y",
        "%d-%m-%y",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d %b %Y",
        "%d %B %Y",
    ):
        try:
            return datetime.strptime(text_value, date_format)
        except ValueError:
            continue

    if re.fullmatch(r"\d+(\.\d+)?", text_value):
        try:
            excel_days = float(text_value)
            if excel_days > 30000:
                return datetime(1899, 12, 30) + timedelta(days=excel_days)
        except ValueError:
            pass

    return None


def format_sheet_date(value):
    parsed_date = parse_sheet_date(value)
    if parsed_date is not None:
        return parsed_date.strftime("%-d/%-m/%Y") if os.name != "nt" else parsed_date.strftime("%#d/%#m/%Y")

    return normalize_whitespace(value) or "-"


def normalize_lookup_name(value):
    return normalize_whitespace(value).casefold()


EDITION_LOG_INTERNAL_FIELD_LABELS = (
    ("shopify_order", "Shopify Order #"),
    ("customer_name", "Customer Name"),
    ("email", "Email"),
    ("address", "Address"),
    ("phone", "Phone"),
    ("tracking_number", "Tracking Number"),
)


def extract_drive_folder_id(folder_url):
    if not folder_url:
        return None

    match = re.search(r"/folders/([a-zA-Z0-9_-]+)", folder_url)
    if match:
        return match.group(1)

    return None


def build_shopify_product_url_from_handle(handle):
    clean_handle = normalize_whitespace(handle).strip("/")
    if not clean_handle:
        return None

    return f"{SHOPIFY_STORE_BASE_URL}/products/{clean_handle}"


def render_external_link(label, url, key):
    if not url:
        return

    if hasattr(st, "link_button"):
        st.link_button(label, url, key=key, use_container_width=False)
    else:
        st.markdown(f"[{label}]({url})")


def get_edition_log_json_url():
    return EDITION_LOG_JSON_URL


def get_edition_log_connection_status():
    return {
        "json_url_found": bool(get_edition_log_json_url()),
    }


class EditionLogEndpointError(RuntimeError):
    def __init__(self, user_message, diagnostics, debug_error=None):
        super().__init__(user_message)
        self.user_message = user_message
        self.diagnostics = diagnostics
        self.debug_error = debug_error


def build_edition_log_response_preview(text, max_chars=300):
    preview = (text or "")[:max_chars]
    return preview.replace("\r", " ").replace("\n", " ")


def response_looks_like_html(text):
    stripped_text = (text or "").lstrip().casefold()
    return (
        stripped_text.startswith("<!doctype")
        or stripped_text.startswith("<html")
        or "<body" in stripped_text
    )


def convert_to_public_apps_script_url(endpoint_url):
    match = re.match(
        r"^(https://script\.google\.com)/a/macros/[^/]+/s/([^/]+)/(exec|dev)(\?.*)?$",
        normalize_whitespace(endpoint_url),
        flags=re.IGNORECASE,
    )
    if not match:
        return None

    base_url, deployment_id, mode, query_string = match.groups()
    query_suffix = query_string or ""
    return f"{base_url}/macros/s/{deployment_id}/{mode}{query_suffix}"


def summarize_edition_log_payload(data):
    if isinstance(data, dict):
        rows = data.get("rows")
        if not isinstance(rows, list):
            raise ValueError(
                "Edition Log endpoint returned invalid JSON. Expected a rows list."
            )
        return rows, "rows"

    if isinstance(data, list):
        return data, "list"

    raise ValueError(
        "Edition Log endpoint returned invalid JSON. Expected a list of rows or an object with a rows list."
    )


def parse_google_sheet_url(sheet_url):
    parsed_url = urlparse(normalize_whitespace(sheet_url))
    path_match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", parsed_url.path)
    if not path_match:
        return None

    query = parse_qs(parsed_url.query)
    fragment_query = parse_qs(parsed_url.fragment)
    gid = None
    for source in (query, fragment_query):
        if source.get("gid"):
            gid = normalize_whitespace(source["gid"][0])
            break

    return {
        "sheet_id": path_match.group(1),
        "gid": gid,
    }


def build_google_sheet_csv_export_url(sheet_url):
    parsed_sheet = parse_google_sheet_url(sheet_url)
    if not parsed_sheet:
        return None

    if parsed_sheet.get("gid"):
        export_url = f"https://docs.google.com/spreadsheets/d/{parsed_sheet['sheet_id']}/export?format=csv&gid={parsed_sheet['gid']}"
        return export_url

    export_url = (
        f"https://docs.google.com/spreadsheets/d/{parsed_sheet['sheet_id']}"
        f"/gviz/tq?tqx=out:csv&sheet={EDITION_LOG_SHEET_NAME.replace(' ', '%20')}"
    )
    return export_url


def build_records_from_sheet_values(values, header_row_number=EDITION_LOG_HEADER_ROW):
    if not values or len(values) < header_row_number:
        return []

    header_index = header_row_number - 1
    header_row = values[header_index]
    if not any(normalize_whitespace(cell) for cell in header_row):
        return []

    header_definitions = []
    for column_index, header_value in enumerate(header_row):
        display_name = normalize_whitespace(header_value)
        if not display_name:
            continue

        header_definitions.append(
            (
                column_index,
                display_name,
                canonicalize_sheet_key(normalize_sheet_header_name(display_name)),
            )
        )

    if not header_definitions:
        return []

    records = []
    for row_index, row_values in enumerate(values[EDITION_LOG_DATA_START_ROW - 1 :], start=EDITION_LOG_DATA_START_ROW):
        if not any(normalize_whitespace(cell) for cell in row_values):
            continue

        record = {
            "_row_number": row_index,
            "_sheet_position": row_index,
            "_raw": {},
        }
        for column_index, display_name, canonical_key in header_definitions:
            cell_value = normalize_whitespace(row_values[column_index] if column_index < len(row_values) else "")
            record[canonical_key] = cell_value
            record["_raw"][display_name] = cell_value

        records.append(record)

    return records


def build_json_rows_from_sheet_values(values):
    records = build_records_from_sheet_values(values)
    json_rows = []
    for record in records:
        raw_row = record.get("_raw", {})
        if raw_row:
            json_rows.append(raw_row)
    return json_rows


def save_edition_log_snapshot_cache(rows, diagnostics):
    EDITION_LOG_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "saved_at": datetime.now().isoformat(),
        "rows": rows,
        "diagnostics": diagnostics,
    }
    EDITION_LOG_CACHE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_edition_log_snapshot_cache():
    if not EDITION_LOG_CACHE_PATH.exists():
        return None

    try:
        payload = json.loads(EDITION_LOG_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None

    rows = payload.get("rows")
    if not isinstance(rows, list):
        return None

    return payload


def request_google_sheet_csv_export(sheet_url):
    requests = get_requests_module()
    export_url = build_google_sheet_csv_export_url(sheet_url)
    diagnostics = {
        "requested_url": export_url,
        "final_url": None,
        "status_code": None,
        "content_type": None,
        "response_preview": "",
        "response_looks_like": "Unknown",
        "json_format": "sheet_csv",
        "data_source": "Google Sheet CSV fallback",
    }

    if not export_url:
        raise EditionLogEndpointError(
            "Could not build a Google Sheet export URL from GOOGLE_SHEET_URL.",
            diagnostics,
        )

    try:
        response = requests.get(
            export_url,
            headers=EDITION_LOG_REQUEST_HEADERS,
            timeout=10,
            allow_redirects=True,
        )
    except requests.RequestException as error:
        raise EditionLogEndpointError(
            f"Could not fetch the Google Sheet CSV fallback: {error}",
            diagnostics,
            debug_error=error,
        ) from error

    response_text = response.text or ""
    diagnostics["final_url"] = response.url
    diagnostics["status_code"] = response.status_code
    diagnostics["content_type"] = response.headers.get("content-type", "")
    diagnostics["response_preview"] = build_edition_log_response_preview(response_text)
    diagnostics["response_looks_like"] = "HTML" if response_looks_like_html(response_text) else "CSV-like"

    try:
        response.raise_for_status()
    except requests.HTTPError as error:
        raise EditionLogEndpointError(
            f"Google Sheet export URL returned HTTP {response.status_code}.",
            diagnostics,
            debug_error=error,
        ) from error

    if response_looks_like_html(response_text):
        raise EditionLogEndpointError(
            "The Google Sheet export fallback returned an HTML page instead of CSV.",
            diagnostics,
        )

    try:
        csv_rows = list(csv.reader(io.StringIO(response_text)))
    except Exception as error:
        raise EditionLogEndpointError(
            "Could not parse the Google Sheet CSV fallback response.",
            diagnostics,
            debug_error=error,
        ) from error

    json_rows = build_json_rows_from_sheet_values(csv_rows)
    if not json_rows:
        raise EditionLogEndpointError(
            "The Google Sheet CSV fallback did not return any usable edition rows.",
            diagnostics,
        )

    return json_rows, diagnostics


def request_edition_log_endpoint(request_url):
    requests = get_requests_module()
    diagnostics = {
        "requested_url": request_url,
        "final_url": None,
        "status_code": None,
        "content_type": None,
        "response_preview": "",
        "response_looks_like": "Unknown",
        "json_format": None,
    }

    try:
        response = requests.get(
            request_url,
            headers=EDITION_LOG_REQUEST_HEADERS,
            timeout=10,
            allow_redirects=True,
        )
    except requests.RequestException as error:
        raise EditionLogEndpointError(
            f"Could not fetch Edition Log JSON endpoint: {error}",
            diagnostics,
            debug_error=error,
        ) from error

    response_text = response.text or ""
    diagnostics["final_url"] = response.url
    diagnostics["status_code"] = response.status_code
    diagnostics["content_type"] = response.headers.get("content-type", "")
    diagnostics["response_preview"] = build_edition_log_response_preview(response_text)
    diagnostics["response_looks_like"] = "HTML" if response_looks_like_html(response_text) else "JSON-like"

    try:
        response.raise_for_status()
    except requests.HTTPError as error:
        raise EditionLogEndpointError(
            f"Edition Log URL returned HTTP {response.status_code}.",
            diagnostics,
            debug_error=error,
        ) from error

    if response_looks_like_html(response_text):
        raise EditionLogEndpointError(
            EDITION_LOG_HTML_WARNING,
            diagnostics,
        )

    try:
        data = response.json()
    except ValueError as error:
        if response_looks_like_html(response_text):
            raise EditionLogEndpointError(
                EDITION_LOG_HTML_WARNING,
                diagnostics,
                debug_error=error,
            ) from error

        raise EditionLogEndpointError(
            "Edition Log endpoint returned invalid JSON. Expected a list of rows or an object with a rows list.",
            diagnostics,
            debug_error=error,
        ) from error

    try:
        rows, json_format = summarize_edition_log_payload(data)
    except ValueError as error:
        raise EditionLogEndpointError(
            str(error),
            diagnostics,
            debug_error=error,
        ) from error

    diagnostics["json_format"] = json_format
    diagnostics["response_looks_like"] = "JSON"
    return rows, diagnostics


def fetch_edition_log_json_rows(endpoint_url):
    requested_url = normalize_whitespace(endpoint_url)
    overall_diagnostics = {
        "original_url_exists": bool(requested_url),
        "original_url": requested_url,
        "requested_url": requested_url,
        "final_url": None,
        "status_code": None,
        "content_type": None,
        "response_preview": "",
        "response_looks_like": "Unknown",
        "json_format": None,
        "retried_public_url_format": False,
        "attempted_urls": [],
        "data_source": "Apps Script JSON endpoint",
        "sheet_fallback_attempted": False,
        "sheet_fallback_used": False,
    }

    try:
        rows, diagnostics = request_edition_log_endpoint(requested_url)
        overall_diagnostics.update(diagnostics)
        overall_diagnostics["attempted_urls"].append(diagnostics["requested_url"])
        return rows, overall_diagnostics
    except EditionLogEndpointError as first_error:
        overall_diagnostics.update(first_error.diagnostics)
        overall_diagnostics["attempted_urls"].append(first_error.diagnostics["requested_url"])
        last_error = first_error

        public_url = convert_to_public_apps_script_url(requested_url)
        should_retry = (
            first_error.diagnostics.get("response_looks_like") == "HTML"
            and public_url
            and public_url != requested_url
        )
        if should_retry:
            overall_diagnostics["retried_public_url_format"] = True

            try:
                rows, retry_diagnostics = request_edition_log_endpoint(public_url)
                overall_diagnostics.update(retry_diagnostics)
                overall_diagnostics["attempted_urls"].append(retry_diagnostics["requested_url"])
                return rows, overall_diagnostics
            except EditionLogEndpointError as retry_error:
                overall_diagnostics.update(retry_error.diagnostics)
                overall_diagnostics["attempted_urls"].append(retry_error.diagnostics["requested_url"])
                last_error = retry_error

        if GOOGLE_SHEET_URL:
            overall_diagnostics["sheet_fallback_attempted"] = True
            try:
                rows, sheet_diagnostics = request_google_sheet_csv_export(GOOGLE_SHEET_URL)
                overall_diagnostics.update(sheet_diagnostics)
                overall_diagnostics["attempted_urls"].append(sheet_diagnostics["requested_url"])
                overall_diagnostics["sheet_fallback_used"] = True
                overall_diagnostics["data_source"] = "Google Sheet CSV fallback"
                return rows, overall_diagnostics
            except EditionLogEndpointError as sheet_error:
                overall_diagnostics["attempted_urls"].append(sheet_error.diagnostics.get("requested_url"))
                overall_diagnostics["sheet_fallback_error"] = sheet_error.user_message

            raise EditionLogEndpointError(
                last_error.user_message,
                overall_diagnostics,
                debug_error=last_error.debug_error,
            ) from last_error

        raise EditionLogEndpointError(
            last_error.user_message,
            overall_diagnostics,
            debug_error=last_error.debug_error,
        ) from last_error


def build_records_from_json_rows(json_rows):
    records = []
    had_date_parse_failure = False

    for index, row_data in enumerate(json_rows, start=1):
        if not isinstance(row_data, dict):
            continue

        normalized_pairs = []
        for key, value in row_data.items():
            display_name = normalize_whitespace(key)
            if not display_name:
                continue

            normalized_pairs.append(
                (
                    display_name,
                    canonicalize_sheet_key(normalize_sheet_header_name(display_name)),
                    normalize_whitespace(value),
                )
            )

        if not normalized_pairs:
            continue

        if not any(value for _, _, value in normalized_pairs):
            continue

        record = {
            "_row_number": index,
            "_sheet_position": index,
            "_raw": {},
        }

        for display_name, canonical_key, value in normalized_pairs:
            record[canonical_key] = value
            record["_raw"][display_name] = value

        record["_parsed_date"] = parse_sheet_date(record.get("date_sent"))
        if normalize_whitespace(record.get("date_sent")) and record["_parsed_date"] is None:
            had_date_parse_failure = True
        records.append(record)

    return records, had_date_parse_failure


def sort_edition_records(records, had_date_parse_failure=False):
    if had_date_parse_failure:
        return list(records)

    dated_records = [record for record in records if record.get("_parsed_date") is not None]
    if not dated_records:
        return list(records)

    return sorted(records, key=lambda record: record.get("_parsed_date") or datetime.min, reverse=True)


def resolve_product_link(record):
    product_url = normalize_whitespace(record.get("product_url"))
    if product_url:
        return product_url

    shopify_handle = normalize_whitespace(record.get("shopify_handle"))
    if shopify_handle:
        return build_shopify_product_url_from_handle(shopify_handle)

    return None


@st.cache_data(ttl=60, show_spinner=False)
def load_limited_editions_snapshot(json_url):
    if not json_url:
        raise ValueError("Edition Log is not connected yet. Add EDITION_LOG_JSON_URL in Render environment variables.")

    cache_payload = load_edition_log_snapshot_cache()
    try:
        json_rows, endpoint_diagnostics = fetch_edition_log_json_rows(json_url)
        save_edition_log_snapshot_cache(json_rows, endpoint_diagnostics)
        using_cached_snapshot = False
        cache_saved_at = None
        live_refresh_error = None
    except EditionLogEndpointError as error:
        if not cache_payload:
            raise

        json_rows = cache_payload["rows"]
        endpoint_diagnostics = cache_payload.get("diagnostics") or {}
        using_cached_snapshot = True
        cache_saved_at = cache_payload.get("saved_at")
        live_refresh_error = error.user_message
        endpoint_diagnostics = {
            **endpoint_diagnostics,
            "live_refresh_error": live_refresh_error,
            "using_cached_snapshot": True,
            "cache_saved_at": cache_saved_at,
        }

    edition_rows, had_date_parse_failure = build_records_from_json_rows(json_rows)
    sorted_rows = sort_edition_records(edition_rows, had_date_parse_failure=had_date_parse_failure)

    for row in sorted_rows:
        row["_product_link"] = resolve_product_link(row)

    return {
        "rows": sorted_rows,
        "had_date_parse_failure": had_date_parse_failure,
        "endpoint_diagnostics": endpoint_diagnostics,
        "using_cached_snapshot": using_cached_snapshot,
        "cache_saved_at": cache_saved_at,
        "live_refresh_error": live_refresh_error,
    }


def build_limited_editions_history(rows):
    history_by_product = {}

    for row in rows:
        product_name = normalize_whitespace(row.get("edition_name")) or "Untitled Product"
        history_entry = history_by_product.setdefault(
            product_name,
            {
                "edition_name": product_name,
                "edition_numbers": [],
                "latest_sent": format_sheet_date(row.get("date_sent")),
                "latest_date": row.get("_parsed_date"),
                "total_logged": 0,
                "product_link": row.get("_product_link"),
            },
        )

        edition_number = normalize_whitespace(row.get("edition_no"))
        if edition_number and edition_number not in history_entry["edition_numbers"]:
            history_entry["edition_numbers"].append(edition_number)

        history_entry["total_logged"] += 1
        if history_entry["product_link"] is None and row.get("_product_link"):
            history_entry["product_link"] = row.get("_product_link")

    history_rows = list(history_by_product.values())
    history_rows.sort(
        key=lambda item: (
            item["latest_date"] is not None,
            item["latest_date"] or datetime.min,
            item["edition_name"].casefold(),
        ),
        reverse=True,
    )
    return history_rows


def build_limited_editions_table_rows(rows, include_internal=False):
    dashboard_rows = []

    for row in rows:
        dashboard_row = {
            "Edition Name": normalize_whitespace(row.get("edition_name")) or "Untitled Product",
            "Edition No.": normalize_whitespace(row.get("edition_no")) or "-",
            "Frame": normalize_whitespace(row.get("frame")) or "-",
            "Size": normalize_whitespace(row.get("size")) or "-",
            "Date Sent": format_sheet_date(row.get("date_sent")),
            "Shipping": normalize_whitespace(row.get("shipping")) or "-",
            "Status": normalize_whitespace(row.get("status")) or "-",
            "Notes": normalize_whitespace(row.get("notes")) or "",
        }

        if include_internal:
            for field_key, field_label in EDITION_LOG_INTERNAL_FIELD_LABELS:
                field_value = normalize_whitespace(row.get(field_key))
                if field_value:
                    dashboard_row[field_label] = field_value

        dashboard_rows.append(dashboard_row)

    return dashboard_rows


def render_limited_editions_empty_state():
    st.warning(
        "Edition Log is not connected yet. Add EDITION_LOG_JSON_URL in Render environment variables."
    )
    render_limited_editions_setup_help(html_issue=False)


def render_limited_editions_setup_help(html_issue=False):
    if html_issue:
        st.info(
            "Apps Script is returning an HTML page, not JSON. Check the Apps Script deployment:\n"
            "\n"
            "1. Deploy as Web app\n"
            "2. Execute as: Me\n"
            "3. Who has access: Anyone with the link\n"
            "4. Copy the Web app URL, not the Deployment ID\n"
            "5. Test the URL in incognito. It must show raw JSON."
        )
    else:
        st.info(
            "Add EDITION_LOG_JSON_URL to Render, then open the URL in an incognito browser. "
            "If it does not show raw JSON, redeploy the Apps Script Web App before using this page."
        )
    with st.expander("Expected Apps Script JSON code"):
        st.code(EXPECTED_APPS_SCRIPT_JSON_CODE, language="javascript")


def render_limited_editions_diagnostics(diagnostics):
    if not diagnostics:
        return

    st.caption("Endpoint diagnostics")
    if diagnostics.get("data_source"):
        st.write(f"**Data source:** {diagnostics.get('data_source')}")
    st.write(f"**Original URL exists:** {'Yes' if diagnostics.get('original_url_exists') else 'No'}")
    st.write(f"**Requested URL:** {diagnostics.get('requested_url') or '-'}")
    st.write(f"**Final response URL:** {diagnostics.get('final_url') or '-'}")
    st.write(f"**HTTP status code:** {diagnostics.get('status_code') or '-'}")
    st.write(f"**Content-Type:** {diagnostics.get('content_type') or '-'}")
    st.write(f"**Response looks like:** {diagnostics.get('response_looks_like') or '-'}")
    if diagnostics.get("json_format"):
        st.write(f"**JSON format:** {diagnostics.get('json_format')}")
    if diagnostics.get("retried_public_url_format"):
        st.info("Retried using public Apps Script URL format.")
    if diagnostics.get("sheet_fallback_used"):
        st.success("Loaded live edition data using the Google Sheet export fallback.")
    if diagnostics.get("sheet_fallback_attempted") and diagnostics.get("sheet_fallback_error"):
        st.warning(diagnostics.get("sheet_fallback_error"))
    if diagnostics.get("using_cached_snapshot"):
        st.warning(
            "Showing the last successful edition snapshot because the live refresh failed."
        )
        if diagnostics.get("cache_saved_at"):
            st.caption(f"Cached snapshot saved at: {diagnostics.get('cache_saved_at')}")
    if diagnostics.get("live_refresh_error"):
        st.caption(f"Live refresh error: {diagnostics.get('live_refresh_error')}")
    attempted_urls = diagnostics.get("attempted_urls") or []
    if attempted_urls:
        st.write(f"**Attempted URLs:** {len(attempted_urls)}")
        for attempt_index, attempt_url in enumerate(attempted_urls, start=1):
            st.caption(f"{attempt_index}. {attempt_url}")
    with st.expander("Response preview", expanded=False):
        st.code(diagnostics.get("response_preview") or "-", language=None)


def render_limited_editions_load_error(error, diagnostics=None):
    st.error("Could not load Edition Log from the live JSON URL.")
    if isinstance(error, EditionLogEndpointError):
        st.warning(error.user_message)
    else:
        st.warning(str(error))
    render_limited_editions_diagnostics(diagnostics)
    render_limited_editions_setup_help(
        html_issue=bool(diagnostics and diagnostics.get("response_looks_like") == "HTML")
    )
    with st.expander("Debug details"):
        if diagnostics:
            st.json(diagnostics)
        st.code("".join(traceback.format_exception(type(error), error, error.__traceback__)))
    if GOOGLE_SHEET_URL:
        render_external_link("Open Edition Log Sheet", GOOGLE_SHEET_URL, "open-edition-log-sheet-error")


def test_edition_log_url(json_url):
    try:
        rows, diagnostics = fetch_edition_log_json_rows(json_url)
        return {
            "ok": True,
            "message": f"Edition Log URL returned JSON successfully. Rows found: {len(rows)}.",
            "diagnostics": diagnostics,
            "debug_details": None,
        }
    except EditionLogEndpointError as error:
        return {
            "ok": False,
            "message": error.user_message,
            "diagnostics": error.diagnostics,
            "debug_details": "".join(
                traceback.format_exception(type(error), error, error.__traceback__)
            ),
        }
    except Exception as error:
        return {
            "ok": False,
            "message": str(error),
            "diagnostics": None,
            "debug_details": "".join(
                traceback.format_exception(type(error), error, error.__traceback__)
            ),
        }


def render_edition_log_test_result(test_result):
    if not test_result:
        return

    st.subheader("Edition Log URL Test")
    if test_result.get("ok"):
        st.success(test_result.get("message") or "Edition Log URL test succeeded.")
    else:
        st.warning(test_result.get("message") or "Edition Log URL test failed.")

    render_limited_editions_diagnostics(test_result.get("diagnostics"))
    if test_result.get("debug_details"):
        with st.expander("Debug details"):
            st.code(test_result["debug_details"])


@lru_cache(maxsize=1)
def import_drive_storage_module():
    return importlib.import_module("drive_storage")


def save_zip_to_drive_folder(zip_path):
    folder_id = extract_drive_folder_id(ZIP_SAVE_DRIVE_FOLDER_URL)
    if not folder_id:
        raise RuntimeError("ZIP save folder URL is missing or invalid.")

    drive_storage = import_drive_storage_module()
    if not drive_storage.is_drive_configured():
        raise RuntimeError(
            "Google Drive save is not connected yet. Add the Google Drive OAuth environment variables to enable Save ZIP."
        )

    return drive_storage.upload_file_to_drive(zip_path, folder_id, mime_type="application/zip")


@lru_cache(maxsize=1)
def get_drive_storage_module():
    if not ENABLE_GOOGLE_DRIVE:
        raise RuntimeError("Google Drive is disabled in lightweight mode.")

    return import_drive_storage_module()


def get_uploaded_file_signature(uploaded_file):
    if uploaded_file is None:
        return None

    name = getattr(uploaded_file, "name", "")
    size = getattr(uploaded_file, "size", 0)
    return hashlib.sha1(f"{name}|{size}".encode("utf-8")).hexdigest()[:16]


def create_uploaded_preview(uploaded_file):
    Image, ImageOps, _ = get_pillow_modules()
    preview_signature = get_uploaded_file_signature(uploaded_file)
    if preview_signature is None:
        return None

    UPLOAD_PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    preview_path = UPLOAD_PREVIEW_DIR / f"{preview_signature}.webp"
    if preview_path.exists():
        return preview_path

    source_image = None
    preview_image = None

    try:
        log_app_memory("Before upload preview creation")
        uploaded_file.seek(0)
        source_image = Image.open(uploaded_file)
        if (source_image.format or "").upper() in {"JPEG", "JPG"}:
            source_image.draft("RGB", (image_factory.MAX_PREVIEW_EDGE, image_factory.MAX_PREVIEW_EDGE))
        preview_image = ImageOps.exif_transpose(source_image)
        preview_image.thumbnail((image_factory.MAX_PREVIEW_EDGE, image_factory.MAX_PREVIEW_EDGE), Image.LANCZOS)
        if preview_image.mode != "RGB":
            preview_image = preview_image.convert("RGB")
        preview_image.save(
            preview_path,
            format="WEBP",
            quality=image_factory.PREVIEW_WEBP_QUALITY,
            method=image_factory.PREVIEW_WEBP_METHOD,
        )
        log_app_memory("After upload preview creation")
        return preview_path
    finally:
        uploaded_file.seek(0)
        if preview_image is not None:
            with suppress(Exception):
                preview_image.close()
        if source_image is not None:
            with suppress(Exception):
                source_image.close()
        del preview_image, source_image
        gc.collect()


def get_local_recent_runs(limit=5):
    if not RUNS_DIR.exists():
        return []

    return sorted(
        [path for path in RUNS_DIR.iterdir() if path.is_dir()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )[:limit]


def get_recent_runs(limit=5):
    if ENABLE_GOOGLE_DRIVE:
        try:
            drive_storage = get_drive_storage_module()
            recent_drive_runs = drive_storage.list_recent_drive_runs(limit=limit)
            if recent_drive_runs:
                return recent_drive_runs
        except Exception:
            pass

    return [
        {"name": path.name, "source": "local", "path": path}
        for path in get_local_recent_runs(limit=limit)
    ]


def get_product_name_from_upload(uploaded_file):
    if uploaded_file is None:
        return ""

    return Path(uploaded_file.name).stem.strip()


def load_run_metadata(run_dir):
    run_dir = Path(run_dir)
    manifest_path = run_dir / "manifest.json"
    metadata = {}

    if manifest_path.exists():
        try:
            metadata = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            metadata = {}

    metadata["run_dir"] = str(run_dir)
    metadata["run_name"] = run_dir.name
    metadata["product_name"] = metadata.get("product_name", run_dir.name)
    metadata["sport_category"] = metadata.get("sport_category", "")
    metadata["product_slug"] = metadata.get("product_slug", run_dir.name)
    metadata["shopify_uploads_dir"] = str(run_dir / "shopify-uploads")
    metadata["shopify_uploads_html_path"] = str(run_dir / "shopify-uploads" / "index.html")
    metadata["prompt_dir"] = str(run_dir / "chatgpt-prompts")
    return metadata


def get_product_upload_prompt(metadata, update_existing=False):
    base_prompt = UPDATE_EXISTING_PRODUCT_PROMPT if update_existing else NEW_SHOPIFY_PRODUCT_PROMPT
    return build_product_upload_prompt(base_prompt)


PRODUCT_UPLOAD_ALT_TEXT_PROMPT = """Create unique commercial SEO image alt text for every Sports Cave Shopify product image supplied.

Inputs:
- Product title/H1
- Athlete, team, vehicle, rivalry, event, or sporting moment
- Sport/category
- Primary commercial keyword
- Ordered image filenames and roles
- Visible room/setting for each lifestyle mockup

Required output:
A table in the exact gallery order:
Position | File/image role | Alt text | Character count

Canonical gallery order:
1. Black frame
2. Lifestyle mockup 1
3. Lifestyle mockup 2
4. Lifestyle mockup 3
5. Size guide
6. Oak frame
7. White frame
8. Unframed

Rules:
- Accurately describe what is visible.
- Usually 80–140 characters; clarity is more important than forcing length.
- Use the primary keyword naturally no more than once per alt text.
- Mention the verified athlete/moment/sport and visible setting when relevant.
- Mention frame colour for Black, Oak, and White product images.
- Identify the size guide clearly.
- Make every line genuinely unique.
- Write for accessibility first and SEO second.
- Do not use hashtags, emoji, sales hype, scarcity language, or keyword stuffing.
- Do not begin with image of unless it is genuinely natural.
- Do not invent a person, team, logo, trophy, signature, event, achievement, room detail, or product specification.
- Do not overdescribe irrelevant furniture.
"""


PRODUCT_UPLOAD_META_PROMPT = """Write commercial Shopify SEO metadata for one Sports Cave product.

Inputs:
- Product title
- Athlete/team/moment/event
- Sport/category
- Product context
- Confirmed edition limit, if any
- Target market
- Primary and secondary keyword candidates

SEO principle:
Search intent first, premium tone second. Clearly tell Google and buyers who/what the page features, what the product is, the sport/category, and the collector or room intent.

Output:
1. Primary keyword
2. Up to 4 secondary keywords
3. SEO title with character count
4. Meta description with character count
5. URL handle
6. H1/product title recommendation
7. Open Graph title
8. Open Graph description
9. Three natural internal-link anchor text ideas

Rules for SEO title:
- 50–60 characters preferred; 60 maximum.
- Put the primary keyword near the start.
- Include the subject and Wall Art.
- Add Limited Edition, Framed Print, sport, or Sports Cave only when it fits naturally.
- Never use a poetic campaign title by itself.
- No keyword stuffing.

Rules for meta description:
- 145–160 characters preferred.
- Mention the subject or moment and primary keyword naturally once.
- Mention collector/limited-edition intent only when confirmed.
- Add a relevant use such as collectors, man caves, offices, bars, or homes when space permits.
- Commercial and human, not robotic.
- No hashtags, emoji, fake urgency, keyword lists, store URL, or elevate your space.

Rules for handle:
- Lowercase letters and hyphens only.
- Include the principal subject and wall-art intent.
- Remove filler words and repeated keywords.

Do not invent dates, achievements, edition limits, licensing, signatures, materials, or product specifications.
"""


PRODUCT_UPLOAD_QA_CHECKLIST_PROMPT = """Review this Sports Cave Shopify product draft before publishing.

Return a Pass / Needs Fix table with the exact evidence and exact correction for each item.

PRODUCT IDENTITY AND STATUS
- Correct product title/H1 and clean handle
- Vendor: Sports Cave
- Product type: Framed Art
- Status: Draft for a new product
- Published: false for a new product
- Exact category: Prints in Posters, Prints, & Visual Artwork

DESCRIPTION
- 90–130 words
- Exactly one bold hook
- Exactly two concise story paragraphs
- Exactly one bold scarcity close
- Specific and grounded rather than ad-like or overstated
- No generic clichés
- No invented specifications or unconfirmed edition claims
- Clean Shopify-safe HTML

SEO
- Primary keyword is commercially relevant
- SEO title is 60 characters or fewer and search-intent led
- Meta description is 145–160 characters where practical
- Metadata is clear rather than poetic-first
- No keyword stuffing
- Every image has unique, accurate alt text
- Alt text describes the real image and uses a target keyword naturally at most once

MEDIA ORDER
Verify the exact sequence:
1. Black frame
2. Lifestyle 1
3. Lifestyle 2
4. Lifestyle 3
5. Size guide
6. Oak frame
7. White frame
8. Unframed

VARIANTS
- Option 1 Frame: Black, Oak, White, Unframed
- Option 2 Size: XL, L, M, S with exact dimensions
- All 16 variants exist in correct order
- Black variants show black-frame image
- Oak variants show oak-frame image
- White variants show white-frame image
- Unframed variants show unframed image

PRICING — AUD
Framed Black/Oak/White:
- XL 349.00 / RRP 428.00
- L 269.00 / RRP 324.00
- M 209.00 / RRP 259.00
- S 159.00 / RRP 194.00
Unframed:
- XL 159.00 / RRP 194.00
- L 119.00 / RRP 142.00
- M 89.00 / RRP 103.00
- S 55.00 / RRP 64.00
Verify Price and Compare-at/RRP are not reversed.

INVENTORY AND FULFILMENT
- Continue selling when out of stock is enabled for all 16 variants
- Inventory policy is continue
- Requires shipping is true
- Taxable is true
- SKUs are unique

FINAL
- Tags and collections are relevant and not based on unproven performance claims
- No unsupported taxonomy metafields were invented
- Mobile preview is strong
- Desktop preview is strong
- Product remains unpublished until manually approved
"""

def product_upload_embedded_sections():
    return f"""ADDITIONAL REQUIRED SUB-PROMPTS
Use these sections inside the product creation/update workflow. Do not run them as separate prompts unless the user explicitly asks.

IMAGE ALT TEXT SUB-PROMPT
{PRODUCT_UPLOAD_ALT_TEXT_PROMPT.strip()}

SEO META TAGS SUB-PROMPT
{PRODUCT_UPLOAD_META_PROMPT.strip()}

FINAL QA CHECKLIST SUB-PROMPT
{PRODUCT_UPLOAD_QA_CHECKLIST_PROMPT.strip()}
""".strip()


def build_product_upload_prompt(base_prompt):
    return f"{str(base_prompt or '').strip()}\n\n{product_upload_embedded_sections()}".strip()


def validate_uploaded_artwork(uploaded_file):
    Image, _, UnidentifiedImageError = get_pillow_modules()
    if uploaded_file is None:
        raise ValueError("Please upload an artwork image first.")

    file_size = getattr(uploaded_file, "size", None)
    if file_size is not None and file_size <= 0:
        raise ValueError("Uploaded file is empty.")
    if file_size is not None and file_size > image_factory.MAX_UPLOAD_SIZE_BYTES:
        raise ValueError(
            "Uploaded image is too large for the current Render instance. "
            "Please upload a JPG or WebP under 20MB."
        )

    filename = getattr(uploaded_file, "name", "")
    suffix = Path(filename).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise ValueError("Unsupported file type. Upload JPG, JPEG, PNG, or WEBP.")

    try:
        image_factory.log_memory("Before upload validation")
        uploaded_file.seek(0)
        with Image.open(uploaded_file) as image:
            width, height = image.size
            image.verify()
        image_factory.log_memory("After upload validation")
    except UnidentifiedImageError as error:
        raise ValueError(
            "Uploaded file is not a valid image. Please upload a valid JPG, PNG, or WEBP file."
        ) from error
    except Exception as error:
        raise RuntimeError("Unable to validate uploaded artwork file.") from error
    finally:
        uploaded_file.seek(0)

    return {
        "file_size": file_size,
        "width": width,
        "height": height,
    }


def should_defer_uploaded_preview(upload_details):
    if not upload_details:
        return False

    file_size = upload_details.get("file_size") or 0
    width = upload_details.get("width") or 0
    height = upload_details.get("height") or 0
    pixel_count = width * height

    return (
        file_size >= UPLOAD_PREVIEW_MAX_FILE_SIZE_BYTES
        or max(width, height) >= UPLOAD_PREVIEW_MAX_SOURCE_EDGE
        or pixel_count >= image_factory.MAX_SOURCE_PIXELS
    )


def get_sport_category(selected_option, custom_value):
    if selected_option == "Custom":
        return custom_value.strip()

    return selected_option.strip()


def normalize_asset(asset):
    defaults = {
        "key": None,
        "label": "Image",
        "review_path": None,
        "preview_path": None,
        "webp_path": None,
        "jpg_path": None,
        "include_in_zip": True,
        "asset_group": "generated",
        "prompt_filename": None,
        "export_to_shopify": True,
        "export_to_socials": True,
    }
    normalized = defaults.copy()
    normalized.update(asset or {})
    return normalized


def ensure_result_assets(result):
    assets = [normalize_asset(asset) for asset in result.get("assets", [])]
    if assets:
        result["assets"] = assets
        return result

    review_paths = result.get("review_paths", [])
    webp_paths = result.get("webp_paths", [])
    jpg_paths = result.get("jpg_paths", [])
    legacy_assets = []

    for index, (asset_key, asset_label) in enumerate(LEGACY_BASE_ASSET_SPECS):
        if index >= len(review_paths) and index >= len(webp_paths) and index >= len(jpg_paths):
            continue

        review_path = review_paths[index] if index < len(review_paths) else None
        webp_path = webp_paths[index] if index < len(webp_paths) else None
        jpg_path = jpg_paths[index] if index < len(jpg_paths) else None
        legacy_assets.append(
            normalize_asset(
                image_factory.build_asset_record(
                    key=asset_key,
                    label=asset_label,
                    review_path=review_path,
                    webp_path=webp_path,
                    jpg_path=jpg_path,
                )
            )
        )

    result["assets"] = legacy_assets
    return result


def normalize_generation_result(result):
    defaults = {
        "product_name": None,
        "sport_category": None,
        "created_at": None,
        "product_slug": None,
        "sport_slug": None,
        "run_dir": None,
        "review_dir": None,
        "preview_dir": None,
        "webp_dir": None,
        "jpg_dir": None,
        "zip_dir": None,
        "zip_path": None,
        "social_zip_path": None,
        "prompt_zip_path": None,
        "complete_zip_path": None,
        "black_framed_webp_path": None,
        "black_framed_jpg_path": None,
        "prompt_dir": None,
        "prompt_paths": [],
        "review_paths": [],
        "webp_paths": [],
        "jpg_paths": [],
        "shopify_uploads_dir": None,
        "socials_dir": None,
        "shopify_uploads_html_path": None,
        "assets": [],
        "lifestyle_mockup_paths": {},
        "lifestyle_pack_error": None,
        "manifest_path": None,
        "uploaded_files": [],
        "drive_root_id": None,
        "drive_root_url": None,
        "drive_run_id": None,
        "drive_run_url": None,
        "drive_sync_enabled": False,
        "drive_sync_error": None,
        "drive_sync_message": None,
        "zip_drive_file_link": None,
        "zip_drive_folder_url": ZIP_SAVE_DRIVE_FOLDER_URL or None,
        "zip_drive_message": None,
        "zip_drive_error": None,
        "status_text": None,
    }
    normalized = defaults.copy()
    normalized.update(result or {})
    normalized = ensure_result_assets(normalized)
    return normalized


def get_asset_checkbox_key(run_dir, asset_key):
    return f"include-asset::{run_dir}::{asset_key}"


def get_lifestyle_asset_key(prompt_filename):
    return f"lifestyle::{prompt_filename}"


def get_prompt_label(prompt_path):
    prompt_name = Path(prompt_path).name
    return PROMPT_LABELS.get(prompt_name, prompt_name)


def is_product_page_prompt(prompt_path):
    return Path(prompt_path).name in PRODUCT_PAGE_PROMPT_NAMES


def prompt_edit_id(namespace, key):
    return f"{namespace}::{key}"


def current_prompt_text(prompt_id, default_text):
    return prompt_store.get_prompt(prompt_id, default_text)


def render_prompt_edit_button(prompt_id, *, label="✎"):
    button_key = f"prompt-edit-button::{prompt_id}"
    panel_key = f"prompt-edit-open::{prompt_id}"
    if st.button(label, key=button_key, help="Developer password required.", use_container_width=True):
        st.session_state[panel_key] = True


def render_prompt_edit_panel(title, prompt_id, prompt_text, *, height=420):
    panel_key = f"prompt-edit-open::{prompt_id}"
    if not st.session_state.get(panel_key):
        return

    with st.container(border=True):
        st.caption("Developer only. Saved changes replace this prompt everywhere it is used.")
        edited_text = st.text_area(
            "Prompt text",
            value=prompt_text,
            height=height,
            key=f"prompt-edit-text::{prompt_id}",
        )
        password = st.text_input(
            "Developer password",
            type="password",
            key=f"prompt-edit-password::{prompt_id}",
        )
        cols = st.columns([1, 1, 3])
        if cols[0].button("Save prompt", key=f"prompt-edit-save::{prompt_id}", use_container_width=True):
            if password != DEVELOPER_PAGE_PASSWORD:
                st.error("Developer password is incorrect.")
            else:
                prompt_store.save_prompt(prompt_id, title, edited_text)
                st.session_state[panel_key] = False
                st.success("Prompt saved to backend.")
                st.rerun()
        if cols[1].button("Cancel", key=f"prompt-edit-cancel::{prompt_id}", use_container_width=True):
            st.session_state[panel_key] = False
            st.rerun()


def render_prompt_edit_controls(title, prompt_id, prompt_text, *, height=420, label="✎"):
    render_prompt_edit_button(prompt_id, label=label)
    render_prompt_edit_panel(title, prompt_id, prompt_text, height=height)


def render_download_button(label, file_path, mime, key):
    if not file_path:
        return

    file_path = Path(file_path)
    if not file_path.exists():
        return

    with file_path.open("rb") as file_handle:
        st.download_button(
            label=label,
            data=file_handle,
            file_name=file_path.name,
            mime=mime,
            key=key,
            use_container_width=True,
        )


def render_copy_prompt_button(
    prompt_text,
    key,
    label="Copy Prompt",
    background="#FFFFFF",
    text_color="#0B0B0D",
    border_color="rgba(11,11,13,0.55)",
):
    prompt_text_json = json.dumps(prompt_text)
    safe_label = html.escape(label)
    button_id = f"copy-inline-button-{hashlib.sha1(str(key).encode('utf-8')).hexdigest()[:12]}"

    get_components_module().html(
        f"""
        <style>
        #{button_id},
        #{button_id}:hover,
        #{button_id}:focus,
        #{button_id}:active {{
            background:{background}!important;
            color:{text_color}!important;
            border-color:{border_color}!important;
            box-shadow:none!important;
            filter:none!important;
            transform:none!important;
        }}
        </style>
        <div style="padding-top:2px;">
          <button
            id="{button_id}"
            type="button"
            style="width:100%;border:1px solid {border_color};border-radius:14px;padding:12px 14px;background:{background};color:{text_color};font-weight:700;font-size:0.95rem;cursor:pointer;box-sizing:border-box;"
          >
            {safe_label}
          </button>
        </div>
        <script>
        (() => {{
          const button = document.getElementById("{button_id}");
          const originalLabel = button.innerText;
          const promptText = {prompt_text_json};

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
            }} catch (error) {{
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

            const toast = document.createElement("div");
            toast.innerText = "Prompt copied";
            toast.style.position = "fixed";
            toast.style.bottom = "22px";
            toast.style.right = "22px";
            toast.style.zIndex = "999999";
            toast.style.background = "#F5F2EA";
            toast.style.color = "#0B0B0D";
            toast.style.border = "1px solid rgba(212,165,76,0.85)";
            toast.style.borderRadius = "999px";
            toast.style.padding = "10px 14px";
            toast.style.fontWeight = "700";
            toast.style.boxShadow = "0 12px 32px rgba(0,0,0,0.32)";
            document.body.appendChild(toast);
            button.innerText = "Prompt copied";
            setTimeout(() => {{
              if (toast.parentNode) {{
                toast.parentNode.removeChild(toast);
              }}
              button.innerText = originalLabel;
            }}, 1400);
          }}

          button.addEventListener("click", copyPrompt);
        }})();
        </script>
        """,
        height=62,
    )


def render_copyable_prompt(title, prompt_text, key, show_title=True, prompt_id=None):
    prompt_id = prompt_id or prompt_edit_id("app", key)
    prompt_text = current_prompt_text(prompt_id, prompt_text).strip()

    textarea_height = min(780, max(320, (prompt_text.count("\n") + 1) * 18 + 80))
    safe_text = html.escape(prompt_text)

    with st.container(border=True):
        if show_title:
            header_cols = st.columns([6, 1.2, 0.35])
            header_cols[0].markdown(f"**{title}**")
            with header_cols[1]:
                render_copy_prompt_button(prompt_text, f"copy::{key}")
            with header_cols[2]:
                render_prompt_edit_button(prompt_id)
        else:
            header_cols = st.columns([1.2, 0.35, 6])
            with header_cols[0]:
                render_copy_prompt_button(prompt_text, f"copy::{key}")
            with header_cols[1]:
                render_prompt_edit_button(prompt_id)

        render_prompt_edit_panel(title, prompt_id, prompt_text)

        get_components_module().html(
            f"""
            <textarea
              id="prompt-text-{key}"
              readonly
              style="width:100%;height:{textarea_height}px;border:1px solid rgba(11,11,13,0.18);border-radius:12px;padding:12px;background:#FFFFFF;color:#000000;font-size:0.95rem;line-height:1.45;resize:none;box-sizing:border-box;"
            >{safe_text}</textarea>
            """,
            height=textarea_height + 18,
        )


def _mockup_prompt_edit_key(prompt_id):
    return f"mockup-prompt-edit::{prompt_id}"


def _clear_mockup_prompt_edit_query():
    try:
        if "mockup_prompt_edit" in st.query_params:
            del st.query_params["mockup_prompt_edit"]
    except Exception:
        pass


def _consume_mockup_prompt_edit_request(prompt_id):
    try:
        requested_prompt_id = st.query_params.get("mockup_prompt_edit", "")
    except Exception:
        requested_prompt_id = ""
    if isinstance(requested_prompt_id, list):
        requested_prompt_id = requested_prompt_id[0] if requested_prompt_id else ""
    if requested_prompt_id != prompt_id:
        return
    st.session_state[_mockup_prompt_edit_key(prompt_id)] = True
    _clear_mockup_prompt_edit_query()
    st.rerun()


def _close_mockup_prompt_editor(prompt_id):
    st.session_state[_mockup_prompt_edit_key(prompt_id)] = False
    _clear_mockup_prompt_edit_query()


def render_mockup_prompt_editor(title, prompt_id, prompt_text):
    _consume_mockup_prompt_edit_request(prompt_id)
    edit_key = _mockup_prompt_edit_key(prompt_id)
    if not st.session_state.get(edit_key):
        return

    @st.dialog(f"Edit prompt: {title}", width="large")
    def _edit_prompt_dialog():
        st.caption("Developer only. Saved changes replace this prompt everywhere it is used.")
        edited_text = st.text_area(
            "Prompt text",
            value=prompt_text,
            height=520,
            key=f"mockup-prompt-edit-text::{prompt_id}",
        )
        password = st.text_input(
            "Developer password",
            type="password",
            key=f"mockup-prompt-edit-password::{prompt_id}",
        )
        cols = st.columns([1, 1, 3])
        if cols[0].button("Save", key=f"mockup-prompt-edit-save::{prompt_id}", type="primary", use_container_width=True):
            if password != DEVELOPER_PAGE_PASSWORD:
                st.error("Developer password is incorrect.")
            else:
                prompt_store.save_prompt(prompt_id, title, edited_text)
                _close_mockup_prompt_editor(prompt_id)
                st.session_state["mockup_prompt_notice"] = "Prompt saved"
                st.rerun()
        if cols[1].button("Cancel", key=f"mockup-prompt-edit-cancel::{prompt_id}", use_container_width=True):
            _close_mockup_prompt_editor(prompt_id)
            st.rerun()

    _edit_prompt_dialog()


def render_mockup_prompt_bar(prompt_text, key, prompt_id):
    prompt_text_json = json.dumps(prompt_text)
    prompt_id_json = json.dumps(prompt_id)
    bar_id = f"mockup-prompt-bar-{hashlib.sha1(str(key).encode('utf-8')).hexdigest()[:12]}"
    show_edit = True
    edit_markup = (
        f"""
        <a
          id="{bar_id}-edit"
          class="mockup-prompt-edit"
          href="#"
          target="_parent"
          title="Edit prompt"
          aria-label="Edit prompt"
        >&#9998;</a>
        """
        if show_edit
        else ""
    )

    get_components_module().html(
        f"""
        <style>
        #{bar_id} {{
            position: relative;
            width: 100%;
            height: 46px;
            border: 1px solid rgba(212, 165, 76, 0.55);
            border-radius: 14px;
            background: #F5F2EA;
            color: #0B0B0D;
            box-sizing: border-box;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 0 44px 0 16px;
            font-weight: 800;
            font-size: 0.95rem;
            line-height: 1;
            white-space: nowrap;
            overflow: hidden;
            user-select: none;
            box-shadow: none;
            filter: none;
            transform: none;
        }}
        #{bar_id}:hover,
        #{bar_id}:focus,
        #{bar_id}:active {{
            background: #F5F2EA;
            color: #0B0B0D;
            border-color: rgba(212, 165, 76, 0.55);
            box-shadow: none;
            filter: none;
            transform: none;
            outline: none;
        }}
        #{bar_id} .mockup-prompt-label {{
            color: #0B0B0D;
            white-space: nowrap;
            pointer-events: none;
        }}
        #{bar_id} .mockup-prompt-edit {{
            position: absolute;
            top: 5px;
            right: 6px;
            width: 28px;
            height: 28px;
            border-radius: 999px;
            color: #0B0B0D;
            background: transparent;
            border: 1px solid transparent;
            display: flex;
            align-items: center;
            justify-content: center;
            text-decoration: none;
            font-size: 0.9rem;
            font-weight: 900;
            line-height: 1;
        }}
        #{bar_id} .mockup-prompt-edit:hover,
        #{bar_id} .mockup-prompt-edit:focus {{
            color: #0B0B0D;
            background: rgba(212, 165, 76, 0.16);
            border-color: rgba(212, 165, 76, 0.30);
            outline: none;
        }}
        </style>
        <div id="{bar_id}" role="button" tabindex="0" aria-label="Copy prompt">
          <span class="mockup-prompt-label">Copy Prompt</span>
          {edit_markup}
        </div>
        <script>
        (() => {{
          const bar = document.getElementById("{bar_id}");
          const edit = document.getElementById("{bar_id}-edit");
          const promptText = {prompt_text_json};
          const promptId = {prompt_id_json};
          const originalLabel = "Copy Prompt";

          if (edit) {{
            edit.addEventListener("click", (event) => {{
              event.preventDefault();
              event.stopPropagation();
              try {{
                const target = new URL(window.parent.location.href);
                target.searchParams.set("mockup_prompt_edit", promptId);
                window.parent.location.href = target.toString();
              }} catch (error) {{
                window.open("?mockup_prompt_edit=" + encodeURIComponent(promptId), "_parent");
              }}
            }});
          }}

          async function copyPrompt(event) {{
            if (event.target && event.target.closest && event.target.closest(".mockup-prompt-edit")) {{
              return;
            }}
            event.preventDefault();
            event.stopPropagation();
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
            }} catch (error) {{
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

            const toast = document.createElement("div");
            toast.innerText = "Prompt copied";
            toast.style.position = "fixed";
            toast.style.bottom = "22px";
            toast.style.right = "22px";
            toast.style.zIndex = "999999";
            toast.style.background = "#F5F2EA";
            toast.style.color = "#0B0B0D";
            toast.style.border = "1px solid rgba(212,165,76,0.85)";
            toast.style.borderRadius = "999px";
            toast.style.padding = "10px 14px";
            toast.style.fontWeight = "700";
            toast.style.boxShadow = "0 12px 32px rgba(0,0,0,0.32)";
            document.body.appendChild(toast);
            bar.querySelector(".mockup-prompt-label").innerText = "Prompt copied";
            setTimeout(() => {{
              if (toast.parentNode) {{
                toast.parentNode.removeChild(toast);
              }}
              bar.querySelector(".mockup-prompt-label").innerText = originalLabel;
            }}, 1400);
          }}

          bar.addEventListener("click", copyPrompt);
          bar.addEventListener("keydown", (event) => {{
            if (event.key === "Enter" || event.key === " ") {{
              copyPrompt(event);
            }}
          }});
        }})();
        </script>
        """,
        height=54,
    )


def render_mockup_prompt_action_row(title, prompt_text, key, prompt_id):
    prompt_text = current_prompt_text(prompt_id, prompt_text).strip()
    notice = st.session_state.pop("mockup_prompt_notice", "")
    if notice:
        st.success(notice)
    render_mockup_prompt_bar(prompt_text, f"mockup-copy::{key}", prompt_id)
    render_mockup_prompt_editor(title, prompt_id, prompt_text)


def prime_asset_selection_state(result):
    if not result["run_dir"]:
        return

    for asset in result["assets"]:
        state_key = get_asset_checkbox_key(result["run_dir"], asset["key"])
        if state_key not in st.session_state:
            st.session_state[state_key] = asset["include_in_zip"]


def upsert_result_asset(result, asset_record):
    result = normalize_generation_result(result)
    normalized_asset = normalize_asset(asset_record)

    for index, existing_asset in enumerate(result["assets"]):
        if existing_asset["key"] == normalized_asset["key"]:
            merged_asset = existing_asset.copy()
            merged_asset.update(normalized_asset)
            result["assets"][index] = normalize_asset(merged_asset)
            return result

    result["assets"].append(normalized_asset)
    return result


def write_local_manifest(result, uploaded_files=None):
    result = normalize_generation_result(result)
    if not result["run_dir"]:
        return None

    manifest_path = Path(result["run_dir"]) / "manifest.json"
    manifest_data = {}

    if manifest_path.exists():
        with manifest_path.open("r", encoding="utf-8") as file_handle:
            manifest_data = json.load(file_handle)

    manifest_data.update(
        {
            "product_name": result["product_name"],
            "product_slug": result["product_slug"],
            "sport_category": result["sport_category"],
            "created_at": result["created_at"],
            "local_run_path": str(Path(result["run_dir"]).resolve()),
            "drive_folder_id": result["drive_run_id"],
            "drive_folder_link": result["drive_run_url"],
            "uploaded_files": uploaded_files
            if uploaded_files is not None
            else manifest_data.get("uploaded_files", []),
        }
    )

    manifest_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
    result["manifest_path"] = manifest_path
    return manifest_path


def ensure_drive_sections():
    drive_storage = get_drive_storage_module()
    root_folder_id = drive_storage.get_root_folder_id()
    if not root_folder_id:
        raise drive_storage.DriveStorageError(
            "GOOGLE_DRIVE_ROOT_FOLDER_ID is missing."
        )

    section_ids = {}
    for key, folder_name in DRIVE_SECTION_NAMES.items():
        section_ids[key] = drive_storage.ensure_drive_folder(root_folder_id, folder_name)

    return section_ids


def sync_result_to_google_drive(result):
    result = normalize_generation_result(result)
    write_local_manifest(result)

    if not result["run_dir"]:
        return result

    if not ENABLE_GOOGLE_DRIVE:
        result["drive_sync_enabled"] = False
        result["drive_sync_error"] = None
        result["drive_sync_message"] = "Google Drive is disabled in lightweight mode."
        return result

    drive_storage = get_drive_storage_module()

    if not drive_storage.is_drive_configured():
        result["drive_sync_enabled"] = False
        result["drive_sync_error"] = None
        result["drive_sync_message"] = (
            "Google Drive is not configured. Files were saved locally only."
        )
        return result

    try:
        section_ids = ensure_drive_sections()
        upload_info = drive_storage.upload_folder_to_drive(
            result["run_dir"],
            section_ids["mockups"],
        )
        manifest_data = drive_storage.create_or_update_manifest(
            result["run_dir"],
            upload_info["folder_id"],
            upload_info["uploaded_files"],
        )
        result["drive_sync_enabled"] = True
        result["drive_root_id"] = drive_storage.get_root_folder_id()
        result["drive_root_url"] = drive_storage.get_drive_folder_link(result["drive_root_id"])
        result["drive_run_id"] = upload_info["folder_id"]
        result["drive_run_url"] = upload_info["folder_link"]
        result["uploaded_files"] = manifest_data.get("uploaded_files", upload_info["uploaded_files"])
        result["drive_sync_error"] = None
        result["drive_sync_message"] = "Saved to Google Drive"
        write_local_manifest(result, uploaded_files=result["uploaded_files"])
    except Exception as error:
        result["drive_sync_enabled"] = True
        result["drive_sync_error"] = str(error)
        result["drive_sync_message"] = None

    return result


def rebuild_result_artifacts(result):
    result = normalize_generation_result(result)

    if not result["run_dir"] or not result["product_slug"]:
        return result

    run_dir = Path(result["run_dir"])
    zip_dir = run_dir / "zip"
    zip_dir.mkdir(parents=True, exist_ok=True)

    export_dirs = image_factory.rebuild_export_folders(
        run_dir,
        result["assets"],
        product_name=result.get("product_name", ""),
        sport_category=result.get("sport_category", ""),
    )
    result["zip_dir"] = zip_dir
    result["shopify_uploads_dir"] = export_dirs["shopify_uploads_dir"]
    result["shopify_uploads_html_path"] = export_dirs.get("shopify_uploads_html_path")
    result["socials_dir"] = export_dirs["socials_dir"]

    for key in ("zip_path", "social_zip_path", "complete_zip_path"):
        existing_path = result.get(key)
        if existing_path:
            with suppress(FileNotFoundError, PermissionError):
                Path(existing_path).unlink()
        result[key] = None

    prompt_zip_path = result.get("prompt_zip_path")
    if prompt_zip_path and not Path(prompt_zip_path).exists():
        result["prompt_zip_path"] = None

    write_local_manifest(result)
    return result


def apply_asset_selection_from_session(result):
    result = normalize_generation_result(result)
    prime_asset_selection_state(result)

    selections_changed = False

    for asset in result["assets"]:
        state_key = get_asset_checkbox_key(result["run_dir"], asset["key"])
        selected = bool(st.session_state.get(state_key, asset["include_in_zip"]))
        if selected != asset["include_in_zip"]:
            asset["include_in_zip"] = selected
            selections_changed = True

    if selections_changed:
        result = rebuild_result_artifacts(result)
        st.session_state.last_generation_result = result

    return result


def build_shopify_zip_package(result):
    result = rebuild_result_artifacts(result)
    shopify_uploads_dir = result.get("shopify_uploads_dir")

    if not shopify_uploads_dir or not Path(shopify_uploads_dir).exists():
        raise FileNotFoundError("Shopify upload files are not available for this run.")

    zip_dir = Path(result["zip_dir"] or (Path(result["run_dir"]) / "zip"))
    zip_dir.mkdir(parents=True, exist_ok=True)
    result["zip_path"] = image_factory.create_shopify_pack_zip(
        zip_dir,
        result["product_slug"],
        Path(shopify_uploads_dir),
    )
    result["status_text"] = "Shopify ZIP ready."
    write_local_manifest(result)
    return result


def ensure_lifestyle_prompts(result):
    result = normalize_generation_result(result)

    existing_prompt_paths = [
        str(Path(prompt_path))
        for prompt_path in result.get("prompt_paths", [])
        if Path(prompt_path).exists()
    ]
    if existing_prompt_paths:
        result["prompt_paths"] = existing_prompt_paths
        return result

    if not result["run_dir"] or not result["black_framed_webp_path"]:
        return result

    prompt_dir, _, prompt_paths, _ = image_factory.generate_lifestyle_prompt_pack(
        result["product_name"],
        result["sport_category"],
        result["product_slug"],
        Path(result["run_dir"]),
        Path(result["black_framed_webp_path"]),
    )
    result["prompt_dir"] = str(prompt_dir)
    result["prompt_paths"] = [str(prompt_path) for prompt_path in prompt_paths]
    result["prompt_zip_path"] = None
    write_local_manifest(result)
    return result


def ensure_primary_download_zip(result):
    result = normalize_generation_result(result)
    existing_zip_path = result.get("zip_path")
    if existing_zip_path and Path(existing_zip_path).exists():
        return result

    result = rebuild_result_artifacts(result)
    shopify_uploads_dir = result.get("shopify_uploads_dir")
    socials_dir = result.get("socials_dir")

    if not shopify_uploads_dir or not Path(shopify_uploads_dir).exists():
        raise FileNotFoundError("Shopify upload files are not available for this run.")
    if not socials_dir or not Path(socials_dir).exists():
        raise FileNotFoundError("JPG export files are not available for this run.")

    zip_dir = Path(result["zip_dir"] or (Path(result["run_dir"]) / "zip"))
    zip_dir.mkdir(parents=True, exist_ok=True)
    result["zip_path"] = image_factory.create_download_bundle_zip(
        zip_dir,
        result["product_slug"],
        Path(shopify_uploads_dir),
        Path(socials_dir),
    )
    write_local_manifest(result)
    return result


def build_lifestyle_prompt_pack(result):
    result = normalize_generation_result(result)

    if not result["run_dir"] or not result["black_framed_webp_path"]:
        raise FileNotFoundError("The black framed reference image is missing for this run.")

    run_dir = Path(result["run_dir"])
    zip_dir = Path(result["zip_dir"] or (run_dir / "zip"))
    zip_dir.mkdir(parents=True, exist_ok=True)

    prompt_dir, _, prompt_paths, _ = image_factory.generate_lifestyle_prompt_pack(
        result["product_name"],
        result["sport_category"],
        result["product_slug"],
        run_dir,
        Path(result["black_framed_webp_path"]),
    )

    result["prompt_dir"] = prompt_dir
    result["prompt_paths"] = prompt_paths
    result["prompt_zip_path"] = image_factory.create_prompt_pack_zip(
        zip_dir,
        result["product_slug"],
        prompt_dir,
    )
    result["lifestyle_pack_error"] = None
    result["status_text"] = "Lifestyle prompt pack ready."
    write_local_manifest(result)
    return result


def build_complete_download_pack(result):
    result = rebuild_result_artifacts(result)
    zip_dir = Path(result["zip_dir"] or (Path(result["run_dir"]) / "zip"))
    zip_dir.mkdir(parents=True, exist_ok=True)

    prompt_dir = result.get("prompt_dir")
    if prompt_dir and not Path(prompt_dir).exists():
        prompt_dir = None
        result["prompt_dir"] = None
        result["prompt_paths"] = []
        result["prompt_zip_path"] = None

    result["complete_zip_path"] = image_factory.create_complete_pack_zip(
        zip_dir,
        result["product_slug"],
        prompt_dir=prompt_dir,
        assets=result["assets"],
    )
    result["status_text"] = "Complete download pack ready."
    write_local_manifest(result)
    return result


def build_lifestyle_asset(prompt_path, saved_paths):
    prompt_filename = Path(prompt_path).name
    is_product_page_asset = image_factory.is_product_page_prompt_filename(prompt_filename)
    return image_factory.build_asset_record(
        key=get_lifestyle_asset_key(prompt_filename),
        label=get_prompt_label(prompt_path),
        review_path=saved_paths.get("jpg_path") or saved_paths.get("webp_path"),
        preview_path=saved_paths.get("preview_path"),
        webp_path=saved_paths.get("webp_path"),
        jpg_path=saved_paths.get("jpg_path"),
        include_in_zip=True,
        asset_group="lifestyle",
        prompt_filename=prompt_filename,
        export_to_shopify=is_product_page_asset,
        export_to_socials=True,
    )


def save_uploaded_lifestyle_result(result, prompt_path, uploaded_file):
    result = normalize_generation_result(result)

    saved_paths = image_factory.save_lifestyle_mockup(
        run_dir=result["run_dir"],
        product_slug=result["product_slug"],
        sport_slug=result["sport_slug"],
        prompt_filename=Path(prompt_path).name,
        image_file=uploaded_file,
    )

    prompt_filename = Path(prompt_path).name
    result["lifestyle_mockup_paths"][prompt_filename] = saved_paths
    result = upsert_result_asset(result, build_lifestyle_asset(prompt_path, saved_paths))

    result["lifestyle_pack_error"] = None
    result["status_text"] = f"Saved lifestyle image for {get_prompt_label(prompt_path)}."
    result = rebuild_result_artifacts(result)
    return result


def render_asset_selection_controls(result):
    result = normalize_generation_result(result)

    if not result["assets"]:
        return result

    included_count = sum(1 for asset in result["assets"] if asset["include_in_zip"])
    st.subheader("Pack Selection")
    st.caption(
        f"{included_count} of {len(result['assets'])} images are currently included. "
        "Untick any image to leave it out of the optional ZIP packs and export folders."
    )

    return result


def render_asset_download_controls(asset, run_dir):
    download_cols = st.columns(2)
    with download_cols[0]:
        render_download_button(
            "WEBP",
            asset.get("webp_path"),
            "image/webp",
            key=f"download-webp::{run_dir}::{asset['key']}",
        )
    with download_cols[1]:
        render_download_button(
            "JPG",
            asset.get("jpg_path"),
            "image/jpeg",
            key=f"download-jpg::{run_dir}::{asset['key']}",
        )


def get_asset_full_resolution_path(asset):
    for candidate in (
        asset.get("review_path"),
        asset.get("webp_path"),
        asset.get("jpg_path"),
    ):
        if candidate and Path(candidate).exists():
            return Path(candidate)

    return None


def render_preview_card(asset, run_dir, image_width=380, caption_text=None):
    preview_path = asset.get("preview_path")
    if preview_path and Path(preview_path).exists():
        st.image(str(preview_path), caption=asset["label"], width=image_width)
    else:
        st.caption("Preview not available.")

    if caption_text:
        st.caption(caption_text)

    full_resolution_path = get_asset_full_resolution_path(asset)
    if not full_resolution_path:
        return

    state_key = f"show-full-resolution::{run_dir}::{asset['key']}"
    button_key = f"toggle-full-resolution::{run_dir}::{asset['key']}"
    action_label = "Hide Full Resolution" if st.session_state.get(state_key) else "Load Full Resolution"
    if st.button(action_label, key=button_key, use_container_width=True):
        st.session_state[state_key] = not st.session_state.get(state_key, False)
        st.rerun()

    if st.session_state.get(state_key):
        st.image(
            str(full_resolution_path),
            caption=f"{asset['label']} - full resolution",
            use_container_width=True,
        )
        st.caption(
            "This full-resolution file only loads after you click the button. "
            "Copy or open this version when you want the best quality for ChatGPT."
        )


def render_generated_previews(result):
    st.subheader("Generated Previews")
    st.caption(
        "These are lightweight preview files only. Click Load Full Resolution on any card if you want to open or copy the higher-quality file."
    )
    preview_cols = st.columns(2)
    base_assets = [asset for asset in result["assets"] if asset["asset_group"] == "generated"]

    for index, asset in enumerate(base_assets):
        with preview_cols[index % 2]:
            render_preview_card(
                asset,
                result["run_dir"],
                image_width=380,
                caption_text="Use the preview for fast browsing. Load the full-resolution file before copying into ChatGPT.",
            )


def render_primary_zip_download(result, section_key):
    st.subheader("Save ZIP")
    st.caption(
        "One ZIP only. Save it into the correct Google Drive folder, or use the backup download if Drive save is not connected."
    )
    action_cols = st.columns([1, 1, 1.2])

    with action_cols[0]:
        if st.button(
            "Save ZIP",
            key=f"save-primary-zip::{result['run_dir']}::{section_key}",
            use_container_width=True,
        ):
            try:
                upload_info = save_zip_to_drive_folder(Path(result["zip_path"]))
                result["zip_drive_file_link"] = upload_info.get("drive_link")
                result["zip_drive_folder_url"] = ZIP_SAVE_DRIVE_FOLDER_URL or result.get("zip_drive_folder_url")
                result["zip_drive_message"] = "ZIP saved to the Google Drive folder."
                result["zip_drive_error"] = None
                st.session_state.last_generation_result = result
                st.rerun()
            except Exception as error:
                result["zip_drive_message"] = None
                result["zip_drive_error"] = str(error)
                st.session_state.last_generation_result = result
                st.rerun()

    with action_cols[1]:
        if ZIP_SAVE_DRIVE_FOLDER_URL:
            render_external_link(
                "Open Drive Folder",
                ZIP_SAVE_DRIVE_FOLDER_URL,
                f"open-zip-drive-folder::{result['run_dir']}::{section_key}",
            )

    with action_cols[2]:
        render_download_button(
            "Download ZIP Instead",
            result.get("zip_path"),
            "application/zip",
            key=f"download-primary-zip::{result['run_dir']}::{section_key}",
        )

    if result.get("zip_drive_message"):
        st.success(result["zip_drive_message"])
        if result.get("zip_drive_file_link"):
            render_external_link(
                "Open Saved ZIP",
                result["zip_drive_file_link"],
                f"open-saved-zip::{result['run_dir']}::{section_key}",
            )
    elif result.get("zip_drive_error"):
        st.info(result["zip_drive_error"])


def render_prompt_cards(result, prompt_paths, heading):
    if not prompt_paths:
        return

    st.subheader(heading)
    cols = st.columns(3)

    for index, prompt_path in enumerate(prompt_paths):
        with cols[index % 3]:
            prompt_title = get_prompt_label(prompt_path)
            st.markdown(f"**{prompt_title}**")
            prompt_name = prompt_path.name
            default_prompt_text = prompt_path.read_text(encoding="utf-8")
            prompt_id = prompt_edit_id("lifestyle", prompt_name)
            prompt_text = current_prompt_text(prompt_id, default_prompt_text)
            prompt_key = f"{result['run_dir']}::{prompt_name}"
            render_mockup_prompt_action_row(prompt_title, prompt_text, prompt_key, prompt_id)

            saved_lifestyle_paths = result["lifestyle_mockup_paths"].get(prompt_name)

            if saved_lifestyle_paths:
                saved_preview_path = saved_lifestyle_paths.get("preview_path")

                preview_path = saved_preview_path
                if preview_path and Path(preview_path).exists():
                    lifestyle_asset = build_lifestyle_asset(prompt_path, saved_lifestyle_paths)
                    render_preview_card(
                        lifestyle_asset,
                        result["run_dir"],
                        image_width=360,
                        caption_text="Saved. This lightweight preview is shown here, but you can load the full-resolution image before copying it into ChatGPT.",
                    )
                    render_asset_download_controls(lifestyle_asset, result["run_dir"])
                    st.caption("It will be included the next time you save the ZIP.")

            uploaded_lifestyle_image = st.file_uploader(
                "Upload image from ChatGPT",
                type=["png", "jpg", "jpeg", "webp"],
                key=f"lifestyle-upload::{result['run_dir']}::{prompt_name}",
            )

            if st.button(
                "Add To ZIP",
                key=f"save-lifestyle::{result['run_dir']}::{prompt_name}",
                use_container_width=True,
            ):
                if uploaded_lifestyle_image is None:
                    st.warning("Upload the generated lifestyle image first.")
                else:
                    try:
                        updated_result = save_uploaded_lifestyle_result(
                            result,
                            prompt_path,
                            uploaded_lifestyle_image,
                        )
                        st.session_state.last_generation_result = updated_result
                        st.rerun()
                    except Exception as error:
                        st.error("Could not save the lifestyle image for this prompt.")
                        st.exception(error)


def render_optional_package_controls(result):
    st.subheader("Optional Packs")
    st.caption("The first generate step stays lightweight. Create heavier ZIP packages only when you need them.")

    package_specs = [
        {
            "button_label": "Create Shopify ZIP",
            "download_label": "Download Shopify ZIP",
            "path_key": "zip_path",
            "mime": "application/zip",
            "builder": build_shopify_zip_package,
            "error_message": "Could not create the Shopify ZIP.",
        },
        {
            "button_label": "Create Lifestyle Prompt Pack",
            "download_label": "Download Lifestyle Prompt Pack",
            "path_key": "prompt_zip_path",
            "mime": "application/zip",
            "builder": build_lifestyle_prompt_pack,
            "error_message": "Could not create the lifestyle prompt pack.",
        },
        {
            "button_label": "Create Complete Download Pack",
            "download_label": "Download Complete Download Pack",
            "path_key": "complete_zip_path",
            "mime": "application/zip",
            "builder": build_complete_download_pack,
            "error_message": "Could not create the complete download pack.",
        },
    ]

    package_cols = st.columns(3)
    for index, package_spec in enumerate(package_specs):
        with package_cols[index]:
            if st.button(
                package_spec["button_label"],
                key=f"create-package::{result['run_dir']}::{package_spec['path_key']}",
                use_container_width=True,
            ):
                try:
                    updated_result = package_spec["builder"](result)
                    st.session_state.last_generation_result = updated_result
                    st.rerun()
                except Exception as error:
                    st.error(package_spec["error_message"])
                    st.exception(error)

            render_download_button(
                package_spec["download_label"],
                result.get(package_spec["path_key"]),
                package_spec["mime"],
                key=f"download-package::{result['run_dir']}::{package_spec['path_key']}",
            )


def render_generation_result(result):
    result = normalize_generation_result(result)
    result = ensure_lifestyle_prompts(result)
    result = ensure_primary_download_zip(result)
    st.session_state.last_generation_result = result
    st.success(result.get("status_text") or "Core Sports Cave product images are ready.")

    if result.get("shopify_uploads_dir"):
        with suppress(FileNotFoundError):
            st.caption(
                f"{len(list(Path(result['shopify_uploads_dir']).glob('*.webp')))} WEBP files ready for Shopify uploads."
            )

    if result.get("socials_dir"):
        with suppress(FileNotFoundError):
            st.caption(
                f"{len(list(Path(result['socials_dir']).glob('*.jpg')))} JPG files ready for socials."
            )

    if ENABLE_GOOGLE_DRIVE and result["drive_run_url"]:
        st.success("Saved to Google Drive")
        st.markdown(f"[Open Google Drive run folder]({result['drive_run_url']})")
    elif ENABLE_GOOGLE_DRIVE and result["drive_sync_error"]:
        st.warning(
            "Google Drive upload failed, but the local files are still ready. "
            f"{result['drive_sync_error']}"
        )

    with st.expander("Local output and Google Drive reminder"):
        st.caption(f"Local output folder: {result['run_dir']}")
        st.info(
            "Upload or save the completed ZIP into the matching product's Google Drive root folder, "
            "then add that folder or ZIP link to the product File Hub. Automatic Drive upload is not used in Phase 3."
        )

    render_primary_zip_download(result, "top")
    render_generated_previews(result)

    if result["lifestyle_pack_error"]:
        st.warning(
            "The core image set was created, but one of the prompt steps reported an issue: "
            f"{result['lifestyle_pack_error']}"
        )

    prompt_paths = [
        Path(prompt_path)
        for prompt_path in result["prompt_paths"]
        if Path(prompt_path).exists()
    ]

    if prompt_paths:
        st.info(
            "Use the prompts below for ChatGPT lifestyle images, then upload the finished images back into the matching cards."
        )
        product_page_prompts = [path for path in prompt_paths if is_product_page_prompt(path)]
        social_prompts = [path for path in prompt_paths if not is_product_page_prompt(path)]

        render_prompt_cards(
            result,
            product_page_prompts,
            "Product Page Lifestyle Mockups",
        )
        render_prompt_cards(
            result,
            social_prompts,
            "Social Lifestyle Mockups",
        )

    render_primary_zip_download(result, "bottom")


def render_recent_runs_sidebar():
    return


def render_sidebar():
    st.sidebar.title("Sports Cave OS")
    st.sidebar.caption("Internal operations command centre")
    st.sidebar.caption(APP_VERSION)
    visible_page = (
        st.session_state.selected_page
        if st.session_state.selected_page in MENU_OPTIONS
        else "Dashboard"
    )
    chosen_page = st.sidebar.radio(
        "Navigation",
        MENU_OPTIONS,
        index=MENU_OPTIONS.index(visible_page),
        label_visibility="collapsed",
    )
    if chosen_page != visible_page:
        st.session_state.selected_page = chosen_page
        st.rerun()
    if st.session_state.selected_page not in MENU_OPTIONS:
        st.sidebar.caption(f"Internal page open: {st.session_state.selected_page}")
        if st.sidebar.button("Back to Dashboard", use_container_width=True):
            st.session_state.selected_page = "Dashboard"
            st.rerun()

    if st.session_state.selected_page == "Mockups":
        st.sidebar.divider()
        st.sidebar.subheader("Mockup Workflow")
        st.sidebar.write("1. Upload artwork.")
        st.sidebar.write("2. Generate core Shopify images.")
        st.sidebar.write("3. Review lightweight previews.")
        st.sidebar.write("4. Download one ZIP bundle.")
        st.sidebar.write("5. Use the prompt sections below if you want ChatGPT lifestyle images.")
    elif st.session_state.selected_page == "Edition Ops":
        st.sidebar.divider()
        st.sidebar.subheader("Edition Ops")
        st.sidebar.write("1. Refresh active products only when needed.")
        st.sidebar.write("2. Edit edition totals and next numbers in one chart.")
        st.sidebar.write("3. Save changed rows to product fields.")
        st.sidebar.write("4. Use CSV import only when replacing the table.")
    elif st.session_state.selected_page == "Orders":
        st.sidebar.divider()
        st.sidebar.subheader("Orders")
        st.sidebar.write("1. Refresh recent paid orders only when needed.")
        st.sidebar.write("2. Edition numbers are read-only and come from Edition Ops/order allocations.")
        st.sidebar.write("3. Select rows, then generate or upload certificates from the top buttons.")
        st.sidebar.write("4. Use Open PDF after a certificate is generated/uploaded.")
    elif st.session_state.selected_page == "Prodigi":
        st.sidebar.divider()
        st.sidebar.subheader("Prodigi")
        st.sidebar.write("1. Open the Prodigi dashboard and search the order.")
        st.sidebar.write("2. Match Shopify size to Prodigi size: XL=A1, L=A2, M=A3, S=A4.")
        st.sidebar.write("3. Copy the exact Prodigi name or code.")
        st.sidebar.write("4. Check the frame colour before sending to production.")
    elif st.session_state.selected_page == "Ads Intelligence":
        st.sidebar.divider()
        st.sidebar.subheader("Ads Intelligence")
        st.sidebar.write("1. Review stored Meta performance from Supabase.")
        st.sidebar.write("2. Sync Meta Ads data only when you click the manual button.")
        st.sidebar.write("3. Tag creatives and export ChatGPT-ready analysis packs.")
    elif st.session_state.selected_page == "Dashboard":
        st.sidebar.divider()
        st.sidebar.subheader("Today's Focus")
        st.sidebar.write("Open Edition Ops only when product edition fields need a manual update.")
    elif st.session_state.selected_page == "Files":
        st.sidebar.divider()
        st.sidebar.subheader("Asset Control")
        st.sidebar.write("Filter missing or review assets, then open the master product record to update them.")
    elif st.session_state.selected_page == "Persistence Check":
        st.sidebar.divider()
        st.sidebar.subheader("Persistence Check")
        st.sidebar.write("Confirm Supabase tables, imports, assets, certificates, and orders are permanently stored.")
    elif st.session_state.selected_page == "Product Uploads":
        st.sidebar.divider()
        st.sidebar.subheader("Upload Workflow")
        st.sidebar.write("Work through products by stage, then use the Shopify prompt tools when needed.")
    elif st.session_state.selected_page == "Developer":
        st.sidebar.divider()
        st.sidebar.subheader("Developer")
        st.sidebar.write("Run connection tests, imports, diagnostics, and admin checks only when needed.")
        st.sidebar.caption("File Hub hidden until PSD/Drive asset workflow is active.")
        if st.sidebar.button("File Hub (Coming Soon)", use_container_width=True):
            st.session_state.selected_page = "Files"
            st.rerun()

    st.sidebar.divider()
    st.sidebar.subheader("MVP Mode")
    st.sidebar.caption(
        "Edition Ops controls product edition fields. Orders handles fulfilment and certificates from a lightweight saved snapshot."
    )


def render_mockups_page():
    get_image_factory()
    log_app_memory("Page load: Mockups")
    st.title("Mockups")
    st.caption(
        "The existing Sports Cave Image Factory. Upload one finished artwork, generate the five core Shopify images, then download one simple ZIP bundle."
    )
    st.caption("Upload limit: 20MB. Working images are capped to 2000px and UI previews are capped to 900px.")

    st.subheader("1. Upload Artwork")
    uploaded_file = st.file_uploader(
        "Upload finished Sports Cave artwork",
        type=["jpg", "jpeg", "png", "webp"],
    )

    upload_details = None
    upload_validation_error = None

    autofill_product_name = get_product_name_from_upload(uploaded_file)

    if uploaded_file is not None and uploaded_file.name != st.session_state.last_uploaded_file_name:
        if (
            not st.session_state.product_name.strip()
            or st.session_state.product_name == st.session_state.last_autofilled_product_name
        ):
            st.session_state.product_name = autofill_product_name

        st.session_state.last_uploaded_file_name = uploaded_file.name
        st.session_state.last_autofilled_product_name = autofill_product_name

    elif uploaded_file is None and st.session_state.last_uploaded_file_name is not None:
        if st.session_state.product_name == st.session_state.last_autofilled_product_name:
            st.session_state.product_name = ""

        st.session_state.last_uploaded_file_name = None
        st.session_state.last_autofilled_product_name = ""
        st.session_state.uploaded_preview_signature = None
        st.session_state.uploaded_preview_path = None

    if uploaded_file is not None:
        try:
            upload_details = validate_uploaded_artwork(uploaded_file)
        except ValueError as error:
            upload_validation_error = str(error)
            st.error(upload_validation_error)
        except Exception as error:
            upload_validation_error = "Could not validate the uploaded artwork."
            st.error(upload_validation_error)
            st.exception(error)

    product_name = st.text_input(
        "Product name",
        key="product_name",
        placeholder="Example: Arsenal The Wait Is Over",
    )

    sport_option = st.selectbox(
        "Sport category",
        options=SPORT_OPTIONS,
        index=0,
    )

    custom_sport = ""
    if sport_option == "Custom":
        custom_sport = st.text_input(
            "Custom sport category",
            placeholder="Example: Formula 1",
        )

    st.subheader("2. Generate Core Shopify Images")
    generate_clicked = st.button("Generate Core Shopify Images", type="primary")

    if uploaded_file is not None:
        st.subheader("Uploaded Artwork")
        if upload_validation_error:
            st.session_state.uploaded_preview_signature = None
            st.session_state.uploaded_preview_path = None
            st.caption("Upload preview unavailable until the file validates cleanly.")
        elif should_defer_uploaded_preview(upload_details):
            st.session_state.uploaded_preview_signature = None
            st.session_state.uploaded_preview_path = None
            st.info(
                "Preview generation was skipped for this larger upload to keep Sports Cave OS stable. "
                "You can still generate the mockups normally."
            )
            st.caption(uploaded_file.name)
        else:
            preview_signature = get_uploaded_file_signature(uploaded_file)
            preview_path = st.session_state.uploaded_preview_path
            preview_missing = not preview_path or not Path(preview_path).exists()
            if preview_signature != st.session_state.uploaded_preview_signature or preview_missing:
                try:
                    preview_path = create_uploaded_preview(uploaded_file)
                    st.session_state.uploaded_preview_signature = preview_signature
                    st.session_state.uploaded_preview_path = str(preview_path) if preview_path else None
                except Exception as error:
                    st.warning(f"Could not create upload preview: {error}")
                    st.session_state.uploaded_preview_signature = preview_signature
                    st.session_state.uploaded_preview_path = None

            preview_path = st.session_state.uploaded_preview_path
            if preview_path and Path(preview_path).exists():
                st.image(str(preview_path), caption=uploaded_file.name, width=400)
            else:
                st.caption("Lightweight preview unavailable until the upload is processed.")

    if generate_clicked:
        sport_category = get_sport_category(sport_option, custom_sport)

        temp_artwork_path = None
        status_container = st.empty()
        progress_bar = st.progress(0)

        def update_status(message, progress=None, level="info"):
            logging.info(message)
            if level == "error":
                status_container.error(message)
            elif level == "success":
                status_container.success(message)
            else:
                status_container.info(message)

            if progress is not None:
                progress_bar.progress(min(max(int(progress), 0), 100))

        try:
            if uploaded_file is None:
                raise ValueError("Please upload an artwork image first.")
            if upload_validation_error:
                raise ValueError(upload_validation_error)
            if not product_name.strip():
                raise ValueError("Please enter a product name.")
            if not sport_category:
                raise ValueError("Please enter a sport category.")

            update_status("Validating upload...", 5)
            upload_details = upload_details or validate_uploaded_artwork(uploaded_file)

            update_status("Preparing lightweight working image...", 15)
            log_app_memory("Mockup generation start")
            suffix = Path(uploaded_file.name).suffix or ".jpg"
            uploaded_file.seek(0)
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                shutil.copyfileobj(uploaded_file, temp_file)
                temp_artwork_path = Path(temp_file.name)
            uploaded_file.seek(0)

            result = image_factory.generate_product_images(
                product_name=product_name,
                sport_category=sport_category,
                artwork_file_path=temp_artwork_path,
                base_dir=BASE_DIR,
                status_callback=lambda msg, progress=None: update_status(msg, progress),
            )

            update_status("Creating downloads...", 92)
            result = rebuild_result_artifacts(result)
            image_factory.cleanup_old_runs(
                BASE_DIR / "output",
                keep_latest=image_factory.MAX_STORED_RUNS,
                active_run_dir=Path(result["run_dir"]),
            )
            result["status_text"] = "Done"
            image_factory.log_memory("Completion")
            status_container.empty()
            progress_bar.empty()
            st.session_state.last_generation_result = result
        except image_factory.MemoryLimitExceededError as error:
            logging.exception("Generation stopped by memory limit")
            status_container.error(str(error))
            st.error(str(error))
        except Exception as error:
            logging.exception("Generation failed")
            status_container.error("Generation failed. See details below.")
            st.error("Generation failed. See details below.")
            st.exception(error)
        finally:
            if temp_artwork_path is not None:
                with suppress(FileNotFoundError, PermissionError):
                    temp_artwork_path.unlink()

    if st.session_state.last_generation_result is not None:
        render_generation_result(st.session_state.last_generation_result)


def render_product_uploads_page():
    started = time.perf_counter()
    log_app_memory("Page load: Product Uploads")
    st.subheader("Shopify Prompt Tools")
    st.caption(
        "Use this lightweight prompt page when you already have your Shopify upload images and HTML preview ready to drag into ChatGPT."
    )

    with st.expander("How to", expanded=False):
        st.markdown(
            "1. Drag every WEBP file from your `shopify-uploads` folder into ChatGPT.\n"
            "2. Drag the matching HTML preview into ChatGPT if you have it.\n"
            "3. Copy either the new-product prompt or the update-existing-product prompt.\n"
            "4. The image alt text, SEO meta tags, and final QA checklist instructions are already embedded inside both prompts.\n"
            "\n"
            "This page stays manual on purpose so it remains fast and lightweight on Render."
        )

    st.divider()

    render_copyable_prompt(
        "New Shopify Product Prompt",
        get_product_upload_prompt({}, update_existing=False),
        "new-shopify-product-prompt",
        prompt_id=prompt_edit_id("product-upload", "new-shopify-product"),
    )

    st.divider()

    render_copyable_prompt(
        "Update Existing Product Prompt",
        get_product_upload_prompt({}, update_existing=True),
        "update-existing-shopify-product-prompt",
        prompt_id=prompt_edit_id("product-upload", "update-existing-shopify-product"),
    )
    safe_startup_print(f"PERF Product Uploads total={(time.perf_counter() - started):.3f}s")


def test_google_drive_connection():
    drive_storage = get_drive_storage_module()
    section_ids = ensure_drive_sections()
    test_dir = BASE_DIR / "output" / "_drive_test"
    test_dir.mkdir(parents=True, exist_ok=True)
    test_file = test_dir / "google-drive-connection-test.txt"
    test_file.write_text("Sports Cave Image Factory connection test", encoding="utf-8")

    try:
        return drive_storage.upload_file_to_drive(
            test_file,
            section_ids["system_logs"],
            mime_type="text/plain",
        )
    finally:
        with suppress(FileNotFoundError, PermissionError):
            test_file.unlink()


def render_google_drive_page():
    log_app_memory("Google Drive section render")
    st.title("Google Drive")
    st.caption("OAuth refresh-token Drive storage for Sports Cave runs.")

    if not ENABLE_GOOGLE_DRIVE:
        st.info("Google Drive is disabled in lightweight mode. Set `ENABLE_GOOGLE_DRIVE=true` to use this page.")
        return

    drive_storage = get_drive_storage_module()
    root_folder_id = drive_storage.get_root_folder_id()
    drive_configured = drive_storage.is_drive_configured()

    if drive_configured:
        st.success("Status: Connected")
    else:
        st.info("Status: Not connected")

    st.write(f"Root folder ID: `{root_folder_id or 'Not set'}`")
    if root_folder_id:
        st.markdown(
            f"[Open root folder]({drive_storage.get_drive_folder_link(root_folder_id)})"
        )

    if st.button("Test Google Drive Connection", type="primary", disabled=not drive_configured):
        try:
            uploaded_test_file = test_google_drive_connection()
            st.success("Google Drive connection test succeeded.")
            st.markdown(f"[Open uploaded test file]({uploaded_test_file['drive_link']})")
        except Exception as error:
            st.error(f"Google Drive connection test failed: {error}")

    st.subheader("Recent Drive Runs")
    if drive_configured:
        try:
            recent_runs = drive_storage.list_recent_drive_runs(limit=20)
        except Exception as error:
            st.warning(f"Could not load recent Drive runs: {error}")
            recent_runs = []
    else:
        recent_runs = []

    if recent_runs:
        for run_entry in recent_runs:
            st.markdown(f"- [{run_entry['name']}]({run_entry['url']})")
    else:
        st.caption("No Drive runs found yet.")


def get_password_protection_status():
    for env_key in PASSWORD_ENV_KEYS:
        if os.getenv(env_key):
            return "Enabled"

    return "Managed outside app or not detected"


def _developer_unlocked():
    return bool(st.session_state.get("developer_unlocked"))


def _developer_section_enabled(key, label):
    state_key = f"{key}-enabled"
    button_key = f"{key}-button"
    if st.session_state.get(key):
        st.session_state[state_key] = True
    if st.session_state.get(state_key):
        st.caption("Loaded for this session.")
        return True
    if st.button(label, key=button_key, use_container_width=True):
        st.session_state[state_key] = True
        return True
    return False


def _developer_section_error(title, error):
    logging.exception("Developer section failed: %s", title)
    st.error(f"{title} failed to load. The rest of Developer is still available.")
    st.caption(f"{type(error).__name__}: {error}")
    st.caption("Full traceback is logged in Render.")


def _developer_action_error(label, error):
    logging.exception("Developer action failed: %s", label)
    st.error(f"{label} failed.")
    st.caption(f"{type(error).__name__}: {error}")
    st.caption("Full traceback is logged in Render.")


def _render_developer_password_gate(title="Developer", caption="Protected diagnostics and setup tools."):
    st.title(title)
    st.caption(caption)
    password = st.text_input(
        "Developer password",
        type="password",
        key="developer-page-password-input",
    )
    unlock_cols = st.columns([1, 2])
    if unlock_cols[0].button("Unlock Developer", type="primary", use_container_width=True):
        if password == DEVELOPER_PAGE_PASSWORD:
            st.session_state.developer_unlocked = True
            st.rerun()
        else:
            st.error("Incorrect developer password.")
    unlock_cols[1].caption("Unlock is kept only for this Streamlit session.")


def _allocation_baseline_row_from_product(product):
    edition = product.get("edition") or {}
    return {
        "shopify_product_id": product.get("shopify_product_id") or "",
        "shopify_product_gid": product.get("shopify_product_id") or "",
        "handle": product.get("handle") or "",
        "product_title": product.get("title") or product.get("product_title") or "",
        "edition_enabled": edition.get("edition_enabled"),
        "edition_total": edition.get("edition_total"),
        "edition_next_number": edition.get("edition_next_number"),
        "edition_sold_count": edition.get("edition_sold_count"),
        "edition_remaining": edition.get("edition_remaining"),
        "edition_status": edition.get("edition_status"),
    }


def _fetch_allocation_baseline_rows(sync, config):
    loaded = sync.fetch_edition_ops_active_products(
        max_products=config.get("edition_ops_max_products", 500),
        page_size=50,
        config=config,
    )
    return [_allocation_baseline_row_from_product(product) for product in loaded.get("products") or []]


def _fetch_recent_paid_shopify_orders(sync, config):
    orders = []
    for page in sync.iter_order_pages(
        days=30,
        page_size=50,
        max_orders=100,
        query="financial_status:paid",
        default_paid_unfulfilled_filter=False,
        config=config,
    ):
        orders.extend(page.get("orders") or [])
    return orders


def _historical_backfill_candidates(rows):
    candidates = []
    for row in rows or []:
        if row.get("has_saved_allocation"):
            continue
        if str(row.get("edition") or "").strip().startswith("#"):
            continue
        if not row.get("shopify_order_id") or not row.get("shopify_line_item_id") or not row.get("shopify_product_id"):
            continue
        candidates.append(row)
    allocator = importlib.import_module("order_allocator")

    def sort_key(row):
        order_digits = re.findall(r"\d+", str(row.get("order") or row.get("order_name") or ""))
        order_number = int(order_digits[-1]) if order_digits else 0
        return (
            allocator.normalize_datetime_utc(row.get("processed_at") or row.get("processedAt")),
            allocator.normalize_datetime_utc(row.get("created_at") or row.get("createdAt")),
            order_number,
        )

    return sorted(candidates, key=sort_key, reverse=True)


def _candidate_label(index, row):
    parts = [
        str(row.get("order") or ""),
        str(row.get("date") or ""),
        str(row.get("product") or ""),
        str(row.get("variant") or ""),
    ]
    return f"{index}: " + " | ".join(part for part in parts if part)


def _override_row_identity(row):
    if str(row.get("id") or "").startswith("snapshot|"):
        return str(row.get("id") or "")
    return "|".join(
        [
            str(row.get("shopify_order_id") or ""),
            str(row.get("shopify_line_item_id") or ""),
            str(row.get("allocation_index") or 1),
            str(row.get("edition_number") or ""),
        ]
    )


def _load_manual_override_rows(search, allocator, limit=80):
    rows = []
    seen = set()
    supabase_available = False
    try:
        supabase = importlib.import_module("supabase_backend")
        if supabase.is_configured():
            supabase_available = True
            for row in supabase.list_edition_orders(search=search, limit=limit):
                item = {**row, "source": row.get("source") or "edition_orders"}
                identity = _override_row_identity(item)
                if identity and identity not in seen:
                    rows.append(item)
                    seen.add(identity)
    except Exception as error:
        _developer_action_error("Load Supabase override rows", error)

    if not supabase_available:
        try:
            for row in allocator.snapshot_allocated_order_rows(search=search, limit=limit):
                identity = _override_row_identity(row)
                if identity and identity not in seen:
                    rows.append(row)
                    seen.add(identity)
        except Exception as error:
            _developer_action_error("Load snapshot override rows", error)

    def sort_key(row):
        order_digits = re.findall(r"\d+", str(row.get("shopify_order_name") or row.get("order_name") or ""))
        order_number = int(order_digits[-1]) if order_digits else 0
        return (
            allocator.normalize_datetime_utc(row.get("processed_at")),
            allocator.normalize_datetime_utc(row.get("created_at")),
            order_number,
        )

    return sorted(rows, key=sort_key, reverse=True)[: max(int(limit or 80), 1)]


def _mark_orders_snapshot_for_reload():
    st.session_state["orders_allocation_snapshot_loaded"] = False
    st.session_state["edition_ops_snapshot_loaded"] = False
    st.session_state["orders-ledger-cache-version"] = int(st.session_state.get("orders-ledger-cache-version", 0)) + 1
    st.session_state["edition-ops-ledger-cache-version"] = int(
        st.session_state.get("edition-ops-ledger-cache-version", 0)
    ) + 1
    with suppress(Exception):
        allocator = importlib.import_module("order_allocator")
        snapshot = allocator.load_orders_snapshot()
        st.session_state["orders_allocation_rows"] = snapshot.get("rows") or []
        st.session_state["orders_allocation_meta"] = {
            "last_refreshed": snapshot.get("last_refreshed") or "",
            "saved_at": snapshot.get("saved_at") or "",
        }


def _render_developer_allocation_tools():
    if not _developer_section_enabled("developer-load-allocation-tools", "Load Allocation Repair Tools"):
        return

    try:
        allocator = importlib.import_module("order_allocator")
        sync = get_shopify_sync()
        config = sync.get_config()
    except Exception as error:
        _developer_section_error("Allocation Repair Tools", error)
        return

    st.caption("Admin repair tools only. Orders remains a daily fulfilment page.")

    view_cols = st.columns(2)
    if view_cols[0].button("View allocation settings", key="developer-view-allocation-settings", use_container_width=True):
        try:
            st.session_state.developer_allocation_settings = allocator.load_cutover_state()
        except Exception as error:
            _developer_action_error("View allocation settings", error)
    if st.session_state.get("developer_allocation_settings"):
        st.json(st.session_state.developer_allocation_settings)

    if view_cols[1].button(
        "Re-capture product baselines",
        key="developer-recapture-allocation-baselines",
        disabled=not config.get("configured"),
        use_container_width=True,
    ):
        try:
            rows = _fetch_allocation_baseline_rows(sync, config)
            state = allocator.capture_product_baselines(rows)
            st.session_state.developer_allocation_settings = state
            st.success(f"Re-captured {state.get('captured_count') or 0} product baseline(s).")
        except Exception as error:
            _developer_action_error("Baseline capture", error)

    repair_cols = st.columns(2)
    if repair_cols[0].button(
        "Allocate Missing Recent Paid Orders",
        key="developer-allocate-missing-paid-orders",
        disabled=not config.get("configured"),
        use_container_width=True,
    ):
        try:
            orders = _fetch_recent_paid_shopify_orders(sync, config)
            result = allocator.process_shopify_orders_for_editions(
                orders,
                config=config,
                require_cutover=True,
            )
            st.success(
                f"Allocated {result.get('assignments_created') or 0} edition number(s) "
                f"across {result.get('processed_orders') or 0} recent paid order(s)."
            )
            if result.get("errors"):
                st.warning(f"{len(result.get('errors') or [])} order(s) need review.")
        except Exception as error:
            _developer_action_error("Recent paid order allocation", error)

    try:
        snapshot = allocator.load_orders_snapshot()
    except Exception as error:
        snapshot = {"rows": []}
        st.warning("Orders snapshot could not be loaded for historical backfill selection.")
        st.caption(f"{type(error).__name__}: {error}")
    candidates = _historical_backfill_candidates(snapshot.get("rows") or [])
    label_to_index = {_candidate_label(index, row): index for index, row in enumerate(candidates)}
    selected_labels = st.multiselect(
        "Historical backfill selected orders",
        list(label_to_index),
        key="developer-historical-backfill-selected-labels",
    )
    if repair_cols[1].button(
        "Historical Backfill Selected Orders",
        key="developer-historical-backfill-selected-orders",
        disabled=not config.get("configured") or not selected_labels,
        use_container_width=True,
    ):
        try:
            selected_rows = [candidates[label_to_index[label]] for label in selected_labels]
            result = allocator.historical_backfill_order_rows(selected_rows, config=config)
            st.success(f"Historical backfill assigned {result.get('assignments_created') or 0} selected row(s).")
            if result.get("errors"):
                st.warning(f"{len(result.get('errors') or [])} product group(s) need review.")
        except Exception as error:
            _developer_action_error("Historical backfill", error)

    st.divider()
    st.subheader("Known Missing Edition Repair")
    st.caption("Admin-only repair for the seven known paid order lines that were imported before editions were assigned.")
    known_cols = st.columns(2)
    if known_cols[0].button(
        "Preview Known Missing Edition Repair",
        key="developer-preview-known-missing-edition-repair",
        use_container_width=True,
    ):
        try:
            supabase = importlib.import_module("supabase_backend")
            st.session_state.developer_known_missing_edition_repair = supabase.preview_known_missing_edition_repair()
        except Exception as error:
            _developer_action_error("Preview known missing edition repair", error)
    if known_cols[1].button(
        "Apply Known Missing Edition Repair",
        key="developer-apply-known-missing-edition-repair",
        use_container_width=True,
    ):
        try:
            supabase = importlib.import_module("supabase_backend")
            result = supabase.apply_known_missing_edition_repair()
            st.session_state.developer_known_missing_edition_repair = result
            st.success(
                f"Applied {result.get('applied_rows') or 0} known edition repair(s); "
                f"skipped {result.get('skipped_rows') or 0}."
            )
            if result.get("errors"):
                st.warning(f"{len(result.get('errors') or [])} repair issue(s) need review.")
            _mark_orders_snapshot_for_reload()
        except Exception as error:
            _developer_action_error("Apply known missing edition repair", error)

    known_result = st.session_state.get("developer_known_missing_edition_repair")
    if known_result:
        summary = {
            key: known_result.get(key)
            for key in (
                "mode",
                "target_rows",
                "ready_rows",
                "already_assigned_correct",
                "blocked_rows",
                "applied_rows",
                "already_exists_consistent",
                "skipped_rows",
            )
            if key in known_result
        }
        st.json(summary)
        rows = known_result.get("preview_rows") or known_result.get("applied") or []
        if rows:
            st.dataframe(rows, hide_index=True, use_container_width=True)
        skipped = known_result.get("skipped") or []
        if skipped:
            with st.expander("Skipped known repair rows", expanded=False):
                st.dataframe(skipped, hide_index=True, use_container_width=True)
        counters = known_result.get("counter_updates") or []
        if counters:
            with st.expander("Counter updates", expanded=False):
                st.dataframe(counters, hide_index=True, use_container_width=True)

    st.divider()
    st.subheader("Manual Edition Override")
    st.caption(
        "Admin-only correction for one already allocated order row. Auto-allocation remains the default."
    )
    override_search = st.text_input(
        "Find allocated order row",
        value=st.session_state.get("developer-edition-override-search", ""),
        placeholder="#SC2843 or GOAT Debate",
        key="developer-edition-override-search",
    )
    override_cols = st.columns([1, 1])
    if override_cols[0].button(
        "Load Override Rows",
        key="developer-load-edition-override-rows",
        use_container_width=True,
    ):
        st.session_state.developer_edition_override_rows = _load_manual_override_rows(
            override_search,
            allocator,
            limit=80,
        )

    override_rows = st.session_state.get("developer_edition_override_rows") or []
    if override_rows:
        def _override_row_label(row):
            number = row.get("edition_number")
            edition = f"#{int(number):03d}" if str(number or "").isdigit() else "No edition"
            order_name = row.get("shopify_order_name") or row.get("order_name") or row.get("shopify_order_id") or ""
            customer = row.get("customer_name") or row.get("customer_email") or "Customer not shown"
            product = row.get("product_title") or row.get("shopify_handle") or ""
            variant = row.get("variant_title") or ""
            certificate = row.get("certificate_status") or "Certificate Missing"
            return f"{order_name} | {customer} | {product} | {variant} | {edition} | {certificate} | row {row.get('id')}"

        labels = [_override_row_label(row) for row in override_rows]
        selected_label = st.selectbox(
            "Allocated order row",
            labels,
            key="developer-edition-override-row-label",
        )
        selected_row = override_rows[labels.index(selected_label)]
        current_number = int(selected_row.get("edition_number") or 1)
        edition_total = max(int(selected_row.get("edition_total") or 100), 1)
        st.caption(
            f"Selected row ID {selected_row.get('id')} - current edition #{current_number:03d}/{edition_total}."
        )
        new_number = st.number_input(
            "New edition number",
            min_value=1,
            max_value=edition_total,
            value=min(max(current_number, 1), edition_total),
            step=1,
            key="developer-edition-override-new-number",
        )
        override_reason = st.text_input(
            "Override reason",
            value="Manual correction",
            key="developer-edition-override-reason",
        )
        action_cols = st.columns(3)
        if action_cols[0].button(
            "Override Edition",
            key="developer-override-edition-number",
            type="primary",
            use_container_width=True,
        ):
            try:
                supabase = importlib.import_module("supabase_backend")
                if supabase.is_configured() and (
                    str(selected_row.get("id") or "").startswith("snapshot|")
                    or selected_row.get("source") == "snapshot_allocation"
                ):
                    raise ValueError("Supabase is configured. Manual overrides must target Supabase ledger rows only.")
                if str(selected_row.get("id") or "").startswith("snapshot|") or selected_row.get("source") == "snapshot_allocation":
                    result = allocator.override_snapshot_allocation_row(
                        selected_row,
                        int(new_number),
                        reason=override_reason,
                        config=config,
                        sync_shopify=bool(config.get("configured")),
                    )
                else:
                    result = supabase.override_edition_order_number(
                        selected_row.get("id"),
                        int(new_number),
                        reason=override_reason,
                        config=config,
                        sync_shopify=bool(config.get("configured")),
                    )
                product = result.get("product") or {}
                st.success(
                    f"Overrode edition #{result.get('old_edition_number'):03d} "
                    f"to #{result.get('new_edition_number'):03d}. "
                    f"Next edition is #{int(product.get('next_edition_number') or 0):03d}."
                )
                if product.get("sold_out"):
                    st.warning("Product is sold out. Needs Review - Sold Out.")
                if result.get("shopify_mirror_status"):
                    st.caption(f"Shopify mirror {result.get('shopify_mirror_status')}")
                if result.get("warning"):
                    st.warning(result["warning"])
                _mark_orders_snapshot_for_reload()
                st.session_state.developer_edition_override_rows = _load_manual_override_rows(
                    override_search,
                    allocator,
                    limit=80,
                )
            except Exception as error:
                _developer_action_error("Override Edition", error)
        if action_cols[1].button(
            "Recalculate Next Edition Number",
            key="developer-recalculate-next-edition-number",
            use_container_width=True,
        ):
            try:
                if str(selected_row.get("id") or "").startswith("snapshot|") or selected_row.get("source") == "snapshot_allocation":
                    result = allocator.recalculate_snapshot_product_next_number(
                        selected_row,
                        sync_shopify=bool(config.get("configured")),
                        config=config,
                    )
                else:
                    supabase = importlib.import_module("supabase_backend")
                    result = supabase.recalculate_next_edition_number(
                        shopify_handle=selected_row.get("shopify_handle") or selected_row.get("product_handle") or "",
                        shopify_product_id=selected_row.get("shopify_product_id") or "",
                        sync_shopify=bool(config.get("configured")),
                        config=config,
                    )
                st.success(
                    f"Recalculated {result.get('shopify_handle')}: "
                    f"next edition #{int(result.get('next_edition_number') or 0):03d}."
                )
                if result.get("sold_out"):
                    st.warning("Product is sold out. Needs Review - Sold Out.")
                if result.get("warning"):
                    st.warning(result["warning"])
            except Exception as error:
                _developer_action_error("Recalculate Next Edition Number", error)
        if action_cols[2].button(
            "Retry Shopify Metafield Sync",
            key="developer-retry-shopify-product-metafield-sync",
            use_container_width=True,
        ):
            try:
                handle = selected_row.get("shopify_handle") or selected_row.get("product_handle") or ""
                if not handle:
                    raise ValueError("Selected row does not have a Shopify handle.")
                if str(selected_row.get("id") or "").startswith("snapshot|") or selected_row.get("source") == "snapshot_allocation":
                    result = allocator.recalculate_snapshot_product_next_number(
                        selected_row,
                        sync_shopify=bool(config.get("configured")),
                        config=config,
                    )
                    next_number = int(result.get("next_edition_number") or 0)
                else:
                    supabase = importlib.import_module("supabase_backend")
                    result = supabase.sync_product_edition_metafields(handle, config=config)
                    payload = result.get("payload") or {}
                    next_number = int(payload.get("next_edition_number") or 0)
                st.success(f"Retried Shopify metafield sync for {handle}: next edition #{next_number:03d}.")
                if result.get("warning"):
                    st.warning(result["warning"])
            except Exception as error:
                _developer_action_error("Retry Shopify Metafield Sync", error)


def _extract_toml_scopes(text):
    match = re.search(r'^\s*scopes\s*=\s*"([^"]*)"', text or "", flags=re.MULTILINE)
    if not match:
        return set()
    return {scope.strip() for scope in match.group(1).split(",") if scope.strip()}


def _customer_certificate_vault_config_status():
    app_config = BASE_DIR / "shopify_customer_account" / "shopify.app.toml"
    extension_config = (
        BASE_DIR
        / "shopify_customer_account"
        / "extensions"
        / "customer-certificate-vault"
        / "shopify.extension.toml"
    )
    extension_source = (
        BASE_DIR
        / "shopify_customer_account"
        / "extensions"
        / "customer-certificate-vault"
        / "src"
        / "MySportsCaveCollection.jsx"
    )
    app_text = ""
    extension_text = ""
    source_text = ""
    with suppress(Exception):
        app_text = app_config.read_text(encoding="utf-8")
    with suppress(Exception):
        extension_text = extension_config.read_text(encoding="utf-8")
    with suppress(Exception):
        source_text = extension_source.read_text(encoding="utf-8")
    scopes = _extract_toml_scopes(app_text)
    return {
        "customer_read_customers": "customer_read_customers" in scopes,
        "customer_read_orders": "customer_read_orders" in scopes,
        "api_access": bool(re.search(r"^\s*api_access\s*=\s*true\s*$", extension_text, flags=re.MULTILINE)),
        "network_access": bool(re.search(r"^\s*network_access\s*=\s*true\s*$", extension_text, flags=re.MULTILINE)),
        "uses_external_endpoint": "fetch(\"http" in source_text or "fetch('http" in source_text,
    }


def render_settings_page():
    if not _developer_unlocked():
        _render_developer_password_gate()
        return

    st.title("Developer")
    st.caption("Protected setup tools. Diagnostics run only when you click a button.")
    lock_cols = st.columns([1, 3])
    if lock_cols[0].button("Lock Developer", use_container_width=True):
        st.session_state.developer_unlocked = False
        st.rerun()
    lock_cols[1].caption("No store, database, Drive, or storage calls run just by opening this page.")

    with st.expander("Basic App Info", expanded=True):
        st.write(f"**App version:** {APP_VERSION}")
        st.write(f"**App password protection:** {get_password_protection_status()}")
        st.write(f"**Developer password env override:** {'Set' if os.getenv('DEVELOPER_PAGE_PASSWORD') else 'Using MVP default'}")
        st.write(f"**Output folder path:** `{RUNS_DIR}`")
        st.write(f"**Python working directory:** `{Path.cwd()}`")

    with st.expander("Edition Ops Diagnostics", expanded=False):
        try:
            if _developer_section_enabled("developer-load-edition-ops-diagnostics", "Load Edition Ops Diagnostics"):
                supabase = importlib.import_module("supabase_backend")
                status = supabase.database_status(run_schema_check=False)
                counts = supabase.persistence_counts() if status.get("configured") else {}
                st.write(f"**Connection:** {'Connected' if status.get('connected') else 'Not connected'}")
                st.write("**Source:** Supabase ledger")
                if status.get("warning"):
                    st.caption(status.get("warning"))
                for label, key in (
                    ("edition_products", "edition_products"),
                    ("edition_orders", "edition_orders"),
                    ("audit_logs", "audit_logs"),
                ):
                    st.write(f"**{label}:** {int(counts.get(key) or 0)}")
        except Exception as error:
            _developer_section_error("Edition Ops Diagnostics", error)

    with st.expander("Shopify Connection", expanded=False):
        try:
            if _developer_section_enabled("developer-load-shopify-connection", "Load Shopify Connection Tools"):
                sync = get_shopify_sync()
                config = sync.get_config()
                st.write(f"**Configured:** {'Yes' if config.get('configured') else 'No'}")
                st.write(f"**Store domain present:** {'Yes' if bool(config.get('store_domain')) else 'No'}")
                st.write(f"**API version:** {config.get('api_version') or 'Missing'}")
                st.write(f"**Auth mode:** {config.get('auth_mode') or 'Missing'}")
                if st.button(
                    "Test Shopify Connection",
                    key="developer-test-shopify-connection",
                    disabled=not config.get("configured"),
                    use_container_width=True,
                ):
                    try:
                        result = sync.test_connection(config=config)
                        st.success(f"Connection OK: {result.get('name') or 'store found'}")
                    except Exception as error:
                        st.error("Connection test failed.")
                        st.caption(f"{type(error).__name__}: {error}")
        except Exception as error:
            _developer_section_error("Shopify Connection", error)

    with st.expander("Ads Intelligence Diagnostics", expanded=False):
        try:
            if _developer_section_enabled("developer-load-ads-intelligence-diagnostics", "Load Ads Intelligence Diagnostics"):
                meta = importlib.import_module("meta_ads_client")
                supabase = importlib.import_module("supabase_backend")
                config_status = meta.safe_meta_config_status()
                counts = supabase.ads_table_counts()
                product_mapping_diagnostics = supabase.ads_product_mapping_diagnostics()
                sync_logs = supabase.list_ads_sync_logs(limit=50)
                action_logs = supabase.list_ads_action_log(limit=50, action_type="meta_sync")
                mapping_action_logs = supabase.list_ads_action_log(limit=50, action_type="product_mapping")
                st.write(f"**META_AD_ACCOUNT_ID present:** {'Yes' if config_status.get('ad_account_id_present') else 'No'}")
                st.write(f"**META_ACCESS_TOKEN present:** {'Yes' if config_status.get('token_present') else 'No'}")
                st.write(f"**META_APP_ID present:** {'Yes' if config_status.get('app_id_present') else 'No'}")
                st.write(f"**META_APP_SECRET present:** {'Yes' if config_status.get('app_secret_present') else 'No'}")
                st.write(f"**META_API_VERSION:** {config_status.get('api_version') or 'Missing'}")
                st.caption("Secret values are intentionally never shown.")
                st.write("**Ads table counts**")
                st.dataframe(
                    [{"Table": table, "Rows": count} for table, count in counts.items()],
                    hide_index=True,
                    use_container_width=True,
                )
                st.write("**Product mapping diagnostics**")
                st.dataframe(
                    [{"Metric": key, "Value": value} for key, value in product_mapping_diagnostics.items()],
                    hide_index=True,
                    use_container_width=True,
                )
                st.write("**Latest sync logs**")
                if sync_logs:
                    st.dataframe(
                        [
                            {
                                "started_at": row.get("started_at"),
                                "finished_at": row.get("finished_at"),
                                "status": row.get("status"),
                                "sync_type": row.get("sync_type"),
                                "date_range": row.get("date_range"),
                                "rows_fetched": row.get("rows_fetched"),
                                "rows_upserted": row.get("rows_upserted"),
                                "error_message": row.get("error_message") or "",
                                "context": row.get("context") or {},
                            }
                            for row in sync_logs
                        ],
                        hide_index=True,
                        use_container_width=True,
                    )
                else:
                    st.caption("No ads sync logs found.")
                st.write("**Latest meta_sync action log rows**")
                if action_logs:
                    st.dataframe(
                        [
                            {
                                "created_at": row.get("created_at"),
                                "status": row.get("status"),
                                "summary": row.get("summary"),
                                "context": row.get("context") or {},
                            }
                            for row in action_logs
                        ],
                        hide_index=True,
                        use_container_width=True,
                    )
                else:
                    st.caption("No meta_sync action rows found.")
                st.write("**Latest product mapping action log rows**")
                if mapping_action_logs:
                    st.dataframe(
                        [
                            {
                                "created_at": row.get("created_at"),
                                "status": row.get("status"),
                                "summary": row.get("summary"),
                                "context": row.get("context") or {},
                            }
                            for row in mapping_action_logs
                        ],
                        hide_index=True,
                        use_container_width=True,
                    )
                else:
                    st.caption("No product_mapping action rows found.")
                last_error = next((row.get("error_message") for row in sync_logs if row.get("error_message")), "")
                if last_error:
                    st.write("**Last sanitized Meta error**")
                    st.code(str(last_error), language="text")
        except Exception as error:
            _developer_section_error("Ads Intelligence Diagnostics", error)

    with st.expander("Shopify Limited Edition Setup", expanded=False):
        try:
            if _developer_section_enabled("developer-load-limited-edition-setup", "Load Limited Edition Setup"):
                sync = get_shopify_sync()
                config = sync.get_config()
                setup_cols = st.columns(2)
                if setup_cols[0].button(
                    "Check Product Metafield Definitions",
                    key="developer-check-product-metafields",
                    disabled=not config.get("configured"),
                    use_container_width=True,
                ):
                    try:
                        st.session_state.developer_product_metafields = sync.list_edition_ops_metafield_definitions(
                            config=config
                        )
                    except Exception as error:
                        st.error("Product metafield check failed.")
                        st.caption(f"{type(error).__name__}: {error}")
                if setup_cols[1].button(
                    "Create Missing Product Metafield Definitions",
                    key="developer-create-product-metafields",
                    disabled=not config.get("configured"),
                    use_container_width=True,
                ):
                    try:
                        st.session_state.developer_product_metafields = sync.create_missing_edition_ops_metafield_definitions(
                            config=config
                        )
                        st.success("Product metafield setup checked.")
                    except Exception as error:
                        st.error("Product metafield setup failed.")
                        st.caption(f"{type(error).__name__}: {error}")
                definitions = (st.session_state.get("developer_product_metafields") or {}).get("definitions") or []
                if definitions:
                    st.dataframe(
                        [
                            {
                                "Key": item.get("key"),
                                "Type": item.get("type"),
                                "Status": item.get("status") or item.get("message") or "",
                            }
                            for item in definitions
                        ],
                        hide_index=True,
                        use_container_width=True,
                    )
        except Exception as error:
            _developer_section_error("Shopify Limited Edition Setup", error)

    with st.expander("Shopify Webhook Setup", expanded=False):
        st.write("**Paid orders webhook endpoint:** `/webhooks/shopify/orders-paid`")
        st.write(f"**Webhook secret configured:** {'Yes' if bool(os.getenv('SHOPIFY_WEBHOOK_SECRET', '').strip()) else 'No'}")
        try:
            sync = get_shopify_sync()
            config = sync.get_config()
            callback_url = sync.orders_paid_webhook_callback_url()
            st.write(f"**Public callback URL:** `{callback_url or 'Not configured'}`")
            if st.button(
                "Register / Verify Orders Paid Webhook",
                key="developer-register-orders-paid-webhook",
                disabled=not bool(config.get("configured")),
                use_container_width=True,
            ):
                result = sync.ensure_orders_paid_webhook_subscription(config=config)
                subscription = result.get("subscription") or {}
                status = "created" if result.get("created") else "already registered"
                st.success(
                    f"orders/paid webhook {status}: {subscription.get('id') or result.get('callback_url')}"
                )
        except Exception as error:
            _developer_section_error("Shopify Webhook Setup", error)
        st.caption(
            "The lightweight webhook wrapper is available in server.py. "
            "Render free uses direct Streamlit startup to stay under the 512MB memory limit."
        )

    with st.expander("Allocation Repair Tools", expanded=False):
        try:
            _render_developer_allocation_tools()
        except Exception as error:
            _developer_section_error("Allocation Repair Tools", error)

    with st.expander("Order Metafield Setup", expanded=False):
        try:
            if _developer_section_enabled("developer-load-order-metafields", "Load Order Metafield Tools"):
                sync = get_shopify_sync()
                config = sync.get_config()
                order_cols = st.columns(2)
                if order_cols[0].button(
                    "Check Order Metafield Definition",
                    key="developer-check-order-metafields",
                    disabled=not config.get("configured"),
                    use_container_width=True,
                ):
                    try:
                        st.session_state.developer_order_metafields = sync.list_order_allocation_metafield_definitions(
                            config=config
                        )
                    except Exception as error:
                        st.error("Order metafield check failed.")
                        st.caption(f"{type(error).__name__}: {error}")
                if order_cols[1].button(
                    "Create Missing Order Metafield Definition",
                    key="developer-create-order-metafields",
                    disabled=not config.get("configured"),
                    use_container_width=True,
                ):
                    try:
                        st.session_state.developer_order_metafields = sync.create_missing_order_allocation_metafield_definitions(
                            config=config
                        )
                        st.success("Order metafield setup checked.")
                    except Exception as error:
                        st.error("Order metafield setup failed.")
                        st.caption(f"{type(error).__name__}: {error}")
                definitions = (st.session_state.get("developer_order_metafields") or {}).get("definitions") or []
                if definitions:
                    st.dataframe(
                        [
                            {
                                "Key": item.get("key"),
                                "Type": item.get("type"),
                                "Status": item.get("status") or item.get("message") or "",
                            }
                            for item in definitions
                        ],
                        hide_index=True,
                        use_container_width=True,
                    )
        except Exception as error:
            _developer_section_error("Order Metafield Setup", error)

    with st.expander("Certificate Templates", expanded=False):
        try:
            if _developer_section_enabled("developer-load-certificate-template-check", "Check Certificate Templates"):
                certificates = importlib.import_module("certificate_service")
                status = certificates.certificate_template_status()
                st.write(f"**Certificate print template:** {'Found' if status['print_template_found'] else 'Missing'}")
                st.caption(status["print_template_path"])
                st.write(f"**Certificate preview template:** {'Found' if status['preview_template_found'] else 'Missing'}")
                st.caption(status["preview_template_path"])
        except Exception as error:
            _developer_section_error("Certificate Templates", error)

    with st.expander("Certificate Metadata", expanded=False):
        st.caption(
            "Repairs Shopify order certificate metafields for ready certificates. "
            "Runs only when clicked and never generates certificates."
        )
        vault_status = _customer_certificate_vault_config_status()
        st.write("**Customer Certificate Vault**")
        st.write(f"**customer_read_customers configured:** {'Yes' if vault_status['customer_read_customers'] else 'No'}")
        st.write(f"**customer_read_orders configured:** {'Yes' if vault_status['customer_read_orders'] else 'No'}")
        st.write(f"**Customer extension api_access enabled:** {'Yes' if vault_status['api_access'] else 'No'}")
        st.write(
            f"**Customer extension network_access enabled:** "
            f"{'Yes' if vault_status['network_access'] else 'No'}"
            f"{' (not needed)' if not vault_status['uses_external_endpoint'] else ''}"
        )
        cert_sync_cols = st.columns(2)
        single_sync_value = cert_sync_cols[0].text_input(
            "Sync Certificate to Shopify",
            value="",
            placeholder="#SC2847, order GID, or certificate ID",
            key="developer-sync-single-certificate-to-shopify",
        )
        if cert_sync_cols[1].button(
            "Sync Certificate to Shopify",
            key="developer-sync-single-certificate-button",
            use_container_width=True,
        ):
            try:
                sync = get_shopify_sync()
                config = sync.get_config()
                if not config.get("configured"):
                    st.warning("Shopify is not configured. Certificate metafields were not pushed.")
                else:
                    supabase = importlib.import_module("supabase_backend")
                    result = supabase.sync_certificate_to_shopify(single_sync_value, config=config)
                    if result.get("skipped"):
                        st.warning(result.get("reason") or "No certificate was synced.")
                    elif result.get("failed"):
                        st.warning(f"{result.get('failed')} certificate sync attempt(s) failed.")
                    else:
                        st.success(f"Synced {result.get('synced') or 0} Shopify order certificate metafield set(s).")
                    for error in result.get("errors") or []:
                        st.caption(error)
            except Exception as error:
                _developer_action_error("Sync Certificate to Shopify", error)
        asset_cols = st.columns(2)
        if asset_cols[0].button("Generate Missing Assets", key="developer-generate-missing-certificate-assets", use_container_width=True):
            try:
                sync = get_shopify_sync()
                config = sync.get_config()
                if not config.get("configured"):
                    st.warning("Shopify is not configured. Certificate assets were not generated/uploaded.")
                else:
                    certificate_engine = importlib.import_module("certificate_engine")
                    result = certificate_engine.generate_missing_certificate_assets_for_recent_orders(
                        config=config,
                        max_orders=100,
                    )
                    st.success(
                        f"Certificate asset generation complete: {result.get('generated') or 0} certificate(s) updated."
                    )
                    if result.get("errors"):
                        st.warning(f"{len(result.get('errors') or [])} asset generation/upload issue(s) need review.")
            except Exception as error:
                _developer_action_error("Generate Missing Assets", error)
        if asset_cols[1].button("Sync Certificate Assets to Shopify", key="developer-sync-unsynced-certificates", use_container_width=True):
            try:
                sync = get_shopify_sync()
                config = sync.get_config()
                if not config.get("configured"):
                    st.warning("Shopify is not configured. Certificate metafields were not pushed.")
                else:
                    supabase = importlib.import_module("supabase_backend")
                    result = supabase.backfill_ready_certificate_order_metafields(
                        config=config,
                        only_unsynced=True,
                        limit=250,
                    )
                    st.success(
                        f"Certificate asset sync complete: {result.get('synced') or 0} order(s) synced."
                    )
                    if result.get("failed"):
                        st.warning(f"{result.get('failed')} certificate metafield push(es) still need review.")
            except Exception as error:
                _developer_action_error("Sync Unsynced Certificates", error)
        if st.button("Load Customer Certificate Vault Diagnostics", key="developer-load-customer-vault-diagnostics", use_container_width=True):
            try:
                supabase = importlib.import_module("supabase_backend")
                diagnostics = supabase.certificate_vault_diagnostics()
                st.write(f"**Supabase configured:** {'Yes' if diagnostics.get('configured') else 'No'}")
                st.write(f"**Certificates generated count:** {diagnostics.get('certificates_generated_count') or 0}")
                st.write(f"**Certificates synced to Shopify count:** {diagnostics.get('certificates_synced_to_shopify_count') or 0}")
                st.write(f"**Unsynced certificate count:** {diagnostics.get('unsynced_certificate_count') or 0}")
                st.write(f"**PDF ready:** {diagnostics.get('pdf_ready_count') or 0}")
                st.write(f"**Print JPG ready:** {diagnostics.get('print_jpg_ready_count') or 0}")
                st.write(f"**Preview ready:** {diagnostics.get('preview_ready_count') or 0}")
                st.write(f"**Missing print JPG:** {diagnostics.get('missing_print_jpg_count') or 0}")
                st.write(f"**Missing preview:** {diagnostics.get('missing_preview_count') or 0}")
                st.write(
                    f"**Last Shopify order metafield sync status:** "
                    f"{diagnostics.get('last_shopify_order_metafield_sync_status') or 'None'}"
                )
                if diagnostics.get("last_sync_error"):
                    st.caption(f"Last sync error: {diagnostics.get('last_sync_error')}")
            except Exception as error:
                _developer_action_error("Customer Certificate Vault diagnostics", error)
        if st.button("Retry Certificate Metafield Push", key="developer-retry-certificate-metafield-push", use_container_width=True):
            try:
                sync = get_shopify_sync()
                config = sync.get_config()
                if not config.get("configured"):
                    st.warning("Shopify is not configured. Certificate metafields were not pushed.")
                else:
                    certificate_engine = importlib.import_module("certificate_engine")
                    allocator = importlib.import_module("order_allocator")
                    snapshot = allocator.load_orders_snapshot()
                    snapshot_result = certificate_engine.retry_certificate_metafield_push_for_rows(
                        snapshot.get("rows") or [],
                        config=config,
                    )
                    supabase_result = {"attempted": 0, "synced": 0, "failed": 0, "skipped": True}
                    try:
                        supabase = importlib.import_module("supabase_backend")
                        if supabase.is_configured():
                            supabase_result = supabase.backfill_ready_certificate_order_metafields(config=config)
                    except Exception as supabase_error:
                        _developer_action_error("Supabase certificate metadata backfill", supabase_error)
                    st.success(
                        "Certificate metafield retry complete: "
                        f"{snapshot_result.get('synced') or 0} snapshot row(s) synced, "
                        f"{supabase_result.get('synced') or 0} Supabase order(s) synced."
                    )
                    total_failed = int(snapshot_result.get("failed") or 0) + int(supabase_result.get("failed") or 0)
                    if total_failed:
                        st.warning(f"{total_failed} certificate metafield push(es) still need review.")
            except Exception as error:
                _developer_action_error("Certificate metafield retry", error)

    with st.expander("Database / Supabase", expanded=False):
        st.write(f"**DATABASE_URL present:** {'Yes' if any(os.getenv(key, '').strip() for key in DATABASE_URL_ENV_KEYS) else 'No'}")
        if st.button("Run Database Connection Test", key="developer-test-database", use_container_width=True):
            try:
                supabase_backend = importlib.import_module("supabase_backend")
                result = supabase_backend.test_connection()
                st.success("Database connection OK.")
                st.caption(f"Server time: {result.get('server_time')}")
            except Exception as error:
                _developer_action_error("Database connection test", error)
        if st.button("Run DB Health / Repair", key="developer-db-health-repair", use_container_width=True):
            try:
                supabase_backend = importlib.import_module("supabase_backend")
                result = supabase_backend.run_db_health_repair()
                st.success("DB health / repair completed.")
                st.caption(f"Duration: {result.get('duration_ms')} ms")
                st.caption(f"Active-run rows touched: {result.get('active_run_rows_touched')}")
            except Exception as error:
                _developer_action_error("DB Health / Repair", error)

    with st.expander("Google Drive / R2", expanded=False):
        st.write(f"**Google Drive lightweight flag:** {'Enabled' if ENABLE_GOOGLE_DRIVE else 'Disabled'}")
        st.write(f"**OAuth client ID present:** {'Yes' if os.getenv('GOOGLE_OAUTH_CLIENT_ID') else 'No'}")
        st.write(f"**OAuth refresh token present:** {'Yes' if os.getenv('GOOGLE_OAUTH_REFRESH_TOKEN') else 'No'}")
        st.write(f"**R2 endpoint present:** {'Yes' if os.getenv('R2_ENDPOINT_URL') else 'No'}")
        if st.button("Load R2 Status", key="developer-load-r2-status", use_container_width=True):
            try:
                r2_storage = importlib.import_module("services.r2_storage")
                st.json(r2_storage.get_r2_status())
            except Exception as error:
                _developer_action_error("R2 status", error)

    with st.expander("Diagnostics", expanded=False):
        st.caption("These checks import heavier modules only after you click.")
        diag_cols = st.columns(2)
        if diag_cols[0].button("Load Legacy Diagnostics Module", key="developer-load-legacy-pages", use_container_width=True):
            try:
                get_os_pages()
                st.success("Legacy diagnostics module imported.")
            except Exception as error:
                _developer_action_error("Legacy diagnostics import", error)
        if diag_cols[1].button("Load Local DB Module", key="developer-load-local-db", use_container_width=True):
            try:
                local_db = get_db()
                st.success(f"Local DB module loaded: `{local_db.DB_PATH}`")
            except Exception as error:
                _developer_action_error("Local DB import", error)


def render_placeholder_page(title, body):
    st.title(title)
    st.caption(body)


def render_lightweight_dashboard_page():
    started = time.perf_counter()
    st.title("Sports Cave OS")
    st.caption("Lightweight command screen for the Edition Ops MVP.")
    with st.container(border=True):
        st.markdown("**Today**")
        st.caption(
            "Open Edition Ops only when product edition fields need configuration."
        )

    st.subheader("Today's Focus")
    focus_columns = st.columns(3)
    with focus_columns[0]:
        st.info("Use Edition Ops to refresh active products only when you need to edit edition fields.")
    with focus_columns[1]:
        st.info("Orders use a saved snapshot first. Refresh only when you need current store data.")
    with focus_columns[2]:
        st.info("Use Mockups only when artwork is ready. Keep generated ZIPs saved in the right Drive folder.")

    st.subheader("Edition Data")
    st.write(
        "Product edition fields are the source of truth for edition display data. This dashboard does not fetch store data, "
        "Supabase, orders, certificates, Google Drive, CSV files, or product sync data."
    )
    st.caption("Advanced legacy tools stay separate from this MVP flow.")
    safe_startup_print(f"PERF Dashboard total={(time.perf_counter() - started):.3f}s")


def page_uses_local_database(current_page):
    if current_page in {"Dashboard", "Products", "Edition Ops", "Orders", "Developer", "Settings"}:
        return False
    supabase_enabled = any(os.getenv(key, "").strip() for key in DATABASE_URL_ENV_KEYS)
    if current_page in {"Files"}:
        return True
    if not supabase_enabled and current_page in {
        "Products",
    }:
        return True
    return False


def render_selected_page(current_page):
    def os_route_pages():
        import_started = time.perf_counter()
        pages = get_os_pages()
        safe_startup_print(
            f"PERF route selected={current_page} import={(time.perf_counter() - import_started):.3f}s"
        )
        return pages

    if current_page == "Dashboard":
        render_lightweight_dashboard_page()
    elif current_page == "Products":
        render_placeholder_page("Products", "Full product sync is paused. Use Edition Ops for product edition fields.")
    elif current_page == "Mockups":
        render_mockups_page()
    elif current_page == "Edition Ops":
        get_edition_ops().render_page()
    elif current_page == "Orders":
        get_orders_page().render_page()
    elif current_page == "Product Assets":
        os_route_pages().render_product_assets_page()
    elif current_page == "Prodigi":
        os_route_pages().render_prodigi_page()
    elif current_page == "Ads Intelligence":
        if not _developer_unlocked():
            _render_developer_password_gate(
                title="Admin access required.",
                caption="Unlock Developer access to open Ads Intelligence.",
            )
        else:
            get_ads_intelligence_page().render_page()
    elif current_page == "Webhook Events":
        os_route_pages().render_webhook_events_page()
    elif current_page == "Sync Runs":
        os_route_pages().render_sync_runs_page()
    elif current_page == "App Errors":
        os_route_pages().render_app_errors_page()
    elif current_page == "Persistence Check":
        os_route_pages().render_persistence_check_page()
    elif current_page == "Product Uploads":
        render_product_uploads_page()
    elif current_page == "Files":
        os_route_pages().render_files_page()
    elif current_page == "Marketing Factory":
        os_route_pages().render_marketing_factory_page()
    elif current_page in {"Settings", "Developer"}:
        render_settings_page()
    else:
        os_route_pages().render_placeholder_page(current_page)


def main():
    init_session_state()
    inject_styles()
    log_startup_stage("CSS LOADED")

    log_startup_stage("SIDEBAR START")
    render_sidebar()
    log_startup_stage("SIDEBAR DONE")

    log_startup_stage("ROUTER START")
    current_page = st.session_state.selected_page
    log_startup_stage(f"PAGE SELECTED: {current_page}")
    log_app_memory(f"Page load start: {current_page}")

    if page_uses_local_database(current_page):
        log_startup_stage("LOCAL DB INIT START")
        get_db().init_db()
        log_startup_stage("LOCAL DB INIT DONE")

    log_startup_stage("PAGE RENDER START", current_page)
    try:
        render_selected_page(current_page)
    except Exception as error:
        error_message = f"Page render failed for {current_page}: {error}"
        print(f"ERROR {error_message}", flush=True)
        logging.exception(error_message)
        st.error("This page failed to load, but Sports Cave OS is still running.")
        st.exception(error)
    log_startup_stage("PAGE RENDER DONE", current_page)
    log_app_memory(f"Page load end: {current_page}")


main()
