# Task Recorder V1 — local Windows setup and verification

For current hosted controls, pairing and Windows setup, see
[TASK_RECORDER_PHASE2.md](TASK_RECORDER_PHASE2.md). The original V1 notes and
verification below are retained as historical evidence.

Implemented and verified locally on 20 October 2026 (Australia/Sydney).
The user subsequently authorized publishing this feature to Git and the existing
Render service. The hosted release adds the Developer entry and local-console
instructions; the browser runner remains on Windows and hosted pairing remains
outside V1. No provider calls or production-data automation tests are required.

## Start / stop

Double-click **Start Task Recorder.cmd** in this task worktree. It opens an
authenticated local console. Dependencies have already been installed and the
launcher has been verified on this PC. The actual recorder browser is visible
Chrome with its own profile. It opens only when Open Browser or Play is used.

For a fresh checkout, from its PowerShell directory:

```powershell
.\scripts\Start-TaskRecorder.ps1 -Setup
# Subsequent starts:
.\scripts\Start-TaskRecorder.ps1
# Shut down only this recorder service:
.\scripts\Start-TaskRecorder.ps1 -StopRunner
```

Python 3.12+ is required; this PC was tested with Python 3.14.0 and Playwright
1.63.0. Setup installs a private worktree .venv and Playwright Chromium.
Installed Chrome is preferred for a visible Windows browser, then Edge, then
bundled Chromium. Bundled headed Chromium returned `spawn UNKNOWN` on this PC;
installed Chrome passed all headed acceptance tests.

Service: http://127.0.0.1:18931/ . Opening that address alone does not grant
browser control. The launcher authenticates using a random per-process key in a
URL fragment, which the console immediately removes and retains in sessionStorage.
Do not share a connection key. A runner restart rotates it; reopen the launcher.

The source app now has **Developer → Task Recorder**, restricted to administrators.
In a local OS at port 8501 it embeds this console. Use **Pair OS page** in the
launcher console to copy the key into the embedded page if that browser context
is not paired. SessionStorage partitioning can require this extra step.

The standalone console is a limited local feature fixture, not a full application
preview. The production app/server was not imported or started. The actual OS
route dispatcher and access checks were exercised with synthetic module stubs.

## Record and play

1. New Task; name it; enter a clean HTTP(S) URL and Open Browser.
2. Sign in manually with recording stopped. Sessions stay in this dedicated
   profile. Never use your regular browser profile for the recorder.
3. Record; interact with the one original tab; Stop Recording.
4. Review the editable steps. Resolve red unsupported rows. For reusable values,
   add a named input (for example `product_name`) and replace a step value with
   `{{product_name}}`. The input name is case-sensitive.
5. File selections become an `image_path` input automatically. Browser JavaScript
   cannot disclose a full Windows path: enter an existing absolute path in Inputs.
   The selected file's contents are never stored with the task.
6. Save, supply input values, Play. Inputs are validated before any browser action.
7. Pause stops subsequent actions after an already dispatched action finishes.
   Resume retries only the current safe checkpoint. Stop closes the dedicated
   browser context to cancel pending browser commands. It retains the profile.
8. Refresh the browser layout on demand. It returns bounded geometry only:
   no webpage strings, values, URLs, images, screenshots or desktop stream.

The example **Local product demonstration** is saved in local application data,
ready to load. Click Use demo / Open Browser to inspect the synthetic site.

Example inputs:

| Input | Example |
|---|---|
| product_name | Product B |
| headline | A different headline |
| url | https://example.com/product-b |
| image_path | C:\Users\hello\AppData\Local\SportsCaveOS\TaskRecorderV1\demo-image.txt |

The demo contains navigation, a form, category selection, a checkbox, a one-file
upload, delayed content and a local submission receipt. It does not send a form
to an external service.

## Runtime isolation and privacy

Everything lives beneath `%LOCALAPPDATA%\SportsCaveOS\TaskRecorderV1`:

- `tasks/*.json`: validated version-1 tasks, stored with atomic replacement.
- `tasks/*.result`, `run.json`: task IDs, progress, status, timestamps and safe
  diagnostic messages only. No input values or page content.
- `browser-profile/`: the dedicated local browser session; never checked into Git.
- `connection.json`: per-run bridge key encrypted with Windows user-scoped DPAPI.
- `launcher.*.log`: startup diagnostics; request/header logging is disabled.

Per-run input values stay in memory. Literal values intentionally saved in steps
remain in task JSON. Do not put credentials into ordinary text fields.
The recorder pauses on recognized sign-in paths, password/username/OTP controls,
sensitive field names, and common token patterns. Resume requires leaving the
sensitive screen. Detection is conservative, not an exhaustive classifier of
every custom sign-in UI: always Stop Recording before sign-in. Preview is
suppressed while sign-in/sensitive content is detected.

The bridge binds only 127.0.0.1, validates Host exactly, rejects other Origins
(including null), disallows CORS, requires a key on every control/state/preview
endpoint, and rejects cross-site API fetches. Only its own origin can control it.
Embedding is restricted to itself and the two explicit local OS origins
`http://127.0.0.1:8501` and `http://localhost:8501`.
The local static console/demo assets carry no key and expose no browser state.

The same DPAPI primitive used by Studio is reused without starting/importing its
companion. The recorder has its own lock, process, jobs, port, profile and data.
Edition allocation, Photoshop processing and existing worker queues are untouched.
The four pre-existing Python companion processes remained running throughout.

The hosted app branch shows instructions and a local-console link, with no server
browser launch. HTTPS hosting, browser local-network permissions, explicit origin
enrollment and secure device pairing still require separate work and verification.
Render localhost is never used as the user's PC. There is no hosted job transport.

## Action contract and failure behavior

Only these data actions execute; unknown fields and action/locator kinds fail
validation. There is no eval/script/shell endpoint or task code interpreter.

| Action | Behavior |
|---|---|
| navigate | Go to a clean HTTP(S) URL; wait for DOM content |
| wait_url | Wait for the exact resulting URL, without navigating again |
| click | Unique target, visibility/actionability checks, one click |
| fill | Fill a labeled text input or textarea |
| select | Choose one native select option by value |
| check | Set checkbox/radio to a boolean state |
| upload | Select one existing local file from an input path |
| wait | Wait for one visible matching element |
| unsupported | Review marker; blocks playback |

Locators support exact role + accessible name, label, test ID, element ID,
placeholder and text. No uploaded CSS/XPath selectors or JavaScript execute.
Timeouts are bounded to 500–30000 ms. Missing and ambiguous targets pause with a
useful reason. Action errors after possible dispatch cannot be resumed; inspect
the outcome and Stop. Completed actions are never automatically retried.

The journal marks a restarted in-flight run interrupted. No task starts on service
startup, and no run is automatically restarted. The UI asks before explicitly
starting an interrupted/stopped task from step 1. A new deliberate Play is a new
run and can repeat submissions; inspect any earlier result first.

Click-induced navigation records a URL checkpoint, not a second GET. If a manual
address change occurs immediately after a click, it can be classified as a URL
checkpoint; edit it to navigate if appropriate. V1 rejects recorded URLs with
query parameters, fragments, embedded credentials or sensitive path names.

Uploading waits for browser file selection. Add a `wait` step for the destination
site's ready/success element to wait for server-side processing. V1 cannot infer
a remote site's upload completion semantics.

Detected unsupported actions are explicitly flagged: new tabs/popups, iframes,
rich text, canvas/SVG drawing, drag/drop, modified/right/double clicks, keyboard
shortcuts/Enter submissions, multiselect and multi-file uploads. Dialogs are
dismissed and downloads cancelled. Only the original tab and main frame play back.
Hover-only menus, closed shadow roots, native OS dialogs and complex editors need
adapters; missing targets pause rather than guessing. Scrolling is not a recorded
step because Playwright scrolls targets into view.

This is an Ads Companion foundation, **not proven Meta ad automation**. No real
ads were created. Any future Meta workflow needs independent validation for its
UI, permissions, upload completion, review and submission behavior.

## Verification performed

All browser data was synthetic, using port 18941 and a separate acceptance profile.
The record and replay phases ran in separate Python processes, with a visible
Windows Chrome browser. The final task had 12 steps including its URL checkpoint.

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_task_recorder -v
.\.venv\Scripts\python.exe -m tests.task_recorder_acceptance record "$env:LOCALAPPDATA\SportsCaveOS\TaskRecorderV1-Acceptance-64cdf0b0"
.\.venv\Scripts\python.exe -m tests.task_recorder_acceptance replay "$env:LOCALAPPDATA\SportsCaveOS\TaskRecorderV1-Acceptance-64cdf0b0"
node --check task_recorder/ui.js
node --check task_recorder/record.js
node --check task_recorder/demo.js
.\.venv\Scripts\python.exe scripts/validate_render_topology.py
git diff --check
```

- 7 contract/navigation tests passed: authentication, Host/Origin/CSRF boundaries,
  code/action rejection, private URL/credential rejection, inputs/uploads,
  interruption persistence, actual route dispatch and admin restrictions.
- Recorded Product A; parameterized, named and saved it; shut down that process;
  loaded and replayed Product B with different headline, URL and upload.
- The real console's Save/Play controls replayed Product C through the HTTP bridge.
  Each product produced exactly one local submission.
- Verified required inputs, single-run exclusion, missing target + repair + resume,
  ambiguous target pause, Pause/Resume, 30-second pending wait cancellation,
  sign-in pause/redaction, preview suppression, unsupported Enter submission.
- Final recorded Stop latency: 108 ms. Console connected in 84 ms on this PC
  during the synthetic run (a measurement, not a performance guarantee).
- Layout checked at 1366×768, 1366×850 and 1920×1080. No outer vertical scrolling at
  the two compact desktop sizes; the steps list scrolls internally.
- Verified that a task name entered before Record is retained, and that actions
  inside an already-present iframe are flagged without saving its field content.
- The actual Windows launcher was installed, opened, stopped and restarted.
  The persisted 12-step example replayed successfully on port 18931.
- Render topology and JavaScript syntax checks passed. No Blueprint sync/deployment
  was attempted.

Evidence JSON and screenshots are outside Git in
`%LOCALAPPDATA%\SportsCaveOS\TaskRecorderV1-Acceptance-64cdf0b0`.
Launcher verification is in `TaskRecorderV1/launcher-verification.json`.

## Files and worktree

Task: `20261019-64cdf0b0` (INTEGRATIONS).
Owner: `codex-task-recorder-20261020-01a15682`.
Branch: `codex/task/integrations-local-task-recorder-v1-20261019-64cdf0b0`.
Path: `C:\Dev\SportsCaveWorktrees\sports-cave-integrations-local-task-recorder-v1-20261019-64cdf0b0`.
Approved Studio base: `59b609728b182c6c997f02ed0a8786fff0483095`.
Source and test evidence are retained in this dedicated task branch. Release
integration preserves the newer production navigation and Product Uploads changes.
The user authorized Git/Render publication on 20 October 2026. Integration with
current production main passed 19 offline Streamlit navigation/access regressions,
the seven recorder contracts, and fresh headed record/replay acceptance. The
actual sidebar opens Task Recorder and preserves Worker Health, Image Protection
and Dev Mode. The hosted page points to the Windows console; secure hosted
pairing is still outside V1.

Changed existing files: `app.py`, `navigation_runtime.py`, `os_accounts.py`.
Added: `task_recorder_page.py`, `Start Task Recorder.cmd`,
`scripts/Start-TaskRecorder.ps1`, `task_recorder/__init__.py`,
`task_recorder/schema.py`, `task_recorder/store.py`, `task_recorder/runner.py`,
`task_recorder/server.py`, `task_recorder/record.js`, `task_recorder/ui.html`,
`task_recorder/ui.css`, `task_recorder/ui.js`, `task_recorder/demo.html`,
`task_recorder/demo.js`, `task_recorder/requirements.txt`,
`tests/test_task_recorder.py`, `tests/test_task_recorder_navigation.py`,
`tests/task_recorder_acceptance.py`, and this guide.

Implementation references: [Playwright actions](https://playwright.dev/python/docs/input),
[locators](https://playwright.dev/python/docs/locators),
[persistent browser contexts](https://playwright.dev/python/docs/api/class-browsertype#browser-type-launch-persistent-context).
