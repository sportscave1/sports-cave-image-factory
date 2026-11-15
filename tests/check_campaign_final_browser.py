"""Loopback before/after browser measurements and trigger-Escape reproduction."""
import os,sys,time,json,math,statistics,subprocess,urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT.parent
OUT=BASE/'.tmp-full-system-audit/final-browser-performance.json'
interactions_only='--interactions-only' in sys.argv
if interactions_only:OUT=BASE/'.tmp-full-system-audit/final-dialog-performance.json'
samples=[];escape=[];processes=[];logs=[]
def save():
    summary=[]
    for phase,metric in sorted({(r['phase'],r['metric']) for r in samples}):
        values=sorted(r['ms'] for r in samples if r['phase']==phase and r['metric']==metric)
        summary.append(dict(phase=phase,metric=metric,n=len(values),p50_ms=statistics.median(values),p95_ms=values[math.ceil(.95*len(values))-1]))
    OUT.write_text(json.dumps(dict(summary=summary,samples=samples,escape=escape),indent=2))
try:
    for phase,root,port in [('before',BASE/'.tmp-campaign-final-baseline',8598),('after',ROOT,8599)]:
        log=open(BASE/f'.tmp-full-system-audit/final-browser-{phase}.log','w');logs.append(log)
        env={**os.environ,'PYTHONPATH':str(BASE/'.tmp-full-system-audit/streamlit165')+os.pathsep+str(root),'CAMPAIGN_SOURCE_ROOT':str(root),'PYTHONUTF8':'1'}
        p=subprocess.Popen([sys.executable,'-m','streamlit','run',str(ROOT/'tests/fixtures/campaign_final_preview.py'),'--server.address=127.0.0.1',f'--server.port={port}','--server.headless=true','--global.developmentMode=false'],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        processes.append(p)
        for retry in range(80):
            try:
                urllib.request.urlopen(f'http://127.0.0.1:{port}/_stcore/health',timeout=1).close();break
            except OSError:time.sleep(.25)
        else:raise RuntimeError('Local fixture startup failed')
    with sync_playwright() as pw:
        for channel in ('chrome','msedge'):
            browser=pw.chromium.launch(channel=channel,headless=True)
            context=browser.new_context(viewport={'width':1440,'height':900},timezone_id='Australia/Sydney')
            context.route('**/*',lambda r:r.continue_() if r.request.url.startswith(('http://127.0.0.1:8598/','http://127.0.0.1:8599/','data:')) else r.abort())
            for phase,port in [('before',8598),('after',8599)]:
                page=context.new_page();page.goto(f'http://127.0.0.1:{port}/?view=home')
                page.locator('#hardening-counts').wait_for(state='attached')
                trigger=page.get_by_role('button',name='⋯',exact=True);menu=page.get_by_test_id('stPopoverBody')
                for run in range(20):
                    start=time.perf_counter();trigger.click();menu.wait_for(state='visible')
                    samples.append(dict(phase=phase,metric=channel+' menu',ms=(time.perf_counter()-start)*1000))
                    trigger.focus();page.keyboard.press('Escape');page.wait_for_timeout(100)
                    closed=not menu.is_visible();escape.append(dict(phase=phase,channel=channel,attempt=run,closed=closed))
                    if not closed:
                        page.get_by_role('button',name='Edit schedule',exact=True).focus();page.keyboard.press('Escape');menu.wait_for(state='hidden')
                if interactions_only:
                    for run in range(20):
                        trigger.click();menu.wait_for(state='visible')
                        start=time.perf_counter();page.get_by_role('button',name='Edit schedule',exact=True).click()
                        dialog=page.get_by_test_id('stDialog').get_by_role('dialog')
                        dialog.get_by_text('Current timing:',exact=False).wait_for()
                        samples.append(dict(phase=phase,metric=channel+' schedule dialog',ms=(time.perf_counter()-start)*1000))
                        runs=json.loads(page.locator('#hardening-counts').inner_text())['runs']
                        dialog.get_by_role('button',name='Cancel',exact=True).click();dialog.wait_for(state='hidden')
                        page.wait_for_function("runs=>JSON.parse(document.querySelector('#hardening-counts').textContent).runs>runs",arg=runs)
                page.close();save()
            if channel=='chrome' and not interactions_only:
                page=context.new_page()
                for view in ('home','workspace'):
                    for run in range(22):
                        for phase,port in ([('before',8598),('after',8599)] if run%2 else [('after',8599),('before',8598)]):
                            start=time.perf_counter();page.goto(f'http://127.0.0.1:{port}/?view={view}')
                            page.locator('#hardening-counts').wait_for(state='attached')
                            page.locator('[data-sc-campaign-due]').first.wait_for()
                            assert page.get_by_test_id('stException').count()==0
                            if run>=2:samples.append(dict(phase=phase,metric='chrome initial '+view,ms=(time.perf_counter()-start)*1000,queries=json.loads(page.locator('#hardening-counts').inner_text())['queries']))
                            save()
                page.close()
            context.close();browser.close()
    save();print(OUT)
finally:
    for p in processes:
        if p.poll() is None:subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
    for log in logs:log.close()
