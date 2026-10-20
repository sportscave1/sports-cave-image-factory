# Windows Recorder V1 — current local checkpoint

Status: local candidate with passing focused acceptance; release is unfinished.
Do not deploy or install this revision. Final Copy 21 completed 2/2 with exact
post-play clipboard verification and an unchanged saved definition. Combined
Edge/Notepad, scroll, checkbox, selection, menu expansion, safety controls and
second-monitor playback have physical evidence. Native provider/queue failure,
capacity, package preparation and disposable startup/update/rollback also have
focused checks. See [the final review checkpoint](LOCAL-REVIEW.md) for current
artifacts, measurements, build distinctions and remaining gates. General button
results, including Generate replay, remain unverified and stop as uncertain.
Actual Product Uploads Generate/readiness were exercised with synthetic providers;
that is not native Generate playback acceptance. Installed-helper acceptance,
exact-commit Studio/integration review and authorized release remain outstanding.
The chronology below is historical; earlier pending/failure statements do not
override subsequent evidence.

## 21 October continuation (local, uncommitted)

The user requested continued development and focused testing. Original evidence
was read from the original checkout's `windows-screen-recorder/evidence/` without
editing it. The taskbar transition was reviewed; its physical acceptance is still
pending. A fresh native candidate was launched using this release worktree and
disposable storage at
`C:\Dev\SportsCaveWorktrees\.studio\runtime\20261020-ff6cc91d\combined-20261021`.
Injected input acceptance is disabled. The requested capture uses Edge text
`Edge combined 21`, a taskbar switch, Notepad text `Notepad combined 21`, and Save
as `Combined 21`. Inspect the actual saved actions before restart/reset/Play.

First physical attempt interrupted on the initial click: the selected prepared
window was `Ads Manager - Manage ads...`, while the actual input/foreground root
was the separate `Recorder harmless acceptance...` Edge window. Diagnostics
confirm distinct roots, both existing, and correct child/root normalization.
The preserved draft contains zero actions. This is not a taskbar trial pass.
Evidence was archived within that runtime under `failed-initial-window-selection/`.
The current candidate can be retried after Review, Discard, Refresh windows and
explicit selection of `Recorder harmless acceptance...`; no guard relaxation or
native rebuild is warranted by this evidence.

Second physical attempt selected the correct test-page window. It interrupted
when UIA returned RootWebArea through the 150 ms focus-publication check; zero
actions were captured. Its evidence is archived under that runtime's
`failed-editor-publication/`. The revised native path retains an unresolved
editor click for at most 2 seconds and validates it against the actual focused
editor on the next input. Process, window, generation, click containment,
privacy, ancestry, window bounds and DPI must still validate before any value
read. An unresolved click blocks subsequent input/barriers rather than silently
disappearing. RootWebArea is never used as a field. Focus-resolution failures
now include metadata-only diagnostics. No native input was injected.

The old development native process was identity-checked and stopped after
archiving the failed attempt; its coordinator exited. The revised candidate is
running with fresh storage at
`C:\Dev\SportsCaveWorktrees\.studio\runtime\20261020-ff6cc91d\editor-handoff-20261021`.
Native build and 7 focused delayed-click policy checks pass; physical success
of this revised editor path remains pending. Next physical check should be
short: select the test-page window, Record, click inside Example text and type
immediately, then Stop/Save if capture remains active. Resume the combined
trial only after inspecting this capture. All broader V1 acceptance remains open.

The editor-handoff attempt also failed with zero actions. Metadata proves the
focused element was an Edit in the expected process with keyboard focus, but
the click was outside its rectangle. The user confirmed clicking the `Example
text` label, which focuses the HTML input. This corrects the earlier inference
that focus publication alone explained the failure. Evidence is preserved under
`editor-handoff-20261021/failed-label-click/` in the task runtime.

The current native source accepts a label click only through UIA's explicit
LabeledBy relationship, with a visible Text label, matching process, validated
same-window ancestry and click containment. Matching names or enlarged bounds
are not accepted. Unsupported label relationships still fail closed; direct
editor clicks retain their original checks. Unresolved-focus messages now
describe the click/label mismatch accurately. Native build and 13 focused
pending-click/linked-label policy checks pass. These are not physical proof of
the browser's label provider. The refreshed local candidate uses fresh runtime
storage `C:\Dev\SportsCaveWorktrees\.studio\runtime\20261020-ff6cc91d\label-focus-20261021`.
The previous candidate was identity-checked and stopped after archiving.
No browser input was injected; the browser inventory did not expose the user's
Edge tab for read-only inspection. Next establish direct-box capture physically
before proceeding to combined capture/playback. No release action performed.

The user subsequently saved `Edge focus test`. Its inspected definition
`7a597516-b417-4fce-b341-099e59d3f15e` contains exactly two actions: focus the
correct test-page window, then scoped Edit/example text `Edge combined 21`.
Revision is `93e2c26e9b05566898ca2d9fad69d688b8e19c3757c1665e99e73be9d25938a7`;
save latency 2.31 ms. No run was started by Save. This establishes the direct-box
physical capture only, not label-click or combined capture acceptance.
Evidence is archived in `label-focus-20261021/verified-edge-capture/` within the
task runtime, including definition and binary hashes. The idle candidate was
identity-checked and restarted against the same storage and same native binary;
the saved file hash remains unchanged. Physical reset/Play/readback is next.

The user then reported Completed and `Edge combined 21` restored in the box.
Run `ede42ff4-bc58-46e8-a9b9-cf0fcb3a1b9d` confirms completed 2/2, both steps
verified, no pending action. The definition SHA-256 remains
`B52346AFE6161CD35777367888E58E727A8B4CF19760116C15A298D36700E743`.
Evidence is archived under `label-focus-20261021/verified-edge-playback/`.
This verifies the current candidate's separate direct-box Edge
capture/save/restart/reset/Play/readback path. Do not repeat that trial without
a new failure or relevant change. Next: combined Edge/Notepad capture using
the taskbar transition, inspect both actual actions, then save/restart/reset/Play.
Label-click capture and all remaining V1 acceptance items are still open.

The user saved `Combined 21` without an interruption. Inspection confirms
exactly four version-2 actions, in order: Edge focus, scoped Edit/example
`Edge combined 21`, Notepad focus, scoped Document/Text editor
`Notepad combined 21`. Native diagnostics include `taskbar_window_switch` to
the already-open `Untitled - Notepad` window. Task ID:
`837db16f-9533-4e63-a49c-8d1bb7216acb`; immutable revision:
`fe8ca535d3c9b8b963061095acf0af4c7d3f955428e01afa92c333fc3efe97d9`.
Save latency was 2.48 ms. Capture evidence is archived under the task runtime's
`label-focus-20261021/verified-combined-capture/`. The idle candidate was
identity-checked and restarted against the same storage/binary; the saved file
hash is unchanged. Combined capture is now verified. Combined reset/Play and
both actual final values remain pending; do not call full combined acceptance
passed until that journal and user-observed values have been inspected.

Combined playback has now passed on the current native binary. The user reported
Completed with both exact values restored. Journal
`3a885da1-efd0-4636-b1e3-9007a213d7e5` independently confirms completed 4/4,
all results verified, no pending action. Saved-definition SHA-256 is unchanged:
`B7B27B2474FFD637D75D20E05925183ADBB658E01ACB5C899A5C740BCD7D596C`.
Evidence is archived under `label-focus-20261021/verified-combined-playback/`.
Do not repeat standalone combined acceptance without a relevant new change or
failure. Remaining acceptance now proceeds through the real UI/relay.

An isolated full OS recorder page is running on `http://127.0.0.1:18961` using
the existing environment-scrubbing, loopback-only preview launcher and synthetic
account/database. The synthetic helper runs on port 18933 using the new
`scripts/task_recorder_native_ui_trial.py`, fresh task-owned storage and only the
explicitly imported Combined 21 definition. It uses the real Bridge,
DesktopRunner, DeviceAgent, DPAPI vault and relay protocol. External socket
connections and subprocesses other than the reviewed native binary are denied.
No installed helper storage/settings are touched. The completed standalone
candidate was identity-checked and stopped to avoid a second native instance.

Real page pairing/connection and the four-step native catalogue row were observed.
The UI now disables desktop Rename/Edit/Delete commands rejected by the adapter,
and disables Play for unavailable/unsaved native definitions. Browser-only name
and starting-website labels are hidden for native capture, and Record's receipt
instructs the user to select a prepared window on the Windows toolbar. Pairing
copy no longer claims that the helper only controls a dedicated browser. These
UI refinements pass JS syntax/transport checks and six focused adapter tests.
UI-triggered native Record/Play and durable receipts remain to be inspected.
Runtime is `C:\Dev\SportsCaveWorktrees\.studio\runtime\20261020-ff6cc91d\native-ui-trial`.

The first real UI Record launch produced an uncertain durable receipt
`b5aae458-6878-4049-888b-642bcd91ff2e`. No native process/capture started.
The trial's subprocess audit guard mishandled Windows' documented event shape:
executable=None and a quoted command-line string. A non-launching audit check
confirmed that shape; the guard now validates the exact reviewed binary command
including its arguments. The failed receipt remains unchanged. UI Stop command
`d4e4fdda-548e-4dec-ad72-a4286c5e9f58` was applied before restarting the helper.
Fresh UI Record command `3414eb7d-07cc-4338-9461-df25c5b3984a` was applied,
durably persisted and reflected the prepared-window instruction on the real
page. Native process 18788 was observed responsive with the expected title and
reviewed executable path. No capture started automatically. These receipts are
exported in the synthetic helper's `trial-receipts.json`.

The real UI now has Combined 21 selected for a playback trial through the relay.
The page is kept open in the in-app browser. Browser-only reusable-input settings
are hidden for desktop tasks. UI Play/result, live capture Pause/Stop barriers,
and command recovery across a helper restart are still pending. Current checks:
6 adapter tests, Node transport, JS syntax and trial-launcher syntax passed.
No commit, push, production deployment or installed-helper replacement occurred.

First physical website Play stopped 0/4: run
`d6b6f505-3dca-429c-9a90-80559c85c5f5` confirms step 0 failed with no_effect=true,
no pending action and `Could not safely focus the intended window. No input sent.`
Windows denied foreground activation from the background helper. Definition and
failed journal/state are archived under `native-ui-trial/failed-web-foreground/`.

Website Play now explicitly requires Start playback on the Windows toolbar.
The adapter marks the internal arm instruction as requiring local confirmation;
the native host does not arm or send play_ready until that local foreground
click. Native-toolbar-originated Play retains its foreground path. Stop cancels
pending preparation. The page now shows the starting instruction and actual
stop reason. Native build, seven focused adapter checks (including cancellation,
duplicate request and late readiness without dispatch), Node transport and
syntax/diff checks pass. The synthetic helper was gracefully restarted; only
the task-owned development binary changed. Current binary SHA-256:
`8E7303851989241AD1CC282718F5439042EDB0F7DD6B364CDC71B4C77FCD3640`.

Fresh website Play request `a452d31c-e386-420b-b322-a30d8e9e23d1` has an applied
durable preparation receipt. Helper state is starting and there is no new run
journal for that request: no action has been dispatched. Native process 26180
is waiting for the user's Start playback click. Leave the page and helper open.
Next: both prepared fields empty, Notepad Untitled, then one local Start playback
click and inspect the resulting four-step journal, both values and definition
hash. This revised UI path has not yet passed physical acceptance.

The user clicked the local Start playback and confirmed Completed with both
exact values restored. UI-triggered run
`a452d31c-e386-420b-b322-a30d8e9e23d1` verifies completed 4/4, all results true,
no pending action, and an applied durable preparation receipt. The saved
definition hash is unchanged. Evidence is archived in
`native-ui-trial/verified-ui-playback/`. This establishes real OS page / relay /
DeviceAgent / native handoff / executor / result projection for this trial.

Current development adds scoped `expand` (explicit bool) and `scroll` (finite
absolute horizontal/vertical percentages) actions. Wheel bursts are bounded and
coalesced at the same point/window; no wheel coordinates enter saved definitions.
Playback uses UIA ExpandCollapse/Scroll patterns once and re-resolves/read-backs
the resulting state; it does not repeat an unverified effect. Indeterminate
toggles and unselected item observations interrupt capture. Generic invoke still
has no application postcondition and remains uncertain; arbitrary button/menu
commands are not completed support. Scroll/menu provider acceptance is pending.

Also fixed: active/pending native task names and totals are projected into the
page; recovered run summaries follow journal modification order; shutdown no
longer changes completed runs to stopped. The old running helper still had that
shutdown bug, so after its graceful shutdown the verified completed trial
journal was restored from its archived exact source, guarded by an equality
check allowing only the terminal-state difference. Both the old shutdown-mutated
journal and a repair receipt are preserved under verified-ui-playback. No task
definition was repaired or changed. The new regression test confirms completed
journal bytes survive Stop/shutdown/recovery unchanged.

Checks: native controls build passed; 35 desktop tests passed before the terminal
shutdown fix; 12 focused playback tests passed including the new shutdown
regression; 7 adapter tests passed. The updated helper is running, and native
toolbar launch was requested through the real page. Binary SHA-256:
`96665585DEB06084293F2C2BD7FC528F5F22F1186F878F0F26DC2C8D00AB97F5`.
The harmless controls fixture is served loopback-only at
`http://127.0.0.1:18974/controls-fixture.html` from this task's tests directory.
Next physical capture: open it in Edge, Refresh windows in the native toolbar,
select Recorder controls acceptance, record checkbox On, Second choice, open
Example menu, and scroll inside the bordered sample. Stop/Save as Controls 21.
Inspect actual actions before any reset or playback. Stop immediately on an
interruption. All Product Uploads, remaining safety/performance and packaging /
installed-helper release work stays open. No release action was performed.

Controls capture interrupted before any actions: draft
`05b25120-ef91-42d1-9d08-e053268549b3` selected the older Edge window
`Recorder harmless acceptance`, while the actual click reached the ChatGPT
in-app browser. Native identity diagnostics consistently identify ChatGPT as
the clicked/foreground root and msedge as the selected root. The controls page
had opened inside ChatGPT, so its title was absent from the eligible Edge
window list. This is an expected window mismatch interruption, not controls
acceptance. Preserved draft, diagnostics and state under local runtime
`native-ui-trial/failed-controls-in-app-browser/`. Retry requires pasting the
fixture URL into Microsoft Edge itself and selecting its exact controls title;
do not weaken the ChatGPT exclusion. No additional tests or binary changes.

The next physical controls capture selected Edge correctly. Draft
`13c4a038-795d-4e6a-a36d-bef808574136` durably contains focus, checkbox On,
Second choice selected and Example menu expanded; scroll interrupted with
`The scrolled control has no supported scroll position`. This is capture
evidence only; these controls have not passed playback. Preserved evidence in
`native-ui-trial/failed-controls-scroll-position/`. Candidate lookup now uses
bounded raw UIA ancestry so layout scroll containers omitted by Control View
can be considered, retaining privacy, process and selected-root validation.
Unsupported scroll diagnostics now include ancestor control types/IDs, pointer
containment and pattern availability, without text values or pointer positions.
Native build and 15 foundation tests passed. Development binary SHA-256:
`FD23B730B31B033F1BAD10AD65ADE34C4B5C50A7BCE28A8650723B7D8EB8AB57`.
Synthetic helper restarted; scroll-only physical verification remains pending.

User completed uninterrupted physical scroll capture and saved `Scroll 21`.
Independently validated saved task `100869bf-d3ef-4a68-9bb7-f5a0438b3d89`,
revision `32502f0b2a0ef8512d1c5306e29d55b06df21f1ce0a8f10fc1e70e306f4dd8ba`,
file SHA-256 `feac53cb8874786d56312b1b7a783fb55224c51682a3ae4cbe24fcc8d19bd24d`.
It contains focus plus 26 bounded absolute scroll observations, all scoped to
Group `scroll-sample` / `Scrollable sample` in the correct Edge document.
Horizontal is unsupported (-1); vertical ranges 0..100 and ends at 0 (top).
Saved definition and inspection preserved in `native-ui-trial/verified-scroll-capture/`.
Playback remains pending: manually set the sample to bottom, select Scroll 21
in the native toolbar and Play once; require per-step readback and final top.
No broad test rerun was needed for inspecting this recording.

Physical Scroll 21 playback completed and user confirmed movement back to top.
Run `4598a194-3714-4f67-8a89-92a76c8774eb` independently shows completed 27/27,
every result verified, no pending action, matching saved revision and byte-for-byte
unchanged definition. Archived under `native-ui-trial/verified-scroll-playback/`.
Its completed journal also survived the next graceful helper shutdown unchanged.

Next controls capture interrupted: draft `5ff54d58-586b-4a9c-9bce-f8b7bcfe2bea`
contains only focus and checkbox On. The subsequent click entered pending editor
classification, and the later menu click flushed it after its timing window.
This does not prove the menu caused the original failure. Evidence preserved in
`native-ui-trial/failed-controls-radio-label/`. Candidate click traversal now
uses bounded raw ancestry and validates the provider's explicit LabeledBy text
relationship for focused toggle/selection/expansion controls. Existing bounds,
privacy, process and ancestor validation remain required; no name-only matching.
Pending-click diagnostics now identify traversed control types and focused type.
Website interruption status now preserves the helper's actual reason rather than
always telling desktop users to check a browser. Native build, 13 no-input
click-policy checks and focused JS transport/status checks passed. Binary SHA-256:
`6E887870E345092497E3E3A751D7B5F7037CAEAB73D118B1C0322D261C002167`.
Synthetic helper restarted; updated click path physical acceptance remains pending.
Generic button result verification, actual Product Uploads synthetic-provider
acceptance, packaging and remaining final-candidate safety/performance remain open.

User completed uninterrupted Controls 21 capture with the updated click path.
Independently validated saved task `ec4f71de-3a6a-40ab-812a-5cd35e88caef`,
revision `09e5e75e6d103c70d4434506e3b357c80a898aa83cfbde7df5096af3843d069a`,
file SHA-256 `41fe2aa97e707d70fd3d183f96b86ca2ca51e2c08fe00625912c529c09f350d9`.
Exactly four scoped actions: Edge focus, Example enabled checkbox true,
Second choice radio selected, Example menu expanded true. Preserved definition,
diagnostics, snapshot and inspection in `native-ui-trial/verified-controls-capture/`.
No playback has yet been verified for these controls. Next reset manually to
checkbox Off / First choice / menu closed in the same Edge window, then select
Controls 21 and Play once from the native toolbar. Require completed 4/4,
per-action readback and user-confirmed final visible states before marking pass.

User reported Prepare recorded window during the attempted controls playback.
Actual run `9e96ada4-836e-43e8-84be-6293fc62d276` was Scroll 21, stopped 0/27,
no_effect true, no pending action. That older recording had a different exact
Edge window title. Controls 21 was not executed. Evidence preserved under
`native-ui-trial/failed-controls-play-selection/`. Found native dropdown bug:
every idle snapshot overwrote the user's selection with the historical run's
task, and rebuilt even unchanged items. TaskList now keeps unchanged items and
preserves the current selected task on catalogue changes; previous run is only
a fallback when the current task is absent. Native build and five checks using
actual WPF ComboBox objects passed without a window or injected desktop input.
Binary SHA-256 `36CD9DA37C8AACC511CAB2B4B926EB5C359FDC30A8F3D3F8F26D61E7EA5DDAE3`.
Restarted isolated helper and prepared Play Controls 21 through its exact website
row. Snapshot confirms Controls 21 / starting / 0 of 4; local Start playback
confirmation is pending, with no actions dispatched. Definition remains unchanged.

User confirmed Controls 21 completed 4/4 with checkbox On, Second choice selected,
and menu open. Independently verified run `2dea6c1d-b373-4002-89a4-65d6d5eada47`:
completed 4/4, every result true, no pending action and matching revision. Saved
definition matches the capture archive byte-for-byte. Evidence archived at
`native-ui-trial/verified-controls-playback/`. Toggle, selection and expansion
now have physical capture/playback evidence; arbitrary invoke remains incomplete.

Preparing final-candidate stop acceptance found playback mouse intervention used
foreground PID, potentially cancelling a click on the native toolbar before it
became foreground. It now classifies mouse input by its actual hit/root window;
keyboard input still uses foreground, and outside clicks/wheel/keys still stop.
The existing six native identity checks and native build passed. Registered
Windows emergency-hotkey handling now emits an explicit diagnostic, allowing
physical acceptance to distinguish that path from generic keyboard intervention.
Fixture has Hide menu for stop check / Restore menu controls, with no network
or provider calls; hiding the existing menu lets Controls 21 wait at its final
action without changing the immutable definition. Synthetic helper restarted.
Binary SHA-256 `465517C09F875DAC8697B6F6FDF3070B7E1DB66DEB913E424CFEADAEE52A63A9`.
Next trial: refresh fixture in Edge, hide menu, start Controls 21, pause from
native toolbar while waiting, then Ctrl+Alt+F12 with toolbar focused. Stop,
hotkey diagnostic, pending result and unchanged definition require inspection.

The first stop attempt completed normal Controls 21 playback too quickly:
`b018dc11-1ed2-416d-a6a9-fc4ae20c4e13` completed 4/4, not a stop acceptance pass.
Preserved under `native-ui-trial/stop-check-attempt-completed/`. To remove the
timing dependency on fixture preparation, created a separate explicitly synthetic
task `Safety stop check (synthetic)`, ID `03376c2f-bd6b-4c0d-821f-b1bad67a41d8`,
revision `4d460be2cba503e5386a53a1269fd4adc1a7afa378638e2646ece051a0ad374d`.
It has one 30-second wait_ready action for an intentionally absent scoped
control. It has no application input actions and is not captured physical proof.
Definition/purpose stored in runtime `safety-stop-fixture.json`; existing saved
recordings remain unchanged. Prepared via exact website Play row, starting 0/1,
awaiting local Start playback. Next: user clicks Start playback, leaves native
toolbar focused, presses Ctrl+Alt+F12; inspect registered-hotkey diagnostic and
terminal journal. No Edge preparation or new recording required for this check.

Physical Ctrl+Alt+F12 acceptance passed on the synthetic readiness wait.
Run `158978c4-e485-414c-ab69-76313bdcf239` is stopped 0/1, result_received true,
pending null and one verified-false/no_effect-true result. Native diagnostic
explicitly records `emergency_stop` / `registered_windows_hotkey`, independently
confirming the registered shortcut rather than generic keyboard intervention.
User saw Emergency Stop requested. DeviceAgent Play receipt is durably applied;
the synthetic definition remains unchanged. Preserved journal, diagnostic and
snapshot in `native-ui-trial/verified-emergency-stop/`. This verifies cancellation
during readiness wait; it does not prove cancellation during a provider mutation.
Next reuse the same no-input wait to physically Pause, Resume, then click blank
Edge space to verify ordinary manual intervention. Other final safety, actual
Product Uploads and packaging/release work remains open.

Physical native Pause/Resume and outside click stop passed on the synthetic wait.
User confirmed Pause and Resume worked, then clicking Edge reported Manual input
stopped playback. Independently verified run `8c8f0871-2903-4c8e-98cd-815c6f363517`
stopped 0/1, pending null, no_effect true. Completed native play_pause and
play_resume receipts were identified by reconstructing their empty-payload
command fingerprints and matching the durable hashes after this run's relay
Play row; archived with journal/state in `native-ui-trial/verified-manual-intervention/`.
Synthetic saved definition is unchanged. The late cancelled action result
overwrote the manual-stop reason with Playback stopped; fixed reason persistence
in journal/acknowledgement and coordinator. Thirteen focused playback tests pass,
including stop-reason preservation through restart and completed-journal stability.
Synthetic helper restarted; native executable unchanged. Added a disposable
pre-filled type=password Protected test field to the controls fixture. Next
physical capture: refresh in Edge, select that window, Record, click only the
masked field and expect immediate protected-input interruption; inspect draft
and diagnostics before saving/discarding. No real credential entry is needed.

Protected field physical check passed. User clicked the prefilled masked field
and immediately saw Protected or unknown text field excluded before value
collection. Draft `459aa399-6194-42f0-befc-97098271aad5` is interrupted with zero
actions. The synthetic masked value is absent from draft, diagnostics and all
durable receipts. Evidence: `native-ui-trial/verified-protected-input/`.
Then terminated only the native process after checking its exact development
executable path and parent PID against the isolated helper. Draft stayed
byte-for-byte identical, with no automatic native restart. Graceful helper
shutdown/restart also recovered that same interrupted empty draft without replay.
Evidence: `native-ui-trial/verified-protected-disconnect/`. This is interrupted
draft recovery evidence, not an in-flight mutation/provider-failure acceptance.

Packaging implementation now includes deterministic ZIPs containing both Python
packages, x64 native executable, native build sources, pinned dependency closure
and a per-file size/SHA-256 manifest. Setup prepares each version and its venv
in a separate final directory, verifies imports/isolated adapter initialization,
then switches active.txt after confirming the prior helper is idle. Previous
versions and the legacy installation are retained; stable launchers preserve
the existing startup path and provide Rollback.cmd. Data remains outside code
releases. The authenticated hosted setup route serves a verified configured
artifact (SPORTS_CAVE_RECORDER_WINDOWS_PACKAGE), or a locally built full bundle;
a host lacking both returns unavailable rather than a browser-only archive.
No Render configuration was changed. See PACKAGING.md for the build recipe.

Four focused package tests passed: deterministic/full bundle and tamper/path
rejection, preparation failure/busy guard/rollback preserving data, tampered
source refusing preparation, and authenticated download/full-artifact selection.
Seven adapter tests also passed after the stop-reason change. VBS was parsed
with an unsupported argument that exits before launch; rollback PowerShell was
parsed without execution. Actual bundle rebuilt identically and passed -I
extracted-package health/adapter initialization using only disposable storage.
Candidate ZIP SHA-256 `0df675186b179b972aa7648c602a5208846d113154a8174783e2020ad2b387c3`,
manifest `3eafe224ffed27acd5cf69d7749945e840367854facba81782b54aa3efcea069`,
under runtime `native-ui-trial/package-candidate/`. It was NOT installed or
published. Actual installed first start/update/rollback remains unverified.

New `scripts/task_recorder_product_trial.py` reuses the actual Product Uploads
renderer/components/services with a new isolated PostgreSQL database on the
existing synthetic loopback server. It generates a small valid tagged synthetic
PSD, uses an in-memory Dropbox/output provider and a synthetic pixel renderer;
external connections and installed Companion render requests are prohibited.
Fixture runs on port 18975; current URL/PID are in runtime
`native-ui-trial/product-ui/ready.json`. No original PSD or customer data is used.
Actual UI Generate was clicked once: provider generated five core images,
Mockups ready appeared, 5 of 8 readiness correctly kept Save All disabled.
Embedded Copy prompt showed Copied, but the IAB clipboard readText/read APIs
returned empty; exact clipboard acceptance is therefore NOT passed. This also
does not validate native recorder button playback. The fixture now captures the
real component's prompt argument and offers a local paste verifier retaining
only match/length/SHA-256. A named wrapper makes its Edge title unambiguous.
Next physical trial should record only that actual Copy prompt button after
Generate is ready, save without playing, then paste into the local verifier.
Inspect its actual native scopes and exact pasted-text result before adding
application-specific invocation postconditions. Generic invoke still stops
uncertain, and final provider/DPI/performance/release checks remain open.

Final prepared Product fixture URL for this checkpoint:
`http://127.0.0.1:18975/?upload=877ed75f-78c7-48c1-90a3-306c002537d6`,
server child PID 42536, logs product-ui-5.out/err.log. Browser tab 5 is an IAB
inspection tab, NOT the physically recordable Edge app. Native toolbar reopened
after disconnect recovery (PID 40164, same reviewed development binary), still
showing the protected interrupted draft. That draft remains byte-identical to
its archive. User can Review/Discard this archived empty test draft before the
next capture. Next Edge trial: open the URL in actual Microsoft Edge, choose
Cricket / Generate and wait for Mockups ready; select Recorder Product Uploads
acceptance in native recorder, record Copy prompt only, Stop/Save Product Copy 21,
then use the page's Open synthetic clipboard check link and paste/Verify. Do not
play this generic invoke recording before inspecting the actual target scopes
and adding/verifying application-specific postconditions. Paste verifier stores
only current intake ID, exact text match, byte length and hashes, no pasted text.

Fixed helper integration: relay capture Pause/Stop receipts now wait for the
correlated native flush acknowledgement; duplicate relay delivery does not
repeat it. Native disconnect rejects pending confirmation, interrupts the draft,
and clears pending Play. Active desktop drafts, selected IDs and durable run
results are projected into the existing UI snapshot. Inspect no longer launches
the native toolbar. The development launcher accepts an explicit existing Python
environment and uses the current task package instead of the old dependency
export. These helper changes are not installed and the standalone physical
candidate does not establish DeviceAgent/relay end-to-end UI acceptance.

Focused checks: native build passed; desktop unittest suite 33 passed; focused
pytest adapter/transport/capability checks 17 passed; Node transport passed;
final adapter adjustments rechecked, 6 passed; `git diff --check` passed.
Physical acceptance, remaining action support, Product Uploads, final safety and
performance trials, packaging/update/rollback and release remain incomplete.
No commit, push, merge, deployment or installed-helper replacement performed.

## Original overnight checkpoint (historical)

The user ended physical trials for the night at this original checkpoint.
Subsequent authorized continuation and results are recorded above.

### Verified local results at that checkpoint
- Separate physical Edge text recording/save/reload/playback, with actual final value confirmed.
- Separate disposable Notepad text recording/playback, with actual document text read back.
- Physical Pause/Resume excluded paused edits; Stop flushed the focused field.
- Durable drafts, receipts and run journals; saved definitions stayed unchanged in the verified trials.
- Focus/readback failures were preserved rather than replayed automatically.

### Original checkpoint state
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

## Product Copy interruption and bounded button fallback (21 October)

The physical Product Uploads Copy attempt interrupted with zero recorded actions
(draft c00cb307-c2b9-4f98-90f5-7d85f1c4aac3). Window diagnostics prove the click
reached the selected Edge window; point hit-testing exposed RootWebArea while a
Button had keyboard focus. The old classifier waited for an editor and stopped.
Original draft and diagnostics are archived outside Git under native-ui-trial/
product-copy-click-interruption. No replay was performed.

Capture now accepts a focused Invoke button only if its actual physical rectangle
contains the click, its process matches, it is on screen, and Target validates its
ancestry to the selected window. Existing explicit semantic-label handling remains.
Product gallery Copy buttons now keep their accessible purpose names during
Copying/Copied feedback. Native build, existing 13 click-policy checks, Copy feedback
regression (including stable accessible names), and diff whitespace check pass.
These are local checks; the new physical Copy capture is still pending, and generic
Invoke still has an uncertain result without a supported postcondition.

Only the disposable development native candidate was replaced. SHA256:
81BC9D346195E3D2360E83C0666B7A835522208FC40FBBF27F35FB319BCA6825.
The isolated helper was restarted; the interrupted draft remains available for
explicit review. The previously built package is now stale relative to this fix
and must be rebuilt before package acceptance. Installed helper untouched.

## Dropdown click interruption (21 October, local only)

The next preserved Product UI attempt reached the intended Edge window but
reported ComboBox focus on RootWebArea hit, then ListItem focus on the following
click. The old pending-editor path interrupted. No Copy acceptance is inferred.
Evidence is archived under native-ui-trial/product-dropdown-click-interruption.
The bounded focused-control fallback now supports the existing UIA toggle,
selection and expansion patterns as well as Invoke buttons, requiring direct
physical containment and validated ancestry. Unresolved non-text focus stops
immediately instead of authorizing pending text reads. Native compilation and
13 existing click-policy checks pass; no new physical acceptance yet. The isolated
helper/candidate were refreshed; installed helper and production unchanged.
Prepare the actual Edge Product UI while recorder is idle before the next trial.

## Product page root scroll interruption (21 October, local only)

Product Copy trial interrupted before any action: RootWebArea had a ScrollPattern
but neither axis was scrollable; raw ancestors exposed no supported position.
Archived draft/metadata: native-ui-trial/product-root-scroll-interruption.
A RootWebArea-only fallback now searches raw descendants under the physical pointer
(256 visited nodes, 16 levels, 200 ms), rejects multiple scrollable containers,
and validates the selected target ancestry and unchanged foreground before emitting
its current percentages. This observes UIA metadata, never injects a wheel or
reads text values. Missing/ambiguous/anonymous targets still stop honestly.
Native build and seven no-input search-policy checks pass (unique, missing,
ambiguous, pruned branch, node/depth limits and provider cycle). Actual Product
scroll/copy acceptance remains pending. New source is included by package CS glob;
previous package is stale. Only isolated local helper/candidate refreshed.

## Verified Product Copy physical capture and exact paste (21 October)

Saved task `1f35385e-0fca-4b4d-af57-60fa8df8ab12`, name `Product copy 21`,
contains exactly focus_window then invoke of Button/copyPrompt/Copy prompt under
the actual product_upload_gallery iframe and selected Edge window. Diagnostics
confirm direct pointer containment and full ancestry validation. Revision:
081d5760bb2d6d83727e42537a934dfdb3bc656c9b0fffc35a7bd7501919dfd3.
Definition file SHA256:
4ce2002a64c818d4d62944a32547a30143d9835cbddf21e9faa0137bb606bdda.
The user's physical clipboard paste verified exact equality with the actual
component prompt: 124265 UTF-8 bytes, SHA256
1e3c47b324fa5bafcff0a01c23245a84f7a4b42d0d67876b0bc5e5feb646d9d6.
Evidence: native-ui-trial/verified-product-copy-capture. This proves capture and
pasted contents, not replay or Win32 clipboard format-byte identity.

Product gallery Copy buttons now expose meaningful tooltip states: initial
"Copy prompt to clipboard", pending Copying, and success-only "Prompt copied"
for the existing 2-second feedback interval. The name remains stable. Native
playback recognizes only the exact captured Edge/component/button scope, requires
ready tooltip before its single Invoke, then observes HelpText success while
retaining full scope/focus checks. Disabled pending buttons may be observed but
must be enabled before success. Generic Invoke remains uncertain. Missing old
component feedback refuses before effect; no fallback invocation or repeat.
Chromium's own UIA HelpText tests map tooltip text to that property:
https://chromium.googlesource.com/chromium/src/+/lkgr/ui/accessibility/platform/ax_platform_node_win_unittest.cc

Native build, seven scope-policy checks against the actual saved target, Copy
feedback regression and 13 playback journal/barrier checks pass. New candidate
SHA256 D9DF8C69EBCB33AD4FD5243773FB60D2E466566CFA9EA0E4588D0A20DC1B6329.
Only isolated local helper/candidate refreshed. Physical replay acknowledgement
and exact post-play paste remain pending. Existing package is stale again.

## Product Copy replay stopped before effect (21 October)

Run 95e601ee-61f5-45f3-892e-9d7868d5792b stopped at 1/2: focus verified,
Copy result verified=false/no_effect=true, pending=null, "Recorded control is not
ready." User confirms Copy prompt was visibly present in actual Edge. Definition
file bytes remain unchanged. Correct UTF-8 decoded revision is
081d5760bb2d6d83727e42537a934dfdb3bc656c9b0fffc35a7bd7501919dfd3.
Earlier evidence-only revision calculation used Windows default decoding; its
metadata and handoff were corrected, without editing the saved recording.
Failed run and saved definition archived under product-copy-playback-not-ready.

Added failure-only playback lookup diagnostics: up to three same-ID candidate
metadata summaries, expected-ancestor matching indices, scope/enabled/offscreen
flags and fixed Copy-readiness booleans. No actual names, values, clipboard,
coordinates or runtime IDs are retained. No matching or execution policy changed.
Native build and whitespace check pass. The isolated candidate/helper were
refreshed for one diagnostic replay; no new physical success is claimed.

## Product Copy iframe wrapper mismatch (21 October)

Diagnostic replay 22e77689-2f4e-4677-ad72-f9a892fcfedf stopped at 1/2 before
Invoke (no_effect=true, pending=null). Exactly one same-ID candidate matched
button type/name/process, enabled and visible, Copy ready=true. All six recorded
ancestors matched in order, but an additional unnamed-ID/named Group was present
between the iframe Document and outer root Group. Candidate ancestry reached the
same window and all process IDs matched. Evidence:
native-ui-trial/product-copy-wrapper-mismatch. No input effect occurred.

The actual component DOM has iframe title
product_upload_gallery.product_upload_gallery. Product Copy scope matching now
normalizes only one Group with that exact title and empty ID, at boundary index 3,
on either expected or actual scope. Every other ancestor remains exact. The
original saved definition stays unchanged. The diagnostic deliberately did not
retain the Group name, so the exact-title hypothesis still requires physical
confirmation; unknown groups remain blocked. New diagnostic reports whether an
unexpected group has this exact component title.

Native build and 15 actual-capture scope-policy checks pass, including both
wrapper directions, duplicate/unknown/misplaced rejection, and exact outer-page
and iframe checks. Only the isolated local helper/candidate refreshed. Product
Copy playback and post-play exact paste remain pending; package still stale.

## Exact-title wrapper hypothesis rejected by physical run

Run 491505f4-031f-45cd-b55b-fc79ab9733da again stopped 1/2 with no_effect=true.
The unique candidate still matches type/name/process and ready/visible state.
Its added Group has component_wrapper=false, so the exact iframe-title hypothesis
was wrong and the compatibility rule correctly did not broaden matching.
Original task definition bytes remain unchanged. Evidence:
native-ui-trial/product-copy-unknown-wrapper. No new physical success is claimed.
Stop repeated playback attempts. One fresh normal physical capture of the same
Copy button on the unchanged page (Product Copy 22) is needed to preserve the
actual current Group identity through existing Safe/Target capture validation.
No custom native inspection probe and no scope-relaxation bypass were used.

## Capture document-only hit; pointer resolution and stable feedback width

The attempted fresh capture interrupted with zero actions. Both hit and focused
element were Document; no focused button was exposed. Selected Edge identity
matched (now "and 2 more pages", so Product Copy 21's old 3-more-pages window
identity also cannot be reused after changing tab count). Original failed draft
and diagnostics archived under native-ui-trial/product-copy-document-click.

RootWebArea-only capture fallback now searches raw descendants directly under
the physical click (256 visited nodes, depth 16, 500 ms). Only a unique supported
semantic control is eligible. It validates process, foreground, generation,
window bounds/DPI, direct containment and full Target ancestry. It sends no input,
reads no text values, never waits for a disabled target to become actionable,
and preserves the draft on ambiguity/movement/provider failure. Focused and
explicit-label paths remain. Protected field checks still precede value reads.

Copy feedback locks the button's measured minimum width during Copying/Copied,
then restores its original style. Node feedback regression and seven bounded
search checks pass. Real IAB component geometry check passed: before and after
114.52611541748048 px, title Prompt copied, visible text Copied. This is browser
render evidence, not native physical capture. Seven scope capability checks pass.

Removed the disproved exact-title wrapper normalization; all playback ancestry
matching is strict again. Failure diagnostics can now retain only an unexpected
Group's bounded name after the existing Safe privacy check, so unknown wrappers
can be diagnosed without another blind name hypothesis. Actual wrapper identity
and physical Product capture/replay remain unresolved. Only isolated local
candidate/helper refreshed. Package remains stale; installed helper untouched.

## Product Copy 22 captured successfully

User physically saved Product copy 22, d0316ddd-60e8-460b-be13-4e0ed7162a87,
without interruption on the pointed-control candidate. Exactly focus_window then
invoke, Button/copyPrompt/Copy prompt; selected Edge now has 2 more pages. File
SHA256 16a789e21f2d245a865a5df20ba4ba727318e99793f2b12e25e2cc27765db8e4.
Diagnostics used focused_semantic_click, so this does not physically exercise the
new pointer descendant path. Its capture scope again has six ancestors; the
unexpected seventh Group is absent during capture. Do not claim the fresh capture
identified that Group. Current failure diagnostics now retain its bounded Safe
name, so the next normal replay can provide the missing identity without another
speculative normalization. Evidence: verified-product-copy-22-capture. Replay and
post-play exact paste pending; original Product Copy 21 also remains unchanged.

## Product Copy 22 replay: excluded host label; stable scope policy

Run 979dc6a7-b7e2-49f7-9aeb-ae900c2d1953 stopped 1/2 before Invoke, pending=null,
no_effect=true. One exact visible/enabled/ready button matched. The sole extra
anonymous Group at the known host boundary has unexpected_group_name=[excluded]
(the diagnostic's length/privacy guard), not a stable permitted identity. No
excluded label contents are retained. Evidence: product-copy-22-excluded-host.

Known Product Copy now treats exactly one empty-ID Group immediately outside
its validated iframe Document as optional host layout. It does not read that
Group's Name. The first three iframe anchors, all subsequent root/page/pane
anchors, target Button name/ID, same-process ancestry, exact native window/app,
and uniqueness remain enforced. A Group with an ID, another named extra group,
a changed iframe/page or a protected/disabled host remains blocked. Other
applications/actions keep strict original scope matching. Capture uses the same
host rule, so it never collects an excluded host label to save a future task.
No stored task/revision or schema was edited.

Native build and 17 focused actual-capture identity/privacy checks pass, including
a host name getter that throws if read, guarded host rejection, misplaced and
identified group rejection, exact documents, optional host disappearance and
bounded traversal. No UI/input was synthesized. Actual saved Product Copy 22
revision/file hash remain unchanged. Only isolated local helper/candidate loaded;
physical playback and exact post-play clipboard paste remain pending. Package
still stale; installed helper and production untouched.

## Product Copy 22 physical replay and exact clipboard verified

User reports Completed 2/2 and post-play paste Exact Match. Durable run
91e34d0c-cecb-4c48-abd2-34ee299417fb completed both steps with verified results,
pending=null and result_received=true. Saved revision remains
0ab0a882c40071a537d52eebd713d8b06a28a62a446aacc9d23aa2a34c19b944;
file SHA256 remains 16a789e21f2d245a865a5df20ba4ba727318e99793f2b12e25e2cc27765db8e4.
The clipboard was reset before playback. The subsequent physical paste (without
clicking Copy again) matches the actual component prompt: 124271 UTF-8 bytes,
SHA256 bd3e458f32ce5efcbd2ee2f96d0541580bb068e8e0ec4abb0e644c012730c3e3.
Evidence: native-ui-trial/verified-product-copy-22-playback in the task runtime.
Candidate SHA256 cb5675950ce8823bbcfcf07d31f63425a95b94b2b0c1c809560ad8173259a78a.
This passes the embedded Copy path only; Generate recorder playback and actual
Product page scrolling remain unverified. No release action performed.

## Final Copy candidate: disposable package lifecycle and panel result correction

Fresh setup found a real Windows path-length failure inside Playwright's deep
package tree. Failed preparations remained inactive and were retained. New
release directory keys are 20 hex characters; ready.json still verifies the full
64-character SHA256 manifest. Existing 64-character release keys are supported
by both release validation and the stable launcher. No global Windows setting
was changed. Focused package, desktop playback journal and foundation checks
passed (32 tests, 6 subtests); package checks passed again after the final fix.

A real disposable venv installed the pinned dependency closure and Playwright
browser, passed isolated integrity/import/adapter initialization, and started
the actual packaged helper on loopback port 18983. Two separate prepared code
directories were selected in sequence and rolled back; all three helper starts
published desktop capture/playback capabilities and the retained Combined 21
definition. The helper was shut down after each check. Saved definition and
synthetic draft/receipt/settings/profile retention canaries remained byte-identical.
These canaries are not acceptance of installed operational data migration.
Evidence: package-copy22-verified/startup-update-rollback.json in task runtime.
No installed helper, startup entry or shortcut was touched.

Panel review found a selected older task incorrectly showing the latest run's
Completed status. Terminal status now uses the selected recording's own result
when it differs from the latest run; active/interrupted safety messages remain.
Focused transport checks and actual local panel observation pass: Product copy 21
Stopped, Product copy 22 Completed. Screenshot is preserved with the verified
Product Copy 22 playback evidence. No native rebuild was needed.

A 20.03-second native idle sample outside inspection observed 0 processor seconds,
private memory 101949440 bytes unchanged and working set 103813120 bytes unchanged.
This is one idle sample, not recording/playback performance acceptance.
Evidence: native-ui-trial/idle-performance-copy22.json.

Final deterministic package and real-venv extracted health results are recorded
in package-copy22-verified/final-verification.json. Native candidate remains the
physically verified Copy binary. Remaining work includes Generate native result
verification, final provider/overflow/moved-window/DPI/inflight-disconnect trials,
record/play performance and bounded final save latency, installed setup/update/
rollback acceptance and Studio integration/release review. Development stays local.

## Pending wait disconnect and actual helper recovery

User started the existing wait-only Safety stop check physically and reports
closed. The candidate process was verified by executable path, helper parent PID
and --candidate command before termination during run
9df70c6a-8987-42ef-b879-537cad279956, pending step 0. It contains only wait_ready,
no application mutation. Durable journal retained uncertain/pending=0, no result
and no verified steps. All seven pre-existing top-level JSON files stayed unchanged (six saved tasks
and one retained draft checkpoint).
Actual helper restart recovered without opening native UI or dispatching an action;
a repeated Play preflight is blocked by the uncertain prior action.

The live disconnect exposed a status defect: a pending journal without a message
projected as running. read_native now durably stops with the disconnect reason,
so its state projects as interrupted. Eight focused adapter checks pass, including
EOF while a text action is dispatched, interrupted projection, unchanged task,
restart without instruction and blocked repeat. That text action test sends no
input and is not physical mutation/disconnect acceptance. The physical disconnect
was not repeated solely to retest the status fix.

The real panel showed the recovered task Needs review. Its normal Stop recovery
acknowledgement cleared the relay review fence with an applied durable receipt,
while the original uncertain journal remained unchanged in disposition. No action
was replayed or counted complete. Evidence: native-ui-trial/verified-inflight-disconnect.
Final package rebuilt deterministically and passed extracted health in the real
disposable venv: package-copy22-verified/recovery-verification.json. The earlier
final package is superseded. Native executable is unchanged. Installed helper
and production remain untouched; broader remaining acceptance is still open.

The recovered task warning also takes precedence over a generic Stop message,
so acknowledgement never visually clears the uncertain task outcome. Transport
regression and actual panel Needs review observation pass. Latest archive is
SportsCaveTaskRecorder-current.zip with current-verification.json: only panel.js
and its manifest differ from the actual-venv health-checked recovery package.
Python and native bytes are identical.

Next physical check is prepared through the real panel: Controls 21 after refreshing
the existing controls page and moving the Edge window (or existing second monitor).
User Start playback remains required. Native process-only CPU/private/working-set
sampler is waiting for that task's next durable run, up to four minutes; it sends
no input and performs no accessibility inspection. Session 66554. Evidence root
native-ui-trial/moved-controls-performance. Do not claim the move/performance
trial passed until the journal, actual user outcomes and sample are checked.

## Moved-monitor Controls 21 attempt: window preparation failed

User reports stopped 0/4 on a different monitor. Run
aac6ab7d-0366-4595-b7d5-bfd6e0a1831e stopped before focus_window completed,
verified=false/no_effect=true, pending=null: Prepare the recorded window before
Play. Playback.Window requires exact visible title and executable identity and
does not check coordinates/DPI. Thus this is not evidence of a DPI failure or a
moved-window pass. No actual matching-window metadata was emitted by this path;
do not infer a tab-count change without user confirmation. Asked whether the
whole window or the controls tab was moved. Evidence retained at
native-ui-trial/moved-controls-performance/failed-window-preparation.
The sampler captured 40 seconds spanning the failed lookup and subsequent idle
time; its stop condition did not group terminal-state alternatives correctly.
That sample is not active playback performance acceptance. Saved Controls 21
is unchanged. Future sampler conditions must group the terminal-state check.

User confirms moving the whole Edge window, not detaching a tab. Opened the
normal unarmed recorder through the real panel; requested Refresh windows and
the exact controls-page dropdown entry. No new capture/playback requested until
the missing identity match is understood. No native inspection/input probe used.

## Controls lookup cause confirmed: Edge tab count decoration

User read the native window dropdown: Recorder controls acceptance and 3 more
pages - Personal - Microsoft Edge. Recorded Controls 21 window says 2 more pages.
The user confirms moving the whole window. The changed tab count explains the
exact-title miss; no saved definition was edited.

Playback now tolerates only supported English Edge tab-count decoration changes
(0 extra tabs/no decoration, singular 1 more page, bounded plural counts), retaining
exact page title, profile/vendor decoration, executable path, process safety and
unique-window checks. A changed title additionally requires exactly one visible,
enabled, nonprotected UIA Document/RootWebArea with that exact page name, in the
window process with bounded same-process ancestry reaching its native root and
no enclosing Document. A matching iframe cannot identify the browser page.
Other applications and unsupported title decoration keep exact matching.
No raw input/coordinates or RootWebArea-as-editor fallback was introduced.

Native build and 18 focused identity checks passed, including absent/wrong document,
wrong page/profile/application, singular and no-extra-tab variants, malformed counts
and unchanged exact-title behavior. Current candidate SHA256
3c24fd08f5fb1704f663c4fbefda593833d645803f402c079ad98ebfd29e50bf.
Only this task's identity-checked unarmed native process was closed/replaced.
Helper storage and installed helper were untouched. The current package built
deterministically and passed extracted integrity/import/adapter health in the
real disposable venv. Evidence: package-edge-tab-identity/verification.json.

Controls 21 was queued through the real panel; user physical Start remains required.
Requested refresh/reset while retaining current three other tabs and the second
monitor. Process-only sampling uses corrected grouped terminal conditions; session
58107. Pending evidence: native-ui-trial/moved-controls-performance/tab-count-fix.
Do not claim this revised native path physically passed until journal, document
identity diagnostic and user-observed control outcomes are checked. Previous
Copy physical acceptance describes the preceding native candidate.

## Changed-tab-count Controls 21 replay completed on second monitor

User reports Completed 4/4. Run 91a1c6aa-0e3c-40c1-bdc3-d0787e3d9ba8
completed all four steps with native readback verified, pending=null. Each step
emitted playback_edge_document_identity: tab_count_changed=true, independent
top_level_document_verified=true, DPI 134, two monitors. User had confirmed moving
the whole Edge window to the other monitor. This passes changed-tab-count
playback on that monitor; differing DPI between the two monitors was not measured.
User explicitly reported completion only; native readback verified control states.
Saved revision 09e5e75e6d103c70d4434506e3b357c80a898aa83cfbde7df5096af3843d069a
and file SHA256 41fe2aa97e707d70fd3d183f96b86ca2ca51e2c08fe00625912c529c09f350d9
are unchanged. Evidence: native-ui-trial/moved-controls-performance/tab-count-fix.
The sampler timed out before the user started this run; no active playback
performance result is claimed. Do not repeat a passed physical trial only for
that missed sampler. Current native remains 3c24fd08f5fb1704f663c4fbefda593833d645803f402c079ad98ebfd29e50bf.

## Native provider/queue fault injection, capacity bound and local metrics

Review found outbound queue overflow merely set Armed=false and could lose the
interruption message while leaving the helper recording. It now marks capture
Broken/disarmed, cancels playback and exits only the candidate (exit 78); the
existing EOF handling preserves/interrupts the acknowledged draft or pending
journal. Queued capture work is skipped after Broken rather than inspecting
stale targets. The actual Capture worker was fault-injected without hooks or
desktop inspection: bounded queue overflow, no queued work after interruption,
provider ElementNotAvailable and stall watchdog. An unconstructed Host Send path
with a real full outbound queue exited its isolated child at 78 with capture
broken/disarmed. Six focused checks pass. These are native-code fault injection,
not physical UI-provider acceptance. Test source: NativeFailureChecks.cs.

Native recording/playback operations now emit local process-only diagnostics
(native_operation_metrics), with elapsed/CPU milliseconds and private/working-set
endpoints. They collect no app values or desktop inspection. Recording timing
includes the Stop/Pause flush barrier; it excludes Save. Repeated Detach/Disarm
cannot duplicate a metric. These are measurements, not pass/fail result signals.

A disposable Python coordinator/disk capacity check saved 500 actions with 1500
characters each: 948968-byte saved file, repository Save 89.77 ms, full Save command
152.92 ms. Overflow stayed interrupted, required review before Save, and recovered
all 500 actions; saved definition unchanged. A separate larger-text draft hit the
1 MB serialized-task bound at 441 actions and recovered interrupted. Evidence:
capacity-save-500/verification.json plus capacity-save-check. This is an observed
local bound test, not a universal latency guarantee or physical/native recording.

Current native is 54bf7f8636c7a27523f5facca85e3c0dbcaf3497dd6aafc885228d8ddfd7c594.
Only this task's stopped, identity-checked candidate was replaced. Current archive
package-native-failure-metrics/SportsCaveTaskRecorder.zip rebuilt identically and
passed real disposable-venv extracted health. Installed helper untouched. The
54bf candidate is open unarmed. Requested one synthetic Product Copy capture
as Final Copy 21 to collect real recording/save timing and then validate normal
playback after the queue fix. No automatic playback is armed. Await user result;
prior Controls second-monitor acceptance belongs to the preceding 3c24 candidate.

The initial browser Record activations did not reach the helper (no receipt or
native process); this was not a native crash. A browser accessibility activation
finally produced applied receipt fc88c2d8-7ad5-4403-a2c5-99e11a58031a and native
PID 276 owned by helper 7608, using the 54bf candidate. The normal unarmed toolbar
is now confirmed available. User is on the synthetic Product Uploads page and
was asked to capture one Copy click as Final Copy 21, then stop/save only.
No playback is queued. Use browser accessibility activation for the panel's
Record button when its iframe/scroll position prevents Playwright activation;
verify a durable receipt and actual owned process before asking for a trial.

## Final Copy 21 physical capture and operation metrics

User reports All good saved success. Inspected task
01680f50-9f5e-4475-90bb-735ef18a59c7 contains exactly focus_window then
Button/copyPrompt/Copy prompt invoke. No run existed before explicit Play.
Revision 4ddcf1dcd399c6c7f5d285ead8c7c70863a33621d923a7546fd859c5d585bf23;
file SHA256 54da8f4b19205858516babd07c48c9ada33fc430f9fe8d29da4b89f260bf5014.
Completed native Save receipt f8dd1380-0d0f-4d53-a027-d8fa29a9e12d records 2.49 ms.
Native recording metrics: elapsed 4799.99 ms, CPU 203.12 ms, private bytes
135766016 -> 125128704, working set 105824256 -> 106700800. This includes normal
capture/flush and no inspection. A separate final-candidate idle sample over
20.08 seconds observed 0 processor seconds, private bytes 95031296 -> 95105024,
working set 93540352 -> 93556736. These are bounded observations, not memory-leak
or sustained-load acceptance. Evidence: native-ui-trial/verified-final-copy-capture.
The six previously saved tasks remain unchanged; the earlier disconnect count
of seven included draft.json, now corrected in its metadata.

Selected and queued Final Copy 21 through real panel accessibility controls.
User asked to reset clipboard to Recorder final reset, Start playback once, then
after Completed 2/2 paste into synthetic clipboard check and Verify without
clicking Copy again. Native operation diagnostics now persist playback timing,
so there is no expiring external sampler. Await outcome; do not claim replay or
post-play exact clipboard acceptance yet. No installed helper or production change.
