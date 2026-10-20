# Task Recorder playback investigation — 20 October 2026

Local implementation in task `20261019-64cdf0b0`, existing owner
`codex-task-recorder-20261020-01a15682`. Studio Open verified the registered path
and branch `codex/task/integrations-local-task-recorder-v1-20261019-64cdf0b0`.
HEAD remains `23103faf617d2cecd4e60b0bf5a4f36d4f3c4455`. Existing uncommitted
editor and performance work was preserved. No companion Phase 4 worktree was used.

## Confirmed failure and available trace

Read the installed task files and command SQLite database read-only; did not
instantiate Store against production data (its constructor reconciles journals).

“Click Generate Mockups & Copy Black Frame Prompt — corrected”:

- ID `42651c21-21d0-4bb5-90ae-128d6ae907cc`.
- Revision `2fcfdb14c078f36e163ce9249c128ff1607fedcc8cc9bb6c2e2a1a87db32ecf9`.
- Exactly three saved steps: navigate to `?page=product_uploads`; wait for exact
  text `Copied` for up to 30 seconds; click test ID `stBaseButton-primary`.
- No PSD binding, upload workflow reference, Generate Mockups action or named
  Copy Black Frame Prompt action is present.
- Command `63951a99-a69f-422c-ae3b-c1e3f49c6766` has an **applied** helper receipt.
  The result carries that operation ID and the same revision, status stopped,
  zero-based step 1, at 19:31:24 Sydney time. Navigation finished; the saved run
  did not finish step 2. The wait precedes any action capable of creating Copied.
  It cannot restore the selected PSD merely by navigating to Product Uploads.
- Code trace: panel `play(id)` sends selected ID/revision; authenticated relay
  queues Play; DeviceAgent applies it under the control lock, loads the exact task,
  resolves local bindings and calls Runner.play; Runner loads the saved revision
  again and runs its saved steps. Play never enables recording. The browser badge
  labels the dedicated browser in both modes.

A separate “Open Chat GPT” recording (`7424b068-8d60-42ba-9e19-f3dc7711aa68`)
has an applied receipt for `036d562c-4775-4b6b-96c6-a94d704864d2`. Its journal
explicitly reports **127 matches** at step 2 for `stBaseButton-secondary`.
The capture script chose framework test IDs before accessible button names.
That is a confirmed target-selection defect, not a browser launch failure.

The corrected recording's metadata identifies source
`5e234c94-5215-4000-90a7-01572661bc8b`, corrected step 2. That original definition
is no longer among the installed saved JSON files. We cannot reconstruct the
historical original iframe event or PSD selection from these surviving records.
The installed runner rejected all actual child-frame interactions; replacing
such a flag with a wait does not reconstruct the missing interaction.

No historical frontend/relay snapshot was retained for the reported contradictory
Stopped/“Stop this task first” display. Its exact historical timing is not
provable. Terminal runner state did retain `run_id`; it now clears ownership on
Stop and advertises an active ID only while a job is actually owned. Existing
relay operation/version fences and acknowledgement reconciliation remain intact.
Regression tests verify stopped tasks can be renamed, stale snapshots do not
roll back progress, duplicate starts are rejected and Stop clears relay ownership.

## Installed versus local versions

Installed `record.js`, `schema.py`, `runner.py`, `device.py` and `panel.js` match
the separate editor release checkout byte-for-byte after newline normalization.
Its release evidence identifies commit `c256c385ac17986023fcf99f641c22be0abb3565`,
protocol 4. This is the previously tested editor release, not the unreleased
performance implementation in this worktree. Before this change, installed
capture/schema matched this worktree; runner/device/panel differed because the
performance phase was intentionally excluded from that release.

This investigation did not deploy, query production providers, stop the installed
helper, replace its package, change saved production recordings or create any
“corrected” production copies. Tests fingerprinted installed helper files.

## Changes in this phase

- `task_recorder/record.js`: prefer unique accessible names/labels and stable IDs;
  reject shared Streamlit test IDs. Check uniqueness synchronously before the
  page rerenders. Flush the previous pending field before a different input;
  avoid capturing the same input event again on blur. Await outstanding binding
  deliveries at Stop and report failed delivery instead of silently losing it.
- `task_recorder/schema.py`: validate bounded frame paths containing only
  unique id/name/title identities, never CSS supplied by a page.
- `task_recorder/runner.py`: serialize capture callbacks; identify same-origin
  embedded frames without frame positions; restore file bindings in their owning
  frame; flush all frames before save. Passive frame navigation remains inert.
  Recheck frame origin before replay; missing/ambiguous frame waits are bounded.
  Show step, target and actionable failure; publish progress as steps start.
  Clear stopped ownership and never append playback to the saved sequence.
- `task_recorder/attention.py`: flag legacy shared framework targets and missing
  Product Uploads source prerequisites before browser launch. Recognize recorded
  uploads or the application's existing exact `upload=<UUID>` recovery URL.
  A fresh navigation invalidates preceding session-only source assumptions.
- `task_recorder/panel.js`: display the runner's step/target progress and disable
  misleading wait corrections for missing source/target information. The existing
  Edit/Record flow is required to supply real information.
- New focused checks: `tests/test_task_recorder_playback.py`,
  `tests/task_recorder_playback_controls.cjs`,
  `tests/task_recorder_playback_fixture.py`,
  `tests/task_recorder_playback_trial.py`.

The other dirty files predate this phase.

## Verification

Used the shared development Python environment. Full isolated app previews use
the existing environment allowlist, loopback synthetic PostgreSQL, external-I/O
denial and disposable storage. Production credentials/data are not loaded.
All test-created helper/app/fixture services are closed afterwards.

56 pytest checks and 14 subtests passed across `test_task_recorder`,
`test_task_recorder_attention`, `test_task_recorder_editing`,
`test_task_recorder_transport`, `test_task_recorder_playback`,
`test_task_recorder_navigation`, `test_task_recorder_relay` and
`test_task_recorder_upgrade`. Four Node control/editor/transport suites and
capture JavaScript syntax passed.

Coverage includes missing/ambiguous targets, missing frames, cross-origin frame
rejection, passive frames, dynamically inserted password fields, unavailable local
file references, bounded waits, delayed targets, Pause/Resume/Stop, duplicate Play,
terminal ownership, stale revisions/receipts/snapshots and unchanged originals.

Actual app/authentication/relay/PC approval form trial:
`TaskRecorderEditing-64cdf0b0/edit-a0a3e6f5` under LocalAppData/SportsCaveOS.
Source `d3cb8145-c159-42a3-a064-6c85a03ac809`, played edited task
`a1862983-6b66-54e3-8ba1-3b81ac12415d`: real navigation, recorded fields,
selection, checkbox, replacement file, Save, refresh and cold-browser Play
reached the expected form result with exactly one submission. Source bytes
remained unchanged. The editor regression is retained.

Final Product Uploads interaction trial:
`TaskRecorderPlayback-64cdf0b0/play-1ec21a31` under LocalAppData/SportsCaveOS.
Actual app UI Record → Stop/save → helper shutdown/restart → app reload → one
Play; no direct runner Play shortcut. Task
`c5ec2bda-78c2-434e-aecc-3d3d016b708f`, revision
`00040632e4eee3f239d3db153baef773d59a0f661a36612b4e76b7379d4afac1`,
operation `0e4ff95d-1a50-480c-92a0-877131cb6c88` completed eight steps.

The synthetic fixture includes 127 distracting framework button IDs, a file
chooser, normal form controls and a delayed same-origin embedded copy button.
Observed result: source `synthetic.psd`, product `Local sample`, category `art`,
approved true, `Mockups generated: 1`, final embedded input
`Flushed final value`, and actual browser clipboard read
`Synthetic black frame prompt`. Saved sequence bytes stayed unchanged during
playback. Evidence includes exact run/revision, saved actions and screenshots;
the real app screenshot visibly shows Completed and enabled Play/Edit controls.

The fixture simulates generation and uses synthetic file contents; this is not
evidence that production Photoshop rendering or live Product Uploads jobs ran.
Those were intentionally not invoked. Browser automation does not lock the mouse.

## Recovery and limits

The affected saved recording cannot be faithfully repaired from its three steps:
the PSD identity and intended button identity are absent. Preserve it as evidence.
Rerecord from Choose PSD through Generate Mockups and Copy, or supply the exact
authorized upload recovery URL and record the named actions. An unavailable
recovery ID remains subject to the application's access/source validation and
will block at the exact missing/disabled target; the runner does not bypass it.
Existing waits can be retained only if they reflect a real readiness condition.

Frame playback requires a unique id/name/title and a same-origin document
(including the parent's srcdoc/about:blank documents). Unidentified or external
frames remain explicit unsupported steps. Dialogs, new tabs, gestures, rich text,
and unsupported keyboard workflows retain their existing limitations. No universal
session reconstruction or arbitrary third-party automation is claimed.

Status: Implemented locally. Not committed, pushed or deployed.
