"""Synthetic Library DOM: native original download and revoked-blob recovery."""
from pathlib import Path
import base64
import pytest
pw=pytest.importorskip('playwright.sync_api')


def test_library_download_is_bound_and_original_bytes_survive_revocation():
    root=Path(__file__).resolve().parents[1]/'windows-upload-companion'
    job='00000000-0000-0000-0000-000000000001'
    url='https://chatgpt.com/library?file_id=libfile_abc123'
    with pw.sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True)
        page=browser.new_page()
        page.route('**/*',lambda r:r.fulfill(content_type='text/html',body='<html><body></body></html>'))
        page.goto(url)
        page.evaluate("""() => {
          window.chrome={runtime:{id:'fixture',onMessage:{addListener:f=>window.listener=f}}};window.clicks=0;
          document.body.innerHTML='<button aria-label="Download">Download</button>';
          document.querySelector('button').onclick=()=>{
            clicks++;window.original=URL.createObjectURL(new Blob(['approved bytes']));URL.revokeObjectURL(original);
          };
        }""")
        page.add_script_tag(content=(root/'ad-downloads.js').read_text())
        page.add_script_tag(content=(root/'ad-library.js').read_text())
        def request(**extra):
            return page.evaluate("m=>new Promise(r=>listener(m,{id:'fixture'},r))",
                dict(type='project:ad-library',job=job,name='ad_copy.csv',url=url,**extra))
        assert request()['clicked']
        blob=page.evaluate("m=>new Promise(r=>listener({...m,blob:original},{id:'fixture'},r))",
            dict(type='project:ad-library-blob',job=job,name='ad_copy.csv',url=url))
        assert base64.b64decode(blob['data'])==b'approved bytes'
        wrong=page.evaluate("m=>new Promise(r=>listener({...m,blob:original},{id:'fixture'},r))",
            dict(type='project:ad-library-blob',job=job,name='man-cave.jpg',url=url))
        assert wrong.get('error')
        page.goto(url+'9')
        page.evaluate("window.chrome={runtime:{id:'fixture',onMessage:{addListener:f=>window.listener=f}}}")
        page.add_script_tag(content=(root/'ad-library.js').read_text())
        assert request().get('error')
        browser.close()


@pytest.mark.parametrize('case', ['exact', 'wrong-name', 'wrong-file', 'thumbnail', 'duplicate'])
def test_library_without_download_reads_only_the_displayed_full_original(case):
    import io
    from PIL import Image
    image = io.BytesIO()
    Image.new('RGB', (256, 256) if case == 'thumbnail' else (1024, 1024), 'navy').save(image, format='JPEG')
    original = image.getvalue()
    url = 'https://chatgpt.com/library?file_id=libfile_abc123'
    path = '/api/library/files/' + ('libfile_wrong' if case == 'wrong-file' else 'libfile_abc123') + '/content'
    name = 'other.jpg' if case == 'wrong-name' else 'man-cave(20261121-022748).jpg'
    html = '<html><body>' + ('<img alt="'+name+'" src="'+path+'">') * (2 if case == 'duplicate' else 1) + '</body></html>'
    root = Path(__file__).resolve().parents[1]/'windows-upload-companion'
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page()
        reads = []
        def respond(route):
            if '/api/library/files/' in route.request.url:
                reads.append(route.request.url)
                route.fulfill(content_type='image/jpeg', body=original)
            else:
                route.fulfill(content_type='text/html', body=html)
        page.route('**/*', respond)
        page.goto(url)
        page.locator('img').first.evaluate('(image)=>image.decode()')
        page.evaluate("window.chrome={runtime:{id:'fixture',onMessage:{addListener:f=>window.listener=f}}}")
        page.add_script_tag(content=(root/'ad-library.js').read_text())
        result = page.evaluate("m=>new Promise(r=>listener(m,{id:'fixture'},r))", dict(
            type='project:ad-library', job='00000000-0000-0000-0000-000000000001', name='man-cave.jpg', url=url))
        if case == 'exact':
            assert base64.b64decode(result['data']) == original
            assert len(reads) == 2  # displayed image, then identical original fetch
        else:
            assert result == {'clicked': False}
            assert len(reads) == 1
        browser.close()
