# Ad partial delivery and prompt clarity

Task 20261121-48b20555. User authorized investigation, workflow/prompt correction
and Git/Render release. No generation or Meta operation is part of local tests.

## Diagnosis

The newer Legends Never Die job `b5a354d2-168c-5f27-b957-6d7f1476384c` used the
current two-line prompt and reserve V2, created at 04:31:28 UTC on 21 November.
Its final marker names `man-cave.jpg` as missing after output-stage
`moderation_blocked`; the screenshot shows two image attachments and a CSV.
The provider's detailed rejection reason is unavailable. The success of two
independent calls does not identify a triggering prompt clause for the third.
No claim is made that these workflow contradictions caused moderation.

Separately, the code raised a terminal ValueError immediately on the moderation
event, before the collection stage could download successful exports. Posting
requires all three valid images and the CSV, so the incomplete pack cannot
legitimately become a completed three-ad campaign.

The prompt repeated the full, identical two-line footer specification twice.
Its CSV section said "after all three images", while its failure rules required
independent copy/CSV completion even when an image failed. The final wrapper also
only described four-file delivery. These are orchestration problems, not evidence
about the provider's safety decision.

## Correction

- Shared generation instructions include the exact footer specification once.
  Standalone image briefs retain the full footer profile. No font, geometry,
  product identity, scene, camera, copy framework or saved assignment is changed.
- Final review covers available images and all copy records. CSV creation and
  available-file attachments proceed independently of a missing image. Completion
  still requires all four originals; safety/unexplained rejections stay blocked.
- A rejection with an exact saved chat, prepared folder and named missing slots
  enters collection of existing successful exports only. Rejected slots are
  excluded. No repair Send, generation, creative revision or Meta submission is
  allowed in this state; existing Send permits remain preserved.
- Receipt/provenance validation remains in the normal transfer endpoint. The
  rejected slot cannot be filled through this collection path. Posting has a
  second guard against any partially rejected package.
- After collection, the job returns to review with its original rejection and
  saved receipts. Transfer failure or a persisted ten-minute deadline releases
  the queue for other jobs, preserving every saved original. Polls/restarts do
  not extend this deadline. Resume Import for a rejected job also uses this
  collection-only path.

Validation uses synthetic briefs, disposable PGlite SQL, fake Dropbox and an
offline provider guard. Tests cover real file receipts, excluded slots, resume,
restart/deadline behavior, no repair/Posting, current creative contracts and the
unchanged two-line footer. Prompt tests do not prove image-provider acceptance.
