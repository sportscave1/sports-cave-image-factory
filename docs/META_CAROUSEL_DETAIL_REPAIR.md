# Meta Review carousel detail repair

The actual screen calls `ad_card` / `simple_winner` → `resolve_selected` →
`meta_review_creative.resolve` → `normalize`. Previously any `asset_feed_spec`
won format precedence and normalized cards became `[]`. The resolver also
skipped post attachment retrieval whenever that field was present. UI checks for
`CAROUSEL` therefore selected the single-image path; handoff lost the sequence.

Ordered inline child attachments, post subattachments, ordered top-level photo
attachments and one explicit asset-feed carousel now retain all source positions.
An asset-feed carousel resolves each label against its matching image/title/
description/link asset; ambiguous labels stay unavailable. Multiple alternative
carousel groups or a generic image pool never certify one fixed winning sequence.
Meta's SDK models this explicit structure as `carousels[].child_attachments` with
asset-label references:
https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/adassetfeedspeccarouselchildattachment.py

Fixed cards plus dynamic fields are `DYNAMIC_CAROUSEL`. Dynamic alternatives with
no ordered source remain `DYNAMIC`. All image hashes use the existing batched
account read; returned hash order cannot reorder cards. No generic creative
thumbnail is used as a missing card's image. Existing incomplete-edge checks
remain fail-closed.

The viewer is a fragment owning its image, arrows, counter and metadata. It shows
one bounded image (maximum 320px height) at a time; navigation never invokes the
parent resolver. Full-resolution links follow the selected card. Meta Review's
image-copy action was removed; archived image copying remains in Creative Refresh.

Package construction, archival and source prompt planning reject missing cards.
All N cards retain positions, URLs, hashes, copy, destinations, attachment IDs and
source creative/ad IDs. Viewer state never enters package construction. Existing
N-card prompts, slots and CSV contracts are reused; canonical product stays the
separate N+1 reference. Manual New Ads defaults and IE three-output rules are
unchanged.

## Live verification still required

No captured `Warne 181125` / `Carousel Shane Warne` payload was found, and this
checkout has neither Meta account ID nor access token configured. Its real source
structure and source/normalized/resolved/displayed/handoff counts are **unverified**.
Synthetic fixtures exercise the actual screen entry points, but do not establish
that the deployed Shane Warne creative is fixed. Open that creative after local
deployment with the connected account and check all five counts against actual
Graph evidence. Safe diagnostics log IDs, structure and counts, never tokens or
image payloads.

## Offline validation

275 tests passed in the final combined regression run, including the actual `ad_card` and
`simple_winner` entry points, reordered hash responses, missing-image refusal,
card-specific full-resolution links, N-card attachments/CSV/slots and IE/single
image regressions and refresh planning/workflow/reference tests. Browser fixture
checks passed at 1366, 750, 390 and 320px. Two existing broader assertions
still fail in untouched code: sidebar selector formatting and the clipboard
implementation's old inline-script text expectation. These were not changed as
part of this repair and were excluded from the final passing run. Compilation
and `git diff --check` passed.
