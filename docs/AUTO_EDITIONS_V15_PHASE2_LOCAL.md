# V15 Phase 2 — Edition Ops status and live updates

Implemented locally on 15 October 2026 (Australia/Sydney), in the same task,
owner, worktree and branch as Phase 1:

`C:\Dev\SportsCaveWorktrees\sports-cave-integrations-auto-editions-v15-automatic-product-mappin-20261014-1aae0e49`

Task `20261014-1aae0e49`, owner `codex/v15-20261015-01a13cc7`, branch
`codex/task/integrations-auto-editions-v15-automatic-product-mappin-20261014-1aae0e49`.
HEAD remains the user-approved V14 prerequisite `ca9ff5c2`. Phase 1 changes,
its report and unrelated work were retained. No commit, push, deployment,
production database mutation or live integration operation was performed.

## UI and authority

The existing Streamlit native editor remains in place. One small link column,
Auto Editions, follows File. The existing Product Title, Next Edition #, Limit,
ledger Status and File columns remain. Rows use 28px height in the same 600px
viewport. A compact filter shares the existing toolbar; mobile keeps one
horizontally scrollable toolbar row rather than wrapping labels vertically.

Statuses come from one product-scoped Supabase query joining audited mappings,
onboarding, immutable preparation sources/proofs, recorded approvals and the
latest public checkpoint. Known current source observations from Phase 1 are
also checked when V15 discovery is enabled. No source paths, transfer tokens,
audit-detail capabilities or credentials are selected for the UI response.

| Display | Required state / action |
| --- | --- |
| Not Connected | No verified mapping; existing File/Add remains available |
| Connect | Verified mapping but no onboarding checkpoint; administrator recovery only |
| Queued | Matching checkpoint awaiting preparation, priority above zero |
| Deferred | Matching checkpoint awaiting preparation, priority zero; Prepare Now |
| Preparing | Matching source and an unexpired companion lease |
| Review | Prepared current source/proofs retained, visual approval outstanding; existing Review |
| Cloud Ready | Current checkpoint/source/limit/proofs and one consistent approved preparation, with identified approver; TEST only |
| Needs Repair | PSD repair checkpoint; retry only if no immutable preparation is retained |
| Failed | Expired lease, blocked verification, stale preparation, changed mapping or inconsistent approval; safe Retry only where existing queue permits |
| Unavailable | Authoritative query cannot be loaded or identity is ambiguous; never inferred disconnected |

Clicking the status opens a compact contextual dialog through the existing PSD
modal launcher. It shows stage, checkpoint, reason and permitted actions. Review
embeds a compact mode of the existing onboarding page and reuses its preview,
explicit visual confirmation and approval endpoints. It does not create another
approval mechanism. Approval and download still perform their existing fresh
source/permission checks. Cloud readiness never means Shopify sync or supplier
print readiness.

Connect locks existing product/mapping records and creates only a missing
checkpoint through the existing queue. Repeated Connect is a no-op for an
existing matching checkpoint. A mismatched existing checkpoint is refused.
Mappings, edition numbers, allocations, certificates and approvals are untouched.
Successful Add/Save retains Phase 1's atomic automatic enqueue; no second Connect
is required. Status reads require Edition Ops access. Mutating actions retain
administrator, Files/Orders, cloud-enable and same-origin checks.

## Live refresh and preservation

The zero-height status component polls one batched endpoint every 25 seconds
while Edition Ops is visible. It uses a server-signed display snapshot, bound to
the current actor and requested products. Rows are transmitted once, rather than
duplicated inside the signature envelope. Stale/modified envelopes are refused.

Unchanged responses cause no rerender. Changed responses update only the table
fragment, never the whole page. Status-only fragment execution skips catalogue
hydration and mapping revision reads; the same signed batch supplies mapping IDs
for existing File links. It preserves the row/original/edit collections, selected
product, search, filter and native widget key. Active text/cell edits, scrolling
and open dialogs defer application. A short post-edit grace lets Glide's
asynchronous edit commit reach Streamlit before a status change alters the widget
identity. Native/page scroll positions are retained across grid reconstruction;
wheel, touch and pointer interactions retain control of the viewport.

While a detail dialog is open, the parent batch poll pauses and the dialog polls
only its current product. Existing modal/visual confirmation state is not replaced.
Manual Refresh remains and refreshes status while preserving dirty edition edits.
Existing Save & Sync Shopify and allocation functions are unchanged.

## Performance against the local baseline

The baseline has no Auto Editions live status read. Phase 2 adds one batch on
initial/status-scope load and one batch per visible 25-second poll, rather than
one query per product. Unchanged polls add zero Streamlit rerenders. Changed polls
add one table-fragment update and zero full-page rerenders. There are zero Dropbox
or Shopify calls in status reads. Explicit visual review retains its existing
on-demand prepared-asset reads.

With 333 synthetic products and 6,660 audit rows, native PostgreSQL measured:

| Local measurement | Result |
| --- | --- |
| Simple synthetic catalogue-listing median | approximately 24 ms |
| Authoritative status-batch median | approximately 45 ms |
| Queries per status poll | 1 |
| Serialized signed status response | approximately 75.6 KB |
| Per-row remote API calls | 0 |

These include local connection/read overhead and are not hosted Render latency
measurements. A small additive index on `(product_gid, created_at DESC, id DESC)`
supports latest-checkpoint lookup. No new service, cron or application dependency.
Reproducible measurements: `output/v15-phase2/performance.json`.

## Changed files in Phase 2

| Files | Purpose |
| --- | --- |
| `auto_editions_status.py` | Scoped authoritative projection, signed snapshots, permissions and Connect recovery |
| `edition_auto_status_ui.py` | Native-editor status cache and signed event handling |
| `edition_ops.py`, `edition_version_ui.py` | Column/filter, status-only fragment handling, dirty Refresh and compact/mobile layout |
| `sports_cave_server.py` | Register status/read-only detail/Connect routes |
| `components/edition_auto_status/index.html`, `live.js` | Visible-only polling, safe application and native/page scroll restoration |
| `components/auto_editions/status.html` | Contextual detail dialog |
| `components/auto_editions/onboarding.html` | Compact mode reusing existing visual review controls |
| `components/psd_picker/index.html` | Launch the new detail dialog through the existing modal mechanism |
| `auto_editions_onboarding_api.py` | Sanitize public checkpoint failure reasons |
| `supabase/migrations/20261015000124_auto_editions_status_audit_index.sql` | Additive latest-checkpoint performance index |
| `tests/test_auto_editions_status.py` | States, stale preparation, SQL, roles, Connect, signed updates, edits and performance |
| `tests/test_edition_ops_table_editing.py` | Updated six-column contract and isolated status reader fixture |
| `tests/test_edition_auto_status_ui.cjs`, `test_edition_auto_status_native.cjs` | Desktop/mobile browser contracts and actual native-grid edit/refresh/scroll checks |
| `tests/edition_status_fixture_state.py`, `edition_status_browser_fixture.py`, `edition_status_fixture_server.py` | Synthetic loopback-only fixture; no production app startup hooks or credentials |
| `docs/AUTO_EDITIONS_V15_PHASE2_LOCAL.md` | Local implementation and integration handoff |

## Tests and limitations

Combined Python regression: **208 passed, 17 subtests passed**. It includes
Phase 1 discovery, leases, transactional mapping, approval, Photoshop host,
uploads, cloud readiness, downloads, webhook eligibility, allocation invariants,
plus Edition Ops editing/save/navigation and all new status contracts. The latest
Phase 2 status-only suite independently passed **30 tests** on isolated native
PostgreSQL. Logs: `output/v15-phase2/final-python-tests.log`.

Browser suites passed: two desktop/mobile status bridge scenarios, two actual
Streamlit native-grid layouts, two existing onboarding layouts and nine existing
PSD modal/File scenarios. The actual grid test enters an uncommitted numeric edit,
defers a changed status, commits the edit, then manually refreshes and verifies
that the dirty edit remains. It also verifies unchanged polls, retained scroll,
constant 600px viewport, one filter and no full-page rerender. Screenshots:
`output/v15-phase2/native-1440.png` and `native-390.png`.

The fixtures reuse existing Python, PostgreSQL and Playwright runtimes. No
application/server production startup was used. The native test cluster and
loopback fixture server are stopped after testing. Diff/static checks and Render
topology pass against the approved V14 prerequisite. The inherited Studio
registry comparison to its older base retains the Phase 1 whitespace failures;
these unrelated prerequisite files were not changed or suppressed.

Remaining integration requires fresh authorization: review both local phases,
apply the Phase 1 additive schema and Phase 2 audit index after existing V6/V11
schemas, include the new status routes/assets in the existing app, and perform
authorized hosted account/browser/Photoshop acceptance. No live multi-user session,
real Shopify/Dropbox assets, hosted latency or supplier workflow was exercised.
The status is authoritative for recorded database identities/approvals and latest
known discovery observations; it does not perform a fresh Dropbox lookup. Existing
download/review checks still fence external source changes. Poll application can
pause during editing, scrolling, hidden tabs or open dialogs. Streamlit may
distribute spare width among its small native columns; the new column uses the
existing small-column sizing policy rather than a separate grid.
Preparing reflects a valid recorded companion lease, not a live Photoshop
heartbeat. Retry follows existing queue safeguards: retained immutable or stale
prepared assets require administrator review instead of an automatic reset.

The task remains local and uncommitted. Tested is not clean committed review
readiness and is not release authorization.
