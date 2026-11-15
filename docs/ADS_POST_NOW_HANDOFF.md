# Ads saved-package handoff — local implementation report

Implemented for New Ads and Creative Refresh, for both Carousel and Instant Experience. No push, deployment, live Meta submission, or production change was performed.

## Root cause and architecture inspected

Creation stores normalized copy in its image workflow's `ad_notes` and durable images in `slots`. Creative Refresh's current `render_page()` delegates to `ads_page.render_page(workflow_mode="creative_refresh")`, with separate result/image state keys. Its older challenger package implementation is not the current Carousel/Instant Experience entry point.

Posting separately owns product selection, copy widgets, durable image records, CSV hydration, run identity, review and Meta submission. The CSV bridge carries copy but not image bytes. The creation-side Carousel Copy CSV and the dedicated Posting Carousel CSV are different schemas. Instant Experience's creation CSV is already understood by Posting, but has no product/targeting identity or images. Existing Dropbox outcomes did not retain a reusable complete Posting payload. Those boundaries caused the repeated entry and image uploads.

Inspected: `ads_page.py`, `ads_creative_refresh.py`, `ads_image_workflow.py`, `ads_image_contracts.py`, `posting_import_csv.py`, `ads_posting_page.py`, the Posting request/service contract, Dropbox save helpers, `ads_navigation.py`, app navigation and related regression tests. No Meta publisher or infrastructure code was changed.

## Shared architecture and save association

1. The existing save function normalizes the current creation copy into the existing workflow before exporting.
2. The existing Dropbox save, paths, conflict handling, image preparation and CSV/text outputs remain in place.
3. Successful uploads are paired with their exact input bytes. A complete saved record contains a package UUID, version, source, type, context, timestamp, folder, file paths/IDs/revisions, file SHA-256 hashes, source-copy model, uploaded CSV bytes, ordered full image bytes and a normalized Posting batch.
4. Carousel image receipts additionally retain their uploaded-byte hash. Partial saves and failed saves cannot create a ready package. A new save attempt revokes the previous ready record immediately.
5. The Carousel CSV now resolves collision-renamed filenames from the actual upload outcomes. This is a compatible repair: no headers, folder names or filename conventions changed.
6. POST NOW checks the current source fingerprint and current top-level creation inputs, then validates the package and queues a unique handoff. It uses the existing Ads Posting route/session/query conventions.
7. Posting validates and stages the entire package before replacing any existing Posting fields. It reuses `apply_posting_import_to_state`, the existing product matcher and `build_meta_posting_image_record`.
8. A consumed handoff ID prevents reapplication. Pending state is removed after success. Each later deliberate POST NOW click gets a new handoff ID.

Normal operation uses the retained in-memory package. It does not download the package from Dropbox, scan folders, access Downloads, or rely on an UploadedFile surviving navigation. No fallback Dropbox downloader was added.

## Field mapping

The following maps apply identically to New Ads and Creative Refresh. Creative Refresh reads its final refreshed workflow, never the winner inputs or the New Ads workflow.

| Saved value | Existing Posting destination |
| --- | --- |
| Explicit campaign type | `AD_TYPE_KEY`: Carousel or Instant Experience |
| Product ID, when present | Exact current product record; an unavailable ID blocks hydration |
| Otherwise product handle / URL / unique name | Existing product matching rules |
| Product selection | `PRODUCT_KEY` and `PRODUCT_TRACK_KEY` |
| Country | Existing canonical country codes, `COUNTRY_KEY` |
| Category | `SPORT_KEY`, checked against Posting's supported sports |
| Exact product URL | Product-bound saved URL used by the existing review/request path; cleared on a new product choice or manual CSV import |
| Campaign/ad-set identifiers | Not supplied by these creation workflows; no values invented |
| Audience and other intentionally retained draft selections | Existing Posting choices remain; the prior ad's product set is cleared |

### Carousel: New Ads and Creative Refresh

| Saved value | Posting destination |
| --- | --- |
| `carousel.primary_texts[0..4]` | `CAROUSEL_PRIMARY_TEXT_KEYS[0..4]`, unchanged |
| `carousel.cards[0..4].headline` | `CAROUSEL_HEADLINE_KEYS[0..4]`, unchanged |
| `carousel.cards[0..4].description` | `CAROUSEL_DESCRIPTION_KEYS[0..4]`, unchanged |
| Actual saved card filename | `CAROUSEL_EXPECTED_IMAGE_NAME_KEYS[0..4]` |
| `carousel-01` | Card 1 image state |
| `carousel-02` | Card 2 image state |
| `carousel-03` | Card 3 image state |
| `carousel-04` | Card 4 image state |
| `carousel-05` | Card 5 image state |
| Card URL / CTA | Existing shared product URL / fixed SHOP_NOW contract; conflicting explicit values produce an error |
| Five ad-level headline/description alternatives, complete card records and setup notes | Retained verbatim in the loaded package's `source_copy`; Posting has no additional controls or submission fields for these alternatives |

The normalized batch uses the same Carousel Posting row validation and batch adapter as dedicated Carousel CSV import. The saved creation CSV remains `Carousel Copy.csv`. Its source-side parser/import and the existing dedicated Posting CSV/import remain compatible.

### Instant Experience: New Ads and Creative Refresh

| Saved role | Posting destination |
| --- | --- |
| `premium_scarcity_right` / position 1 | Ad 1 cover, `IMAGE_STATE_KEYS[0]` |
| `premium_scarcity_front` / position 2 | Ad 2 cover, `IMAGE_STATE_KEYS[1]` |
| `premium_scarcity_left` / position 3 | Ad 3 cover, `IMAGE_STATE_KEYS[2]` |
| All three copy variations for each of the three roles | Existing `ADS_COPY_ROUTES_STATE_KEY`, plus full source copy retained in the package |
| Active primary text | Existing CSV rule: variation 1 of right, variation 2 of front, variation 3 of left |
| Active headline | Existing CSV rule: variation 1 headline for each role |
| Creation UI's “Description” | This is `primary_text`, mapped as above; it is not Posting's separate optional Description field |
| Optional Posting Description | Blank for the current source schema; stale prior descriptions are cleared |
| Creative CTA text | Preserved in the saved source copy and route variations; fixed Meta Shop Now / Instant Experience button behavior is unchanged |

The exact uploaded `Sports Cave - <product> - Instant Experience Copy.csv` bytes go through the existing canonical parser. The handoff adds product/country/sport context that the CSV lacks. No variation-selection semantics were changed.

New Ads uses the existing JPEG package export; its exact exported JPEG bytes reach Posting. Creative Refresh preserves the existing original-format package assets. Neither case recompresses an image just for navigation. The existing Posting image helper inspects the full bytes and creates a separate best-effort preview once on consumption. Original source metadata, processed-byte hash, filename, content type, dimensions, role/slot and Dropbox reference remain attached to each Posting record.

## State, failure handling and UI

The Carousel “Ad setup notes (optional)” expander was removed from `_render_carousel_setup_notes`. Its existing widgets, keys and mapping are unchanged and permanently visible under the five images. No duplicate controls or copy state were introduced. Other workflows' optional notes UI was left alone.

Before committing a handoff, Posting stages replacement copy, all images, product matching and supported country/sport validation in a temporary state dictionary. A failure leaves the old Posting work, saved package and recoverable creation state intact. The error identifies the component. The user can return to the current Posting run.

Successful hydration clears both types' previous copy/image widgets and durable image records, previous CSV uploader/import state, copy-route state, expected image names, product-specific state and stale diagnostic results. Only scoped Posting state is committed; unrelated global state is untouched. Existing Meta-history guards still reject loading a different package into a started/failed run. Completed runs receive fresh run identity through the existing helper, without reusing prior Meta IDs.

The source fingerprint covers identity/type/source, URL, market/category, generation context, normalized copy and full slot contents. Top-level form changes are also compared to the generated result. A meaningful difference hides POST NOW and asks for the updated package to be saved. Reruns after successful Posting hydration neither decode images again nor overwrite manual edits.

## Preserved workflows and safety

- Existing package generation, Dropbox save helpers, folder structure, text outputs, CSV formats, image optimization and download/import controls remain.
- Existing manual Posting, manual image upload and both CSV import paths remain. Manual Instant Experience CSV import still preserves an existing optional Posting Description, as before; a new saved-package handoff explicitly clears it.
- Existing final review, validation, campaign/ad-set selection, paused status, run history, diagnostics and explicit submission remain authoritative.
- Saving, POST NOW, navigation, hydration and reruns add zero Meta writes. The new handoff module has no network or publisher path. Existing deliberate actions inside Posting remain the only routes to their existing Meta operations.
- Tests mock Dropbox and Meta interactions. No live Meta ad, campaign, ad set or creative was created, and no production Dropbox operation was used for verification.

## Files changed

- `ads_page.py`: save receipts, canonical snapshot, current-source checks, shared POST NOW UI and visible Carousel fields.
- `ads_posting_handoff.py`: shared package schema, hashes, copy normalization, integrity/slot validation and pending handoff.
- `ads_posting_page.py`: transactional one-time consumption, existing form hydration, exact product/URL mapping and source notice.
- `tests/test_ads_posting_handoff.py`: ten tests with matrices covering both sources and both types, including UI reruns and failure paths.
- `docs/ADS_POST_NOW_HANDOFF.md`: this report.

## Validation commands and results

The repository's `.venv` contains the required dependencies. Initial system-Python attempts could not run tests: `python -m pytest tests/test_posting_import_csv.py tests/test_ads_image_workflow.py tests/test_meta_carousel_posting.py -q --disable-warnings --maxfail=3` lacked pytest; `python -m unittest tests.test_posting_import_csv tests.test_ads_image_workflow tests.test_meta_carousel_posting -q` lacked Pillow/Streamlit. No dependencies were installed.

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_posting_import_csv tests.test_ads_image_workflow tests.test_meta_carousel_posting -q
```

An intermediate 101-test run caught an optional-description preservation regression. It was corrected; the final 111-test run below includes those same tests and passes.

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_ads_page tests.test_ads_creative_refresh tests.test_ads_instant_experience_footer tests.test_ads_image_workflow tests.test_ads_final_review tests.test_posting_import_csv tests.test_ads_posting_handoff tests.test_meta_posting tests.test_meta_carousel_posting tests.test_dropbox_integration tests.test_navigation_performance tests.test_sidebar_navigation_cleanup -q
```

589 tests ran in 152.295 seconds: 588 passed, one pre-existing failure. At this point the handoff suite contained seven tests; three further failure/history tests were added afterward.

The failure is `tests.test_ads_page.AdsPageTests.test_dropdown_options_are_in_required_order`: HEAD alphabetizes categories while that test expects an older custom order. It was independently reproduced with the unmodified HEAD `ads_page.py` loaded in memory, leaving working files unchanged:

```powershell
@'
import subprocess
import unittest
import ads_page
from tests.test_ads_page import AdsPageTests
baseline = subprocess.run(['git', 'show', 'HEAD:ads_page.py'], check=True, capture_output=True).stdout.decode('utf-8')
exec(compile(baseline, ads_page.__file__, 'exec'), ads_page.__dict__)
suite = unittest.TestSuite([AdsPageTests('test_dropdown_options_are_in_required_order')])
result = unittest.TextTestRunner(verbosity=1).run(suite)
raise SystemExit(not result.wasSuccessful())
'@ | .\.venv\Scripts\python.exe -
```

Result: the same one-test failure. Category ordering was not changed by this task.

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_ads_posting_handoff -q
```

Final standalone result: all 10 tests passed in 4.172 seconds. An intermediate test-file indentation mistake was corrected before this successful run.

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_ads_posting_handoff tests.test_posting_import_csv tests.test_ads_image_workflow tests.test_meta_carousel_posting -q
```

Final focused result after the last implementation changes: all 111 tests passed in 6.386 seconds.

```powershell
python -m py_compile ads_page.py ads_posting_page.py ads_posting_handoff.py
.\.venv\Scripts\python.exe -m py_compile ads_page.py ads_posting_page.py ads_posting_handoff.py tests/test_ads_posting_handoff.py
git diff --check
```

Compile checks passed, including every changed Python file in the final virtual-environment command. Diff whitespace checks passed.

## Remaining limits and assumptions

- This is a session-local handoff for newly saved packages. It does not restore a lost Streamlit session or retrieve an older Dropbox package. The existing manual/import paths remain available.
- All saved alternatives are retained, but active Posting controls and submission continue to use the existing supported fields and variation selection described above.
- Carousel Posting still requires a shared product URL and fixed Shop Now CTA. An incompatible saved card produces an explicit handoff error while preserving its successful Dropbox save.
- Posting-only product-set, audience, campaign/ad-set and other review choices still require the existing Posting review where not already available. No values are fabricated.
- Live Dropbox/Meta integration was not exercised, per the local-only instruction. The one unrelated baseline test failure remains.
- Nothing was pushed. Nothing was deployed. Render topology and production services were untouched.
