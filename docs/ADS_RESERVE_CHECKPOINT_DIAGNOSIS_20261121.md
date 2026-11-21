# Legends Never Die reserve-room diagnosis

Task 20261121-0435a203. User authorized diagnosis, a stronger fallback prompt and
Git/Render release. Local tests use synthetic inputs and blocked provider access.

## Confirmed cause

Read-only production job and saved ChatGPT conversation inspection confirmed job
`89fafa40-b451-52fa-8546-cc660e66d47c` completed one image and its three-row CSV.
The two missing files were rejected by the image provider's safety system:

| Missing filename | Request ID | Code | Stage | Category |
|---|---|---|---|---|
| collector-hallway.jpg | d2335789-46ee-456b-995c-0122d07a9525 | moderation_blocked | output | other |
| man-cave.jpg | b4758d32-cdf7-4c11-8ddf-47e65bddaeac | moderation_blocked | output | other |

No more specific cause was supplied. There is no evidence that either room
caused the rejection. The original reserve policy explicitly excluded moderation
and unexplained rejections. The assistant correctly preserved the successful
image and copy, reported the provider evidence and emitted SC_AD_BLOCKED.
Reserves did not run because these failures were ineligible, not because the
reserve section was missing. No retry or alternate room was submitted here.

## Strengthening for eligible technical failures

The old section called reserves optional fourth/fifth calls and left the decision
inside a long final-review tail. This was ambiguous for otherwise eligible
technical failures, although it did not cause this moderation stop.

- New Ads IE execution now has an explicit step 4a between original call 3 and
  final review/export: inspect original results and execute eligible unused
  reserves without a new approval. A missing image alone does not prove an
  eligible technical error.
- Reserve A and B are required when their respective missing slots qualify.
  Allocation remains in original slot order, one attempt per distinct slot,
  at most two total. Successes, reference, camera, footer split, CSV mapping and
  delivery filenames are retained. Budgets never reset on recovery.
- Incomplete delivery reports exact provider evidence and reserve eligibility,
  attempted reserve/result or ineligibility reason per missing file. Missing
  provider metadata must remain unspecified, never invented.
- Moderation and unexplained rejections remain ineligible. The app now explains
  the technical-only reserve rule alongside an existing moderation failure.
- Project source documents mirror the stronger rules. The current live project
  already delegates scene execution to the current OS brief and limits reserves
  to technical failures. Its settings were not changed.

The Baseline 2.0 two-line footer template, room specifications, copy frameworks,
existing saved briefs, Meta campaign identities and companion installation are
unchanged. This release cannot complete this particular job's rejected slots
through alternate-room retries; the provider rejection requires review.
