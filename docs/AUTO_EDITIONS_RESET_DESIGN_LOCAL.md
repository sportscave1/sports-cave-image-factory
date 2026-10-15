# Auto Editions minimal Reset design - local implementation

Status: IMPLEMENTED AND TESTED LOCALLY. NOT COMMITTED, PUSHED, DEPLOYED OR ACTIVE.

## Verified isolation

- Task: `20261015-9013660f`; owner `codex/reset-design-20261015-01a13cc7`.
- Worktree: `C:/Dev/SportsCaveWorktrees/sports-cave-integrations-auto-editions-minimal-reset-design-and-saf-20261015-9013660f`.
- Branch: `codex/task/integrations-auto-editions-minimal-reset-design-and-saf-20261015-9013660f`.
- Baseline: independently verified canonical Render Live revision
  `607d10cb743694f5b94b1567897adad8280dd159`.
- Studio created this new task at its older global base. Only this task was
  fast-forwarded locally to the verified live commit. The global approved base,
  original checkout, V15, RELEASE and uncommitted V16 work were preserved.

## UI

The existing Auto Editions column and native editor remain unchanged. Only visible
status cells get a tiny right-aligned refresh button. The popup contains exactly
Reset design? / Cancel / Reset. Cancel removes it immediately and sends no request;
Reset closes before the request completes. The existing signed batched status
refresh updates the row without changing the dirty edit buffer, product selection,
filters, native grid scroll or page layout. No new column, toolbar, page, service,
worker, cron or timer was introduced. The existing 25-second refresh remains.

The native grid is canvas-based. The existing status component discovers the
current committed Glide ref and uses its actual getBounds/getCellContent APIs to
place buttons over visible rows only. It never guesses product IDs from row
numbers or text. Headers and partially clipped cells are excluded. A click rechecks
the committed row identity and fails closed if it changed. A framework upgrade
requires rerunning the native-grid compatibility tests; an unsupported ref yields
no unsafe guessed targets. Read-only accounts and actively preparing designs have
disabled icons. Backend authorization independently requires the existing admin
Files/Orders/Edition Ops permissions, same-origin access and existing V6/V15 gates.

## Reset and safe publication

The existing onboarding row holds one nullable replacement JSON object. Its active
file/source/preparation/status remain intact while an explicitly requested redo
is discovered, queued and prepared. This is pending operation state, not a new
version-management system. Existing append-only audits retain request and previous
preparation identities. No approval record is rewritten.

POST `/api/auto-editions/status/reset` accepts exactly product_gid and request_id.
It performs no Dropbox calls and queues discovery durably. Duplicate and delayed
historical request IDs are idempotent. A second request for a pending reset, an
active original preparation or an uncertain expired original Preparing job is
rejected; no Photoshop lock is stolen or removed.

The existing discovery worker wakes its cursor and consumes a complete incremental
Dropbox delta after the request. An already in-flight inventory is insufficient.
It uses the existing exact filename/title/product/handle/ownership matcher, with
only the explicitly selected product's prior mapping excluded for this rematch.
Other verified ownership is always reserved. Current file ID, revision, content
hash and approved original PSD directory are checked. Ambiguous/missing/changed
sources retain the original working design and expose existing Failed/Needs Repair
states. No timestamp/fuzzy/latest-file guess is accepted. Only the selected exact
candidate's cached metadata is refreshed. No Prepared/Masters folder is scanned.

The same preparation queue and paired Windows companion process the replacement.
Order urgency and Prepare Now priority keep precedence; other Deferred jobs are
untouched. A reset request identity in the scoped context and immutable manifest
forces fresh Photoshop work even when the original Dropbox file ID/revision did
not change. A package from before this reset cannot satisfy it. A package already
built for this SAME request can resume an interrupted upload without redoing
Photoshop. Existing lease ownership, source/context fences and bounded three-attempt
recovery apply. The old checkpoint cannot be mistaken for successful new completion.

After existing package/pixel validation, complete immutable Dropbox receipt
verification and preparation save succeed, the audited mapping and active checkpoint
switch atomically. Mapping/source/product/limit/ownership are checked again under
the existing lock order. Old preparations, approvals, source files, archives,
certificates and allocations are retained. New preparation still goes through
existing Review/approval rules; reset never fabricates or transfers approval.
Failed publication retains the working checkpoint. Transient upload failures reuse
the existing reconnect path. Explicit newer manual Add/Save can supersede a reset
without hanging the normal queue; stale reset capabilities cannot publish afterward.

## Focused tests and performance

- **22 dedicated reset cases passed across focused runs**, including same-ID fresh redo, changed-ID
  atomic switch, latest revision, ambiguous/missing/unapproved/other-owned files,
  duplicate and historical retries, active-job rejection, expiry recovery, interrupted
  upload, old companion rejection, manual Add concurrency, Not Connected onboarding,
  permission/scope/privacy and 167 unchanged Deferred checkpoint records. Final
  acknowledgement checks also confirmed that a previous completed upload can
  finish acknowledging before the replacement is claimed, while the new reset
  cannot mistake that old receipt for its own completion (3 targeted checks passed).
- **97 focused regression tests passed; 1 optional PGlite test skipped.** New reset
  tests use real disposable native PostgreSQL and synthetic products/assets only.
  Final reset tests overlap this regression run; counts are not additive.
- **7 browser scenarios passed:** reset desktop/mobile, concurrent status-refresh
  race, existing desktop/mobile modal bridge, existing desktop/mobile native table.
  Actual native 28px rows, 600px grid height, dirty edits, immediate cancellation,
  row identity after scroll, immediate popup close, one refresh, scroll preservation
  and no whole-page rerun were checked on the 334-product synthetic fixture.
- Python/JavaScript syntax, focused diff whitespace and Render topology passed.
  No unrelated baseline whitespace was edited and no global Studio base changed.
- No production database, Shopify, Dropbox or live Photoshop operation was performed.
  Browser scenarios were isolated loopback/intercepted fixtures, not hosted acceptance.

Seven-sample synthetic local benchmark with Python allocation tracing (not hosted
latency/RSS), 334 products:
- verified_baseline: {'median_ms': 51.94, 'python_peak_bytes': 1313868, 'response_bytes': 83668, 'queries': 1, 'dropbox_calls': 0}
- with_reset: {'median_ms': 57.09, 'python_peak_bytes': 1296392, 'response_bytes': 87675, 'queries': 1, 'dropbox_calls': 0}

The extra response field is a permission flag. It adds about 4 KB to the full
batch. There remain zero Dropbox calls per status refresh and no extra periodic
browser polling; button DOM is bounded to visible rows.

## Remaining release requirements / limitations

1. Owner release approval is still required. The new additive migration
   `20261015024929_auto_editions_reset_design.sql` adds only nullable replacement
   state and a pending-state index to the existing private onboarding table. It
   was applied only to isolated test databases. Apply it before exposing the action
   in a later approved release. No allocation, mapping or approval migration is needed.
2. Deploy only an explicitly approved combined revision. Update the existing
   companion's two reset-related code additions during an approved idle installation
   window. The currently installed live companion was NOT replaced or restarted.
   An outdated companion is rejected safely before publishing a replacement.
3. Actual Windows Photoshop, Dropbox and authenticated hosted acceptance remain
   for an explicitly authorised test after release/installation. Synthetic tests
   verify contracts but are not a real Photoshop execution claim.
4. V16's uncommitted production-quality work was deliberately not copied into this
   branch. Any later combined release must integrate and test the two reviewed
   branches explicitly. Reset retains V15 approval and allocation safeguards.
5. A stale shared Photoshop processor lock still requires the existing owner-led
   recovery; reset is not a lock-stealing, allocation-reset or approval-bypass action.
   Newly uploaded but unreferenced assets after a failed import are retained and
   reported through existing audit controls, never automatically deleted or relinked.

## Exact changed files
- `auto_editions_discovery.py`
- `auto_editions_onboarding_api.py`
- `auto_editions_onboarding_store.py`
- `auto_editions_setup_api.py`
- `auto_editions_status.py`
- `components/edition_auto_status/index.html`
- `components/edition_auto_status/live.js`
- `scripts/studio/auto_editions_local.py`
- `tests/edition_status_fixture_state.py`
- `auto_editions_reset.py`
- `components/edition_auto_status/reset.js`
- `docs/AUTO_EDITIONS_RESET_DESIGN_LOCAL.md`
- `supabase/migrations/20261015024929_auto_editions_reset_design.sql`
- `tests/test_auto_editions_reset.py`
- `tests/test_auto_editions_reset_ui.cjs`
