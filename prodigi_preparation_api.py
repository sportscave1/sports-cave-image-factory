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
        value = await run_in_threadpool(queue.tick)
        from prodigi_submission import kick
        kick()
        from prodigi_browser import claim
        browser = (await run_in_threadpool(claim)
            if request.headers.get('x-sports-cave-orders-browser') == '1' else None)
        if browser is None and request.headers.get('x-sports-cave-orders-qa')=='1':
            from prodigi_dashboard_qa import claim as qa_claim
            browser=await run_in_threadpool(qa_claim)
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
        if (not isinstance(body,dict) or (set(body)!={'key','token','sha256'} if is_permit else set(body) not in ({'key','token'},{'key','token','stage'})) or
            not all(isinstance(v,str) for v in body.values()) or
            not re.fullmatch(r'[A-Za-z0-9_-]{43}',body['token'])):
            raise ValueError('Only an exact Orders handoff receipt is accepted.')
        if not is_permit and body.get('stage','readback') not in ('readback','download','open','signin','page','row','editor','picker','transfer','uploaded','orientation','permit','save'):
            raise ValueError('Unknown browser stage.')
        import os
        if (re.fullmatch(r'(?:document:)?prodigi_sandbox_test:[a-f0-9-]{36}',body['key']) and
            os.getenv('SPORTS_CAVE_PRODIGI_SANDBOX_ENABLED','').lower()!='true'):
            return JSONResponse({'status':'Stopped'},headers=HEADERS)
        from prodigi_browser import permit,finish
        if body['key'].startswith('document:'):
            from prodigi_document_browser import permit,finish
        result=await run_in_threadpool(permit,body['key'],body['token'],body['sha256']) if is_permit else await run_in_threadpool(finish,body['key'],body['token'],body.get('stage','readback'))
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


ROUTES = (('/api/orders-companion/qa/permit',dashboard_qa_action,('POST',)),
          ('/api/orders-companion/qa/finish',dashboard_qa_action,('POST',)),('/api/orders-companion/tick', tick, ('POST',)),
          ('/api/orders-companion/browser/permit',browser_action,('POST',)),
          ('/api/orders-companion/browser/finish',browser_action,('POST',)),
          ('/api/prodigi-artwork/{token}', serve_artwork, ('GET', 'HEAD')),
          ('/api/prodigi-document/{token}', serve_document, ('GET','HEAD')))
