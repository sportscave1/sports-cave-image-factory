# V8 connection repair — local only, 13 October 2026

## Confirmed local identities and findings

CORE task: `20261012-v8`, owner `codex/v8-01a12f62`, branch
`codex/task/core-v8-os-drafts-20261012-v8`, HEAD `c6b1c82ab51b915bf7d9e31b4b99ce3f1801e4b7`.
The CORE worktree was clean before this repair. The repository's primary checkout
and all other worktrees' unfinished source were left alone.

Registered application: `9ca4a85e-b3f4-4c85-b61e-4eb5551d2740`, internal task
`app-9ca4a85e-b3f4-4c85-b61e-4eb5551d2740`, same owner. Its persistent registry
home is the CORE worktree's parent `v8` directory, **not** `C:/Dev/SportsCaveWorktrees`.
Its stable companion endpoint is `http://127.0.0.1:18762`.
The older V5 companion on 18761 is a different home/task/owner and cannot discover
this separately registered application. Neither companion was deleted or reassigned.

Both registered Windows tasks were running. V8's approved action is under the
historical name `SportsCave-Studio-20261011-7192d493`, invoking V8 `companion.py`
with the application task and owner above through `.venv/Scripts/pythonw.exe`.
The V5 task `SportsCave-Studio-20261012-54a08610` belongs to `me/studio-companion-v5`.
Both use sign-in plus minute recovery triggers, interactive limited privilege,
IgnoreNew, no execution time limit and three one-minute scheduler retries.
Multiple Python PIDs include Windows virtual-environment launcher processes;
they do not prove multiple serving workers. Port listeners and session PID were checked.

V8 has an unexpired, user-scoped DPAPI trust enrollment for
`https://sports-cave-image-factory.onrender.com`. Edge's configured profile is
`Default`. This session cannot control that everyday Edge profile, and its cookie
database metadata was unavailable. **The precise missing/stale cookie in that
profile is not confirmed.** No cookie values were extracted or printed.

Confirmed code defects: stale saved 18761 addresses could route the V8 panel to
the incompatible older registry; renewal committed rotation before delivering
Set-Cookie, so a lost response stranded the browser secret; default selection
depended on browser storage and arbitrary catalog order; startup operations used
task name alone, missing the approved alias and permitting insufficient ownership
checks on removal; background Git/Docker subprocesses had no CREATE_NO_WINDOW.
The latter is a confirmed console-launch mechanism. No attribution of each
observed PowerShell popup to a particular process is claimed. The untouched V5
implementation can still spawn visible subprocesses.

## Local changes

- Persist the last locally confirmed application ID by owner. Verify registry,
  branch/worktree identity and source provenance before restoration. Otherwise
  prefer descendant verified source revisions, then deterministic copy timestamps.
  Technical tasks, archived copies and other owners cannot become defaults.
- Display actual worktree HEAD, saved draft revision, dirty status, freshly verified
  Live SHA and ancestry comparison. Live is `cbd1c9db2d47c3bc202f771e78ed0ab78750c5f8`,
  deployment `dep-db6kqp67bikc73c6isc0`, confirmed by read-only authenticated Render
  and exact GitHub main. The existing copy remains clean at `c6b1c82ab51b915bf7d9e31b4b99ce3f1801e4b7`,
  saved revision 6; **Live is newer**. Only the local Live receipt was refreshed.
- Keep the explicit reviewed/confirmed Update Draft from Live operation. No update
  was applied. Dirty or diverged copies still fail closed, with source/review
  fingerprints, exact revision confirmation and recovery branch protections.
- Make a lost renewal response retry return the same replacement for a fixed
  60-second interval, surviving worker restart through DPAPI. Retrying does not
  extend that interval or the original 30-day enrollment expiry. Tokens remain
  short-lived, cookies HttpOnly/SameSite=Strict, and exact origins, ownership,
  fresh launcher approval, one-use setup tickets and revocation checks remain.
- Retry temporary connection failures without falsely reporting missing trust.
- Match startup helper, home, task, owner, interpreter and single action before
  Start/Enable/Disable. Recognise the approved historical-name alias without
  creating, overwriting, renaming or removing any task.
- Hide Windows Git/Docker subprocesses. `OpenRegisteredV8.vbs` provides an explicit
  hidden one-click authenticated launcher for the existing V8 identity in Edge
  Default. It only opens approval; it cannot grant trust without the local button.

Changed implementation files: `components/developer_studio/panel.html`, `panel.js`;
`scripts/studio/Companion.ps1`, `companion` setup launcher `OpenRegisteredV8.vbs`,
`application_drafts.py`, `device_trust.py`, `draft_ui.py`, `studio.py`,
`preview_boundary.py`, `preview_runtime.py`, `releases.py`, `ui/pair.js`.
Tests: `test_application_drafts.py`, `test_companion.py`,
`test_workspace_selection.cjs`, new `verify_v8_trusted_reopen.py`.

## Verified tests and operational result

- 76 Python tests: application lifecycle, DPAPI, authenticated setup, expiry,
  bounded rotation retry, revocation, cross-origin protection, ownership,
  dirty/diverged Update from Live refusal, editor and workspace operations.
- Three Node protocol suites: pairing, trusted renewal and workspace/default
  selection; registry selection wins over conflicting browser selection.
- Actual installed Edge: disposable V8 lifecycle, Save Draft, rename/duplicate,
  reopen with unsaved recovery, owner isolation and archive retention.
- Actual installed Edge with a disposable **persistent profile**: authenticated
  one-time trust, full Edge close/reopen plus companion restart, trusted renewal,
  same immutable default ID and saved source restored; 30-day expiry unchanged.
  Local editing confirmation remains required; no repeated draft selection.
- Actual **existing V8 application copy**: automatic default selection and real
  editor loaded in isolated Edge against the registered 18762 companion and a
  local candidate OS panel. Verified newer-Live display. Source hash, HEAD and
  clean worktree unchanged. Save Draft writes were tested in disposable copies.
- Actual existing V8 application: Docker synthetic raster preview, desktop
  1280×900 and mobile 390×900, stopped afterwards; source/hash/HEAD unchanged.
- Controlled termination of only the authenticated V8 worker, with no previews
  active: approved supervisor recovered the same task/owner/port with rotated
  bootstrap. The old V5 worker was untouched.
- Approved startup alias Start succeeded. Synthetic ownership tests reject a
  foreign owner/task/home/helper/interpreter or extra action without task mutation.
- Git diff formatting and PowerShell syntax verified.

Evidence is in the original repository's `tmp/v8-regression.log`,
`v8-edge-lifecycle.json`, `v8-persistent-edge.json`, `v8-existing-editor.json`,
`v8-registered-preview.json` and accompanying screenshots. Acceptance scripts
in `tmp/verify_v8_*` record the exact operational scopes.

## Remaining real-profile gesture and limits

The existing application **opens correctly by default in the local candidate**.
Everyday Edge/hosted OS reopening has not been personally verified in this
session. If its trust cookie is unavailable, open `scripts/studio/OpenRegisteredV8.vbs`,
click **Trust this Edge profile and connect**, then use **Connect local device**
with `http://127.0.0.1:18762` in the signed-in OS. The local draft editing grant
still needs its explicit local confirmation. Browser-required popup gestures
and permission expiry remain intact. No credentials need copying.

An actual Windows sign-out/sign-in was not performed; the existing trigger,
approved startup action, duplicate protection and crash recovery were checked.
No scheduled task was removed or overwritten. Changing the older V5 registration
requires its owner's specific approval. Hosted frontend changes remain local;
production does not receive this repair without a separately authorised release.

No commit, push, merge, deploy, publish, production mutation or edition-data change.
No existing application source update, reset, stash, clean or worktree removal.
