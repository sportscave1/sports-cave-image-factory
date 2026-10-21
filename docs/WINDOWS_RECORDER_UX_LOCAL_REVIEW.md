# Recorder library and popup — local UX review

Task: `20261021-e54cebc7`; owner: `codex-recorder-ux-20261021`.

Verified worktree:
`C:\Dev\SportsCaveWorktrees\sports-cave-integrations-simplify-windows-recorder-popup-and-record-20261021-e54cebc7`

Branch: `codex/task/integrations-simplify-windows-recorder-popup-and-record-20261021-e54cebc7`.
Base: `5b9deb01d6bf5db455746de725af9bb63e98b6e3`.

This task reuses the released recorder, authenticated relay, durable receipts,
capture barriers, native playback confirmation and recovery. It does not replace
the installed helper, rebuild the shipping download, commit or deploy.

## Workflow

- New recording opens the Windows popup. Choose the window when necessary, Record,
  Stop, then Save recording. A dated default name is selected and editable.
- Library Play restores the popup with that immutable revision ready. Press Play
  there to grant Windows foreground control; then use Pause/Resume or Stop.
- Reopening the popup preserves active capture, playback and draft state. The
  `open-popup` relay command does not reserve a new run or change operation identity.
- Stop remains available during pending Pause/Resume acknowledgements. Conflicting
  starts and duplicate pending starts are disabled.
- Interrupted drafts still require explicit review. Discard remains explicit.

## Surface changes

The page shows Windows recordings with name, updated date, status and Play. Rename,
Edit and Delete live in a small row menu. Windows action editing remains disabled
and explained: changing steps requires a new recording. Rename updates a separate
library label; Delete hides the item while retaining its definition for recovery.
Neither changes saved action bytes or revisions.

Advanced contains connection/startup/update controls and the older browser library
with its existing playback, values, editing and correction tools. The user chose
to retain these compatibility tools. Normal Windows recording no longer asks for
a page name, starting website, mapping or browser setup. Legacy active controls
remain available even when another library row is selected.

The popup is compact, uses the OS palette, shows state-specific controls, retains
the selected recording after Save, and preserves the selected window on refresh.
Saved recording selection, window inspection and the emergency hotkey hint are in
Details. No new dependency or background poll loop was added.

## Changed files

- `task_recorder/panel.html`, `panel.css`, `panel.js`: library, menus, Advanced,
  state rendering, popup handoff and iframe sizing.
- `task_recorder/device.py`, `relay_store.py`: capability-gated popup opening and
  native library management through existing durable commands.
- `windows-screen-recorder/desktop_recorder/helper.py`, `coordinator.py`,
  `lifecycle.py`: popup reopening, current context, default name, native Save flow.
- `windows-screen-recorder/desktop_recorder/integration.py`, `catalogue.py`,
  `playback.py`: metadata-only labels/removal; archived definitions remain readable
  for journal recovery, while normal playback lookup rejects removed entries.
- `windows-screen-recorder/native/Host.cs`, `ToolbarPresentation.cs`, `build.ps1`:
  native presentation and control availability; existing capture/executor retained.
- `tests/test_task_recorder_library_ux.py`, `tests/test_task_recorder_transport.py`,
  `windows-screen-recorder/tests/ToolbarPresentationChecks.cs`: focused lifecycle,
  immutability, relay identity and popup control checks.
- `tests/fixtures/recorder_library_preview.py`: disposable loopback presentation
  fixture serving the actual panel assets; no desktop input or real helper data.

## Verification and limits

- Focused Python suite: 56 tests and 6 subtests passed (adapter, transport,
  capabilities, foundation, playback, receipts and library lifecycle).
- Node transport checks: five groups passed; panel JavaScript syntax passed.
- Native candidate compiled into ignored `.local-data/recorder-ux/`.
- Pure native presentation checks: 18 passed without Windows input/inspection.
- Browser review used actual assets with synthetic rows: New recording handoff,
  inline Rename, menu rendering, Play readiness, conflicting controls disabled,
  offline explanation and legacy tools under Advanced.
- Screenshot: `.local-data/recorder-ux/library.png` (synthetic presentation only).

At the initial local checkpoint, physical acceptance of the revised popup was
pending. The full-OS follow-up and physical trial below supersede that checkpoint.
Automated adapter/presentation results are distinct from physical input evidence.

## Full OS follow-up, 21 October

The production page was inspected read-only: the installed helper is connected,
the old UI remains live, and its three older browser recordings remain present.
The new UI has not been deployed.

The exact local candidate was then opened in the full OS app at loopback port
19022, using a separate synthetic administrator/database and a real DeviceAgent,
relay and native helper profile at port 19023. No production credentials or
recordings were copied into this test.

This caught a startup false positive: an already-open installed popup owned the
single-instance native mutex, so the candidate exited while the original command
receipt still said applied. The helper now waits for a readiness diagnostic from
its own native child before acknowledging popup opening. Early exit is rejected
with an instruction to close the other popup and try again. Capture never starts
automatically. Two focused startup tests cover the ready and early-exit paths;
the updated adapter/library set passes 15 tests and native compilation passes.

The early-exit correction was verified through the real full-OS UI and durable
receipt (`rejected`, actionable message), not the presentation fixture. Screenshot:
`.local-data/recorder-ux/os-startup-check.png`. After the user closed the old idle
popup, the new popup opened through the actual OS library and emitted its own
readiness diagnostic. Its source executable path was verified in the task worktree.

The user physically recorded checkbox enabled and Second choice, pressed Stop,
edited the suggested name to "UX Live check", and saved. Inspection found exactly
three actions: focus the prepared Edge window, toggle enabled to true, and select
Second choice. The durable Save receipt matched the saved revision (2.75 ms save).

The full app also exposed a pre-existing stopped-session review flag after the
startup/disconnect checks, which hid Play despite the popup being Idle. The page
now offers Acknowledge Stop only for a stopped/idle recovery state. It uses the
existing fenced, durable Stop command; it does not clear review flags implicitly.
This action was verified in the real OS, enabling Play without changing the saved
recording. Node checks cover its visibility and offline/active-recording guards.

The saved recording was opened from the OS library. The popup waited at Ready to
play, with Play and Stop visible. After refreshing the Edge page, the user pressed
Play and reported Completed 3/3. The durable run journal independently confirms
three verified results, no pending action and the original saved revision. A
read-only screenshot of the physical Edge window confirms checkbox enabled and
Second choice selected. Saved file bytes remained unchanged through Stop and Play.

The current popup's minimize/restore and physical Pause/Resume during this short
run were not separately trialled. Their policy/adapter checks pass; the earlier
engine safety trials are retained as historical evidence. No new arbitrary-app
or generic-button capability is claimed by this UX release.

Operating instructions: [Task Recorder user guide](TASK_RECORDER_USER_GUIDE.md).
The user authorized Git/Render release and recorder companion update conditional
on successful validation. The above physical trial satisfies that acceptance gate;
exact-revision packaging, integration and deployment verification follow separately.
