# Automations Home and checkout Analytics performance

Local implementation only. No production publication, email, deployment or webhook mutation.

## Root cause and evidence

The old Home scheduled count/summary/activity work before the full metrics table. Its bottom-of-page, one-shot controller was required to resolve completed futures into visible data. The controller was unreliable below the viewport. Publication watching was registered only after the metrics table completed, and accepted publication patched existing cached rows but did not seed a cold cache.

Browser instrumentation additionally reproduced a lost wakeup: competing fragment updates temporarily disabled refresh buttons. A timer firing during that interval returned without retrying. After five seconds KPI skeletons and activity placeholders remained despite completed SQL; manually clicking the hidden KPI refresh resolved all six immediately. Earlier narrow-screen cold-list tests timed out at 30 seconds. These are local reproductions, not measurements of production latency.

## Current flow

Acceptance preserves the backend job ID, exact saved revision, name, trigger, timestamp and known Publishing state. The handoff row appears before analytics resolve. Acceptance resets the Home filters to newest/all so an earlier search cannot hide the accepted row. A bounded identity query has no event, enrollment or order joins. A separate deferred metrics query aggregates page-level enrollments and commerce in bulk. Its completion patches text spans instead of replacing interactive row controls. Existing resolved values stay visible during refresh/errors.

KPI, deferred row metrics and activity are independent scoped fragments. Their one-second completion checks reuse the existing 20-second read cache; they do not execute SQL every second. The list completion controller lives above the dashboard, retries unavailable/disabled controls, pauses around menus/dropdowns, and stops when navigation removes it. It refreshes only the table fragment. Normal list refresh remains 20 seconds.

Publication status has a three-second fragment and one compact query for visible pending identities. It patches escaped status spans only. It does not invalidate table, KPI or activity caches or rerun the application. Once no visible publication is pending, database status polling stops. The registered fragment callback remains a no-op until navigation. Failures retain backend truth, never imply Live. Pending attempts older than ten minutes display Publishing delayed; existing durable five-minute leases and bounded worker retries remain responsible for terminal job state. A permanently absent worker cannot be diagnosed as failed by the UI alone.

Home no longer calls Shopify for customer labels. Missing canonical labels remain customer IDs rather than blocking on a provider. No provider is contacted for first paint.

## Local measurements

- Durable acceptance: 5.3–6.4 ms in disposable SQL tests.
- Identity: 25.79 ms; deferred row metrics: 8.84 ms; counts: 19.65 ms; KPI summary: 19.59 ms; activity: 4.35 ms in one local fixture run. These serial timings are not production estimates.
- Before: initial dashboard submitted seven SQL reads, with the list requiring the heavier metrics query. Now: first-paint identity read is one lightweight query, submitted first. Total cold dashboard SQL: seven before versus eight now, because the list is separated from metrics. Provider calls: one possible Shopify labels call before versus zero now. Status tick: one compact query while pending, zero after completion.
- Five-width browser workflow, with secondary work delayed three seconds: 916 / 980 / 935 / 905 / 921 ms from edited-subject Publish click to usable Publishing row/actions at 1920 / 1366 / 750 / 390 / 320 pixels.
- All five success transitions passed with zero observed mutations to loaded KPI/activity regions. Failure and latest subject/HTML snapshot cases passed. No horizontal document overflow at the tested widths.
- End-to-end time includes save/flush debounce. It does not meet a 500 ms whole-transition target; request acceptance itself is fast. Shell-only navigation timing was not measured separately.

## Checkout Analytics work retained

The dialog reads the signed canonical checkout ledger first, with rolling UTC 7/30/90/365/all-time filters. One virtualized table replaces checkout pagination. Metrics/chart/activity defer behind the primary list. Manual reconciliation is bounded to 400 Shopify records and never enrolls anyone. Exact selected checkout enrollment still re-verifies Shopify, canonical token/customer, current live flow, consent, suppression and recovery; it creates a durable journey without sending inline. Explicit selected historical enrollment is allowed; automatic historical backfill remains prohibited.

The additive checkout analytics migration caches a small verified display projection and indexes checkout creation time. It preserves RLS and existing records. Published template/job safety remains unchanged. Apply both previously added publication-job and analytics migrations through the normal runner before deployment; this Home repair adds no further migration.

Baseline Analytics measurement: six SQL reads plus one mocked Shopify read, 63.12 ms serial local work. Revised dialog: four SQL reads, zero provider calls, 15.12 ms serial local work. A 5,131-row all-time fixture queried in median 175.02 ms; its native canvas table virtualizes rendering. Provider reconciliation and eligibility verification remain explicit rather than initial-paint dependencies.

## Verification boundaries

Synthetic loopback SQL and mocked providers only. Browser scripts block external requests. No real customer records, emails or automations were modified. Production network latency, worker health and the actual incident have not been measured here. Review local test results before approving deployment; this document is not production verification.

## Final verification results

- Focused Home/publication/native-flow/Analytics suites: 86 passed.
- Worker, CRM boundary, checkout preview, editor stability, diagnostics, tracking and Resend regression suites: 92 passed in a fresh process.
- Final clean SQL/browser publish run: 932 / 933 / 929 / 897 / 898 ms at the five widths. Success, safe failure, latest HTML/subject snapshot and independent secondary-region checks passed.
- Analytics browser: five widths passed; warm reopen 241 ms; 5,000+ virtualized rows; selected historical enrollment 314 ms, no inline email.
- Python compilation, JavaScript syntax, migration manifest and topology validation passed; git diff --check passed.
- Full discovery (`python -m unittest discover -s tests`): 4,707 run; 218 failures, 89 errors, 37 skipped. Broad rendering failures include shared Streamlit form-context leakage; relevant tests pass in isolated focused processes. A source-inspection test also ran while its source was being edited. This larger run is not comparable to the prior 825-test baseline, and its remaining failures have not all been established as pre-existing. It is not a green full-suite result.

A concurrent commit, 43b37ea, captured the earlier implementation in the shared checkout during testing. This run did not commit, push or deploy. Remaining local files relative to that commit: crm_automation_home.py, tests/test_crm_automation_home_reactivity.py, tests/test_crm_automation_ui.py, tests/test_crm_checkout_analytics_ui.cjs, and this document. Preserve the concurrent work. Deployment remains pending review of the full-suite failures and explicit approval.
