"""Same-origin session transport: HttpOnly cookie, durable lock and revocation."""
import os
import time
from urllib.parse import urlsplit
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
import os_accounts
import sc_auth
from security_protection import STORE, session_key


def same_origin(request):
    origin=request.headers.get('origin','')
    try:
        parts=urlsplit(origin)
        return bool(origin and parts.scheme in ('https','http') and parts.netloc==request.headers.get('host','') and not parts.username and not parts.path and not parts.query and not parts.fragment)
    except ValueError:
        return False


def identity(token):
    valid,_,payload=sc_auth.validate_user_auth_token(token,extra_secret=os.getenv('SPORTS_CAVE_AUTH_SECRET',''))
    if not valid:raise PermissionError('Sign in required.')
    user=os_accounts.DEFAULT_STORE.get_user(payload['sub'])
    if not os_accounts.account_is_active(user) or int(user.get('session_version') or 1)!=payload['sv']:
        raise PermissionError('Account access expired.')
    return user,payload


async def session(request):
    if not same_origin(request):return JSONResponse({'error':'Same-origin request required.'},status_code=403)
    # A real body bound, independent of untrusted Content-Length.
    body=bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body)>4096:return JSONResponse({'error':'Request too large.'},status_code=413)
    import json
    try:
        payload=json.loads(body)
        if not isinstance(payload,dict) or set(payload)-{'token','grant','password','action','remember'}:raise ValueError()
        if any(key in payload and not isinstance(payload[key],str) for key in ('token','grant','password','action')):raise ValueError()
        if 'remember' in payload and type(payload['remember']) is not bool:raise ValueError()
        token=payload.get('token') or request.cookies.get(sc_auth.AUTH_COOKIE_NAME,'')
        if payload.get('grant'):
            claims=await run_in_threadpool(STORE.consume_cookie_handoff,str(payload['grant']))
            token=sc_auth.sign_user_auth_claims(claims,extra_secret=os.getenv('SPORTS_CAVE_AUTH_SECRET',''))
        user,claims=await run_in_threadpool(identity,token)
        sid=session_key(token)
        action=payload.get('action','register')
        if action=='register':
            await run_in_threadpool(STORE.register,token,claims,user,request.headers.get('user-agent',''))
            await run_in_threadpool(STORE.validate_session,sid,user['id'])
            await run_in_threadpool(STORE.q,'UPDATE os_security_sessions SET device=%s WHERE id=%s',(request.headers.get('user-agent','')[:200],sid))
        elif action=='reauth':
            await run_in_threadpool(STORE.reauthenticate,user['id'],sid,str(payload.get('password','')))
        elif action=='activity':
            await run_in_threadpool(STORE.validate_session,sid,user['id'],touch=True)
        elif action=='lock':
            await run_in_threadpool(STORE.q,'UPDATE os_security_sessions SET locked_at=now() WHERE id=%s AND user_id=%s AND revoked_at IS NULL',(sid,user['id']))
            await run_in_threadpool(STORE.audit,'AUTO_LOCK',user['id'],session_id=sid)
        elif action=='logout':
            await run_in_threadpool(STORE.q,'UPDATE os_security_sessions SET revoked_at=now() WHERE id=%s AND user_id=%s',(sid,user['id']))
            await run_in_threadpool(STORE.audit,'LOGOUT',user['id'],session_id=sid)
        else:raise ValueError()
        response=JSONResponse({'ok':True},headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})
        if action=='register':
            response.set_cookie(sc_auth.AUTH_COOKIE_NAME,token,httponly=True,secure=bool(os.getenv('RENDER')) or request.url.scheme=='https',samesite='lax',max_age=sc_auth.auth_cookie_max_age() if payload.get('remember',True) else None)
        if action=='logout':response.delete_cookie(sc_auth.AUTH_COOKIE_NAME,httponly=True,samesite='lax')
        return response
    except PermissionError as error:return JSONResponse({'error':str(error)},status_code=423,headers={'Cache-Control':'no-store'})
    except (ValueError,TypeError,KeyError):return JSONResponse({'error':'Invalid session request.'},status_code=400)
    except Exception:return JSONResponse({'error':'Session verification temporarily unavailable.'},status_code=503)


ROUTES=(('/api/os/security/session',session,('POST',)),)
