"""Account-authorised, read-only deltas for the latest 75 mirrored orders.

All links and cells use the existing presenter. No Shopify/supplier requests,
artwork downloads, allocation changes or preparation actions run in this feed.
"""
from collections import OrderedDict
from copy import deepcopy
import hashlib,json,re,threading,time
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
import prodigi_preparation as prep

_lock=threading.Lock()
_builders=threading.BoundedSemaphore(2)
_cache=OrderedDict()
_building=set()
MAX_ROWS=2000
MAX_AGE=30


def allowed(actor):
    import os_accounts
    return prep.enabled() and os_accounts.is_admin(actor) and os_accounts.can_access_page(actor,'Prodigi')


def key(actor,query):
    return str(actor.get('id') or ''),bool(allowed(actor)),query


def signature(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,default=str).encode()).hexdigest()


def marker():
    # Reuse the shared short committed-state probe. Completed-state and mapping
    # updates are also picked up by the bounded 30-second snapshot lifetime.
    from orders_wake import version
    return version()


def build(actor,query):
    import order_allocator,orders_page,psd_directory
    from orders_display_reads import download_links
    import orders_prodigi_grid as grid
    source=order_allocator.load_hybrid_orders_snapshot(limit=75,search=query)
    if source is None:raise RuntimeError('Orders are temporarily unavailable.')
    raw=[orders_page._normalise_row(r) for r in source.get('rows',[])]
    if len(raw)>MAX_ROWS:raise ValueError('This result is too large for live updates. Narrow the order search.')
    display=orders_page._display_rows(raw,normalised=True,resources=(psd_directory.page_directory(),download_links(raw)))
    permitted=allowed(actor)
    statuses=grid.batch_status([r.get('edition_order_id') for r in raw]) if permitted else {}
    rows=grid.payload_rows(raw,display,statuses,allowed=permitted)
    identities=[r['id'] for r in rows]
    if len(set(identities))!=len(identities):raise ValueError('Order identities need review before live updates.')
    return dict(raw=raw,rows=rows,version=signature([(r['id'],r['revision']) for r in rows]))


def snapshot(actor,query):
    identity=key(actor,query);stamp=time.monotonic();current_marker=marker()
    with _lock:
        previous=_cache.get(identity)
        if previous and previous['marker']==current_marker and stamp-previous['at']<MAX_AGE:
            _cache.move_to_end(identity)
            return deepcopy(previous['snapshots'][-1]),False
        if identity in _building:
            if previous:return deepcopy(previous['snapshots'][-1]),True
            raise RuntimeError('Orders updates are loading; retry shortly.')
        _building.add(identity)
    if not _builders.acquire(blocking=False):
        with _lock:_building.discard(identity)
        if previous:return deepcopy(previous['snapshots'][-1]),True
        raise RuntimeError('Orders updates are busy; retry shortly.')
    try:
        fresh=build(actor,query)
        with _lock:
            old=_cache.get(identity) or {};history=list(old.get('snapshots',[]))
            if not history or history[-1]['version']!=fresh['version']:history.append(fresh)
            else:history[-1]=fresh
            _cache[identity]=dict(at=time.monotonic(),marker=current_marker,snapshots=history[-3:])
            _cache.move_to_end(identity)
            while len(_cache)>8:_cache.popitem(last=False)
        return deepcopy(fresh),False
    finally:
        with _lock:_building.discard(identity)
        _builders.release()


def recalled(actor,query,version):
    with _lock:
        entry=_cache.get(key(actor,query)) or {}
        saved=next((s for s in entry.get('snapshots',[]) if s['version']==version),None)
        return deepcopy(saved) if saved is not None else None


def delta(saved,known):
    rows=saved['rows'];ids=[r['id'] for r in rows]
    return dict(version=saved['version'],order=ids,
        rows=[r for r in rows if known.get(r['id'])!=r['revision']],
        removed=sorted(set(known)-set(ids)))


async def feed(request):
    from files_upload_api import _request_user
    from product_upload_api import HEADERS,failure
    started=time.perf_counter()
    try:
        actor=await run_in_threadpool(_request_user,request,required_page='Orders')
        raw=bytearray()
        async for block in request.stream():
            raw.extend(block)
            if len(raw)>350000:raise ValueError('Orders update request is too large.')
        body=json.loads(raw)
        if not isinstance(body,dict) or set(body)!={'query','known'}:raise ValueError('Choose a saved Orders view.')
        query=body['query'];known=body['known']
        if not isinstance(query,str) or len(query)>200:raise ValueError('Order search is too long.')
        if not isinstance(known,dict) or len(known)>MAX_ROWS or any(
            not isinstance(k,str) or not re.fullmatch(r'[A-Za-z0-9:_.-]{1,150}',k) or
            not isinstance(v,str) or not re.fullmatch(r'[a-f0-9]{64}',v) for k,v in known.items()):
            raise ValueError('Orders update identities are invalid.')
        saved,delayed=await run_in_threadpool(snapshot,actor,query.strip())
        result=delta(saved,known);elapsed=(time.perf_counter()-started)*1000
        if result['rows'] or result['removed'] or delayed or elapsed>1000:
            import logging
            logging.getLogger(__name__).info('ORDERS_FEED rows=%d changed=%d removed=%d delayed=%s duration_ms=%.1f',
                len(saved['rows']),len(result['rows']),len(result['removed']),delayed,elapsed)
        return JSONResponse(dict(**result,delayed=delayed),headers={**HEADERS,'Server-Timing':f'orders_feed;dur={elapsed:.1f}'})
    except Exception as error:return failure(error)
