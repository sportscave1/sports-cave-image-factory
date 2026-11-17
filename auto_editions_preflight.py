"""Native Photoshop preflight; no inferred background, colour or role choices."""
from hashlib import sha256
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


def _resize_edge_signature(alpha, changed_pixels):
    """Identify Photoshop's thin, nearly continuous resize edge, not artwork holes."""
    width, height = alpha.size
    band = 2
    if min(width, height) <= band * 2 or alpha.getextrema()[0] < 128:
        return None
    interior = (band, band, width - band, height - band)
    if alpha.crop(interior).getextrema() != (255, 255):
        return None
    # Require the nearly complete two-pixel perimeter observed in the native
    # exports. Isolated edge defects and sparse artwork masks still fail.
    edge_pixels = width * height - (width - band * 2) * (height - band * 2)
    if changed_pixels * 100 < edge_pixels * 95:
        return None
    digest = sha256()
    for box in ((0, 0, width, band), (0, height - band, width, height),
                (0, band, band, height - band), (width - band, band, width, height - band)):
        digest.update(alpha.crop(box).tobytes())
    return digest.hexdigest()


def normalize_resize_corners(root, names, dimensions, *, matched_edges=False):
    """Remove verified resize alpha without modifying any RGB sample or profile."""
    native_width, native_height = opaque(root / 'preflight-original.png')
    width, height = dimensions
    corners = [(x, y, x + 2, y + 2) for x in (0, width - 2) for y in (0, height - 2)]
    changed, signatures = {}, {}
    saw_edge = False
    for name in names:
        with Image.open(root / name) as image:
            if image.format != 'PNG' or image.size != (width, height) or image.mode not in ('RGB', 'RGBA'):
                raise ValueError('Resized Photoshop export has different format or geometry.')
            if image.mode == 'RGB':
                continue
            with image.getchannel('A') as alpha:
                histogram = alpha.histogram()
                corner_count = sum(alpha.crop(box).histogram()[254] for box in corners)
                count = sum(histogram[:255])
                corner_only = not any(histogram[:254]) and histogram[254] == corner_count
                if not corner_only:
                    signature = (_resize_edge_signature(alpha, count)
                                 if matched_edges and width > native_width and height > native_height else None)
                    if not signature:
                        raise NonOpaqueArtwork(f'{name}: resized artwork contains unverified transparency. '
                                              'The source and Photoshop export require review.')
                    signatures[name] = signature
                    saw_edge = True
                changed[name] = count

    if saw_edge and (not {'original.png', 'master.png'} <= signatures.keys()
                     or not any(name.startswith('reference-') for name in signatures)
                     or len(signatures) != len(names) or len(set(signatures.values())) != 1):
        raise NonOpaqueArtwork('Resized artwork edge transparency differs across the Photoshop proofs; '
                               'no alpha samples were changed.')

    # Validate the complete set before touching any staged export. The original
    # PSD and the numbered patches are never rewritten by this correction.
    for name in changed:
        path = root / name
        temporary = path.with_suffix(f'.{uuid4().hex}.rgb-tmp')
        try:
            with Image.open(path) as image, temporary.open('xb') as stream:
                options = {key: image.info[key] for key in ('icc_profile', 'dpi') if key in image.info}
                with image.convert('RGB') as rgb:
                    rgb.save(stream, format='PNG', **options)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    return changed
