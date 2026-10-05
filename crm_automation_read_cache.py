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
READ_DEADLINE = 20
HOME_GROUPS = ('identities','counts','delivery','table','activity','publication')
LOG=logging.getLogger(__name__)

def lifecycle(event,key,future=None,**values):
    LOG.warning('AUTOMATIONS_HOME_%s read=%s key=%s future=%s %s',event,key[0],__import__('hashlib').sha256(repr(key).encode()).hexdigest()[:12],hex(id(future)) if future else '-', ' '.join(str(k)+'='+str(v) for k,v in values.items()))


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
    generation=state.setdefault('automation_read_generation',__import__('uuid').uuid4().hex[:12])
    cache = state.setdefault('campaign_home_cache', {})
    identity = (store.connect, key)
    entry = cache.get(identity)
    if identity in state.get('automation_read_terminal',{}):return entry[1] if entry else None
    if entry:
        future = entry[1]
        # Start the TTL at completion, not submission: a slow response must not
        # immediately expire and trigger a second identical read.
        if not future.done():
            lifecycle('READ_REUSE',key,future)
            return future
        if entry[0] is None:
            entry = cache[identity] = (monotonic(), future)
        if monotonic() - entry[0] < ttl: return future
    if not CAPACITY.acquire(blocking=False): return None
    def work():
        started = perf_counter()
        try:
            value=pack(load())
            lifecycle('READ_COMPLETE',key,generation=generation,elapsed_ms=round((perf_counter()-started)*1000),rows=len(value) if isinstance(value,list) else -1)
            return value
        except Exception as exc:
            lifecycle('READ_ERROR',key,exception=type(exc).__name__)
            raise
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
        state.get('automation_read_started',{}).pop(victim,None)
        state.get('automation_read_terminal',{}).pop(victim,None)
        state.get('campaign_home_resolved', {}).pop(victim, None)
        state.get('campaign_home_reported_errors', {}).pop(victim, None)
    try: future = POOL.submit(work)
    except RuntimeError:
        CAPACITY.release()
        raise
    future.add_done_callback(lambda f: CAPACITY.release() if f.cancelled() else None)
    cache[identity] = (None, future)
    state.setdefault('automation_read_started',{})[identity]=monotonic()
    lifecycle('READ_START',key,future,generation=generation,cache_entries=len(cache))
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
    if identity in state.get('automation_read_terminal',{}):
        return unpack(previous),state['automation_read_terminal'][identity]
    starts=state.setdefault('automation_read_started',{})
    started=starts.setdefault(identity,monotonic())
    while len(starts)>MAX_ENTRIES*2:
        victim=next((i for i in starts if i!=identity and i not in state.get('campaign_home_cache',{})),None)
        if victim is None:break
        starts.pop(victim,None)
        state.get('automation_read_terminal',{}).pop(victim,None)
    if key[0] in HOME_GROUPS and (future is None or not future.done()) and monotonic()-started>=READ_DEADLINE:
        state.setdefault('automation_read_terminal',{})[identity]='TIMED_OUT'
        if future is not None:future.cancel()
        lifecycle('READ_TIMEOUT',key,future,elapsed_ms=round((monotonic()-started)*1000))
        return unpack(previous),'TIMED_OUT'
    if current is None or current[1] is not future:
        return unpack(previous), 'REFRESHING' if previous is not None else 'NOT_STARTED'
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
        if key[0] in HOME_GROUPS:state.setdefault('automation_read_terminal',{})[identity]='ERROR'
        return unpack(previous), 'ERROR'
    lifecycle('RESULT_CONSUMED',key,future,generation=state.get('automation_read_generation','-'),rows=len(value))
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
        state.get('automation_read_started',{}).pop(identity,None)
        state.get('automation_read_terminal',{}).pop(identity,None)
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
