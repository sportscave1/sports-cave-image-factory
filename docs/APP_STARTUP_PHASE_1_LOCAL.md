# App startup performance — Phase 1 local measurement

Date: 24 November 2026 (Australia/Sydney).

Phase 1's local instrumentation, repeatable isolated baseline and focused checks
are complete. This establishes measurement; it does not claim a production
speed-up or full production Home/Orders timings. No commit, push, merge, deployment,
production access, customer data, provider request, schema change or dependency
installation was performed.

## Task and source

- Studio task: `20261124-564ab6e2`.
- Owner: `codex-perf-phase1-20261124-session-a`.
- Branch: `codex/task/core-phase-1-app-startup-performance-measuremen-20261124-564ab6e2`.
- Approved base: `333d9a9d481bb96c0c84fb42bbfa80a8a7f26d35`, dated 23 November.
- Worktree: `C:/Dev/SportsCaveWorktrees/sports-cave-core-phase-1-app-startup-performance-measuremen-20261124-564ab6e2`.

Studio's approved base is newer than the category checkout used in the original
review. It already has bounded read pools, background Home snapshots, newer
Orders loading and readiness handling. The October reports are historical
context; they are not measurements of this base or current production.

## Changes

1. Start the app script clock before the early Product Upload/helper imports.
   The former clock omitted those imports from startup totals. This corrects a
   diagnostic blind spot; it does not make those imports execute faster.
2. Add fixed-label process timings for route imports, application assembly,
   deployment migrations, SEO storage, readiness, each background worker/warmup
   entry point, listener dispatch and ASGI lifespan readiness.
3. Add `Server-Timing: os_headers;dur=...` to public initial-document and frontend
   bundle responses. Log anonymous response-header and WebSocket-accept timings.
   Responses are not buffered, and no cache, request, endpoint or polling loop
   is added. Constant-time health stays outside the new wrapper.
4. Expose the existing database `connection_ms` and `query_ms` diagnostics in
   successful/shared/failed read logs. Account validation intervals, queries,
   pooling, deadlines, retries, transactions and permissions are unchanged.
5. Add a repeatable Chromium benchmark with fresh contexts, cached reloads,
   Home/Orders transitions, network/CPU throttling and fresh server processes.
   The runner rejects source changes during a run and records source hashes.

No demonstrated production bottleneck was removed speculatively. Existing
compression and browser caching passed; replacing them would repeat completed
work. Startup migrations still finish before the listener is invoked, and a
migration failure still prevents listening.

## Measurement boundaries and isolation

The repository disables general app previews/imports until Developer Studio's
Phase 2 safety prerequisites exist. The production `app.py` and
`sports_cave_server.py` were not imported or launched. Tests extract selected
startup/health code with AST and execute it using synthetic dependencies.

The browser fixture uses the installed Streamlit frontend and the actual
branding, compression and timing middleware, with fabricated Home metrics and
50 fabricated Orders. It deliberately simulates 40 ms authentication and a
120 ms data miss per route/session. These delays are explicitly test data,
not real account or database performance.

The child uses an allowlisted environment, an empty Streamlit secrets-file list,
a private temporary working directory and loopback binding. It imports no
production API routes or workers. A socket audit hook rejects external
connections. Chromium uses a dead external proxy with a loopback bypass;
Playwright request interception is avoided because it disables HTTP caching.
Observed external page requests and browser exceptions must both be zero.
All fixture processes are terminated and private runtime directories are
removed by the runner.

Definitions:

- Fresh browser: a new browser context with an empty HTTP cache, on an already
  running fixture server. Only the first sample also includes the fixture's
  first script execution in that process.
- Cached reopening: reload in the same browser context, preserving its asset
  cache but starting a new Streamlit session. This is not a browser-process
  restart or native desktop-shell launch.
- Warm navigation: switch between already loaded synthetic Home/Orders routes
  within one session.
- Server restart: a fresh fixture process plus a fresh browser context. Server
  health and first-browser readiness are reported separately.
- Usable timing: navigation/click to the matching content-complete marker and
  the visible metric/table element. It includes automation observation overhead.
  The raw file also records DOM-observed shell/content timestamps, paint events,
  long tasks, document TTFB, WebSocket handshake and asset transfer.
- `os_headers` ends when response headers are available. It is not page TTI,
  complete download time or database execution time.
- Database `connection_ms` is lease acquisition and can include pool waiting or
  new transport establishment. Existing `query_ms` includes callback/fetch and
  read cleanup wall time; it is not PostgreSQL EXPLAIN execution time. Shared
  reads correctly report zero additional connection time.
- Lifespan readiness is an ASGI signal, not proof that the OS socket is bound.
  The benchmark separately waits for an actual HTTP health response.

## Final local baseline

Normal desktop: Chromium headless, 1440 x 1000, loopback, 10 independent browser
contexts. Slow profile: 4x CPU slowdown, 150 ms network latency, 200,000 bytes/sec
download and 100,000 bytes/sec upload, three contexts.

| Synthetic fixture experience | Normal median | Normal sample p95 | Slow median |
| --- | ---: | ---: | ---: |
| Fresh browser to usable Home fixture | 466.916 ms | 559.008 ms | 8,797.153 ms |
| Cached reload to usable Home fixture | 360.402 ms | 371.579 ms | 1,215.550 ms |
| Warm Home navigation | 107.236 ms | 120.041 ms | 214.888 ms |
| First Orders navigation in a session | 315.894 ms | 721.361 ms | 2,174.523 ms |
| Warm Orders navigation | 104.492 ms | 111.800 ms | 261.944 ms |

The JSON uses nearest-rank sample percentiles. Ten observations are a small
baseline; three slow/restart observations are exploratory, not reliable
production p95 estimates. Warm Home has two transitions per context.

The first Home fixture downloaded 3,317,269 decoded JS/CSS bytes as 908,331
encoded bytes (912,231 transfer bytes including browser-counted overhead).
Every normal cached reload transferred zero JS/CSS bytes. Large bundles were
gzip encoded and used immutable cache headers. These benefits existed before
this phase and are verified, not newly claimed savings.

Machine-readable summary, source hashes, exact dependency versions and restart
samples: [APP_STARTUP_PHASE_1_EVIDENCE.json](APP_STARTUP_PHASE_1_EVIDENCE.json).
Full local samples, paint/long-task/resource timings and sanitized fixture logs:
`.tmp-startup-phase1/baseline.json` (intentionally ignored by Git).

## Interpretation and next steps

1. The installed frontend still has a material first-download/browser cost:
   the minimal synthetic fixture takes about 8.8 seconds under the slow profile
   despite small fixed simulated data delays. This supports investigating
   frontend transfer and main-thread work for initial opening.
2. Warm/cached behaviour is materially different from fresh opening. Comparing
   these states as a before/after speed gain would be misleading.
3. The normal isolated shell can render quickly. Actual Home/Orders providers,
   authentication/database latency, server route imports, migrations, native
   WebView2 startup and real concurrent load remain unmeasured here. There is no
   basis for claiming the live app meets the proposed speed targets.
4. For Phase 2, use the existing pools and new lease/read breakdown rather than
   introducing another pool. Measure realistic synthetic data/query plans in an
   isolated database before changing queries/indexes.
5. For Phase 3, profile this newer Home/Orders implementation and its completed
   content signals before changing polling or rerun behaviour. The earlier
   category-checkout diagnosis should not be applied blindly to the new base.
6. Keep the canonical Render service and current topology. No infrastructure
   capacity change is justified by this fixture baseline.

## Verification and reproduction

- Focused Python: 42 passed, plus 23 passing subtests.
- Browser: 10 normal samples, three slow samples, three fresh fixture server
  restarts; compression, immutable caching, zero cached bundle transfer,
  initial-document timing header, no external page requests and no browser
  exceptions asserted.
- JavaScript: shell request-lifetime suite and Home mirror/navigation suite passed.
- All nine changed/new Python files parsed without importing the application.
- Render topology validation and `git diff --check` passed.
- Mocked execution of the actual startup entry point verifies worker ordering and
  failure-closed migrations. Actual health-wrapper code bypasses inner lifecycle
  and diagnostic work.

Run from this task worktree:

```powershell
python -m pytest -q tests/test_startup_performance.py tests/test_startup_database_timings.py tests/test_static_asset_compression.py tests/test_database_read_pool.py tests/test_phase3_read_safety.py tests/test_home_fast_panels.py tests/test_home_shell_lazy.py tests/test_workspace_display_cache.py --disable-warnings
python -B scripts/benchmark_app_startup.py --samples 10 --slow-samples 3 --restart-samples 3 --out .tmp-startup-phase1/baseline.json
node tests/test_top_bar_requests.cjs
node tests/test_home_shell_component.cjs
python scripts/validate_render_topology.py
git diff --check
```

Changes remain uncommitted for review. Studio can record Tested; it must not
claim Ready for Review/integration readiness, which requires a separately
authorized clean committed revision.
