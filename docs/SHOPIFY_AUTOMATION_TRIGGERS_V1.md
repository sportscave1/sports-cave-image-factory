# Shopify Automation Triggers V1

## Current verification status

Implemented locally and tested with disposable loopback PostgreSQL and mocked
Shopify/Resend. No installed Sports Cave credentials were available in the shell,
`.env`, or Streamlit secrets. No live subscriptions were created, pixel activated,
customer changed, or email sent. No trigger is claimed LIVE. No WebPixel ID exists
from this task. Shopify Customer Events connection remains unverified.

The local Shopify CLI attempted authentication before config validation; that
process was stopped without completing authentication. TOML parsing and fixture
tests do not substitute for `shopify app config validate --json`. The new pixel
extension still needs its Shopify-managed UID assigned during the authenticated
extension registration/release workflow. Do not invent an extension UID.

## Sources and boundaries

The installed app is checked through the OS's existing Shopify credentials and
matched against the canonical app's client ID. Connector-app permissions are not
used as evidence. `write_pixels`, `read_customer_events`, `write_marketing_events`
are separately diagnosed. Server triggers require current verified read scopes,
matching callbacks, and webhook serialization version **2026-04**. Checks run in
the worker every five minutes or explicitly from the admin script. Publishing
and entry fail closed without a diagnostic newer than ten minutes.

Required subscriptions reuse `scripts/register_crm_webhooks.py`:

* `customers_email_marketing_consent/update`
* `checkouts/create`
* `checkouts/update`
* `orders/create`
* `orders/paid` (existing signed orders-paid endpoint may forward to CRM)
* `orders/fulfilled`

Existing topics and other registered callbacks remain intact. A subscription at
a different callback is reported for review rather than duplicated.

HTTP requests verify raw-body HMAC and store domain, persist minimal normalized
facts transactionally, then acknowledge. Shopify/Resend reads, rendering and
enrollment run only in the existing CRM worker. Retries use the Shopify event ID
(or webhook ID fallback), plus stable consent version/order/checkout journey keys.

Welcome requires an explicitly subscribed consent payload, a matching fresh
Shopify consent version, and future activation time. Minimal consent-state/version
control records reject unchanged or out-of-order updates; they are not a customer
profile mirror. Missing/contradictory evidence does not enroll anyone.

Paid and fulfilled use distinct exact topics and fresh order validation.
Fulfilled is not described as delivered. The same source order cannot create a
second journey on retry or republish; normal re-entry protections still apply.

## Checkout lifecycle

Checkout webhook `token` and order webhook `checkout_token` become the same
SHA-256(shop-domain + token) key. Raw tokens, recovery URLs, email addresses,
addresses and payload bodies are not persisted or logged. Neither removed
webhook `id`/`checkout_id` nor cart IDs are used for correlation.

1. Signed checkout event stores last activity, known customer, source event ID.
2. Qualification threshold (default one hour, configurable 1 minute–7 days) is
   separate from the first email delay.
3. A bounded Admin abandoned-checkout page resolves only signed, future ledger
   entries. The exact token in the authoritative recovery URL and customer must
   match before using the real Admin checkout GID. No GID is synthesized.
4. Fresh customer consent, suppressions, rules and checkout completion are checked.
5. Entry freezes normal Automation V1 email/version steps and preserves the
   source event ID and checkout key.
6. Every recovery email rechecks the fresh Admin checkout and local completion.
7. An order event atomically marks the token ledger RECOVERED at ingestion. The
   worker marks matching journeys `CHECKOUT_RECOVERED` and blocks PENDING/CLAIMED
   steps. The final submission claim locks and rechecks the completion ledger.

Receipts already SUBMITTING/ACCEPTED are retained and never replayed/cancelled as
though unsent. A purchase occurring after submission was already committed cannot
recall a message already handed to transport. New steps cannot claim submission
after the signed completion guard commits.

States: OPEN → ABANDONED → RECOVERY_EMAIL_SENT → RECOVERED. Late checkout updates
cannot revert RECOVERED. Only matching commerce/fresh completion evidence marks
recovery; an unrelated customer's order is not a token match.

No existing abandoned checkout is enrolled without the new signed ledger and a
created-at watermark after automation activation. Unknown customer identities,
unmatched URLs and unstable/incomplete pagination remain held. Older legacy
automation behavior is retained; these new native triggers do not backfill it.

## Rules and analytics

Simple AND fields: Market, Customer country, Checkout country (checkout only),
Product purchased and Order value (paid/fulfilled only). Order values explicitly
include currency, for example `AUD 100`, and use the fresh Shopify shop-money
amount. Product-ID checks use the fresh order line items, bounded pagination only
when required; no product/title/collection scans or per-product network enrichment.
Collection/title rules are not exposed without complete authoritative mappings.

Fresh rules are also checked before delivery. All existing consent, suppression,
smart sending, unsubscribe, tracking, production-size and idempotency boundaries
remain. Sends use the same queue, Resend receipts/events and attribution matcher.
Attribution evidence additionally retains source event ID and checkout hash.
Marketing and mirror environment flags are not changed.

## App Web Pixel

Extension: `shopify_customer_account/extensions/sports-cave-automation-pixel/`.
Official SDK pinned to 2.18.0. Strict sandbox; analytics and marketing privacy
purposes required. The SDK privacy state is rechecked for every event, including
after consent revocation. No script injection or subscribe-all listener.

Six events only: product_viewed, product_added_to_cart, product_removed_from_cart,
cart_viewed, checkout_started, checkout_completed. No email, name, address, URLs,
checkout tokens, payload bodies or private credentials leave the pixel.

Settings: endpoint, shop, ingestionId (public identifier, **not a secret**).
`/shopify/customer-events` enforces bounded schema/body/rate, configured app context,
consent flags, timestamps and allowed origins (including strict-worker null Origin
and the authoritative store primary domain). Client IDs are hashed on receipt.

Browser events remain **untrusted telemetry**, including checkout_completed.
Neither public settings nor Origin authenticate a customer. Pixel data cannot
enroll anyone, recover a checkout or send email. Secure identity stitching is not
available in V1; behavioral triggers are explicitly coming/identity-dependent.

Activation checks the app-scoped `webPixel` before `webPixelCreate`, persists intent
before mutation for interruption recovery, and stores returned ID/settings after
success. A failed lookup is not treated as absence. Different existing settings
require review; no duplicate creation or automatic replacement occurs. Installed
is not the same as verified Connected in Shopify Customer Events.

## Shopify recovery reporting: integration still required

`write_marketing_events` alone does not supply the necessary IDs. Official
`abandonmentUpdateActivitiesDeliveryStatuses` needs a legitimate Abandonment ID
and MarketingActivity ID from Shopify's marketing automation/Flow action context.
There is no such extension/action callback in this repo. Ordinary checkout tokens
and AbandonedCheckout GIDs are not substitutes.

Required future integration: a Shopify Flow marketing action extension, its
authenticated action callback, app-owned marketing activity creation/update and
durable linkage of the callback's abandonment/activity IDs to the native journey.
Only then report SENT after actual provider acceptance (with delivery timestamp),
or NOT_SENT after a known rejection under that workflow's semantics. This release
does not call the mutation, fabricate IDs, or report Shopify recovery status.

Official references:
* https://shopify.dev/changelog/posts/removed-checkout-id-from-checkouts-and-orders-webhooks
* https://shopify.dev/docs/api/webhooks/2026-04
* https://shopify.dev/docs/apps/build/marketing/build-web-pixels
* https://shopify.dev/docs/apps/build/marketing/automations/create-marketing-automation-actions

## Post-deployment procedure (not executed here)

1. Apply reviewed CRM migrations via the existing deployment mechanism. Deploy the
   OS/webhook/worker code together; no new Render service is needed.
2. In the authenticated existing Shopify app project, assign/register the pixel
   extension's UID, run `shopify app config validate --json`, build/test and release
   that extension. This is extension delivery, not evidence that another merchant
   permission is needed; the approved permissions remain the intended set.
3. In the connected server environment run
   `python scripts/shopify_automation_diagnostics.py`. Confirm canonical app ID,
   installed scopes, callback URLs and 2026-04 versions. Do not publish on failure.
4. Inspect subscriptions with `python scripts/register_crm_webhooks.py --automation-only`; apply only
   missing ones using `--automation-only --apply` after the new endpoint is deployed. Review any
   existing different callback; do not duplicate it.
5. Activate once with `python scripts/shopify_automation_diagnostics.py
   --activate-pixel --extension-and-endpoint-deployed --endpoint
   https://<existing-webhook-host>/shopify/customer-events`. Repeated invocations
   recover the persisted identical setup. No production email is sent by this script.
6. Check Shopify Admin → Settings → Customer events for the actual app pixel
   connection. Record its real WebPixel ID and live connection status.
7. Use one explicitly authorized test subscriber and future-only test automation.
   With production marketing disabled, verify a new subscribed consent event
   enters once, duplicate/unchanged/pending/unsubscribe events do not. Publishing
   does not scan existing subscribers. Do not enable marketing just to test ingestion.
8. Start a new checkout as that known customer; verify the hashed token and timer.
   Complete that same checkout and inspect the order token match, RECOVERED journey
   and blocked pending steps. No historical checkout campaign/backfill is run.
9. Consent to collection and view a product/add to cart in the real store; verify
   the six allowlisted browser events arrive. Confirm anonymous behavior creates
   no enrollment/send. Denied/revoked consent must produce no new pixel events.
10. Only separately authorized real delivery tests should enable/send email. Check
    existing Resend delivery/bounce/open/click and attribution records afterward.

## Offline validation

* 92 trigger/native-automation/UI/CRM/Inbox/loading tests passed, with no skips.
* 95 campaign send/tracking/production/first-paint/home regression tests passed.
* 8 Web Pixel JavaScript tests passed.
* 24 Python files compiled; both app/extension TOML files parsed.
* Reviewed migration checksum passed; disposable PostgreSQL schema issues: none.
* `git diff --check` passed.

The initial GraphQL bundle passed external 2026-04 schema validation. Final
additions (storefront domain and checkout country fields) were not revalidated:
automatic approval review rejected the final external validator command because
it contained private request text and local queries. No workaround was used.
Shopify CLI app/extension config validation also remains pending authentication.
These are offline fixture results, not live Shopify or provider evidence.

## Files for this task

Runtime: crm_automation_capabilities.py, crm_automation_rule_facts.py,
crm_shopify_automation_events.py, crm_shopify_pixel.py, crm_automation_definition.py,
crm_automation_runtime.py, crm_automation_store.py, crm_automation_ui.py,
crm_automation_attribution.py, crm_campaign_attribution.py, crm_engine.py,
crm_store.py, crm_shopify.py, crm_webhooks.py, crm_http.py, crm_schema.py,
run_migrations.py.

Admin/app: scripts/register_crm_webhooks.py, scripts/shopify_automation_diagnostics.py,
shopify_customer_account/shopify.app.toml, package.json, package-lock.json,
extensions/sports-cave-automation-pixel/shopify.extension.toml,
extensions/sports-cave-automation-pixel/src/index.js, pixel.mjs, pixel.test.mjs.

Migration: migrations/20261002143522_crm_shopify_automation_triggers_v1.sql.
Tests: tests/crm_postgres_server.mjs, tests/test_crm_shopify_automation_triggers.py,
tests/test_crm_native_automations.py, tests/test_crm_automation_ui.py, tests/test_crm.py,
tests/fixtures/crm_automation_preview.py.

No commit, push, deploy, Render modification or live Shopify/email operation was
performed. Existing uncommitted Automation V1 work was preserved.
