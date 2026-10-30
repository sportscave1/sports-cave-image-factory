"""Real Chromium + isolated HTTP/SQL; Dropbox/preview/native-ready are fixtures."""
import io
import json
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright, expect
from starlette.applications import Starlette
from starlette.responses import HTMLResponse, Response
from starlette.routing import Route
from tests.test_product_upload_intake import env, database, ADMIN
from tests.test_product_upload_dropbox import provider_fixture
from tests.test_product_upload_server_artwork import real_psd
from tests.benchmark_product_upload_transfer import local_client

ROOT=Path(__file__).resolve().parents[1]


def test_dropbox_picker_browser_exact_source_search_navigation_fresh_page_and_timings(env,monkeypatch,tmp_path):
    import product_upload_api as api
    import files_upload_api as files
    store,sql,provider=env;add=provider_fixture(provider)
    first=add('id:first','First.psd');second=add('id:second','Second.psd')
    from auto_editions import file_hash
    sources={}
    for meta,colour in [(first,(220,35,60)),(second,(20,60,220))]:
        path=real_psd(tmp_path/meta['name'],colour=colour);meta.update(content_hash=file_hash(path,dropbox=True),size=path.stat().st_size)
        provider.files[meta['id']]=meta;provider.files[meta['path_display']]=meta;sources[meta['id']]=path
    def download(metadata,destination,*,progress=None):
        Path(destination).write_bytes(sources[metadata['id']].read_bytes())
        if progress:progress(metadata['size'],metadata['size'])
    provider.download=download
    monkeypatch.setenv('SPORTS_CAVE_TEMP_DIR',str(tmp_path/'server'))
    from product_upload_dropbox import REVIEW
    sub=dict(id='id:sub',name='Subfolder',path_display=REVIEW+'/Subfolder',**{'.tag':'folder'})
    provider.files[sub['id']]=sub;provider.files[sub['path_display']]=sub
    monkeypatch.setattr(api,'connect',store.connect);monkeypatch.setattr(api,'Dropbox',lambda:provider)
    monkeypatch.setattr(files,'_request_user',lambda *a,**k:ADMIN)
    def directory(token,path,**kwargs):
        rows=[m for k,m in provider.files.items() if k.startswith('id:') and Path(m.get('path_display','')).parent.as_posix()==path]
        return dict(entries=rows,has_more=False,page_token='')
    monkeypatch.setattr(files,'_directory_page',directory)
    thumbnail=io.BytesIO();Image.new('RGB',(160,100),'navy').save(thumbnail,format='JPEG')
    provider.api.get_psd_thumbnail_bytes.return_value=thumbnail.getvalue()
    async def html(request):
        # Match the production page's same-origin script URLs when mounted at /.
        html=(ROOT/'components/product_uploads/index.html').read_text(encoding='utf-8')
        return HTMLResponse(html.replace('./app.js','/product-uploads.js').replace('./mapping.js','/product-upload-mapping.js'))
    app=Starlette(routes=[Route('/',html),*[Route(p,e,methods=list(m)) for p,e,m in api.ROUTES]])
    with local_client(app) as client,sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True);page=browser.new_page(viewport=dict(width=1280,height=900));errors=[];requests=[]
        page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda r:requests.append(r.url))
        page.goto(client.base);expect(page.locator('#summary')).to_be_hidden()
        assert page.locator('input[type=file]').count()==0
        page.locator('#choose').click();expect(page.locator('#picker')).to_be_visible()
        expect(page.locator('#picker-path')).to_have_attribute('title',REVIEW)
        page.get_by_role('button',name='▸ Subfolder',exact=True).click();expect(page.locator('#picker-path')).to_have_attribute('title',sub['path_display'])
        page.locator('#picker-path').get_by_role('button',name='Review',exact=True).click();expect(page.locator('#picker-path')).to_have_attribute('title',REVIEW)
        page.locator('#picker-search').fill('First');expect(page.locator('#picker-items button')).to_have_count(1)
        page.get_by_role('button',name='First.psd',exact=True).click()
        expect(page.locator('#filename')).to_have_text('First.psd');expect(page.locator('#preview img')).to_be_visible()
        key=page.evaluate('productUploadMetrics.selections[0].id')
        assert store.read(key,ADMIN['id'])['data']['source']['id']=='id:first'
        expect(page.locator('#stage')).to_have_text('Ready',timeout=10000)
        page.wait_for_function('productUploadMetrics.selections.filter(x=>x.selection_to_preview_ms!==undefined).length>=2')
        assert page.evaluate("() => {const img=document.querySelector('#preview img'),c=document.createElement('canvas');c.width=img.naturalWidth;c.height=img.naturalHeight;const g=c.getContext('2d');g.drawImage(img,0,0);return g.getImageData(300,200,1,1).data[0]>200;}")
        metrics=page.evaluate('productUploadMetrics')
        out=ROOT/'output/product-upload-dropbox';out.mkdir(parents=True,exist_ok=True)
        (out/'browser-fixture-timings.json').write_text(json.dumps(dict(boundaries='Real Chromium/HTTP/SQL/Pillow PSD decoder and prepared preview; synthetic source and Dropbox byte stream; Companion disconnected. Not production timing.',metrics=metrics),indent=2))
        page.screenshot(path=str(out/'picker-selection-desktop.png'),full_page=True)
        page.locator('#choose').click();page.locator('#picker-search').fill('Second');expect(page.locator('#picker-items button')).to_have_count(1)
        page.get_by_role('button',name='Second.psd',exact=True).click();expect(page.locator('#filename')).to_have_text('Second.psd')
        page.wait_for_function("old=>productUploadMetrics.selections.filter(x=>x.selection_to_bound_ms!==undefined).at(-1)?.id!==old",arg=key)
        assert page.evaluate('productUploadMetrics.selections.filter(x=>x.selection_to_bound_ms!==undefined).at(-1).id')!=key
        expect(page.locator('#stage')).to_have_text('Ready',timeout=10000)
        selected_mode=page.locator('#mode').input_value()
        selected_name=page.locator('#filename').inner_text();held_metadata=[]
        page.route('**/api/product-uploads/browse',lambda route:held_metadata.append(route))
        page.locator('#choose').click();expect(page.locator('#picker-status')).to_have_text('Loading Dropbox metadata…')
        expect(page.get_by_role('button',name='Close Dropbox picker',exact=True)).to_be_visible()
        assert page.get_by_role('button',name='Up',exact=True).count()==0
        page.get_by_role('button',name='Close Dropbox picker',exact=True).click();expect(page.locator('#picker')).not_to_be_visible()
        expect(page.locator('#choose')).to_be_focused();expect(page.locator('#filename')).to_have_text(selected_name)
        assert page.locator('#mode').input_value()==selected_mode
        page.unroute('**/api/product-uploads/browse')
        page.locator('#choose').click();page.keyboard.press('Escape');expect(page.locator('#picker')).not_to_be_visible();expect(page.locator('#choose')).to_be_focused()
        page.reload();expect(page.locator('#summary')).to_be_hidden();assert page.locator('#preview img').count()==0
        page.set_viewport_size(dict(width=390,height=844));page.locator('#choose').click();expect(page.locator('#picker')).to_be_visible()
        expect(page.locator('#picker-path')).to_have_attribute('title',REVIEW)
        expect(page.locator('#picker-items button')).to_have_count(3)
        page.screenshot(path=str(out/'picker-mobile.png'),full_page=True)
        assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
        page.route('**/__frame',lambda route:route.fulfill(content_type='text/html',body='''<iframe title="Product Upload" src="/" style="width:100%;height:280px;border:0"></iframe><script>addEventListener('message',e=>{if(e.data.type==='sports-cave-product-upload-height')document.querySelector('iframe').style.height=e.data.height+'px';});</script>'''))
        page.goto(client.base+'/__frame');frame=page.frame_locator('iframe')
        frame.locator('#choose').click();expect(frame.locator('#picker-path')).to_have_attribute('title',REVIEW)
        page.wait_for_function("() => {const f=document.querySelector('iframe'),p=f.contentDocument.querySelector('#picker');return p.getBoundingClientRect().bottom<=f.getBoundingClientRect().height;}")
        # Status copy can wrap differently; the picker must retain a useful
        # viewport and fit the resized host frame, rather than a magic 400px.
        assert 300<frame.locator('#picker').bounding_box()['height']<=page.viewport_size['height']
        frame.locator('#picker-close').click();expect(frame.locator('#picker')).to_be_hidden()
        assert not any('/chunk' in url or '/start' in url or '/finish' in url for url in requests)
        assert not provider.sessions and not provider.calls and not errors
        assert not env[0].read(key,ADMIN['id'])['data'].get('companion_connected')
        browser.close()
