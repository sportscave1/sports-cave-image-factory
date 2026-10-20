# Phase 1 assessment and handoff — 20 October 2026

## Completion and ownership

Phase 1 source recovery, local foundation and bounded read-only Windows inspection
are complete. Native event capture, floating toolbar, input execution and OS
integration remain Phase 2/3 work. No recording/playback capability is advertised
by the new component.

Requested folder was absent; only that requested folder was created. Its parent
is `C:\Users\hello\Documents\sports-cave-image-factory`, branch `main`, revision
`7b84f2c572363f662b6e5f8d8a343e171ff10e1f`. Parent `AGENTS.md` and ancestor
instruction locations were checked. Parent has substantial unrelated dirty work.
`ownership.json` records the initial status. This subfolder does not isolate Git
state. User's explicit location/no-new-worktree instruction takes precedence over
the supplied category-worktree default. No shared source file was edited.

Registry lookup verified task `20261019-64cdf0b0`, owner
`codex-task-recorder-20261020-01a15682`, status `Tested`, branch
`codex/task/integrations-local-task-recorder-v1-20261019-64cdf0b0`.
Actual Git root/branch/HEAD match its record. Root, abbreviated **OLD** below:

`C:\Dev\SportsCaveWorktrees\sports-cave-integrations-local-task-recorder-v1-20261019-64cdf0b0`

HEAD is `23103faf617d2cecd4e60b0bf5a4f36d4f3c4455`; 40 changed/untracked paths.
All old worktree access was read-only. The registry's latest test evidence and
actual reports/code agree on the local browser implementation. Ownership was not
transferred. Before modifying `task_recorder`, hosted endpoints, Product Uploads
or packaging, arrange an explicit handoff/integration task with that owner and
the current shared-file owners. Do not copy the old renderer over newer work.
No Studio task was created or falsely marked tested for this parent subfolder.

## Recoverable checkpoint

`recovery/recorder-source.zip` contains 67 allowlisted source/doc/test files:
the recorder package, recorder tests/harnesses/reports, recorder install/start
scripts, Product Uploads context module, renderer and gallery hook, and applicable
old AGENTS instructions. All 40 dirty/untracked paths are included. Original
paths, sizes, SHA-256 hashes, source branch/revision, ownership and dirty status
are in `recovery/manifest.json`. Every ZIP entry was read back and hash checked.
This preserves both changed files and their relevant package dependencies.

No installed task data, vault, connection file, credentials, browser profiles,
PSD, virtual environment, generated screenshots or unrelated project was copied.
Synthetic test fixtures are source, not live customer data. The original Git
index/worktree was not committed, stashed, reset or cleaned. Restore by extracting
into a review directory and comparing with the recorded revision, not by
overwriting the still-owned worktree.

## Implementation versus release evidence

| Layer | Evidence and status |
|---|---|
| Existing local browser work | OLD dirty files and four `*_LOCAL.md`/performance reports; tested locally in prior phase. Preserved, not released here. |
| Prior deployed OS | Latest experience report records read-only Render revision `7c58bfc3cd6a8f66b9c6298ace1b53c717b40f52`. Historical observation, **not re-queried in this phase**. Parent `main` is not proof of deployment. |
| Installed helper | This phase rehashed all 25 manifest-listed source files; all match retained release `c0a912f753cf53a7406388c882a898434e584457`, protocol 4 in prior evidence. Source equality does not prove current running-process health. See `recovery/installed-source-check.json`. No helper contact/update/restart. |
| Latest browser candidate | Protocol 5, browser toolbar/drafts/product context. Prior actual OS/relay/Product Uploads synthetic trial; 58 tests + 14 subtests and four Node suites reported. No new full browser trial here. |
| Desktop foundation | New Python contracts and supported-runtime diagnostics, local checks only. No packaging/installation/production integration. |
| Experiments | Older lookalike fixtures did not catch Streamlit document replacement. Benchmark preliminary/contaminated runs are excluded by its report. They are not native Windows evidence. |

## Component reuse map

All source paths below are relative to the exact OLD root above, also recorded
as absolute paths in the checkpoint manifest.

| Component and exact source | Decision | Reason / adaptation boundary |
|---|---|---|
| `task_recorder/state_updates.py::task_changes/merge_tasks`; `device.py::publish`; `hosted_api.py::state`; `relay_store.py`; `panel.js` | Adapt | Keep version-bound deltas/full-baseline fallback, keyed rows, bounded progress and terminal-state wakeups. Add explicit desktop format/capability metadata only after negotiation. |
| `store.py::atomic`, `Store.revision` | Reuse unchanged | Foundation injects these actual primitives. Atomic replacement and canonical revision hashing retained. |
| `store.py::Store.list/get/save/checkpoint/result` | Adapt | Browser validator is intentionally version 1. Desktop namespace must be dispatched explicitly; preserve summary cache and separate run results. Do not pass desktop tasks into browser validation. |
| `runner.py::toolbar_state/start_recording/pause/resume/stop`; `toolbar.js` | Adapt | Keep monotonic active-time accounting, flush-before-pause/stop and draft lifecycle. Replace shadow-DOM UI with floating native UI; current 300 ms browser bridge polling is not needed for a local toolbar timer. |
| `runner.py::browser_control` Save trial auto-Play | Supersede | New user contract requires Save only; explicit Play is mandatory for every desktop task. Old code is preserved, not modified in its owned worktree. |
| `editing.py`, `editor.js`, `panel.html/js/css`, `attention.py` | Adapt | Keep immutable edited copies, revision fences, simple names, local file choice and explicit unsupported warnings. Desktop action rendering and replacement capture need separate adapters. |
| `schema.py::validate_task/resolve_task/validate_locator` | Retain as browser adapter | Preserve all browser v1 JSON unchanged, including opaque file references and initial context. No silent desktop relabeling. |
| `windows.py::protect/Vault/add_file/file` | Reuse unchanged | DPAPI and opaque local file bindings remain helper responsibility; no second credential store. Do not import/read installed vault during diagnostics. |
| `device.py::pair/inspect_pair/exchange`; `hosted_api.py::actor/pairing`; `relay_store.py` | Reuse unchanged core | Existing account-scoped PC pairing, authenticated outbound connection and queue ownership stay. Add format negotiation at dispatch boundary, not another public endpoint or relay. |
| `device.py::apply/perform`, SQLite command receipts; relay boot/fence and revisions | Adapt | Retain durable duplicate-command fingerprint checks, acknowledgement, uncertain outcomes and stop fences. Route desktop operations to coordinator; no automatic retry of uncertain input. |
| `runner.py::play/restore_context` and action execution/clipboard checks | Retain as browser adapter | Browser-specific locators, readiness and outcome checks are useful. Native executor must validate window/focus and resolve UIA controls before each action. Existing browser Stop is not a global Windows emergency stop. |
| `record.js` | Retain as browser adapter | Semantic labels, privacy checks, input coalescing, frame identity and document-root rebinding are valuable. `__scRecord` Playwright binding cannot directly attach to arbitrary existing browser windows. |
| `runner.py::open_browser`, persistent profile and separate playback window | Supersede as mandatory desktop path | Desktop Record must attach to prepared windows with no launch/navigation/refresh. Keep old engine only for explicitly selected browser-v1 tasks. |
| `product_upload_recorder.py::publish/restore`; `product_upload_mockups_ui.py`; `components/product_upload_gallery/app.js` | Adapt | Preserve exact source/workflow/name/category checks and verified current clipboard outcome. Required context is separate from actions. Need existing-window observation; no automatic navigation during Record. |
| `install.py`; `scripts/Install-TaskRecorder.ps1`, `Start-TaskRecorder.ps1`; `windows.py::startup`; `hosted_api.py::setup`; `server.py::instance_lock/Bridge` | Adapt | Existing packaging, idle-before-update, single instance and independent startup are reusable. Native child lifecycle/health supervision is new work: no separate recorder supervisor module was found in this source. Do not confuse companion supervision with recorder supervision. |
| `tests/test_task_recorder*.py`, `tests/task_recorder*.cjs`, trial scripts; `scripts/benchmark_task_recorder.py`; `docs/TASK_RECORDER*.md` | Reuse evidence, adapt coverage | Keep regression coverage for browser compatibility, transport and privacy. Add real native tests; browser fixtures cannot certify desktop capture. |
| Photoshop/Edition Ops companion | Retain separately | `server.py` explicitly isolates recorder lifecycle. No required shared execution dependency established. No companion speed code, jobs, PSDs or benchmarks touched. |

Performance evidence: `docs/TASK_RECORDER_MEASURED_PERFORMANCE.md` and
`%LOCALAPPDATA%\SportsCaveOS\TaskRecorderMeasured-64cdf0b0\comparison.json`.
Prior equivalent-work HTTP measurements fell from 356,972 B to 87,504 B (75.5%);
completion median fell 828 ms to 169 ms. Request count stayed 59. Cold/warm
launch, CPU and memory did not show material gains; Pause/Resume samples were
not faster. Preserve deltas, summary caching, lazy detail loading, keyed rows,
event wakeups and backoff. These numbers are browser/relay evidence, not desktop
timings. The native design does not inherit a desktop performance claim.

## Actual Windows observations and capability matrix

Used only the skill-supported `node_repl` + `@oai/sky` client. One window inventory,
three selected text-only snapshots, then the new diagnostic on existing test
windows. No clicks, typing, activation, refresh, navigation, browser restart,
debug configuration, screenshots, hooks or secure dialogs. Existing Notepad
had unsaved documents; none were changed.

Sports Cave OS was an `MSEdge` window titled Sports Cave OS, exposing an Edge
document at the application's `?page=email` route, nested Streamlit documents,
named navigation buttons, search inputs and IDs such as `sc-os-global-search`.
This supports an Edge-hosted app window observation; it does not prove its
installation mechanism. Browser zoom showed 110%; that is not monitor DPI.
The normal Edge window was Kira Editor Project, with address/search, navigation
and page buttons. Notepad exposed Text editor, a tab list, File/Edit/View menus
and scroll buttons. Focus information was present for all three.

| Application / capability | Observed | Untested or unsupported |
|---|---|---|
| Sports Cave OS in Edge | Named buttons, search edit, document/frame hierarchy, disabled controls, focus snapshot | Product Uploads page not opened; Generate/copy control not inspected live in this phase. No native recording/playback proof. |
| Existing normal Edge window | Browser chrome and page control roles/names; buttons New/Fit/Export, editable address field | DOM extension bridge, native messaging, control invocation, event capture and existing-tab permission flow untested. |
| Existing Notepad | Real native editor/document, tabs/list, File/Edit/View menu items, scroll buttons and focus | Text edit/selection/invoke event capture and playback untested. No document edits made. |
| Application/window identity | Returned app IDs and current opaque window IDs | PID/executable signing/process-start validation not exposed by this structured runtime. Native adapter must add them. |
| Buttons, inputs, lists, menus | Roles and some identities exposed | Pattern availability is not proven just by a role. Same-label ambiguity must fail closed. |
| User actions and focus changes | Point-in-time focus reported | Runtime exposes no passive event subscription API. No hooks installed; no event provenance or ordering tested. |
| Re-resolution after movement | No coordinates stored by foundation | Window movement/reacquisition test not performed; schema identity is a contract, not proof. |
| Scaling/multiple monitors | OS browser zoom 110% observed | Physical DPI/monitor topology not exposed by text-only runtime. No multi-monitor test. |
| Password and secure controls | Not inspected | Structured runtime lacks `IsPassword`; cannot certify privacy-safe capture. Secure desktop, UAC, authentication and elevated targets are outside initial support. |
| Canvas/custom/inaccessible controls | No playback claim | Explicit unsupported interruption; no coordinate-only fallback or silent omission. |
| Desktop action capture/playback overall | None enabled | All action capabilities currently unavailable. Schema entries are proposed contracts. |

Initial snapshots: OS 1,905 ms; Edge 314 ms; Notepad 128 ms. New diagnostic:
Edge 286 ms, Notepad 40 ms. Single observations with different trees/cache state,
not before/after benchmarks, latency promises or CPU measurements.

The OS window disappeared from the inventory before the diagnostic rerun.
The diagnostic rejected its stale ID instead of reopening or guessing a target.
Edge and Notepad diagnostic reruns succeeded. Notepad's active document changed
between observations without any automation input. This reinforces that current
window identity alone cannot establish the intended document. Raw document
contents were not saved in project evidence; retained reports contain only
sanitized roles and technical metadata.

## Selected architecture and recording/playback contract

Keep the existing Python recorder helper as coordinator, authenticated transport,
local task library and command-receipt owner. Add a separately bounded native
desktop child owned by that helper, not by the Photoshop companion. Selected
native implementation direction is C# WPF for a small topmost toolbar, with a
dedicated UIA worker and versioned local IPC. This is a design selection, not a
built or installed binary. The local Python core is an executable reference
contract for the coordinator; C# messages must pass that validator.

The native capture adapter attaches to user-selected existing windows. It must
classify privacy before retrieving any text, exclude its own toolbar and stop
subscriptions while paused/stopped. UIA events alone are not guaranteed to
describe every user action: correlate supported control events with explicit
foreground user interaction in the eventual native adapter, without retaining
raw keystrokes. Unknown controls/overflow/privacy uncertainty interrupt recording
with a visible explanation. No mouse-movement stream, continuous screenshot or
full-desktop query loop.

Use cached targeted UIA property requests around the event target and selected
window, not repeated full trees. Subscribe/unsubscribe on one dedicated worker;
do not block the toolbar or emergency stop behind accessibility calls.
Microsoft documents [UIA caching](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-cachingforclients)
and [event subscriptions](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-eventsforclients).
Native providers still require validation on these exact applications.

Control identity combines application identity, a local window/document binding,
control type and stable ID/name scoped within that window. Runtime handles and
snapshot indexes are never saved. Zero/multiple matches interrupt; users should
see a plain explanation and re-record the unsupported interaction, not supply
selectors. A richer ancestor path can be added only with an explicit action
version when required. [Microsoft's property reference](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-automation-element-propids)
explains IDs are not globally unique and may change across releases.

For browser details UIA cannot expose reliably, retain `record.js` semantics
behind an explicitly permitted existing-tab extension/content-script adapter,
using [content scripts](https://developer.chrome.com/docs/extensions/develop/concepts/content-scripts)
and [native messaging](https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging).
No extension was installed. Do not depend on enabling a debugging port or launching
a replacement browser. Extension support inside the Edge app window must itself
be tested; UIA remains the initial existing-window path.

`sports-cave.desktop` format v1 is distinct from legacy browser `version: 1`.
Every desktop action has its own version and required capability. Unknown
versions/capabilities are rejected. Desktop files occupy a distinct namespace
under the eventual existing data root; the foundation does not modify the
existing Store validator or relay schema. OS lists must merge namespaces only
after explicit capability negotiation. Unsupported helpers must show Update
required, never send desktop data to browser Runner.

The lifecycle uses a monotonic local timer and explicit visible-indicator gate.
Pause/Stop require the provider to quiesce and flush accepted events through a
generation barrier; late events are discarded. Stop produces a durable draft,
then the UI presents Save. Save persists an immutable definition and never plays.
Disk/flush failures preserve the draft and suspend capture. Crashed recordings
recover as interrupted, never resume automatically. Current minimal recovery is
inspect/discard; a safe review/save-partial UI remains Phase 2.

Starting context is separate from actions. `prepared` means the intended bound
window/document must be validated before playback; it does not snapshot app
state. `specific_product` binds workflow/source hash+revision/name/category via
an opaque local reference. `per_run_product` requests a fresh validated binding
at each explicit run; it must not reuse the recorded product implicitly. The
foundation validates these modes/references but does not resolve product bindings.
Do not advertise reusable-product execution until that resolver exists.

Playback must first validate the exact saved revision and required capabilities,
explicit Play, visible progress and registered emergency Stop. Before every
input, revalidate app/window/document/focus and unique control, wait for actual
enabled/readiness state with bounded timeout, and abort on manual focus change.
Record no absolute screen coordinates. Per-monitor DPI awareness and fresh
physical geometry are required before any future positional fallback; see
[Microsoft DPI guidance](https://learn.microsoft.com/en-us/windows/win32/hidpi/high-dpi-desktop-application-development-on-windows).
Saved definitions never acquire playback progress; retain separate run journals.

An independent cancellation event must wake waits and cancel pending actions.
Native execution owns a held-key/button ledger and releases it on success,
failure, Stop or disconnect. `input_scope` implements the cleanup boundary but
no native release backend exists yet. Register a global emergency shortcut and
visible Stop before enabling Play; fail closed if registration fails. No
automatic re-execution after an uncertain result; retain command receipts and
confirmation requirements for consequential actions.

Initial support is same-user, non-elevated desktop applications. No privilege
escalation or UIAccess workaround is proposed. Secure prompts need manual
handling. [Microsoft security guidance](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-securityoverview)
describes integrity boundaries; these must be respected.

## Implemented foundation and checks

- `desktop_recorder/contract.py`: strict data-only format, per-action capabilities,
  stable target fields, distinct context modes, size/action limits and credential
  heuristics. Heuristics supplement provider privacy classification, not replace it.
- `lifecycle.py`: visible Record gate, active-time timer, Pause/Resume/Stop barriers,
  bounded ordered actions, draft checkpoints, explicit Save, interrupt/recover/discard.
- `integration.py`: capture/execution ports, existing atomic/revision injection,
  immutable local storage adapter, capability preflight, cancellation/cleanup.
- `diagnostics.mjs`: safe, one-shot supported-runtime inspection; no app inputs.
- `tests/`: isolated contract tests using actual checkpointed old storage code,
  plus diagnostic redaction/stale-target tests. Those doubles are not native proof.

See `verification.json` for exact check results and preservation audit. No broad
benchmark or production integration suite was rerun. Production task data and
customer data were not used in tests.

## Phase 2 implementation plan and exit checks

1. Confirm ownership handoff for helper dispatch/storage/package files. Preserve
   both parent dirty work and old task changes; do not silently edit either.
   Keep this component local until release is separately authorized.
2. Build the WPF toolbar and a local-only native host. Record/Pause/Resume/Stop,
   visible active timer, Save/Discard, safe crash recovery and single instance.
   Attach selected existing windows; no navigation/refresh/new browser calls.
   Test timer/indicator transitions, Save without Play, unsaved-draft protection.
3. Implement native UIA metadata-only diagnostic first: IsPassword, enabled/offscreen,
   patterns, bounded ancestors, window/process/document identity, per-monitor DPI.
   Validate same-user scope and unknown privacy blocking on disposable test apps.
   Test moved windows and monitors before claiming geometry support.
4. Add explicitly armed capture for verified Invoke, Value, Selection and Toggle
   controls plus focus switches. Coalesce text updates, apply generation barriers,
   privacy checks before values, bounded events and visible unsupported messages.
   No background hooks when idle/paused; no screenshots or raw-key event storage.
   Add scroll/shortcut contracts only after actual semantic evidence and versioning.
5. Prove capture across an existing harmless Edge page and disposable Notepad
   document: no reload, two-window order, Pause exclusion, final text flush,
   Stop/durable Save, restart recovery and unchanged original task formats.
   Inspect document contents only when explicitly selected for that local test.
6. Adapt the existing task list/receipt transport with format/capability negotiation,
   and retain performance deltas/cache/lazy details. Verify old helper fallback
   and duplicate Save/Record commands without another database/auth system.
7. Assess Product Uploads context in an isolated preview with synthetic PSD/data,
   preserving current production copy-handoff changes. UIA-first Generate/copy
   identification; add permitted browser adapter only where evidence requires it.
   No production generation or authoritative PSDs.

Phase 2 ends with real cross-window capture and durable Save, **not desktop Play**.
Phase 3 implements execution/readiness/progress/global Stop/input release and
outcome verification, including the Product Uploads clipboard acceptance.
Packaging, coordinated release and installed verification need fresh explicit
authorization. Nothing in this phase was committed, pushed, deployed or installed.
