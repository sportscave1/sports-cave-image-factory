# Carousel Card 1 and Card 5 prompt repair

## Scope and implementation found

This repair applies to **New Ads > Carousel** image prompts only. The existing `build_ads_prompt` pipeline assembles the visual contract through `compose_final_ads_prompt`, `apply_campaign_visual_output_contract`, `build_campaign_visual_output_contract`, `build_carousel_visual_output_requirements` and `build_carousel_image_prompt_schema`. The existing selected `category` value is already available throughout that pipeline.

Card 1 reused the Mockups close-up foundation, but its Carousel adapter replaced the slight angle with an almost straight-on, optional 2–4 degree view. Its wall directions were generic rather than deterministic by sport. Card 5 used a generic product-prominent scarcity composition without a magnifying glass.

The application already shares product, frame/glass and realism helpers in `ads_page.py`, plus the authoritative image realism block in `sports_cave_prompt_blocks.py`. The repair extends that architecture. It does not change the shared master block or the underlying Mockups foundation.

## Result

- **Card 1:** mandatory subtle 5–12 degree off-axis / slight three-quarter view, all outer frame edges visible, rigid rectangular product perspective, genuine transparent glazing, restrained reflections and glare, realistic wall contact and directional shadows, ambient occlusion, and exact source artwork/frame protection. Fake white streaks and CGI shine are prohibited.
- **Sport treatment:** a deterministic lookup covers the existing sport taxonomy, reuses the existing label normalisation helper, and handles common aliases and case/punctuation differences. Cricket resolves to muted heritage pavilion green; Basketball/NBA resolves to muted vintage hardwood tan. Unknown or empty categories resolve to muted gallery taupe. All directions require matte painted/plaster finishes, restrained saturation and no added team branding. No new selector or manual colour input was added.
- **Card 5:** a physical magnifying glass with clear lens, metal rim, handle, reflections and plausible shadows highlights an actual visible edition detail. A numbered edition plate takes priority over a collector badge. Only modest optical magnification inside the lens is permitted; the source product remains unchanged. The prompt forbids fake text, fabricated or changed edition numbers, invented scarcity, new badges/logos, overlays and watermarks. It requires realistic artwork glazing and lens reflections, source frame geometry/materials, a clean wall and no people, furniture, decor or other props. If no genuine edition detail is readable, the prompt requests a source showing it rather than inventing one.
- **Preservation:** Cards 2–4 retain their original assembled prompt strings. Creative Refresh is explicitly routed through its previous prompt behavior. Instant Experience and single-image prompts remain unchanged. Card order, permanent image slots, CSV, save/package structure and posting/handoff implementation were not edited in this repair.
- **Existing sessions:** a New Ads Carousel-specific prompt version refreshes stale master prompts through the existing result-refresh mechanism without replacing completed ad copy or its context. Applying the current contract again is idempotent.

## Files

- `ads_page.py`: scoped prompt changes and workflow-mode propagation.
- `tests/test_ads_page.py`: update three existing Card 1/Card 5 expectations.
- `tests/test_carousel_detail_prompts.py`: nine focused tests of final assembled prompts, taxonomy aliases/fallback, all-category/market preservation, shared realism, slot order, version refresh and idempotence.
- `tests/fixtures/carousel_detail_prompt_baseline.json`: 28 pre-change SHA-256 expectations for unaffected card sections and complete campaign prompts across four sport/market cases.
- This report.

Temporary prompt-review files and the source snapshot created during the task were removed after inspection. An external commit appeared during the task and had included those temporary files; this task did not run Git commit, push or deployment commands.

## Validation

All commands ran locally using the repository virtual environment. Final assembled Card 1 and Card 5 strings were inspected, including Cricket, NBA and unknown-sport outputs. No generated images were requested, so image-model adherence still needs a visual UI check.

Compilation passed:

```powershell
.\.venv\Scripts\python.exe -m py_compile ads_page.py tests/test_ads_page.py tests/test_carousel_detail_prompts.py
```

The final focused/regression run passed **123 tests**:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_carousel_detail_prompts tests.test_ads_page.AdsPageTests.test_carousel_card_one_uses_mockups_close_up_foundation_with_close_lock_only tests.test_ads_page.AdsPageTests.test_carousel_card_distance_rules_keep_products_dominant tests.test_ads_page.AdsPageTests.test_every_carousel_card_prompt_has_strict_product_lock_and_photorealism tests.test_ads_image_workflow tests.test_posting_import_csv tests.test_ads_posting_handoff tests.test_meta_carousel_posting -q
```

The broader run passed **617 of 618 tests**:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_carousel_detail_prompts tests.test_ads_page tests.test_ads_creative_refresh tests.test_ads_instant_experience_footer tests.test_ads_image_workflow tests.test_ads_final_review tests.test_posting_import_csv tests.test_ads_posting_handoff tests.test_meta_posting tests.test_meta_carousel_posting tests.test_dropbox_integration tests.test_navigation_performance tests.test_sidebar_navigation_cleanup tests.test_sports_cave_prompt_blocks tests.test_mockup_reels -q
```

The sole failure was the previously identified baseline failure `tests.test_ads_page.AdsPageTests.test_dropdown_options_are_in_required_order`: the current category list is alphabetised while the test expects the older order. Category ordering was not changed. The final focused run above includes two additional focused tests and the final minor prompt wording fixes added after the broader run.

`git diff --check` passed.

## Delivery

No ad was posted or uploaded, no live Meta write was performed, and this task made no Git commit, push or deployment. The repair is ready to test in the Sports Cave OS UI **running this local checkout**. Hosted behavior requires a separate deployment, which this task did not perform. Test Card 1 with Cricket and Basketball/NBA to compare wall treatments, and Card 5 with a source containing a readable numbered plate; inspect source-text fidelity, frame geometry and lens placement in the generated results.
