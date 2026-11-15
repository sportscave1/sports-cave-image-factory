# Application Performance Phase 3 — Final

Date: 2026-10-08. Local implementation only. No push, deployment, production restart, configuration change, database mutation, Shopify write or customer send.

## Executive summary

Two small production changes address observed blocking I/O without changing business logic:

1. Orders' existing 30-second visibility check uses Streamlit's supported parallel fragment. The page no longer waits for this independent read to finish. Late results are discarded following navigation, account changes or certificate actions.
2. The current-account refresh uses an autocommit connection for its single authoritative SELECT, avoiding an explicit BEGIN/COMMIT around that statement. User and permissions remain one database snapshot. Schema setup and all mutations retain transactional connections. Authentication validation intervals are unchanged.

No pooling, new caches, dependencies, services, polling or migrations were introduced. Existing Phase 1/2 optimizations and the prior local email/sidebar work remain intact.

The final repeated local Orders comparison improved rendering completion from median **1,868ms to 127ms**, with a **simulated** 1,280ms marker read. This is not a production latency claim. A separate 20ms round-trip model improved account reads from 81.16ms to 40.58ms; production savings await rollout measurement.

## Production evidence and limits

Read-only Render metrics and existing PERF logs were inspected in the previously approved Nathan's workspace, for canonical `sports-cave-os` (`srv-d8kl4on7f7vs73dvavv0`). Approximate sample: 10:35–11:35 UTC. No service settings were changed.

Ranked opportunities:

| Rank | Observed operation | Production sample | Interpretation / decision |
|---|---|---|---|
| 1 | Orders initial snapshot | 3,689ms asynchronous total; 3,093ms batch | Already asynchronous. Preserve bounded latest-order loading; do not rewrite allocation/query logic for this pass. |
| 2 | Home weekly work | 1,946–1,951ms, one source query | Already isolated in parallel fragment and account-scoped cache. No demonstrated redundant query to remove. |
| 3 | Authentication refresh | 1,287–1,302ms cache misses; 0.05–1.15ms hits | Remove two protocol commands for the one-query read; retain fresh security validation. |
| 4 | Orders visibility check | 1,283ms, followed by page total 1,327ms | Independent marker I/O was on the page completion path. Isolate it without changing cadence or data validity. |
| 5 | Warm navigation / CRM first loading | Local warm Home ~834ms; production CRM reruns 1,485ms then 73ms | Route dispatch itself <0.2ms. Do not equate different data/cache states or renderer dispatch with completed content. Preserve existing lazy reads. |

Design Studio had a single 1,902ms sample; Mockups one 90ms sample. These are insufficient for a safe page rewrite. Orders badge reads were 1,474–1,623ms; existing independent notification handling was retained.

CPU: 12 sampled points, approximately 0.0036–0.0519 cores. Memory across instance labels: 148–405MB; the current instance rose from about 199MB to 264MB, then remained near 264MB for the final 30 minutes. This sample does not demonstrate CPU saturation or a leak. Render returned no HTTP latency series for the request.

### Timing decomposition

Production Orders logs separated ID/base/fulfilment/allocation/manual queries at approximately 283/974/143/294/319ms, plus conversion 8ms, table preparation 2ms and rendering 36ms. These are application timings, not PostgreSQL EXPLAIN execution times.

Existing logs did not separate connection/TLS establishment from SQL/network round trips. New sanitized `PERF Accounts connect_ms` and `current_user_query_ms` logs address that gap. Connection timing includes DNS/TCP/TLS/authentication together; query timing includes request/result transfer and decoding. Neither is pure server execution time. No IDs, credentials, SQL arguments or customer payloads are logged.

No production after-change measurements exist, because deployment was prohibited. Database pooling is not justified by the available decomposition and was not added.

## Root causes and implementation

### Orders

The marker fragment was synchronous during a full run. Its 30-second live-change read executes after table rendering but still delayed completion of the page script. It now uses `parallel=True`, already supported and used elsewhere in the installed Streamlit application.

Marker semantics remain unchanged: first observation records the marker; equal/empty results do nothing; failures preserve state; confirmed changes invalidate the snapshot and request the normal refresh. Certificate operations are checked both before and after I/O. Account and route are checked again after I/O. No additional executor, timer or retained future was introduced.

### Accounts

`get_user()` already retrieved the account and page permissions with a single SQL statement. The default psycopg connection nevertheless wrapped that read in a transaction. Only this statement uses `autocommit=True`; all other callers default to `False`. There is no stale authorization cache, TTL extension, permission bypass or mutation-path change.

The statement retains the same snapshot semantics and timeout settings. See the [psycopg transaction documentation](https://www.psycopg.org/psycopg3/docs/basic/transactions.html#autocommit-transactions). Supabase's changelog endpoint was unavailable to the documentation tool; no Supabase API/schema feature was changed.

### Navigation, CRM and memory review

All 48 registered routes plus aliases still dispatch only their selected renderer. Existing account-scoped display caches, Planner invalidation, Home parallel fragments, lazy Analytics tabs, compressed assets and one-render Flow definition memo remain unchanged. Warm Home still reuses its weekly read (one read across return navigation), and Analytics loads four visited reports rather than refetching cached tabs.

No evidence justified another CRM rendering/state layer. Existing Flow tests cover immutable published sequences, draft revision safety, independent step identity and metrics, reordering and persistence. The remaining ~0.83s warm Home time was not isolated to a safe application-level change; this pass does not claim to have eliminated framework/browser rerun latency.

No new cache or connection pool retains account data. Connections close after success and failure. No production memory leak was established. Short repeated-navigation checks are not a multi-hour memory soak.

## Benchmarks

Windows, Chrome headless, production Streamlit renderers with synthetic loopback data. Browser traffic outside localhost blocked. Before/after use identical fixtures. The portable Orders baseline reproduces the former synchronous fragment; the first comparison also used the saved pre-change source.

| Measurement | Before | After | Scope |
|---|---|---|---|
| Orders rendering completion, final 3 runs | 1,871 / 1,855 / 1,868ms | 127 / 112 / 226ms | Same 1,280ms simulated marker I/O; median reduction 93.2% |
| Orders first 3-run comparison | 1,885 / 1,850 / 1,883ms | 115 / 124 / 115ms | Independent repeat confirms direction; not actual DB speedup |
| Account refresh latency model, 7 runs | Median 81.16ms; range 80.84–81.38 | Median 40.58ms; range 40.46–41.10 | 20ms simulated connection + 20ms per protocol command; not measured production |
| Warm Home, 2 runs | 833 / 834ms | 831 / 824ms | Effectively unchanged; target 100–500ms not met |
| Normal cold browser Home, 2 runs | 1,523 / 998ms | 1,532 / 1,516ms | Variable first-load/import/host contention; insufficient evidence of gain or material code regression in unchanged Home renderer |
| Cached Analytics tabs | 35–39ms | 29–39ms | Unchanged behavior |
| Asset transfer | 1,254,721 bytes | 1,254,721 bytes | Phase 2 gzip saving preserved |
| Throttled cold Home | Phase 2 reference 11.14s | 11.339s | 4x CPU, 150ms latency, 200KB/s; historical reference, not paired Phase 3 baseline |
| Throttled warm Home | Not paired | 959ms | Current verification only |
| Flow initial/reorder | Not paired | 2,346 / 440ms | Existing synthetic Flow browser fixture; no Phase 3 speed claim |

Orders timing ends at the completion marker after the production fragment invocation, not merely fragment dispatch. It measures removal of marker I/O from the main page completion path, not freshness completion. Marker I/O still takes its configured fixture duration.

Normal browser samples recorded about 24–38MB JS heap, 371–372 layouts and 1.03–1.17 seconds cumulative task duration across the scenario. GC and run variability prevent interpreting that as a memory improvement. Throttled task duration was 4.80s with ~33MB heap.

Artifacts are in local ignored `.tmp-phase3-results/`, including Orders/browser/model JSON, regression outputs and baseline failure reproduction. They contain synthetic data only.

## Regression verification

- Broad run: **616 tests; 502 passed, 104 skipped, 10 failed**. The ten failures were reproduced using saved pre-Phase-3 modules: **10 identical failures, zero import/test errors**. No assertions were weakened.
- Disposable SQL follow-up: **101 passed**, enabling CRM and Edition integration tests that otherwise skip without their local fixture. Mock providers only.
- Final focused safety/health/Orders/Edition run: **85 passed**.
- Real isolated PostgreSQL: **5 passed**. Covers actual statement transaction status and connection closure, account permission/session revision changes, removed users, schema setup and rollback/retry, automation read timeouts. Temporary tables/unique schemas only. Native protocol tracing is Linux-only in this psycopg build, so the test uses the supported transaction-status API instead.
- New Phase 3 tests pass: one authoritative account query, transactional defaults/timeouts, failure propagation/closure, unchanged marker cadence, no-op/changed/failure markers, navigation/account/certificate races.
- Chrome Orders before/after repeated navigation: passed; late checks did not reopen Orders; no Streamlit/JS errors; 390px no horizontal document overflow.
- Home/Analytics normal and throttled browser scenarios: passed; read counts, refresh completion, return navigation and rapid departure remain correct.
- Existing Flow browser regression: passed with intended preview fixture, including repeated live-flow draft reorder, metrics refresh, reload persistence, pause/resume, simulation and Add Email. No real sends. Running it against the extra profiling wrapper initially encountered covered click targets; no production change was made for that fixture mismatch, and the browser test remains unchanged.
- Shell browser: eight full reruns retained the same header and recovery observer; desktop/narrow checks passed. Home component and top-bar native history/navigation contract tests passed.
- Python compilation, dependency consistency (`pip check`), JavaScript syntax and canonical Render topology validation passed. Streamlit has no separate frontend build command; actual ASGI fixtures and health/middleware tests cover startup/rendering.

### Unchanged failures needing separate triage

1. Planner toolbar countdown mirror source expectation.
2. Planner authoritative-sheet/stale-date source expectation.
3. `PreviewStabilityTests.test_automation_only_polling_and_debounce` — the same Phase 2 documented source assertion.
4–8. Five legacy Edition Ops UI source expectations: CSV action, old source/help copy, save path, editor source and editor key.
9. Mockups prompt-card source expectation.
10. Product Uploads embedded-prompt copy expectation.

These files/behaviors were not changed by Phase 3. They remain visible test failures, not a clean whole-repository pass. All 48-route dispatch assertions and focused security/transaction tests passed. No exhaustive live business-workflow verification is claimed.

## Desktop/mobile status

Chrome desktop and narrow/mobile-sized layouts passed the listed fixtures. Existing desktop-helper and native-history contracts passed. Native Windows WebView2 runtime performance, mobile hardware/Safari and multi-hour sessions remain **unverified**; Chromium results are not a substitute.

## Files changed by Phase 3

Production:
- `orders_page.py` — parallel marker read and stale-result guards.
- `os_accounts.py` — single-query autocommit and sanitized timing logs.

Tests/benchmarks/report:
- `tests/test_account_reads_postgres.py` — fixture connection accepts explicit connection options.
- `tests/test_account_schema_pipeline.py` — real connection-option and transaction/closure coverage.
- `tests/test_phase3_read_safety.py` — focused safety regressions.
- `tests/fixtures/performance_phase3.py` — isolated before/after Orders renderer.
- `tests/fixtures/performance_phase3_server.py` — release-style ASGI fixture.
- `tests/test_phase3_browser.cjs` — repeated navigation, errors and responsive comparison.
- `scripts/benchmark_phase3.py` — repeatable, explicitly simulated account RTT model.
- `docs/APPLICATION_PERFORMANCE_PHASE_3_FINAL.md` — this report.

Other pre-existing local email, notification and Shopify artifacts were preserved and are not counted as Phase 3 work.

## Reproduction

```powershell
.venv/Scripts/python.exe scripts/benchmark_phase3.py
.venv/Scripts/python.exe -m unittest tests.test_phase3_read_safety tests.test_account_read_queries tests.test_phase2_read_safety
.venv/Scripts/python.exe -m uvicorn tests.fixtures.performance_phase3_server:app --host 127.0.0.1 --port 8556
# Separate terminal; Playwright must be available in NODE_PATH:
node tests/test_phase3_browser.cjs
# Optional real PostgreSQL tests: LOCAL_ACCOUNT_TEST_DSN must point to an isolated loopback DB.
.venv/Scripts/python.exe -m unittest tests.test_account_schema_pipeline tests.test_account_reads_postgres
```

## Rollout and final recommendation

No migration, environment change, Render plan change or worker configuration is required. The minimal patch is ready for controlled staging/deployment review, with the known baseline test failures explicitly recorded; it is not an assertion that the entire repository is green.

After a separately authorized release, verify: normal/disabled/revoked accounts; permission refresh at the existing interval; Orders initial/live changes; certificate work during a delayed marker; leaving Orders mid-read. Compare `connect_ms`, `current_user_query_ms`, auth misses and completed page/browser timings under equivalent data and network conditions. Keep the canonical primary service identity. Do not infer an SQL speedup from fragment dispatch time. Roll back the two production changes if authentication or marker behavior regresses; no data rollback is needed.

**End broad performance optimization here and return focus to application features.** Keep routine measurement and address a future concrete regression if observed. The remaining latency is chiefly remote I/O and framework/browser lifecycle work, with insufficient evidence to justify pooling, a navigation rewrite or more infrastructure. Orders completion is measurably faster in the isolated comparison; account protocol work is reduced; Home/Analytics, business rules and operational safety remain unchanged.
