"""Dedicated session cache on the existing bounded OS read pool."""
from time import monotonic
from crm_campaign_home_cache import POOL,CAPACITY
from time import perf_counter
import logging

def read(state,key,load,ttl=60):
    cache=state.setdefault('reviews_cache',{});good=state.setdefault('reviews_good',{})
    entry=cache.get(key)
    if entry and entry['future'].done() and entry['completed'] is None:entry['completed']=monotonic()
    if not entry or (entry['completed'] is not None and monotonic()-entry['completed']>=ttl):
        if CAPACITY.acquire(blocking=False):
            def work():
                started=perf_counter()
                try:return load()
                finally:
                    CAPACITY.release()
                    logging.getLogger(__name__).info('reviews stage=%s duration_ms=%.1f',key[0],(perf_counter()-started)*1000)
            try:future=POOL.submit(work)
            except RuntimeError:CAPACITY.release();return good.get(key),'ERROR'
            entry=cache[key]={'future':future,'completed':None}
            if len(cache)>48:
                victim=next((k for k,v in cache.items() if k!=key and v['future'].done()),None)
                if victim:cache.pop(victim);good.pop(victim,None)
        else:return good.get(key),'REFRESHING' if key in good else 'LOADING'
    if not entry['future'].done():return good.get(key),'REFRESHING' if key in good else 'LOADING'
    try:value=entry['future'].result()
    except Exception:return good.get(key),'ERROR'
    if value is None and key[0] not in ('sources',):return good.get(key),'ERROR'
    if key[0]=='summary' and (not isinstance(value,dict) or not {'average','total','recent','five_rate','attention'}<=value.keys()):return good.get(key),'ERROR'
    # Only the currently registered job can publish a response after invalidation.
    if cache.get(key) is entry:good[key]=value
    return good.get(key),'READY'

def invalidate(state,*groups):
    for key in list(state.get('reviews_cache',{})):
        if key[0] in groups:state['reviews_cache'].pop(key)
    # Last-good values stay visible until replacement resolves.
