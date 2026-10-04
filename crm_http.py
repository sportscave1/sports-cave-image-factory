"""Lazy FastAPI handlers mounted in the existing webhook service."""
import json
import os
from html import escape
from fastapi import APIRouter,Request,Response
from fastapi.responses import HTMLResponse
from starlette.concurrency import run_in_threadpool

router=APIRouter()


@router.api_route('/shopify/customer-events',methods=['POST','OPTIONS'])
async def app_pixel_event(request:Request):
    from crm_store import Store
    from crm_shopify_pixel import record
    from crm_onsite import allow_rate
    origin=request.headers.get('origin','')
    store=Store()
    try:state=await run_in_threadpool(store.state,'shopify_automation_pixel')
    except Exception:return Response(status_code=503)
    if not state.get('id'):return Response(status_code=404)
    # Shopify app pixels run in a strict worker sandbox. They can have null
    # Origin. This telemetry has no trusted identity or dispatch privileges.
    allowed={'null','https://'+os.getenv('SHOPIFY_STORE_DOMAIN','')}
    allowed.update(state.get('origins',[]))
    allowed.update(v.strip() for v in os.getenv('CRM_WEBSITE_ALLOWED_ORIGINS','').split(',') if v.strip())
    if origin not in allowed:return Response(status_code=403)
    cors={'Access-Control-Allow-Origin':origin,'Vary':'Origin','Access-Control-Allow-Methods':'POST, OPTIONS','Access-Control-Allow-Headers':'Content-Type','Cache-Control':'no-store'}
    if request.method=='OPTIONS':return Response(status_code=204,headers=cors)
    if not allow_rate(request.client.host if request.client else 'unknown'):return Response(status_code=429,headers=cors)
    if request.headers.get('content-type','').split(';')[0]!='application/json':return Response(status_code=415,headers=cors)
    try:
        await run_in_threadpool(record,store,json.loads(await bounded_body(request,4096)),state)
        return Response(status_code=202,headers=cors)
    except (ValueError,TypeError):return Response(status_code=400,headers=cors)
    except Exception:return Response(status_code=503,headers=cors)


@router.api_route('/crm/tracking/events',methods=['POST','OPTIONS'])
async def website_event(request:Request):
    from crm_onsite import config,allow_rate,record_event
    from crm_store import Store
    cfg=config();origin=request.headers.get('origin','')
    if not cfg['enabled'] or not cfg['configured']:return Response(status_code=404)
    if origin not in cfg['origins']:return Response(status_code=403)
    cors={'Access-Control-Allow-Origin':origin,'Vary':'Origin','Access-Control-Allow-Methods':'POST, OPTIONS',
          'Access-Control-Allow-Headers':'Content-Type','Access-Control-Max-Age':'300','Cache-Control':'no-store'}
    if request.method=='OPTIONS':return Response(status_code=204,headers=cors)
    if not allow_rate(request.client.host if request.client else 'unknown'):return Response(status_code=429,headers=cors)
    if request.headers.get('content-type','').split(';')[0]!='application/json':return Response(status_code=415,headers=cors)
    try:
        payload=json.loads(await bounded_body(request,4096))
        await run_in_threadpool(record_event,Store(),payload,cfg)
        return Response(status_code=202,headers=cors)
    except (ValueError,TypeError):return Response(status_code=400,headers=cors)
    except Exception:return Response(status_code=503,headers=cors)

async def bounded_body(request,limit=2*1024*1024):
    raw=bytearray()
    async for part in request.stream():
        raw.extend(part)
        if len(raw)>limit:raise ValueError('Request too large.')
    return bytes(raw)

@router.post('/webhooks/shopify/crm')
async def shopify_hook(request:Request):
    from webhook_server import verify_shopify_webhook_hmac
    from crm_webhooks import receive_shopify
    from crm_store import Store
    from shopify_sync import normalize_store_domain
    try:
        raw=await bounded_body(request)
        if not verify_shopify_webhook_hmac(raw,request.headers)['ok']:return Response(status_code=401)
        expected=normalize_store_domain(os.getenv('SHOPIFY_STORE_DOMAIN',''))
        if not expected or normalize_store_domain(request.headers.get('x-shopify-shop-domain',''))!=expected:return Response(status_code=403)
        payload=json.loads(raw)
        await run_in_threadpool(receive_shopify,Store(),request.headers.get('x-shopify-topic',''),request.headers.get('x-shopify-event-id') or request.headers.get('x-shopify-webhook-id',''),payload,request.headers.get('x-shopify-triggered-at'),expected)
        return Response(status_code=200)
    except (ValueError,TypeError):return Response(status_code=400)
    except Exception:return Response(status_code=503)

@router.post('/webhooks/resend/crm')
async def resend_hook(request:Request):
    from crm_resend import Config,verify_resend
    from crm_store import Store
    from crm_webhooks import receive_resend
    from crm_resend_event_worker import admission,log
    from time import perf_counter
    started=perf_counter();identity=None;admitted=False
    try:
        raw=await bounded_body(request,128*1024)
        if not verify_resend(raw,request.headers,Config().resend_webhook_secret):return Response(status_code=401)
        identity=request.headers['svix-id']
        admitted=admission.acquire(blocking=False)
        if not admitted:
            await run_in_threadpool(log,'backpressure')
            return Response(status_code=503)
        await run_in_threadpool(log,'received')
        await run_in_threadpool(receive_resend,Store(),identity,json.loads(raw),defer=True)
        await run_in_threadpool(log,'acknowledged',duration_ms=round((perf_counter()-started)*1000,1))
        return Response(status_code=200)
    except (ValueError,TypeError):return Response(status_code=400)
    except Exception as exc:
        await run_in_threadpool(log,'processing_failed',error_type=type(exc).__name__)
        return Response(status_code=503)
    finally:
        if admitted:admission.release()

@router.get('/crm/unsubscribe')
async def unsubscribe_page(token:str=''):
    from crm_resend import Config
    if not Config().verify_token(token):return Response('Invalid unsubscribe link.',status_code=400)
    # GET is a confirmation only: link scanners must not unsubscribe recipients.
    return HTMLResponse('<!doctype html><title>Sports Cave · Unsubscribe</title><main style="font:16px Arial;max-width:480px;margin:12vh auto;padding:24px"><h2>Sports Cave</h2><p>Stop Sports Cave marketing emails?</p><form method="post" action="?token='+escape(token,quote=True)+'"><button type="submit">Unsubscribe</button></form></main>',headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})

@router.api_route('/crm/unsubscribe/test',methods=['GET','POST'])
async def unsubscribe_test():
    return unsubscribe_confirmation('This is a test unsubscribe link. No subscription has been changed.')

def unsubscribe_confirmation(message):
    return HTMLResponse('<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><title>Sports Cave · Unsubscribe</title>'
        '<main style="font:16px Arial;max-width:480px;margin:12vh auto;padding:28px;border-top:3px solid #c9a33f;color:#171717">'
        '<h2>Sports Cave</h2><p>'+escape(message)+'</p></main>',headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})

@router.post('/crm/unsubscribe')
async def unsubscribe_post(token:str=''):
    from crm_resend import Config
    from crm_store import Store
    from crm_webhooks import unsubscribe
    try:
        await run_in_threadpool(unsubscribe,Store(),Config(),token)
        return unsubscribe_confirmation("You've been unsubscribed. You won't receive marketing emails from Sports Cave.")
    except ValueError:return Response('Invalid unsubscribe link.',status_code=400)
    except Exception:return Response('Please try again shortly.',status_code=503)
