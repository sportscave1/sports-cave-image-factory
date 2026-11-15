"""Real Windows Edge / Docker checks, own isolated browser profile and current-draft copy."""
import json, time, threading, hashlib, statistics, math
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
import studio, draft_ui, source_editor, preview_runtime

source=Path(__file__).resolve().parents[2]
receipt=json.loads((source/'docs/codefirst-qa-copy.json').read_text());home=Path(receipt['home']);root=Path(receipt['root']);owner=receipt['owner'];task=receipt['task'];draft_id=receipt['draft_id']
paths=['components/sign_in/presentation.html','orders_page.css','components/session_recovery.js','components/sports_cave_top_bar/index.html','signin_presentation.py']
baseline={path:(root/path).read_bytes() for path in paths}
server=draft_ui.DraftServer(home,task,owner,persistent=True)
threading.Thread(target=server.run,daemon=True).start()
report={'scope':'Disposable Edge profile and sanitised current-draft acceptance copy; no 18762 operations','image':preview_runtime.IMAGE_TAG,'checks':{},'timings':{},'browser_errors':[]}
original_replace=source_editor.replace
def record(name,value=True):report['checks'][name]=value;print(name,value,flush=True)
try:
 with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=False)
    context=browser.new_context(viewport={'width':1680,'height':1050},permissions=['clipboard-read','clipboard-write'])
    page=context.new_page();page.on('pageerror',lambda e:report['browser_errors'].append(str(e)))
    start=time.perf_counter();page.goto(server.origin+'/workspace#token='+server.token)
    expect(page.locator('#ed-source')).to_be_visible(timeout=120000)
    report['timings']['editor_available_seconds']=time.perf_counter()-start
    expect(page.locator('#ws-image')).to_be_visible(timeout=120000);expect(page.locator('#ws-loading')).to_be_hidden(timeout=120000)
    report['timings']['cold_ready_seconds']=time.perf_counter()-start
    container=server.preview_runtime.container_id
    record('real_preview_synthetic',server.preview_runtime.last_frame['synthetic'])
    def open_file(path):
        page.locator('#ws-list').get_by_role('button',name=path.split('/')[-1],exact=False).last.click()
        expect(page.locator('#ed-path')).to_contain_text(path,timeout=30000)
    def set_buffer(value):
        page.locator('#ed-source').evaluate('(n,value)=>{n.value=value;n.dispatchEvent(new InputEvent("input",{bubbles:true,inputType:"insertFromPaste"}));}',value)
    def settled():expect(page.locator('#ws-loading')).to_be_hidden(timeout=120000)
    html_path=paths[0];open_file(html_path);html=page.locator('#ed-source').input_value()
    page.bring_to_front();page.locator('#ed-copy').click();expect(page.locator('#ed-status')).to_contain_text('Complete source copied',timeout=15000);assert page.evaluate('navigator.clipboard.readText()').replace('\r\n','\n')==html;record('copy_complete_source')
    page.evaluate('() => {window.qaClipboardWrite=navigator.clipboard.writeText.bind(navigator.clipboard);navigator.clipboard.writeText=async()=>{throw new DOMException("QA permission denied","NotAllowedError");};}')
    page.locator('#ed-copy').click();expect(page.locator('#ed-status')).to_contain_text('Press Ctrl+C')
    assert page.locator('#ed-source').evaluate('n=>n.selectionStart===0&&n.selectionEnd===n.value.length')
    page.evaluate('() => {navigator.clipboard.writeText=window.qaClipboardWrite;delete window.qaClipboardWrite;}');record('clipboard_gesture_fallback')
    open_file('app.py');assert page.locator('#ed-source').evaluate('n=>n.readOnly')
    assert page.locator('#ed-source').input_value()==(root/'app.py').read_bytes().decode('utf-8-sig').replace('\r\n','\n');record('complete_actual_python_read_only')
    open_file(html_path)
    # Three independent unsaved buffers. No file/page-switch confirmation.
    dialogs=[]
    def no_navigation_dialog(d):dialogs.append(d.message);d.dismiss()
    page.on('dialog',no_navigation_dialog)
    set_buffer(html.replace('{{title}}','Code-first acceptance heading'))
    open_file(paths[1]);css=page.locator('#ed-source').input_value();set_buffer(css+'\n/* multi-file acceptance */\n')
    open_file(paths[2]);js=page.locator('#ed-source').input_value();set_buffer(js+'\n// multi-file acceptance\n')
    expect(page.locator('#ws-unsaved')).to_have_text('Unsaved files: 3')
    for route in ('orders','dashboard','__signin__'):
        start=time.perf_counter();page.locator('#ws-page').select_option(route);settled();report['timings'].setdefault('navigation_seconds',[]).append(time.perf_counter()-start)
    open_file(html_path);assert page.locator('#ed-source').input_value()==html.replace('{{title}}','Code-first acceptance heading')
    open_file(paths[1]);assert page.locator('#ed-source').input_value()==css+'\n/* multi-file acceptance */\n'
    assert not dialogs,dialogs;record('multi_file_page_switch_without_discard_prompts')
    # Undo/Redo changes only the active buffer.
    page.locator('#ws-undo').click();expect(page.locator('#ed-source')).to_have_value(css)
    page.locator('#ws-redo').click();expect(page.locator('#ed-source')).to_have_value(css+'\n/* multi-file acceptance */\n');record('per_file_undo_redo')
    # Actual browser close / reopen in the same disposable profile.
    page.remove_listener('dialog',no_navigation_dialog)
    page.once('dialog',lambda d:d.accept())
    # Use the browser's normal beforeunload gesture; all buffers flush on close.
    with page.expect_event('close',timeout=15000):page.close(run_before_unload=True)
    page=context.new_page();page.on('pageerror',lambda e:report['browser_errors'].append(str(e)))
    start=time.perf_counter();page.goto(server.origin+'/workspace#token='+server.token)
    expect(page.locator('#ws-unsaved')).to_have_text('Unsaved files: 3',timeout=120000);settled();report['timings']['reopen_recovery_seconds']=time.perf_counter()-start
    open_file(paths[2]);assert page.locator('#ed-source').input_value()==js+'\n// multi-file acceptance\n';record('all_dirty_buffers_recovered_after_reopen')
    # One button -> one coherent revision containing every file.
    before=studio.read(home/'.studio/registry.json')['drafts'][0]['revision']
    start=time.perf_counter();page.locator('#ws-save').click();expect(page.locator('#ed-status')).to_contain_text('Saved all files in draft revision',timeout=120000);settled()
    report['timings']['save_all_to_preview_seconds']=time.perf_counter()-start
    draft=studio.read(home/'.studio/registry.json')['drafts'][0];assert draft['revision']==before+1
    assert {h['path'] for h in draft['editor_history'][-3:]}==set(paths[:3]);assert len({h['batch_id'] for h in draft['editor_history'][-3:]})==1
    assert b'Code-first acceptance heading' in (root/html_path).read_bytes();assert 'Code-first acceptance heading' in server.preview_runtime.last_frame['text'];record('one_revision_all_files_and_actual_preview')
    expect(page.locator('#ws-unsaved')).to_have_text('All files saved');assert server.preview_runtime.container_id==container;record('container_and_session_reused')
    page.locator('#ws-history').click();expect(page.locator('#ed-history-panel')).to_be_visible();record('file_specific_history')
    # Real complete large-file paste; bounded DOM and repeated source typing.
    open_file(paths[3]);large=page.locator('#ed-source').input_value();assert len(large)>100000
    start=time.perf_counter();set_buffer(large+'\n<!-- large complete replacement -->\n');report['timings']['large_paste_seconds']=time.perf_counter()-start
    metrics=page.locator('#ed-source').evaluate('n=>{const values=[];for(let i=0;i<100;i++){const start=performance.now();n.value+=" ";n.dispatchEvent(new InputEvent("input",{bubbles:true}));values.push(performance.now()-start);}return values;}')
    report['timings']['large_typing_median_ms']=statistics.median(metrics);report['timings']['large_typing_p95_ms']=sorted(metrics)[math.ceil(.95*len(metrics))-1]
    assert page.locator('#ed-highlight').inner_text().__len__()<20000;record('large_complete_file_bounded_rendering')
    # Controlled Python data edit; all executable alterations must fail before writes.
    open_file(paths[4]);settings=page.locator('#ed-source').input_value();set_buffer(settings.replace('Welcome back','Controlled presentation setting'))
    revision=studio.read(home/'.studio/registry.json')['drafts'][0]['revision']
    opened=source_editor.open_file(home,draft_id,owner,paths[4])
    try:source_editor.write_all(home,draft_id,owner,revision,[{'path':paths[4],'expected_hash':opened['hash'],'source':'import os\nos.remove("file")'}])
    except ValueError:record('executable_python_rejected')
    else:raise AssertionError('Unsafe Python accepted')
    # Conflict from another writer: actual Save All must retain both pending buffers.
    original=(root/paths[4]).read_bytes();(root/paths[4]).write_bytes(original+b'\n# external QA edit\n')
    page.locator('#ws-save').click();expect(page.locator('#ed-status')).to_contain_text('Concurrent source modification',timeout=30000)
    expect(page.locator('#ws-unsaved')).to_have_text('Unsaved files: 2');assert studio.read(home/'.studio/registry.json')['drafts'][0]['revision']==revision
    (root/paths[4]).write_bytes(original);record('conflict_retains_all_pending_buffers_and_source')
    for mode in ('tablet','mobile','desktop'):
        page.locator('[data-size="'+mode+'"]').click();settled()
    record('responsive_preview_controls')
    assert server.preview_runtime.container_id==container
    page.locator('.ws-more summary').click();page.locator('#ws-discard').click()
    expect(page.locator('dialog')).to_be_visible();page.get_by_role('button',name='Keep editing',exact=True).click()
    expect(page.locator('#ws-unsaved')).to_have_text('Unsaved files: 2')
    page.locator('#ws-discard').click();page.get_by_role('button',name='Discard changes',exact=True).click()
    expect(page.locator('#ws-unsaved')).to_have_text('All files saved');record('discard_only_on_explicit_confirmed_action')
    page.screenshot(path=str(source/'docs/codefirst-edge.png'),full_page=True)
    restore=[]
    for path,data in baseline.items():
        opened=source_editor.open_file(home,draft_id,owner,path)
        if (root/path).read_bytes()!=data:restore.append({'path':path,'expected_hash':opened['hash'],'source':data.decode('utf-8')})
    if restore:
        source_editor.write_all(home,draft_id,owner,studio.read(home/'.studio/registry.json')['drafts'][0]['revision'],restore)
        server.preview_runtime.refresh_source([row['path'] for row in restore])
    page.close();page=context.new_page();page.on('pageerror',lambda e:report['browser_errors'].append(str(e)));page.goto(server.origin+'/workspace#token='+server.token);expect(page.locator('#ed-source')).to_be_visible(timeout=120000);settled()
    expect(page.locator('#ws-unsaved')).to_have_text('All files saved')
    open_file('components/sign_in/presentation.html');expect(page.locator('#ed-source')).to_have_value(baseline['components/sign_in/presentation.html'].decode('utf-8').replace('\r\n','\n'));assert 'Code-first acceptance heading' not in server.preview_runtime.last_frame['text'];page.locator('.ws-more summary').evaluate('n=>n.parentElement.open=false');page.screenshot(path=str(source/'docs/codefirst-ready.png'),full_page=True)
    record('clean_reopen_after_exact_source_restore')
    assert not report['browser_errors'],report['browser_errors']
    context.close();browser.close()
finally:
    # Restore acceptance source with the same journalled Save All and retain its history.
    rows=[]
    for path,data in baseline.items():
        opened=source_editor.open_file(home,draft_id,owner,path)
        if (root/path).read_bytes()!=data:rows.append({'path':path,'expected_hash':opened['hash'],'source':data.decode('utf-8')})
    if rows:source_editor.write_all(home,draft_id,owner,studio.read(home/'.studio/registry.json')['drafts'][0]['revision'],rows)
    assert all((root/path).read_bytes()==data for path,data in baseline.items())
    if server.preview_runtime:server.preview_runtime.stop()
    server.stopping=True
    report['acceptance_source_restored']=True
    (source/'docs/codefirst-acceptance.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2),flush=True)
