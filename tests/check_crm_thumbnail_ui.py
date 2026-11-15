import re
import json,time,os
from pathlib import Path
from playwright.sync_api import sync_playwright
results=[]
base=os.environ.get('THUMBNAIL_FIXTURE_URL','http://127.0.0.1:8551/')
version=str(int(time.time()))
with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='chrome',headless=True)
    for baseline in (True,False):
        context=browser.new_context(viewport={'width':1440,'height':1000})
        context.route('**/*',lambda route: route.continue_() if route.request.url.startswith(('http://127.0.0.1','ws://127.0.0.1','data:')) else route.abort())
        page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        for run in ('cold','warm'):
            start=time.perf_counter();page.goto(base+('?baseline=1' if baseline else '?version='+version))
            page.get_by_role('button',name='Edit Email',exact=True).first.wait_for(timeout=30000)
            initial=(time.perf_counter()-start)*1000
            try:
                if baseline:page.wait_for_function("document.querySelector('.sc-flow-thumbnail')?.shadowRoot?.querySelector('.email')?.textContent.length>5",timeout=20000)
                else:page.locator('.sc-flow-thumbnail img').first.wait_for(timeout=60000)
                preview=(time.perf_counter()-start)*1000
            except Exception:preview=None
            results.append({'baseline':baseline,'run':run,'initial_ms':round(initial,1),'first_thumbnail_ms':round(preview,1) if preview else None,'images':page.locator('.sc-flow-thumbnail img').count(),'errors':errors})
        if not baseline:
            page.wait_for_function("[...document.querySelectorAll('.sc-flow-thumbnail')].slice(0,5).every(e=>e.querySelector('img')?.naturalWidth>0)",timeout=30000)
            assert page.locator('.sc-flow-thumbnail img').count()<12
            assert page.locator('iframe').count()==0
            page.locator('.sc-flow-thumbnail').last.scroll_into_view_if_needed()
            page.locator('.sc-flow-thumbnail').last.locator('img').wait_for(timeout=60000)
            for width in (1440,390):
                page.set_viewport_size({'width':width,'height':1000})
                page.evaluate('window.scrollTo(0,0)')
                page.screenshot(path=f'tmp/thumbnail-{width}.png',full_page=True)
                assert not page.get_by_test_id('stMain').evaluate('(e)=>e.scrollWidth>e.clientWidth+2')
            image=page.locator('.sc-flow-thumbnail img').first
            image.evaluate("e=>e.src='data:image/webp;base64,broken'")
            page.get_by_text('Preview unavailable. Click to open email.',exact=True).first.wait_for()
            page.locator('.sc-flow-thumbnail').first.click()
            page.get_by_text(re.compile('LIVE v'+version+' email preview')).wait_for()
        assert not errors,errors
        assert page.get_by_test_id('stException').count()==0
        context.close()
    browser.close()
Path('tmp/thumbnail-benchmarks.json').write_text(json.dumps(results,indent=2))
print(json.dumps(results,indent=2))
