# Developer / Worker Health — local implementation

Local only, 16 October 2026. No commit, push, deployment, production migration,
flag activation, live worker restart, live companion installation or provider/data
mutation was performed. This is not a live-health certification.

## Isolated development identity

- Task `20261015-858d40e0`, owner `codex/worker-health-20261016`.
- Worktree `C:/Dev/SportsCaveWorktrees/sports-cave-integrations-developer-worker-health-diagnostics-and-du-20261015-858d40e0`.
- Branch `codex/task/integrations-developer-worker-health-diagnostics-and-du-20261015-858d40e0`.
- Approved Studio base and origin/main at inventory:
  `1a41ca3e78439d7b2391de6201a48712788b91a1`.
- Category entry point and other registered tasks were preserved. Existing
  installed preparation computer/companion was not changed or stopped.

## Findings and scope of repair

The current companion already has sign-in supervision, capped retry backoff,
DPAPI pairing, owned processor locks, retained package/receipt recovery and lease
renewal. The queue already prioritises paid orders, then its established manual,
advertised and catalogue rules, and stops terminal artwork from blocking the next
design. These implementations were reused, not replaced.

Missing connections were an administrator operations view, a durable pause at the
actual queue claim boundary, and independent worker revision/checkpoint telemetry.
Host presence alone did not establish useful processing health. Old generic
RuntimeError audits cannot establish an ICC, PSD or upload cause retrospectively.
New safe diagnostic codes retain underlying recognised causes; unknown failures
remain `Cause not yet determined` with an audit reference. No new claim is made
about the cause of an uninspected live order failure.

## Behaviour

Developer uses the existing disclosure styling/animation and defaults to Worker
Health. Its first child is Worker Health; its second is the existing owner-only
Dev Mode separate-tab link. Worker Health itself is active-administrator-only,
including its HTML, snapshot, diagnostics and control API. Staff cannot acquire it
through stored page permissions. Existing Dev Mode ownership restrictions remain.

Pause/Resume use the existing onboarding audit table. Pause takes exactly the
same table lock as `Queue.claim`, writes an identified control decision, and fences
subsequent claims. Repeating the same decision is idempotent. Active owned work,
uploads and same-owner reconnect/heartbeat remain valid. The state survives server
restart. Resume clears the decision without changing priorities, attempts,
approvals, mappings or numbering. It does not reset failed jobs. Already admitted
quality validation finishes its existing transaction; new quality passes are
also held before provider I/O. Discovery is not killed: Pause controls preparation
admission, not product registration, unrelated OS services or order downloads.

The page shows verified current preparation counts, separate review/repair/failure
counts, measured job duration, current stage and independent health evidence.
Current-job progress is indeterminate: no trustworthy per-file progress signal
exists during the synchronous Photoshop/export/package request. Backlog ETA uses
the median of at least three of the last twenty successful claim-to-completion
durations, excludes human review/repair, and becomes unavailable for stale output,
unhealthy workers, unusually long active jobs or separately pending quality checks.
It never fabricates supplier certification or time estimates. Pending V16 quality
validation is shown as queued verification, not an active Photoshop process.

The queue displays 25 keyed rows per page, 30px desktop row height, active/failed
first, six compact filters and inline details. Existing authorised review,
Connect/Retry/Prepare Now controls open inside a dialog; no bypass route or new
retry mechanism was introduced. Refresh updates data every 20 seconds while the
document is visible. Filters, scroll, open details, diagnostics fields and the
existing review iframe remain intact. The latest filter/page intent wins over a
slow earlier response. Mobile uses bounded horizontal table/health-strip scrolling
and the existing 44px sidebar touch targets.

Diagnostics use existing audits, Sydney timestamps, bounded search/date/component/
severity/design filtering and expandable history. Responses expose only declared
codes/descriptions and safe revision/checkpoint fields, never raw exceptions,
credentials, capabilities, signed URLs or filesystem paths. New terminal failures
capture the attempt count at that checkpoint. Older records may have only the
current attempt count and no recorded revision/retry time; missing evidence is
labelled explicitly. `WH-` unavailable references correlate to type-only server
logs; `AE-` references identify persistent audit records.

## Persistence and release requirements — NOT applied

`supabase/migrations/20261015200847_worker_health_telemetry.sql` was generated with
Supabase CLI 2.121.0 and validated on the isolated local PostgreSQL cluster. It
adds only a bounded-payload, RLS-protected heartbeat table and two indexes. It
does not update existing tables' rows, editions, allocations, source files or
approvals. Browser roles PUBLIC/anon/authenticated get no access; service_role
gets SELECT/INSERT/UPDATE. No startup migration exists.

`WORKER_HEALTH_TELEMETRY_ENABLED=false` is the documented default. A future owner-
approved release must apply the migration and enable this flag on the existing
application/Auto Editions scheduler processes. Telemetry piggybacks on the
existing 60-second discovery/priority/quality loop and existing companion claim/
heartbeat/reconnect requests; no service, thread, cron, polling worker or paid
dependency was added. Missing optional telemetry never aborts owned preparation;
the page reports Unavailable/Degraded instead of falsely reporting healthy.

Update the existing companion from the exact approved release only when idle,
using its existing installation/stop guards. Include the new root module
`worker_diagnostics.py` alongside `scripts/studio/auto_editions_local.py` and its
existing dependencies. Deploy compatible server APIs first; old servers reject
the optional new health request field. Do not hot-copy into a working processor
or remove its lock. The helper reports release revision plus normalised code hash;
the server compares both. No pairing reset or startup-task replacement is needed.

Rollback: disable optional telemetry without deleting its data; the independent
durable claim pause remains in the existing audit. Resume through the authorised
control before rolling back to older code that does not enforce this pause.
Never assume an older binary will honour a new pause record.

## Focused validation

Synthetic products, providers and disposable loopback PostgreSQL only. The SQL
fixture verifies its exact data directory and localhost address before creating
isolated databases. No live assets or customer allocations were used.

- Backend regressions: 156 passed across Worker Health, reliability, preparation
  host, V17 priority/onboarding, Reset, V16 quality and authoritative statuses.
- Final Worker Health/quality/theme/navigation checks: 61 passed including queued
  verification and paused quality admission; navigation/performance group: 31 passed.
- Four browser scenarios passed: Worker Health at 1280px/390px and native sidebar
  at both sizes. These cover default routing, collapse, owner Dev Mode link,
  indeterminate progress, Pause/Pausing/Resume, 20-second polling, preserved scroll,
  expanded rows/dialog checkbox/filters, pagination, lazy diagnostics and failure
  fallback. Mobile sidebar fixture supplies the existing shell's open class;
  this is not a physical-device or hosted authenticated acceptance test.
- Isolated 334-job snapshot: median 131.16ms, max 133.69ms over five reads;
  5 SQL statements with telemetry, 4 without, zero provider calls. Full internal
  snapshot about 157KB; the API returns only the selected 25-job page. Initial
  browser load uses one snapshot and no diagnostics request; history is lazy.
- Browser synthetic first render 80ms desktop / 57ms mobile. After ten simulated
  20-second refreshes: stable 349 DOM nodes, retained JS heap about 3.34MB with
  under 23KB growth after GC. These measurements exclude Streamlit shell,
  Photoshop, network latency and operating-system memory.
- Existing Edition Ops still uses its single batched status SQL and zero Dropbox
  calls. Its default code path is unchanged; evidence receipts are requested only
  by Worker Health. No Worker Health read/import is added to Orders rendering.
- `git diff --check` passed. All allocation/mapping/certificate fixture snapshots
  remained unchanged through pause, recovery and status reads. Existing regressions
  cover 167 deferred mappings and V17 opt-in continuous processing.

A combined 272-test run reported 244 passed / 28 failed / 18 subtests passed:
importing the full app at collection left Streamlit form context in shared test
state, contaminating later AppTest cases. The navigation group passes in its own
process. Standalone accounts testing reports 74 passed / 5 failed / 6 subtests
passed: Password Access source-string expectation, admin-all-pages expectation
that omits existing owner-only Dev Mode, two retired Files-preview expectations,
and product-upload prompt-button expectation. These areas were not rewritten.
The startup AST assertion also mistakes function-local imports `cleanup_completed`
and `RECEIPT_KEY` for unresolved names; both imports are present in the approved
base. These older suite assumptions/failures are recorded, not hidden or treated
as proof of a clean complete application suite.

Evidence under ignored `output/worker-health/`: backend-tests.log,
final-focused-tests.log, navigation-tests.log, accounts-tests.log, browser PNGs.
No claim of live health or full end-to-end Photoshop acceptance is made.

## Exact changed files

New runtime/UI: `worker_health.py`, `worker_diagnostics.py`,
`worker_health_api.py`, `worker_health_page.py`,
`components/worker_health/index.html`.

Runtime integrations: `app.py`, `navigation_runtime.py`, `os_accounts.py`,
`sidebar_theme.py`, `sports_cave_server.py`, `auto_editions_discovery.py`,
`auto_editions_onboarding_api.py`, `auto_editions_onboarding_store.py`,
`auto_editions_status.py`, `auto_editions_quality_store.py`,
`scripts/studio/auto_editions_local.py`, `.env.example`.

Persistence: `supabase/migrations/20261015200847_worker_health_telemetry.sql`.

Tests: `tests/test_worker_health.py`, `tests/test_worker_health_navigation.py`,
`tests/test_worker_health_ui.cjs`, `tests/test_worker_health_sidebar_ui.cjs`,
`tests/worker_health_nav_fixture.py`, `tests/sidebar_preview_app.py` (the AST
fixture now resolves app-relative styles from the app file, not tests/).

Documentation: this file.

## Remaining acceptance

Owner-approved release/migration/flag change and idle companion installation are
still required. Then verify actual matching process revisions, independent
heartbeats and one authorised live preparation with Pause during processing,
owned completion, Paused/no new claim and Resume. Retain mandatory artwork review
and V16 supplier-quality safeguards. No new test allocation, silent approval or
provider mutation is authorised by this local task.
