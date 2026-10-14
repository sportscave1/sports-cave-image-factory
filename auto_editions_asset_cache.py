"""Bounded disposable cache of checksum-verified prepared PNG bytes.

Dropbox remains authoritative storage. Authorization and source revision checks
remain in the caller; this cache never contains credentials or PSDs.
"""
from collections import OrderedDict
from pathlib import Path
import shutil
import tempfile
import threading

import auto_editions as ae


class AssetCache:
    def __init__(self, max_bytes=512 * 1024 * 1024):
        self.max_bytes = max_bytes
        self.entries = OrderedDict()
        self.lock = threading.Lock()
        self.directory = None

    def copy(self, digest, destination):
        with self.lock:
            path = self.entries.get(digest)
            if path is None:
                return False
            if not path.is_file() or ae.file_hash(path) != digest:
                path.unlink(missing_ok=True)
                del self.entries[digest]
                return False
            shutil.copyfile(path, destination)
            self.entries.move_to_end(digest)
            return True

    def remember(self, digest, source):
        source = Path(source)
        size = source.stat().st_size
        if size > self.max_bytes or ae.file_hash(source) != digest:
            return
        with self.lock:
            if self.directory is None:
                self.directory = tempfile.TemporaryDirectory(prefix='sc-prepared-cache-')
            if digest in self.entries:
                self.entries.move_to_end(digest)
                return
            while self.entries and sum(p.stat().st_size for p in self.entries.values()) + size > self.max_bytes:
                _, old = self.entries.popitem(last=False)
                old.unlink(missing_ok=True)
            target = Path(self.directory.name) / digest
            try:shutil.copyfile(source, target)
            except OSError:
                target.unlink(missing_ok=True)
                raise
            self.entries[digest] = target


prepared_assets = AssetCache()
