# Abandoned checkout receiver audit — 5 October 2026

Local repair only. No commit, push, deployment, environment change, live webhook
registration, emails, orders or edition allocations were performed.

## Root cause and production evidence

`crm_automation_diagnostic_ui.control()` calls
`crm_automation_capabilities.verify()` in the primary `sports-cave-os` Streamlit
process on an explicit admin click. The same verification runs every five minutes
in the leased `crm_worker.py`, supervised by `sports_cave_worker.py` on the existing
`sports-cave-seo-worker`. Both write `shopify_automation_capabilities` in
`crm_runtime_state`. Before this repair, whichever process ran last diagnosed its
own local environment as though it belonged to the webhook receiver.

The latest production stored report was read without mutation, checked at
2026-10-05T00:54:49Z. App identity, API and customer/order read scopes were verified;
both checkout subscriptions were absent. The order subscriptions already had the
correct receiver URLs and delivery version 2026-04. The callback mismatch labels
were false: absent local base configuration produced relative expected URLs.

The literal `Admin API token is not a webhook secret` text came from
`crm_automation_capabilities.verify()`, using the receiver's prefix tuple.
That tuple incorrectly included `shpss_`, a shared/app-secret prefix. Furthermore,
the receiver calculated HMAC against access-token-shaped candidates instead of
excluding them; the diagnostic and receiver could disagree. Both are corrected.

Actual receiver logs at 2026-10-04T23:36:34Z and subsequent retries show
`webhook_hmac_verified`, `orders/paid`, `secret_env_used=SHOPIFY_SHARED_SECRET`.
This is proof that the differently valued shared secret is actively needed for
the existing signed-order deliveries. **Do not replace it.** Repository usage is
webhook HMAC fallback and Collector Vault HS256 Shopify session-token fallback;
it is not the Admin API token/client-credentials exchange variable. The exact
provider-side origin of that historical secret is not inferable from a variable
name or logs alone.

Production CRM receipts include 21 orders/create and 20 orders/paid events, and
29 recovered token-ledger checkout records; no checkout create/update receipts.
The app TOML declares webhook API version but no topic subscriptions, and setup
is an explicit admin CLI action, not automatic installation/startup registration.
The observed missing checkout subscriptions are real registration omissions,
not removed Shopify topics. No assertion is made about who omitted them or when.

No local OS-app Shopify credentials are available. Fresh direct subscription
inspection could not be run from this checkout. Evidence above comes from the
production OS app's persisted, paginated GraphQL diagnostic and actual receiver
logs, not an unrelated connector app's installation/scopes.

## Configuration ownership and precedence

| Variable | Purpose | Service/process that needs it |
| --- | --- | --- |
| SHOPIFY_STORE_DOMAIN | Admin transport/store identity, signed webhook store validation, token hashing | Primary OS, existing CRM worker, webhook receiver |
| SHOPIFY_API_VERSION | Admin requests and expected webhook delivery contract: 2026-04 | Primary OS, CRM worker, webhook receiver/setup shell |
| SHOPIFY_CLIENT_ID | Installed-app credentials exchange; existing app identity/session audience | OS and worker making Admin queries; receiver if its existing sync uses that auth |
| SHOPIFY_CLIENT_SECRET | Client-credentials token exchange; app HMAC/session-secret fallback | Services using that existing auth; receiver supports fallback |
| SHOPIFY_ADMIN_ACCESS_TOKEN | Legacy Admin transport alternative; never webhook HMAC | Only services using legacy Admin authentication |
| SHOPIFY_WEBHOOK_SECRET | Explicit webhook signing candidate | Webhook receiver |
| SHOPIFY_API_SECRET_KEY / SHOPIFY_API_SECRET | Legacy app signing aliases | Receiver and existing Collector Vault session validation where configured |
| SHOPIFY_SHARED_SECRET | Historical webhook signing candidate and Collector Vault session validation fallback | Preserve existing receiver value and any existing Vault configuration |
| SPORTS_CAVE_WEBHOOK_BASE_URL | Non-secret HTTPS receiver origin | Receiver; optional explicit override in OS/worker/setup |
| CRM_PUBLIC_BASE_URL | Existing fallback public CRM receiver origin | Existing CRM services where configured |

Admin transport prefers CLIENT_ID + CLIENT_SECRET when both exist, otherwise the
ADMIN_ACCESS_TOKEN. These are unrelated to webhook verification selection.
Receiver HMAC candidates remain WEBHOOK_SECRET → API_SECRET_KEY → API_SECRET →
SHARED_SECRET → CLIENT_SECRET. Each eligible candidate is tried for signature
rotation/backward compatibility; shpat_/shpca_/shppa_ are excluded, shpss_ retained.
Raw request bytes, base64 SHA-256 and constant-time comparison remain authoritative.

Base precedence is SPORTS_CAVE_WEBHOOK_BASE_URL → CRM_PUBLIC_BASE_URL → the
canonical `https://sports-cave-os-webhooks.onrender.com` only in a Render process.
Configured invalid origins are rejected rather than hidden by fallback. Paths,
credentials, query strings, fragments, insecure/private literal hosts are rejected.
RENDER_EXTERNAL_URL is deliberately not used: in the OS it identifies the UI.

Render diagnostics now read the receiver's non-secret
`GET /webhooks/shopify/readiness`. It returns configuration flags, canonical
callbacks, route availability and version only. No DB/Shopify calls, secret names
or values, customer details or mutations. Requests are bounded, redirects rejected,
and responses strictly validated. Missing/malformed/unreachable readiness fails
closed rather than falling back to UI/worker signing credentials. HMAC is
CONFIGURED until the running receiver accepts a valid signature, then VERIFIED;
after restart it honestly returns CONFIGURED again. Configuration alone is not
proof of a real signed delivery.

No new Render variables or duplicated signing secrets are required for the
canonical production topology. Existing correctly configured values stay intact.

## Canonical routes and registration

| Shopify topic | Canonical route |
| --- | --- |
| CHECKOUTS_CREATE | /webhooks/shopify/crm |
| CHECKOUTS_UPDATE | /webhooks/shopify/crm |
| ORDERS_CREATE | /webhooks/shopify/crm |
| ORDERS_PAID | /webhooks/shopify/orders-paid |

All routes use the canonical receiver base above. Existing ORDERS_PAID on /crm
remains accepted as a compatibility route; do not duplicate an existing correct
subscription. CRM dispatches by the signed topic header, so separate new checkout
routes are unnecessary. The paid route keeps its existing allocation/Vault flow.

Subscription reads use the OS Shopify transport and the existing GraphQL
webhookSubscriptions query, pages of 100 with advancing cursor validation. Checks
separate missing, unavailable, unverified base, actual callback mismatch and
version mismatch. Duplicate flags are recorded without deleting subscriptions.

`scripts/register_crm_webhooks.py --abandoned-only` inspects only the four topics.
With explicit approved --apply it validates canonical app identity/read scopes,
requires API 2026-04, creates only absent topics, and re-reads actual callback and
delivery version. Existing wrong/old/duplicate subscriptions require review and
are never duplicated or deleted. It does not create unrelated welcome/fulfilled
subscriptions in abandoned-only mode. Both existing correct order routes stay put.

## State machine / send boundary

Token matching was already implemented correctly: checkout webhook `token` and
order webhook `checkout_token` are hashed with store identity to one checkout_key.
Webhook numeric checkout id/checkout_id are not used. Historical Admin GraphQL
AbandonedCheckout GIDs/admin_checkout_id remain valid for exact fresh checkout
hydration and are not deleted or confused with removed webhook fields.

Create/update persist event and token state in one transaction. Event identity is
unique; updates advance activity_at with GREATEST, preserving abandonment timing.
Recovery is monotonic, so late checkout updates cannot reopen converted records.
Worker enrollment requires signed future-only token state and resolves the exact
Admin checkout from its recovery URL. Fresh live hydration now rechecks that URL's
token against enrollment checkout_key, in addition to the existing customer check.
Legacy enrollments without keys retain their stricter customer/order checks.

The existing /crm order route already commits conversion before acknowledgement.
The paid route previously forwarded CRM in a swallowed-error background task.
For token-bearing paid orders it now commits the same idempotent conversion ledger
before allocation and HTTP acknowledgement. Persistence failure returns 503 for
Shopify retry. Duplicate paid receipts still replay the conversion guard safely.
No redundant background CRM forwarding occurs for those already-persisted events.
Orders without tokens retain the existing legacy fan-out. No allocation algorithm,
numbering, certificate, fulfilment or order-sync logic changed.

RECOVERED state blocks validation and the transactional begin_send boundary
immediately; the existing worker marks active enrollments recovered and blocks
pending/claimed reminders. SUBMITTING/ACCEPTED receipts remain immutable.
No schema migration or changes to existing historical metadata are needed.

## Local verification and known unrelated test failure

Focused signed HTTP/config/registration/real disposable-Postgres tests cover
allowed and invalid HMAC, access-token exclusion, shpss_ acceptance, exact raw-body
validation, receiver/local boundary, fail-closed receiver outages, base precedence,
subscription classifications, repeat setup, checkout retry/update, order token
conversion, recovery monotonicity and mismatched hydration. Existing automation
tests cover recovered suppression before/after claiming and legacy send isolation.
All external transports in these tests are mocked or loopback; no emails sent.

The unchanged Collector Vault test
test_render_declares_frame_product_variables_without_values expects two primary
copies of Render variables. HEAD render.yaml already has one, and repository
AGENTS.md explicitly prohibits a duplicate primary. This stale test fails on the
unchanged topology. It was not 'fixed' by changing production Render configuration.

Final results: focused receiver/diagnostic/trigger/native-automation/checkout/
boundary suites: 100/100 passed (disposable loopback PostgreSQL enabled). Shopify
sync, health responsiveness, product webhooks and tracking/attribution regressions:
226 run, 184 passed, 42 skipped. Collector Vault: 42 passed, the one pre-existing
topology assertion above failed. The new 14-test receiver suite was rerun after
the final HMAC edge-case changes: all passed. Compilation of all changed Python,
git diff --check, and validate_render_topology.py passed. Existing GraphQL query
and registration mutation validated against 2026-04, with an informational warning
that endpoint is deprecated but still supported. No unrelated GraphQL rewrite.

Files changed: crm_shopify_webhook_config.py (new),
crm_automation_capabilities.py, crm_tracking_health.py, crm_engine.py,
webhook_server.py, shopify_sync.py, scripts/register_crm_webhooks.py,
tests/test_crm_shopify_receiver_reliability.py (new),
tests/test_crm_shopify_automation_triggers.py,
docs/AUTOMATION_TRIGGER_DIAGNOSTIC.md and this audit. render.yaml, schemas,
templates, UI layout, allocation, fulfilment, Meta/SEO and live settings unchanged.

## Controlled live procedure — only after approval

1. Deploy receiver first, then primary OS and the existing CRM worker. No Blueprint
   sync/new service. Check /healthz and /webhooks/shopify/readiness: correct origin,
   both routes ready, 2026-04, no secrets. CONFIGURED is valid until real HMAC proof.
2. Run the existing OS-app diagnostic script with --inspect-only in a connected
   server shell. Confirm both order URLs verified and only checkout topics missing.
3. Separately approve registration. Run register_crm_webhooks.py --abandoned-only
   first without --apply; review exact missing topics. Then run with --apply.
   Repeat inspection: exactly one correct subscription per required topic, version
   2026-04. Do not delete any unrelated or historical callbacks.
4. Rerun the admin diagnostic; wait for the leased worker refresh (>5 minutes) and
   confirm readiness is stable across both writers. This does not publish a flow.
5. Keep abandoned flows unpublished/paused during controlled verification. If that
   cannot be guaranteed without affecting current business, use an isolated staging
   receiver/database for signed synthetic lifecycle tests instead of production.
   Post one controlled token-only create, update, identical retry and order/create
   with checkout_token to /crm (never synthetic orders to the allocation route).
   Confirm one checkout row, advancing activity, recovery, blocked reminders and
   idempotent event receipts. Invalid HMAC must return 401 with no writes.
6. Verify paid route using Shopify's test header/notification path, which returns
   before allocation, then observe the next genuine paid delivery for durable CRM
   conversion. No artificial purchases, allocations, email sends or campaigns.
7. Review evidence before separately approving automation publication. The local
   fix alone does not make missing live subscriptions present or publish a flow.
