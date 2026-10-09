# Email performance V4 — local implementation and verification

9 October 2026. Baseline: `736cd66`. All changes remain local and uncommitted. No production writes, emails, publications, migrations, configuration changes, commits, pushes or deployments were performed. Existing appearance and delivery infrastructure are preserved.

## Findings and current production outcome

Read-only inspection at 23:16:50 UTC on 8 October confirmed that **Abandoned Checkout — Wall Preview 1 was already ACTIVE, LIVE v3**, revision 120. The pending operation shown in the earlier screenshot succeeded; it does not need another publication attempt. Both current draft and published flow had enabled delays of **600 seconds and 43,200 seconds**. The inspected document differences were review/count metadata excluded from the existing publication comparison, not a meaningful unpublished content difference.

Persisted v3 timestamps show **152.077 seconds waiting in the queue, then 8.483 seconds processing**. The previous v2 job waited 361.373 seconds and processed for 8.429 seconds. Both succeeded on their first attempt. These are individual production observations, not percentiles.

The confirmed dominant bottleneck was queue waiting. Previously, the existing CRM worker reached publication only after archive, customer, review and other maintenance work, and its main loop then waited 30 seconds. Publication could therefore wait behind unrelated external operations. The database due-job query took **0.171 ms execution / 2.394 ms planning** in a read-only plan inspection and used the existing due index. This does not support blaming that query for minutes of waiting. The exact breakdown of the remaining production processing time is not established; safe claim/validation/commit timing logs were added to resolve it after an approved deployment.

A database activity snapshot showed one active session (the inspection), eleven idle and one idle-in-transaction; it did not establish connection exhaustion. Existing publication, enrollment, checkout and send indexes were inspected. No new index or migration was justified.

## Changes

### Publishing and recovery

The sequence is now: **immediate submitting acknowledgement → flush pending editor changes → request the existing durable job → show persisted queue/processing state and elapsed time → verify persisted LIVE version**.

- One bounded publication polling thread runs inside the **existing CRM worker process**, independently of maintenance. It invokes the existing durable executor, claims and fencing. It introduces no additional Render service or email delivery mechanism. Normal idle polling is one second; errors back off. Administrative `--once` execution retains synchronous publication.
- The polling thread owns one reusable database connection. Each store operation still has an explicit transaction; idle polling holds no transaction. Disconnects discard the connection, and connection code never replays SQL. Existing job reconciliation resolves uncertain commit outcomes. This follows [Psycopg explicit transaction semantics](https://www.psycopg.org/psycopg3/docs/basic/transactions.html).
- Template and immutable version writes are batched into two SQL statements instead of two per email, inside the original atomic publication transaction.
- The browser acknowledgement remains visible through the next paint. Duplicate-click protection and the pending-HTML save barrier remain. A 15-second submission uncertainty message requests status reconciliation, not automatic resubmission.
- The toolbar polls persisted status every two seconds without reopening the editor or rebuilding analytics. It retains polling after a transient status-read error. After 30 seconds it explains that processing is taking longer and that the current live version remains available.
- Existing five-minute leases, three-attempt limit, transient retry backoff and twenty-minute absolute job expiry remain. Failed/expired operations have explicit recovery states. Success requires persisted LIVE state and matching draft/version, never just a click or request acceptance.
- Concurrent requests, no-change publication and lost commit acknowledgements remain protected by durable job uniqueness, revision checks and fencing. Tests verify one publication/version under the covered retry and uncertainty cases. This is not a claim that every possible distributed failure was exhaustively tested.

### Correct editor state

Opening the editor previously normalized a legacy checkout document after its clean baseline was captured, injected default sections, and could refresh product data into the authored draft during component mounting. Forced saves could then write an unchanged document. In the baseline browser reproduction, opening/closing an untouched checkout email advanced revision **2 → 3**. The updated implementation retained **2 → 2** through eight open/tab/preview/close cycles.

- Editable view normalization precedes baseline capture and does not persist merely from opening a view.
- Component mounting and unchanged native blur events do not alter authored content or invalidate its review flag. Explicit product refresh and fresh send/test eligibility checks remain.
- Exact no-change saves do not write or create history revisions. Real edits still pass permission, revision and queued-readonly checks.
- Exact content undo restores the clean state, including automatic review-state changes. Explicit review-checkbox changes remain meaningful. HTML whitespace is not stripped to manufacture equality.
- Local editor-versus-saved differences show **Unsaved changes**; saved-versus-live differences show **Unpublished changes**. Genuine existing unpublished drafts remain visible.
- Toolbar wake signatures use small state tuples rather than repeatedly serializing complete HTML documents. Saved/live comparison is cached by the current row/version identity. A fresh narrow `updated_at` read invalidates the session-local full-row display cache; writes still read and lock authoritative state.

### Worker and other Email paths

The intermittent pause/resume test was reproduced with the application clock two seconds ahead of the database: a resumed job was not immediately claimable. Pause/resume now uses the database transition timestamp used by due claims. The original assertion is unchanged; a clock-skew regression was added. Remaining-wait and frozen-version behavior are preserved.

Campaign editing shares the no-op save and clean-baseline fixes. Final campaign recipient eligibility remains fresh. Inbox/navigation, scheduled campaigns, provider idempotency, purchase/recovery cancellation, suppression, webhooks and worker safety paths were covered by existing tests. They were not rewritten for speculative performance gains.

The checkout table retains its combined query, 50-row pagination, 12-second cache, approximately 15-second backend refresh and shared browser countdown. A delta-only query was considered but not introduced: progress comes from multiple authoritative ledgers, and the measured bounded query did not justify adding invalidation complexity. Countdown timing and send scheduling are unchanged.

## Measurements

Raw measurements, SQL plans, exact baseline/current failing test identities and sampling notes are in [measurements.json](email-performance-v4/measurements.json). Local fixtures use real application logic and disposable loopback PGlite SQL; browser external requests were blocked. These numbers do **not** represent production after deployment.

| Local measurement | Before | After | Interpretation |
|---|---:|---:|---|
| Publish acknowledgement visible at next paint, 30 clicks | 0/30 | 30/30 | After p50 1.7 ms, p95 9 ms; old paint timing is not an acknowledgement latency |
| Checkout automation first useful flow, one observation | 1,572 ms | 1,530 ms | Small point difference only |
| Checkout editor opening, 8 cycles, p50 / p95 | 329 / 898 ms | 233 / 267 ms | p50 improved 29%; small sample includes initial opening |
| Untouched checkout revision | 2 → 3 | 2 → 2 | No unnecessary persisted change |
| Campaign home first useful content, one observation | 2,021 ms | 1,546 ms | 23.5% point improvement; not a percentile |
| Campaign cold editor, one observation | 1,080 ms | 1,186 ms | Slower in this run |
| Campaign warm editor, one observation | 1,082 ms | 1,074 ms | Essentially unchanged; 500 ms target not met |
| Campaign warm return navigation, one observation | 265 ms | 231 ms | Bounded interaction; not a percentile |
| Campaign opening reads, cold / warm | 7 / 3 | 7 / 3 | Unchanged; zero warm tab/default reads, no observed browser long tasks |
| Complete browser publication, 1/3/6 emails | Production observations above are not comparable | 2,345–2,933 ms, 12 samples | Actual click → verified LIVE, including both polling intervals; local p50 2,397 ms, p95 2,933 ms |

The complete local publication check is below five seconds but does **not** meet the aspirational two-second target. There is no comparable controlled baseline end-to-end distribution, and no production-after p95. Individual flow sizes have only four full-browser samples each.

Twelve independent microbenchmark samples per flow size, milliseconds (p50 / p95):

| Operation | Emails | Before | After |
|---|---:|---:|---:|
| Accept durable publication | 1 | 24.645 / 44.280 | 14.581 / 38.800 |
| Accept durable publication | 3 | 30.502 / 48.072 | 15.568 / 30.688 |
| Accept durable publication | 6 | 28.993 / 84.204 | 19.613 / 72.783 |
| Validate publication | 1 | 64.450 / 201.735 | 75.381 / 182.900 |
| Validate publication | 3 | 177.307 / 207.916 | 170.838 / 199.863 |
| Validate publication | 6 | 328.130 / 365.328 | 325.498 / 396.613 |
| Worker publication execution | 1 | 83.977 / 261.984 | 101.787 / 204.833 |
| Worker publication execution | 3 | 242.493 / 285.067 | 211.523 / 245.709 |
| Worker publication execution | 6 | 409.216 / 454.764 | 380.892 / 426.715 |
| No-change publication | 6 | 20.852 / 75.608 | 30.956 / 52.208 |
| Clean forced save | 1 | 26.969 / 58.267 | 0.007 / 0.009 |
| Clean forced save | 3 | 48.104 / 92.442 | 0.007 / 0.012 |
| Clean forced save | 6 | 63.679 / 85.094 | 0.008 / 0.010 |
| Canonical comparison | 6 | 2.199 / 3.927 | 2.195 / 2.698 |

Clean saves make zero store-save calls instead of one; that is a verified reduction, not merely a timing claim. Genuine save behavior remains tested. Canonical comparison itself is essentially unchanged; the optimization avoids repeated comparisons. Smaller performance differences are noisy: the baseline microbenchmark overlapped the broad suite. Some medians regressed, so these results do not establish uniform speedup.

Across the 36 instrumented microbenchmark cases, process CPU was **10.469 → 9.234 seconds** (11.8% lower); peak Python traced allocation **23,183,099 → 23,198,334 bytes** was effectively unchanged. These are fixture CPU/allocations, not production worker RSS or load-test results.

Checkout audit, unchanged single-query 50-row page, twelve warm samples per case, p50 / p95 milliseconds:

| Total checkouts | 1 email | 3 emails | 6 emails |
|---:|---:|---:|---:|
| 50 | 41.698 / 84.005 | 30.656 / 45.825 | 52.162 / 78.528 |
| 500 | 14.387 / 34.210 | 16.704 / 38.661 | 33.730 / 52.385 |
| 5,000 | 34.942 / 57.504 | 17.635 / 20.018 | 24.002 / 35.756 |

Fixtures include pending, accepted, uncertain, failed, recovered and frozen v1/v2 journeys. Payloads stayed bounded by page size: 78,765 / 117,065 / 174,515 bytes for 1/3/6-email flows. Local fixture warm-up/JIT explains non-monotonic timings; larger datasets are not inherently faster. This is a backend-read audit, not a new frontend render speedup or a measured production table-refresh distribution.

Campaign final-review snapshots with 50 mocked fresh eligible recipients and real local SQL: Send now review p50/p95 **34.571/56.871 ms**; scheduled review **36.694/60.540 ms**. No real queue release or email was performed. Raw browser tab/preview interaction samples are retained in the evidence; preview click-return timing is not claimed as complete iframe rendering latency.

## Verification

- Baseline broad CRM suite: **1,088 run, 1,066 passed, 11 failures, 10 errors, 1 skipped**.
- Final broad CRM suite: **1,104 run, 1,082 passed, the same 11 failures and 10 errors, 1 skipped**. No new failing test identities. Existing failures remain unresolved; this is not an all-green suite.
- Focused reliability/publication/worker/editor suite: **455 passed** (104.176 seconds).
- Additional mailbox/navigation/worker suite: **86 passed** (2.804 seconds). A first sandbox-restricted invocation hit a temporary-directory permission error; the approved local rerun passed.
- V4 focused unit suite: **12 passed**, including real catalogue mount preservation, exact undo, unchanged saves, cache invalidation and connection ownership/recovery.
- Browser checks passed at 1,440 px and 390 px: pending HTML barrier, duplicate clicks, unrelated preview mutations, failure/retry, reload reconciliation, retained editor/input state, no analytics rebuild while polling, eight no-touch cycles for each welcome/checkout fixture, 30 acknowledgement samples and 12 complete durable publications.
- Lost commit acknowledgement, rollback, stale revisions, no-op history, paused/resumed timing and two-second clock skew have focused regressions. A stale-delete test now makes a real edit to produce the newer revision it requires; its rejection assertion was not weakened.
- Compile checks and `git diff --check` passed.

The 21 baseline failures/errors cover audience sync fixtures, HTML workspace, footer/default rendering, storage recovery, UI activation, preview/section source assertions, template cache and preflight attribution. Exact names are preserved in the JSON evidence. They require separate investigation rather than being hidden or relaxed here.

Reproduction entry points:

```powershell
.venv/Scripts/python.exe scripts/run_email_reliability.py --all-crm
# Browser driver starts and stops only its disposable local fixtures.
.venv/Scripts/python.exe scripts/run_email_v4_browser.py
.venv/Scripts/python.exe scripts/run_email_v4_browser.py tests/test_crm_publish_ack_ui.cjs
$env:EMAIL_V4_BACKGROUND_PUBLICATION='1'
.venv/Scripts/python.exe scripts/run_email_v4_browser.py tests/test_crm_publication_latency_ui.cjs
Remove-Item Env:EMAIL_V4_BACKGROUND_PUBLICATION
```

Browser runs require installed Playwright/Chromium and the local Node dependency path. The benchmark files and fixture flags document the optional baseline and automatic publisher modes. The complete publication fixture uses a thread in its test process to share the disposable SQL adapter lock, not a new production UI publisher.

## Files changed

Application/component:

- `components/crm_sections/automation_publish.js`
- `crm_automation_publication.py`
- `crm_publication_connection.py` (new)
- `crm_automation_store.py`
- `crm_automation_toolbar.py`
- `crm_automation_ui.py`
- `crm_campaign_page.py`
- `crm_campaign_recovery.py`
- `crm_campaign_store.py`
- `crm_email_editor_context.py`
- `crm_engine.py`
- `crm_section_ui.py`
- `crm_worker.py`

Existing test/fixture updates:

- `tests/fixtures/crm_automation_preview.py`
- `tests/fixtures/crm_email_performance.py`
- `tests/test_crm_automation_publication.py`
- `tests/test_crm_automation_publish_ui.cjs`
- `tests/test_crm_email_performance_ui.cjs`
- `tests/test_crm_html_workspace.py`
- `tests/test_crm_native_automations.py`

New tests, benchmarks and evidence:

- `scripts/run_email_v4_browser.py`
- `tests/email_v4_benchmark.py`
- `tests/email_v4_audit_benchmark.py`
- `tests/fixtures/email_v4_server.py`
- `tests/fixtures/email_v4_publisher.py`
- `tests/test_crm_email_v4.py`
- `tests/test_crm_email_v4_ui.cjs`
- `tests/test_crm_publish_ack_ui.cjs`
- `tests/test_crm_publication_latency_ui.cjs`
- `docs/EMAIL_PERFORMANCE_V4.md`
- `docs/email-performance-v4/measurements.json`

## Deployment requirements and remaining limits

Production benefits require a separately approved code deployment to the existing primary web application and existing worker that runs CRM. **No migration, new service, topology change or new environment setting is required.** No deployment was performed.

After approval, use the added stage timing logs to verify production queue/validation/commit p50/p95 and the reusable connection under real PostgreSQL concurrency. Local fixtures cannot establish production multi-session capacity, pool pressure or external Shopify latency. Existing frozen enrollments, immutable versions, delivery receipts and customer history remain intact.

Campaign warm editor opening remains about 1.1 seconds in the latest observation, and complete local publication remains above two seconds. Production Inbox network latency, full preview-frame paint, maintenance-cycle throughput, due-email latency and worker RSS were not remeasured; existing regression coverage is not a substitute for those measurements. No new claim is made against the earlier maintenance benchmark. Investigating the measured remaining campaign opening time and production stage logs is justified; speculative rewrites of sending, checkout refresh or readiness checks are not.
