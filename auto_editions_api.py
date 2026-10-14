"""Cookie-authenticated cloud downloads. No companion or allocation mutations."""
import json
import re
from pathlib import Path
import tempfile

from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from starlette.responses import HTMLResponse,JSONResponse,FileResponse,RedirectResponse
import auto_editions as ae
import auto_editions_cloud as cloud
import auto_editions_runtime as runtime

HEADERS={'Cache-Control':'private, no-store','Referrer-Policy':'no-referrer',
         'X-Content-Type-Options':'nosniff','X-Frame-Options':'SAMEORIGIN'}


async def actor(request,*,setup=False,write=False):
    import files_upload_api as files
    if not runtime.enabled():raise cloud.PreparationBlocked('Cloud editions are not enabled.')
    if write and (not request.headers.get('origin') or not files._same_origin(request)):
        raise PermissionError('Request origin rejected.')
    user=await run_in_threadpool(files._request_user,request)
    cloud.require_access(user,setup=setup)
    return user


def failure(error):
    known=isinstance(error,(ValueError,PermissionError))
    return JSONResponse({'ok':False,'error':str(error) if known else 'Auto Editions is temporarily unavailable. Retry shortly.'},
                        status_code=403 if isinstance(error,PermissionError) else 409 if known else 503,headers=HEADERS)


def allocation(request):
    value=request.query_params.get('allocation_id','')
    if not value.isdigit() or int(value)<=0:raise ValueError('Open an allocated order unit from Orders.')
    return int(value)


async def page(request):
    try:
        await actor(request);allocation(request)
        return HTMLResponse((Path(__file__).parent/'components/auto_editions/download.html').read_text(),headers=HEADERS)
    except Exception as error:return failure(error)


async def start(request):
    try:
        import files_upload_api as files
        user=await actor(request,write=True)
        if await files._json_body(request)!={}:raise ValueError('Edition numbers are read from the saved allocation.')
        job,_=await run_in_threadpool(runtime.job_for,allocation(request))
        _,jobs=runtime.stores()
        row=await run_in_threadpool(jobs.enqueue,job,str(user['id']))
        runtime.start_worker()
        return JSONResponse({'ok':True,'job_id':row['id'],'status':row['status'],'test_only':True},headers=HEADERS)
    except Exception as error:return failure(error)


async def current(request):
    await actor(request)
    job,assets=await run_in_threadpool(runtime.job_for,allocation(request))
    if request.query_params.get('job_id')!=job['id']:raise ValueError('Allocation or artwork changed. Generate again.')
    _,jobs=runtime.stores()
    row=await run_in_threadpool(jobs.read,job['id'])
    if not row:raise ValueError('Generation request is unavailable.')
    return job,assets,row


async def status(request):
    try:
        _,_,row=await current(request)
        runtime.start_worker()
        return JSONResponse({'ok':True,'status':row['status'],'error_code':row['error_code'],
                             'filename':row['result']['filename'] if row['status']=='Ready' else None,
                             'test_only':True},headers=HEADERS)
    except Exception as error:return failure(error)


async def download(request):
    folder=None
    try:
        job,assets,row=await stored_current(request)
        if row['status']!='Ready':raise ValueError('The JPG is not ready yet.')
        user=await actor(request)
        _,jobs=runtime.stores()
        await run_in_threadpool(jobs.retain,job['id'],str(user['id']))
        result=row['result'];output=result['output']
        folder=tempfile.TemporaryDirectory(prefix='sc-edition-download-')
        path=Path(folder.name)/'output.jpg'
        def fetch():
            metadata,response=assets.output_response(output)
            try:
                if (metadata.get('id')!=output['file_id'] or metadata.get('rev')!=output['revision']
                        or metadata.get('size')!=output['bytes'] or not 0<output['bytes']<=cloud.MAX_OUTPUT_BYTES):
                    raise ValueError('Cached output changed; download blocked.')
                count=0
                with path.open('wb') as target:
                    for block in response.iter_content(chunk_size=1024*1024):
                        count+=len(block)
                        if count>output['bytes']:raise ValueError('Cached output exceeded its verified size.')
                        target.write(block)
                if count!=output['bytes'] or ae.file_hash(path)!=output['sha256']:
                    raise ValueError('Cached output checksum failed.')
            finally:response.close()
        await run_in_threadpool(fetch)
        # Permissions/source are rechecked after the potentially slow transfer.
        await stored_current(request)
        return FileResponse(path,media_type='image/jpeg',filename=result['filename'],content_disposition_type='inline' if request.query_params.get('inline')=='1' else 'attachment',headers=HEADERS,
                            background=BackgroundTask(folder.cleanup))
    except Exception as error:
        if folder:folder.cleanup()
        return failure(error)



def same_allocation(unit,identity):
    return (unit.get('allocation_valid') is True and unit.get('identity_enforced') is True
        and not unit.get('invalidated_at') and not unit.get('cancelled_at')
        and not unit.get('duplicate_allocation_warning')
        and unit.get('status') in ('assigned','completed','fulfilled')
        and (unit.get('allocation_index') or unit.get('unit_ordinal'))==identity.get('ordinal')
        and unit.get('id')==identity.get('allocation_id')
        and unit.get('shopify_order_id')==identity.get('order_id')
        and unit.get('shopify_line_item_id')==identity.get('line_id')
        and unit.get('edition_number')==identity.get('number')
        and unit.get('edition_total')==identity.get('total')
        and str(unit.get('shopify_variant_id') or '')==identity.get('variant_id')
        and unit.get('shopify_product_gid')==identity.get('source',{}).get('product_gid'))


async def stored_current(request):
    # Retained historical output is bound to its exact allocation, not today's PSD.
    await actor(request)
    if not re.fullmatch(r'[a-f0-9]{64}',request.query_params.get('job_id','')):raise ValueError('Invalid saved artwork identity.')
    registry,jobs=runtime.stores()
    row=await run_in_threadpool(jobs.read,request.query_params.get('job_id',''))
    if row and (row.get('result') or {}).get('retained') is True:
        unit,_=await run_in_threadpool(registry.unit,allocation(request))
        if not same_allocation(unit,row['payload']['identity']):raise PermissionError('Artwork does not match this allocation.')
        return row['payload'],runtime.storage(),row
    return await current(request)


async def state(request):
    try:
        await actor(request)
        job,assets=await run_in_threadpool(runtime.job_for,allocation(request))
        _,jobs=runtime.stores();row=await run_in_threadpool(jobs.read,job['id'])
        if row and row['status']=='Ready':
            await run_in_threadpool(assets.verify_output,row['result']['output'])
        runtime.start_worker()
        return JSONResponse(dict(ok=True,job_id=job['id'],status=row['status'] if row else 'Not generated',
            error_code=row.get('error_code') if row else None,filename=(row.get('result') or {}).get('filename') if row else None),headers=HEADERS)
    except Exception as error:return failure(error)


async def retry(request):
    try:
        user=await actor(request,write=True)
        job,_=await run_in_threadpool(runtime.job_for,allocation(request))
        _,jobs=runtime.stores();row=await run_in_threadpool(jobs.read,job['id'])
        if row and row['status']=='Blocked' and row['error_code']=='worker_unavailable':
            await run_in_threadpool(jobs.retry,job['id'],str(user['id']))
        elif row and row['status']=='Blocked' and row['error_code']=='cache_expired':
            await run_in_threadpool(jobs.enqueue,job,str(user['id']))
        else:raise ValueError('This file needs artwork review before retrying.')
        runtime.start_worker()
        return JSONResponse(dict(ok=True,job_id=job['id'],status='Queued'),headers=HEADERS)
    except Exception as error:return failure(error)


async def location(request):
    try:
        job,assets,row=await stored_current(request)
        if row['status']!='Ready':raise ValueError('The saved JPG is not ready. Return to Orders and retry.')
        metadata=await run_in_threadpool(assets.verify_output,row['result']['output'])
        path=metadata.get('path_display') or metadata['path_lower']
        return JSONResponse(dict(ok=True,file_id=metadata['id'],revision=metadata['rev'],path=path,
            folder_path=path.rsplit('/',1)[0],filename=metadata.get('name') or path.rsplit('/',1)[-1],
            test_only=True),headers=HEADERS)
    except Exception as error:return failure(error)


async def view(request):
    # Old bookmarked View URLs now resolve the saved location, never a preview.
    try:
        await actor(request)
        allocation(request)
    except Exception as error:return failure(error)
    from urllib.parse import urlencode
    return RedirectResponse('/?page=orders&workspace=files&'+urlencode(dict(edition_allocation=allocation(request),
        edition_job=request.query_params['job_id'])),headers=HEADERS)


ROUTES=(('/auto-editions/download',page,('GET',)),('/api/auto-editions/start',start,('POST',)),
        ('/api/auto-editions/status',status,('GET',)),('/api/auto-editions/file',download,('GET',)),('/api/auto-editions/state',state,('GET',)),('/api/auto-editions/retry',retry,('POST',)),('/auto-editions/view',view,('GET',)),('/auto-editions/open',view,('GET',)),('/api/auto-editions/location',location,('GET',)))
