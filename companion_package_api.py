"""Host-authorised resumable preparation, on existing server and worker only."""
import asyncio
import hashlib
import json
import os
import re
import time
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
import auto_editions as ae
import auto_editions_api as api
import auto_editions_runtime as runtime
from companion_package_identity import CHUNK,validate
from companion_package_store import Sessions


def enabled():return os.getenv('COMPANION_RESUMABLE_UPLOADS_ENABLED','').lower()=='true'


def accepted():
    # Explicit release acceptance, separate from installing code/schema. Default
    # closed, including installations which prematurely enabled the old flag.
    from companion_package_identity import generation
    return (os.getenv('COMPANION_RESUMABLE_ACCEPTANCE','')=='provider-postgres-retention-v1'
        and os.getenv('COMPANION_RESUMABLE_ACCEPTANCE_GENERATION','')==generation()
        and re.fullmatch('[a-f0-9]{64}',os.getenv('COMPANION_RESUMABLE_ACCEPTANCE_EVIDENCE_SHA256','')) is not None)


def capability():return 1 if enabled() and runtime.enabled() and accepted() else 0


def service():
    from auto_editions_onboarding_api import queue
    from companion_package_provider import PackageProvider
    return Sessions(queue().connect,PackageProvider())


def private(store,key,owner,host):
    if not re.fullmatch('[a-f0-9]{64}',str(key)):raise ValueError('Exact upload session required.')
    with store.connect() as conn,conn.cursor() as cur:
        cur.execute('SELECT * FROM companion_package_uploads WHERE id=%s AND owner_id=%s AND host_hash=%s',(key,owner,host))
        row=cur.fetchone()
    if not row:raise PermissionError('Upload session is unavailable to this host.')
    return dict(row)


def current(row):
    """Fresh host/session, original lease, source revision and mapping gates."""
    from auto_editions_onboarding_api import queue,host_account,product_context
    ctx=row['context'];store=queue()
    validate(row['descriptor'],ctx)
    with store.connect() as conn,conn.cursor() as cur:
        cur.execute('SELECT * FROM auto_edition_preparation_hosts WHERE token_hash=%s AND revoked_at IS NULL AND expires_at>now()',(row['host_hash'],))
        host=cur.fetchone()
    if not host or str(host['actor_id'])!=row['owner_id']:raise PermissionError('Preparation host expired or changed.')
    host_account(host)
    completed=store.completed_receipt(ctx['product_gid'],ctx['lease_token'],row['owner_id'])
    if completed:
        if completed['preparation_hash']!=row['descriptor']['preparation_hash'] or completed['source']!=ctx['source']:
            raise ValueError('Completed preparation differs from the upload session.')
        assets=runtime.storage()
        meta=assets.integration.psd_open_metadata(assets.token,ctx['source']['file_id'],include_preview=False)
        if ae.source_identity(ctx['product_gid'],meta)!=ctx['source']:raise ValueError('Completed source revision changed.')
        status=store.imported_state(ctx['product_gid'],completed['preparation_hash'],ctx['source'])
        return dict(preparation_hash=completed['preparation_hash'],source=ctx['source'],status=status,print_ready=False,timings=completed.get('timings',{}))
    if product_context(ctx['product_gid'],ctx['lease_token'])!=ctx:raise ValueError('Source, edition run or current lease changed.')
    return None


async def host(request):
    entered=time.monotonic();body_seconds=None;durable_seconds=None
    try:
        if not enabled():raise ValueError('Resumable backend is disabled; retained sessions require a compatible backend.')
        from auto_editions_onboarding_api import preparation_actor
        if not request.headers.get('x-sports-cave-preparation-host'):raise PermissionError('Registered preparation host required.')
        user=await preparation_actor(request)
        if not runtime.enabled():raise ValueError('Existing durable processing worker must be enabled before resumable uploads.')
        host_hash=hashlib.sha256(request.headers['x-sports-cave-preparation-host'].encode()).hexdigest()
        action=request.path_params['upload_action']
        if action=='create' and not accepted():raise ValueError('Resumable production acceptance is incomplete; use the negotiated legacy route for new work.')
        owner=str(user['id']);store=await run_in_threadpool(service)
        received_size=None
        if action=='create':
            from auto_editions_setup_api import grant_context
            import files_upload_api as files
            setup=await run_in_threadpool(grant_context,request)
            if not setup['context'].get('automatic') or setup.get('host_token_hash')!=host_hash or setup['actor_id']!=owner:
                raise PermissionError('The exact host-owned product preparation grant is required.')
            descriptor=await files._json_body(request)
            correlation=request.headers.get('x-sc-transfer-id','')
            correlation=correlation if re.fullmatch('[a-f0-9]{32}',correlation) else None
            result=await run_in_threadpool(store.create,owner,host_hash,str(request.base_url).rstrip('/'),setup['context'],descriptor,correlation)
        else:
            key=request.query_params.get('id','')
            row=await run_in_threadpool(private,store,key,owner,host_hash)
            store.live(row)
            if row['shop_origin']!=str(request.base_url).rstrip('/'):raise PermissionError('Upload belongs to another application/shop origin.')
            completed=await run_in_threadpool(current,row)
            if completed:
                result={**store.public(row),'state':'Complete','result':completed}
            elif action=='status':result=await run_in_threadpool(store.status,key,owner,host_hash)
            elif action=='finalize':
                result=await run_in_threadpool(store.finalize,key,owner,host_hash)
                runtime._wake.set() # Durable row is already queued; wake is optional.
            elif action=='chunk':
                text=request.headers.get('x-sc-chunk-offset','')
                if not text.isdecimal() or len(text)>12:raise ValueError('Explicit chunk offset required.')
                length=request.headers.get('content-length','')
                if not length.isdecimal() or not 0<int(length)<=CHUNK:raise ValueError('Bounded chunk Content-Length required.')
                content=bytearray();started=time.monotonic();first_body=None
                async for block in request.stream():
                    if block and first_body is None:first_body=time.monotonic()
                    if len(content)+len(block)>int(length):raise ValueError('Chunk exceeds its declared length.')
                    content.extend(block)
                if len(content)!=int(length):raise ValueError('Incomplete chunk body.')
                body_seconds=time.monotonic()-(first_body or time.monotonic())
                received_size=len(content)
                started=time.monotonic()
                result=await run_in_threadpool(store.chunk,key,owner,host_hash,int(text),content,request.headers.get('x-sc-chunk-sha256',''))
                durable_seconds=time.monotonic()-started
            else:raise ValueError('Unsupported upload action.')
        headers=dict(api.HEADERS)
        correlation=request.headers.get('x-sc-transfer-id','')
        if re.fullmatch('[a-f0-9]{32}',correlation):headers['X-SC-Transfer-ID']=correlation
        if received_size is not None:headers['X-SC-Received-Bytes']=str(received_size)
        headers['X-SC-Handler-Seconds']=str(round(time.monotonic()-entered,6))
        if body_seconds is not None:headers['X-SC-Body-Receive-Seconds']=str(round(body_seconds,6))
        if durable_seconds is not None:headers['X-SC-Durable-Seconds']=str(round(durable_seconds,6))
        return JSONResponse(result,headers=headers)
    except Exception as error:return api.failure(error)


def process(row,archive):
    completed=current(row)
    if completed:return completed
    from auto_editions_setup_api import import_archive
    return asyncio.run(import_archive(archive,dict(context=row['context'],actor_id=row['owner_id']),
        lambda:current(row),time.monotonic(),dict(resumable_protocol=1,package_sha256=row['descriptor']['sha256'],correlation_id=row['data'].get('correlation_id')),
        expected=row['descriptor']['preparation_hash']))


def run_one():
    if not enabled():return False
    from auto_editions_setup_api import IMPORT_LOCK
    if not IMPORT_LOCK.acquire(blocking=False):return False
    try:
        store=service()
        result=store.run_one(process,recover=current)
        store.cleanup()
        return result
    finally:IMPORT_LOCK.release()


ROUTES=(('/api/auto-editions/uploads/{upload_action}',host,('POST',)),)
