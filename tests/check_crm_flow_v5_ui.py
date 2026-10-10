"""Equivalent synthetic before/after browser samples. External requests denied."""
import json,math,statistics,time
from pathlib import Path
from playwright.sync_api import sync_playwright

out=Path('docs/flow-v5-evidence');out.mkdir(parents=True,exist_ok=True)
results=[];layouts=[]
def ms(fn):
    at=time.perf_counter();fn();return round((time.perf_counter()-at)*1000,2)
def settle(page):
    page.wait_for_timeout(350)

with sync_playwright() as pw:
    for channel in ('chrome','msedge'):
        browser=pw.chromium.launch(channel=channel,headless=True)
        for before,port in ((True,8594),(False,8595)):
            context=browser.new_context(viewport={'width':1440,'height':1000})
            context.route('**/*',lambda r:r.continue_() if r.request.url.startswith(('http://127.0.0.1','ws://127.0.0.1','data:')) else r.abort())
            page=context.new_page();page.set_default_timeout(30000)
            for run in range(6):
                at=time.perf_counter();page.goto(f'http://127.0.0.1:{port}/?stages=3')
                page.locator('.automation-title').wait_for()
                header=(time.perf_counter()-at)*1000
                page.get_by_role('button',name='Edit Email',exact=True).first.wait_for()
                stage=(time.perf_counter()-at)*1000
                page.locator('.sc-flow-stats dd').first.wait_for()
                analytics=(time.perf_counter()-at)*1000
                assert page.get_by_test_id('stException').count()==0
                values={'channel':channel,'before':before,'run':run,'header_ms':round(header,2),'stage_ms':round(stage,2),'analytics_ms':round(analytics,2)}
                if not before:
                    assert page.get_by_role('button',name='Diagnostics',exact=True).count()==0
                    assert page.get_by_role('button',name='Refresh analytics',exact=True).count()==0
                    assert not page.locator('.automation-title').inner_text().find('LIVE v')>=0
                    assert 'Draft content (thumbnail: published)' not in page.locator('body').inner_text()
                    settle(page)
                    counters=json.loads(page.locator('#flow-v4-counters').inner_text())
                    assert counters['checkout_loads']==0 and counters['timeline_loads']==0
                    values['test_open_ms']=ms(lambda:(page.get_by_role('button',name='Test',exact=True).click(),page.get_by_role('textbox',name='Email address',exact=True).wait_for()))
                    assert page.get_by_role('checkbox',name='Recipient subscribed').count()==0
                    values['test_close_ms']=ms(lambda:page.keyboard.press('Escape'));settle(page)
                    page.get_by_role('button',name='Edit Email',exact=True).first.click()
                    page.get_by_role('textbox',name='Subject',exact=True).wait_for()
                    values['editor_return_ms']=ms(lambda:(page.get_by_role('button',name='Flow',exact=True).click(),page.get_by_role('button',name='Edit Email',exact=True).first.wait_for()))
                results.append(values)
                print(channel,before,run,values,flush=True)
            if not before:
                for width in (1920,1440,1366,1024,750,430,390,320):
                    page.set_viewport_size({'width':width,'height':1000});settle(page)
                    assert not page.get_by_test_id('stMain').evaluate('(e)=>e.scrollWidth>e.clientWidth+2'),(channel,width)
                    toolbar=page.locator('.st-key-automation-toolbar')
                    layouts.append({'channel':channel,'width':width,'height':toolbar.bounding_box()['height']})
                    page.screenshot(path=str(out/f'{channel}-{width}.png'),full_page=True)
                page.set_viewport_size({'width':1440,'height':1000})
                recipient=page.get_by_text('Recipient timelines and scheduled deliveries',exact=True)
                checkout=page.get_by_text('Abandoned checkouts',exact=True)
                values={'channel':channel,'before':False,'operations':True}
                values['timeline_expand_ms']=ms(lambda:(recipient.click(),page.get_by_text('Synthetic recipient journey',exact=True).wait_for()))
                recipient.click()
                values['checkout_expand_ms']=ms(lambda:(checkout.click(),page.get_by_text('Synthetic paginated checkout table',exact=True).wait_for()))
                checkout.click();page.get_by_role('button',name='Test',exact=True).click()
                page.get_by_role('textbox',name='Email address',exact=True).fill('operator@example.test')
                values['mock_start_ms']=ms(lambda:(page.get_by_role('button',name='Start Test',exact=True).click(),page.get_by_text('TEST — Draft · scheduled',exact=True).wait_for()))
                results.append(values)
            context.close()
        browser.close()

summary={}
for before in (True,False):
    samples=[r for r in results if r['before']==before and 'run' in r]
    for key in sorted({k for r in samples for k in r if k.endswith('_ms')}):
        values=sorted(r[key] for r in samples if key in r)
        summary[f'{"before" if before else "after"}_{key}']={'n':len(values),'p50':round(statistics.median(values),2),'p95':values[math.ceil(len(values)*.95)-1]}
(out/'browser-results.json').write_text(json.dumps({'samples':results,'layouts':layouts,'summary':summary},indent=2))
print(json.dumps(summary,indent=2))
