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
- Judge.me private API credentials remain on the server.

The browser never receives Shopify Admin credentials, Judge.me private tokens,
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

Create one active Shopify product:

- Title: `Framed Collector Certificate`
- Handle: `framed-collector-certificate`
- One variant: premium black frame, A4 landscape
- Real Shopify price and inventory/availability configuration

Configure:

```text
FRAMED_CERTIFICATE_PRODUCT_HANDLE=framed-collector-certificate
FRAMED_CERTIFICATE_VARIANT_ID=gid://shopify/ProductVariant/...
```

The offer is intentionally hidden if the product or safe variant mapping cannot
be resolved. Price and currency are fetched contextually through Shopify at
render time; checkout remains authoritative.

## Judge.me

Configure the existing Judge.me account:

```text
JUDGEME_PRIVATE_API_TOKEN=...
JUDGEME_SHOP_DOMAIN=your-store.myshopify.com
```

The API maps reviews by stable Shopify product ID, checks customer ownership,
requires a Shopify `DELIVERED` fulfillment event, blocks duplicate submissions,
rate limits retries, and validates/re-encodes JPG, PNG, and WebP photos before
temporary private upload.

Judge.me's public API cannot force an API-created review to carry its verified
badge. The Sports Cave API still enforces verified purchase and delivery. Keep
Judge.me's own review-request email as the only email system and set it to
delivered date plus seven days in the Judge.me dashboard.

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
