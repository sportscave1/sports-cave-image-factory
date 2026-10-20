# Task Recorder playback release — 20 October 2026

User explicitly authorized GitHub/Render deployment and Windows helper update.
Release task 20261020-117ee561, owner codex-recorder-playback-release-01a15872.
Based on verified production 276df0e6a8ef34f47619288e7a9984f610b9234f.

Only playback capture, frame schema, prerequisite/target warnings, progress and
terminal ownership fixes are included. The earlier editor is already deployed.
Unfinished performance work stays unchanged in task 20261019-64cdf0b0: no compact
level 2, catalogue patches, polling jitter or keyed-row changes are included.
Runner notifications accompany playback progress, with no transport changes.

Release checkout: 50 focused pytest checks and 14 subtests passed, four Node
control/editor/transport suites passed, topology validation passed. Full isolated
OS/auth/relay/PC approval Record/Stop-save/helper restart/app reload/one Play passed
at LocalAppData/SportsCaveOS/TaskRecorderPlayback-64cdf0b0/play-6657bc80.
It restored the synthetic PSD binding, fields, delayed frame interaction and exact
clipboard text. This fixture invokes no production Product Uploads job.

Existing canonical Render services auto-deploy from main. No service creation,
Blueprint sync, configuration changes, provider operations or new migrations.
Update the Task Recorder Windows helper with its existing installer only after
saving the paused-run evidence and issuing Stop. Preserve recordings, private
bindings, pairing and profile. Do not replace any other Windows companion.

The incomplete old recording still requires missing source/actions to be recorded;
this release cannot reconstruct absent PSD/button identity. See
TASK_RECORDER_PLAYBACK_LOCAL.md for investigation and limitations. Its local-only
footer describes the implementation phase, not this separately authorized release.

Live commit/deploy IDs, installed hashes, preservation checks and final helper
state are recorded outside Git in LocalAppData/SportsCaveOS/TaskRecorderPlaybackRelease-117ee561.
