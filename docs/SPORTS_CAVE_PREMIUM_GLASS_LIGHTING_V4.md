# Sports Cave premium glass and lighting V4

## Scope and supported hypothesis

V3 combined “subtle but clearly visible” reflections with material-focused acrylic/Perspex directions. The physical contract also said “glass only when verified”. Those instructions may encourage an overly restrained reflective appearance. This is a supported prompt-language hypothesis, not a demonstrated cause of the example image. No example pixels were attached to this request; the pasted brief described The Lap of the Gods image.

This update changes generation instructions only. It does not change Shopify specifications, fulfilment construction, product metadata, saved images, published ads, dimensions, filenames, or Render topology.

## Shared implementation

`sports_cave_prompt_blocks.py` defines `SPORTS_CAVE_PREMIUM_GLASS_LIGHTING_V4`. The old Python import name remains a compatibility alias to V4, so email and existing callers share the same version. New framed-product assembly receives one V4 block. Saved generated V3 blocks are replaced in memory by their delimited contract; authored custom text and required endings remain intact. Repeated assembly is idempotent. Original Design Studio artwork mode and explicitly selected unframed products do not receive V4.

`sports_cave_physical_realism.py` changes only shared glazing styling. Verified material evidence remains truthful, including acrylic metadata. When upgrading a saved physical block without new metadata, only its GLAZING line changes; its embedded evidence and other instructions remain verbatim. With supplied metadata, the existing context-resolution mechanism remains authoritative.

The contract applies reflections only to an existing glazed product. Known unglazed products must not acquire a pane. Lighting and frame shadows still apply to genuine framed products. Wall shadows are conditional on actual placement: held, studio and detail shots retain their own settings.

## Audited pathways

| Workflow | Shared assembly or inspected source |
| --- | --- |
| Product-page, man cave, living room, office and other mockups | `mockup_product_prompts.py`, `image_factory.py`, `app.py` physical metadata handoff |
| New Meta ads, banners and standard IE three-image outputs | `ads_page.py` |
| IE Creative Refresh and winning-ad roles | `ads_creative_refresh.py`, `ads_refresh_plan.py`, `ads_refresh_generation.py`, `ads_ie_visual_systems.py` |
| Carousel ads and four/five-card refresh | `ads_page.py`, `ads_carousel_winner.py`, `ads_refresh_plan.py`, `ads_refresh_generation.py` |
| Google advertising | `ads_google_demand_gen.py`, `prompts/google_demand_gen_v1.txt` |
| Social product images | `social_media_creator.py` |
| Reels lifestyle imagery | `social_media_reels_studio_page.py` |
| Marketing visuals and promotional banners | `marketing_factory_page.py` |
| Email visuals | `crm_email_visual_prompt.py`, `prompts/sports_cave_email_visual_v1.txt` |
| SEO article framed-product imagery | `seo_blog_workflow.py` |
| Original artwork exclusion | `design_studio_page.py`, shared `include_product_lock=False` mode |

Repository-wide prompt searches included other Python and prompt text sources. Existing generic glass wording in fixed templates is qualified by the authoritative shared construction and V4 contracts. Saved administrator prose is preserved rather than globally rewritten. Fulfilment Perspex specifications in `os_pages.py` remain untouched.

## Exact visual wording changes

The old V3 reflection paragraph began “a verified glazed frame (acrylic/Perspex OR glass)” and included “Acrylic can look as premium and reflective as glass”. V4 replaces that paragraph with:

> PREMIUM CLEAR GLASS REFLECTION LOOK — MANDATORY: for the supplied glazed framed product, require convincing, clearly visible glass-like reflections on its transparent front surface.

V4 further requires:

> Reflections must actually be visible, including at advertising-thumbnail size; subtle must not mean almost invisible.

It requests a plausible reflected window or room light, highlight falloff, luminance variation and viewing-angle interaction, with slightly stronger edge/upper reflections where appropriate. It forbids matte/invisible glazing, opaque patches, artificial streaks, mirror glare, CGI glow and scene-disconnected reflections. Faces, vehicles, logos, signatures, titles and edition details remain protected.

The previous combined shadow sentence becomes explicit contact shadows, softer secondary shadows and ambient occlusion around actual bevels, mitres, moulding, side profile and mounting. V4 adds directional light, brightness falloff, environmental fill, coherent shadow direction and colour temperature, while preserving cinematic collector rooms.

Additional short visual phrases are changed in `ads_page.py`, `ads_carousel_winner.py`, `ads_refresh_generation.py`, `image_factory.py` and the email text template. These now request the premium clear glass reflection look on existing glazing instead of acrylic/Perspex styling. No surrounding creative instructions are rewritten.

## Before/after final prompt examples

Before, a framed mockup's final shared instructions asked for “subtle but clearly visible transparent-glazing reflections” and “glass only when verified”. After, the same authored room, camera and output brief receives V4's visibly reflective surface requirements, followed by physical evidence retaining actual verified construction.

Before, carousel lifestyle cards said:

> Require clear acrylic/glass, restrained reflections, real highlight falloff and no glare hiding artwork.

After, the same card says:

> Require a premium clear glass reflection look, visible restrained reflections, real highlight falloff and no glare hiding artwork.

Before/after representative card output was compared in `tmp/glass-v4-card-before.txt` and `tmp/glass-v4-card-after.txt`. Their only differing line is the reviewed reflection sentence. Regression hashes for cards 2–4 retain their original baseline after reversing exactly that visual sentence, rather than replacing expected hashes.

## Regression evidence and limitations

Focused verification initially passed 154 Python tests. Final release verification passed all 237 Python tests across 13 test modules in separate processes against an isolated copy of fetched GitHub main with only the listed V4 changes. This avoids existing test-order interference: a combined suite leaves Streamlit form context affecting later AppTest suites, while separate-process save/reopen verification passes. The final module results are recorded in `tmp/glass-v4-test-results.json`; individual logs use `tmp/glass-v4-test_*.log`.

Checks cover legacy upgrades, exact physical evidence preservation, original artwork/unframed exclusions, truthful acrylic metadata, required endings and idempotence; 25 ads combinations; IE slot identities, fixed footer and CSV contracts; carousel roles and source mapping; Google visuals; social/reels; email; mockup camera selections; and save/reopen behavior. Legacy approved full-rule validation accepts either the complete old or complete new product lock, retaining all artwork-fidelity checks and rejecting partial contracts.

Chrome and Edge passed existing offline refresh stability checks for four, five and six cards: 60 navigation actions per case, repeated winning-ad replay, retained edited headlines, correct archive reads, background ticks and no Streamlit exception. Evidence: `tmp/glass-v4-browser.json` and `tmp/glass-v4-browser.log`. Chrome and Edge also passed the Instant Experience offline-page smoke check (`tmp/glass-v4-ie-browser-final.log`). This verifies browser workflow behavior, not generated-image quality.

No new image generation or visual comparison was performed. Actual glass reflection improvement and fidelity of generated pixels remain unverified. There are no identified uncovered framed-product prompt builders from the repository audit; externally stored or future builders that bypass shared assembly cannot be certified by these checks.

## Manual release only

No commit, push or deployment was performed. The local manual release helper uses a separate temporary Git index based on the fetched GitHub-main commit and stages only hash-verified V4 files. It creates a commit with that remote commit as its parent and pushes normally to main. It preserves the normal index, unrelated workspace edits, local unpublished commits and the local branch. It stops if GitHub main or any verified file changes. It never forces, resets, stashes, runs tests or starts a browser during deployment. An isolated staging dry run confirmed exactly 17 release paths and passed Git whitespace checks without creating a commit.
