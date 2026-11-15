# Automations V5 — local navigation and first-paint audit

Implemented locally on 10 October 2026. No commit, push, merge, deployment,
production database write, publication or email send was performed. The existing
primary Render service remains `sports-cave-os` (`srv-d8kl4on7f7vs73dvavv0`).

## Scope and evidence boundaries

The browser harness executes the production sidebar, shared route functions and
top bar, and the actual `crm_page.render_page`, Automations overview, Flow,
composer and `AutomationStore` SQL paths. The database is disposable PGlite over
loopback HTTP. Authentication supplies a synthetic administrator; Shopify,
provider settings and unrelated OS startup services are isolated. External browser
requests and provider transport are blocked. This is a real routed CRM page test,
not a mocked destination body, but it is not an authenticated production benchmark
or a measurement of the entire application's startup services.

The synthetic definitions cover 1, 3, 6 and 12 real draft email stages. The
customer/order/send ledger starts empty. The production analytics SQL executes,
but this does not reproduce a production-scale ledger workload. Mock rendering
settings also exclude production compliance/branding settings reads from these
query totals. The controlled-latency tests add delay to real fixture SQL calls;
the read-only production logs are the evidence for live read costs.

The before snapshot is the six relevant modules copied from the working tree at
the start of V5, including existing local V4 work. It is not the production Git
revision. Shared dependencies outside those modules use the current working tree;
the updated history bridge is not exercised by baseline history assertions. Before
and after use separate owned fixture processes sequentially, the same database
transport, browser channels, viewport and six navigation attempts per stage count.

Click-to-ready starts at the browser's trusted click. Wall-clock locator timings
also include Playwright scrolling and actionability waits and are retained in the
raw evidence. Paint samples use `requestAnimationFrame` and visible DOM checks;
they are browser observations, not compositor or Event Timing API measurements.
Usability waits require all stage Edit buttons and Save draft, or real overview
rows plus the search input, or the real Subject input. Optional analytics are
measured separately where an observed terminal paint exists. Missing measurements
are not treated as zero. No authenticated production click measurements were
collected, so fixture improvements must not be described as proven production
speed improvements.

## Proven causes and implemented changes

1. Normal overview links navigated the whole browser document and re-established
   the Streamlit session. The links now retain a real bookmarkable `href`, while
   ordinary clicks and keyboard activation use supported native query-bound
   widgets in a workspace fragment. Modifier clicks retain normal new-tab behavior.
   The existing shared history bridge handles Back/Forward and compares both
   automation and email step. A superseding click, history event or sidebar click
   invalidates older deferred native commits. A 25 ms event-flush window reapplies
   the latest input values if an earlier widget response replaced them; it keeps
   the latest same-page URL and commits through native widget blur events.
   Subview history does not start an uncleared page overlay. Sidebar activation
   paints the existing gold pending treatment immediately without changing
   native button classes or consuming React's route event.
2. Overview background settlement reran the entire OS. Counts, attribution,
   delivery, publication status and recent activity now consume results in their
   own fragments. One-shot native wakeups are serialized during ordinary refresh,
   yield to interaction, ignore hidden/inert listboxes, stop on unmount and have a
   finite retry budget. A final settlement consumes terminal read states after a
   dialog held the normal budget. Optional reads have a 20-second terminal deadline.
3. The generic CRM header/cache setup preceded Automations. The existing safe
   automation workspace now branches before that unrelated work. The essential
   list submits identity rows before optional analytics. The bounded identity
   cache and query remain scoped to the session and existing invalidation paths;
   analytics, Shopify lookups and thumbnails are not prerequisites for rows.
4. Flow and its toolbar could independently retrieve/validate a full definition.
   A render-scoped normalized snapshot is reused during one display render and
   invalidated by database operations. Warm opens reuse a session display row only
   after a fresh `updated_at` query for that exact identity. Changed, missing,
   legacy and uncached records take a full read. Mutations retain their independent
   fresh reads and optimistic revision checks; immutable publication selection
   does not use this display shortcut.
5. Flow-to-editor transitions now use the same workspace route, including the
   email step in the URL. Selecting or adding a composer email updates that route.
   The fragment checks the current account and permission before rendering. It
   flushes edits before a route change; a failed save restores the previous URL
   and retains the editor. Unknown email deep links show an error rather than
   silently selecting a different email. Successful route changes clear the prior
   template view, and changing identity clears the prior Flow diagnostics.
6. Closed stage menus no longer build every settings form, delete confirmation
   and detail-metric placeholder during initial Flow construction. Supported
   `st.popover(on_change='rerun')` state builds those controls when the menu opens;
   that event reruns the owning sequence fragment and validates definition
   freshness. Visible stage metrics remain present with every menu closed.
   Save, duplicate, move and add are checked in both browsers after this change.
   This uses Streamlit's documented [lazy popover execution](https://docs.streamlit.io/develop/api-reference/layout/st.popover)
   and the installed 1.58 API; it adds no custom menu polling.

There is no new general-purpose router, visual redesign, sending-engine policy
change or publication migration. Existing Flow controls, eight metric definitions,
filters, search, sorting, pagination, consent, suppression, purchase exit and
checkout protections remain on their existing paths.

## Measurements

All timings below are local trusted-click-to-ready measurements. p95 uses the
nearest rank; six samples per group make each group p95 its maximum. The aggregate
mixes browsers and stage counts, so the per-group table is also required. Baseline
failed transitions are excluded from successful timings and listed separately.

| Journey | Before p50/p95 | After p50/p95 | Median improvement |
|---|---|---|---|
| OS → Automations | 653.5 / 929 ms (n=8) | 591.5 / 690 ms (n=8) | 9.5% |
| Overview → Flow | 1286 / 1568 ms (n=48) | 550 / 1397 ms (n=48) | 57.2% |
| Flow → Overview | 667.5 / 1021 ms (n=48) | 406 / 498 ms (n=48) | 39.2% |
| Flow → Edit Email | 686 / 1151 ms (n=45) | 438.5 / 996 ms (n=48) | 36.1% |
| Editor → Flow | 1022 / 1375 ms (n=48) | 531.5 / 880 ms (n=48) | 48% |

The OS entry is a cold **session route** with authentication already supplied by
the fixture. It is not a fully cold process or real login. Flow first opens are
the first attempt per group; repeated opens are attempts 2–6. Resource/preview
caches persist within each owned server, so later browser groups are not globally
cold. Baseline editor failures reduce the successful sample count.

| Browser / stages | Before repeated Flow p50/p95 | After repeated Flow p50/p95 | After first Flow | After Back p50/p95 |
|---|---|---|---|---|
| chrome-1 | 1049 / 1132 ms (n=5) | 318 / 403 ms (n=5) | 720 ms | 281 / 394 ms (n=6) |
| chrome-3 | 1384 / 1500 ms (n=5) | 554 / 781 ms (n=5) | 689 ms | 443 / 498 ms (n=6) |
| chrome-6 | 1382 / 1568 ms (n=5) | 510 / 726 ms (n=5) | 1175 ms | 381 / 457 ms (n=6) |
| chrome-12 | 1516 / 1774 ms (n=5) | 819 / 1304 ms (n=5) | 1397 ms | 409.5 / 432 ms (n=6) |
| msedge-1 | 1041 / 1161 ms (n=5) | 371 / 403 ms (n=5) | 687 ms | 408.5 / 453 ms (n=6) |
| msedge-3 | 1391 / 1497 ms (n=5) | 503 / 718 ms (n=5) | 862 ms | 455.5 / 515 ms (n=6) |
| msedge-6 | 1423 / 1497 ms (n=5) | 620 / 778 ms (n=5) | 1485 ms | 400.5 / 543 ms (n=6) |
| msedge-12 | 1076 / 1522 ms (n=5) | 1149 / 1282 ms (n=5) | 1560 ms | 440.5 / 484 ms (n=6) |

| After journey / observed phase | p50/p95 |
|---|---|
| OS → Automations / accepted | 485 / 547 ms (n=8) |
| OS → Automations / shell | 537 / 613 ms (n=8) |
| OS → Automations / first | 537 / 613 ms (n=8) |
| OS → Automations / all | 570.5 / 653 ms (n=8) |
| OS → Automations / optional | Not observed |
| Overview → Flow / accepted | 260.5 / 401 ms (n=48) |
| Overview → Flow / shell | 274 / 493 ms (n=48) |
| Overview → Flow / first | 401 / 600 ms (n=48) |
| Overview → Flow / all | 480.5 / 672 ms (n=48) |
| Overview → Flow / optional | 479 / 650 ms (n=40) |
| Flow → Overview / accepted | 228 / 291 ms (n=48) |
| Flow → Overview / shell | 374 / 441 ms (n=47) |
| Flow → Overview / first | 378 / 456 ms (n=47) |
| Flow → Overview / all | 378 / 456 ms (n=47) |
| Flow → Overview / optional | 385 / 473 ms (n=47) |
| Flow → Edit Email / accepted | 235 / 413 ms (n=48) |
| Flow → Edit Email / shell | 382 / 612 ms (n=48) |
| Flow → Edit Email / first | 395.5 / 612 ms (n=48) |
| Flow → Edit Email / all | 395.5 / 612 ms (n=48) |
| Flow → Edit Email / optional | 395.5 / 612 ms (n=48) |
| Editor → Flow / accepted | 258 / 302 ms (n=48) |
| Editor → Flow / shell | 332.5 / 469 ms (n=48) |
| Editor → Flow / first | 339 / 471 ms (n=48) |
| Editor → Flow / all | 447 / 589 ms (n=48) |
| Editor → Flow / optional | 447 / 589 ms (n=48) |

Sidebar feedback: 12.2 / 12.7 ms (n=24). Flow-link busy feedback: 27.25 / 39.9 ms (n=48).
OS entry phases and readiness come from a dedicated paired pass that waits
for the shared opaque loading overlay to clear. Original navigation-run OS
DOM-only observations are preserved but do not supply the reported OS timings.
`accepted` observes the server-rendered route marker matching both URL fields;
it combines transport, route processing and the synthetic account permission gate.
Authentication, imports, toolbar construction and render reconciliation cannot be
separated into independent wall-clock phases by this instrumentation. `shell`
includes the truthful opening status; `first` is the first stage/row/input;
`all` observes all Edit buttons for Flow, while ready additionally waits for
Save draft. Optional observations can precede ready and do not measure every
provider/preview task. The raw evidence retains missing phases explicitly.

| Journey | Before document navigations / new WebSockets | After document navigations / new WebSockets | After app starts / completed renders |
|---|---|---|---|
| OS → Automations | 0 / 0 | 0 / 0 | 16 / 16 |
| Overview → Flow | 48 / 48 | 0 / 0 | 0 / 0 |
| Flow → Overview | 0 / 0 | 0 / 0 | 0 / 0 |
| Flow → Edit Email | 0 / 0 | 0 / 0 | 0 / 0 |
| Editor → Flow | 0 / 0 | 0 / 0 | 0 / 0 |

Warm sidebar → overview entry: before 771 / 1468 ms (n=16); after 542.5 / 911 ms (n=16).
These are two subsequent real Dashboard → Automations entries per browser/stage group.

Background overview settlement over 4.5 seconds: before [3, 3, 3, 3, 3, 3, 3, 3]; after [0, 0, 0, 0, 0, 0, 0, 0] full-app runs.
Before document navigation necessarily restarts the session; the baseline
did not independently instrument every same-document app rerun per action.
The original fixture counter includes interrupted app starts. Dedicated sidebar
instrumentation separately counts starts and completed renders; scoped Flow
transitions have zero starts and therefore zero completed full-app renders.
Browser reload deliberately creates a new document/socket and is
tested separately from route transitions.

Baseline failed transitions: `[{"group": "chrome-6", "journey": "flow_to_editor", "elapsed_ms": 8568.26}, {"group": "chrome-6", "journey": "width_probe_return", "elapsed_ms": 8292.19}, {"group": "chrome-12", "journey": "flow_to_editor", "elapsed_ms": 8524.0}, {"group": "msedge-6", "journey": "flow_to_editor", "elapsed_ms": 8550.72}]`. Recovery waits/reloads are
not counted as successful measurements. Revised transitions all complete.

### Database and connection observations

The following totals cover the entire run, including optional reads, retries,
history/reload checks and width probes. After has extra width navigation checks;
these totals are not matched per-click query counts or a connection speed comparison.
Connection acquisition is the synthetic wrapper factory; BEGIN measures local
lock/HTTP overhead. Neither measures production TCP/TLS or connection pooling.

| Run / operation | Calls | p50/p95 duration |
|---|---|---|
| before / other | 710 | 2.006 / 55.705 ms (n=710) |
| before / identity | 64 | 2.352 / 17.008 ms (n=64) |
| before / definition | 204 | 1.946 / 5.755 ms (n=204) |
| before / freshness | 427 | 1.509 / 20.103 ms (n=427) |
| before / publication | 60 | 7.223 / 80.985 ms (n=60) |
| before / connection_factory | 1337 | 0.002 / 0.003 ms (n=1337) |
| before / begin | 1337 | 2.028 / 57.372 ms (n=1337) |
| after / other | 247 | 1.811 / 25.982 ms (n=247) |
| after / identity | 18 | 2.248 / 17.001 ms (n=18) |
| after / definition | 16 | 1.988 / 14.949 ms (n=16) |
| after / publication | 16 | 42.609 / 55.595 ms (n=16) |
| after / freshness | 216 | 1.45 / 22.583 ms (n=216) |
| after / connection_factory | 477 | 0.002 / 0.003 ms (n=477) |
| after / begin | 477 | 1.796 / 36.21 ms (n=477) |

Within a fresh native display render, the essential definition is read once
and shared with its toolbar/sequence. A warm existing display row requires one
freshness statement instead of another full-definition statement; mutation
paths still verify fresh data. Each uncached overview identity operation uses
one connection and three statements (two local timeout settings and SELECT);
psycopg pipelines those statements on production. Session hits within the
existing 30-second identity TTL use no identity SQL. Counts, delivery, attribution,
recent activity, publication reconciliation and stage analytics remain secondary.
Definition freshness and publication/draft status are still authoritative gates.

The local results show achieved and missed targets directly; do not infer
production target attainment from this table. Large Flow construction and
Streamlit widget transport/reconciliation remain material after the database
read has returned. No isolated profiler result proves a universal framework floor.

## Production read-only observations

The authorised Nathan's workspace was inspected with the Render monitoring
connector, using only logs and metrics for the existing primary service. The
sanitized capture is `automations-v5-evidence/render-read-telemetry.json`.

For the queried 05:00–06:05 UTC window, identity reads took 1,284–1,328 ms;
delivery reads took 5,203–5,316 ms. These logged durations include connection,
query and application work. They are not isolated SQL timings or user navigation
measurements. The maximum sampled five-minute CPU value was about 5.65% of the reported CPU limit, and memory
at about 16.4% of the reported limit. The root HTTP p95 metric returned no samples;
an empty series does not mean zero latency and cannot measure Streamlit WebSocket
interactivity.

Inspection of `Store.db()` and `supabase_backend.connect()` confirms that the
existing production factory opens a fresh psycopg connection for each database
operation. This task reduces unnecessary calls and document reconnection; it does
not introduce a shared production connection pool. The telemetry cannot separate
handshake time from SQL time. The loopback fixture's connection factory merely
constructs an HTTP wrapper, so its near-zero acquisition times must not be used as
production connection measurements. Fixture BEGIN includes local transaction lock
and HTTP costs. A measured, bounded, credential-aware pool remains a separate
potential improvement, requiring genuine PostgreSQL connection measurements.

## Limits and release assessment

| Engineering target | Final local observation | Assessment |
|---|---|---|
| Feedback <50 ms | Sidebar 12.2/12.7 ms; Flow link 27.25/39.9 ms p50/p95 | Met locally |
| Overview shell <150 ms | 537 ms median, overlay-aware | Missed |
| Warm overview usable <400 ms | 542.5 ms median via real sidebar | Missed |
| Cold overview usable <800 ms | 591.5 ms median; 690 ms p95 | Met in this local sample |
| Flow shell <200 ms | 274 ms median | Missed |
| Warm Flow usable <500 ms | 519.5 ms median, n=40; 1,273 ms p95 | Missed |
| First Flow usable <1,000 ms | 1,018.5 ms median, n=8; 1,560 ms p95 | Missed; first per group is not globally cold |
| Back to overview <400 ms | 406 ms median | Missed narrowly |
| No redundant document/socket reconnect | Zero on ordinary Flow/editor transitions | Met locally |
| Optional data nonblocking | Essential controls work during settlement; scoped completion and bounded errors pass | Met locally |
| Cached thumbnails promptly visible | Cache/source regressions and separate successful Chrome previews pass | No V5 readiness timing claim |

Cold overview entry improves modestly in this small sample: median 653.5 →
591.5 ms (9.5%), with p95 929 → 690 ms, n=8 per version. Warm sidebar entry
improves 771 → 542.5 ms median (29.6%), but still misses the 400 ms target.
Both versions still complete two full-app renders per sidebar entry; that
remaining work is unchanged. These fixture samples do not establish production
cold-entry or tail improvements. Flow opening
improves 1,286 → 550 ms median (57.2%); this aggregate includes first opens.
The 12-stage results and variation between browser groups remain visible in the
per-group table. The sample is too small to certify production tail latency.

The production identity-read duration alone exceeds the 800 ms cold-overview
target in this capture. Fast browser feedback and fragment routing cannot erase
that wait. Flow construction and Streamlit delivery/reconciliation also remain
work proportional to stage count. This implementation is not a claim of
Klaviyo/Mailchimp-equivalent production responsiveness or universal target attainment.

The navigation benchmark does not time successful thumbnail rasterization: the
default bundled Chromium renderer is unavailable in that harness, and safe
unavailable states are exercised instead. Separate current-code operation tests
use installed Chrome for previews; existing cache/source safety regressions remain
required. No live publication or real customer send is used for validation.

The known frozen-version versus current-LIVE sending-policy discrepancy remains
unchanged. Its exact pre-existing assertion is classified as an expected failure,
not omitted, fixed by changing policy, or counted as a successful assertion.

The local regression gate passes. Production performance is not certified:
several first-paint and warm-readiness targets remain unmet. Production readiness
additionally requires an explicitly authorised release and
authenticated, read-only production click measurements. No release action or
deployment command is included here.

## Validation and changed files

- The final isolated SQL/navigation/composer gate runs **578 tests**, with **577
  passing and one exact expected sending-policy failure**. There are no other
  failures or errors. It covers sending idempotency, consent/suppression,
  checkout recovery, purchase exit, scheduling, attribution, immutable versions,
  optimistic revisions, permissions, source/cache integrity and authoring.
- Chrome and Edge each complete six overview/Flow/editor round trips for every
  1/3/6/12-stage group. Actual overview ↔ Flow navigation also completes at
  1920, 1440, 1366, 1024, 750, 390 and 320 px. All layout probes report no
  document horizontal overflow. Each group passes Back, Forward and reload.
  Ordinary Flow routes create no new document, no new WebSocket and no full-app
  rerun. Background settlement causes zero full-app reruns, versus three per
  baseline overview case. Four viewport screenshots accompany the raw evidence.
- Controlled tests pass in both browsers for failed identity/definition reads,
  enabled search under 150 ms latency per SQL statement, keyboard Enter,
  modifier-click deep links, rapid clicks, rapid history, and a second click
  after a slow definition read is already in flight. Failed saves retain the
  Subject and restore the prior Flow/editor URL. The 150 ms-per-statement
  overview check takes about 1,080 ms in Chrome and 1,013 ms in Edge, including
  document navigation; it demonstrates usable recovery, not target attainment.
- Separate real-SQL operation checks pass in both browsers for actual stage-menu
  Save, Duplicate, Move down, Add, reload, editor transitions, restored panels
  and analytics. Installed Chrome generates ready neutral previews in that
  harness. No publication, lifecycle or sending UI control is activated.
- Deterministic controller tests pass for serialized ordinary refresh,
  acknowledgement, dialog resumption, one terminal settlement and unmount
  disposal. The previously hidden global-search listbox blocks zero refreshes:
  the historical controller produces zero clicks in 60 seconds, the fixed one
  produces one. Rendering visible row metrics with all stage menus closed is
  covered independently.
- The initial broad run exposed stale assertions for eagerly rendered forms and
  session-only navigation, plus three timing-sensitive failures outside V5.
  Tests now explicitly open the real tracked menu and verify form submission and
  retained configuration; real browsers validate native opening/closing. Those
  unrelated cases pass on recheck, and the complete final gate passes. No failing
  assertion was dropped or reclassified apart from the pre-existing exact policy
  discrepancy. AppTest does not expose popover state as an editable element, so
  its form fixture holds the explicit open state through submission.
- After the final transient template/diagnostics cleanup, all 53 focused unit
  tests pass. The timing fixtures did not open those transient panels; that final
  cleanup adds no SQL or rendering work, but occurred after the timing matrix.
- Render topology validation, relevant whitespace checks and the unchanged
  Email Editor V6 ZIP SHA-256 pass. The existing V6 artifact and prior V4 release
  work remain intact. Owned browser/database processes are cleaned up; the
  Windows harness stops only its recorded process trees.

V5 implementation touches `crm_automation_ui.py`, `crm_automation_home.py`,
`crm_automation_store.py`, `crm_automation_toolbar.py`,
`crm_automation_read_cache.py`, `crm_flow_page.py`, `crm_page.py`, and
`components/sports_cave_top_bar/index.html`. New enhancement controllers are
`components/crm_sections/automation_navigation.js` and `automation_refresh.js`.
The changes are scoped hunks within an already dirty working tree; they do not
replace unrelated changes.

Evidence tooling adds `scripts/benchmark_automations_v5.py`,
`scripts/summarize_automations_v5.py`, the three
`tests/fixtures/automation_v5_*` instrumentation files, and the three
`tests/check_automations_v5*` browser checks. `tests/test_automations_v5.py` adds
behavioral freshness, invalidation, permissions, URL restoration, terminal-read
and closed-menu metric regressions. Existing navigation, loading, stability,
publication and stage-settings tests are adapted to the supported fragment and
route behavior; the two controller CJS tests exercise the actual rendered script.

Raw before/after navigation, overlay-aware cold/warm entry, sanitized read-only
Render telemetry, fault results, operation results, gate logs, screenshots and
source hashes are saved in `docs/automations-v5-evidence/`. Connection/query
statistics are in `summary.json`. The source manifest records the six initial
working-tree snapshot hashes separately from current V5 files. No new release
package, commit or deployment was created.

**Status: Implemented locally. Not committed, pushed or deployed.**
