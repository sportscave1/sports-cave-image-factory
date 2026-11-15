"""Local-only recorder benchmark. Never imports credentials or installed helper data.

Run with the shared test venv, from this repository:
python -m scripts.benchmark_task_recorder --variant before --recorder-source <baseline-package-parent>
python -m scripts.benchmark_task_recorder --variant after

Both use a full isolated OS preview on 18966, helper on 18936, synthetic local
PostgreSQL, fresh profiles, 40 task summaries, 3 latency samples and 60s windows.
Body bytes only: excludes TLS/HTTP headers, OS assets and unrelated companions.
"""
import argparse
import asyncio
import contextlib
import ctypes
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import threading
import time
from urllib.request import Request,urlopen
import uuid

REPO=Path(__file__).resolve().parents[1]
BASE=Path.home()/"AppData/Local/SportsCaveOS/TaskRecorderMeasured-64cdf0b0"
SITE="http://127.0.0.1:18966"
LOCAL="http://127.0.0.1:18936"

def emit(path,kind,**data):
    with path.open("a",encoding="utf-8") as f:f.write(json.dumps({"ts":time.time(),"kind":kind,**data})+"\n")

def memory_mb():
    from ctypes import wintypes as w
    size=ctypes.c_size_t
    class Counters(ctypes.Structure):
        _fields_=[("cb",w.DWORD),("faults",w.DWORD)]+[(n,size) for n in ("peak","working","pagedpeak","paged","nonpagedpeak","nonpaged","pagefile","pagefilepeak")]
    k=ctypes.WinDLL("kernel32");k.GetCurrentProcess.restype=w.HANDLE
    ps=ctypes.WinDLL("psapi");ps.GetProcessMemoryInfo.argtypes=[w.HANDLE,ctypes.POINTER(Counters),w.DWORD]
    c=Counters();c.cb=ctypes.sizeof(c)
    if not ps.GetProcessMemoryInfo(k.GetCurrentProcess(),ctypes.byref(c),c.cb):raise ctypes.WinError()
    return c.working/1048576

def helper(args):
    sys.path.insert(0,str(args.recorder_source))
    from task_recorder.device import DeviceAgent
    from task_recorder.server import Bridge
    from task_recorder.runner import Runner
    from playwright.async_api import BrowserType
    out=args.out;out.mkdir(parents=True,exist_ok=True);metrics=out/"helper.jsonl"
    old_exchange=DeviceAgent.exchange;old_apply=DeviceAgent.apply;old_perform=Runner.perform
    async def exchange(self,device,data,wait=False):
        if (out/"cut-connection").exists():
            import httpx
            raise httpx.ConnectError("Synthetic benchmark connection loss")
        started=time.time();result=await old_exchange(self,device,data,wait)
        return result
    # Capture actual serialized HTTP body sizes, including heartbeat/ack traffic.
    import httpx
    old_post=httpx.AsyncClient.post
    async def post(self,url,*a,**kw):
        started=time.time();body=kw.get("json",{});is_exchange=str(url).endswith('/device/exchange')
        try:response=await old_post(self,url,*a,**kw)
        except Exception:
            if is_exchange:emit(metrics,"wire",group="helper",sent=len(json.dumps(body,separators=(",",":")).encode()),received=0,wait=body.get('wait',False),start=started,failed=True)
            raise
        if is_exchange:
            request_headers=len(response.request.method.encode())+len(response.request.url.raw_path)+12+sum(len(k)+len(v)+4 for k,v in response.request.headers.raw)+2
            response_headers=len(response.http_version)+len(response.reason_phrase)+7+sum(len(k)+len(v)+4 for k,v in response.headers.raw)+2
            emit(metrics,"wire",group="helper",sent=len(response.request.content),received=len(response.content),encoded_received=response.num_bytes_downloaded,
                 sent_http=len(response.request.content)+request_headers,received_http=response.num_bytes_downloaded+response_headers,
                 encoding=response.headers.get('content-encoding','identity'),status=response.status_code,wait=body.get('wait',False),start=started,duration=time.time()-started)
        return response
    httpx.AsyncClient.post=post;DeviceAgent.exchange=exchange
    async def apply(self,command):
        emit(metrics,"apply_start",id=command['id'],control=command['kind'])
        await old_apply(self,command)
        status=self.db.execute('SELECT status FROM commands WHERE id=?',(command['id'],)).fetchone()
        emit(metrics,"apply_end",id=command['id'],control=command['kind'],status=status[0] if status else None)
    async def perform(self,step):
        emit(metrics,"action",action=step['action'],index=self.index,operation=getattr(self.store,'run_context',{}).get('operation_id'))
        return await old_perform(self,step)
    DeviceAgent.apply=apply;Runner.perform=perform
    old_launch=BrowserType.launch_persistent_context
    async def launch(self,*a,**kw):
        ctx=await old_launch(self,*a,**kw)
        def response(r):
            if r.url.startswith(LOCAL):emit(metrics,"wire",group="website",sent=len(r.request.post_data_buffer or b''),received=int(r.headers.get('content-length',0)))
        ctx.on('response',response);return ctx
    BrowserType.launch_persistent_context=launch
    bridge=Bridge(out/'helper',18936,preview=True)
    from task_recorder.store import atomic
    from task_recorder.server import protect
    atomic(out/'helper/connection.json',{'origin':bridge.origin,'protected':protect(bridge.token.encode()).hex()})
    async def monitor():
        last=None;cpu=time.process_time();tick=time.time();resource=tick
        while True:
            r=bridge.runner;state=(r.mode,r.index,r.recording,bridge.agent.connected)
            if state!=last:
                emit(metrics,"state",mode=r.mode,index=r.index,recording=r.recording,connected=bridge.agent.connected,operation=bridge.agent.operation_id);last=state
            now=time.time()
            if now-resource>=.5:
                current=time.process_time();emit(metrics,"resource",cpu=100*(current-cpu)/(now-tick),memory_mb=memory_mb(),mode=r.mode)
                cpu=current;tick=now;resource=now
            await asyncio.sleep(.01)
    future=asyncio.run_coroutine_threadsafe(monitor(),bridge.loop)
    try:bridge.serve_forever()
    finally:future.cancel();bridge.close()

def records(path):
    if not path.exists():return []
    rows=[]
    for line in path.read_text(encoding='utf-8').splitlines():
        try:rows.append(json.loads(line))
        except ValueError:pass
    return rows

def stats(values):
    return {"n":len(values),"median":round(statistics.median(values),3),"max":round(max(values),3)} if values else {"n":0}

async def run(args):
    from playwright.async_api import async_playwright
    from task_recorder.server import existing
    out=args.out;out.mkdir(parents=True,exist_ok=False)
    processes=[];logs=[]
    # A separate loopback database preserves the single-administrator invariant
    # and excludes all earlier test devices. Never touch the shared fixture DB.
    import psycopg
    from psycopg import sql
    database="recorder_bench_64cdf0b0_"+args.variant.replace("-","_")
    if not __import__("re").fullmatch("[a-z0-9_]{1,63}",database):raise SystemExit("Invalid benchmark database name.")
    with psycopg.connect("postgresql://postgres:synthetic-recorder-only@127.0.0.1:55439/postgres",autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
    env={k:v for k,v in os.environ.items() if k.upper() in {'PATH','SYSTEMROOT','WINDIR','COMSPEC','PATHEXT','USERPROFILE','APPDATA','LOCALAPPDATA','PROGRAMFILES','PROGRAMFILES(X86)','TEMP','TMP'}}
    env['PYTHONPATH']=str(args.recorder_source)+os.pathsep+str(REPO);env['PYTHONDONTWRITEBYTECODE']='1'
    def start(argv,name):
        log=(out/(name+'.log')).open('w',encoding='utf-8');logs.append(log)
        proc=subprocess.Popen([sys.executable,'-X','utf8',*argv],cwd=REPO,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        processes.append(proc);return proc
    preview=start(['scripts/task_recorder_preview.py','--root',str(out/'preview'),'--port','18966','--recorder-source',str(args.recorder_source),'--benchmark-account',args.variant],'preview')
    hp=start(['scripts/benchmark_task_recorder.py','--helper','--out',str(out),'--recorder-source',str(args.recorder_source)],'helper')
    async def until(fn,timeout=35):
        end=time.time()+timeout
        while time.time()<end:
            result=fn()
            if result:return result
            await asyncio.sleep(.02)
        raise AssertionError('Benchmark condition timed out')
    async def ready():
        for _ in range(100):
            try:
                with urlopen(SITE+'/healthz',timeout=.5):pass
                if existing(out/'helper'):return
            except Exception:pass
            await asyncio.sleep(.2)
        raise AssertionError('Isolated preview/helper failed to start')
    def local(action,data=None):
        site,key=existing(out/'helper')
        with urlopen(Request(site+'/api/'+action,data=None if data is None else json.dumps(data).encode(),headers={'X-Recorder-Key':key,'Content-Type':'application/json'}),timeout=10) as r:return json.load(r)
    hpath=out/'helper.jsonl';ui=[];commands=[];latencies={};windows={};checks={}
    def sample(name,value):latencies.setdefault(name,[]).append(value*1000)
    async def helper_event(kind,after,**fields):
        return await until(lambda:next((e for e in records(hpath) if e['kind']==kind and e['ts']>=after and all(e.get(k)==v for k,v in fields.items())),None))
    try:
        await ready()
        # Identical catalogue/steps across variants. No user's tasks or profile.
        ids=[]
        nav=[{'action':'navigate','value':LOCAL+'/demo/form'},{'action':'fill','locator':{'by':'label','value':'Product name'},'value':'Synthetic sample'},{'action':'wait','locator':{'by':'label','value':'Headline'}},{'action':'wait_url','value':LOCAL+'/demo/form'}]
        controls=nav[:2]+[{'action':'wait','locator':{'by':'text','value':'Unreleased benchmark condition'},'timeout_ms':30000},{'action':'fill','locator':{'by':'label','value':'Headline'},'value':'Must never execute'}]
        active=nav[:1]+[{'action':'fill','locator':{'by':'label','value':'Product name'},'value':'Synthetic '+str(i)} for i in range(30)]+nav[-1:]
        for n in range(40):
            tid=str(uuid.uuid5(uuid.NAMESPACE_URL,'recorder-measurement-'+str(n)));ids.append(tid)
            steps=nav if n!=1 and n!=2 else controls if n==1 else active
            local('save',{'task':{'version':1,'id':tid,'name':('00 Navigation' if n==0 else '01 Controls' if n==1 else '02 Active traffic' if n==2 else 'Synthetic saved '+str(n)),'inputs':[],'steps':steps}})
        async with async_playwright() as pw:
            browser=await pw.chromium.launch(headless=True)
            context=await browser.new_context(viewport={'width':1200,'height':850})
            page=await context.new_page()
            async def track(response):
                if '/api/task-recorder/' in response.url or '/task-recorder/assets/' in response.url:
                    with contextlib.suppress(Exception):
                        body=await response.body();sizes=await response.request.sizes();ui.append({'sent_http':sizes['requestBodySize']+sizes['requestHeadersSize'],'received_http':sizes['responseBodySize']+sizes['responseHeadersSize'],'encoded_received':sizes['responseBodySize'],'encoding':response.headers.get('content-encoding','identity'),'ts':time.time(),'start':response.request.timing['startTime']/1000,'kind':'wire','group':'ui' if '/api/' in response.url else 'ui_assets','sent':len(response.request.post_data_buffer or b''),'received':len(body),'status':response.status})
            def request(req):
                if req.url.endswith('/api/task-recorder/command') and req.method=='POST':
                    d=req.post_data_json;commands.append({'ts':time.time(),'id':d['id'],'control':d['kind']})
            def attach(p):p.on('response',lambda r:asyncio.create_task(track(r)));p.on('request',request)
            attach(page)
            await page.goto(SITE+'/?page=task_recorder')
            await page.get_by_placeholder('Username or email',exact=True).fill('recorder-'+args.variant+'@example.invalid')
            await page.get_by_placeholder('Password',exact=True).fill('RecorderPreview-Only-2026')
            await page.get_by_role('button',name='Sign in',exact=True).click()
            panel=page.frame_locator('iframe[src="/task-recorder/panel"]')
            await panel.locator('#pair').click();await panel.locator('#code').filter(has_text=__import__('re').compile('[A-Z2-9]{4}-')).wait_for()
            code=await panel.locator('#code').inner_text();pc=await context.new_page()
            from urllib.parse import urlencode
            await pc.goto(LOCAL+'/pair#'+urlencode({'origin':SITE,'code':code}))
            await pc.get_by_label('PC name',exact=True).fill('Measured PC')
            await pc.get_by_role('button',name='Continue',exact=True).click();await pc.get_by_role('button',name='Approve connection on this PC',exact=True).click()
            await pc.locator('#message').filter(has_text='PC connected').wait_for();await pc.close()
            await panel.locator('#pc').filter(has_text='Connected').wait_for(timeout=35000)
            auth=await context.storage_state()
            for _ in range(3):
                fresh=await browser.new_context(storage_state=auth,viewport={'width':1200,'height':850});p=await fresh.new_page();attach(p)
                t=time.time();await p.goto(SITE+'/?page=task_recorder')
                pf=p.frame_locator('iframe[src="/task-recorder/panel"]');await pf.locator('#pc').filter(has_text='Connected').wait_for(timeout=30000)
                await pf.locator('#record').wait_for();await until(lambda:True)
                assert await pf.locator('#record').is_enabled();sample('page_usable_ms',time.time()-t);await fresh.close()
            async def control(kind,button):
                t=time.time();await button.click();cmd=await until(lambda:next((c for c in commands if c['ts']>=t and c['control']==kind),None))
                start=await helper_event('apply_start',t,id=cmd['id']);end=await helper_event('apply_end',t,id=cmd['id'])
                assert end['status']=='applied',end
                sample(kind+'_delivery_ms',start['ts']-cmd['ts']);sample(kind+'_ack_ms',end['ts']-t)
                return t,cmd,end
            async def message(text):await panel.locator('#message').filter(has_text=text).wait_for(timeout=30000)
            async def row_play(index,tag):
                row=panel.locator(f'tr[data-task-id="{ids[index]}"]')
                t,cmd,ack=await control('play',row.get_by_role('button',name='Play '+('00 Navigation' if index==0 else '01 Controls' if index==1 else '02 Active traffic'),exact=True))
                first=await helper_event('action',t,operation=cmd['id'],index=0);sample(tag,time.time()-t if not first else first['ts']-t)
                return t,cmd
            if args.wire_only:
                t,cmd=await row_play(0,'wire_warmup_ms');await helper_event('state',t,mode='completed',operation=cmd['id']);await message('Completed')
                begin=time.time()
                for _ in range(3):
                    t,cmd=await row_play(2,'wire_play_ms');await helper_event('state',t,mode='completed',operation=cmd['id']);await message('Completed')
                windows['active_wire']=[begin,time.time()];checks['active_runs']=3
                # Let responses for requests already started inside the measured
                # window finish; new idle requests are excluded by their start time.
                await asyncio.sleep(21)
            else:
                for _ in range(3):
                    # A fresh launch after explicit idle Stop; profile retained.
                    local('stop',{});await asyncio.sleep(2.2)
                    t,cmd=await row_play(0,'cold_play_first_action_ms')
                    done=await helper_event('state',t,mode='completed',operation=cmd['id']);await message('Completed');sample('completion_ui_ms',time.time()-done['ts'])
                    t,cmd=await row_play(0,'warm_play_first_action_ms')
                    done=await helper_event('state',t,mode='completed',operation=cmd['id']);await message('Completed');sample('completion_ui_ms',time.time()-done['ts'])
                for _ in range(3):
                    await panel.locator('#name').fill('Measured navigation recording')
                    await panel.locator('#website').fill(LOCAL+'/demo/form')
                    t,cmd,ack=await control('record',panel.locator('#record'))
                    active_event=await helper_event('state',t,recording=True);sample('record_flag_ms',active_event['ts']-t);sample('record_ready_ms',ack['ts']-t)
                    await message('Recording ·');await control('stop-save',panel.locator('#stop'));await message('Recording saved.')
                for _ in range(3):
                    t,cmd=await row_play(1,'control_play_first_action_ms')
                    await helper_event('state',t,index=2);await message('Playing')
                    unchanged=await panel.locator(f'tr[data-task-id="{ids[3]}"]').element_handle()
                    t,_,_=await control('pause',panel.locator('#pause'));paused=await helper_event('state',t,mode='paused');sample('pause_execution_ms',paused['ts']-t);await message('Paused.')
                    if args.repeat_visits:assert await unchanged.evaluate('(row)=>row.isConnected'), 'Unchanged row was rebuilt'
                    t,_,_=await control('resume',panel.locator('#resume'));resumed=await helper_event('state',t,mode='running');sample('resume_execution_ms',resumed['ts']-t)
                    await message('Playing')
                    t,_,_=await control('stop',panel.locator('#stop'));done=await helper_event('state',t,mode='stopped');sample('stop_execution_ms',done['ts']-t);await message(__import__('re').compile('Stopped|Recording saved'))
                    assert local('state')['step']==3
                checks['controls_same_unfinished_step']=True
                print(args.variant+': latency samples complete',flush=True)
                # One full minute per state, both helper and page control traffic.
                begin=time.time();await asyncio.sleep(60);windows['idle']=[begin,time.time()]
                print(args.variant+': idle window complete',flush=True)
                begin=time.time();runs=0
                while time.time()-begin<60:
                    t,cmd=await row_play(2,'traffic_play_first_action_ms');await helper_event('state',t,mode='completed',operation=cmd['id']);await message('Completed');runs+=1
                windows['active']=[begin,time.time()];checks['active_runs']=runs
                # Double Play at the DOM surface: same actual pending state guard.
                row=panel.locator(f'tr[data-task-id="{ids[1]}"]');before=len([c for c in commands if c['control']=='play'])
                await row.get_by_role('button',name='Play 01 Controls',exact=True).evaluate('(b)=>{b.click();b.click()}')
                await message('Playing');await asyncio.sleep(.5)
                assert len([c for c in commands if c['control']=='play'])==before+1
                checks['duplicate_play_blocked']=True
                # Fault only this synthetic helper connection, never installed transport.
                (out/'cut-connection').write_text('synthetic')
                interrupted=await helper_event('state',time.time()-1,mode='interrupted')
                (out/'cut-connection').unlink()
                await helper_event('state',interrupted['ts'],connected=True)
                await asyncio.sleep(1);assert local('state')['mode']=='interrupted'
                checks['reconnect_no_replay']=True
                await control('stop',panel.locator('#stop'));await message(__import__('re').compile('Stopped|Recording saved'))
                # Closed-page status traffic stays quiet; return recovers same state.
                begin=time.time();await page.goto('about:blank');await asyncio.sleep(10);windows['closed']=[begin,time.time()]
                await page.goto(SITE+'/?page=task_recorder');await panel.locator('#pc').filter(has_text='Connected').wait_for(timeout=30000)
                assert local('state')['mode']=='stopped';checks['page_return_no_replay']=True
                if args.repeat_visits:
                    # Auxiliary lifecycle/focus checks run after measurement windows.
                    await panel.locator(f'tr[data-task-id="{ids[0]}"]').get_by_role('button',name='Select 00 Navigation',exact=True).click()
                    await panel.locator('#name').fill('Draft name retained')
                    await panel.locator('#refresh').click()
                    await asyncio.sleep(.5)
                    assert await panel.locator('#name').input_value()=='Draft name retained'
                    cdp=await context.new_cdp_session(page);await cdp.send('Performance.enable')
                    retained=[]
                    for visit in range(5):
                        await page.goto('about:blank');await page.goto(SITE+'/?page=task_recorder')
                        await panel.locator('#pc').filter(has_text='Connected').wait_for(timeout=30000)
                        assert await panel.locator('#activeName').inner_text()=='00 Navigation'
                        assert await panel.locator(f'tr[data-task-id="{ids[0]}"]').count()==1
                        await cdp.send('HeapProfiler.collectGarbage')
                        counters=await cdp.send('Memory.getDOMCounters')
                        metrics=await cdp.send('Performance.getMetrics')
                        heap=next(m['value'] for m in metrics['metrics'] if m['name']=='JSHeapUsedSize')
                        retained.append({**counters,'heap_mb':heap/1048576})
                    checks['five_page_visits']=retained
                    checks['unchanged_row_retained_while_paused']=True
                    checks['draft_input_retained_on_refresh']=True
                    checks['selection_retained_after_refresh']=True
            await page.screenshot(path=str(out/'page.png'),full_page=True)
            await browser.close()
        allrows=records(hpath)+ui
        summary={'variant':args.variant,'latency_ms':{k:stats(v) for k,v in latencies.items()},'windows':{},'checks':checks}
        for name,(begin,end) in windows.items():
            wire=[r for r in allrows if r['kind']=='wire' and begin<=r.get('start',r['ts'])<end]
            resources=[r for r in allrows if r['kind']=='resource' and begin<=r['ts']<end]
            row={'seconds':end-begin,'traffic':{}}
            for group in ('ui','helper','website','ui_assets'):
                selected=[r for r in wire if r['group']==group];minutes=(end-begin)/60
                row['traffic'][group]={'requests':len(selected),'requests_per_min':len(selected)/minutes,'sent_bytes':sum(r['sent'] for r in selected),'received_bytes':sum(r['received'] for r in selected),'sent_http_bytes':sum(r.get('sent_http',0) for r in selected),'received_http_bytes':sum(r.get('received_http',0) for r in selected)}
            row['cpu_one_core_percent']=stats([r['cpu'] for r in resources]);row['working_set_mb']=stats([r['memory_mb'] for r in resources]);summary['windows'][name]=row
        (out/'ui.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in ui),encoding='utf-8')
        (out/'commands.json').write_text(json.dumps(commands,indent=2),encoding='utf-8')
        (out/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
        print(json.dumps(summary,indent=2),flush=True)
    finally:
        with contextlib.suppress(Exception):local('shutdown',{})
        # Only children started here. Preview launcher starts one serving child.
        for proc in processes:
            if proc.poll() is None:subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for log in logs:log.close()

def main():
    p=argparse.ArgumentParser();p.add_argument('--helper',action='store_true');p.add_argument('--wire-only',action='store_true');p.add_argument('--repeat-visits',action='store_true');p.add_argument('--variant',default='after');p.add_argument('--recorder-source',type=Path,default=REPO);p.add_argument('--out',type=Path)
    args=p.parse_args();args.recorder_source=args.recorder_source.resolve();args.out=(args.out or BASE/args.variant).resolve()
    if BASE not in args.out.parents:raise SystemExit('Benchmark must use its isolated local data folder.')
    if args.helper:helper(args)
    else:asyncio.run(run(args))
if __name__=='__main__':main()
