# Companion automatic submit repair — 18 November 2026

Task: 20261117-9bcb0e65. Owner: codex-companion-submit-20261118-final.

## Baseline and diagnosis

The Studio approved base predates windows-upload-companion. Inspected and copied
only the installed extension 1.4.3 into this isolated task as the repair baseline.
Inspected and copied the two focused composer/reference tests from task
20261117-008c7d36; no application changes from that task were transferred.
The original checkout contains unrelated unfinished work and was not edited.

Compared Git history: 935d0f8f (17 November 21:01 AEDT) selected second-highest
thinking; 1c00deca (18 November 08:06) added draft preservation; b812014a
(08:25) added verified image attachment; d54a05eb (08:50) integrated cancellation
and Ads support. Today's local 1.4.1–1.4.3 repairs added filename selectors,
longer upload waits and conditional model-menu reopening.

Live Edge inspection confirmed an enabled Send, one image and one pasted prompt
in the stalled project. The actual loaded extension was already 1.4.3; simply
reloading yesterday's patch was therefore insufficient. Fresh worker DevTools
storage showed a recorded failure after setting second-highest thinking, and
the latest job was explicitly cancelled. The old DevTools window was stale.
The exact readiness subcondition of the recorded older failure is not available.
The composer placeholder is a data-empty-paragraph/data-placeholder decoration;
its appearance in accessibility alone does not establish it as the blocker.

Confirmed code-level failure modes: reopening the model menu after a prepared
paste can invalidate the ready draft; Design waits ended at 25 seconds, while
reference uploads got 120 seconds; Design prompt acceptance also depended on
abbreviated preview text. An unanswered tabs.sendMessage Promise does not itself
provide ongoing extension API activity, leaving long uploads vulnerable to MV3
worker suspension. Lifecycle reference:
https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle/
The suspension case is regression-tested, not claimed as the observed live cause.

## Repair 1.4.4

- Select and verify second-highest power once before preparing the prompt.
  Do not reopen or change the model menu after the draft has been prepared.
- Both Work projects wait up to 120 seconds for their current enabled Send.
- Recognise the single pasted-text attachment created by this invocation without
  depending on its truncated display preview. Existing drafts/attachments remain
  refused; reference identity, extra attachment and changed inline-text checks stay.
- Reserve submission through the existing worker permit, recheck current readiness,
  click once, and verify the user turn. Missing acknowledgement never triggers a
  second click.
- Keep the worker active with a local storage read every 20 seconds only during
  the bounded handoff; always clear its timer on completion, cancellation or error.
- Preserve cancellation, receipt checks and reference hash validation.

## Verification and installation

14 focused Node tests pass:
node --test tests/test_upload_companion_composer.cjs tests/test_upload_companion_reference.cjs tests/test_upload_companion_worker_lifetime.cjs

New slow-project and worker-lifetime regressions fail against installed 1.4.3
and pass with this repair. Coverage includes 65-second waits for both projects,
missing model labels, rerendering model menus, abbreviated previews, disabled
Send, cancelled jobs, denied permits, changed drafts, extra files and lost ack.
Node syntax checks pass for composer.js and worker.js; git diff --check passes.

Installed only composer.js, worker.js and manifest.json into
C:/Users/hello/AppData/Local/SportsCave/UploadCompanion/1.1.0.
SHA256 comparisons verified all three against tested source.
Backup: C:/Users/hello/AppData/Local/SportsCave/UploadCompanion/backups/submit-1.4.4-20261118-9bcb0e65.
Reloaded the existing extension through Edge and observed version 1.4.4 enabled.
Fresh Companion-created project tabs load this version. Cancelled old drafts
were left untouched. No actual production workflow was sent as a test, so a live
ChatGPT submission outcome is not claimed. No commit, push, merge or Render deploy.

## Observed live failure and repair 1.4.5

Watched the user's Silver & Soul - Lewis Hamilton Wall Art run from mockups
through ChatGPT handoff. Version 1.4.4 uploaded the image and pasted prompt,
and Send became enabled, but it still did not submit. The fresh worker recorded:
"ChatGPT did not make the pasted prompt ready to send: waiting for verified
reference image attachment."

ChatGPT displayed the original reference filename with `(5)` inserted before
`.webp`. The exact-name attachment check therefore stopped recognizing the
successfully uploaded reference. This is the directly observed live cause;
the earlier robustness changes alone did not resolve this run. Today's verified
reference-attachment requirement introduced the check that rejected this state.

Version 1.4.5 accepts ChatGPT's numeric filename suffix for the sole owned image,
while retaining reference hash verification and rejecting unrelated filenames
and additional attachments. Added two regressions, including renaming the image
after prompt paste to reproduce the timing of the live failure. Both fail on
1.4.4 and pass on 1.4.5. All 16 focused tests pass; composer syntax passes.

Installed composer.js and manifest.json, verified matching SHA256 hashes, and
reloaded the existing Edge extension. Observed version 1.4.5 enabled.
Backup: C:/Users/hello/AppData/Local/SportsCave/UploadCompanion/backups/reference-rename-1.4.5-20261118-9bcb0e65.

The failed live job remains Needs attention. Its available recovery action is
Restart failed upload, which regenerates mockups from the original PSD. Left
that live restart to the user. No successful live auto-submit on 1.4.5 has yet
been observed. Both Design and Upload use the repaired shared composer.

## Successful authorized live retry

The user explicitly requested restarting the failed job from the app status bar
and monitoring through submission. Used Restart failed upload once. New job:
d67079fb-fdd3-40ff-a671-639fd4f7d7ea. Observed PSD preparation, mockup generation,
Dropbox saves and automatic ChatGPT handoff under installed version 1.4.5.

At approximately 10:12 AEDT on 18 November, observed a new chat with a sent user
turn containing the black-frame image and Pasted text(20261117-231150).txt.
ChatGPT began responding: it would read the attached brief and project guide.
The composer was empty and a generation-stop control was visible. No manual Send
click or keyboard submission was performed. This verifies actual automatic
submission, beyond the local regression tests.

Conversation: https://chatgpt.com/g/g-p-6a387a17627081918e1700ec2783a12b-sc-mockups-uploads/c/6afcdf36-d360-83ec-8333-b173df7a2be6

This verifies the Upload run and shared composer; it does not claim a separate
live Design run, downstream product completion, or immunity to future ChatGPT
UI/service changes. No additional code change was needed after this retry.

## Post-submission diagnosis and hardening 1.4.6

Inspected the completed response in the same live conversation. ChatGPT reported
6/8 WebPs saved, with the Man Cave completed. Office request
bf2812d8-9bc2-4303-9b2c-e343d64d99c7 and Living Room request
00b61654-78ae-4006-980e-981e9042e264 returned moderation_blocked, category other,
at the output stage. These are assistant-reported tool results; the underlying
tool logs were not independently retrieved. No exact product was found by its
Shopify lookup. Publication and mapping remain pending, not complete.

The final response omitted SC_UPLOAD_BLOCKED. Added an Upload-only fallback for
an explicit moderation_blocked report together with unfinished/pending language
in the final assistant response, never while generation is active. Added a
specific MODERATION reason preserving completed assets rather than recommending
a full restart. Existing explicit stage markers retain priority. This improves
failure visibility, not the image service's acceptance rate.

Added local prompt recovery instructions: verify/save each successful card,
checkpoint IDs/roles/operation tag, reuse completed files, cap transient retries,
check writes before retry, preserve approval requirements, and verify actual
publication/mapping receipts. Moderation is not retried or evaded; approved
missing outputs are needed before resumption. Existing room and image-production
requirements are unchanged. These Python prompt changes are LOCAL ONLY and
require an authorized hosted-app release before affecting newly generated prompts.

Validation: 21 companion Node tests and 6 master-prompt Python tests pass;
git diff --check passes. Installed hash-verified composer.js, staff-queue.js and
manifest.json; Edge shows enabled 1.4.6. Backup is
C:/Users/hello/AppData/Local/SportsCave/UploadCompanion/backups/progress-1.4.6-20261118-9bcb0e65.
Existing chat content scripts are not retroactively replaced by extension reload.
Did not regenerate rejected outputs, fabricate a complete manifest, publish a
partial product, or claim mapping completion. No commit, push or deployment.

## Authorized release preparation

User subsequently explicitly authorized pushing to Render and a complete live
workflow test. Integrated current live main 6c07260b3ffdf3702bf9ee528b59f0fb41cc0c6c
into this owned task branch. Preserved newer scene quality, safety-rejection
handling, staff mapping protocol and Design Studio changes. Resolved overlapping
companion files against the tested 1.4.6 implementation; retained existing
progress tests and Meta Ads coverage. Added timer globals to the queue test VM
to model the worker keep-alive API.

Combined verification: 35 Node companion/queue tests pass; 33 Python prompt,
scene-quality, staff-queue and staff-mapping tests pass with disposable PGlite.
One upstream Starlette test-client deprecation warning. Topology validation and
diff whitespace checks pass. No infrastructure or migration changes. Canonical
Render service is configured to auto-deploy main; no Blueprint sync is needed.
