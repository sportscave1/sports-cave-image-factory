"""Chrome/Edge responsive schedule contracts; loopback fixture only."""
import json,time,statistics,math
from pathlib import Path
from playwright.sync_api import sync_playwright
out=Path('docs/campaign-v8-evidence');out.mkdir(parents=True,exist_ok=True)
results=[];samples=[]
with sync_playwright() as p:
    for channel in ('chrome','msedge'):
        browser=p.chromium.launch(channel=channel,headless=True)
        context=browser.new_context()
        context.route('**/*',lambda r:r.continue_() if r.request.url.startswith(('http://127.0.0.1','ws://127.0.0.1','data:')) else r.abort())
        page=context.new_page()
        for before in (True,False):
            for run in range(8):
                start=time.perf_counter();page.goto('http://127.0.0.1:8596/?before='+str(int(before)))
                page.get_by_role('heading',name='Campaign scheduling').wait_for()
                header=(time.perf_counter()-start)*1000
                page.locator('.sc-home-row').wait_for()
                samples.append({'channel':channel,'before':before,'header_ms':header,'row_ms':(time.perf_counter()-start)*1000})
        for width in (1920,1440,1366,1024,750,430,390,320):
            page.close();page=context.new_page()
            page.set_viewport_size({'width':width,'height':1000});page.goto('http://127.0.0.1:8596/')
            page.locator('.sc-home-row').wait_for()
            page.get_by_test_id('stRadio').get_by_text('Schedule',exact=True).click()
            basis=page.get_by_test_id('stSelectbox').filter(has=page.get_by_text('Time basis',exact=True)).get_by_role('combobox')
            basis.wait_for()
            zone=page.get_by_test_id('stSelectbox').filter(has=page.get_by_text('Timezone',exact=True)).get_by_role('combobox')
            zone.wait_for()
            contract=json.loads(page.locator('#v8-contract').inner_text())
            assert contract['timezone']=='Australia/Sydney' and contract['time_basis']=='campaign_timezone'
            zone.click();page.get_by_role('option',name='Australia/Darwin',exact=True).click()
            page.wait_for_function("JSON.parse(document.querySelector('#v8-contract').textContent).timezone==='Australia/Darwin'")
            basis.click();page.get_by_role('option',name='Each recipient’s own timezone',exact=True).click()
            page.wait_for_function("JSON.parse(document.querySelector('#v8-contract').textContent).time_basis==='recipient_local'")
            assert 'many hours' in page.locator('body').inner_text()
            assert page.get_by_test_id('stException').count()==0
            assert page.evaluate('document.documentElement.scrollWidth')<=width
            countdown=page.locator('[data-sc-campaign-due]');countdown.wait_for();first=countdown.inner_text();page.wait_for_timeout(1100)
            assert countdown.inner_text()!=first
            assert json.loads(page.locator('#v8-ui-counters').inner_text())['snapshot_reads']==0
            page.get_by_role('button',name='Edit schedule',exact=True).click()
            page.get_by_role('dialog').wait_for()
            dialog=page.get_by_role('dialog')
            assert 'Sydney time (AEDT)' in dialog.inner_text()
            assert dialog.get_by_test_id('stSelectbox').filter(has=page.get_by_text('Timezone',exact=True)).count()==1
            dialog.get_by_role('button',name='Save schedule',exact=True).click()
            page.wait_for_function("JSON.parse(document.querySelector('#v8-ui-counters').textContent).amendments===1")
            page.get_by_role('button',name='Send now',exact=True).click()
            page.get_by_role('dialog').get_by_role('button',name='Confirm Send Now',exact=True).click()
            page.wait_for_function("JSON.parse(document.querySelector('#v8-ui-counters').textContent).amendments===2")
            page.screenshot(path=str(out/f'{channel}-{width}.png'),full_page=True)
            page.get_by_role('button',name='Fixture: complete',exact=True).click()
            page.wait_for_function("!document.querySelector('[data-sc-campaign-due]')")
            page.wait_for_function("JSON.parse(document.querySelector('#v8-ui-counters').textContent).amendments===2")
            results.append({'channel':channel,'width':width,'passed':True})
        context.close();browser.close()
summary=[]
for channel in ('chrome','msedge'):
    for before in (True,False):
        group=[r for r in samples if r['channel']==channel and r['before']==before]
        item={'channel':channel,'before':before,'n':len(group)}
        for metric in ('header_ms','row_ms'):
            values=sorted(r[metric] for r in group);item[metric]={'p50':statistics.median(values),'p95':values[math.ceil(.95*len(values))-1]}
        summary.append(item)
(out/'browser.json').write_text(json.dumps({'layouts':results,'summary':summary,'samples':samples},indent=2))
print(json.dumps({'layouts':results,'summary':summary},indent=2))
