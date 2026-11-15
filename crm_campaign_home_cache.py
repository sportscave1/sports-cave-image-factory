"""Session-owned read cache. Worker threads never write Streamlit state."""
from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore
from time import monotonic, perf_counter
import logging
from crm_campaign_home_data import TTL

POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix='campaign-home')
CAPACITY = BoundedSemaphore(12)
MAX_ENTRIES = 24
SUMMARY_GROUPS = ('counts', 'delivery', 'attribution')


def job(state, store, key, load, *, ttl=TTL):
    cache = state.setdefault('campaign_home_cache', {})
    identity = (store.connect, key)
    entry = cache.get(identity)
    if entry:
        future = entry[1]
        # Start the TTL at completion, not submission: a slow response must not
        # immediately expire and trigger a second identical read.
        if not future.done(): return future
        if entry[0] is None:
            entry = cache[identity] = (monotonic(), future)
        if monotonic() - entry[0] < ttl: return future
    if not CAPACITY.acquire(blocking=False): return None
    def work():
        started = perf_counter()
        try: return load()
        finally:
            logging.getLogger(__name__).info('campaign_home stage=%s duration_ms=%.1f', key[0], (perf_counter()-started)*1000)
            CAPACITY.release()
    # Evict only completed entries, never clear unrelated in-flight work.
    if len(cache) >= MAX_ENTRIES:
        victim = next((i for i,e in cache.items() if e[1].done() and i != identity and i[1][0] not in SUMMARY_GROUPS), None)
        if victim is None:
            CAPACITY.release()
            return None
        cache.pop(victim)
        state.get('campaign_home_resolved', {}).pop(victim, None)
        state.get('campaign_home_reported_errors', {}).pop(victim, None)
    try: future = POOL.submit(work)
    except RuntimeError:
        CAPACITY.release()
        raise
    cache[identity] = (None, future)
    return future


def resolve(state, store, key, future, *, fields=None):
    """Publish only the currently registered response; retain good data on error.

    A valid empty table is authoritative. Empty/missing summary fields are not.
    Payloads are replaced atomically rather than merged with partial responses.
    """
    identity = (store.connect, key)
    resolved = state.setdefault('campaign_home_resolved', {})
    previous = resolved.get(identity)
    current = state.get('campaign_home_cache', {}).get(identity)
    if current is None or current[1] is not future:
        return previous, 'REFRESHING' if previous is not None else 'UNRESOLVED'
    if future is None or not future.done():
        return previous, 'REFRESHING' if previous is not None else 'LOADING'
    if current[0] is None:
        state['campaign_home_cache'][identity] = (monotonic(), future)
    try:
        value = future.result()
        if fields is not None:
            if not isinstance(value, dict) or not all(f in value for f in fields):
                raise ValueError('Incomplete summary')
            value = {field:value[field] for field in fields}
            if any(v is None for field,v in value.items() if field not in ('click_rate','bounce_rate')):
                raise ValueError('Incomplete summary')
        elif not isinstance(value, list):
            raise ValueError('Incomplete campaign list')
    except Exception as exc:
        # Never log exception text: database diagnostics may contain private data.
        reported=state.setdefault('campaign_home_reported_errors', {})
        if reported.get(identity) is not future:
            logging.getLogger(__name__).warning('campaign_home stage=%s failure=%s', key[0], type(exc).__name__)
            reported[identity]=future
        return previous, 'ERROR'
    resolved[identity] = value
    while len(resolved) > MAX_ENTRIES:
        victim = next((i for i in resolved if i != identity and i[1][0] not in SUMMARY_GROUPS), None)
        if victim is None: break
        resolved.pop(victim)
    return value, 'READY'
