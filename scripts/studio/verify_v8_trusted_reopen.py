import sys,json,threading,urllib.request,tempfile
from pathlib import Path
from http.server import HTTPServer
root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root/'scripts/studio'))
from playwright.sync_api import sync_playwright,expect
from test_application_drafts import ApplicationDraftTests
from verify_phase4a_browser import Panel
import draft_ui,studio
fixture=ApplicationDraftTests();fixture.setUp()
draft=fixture.create(default=True)
server=draft_ui.DraftServer(fixture.home,fixture.task['id'],'owner',persistent=True)
port=server.server_port
panel=HTTPServer(('127.0.0.1',0),Panel)
panel_origin='http://127.0.0.1:'+str(panel.server_port)
thread=threading.Thread(target=server.run,daemon=True);thread.start()
panel_thread=threading.Thread(target=panel.serve_forever,daemon=True);panel_thread.start()
errors=[]
def setup_url():
    request=urllib.request.Request(server.origin+'/api/device',data=json.dumps({'operation':'prepare','origin':panel_origin}).encode(),headers={'Content-Type':'application/json','Origin':server.origin,'X-Studio-Local':'1','X-Studio-Token':server.token})
    with urllib.request.urlopen(request) as response:return json.load(response)['url']
def connect(context):
    page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(panel_origin)
    page.locator('#connection-settings summary').click();page.locator('#origin').fill(server.origin)
    with page.expect_popup() as popup:page.locator('#connect').click()
    return page,popup.value
try:
    with tempfile.TemporaryDirectory(prefix='v8-edge-fixture-') as profile,sync_playwright() as playwright:
        def launch():
            context=playwright.chromium.launch_persistent_context(profile,channel='msedge',headless=True,viewport={'width':1440,'height':900})
            context.route('**/*',lambda r:r.continue_() if r.request.url.startswith(('http://127.0.0.1:','data:','blob:')) else r.abort())
            return context
        context=launch();page,local=connect(context)
        expect(local.locator('#status')).to_contain_text('No usable saved trust')
        setup=context.new_page();setup.goto(setup_url());setup.locator('#approve').click()
        expect(setup.locator('#status')).to_contain_text('Computer trusted')
        expect(page.locator('#connection')).to_contain_text('connected')
        expect(local.locator('#handoff')).to_be_visible();local.locator('#open').click()
        expect(page.locator('#ws-title')).to_have_text('Sports Cave OS copy')
        expect(page.locator('#revision-summary')).to_contain_text(fixture.sha)
        page.get_by_role('button',name='Files',exact=True).click()
        page.locator('#ws-list').get_by_role('button',name='app.py',exact=False).click()
        page.locator('#ed-text').fill('Persistent Edge V8 Save Draft acceptance')
        page.locator('#ws-save').click()
        expect(page.locator('#ed-status')).to_contain_text('Saved to the actual draft')
        first_expiry=next(iter(server.device.read()['records'].values()))['expires']
        assert json.loads((fixture.home/'.studio/application-selections.json').read_text())['owner']==draft['id']
        context.close()
        server.stopping=True;thread.join(10);assert not thread.is_alive()
        server=draft_ui.DraftServer(fixture.home,fixture.task['id'],'owner',persistent=True,port=port)
        thread=threading.Thread(target=server.run,daemon=True);thread.start()
        context=launch();page,local=connect(context)
        expect(page.locator('#connection')).to_contain_text('connected')
        expect(local.locator('#approve')).to_be_disabled()
        expect(local.locator('#handoff')).to_be_visible();local.locator('#open').click()
        expect(page.locator('#ws-title')).to_have_text('Sports Cave OS copy')
        page.get_by_role('button',name='Files',exact=True).click()
        page.locator('#ws-list').get_by_role('button',name='app.py',exact=False).click()
        expect(page.locator('#ed-text')).to_have_value('Persistent Edge V8 Save Draft acceptance')
        assert next(iter(server.device.read()['records'].values()))['expires']==first_expiry
        assert len(server.device.read()['records'])==1
        page.screenshot(path=str(root/'docs/v8-performance-trust.png'))
        context.close()
        server.stopping=True;thread.join(10);assert not thread.is_alive()
        assert server.catalog()['default_draft_id']==draft['id']
        assert not errors,errors
        result={'actual_installed_edge':True,'scope':'Disposable persistent Edge profile, synthetic local OS panel and application worktrees','authenticated_one_time_setup':True,'browser_and_companion_restart_trust_survives':True,'same_immutable_draft_opens_without_manual_selection':True,'local_edit_confirmation_preserved':True,'save_draft_loaded_after_restart':True,'fixed_30_day_expiry_preserved':True,'browser_errors':errors}
        (root/'docs/v8-performance-trust.json').write_text(json.dumps(result,indent=2))
        print(json.dumps(result))
finally:
    server.stopping=True;thread.join(10)
    panel.shutdown();panel.server_close()
    fixture.doCleanups()
