"""Bounded account-scoped picker display cache; never used for send facts."""
from copy import deepcopy
import logging
import threading
import time
from crm_cache import DisplayCache

TTL = 600
_CACHE = DisplayCache(limit=256, byte_limit=8*1024*1024)
_LOCKS = [threading.RLock() for _ in range(32)]


def load(key, loader):
    # Striped locks avoid unbounded per-search locks and duplicate cold requests.
    with _LOCKS[hash(key) % len(_LOCKS)]:
        row = _CACHE.get(key)
        if row and row['until'] > time.monotonic():
            return deepcopy(row['value']), row['stale']
        try:
            value = loader()
        except Exception as exc:
            if not row: raise
            logging.getLogger(__name__).warning('crm_picker_cached_fallback type=%s', type(exc).__name__)
            row.update(until=time.monotonic()+60, stale=True)
            _CACHE.put(key, row, 3600)
            return deepcopy(row['value']), True
        _CACHE.put(key, dict(value=value, until=time.monotonic()+TTL, stale=False), 3600)
        return deepcopy(value), False
