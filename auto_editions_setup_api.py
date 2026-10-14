"""Administrator onboarding through the existing linked-PSD transfer companion."""
import json
from pathlib import Path
import re
import tempfile
import threading
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from starlette.responses import HTMLResponse,JSONResponse,FileResponse
import auto_editions as ae
import auto_editions_api as api
import auto_editions_cloud as cloud
import auto_editions_runtime as runtime
from auto_editions_package import MAX_PACKAGE_BYTES,unpack

IMPORT_LOCK=threading.Lock()


def setup_context(allocation_id):
    unit,mapping,metadata,assets=runtime.context(allocation_id)
    if (unit.get('allocation_valid') is not True or unit.get('identity_enforced') is not True
            or unit.get('invalidated_at') or unit.get('status') not in ('assigned','completed','fulfilled')):
        raise ValueError('Choose an existing valid allocation, including a completed order.')
    source=ae.source_identity(unit['shopify_product_gid'],metadata)
    return dict(allocation_id=allocation_id,source=source,
                metadata={k:metadata[k] for k in ('id','rev','content_hash','size','name')},
                number=unit['edition_number'],total=unit['edition_total'],
                variant_id=str(unit.get('shopify_variant_id') or ''),
                product_title=unit.get('product_title',''),variant_title=unit.get('variant_title',''))


async def page(request):
    try:
        await api.actor(request,setup=True);api.allocation(request)
        return HTMLResponse((Path(__file__).parent/'components/auto_editions/setup.html').read_text(),headers=api.HEADERS)
    except Exception as error:return api.failure(error)


async def details(request):
    try:
        await api.actor(request,setup=True)
        registry,_=runtime.stores()
        unit,mapping=await run_in_threadpool(registry.unit,api.allocation(request))
        current='';print_spec=None
        try:
            manifest=(await run_in_threadpool(registry.for_unit,unit))['manifest']
            current=ae.fingerprint(manifest)
            from auto_editions_print import describe
            print_spec=describe(unit.get('variant_title',''),manifest)
        except cloud.PreparationBlocked:pass
        candidate=request.query_params.get('preparation_hash','')
        candidate_info=None
        if candidate:
            if not re.fullmatch(r'[a-f0-9]{64}',candidate):raise ValueError('Invalid preparation identity.')
            row=await run_in_threadpool(registry.read,candidate)
            if not row or row['manifest']['source']['product_gid']!=unit['shopify_product_gid']:
                raise ValueError('Preparation does not belong to this product.')
            candidate_info=dict(hash=candidate,dimensions=row['manifest']['dimensions'],
                source_dimensions=row['manifest']['source_dimensions'],upscaled=row['manifest']['upscaled'])
        return JSONResponse(dict(candidate=candidate_info,product_gid=unit['shopify_product_gid'],product_title=unit.get('product_title',''),
            variant_title=unit.get('variant_title',''),variant_id=unit.get('shopify_variant_id'),
            number=unit['edition_number'],total=unit['edition_total'],linked=bool(mapping),
            current_hash=current,template_name=ae.reference_template().get('name','SC_Auto_Editions_Base_Template_V1.psd'),
            print_status='TEST / NOT PRINT READY' if current else 'NOT CONFIGURED',print_spec=print_spec),headers=api.HEADERS)
    except Exception as error:return api.failure(error)


async def prepare(request):
    try:
        import files_upload_api as files
        user=await api.actor(request,setup=True,write=True)
        if await files._json_body(request)!={}:raise ValueError('Preparation uses the current linked PSD.')
        ctx=await run_in_threadpool(setup_context,api.allocation(request))
        auth=await run_in_threadpool(files._dropbox_context)
        meta=await run_in_threadpool(files.dropbox_integration.psd_open_metadata,auth['access_token'],ctx['source']['file_id'],include_preview=False)
        if ae.source_identity(ctx['source']['product_gid'],meta)!=ctx['source']:raise ValueError('Source changed. Retry.')
        record=files.NATIVE_TRANSFER_MANAGER.create_psd(access_token=auth['access_token'],root_path=auth['root_path'],user=user,metadata=meta)
        record.v6_setup=dict(context=ctx,actor_id=str(user['id']),session_version=user.get('session_version'),importing=False)
        return JSONResponse(dict(grant=dict(base_url=str(request.base_url).rstrip('/'),ticket=record.ticket,secret=record.secret)),headers=api.HEADERS)
    except Exception as error:return api.failure(error)


def grant_context(request):
    import files_upload_api as files
    if not runtime.enabled():raise PermissionError('Cloud setup is disabled.')
    manager=files.NATIVE_TRANSFER_MANAGER
    with manager._lock:
        record=manager.get(request.query_params.get('ticket'),files._native_transfer_secret(request))
        setup=getattr(record,'v6_setup',None)
        if not setup:raise PermissionError('Administrator preparation grant required.')
        if setup['actor_id']!='legacy-master-admin':
            user=files.os_accounts.DEFAULT_STORE.get_user(setup['actor_id'])
            if not user or str(user.get('session_version'))!=str(setup['session_version']):
                raise PermissionError('Administrator session changed.')
            cloud.require_access(user,setup=True)
    if setup['context'].get('automatic'):
        from auto_editions_onboarding_api import product_context
        if setup.get('host_token_hash'):
            from auto_editions_onboarding_api import queue,host_account
            with queue().connect() as conn,conn.cursor() as cur:
                cur.execute('''SELECT * FROM auto_edition_preparation_hosts WHERE token_hash=%s
                    AND revoked_at IS NULL AND expires_at>now()''',(setup['host_token_hash'],))
                host=cur.fetchone()
                if not host:raise PermissionError('Preparation host was revoked.')
                host_account(host)
        current=product_context(setup['context']['product_gid'],setup['context']['lease_token'])
    else:
        current=setup_context(setup['context']['allocation_id'])
    if current!=setup['context']:raise ValueError('Linked source or allocation changed during preparation.')
    return setup


async def context(request):
    try:
        setup=await run_in_threadpool(grant_context,request)
        return JSONResponse(setup['context'],headers=api.HEADERS)
    except Exception as error:return api.failure(error)


async def package(request):
    acquired=False
    try:
        setup=await run_in_threadpool(grant_context,request)
        acquired=IMPORT_LOCK.acquire(blocking=False)
        if not acquired:raise ValueError('Another preparation is being verified. Retry shortly.')
        if setup.get('imported'):raise ValueError('This preparation grant was already used.')
        with tempfile.TemporaryDirectory(prefix='sc-edition-import-') as folder:
            root=Path(folder);archive=root/'package.zip'
            size=0
            with archive.open('xb') as output:
                async for block in request.stream():
                    size+=len(block)
                    if size>MAX_PACKAGE_BYTES:raise ValueError('Preparation transfer exceeds its limit.')
                    output.write(block)
            assets_root=root/'assets';assets_root.mkdir()
            ctx=setup['context']
            manifest,proofs=await run_in_threadpool(unpack,archive,assets_root,ctx['source'],ctx['number'],ctx['total'])
            assets=runtime.storage()
            receipts=await run_in_threadpool(assets.publish_preparation,manifest,assets_root)
            await run_in_threadpool(grant_context,request)
            registry,_=runtime.stores()
            digest=await run_in_threadpool(registry.save,manifest,proofs,receipts,setup['actor_id'])
            if ctx.get('automatic'):
                from auto_editions_onboarding_api import queue,host_account
                await run_in_threadpool(queue().checkpoint,ctx['product_gid'],ctx['lease_token'],setup['actor_id'],
                    'Blocked','Prepared and pixel-verified; visual quality review required before Cloud Ready.',digest=digest)
            setup['imported']=digest
        return JSONResponse(dict(preparation_hash=digest,status='Awaiting visual approval',print_ready=False),headers=api.HEADERS)
    except Exception as error:return api.failure(error)
    finally:
        if acquired:IMPORT_LOCK.release()


async def approve(request):
    try:
        import files_upload_api as files
        user=await api.actor(request,setup=True,write=True)
        body=await files._json_body(request)
        if set(body)!={'preparation_hash','expected_hash','confirm_test_layout'} or body['confirm_test_layout'] is not True:
            raise ValueError('Confirm the artwork, plaque placement and exact variant for TEST use.')
        registry,_=runtime.stores()
        record=await run_in_threadpool(registry.read,body['preparation_hash'])
        if not record:raise ValueError('Prepare this design first.')
        unit,mapping,meta,_=await run_in_threadpool(runtime.context,api.allocation(request))
        approval=dict(actor_id=str(user['id']),preparation_hash=body['preparation_hash'],pixel_exact=True,visual_approved=True)
        cloud.confirmed_job(unit,mapping,meta,dict(manifest=record['manifest'],approval=approval,
                            variant_ids=[str(unit.get('shopify_variant_id') or '')]))
        await run_in_threadpool(registry.approve,body['preparation_hash'],unit,str(user['id']),body['expected_hash'])
        return JSONResponse(dict(status='TEST READY',print_ready=False),headers=api.HEADERS)
    except Exception as error:return api.failure(error)


async def preview(request):
    folder=None
    try:
        await api.actor(request,setup=True)
        digest=request.query_params.get('preparation_hash','')
        if not re.fullmatch(r'[a-f0-9]{64}',digest):raise ValueError('Invalid preparation identity.')
        registry,_=runtime.stores();record=await run_in_threadpool(registry.read,digest)
        unit,mapping,meta,assets=await run_in_threadpool(runtime.context,api.allocation(request))
        if not record or record['manifest']['source']!=ae.source_identity(unit['shopify_product_gid'],meta):
            raise ValueError('Preview does not match the linked source.')
        manifest=record['manifest'];folder=tempfile.TemporaryDirectory(prefix='sc-edition-preview-')
        root=Path(folder.name)
        def render():
            for asset in [manifest['master'],manifest['patches'][str(unit['edition_number'])]]:
                assets.fetch(digest,asset,root/asset['name'])
            ae.render_jpg(manifest,root,unit['edition_number'],root/'preview.jpg')
        await run_in_threadpool(render)
        return FileResponse(root/'preview.jpg',media_type='image/jpeg',headers=api.HEADERS,background=BackgroundTask(folder.cleanup))
    except Exception as error:
        if folder:folder.cleanup()
        return api.failure(error)


ROUTES=(('/auto-editions/setup',page,('GET',)),('/api/auto-editions/details',details,('GET',)),
        ('/api/auto-editions/prepare',prepare,('POST',)),('/api/auto-editions/context',context,('GET',)),
        ('/api/auto-editions/package',package,('POST',)),('/api/auto-editions/approve',approve,('POST',)),
        ('/api/auto-editions/preview',preview,('GET',)))
