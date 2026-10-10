"""Controlled local read latency, failures and unsaved history protection."""
import json,os,time
from pathlib import Path
from playwright.sync_api import sync_playwright
base='http://127.0.0.1:'+os.environ['AUTOMATIONS_V5_PORT']+'/'
results={}
with sync_playwright() as pw:
    for channel in ('chrome','msedge'):
        browser=pw.chromium.launch(channel=channel,headless=True)
        context=browser.new_context(viewport={'width':1440,'height':1000})
        context.route('**/*',lambda r:r.continue_() if r.request.url.startswith(('http://127.0.0.1','ws://127.0.0.1','data:')) else r.abort())
        page=context.new_page();page.set_default_timeout(20000);results[channel]={}
        page.goto(base+'?page=crm_automations_manage&fixture_fail_identity=1')
        page.get_by_text('Automation list unavailable — retry. Navigation remains available.',exact=True).wait_for()
        runs=page.locator('#v5-render').get_attribute('data-runs');page.wait_for_timeout(2500)
        assert page.locator('#v5-render').get_attribute('data-runs')==runs
        page.locator('.st-key-sidebar-row-dashboard button:visible').first.click()
        page.get_by_role('heading',name='Dashboard',exact=True).wait_for()
        results[channel]['failed_identity_shell_navigation']='PASS'
        started=time.perf_counter();page.goto(base+'?page=crm_automations_manage&fixture_latency_ms=150')
        page.locator('.sc-auto-row').first.wait_for();page.get_by_role('textbox',name='Search automations',exact=True).wait_for()
        results[channel]['150ms_per_sql_overview_ms']=round((time.perf_counter()-started)*1000,2)
        assert not page.get_by_role('textbox',name='Search automations',exact=True).is_disabled()
        page.goto(base+'?page=crm_automations_manage')
        link=page.locator('.sc-auto-name a').filter(has_text='V5 welcome 3 stages');link.wait_for()
        href=link.get_attribute('href')
        link.focus();link.press('Enter')
        page.get_by_role('button',name='Edit Email',exact=True).nth(2).wait_for()
        page.get_by_role('button',name='← Automations',exact=True).click();link.wait_for()
        with context.expect_page() as tab_info:link.click(modifiers=['Control'])
        new_tab=tab_info.value
        new_tab.get_by_role('button',name='Edit Email',exact=True).nth(2).wait_for();new_tab.close()
        assert page.locator('.sc-auto-row').count()>0
        results[channel]['keyboard_and_modifier_deep_link']='PASS'
        page.goto(base+href+'&fixture_fail_definition=1')
        page.get_by_role('button',name='Retry opening editor',exact=True).wait_for()
        page.get_by_role('button',name='← Automations',exact=True).click()
        page.locator('.sc-auto-row').first.wait_for()
        results[channel]['failed_definition_can_return']='PASS'
        page.goto(base+'?page=crm_automations_manage')
        first=page.locator('.sc-auto-name a').filter(has_text='V5 welcome 3 stages');second=page.locator('.sc-auto-name a').filter(has_text='V5 post_purchase 3 stages')
        first.wait_for();second.wait_for();page.wait_for_timeout(1200)
        page.evaluate("window.v5Rapid=[];document.addEventListener('click',e=>{const a=e.target.closest?.('a[data-flow-open]');if(a)window.v5Rapid.push(a.textContent)},true)")
        first.scroll_into_view_if_needed();a=first.bounding_box();b=second.bounding_box()
        page.mouse.click(a['x']+5,a['y']+5);page.mouse.click(b['x']+5,b['y']+5)
        try:page.locator('.automation-title strong').filter(has_text='V5 post_purchase 3 stages').wait_for()
        except Exception:
            print('RAPID DEBUG',page.url,page.evaluate('window.v5Rapid'),page.locator('.automation-title strong').all_text_contents(),flush=True);raise
        assert page.evaluate('window.v5Rapid')==['V5 welcome 3 stages','V5 post_purchase 3 stages']
        page.go_back();page.go_forward()
        page.locator('.automation-title strong').filter(has_text='V5 post_purchase 3 stages').wait_for()
        page.wait_for_timeout(500)
        assert page.locator('.automation-title strong').inner_text()=='V5 post_purchase 3 stages'
        results[channel]['rapid_flow_clicks_and_history']='PASS'
        page.goto(base+'?page=crm_automations_manage&fixture_latency_ms=150')
        first=page.locator('.sc-auto-name a').filter(has_text='V5 welcome 3 stages');second=page.locator('.sc-auto-name a').filter(has_text='V5 post_purchase 3 stages')
        first.wait_for();second.wait_for();page.wait_for_timeout(1800)
        first.scroll_into_view_if_needed();a=first.bounding_box();b=second.bounding_box()
        page.mouse.click(a['x']+5,a['y']+5)
        # The first native commit is already in flight before the second click.
        page.wait_for_timeout(70);page.mouse.click(b['x']+5,b['y']+5)
        page.locator('.automation-title strong').filter(has_text='V5 post_purchase 3 stages').wait_for()
        page.wait_for_timeout(500)
        assert page.locator('.automation-title strong').inner_text()=='V5 post_purchase 3 stages'
        results[channel]['latest_click_with_inflight_slow_read']='PASS'
        page.goto(base+'?page=crm_automations_manage&fixture_fail_save=1')
        page.locator('.sc-auto-name a').filter(has_text='V5 welcome 3 stages').click()
        page.get_by_role('button',name='Edit Email',exact=True).first.click()
        subject=page.get_by_role('textbox',name='Subject',exact=True);subject.wait_for()
        desired='V5 retained after synthetic save failure';subject.fill(desired);subject.press('Tab')
        page.get_by_role('button',name='← Automations',exact=True).click()
        page.get_by_text('Save failed. Your automation edits are retained; retry before leaving.',exact=True).wait_for()
        subject.wait_for();assert subject.input_value()==desired
        assert 'automation=' in page.url
        results[channel]['failed_save_retains_editor_and_url']='PASS'
        assert page.get_by_test_id('stException').count()==0
        browser.close()
Path('tmp/automations-v5-faults.json').write_text(json.dumps(results,indent=2));print(json.dumps(results,indent=2))
