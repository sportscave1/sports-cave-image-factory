# Sports Cave Customer Account Extension

Customer Certificate Vault V1 lives in this Shopify Customer Account UI Extension.
It is separate from the Streamlit Sports Cave OS runtime and does not use
Supabase or any customer-facing backend.

## What It Reads

The extension reads the logged-in customer's own orders through Shopify's
Customer Account API:

```graphql
customer {
  orders(first: 50, reverse: true) {
    nodes {
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

## Navigation

After deploy:

1. Open Shopify Admin.
2. Go to **Settings > Customer accounts**.
3. Open the checkout and accounts editor.
4. Add the full-page extension to the customer account header menu.
5. Use menu label: `My Collection`.
6. Page title shown by the extension: `My Sports Cave Collection`.

Shopify's full-page extension flow prompts for customer account menu placement
when the extension is added.

## QA Checklist

- Customer with one certificate sees one certificate.
- Customer with multiple orders sees multiple certificates.
- Quantity 2 order shows two certificate cards from the same order metafield.
- Customer cannot see another customer's certificates because the query is
  scoped by Shopify customer authentication.
- Customer with no certificates sees the empty state.
- Missing or non-ready file shows `Certificate processing`.
- Mobile uses stacked Shopify UI extension components.
- Failure in this extension does not affect storefront, product page widget,
  Orders, edition allocation, certificate generation, or Shopify Files upload.
- No secrets, tokens, API keys, or Supabase access are in frontend code.
