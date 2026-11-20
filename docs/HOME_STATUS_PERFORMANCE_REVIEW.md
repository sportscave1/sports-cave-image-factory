# Home and header performance — local review evidence

Task: `20261118-ddafdaf6`
Owner: `codex-home-speed-20261118-01a1ecc0`
Approved base: `7f9f617e2bce2f150d51561c2f0873412312b036`
Date: 18 November 2026, Australia/Sydney

## Result

Home now dispatches three independently cached display panels without waiting for
storage. Saved results remain visible during background refreshes. Initial empty
caches show a loading state, checked each second until ready; populated panels
refresh their display every 30 seconds. This does not promise instantaneous fresh
data during a database outage. Snapshots expire after 15 minutes without success.

The Design, Uploads and Ads header reserves visible cards before its first
response, retains them across controller replacement and outages, clears private
content when identity/permission scope changes, and labels delayed status. Failed
queue checks disable queue controls until recovery. Planner failures are explicit
unavailability, never a successful empty timer. Order counts retain a stale label
rather than disappearing. Shared header GETs have eight-second deadlines, and
destroyed controllers cannot restart planner polling.

## Changes by phase

1. **Baseline:** inspected the Studio-approved implementation and existing tests.
   It is newer than the initial AI checkout and includes the real companion cards
   and published morning briefs. Added reproducible synthetic timing evidence.
2. **Reliability:** fixed initial failure, rerun, identity, timeout and recovery
   paths. Added real-browser regression tests for these transitions.
3. **Home:** independently loads saved sports/Meta/weekly data, caches by account
   revision and permission scope, retains stale data, bounds memory, and removes
   automatic live Meta/GA4 queries when saved reporting data is old. Explicit
   reporting-period selections still fetch results with a deadline. Weekly totals
   remain complete; the Home detail table shows the latest 100 entries. Calendars
   retain archive ranking fields instead of twenty full article bodies.
4. **Live updates:** retained adaptive polling: companion checks every two seconds
   when active, fifteen when idle, one second while an initial snapshot loads,
   and bounded backoff on failure. Hidden documents suspend these reads. Reads
   coalesce on the server across matching user scopes. Existing email streaming
   remains in place. A new universal stream or cross-tab leader was not necessary
   for this local change; authentication still runs per request.
5. **Contention:** header display requests no longer take the design companion
   claim lock, reconcile delivery/stalled uploads, or verify files in Dropbox.
   Authoritative worker/queue operations retain their existing behavior. Two
   header snapshot workers and three separate Home workers admit no queued
   backlog. This isolates display refresh capacity, not the shared database or
   the entire application's process resources.
6. **Verification:** isolated Streamlit panel tests, intercepted browser fixtures,
   disposable PGlite PostgreSQL tests, Node contracts, Studio static/infrastructure
   checks, screenshots and synthetic benchmark. No application server or live
   production data was used.

## Evidence

- `home-performance-tests.txt`: **133 Python tests passed**, nine subtests passed.
- Six JavaScript test scripts passed, including six companion automation cases.
- Three header browser tests were repeated after the final control-state changes
  and passed.
- Browser layout checks: header at 390–1600 px; saved brief markup at 320–1600 px.
- `home-performance-images/`: inspected header screenshots. The synthetic fixture
  intentionally has no real logo URL; its missing-logo marker is not app evidence.
- `home-performance-evidence.json`: three simulated 200 ms saved-data reads took
  600.956 ms sequentially; new dispatch took 0.951 ms and all snapshots were ready
  after 202.801 ms. Warm three-panel reads were 0.009 ms at p95; blocked-refresh
  reads were 0.001 ms at p95. Zero queued refresh backlog. These measure the cache
  architecture, **not network/browser rendering or production load time**.

To reproduce the Python suite, run `scripts/run_home_performance_checks.ps1` from this worktree. PGlite path is supplied through
`AUTO_EDITIONS_TEST_PGLITE`; browser tests use installed Edge in headless mode and
intercept all requests. The benchmark runs with
`python scripts/benchmark_home_display.py` and never contacts a service.

## Boundaries recorded at completion of local validation

- No commits, pushes, merges, deployments, service changes or live customer actions.
- The original unfinished AI checkout was neither copied nor modified. Integration
  with that work requires testing the combined revision later.
- Full application preview remains disabled by the repository's Phase 1 rules.
  The browser and Streamlit tests above exercise isolated real components with
  synthetic inputs; they do not certify production cold starts, authentication
  latency, real database saturation, or end-to-end LCP/INP.
- Before a separately authorised release, verify the combined revision, real
  query plans and browser p95 timings on the approved isolated integration setup.
  No Render topology changes are needed.
- Keep this worktree and uncommitted changes for review. Studio's clean-commit
  release-readiness gate is intentionally not satisfied.

## Release authorisation

The user subsequently authorised committing, pushing to GitHub and deploying
these changes to the existing Render service. The task branch was integrated
with the current production main before rerunning the combined test suite.
The exact release commit and live deployment outcome are recorded in Studio
task history and the deployment response; the earlier local-only statement
above describes the initial validation stage. No infrastructure changes are
part of this release.
