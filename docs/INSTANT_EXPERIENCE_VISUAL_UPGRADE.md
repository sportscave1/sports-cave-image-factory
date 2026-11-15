# Instant Experience image prompt upgrade

Implemented locally on 2026-09-16. No commit, push, deployment, or live Meta changes.

## Architecture and compatibility

`ads_page.py` builds the standard master prompt from the selected product/campaign context, resolves three visual slots, renders each standalone image prompt and its three-row copy table, and retains the existing shared setup block. Previously every slot used the Premium Scarcity renderer, a fixed right/front/left camera and the same opaque footer.

The existing product context and edition-limit resolver remain authoritative. The new `ads_ie_visual_systems.py` adds visual selection and the two editorial layouts; it does not look up products or edition limits independently. The existing app-wide product/realism block appears once per standalone image prompt.

Internal `premium_scarcity_right`, `premium_scarcity_front`, and `premium_scarcity_left` identifiers, upload slots, filenames, folder names, CSV labels/schema, description keys, nine copy rows, URL handling and Meta UTM parameters remain unchanged. Existing UI labels are retained for compatibility. Generated prompt group headings identify the new formats. The standard prompt version advances to V9 so cached prompts can refresh through the existing mechanism.

## Visual slots

1. **Premium Scarcity — Smart Hybrid:** retains the original 21–23% opaque footer, typography, resolved headline/supporting line/CTA, gold separator, copy-fit and quality contracts. Room selection uses existing product-aware weights; camera and wall choices now vary.
2. **Private Gallery:** dominant collectible artwork, quiet gallery setting, small branding, `FOR THE ROOM THAT REMEMBERS.`, verified `LIMITED TO n`, no scarcity footer or on-image CTA.
3. **The Cave:** left 66–68% photographic room, right 32–34% flat full-height near-black graphic column; `THE CAVE / STARTS / HERE.`, verified `LIMITED TO n`, `COLLECTOR SERIES`. One picture light and a completely empty cabinet top.

All three image prompts prohibit appending “worldwide”, “world wide” or other geographic scope to edition claims. Existing immutable artwork is protected. Description-copy generation is unchanged. Without a verified limit, the two new formats use `LIMITED COLLECTOR RELEASE`; Smart Hybrid retains its established evidence-gated fallback.

The existing package variation token is included in every prompt. A deterministic cue derived from the existing product seed, token and stable slot identity varies each slot's camera and approved wall interpretation. The same inputs reproduce the same choices. Prompt instructions require inspection of the actual uploaded artwork, including palette, brightness, frame separation, sport, market, era and campaign context, and exactly one final camera/room/wall selection. Fingerprints now include visual family, campaign line, resolved camera and format-specific overlay placement; recent-fingerprint guidance remains present.

## Files changed

- `ads_page.py`
- `ads_ie_visual_systems.py` (new)
- `tests/test_ads_ie_visual_systems.py` (new)
- `tests/test_ads_instant_experience_footer.py`
- `tests/test_ads_page.py`
- `tests/test_ads_creative_refresh.py` (new-ads assertions only)
- `tests/fixtures/carousel_detail_prompt_baseline.json` (four standard IE snapshots only)
- This report.

Pre-existing changes in Edition Ops, Shopify sync, Supabase and their tests were left untouched.

## Validation

Used `.venv/Scripts/python.exe` with unittest; pytest is not installed.

- Seven new visual-system regression tests passed: stable identities, distinct layouts, verified/missing limits, deterministic variation, shared realism, fingerprints and three copy tables/setup compatibility.
- Ads page suite: 193 tests ran. Two failures were reported; the obsolete CTA-block-count assertion was corrected and passed on rerun. The remaining dropdown-order assertion also fails against the original HEAD source and was left untouched.
- Final combined visual-system, footer, image workflow, CSV importer, Creative Refresh, carousel-detail, shared-realism and corrected CTA test run: **168 tests in 9.244s**. Only four pre-existing Creative Refresh snapshot subcase failures remained, all in `test_unaffected_prompts_match_captured_prechange_bytes` (Motorsport, Football, Cricket and NBA). Those same four failures were reproduced against original HEAD source. All other tests in that run passed.
- Independently compared **20** Carousel, Single Image and Creative Refresh rendered prompts against original HEAD: all byte-for-byte identical.
- Python compilation passed for all six changed/new Python files.
- `git diff --check` passed.
- Inspected a rendered generic Cricket package with edition limit 100: three new group headings, three image prompts, three copy tables, one shared realism block per image, distinct resolved cameras, and `LIMITED TO 100` without a geographic suffix in the two new editorial formats. Setup and UTM compatibility are covered by regression tests.

This validates the generated text contracts, not a rendered image: no external image generation or live ad operation was performed.
