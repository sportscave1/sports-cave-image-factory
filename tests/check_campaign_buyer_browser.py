"""Synthetic real controls; browser network restricted to loopback."""
import json, math, statistics, time
from pathlib import Path
from playwright.sync_api import sync_playwright
out=Path('docs/buyer-segments-v8-evidence');out.mkdir(exist_ok=True)
samples=[];layouts=[]
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    context=browser.new_context()
    context.route('**/*',lambda r:r.continue_() if r.request.url.startswith(('http://127.0.0.1','ws://127.0.0.1','data:')) else r.abort())
    page=context.new_page()
    for before in (True,False):
        for run in range(12):
            started=time.perf_counter();page.goto('http://127.0.0.1:8598/?before='+str(int(before)))
            page.get_by_test_id('stSelectbox').filter(has=page.get_by_text('Segment' if before else 'Location',exact=True)).wait_for()
            if not before:page.get_by_test_id('stMultiSelect').wait_for()
            samples.append({'before':before,'run':run,'controls_ms':(time.perf_counter()-started)*1000})
    for width in (1440,768,390,320):
        page.set_viewport_size({'width':width,'height':1000})
        page.goto('http://127.0.0.1:8598/')
        field=page.get_by_test_id('stMultiSelect');field.wait_for()
        field.get_by_role('combobox').fill('Cricket')
        page.get_by_role('option').filter(has_text='Cricket Buyers').click()
        page.get_by_text('1 selected · match any selected segment',exact=True).wait_for()
        page.wait_for_timeout(300)
        field.get_by_role('combobox').fill('Motorsport')
        page.get_by_role('option').filter(has_text='Motorsport Buyers').click()
        page.get_by_text('2 selected · match any selected segment',exact=True).wait_for()
        page.keyboard.press('Escape')
        page.get_by_role('button',name='Fixture save',exact=True).click()
        page.wait_for_timeout(250)
        contract=json.loads(page.locator('#buyer-contract').inner_text())
        assert len(contract['shopify_segment_ids'])==2,contract
        assert contract['market']=='Global'
        overflow=page.evaluate('document.documentElement.scrollWidth > window.innerWidth')
        assert not overflow, width
        page.screenshot(path=str(out/f'settings-{width}.png'),full_page=True)
        layouts.append({'width':width,'horizontal_overflow':overflow,'selections':2})
    browser.close()
summary={}
for before in (True,False):
    values=[r['controls_ms'] for r in samples if r['before']==before]
    summary['before' if before else 'after']={'samples':len(values),'p50_ms':statistics.median(values),'p95_ms':sorted(values)[math.ceil(len(values)*.95)-1]}
(out/'browser.json').write_text(json.dumps({'method':'Synthetic cached controls, Edge, loopback, fresh navigation; not production API latency','summary':summary,'samples':samples,'layouts':layouts},indent=2))
print(json.dumps(summary))
