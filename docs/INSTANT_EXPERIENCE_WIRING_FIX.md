# Instant Experience active prompt wiring fix

Implemented locally, 16 September 2026. No commit, push, deployment or live Meta mutation.

## Confirmed runtime path and cause

Ads `render_page` Submit calls `build_ads_result_record`, which calls the public
`build_ads_prompt` entry point. New Instant Experience uses
`build_standard_instant_experience_prompt` and `compose_final_ads_prompt`.
The composed visual requirements render the grouped standalone image prompts
through the canonical renderer and `ads_ie_visual_systems`.
The result is stored in `ADS_RESULT_STATE_KEY`; `render_supported_result` passes
its `master_prompt` to `render_prompt_copy_button`, which serializes that exact
string into the clipboard JavaScript.

The new module was already called in this checkout. However,
`build_instant_experience_visual_output_requirements` still imposed the old
Right Angle / Straight On / Left Angle output order, and
`build_ads_text_first_image_generation_gate` still required the old three
Premium Scarcity routes. These later master instructions contradicted the new
standalone visuals. Also, `ensure_current_ads_result_prompt` trusted version
equality without checking content, allowing stale cached prompts to survive.
The complete reported V4-only output was not reproduced from a fresh local
build; the contradictory overrides and cache weakness were reproduced.

## Changes in this fix

- `ads_page.py`: replaced the final visual-order and text-first gate overrides,
  updated explicit image-generation examples, renamed the copy-diversity heading
  without changing copy behavior, and added a New IE wiring version plus cached
  content validation/rebuilding. Creative Refresh is excluded from this change.
- `ads_ie_visual_systems.py`: emit only the selected camera/room/wall/materials,
  include exact V1 visual-system titles, literal Gallery signature lines and an
  explicit full-height right graphic column for The Cave.
- `tests/test_ads_ie_prompt_integration.py`: seven integration tests covering
  the public builder, result record, real Streamlit Submit action, copy-button
  payload, actual clipboard serialization, stale-cache recovery, and preservation
  of completed copy and historical fingerprints.
- `tests/test_ads_page.py`: update the copy heading and replace old fixed-camera
  expectations with exactly three resolved camera selections.
- `tests/fixtures/carousel_detail_prompt_baseline.json` and
  `tests/fixtures/carousel_winner_unaffected.json`: update only standard New IE
  prompt hashes. Preserve Creative Refresh and other campaign baselines.
- This report: `docs/INSTANT_EXPERIENCE_WIRING_FIX.md`.

Other existing worktree changes are outside this wiring fix.

The objective, copy-set application, final image check, final termination and
fingerprint families already used the new formats in this checkout. The
three-image package instruction also names the three new formats;
integration tests reject the legacy three-angle package in the final master prompt. Internal
route keys and CSV schema remain unchanged. All three groups retain three rows:
`legacy_standard`, `framed_greatness`, `choose_a_side`.

## Manually rendered result

Rendered through `build_ads_result_record`, using Collector Cricket Print,
Cricket, Australia, verified edition limit 100 and token `integration`:

| Group | Internal slot | Visual family | Resolved camera |
| --- | --- | --- | --- |
| 1 | premium_scarcity_right | premium_scarcity_smart_hybrid | Slight left 4–7° |
| 2 | premium_scarcity_front | private_gallery | Straight gallery 0–2° |
| 3 | premium_scarcity_left | the_cave | Subtle three-quarter 7–10° |

Exactly one complete fixed-footer block appears, in Group 1. Group 2 contains
`SPORTS CAVE — PRIVATE GALLERY META AD SYSTEM V1` and
`FOR THE ROOM THAT REMEMBERS.` Group 3 contains
`SPORTS CAVE — THE CAVE META AD SYSTEM V1`, the stacked
`THE CAVE / STARTS / HERE.`, a full-height right graphic column, empty-cabinet
instruction and `LIMITED TO 100`, without a worldwide suffix. Groups 2 and 3
contain no Premium Scarcity footer contract. Each group contains one resolved
camera rather than a camera menu.

## Validation

The new integration test failed before the fix on the legacy controlling text.
After the fix, all seven integration tests and seven visual-system tests pass.
Together with the two updated Ads camera tests: **16 tests passed in 5.270s**.

The combined IE, image workflow, import/export, Creative Refresh, Carousel and
shared prompt suite ran **187 tests in 18.188s**. Its only failures were four
subcases of the pre-existing captured-byte test
`test_unaffected_prompts_match_captured_prechange_bytes`, for Creative Refresh
Instant Experience (Motorsport, Football, Cricket, NBA). Their baselines were
not rewritten to conceal those mismatches.

The same combined suite excluding that one known failing captured-byte test
passed: **186 tests in 17.827s**. Python compilation and `git diff --check` passed.

Final full Ads-page run: **193 tests in 123.039s, 191 passed, 2 failed**.
The remaining failures are outside this fix:
`test_dropdown_options_are_in_required_order` expects a different category order,
and `test_generated_prompt_contains_required_dynamic_and_rule_text` expects an
old Carousel specificity sentence replaced by the earlier Carousel upgrade.
All Instant Experience Ads-page tests passed, including CSV import/export.
