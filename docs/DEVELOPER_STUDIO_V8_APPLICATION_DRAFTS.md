# Developer Studio V8 — local application drafts

Status: implemented locally; no repository commit, push, merge or deployment.
Real publishing remains disabled. The production site and existing Windows
companion/startup registrations have not been replaced.

## Result

The permanent Developer Studio opens the existing V6 three-panel workspace.
Ordinary Drafts contains only active records with kind "application". Legacy
technical tasks, acceptance drafts and archived copies are available separately
under Studio → Release history → Advanced · technical task history.

Application copies reuse the existing registered-worktree, owner, editor,
checkpoint, local confirmation and Docker contracts. Each has an immutable UUID,
a UUID-based branch/path, independently editable name, production receipt,
source revision, timestamps, history, source test evidence and preview evidence.
Names are never used to resolve files. Later automatic names are "Sports Cave OS
copy 2", "Sports Cave OS copy 3", etc., including after the first copy is renamed.

Create/configure and duplicate reserve a new task/worktree before allocating it.
Repeated initial configuration reopens the existing copy. A failed allocation
stays registered as Blocked and prevents unattended retry copies. Existing
technical worktrees are never converted into application drafts.

Rename, duplicate, create, archive and update requests are reviewed in the
existing localhost approval window. A short-lived, one-use local ticket binds
the review. Revision, metadata version, content fingerprint and owner checks
are repeated before mutation. Tickets and private capabilities stay local.

Archive / Delete currently archives the entry only. It requires review of
unfinished changes and the exact draft name. Source, branch, task record and
recovery history are retained. Physical worktree deletion is intentionally
unavailable. Archived drafts cannot obtain an editor grant.

Update Draft from Live supports a reviewed, explicitly confirmed clean
fast-forward only. Dirty or diverged source is refused with an explanation.
It prepares a recovery branch and rechecks the exact verified SHA. Conflicting
work needs a separately approved integration; nothing is reset or silently
merged. No actual update/merge was executed in this task.

The 49 OS pages plus Sign in remain driven by the selected copy's static page
catalog. Unsupported inspection stays read-only. Existing source allowlists,
hash/revision checks, Undo and per-file Restore Revision remain in force.

Selected draft/page metadata and unsaved editor buffers are scoped to the local
companion origin and immutable draft ID in the owner's browser storage. Buffers
are restored only after the selected draft receives the normal local grant.
Recovery retains the original file hash and draft revision, so changed source
cannot be overwritten by stale recovered text. Explicit Discard clears recovery.
No bearer token or local capability is stored there. Clearing browser storage
removes unsaved browser recovery; Save Draft writes to the actual worktree.

Tests runs bounded source/catalog/mapping checks without executing draft code on
the Windows host. Evidence carries the source snapshot. Docker runtime probes
and owner-controlled release approval remain separate.

## Verified default copy

- Name: Sports Cave OS copy
- Immutable draft ID: 9ca4a85e-b3f4-4c85-b61e-4eb5551d2740
- Owner: codex/v8-01a12f62
- Internal backing task: app-9ca4a85e-b3f4-4c85-b61e-4eb5551d2740
- Branch: codex/application/9ca4a85e-b3f4-4c85-b61e-4eb5551d2740
- Base/current Git revision: 9de9539f07437f9d5809ee2828e61b3e47909734
- Worktree: C:/Users/hello/.codex/visualizations/2026/10/12/01a12f62-716b-7020-bd5c-ca5719a94467/v8/sports-cave-app-9ca4a85e-b3f4-4c85-b61e-4eb5551d2740
- Registry home: C:/Users/hello/.codex/visualizations/2026/10/12/01a12f62-716b-7020-bd5c-ca5719a94467/v8
- Authenticated Render live deployment: dep-db6aor49v7es739s877g
- Canonical service: sports-cave-os / srv-d8kl4on7f7vs73dvavv0
- Verification recorded: 2026-10-12 10:13:56 UTC

GitHub main was freshly checked with ls-remote and matched Render's live
deployment. The copy was created from that exact immutable Git object, not the
older original checkout, UI/UX task or historical V6 task. The acceptance edit
was undone byte-for-byte; the copy's Git status is clean.

The V8 implementation remains separate in task 20261012-v8, branch
codex/task/core-v8-os-drafts-20261012-v8. Uncommitted V8 implementation code has
not been silently integrated into the production-based application copy.

## Preserved records

The original C:/Dev/SportsCaveWorktrees registry retains 16 technical tasks and
these seven historical draft records:

- Phase 2 safety foundation
- Synthetic preview acceptance
- Developer Studio Phase 4B and 4C local acceptance
- Sports Cave OS UI UX V1
- V5 Companion Acceptance
- Developer Studio V6 OS Editor
- Developer Studio V6 RELEASE acceptance

They are hidden from ordinary Drafts by the new type filter, not deleted or
reassigned. Their Git/source history, ownership, tests and recovery records
remain available. All 35 worktrees in the initial inventory were retained with
their original branch and HEAD identities,
including the original dirty repository, UI/UX work, prior V6 work, Google
integration/release work and other unfinished sessions. The registry and Git
worktree inventory were checked once for V7; none was registered. No Docker
runtime/performance implementation file was changed.

## Exact repository files changed

Application and editor implementation:

- components/developer_studio/panel.html
- components/developer_studio/panel.js
- scripts/studio/application_drafts.py (new)
- scripts/studio/draft_ui.py
- scripts/studio/drafts.py
- scripts/studio/editor.py
- scripts/studio/ui/editor.js
- scripts/studio/ui/workspace.js
- scripts/studio/ui/pair.html
- scripts/studio/ui/pair.js

Tests and acceptance:

- scripts/studio/test_application_drafts.py (new)
- scripts/studio/test_phase4a.py
- scripts/studio/test_workspace_selection.cjs
- scripts/studio/verify_v6_ui.py
- scripts/studio/verify_v8_browser.py (new)
- docs/DEVELOPER_STUDIO_V8_APPLICATION_DRAFTS.md (this report)

Runtime data outside the implementation checkout: verified-live.json, the local
registry/application worktree, recovery/checkpoint blobs, preview/test evidence
and browser acceptance reports. These contain no production data or credentials.

## Verification and performance

- 202 Python Studio tests passed, including owner/source/hash/expiry restrictions,
  application-only catalogs, actual worktree identity, idempotency, naming,
  copy isolation, stale review rejection and archive preservation.
- All three Node protocol suites passed.
- Disposable Edge lifecycle acceptance passed: first creation only after local
  confirmation, rename identity, real source duplication, source save, reopening
  recovery, focused tests and archive of unfinished source without deletion.
- Responsive Edge acceptance passed at widths 1440, 1100 and 390: no document
  overflow or JavaScript errors; Save/Undo/Restore, authorised source, delayed
  load locking, permission expiry, reconnect and locked-draft rejection passed.
- Actual Sports Cave OS copy in the existing Docker runtime: the mapped change
  appeared in the preview and Undo restored app.py byte-for-byte. Pages selected
  the actual Developer Studio route; its three-panel interface was visible.
- Docker negative probes passed: network denied, no credentials or host mounts,
  no published ports, non-root, read-only root, bounded resources and restricted
  browser navigation. Only acceptance-owned previews were stopped.
- Source checks for the real copy passed: 49 OS pages plus Sign in, clean source.
- Render topology validation and git diff --check passed.

Single-run timings: default workspace 0.092 s; fixture connection/open 1.806 s;
cold Docker preview 29.643 s; save plus explicit preview verification 10.138 s.
Prior V6 measurements were 0.152 s, 29.272 s and 10.025 s for the comparable
entry/cold-preview/save checks. No meaningful regression was observed; these
are local samples, not a load benchmark. The generated panel is approximately
65 KB, versus approximately 60 KB previously. No dependency, heavy framework,
polling loop, new Render service or database was added.

Evidence beside the V8 registry:

- v8-actual-acceptance.json and associated default/edited/pages/OS-route images
- v8-responsive.json and images for all three widths
- v8-lifecycle-browser.json and screenshot
- verified-live.json and live-deployment.json

## Configuration, limits and release readiness

Ready for focused local release review. Activation needs the corresponding V8
hosted UI and local companion backend together; the currently running production
UI/companion have deliberately not been replaced by this local task. Reuse the
existing companion launcher/trust mechanism, with the registered application
owner, and verify the hosted HTTPS handoff after a separately approved release.
No personal browser profile, scheduled task or active companion was changed.

Initial configuration uses application_drafts.py --configure with the assigned
local task/owner and registry home. A local administrator first records the
authenticated live provider receipt using --record-live, --github-main and
--evidence. The OS browser cannot submit or override a production revision.
Receipts expire after one hour for new-copy/live-update operations; GitHub main
is rechecked immediately. Existing copies remain editable after receipt expiry.
Fresh Render evidence currently requires the local administrator verification
step; this task does not add background provider credentials or claim continuous
production monitoring.

The real fast-forward integration command was not exercised. Automatic approval
review rejected a disposable positive test because the user prohibited merges.
The replacement test mocks the Git mutation boundary and verifies exact
confirmation, recovery command planning and stale rejection. Real update
acceptance therefore remains for a separately authorised integration.

Publish stays disabled. Existing Release Manager requires its independent
exact-revision tests, review and approval; a draft name, saved status or passing
source test never grants release eligibility.
