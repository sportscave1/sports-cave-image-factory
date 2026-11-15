"""Local synthetic lifecycle previews. No authentication, database or email sends."""
from pathlib import Path
import sys,json,time,statistics
from html import escape
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from crm_collector_stages import STAGES,document,source,mapping
from crm_collector_templates import DESIGNS,source as reusable_source
from crm_collector_images import render,sample_facts
from crm_campaign_content import render_campaign,settings

OUT=Path(__file__).resolve().parents[1]/'docs/collector-email-v2'
OUT.mkdir(parents=True,exist_ok=True)
cfg={**settings({}),'postal':'Local fixture only · no customer data',
     'contact':'fixture@example.test','email_defaults':{'header':'','footer':''}}
examples={};metrics=[]
for key in DESIGNS:
    (OUT/(key+'-source.txt')).write_text(reusable_source(key),encoding='utf-8')
for key in STAGES:
    doc=document(key)
    (OUT/(key+'-source.txt')).write_text(source(key),encoding='utf-8')
    variants=['sample','neutral'] if key in ('welcome-2','post_purchase-2','win_back-2') else ['sample']
    for variant in variants:
        facts=sample_facts(doc) if variant=='sample' else {}
        sample=render(doc,facts,preview=True)
        description=('Synthetic customer; hypothetical V8 Supercars interest, ownership, variants and allocation. Public artwork images; not evidence of stock or certificate readiness.'
                     if variant=='sample' else 'Synthetic customer; no verified artwork or classification available. Neutral fallback; no certificate readiness assertion.')
        if key.startswith('welcome') and variant=='sample':
            description='Synthetic subscriber; no purchase presumed. '+('Curated public artwork example.' if key=='welcome-1' else 'Hypothetical explicitly known V8 Supercars interest.')+' Not evidence of stock or real customer preferences.'
        if key=='win_back-4':description='DISABLED — review preview only; no application or sending. '+description
        heading=f'{key.replace("_"," ")} · {variant} fixture'
        banner='<p style="font:13px Arial;padding:12px;background:#fff;color:#111">'+escape(heading+' — '+description)+'</p>'
        durations=[]
        for _ in range(20):
            start=time.perf_counter();mail=render_campaign(sample,cfg);durations.append((time.perf_counter()-start)*1000)
        html=banner+mail['html'];name=key+'-'+variant
        (OUT/(name+'-preview.txt')).write_text(html,encoding='utf-8')
        examples[name]=html
        metrics.append({'email':key,'fixture':variant,'render_ms_median':round(statistics.median(durations),3),'bytes':len(html.encode()),'shopify_requests':0})

if '--screenshots' in sys.argv:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser=pw.chromium.launch(channel='msedge',headless=True)
        for name,html in examples.items():
            for width in (600,375):
                page=browser.new_page(viewport={'width':width,'height':1000})
                page.set_content(html,wait_until='networkidle',timeout=45000)
                dimensions=page.evaluate('''({width:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth,
                  images:[...document.images].map(i=>({loaded:i.complete&&i.naturalWidth>0,
                    natural:[i.naturalWidth,i.naturalHeight],rendered:[i.width,i.height]}))})''')
                assert dimensions['scroll']<=width,(name,dimensions)
                for img in dimensions['images']:
                    assert img['loaded'],(name,img)
                    nw,nh=img['natural'];w,h=img['rendered']
                    assert abs(h-w*nh/nw)<=2,(name,img)
                page.screenshot(path=str(OUT/(name+'-'+str(width)+'.png')),full_page=True)
                metrics.append({'email':name,'viewport':width,**dimensions});page.close()
        browser.close()
(OUT/'preview-metrics.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8')
(OUT/'lifecycle-mapping.json').write_text(json.dumps(mapping(),indent=2),encoding='utf-8')
print(f'{len(examples)} labelled previews; '+str(len(metrics))+' measurements; no sends.')
