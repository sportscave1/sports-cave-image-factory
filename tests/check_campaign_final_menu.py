"""Repeated native-menu keyboard/outside-pointer acceptance on all target widths."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
results=[]
with sync_playwright() as p:
    for channel in ('chrome','msedge'):
        browser=p.chromium.launch(channel=channel,headless=True)
        context=browser.new_context()
        context.route('**/*',lambda r:r.continue_() if r.request.url.startswith(('http://127.0.0.1:8597/','data:')) else r.abort())
        for width in (1440,820,390,320):
            page=context.new_page();page.set_viewport_size({'width':width,'height':900})
            frames=[];page.on('websocket',lambda ws:ws.on('framesent',lambda data:frames.append(str(data))))
            page.goto('http://127.0.0.1:8597/?view=home')
            page.locator('#hardening-counts').wait_for(state='attached')
            assert page.evaluate('document.documentElement.scrollWidth')<=width
            trigger=page.get_by_role('button',name='⋯',exact=True);menu=page.get_by_test_id('stPopoverBody')
            before=len(frames)
            for attempt in range(24):
                trigger.focus();trigger.press('Enter');menu.wait_for(state='visible')
                assert menu.count()==1
                box=menu.bounding_box();assert box['x']>=-1 and box['x']+box['width']<=width+1
                focus=trigger if attempt%3==0 else page.get_by_role('button',name='Edit schedule' if attempt%3==1 else 'History',exact=True)
                focus.focus()
                if attempt%3==1:
                    page.keyboard.press('Tab')
                    assert page.get_by_role('button',name='Send now',exact=True).evaluate('(el)=>el===document.activeElement')
                    page.keyboard.press('Shift+Tab');assert focus.evaluate('(el)=>el===document.activeElement')
                page.keyboard.press('Escape');menu.wait_for(state='hidden')
                page.wait_for_function("document.activeElement?.textContent.includes('⋯')")
                if attempt%4==0:
                    trigger.click();menu.wait_for(state='visible')
                    page.get_by_role('heading',name='Campaigns',exact=True).click();menu.wait_for(state='hidden')
            assert len(frames)==before, 'Menu generated network requests'
            assert page.get_by_test_id('stException').count()==0
            results.append(dict(channel=channel,width=width,escape_cycles=24,outside_cycles=6,tab_cycles=8,network_requests=0,passed=True))
            print(channel,width,'PASS',flush=True);page.close()
        context.close();browser.close()
Path('../.tmp-full-system-audit/final-menu.json').write_text(json.dumps(results,indent=2))
