# App startup performance — Phase 3 Home and Orders

24 November 2026, Australia/Sydney. Completed locally in the existing owned
Studio task `20261124-564ab6e2`. Phases 1–2 are preserved. No commit, push,
merge, deployment, production application launch or business-provider action.

## Changes

### Home

The previous panel started a background snapshot, checked it on a one-second
fragment timer, and triggered a full app rerun when the first value became
available. Each cold section could independently request that rerun.

Panels now render in supported parallel fragments. An event on the existing
bounded snapshot entry signals completion. The fragment waits without holding
the cache lock, rechecks route/account/authentication scope every 50 ms while
waiting, and renders the result directly. It adds no database read or browser
polling loop. The initial wait is bounded to eight seconds.

Warm and valid stale snapshots render immediately. A stable status placeholder
is separate from the loaded content; clearing a loading label does not clear
the table or other native widgets. Widgets belong to the fragment itself,
correcting the prior external-container limitation.

The normal 30-second section refresh and existing snapshot TTL, memory limits,
worker count and stale-value policy remain. Failed/long first loads offer a
native Retry button that invalidates only that display key and reruns its
fragment. Automatic recovery now follows the normal 30-second refresh rather
than the previous cold one-second loop; users can retry sooner manually.
The first-read wait does not extend the lifetime of cached data.

### Orders

The primary Orders workspace is now a parallel fragment and explicitly opts
into direct completion. It starts the same bounded read, yields to pending
navigation/stop requests every 50 ms, and consumes its existing future when
ready. It keeps the original eight-second deadline and safe error/retry path.
No extra timer, executor or data request is added.

A stable loading-status slot shows Loading/Updating orders without replacing
the previous table while a search is pending. Completion updates the workspace
and its existing readiness acknowledgement without rerunning the surrounding
app. Direct/legacy renderer callers retain their previous bounded inline and
timer fallback; the canonical app route uses the new progressive path.

Pending reads now compare the complete existing account scope, including role,
permissions and active status, before and after receiving a result. Logout,
removed identity, navigation and account-revision changes cannot publish a late
snapshot. The workspace also checks scope again before acknowledging completion.
Existing authoritative authentication/permission checks and action guards remain.

The native Orders grid already has 50-row pagination, lazy proofs and selection/
viewport retention. Those behaviours were verified rather than replaced.
The bounded 75-order backend window and all fulfilment units remain intact;
this phase does not introduce unbounded historical loading.

## Browser evidence

Actual Home panel, Orders loader and Orders workspace functions run against
synthetic providers, with a synthetic data table in place of business actions.
Production app/server modules are not imported. The fixture uses the installed
Streamlit frontend and the production branding/compression/timing middleware.
No provider API routes or workers are mounted.

The pre-Phase-3 source snapshots were preserved before editing. Before/after
order alternates over three samples per scenario. Each context starts on Other,
then navigates to the requested page with either a 300 ms or 1,400 ms fabricated
read. This measures navigation/data reveal after frontend startup, not the app's
first browser download.

| Scenario | Before median | After median |
| --- | ---: | ---: |
| Cold Home section, 300 ms synthetic read | 1,358.9 ms | 417.1 ms |
| Orders, 300 ms synthetic read | 808.1 ms | 778.9 ms |
| Orders, 1,400 ms synthetic read | 3,266.7 ms | 1,912.0 ms |
| Orders search, 1,400 ms synthetic read | 2,927.9 ms | 1,554.4 ms |

Fast Orders results were already covered by the previous inline path; the small
difference there is not a demonstrated meaningful improvement. The strong
findings are removal of cold Home completion reruns and the slower Orders
timer/rerun penalty.

All candidate navigation scenarios used one full app run for the user-requested
navigation, with zero additional full runs for completion. The old cold Home
and slow Orders paths used two. Slow search completion changed from one extra
full run to zero. Previous rows remained visible during every tested slow
candidate search, and all 150 synthetic fulfilment-unit rows were preserved.

Readiness is timestamped by a browser MutationObserver/requestAnimationFrame
check, including a visible data-frame container for Orders, rather than by
Playwright's later selector-poll return. Rapid-departure checks require a fresh
Other-page run marker, not a leftover stale DOM node. Two-second abandoned reads
could not paint Home/Orders content or acknowledge Orders after departure.
Home's explicit failure/retry path recovered on its second synthetic read with
zero full-app reruns.

Exact departures, samples, source hashes and checks:
[APP_STARTUP_PHASE_3_EVIDENCE.json](APP_STARTUP_PHASE_3_EVIDENCE.json).
Full fixture logs and samples: `.tmp-startup-phase3/browser-final.json` and
`.tmp-startup-phase3/browser-final.log`.

These small Chromium samples establish direction and behaviour, not production
p95s. They do not measure actual Home providers, authentication/network costs,
the complete operational grid under the app shell, native WebView2 or Safari.

## Verification

- 168 tests passed, with 39 passing subtests; one known unchanged toolbar test
  was deselected as documented in Phase 2. The run emitted one warning.
- New contracts cover event wait/lock ownership, first-run Home completion,
  native fragment widget ownership, display-only Retry, stale-data reuse,
  logout/removed-account/role/permission/revision races, Orders deadline/error
  handling and stale navigation acknowledgements.
- All Phase 2 actual SQL cases ran against the disposable local database.
- Existing Orders grid/feed browser tests passed, including keyed row retention,
  new arrivals, selection transfer, later-page retention, lazy proof loading,
  failure recovery and narrow layouts.
- Paired loading browser checks passed at 1440 px and 390 px, including retained
  rows during search, no extra completion runs, rapid departure and Home Retry.
- Shell/Home JavaScript suites passed. Native grid/feed JavaScript suites:
  14 tests passed.
- Render topology and diff checks passed. No Render configuration changed.

## Reproduction and remaining work

From the same retained task worktree:

```powershell
python -B scripts/benchmark_page_loading.py --samples 3 --out .tmp-startup-phase3/browser-final.json
python -m pytest -q tests/test_page_loading_progressive.py tests/test_app_data_performance_sql.py tests/test_startup_performance.py tests/test_startup_database_timings.py tests/test_static_asset_compression.py tests/test_database_read_pool.py tests/test_phase3_read_safety.py tests/test_orders_bounded_reader.py tests/test_orders_v20.py tests/test_home_fast_panels.py tests/test_home_status_performance.py tests/test_home_shell_lazy.py tests/test_workspace_display_cache.py tests/test_human_work_tracking.py tests/test_daily_planner_overhaul.py tests/test_orders_feed.py tests/test_orders_prodigi_grid.py tests/test_orders_feed_browser.py tests/test_home_saved_briefs_browser.py -k 'not test_toolbar_countdown_mirror_is_client_side_and_cross_window' --disable-warnings
node tests/test_top_bar_requests.cjs
node tests/test_home_shell_component.cjs
node tests/test_orders_live_feed.cjs
node tests/test_orders_grid_ui.cjs
python scripts/validate_render_topology.py
git diff --check
```

The SQL tests use the pinned local dependencies from the Phase 2 report. The
loading fixture uses the preserved local before-source snapshots; on the same
approved base without those files, it can read the corresponding baseline
functions from commit `333d9a9d481bb96c0c84fb42bbfa80a8a7f26d35`.

The child uses the existing allowlisted environment, empty secrets-file list,
private runtime directory and external-socket denial. Chromium uses a dead
external proxy with a loopback bypass. All fixture processes are terminated.

Phase 4 still needs to address frontend first-download/startup costs and broader
performance budgets. No live-app speed target or exhaustive business-workflow
verification is claimed. Changes remain uncommitted, so Studio status Tested
does not mean integration or release readiness.

Public API references used:
[Streamlit 1.58 fragments](https://docs.streamlit.io/1.58.0/develop/api-reference/execution-flow/st.fragment),
[fragment rerun scope](https://docs.streamlit.io/1.58.0/develop/api-reference/execution-flow/st.rerun).
