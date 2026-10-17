"""Auto Editions preparation contract and offline cloud compositor.

No PSD mapping, allocation, fulfilment or supplier writes. Photoshop prepares
one lossless master and small opaque number patches once. Order-time rendering
needs only those assets, Pillow and a verified immutable preparation manifest.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import threading
import time
from functools import wraps
from pathlib import Path

REQUIRED_LAYERS = ('SC_EDITION_NUMBER', 'SC_EDITION_PLAQUE', 'SC_EDITION_MATTING')
MAX_PIXELS = 110_000_000
WORKER_MAX_PIXELS = 95_000_000
_RENDER_LOCK = threading.RLock()


def serial_render(function):
    @wraps(function)
    def call(*args, **kwargs):
        with _RENDER_LOCK:
            return function(*args, **kwargs)
    return call


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def file_hash(path, *, dropbox=False):
    result = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(4 * 1024 * 1024), b''):
            result.update(hashlib.sha256(block).digest() if dropbox else block)
    return result.hexdigest()


def reference_template():
    return json.loads((Path(__file__).parent / 'data/auto_editions_template.json').read_text())


def dimensions(value):
    if (not isinstance(value, list) or len(value) != 2
            or any(type(n) is not int or n <= 0 for n in value)
            or value[0] * value[1] > MAX_PIXELS):
        raise ValueError('Unsupported canvas dimensions.')
    return value


def bounds(value, canvas, *, contained=True):
    if (not isinstance(value, list) or len(value) != 4
            or any(type(n) not in (int, float) or not math.isfinite(n) for n in value)
            or value[0] >= value[2] or value[1] >= value[3]):
        raise ValueError('Invalid layer bounds.')
    if contained and not (0 <= value[0] < value[2] <= canvas[0]
                          and 0 <= value[1] < value[3] <= canvas[1]):
        raise ValueError('Edition artwork falls outside the canvas.')
    return value


def source_identity(product_gid, metadata):
    if not re.fullmatch(r'gid://shopify/Product/[1-9][0-9]*', str(product_gid)):
        raise ValueError('An exact product identity is required.')
    if (not re.fullmatch(r'id:[A-Za-z0-9_-]+', str(metadata.get('id', '')))
            or not re.fullmatch(r'[a-f0-9]+', str(metadata.get('rev', '')))
            or not re.fullmatch(r'[a-f0-9]{64}', str(metadata.get('content_hash', '')))):
        raise ValueError('Dropbox permanent ID, revision and content hash are required.')
    return dict(product_gid=product_gid, file_id=metadata['id'],
                revision=metadata['rev'], content_hash=metadata['content_hash'])


def inspect_layout(inspection):
    """Never inherit coordinates from the reference template or guess a text layer.

    Smart-object-local number coordinates are not document coordinates. Such
    designs stay on Photoshop until a verified transform is available.
    """
    doc = inspection.get('document') or {}
    canvas = dimensions([doc.get('width_px'), doc.get('height_px')])
    selected = {}
    for name in REQUIRED_LAYERS:
        matches = [row for row in inspection.get('layers', [])
                   if (row.get('path') or [{}])[-1].get('name') == name]
        if len(matches) != 1:
            raise ValueError(f'{name}: exactly one approved layer is required; review in Photoshop.')
        row = matches[0]
        if row.get('smart_object_chain') or row.get('visible') is not True:
            raise ValueError(f'{name}: hidden or nested coordinates require Photoshop review.')
        bounds(row.get('bounds_px'), canvas, contained=name != 'SC_EDITION_MATTING')
        selected[name] = row
    number = selected['SC_EDITION_NUMBER']
    if number.get('kind') != 'text' or number.get('editable') is not True:
        raise ValueError('The edition number must be editable text.')
    if not number.get('fonts') or any(f.get('installed') is not True for f in number['fonts']):
        raise ValueError('The original fonts are unavailable; substitution is forbidden.')
    match = re.fullmatch(r'(\s*(?:(?:LIMITED\s+)?EDITION\s+)?#?\s*)(\d{1,6})(\s*/\s*|\s+of\s+)(\d{1,6})(\s*)',
                         str(number.get('text', '')), re.I)
    if not match or not (1 <= int(match[2]) <= int(match[4]) <= 1000):
        raise ValueError('Edition number/total is ambiguous or unsupported.')
    if len(str(int(match[4]))) > len(match[2]):
        raise ValueError('Changing digit width requires manual typography review.')
    nb, pb = number['bounds_px'], selected['SC_EDITION_PLAQUE']['bounds_px']
    if nb[0] < pb[0] or nb[1] < pb[1] or nb[2] > pb[2] or nb[3] > pb[3]:
        raise ValueError('Number does not lie inside this design\'s plaque.')
    return {'dimensions': canvas, 'number': number, 'plaque': selected['SC_EDITION_PLAQUE'],
            'matting': selected['SC_EDITION_MATTING'], 'edition_total': int(match[4]),
            'number_width': len(match[2]), 'profile': doc.get('profile'),
            'resolution': doc.get('resolution'), 'inspection_warnings': inspection.get('warnings', [])}


def asset_path(root, record):
    """Prepared asset names are flat and content-pinned; never URLs or user paths."""
    name = record.get('name', '')
    if not re.fullmatch(r'[A-Za-z0-9_-]+\.png', name):
        raise ValueError('Invalid preparation asset name.')
    path = (Path(root) / name).resolve()
    if not path.is_relative_to(Path(root).resolve()) or file_hash(path) != record.get('sha256'):
        raise ValueError('Prepared asset changed or escaped its package.')
    return path


def validate_manifest(manifest):
    if manifest.get('schema_version') != 1 or manifest.get('strategy') != 'photoshop_number_patches':
        raise ValueError('Unsupported preparation format.')
    source = manifest.get('source') or {}
    source_identity(source.get('product_gid'), dict(id=source.get('file_id'),
                    rev=source.get('revision'), content_hash=source.get('content_hash')))
    canvas = dimensions(manifest.get('dimensions'))
    area = bounds(manifest.get('number_region'), canvas)
    if any(type(n) is not int for n in area):
        raise ValueError('Number patch coordinates must be integer pixels.')
    # A whole-image patch would defeat bounded, reusable cloud preparation.
    if (area[2] - area[0]) * (area[3] - area[1]) > canvas[0] * canvas[1] / 10:
        raise ValueError('Number region exceeds 10% of the artwork.')
    total = manifest.get('edition_total')
    if type(total) is not int or not 1 <= total <= 1000:
        raise ValueError('Invalid edition total.')
    if set(manifest.get('patches', {})) != {str(n) for n in range(1, total + 1)}:
        raise ValueError('Every edition needs its small approved Photoshop patch.')
    assets = [manifest.get('master', {})] + list(manifest['patches'].values())
    names = set()
    for asset in assets:
        if (not isinstance(asset, dict)
                or not re.fullmatch(r'[A-Za-z0-9_-]+\.png', str(asset.get('name', '')))
                or not re.fullmatch(r'[a-f0-9]{64}', str(asset.get('sha256', '')))
                or asset['name'] in names):
            raise ValueError('Prepared assets need distinct names and pinned checksums.')
        names.add(asset['name'])
    dimensions(manifest.get('source_dimensions'))
    if manifest.get('source_dimensions') != canvas and manifest.get('upscaled') is not True:
        raise ValueError('Resampling must be disclosed explicitly.')
    if manifest.get('upscaled') is True:
        geometry = manifest.get('preparation_geometry') or {}
        scale = geometry.get('scale')
        if (type(scale) is not int or scale not in (2, 3, 4)
                or geometry.get('method') != 'photoshop_layered_bicubic_smoother'
                or geometry.get('supplier_verified') is not False
                or geometry.get('quality_approval_required') is not True
                or canvas != [n*scale for n in manifest['source_dimensions']]):
            raise ValueError('Enlargement needs explicit proportional TEST geometry and quality review.')
    return manifest


def compose(manifest, root, number, *, timings=None):
    """Exact RGB composition before JPEG compression; no font substitution/upscale."""
    from PIL import Image
    validate_manifest(manifest)
    if type(number) is not int or not 1 <= number <= manifest['edition_total']:
        raise ValueError('Edition is outside the prepared range.')
    canvas = manifest['dimensions']
    x0, y0, x1, y1 = manifest['number_region']
    started=time.monotonic()
    with Image.open(asset_path(root, manifest['master'])) as source:
        if source.format != 'PNG' or source.mode != 'RGB' or list(source.size) != canvas:
            raise ValueError('Master must be a lossless RGB PNG at the prepared size.')
        result = source.copy()
        profile = source.info.get('icc_profile', b'')
    if timings is not None:timings['master_decode_copy_ms']=round((time.monotonic()-started)*1000,3)
    started=time.monotonic()
    try:
        with Image.open(asset_path(root, manifest['patches'][str(number)])) as patch:
            if patch.format != 'PNG' or patch.mode != 'RGB' or patch.size != (x1-x0, y1-y0):
                raise ValueError('Patch mode or geometry changed.')
            if patch.info.get('icc_profile', b'') != profile:
                raise ValueError('Master and number colour profiles differ.')
            result.paste(patch, (x0, y0))
    except Exception:
        result.close()
        raise
    result.info['icc_profile'] = profile
    if timings is not None:timings['number_patch_ms']=round((time.monotonic()-started)*1000,3)
    return result


@serial_render
def render_jpg(manifest, root, number, destination):
    """Worker primitive. Caller must enforce auth/allocation/approval on each job."""
    destination = Path(destination)
    timings={}
    with compose(manifest, root, number,timings=timings) as image:
        expected_profile=image.info.get('icc_profile',b'')
        started=time.monotonic()
        image.save(destination, format='JPEG', quality=100, subsampling=0,
                   icc_profile=image.info.get('icc_profile', b''), dpi=(300, 300))
        timings['jpg_encode_ms']=round((time.monotonic()-started)*1000,3)
    started=time.monotonic()
    from PIL import Image, ImageCms
    with Image.open(destination) as verified:
        if verified.format != 'JPEG' or list(verified.size) != manifest['dimensions']:
            raise ValueError('Encoded JPG geometry changed.')
        verified.load()
        profile = verified.info.get('icc_profile', b'')
        if profile!=expected_profile:raise ValueError('ICC export mismatch: JPG did not retain the verified source profile.')
        import io
        profile_name = ImageCms.getProfileName(ImageCms.ImageCmsProfile(io.BytesIO(profile))).strip() if profile else 'Unspecified'
    digest=file_hash(destination)
    timings['jpg_integrity_ms']=round((time.monotonic()-started)*1000,3)
    return {'sha256': digest, 'dimensions': manifest['dimensions'],'render_timings':timings,
            'ppi_metadata': [300, 300], 'colour_profile': profile_name,
            'icc_sha256': hashlib.sha256(profile).hexdigest() if profile else None,
            'edition_number': number, 'edition_total': manifest['edition_total'],
            'preparation_hash': fingerprint(manifest), 'print_ready': False}


@serial_render
def compare_reference(manifest, root, number, photoshop_png):
    """Pixel-exact lossless proof, including the area outside the number.

    JPEGs from different encoders need not be byte/pixel identical. Validate the
    lossless composition, then independently inspect encoded output quality.
    """
    from PIL import Image, ImageChops
    with compose(manifest, root, number) as actual, Image.open(photoshop_png) as expected:
        if expected.mode != 'RGB' or expected.size != actual.size:
            raise ValueError('Photoshop reference has different geometry or colour mode.')
        if expected.info.get('icc_profile', b'') != actual.info.get('icc_profile', b''):
            raise ValueError('Photoshop reference has a different colour profile.')
        difference = ImageChops.difference(actual, expected).getbbox()
        if difference is not None:
            raise ValueError('Cloud composition differs from the Photoshop reference.')
    return {'number': number, 'reference_sha256': file_hash(photoshop_png),
            'preparation_hash': fingerprint(manifest), 'pixel_exact': True}


def status(manifest=None, approval=None):
    """Print certification is deliberately unavailable in this first preparation contract."""
    if not manifest:
        return 'NOT CONFIGURED'
    try:
        validate_manifest(manifest)
    except (ValueError, TypeError, KeyError):
        return 'NOT CONFIGURED'
    if approval and approval.get('method')=='auto-editions-technical-v1':
        from auto_editions_technical import current
        return 'TEST READY' if current(approval,manifest) else 'NOT CONFIGURED'
    if approval and approval.get('method')=='auto-editions-visual-v1':
        from auto_editions_visual import current
        return 'TEST READY' if current(approval,manifest) else 'NOT CONFIGURED'
    if approval and approval.get('method')=='product-upload-technical-v1':
        from product_upload_readiness import current
        return 'TEST READY' if current(approval,manifest) else 'NOT CONFIGURED'
    if (not approval or approval.get('preparation_hash') != fingerprint(manifest)
            or not approval.get('actor_id') or approval.get('visual_approved') is not True
            or approval.get('pixel_exact') is not True):
        return 'NOT CONFIGURED'
    return 'TEST READY'


@serial_render
def compare_original_outside_number(manifest, root, number, original_png):
    """Prove preparation did not alter the source composition beyond its number."""
    from PIL import Image, ImageChops
    with compose(manifest, root, number) as actual, Image.open(original_png) as original:
        if (original.mode != actual.mode or original.size != actual.size
                or original.info.get('icc_profile', b'') != actual.info.get('icc_profile', b'')):
            raise ValueError('Original artwork geometry or colour profile differs.')
        with ImageChops.difference(actual, original) as difference:
            difference.paste((0, 0, 0), tuple(manifest['number_region']))
            if difference.getbbox() is not None:
                raise ValueError('Preparation changed artwork outside the approved number region.')
    return {'original_sha256': file_hash(original_png), 'outside_number_exact': True,
            'preparation_hash': fingerprint(manifest)}
