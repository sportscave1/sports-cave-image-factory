"""Chrome and Edge acceptance, synthetic loopback UI and blocked external I/O."""
import json,time,math,statistics,argparse
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT=Path('docs/campaign-hardening-evidence');OUT.mkdir(exist_ok=True)
parser=argparse.ArgumentParser()
parser.add_argument('--acceptance-only',action='store_true')
parser.add_argument('--performance-only',action='store_true')
parser.add_argument('--channel',choices=('chrome','msedge'))
parser.add_argument('--view',choices=('home','detail'))
parser.add_argument('--width',type=int)
args=parser.parse_args()
channels=(args.channel,) if args.channel else ('chrome','msedge')
results=[];perf=[]
with sync_playwright() as p:
    for channel in channels:
        browser=p.chromium.launch(channel=channel,headless=True)
        context=browser.new_context(timezone_id='Australia/Sydney')
        context.route('**/*',lambda r:r.continue_() if r.request.url.startswith(('http://127.0.0.1:8597/','ws://127.0.0.1:8597/','data:')) else r.abort())
        for view in (() if args.performance_only else ((args.view,) if args.view else ('detail','home'))):
            for width,height in ((1440,900),(820,1180),(390,844),(320,740)):
                if args.width and width!=args.width:continue
                page=context.new_page()
                page.set_viewport_size({'width':width,'height':height})
                navigations=[];page.on('framenavigated',lambda f:navigations.append(f.url) if f==page.main_frame else None)
                page.goto('http://127.0.0.1:8597/?view='+view+'&countdown_probe=1')
                page.locator('#hardening-counts').wait_for(state='attached')
                page.wait_for_timeout(500)
                assert page.get_by_test_id('stException').count()==0
                assert page.evaluate('document.documentElement.scrollWidth')<=width
                countdown=page.locator('[data-sc-campaign-due]').first
                countdown.wait_for();first=countdown.inner_text();page.wait_for_timeout(1150)
                assert countdown.inner_text()!=first
                counts=lambda:json.loads(page.locator('#hardening-counts').inner_text())
                initial=counts();menu_ms=None
                if view=='home':
                    frames=[]
                    page.on('websocket',lambda ws:ws.on('framesent',lambda payload:frames.append(str(payload))))
                    button=page.get_by_role('button',name='⋯',exact=True)
                    button.focus();start=time.perf_counter();button.press('Enter')
                    page.get_by_role('button',name='Edit schedule',exact=True).wait_for(state='visible')
                    menu_ms=(time.perf_counter()-start)*1000
                    assert counts()==initial
                    menu=page.get_by_test_id('stPopoverBody');box=menu.bounding_box()
                    assert box['x']>=-1 and box['x']+box['width']<=width+1
                    page.get_by_role('button',name='Edit schedule',exact=True).focus()
                    page.keyboard.press('Escape');menu.wait_for(state='hidden')
                    button.click()
                page.get_by_role('button',name='Edit schedule',exact=True).click()
                dialog=page.get_by_test_id('stDialog').get_by_role('dialog');dialog.wait_for()
                dialog.get_by_text('Current timing:',exact=False).wait_for()
                assert '2099' in dialog.inner_text() or dialog.get_by_role('textbox').count()>0
                dialog.get_by_role('button',name='Cancel',exact=True).click()
                dialog.wait_for(state='hidden')
                assert counts()['amendments']==0
                if view=='home' and not page.get_by_role('button',name='Edit schedule',exact=True).is_visible():page.get_by_role('button',name='⋯',exact=True).click()
                page.get_by_role('button',name='Edit schedule',exact=True).click()
                time_input=page.get_by_test_id('stDialog').get_by_role('dialog').get_by_test_id('stTimeInput').locator('input')
                if time_input.is_visible():
                    time_input.fill('18:00');time_input.press('Tab')
                else:
                    hour=page.get_by_test_id('stDialog').get_by_role('dialog').get_by_role('spinbutton',name='hour, Time',exact=True)
                    hour.press('ArrowUp');hour.press('Tab')
                page.get_by_test_id('stDialog').get_by_role('dialog').get_by_text('Current timing:',exact=False).click()
                page.wait_for_timeout(600)
                page.get_by_test_id('stDialog').get_by_role('dialog').get_by_role('button',name='Save schedule',exact=True).click()
                page.get_by_test_id('stDialog').get_by_role('dialog').wait_for(state='hidden')
                page.wait_for_function("JSON.parse(document.querySelector('#hardening-counts')?.textContent||'{}').amendments===1")
                assert '18:00' in page.locator('body').inner_text()
                if view=='home' and not page.get_by_role('button',name='Send now',exact=True).is_visible():page.get_by_role('button',name='⋯',exact=True).click()
                page.get_by_role('button',name='Send now',exact=True).click()
                dialog=page.get_by_test_id('stDialog').get_by_role('dialog');dialog.wait_for()
                assert counts()['amendments']==1
                confirm=dialog.get_by_role('button',name='Confirm Send Now',exact=True)
                confirm.focus();confirm.press('Enter')
                page.wait_for_function("JSON.parse(document.querySelector('#hardening-counts')?.textContent||'{}').amendments===2")
                assert page.get_by_test_id('stDialog').get_by_role('dialog').count()==0
                assert 'Queued' in page.locator('body').inner_text()
                assert len(navigations)==1
                assert page.get_by_test_id('stException').count()==0
                page.screenshot(path=str(OUT/f'{channel}-{view}-{width}.png'),full_page=True)
                results.append({'channel':channel,'view':view,'width':width,'height':height,'passed':True,'menu_ms':menu_ms,'main_navigations':len(navigations),'amendments':counts()['amendments']})
                (OUT/f'acceptance-{channel}-{view}-{width}.json').write_text(json.dumps(results[-1],indent=2))
                print(channel,view,width,'passed',flush=True)
                page.close()
        if args.acceptance_only:
            context.close();browser.close();continue
        # Alternate phases to reduce warmup/order bias. Same fixture and viewport.
        page=context.new_page();page.set_viewport_size({'width':1440,'height':900})
        for run in range(22):
            for phase in ('hardening','0') if run%2==0 else ('0','hardening'):
                start=time.perf_counter();page.goto('http://127.0.0.1:8597/?view=detail&before='+phase)
                page.get_by_role('button',name='Email preview',exact=True).wait_for()
                page.locator('[data-sc-campaign-due]').wait_for()
                if run>=2:perf.append({'channel':channel,'phase':'before' if phase=='hardening' else 'after','ms':(time.perf_counter()-start)*1000})
        page.close();context.close();browser.close()
summary=[]
for channel in channels:
    for phase in ('before','after'):
        values=sorted(r['ms'] for r in perf if r['channel']==channel and r['phase']==phase)
        if not values:continue
        summary.append({'channel':channel,'phase':phase,'n':len(values),'p50_ms':statistics.median(values),'p95_ms':values[math.ceil(.95*len(values))-1]})
(OUT/'browser.json').write_text(json.dumps({'acceptance':results,'summary':summary,'samples':perf},indent=2))
print(json.dumps({'acceptance':results,'summary':summary},indent=2))
