"""Revocable, expiring capability for one exact retained production JPG.

No allocation, customer name, supplier credentials or editable file path in URL.
The current allocation and archive identity are checked on every request.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import secrets
import tempfile

from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from starlette.responses import FileResponse, Response

PREFIX = 'prodigi_artwork_cap:'
URL = 'https://sports-cave-image-factory.onrender.com/api/prodigi-artwork/'
HEADERS = {'Cache-Control': 'private, no-store', 'Referrer-Policy': 'no-referrer',
           'X-Content-Type-Options': 'nosniff', 'X-Robots-Tag': 'noindex, nofollow'}


def issue(snapshot):
    from prodigi_preparation import connect
    token = secrets.token_urlsafe(32)
    value = dict(allocation_id=snapshot['allocation_id'], job_id=snapshot['job_id'], output=snapshot['output'],
                 expires_at=(datetime.now(timezone.utc) + timedelta(days=30)).isoformat())
    with connect() as conn, conn.cursor() as cur:
        cur.execute('INSERT INTO app_settings(key,value,updated_at) VALUES(%s,%s::jsonb,now())',
                    (PREFIX + hashlib.sha256(token.encode()).hexdigest(), json.dumps(value)))
    return URL + token


def bound(token):
    if not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
        raise ValueError('Unavailable')
    from prodigi_preparation import connect
    from auto_editions_jobs import Jobs
    from auto_editions_api import same_allocation
    with connect() as conn, conn.cursor() as cur:
        cur.execute('SELECT value FROM app_settings WHERE key=%s', (PREFIX + hashlib.sha256(token.encode()).hexdigest(),))
        found = cur.fetchone()
    if not found:
        raise ValueError('Unavailable')
    value = found['value']
    if datetime.fromisoformat(value['expires_at']) <= datetime.now(timezone.utc):
        raise ValueError('Unavailable')
    record, unit = Jobs(connect).read_bound(value['job_id'], value['allocation_id'])
    if (not record or record['status'] != 'Ready' or not same_allocation(unit, record['payload']['identity'])
            or record['result'].get('test_only') is not False or record['result'].get('retained') is not True
            or record['result']['output'] != value['output']):
        raise ValueError('Unavailable')
    return value


def fetch(value, folder):
    import auto_editions_runtime
    assets = auto_editions_runtime.storage()
    output = value['output']
    if not 0 < output['bytes'] <= 128 * 1024 * 1024:
        raise ValueError('Unavailable')
    assets.verify_output(output)
    from auto_editions_asset_cache import output_assets
    path = Path(folder) / 'artwork.jpg'
    if output_assets.copy(output['sha256'], path):
        if path.stat().st_size != output['bytes']:
            raise ValueError('Unavailable')
        return path
    _, source = assets.output_response(output)
    sha, count = hashlib.sha256(), 0
    try:
        with path.open('wb') as target:
            for chunk in source.iter_content(1024 * 1024):
                count += len(chunk)
                if count > output['bytes']:
                    raise ValueError('Unavailable')
                sha.update(chunk)
                target.write(chunk)
    finally:
        source.close()
    if count != output['bytes'] or sha.hexdigest() != output['sha256']:
        raise ValueError('Unavailable')
    try:
        output_assets.remember(output['sha256'], path)
    except OSError:
        pass
    return path


async def serve(request):
    folder = None
    try:
        value = await run_in_threadpool(bound, request.path_params['token'])
        if request.method == 'HEAD':
            return Response(headers={**HEADERS, 'Content-Type': 'image/jpeg', 'Content-Length': str(value['output']['bytes'])})
        folder = tempfile.TemporaryDirectory(prefix='sc-prodigi-artwork-')
        path = await run_in_threadpool(fetch, value, folder.name)
        await run_in_threadpool(bound, request.path_params['token'])
        return FileResponse(path, media_type='image/jpeg', filename='artwork.jpg', content_disposition_type='inline',
                            headers=HEADERS, background=BackgroundTask(folder.cleanup))
    except Exception:
        if folder:
            folder.cleanup()
        return Response(status_code=404, headers=HEADERS)
