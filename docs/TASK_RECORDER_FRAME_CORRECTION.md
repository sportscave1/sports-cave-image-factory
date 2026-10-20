# Task Recorder: passive frame navigation correction — 20 October 2026

## Exact affected recording and cause

The installed Windows task `9e211986-7433-4879-ba87-cdb458c59683`, “Open the OS app”,
was saved at 13:45:33 Sydney time with duration 21,503 ms. Its original SHA-256 is
`37ff309d76fca6a3fc2edf8e94b05597c4099eccb84d943f1fe9de5dc7e39559`.
The original file and metadata are preserved.

1. Navigate to `https://sports-cave-image-factory.onrender.com/`.
2. Navigate to `https://sports-cave-image-factory.onrender.com/?page=dashboard`.
3. Unsupported: “Frame navigation is unsupported; V1 records only the main frame.”

That exact reason is emitted only by the old Runner.navigated child-frame branch,
registered on Playwright's `framenavigated` event. It is not emitted by click capture
or interrupted-recording recovery. The original format did not retain the frame
identity; identifying the historical iframe retrospectively would be guessing.

An exact-source legacy-engine reproduction against the isolated full OS produced
the identical three-step sequence by opening the OS and waiting, without clicking.
Its frame trace shows `about:srcdoc` document loads, including an empty document
and “Sports Cave OS top bar”. The old rule marked every child navigation as an
unsupported action; adjacent identical flags were deduplicated. These embedded OS
rendering documents are not user interactions. This is a capture false positive,
not a lack of support for ordinary top-level navigation and not an interruption.

## Correction

Passive frame navigation no longer appends a workflow step. Init-script readiness
notifications enable recording in dynamically loaded documents after their
frame-local privacy check. Actual iframe input still produces an explicit flag;
authentication paths, password/credential fields and later sensitive field insertion
still pause capture. No frame interaction is silently treated as supported.

Unsupported browser events now use a fixed reason-code whitelist rather than
replacing every reason with a generic message. Arbitrary page-supplied reasons are
not retained. Validation reports the exact first flagged step and explanation.
Task summaries expose up to three bounded attention entries plus the total count;
old format V1 task files remain valid and original revisions remain unchanged.

The compact existing page shows Needs attention and a Review step control. It
shows the exact recorded reason and distinguishes interrupted recordings. A
correction can open a website or wait for unique visible text. Save corrected copy
uses the authenticated owner-scoped command transport, task UUID, source revision,
flagged step index, fixed replacement actions and duplicate receipts. It creates a
new task; it never edits the original, skips a step or starts playback automatically.
Record replacement is available for actions that cannot be corrected faithfully.
Raw scripts, CSS, shell and credential URLs are rejected.

For this navigation task, the faithful correction replaces step 3 with a wait for
“Active & Upcoming Events” on the main dashboard, with a 30-second condition timeout.
The first two navigation steps are preserved. The copy retains the actual original
recorded duration and records source ID/revision/corrected step in local metadata.
The original remains visibly Needs attention as historical evidence.

The helper advertises protocol 3. Older helpers receive an update explanation;
copy correction is gated server-side to protocol 3. Existing normal controls,
Pause/Resume/Stop, revision-bound execution and duplicate-start protection remain.
The setup zip includes the updated helper; upgrade uses the safe idle installer and
preserves tasks, profile, DPAPI pairing, local files and sessions.

## Verification

- `tests/test_task_recorder_attention.py`: exact step/reason, interruption distinction,
  passive navigation versus actual frame input, fixed reason mapping, strict copy
  correction, original bytes/revision preservation and rejection of unsafe replacements.
- Existing recorder, relay, metadata, navigation and Pause/Resume/Stop suites retained.
- `tests/task_recorder_frame_trial.py`: full isolated OS sign-in, explicit synthetic
  PC pairing, recording an OS navigation without false flags, actual page Review
  step → corrected copy → Play with a closed browser; asserts final dashboard URL
  and visible “Active & Upcoming Events”. Also tests genuine iframe input rejection
  and automatic privacy pause for a dynamically loaded password field.
- Synthetic preview uses port18964; its headed test helper uses port18934 and separate
  local storage. Production credentials/provider writes are not used in preview.

Evidence stays under `%LOCALAPPDATA%\SportsCaveOS\TaskRecorderFrameFix-64cdf0b0`.
It includes the untouched original snapshot, exact legacy capture reproduction,
focused evidence and corrected-preview screenshot. Live verification is recorded
separately after deployment and installed-helper upgrade; an accepted Play command
alone is not counted as successful playback.

No edition/Photoshop/companion/worker queue or Render topology changes are included.
Genuine iframe actions, unsupported gestures and missing/ambiguous targets still
require attention; this fix does not claim universal browser or Meta automation.
