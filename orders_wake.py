"""Paired, level-triggered Orders notifications from already-durable state.

No webhook acknowledgement, supplier action or customer payload lives here. The
opaque cursor changes after mirror arrival, allocation, JPG readiness or an
actionable preparation transition. A missed response is replayed on reconnect.
Long waits hold no database connection; all listeners share one short snapshot.
"""
import asyncio
import re
import threading
import time
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
import prodigi_preparation as prep
from companion_poll_transaction import connection

WAIT_SECONDS=20
CHECK_SECONDS=2
_waiters=threading.BoundedSemaphore(2)
_reads=threading.BoundedSemaphore(1)
_auth=threading.BoundedSemaphore(1)
_cache_lock=threading.Lock()
_cache=None
_cache_at=0.0

SQL="""WITH recent_orders AS (
    SELECT shopify_order_id,updated_at,synced_at,created_at FROM shopify_orders
    ORDER BY created_at DESC,shopify_order_id LIMIT 50
)
SELECT
    (SELECT count(*) FROM recent_orders) AS arrivals,
    (SELECT md5(string_agg(jsonb_build_array(shopify_order_id,updated_at,synced_at,created_at)::text,
        ',' ORDER BY shopify_order_id)) FROM recent_orders) AS arrival_revision,
    (SELECT count(*) FROM edition_orders) AS allocations,
    (SELECT max(assigned_at)::text FROM edition_orders) AS allocation_at,
    (SELECT count(*) FROM auto_edition_jobs WHERE status='Ready') AS jpgs,
    (SELECT max(updated_at)::text FROM auto_edition_jobs WHERE status='Ready') AS jpg_at,
    count(*) AS handoffs,md5(string_agg(jsonb_build_array(key,value->>'status',updated_at)::text,
        ',' ORDER BY key)) AS handoff_revision
FROM app_settings WHERE key LIKE 'prodigi_prepare:%%'
    AND NOT COALESCE((value->>'hidden')::boolean,false)
    AND value->>'status' IN ('Queued','Checking QA','Awaiting browser upload',
        'Awaiting product selection','Awaiting dashboard QA','Ready for manual payment')
"""


def version():
    global _cache,_cache_at
    with _cache_lock:
        if _cache is not None and time.monotonic()-_cache_at<CHECK_SECONDS:
            return _cache
        with connection(prep.connect,slots=_reads) as conn,conn.cursor() as cur:
            cur.execute(SQL)
            value=prep.digest(cur.fetchone())
        _cache=value
        _cache_at=time.monotonic()
        return value


async def changed(after,request):
    deadline=time.monotonic()+WAIT_SECONDS
    while True:
        current=await run_in_threadpool(version)
        if current!=after:return current,True
        remaining=deadline-time.monotonic()
        if remaining<=0:return current,False
        if await request.is_disconnected():return current,False
        # Align listeners with the shared snapshot expiry rather than sleeping
        # another full interval after reading an almost-expired cached version.
        refresh=max(0.05,CHECK_SECONDS-(time.monotonic()-_cache_at))
        await asyncio.sleep(min(CHECK_SECONDS,refresh,remaining))


async def listen(request):
    from prodigi_preparation_api import desktop
    from product_upload_api import HEADERS,failure
    try:
        auth=request.headers.get('authorization','')
        if not re.fullmatch(r'Bearer [A-Za-z0-9_-]{43}',auth):
            raise PermissionError('A paired desktop credential is required.')
        after=request.query_params.get('after','')
        if set(request.query_params)-{'after'} or (after and not re.fullmatch(r'[a-f0-9]{64}',after)):
            raise ValueError('Only an opaque Orders notification cursor is accepted.')
        # A long-poll reconnect must never occupy the native tick's auth slot.
        await run_in_threadpool(desktop,auth[7:],slots=_auth)
        state=request.headers.get('x-sports-cave-orders-wake-state','')
        if state in ('queue-failed','notification-invalid','transport-failed'):
            import logging
            logging.getLogger(__name__).warning('Orders notification reconnect previous=%s',state)
        if not prep.enabled():return JSONResponse(dict(enabled=False,changed=False),headers=HEADERS)
        if not _waiters.acquire(blocking=False):
            return JSONResponse(dict(retry=True),status_code=429,headers={**HEADERS,'Retry-After':'5'})
        try:
            current,ready=await changed(after,request)
            return JSONResponse(dict(enabled=True,version=current,changed=ready),headers=HEADERS)
        finally:_waiters.release()
    except Exception as error:return failure(error)
