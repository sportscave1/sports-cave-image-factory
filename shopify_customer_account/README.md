# Sports Cave Customer Account Extension

The `customer-certificate-vault` extension provides the Sports Cave Collector
Vault as a Shopify Customer Account full page.

## Architecture

- Shopify owns customer sign-in and issues the extension session token.
- The extension sends that token to the Sports Cave OS Collector Vault API.
- The API verifies signature, expiry, audience, shop, and customer subject.
- Supabase remains the source of truth for orders, editions, certificates,
  framed requests, and review-submission state.
- Certificate previews and downloads use short-lived signed proxy URLs.
- Shopify Storefront API supplies contextual frame price, currency,
  availability, cart creation, and checkout.
- Shopify Admin API is used server-side for stable product/variant validation
  and confirmed delivery events.
- Native reviews use the existing OS and Dropbox configuration.

The browser never receives Shopify Admin credentials,
Supabase service-role credentials, R2 credentials, permanent private asset URLs,
customer email addresses, or local storage paths.

## Required Access

The app retains the existing Admin and Customer Account scopes, including:

- `read_customers`
- `read_orders`
- `read_products`
- `customer_read_customers`
- `customer_read_orders`

The extension requires:

```toml
[extensions.capabilities]
api_access = true
network_access = true
```

Shopify must approve external network access for the released extension version.
Set `api_base_url` in the checkout and accounts editor only when it differs from
the production default.

## Database

Apply:

```text
migrations/20260723_collector_vault.sql
```

This additive migration creates:

- `collector_frame_requests`
- `collector_reviews`

Both tables have RLS enabled and no browser-facing policy. They are accessed by
the existing trusted server connection. Existing certificate, order, edition,
allocation, and certificate-generation tables are unchanged.

## Framed Certificate Product

Configure one Shopify product:

- Title: `Framed Collector Certificate`
- Handle: `framed-collector-certificate`
- Three A4 landscape variants: Black (`SC-FCC-A4-BLK`), Oak
  (`SC-FCC-A4-OAK`), and White (`SC-FCC-A4-WHT`)
- Real Shopify price and inventory/availability configuration

Configure:

```text
FRAMED_CERTIFICATE_PRODUCT_ID=gid://shopify/Product/...
FRAMED_CERTIFICATE_PRODUCT_HANDLE=framed-collector-certificate
FRAMED_CERTIFICATE_VARIANT_ID=gid://shopify/ProductVariant/...
```

The product and variant GIDs are authoritative; the handle is discovery-only.
The configured variant remains the original Black variant. Oak and White are
resolved by their exact SKU within that same verified product. Available colors
are checked again before creating a framing request. Free unframed certificates
use the existing Download Print action, never a paid Shopify variant.
The offer is intentionally hidden while the product is Draft, unpublished,
unavailable, or the safe variant/SKU mapping cannot be resolved. Price and
currency are fetched contextually through Shopify at render time; checkout
remains authoritative.

Account previews use the existing upload mockup templates and artwork placement
box, containing the owner's signed certificate image without cropping. Signed
preview URLs accept `frame=black|oak|white`; print and PDF assets are unchanged.
The account's Build your collection section uses the existing smart catalogue
resolver, then fetches current Storefront variants and prices. Its four cards
share a cart during the page session.

## Native reviews

My Collection retains the purchased-product lifestyle image and sends review text,
photos and video to authenticated Sports Cave OS endpoints. The OS verifies purchase
ownership, prevents duplicates and stores originals in Dropbox before background
optimisation. Post Checkout owns requests and approved-media rewards. No external
review provider credentials are required.

## Local Checks

```bash
cd shopify_customer_account
npm run test:vault
shopify app config validate --json
shopify app build
```

The full-page extension must be added to the customer account menu as
`My Collection` in Shopify's checkout and accounts editor.

## Platform Boundary

Shopify renders full-page extensions inside its native customer-account shell.
The extension cannot remove, restyle, or access the host account sidebar/header
DOM. Navigation and visual branding outside the extension must be configured in
Shopify's customer-account editor. Inside the page, the Collector Vault uses
Shopify's native accessible components, responsive layout, modal focus handling,
and merchant branding tokens.
