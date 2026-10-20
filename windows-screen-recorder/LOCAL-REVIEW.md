# Windows Recorder V1 local review — 21 October 2026

This is a reviewable local checkpoint, not a completed or authorized release.
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
postcondition. Product Copy has one; Generate replay does not. The pointer-based
semantic descendant fallback and actual Product Uploads scrolling lack physical
acceptance. Mixed-DPI behavior, installed first setup/startup/update/rollback and
the final integrated candidate still need acceptance. These gaps are not passes.

Studio requires a clean committed revision and current exact-revision evidence
for review readiness. The user has now explicitly authorized the local recorder
commit and exact-revision checks. Keep the task In Progress until the
applicable gates are complete. Local preparation and an archive do not authorize
deployment, installation or a claim that the recorder is fully released.
