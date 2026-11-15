# Email tracking readiness — 30 September 2026

Local hardening of Campaigns V2. No email, order, metafield definition, webhook
subscription, live database or Render service was changed during implementation.
No custom pixel is needed. Existing Resend transport and campaign safety gates remain.

## Tracking and evidence contract

Production rendering uses the campaign database ID and its immutable
`campaign_send_id`. New sends derive that UUID once from the saved campaign UUID
(UUID5, `production-email-send-v1`); SQL stores/locks it. Duplicating a campaign
creates a different draft UUID and therefore a different send UUID. Historical
queued campaigns keep their already-stored send UUID. Historical sent links using
`campaign_key` remain readable; new campaigns require send-ID evidence.

```
utm_source=sports_cave_os
utm_medium=email
utm_campaign=<campaign_send_id>
utm_content=<stable block/product/link identifier>
sc_campaign_id=<campaign database UUID>
sc_campaign_send_id=<campaign_send_id>
```

Existing query parameters/fragments survive. Unsubscribe, account, checkout,
recovery, signed, system, external, mailto, tel and anchor links are untouched.
Review, queue confirmation and worker rendering validate decorated store anchors.
A failure blocks delivery. Preview/test links retain their test marker.

`CrmEmailOrder` queries first/last visits and **all paginated journey moments**,
including visit ID, occurrence time, landing page, source/description and all five
UTM fields. Lines and refund lines also paginate. Revenue uses existing
`netPaymentSet`; audit gross/refund use `totalReceivedSet`/`totalRefundedSet`.

Priority:

1. `SHOPIFY_UTM_EXACT` / `CONFIRMED`: exact known send UTM before purchase and
   within `EMAIL_ATTRIBUTION_WINDOW_DAYS` (default 7, existing configurable limit).
2. `RESEND_CLICK_MATCH` / `SUPPORTED`: incomplete/missing Shopify attribution,
   exact Shopify customer/recipient, real production click with matching campaign
   and send IDs, before purchase and within the window. Latest qualifying click
   wins. Contradictory explicit campaign evidence blocks this fallback.

Delivered/opened alone never qualifies. `ready=false` remains `PENDING_JOURNEY`
and cannot be reinterpreted as missing/private attribution to force a fallback.
One order has one ledger primary key. Established Shopify evidence is not downgraded
when a later API response temporarily loses it. If no actual Resend click exists,
the click time and time-to-purchase stay unavailable; a visit is not invented as a click.

## Webhooks, retries and mirror

Use the **OS application's token**, not another Shopify integration, for:

```
python scripts/register_crm_webhooks.py --orders-only
python scripts/verify_crm_tracking.py
```

Both commands above are read-only. The registration command's explicit `--apply`
creates only missing subscriptions, never duplicates or repoints existing ones.
Do not run it on Streamlit startup. Review wrong callbacks before changing anything.

Required order topics: `ORDERS_CREATE`, `ORDERS_UPDATED`, `ORDERS_PAID`.
Configured base: `SPORTS_CAVE_WEBHOOK_BASE_URL` on the existing supporting service.
Expected documented production URL:
`https://sports-cave-os-webhooks.onrender.com/webhooks/shopify/crm`.
An existing `ORDERS_PAID` subscription to `/webhooks/shopify/orders-paid` is reused:
that handler forwards the verified event to CRM after durable fulfillment handling,
without changing fulfillment results. Failure is isolated and the bounded scan recovers.
The shared receiver verifies HMAC against **raw bytes**, checks shop domain, and
stores only event/order/customer identities. Duplicate event IDs are ignored.

The existing `crm_worker.py` runs attribution even with marketing OFF. Order events
mark the existing ledger for work. Each tick handles at most two due retries plus
two orders from an updated-at scan. Initial delayed-journey retry is 1 minute,
then 5/15 minutes and hourly for persistent delays. Scan cycles run every 15 minutes
over at most the attribution window plus one day of **order updates**, including
recent refunds of old orders. There is no years-long initial order scan.
Malformed/unavailable evidence backs off; no raw customer payload is logged.

The sole attribution ledger is `crm_order_attribution`. The new migration adds
pending/retry state, JSON evidence, gross/refund amounts, mirror error and timestamps,
plus a retry index. Its existing primary key, RLS and restricted roles are retained.
Evidence stores recipient send/provider IDs, click/visit timestamps, sanitized
landing/tracking parameters, confidence, window and time to purchase. No customer
profile mirror is introduced.

`sports_cave_os.email_attribution` is reused as an ORDER/json **value**. The setup
check verifies the existing definition; nothing creates/recreates the definition.
Enable writes only with `CRM_EMAIL_ATTRIBUTION_MIRROR_ENABLED=true` after setup
review. Payload contains campaign/send/display identity, UTMs, method/confidence,
click/order timestamps and elapsed seconds. No email address or recipient ID goes
into Shopify. `compareDigest` protects concurrent edits. An identical value is a
no-op; a conflicting source/campaign/send is `FAILED` with
`attribution_conflict_admin_review`, never silently overwritten. A transient failure
keeps operational attribution and schedules retry. Statuses are PENDING/UPDATED/FAILED.

Refunds retain the attribution and refresh gross/refund/net amounts. Fully refunded
paid conversions remain recorded with zero net revenue. Existing cancellation
eligibility rules remain; cancelled attribution records are still visible in details.

## UI and health

Sent → View analytics contains EMAIL ORDERS and an on-demand Order evidence panel
with Resend, Shopify, Attribution and Purchase tabs. It uses local persisted data.
Missing click proof/fields display unavailable rather than guessed timestamps.
Open Shopify uses the configured OS store domain and order ID.

Admin-only Tracking health → Verify tracking setup runs read-only queries through
`crm_shopify.Shopify`/`shopify_sync`, the same connection as the OS. Reports actual
granted scopes, own-app subscriptions/callbacks, query access, definition, URL
decorator, mirror setting, Resend configuration and persisted event/worker evidence.
No provider request runs just because Campaigns or the popover is rendered.
Results include their verification time. A configured secret is never a green
webhook: never-received, stale (>24h event silence), error and recent states differ.
Reconciliation heartbeat must be within ten minutes. Event silence can be normal
for a quiet shop; it is not proof that a webhook is broken.

Read-only verification cannot prove a future metafield mutation will succeed;
`write_orders` and definition access are prerequisites, and actual writes retain
independent success/failure evidence. No write is performed just to test permission.

## Required configuration before acceptance

This checkout has no OS Shopify domain/API version/authentication, Resend webhook
secret or database connection configured. The local verifier reports **NOT READY**;
actual OS scopes, installed subscriptions and live metafield access are **unverified**.
No subscriptions were created. Schema validation of all nine GraphQL operations
succeeded (the existing webhook `endpoint` field is valid but deprecated).

After Nathan approves deployment, use existing services only:

1. Apply the SHA-reviewed CRM migration via the existing migration runner:
   `20260930051803_crm_email_attribution_hardening.sql`. Run `--crm --check` first.
2. Make the OS Shopify configuration available to UI/worker/webhook services:
   existing domain, API version, Admin token or client credentials, actual app HMAC
   secret; read_orders/write_orders and existing customer/product access. Historical
   access beyond Shopify's normal retention requires read_all_orders.
3. Check/register only missing own-app order topics using the command above;
   inspect the existing paid callback rather than creating a duplicate.
4. Confirm existing Resend click/open tracking and `/webhooks/resend/crm` event
   subscription/signing secret. Keep all current sending attestations and permissions.
5. Run the existing CRM worker and enable the reviewed mirror flag. Verify setup
   with actual configuration. Do not treat local mocked tests as live permission proof.

## Nathan's one-recipient acceptance procedure

Run only after setup is verified and Nathan authorizes production activation.
This procedure was **not** executed by the implementation agent.

1. Create a campaign with exactly Nathan's/test customer's Shopify subscribed
   identity. Review eligible recipients = 1 and inspect the final tracking check.
2. Send once through the real production action. Confirm Resend sent = 1,
   delivered = 1; retain campaign database ID and unique campaign send ID.
3. From the received email, click a store product link. Confirm Resend clicked = 1.
4. Inspect the landing URL for all six tracking parameters above with the exact
   IDs. Keep the same ordinary browser session for purchase.
5. Purchase normally through the **Online Store**, not a Shopify draft order.
6. Wait for signed order/create/paid processing. If journey readiness is delayed,
   check PENDING_JOURNEY and allow the worker's retry interval.
7. Open Sent analytics → EMAIL ORDERS → evidence. Verify the matching Shopify
   visit or clearly labelled supported click fallback, recipient, click and order
   timestamps, products/units/currency, revenue and click-to-purchase duration.
8. Confirm Orders = 1, correct net revenue, revenue/recipient and revenue/click.
   Replay/delayed events must not add a second conversion.
9. Open the Shopify order and confirm `sports_cave_os.email_attribution` matches
   this send and contains no customer email. Mirror status must be Updated.
10. Optionally refund/cancel the test order yourself. Confirm the original
    attribution remains and current net revenue/refund evidence follows Shopify.

The one-recipient live acceptance test is **not yet certified ready** from this
machine; configuration, deployment/migration and real service evidence remain required.

## Validation results

- Full CRM/Campaign discovery plus webhook health responsiveness: 407 tests run,
  406 passed, one existing capability skip. All SQL tests used disposable loopback
  PostgreSQL fixtures. Repeated runs first exhausted the fixture's existing test
  rate limit; a fresh in-memory database passed without changing that safety gate.
- All 22 changed Python files compiled; JavaScript syntax, CRM migration manifest
  hashes and `git diff --check` passed. Migration execution and RLS were tested
  only in the disposable database.
- Nine read-only GraphQL operations and the existing metafieldsSet/webhook-create
  definitions passed Shopify schema validation; no mutation was executed.
- Offline browser checks at 1440×900 and 1920×1080 verified EMAIL ORDERS, selecting
  a row, on-demand evidence tabs and compact layout. Historical console disconnect
  messages came from restarting the fixture server, not a new application error.
- The own-OS live verification remains NOT READY because local credentials and
  service configuration are unavailable. No live scopes, subscriptions, mirror
  writes or end-to-end conversion are claimed verified.

## Changed files

- crm_attribution_shopify.py
- crm_campaign_analytics.py
- crm_campaign_analytics_ui.py
- crm_campaign_attribution.py
- crm_campaign_content.py
- crm_campaign_page.py
- crm_campaign_send.py
- crm_campaign_send_ui.py
- crm_engine.py
- crm_schema.py
- crm_tracking.py
- crm_tracking_health.py
- crm_webhooks.py
- docs/CRM_EMAIL_TRACKING_READINESS.md
- migrations/20260930051803_crm_email_attribution_hardening.sql
- run_migrations.py
- scripts/register_crm_webhooks.py
- scripts/verify_crm_tracking.py
- tests/crm_postgres_server.mjs
- tests/fixtures/crm_production_v2_preview.py
- tests/test_crm_boundaries.py
- tests/test_crm_native_unsubscribe.py
- tests/test_crm_production_v2.py
- tests/test_crm_tracking_hardening.py
- webhook_server.py
