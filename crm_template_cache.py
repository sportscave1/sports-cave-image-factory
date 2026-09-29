"""Bounded process-local display cache, shared by the composer and template list."""
from crm_cache import DisplayCache

TTL = 600
CACHE = DisplayCache(limit=128, byte_limit=4*1024*1024)


def cached(store, key, load):
    # Serialize misses with invalidation: a pre-save read cannot repopulate stale data
    # after the successful write has invalidated the cache.
    with CACHE.lock:
        identity = (store.connect, *key)
        value = CACHE.get(identity)
        if value is None:
            value = load()
            CACHE.put(identity, value, TTL)
        return value


def invalidate():
    CACHE.invalidate()
