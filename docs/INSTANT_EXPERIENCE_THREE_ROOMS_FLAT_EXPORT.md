# Instant Experience: three premium rooms and flat export

Local review change only. No commit, push, deployment or live API changes.

## Prompt construction

The New Ads Instant Experience path is `build_ads_result_record` → `build_ads_prompt` → `build_standard_instant_experience_prompt`. Its grouped output resolves visuals with `resolve_standard_instant_experience_visuals` and renders each standalone image prompt through `build_instant_experience_canonical_prompt_v4` in `ads_page.py`.

`ads_ie_visual_systems.py` now resolves three rooms in the same premium campaign family:

| Image | Camera | Room and furnishings |
| --- | --- | --- |
| 1 | Right | Warm taupe plaster collector lounge, walnut console, cognac leather sofa |
| 2 | Centre / straight-on | Smoked bronze plaster home office, oak desk, upholstered desk chair |
| 3 | Left | Dark stone-plaster architectural collector den, asymmetric timber credenza, leather club chair |

Furniture, wall treatment, architecture, light direction and composition differ across the three. The artwork stays unchanged; mirroring and cloned rooms are prohibited.

All three use the shared opaque full-width black/gold bottom-banner contract: upper room 72–76%, banner 24–28%, thin gold divider, ivory type, gold edition number and CTA. For a verified 100-edition product, the exact wording is:

```
ONLY 100 WILL EVER EXIST
Once they’re claimed, this edition retires forever.
CLAIM YOUR EDITION
```

Existing factual validation remains: other verified limits use their actual number; missing limits do not invent 100. Geographic scope is prohibited in image scarcity copy. Product fidelity, frame, glazing and physical shadows retain the shared quality rules.

The objective, text-first gate, grouped output, sibling checks, CTA image rules, final output requirements and cached-prompt validation now agree with this contract. New Ads still requests three copy combinations, one Description, Headline and CTA per group. Copy seeds, selection patterns, historical compatibility and CSV schema remain intact. Creative Refresh winner-refinement copy and its winner-specific prompt remain intact. Carousel and other campaign prompts are unchanged.

## Output paths

`_instant_experience_package_items`, `_meta_output_filename`, `_instant_experience_current_copy_csv_filename` and `build_ads_notes_filename` in `ads_page.py` supply the flat Instant Experience package. The existing Dropbox batch-save path consumes these relative filenames under the existing single ad-set parent.

Previously each creative used its own folder with an image, `ad-copy.txt`, and nested description folders containing primary text and headline files. Now every file sits directly in the parent:

```
01-premium-scarcity-right.png
02-premium-scarcity-front.png
03-premium-scarcity-left.png
ad_copy.csv
notes.txt
01-premium-scarcity-right-ad-copy.txt
01-premium-scarcity-right--01-legacy-standard--primary-text.txt
01-premium-scarcity-right--01-legacy-standard--headline.txt
...equivalent unique copy files for slots 2 and 3
```

Historical multi-row copy exports retain their extra text files with unique flat names. `prepare_instant_experience_package_png` in `ads_image_workflow.py` encodes actual full-resolution PNG bytes; it does not merely rename JPEGs. Notes list the actual image filenames and room/camera/banner assignments. Existing remote folders are not deleted or migrated.

## Validation

The public Ads entry point and Submit/clipboard UI are covered, along with stale cached-prompt rebuilding. Tests check all three exact banners, cameras, distinct rooms, product fidelity, one copy set per creative, legacy copy-history compatibility, CSV import/export, real PNG bytes, flat filenames, notes, unique ZIP entries, unchanged text bytes, caching and partial-save errors.

Validation results:

- Focused public prompt / visual / footer / export / copy suites: 61 passed.
- Creative Refresh suite, final run: 61 passed.
- Wider Ads / copy / Creative Refresh / winner refinement / Posting handoff / review / URL suite: 320 tests, initially 316 passed and four failed. One new banner test lacked verified edition metadata; its fixture was corrected and the complete 61-test Creative Refresh suite then passed. The remaining three failures reproduce with the unmodified HEAD runtime modules: category order, a Carousel wording assertion, and missing-product-URL fallback. Their unrelated behavior was not changed.
- All 11 changed Python files compiled successfully.
- `git diff --check` passed.

Commands: `.venv\Scripts\python.exe -m unittest` with the module groups listed above; `.venv\Scripts\python.exe -m py_compile` for all changed Python files. Tests used mocked save/handoff boundaries; no live upload or Meta write was performed.

Manual text review: `output/reviews/instant-experience-three-rooms-prompt.txt` contains a resolved Peter Brock example. This validates the prompt instructions; no ad images were generated.

## Exact files changed

- `ads_page.py`
- `ads_ie_visual_systems.py`
- `ads_ie_copy.py`
- `ads_image_workflow.py`
- `tests/test_ads_ie_prompt_integration.py`
- `tests/test_ads_ie_visual_systems.py`
- `tests/test_ads_instant_experience_footer.py`
- `tests/test_ads_image_workflow.py`
- `tests/test_ads_ie_copy_v2.py`
- `tests/test_ads_page.py`
- `tests/test_ads_creative_refresh.py`
- `docs/INSTANT_EXPERIENCE_THREE_ROOMS_FLAT_EXPORT.md`

Posting, Meta Review, Orders, Mockups, Product Uploads, Supabase and unrelated pages have no source changes.
