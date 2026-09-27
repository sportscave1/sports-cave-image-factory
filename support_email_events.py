"""Authenticated same-origin SSE transport of mailbox state only."""
import asyncio
import json
import time

from starlette.responses import JSONResponse, StreamingResponse
from support_email_idle import HUB

EVENTS_PATH = '/api/os/top-bar/email-events'


async def email_events(request):
    from top_bar_api import _claims
    claims = _claims(request)
    if not claims or 'Email' not in set(claims.get('allowed_routes') or ()):
        return JSONResponse({'ok': False, 'error': 'Access not approved.'}, status_code=403)
    return StreamingResponse(event_stream(request), media_type='text/event-stream', headers={
        'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})


async def event_stream(request, *, hub=HUB, duration=55, interval=.25):
    previous = ''
    started = time.monotonic()
    heartbeat = started
    yield ': connected\n\n'
    # Rotate streams so ordinary token expiry/permission validation still applies.
    while time.monotonic() - started < duration:
        if await request.is_disconnected():
            return
        value = hub.snapshot()
        if value.get('version') != previous and time.time() - value.get('checked_at', 0) < 120:
            previous = value['version']
            allowed = {k: value[k] for k in ('mailbox', 'version', 'uidvalidity', 'uidnext', 'unseen', 'messages', 'checked_at')}
            yield 'data: ' + json.dumps(allowed, separators=(',', ':')) + '\n\n'
        elif time.monotonic() - heartbeat > 10:
            heartbeat = time.monotonic()
            yield ': keepalive\n\n'
        await asyncio.sleep(interval)
