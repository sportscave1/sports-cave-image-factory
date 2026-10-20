# Windows Recorder V1 — overnight handoff

Status: unfinished development checkpoint. Do not deploy or install this revision.
The user ended physical trials for the night. No more trials were requested.

## Verified local results
- Separate physical Edge text recording/save/reload/playback, with actual final value confirmed.
- Separate disposable Notepad text recording/playback, with actual document text read back.
- Physical Pause/Resume excluded paused edits; Stop flushed the focused field.
- Durable drafts, receipts and run journals; saved definitions stayed unchanged in the verified trials.
- Focus/readback failures were preserved rather than replayed automatically.

## Latest state
The combined trial has NOT passed. The latest preserved draft contains Edge text
"Edge focus race" and no Notepad action, despite the conversational report of success.
It stopped on taskbar switching. Evidence remains local under
`evidence/v1-taskbar-switch-before-support/`; recordings and recovery archives are
intentionally excluded from Git.

The latest native candidate adds a bounded taskbar transition to an already-open
window, validates process/window identity, and records a semantic focus action.
This new path compiled but has NOT had a physical acceptance trial. Menus,
previews, newly opened windows and ambiguous transitions still interrupt.
The previous browser focus race now waits up to 150 ms for the editor; it never
anchors RootWebArea as a text field. Real Edge typing passed before the taskbar
change. Save controls now require explicit review of interrupted drafts.

## Required work, in order
1. Review the new taskbar transition and validate one combined Edge/Notepad capture.
   Save, restart, reset prepared context and play once; inspect actual values and
   immutable revision. Stop immediately on any failed/uncertain action.
2. Finish real Task Recorder UI integration through DeviceAgent/relay and durable
   receipts. Local adapter tests are not end-to-end UI evidence.
3. Complete selection/toggle/button/menu/scroll support honestly. Invoke currently
   yields an uncertain result without an application-specific postcondition.
4. Actual Product Uploads components with synthetic providers: Generate, readiness,
   embedded Copy and exact clipboard verification. This remains incomplete.
5. Emergency Stop, manual intervention, protected input, provider failure/overflow,
   moved-window/DPI and disconnect recovery trials on the final candidate.
6. Native idle/record/play CPU and memory outside inspection; bounded save latency.
7. Reproducible native/Python package, startup/update and rollback preserving all
   data. Hosted download packaging and installed-helper integration remain unfinished.
8. Final diff review against current main, integrated acceptance and Studio release
   workflow, then compatible Render deployment and recorder-only helper update.

## Production and ownership
No Render deployment, main merge or installed helper replacement was performed.
Photoshop/Edition Ops jobs and settings were untouched. The feature branch is a
checkpoint only. Original owner handoff commit: 4e1bc88b6505db1a2b2e92e71902a6df65594c25.
Original uncommitted experiments remain in their owner worktree, untouched.
Release task: 20261020-ff6cc91d, owner codex-windows-recorder-release-01a1589a.

## Tomorrow
Start from this handoff and the preserved local evidence, not from another full
assessment. Native computer-use input has demonstrably targeted the wrong window;
do not bypass that restriction with custom probes. One concise user physical trial
will be needed after independent fixes. Do not claim injected input as physical proof.
The development launcher requires the existing local Python environment; it is not
an installer. Recovery archives are not runtime dependencies. Tests now also load
the normal reviewed package instead of extracting recovery archives.
