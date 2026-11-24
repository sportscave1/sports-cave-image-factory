# App startup performance — Phase 2 data layer

24 November 2026, Australia/Sydney. Implemented and tested locally, continuing
Studio task `20261124-564ab6e2` in its existing owned worktree. All Phase 1 work
is retained. Changes remain uncommitted; nothing was pushed, merged or deployed.
No production database, customer data, application preview or business provider
was accessed.

## Implemented changes

### Home weekly summary

`load_home_weekly_work_bundle` previously opened a fresh database connection
and sent the transaction-local timeout and weekly SELECT separately.

It now uses the existing bounded read pool and its exclusive lease, watchdog,
stale-connection recovery and diagnostics. Inside the original transaction
boundary, the timeout and SELECT are pipelined. The pipeline finishes before
fetching the result, avoiding an extra fetch synchronization. The existing
dashboard timeout (2,500 ms by default) is transaction-local and restored before
the connection returns to the pool.

The SQL, selected columns, account/team scope, schema-readiness check, result
shape and current-statement snapshot remain unchanged. No permissions or result
data are cached. There is no new pool instance/configuration lane, increased
connection limit, dependency or schema change in the application.

### Orders certificate enrichment

The allocation query used a text COALESCE expression across the preferred UUID
certificate link and its legacy link. That expression prevented the test
planner from using the existing individual link indexes.

The revised predicate separates the two alternatives:

1. Match the preferred UUID link using its existing index.
2. Consult the legacy link only when the preferred link is NULL.

A guarded, canonical-lowercase UUID conversion preserves the former exact text
semantics and accepts older numeric/text edition IDs without an invalid cast.
Certificate readiness/date ordering and LIMIT 1 are unchanged. A conflicting
preferred link cannot accidentally fall back to the legacy link.

No indexes or migrations were added. The already-bounded latest-order window,
deduplicated raw-order transfer, pipelined enrichment reads, quantity handling,
manual editions, refunds and certificate actions are retained.

## Evidence

The benchmark executes the actual before/after Home functions and extracts the
actual Orders allocation SQL through the existing SQL-aware fixture. It creates
a new in-memory PostgreSQL/WASM engine on loopback with fabricated data:
2,000 edition rows, 25,000 certificates, and a 50-order/100-line selection.
Home records include active/removed accounts, sheets, timers and human work.

Before/after order alternates across seven paired samples. The baseline is the
local pre-Phase-2 source snapshot; source and harness hashes are recorded and
checked for changes during each run.

| Measurement | Before median | After median | Scope |
| --- | ---: | ---: | --- |
| Orders allocation/certificate SQL | 399.774 ms | 4.593 ms | Actual SQL, synthetic local database; not full Orders page |
| Home weekly bundle, loopback | 7.036 ms | 2.653 ms | Includes client/connection orchestration |
| Home weekly bundle, imposed 20 ms frontend transport delay | 107.136 ms | 64.146 ms | Explicit latency model; not measured WAN/TLS latency |

Home's first loopback calls were 7.036 ms before and 16.000 ms after, including
first pool setup. Across repeated exploratory runs the old loopback median
ranged from approximately 3 to 17 ms. Do not treat its final seven-sample median
as a reliable production speedup or claim that cold application opening is
already faster. The delayed-transport comparison demonstrates the value of
connection reuse and fewer serialized waits under an explicit latency model.

The Orders query plan is the stronger finding: the old plan scanned the
certificate table 100 times, removing 24,999 rows on each loop. The candidate
uses bitmap scans of the existing preferred-link and legacy-link indexes.
The recorded EXPLAIN execution times are 394.106 ms before and 5.388 ms after.
EXPLAIN and client elapsed times measure different boundaries.

All 100 allocation query results, complete Home bundles and final rendered-data
summary dictionaries matched. The latency-model results also matched. There
is no claim of an equivalent percentage improvement to the entire app.

Summary, raw sample durations, selected plans, versions and source hashes:
[APP_STARTUP_PHASE_2_EVIDENCE.json](APP_STARTUP_PHASE_2_EVIDENCE.json).
Full EXPLAIN plans and protocol counters:
`.tmp-startup-phase2/sql-baseline.json` (local ignored evidence).

## Verification

- 114 tests passed, with 39 passing subtests, in the final focused run.
- All 13 new SQL cases ran against the disposable database; none were skipped.
  They cover worker/team/removed-account scope, no cached disabled-account
  results, bundle parity, exclusive connection reuse, transaction/timeout
  restoration, query failure and recovery, stale-transport retry, legacy text/
  numeric/uppercase IDs, conflicting links and certificate asset preference.
- Existing bounded Orders and multi-unit/manual-edition fixtures pass.
- Existing pool exclusivity, bounded pressure, cancellation and fresh-account
  validation checks pass. These use controlled concurrent connection doubles;
  PGlite's single-session multiplexer is not evidence of native PostgreSQL
  multi-user isolation or production capacity.
- Phase 1 timing/compression contracts, Home/cache/Planner/human-work regressions,
  shell request-lifetime and Home navigation JavaScript checks pass.
- Node syntax, Render topology and diff checks pass.

One existing test failed in the wider run:
`DailyPlannerOverhaulContractTests.test_toolbar_countdown_mirror_is_client_side_and_cross_window`.
It expects one `setInterval(() =>` occurrence; the unchanged toolbar source has
two. The test, toolbar, Planner source, top_bar.py and top_bar_api.py were checked
against HEAD and are identical. The failure is therefore recorded separately,
and the final focused command deselects that one known failing test. No existing
test or toolbar implementation was altered. This is not a whole-repository
green-test claim.

## Isolation and limits

The SQL engine and socket adapter are pinned test-only dependencies installed
under this task's ignored scratch directory. The engine stores no database
files. Its child has an allowlisted environment and listens only on loopback;
the benchmark rejects external socket connections. No production application
server, worker, schema initializer or provider mutation is launched.

PGlite 0.6.0 reports PostgreSQL 19/WASM, which is not necessarily the production
PostgreSQL version. The plan benefit depends on the actual production indexes,
data distribution and planner. Production index state, region alignment,
connection/TLS costs, concurrent load and end-to-end Home/Orders timings remain
unverified. No regional, hosting or capacity change was made.

The frontend first-download problem identified in Phase 1 is outside this
data-layer change. Phase 3 should profile the current Home/Orders loading and
refresh paths; Phase 4 retains the frontend/startup work.

## Reproduction

From the owned task worktree:

```powershell
npm install --prefix .tmp-startup-phase2/sql-engine --ignore-scripts --no-audit --no-fund --save-exact @electric-sql/pglite@0.6.0 @electric-sql/pglite-socket@0.3.0
python -m pytest -q tests/test_app_data_performance_sql.py tests/test_startup_performance.py tests/test_startup_database_timings.py tests/test_static_asset_compression.py tests/test_database_read_pool.py tests/test_phase3_read_safety.py tests/test_orders_bounded_reader.py tests/test_orders_v20.py tests/test_home_fast_panels.py tests/test_home_shell_lazy.py tests/test_workspace_display_cache.py tests/test_human_work_tracking.py tests/test_daily_planner_overhaul.py -k 'not test_toolbar_countdown_mirror_is_client_side_and_cross_window' --disable-warnings
python -B scripts/benchmark_app_data.py --modules .tmp-startup-phase2/sql-engine/node_modules --before .tmp-startup-phase2/supabase_backend_before.py --out .tmp-startup-phase2/sql-baseline.json --samples 7 --certificates 25000
node --check tests/fixtures/data_performance_server.mjs
node tests/test_top_bar_requests.cjs
node tests/test_home_shell_component.cjs
python scripts/validate_render_topology.py
git diff --check
```

The preserved baseline snapshot is local evidence. When reproducing from the
same approved base without that snapshot, omit `--before` to use
`HEAD:supabase_backend.py`; its read behaviour matches the pre-Phase-2 baseline
(Phase 1 only added database timing log fields). The SQL test suite uses HEAD
as its baseline. It explicitly skips without installed optional SQL dependencies;
an explicitly configured invalid `LOCAL_APP_DATA_SQL_MODULES` path fails rather
than skipping. The standalone benchmark always requires its dependencies.

Primary references:
[Psycopg pipeline semantics](https://www.psycopg.org/psycopg3/docs/advanced/pipeline.html),
[Supabase connection guidance](https://supabase.com/docs/guides/database/connecting-to-postgres),
[PGlite socket limitations](https://pglite.dev/docs/pglite-socket).
