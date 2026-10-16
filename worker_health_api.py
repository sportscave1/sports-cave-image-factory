"""Administrator-only Worker Health on the existing server; no provider I/O."""
from pathlib import Path
from starlette.concurrency import run_in_threadpool
from starlette.responses import HTMLResponse,JSONResponse
import worker_health

HEADERS={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff','X-Frame-Options':'SAMEORIGIN','Referrer-Policy':'no-referrer'}


async def actor(request,write=False):
    import files_upload_api as files,os_accounts
    if write and (not request.headers.get('origin') or not files._same_origin(request)):raise PermissionError('Request origin rejected.')
    user=await run_in_threadpool(files._request_user,request)
    if not os_accounts.account_is_active(user) or not os_accounts.is_admin(user):raise PermissionError('Worker Health requires an authorised administrator.')
    return user


def store():
    import supabase_backend
    return worker_health.Health(supabase_backend.connect)


def failure(error):
    import uuid,logging
    if getattr(error,'sqlstate',None) in ('55P03','57014'):
        return JSONResponse(dict(error='The queue is busy with another operation. Wait briefly and retry the same request; no duplicate job will be created.'),status_code=503,headers=HEADERS)
    known=isinstance(error,(PermissionError,ValueError))
    trace='WH-'+uuid.uuid4().hex[:12]
    if not known:logging.getLogger(__name__).warning('worker_health_unavailable trace=%s error_type=%s',trace,type(error).__name__)
    return JSONResponse(dict(error=str(error) if known else 'Authoritative worker status unavailable.',trace=trace),
        status_code=403 if isinstance(error,PermissionError) else 409 if known else 503,headers=HEADERS)


async def page(request):
    try:
        await actor(request)
        return HTMLResponse((Path(__file__).parent/'components/worker_health/index.html').read_text(encoding='utf-8'),headers=HEADERS)
    except Exception as error:return failure(error)


async def snapshot(request):
    try:
        await actor(request)
        category=request.query_params.get('filter','All')
        if category not in ('All','Active','Queued','Failed','Needs Review','Completed'):raise ValueError('Invalid job filter.')
        offset=max(0,min(1000,int(request.query_params.get('offset','0'))))
        from worker_health_cache import snapshot as cached_snapshot
        data=await run_in_threadpool(cached_snapshot,store())
        jobs=data.pop('jobs');data['filters']={name:len([j for j in jobs if name=='All' or j['category']==name]) for name in ('All','Active','Queued','Failed','Needs Review','Completed')}
        if category!='All':jobs=[j for j in jobs if j['category']==category]
        data.update(jobs=jobs[offset:offset+25],offset=offset,total_rows=len(jobs),page_size=25)
        return JSONResponse(data,headers=HEADERS)
    except Exception as error:return failure(error)


async def pause(request):
    try:
        import files_upload_api as files
        user=await actor(request,write=True);body=await files._json_body(request)
        if not isinstance(body,dict) or set(body)!={'paused'} or type(body['paused']) is not bool:raise ValueError('Choose Pause or Resume.')
        from worker_health_cache import invalidate
        service=store();invalidate(service.connect)
        try:result=await run_in_threadpool(worker_health.set_pause,service.connect,body['paused'],str(user['id']))
        finally:invalidate(service.connect)
        return JSONResponse(result,headers=HEADERS)
    except Exception as error:return failure(error)


async def logs(request):
    try:
        await actor(request)
        args={k:request.query_params.get(k,'') for k in ('severity','component','design','date_from','date_to','search')}
        args['cursor']=max(0,int(request.query_params.get('cursor','0')))
        if len(args['search'])>120:raise ValueError('Diagnostic search is limited to 120 characters.')
        return JSONResponse(await run_in_threadpool(store().logs,**args),headers=HEADERS)
    except Exception as error:return failure(error)


async def jobs(request):
    try:
        await actor(request)
        import worker_health_queue as queue
        return JSONResponse(await run_in_threadpool(queue.page,store(),request.query_params.get('filter','All'),request.query_params.get('cursor','')),headers=HEADERS)
    except Exception as error:return failure(error)


async def updates(request):
    try:
        await actor(request)
        import worker_health_queue as queue,files_upload_api as files
        body=await files._json_body(request)
        if not isinstance(body,dict) or set(body)!={'filter','known','scanned_to'}:raise ValueError('Current filter and loaded job versions required.')
        return JSONResponse(await run_in_threadpool(queue.changes,store(),body['filter'],body['known'],body['scanned_to']),headers=HEADERS)
    except Exception as error:return failure(error)


async def search(request):
    try:
        await actor(request)
        import worker_health_queue as queue
        return JSONResponse(await run_in_threadpool(queue.search,store().connect,request.query_params.get('q','')),headers=HEADERS)
    except Exception as error:return failure(error)


async def enqueue(request):
    try:
        user=await actor(request,write=True)
        import worker_health_queue as queue,files_upload_api as files
        body=await files._json_body(request)
        if not isinstance(body,dict) or set(body)!={'product_gid','request_id','repair_confirmed'}:raise ValueError('Choose one mapped design and confirm any required repair.')
        from worker_health_cache import invalidate
        service=store();invalidate(service.connect)
        try:result=await run_in_threadpool(queue.submit,service.connect,body['product_gid'],str(user['id']),body['request_id'],body['repair_confirmed'])
        finally:invalidate(service.connect)
        return JSONResponse(result,status_code=202,headers=HEADERS)
    except Exception as error:return failure(error)


async def details(request):
    try:
        await actor(request)
        import worker_health_queue as queue
        return JSONResponse(await run_in_threadpool(queue.details,store().connect,request.query_params.get('product_gid')),headers=HEADERS)
    except Exception as error:return failure(error)


ROUTES=(('/worker-health',page,('GET',)),('/api/worker-health',snapshot,('GET',)),
        ('/api/worker-health/control',pause,('POST',)),('/api/worker-health/diagnostics',logs,('GET',)),
        ('/api/worker-health/jobs',jobs,('GET',)),('/api/worker-health/updates',updates,('POST',)),
        ('/api/worker-health/search',search,('GET',)),('/api/worker-health/enqueue',enqueue,('POST',)),('/api/worker-health/details',details,('GET',)))
