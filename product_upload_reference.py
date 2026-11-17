"""Attach the exact saved black-frame WebP through the authenticated OS origin."""
from pathlib import Path
import hashlib

MAX_REFERENCE_BYTES = 16 * 1024 * 1024


def attachment(result, row, receipt):
    from auto_editions import file_hash
    from PIL import Image
    from product_upload_gallery import register

    spec = next(item for item in result['product_image_manifest'] if item['slot_id'] == 'black-frame')
    filename = spec['output_filename']
    saved = next(item['metadata'] for item in receipt['successes']
                 if item['relative_path'] == 'WEBP/' + filename)
    asset = next(item for item in result['assets'] if item['key'] == 'black')
    path = Path(asset['webp_path'])
    size = path.stat().st_size
    if (not 0 < size <= MAX_REFERENCE_BYTES or size != saved['size']
            or file_hash(path, dropbox=True) != saved['content_hash']):
        raise ValueError('The black-frame attachment differs from its verified Dropbox original. Refresh the saved package.')
    with Image.open(path) as image:
        if image.format != 'WEBP':
            raise ValueError('The original black-frame attachment must be a WebP.')
        image.verify()
    address = register(result, dict(key='upload-reference-black'), row['data']['source'], path)
    return dict(url=address, name=filename, type='image/webp', size=size,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                content_hash=saved['content_hash'], file_id=saved['id'], revision=saved['rev'])
