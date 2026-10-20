# Task Recorder Phase 2

## Normal use

In Sports Cave OS, open **Developer → Task Recorder**. Press **Record**, perform
the task in the visible window marked **Sports Cave recorder browser**, press
**Stop** to save automatically, then **Play**. A compact selector holds previous
recordings. Names are automatic; renaming and reusable labelled values are in
Advanced. Closing the popup does not stop, restart or repeat a task.

Always stop recording before manual sign-in. Recognised sign-in screens pause
capture automatically. Resume only after leaving that screen. Sessions remain
in the dedicated Windows browser profile. Playback stays visible.

## First installation and pairing

Python 3.12+ must be installed on Windows. Download helper setup in the popup,
unzip it and run `Install.cmd`. Windows may require confirmation; a website
cannot start an uninstalled Windows program. Existing checkout alternative:

```powershell
.\scripts\Install-TaskRecorder.ps1
```

Installation uses `%LOCALAPPDATA%\SportsCaveOS\TaskRecorderHelper`, its own venv
and pinned Playwright/httpx. It installs Chromium; existing Chrome or Edge is
preferred for visible operation. Start menu → **Sports Cave Task Recorder →
Task Recorder** starts quietly. Repeated launches detect the existing instance.
Only the opt-in Advanced **Start with Windows** setting adds an HKCU Run entry.

In the OS popup choose **Connect PC**, then **Approve on this PC**. Review the
account/site in the local approval page and explicitly approve. Challenges expire
after five minutes and are single use. Ordinary use needs no copied keys.
Disconnect/revoke invalidates the device credential; pairing is required again.

Stable launchers:

- `%LOCALAPPDATA%\SportsCaveOS\TaskRecorderHelper\Start.vbs` — quiet start.
- `Start.cmd` — quiet start wrapper.
- `Stop.cmd` — authenticated local emergency Stop and helper shutdown.
- `Diagnostics.cmd` — authenticated local console fallback.
- `Connect PC.cmd` — local approval page.

Setup upgrades only an idle recorder. It preserves
`%LOCALAPPDATA%\SportsCaveOS\TaskRecorderV1\tasks` and `browser-profile`.
No editions/Photoshop process, configuration, lock or worker queue is used.

## Transport and persistence

The PC makes outbound TLS-verified HTTPS requests to the existing OS backend.
Render never opens a browser or treats its localhost as the PC. The local bridge
binds only 127.0.0.1:18931, enforces Host/Origin checks and authenticated controls.
The hosted popup calls same-origin administrator APIs, not localhost controls.
The top-level local approval page is the only first-time bridge between them.

The existing signed account cookie is verified against the current active admin
and session version. Legacy master-password cookies cannot enroll/control PCs.
Device ownership is checked for each account request, and active admin ownership
is checked for each device exchange. Only a credential hash is stored server-side.
The Windows device credential, file references and reusable defaults are DPAPI
encrypted for the current Windows user. Browser sessions never leave the PC.

Private PostgreSQL tables persist device state, short-lived pairing challenges
and command receipts. They use RLS with no public/anon/authenticated access.
The reviewed deployment migration creates only `task_recorder_private` objects.
Task files and browser profiles remain local; Advanced edits/inspection and
ordinary input values pass through the authenticated relay. Do not use these
fields for credentials. The relay is not an arbitrary script/shell executor.

Each command has a unique ID, persisted acknowledgement and a boot/fence binding.
Each playback binds a local task revision and operation ID. Duplicate requests
reuse their receipt. A second start is rejected. Stop invalidates pending controls
and cancels local actions. Starts expire after 30 seconds. Restart and connection
loss require reconciliation; interrupted/uncertain work never automatically plays
again. Completed submissions are never retried automatically.

State uses bounded metadata and long polls (15-second PC / 20-second panel waits),
with changed-state pushes while active. There is no continuous desktop stream,
hosted screenshot, new UI framework or paid/AI automation service.
The PC allows 45 seconds for a long-poll response and 20 seconds for a state
exchange, including authenticated database work. A healthy live long poll measured
22.48 seconds; V1 Phase 2's original 22-second client budget could falsely abort
a recording. The corrected budget is covered by a regression check. Safe local
transport diagnostics record only an exception class and timestamp in
`transport-status.json`, without credentials or request bodies.

## Supported actions and limitations

Navigation, URL checkpoints, labelled/role/test-ID/ID/placeholder clicks, text
entry, single selection, checkbox/radio, single local file upload and condition
waits. Normal query strings are allowed; embedded credentials, known auth query
keys, sign-in/session URLs and token-like contents are rejected. Upload references
reuse the local file; if unavailable, choose a replacement in Advanced. Uploads
wait for the browser file assignment; site-specific server processing needs a
subsequent actionable control/condition. No universal upload-completion detector.

Unsupported actions are saved as blocking flags: new tabs/popups, iframe actions,
downloads, dialogs, Enter submissions, rich text, canvas, drag/drop, double/right
click, modified clicks and unrecognised keyboard shortcuts. No arbitrary scripts,
CSS/XPath or desktop automation. Dynamic websites can require locator repair.
Privacy checks are conservative heuristics, not recognition of every sign-in UI.
Native file selection may remain open if Stop closes its browser; cancel that
Windows dialog. Do not enter credentials while recording.

## Isolated verification and trial

Actual full `app.py` sign-in/sidebar/dialog and production API handlers run at:
`http://127.0.0.1:18961/?page=task_recorder`.

Preview launcher: `scripts/task_recorder_preview.py --root
%LOCALAPPDATA%\SportsCaveOS\TaskRecorderPhase2-Preview-64cdf0b0 --port 18961`.
Use the repository's full application venv. It sanitizes the environment, blocks
external sockets/subprocesses, and confines writes to isolated preview storage.
PostgreSQL fixture: Docker `sports-cave-task-recorder-pg-64cdf0b0`, loopback 55439,
database `recorder`; synthetic credentials are in the preview/test scripts.
No production database or provider APIs are used for development acceptance.

Automated evidence:

- `tests/test_task_recorder.py`: seven original contract/authentication checks
  plus existing-browser foreground and hosted timeout-budget regressions.
- `tests/test_task_recorder_relay.py`: seven real PostgreSQL security, ownership,
  pairing, duplicate, Stop, expiry and restart checks.
- Sidebar/retirement/navigation regression suites.
- `tests/task_recorder_acceptance.py record|replay`: original headed V1 coverage
  in separate processes; 12 steps, changed values, delayed content, upload,
  missing/ambiguous targets, pause/resume, privacy and Stop (148 ms measured).
- `tests/task_recorder_phase2_browser.py`: actual OS login, local PC approval,
  outbound transport, Record → Stop/autosave → exact Play, upload reuse, query
  URLs, changed labelled inputs, popup reopening, missing target/Resume/Stop,
  duplicate Start rejection, injected outbound connection loss, installed helper
  process restart/reconnection, unauthorized requests and OS revocation.

Evidence and screenshots stay in local application data under
`TaskRecorderPhase2-Acceptance-64cdf0b0`; V1 regression uses the separate
`TaskRecorderPhase2-V1Regression-64cdf0b0` directory. Original data/profile stays
separate from these tests. Existing four companion processes remained running.

**User trial:** the user approved their PC on the live HTTPS app and saved two
recordings (11:53 and 11:54). Both were inspected: each contains only navigation
to the local demo form; neither contains form values or a Save action. Navigation
playback completed, but this does not verify form interaction or changed inputs.
The guided form recording/replay remains pending the user's demonstration.
Record/Play were corrected to bring an existing recorder window forward.
A guided start at 12:20 was interrupted before form actions by the hosted timeout
described above; it was saved for review, not replayed as a completed form trial.
The pairing, two recordings and command receipts were transferred to the normal
installed helper's TaskRecorderV1 data directory. The original V1 example and
browser profile were verified unchanged, and both profiles were retained.
No real ads, email or production writes are suitable trial actions. Meta
automation remains unverified.

**Live HTTPS:** commit 935960ae deployed successfully to the existing primary,
webhook and worker services. The private migration applied; primary/webhook health
passed and unauthenticated account/device requests were rejected. Nathan's
authenticated popup and Connected PC state were visually verified. Real-account
PC approval, saved navigation recordings and confirmed playback were observed
separately from isolated automated tests. The substantive form trial is pending.
