# Task Recorder editing — local implementation, 20 October 2026

Worktree: `C:\Dev\SportsCaveWorktrees\sports-cave-integrations-local-task-recorder-v1-20261019-64cdf0b0`.
Branch: `codex/task/integrations-local-task-recorder-v1-20261019-64cdf0b0`.
Task: `20261019-64cdf0b0`; verified owner: `codex-task-recorder-20261020-01a15682`.
HEAD remains `23103faf617d2cecd4e60b0bf5a4f36d4f3c4455`.

The unfinished measured-performance changes present at the start remain in place.
This phase does not release them, change production, install a helper, or touch
Edition Ops, Photoshop, products, ads, email or unrelated workers.

## Use

Choose **Edit** beside a recording. The existing page displays a numbered action
list, with ordinary labels and values. Back / Cancel leaves the original alone.
The copy name defaults to `[original name] — edited` and can be changed.

- Change entered text, website addresses, dropdown values or checkbox choices.
- Choose a replacement upload through the recorder PC's existing native file
  chooser. Only its opaque local reference travels through the authenticated
  relay; no hosted server filesystem is involved.
- Select one or several unwanted actions and Delete selected, or Delete step.
  Undo restores previous action sequences and value edits (30 draft snapshots).
- Set Keep from step / through step and Keep this range. The numbered list
  immediately shows exactly what will be saved.
- Replace by recording opens/reuses the marked dedicated browser. A closed
  browser starts at the nearest preceding recorded website. An already prepared
  browser keeps its current page/state. Perform the replacement and Stop
  replacement, then review/select the captured actions before insertion. Exclude
  its initial navigation when that is not part of the intended replacement.
- Add a visible-text or expected-address readiness check at a chosen position.
  Checks use the existing 30-second maximum and unique-target semantics.

Save edited copy validates the draft and waits for the helper's durable receipt.
The new recording appears in the ordinary table; it does not play automatically.
Its result is Never run; the helper clears previous playback progress/status.
The original JSON, metadata and result are unchanged. The new task has a fresh
ID and revision, no result history and no recorded duration. Original capture
duration remains separately in `source_duration_ms` provenance; there is no
invented playback estimate or modified playback timing.

## Safety and compatibility

The editor imports existing steps by source ID, revision and position. It cannot
upload selectors, scripts or replacement action implementations. Value changes
and inserted readiness checks pass the existing schema/URL/privacy validation.
Remaining unsupported/interrupted actions retain their reason and still block
playback. Validation errors appear beside the affected numbered action; the
draft/name remain available for correction.

Editing, file selection and replacement recording are fenced against stale
source revisions and active recording/playback at both relay and helper. The
existing command receipts, ownership checks, control lock and Stop fence are
reused. A Save command has a deterministic new task ID derived from its command
ID; duplicate command receipts survive helper restart. No automatic replay or
retry of uncertain runs is introduced. Definitively rejected enqueue requests
can be corrected/retried; uncertain dispatched commands retain their identity.

Editor commands require **helper protocol 4**. Protocol 3 retains ordinary
recording/playback and gives a clear update message on Edit. The setup endpoint
already packages all recorder assets, including the new module and validator.
The isolated local trial downloads and checks this package; it does not execute
its installer. The installed production helper remains unchanged.

Detailed steps and the small editor module load only on Edit. There are no new
polling loops, dependencies, screenshots or video capture in the product.
Playback, Pause, Resume and Stop use the existing runner without new defaults.

## Focused verification

Run from this worktree with the shared development venv:

```powershell
$py = 'C:\Users\hello\Documents\sports-cave-image-factory\.venv\Scripts\python.exe'
& $py -X utf8 -m pytest tests/test_task_recorder_editing.py tests/test_task_recorder_attention.py tests/test_task_recorder_upgrade.py tests/test_task_recorder_transport.py -q
node tests/task_recorder_editor_controls.cjs
node tests/task_recorder_panel_controls.cjs
node tests/task_recorder_transport.cjs
& $py -X utf8 -m tests.task_recorder_editing_trial
```

The standalone trial creates a fresh synthetic loopback PostgreSQL database,
full Sports Cave OS preview on **18967**, authenticated Windows helper on
**18938**, and separate task/vault/profile storage outside Git. It signs into
the real OS page and approves pairing through the actual PC approval flow.
Only harmless local demonstration form actions are performed. Both services
started by the test are shut down afterwards; no shared production helper is
stopped. The demo is not evidence of ad or other third-party automation.

Verified through the full application path: Record / Stop; trim both ends;
change product, URL, category and checkbox; delete / Undo / delete a mistake;
record, review and insert a headline replacement; choose a replacement PC file;
insert text and URL readiness checks; reject and correct a sensitive URL beside
its step; Save edited copy; refresh; Play from a closed recorder browser;
observe completed result and exactly one submission. Original bytes/metadata
remain unchanged. Active playback disables Edit. Installed helper source hashes
are checked without changing the installed files. Concurrent user activity in
live recordings is observed only and never restored or overwritten.

Expected actual local result:

```json
{"product":"Edited product","headline":"Replacement headline","url":"https://example.com/edited?category=sport","category":"art","approved":false,"file":"replacement-image.txt","submissions":1}
```

Focused automated checks also cover stale source/replacement revisions, durable
duplicate saves across agent restart, active playback/recording exclusion,
protocol gating, ownership rejection, flag retention, PC file references,
reusable-input collision handling (including legacy 50-input tasks), no inherited
Completed status/duration, preservation of a prepared replacement browser, and
uncertain command identity retention. Existing attention/correction, upgrade,
transport and Pause/Resume control regressions are reused; the entire Phase 2
acceptance programme is not repeated.

Evidence and the **prepared, uninstalled** ZIP live below:
`C:\Users\hello\AppData\Local\SportsCaveOS\TaskRecorderEditing-64cdf0b0\`.
Each disposable run has `evidence.json`, editor/table/result screenshots,
readonly installed-file hashes and `SportsCaveTaskRecorder-local-editor.zip`.

Final frozen-source verification: **30 pytest checks passed**, all three Node
control/transport checks passed, JavaScript syntax and Studio verification passed.
The final full application trial passed at
`C:\Users\hello\AppData\Local\SportsCaveOS\TaskRecorderEditing-64cdf0b0\edit-f1a60239`.
Its edited copy `945997f9-3e61-5513-8482-3ec254250e38` completed all 11 steps,
including replacement upload and both readiness checks, with the result above
and one submission. Original `fd391380-5b95-4af8-aa07-a9451f45f2ce` JSON/metadata
were byte-identical. Installed helper sources were unchanged; that final run
also observed no concurrent live-data changes. The test services were stopped.

## Files for this phase

- `task_recorder/editor.js` — lazy in-page draft editor and replacement review.
- `task_recorder/editing.py` — fixed edit format, revision fences, schema/privacy
  validation, source-step import and reusable input/default copy handling.
- `task_recorder/panel.js`, `panel.html`, `panel.css` — row Edit, embedded editor,
  compatibility/active guards, acknowledged Save selection and validation retry.
- `task_recorder/device.py` — protocol 4, copy/file/replacement controls, per-step
  errors and inspect revision; uses the existing runner and local store.
- `task_recorder/relay_store.py`, `hosted_api.py` — authenticated command allowlist,
  helper version/active guards, bounded validation errors and lazy editor asset.
- `tests/test_task_recorder_editing.py`, `task_recorder_editing_trial.py`,
  `task_recorder_editor_controls.cjs`, `task_recorder_panel_controls.cjs` — focused
  contracts, full app trial and existing control regression coverage.
- This report. Other dirty files belong to the preceding performance phase.

## Limits

Replacement captures are retained as separate saved recordings. They can be
deleted with the existing trash action after the edited copy is saved; the copy
then contains independent steps. If replacement actions require earlier page
state, prepare that state manually with recording off; the editor does not
replay preceding actions automatically. Replacement steps are reviewed before
insertion, including any unsupported/interruption warnings.

Dropdown edits use the website's option value; choices are validated against
the existing action schema, and the site must offer that choice at playback.
Selectors remain hidden and cannot be typed: use Record replacement for a
different target. V1 has no optional sleep/delay action, so there is no delay
slider; required readiness timeouts and playback defaults are unchanged.
Unsaved drafts/Undo are page-local and are discarded on navigation/refresh;
saved copies and replacement recordings are durable.

Status: Implemented locally. Not committed, pushed or deployed.
