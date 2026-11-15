# Email Performance V5 — local delivery report

2026-10-09. Performance-only changes; no production writes, sends, publications,
deployments, migrations, service creation, commits or pushes performed by this task.

## Result and scope

Campaign warm opening improved from **379.5 ms p50 / 843.8 ms p95** to
**304.9 ms / 358.9 ms** in the controlled local browser comparison. First-session
opening was 1,323 ms before and 823 ms after. Warm return to Campaigns was
211.2 ms p50 / 256.3 ms p95 after. These are local measurements, not production
latency guarantees. The p95 is the highest of 12 samples, not a robust production
tail estimate. V4's roughly 1.1-second opening numbers were individual observations
with a different click timing boundary; they are not the denominator for V5 gains.

V4 and the Campaign template-picker, checkout table and email reliability reports
were reviewed first. The publisher, worker, checkout table, database access layer,
provider integration, automation delays and content were not changed.

## Confirmed bottlenecks and changes

1. `test_control()` rendered the closed Send Test popover's entire form, scripts,
   readiness checks and email HTML. It now mounts those controls only when opened,
   using Streamlit's supported `popover.open` state. Once opened, its form remains
   mounted: a concurrent browser test caught that unmounting loses unsent form text
   that has not reached Python yet. Desktop/narrow sessions now retain independent
   addresses on close/reopen. Readiness is checked on opening and authoritative validation
   still runs at the actual send boundary. This also benefits the shared automation
   editor without changing its delivery behavior.
2. Campaign opening and market changes started exact recipient preparation even
   when the user only wanted to edit. They now display the existing aggregate
   segment counts; exact preparation starts in Review & send. Consent, current
   eligibility, snapshot identity and dispatch validation remain authoritative.
   This deliberately trades eager preparation for work when review is requested;
   it does not promise that the first review opens faster.
3. The size meter reparsed unchanged rendered HTML when optional remote image byte
   metadata changed. A pure helper now combines already-parsed asset URLs with
   metadata. HTML/text size, unknown assets and threshold semantics are unchanged.
   The toolbar retains its original size-meter position using a placeholder, while
   the composer is emitted before filling it. Original image assets are untouched.

Diagnostic profiles showed HTML imports dropping from 18 to 5 calls and asset
analysis from three calls to one in the intermediate lazy-preflight implementation.
That intermediate change alone did not materially improve browser opening. Deferring
the entire closed popover produced the final measured improvement. Profiles include
Streamlit event-loop overhead and are not additive server stage stopwatches.

## Controlled browser measurements

Headless installed Chrome, Windows, local Streamlit 1.64, disposable loopback SQL,
120 synthetic campaigns with approximately 40 KB HTML each; Shopify and outbound
HTTP blocked/mocked. Twelve independent sessions, each opening then reopening a
Campaign. Eleven desktop viewports (1440×1000), one narrow viewport (390×1000).
Profiler disabled for the table. Baseline and final runs were sequential without
the broad unit suite running. Browser timers start at DOM click, not Playwright's
action-settling delay. `cold` means a new browser session, **not** 12 independently
restarted servers; only sample zero includes cold process imports/cache setup.

All values below are p50 / nearest-rank p95, milliseconds unless stated.

| Metric | Before | After |
|---|---:|---:|
| New-session first useful saved fields | 542.4 / 1323.0 | 321.2 / 822.6 |
| Warm first useful saved fields | 379.5 / 843.8 | 304.9 / 358.9 |
| New-session preview iframe mounted | 622.4 / 1328.2 | 343.8 / 825.3 |
| Warm preview iframe mounted | 395.6 / 846.2 | 307.9 / 366.0 |
| Warm opening SQL wait sum | 13.7 / 58.2 | 23.5 / 61.3 |
| New-session opening SQL wait sum | 25.6 / 172.4 | 11.4 / 51.3 |
| Warm Editor tab → editable textbox | 214.2 / 242.9 | 206.9 / 240.4 |
| Warm Templates tab → defaults visible | 121.6 / 212.8 | 116.0 / 236.0 |
| Warm Mobile preview selection | 94.6 / 102.8 | 86.9 / 120.2 |
| Warm return to Campaigns | 207.0 / 285.5 | 211.2 / 256.3 |

The main opening targets were met locally. Editor tab p95 remains above 200 ms;
template and preview tails did not improve. Do not claim a general interaction,
SQL or network speedup. Preview-ready means iframe attached, not all external
images painted; external assets are deliberately blocked. Template measurement is
picker readiness, not loading every possible remote template body.

SQL instrumentation records query shapes and elapsed client time, without query
arguments. The three warm reads remain: saved draft, template/default revision
marker, and authoritative existing campaign/delivery record. They protect freshness
and editability. The first cold open also checks/loads default configuration and
reads aggregate-count cache state. Cold count is seven after, eight in this baseline
sample (an asynchronous state read overlaps the window); later fresh sessions are
three after versus three/four before. No queries were artificially combined and no
eligibility data was cached. Query time is not equivalent to connection acquisition
time: that component was not separately instrumented. It cannot be subtracted from
browser wall time to produce an accurate browser-render cost.

The measurements establish first useful fields, iframe mounting, textbox readiness
and query duration. Navigation dispatch, imports, normalization and browser paint
are not each independently timed. Import profiles implicated first-load dependency
work, but no dependency/import rewrite is justified by the final sub-second sample.

Raw browser samples, SQL timings and summaries are in `email-performance-v5/`.

### Save and resource checks

Twenty-four independent synthetic SQL Campaign drafts exercised the actual
`flush_current(force=True)` path. Unchanged saves took 0.007 ms p50 / 0.013 ms p95,
with zero checkpoint calls. Modified saves took 17.515 ms / 54.644 ms; every changed
draft advanced exactly one revision, read back the exact document, then produced no
second checkpoint on a repeated unchanged save. These are server-side local save
times, not browser acknowledgement or production network timings. Persistence code
was not modified; no pre-V5 save distribution was captured, so no save speedup is
claimed. Tracing reported 1.141 process CPU seconds and 15.9 MB peak Python allocation
for the entire 24-draft benchmark, not whole-application RSS or editor CPU savings.

## Production V4 verification and publishing

Read-only Render inspection found both the canonical `sports-cave-os`
(`srv-d8kl4on7f7vs73dvavv0`) and existing `sports-cave-seo-worker`
(`srv-d9ujm9navr4c73amurgg`) running `051d57b1598ff71eef11f4e8938c4239041edbec`.
That source includes V4's dedicated publication lane and connection reuse.
The observed deployment completion times were 05:39:22Z and 05:37:45Z. Local HEAD
subsequently advanced externally to `7f1481e`; this task did not deploy either commit.

Two real successful publication records from October 9 had queue waits of 2.091
and 2.079 seconds, one attempt each, with requested-to-completion database timestamp
intervals of 5.464 and 4.837 seconds. Both preceded the observed 05:37 worker restart;
they show earlier V4 behavior that day, not executions on the newest instance.
Production does **not** consistently meet the five-second target in these samples.

Stage logs separately recorded claim 864–908 ms, validation 1,894–2,465 ms and commit
1,668–1,917 ms. PostgreSQL transaction timestamps and monotonic stage timers differ;
do not sum them as if they shared identical boundaries. There were only two samples,
so no production p50/p95 claim is made. Final browser readback/acknowledgement and
connection acquisition latency could not be measured read-only. V4's local reference
was acknowledgement 9 ms p95 and completion 2.35–2.93 seconds; it is retained as
historical evidence, not relabelled as a fresh V5 production measurement.

A fresh local publication benchmark used 12 samples each of one-, three- and
six-email flows (mocked external validation, tracing enabled). For three-email
flows, acceptance was 35.353/79.957 ms p50/p95; direct worker execution including
validation/commit was 315.124/389.258 ms; readback was 18.860/46.074 ms. Unchanged
automation saves issued zero saves (0.009/0.021 ms). Direct executor timing excludes
queue polling and browser refresh; it is **not** end-to-end publication latency.
The historical V4 same-size executor measurement was 211.523/245.709 ms: the newer
run is slower, not an improvement. Since this code is unchanged by V5 and these
are different-day/environment measurements, it does not establish a V5 regression.
The benchmark used 11.734 process CPU seconds and 23.4 MB peak Python allocation
across all 36 flows. Raw results are in `publication-local.json`.

The due-publication EXPLAIN used `crm_automation_publish_due`: 0.113 ms execution,
5.357 ms planning, five shared-hit blocks, no due rows. A snapshot had ten idle,
one idle-in-transaction and one inspection connection plus two extension sessions.
A subsequent transaction-age observation was about 0.953 seconds. This does not
establish pool exhaustion, a connection leak or a persistent long transaction.

The existing worker lane uses one thread-owned reusable autocommit connection with
explicit per-operation transactions, one-second idle polling and bounded five-second
error backoff. Regression tests cover connection reuse, close-on-failure and no
replay after uncertain commit. No transaction is intentionally held for a UI action.
Coarse 15-minute worker metrics over 04:00–05:45Z showed about 0.013–0.014 CPU cores
and 198–218 MB RSS across deployment instances. There is no controlled V5 production
before/after CPU or RSS result because V5 was not deployed.

Only one non-test send in the inspected window had usable due-to-first-submission
timestamps: 36.367 seconds, with zero overdue pending sends at inspection. This
includes validation/dispatch, not just time until a worker claims it. **It cannot
prove that publishing never delays sends, nor attribute the delay to publishing.**
Reliable claim timestamps and more passive production samples would be needed for
that conclusion. Existing independent publication-lane and delivery regression tests
provide structural coverage; they are not substitutes for production tail telemetry.

No measured evidence justified publisher, polling, connection, index, schema or
checkout-table changes. Sanitized observations are preserved in
`email-performance-v5/production-observations.json`.

## Reproduction

Run local SQL tests with `.venv/Scripts/python.exe scripts/run_email_reliability.py`.
For the original baseline comparison use `--modules tests.email_v5_baseline`; it
loads the five original application modules and corresponding old tests in memory
from `7f1481e1f7e54eb3665e3d0b9df789531e15eb5b`, without changing the checkout.
Those five sources were verified byte-for-text equivalent to the snapshots taken
before V5, including the preceding Customer-Like Send Test work.

For browser measurements set `EMAIL_V4_CAMPAIGNS=1`, `EMAIL_V5_MEASURE=1` and
`EMAIL_V5_LABEL=current-clean`, then run
`scripts/run_email_v4_browser.py tests/test_crm_email_v5_ui.cjs` with the local venv.
The baseline uses `EMAIL_V5_BASELINE=1` and `EMAIL_V5_LABEL=baseline-clean`.
Set `NODE_PATH` to the installed Playwright dependencies if required. Optional
`EMAIL_V5_PROFILE=1` adds diagnostic profiling; do not mix those timings with the
clean comparison. `scripts/summarize_email_v5.py` generates the evidence summary.
`--modules tests.email_v5_benchmark` measures actual no-op/modified Campaign saves.
All runners own and clean up disposable local SQL/server processes.

## Deployment and limitations

Normal deployment of the existing application only, after separate approval. No
new configuration, permissions, dependencies, migrations, indexes or Render services
are required. This task has not deployed or published anything.

Opening/searching, no-op saves and published immutable flow versions must remain
non-mutating. Send Test remains an explicit user action. The changes do not remove
readiness checks, stale-revision protection, consent checks, checkout identity or
provider idempotency. No edition allocation, orders, fulfillment, theme or certificate
code was changed. Unknown provider outcomes are not automatically replayed.

Further work should be driven by passive production samples of claim time,
validation and commit/readback latency. Current evidence supports observing these
boundaries, not changing them or adding indexes/services speculatively.

## Files changed for V5

Application:
- `crm_campaign_page.py` — defer filling the existing toolbar size indicator.
- `crm_campaign_controls.py` — defer exact audience preparation until review.
- `crm_campaign_send_ui.py` — lazy closed popover, preserve recipient state.
- `crm_email_size.py` — pure asset-metadata merge without another HTML parse.
- `crm_email_size_ui.py` — reuse parsed size report.

Tests and reproducible evidence:
- `tests/fixtures/crm_email_performance.py` — opt-in baseline, query and profile instrumentation.
- `tests/test_crm_email_v5.py` — lazy UI and size-report equivalence tests.
- `tests/test_crm_email_v5_ui.cjs` — browser measurements and immutable-draft assertions.
- `tests/test_crm_email_v5_sessions_ui.cjs` — concurrent desktop/narrow unsent form isolation.
- `tests/email_v5_baseline.py` — read-only in-memory baseline suite loader.
- `tests/email_v5_benchmark.py` — actual Campaign save benchmark.
- `tests/test_crm_audience_prepare.py` — assert preparation is deferred to review.
- `tests/test_crm_email_size.py` — assert retained toolbar location and first-paint safety.
- `tests/test_crm_send_flow.py`, `tests/test_crm_segment_performance.py`,
  `tests/test_crm_test_issue_groups.py` — explicitly open the lazy popover before
  interacting with it; original delivery/readiness assertions retained.
- `scripts/summarize_email_v5.py`, this report and `docs/email-performance-v5/*`.

Temporary runner outputs are generated under `tmp/`. The prior Customer-Like Send
Test work is included in the baseline; it is not attributed to this performance task.

## Regression results

| Run | Total | Passed | Failures | Errors | Skipped |
|---|---:|---:|---:|---:|---:|
| Pre-V5 baseline on current repository | 1,195 | 1,172 | 12 | 10 | 1 |
| V5 full CRM suite | 1,197 | 1,175 | 11 | 10 | 1 |
| Focused editor, safety, review, delivery and worker suite | 178 | 178 | 0 | 0 | 0 |
| After final mounted-form retention correction | 32 | 32 | 0 | 0 | 0 |

Full baseline took 206.855 seconds; V5 204.843 seconds. The full V5 run's 21
failures/errors match the recorded V4 list. The baseline additionally reproduced
the timing-sensitive `test_slow_checkout_does_not_block_other_results_and_bounded_parallelism`;
it passed in V5 and in the focused run. It is not counted as a V5 fix. Exact lists,
counts and the preserved V4 baseline are in `summary.json`; no new failing test
identity remained. The complete suite is **not green**. Existing failures concern
audience-sync fixtures, older UI/source contracts, footer/default fixtures, storage
recovery/template-cache expectations and issue attribution. They were not weakened
or repaired outside this task's scope.

The full run preceded the final mounted-form retention correction. After that
small change, all 32 directly affected UI/size/readiness tests and the two-session
real-browser check passed. The last correction preserves the initial unopened
fast path used for clean timing comparisons.

Browser verification:
- 24 Campaign opening cycles across 12 sessions, desktop and narrow viewports;
  exact SQL digest of every draft/version remains unchanged through open, tabs,
  preview and close. Preview iframe identity is retained; no Streamlit exceptions.
- Existing real HTML typing/autosave/navigation test passed, with no browser
  errors, no oversized transient icons, and zero measured long tasks while typing.
- Eight abandoned-checkout editor cycles retained the exact full flow configuration
  and revision 2. No publication or provider transport was invoked.
- Two concurrent desktop/narrow sessions retained distinct unsent test addresses
  through close/reopen. No submit action was taken.
- Actual SQL save benchmark: 24 unchanged/modified/repeated-save sequences passed.
- Publication benchmark: all 36 synthetic executions passed.

Functional browser checks run alongside regression tests are not included in the
uncontended timing table. Baseline-source tests were updated only where the desired
performance contract changed (deferred preparation/placeholder placement). Four
popover UI tests now explicitly open it; their original validation and delivery
assertions remain. All real customer/provider/Shopify mutations were excluded.
