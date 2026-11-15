"""Click-to-visible/interactivity on production router and actual CRM SQL pages."""
import json, os, statistics, time
from pathlib import Path
from playwright.sync_api import sync_playwright,TimeoutError
RESULT={};base='http://127.0.0.1:'+os.environ['AUTOMATIONS_V5_PORT']+'/'
def measure(page,values,name,action,ready):
    kind='editor' if name=='flow_to_editor' else 'overview' if 'to_overview' in name else 'flow'
    page.evaluate('(kind)=>sessionStorage.setItem("v5-expected-view",kind)',kind)
    docs=page.v5_documents;websockets=page.v5_websockets
    full_runs=int(page.locator('#v5-render').get_attribute('data-runs'))
    start=time.perf_counter();action()
    try:ready()
    except TimeoutError:
        values.setdefault('failed_transitions',[]).append({'journey':name,'elapsed_ms':round((time.perf_counter()-start)*1000,2)})
        if os.environ['AUTOMATIONS_V5_VARIANT']!='before':raise
        # Preserve the baseline failure as evidence, then explicitly retry so
        # the remaining matrix can be measured. Never count it as a success.
        for attempt in range(3):
            page.reload()
            page.wait_for_timeout(5000)
            try:
                action();ready();return
            except TimeoutError:
                values.setdefault('failed_transitions',[]).append({'journey':name,'recovery_attempt':attempt+1})
        raise
    values.setdefault(name,[]).append(round((time.perf_counter()-start)*1000,2))
    values.setdefault(name+'_click_to_ready',[]).append(page.evaluate('Date.now()-Number(sessionStorage.getItem("v5-click-absolute"))'))
    values.setdefault(name+'_paints',[]).append(page.evaluate('window.v5Paints'))
    values.setdefault(name+'_documents',[]).append(page.v5_documents-docs)
    values.setdefault(name+'_websockets',[]).append(page.v5_websockets-websockets)
    values.setdefault(name+'_full_runs',[]).append(int(page.locator('#v5-render').get_attribute('data-runs')) if page.v5_documents!=docs else int(page.locator('#v5-render').get_attribute('data-runs'))-full_runs)
with sync_playwright() as pw:
    for channel in os.getenv('AUTOMATIONS_V5_CHANNELS','chrome,msedge').split(','):
        browser=pw.chromium.launch(channel=channel,headless=True)
        context=browser.new_context(viewport={'width':1440,'height':1000})
        context.add_init_script(Path('tests/fixtures/automation_v5_paint.js').read_text())
        context.route('**/*',lambda r:r.continue_() if r.request.url.startswith(('http://127.0.0.1','ws://127.0.0.1','data:')) else r.abort())
        page=context.new_page();page.set_default_timeout(8000)
        page.v5_documents=0;page.v5_websockets=0
        def request_seen(request):
            if request.resource_type=='document' and request.is_navigation_request() and request.frame==page.main_frame:page.v5_documents+=1
        def socket_seen(socket):page.v5_websockets+=1
        page.on('request',request_seen);page.on('websocket',socket_seen)
        for steps in map(int,os.getenv('AUTOMATIONS_V5_STEPS','1,3,6,12').split(',')):
            page.set_viewport_size({'width':1440,'height':1000})
            values={};RESULT[channel+'-'+str(steps)]=values
            page.goto(base+'?fixture_steps='+str(steps));page.get_by_role('heading',name='Dashboard',exact=True).wait_for()
            page.evaluate('(count)=>sessionStorage.setItem("v5-stages",String(count))',steps)
            def overview():page.locator('.sc-auto-row').first.wait_for();page.get_by_role('textbox',name='Search automations',exact=True).wait_for()
            def flow():page.get_by_role('button',name='Edit Email',exact=True).nth(steps-1).wait_for();page.get_by_role('button',name='Save draft',exact=True).wait_for()
            def open_flow():
                page.locator('.sc-auto-name a').filter(has_text='V5 welcome '+str(steps)+' stages').click()
            # Actual production sidebar disclosure and route button.
            page.locator('[class*="st-key-sidebar-disclosure-email-"] button:visible').first.click()
            measure(page,values,'os_to_overview_cold',lambda:page.locator('.st-key-sidebar-row-crm_automations_manage button:visible').first.click(),overview)
            values['os_feedback_ms']=page.evaluate('window.v5Feedback')
            for i in range(int(os.getenv('AUTOMATIONS_V5_SAMPLES',6))):
                measure(page,values,'overview_to_flow',open_flow,flow)
                if os.environ['AUTOMATIONS_V5_VARIANT']=='after':values.setdefault('flow_feedback_ms',[]).append(page.evaluate('window.v5Feedback'))
                measure(page,values,'flow_to_editor',lambda:page.get_by_role('button',name='Edit Email',exact=True).first.click(),lambda:page.get_by_role('textbox',name='Subject',exact=True).wait_for())
                measure(page,values,'editor_to_flow',lambda:page.get_by_role('button',name='Flow',exact=True).click(),flow)
                measure(page,values,'flow_to_overview',lambda:page.get_by_role('button',name='← Automations',exact=True).click(),overview)
            values['flow_widths']={}
            values['width_navigation']={}
            open_flow();flow()
            for width in (1920,1440,1366,1024,750,390,320):
                page.set_viewport_size({'width':width,'height':1000});flow()
                values['flow_widths'][str(width)]=page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
                if os.environ['AUTOMATIONS_V5_VARIANT']=='after':
                    probe={}
                    measure(page,probe,'flow_to_overview',lambda:page.get_by_role('button',name='← Automations',exact=True).click(),overview)
                    measure(page,probe,'overview_to_flow',open_flow,flow)
                    values['width_navigation'][str(width)]=probe
                    if steps==12 and width in (1440,320):
                        evidence=Path('docs/automations-v5-evidence');evidence.mkdir(exist_ok=True)
                        page.screenshot(path=str(evidence/f'{channel}-flow-12-{width}.png'),full_page=True)
            page.set_viewport_size({'width':1440,'height':1000})
            measure(page,values,'width_probe_return',lambda:page.get_by_role('button',name='← Automations',exact=True).click(),overview)
            if os.environ['AUTOMATIONS_V5_VARIANT']=='after':
                open_flow();flow();page.go_back()
                try:overview()
                except TimeoutError:
                    print('HISTORY DEBUG',page.url,page.evaluate('''({marker:document.querySelector('[data-automation-route]')?.dataset.automationRoute,pending:document.body.className,controller:document.querySelector('#sports-cave-os-top-bar')?.dataset})'''))
                    for frame in page.frames:
                        if frame!=page.main_frame:
                            print('FRAME DEBUG',frame.evaluate('document.querySelector("#sports-cave-os-top-bar")?.dataset || document.body.innerHTML.slice(0,150)'))
                    raise
                page.go_forward();flow()
                page.reload();flow()
                page.get_by_role('button',name='← Automations',exact=True).click();overview()
                values['history_reload']='PASS'
            # Optional settlement must not replace interactive controls.
            runs=page.locator('#v5-render').get_attribute('data-runs')
            page.wait_for_timeout(4500)
            values['full_runs_during_settlement']=int(page.locator('#v5-render').get_attribute('data-runs'))-int(runs)
            values['overview_settled_paints']=page.evaluate('window.v5Paints')
            assert page.get_by_test_id('stException').count()==0
            values['widths']={}
            for width in (1920,1440,1366,1024,750,390,320):
                page.set_viewport_size({'width':width,'height':1000});overview()
                values['widths'][str(width)]=page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
            for key,samples in list(values.items()):
                if isinstance(samples,list) and samples and isinstance(samples[0],(int,float)):values[key+'_summary']={'n':len(samples),'p50':statistics.median(samples),'p95':sorted(samples)[-1]}
            Path('tmp/automations-v5-'+os.environ['AUTOMATIONS_V5_VARIANT']+'.json').write_text(json.dumps(RESULT,indent=2))
        browser.close()
path=Path('tmp/automations-v5-'+os.environ['AUTOMATIONS_V5_VARIANT']+'.json');path.write_text(json.dumps(RESULT,indent=2));print(path)
