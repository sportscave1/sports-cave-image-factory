"""Public configuration and script only; never exposes admin/session data."""
from pathlib import Path
import hashlib
import json

from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse, Response

from image_protection import DEFAULTS, public_policy

ALLOWED_ORIGINS = frozenset(('https://www.sportscaveshop.com','https://sportscaveshop.com'))
SCRIPT = Path(__file__).with_name('storefront-protection.js').read_text(encoding='utf-8')
ASSETS = Path(__file__).parent / 'shopify_theme' / 'assets'


async def config(request):
    origin = request.headers.get('origin','')
    if origin and origin not in ALLOWED_ORIGINS:
        return JSONResponse({'error':'Origin not allowed'},status_code=403)
    headers={'Cache-Control':'public, max-age=30','X-Content-Type-Options':'nosniff','Vary':'Origin'}
    if origin:
        headers['Access-Control-Allow-Origin']=origin
    if request.method=='OPTIONS':
        headers['Access-Control-Allow-Methods']='GET, OPTIONS'
        return Response(status_code=204,headers=headers)
    try:
        values=await run_in_threadpool(public_policy)
    except Exception:
        # Safe baseline is explicit; operators see storage failures in private UI.
        values={**DEFAULTS, 'enabled':False}
        headers['Cache-Control']='no-store'
    etag='"'+hashlib.sha256(json.dumps(values,sort_keys=True).encode()).hexdigest()+'"'
    headers['ETag']=etag
    if request.headers.get('if-none-match') == etag:
        return Response(status_code=304,headers=headers)
    return JSONResponse(values,headers=headers)


async def script(request):
    return Response(SCRIPT,media_type='application/javascript',headers={
        'Cache-Control':'public, max-age=300','X-Content-Type-Options':'nosniff',
        'Access-Control-Allow-Origin':'*',
    })


async def runtime(request):
    return Response((ASSETS / 'sports-cave-image-protection.js').read_text(encoding='utf-8'),media_type='application/javascript',headers={'Cache-Control':'public, max-age=300','X-Content-Type-Options':'nosniff'})


async def stylesheet(request):
    return Response((ASSETS / 'sports-cave-image-protection.css').read_text(encoding='utf-8'),media_type='text/css',headers={'Cache-Control':'public, max-age=300','X-Content-Type-Options':'nosniff'})


ROUTES=(('/api/storefront-protection/config',config,('GET','OPTIONS')),('/storefront-protection.js',script,('GET',)),('/storefront-protection-runtime.js',runtime,('GET',)),('/storefront-protection.css',stylesheet,('GET',)))
