# Carousel winner prompt upgrade

Implemented locally on 2026-09-16. No commit, push, deployment, ad posting or live Meta changes.

## Source of truth and scope

The Ads inputs feed `build_ads_prompt` in `ads_page.py`. Its generic/Motorsport copy templates are composed through `compose_final_ads_prompt`; image prompts are composed through `build_campaign_visual_output_contract`, `build_carousel_visual_output_requirements` and `build_carousel_image_prompt_schema`.

The previous shared copy strategy assigned display desire to Card 2, collector appeal to Card 3 and emotional meaning to Card 4. Card 1 used a fixed sport-nostalgic wall tone; standard Card 5 used the magnifying-glass edition-detail helper. Cards 2–4 relied on prose variation instructions instead of an explicit coordinated room set.

The new `ads_carousel_winner.py` provides reusable winner-copy instructions, verified preferred fields and a deterministic scene resolver. `ads_page.py` applies them only to new Carousel campaigns. Existing product inputs, edition parsing, boolean parsing and copy validation are reused. The old copy/detail helpers remain available for historical uses, and Creative Refresh continues through its existing contracts.

## Five-card copy sequence

1. **Product Identity:** strongest short verified identity, with generic artwork suffixes removed; prefer `Limited Edition` only when verified. An overlong identity remains for the model to shorten truthfully, never by cutting a word.
2. **Moment / Legacy:** supported fan identity and an appropriate memory response. Current subjects must not receive invented historical context.
3. **Emotional Hook:** a different defining product-specific anchor supported by the supplied facts.
4. **Fan Ownership:** default headline `For The Cave`, paired with a supported product cue or safe ownership alternative.
5. **Scarcity:** prefer `Only N Made` when verified and within 17 characters. `Numbered Run` requires explicit numbering evidence; otherwise use a supported alternative. Unknown limits do not default to 100, including for Baseball.

All existing Python `len()`-based 17-character limits, punctuation restrictions, duplicate-line checks, factual gates, localisation, five Primary Text variants and `Claim Your Edition` CTA remain. Existing generic role labels and Motorsport aliases remain intact. The app still builds instructions for the existing ChatGPT workflow; it does not call a new copy-generation service.

## Visual system

Card 1 retains its close-up foundation: approximately 65–80% useful composition, full outer frame, no furniture, narrow wall context, slight photography angle, glazing, reflections and mounting shadows. Its low-saturation wall is now resolved using product/sport/market/context and the variation token, with an explicit instruction to check actual artwork palette, brightness and frame separation before returning the standalone prompt.

The room pool contains 20 families:

- Premium Man Cave / Sports Cave
- Executive Home Office
- Premium Residential Home Bar
- Games / Pool Table Room
- Collector Lounge
- Media Room
- Heritage Study / Library
- Modern Study
- Finished Basement Sports Lounge
- Premium Adult Fan Bedroom
- Home Gym
- Garage Lounge
- Workshop / Garage Office
- Private Clubhouse Lounge
- Home Theater
- Entry / Hall Gallery
- Loft / Industrial Den
- Modern Penthouse Lounge
- Enclosed Pavilion / Veranda Clubroom
- Locker-Inspired Private Sports Room

Cards 2–5 select four unique families and distinct principal architecture, furniture, wall, camera, lighting and placement. Selection limits closely related lounge environments so the result does not become four versions of the same lounge. Two walls are lighter and two darker. Card 4 is always `sports_cave`, with varying architecture, furniture arrangement, camera and lighting.

At most one additional sport-specific environment is selected from the supplied sport and its established aliases. Examples include pavilion/clubroom for Cricket, garage/workshop for Motorsport and locker/gym for Basketball. No team identity is inferred from image appearance. Prompts prohibit invented logos, player names, vehicles, official club branding and memorabilia.

Each package uses its existing Creative Variation Token, product, sport, market, supplied visual metadata and campaign context as a deterministic seed. Card-level cues use the card number. Repeating inputs repeats the scene set; changing the token varies the campaign without changing facts. Every prompt contains resolved scene fields and a visual fingerprint. The existing LAST-IMAGE VARIATION LOCK remains and can use previous visible images to refine architecture/furniture/light while retaining Card 4's cave family.

Card 5 now uses the fourth distinct lifestyle room with approximately 45–65% product prominence and a stronger collector composition. Genuine edition details remain untouched and readable through composition/light. There is no default magnifier or requirement to supply an edition-detail asset. Meta copy carries scarcity; the image does not add advertising text.

## Compatibility and files

No CSV schema, headers, row types/order, slot IDs, card positions, import/export implementation, UI workflow, product selection or URL handling changed. Meta URL parameters remain exact. Standard Carousel prompt version advances to `CAROUSEL WINNER AND FOUR ENVIRONMENTS V2` through the existing cached-prompt refresh mechanism.

Files changed for this task:

- `ads_page.py`
- `ads_carousel_winner.py` — new
- `tests/test_ads_page.py`
- `tests/test_carousel_detail_prompts.py`
- `tests/test_carousel_winner_system.py` — new
- `tests/fixtures/carousel_detail_prompt_baseline.json` — standard Carousel card snapshots only in this task
- `tests/fixtures/carousel_winner_unaffected.json` — new pre-upgrade compatibility hashes
- This report

Earlier Instant Experience work and existing Edition Ops/Shopify/Supabase changes were retained. No unrelated source files were edited in this task.

## Validation

Used `.venv/Scripts/python.exe` with unittest.

- **13 new regression tests passed**, covering preferred copy, length limits, numbering/edition evidence, identity handling, connected roles, 132 sport/token scene combinations, sport aliases, determinism/freshness, all five product/realism blocks, example isolation and unaffected-campaign snapshots.
- **51 selected Ads-page tests passed** in 19.198s, including Carousel prompts, copy validators, CSV handling and relevant UI/image behavior.
- **102 tests ran** in the final combined winner, detail-prompt, image-workflow, posting CSV/import and shared-realism suite in 2.115s. The only failures were four already-known subcases of `test_unaffected_prompts_match_captured_prechange_bytes`: Creative Refresh Instant Experience for Motorsport, Football, Cricket and NBA. These stale fixture failures were present before this task; they were not updated as part of the Carousel change. All other tests in that run passed.
- **20 non-target prompts match pre-upgrade bytes**, enforced by the new compatibility fixture: Instant Experience, Single Image and Creative Refresh across five sports.
- Confirmed all **20 room families** are reachable.
- Python compilation passed for all five changed/new Python files.
- `git diff --check` passed.

Inspected a generic Cricket package with verified edition limit 100. Its five image scenes resolve to: close-up hero, enclosed pavilion, media room, Sports Cave and games room. Cards 2–5 have four unique walls, cameras, lighting treatments and principal furniture arrangements. Every image prompt retains product/realism protections; no default prompt contains magnifying-glass instructions or the retired Card 5 detail rules.

Validation covers prompt text and application behavior. No images were generated and no external ad operation was performed.
