# No Fear USA — blocked and successful run comparison

Task 20261120-b8387c2e, owner codex-ad-run-audit-20261120-08.
User authorized comparison, recording evidence, focused prompt/Companion fixes and Git/Render release while preserving the design and three-line footer.

## What the evidence establishes

The blocked job `dddf3ca0-bf8a-5af1-87a4-5cdc4300595c` produced Hallway and Man Cave JPEGs plus its CSV. Ad 2 returned provider output-review `moderation_blocked`, request `e331e00d-4ea0-41c4-8f58-7fafdd48cc71`, without identifying triggering content. Its chat and queue displayed that same reason. There was no successful full Meta posting receipt.

The user independently queued successful job `33e70273-f3a5-5d42-b30b-9ab5ac495194`. It ran approximately 02:15–02:28 UTC on 20 November 2026. Observation did not submit or modify its generation requests. All three images rendered, all four original files imported automatically, and posting job `e87cab10-99b5-5fc6-8c19-57fa6a6ee2d5` reached **Ads created · PAUSED for review**. The queue completed count advanced from seven to eight, with no running/waiting ad. No blocking generation, attachment or posting error was displayed. This does not mean the ads are delivering or spending.

[Successful chat](https://chatgpt.com/g/g-p-6a6bd98cd6f081918788b544dcdecfc2-sports-cave-meta-ads/c/6affad34-2234-83ec-9685-38832453dd7e) · [Posting receipt](https://sports-cave-image-factory.onrender.com/?page=ads_posting&meta_posting_job=e87cab10-99b5-5fc6-8c19-57fa6a6ee2d5)

Compared both exact submitted text attachments previously read through their visible previews. Both reference the same Shopify URL and version:
`no-fear-kobe-bryant-vs-allen-iverson-wall-art-black-framed-nba-wall-art.webp?v=1795058845`.
Both contain the same 160 px footer geometry and 50 px title profile. Shared project sources remained the premium compact V2 references, and the installed Companion was 1.7.7 for both runs. The later 1.7.8 audit fixes below were not involved in the successful run.

| Input | Blocked run | Successful run |
|---|---|---|
| Ad 2 role | Architectural product wall; tiny residential glimpse | Front-view collector hallway; visible passage depth |
| Ad 1 headline | 100 Edition Collector Run | Limited to 100 Editions |
| Ad 2 headline | Limited to 100 Editions | Only 100 Will Ever Exist |
| Ad 3 headline | Only 100 Editions Available | Limited to 100 Worldwide |
| Supporting copy | Original saved assignment for each route | Fresh saved assignment for each route |
| Room/light selection | Earlier three homes | Fresh variation token, different resolved home/light choices |
| Artwork reference, footer design, CSV route identities | Same product reference URL, compact three-line profile and schema | Preserved |

The corrected room definition is a confirmed design fix. The fresh run also changed scene details and copy assignments, and provider-generated pixels differ. This was not a controlled comparison. The provider supplied no causal explanation, so neither the room name nor any other changed phrase can be identified as the reason it accepted this run. Do not promote a successful prompt into a claimed moderation workaround or automatically resubmit rejected content.

## What worked and should be retained

- Original black-frame artwork was verified before generation; every cover retained the featured athletes, action, title, seal, complete frame and believable glazing.
- Ad 2 visibly depicts a front-view collector hallway. The first hallway and Man Cave are distinct residential compositions with different wall/light treatments.
- Inspected all three final downloaded Library JPEG originals, not only generation previews. Each is 1024 × 1024, has its assigned headline/supporting sentence/CLAIM YOUR EDITION on exactly three visible baselines, an inline gold number and underline, the compact footer boundary at y=864 with its thin highlighted seam, and no fourth line. Font naming/point size cannot be certified from raster metadata; visible hierarchy, spacing and readability were checked.
- CSV has 11 columns and three populated rows in stable route order; the existing parser accepted it using an offline synthetic result. Actual import success is separately established by the live Companion receipt.
- Initial handoff confirmation advanced without another Send. Collection progressed through the CSV and all three images, then the existing durable posting job created all three ads paused. Native Library downloads worked during independent inspection; there is no claim that the automatic collector needed that fallback or a repair message in this run.
- Preserve original-byte recovery, immutable receipt hashes, saved chat/response provenance, stable filenames, bounded repair permits and final three-ad verification. The second slot's legacy architectural-wall.jpg filename remains a delivery identifier for Collector Hallway Front View.

### Preserved successful output evidence

| Original filename | Bytes | SHA256 |
|---|---:|---|
| collector-hallway(20261120-022041).jpg | 447617 | 966b240cb7bd5048e2bf033931552ca780a1969b754d7d19831f231cfaf29dd1 |
| architectural-wall(20261120-022041).jpg | 479227 | 1958895c46cf770b53926cb6138840b6c6df9ce38e479fa8055df649ed856840 |
| man-cave(20261120-022041).jpg | 403358 | 0a4a3fc9b30a5a9db5488142d9f0e65d8290f63a4dc24cc1536197c1773cf158 |

The original observation receipt is saved locally as Downloads/no-fear-usa-run-33e70273-review.json. This repository report records the findings without uploading image binaries.

## Remaining conflicts fixed in this release

1. **Generation versus recovery.** Companion 1.7.7's attachment-repair message said to reuse originals “where possible” and otherwise recreate from the brief. That conflicts with recovery of approved original bytes and risks design drift. Companion 1.7.8 explicitly recovers existing exports/associated Library originals only, preserves the design and three-line footer, and never regenerates, rewrites, restyles or switches room during download repair. It emits READY only when the required originals exist; unavailable originals produce the existing BLOCKED marker with the actual filename/reason. No send permits, repair bounds, receipt checks or posting behavior change.
2. **Downloadable package completeness.** The server ZIP omitted ad-library.js even though manifest.json declares it. The working installed 1.7.7 copy already contained it, so this does not explain the observed moderation rejection. Added the missing file to the ZIP so fresh installations retain the existing original-Library fallback. The existing packaging regression test exposed this defect and now passes.
3. **Initial generation versus creative review.** Two pack instructions could be read as limiting all generation to one call per ad despite the existing pre-export creative review. Clarified that they describe the initial image phase. Existing review, final image count, protected design/copy and technical-only failure rules remain unchanged. Download recovery stays a separate no-generation phase.
4. **Connection versus previous job status.** During reload verification, the health panel visibly reported version 1.7.8 but called an old stopped-job state “not connected.” Its default label treated unlisted job states as absent transport. Cancelled/blocked states and other version-bearing responses now say the Companion is responding and retain the original job reason/time. Missing responses still show not connected. Pairing, credentials and controls are untouched; no automatic pairing or start request was added.

The existing local 1.7.7 ad-repair.js and manifest.json were verified against released source before backing up and installing the two changed 1.7.8 files. The user reloaded the existing extension and the live browser panel visibly reported 1.7.8. No new extension permissions or identity were introduced. The health-label and complete ZIP fixes are served by the Render release.

## Validation and scope

87 focused Python/browser tests passed, covering actual repair message text, one-shot Send/draft recovery, Library provenance/downloads, full package contents, five-market initial/review phase wording, unchanged footer/design contract, scene consistency, parser/manifest hashes and prompt-library UI. Nine Node download/receipt tests and the copy-feedback/health-label Node harness passed. Synthetic health tests distinguish stopped/unknown job states from a missing response, retain reasons and verify only a health request is issued. Studio, Render topology and whitespace checks pass.

No generated image, assigned headline/supporting sentence, 160 px footer specification, room role, targeting, live campaign or project source was modified during this audit. Existing creative-review corrections and technical-only reserve rules remain in place. No live image-generation or posting test was started.
