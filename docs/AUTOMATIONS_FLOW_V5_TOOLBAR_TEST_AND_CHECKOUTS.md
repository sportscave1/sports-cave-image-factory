# Automations Flow V5 — local implementation and validation

Date: 10 October 2026 (Australia/Sydney). No production database, automation,
customer enrolment or provider delivery was changed. No commit, push or deploy.
Concurrent navigation and other workspace changes were preserved.

## 1. Missing operational panels

V4 retained the operational functions but moved their calls behind the
`flow-operational-diagnostics` admin route. The normal Flow route stopped calling
them. The locally available commit `02c81f1d4dcb2c572e63d8aa4004766d458b634d`
confirmed the earlier sequence → recipient timelines → abandoned checkouts order.
This implementation restores those calls without reverting the page or caches.

## 2. Restored operations

Recipient timelines and scheduled deliveries and Abandoned checkouts are again
expandable sections beneath the sequence. Checkout loading retains the existing
51-row keyset read (50 displayed plus a next-page sentinel), search, pagination,
cross-page selection, details, refresh, authorised enrolment requests, retries,
recovery information and user timezone handling. No first-page-only replacement
table was introduced. Existing recipient activity and permission checks remain.

## 3. Customer progress

The existing `crm_checkout_progress.columns()`, `progress()` and `listing()` paths
remain authoritative. Columns use published stage metadata, while historical
cells match stable stage IDs to immutable journey steps and recorded receipts.
Draft edits, reorder and disabled stages do not replace a customer's snapshot.
Queued/claimed/submitting records are not projected as successful sends. Existing
tests cover due times, acceptance, missing receipts, purchase, pause, suppression,
historical checkouts, timezones and three-or-more published columns.

Collapsed panels do not call the checkout loader, customer timeline reads or
Shopify. Refresh arming stops on collapse. Authorised durable enrolment work
already requested continues in its existing worker. Search/filter values and
selected checkout keys retain the existing session persistence.

## 4. Test dropdown

The normal Flow toolbar now exposes only Test entire email flow, Email address
and Start Test, followed by a compact durable receipt when a test exists. The
receipt includes recipient, TEST — Draft/TEST — LIVE, per-stage state and next
due time in the operator's timezone, with cancellation and a status-check action.
Opening and closing uses an isolated Streamlit fragment. Closed Test renders do
not perform a recipient lookup or read test history.

Simulation controls have been removed from this dropdown. `test_flow()` and
`simulate()` remain available to internal tooling and tests.

## 5. Full-sequence test architecture

`crm_flow_tests.start()` reads the saved draft under a database lock, checks its
expected revision, captures the flow and rendering settings, and prepares the
enabled messages using the shared renderer. Immutable SQL guards protect the
snapshot, recipient, actor, message bodies, stage positions and configured delays.
No publication method is called. Editor changes known to the authenticated session
must be saved first; browser-only unsubmitted step-settings form values are not
part of the saved test snapshot.

The new `crm_flow_tests` and `crm_flow_test_stages` tables are separate from
customer enrolments, marketing sends, checkout records and attribution tables.
The existing CRM worker calls the test processor, which uses the existing gated
Resend transport. It processes at most one due test stage per worker cycle.

## 6. Timers

The first enabled email is scheduled from test creation. Each subsequent enabled
email is scheduled from the previous provider acceptance plus its real configured
delay. The existing `single_delay()` and `scheduled_at()` contracts are reused.
Disabled emails do not advance the anchor. There is no production clock scaling,
browser timer authority or immediate send-all action. Worker-cycle latency can
make delivery later than the deadline; it never makes a stage early.

## 7. Recipient restrictions

Start requires an active administrator, CRM Automations permission, a stable
authenticated actor, one valid bare email address, and server-side internal-test
authorisation. Background recipients must also be explicitly configured in
`CRM_INTERNAL_TEST_RECIPIENTS` or `SPORTS_CAVE_ADMIN_EMAIL`. The worker rechecks
that deployment-owned allowlist before each submission. Allowlist removal blocks
the stage and cancels waiting stages. The UI cannot approve a mailbox.

## 8. Delivery safeguards

Per-actor advisory locking and durable operation IDs prevent repeated requests
from creating the same test twice. Limits are five sequences per administrator
per rolling 24 hours, two active sequences and at most 32 enabled stages (within
the flow-definition validator's own bounds). Jobs survive UI reruns and closure.
Scheduled jobs resume through a fresh worker/store instance.

The states are WAITING, SCHEDULED, SUBMITTED, ACCEPTED, FAILED and CANCELLED.
SUBMITTED is a durable submission fence; it is not evidence of acceptance or
inbox delivery. Only an actual provider receipt permits ACCEPTED and scheduling
the next email. Explicit provider rejections are FAILED. Unknown responses and
crashes after the submission fence remain held for audit and are never blindly
replayed, including beyond a provider idempotency window. Automatic reconciliation
or manual retry of uncertain test submissions is not implemented.

Cancellation stops future WAITING/SCHEDULED stages. An already submitted message
cannot be recalled. Stored error categories and receipts support investigation.
An isolated test unsubscribe URL and test-rendered footer are used; no customer
unsubscribe record, discount, purchase or suppression is created. Sample checkout
rendering uses selected artwork where available and no redeemable recovery URL.
Subjects are marked `[FLOW TEST]`, and content includes an explicit test marker.
Provider acceptance is never presented as confirmed inbox delivery.

## 9. Diagnostics

The normal Flow toolbar has no Diagnostics dropdown or replacement settings
button. Existing diagnostic functions, simulation engine, worker health data,
audit records and the secured operational diagnostic route remain in the code.
Email-editor diagnostic behaviour outside the Flow view was preserved.

## 10. Analytics

The reporting-period dropdown is in the toolbar. The visible Refresh analytics
button is removed. An invisible fragment wake control supports scoped invalidation.
Period changes and completed enrolment mutations invalidate the appropriate reads.
The active analytics fragment revalidates on a bounded 180-second interval, using
existing asynchronous reads, TTLs and last-good values. Sequence metrics refresh
only when needed. Toolbar/sequence rendering does not wait for report completion.

Entered, Sent, Delivery, Opens, Clicks, Conversions, Orders and Bounce calculations
were not changed. Test records do not enter their underlying customer ledgers.

## 11. Toolbar and visible labels

The toolbar order is Back, automation name, reporting period, Save draft, Test,
publication status/action and Pause/Resume. Save/publish/lifecycle contracts remain.
The title truncates with its full text in a tooltip. Controls are 32px, with Segoe
UI, existing restrained gold styling, subtle borders and accessible focus states.
It wraps at smaller widths instead of forcing horizontal overflow.

Normal Flow title/version badges, thumbnail version captions, preview version
wording and Draft content (thumbnail: published) stage wording are removed.
The thumbnail selection, version metadata, cache keys, immutable publications and
actual customer sending-version selection were not changed by this task.

## 12. Top spacing

The generic CRM 4rem padding and nested workspace spacing were inspected. Flow now
uses a scoped `calc(var(--sc-topbar-height,64px) + 8px)` top offset and 6px workspace
gaps. This respects the actual OS top-bar height, including responsive overrides.
The sidebar and OS top-bar implementation were not edited. Synthetic browser
fixtures verify the fallback header clearance; the complete authenticated OS shell
was not used for an end-to-end visual test.

## 13. Performance evidence

Results: `docs/flow-v5-evidence/browser-results.json` and `collapsed-panels.json`.
Before source was captured locally before V5 edits in `tmp/flow-v5-before`.
Browser runs use synthetic flows, mocked analytics/operations and equivalent
valid synthetic cached thumbnails. Six samples per browser give 12 startup
samples per variant; p95 uses nearest rank. These are local fixture measurements,
not production latency guarantees. Concurrent navigation code changed during
development; the fixture was adapted to its new request contract.

| Measurement | Before p50 / p95 ms | After p50 / p95 ms | Scope |
|---|---:|---:|---|
| First visible header | 287.85 / 584.37 | 292.00 / 497.56 | 12 samples each |
| First usable email stage | 459.37 / 630.86 | 416.00 / 545.58 | 12 samples each, warm synthetic thumbnails |
| Analytics visible | 484.20 / 635.85 | 445.47 / 580.10 | 12 samples each, mocked report |
| Both collapsed panel bodies | 0.0205 / 0.0257 | 0.0204 / 0.0265 | 1,000 Python-only samples; zero data reads |
| Open Test | Not equivalent | 145.72 / 170.64 | 12 after samples |
| Close Test | Not equivalent | 4.20 / 6.31 | 12 after samples |
| Return from editor | Not measured | 257.75 / 369.84 | 12 after samples, navigation fixture |
| Expand checkouts | Not equivalent | 1023.83 / 1048.75 | Two synthetic panel samples |
| Expand recipient timeline | Not equivalent | 159.58 / 172.92 | Two synthetic panel samples |
| Start mocked journey | Feature absent | 194.42 / 227.21 | Two mocked-start samples |

Measurements varied across repeated runs; earlier runs included higher after
startup medians. No consistent overall speed improvement or production
performance non-regression is claimed. Opening the full Automations overview,
real checkout-progress query/render latency, actual editor performance, uncached
thumbnail generation and the complete thirteen-action production-equivalent
benchmark matrix remain unverified. Startup measurements include collapsed
headers, and demonstrate no checkout/timeline loader invocation in that state.

## 14. Browser validation

Chrome and Edge passed the synthetic Flow fixture at 1920, 1440, 1366, 1024, 750,
430, 390 and 320px. Toolbar height is 32px through 750px where available width
permits; at 430px it wraps to 70px, and at 390/320px to 108px. No horizontal main
overflow was observed. Screenshots are in `docs/flow-v5-evidence/`.
Checks cover version-label absence, minimal Test controls, unchanged eight metric
names, collapsed-loader counters, panel expansion, mocked Start Test and editor
return. Checkout data/loading and the editor are mocked in this fixture; it is
not an authenticated production browser test. Earlier navigation failures were
traced to the fixture observing the old navigation key after concurrent code
changed to route requests; the final fixture consumes the current contract.

## 15. Regression results and unresolved gates

- Final V5-only suite: **13 tests passed**, using a new disposable PostgreSQL
  fixture, fake clock and mocked transport. Includes cardinalities 1/3/6/12,
  timing, disabled stages, duplicate operations, snapshots, role restrictions,
  stale revision, cancellation/ownership, limits, failures, uncertain submission,
  restart handling, SQL immutability and no customer-ledger effects.
- Combined affected regression rerun: **102 tests passed**, including checkout
  enrolment requests, PostgreSQL security, Flow, paginated checkout reads and
  historical customer progress. Logs: `tmp/flow-v5-final-regression.log`.
- Complete existing security/reliability suite: **395 tests run; one failure** in
  `test_batch_sql_statement_count_is_constant`: its checkout-worker requests did
  not finish within the existing deadline. That module passed in the 102-test
  isolated rerun. This timing gate remains unresolved; its assertion was not
  weakened. Log: `tmp/flow-v5-security-final.log`.
- Existing extended Flow regression: **158 tests run; one failure** in
  `test_email_three_only_frozen_versions_tracking_and_no_duplicates`. It also
  failed in the isolated discount-delivery suite: a frozen customer journey used
  newly published email content. The failing customer sending code was already
  modified before this task and was not changed here. This is a material release
  concern, not a waived security test. Logs: `tmp/flow-v5-regression.log` and
  `tmp/flow-v5-discount-isolated.log`.
- The PostgreSQL table-count test now expects the two additional test tables and
  still asserts RLS for every CRM table. Browser-role access to the test tables is
  separately denied and tested. No legitimate sending-security assertion was
  removed.

PostgreSQL fixtures use the existing disposable PGlite PostgreSQL harness on
loopback. Worker restart is exercised with a fresh Store against persisted fixture
state, including a submitted-stage hold. Independent native PostgreSQL processes,
multi-worker contention and a real provider round trip were not verified.

## 16. V5 files touched

- `crm_flow_page.py`, `crm_automation_toolbar.py`, `crm_flow_thumbnail.py`
- `crm_flow_tests.py`, `crm_flow_test_ui.py`, `crm_worker.py`
- `migrations/20261010090000_crm_flow_tests.sql`
- `tests/test_crm_flow_v5.py`, `tests/test_crm_flow_v4.py`
- `tests/test_crm_postgres.py`, `tests/crm_postgres_server.mjs`
- `tests/check_crm_flow_v5_ui.py`, `tests/fixtures/crm_flow_v5_preview.py`
- `tests/check_crm_flow_v4_ui.py`, `tests/check_crm_flow_v4_operations.py`
- `scripts/benchmark_flow_v5.py`, this report and `docs/flow-v5-evidence/`

Other pre-existing modified/untracked files were retained. Navigation changes in
the shared Flow/toolbar files were preserved. No Render topology file was touched.

## 17. Future configuration requirements

The new migration was exercised only in disposable local fixtures. A future
explicitly authorised release would need that migration and the updated existing
CRM worker. Test delivery remains gated by `CRM_MARKETING_ENABLED`,
`CRM_MARKETING_TEST_ENABLED`, the existing Resend sender/API/reply configuration,
an isolated test unsubscribe base URL and the internal recipient allowlist.
No production migration or configuration change was performed, and no deployment
command or release request is supplied.

## 18. Remaining limitations

The implementation is local, but the full acceptance/validation gate is not clean:
the two existing regression concerns above and the unmeasured performance scope
remain. Uncertain test submissions require secured provider/audit investigation;
there is no automatic reconciliation or replay. Test receipts show acceptance,
not verified inbox delivery. A test cannot verify genuine Shopify trigger,
purchase-exit or customer checkout recovery behaviour. No real test email or
customer email was sent, and no actual end-to-end delivery is claimed.

**Status: Implemented locally. Not committed, pushed or deployed.**
