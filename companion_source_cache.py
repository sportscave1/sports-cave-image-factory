"""Small private resident-source cache, outside Dropbox/OneDrive staging paths.

Every use rehashes bytes and binds exact provider ID, revision and content hash.
An upload owner may register its verified local copy through remember(); browser
file paths are never guessed or scanned. Originals are never moved or modified.
"""
import json
import os
from pathlib import Path
import shutil
import threading
import time
import auto_editions as ae
from auto_editions_local_cache import verified

BUDGET=512*1024*1024
_lock=threading.Lock()


def root():
    configured=os.getenv('SPORTS_CAVE_COMPANION_SOURCE_CACHE')
    return Path(configured) if configured else Path(os.getenv('LOCALAPPDATA',str(Path.home()/'AppData/Local')))/'SportsCave/Companion/SourceCache'


def identity(source):return {k:source[k] for k in ('file_id','revision','content_hash')}


def reuse(destination,source,size,*,cache=None):
    cache=Path(cache) if cache else root();key=ae.fingerprint(identity(source));folder=cache/key
    try:
        receipt=json.loads((folder/'receipt.json').read_text(encoding='utf-8'))
        if receipt['identity']!=identity(source) or receipt['size']!=size:return None
        if folder.is_symlink() or folder.resolve().parent!=cache.resolve() or (folder/'receipt.json').is_symlink():return None
        hashes=verified(folder/'input.psd',source,size)
        if not hashes or hashes['sha256']!=receipt['sha256']:return None
        destination=Path(destination)
        with destination.open('xb') as output,(folder/'input.psd').open('rb') as stream:shutil.copyfileobj(stream,output,1024*1024)
        if verified(destination,source,size)!=hashes:raise ValueError('Cached source changed while staging.')
        return hashes
    except (FileNotFoundError,KeyError,json.JSONDecodeError):return None


def remember(path,source,size,*,cache=None):
    if size>BUDGET:return False
    hashes=verified(path,source,size)
    if not hashes:raise ValueError('Local upload/source copy does not match the immutable provider receipt.')
    cache=Path(cache) if cache else root()
    with _lock:
        cache.mkdir(parents=True,exist_ok=True)
        if cache.is_symlink():raise ValueError('Unexpected source-cache link.')
        key=ae.fingerprint(identity(source));folder=cache/key
        if folder.exists():
            receipt=folder/'receipt.json'
            if not folder.is_symlink() and receipt.exists() and verified(folder/'input.psd',source,size)==hashes:return True
            return False # Preserve corrupt/conflicting evidence for operator review.
        retained=sorted((p for p in cache.iterdir() if p.is_dir() and not p.is_symlink()),key=lambda p:p.stat().st_mtime)
        used=sum(p.stat().st_size for p in cache.glob('*/input.psd') if not p.is_symlink())
        for old in retained:
            if used+size<=BUDGET:break
            if old.resolve().parent!=cache.resolve() or len(old.name)!=64 or any(c not in '0123456789abcdef' for c in old.name):continue
            files=list(old.iterdir())
            if any(p.is_symlink() or p.name not in ('input.psd','receipt.json') or not p.is_file() for p in files):continue
            used-=(old/'input.psd').stat().st_size if (old/'input.psd').exists() else 0
            # Only known cache-owned regular files; no recursive move/delete.
            for p in files:p.unlink()
            old.rmdir()
        if used+size>BUDGET:return False
        folder.mkdir()
        with Path(path).open('rb') as stream,(folder/'input.psd').open('xb') as output:shutil.copyfileobj(stream,output,1024*1024)
        if verified(folder/'input.psd',source,size)!=hashes:raise ValueError('Source changed while caching.')
        from companion_atomic import atomic_json
        atomic_json(folder/'receipt.json',dict(identity=identity(source),size=size,sha256=hashes['sha256'],created=time.time()))
        return True
