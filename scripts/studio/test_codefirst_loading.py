"""Focused hosted-bundle regression in disposable Edge and isolated Docker QA."""
import base64
import json
import re
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright, expect
import draft_ui
import source_editor
import studio

ROOT = Path(__file__).resolve().parents[2]
import sys
sys.path.insert(0, str(ROOT))
from developer_studio_page import panel_html

SESSION = ROOT.parents[1]
receipt = json.loads((SESSION/'codefirst/sports-cave-core-code-first-v9-codefirst/docs/codefirst-qa-copy.json').read_text())
home, root = Path(receipt['home']), Path(receipt['root'])
server = draft_ui.DraftServer(home, receipt['task'], receipt['owner'], persistent=True)
server_thread=threading.Thread(target=server.run, daemon=True)
server_thread.start()
paths = ['components/sign_in/presentation.html', 'orders_page.css']
before = {p: (root/p).read_bytes() for p in paths}
report = {'checks': {}, 'browser_errors': [], 'scope': 'Disposable Edge profile / sanitised QA copy only; no 18762 changes'}
html = panel_html()
bundle = json.loads(html.split('window.STUDIO_V6_BUNDLE=', 1)[1].split(';"use strict";', 1)[0])
assert bundle['code-editor.js'] == (ROOT/'scripts/studio/ui/code-editor.js').read_text(encoding='utf-8-sig')
loader = re.search(r' async function moduleFrom\(.*?\n', (ROOT/'components/developer_studio/panel.js').read_text()).group(0)
fixture = '<html><style>'+bundle['editor.css']+bundle['workspace.css']+'</style><div id="workspace"></div><script>window.bundle='+json.dumps(bundle).replace('</','<\\/')+';'+loader+'window.moduleFrom=moduleFrom;</script></html>'

try:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='msedge', headless=False)
        context = browser.new_context(viewport={'width':1680,'height':1050})
        context.route(server.origin+'/fixture', lambda route: route.fulfill(body=fixture, content_type='text/html'))
        scratch = context.new_page()
        scratch.goto(server.origin+'/fixture')
        jpg = base64.b64encode(scratch.screenshot(type='jpeg')).decode()
        scratch.close()
        model = server.workspace_model()
        for case in ['missing', 'missing-mount', 'mount-failure', 'phase2']:
            page = context.new_page()
            page.on('pageerror', lambda e: report['browser_errors'].append(str(e)))
            page.goto(server.origin+'/fixture')
            page.evaluate('''async ({model,jpg,caseName})=>{
              window.calls=[];window.partialLeave=0;const key='loading-test:'+caseName;
              localStorage.setItem('studio-code-buffers:'+key, '{"dirty":["retain.html"]}');
              localStorage.setItem('studio-code-buffers:'+key+':retain.html','unsaved sentinel');
              if(caseName==='phase2')delete model.capabilities;
              const frame={image:jpg,width:1680,height:1050,page_key:'dashboard'};
              const request=async(_path,data)=>{calls.push(data.action);if(data.action==='workspace-model')return model;if(data.action==='editor-reference')return {files:[],references:[]};return frame;};
              const ws=await moduleFrom(bundle['workspace.js'],'workspace.js');
              const loadEditor=()=>caseName==='missing'?moduleFrom(undefined,'code-editor.js'):caseName==='missing-mount'?moduleFrom('export const version=1;','code-editor.js'):Promise.resolve({mount(){throw Error('QA mount failed');},selectFile(){},selectComponent(){},canLeave(){partialLeave++;return true;},command(){},dispose(){}});
              window.view=await ws.mount(document.getElementById('workspace'),request,{storageKey:()=>key,loadEditor});
            }''', {'model':model,'jpg':jpg,'caseName':case})
            expect(page.locator('#ws-editor-error')).to_be_visible()
            box=page.locator('#ws-editor-error').bounding_box()
            assert box['y']+box['height']<=1050,box
            expect(page.locator('#ws-image')).to_be_visible(timeout=10000)
            expect(page.locator('#ws-loading')).to_be_hidden(timeout=10000)
            assert page.evaluate("calls.filter(x=>x==='start-preview').length") == 1
            assert page.evaluate("calls.filter(x=>x==='source-open'||x==='editor-save-all').length") == 0
            assert page.evaluate("name=>localStorage.getItem('studio-code-buffers:loading-test:'+name+':retain.html')", case) == 'unsaved sentinel'
            assert page.locator('#ws-save').is_disabled()
            assert page.evaluate('view.canLeave()')
            if case=='mount-failure': assert page.evaluate('partialLeave') == 1
            report['checks'][case+'_visible_error_independent_preview_buffers_preserved'] = True
            page.evaluate('view.dispose()')
            page.close()
        if '--failures-only' in sys.argv:
            browser.close()
            print(json.dumps(report,indent=2))
            raise SystemExit(0)
        page = context.new_page()
        page.on('pageerror', lambda e: report['browser_errors'].append(str(e)))
        page.goto(server.origin+'/fixture')
        page.evaluate('''async token=>{
          const ws=await moduleFrom(bundle['workspace.js'],'workspace.js');
          window.view=await ws.mount(document.getElementById('workspace'),async(path,data)=>{
            const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Studio-Token':token},body:JSON.stringify(data)}),v=await r.json();if(!r.ok)throw Error(v.error);return v;
          },{storageKey:()=>location.origin+':hosted-loading-qa',loadEditor:()=>moduleFrom(bundle['code-editor.js'],'code-editor.js')});
        }''', server.token)
        expect(page.locator('#ed-source')).to_be_visible(timeout=30000)
        expect(page.locator('#ws-image')).to_be_visible(timeout=120000)
        expect(page.locator('#ws-loading')).to_be_hidden(timeout=120000)
        assert not page.locator('#ws-editor-error').is_visible()
        container = server.preview_runtime.container_id
        def select(path):
            page.locator('#ws-list').get_by_role('button', name=path.split('/')[-1], exact=False).last.click()
            expect(page.locator('#ed-path')).to_contain_text(path)
        for path in paths:
            select(path)
            expected = before[path].decode('utf-8-sig').replace('\r\n','\n')
            assert page.locator('#ed-source').input_value() == expected
            addition = '\n<!-- hosted loading QA -->\n' if path.endswith('.html') else '\n/* hosted loading QA */\n'
            page.locator('#ed-source').fill(expected+addition)
        page.locator('#ws-undo').click()
        expect(page.locator('#ed-source')).to_have_value(before[paths[-1]].decode('utf-8-sig').replace('\r\n','\n'))
        page.locator('#ws-redo').click()
        expect(page.locator('#ws-unsaved')).to_have_text('Unsaved files: 2')
        revision = next(d['revision'] for d in studio.read(home/'.studio/registry.json')['drafts'] if d['id']==receipt['draft_id'])
        page.locator('#ws-save').click()
        expect(page.locator('#ed-status')).to_contain_text('Saved all files',timeout=120000)
        assert next(d['revision'] for d in studio.read(home/'.studio/registry.json')['drafts'] if d['id']==receipt['draft_id']) == revision+1
        assert server.preview_runtime.container_id == container
        assert server.preview_runtime.last_frame['synthetic']
        report['checks']['actual_hosted_blob_module_complete_source_undo_save_all_same_isolated_container'] = True
        assert not report['browser_errors'], report['browser_errors']
        page.evaluate('view.dispose()')
        browser.close()
finally:
    server.stopping=True
    server_thread.join(120)
    assert not server_thread.is_alive(), "QA server must finish before source restoration"
    rows=[]
    for path, data in before.items():
        if (root/path).read_bytes()!=data:
            opened=source_editor.open_file(home,receipt['draft_id'],receipt['owner'],path)
            rows.append({'path':path,'expected_hash':opened['hash'],'source':data.decode('utf-8')})
    if rows:source_editor.write_all(home,receipt['draft_id'],receipt['owner'],next(d['revision'] for d in studio.read(home/'.studio/registry.json')['drafts'] if d['id']==receipt['draft_id']),rows)
    assert all((root/path).read_bytes()==data for path,data in before.items())
    if server.preview_runtime:server.preview_runtime.stop()
    server.server_close()
    report['checks']['qa_source_restored']=True
    (ROOT/('docs/codefirst-loading-failures.json' if '--failures-only' in sys.argv else 'docs/codefirst-loading-tests.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
