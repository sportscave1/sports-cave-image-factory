"""Bounded, process-local private preview bytes. Call only AFTER ownership checks.

No database, filesystem, credentials or customer identifiers are persisted here.
Signed browser tokens are deliberately not cache keys: fresh authorized tokens
for the same issued asset can reuse work without bypassing token validation.
"""
from collections import OrderedDict
from concurrent.futures import Future
import hashlib
import json
import threading
import time
from pathlib import Path

import requests


MAX_SOURCE_BYTES = 12 * 1024 * 1024
RECIPE_VERSION = "private-frame-v1"
FRAME_WIDTHS = (400, 1000)


class PreviewBusyError(RuntimeError):
    pass


class PreviewSourceError(RuntimeError):
    pass


class ByteCache:
    def __init__(self, *, max_bytes, max_entries, ttl=300, max_pending=12, now=time.monotonic):
        self.max_bytes, self.max_entries, self.ttl = max_bytes, max_entries, ttl
        self.max_pending, self.now = max_pending, now
        self._lock = threading.Lock()
        self._entries, self._pending = OrderedDict(), {}
        self._bytes = 0
        self._counts = dict(hits=0, misses=0, waits=0, failures=0, busy=0)

    def _prune(self):
        expired = [key for key, (_, deadline) in self._entries.items() if deadline <= self.now()]
        for key in expired:
            value, _ = self._entries.pop(key)
            self._bytes -= len(value)

    def get_or_load(self, key, loader):
        with self._lock:
            self._prune()
            cached = self._entries.get(key)
            if cached is not None:
                self._counts['hits'] += 1
                self._entries.move_to_end(key)
                return cached[0]
            future = self._pending.get(key)
            leader = future is None
            if leader:
                if len(self._pending) >= self.max_pending:
                    self._counts['busy'] += 1
                    raise PreviewBusyError("Preview queue is busy; please retry shortly.")
                future = self._pending[key] = Future()
                self._counts['misses'] += 1
            else:
                self._counts['waits'] += 1
        if not leader:
            return future.result(timeout=55)
        try:
            value = loader()
            if not isinstance(value, bytes):
                raise TypeError("Preview cache requires immutable bytes")
            with self._lock:
                if len(value) <= self.max_bytes:
                    while self._entries and (self._bytes + len(value) > self.max_bytes or len(self._entries) >= self.max_entries):
                        _, (old, _) = self._entries.popitem(last=False)
                        self._bytes -= len(old)
                    self._entries[key] = value, self.now() + self.ttl
                    self._bytes += len(value)
                self._pending.pop(key, None)
                future.set_result(value)
            return value
        except BaseException as error:
            with self._lock:
                self._counts['failures'] += 1
                self._pending.pop(key, None)
                future.set_exception(error)
            raise

    def stats(self):
        with self._lock:
            self._prune()
            return {"bytes": self._bytes, "entries": len(self._entries), "pending": len(self._pending)}

    def invalidate(self, key):
        with self._lock:
            old = self._entries.pop(key, None)
            if old:
                self._bytes -= len(old[0])

    def diagnostics(self):
        with self._lock:
            return dict(self._counts)


class PreviewPipeline:
    def __init__(self, *, source_cache=None, image_cache=None, fetch=None, render=None):
        self.sources = source_cache or ByteCache(max_bytes=16 * 1024 * 1024, max_entries=32)
        self.images = image_cache or ByteCache(max_bytes=8 * 1024 * 1024, max_entries=96)
        self.fetch, self.render = fetch or self._fetch, render or self._render
        self._downloads, self._renders = threading.BoundedSemaphore(2), threading.BoundedSemaphore(1)

    @staticmethod
    def _fetch(url):
        response = None
        try:
            response = requests.get(url, stream=True, timeout=(8, 30))
            response.raise_for_status()
            content = bytearray()
            for chunk in response.iter_content(chunk_size=64 * 1024):
                content.extend(chunk)
                if len(content) > MAX_SOURCE_BYTES:
                    raise ValueError("Certificate preview is too large.")
            return bytes(content)
        except requests.RequestException:
            raise PreviewSourceError("Certificate preview source could not be loaded.") from None
        finally:
            if response is not None:
                response.close()

    @staticmethod
    def _render(content, color, width):
        from collector_collection_offers import render_certificate_frame
        return render_certificate_frame(content, color, output_width=width)

    @staticmethod
    def source_key(asset):
        # The owner was resolved from the certificate row, never the caller.
        if not asset.get("owner_hash") or not asset.get("certificate_row_id") or asset.get("kind") != "preview":
            raise ValueError("An authorized preview identity is required")
        identity = {key: asset.get(key) for key in (
            "owner_hash", "certificate_row_id", "storage", "bucket", "key", "url", "asset_version",
        )}
        return hashlib.sha256(json.dumps(identity, sort_keys=True, default=str).encode()).hexdigest()

    def framed(self, asset, color, width, source_url):
        if color not in ("black", "oak", "white") or width not in FRAME_WIDTHS:
            raise ValueError("Invalid frame preview options")
        source_key = self.source_key(asset)
        from collector_collection_offers import FRAME_BOX
        template = Path(__file__).resolve().parent / "templates" / f"{color}-frame-template.jpg"
        stat = template.stat()
        image_key = (source_key, color, width, RECIPE_VERSION, FRAME_BOX, stat.st_size, stat.st_mtime_ns)

        def download():
            if not self._downloads.acquire(timeout=5):
                raise PreviewBusyError("Preview downloads are busy; please retry shortly.")
            try:
                content = self.fetch(source_url())
                if len(content) > MAX_SOURCE_BYTES:
                    raise ValueError("Certificate preview is too large.")
                return content
            finally:
                self._downloads.release()

        def compose():
            content = self.sources.get_or_load(source_key, download)
            if not self._renders.acquire(timeout=5):
                raise PreviewBusyError("Preview rendering is busy; please retry shortly.")
            try:
                return self.render(content, color, width)
            except Exception:
                self.sources.invalidate(source_key)
                raise
            finally:
                self._renders.release()

        return self.images.get_or_load(image_key, compose)


PREVIEWS = PreviewPipeline()
