"""Bounded published-only cache; separate from admin KPI/list session caches."""
from crm_cache import DisplayCache
CACHE=DisplayCache(limit=256,byte_limit=2*1024*1024)

def load(store,key,fn,ttl=30):
    identity=(store.connect,key)
    value=CACHE.get(identity)
    if value is None:value=CACHE.put(identity,fn(),ttl)
    return value
