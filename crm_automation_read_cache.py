"""Automations-only bounded reads. Campaign queue and cache remain unchanged."""
from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore
from time import monotonic, perf_counter
import logging
import pickle
import zlib
from dataclasses import dataclass

POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix='automation-read')
CAPACITY = BoundedSemaphore(6)
MAX_ENTRIES = 8
SUMMARY_GROUPS = ('counts', 'delivery', 'attribution')


@dataclass(frozen=True)
class PackedRows:
    """Trusted internal query data only; never deserialize client input."""
    data: bytes
    def unpack(self):return pickle.loads(zlib.decompress(self.data))
    def __iter__(self):return iter(self.unpack())

def pack(value):
    if not isinstance(value,list):return value
    raw=pickle.dumps(value,protocol=5)
    if len(raw)<65536:return value
    data=zlib.compress(raw,1)
    if len(data)>1024*1024:raise ValueError('Analytics result exceeds UI cache budget')
    return PackedRows(data)

def unpack(value):return value.unpack() if isinstance(value,PackedRows) else value


def job(state, store, key, load, *, ttl=60):
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
        try: return pack(load())
        finally:
            logging.getLogger(__name__).info('automation_read stage=%s duration_ms=%.1f', key[0], (perf_counter()-started)*1000)
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
    future.add_done_callback(lambda f: CAPACITY.release() if f.cancelled() else None)
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
        return unpack(previous), 'REFRESHING' if previous is not None else 'UNRESOLVED'
    if future is None or not future.done():
        return unpack(previous), 'REFRESHING' if previous is not None else 'LOADING'
    if current[0] is None:
        state['campaign_home_cache'][identity] = (monotonic(), future)
    try:
        raw = future.result()
        value = unpack(raw)
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
            logging.getLogger(__name__).warning('automation_read stage=%s failure=%s', key[0], type(exc).__name__)
            reported[identity]=future
        __import__('traceback').clear_frames(exc.__traceback__)
        return unpack(previous), 'ERROR'
    resolved[identity] = raw if isinstance(raw,PackedRows) else value
    while len(resolved) > MAX_ENTRIES:
        victim = next((i for i in resolved if i != identity and i[1][0] not in SUMMARY_GROUPS), None)
        if victim is None: break
        resolved.pop(victim)
    return value, 'READY'


def dispose(state,*,keep_compact=False):
    """Cancel queued UI reads, release completed/large results on navigation.

    Running database reads finish under the existing statement timeout; they
    cannot write session state or start replacement jobs after disposal.
    """
    cache=state.get('campaign_home_cache',{})
    for identity,(_,future) in list(cache.items()):
        if not future.done():future.cancel()
        if keep_compact and future.done() and not future.cancelled():
            try:
                if not isinstance(future.result(),PackedRows):continue
            except Exception:pass
        cache.pop(identity,None)
        state.get('campaign_home_resolved',{}).pop(identity,None)
    state.pop('campaign_home_reported_errors',None)
    if not keep_compact:
        state.pop('campaign_home_cache',None)
        state.pop('campaign_home_resolved',None)


def isolated(function):
    """Section failures must not unwind the OS shell; no private error text."""
    from functools import wraps
    @wraps(function)
    def render(*args,**kwargs):
        try:return function(*args,**kwargs)
        except Exception as exc:
            logging.getLogger(__name__).error('automation_section stage=%s failure=%s',function.__name__,type(exc).__name__)
            import streamlit as st
            st.caption('This Automations section is temporarily unavailable. Navigation remains available.')
    return render
