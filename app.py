from contextlib import suppress
from datetime import datetime, timedelta
from functools import lru_cache
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
import traceback

from PIL import Image, ImageOps, UnidentifiedImageError
from dotenv import load_dotenv
import requests
import streamlit as st
import streamlit.components.v1 as components

import image_factory


load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


BASE_DIR = Path(__file__).resolve().parent
RUNS_DIR = BASE_DIR / "output" / "runs"
UPLOAD_PREVIEW_DIR = BASE_DIR / "output" / "_ui-upload-previews"
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
MENU_OPTIONS = ["Mockups", "Limited Editions", "Product Uploads", "Settings"]
if ENABLE_GOOGLE_DRIVE:
    MENU_OPTIONS.insert(1, "Google Drive")
APP_VERSION = "Build 2026-06-11"
DRIVE_SECTION_NAMES = {
    "mockups": "Mockups",
    "limited_editions": "Limited Editions",
    "product_uploads": "Product Uploads",
    "system_logs": "System Logs",
}
PASSWORD_ENV_KEYS = (
    "APP_PASSWORD",
    "STREAMLIT_PASSWORD",
    "SPORTS_CAVE_PASSWORD",
    "SITE_PASSWORD",
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
    page_title="Sports Cave Image Factory",
    layout="wide",
    initial_sidebar_state="expanded",
)


def inject_styles():
    st.markdown(
        """
        <style>
        [data-testid="stAppViewContainer"] {
            background: #f7f4ee;
        }

        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #111315 0%, #1b1d21 100%);
        }

        [data-testid="stSidebar"] * {
            color: #f6f1e7;
        }

        div[data-testid="stRadio"] label p {
            font-weight: 600;
        }

        .sc-shell-card {
            background: rgba(255, 252, 246, 0.94);
            border: 1px solid #e5dbc6;
            border-radius: 18px;
            padding: 1rem 1.15rem;
        }

        .sc-muted {
            color: #6b675f;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def init_session_state():
    if "selected_page" not in st.session_state:
        st.session_state.selected_page = "Mockups"

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

    if "limited_editions_test_result" not in st.session_state:
        st.session_state.limited_editions_test_result = None


def log_app_memory(stage):
    image_factory.log_memory(stage)


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
    }

    try:
        rows, diagnostics = request_edition_log_endpoint(requested_url)
        overall_diagnostics.update(diagnostics)
        overall_diagnostics["attempted_urls"].append(diagnostics["requested_url"])
        return rows, overall_diagnostics
    except EditionLogEndpointError as first_error:
        overall_diagnostics.update(first_error.diagnostics)
        overall_diagnostics["attempted_urls"].append(first_error.diagnostics["requested_url"])

        public_url = convert_to_public_apps_script_url(requested_url)
        should_retry = (
            first_error.diagnostics.get("response_looks_like") == "HTML"
            and public_url
            and public_url != requested_url
        )
        if not should_retry:
            raise EditionLogEndpointError(
                first_error.user_message,
                overall_diagnostics,
                debug_error=first_error.debug_error,
            ) from first_error

        overall_diagnostics["retried_public_url_format"] = True

        try:
            rows, retry_diagnostics = request_edition_log_endpoint(public_url)
            overall_diagnostics.update(retry_diagnostics)
            overall_diagnostics["attempted_urls"].append(retry_diagnostics["requested_url"])
            return rows, overall_diagnostics
        except EditionLogEndpointError as retry_error:
            overall_diagnostics.update(retry_error.diagnostics)
            overall_diagnostics["attempted_urls"].append(retry_error.diagnostics["requested_url"])
            raise EditionLogEndpointError(
                retry_error.user_message,
                overall_diagnostics,
                debug_error=retry_error.debug_error,
            ) from retry_error


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

    json_rows, endpoint_diagnostics = fetch_edition_log_json_rows(json_url)
    edition_rows, had_date_parse_failure = build_records_from_json_rows(json_rows)
    sorted_rows = sort_edition_records(edition_rows, had_date_parse_failure=had_date_parse_failure)

    for row in sorted_rows:
        row["_product_link"] = resolve_product_link(row)

    return {
        "rows": sorted_rows,
        "had_date_parse_failure": had_date_parse_failure,
        "endpoint_diagnostics": endpoint_diagnostics,
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

        preview_image = ImageOps.exif_transpose(source_image).convert("RGB")
        preview_image.thumbnail((image_factory.MAX_PREVIEW_EDGE, image_factory.MAX_PREVIEW_EDGE), Image.LANCZOS)
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


def validate_uploaded_artwork(uploaded_file):
    if uploaded_file is None:
        raise ValueError("Please upload an artwork image first.")

    file_size = getattr(uploaded_file, "size", None)
    if file_size is not None and file_size <= 0:
        raise ValueError("Uploaded file is empty.")
    if file_size is not None and file_size > image_factory.MAX_UPLOAD_SIZE_BYTES:
        raise ValueError(
            "Uploaded image is too large for the current Render instance. "
            "Please upload a JPG or WebP under 10MB."
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


def render_copyable_prompt(title, prompt_text, key):
    textarea_height = min(780, max(320, (prompt_text.count("\n") + 1) * 18 + 80))
    component_height = textarea_height + 96
    safe_title = html.escape(title)
    safe_text = html.escape(prompt_text)

    components.html(
        f"""
        <div style="border:1px solid #ddd6ca;border-radius:16px;padding:16px;background:#ffffff;">
          <div style="display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:12px;">
            <strong style="font-size:1rem;color:#243040;">{safe_title}</strong>
            <button
              id="copy-button-{key}"
              type="button"
              style="border:none;border-radius:999px;padding:10px 16px;background:#243040;color:#ffffff;font-weight:600;cursor:pointer;"
            >
              Copy Prompt
            </button>
          </div>
          <textarea
            id="prompt-text-{key}"
            readonly
            style="width:100%;height:{textarea_height}px;border:1px solid #ddd6ca;border-radius:12px;padding:12px;background:#faf8f4;color:#1f2937;font-size:0.95rem;line-height:1.45;resize:none;box-sizing:border-box;"
          >{safe_text}</textarea>
        </div>
        <script>
        (() => {{
          const button = document.getElementById("copy-button-{key}");
          const textarea = document.getElementById("prompt-text-{key}");
          const originalLabel = button.innerText;

          async function copyPrompt() {{
            textarea.focus();
            textarea.select();
            textarea.setSelectionRange(0, textarea.value.length);

            try {{
              if (navigator.clipboard && window.isSecureContext) {{
                await navigator.clipboard.writeText(textarea.value);
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


def render_generated_previews(result):
    st.subheader("Generated Previews")
    st.caption("These are lightweight preview files only. Full export images stay on disk until you download them.")
    preview_cols = st.columns(2)
    base_assets = [asset for asset in result["assets"] if asset["asset_group"] == "generated"]

    for index, asset in enumerate(base_assets):
        with preview_cols[index % 2]:
            preview_path = asset.get("preview_path")
            if preview_path and Path(preview_path).exists():
                st.image(str(preview_path), caption=asset["label"], width=380)
            else:
                st.caption("Preview not available.")


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
            with st.expander("View Prompt"):
                st.code(prompt_path.read_text(encoding="utf-8"), language=None)

            prompt_name = prompt_path.name
            saved_lifestyle_paths = result["lifestyle_mockup_paths"].get(prompt_name)

            if saved_lifestyle_paths:
                saved_preview_path = saved_lifestyle_paths.get("preview_path")

                preview_path = saved_preview_path
                if preview_path and Path(preview_path).exists():
                    st.image(
                        str(preview_path),
                        caption=Path(preview_path).name,
                        width=360,
                    )
                    st.caption("Saved. It will be included the next time you save the ZIP.")

            uploaded_lifestyle_image = st.file_uploader(
                "Upload image from ChatGPT",
                type=["png", "jpg", "jpeg", "webp"],
                key=f"lifestyle-upload::{result['run_dir']}::{prompt_name}",
                help="Upload the finished ChatGPT lifestyle image here.",
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

    if result["run_dir"]:
        st.caption(f"Local run folder: `{result['run_dir']}`")

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
    st.sidebar.title("Sports Cave")
    st.sidebar.caption("Image Factory")
    st.sidebar.caption(APP_VERSION)
    st.sidebar.radio(
        "Navigation",
        MENU_OPTIONS,
        key="selected_page",
        label_visibility="collapsed",
    )

    if st.session_state.selected_page == "Mockups":
        st.sidebar.divider()
        st.sidebar.subheader("How It Works")
        st.sidebar.write("1. Upload artwork.")
        st.sidebar.write("2. Generate core Shopify images.")
        st.sidebar.write("3. Review lightweight previews.")
        st.sidebar.write("4. Download one ZIP bundle.")
        st.sidebar.write("5. Use the prompt sections below if you want ChatGPT lifestyle images.")
    elif st.session_state.selected_page == "Limited Editions":
        st.sidebar.divider()
        st.sidebar.subheader("Limited Editions")
        st.sidebar.write("1. Open the live edition dashboard.")
        st.sidebar.write("2. Refresh the sheet when needed.")
        st.sidebar.write("3. Check previous edition numbers by product.")
        st.sidebar.write("4. Expand internal details only when needed.")

    st.sidebar.divider()
    st.sidebar.subheader("Storage")
    if ENABLE_GOOGLE_DRIVE:
        st.sidebar.caption("Google Drive available on its own page.")
        st.sidebar.caption("Drive authentication and syncing stay idle until you open Drive actions.")
    else:
        st.sidebar.caption("Google Drive disabled in lightweight mode.")
        st.sidebar.caption("Local output stays isolated unless Drive is enabled explicitly.")


def render_mockups_page():
    log_app_memory("Page load: Mockups")
    st.title("Sports Cave Image Factory")
    st.caption(
        "Upload one finished artwork, generate the five core Shopify images, then download one simple ZIP bundle."
    )
    st.caption("Upload limit: 10MB. Working images are capped to 2000px and UI previews are capped to 900px.")

    st.subheader("1. Upload Artwork")
    uploaded_file = st.file_uploader(
        "Upload finished Sports Cave artwork",
        type=["jpg", "jpeg", "png", "webp"],
        help="Upload the final flattened artwork that should appear in every mockup.",
    )

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
            if not product_name.strip():
                raise ValueError("Please enter a product name.")
            if not sport_category:
                raise ValueError("Please enter a sport category.")

            update_status("Validating upload...", 5)
            validate_uploaded_artwork(uploaded_file)

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
            update_status("Done", 100, level="success")
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
    log_app_memory("Page load: Product Uploads")
    st.title("Product Uploads")
    st.caption(
        "Use this lightweight prompt page when you already have your Shopify upload images and HTML preview ready to drag into ChatGPT."
    )

    st.info(
        "This page does not scan local runs. Attach your own `shopify-uploads` WEBP files and HTML preview in ChatGPT, then copy one of the prompts below."
    )

    st.markdown(
        "1. Drag every WEBP file from your `shopify-uploads` folder into ChatGPT.\n"
        "2. Drag the matching HTML preview into ChatGPT if you have it.\n"
        "3. Click the copy button on the prompt you need, then paste it into ChatGPT.\n"
        "4. Review the draft Shopify product carefully before publishing.\n"
        "\n"
        "- `New Shopify product` will generate a prompt for creating a brand new product in Shopify.\n"
        "- `Update existing product` will generate a prompt for replacing the images on an existing Shopify product.\n"
        "- This page stays manual on purpose so it remains fast and lightweight on Render."
    )

    st.divider()
    st.write("Both prompts are ready below. Copy the one you need and paste it into ChatGPT under your uploaded files.")

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


def render_limited_editions_page():
    log_app_memory("Page load: Limited Editions")
    st.title("Limited Editions")
    st.caption(
        "Live edition dispatch tracking from the Sports Cave Edition Log. This page stays lightweight and only refreshes the data when you open it or press Refresh."
    )

    action_cols = st.columns([1, 1, 1, 2])
    with action_cols[0]:
        if st.button("Refresh Edition Log", type="primary", use_container_width=True):
            load_limited_editions_snapshot.clear()
            st.session_state.limited_editions_test_result = None
            st.rerun()
    with action_cols[1]:
        if GOOGLE_SHEET_URL:
            render_external_link("Open Edition Log Sheet", GOOGLE_SHEET_URL, "open-edition-log-sheet")
    with action_cols[2]:
        json_url = get_edition_log_json_url()
        if st.button(
            "Test Edition Log URL",
            use_container_width=True,
            disabled=not bool(json_url),
        ):
            st.session_state.limited_editions_test_result = test_edition_log_url(json_url)
            st.rerun()

    connection_status = get_edition_log_connection_status()
    st.caption(
        f"Edition Log JSON URL: {'Found' if connection_status['json_url_found'] else 'Missing'}"
    )

    render_edition_log_test_result(st.session_state.limited_editions_test_result)

    if not json_url:
        render_limited_editions_empty_state()
        return

    try:
        snapshot = load_limited_editions_snapshot(json_url)
    except Exception as error:
        diagnostics = error.diagnostics if isinstance(error, EditionLogEndpointError) else None
        render_limited_editions_load_error(error, diagnostics=diagnostics)
        return

    rows = snapshot["rows"]
    if not rows:
        st.info("No edition log rows were found yet.")
        if GOOGLE_SHEET_URL:
            render_external_link("Open Edition Log Sheet", GOOGLE_SHEET_URL, "open-edition-log-sheet-empty-data")
        return

    latest_row = rows[0]
    submitted_count = sum(1 for row in rows if "submitted" in normalize_whitespace(row.get("status")).casefold())
    latest_edition_sent = normalize_whitespace(latest_row.get("edition_no")) or "-"
    latest_product_sent = normalize_whitespace(latest_row.get("edition_name")) or "Untitled Product"

    metric_cols = st.columns(4)
    metric_cols[0].metric("Total editions logged", str(len(rows)))
    metric_cols[1].metric("Submitted editions", str(submitted_count))
    metric_cols[2].metric("Latest edition sent", latest_edition_sent)
    metric_cols[3].metric("Latest product sent", latest_product_sent)

    with st.expander("Endpoint diagnostics"):
        render_limited_editions_diagnostics(snapshot.get("endpoint_diagnostics"))

    st.divider()
    st.subheader("Latest Editions Sent Out")
    if snapshot.get("had_date_parse_failure"):
        st.caption("Date parsing failed for at least one row, so the dashboard is keeping the original endpoint order.")
    else:
        st.caption("Newest rows first where the date could be parsed. Product links appear whenever a URL or Shopify handle is available.")

    latest_cols = st.columns(2)
    for index, row in enumerate(rows[:12]):
        with latest_cols[index % 2]:
            edition_name = normalize_whitespace(row.get("edition_name")) or "Untitled Product"
            edition_number = normalize_whitespace(row.get("edition_no")) or "-"
            frame = normalize_whitespace(row.get("frame")) or "-"
            size = normalize_whitespace(row.get("size")) or "-"
            status = normalize_whitespace(row.get("status")) or "-"
            shipping = normalize_whitespace(row.get("shipping")) or "-"
            notes = normalize_whitespace(row.get("notes"))

            st.markdown(f"**{edition_name}**")
            st.write(f"Edition #{edition_number}")
            st.caption(f"{frame} / {size}")
            st.caption(f"Status: {status}")
            st.caption(f"Sent: {format_sheet_date(row.get('date_sent'))}")
            st.caption(f"Shipping: {shipping}")
            if notes:
                st.caption(f"Notes: {notes}")
            if row.get("_product_link"):
                render_external_link("Open Product", row["_product_link"], f"open-product::{row['_row_number']}")
            st.markdown("---")

    st.subheader("Recent Dispatch Table")
    st.caption("A quick lightweight table so you can scan the latest editions sent out at a glance.")
    st.dataframe(
        build_limited_editions_table_rows(rows[:25], include_internal=False),
        hide_index=True,
        use_container_width=True,
    )

    st.subheader("Previous Edition Numbers Sent")
    st.caption("Quick product-by-product reference so you can see which edition numbers have already gone out.")
    product_search = st.text_input(
        "Find product",
        placeholder="Start typing a product name...",
        key="limited-editions-product-search",
    )

    history_rows = build_limited_editions_history(rows)
    if product_search.strip():
        search_text = normalize_lookup_name(product_search)
        history_rows = [
            history_row
            for history_row in history_rows
            if search_text in normalize_lookup_name(history_row["edition_name"])
        ]

    if history_rows:
        history_cols = st.columns(2)
        for index, history_row in enumerate(history_rows):
            with history_cols[index % 2]:
                previous_numbers = ", ".join(history_row["edition_numbers"]) if history_row["edition_numbers"] else "-"
                st.markdown(f"**{history_row['edition_name']}**")
                st.caption(f"Previous editions sent: {previous_numbers}")
                st.caption(f"Total logged: {history_row['total_logged']}")
                st.caption(f"Latest sent: {history_row['latest_sent']}")
                if history_row.get("product_link"):
                    render_external_link(
                        "Open Product",
                        history_row["product_link"],
                        f"open-history-product::{normalize_sheet_header_name(history_row['edition_name'])}",
                    )
                st.markdown("---")
    else:
        st.info("No matching products were found for that search.")

    with st.expander("Internal details"):
        show_internal_details = st.checkbox(
            "Show internal order/customer details",
            key="limited-editions-show-internal",
        )
        st.dataframe(
            build_limited_editions_table_rows(rows, include_internal=show_internal_details),
            hide_index=True,
            use_container_width=True,
        )


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


def render_settings_page():
    st.title("Settings")
    st.caption("Current app and environment status.")

    st.write(f"**Password protection:** {get_password_protection_status()}")
    st.write(f"**Edition Log JSON URL present:** {'Yes' if get_edition_log_json_url() else 'No'}")
    st.write(f"**Edition Log sheet shortcut URL present:** {'Yes' if bool(GOOGLE_SHEET_URL) else 'No'}")
    st.write(f"**Google Drive lightweight flag:** {'Enabled' if ENABLE_GOOGLE_DRIVE else 'Disabled'}")
    if ENABLE_GOOGLE_DRIVE:
        st.write("**Google Drive configured:** Open the Google Drive page to inspect the current connection.")
        st.write("**Root folder ID present:** Checked only on the Google Drive page")
    else:
        st.write("**Google Drive configured:** Disabled in lightweight mode")
        st.write("**Root folder ID present:** Not checked while Drive is disabled")
    st.write(f"**OAuth client ID present:** {'Yes' if os.getenv('GOOGLE_OAUTH_CLIENT_ID') else 'No'}")
    st.write(f"**OAuth client secret present:** {'Yes' if os.getenv('GOOGLE_OAUTH_CLIENT_SECRET') else 'No'}")
    st.write(f"**OAuth refresh token present:** {'Yes' if os.getenv('GOOGLE_OAUTH_REFRESH_TOKEN') else 'No'}")
    st.write(f"**Output folder path:** `{RUNS_DIR}`")
    st.write(f"**App version:** {APP_VERSION}")


def render_placeholder_page(title, body):
    st.title(title)
    st.caption(body)


def main():
    inject_styles()
    init_session_state()
    render_sidebar()

    current_page = st.session_state.selected_page
    log_app_memory(f"Page load start: {current_page}")
    if current_page == "Google Drive":
        render_google_drive_page()
    elif current_page == "Limited Editions":
        render_limited_editions_page()
    elif current_page == "Product Uploads":
        render_product_uploads_page()
    elif current_page == "Settings":
        render_settings_page()
    else:
        render_mockups_page()
    log_app_memory(f"Page load end: {current_page}")


main()
