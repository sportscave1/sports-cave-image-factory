# Automations data handoff fix — 5 October 2026

## Proven root cause

In deployed commit `8447b3f`, `crm_automation_home.arm_section()` treats the
existence of any `[role=listbox]` as an open interaction and defers its refresh
click for another two seconds. The actual authenticated production DOM contains
`#sc-os-search-results[role=listbox][hidden]` even when search is closed. Thus
every home completion controller can defer forever. No Python exception is
required: the initial shell returns while completed query results remain unread.

Read-only production reproduction: cold navigation displayed loading in all
three sections. Changing search and then restoring the original search consumed
the original table results, showing four rows including the live Reminder 1.
KPI/activity remained loading because their fragments had not rerun.

The regression test extracts the actual controller from commit `8447b3f` and
runs it with that hidden listbox: **zero clicks over 60 seconds**. The corrected
visibility predicate produces one refresh click. The old fixture lacked the
OS top-bar hidden listbox and consequently missed this failure.

This is not specific to invalid abandoned-checkout content. Publishing/cold cache
invalidation exposes the missed wakeup when the first identity read does not
finish inside its former 50ms opportunity. Empty/warm/fast fixtures can mask it.
The available evidence does not prove publishing was the only possible trigger.

Two additional handoff defects were reproduced locally:

* `accepted_publication()` iterated a wrapped `[rows]` secondary metrics payload
  as flat rows, raising TypeError. The redundant cache mutation is removed.
* An old resolved publication response could settle a newly accepted request
  during refresh. Publication invalidation now clears that pending read state;
  only READY results for the expected job can update its accepted status.

No production data-specific serialization defect, stuck worker, or session
generation mismatch was found as the cause of the observed permanent loading.
No failed SQL response was observed. Exception masking was not the primary cause.

## Production inspection (read-only)

Reminder 1 ID: `76784f53-7878-40cc-85e4-ba60c2ea835a`.

* Status ACTIVE, trigger abandoned, revision 39, published version 1.
* Activated/updated: `2026-10-05 06:01:41.284889+00`.
* Config is an object; steps an array with one step. Config keys: draft, format,
  revision, published, published_at, published_version.
* Publication metadata is null; this is an earlier published version, not a
  pending async publication. The publish job table is empty.
* Step references template `634132dc-7fcc-5603-8274-8e72bdf84846`, version 1;
  that immutable version exists.
* Four visible automations; one additional deleted legacy row is excluded.
* Zero enrollments and automation sends; 9,002 delivery events in the wider CRM.
  Zero automation sent/activity data is legitimate and must settle to zero/—.
* Actual version ledger is `crm_template_versions`; actual publication queue is
  `crm_automation_publish_jobs`, not the conceptual names in the request.
* EXPLAIN ANALYZE of the identity projection: execution 2.584ms, planning 1.234ms,
  four rows, no joins. Activity inspection found no blocked/idle-in-transaction
  session at the observation time. No new index is justified by this query.

## New lifecycle

Critical list: one direct, limited identity/status SELECT, with transaction-local
1500ms statement timeout and 500ms lock timeout. The existing connection setup
retains its bounded eight-second connection timeout. IDs/dates are normalized;
publication null becomes an empty object. An eight-entry, 30-second cache keeps
last-good rows; failures expose Retry. The list never submits a Future or loads
checkout/customer/provider/metric data.

Secondary metrics, KPI and activity retain the existing bounded two-worker,
six-operation executor. Explicit NOT_STARTED/LOADING/READY/ERROR/TIMED_OUT phases
separate empty results from pending reads. Home reads have a 20-second watchdog,
terminal error/timeout states and explicit Retry. Older verified values remain
visible. Timer state and metadata are bounded and disposed with read entries.

Native scoped Streamlit fragments check pending secondary results every two
seconds; publication uses three seconds only while Publishing. A settlement
rerun unregisters the corresponding timer. A later interaction that expires a
cache registers a new bounded completion refresh. Settled home has no recurring
timer. The main table uses cached metrics only; metric loading/retry belongs to
its separate region. Detailed analytics keeps its existing lazy architecture;
its menu guard now ignores invisible menus.

Safe lifecycle logs cover READ_START, READ_REUSE, READ_COMPLETE, READ_ERROR,
READ_TIMEOUT, RESULT_CONSUMED and RERUN_REQUESTED. Metadata includes read type,
hashed key, Future identity, generation, elapsed time and result count; no search
text, customer emails, credentials or rendered content is logged.

## Verification

* 91 SQL-backed/unit Automations tests passed, including EMPTY → first abandoned
  draft → queued publication → actual worker validation → cold identity/KPI/
  activity reads. This test confirms no automation send was created.
* 79 broader checkout-preview, live-send/trigger and Campaign home/cache tests
  passed. No real providers were called or written to.
* 165 real browser assertions passed at 1920, 1366, 750, 390 and 320: five states,
  cold loads, browser reload, synthetic success/failure transitions, no overflow,
  and isolated counts/activity/metrics exceptions with Retry and no private text.
* Before/after hidden-listbox controller comparison and controller serialization,
  acknowledgement, dialog-resume/navigation-disposal checks passed.
* Fresh Python process with persisted local live row: first useful browser row
  1021ms including browser/assets startup. Identity fixture query around 30–60ms.
  Full cold/reload secondary settlement generally around 2.5–2.8 seconds.
* Idle 60 seconds: queries 8 → 8, Futures 4 → 4, pending 0 → 0, external requests 0.
  Ten leave/return cycles: queries 10, Futures 4, pending 0. The two extra queries
  were cache revalidation during navigation, not idle polling.
* Local durable publish acceptance measured 22.2ms in the final SQL suite.
* Python compilation, JavaScript syntax, diff whitespace and canonical Render
  topology checks passed.

## Exact files for this fix

Production code:

* crm_automation_home.py
* crm_automation_home_data.py
* crm_automation_home_read.py (new)
* crm_automation_read_cache.py
* crm_automation_ui.py

Tests/fixtures:

* tests/test_crm_automation_loading.py (new)
* tests/test_crm_automation_loading_ui.cjs (new)
* tests/test_crm_automation_loading_idle.cjs (new)
* tests/test_crm_automation_hidden_listbox.cjs (new)
* tests/fixtures/crm_automation_loading.py (new)
* tests/fixtures/crm_automation_loading_server.py (new)
* tests/test_crm_automation_refresh_controller.cjs
* tests/test_crm_automation_stability.py
* tests/test_crm_automation_publication.py
* tests/test_crm_automation_ui.py

Documentation: docs/AUTOMATIONS_LOADING_FIX.md.

No migration or environment change is required. No production automation,
customer, subscription, email, or database row was mutated. Existing live-version
replacement safety, durable publication, worker validation and sending rules
remain intact. No unrelated application code was changed for this fix.

The fix is locally verified and ready for selective deployment, followed by a
fresh authenticated production session check. It has not been committed, pushed,
or deployed. The workspace also contains unrelated pending security work and
earlier concurrent test edits; those must not be included accidentally.
