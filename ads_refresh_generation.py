"""Creative Refresh generation context; production schemas remain owned by ads_page."""
from copy import deepcopy
import json
import ads_refresh_plan as plan


def source_context(source=None):
    source = deepcopy(source or {})
    return {"source_winner": source} if source else {}


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
        briefs.append(plan.standalone_brief(product, reference['label'], scene=reference.get('scene', ''),
                     role=reference.get('role', ''), style=style, detail=carousel and 'detail' in reference.get('role', '').casefold(),
                     dimensions='1024 x 1024' if ie else '1080 x 1080')
                      + ('\n\n' + ads.build_instant_experience_fixed_opaque_footer_rules() + '\n\n' + ads.build_instant_experience_on_image_copy_fit_rules() if ie else ''))
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
