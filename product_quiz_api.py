"""Small anonymous, consent-gated analytics ingest; all reports remain admin only."""
import json
import os
import re
import threading
import time
from uuid import UUID
from starlette.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

_LOCK=threading.Lock()
_BUCKETS={}


def clean(payload):
    if set(payload)!={'event_id','session_id','version','type','step','source','product_id'}: raise ValueError('Invalid event fields')
    result={}
    for name in ('event_id','session_id'): result[name]=str(UUID(payload[name]))
    if not re.fullmatch('[a-f0-9]{24}',payload['version']): raise ValueError('Invalid version')
    if payload['type'] not in {'started','question','answered','completed','product_click','closed'}: raise ValueError('Invalid event')
    if payload['step'] not in {'','sport','subject','preference'} or payload['source'] not in {'collection','page','campaign'}: raise ValueError('Invalid context')
    if payload['product_id'] and not re.fullmatch(r'gid://shopify/Product/\d{1,24}',payload['product_id']): raise ValueError('Invalid product')
    return {**payload,**result}


async def ingest(request):
    allowed=set(filter(None,os.getenv('PRODUCT_QUIZ_ALLOWED_ORIGINS','https://sportscaveshop.com,https://www.sportscaveshop.com').split(',')))
    origin=request.headers.get('origin','')
    headers={'Vary':'Origin','Cache-Control':'no-store','Access-Control-Allow-Methods':'POST, OPTIONS',
             'Access-Control-Allow-Headers':'Content-Type','X-Content-Type-Options':'nosniff'}
    if origin not in allowed: return Response(status_code=403,headers=headers)
    headers['Access-Control-Allow-Origin']=origin
    if request.method=='OPTIONS': return Response(status_code=204,headers=headers)
    if os.getenv('PRODUCT_QUIZ_ENABLED')!='true': return Response(status_code=503,headers=headers)
    try:
        body=bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body)>2048: return Response(status_code=413,headers=headers)
        payload=clean(json.loads(body))
        # Bounded in-memory abuse limit. No PII, cookies, IP addresses or answer text.
        at=time.monotonic();rate_key=payload['session_id']
        with _LOCK:
            for k in list(_BUCKETS):
                if _BUCKETS[k][0]<at-600: del _BUCKETS[k]
            start,count=_BUCKETS.get(rate_key,(at,0))
            if count>=150 or len(_BUCKETS)>=10000 and rate_key not in _BUCKETS: return Response(status_code=429,headers=headers)
            _BUCKETS[rate_key]=(start,count+1)
        from product_quiz_store import QuizStore
        inserted=await run_in_threadpool(QuizStore().event,payload)
        return JSONResponse({'ok':True,'duplicate':not inserted},headers=headers)
    except (ValueError,TypeError,KeyError,AttributeError): return JSONResponse({'ok':False},status_code=400,headers=headers)
    except Exception: return JSONResponse({'ok':False},status_code=503,headers=headers)


ROUTES=(('/api/product-quiz/events',ingest,('POST','OPTIONS')),)
