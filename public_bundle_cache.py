"""Bounded precompression of installed, public Streamlit bundles only.

One daemon warms files off the HTTP event loop. No response/customer data enters
this cache; missing, changed or not-yet-warmed files use normal gzip delivery.
"""
from dataclasses import dataclass
import hashlib
from functools import lru_cache
from importlib.util import find_spec
import logging
from pathlib import Path
import re
import threading
import time

import brotli

LOG = logging.getLogger(__name__)
HASHED_BUNDLE = re.compile(r"^/static/(?:js|css)/[A-Za-z0-9_.-]+\.[A-Za-z0-9_-]{6,}\.(?:js|css)$")


@dataclass(frozen=True)
class Bundle:
    signature: tuple
    etag: str
    data: bytes


class PublicBundleCache:
    def __init__(self, root=None, *, max_bytes=16 * 1024 * 1024,
                 max_file_bytes=8 * 1024 * 1024, max_entries=512):
        if root is None:
            spec = find_spec("streamlit")
            root = Path(spec.origin).parent / "static" / "static"
        self.root = Path(root).resolve()
        self.max_bytes = max_bytes
        self.max_file_bytes = max_file_bytes
        self.max_entries = max_entries
        self.entries = {}
        self.bytes = 0
        self.finished = threading.Event()
        self._lock = threading.Lock()
        self._started = False

    def source(self, path):
        if not HASHED_BUNDLE.fullmatch(path):
            return None
        candidate = (self.root / path.removeprefix("/static/")).resolve()
        return candidate if candidate.is_relative_to(self.root) else None

    def warm(self):
        began = time.perf_counter()
        try:
            files = [p for folder in ("js", "css") for p in (self.root / folder).glob("*")]
            files.sort(key=lambda p: (not p.name.startswith("index."), p.name))
            for source in files:
                path = "/static/" + source.relative_to(self.root).as_posix()
                if self.source(path) != source.resolve():
                    continue
                stat = source.stat()
                if not 1024 <= stat.st_size <= self.max_file_bytes:
                    continue
                raw = source.read_bytes()
                signature = (stat.st_mtime_ns, stat.st_size)
                after = source.stat()
                if signature != (after.st_mtime_ns, after.st_size):
                    continue
                data = brotli.compress(raw, quality=5)
                if len(data) >= len(raw):
                    continue
                # Same validator as Starlette FileResponse. A different handler
                # or file version must never receive this precompressed payload.
                etag = '"' + hashlib.md5(
                    f"{stat.st_mtime}-{stat.st_size}".encode(), usedforsecurity=False
                ).hexdigest() + '"'
                with self._lock:
                    if len(self.entries) >= self.max_entries or self.bytes + len(data) > self.max_bytes:
                        break
                    if path not in self.entries:
                        self.entries[path] = Bundle(signature, etag, data)
                        self.bytes += len(data)
        except Exception:
            LOG.exception("public_bundle_warm_failed")
        finally:
            self.finished.set()
            LOG.info("public_bundle_warm entries=%d compressed_bytes=%d elapsed_ms=%.1f",
                     len(self.entries), self.bytes, (time.perf_counter() - began) * 1000)

    def start(self):
        with self._lock:
            if self._started:
                return
            self._started = True
        threading.Thread(target=self.warm, name="public-bundle-warm", daemon=True).start()

    def get(self, path):
        with self._lock:
            entry = self.entries.get(path)
        if entry is None:
            return None
        source = self.source(path)
        try:
            stat = source.stat()
        except (AttributeError, OSError):
            return None
        return entry if entry.signature == (stat.st_mtime_ns, stat.st_size) else None


@lru_cache(maxsize=1)
def default_cache():
    return PublicBundleCache()
