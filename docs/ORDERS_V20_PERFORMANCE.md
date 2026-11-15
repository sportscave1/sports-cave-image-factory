# Orders V20 performance release candidate

Local implementation, 16 October 2026. **Not pushed or deployed.**

Verified production/base: `5445e0f99a110eb2292d6cc279c55626de2356a6` on both
canonical application and webhook services. Origin/main still matches that revision.
This includes, and preserves, the earlier `f7b4e390` connection optimizations and
the subsequent visual approval safeguards. The candidate commit is reported in
the delivery message and external `release.json`; this document is part of it.

## Outcome and measurement boundaries

Orders queries, display lookups and interaction reruns are materially faster.
No new dependencies, services, migrations, indexes or operational caches were
added. No production application files or customer records were modified.

Two different experiments must be distinguished:

1. **Actual production data, read-only backend shadow:** baseline and candidate
   SELECT functions run in separate isolated processes inside the existing
   application service. The candidate replaces selected read definitions only
   in that process. It does not change deployed files or serve customers.
2. **Controlled local browser:** actual app dispatcher, Orders renderer, widgets,
   components, authentication and permission functions; signed disposable local
   cookie and synthetic account/data boundaries. Source delays use measured
   production medians. There are 560 synthetic orders, the same Latest 50 window
   containing 64 fulfilment units, multi-product orders, and a 288-product PSD
   directory. These results establish renderer/lifecycle gains, **not live
   production browser latency**. They exclude real Shopify and database I/O;
   those costs are tested separately by experiment 1. No customer data or
   production credentials enter the local preview.

All timings below are milliseconds, including browser action dispatch and result
delivery where applicable. p95 uses the nearest-rank method with 20 samples.
Five-sample browser operations do not have a claimed p95.

## Actual backend before/after

| Operation | n per version | Median before / after | p95 before / after | Min–max before | Min–max after | SQL before / after |
|---|---:|---:|---:|---:|---:|---:|
| Latest 50 | 20 | 1705 / 960 | 1748 / 1027 | 1618–1765 | 903–1127 | 6 / 4 |
| Search SC3303 | 20 | 869 / 309 | 927 / 316 | 866–934 | 296–319 | 6 / 4 |
| Orders badge | 20 | 160 / 166 | 163 / 168 | 159–164 | 158–170 | 1 / 1 |
| PSD directory | 20 | 143 / 147 | 146 / 151 | 142–146 | 141–151 | 1 / 1 |
| JPG resources, including parallel PSD | 20 | 1252 / 390 | 1280 / 401 | 1244–1299 | 384–455 | 3 / 3 |
| Render preparation | 20 | 1254 / 390 | 1269 / 395 | 1246–1287 | 384–396 | 3 / 3 |

Every operation made **zero external HTTP/API calls**. Warm measured lease wait
was zero. The existing bounded read pool remains at maximum three connections;
both processes created two transports, with zero waiters at completion.
Process RSS was 89.50 MiB before and 93.49 MiB after. This modest single-process
comparison is not a long-duration memory soak. Worker queue pressure/cancellation
tests separately verify bounded outstanding work and complete slot release.

Initial pool creation queued once (857/849 ms cumulative before/after); these
startup counters are not warm-operation lease waits. The profiler's first calls
are not cold server starts: setup already performs reads. First measured Latest
50 was 1698/1101 ms, search 923/323 ms, JPG 1864/876 ms. No cold Render process
start benchmark is claimed.

The badge implementation is unchanged. Its small timing fluctuation tracks the
unchanged PSD/transport reads; no badge performance improvement is claimed.
The 800 ms Latest 50 and 150 ms badge targets remain unmet. Search and JPG/render
backend targets are met in these samples.

## Browser before/after

| Controlled local operation | n per version | Median before / final after | p95 before / after | Min–max before | Min–max after |
|---|---:|---:|---:|---:|---:|
| Full reload, new session / warm server | 5 | 6553 / 2919 | — | 6394–7367 | 2718–3420 |
| Home → Orders, retained snapshot | 5 | 3138 / 2297 | — | 2964–3230 | 2257–2407 |
| Search, alternating exact orders | 20 | 4995 / 1980 | 5498 / 2050 | 4672–5562 | 1674–2127 |

Search uses fresh completion markers containing the requested query, row count
and render sequence, preventing old DOM content from masquerading as results.
An earlier candidate search run had a 1146 ms median; the conservative final
repeat above is the reported result. Server logs show approximately 740 ms for
the final search read plus render; browser/automation delivery adds variation.
The final browser search median is under two seconds, but its p95 is not.
Final navigation remains above the two-second target. Matched final comparisons
above use verified 1280-pixel desktop viewports. Earlier runs, including two
reload observations taken after the baseline tab had changed to a phone viewport,
are retained separately and do not enter this final comparison.

The final reload grace period is 1.2 seconds, supported by the measured Latest
50 p95 of 1.03 seconds. The earlier 0.8-second prototype still polled and had a
6464 ms local reload median. Its timings are retained as intermediate evidence,
not reported as the final candidate. Slow reads retain the existing asynchronous
loader, timeout, retry and visible error handling.

Actual production browser baseline: five reloads median 9042 ms (8751–10160),
five navigations median 2762 ms (2713–3069). Three valid search observations were
4827, 5805 and 5293 ms; two additional early readings were rejected because they
matched stale DOM. No p95 is claimed for these small sets. **There is no
post-deployment production browser benchmark**, because deployment is prohibited.

An interrupted exploratory reload batch and a non-equivalent disposable slow
source experiment are excluded from numerical comparisons. The prototype also
produced one local viewport-component loading warning; a reload recovered it.
Final ordinary reload samples all completed. This is recorded, not suppressed.

## Confirmed bottlenecks and changes

- Six sequential SQL reads each paid roughly 140 ms transport cost. Latest 50
  order-ID selection now remains before joins in a materialized CTE; table
  capability is projected by the same SELECT. Three independent enrichment
  reads pipeline on one exclusive existing lease. Selection and merge rules
  remain unchanged, including every unit of a multi-item order.
- Full order JSON was repeatedly transported across joined rows. It is now sent
  once per order and restored as independent copies before existing merge and
  refund logic. Initial base results were 590 KB across 126 joined rows.
- JPG reads previously fetched 288 products' layout manifests (609 KB) and used
  transactional connection preflight for display-only SELECTs. Orders now uses
  the existing bounded autocommit read lease and scopes layouts/quality reads to
  displayed products. **Every variant and conflicting master for each selected
  product remains included.** Generation, approval and write paths keep their
  original defaults and transactions.
- Search/loading polling and selection caused full-app reruns. Orders now has a
  fragment with the existing fresh authentication and permission checks, error
  boundary and navigation-completion signal. Fast reads finish in that render.
  Twenty search events left the full-app run counter unchanged.
- Repeated fragment events no longer redo the visibility-marker query within its
  existing 30-second cadence. Pending requests and certificate actions defer
  marker work. Request identity, account, route and generation checks reject
  stale results and refreshes. There is no new polling loop or status cache.
- The existing two read workers now have a bounded eight-request active/queued
  limit. Cancelled queued items retain a slot until drained, skip SQL, and release
  resources even during shutdown. Queue pressure uses the established error path;
  accurate JPG display can fall back to the same bounded database reader.

EXPLAIN ANALYZE supported transport/payload optimization rather than new indexes:
baseline server execution was 0.119 ms for order IDs, 12.735 ms base, 0.341 ms
fulfilment, 17.181 ms allocations, 13.732 ms manual editions, 101.968 ms catalogue
layouts and 7.356 ms job summaries. Base execute/delivery took 1040 ms and layout
execute/delivery 1002 ms in the initial profile. Unrelated imports/sidebar work
was not the dominant measured cost; startup/authentication was not broadly rewritten.

## Modified paths and functions

Paths are relative to the isolated root:
`C:/Dev/SportsCaveWorktrees/sports-cave-commerce-orders-v20-final-measured-performance-opti-20261016-61637fda`.

| Path | Important change |
|---|---|
| `supabase_backend.py` | Only `list_hybrid_order_rows`: bounded CTE, payload deduplication, pipelined enrichment and diagnostics |
| `orders_read_batch.py` | New exclusive-lease SELECT pipeline helper |
| `orders_display_reads.py` | New Orders-only fresh JPG read adapter |
| `orders_read_executor.py` | Bounded existing two-worker executor; cancellation/shutdown release |
| `auto_editions_store.py` | Only `Preparations.layouts/index`: optional product scope |
| `auto_editions_quality_store.py` | Only `Quality.index`: optional product scope |
| `auto_editions_runtime.py` | Only `download_links`: optional supplied display-read connection |
| `orders_page.py` | Request consumption/scope guards, inline grace, marker cadence and shared display reads |
| `app.py` | `_render_orders_workspace`, Orders dispatch and completion ownership |
| `orders_page.css` | Extend the **existing** 8 px spacing selector to the fragment wrapper; identical visible geometry |
| `tests/read_connection_fakes.py` | Disposable pipeline cursor/connection adapter |
| `tests/test_orders_bounded_reader.py` | Updated four-query bounded selection assertions |
| `tests/test_orders_loading_ui.py` | Updated read-repair query fixtures; retained stale retry coverage |
| `tests/test_orders_badge_repair.py` | Point overlap test at new display-read adapter |
| `tests/test_phase3_read_safety.py` | Supply new marker-state constants to existing AST fixture |
| `tests/test_orders_v20.py` | Queue/pipeline, JSON copy, auth, timeout, cancellation, rapid search and navigation guards |
| `tests/test_orders_v20_preparations.py` | Real disposable PostgreSQL scoping/readiness/quality fence tests |
| `tests/orders_v20_preview.py` | Local-only synthetic actual-app browser harness |
| `scripts/benchmark_orders_v20.py` | Aggregate-only SELECT profiler and parity checks |
| `scripts/orders_v20_candidate_bundle.py` | Export selected read definitions for non-deploying shadow checks |
| `docs/ORDERS_V20_PERFORMANCE.md` | This report |

## Safety and regression evidence

- 68 targeted unittest checks pass. Another 26 focused pytest checks pass against
  disposable PGlite PostgreSQL, covering scoped/unscoped equivalence, conflicting
  masters, source changes, expired quality checks, edition limits, variant scope
  and revoked policy. No skips. Existing read-pool cancellation/stale retry,
  webhook/refund reconciliation and distinct-order badge tests remain included.
  The network-blocked exported-candidate gate passes 88 checks (including those
  68 and 20 existing release-policy checks): 114 distinct gate/PostgreSQL checks.
- Read-only production comparison gives identical full normalized Latest 50 rows
  (50 orders / 64 units), identical JPG links, and identical searches for SC3303,
  SC3145, Warne and a non-match. No reduced result set or permission bypass.
- Production actionable count remains **0**. SC3303 stays Refund Pending / blocked,
  closed=false, allocation 678, **#019/100**. SC3145 stays Refunded / blocked /
  closed=true, allocation 483, **#051/100**. These are the stored reconciled Shopify
  projections; this task did not create refunds or run payment transactions.
- All 670 allocation rows and 1058 certificate rows have identical before/after
  aggregate digests. Edition counter/run/override fields have identical digests
  across the later verification window. The full product-table digest changed
  during the longer investigation; its earlier values were not exported, so no
  claim is made that every unrelated product metadata field remained static.
  All profiling is SELECT-only and this candidate has no production writes.
- Allocation, Edition Ops, refund logic, badge logic, Shopify sync, generation,
  job workers and connection-pool implementation are byte-identical to the base.
  AST comparison confirms all existing write/approval methods remain unchanged;
  126 Orders functions, including desktop/mobile rendering, search controls and
  action construction, remain unchanged.
- Desktop heading, form, table, columns and controls match baseline geometry.
  A fragment's default spacing was detected and corrected to the original 8 px.
  Selection, detail expansion/collapse and table scroll were exercised; scrollTop
  remained 720 across selection clearing. Refund Pending and Refunded/strikethrough
  display were visually checked with synthetic rows.
  True mobile checks at 390×845 also pass: heading, form and card geometry are
  identical before/after, all 64 units remain present, and mobile search and
  refunded status/strikethrough were exercised. Viewport overrides initially
  affected the selected tab rather than the inspected background tab; this was
  resolved by selecting the candidate preview and verifying its effective size.
- The broad legacy loading-UI suite has 12 failures and one error. An untouched
  production export has exactly the same failures/error. They are recorded as
  pre-existing, not suppressed or changed to manufacture a passing release.
- Production application and webhook health endpoints return HTTP 200; both
  deployments remain on the base revision. No deployed code, schema, environment
  variable, edition metafield, allocation or customer transaction was changed.

## Remaining verification and release control

The implementation is ready for production review/approval, with demonstrable
gains and completed representative desktop/mobile checks. It is **not a claim
that every production target or every requested browser scenario has passed**.

There was no long-running production concurrency soak, cold server restart,
production auth-expiry browser exercise, or synthetic production webhook/payment
write. Focused offline concurrency/security/refund tests cover those code paths.
Read-only shadow measurements do not prove live browser network performance.

No automatic deployment is authorized. Review the local commit and obtain
explicit deployment approval.
After an approved Git/Render release, remeasure the same production browser
operations and verify service health, badge and protected orders. Rollback is a
code-only revert; no data or schema rollback is needed.

Aggregate/raw timing evidence, screenshots, source comparisons, focused outputs
and offline candidate gate results are retained outside Git at
`C:/Dev/SportsCaveWorktrees/.studio/release-evidence/ov20`.
