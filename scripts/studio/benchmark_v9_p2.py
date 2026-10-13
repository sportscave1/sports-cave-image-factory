"""Repeated installed Edge/Docker measurements in this assigned disposable CORE task.

Never connects to 18762 or loads personal browser profiles/production origins.
Timing starts after the required local editing confirmation is clicked.
"""
import sys,json,time,threading,subprocess,statistics,math,hashlib,argparse
from pathlib import Path
from collections import Counter
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
root=Path(__file__).resolve().parents[2]; home=root.parent
sys.path[:0]=[str(root/'scripts/studio'),str(root)]
import studio,drafts,draft_ui,device_trust,application_drafts,developer_studio_page,editor
from playwright.sync_api import sync_playwright,expect

def main():
    parser=argparse.ArgumentParser();parser.add_argument('phase');parser.add_argument('--warm-only',action='store_true');parser.add_argument('--editor-only',action='store_true');parser.add_argument('--baseline-host',action='store_true');args=parser.parse_args()
    if args.baseline_host:
        # Frozen verified V9 code in this process only. Never replace worktree files.
        import ast,types,preview_runtime
        def blob(path):return subprocess.check_output(['git','-C',str(root),'show','c646cf0a6c69a71a5b4ee16a4c3778805761131e:'+path],text=True,encoding='utf-8',creationflags=subprocess.CREATE_NO_WINDOW)
        node=next(n for n in ast.parse(blob('scripts/studio/studio.py')).body if isinstance(n,ast.FunctionDef) and n.name=='identity')
        namespace=dict(studio.__dict__);exec(compile(ast.Module(body=[node],type_ignores=[]),'verified-baseline-identity','exec'),namespace);studio.identity=namespace['identity']
        old=types.ModuleType('verified_baseline_draft_ui');old.__file__=draft_ui.__file__;exec(compile(blob('scripts/studio/draft_ui.py'),old.__file__,'exec'),old.__dict__)
        draft_ui.DraftServer=old.DraftServer
        def baseline_panel():
            assets=root/'components/developer_studio';bundle=json.dumps({name:blob('scripts/studio/ui/'+name) for name in ('workspace.js','workspace.css','editor.js','editor.css')}).replace('</','<\\/')
            return (assets/'panel.html').read_text(encoding='utf-8').replace('/*STUDIO_CSS*/',(assets/'panel.css').read_text(encoding='utf-8')).replace('/*STUDIO_JS*/',(assets/'panel.js').read_text(encoding='utf-8')).replace('/*STUDIO_V6_BUNDLE*/',bundle)
        developer_studio_page.panel_html=baseline_panel;preview_runtime.IMAGE_TAG='sha256:5a22bde08670c241dd349f56e374ee5510a58f9f13d077831d1cd9de8746d061'
    task='v9-p2';owner='codex/v9-p2-01a13216'
    registry=studio.read(home/'.studio/registry.json')
    assert studio.task_by_id(registry,task,owner)['worktree_path']==str(root)
    draft=next((d for d in registry.get('drafts',[]) if d['task_id']==task),None)
    if not draft:draft=drafts.new(home,task,owner,'Performance test ONLY')
    with studio.locked(home) as file:
        reg=studio.read(file);d=next(d for d in reg['drafts'] if d['id']==draft['id'])
        d['kind']='application';d['production_base']={'service_id':application_drafts.SERVICE,'repository':application_drafts.REPOSITORY,'status':'live','deployment_id':'synthetic-fixture','evidence':'TEST ONLY, not a Live receipt','revision':d['base_commit']};studio.atomic(file,reg)
    application_drafts.remember_selection(home,draft['id'],owner)
    server=draft_ui.DraftServer(home,task,owner,persistent=True)
    threading.Thread(target=server.run,daemon=True).start()
    class Surface(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            data=(developer_studio_page.panel_html().replace('http://127.0.0.1:18762',server.origin) if self.path.startswith('/dev') else '<title>Synthetic Live entry</title><a href="/dev" target="_blank" rel="noopener">Dev Mode</a><p id="live">Untouched entry fixture</p>').encode()
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    surface=ThreadingHTTPServer(('127.0.0.1',0),Surface);threading.Thread(target=surface.serve_forever,daemon=True).start()
    origin='http://127.0.0.1:'+str(surface.server_port)
    secret,_=server.device.enroll(origin,'');cookie='studio_device_'+str(server.server_port)+'_'+device_trust.digest(origin)[:16]
    times={};calls=[];launches=[];errors=[];result={'phase':args.phase,'scope':'Disposable installed Edge context, synthetic local hosted entry, assigned test draft and real Docker; no active companion operations','confirmation_wait_excluded':True}
    def record(name,start):
        times.setdefault(name,[]).append((time.perf_counter()-start)*1000);print(name,round(times[name][-1],1),flush=True)
        (root/'docs'/('v9-p2-'+args.phase+'-progress.json')).write_text(json.dumps({'times':times,'calls':calls,'partial':True},indent=2))
    real_popen=subprocess.Popen
    def popen(*a,**k):
        cmd=a[0] if a else k.get('args')
        if isinstance(cmd,list) and Path(cmd[0]).name.lower() in ('docker','docker.exe','git','git.exe'):launches.append({'program':Path(cmd[0]).name,'silent':bool(k.get('creationflags',0)&subprocess.CREATE_NO_WINDOW)})
        return real_popen(*a,**k)
    # Attribute API/capability/catalogue work without exposing private arguments.
    for name in ('catalog','workspace_model','workspace_request','action'):
        fn=getattr(server,name)
        def wrap(*a,_fn=fn,_name=name,**k):
            start=time.perf_counter();count=len(launches)
            try:return _fn(*a,**k)
            finally:calls.append({'method':_name,'action':a[0].get('command',a[0]).get('action') if a and isinstance(a[0],dict) else '', 'ms':(time.perf_counter()-start)*1000,'launches':len(launches)-count})
        setattr(server,name,wrap)
    paths=['orders_page.css',editor.CODE_FILES[0]];original={p:(root/p).read_bytes() for p in paths}
    try:
        subprocess.Popen=popen
        with sync_playwright() as pw:
            browser=pw.chromium.launch(channel='msedge',headless=False)
            context=browser.new_context(viewport={'width':1600,'height':1000})
            context.add_cookies([{'name':cookie,'value':secret,'domain':'127.0.0.1','path':'/api/device','httpOnly':True,'sameSite':'Strict'}])
            context.route('**/*',lambda r:r.continue_() if r.request.url.startswith((origin,server.origin,'data:','blob:')) else r.abort())
            context.add_init_script("""window.perf={input:[],writes:[],long:[]};const set=Storage.prototype.setItem;Storage.prototype.setItem=function(k,v){const t=performance.now();try{return set.call(this,k,v);}finally{window.perf.writes.push({ms:performance.now()-t,bytes:v.length});}};document.addEventListener('input',e=>{if(e.target.id==='ed-source'){const t=performance.now();requestAnimationFrame(()=>window.perf.input.push(performance.now()-t));}},true);new PerformanceObserver(l=>window.perf.long.push(...l.getEntries().map(e=>e.duration))).observe({type:'longtask',buffered:true});""")
            live=context.new_page();live.goto(origin)
            def ready(dev):
                expect(dev.locator('#ws-image')).to_be_visible(timeout=120000)
                expect(dev.locator('#ws-loading')).to_be_hidden(timeout=120000)
                expect(dev.locator('#ws-page')).to_be_enabled(timeout=30000)
                dev.wait_for_timeout(300)
            def open_dev():
                with context.expect_page() as tab:live.get_by_role('link',name='Dev Mode').click()
                dev=tab.value;dev.on('pageerror',lambda e:errors.append(str(e)));dev.wait_for_timeout(700)
                bridge=next((p for p in reversed(context.pages) if '/pair' in p.url),None)
                if not bridge:
                    with context.expect_page() as pair:dev.locator('#connect').click()
                    bridge=pair.value
                expect(bridge.locator('#open')).to_be_visible(timeout=30000)
                was_running=bool(server.preview_runtime and server.preview_runtime.name)
                start=time.perf_counter();bridge.locator('#open').click();dev.bring_to_front()
                expect(dev.locator('#ed-source')).to_be_attached(timeout=120000)
                record('entry_editor_attached',start);ready(dev);record('warm_reopen' if was_running else 'cold_entry',start)
                return dev
            dev=open_dev();container=server.preview_runtime.container_id
            if args.editor_only:
                dev.get_by_role('button',name='Files',exact=True).click()
                for _ in range(5):
                    start=time.perf_counter();dev.locator('#ws-list').get_by_role('button',name=editor.CODE_FILES[0],exact=False).click();expect(dev.locator('#ed-file')).to_have_value(editor.CODE_FILES[0]);expect(dev.locator('#ed-source')).to_be_enabled();record('html_source_switch',start)
                    dev.locator('#ws-list').get_by_role('button',name='orders_page.css',exact=False).click();expect(dev.locator('#ed-file')).to_have_value('orders_page.css');expect(dev.locator('#ed-source')).to_be_enabled()
                result['sources_unchanged']=all((root/p).read_bytes()==v for p,v in original.items());result['browser_errors']=errors;browser.close();return
            if args.warm_only:
                for _ in range(5):
                    dev.close();dev=open_dev()
                result['sources_unchanged']=True
                browser.close();return
            for i in range(5):
                start=time.perf_counter();dev.locator('#ws-page').select_option('orders' if i%2==0 else 'dashboard');ready(dev);assert server.preview_runtime.last_frame['page_key']==('orders' if i%2==0 else 'dashboard');record('page_navigation',start)
            dev.get_by_role('button',name='Files',exact=True).click()
            start=time.perf_counter();dev.locator('#ws-list').get_by_role('button',name=editor.CODE_FILES[0],exact=False).click()
            expect(dev.locator('#ed-source')).to_be_visible();expect(dev.locator('#ed-source')).to_be_enabled();record('large_html_open',start)
            field=dev.locator('#ed-source');value=field.input_value();result['html_chars']=len(value)
            field.focus();field.press('Control+End')
            start=time.perf_counter();field.press_sequentially('<!-- p2 typing benchmark -->',delay=15,timeout=20000);record('typing_sequence',start)
            dev.wait_for_timeout(1000);result['typing']=dev.evaluate('window.perf');result['heap_bytes']=dev.evaluate('performance.memory?.usedJSHeapSize||null')
            # Every unsaved keystroke remains undoable, then test close/recovery.
            dev.once('dialog',lambda dialog:dialog.accept());dev.close();dev=open_dev()
            expect(dev.locator('#ed-source')).to_have_value(value+'<!-- p2 typing benchmark -->',timeout=30000)
            result['recovery_passed']=True
            for _ in range(len('<!-- p2 typing benchmark -->')):dev.locator('#ws-undo').click()
            expect(dev.locator('#ed-source')).to_have_value(value)
            for _ in range(4):
                dev.close();dev=open_dev()
            for i in range(5):
                start=time.perf_counter();dev.get_by_role('button',name=['Mobile','Tablet','Desktop'][i%3],exact=True).click();ready(dev);record('device_switch',start)
            dev.get_by_role('button',name='Files',exact=True).click();dev.locator('#ws-list').get_by_role('button',name='orders_page.css',exact=False).click()
            field=dev.locator('#ed-source');expect(field).to_be_enabled();css=field.input_value()
            for i in range(5):
                field.fill(css+'\n/* isolated p2 benchmark '+str(i)+' */\n');start=time.perf_counter();dev.locator('#ws-save').click();expect(dev.locator('#ed-status')).to_contain_text('Saved to the actual draft',timeout=30000);ready(dev);record('save_to_preview',start)
                dev.locator('#ws-undo').click();expect(dev.locator('#ed-status')).to_contain_text('Saved to the actual draft',timeout=30000);ready(dev);assert (root/'orders_page.css').read_bytes()==original['orders_page.css']
            for i in range(5):
                start=time.perf_counter();dev.locator('#ws-image').hover();dev.mouse.wheel(0,400 if i%2==0 else -400);dev.wait_for_timeout(110);ready(dev);record('scroll',start)
            # Full-source replacement reproducer (bounded driver deadline).
            dev.locator('#ws-list').get_by_role('button',name=editor.CODE_FILES[0],exact=False).click();field=dev.locator('#ed-source');expect(field).to_be_enabled()
            start=time.perf_counter()
            try:field.fill(value+'\n<!-- bulk fixture -->',timeout=8000);record('large_html_fill',start);result['bulk_fill_passed']=True
            except Exception as exc:result['bulk_fill_passed']=False;result['bulk_error']=str(exc)[-2000:]
            print('bulk complete',flush=True)
            result['final_browser_metrics']=dev.evaluate('({heap:performance.memory?.usedJSHeapSize,perf:window.perf})')
            result['same_container']=server.preview_runtime.container_id==container
            result['isolation']=server.preview_runtime.evidence
            result['idle_docker']=subprocess.check_output(['docker','--context',server.preview_runtime.docker_context,'stats','--no-stream','--format','{{json .}}',container],text=True,creationflags=subprocess.CREATE_NO_WINDOW).strip()
            result['idle_host_pid']=__import__('os').getpid()
            # Own Edge CDP process metrics; no personal Edge process/profile access.
            cdp=browser.new_browser_cdp_session();a=cdp.send('SystemInfo.getProcessInfo')['processInfo'];dev.wait_for_timeout(10000);b=cdp.send('SystemInfo.getProcessInfo')['processInfo'];prior={p['id']:p['cpuTime'] for p in a};result['edge_idle_cpu_one_core_percent']=sum(max(0,p['cpuTime']-prior.get(p['id'],p['cpuTime'])) for p in b)*10
            result['browser_errors']=errors;dev.screenshot(path=str(root/'docs'/('v9-p2-'+args.phase+'.png')))
            dev.once('dialog',lambda d:d.accept());browser.close()
        for _ in range(3):
            server.preview_runtime.stop();start=time.perf_counter();server.action({'action':'start-preview'});record('cold_runtime',start)
        result['sources_unchanged']=all((root/p).read_bytes()==v for p,v in original.items())
    finally:
        subprocess.Popen=real_popen
        if server.preview_runtime and server.preview_runtime.name:server.preview_runtime.stop()
        server.stopping=True;surface.shutdown()
        result['samples_ms']=times;result['summary_ms']={name:{'n':len(v),'median':statistics.median(v),'p95_nearest_rank':sorted(v)[math.ceil(.95*len(v))-1]} for name,v in times.items()};result['calls']=calls;result['launches']=dict(Counter(p['program'] for p in launches));result['all_launches_silent']=all(p['silent'] for p in launches)
        (root/'docs'/('v9-p2-'+args.phase+'.json')).write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps({k:v for k,v in result.items() if k in ('summary_ms','bulk_fill_passed','sources_unchanged','browser_errors')},indent=2),flush=True)
if __name__=='__main__':main()
