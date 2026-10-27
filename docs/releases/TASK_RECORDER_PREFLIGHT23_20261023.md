# Task Recorder Preflight23 release — 23 October 2026

This release carries the accepted Windows recorder package and required OS integration. It retains strict browser profile/page/product matching and ambiguous-control rejection. The navigation fix withholds stale Product Uploads identity during a page transition. The OS exposes the exact Copy Black Frame Prompt control and preserves the account-owned prepared selection across navigation.

## Package and compatibility

- Download: `recorder-releases/windows/SportsCaveTaskRecorder.zip`.
- ZIP SHA256: `7e03d11c2b06aebd345feeed581fbbfa42f1a09cca375fcc4c4672c417fc6210`.
- Manifest ID: `e7c6831bc3e1fda003b45f009fce076916090b9231a45a9b8ef3a8d6763dc9a5`.
- Native SHA256: `ac312f0f3933911be7088182174b2b388ae3b46c7d92a2f16295f695b420a423`.
- Helper fingerprint: `36737096a2756d90f3b268492883a10e133cf7545febca0083a5d0a87cd448e1`.
- Edge adapter 0.3.4, protocol 1; browser identity SHA256 `4066aa20aa61e0d1b32d1302f7286a5c8710ab83e2a2ebc9059a7c025dc82c75`.
- Download host SHA256: `a2c74184ade29a8cd5f96782b76504ff0c2cef7d9e4169f1453ac59f6661c993`.
- Native IPC 2; desktop format 1; actions 2/3; relay protocol 4; package format 2.

The reviewed archive is authoritative. Do not substitute an ad-hoc build or the legacy format-1 package builder for this release. Its source and dependency hashes are carried in the archive manifest. Python 3.11+ Windows x64 and .NET Framework 4 are required; exact Python dependency pins are in the archive's `task_recorder/requirements-windows.txt`.

## Acceptance before publication

The accepted automated full workflow completed 21/21 steps, including the correct prompt copy and verified downloads. It was not repeated for release. Installed physical Record, move, Pause, excluded input, Resume, Stop and Save passed; standard-launcher restart was idle and replay verified 5/5 with the target resized and minimized. The physical move was matched by the Windows move event. Active local disconnect suspended capture and preserved its draft; reconnection returned idle. Physical download cancellation produced USER_CANCELED, no completed file or retained download action, and the partial draft was reviewed and saved. The installed native host's actual Edge routing and helper/adapter rollback were previously verified.

These checks cover the supported acceptance controls, not every Windows application or possible control. Private recordings, receipts, screenshots and diagnostic logs remain local and are excluded from Git. Existing definitions and journals were preserved; the superseded working draft remains in the private backup.

## Installation and rollback

1. Verify the ZIP hash, extract to a new directory, and preserve the old release and all recording data.
2. Stop/save any capture or playback through supported controls. Back up the helper, TaskRecorderV1 data, existing adapter directory and native-messaging registration.
3. Update only the existing Task Recorder adapter in its established profile/path, reload that adapter, and run `Install.ps1 -ExtensionId '<verified extension id>'` from the extracted package. Do not update the Photoshop/Edition Ops companion.
4. Verify the exact active package/runtime hashes, browser adapter, fresh download receipt routing, no autoplay and existing recording preservation. The acceptance PC already runs this exact package; no additional helper replacement is required for this OS release.
5. To roll back, stop/save and preserve newer recordings first, use the installed `Rollback.cmd`, restore the backed-up Task Recorder adapter bytes in the same path/profile, and verify host routing. Never restore an older data snapshot over newer recordings.

On the acceptance PC, command-side registry changes were not visible to interactive Edge. An interactive import of the prepared current-user native-host registration was required and verified with a fresh receipt. The corresponding interactive rollback import was also tested. A registry readback alone is insufficient evidence of host routing on that PC.

## Existing production target

Nathan's workspace `tea-cut91gtsvqrc73e5acs0`; existing `sports-cave-os` service `srv-d8kl4on7f7vs73dvavv0`; repository `sportscave1/sports-cave-image-factory`, branch `main`. No Blueprint or service topology changes.

Pre-release live deploy: `dep-dbcnfcjncjis73d1o87g`, commit `b78b78356cbc891dfd8b94aaec21d3082cad5642`. Preserve this Render build as the rollback reference. Render rollback does not reverse data changes; this release adds no database migration. Record the final release commit and deployment receipt separately after publication. Deployed acceptance is separate from local/installed acceptance and must be verified after the service reports live.
