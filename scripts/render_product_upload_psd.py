"""Native colour-managed web render; never edits/saves the original PSD."""
import json
import shutil
from pathlib import Path
from PIL import Image, ImageCms
from auto_editions_performance import file_hashes
from auto_editions import file_hash
from auto_editions_colour_source import inspect_psd, stage_profile, ColourReview


def render(source, output, identity, *, dispatch=None):
    source, output = Path(source), Path(output)
    hashes = file_hashes(source)
    if hashes['dropbox'] != identity['content_hash']: raise ValueError('PSD source checksum changed.')
    if output.exists(): raise ValueError('Use a new render directory; retained work is never overwritten.')
    colour = inspect_psd(source)
    if colour['mode'] != 3 or colour['depth'] != 8:
        raise ColourReview('Mockups needs an RGB8 working PSD. Preserve the original and review its supported export.')
    icc, policy = colour['icc'], None
    if not icc:
        from product_upload_colour import resolve_web
        icc, policy = resolve_web(identity)
    output.mkdir(parents=True)
    staged = output/'working.psd'
    assignment = stage_profile(source, staged, icc) if policy else None
    if not policy: shutil.copyfile(source, staged)
    staged_hash=assignment['staged_sha256'] if assignment else hashes['sha256']
    from auto_editions_colour_source import profile_info
    original_profile = profile_info(icc)
    request = dict(input=str(staged.resolve()), output=str((output/'render.png').resolve()),
                   status=str((output/'native-status.json').resolve()),
                   profiles=[original_profile['name'], original_profile['description']])
    script = (Path(__file__).parent/'photoshop/inspect_psd_editions.jsx').read_text(encoding='utf-8-sig').split('if(typeof SC_PSD_INSPECT_REQUEST')[0] + '\n' + (Path(__file__).parent/'photoshop/render_product_upload.jsx').read_text(encoding='utf-8')
    if dispatch is None:
        from scripts.photoshop_dispatch import run
        dispatch = run
    (output/'dispatch-intent.json').write_text(json.dumps(dict(source=identity)))
    try:
        result = dispatch('var SC_PRODUCT_RENDER = '+json.dumps(request)+';\n'+script)
    finally:
        # The provider content hash was already checked before dispatch. These
        # preservation fences require SHA-256 only; do not calculate a second,
        # unused provider digest over both full PSDs after every native render.
        if file_hash(source) != hashes['sha256'] or file_hash(staged) != staged_hash:
            raise ValueError('Original PSD preservation check failed.')
    status = json.loads((output/'native-status.json').read_text(encoding='utf-8-sig'))
    if result != 'SC_PRODUCT_RENDERED' or not status.get('owned_document_closed'):
        raise ValueError('Native render/cleanup could not be verified; inspect retained evidence before retrying.')
    path = output/'render.png'
    # Photoshop's verified conversion is authoritative. Add the matching web
    # profile if its PNG writer omitted metadata; do not reinterpret pixels.
    srgb = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    with Image.open(path) as image:
        if image.format != 'PNG' or list(image.size) != status['dimensions'] or max(image.size)>2000:
            raise ValueError('Native render dimensions differ from the saved output.')
        if image.info.get('icc_profile'):
            if 'srgb' not in profile_info(image.info['icc_profile'])['description'].lower():
                raise ColourReview('Native web export has a conflicting profile.')
        else:
            image.save(output/'tagged.png', icc_profile=srgb)
            (output/'tagged.png').replace(path)
    receipt = dict(renderer_version='native-web-v1',renderer_sha256=__import__('hashlib').sha256(script.encode()).hexdigest(),render_sha256=file_hash(path),source=identity,source_sha256=hashes['sha256'],source_unchanged=True,
                   native_render=True,owned_document_closed=True,dimensions=status['dimensions'],
                   colour=dict(source_profile=original_profile,policy=policy,assignment=assignment,
                               web_profile='sRGB IEC61966-2.1',operation='native colour-managed web conversion',
                               original_profile_preserved=True))
    (output/'receipt.json').write_text(json.dumps(receipt,indent=2))
    return path, receipt
