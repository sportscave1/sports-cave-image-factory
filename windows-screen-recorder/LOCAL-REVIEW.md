# Windows Recorder V1 local review — 21 October 2026

This is a reviewable local checkpoint, not a completed or authorized release.
The checkpoint was committed locally as `148a1a4d3731167f7705cab2fc2b3d36f649f79a`.
Exact-revision Studio Verify, 63 Python checks (plus six subtests) and both focused
JavaScript checks passed on the clean committed worktree. Subsequent Generate
and shutdown fixes are described below; Studio records their exact follow-up
revision and verification independently of this historical checkpoint.
Task `20261020-ff6cc91d`, owner `codex-windows-recorder-release-01a1589a`.
The user authorized a recorder-only local commit and exact-revision Studio
checks, followed by continued work. Push, merge, Render deployment and installed
helper replacement remain unauthorized. Original owner experiments and production
Photoshop/Edition Ops jobs/settings were not changed.

## Verified behavior

| Check | Evidence |
|---|---|
| Combined Edge/Notepad | Physical capture, save, restart, reset and 4/4 playback; actual text confirmed; immutable definition retained. |
| Scroll | Physical capture and 27/27 playback; sample returned to top. |
| Checkbox, selection and menu | Physical 4/4 playback with semantic readback; repeated on second monitor after an Edge tab-count change. |
| Safety | Physical Emergency Stop, Pause/Resume, manual intervention and protected-field exclusion. In-flight disconnect retained an uncertain journal and blocked automatic replay after restart. |
| Actual Product Uploads | Generate and readiness exercised using synthetic providers; 5/8 ready correctly kept Save All disabled. Embedded Copy captured and replayed physically, followed by exact clipboard paste verification. |
| Faults and capacity | Six native-code provider/queue failure checks passed without desktop inspection/input. Disposable 500-action Save completed in 152.92 ms; overflow interrupted and recovered. |
| Compatibility | 28 focused relay, transport, desktop-adapter and capability tests passed. Five package tests passed, including actual generated launcher release-ID validation. |
| Packaging | Deterministic ZIP, manifest/extracted integrity and isolated health passed with a real disposable pinned environment. Actual disposable helper startup, update selection and rollback retained data. Generated Rollback.ps1 selected a previous compact release; its final launch was intercepted for that separate entrypoint check. |

The final physical Copy run is `2b54da5a-8a82-45dd-8731-47ebb09e30da`, task
`01680f50-9f5e-4475-90bb-735ef18a59c7`: completed 2/2, both results verified,
no pending step. User reset the clipboard before Play, then pasted and verified
without clicking Copy again. Exact UTF-8 payload: 124265 bytes, SHA-256
`1e3c47b324fa5bafcff0a01c23245a84f7a4b42d0d67876b0bc5e5feb646d9d6`.
Saved revision `4ddcf1dcd399c6c7f5d285ead8c7c70863a33621d923a7546fd859c5d585bf23`
and file SHA-256 `54da8f4b19205858516babd07c48c9ada33fc430f9fe8d29da4b89f260bf5014`
remain unchanged. Evidence is under the Studio runtime:
`native-ui-trial/verified-final-copy-playback/` and `verified-final-copy-capture/`.
Recordings, clipboard payloads and recovery archives are excluded from Git.

## Measurements and build distinction

The physically accepted native build is
`54bf7f8636c7a27523f5facca85e3c0dbcaf3497dd6aafc885228d8ddfd7c594`.
Final capture: 4799.99 ms elapsed / 203.12 ms CPU; native Save receipt: 2.49 ms.
Playback: 326 ms elapsed / 156.25 ms CPU. Idle: 20.08 seconds / zero observed CPU.
Playback private bytes: 110665728 to 111112192; working set: 111816704 to 113057792.
These bounded measurements were outside inspection; they do not establish
sustained-load or memory-leak acceptance. Second-monitor diagnostics reported
DPI 134 and two monitors; differing DPI between monitors was not measured.

Final review aligned generic playback control/ancestor PID checks with capture's
existing same-process rule. Product Copy already enforced this rule. That source
built and passed the six native fault checks, but the new generic-control guard
has not had physical acceptance. Its native SHA-256 is
`930517a932e42939776de894bfb4a07eed9f93370d9b35b2d0a987e659bbae52`.
The running development toolbar retains the physically accepted build.

Review archive: `final-review-package/SportsCaveTaskRecorder.zip` in the Studio
runtime. Archive SHA-256:
`79850e3c49a20751d4f94681d8df82981d7b5d8a913f90f59ca6555371e37047`.
Manifest SHA-256:
`eefdfd0fa67118adede6fc7cb7e66f629e3e2950550f3b12cda6bb2b225bfadd`.
It includes the reviewed native build, 52 files, and no user data. It rebuilt
identically and passed extracted health. Documentation is outside the archive.

## Integration review and remaining gates

Read-only fetch identified current `origin/main` as
`af9de46d5744c07196a2c575da74c0580b8d96d3`. The recorder/package/component files
had no intervening changes on main since the merge base. Shared `app.py`,
`sports_cave_server.py` and Product Uploads generation UI match this task's
baseline. A full two-tree diff also contains other tasks' newer main changes;
those are not recorder removals and must not be reverted during integration.
Use a recorder-scoped integration review, preserving current main's other work.
No Render topology or installed Companion change belongs to this release.

Current production relay does not accept `desktop_capabilities`; ship compatible
relay handling before updating the helper. Hosted package delivery needs the
exact reviewed Windows artifact configured on the existing primary service.
Neither production change has been made.

General invoke runs once and stops as uncertain without an application-specific
postcondition. Product Copy and Generate now have narrow result verifiers. The pointer-based
semantic descendant fallback and actual Product Uploads scrolling lack physical
acceptance. Mixed-DPI behavior, installed first setup/startup/update/rollback and
the final integrated candidate still need acceptance. These gaps are not passes.

Studio requires a clean committed revision and current exact-revision evidence
for review readiness. The user has now explicitly authorized the local recorder
commit and exact-revision checks. Keep the task In Progress until the
applicable gates are complete. Local preparation and an archive do not authorize
deployment, installation or a claim that the recorder is fully released.

## Continuation after the authorized local commit

Product Uploads now emits a public generation acknowledgement for each accepted
Generate request. Ready requires the current intake/name/sport/source, matching
job and applied result; stale, failed and changed-context results cannot satisfy
it. The opaque per-attempt identity is an HTML ID, not visible/spoken content or
a value saved in recordings. A scoped optional native result contract requires a
fresh acknowledgement before confirming Generate playback. It waits within the
recorded 30-second action bound, never repeats Generate, and preserves unknown
effects. Result-only observation tolerates the application's scroll to previews;
the mutation still requires a visible, enabled target.

The first physical Generate attempt on native `57e831f4...` interrupted with zero
actions. The user confirmed clicking Generate directly. Diagnostics exposed only
RootWebArea and no semantic control under the pointer. Evidence is retained in
`generate-acceptance/failed-editor-click/`; no successful capture is claimed.

The revised candidate prepares the unique visible Generate control and its
document before arming. Its mouse-down worker must confirm the same enabled,
nonprotected control, point, window, process, DPI and bounds before release.
Mouse-up must stay in the same window/control bounds and within two seconds;
capture emits Invoke only after a fresh working/ready application acknowledgement
in that same top-level document. If any proof is unavailable it interrupts.
These are physical input observations, not injected input or coordinate playback.
The first pre-click native `51dbcdea0239f64697092277c5c79a7ae85786a8db8ff739da57c4da5440b2c3`
compiled and passed 13 fresh-acknowledgement policy checks. Physical acceptance
is pending. Seven previously saved definitions remained unchanged across restart.

Focused Python checks passed for acknowledgement/context rejection and scoped
contracts (18 tests plus six subtests), and the existing Generate callback/loading
checks passed (six tests). Actual UI generation with synthetic providers showed
working then ready, five generated core images and Save all disabled at 5/8.
This browser-driven check is not physical native acceptance.

The synthetic reset control was initially covered by the fixed page header.
It has moved into the test sidebar. The refreshed fixture uses port 18976 and
intake `b1d9c43d-d557-4367-8f21-b632a4ad48f3`; the previous fixture's files remain
under `generate-acceptance/product-ui/`. No real workflow or source was reset.

Independent shutdown review found base Runner.close could call DesktopRunner.stop
and reopen the native toolbar when a draft was interrupted. Closing now blocks
reopening, bounds native/pump cleanup and closes stdin even after a broken pipe.
Readers retain their own process and cannot consume or interrupt a replacement
toolbar. Ten desktop-adapter checks pass, including broken-pipe shutdown with
draft retention and a stale reader not touching a replacement. The running helper
now loads this cleanup fix after an idle restart. Installation/deployment remain forbidden.

The preparation attempt on 51db rejected the acknowledgement's process/protection
check before capture. The subsequent build distinguishes process mismatch,
protected state and unavailable document classification. Unknown layout-container
classification now follows capture's existing metadata-only rule; protected
controls and unknown Document/Edit classification still block. Current native
`fc05b2422df3c0c460d1ef4cf70d6b4818a14902a5f2ad53b985daee658eee8c`
passed physical Generate capture on the corrected sidebar fixture. Generate 21
contains exactly focus and scoped Invoke, with revision
`7c218dbf40bf14258229b0cc0db584a46296527b2ef33196546637f6cfd64e6d`.
The durable Save receipt reports 2.53 ms. All eight saved definitions retained
their exact bytes across the subsequent development-helper restart.

One physical playback completed 2/2 and the user confirmed reset had removed the
previews beforehand. Fresh generation remains unresolved: the synthetic provider
counter did not advance, including after an independent browser-driven Generate.
The archive named `verified-reuse-playback` records the initial reuse inference;
that name is not proof of result reuse. A subsequent fresh-tab physical playback
stopped 1/2 before Invoke with "Recorded control is not ready." The user confirmed
Generate was visible and enabled. Its run, diagnostics and unchanged definition
are preserved under `generate-acceptance/fresh-tab-resolution-failure`.

Failure diagnostics previously sampled unrelated controls with an empty
AutomationId. The next diagnostic candidate filters by saved name and type,
reports Edge document identity once per step, and records whether result
verification observed a fresh working state. It changes no target matching or
input guard. Native SHA-256:
`113df98a6e8b3a7081a596ad8174e7d63bc30428e1d6573ff198373ee107bc17`.
It compiles and is queued for a user-started diagnostic playback. Twelve focused
acknowledgement and helper-lifecycle checks pass. Fresh Generate replay and final
candidate acceptance remain open; no installation or deployment occurred.

The diagnostic retry found exactly one visible, enabled, same-process Generate
button. Its three saved ancestors matched, but Streamlit exposed an additional
content-named Group inside root. Generate's application-specific scope now allows
one anonymous, enabled, nonprotected layout Group at that boundary without reading
its content-derived name. All three stable ancestors still compare exactly;
the result acknowledgement must independently belong to the same top-level
document. Other actions retain their existing scope policy. Capture canonicalizes
this same boundary. Twenty-two native policy checks include wrong document/pane,
identified or multiple named groups, unsafe host and missing ancestry rejection.

Physical playback on native
`c7399e7ff115cdf979d753814c14b46bb69fa958745830f1ab3e75e3b4ecfe8b`
completed 2/2, confirmed by the user and durable run
`eb2fc8ac-0eac-401e-88f3-4f9574534b04`. The verifier observed a fresh working state
then a fresh applied ready acknowledgement; no pending step remains and Generate
21's bytes are unchanged. Playback took 3047.98 ms / 781.25 ms CPU; private bytes
96174080 to 100995072. A subsequent 10.04-second idle sample outside accessibility
inspection observed zero CPU and stable private bytes 102395904. The provider
counter still reports one call and is not used as an independent freshness oracle.
Source remains unchanged; no exports or output-provider calls occurred.
Evidence: `generate-acceptance/verified-fresh-playback` in the Studio runtime.

The corresponding local package is
`generate-acceptance/layout-scope-package/SportsCaveTaskRecorder.zip`, SHA-256
`e1ba83c7dab9acfaceea262a90bd83b83e21ab072a3dbe2c41c2056101ea11f3`,
manifest `ca10e118a485854ee77161ca297b0c273e2b5e02968d4f9ad5430761ae291d2e`.
Deterministic rebuild, extracted integrity and health in the real disposable
pinned environment pass. Six native provider/overflow checks, twelve focused
acknowledgement/helper checks and twenty-seven job/contract/package checks
(plus six subtests) pass. The package was not installed or published.
