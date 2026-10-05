# Wall Preview HD email and consent

The Markets and disclosed-Send extension is implemented locally; no production deployment or
migration application was performed in this pass. The earlier HD-email work is
already present in the current committed baseline.
No Shopify theme files changed. No real customer writes or emails were used for testing.

## Exact files changed in the Markets and disclosed-Send extension

All paths below are relative to `C:/Users/hello/Documents/sports-cave-image-factory`:

- `wall_preview_crm_api.py`
- `wall_preview_archive.py` (new)
- `crm_worker.py` (one additional bounded Wall Preview archive cycle)
- `wall_preview_crm_store.py`
- `wall_preview_customer.py`
- `wall_preview_inbox.py`
- `wall_preview_store.py`
- `run_migrations.py` (reviewed manifest only)
- `migrations/20261005194500_wall_preview_market_country.sql` (new)
- `migrations/20261005051833_wall_preview_hd_send_evidence.sql` (new)
- `tests/test_wall_preview_hd_email.py`
- `tests/test_wall_preview_hd_send.py` (new)
- `tests/test_wall_preview_crm_v2.py` (confirmation queues archive)
- `tests/wall_preview_hd_responsive.cjs`
- `tests/wall_preview_hd_ui_fixture.py`
- `docs/WALL_PREVIEW_HD_EMAIL.md` (this report)

## API and persistence

`POST /api/wall-previews/{preview_id}/email` retains the existing Origin allowlist
and `X-Wall-Preview-Token` capability requirement. Old email-only JSON remains valid.
New optional fields: `name`, `image_reuse_allowed`, `marketing_opt_in`,
`marketing_consent_source`, `marketing_consent_text`, `marketing_consent_version`,
`reuse_consent_source`, `market_country_code`,
`market_country_name`. Country codes require two ASCII letters and normalize to
uppercase; country names are bounded, normalized text with control characters
rejected. Market values are accepted at confirmation too, retained by older email-only requests, and
preserved on retries and deliberate image reconfirmation. The consent fields require actual
JSON booleans; legacy source is `wall_preview_hd_email`. The current Send source is
`wall_preview_hd_email_send`, with the exact disclosed text and version
`wall_preview_hd_email_send_v1` (inferred from that known text when omitted).
An explicit true from the current Send source requires its disclosure. Source,
text, version and server timestamp are retained on the record and capture event. Existing optional `product_url`
and `requested_at` are validated; neither can replace the canonical product/image
or server audit time.

One existing confirmed preview, one recipient, one requested email job. Duplicate
requests return the saved job state without changing the first request's consent.
No inline Resend or Shopify calls. `marketing_subscribed:false` in the immediate
response means no subscription has been confirmed by this API request.

Reuse existing columns:

- `customer_name`, `customer_email`, `shopify_customer_id` for HD contact identity.
- `email_requested_at`, `email_sent_at` and email jobs' `due_at`, `finished_at`,
  `state`, `reason` for requested/queued/sent/failed reporting.
- `marketing_permission` for IMAGE reuse only. False plus a null consent timestamp
  means unknown; false with a timestamp records an explicit refusal.

The additive migration `20261005183000_wall_preview_hd_consent.sql` adds five
preview audit columns and the eight-column `wall_preview_customer_jobs` table
with a due index, unique preview key, RLS and no public table privileges.
The earlier schema inspection found 46 preview columns. This pass re-inspected
production read-only and found previews 51, events 7, email jobs 10, customer
jobs 8. The new `20261005194500_wall_preview_market_country.sql` migration adds
two nullable text fields only. Local replay verifies previews 53, events 7,
email jobs 10, customer jobs 8. Existing metadata/indexes and RLS are retained.

Email capture never uploads, moves or changes the confirmed composite. Deliberate
reconfirmation retains stable client/preview ID semantics and clears image-use
permission for the replacement version. The original capture event preserves the
earlier consent audit. Confirmation commits a durable private copy of the cleaned confirmed JPEG
and an archive job in the same transaction. The existing CRM worker retries one
job per cycle, at most five times, five minutes apart, replacing the same path.
After success it clears the temporary database image. On exhausted retries the
canonical image remains available through the capability-protected app image
route; the backend records failed state for operator intervention. No shopper
Retry Sync state or raw-photo upload is introduced. Reconfirmation supersedes
a pending version under the same preview lock; old versions cannot overwrite it.

Dropbox remains `/Sportscave Team Folder/03_ASSETS/11 Wall Preview Inbox`.
Requested email uses the existing private/revocable app image URL, with the
confirmed high-resolution archive; no Dropbox public sharing link. Subject:
`Your Sports Cave wall preview`. Immediate email is transactional, independent
of marketing consent or image-reuse permission. Existing consent/suppression checks still guard 4h/24h
marketing follow-ups, and verified purchases suppress them.

## Shopify sync

Existing `shopify_sync.graphql_request` and its configured Admin credentials/API
version are reused. Exact email matching precedes creation on every attempt.
Pagination is bounded and incomplete/ambiguous results prevent creation. An
email-scoped PostgreSQL advisory lock serializes this integration across workers;
Shopify's email uniqueness prevents duplicates after ambiguous create outcomes.
Create uses normalized email and conservative first/last split. Existing nonempty
names are preserved; `tagsAdd` adds `Wall Preview` without replacing other tags.

Only submitted true uses `customerEmailMarketingConsentUpdate`, `SUBSCRIBED`,
`SINGLE_OPT_IN`, and the recorded server consent timestamp. Source is audited
locally: Shopify's `sourceLocationId` expects a real location GID, not this source
string. False/absent performs no consent mutation, including no unsubscribe.
The current storefront has no separate marketing checkbox. Its Send disclosure
is: “By selecting Send, you’ll also receive Sports Cave collector emails.
Unsubscribe anytime.” The backend uses the explicit true/source/text evidence,
never image-reuse permission. Legacy false/absent values leave subscription unchanged.
A newer Shopify consent change prevents a delayed job overwriting an unsubscribe.
Customer synchronization retries at most five times, five minutes apart; stale
processing claims recover after five minutes. Reasons/logs contain categories,
not email addresses or provider payloads. Requested delivery runs first in the
existing CRM worker cycle and is not gated on successful customer synchronization.

There is no existing customer-metafield write mechanism in this integration.
The permitted fallback adds `Wall Preview Market: AU` (or the supplied code)
through the same `tagsAdd` operation. Both country fields remain authoritative
on the preview record. This signal is Shopify Markets context, not a verified
home/shipping/billing address. No address input is sent to Shopify and existing
addresses are not changed. Later purchases retain the original preview-market
fields; existing commerce reporting can continue using real order countries.

## Inbox

Separate `MARKETING USE: ALLOWED` / `N/A` and `EMAIL: SUBSCRIBED` badges;
subscription is displayed only from Shopify-confirmed state. HD email job state,
contact/customer association, existing timeline, and a Reuse allowed filter.
Market context renders separately as `MARKET: AUSTRALIA (AU)` when supplied.
Authorization and Files/Social Media behavior remain unchanged.

## Validation and release boundary

- 219 Python tests passed with disposable loopback PostgreSQL: Wall Preview
  HD/Send/V2/gallery, Social Media page, migration connections, Files upload,
  email defaults, checkout publication migration, native automations and
  analytics. Provider writes mocked; no real emails.
- Browser checks: 1920, 1366, 750, 390, 320px, no horizontal overflow and
  independent permission/subscription/market badges.
- Python compilation and JavaScript syntax checks passed.
- Five existing Admin operations passed code-only schema validation, with
  consent input checked against official 2026-04 documentation.
- Additive migration replay, RLS and no-public-read checks passed.
- SHA-reviewed deployment manifest, canonical Render topology and git diff
  whitespace checks passed.

No new Render variables or credential path. Before release verify the EXISTING
Shopify installation has `read_customers` and `write_customers` plus protected
customer-data access, apply the reviewed migration, and deploy the web/CRM worker
changes together. Live store scopes and actual provider delivery were not exercised
with real customer mutations. The production schema remains unchanged at 51
preview columns until both reviewed migrations are deployed/applied. Theme rollout is managed separately by the owner.

## Disclosed-Send migration and validation

`20261005051833_wall_preview_hd_send_evidence.sql` was generated with the
Supabase CLI, moved into this repository’s migration directory, and registered
with its reviewed SHA after the existing dependencies. It adds two nullable
preview evidence fields and a ten-column private `wall_preview_archive_jobs`
table. Combined local schema: previews 55, events 7, email jobs 10, customer
jobs 8, archive jobs 10. Production remains 51 preview columns until the
Markets and evidence migrations are deployed/applied. Existing ten preview
indexes are retained; archive queue has its primary key and due index.
RLS is enabled with no public/anon/authenticated archive-table access.

Five Shopify operations (lookup, create, fill missing name, append tags, consent)
passed code-only connector schema validation. The 2026-04 consent input was
checked against https://shopify.dev/docs/api/admin-graphql/2026-04/input-objects/CustomerEmailMarketingConsentInput.
No new credential paths or Admin operations were added. No live Shopify writes,
Resend delivery, theme updates or deployment were performed.
