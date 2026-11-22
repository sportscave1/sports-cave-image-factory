"""Paired Orders companion polling. The Prodigi key stays on the server."""
import re
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
import prodigi_preparation as queue


def desktop(token):
    import product_upload_staff_queue as pairing
    import os_accounts
    with queue.connect() as conn, conn.cursor() as cur:
        cur.execute('''UPDATE product_upload_desktop SET seen_at=now()
            WHERE singleton AND token_hash=%s RETURNING actor_id''', (pairing.digest(token),))
        row = cur.fetchone()
    if not row:
        raise PermissionError('Pair this desktop in Companion control first.')
    user = os_accounts.DEFAULT_STORE.get_user(row['actor_id'])
    queue.require_user(user)
    if not os_accounts.can_access_page(user, 'Upload Companion'):
        raise PermissionError('Orders companion access is required.')
    return user


async def tick(request):
    from product_upload_api import HEADERS, failure
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
        await run_in_threadpool(desktop, auth[7:])
        from orders_automatic import kick as admit_orders
        admit_orders()
        value = await run_in_threadpool(queue.tick)
        from prodigi_submission import kick
        kick()
        from prodigi_browser import claim
        browser = None
        if request.headers.get('x-sports-cave-orders-products')=='1' and __import__('os').getenv('SPORTS_CAVE_PRODIGI_BROWSER_ACCEPTED','').lower()=='true':
            from prodigi_product_browser import claim as product_claim
            browser=await run_in_threadpool(product_claim)
        browser = browser or (await run_in_threadpool(claim,exact_item_supported=request.headers.get('x-sports-cave-orders-products')=='1',reset_supported=request.headers.get('x-sports-cave-orders-reset')=='1')
            if request.headers.get('x-sports-cave-orders-browser') == '1' else None)
        if browser is None and request.headers.get('x-sports-cave-orders-qa')=='1':
            from prodigi_dashboard_qa import claim as qa_claim
            browser=await run_in_threadpool(qa_claim,tax_supported=request.headers.get('x-sports-cave-orders-tax')=='1',exact_item_supported=request.headers.get('x-sports-cave-orders-products')=='1',batch_supported=request.headers.get('x-sports-cave-orders-qa-batch')=='1')
        if browser is None and request.headers.get('x-sports-cave-orders-documents')=='1' and __import__('os').getenv('SPORTS_CAVE_PRODIGI_LEGACY_DOCUMENT_UPLOAD','').lower()=='true':
            from prodigi_document_browser import claim as document_claim
            browser=await run_in_threadpool(document_claim)
        return JSONResponse({'enabled': queue.enabled(), 'job':
            {'allocation_id': value['allocation_id'], 'status': value['status']} if value else None,
            'browser': browser}, headers=HEADERS)
    except Exception as error:
        return failure(error)


from prodigi_artwork import serve as serve_artwork
from prodigi_documents import serve as serve_document


async def browser_action(request):
    from product_upload_api import HEADERS, failure
    try:
        import json
        auth=request.headers.get('authorization','')
        if not re.fullmatch(r'Bearer [A-Za-z0-9_-]{43}',auth):
            raise PermissionError('A paired desktop credential is required.')
        await run_in_threadpool(desktop,auth[7:])
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
        if not is_permit and body.get('stage','readback') not in ('readback','download','open','signin','page','row','editor','reset-image','picker','transfer','uploaded','orientation','permit','save','product','product-search','product-select','product-readback'):
            raise ValueError('Unknown browser stage.')
        import os
        if (re.fullmatch(r'(?:document:)?prodigi_sandbox_test:[a-f0-9-]{36}',body['key']) and
            os.getenv('SPORTS_CAVE_PRODIGI_SANDBOX_ENABLED','').lower()!='true'):
            return JSONResponse({'status':'Stopped'},headers=HEADERS)
        from prodigi_browser import permit,finish
        if body['key'].startswith('document:'):
            from prodigi_document_browser import permit,finish
        if body['key'].startswith('product:'):
            from prodigi_product_browser import permit,finish
        extra={'error':body.get('error','')} if not body['key'].startswith(('product:','document:')) else {}
        result=await run_in_threadpool(permit,body['key'],body['token'],body['sha256']) if is_permit else await run_in_threadpool(finish,body['key'],body['token'],body.get('stage','readback'),**extra)
        return JSONResponse(result,headers=HEADERS)
    except Exception as error:
        return failure(error)


async def dashboard_qa_action(request):
    from product_upload_api import HEADERS,failure
    try:
        import json
        auth=request.headers.get('authorization','')
        if not re.fullmatch(r'Bearer [A-Za-z0-9_-]{43}',auth):raise PermissionError('A paired desktop credential is required.')
        await run_in_threadpool(desktop,auth[7:])
        raw=bytearray()
        async for block in request.stream():
            raw.extend(block)
            if len(raw)>8192:raise ValueError('QA receipt is too large.')
        body=json.loads(raw)
        if (not isinstance(body,dict) or set(body) not in ({'key','token','evidence'},{'key','token','evidence','error'})
            or not isinstance(body['key'],str) or not isinstance(body['token'],str)
            or not re.fullmatch(r'[A-Za-z0-9_-]{43}',body['token'])
            or not isinstance(body.get('error',''),str) or len(body.get('error',''))>240):raise ValueError('Invalid QA receipt.')
        from prodigi_dashboard_qa import permit,finish
        result=await run_in_threadpool(permit,body['key'],body['token'],body['evidence']) if request.url.path.endswith('/permit') else await run_in_threadpool(finish,body['key'],body['token'],body['evidence'],body.get('error',''))
        return JSONResponse(result,headers=HEADERS)
    except Exception as error:return failure(error)


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
        result=await run_in_threadpool(reset_order,user,body['allocation_id'])
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

ROUTES = (('/api/orders-companion/status',order_status,('GET',)),('/api/orders-companion/restart',restart_order,('POST',)),('/api/orders/certificate',open_certificate,('GET',)),('/api/orders-companion/qa/permit',dashboard_qa_action,('POST',)),
          ('/api/orders-companion/qa/finish',dashboard_qa_action,('POST',)),('/api/orders-companion/tick', tick, ('POST',)),
          ('/api/orders-companion/browser/permit',browser_action,('POST',)),
          ('/api/orders-companion/browser/finish',browser_action,('POST',)),
          ('/api/prodigi-artwork/{token}', serve_artwork, ('GET', 'HEAD')),
          ('/api/prodigi-document/{token}', serve_document, ('GET','HEAD')))
