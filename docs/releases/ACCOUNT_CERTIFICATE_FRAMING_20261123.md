# Account certificate framing and collection upsells

User authorization: implement the requested account changes, commit/push to Git,
and release to the existing Render application and Shopify app (23 November 2026).
Task: `20261123-f77161d6`; owner: `codex-certificate-20261123-unique`.
The isolated task was fast-forwarded from Studio's approved base to the verified
live production revision `beac8e592e30e379081cdc5e6d8de1682aa03d9a` before edits.

Certificate cards retain View Certificate and Download Print. Get Certificate
Framed replaces Download PDF. Previews insert the owner's signed certificate
into the existing upload mockup templates, preserving the complete document.
The viewer switches Black, Oak, White, or the free unframed print. Paid variants
are verified within the configured certificate product and rechecked before
creating the owner-bound request. Paid-order matching checks each request and
variant together. No database schema or Render topology changes are required.

Build your collection reuses the smart catalogue's exact sport membership,
purchase exclusion, edition eligibility, sales ranking and balancing helpers.
All purchase ID formats and owned certificates contribute to exclusions.
Up to eight ranked candidates are checked by the authenticated account's native
Storefront token to display four available frame/size cards with current prices.
No additional server Storefront credential is required.
Adds are serialized into a shared cart for the page session. Checkout remains
authoritative for availability, currency, tax, and delivery.

The existing Shopify product `10332579103027` preserves the Black variant
`53700496261427`. Oak is `68066069938483`; White is `68066069971251`.
All three retain the existing AU$99 pricing and made-to-order inventory policy.
The product was published only to the Online Store for checkout availability.

Validation:

- `python -m unittest tests.test_collector_collection_offers tests.test_collector_vault tests.test_customer_certificate_vault tests.test_crm_smart_catalogue -q`:
  87 tests, 81 passed and 6 database integration tests skipped.
- `npm --prefix shopify_customer_account run test:vault`: 15 passed.
- `shopify app config validate --path shopify_customer_account --json`: valid.
- `shopify app build --path shopify_customer_account`: successful.
- Shopify Admin mutations and new Storefront operations passed skill schema validation.
- The skill's separate component validator is unavailable: bundled types/index.json
  is absent (after resolving its missing TypeScript dependency). Local Shopify
  build and configuration validation pass.
- `python scripts/validate_render_topology.py`: passed; Blueprint unchanged.
- Broader smart matching suite has one existing fixture failure: the October 7
  audit omits `darts-wall-art`, which the current taxonomy allows. No matching or
  taxonomy implementation was changed in this release.
- Generated sample previews were visually inspected using the repository's blank
  certificate template; no customer data or production credentials used locally.

Release verification is recorded in Developer Studio after deployment. Preserve
the canonical `sports-cave-os` service and the supporting webhook service; this
release must not sync or create any Blueprint resources.

Live verification exposed an existing unfinished Shopify secret rotation: the
webhook receiver accepted the older active signing secret, while the primary
service only held the newer OAuth secret. With the user's explicit credential
sync authorization, the same active verification fallback was configured on the
primary service. Both secrets remain active; no key was created or revoked.
Safe authentication failure-stage logging contains no token or claim values.
