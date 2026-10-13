"""Real installed Edge and Docker; disposable V9 task, never the revision 6 draft."""
import sys,json,time,threading,hashlib,subprocess
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
root=Path(__file__).resolve().parents[2] if 'scripts' in str(Path(__file__)) else Path('C:/Users/hello/.codex/visualizations/2026/10/12/01a13216-edba-7c20-896a-70f604c44d7e/v9/sports-cave-core-dev-mode-v9-dev')
home=root.parent;task='v9-dev';owner='codex/v9-01a13216'
sys.path.insert(0,str(root/'scripts/studio'));sys.path.insert(0,str(root))
import studio,drafts,draft_ui,device_trust,application_drafts,developer_studio_page,editor
from playwright.sync_api import sync_playwright,expect
registry=studio.read(home/'.studio/registry.json')
draft=next((d for d in registry.get('drafts',[]) if d['task_id']==task),None)
if not draft:draft=drafts.new(home,task,owner,'V9 isolated acceptance')
# A test application record derived from the known base, solely in the isolated task.
with studio.locked(home) as file:
    registry=studio.read(file);draft=next(d for d in registry['drafts'] if d['task_id']==task)
    draft['kind']='application';draft['production_base']={'service_id':application_drafts.SERVICE,'repository':application_drafts.REPOSITORY,'status':'live','deployment_id':'synthetic-test-provenance','evidence':'Test fixture only; never a Live verification receipt','revision':draft['base_commit']}
    studio.atomic(file,registry)
application_drafts.remember_selection(home,draft['id'],owner)
server=draft_ui.DraftServer(home,task,owner,persistent=True)
server_thread=threading.Thread(target=server.run,daemon=True);server_thread.start()
class Surface(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        content=developer_studio_page.panel_html().replace('http://127.0.0.1:18762',server.origin) if self.path.startswith('/dev') else '<title>Local entry acceptance — Live unchanged</title><a href="/dev" target="_blank" rel="noopener">Dev Mode</a><p id="live">Live entry fixture stays open</p>'
        data=content.encode();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
surface=ThreadingHTTPServer(('127.0.0.1',0),Surface);surface_thread=threading.Thread(target=surface.serve_forever,daemon=True);surface_thread.start()
os_origin='http://127.0.0.1:'+str(surface.server_port)
secret,_=server.device.enroll(os_origin,'');cookie='studio_device_'+str(server.server_port)+'_'+device_trust.digest(os_origin)[:16]
before={path:(root/path).read_bytes() for path in ['app.py',editor.CODE_FILES[0],'orders_page.css']}
report={'scope':'Real visible Windows Edge; synthetic Live entry fixture, isolated V9 application task and real Docker; existing 18762 companion unchanged','timings':{}};errors=[];launches=[];real_popen=subprocess.Popen
def popen(*args,**kwargs):
    command=args[0] if args else kwargs.get('args')
    if isinstance(command,list) and Path(command[0]).name.lower() in ('docker','docker.exe','git','git.exe'):
        launches.append({'program':command[0],'silent':bool(kwargs.get('creationflags',0)&subprocess.CREATE_NO_WINDOW)})
    return real_popen(*args,**kwargs)
try:
    subprocess.Popen=popen
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(channel='msedge',headless=False)
        context=browser.new_context(viewport={'width':1600,'height':1000})
        context.add_cookies([{'name':cookie,'value':secret,'domain':'127.0.0.1','path':'/api/device','httpOnly':True,'sameSite':'Strict'}])
        context.route('**/*',lambda r:r.continue_() if r.request.url.startswith((server.origin,os_origin,'data:','blob:')) else r.abort())
        live=context.new_page();live.goto(os_origin);start=time.monotonic()
        with context.expect_page() as new_tab:live.get_by_role('link',name='Dev Mode',exact=True).click()
        dev=new_tab.value;dev.on('pageerror',lambda e:errors.append(str(e)))
        expect(dev.locator('#connect')).to_be_visible()
        # Browser user gesture fallback, using already seeded test-profile trust.
        dev.wait_for_timeout(1000)
        if not any('/pair' in p.url for p in context.pages):dev.locator('#connect').click()
        bridge=next(p for p in reversed(context.pages) if '/pair' in p.url)
        expect(bridge.locator('#approve')).to_be_disabled(timeout=20000)
        if not server.workspace_grants:
            expect(bridge.locator('#open')).to_be_visible(timeout=20000)
            bridge.locator('#open').click() # Existing local editing-grant confirmation is retained.
        expect(dev.locator('#ws-image')).to_be_visible(timeout=120000);expect(dev.locator('#ws-loading')).to_be_hidden(timeout=120000)
        report['timings']['entry_to_full_preview']=round(time.monotonic()-start,2)
        expect(dev).to_have_title('Sports Cave OS — DEV');expect(live.locator('#live')).to_have_text('Live entry fixture stays open')
        assert len([p for p in context.pages if p.url.startswith(os_origin+'/dev')])==1
        assert server.preview_runtime.container_id;container=server.preview_runtime.container_id
        assert dev.locator('#editor-panel').is_visible();assert dev.locator('.ws-right').count()==0
        assert not dev.get_by_role('button',name='Edit Page',exact=True).count()
        assert 'Synthetic Preview Admin' in server.preview_runtime.last_frame['text']
        box=dev.locator('.ws-frame-area').bounding_box();assert box['width']>1000 and box['height']>700,box
        report['preview_area']=box
        start=time.monotonic();dev.locator('#ws-page').select_option('orders');expect(dev.locator('#ws-loading')).to_be_hidden(timeout=30000)
        report['timings']['warm_page']=round(time.monotonic()-start,2)
        assert server.preview_runtime.container_id==container
        # Authorised source loads inside the left editing workspace.
        dev.get_by_role('button',name='Files',exact=True).click()
        dev.locator('#ws-list').get_by_role('button',name='orders_page.css',exact=False).click()
        expect(dev.locator('#ed-source')).to_be_visible();original_css=dev.locator('#ed-source').input_value()
        dev.locator('#ed-source').fill(original_css+'\n/* V9 isolated acceptance */\n')
        dev.locator('#ws-page').select_option('dashboard');expect(dev.locator('#ws-loading')).to_be_hidden(timeout=30000)
        assert 'V9 isolated acceptance' in dev.locator('#ed-source').input_value(),'Navigation lost unsaved source'
        dev.locator('#ws-save').click();expect(dev.locator('#ed-status')).to_contain_text('Saved to the actual draft',timeout=30000)
        expect(dev.locator('#ws-loading')).to_be_hidden(timeout=30000);assert b'V9 isolated acceptance' in (root/'orders_page.css').read_bytes()
        dev.locator('#ws-undo').click();expect(dev.locator('#ws-loading')).to_be_hidden(timeout=30000)
        expect(dev.locator('#ed-status')).to_contain_text('Saved to the actual draft',timeout=30000);assert (root/'orders_page.css').read_bytes()==before['orders_page.css']
        dev.get_by_role('button',name='Pages',exact=True).click();dev.locator('#ws-page').select_option('__signin__')
        expect(dev.locator('#ws-loading')).to_be_hidden(timeout=30000)
        dev.locator('#ws-list').get_by_role('button',name='Sign-in heading',exact=False).click()
        expect(dev.locator('#ed-text')).to_be_visible();expect(dev.locator('#ws-outline')).to_be_visible()
        original=dev.locator('#ed-text').input_value();dev.locator('#ed-text').fill(original+' V9')
        start=time.monotonic();dev.locator('#ws-save').click();expect(dev.locator('#ed-status')).to_contain_text('Saved to the actual draft',timeout=30000)
        expect(dev.locator('#ws-loading')).to_be_hidden(timeout=30000);report['timings']['save_to_preview']=round(time.monotonic()-start,2)
        assert ' V9' in server.preview_runtime.last_frame['text'];assert server.preview_runtime.container_id==container
        dev.locator('#ws-undo').click();expect(dev.locator('#ws-loading')).to_be_hidden(timeout=30000)
        expect(dev.locator('#ed-status')).to_contain_text('Saved to the actual draft',timeout=30000);assert (root/'app.py').read_bytes()==before['app.py']
        dev.locator('#ws-history').click();expect(dev.locator('#ed-history')).to_be_visible();assert dev.locator('#ed-history option').count()>=2
        for mode in ('Tablet','Mobile','Desktop'):
            dev.get_by_role('button',name=mode,exact=True).click();expect(dev.locator('#ws-loading')).to_be_hidden(timeout=20000)
        dev.locator('#ws-page').select_option('dashboard');expect(dev.locator('#ws-loading')).to_be_hidden(timeout=30000)
        dev.screenshot(path=str(root/'docs/v9-dev-mode-edge.png'))
        dev.locator('.ws-more summary').click();dev.locator('#ws-stop').click();expect(dev.locator('#ws-status')).to_contain_text('Preview stopped',timeout=20000)
        assert server.preview_runtime.name is None
        dev.close();bridge.close();browser.close()
    assert not errors,errors;assert launches and all(x['silent'] for x in launches),launches
    report.update(separate_tab_live_unchanged=True,automatic_test_application_selection=True,reused_existing_test_device_trust=True,explicit_editing_grant_retained=True,always_available_editor=True,full_viewport=True,authorised_css_save_and_undo=True,mapped_selection_save_and_undo=True,history=True,responsive=True,same_container=True,silent_background_launches=len(launches),javascript_errors=errors)
    print(json.dumps(report),flush=True)
finally:
    subprocess.Popen=real_popen;server.stopping=True;server_thread.join(20);surface.shutdown();surface.server_close()
    # Do not silently overwrite source on failure; retain test revision history for review.
    report['source_restored']=all((root/path).read_bytes()==data for path,data in before.items())
    (root/'docs/v9-dev-mode-edge.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
