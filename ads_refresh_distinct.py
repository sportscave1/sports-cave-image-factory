"""New Refresh packages only; historical source-preservation plans remain readable."""
import json
import random
import ads_refresh_preserve as legacy
import ads_ie_visual_systems as visuals
import ads_ie_glazing as glazing
import sports_cave_physical_realism as physical

VERSION = 'WINNER DIRECTION THREE DISTINCT REFRESHES V2'


def active(plan):
    return (plan or {}).get('version') == VERSION


def output_format(campaign, context):
    # A historical saved contract keeps its original format and rows.
    saved = (context or {}).get('refresh_plan') or {}
    return 'Single Image / Video' if campaign == 'Carousel' and (not saved or active(saved)) else campaign


def build_plan(context, campaign, product, category, seed, references, identity):
    result = legacy.build_plan(context, campaign, product, category, seed, references, identity)
    result.update(version=VERSION, preservation='Preserve winner direction and room type; create three new photographs.',
                  output_count=3)
    result.pop('carousel_contract', None)
    assigned = (context or {}).get('on_image_headlines') or []
    result['on_image_headlines'] = visuals.select_distinct_headlines(context or {}, seed, assigned)
    return result


def build_prompt(ads, product, category, country, campaign, url, winner, selected, metadata):
    identity = dict(product_name=product, category=category, country=country, campaign_type=campaign,
                    workflow_mode=ads.ADS_WORKFLOW_MODE_CREATIVE_REFRESH,
                    creative_refresh_context=winner, product_url=url)
    template = (ads.build_instant_experience_copy_csv(identity, blank=True) if campaign == 'Instant Experience'
                else ads.build_standard_ads_csv(product_name=product))
    return f'''{VERSION}
SPORTS CAVE — COMPLETE CREATIVE REFRESH PACKAGE
Product: {product}
Category: {category}
Market: {country}
Campaign format: {campaign}
Product page: {url}
SOURCE EVIDENCE AND WINNING COPY: {json.dumps(winner.get('source_winner') or {}, ensure_ascii=False, default=str)}
Winning primary text: {winner.get('winning_primary_text', '')}
Winning written headline: {winner.get('winning_headline', '')}
Verified product metadata: {json.dumps(metadata or {}, ensure_ascii=False, default=str)}
Actual reference manifest: {json.dumps(selected['references'], ensure_ascii=False, default=str)}
Canonical reference: {json.dumps(winner.get('canonical_reference') or {}, ensure_ascii=False, default=str)}

REFERENCE AUTHORITY AND MANDATORY PRODUCT CORRECTION
If multiple source cards show incompatible room types, request only the intended winning reference; do not guess a room. Inspect the actual accessible WINNER_REFERENCE and CANONICAL_PRODUCT image attachments before planning.
WINNER_IE / WINNER_AD / WINNER_CARD references provide creative direction only.
Reuse the verified Shopify product mapping and exact matching frame-variant image supplied through the reference panel. Use accessible image bytes/attachments, not a URL alone; do not assume the first Shopify image is correct. Retrieve available references before requesting uploads. If the edition, frame variant or image is ambiguous/unavailable, request only the missing reference rather than guessing.
CANONICAL_PRODUCT controls the exact original artwork, faces, lettering, logos, colours, proportions, frame and verified physical dimensions. Use it independently for EVERY image. Never reconstruct or reinterpret the design from the winner, redraw its lettering or copy the canonical photograph's external background.
If the winner's artwork differs from the verified canonical product, automatically correct it in all three images. This is mandatory and already authorised; do not ask permission. Record it briefly as shared_product_correction, separate from creative variations. Do not claim fidelity was verified unless the actual output was inspected against the actual canonical image.

PLAN THREE NEW PHOTOGRAPHS AFTER INSPECTING THE WINNER
Identify its room type, palette, atmosphere, product prominence, styling, lighting character and message.
Keep the same observed room TYPE across all three refreshes. A hallway winner gives three hallways; an office winner gives three offices. Never hardcode a room or colour for unrelated winners.
Retain selected recognisable aesthetic cues, not the exact photograph. Each refresh starts independently from the original winner and canonical product, not from a sibling output.
For EACH refresh change BOTH camera position/viewing angle/framing AND room architecture/arrangement/surroundings. Also vary suitable furniture, objects, depth, light direction or finishes. Do not simultaneously lock source layout, camera, lighting placement and composition. No mandatory right/front/left assignments.
All three must be visibly different from the original AND each other at thumbnail size, potentially in different houses of the same room type. Tiny props, recolouring and near-identical recreations do not qualify. Improve visibility, realism, hierarchy and premium presentation without promising performance.

PRODUCT AND PHOTOGRAPHIC REQUIREMENTS — REPEAT IN EVERY STANDALONE IMAGE BRIEF
{physical.build(metadata, compact=True, glazing_requirement=glazing.REQUIREMENT)}
Keep the entire rigid frame visible with breathing room and footer clearance. Camera changes must never enlarge the physical product or distort its proportions. Moderate perspective; coherent natural or warm scene lighting, realistic frame depth, mounting/contact shadows and edge highlights. Keep faces, action and defining lettering clear.
{glazing.REQUIREMENT}
Deliver three separate 1024 x 1024 sRGB images, retaining the existing download and route associations. Never deliver a collage or carousel in place of these three ads.

ON-IMAGE FOOTER — REFRESH-SCOPED ASSIGNMENTS, RESOLVED ONCE
Refresh 1 headline: {selected['on_image_headlines'][0]}
Refresh 2 headline: {selected['on_image_headlines'][1]}
Refresh 3 headline: {selected['on_image_headlines'][2]}
Use these exact distinct approved headlines through individual calls, retries and export. Do not invent or paraphrase them. No supporting sentence on the image. CTA exactly CLAIM YOUR EDITION.
Keep the existing compact full-width fully opaque near-black footer, approximately 18–20% height, straight boundary, thin muted-gold separator, premium regular serif headline and existing CTA styling. Restrained antique-gold 100 with a fine matching underline beneath the FULL NUMBER ONLY. Preserve 64–72 px safe margins, headline 42–48 px and CTA 26–28 px at 1024 square, restrained CTA tracking. No gradient, floating text, extra badge or enlarged panel. Fit exact approved wording without shrinking/stretching typography. Keep the product clear of the panel.

THREE CORRESPONDING WRITTEN COPY SETS
Use only existing copy fields: IE description styles are primary_text, not an additional description column. Refresh the hook, phrasing or sentence structure for all three: distinct primary text/descriptions and one distinct written Meta headline per ad. Preserve winning message, emotional appeal, collector identity, market, product and verified facts. Do not repeat source copy verbatim across the package. Keep assigned frameworks and their distinct approaches where supplied.
Written headlines add product-specific emotional meaning beyond scarcity; aim for 2–6 natural words. Consider candidates internally; return only one headline per ad. No generic purchase slogans or edition-count repetition. Preserve required written CTA Claim Your Edition and native Shop Now. Do not invent claims, rivalry, achievements, discounts, urgency or availability. Flag expired or unsupported offers; never carry them into final copy.

EXECUTION AND COMPLETION — THREE IMAGES PLUS COMPLETE CSV
Continue automatically through ALL THREE separate image outputs, their complete copy and ONE populated downloadable CSV. Do not stop after image one, ask permission between outputs, reuse the winner image or return only a plan/template. Supply the original canonical reference in every image call.
Inspect outputs against source and siblings at thumbnail size. Regenerate a near-duplicate before completion; retry missing outputs after retryable technical failures without discarding successful work. Respect provider safety refusals; never evade a block. If an output remains unavailable, report the specific incomplete item honestly, not completion.
Record in existing ad_notes.refresh_executions exactly three records: position (1–3), winner_reference, reference_inspected, canonical_inspected, observations, source_room_type, room_type, scene, keep, change, improvement (test hypothesis), secondary_differences, camera_treatment, scene_treatment, changed_components (include camera and scene), image_action='redraw', shared_product_correction, canonical_reference (exact supplied image hash or URL), on_image_headline, supporting_line='', cta='CLAIM YOUR EDITION', unresolved_conflicts, image_prompt, and visual_checks. Every image_prompt must identify its original WINNER reference and CANONICAL_PRODUCT and include its scene/camera treatment, exact assigned two-line footer and all product/glazing rules. Do not fabricate inspection or quality checks.
visual_checks contains true only after actual inspection for product_reference_checked, same_room_type, new_camera_and_scene, distinct_from_source_and_siblings, visible_glazing and footer_checked. These declarations do not constitute automated pixel verification.
Before returning, check three generated files are accessible, correct canonical reference used each time, same winner room type and creative direction, new scene and camera treatments, no duplicates, three complete copy sets, and all three CSV rows. Read the exported CSV back to verify its schema, row count/order and exact copy consistency. Provide actual image download links and an actual populated CSV download; never claim missing files exist.
Preserve exact CSV columns/order, compatibility values, route IDs, image associations, UTF-8 BOM encoding, quoting and existing line endings. IE uses variation=1 and output_mode=winner_refinement. Historic Right/Centre/Left route IDs are storage identifiers only, not camera assignments. Keep setup instructions and existing fields. No extra variants, scores, publication or live campaign changes.
EXACT CSV TEMPLATE — POPULATE ALL THREE ADS, DO NOT RETURN A BLANK TEMPLATE
{template.decode('utf-8-sig')}
'''


def execution_issues(records, selected):
    if not isinstance(records, list) or len(records) != 3:
        return ['Record three completed refresh execution notes before marking ready.']
    issues, cameras, scenes, rooms = [], [], [], []
    canonical = next((r for r in selected.get('references', []) if r.get('label') == 'CANONICAL_PRODUCT'), {})
    reference = canonical.get('image_sha256') or canonical.get('url') or canonical.get('image_url')
    for i, row in enumerate(records, 1):
        if not isinstance(row, dict):
            issues.append(f'Refresh {i}: invalid execution record.'); continue
        for field in ('observations', 'source_room_type', 'room_type', 'keep', 'change', 'improvement',
                      'secondary_differences', 'camera_treatment', 'scene_treatment', 'shared_product_correction', 'image_prompt'):
            if not row.get(field):
                issues.append(f'Refresh {i}: complete {field}.')
        if row.get('position') != i or row.get('reference_inspected') is not True or row.get('canonical_inspected') is not True:
            issues.append(f'Refresh {i}: inspect both references and preserve output order.')
        if not reference or row.get('canonical_reference') != reference:
            issues.append(f'Refresh {i}: identify the retrieved exact canonical reference.')
        if row.get('room_type') != row.get('source_room_type'):
            issues.append(f'Refresh {i}: retain the observed winner room type.')
        if row.get('image_action') != 'redraw' or not {'camera', 'scene'} <= set(row.get('changed_components') or []):
            issues.append(f'Refresh {i}: require a new image with both camera and scene changes.')
        if row.get('on_image_headline') != selected['on_image_headlines'][i-1] or row.get('supporting_line') != '' or row.get('cta') != 'CLAIM YOUR EDITION':
            issues.append(f'Refresh {i}: preserve assigned headline, no supporting sentence and exact CTA.')
        checks = row.get('visual_checks') or {}
        if any(checks.get(k) is not True for k in ('product_reference_checked', 'same_room_type', 'new_camera_and_scene', 'distinct_from_source_and_siblings', 'visible_glazing', 'footer_checked')):
            issues.append(f'Refresh {i}: complete actual visual inspection before marking ready.')
        if row.get('unresolved_conflicts') != []:
            issues.append(f'Refresh {i}: resolve remaining reference or factual conflicts.')
        if 'CANONICAL_PRODUCT' not in str(row.get('image_prompt')) or 'WINNER_' not in str(row.get('image_prompt')):
            issues.append(f'Refresh {i}: identify both references in the individual image prompt.')
        cameras.append(str(row.get('camera_treatment', '')).strip().casefold())
        scenes.append(str(row.get('scene_treatment', '')).strip().casefold())
        rooms.append(str(row.get('room_type', '')).strip().casefold())
    if len(set(cameras)) != 3 or len(set(scenes)) != 3:
        issues.append('Require three distinct camera and scene treatments; inspect for near-duplicates too.')
    if len(set(rooms)) != 1:
        issues.append('All refreshes must retain the same observed winner room type.')
    return issues


def copy_issues(rows, campaign):
    if len(rows) != 3:
        return ['Complete all three matching copy sets.']
    issues = []
    for field in (('primary_text', 'headline') if campaign == 'Instant Experience' else ('primary_text', 'headline', 'description')):
        values = [str(r.get(field) or '').strip() for r in rows]
        if not all(values) or len(set(v.casefold() for v in values)) != 3:
            issues.append(f'Complete three distinct {field} values for the refreshed images.')
    return issues
