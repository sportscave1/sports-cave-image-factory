"""Reuse local staged inputs only after exact pinned byte verification.

No original PSD mutation, global approval, mtime-only trust or provider access.
Inspector receipts are invalidated by any source, report or inspector change.
"""
import hashlib,json,shutil
from pathlib import Path
from auto_editions_performance import file_hashes

def verified(path,identity,size):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size!=size:return None
    hashes=file_hashes(path)
    return hashes if hashes['dropbox']==identity['content_hash'] else None

def reuse_source(root,destination,identity,size):
    root=Path(root).resolve();destination=Path(destination)
    if destination.exists():return verified(destination,identity,size)
    if destination.parent.resolve().parent!=root or destination.parent.is_symlink():raise ValueError('Source cache outside owned root.')
    # Bounded candidate metadata reads; three bad byte candidates cannot monopolise work.
    files=sorted(root.glob('*/job-state.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:512]
    attempts=0
    for record in files:
        try:
            if record.is_symlink() or record.parent.is_symlink() or record.stat().st_size>4*1024*1024:continue
            row=json.loads(record.read_text())
            if row.get('context',{}).get('source')!=identity:continue
            source=record.parent/'input.psd'
            if source==destination or not source.is_file() or source.is_symlink() or source.stat().st_size!=size:continue
            attempts+=1
            hashes=verified(source,identity,size)
            if hashes:
                with destination.open('xb') as dst,source.open('rb') as src:shutil.copyfileobj(src,dst,4*1024*1024)
                copied=verified(destination,identity,size)
                if copied!=hashes:raise ValueError('Source cache changed while staging.')
                return copied
            if attempts>=3:break
        except (OSError,ValueError,KeyError):
            if destination.exists():raise # Never overwrite a partially staged source.
    return None

def cached_inspection(folder,source,source_sha256,inspector_sha256):
    folder=Path(folder);report=folder/'inspection.json';receipt=folder/'inspection-cache.json'
    try:
        if report.is_symlink() or receipt.is_symlink() or receipt.stat().st_size>4096 or report.stat().st_size>4*1024*1024:return None
        expected=json.loads(receipt.read_text());data=report.read_bytes()
        if expected!=dict(source=source,source_sha256=source_sha256,inspector_sha256=inspector_sha256,report_sha256=hashlib.sha256(data).hexdigest()):return None
        return json.loads(data.decode('utf-8-sig'))
    except (OSError,ValueError):return None

def inspection_receipt(folder,source,source_sha256,inspector_sha256):
    report=Path(folder)/'inspection.json'
    return dict(source=source,source_sha256=source_sha256,inspector_sha256=inspector_sha256,report_sha256=file_hashes(report)['sha256'])
