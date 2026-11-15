# Distinct fan rooms and banner support lines

Local-only Instant Experience correction. No commit, push, deployment or live data changes.

## Active path and cause

New Ads uses `build_ads_prompt` / `build_standard_instant_experience_prompt`, then `resolve_standard_instant_experience_visuals`, then `build_instant_experience_canonical_prompt_v4` in `ads_page.py`.

The previous resolver replaced product-aware room selection with a fixed, similar set of rooms. The shared canonical prompt explicitly said to use identical banner wording on all three images. It also imposed the same 82–88% artwork width, leaving little environment visible. A shared rejection gate rejected another route's CTA even though all three are allowed to share CLAIM YOUR EDITION. The New Ads description template also emitted sport-specific collector labels.

## Corrected contract

| Slot / filename stem | Room | Camera | Artwork width | Supporting line |
| --- | --- | --- | --- | --- |
| 01-premium-scarcity-right | Residential hallway / gallery corridor | Right diagonal | 72–78% | Once they’re claimed, this edition retires forever. |
| 02-premium-scarcity-front | Man cave / home office / collector den | Centre/front | 78–84% | Made for serious collectors. |
| 03-premium-scarcity-left | Private home bar / lounge / entertaining corner | Left diagonal | 70–76% | For collectors who know why it matters. |

Each has distinct wall treatment, furniture arrangement, architectural cue, lighting and framing. The hallway has passage depth and gallery lighting; the office has a desk and task lighting; the bar/lounge has a drinks cabinet, social seating and moody pendant lighting. The supplied artwork remains the largest visual element, complete and unchanged.

The full-width opaque black/gold banner, 24–28% height, gold divider, premium typography and CLAIM YOUR EDITION remain common. The resolved support line is unique per slot. Existing verified-edition handling remains; unknown limits use safe non-numeric wording rather than inventing a quantity.

The variant-precedence block makes the assigned room, camera and supporting line authoritative over generic lifestyle suggestions. Sibling metadata is explicitly comparison data, never permission to blend scenes. Late package checks agree with the three room assignments and distinct supporting lines. The rendered version marker uses the current resolver version so stale cached prompts refresh once.

## Product-aware styling

`ads_ie_visual_systems.py` resolves aesthetic profiles for racing, social/team sports, basketball, baseball, horse racing, cricket and a neutral fallback. These change wall colours, furniture timber, metal finishes and atmosphere while retaining the fixed room roles.

Racing uses smoked walnut, graphite/bronze/tobacco walls and precision metal accents. Basketball uses cleaner urban styling, light smoked oak, microcement and satin-black details. Cricket uses honey oak and understated study character; baseball uses classic walnut and heritage warmth; horse racing uses polished tailored finishes. Supplied historic/legend context adds timeless silhouettes and patina; modern context adds sharper detailing. Supplied team context supports a tasteful supporter atmosphere without merchandise overload. These are visual directions, not demographic claims or new product facts.

The active New Ads copy template now says Made for collectors. Sport-specific identity and product facts remain available, but collector labels are neutral.

## Creative Refresh and exports

Creative Refresh currently uses its separate `build_instant_experience_winner_refinement_prompt`; it does not call this three-room generator. Its winner-refinement prompt remains byte-for-byte unchanged, verified by the existing baseline test. Every caller of the shared standard Instant Experience generator receives the correction.

Flat exports are unchanged: the three PNGs, ad_copy.csv, notes.txt and existing uniquely named copy files remain directly inside the existing ad-set folder. No export, folder, upload, Posting, Meta Review, Orders, Mockups, Shopify, Supabase or Product Upload implementation changed.

## Validation

The tests exercise the actual public prompt and Submit/clipboard boundary, not only the resolver. They check room roles, angles, unique support lines, neutral collector labels, same CTA, distinct framing, fan profiles across six sports, era/team adaptation, stale-cache rebuilding, fidelity, CSV/export and Posting handoff. Updated image snapshots reflect this requested visual change; the Creative Refresh snapshot is unchanged.

Validation results:

- 97 targeted public prompt, visual, legacy-copy, footer, export, winner-refinement and Posting-handoff tests passed.
- Eight visual-system tests passed again after adding distinct framing assertions.
- Wider Ads page / Creative Refresh / final review run: 275 tests, 267 passed and eight failed. Five assertions still expected prior wording or room instructions; updated all five and reran them successfully.
- Remaining three failures also reproduce against unchanged HEAD runtime modules: category order, an existing Carousel product-anchor wording assertion, and product URL fallback. Their unrelated behavior was not changed.
- Changed Python files compile and git diff --check passes.

The commands used `.venv\Scripts\python.exe -m unittest` for the named module groups, `.venv\Scripts\python.exe -m py_compile` for changed Python files, and `git diff --check`. All save and handoff checks used mocked boundaries.

Manually inspected resolved Motorsport and NBA examples:

- `output/reviews/fan-rooms-motorsport.txt`
- `output/reviews/fan-rooms-nba.txt`

No image generation or live uploads were performed; validation inspected the rendered instructions and mocked export/handoff behavior.

## Exact files changed

- `ads_ie_visual_systems.py`
- `ads_page.py`
- `ads_ie_legacy_description.py`
- `tests/test_ads_ie_prompt_integration.py`
- `tests/test_ads_ie_visual_systems.py`
- `tests/test_ads_ie_locked_legacy_copy.py`
- `tests/test_ads_page.py`
- `tests/test_ads_creative_refresh.py`
- `tests/fixtures/ie_locked_copy_scope_baseline.json`
- `docs/INSTANT_EXPERIENCE_DISTINCT_FAN_ROOMS.md`
