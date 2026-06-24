# Sports Cave OS

Private Streamlit operations app for Sports Cave staff. Phase 5B combines the
existing Image Factory, Product Command Centre, link-based Google Drive asset
workflow, Shopify product sync, and the backend-led limited edition engine.

## Active Workflows

- Dashboard priorities for product readiness, missing files, and asset review
- Product creation, filtering, editing, archiving, links, edition data, and VA notes
- Product File Hub with grouped Drive links and asset approval statuses
- Files dashboard for missing, connected, review, and approved asset packs
- Product Upload workflow board grouped by VA stage
- CSV product backup/export including file links and asset statuses
- Backend-led limited-edition tracking for synced Shopify products
- Manual Shopify Admin GraphQL catalog sync from the Limited Editions page
- Manual Shopify order sync with automatic paid-order edition assignment
- Storefront edition metafield mirror for the exact next available edition
- Cached Shopify variants, image links, tags, collections, and metafields
- Existing mockup generation, previews, prompts, and ZIP downloads

The sidebar still includes placeholders for Marketing Factory and VA Training.
Customer Certificate Vault V1 is a Shopify Customer Account UI Extension in
`shopify_customer_account/` and reads Shopify order metafield
`sports_cave.certificates_json`.

## Customer Account Certificate Vault

The customer account vault requires the Shopify Customer Account API scopes
`customer_read_customers` and `customer_read_orders` in addition to the Admin API
scopes used by Sports Cave OS. The customer account extension must keep
`api_access = true`; `network_access` is only needed if an external Sports Cave
OS endpoint is introduced later.

Certificate PDFs are stored in Shopify Files/CDN. Certificate ownership records
are stored in Supabase for Sports Cave OS operations, and Shopify order
metafields mirror the customer-facing certificate metadata:

- `sports_cave.certificate_status`
- `sports_cave.certificate_count`
- `sports_cave.certificates_json`

After changing scopes, release a new Shopify app version, approve the updated
permissions in Shopify Admin, and reinstall/update the app if access-denied
messages persist. Then test the customer account page with a real certificate
order and confirm the Download Certificate button opens the Shopify CDN PDF.

## Database

Product, asset status, and limited-edition records are stored in SQLite at
`data/sports_cave_os.db`. Override this location with `SPORTS_CAVE_DB_PATH`.

Render's normal filesystem is ephemeral. Attach a Render persistent disk and
point `SPORTS_CAVE_DB_PATH` to that mounted path if records must survive a
redeploy. Database migrations only add missing tables and columns; they do not
delete existing products, edition records, or output folders.

## Local Run

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Start the app:

```bash
python -m streamlit run app.py
```

You can also use `start-app.bat` on Windows.

## Google Drive Link-Based Mode

Phase 3 stores Google Drive file and folder URLs on each product record. It does
not require Google OAuth, a Drive Picker, or full Drive API sync. VAs open the
connected links from Product Detail or the Files dashboard and manually save
generated ZIPs into the correct product folder.

Recommended structure:

```text
Sports Cave Products
└── [Product Name]
    ├── 01 PSD
    ├── 02 Final JPG
    ├── 03 Shopify Images WebP
    ├── 04 Mockups
    ├── 05 Lifestyle ChatGPT
    ├── 06 Prompt Pack
    ├── 07 Certificates
    └── 08 Ads Social
```

Full Drive API sync, OAuth, and a Drive Picker are intentionally deferred until
the link-based file workflow is stable.

## Shopify Products, Orders, And Editions

Phase 5B uses Shopify's Admin GraphQL API only when a staff member clicks a sync
button on `Limited Editions` or `Orders`. No Shopify request runs during mockup
generation or normal page loads.

Add these environment variables locally or in Render:

```text
SHOPIFY_STORE_DOMAIN=your-store.myshopify.com
SHOPIFY_API_VERSION=2026-04
SHOPIFY_CLIENT_ID=your-dev-dashboard-client-id
SHOPIFY_CLIENT_SECRET=your-dev-dashboard-client-secret
# Optional legacy mode; preferred over client credentials when present:
SHOPIFY_ADMIN_ACCESS_TOKEN=shpat_...
SHOPIFY_SYNC_MAX_PRODUCTS=500
SHOPIFY_SYNC_MAX_ORDERS=250
# Optional; defaults true:
SHOPIFY_AUTO_SYNC_EDITION_WIDGET=true
```

Sports Cave OS prefers a configured legacy Admin API token. Otherwise it uses
the Shopify Dev Dashboard client credentials grant and caches the temporary
access token in process memory until shortly before expiry. Keep every credential
in Render environment variables and never commit it. Product metadata is cached
in the local SQLite database; image URLs are stored, but image files are not downloaded.

Required Shopify app scopes for Phase 5B:

- `read_products`
- `write_products`
- `read_orders`

The backend database is the source of truth for edition numbers. Shopify
metafields are only a storefront display mirror. Edition availability must not
be based on Shopify inventory, stock, or variant inventory.

The storefront snippet lives at
`shopify_theme/snippets/sports-cave-edition-pill.liquid` and reads only the
`sports_cave` product metafields synced from Sports Cave OS.

Matching rules:

1. Existing Shopify product IDs are matched first.
2. A unique exact handle match is connected automatically.
3. Title-only matches are suggestions and require manual confirmation.
4. Unmatched Shopify products can create a new internal master record.

## Mockup Workflow

1. Open `Mockups`.
2. Upload the finished artwork.
3. Confirm the product name and sport category.
4. Generate the five core Shopify images.
5. Review lightweight previews or load full resolution only when needed.
6. Download the final ZIP.
7. Save the ZIP into the correct Google Drive product folder.
8. Add the Drive folder or ZIP URL to the product File Hub.

Mockup generation continues to use local `output/runs/...` working folders and
does not call the Phase 3 asset database while images are being generated.

## Notes

- Never commit credentials to GitHub.
- `.env`, OAuth files, `output/`, and local database files are ignored by git.
- Full-resolution mockups and ZIP generation remain separate from the link-based File Hub.
