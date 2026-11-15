# Abandoned checkout email progress table — 9 October 2026

Implemented in the existing table component and analytics read path. The posting engine, email worker, publishing rules, suppression rules and delivery/idempotency controls are unchanged by this task.

## Interface

- Selection checkbox, **Customer**, **Created**, and dynamic **Email 1…N** columns replace the visible checkout reference, region, recovery-status and time-to-send columns.
- Verified customer names retain the existing email/Guest fallback; numeric identifiers never become names. The customer button opens the existing checkout details using the stable hidden checkout key. IDs and history remain available in details and storage.
- Created dates use the user's existing OS timezone preference; the full timestamp and timezone appear on hover.
- Warm-white background, restrained gold countdowns, text-only states, 34 px standard rows, sticky customer/header cells, and internal horizontal/vertical scrolling. The embedded frame is constrained to its parent at narrow widths.
- Search, the existing Incomplete filter, paging, selection across pages, details, Refresh checkout details, Add to flow, asynchronous request feedback, and explicit recovery retries remain available. Add to flow is secondary.
- A customer with separate checkout identities retains separate rows. Emails never create duplicate rows; merging distinct checkouts would lose recovery identity and is deliberately avoided.

## Published columns and backend truth

The existing cursor-paged query reads at most 51 base checkout records to display 50 plus a next-page indicator. It joins frozen journeys, send receipts, provider events, evaluations and recovery requests in one database call; it does not query Shopify or fetch each row separately. Published column metadata is projected to IDs, names and enabled flags without transferring email documents. It uses the current published snapshot, older successful publication snapshots when necessary, and existing compiled steps as the legacy fallback. Editable drafts do not control table columns.

Cells match published **step IDs** against the selected enrollment's frozen steps, never against another flow's send index. Publishing an additional or reordered email does not rewrite an existing enrollment. A step absent from that frozen version is **—**. Disabled published steps show **Disabled** for new/non-enrolled rows; an already enrolled enabled step continues to show its actual frozen schedule, with that distinction explained on hover. Removed emails disappear from current published columns; their receipts remain in checkout details and backend history.

**Sent ✓** requires both an ACCEPTED marketing-send state and a provider message ID for the corresponding enrollment and step. Delivery timestamps remain separate in receipt details. Queued, claimed and uncertain sends cannot produce a Sent label. Deferred send deadlines are included in both ordinary and manual-recovery reads; the later persisted deadline controls the countdown.

Other states include Waiting, Due, Processing, Confirming, Paused, Failed, Suppressed, Purchased, Contact needed, Qualifying, Awaiting worker and evaluated Not in flow, with reasons on hover. A verified purchase stops outstanding reminders while keeping earlier acceptance receipts visible. A completed journey missing acceptance evidence shows Unconfirmed rather than invented success.

## Live updates and performance

One shared browser timer updates visible countdown text each second. It uses a server UTC anchor plus the browser's monotonic performance clock, so changing the browser wall clock does not move the deadline. It never sends email or advances a journey. Reopening the page rebuilds countdowns from persisted deadlines.

While visible, the component requests a status refresh no more than once every 15 seconds. The existing asynchronous read cache has a 12-second TTL for checkout pages and reuses in-flight reads. Updates stay inside the existing Streamlit fragment. Completed reads replace only changed text where possible; unchanged table structure, checkbox nodes, focus and scroll positions survive. Existing manually requested recovery operations retain their separate bounded batch-status polling.

Hidden/offscreen tables suspend ticking and polling. Timers, listeners and observers are cleaned up on unmount. Backend errors or snapshots over 45 seconds old display an explicit delayed-status message; deadlines reaching zero remain Due, never Sent. Existing database connection/statement timeouts remain in force. Initial loads now retry when the shared read pool is temporarily full instead of being left without a refresh signal.

Measured local component results: Chromium, 50 rows, 30 repeated render samples after warmup. The new table displays five email columns.

| Measurement | Before | After |
|---|---:|---:|
| Median repeated component render | 3.8 ms | 0.3 ms |
| Standard row height | 37 px | 34 px |
| DOM elements | 570 | 622 |
| Backend requests from countdown ticking | Not applicable | 0 |

The update improvement comes from retaining the table instead of rebuilding every row. More email cells increase the DOM count; no DOM-count reduction is claimed. These are the final reproducible run's values against baseline commit `675342a`; an earlier run measured 3.2 ms / 0.2 ms. This benchmark measures local component updates, **not production initial loading, database latency or email delivery speed**. Production timings remain unmeasured. Evidence: `checkout-flow-evidence/component-benchmark.json`, desktop and narrow screenshots in that directory.

## Automatic enrollment and safety

Disposable SQL tests exercised the existing Shopify verification/reconciliation → automatic enrollment → persisted deadline → mocked provider acceptance → next-step scheduling → purchase cancellation path without clicking Add to flow. Duplicate advancement/submission did not duplicate sends. Existing webhook deduplication, historical cutoff, consent, suppressed recipients, uncertain outcomes, throttling and immutable-publication tests also passed.

No new worker/enrollment defect was confirmed in this task, so the worker was not changed. The existing table still lists Shopify's verified abandoned-checkout mirror; ordinary active carts are not newly added to this list. The current engine treats Shopify abandonment as qualification and does not impose another invented wait. Qualifying applies when the available record has not yet passed that boundary; eligibility remains a worker decision.

No new schema migration, webhook registration, automation publication, production API mutation or real customer email was performed by this task. Deployment requires separate authorization and the existing worker/capability configuration. Earlier email-reliability deployment/webhook limitations remain documented in `EMAIL_RELIABILITY_REPAIR_2026-10-09.md`; this UI change does not resolve infrastructure problems or authorize historical backlog enrollment.

## Verification

- Final focused regression: **394 tests passed in 65.203 seconds**, against a fresh loopback PGlite/PostgreSQL fixture with mocked Shopify/Resend.
- Three browser suites passed: component/countdown behavior; existing operational actions; actual Streamlit fragment/cache refresh and pagination. External browser network access was blocked. Checked desktop/laptop/narrow widths including 1440, 1366, 1024, 750, 390 and 320 px across the suites.
- Verified live ticking without backend events, clock drift, reload from persisted UTC, acceptance/next-step transition, dynamic fourth/fifth/sixth columns, old frozen versions, sticky scrolling, table-node preservation, checkbox/detail events, hidden/unmounted cleanup, unsubmitted Search text surviving a real periodic fragment refresh, and selections across server pages.
- The first broad focused run passed 392/393: the existing `test_pause_prevents_entry_claim_and_submission_resume_preserves_wait` immediate claim assertion failed intermittently. It also failed in one isolated run, then passed a diagnostic native-suite run, three isolated repeats, and the final full run. Its application code and assertion were not weakened or changed. The timing sensitivity remains worth monitoring.
- This task did not re-run all unrelated CRM discovery tests. The known broader-suite failures recorded in the earlier reliability report are not claimed fixed.

Reproduce:

```powershell
.venv/Scripts/python.exe scripts/run_email_reliability.py
node tests/test_crm_checkout_progress_ui.cjs
.venv/Scripts/python.exe scripts/test_checkout_browser.py
```

Browser commands require Playwright available on NODE_PATH and local Chrome. The browser runner owns and stops its synthetic Streamlit servers. All fixtures are disposable; no production credentials are used.

## Files changed for this table task

Application:
- `components/crm_checkout_table/index.html`
- `crm_checkout_progress.py` (new projection)
- `crm_checkout_analytics.py` (read-only query enrichment; earlier sync optimizations preserved)
- `crm_checkout_enrollment_requests.py` (read-only receipt metadata enrichment)
- `crm_automation_analytics_ui.py`

Tests/fixtures:
- `tests/test_crm_checkout_progress.py`
- `tests/test_crm_checkout_progress_ui.cjs`
- `tests/test_crm_checkout_live_ui.cjs`
- `tests/fixtures/crm_checkout_live.py`
- `tests/test_crm_checkout_operations_ui.cjs`
- `tests/fixtures/crm_checkout_operations.py`
- `tests/test_crm_automation_timing.py`
- `tests/test_crm_checkout_reliability.py`

Tools/evidence: `scripts/test_checkout_browser.py`, extended `scripts/run_email_reliability.py`, this report, and `docs/checkout-flow-evidence/*`.

During this task, another actor advanced repository HEAD from `675342a` to `72cabec`, incorporating most previously uncommitted work. This task did not issue commit, push or deployment commands and preserved that external commit. Later fixture corrections, final read-pool handling and this report remain local unless changed externally.
