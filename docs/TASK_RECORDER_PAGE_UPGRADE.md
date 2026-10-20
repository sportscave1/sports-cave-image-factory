# Task Recorder embedded page upgrade — 20 October 2026

Developer → Task Recorder now opens the complete page immediately. Enter a new
recording name and optional starting website, Record, demonstrate actions in the
marked dedicated browser, then Stop to save automatically. Select or Play a saved
row. Pause, Resume and Stop stay tied to the active run even when another row is
selected. Navigating away does not dispatch any control.

The previous modal, Open recorder button, dropdown and Advanced accordion are
removed. Settings exposes connection management, opt-in Windows startup and
labelled reusable inputs. Each compact row has Play, inline Rename, an accessible
trash icon with inline Delete/Cancel, duration, steps, local saved/updated time
and acknowledged status. Duplicate names have copy labels and saved times; IDs
remain internal. The toolbar stays visible during OS page scrolling. No new UI
framework, streaming or continuous preview was added.

## Correctness and compatibility

The old page did not send a name with Record; the helper unconditionally generated
one. Rename previously used whichever draft happened to be loaded. The page now
sends `record.name`; the helper creates a fresh UUID and preserves that name
through Stop/autosave. Rename, inspect, reusable inputs, Play and Delete target
explicit task IDs. A default timestamp name is generated only for a blank name.
New-recording fields are independent of selection and are retained on errors.

Task JSON remains V1 and existing revisions/names are preserved. Optional `.meta`
sidecars store real recorded duration in milliseconds and last save/update UTC.
Duration excludes recorder pauses and browser preparation; it does not change
playback timing. Legacy tasks without timing show “—”; step count is measured
from the stored steps. Times display using the viewer's local timezone. Summary
caching avoids rereading every task's full contents on each heartbeat. Detailed
values are fetched only for the selected reusable task or when requested.

Deletion uses the same authenticated, owner-scoped, durable command architecture.
A durable local tombstone prevents interrupted cleanup or stale responses from
restoring a deleted row. Only that task JSON, metadata, result, matching checkpoint
and reusable defaults are removed. Original upload files, file references, profile,
sessions, pairing and other recordings are retained. Both relay and helper reject
active-task deletion with “Stop this task first.” Duplicate receipts remain
idempotent. A deleted ID cannot be saved or replayed again.

Pause reports Pausing while an action is dispatched, then acknowledges Paused at
a safe gate. Resume opens that gate without resetting the loop index. Stop retains
its existing cancellation priority. The page uses actual helper state and durable
receipts, retains pending command IDs across navigation, and never automatically
submits a fresh start during reconciliation. One bounded state long-poll loop is
used; short receipt polling runs only while a command is awaiting acknowledgement.

The helper advertises protocol 2. The new page clearly requests an update for old
helpers and disables unsupported table mutations/start controls; emergency Stop
and View browser remain available. Old command formats remain accepted by the new
helper. Install the updated helper only after the backend supports its state fields.
The downloadable authenticated setup zip includes the same updated helper source.
`python -m task_recorder.install` performs the existing safe idle upgrade and
retains `%LOCALAPPDATA%\SportsCaveOS\TaskRecorderV1` data/profile/DPAPI pairing.
Pausing is now also considered active by the installer.

## Focused verification

- `tests/test_task_recorder_upgrade.py`: legacy metadata, real duration, ID rename,
  deletion/tombstone durability, preserved source/profile, active deletion, names,
  pause acknowledgement and strict command validation.
- `tests/test_task_recorder_relay.py`: existing real PostgreSQL security/receipt
  coverage plus old-helper rejection, active deletion, duplicate Delete and owner
  rejection. Uses only loopback synthetic PostgreSQL.
- `tests/task_recorder_page_trial.py`: full isolated app.py sign-in, real page,
  authenticated relay and Windows helper/browser. Records “Clicking to Home” via
  a real navigation click, Stop/autosave, metadata, one-click Play, inline rename,
  refresh/restart persistence and disposable deletion. A multi-step local fixture
  checks Pause/Resume/Stop, changing selected row, active deletion, no repeated
  completed fill, reopening the page while paused and disconnected feedback.
- Existing recorder/sidebar/auth/navigation coverage is retained. Prior Phase 2
  acceptance and human trial remain documented in TASK_RECORDER_PHASE2.md; no
  universal browser or Meta ad automation claim is made.

Preview: `http://127.0.0.1:18962/?page=task_recorder` using
`scripts/task_recorder_preview.py --root %LOCALAPPDATA%\SportsCaveOS\TaskRecorderPage-Preview-64cdf0b0 --port 18962`.
It uses synthetic local storage and blocks external/provider I/O. Test helper port
18932 is separate from the user's installed helper port 18931. Evidence/screenshots
are under `%LOCALAPPDATA%\SportsCaveOS\TaskRecorderPage-Acceptance-64cdf0b0`.

Changed files: `task_recorder_page.py`; `task_recorder/panel.html`, `panel.js`,
`panel.css`, `device.py`, `runner.py`, `store.py`, `relay_store.py`, `install.py`;
focused tests and these docs. No edition allocation, Photoshop/companion code,
worker queues, Render topology, database migration or provider data is changed.

Focused verification passed: 36 tests and 14 subtests; JavaScript syntax,
Studio static/secret checks and canonical Render topology validation passed.
The full isolated page trial passed name/metadata, exact playback, inline rename,
disposable deletion, helper restart, paused-page reopening, active deletion
protection, Resume without repeated steps, Stop and disconnected feedback.

Live HTTPS verification also passed: embedded interface/table, explicit outdated-helper
message, installed helper upgrade/reconnection, supplied-name recording/autosave,
row Play, inline Rename surviving refresh and durable disposable deletion. All 11
pre-upgrade task hashes, pairing and profile identity matched immediately after
upgrade. The user subsequently confirmed deleting the older recordings themselves;
those deletions were preserved. Only the agent's disposable release task was removed
by this release check.

A 1004px desktop layout check confirms the table has no horizontal overflow and
all actions fit. The toolbar stays at 64px below the OS header when the page is
scrolled. Page-specific OS padding uses the available width; no global navigation
or unrelated page source is changed.

## Remaining limitations

Supported actions and privacy protections are the existing Phase 2 set. Unsupported
actions remain blocked; repair/technical diagnostics stay in the local diagnostic
console. Native file reselection may require a Windows dialog. Missing targets or
uncertain submissions require inspection; completed actions never auto-replay.
Offline detection follows the existing 35-second heartbeat threshold plus the
bounded OS poll response, rather than pretending to know immediately. Existing
recordings without duration retain “—”. The helper and session stay on Windows.
