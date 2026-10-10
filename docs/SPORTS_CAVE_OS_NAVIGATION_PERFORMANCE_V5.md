# Sports Cave OS Navigation Performance V5

Validation date: 10 October 2026. Selected release base: GitHub main
`02c81f1d4dcb2c572e63d8aa4004766d458b634d` (includes concurrent table presentation work).
No commit, push, merge, deployment or production mutation was performed.

## Release assessment

The selected changes are prepared for manual release in `tmp/navigation-v5/main`.
Navigation/affected-module regressions passed. Live production latency, Chrome and
Edge acceptance, independently measured network time and genuine process-cold
startup remain unverified. This is a scoped navigation release, not a claim that
every production page meets Shopify-class latency or the 300ms engineering target.

The existing canonical Render service was inspected read-only: `sports-cave-os`,
`srv-d8kl4on7f7vs73dvavv0`, repository `sportscave1/sports-cave-image-factory`, branch
`main`, `autoDeploy=yes`, trigger `commit`. Its identity/topology was unchanged.

## Architecture and lifecycle

`app.py` retains its existing session/authentication gate (30-second revalidation),
URL/session history resolver, permission gate, lazy module imports, top-bar
controller, sidebar fragment, page dispatcher and completion bridge. No replacement
router, global data cache, extra navigation polling or inactive mounted applications
were introduced. The requested destinations do not use the shared local-database
initialization path, so unrelated database initialization was not changed.

1. A sidebar event receives client feedback and a latest-intent identifier.
2. Streamlit accepts the widget event. Full-sidebar callbacks now resolve their
   route before main runs; fragment destinations retain their existing app rerun.
3. Existing route, permissions and draft guards run. The top bar receives the
   accepted route/epoch. Lazy dispatch runs only the selected page renderer.
4. Existing cached information and essential/optional reads follow that page's
   own rules. Email/Orders expose their existing progressive loading states.
5. Completion acknowledgements remain route/epoch/intent guarded. Essential
   asynchronous Orders/Email loading is distinguished from readiness; Email can
   acknowledge after its actual fragment controls render. The loaded fragment also
   updates the server last-working-page state under the same route/epoch guard.

## Confirmed bottlenecks, ranked

| Rank | Bottleneck | Evidence / frequency | Fix and risk |
|---|---|---|---|
| 1 | Reporting repeats identical schema probes | Six checks per real populated Reporting render; 100 unnecessary reads over 20 returns | One fresh render-scoped check for four read helpers. Context resets on failure/exit, thread/backend isolated; mutation helpers still perform fresh checks. No record or permission cache. |
| 2 | Full-sidebar route changes discard a first full run | Orders/Edition Ops: 40 attempts per 20 clicks before; 20 afterward in both independent trials | Standard Streamlit callback sets the route before main. Revoked permission check, latest intent and draft guard remain. Fragment route behavior unchanged. |
| 3 | Returning to Email forces provider refresh | 20 warm returns performed 20 settings, 20 folder and 20 header reads despite existing cache rules | Remove forced load on navigation; existing 20-second header TTL, folder TTL, scope and recovery backoff stay authoritative. Explicit Refresh still forces reads. |
| 4 | Completion conflates shell and essential readiness | Cold Orders can return while snapshot worker is pending; initial Email/body arrives through a fragment | Distinguish loading/error/ready; later Email DOM acknowledgement completes the current epoch. Does not invent data or change loader timers. |
| 5 | Existing local V4 disclosure/width/presentation overhead | Selected-parent disclosure previously requested a full app run; redundant width writes and remounted badge bindings | Carry forward already implemented V4 fragment reruns, observed width and coalesced structural observer. Cached badge restoration and current-route disclosure behavior preserved. |

## Controlled browser measurements

Milliseconds below are **p50 / p95** (nearest-rank p95). Orders/Edition Ops and
Email/Reporting each used two independent browser sessions per variant, opposite
trial order, matching foreground 1440px viewport and four discarded warmup clicks
per 24-click trial. There are 40 retained clicks per variant, 20 per destination.
Separate before/current Streamlit processes supplied matching real renderers.

Orders used 50 fabricated rows; Edition Ops used 100 products. Email used 30
fabricated messages with the real Workspace/component. Reporting used an archive,
actual store helpers and actual page UI. Their controlled source boundary delays
were 40ms/read. HTTP, production DB, SMTP and IMAP transports were fenced off;
only designated disposable loopback SQL was used for CRM regressions/acceptance.

| Destination | Samples per variant | Before browser ready | After browser ready | Interpretation |
|---|---:|---:|---:|---|
| Orders | 20 | 584.30 / 614.30 | 488.90 / 513.90 | Matching 50-order / 100-product synthetic workloads |
| Edition Ops | 20 | 567.00 / 601.90 | 463.70 / 497.80 | Matching 50-order / 100-product synthetic workloads |
| Reporting | 20 | 885.50 / 948.70 | 735.95 / 779.60 | Improvement; six schema checks become one |
| Email | 20 | 544.15 / 598.70 | 542.45 / 632.90 | No reliable browser speed gain; warm provider reads reduced |
| Home | 20 | 576.00 / 588.90 | 417.55 / 478.40 | Same page functions; offline optional sources / empty dispatch ledger |
| Fulfilment | 20 | 598.45 / 651.40 | 448.65 / 495.20 | Same page functions; offline optional sources / empty dispatch ledger |

For Orders/Edition Ops pooled together, route acceptance changed from
566.40 / 599.00 to 449.95 / 483.50ms;
the completed main-content marker changed from 580.05 / 607.30 to 476.80 / 504.20ms.
Single completed-render Python time was 69.99 / 76.66 → 69.78 / 77.79ms;
sidebar processing was 28.71 / 31.91 → 28.00 / 31.97ms.
Thus the browser gain is consistent with eliminating an aborted extra run,
not a faster table renderer. Warm source reads/cache invalidation were retained.

Browser feedback for that workload was 8.75 / 12.30 → 9.10 / 14.80ms.
The next animation-frame observation was 85.85 / 95.50 → 92.45 / 100.90ms;
this frame tail did not improve. It is not proof that every frame appears under
50ms, even though the DOM feedback itself meets that target.

| Destination | Page initialization before → after | Measured server region before → after | Controlled read time before → after | Python excluding those controlled reads before → after |
|---|---:|---:|---:|---:|
| Email | 126.37 / 127.79 → 2.47 / 2.88 | 158.28 / 161.53 → 35.44 / 40.13 | 121.10 / 121.58 → 0.00 / 0.00 | 36.73 / 40.02 → 34.89 / 37.87 |
| Reporting | 467.13 / 469.98 → 266.18 / 270.95 | 499.84 / 505.34 → 299.84 / 307.16 | 443.94 / 444.53 → 242.02 / 242.76 | 56.35 / 61.48 → 57.69 / 65.08 |

These server regions include top-bar/sidebar and page dispatch, but exclude fixture
definition/import setup and production authentication. They are **not** the total
production Streamlit rerun duration. The content sentinel is at the end of page
rendering: it is a conservative completed-content marker, not a measurement of the
earliest useful pixel. Essential controls were separately checked through the actual
UI (including native Email controls and real Automation Email Editor); independent
interactive-control and compositor-paint p50/p95 were not captured.

**Network timing:** not separately measurable here. Streamlit uses WebSocket
messages; the browser/server residual includes transport, scheduling, serialization
and frontend reconciliation. It must not be labeled network latency. No production
Shopify/Meta/GA4/IMAP or database latency figures are invented. Controlled read time
above is synthetic source latency, not an external-service SLA.

### Request reductions and measurement noise

Reporting: 220 measured reads before versus 120 after over 20 returns. All 100
data reads remain; schema reads fall from 120 to 20. Each render still freshly
checks storage and enforces each helper's permissions. At 40ms/source this removes
about 200ms of repeated waiting per render.

Email: 60 forced reads before versus one naturally expired header read after over
20 returns. Nineteen warm returns required none. Explicit Refresh, TTL expiry,
mailbox/user scope changes and failed-connection backoff are regression-tested.
Email browser p95 increased despite the server/read improvement. Two reversed
trials did not show a reliable median browser improvement; the persistent
roughly half-second component/Streamlit handoff dominates. **No Email browser
speed improvement is claimed.** Provider-call reduction is independently verified.

The former V4 AppTest 295.59→339.33ms / 405.88→454.83ms figures are not used to
claim a regression or improvement. They are a different offline workload and were
not controlled browser measurements. V5's repeated matched trials show that
completed-render Python/sidebar costs remain broadly stable; the confirmed wins
come from less duplicate work. They do not retrospectively prove those V4 numbers
were noise. The previously invalid cold-start comparison remains discarded.

### Cold and warm limitations

First-session samples are retained in the raw evidence, including first Orders
snapshot and Edition Ops reads. They are not process-cold starts: imported modules
are warm, Email is explicitly seeded for comparable complete data, and initial
async Orders shell completion in the older baseline was premature. These samples
are excluded from warm statistics and from cold-start improvement claims. Genuine
production cold startup needs a controlled process restart and production-safe
service instrumentation; no valid cold-start gain is claimed in this release.

### Additional lightweight workload check

Two 11-cycle trials per variant retained 20 samples/destination after a six-click
warmup. Home and Fulfilment had matching page bodies/modules; their offline results
appear above (Home's optional weekly analytics was unavailable, Fulfilment's ledger
was empty). Mockups, Design Studio, Ads and Product Uploads also completed the
repeated journeys, but reconciliation found differing unrelated local image/design/
ads module revisions across the broader release comparison. Their comparative
numbers are retained as diagnostics in `light-summary.json` and **excluded from
speed claims**. Those differences are not shipped by this release.

## Complete destination and journey audit

| Destination | Actual interface exercised | Data/access limit |
|---|---|---|
| Home | Calendar table, welcome and weekly section | Optional weekly backend unavailable |
| Orders | Real search/table/certificate controls | 50 fabricated records; no fulfilment/sync actions |
| Fulfilment | Existing dispatch interface | Empty isolated dispatch ledger |
| Edition Ops | Real 100-product table, filters and advanced controls | Fabricated rows; no Save/Shopify sync; archive/tracking remain lazy |
| Mockups | Actual upload/product/generation controls | No image generation or external uploads |
| Social Media | Actual landing page and retry UI | Storage fenced; full live workspace not available |
| Product Uploads | Actual prompt workflow and controls | No Shopify product creation/publishing |
| Design Studio | Actual saved-design/scheduling controls | Empty controlled selection; research/Sales Intelligence unchanged |
| New Ads | Actual form and campaign/prompt controls | No campaign submission or Meta changes |
| Creative Refresh | Actual winning-ad/product/country controls | No generated/saved live campaign |
| Meta Review | Actual search/date/sort controls and unavailable state | Live account/report access unavailable; retry/cache/attribution untouched |
| Analytics | Actual overview/settings | GA4 property unavailable; no live data latency claim |
| SEO | Actual filters and recoverable error UI | Fenced backend; no live GSC result verification |
| Reviews | Actual filters/list scaffold | Backend fenced; populated reviews not verified |
| Email Inbox | Real component, thread/Reply controls | 30 fabricated messages; no sending |
| Campaigns | Real search/filter/list workspace | Disposable SQL; live totals/delivery unavailable |
| Automations | Real SQL-backed overview and native flow link | Fabricated draft; live analytics empty |
| Individual Automation Flow | Real sequence, toolbar, Edit Email and return | Synthetic native flow; no publish/test/send |
| Reporting | Actual report archive, preview, delivery-health controls | SELECT-only controlled sources; test-send not clicked |
| Accounts & Access | Actual permission/admin page | Production account storage fenced; no account changes |

Home→Orders→Home, Orders↔Edition Ops, Design Studio→Ads→Design Studio,
Campaigns↔Automations and Meta Review↔Analytics use the same preserved dispatcher
and were exercised through sidebar routes. The native Automation Flow→Email Editor
→Flow journey used the actual editor, not a placeholder. A fabricated subject
`V5 synthetic draft retained` returned in the real sequence after the editor handoff.
No live publishing or delivery controls were used.

Repeated current Orders clicks did not change the fixture's full-run samples.
Rapid Orders→Edition Ops→Orders resolved to latest Orders with no pending overlay.
Production top-bar Back and Forward restored Orders/Edition Ops with one history
widget event per traversal. The tooling's tab.back helper changed the URL without
the expected native event; the actual application Back/Forward controls were used
to verify browser history rather than treating that tooling behavior as an app fix.
Orders async loading and transition away remained navigable.

Selected Email disclosure: 20 retained toggles had p50/p95 360.00 / 387.20ms,
with **no additional full page samples or page initialization**. This does not meet
the 100ms child-list expansion target; Streamlit fragment/widget reconciliation
still costs hundreds of milliseconds. Immediate click feedback and child expansion
are separate measurements. Existing forced-open Ads/Analytics/SEO route families
were preserved, not made collapsible for the test.

## Browser and responsive acceptance

Windows Chrome and Edge are installed, but native browser control was blocked by
the tool's browser-policy availability. Neither is claimed verified. Browser
acceptance and timing used the Codex in-app browser, with the production controller,
sidebar fragment and real renderer source in the exact reconciled release.

1920, 1440, 1366, 1024, 750, 390 and 320px were checked. Sidebar width and width
token both measured 244px. No sidebar button overflow or document overflow was
detected; gold highlighting/compact typography remain. Top-bar height is 64px on
desktop, 56px at 750px, 100px at 390/320px. The actual mobile drawer opened at 320px;
Escape, backdrop dismissal, Enter navigation, lower-menu scroll reach, navigation
close and desktop resizing worked. Its mobile box begins under the 100px top bar.
The earlier visibly closed drawer was a fixture/testing limitation, not evidence
that the production opener needed removal.

No additional full-page flashes were observed in the checked transitions. Same-route
events, epoch guards, abort ownership, status deduplication and listener cleanup
are covered by Node and Python contracts. Repeated routes completed without accumulating
page trees; a browser-heap/production-session soak was not performed, so no claim
of zero memory growth is made. Existing bounded CRM cache tests remain authoritative.

## Regression results

- Exact current-main release: 348 Python tests, 345 passed / 3 database-dependent
  skips. Covers navigation, V4/V5 behavior, permissions, Reporting, top bar, order
  notification status, Email scope/TTL/recovery and initial load.
- Nine Node suites passed: readiness, top-bar request ownership/history, V4 width/
  structural observers, Email autosave, reader, notifications, live scheduler and
  reconnect. The live scheduler suite contains 73 assertions.
- Broader real-page suite: 226 tests, 209 passed / 9 skips / 8 identical failures
  on pristine main and release. These are legacy Edition Ops/Mockups/Product Upload
  structural/catalogue expectations, not newly introduced Navigation V5 failures.
  The old save fixture patches `edition_ops.st` and clicks `Save Changes`, while
  the current page delegates to `edition_version_ui`; it never exercises the new
  save control. Current Edition version UI/mirror tests: 21 tests, 11 passed /
  10 database-dependent skips, including failed-save input retention, concurrency
  baselines and confirmed Shopify readback feedback. The 50-row expectation also
  conflicts with the existing complete 120-row catalogue fixture.
- CRM cache/recovery suite: 42 tests, 35 passed / 5 skips / 2 identical failures on
  pristine main and release (migration-list and outdated outage-element assertions).
  The migration assertion incorrectly requires CRM to be the deployment-list
  suffix after later Wall Preview migrations were appended; the outage assertion
  expects `st.error` on an initial render despite the current progressive inline
  unavailable/retry states. Those assertions were not weakened or shipped as fixes.
- SQL CRM navigation, delivery checkpoints and automation timing: 22 passed.
  The final bounded run retained worker scheduling/source reads with fabricated
  image bytes, avoiding unavailable Chromium image-renderer installation. Earlier
  test processes completed assertions but waited for thumbnail worker cleanup;
  those are not silently reported as clean process exits.
- Wall notification arrival / per-user receipt SQL: 9 passed against disposable
  loopback PostgreSQL. Provider/Shopify/Dropbox boundaries are mocked.
- `git diff --check`, Python source compilation, PowerShell parse/integrity dry run
  and canonical Render topology validation are release checks. The deployment
  command runs none of these expensive suites.

## Files and preservation

Production: `app.py`, `components/sports_cave_top_bar/index.html`,
`components/support_email/mail.js`, `support_email_page.py`, `reporting_page.py`,
`reporting_store.py`. Regression additions/adjustments: `tests/sidebar_preview_app.py`,
`tests/test_navigation_performance.py`, `tests/test_navigation_v4.py`,
`tests/test_navigation_v4_width.cjs`, `tests/test_navigation_v5.py`,
`tests/test_navigation_v5_ready.cjs`, and this report.

The release was assembled by reviewed hunks on a fresh existing local main checkout,
not by staging the shared workspace's full app diff. Unrelated app encoding edits
and concurrent image/design/Ads/CRM files were excluded. Main's table presentation
changes are retained. The working checkout and its unrelated modifications remain
uncommitted. Routes/order, authentication, draft guards, notification counts, TTLs,
CRM publishing/consent/scheduling, Shopify/Meta calculations, allocation and all
production records remain unchanged.

## Evidence and remaining limits

Local raw browser/server JSON, module comparison, reports and screenshots:
`tmp/navigation-v5/evidence/`. Primary summaries: `summary.json`,
`operations-summary.json`, `light-summary.json`, `release-widths.json`.
Route snapshots: `route-audit-1.json`, `route-audit-2.json`,
`flow-editor-retained.txt`. Desktop/mobile proof: `release-orders-1440.png`,
`mobile-320.png`. Test logs are in `tmp/navigation-v5/`.

Real provider latency, cold-process startup, Chrome/Edge acceptance and precise
first-pixel/interactive/network timing require a further production-safe measurement
pass. Warm browser display remains above 300ms; the unchanged Streamlit/component
handoff dominates several pages. Optional GA4/SEO/Meta/CRM reads continue to use
their existing correctly scoped freshness rules. No new cache masks live data,
notification/background work is not disabled for the benchmarks, and missing live
services are shown explicitly rather than presenting fabricated results as current.

## Fast manual release

All reconciliation and expensive verification happen before the user command.
The helper verifies a sealed approved-file manifest, exact base/main revision,
remote repository, empty index and allowed working changes. It stages only those
files, checks their staged Git blobs and diff, commits, and performs a normal push
to `main`. It fails if remote main or approved files changed. No force push,
automatic reset/rebase, clone, tests, dependency installs or Render API mutation
is in the command. A successful push triggers the existing commit auto-deploy.
