# Automations stability audit — 5 October 2026

## Scope and outcome

Local changes only. No commit, push, deployment, production publication, email,
Shopify write, webhook registration, Render configuration change, or schema
migration was performed. Synthetic SQL publication tests activate only local
fixture versions and never invoke a mail transport.

Confirmed UI reliability faults were corrected. A Windows desktop process exit
was **not reproduced or root-caused**; do not describe that symptom as fixed.
The local regression/stress results support review of the scoped changes, not a
claim that every reported production/native crash has been eliminated.

## Evidence and causes

- Revision `43b37ea` has two one-second Home fragments, a three-second publication
  fragment, and independently scheduled hidden refresh buttons. Pending table
  wakeups start at 100 ms, with 200/250/500 ms retry paths. The pre-existing local
  work also added a third one-second metrics fragment. These overlapping owners
  can issue fragment requests together; browser testing of slow reads reproduced
  dropped completion updates. Repeated retries compensate by adding more work.
- Analytics nested fragments inside a dialog (itself a Streamlit fragment), with
  a 20-second checkout timer and two 30-second secondary instances, produced
  `StreamlitDuplicateElementKey` during repeated open/filter/navigation. Server
  logs verified the exception; it was not inferred from screenshots.
- The shared Campaign cache was already bounded, not an unlimited executor:
  four threads, twelve outstanding jobs and twenty-four entries per state. But
  Automations competed in that pool, retained large raw query results in Futures
  and session state, and had no navigation disposal for those reads.
- Publication status previously performed its database query on the UI thread.
  The database connector has an eight-second connection/statement timeout, so
  even a small status query could block an interaction on a slow connection.
- The Automations route lacked an unexpected-error/import boundary. Analytics
  panel rendering errors could escape their section rather than preserve the OS
  shell. Added boundaries do not intercept Streamlit control-flow BaseExceptions.
- No Home provider dependency was found in this revision: zero Shopify/Resend/
  Dropbox/Meta calls before and after. Existing activity labels use customer IDs
  where no local name is available; no customer-provider scan was added.
- No connection leak was identified: Store.db uses context-managed connections.
  No long publication transaction surrounds remote validation/rendering; the
  existing worker prepares outside its short final publication transaction.

### Process-close evidence

Read-only Render sampling around 07:01–08:01 UTC showed roughly 160–271 MB RSS
against a 2 GB memory limit, with low CPU. A 07:32:50 ASGI exception was an
unrelated Wall Preview upload `ClientDisconnect`; subsequent health checks were
200. The later shutdown followed the recorded deployment/pre-deploy sequence.
Those observations do not establish an Automations OOM or spontaneous restart.
Local Windows Application error events for the previous two days showed no
matching Sports Cave/WebView2 crash. The available desktop helper log had only
older July startup errors. Native WebView2 was not driven by the browser tests.
Actual desktop crash evidence remains necessary to identify that reported exit.

## Implemented architecture

- Home retains its bounded identity/status read model, separate from metrics.
  A cold indexed identity query may finish within a **50 ms maximum wait**;
  slower work continues asynchronously with a scoped one-second wakeup. This
  does not make the dashboard queries synchronous or wait for analytics.
- No `run_every` server timers remain in Home or Analytics. Four Home section
  controllers use 60-second table/metric and 180-second KPI/activity schedules.
  A fifth status controller exists only for visible Publishing rows, at three
  seconds, and stops at a terminal state. No full-page timer is used.
- All background controller clicks share one in-flight gate. A matching render
  acknowledges the request. Pause during dialogs/menus/hidden tabs; resume after
  a long pause. Removed owners stop timers. Missing-button retries are bounded;
  no 250/500 ms click retry loops remain. Stale request gates expire safely.
- Analytics has **one refresh owner: the dialog**, rather than nested child
  fragments. Definition/list reads have a maximum 50 ms readiness opportunity;
  cold pending completion wakes at one second, normal dialog refresh at thirty
  seconds. Its single selected countdown remains client-side; no Python
  one-second countdown timer was added.
- Automations-only read pool: two running jobs, four additional queued jobs,
  eight entries per state. Same pending key reuses its Future. Campaign pool,
  cache, sending and refresh implementation are unchanged.
- Large trusted internal query lists are compressed before retention; each
  compressed entry is capped at 1 MiB. Future and resolved cache reuse the same
  compact payload. Private bytes never leave the server and no external input
  is unpickled. Exception frames are cleared after safe class-only logging.
  This bounds retained cache data, not arbitrary future database cardinality;
  very large ranges beyond this budget retain last-good data and fail locally.
- Navigation cancels queued UI work, disposes large Analytics state and keeps
  small completed Home projections for warm reopening. Running reads finish
  under the existing DB timeout and cannot write session state. Draft guards
  run first; blocked navigation does not discard unsaved content.
- Stale-while-revalidate retains validated previous values on pending/error;
  backend state always replaces optimistic Publishing. Existing immutable
  revisions, idempotency, worker retries and active-version replacement remain
  unchanged. Publishing still does not send or enroll customers.
- Route-specific import/render guard and panel guards log only stage/error
  class and keep the shell/navigation available. No global UI fade was added;
  existing preview-specific anti-dimming treatment is unchanged.

## Freshness and worker decisions

| Data | Policy |
| --- | --- |
| Accepted publication / pending status | Immediate handoff, three-second indexed async status query; stop at terminal state |
| Definitions/status on Home | One bounded identity query, explicit mutation invalidation, 60-second background refresh |
| Table send/event/conversion counters | 60-second cache |
| KPI/revenue/prior-period/activity | 180-second cache; cached values retained |
| Detailed checkout list | On explicit Analytics opening/range choice; 60-second cache |
| Detailed metrics/activity | On demand, 180-second cache |
| Preview checkout | Existing editor-only context and finite initial-lookup polling retained; absent on Home |
| Countdown | One client interval for selected checkout; worker remains authoritative |

No new worker/service/projection table was introduced. Existing persisted ledgers
and the lightweight Home projection already support the needed read model;
non-live aggregate reads are now bounded/cached rather than repeatedly queried.
The existing durable publication worker remains the owner of expensive publish
validation. A further worker-maintained aggregate snapshot would need production
query-volume evidence; it was not added speculatively.

## Measurements

Synthetic loopback PostgreSQL/PGlite, mocked Shopify, headless Edge, no provider
transport. tracemalloc and process working-set measurement enabled for stress.

| Check | Result |
| --- | --- |
| Home SQL cold | 8 queries: identities 1, row metrics 1, counts 1, summary 4, activity 1 |
| Home warm | 0 new SQL while valid caches remain |
| Home idle, settled 60 seconds | 0 additional SQL, 0 providers, 0 pending Futures; 146 → 2 rerun requests |
| Analytics cold abandoned checkout | 4 reads: definition, list, report, activity; warm reuse avoids them |
| All-time rendering | 5,000+ rows, native virtualized canvas, no per-row buttons/timers |
| Indexed identity SQL EXPLAIN ANALYZE | 0.352 ms execution in local fixture |
| Row-metrics SQL EXPLAIN ANALYZE | 0.585 ms execution in local fixture |
| Publish durable acceptance, unit fixture | 6.4 ms |
| Publish browser command → interactive Home | 900–960 ms across validated five-width runs |
| Useful Home row on warm backend | 551 ms |
| Analytics shell | 126–363 ms across validated runs |
| Analytics table after final bounded-read change | 158–679 ms across validated runs |
| Warm Analytics reopen | 223–459 ms |
| All-time scroll input | 126 ms, including deliberate 100 ms test observation |
| Add to flow | 233–372 ms; local durable journey only, no inline email |

Historical comparison: the `43b37ea` cold fixture visit took 4,085 ms; an early
new cold fixture visit took 3,622 ms. Those include Python imports and synthetic
seeding, and are **not** production first-paint measurements. Warm 551 ms is not
presented as a directly comparable cold speedup. An initial cold Analytics run
failed its 2.5-second budget at 2,698 ms; the final recheck was 679 ms.
An early baseline idle sample started with pending reads, so its four additional
queries were startup completion. A later settled baseline also made zero SQL
queries. A separate protocol-decoded comparison measured **146 rerun_script
requests before versus 2 after** in sixty seconds (98.6% fewer).
This is not evidence of an idle database-query storm; timer/message churn and
nested-fragment errors were the verified UI concerns. Configured timer counts
are distinguished from measured query executions.

### Final stress measurements

| Stage | RSS bytes | Python allocations bytes | Threads | Retained Futures | Pending |
| --- | ---: | ---: | ---: | ---: | ---: |
| Warm initial | 150,884,352 | 501,934 | 15 | 5 | 0 |
| Idle 60 s | 150,884,352 | 533,363 | 15 | 5 | 0 |
| 10 workflow cycles | 159,531,008 | 1,579,645 | 10 | 12 | 0 |
| 25 workflow cycles | 159,645,696 | 1,620,830 | 10 | 12 | 0 |
| 50 workflow cycles | 159,567,872 | 1,665,030 | 10 | 12 | 0 |
| 100 leave/return pairs | 159,080,448 | 549,600 | 10 | 5 | 0 |

RSS plateaus after warm initialization; Python allocation growth is small and
falls on disposal. Provider count was zero on Home/idle. Explicit editor visits
made one mocked checkout-preview lookup each (50 visits → 50 calls); those are
not Home calls. No browser page errors, duplicate-widget errors or process exit
occurred in the final stress log. This proves the local browser fixture, not
native Windows/WebView2 or production Supabase pool behavior.

## Validation

- 95 focused Automations/publication/checkout/cache/UI tests passed.
- 92 worker, boundaries, preview, diagnostics, tracking and Resend safety
  regressions passed.
- 68 Campaign cache/Home/history/first-paint/cleanup tests passed on a clean
  fixture. A mixed-database run had one bounce-cohort assertion failure;
  it passed unchanged on clean data. No Campaign code was altered to mask it.
- Publish browser success/failure/retry/exact-snapshot checks at 1920, 1366,
  750, 390, 320; no overflow or KPI/activity replacement from status polling.
- Analytics browser checks at the same five widths; the recheck waits for the
  filtered projection before opening a row menu (an earlier attempt clicked the
  previous projection during search refresh); filtering, all-time scroll,
  recovery/ineligibility gates, selected Add to flow and immediate journey state.
- 50 Home → Analytics → Editor → Home cycles, then 100 leave/return pairs
  (200 transitions); no crash, blank screen or localized error in final run.
- Deterministic execution of the actual controller: simultaneous-click
  serialization, acknowledgement, long-dialog resume and navigation disposal.
- Injected section and route exceptions produce safe localized errors; unsaved
  draft navigation guards preserve content and cancellation cleans queued work.
- Modified Python compilation, JavaScript syntax, topology validation and
  whitespace diff checks. No new index/migration was justified by local plans.

The full repository discovery run was not repeated for this audit; these are
relevant isolated suites, not a claim that every repository test passes.

## Changed files

Runtime:
- crm_automation_home.py
- crm_automation_analytics_ui.py
- crm_automation_ui.py
- crm_automation_read_cache.py (new, scoped read/cache boundary)
- crm_navigation.py (Automations-only cleanup branch)
- crm_page.py (Automations-only import/render boundary)

Tests/docs:
- tests/fixtures/crm_automation_preview.py
- tests/fixtures/crm_automation_stability_baseline.py
- tests/test_crm_automation_stability.py
- tests/test_crm_automation_stability_ui.cjs
- tests/test_crm_automation_refresh_controller.cjs
- tests/test_crm_automation_publication.py
- tests/test_crm_automation_home_reactivity.py
- tests/test_crm_automation_ui.py
- tests/test_crm_checkout_analytics_ui.cjs (pre-existing local test adjustment retained)
- docs/AUTOMATIONS_STABILITY_AUDIT.md

Pre-existing docs/AUTOMATION_HOME_PERFORMANCE.md was retained, not used as the
new audit's result. Orders/Fulfilment/Edition Ops/Ads/SEO/Wall Preview/Product
Uploads/Mockups code, Render topology, database schemas and live data were not
modified. Shared CRM edits are route-specific; Campaign regressions are listed
above.
