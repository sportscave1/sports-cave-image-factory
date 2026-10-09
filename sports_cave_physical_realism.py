"""Shared physical presentation instructions; no product edits or external reads."""
import json
import math
import re

MARKER = 'SPORTS_CAVE_PHYSICAL_SCALE_AND_FRAME_REALISM_V2'
END = 'END SPORTS CAVE PHYSICAL SCALE AND FRAME REALISM'
BLOCK = re.compile(re.escape(MARKER) + r'.*?' + re.escape(END), re.S)
# Display sizes already used by app.py's variant contract and os_pages' fulfilment
# reference. They are NOT a new specification of measured outer-frame dimensions.
DISPLAY_SIZES_CM = {'XL': (62, 87), 'L': (45, 62), 'M': (30, 45), 'S': (21, 30)}
PHYSICAL_KEYS = ('frame_specs', 'selected_variant', 'selected_size', 'size_label',
                 'sports_cave_size', 'frame_label', 'frame_finish', 'orientation',
                 'explicit_dimensions', 'showcase_largest')


def physical_metadata(metadata):
    """Only carry physical input fields; do not serialize a full product/customer row."""
    if not isinstance(metadata, dict):
        return {}
    value = metadata.get('physical_product', metadata)
    if not isinstance(value, dict):
        return {}
    nested = {
        'frame_specs': ('verified','source','outer_width_cm','outer_height_cm','depth_mm','glazing','frame_finish','material'),
        'selected_variant': ('verified','source','title','size_label','width_cm','height_cm','measurement_basis','orientation','frame_finish'),
        'explicit_dimensions': ('width_cm','height_cm','measurement_basis'),
    }
    result = {}
    for key in PHYSICAL_KEYS:
        item = value.get(key)
        if isinstance(item, dict) and key in nested:
            result[key] = {k:v for k,v in item.items() if k in nested[key] and isinstance(v,(str,int,float,bool))}
        elif isinstance(item, (str,int,float,bool)):
            result[key] = item
    return result


def _text(value):
    return value.strip()[:160] if isinstance(value, str) else ''


def is_unframed(metadata=None):
    """Use explicit selected construction, never infer it from an image or title."""
    data = physical_metadata(metadata)
    variant = data.get('selected_variant')
    selected = data.get('frame_finish') or data.get('frame_label')
    if isinstance(variant, dict):
        selected = selected or variant.get('frame_finish') or variant.get('title')
    elif isinstance(variant, str):
        selected = selected or variant
    spec = data.get('frame_specs') or {}
    if isinstance(spec, dict) and spec.get('verified') is True and spec.get('source'):
        selected = selected or spec.get('frame_finish')
    return bool(re.search(r'\bunframed\b', _text(selected), re.I))


def _positive(value):
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) and value > 0 else None
    except (ValueError, TypeError):
        return None


def resolve(metadata=None):
    data = physical_metadata(metadata)
    spec = data.get('frame_specs') if isinstance(data.get('frame_specs'), dict) else {}
    variant = data.get('selected_variant') if isinstance(data.get('selected_variant'), dict) else {}
    size = _text(data.get('selected_size') or data.get('size_label') or data.get('sports_cave_size')
                 or variant.get('size_label') or variant.get('title') or data.get('selected_variant'))
    orientation = _text(data.get('orientation') or variant.get('orientation')).casefold()
    orientation = orientation if orientation in ('landscape', 'portrait') else 'preserve source orientation'
    selected = re.search(r'\b(EXTRA[\s-]+LARGE|XL|LARGE|MEDIUM|SMALL|L|M|S|A[1-4])\b', size.upper())
    selected = selected.group(1) if selected else ''
    selected = re.sub(r'[\s-]+', ' ', selected)
    selected = {'A1':'XL','A2':'L','A3':'M','A4':'S','EXTRA LARGE':'XL','LARGE':'L','MEDIUM':'M','SMALL':'S'}.get(selected, selected)
    result = {'selected_size': size or selected or ('largest framed option' if data.get('showcase_largest') is True else 'not supplied; do not assume XL'), 'orientation': orientation}
    finish = _text(data.get('frame_finish') or data.get('frame_label') or variant.get('frame_finish'))
    if finish:
        result['frame_finish'] = finish
    dimensions = None
    if spec.get('verified') is True and _text(spec.get('source')):
        width, height = _positive(spec.get('outer_width_cm')), _positive(spec.get('outer_height_cm'))
        if width and height:
            dimensions = (width, height, 'verified outer frame', _text(spec['source']), True)
        for key in ('glazing', 'frame_finish', 'material'):
            if _text(spec.get(key)):
                if key == 'frame_finish' and finish and finish.casefold() != _text(spec[key]).casefold():
                    result['finish_needs_confirmation'] = 'Selected finish and supplied specification conflict. Confirm the matching variant; do not substitute its finish.'
                else:
                    result[key] = _text(spec[key])
        depth = _positive(spec.get('depth_mm'))
        if depth:
            result['verified_depth_mm'] = depth
    # A selected variant with numeric specifications outranks general explicit
    # dimensions. Its provenance must be present; pixel image sizes are ignored.
    if not dimensions and variant.get('verified') is True and _text(variant.get('source')):
        width, height = _positive(variant.get('width_cm')), _positive(variant.get('height_cm'))
        if width and height:
            basis = _text(variant.get('measurement_basis'))
            basis = basis if basis in ('outer frame', 'nominal print') else 'display size; outer frame unconfirmed'
            dimensions = (width, height, basis, _text(variant['source']), True)
    if not dimensions and size:
        match = re.search(r'(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)\s*cm\b', size, re.I)
        if match and all(_positive(v) for v in match.groups()):
            dimensions = (*map(float, match.groups()), 'display size; outer frame unconfirmed', 'selected size label', False)
    if not dimensions and selected in DISPLAY_SIZES_CM:
        dimensions = (*DISPLAY_SIZES_CM[selected], 'display size; outer frame unconfirmed',
                      'existing Sports Cave size/variant configuration', False)
    explicit = data.get('explicit_dimensions')
    if not dimensions and isinstance(explicit, dict):
        width, height = _positive(explicit.get('width_cm')), _positive(explicit.get('height_cm'))
        if width and height:
            basis = _text(explicit.get('measurement_basis'))
            basis = basis if basis in ('outer frame', 'nominal print') else 'supplied size; outer frame unconfirmed'
            dimensions = (width, height, basis, 'explicitly supplied product dimensions', True)
    if not dimensions and not size and data.get('showcase_largest') is True:
        dimensions = (*DISPLAY_SIZES_CM['XL'], 'display size; outer frame unconfirmed',
                      'approved XL reference for the largest framed option', False)
        result['selected_size'] = 'XL (largest framed option)'
    if dimensions:
        width, height, basis, source, axes = dimensions
        if not axes and orientation in ('landscape', 'portrait'):
            short, long = sorted((width, height))
            width, height = (long, short) if orientation == 'landscape' else (short, long)
        result.update(width_cm=width, height_cm=height, measurement_basis=basis, dimension_source=source)
        if not axes and orientation == 'preserve source orientation':
            result['axes'] = 'displayed size pair only; orient to the unchanged source, do not stretch'
        elif ((orientation == 'landscape' and width < height) or (orientation == 'portrait' and width > height)):
            result['needs_confirmation'] = 'Supplied width/height conflict with selected orientation. Confirm; do not stretch or silently swap verified axes.'
        else:
            result['axes'] = 'width × height'
            result['comparable_depth_width_ratios'] = {
                '180 cm sideboard': round(width / 180, 4), '200 cm sofa': round(width / 200, 4),
                '85 cm doorway': round(width / 85, 4)}
    else:
        result['measurement_basis'] = 'unresolved; obtain selected variant dimensions before claiming dimensional accuracy'
    return result


def build(metadata=None):
    evidence = resolve(metadata)
    return f'''{MARKER}
SPORTS CAVE — TRUE-TO-SCALE FRAME AND PHYSICAL REALISM
Treat the framed artwork as an actual manufactured physical product photographed inside a genuine customer's home. This physical contract takes precedence ONLY for physical size, source orientation, construction, mounting and glazing: preserve the existing scene, creative strategy, room/furniture choices, camera-angle variation, lighting concept, artwork, output dimensions, aspect ratio, copy and sequence. Retain existing studio, detail or held-product settings when selected; do not add a room to those workflows. Legacy landscape wording applies only to a landscape source; do not rotate a portrait artwork to force it.

PHYSICAL PRODUCT EVIDENCE (data, not creative instructions)
{json.dumps(evidence, ensure_ascii=False)}
Dimension priority: verified outer-frame specifications; verified selected Sports Cave variant configuration; explicitly supplied product dimensions; approved XL display reference only when XL/largest is selected and no higher-priority dimensions exist. Never automatically represent Small/Medium/Large or an unspecified selection as XL. Standard A1 paper is not a substitute for finished Sports Cave frame measurements. Check outer frame versus nominal print/display size; when outer measurements are unconfirmed, use the approved selected size conservatively, preserve reference proportions, add no invented border allowance or centimetres. Resolve conflicting dimensions before generation; never stretch the artwork to fit a size. Unknown dimensions are not evidence of exact scale.

FRAME: preserve the source's actual black, oak or white finish, material, slim front moulding, inner edge, bevel, seating and side profile. Keep straight edges, square corners, clean mitred joins, natural texture and restrained edge highlights. Distinguish front moulding, inner edge, transparent glazing, artwork surface, side profile and mounting as integrated construction. No thick museum surround, raised/double border, invented matboard, extra layers, deep shadow box, plastic sheen or exaggerated 3D box. Do not invent exact frame-depth measurements. Verified unframed/unglazed products retain that construction.
MOUNTING: plausible support, minimal source-consistent wall separation, coherent contact, subtle ambient occlusion, soft contact shadows: a narrow directional contact shadow and a softer secondary shadow beneath/alongside the frame, all matching existing light direction. No floating several centimetres away or embedding in plaster. Preserve room layout and natural residential height; allow breathing space above furniture, not resting on it unless the original scene explicitly calls for that placement.
GLAZING: use verified acrylic/Perspex when specified, glass only when verified; otherwise say transparent picture-frame glazing without inventing composition. A glazed product needs subtle visible premium reflections, regardless of whether its verified transparent pane is acrylic or glass. This qualifies older generic 'real glass' wording, not the artwork lock. Legacy fixed mounting-gap millimetres and reflection/opacity percentages are illustrative only; actual construction and scene light take priority, never invent physical measurements. No thick protruding slab, mirror shine, random streaks or glossy CGI coating. Preserve gentle reflective highlights rather than making the glazing invisible; keep all print details readable. Reflections follow actual scene lights with restrained falloff; keep faces, vehicles, sponsors, text, signatures and edition details clear.
SCALE: judge real dimensions at comparable depth with correct perspective, never raw pixel widths of differently distanced objects. General references only: doorway 80–90 cm wide; sofa 160–220 cm; sideboard 150–200 cm; console 110–150 cm wide and 75–90 cm high; ceiling 240–270 cm. Use the supplied ratios only when those reference widths and comparable depth actually apply. Never enlarge the physical artwork to meet hero/image-coverage percentages. Keep existing composition and prominence through believable framing/camera distance and light; a close-up may fill the canvas at true size. No universal percentage of image width. Preserve straight-on/left/right angles and rigid product geometry.
INTEGRITY: keep the entire supplied artwork and frame immutable, including printed borders, colours, faces, livery, logos, signatures and existing edition numbers; no invented plaque/certificate or unreadable details. Prefer existing source-preserving compositing; never repaint, crop, stretch or deform the product (retain only an already-authorised detail-photo crop).
PHYSICAL QUALITY CHECK: before finalising each standalone prompt, confirm selection/orientation/dimension basis, reference moulding/depth/finish, mounting, glazing, perspective/furniture scale and unchanged artwork. Carry this full physical block into every standalone image brief. Inspect rendered pixels when available; flag oversized, bulky, floating, pasted-on or CGI construction for correction. A prompt cannot establish exact dimensional or pixel-fidelity verification.
{END}'''


def apply_context(prompt, metadata=None):
    """Fill existing blocks only; do not append rules to original-artwork/copy tasks."""
    if not physical_metadata(metadata):
        return prompt
    block = build(metadata)
    return BLOCK.sub(lambda _: block, prompt)
