# Creative Refresh Carousel repair and compact UI

Implemented and verified locally on 9 October 2026. No commit, push, deployment,
Meta mutation, Shopify mutation, email send or automation publication was performed
by this task. The comparison source is `b274b054235be54854fd972006eb9e7a46a707c7`.
Existing unrelated Email V2 work was preserved; its commit was made outside this task.

## Confirmed defects and evidence

The active route is `ads_creative_refresh.render_page` → `ads_page.render_page`
in Creative Refresh mode → `build_ads_result_record` / `build_ads_prompt` →
`ads_refresh_generation`. The older standalone builders in
`ads_creative_refresh.py` are not this page's generation path.

Historical repairs were already present: ordered original cards, separate per-card
analysis, full shared realism rules, three-cover IE output, product correction,
dynamic Carousel counts and durable package saves. Those were retained.

1. **Incorrect Carousel instructions in the UI.** The image slots and copy editor
   still displayed New Ads' fixed `IMAGE_ORDER` roles, even when the winner had a
   different scene or role. These contradicted the winner-led master prompt.
   Refresh now labels each original-to-refreshed card mapping and displays only
   supplied scene/role metadata. Unknown observations remain explicitly unknown.
2. **Six-card editor crash.** `_render_carousel_setup_notes` indexed the five-item
   `IMAGE_ORDER` list using every actual source position. The active AppTest page
   reproduced `IndexError: list index out of range` for six cards. It now renders
   all six, as well as four and five, without inventing roles or dropping cards.
3. **Disappearing Save.** `_render_ads_image_save` returned before rendering any
   Save button when quality checks failed. Required execution notes were inside
   a collapsed section. Save now stays visible but disabled, with the reason;
   incomplete execution review opens automatically. The same quality gates still
   run in the actual save operation. Malformed edits block Save/Post while keeping
   the last valid analysis rather than deleting it.
4. **Incomplete copy instructions.** The Carousel master explicitly requested
   five primary texts and N card pairs, but did not explicitly request the five
   shared headline and description rows that its CSV template and readiness gate
   require. The prompt now names all required existing rows. No CSV columns or
   posting settings changed. This is a proven instruction gap, not evidence that
   a particular external ChatGPT response omitted those rows.
5. **Saved URL lost on reopen.** Restoration reset the URL's manual/autofill flags.
   The next catalogue render replaced a saved host alias or tracking URL with the
   catalogue URL. `source_matches` then rejected the saved package and hid
   POST NOW. The active Save/reopen/Post fixture reproduced this mismatch.
   Reopening now retains the exact saved URL, including query/fragment, also when
   a legacy selector identity must first resolve. Stale fields for that exact run
   are cleared; unrelated drafts are preserved. Changed current settings require
   Submit before Save, preventing an old package being saved as the new selection.

The reported stock-mockup visual result itself cannot be proven or attributed to
a particular generation from this material: no genuine winning-card attachments
and corresponding generated outputs were supplied for visual comparison. No pixel
analysis, originality assessment or performance improvement is fabricated here.

## Winner-led generation and format protection

Carousel still uses all N original winning images, N independent observations,
N standalone image prompts, N finished-image slots and N card copy pairs, in
source order. Five shared primary texts and the existing shared headline and
description options remain separate from the card positions. Each card keeps its
winning broad scene family, advertising role and supported detail-shot purpose.
The existing instructions require concrete architecture, layout, composition,
lighting and product-prominence improvements rather than recolouring a room.

An optional canonical black-frame photograph is now explicitly limited to exact
artwork/frame fidelity in the master and every Carousel standalone brief. Its
stock room, furniture, camera and lighting must not become the creative scene.
It is neither a mandatory duplicate upload nor an additional source/output card.
Conflicting or unreadable product details must be resolved before generation.
The existing collective winning-card product authority remains usable without it.

Duplicate source-file identities and identical returned prompts now fail clearly.
Existing output-byte duplicate checks, per-card observations, full product-lock
and realism blocks, observed-versus-proposed execution checks, copy checks and
final human visual review remain. These checks do not detect every perceptually
similar image or establish that natural-language observations are truthful.

**Instant Experience generation is unchanged.** Its winner analysis, three-cover
prompts, exact copy/description rules, permanent slot IDs, CSV and posting
structure were preserved. Fifteen New Ads and ten IE/Single Image Refresh prompt
comparisons across five categories are byte-identical to pre-change outputs.
Shared realism helpers, `ads_carousel_winner.py`, `ads_image_workflow.py`,
`meta_review_products.py`, CSV headers and the Meta posting engine were not edited.

## Save and Posting

Both formats continue through the proven New Ads image/package save functions,
Dropbox receipts, saved source signatures, `ads_refresh_saved` workspace file,
`ads_posting_handoff.queue_saved_package` and existing Posting import.

The active tests exercise real UI Save controls with fake storage, exact saved
workspace reopening, verified package identity and POST NOW navigation. Product
title/ID/handle, category, market, destination, source provenance and image-to-copy
associations continue through existing package validation. Current mismatch
checks and product correction tests pass. No replacement winner record is written.

POST NOW opens Posting with the saved package; it does not submit Meta ads.
Existing PAUSED creation and duplicate/recovery safeguards are unchanged and
covered by the mocked Posting tests.

Four- and six-card packages still save/export their actual card count. **Posting
continues to support five-card Carousel packages only**, with the existing clear
restriction; this repair does not silently truncate or expand Posting behavior.

## UI and performance

Only Creative Refresh receives the new compact CSS. The heading clears the app
header, reference roles are labelled, the winner preview is smaller, uploads and
buttons are compact, and Save/Post remain aligned. Three IE cover/copy panels sit
together on desktop and stack below 1050px. Required copy remains editable.
Existing full-resolution download, upload, replacement and clipboard actions stay
available. Carousel prompts use one reusable card selector/viewer rather than
rendering a clipboard iframe and large code block for every closed card panel.

Measured bottlenecks and changes:

- IE reread the same archived winner on every rerun. A single immutable winner
  (maximum 8 MiB) is retained in the authenticated session, scoped to user, account
  and image hash. Changing scope clears it; failures are not cached. The database
  query, authentication, records and existing Carousel archive cache are unchanged.
- Unchanged uploaded files were read/hashed again before discovering they were
  unchanged. Refresh now recognizes Streamlit's upload identity first. New files
  still run existing image validation; this transient identity is cleared on
  reopening. Small Carousel previews reuse the existing bounded thumbnail helper;
  saved/exported original-quality bytes remain unchanged.
- Refresh quality checks are reused between the final action controls, while the
  save backend continues to validate independently. No new service, dependency,
  background worker, campaign scan or product cache was introduced.

Actual local measurements, using the same mocked browser fixture:

| Measurement | Before | After |
|---|---:|---:|
| IE page height, 1366px viewport | 4,443px | 2,436px (45.2% less) |
| Carousel page height, 1366px viewport | 5,744px | 5,087px (11.4% less) |
| IE page height, 390px viewport | 6,308px | 4,674px |
| Carousel page height, 390px viewport | 12,740px | 10,590px |
| Browser initial IE display | 2,091ms | 1,687ms |
| Browser initial Carousel display | 1,530ms | 1,628ms |
| IE archived winner reads over six renders | 6 | 1 |
| Unchanged 10.65MB upload CPU, median of 60 calls | 4.808ms | 0.0004ms |

Browser loading values are individual local samples including fixture startup and
a fixed 500ms settling period, not production latency or a statistically established
speedup. Carousel initial loading did not improve in the recorded final sample.
The eliminated repeated read/hash work and reduced layout height are independently
verified. No live database/Meta/Shopify timings were measured.

## Verification

- Pre-change focused baseline: **120 tests passed**, 16.538s.
- Final focused acceptance: **469 tests, 468 passed, one existing failure**, 33.810s.
  This includes **15 new repair tests**, existing product correction, references,
  image validation, save/reopen, CSV, Carousel and IE, paused posting, failures,
  recovery and duplicate safeguards. The failure is
  `test_ie_refresh_all_three_briefs_include_premium_fomo_rules`: an older assertion
  expects the unsplit rules block three times despite the existing reordered IE
  realism contract. It fails identically on original source and was not weakened.
- Wider existing suite: **303 tests**, 14 failed assertions/subtests and one error,
  155.612s. All reproduced against original source: three New Ads UI expectations,
  two older sidebar/clipboard source assertions, nine historical IE snapshot
  subcases, and the ambiguous Carousel fixture indexing an intentionally empty
  card list. Detailed failure identities are in the results JSON. No new regression
  was found in these runs; the overall repository suite is not claimed green.
- Additional final URL/reference/repair check: **26 tests passed**, 11.745s.
- Headless Edge: **1366, 1024, 750 and 390px**, no overflow or application exceptions;
  three desktop IE columns, stacked narrow layouts, heading clearance, Copy Prompt,
  actual local cover upload/preview, Carousel CSV import, mocked Save and exact
  three-/five-asset POST NOW handoff all passed. External requests were blocked.
- Existing Node image-clipboard tests passed, including denial/insecure fallback
  and original-resolution handling. Python compilation and `git diff --check` passed.

All images used for UI tests were synthetic colour tiles. Execution records are
test declarations, not manufactured successful analysis of real winner pixels.
The reproducible measurements and failure inventory are in
`docs/CREATIVE_REFRESH_REPAIR_RESULTS.json`.

## Files changed

Production:

- `ads_page.py`
- `ads_refresh_generation.py`
- `ads_refresh_plan.py`
- `ads_refresh_reference.py`
- `ads_refresh_saved.py`
- `ads_refresh_ui.py` (new)
- `meta_review_handoff.py`

Tests, fixtures and measurement tools:

- `tests/test_ads_refresh_reference.py`
- `tests/test_ads_refresh_repair.py` (new)
- `tests/test_ads_refresh_ui.cjs` (new)
- `tests/fixtures/refresh_ui.py` (new)
- `tests/fixtures/refresh_unaffected_prompts.json` (new)
- `tests/refresh_measure.py` (new)
- `tests/refresh_upload_benchmark.py` (new)
- `scripts/run_refresh_browser.py` (new)
- This report and `docs/CREATIVE_REFRESH_REPAIR_RESULTS.json` (new)

## Release requirements and remaining limits

The targeted repair is ready for review and a separately approved release based on
the local checks. No migrations, credentials, permissions or dependency updates
are required. Review the exact diff, rerun the focused tests and browser runner,
then obtain separate approval for commit/push/deployment. Release to the existing
canonical `sports-cave-os` service only; do not create or rename services. If a
Blueprint sync is proposed, run `scripts/validate_render_topology.py` and inspect
the preview as required by AGENTS.md. No Blueprint sync is needed for these files.

After an approved release, verify one genuine saved winner in each format without
submitting Meta: load, copy prompt, import output, save, reopen and open Posting.
Inspect actual generated artwork/frame fidelity, role retention and novelty before
using the assets. Real image generation, live Dropbox persistence and production
latency remain unverified here. Existing stored prompts/packages are preserved;
only an obsolete active Carousel master prompt receives the new instruction suffix.
