"""The real picker HTML, served only through synthetic browser routes."""
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def test_save_psd_explicit_takeover_and_selection_reset():
    html=(Path(__file__).resolve().parents[1]/'components/psd_picker/picker.html').read_text(encoding='utf-8')
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        try:
            page=browser.new_page();requests=[];state={'active':False}
            def route(request):
                url=request.request.url
                if '/files-psd-picker?' in url:return request.fulfill(body=html,content_type='text/html')
                if '/api/files-psd-options?' in url:
                    return request.fulfill(json={'product_title':'Recovery fixture','current_file_id':'','can_replace':True,
                        'files':[{'id':'id:held','name':'Different.psd','mismatch':True},
                                 {'id':'id:ordinary','name':'Recovery fixture.psd','mismatch':False}]})
                if url.endswith('/api/files-psd-attach'):
                    data=request.request.post_data_json;requests.append(data)
                    if data['file_id']=='id:ordinary':return request.fulfill(json={'ok':True})
                    if state['active']:return request.fulfill(status=409,json={'message':'A mapping worker is active.'})
                    if not data.get('manual_takeover_operation'):
                        return request.fulfill(status=409,json={'message':'Confirm manual takeover, then Save PSD again.',
                                                              'manual_takeover_operation':'exact-held-operation'})
                    assert data['manual_takeover_operation']=='exact-held-operation'
                    return request.fulfill(json={'ok':True})
                request.abort()
            page.route('**/*',route)
            page.goto('http://psd.local.test/files-psd-picker?product_gid=gid%3A%2F%2Fshopify%2FProduct%2F987')
            expect(page.locator('#identity')).to_have_text('Attach PSD to: Recovery fixture')
            page.locator('#files').select_option('id:held')
            page.locator('#save').click()
            expect(page.locator('#message')).to_have_text('Confirm the filename mismatch first.')
            assert not requests
            page.locator('#mismatch').check();page.locator('#save').click()
            expect(page.locator('#takeover-label')).to_be_visible()
            assert len(requests)==1 and 'manual_takeover_operation' not in requests[-1]
            page.locator('#save').click()
            expect(page.locator('#message')).to_have_text('Confirm manual takeover first.')
            assert len(requests)==1
            page.locator('#takeover').check();state['active']=True;page.locator('#save').click()
            expect(page.locator('#message')).to_have_text('A mapping worker is active.')
            assert len(requests)==2
            state['active']=False
            page.evaluate("window.saved=false;addEventListener('message',e=>{if(e.data.type==='sports-cave-psd-saved')window.saved=true;});")
            page.locator('#save').click();page.wait_for_function('window.saved')
            assert requests[-1]['confirm_mismatch'] and requests[-1]['manual_takeover_operation']=='exact-held-operation'
            # A new selection must never carry consent or operation ID from the old PSD.
            page.locator('#files').select_option('id:ordinary')
            expect(page.locator('#takeover-label')).to_be_hidden()
            assert not page.locator('#takeover').is_checked()
            with page.expect_response('**/api/files-psd-attach'):
                page.locator('#save').click()
            assert requests[-1]['file_id']=='id:ordinary' and 'manual_takeover_operation' not in requests[-1]
        finally:browser.close()
