"""Paired Inbox Companion endpoints. No arbitrary mail, address or supplier jobs."""
import json
import re
from threading import BoundedSemaphore
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
import inbox_companion as inbox

SLOTS=BoundedSemaphore(1)

async def endpoint(request):
    from prodigi_preparation_api import desktop
    from product_upload_api import HEADERS,failure
    try:
        auth=request.headers.get('authorization','')
        if not re.fullmatch(r'Bearer [A-Za-z0-9_-]{43}',auth):raise PermissionError('Pair this desktop first.')
        actor=await run_in_threadpool(desktop,auth[7:],slots=SLOTS)
        import os_accounts
        if not os_accounts.can_access_page(actor,'Email'):raise PermissionError('Email access required.')
        raw=bytearray()
        async for block in request.stream():
            raw.extend(block)
            if len(raw)>1024:raise ValueError('Inbox receipt too large.')
        data=json.loads(raw or b'{}')
        action=request.url.path.rsplit('/',1)[-1]
        if action=='tick':
            if data!={}:raise ValueError('Inbox tick accepts no job instructions.')
            result=await run_in_threadpool(inbox.tick,actor,scan_only=request.headers.get('x-inbox-scan-only')=='1')
        else:
            if not inbox.available() or not (await run_in_threadpool(inbox.read,inbox.SETTING)).get('enabled'):
                raise PermissionError('Inbox Companion is disabled.')
            expected={'key','token','order_id'}|({'evidence','error'} if action=='finish' else set())
            if not isinstance(data,dict) or set(data)!=expected:raise ValueError('Invalid Inbox receipt.')
            if not all(isinstance(data[k],str) for k in ('key','token','order_id')) or not re.fullmatch(r'[A-Za-z0-9_-]{43}',data['token']):
                raise ValueError('Invalid Inbox identity.')
            if action=='permit':result=await run_in_threadpool(inbox.permit,**data)
            elif action=='finish':
                if not isinstance(data['error'],str) or len(data['error'])>240:raise ValueError('Invalid Inbox result.')
                evidence=data['evidence']
                if evidence is not None and (not isinstance(evidence,dict) or set(evidence)-{'address_saved','indefinite_hold'} or any(type(v) is not bool for v in evidence.values())):
                    raise ValueError('Invalid Inbox evidence.')
                result=await run_in_threadpool(inbox.finish,**data)
            else:raise ValueError('Unknown Inbox operation.')
        return JSONResponse(result,headers=HEADERS)
    except Exception as error:return failure(error)

ROUTES=tuple(('/api/inbox-companion/'+name,endpoint,('POST',)) for name in ('tick','permit','finish'))
