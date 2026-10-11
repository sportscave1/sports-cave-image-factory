"""Generate clearly labelled local examples and Notepad source exports. No sends."""
from pathlib import Path
import sys,json,time,statistics
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from crm_collector_templates import DESIGNS,document,source
from crm_campaign_content import render_campaign,settings

OUT=Path(__file__).resolve().parents[1]/'docs/collector-email-v1'
OUT.mkdir(parents=True,exist_ok=True)
cfg={**settings({}),'postal':'Local preview fixture · no customer data',
     'contact':'fixture@example.test','email_defaults':{'header':'','footer':''}}
examples={};metrics=[]
for key in DESIGNS:
    doc=document(key)
    (OUT/(key+'-source.txt')).write_text(source(key),encoding='utf-8')
    samples=[]
    for _ in range(20):
        start=time.perf_counter();mail=render_campaign(doc,cfg);samples.append((time.perf_counter()-start)*1000)
    html=mail['html']
    (OUT/(key+'-preview.txt')).write_text(html,encoding='utf-8')
    examples[key]=html
    metrics.append({'template':key,'render_ms_median':round(statistics.median(samples),3),'bytes':len(html.encode())})

if '--screenshots' in sys.argv:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser=pw.chromium.launch(channel='msedge',headless=True)
        context=browser.new_context()
        for key,html in examples.items():
            for width in (600,375):
                page=context.new_page();page.set_viewport_size({'width':width,'height':1000})
                page.set_content(html,wait_until='networkidle',timeout=45000)
                dimensions=page.evaluate('({width:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth,images:[...document.images].map(i=>({loaded:i.complete&&i.naturalWidth>0,src:i.src}))})')
                assert dimensions['scroll']<=width,(key,width,dimensions)
                page.screenshot(path=str(OUT/(key+'-'+str(width)+'.png')),full_page=True)
                metrics.append({'template':key,'viewport':width,**dimensions})
                page.close()
        browser.close()
(OUT/'preview-metrics.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8')
print(json.dumps(metrics,indent=2))
