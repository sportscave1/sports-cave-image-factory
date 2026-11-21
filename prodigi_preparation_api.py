"""Paired Orders companion polling. The Prodigi key stays on the server."""
import re
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
import prodigi_preparation as queue


def desktop(token):
    import product_upload_staff_queue as pairing
    import os_accounts
    with queue.connect() as conn, conn.cursor() as cur:
        cur.execute('''UPDATE product_upload_desktop SET seen_at=now()
            WHERE singleton AND token_hash=%s RETURNING actor_id''', (pairing.digest(token),))
        row = cur.fetchone()
    if not row:
        raise PermissionError('Pair this desktop in Companion control first.')
    user = os_accounts.DEFAULT_STORE.get_user(row['actor_id'])
    queue.require_user(user)
    if not os_accounts.can_access_page(user, 'Upload Companion'):
        raise PermissionError('Orders companion access is required.')
    return user


async def tick(request):
    from product_upload_api import HEADERS, failure
    try:
        auth = request.headers.get('authorization', '')
        if not re.fullmatch(r'Bearer [A-Za-z0-9_-]{43}', auth):
            raise PermissionError('A paired desktop credential is required.')
        await run_in_threadpool(desktop, auth[7:])
        # No provider URLs, artwork, QA claims or production actions from Edge.
        if await request.body() not in (b'', b'{}'):
            raise ValueError('Orders tick accepts no job instructions.')
        value = await run_in_threadpool(queue.tick)
        return JSONResponse({'enabled': queue.enabled(), 'job':
            {'allocation_id': value['allocation_id'], 'status': value['status']} if value else None}, headers=HEADERS)
    except Exception as error:
        return failure(error)


ROUTES = (('/api/orders-companion/tick', tick, ('POST',)),)
