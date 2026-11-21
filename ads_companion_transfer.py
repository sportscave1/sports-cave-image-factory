"""Paired-desktop artifact receipts; the existing ad worker owns posting."""
import hashlib
import json
import re
import asyncio
import time
from threading import BoundedSemaphore

_BODY_SLOTS = BoundedSemaphore(2)
from uuid import UUID, uuid4

import design_publish_ad as ads

FILES = ('ad_copy.csv', *ads.COVERS.values())


def content_hash(data):
    return hashlib.sha256(b''.join(hashlib.sha256(data[i:i+4*1024**2]).digest()
        for i in range(0, len(data), 4*1024**2))).hexdigest()


def receive(token, job_id, name, chat_url, response_id, data):
    from product_upload_services import Dropbox
    from os_accounts import DEFAULT_STORE
    import ads_page
    import ads_image_workflow

    key = ads.PREFIX + str(UUID(job_id))
    if name not in FILES or not data or len(data) > (2 if name.endswith('.csv') else 20)*1024**2:
        raise ValueError('Invalid ad file name or size.')
    if not ads.CHAT.fullmatch(chat_url) or not re.fullmatch(r'[A-Za-z0-9_-]{1,160}', response_id):
        raise ValueError('The original ad response is required.')
    digest = content_hash(data)
    lease = str(uuid4())
    with ads.connect() as conn, conn.cursor() as cur:
        cur.execute('SELECT 1 FROM product_upload_desktop WHERE singleton AND token_hash=%s FOR UPDATE', (ads.digest(token),))
        if not cur.fetchone():
            raise PermissionError('The paired desktop credential is required.')
        cur.execute('SELECT value FROM app_settings WHERE key=%s', (key,))
        row = cur.fetchone()
        if not row:
            raise ValueError('Ad job not found.')
        value = row['value']
        user = DEFAULT_STORE.get_user(value['requester'])
        ads.check_request(user, value['sport'], value['country'])
        # A lost HTTP acknowledgement must not reconvert or reupload a verified file.
        receipt = (value.get('artifacts') or {}).get(name)
        if receipt and value.get('chat_url') == chat_url and (value.get('response_ids') or {}).get(name) == response_id:
            if receipt.get('hash') != digest or receipt.get('size') != len(data):
                raise ValueError('A different file already occupies this ad slot. Existing files were preserved.')
            if receipt.get('id') and receipt.get('rev'):
                return dict(received=name, ready=all(filename in value['artifacts'] for filename in FILES),
                            detail=progress(value), reused=True)
        if value['stage'] != 'generating' or value.get('posting_id'):
            raise ValueError('This job is not accepting creative files.')
        if value.get('chat_url') != chat_url or (value.get('response_ids') or {}).get(name, response_id) != response_id:
            raise ValueError('The file belongs to a different conversation or response.')
        cur.execute('''INSERT INTO app_settings(key,value,updated_at) VALUES (%s,%s::jsonb,now())
            ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value,updated_at=now()
            WHERE app_settings.updated_at < now()-interval '10 minutes' RETURNING key''',
            (ads.PREFIX+'lease', json.dumps(lease)))
        if not cur.fetchone():
            raise RuntimeError('The ad worker is busy; retry this same file.')
        cur.execute('SELECT value FROM app_settings WHERE key=%s', (key,))
        value = cur.fetchone()['value']
    try:
        from ads_companion_controls import stopped
        if stopped(job_id): raise ValueError('This ad job has been cancelled or deleted.')
        if value['stage'] != 'generating' or value.get('posting_id') or value.get('chat_url') != chat_url:
            raise ValueError('The ad checkpoint changed; refresh its import status.')
        if (value.get('response_ids') or {}).get(name, response_id) != response_id:
            raise ValueError('The file belongs to a different response.')
        if name.endswith('.csv'):
            ads_page.parse_instant_experience_copy_csv(data, value['result'])
        else:
            ads_image_workflow.inspect_instant_experience_original(data, original_name=name)
            record = ads_image_workflow.build_meta_posting_image_record(data, original_name=name)
            if not record['valid'] or record['source_format'] != 'JPEG':
                raise ValueError('Ad covers must be full-resolution JPEGs.')
        dbx = Dropbox()
        path = value['folder'] + '/' + name
        if not dbx.api.path_is_within_root(path, dbx.context['root_path']):
            raise ValueError('Ad destination is outside the Files root.')
        existing = dbx.metadata_if_present(path)
        if not existing:
            existing = dbx.api.upload_file(dbx.token, path, data)
        if (existing.get('path_display') != path or existing.get('content_hash') != digest
                or existing.get('size') != len(data) or not existing.get('id') or not existing.get('rev')):
            raise ValueError('A different file already occupies this ad slot. Existing files were preserved.')
        value.setdefault('artifacts', {})[name] = dict(id=existing['id'], rev=existing['rev'], hash=digest, size=len(data))
        value.setdefault('response_ids', {})[name] = response_id
        value['last_artifact_at'] = time.time()
        value['detail'] = progress(value)
        ads.write(key, value)
        return dict(received=name, ready=all(filename in value['artifacts'] for filename in FILES), detail=value['detail'])
    finally:
        with ads.connect() as conn, conn.cursor() as cur:
            cur.execute('DELETE FROM app_settings WHERE key=%s AND value=%s::jsonb', (ads.PREFIX+'lease', json.dumps(lease)))


def progress(value):
    received = value.get('artifacts') or {}
    return f"{sum(name in received for name in ads.COVERS.values())} of 3 images collected · CSV {'ready' if 'ad_copy.csv' in received else 'waiting'}"


def delivery(value):
    return dict(id=value['upload'], stage=value['stage'], receipt=ads._source_token(value['upload']),
                repair=value.get('attachment_repair'),
                recover=bool(value.get('collect_only')),resume_token=value.get('resume_token'),response_ids=value.get('response_ids') or {},
                chat_url=value.get('chat_url'),
                missing=[name for name in FILES if name not in (value.get('artifacts') or {})])


def resume(job_id, user, settings=None):
    from product_upload_staff_queue import can_control_queues
    if not can_control_queues(user):
        raise PermissionError('A companion administrator must resume an ad.')
    with ads.connect() as conn, conn.cursor() as cur:
        # Serialize with lease acquisition, then refuse changes while a transfer or
        # posting step is using its checkpoint outside the database transaction.
        cur.execute('SELECT 1 FROM product_upload_desktop WHERE singleton FOR UPDATE')
        cur.execute("SELECT 1 FROM app_settings WHERE key=%s AND updated_at > now()-interval '10 minutes'",
                    (ads.PREFIX+'lease',))
        if cur.fetchone():
            raise ValueError('The ad worker is still running. Retry Resume import shortly.')
        cur.execute('SELECT value FROM app_settings WHERE key=%s FOR UPDATE', (ads.PREFIX+str(UUID(job_id)),))
        row = cur.fetchone()
        if not row:
            raise ValueError('Ad job not found.')
        value = row['value']
        value.pop('catalog_retry', None)
        value.pop('auto_recovery', None)
        value.pop('resume_stage', None)
        if value.get('attachment_repair'):
            value.setdefault('attachment_repair_history', []).append(value.pop('attachment_repair'))
        if settings is not None:
            if value['stage'] != 'failed':
                raise ValueError('Targeting can be corrected after the job stops for review.')
            value['result']['posting_settings'] = settings
            value.pop('targeting', None)
        if value['stage'] not in ('failed', 'generating') or value.get('posting_id'):
            raise ValueError('Use the existing Posting receipt to recover a submitted ad.')
        if not value.get('folder') or not ads.CHAT.fullmatch(value.get('chat_url', '')):
            raise ValueError('The original ad conversation and prepared folder are required.')
        value.update(stage='generating', detail=progress(value), collect_only=True,resume_token=str(uuid4()))
        value.pop('timed_stage', None)
        value.pop('dependency_failed_at', None)
        value.update(generation_started_at=time.time(), last_chat_activity_at=time.time())
        value.pop('chat_finished_at', None)
        cur.execute('DELETE FROM app_settings WHERE key=%s',('ads_job_control:'+str(UUID(job_id)),))
        cur.execute('UPDATE app_settings SET value=%s::jsonb,updated_at=now() WHERE key=%s',
                    (json.dumps(value), ads.PREFIX+str(UUID(job_id))))


async def file_route(request):
    from product_upload_api import HEADERS, failure
    from starlette.concurrency import run_in_threadpool
    from starlette.responses import JSONResponse
    try:
        auth = request.headers.get('authorization', '')
        if not re.fullmatch(r'Bearer [A-Za-z0-9_-]{43}', auth):
            raise PermissionError('Desktop credential required.')
        q = request.query_params
        name = q.get('name', '')
        if name not in FILES: raise ValueError('Invalid ad file name.')
        limit = (2 if name.endswith('.csv') else 20)*1024**2
        declared = request.headers.get('content-length')
        if declared and (not declared.isdigit() or int(declared)>limit):
            raise ValueError('Ad file exceeds the transfer limit.')
        if not _BODY_SLOTS.acquire(blocking=False):
            raise ValueError('Ad transfer is busy. Retry the same file shortly.')
        try:
            async def body():
                data = bytearray()
                async for chunk in request.stream():
                    if len(data)+len(chunk)>limit: raise ValueError('Ad file exceeds the transfer limit.')
                    data.extend(chunk)
                return bytes(data)
            data = await asyncio.wait_for(body(), timeout=30)
            result = await run_in_threadpool(receive, auth[7:], q.get('job',''), name,
                q.get('chat',''), q.get('response',''), data)
        finally:
            _BODY_SLOTS.release()
        return JSONResponse(result, headers=HEADERS)
    except Exception as error:
        return failure(error)
