# Campaign audience preparation — local validation, 2 October 2026

## Root cause and former flow

The modal already opened before its background ReviewJob finished. The expensive
eligibility work, however, only began at that point. Review identity included the
whole draft, so changing copy also repeated eligibility. Native markets already
used selected membership and targeted email conflicts, not a store-wide scan.

For 1,093 unique selected identities the fixture requires one segment catalogue
request, five membership pages, 22 profile batches and 44 email-conflict groups:
72 Graph operations. Profile batches and conflict groups previously ran serially.

Queueing had a separate bottleneck: 1,093 suppression reads and 1,093 individual
recipient inserts. The historical queue fixture measured 2,197 SQL statements.
This path already queued worker jobs rather than sending email in the browser.

## New flow and freshness

Audience selection -> 400 ms debounce -> read-only background preparation ->
session-owned eligibility result -> immediate review shell -> current content,
settings, scheduling and immutable database snapshot -> fresh queue safety checks
-> one transactional bulk recipient insert -> existing worker delivery.

Preparation starts after composer output and from the existing market fragment.
Two preparation jobs may run globally; each uses at most two pending Shopify
reads. Shopify's existing global two-request semaphore, cost pacing and retries
remain authoritative. Pages within each membership/conflict query remain serial
and fully checked for completeness and cursor instability.

The key includes Shopify namespace, audience definition, market, smart-sending
hours, sender/reply-to/contact and eligibility policy version. Subject, body,
images, title and delivery timing do not invalidate eligibility. Content, settings
and schedule remain part of the separate ReviewJob identity.

Results are valid for 60 seconds after completion. Identical pending jobs and
valid results are reused. Expired results retain their visible counts during
refresh, but cannot authorize a new review. A newer preparation replaces the old
ReviewJob, preventing an older completed review from overriding fresher results.
Only one active audience cache is retained per session, with safe reuse across
campaigns using identical eligibility inputs. An obsolete worker never writes session state. Only the current session pointer
selects the visible result. Errors persist until explicit Retry; polling does not
create a retry storm. One previous compact result is retained, not a growing chain.

Snapshots retain counts, exclusion reasons, recipient IDs/hashes and narrow
scheduling evidence. Raw profiles, email lists and unsubscribe tokens are not
retained. Authoritative provider profiles are transient. No customer mirror or
new infrastructure service was added.

## Safety and queue boundary

Existing eligibility, normalized-address deduplication, conflicting consent,
incomplete identity responses and Shopify unsubscribe URL verification remain.
Campaign-specific profiles omit names, tags, order history and spending data,
while retaining both consent sources, native email validity, unsubscribe URL and
the existing scheduling country/province/postcode/timezone evidence.

Native preparation reads only matching local suppression/recent-send rows.
Queueing freshly fetches the frozen recipient IDs in bounded batches, rechecks
consent, identity and native unsubscribe URLs, and reads suppressions in one
bounded query plus the existing in-transaction check. Recipients can only be
blocked, never added. The old conservative inactive-suppression behavior at
queueing is preserved. Missing profiles remain blocked; contradictory or
unexpected identities fail closed.

The existing draft row lock, prior-campaign check, unique campaign/hash/customer
constraints and stable send identities remain. Bulk insertion retains
`ON CONFLICT DO NOTHING` and commits together with campaign/template/audit rows.
The queue boundary renders and validates final tracked HTML once, reusing that
size result for readiness. Content/settings/version/size/tracking/catalogue and
scheduling checks remain.

No worker or transport changes were made. The worker still freshly checks consent,
identity, native unsubscribe, local suppressions, provider suppressions and smart
sending before submission. Scheduled delivery retains its frozen audience and
existing dispatch-time/overdue guards. Queue acceptance does not wait for delivery.

## Measured evidence

All timings below are local, fabricated data, with **5 ms simulated latency per
Graph operation**. They are not measurements of production Shopify or Resend.

| Selected members | Historical preparation | New cold preparation | Warm reuse | Cold Graph operations, before/after |
|---:|---:|---:|---:|---:|
| 50 | 31.5 ms | 27.3 ms | 0.30 ms | 5 / 5 |
| 1,000 | 476.4 ms | 328.2 ms | 6.06 ms | 65 / 65 |
| 1,093 | 506.2 ms | 360.5 ms | 3.29 ms | 72 / 72 |
| 5,000 | 2,763.4 ms | 1,953.7 ms | 27.97 ms | 321 / 321 |
| 10,000 | 6,693.0 ms | 5,194.8 ms | 38.23 ms | 641 / 641 |

Warm reuse makes zero Graph/provider/database reads. Cold request count is not
reduced: the improvement comes from overlapping bounded reads, narrower profiles,
earlier preparation and avoiding repeated work. Larger fixtures include Python
fixture scans and serialization overhead, so these are scaling evidence, not
provider latency predictions.

Separate 1,093-recipient tests using disposable local PostgreSQL measured:

- Prepared modal open: 10.4 ms in Streamlit AppTest; zero provider reads on open.
- Cold preparation: 393.3 ms; three local database reads.
- Warm content review plus durable snapshot creation: 45.2 ms; zero Graph reads.
- Queue acceptance: 5,920.8 ms historically -> 374.5 ms after the change.
- Queue SQL statements: 2,197 -> 13, including unchanged transaction/audit work.
- Queue Graph reads: 22 freshly fetched batches in both versions, now overlapping.
- Email-provider requests: zero throughout preparation/review/queue acceptance.
- 1,093 persistent recipient jobs; zero provider submissions. Repeating queueing
  with a different operation UUID returns the same existing campaign without any
  additional profile reads or recipient jobs.

An earlier isolated run measured queue acceptance at 13,035.2 -> 273.2 ms.
Local database timings vary; neither number establishes production acceptance time.
AppTest timing also excludes browser/network latency and perceived paint.

Local EXPLAIN ANALYZE: selected suppression query executed in 0.136 ms (small-table
sequential scan); selected recent-send query in 0.076 ms using the existing
`crm_send_due_idx` bitmap path. Suppression hash/customer indexes already exist.
Production plans and historical-table scale were not inspected; no index/schema
change was made.

## Diagnostics

Existing safe stage logs cover segment resolution, membership, profile fetch,
conflict validation, suppression reads, eligibility, rendering and snapshot.
Added deduplication, queue content/profile/suppression/total stages and audience
member/eligible/excluded counts, cache hit, result age and review reuse flags.
Preparation logs logical Graph operations and `Store.q` database reads; internal
transport retries and direct transaction statements are not counted by that
preparation counter. Queue SQL counts above came from the disposable connection
fixture. No addresses, tokens, raw payloads, secrets or campaign copy are logged.

## Files changed for this task

All paths are relative to `C:/Users/hello/Documents/sports-cave-image-factory/`:

- `crm_campaign_audience_prepare.py`
- `crm_campaign_controls.py`
- `crm_campaign_markets.py`
- `crm_campaign_page.py`
- `crm_campaign_review.py`
- `crm_campaign_review_reads.py`
- `crm_campaign_send.py`
- `crm_campaign_send_ui.py`
- `crm_shopify.py`
- `crm_workspace_store.py`
- `tests/crm_fixtures.py`
- `tests/test_crm_fast_review.py`
- `tests/test_crm_audience_prepare.py`
- `tests/fixtures/crm_audience_reads_baseline.py`
- `tests/fixtures/crm_send_queue_baseline.py`
- `docs/CAMPAIGN_AUDIENCE_PREPARATION.md`

The two baseline fixtures preserve the former code solely for offline comparison.
The existing Meta CPC changes were preserved and are outside this task.

## Validation and limits

231 tests passed with `CRM_TEST_POSTGRES=1` pointing exclusively at the repository's
disposable loopback fixture. Coverage includes preparation reuse/invalidation,
debounce/stale results, consent conflicts, suppression, missing identities,
pagination, snapshots, idempotency, actual queue SQL, worker mocked delivery,
scheduling, compact review, first paint, recovery, previews and email-size guards.
The final targeted send/review rerun passed 50 tests; the final preparation-domain
rerun passed 14 tests. Python compilation and `git diff --check` passed.

The reduced campaign-profile GraphQL query passed Shopify's schema validator for
2025-10. Existing legacy consent/email fields produced deprecation warnings; they
were retained intentionally to preserve the existing contradictory-consent veto.
It remains a query, with no new mutation or scope/configuration change.
Reference: [Shopify Customer](https://shopify.dev/docs/api/admin-graphql/latest/objects/Customer).
Database plan interpretation follows [Supabase query optimization](https://supabase.com/docs/guides/database/query-optimization).

Safe for deployment review on this local evidence. Production credentials,
throttle latency, live segment responses, browser paint and production database
plans were not tested. Preparation is session-owned: a page refresh can require
cold preparation; there is no persistent provider-version cache. No production
API/database access, live email, migration, environment/Render change, commit,
push or deployment was performed.
