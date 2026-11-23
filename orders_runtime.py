"""Bounded token-scoped diagnostics, separate from workflow/permit records."""
import hmac,json,re
from datetime import datetime,timezone,timedelta
from threading import BoundedSemaphore
from companion_poll_transaction import connection
import prodigi_preparation as prep

SLOTS=BoundedSemaphore(1)
PREFIX='orders_runtime:'
LABELS={'signin':'Prodigi sign-in needed · orders resume automatically','received':'Companion received this step','download':'Downloading verified JPG','open':'Opening saved order','readback':'Verifying saved supplier state','retrying':'Retrying a temporary connection failure',
 'page':'Checking order page','row':'Waiting for exact product','editor':'Opening image editor','reset-image':'Replacing authorised artwork',
 'picker':'Opening image picker','transfer':'Transferring numbered JPG','uploaded':'Waiting for image processing',
 'orientation':'Checking orientation and fit','permit':'Verifying Save permission','save':'Saving artwork',
 'product':'Waiting for exact product','product-search':'Finding mapped product','product-select':'Selecting mapped variant',
 'product-readback':'Verifying saved variant','product-row':'Checking product and image quality',
 'inserts':'Checking saved packing inserts','shipping':'Checking shipping and price','tax-declaration':'Checking tax declaration'}
KINDS={'product':('product_browser',{'Selecting product'}),'artwork':('browser',{'Browser uploading'}),
       'qa':('dashboard_qa',{'Checking dashboard QA'})}

def version(value):
    return value if isinstance(value,str) and re.fullmatch(r'1\.\d{1,3}\.\d{1,3}',value) else ''

def record_version(value):
    if not version(value):return
    with connection(prep.connect,slots=SLOTS) as conn,conn.cursor() as cur:
        cur.execute("""INSERT INTO app_settings(key,value,updated_at) VALUES('orders_companion_runtime',%s::jsonb,now())
          ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=now()
          WHERE app_settings.updated_at<now()-interval '20 seconds' OR app_settings.value->>'version'<>excluded.value->>'version'""",
          (json.dumps(dict(version=value,seen_at=prep.now())),))

def progress(data):
    if not isinstance(data,dict) or set(data)!={'key','token','kind','stage','elapsed_ms','sequence','version','attempt','retry_in_ms'}:
        raise ValueError('Invalid progress record.')
    key=data['key'];kind=data['kind'];stage=data['stage']
    if (not isinstance(key,str) or not re.fullmatch(r'(?:product:)?prodigi_prepare:\d+',key)
        or not isinstance(kind,str) or kind not in KINDS or not isinstance(stage,str) or stage not in LABELS or not version(data['version'])
        or not isinstance(data['token'],str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}',data['token'])
        or type(data['sequence']) is not int or not 1<=data['sequence']<=100000
        or type(data['elapsed_ms']) is not int or not 0<=data['elapsed_ms']<=3600000
        or type(data['attempt']) is not int or not 0<=data['attempt']<=2
        or type(data['retry_in_ms']) is not int or not 0<=data['retry_in_ms']<=5000):raise ValueError('Invalid progress identity.')
    if key.startswith('product:')!=(kind=='product'):raise ValueError('Progress scope differs.')
    key=key.removeprefix('product:');field,states=KINDS[kind]
    digest=prep.digest(data['token']);stamp=prep.now()
    with connection(prep.connect,slots=SLOTS) as conn,conn.cursor() as cur:
        # Diagnostics are not workflow authority. A shared preparation-row lock
        # here conflicts with the permit's FOR UPDATE NOWAIT safety fence.
        # Late telemetry is hidden by public()'s current token/status check.
        cur.execute('SELECT value FROM app_settings WHERE key=%s',(key,));row=cur.fetchone()
        value=row['value'] if row else {};receipt=value.get(field) or {}
        if value.get('status') not in states or not hmac.compare_digest(receipt.get('token_hash',''),digest):
            raise PermissionError('Retired progress handoff.')
        runtime_key=PREFIX+key.split(':')[-1]
        cur.execute('SELECT value FROM app_settings WHERE key=%s FOR UPDATE',(runtime_key,));previous=cur.fetchone()
        previous=previous['value'] if previous else {}
        if previous.get('claim')==digest and previous.get('sequence',0)>=data['sequence']:return {'recorded':False}
        history=previous.get('timings',[]) if previous.get('claim')==digest else []
        if previous.get('claim')==digest and previous.get('stage')!=stage:
            history=history+[dict(stage=previous['stage'],elapsed_ms=max(0,data['elapsed_ms']-previous.get('stage_entered_ms',0)))]
        entered=previous.get('stage_entered_ms',0) if previous.get('claim')==digest and previous.get('stage')==stage else data['elapsed_ms']
        saved=dict(claim=digest,kind=kind,stage=stage,label=LABELS[stage],elapsed_ms=data['elapsed_ms'],
            sequence=data['sequence'],version=data['version'],seen_at=stamp,stage_entered_ms=entered,timings=history[-24:],
            attempt=data['attempt'],next_retry_at=(datetime.now(timezone.utc)+timedelta(milliseconds=data['retry_in_ms'])).isoformat() if data['retry_in_ms'] else None)
        cur.execute('INSERT INTO app_settings(key,value,updated_at) VALUES(%s,%s::jsonb,now()) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=now()',
            (runtime_key,json.dumps(saved)))
    return {'recorded':True}

def public(value,record):
    field,states=KINDS.get(record.get('kind'),('',set()))
    if value.get('status') not in states or (value.get(field) or {}).get('token_hash')!=record.get('claim'):return {}
    result={k:record.get(k) for k in ('kind','stage','label','elapsed_ms','version','seen_at','timings','attempt','next_retry_at')}
    try:delayed=(datetime.now(timezone.utc)-datetime.fromisoformat(record['seen_at'])).total_seconds()>90
    except (ValueError,KeyError,TypeError):delayed=True
    result['delayed']=delayed
    if delayed:result['label']='Waiting for companion · last step: '+LABELS.get(record.get('stage'),'Verification')
    return result

def metrics():
    """On-demand bounded aggregate; no order/customer identifiers returned."""
    import math
    with connection(prep.connect,slots=SLOTS) as conn,conn.cursor() as cur:
        cur.execute("""SELECT value->>'status' AS status,value->'stage_durations' AS durations,
            value->'stage_timing'->>'entered_at' AS entered_at FROM app_settings
            WHERE key LIKE 'prodigi_prepare:%%' ORDER BY updated_at DESC LIMIT 500""")
        rows=cur.fetchall()
        cur.execute("SELECT value FROM app_settings WHERE key='orders_companion_runtime'");seen=cur.fetchone()
    stages={};states={};ages=[]
    for row in rows:
        state=row.get('status') or 'Unknown';states[state]=states.get(state,0)+1
        for sample in row.get('durations') or []:
            if isinstance(sample,dict) and isinstance(sample.get('stage'),str) and type(sample.get('elapsed_ms')) is int and sample['elapsed_ms']>=0:
                stages.setdefault(sample['stage'],[]).append(sample['elapsed_ms'])
        if state in ('Queued','Preparing JPG','Awaiting product selection','Awaiting browser upload','Awaiting dashboard QA'):
            try:ages.append(max(0,(datetime.now(timezone.utc)-datetime.fromisoformat(row['entered_at'])).total_seconds()))
            except (TypeError,ValueError):pass
    result={}
    for stage,values in stages.items():
        values.sort();result[stage]=dict(samples=len(values),p50_ms=values[max(0,math.ceil(len(values)*.5)-1)],p95_ms=values[max(0,math.ceil(len(values)*.95)-1)])
    return dict(sample_limit=500,sampled_orders=len(rows),states=states,stages=result,oldest_ready_wait_s=round(max(ages,default=0),1),
        companion=(seen or {}).get('value',{}))

async def metrics_endpoint(request):
    from files_upload_api import _request_user
    from product_upload_api import HEADERS,failure
    from starlette.concurrency import run_in_threadpool
    from starlette.responses import JSONResponse
    try:
        user=await run_in_threadpool(_request_user,request,required_page='Orders');prep.require_user(user)
        return JSONResponse(await run_in_threadpool(metrics),headers=HEADERS)
    except Exception as error:return failure(error)

async def endpoint(request):
    from prodigi_preparation_api import desktop
    from product_upload_api import HEADERS,failure
    from starlette.concurrency import run_in_threadpool
    from starlette.responses import JSONResponse
    try:
        auth=request.headers.get('authorization','')
        if not re.fullmatch(r'Bearer [A-Za-z0-9_-]{43}',auth):raise PermissionError('Pair this desktop first.')
        raw=bytearray()
        async for block in request.stream():
            raw.extend(block)
            if len(raw)>2048:raise ValueError('Progress record too large.')
        data=json.loads(raw)
        await run_in_threadpool(desktop,auth[7:],slots=SLOTS)
        return JSONResponse(await run_in_threadpool(progress,data),headers=HEADERS)
    except Exception as error:return failure(error)
