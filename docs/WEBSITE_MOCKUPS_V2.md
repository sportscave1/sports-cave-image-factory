# Website Mockups V2 — local implementation report

1. **Architecture found.** `app.py` renders Mockups and manages result/session state, upload cards and save/export controls. `image_factory.py` defines 17 legacy lifestyle prompts, the three permanent product-gallery room slots and the working image conversion/filename/export pipeline. Prompt overrides are available through `prompt_store`; local reads are used for the new brief. The gallery order remains Black Framed, three lifestyle slots, Size Guide, Oak Framed, White Framed and Unframed.

2. **Master rules preserved.** The exact `build_sports_cave_image_realism_rules()` output is retained, including the full global photographic realism and product/mockup lock blocks. These cover original full-resolution source fidelity, rigid frame geometry, glass, mounting, lighting, room realism, prominence, dimensions and final inspection. `sports_cave_prompt_blocks.py` was not changed. All 17 original prompt bodies remain unchanged for other consumers and historical compatibility.

3. **Existing room prompts reused.** The new assembler reuses the detailed Man Cave, Office, Living Room, Premium Home Sports Bar, Collector Display Room, Luxury Entry Statement Wall, Private Club Lounge / Collector Retreat, Luxury Fireplace Feature Wall, Premium Bedroom / Private Retreat, Premium Tool Shed / Workshop, Man Cave With Pool Table and Architectural Loft / Statement Wall presets. Only their assembled website copies adapt obsolete ad-purpose and previous-generated-image instructions. Room geometry, lighting, materials and product safeguards remain. Pool-table duplicates are consolidated; The Wall Upgrade Moment is an installation concept rather than a room and remains available only in the unchanged legacy definitions.

4. **Files changed in this task.** `app.py`, `image_factory.py`, new `website_mockups.py`, `tests/test_mockup_prompt_preview.py`, `tests/test_mockup_eight_image_manifest.py`, new `tests/test_website_mockups.py`, new `tests/fixtures/website_mockups_baseline.json`, this report and `docs/WEBSITE_MOCKUPS_CRICKET_EXAMPLE.txt`. Pre-existing Carousel changes in the working tree were not edited by this task.

5. **Design Type source.** The dropdown calls `design_studio_styles.style_labels()` directly and uses its normaliser/registry. Current options: Ultimate Moment; Rivalry Face-Off; Legends Jersey Display; Nostalgic Tribute; Motorsport: Driver & Car; Minimalist Hero; Championship / Achievement; Vintage Restoration; Update Existing Design. No Design Studio source was modified. Even Update Existing Design is explicitly environment context only.

6. **Era options.** Pre-1950; 1950-1969; 1970-1979; 1980-1989; 1990-1999; 2000-2009; 2010-2019; 2020-Present; Timeless / Multiple Eras; Not Sure.

7. **Full room library.** There are 33 selectable presets; see the table below. Familiar equivalent names resolve to the same preset rather than adding duplicate options: Office → Home Office, Home Sports Bar → Premium Home Sports Bar, Entry Statement Wall → Luxury Entry Statement Wall, Private Club Lounge / Collector Retreat → Clubhouse-Inspired Lounge, Architectural Loft / Statement Wall → Industrial Loft, and the two pool-table names → Man Cave with Pool Table.

8. **Room families.** Entertainment, bar/social, living, work/study, collector, garage/workshop, architectural and fitness metadata are internal only. The UI shows room names without family controls.

9. **Best 3 logic.** A deterministic local score combines design-type preferences, sport preferences, era material cues and useful product-title heritage words. Stable tie-breaking and one selection per family yield exactly three unique, different-family defaults. No external AI or recommendation API is called.

10. **Cricket example.** Cricket + Nostalgic Tribute + 1990-1999 recommends **Study / Library**, **Clubhouse-Inspired Lounge**, **Heritage Living Room**, in that order. Their wall treatments are muted pavilion green, warm heritage clubhouse cream and deep charcoal-green. The complete assembled example is saved beside this report and was inspected.

11. **Manual overrides.** All three selectors contain the full room library. Changing Design Type/Era updates draft recommendations; users can then choose any rooms. Submission rejects duplicate exact rooms, including equivalent aliases.

12. **Master assembly.** The assembler combines unchanged authoritative rules, product/sport, design/era environment guidance, the three selected room presets, three assigned home/palette/camera treatments and a final execution/inspection contract. A submitted snapshot stores these values and the exact assembled prompt. Reruns use the stored prompt, including if a cached source template later changes.

13. **Sequential ChatGPT generation.** One Copy Master Prompt button copies the locked brief. ChatGPT is instructed to generate Mockup 1 first and wait, then respond to “Generate Mockup 2” and “Generate Mockup 3” with the corresponding locked briefs. Collages, simultaneous generation and silent substitution/reordering are forbidden.

14. **Sport intelligence.** Muted palette families cover the existing Mockups sports and common aliases, plus golf, combat and horse racing. Unknown sports use premium neutral tones. Each output receives a different complementary wall treatment. Team-colour copying, invented logos, slogans and themed clutter are forbidden.

15. **Era intelligence.** The selected period affects timber, upholstery, finish, architectural familiarity and lighting warmth. All outputs remain present-day premium homes; no literal historical movie sets are requested.

16. **Design-type intelligence.** Local presentation metadata expresses heritage warmth, minimalist architecture, confident achievement, rivalry contrast, collector display, dramatic moment placement or motorsport precision. It never grants permission to redesign the artwork.

17. **Different homes.** Each brief assigns a different room plan, ceiling treatment, window/light source, floor treatment, furniture arrangement, wall finish and camera composition. The master explicitly rejects merely changing cushions, a lamp or wall colour in the same property. Room-specific architectural feasibility takes precedence over an incompatible generic example.

18. **Three upload cards.** After submission, exactly three lifestyle uploaders render in the existing three-column component. The unchanged source-artwork uploader remains above them on the full page. Individual prompt-copy/edit controls are replaced by the single master-copy button for the submitted brief.

19. **Permanent order and snapshot safety.** Submitted order is never alphabetised. Existing three storage slot IDs are retained; their displayed names, filename variants and image metadata come from the snapshot. Upload/lifecycle keys include the snapshot ID. Draft edits do not change active cards or uploaded associations. Resubmission starts empty active cards, records prior associations and leaves prior source files in place. An in-progress upload prevents resubmission, and stale upload callbacks cannot attach to a newer brief.

20. **Filename format unchanged.** No replacement filename generator was introduced. The existing saver accepts an optional selected room variant; its existing product/sport prefix, separators, extension and directory construction remain unchanged. Known room variants retain their established spelling. New variants use the existing `image_factory.slugify` function.

21. **Filename regression results.** Known Product + Man Cave/Office/Living Room cases produce the same paths using either the legacy call or new room metadata. Reordered dynamic rooms produce matching upload, gallery-manifest, ZIP and Dropbox-manifest names while retaining gallery positions 2–4. ZIP numbering/order and package/folder naming were not redesigned.

22. **Save/export preservation.** Existing upload validation, image processing, WebP/JPEG conversion, previews, export-folder rebuilding, ZIP creation and Dropbox save functions are reused. Tests exercise real local image conversion and archive creation and inspect ordered manifests. No live Dropbox call was required. Historical prompt files/packages are not migrated or renamed; the fixed historical grid is no longer displayed.

23. **Top workflow unchanged.** Product Name, Sport, source upload/validation, the five core Black/Oak/White/Unframed/Size Guide images, preview and Load Full Resolution remain functionally unchanged. New core runs wait for brief submission instead of preparing 17 lifestyle prompts. Pre-change hashes protect core generation, preview, validation and export functions.

24. **Ads separation.** Close-Up Premium Wall Shot, Limited Edition Detail Shot and Instant Experience Cover Banner are absent from the new Mockups UI. Their shared/legacy definitions remain intact. Ads, Carousel, Instant Experience, Creative Refresh, Posting, POST NOW, Design Studio and Product Uploads were not edited.

25. **Tests.** Added 17 focused tests covering taxonomy, eras, all-context deterministic/family-diverse recommendations, aliases/fallback, overrides, duplicate rejection, final prompt content, immutable shared rules, local-only template loading, filenames/WebP, order/export manifests, snapshot restoration, resubmission/stale uploads and actual Streamlit widget interactions. Updated existing fixed-grid and uploader-key expectations to the three-card workflow. The baseline fixture captures all 17 legacy prompt bodies, the authoritative master and 18 protected functions.

26. **Validation.** The broader regression run passed **409 tests**. After the final mixed-Path/string stale-upload guard adjustment, the focused website/upload rerun passed **27 tests**. All six changed Python files compiled, and `git diff --check` passed. Commands are below. Tests blocked socket connections and made no external API calls. The manual quality check assembled and inspected the Cricket prompt; no AI images were generated.

27. **Delivery.** This task made no Git commit, push or deployment, no live Shopify changes and no Meta post. Work stopped at local implementation and testing.

28. **UI readiness.** Ready to test in Sports Cave OS running this checkout. Generate/select the existing product assets, choose Design Type/Era, review the three rooms, create the brief and copy it into ChatGPT with the full-resolution product. Inspect generated artwork fidelity and home diversity before uploading results. Hosted behavior has not been updated by this task.

## Room library

| Internal family | Available rooms |
| --- | --- |
| Entertainment | Man Cave; Man Cave with Pool Table; Premium Man Cave; Games Room; Entertainment Room; Media Room / Home Theatre; Basement Sports Lounge |
| Bar / social | Premium Home Sports Bar; Clubhouse-Inspired Lounge |
| Collector | Collector Display Room; Collector Lounge |
| Living | Living Room; Modern Living Room; Heritage Living Room; Premium Family Living Room; Apartment Living Room; Luxury Fireplace Feature Wall; Premium Bedroom / Private Retreat |
| Work / study | Home Office; Executive Office; Study / Library |
| Garage / workshop | Garage; Collector Garage; Luxury Garage; Premium Tool Shed / Workshop |
| Architectural | Luxury Entry Statement Wall; Hallway Gallery Wall; Staircase / Landing Gallery; Industrial Loft; Premium Apartment; Contemporary Architectural Home; Heritage Character Home |
| Fitness | Home Gym |

## Commands

Compilation:

```powershell
.\.venv\Scripts\python.exe -m py_compile app.py image_factory.py website_mockups.py tests/test_website_mockups.py tests/test_mockup_prompt_preview.py tests/test_mockup_eight_image_manifest.py
git diff --check
```

The 409-test run used this local runner to prohibit network access. The temporary Streamlit form reset isolates `app.main()`'s bare-import login state in tests only; production authentication was not changed.

```powershell
@'
import socket, unittest
from unittest import mock
names = ['tests.test_website_mockups', 'tests.test_mockup_prompt_preview', 'tests.test_mockup_eight_image_manifest', 'tests.test_mockup_memory_pipeline', 'tests.test_mockup_second_image_upload', 'tests.test_mockup_reels', 'tests.test_sports_cave_prompt_blocks', 'tests.test_carousel_detail_prompts', 'tests.test_ads_image_workflow', 'tests.test_ads_posting_handoff', 'tests.test_posting_import_csv', 'tests.test_meta_carousel_posting', 'tests.test_ads_creative_refresh', 'tests.test_ads_instant_experience_footer', 'tests.test_design_studio_type_contracts', 'tests.test_design_studio_v2', 'tests.test_product_upload_prompts', 'tests.test_navigation_performance']
suite = unittest.defaultTestLoader.loadTestsFromNames(names)
import streamlit as st
with mock.patch.object(st._main, '_form_data', None), mock.patch.object(socket.socket, 'connect', side_effect=AssertionError('External network blocked during local tests')):
    result = unittest.TextTestRunner(verbosity=1).run(suite)
raise SystemExit(not result.wasSuccessful())
'@ | .\.venv\Scripts\python.exe -
```

The final focused run used the same runner with `names = ['tests.test_website_mockups', 'tests.test_mockup_second_image_upload']`.
