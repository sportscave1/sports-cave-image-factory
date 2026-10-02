"""Local, deterministic refresh planning. No image inference or network calls."""
from copy import deepcopy
import hashlib
import json
import random
import re
from difflib import SequenceMatcher

from sports_cave_prompt_blocks import build_sports_cave_image_realism_rules

VERSION = 'WINNER LED REFRESH V3'
AUTHORITY = ('The canonical black-framed product image supplies the exact artwork and black frame only. '
             'Its external background is not a creative reference. Analyse the separately supplied winning '
             'advertisement(s) for creative direction. Preserve the product; redesign the surrounding scene.')
# Architecture, palette and materials are selection metadata, not inferred winner observations.
_STYLES = (
 ('Heritage billiards room', 'games', 'burgundy', 'panelling', 'traditional timber', 'heritage enclosed room', 'warm practical light', 'pool table'),
 ('Contemporary home bar', 'bar', 'ink-blue', 'paint', 'walnut cabinetry', 'modern built-in bar', 'warm practical light', 'home bar'),
 ('Industrial loft lounge', 'loft', 'warm brick', 'brick', 'steel and leather', 'high-ceiling loft', 'side window light', 'collector lounge'),
 ('Modern sports-viewing den', 'den', 'olive', 'acoustic walls', 'low seating', 'modern enclosed den', 'soft practical light', 'viewing room'),
 ('Daylight oak study', 'study', 'limestone', 'stone', 'natural timber', 'daylight study', 'natural daylight', 'desk'),
 ('Traditional private library', 'library', 'oxblood', 'paint', 'bookshelves', 'traditional library', 'warm reading light', 'books'),
 ('Minimal gallery hallway', 'hallway', 'warm plaster', 'plaster', 'restrained furnishings', 'minimal gallery hallway', 'soft daylight', 'art display'),
 ('Mid-century conversation lounge', 'lounge', 'tobacco', 'paint', 'teak and mustard upholstery', 'mid-century lounge', 'warm lamp light', 'conversation seating'),
 ('Coastal collector lounge', 'lounge', 'muted blue', 'paint', 'whitewashed timber', 'coastal lounge', 'soft daylight', 'collector seating'),
 ('Scandinavian reading room', 'reading', 'sage', 'paint', 'ash furniture', 'Scandinavian reading room', 'diffuse daylight', 'reading chair'),
 ('Japandi living room', 'lounge', 'sand', 'limewash', 'dark timber', 'Japandi living room', 'soft daylight', 'restrained seating'),
 ('Sunken conversation room', 'lounge', 'deep taupe', 'plaster', 'built-in seating', 'sunken conversation room', 'warm practical light', 'conversation seating'),
 ('Contemporary penthouse lounge', 'lounge', 'slate', 'stone', 'clean glazing', 'penthouse lounge', 'side window light', 'collector seating'),
 ('Converted warehouse apartment', 'loft', 'pale concrete', 'concrete', 'warm furnishings', 'converted warehouse', 'diffuse daylight', 'apartment seating'),
 ('Vinyl listening room', 'listening', 'aubergine', 'acoustic surfaces', 'record storage', 'private listening room', 'warm practical light', 'records'),
 ('Home cinema foyer', 'foyer', 'midnight-blue', 'paint', 'restrained timber', 'cinema foyer', 'subtle practical lighting', 'foyer'),
 ('Collector display study', 'study', 'warm grey', 'plaster', 'restrained display niches', 'display study', 'soft practical light', 'display niches'),
 ('Motorsport garage lounge', 'garage', 'graphite', 'cabinetry', 'clean workshop furnishings', 'garage lounge', 'soft practical light', 'motorsport'),
 ('Private training lounge', 'training', 'warm grey', 'plaster', 'timber bench', 'private training lounge', 'natural daylight', 'training'),
 ('Heritage clubroom', 'clubroom', 'forest-green', 'paint', 'leather chairs', 'heritage clubroom', 'warm lamp light', 'club seating'),
 ('Converted barn living room', 'lounge', 'chalk', 'plaster', 'exposed timber beams', 'converted barn', 'soft daylight', 'collector seating'),
 ('Townhouse stair landing', 'hallway', 'mineral-blue', 'paint', 'stone stair details', 'townhouse stair landing', 'natural daylight', 'art display'),
 ('Converted attic study', 'study', 'muted olive', 'paint', 'timber desk', 'sloped attic ceiling', 'roof-window daylight', 'desk'),
 ('Contemporary games room', 'games', 'cream', 'paint', 'ochre accents', 'modern games room', 'soft practical light', 'pool table'),
 ('Chess and reading lounge', 'reading', 'tobacco', 'paint', 'pale timber', 'reading lounge', 'warm reading light', 'chess'),
 ('Restrained Art Deco lounge', 'lounge', 'plum', 'paint', 'fluted walnut', 'Art Deco lounge', 'warm practical light', 'collector seating'),
 ('Modern farmhouse sitting room', 'lounge', 'dove-grey', 'paint', 'limestone fireplace', 'farmhouse sitting room', 'soft daylight', 'collector seating'),
 ('Courtyard-facing lounge', 'lounge', 'terracotta', 'plaster', 'restrained timber', 'courtyard-facing lounge', 'soft natural light', 'collector seating'),
 ('Timber-lined collector retreat', 'retreat', 'cedar', 'timber', 'simple furnishings', 'timber-lined retreat', 'simple warm lighting', 'collector seating'),
 ('Modern apartment dining nook', 'dining', 'clay', 'paint', 'compact oak furnishings', 'apartment dining nook', 'natural daylight', 'dining'),
)
STYLES = tuple(dict(id=f'{i:02}', name=row[0], family=row[1], wall_hue=row[2],
                    wall_value='dark' if row[2] in {'burgundy','ink-blue','oxblood','aubergine','midnight-blue','graphite','forest-green','plum','slate'} else 'mid/light',
                    wall_material=row[3], furniture_materials=row[4], architecture=row[5],
                    lighting=row[6], context=row[7], compatibility='Candidate premium collector environment; confirm against actual winner pixels before use.',
                    exclusions='No invented sporting equipment, logos, memorabilia or demographic stereotypes.')
               for i, row in enumerate(_STYLES, 1))


def select_styles(seed, *, product='', category='', history=(), eligible_ids=None):
    """Seeded without replacement; least recently used candidates first if restricted."""
    allowed = set(eligible_ids) if eligible_ids is not None else {s['id'] for s in STYLES}
    pool = [s for s in STYLES if s['id'] in allowed
            and (s['context'] != 'motorsport' or re.search('motorsport|racing|formula|f1', category + ' ' + product, re.I))]
    recent = [str(i) for entry in history[-30:] for i in entry.get('style_ids', [])]
    rng = random.Random(str(seed))
    rng.shuffle(pool)
    pool.sort(key=lambda s: (s['id'] in recent, max((i for i, v in enumerate(recent) if v == s['id']), default=-1)))
    selected = []
    for style in pool:
        if any((style['family'], style['wall_hue']) == (old['family'], old['wall_hue']) for old in selected):
            continue
        selected.append(deepcopy(style))
        if len(selected) == 3:
            return selected
    raise ValueError('Three compatible distinct styles are required; expand the eligible pool.')


def reference_map(campaign_type, source=None):
    source = source or {}
    cards = source.get('carousel_cards') or source.get('cards') or []
    cards = cards if isinstance(cards, list) else []
    if campaign_type == 'Carousel':
        count = len(cards) if len(cards) >= 2 else max([5, len(cards)] + [int(c.get('position', i)) for i, c in enumerate(cards, 1) if isinstance(c, dict) and str(c.get('position', i)).isdigit()])
        by_position = {}
        for index, card in enumerate(cards, 1):
            if not isinstance(card, dict):
                continue
            try:
                position = int(card.get('position', index))
            except (TypeError, ValueError):
                continue
            if 1 <= position <= count and position not in by_position:
                by_position[position] = card
        refs = []
        for i in range(1, count + 1):
            card = by_position.get(i, {})
            refs.append({'label': f'WINNER_CARD_{i}', 'position': i,
                         'image_sha256': card.get('image_sha256', ''),
                         'image_url': card.get('image_url') or card.get('picture') or '',
                         'headline': card.get('headline') or '', 'description': card.get('description') or '',
                         'source_id': card.get('source_id') or '',
                         'scene': card.get('scene') or '', 'role': card.get('role') or '',
                         'evidence': 'metadata only; inspect attachment in ChatGPT'})
    else:
        refs = [{'label': 'WINNER_IE' if campaign_type == 'Instant Experience' else 'WINNER_AD',
                 'image_sha256': source.get('image_sha256', ''),
                 'image_url': ((source.get('components') or {}).get('image') or {}).get('value', ''),
                 'evidence': 'metadata only; inspect attachment in ChatGPT'}]
    return refs + [{'label': 'CANONICAL_PRODUCT', 'authority': 'exact artwork and black frame only'}]


def identity_hash(context, campaign_type, product, category):
    base = {k: v for k, v in (context or {}).items() if k != 'refresh_plan'}
    identity = json.dumps([product, category, campaign_type, base], sort_keys=True, default=str)
    return hashlib.sha256(identity.encode()).hexdigest()


def build_plan(context, campaign_type, product, category, seed, history=()):
    source = (context or {}).get('source_winner') or {}
    identity = identity_hash(context, campaign_type, product, category)
    return {'version': VERSION, 'run_id': hashlib.sha256((identity+str(seed)).encode()).hexdigest()[:24],
            'identity_hash': identity, 'product': product, 'category': category, 'campaign_type': campaign_type,
            'seed': str(seed), 'references': reference_map(campaign_type, source),
            'styles': select_styles(seed, product=product, category=category, history=history) if campaign_type != 'Carousel' else [],
            'recent_styles': deepcopy(list(history)[-30:]),
            'visual_analysis': 'Pending external ChatGPT attachment inspection; OS has not analysed pixels.'}


def current_plan(context, campaign_type, product, category, seed, history=()):
    saved = (context or {}).get('refresh_plan') or {}
    refs = saved.get('references') or []
    expected = len(reference_map(campaign_type, (context or {}).get('source_winner'))) if campaign_type == 'Carousel' else 2
    structural = (isinstance(refs, list) and len(refs) == expected
                  and all(isinstance(r, dict) for r in refs)
                  and refs[-1].get('label') == 'CANONICAL_PRODUCT'
                  and (campaign_type == 'Carousel' or len(saved.get('styles') or []) == 3))
    if structural and saved.get('version') == VERSION and saved.get('identity_hash') == identity_hash(context, campaign_type, product, category):
        return saved
    return build_plan(context, campaign_type, product, category, seed, history)


def session_plan(state, identity, context, campaign_type, product, category, seed_factory, *, new=False):
    key = hashlib.sha256(identity.encode()).hexdigest()
    plans = state.setdefault('ads-refresh-plans', {})
    history_key = f'{product}::{campaign_type}'
    histories = state.setdefault('ads-refresh-style-history', {})
    history = histories.setdefault(history_key, [])
    while len(histories) > 30:
        del histories[next(iter(histories))]
    if key not in plans or new:
        plans[key] = build_plan(context, campaign_type, product, category, seed_factory(), history)
        history.append({'run_id': plans[key]['run_id'], 'style_ids': [s['id'] for s in plans[key]['styles']]})
        del history[:-30]
        while len(plans) > 30:
            oldest = next(iter(plans))
            if oldest == key:
                plans[key] = plans.pop(key)
                continue
            del plans[oldest]
    return plans[key]


def standalone_brief(product, reference, *, scene='', role='', style=None, detail=False, dimensions='1080 x 1080'):
    style = style or {}
    return f'''PRODUCT: {product}
REFERENCE: {reference}; inspect this exact attachment. CANONICAL_PRODUCT is the independent immutable product authority.
{AUTHORITY}
Keep/Change/Improvement rationale: after inspecting {reference}, record observed concept, advertising role, product prominence, mood, hierarchy, clutter and copy appeal. Preserve the concept and role; do not claim causal sales evidence for an individual carousel card.
Concept anchor: {scene or 'Determine from this winner attachment; do not substitute another reference'}.
Advertising role: {role or 'Determine from this winner attachment'}.
Candidate execution (subject to visual compatibility): {json.dumps(style, ensure_ascii=False)}
Redesign architecture and layout, wall palette/material and camera composition, plus at least two of furniture, lighting, flooring, background or product placement. Describe each concrete change in the final brief. Keep defining objects (including a pool table for a billiards concept). Never replace a bar with an office. For an intentional detail card preserve its detail function rather than force a room.
Design a genuinely new photograph, not a recolour, crop or angle sibling. Product remains the mobile-readable hero, never a tiny object in a wide interior. Compare with the winner and every sibling; revise near-duplicate rooms, palettes, layouts and copy openings.
Output: square {dimensions}; preserve production safe areas and deterministic branded overlays, do not alter printed artwork. Camera perspective transforms the whole rigid product only. Explicitly describe mounting depth, contact shadow, light direction and restrained glazing reflections in the final execution. {'Intentional detail crop is permitted only for this verified detail-card role; do not invent or redraw details.' if detail else 'Show the full outer black frame.'}
Use an existing source-preserving composite where available. Prompt instructions alone cannot guarantee pixel-perfect fidelity. Do not paste the canonical external stock-photo background rectangle into the new scene.
{build_sports_cave_image_realism_rules(include_product_lock=True, allow_intentional_detail_crop=detail)}'''


def copy_issues(rows, product='', winner=None, fixed_facts=()):
    """Conservative textual duplication checks, not semantic/visual quality claims."""
    issues = []
    def normal(value):
        value = str(value or '').casefold().replace(product.casefold(), '') if product else str(value or '').casefold()
        for fact in fixed_facts:
            value = value.replace(str(fact).casefold(), '')
        return ' '.join(re.findall(r'[a-z]+', value))
    for field in ('primary_text', 'headline', 'description'):
        values = [normal(row.get(field)) for row in rows]
        for i, a in enumerate(values):
            for b in values[:i]:
                opening_a, opening_b = set(a.split()[:8]), set(b.split()[:8])
                reordered_opening = len(opening_a) >= 4 and opening_a == opening_b
                if a and b and (SequenceMatcher(None, a, b).ratio() >= .85 or reordered_opening):
                    issues.append(f'Refresh {field}: repeated or near-identical sibling wording.')
            old = normal((winner or {}).get('winning_'+field))
            if a and old and SequenceMatcher(None, a, old).ratio() >= .9:
                issues.append(f'Refresh {field}: essentially unchanged winner wording.')
    return list(dict.fromkeys(issues))


def asset_issues(slots, source_hashes=()):
    hashes = []
    output_hashes = []
    issues = []
    for slot in slots:
        digest = slot.get('source_hash') or (hashlib.sha256(slot['data']).hexdigest() if slot.get('data') else '')
        output_digest = hashlib.sha256(slot['data']).hexdigest() if slot.get('data') else ''
        if (digest and digest in hashes) or (output_digest and output_digest in output_hashes):
            issues.append('Identical output image assigned to multiple refresh slots.')
        if digest and digest in source_hashes:
            issues.append('Unchanged winner/canonical source assigned as a refreshed image.')
        hashes.append(digest)
        output_hashes.append(output_digest)
    return list(dict.fromkeys(issues))


def execution_issues(executions, refresh_plan, product, campaign_type):
    """Validate declared plans only. This does not certify rendered image fidelity."""
    count = len(refresh_plan.get('references') or []) - 1 if campaign_type == 'Carousel' else 3
    if not isinstance(executions, list) or len(executions) != count:
        return [f'Paste {count} final execution records in refresh notes before marking ready.']
    issues = []
    seen_scenes = []
    by_style = {s['id']: s for s in STYLES}
    styles = []
    scene_signatures = []
    for i, execution in enumerate(executions, 1):
        if not isinstance(execution, dict):
            issues.append(f'Execution {i}: invalid record.')
            continue
        expected = f'WINNER_CARD_{i}' if campaign_type == 'Carousel' else ('WINNER_IE' if campaign_type == 'Instant Experience' else 'WINNER_AD')
        if execution.get('position') != i or execution.get('winner_reference') != expected:
            issues.append(f'Execution {i}: wrong winner reference or order.')
        observations = execution.get('observations') or {}
        if execution.get('reference_inspected') is not True or execution.get('canonical_inspected') is not True:
            issues.append(f'Execution {i}: external winner and canonical attachment inspection is not declared complete.')
        observation_fields = ('scene_category', 'ad_role', 'defining_objects', 'composition', 'product_attention',
                              'strengths', 'clutter', 'mood_contrast', 'copy_hook', 'tone', 'structure', 'emotional_appeal')
        if not isinstance(observations, dict) or not all(str(observations.get(k) or '').strip() for k in observation_fields):
            issues.append(f'Execution {i}: incomplete per-reference observations; do not substitute another winner.')
        if not all(str(execution.get(field) or '').strip() for field in ('scene', 'role', 'keep', 'change', 'improvement', 'image_prompt')):
            issues.append(f'Execution {i}: complete scene, role, keep/change/rationale and standalone brief.')
        dimensions = execution.get('execution') or {}
        is_detail = campaign_type == 'Carousel' and 'detail' in str(execution.get('role') or '').casefold()
        full_rules = build_sports_cave_image_realism_rules(include_product_lock=True, allow_intentional_detail_crop=is_detail)
        required = ('camera', 'lighting', 'product_placement') if is_detail else ('architecture', 'layout', 'wall_palette', 'wall_material', 'camera')
        extras = ('furniture', 'lighting', 'flooring', 'background', 'product_placement')
        if not isinstance(dimensions, dict):
            dimensions = {}
        def resolved(value):
            return bool(str(value or '').strip()) and str(value).casefold().strip() not in {'unknown', 'tbd', 'n/a', 'pending', 'not supplied'}
        if not all(resolved(dimensions.get(k)) for k in required) or (not is_detail and sum(resolved(dimensions.get(k)) for k in extras) < 2):
            issues.append(f'Execution {i}: specify new architecture/layout, wall palette/material, camera and two further scene changes.')
        signature = tuple(str(dimensions.get(k) or '').casefold().strip() for k in required)
        if any(sum(a == b for a, b in zip(signature, old)) >= 4 for old in scene_signatures):
            issues.append(f'Execution {i}: near-identical planned environment; change more than paint/camera.')
        scene_signatures.append(signature)
        winner_dimensions = observations.get('execution') if isinstance(observations, dict) else None
        if isinstance(winner_dimensions, dict) and not is_detail:
            same = [k for k in required if resolved(winner_dimensions.get(k))
                    and str(winner_dimensions[k]).casefold().strip() == str(dimensions.get(k) or '').casefold().strip()]
            if len(same) >= 4:
                issues.append(f'Execution {i}: declared scene barely changes the winner; redesign architecture and layout.')
        prompt = str(execution.get('image_prompt') or '')
        if full_rules not in prompt or AUTHORITY not in prompt or product.casefold() not in prompt.casefold() or expected not in prompt:
            issues.append(f'Execution {i}: missing full shared rules, product authority or exact reference.')
        if campaign_type == 'Carousel':
            anchor = refresh_plan['references'][i-1]
            if anchor.get('scene') and str(anchor['scene']).casefold() != str(execution.get('scene')).casefold():
                issues.append(f'Execution {i}: original carousel scene anchor changed.')
            if anchor.get('role') and str(anchor['role']).casefold() != str(execution.get('role')).casefold():
                issues.append(f'Execution {i}: original carousel role changed.')
        else:
            style = by_style.get(str(execution.get('style_id')))
            if not style:
                issues.append(f'Execution {i}: select a curated style ID after attachment inspection.')
            elif style['context'] == 'motorsport' and not re.search('motorsport|racing|formula|f1', product+' '+refresh_plan.get('category', ''), re.I):
                issues.append(f'Execution {i}: style is incompatible with verified product context.')
            elif any(style['id'] == old['id'] or (style['family'], style['wall_hue']) == (old['family'], old['wall_hue']) for old in styles):
                issues.append(f'Execution {i}: repeated style/family and palette.')
            else:
                styles.append(style)
            scene = ' '.join(str(execution.get('scene') or '').casefold().split())
            if scene and scene in seen_scenes:
                issues.append(f'Execution {i}: repeated environment declaration.')
            seen_scenes.append(scene)
    return issues
