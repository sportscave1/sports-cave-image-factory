"""Pixel and interaction regression against the captured pre-edit checkout table."""
import json
from pathlib import Path
from PIL import Image,ImageChops
from playwright.sync_api import sync_playwright

out=Path('docs/lifecycle-expansion-evidence');out.mkdir(exist_ok=True)
payload=dict(rows=[dict(key='fixture-1',customer='Fixture Collector',created='10 Oct 2026',created_full='10 Oct 2026 12:00',
    cells=[dict(label='Delivered',tone='success'),dict(label='Queued',tone='muted')])],
    columns=[dict(label='Email 1',enabled=True),dict(label='Email 2',enabled=True)],selected=[],
    server_now='2026-10-10T12:00:00Z',read_at='2026-10-10T12:00:00Z',phase='READY')
results=[]
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    for width in (1440,620):
        captures=[];interactions=[]
        for label,path in [('original','tmp/lifecycle-baseline/checkout-table.html'),('current','components/crm_checkout_table/index.html')]:
            page=browser.new_page(viewport=dict(width=width,height=400))
            page.set_content(Path(path).read_text(encoding='utf-8'))
            page.evaluate("window.receipts=[];addEventListener('message',e=>{if(e.data.type==='streamlit:setComponentValue')receipts.push(e.data.value)})")
            page.evaluate("args=>dispatchEvent(new MessageEvent('message',{source:window,data:{type:'streamlit:render',args}}))",payload)
            page.get_by_role('button',name='Details Fixture Collector',exact=True).wait_for()
            page.screenshot(path=str(out/f'checkout-table-{label}-{width}.png'))
            captures.append(Image.open(out/f'checkout-table-{label}-{width}.png').convert('RGB'))
            page.get_by_role('button',name='Details Fixture Collector',exact=True).click()
            page.wait_for_timeout(50)
            interactions.append(page.evaluate("receipts.map(({sequence,...rest})=>rest)"))
            page.close()
        assert ImageChops.difference(*captures).getbbox() is None,f'Table pixels changed at {width}'
        assert interactions[0]==interactions[1],interactions
        results.append(dict(width=width,pixel_difference=0,details_interaction='identical'))
    browser.close()
(out/'checkout-table-regression.json').write_text(json.dumps(results,indent=2))
print(json.dumps(results))
