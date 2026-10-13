"""Loopback browser acceptance and measured timings; denies external requests."""
import json,time,statistics
from pathlib import Path
from playwright.sync_api import sync_playwright,expect

OUT=Path('docs/lifecycle-expansion-evidence');OUT.mkdir(parents=True,exist_ok=True)
results=[]
with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True)
    context=browser.new_context(viewport={'width':1440,'height':1050})
    context.route('**/*',lambda r:r.continue_() if r.request.url.startswith(('http://127.0.0.1','ws://127.0.0.1','data:')) else r.abort())
    page=context.new_page();page.set_default_timeout(45000)
    for label,port,flow in [('before',8613,'abandoned'),('after',8614,'abandoned'),('welcome',8614,'welcome'),('post_purchase',8614,'post_purchase'),('win_back',8614,'win_back')]:
        timings=[]
        for sample in range(3):
            start=time.perf_counter();page.goto(f'http://127.0.0.1:{port}/?flow={flow}')
            page.get_by_role('button',name='Edit Email',exact=True).first.wait_for()
            timings.append(round((time.perf_counter()-start)*1000,2))
        page.wait_for_timeout(500)
        assert page.get_by_test_id('stException').count()==0,page.locator('body').inner_text()
        page.screenshot(path=str(OUT/(label+'-desktop.png')),full_page=True)
        metric={'page':label,'load_ms':timings}
        if flow!='abandoned':
            assert page.get_by_role('button',name='Publish now',exact=True).count()==1
            assert 'Draft · activation locked' not in page.locator('body').inner_text()
            name={'welcome':'Marketing subscribers','post_purchase':'Paid orders','win_back':'Inactive purchasers'}[flow]
            page.get_by_text(name,exact=True).click()
            table=page.frame_locator('iframe[title$=".crm_checkout_table"]').get_by_role('table')
            table.wait_for()
            start=time.perf_counter();page.get_by_role('textbox',name='Search and filter',exact=True).fill('collector10@example.test')
            page.get_by_role('textbox',name='Search and filter',exact=True).press('Enter')
            page.wait_for_timeout(500)
            table.get_by_role('button',name='Details Fixture Collector 10',exact=True).wait_for()
            metric['search_ms']=round((time.perf_counter()-start)*1000,2)
            table.get_by_role('button',name='Details Fixture Collector 10',exact=True).click()
            page.get_by_text('Eligibility:',exact=False).wait_for()
            page.screenshot(path=str(OUT/(label+'-audience.png')),full_page=True)
            page.set_viewport_size({'width':620,'height':950});page.wait_for_timeout(200)
            page.screenshot(path=str(OUT/(label+'-narrow.png')),full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
            page.set_viewport_size({'width':1440,'height':1050})
        start=time.perf_counter();page.get_by_role('button',name='Edit Email',exact=True).first.click()
        page.get_by_role('button',name='Flow',exact=True).wait_for()
        metric['editor_ms']=round((time.perf_counter()-start)*1000,2)
        page.get_by_role('textbox',name='Subject',exact=True).wait_for()
        page.locator('.st-key-crm-composer-preview iframe, .st-key-crm-automation-live-preview iframe').first.wait_for()
        metric['preview_ready_ms']=round((time.perf_counter()-start)*1000,2)
        page.wait_for_timeout(350)
        assert page.get_by_test_id('stException').count()==0,page.locator('body').inner_text()
        page.screenshot(path=str(OUT/(label+'-editor.png')),full_page=True)
        if flow!='abandoned':
            page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(200)
            page.screenshot(path=str(OUT/(label+'-editor-narrow.png')),full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
            page.set_viewport_size({'width':1440,'height':1050})
            subject=page.get_by_role('textbox',name='Subject',exact=True)
            original=subject.input_value();subject.fill(original+' [local draft check]');subject.press('Tab')
            page.wait_for_timeout(350)
            page.get_by_role('button',name='Save draft',exact=True).click()
            page.wait_for_timeout(400)
            page.get_by_role('button',name='Flow',exact=True).click()
            page.get_by_role('button',name='Edit Email',exact=True).first.click()
            subject=page.get_by_role('textbox',name='Subject',exact=True)
            expect(subject).to_have_value(original+' [local draft check]')
            subject.fill(original);subject.press('Tab')
            page.wait_for_timeout(350)
            page.get_by_role('button',name='Save draft',exact=True).click()
            page.wait_for_timeout(300)
            metric['save_reload']='passed'
            metric['narrow_editor_width']=390
        start=time.perf_counter();page.get_by_role('button',name='Flow',exact=True).click()
        page.get_by_role('button',name='Edit Email',exact=True).first.wait_for()
        metric['warm_return_ms']=round((time.perf_counter()-start)*1000,2)
        results.append(metric)
        (OUT/'browser.json').write_text(json.dumps(results,indent=2))
    browser.close()
print(json.dumps(results,indent=2))
