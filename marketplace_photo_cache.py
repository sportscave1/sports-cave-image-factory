"""Bounded process-local reuse of verified, immutable public photograph bytes.

Call only after checking the listing's current publication state. Nothing here
caches approval, serves a URL, persists media or changes private moderation reads.
"""
from collections import OrderedDict
from concurrent.futures import Future
import hashlib
import threading


class PhotoCache:
    def __init__(self, *, max_bytes=8 * 1024 * 1024, max_entries=64, max_inflight=8, wait_seconds=35):
        self.max_bytes, self.max_entries = max_bytes, max_entries
        self.max_inflight, self.wait_seconds = max_inflight, wait_seconds
        self._values, self._inflight = OrderedDict(), {}
        self._bytes = 0
        self._condition = threading.Condition()

    def clear(self):
        with self._condition:
            self._values.clear()
            self._bytes = 0

    def read(self, listing_id, index, reference, loader):
        from marketplace_dropbox import MAX_PHOTO, validate_receipt
        value = validate_receipt(reference, MAX_PHOTO)
        key = (listing_id, index, value['id'], value['rev'], value['size'], value['sha256'])
        with self._condition:
            def ready():
                return key in self._values or key in self._inflight or len(self._inflight) < self.max_inflight
            if not self._condition.wait_for(ready, timeout=self.wait_seconds):
                raise TimeoutError('Item photo delivery is busy. Please retry.')
            if key in self._values:
                self._values.move_to_end(key)
                return self._values[key]
            future = self._inflight.get(key)
            owner = future is None
            if owner:
                future = self._inflight[key] = Future()
        if not owner:
            # A disconnected/expired waiter never cancels the shared download.
            return future.result(timeout=self.wait_seconds)
        try:
            data = loader()
            if not isinstance(data, bytes) or len(data) != value['size'] or hashlib.sha256(data).hexdigest() != value['sha256']:
                raise RuntimeError('Item source does not match the received submission.')
            with self._condition:
                if len(data) <= self.max_bytes and self.max_entries > 0:
                    while self._values and (self._bytes + len(data) > self.max_bytes or len(self._values) >= self.max_entries):
                        _, previous = self._values.popitem(last=False)
                        self._bytes -= len(previous)
                    self._values[key] = data
                    self._bytes += len(data)
            future.set_result(data)
            return data
        except BaseException as error:
            future.set_exception(error)
            raise
        finally:
            with self._condition:
                del self._inflight[key]
                self._condition.notify_all()


PHOTOS = PhotoCache()
