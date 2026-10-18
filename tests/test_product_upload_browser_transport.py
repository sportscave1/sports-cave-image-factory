"""Real Chromium transport faults against isolated SQL/storage; never the full app."""
from pathlib import Path
import json
import pytest
from playwright.sync_api import sync_playwright
from starlette.applications import Starlette
from starlette.responses import HTMLResponse, Response
from starlette.routing import Route
from tests.test_product_upload_intake import env, database, ADMIN, DiskDropbox, psd, digest, CHUNK
from tests.benchmark_product_upload_transfer import local_client

ROOT=Path(__file__).resolve().parents[1]


def test_browser_batched_lost_ack_reload_and_exact_resume(env,monkeypatch,tmp_path):
    import product_upload_api as api
    import files_upload_api as files
    provider=DiskDropbox(tmp_path/'provider')
    monkeypatch.setattr(api,'connect',env[0].connect);monkeypatch.setattr(api,'Dropbox',lambda:provider)
    monkeypatch.setattr(files,'_request_user',lambda *a,**k:ADMIN)
    async def html(request):return HTMLResponse((ROOT/'components/product_uploads/index.html').read_text(encoding='utf-8'))
    async def script(request):return Response((ROOT/'components/product_uploads/app.js').read_text(encoding='utf-8'),media_type='application/javascript')
    routes=[Route('/',html),Route('/product-uploads.js',script)]
    routes += [Route(p,e,methods=list(m)) for p,e,m in api.ROUTES if p!='/product-uploads.js']
    path=tmp_path/'non-production.psd';data=psd(3*CHUNK+73);path.write_bytes(data)
    with local_client(Starlette(routes=routes)) as client,sync_playwright() as playwright:
        browser=playwright.chromium.launch(headless=True);context=browser.new_context();page=context.new_page()
        page.goto(client.base+'/');page.wait_for_function('window.productUploadMetrics')
        # Accept the first 8 MiB, then lose its HTTP acknowledgement. Fail the next
        # request permanently to stop deterministically without long backoff waits.
        attempts=[]
        def fault(route):
            url=route.request.url;attempts.append(url)
            if len(attempts)==1:
                response=route.fetch();assert response.ok;route.abort('connectionreset')
            elif 'offset=8388608' in url:
                route.fulfill(status=409,content_type='application/json',body=json.dumps(dict(error='synthetic pause')))
            else:route.continue_()
        page.route('**/api/product-uploads/chunk?*',fault)
        page.locator('#file').set_input_files(str(path))
        page.wait_for_function("document.getElementById('stage').textContent==='Interrupted'",timeout=15000)
        assert attempts[0].endswith('offset=0') and attempts[1].endswith('offset=8388608')
        row=env[0].read(None,ADMIN['id']);key=str(row['id'])
        assert row['data']['offset']==2*CHUNK
        assert provider.calls==[('append',CHUNK),('append',CHUNK)]
        page.unroute('**/api/product-uploads/chunk?*',fault);page.reload()
        page.wait_for_function('window.productUploadMetrics')
        assert page.locator('#summary').is_hidden() and page.locator('#file').input_value()==''
        assert page.locator('#preview img').count()==0
        # A reselected file with the same name/size but different bytes cannot
        # reuse the old ID. It creates a distinct intake and cannot reach a job.
        # Keep this check on the backend start identity to avoid creating a second upload.
        with pytest.raises(ValueError,match='identity'):
            env[0].create(key,ADMIN['id'],'DRAFT',path.name,len(data),provider,'a'*64)
        provider.lose_finish=True
        page.locator('#file').set_input_files(str(path))
        page.wait_for_function("document.getElementById('stage').textContent==='Uploaded'",timeout=20000)
        result=env[0].read(key,ADMIN['id'])
        assert result['data']['source']['content_hash']==digest(data)
        assert sum(k=='append' for k,n in provider.calls)==4
        assert sum(k=='finish' for k,n in provider.calls)==1
        assert len(provider.sessions)==1
        assert page.evaluate("productUploadMetrics.requests.filter(r=>r.operation==='chunk').length")==1
        assert page.evaluate('productUploadMetrics.identity.length')==1
        env[1].execute('SELECT count(*) AS n FROM auto_edition_onboarding')
        assert env[1].fetchone()['n']==0
        context.close();browser.close()
