"""Same-origin OS panel and outbound helper transport; no browser control on Render."""
import asyncio
import json
import os
import time
from collections import defaultdict, deque
from pathlib import Path
from starlette.concurrency import run_in_threadpool
from starlette.responses import HTMLResponse, JSONResponse, Response
from .relay_store import Relay
from .schema import Invalid
from .state_updates import task_changes

ROOT = Path(__file__).resolve().parents[1]
HEADERS = {"Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff",
           "Referrer-Policy":"no-referrer","X-Frame-Options":"SAMEORIGIN"}
_events = {}
_limits = defaultdict(deque)

def event(key):
    return _events.setdefault(key,asyncio.Event())

def wake(key):
    previous=_events.pop(key,None)
    if previous: previous.set()

def relay(request):
    configured=getattr(request.app.state,"recorder_relay",None)
    if configured: return configured
    import os_accounts
    import supabase_backend
    return Relay(supabase_backend.connect,os_accounts.DEFAULT_STORE)

def same_origin(request):
    origin=request.headers.get("origin","")
    expected="https://sports-cave-image-factory.onrender.com" if os.environ.get("RENDER") else str(request.base_url).rstrip("/")
    if origin.rstrip("/")!=expected:
        raise PermissionError("Request origin rejected.")

def current_admin(request):
    # Reuse the account cookie/signature/session-version contract; do not accept
    # the legacy master-password cookie for device enrollment or control.
    import sc_auth,os_accounts
    valid,_,claims=sc_auth.validate_user_auth_token(
        request.cookies.get(sc_auth.AUTH_COOKIE_NAME,""),
        extra_secret=os.environ.get("SPORTS_CAVE_AUTH_SECRET","").strip())
    if not valid: raise PermissionError("Sign in to Sports Cave OS.")
    user=relay(request).users.get_user(claims.get("sub"))
    if (not user or str(user.get("id"))!=str(claims.get("sub")) or
        int(user.get("session_version",1))!=int(claims.get("sv",1)) or
        not os_accounts.is_admin(user) or not os_accounts.account_is_active(user)):
        raise PermissionError("An active administrator account is required.")
    return user

async def actor(request,write=False):
    if write: same_origin(request)
    return await run_in_threadpool(current_admin,request)

async def body(request):
    if request.headers.get("content-type","").split(";")[0]!="application/json":
        raise Invalid("JSON required.")
    content=bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content)>256000: raise Invalid("Request is too large.")
    try: result=json.loads(content)
    except ValueError: raise Invalid("Invalid JSON.")
    if not isinstance(result,dict): raise Invalid("Expected an object.")
    return result

def failure(error):
    status=403 if isinstance(error,PermissionError) else 409 if isinstance(error,ValueError) else 503
    detail={"error":str(error) if status!=503 else "Recorder connection is unavailable. Try again shortly."}
    if status==409 and getattr(error,"step_errors",None):detail["step_errors"]=error.step_errors
    return JSONResponse(detail,status_code=status,headers=HEADERS)

def bounded(endpoint):
    async def wrapped(request):
        try: return await endpoint(request)
        except asyncio.CancelledError: raise
        except Exception as error: return failure(error)
    return wrapped

@bounded
async def panel(request):
    await actor(request)
    headers={**HEADERS,"Content-Security-Policy":"default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'self'; base-uri 'none'; form-action 'self'"}
    return HTMLResponse((ROOT/"task_recorder/panel.html").read_text(encoding="utf-8"),headers=headers)

@bounded
async def asset(request):
    await actor(request)
    name=request.path_params["name"]
    if name not in {"panel.js","panel.css","editor.js"}: raise Invalid("Unknown asset.")
    return Response((ROOT/"task_recorder"/name).read_bytes(),media_type="text/javascript" if name.endswith(".js") else "text/css",headers=HEADERS)

@bounded
async def state(request):
    user=await actor(request)
    device_id=request.query_params.get("device","")
    signal=event("state:"+device_id)
    rows=await run_in_threadpool(relay(request).devices,str(user["id"]))
    selected=next((d for d in rows if d["id"]==device_id),None)
    if selected and request.query_params.get("after")==str(selected["seq"]) and request.query_params.get("wait")!="0":
        try: await asyncio.wait_for(signal.wait(),timeout=20)
        except asyncio.TimeoutError: pass
        await actor(request)
        rows=await run_in_threadpool(relay(request).devices,str(user["id"]))
    compact=request.query_params.get("compact")
    if selected and compact in {"1","2"}:
        condensed=[]
        for row in rows:
            if row["id"]!=device_id:
                condensed.append({k:v for k,v in row.items() if k!="state"} if compact=="2" else row);continue
            metadata={k:v for k,v in row.items() if k!="state"}
            if request.query_params.get("after")==str(row["seq"]):
                condensed.append(metadata)
            elif compact=="2" and request.query_params.get("after")==str(selected["seq"]):
                # The held poll's initial snapshot is the exact client baseline.
                # No per-client history/cache is required; missed baselines fall
                # back to full state, including across server restarts.
                previous=selected["state"];current=row["state"]
                metadata["state_delta"]={"base_seq":selected["seq"],
                    "changes":{k:v for k,v in current.items() if k!="tasks" and previous.get(k)!=v},
                    "tasks":task_changes(previous.get("tasks",[]),current.get("tasks",[]))}
                condensed.append(metadata)
            else:condensed.append(row)
        rows=condensed
    return JSONResponse({"devices":rows,"compact":2},headers=HEADERS)

@bounded
async def pairing(request):
    user=await actor(request,True)
    return JSONResponse(await run_in_threadpool(relay(request).challenge,str(user["id"])),headers=HEADERS)

def rate(request):
    key=request.client.host if request.client else "unknown"
    now=time.monotonic()
    queue=_limits[key]
    while queue and queue[0]<now-300: queue.popleft()
    if len(queue)>=30: raise PermissionError("Too many pairing attempts. Wait a few minutes.")
    queue.append(now)

@bounded
async def inspect_pair(request):
    rate(request)
    data=await body(request)
    return JSONResponse(await run_in_threadpool(relay(request).inspect_pair,data.get("code")),headers=HEADERS)

@bounded
async def claim(request):
    rate(request)
    data=await body(request)
    result=await run_in_threadpool(relay(request).claim,data.get("code"),data.get("device_id"),data.get("key"),data.get("name"))
    wake("state:")
    return JSONResponse(result,headers=HEADERS)

@bounded
async def revoke(request):
    user=await actor(request,True)
    data=await body(request)
    await run_in_threadpool(relay(request).revoke,str(user["id"]),data.get("device_id"))
    wake("cmd:"+str(data.get("device_id")));wake("state:"+str(data.get("device_id")))
    return JSONResponse({"revoked":True},headers=HEADERS)

@bounded
async def command(request):
    user=await actor(request,True)
    data=await body(request)
    result=await run_in_threadpool(relay(request).enqueue,str(user["id"]),data.get("device_id"),
                                   data.get("id"),data.get("kind"),data.get("payload",{}))
    wake("cmd:"+str(data.get("device_id")))
    return JSONResponse(result,headers=HEADERS)

@bounded
async def receipt(request):
    user=await actor(request)
    device_id=request.query_params.get("device")
    command_id=request.query_params.get("id")
    signal=event("state:"+str(device_id))
    result=await run_in_threadpool(relay(request).receipt,str(user["id"]),device_id,command_id)
    if request.query_params.get("wait")=="1" and result["status"] in {"queued","dispatched"}:
        try:await asyncio.wait_for(signal.wait(),timeout=15)
        except asyncio.TimeoutError:pass
        user=await actor(request)
        result=await run_in_threadpool(relay(request).receipt,str(user["id"]),device_id,command_id)
    return JSONResponse(result,headers=HEADERS)

@bounded
async def exchange(request):
    data=await body(request)
    authorization=request.headers.get("authorization","")
    if not authorization.startswith("Bearer ") or len(authorization)>200:
        raise PermissionError("Paired device credential required.")
    key=authorization[7:]
    device_id=data.get("device_id")
    signal=event("cmd:"+str(device_id))
    result=await run_in_threadpool(relay(request).exchange,device_id,key,data)
    wake("state:"+str(device_id))
    if not result["commands"] and data.get("wait"):
        try: await asyncio.wait_for(signal.wait(),timeout=15)
        except asyncio.TimeoutError: pass
        # Never overwrite a newer state push with the original long-poll body.
        result=await run_in_threadpool(relay(request).exchange,device_id,key,
                    {"boot_id":data["boot_id"],"epoch":data["epoch"]})
    return JSONResponse(result,headers=HEADERS)

@bounded
async def setup(request):
    await actor(request)
    from .release import build_package, verify_archive
    package = os.environ.get("SPORTS_CAVE_RECORDER_WINDOWS_PACKAGE")
    reviewed = ROOT / "recorder-releases/windows/SportsCaveTaskRecorder.zip"
    if not package and reviewed.is_file():
        package = str(reviewed)
    native = ROOT / "windows-screen-recorder/native/bin/DesktopRecorder.exe"
    if package:
        data = Path(package).read_bytes()
        verify_archive(data)
    elif native.is_file():
        data = await run_in_threadpool(build_package, ROOT, native)
    else:
        return JSONResponse({"error":"The reviewed Windows recorder package is not available yet."},status_code=503,headers=HEADERS)
    return Response(data,media_type="application/zip",headers={**HEADERS,"Content-Disposition":'attachment; filename="SportsCaveTaskRecorder.zip"'})

ROUTES = (
 ("/task-recorder/panel",panel,("GET",)),
 ("/task-recorder/assets/{name}",asset,("GET",)),
 ("/api/task-recorder/state",state,("GET",)),
 ("/api/task-recorder/pairing",pairing,("POST",)),
 ("/api/task-recorder/pairing/inspect",inspect_pair,("POST",)),
 ("/api/task-recorder/pairing/claim",claim,("POST",)),
 ("/api/task-recorder/revoke",revoke,("POST",)),
 ("/api/task-recorder/command",command,("POST",)),
 ("/api/task-recorder/receipt",receipt,("GET",)),
 ("/api/task-recorder/device/exchange",exchange,("POST",)),
 ("/task-recorder/setup.zip",setup,("GET",)),
)
