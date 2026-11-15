"""Isolated Chromium/HTTP/SQL upload benchmark; all storage and auth are local doubles.

Opt in with PRODUCT_UPLOAD_BENCHMARK_PSD pointing at an explicitly non-production PSD.
PHASE2_BENCH_MODE=phase1 or phase2; baseline snapshot is the preserved Phase1 local code.
"""
from pathlib import Path
import gc
import json
import os
import threading
import time
import types

import psutil
import pytest
from playwright.sync_api import sync_playwright
from starlette.applications import Starlette
from starlette.responses import HTMLResponse, Response
from starlette.routing import Route
from tests.test_product_upload_intake import env, database, ADMIN, DiskDropbox
from tests.benchmark_product_upload_transfer import local_client

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/product-upload-phase2'


def load_snapshot(name,path):
    module=types.ModuleType(name);module.__file__=str(path)
    exec(compile(path.read_text(encoding='utf-8-sig'),str(path),'exec'),module.__dict__)
    return module


def test_browser_benchmark(env, monkeypatch, tmp_path):
    source=os.environ.get('PRODUCT_UPLOAD_BENCHMARK_PSD')
    if not source:pytest.skip('Requires explicitly non-production PSD')
    source=Path(source);mode=os.environ.get('PHASE2_BENCH_MODE','phase1')
    import product_upload_api as current
    import files_upload_api as files
    baseline=OUT/'phase1'
    api=load_snapshot('phase1_api',baseline/'product_upload_api.py') if mode=='phase1' else current
    if mode=='phase2_baseline':
        api=load_snapshot('phase2_api',OUT/'phase2-api.py')
        intake=load_snapshot('phase2_intake',OUT/'phase2-intake.py')
        api.Intakes=intake.Intakes;api.public=intake.public
    if mode=='phase1':
        intake=load_snapshot('phase1_intake',baseline/'product_upload_intake.py')
        api.Intakes=intake.Intakes;api.public=intake.public
    javascript=(baseline/'components/product_uploads/app.js' if mode=='phase1' else ROOT/'components/product_uploads/app.js').read_text(encoding='utf-8')
    if mode=='phase2_baseline':javascript=(OUT/'phase2-app.js').read_text(encoding='utf-8')
    profiles=[dict(name='loopback',up_mbps=0,rtt_ms=0,storage_rtt_ms=0,storage_mbps=0),
              dict(name='latency-bandwidth',up_mbps=40,rtt_ms=160,storage_rtt_ms=180,storage_mbps=100)]
    rows=[];startup_only=os.environ.get('PHASE2_BENCH_STARTUP_ONLY')=='1'
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(headless=True)
        for profile in profiles:
            provider=DiskDropbox(tmp_path/profile['name'])
            class Storage:
                def __getattr__(self,name):
                    member=getattr(provider,name)
                    def call(*args,**kwargs):
                        delay=profile['storage_rtt_ms']/1000
                        if name=='append' and profile['storage_mbps']:
                            delay+=len(args[2])*8/(profile['storage_mbps']*1000000)
                        if delay:time.sleep(delay)
                        return member(*args,**kwargs)
                    return call
            monkeypatch.setattr(api,'connect',env[0].connect);monkeypatch.setattr(api,'Dropbox',Storage)
            monkeypatch.setattr(files,'_request_user',lambda *args,**kwargs:ADMIN)
            async def html(request):return HTMLResponse((ROOT/'components/product_uploads/index.html').read_text(encoding='utf-8'))
            async def script(request):return Response(javascript,media_type='application/javascript')
            routes=[Route('/',html),Route('/product-uploads.js',script)]
            routes += [Route(p,e,methods=list(m)) for p,e,m in api.ROUTES if p!='/product-uploads.js']
            application=Starlette(routes=routes)
            first_body=[]
            class BodyArrival:
                async def __call__(self,scope,receive,send):
                    async def observed_receive():
                        event=await receive()
                        if scope.get('path')=='/api/product-uploads/chunk' and event.get('body') and not first_body:
                            first_body.append(time.time()*1000)
                        return event
                    await application(scope,observed_receive,send)
            with local_client(BodyArrival()) as client:
                context=browser.new_context();page=context.new_page();errors=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                session=context.new_cdp_session(page)
                session.send('Network.enable')
                if profile['up_mbps']:
                    session.send('Network.emulateNetworkConditions',dict(offline=False,latency=profile['rtt_ms'],downloadThroughput=100000000,uploadThroughput=profile['up_mbps']*1000000/8))
                # local_client deliberately binds only loopback. Expose its URL for this browser fixture.
                base=client.base
                page.goto(base+'/');page.wait_for_function("!document.getElementById('mode').disabled && window.productUploadMetrics")
                page.evaluate("""() => {
                  window.uploadBench={events:[],longTasks:[],maxFrameGap:0};
                  new PerformanceObserver(list=>{for(const e of list.getEntries())uploadBench.longTasks.push({start:e.startTime,duration:e.duration});}).observe({entryTypes:['longtask']});
                  let previous=performance.now();function frame(now){uploadBench.maxFrameGap=Math.max(uploadBench.maxFrameGap,now-previous);previous=now;requestAnimationFrame(frame);}requestAnimationFrame(frame);
                  const open=XMLHttpRequest.prototype.open,send=XMLHttpRequest.prototype.send;
                  XMLHttpRequest.prototype.open=function(method,url){this.benchURL=url;return open.apply(this,arguments)};
                  XMLHttpRequest.prototype.send=function(body){uploadBench.events.push({kind:'send',at:performance.now(),bytes:body?.size||0});this.addEventListener('loadend',()=>uploadBench.events.push({kind:'ack',at:performance.now(),status:this.status}));return send.apply(this,arguments)};
                }""")
                baseline_memory=psutil.Process().memory_info().rss;samples=[];stop=threading.Event()
                def sample():
                    while not stop.wait(.025):
                        try:
                            processes=[psutil.Process(),*psutil.Process().children(recursive=True)]
                            chromium=[p for p in processes if 'chrome' in p.name().lower() or 'headless' in p.name().lower()]
                            samples.append(dict(server=psutil.Process().memory_info().rss,browser=sum(p.memory_info().rss for p in chromium)))
                        except (psutil.NoSuchProcess,psutil.AccessDenied):pass
                thread=threading.Thread(target=sample,daemon=True);thread.start()
                t=time.perf_counter();selected_at=page.evaluate('performance.now()');selected_epoch=page.evaluate('Date.now()')
                page.locator('#file').set_input_files(str(source))
                if startup_only:
                    deadline=time.monotonic()+20
                    try:
                        while not first_body and time.monotonic()<deadline:page.wait_for_timeout(10)
                        assert first_body,'No binary body arrived'
                        rows.append(dict(mode=mode,profile=profile,bytes=source.stat().st_size,
                                         selection_to_first_server_body_byte_s=(first_body[0]-selected_epoch)/1000,
                                         identity=page.evaluate('productUploadMetrics.identity')))
                        print(json.dumps(rows[-1]),flush=True)
                    finally:
                        stop.set();thread.join();context.close();gc.collect()
                    continue
                try:page.wait_for_function("document.getElementById('stage').textContent==='Uploaded'",timeout=180000)
                finally:stop.set();thread.join()
                duration=time.perf_counter()-t
                metrics=page.evaluate('productUploadMetrics');bench=page.evaluate('uploadBench')
                assert not errors,errors
                events=bench['events'];sends=[e for e in events if e['kind']=='send'];acks=[e for e in events if e['kind']=='ack']
                assert all(e['status']==200 for e in acks)
                first=sends[0]['at'];last=acks[-1]['at'];transfer=(last-first)/1000
                finish=[r for r in metrics['requests'] if r['operation']=='finish'][-1]
                row=dict(mode=mode,profile=profile,bytes=source.stat().st_size,selection_to_first_send_s=(first-selected_at)/1000,
                         transfer_s=transfer,finalisation_s=finish['elapsed_ms']/1000,total_s=duration,
                         effective_MiB_s=source.stat().st_size/1048576/transfer,chunk_requests=len(sends),
                         provider_appends=sum(k=='append' for k,n in provider.calls),identity=metrics['identity'],requests=metrics['requests'],
                         renderer_heap=session.send('Runtime.getHeapUsage'),peak_server_rss_MiB=max(s['server'] for s in samples)/1048576,
                         server_rss_growth_MiB=(max(s['server'] for s in samples)-baseline_memory)/1048576,
                         peak_browser_rss_MiB=max(s['browser'] for s in samples)/1048576,
                         max_frame_gap_ms=bench['maxFrameGap'],long_tasks=bench['longTasks'])
                rows.append(row);print(json.dumps({k:v for k,v in row.items() if k not in ('requests','renderer_heap','long_tasks')}),flush=True)
                context.close();gc.collect()
        browser.close()
    OUT.mkdir(exist_ok=True,parents=True)
    (OUT/(mode+('-startup.json' if startup_only else '-browser.json'))).write_text(json.dumps(dict(boundary='Actual Chromium to isolated loopback HTTP and disposable SQL; synthetic CDP bandwidth/latency and disk provider latency. No real Dropbox or production calls.',runs=rows),indent=2),encoding='utf-8')
