# Customer-like automation Send Test

Implemented locally on 2026-10-09. No deployment, commit, live email, Shopify mutation, automation publication or production database change was performed.

## Behavior

The existing Send test popover, recipient field, Send button, spinner and durable operation ID remain. No second mode or configuration screen was added.

For abandoned-checkout automations, Send Test now verifies the addressed internal recipient and finds their newest matching incomplete checkout. It never uses the editor's cached preview or sample product for delivery. It verifies both the linked Shopify customer and the separate checkout contact email, original recovery URL, variant IDs, quantities, complete line items, prices and availability. Unavailable or inconsistent evidence stops the send.

The verified checkout passes through the existing discount validation, personalization, checkout hydration, sanitization and production email renderer. Configured recovery buttons, images and swatches retain the same original checkout destination, including opaque parameters and fragments. Wall Preview remains a separate product destination. The automation test subject no longer receives a `[CAMPAIGN TEST]` prefix. Existing Campaign Send Test behavior retains its prefix and permissions.

Samples and unsupported preview/test contexts still disable recovery links. No blanket security restriction was removed. Previously published documents and frozen journeys are unchanged.

## Authorization and Shopify requirements

The sender must be an active administrator. Permitted recipients are that administrator's account email, `SPORTS_CAVE_ADMIN_EMAIL`, or the deployment-admin `CRM_INTERNAL_TEST_RECIPIENTS` allowlist (comma, semicolon or newline separated). No recipient list is trusted from editor state. Existing verified Shopify default-email, marketing-consent, suppression and native-unsubscribe checks remain.

The new newest-first GraphQL query was accepted by Shopify's schema validator; it requires `read_orders` and `read_customers`. The existing `Customer.email` field is supported but deprecated. The installed store's permissions were not changed or freshly checked for this task.

GraphQL's AbandonedCheckout exposes the linked customer email but not a separate checkout contact-email field. The implementation therefore makes a read-only, authenticated REST abandoned-checkout lookup for the exact candidate, constrained by creation time and ID, using the existing Shopify token and configured API version. It checks the returned checkout's own `email`. It does not fetch the private recovery URL. REST access is legacy and must remain available to the installed app; inaccessible contact evidence causes a clear safe hold, not a fallback to another customer.

References: [Shopify abandoned-checkout REST resource](https://shopify.dev/docs/api/admin-rest/latest/resources/abandoned-checkouts), [GraphQL abandonedCheckouts](https://shopify.dev/docs/api/admin-graphql/2026-04/queries/abandonedCheckouts).

## Delivery and retry safety

- Only the existing internal Resend transport and `crm_internal_tests` receipts are used.
- Accepted-operation replay returns the persisted receipt before customer/checkout reads or provider submission.
- Requested or uncertain outcomes cannot be automatically resent. Receipt identity continues to include recipient, document version/hash, automation and email step.
- No enrollment, scheduling, marketing-send record, edition allocation, checkout creation, order creation or consent mutation was added.
- Production attribution identifiers are not introduced; existing test tracking remains active for eligible public product links. Private recovery destinations are preserved exactly.
- Configured discounts use existing fresh eligibility and conflict checks. Inactive/unverifiable/conflicting offers stop delivery. Including a discount in a URL is not treated as proof Shopify applied it.
- Logs contain exception classes rather than checkout tokens or response payloads.

## Performance and limits

The initial search reads only metadata, newest first, in pages of 25, with a maximum of five pages (125 recent checkouts). Full checkout data and the contact record are read only for an exact customer/email candidate. The search checks a 30-second elapsed budget between operations; individual calls retain the existing bounded GraphQL timeout/retries, and the contact GET has a 10-second timeout without redirects. This is not a hard 30-second total deadline for in-flight requests.

There is no cross-recipient checkout cache. Facts are reused during one rendering operation, and accepted receipt replay makes no additional checkout calls. Optional edition reads are not repeated by the initial structural validation. Opening/editing the email adds no new Shopify lookup; the lookup occurs at Send.

An older checkout outside the bounded recent window requires creating a new abandoned checkout with the authorized address. Production Shopify latency was not benchmarked, and no claim of faster live sending is made. The clean disposable regression run completed in 18.679 seconds.

## Verification

174 focused tests passed with mocked Shopify/Resend and disposable loopback PostgreSQL. Suites: customer test, recovery elements, abandoned checkout, preview fallback, Wall Preview, frame banner, personalization, discounts, discount delivery, native automations and Campaign Send Test.

Coverage includes exact contact ownership, newest-first pagination, mismatch/completed/invalid product failure, authorization, sanitized contact-read errors, real rendered pricing and variants, exact recovery destinations, lifestyle/product images and swatches, independent Wall Preview, discount-bearing internal delivery, personalized subjects/preheaders, sample restrictions, unchanged production delivery/frozen journeys, no enrollment/marketing/edition writes, accepted retry and uncertain-provider duplicate prevention. Existing Streamlit AppTests exercise the unchanged popover. `git diff --check` passed.

Earlier runs reused a disposable database and hit existing frequency guards; the final result above used a fresh fixture. No live inbox or live recovery-link click was performed. Existing Streamlit deprecation warnings remain unrelated to this change.

## Files changed for this request

- `crm_test_checkout.py` (new): recipient-owned checkout verification and production hydration.
- `crm_test_recipient.py`: reusable verified customer and server-owned internal-recipient authorization.
- `crm_shopify.py`: separate newest-first test metadata query; production discovery unchanged.
- `crm_automation_store.py`: verified checkout dispatch; verified customer personalization for non-checkout tests.
- `crm_campaign_send.py`: authorization and shared authoritative send boundary.
- `crm_campaign_store.py`: receipt-first replay, verified rendering and final recovery-link checks.
- `crm_campaign_send_ui.py`: compact explanation in the existing popover.
- `tests/test_crm_customer_test.py` (new): ownership, rendering, transport and safety regressions.
- `tests/test_crm_native_automations.py`, `tests/test_crm_discount_delivery.py`, `tests/test_crm_personalisation.py`: updated test expectations for the authorized recipient-owned path.
- This report.

## Deployment prerequisites

No database migration is required. Before separately authorized deployment, verify the installed app can read both GraphQL checkout/customer data and the REST checkout contact record, and ensure the administrator's intended address is authorized and has a recent incomplete checkout. Additional internal addresses may be configured in the server allowlist. Existing consent/unsubscribe requirements still apply. No app permissions were altered.
