"""Small anonymous, consent-gated analytics ingest; all reports remain admin only."""
import json
import os
import re
import threading
import time
import hashlib
from pathlib import Path
from uuid import UUID
from starlette.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

_LOCK=threading.Lock()
_BUCKETS={}
_ASSETS={}
_PUBLIC_PATH=re.compile(r'(?:loader\.js|manifest\.json|catalogue\.json|(?:config|catalogue)/[a-f0-9]{24}\.json|runtime/[a-f0-9]{24}\.js)\Z')


def public_bytes(path):
    """Read exact published objects only; private R2 never becomes public."""
    immutable=bool(re.search(r'/[a-f0-9]{24}\.',path))
    at=time.monotonic()
    with _LOCK:
        cached=_ASSETS.get(path)
        if cached and cached['expires']>at: return cached
    if path=='loader.js':
        data=(Path(__file__).parent/'static/product-quiz/loader.js').read_bytes()
    else:
        if path.startswith(('config/','runtime/')):
            manifest=json.loads(public_bytes('manifest.json')['body'])
            previous=manifest.get('previous') or {}
            allowed={manifest.get('config'),manifest.get('runtime'),previous.get('config'),previous.get('runtime')}
            if path not in allowed: raise FileNotFoundError
        from product_quiz_publish import Assets
        assets=Assets()
        try:
            response=assets.client.get_object(Bucket=assets.bucket,Key='product-quiz/'+path)
        except Exception as exc:
            if getattr(exc,'response',{}).get('Error',{}).get('Code') in ('NoSuchKey','404'): raise FileNotFoundError from None
            raise
        body=response['Body']
        try: data=body.read(250001)
        finally: body.close()
    if len(data)>250000: raise ValueError('Public quiz asset exceeds its size limit')
    result={'body':data,'etag':'"'+hashlib.sha256(data).hexdigest()+'"','expires':at+(3600 if immutable else 30)}
    with _LOCK:
        if len(_ASSETS)>=64:
            oldest=min(_ASSETS,key=lambda k:_ASSETS[k]['expires']);_ASSETS.pop(oldest,None)
        _ASSETS[path]=result
    return result


async def asset(request):
    path=request.path_params.get('asset','')
    headers={'Access-Control-Allow-Origin':'*','Access-Control-Allow-Methods':'GET, HEAD, OPTIONS',
             'Access-Control-Allow-Headers':'If-None-Match','Access-Control-Expose-Headers':'ETag',
             'X-Content-Type-Options':'nosniff','Cache-Control':'no-store'}
    if not _PUBLIC_PATH.fullmatch(path): return Response(status_code=404,headers=headers)
    if request.method=='OPTIONS': return Response(status_code=204,headers=headers)
    try:
        result=await run_in_threadpool(public_bytes,path)
        headers['ETag']=result['etag']
        headers['Cache-Control']='public,max-age=31536000,immutable' if re.search(r'/[a-f0-9]{24}\.',path) else 'public,max-age=60,must-revalidate'
        candidates=request.headers.get('if-none-match','').split(',')
        if any(tag.strip()=='*' or tag.strip().removeprefix('W/')==result['etag'] for tag in candidates):
            return Response(status_code=304,headers=headers)
        headers['Content-Length']=str(len(result['body']))
        return Response(b'' if request.method=='HEAD' else result['body'],headers=headers,
                        media_type='text/javascript' if path.endswith('.js') else 'application/json')
    except FileNotFoundError: return Response(status_code=404,headers=headers)
    except Exception: return Response(status_code=503,headers=headers)


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


ROUTES=(('/api/product-quiz/events',ingest,('POST','OPTIONS')),
        ('/product-quiz/{asset:path}',asset,('GET','HEAD','OPTIONS')))
