"""On-demand original pixels, scoped to an authenticated workflow and asset."""
import base64
import json
import secrets
from pathlib import Path
from threading import RLock
from time import monotonic
from urllib.parse import urlencode

_lock = RLock()
_assets = {}


def revoke(key, actor):
    with _lock:
        for token, item in list(_assets.items()):
            if item['key'] == str(key) and item['actor'] == str(actor):
                del _assets[token]


def register(result, asset, source, path):
    import mockup_storage
    run = mockup_storage.safe_temp_path(result['run_dir'])
    path = Path(path).resolve()
    if not run or not path.is_file() or not path.is_relative_to(run.resolve()):
        raise ValueError('The original image is no longer available. Generate mockups again.')
    identity = (str(result['_product_upload_actor_id']), str(result['_product_upload_intake']), asset['key'])
    signature = (str(path), path.stat().st_size, path.stat().st_mtime_ns)
    with _lock:
        for token, item in list(_assets.items()):
            if monotonic() - item['created'] > 86400:
                del _assets[token]
            elif item['identity'] == identity:
                if item['signature'] == signature and item['source'] == source:
                    return '/api/product-uploads/asset?' + urlencode(dict(token=token))
                del _assets[token]
        while len(_assets) >= 200:
            del _assets[next(iter(_assets))]
        token = secrets.token_urlsafe(32)
        _assets[token] = dict(identity=identity, actor=identity[0], key=identity[1], source=dict(source),
                              signature=signature, path=path, created=monotonic())
        return '/api/product-uploads/asset?' + urlencode(dict(token=token))


def resolve(token, actor, read):
    with _lock:
        item = dict(_assets.get(token) or {})
    if not item or item['actor'] != str(actor) or monotonic() - item['created'] > 86400:
        raise ValueError('This image link expired. Reopen the current mockup.')
    row = read(item['key'], actor)
    if not row or row['data'].get('source') != item['source']:
        raise ValueError('This image belongs to a previous PSD selection.')
    path = item['path']
    if not path.is_file() or (str(path), path.stat().st_size, path.stat().st_mtime_ns) != item['signature']:
        raise ValueError('This original has been replaced. Reopen the current mockup.')
    return path


def retain_upload_original(result, filename, uploaded, signature):
    """Keep uploaded pixels separately from the shared, size-limited export assets."""
    import os
    import shutil
    import tempfile
    originals=dict(result.get('product_upload_originals') or {})
    old=originals.get(filename) or {}
    if signature and old.get('signature')==signature and Path(old['path']).is_file():return result
    folder=Path(result['run_dir'])/'uploaded-originals'
    folder.mkdir(exist_ok=True)
    suffix=Path(uploaded.name).suffix.lower()
    if suffix not in ('.png','.jpg','.jpeg','.webp'):raise ValueError('Unsupported original image format.')
    destination=folder/(Path(filename).stem+suffix)
    temporary=None
    try:
        uploaded.seek(0)
        with tempfile.NamedTemporaryFile(dir=folder,delete=False) as output:
            temporary=Path(output.name)
            shutil.copyfileobj(uploaded,output,length=1024*1024)
        os.replace(temporary,destination)
    finally:
        uploaded.seek(0)
        if temporary:temporary.unlink(missing_ok=True)
    originals[filename]=dict(path=str(destination),signature=signature)
    result=dict(result,product_upload_originals=originals)
    return result


def render(*, preview=None, original='', label='', prompt=None, copy_row=False, copy_action=True):
    import streamlit.components.v1 as components
    data = dict(original=original, label=label, prompt=prompt, copyRow=copy_row, copyAction=copy_action)
    if preview and Path(preview).is_file():
        data['preview'] = 'data:image/webp;base64,' + base64.b64encode(Path(preview).read_bytes()).decode('ascii')
    template = (Path(__file__).parent / 'components/product_upload_gallery/index.html').read_text(encoding='utf-8')
    components.html(template.replace('/*CONFIG*/{}', json.dumps(data).replace('<', '\\u003c')),
                    height=86 if copy_row else 315, scrolling=False)
