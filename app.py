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

from PIL import Image, ImageOps, UnidentifiedImageError
from dotenv import load_dotenv
import requests
import streamlit as st
import streamlit.components.v1 as components

db = None
image_factory = None
os_pages = None
shopify_sync = None
edition_ops_module = None
orders_page_module = None


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
MENU_OPTIONS = [
    "Dashboard",
    "Mockups",
    "Product Uploads",
    "Edition Ops",
    "Orders",
    "Prodigi",
    "Files",
    "Marketing Factory",
    "VA Training",
    "Developer",
]
HIDDEN_PAGE_OPTIONS = [
    "Products",
    "Product Assets",
    "Certificates",
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
Direct Draft Product Upload Version — No CSV Import Required
Goal
Create a complete new Sports Cave Shopify product directly through ChatGPT using the connected Shopify tool.
This SOP replaces the old CSV import workflow for new product uploads.
ChatGPT must:
Create the Shopify product as a Draft
Upload all supplied final WebP product images to Shopify
Use those Shopify-uploaded images in the product gallery
Create all required variants
Set pricing and compare-at pricing
Assign variant images correctly
Write the product description in the correct Sports Cave style
Create SEO meta title and meta description for maximum organic search value
Write unique image alt text for every image
Add clean tags for automated collections
Leave the product unpublished until manually approved
No CSV import is required.
No manual Shopify image upload is required.
No product should be published automatically.

Brutal Rule
Never publish a new product automatically.
Every new Sports Cave product must be created as:
Status: Draft
Published: false
The product must only be published after the final manual review confirms:
Images are correct
Product title is correct
Description feels premium
Variants are correct
Prices are correct
Variant image mapping is correct
SEO fields are complete
Tags are clean
Mobile preview looks strong
Product feels ready to sell

Required Uploads
Before running this SOP, upload all final approved WebP product images.
Images should already be:
Final production assets
Optimised WebP files
Correctly cropped
Correctly sized
Visually approved
Ready for Shopify upload
Do not ask ChatGPT to redesign, edit, crop, stylise, resize, relight, or change any product image during this SOP.
This SOP is for Shopify product creation only.

Required Product Inputs
Along with the WebP images, provide as much of the following as possible:
Product subject
Example: Greg Murphy, Cristiano Ronaldo, Arsenal, Shane Warne
Sport or category
Example: Motorsport, Football, NBA, Cricket, Boxing, Tennis
Athlete, team, rivalry, or moment
Example: Bathurst 2003 Lap of the Gods, Manchester United years, Arsenal title charge
Product title idea if already chosen
Optional
Collection/category if known
Example: Motor Racing Wall Art, Football Wall Art, NBA Wall Art
Any required wording that must appear in the product description
Optional
Any wording that must not appear
Optional
If the uploaded images make the product subject obvious, ChatGPT may infer the subject and create the product copy from the visuals.
If the subject is unclear, ChatGPT must ask before creating the Shopify draft.

Shopify Product Creation Rule
ChatGPT must create the product directly in Shopify using the connected Shopify tool.
The product must be created as a draft first.
Default Shopify product fields:
Vendor: Sports Cave
Product type: Framed Art
Status: Draft
Published: false
Gift card: false
Requires shipping: true
Taxable: true
Condition: New
Product category: Home & Garden > Decor > Artwork > Posters, Prints & Visual Artwork
If Shopify rejects or does not support a category/taxonomy field through the connector, leave that field blank and continue. Do not guess controlled Shopify metafield values.

High-Risk Shopify Metafield Rule
Do not fill Shopify-controlled category metafields unless Shopify provides safe accepted values.
Leave the following blank unless the value is confirmed inside Shopify:
Art movement
Art style
Artwork authenticity
Artwork frame material
Colour
Condition metafields
Frame style
Material
Orientation
Painting medium
Print edition type
Rarity
Signature placement
Sports logo
Suitable space
Theme
Printing method
Do not invent values such as:
Modernism
Reproduction
Horizontal
Limited edition
Paper
Wood
Black
Gold
Framed
Sports
These may look correct but can break Shopify category validation.
Default action:
Leave Shopify taxonomy metafields blank unless safely accepted by Shopify.

Product Title Rules
Create a short, premium, SEO-friendly product title.
Rules:
Must include Wall Art
Maximum 10 words where possible
Clear subject first
No cheap marketplace-style wording
No keyword stuffing
No “poster print canvas home decor gift” style titles
Good examples:
Greg Murphy Bathurst Wall Art
Cristiano Ronaldo Manchester United Wall Art
Arsenal The Wait Is Over Wall Art
Shane Warne MCG Wall Art
Kobe Bryant Lakers Wall Art
Lionel Messi World Cup Wall Art
Peter Brock Bathurst Wall Art
Bad examples:
Premium Limited Edition Sports Poster Print Wall Decor Gift
New Framed Motorsport Poster For Man Cave
Cool Racing Car Sports Artwork Canvas Print
The title should feel premium, clean, and collectible.

Shopify Handle Rules
Create a lowercase, hyphenated Shopify handle.
Rules:
Lowercase only
Hyphens only
Short and clean
Include main subject and Wall Art
No filler words
No “limited-edition-premium-poster-print” clutter
Good examples:
greg-murphy-bathurst-wall-art
cristiano-ronaldo-manchester-united-wall-art
arsenal-the-wait-is-over-wall-art
shane-warne-mcg-wall-art

Product Description Rules
The product description must follow the Sports Cave emotional collector style.
It must be:
Short
Emotional
Nostalgic
Identity-driven
Collector-focused
Built for mobile reading
Written like a premium sports tribute, not a product listing
The buyer should read it and think:
“That’s me. I remember that. I need this.”

Description Length
Preferred length:
65–105 words
Maximum:
125 words
Do not over-explain.

Description HTML Rules
Use clean Shopify-safe HTML only.
Allowed:
<p>
<strong>
<br>
<em>
Do not use:
<div>
<section>
inline CSS
classes
tables
bullet lists
emoji
data-start
data-end

Words To Avoid In The Visible Description
In the visible product description body, avoid these words where possible:
art
artwork
poster
product
wall decor
print
Use these instead:
edition
limited edition
collector edition
piece
release
tribute
moment
frame
legacy
drop
SEO keywords can still be used in the SEO title, SEO description, product title, tags, and image alt text.
The visible description should sell emotion first.

Sports Cave Description Structure
Every product description must follow this structure:

1. Emotional Hook
One or two short lines.
Examples:
<p><strong>Some moments don’t fade.</strong><br>They live on the wall.</p>

<p><strong>Before the trophies, there was the hunger.</strong></p>

<p><strong>This wasn’t just a game.</strong><br>It was the moment everything changed.</strong></p>
The hook should feel like Nike meets sports nostalgia.
Short. Sharp. Emotional.

2. Nostalgia Trigger
Bring the fan back to the moment, era, shirt, stadium, rivalry, roar, colour, car, track, or pressure.
Examples:
<p>The roar. The colours. The rivalry. That split-second every real fan still remembers.</p>

<p>The shirt. The number. The stadium under lights. A whole era in one frame.</p>

<p>The mountain. The engine note. The lap that still gets talked about like folklore.</p>
This section should make the fan feel the memory.

3. Identity Line
Tell the buyer who this is for.
Examples:
<p>Built for fans who were there in spirit, even if they watched from the couch.</p>

<p>Made for the ones who still talk about that night.</p>

<p>For the collector who knows this meant more than a scoreline.</p>
The buyer must feel seen.

4. Scarcity Close
Short, direct, urgent.
Examples:
<p><strong>Only 100 made. Secure yours before it’s gone.</strong></p>

<p><strong>Numbered edition. Once they’re gone, they’re gone.</strong></p>

<p><strong>A collector’s piece for real fans. Don’t miss this drop.</strong></p>
No long urgency paragraphs.
No fake hype.
No over-selling.

Final Description Format
Use this structure:
<p><strong>[Short emotional hook.]</strong><br>[Optional second punch line.]</p>
<p>[Nostalgia trigger: 2–4 short sentences tied to the sport, athlete, rivalry, era, stadium, car, track, shirt, or moment.]</p>
<p>[Identity line for the true fan or collector.]</p>
<p><strong>[Scarcity close.]</strong></p>

Description Style Examples
Motorsport Example
<p><strong>Some laps become legend.</strong><br>This was one of them.</p>
<p>The mountain. The pressure. The engine note echoing through Bathurst. One lap, no room for fear, and a moment that still gives real racing fans chills.</p>
<p>Made for the ones who remember when motorsport felt raw, loud, and untouchable.</p>
<p><strong>Only 100 made. Secure yours before it’s gone.</strong></p>
Football Example
<p><strong>Before the records, there was the obsession.</strong><br>Old Trafford felt it first.</p>
<p>The red shirt. The number seven. The stepovers. The stare. Those European nights when defenders knew what was coming — and still couldn’t stop it.</p>
<p>Built for fans who remember the rise before the world called him inevitable.</p>
<p><strong>Only 100 made. Secure yours before this edition disappears.</strong></p>
NBA Example
<p><strong>Some players change the game.</strong><br>Others become the standard.</p>
<p>The footwork. The stare. The final shot. Every era has stars, but only a few leave a mark that never fades.</p>
<p>For the fans who still measure greatness against the legends.</p>
<p><strong>Numbered edition. Once they’re gone, they’re gone.</strong></p>
Cricket Example
<p><strong>Some spells never leave the memory.</strong><br>They echo through summer forever.</p>
<p>The white zinc. The packed stands. The pause before the ball ripped sideways. Real cricket fans know exactly what that felt like.</p>
<p>Made for the ones who still talk about legends like they watched them yesterday.</p>
<p><strong>Only 100 made. Secure yours before it’s gone.</strong></p>

SEO Meta Tag Rules
SEO must be built for maximum organic reach while still sounding premium.
The goal is to rank for high-intent product searches, not generic low-quality traffic.

SEO Meta Title
Rules:
Maximum 55–60 characters preferred
Include the main subject
Include Wall Art
Use the strongest relevant keyword naturally
Keep it clean and premium
Do not stuff keywords
Do not include the website URL
Do not use fake hype words
Good examples:
Greg Murphy Bathurst Wall Art
Cristiano Ronaldo Man United Wall Art
Arsenal The Wait Is Over Wall Art
Shane Warne Cricket Wall Art
Peter Brock Bathurst Wall Art
Kobe Bryant Lakers Wall Art
If space allows and it feels natural, add a high-intent modifier:
Limited Edition
Framed
Bathurst
NBA
Cricket
Football
Example:
Greg Murphy Bathurst Wall Art | Limited Edition
Only use a separator if it still fits cleanly under 60 characters.

SEO Meta Description
Rules:
Maximum 150–155 characters preferred
Mention the subject
Include one strong SEO keyword naturally
Mention limited edition or collector appeal
Make it emotional enough to win clicks
Do not include the website URL
Do not say “elevate your space”
Do not sound generic
Do not keyword stuff
Structure:
[Subject/moment] + [SEO keyword] + [collector scarcity/emotion].
Good examples:
Greg Murphy Bathurst wall art celebrating the Lap of the Gods. A limited edition collector piece for true motorsport fans.
Cristiano Ronaldo Manchester United wall art built for fans who remember the rise, the number seven, and the hunger. Limited to 100.
Arsenal wall art for fans who believe the wait is over. A numbered collector edition built around pride, history, and belief.

SEO Keyword Selection Rules
Choose keywords based on the product subject.
Use the most relevant keywords only.
Do not force every keyword into one product.

Core Sports Cave Keywords
Use naturally where relevant:
sports wall art
framed sports art
framed sports memorabilia
limited edition sports prints
man cave wall art
premium sports collectibles
sports art prints
sports posters Australia
Only use sports posters Australia when the product is Australian-based.
Examples:
Use for:
Bathurst
V8 Supercars
Greg Murphy
Peter Brock
Allan Moffat
Shane Warne
Australian cricket
AFL
Melbourne Cup
Australian racing moments
Do not use for:
NBA USA products
Premier League products
European football products
US boxing products

Sport-Specific SEO Keyword Map
Motorsport / Bathurst / V8
Use keywords such as:
motorsport wall art
Bathurst wall art
V8 Supercars wall art
motor racing wall art
framed sports memorabilia
sports posters Australia
limited edition sports prints
man cave wall art
Best for:
Greg Murphy
Peter Brock
Allan Moffat
Bathurst moments
Australian touring cars

NBA / Basketball
Use keywords such as:
NBA wall art
basketball wall art
Michael Jordan wall art
Kobe Bryant wall art
LeBron James wall art
framed sports art
man cave wall art
premium sports collectibles
Best for:
Michael Jordan
Kobe Bryant
LeBron James
Stephen Curry
Jalen Brunson
Knicks, Lakers, Bulls, Warriors

Football / Soccer
Use keywords such as:
football wall art
soccer wall art
Cristiano Ronaldo wall art
Lionel Messi wall art
Premier League wall art
framed sports art
limited edition sports prints
sports wall art
Best for:
Cristiano Ronaldo
Lionel Messi
Arsenal
Manchester United
Real Madrid
World Cup moments
Premier League legends

Cricket
Use keywords such as:
cricket wall art
cricket memorabilia
Shane Warne wall art
sports posters Australia
limited edition sports prints
man cave wall art
Best for:
Shane Warne
Don Bradman
Ricky Ponting
Pat Cummins
Ashes moments
Australian cricket icons

Boxing / Combat
Use keywords such as:
boxing wall art
Muhammad Ali wall art
Mike Tyson wall art
combat sports wall art
framed sports art
premium sports collectibles
man cave wall art

Horse Racing
Use keywords such as:
horse racing wall art
horse racing memorabilia
Melbourne Cup wall art
framed sports memorabilia
sports posters Australia
premium sports collectibles

Tennis
Use keywords such as:
tennis wall art
tennis sports wall art
framed sports art
premium sports collectibles
limited edition sports prints

Image Upload Rules
ChatGPT must upload every supplied final WebP image to Shopify.
Do not skip valid images.
Do not manually ask the user to upload images to Shopify Files.
Do not use local file paths in the final product.
Only use Shopify-hosted media once uploaded successfully.
If an image upload fails, ChatGPT must stop and report which file failed.

Product Image Order
Use this Sports Cave media order:
Black frame image
Lifestyle/mockup image 1
Lifestyle/mockup image 2
Lifestyle/mockup image 3
Office or man cave image
Size guide image
Oak frame image
White frame image
Unframed image
If fewer or more lifestyle images are supplied, keep this general order:
Black frame
Lifestyle/mockups
Size guide
Oak frame
White frame
Unframed
Every valid supplied image must be included.
Only remove exact duplicate files.

Image Naming Rules Before Upload
Where possible, rename files before Shopify upload using:
Lowercase letters
Hyphens only
Product-specific names
Accurate image descriptor
Do not include:
final
compressed
v2
copy
new
test
random numbers
unnecessary descriptors
Good examples:
greg-murphy-bathurst-wall-art-black-frame.webp
greg-murphy-bathurst-wall-art-living-room.webp
greg-murphy-bathurst-wall-art-man-cave.webp
greg-murphy-bathurst-wall-art-sizing-guide.webp
greg-murphy-bathurst-wall-art-oak-frame.webp
greg-murphy-bathurst-wall-art-white-frame.webp
greg-murphy-bathurst-wall-art-unframed.webp

Image Alt Text Rules
Every image must have unique SEO-friendly alt text.
Rules:
110–125 characters preferred
Natural sentence-style wording
Mention subject
Mention image type or setting
Use one SEO keyword only if it fits naturally
Do not keyword stuff
Do not repeat the same alt text for every image
Do not describe irrelevant furniture too heavily
Do not overuse “premium”
Good structure:
[Image type] + [subject] + [sport/keyword] + [fan/collector context].

Alt Text Examples
Black frame:
Black framed Greg Murphy Bathurst wall art celebrating the Lap of the Gods for Australian motorsport fans.
Living room:
Greg Murphy Bathurst wall art displayed in a modern living room for collectors of iconic racing moments.
Man cave:
Greg Murphy Lap of the Gods framed sports memorabilia styled in a dark man cave for true V8 racing fans.
Size guide:
Greg Murphy Bathurst wall art size guide showing framed options for limited edition motorsport collectors.
Oak frame:
Oak framed Greg Murphy Bathurst wall art with collector styling for fans of Australian motor racing history.
White frame:
White framed Greg Murphy Bathurst wall art featuring the Lap of the Gods moment for motorsport collectors.
Unframed:
Unframed Greg Murphy Bathurst sports poster Australia design celebrating the legendary Lap of the Gods.

Variant Structure
Create exactly 16 variants.
Option 1 Name:
Frame
Frame values in this order:
Black
Oak
White
Unframed
Option 2 Name:
Size
Size values in this order for each frame:
XL - 62 × 87 cm (24.4 × 34.3 in)
L - 45 × 62 cm (17.7 × 24.4 in)
M - 30 × 45 cm (11.8 × 17.7 in)
S - 21 × 30 cm (8.3 × 11.8 in)
Variant order must be:
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

Pricing Rules
Use AUD pricing.
Framed Black, Oak, White
XL:
Price: 329.00
Compare-at price: 428.00
L:
Price: 249.00
Compare-at price: 324.00
M:
Price: 199.00
Compare-at price: 259.00
S:
Price: 149.00
Compare-at price: 194.00
Unframed
XL:
Price: 149.00
Compare-at price: 194.00
L:
Price: 109.00
Compare-at price: 142.00
M:
Price: 79.00
Compare-at price: 103.00
S:
Price: 49.00
Compare-at price: 64.00

Inventory and Shipping Rules
Default settings:
Track inventory: true if supported
Inventory policy: continue unless instructed otherwise
Fulfillment service: manual unless Shopify fulfilment settings require otherwise
Requires shipping: true
Taxable: true
Weight unit: kg
If inventory quantity is not supplied or cannot be safely set through the Shopify connector, ChatGPT must leave inventory for manual review.
Do not use inventory deny unless stock is being controlled correctly.

SKU Rules
Create clean unique SKUs.
Rules:
Uppercase letters and numbers only
No spaces
No special symbols
Product-specific prefix
Size/frame suffix
Create a short SKU prefix from the product subject.
Examples:
Greg Murphy Lap of the Gods:
Prefix:
GMLG
Cristiano Ronaldo Manchester United:
Prefix:
CRMU
Arsenal The Wait Is Over:
Prefix:
ATWIO

SKU Suffix System
Black:
A1B = XL Black
A2B = L Black
A3B = M Black
A4B = S Black
Oak:
A1O = XL Oak
A2O = L Oak
A3O = M Oak
A4O = S Oak
White:
A1W = XL White
A2W = L White
A3W = M White
A4W = S White
Unframed:
A1 = XL Unframed
A2 = L Unframed
A3 = M Unframed
A4 = S Unframed
Example:
GMLGA1B
GMLGA2B
GMLGA3B
GMLGA4B
GMLGA1O
GMLGA1W
GMLGA1
All 16 SKUs must be unique.

Variant Image Mapping
Assign variant images correctly.
Rules:
Black variants use the black frame image
Oak variants use the oak frame image
White variants use the white frame image
Unframed variants use the unframed image
Do not assign these as variant images:
Lifestyle images
Living room images
Office images
Man cave images
Size guide images
Close-up detail images
These belong in the gallery only.

Tags
Use 8–16 clean, relevant tags.
Every product should include:
Collector Series
Limited Edition
Sports Wall Art
Limited Edition Sports Prints
Framed Sports Art
Man Cave Wall Art
Then add sport/product-specific tags.

Motorsport Tag Examples
Motorsport Wall Art
Motor Racing Wall Art
Bathurst Wall Art
V8 Supercars Wall Art
Sports Posters Australia
Greg Murphy
Bathurst
Lap Of The Gods

Football Tag Examples
Football Wall Art
Soccer Wall Art
Premier League Wall Art
Cristiano Ronaldo Wall Art
Lionel Messi Wall Art
Arsenal
Manchester United
Real Madrid

NBA Tag Examples
NBA Wall Art
Basketball Wall Art
Kobe Bryant Wall Art
Michael Jordan Wall Art
Lakers Wall Art
Bulls Wall Art
New York Knicks
Jalen Brunson

Cricket Tag Examples
Cricket Wall Art
Cricket Memorabilia
Shane Warne Wall Art
Sports Posters Australia
Australian Cricket
Ashes Cricket

Tags To Avoid Unless Proven
Do not use these unless specifically instructed:
Best Seller
Best Selling
Popular
Viral
Trending
Featured
New Arrival
Only use performance-based tags when proven by sales data.

Collections
Default safer method:
Use tags to trigger automated collections.
ChatGPT may assign collections directly only if the Shopify connector safely supports collection assignment.
Every product usually needs to appear in:
Collector Series Wall Art
Best Online Sports Wall Art
Sport collection examples:
NBA product → NBA Wall Art
Motorsport product → Motor Racing Wall Art
Cricket product → Cricket Wall Art
Football product → Football Wall Art
Horse racing product → Horse Racing Wall Art
Combat product → Combat Wall Art
NFL product → NFL Wall Art
Ice Hockey product → Ice Hockey Wall Art
Baseball product → Baseball Wall Art
Tennis product → Tennis Wall Art
WWE product → WWE Wrestling Wall Art
Only use these collections when specifically instructed:
Popular
Featured Sports Wall Art
Best Selling Wall Art UK

Google Shopping Fields
If the Shopify connector supports Google Shopping fields, use:
Google Shopping condition: New
Google Shopping custom product: True
Google Shopping age group: Adult if required
Google Shopping gender: Unisex if required
If Google Shopping fields are not safely supported through the connector, leave them for manual review.
Do not invent Google taxonomy values.

Product Category
Use:
Home & Garden > Decor > Artwork > Posters, Prints & Visual Artwork
If Shopify rejects the product category through the connector, leave it blank and continue.
Do not let category setup block product creation.

Pre-Creation Checklist
Before creating the Shopify draft, ChatGPT must confirm internally:
Product subject is clear
Sport/category is clear
Product title is clean
Handle is clean
Description follows Sports Cave structure
SEO title is under 60 characters
SEO description is under 155 characters
All supplied images are WebP
All supplied images are final assets
All supplied images are included
Image order is planned
Alt text is unique for every image
16 variants are planned
Prices are correct
Compare-at prices are correct
Compare-at prices are correct
SKUs are unique
Product will be draft
Product will not be published

Shopify Creation Workflow
ChatGPT must complete the workflow in this order:
Identify product subject from uploads and user context
Create product title
Create Shopify handle
Write Sports Cave-style description
Create SEO title
Create SEO description
Generate tags
Generate unique image alt text
Upload all supplied WebP images to Shopify
Create Shopify product as Draft
Add all images to the product in correct order
Create all 16 variants
Add prices and compare-at prices
Add SKUs
Assign variant images
Add tags
Add product type and vendor
Add product category only if safe
Leave product unpublished
Return the draft product link or confirmation

Post-Creation Validation
After creating the draft product, ChatGPT must verify:
Product exists in Shopify
Product is Draft
Product is not published
Product title is correct
Handle is correct
Product description has clean HTML
All images uploaded successfully
Image order is correct
All image alt text is applied where supported
All 16 variants exist
Variant order is correct
Prices are correct
Compare-at prices are correct
SKUs are unique
Variant images are mapped correctly
Tags are applied
SEO title is applied
SEO description is applied
No unsupported category metafields were filled
If the connector cannot verify a field, ChatGPT must clearly state what needs manual review.

Manual Review Checklist Before Publishing
Open the draft product in Shopify and check:
Product title
Product images
Image order
Image quality
Image alt text
Description formatting
Product description strength
Variant selector
Variant images
Prices
Compare-at prices
SKUs
Tags
Collections
SEO title
SEO description
Product category
Inventory
Markets
Google Shopping fields
Mobile preview
Desktop preview
Only publish when the product feels premium and ready.

Failure Rules
If Shopify product creation fails, ChatGPT must not guess or retry blindly.
Check these first:
Did image upload fail?
Did Shopify reject the product category?
Did Shopify reject a controlled metafield?
Did variant creation fail?
Did a SKU duplicate an existing SKU?
Did the product handle already exist?
Did the connector lack permission to upload media?
Did the connector lack permission to create products?
Fastest safe fix:
Create product without risky category fields
Leave taxonomy metafields blank
Re-upload failed images
Use a slightly adjusted handle if the handle already exists
Keep product as Draft

No-Publish Rule
ChatGPT must never publish the product unless the user explicitly says:
Publish this product now.
Even then, ChatGPT must confirm the product has been reviewed first.
Default status is always:
Draft

Final Execution Prompt
Use this prompt when uploading a new product:

I have uploaded final approved Sports Cave WebP product images.
Use SOP 07B.
Create a new Shopify product directly through the connected Shopify tool.
Do not create a CSV.
Do not ask me to manually upload images.
Upload all supplied WebP images to Shopify, create the product as a Draft, add all images in the correct Sports Cave order, write the product title, handle, Sports Cave-style emotional description, SEO meta title, SEO meta description, image alt text, tags, variants, SKUs, pricing, compare-at pricing, and variant image mapping.
Keep the product unpublished.
Use the product subject, sport, athlete, team, rivalry, or moment from the uploaded images. If unclear, ask before creating the draft.
Follow the Sports Cave description style:
Short. Emotional. Nostalgic. Identity-driven. Collector-focused.
The buyer should feel:
“That’s me. I remember that. I need this.”

Final Rule
This SOP exists to remove CSV import risk and manual Shopify upload work.
ChatGPT should now create the product directly in Shopify as a clean draft.
The only manual step left should be final approval and publishing.
"""
UPDATE_EXISTING_PRODUCT_PROMPT = """
SOP 07C — Sports Cave Shopify Existing Product Image Update Using ChatGPT + Shopify Connector
Direct Product Media Replacement Version — No CSV Import Required
Goal
Update an existing Sports Cave Shopify product directly through ChatGPT using the connected Shopify tool.
This SOP is for existing products only.
ChatGPT must:
Find the correct existing Shopify product
Upload all supplied final WebP replacement images to Shopify
Replace the existing product gallery images with the new supplied images
Apply the new images in the correct Sports Cave media order
Write or update unique SEO image alt text
Reassign variant images correctly
Keep the existing product handle unless instructed otherwise
Keep existing product pricing unless instructed otherwise
Keep existing variants unless instructed otherwise
Keep existing product status unchanged
Leave the product unpublished if it is already unpublished
Do not create a duplicate product
Do not use CSV import
Do not ask the user to manually upload images to Shopify
Brutal Rule
Never create a new Shopify product when the task is to update an existing product.
ChatGPT must update the existing product only.
Before making changes, ChatGPT must confirm it has found the correct existing product by matching at least one of the following:
Shopify product URL
Shopify product handle
Exact product title
Product ID
Clear product subject with only one matching Shopify product
If there is more than one possible match, ChatGPT must stop and ask the user to confirm the correct product.
Required Uploads
Before running this SOP, upload all final approved replacement WebP product images.
Images should already be:
Final production assets
Optimised WebP files
Correctly cropped
Correctly sized
Visually approved
Ready for Shopify upload
Do not ask ChatGPT to redesign, edit, crop, stylise, resize, relight, or change any product image during this SOP.
This SOP is for Shopify product image replacement and product media updating only.
Required Product Inputs
Provide one of the following:
Existing Shopify product URL
Existing Shopify product handle
Exact existing Shopify product title
Product subject and sport/category if the product can be clearly identified
Also provide:
Final approved replacement WebP images
Any images that must stay on the product, if any
Any images that must be removed, if any
Any title, description, SEO, or tag changes required
If the user only uploads images and gives no product URL, handle, or title, ChatGPT must identify the likely product from Shopify search but must ask for confirmation before replacing images.
Default Update Scope
Unless the user specifically requests more, ChatGPT must update only:
Product images
Image order
Image alt text
Variant image mapping
ChatGPT must not change these unless requested:
Product title
Product handle
Product description
SEO title
SEO description
Tags
Product type
Vendor
Collections
Prices
Compare-at prices
Variants
SKUs
Inventory
Product status
Publishing status
Markets
Google Shopping fields
Shopify category metafields
No-Publish / Status Rule
ChatGPT must never publish, unpublish, archive, or change the product status unless the user specifically asks.
Default action:
If product is Active, keep Active
If product is Draft, keep Draft
If product is Archived, stop and ask before updating
Do not automatically publish an updated product.
Existing Product Safety Rule
Before replacing images, ChatGPT must verify internally:
Correct product has been found
Product title matches user intent
Product handle matches user intent
Uploaded images match the product subject
Replacement images are WebP
Images appear to be final assets
New image order is planned
Variant image mapping is planned
No duplicate product will be created
If there is uncertainty, ChatGPT must ask before updating.
Image Replacement Rule
ChatGPT must replace the existing product images with the new supplied images.
Default behaviour:
Upload all supplied replacement WebP images to Shopify
Add the new Shopify-hosted images to the existing product
Apply image alt text to each new image where supported
Reorder the product gallery into the correct Sports Cave order
Assign the correct variant images
Remove old product images after the new images are confirmed uploaded and attached
Do not remove old images first.
Safe sequence:
Upload new images first
Attach new images to product
Confirm new images are present
Assign variant images
Confirm variant image mapping
Then remove old images that are being replaced
This prevents the product being left with no images if upload fails.
Image Preservation Rule
If the existing product has images that should remain, the user must clearly say so.
Examples:
Keep the size guide
Keep the lifestyle image
Keep the old black frame image
Only replace the mockups
Only replace the frame images
If the user says “replace the images” or “update to these new images,” ChatGPT should assume all old gallery images should be replaced by the newly supplied images.
Product Image Order
Use this Sports Cave media order:
Black frame image
Lifestyle/mockup image 1
Lifestyle/mockup image 2
Lifestyle/mockup image 3
Office, hallway, living room, sports bar, or man cave image
Size guide image
Oak frame image
White frame image
Unframed image
If fewer or more lifestyle images are supplied, keep this general order:
Black frame
Lifestyle/mockups
Size guide
Oak frame
White frame
Unframed
Every valid supplied image must be included.
Only remove exact duplicate files.
Image Naming Rules Before Upload
Where possible, rename files before Shopify upload using:
Lowercase letters
Hyphens only
Product-specific names
Accurate image descriptor
Do not include:
final
compressed
v2
copy
new
test
random numbers
unnecessary descriptors
Good examples:
greg-murphy-bathurst-wall-art-black-frame.webp
greg-murphy-bathurst-wall-art-living-room.webp
greg-murphy-bathurst-wall-art-man-cave.webp
greg-murphy-bathurst-wall-art-sizing-guide.webp
greg-murphy-bathurst-wall-art-oak-frame.webp
greg-murphy-bathurst-wall-art-white-frame.webp
greg-murphy-bathurst-wall-art-unframed.webp
Image Alt Text Rules
Every replacement image must have unique SEO-friendly alt text.
Rules:
110–125 characters preferred
Natural sentence-style wording
Mention the subject
Mention image type or setting
Use one SEO keyword only if it fits naturally
Do not keyword stuff
Do not repeat the same alt text for every image
Do not describe irrelevant furniture too heavily
Do not overuse “premium”
Good structure:
[Image type] + [subject] + [sport/keyword] + [fan/collector context].
Alt Text Examples
Black frame:
Black framed Greg Murphy Bathurst wall art celebrating the Lap of the Gods for Australian motorsport fans.
Living room:
Greg Murphy Bathurst wall art displayed in a modern living room for collectors of iconic racing moments.
Man cave:
Greg Murphy Lap of the Gods framed sports memorabilia styled in a dark man cave for true V8 racing fans.
Size guide:
Greg Murphy Bathurst wall art size guide showing framed options for limited edition motorsport collectors.
Oak frame:
Oak framed Greg Murphy Bathurst wall art with collector styling for fans of Australian motor racing history.
White frame:
White framed Greg Murphy Bathurst wall art featuring the Lap of the Gods moment for motorsport collectors.
Unframed:
Unframed Greg Murphy Bathurst sports poster Australia design celebrating the legendary Lap of the Gods.
Variant Image Mapping
After replacing product images, ChatGPT must reassign variant images correctly.
Rules:
Black variants use the black frame image
Oak variants use the oak frame image
White variants use the white frame image
Unframed variants use the unframed image
Do not assign these as variant images:
Lifestyle images
Living room images
Office images
Hallway images
Sports bar images
Man cave images
Size guide images
Close-up detail images
These belong in the product gallery only.
Variant Structure Protection Rule
Existing product variants must not be deleted or recreated unless specifically requested.
Default action:
Keep all existing variants
Keep existing variant order
Keep existing prices
Keep existing compare-at prices
Keep existing SKUs
Only update variant image assignments
If the product has broken, missing, or incorrect variants, ChatGPT must report the issue and ask before making variant changes.
Pricing Protection Rule
Do not change pricing during an image replacement update unless the user specifically asks.
Existing prices must remain unchanged.
Existing compare-at prices must remain unchanged.
Inventory Protection Rule
Do not change inventory during an image replacement update unless the user specifically asks.
Existing inventory tracking must remain unchanged.
Existing inventory policy must remain unchanged.
Existing stock quantities must remain unchanged.
SEO Update Rule
Default action:
Update image alt text only.
Do not rewrite SEO title or SEO meta description unless the user asks.
If the user asks to refresh SEO at the same time, follow the Sports Cave SEO rules:
SEO title should be under 60 characters
SEO description should be under 155 characters
Use the main subject and strongest relevant wall art keyword
Keep it premium and clean
Do not keyword stuff
Do not use generic phrases like “elevate your space”
Product Description Update Rule
Default action:
Do not change the existing product description.
If the user asks to update the product description, rewrite it in the Sports Cave emotional collector style:
Short
Emotional
Nostalgic
Identity-driven
Collector-focused
Built for mobile reading
Description structure:
Emotional hook
Nostalgia trigger
Identity line
Scarcity close
Allowed HTML:
Do not use:
Tags and Collections Protection Rule
Do not change tags or collections during an image replacement update unless the user specifically asks.
Existing automated collection logic may depend on tags.
If tags are updated, use only clean, relevant Sports Cave tags.
Do not add performance-based tags unless proven:
Best Seller
Best Selling
Popular
Viral
Trending
Featured
New Arrival
Shopify Category and Metafield Protection Rule
Do not update Shopify-controlled category metafields during an image replacement update unless specifically instructed and safe accepted values are provided.
Leave the following unchanged:
Art movement
Art style
Artwork authenticity
Artwork frame material
Colour
Condition metafields
Frame style
Material
Orientation
Painting medium
Print edition type
Rarity
Signature placement
Sports logo
Suitable space
Theme
Printing method
Do not invent values.
Existing Product Update Workflow
ChatGPT must complete the workflow in this order:
Identify the existing Shopify product
Confirm the product match if there is any uncertainty
Review current product images and variant image mapping where possible
Identify all supplied replacement WebP images
Plan the new Sports Cave image order
Generate unique alt text for every replacement image
Upload all replacement images to Shopify
Attach the new images to the existing product
Reorder the product gallery correctly
Assign black frame image to all Black variants
Assign oak frame image to all Oak variants
Assign white frame image to all White variants
Assign unframed image to all Unframed variants
Confirm new images are attached successfully
Remove old images that are being replaced
Keep product status unchanged
Verify the updated product
Return the product link and manual review checklist
Post-Update Validation
After updating the product, ChatGPT must verify:
Correct existing product was updated
No duplicate product was created
Product status was not changed
Product title was not changed unless requested
Product handle was not changed unless requested
All new images uploaded successfully
Old images were removed only after new images were attached
Image order is correct
Image alt text is applied where supported
All 16 variants still exist if the product previously had 16 variants
Variant image mapping is correct
Prices were not changed unless requested
Compare-at prices were not changed unless requested
SKUs were not changed unless requested
Inventory was not changed unless requested
Tags were not changed unless requested
SEO fields were not changed unless requested
No unsupported category metafields were filled
If the Shopify connector cannot verify a field, ChatGPT must clearly state what needs manual review.
Manual Review Checklist After Updating Images
After updating the product, ChatGPT must verify:
Open the product in Shopify and check:
Correct product was updated
No duplicate product was created
Product images
Image order
Image quality
Image alt text
Black variant image
Oak variant image
White variant image
Unframed variant image
Variant selector
Prices
Compare-at prices
SKUs
Inventory
Tags
Collections
SEO title
SEO description
Mobile preview
Desktop preview
Live product page if product is active
Only consider the update complete when the product looks premium and ready to sell.
Failure Rules
If the Shopify product update fails, ChatGPT must not guess or retry blindly.
Check these first:
Could the existing product not be found?
Were multiple matching products found?
Did image upload fail?
Did Shopify reject one or more media files?
Did the connector lack permission to upload media?
Did the connector lack permission to update products?
Did variant image assignment fail?
Did old image deletion fail?
Did alt text fail to apply?
Did Shopify timeout during media processing?
Fastest safe fix:
Do not remove old images until new images are confirmed
Retry failed image upload once
If upload still fails, report the failed file
If product match is unclear, ask user for product URL or handle
If variant mapping fails, leave product images updated and report variant mapping for manual review
Do not create a new product as a workaround.
Final Execution Prompt
Use this prompt when updating an existing product:
I have uploaded final approved replacement Sports Cave WebP product images.
Use SOP 07C.
Update the existing Shopify product directly through the connected Shopify tool.
Do not create a CSV.
Do not create a new product.
Do not ask me to manually upload images.
Find the existing product using the product URL, handle, title, or product subject I provide.
Upload all supplied WebP images to Shopify, attach them to the existing product, replace the old product images, apply the correct Sports Cave image order, write unique SEO-friendly alt text for every image, and reassign variant images correctly.
Black variants use the black frame image.
Oak variants use the oak frame image.
White variants use the white frame image.
Unframed variants use the unframed image.
Keep the existing product status unchanged.
Keep the existing product title, handle, description, SEO, tags, prices, SKUs, variants, inventory, collections, and metafields unchanged unless I specifically ask you to update them.
If the correct product is unclear, ask before making changes.
Final Rule
This SOP exists to replace manual Shopify image updates and prevent duplicate products.
ChatGPT should update the existing Shopify product directly, replace the old images safely, reassign variant images, and leave only final manual review.
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
        [data-testid="stExpander"] details > div .stDownloadButton > button,
        [data-testid="stExpander"] details > div .stDownloadButton > button:hover,
        [data-testid="stExpander"] details > div .stDownloadButton > button:focus,
        [data-testid="stExpander"] details > div .stLinkButton > a,
        [data-testid="stExpander"] details > div .stLinkButton > a:hover,
        [data-testid="stExpander"] details > div .stLinkButton > a:focus,
        [data-testid="stExpander"] details > div div[data-testid="stButton"] button,
        [data-testid="stExpander"] details > div div[data-testid="stDownloadButton"] button,
        [data-testid="stExpander"] details > div a[data-testid="stLinkButton"] {
            background: #F5F2EA !important;
            color: #000000 !important;
            -webkit-text-fill-color: #000000 !important;
            border-color: rgba(212, 165, 76, 0.55) !important;
            filter: none !important;
            transform: none !important;
        }

        [data-testid="stExpander"] details > div .stButton > button *,
        [data-testid="stExpander"] details > div .stDownloadButton > button *,
        [data-testid="stExpander"] details > div .stLinkButton > a *,
        [data-testid="stExpander"] details > div div[data-testid="stButton"] button *,
        [data-testid="stExpander"] details > div div[data-testid="stDownloadButton"] button *,
        [data-testid="stExpander"] details > div a[data-testid="stLinkButton"] * {
            color: #000000 !important;
            -webkit-text-fill-color: #000000 !important;
            fill: #000000 !important;
            stroke: #000000 !important;
        }

        .stButton > button,
        .stLinkButton > a,
        .stDownloadButton > button,
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
        .stLinkButton > a *,
        .stDownloadButton > button *,
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
        .stLinkButton > a:hover,
        .stLinkButton > a:focus,
        .stLinkButton > a:active,
        .stDownloadButton > button:hover,
        .stDownloadButton > button:focus,
        .stDownloadButton > button:active,
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

        .stButton > button[kind="primary"] {
            background: var(--sc-gold) !important;
            border-color: var(--sc-gold) !important;
            color: #000000 !important;
            font-weight: 700;
        }

        .stButton > button[kind="primary"] *,
        .stButton > button[kind="primary"] p,
        .stButton > button[kind="primary"] span {
            color: #000000 !important;
            fill: #000000 !important;
            stroke: #000000 !important;
        }

        .stButton > button:disabled,
        .stLinkButton > a[aria-disabled="true"],
        .stDownloadButton > button:disabled,
        div[data-testid="stFileUploader"] button:disabled,
        section[data-testid="stFileUploaderDropzone"] button:disabled {
            background: #2A2A2D !important;
            border-color: #444149 !important;
            color: #C2BBB0 !important;
            opacity: 1 !important;
        }

        .stButton > button:disabled *,
        .stLinkButton > a[aria-disabled="true"] *,
        .stDownloadButton > button:disabled *,
        div[data-testid="stFileUploader"] button:disabled *,
        section[data-testid="stFileUploaderDropzone"] button:disabled * {
            color: #C2BBB0 !important;
            fill: #C2BBB0 !important;
            stroke: #C2BBB0 !important;
        }

        .stButton > button[kind="primary"]:hover {
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
    return UPDATE_EXISTING_PRODUCT_PROMPT if update_existing else NEW_SHOPIFY_PRODUCT_PROMPT


PRODUCT_UPLOAD_ALT_TEXT_PROMPT = """
Create unique Shopify image alt text for every Sports Cave product image I upload.

Inputs:
- Product title
- Sport / athlete / team / moment if known
- Image filenames or image order
- Screenshot/product preview if supplied

Rules:
- Write one unique alt text line per image.
- Keep it natural, descriptive, and buyer-friendly.
- Include the product title or sport context only when true.
- Do not keyword stuff.
- Do not repeat the same wording across every image.
- Do not invent athletes, teams, trophies, or events that are not visible/provided.

Output:
Image/file | Alt text
"""


PRODUCT_UPLOAD_META_PROMPT = """
Write Shopify SEO metadata for this Sports Cave product.

Inputs:
- Product title
- Sport/category
- Product description or artwork context
- Target market if known

Output:
1. SEO title, maximum 60 characters
2. SEO meta description, maximum 155 characters
3. URL handle suggestion
4. 10 Shopify tags

Rules:
- Premium sports wall art tone.
- Clear collector/man cave intent.
- No fake scarcity unless the edition limit is provided.
- No keyword stuffing.
- Make the meta description sound human, not robotic.
"""


PRODUCT_UPLOAD_QA_CHECKLIST_PROMPT = """
Review this Shopify product draft before publishing.

Check:
- Product title is clean and accurate.
- Description sounds like Sports Cave and does not overpromise.
- All uploaded images are in the correct order.
- Each image has unique alt text.
- Variant names, SKUs, prices, and compare-at prices are correct.
- Frame/size variant image mapping is correct.
- SEO title and meta description are filled in.
- Tags are relevant and not spammy.
- Limited edition wording is accurate.
- Product is saved as Draft until manually approved.

Output:
Pass / Needs Fix table with exact fixes.
"""


def validate_uploaded_artwork(uploaded_file):
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
    background="#0B0B0D",
    text_color="#F5F2EA",
    border_color="#0B0B0D",
):
    prompt_text_json = json.dumps(prompt_text)
    safe_label = html.escape(label)

    components.html(
        f"""
        <div style="padding-top:2px;">
          <button
            id="copy-inline-button-{key}"
            type="button"
            style="width:100%;border:1px solid {border_color};border-radius:14px;padding:12px 14px;background:{background};color:{text_color};font-weight:700;font-size:0.95rem;cursor:pointer;box-sizing:border-box;"
          >
            {safe_label}
          </button>
        </div>
        <script>
        (() => {{
          const button = document.getElementById("copy-inline-button-{key}");
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

            button.innerText = "Copied";
            setTimeout(() => {{
              button.innerText = originalLabel;
            }}, 1400);
          }}

          button.addEventListener("click", copyPrompt);
        }})();
        </script>
        """,
        height=62,
    )


def render_copyable_prompt(title, prompt_text, key, show_title=True):
    textarea_height = min(780, max(320, (prompt_text.count("\n") + 1) * 18 + 80))
    component_height = textarea_height + (104 if show_title else 78)
    safe_title = html.escape(title)
    safe_text = html.escape(prompt_text)
    title_markup = (
        f'<strong style="font-size:1rem;color:#0B0B0D;">{safe_title}</strong>'
        if show_title
        else '<span style="display:block;width:1px;height:1px;opacity:0;">Prompt</span>'
    )

    components.html(
        f"""
        <div style="border:1px solid rgba(212,165,76,0.30);border-radius:16px;padding:16px;background:#FFFFFF;color:#0B0B0D;box-sizing:border-box;">
          <div style="display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:12px;">
            {title_markup}
            <button
              id="copy-button-{key}"
              type="button"
              style="border:1px solid #0B0B0D;border-radius:999px;padding:10px 16px;background:#FFFFFF;color:#0B0B0D;font-weight:700;cursor:pointer;"
            >
              Copy Prompt
            </button>
          </div>
          <textarea
            id="prompt-text-{key}"
            readonly
            style="width:100%;height:{textarea_height}px;border:1px solid rgba(11,11,13,0.18);border-radius:12px;padding:12px;background:#FFFFFF;color:#000000;font-size:0.95rem;line-height:1.45;resize:none;box-sizing:border-box;"
          >{safe_text}</textarea>
        </div>
        <script>
        (() => {{
          const button = document.getElementById("copy-button-{key}");
          const textarea = document.getElementById("prompt-text-{key}");
          const originalLabel = button.innerText;
          const promptText = {json.dumps(prompt_text)};

          async function copyPrompt() {{
            textarea.focus();
            textarea.select();
            textarea.setSelectionRange(0, textarea.value.length);

            try {{
              if (navigator.clipboard && window.isSecureContext) {{
                await navigator.clipboard.writeText(promptText);
              }} else {{
                document.execCommand("copy");
              }}
            }} catch (error) {{
              document.execCommand("copy");
            }}

            button.innerText = "Copied";
            setTimeout(() => {{
              button.innerText = originalLabel;
            }}, 1400);
          }}

          button.addEventListener("click", copyPrompt);
        }})();
        </script>
        """,
        height=component_height,
    )


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
            st.markdown(f"**{get_prompt_label(prompt_path)}**")
            prompt_name = prompt_path.name
            prompt_text = prompt_path.read_text(encoding="utf-8")
            prompt_key = f"{result['run_dir']}::{prompt_name}"

            prompt_header_cols = st.columns([4, 1], gap="small")
            with prompt_header_cols[0]:
                with st.expander("View Prompt"):
                    render_copyable_prompt(
                        get_prompt_label(prompt_path),
                        prompt_text,
                        f"prompt-box::{prompt_key}",
                        show_title=False,
                    )
            with prompt_header_cols[1]:
                render_copy_prompt_button(
                    prompt_text,
                    f"prompt-header::{prompt_key}",
                    label="Copy",
                    background="#0B0B0D",
                    text_color="#F5F2EA",
                    border_color="#0B0B0D",
                )

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
        st.sidebar.write("1. Shows the saved order allocation snapshot immediately.")
        st.sidebar.write("2. Refresh recent paid orders only when needed.")
        st.sidebar.write("3. Manual edits update order edition fields only.")
        st.sidebar.write("4. Product counters stay controlled from Edition Ops unless explicitly allocated.")
    elif st.session_state.selected_page == "Prodigi":
        st.sidebar.divider()
        st.sidebar.subheader("Prodigi")
        st.sidebar.write("1. Open the Prodigi dashboard and search the order.")
        st.sidebar.write("2. Match Shopify size to Prodigi size: XL=A1, L=A2, M=A3, S=A4.")
        st.sidebar.write("3. Copy the exact Prodigi name or code.")
        st.sidebar.write("4. Check the frame colour before sending to production.")
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

    st.sidebar.divider()
    st.sidebar.subheader("MVP Mode")
    st.sidebar.caption(
        "Edition Ops controls product edition fields. Orders uses a lightweight saved allocation snapshot."
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

    st.info(
        "This page does not scan local runs. Attach your own `shopify-uploads` WEBP files and HTML preview in ChatGPT, then copy one of the prompts below."
    )

    with st.container(border=True):
        st.markdown("**Upload checklist**")
        st.markdown(
            "1. Drag every WEBP file from your `shopify-uploads` folder into ChatGPT.\n"
            "2. Drag the matching HTML preview into ChatGPT if you have it.\n"
            "3. Copy the product prompt you need.\n"
            "4. Copy the alt text and meta prompts when the draft needs them.\n"
            "5. Run the final QA checklist before publishing.\n"
            "\n"
            "This page stays manual on purpose so it remains fast and lightweight on Render."
        )

    st.divider()
    st.write("Copy only the prompt you need. Nothing on this page queries products, Shopify, or generated runs.")

    render_copyable_prompt(
        "New Shopify Product Prompt",
        get_product_upload_prompt({}, update_existing=False),
        "new-shopify-product-prompt",
    )

    st.divider()

    render_copyable_prompt(
        "Update Existing Product Prompt",
        get_product_upload_prompt({}, update_existing=True),
        "update-existing-shopify-product-prompt",
    )

    st.divider()
    render_copyable_prompt(
        "Image Alt Text Prompt",
        PRODUCT_UPLOAD_ALT_TEXT_PROMPT,
        "shopify-image-alt-text-prompt",
    )

    st.divider()
    render_copyable_prompt(
        "Meta Title / Description Prompt",
        PRODUCT_UPLOAD_META_PROMPT,
        "shopify-meta-title-description-prompt",
    )

    st.divider()
    render_copyable_prompt(
        "Final QA Checklist Prompt",
        PRODUCT_UPLOAD_QA_CHECKLIST_PROMPT,
        "shopify-final-qa-checklist-prompt",
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
    if st.button(label, key=key, use_container_width=True):
        st.session_state[key] = True
    return bool(st.session_state.get(key))


def _render_developer_password_gate():
    st.title("Developer")
    st.caption("Protected diagnostics and setup tools.")
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

    with st.expander("Shopify Connection", expanded=False):
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
                    st.exception(error)

    with st.expander("Shopify Limited Edition Setup", expanded=False):
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
                    st.exception(error)
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
                    st.exception(error)
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

    with st.expander("Shopify Webhook Setup", expanded=False):
        st.write("**Paid orders webhook endpoint:** `/webhooks/shopify/orders-paid`")
        st.write(f"**Webhook secret configured:** {'Yes' if bool(os.getenv('SHOPIFY_WEBHOOK_SECRET', '').strip()) else 'No'}")
        st.caption("The endpoint verifies the HMAC header before allocating edition numbers.")

    with st.expander("Order Metafield Setup", expanded=False):
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
                    st.exception(error)
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
                    st.exception(error)
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

    with st.expander("Database / Supabase", expanded=False):
        st.write(f"**DATABASE_URL present:** {'Yes' if any(os.getenv(key, '').strip() for key in DATABASE_URL_ENV_KEYS) else 'No'}")
        if st.button("Run Database Connection Test", key="developer-test-database", use_container_width=True):
            try:
                supabase_backend = importlib.import_module("supabase_backend")
                result = supabase_backend.test_connection()
                st.success("Database connection OK.")
                st.caption(f"Server time: {result.get('server_time')}")
            except Exception as error:
                st.error("Database connection failed.")
                st.exception(error)

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
                st.error("R2 status failed.")
                st.exception(error)

    with st.expander("Diagnostics", expanded=False):
        st.caption("These checks import heavier modules only after you click.")
        diag_cols = st.columns(2)
        if diag_cols[0].button("Load Legacy Diagnostics Module", key="developer-load-legacy-pages", use_container_width=True):
            try:
                get_os_pages()
                st.success("Legacy diagnostics module imported.")
            except Exception as error:
                st.error("Legacy diagnostics import failed.")
                st.exception(error)
        if diag_cols[1].button("Load Local DB Module", key="developer-load-local-db", use_container_width=True):
            try:
                local_db = get_db()
                st.success(f"Local DB module loaded: `{local_db.DB_PATH}`")
            except Exception as error:
                st.error("Local DB import failed.")
                st.exception(error)


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
        st.info("Orders, Supabase sync, product sync, CSV imports, and certificates are paused for this MVP.")
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
        "Certificates",
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
    elif current_page == "Certificates":
        os_route_pages().render_certificates_page()
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
