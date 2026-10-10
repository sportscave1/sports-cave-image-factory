"""Repeatable local browser checks; every outbound non-loopback request is denied."""
from pathlib import Path
import json,time,statistics,os
from playwright.sync_api import sync_playwright
out=Path(os.getenv('FLOW_V4_UI_SCREENSHOTS','tmp/flow-v4-browser'));out.mkdir(exist_ok=True)
results=[]
def timed(fn):
    start=time.perf_counter();fn();return round(1000*(time.perf_counter()-start),2)
with sync_playwright() as pw:
    for channel in ('chrome','msedge'):
        browser=pw.chromium.launch(channel=channel,headless=True)
        context=browser.new_context(viewport={'width':1440,'height':1000})
        context.route('**/*',lambda r:r.continue_() if r.request.url.startswith(('http://127.0.0.1','ws://127.0.0.1','data:')) else r.abort())
        page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        targets=((False,int(os.getenv('FLOW_V4_UI_PORT','8566'))),) if os.getenv('FLOW_V4_UI_SKIP_BASELINE')=='1' else ((True,int(os.getenv('FLOW_V4_BEFORE_PORT','8564'))),(False,int(os.getenv('FLOW_V4_AFTER_PORT','8566'))))
        for before,port in targets:
            for stages in (1,3,6,12):
                print(channel,before,stages,flush=True)
                for run in range(6):
                    started=time.perf_counter();page.goto(f'http://127.0.0.1:{port}/?stages={stages}')
                    page.get_by_role('button',name='Edit Email',exact=True).first.wait_for(timeout=30000)
                    row_ms=round(1000*(time.perf_counter()-started),2)
                    first_ms=timed(lambda:page.locator('.sc-flow-thumbnail').first.locator('img').wait_for(timeout=120000))
                    visible_ms=timed(lambda:page.wait_for_function("[...document.querySelectorAll('.sc-flow-thumbnail')].filter(e=>{const r=e.getBoundingClientRect();return r.top<innerHeight&&r.bottom>0}).every(e=>e.querySelector('img')?.naturalWidth>0)",timeout=120000))
                    results.append(dict(channel=channel,before=before,stages=stages,run=run,rows_ms=row_ms,first_after_rows_ms=first_ms,visible_after_first_ms=visible_ms))
                    assert page.get_by_test_id('stException').count()==0
                page.locator('.sc-flow-thumbnail').last.scroll_into_view_if_needed()
                try:page.locator('.sc-flow-thumbnail').last.locator('img').wait_for(timeout=30000 if before else 120000)
                except Exception:
                    results.append(dict(channel=channel,before=before,stages=stages,later_stage_error=page.locator('.sc-flow-thumbnail').last.get_attribute('data-phase')))
                    if not before:raise
                if stages==3:
                    for width in (1920,1440,1366,1024,750,430,390,320):
                        page.set_viewport_size({'width':width,'height':1000});page.locator('.automation-title').scroll_into_view_if_needed()
                        page.screenshot(path=str(out/(f'{channel}-'+('before' if before else 'after')+f'-{width}.png')),full_page=True)
                        assert not page.get_by_test_id('stMain').evaluate('(e)=>e.scrollWidth>e.clientWidth+2'),(channel,width)
                    page.set_viewport_size({'width':1440,'height':1000})
                if not before and stages==3:
                    assert page.get_by_text('Recipient timelines and scheduled deliveries',exact=True).count()==1
                    assert page.get_by_text('Abandoned checkouts',exact=True).count()==1
                    assert page.locator('.sc-flow-stats dt').all_text_contents()==['Entered','Sent','Delivery','Opens','Clicks','Conversions','Orders','Bounce']
                    assert page.locator('.sc-flow-stats dd').all_text_contents()==['41','43','100.0%','39.5%','9.3%','0','0','0.0%']
                    interactions={}
                    for run in range(6):
                        interactions.setdefault('menu_ms',[]).append(timed(lambda:(page.locator('[class*="st-key-flow-row-"]').first.get_by_role('button',name='⋮',exact=True).click(),page.get_by_role('textbox',name='Email name',exact=True).first.wait_for())))
                        page.keyboard.press('Escape')
                        interactions.setdefault('preview_open_ms',[]).append(timed(lambda:(page.locator('.sc-flow-thumbnail').first.click(),page.get_by_role('button',name='Close preview',exact=True).wait_for())))
                        interactions.setdefault('preview_close_ms',[]).append(timed(lambda:(page.get_by_role('button',name='Close preview',exact=True).click(),page.get_by_role('button',name='Close preview',exact=True).wait_for(state='hidden'))))
                    results.append(dict(channel=channel,interactions=interactions))
        assert not errors,errors
        context.close();browser.close()
Path(os.getenv('FLOW_V4_RESULTS_PREFIX','tmp/flow-v4')+'-benchmarks.json').write_text(json.dumps(results,indent=2))
summary=[]
for channel in ('chrome','msedge'):
    for before in (True,False):
        for stages in (1,3,6,12):
            values=[r['rows_ms'] for r in results if r.get('channel')==channel and r.get('before')==before and r.get('stages')==stages and r['run']>0]
            if not values:continue
            summary.append(dict(channel=channel,before=before,stages=stages,n=len(values),warm_rows_p50=round(statistics.median(values),2),warm_rows_p95=sorted(values)[-1]))
Path(os.getenv('FLOW_V4_RESULTS_PREFIX','tmp/flow-v4')+'-benchmark-summary.json').write_text(json.dumps(summary,indent=2))
print(json.dumps(summary,indent=2))
