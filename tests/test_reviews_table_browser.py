"""Real Streamlit layout/cache checks on loopback with fabricated reviews only."""
import ast
import base64
import json
import os
from pathlib import Path
from time import perf_counter
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright,expect

ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=ROOT/'artifacts/reviews-table-responsive-20261124'
URL='http://127.0.0.1:8543'


def test_responsive_table_actions_latency_and_recovery():
    EVIDENCE.mkdir(parents=True,exist_ok=True)
    metrics=[];errors=[]
    with sync_playwright() as runtime:
        channel=os.getenv('REVIEWS_BROWSER_CHANNEL','msedge')
        browser=runtime.chromium.launch(headless=True,**({'channel':channel} if channel!='chromium' else {}))
        context=browser.new_context()
        def route(request):
            host=urlsplit(request.request.url).hostname
            if host=='127.0.0.1':request.continue_()
            elif host=='cdn.shopify.com':request.fulfill(content_type='image/png',body=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII='))
            else:request.abort()
        context.route('**/*',route)
        page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
        try:
            for width,height in [(1920,1080),(1440,900),(1366,768),(1024,768),(881,826),(750,900),(430,900),(390,844),(375,667),(320,740)]:
                page.set_viewport_size({'width':width,'height':height});started=perf_counter();page.goto(URL)
                expect(page.locator('.rv-row')).to_have_count(25,timeout=15000)
                elapsed=round((perf_counter()-started)*1000)
                assert page.get_by_test_id('stException').count()==0
                expect(page.locator('[class*="st-key-rv-entry-"]').first.get_by_role('button',name='Edit',exact=True)).to_be_visible()
                values=page.locator('[class*="st-key-rv-entry-"]').first.evaluate('''el=>({
                  width:el.clientWidth,height:el.getBoundingClientRect().height,overflow:el.scrollWidth>el.clientWidth+1,
                  columns:getComputedStyle(el).gridTemplateColumns,
                  product:(()=>{const p=el.querySelector('.rv-product-name');return {w:p.clientWidth,h:p.clientHeight,line:parseFloat(getComputedStyle(p).lineHeight)}})(),
                  buttons:Array.from(el.querySelectorAll('button')).filter(b=>b.getBoundingClientRect().width>0).map(b=>({text:b.innerText,w:b.getBoundingClientRect().width,h:b.getBoundingClientRect().height,font:parseFloat(getComputedStyle(b.querySelector('p')).fontSize)}))
                })''')
                assert not values['overflow'],(width,values)
                assert values['product']['w']>=115,(width,values)
                assert values['product']['h']<=values['product']['line']*2+2,(width,values)
                assert values['height']<240,(width,values)
                assert [b['text'] for b in values['buttons']]==['Open','Edit'],(width,values)
                assert all(b['w']>=78 and b['h']>=35 and b['font']>=12 for b in values['buttons']),(width,values)
                assert page.locator('[data-testid="stMain"]').evaluate('el=>el.scrollWidth<=el.clientWidth+1'),width
                metrics.append({'viewport':[width,height],'cold_rows_ms':elapsed,**values})
                if width in (1440,881,390,320):page.screenshot(path=str(EVIDENCE/f'local-{width}.png'),full_page=False)
            # Warm viewport changes must reuse the registered read jobs.
            initial=ast.literal_eval(page.locator('[data-testid="stCode"] code').inner_text())
            page.set_viewport_size({'width':881,'height':826})
            assert ast.literal_eval(page.locator('[data-testid="stCode"] code').inner_text())==initial
            start=perf_counter();page.get_by_role('button',name='Next',exact=True).click()
            expect(page.locator('.rv-customer').first).to_have_text('Synthetic collector 26')
            next_ms=round((perf_counter()-start)*1000)
            page.get_by_role('button',name='Previous',exact=True).click()
            expect(page.locator('.rv-customer').first).to_have_text('Synthetic collector 1')
            page.locator('[class*="st-key-rv-actions-"]').first.get_by_role('button',name='Open',exact=True).click()
            expect(page.get_by_role('dialog')).to_be_visible()
            expect(page.get_by_role('button',name='Save reply',exact=True)).to_be_visible()
            assert page.get_by_test_id('stException').count()==0
            page.keyboard.press('Escape');expect(page.get_by_role('dialog')).to_be_hidden()
            page.get_by_role('button',name='Edit',exact=True).first.click()
            expect(page.get_by_role('textbox',name='Review text',exact=True)).to_be_visible()
            page.get_by_role('textbox',name='Review text',exact=True).fill('Synthetic corrected review text')
            page.get_by_role('textbox',name='Reason for edit',exact=True).fill('Synthetic customer correction')
            page.get_by_role('button',name='Save changes',exact=True).click()
            expect(page.get_by_role('dialog')).to_be_hidden()
            expect(page.locator('.rv-copy').first).to_contain_text('Synthetic corrected review text')
            page.get_by_text('Simulate slow storage',exact=True).click()
            page.get_by_text('Simulate storage failure',exact=True).click()
            start=perf_counter();page.get_by_role('button',name='Refresh fixture',exact=True).click()
            expect(page.locator('.rv-row')).to_have_count(25)
            retained_ms=round((perf_counter()-start)*1000)
            expect(page.get_by_text('Reviews could not refresh. Last resolved rows remain visible.',exact=True)).to_be_visible(timeout=10000)
            expect(page.locator('.rv-row')).to_have_count(25)
            page.get_by_text('Simulate storage failure',exact=True).click()
            page.get_by_text('Simulate slow storage',exact=True).click()
            page.get_by_role('button',name='Retry reviews',exact=True).click()
            expect(page.get_by_text('Reviews could not refresh. Last resolved rows remain visible.',exact=True)).to_be_hidden(timeout=10000)
            assert not errors,errors
            result={'layouts':metrics,'next_page_ms':next_ms,'last_good_retained_ms':retained_ms,'console_errors':errors,'read_calls_before_resize':initial}
            (EVIDENCE/'benchmark.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
            print(json.dumps(result))
        finally:
            if not (EVIDENCE/'benchmark.json').exists():
                page.screenshot(path=str(EVIDENCE/'last-test-state.png'),full_page=False)
                (EVIDENCE/'last-test-state.txt').write_text(page.get_by_test_id('stMain').inner_text(),encoding='utf-8')
            browser.close()
