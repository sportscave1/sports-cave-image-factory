# Code-First loading fix — local only

Prepared in `codex/task/core-code-loading-fix-cf-load`, task `cf-load`, owner
`codex/cf-loading-fix`, from verified Code-First release commit
`30c2da00ff47822b4a205e937b29956b9ff655d9`. No commits or external mutations made.
The previous Code-First worktree and its uncommitted edits remain intact.

## Confirmed causes

The release commit's `developer_studio_page.py` bundles workspace/legacy editor assets
but omits `code-editor.js`; `panel.js` requests that missing entry. Previously
`Blob([undefined])` imported a valid JavaScript module with no `mount` export.
Workspace assigned that module before validating it, then failed at `editor.mount`.
Initial preview startup occurred after this failing source-editor initialisation,
so the exception also prevented the independent Docker preview from opening.
The earlier Code-First worktree has an uncommitted producer-only correction; the
new task includes that correction without modifying the original worktree.

The running Windows companion remains the approved Phase 2 installation, whose
source lacks `source-open` / `editor-save-all` and the Code-First editor module.
A hosted bundle correction alone therefore cannot enable complete source editing
and Save All on that installed companion. The reported hosted error matches the
verified release source; production was not changed or inspected using credentials.

## Files changed

| File | Fix |
|---|---|
| `developer_studio_page.py` | Explicit complete asset list includes `code-editor.js`. |
| `components/developer_studio/panel.js` | Reject missing/empty module text before Blob import; validate workspace `mount` before caching; identify failed asset. |
| `scripts/studio/ui/workspace.js` | Validate editor exports and companion capabilities; publish editor only after mount; display persistent source error; continue independent preview startup. Preserve partially recovered editor buffers and its canLeave/flush protection on mount failure. |
| `scripts/studio/ui/workspace.css` | Place the error inside the visible source workspace rather than below the full-height grid. |
| `scripts/studio/draft_ui.py` | Advertise versioned Code-First source / Save All support in the already authorised workspace model. No validation bypass. |
| `signin_presentation.py` | Carry forward the exact existing untracked Code-First dependency into this separate worktree/package; no original file or application draft changed. |
| `scripts/studio/test_codefirst_loading.py` | Focused hosted Blob-module, failure, compatibility and real Edge/Docker regression fixture. |

## Focused verification

- 11 source editor integrity/permission/conflict/recovery tests passed.
- 12 companion/UI tests passed. JavaScript module syntax, Python parsing and
  Git whitespace checks passed; Studio static verification passed.
- Actual rendered hosted bundle contains the complete editor source, byte-for-text
  equivalent to the shipped module; its exported mount loads in disposable Edge.
- Missing module, missing mount export, mount exception and Phase 2 companion
  mismatch each produce an on-screen error, disable source saves, preserve recovery
  storage and still invoke preview startup exactly once. Partial mount canLeave
  protection is retained. These failure-path previews use a bounded fixture frame.
- Real Windows Edge with the matching local server and exact Docker image:
  complete actual HTML/CSS, per-file Undo/Redo, two-file Save All, one saved
  revision and rendered synthetic preview passed. The same isolated container
  remained in use. Browser JavaScript errors: none. QA source restored exactly.
- Earlier harness cleanup raced a server-held registry lock. Only our verified
  dead QA process's lock and labelled QA container lease were recovered, and
  only our two QA edits restored from verified before-images. The harness now
  finishes server shutdown before source restoration. The final passing run
  logged a client disconnect during browser shutdown, without browser errors.

Results: `codefirst-loading-tests.json`. Runtime package hashes/identity:
`codefirst-loading-runtime.json`.

## Prepared Windows package — not installed

53 runtime files are staged outside the active installation at:

`C:/Users/hello/.codex/visualizations/2026/10/12/01a13216-edba-7c20-896a-70f604c44d7e/cf-fix-staged/v9-codefirst-loading-20261013`

All staged hashes match this source; companion, draft/source editor, preview and
trust modules import successfully. The module route and image pin are verified.
The existing tested Docker image is present:
`sha256:d74525e5ce7bd49a602399f6ac1e16476b9158bfaab00bb00703b42a85815baa`.
No image substitution or rebuild is required.

The package intentionally excludes installation of application `app.py` over the
existing draft. Existing revision 8, revision 6 history and actual application
source remain intact. Missing presentation files in an older draft remain subject
to the source catalogue's actual availability and existing permissions.

Existing companion: localhost 18762, PID 28132; logical task
`app-9ca4a85e-b3f4-4c85-b61e-4eb5551d2740`, logical owner `codex/v8-01a12f62`.
Windows task `SportsCave-Studio-20261011-7192d493`, Windows owner hello;
configured interpreter is the original repository `.venv/Scripts/pythonw.exe`,
underlying executable `C:/Python314/pythonw.exe`. It continues running
`v9-performance-phase2-20261013` from the original V8 registry home.

Trust expiry, immutable default application ID, revision 8 and original source
preservation checks passed. No actual browser recovery storage was opened or
altered. Authentication, owner/grant/expiry/source/lease checks, DPAPI, isolation,
silent subprocesses, persistent relay and original startup settings are preserved.

## Remaining release steps

Both a separately approved hosted release containing the complete bundle and a
separately approved matching Windows companion upgrade are needed for everyday
hosted Code-First editing. Phase 2 remains preview-compatible but cannot provide
the new source/Save All protocol. The corrected interface explains this mismatch.
Normal trusted Edge against the installed 18762 runtime has not been upgraded or
certified as Code-First: testing used a disposable profile and sanitised QA copy.

Before installation: confirm active work is saved/closed, reverify package hashes
and identity, back up the existing runtime and task XML, obtain owner approval for
the exact startup action, then use the existing stop/resume lifecycle and rollback
to the backed-up Phase 2 action/runtime on failure. Preserve all registry/trust,
draft and session files. No task action, active runtime, application source, GitHub,
Render or production business data was changed by this fix.
