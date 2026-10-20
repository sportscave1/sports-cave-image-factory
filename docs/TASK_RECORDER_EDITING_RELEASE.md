# Task Recorder editor release — 20 October 2026

User authorised GitHub/Render publication after local implementation. This
release is isolated in Studio task `20261020-e9687db6`, owner
`codex-recorder-edit-release-20261020`, based on production `5504669b01fc691fb15dd6704ca34463901c24f2`.

Only recording editing, helper protocol 4, its existing authenticated relay
controls, focused tests and the isolated preview harness are included. The
unfinished measured-performance phase stays byte-for-byte in task
`20261019-64cdf0b0`; task summary patches, compact level 2, keyed row rendering,
new polling jitter and engine notification changes are excluded from this release.
No topology, worker, Photoshop, Edition Ops, provider or migration changes.

The editor supports value changes, PC file references, selected deletion/Undo,
range trimming, reviewed replacement recording and inserted readiness checks.
Save creates an independent revision-fenced copy, not yet run, preserving source
bytes/metadata and recording duration provenance. Existing protocol 3 playback
continues during rollout; Edit explains that helper 4 is needed.

Release-candidate verification: 24 focused pytest checks pass (the 30-check local
implementation run included six unreleased performance checks); Node editor and
existing playback controls pass. Full OS/account auth/relay/PC approval/visible
Windows runner trial passed from this release worktree at:
`C:\Users\hello\AppData\Local\SportsCaveOS\TaskRecorderEditing-64cdf0b0\edit-ae833193`.
It recorded, edited text/URL/select/check/file, trimmed, deleted/undid, recorded and
reviewed a replacement, inserted text/URL waits, corrected an invalid URL,
saved/refreshed and actually played the copy with one synthetic local submission.
Original JSON/metadata and installed helper source remained unchanged. Syntax,
Studio checks and Render topology validation pass.

Normal deployment uses the existing main-branch automatic deploys. No Blueprint
sync or service creation is required. Monitor canonical `sports-cave-os`
`srv-d8kl4on7f7vs73dvavv0` through live status and verify the authenticated page,
new downloadable setup and PC helper connection before reporting Live. The helper
must be updated only while idle through its existing installer, preserving
TaskRecorderV1 data/profile/pairing. Runtime release evidence belongs outside Git
at `AppData/Local/SportsCaveOS/TaskRecorderEditorRelease-e9687db6`.

The prior local report `TASK_RECORDER_EDITING_LOCAL.md` is retained as the
implementation and limitation record; its local-only status describes that
completed stage, not a deployment result. Replacement fragments remain separate
saved recordings; unsaved drafts are page-local. There are no optional delay
steps in V1 and no new timing multiplier.
