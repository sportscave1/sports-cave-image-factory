"""Paired Orders companion polling. The Prodigi key stays on the server."""
import re
from threading import BoundedSemaphore

# Short Orders auth must not queue behind other workers' external operations.
_orders_auth_slots=BoundedSemaphore(1)
_orders_action_auth_slots=BoundedSemaphore(1)
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
import prodigi_preparation as queue

def _record_runtime_version(value):
    from orders_runtime import record_version
    try:record_version(value)
    except Exception:pass  # Telemetry failure never changes a handoff outcome.


def desktop(token,*,slots=None):
    import product_upload_staff_queue as pairing
    import os_accounts
    from companion_poll_transaction import connection
    limiter=_orders_auth_slots if slots is None else slots
    with connection(queue.connect,slots=limiter) as conn, conn.cursor() as cur:
        # Authenticate through MVCC; another worker's long transaction must not
        # make Orders wait for the shared desktop heartbeat row lock.
        cur.execute('''SELECT actor_id FROM product_upload_desktop
            WHERE singleton AND token_hash=%s''', (pairing.digest(token),))
        row = cur.fetchone()
    if not row:
        raise PermissionError('Pair this desktop in Companion control first.')
    user = os_accounts.DEFAULT_STORE.get_user(row['actor_id'])
    queue.require_user(user)
    if not os_accounts.can_access_page(user, 'Upload Companion'):
        raise PermissionError('Orders companion access is required.')
    with connection(queue.connect,slots=limiter) as conn,conn.cursor() as cur:
        cur.execute("""INSERT INTO app_settings(key,value,updated_at) VALUES('orders_companion_seen','true',now())
            ON CONFLICT(key) DO UPDATE SET updated_at=now()
            WHERE app_settings.updated_at<now()-interval '20 seconds'""")
    return user


async def ready_handoff(request, merge_supported):
    from prodigi_browser import claim
    browser = None
    preferred=request.headers.get('x-sports-cave-orders-continue','')
    priority={'preferred_order':preferred} if re.fullmatch(r'[A-Za-z0-9-]{1,100}',preferred) else {}
    if merge_supported:
        from prodigi_consolidation import claim as merge_claim
        browser=await run_in_threadpool(merge_claim)
    # Finish already-uploaded orders before starting another large transfer.
    if browser is None and request.headers.get('x-sports-cave-orders-qa')=='1':
        from prodigi_dashboard_qa import claim as qa_claim
        browser=await run_in_threadpool(qa_claim,tax_supported=request.headers.get('x-sports-cave-orders-tax')=='1',exact_item_supported=request.headers.get('x-sports-cave-orders-products')=='1',batch_supported=request.headers.get('x-sports-cave-orders-qa-batch')=='1',sequential_supported=request.headers.get('x-sports-cave-orders-sequential')=='1',item_qa_supported=request.headers.get('x-sports-cave-orders-item-qa')=='1',**priority)
    # Continue the selected item through upload before choosing a sibling.
    if browser is None and request.headers.get('x-sports-cave-orders-browser')=='1':
        browser=await run_in_threadpool(claim,exact_item_supported=request.headers.get('x-sports-cave-orders-products')=='1',reset_supported=request.headers.get('x-sports-cave-orders-reset')=='1',**priority)
    if browser is None and request.headers.get('x-sports-cave-orders-products')=='1' and __import__('os').getenv('SPORTS_CAVE_PRODIGI_BROWSER_ACCEPTED','').lower()=='true':
        from prodigi_product_browser import claim as product_claim
        browser=await run_in_threadpool(product_claim,**priority)
    if browser is None and request.headers.get('x-sports-cave-orders-documents')=='1' and __import__('os').getenv('SPORTS_CAVE_PRODIGI_LEGACY_DOCUMENT_UPLOAD','').lower()=='true':
        from prodigi_document_browser import claim as document_claim
        browser=await run_in_threadpool(document_claim)
    return browser


async def tick(request):
    from product_upload_api import HEADERS, failure
    stage='request'
    try:
        auth = request.headers.get('authorization', '')
        if not re.fullmatch(r'Bearer [A-Za-z0-9_-]{43}', auth):
            raise PermissionError('A paired desktop credential is required.')
        # No provider URLs, artwork, QA claims or production actions from Edge.
        body = bytearray()
        async for block in request.stream():
            body.extend(block)
            if len(body) > 2:
                raise ValueError('Orders tick accepts no job instructions.')
        if bytes(body) not in (b'', b'{}'):
            raise ValueError('Orders tick accepts no job instructions.')
        if not queue.enabled():
            return JSONResponse({'enabled': False, 'job': None}, headers=HEADERS)
        stage='authentication'
        actor=await run_in_threadpool(desktop, auth[7:])
        if request.headers.get('x-sports-cave-orders-empty-editor')=='1':
            stage='empty_product_editor_recovery'
            from prodigi_browser import recover_selected_empty_editors
            if request.headers.get('x-sports-cave-orders-upload-ready')=='1':
                await run_in_threadpool(recover_selected_empty_editors,actor,page_supported=True,processing_supported=True)
            elif request.headers.get('x-sports-cave-orders-fresh-page')=='1':
                await run_in_threadpool(recover_selected_empty_editors,actor,page_supported=True)
            else:await run_in_threadpool(recover_selected_empty_editors,actor)
            stage='product_selection_readback_recovery'
            from prodigi_product_browser import recover_readbacks
            await run_in_threadpool(recover_readbacks,actor)
        if request.headers.get('x-sports-cave-orders-item-qa')=='1':
            stage='item_qa_recovery'
            from prodigi_dashboard_qa import recover_waiting_item_qa
            if request.headers.get('x-sports-cave-orders-fresh-page')=='1':
                await run_in_threadpool(recover_waiting_item_qa,actor,page_supported=True)
            else:await run_in_threadpool(recover_waiting_item_qa,actor)
        merge_supported=request.headers.get('x-sports-cave-orders-merge')=='1'
        if merge_supported:
            stage='merge_readback'
            from prodigi_consolidation import record_capability,commit_ready
            await run_in_threadpool(record_capability)
            await run_in_threadpool(commit_ready)
        from orders_automatic import kick as admit_orders
        admit_orders()
        value = None
        from prodigi_submission import kick
        kick()
        from prodigi_status_sync import kick as sync_supplier_status
        sync_supplier_status()
        stage='ready_handoff'
        browser = await ready_handoff(request,merge_supported)
        if browser is None:
            stage='preparation'
            value = await run_in_threadpool(queue.tick)
            stage='prepared_handoff'
            browser = await ready_handoff(request,merge_supported)
        from starlette.background import BackgroundTask
        runtime_version=request.headers.get('x-sports-cave-orders-version','')
        background=BackgroundTask(_record_runtime_version,runtime_version) if runtime_version else None
        return JSONResponse({'enabled': queue.enabled(), 'job':
            {'allocation_id': value['allocation_id'], 'status': value['status']} if value else None,
            'browser': browser}, headers=HEADERS,background=background)
    except Exception as error:
        import logging
        logging.getLogger(__name__).warning('Orders poll retry stage=%s kind=%s',stage,type(error).__name__)
        return failure(error)


from prodigi_artwork import serve as serve_artwork
from prodigi_documents import serve as serve_document


async def browser_action(request):
    from product_upload_api import HEADERS, failure
    stage='authentication'
    try:
        import json
        auth=request.headers.get('authorization','')
        if not re.fullmatch(r'Bearer [A-Za-z0-9_-]{43}',auth):
            raise PermissionError('A paired desktop credential is required.')
        await run_in_threadpool(desktop,auth[7:],slots=_orders_action_auth_slots)
        stage='request_validation'
        raw=bytearray()
        async for block in request.stream():
            raw.extend(block)
            if len(raw)>512: raise ValueError('Orders receipt is too large.')
        body=json.loads(raw)
        is_permit=request.url.path.endswith('/permit')
        if (not isinstance(body,dict) or (set(body)!={'key','token','sha256'} if is_permit else set(body) not in ({'key','token'},{'key','token','stage'},{'key','token','stage','error'})) or
            not all(isinstance(v,str) for v in body.values()) or
            len(body.get('error',''))>240 or
            not re.fullmatch(r'[A-Za-z0-9_-]{43}',body['token'])):
            raise ValueError('Only an exact Orders handoff receipt is accepted.')
        if not is_permit and body.get('stage','readback') not in ('readback','download','open','signin','readiness','page','row','editor','reset-image','picker','transfer','uploaded','orientation','permit','save','product','product-search','product-select','product-readback','merge-hold','merge-hold-confirmed'):
            raise ValueError('Unknown browser stage.')
        import os
        if (re.fullmatch(r'(?:document:)?prodigi_sandbox_test:[a-f0-9-]{36}',body['key']) and
            os.getenv('SPORTS_CAVE_PRODIGI_SANDBOX_ENABLED','').lower()!='true'):
            return JSONResponse({'status':'Stopped'},headers=HEADERS)
        from prodigi_browser import permit,finish
        if body['key'].startswith(('merge:','mergehold:')):
            from prodigi_consolidation import permit,finish
        if body['key'].startswith('document:'):
            from prodigi_document_browser import permit,finish
        if body['key'].startswith('product:'):
            from prodigi_product_browser import permit,finish
        kind=('product' if body['key'].startswith('product:') else
              'document' if body['key'].startswith('document:') else
              'merge' if body['key'].startswith(('merge:','mergehold:')) else 'artwork')
        stage=kind+('.permit' if is_permit else '.finish')
        extra={'error':body.get('error','')} if not body['key'].startswith('document:') else {}
        result=await run_in_threadpool(permit,body['key'],body['token'],body['sha256']) if is_permit else await run_in_threadpool(finish,body['key'],body['token'],body.get('stage','readback'),**extra)
        return JSONResponse(result,headers=HEADERS)
    except Exception as error:
        __import__('logging').getLogger(__name__).warning('Orders browser request stopped stage=%s kind=%s sqlstate=%s',stage,type(error).__name__,getattr(error,'sqlstate',''))
        return failure(error)


async def dashboard_qa_action(request):
    from product_upload_api import HEADERS,failure
    stage='authentication'
    try:
        import json
        auth=request.headers.get('authorization','')
        if not re.fullmatch(r'Bearer [A-Za-z0-9_-]{43}',auth):raise PermissionError('A paired desktop credential is required.')
        await run_in_threadpool(desktop,auth[7:],slots=_orders_action_auth_slots)
        raw=bytearray()
        async for block in request.stream():
            raw.extend(block)
            if len(raw)>32768:raise ValueError('QA receipt is too large.')
        body=json.loads(raw)
        if (not isinstance(body,dict) or set(body) not in ({'key','token','evidence'},{'key','token','evidence','error'})
            or not isinstance(body['key'],str) or not isinstance(body['token'],str)
            or not re.fullmatch(r'[A-Za-z0-9_-]{43}',body['token'])
            or not isinstance(body.get('error',''),str) or len(body.get('error',''))>240):raise ValueError('Invalid QA receipt.')
        from prodigi_dashboard_qa import permit,finish
        stage='permit_verification' if request.url.path.endswith('/permit') else 'finish_verification'
        result=await run_in_threadpool(permit,body['key'],body['token'],body['evidence']) if request.url.path.endswith('/permit') else await run_in_threadpool(finish,body['key'],body['token'],body['evidence'],body.get('error',''))
        if request.url.path.endswith('/finish') and result.get('status')=='Ready for manual payment':
            from prodigi_consolidation import kick_commit
            kick_commit()
            from prodigi_submission import kick
            kick() # Owner gate and durable order fence still precede any POST.
        return JSONResponse(result,headers=HEADERS)
    except Exception as error:
        __import__('logging').getLogger(__name__).warning('Orders QA request stopped stage=%s kind=%s sqlstate=%s',stage,type(error).__name__,getattr(error,'sqlstate',''))
        return failure(error)


from orders_certificate import open_certificate


async def restart_order(request):
    from files_upload_api import _request_user,_same_origin
    from product_upload_api import HEADERS,failure
    try:
        if not request.headers.get('origin') or not _same_origin(request):raise PermissionError('Request origin rejected.')
        user=await run_in_threadpool(_request_user,request,required_page='Orders')
        queue.require_user(user)
        body=await request.json()
        if not isinstance(body,dict) or set(body)!={'allocation_id'} or type(body['allocation_id']) is not int or body['allocation_id']<=0:
            raise ValueError('Choose an allocated order to restart.')
        from prodigi_reset import reset_order
        current=await run_in_threadpool(queue.read,body['allocation_id'])
        if current and current.get('merge_pending'):
            from prodigi_consolidation import restart_qa
            result=await run_in_threadpool(restart_qa,user,body['allocation_id'])
        else:result=await run_in_threadpool(reset_order,user,body['allocation_id'])
        if result and result.get('status') in ('Queued','Preparing JPG','Checking QA','Awaiting dashboard QA','Checking dashboard QA'):
            def clear_request_failure():
                with queue.connect() as c,c.cursor() as q:
                    q.execute("UPDATE app_settings SET value=value || %s::jsonb,updated_at=now() WHERE key=%s",
                        (__import__('json').dumps(dict(active=False,resolved_at=queue.now())),queue.FAILURE_PREFIX+str(body['allocation_id'])))
            await run_in_threadpool(clear_request_failure)
        return JSONResponse({'status':(result or {}).get('status','Queued')},headers=HEADERS)
    except Exception as error:return failure(error)


async def order_status(request):
    from files_upload_api import _request_user
    from product_upload_api import HEADERS,failure
    try:
        user=await run_in_threadpool(_request_user,request,required_page='Orders');queue.require_user(user)
        raw=request.query_params.get('allocations','')
        if len(raw)>2500 or not re.fullmatch(r'[1-9][0-9]*(?:,[1-9][0-9]*){0,199}',raw):
            raise ValueError('Choose up to 200 allocated editions.')
        ids=raw.split(',')
        from orders_prodigi_grid import batch_status,review
        saved=await run_in_threadpool(batch_status,ids)
        return JSONResponse({'orders':{aid:review(saved.get(aid),{'edition_order_id':aid},'') for aid in ids}},headers=HEADERS)
    except Exception as error:return failure(error)

from orders_wake import listen as orders_notifications
from orders_feed import feed as orders_row_feed
from orders_runtime import endpoint as orders_progress
from orders_runtime import metrics_endpoint as orders_metrics

ROUTES = (('/api/orders/feed',orders_row_feed,('POST',)),('/api/orders-companion/notifications',orders_notifications,('GET',)),('/api/orders-companion/status',order_status,('GET',)),('/api/orders-companion/restart',restart_order,('POST',)),('/api/orders/certificate',open_certificate,('GET',)),('/api/orders-companion/qa/permit',dashboard_qa_action,('POST',)),
          ('/api/orders-companion/qa/finish',dashboard_qa_action,('POST',)),('/api/orders-companion/tick', tick, ('POST',)),
          ('/api/orders-companion/browser/permit',browser_action,('POST',)),
          ('/api/orders-companion/browser/finish',browser_action,('POST',)),
          ('/api/prodigi-artwork/{token}', serve_artwork, ('GET', 'HEAD')),
          ('/api/prodigi-document/{token}', serve_document, ('GET','HEAD')),
          ('/api/orders-companion/progress',orders_progress,('POST',)),
          ('/api/orders-companion/metrics',orders_metrics,('GET',)))
