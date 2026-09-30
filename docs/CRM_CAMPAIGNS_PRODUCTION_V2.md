# Campaigns V2 — local implementation and activation review

This extends the existing Campaign editor, Shopify audience rules, native Shopify
unsubscribe links, Resend transport, SQL queue, signed webhook receiver and worker.
No live sends, Shopify writes, environment changes or deployments were performed.
The preceding audience-sync changes in this checkout are retained.

## Send contract

- Final review calculates current Shopify membership and eligibility using the
  existing explicit SUBSCRIBED, valid-email, suppression, deduplication, campaign
  exclusion and Smart Sending rules. It requires native unsubscribe URLs.
- Review stores a versioned immutable snapshot of the document, render settings,
  counts/reasons, timestamp, recipient IDs/hashes and per-recipient schedule.
  Customer profiles, raw email addresses and unsubscribe tokens are not mirrored.
- Confirmation requires that exact snapshot and unchanged saved draft/settings.
  Fresh customer revalidation uses the existing 50-customer batch reader. Newly
  ineligible recipients become BLOCKED with a reason; nobody is added. Local
  suppressions are checked again in the queue transaction and before submission.
- Immediate: DRAFT → SENDING → SENT. Scheduled: DRAFT → SCHEDULED → SENDING → SENT.
  The existing `python crm_worker.py` advances due work independently of Streamlit.
- A draft-row lock and unique campaign, recipient, email-hash, provider receipt and
  transport idempotency keys prevent duplicate queues/submissions. An uncertain
  provider submission remains UNCERTAIN for operator reconciliation, never an
  automatic retry. SENT means queue processing is complete, not that every address
  was delivered; delivery and failed/blocked history remain separately visible.
- Content, audience, reviewed snapshot, template version and tracking identity
  lock in SQL and the UI. SENT cannot be reopened. Duplicate creates new identities.
  Archive/restore changes only list metadata; it does not unlock delivery content.
- Final recipient count counts production submission attempts, excluding recipients
  blocked before submission. The original reviewed count remains available in the
  immutable snapshot for comparison.
- Scheduled review-count TTL no longer expires an admitted send. Healthy queue
  backlog is allowed; existing marketing-OFF and >5-minute worker-outage checks
  still block missed scheduled jobs. There is no automatic catch-up after an outage.
  Those jobs require operator review and a new draft if appropriate.

## Resend and persisted reporting

Existing endpoint: `POST /webhooks/resend/crm` on the existing webhook service.
With the currently documented topology, this is
`https://sports-cave-os-webhooks.onrender.com/webhooks/resend/crm`.
Its existing RAW-body Svix verification uses **CRM_RESEND_WEBHOOK_SECRET** (the
repository's actual setting, rather than a new secret name).

Accepted events: `email.sent`, `email.delivered`, `email.opened`, `email.clicked`,
`email.bounced`, `email.complained`, `email.suppressed`, `email.delivery_delayed`,
`email.failed`, `email.scheduled`. Event ID uniqueness deduplicates deliveries;
provider event time is retained. Early events join when the durable provider receipt
arrives. Internal-test receipts remain separate. Complaint/permanent-bounce/provider
suppression events retain the existing local stop-state behavior.

Sent rows use local SQL only and refresh every 30 seconds while that view is open
(the timer pauses while the analytics dialog is open):
campaign, market, sent time, recipients, delivered + delivery rate, unique delivered
openers + open rate, unique delivered clickers + CTR, bounces, complaints, attributed
orders, currency-separated revenue, revenue/recipient, and View analytics.
Details add suppressed, conversion rate, revenue/click, product orders/units/revenue,
click-to-purchase time, recipient delivery history and an on-demand frozen preview.
Zero denominators display —. Counts use unique recipients, not event totals.
Drafts retains the existing editor/list; Sent unmounts that editor without losing
the draft. Archived sent campaigns can be restored through View → Archived.

See [Resend event types](https://resend.com/docs/webhooks/event-types) and
[RAW-body signature verification](https://resend.com/docs/webhooks/verify-webhooks-requests).

## Links, orders and revenue

Production store links receive `utm_source=sports_cave_os`, `utm_medium=email`,
`utm_campaign=<permanent campaign_key>`, `utm_content=<stable block/link key>` and
`sc_campaign_id=<same campaign_key>`. Existing query parameters/fragments survive;
tracking keys are replaced once. Native unsubscribe, signed/system, external,
mailto/tel and anchor links are preserved. Author URLs are unchanged in storage.
Controlled tests include `sc_test=1`; production links do not. Legacy automation
tracking retains its old behavior.

New order queries use the existing Shopify transport. All order-line, refund-line
and journey-moment connections are paginated. Exact Sports Cave OS campaign UTMs
in Shopify journey visits take priority. Otherwise a same-customer Resend click
requires supporting Shopify email-source/UTM evidence; the latest qualifying click
wins. Mere receipt of an email never attributes an order. The default window is
7 days, configurable with `EMAIL_ATTRIBUTION_WINDOW_DAYS` (1–90).

The existing `crm_order_attribution` primary key permits one campaign per Shopify
order. Method, send ID, order/customer references, visit/click times and minimal
product facts are added there. There is no second orders/customer database.
Shopify `netPaymentSet.shopMoney` remains the revenue authority (payments less
refunds); cancelled/test/unpaid orders do not contribute. Source `updatedAt` guards
against an older response restoring refunded revenue. Product amounts use original
line totals minus allocated discounts and item refund subtotals. For order-edit
removals lacking an exact remaining line value, product revenue displays — rather
than an estimate. Product subtotals exclude shipping/tax and need not equal order
net payments. Values remain in Shopify's recorded shop currency; no FX conversion
or inference from campaign market occurs.

The existing signed order webhooks expedite reconciliation. A persisted background
scan processes at most two full orders per worker tick, in 10-ID pages, on a
15-minute cycle. A rolling window retries delayed journey/click evidence; the
watermark includes older updated orders/refunds after downtime. No Shopify/Resend
requests occur per Sent row or ordinary table interaction. Backend failure leaves
stored metrics available with a subtle delayed status. Missing journey evidence
does not produce guessed revenue.

## Optional Shopify marker

Native Shopify journey UTMs are the primary evidence; the app does not rename
Shopify-owned channels. The optional metadata mirror is OFF by default.

Before enabling it, create/review a merchant-owned **Order** metafield definition
in Shopify Custom data: name “Sports Cave OS Email attribution”, namespace/key
`sports_cave_os.email_attribution`, type **JSON**, no storefront access. This is
the explicitly requested merchant namespace, using the existing custom integration.
Then enable `CRM_EMAIL_ATTRIBUTION_MIRROR_ENABLED=true` only after reviewing scopes.
The worker writes source, campaign ID/name, send ID and attribution method through
the existing `shopify_sync.metafields_set` helper. It retrieves the same namespace
with `fetch_metafields`, skips identical values and uses compareDigest. It does not
overwrite a marker owned by another source or touch other metafields/notes.
Missing permissions or write failure mark the mirror UNAVAILABLE; local attribution
and order processing continue. No definition or value was created live in this task.

## Schema and files

Migration `migrations/20260930031755_crm_campaigns_production_v2.sql` adds one table:
`crm_campaign_snapshots`, with RLS, revoked public/client access and immutability.
It extends `crm_campaigns` with snapshot/key/send ID, lock/start/sent timestamps and
final count; `crm_delivery_events` with sanitized clicked URL; and
`crm_order_attribution` with send/order/customer references, click time, method,
source timestamp, product facts and mirror status. It adds FKs, unique/reporting
indexes and SQL content/template locks. Registered in the reviewed migration
manifest and schema readiness checks. Applied only to disposable local PostgreSQL.

Implementation files added: `crm_campaign_snapshot.py`, `crm_campaign_analytics.py`,
`crm_campaign_analytics_ui.py`, `crm_campaign_attribution.py`,
`crm_attribution_shopify.py`.

Existing implementation files adjusted: `crm_campaign_send.py`,
`crm_campaign_send_ui.py`, `crm_campaign_store.py`, `crm_campaign_page.py`,
`crm_campaign_leave_ui.py` (DOM observer startup guard only),
`crm_campaign_schedule.py`, `crm_campaign_content.py`, `crm_engine.py`,
`crm_tracking.py`, `crm_templates.py` (legacy adapter only), `crm_webhooks.py`,
`crm_workspace_store.py`, `crm_attribution.py` (protect V2 rows from legacy manual
refresh), `crm_schema.py`, `run_migrations.py`.

Tests added: `tests/test_crm_production_v2.py` and
`tests/fixtures/crm_production_v2_preview.py`. Existing contract assertions updated
in `test_crm_send_flow`, `test_crm_campaign_v2`, `test_crm_campaign_sections`,
`test_crm_composer_presentation`, `test_crm_email_defaults`,
`test_crm_html_workspace`, `test_crm_postgres`, `test_crm_production_style_test`,
`test_crm_single_footer`, `test_crm_storage_recovery`; the disposable SQL fixture
includes the new migration. Other existing checkout changes belong to the preceding
audience-sync work and have been preserved.

## Activation and validation

Not activated: marketing gates, live Resend events, Shopify mirror, production
migration, worker service, or deployment. Before any real send:

1. Review/apply the CRM migration using the existing migration runner; deploy the
   reviewed code to the existing services. Do not create a second primary web app.
2. Verify the existing Resend sender/domain, reply-to, API key, DMARC, webhook secret
   and event subscriptions above. Enable Resend open/click tracking for actual
   engagement callbacks; webhook subscription alone cannot enable that tracking.
3. Verify Shopify `read_orders`, existing customer/product access and customer
   journey availability. Older order access can require Shopify `read_all_orders`.
   The optional marker requires order metafield write capability (`write_orders`).
   The five new GraphQL queries were schema-validated; the OS production token and
   deployed registrations were not available for live capability verification.
4. Review/run the existing `python crm_worker.py` as the previously documented
   supporting CRM background worker, one instance. No worker or Render topology
   changes were made here. Keep the worker healthy for scheduled delivery.
5. Keep marketing OFF until Nathan explicitly authorizes activation. Existing
   `CRM_MARKETING_ENABLED`, `CRM_MARKETING_SEND_ENABLED`, DMARC/webhook/broadcast
   attestations and per-market review gates remain required. Nothing enables them.

Local fixture testing is safe: run `node tests/crm_postgres_server.mjs`, then
`python -m streamlit run tests/fixtures/crm_production_v2_preview.py --server.address
127.0.0.1 --server.port 8521 --server.headless true`. Its DB is memory-only/loopback
and external HTTP/production DB connections are blocked. No real internal test or
campaign should be sent merely to inspect the UI.

Validation completed locally on 30 September 2026:

- Full `test_crm*.py` suite: 371 tests, 370 passed, one existing capability skip
  (named Streamlit fragment targeting is unavailable; its fallback remains tested).
  This includes 26 new production V2 tests and existing controlled test-send mocks.
- Compiled all 45 changed/new Python files; checked the SQL fixture JavaScript and
  both inline Campaigns focus/navigation scripts. Migration manifest/schema checks
  and `git diff --check` passed. Existing Streamlit deprecation warnings remain.
- Validated all five new Shopify GraphQL queries against the current schema.
- Browser: 1440×900 and 1920×1080, plus a narrower 1100×800 check. Verified final
  review, marketing-OFF gate, Drafts/Sent switching with draft retained, compact
  persisted metrics, analytics/product details and on-demand frozen email preview.
  Table overflow is horizontal; row-based height avoids a nested vertical table
  scroller. The final clean browser run had no console errors or page overflow.
- Fixed the existing Campaigns focus/leave observers to observe the document root
  safely when the body is not yet mounted. No navigation or sending logic changed.
- Browser fixtures use synthetic records in disposable loopback PostgreSQL and
  block production DB/outbound HTTP for the whole fixture process, including
  fragment reruns. Test servers were stopped afterward.

Screenshots: [final review at 1440](validation/crm-v2-review-1440.png),
[Sent at 1440](validation/crm-v2-sent-1440.png),
[Sent at 1920](validation/crm-v2-sent-1920.png).

No campaign/test email was sent. No live customer, order, segment, metafield,
Resend setting, production database, marketing flag or Render service was modified.
Nothing was committed, pushed or deployed. Live delivery/event and Shopify-scope
verification remains an activation step, not a claimed result of these fixtures.
