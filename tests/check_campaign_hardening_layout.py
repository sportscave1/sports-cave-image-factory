"""Scheduled-state layout and zero-I/O menu checks in real Chrome/Edge."""
import json,time
from pathlib import Path
from playwright.sync_api import sync_playwright
out=Path('docs/campaign-hardening-evidence');results=[]
with sync_playwright() as p:
    for channel in ('chrome','msedge'):
        browser=p.chromium.launch(channel=channel,headless=True)
        for view in ('detail','home'):
            for width,height in ((1440,900),(820,1180),(390,844),(320,740)):
                context=browser.new_context(viewport={'width':width,'height':height},timezone_id='Australia/Sydney')
                context.route('**/*',lambda r:r.continue_() if r.request.url.startswith(('http://127.0.0.1:8597/','ws://127.0.0.1:8597/','data:')) else r.abort())
                page=context.new_page();frames=[];http=[]
                page.on('websocket',lambda ws:ws.on('framesent',lambda payload:frames.append(str(payload))))
                page.on('request',lambda r:http.append(r.url))
                page.goto('http://127.0.0.1:8597/?view='+view)
                page.locator('#hardening-counts').wait_for(state='attached');page.wait_for_timeout(500)
                page.screenshot(path=str(out/f'{channel}-scheduled-{view}-{width}.png'),full_page=True)
                metrics=page.locator('[data-testid=stMain]').evaluate('(n)=>({scrollHeight:n.scrollHeight,clientHeight:n.clientHeight,scrollWidth:n.scrollWidth,clientWidth:n.clientWidth})')
                assert metrics['scrollWidth']<=metrics['clientWidth']
                assert page.get_by_test_id('stException').count()==0
                menu_ms=None
                if view=='home':
                    old_frames=len(frames);old_http=len(http)
                    button=page.get_by_role('button',name='⋯',exact=True)
                    button.focus();start=time.perf_counter();button.press('Enter')
                    menu=page.get_by_test_id('stPopoverBody');menu.wait_for(state='visible')
                    menu_ms=(time.perf_counter()-start)*1000
                    assert len(frames)==old_frames and len(http)==old_http
                    page.keyboard.press('Escape');menu.wait_for(state='hidden')
                results.append({'channel':channel,'view':view,'width':width,'height':height,**metrics,'menu_ms':menu_ms,'menu_network_requests':0 if view=='home' else None})
                context.close()
        browser.close()
(out/'layout.json').write_text(json.dumps(results,indent=2))
print(json.dumps(results,indent=2))
