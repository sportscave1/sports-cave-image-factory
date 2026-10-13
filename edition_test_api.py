"""Existing Files auth/Dropbox transfer, restricted to one read-only edition test."""
import hmac
from pathlib import Path
from starlette.concurrency import run_in_threadpool
from starlette.responses import HTMLResponse,JSONResponse
import edition_test as case


async def page(request):
    import files_upload_api as files
    try:
        user=await run_in_threadpool(files._request_user,request)
        if not files.os_accounts.can_access_page(user,'Orders'):raise ValueError('Orders and Files access are required for this test.')
        return HTMLResponse((Path(__file__).parent/'components/edition_test/index.html').read_text(encoding='utf-8'),headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer','X-Frame-Options':'SAMEORIGIN'})
    except Exception as error:return files._psd_error_page(str(error),status=403,title='Download JPG')


async def prepare(request):
    import files_upload_api as files
    try:
        if not request.headers.get('origin') or not files._same_origin(request):raise ValueError('Request origin rejected.')
        user=await run_in_threadpool(files._request_user,request)
        if not files.os_accounts.can_access_page(user,'Orders'):raise ValueError('Orders and Files access are required for this test.')
        if await files._json_body(request)!={}:raise ValueError('Only the verified test unit is enabled.')
        unit=await run_in_threadpool(case.confirmed_unit)
        auth=await run_in_threadpool(files._dropbox_context)
        meta=await run_in_threadpool(files.dropbox_integration.psd_open_metadata,auth['access_token'],case.FILE,include_preview=False)
        case.validate_context({'unit':unit,'metadata':meta})
        transfer=files.NATIVE_TRANSFER_MANAGER.create_psd(access_token=auth['access_token'],root_path=auth['root_path'],user=user,metadata=meta)
        transfer.edition_test_actor=dict(id=user['id'],session_version=user.get('session_version'))
        transfer.edition_test_claimed=False
        return JSONResponse({'ok':True,'grant':{'base_url':str(request.base_url).rstrip('/'),'ticket':transfer.ticket,'secret':transfer.secret}},headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})
    except Exception as error:return files._response_error(files.FilesUploadError(str(error) if isinstance(error,(ValueError,files.FilesUploadError)) else 'Test verification is unavailable. Retry or contact the administrator.',code='edition_test_blocked',status_code=403))


async def context(request):
    import files_upload_api as files
    try:
        manager=files.NATIVE_TRANSFER_MANAGER
        with manager._lock:
            record=manager.get(request.query_params.get('ticket'),files._native_transfer_secret(request))
            actor=getattr(record,'edition_test_actor',None)
            verify=request.query_params.get('verify')=='1'
            if not actor or (record.edition_test_claimed and not verify) or (verify and not record.edition_test_claimed):raise ValueError('Edition test grant expired or already used.')
            if actor['id']!='legacy-master-admin':
                current=files.os_accounts.DEFAULT_STORE.get_user(actor['id'])
                if not current or str(current.get('session_version'))!=str(actor['session_version']) or not all(files.os_accounts.can_access_page(current,p) for p in ('Files','Orders')):raise ValueError('Files/Orders permission or session changed.')
            record.edition_test_claimed=True
        unit=await run_in_threadpool(case.confirmed_unit)
        meta=await run_in_threadpool(files.dropbox_integration.psd_open_metadata,record.access_token,case.FILE,include_preview=False)
        data=case.validate_context({'unit':unit,'metadata':{k:meta[k] for k in ('id','rev','content_hash','size','name')},'actor_id':actor['id']})
        return JSONResponse(data,headers={'Cache-Control':'no-store'})
    except Exception as error:return files._response_error(files.FilesUploadError(str(error) if isinstance(error,(ValueError,files.FilesUploadError)) else 'Test verification is unavailable. Retry or contact the administrator.',code='edition_test_blocked',status_code=403))


ROUTES=(('/edition-jpg-download',page,('GET',)),('/edition-jpg-test',page,('GET',)),('/api/edition-jpg-test/prepare',prepare,('POST',)),('/api/edition-jpg-test/context',context,('GET',)))
