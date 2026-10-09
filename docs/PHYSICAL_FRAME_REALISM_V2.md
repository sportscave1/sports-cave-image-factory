# Sports Cave physical frame realism V2

Implemented locally on 9 October 2026. No commit, push, deployment, live provider mutation or image-generation request was made for this change.

## What changed and why

Added `SPORTS_CAVE_PHYSICAL_SCALE_AND_FRAME_REALISM_V2` to the existing shared product-mockup prompt architecture. It qualifies only physical size, source orientation, frame construction, mounting and glazing. Existing photographic realism and product-lock constants remain verbatim; existing creative instructions remain outside the new block.

The repository contains instructions capable of encouraging the reported problems:

- `ads_page.py:2832` asks for an "extremely large" frame without a physical dimension constraint in that sentence.
- Legacy image-factory scene templates contain image-width coverage targets, including 65–80%. A composition target alone does not establish real product size.
- Shared and route-specific rules assume glass, while `os_pages.py`'s fulfilment reference describes no-mat Classic Frames with Perspex glazing.
- No common resolver previously distinguished selected display size, verified outer-frame dimensions and nominal print size across these builders.

These are evidenced prompt weaknesses, not proof of why a particular generated image looks wrong. No new rendered image was produced or measured during this task. The old instructions remain; the new physical-only precedence rule resolves conflicting enlargement, glazing, mounting-gap and reflection-percentage instructions without changing their creative intent.

## Exact files changed for this request

| File | Change |
|---|---|
| `sports_cave_physical_realism.py` | New shared contract, allowlisted physical metadata, dimension resolution and replacement of existing physical blocks. |
| `sports_cave_prompt_blocks.py` | Adds the contract once to product-mockup rules; retains original-artwork exclusion, required endings and legacy rules. |
| `image_factory.py` | Passes optional product metadata into active lifestyle prompts. |
| `app.py` | One-line metadata handoff from an existing product-page result. |
| `ads_page.py` | Retains available physical metadata, applies it to New Ads and Creative Refresh prompts, and stamps the prompt version. |
| `ads_refresh_plan.py` | Keeps historical completed execution notes valid when the new physical block is absent; new prompts receive the block. |
| `ads_google_demand_gen.py` | Passes available product metadata to existing shared image rules. |
| `social_media_creator.py` | Preserves optional physical metadata during input normalisation and passes it into still/video prompts. |
| `marketing_factory_page.py` | Passes available physical metadata into existing promotional/mockup briefs. |
| `seo_blog_workflow.py` | Passes available product metadata into article/lifestyle image instructions. |
| `crm_email_visual_prompt.py` | Appends the shared block to the existing cached email visual contract. |
| `tests/test_physical_frame_realism.py` | 39 focused offline tests. |
| `tests/test_ads_refresh_repair.py` | Keeps original prompt hashes; compares everything outside the approved new block/version stamp and requires that block to exist. |
| `tests/test_ads_google_demand_gen.py` | Makes the same targeted adjustment to the existing Meta prompt snapshot check, retaining its original fixture hashes. |
| `docs/PHYSICAL_FRAME_REALISM_V2.md` | This report. |

Pre-existing uncommitted Carousel copy-evolution changes remain intact. They account for other files in `git status` and some additional hunks in `ads_page.py` and `ads_refresh_plan.py`; they are not part of this physical-realism change.

## Dimension sources and limits

Resolution order is: verified outer-frame specifications with provenance; verified selected variant specifications or existing Sports Cave size configuration; explicitly supplied dimensions; approved XL reference when the workflow explicitly selects the largest framed option.

The existing Sports Cave display pairs are XL 62 × 87, L 45 × 62, M 30 × 45 and S 21 × 30 cm. They come from the existing size contract in `app.py:823` and the variant references in `os_pages.py:117` onward. This implementation does not edit those specifications. Landscape uses the longer display dimension as width; portrait uses the shorter dimension as width. Numeric selected-size labels can retain their own supplied display measurements.

These display sizes are explicitly labelled **outer frame unconfirmed**. The repository's nominal print measurements differ. No extra border allowance, invented depth or generic A1-paper substitution is added. Verified width/height axes are not silently swapped. Conflicting orientation or finish evidence produces a confirmation flag in the prompt data, rather than stretching the product or replacing its finish.

An unspecified/custom size is not silently made XL. No physical dimensions are inferred from image pixels or product names. Workflows without physical metadata receive the common source-preservation rules and an explicit unresolved-size statement. They must obtain the actual selected variant/reference dimensions before claiming exact scale; no new UI fields or product API reads were introduced.

## Construction, mounting and glazing

- Keep the actual reference finish, front moulding, bevel/inner edge, straight edges, mitred joins, artwork seating and side profile. No extra matboard, double border or deep shadow box. Exact depth is used only when supplied as a verified specification.
- Use source-consistent wall separation, plausible support, subtle ambient occlusion and soft contact shadows aligned with the existing lighting. Preserve the selected room and natural mounting position.
- Use acrylic/Perspex when verified for that product, glass only when verified, and neutral transparent picture-frame glazing otherwise. Keep reflections restrained and printed details readable. The generic fulfilment reference is not treated as proof of every customer's selected variant.
- Preserve all artwork details and existing edition numbers. Keep existing authorised detail-card crops and source-preserving compositing behaviour. Original-artwork creation remains excluded from the product lock.

Furniture ratios use the resolved width only when orientation/axes are known and not conflicting. XL landscape yields 87/180 = 48.33% of a 180 cm sideboard, 87/200 = 43.5% of a 200 cm sofa and 87/85 = 102.35% of an 85 cm doorway. These are physical widths at comparable depth, not pixel ratios. General room dimensions are reference ranges, not invented measurements of a selected room. Smaller variants get their own ratios. Hero prominence comes from existing framing, distance and light; a close-up can fill the image at true physical size.

## Active workflow coverage

| Workflow | Integration |
|---|---|
| Product Page / Shopify lifestyle mockups | Existing three active Man Cave, Office and Living Room builders inherit the block; room and camera selection remain unchanged. |
| Meta New Ads | Carousel, Instant Experience and Single Image/Video builders inherit it through shared rules, with optional selected metadata. |
| Creative Refresh / winner-led work | Carousel card roles/order/detail exceptions and all three separate Instant Experience execution briefs retain their original contracts and receive the physical rules. |
| Google Demand Gen | Existing image brief receives shared rules and available metadata. |
| Social Creator and Reels Studio | Product stills/video scenes inherit the block; existing camera restrictions and artwork-freeze rules remain. |
| Marketing Factory / Ads Intelligence | Existing product-scene prompts inherit shared rules. |
| Website/blog lifestyle imagery | SEO article image/banner briefs inherit shared rules; existing output dimensions remain. |
| Email promotional / See It On Your Wall promotional room imagery | Existing email visual generation contract includes the block. No email HTML, recovery URL or send behaviour changes. |

Design Studio currently creates original artwork rather than furnishing a product room; its original-artwork prompts remain excluded. Completed artwork used by the existing product-page mockup generator receives the rules there. The customer's See It On Your Wall compositor is not a scene-prompt generator and remains unchanged. Retired Website Mockups V2 remains retired. Existing saved image files are not regenerated.

## Sample instruction

For an explicitly selected XL landscape product, the generated evidence states width 87 cm, height 62 cm and "display size; outer frame unconfirmed", with the furniture ratios above. The shared instruction includes:

> Never enlarge the physical artwork to meet hero/image-coverage percentages. Keep existing composition and prominence through believable framing/camera distance and light; a close-up may fill the canvas at true size. No universal percentage of image width. Preserve straight-on/left/right angles and rigid product geometry.

It also requires the source's slim moulding, clean mitres, integrated side profile, soft mounting shadows and verified glazing, while keeping the artwork immutable.

## Verification

Final verification used isolated test processes because combining all Streamlit UI families in one process leaked form state and produced `st.button() can't be used in an st.form()` errors across otherwise passing UI tests. This test-isolation limitation was not repaired by changing production UI code.

| Suite | Result | Runtime |
|---|---|---|
| Physical contract plus shared rules, product mockups, Reels, social, marketing, SEO and Design Studio | 190 passed | 1.823 s |
| Ads / Carousel evolution / Creative Refresh / saved work / Meta Review / Posting handoff / CSV | 326 passed; 1 existing assertion failure | 26.022 s |
| Google Demand Gen | 16 passed | 5.651 s |
| Ads Intelligence | 1 passed | 0.001 s |
| Email prompt builder | 13 passed | 0.575 s |
| Mockup prompt/UI preview | 32 passed | 25.351 s |
| Mockup upload validation and repeat uploads | 22 passed | 1.842 s |
| Total across isolated suites | **600 passed / 601 tests** | Test runtimes, not page-loading benchmarks |

The 39 new tests also passed independently after the final Extra Large alias check (1.113 s). Tests cover both XL orientations, smaller variants, source priority, unknown/conflicting evidence, no fabricated dimensions, furniture ratios, single insertion, saved-rule compatibility, room/camera/copy preservation and metadata propagation. Existing CSV, saved-work, image upload and Posting handoff tests use fixtures/mocks; no live ads or customer emails were created.

The remaining failure is `tests.test_ads_winner_refinement.WinnerRefinementTests.test_ie_refresh_all_three_briefs_include_premium_fomo_rules`: it expects three verbatim contiguous copies of `ie_refresh_image_rules()` but observes zero. Loading the relevant modules from unchanged HEAD `d57eec7` into memory reproduces exactly the same failure. Its source was left unchanged. It is not a new failure introduced by this patch.

Both existing prompt-hash fixtures remain unchanged: 25 prior Ads prompt cases and 78 New Ads market/format cases still match their original hashes after removing only the new physical block and its version stamp. This checks preservation of the surrounding creative text rather than accepting fresh snapshot hashes. Syntax compilation and `git diff --check` passed.

## Preservation and remaining limits

No layouts, buttons, schedules, CSV headers, export formats, output aspect ratios, room/camera selection algorithms, artwork files, posting engine, Meta/Shopify authentication, database schema or product specifications were changed for this request. The tests support preservation of the exercised contracts; they cannot guarantee every untested runtime path.

Physical QC is included in each standalone generation brief. It instructs review of dimensions, construction, finish, mounting, glazing, perspective and original artwork, with visibly wrong renders flagged for correction. This is not a new automatic pixel-analysis service. Prompt tests and synthetic fixtures do not establish the physical accuracy or exact pixel fidelity of an AI-generated image. Measured product specifications and visual inspection of future generated outputs remain necessary.

Nothing was committed, pushed, published or deployed. Existing saved products, customer data and provider resources were not modified.
