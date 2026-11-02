"""Opt-in policy for freshly resolved USA IE packs; no storage or backend."""
import hashlib
import re

VERSION = 'USA IE PRODUCT FIRST V1'
HEADLINE = 'Limited to 100 Worldwide'
FINALITY = 'Once it sells out, it’s done.'
FALLBACK = 'A limited run of 100 editions.'
GLAZING = ('For every framed edition: Show believable premium glass reflections while preserving immediate recognition of faces, action and defining edition text. '
           'Keep strong reflections away from those areas. At thumbnail size, product recognition takes priority over reflection visibility. '
           'Preserve premium glass, never an acrylic appearance or pasted-on product. Keep realistic frame-edge highlights and mounting shadows; '
           'no bright window grids across important details. Preserve unframed products without adding a frame or pane.')
COMPOSITION = ('USA PRODUCT-FIRST COMPOSITION: Preserve the collector hallway, straight-on architectural product wall and residential man cave, '
               'with their assigned RIGHT / FRONT / LEFT cameras. Use three recognisably different residential compositions; neutral colour families '
               'and understated wall finishes may repeat. Priority: product fidelity and real scale; subject and defining-detail recognition; desirable '
               'residential presentation; meaningful composition variety; then environmental novelty. Moderate perspective, no extreme foreshortening. '
               'Move the camera closer when needed, never enlarge the product. Keep the full frame, breathing room and footer clearance. '
               'A wider residential view is valid when the edition remains recognisable and the setting contributes. At approximately 256 × 256, '
               'recognise the subject and defining action; read main lettering where the source permits. Never invent, enlarge or redesign small source text. '
               'Keep furniture, bright windows and patterns subordinate. Coherent natural or warm directional light must not darken faces or key details. '
               'Use the supplied edition colours, contrast and mood; never recolour the product or add compulsory team colours, flags, neon or invented memorabilia. '
               'Recent history prevents accidental near-duplicates, not reuse of effective neutral settings across products. Inspect actual images before claiming visual quality.')
WALL_RULES = ('USA automatic walls prioritise warm greige, stone beige, sand, medium earthy taupe and soft warm off-white when the source supports it; '
              'charcoal or smoky grey require clear frame separation. Deep navy, heritage green and muted olive are secondary options only when supplied '
              'edition colours support them. Prefer calm matte paint, fine plaster and restrained stone/concrete. Keep pronounced masonry, timber joins '
              'and strong material details peripheral. No fixed colour per slot or stereotyped American sports-bar styling.')
COPY_RULES = ('USA SUPPORTING WORDING: Keep legacy_standard, framed_greatness and choose_a_side in their existing order, line/blank-line positions, '
              'approximate length and distinct approaches. Preserve signature hooks, approved scarcity, ownership closes and CTA. '
              'Generic supporting sentences are editable in their existing positions: “It’s a statement of {identity} identity.”, '
              '“Made for fans who know why it matters.” and “Made for collectors who want their {sport} identity on display.” '
              'may express this exact edition’s meaning instead. Retain “This isn’t wall art.”, “Greatness doesn’t fade. / It gets framed.” '
              'and the Choose a Side question/response, “You already know the answer.” and ownership close. '
              'No shared storytelling formula, biographies, invented rivalries, quotes, adversity, achievements or viewer memories. '
              'Use natural American spelling in flexible copy; preserve protected names and source-edition text.')
WALLS = (
    ('warm greige', 'greige', 'mid', 'neutral', 'matte painted wall'),
    ('stone beige', 'beige', 'light', 'neutral', 'fine plaster'),
    ('sand', 'sand', 'light', 'neutral', 'restrained stone'),
    ('medium earthy taupe', 'taupe', 'mid', 'neutral', 'fine plaster'),
    ('soft warm off-white', 'off-white', 'light', 'neutral', 'matte painted wall'),
    ('smoky grey', 'grey', 'mid', 'grey', 'restrained concrete'),
    ('charcoal', 'charcoal', 'dark', 'grey', 'matte painted wall'),
    ('deep navy', 'navy', 'dark', 'blue', 'matte painted wall'),
    ('heritage green', 'green', 'mid', 'green', 'fine plaster'),
    ('muted olive', 'olive', 'mid', 'olive', 'fine plaster'),
)


def enabled(normalized_country, metadata):
    if normalized_country != 'USA':
        return False
    metadata = metadata or {}
    saved = list(metadata.get('instant_experience_scene_selections') or ())
    footers = metadata.get('instant_experience_footer_selections') or ()
    # Old or explicitly supplied specifications are authoritative, not a request to regenerate.
    return (not saved and not footers) or (len(saved) == 3 and all(isinstance(s, dict) and s.get('scene_selection_version') == VERSION for s in saved))


def resolve_footer(visuals, context, headline_is_valid, pair_is_valid, selections=()):
    if len(visuals) != 3:
        raise ValueError('USA IE requires exactly three visuals.')
    support = FINALITY if context.get('no_second_run_verified') is True or context.get('retires_when_sold_out') is True else FALLBACK
    if selections:
        pairs = [(s.get('headline_text'), s.get('supporting_line')) for s in selections]
        if len(pairs) != 3 or len(set(pairs)) != 1 or pairs[0][0] != HEADLINE or pairs[0][1] not in (FINALITY, FALLBACK):
            raise ValueError('Preserve the supplied USA footer; inconsistent saved selections require explicit regeneration.')
        support = pairs[0][1]  # Do not reinterpret an approved resolved pack on export.
    if not headline_is_valid(HEADLINE) or (pair_is_valid and not pair_is_valid(HEADLINE, support)):
        raise ValueError('USA fixed footer must pass existing copy-fit limits.')
    for v in visuals:
        v.update(headline_text=HEADLINE, supporting_line=support, fomo_line=support, cta_text='CLAIM YOUR EDITION',
                 footer_emphasis='scarcity', footer_pair_signature=hashlib.sha256(f'{HEADLINE}|{support}'.encode()).hexdigest()[:20],
                 eligible_headline_alternatives=[], headline_fit_fallback=HEADLINE)


def distinct(a, b):
    return a['home_setting'] != b['home_setting'] and (
        a['spatial_family'] != b['spatial_family'] or a['depth_position'] != b['depth_position'])


def select_scenes(seed, context, recent=(), selections=()):
    from ads_ie_scenes import SCENES, signature, _rank, HISTORY_LIMIT
    metadata = context.get('product_metadata') or {}
    palette = ' '.join(str(metadata.get(k, '')) for k in ('artwork_colours', 'artwork_colors', 'dominant_colours', 'dominant_colors', 'colour_palette')).lower()
    frame = str(context.get('frame_finish', '')).lower()
    history = [r for r in list(recent)[:HISTORY_LIMIT] if isinstance(r, dict)]
    pools = []
    for slot in SCENES:
        pool = []
        for original in slot:
            # Retain curated homes, roles, architecture and lights; change only eligible wall treatments.
            for wi, wall in enumerate(WALLS):
                if wi >= 7 and wall[1] not in palette:
                    continue
                s = dict(original)
                colour, family, lightness, group, finish = wall
                s.update(scene_selection_version=VERSION, scene_id=original['scene_id']+'|usa:'+str(wi),
                         wall_colour=colour, wall_colour_family=family, wall_lightness=lightness,
                         wall_visual_group=group, wall_finish=finish, wall_material=finish)
                s['scene_signature'] = signature(s)
                s['scene_near_signature'] = signature(s, near=True)
                pool.append(s)
        def rank(s):
            matching_accent = s['wall_colour_family'] in palette and s['wall_visual_group'] in ('blue', 'green', 'olive')
            dark_frame = 'black' in frame and s['wall_lightness'] == 'dark'
            return (dark_frame, s['wall_visual_group'] != 'neutral' and not matching_accent, _rank(seed, s['scene_signature']))
        # Multiple old candidates can share the new wall: keep one resolved composition each.
        pools.append(sorted({s['scene_signature']:s for s in pool}.values(), key=rank))
    for keep in range(len(history), -1, -1):
        filtered = [[s for s in pool if not any(
            old.get('scene_signature') == s['scene_signature'] or old.get('scene_near_signature') == s['scene_near_signature']
            for old in history[:keep])] for pool in pools]
        for a in filtered[0]:
            for b in filtered[1]:
                if not distinct(a,b): continue
                c = next((c for c in filtered[2] if distinct(a,c) and distinct(b,c)),None)
                if c:
                    return [dict(s, history_exclusions_relaxed=len(history)-keep) for s in (a,b,c)]
    raise ValueError('USA IE needs three distinct residential compositions.')


def adapt_prompt(prompt):
    """Replace only the conflicting shared directives, before returning a newly resolved USA prompt."""
    from ads_ie_visual_systems import GLAZING_REQUIREMENT, SCENE_VISIBILITY_RULES
    from ads_ie_scenes import ROOM_STYLE
    prompt = prompt.replace(GLAZING_REQUIREMENT, GLAZING).replace(SCENE_VISIBILITY_RULES.strip(), COMPOSITION+' '+WALL_RULES)
    prompt = prompt.replace(ROOM_STYLE, WALL_RULES)
    prompt = re.sub(r'PACK COMPOSITION:.*?(?=\n\n)', COMPOSITION+' '+WALL_RULES, prompt, flags=re.S)
    prompt = re.sub(r'MANDATORY CREATIVE VARIETY AND TYPOGRAPHY:.*?(?=\n)', COMPOSITION+' Preserve the existing restrained typography; resolve choices before exactly one image per ad.', prompt)
    replacements = {
        'Premium collector hallway: close edition-led photography': 'Premium collector hallway: edition-led photography',
        'retain close edition prominence.': 'retain recognisable edition prominence.',
        'GLAZING CHECK: Every framed edition must show believable surface reflections clearly visible at thumbnail size.': 'GLAZING CHECK: Product recognition takes priority over reflection visibility at thumbnail size.',
        'Confirm three different approved footer headlines and distinct supporting lines in every set; preserve the assigned selections verbatim.': 'Confirm the identical fixed USA footer headline and approved supporting line across all three images; preserve the assigned selections verbatim.',
        'three visibly different homes/walls/light': 'three recognisably different residential compositions',
        'flag missing or imperceptible surface reflections on every framed edition at 256 × 256 (frame-edge highlights alone do not count)': 'check premium glazing without obscuring faces, action or defining edition text; thumbnail recognition takes priority',
        'approved selected headline and supporting-line wording, with maximum eligible variety': 'the identical exact USA footer headline and approved supporting line on all three images',
        'Select three different approved headlines for a fresh pack; no within-pack repeats.': 'Repeat the fixed USA footer headline and approved supporting line across all three images.',
        'Never repeat a headline or subline within this three-image set; CTA and banner styling stay shared.': 'Repeat the exact fixed USA footer headline, approved supporting line and CTA in all three images.',
        'Keep all signature and fixed template lines verbatim, including': 'Keep signature hooks, scarcity and ownership closes verbatim; generic supporting lines are editable in place. Preserve',
        'Keep the three hook families, mandatory lines and ownership closes even when recent history contains them.': 'Keep the three signature hook families, approved scarcity and ownership closes even when history contains them; personalise generic supporting lines in their existing positions.',
        '- Wall colour and cues differ from the other routes.': '- Composition cues distinguish the routes; neutral wall colours and finishes may repeat.',
        '- Room type, architecture, furniture layout, lighting and atmosphere must visibly differ; decorative styling stays restrained and product-led.': '- Use recognisably distinct residential compositions; not every environmental attribute needs to differ.',
    }
    for old,new in replacements.items(): prompt = prompt.replace(old,new)
    return prompt
