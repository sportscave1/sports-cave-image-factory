"""Disposable headless UI acceptance. No personal browser profiles, hosted OS or real trust."""
import argparse,base64,json,threading,time
from pathlib import Path
from http.server import HTTPServer
from playwright.sync_api import sync_playwright,expect
import test_editor,test_drafts,drafts,studio,draft_ui
from verify_phase4a_browser import Panel

def main(report):
    f=test_editor.EditorTests();f.setUp()
    (f.root/'os_accounts.py').write_text("PAGE_REGISTRY=({'key':'home','route':'Home','label':'Home','group':'OS pages'},)")
    registry=studio.read(f.home/'.studio/registry.json')
    locked_root=f.home/'locked-task';locked_root.mkdir();(locked_root/'app.py').write_text(test_editor.FIXTURE)
    registry['tasks'].append({**f.task,'id':'task-b','owner':'owner-b','branch':'codex/task/b','worktree_path':str(locked_root)})
    studio.atomic(f.home/'.studio/registry.json',registry)
    locked=drafts.new(f.home,'task-b','owner-b','Locked other owner')
    server=draft_ui.DraftServer(f.home,'task-a','owner-a',idle_seconds=300)
    panel=HTTPServer(('127.0.0.1',0),Panel)
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    pt=threading.Thread(target=panel.serve_forever,daemon=True);pt.start()
    url='http://127.0.0.1:'+str(panel.server_port)
    result={'scope':'Disposable local UI and real editor HTTP fixture; NOT hosted HTTPS or production browser acceptance'}
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='msedge',headless=True)
            context=browser.new_context(viewport={'width':1440,'height':950})
            context.route('**/*',lambda route:route.continue_() if route.request.url.startswith(('http://127.0.0.1:','blob:','data:')) else route.abort())
            page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            t=time.monotonic();page.goto(url);expect(page.locator('#ws-selector')).to_be_visible();expect(page.locator('.ws-left')).to_be_visible();expect(page.locator('.ws-right')).to_be_visible();page.locator('#connection-settings summary').click();page.locator('#origin').fill(server.origin)
            with page.expect_popup() as popup:page.locator('#connect').click()
            local=popup.value;local.locator('#session').fill(server.origin+'/#'+server.token)
            local.locator('#trust').uncheck();local.locator('#approve').click()
            expect(page.locator('#connection')).to_contain_text('connected')
            page.get_by_role('button',name='Drafts',exact=True).click()
            expect(page.locator('#ws-list').get_by_role('button',name='Locked other owner',exact=False)).to_be_disabled()
            expect(page.locator('#ws-list')).to_contain_text('assigned owner companion')
            page.locator('#ws-draft-select').select_option(f.draft['id']);page.locator('#ws-open-draft').click()
            expect(page.locator('#ws-selector')).to_be_visible()
            local.locator('#cancel').click();expect(local.locator('#handoff')).to_be_hidden()
            page.locator('#ws-open-draft').click();expect(local.locator('#handoff')).to_be_visible()
            local.locator('#open').click()
            expect(page.locator('#ws-title')).to_have_text('Editor fixture')
            result['connect_and_embedded_open_seconds']=round(time.monotonic()-t,3)
            page.get_by_role('button',name='Files',exact=True).click()
            page.locator('#ws-list').get_by_role('button',name='app.py',exact=False).click()
            expect(page.locator('#ed-text')).to_have_value('Welcome back')
            # A delayed file selection must lock existing fields until its response arrives.
            pending=[]
            def hold_open(route):
                data=route.request.post_data_json or {}
                if data.get('action')=='workspace-request' and data.get('command',{}).get('action')=='editor-open':pending.append(route)
                else:route.continue_()
            context.route('**/api/action',hold_open)
            page.locator('#ws-list').get_by_role('button',name='app.py',exact=False).click()
            try:
                expect(page.locator('#ed-text')).to_be_disabled()
                deadline=time.monotonic()+5
                while not pending and time.monotonic()<deadline:page.wait_for_timeout(20)
                assert pending,'Expected a held file-open response'
            finally:
                context.unroute('**/api/action',hold_open)
                for route in pending:route.continue_()
            expect(page.locator('#ed-text')).to_be_enabled()
            expect(page.locator('#ws-save')).to_be_enabled()
            result['delayed_file_open_locks_fields']=True
            # Permission expiry never loses the unsaved buffer or forces another setup.
            page.locator('#ed-text').fill('unsaved before expiry')
            for grant in server.workspace_grants.values():grant['expires']=time.monotonic()-1
            page.locator('#ws-save').click();expect(page.locator('#ed-status')).to_contain_text('permission expired')
            page.locator('#connection-settings summary').click();page.locator('#resume-editor').click();local.locator('#open').click()
            expect(page.locator('#ed-text')).to_have_value('unsaved before expiry')
            page.locator('#connection-settings summary').click()
            result['cancel_retry_and_expiry_preserve_buffer']=True
            page.locator('#ed-text').fill('V6 visual fixture')
            page.locator('#ws-save').click();expect(page.locator('#ed-status')).to_contain_text('Saved to the actual draft')
            assert 'V6 visual fixture' in (f.root/'app.py').read_text()
            page.locator('#ws-undo').click();expect(page.locator('#ed-text')).to_have_value('Welcome back')
            assert (f.root/'app.py').read_text()==test_editor.FIXTURE
            page.locator('#ed-text').fill('unsaved text')
            page.locator('#ws-discard').click();page.get_by_role('button',name='Keep editing',exact=True).click()
            expect(page.locator('#ed-text')).to_have_value('unsaved text')
            page.locator('#ws-discard').click();page.get_by_role('button',name='Discard changes',exact=True).click()
            expect(page.locator('#ed-text')).to_have_value('Welcome back')
            page.locator('#ws-history').click();expect(page.locator('#ed-history')).to_be_visible()
            history=server.action({'action':'editor-open','path':'app.py'})['history'];original=history[0]['id']
            page.locator('#ed-history').select_option(original);page.locator('#ed-restore').click()
            expect(page.locator('#ed-status')).to_contain_text('Saved to the actual draft')
            assert 'V6 visual fixture' in (f.root/'app.py').read_text()
            page.locator('#ws-undo').click();expect(page.locator('#ed-status')).to_contain_text('Saved to the actual draft')
            assert (f.root/'app.py').read_text()==test_editor.FIXTURE
            page.locator('#ws-list').get_by_role('button',name='components/sports_cave_top_bar/index.html',exact=False).click()
            page.locator('#ed-source').fill('<h1>V6 source fixture</h1>');page.locator('#ws-save').click()
            expect(page.locator('#ed-status')).to_contain_text('Saved to the actual draft')
            assert (f.root/'components/sports_cave_top_bar/index.html').read_text()=='<h1>V6 source fixture</h1>'
            page.locator('#ws-undo').click();expect(page.locator('#ed-source')).to_have_value('<h1>Example</h1>')
            page.locator('#ed-source').fill('<h1>unsaved survives reconnect</h1>')
            page.locator('#connection-settings summary').click();page.locator('#disconnect').click();expect(page.locator('#connection')).to_contain_text('offline')
            expect(page.locator('#ed-source')).to_have_value('<h1>unsaved survives reconnect</h1>')
            with page.expect_popup() as popup:page.locator('#connect').click()
            local=popup.value;local.locator('#session').fill(server.origin+'/#'+server.token);local.locator('#trust').uncheck();local.locator('#approve').click()
            expect(page.locator('#connection')).to_contain_text('connected')
            # Existing workspace is retained while permission is renewed explicitly.
            local.locator('#open').click()
            expect(page.locator('#ed-source')).to_have_value('<h1>unsaved survives reconnect</h1>')
            page.locator('#ws-discard').click();page.get_by_role('button',name='Discard changes',exact=True).click()
            expect(page.locator('#ed-source')).to_have_value('<h1>Example</h1>')
            page.locator('#ws-tests').click();expect(page.locator('#ws-info')).to_contain_text('Not recorded')
            page.locator('#ws-tests').click()
            for width in [1440,1100,390]:
                page.set_viewport_size({'width':width,'height':900})
                assert not page.locator('body').inner_text().count('\u00c2');assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1');assert page.evaluate('document.documentElement.scrollHeight <= innerHeight+1')
                page.screenshot(path=str(report.with_name(report.stem+'-'+str(width)+'.png')))
            # Reload remembers only draft metadata and still waits for local approval.
            page.set_viewport_size({'width':1440,'height':900});page.reload()
            expect(page.locator('#ws-selector')).to_be_visible()
            with page.expect_popup() as popup:page.locator('#connect').click()
            local=popup.value;local.locator('#session').fill(server.origin+'/#'+server.token);local.locator('#trust').uncheck();local.locator('#approve').click()
            expect(local.locator('#open')).to_be_visible()
            expect(page.locator('#ws-selector')).to_be_visible()
            local.locator('#open').click();expect(page.locator('#ws-title')).to_have_text('Editor fixture')
            assert len([p for p in context.pages if '/workspace' in p.url])==0
            # A remembered locked draft must leave the compact selector open.
            page.evaluate('(key)=>localStorage.setItem(key[0],key[1])',['studio-v6-last-draft:'+server.origin,locked['id']])
            page.reload();expect(page.locator('#ws-selector')).to_be_visible()
            with page.expect_popup() as popup:page.locator('#connect').click()
            local=popup.value;local.locator('#session').fill(server.origin+'/#'+server.token);local.locator('#trust').uncheck();local.locator('#approve').click()
            expect(page.locator('#connection')).to_contain_text('connected')
            expect(local.locator('#handoff')).to_be_hidden()
            expect(page.locator('#ws-open-draft')).to_be_disabled()
            result.update(default_workspace=True,locked_draft_explanation=True,last_draft_restore_requires_approval=True,locked_restore_denied=True,no_separate_editor=True)
            result.update({'visual_save_undo_restore':True,'source_save_undo':True,'discard_confirmations':True,'same_draft_unsaved_reconnect':True,'tests_history':True,'responsive_widths':[1440,1100,390],'browser':browser.version,'errors':errors})
            assert not errors,errors
            browser.close()
    finally:
        server.stopping=True;thread.join(5);panel.shutdown();panel.server_close();f.doCleanups()
    studio.atomic(report,result);print(json.dumps(result,indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True);main(p.parse_args().report)
