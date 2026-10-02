"""Creative Refresh generation context; production schemas remain owned by ads_page."""
from copy import deepcopy
import json
import ads_refresh_plan as plan


IE_REFRESH_FOOTER_HEADLINES = (
    'ONLY 100 WILL EVER EXIST',
    'LIMITED TO 100 EDITIONS',
    'JUST 100 EDITIONS WORLDWIDE',
    'ONE OF ONLY 100',
    'STRICTLY 100 EDITIONS',
    'ONLY 100 CAN BE CLAIMED',
    'WHEN 100 GO, IT ENDS',
    'A 100 EDITION RELEASE',
    '100 WORLDWIDE. NO MORE',
    'CLAIM BEFORE 100 ARE GONE',
)
IE_REFRESH_FOOTER_SUPPORT = (
    'Once they’re gone, they’re gone for good.',
    'A collector release that won’t be repeated.',
    'No second run after sellout.',
    'Secure yours before the edition closes.',
    'A short-run release made for collectors.',
    'Miss this release and it stays missed.',
    'The edition retires once the run is gone.',
    'Own it before the collector window closes.',
    'Built as a limited run, not a mass release.',
    'When this release is claimed out, it’s finished.',
)


def ie_refresh_image_rules():
    """Prompt-only refinement; no change to New Ads, carousel or generation flow."""
    return '''IE WINNER REFINEMENT — PREMIUM PRODUCT / REAL CUSTOMER WALL / FOMO FOOTER
WINNER_IE supplies the winning creative DNA, collector/scarcity persuasion, product prominence and established footer hierarchy. Evolve that principle into three substantially fresh rooms; never merely recolour or change camera angle. The winner is a creative reference, not the product/frame authority.
CANONICAL_PRODUCT — the uploaded canonical black-framed website product image — is the absolute authority for exact artwork, black frame thickness, frame depth, outer proportions, bevel profile, frame geometry and glazing relationship. The winning ad must NOT override canonical frame proportions. Preserve the same frame thickness consistently across all three outputs, allowing only physically correct perspective of the whole rigid frame.
Match the canonical black frame thickness and depth exactly. Do not visually thin, thicken, simplify, flatten or reinterpret the frame.
The frame is a premium physical object with genuine bevel and mounting depth, never a flat black border. Ignore the canonical photograph's external room/background; never redraw the artwork or import its stock-photo wall into the new scene. If depth/glazing cannot be established from the supplied source, request an additional canonical reference rather than invent construction details.

PREMIUM GLASS, LIGHT AND WALL-MOUNT REALISM — include these requirements explicitly in EACH final image prompt:
Premium real-glass glazing with subtle but visible room-based reflections, physically believable highlight falloff on the glazing, realistic frame bevel lighting, believable wall mounting depth, soft contact shadow where frame meets wall and realistic ambient occlusion behind/under the frame. Premium interior lighting must interact naturally with the frame and glass. Keep reflections restrained and consistent with actual windows/lamps and camera angle; printed artwork text/details remain clear. If the canonical product is explicitly verified as unglazed, preserve that construction instead of adding glass.
Use real interior photography, believable wall texture/materials and room proportions, tasteful premium furniture, physically credible lighting sources and high-end but lived-in interior credibility. Product remains the dominant mobile-readable hero on a real customer's wall.
The final result must feel like a genuine premium lifestyle photograph taken in a real home, not a rendered showroom, not an AI room, and not a flat composited mockup.
Prohibit flat poster look, matte/no-glass look for a glazed product, pasted-on mockup look, fake shiny CGI glare, generic AI room rendering, inconsistent shadow directions, floating artwork, frame edge distortion and washed-out glazing that hides artwork text/details. Do not add generic decorative clutter or unsupported product details.

IE REFRESH ON-IMAGE FOOTER COPY — apply to ALL THREE covers, not just the first:
The main/top footer headline must ALWAYS be scarcity/FOMO-led, selected from the approved headline patterns below. Never use Legends On The Wall, Two Names One Standard, Framed Greatness, For Real Fans or a similar generic/conceptual brand headline as the main footer headline. The second footer line must add restrained collector urgency or a distinct scarcity/finality layer; the supporting line must not repeat the headline. CTA remains collector-led within the existing approved CTA bank.
All 3 outputs must use distinct scarcity/support pairings: three different headlines AND three different supporting lines, with no duplicate footer copy. Do not treat synonym swaps as meaningful variation. If the headline states only 100/100 editions, do not repeat the quantity or worldwide edition statement in its support line. If the headline already expresses sellout finality, support it with collector ownership/limited-run urgency rather than another gone-for-good statement. Avoid pairing two versions of the same finality claim. Preserve the winner's winning scarcity logic across all three while refreshing the rooms substantially.
Premium, restrained, concise collector tone; no cheap hype, pressure countdowns or invented demand. Keep the established opaque footer, gold separator, safe margins, hierarchy and typography unchanged. Headline: exactly one line, at most 6 words/28 characters. Support: exactly one line, at most 12 words/70 characters. CTA: exactly one line, at most 4 words/24 characters. Shorten copy within the scarcity strategy instead of shrinking fonts or wrapping.
Evidence gate: 100 in this bank is a pattern example, NOT a product fact. Use 100 only when the canonical artwork or supplied verified product facts confirm that limit; substitute another verified limit and recheck fit. Never infer edition size, remaining stock, exclusivity, no reprint, retirement or a closing deadline from the winner alone. Use no-second-run/finality/support patterns only when that policy is verified. If necessary edition facts are missing, request them before generating final footer copy; do not fall back to a generic non-FOMO headline or fabricate scarcity.

APPROVED IE CREATIVE REFRESH FOOTER HEADLINE BANK
''' + '\n'.join('- '+line for line in IE_REFRESH_FOOTER_HEADLINES) + '''

APPROVED IE CREATIVE REFRESH SUPPORTING-LINE BANK
''' + '\n'.join('- '+line for line in IE_REFRESH_FOOTER_SUPPORT) + '''

Before returning each standalone image prompt, include the complete winner/canonical authority roles, exact frame-thickness/depth instruction, premium glass and wall-mount realism, real-room lifestyle-photography requirement, FOMO-only headline rule, non-repeating support rule and three-output distinct-pair rule. Resolve the exact permitted headline/support/CTA text for that cover in its own prompt; do not leave a choice bank or an instruction to consult another brief. Check all three selected pairs together for duplicate ideas and copy before returning them.'''


def source_context(source=None):
    source = deepcopy(source or {})
    return {"source_winner": source} if source else {}


IE_CRITICAL_PRODUCT_REALISM = '''CRITICAL PRODUCT REALISM — PASS/FAIL
Before designing the room, establish the Sports Cave framed product as a real physical object.
The image FAILS and must be regenerated if any of these are missing:
1. EXACT CANONICAL FRAME
Match CANONICAL_PRODUCT frame thickness, bevel profile, depth and outer proportions exactly. Never thin, thicken, flatten, simplify or reinterpret the frame. The winning advertisement must never override canonical frame construction.
2. CLEAR REAL GLASS
The artwork must visibly sit behind genuine transparent glazing. Show restrained but clearly visible room-based reflections across part of the glass, following the flat glass plane and actual room windows/lights with realistic highlight falloff. Keep reflections subtle without obscuring artwork details. Never a matte, frameless, digitally pasted or flat poster look.
3. PREMIUM FRAME BEVEL LIGHTING
Room light must naturally interact with the physical black frame. At least one front bevel and, where perspective permits, one frame side/depth edge must visibly catch realistic light. The frame must read as a three-dimensional premium physical object.
4. WALL SEPARATION
The frame sits physically in front of the wall: believable mounting depth, subtle gap/separation and ambient occlusion immediately behind it. Never painted directly onto the wall.
5. CONTACT SHADOW
Show a soft but clearly visible contact shadow behind/below the frame. Direction, softness and intensity must match the room's primary light source.
6. PRODUCT FIRST
Do not prioritise decorative room styling until exact canonical frame thickness, physical frame depth, visible real glass, frame bevel lighting, wall separation, contact shadow and ambient occlusion are visually convincing. Product physics comes before room decoration.'''

IE_FINAL_PRODUCT_REALISM_GATE = '''FINAL PRODUCT REALISM REJECTION GATE
Before returning the generated image, reject and regenerate it if ANY of these are true:
- glass cannot be visually identified
- artwork looks like a flat matte print
- frame looks like a flat black border
- canonical frame thickness has changed
- frame depth is missing where perspective should reveal it
- frame bevel lighting is absent
- mounting separation from the wall is not believable
- contact shadow is missing
- ambient occlusion behind the frame is missing
- glass reflection conflicts with room lighting
- glass reflection washes out artwork details
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
    briefs = []
    for i in range(n if carousel else 3):
        reference = refs[i] if carousel else refs[0]
        style = {} if carousel else refresh_plan['styles'][i]
        briefs.append(ie_refresh_standalone_brief(ads, product, style=style) if ie else plan.standalone_brief(product, reference['label'], scene=reference.get('scene', ''),
                     role=reference.get('role', ''), style=style, detail=carousel and 'detail' in reference.get('role', '').casefold(),
                     dimensions='1080 x 1080'))
    visual = ads.build_campaign_moment_visual_context(campaign_moment, selected_country=country)
    return f"""SPORTS CAVE — CREATIVE REFRESH
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
Verified product context: {json.dumps(product_metadata or {}, ensure_ascii=False, default=str)}

REFERENCE AUTHORITIES AND ATTACHMENT CHECKLIST
{attachment_rules}
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
IE: three genuinely different environments, styles, palettes, layouts, camera compositions and materials; compare against WINNER_IE and each sibling. Permanent right/centre/left CSV identities are compatibility IDs, not three camera angles in one room. Do not force unrelated Winner Evolution / Emotional Expansion / Pattern Interrupt strategies.
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

REFRESH RUN / CANDIDATE STYLE PLAN (OS has not analysed winner pixels)
{json.dumps(refresh_plan, ensure_ascii=False)}
For IE, inspect WINNER_IE before selecting the final three compatible styles from the curated pool, avoiding recent styles and same family+palette. If a candidate conflicts with the actual winner/product, replace it with an eligible unused pool entry; return final style IDs in existing brief/context notes. Never shuffle on recopy/save. No stereotypes or invented equipment/logos/memorabilia.
Curated eligible style library (IE/single-image only; never override carousel concepts):
{json.dumps([s for s in plan.STYLES if s['context'] != 'motorsport' or any(t in (category + ' ' + product).casefold() for t in ('motorsport', 'racing', 'formula', 'f1'))] if not carousel else [], ensure_ascii=False)}

STANDALONE EXECUTION CONTRACTS — complete each after actual attachment analysis
{chr(10).join(briefs)}

EXECUTION NOTES — return a JSON array alongside the CSV; no new CSV columns.
Exactly one record per output in permanent order with position (integer), winner_reference (WINNER_CARD_N/WINNER_IE/WINNER_AD), reference_inspected and canonical_inspected (true only after viewing both actual attachments), observations (object with scene_category, ad_role, defining_objects, composition, product_attention, strengths, clutter, mood_contrast, copy_hook, tone, structure, emotional_appeal; include observed execution dimensions where visible, label unknowns honestly), scene, role, keep, change, improvement, style_id (IE/single-image only), execution (object with architecture, layout, wall_palette, wall_material, camera and at least two of furniture, lighting, flooring, background, product_placement; for a supported intentional detail card use camera, lighting and product_placement without forcing room architecture), image_prompt (complete final standalone prompt). These go into existing internal ad notes, never customer ad copy. Include concrete architecture/layout, wall treatment, camera, furniture/materials, product placement, coherent light/glass and overlays in each image_prompt. Reuse actual supplied output/safe-area conventions; preserve deterministic branding separately from immutable artwork.

FINAL BATCH CHECK
Check exact role map, {n} carousel or 3 IE outputs, order, all copy fields, explicit keep/change/new execution, full shared rules in EACH final brief, distinct rooms and substantive copy. Revise near-duplicates. Do not claim visual product fidelity was verified without viewing the actual output images.

EXACT CSV TEMPLATE
{template.decode('utf-8-sig')}
""".strip()
