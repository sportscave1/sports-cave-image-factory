# Wall Preview HD email and consent

Implemented locally; no production deployment or migration application performed.
No Shopify theme files changed. No real customer writes or emails were used for testing.

## Exact files changed

All paths below are relative to `C:/Users/hello/Documents/sports-cave-image-factory`:

- `wall_preview_crm_api.py`
- `wall_preview_crm_store.py`
- `wall_preview_customer.py` (new)
- `wall_preview_email.py`
- `wall_preview_inbox.py`
- `wall_preview_store.py`
- `crm_worker.py` (existing worker integration only)
- `run_migrations.py` (reviewed manifest only)
- `migrations/20261005183000_wall_preview_hd_consent.sql` (new)
- `tests/test_wall_preview_hd_email.py` (new)
- `tests/test_wall_preview_crm_v2.py`
- `tests/test_wall_preview_feature.py`
- `tests/wall_preview_hd_responsive.cjs` (new)
- `tests/wall_preview_hd_ui_fixture.py` (new)
- `docs/WALL_PREVIEW_HD_EMAIL.md` (this report)

## API and persistence

`POST /api/wall-previews/{preview_id}/email` retains the existing Origin allowlist
and `X-Wall-Preview-Token` capability requirement. Old email-only JSON remains valid.
New optional fields: `name`, `image_reuse_allowed`, `marketing_opt_in`,
`marketing_consent_source`, `reuse_consent_source`. The consent fields require actual
JSON booleans; source is `wall_preview_hd_email`. Existing optional `product_url`
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
Production schema was inspected read-only: previews 46, events 7, email jobs 10
columns. Local migration replay verifies previews 51, events 7, email jobs 10,
customer jobs 8. Existing metadata/indexes are retained.

Email capture never uploads, moves or changes the confirmed composite. Deliberate
reconfirmation retains stable client/preview ID semantics and clears image-use
permission for the replacement version. The original capture event preserves the
earlier consent audit. Confirmation upload/Dropbox failure behavior remains the
existing backend contract; no shopper retry UI or theme change was introduced.

Dropbox remains `/Sportscave Team Folder/03_ASSETS/11 Wall Preview Inbox`.
Requested email uses the existing private/revocable app image URL, with the
confirmed high-resolution archive; no Dropbox public sharing link. Subject:
`Your Sports Cave wall preview`. Immediate email is transactional, independent
of either checkbox. Existing consent/suppression checks still guard 4h/24h
marketing follow-ups, and verified purchases suppress them.

## Shopify sync

Existing `shopify_sync.graphql_request` and its configured Admin credentials/API
version are reused. Exact email matching precedes creation on every attempt.
Pagination is bounded and incomplete/ambiguous results prevent creation. An
email-scoped PostgreSQL advisory lock serializes this integration across workers;
Shopify's email uniqueness prevents duplicates after ambiguous create outcomes.
Create uses normalized email and conservative first/last split. Existing nonempty
names are preserved; `tagsAdd` adds `Wall Preview` without replacing other tags.

Only explicit true uses `customerEmailMarketingConsentUpdate`, `SUBSCRIBED`,
`SINGLE_OPT_IN`, and the recorded server consent timestamp. Source is audited
locally: Shopify's `sourceLocationId` expects a real location GID, not this source
string. False/absent performs no consent mutation, including no unsubscribe.
A newer Shopify consent change prevents a delayed job overwriting an unsubscribe.
Customer synchronization retries at most five times, five minutes apart; stale
processing claims recover after five minutes. Reasons/logs contain categories,
not email addresses or provider payloads. Requested delivery runs first in the
existing CRM worker cycle and is not gated on successful customer synchronization.

## Inbox

Separate `MARKETING USE: ALLOWED` / `N/A` and `EMAIL: SUBSCRIBED` badges;
subscription is displayed only from Shopify-confirmed state. HD email job state,
contact/customer association, existing timeline, and a Reuse allowed filter.
Authorization and Files/Social Media behavior remain unchanged.

## Validation and release boundary

- 101 focused Python tests passed (Wall Preview HD/V2/identity/gallery and Social Media page).
- Broader regression: 321 tests, 287 passed, 34 skipped (email transport, Files upload,
  migration connections, Shopify, native automations, triggers, receiver reliability,
  native unsubscribe, Social Media workspace/navigation).
- Browser checks: 1920, 1366, 750, 390, 320px, no horizontal overflow and independent badges.
- Existing storefront adapter: six contract checks passed. Python compilation and
  JavaScript syntax checks passed.
- All five operations validated using Shopify's GraphQL validator; relevant fields,
  mutation inputs and opt-in enum also checked against official 2026-04 pages.
- SHA-reviewed deployment migration manifest and canonical Render topology passed.

No new Render variables or credential path. Before release verify the EXISTING
Shopify installation has `read_customers` and `write_customers` plus protected
customer-data access, apply the reviewed migration, and deploy the web/CRM worker
changes together. Live store scopes and actual provider delivery were not exercised
with real customer mutations. The production schema remains unchanged at 46
preview columns until deployment. Theme rollout is managed separately by the owner.
