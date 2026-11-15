# Phase 2 local implementation and acceptance — 20 October 2026

**Phase 2 is incomplete.** A real native recording → Stop → Save path works
for an Edge text field, and real button/toggle actions were captured and saved.
The existing Sports Cave OS catalogue is **not connected**. Notepad,
cross-application capture, selection capture, native password exclusion and
embedded Product Uploads capture have not passed acceptance. Do not deploy or
replace the installed helper with this candidate.

## Open the candidate

From PowerShell:

```powershell
& 'C:\Users\hello\Documents\sports-cave-image-factory\windows-screen-recorder\Start-LocalRecorder.ps1'
```

This builds the WPF executable and starts its Python coordinator with isolated
`.local-data` storage. No browser is launched by Record. No task is run by Save.
Close the existing candidate before rebuilding. The test-only
`-AcceptInjectedTestInput` switch was used for Computer Use trials; ordinary
launches ignore injected mouse/keyboard events. It is not a production setting.
No SDK download or installation was needed: compilation uses the installed
64-bit .NET Framework C# compiler and WPF/UI Automation assemblies.

## Recovery, source identity and ownership

Parent remains `C:\Users\hello\Documents\sports-cave-image-factory`, branch
`main`, initial revision `7b84f2c572363f662b6e5f8d8a343e171ff10e1f`.
This directory is a subfolder, not a Git repository/worktree. Unrelated dirty
files remain untouched. `ownership.json` and Phase 1 verification are preserved.

All 67 source entries in `recovery/recorder-source.zip` were re-read and matched
their SHA-256 values in `recovery/manifest.json`. Before editing the foundation,
`recovery/phase1-foundation.zip` preserved its source/tests/reports. Archive and
final source/build hashes are in `evidence/phase2-source-manifest.json`.
`evidence/phase2-start.json` records the branch and handoff refusal.

Shared source remains owned by `codex-task-recorder-20261020-01a15682` under task
`20261019-64cdf0b0`. Its exact location is:

`C:\Dev\SportsCaveWorktrees\sports-cave-integrations-local-task-recorder-v1-20261019-64cdf0b0`

Studio `Open -Id 20261019-64cdf0b0 -Owner codex-desktop-foundation-01a1589a
-NonInteractive` refused: **“Owned by another session. Ask its owner; do not
take over.”** The previous “Add local Task Recorder V1” chat was idle/completed,
but the registry lock remained. The inspected Studio procedure exposes no
supported ownership-transfer verb. The user's conditional handoff authorization
has not been used to bypass the lock or edit the registry.

Message for the previous owner:

> Confirm you have stopped editing task 20261019-64cdf0b0 and hand off its
> preserved recorder changes to codex-desktop-foundation-01a1589a using a
> supported Studio ownership transfer. Do not reset, stash, commit or delete
> anything. If Studio lacks that operation, report the missing procedure rather
> than editing the registry manually.

## Implemented files

| File | Implemented behavior |
|---|---|
| `native/Host.cs` | Native draggable WPF toolbar, active timer, Record/Pause/Resume/Stop, selected-window preflight, Save/Discard, recovery review, own-process input exclusion, single candidate mutex. Explicitly armed hooks correlate input intent with targeted UIA queries on a dedicated bounded worker. Invoke/toggle/selection-pattern actions, coalesced text, focus identity, privacy/elevation checks, visible interruptions and watchdog. |
| `native/build.ps1` | Builds the x64 windowed executable from local Framework assemblies. |
| `desktop_recorder/coordinator.py` | Versioned bounded private inherited pipe protocol; matching acknowledgements; lifecycle routing; bounded command-ID deduplication; recovery and durable-save acknowledgement. No listening recorder control endpoint. |
| `desktop_recorder/dependencies.py` | Verifies the recovery ZIP and extracts only the pinned recorder package as a candidate dependency. Does not copy the old project or modify its source. |
| `desktop_recorder/contract.py` | Explicit desktop format/action versions, capabilities, stable identity fields, optional selected starting window and observation time. No persisted HWND/runtime ID/coordinates. Legacy browser definitions are not converted. |
| `desktop_recorder/integration.py`, `lifecycle.py` | Preserved Phase 1 repository and lifecycle; reuse original atomic replacement/revision functions, format-separated immutable definitions, draft barriers, late-event rejection and cancellation interfaces. |
| `desktop_recorder/catalogue.py` | Cached desktop summary/lazy-detail composition adapter; legacy row passthrough; protocol-6 update requirement and desktop Play/edit guards. **Not wired into shared DeviceAgent/OS routes.** |
| `Start-LocalRecorder.ps1` | Hidden coordinator startup and isolated data; does not stop/update/install the production helper. |
| `preview_product.py` | Composes the existing actual Product Uploads synthetic harness read-only, redirects its output away from the owned checkout, blocks external socket connections, and uses a unique short temporary runtime path. |
| `tests/test_phase2.py`, `tests/capture-fixture.html` | Coordinator/storage/catalogue checks and harmless browser controls for actual native trials. |

Reuse retains `task_recorder/store.py::atomic` and `Store.revision` unchanged.
Existing caching/deltas/keyed rows/lazy inspection/event-driven relay code is
preserved in the checkpoint and owned worktree. The new catalogue adapter caches
summaries by file stamp and only loads details on request. Authentication,
registration, relay, file bindings and durable DeviceAgent receipts are **not
duplicated**, but also **not connected to the native coordinator yet**. The
native pipe's small receipt cache is in-memory, not a substitute for those
durable receipts. Photoshop/Edition Ops code, jobs, settings and performance
work were not changed or benchmarked.

## Actual Windows evidence

Windows UI actions used the Computer Use skill, not custom automation probes.
The real host and coordinator ran on Windows. Accepted input came through the
tool's explicit injected-input test switch; manual physical-input acceptance
has not been separately performed.

| Capability | Evidence / acceptance status |
|---|---|
| Existing Edge page preserved at Record | Observed on the local harmless fixture. Its existing field values/page remained present; no recorder navigation or refresh. |
| Native button | Real UIA `focus_window` then `invoke`, `automation_id=action`, name `Harmless action`; saved after interruption review. |
| Native checkbox | Real UIA `toggle`, `automation_id=enabled`, value `true`; same saved trial. |
| Native text | Real Edge edit `automation_id=example`, complete `set_text` value persisted. Ctrl+V intent supported; modifier-key handling fixed during trials. No raw key stream is stored. |
| Pause | Real Pause flushed the pending field. `PAUSED_ONLY` entered during Pause is absent from `native-pause-draft.json`; active time froze. |
| Resume | UI resumed, but the trial exposed an initial-window restriction bug. Fixed by consuming that restriction after the first accepted action. Final native Resume retest remains outstanding. |
| Final focused field at Stop | **Passed on final build**: Stop flushed the Edge field without another application-control click. |
| Save without Play | **Passed on final build** via the WPF name/Save form. Exact saved definition and acknowledgement retained in evidence. No desktop execution implementation is invoked. |
| Restart | Final candidate was closed, restarted with the same data root, and returned idle rather than resurrecting the saved draft. Saved bytes/revision verified unchanged. |
| Interrupted recovery | Earlier captured button/toggle draft reappeared as interrupted after restart; explicit Review and Save succeeded. |
| Toolbar exclusion | Saved actions refer to Edge only; toolbar Save/Pause interactions do not appear. |
| Notepad / cross-window | Disposable blank tab prepared, but trial blocked by repeated tool “user input was detected” / minimized-window failures after bounded recovery. No Notepad action acceptance. |
| Selections, menus, scrolling | SelectionItem pattern implementation unverified. Scroll, secondary clicks and other shortcuts visibly interrupt rather than silently omit. General combo/menu capture not complete. |
| Password / unknown privacy | Guards precede value reads in source; unknown privacy rejection tested at coordinator boundary. Actual native password-field trial not completed. |
| Provider failure / overflow | Bounded queues, 3-second watchdog and preserved draft implemented; automated lifecycle failure/overflow checks pass. Actual hung provider not exercised. |
| DPI / monitors | Native diagnostic reported DPI 134 and two monitors. No moved-window, mixed-DPI or second-monitor acceptance was completed. |
| Existing Task Recorder screen | **Blocked/incomplete**; saved desktop tasks do not yet appear in that screen. |

The final trial saved task `fd8bfaba-526c-442a-9991-09aaf6664987`, revision
`d05cff53fa183723693ddf1e93cf6be0c5f0fd2f1989fdfef4741996035516a7`.
`evidence/final-native-task.json` contains the synthetic field contents.
The phrase `PAUSED_ONLY` is present in this **separate later recording** because
it was already in the prepared page when that later field was edited; the
earlier Pause trial's draft excludes it. Do not conflate the two trials.

Final source/build hashes identify the final Stop/Save trial. Earlier button,
toggle and Pause trials preceded subsequent acknowledgement, timer and Resume
fixes; they are not full final-build regression evidence.

## Product Uploads assessment

Ran the actual recovered renderer in isolated localhost preview with disposable
PSD, provider doubles and real local mockup generation. Selected `Same.psd`,
named `Recorder synthetic product`, selected Baseball, then pressed the real
`Generate mockups` button. The first generation failed with FileNotFoundError;
the candidate wrapper's longer runtime path was replaced with a unique short
TEMP directory, after which generation reached **Mockups ready**.

Observed the real embedded gallery control:
`sc-product-upload-copy` → button `copyPrompt`, accessible name
`Copy Black Frame Prompt`. Clicked it after readiness; clipboard success was
not independently verified. Screenshot: `evidence/product-preview.png`.
This was browser-level inspection in the supported in-app browser, **not native
capture evidence** and not a substitute for an existing-tab adapter trial.
No browser extension was installed or insecure debugging enabled.

Starting product/PSD/category are setup context, not inferred recorded actions.
The contract distinguishes prepared/specific-product/per-run-product contexts;
the native toolbar currently supplies only prepared-window context. Product
binding selection and an existing-tab semantic adapter remain unfinished.
No wait for “Copied” was inserted. Reliable readiness waits remain Phase 3.

## Checks and bounded measurements

Final native build succeeded. Twenty Python tests passed (13 retained foundation
+ 7 Phase 2); Node diagnostics are recorded separately in verification evidence.
Checks cover ordering/generation barriers, late events, privacy rejection,
capacity failure, save durability/retry, duplicate IDs, immutable definitions,
recovery, format compatibility, catalogue caching and desktop Play guards.
Automated events are not presented as native user-action proof.

Under the Windows Computer Use instrumentation, 3-second final-build samples:

| Process/sample | CPU seconds consumed | Working set after sample |
|---|---:|---:|
| Native idle | 0.40625 | 103,690,240 bytes |
| Native armed, no application input | 0.53125 | 106,176,512 bytes |
| Python idle / armed | 0 / 0 | 37,277,696 / 37,302,272 bytes |

These are process CPU deltas, roughly 13.5% and 17.7% of one core, not whole-PC
percentages. They do **not** establish an acceptable idle budget; profiling
outside accessibility instrumentation remains needed. No desktop-wide scanning,
video, screenshots or mouse-movement sampling was added to the recorder.
Final durable Save: **3.66 ms**; earlier captured button/toggle Save: **4.18 ms**.
No reliable input-to-action latency distribution was measured. Old browser/
relay speed evidence is not native Windows performance evidence.

## Remaining Phase 2 work before Phase 3

1. Resolve the supported Studio handoff. Integrate `Catalogue` with
   `DeviceAgent.snapshot/perform`, the existing durable receipts, registration,
   relay and file bindings. Extend `state_updates.SUMMARY_FIELDS` for explicit
   format/capability metadata and negotiate protocol 6. Keep legacy routing.
2. Adapt existing `panel.js` controls using acknowledged native state, keyed rows,
   deltas and lazy details. Disable desktop Play with a Phase 3 explanation.
   Do not route desktop definitions into the browser runner.
3. Complete control/document identity beyond title + UIA name/ID, including
   ancestor/document scoping and ambiguity checks. Current focus actions occur
   with accepted input; foreground-only changes are not captured independently.
4. Finish event correlation for selection, menus, document replacement and
   provider races. Text reads are deferred to flush; distinguishing subsequent
   programmatic field changes from user changes is not fully solved.
5. Complete actual Notepad/cross-window, Resume, selections, password-before-read,
   provider failure, moved-window/mixed-DPI and embedded Product Uploads trials.
   UIA-first findings must determine whether the small existing-tab adapter is
   necessary; no native Product Uploads support is asserted yet.
6. Confirm low idle overhead and responsiveness outside the UI inspection tool.
   Preserve the recovery archives and all trial drafts.

Then Phase 3 can implement explicit Play, target revalidation, readiness waits,
visible progress, independent emergency cancellation and held-input release,
with results separate from immutable tasks. Playback is not implemented here.

All work is local. Nothing was committed, pushed, merged, deployed or installed.

### V1 physical acceptance update — 2026-10-20

The normal-input local candidate recorded and saved `Physical trial 1` and `Physical pause resume`. Saved definitions remained byte-for-byte unchanged after candidate restart and playback. Pause trial captured `Before pause` and `After resume`, with no `Paused only` action. Stop flushed the final focused field and toolbar interactions were excluded. Save latency samples were 2.97 ms and 6.26 ms.

Playback attempts exposed two real defects: immediate focus validation before activation completed, then immediate value read-back before Edge published the new accessibility value. The executor now waits boundedly for focus and fresh scoped read-back, without repeating effects. Third-window focus changes and cancellation remain guarded. Failed results return normal controls; uncertain effects remain blocked until explicitly reconciled. The task dropdown preserves the executed task.

Run `d2598f76-2a4f-45d2-90b9-2134cb18dd5b` executed `Physical trial 1` revision `1b9cdd8f64656b4d6944294fb0d4cb300e7e39d43b6834b1bec25f13478b3279`: both focus and text steps verified, no pending action. Expected text was verified through fresh UIA ValuePattern read-back. User reported Completed; final visual value confirmation remains requested. Earlier failed runs remain preserved and are not counted as completed acceptance.

Evidence: `evidence/v1-physical-record-save.json`, `v1-physical-pause-resume.json`, `v1-physical-reload.json`, `v1-focus-failed-run-original.json`, `v1-readback-failed-run-original.json`, `v1-readback-fix.json`, and `v1-physical-text-playback.json`. The latest focused automated suite has 33 passing tests. A subsequent local UI-only change replaces misleading recording time after playback with step progress; compiled to `.local-data/progress-build`, not yet installed in the running candidate.

This proves only the bounded local native Edge text path. Cross-application/Notepad, real OS catalogue integration, Product Uploads, emergency-stop acceptance, final performance, packaging and installed release remain incomplete. Windows Computer Use continues to return mismatched screenshots (Notepad target returned Sports Cave OS); no input was sent to the mismatched target. No production helper update or deployment occurred.

### Subsequent physical acceptance evidence — 2026-10-20

This update supersedes the earlier pending Edge value confirmation and Notepad
status. The user confirmed the Edge playback result `V1 Physical`. A separate
Notepad recording and playback completed two steps, and a read-only accessibility
observation confirmed `Notepad text final`. Its saved definition was unchanged.
See `evidence/v1-notepad-playback.json` for the run, revision and tested binary.
These are separate application trials, not a combined cross-application pass.

The Notepad title-anchor change subsequently exposed an Edge capture regression.
The revised click handler prefers the focused editor only when its bounds contain
the clicked point and its process, privacy classification and ancestry validate.
It retains the text-input identity guard. On native binary SHA-256
`756ED806485BB15E5ABD2901748D78AA73EA3F1237E7CCE571481771C81FF99B`,
normal physical input now identifies `Edit/example/Example text`. The click-only
trial read no value and emitted no action. The next typing trial produced exactly
one focus action and one scoped text action containing `Edge anchor verified`,
with final-field flushing at Stop and no duplicate actions. Its draft lasted
14,934 ms. Evidence is preserved in `evidence/v1-edge-click-anchor-pass/` and
`evidence/v1-edge-anchor-text-pass/`. Save/playback of this latest draft and
combined Edge-to-Notepad recording are still pending.

The current candidate does not enable injected-input acceptance. Computer Use
previously routed an attempted acceptance-page click to a different Edge window;
the recorder rejected that target, and the trial was not counted as passed.
See `evidence/v1-edge-anchor-tool-routing-blocker.json`. Physical user input is
therefore required for the remaining native acceptance interactions.

No release commit, deployment or installed-helper update has occurred. Real OS
task-list acceptance, Product Uploads readiness/copy, emergency-stop trials,
final performance and release packaging remain incomplete.
