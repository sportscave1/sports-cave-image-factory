# Windows Task Recorder V1

Local development candidate. Native recording and playback are implemented;
this revision has not been approved for installation or production release.
Work belongs to Studio task `20261020-ff6cc91d`, owner
`codex-windows-recorder-release-01a1589a`, in its assigned release worktree.

The recorder uses the existing Task Recorder panel, DeviceAgent, relay and durable
receipts. It captures supported interactions in prepared, already-open Windows
applications. Saved desktop recordings are immutable; results live in separate
journals. Pending unknown effects are preserved and never automatically replayed
following a disconnect or restart.

Local physical acceptance includes Edge/Notepad text and taskbar transitions,
Pause/Resume, focused-field Stop flush, checkbox/selection/menu expansion,
scrolling, Emergency Stop, manual intervention and protected-field exclusion.
Controls playback also passed on a second monitor after Edge's tab count changed.
The current candidate recorded and replayed the real embedded Product Uploads
Copy control with synthetic providers; the user's post-play clipboard paste
matched the expected prompt exactly. See [current evidence and limitations](V1-HANDOFF.md).

Text, toggle, selection, expansion and scroll results require fresh semantic
readback. General buttons are invoked once and then remain uncertain unless an
application-specific result can be verified. Product Copy has that verification;
general Generate button playback does not. Unsupported/ambiguous controls and
unclassified or protected text fields interrupt rather than guessing.

The native process uses UI Automation, explicit local Start playback confirmation,
bounded identity checks and Ctrl+Alt+F12 cancellation. Playback does not use
coordinate clicks or raw keyboard injection. Edge tab-count changes require an
independently verified top-level page; profile, executable and uniqueness checks
remain enforced. Local operation diagnostics measure CPU/memory and contain
neither clipboard contents nor field values.

## Local development

Use a disposable data directory and an existing Python environment with the
recorder requirements. This launcher builds the native development candidate;
it is not an installer and does not replace the installed helper:

```powershell
& windows-screen-recorder/Start-LocalRecorder.ps1 `
  -PythonExecutable C:\path\to\existing-env\Scripts\python.exe `
  -DataDirectory C:\path\to\disposable-recorder-data
```

The normal reviewed Python package is loaded directly. Recovery archives and
the historical Phase 1/2 assessments are not runtime dependencies. The
`AcceptInjectedTestInput` development switch is never physical acceptance and
is unreachable from the normal helper integration.

## Packaging and release

See [the package and rollback procedure](PACKAGING.md). The Windows archive
includes native code, its sources, the Python adapter and pinned dependencies.
Disposable preparation, startup, update selection, rollback and data-retention
checks have run. Installed-helper setup, startup/update/rollback, remaining
acceptance and final Studio integration review are still release gates.
No commit, push, merge, Render deployment or installed-helper replacement is
authorized by these local results.
