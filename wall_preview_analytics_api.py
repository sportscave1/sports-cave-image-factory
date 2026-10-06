"""Small first-party ingest plus authenticated Social Media analytics reads."""
import json
from starlette.responses import JSONResponse,Response
from starlette.concurrency import run_in_threadpool
from fastapi.encoders import jsonable_encoder
import wall_preview_api as archive
import wall_preview_analytics as analytics

async def ingest(request):
    origin=archive._origin(request);headers=archive._cors_headers(origin)
    if origin not in archive._allowed_origins():return Response(status_code=403,headers=headers)
    if request.method=='OPTIONS':return Response(status_code=204,headers=headers)
    body=bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body)>8192:return JSONResponse({'ok':False},status_code=413,headers=headers)
    try:
        payload=json.loads(body)
        clean=analytics.clean(payload)
        # Use the supplied random session for an in-memory abuse limit. No IP collection.
        if not archive._rate_allowed('analytics:'+clean['session_id'],limit=300):return Response(status_code=429,headers=headers)
        inserted=await run_in_threadpool(analytics.ingest,payload)
        return JSONResponse({'ok':True,'duplicate':not inserted},headers=headers)
    except (ValueError,TypeError,AttributeError):return JSONResponse({'ok':False},status_code=400,headers=headers)
    except PermissionError:return JSONResponse({'ok':False},status_code=403,headers=headers)
    except Exception:return JSONResponse({'ok':False},status_code=503,headers=headers)


def authorize(request):
    import os,sc_auth,os_accounts,social_media
    token=request.cookies.get(sc_auth.AUTH_COOKIE_NAME,'')
    valid,_,claims=sc_auth.validate_user_auth_token(token,extra_secret=os.getenv('SPORTS_CAVE_AUTH_SECRET','').strip())
    if not valid:raise PermissionError('Access denied')
    user=os_accounts.DEFAULT_STORE.get_user(claims.get('sub'))
    if not os_accounts.account_is_active(user) or int(user.get('session_version') or 1)!=int(claims.get('sv') or 1):
        raise PermissionError('Access denied')
    if not os_accounts.can_access_page(user,social_media.SOCIAL_MEDIA_ROUTE):raise PermissionError('Access denied')
    return user

async def read(request):
    headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}
    try:
        await run_in_threadpool(authorize,request)
        section=request.path_params['section']
        if section not in ('summary','funnel','products','events'):return Response(status_code=404)
        params=dict(request.query_params)
        data=await run_in_threadpool(analytics.events if section=='events' else analytics.report,params)
        return JSONResponse(jsonable_encoder(data if section=='events' else data[section]),headers=headers)
    except PermissionError:return JSONResponse({'error':'Access denied'},status_code=403,headers=headers)
    except (ValueError,TypeError):return JSONResponse({'error':'Invalid filters'},status_code=400,headers=headers)
    except Exception:return JSONResponse({'error':'Analytics unavailable'},status_code=503,headers=headers)

ROUTES=(('/api/wall-previews/analytics/events',ingest,('POST','OPTIONS')),
        ('/api/wall-previews/analytics/{section}',read,('GET',)))
