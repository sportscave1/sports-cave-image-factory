"""Small, immutable proof cache. Only called after the JPG access checks."""
from pathlib import Path
import tempfile,os,re


def cached(sha):
    if not re.fullmatch('[a-f0-9]{64}',sha or ''):raise ValueError('Invalid preview identity.')
    folder=Path(tempfile.gettempdir())/'sports-cave-order-proofs'
    folder.mkdir(exist_ok=True)
    return folder/(sha+'.jpg')


def create(source,sha):
    target=cached(sha)
    if target.is_file():return target
    from PIL import Image
    with Image.open(source) as im:
        im.draft('RGB',(1000,1000))
        im.thumbnail((1000,1000))
        with tempfile.NamedTemporaryFile(dir=target.parent,suffix='.jpg',delete=False) as tmp:part=Path(tmp.name)
        try:
            im.convert('RGB').save(part,format='JPEG',quality=78,optimize=True)
            os.replace(part,target)
        finally:part.unlink(missing_ok=True)
    # This cache contains disposable generated proofs, never source artwork.
    proofs=sorted(target.parent.glob('*.jpg'),key=lambda p:p.stat().st_mtime,reverse=True)
    for old in proofs[256:]:
        if old!=target and re.fullmatch('[a-f0-9]{64}.jpg',old.name):old.unlink(missing_ok=True)
    return target
