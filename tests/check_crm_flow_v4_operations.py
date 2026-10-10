"""Browser actions on disposable SQL fixtures only; never lifecycle or sending."""
import json,time,os,statistics
from pathlib import Path
from playwright.sync_api import sync_playwright
result={};errors=[]
def measure(name,fn):
    t=time.perf_counter();fn();result.setdefault(name,[]).append(round(1000*(time.perf_counter()-t),2))
with sync_playwright() as pw:
    browser=pw.chromium.launch(channel=os.getenv('FLOW_V4_CHANNEL','chrome'),headless=True)
    context=browser.new_context(viewport={'width':1440,'height':1000})
    context.route('**/*',lambda r:r.continue_() if r.request.url.startswith(('http://127.0.0.1','ws://127.0.0.1','data:')) else r.abort())
    page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
    page.set_default_timeout(25000)
    base='http://127.0.0.1:'+os.getenv('FLOW_V4_OPERATIONS_PORT','8567')+'/?fixture_checkout=1&fixture_steps=3&fixture_checkout_live=1&fixture_run=flow-v4-'+str(time.time_ns())
    page.goto(base)
    rows=page.locator('[class*="st-key-flow-row-"]')
    rows.nth(2).wait_for(timeout=60000)
    def settled():
        # Await completion of Streamlit's post-save sibling fragment refresh,
        # rather than clicking a menu while its preceding DOM is being replaced.
        page.evaluate("""() => new Promise(resolve => {
          let timer; const done=()=>{observer.disconnect();resolve();};
          const reset=()=>{clearTimeout(timer);timer=setTimeout(done,300);};
          const observer=new MutationObserver(reset);
          observer.observe(document.querySelector('.st-key-flow-workspace'),{childList:true,subtree:true});reset();
        })""")
    for i in range(6):
        measure('real_editor_open_ms',lambda:(page.get_by_role('button',name='Edit Email',exact=True).first.click(),page.get_by_role('textbox',name='Subject',exact=True).wait_for()))
        measure('real_editor_return_ms',lambda:(page.get_by_role('button',name='Flow',exact=True).click(),rows.nth(2).wait_for()))
    def menu():
        settled()
        page.locator('.sc-flow-stats').click()
        page.wait_for_function("[...document.querySelectorAll('[data-testid=stPopoverBody]')].every(e=>!e.getClientRects().length)")
        rows.first.get_by_role('button',name='⋮',exact=True).click()
        page.get_by_role('textbox',name='Email name',exact=True).wait_for()
    menu();page.get_by_role('spinbutton',name='Delay',exact=True).fill('31')
    page.get_by_role('button',name='Save step',exact=True).click()
    page.get_by_text('31 minutes after trigger · Enabled',exact=True).wait_for()
    menu();page.get_by_role('button',name='Duplicate',exact=True).click();rows.nth(3).wait_for()
    page.keyboard.press('Escape');menu();page.get_by_role('button',name='Move down',exact=True).click()
    page.keyboard.press('Escape');page.get_by_role('button',name='+ Add Email',exact=True).click();rows.nth(4).wait_for()
    page.reload();rows.nth(4).wait_for()
    page.get_by_role('button',name='Refresh analytics',exact=True).click()
    page.get_by_role('button',name='Diagnostics',exact=True).click()
    page.get_by_role('button',name='Open operational diagnostics',exact=True).click()
    page.get_by_text('Operational diagnostics',exact=True).wait_for()
    page.get_by_role('button',name='← Back to Flow',exact=True).click();rows.nth(4).wait_for()
    assert page.get_by_test_id('stException').count()==0
    assert not errors,errors
    result['result']='PASS save/duplicate/reorder/add/reload/analytics/admin route/actual editor transitions; no publication or sending controls activated'
    for key in list(result):
        if isinstance(result[key],list):result[key+'_summary']={'n':len(result[key]),'p50':statistics.median(result[key]),'p95':max(result[key])}
    browser.close()
Path('tmp/flow-v4-operations-'+os.getenv('FLOW_V4_CHANNEL','chrome')+'.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
