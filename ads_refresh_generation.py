import sports_cave_physical_realism as physical_realism
"""Creative Refresh generation context; production schemas remain owned by ads_page."""
from sports_categories import sport_family
from copy import deepcopy
from ads_footer import image_context_without_support
import json
import ads_refresh_plan as plan


def ie_refresh_image_rules():
    """Prompt-only refinement; no change to New Ads, carousel or generation flow."""
    return '''IE WINNER REFINEMENT — PREMIUM PRODUCT / REAL CUSTOMER WALL / FOMO FOOTER
WINNER_IE supplies the winning creative DNA, collector/scarcity persuasion, product prominence and established footer hierarchy. Evolve that principle into three substantially fresh rooms; never merely recolour or change camera angle. The winner is a creative reference, not the product/frame authority.
CANONICAL_PRODUCT — the uploaded canonical black-framed website product image — is the absolute authority for exact artwork, black frame thickness, frame depth, outer proportions, bevel profile, frame geometry and glazing relationship. The winning ad must NOT override canonical frame proportions. Preserve the same frame thickness consistently across all three outputs, allowing only physically correct perspective of the whole rigid frame.
Match the canonical black frame thickness and depth exactly. Do not visually thin, thicken, simplify, flatten or reinterpret the frame.
The frame is a premium physical object with genuine bevel and mounting depth, never a flat black border. Ignore the canonical photograph's external room/background; never redraw the artwork or import its stock-photo wall into the new scene. Every framed mockup represents the owner-confirmed large 87 × 62 cm landscape edition (62 × 87 cm portrait) with premium glass, not acrylic, even when reflections are absent in the canonical photograph. Never ask for size or glazing confirmation. Preserve source frame depth without inventing measurements.

PREMIUM GLASS, LIGHT AND WALL-MOUNT REALISM — include these requirements explicitly in EACH final image prompt:
Apply the shared thumbnail-visible protective-glazing requirement for every framed edition with owner-confirmed premium glass, with realistic frame bevel lighting, believable wall mounting depth, soft contact shadow where frame meets wall and realistic ambient occlusion behind/under the frame. Premium interior lighting must interact naturally with the frame and glazing. Preserve unframed construction; every framed edition uses premium glass, never acrylic.
Use real interior photography, believable wall texture/materials and room proportions, tasteful premium furniture, physically credible lighting sources and high-end but lived-in interior credibility. Product remains the dominant mobile-readable hero on a real customer's wall.
The final result must feel like a genuine premium lifestyle photograph taken in a real home, not a rendered showroom, not an AI room, and not a flat composited mockup.
Prohibit flat poster look, matte/no-glass look for a glazed product, pasted-on mockup look, fake shiny CGI glare, generic AI room rendering, inconsistent shadow directions, floating artwork, frame edge distortion and washed-out glazing that hides artwork text/details. Do not add generic decorative clutter or unsupported product details.

IE REFRESH ON-IMAGE FOOTER COPY — apply to ALL THREE covers, not just the first:
Use the exact headline resolved by the shared approved five-headline bank in ads_ie_visual_systems. No separate refresh bank, paraphrasing, added product names or extra text. Validate exact bank membership and set uniqueness before generation; reuse the selection verbatim in image prompts and corresponding exported footer fields. Select three different approved headlines per set with no repeats; preserve the assigned headline selections verbatim. CTA: CLAIM YOUR EDITION.
Remove the supporting sentence entirely, with no replacement or empty row. Reduce the opaque footer to 18–20% of the square canvas with balanced spacing between headline and CTA. Keep the existing typography and fine gold underline beneath the measured 100 glyphs. General Meta copy instructions and character limits apply only to their named Meta fields, never to the selected on-image footer. No additional advertising text in the edition or room photograph; the established footer is required.'''



def source_context(source=None):
    source = deepcopy(source or {})
    return {"source_winner": source} if source else {}


IE_CRITICAL_PRODUCT_REALISM = '''CRITICAL PRODUCT REALISM — PASS/FAIL
Before designing the room, establish the Sports Cave framed product as a real physical object.
The image FAILS and must be regenerated if any of these are missing:
1. EXACT CANONICAL FRAME
Match CANONICAL_PRODUCT frame thickness, bevel profile, depth and outer proportions exactly. Never thin, thicken, flatten, simplify or reinterpret the frame. The winning advertisement must never override canonical frame construction.
2. CLEAR REAL GLASS OR ACRYLIC GLAZING
For every framed edition, apply the shared thumbnail-visible protective-glazing requirement; missing or imperceptible surface reflections fail visual review, and frame-edge highlights alone do not count. Use owner-confirmed premium glass, not acrylic; preserve the exclusion for unframed products. Prompt wording alone cannot pass this visual check.
3. PREMIUM FRAME BEVEL LIGHTING
Room light must naturally interact with the physical black frame. At least one front bevel and, where perspective permits, one frame side/depth edge must visibly catch realistic light. The frame must read as a three-dimensional premium physical object.
4. WALL SEPARATION
The frame sits physically in front of the wall: believable mounting depth, subtle gap/separation and ambient occlusion immediately behind it. Never painted directly onto the wall.
5. CONTACT SHADOW
Show a soft but clearly visible contact shadow behind/below the frame. Direction, softness and intensity must match the room's primary light source.
6. PRODUCT FIRST
Do not prioritise decorative room styling until exact canonical frame thickness, physical frame depth, thumbnail-visible protective glazing on every framed edition, frame bevel lighting, wall separation, contact shadow and ambient occlusion are visually convincing. Product physics comes before room decoration.'''

IE_FINAL_PRODUCT_REALISM_GATE = '''FINAL PRODUCT REALISM REJECTION GATE
Before returning the generated image, reject and regenerate it if ANY of these are true:
- a framed edition has missing or imperceptible surface reflections at 256 × 256; frame-edge highlights alone do not count (exclude unframed products)
- artwork looks like a flat matte print
- frame looks like a flat black border
- canonical frame thickness has changed
- frame depth is missing where perspective should reveal it
- frame bevel lighting is absent
- mounting separation from the wall is not believable
- contact shadow is missing
- ambient occlusion behind the frame is missing
- glazing reflection conflicts with room lighting
- glazing reflection washes out artwork details
- frame geometry is distorted
- product appears digitally pasted onto the wall
- product appears to float
- image looks CGI-rendered or obviously AI-generated rather than genuine interior photography'''


def ie_refresh_standalone_brief(ads, product, *, style):
    """Prioritise product physics only for Creative Refresh IE contracts."""
    base = plan.standalone_brief(product, 'WINNER_IE', style=style, dimensions='1024 x 1024')
    header, _, execution = base.partition(plan.AUTHORITY)
    shared = plan.build_sports_cave_image_realism_rules(include_product_lock=True)
    execution = execution.removesuffix(shared).strip()
    # Keep the shared rules and existing footer contract intact, emitted once.
    authority, separator, rules = ie_refresh_image_rules().partition('PREMIUM GLASS, LIGHT AND WALL-MOUNT REALISM')
    goal = 'Evolve that principle into three substantially fresh rooms; never merely recolour or change camera angle.'
    authority = authority.replace(goal+' ', '')
    header = header.replace('PRODUCT: '+product, 'PRODUCT: '+product+'\nOutput: square 1024 x 1024')
    execution = execution.replace('Output: square 1024 x 1024; ', '')
    return '\n\n'.join((header.strip(), plan.AUTHORITY, authority.strip(),
                        IE_CRITICAL_PRODUCT_REALISM, goal, execution,
                        ads.build_instant_experience_fixed_opaque_footer_rules(),
                        ads.build_instant_experience_on_image_copy_fit_rules(),
                        separator + rules,
                        'Preserve this order in each final standalone image prompt: product/output size, winner and canonical authorities, CRITICAL PRODUCT REALISM — PASS/FAIL, refresh goal and room, product placement, footer copy, full product-lock/realism rules, FINAL PRODUCT REALISM REJECTION GATE last.',
                        shared, IE_FINAL_PRODUCT_REALISM_GATE))


def build_prompt(ads, product, category, country, campaign_type, url, context,
                 *, campaign_moment=None, product_metadata=None):
    winner = ads.normalize_creative_refresh_context(context)
    source = winner.get("source_winner") or {}
    if campaign_type == 'Carousel':
        return build_carousel_refresh_prompt(ads, product, category, country, url, winner,
            campaign_moment=campaign_moment, product_metadata=product_metadata)
    identity = {"product_name": product, "category": category, "country": country,
                "campaign_type": campaign_type, "product_url": url}
    carousel = campaign_type == "Carousel"
    n = len(source.get("carousel_cards") or source.get("cards") or []) or 5
    identity["creative_refresh_context"] = winner
    template = (ads.build_carousel_copy_csv(identity, template=True) if carousel
                else ads.build_standard_ads_csv(product_name=product))
    count = (f"Create ONE refreshed {n}-CARD carousel (Card 1 through Card {n}). Preserve the useful "
             "sequence/storytelling principle of the reference. Use the exact existing New Ads card fields, "
             "five shared-copy options and one new headline/description per source card in the supplied template."
             if carousel else "Create THREE refreshed creative directions, REFRESH 1, REFRESH 2 and REFRESH 3. "
             "Each needs primary text, headline, description, CTA guidance and a standalone image prompt.")
    ie = campaign_type == "Instant Experience"
    if ie:
        template = ads.build_instant_experience_copy_csv(
            {"campaign_type": campaign_type, "workflow_mode": ads.ADS_WORKFLOW_MODE_CREATIVE_REFRESH}, blank=True)
        count = "Create THREE refreshed creatives: exactly one square 1024 x 1024 cover and ONE copy pair per permanent slot, variation=1, output_mode=winner_refinement. No nine-copy combinations."
    refresh_plan = plan.current_plan(winner, campaign_type, product, category, 'direct-prompt')
    refs = refresh_plan['references']
    attachment_rules = ("ATTACH TO CHATGPT: " + ", ".join(f"ATTACHMENT {i} — WINNER_CARD_{i}" for i in range(1, n+1)) + f" in original order. ATTACHMENT {n+1} — CANONICAL_PRODUCT."
                        if carousel else "ATTACHMENT 1 — WINNER_IE (or WINNER_AD for single-image). ATTACHMENT 2 — CANONICAL_PRODUCT — CANONICAL BLACK-FRAME WEBSITE PRODUCT IMAGE (canonical Sports Cave product image).")
    resolved = ads.resolve_standard_instant_experience_visuals(
        product_name=product, category=category, country=country,
        product_metadata=product_metadata, campaign_moment=campaign_moment) if ie else []
    briefs = []
    for i in range(n if carousel else 3):
        reference = refs[i] if carousel else refs[0]
        style = {} if carousel else refresh_plan['styles'][i]
        briefs.append("\n\n".join((plan.AUTHORITY, IE_CRITICAL_PRODUCT_REALISM,
            ads.build_standard_instant_experience_image_prompt(i + 1, resolved[i],
                product_name=product, category=category, country=country),
            ie_refresh_image_rules(), IE_FINAL_PRODUCT_REALISM_GATE)) if ie else plan.standalone_brief(product, reference['label'], scene=reference.get('scene', ''),
                     role=reference.get('role', ''), style=style, detail=carousel and 'detail' in reference.get('role', '').casefold(),
                     dimensions='1080 x 1080'))
    legacy_style_plan = f"""REFRESH RUN / CANDIDATE STYLE PLAN (OS has not analysed winner pixels)
{json.dumps(refresh_plan, ensure_ascii=False)}
For IE, inspect WINNER_IE before selecting the final three compatible styles from the curated pool, avoiding recent styles and retaining three different home settings, colour families, wall finishes and dark/mid/light earthy shades within the Sports Cave brand palette. If a candidate conflicts with the actual winner/product, replace it with an eligible unused pool entry; return final style IDs in existing brief/context notes. Never shuffle on recopy/save. No stereotypes or invented equipment/logos/memorabilia.
Curated eligible style library (IE/single-image only; never override carousel concepts):
{json.dumps([s for s in plan.STYLES if s['context'] != 'motorsport' or any(t in (sport_family(category) + ' ' + category + ' ' + product).casefold() for t in ('motorsport', 'racing', 'formula', 'f1'))] if not carousel else [], ensure_ascii=False)}

""" if not ie else ""
    visual = ads.build_campaign_moment_visual_context(campaign_moment, selected_country=country)
    return f"""SPORTS CAVE — CREATIVE REFRESH
{(ads.IE_FOOTER_TEXT_CLARIFICATION + chr(10)) if ie else ""}Always describe the product as an ‘edition’, never ‘artwork’; use ‘edition’ or ‘editions’ wherever you would otherwise use ‘artwork’ or ‘artworks’.
{'INSTANT EXPERIENCE WINNER REFINEMENT — NEW ENVIRONMENTS' if ie else ''}
{ads.CREATIVE_REFRESH_WINNER_CONTEXT_VERSION}

CURRENT WINNER / SELECTED REFERENCE CREATIVE
Product: {product}
Category: {category}
Market: {country}
Campaign format: {campaign_type}
Product page URL: {url}
Winning primary text:
{winner['winning_primary_text']}
Winning headline:
{winner['winning_headline']}
Winning description: {source.get('description') or 'Not supplied'}
Winning CTA: {source.get('cta') or 'Not supplied'}
Source evidence (factual context, not customer copy):
{json.dumps(source, ensure_ascii=False, default=str)}
Verified product context: {json.dumps(image_context_without_support(physical_realism.prompt_metadata(product_metadata)) if ie else physical_realism.prompt_metadata(product_metadata), ensure_ascii=False, default=str)}

REFERENCE AUTHORITIES AND ATTACHMENT CHECKLIST
{('GLAZING CHECK: Every framed edition must show believable surface reflections clearly visible at thumbnail size.' + chr(10)) if ie else ''}{attachment_rules}
CSV TEMPLATE — separate non-image attachment (legacy ATTACHMENT 3 for single-image workflow).
{plan.AUTHORITY}
The PRINTED internal artwork background is immutable. Ignore the canonical image's external wall, room, furniture, camera and shadows. Never reconstruct artwork from a winner.
Reference map (metadata, NOT completed pixel analysis):
{json.dumps(refs, ensure_ascii=False)}
Missing references: before proceeding, list every missing labelled image explicitly; stop incomplete visual generation. One winning image cannot stand in for {n} carousel cards. Do not claim all {n} were reviewed without all {n} images.
Analyse each actual attached winner: visible scene/category, card role, defining objects, product attention, strengths/clutter, mood/contrast, copy hook/tone/structure and emotional appeal. Return concise Keep / Change / Improvement rationale in existing notes/context, separate from customer copy. Treat effectiveness as a hypothesis unless performance evidence supports it. A carousel card is a card from a winning carousel, never independently sales-proven.

OBJECTIVE
Analyse the selected reference and identify the visual/copy principle that appears to be working.
Preserve the winning creative DNA. Evolve it rather than discard it. Create NEW executions that
prevent creative fatigue, recognisably related to the reference but not duplicates or unrelated styles.
Preserve concept and advertising principles, not literal room/composition/wall/crop. Redesign architecture/layout, wall palette/material, camera composition plus at least two other scene dimensions. Never only recolour or move the camera.
Carousel: original card N maps refreshed card N. Keep all {n} scene categories, roles, defining objects and sequence; do not apply the IE style library to carousel. Preserve a supported detail-card function.
IE: three genuinely different environments, styles, palettes, layouts, camera compositions and materials; compare against WINNER_IE and each sibling. Permanent right/centre/left identities retain their assigned camera roles in three different homes. Do not force unrelated Winner Evolution / Emotional Expansion / Pattern Interrupt strategies.
Do not describe inconclusive signals or mixed components as a statistically proven winner.
Only use actual supplied evidence; no invented performance claims, offers, scarcity or endorsements.

{count}

{ads.build_country_language_guidance(country)}
{ads.build_carousel_card_copy_rules().replace('For all five carousel cards:', f'For all {n} carousel cards:') if carousel else 'Use the exact supplied three-row IE contract with one copy pair per cover.' if ie else ads.build_standard_ads_output_contract()}

COPY AND IMAGE OUTPUT
Refresh all required CSV copy fields substantially while retaining the winner's underlying emotional/collector appeal. Distinct openings, supporting arguments and headlines per sibling; reject synonym swaps, reordered openings, repeated descriptions and one-word headline changes. Fixed verified facts, product names and required CTAs may repeat. Carousel tells one connected {n}-card story aligned to its scenes. Do not invent stock, demand, discounts, delivery, endorsements or personally signed claims.
Return the copy in the supplied CSV with matching standalone briefs, one per creative/card. Generate images only when requested.
Every final image prompt must be standalone, name {product}, identify its exact winner label and CANONICAL_PRODUCT, and contain the COMPLETE shared realism block below, not a marker or reference to rules above.
Generate square {'1024 x 1024' if ie else '1080 x 1080'} images with premium photorealistic collector presentation, accurate frame geometry and legible mobile composition.
For single-image rows, each image_prompt must be at least 200 characters, with no cross-references.
For Carousel preserve the New Ads card order and fields; use {url} for every card destination.
Return a completed downloadable UTF-8 CSV; quote commas and paragraph breaks correctly.
No extra schema, columns or identity changes. Import it into Sports Cave OS, then attach generated images.

{ads.build_campaign_moment_copy_relevance_block(campaign_moment, selected_country=country, campaign_type=campaign_type)}

VISUAL CAMPAIGN MOMENT RULE
{visual or 'Do not inject the Campaign Moment, event, seasonal props or promotion into visual instructions.'}
Campaign Moment must never overwrite the reference creative logic. Use only explicitly entered promotions.

REFRESH RUN / RESOLVED STYLE PLAN (OS has not analysed winner pixels)
{json.dumps({"references": refs, "resolved_scenes": [{k: v for k, v in row.items() if k not in {"supporting_line", "fomo_line", "sibling_summaries"}} for row in resolved]} if ie else refresh_plan, ensure_ascii=False)}
{legacy_style_plan}
{'Use the resolved hallway / architectural wall / residential man-cave settings and right/front/left cameras verbatim. Inspect WINNER_IE for atmosphere only; never reselect rooms or footer copy. No additional text outside the established footer and immutable edition.' if ie else ''}

STANDALONE EXECUTION CONTRACTS — complete each after actual attachment analysis
{chr(10).join(briefs)}

EXECUTION NOTES — return a JSON array alongside the CSV; no new CSV columns.
Exactly one record per output in permanent order with position (integer), winner_reference (WINNER_CARD_N/WINNER_IE/WINNER_AD), reference_inspected and canonical_inspected (true only after viewing both actual attachments), observations (object with scene_category, ad_role, defining_objects, composition, product_attention, strengths, clutter, mood_contrast, copy_hook, tone, structure, emotional_appeal; include observed execution dimensions where visible, label unknowns honestly), scene, role, keep, change, improvement, style_id (IE/single-image only), execution (object with architecture, layout, wall_palette, wall_material, camera and at least two of furniture, lighting, flooring, background, product_placement; for a supported intentional detail card use camera, lighting and product_placement without forcing room architecture), image_prompt (complete final standalone prompt). These go into existing internal ad notes, never customer ad copy. Include concrete architecture/layout, wall treatment, camera, furniture/materials, product placement, coherent light/glass and overlays in each image_prompt. Reuse actual supplied output/safe-area conventions; preserve deterministic branding separately from immutable artwork.

FINAL BATCH CHECK
Check exact role map, {n} carousel or 3 IE outputs, order, all copy fields, explicit keep/change/new execution, full shared rules in EACH final brief, distinct rooms and substantive copy. Revise near-duplicates. Do not claim visual product fidelity was verified without viewing the actual output images.

EXACT CSV TEMPLATE
{template.decode('utf-8-sig')}
""".strip()


def carousel_identity_issue(product, url, source):
    """No network: validate the verified mapping already carried by the handoff."""
    from meta_review_products import product_url_handle
    mapping = source.get('product_mapping') or {}
    if not source:
        return ''  # Legacy manual references are explicitly supplied by the operator.
    if not mapping.get('product_title') or not mapping.get('product_handle'):
        return 'Confirm the Carousel product from the product selector before generating.'
    labels = {mapping['product_title'].strip().casefold(),
              f"{mapping['product_title']} ({mapping['product_handle']})".strip().casefold()}
    if (str(product).strip().casefold() not in labels
            or product_url_handle(url) != mapping['product_handle'].casefold()):
        return 'Product and URL do not match the selected product. Select the correct product, or use “Use product from URL”, before submitting.'
    return ''


def build_carousel_refresh_prompt(ads, product, category, country, url, winner,
                                  *, campaign_moment=None, product_metadata=None):
    source = winner.get('source_winner') or {}
    issue = carousel_identity_issue(product, url, source)
    if issue:
        raise ValueError(issue)
    selected = plan.current_plan(winner, 'Carousel', product, category, 'direct-prompt')
    refs = selected['references']
    n = len(refs)
    identity = dict(product_name=product, category=category, country=country,
                    campaign_type='Carousel', product_url=url, creative_refresh_context=winner)
    template = ads.build_carousel_copy_csv(identity, template=True).decode('utf-8-sig')
    shared = source.get('shared_primary_texts') or [winner['winning_primary_text']]
    mappings = '\n'.join(f'Image {i} = Card {i} = WINNER_CARD_{i}' for i in range(1, n + 1))
    briefs = '\n\n'.join(plan.carousel_standalone_brief(product, r['label'],
        scene=r.get('scene', ''), role=r.get('role', ''), detail='detail' in r.get('role', '').casefold(),
        references=[ref['label'] for ref in refs]) for r in refs)
    return f'''SPORTS CAVE — TRUE WINNER CAROUSEL REFRESH
Always describe the product as an ‘edition’, never ‘artwork’; use ‘edition’ or ‘editions’ wherever you would otherwise use ‘artwork’ or ‘artworks’.
{plan.VERSION} / {plan.CAROUSEL_CONTRACT}
Product: {product}
Category: {category}
Market: {country}
Campaign format: Carousel
Product page URL: {url}
LIVE BLACK-FRAME VERIFICATION: open the supplied live product URL, select the Black frame variant and compare the visible original product gallery, text, border and construction. Use the verified Black variant link supplied by Sports Cave OS if available. A URL is not proof pixels were inspected; disclose when direct visual verification is unavailable.
Verified Black variant source data (when explicitly checked): {json.dumps((product_metadata or {}).get('verified_black_variant') or {}, ensure_ascii=False, default=str)}
Verified product facts: {json.dumps(physical_realism.prompt_metadata(product_metadata), ensure_ascii=False, default=str)}

{plan.carousel_copy.instruction(winner, refs)}

ATTACH EXACTLY {n} ORIGINAL WINNING CARD IMAGES IN SOURCE ORDER + SEPARATE CANONICAL PRODUCT WHEN AVAILABLE
{mappings}
WINNER_CARD_1 through WINNER_CARD_{n} are advertising reference images, not immutable original product artwork.
CANONICAL_PRODUCT is the optional additional black-framed original Shopify product photo. It defines actual artwork/frame fidelity, NOT the new room/background. Do not import its original external setting or copy the old winner.
Keep exactly {n} original card slots and {n} refreshed outputs. The product reference is NOT a new Carousel card. Four original cards mean four new images; five original cards mean five.
Inspect all {n} full-resolution winning images and select BEST_WINNER_CLOSEUP only after comparing actual useful frame/detail clarity, rigid corners, legible text and lack of distortion. Use it as SECONDARY supporting evidence, never over the original Shopify source. A simulated magnifier does not prove detail accuracy. If none is suitable, declare unavailable.
If product pixels or frame construction remain unclear, request the full-resolution black-framed original image; never guess product details.
CSV template is a separate non-image attachment. For a legacy manual winner, attach every labelled card and supply its matching headline/description and shared primary texts before proceeding.
Missing references: list every missing labelled image and stop. One winning image cannot stand in for {n} cards. Complete winning Carousel required. Reload the winner from Meta Review.
OS has not analysed winner pixels. Inspect the actual full-resolution attachments, never infer visual details from metadata.

PRODUCT ACCURACY AND WINNING CREATIVE AUTHORITIES — SHARED ACROSS ALL CARDS
{plan.CAROUSEL_AUTHORITY}
List the {n} winner labels in each standalone prompt and CANONICAL_PRODUCT when supplied. Record the inspected BEST_WINNER_CLOSEUP label separately as a secondary source. Lock unchanged printed artwork across all images; only the outside room/wall/furniture/light may change.
Cross-check unclear winner details against the supplied canonical product, not a generated visual approximation. Never borrow another card's exterior room or redraw the artwork.

SOURCE CARDS — CARD N MUST REMAIN CARD N
{json.dumps(refs, ensure_ascii=False)}
Keep each image, headline, description, destination, CTA and source identity paired. Do not assign shared primary variation N to card N.
SHARED WINNING PRIMARY TEXT VARIATIONS
{json.dumps(shared, ensure_ascii=False)}
Fallback winning headline: {winner['winning_headline']}
Winning CTA: {source.get('cta') or 'Not supplied'}

INDIVIDUAL WINNER ANALYSIS — REQUIRED FOR EVERY CARD
For each Image 1 through Image {n}, identify observed scene family, advertising role, defining functional objects, composition, product attention, strengths, clutter, mood/contrast, copy hook, tone, structure and emotional appeal. Record what to keep, what to change and why the new execution is better. Treat effectiveness as a hypothesis, not independently proven card performance.
Preserve the winning strategic principle, broad room family, card role and source sequence. Create a substantially different physical scene for every card: bedroom -> new bedroom; man cave -> new man cave; office -> new office; lounge -> new lounge; detail-role -> new detail execution.
Redesign room architecture/layout, wall colour/material, furniture/environment, product position, camera composition and lighting arrangement. Preserve concept-defining objects (e.g. billiards table) but not their literal styling. Never only recolour, recrop, change camera angle or make an unrelated concept. Detail cards retain detail function with a fresh photographic execution rather than a forced interior.

ONE refreshed {n}-CARD carousel — EXACTLY {n} COMPLETE STANDALONE IMAGE PROMPTS
Each final prompt must name {product}, its exact WINNER_CARD_N, all collective product-authority references, source role, preserved principle, concrete new scene, architecture/wall, furniture/environment, camera, lighting, product position and specific upgrade. Include the COMPLETE shared product-lock and photographic realism block from its contract below, not a cross-reference. Supported detail crops retain the applicable detail version.
Product physics comes first: faithful frame thickness/depth/bevel, realistic transparent glass/reflections consistent with actual lights, bevel lighting, wall separation, soft contact shadow, ambient occlusion, mobile-readable product prominence and genuine interior photography. No invented construction, flat matte poster treatment of glazed products, distorted frame, CGI sheen or pasted rectangle. Reject unclear artwork details rather than regenerate them from imagination.

REFRESH THE WINNING COPY
Return exactly five shared Primary Text variations AND {n} matching card headline/description pairs under {plan.carousel_copy.CONTRACT}. Refresh each card's OWN original headline and description in its original role. Keep the same argument, psychological trigger, tone and source-relative rhythm/length; improve its expression. Fixed verified facts, product names and mandatory CTAs may repeat; do not invent scarcity, stock, offers, demand or endorsements.
Also complete all five shared headline variation rows and all five shared description variation rows already present in the CSV template. Those shared copy choices are separate from card-specific headlines/descriptions. No required production copy cell may remain blank; an incomplete template cannot be saved for Posting.
{ads.build_country_language_guidance(country)}
CAROUSEL CARD CHARACTER LIMIT: Maximum 17 characters each for headline and description, including spaces/punctuation. No commas or full stops, no truncated words. The original card's selling role takes priority; do not replace premium framing or personal sports-space desire with general sporting history. Shared Meta options are separate from this limit.
Keep the EXACT existing CSV headers, row identities, five shared-copy slots, {n} ordered card fields, upload slots and Posting contract. No execution metadata in CSV columns. Use {url} for every card destination. Return completed downloadable UTF-8 CSV with correctly quoted commas/newlines. Generate images only when requested.
{ads.build_campaign_moment_copy_relevance_block(campaign_moment, selected_country=country, campaign_type='Carousel')}
VISUAL CAMPAIGN MOMENT RULE
{ads.build_campaign_moment_visual_context(campaign_moment, selected_country=country) or 'Do not inject events, seasonal props or promotions into the visuals.'}
Campaign Moment must not overwrite the winning creative strategy.

STANDALONE EXECUTION CONTRACTS — COMPLETE AFTER INSPECTING THE ACTUAL ATTACHMENTS
{briefs}

EXECUTION NOTES — {n} JSON records alongside CSV, in source order
Each record: position, winner_reference, reference_inspected=true and collective_product_inspected=true only after inspecting all winning images; observations object with scene_category, ad_role, defining_objects, composition, product_attention, strengths, clutter, mood_contrast, copy_hook, tone, structure, emotional_appeal and execution (observed architecture, layout, wall_palette, wall_material, camera, furniture, lighting, flooring, background, product_placement). Record unknowns honestly; resolve required unknowns before finalising. Then scene (preserved broad family), role, keep (winning principle), change (concrete new execution), improvement (upgrade rationale), execution (NEW architecture/layout/wall_palette/wall_material/camera plus at least two of furniture/lighting/flooring/background/product_placement), image_prompt (complete standalone final brief). For verified detail roles use camera, lighting and product_placement as required source/new dimensions instead of forcing room architecture.
Include the source-mapped copy_review, shared_copy_review and visual_review objects specified by {plan.carousel_copy.CONTRACT} in this same JSON array, outside the CSV. Compare the declared new dimensions against the observed source and all siblings. Reject unchanged architecture/layout with mere colour or angle swaps, missing analysis, generic placeholders, missing product-lock/realism, near-duplicate rooms or unchanged unprotected sentences. These deterministic declarations do not certify pixel fidelity; inspect generated images before use. Never claim a visual similarity score.

FINAL BATCH CHECK
Exactly {n} source cards, {n} independent analyses, {n} new same-family executions, {n} standalone image prompts, five shared Primary Text variations and {n} refreshed card headline/description pairs; same order, same product and strategy, no copied room or unchanged unprotected sentences. Complete all required fields before marking ready.

EXACT CSV TEMPLATE
{template}'''.strip()
