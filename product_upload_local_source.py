"""Read-only reuse of an already resident synced PSD; never hydrate originals."""
import json
import os
import shutil
from pathlib import Path
from auto_editions_local_cache import verified


def synced_roots():
    configured = os.getenv('SPORTS_CAVE_DROPBOX_SYNC_ROOT')
    if configured: return [Path(configured)]
    roots = []
    for base in ('APPDATA','LOCALAPPDATA'):
        info = Path(os.getenv(base, '.'))/'Dropbox/info.json'
        if not info.is_file() or info.is_symlink() or info.stat().st_size > 65536: continue
        for account in json.loads(info.read_text(encoding='utf-8')).values():
            if account.get('path'): roots.append(Path(account['path']))
    return roots


def reuse_synced(metadata, destination, roots=None):
    destination = Path(destination)
    if destination.exists(): return verified(destination, {'content_hash':metadata['content_hash']}, metadata['size'])
    path = metadata['path_display']
    if not path.startswith('/') or '..' in Path(path).parts: return None
    for root in synced_roots() if roots is None else roots:
        root = Path(root).resolve(); candidate = root/path.lstrip('/')
        try:
            resolved = candidate.resolve()
            if not resolved.is_relative_to(root) or candidate.is_symlink(): continue
            if any(p.is_symlink() for p in candidate.parents if p != root and p.is_relative_to(root)): continue
            info = candidate.stat()
            # Offline/recall flags mean reading would trigger a full cloud fetch.
            if getattr(info,'st_file_attributes',0) & (0x1000|0x40000|0x400000): continue
            identity = {'content_hash':metadata['content_hash']}
            hashes = verified(candidate, identity, metadata['size'])
            if not hashes: continue
            with candidate.open('rb') as source, destination.open('xb') as output:
                shutil.copyfileobj(source, output, 4*1024*1024)
            if verified(destination, identity, metadata['size']) != hashes: raise ValueError('Synced source changed during staging.')
            return hashes
        except (FileNotFoundError, PermissionError): continue
    return None
