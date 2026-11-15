# Application performance — Phase 2

Implemented locally on 8 October 2026. Read together with
[the Phase 1 audit](APPLICATION_PERFORMANCE_AUDIT.md). No deployment, push,
production database changes, customer sends, Shopify writes or Render changes
were performed. No dependency, paid service or migration was added.

## Findings and current production baseline

Read-only logs/metrics were inspected in the authorised **Nathan's workspace**,
for the canonical `sports-cave-os` service (`srv-d8kl4on7f7vs73dvavv0`). These are
server observations, not browser interactivity measurements, and were collected
before deploying any Phase 2 code:

| Observation on 8 October (UTC) | Current evidence |
| --- | --- |
| Authentication refresh, ten sampled log entries | 2,557–8,076 ms |
| Home, 08:42 | Auth 3,023 ms; weekly data/render 2,005 ms; Home 2,028 ms; full rerun 5,093 ms |
| Home, fresh instance at 08:45 | Imports 181 ms; auth 8,076 ms; events 2,440 ms; weekly 1,900 ms; Home 4,344 ms; full rerun 12,504 ms |
| Automations, sampled 08:10 entry | Auth 2,862 ms; full rerun 12,186 ms |
| Recent resource samples | CPU 0.005–0.074 cores; memory approximately 176–248 MB |

There is no comparable production **after** measurement: this implementation
remains local. HTTP latency time series were unavailable in the metrics response.
The sample does not establish sustained CPU/memory pressure or justify changing
the Render plan. External database latency remains material.

### Root causes traced

1. **Authentication:** refreshing an already signed-in user called account
   bootstrap discovery (`first_admin`) before reading the actual user and their
   permissions. Both opened database connections. Restoring a valid signed
   account cookie also performed the unrelated administrator lookup. On a fresh
   process, account schema setup additionally sent 28 ordered SQL statements in
   separate network exchanges. Phase 1's single-statement permission reads were
   already present and have been retained.
2. **Home:** event-table initialisation (including cold dataframe imports) and
   the independent weekly-work query/render ran serially. Weekly snapshots were
   already bounded, account-scoped and invalidated by Planner updates. Replacing
   that cache would not address the remaining serial work.
3. **Automations:** the overview already uses bounded identity projections and
   separate background summary reads. Its critical identity read nevertheless
   required separate exchanges for two transaction-local timeout statements
   and the SELECT. The Flow header, sequence and settings also reread the same
   flow definition during one render. Lazy composer imports, preview caches,
   queue limits and navigation cancellation were already working.
4. **Cold browser loading:** the installed Streamlit 1.58 ASGI middleware
   deliberately bypasses compression for `/static/`. Verified locally: the main
   JavaScript file alone transferred **2,364,515 uncompressed bytes**. The tested
   Home screen loads about 4.93 MB of JS/CSS before becoming usable. This is
   separate from Python imports, authentication and database execution.
5. **Analytics:** lazy tabs correctly avoided unselected queries, but discarded
   previously visited tab output. Returning to a cached tab still waited for a
   fragment round trip even when the report remained in the display cache.
6. **Navigation/shell:** existing route imports, account-scoped snapshots,
   request deduplication, stale-response guards and teardown were retained.
   The route registry, aliases, top bar, sidebar and recovery protocol needed
   no further rewrite. A local cold `crm_page` import took about 0.839 s,
   largely Streamlit imports; the observed production restart logged 0.181 s of
   app imports. Imports do not explain the multi-second authentication path.

## Changes implemented

- **Authentication:** use the current account's authoritative `get_user` read
  directly. Keep the existing 30-second validation interval, cookie validation,
  session revision checks, permissions and disabled/removed-account handling.
  Failed authoritative verification clears the session; it never falls back to
  stale permissions. Bootstrap/legacy login still performs account discovery.
- **Account startup:** batch the existing 28 SQL statements using psycopg's
  supported pipeline mode inside the same transaction. Confirm all results
  before committing or setting `_schema_ready`. Failure rolls back and remains
  retryable. No SQL/schema meaning changed.
- **Home:** two independent areas use public `st.fragment(parallel=True)`.
  Each owns its complete layout; no cross-fragment container writes. The
  existing weekly display cache, account ownership and Planner invalidation
  remain intact. This overlaps independent cold work without adding an executor
  or polling loop. Home logs now distinguish `shell_dispatch` from each
  fragment's completion; dispatch time must not be reported as full-page TTI.
- **Automations overview:** pipeline timeout setup and the identity SELECT on
  supporting connections. Preserve transaction boundaries and the 1,500 ms
  statement / 500 ms lock timeouts. Lightweight local test adapters retain the
  sequential fallback.
- **Flow/editor:** a context-local, one-flow memo shares the loaded definition
  only within one editor render. Returned values are independent copies. Every
  database operation clears it **before** execution. Context cleanup also runs
  on exceptions; later fragment reruns and background threads read independently.
  It is neither a cross-request cache nor an authority for mutations. Existing
  locked validation, optimistic revisions and immutable publications remain.
- **Public assets:** a narrow ASGI wrapper reuses Starlette's existing gzip
  middleware, level 4, for public JS/CSS GETs of at least 1 KB. It streams large
  bundles without retaining an application asset cache. It preserves cache
  policy, adds `Vary: Accept-Encoding`, weakens compressed ETags appropriately,
  and respects identity/q=0, pre-encoded bodies, ranges and conditional responses.
  Private routes, root HTML, media, uploads, WebSockets and SSE are untouched.
  No Streamlit internals, browser storage or injected JavaScript were patched.
- **Analytics:** render already-visited, unexpired reports in their inactive tab
  using the existing account/property/date-scoped bounded cache. The browser can
  reveal these immediately while the normal fragment revalidates. Unvisited
  tabs still make **zero** queries. No background prefetch, new TTL or new cache.

The concurrency/batching APIs are documented public interfaces:
[Streamlit fragments](https://docs.streamlit.io/develop/api-reference/execution-flow/st.fragment),
[psycopg pipeline mode](https://www.psycopg.org/psycopg3/docs/advanced/pipeline.html).
Installed versions tested: Python 3.14, Streamlit 1.58.0, psycopg 3.3.4,
PostgreSQL 17.6 and Windows Chromium. The existing dependency constraints already
include these capabilities.

## Before/after measurements

### Real browser, isolated data

Same Windows machine, 1440×1000 Chromium, loopback ASGI, real Home/Analytics
renderers, fabricated records, all external browser traffic blocked. Each cold
sample uses a fresh browser context; the Python server is otherwise warm.
The fixture adds the same explicit 300 ms weekly read and 60 ms report read in
both versions. These are **test-only** waits, not production delays.

Normal results below are medians of three successful runs. The throttled pair
uses 4× CPU, 150 ms configured latency, 200,000 B/s down, 100,000 B/s up.
CDP throttling does not model every WebSocket/production network characteristic.

| Browser measurement | Before | After | Interpretation |
| --- | ---: | ---: | --- |
| Cold Home, normal connection | 1,021 ms | 1,065 ms | No demonstrated gain; 44 ms slower median, overlapping run ranges |
| Cold Home, throttled | 30,253 ms | 11,140 ms | 63% shorter in the paired run |
| JS/CSS transferred through initial content | 4,931,737 B | 1,254,721 B | 74.6% less transfer; same assets |
| Warm return to Home | 850 ms | 834 ms | Largely unchanged; 100–500 ms target not met |
| First visit to Analytics breakdown | 242 ms | 230 ms | Remains lazy; little change |
| Previously visited Analytics breakdown | 130 ms | 39 ms | Immediate cached tab reveal |
| Previously visited tab, throttled pair | 273–292 ms | 57–67 ms | Less dependence on fragment round trip |
| Browser heap after scenario, median | 29.07 MB | 27.35 MB | No increase in this short scenario; not a leak/soak proof |
| Full app runs through initial tab scenario | 5 | 5 | Tab switching stays in its fragment |
| Weekly DB loader calls: initial / warm return / explicit refresh | 1 / 1 / 2 | 1 / 1 / 2 | Cache and invalidation preserved |
| Report reads after visiting all four tabs and revisiting two | 4 | 4 | No extra API/database loading |

Normal cold ranges: before 1,010–1,527 ms; after 1,025–1,077 ms. The first server
run includes additional import work. No claim is made that compression improves
unthrottled loopback latency. It costs CPU to reduce transfer; that trade-off
should be monitored after a controlled production release.

Flow browser verification on disposable SQL: initial local Flow content was
2,354 ms and one reorder 516 ms. Repeated reorders, metrics refresh, persistence,
simulation, pause/resume and adding a step passed. This is an **after-only**
functional measurement, not a claimed production or before/after improvement.

### Server execution with explicitly simulated SQL latency

`scripts/benchmark_phase2.py` executes the old/new functions with a fixed **20 ms
simulated SQL round trip**. It proves removed work and batching, not production
wall-clock gains. Connection/TLS establishment and database execution time are
not represented by this model.

| Path | Before | After | Work count |
| --- | ---: | ---: | --- |
| Due account refresh | 40.75 ms | 20.72 ms | Two account queries → one; current-user read retained |
| Cold account schema setup | 589.06 ms | 40.85 ms | Same 28 statements; 29 exchanges including commit → 2 |
| Cold automation identity query | 60.90 ms | 20.16 ms | Same three ordered statements; 3 exchanges → 1 |
| Four Flow definition consumers in one render | 83.52 ms | 21.49 ms | 4 definition reads → 1 |

A Flow render that performs other database work deliberately invalidates the
memo and may need additional fresh reads. Existing legacy-publication lookups
are an example. Real production Home/Automations completion timings must still
be measured after release; the UI targets are not all met by these local changes.

## Verification

- **314 tests passed:** account/authentication, Home, cached reads, Analytics
  fragments, navigation, all 48 destinations and aliases, desktop-helper
  contracts, reporting permissions, Edition Ops catalogue/stability/table
  editing, and main/webhook health checks.
- **69 tests passed:** CRM publication, navigation, overview loading/reactivity,
  Flow builder/page/compact controls and new read-safety/compression tests.
- Broader **102-test CRM suite:** 101 passed, one existing source-text assertion
  failed: `PreviewStabilityTests.test_automation_only_polling_and_debounce`
  expects `not any(s['type']==BLOCK` in `crm_section_ui.py`. The same failure was
  reproduced with **unchanged HEAD** contents for every file read by that test.
  No assertion was weakened and no unrelated editor behavior was reverted.
- **Four real PostgreSQL checks passed:** initial/repeated account setup,
  pipeline failure/atomic rollback/retry, authoritative permission/session
  revision reads, and automation SELECT results with unchanged local timeouts.
  Unique disposable schemas/temporary tables only; no production DB contacted.
- Chromium normal/throttled, repeated navigation, refresh completion and rapid
  departure from Home passed with no application exceptions or page JS errors.
  The 650 px fixture had no horizontal document overflow. Test timing was changed
  from a fixed wait to the actual refreshed metric to avoid a race in the test.
- Existing Flow fragment browser regression passed: initial metrics, repeated
  live-flow **draft** reorder, refresh, reload, pause/resume, simulation and Add
  Email. All data synthetic and all external provider calls blocked.
- Shell JS checks passed: GET deduplication, identity isolation, abort/retry,
  stale-response rejection, mutation exclusions, timer teardown, session
  recovery, native history and unsupported-API fallbacks.
- Final review reran **49 focused safety tests**, all passing, after bounding
  the Flow memo and adding the identity-query pipeline. The final browser
  scenario passed after waiting for Streamlit's native narrow-screen sidebar
  transition instead of capturing its intermediate animation frame.
- Real ASGI HTTP checks passed: gzip decodes to the exact original bundle,
  conditional GET returns 304, byte ranges return uncompressed 206, and explicit
  gzip refusal returns identity. The main bundle was 574,686 B compressed versus
  2,364,515 B original.
- Python compilation, JavaScript syntax, dependency consistency, diff whitespace
  and Render topology validation passed. Streamlit has no separate frontend
  production-build command; its production ASGI entry point is covered by
  health/middleware tests and the release-style local browser fixture.

The desktop checks cover existing Windows WebView2 host/protocol contracts and
Chromium behavior. They are **not** an authenticated end-to-end run of the native
WebView2 application. Long-session, concurrent-user and production-provider
profiling remain outstanding. Existing Streamlit deprecation warnings remain;
they were not introduced or hidden by this work.

## Files modified

Runtime:

- `app.py` — account refresh/cookie restoration, independent Home fragments and
  accurate component/dispatch timing labels.
- `os_accounts.py` — transactional schema pipeline.
- `crm_automation_home_read.py` — bounded identity-query pipeline.
- `crm_automation_store.py` — one-render definition reuse and invalidation.
- `crm_automation_ui.py` — enter the display scope for the selected editor.
- `analytics_page.py` — reuse visited report output without eager queries.
- `static_asset_compression.py` — public JS/CSS ASGI compression.
- `sports_cave_server.py` — attach the wrapper inside existing health/lifecycle
  middleware; routes and primary service identity unchanged.

Verification/reporting:

- `scripts/benchmark_phase2.py`
- `tests/fixtures/performance_phase2.py`
- `tests/fixtures/performance_phase2_server.py`
- `tests/test_phase2_browser.cjs`
- `tests/test_phase2_read_safety.py`
- `tests/test_static_asset_compression.py`
- `tests/test_account_schema_pipeline.py`
- `docs/APPLICATION_PERFORMANCE_PHASE_2.md`

Local raw measurements/logs/screenshots are in ignored `.tmp-phase2-results/`.
Before-source snapshots are in ignored `.tmp-phase2-baseline/`. They contain no
production customer records. The report records the durable results.

## Reproduction and rollout

Before modifying source, snapshot these files into `.tmp-phase2-baseline/`:
`app.py`, `analytics_page.py`, `os_accounts.py`, `crm_automation_store.py`,
`crm_automation_home_read.py`. For a later reproduction, recover the pre-Phase-2
revision of those files without replacing the working checkout.

```powershell
# Existing repository venv and Playwright installation; no new packages.
$env:PHASE2_BASELINE='1'
.venv/Scripts/python.exe scripts/benchmark_phase2.py .tmp-phase2-results/server-before.json
Remove-Item Env:PHASE2_BASELINE
.venv/Scripts/python.exe scripts/benchmark_phase2.py .tmp-phase2-results/server-after.json

# Run the fixture in its own terminal. Set PHASE2_BASELINE=1 in BOTH terminals
# for the before run; restart the fixture without it for the after run.
.venv/Scripts/python.exe -m uvicorn tests.fixtures.performance_phase2_server:app --host 127.0.0.1 --port 8555
node tests/test_phase2_browser.cjs
# Repeat with PERF_SLOW=1 for the throttled pair.

.venv/Scripts/python.exe -m unittest tests.test_phase2_read_safety tests.test_static_asset_compression tests.test_crm_automation_loading
# Set LOCAL_ACCOUNT_TEST_DSN to disposable localhost PostgreSQL only:
.venv/Scripts/python.exe -m unittest tests.test_account_schema_pipeline tests.test_account_reads_postgres
```

**Rollout:** no new migration, worker setting, Render configuration, instance
upgrade or desktop installer change. Use the normal web-application release and
process restart when authorised. Compression is integrated with the existing
ASGI production entry point; launching plain Streamlit directly does not install
the Sports Cave middleware.

**Production verification:** compare the same authenticated Home/Automations
paths, auth misses, individual fragment completion and browser content-ready
measurements. Check public asset `Content-Encoding`, `Vary` and conditional
requests through Render's edge, plus cold-load CPU/memory under concurrent users.
Verify account revocation, Planner refresh and browser/native session recovery.
Do not interpret the smaller Home dispatch log as completed rendering.

**Next optimisation:** measure database connection/TLS time separately from SQL
on real account and automation reads, then assess reuse of the existing
connection infrastructure. A new connection pool or longer auth TTL was not
introduced without those measurements. First-time Analytics tabs still require
a server round trip, and Streamlit's rerun/navigation overhead remains visible
on warm Home navigation. Native WebView2 and sustained production verification
are required before making broader latency or memory claims.
