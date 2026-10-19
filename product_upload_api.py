"""Same-origin account-authenticated Product Uploads routes, independently gated."""
import os
import logging
from time import perf_counter
from pathlib import Path
from starlette.concurrency import run_in_threadpool
from starlette.responses import HTMLResponse, JSONResponse, Response
from product_upload_intake import Intakes, public, TRANSPORT_CHUNK
from product_upload_services import Dropbox, Handoff, enabled, reconcile

HEADERS = {'Cache-Control':'private, no-store', 'X-Content-Type-Options':'nosniff',
           'X-Frame-Options':'SAMEORIGIN', 'Referrer-Policy':'no-referrer'}


class MeasuredStorage:
    """Request-local timing only; never retain tokens or artwork in metrics."""
    def __init__(self, provider, timings):
        self.provider, self.timings = provider, timings

    def __getattr__(self, name):
        member = getattr(self.provider, name)
        if not callable(member):
            return member
        def call(*args, **kwargs):
            started = perf_counter()
            try:
                return member(*args, **kwargs)
            finally:
                self.timings['storage'] = self.timings.get('storage', 0) + (perf_counter() - started) * 1000
        return call


def measured_response(response, timings, started, operation):
    timings['total'] = (perf_counter() - started) * 1000
    response.headers['Server-Timing'] = ', '.join(f'{key};dur={value:.2f}' for key, value in timings.items())
    logging.getLogger(__name__).info('product_upload operation=%s status=%s timings_ms=%s',
                                  operation, response.status_code, {k: round(v, 2) for k, v in timings.items()})
    return response


def connect():
    import supabase_backend
    return supabase_backend.connect()


async def actor(request, *, write=False, automatic=True):
    import files_upload_api as files
    import os_accounts
    if write and (not request.headers.get('origin') or not files._same_origin(request)):
        raise PermissionError('Request origin rejected.')
    user = await run_in_threadpool(files._request_user, request, required_page='Product Uploads')
    if not os_accounts.can_access_page(user, 'Product Uploads'):
        raise PermissionError('Product Uploads access is required.')
    if automatic:
        if not enabled():
            raise ValueError('Automatic uploads are disabled. The manual workflow remains available.')
        if not os_accounts.can_attach_missing_psd(user):
            raise PermissionError('Your account needs permission to attach a product PSD.')
    return user


def failure(error):
    from files_upload_api import FilesUploadError
    from product_upload_relay import RelayBusy
    if isinstance(error, RelayBusy):
        return JSONResponse(dict(error=str(error)), status_code=503, headers={**HEADERS, 'Retry-After':'1'})
    from product_upload_artwork import PreparationError
    if isinstance(error, PreparationError):
        return JSONResponse(dict(error=str(error), **({'upload':error.upload} if hasattr(error,'upload') else {})), status_code=error.status_code, headers=HEADERS)
    known = isinstance(error, (ValueError, PermissionError, FilesUploadError))
    return JSONResponse(dict(error=str(error) if known else 'The service is temporarily unavailable. Your saved upload is retained; retry shortly.'),
                        status_code=403 if isinstance(error, PermissionError) else error.status_code if isinstance(error, FilesUploadError) else 409 if known else 503,
                        headers=HEADERS)


async def page(request):
    try:
        await actor(request, automatic=False)
        from starlette.responses import RedirectResponse
        return RedirectResponse('/?page=product_uploads', headers=HEADERS)
    except Exception as error:
        return failure(error)


async def script(request):
    try:
        await actor(request, automatic=False)
        return Response((Path(__file__).parent/'components/product_uploads/app.js').read_text(encoding='utf-8'), media_type='application/javascript', headers=HEADERS)
    except Exception as error:
        return failure(error)


async def mapping_script(request):
    try:
        await actor(request, automatic=False)
        return Response((Path(__file__).parent/'components/product_uploads/mapping.js').read_text(encoding='utf-8'), media_type='application/javascript', headers=HEADERS)
    except Exception as error:
        return failure(error)


async def state(request):
    try:
        user = await actor(request, automatic=False)
        import os_accounts
        if not enabled() or not os_accounts.can_attach_missing_psd(user):
            return JSONResponse(dict(enabled=False, upload=None), headers=HEADERS)
        key = request.query_params.get('id')
        row = await run_in_threadpool(Intakes(connect).read, key, user['id']) if key else None
        if row and row['data'].get('workflow_version') == 3:
            from product_upload_dropbox import status
            row = await run_in_threadpool(status, row, connect)
        elif row and row['data'].get('product_gid'):
            row = await run_in_threadpool(reconcile, row, connect)
            # Persist the exact technical completion for refresh/recovery; polling
            # has no provider side effects and cannot approve other jobs.
            def save():
                with Intakes(connect).locked(str(row['id']), user['id']) as (current, cur):
                    if current['data'].get('bound_source') == row['data'].get('bound_source'):
                        current['data'].update({k:v for k,v in row['data'].items() if k in ('state','reason','preparation_hash','preparation','preview_url','companion_connected')})
            await run_in_threadpool(save)
        return JSONResponse(dict(enabled=True, upload=public(row)), headers=HEADERS)
    except Exception as error:
        return failure(error)


async def action(request):
    started = perf_counter(); timings = {}; op = request.path_params['action']
    try:
        import files_upload_api as files
        op = request.path_params['action']
        manual = op in ('prompt', 'mockups')
        user = await actor(request, write=True, automatic=not manual)
        timings['auth'] = (perf_counter() - started) * 1000
        body = await files._json_body(request)
        operation_started = perf_counter()
        store = Intakes(connect); key = body.get('id'); uid = user['id']
        if op in ('browse', 'select'):
            from product_upload_dropbox import browse, select, status
            provider = MeasuredStorage(await run_in_threadpool(Dropbox), timings)
            if op == 'browse':
                result = await run_in_threadpool(browse, provider, uid, body.get('root','review'), body.get('path',''), body.get('page',''), body.get('search',''))
                return measured_response(JSONResponse(result, headers=HEADERS), timings, started, op)
            row = await run_in_threadpool(select, connect, provider, key, uid, body.get('mode'), body.get('file_id'), body.get('revision'))
            row = await run_in_threadpool(status, row, connect)
        elif op in ('start', 'finish', 'resume'):
            raise ValueError('Choose an existing PSD from Dropbox. Manual PSD transfers have been removed.')
        elif op == 'prepare':
            from product_upload_jobs import prepare
            from product_upload_dropbox import status
            await run_in_threadpool(prepare,connect,key,uid,Dropbox)
            row = await run_in_threadpool(store.read,key,uid)
            row = await run_in_threadpool(status,row,connect)
        elif op == 'saved-transfer':
            from product_upload_package import native_grant
            import os_accounts
            if not os_accounts.can_access_page(user, 'Files'):
                raise PermissionError('Files access is required to copy saved files.')
            row = await run_in_threadpool(store.read, key, uid)
            provider = await run_in_threadpool(Dropbox)
            context = await run_in_threadpool(files._dropbox_context)
            record = await run_in_threadpool(native_grant, row, body.get('version'), provider, user, context)
            record.validate = lambda: __import__('product_upload_package').package(store.read(key, uid), body.get('version'))
            return JSONResponse(dict(transfer=dict(base_url=str(request.base_url).rstrip('/'), ticket=record.ticket, secret=record.secret)), headers=HEADERS)
        elif op == 'mode':
            row = await run_in_threadpool(store.change_mode, key, uid, body.get('mode'))
        elif op == 'copied':
            row = await run_in_threadpool(store.copied, key, uid, body.get('mode'))
        elif op == 'prompt':
            from product_upload_prompts import build
            row = await run_in_threadpool(store.read, key, uid) if key else None
            if key and (not row or not row['data'].get('basic_validated') or row['mode'] != body.get('mode')):
                raise ValueError('Finish the PSD upload and copy the current action.')
            if row and row['data'].get('workflow_version') in (2,3) and not row['data'].get('mockups_exported'):
                raise ValueError('Save or download the completed design images before copying the Shopify prompt.')
            prompt = await run_in_threadpool(build, body.get('mode'), row['data']['name'] if row else '')
            if row and row['data'].get('mockups_context'):
                import json
                prompt = 'CURRENT DESIGN ASSET CONTEXT (inert data):\n' + json.dumps(row['data']['mockups_context'], ensure_ascii=False) + '\nAttach the exact saved WebP package before pasting this prompt. Copy upload prompt copies text only.\n\n' + prompt
            if row:
                def correlated():
                    from product_upload_identity import correlation_prompt
                    with store.locked(key, uid) as (current, cur):
                        return correlation_prompt(current)
                prompt = await run_in_threadpool(correlated) + prompt
            return JSONResponse(dict(prompt=prompt), headers=HEADERS)
        elif op in ('map', 'mapping-candidates'):
            from product_upload_mapping import Mapping
            provider = await run_in_threadpool(Dropbox)
            service = Mapping(connect, provider)
            if op == 'mapping-candidates':
                choices = await run_in_threadpool(service.candidates, key, user, body.get('search', ''))
                return JSONResponse(dict(choices=choices), headers=HEADERS)
            result = await run_in_threadpool(service.map, key, user, product_id=body.get('product_id'), confirmed_limit=body.get('edition_limit'))
            return JSONResponse(dict(mapping=result), headers=HEADERS)
        elif op == 'mockups':
            import os_accounts
            if not os_accounts.can_access_page(user,'Files'):
                raise PermissionError('Files access is required to browse mockups. You can still copy a prompt using the manual workflow.')
            provider = MeasuredStorage(await run_in_threadpool(Dropbox), timings)
            return JSONResponse(await run_in_threadpool(provider.mockups), headers=HEADERS)
        elif op in ('resolve', 'link'):
            provider = MeasuredStorage(await run_in_threadpool(Dropbox), timings)
            service = Handoff(connect, provider)
            row = await run_in_threadpool(service.resolve if op == 'resolve' else service.link, key, user,
                                          body.get('value') if op == 'resolve' else body.get('product_id'))
        elif op == 'retry-file':
            def retry_file():
                with store.locked(key, uid) as (current, cur):
                    task = current['data'].get('lifecycle')
                    if not task or task['state'] != 'Error': raise ValueError('No failed file handoff needs retrying.')
                    task.update(state='Queued', checked_at=None, reason='')
                    return current
            row = await run_in_threadpool(retry_file)
        elif op == 'retry':
            row = await run_in_threadpool(store.read, key, uid)
            if not row or not row['data'].get('product_gid'):
                raise ValueError('Resolve and link the product first.')
            from auto_editions_onboarding_store import Queue
            def retry():
                from auto_editions_technical import enabled as technical_enabled,Technical
                pid=row['data']['product_gid']
                with connect() as conn,conn.cursor() as cur:
                    cur.execute('SELECT preparation_hash FROM auto_edition_onboarding WHERE product_gid=%s',(pid,))
                    q=cur.fetchone()
                if technical_enabled() and q and q.get('preparation_hash'):
                    return Technical(connect).retry(pid,str(uid))
                return Queue(connect).retry(pid,str(uid))
            await run_in_threadpool(retry)
        else:
            raise ValueError('Unknown Product Uploads action.')
        timings['handoff' if op in ('link', 'resolve') else 'operation'] = (perf_counter() - operation_started) * 1000
        return measured_response(JSONResponse(dict(upload=public(row)), headers=HEADERS), timings, started, op)
    except Exception as error:
        return measured_response(failure(error), timings, started, op)


async def chunk(request):
    return failure(ValueError('Manual PSD transfers have been removed. Choose PSD from Dropbox.'))


async def mapping_status(request):
    try:
        user = await actor(request)
        from product_upload_mapping import Mapping
        provider = await run_in_threadpool(Dropbox)
        result = await run_in_threadpool(Mapping(connect, provider).status, request.query_params.get('id'), user)
        return JSONResponse(dict(mapping=result), headers=HEADERS)
    except Exception as error:
        return failure(error)


async def preview(request):
    try:
        user = await actor(request)
        row = await run_in_threadpool(Intakes(connect).read, request.query_params['id'], user['id'])
        if not row or row['data'].get('preparation_hash') != request.query_params.get('hash'):
            raise ValueError('Preview belongs to a previous source version.')
        row = await run_in_threadpool(reconcile, row, connect)
        if row['data'].get('state') != 'Cloud Ready' or row['data'].get('preparation_hash') != request.query_params.get('hash'):
            raise ValueError('This preview no longer matches the current PSD mapping.')
        from auto_editions_store import Preparations
        from auto_editions_bulk import preview_builds, prepared_fetch, evidence
        from auto_editions_review_thumbnails import ReviewBuildStore
        record = await run_in_threadpool(Preparations(connect).read, row['data']['preparation_hash'])
        # The reconciler already verifies strict readiness with current colour
        # policy. Thumbnail rendering uses the existing preview-only evidence.
        from auto_editions_preview_evidence import evidence as preview_evidence
        if not record or preview_evidence(record)['source'] != row['data']['bound_source']:
            raise ValueError('The prepared design changed.')
        data = await run_in_threadpool(preview_builds.read, record, prepared_fetch(), 300, ReviewBuildStore(connect))
        if data is None:
            return JSONResponse(dict(state='Preparing preview'), status_code=202, headers={**HEADERS, 'Retry-After':'5'})
        return Response(data, media_type='image/jpeg', headers={**HEADERS, 'Cache-Control':'private, max-age=900', 'Vary':'Cookie'})
    except Exception as error:
        return failure(error)


from product_upload_render import ROUTES as RENDER_ROUTES


async def source_preview(request):
    try:
        user = await actor(request)
        row = await run_in_threadpool(Intakes(connect).read, request.query_params['id'], user['id'])
        if not row or row['data'].get('workflow_version') != 3: raise ValueError('Select a Dropbox PSD first.')
        provider = await run_in_threadpool(Dropbox)
        expected = row['data']['source']
        if (row['data'].get('server_artwork') or {}).get('state') == 'Ready':
            from product_upload_artwork import ready
            folder = await run_in_threadpool(ready,row,connect,provider)
            return Response(await run_in_threadpool((folder/'preview.webp').read_bytes),media_type='image/webp',headers=HEADERS)
        meta = await run_in_threadpool(provider.metadata_if_present, expected['id'])
        if not meta or any(meta.get(k) != expected.get(k) for k in ('id','rev','content_hash')):
            raise ValueError('The selected revision changed. Select its current PSD again.')
        data = await run_in_threadpool(provider.api.get_psd_thumbnail_bytes, provider.token, meta['id'])
        after = await run_in_threadpool(provider.metadata_if_present, expected['id'])
        if not after or any(after.get(k) != expected.get(k) for k in ('id','rev','content_hash')):
            raise ValueError('PSD revision changed while loading the preview. Choose its current revision again.')
        return Response(data, media_type='image/jpeg', headers=HEADERS)
    except Exception as error: return failure(error)

async def original_asset(request):
    try:
        user = await actor(request, automatic=False)
        from product_upload_gallery import resolve
        from starlette.responses import FileResponse
        path = await run_in_threadpool(resolve, request.query_params.get('token', ''), user['id'], Intakes(connect).read)
        return FileResponse(path, headers=HEADERS)
    except Exception as error:
        return failure(error)


async def saved_package(request):
    try:
        from product_upload_package import view
        user = await actor(request)
        row = await run_in_threadpool(Intakes(connect).read, request.query_params.get('id'), user['id'])
        return JSONResponse(await run_in_threadpool(view, row), headers=HEADERS)
    except Exception as error: return failure(error)


async def saved_image(request):
    upstream = None
    try:
        from product_upload_package import package, verified
        from starlette.responses import StreamingResponse
        import files_upload_api as files
        user = await actor(request)
        row = await run_in_threadpool(Intakes(connect).read, request.query_params.get('id'), user['id'])
        result = package(row, request.query_params.get('version', ''))
        item = next((x for x in result['items'] if x['role'] == request.query_params.get('role')), None)
        if not item: raise ValueError('This saved image is unavailable.')
        provider = await run_in_threadpool(Dropbox)
        meta = await run_in_threadpool(verified, provider, item)
        if request.query_params.get('thumbnail') == '1':
            data = await run_in_threadpool(provider.api.get_thumbnail_bytes, provider.token, meta.get('path_display') or meta['path_lower'], size='w128h128')
            await run_in_threadpool(verified, provider, item)
            return Response(data, media_type='image/jpeg', headers=HEADERS)
        actual, upstream = await run_in_threadpool(provider.api.get_psd_file_response, provider.token, meta['id'], meta['rev'])
        if any(actual.get(k) != meta.get(k) for k in ('id', 'rev', 'content_hash', 'size')):
            raise ValueError(item['name'] + ' changed during retrieval. Retry Save all.')
        disposition = 'attachment' if request.query_params.get('download') == '1' else 'inline'
        return StreamingResponse(files._stream_upstream_response(upstream), media_type='image/webp',
            headers={**HEADERS, 'Content-Length': str(meta['size']), 'Content-Disposition': files._content_disposition(disposition, item['name'])})
    except Exception as error:
        if upstream is not None: upstream.close()
        return failure(error)


async def package_script(request):
    try:
        await actor(request, automatic=False)
        return Response((Path(__file__).parent/'components/product_uploads/package.js').read_text(encoding='utf-8'), media_type='application/javascript', headers=HEADERS)
    except Exception as error: return failure(error)


ROUTES = (*RENDER_ROUTES, ('/product-uploads', page, ('GET',)), ('/product-uploads.js', script, ('GET',)),
          ('/product-upload-package.js', package_script, ('GET',)),
          ('/api/product-uploads/saved-package', saved_package, ('GET',)),
          ('/api/product-uploads/saved-image', saved_image, ('GET',)),
          ('/product-upload-mapping.js', mapping_script, ('GET',)),
          ('/api/product-uploads/asset', original_asset, ('GET',)),
          ('/api/product-uploads/source-preview', source_preview, ('GET',)),
          ('/api/product-uploads/mapping-status', mapping_status, ('GET',)),
          ('/api/product-uploads/state', state, ('GET',)), ('/api/product-uploads/chunk', chunk, ('POST',)),
          ('/api/product-uploads/preview', preview, ('GET',)), ('/api/product-uploads/{action}', action, ('POST',)))
