import sys,json,time,threading,hashlib,subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[2];home=root.parent;task='20261013-v8-silent-performance';owner='codex/v8-performance-01a13216'
sys.path.insert(0,str(root/'scripts/studio'))
from playwright.sync_api import sync_playwright,expect
import studio,draft_ui,preview_boundary
server=draft_ui.DraftServer(home,task,owner,idle_seconds=900)
thread=threading.Thread(target=server.run,daemon=True);thread.start()
before=(root/'app.py').read_bytes();errors=[];report={'scope':'Installed Edge, isolated browser profile, real Docker synthetic OS in new CORE task'}
launches=[];real_popen=subprocess.Popen
def popen(*args,**kwargs):
    command=args[0] if args else kwargs.get('args')
    if isinstance(command,list) and Path(command[0]).name.lower() in ('docker','docker.exe','git','git.exe'):
        launches.append({'program':command[0],'no_console':bool(kwargs.get('creationflags',0)&subprocess.CREATE_NO_WINDOW)})
    return real_popen(*args,**kwargs)
try:
    subprocess.Popen=popen
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(channel='msedge',headless=False)
        context=browser.new_context(viewport={'width':1440,'height':900})
        context.route('**/*',lambda r:r.continue_() if r.request.url.startswith(('http://127.0.0.1:','data:','blob:')) else r.abort())
        page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
        url=server.origin+'/workspace#token='+server.token+'&intent=edit'
        page.goto(url);expect(page.locator('#ws-title')).to_contain_text('performance')
        expect(page.locator('.ws-left')).to_be_visible();expect(page.locator('.ws-right')).to_be_visible()
        page.locator('#ws-start').click();expect(page.locator('#ws-image')).to_be_visible(timeout=90000)
        expect(page.locator('#ws-loading')).to_be_hidden(timeout=90000)
        container=server.preview_runtime.container_id
        page.locator('#ws-start').click();expect(page.locator('#ws-loading')).to_be_hidden(timeout=20000)
        assert server.preview_runtime.container_id==container
        previous=page.locator('#ws-image').get_attribute('src')
        page.locator('#ws-page').select_option('dashboard')
        expect(page.locator('#ws-loading')).to_be_visible();expect(page.locator('#ws-image')).to_be_visible()
        assert page.locator('#ws-image').get_attribute('src')==previous
        expect(page.locator('#ws-loading')).to_be_hidden(timeout=30000)
        page.locator('#ws-page').select_option('developer_studio');expect(page.locator('#ws-loading')).to_be_hidden(timeout=30000)
        for mode in ('Tablet','Mobile','Desktop'):
            page.get_by_role('button',name=mode,exact=True).click();expect(page.locator('#ws-loading')).to_be_hidden(timeout=20000)
        page.locator('#ws-page').select_option('__signin__');expect(page.locator('#ws-loading')).to_be_hidden(timeout=30000)
        page.get_by_role('button',name='Files',exact=True).click()
        page.locator('#ws-list').get_by_role('button',name='app.py',exact=False).click()
        page.locator('#ed-component').select_option('title')
        original_text=page.locator('#ed-text').input_value()
        page.locator('#ed-text').fill(original_text+' silent performance acceptance')
        page.locator('#ws-save').click();expect(page.locator('#ed-status')).to_contain_text('Saved to the actual draft',timeout=30000)
        expect(page.locator('#ws-loading')).to_be_hidden(timeout=30000)
        assert 'silent performance acceptance' in server.preview_runtime.last_frame['text'],'Source rerun did not update the rendered page'
        assert server.preview_runtime.container_id==container
        page.locator('#ed-text').fill(original_text);page.locator('#ws-save').click()
        expect(page.locator('#ed-status')).to_contain_text('Saved to the actual draft',timeout=30000)
        expect(page.locator('#ws-loading')).to_be_hidden(timeout=30000)
        assert (root/'app.py').read_bytes()==before
        relay_pid=server.preview_runtime.relay.process.pid
        server.preview_runtime.relay.process.kill();server.preview_runtime.relay.process.wait(5)
        page.locator('#ws-refresh').click();expect(page.locator('#ws-loading')).to_be_hidden(timeout=25000)
        expect(page.locator('#ws-image')).to_be_visible()
        page.locator('#ws-refresh').click();expect(page.locator('#ws-loading')).to_be_hidden(timeout=25000)
        assert server.preview_runtime.relay.process.pid!=relay_pid
        assert server.preview_runtime.container_id==container
        page.screenshot(path=str(root/'docs/v8-performance-edge.png'))
        page.locator('#ws-stop').click();expect(page.locator('#ws-status')).to_contain_text('Preview stopped',timeout=20000)
        assert server.preview_runtime.name is None
        page.close();page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(url);expect(page.locator('#ws-title')).to_contain_text('performance')
        expect(page.locator('.ws-left')).to_be_visible();expect(page.locator('.ws-right')).to_be_visible()
        browser.close()
    assert launches and all(x['no_console'] for x in launches),launches
    assert not errors,errors
    report.update(repeated_start_same_container=True,page_switch_and_resize=True,last_frame_visible_during_loading=True,save_reruns_existing_session_and_frame=True,relay_failure_preserves_frame_and_recovers=True,stop_and_editor_reopen=True,three_panel_interface=True,all_background_windows_launches_no_console=True,background_launch_count=len(launches),source_restored=True,browser_errors=errors)
    print(json.dumps(report))
finally:
    subprocess.Popen=real_popen
    server.stopping=True;thread.join(15)
    if (root/'app.py').read_bytes()!=before:
        import editor
        draft=server.state()['draft'];opened=editor.open_file(home,draft['id'],owner,'app.py')
        values=editor.visual_values(before.decode('utf-8-sig'))
        editor.write(home,draft['id'],owner,'app.py',opened['hash'],opened['revision'],component='title',changes={'text':values['title']['text']})
    (root/'docs/v8-performance-edge.json').write_text(json.dumps(report,indent=2))
