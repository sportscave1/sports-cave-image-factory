# Reviews V1 — local implementation and release checklist

Implemented locally on 3 October 2026. No production migration, provider sync,
Shopify extension release, theme change, email send, commit, push or deployment
was performed. Existing unrelated changes in this checkout were preserved.

## Architecture and review integrity

One top-level **Reviews** route contains exactly **Overview**, **Import reviews**
and **Display**. Access uses the existing active-account/page permissions.
Server-only canonical tables retain source identity, normalized plain text,
product mapping, moderation, local replies and an audit trail. Imported customer
emails become one-way normalized SHA-256 hashes for deduplication; raw emails
are not stored in review records or import jobs.

Deduplication first uses provider/store/review identity. Without a source ID it
uses deterministic source, product hints, rating, text, date and reviewer identity.
Different reviews are not merged merely because their product or reviewer matches.
Product matching checks exact ID, handle, URL, SKU and title in that priority order.
An ambiguous higher-priority match stays unresolved. Unmapped reviews remain
visible to staff for correction and are excluded from storefront publication.

Staff can reply, publish, unpublish, archive, mark spam and resolve a product
mapping. Imported provider verification is retained as provenance, **not**
converted into a Sports Cave Verified Purchase badge. Moderation policies are
manual or publish-all, independent of rating. No automatic positive-only filter.

## Sources and importing

UTF-8/BOM CSV supports up to 10 MB and 10,000 rows, comma/semicolon/tab delimiters,
automatic aliases and explicit column mapping. Fields:

`source_review_id`, `product_id`, `product_handle`, `product_url`, `product_sku`,
`product_title`, `reviewer_name`, `email`, `rating`, `title`, `body`, `created_at`,
`source_verified`, `merchant_reply`, `status`.

Preview reports invalid rows, duplicates and unresolved products before confirmation.
CSV dates without a zone use UTC; missing original dates remain unknown and do not
inflate the 30-day KPI. HTML/script/style input is reduced to bounded plain text.
XLSX and media imports are outside V1.

Judge.me CSV works through the same importer. The official read-only API adapter
uses `GET https://api.judge.me/api/v1/reviews`, `api_token`, `shop_domain` and bounded
100-row pages. Merchant setup requires **JUDGEME_PRIVATE_API_TOKEN** in server
configuration and the existing **SHOPIFY_STORE_DOMAIN**. No credentials were added
or changed during this task. The UI distinguishes configured credentials from a
verified sync; no live connection has been verified here.

Judge.me's list endpoint does not supply merchant replies or video URLs. Its
internal product ID is not treated as a Shopify product ID: `product_external_id`
is used when supplied, with unresolved mappings requiring staff attention.
Repeated manual syncs reconcile bounded pages and update existing source IDs;
local replies/moderation survive. This is not an undocumented updated-since delta
endpoint, webhook integration or scheduled sync. No scraping or provider writes.
Reference: https://judge.me/help/en/articles/8409180-using-judge-me-api

Durable imports use the existing CRM worker, one 100-review chunk/page per tick.
Short row-lock claims, a lease and a claim-generation check protect progress.
Up to three failed attempts end in FAILED with a safe error code. Repeating an
import is idempotent. Imports continue with marketing disabled and never send email.

## Overview and KPI definitions

Five cards: average rating, total reviews, reviews in 30 days, 5-star rate, needs
attention. Average/total/5-star share PENDING and PUBLISHED records; archived/spam
are excluded. Needs attention counts each active review once if pending, unmapped
or rated 1–2 without a merchant reply. The 30-day count is an exact rolling UTC
window using original known dates. No reviews gives unavailable average/5-star
rate rather than a fabricated rating.

The table shows product, reviewer, rating, text, date, source and status with
detail/actions; SQL search, rating/source/date/product/status filters and bounded
25-row pagination. A detail dialog retains order/customer links only for genuinely
verified native context. No complete review table is loaded into the browser.

## Shopify display and native submissions

Theme App Extension: `shopify_customer_account/extensions/sports-cave-reviews`.
Three section app blocks: **Product reviews**, **Review stars**, **All reviews**.
The star block links to the stable product-review anchor and fetches summary only.
All reviews includes product thumbnails/links, rating/search/product filtering,
sort and bounded Load more. Merchant replies and original dates respect Display
settings. All browser output uses text nodes; no arbitrary HTML is inserted.

Release/register this extension through the existing Shopify app in an authenticated
development environment, then add blocks in Theme Editor. Add All reviews to a
normal merchant-created page such as `/pages/reviews`; this task creates no live
page or theme edits. Each block needs the existing server's HTTPS `/reviews/public`
URL. Storefront data is disabled by default until explicitly enabled in Display.
Extension UID registration/app configuration release validation remains pending.
Reference: https://shopify.dev/docs/apps/build/online-store/theme-app-extensions/configuration

Display settings include verified badges, date, thumbnail, replies, page size,
default sort, gold accent, density and rating-neutral moderation. Public responses
contain mapped PUBLISHED reviews only, without customer/order IDs, email hashes or
private provenance. Scoped 30-second caches, pagination, rate limits and a bounded
published-product selector keep requests small. Numeric and full Shopify IDs
resolve to identical review counts.

Native submissions require a 30-day opaque request token issued only after a fresh
Shopify read confirms the order/customer relationship and exact purchased product.
Cancelled orders and incomplete evidence fail closed. Tokens use the existing
server secret with a distinct HMAC purpose; only their hashes are persisted.
Submission locks the token, rejects expired/invalid/bot payloads, requires public
display consent and is idempotent. Only this verified context can set native
Verified Purchase; arbitrary imported flags cannot. Forms are rate limited,
bounded, escaped, no-store and suppress referrer leakage.

## Review-request automation handoff

Display can create an existing Email Automation **draft**: order fulfilled,
exact selected product rule, 1–90 day wait, one review-request email. It opens the
existing Automation editor for review/publication; no second email editor or engine.
An opt-in immutable marker is replaced with the verified token URL at worker send
time. Existing consent, suppression, marketing gates, tracking, email-size checks
and transport remain authoritative. Ordinary automations do not enter this branch.
The existing public CRM URL must route the new review endpoints, and the existing
secret must satisfy its minimum length; no new review-token secret is required.

## Performance evidence and limits

The shell emits before SQL results. Cold Overview uses two summary queries and
one bounded page query independently on the existing small shared read pool.
Hidden Import/Display tabs do not run their queries. Session reads have a 60-second
TTL; last-good data remains through refreshing/error/incomplete results. Search and
filters change only table keys. A completed import invalidates affected groups once.

Import matching uses at most five set queries per batch of up to 200 hints, instead
of one product query per review. Existing-ID checks are also batched. Normal page
loads use the existing local product index, no Shopify scans/customer/order reads.
Fresh order reads occur only for native request verification.

Storefront JavaScript is 6,282 bytes and CSS 1,848 bytes uncompressed. No framework,
image downloads before visibility, tracking cookies or provider browser calls.
Widgets lazily load on intersection, abort superseded requests, reject stale
responses and retain displayed reviews on errors. Default page size is eight
(configurable maximum twenty); rating totals are incremental aggregate lookups.

Local tests demonstrate request bounds and immediate shell emission, not real
Shopify/Judge.me latency. Synthetic screenshots use fixture data and actual widget
assets: `docs/performance-evidence/reviews/overview-{width}.png` at 1920, 1366,
750, 430, 390, 375, 320; `storefront-{width}.png` at 600, 430, 390, 375, 320.
Browser assertions check overflow, lazy tabs, escaping, pagination, summary anchors,
default sort and last-good values after refresh failure. Live theme rendering,
provider permissions, large production data plans and actual email handoff still
require connected-environment checks.

## Migration and changed files

Migration `migrations/20261002152512_reviews_v1.sql` creates seven private RLS tables,
five named indexes, transactional aggregate maintenance and revoked public grants.
It adds no customer mirror or theme data. It is registered with its reviewed SHA-256
in the existing deployment manifest. Read-only schema verification remains fail
closed before/after deployment commits; no request-time DDL. Applied only to the
disposable local PostgreSQL-compatible test fixture during this task.

New runtime files: `reviews_model.py`, `reviews_store.py`, `reviews_import.py`,
`reviews_worker.py`, `reviews_cache.py`, `reviews_public_cache.py`, `reviews_schema.py`,
`reviews_submission.py`, `reviews_http.py`, `reviews_page.py`.

Integration edits: `app.py`, `os_accounts.py`, `crm_worker.py`, `crm_engine.py`,
`crm_automation_definition.py`, `crm_automation_store.py`, `webhook_server.py`,
`run_migrations.py`, `tests/crm_postgres_server.mjs`.

Extension files: `shopify.extension.toml`, `blocks/product-reviews.liquid`,
`blocks/review-stars.liquid`, `blocks/all-reviews.liquid`, `assets/reviews.js`,
`assets/reviews.css`, `locales/en.default.json`, `snippets/.gitkeep`.

Tests/evidence: `tests/test_reviews.py`, `tests/test_reviews_ui.cjs`,
`tests/fixtures/reviews_preview.py`, the twelve screenshots above, this document.
Other dirty checkout files belong to earlier work, not this Reviews change.

## Validation

- 118 tests passed: Reviews + account permissions + sidebar navigation.
- Reviews-only final rerun: 33 tests passed on the disposable local database.
- Existing Automations, Campaigns home/first paint, Inbox/loading: 67 passed.
- Send-flow regression: 22 passed on a fresh isolated fixture. A prior shared-fixture
  run encountered existing recent-send suppression contamination; fresh isolation
  removed it without changing send protections.
- Browser matrix: seven OS widths, five storefront widths; passed.
- Shopify CLI Theme Check (`theme-app-extension`): no findings (`[]`). The skill's
  validator could not load its bundled dependency; installed CLI was the fallback.
- Python compilation and `git diff --check`: passed.

Local implementation is ready for deployment review. Live operation is not yet
verified: deploy the reviewed migration, register/release the extension, configure
merchant block URLs, test provider credentials, and perform an authorized store
smoke test before enabling storefront display or publishing review-request emails.
