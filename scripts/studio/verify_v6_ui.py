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
            t=time.monotonic();page.goto(url);page.locator('#origin').fill(server.origin)
            with page.expect_popup() as popup:page.locator('#connect').click()
            local=popup.value;local.locator('#session').fill(server.origin+'/#'+server.token)
            local.locator('#trust').uncheck();local.locator('#approve').click()
            expect(page.locator('#connection')).to_contain_text('connected')
            page.locator('#list').get_by_role('button',name='Edit',exact=True).click()
            local.locator('#open').click()
            expect(page.locator('#ws-title')).to_have_text('Editor fixture')
            result['connect_and_embedded_open_seconds']=round(time.monotonic()-t,3)
            page.get_by_role('button',name='Files',exact=True).click()
            page.locator('#ws-list').get_by_role('button',name='app.py',exact=False).click()
            expect(page.locator('#ed-text')).to_have_value('Welcome back')
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
            page.locator('#disconnect').click();expect(page.locator('#connection')).to_contain_text('offline')
            expect(page.locator('#ed-source')).to_have_value('<h1>unsaved survives reconnect</h1>')
            with page.expect_popup() as popup:page.locator('#connect').click()
            local=popup.value;local.locator('#session').fill(server.origin+'/#'+server.token);local.locator('#trust').uncheck();local.locator('#approve').click()
            expect(page.locator('#connection')).to_contain_text('connected')
            # Existing workspace is retained while permission is renewed explicitly.
            page.locator("#resume-editor").click();local.locator('#open').click()
            expect(page.locator('#ed-source')).to_have_value('<h1>unsaved survives reconnect</h1>')
            page.locator('#ws-discard').click();page.get_by_role('button',name='Discard changes',exact=True).click()
            expect(page.locator('#ed-source')).to_have_value('<h1>Example</h1>')
            page.locator('#ws-tests').click();expect(page.locator('#ws-info')).to_contain_text('Not recorded')
            page.locator('#ws-tests').click()
            for width in [1440,1100,390]:
                page.set_viewport_size({'width':width,'height':900})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
                page.screenshot(path=str(report.with_name(report.stem+'-'+str(width)+'.png')))
            result.update({'visual_save_undo_restore':True,'source_save_undo':True,'discard_confirmations':True,'same_draft_unsaved_reconnect':True,'tests_history':True,'responsive_widths':[1440,1100,390],'browser':browser.version,'errors':errors})
            assert not errors,errors
            browser.close()
    finally:
        server.stopping=True;thread.join(5);panel.shutdown();panel.server_close();f.doCleanups()
    studio.atomic(report,result);print(json.dumps(result,indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True);main(p.parse_args().report)
