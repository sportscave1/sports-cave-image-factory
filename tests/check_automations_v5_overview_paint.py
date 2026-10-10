"""Measure real sidebar entry with the shared loading overlay accounted for."""
import json,os,time
from pathlib import Path
from playwright.sync_api import sync_playwright

base='http://127.0.0.1:'+os.environ['AUTOMATIONS_V5_PORT']+'/'
result={}
source=Path('tests/fixtures/automation_v5_paint.js').read_text()
# A visible DOM node underneath the opaque OS loading layer is not a visible
# destination paint. Keep route acceptance independent; gate actual UI paints.
source=source.replace('for (const [name, element] of Object.entries',"if (!document.body.classList.contains('sc-navigation-pending')) for (const [name, element] of Object.entries")
with sync_playwright() as pw:
    for channel in ('chrome','msedge'):
        browser=pw.chromium.launch(channel=channel,headless=True)
        context=browser.new_context(viewport={'width':1440,'height':1000})
        context.add_init_script(source)
        context.route('**/*',lambda route:route.continue_() if route.request.url.startswith(('http://127.0.0.1','ws://127.0.0.1','data:')) else route.abort())
        page=context.new_page();page.set_default_timeout(20000)
        for steps in (1,3,6,12):
            values=[];result[channel+'-'+str(steps)]=values
            page.goto(base+'?fixture_steps='+str(steps))
            page.get_by_role('heading',name='Dashboard',exact=True).wait_for()
            page.locator('[class*="st-key-sidebar-disclosure-email-"] button:visible').first.click()
            for attempt in range(3):
                page.evaluate("sessionStorage.setItem('v5-expected-view','overview')")
                app_starts=int(page.locator('#v5-render').get_attribute('data-runs'))
                app_completions=int(page.locator('#v5-render').get_attribute('data-completed-runs'))
                started=time.perf_counter()
                page.locator('.st-key-sidebar-row-crm_automations_manage button:visible').first.click()
                page.locator('.sc-auto-row').first.wait_for()
                search=page.get_by_role('textbox',name='Search automations',exact=True);search.wait_for()
                page.wait_for_function("!document.body.classList.contains('sc-navigation-pending')")
                assert search.is_enabled()
                page.wait_for_function("window.v5Paints.all !== undefined")
                page.wait_for_function('(previous)=>Number(document.querySelector("#v5-render").dataset.completedRuns)>previous',arg=app_completions)
                sample={'kind':'cold_session_entry' if attempt==0 else 'warm_sidebar_entry',
                        'wall_ms':round((time.perf_counter()-started)*1000,2),
                        'click_to_ready_ms':page.evaluate("Date.now()-Number(sessionStorage.getItem('v5-click-absolute'))"),
                        'feedback_ms':page.evaluate('window.v5Feedback'),
                        'paints':page.evaluate('window.v5Paints'),
                        'app_run_starts':int(page.locator('#v5-render').get_attribute('data-runs'))-app_starts,
                        'completed_app_runs':int(page.locator('#v5-render').get_attribute('data-completed-runs'))-app_completions}
                page.wait_for_timeout(1500)
                sample['settled_paints']=page.evaluate('window.v5Paints');values.append(sample)
                assert page.get_by_test_id('stException').count()==0
                if attempt<2:
                    page.locator('.st-key-sidebar-row-dashboard button:visible').first.click()
                    page.get_by_role('heading',name='Dashboard',exact=True).wait_for()
                    page.wait_for_function("!document.body.classList.contains('sc-navigation-pending')")
        browser.close()
Path('tmp/automations-v5-'+os.environ['AUTOMATIONS_V5_VARIANT']+'-overview.json').write_text(json.dumps(result,indent=2)+'\n')
print('Overview overlay-aware cold/warm entries PASS')
