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
        live=context.new_page();live.goto(os_origin)
        def enter():
            with context.expect_page() as new:live.get_by_role('link',name='Dev Mode',exact=True).click()
            page=new.value;page.on('pageerror',lambda e:errors.append(str(e)))
            page.wait_for_timeout(1000)
            if not any('/pair' in p.url and not p.is_closed() for p in context.pages):page.locator('#connect').click()
            bridge=next(p for p in reversed(context.pages) if '/pair' in p.url)
            expect(bridge.locator('#approve')).to_be_disabled(timeout=20000)
            try:expect(bridge.locator('#open')).to_be_visible(timeout=20000);bridge.locator('#open').click()
            except Exception:
                if not page.locator('#ws-image').is_visible():raise
            expect(page.locator('#ws-image')).to_be_visible(timeout=120000)
            expect(page.locator('#ws-loading')).to_be_hidden(timeout=120000)
            return page,bridge
        start=time.monotonic();dev,bridge=enter();report['timings']['cold_entry']=round(time.monotonic()-start,2)
        container=server.preview_runtime.container_id
        # Ordinary OS sidebar click, passed through the real raster interaction handler.
        target=next(t for t in server.preview_runtime.last_frame['navigation_targets'] if t['page']=='orders')
        image=dev.locator('#ws-image').bounding_box();frame=server.preview_runtime.last_frame
        dev.locator('#ws-image').click(position={'x':target['x']*image['width']/frame['width'],'y':target['y']*image['height']/frame['height']})
        expect(dev.locator('#ws-loading')).to_be_hidden(timeout=30000);expect(dev.locator('#ws-page')).to_have_value('orders')
        assert 'orders_page.py' in dev.locator('#ws-list').inner_text()
        assert server.preview_runtime.container_id==container
        # Mapped sections remain limited. HTML is the real authorised custom component.
        dev.locator('#ws-list').get_by_role('button',name='components/sports_cave_top_bar/index.html',exact=False).click()
        expect(dev.locator('#ed-source')).to_be_visible();original=dev.locator('#ed-source').input_value()
        assert '<' in original;dev.locator('#ed-wrap').check();assert dev.locator('#ed-source').get_attribute('wrap')=='soft'
        print(json.dumps({'editor_state':dev.locator('#ed-source').evaluate('e => ({disabled:e.disabled,readOnly:e.readOnly,hidden:e.hidden,rect:e.getBoundingClientRect().toJSON()})'),'errors':errors,'status':dev.locator('#ed-status').inner_text()}),flush=True)
        dev.screenshot(path=str(root/'docs/v9-source-state.png'))
        dev.locator('#ed-wrap').uncheck();dev.locator('#ed-source').press('Control+Home',timeout=5000);dev.locator('#ed-source').press_sequentially('<!-- V9 unsaved recovery test -->',delay=5,timeout=10000);print('Short native HTML edit completed',flush=True)
        dev.locator('#ws-page').select_option('mockups');expect(dev.locator('#ws-loading')).to_be_hidden(timeout=30000)
        assert 'V9 unsaved recovery test' in dev.locator('#ed-source').input_value()
        # Explicitly leave a test tab; the existing recovery buffer must survive.
        dev.on('dialog',lambda d:d.accept());dev.close();bridge.close()
        start=time.monotonic();dev,bridge=enter();report['timings']['warm_reopen']=round(time.monotonic()-start,2)
        expect(dev.locator('#ed-source')).to_be_visible();assert 'V9 unsaved recovery test' in dev.locator('#ed-source').input_value()
        assert server.preview_runtime.container_id==container
        assert (root/editor.CODE_FILES[0]).read_bytes()==before[editor.CODE_FILES[0]]
        # Return the test recovery buffer to its original source without a save/revision.
        dev.locator('#ws-undo').click();expect(dev.locator('#ed-status')).to_contain_text('Local edits undone',timeout=10000)
        dev.locator('#ws-save').click();expect(dev.locator('#ws-loading')).to_be_hidden(timeout=20000)
        assert (root/editor.CODE_FILES[0]).read_bytes()==before[editor.CODE_FILES[0]]
        dev.locator('#ws-left-toggle').click();assert dev.locator('.ws-left').is_hidden()
        dev.locator('#ws-left-toggle').click();assert dev.locator('.ws-left').is_visible()
        dev.locator('.ws-resize').focus();dev.keyboard.press('ArrowRight');expect(dev.locator('#ws-loading')).to_be_hidden(timeout=20000)
        # Clean screenshot: current source + full synthetic application.
        dev.locator('#ws-page').select_option('dashboard');expect(dev.locator('#ws-loading')).to_be_hidden(timeout=30000)
        dev.screenshot(path=str(root/'docs/v9-dev-mode-final.png'))
        dev.locator('.ws-more summary').click();dev.locator('#ws-stop').click();expect(dev.locator('#ws-status')).to_contain_text('Preview stopped',timeout=20000)
        dev.on('dialog',lambda d:d.accept());dev.close();bridge.close();browser.close()
    assert not errors,errors;assert launches and all(x['silent'] for x in launches)
    report.update(real_sidebar_navigation=True,navigator_follows_actual_page=True,real_custom_html_opens=True,word_wrap=True,unsaved_buffer_survives_navigation_and_reopen=True,warm_reopen_same_container=True,sidebar_resize_and_collapse=True,silent_launches=len(launches),javascript_errors=errors)
    print(json.dumps(report),flush=True)
except Exception as error:
    print(json.dumps({'failure':str(error).splitlines()[0],'errors':errors,'last_log':str(error).splitlines()[-5:]}),flush=True)
    raise RuntimeError('Focused V9 follow-up failed; see diagnostics') from None
finally:
    subprocess.Popen=real_popen;server.stopping=True;server_thread.join(20);surface.shutdown();surface.server_close()
    report['source_restored']=all((root/path).read_bytes()==data for path,data in before.items())
    (root/'docs/v9-dev-mode-reopen.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
