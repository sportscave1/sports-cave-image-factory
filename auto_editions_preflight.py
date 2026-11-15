"""Native Photoshop preflight; no inferred background, colour or role choices."""
from pathlib import Path
from uuid import uuid4
from PIL import Image, ImageChops
from auto_editions_onboarding import detect


def preparation_code_hash():
    """Content identity of the native fix; independent of unrelated releases."""
    import hashlib
    root=Path(__file__).parent
    return hashlib.sha256(''.join((root/name).read_text(encoding='utf-8-sig').replace('\r\n','\n')
        for name in ('auto_editions_preflight.py','scripts/photoshop/prepare_auto_editions.jsx',
                     'scripts/photoshop/inspect_psd_editions.jsx','scripts/photoshop_dispatch.py')).encode()).hexdigest()


class NonOpaqueArtwork(ValueError):
    pass


def opaque(path):
    with Image.open(path) as image:
        if image.format != 'PNG' or image.mode not in ('RGB', 'RGBA'):
            raise ValueError('Preflight requires a native RGB Photoshop PNG.')
        if image.mode == 'RGBA':
            low, high = image.getchannel('A').getextrema()
            if low != 255:
                raise NonOpaqueArtwork(f'{Path(path).name}: non-opaque alpha ({low}-{high}). '
                    'The visible artwork must cover the complete canvas; preserve the approved background in the PSD.')
        return image.size


def validate(root, report, source, total, number_layer, plaque_layer, scale):
    roles = detect(report['inspection'], total, source=source)
    if roles['number_layer'] != number_layer or roles['plaque_layer'] != plaque_layer:
        raise ValueError('Preflight roles differ from the inspected preparation roles.')
    from auto_editions_role_evidence import resolution
    reviewed = resolution(source) or {}
    # Existing exact owner-reviewed presentations still use their separate proofs.
    if reviewed.get('opaque_backing'):
        return None
    size = opaque(root/'preflight-original.png')
    if list(size) != roles['source_dimensions']:
        raise ValueError('Preflight source geometry differs from the inspected PSD.')
    candidate = report.get('resize_background')
    if scale == 1 or not candidate:
        return None
    try:
        candidate_size = opaque(root/'preflight-artwork.png')
    except NonOpaqueArtwork:
        # The full composite already passed. Leave the layered document intact:
        # promoting a partial layer could fill transparent pixels or change art.
        # The ordinary preparation pixel proofs still validate the resized output.
        return None
    if candidate_size != size:
        raise ValueError('Resize background must cover the native canvas exactly.')
    return candidate


def verify_resize(root):
    """Background promotion must be pixel exact BEFORE any enlargement."""
    with Image.open(root/'preflight-original.png') as before, Image.open(root/'resize-original.png') as after:
        if before.size != after.size or any(b.getbbox() for b in ImageChops.difference(
                before.convert('RGBA'), after.convert('RGBA')).split()):
            raise ValueError('Resize background changed native artwork pixels; preparation rejected.')
    opaque(root/'original.png')
    opaque(root/'master.png')
    return dict(method='verified_opaque_native_background_v1', native_pixels_exact=True,
                original_opaque=True, master_opaque=True)


def normalize_resize_corners(root, names, dimensions):
    """Remove one-level alpha rounding at the corners of a verified opaque resize."""
    opaque(root / 'preflight-original.png')
    width, height = dimensions
    corners = [(x, y, x + 2, y + 2) for x in (0, width - 2) for y in (0, height - 2)]
    changed = {}
    for name in names:
        path = root / name
        with Image.open(path) as image:
            if image.format != 'PNG' or image.size != (width, height):
                raise ValueError('Resized Photoshop export has different format or geometry.')
            if image.mode != 'RGBA':
                continue
            with image.getchannel('A') as alpha:
                histogram = alpha.histogram()
                corner_count = sum(alpha.crop(box).histogram()[254] for box in corners)
            if any(histogram[:254]) or histogram[254] != corner_count:
                raise NonOpaqueArtwork(f'{name}: resized artwork contains transparency outside the one-level corner rounding allowance.')
            options = {key: image.info[key] for key in ('icc_profile', 'dpi') if key in image.info}
            rgb = image.convert('RGB')
        temporary = path.with_suffix(f'.{uuid4().hex}.rgb-tmp')
        try:
            with rgb, temporary.open('xb') as stream:
                rgb.save(stream, format='PNG', **options)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        changed[name] = corner_count
    return changed
