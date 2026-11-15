"""Short-lived, session-owned readiness tickets; never transports email content.

The normal authenticated component event still validates selection and fetches
the result. This endpoint only wakes that event when its existing worker ends.
"""
import asyncio
from collections import OrderedDict
import secrets
import threading
import time

from starlette.responses import JSONResponse

PATH = '/api/os/email/read-ready'
_tickets = OrderedDict()
_lock = threading.Lock()


def issue(future, owner, scope):
    now = time.monotonic()
    with _lock:
        for key, ticket in list(_tickets.items()):
            if ticket['expires'] < now or ticket['scope'] == scope:
                _tickets.pop(key, None)
        while len(_tickets) >= 256:
            _tickets.popitem(last=False)
        key = secrets.token_urlsafe(32)
        _tickets[key] = dict(future=future, owner=str(owner), scope=scope, expires=now+30)
        return key


def revoke(scope):
    with _lock:
        for key, ticket in list(_tickets.items()):
            if ticket['scope'] == scope:_tickets.pop(key, None)


async def read_ready(request):
    from support_email_access import current_email_claims
    claims = await asyncio.to_thread(current_email_claims, request)
    key = request.headers.get('X-Email-Read', '')
    with _lock:ticket = _tickets.get(key)
    def valid():
        with _lock:
            return (ticket is not None and _tickets.get(key) is ticket
                    and ticket['expires'] > time.monotonic()
                    and claims.get('sub') == ticket['owner']
                    and 'Email' in claims.get('allowed_routes', ())
                    and float(claims.get('exp', 0)) > time.time())
    headers = {'Cache-Control': 'no-store'}
    if not valid():return JSONResponse({'ready': False}, status_code=403, headers=headers)
    with _lock:
        if ticket.get('waiting'):
            return JSONResponse({'ready': False}, status_code=409, headers=headers)
        ticket['waiting'] = True
    try:
        await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(ticket['future'])), timeout=20)
    except TimeoutError:
        pass
    except asyncio.CancelledError:
        if not ticket['future'].cancelled():raise  # Do not swallow request cancellation.
    except Exception:
        pass  # The component receives the provider's safe error, never this route.
    finally:
        with _lock:ticket['waiting'] = False
    claims = await asyncio.to_thread(current_email_claims, request)
    if not valid():return JSONResponse({'ready': False}, status_code=403, headers=headers)
    return JSONResponse({'ready': ticket['future'].done()}, headers=headers)
