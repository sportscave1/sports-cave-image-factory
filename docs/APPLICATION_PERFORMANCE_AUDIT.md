# Sports Cave OS application performance audit — 8 October 2026

Implemented against the current repository, preserving the existing Streamlit UI,
email/edition/Meta engines, authentication rules and production service topology.
Nothing was deployed and no production business action or database migration was run.

## Findings and changes

1. **Shell request lifetime:** an outstanding status request could complete after
   its toolbar controller was destroyed, update the persistent DOM, and schedule
   another obsolete polling timer in `finally`. GET requests now deduplicate
   while pending, abort on controller destruction/account revision change, reject
   late responses, and cannot schedule callbacks or fetch from a destroyed
   controller. Mutations are neither deduplicated nor cancelled mid-flight. The
   existing notification intervals, SSE and provider logic remain unchanged.
2. **Recovery installation and observer work:** Chromium testing against local
   Streamlit 1.58 found DOMPurify dropping the recovery script because a compact
   less-than comparison resembled markup. Comparison whitespace fixes the actual
   sanitizer incompatibility. Installation is now idempotent in the main document;
   mutation notifications coalesce to one check per animation frame, and source
   text is read once per Python process. Cancelled health-check responses cannot
   reload the page or restart a destroyed recovery controller. Existing bounded recovery, disabled-widget
   protections, page-hide cancellation and no-I/O healthy focus behaviour remain.
3. **Accounts/authentication:** individual account reads fetched permissions in a
   second SQL round trip; listing N accounts fetched permissions N more times.
   Correlated permission arrays now return identity and permissions in one current
   SQL snapshot. No authentication cache/TTL was added or extended. Password
   material remains excluded from account listings. Existing permission indexes
   already support these queries; no schema/index change is required.
4. **Analytics:** the Overview loaded all four breakdowns eagerly. Only the selected
   breakdown now loads, inside a fragment that owns all its layout elements. Tab
   interactions cannot rebuild the summary, chart or shell. Failed tab reads have
   a local error/retry path. A per-session report store avoids repeating its
   successful schema initialisation on every page rerun. Saved report display
   reads reuse the existing bounded `DisplayCache` implementation: 30 seconds,
   10 for realtime, 3 for empty results, with no cached exceptions. Keys include
   property, contract and exact dates; owner scope includes account identity,
   revision, status, role, timezone and permissions. Explicit queue operations
   bypass read caching and invalidate it after success.
5. **Home:** the existing single-query weekly work bundle and its transformations
   are reused for up to 30 seconds on return navigation. This is display data only.
   The cache is session/account/permission/date scoped and invalidated by the
   existing Planner data-refresh bridge. Authentication and all operational
   decisions still use fresh authoritative reads. Calendar caching was already
   present and is unchanged.
6. **Reporting:** archive filters and report selection now rerun in their own
   fragment, preserving the surrounding workspace. Archive/detail/CSV helpers
   still enforce their existing permissions. Send/test paths are unchanged.

Each display cache is limited to 32 entries and 4 MiB and returns independent
copies. There is no shared customer-data cache, new service, paid dependency,
new polling loop, artificial navigation delay or Render plan change.

## Measurements

### Production observations, read-only

Authorised Render workspace: Nathan's workspace. Canonical service:
`sports-cave-os` (`srv-d8kl4on7f7vs73dvavv0`). Sample collected on 8 October,
approximately 06:42–07:42 UTC. This is a small observational sample, not a load test.

| Observation | Sample |
| --- | --- |
| CPU usage, 12 samples | 0.0051–0.0524 of one core; mean 0.0151 |
| Memory, 14 samples | 139.5–276.5 MB of approximately 2.15 GB |
| Auth cache hit, 8 log entries | median 0.08 ms |
| Auth refresh, 4 log entries | 2,859–8,155 ms |
| Automations full rerun, 9 entries | 68–14,506 ms; median 9,199 ms |
| Home full rerun, 1 entry | 11,366 ms |
| Edition Ops full rerun, 1 entry | 2,497 ms |

These are server log durations, **not browser time to interactivity**. Render
returned no HTTP latency series. The sample supports investigating repeated
I/O and request lifetimes before buying more capacity; it does not establish
capacity under peak load. Production after-change timing is unavailable because
deployment was expressly excluded.

### Reproducible local before/after

Chromium/Chrome on Windows, 1440×1000, production Analytics render functions,
fabricated records and 60 ms per storage read, external HTTP blocked. Both runs
use an already-started Streamlit server. “Cold” below means a new browser context,
not a cold server import. The pre-change Analytics source was captured from HEAD
before implementation. These are paired samples, not statistically reliable p95s.

| Measurement | Before | After |
| --- | ---: | ---: |
| Analytics initial reads, including operational totals | 8 | 5 |
| New browser context to complete fixture | 1,333 ms | 1,067 ms |
| Warm return to Analytics | 829 ms | 242 ms |
| Full app reruns on Analytics tab switch | 0 | 0 |
| Previously loaded breakdown reread within TTL | Preloaded already | 0 |
| Metrics DOM retained during tab interactions | Yes | Yes |
| Missing-metric/exception frames in after sample | — | 0 / 0 across 137 frames |
| Reporting archive filter full-app reruns | Full-page widget path | 0, browser verified |
| One account read, deterministic 20 ms SQL latency | 2 queries / 41.01 ms | 1 / 20.24 ms |
| List 20 accounts, same SQL latency | 21 queries / 426.35 ms | 1 / 20.24 ms |

With 4× CPU throttling, 150 ms network latency and 200 KB/s download:

| Measurement | Before | After |
| --- | ---: | ---: |
| Cold browser context | 30,611 ms | 30,832 ms |
| Warm Analytics return | 936 ms | 732 ms |
| Missing-metric/exception frames | 0 / 0 | 0 / 0 across 206 frames |

**Trade-offs and limits:** the throttled cold load is dominated by Streamlit's
initial frontend assets and did not improve. The first visit to a deferred
breakdown needs a server round trip, whereas all old tabs were preloaded.
Measured tab actions including the profiling round trip were 150 ms before and
233–366 ms after on the normal connection, and 270–311 vs 537–619 ms throttled.
That trades unused upfront work for on-demand data, with stable surrounding DOM.
No claim is made that all routes meet the requested 100–500 ms targets.

Existing email fixture regression (after only): warm editor 564 ms, return to
Campaigns 234 ms, warm tab switches 118–267 ms, no extra default-template reads,
no overlapping/giant-icon frames, and no typing long tasks recorded. Existing
Flow browser regression: initial 2,366 ms, reorder 464 ms, repeated reorder,
refresh, persistence, pause/resume and add-step passed. These are regression
checks, not before/after claims for the unchanged email engine.

## Route audit coverage

The registry has **48 destinations**, plus the existing Settings and Marketing
Factory aliases. An offline dispatch test covers all 50 and asserts that only
the selected renderer/redirect is invoked. This verifies route isolation, not
authenticated end-to-end rendering of every business page.

| Routes/components reviewed | Existing protections retained / outcome |
| --- | --- |
| Dashboard; Daily Planner; Weekly Review | Lightweight shell, click-only Planner, cached calendar, batched weekly bundle. Added scoped weekly display cache; native timer/refresh semantics retained. |
| Orders; Prodigi/Fulfilment | Existing asynchronous/bounded snapshot reads, lazy heavy imports and on-demand details retained. No order/fulfilment mutation changes. |
| Edition Ops | Existing continuous virtual table, fragment controls, cached product snapshot, lazy archive and override/sync guards retained. No numbering/allocation changes. |
| Mockups; Product Uploads; Design Studio | Existing fragment image consumers, prompt-only upload tooling, selected workspace and upload/hash state retained. No artwork/export-quality changes. |
| Social Media; Wall Preview Inbox; AI Reels | Selected-view dispatch, bounded history/gallery, thumbnail/token caches and deferred processing retained. Staff listing benefits from the account SQL fix. |
| Ads; Creative Refresh; Posting; Meta Review | Shared posting jobs/progress, selected creative reads, account-scoped Meta cache and fragments retained. No resource creation/activation. |
| Analytics Overview; Traffic & Acquisition; Pages & Engagement; Analytics Ecommerce; Analytics Realtime | Added bounded exact-report cache/store reuse; Overview breakdown fragment. Saved snapshot and attribution contracts unchanged. |
| SEO Overview; Keywords & Rankings; SEO Opportunities; SEO Landing Pages; Keyword Mapping; SEO Blog; SEO Health & Fixes | Existing selected-route dispatcher, bounded/cache-backed reports, lazy admin diagnostics and navigation epochs retained. No provider sync changes. |
| Email Inbox | Existing durable IMAP/read model and isolated inbox fragments retained; shell read lifetime fix avoids obsolete status loops. |
| CRM Campaigns; CRM Automations; CRM Settings; CRM Customers; CRM Segments; CRM Templates; CRM Reports | Existing lazy editors, bounded caches, shared templates, debounced previews and unified Flow fragments retained. SQL/browser regressions cover identity and publish safeguards. |
| Reviews | Existing selected view, read cache/fragments and pending-only refresh controller retained. |
| Image Protection | Admin-only form, two current settings reads and explicit installation verification retained. No new background storefront requests. |
| Reporting | Archive selection/filter fragment added; Today, staff, history, delivery health and explicit test action retained. |
| Accounts & Access | Eliminated permission N+1 reads; fresh permission/status/session-version behaviour verified in real local PostgreSQL. |
| Files | Existing scoped directory/token cache, on-demand opening and permissions retained. Shared shell avoids duplicate/outdated work. |
| Developer / Settings alias | Existing click-to-load diagnostics retained; no expensive diagnostics automatically activated. |
| Products; Product Assets; Webhook Events; Sync Runs; App Errors; Persistence Check | Existing placeholder, bounded diagnostic listings and explicit repair actions retained. |
| Global Search; sidebar; top bar; Windows WebView2 helper | Existing permission-scoped local search index, lazy route imports, stable DOM, epoch handling, native history and helper lifecycle retained. Shared request cancellation and timer teardown repaired. No worker/service-worker cache or desktop binary changes. |

No separate frontend build is configured for the Streamlit application. The
Shopify account-extension package is unrelated and was not rebuilt or changed.

## Verification

- 240 affected shell/Home/Reporting/Analytics/cache/navigation/desktop-helper
  unit and AppTest checks passed.
- 79 account/authentication regressions passed.
- 71 CRM Flow/native-automation/publication tests passed against disposable
  loopback SQL with mocked providers, including recipient/version safeguards.
- Real PostgreSQL temporary-table test passed: all revised account query forms,
  removed users, password exclusion, and immediate permission/session revision
  changes. Transaction rolled back; no production database contacted.
- All 48 registry routes + two aliases passed isolated dispatch verification.
- JavaScript tests passed: GET deduplication, retry after completion, identity
  changes, aborts, stale responses, no mutation deduplication, no timers after
  destruction, native history, Home/Files controls and recovery cancellation.
- Chromium tests passed: normal and throttled Analytics, archive-filter fragment,
  narrow viewport, repeated shell reruns with stable header/recovery identity,
  existing campaign editing/preview and Flow reorder/publish-state regressions.
- Python compilation, `pip check`, JavaScript syntax, `git diff --check` and
  `scripts/validate_render_topology.py` passed.
- Final review reran 33 focused checks, all four JavaScript suites and the
  Chromium shell check after restarting its local server with the final source.
- Broader existing suite: 377 tests, **337 passed, 33 skipped, seven failures**.
  The seven failures were reproduced using unchanged HEAD source snapshots:
  old Edition Ops renderer/CSV/editor/save expectations and two obsolete
  Mockups/Product Uploads source-text expectations in `test_orders_loading_ui`.
  They were not “fixed” by reverting the latest working interfaces. Skipped
  provider/database cases require their separate opt-in fixtures.
- Corrected one outdated XSS assertion in `test_dashboard_home`: it previously
  rejected any application-owned script; it now explicitly rejects execution of
  the two untrusted task payloads while allowing the existing trusted shell scripts.

## Files and operation

Runtime: `app.py`, `analytics_page.py`, `os_accounts.py`, `reporting_page.py`,
`top_bar.py`, `session_recovery.py`, `components/session_recovery.js`,
`components/sports_cave_top_bar/index.html`, `workspace_display_cache.py`.

Verification: `scripts/benchmark_account_reads.py`; new account-read, cache,
Analytics-fragment, route-isolation and shell-request tests; two offline browser
fixtures and their browser tests; updates to `test_dashboard_home.py` and
`test_session_recovery.cjs`. Generated local measurements live under the ignored
`.tmp-performance-results/` directory.

**Migrations / deployment:** none required. No worker, environment, Render
Blueprint, instance size or paid-service configuration changed. Use the normal
application release workflow when approved. A normal process restart refreshes
the cached script source. After a controlled release, compare the same production
PERF log paths and request counts; do not infer production gains solely from
synthetic latency tests.

**Remaining validation:** authenticated cold/warm profiling for every production
route, peak-user load, long-duration WebView2 testing and provider slow/failure
conditions across every workflow were not exercised live. External provider
latency and cold Streamlit asset transfer remain limitations. No real customer
send, allocation, fulfilment, Meta post or Shopify write was used to test speed.

## Reproduction

Use the repository virtual environment and existing Playwright installation.
No new dependency is needed. Run from the repository root:

```powershell
# Capture pre-change source before editing (or git show <baseline>:analytics_page.py).
New-Item -ItemType Directory -Force .tmp-performance-baseline, .tmp-performance-results
git show HEAD:analytics_page.py | Set-Content .tmp-performance-baseline/analytics_page.py
.venv/Scripts/python.exe -m streamlit run tests/fixtures/application_performance.py --server.port 8551 --server.address 127.0.0.1 --server.headless true
# In another terminal; NODE_PATH may point to the existing bundled Playwright packages.
$env:PERF_BASELINE='1'
node tests/test_application_performance_ui.cjs
Remove-Item Env:PERF_BASELINE
node tests/test_application_performance_ui.cjs
# Repeat the pair with PERF_SLOW=1 for CPU/network throttling.
.venv/Scripts/python.exe scripts/benchmark_account_reads.py .tmp-performance-results/account-after.json
node tests/test_top_bar_requests.cjs
node tests/test_session_recovery.cjs
.venv/Scripts/python.exe -m unittest tests.test_workspace_display_cache tests.test_account_read_queries tests.test_analytics_fragment_reads tests.test_workspace_route_isolation
```

The SQL benchmark's 20 ms latency is deliberately simulated and labelled;
the browser fixture's 60 ms delay is test data latency only. Production code
contains no such sleeps. For the opt-in PostgreSQL test, set
`LOCAL_ACCOUNT_TEST_DSN` to an isolated loopback database and run
`tests.test_account_reads_postgres`. The test refuses non-loopback hosts and
uses temporary tables/rollback.
