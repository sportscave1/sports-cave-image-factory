"""Selected-SKU sizing for shared masters; no source, approval or archive writes."""
import math

from auto_editions_resolution import supplier_reference
import print_specifications

VERSION = 'selected-sku-fractional-v1'


def proportional_dimensions(source, width):
    """Photoshop width-only resize: nearest integer height, never stretch/crop."""
    return [width, int(math.floor(source[1] * width / source[0] + .5))]


def references(variant='', variants=None, sku=None):
    """Product masters are shared. Retain the largest mapped size in each family.

    No selected/cached commerce variant means no supplier target is invented.
    Unknown families stay unverified even when another family has a known target.
    """
    found = {}
    titles=sorted({title for title in [variant]+list(variants or []) if isinstance(title,str) and title})
    if sku and not titles:
        titles=[f'{s["frame"]} / {s["size"]}' for s in print_specifications.registry()['specifications']
                if s['prodigi_sku']==sku]
    for title in titles:
        mapped = print_specifications.for_variant(title)
        if not mapped:
            continue
        if sku and mapped.get('prodigi_sku') != sku:
            continue
        family = [s for s in print_specifications.registry()['specifications'] if s['frame'] == mapped['frame']]
        for candidate in family:
            spec = supplier_reference(f'{candidate["frame"]} / {candidate["size"]}', candidate['prodigi_sku'])
            if spec:
                found[spec['sku']] = spec
    return [found[key] for key in sorted(found)]


def plan(source, legacy_scale, *, variant='', variants=None, sku=None,
         crop_bounds_px=None, max_pixels=95_000_000):
    """Keep successful legacy results, supplement undersized ones fractionally.

    A known supplier crop in source coordinates increases the required full
    canvas size; it never crops the source. Printable supplier canvases already
    include declared bleed. Unknown bleed/crop remains an explicit estimate.
    """
    if (not isinstance(source, list) or len(source) != 2 or
            any(type(n) is not int or n <= 0 for n in source)):
        raise ValueError('Positive integer source dimensions required.')
    if type(legacy_scale) is not int or legacy_scale not in (1, 2, 3, 4):
        raise ValueError('Legacy preparation scale must be 1, 2, 3 or 4.')
    legacy = [n * legacy_scale for n in source]
    if legacy[0] * legacy[1] > max_pixels:
        raise ValueError('Source or requested legacy scale exceeds the worker budget.')
    specs = references(variant, variants, sku)
    fraction = [1, 1]
    if crop_bounds_px is not None:
        if (not isinstance(crop_bounds_px, list) or len(crop_bounds_px) != 4
                or any(type(n) not in (int, float) or not math.isfinite(n) for n in crop_bounds_px)):
            raise ValueError('Known supplier crop bounds are invalid.')
        x0, y0, x1, y1 = crop_bounds_px
        if not (0 <= x0 < x1 <= source[0] and 0 <= y0 < y1 <= source[1]):
            raise ValueError('Known supplier crop is outside the source.')
        fraction = [(x1 - x0) / source[0], (y1 - y0) / source[1]]
    required = [0, 0]
    for spec in specs:
        physical = sorted(spec['printable_mm'], reverse=source[0] >= source[1])
        pixels = [round(mm * spec['recommended_ppi'] / 25.4) for mm in physical]
        configured = spec.get('pixel_dimensions')
        if isinstance(configured, list) and len(configured) == 2:
            pixels = [max(a, b) for a, b in zip(pixels, sorted(configured, reverse=source[0] >= source[1]))]
        required = [max(old, math.ceil(px / part)) for old, px, part in zip(required, pixels, fraction)]
    output = legacy
    desired = None
    status = 'target_not_verified'
    if specs:
        status = 'target_met'
        if any(n < target for n, target in zip(legacy, required)):
            width = max(source[0], required[0], math.ceil(source[0] * required[1] / source[1]))
            desired = proportional_dimensions(source, width)
            if desired[0] * desired[1] <= max_pixels:
                output = desired
            else:
                status = 'below_target_worker_budget'
    return dict(version=VERSION, scope='shared_product_master_largest_known_sku',
                source_dimensions=source, required_dimensions=required if specs else None,
                output_dimensions=output, scale=round(output[0] / source[0],12),legacy_scale=legacy_scale,
                references=specs, crop_bounds_px=crop_bounds_px,
                estimate_before_supplier_crop=crop_bounds_px is None,
                bleed_verified=bool(specs) and all(s['includes_bleed'] for s in specs),
                resolution_status=status, requested_dimensions=desired,
                worker_max_pixels=max_pixels, supplier_verified=False, print_ready=False)


def _scale(value):
    # ExtendScript serializes numbers to ~15 significant digits. Pixel dimensions
    # remain exact; compare scale evidence at a stable 12 decimal places.
    return round(value, 12) if type(value) in (int, float) and math.isfinite(value) else None


def validate(source, dimensions, geometry):
    """Validate a recorded plan structurally without invalidating historic specs."""
    record = geometry.get('plan') or {}
    if (record.get('version') != VERSION or record.get('source_dimensions') != source
            or record.get('output_dimensions') != dimensions
            or record.get('worker_max_pixels') != 95_000_000
            or dimensions[0] * dimensions[1] > 95_000_000
            or dimensions[0] < source[0] or dimensions[1] < source[1]
            or dimensions != proportional_dimensions(source, dimensions[0])
            or _scale(geometry.get('scale')) != _scale(dimensions[0] / source[0])
            or _scale(record.get('scale')) != _scale(geometry.get('scale'))
            or geometry.get('method') != ('native' if dimensions == source else 'photoshop_layered_bicubic_smoother')
            or geometry.get('supplier_verified') is not False
            or geometry.get('quality_approval_required') is not (dimensions != source)
            or record.get('supplier_verified') is not False or record.get('print_ready') is not False):
        raise ValueError('Fractional preparation requires a pinned proportional TEST geometry plan.')


def for_context(source, ctx, *, legacy_scale=None):
    from auto_editions_onboarding import preparation_scale
    return plan(source, preparation_scale(source) if legacy_scale is None else legacy_scale,
                variant=ctx.get('variant_title', ''), variants=ctx.get('preparation_variants'),
                sku=ctx.get('supplier_sku'),crop_bounds_px=ctx.get('supplier_crop_bounds_px'))


def matches(manifest, ctx):
    """Only future preparations use new targets. Archived outputs are not visited."""
    source = manifest.get('source_dimensions', manifest.get('dimensions'))
    geometry = manifest.get('preparation_geometry') or {}
    # Manual preparation already permits explicit 1/2/3/4 choices. Bind that
    # choice in the versioned plan; automatic reuse retains its legacy policy.
    manual_scale=(geometry.get('plan') or {}).get('legacy_scale') if not ctx.get('automatic') else None
    expected = for_context(source, ctx,legacy_scale=manual_scale)
    if not expected['references']:
        # Preserve the old cache rule when there is no verified selected target.
        return geometry.get('scale', 1) == expected['scale']
    record = geometry.get('plan') or {}
    canonical = {**record, 'scale': _scale(record.get('scale'))}
    return canonical == expected and manifest.get('dimensions') == expected['output_dimensions']
