"""Owner-session report handoff; no deploy, credentials or arbitrary job endpoint."""
import json
import logging
from urllib.parse import parse_qs

from starlette.concurrency import run_in_threadpool
from starlette.responses import HTMLResponse, JSONResponse

from speed_optimisation import MAX_BYTES, Reports

HEADERS = {'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff',
           'Content-Security-Policy': "default-src 'none'; form-action 'self'; frame-ancestors 'none'"}


def store():
    from supabase_backend import connect
    return Reports(connect)


async def actor(request):
    from files_upload_api import FilesUploadError, _request_user, _same_origin
    import os_accounts
    if request.method == 'POST' and (not request.headers.get('origin') or not _same_origin(request)):
        raise PermissionError('Request origin rejected.')
    try:
        user = await run_in_threadpool(_request_user, request, required_page='Speed Optimisation')
    except FilesUploadError as error:
        raise PermissionError('Owner access required.') from error
    if not os_accounts.can_access_page(user, 'Speed Optimisation'):
        raise PermissionError('Owner access required.')
    return user


async def reports(request):
    try:
        await actor(request)
        return JSONResponse({'reports': await run_in_threadpool(store().recent)}, headers=HEADERS)
    except Exception as error:
        return failure(error)


def failure(error):
    if isinstance(error, PermissionError):
        return JSONResponse({'error': 'Owner access and same-origin publication required.'}, status_code=403, headers=HEADERS)
    if isinstance(error, (ValueError, KeyError, TypeError)):
        return JSONResponse({'error': 'Invalid speed report. Check required fields and timing samples.'}, status_code=400, headers=HEADERS)
    logging.getLogger(__name__).warning('speed_report_failed type=%s', type(error).__name__)
    return JSONResponse({'error': 'Speed report storage unavailable.'}, status_code=503, headers=HEADERS)


async def publish(request):
    try:
        await actor(request)
        if request.method == 'GET':
            return HTMLResponse('''<!doctype html><html lang="en"><meta charset="utf-8">
                <title>Publish speed report</title><main><h1>Publish daily speed report</h1>
                <form method="post"><label for="report">Report JSON</label><br>
                <textarea id="report" name="report" rows="24" cols="90" required></textarea><br>
                <button>Publish report</button></form></main></html>''', headers=HEADERS)
        encoded = bytearray()
        async for chunk in request.stream():
            if len(encoded) + len(chunk) > MAX_BYTES * 4:
                return JSONResponse({'error': 'Report too large.'}, status_code=413, headers=HEADERS)
            encoded.extend(chunk)
        content_type = request.headers.get('content-type', '').split(';')[0]
        if content_type == 'application/json':
            raw = encoded.decode('utf-8')
        elif content_type == 'application/x-www-form-urlencoded':
            raw = parse_qs(encoded.decode('ascii'), strict_parsing=True, max_num_fields=1)['report'][0]
        else:
            return JSONResponse({'error': 'Expected JSON or a report form.'}, status_code=415, headers=HEADERS)
        if len(raw.encode()) > MAX_BYTES:
            raise ValueError('Report too large.')
        report = await run_in_threadpool(store().publish, json.loads(raw))
        return JSONResponse({'published': report['id'], 'date': report['date']}, headers=HEADERS)
    except Exception as error:
        return failure(error)


ROUTES = (('/ops/speed/publish', publish, ('GET', 'POST')),
          ('/api/speed/reports', reports, ('GET',)))
