# Meta Review → Creative Refresh: format and complete card handoff

Implemented locally. No live Meta reads/writes, email sends, Shopify requests,
schema changes, configuration changes, commits, pushes or deployments were made.

## Root cause and active path

The active path is `meta_review_live.load_campaign` →
`ads_meta_review_page.build_ads` → selected row / `simple_winner` (with advanced
`winner_board`) → `meta_review_handoff.build_package` → existing media archive and
action-log handoff → `load_link` / `hydrate` → `ads_page` Creative Refresh →
`ads_refresh_generation.build_prompt` / `ads_refresh_plan` → existing CSV,
image upload, save/export and applicable Posting handoff.

The old asset extractor only exposed a thumbnail when child attachments supplied
image hashes rather than URLs. It did not retrieve existing-post subattachments.
The handoff sliced child attachments and archived cards with `[:5]`; the source
viewer, reference map, prompt, CSV and image-slot paths assumed five cards.
Format provenance was also conflated with benchmark/saved campaign labels.

## Graph fields and detection

The application default is Graph **v26.0**, with the existing `META_API_VERSION`
override still respected. Neither configuration nor the API client was changed.

Selected-campaign ad-list fields now retain the existing reporting payload and
add lightweight image/video/destination/story identities:
`id,name,status,effective_status,adset_id,creative{id,name,thumbnail_url,image_url,image_hash,video_id,link_url,object_story_id,effective_object_story_id,object_story_spec,asset_feed_spec},created_time,updated_time`.
The existing reporting inputs were retained to avoid changing benchmark logic.
Story IDs prevent a post cover from being mislabeled Single Image before lazy resolution.
The campaign overview does not retrieve ad creative detail.

Only a selected/opened winner receives the new full creative read:
`id,name,object_story_id,effective_object_story_id,object_story_spec,asset_feed_spec,object_type,image_hash,image_url,thumbnail_url,video_id,body,title,link_url,template_url,template_url_spec,destination_spec,call_to_action_type`.

Rules, in order:

1. Nonempty asset feed → **DYNAMIC**; alternatives are never authored cards.
2. Multiple genuine inline `link_data.child_attachments`, or a complete existing
   post `attachments.subattachments` set → **CAROUSEL**. A Canvas destination
   does not erase an authored carousel cover format.
3. Concrete Facebook `/canvas/` destination URL in creative/story metadata →
   **INSTANT_EXPERIENCE**.
4. Concrete video ID → **VIDEO**.
5. Concrete single-image asset, with no unresolved existing-post identity →
   **SINGLE_IMAGE**.
6. Insufficient, malformed, thumbnail-only or unresolved-post evidence →
   **UNKNOWN**.

Every result includes format, exact evidence path and `deterministic` or
`unconfirmed` confidence. Names and numerical confidence guesses are unused.
Campaign display aggregates available ad evidence to a uniform format or MIXED;
unread formats remain visibly UNKNOWN. Existing performance/benchmark rules are
unchanged and are not the authority for the new creative handoff.

Field support was checked against Meta's generated SDK definitions:
[AdCreative](https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/adcreative.py),
[link data](https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/adcreativelinkdata.py),
[CTA value](https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/adcreativelinkdatacalltoactionvalue.py).
No new guessed `canvas_id` or `instant_experience_id` field is requested.

## Retrieval, identity, copy and availability

The GET-only resolver reads one creative. If authored inline cards are absent,
it lazily reads the effective/object story with message, attachments and nested
subattachments (limit 100). Permission/read errors and unfinished pagination
remain unconfirmed; a cover thumbnail never certifies a complete carousel.

Image hashes needing resolution are fetched together from the existing account
`adimages` edge, with `hash,url,url_128`. Best source priority is explicit image
URL, resolved asset URL, supplied picture, story media image, then thumbnail.
No full images are downloaded for the reporting table or card preview.

Each card retains position, original source position, creative/source/hash/media
identity, current URL, image hash, thumbnail, video ID, headline, description,
destination/link caption and CTA. Shared message/primary text and CTA remain at
creative level. URLs are retrieval values, not permanent card identities.
All actual cards survive; there is no first-image duplication or five-card slice.

`multi_share_optimized` produces a small reorder note while keeping source order.
`multi_share_end_card` alone never deletes a genuine authored card. An explicit terminal Page/profile story attachment is excluded only with the
Meta end-card setting; ambiguous attachments are retained.
An unavailable image retains its position and copy with an explicit warning.
Archiving one unavailable card does not discard the other cards.

## UI and handoff

Meta Review has compact Format columns/badges and a shared two-column source
viewer. It uses 200px images in a bounded 460px scrolling area; narrow Streamlit
layouts stack safely. Every card retains its own text. Single/IE detail views
keep one reference and full-source actions. Existing advanced metrics remain.

Copy downloads occur only after a request, use the existing bounded verified
image-byte helper, then the existing browser clipboard component. Full-source
links use the best resolved URL. The Refresh source viewer uses archived originals
and the same clipboard helper.

The existing persistent handoff carries the complete normalized creative and
ordered cards plus campaign/adset/ad/creative IDs, product mapping, market,
dates and unchanged performance context. Known Carousel/IE formats select the
correct existing Refresh type automatically. UNKNOWN has a visible warning and
safe manual choice. DYNAMIC/VIDEO cannot enter fixed-card Refresh generation.

The link fingerprint includes selected winner, full creative/copy/cards, context
and product mapping. Changing these rebuilds the handoff. Normal rerenders reuse
it, preserve operator edits, and do not repeatedly archive/save an unchanged
Apply action. The Refresh plan identity also contains the full source context.

## Prompts, CSV, output count and unaffected systems

N retained source cards → `WINNER_CARD_1` through `WINNER_CARD_N` plus
`CANONICAL_PRODUCT` → N refreshed cards, N standalone image briefs and N card
CSV records/image slots. Source copy is carried per card. Shared primary copy
stays separate; the existing schema still retains five shared-copy options.
CSV import before image upload also preserves N records. Missing attachments
must be listed and incomplete visual generation must stop.

Every brief reuses the authoritative shared realism/product-lock helper. Each
card's concept/role is retained while architecture, room execution, composition,
materials and copy must be substantially refreshed. Canonical product pixels
remain a separate authority. IE remains one winner plus canonical product →
three square covers and three matching copy sets.

New Ads remains five-card and unchanged. **Posting remains five-card**: non-five
Refresh packages can save/export every card, but the existing Posting receipt
caller blocks POST NOW with an explicit explanation rather than truncating.
No Posting or live-publishing implementation was changed.

## Performance and validation

Full creative reads are lazy for selected/opened winners. The existing scoped
120-second, 24-entry session cache is reused across preview, Apply and rerenders.
Scope includes account, API version and credential rotation hash. Resolved cached
formats feed subsequent table displays without new reads. Missing hashes use a
batch, not one Graph call per card. Copy-byte downloads have a separate bounded
session cache. No sensitive payload or exception diagnostics are logged.

Validation performed offline:

- Final relevant regression batch: **315 tests passed** across creative fixtures,
  Meta Review/live/UI/tables/benchmarks/country/CPC/product mapping, Refresh plan/
  workflow/reference, image workflow, Posting handoff, locked IE copy and winner
  refinement.
- New format/card/handoff/prompt/CSV/UI fixtures: **37 tests passed** within that
  batch, including 4/5/6 cards, existing posts, incomplete responses, missing
  images, dynamic/video/unknown, stable IDs, cache reuse and repeated Apply.
- Separate extended legacy prompt run: 215 tests; nine historical IE snapshot
  subtest failures. All nine reproduced using original HEAD `ads_page.py` in two
  isolated legacy tests; these predate this task.
- **30 New Ads prompt comparisons** across ten categories × three formats were
  byte-identical to original HEAD.
- Offline browser fixture: all six cards, zero exceptions and no horizontal
  overflow at **1366, 750 and 390px**. Images were generated colour tiles, not
  production assets. Screenshots are in the task's visualization directory.
- Python compilation and `git diff --check` passed.

Production files changed: `meta_review_creative.py`, `meta_review_handoff.py`,
`ads_meta_review_page.py`, `meta_review_tables.py`, `meta_review_live.py`, `ads_refresh_plan.py`,
`ads_refresh_generation.py`, `ads_image_workflow.py`, `ads_page.py`.
Tests changed/added: `test_meta_review_creative`, `test_ads_refresh_plan`,
`test_ads_refresh_reference`, `test_ads_refresh_workflow`, `test_meta_review_live`,
`test_meta_review_va`, `test_meta_review_active_cpc`, `test_meta_review_benchmarks`,
`test_meta_review_products`, and the offline source-viewer fixture. Legacy tests
were updated for the new Format column and actual supported creative evidence;
the benchmark fixture now deep-copies its source to prevent cross-test mutation.

## Deployment assessment and unverified variants

Safe for deployment based on these offline checks; nothing was deployed.
Actual Sports Cave Graph payloads/token permissions were not read. Existing-post
attachment availability, the account's current IE representation, original-image
resolution and dynamic/Advantage+ variants therefore remain unverified live.
Unsupported or incomplete payloads visibly fail to UNKNOWN/unavailable rather
than fabricate format/cards. This does not promise every Meta variant will be
recognized. Non-five POST NOW support remains outside this task by design.
