# Sports Cave Customer Account Extension

Customer Certificate Vault V1 lives in this Shopify Customer Account UI Extension.
It is separate from the Streamlit Sports Cave OS runtime and does not use
Supabase or any customer-facing backend.

## What It Reads

The extension reads the logged-in customer's own orders through Shopify's
Customer Account API:

```graphql
customer {
  id
  orders(first: 50, reverse: true) {
    nodes {
      id
      name
      processedAt
      metafield(namespace: "sports_cave", key: "certificates_json") {
        type
        jsonValue
        value
      }
    }
  }
}
```

The source of truth is the Shopify order metafield:

- namespace: `sports_cave`
- key: `certificates_json`
- type: `json`

The extension does not accept customer IDs, order IDs, emails, or line item IDs
from frontend input. Shopify scopes the query to the currently authenticated
customer.

## Required Access

The Shopify app config must request these Customer Account API scopes:

- `customer_read_customers`
- `customer_read_orders`

These are separate from Admin API scopes such as `read_customers` and
`read_orders`. Keep `[extensions.capabilities] api_access = true` in
`extensions/customer-certificate-vault/shopify.extension.toml`.

This extension reads Shopify order metafields directly and does not call a
Sports Cave OS or Supabase endpoint, so `network_access` is not enabled.
Certificate PDFs, lightweight preview images, and print-quality JPG files are
stored in Shopify Files/CDN; the extension only reads the mirrored order
metafield metadata and opens the CDN asset URLs.

The certificate image asset upload path also needs these Admin API scopes:

- `read_images`
- `write_images`

## Store Setup Verified

Live Admin API check on 2026-06-23:

- shop: `Sports Cave`
- myshopify domain: `sportscave-nb.myshopify.com`
- customer account version: `NEW_CUSTOMER_ACCOUNTS`
- customer account URL: `https://account.sportscaveshop.com`
- login links visible: `true`

## Local Development

Link this folder to the real Shopify Partner app before deploying:

```bash
cd shopify_customer_account
shopify app config link
shopify app dev
```

If Shopify CLI asks to update `client_id` or app URLs in `shopify.app.toml`,
accept the generated local changes. Do not commit secrets.

## Deploy

```bash
cd shopify_customer_account
npm install
shopify app deploy
```

The app needs customer/order access suitable for reading the logged-in
customer's order history and order metafields. Protected customer data access
must be approved in Shopify before the extension can go live.

After any scope change:

1. Release a new Shopify app version.
2. Confirm the app scopes include `customer_read_customers` and `customer_read_orders`.
3. Approve/update the new permissions in Shopify Admin.
4. If access denied persists, uninstall/reinstall the app after the new version is released.
5. Test the customer account preview with a certificate order.
6. Confirm the certificate card appears and certificate links open in a new tab.

## Navigation

After deploy:

1. Open Shopify Admin.
2. Go to **Settings > Customer accounts**.
3. Open the checkout and accounts editor.
4. Add the full-page extension to the customer account header menu.
5. Use menu label: `My Collection`.
6. Page title shown by the extension: `My Collection`.

Shopify's full-page extension flow prompts for customer account menu placement
when the extension is added.

## QA Checklist

- Customer with one certificate sees one certificate.
- Customer with multiple orders sees multiple certificates.
- Quantity 2 order shows two certificate cards from the same order metafield.
- Customer cannot see another customer's certificates because the query is
  scoped by Shopify customer authentication.
- Customer with no certificates sees the empty state.
- Missing preview image shows the premium preview placeholder.
- Missing or non-ready PDF shows `Certificate processing`.
- Mobile uses stacked Shopify UI extension components.
- Failure in this extension does not affect storefront, product page widget,
  Orders, edition allocation, certificate generation, or Shopify Files upload.
- No secrets, tokens, API keys, or Supabase access are in frontend code.
