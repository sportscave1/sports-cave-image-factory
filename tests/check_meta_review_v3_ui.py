"""Requested Chrome/Edge loopback browser checks; blocks all external requests.

Start tests/fixtures/meta_review_v3_preview.py on port 8899 first.
"""
import json
import os
import re
import statistics
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

def summary(values):
    return {'p50_ms':round(statistics.median(values),2),
            'p95_ms':round(sorted(values)[int(.95*(len(values)-1))],2),'samples':len(values)}

results={}
base=os.environ.get('META_REVIEW_FIXTURE_URL','http://127.0.0.1:8899')
prefix=os.environ.get('META_REVIEW_BENCH_PREFIX','meta-v3')
with sync_playwright() as pw:
    for channel in ('chrome','msedge'):
        browser=pw.chromium.launch(channel=channel,headless=True)
        context=browser.new_context(viewport={'width':1440,'height':1000})
        context.route('**/*',lambda route:route.continue_() if route.request.url.startswith(('http://127.0.0.1','ws://127.0.0.1','data:')) else route.abort())
        page=context.new_page(); errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        opening=[]; search=[]; refresh=[]
        for _ in range(10):
            start=time.perf_counter(); page.goto(base)
            page.get_by_test_id('stDataFrame').first.wait_for()
            opening.append((time.perf_counter()-start)*1000)
            control=page.get_by_role('textbox',name='Search campaigns')
            start=time.perf_counter(); control.fill('NO_MATCH_XYZ'); control.press('Enter')
            page.get_by_text('No matching campaigns.',exact=True).wait_for()
            search.append((time.perf_counter()-start)*1000)
            control.fill('');control.press('Enter');page.get_by_test_id('stDataFrame').first.wait_for()
            marker=page.get_by_text(re.compile(r'^Fixture run \d+$'))
            run=int(marker.inner_text().split()[-1])
            start=time.perf_counter();page.get_by_role('button',name='Refresh From Meta',exact=True).click()
            page.get_by_text('Fixture run '+str(run+1),exact=True).wait_for()
            refresh.append((time.perf_counter()-start)*1000)
        for width in (1440,390):
            page.set_viewport_size({'width':width,'height':1000})
            collapse=page.get_by_test_id('stSidebarCollapseButton').get_by_role('button')
            if width<600 and collapse.is_visible():
                collapse.click()
            page.wait_for_function("(()=>{const e=document.querySelector('[data-testid=stMain]');return e && e.scrollWidth<=e.clientWidth+2})()",timeout=5000)
            page.get_by_test_id('stMain').evaluate('(e)=>e.scrollTop=0')
            page.screenshot(path=f'tmp/{prefix}-{channel}-{width}.png',full_page=True)
            assert not page.get_by_test_id('stMain').evaluate('(e)=>e.scrollWidth>e.clientWidth+2')
            assert page.get_by_role('button',name='Refresh From Meta',exact=True).is_visible()
            assert page.get_by_role('textbox',name='Search campaigns').is_visible()
            page.get_by_text('Advanced metrics',exact=True).click()
            assert page.get_by_test_id('stDataFrame').count()==2
        assert not errors,errors
        assert page.get_by_test_id('stException').count()==0
        if 'before' not in prefix:
            page.get_by_text('Simulate outage',exact=True).click()
            page.get_by_role('button',name='Refresh From Meta',exact=True).click()
            page.get_by_text(re.compile('STALE CACHED META')).wait_for()
            assert page.get_by_test_id('stDataFrame').count()>=1
            page.goto(base+'/?failure=1')
            page.get_by_text(re.compile('No complete report is available')).wait_for()
            assert page.get_by_test_id('stDataFrame').count()==0
            assert page.get_by_text(re.compile('No campaigns matched')).count()==0
        results[channel]={'fixture_new_session':summary(opening),'search_no_match_browser':summary(search),
                          'refresh_mock_browser':summary(refresh),'desktop_and_narrow':'passed','javascript_errors':errors}
        context.close();browser.close()
Path(f'tmp/{prefix}-browser.json').write_text(json.dumps(results,indent=2))
print(json.dumps(results,indent=2))
