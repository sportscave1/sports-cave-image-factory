"""Versioned read-only references. Supplier requirements, never storefront labels, approve prints."""
import json
import math
import re
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def registry():
    return json.loads((Path(__file__).parent / 'data/print_specifications.json').read_text(encoding='utf-8'))


def for_variant(variant):
    match = re.match(r'^(Black|Oak|White|Unframed)\s*/\s*(XL|L|M|S)\b', str(variant or ''), re.I)
    if not match:
        return None
    return next((s for s in registry()['specifications'] if s['frame'].casefold() == match[1].casefold() and s['size'] == match[2].upper()), None)


def verified(spec):
    if not spec or spec.get('verification_status') != 'Verified supplier':
        return False
    pixels = spec.get('pixel_dimensions')
    horizontal, vertical = spec.get('horizontalResolution'), spec.get('verticalResolution')
    if horizontal is not None or vertical is not None:
        if pixels != [horizontal, vertical]:
            return False
    return bool(spec.get('prodigi_sku') and spec.get('source') and isinstance(pixels, list) and len(pixels) == 2
                and all(type(v) is int and v > 0 for v in pixels) and spec.get('printable_mm')
                and spec.get('bleed_mm') is not None and spec.get('margins_mm') is not None
                and spec.get('colour', {}).get('profile') and spec.get('colour', {}).get('mode'))


def _geometry(spec):
    """Supplier canvas dimensions include declared bleed. Insets: left, top, right, bottom."""
    def values(name, count, positive=False):
        value = spec.get(name)
        if not isinstance(value, list) or len(value) != count or any(
            isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n)
            or (n <= 0 if positive else n < 0) for n in value
        ):
            raise ValueError('Verified supplier ' + name + ' is missing or invalid.')
        return value
    canvas = values('printable_mm', 2, True)
    bleed, margins = values('bleed_mm', 4), values('margins_mm', 4)
    safe = [(bleed[0] + margins[0]) / canvas[0], (bleed[1] + margins[1]) / canvas[1],
            1 - (bleed[2] + margins[2]) / canvas[0], 1 - (bleed[3] + margins[3]) / canvas[1]]
    if safe[0] >= safe[2] or safe[1] >= safe[3]:
        raise ValueError('Supplier safe print area is empty.')
    return safe


def compatible(master, target, layout):
    """No implicit crop/rotation/padding. Uses an explicitly approved artwork safe region."""
    if not verified(master) or not verified(target):
        return {'status': 'Unverified', 'reason': 'Supplier pixels, bleed, margins and colour are unverified.'}
    if not layout or layout.get('verified') is not True or not layout.get('source'):
        return {'status': 'Unverified', 'reason': 'Approved artwork safe-region evidence is missing.'}
    try:
        master_safe, target_safe = _geometry(master), _geometry(target)
        width, height = master['pixel_dimensions']
        tw, th = target['pixel_dimensions']
        if tw > width or th > height:
            return {'status': 'Separate layout', 'reason': 'Target exceeds the approved XL master requirement.'}
        # Exact proportional supplier canvases only. Unverified rounding/crop tolerance is not inferred.
        if width * th != height * tw or master['printable_mm'][0] * target['printable_mm'][1] != master['printable_mm'][1] * target['printable_mm'][0]:
            return {'status': 'Separate layout', 'reason': 'Supplier print-area ratios differ; a separate approved layout is required.'}
        if master['colour'] != target['colour']:
            return {'status': 'Separate layout', 'reason': 'Supplier colour requirements differ.'}
        dimensions = layout.get('dimensions')
        bounds = layout.get('protected_bounds')
        if not isinstance(dimensions, list) or len(dimensions) != 2 or any(type(v) is not int or v <= 0 for v in dimensions):
            raise ValueError('Approved artwork dimensions are invalid.')
        if not isinstance(bounds, list) or len(bounds) != 4 or any(type(v) not in (int, float) or not math.isfinite(v) for v in bounds):
            raise ValueError('Approved badge/artwork bounds are missing.')
        if not (0 <= bounds[0] < bounds[2] <= dimensions[0] and 0 <= bounds[1] < bounds[3] <= dimensions[1]):
            raise ValueError('Approved artwork bounds are invalid.')
        # Whole artwork must resize to the XL canvas without adding padding or cropping.
        if round(dimensions[1] * width / dimensions[0]) != height:
            return {'status': 'Separate layout', 'reason': 'Artwork ratio does not fit the XL canvas without crop or padding.'}
        normal = [bounds[0]/dimensions[0], bounds[1]/dimensions[1], bounds[2]/dimensions[0], bounds[3]/dimensions[1]]
        safe = [max(master_safe[0], target_safe[0]), max(master_safe[1], target_safe[1]),
                min(master_safe[2], target_safe[2]), min(master_safe[3], target_safe[3])]
        if normal[0] < safe[0] or normal[1] < safe[1] or normal[2] > safe[2] or normal[3] > safe[3]:
            return {'status': 'Separate layout', 'reason': 'Badge or essential artwork enters supplier bleed/safe margins.'}
    except (ValueError, TypeError, KeyError) as error:
        return {'status': 'Unverified', 'reason': str(error)}
    return {'status': 'Shared master', 'reason': 'Approved proportional downscale; badge and artwork remain within safe margins.',
            'sizing': 'fitPrintArea'}


def master_plan(variant, layout=None):
    """One XL asset for an exact unit; target sizes never select independent generators."""
    selected = for_variant(variant)
    if not selected:
        return {'status': 'Unverified', 'reason': 'Mapped variant specification is missing.', 'sizes': {}}
    family = [s for s in registry()['specifications'] if s['frame'] == selected['frame']]
    masters = [s for s in family if s['size'] == 'XL']
    if len(masters) != 1 or not verified(masters[0]):
        return {'status': 'Unverified', 'reason': 'The mapped XL SKU supplier requirement is unverified.', 'sizes': {}}
    master = masters[0]
    if master.get('colour', {}).get('mode') != 'RGB':
        return {'status': 'Unverified', 'reason': 'The current Photoshop exporter requires an approved RGB specification.', 'sizes': {}}
    sizes = {}
    for size in ('XL', 'L', 'M', 'S'):
        targets = [s for s in family if s['size'] == size]
        sizes[size] = compatible(master, targets[0], layout) if len(targets) == 1 else {
            'status': 'Unverified', 'reason': 'Exactly one mapped supplier specification is required.'}
    result = sizes.get(selected['size'], {'status': 'Unverified', 'reason': 'Unknown mapped size.'})
    # An unusable XL canvas cannot be the common source even if a smaller target fits.
    if sizes['XL']['status'] != 'Shared master':
        result = sizes['XL']
    return {'status': result['status'], 'reason': result['reason'], 'master': master,
            'sizes': sizes, 'shared_sizes': [size for size, result in sizes.items() if result['status'] == 'Shared master'],
            'strategy': 'largest_approved_size_first'}


def render_reference(st):
    with st.expander('Print Specifications', expanded=False):
        st.caption('Read-only references. Storefront sizes do not approve a Prodigi print. No fulfilment mappings are changed.')
        st.dataframe([{'Size': k, 'Storefront cm': ' × '.join(str(v / 10) for v in r['physical_mm']),
                       '300 PPI reference': ' × '.join(map(str, r['pixels_300ppi'])), 'Status': r['verification_status']}
                      for k, r in registry()['storefront_references'].items()], hide_index=True, use_container_width=True)
        st.dataframe([{'Frame': s['frame'], 'Size': s['size'], 'Prodigi SKU': s['prodigi_sku'],
                       'Print area': ' × '.join(map(str, s['printable_mm'])) if s['printable_mm'] else 'Not verified', 'Status': s['verification_status']} for s in registry()['specifications']],
                     hide_index=True, use_container_width=True)
        frame = st.selectbox('Frame specification', ['Black', 'Oak', 'White', 'Unframed'], key='print-spec-reference-frame')
        size = st.selectbox('Size specification', ['S', 'M', 'L', 'XL'], key='print-spec-reference-size')
        st.json(for_variant(f'{frame} / {size}'))
        for warning in registry()['warnings']:
            st.caption(warning)
        st.caption('One approved XL JPG per edition/order-line unit. Smaller sizes reuse it only after ratio, bleed, safe-margin and colour checks; no automatic crop, stretch or padding.')
