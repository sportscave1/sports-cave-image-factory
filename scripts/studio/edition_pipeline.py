"""Admission for one prepared upload overlapping one native preparation."""
from pathlib import Path
import os
import shutil

GIB = 1024 ** 3
MAX_ACTIVE_BYTES = 8 * GIB
MIN_FREE_DISK = 12 * GIB
MIN_FREE_RAM = 4 * GIB


def footprint(rows, root):
    size = count = 0
    for row in rows:
        folder = Path(row['folder'])
        if folder.is_symlink() or folder.resolve().parent != Path(root).resolve():
            raise ValueError('Unowned pipeline folder.')
        for parent, directories, files in os.walk(folder, followlinks=False):
            for name in directories + files:
                path = Path(parent)/name
                count += 1
                if count > 4096 or path.is_symlink() or path.is_junction():
                    raise ValueError('Unbounded pipeline workspace.')
                if path.is_file():size += path.stat().st_size
    return size


def native_budget(rows, row, root):
    peers=[r for r in rows if r is not row and r.get('status')=='Working']
    if not peers:return True # Existing serial resource checks remain authoritative.
    try:
        import psutil
        source=row['context']['metadata']['size']
        return (all(released_upload(r) for r in peers)
                and footprint(peers+[row],root)+2*source+2*GIB<=MAX_ACTIVE_BYTES
                and shutil.disk_usage(root).free>=8*GIB
                and psutil.virtual_memory().available>=MIN_FREE_RAM)
    except (OSError,ValueError,KeyError,ImportError):return False


def released_upload(row):
    return (row.get('status') == 'Working' and row.get('phase') == 'Uploading'
            and row.get('native_released') is True and row.get('upload_protocol') == 1
            and row.get('context', {}).get('automatic') is True
            and not row.get('cancel_requested') and not row.get('checkpoint_pending'))


def admission(rows, root, *, paused=False, processor_locked=False):
    """Fail closed on unknown resources/paths; never queue another native job."""
    active = [r for r in rows if r.get('status') == 'Working']
    if paused or processor_locked or len(active) != 1 or not released_upload(active[0]):
        return None
    if any(r.get('checkpoint_pending') or r.get('status') == 'Recovering' for r in rows):
        return None
    try:
        import psutil
        root = Path(root).resolve()
        # Reserve the maximum admitted 2 GiB PSD before the second download.
        if footprint(active,root)>MAX_ACTIVE_BYTES-2*GIB:return None
        if shutil.disk_usage(root).free < MIN_FREE_DISK or psutil.virtual_memory().available < MIN_FREE_RAM:
            return None
        return active[0]
    except (OSError, ValueError, KeyError, ImportError):
        return None
