# Shopify-native marketing unsubscribe

## Verified contract

Use `Customer.defaultEmailAddress.marketingUnsubscribeUrl`, fetched alongside
`emailAddress`, `marketingState`, and `validFormat` in existing customer list,
individual, batch, and lightweight campaign-subscriber queries. Shopify 2026-04
(the repository default API version) documents these fields:
https://shopify.dev/docs/api/admin-graphql/2026-04/objects/CustomerEmailAddress

All four modified queries passed Shopify schema validation. Existing legacy
email/consent fields are retained for compatibility and checked conservatively;
validation notes that Shopify has deprecated them. No API version was changed.

A read-only Shopify connector query returned a native URL for a subscribed,
valid customer and reported `read_customers` plus `write_customers` access.
Only availability was reported; no complete URL, token, email, or customer ID was
printed. No unsubscribe URL was opened. The URL uses the store's public domain;
validation must not assume all Shopify-supplied URLs have a shopify.com hostname.
The local OS Shopify credentials are absent, so this check used the connected
Shopify tool rather than the locally configured OS transport.

## Production path

Final audience preparation validates URLs from the same freshly fetched profiles.
Missing/unsafe URLs stop queue preparation with a concise error; zero new jobs
are inserted. There is no per-customer URL lookup.

The worker's existing fresh customer read includes the URL. It verifies matching
email identity, valid format, subscribed consent, and a public HTTPS destination.
A missing URL records `missing_shopify_marketing_unsubscribe_url` and blocks that
receipt before provider submission. No fallback token is synthesized.

The unchanged footer placeholder receives that URL through the existing renderer.
Provider-signed opt-out URLs bypass tracking cleanup. `List-Unsubscribe` uses the
same URL. `List-Unsubscribe-Post` is omitted for future native-link messages:
Shopify's field documentation does not verify RFC 8058 POST semantics. The
transport retains explicit one-click capability for verified compatibility
callers, rather than assuming it for every URL.

## Consent and compatibility

Native UNSUBSCRIBED (or another ineligible native state) vetoes delivery even if
a legacy consent field says SUBSCRIBED. Legacy opt-outs also remain restrictive.
Local and provider suppression checks remain in place. This applies to AU, US,
UK and all eligible countries in All subscribers. Final eligibility stays fresh.

`CRM_UNSUBSCRIBE_SECRET` and the custom public base are no longer prerequisites
for normal future production sending. Do NOT delete or rotate the deployed
secret: `/crm/unsubscribe` and its existing HMAC verifier, local suppression,
Shopify sync, retry and audit behavior still support previously issued links.

Send Test and previews retain the harmless `/crm/unsubscribe/test` route and
never receive a real customer's native URL. Keep `CRM_PUBLIC_BASE_URL` configured
for those links and historical custom routes. Marketing remains OFF.

## Files for this change

- crm_shopify.py, crm_native_unsubscribe.py
- crm_logic.py, crm_eligibility.py, crm_audience.py, crm_campaign_markets.py
- crm_campaign_send.py, crm_engine.py, crm_resend.py, crm_campaign_content.py
- tests/crm_fixtures.py, tests/test_crm_native_unsubscribe.py
- tests/test_crm_boundaries.py, tests/test_crm_campaign_v2.py
- tests/test_crm_footer_urls.py, tests/test_crm_send_flow.py

No schema migration, authentication system, footer redesign or production
configuration change is introduced.

## Local validation

294 CRM tests passed; 143 Email tests passed, one skipped. Sixteen affected Python
files compiled; git diff --check passed. Tests use synthetic customer URLs,
mocked email transports and disposable loopback SQL. Production-enable flags are
mocked only in isolated test configuration objects; no deployment flags changed.
The tests cover queue preparation without a signing secret, missing URL blocking,
per-recipient worker URLs, one existing customer read, exact signed URL retention,
preview/test isolation, consent/suppression exclusions, and old custom links.
No real email, customer consent change, commit, push or deployment occurred.
