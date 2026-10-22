# Task Recorder checkpoint — 22 October 2026

The original seven-phase plan remains unfinished. No phase is fully accepted on the latest integrated build. All automated desktop input evidence is development-injected; physical input acceptance remains separate.

| Plan area | Completed or evidenced today | Still required |
|---|---|---|
| 1. Integrated baseline | Current helper/native identities aligned; version checks, acknowledged commands/deadlines, duplicate-command protection and paged library implemented. Build 11 restart preserved 46 recording/revision files and remained idle. Direct OS panel command acknowledged; toolbar and panel agreed. | Embedded OS recorder panel is blank. Finish embedded connection/state/reconnection acceptance. |
| 2. Toolbar and capture | Record, Pause/Resume, Stop, Save and indicators implemented. Control-only lifecycle saved zero actions without playback on build 11. | Full ordered action capture, indicator/display scaling and physical-input regression on the final build. |
| 3. Actual OS/browser controls | Build 10 first-navigation replay passed 2/2 and saved tab/control workflow passed 7/7 after restart. Build 7 actual OS dropdown/navigation passed 4/4; missing and duplicate destinations stopped safely. Official ChatGPT Edge extension now connects and permits interaction with the existing preview. | Regress these workflows on build 11; finish embedded/dialog control coverage. |
| 4. Product Uploads | Full clipboard independently matched 126,148 UTF-16 units / 126,312 UTF-8 bytes on build 10. Generate capture failure diagnosed; preflight-cache fix compiled in build 11. | Build 10 capture failed despite successful clipboard copying. Fresh build 11 Generate → readiness → Copy → Save → restart → replay is unaccepted. Repeat with slow generation and wrong product/PSD rejection. Live 80,790-character case remains unverified. |
| 5. Transfer | Versioned dynamic Copy/Paste, current-run value checks, Unicode handling, legacy fixed text and stale clipboard rejection implemented; earlier isolated evidence preserved. | Integrated transfer regression. Edge download native host is not found. Complete download/cancel/duplicate-file tests and implement supported Save As. |
| 6. Desktop workflow | Targeting, Stop/emergency hotkey and interruption handling implemented in parts. | Full OS → native document → existing browser → OS workflow with independent destination/file checks, moved windows, minimise/restore, missing targets and interruption. |
| 7. Release | Isolated candidate and preservation/rollback mechanisms exist. | A fully tested compatible package, production-origin adapter support, installation and post-install acceptance. Current adapter is local-preview-only. |

Additional agreed follow-up: readable saved action/failure review, immutable repair/re-record revisions and a second harmless reusable OS workflow remain unfinished.

## Exact candidate and validation

- Native build 11 SHA-256: `c3917e5edc6cb82c619f8c4f680be068eef3b66e286893b25d5362fc08d3410d`.
- Helper identity: `47592791ec533fb4f2a7ca314157caf207d7b2044ae7b53d3f9933c41b61fdd1`.
- Adapter: `0.3.1`; IPC: `2`; action versions: `2,3`.
- Fresh source regression: `python -m pytest tests -q` from `integrated-20261022`: **78 passed, 36 subtests passed**. An initial invocation from the parent directory failed collection by importing the wrong package; running from the candidate directory resolved it.
- Latest panel draft-count fix passes syntax validation but has not passed visual regression.
- At this checkpoint no `DesktopRecorder.exe` process was found. Prior acceptance identities above describe the tested candidate, not a currently running native process.
- Installed helper selector remains `72d074f248996f7df51c`.

## Preservation and release decision

User explicitly authorised a Git/Render/Windows release in this turn. Release remains technically blocked by the failures above and the original plan's acceptance gates. No production deployment or installed-helper replacement is claimed. The Photoshop/Edition Ops companion is outside this recorder release scope.

Preserve source, recordings, revisions, failed/uncertain runs, settings and diagnostics locally. The evening ZIP manifest identifies copied files and exclusions. SQLite command databases use SQLite backup rather than copying live database pages. Existing ZIPs, PSDs and dependency caches remain in place; they are not duplicated in this archive. Private recordings, authentication, diagnostics content, PSDs and binaries must not be pushed to Git.

A separate `codex/recorder-checkpoint-20261022` branch is intended only as a source backup. It is not merged to main and is not a live release. The shared checkout has 87 pre-existing tracked modifications in other areas; they must not be swept into this recorder checkpoint. Complete local preview source is preserved in the local archive; only selected recorder source is suitable for the source branch.

Render connector currently reports no workspace selected. Its supported recovery requires explicit workspace confirmation before Render operations. There is no reason to request that now while the release itself is blocked. Canonical primary service remains `sports-cave-os` / `srv-d8kl4on7f7vs73dvavv0`; do not create another primary service.

## Resume order and rollback

1. Launch the preserved isolated candidate, verify exact hashes and normal injected-input filtering; preserve prepared browser state.
2. Resolve the embedded panel and complete OS/toolbar acceptance. Reuse successful earlier tests without promoting them to build 11 acceptance.
3. Complete current-build browser regression, then Product Uploads capture/restart/replay, then transfer/download and full desktop workflow in dependency order.
4. Package and inspect a focused release only after gates pass. Confirm Render workspace, exact source commit and existing service; deploy and verify terminal live state. Install only the Task Recorder helper and verify recordings/rollback.

The installed helper was not changed, so installation rollback is unnecessary. To restore development source, stop only the owned idle candidate and extract the appropriate checkpoint into a separate directory first. Never overwrite newer recordings or authentication with older checkpoint data. Keep uncertain historical runs stopped and never relabel them successful.

Evidence directory: `.local-data/milestones-20261022`. Key files: `integrated-build11-restart-verification.json`, `integrated-library-audit.json`, `connected-lifecycle-proof.json`, `navigation-first-build10-passed.json`, `tab-build10-passed.json`, `tab-build7-missing-target.json`, `tab-build7-duplicate-target.json`, and the existing phase reports.
