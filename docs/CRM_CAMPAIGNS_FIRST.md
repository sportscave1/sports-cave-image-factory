# CRM campaigns-first workspace — local implementation runbook

Implementation date: 28 September 2026. Nothing was committed, pushed, deployed,
sent to Resend, installed in Shopify or applied to production Supabase. Marketing
and website tracking were not enabled. The live environment was not queried or
changed. Keep `CRM_MARKETING_ENABLED=false`.

## What works locally

The CRM sidebar is **Campaigns → Flows → Settings**, defaulting to Campaigns.
Legacy Customers, Segments, Templates and Reports routes open their corresponding
Settings section and retain their existing permissions. Settings also contains
Branding, Connections & Tracking, Prompts, and Sending & Compliance.

Campaigns have persisted drafts, search/status/market filters, paginated tables,
duplicate/archive/restore actions, optimistic revisions and history. The editor
uses Recipients → Message → Review, a sticky toolbar, explicit Saving/Saved/Failed
feedback and a guard when leaving a campaign with unsaved changes. Nothing seeds
or sends on page load. “Create first test campaign” is an explicit database write.

Campaign and template content is a versioned block document. Text, heading,
image, button, product, two-column product grid, divider and spacer blocks support
editing/reordering/copying/removal. The header/footer are generated outside the
editable body. Templates have immutable content revisions; using one copies a
snapshot and subsequent template edits do not alter existing campaigns. Built-in
Collector Launch, New Editions and Collector Note starters are not automatic
database seeds. New Editions requires 2–4 explicitly selected products.

Shopify remains the source of customer, consent, order and product facts. Read-only
product search, image/variant pagination and contextual prices are explicit actions.
Unknown facts are omitted. Market currencies must match AUD/USD/GBP; Global has
no inferred price. Shopify image transforms request proportional JPEG derivatives
up to 1000px, with no crop, upload or server-side image fetch. Unsupported external
assets must be converted using the existing approved asset workflow. Image byte
size is not fetched automatically; the editor gives the ≤1 MB guidance separately
from measured HTML size.

The same `render_campaign` renderer is used for previews, saved campaign tests and
the legacy flow-template adapter. It creates table-based email HTML, inline essential
styles, a 600px fluid container, 16px body text, mobile stacking, proportional
images, escaped copy, preheader and plain text. Preview modes are 320/375/430/600px,
images off and plain text. These are layout previews, not Gmail/Outlook certification.
HTML budgets: target <80 KB, warning ≥85 KB, test blocker >95 KB. No crop tool is
introduced and no artwork is destructively cropped.

Prompt generation is copy/paste only. Versioned Settings guidance is subordinate
to locked truthful-copy rules and supplied canonical facts. JSON v1 imports are
validated, displayed as before/after proposals and selectively applied. Footer,
sender, consent, recipients, links and delivery controls cannot be imported. No
AI API is connected and no missing product facts are invented.

## Safety and eligibility

Multi-segment inclusions are a union by Shopify customer identity. Exclusions win.
One normalized email can appear only once. Only exact Shopify `SUBSCRIBED` is
eligible: purchases, NOT_SUBSCRIBED, PENDING, INVALID, UNSUBSCRIBED and REDACTED
do not qualify. A separate current Shopify consent pass detects conflicting
duplicate profiles outside the selected segment and conservatively excludes them.
Local suppressions and the configured Smart Sending window are checked. Failed,
partial or non-advancing pagination never becomes a complete eligible estimate.
Only aggregate counts and segment/rule references persist, not customer profiles.

Smart Sending defaults to 16 hours, configurable from 1–168 hours. Its estimates
use actual accepted OS marketing receipts. Internal tests, legacy test sends and
the separate support/transactional inbox are excluded. The legacy dispatch
boundary rechecks recent accepted/submitting/uncertain marketing attempts before
submission. This does not discover Klaviyo or Shopify-native sending history.
Fresh consent, exclusions, suppression and frequency checks remain mandatory
before a separately approved future production dispatch.

AU/US policy uses the strict common subscription baseline. The footer identifies
the business, configured postal address, website, contact, subscription reason,
optional confirmed privacy/social links and unsubscribe state. No home address is
invented. Missing identity/postal data permits clearly labelled internal previews
but blocks production readiness. No jurisdiction is automatically marked legally
reviewed; UK/EU remains a placeholder. No claim of guaranteed inbox delivery or
complete legal compliance is made.

Campaign internal tests require an active administrator, a saved editable revision,
exactly one manually typed valid mailbox on the persisted internal allowlist,
explicit confirmation and button submission. They call the Stage 1 dedicated
`RESEND_MARKETING_API_KEY` transport with rendered HTML/plain text and campaign-test
metadata. No segment/list parameter exists. REQUESTED/ACCEPTED/FAILED/UNCERTAIN
attempts persist before/after I/O. An operation ID cannot be reused for another
request; repeating an accepted operation returns its receipt. Ambiguous responses
are held without automatic retry. A concurrent edit does not inherit TESTED.
Provider acceptance is explicitly distinguished from verified delivery.

The existing Stage 1 fixed diagnostic test remains in Sending & Compliance and
retains its separate manual-admin contract. Its fixed content does not become a
bulk or campaign bypass. Campaign tests have the additional allowlist/revision
boundary. Both use the dedicated marketing key; support IMAP/SMTP is untouched.

No production campaign action is functional. Schedule/resume and Flow activation
are blocked in the action layer, and the future Broadcast abstraction raises.
Authoring records are separate from the legacy worker queue. Do not start or
enable a CRM worker as part of this rollout. Existing external Klaviyo/Shopify flows
may already be LIVE; inspect them before any later activation. Nothing external
was paused or deleted.

## Persistence and migration

New migration: `migrations/20260928024722_crm_campaigns_first_workspace.sql`.
It depends on the two existing CRM migrations, in order:

1. `migrations/20260927093818_crm_marketing_v1.sql`
2. `migrations/20260928020740_crm_campaign_workspace_v1.sql`
3. `migrations/20260928024722_crm_campaigns_first_workspace.sql`

The new migration adds workspace settings/history, internal tests, verified
delivery events, minimal website events and minimal order-attribution records.
It adds template archive metadata and suppression reconciliation state, and maps
legacy authoring status spellings to DRAFT/NEEDS_REVIEW/TEST_READY/TESTED/ARCHIVED.
Existing draft/template/history records are retained. Tables have server-only RLS
and revoke public/anon/authenticated access. No browser service-role key, mirrored
customer database, page-load DDL or production migration registration is added.

The local SQL fixture applies all three migrations in memory on real PGlite
PostgreSQL, with no Supabase connection:

```powershell
npm --prefix tests/fixtures/crm ci
node tests/crm_postgres_server.mjs
# Keep this loopback-only server running in a separate terminal, then:
$env:CRM_TEST_POSTGRES='1'
.venv/Scripts/python.exe -m unittest tests.test_crm_workspace tests.test_crm_campaigns_v1 tests.test_crm_resend_marketing tests.test_crm tests.test_crm_boundaries tests.test_crm_postgres tests.test_crm_ui
```

For an independently created disposable local Supabase database, apply only the
missing migrations once. Example local-only commands (not executed in production):

```powershell
psql -h 127.0.0.1 -p 54322 -U postgres -d postgres -v ON_ERROR_STOP=1 -f migrations/20260927093818_crm_marketing_v1.sql
psql -h 127.0.0.1 -p 54322 -U postgres -d postgres -v ON_ERROR_STOP=1 -f migrations/20260928020740_crm_campaign_workspace_v1.sql
psql -h 127.0.0.1 -p 54322 -U postgres -d postgres -v ON_ERROR_STOP=1 -f migrations/20260928024722_crm_campaigns_first_workspace.sql
```

Do not point those commands at production. The existing `run_migrations.py` allowlist
has intentionally not been expanded. A reviewed production migration plan, backup
and deployment approval are separate prerequisites. Missing storage produces an
installation diagnostic rather than a session-only “saved” message.

## Configuration after approved deployment

Retain the existing server-side database and Shopify read-adapter configuration.
No Shopify credentials or scopes were changed. Live access to customer/segment,
product/image/contextual-pricing and order-journey fields must be verified using
the installed app's approved read scopes; schema validation alone is not permission
proof. Attribution over older orders may need separately approved historical-order
access. No write-customer scope/client is introduced.

Connections & Tracking has an explicit **Check Shopify connection and read scopes**
button using `shop.id` and `currentAppInstallation.accessScopes`. It displays only
connection evidence, check time and scope names, with a missing-read-permission
warning. Merely opening Settings does not make that API call.

Existing marketing variables read by the dedicated test service:
`RESEND_MARKETING_API_KEY`, `RESEND_FROM_EMAIL`, `RESEND_FROM_NAME`,
`RESEND_REPLY_TO`, `CRM_MARKETING_ENABLED`. Keep the last **false**. The older
`RESEND_API_KEY` is not used for CRM. Never paste credentials into settings.

Non-secret persisted settings: branding logo/accent/social links, Arial/Georgia
typography and solid/outlined black button presets, legal display
name/business postal address/website/contact/privacy URL and explicit identity
confirmations, internal-test mailbox allowlist, default Smart Sending hours, and
per-purpose prompt guidance. The code also retains existing environment defaults
`CRM_BUSINESS_DISPLAY_NAME`, `BUSINESS_POSTAL_ADDRESS`, `CRM_BUSINESS_WEBSITE`,
`CRM_BUSINESS_ADDRESS_VERIFIED` and `CRM_SENDING_DOMAIN_VERIFIED`. Saved compliance
settings override corresponding environment defaults. Do not mark verification
complete without evidence. DMARC and actual provider delivery remain unproven.

Future webhook/unsubscribe variables: `CRM_PUBLIC_BASE_URL`, dedicated secret
`CRM_RESEND_WEBHOOK_SECRET`, and `CRM_UNSUBSCRIBE_SECRET` (at least 32 characters).
Legacy public-base fallbacks are retained. Do not rotate an issued unsubscribe
signing secret without preserving existing links. Existing extra worker send/test
flags remain subordinate to the master switch; do not enable them.

Future onsite variables: `CRM_WEBSITE_TRACKING_ENABLED` (default false),
`CRM_WEBSITE_PIXEL_ID` (public random 16–80 character identifier),
`CRM_WEBSITE_ALLOWED_ORIGINS` (explicit comma-separated origins), and the HTTPS
`CRM_PUBLIC_BASE_URL`. Generated pixel source also starts `enabled:false` and
`test_context:true`. No tracking was installed or activated.

## First campaign / one internal test

1. After approved deployment/migrations, open CRM & Marketing → Settings → Sending
   & Compliance. Nathan enters the confirmed business details and approved internal
   mailbox allowlist. Saving this sends nothing. Verify Marketing Delivery is disabled.
2. Open Campaigns → + New Campaign, or explicitly create the first test draft.
   Set name, purpose, market and tags. The draft is stored immediately.
3. Recipients: choose rule filters or load saved segments, apply include/exclude
   selection, and recalculate. Continue all pages including global consent verification.
   Incomplete estimates are unavailable, not zero. Internal testing does not require
   dispatching or resolving a production audience.
4. Message: choose a starter/template, select real Shopify products/images, optionally
   load a variant's verified market price, and edit subject/preheader/blocks/CTA.
   Review the offer and facts. Optionally generate/copy a prompt, paste JSON, inspect
   proposals and apply selected copy. Save the draft and reopen to confirm persistence.
5. Inspect 320/375/430/600px, images-off and plain-text previews. The header/footer
   remain locked. Resolve internal-test blockers; production blockers stay visible.
6. Review: Nathan manually types ONE allowlisted internal mailbox, confirms TEST ONLY,
   then clicks Send internal test. This is a real email only after the separate approved
   rollout. This development session performed mocked sends only. Record the returned
   message ID/time. Accepted is not delivered; inspect verified events and the mailbox.
7. If status is uncertain or receipt storage failed, investigate the provider message
   and operation ID first. Never assume failure and click another attempt blindly.
   “Start a separate test attempt” deliberately creates a new operation, not a retry.

## Webhooks, suppression and unsubscribe — activation still required

The existing webhook service route `/webhooks/resend/crm` now verifies unchanged
request bytes with pinned `svix==1.99.1`, timestamp tolerance and its dedicated
signing secret. Durable provider event IDs deduplicate callbacks before ACK.
Early/out-of-order events reconcile against locally stored provider message IDs,
never caller-supplied campaign/recipient tags. Only known production permanent
bounces/complaints suppress a customer. Test and unrelated messages cannot do so.
Unknown event types, including unmapped contact updates, do not mutate consent.

After separate approval, register that route on the existing webhook service with
email.sent/delivered/delivery_delayed/failed/bounced/complained/opened/clicked. Verify
signature rejection, duplicate replay, early callbacks and an internal-test message
end to end. A configured secret is not proof that events are arriving. No provider
webhook was registered during development.

Manual support unsubscribe requests can be recorded through Settings without
altering the support inbox. Suppression is immediate and is never cleared by
campaign code. The future `crm_consent_sync.reconcile_opt_out` adapter is mockable
but has no production writer/caller/scheduler. Failure or missing acknowledgement
leaves suppression active and reconciliation pending. Approval and a narrowly
scoped unsubscribe-only Shopify write workflow are required before wiring it.

The existing OS unsubscribe route uses signed recipient-purpose tokens with no
email in the URL. GET is non-mutating; verified POST suppresses without login;
repeats are safe; test receipts are rejected. Legacy issued signatures remain valid.
Internal campaign content visibly labels the production unsubscribe path inactive
and does not fabricate a working link. A functional body link plus RFC 8058 headers,
provider/OS suppression and Shopify reconciliation must be proven before live use.

## Website tracking and attribution — default off

After approval only: configure the explicit allowed origin/public identifier/base
URL, create a Shopify Customer Events custom pixel requiring BOTH Analytics and
Marketing permission, and paste the generated source. Enable the source only for
an approved test while retaining `test_context:true`; enable the server route only
for that controlled verification. Test actual sandbox CORS origin (including `null`
only if observed and explicitly reviewed), denied/granted/withdrawn consent and
all five events. No wildcard origins or credentials. Disable both switches afterward
until production tracking has its own approval. A public pixel ID is not a secret
or authentication mechanism; events remain untrusted.

Only page_viewed, product_viewed, product_added_to_cart, checkout_started and
checkout_completed are accepted, in bounded JSON with timestamp, random session
reference, safe campaign/product IDs and consent flags. Browser snapshots, names,
emails, address, checkout/payment data and full URLs are not sent or stored. Consent
withdrawal clears context and stops subsequent work including pending async callbacks.
Per-peer/global memory limits and a durable global rate cap bound ingestion. Browser
events cannot enqueue messages, claim a purchase, change consent or create revenue.

UTMs use `sports_cave` / `email`, opaque stable campaign/block references and explicit
internal-test context. Existing variant/query/fragment values survive. Recovery,
signed, unsubscribe, privacy and mailto links are excluded from rewriting.

Reports separate internal tests from production receipts/events. Orders are fetched
only on explicit action and all requested pages must complete before totals appear.
Attribution is **Shopify last recorded visit within 30 days**, requiring matching
source/medium/campaign, available journey/landing data, and a canonical paid,
non-test, non-canceled order. It excludes internal-test links and browser purchase
claims. `netPaymentSet.shopMoney` records payments received minus refunds, grouped
by currency without conversion. Re-reading updates refunds/cancellations and
invalidates lost associations. This is an association, not incremental revenue or
cross-device/multi-touch attribution. Missing permissions/data are unavailable,
not zero; reports show the range/completeness/check time. Refresh after later refunds.

## Future Resend transport decision

Official documentation checked on 28 September 2026:

- [Marketing pricing](https://resend.com/pricing): Broadcast marketing plans are
  contact-based and separate from transactional plans; do not assume the US$20
  transactional plan includes the required Broadcast entitlement.
- [Create Broadcast](https://resend.com/docs/api-reference/broadcasts/create-broadcast):
  use current `segment_id` resources and the documented unsubscribe placeholder,
  not deprecated Audience APIs. The intended future flow is current Shopify
  eligibility → non-authoritative delivery mirror/segment → Broadcast → provider
  events → durable OS history/suppression.
- [API key permissions](https://resend.com/docs/api-reference/api-keys/create-api-key):
  `sending_access` is insufficient for contact/segment/Broadcast management. The
  current documented alternative is `full_access`; there is no verified granular
  Broadcast-management key claimed here. Use a separate restricted operational
  credential/service boundary only after explicit approval; do not widen or reuse
  the present send-only key or an older full-access key. Evaluate scoped OAuth if
  the selected Resend integration actually supports the necessary resource scopes.
- [Send](https://resend.com/docs/api-reference/emails/send-email) and
  [batch send](https://resend.com/docs/api-reference/emails/send-batch-emails) are
  application-managed alternatives. They would require a durable queue, idempotency,
  current account rate-limit handling, consent revalidation, frequency/suppression,
  permanent event history, RFC 8058 and functioning unsubscribe. No synchronous
  bulk loop, Broadcast creation, contact import or provider management is implemented.
- [Shopify image transforms](https://shopify.dev/docs/api/admin-graphql/latest/input-objects/ImageTransformInput),
  [granted installation scopes](https://shopify.dev/docs/api/admin-graphql/latest/queries/currentAppInstallation),
  [Order revenue fields](https://shopify.dev/docs/api/admin-graphql/latest/objects/Order),
  [pixel privacy API](https://shopify.dev/docs/api/web-pixels-api/standard-api/customerprivacy)
  and [Resend webhook verification](https://resend.com/docs/webhooks/verify-webhooks-requests)
  inform the read/conversion/privacy/verification boundaries above.

## Files changed in this task

- Navigation/UI: `app.py`, `os_accounts.py`, `crm_navigation.py`, `crm_page.py`,
  `crm_campaign_page.py`, new `crm_settings_page.py`.
- Content/authoring: `crm_campaign_content.py`, `crm_campaign_store.py`,
  `crm_templates.py`, new `crm_email_blocks.py`, `crm_prompt_factory.py`,
  `crm_workspace_store.py`, `crm_tracking.py`.
- Authority/safety/events: `crm_audience.py`, `crm_shopify.py`, `crm_engine.py`,
  `crm_service.py`, `crm_store.py`, `crm_resend.py`, `crm_webhooks.py`, `crm_http.py`,
  new `crm_attribution.py`, `crm_consent_sync.py`, `crm_onsite.py`,
  `crm_customer_pixel.js`; `requirements.txt` pins Svix.
- Schema: the single new `20260928024722_crm_campaigns_first_workspace.sql` migration
  listed above; earlier CRM migrations were reused unchanged.
- Verification: new `tests/test_crm_workspace.py`, `tests/test_crm_pixel.cjs`,
  `tests/verify_campaigns_first.cjs`; updated `tests/crm_fixtures.py`,
  `tests/crm_postgres_server.mjs`, `tests/fixtures/campaigns_v1_preview.py`,
  `tests/test_crm.py`, `tests/test_crm_boundaries.py`, `tests/test_crm_campaigns_v1.py`,
  `tests/test_crm_postgres.py`, `tests/test_crm_resend_marketing.py`, `tests/test_crm_ui.py`.
- This runbook: `docs/CRM_CAMPAIGNS_FIRST.md`.

Pre-existing changes to `tests/test_email_permanent_reliability.py` and the untracked
`tests/verify_campaigns_v1.cjs` were preserved. The existing untracked preview fixture
was extended for this workflow; use the new `verify_campaigns_first.cjs` script.

## Verification and known limits

All external APIs are synthetic/mocked in automated verification. Local database
fixtures use loopback only. Browser fixture delivery is mocked and external browser
requests are blocked; product artwork is visibly synthetic.

- CRM: 118 tests passing, including 29 workspace unit/SQL tests.
- Email/SMTP/IMAP regression: 140 tests passing.
- Accounts: 79 passing in a separate process.
- Navigation/startup/sidebar: 34 passing in a separate process.
- Product Upload prompts/modes/collections: 48 passing in a separate process.
- Edition Ops table-editing/stability/new-product-pull: 39 passing.
- All 34 changed/new Python files compile; `git diff --check` passes.
- Pixel sandbox assertions pass for disabled/denied/granted consent, five events,
  withdrawal including an async race, PII minimization and fetch options.
- Read-only GraphQL operations pass the official Shopify schema validator. One
  attribution validation attempt failed because PowerShell split the multiline
  argument; joining the argument fixed validation without changing the operation.
- A combined 161-test Accounts/navigation/Product Upload run had 22 Streamlit
  form-context failures. All three component suites pass when isolated as above.
  Do not hide this test-process isolation limitation or label it a product failure.
- Browser workflow: create → audience → starter → products → edit → mobile/desktop
  preview → save → reopen and full reload → Review → mocked single internal test.
  Screen sizes 1440×900 and 1920×1080; email widths 320/375/430/600. Screenshots and
  verification JSON are in ignored `output/campaigns-first/`, including full email
  screenshots. No actual Gmail/Outlook or live storefront/provider result is claimed.

The Email, Accounts and wider regressions were run separately with:

```powershell
.venv/Scripts/python.exe -m unittest tests.test_email_service tests.test_support_email tests.test_support_email_v2 tests.test_email_connection_recovery tests.test_email_permanent_reliability tests.test_email_send_ux
.venv/Scripts/python.exe -m unittest tests.test_os_accounts
.venv/Scripts/python.exe -m unittest tests.test_navigation_performance tests.test_app_startup_scope_regression tests.test_sidebar_navigation_cleanup
.venv/Scripts/python.exe -m unittest tests.test_product_upload_prompts tests.test_product_upload_modes tests.test_product_upload_collections
.venv/Scripts/python.exe -m unittest tests.test_edition_ops_table_editing tests.test_edition_ops_stability tests.test_edition_ops_new_product_pull
```

To repeat the browser check, run the loopback database above, then:

```powershell
.venv/Scripts/python.exe -m streamlit run tests/fixtures/campaigns_v1_preview.py --server.address 127.0.0.1 --server.port 8517 --server.headless true --browser.gatherUsageStats false
# In another terminal with Playwright available (Edge installed):
node tests/verify_campaigns_first.cjs
node tests/test_crm_pixel.cjs
git diff --check
```

On this workstation Playwright is available by setting `NODE_PATH` to
`C:/Users/hello/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules`.
Run CRM database tests before browser checks, since legacy test fixtures truncate
their own local tables. Restart the fixture server after changing imported modules.

Explicit saves are used; browser close/reload before saving can lose unsaved edits.
Campaign navigation is guarded. Interactive audience calculation is manually paged
and capped at 20,000 selected profiles / 2,000 pages; larger audiences require a
future background planner. Saved templates are currently bounded to 200 rows.
No destructive crop editor, asset upload service, image byte-size probe, multi-touch
attribution, recipient profile mirror or external-provider-history import exists.
The existing Streamlit HTML component emits a deprecation warning in this runtime;
its sandboxed previews still passed. Dependency/runtime upgrades need a separate review.

## Rollback and recommended next stage

Before an approved deployment, take the normal database backup and retain the
previous application revision. Keep all marketing/flow/pixel switches off throughout.
If reverting the application, preserve new campaign/template/settings/event tables;
do not drop records. The migration normalizes statuses, so a full old-UI rollback
must either retain the new status compatibility mapping or apply a reviewed inverse
status/constraint migration. Existing immutable template/campaign history remains
available for recovery. Never restore by overwriting current Shopify customer data.

Next stage: Nathan reviews this local diff and migration plan, confirms business
identity/internal mailboxes, then separately approves deployment and ONE internal
test. Prove webhook receipts, unsubscribe reconciliation and pixel consent/CORS in
a controlled test before enabling any production tracking. Choose the Resend
marketing plan/management credential boundary, review DMARC and the live Klaviyo /
Shopify overlap, then design and approve a small engaged-audience Broadcast pilot.
No production sends, schedules, automation activation or consent writes are approved
by this implementation.
