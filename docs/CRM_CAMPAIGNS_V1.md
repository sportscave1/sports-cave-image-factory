# Campaigns V1 — local review report

No commit, push, deployment, production migration, real email, Broadcast operation,
campaign scheduling or automation activation is part of this implementation.
`CRM_MARKETING_ENABLED=false` stays the master switch. No environment values change.

## Architecture and source files

- `crm_campaign_page.py`: compact four-step Campaigns workspace: basics, audience,
  email creator, preview/test. Existing navigation and CRM permissions are retained.
- `crm_campaign_content.py`: structured content validation, market policy data,
  locked footer, renderer version 1, prompt factory, preflight, reputation thresholds
  and a disabled Broadcast adapter boundary.
- `crm_campaign_store.py`: draft persistence, optimistic concurrency, version/history,
  duplicate/archive and a single-recipient campaign-test service.
- `crm_eligibility.py`: shared global eligibility service, also used through
  `crm_logic.eligibility` by the existing automation engine.
- `crm_audience.py`: paginated, live read-only Shopify evaluation with exclusion
  breakdown and normalized-email deduplication. Membership hashes stay in session
  memory only. Persisted campaigns contain aggregate counts, never customer lists.
- `crm_resend_marketing.py`: Stage 1 diagnostic remains fixed-content. Its internal
  admin-only transport is reused by the campaign service after loading the saved
  campaign, running preflight and rendering the locked system email.
- `crm_page.py`: routes Campaigns into V1. Other CRM pages keep their existing paths.

## Storage and migration

`migrations/20260928020740_crm_campaign_workspace_v1.sql` was generated with the
Supabase CLI, prepared locally and applied only to disposable local PostgreSQL tests.
It is NOT added to the deployment manifest. It requires the existing CRM V1 migration.

Two server-only tables: `crm_campaign_drafts` and `crm_campaign_history`. Both have
RLS and no public/anon/authenticated grants. The existing server database connection
is used. Drafts store typed content, renderer version, product identity/facts, audience
reference or rules, offer, aggregate counts, author/timestamps, status and latest test
receipt. Edits invalidate tested-version approval. Short transactions atomically
persist before/after history; provider calls happen outside locks. Concurrent edits
cannot silently overwrite a draft or inherit another version's tested status.

These are authoring records, intentionally separate from `crm_campaigns`, which is
connected to the legacy per-recipient worker. No V1 record can enter that queue.
Historical legacy campaigns remain available through existing reporting/storage.
The V1 list shows up to 100 most recently edited drafts or archived records.

Audited actions: create, edit, segment/content change, compliance-status change,
duplicate, archive and accepted test. Test metadata includes campaign/version,
render hash, receipt, timestamp and system footer snapshot. Stage 1 audit storage
records requested/accepted/failed/uncertain submission events with CAMPAIGN TEST
metadata, no secret or message body. Failure after provider acceptance never retries.

## Eligibility and suppression

Only a normalized valid mailbox with Shopify status exactly SUBSCRIBED qualifies.
Purchase is never consent. NOT_SUBSCRIBED, PENDING, INVALID, UNSUBSCRIBED and REDACTED
are excluded. Existing local/provider suppression checks remain in force; normalized
email hashes deduplicate eligible recipients across pages. Counts reconcile raw
members = eligible + reason exclusions. Partial calculations are clearly labelled.
Tests require a complete calculation within 24 hours; future production MUST perform
a new current-data evaluation, never send from saved counts. Consent evidence fields
available from Shopify (state, opt-in level and consent timestamp) have a shared
extractor for future send-time evidence, without creating a customer mirror.

The migration extends the existing `crm_suppressions` reason constraint with
manual_unsubscribe, provider_unsubscribe, hard_bounce, spam_complaint,
invalid_address and admin_suppression. It adds active/provider/campaign references;
existing timestamps and hashed identities are reused. Existing readers conservatively
block ANY suppression record, including one marked inactive. Campaign code never
clears a suppression or changes Shopify consent. Immediate local suppression is the
global policy; production signal ingestion remains a next-stage approval item.

## Compliance and unsubscribe

AU and US have market-aware policy labels but share the stronger explicit-subscription
baseline. UK is a placeholder requiring future legal review, not invented UK/EU rules.
Content must have accurate identity/subject, contact information, a postal business
address and a free, easy unsubscribe without login. The prompt and operator review
cover truthful copy; software cannot verify every factual claim semantically.

New non-secret configuration:

- `CRM_BUSINESS_DISPLAY_NAME` (default Sports Cave)
- `BUSINESS_POSTAL_ADDRESS` (no default or private address)
- `CRM_BUSINESS_ADDRESS_VERIFIED=true` only after manual business-address verification
- `CRM_BUSINESS_WEBSITE` (default https://www.sportscaveshop.com)
- `CRM_SENDING_DOMAIN_VERIFIED=true` only after verification evidence is documented

Sender/contact and API configuration reuse the five Stage 1 variables. No key is
displayed or persisted; `RESEND_API_KEY` is not used. The supplied domain-verification
statement is labelled as reported, not treated as a live DNS check.

The footer is generated outside all editable/AI fields and text is HTML-escaped.
Missing postal details are visibly flagged. No fake unsubscribe href is used: layout
and test emails explicitly show an inactive unsubscribe notice. This is a diagnostic
preview, NOT production compliance. Live readiness is always false until a proven
body unsubscribe link AND List-Unsubscribe / List-Unsubscribe-Post handling exist.
The existing `/webhooks/resend/crm` and `/crm/unsubscribe` handlers are not changed or
declared production-ready for Broadcasts. No test creates an unsubscribe token that
could alter a Shopify subscriber's consent.

AU/US primary references reviewed:
- https://www.acma.gov.au/avoid-sending-spam
- https://www.ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business

## Email creator and design

Fields cover subject, preheader, hero/alt, eyebrow, headline, intro/body, collector
block, CTA, secondary block and closing/PS. The prompt uses supplied canonical product
facts only; price and edition availability are omitted when the existing product
reader does not provide them. Offers must be explicit and reviewed. No OpenAI call.
Copy Prompt uses the clipboard; pasted COPY JSON accepts text fields only, never
footer, URLs, raw HTML or product facts. Applying AI copy clears review confirmation.

Single-column, table-based 600px maximum email with inline CSS, Outlook conditional
width wrapper, 100% mobile width, fallback Arial/Helvetica, preheader, proportional
images, readable type and large CTA. No forms, JS, layout-grid dependency or critical
image-only text. Alt text and HTTPS URLs are checked. Hero images are not cropped;
the actual uncropped layout is previewed. UI guidance: 600–1000px source, ≤1MB target,
16:9/5:3 hero, 4:3/1:1 product image. No unsupported image byte-size claim is made.

Layout preview widths: 320, 375, 390, 430 and 600px. These are browser layout previews,
not Gmail/Outlook engines. Single-column structure avoids stacking failures. Plain
text is generated independently and includes contact/footer information.

## Test and production boundaries

Draft/Needs Review/Test Ready/Compliance Blocked/Tested/Canceled are authoring states.
Tested means the saved version's diagnostic was accepted by Resend, not inbox delivery
or live compliance approval. No Ready for Future Live Send, Scheduled or Sent transition
exists in V1; the database also rejects these statuses for authoring records.

Only an active admin can send one manually typed recipient after explicit confirmation.
No segment, list, customer object or body override reaches the test transport. The
message is labelled CAMPAIGN TEST in subject/body and audit, has HTML/plain text and
never increments production recipient counts. Page load, refresh, save, preview,
prompt generation and audience calculation cannot send. Stage 1 diagnostic still works.

Future reputation focus: delivered, clicks, attributed purchases/revenue, unsubscribes,
hard bounces and complaints. Opens are secondary. Complaint target <0.10%; critical
≥0.30%, implemented as policy warning thresholds, not invented provider limits.
Engaged-audience warm-up must be reviewed before any first production Broadcast.

## Future Broadcast permissions and next stage

Planned path: fresh Sports Cave eligible audience → minimal Resend delivery mirror /
segment → Broadcast queue/throttle → verified events → permanent Supabase history →
local suppression and an explicitly approved Shopify unsubscribe sync.

Current Resend key documentation offers `sending_access` (send only) and `full_access`
(create/read/update/delete resources). Creating/managing contacts, segments and
Broadcast drafts requires resource-management authorization, which the current send-only
key does not provide. Do not upgrade or reuse an older key. Next stage should approve
a separate management credential or supported OAuth scopes after capability review;
do not claim a granular API-key scope exists when the published API offers only these
two choices. No management credential is read by V1.

References:
- https://resend.com/docs/api-reference/api-keys/create-api-key
- https://resend.com/docs/api-reference/broadcasts/create-broadcast

Recommended next stage: review/apply migrations and business identity settings;
approve scoped provider management; prove Broadcast-managed unsubscribe and one-click
headers, authenticated webhook ingestion, immediate local suppression, consent evidence,
DMARC and receipt/history correlation. Then separately approve a single controlled
admin campaign test and client rendering checks. Live/bulk/warm-up activation requires
another explicit approval and must not reuse the legacy per-recipient campaign loop.

## Verification tools

`tests/test_crm_campaigns_v1.py`: policy, renderer, prompt, preflight, SQL persistence,
concurrency, history, suppression and mocked single-recipient sending.
`tests/crm_postgres_server.mjs`: disposable loopback PGlite with both CRM migrations.
`tests/fixtures/campaigns_v1_preview.py`: synthetic Shopify/local SQL browser fixture;
real network and test sending are blocked.
`tests/verify_campaigns_v1.cjs`: headless Edge checks at 1440×900 and 1920×1080 plus all
five email widths, creation/editing, counts, prompt clipboard and no live-send action.
Screenshots and machine-readable results are written under `output/campaigns-v1/`.

No live provider/DNS/production database verification is claimed. Missing production
postal identity, unproven unsubscribe/webhooks/DMARC and management permissions are
intentional live blockers. Workflow storage still requires separately approved migration.

Final results: 89 CRM/policy/database/UI tests, 140 Email regressions, 48 Product
Upload tests and 22 Edition Ops tests passed (299 total). The Email/Product Upload/
Edition Ops suites were run in separate interpreters because their combined legacy
AppTests leave shared Streamlit form context behind. All 13 changed Python files
compiled and `git diff --check` passed. Browser creation/editing, aggregate audience
counts, clipboard copying, disabled production controls and all five layout widths
passed on headless Edge using synthetic Shopify and disposable local SQL only.
No horizontal email overflow was detected at the tested widths. Screenshots were
visually inspected. These checks do not assert real Gmail/Outlook compatibility.

Additional changed verification files: `tests/test_crm_ui.py`,
`tests/test_crm_postgres.py`, and `tests/test_email_permanent_reliability.py` update
expectations for the V1 disabled-delivery notice and two additional RLS tables.
The test database bootstrap adds the new migration; no production bootstrap changes.
