# Email Campaigns V8 — Location and Shopify buyer segments

Local implementation, 11 October 2026. No commit, push, deployment, live send,
consent change, segment mutation or production migration was performed.

## Settings and persistence

The existing Settings / Editor / Templates composer remains. Its country selector
is now **Location**; a native searchable **Segments** multi-select sits directly
below it. Selected chips can be removed individually or cleared together. A count
and compact audience estimate follow. No new uploader or campaign page exists.

`new_compose` initializes only new campaigns to Global (All subscribers), no buyer
segments. The shared automation document factory retains its prior AU default.
Existing documents retain geography, saved buyer IDs, and advanced audience rules;
opening a draft no longer replaces an advanced audience with country rules.
Advanced audiences remain supported through their existing resolution path; the
buyer selector is disabled for them rather than silently changing their meaning.

Draft JSON stores `shopify_segment_ids` and `shopify_segment_store`. These fields
are optional for legacy documents, validated, included in preparation fingerprints
and audience-change history. Deleted IDs remain visible as unavailable selections;
fresh resolution fails closed. Renames retain IDs. Store mismatches block sending.

## Shopify definitions and synchronization

Read-only discovery confirmed all 28 requested segments. Exact IDs and untouched
saved queries are recorded in `shopify-buyer-segments-observed.json` (evidence only,
not runtime configuration). Runtime discovery resolves exact names per configured
store and preserves discovered IDs across renames. Duplicate names require review.
The original 23 definitions include `SC_HIST_*` customer-tag alternatives; the five
new motorsport definitions use purchased product tags only. Neither is rewritten.

`crm_buyer_segments.py` reuses the existing paginated Shopify adapter, rate-limit
gate, bounded retries and fresh member-ID queries. A five-minute authoritative
poll reconciles purchases, customer changes, consent, refunds and cancellations
according to Shopify's current saved queries, independently of webhook ordering.
Webhooks are not treated as proof of membership. No segment/customer mutation exists.

The existing worker gains an independent polling thread. A PostgreSQL advisory
transaction lock serializes refreshes across worker/web processes. Existing
server-only `crm_runtime_state` stores an atomic, store-scoped projection containing
definitions, customer IDs and the last successful timestamp, never email addresses.
A failed refresh preserves the prior snapshot. The UI uses a bounded background
cache scoped by Shopify namespace and database connection factory. Shopify I/O
does not run synchronously in the Settings render. Stale/error/loading states are
explicit. A worker is needed for continuous synchronization when no page is open.

No new table or migration is introduced. Existing reviewed CRM workspace,
preparation, runtime-state and durable-dispatch migrations must already be applied.

## Audience and dispatch safeguards

The authoritative query is **Location AND (saved query A OR saved query B …)**.
No selected IDs means no sporting-interest restriction. Locations reuse existing
Shopify definitions and country/tag mappings; no country segments are created.

Membership is deduplicated by customer identity, then current profiles are grouped
by normalized email. Existing invalid-email, consent-conflict, subscription,
suppression and Smart Sending checks apply. Unique customer IDs, eligible final
deduplicated recipients and excluded counts come from actual resolution, never
addition of segment totals. They are labelled estimates, not live delivery totals.

Background audience preparation is reused. Review and queue resolve selected
definitions and membership again. At each selected-segment native batch submission,
fresh membership, profiles, consent conflicts and local suppressions are checked.
Only unsafe recipients are removed; the frozen reviewed audience is never expanded.
An already attempted batch cannot be changed to a different retry payload: changes
hold it for review. Existing provider suppression, webhook stop-state checks,
lease fencing, unsubscribe URLs, kill switch and provider idempotency remain.
Scheduled batches use this same boundary when due. Shopify failure prevents
provider submission. Existing campaigns without buyer IDs retain their prior path.

Fresh checks add Shopify reads to **buyer-targeted** dispatch. This intentionally
does not retain the old zero-Shopify-I/O claim for that path. Production throughput
for large selected audiences has not been measured.

## Permissions, limits and release checks

- Existing app needs `read_customers` and protected customer-data access for saved
  definitions, membership, current consent/profile and unsubscribe fields.
- Product tagging separately needs `read_products` and `write_products` plus the
  existing authenticated product create/update webhook subscriptions.
- Connector read success does not prove the deployed application's own token scopes.
- Existing member pagination refuses partial, duplicate or changing pages and
  audiences over 20,000 IDs. Complex queries requiring Shopify asynchronous query
  jobs currently fail closed through the existing adapter; no async job creation
  was added. Such a response is a release/use blocker for the affected audience.
- A read-only Shopify check accepted Australia AND (Cricket OR Motorsport) and
  returned 354 segment members. This was not a consent/suppression-verified send
  total. No customer records were exported for that check.
- Production worker availability, database prerequisites and app-token capabilities
  must be checked before a future release; none was changed here.

## Tests and performance

See `SHOPIFY_SEGMENTS_PRODUCT_UPLOAD_CAMPAIGNS_RELEASE.md` for final run totals,
before/after timings, responsive browser evidence and outstanding baseline failures.
Fixtures cover all-subscriber defaults, restored AU drafts, empty/single/multiple
selections, union/overlap, consent/suppression, deletion/rename/store isolation,
outage, pagination, atomic SQL cache, queueing, scheduled dispatch and duplicates.
Actual sending is replaced by a local fake transport; SQL uses disposable loopback
PGlite. Browser tests use cached synthetic data and block external requests.

## Files

`crm_buyer_segments.py`; audience-related hunks in `crm_campaign_controls.py`,
`crm_campaign_page.py`, `crm_campaign_content.py`, `crm_campaign_audience_prepare.py`,
`crm_campaign_send.py`, `crm_campaign_dispatch.py`, `crm_campaign_store.py`,
`crm_worker.py`; tests `test_campaign_buyer_segments.py`,
`test_campaign_buyer_dispatch.py`, `test_campaign_buyer_ui.py`,
`fixtures/campaign_buyer_segments_preview.py`, `run_buyer_segments_local.py`,
`serve_campaign_buyer_preview.py`, `check_campaign_buyer_browser.py`; intentional
Location-label/fixture changes in `test_crm_campaign_v2.py` and
`test_crm_segment_performance.py`; reports and `buyer-segments-v8-evidence/`.

The separate collector-template task also edits `crm_campaign_content.py`.
Its imports/render hooks are unrelated and must not enter this release. Inbox
files and every other task's changes remain untouched.

## Deployment and rollback

Review an isolated patch/selection, not whole dirty shared files. Ship the primary
application and existing webhook/worker code together only after approval and
production prerequisites pass. Do not create services or activate marketing.
Observe sync completion for all 28 actual IDs, then preview audiences without sending.
Rollback requires pausing affected buyer-targeted queued campaigns before reverting
code: older code must not interpret their documents as unrestricted audiences.
Keep stored draft selections/projections for recovery. Do not remove product tags
or customer history as rollback; tag corrections require a separate reviewed action.

Shopify references: [saved segments and membership](https://shopify.dev/docs/apps/build/marketing-analytics/customer-segments),
[membership connection](https://shopify.dev/docs/api/admin-graphql/2026-04/connections/CustomerSegmentMemberConnection),
[complex asynchronous queries](https://shopify.dev/docs/apps/build/marketing/customer-segments/migrate-to-async-queries).
