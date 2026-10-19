"""Opt-in local desktop fixture: real component/API/SQL, synthetic external services.

Run python -m tests.fixtures.product_upload_mapping_ui. No production config.
"""
import os
from pathlib import Path
import tempfile
from contextlib import contextmanager


@contextmanager
def fixture():
    import pytest
    from starlette.applications import Starlette
    from starlette.responses import HTMLResponse, JSONResponse
    from starlette.routing import Route
    from tests.test_product_upload_mapping import setup
    from tests.test_product_upload_intake import database, env, ADMIN
    from tests.benchmark_product_upload_transfer import local_client
    import product_upload_api as api, files_upload_api as files, product_upload_mapping as mapping
    root=Path(__file__).resolve().parents[2]
    db=database.__wrapped__();database_value=next(db)
    with tempfile.TemporaryDirectory(prefix='sc-map-fixture-') as directory, pytest.MonkeyPatch.context() as patch:
        environment=env.__wrapped__(database_value,Path(directory),patch)
        service,key,meta,product=setup(environment)
        working_attach=service.mappings.attach
        with environment[0].locked(key,ADMIN['id']) as (row,cur):
            row['data']['server_artwork']={'state':'Ready','settings':'synthetic'}
        patch.setattr(api,'connect',environment[0].connect)
        patch.setattr(api,'Dropbox',lambda:environment[2])
        patch.setattr(files,'_request_user',lambda *a,**kw:ADMIN)
        patch.setattr(mapping,'Mapping',lambda *a,**kw:service)
        history=[]
        class Requests:
            def __init__(self,app):self.app=app
            async def __call__(self,scope,receive,send):
                if scope['type']=='http':history.append(scope['method']+' '+scope['path'])
                await self.app(scope,receive,send)
        async def component(request):
            return HTMLResponse((root/'components/product_uploads/index.html').read_text(encoding='utf-8'))
        async def shell(request):
            return HTMLResponse('''<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1">
            <style>body{margin:0;font:14px/1.5 "Segoe UI",sans-serif;background:#faf9f5;color:#252930}header{position:sticky;top:0;padding:14px;background:#161713;color:#d0aa4c}main{padding:20px;max-width:1050px;margin:auto}input,button{padding:8px;font:inherit}label{display:block}iframe{width:100%;height:260px;border:1px solid #ddd}section{padding:16px;border:1px solid #ddd;margin:12px 0}#space{height:420px}</style>
            <header>Sports Cave OS · Isolated Product Upload mapping fixture</header><main><h2>Product Uploads</h2>
            <label>Product name <input id="name" value="Fixture artwork"></label><label>Sport category <input id="sport" value="V8 Supercars Wall Art"></label>
            <section>PSD: Same.psd — captured fixture revision a1<br>Prepared images retained<br>Saving to: V8 Supercars Wall Art / fixture-artwork</section>
            <div id="space">Prepared mockup section (fixture)</div><iframe id="handoff" title="Product Upload handoff" src="/component"></iframe>
            <section><button id="below" onclick="this.textContent='Below control works'">Control below results</button> <button onclick="document.querySelector('iframe').remove()">Unmount component</button></section>
            <section><button onclick="fetch('/fixture/fail',{method:'POST'}).then(()=>this.textContent='Fixture sync paused')">Pause fixture mapping</button> <button onclick="fetch('/fixture/restore',{method:'POST'}).then(()=>this.textContent='Fixture sync restored')">Restore fixture mapping</button></section>
            <label>Fixture viewport <select onchange="document.querySelector('main').style.maxWidth=this.value+'px'"><option value="1050">Desktop</option><option value="640">Narrow desktop</option></select></label>
            <label>Fixture text scale <select onchange="document.querySelector('iframe').contentDocument.documentElement.style.fontSize=this.value+'px';document.documentElement.style.fontSize=this.value+'px'"><option value="14">100%</option><option value="21">150%</option><option value="28">200%</option></select></label></main>
            <script>const f=document.querySelector('iframe');f.addEventListener('load',()=>f.contentWindow.postMessage({type:'streamlit:render',args:{section:'handoff',id:'KEY',mode:'DRAFT'}},location.origin));
            addEventListener('message',e=>{if(e.source===f.contentWindow&&e.data.type==='sports-cave-product-upload-height')f.style.height=e.data.height+'px';});</script>'''.replace('KEY',key))
        async def evidence(request):
            return JSONResponse(dict(requests=history,operation=key,source=meta,state=service.status(key,ADMIN)))
        async def control(request):
            if request.path_params['state']=='fail':
                def unavailable(*a,**kw):raise ConnectionError('Synthetic mapping outage')
                service.mappings.attach=unavailable
            else:service.mappings.attach=working_attach
            return JSONResponse(dict(ok=True))
        app=Starlette(routes=[Route('/',shell),Route('/component',component),Route('/fixture/evidence',evidence),
                             Route('/fixture/{state}',control,methods=['POST']),
                             *[Route(p,e,methods=list(m)) for p,e,m in api.ROUTES]])
        try:
            with local_client(Requests(app)) as client:
                yield dict(url=client.base,service=service,env=environment,key=key,requests=history)
        finally:
            db.close()


def main():
    keep={k:v for k,v in os.environ.items() if k.upper() in ('PATH','SYSTEMROOT','WINDIR','TEMP','TMP','USERPROFILE','AUTO_EDITIONS_TEST_PGLITE')}
    os.environ.clear();os.environ.update(keep)
    with fixture() as value:
        print(value['url'],flush=True)
        input('Local fixture running; press Enter to stop.\n')


if __name__=='__main__':main()
