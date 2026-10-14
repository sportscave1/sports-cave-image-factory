"""Cookie-authenticated cloud downloads. No companion or allocation mutations."""
import json
from pathlib import Path
import tempfile

from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from starlette.responses import HTMLResponse,JSONResponse,FileResponse
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
        job,assets,row=await current(request)
        if row['status']!='Ready':raise ValueError('The JPG is not ready yet.')
        result=row['result'];output=result['output']
        folder=tempfile.TemporaryDirectory(prefix='sc-edition-download-')
        path=Path(folder.name)/'output.jpg'
        def fetch():
            metadata,response=assets.integration.get_file_response(assets.token,assets.path(job['id'],'output.jpg',cache=True))
            try:
                if (metadata.get('id')!=output['file_id'] or metadata.get('rev')!=output['revision']
                        or metadata.get('size')!=output['bytes'] or not 0<output['bytes']<=32*1024*1024):
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
        await current(request)
        return FileResponse(path,media_type='image/jpeg',filename=result['filename'],headers=HEADERS,
                            background=BackgroundTask(folder.cleanup))
    except Exception as error:
        if folder:folder.cleanup()
        return failure(error)


ROUTES=(('/auto-editions/download',page,('GET',)),('/api/auto-editions/start',start,('POST',)),
        ('/api/auto-editions/status',status,('GET',)),('/api/auto-editions/file',download,('GET',)))
