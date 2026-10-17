"""Loopback-only integration harness. Real intake/SQL/services; provider doubles.

Never imports the production server or loads credentials. The disposable database
and cloud disk are test fixtures, not the installed Companion or production.
"""
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def application(technical=False):
    allowed={'SYSTEMROOT','WINDIR','PATH','PATHEXT','TEMP','TMP','COMSPEC','USERPROFILE','APPDATA','LOCALAPPDATA','AUTO_EDITIONS_TEST_PGLITE'}
    clean={k:v for k,v in os.environ.items() if k.upper() in allowed}
    os.environ.clear();os.environ.update(clean)
    os.environ['PRODUCT_UPLOAD_AUTOMATIC_ENABLED']='true'
    os.environ['AUTO_EDITIONS_VISUAL_AUTO_APPROVAL_ENABLED']='false'
    import dotenv
    dotenv.load_dotenv=lambda *a,**k:False
    import requests
    from urllib.parse import urlparse
    request=requests.sessions.Session.request
    def local_request(self,method,url,*a,**k):
        if urlparse(url).hostname not in ('127.0.0.1','localhost','::1'):
            raise RuntimeError('External requests are disabled in the local integration harness.')
        return request(self,method,url,*a,**k)
    requests.sessions.Session.request=local_request
    import pytest,shutil,json
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.responses import JSONResponse,HTMLResponse
    from starlette.concurrency import run_in_threadpool
    from tests.test_product_upload_intake import database,env,ADMIN,product
    from tests.test_product_upload_handoff import import_synthetic
    from product_upload_services import Handoff
    import product_upload_api as api
    import files_upload_api,prompt_store,auto_editions_bulk as bulk
    from unittest.mock import Mock
    output=ROOT/'output/product-uploads/preview-session';output.mkdir(parents=True,exist_ok=True)
    db=database.__wrapped__();fixture=next(db);patch=pytest.MonkeyPatch()
    local=env.__wrapped__(fixture,output,patch);store,sql,provider=local
    for file in ('20261016071758_auto_editions_bulk_operations.sql','20261016211735_review_thumbnail_build_leases.sql'):
        sql.execute((ROOT/'supabase/migrations'/file).read_text())
    if technical:
        sql.execute((ROOT/'supabase/migrations/20261017001547_auto_editions_technical_completion.sql').read_text())
        patch.setenv('AUTO_EDITIONS_TECHNICAL_FLOW_ENABLED','true')
    patch.setattr(api,'connect',store.connect);patch.setattr(api,'Dropbox',lambda:provider)
    failure=api.failure
    def local_failure(error):
        import traceback
        traceback.print_exception(error)
        return failure(error)
    patch.setattr(api,'failure',local_failure)
    patch.setattr(files_upload_api,'_request_user',lambda request,**kwargs:ADMIN)
    patch.setattr(prompt_store,'get_prompt',lambda key,default,**kw:default)
    p=product();shop=Mock();shop.fetch_product_by_shopify_id.return_value=p
    patch.setattr(api,'Handoff',lambda connect,dropbox:Handoff(connect,dropbox,lookup=lambda text:[p] if text.strip()=='New Art' else [],shopify=shop))
    prepared={};fetches=[]
    def fetch(digest,asset,target):
        fetches.append(asset['name']);shutil.copyfile(prepared[digest]/asset['name'],target)
    patch.setattr(bulk,'prepared_fetch',lambda:fetch)
    async def complete(request):
        def generate():
            row=store.read(None,ADMIN['id']);folder=output/str(row['id']);folder.mkdir(exist_ok=True)
            record=import_synthetic(local,row,folder);prepared[record['hash']]=folder
            if technical:
                from types import SimpleNamespace
                from auto_editions_technical import Technical
                integration=Mock();integration.psd_open_metadata.side_effect=lambda token,key,**kw:provider.metadata_if_present(key)
                assets=SimpleNamespace(token='synthetic',integration=integration)
                assert Technical(store.connect).run_one(assets,pid=row['data']['product_gid'],local_root=folder)=='Cloud Ready'
            return record['hash']
        return JSONResponse(dict(synthetic_preparation=await run_in_threadpool(generate)))
    async def metrics(request):
        import psutil
        return JSONResponse(dict(server_rss=psutil.Process().memory_info().rss,provider_calls=provider.calls,preview_asset_fetches=fetches))
    async def reset(request):
        def clean_fixture():
            sql.execute('TRUNCATE product_upload_intakes,product_psd_mappings,auto_edition_onboarding,auto_edition_onboarding_audit,auto_edition_layouts,auto_edition_preparations,edition_products,edition_runs,shopify_products CASCADE')
            provider.calls.clear();fetches.clear()
        await run_in_threadpool(clean_fixture)
        return JSONResponse(dict(disposable_fixture_reset=True))
    async def files(request):
        # The real Files navigation is verified by URL; this loopback harness
        # intentionally cannot connect the production Files browser.
        return HTMLResponse('<p>Local Files navigation boundary: product-images</p><a href="/product-uploads">Return to Product Uploads</a>')
    app=Starlette(routes=[Route(path,handler,methods=list(methods)) for path,handler,methods in api.ROUTES]+
        [Route('/__test/complete',complete,methods=['POST']),Route('/__test/reset',reset,methods=['POST']),Route('/__test/metrics',metrics),Route('/',files)])
    app.state.fixture=(db,patch,local)
    return app


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8676);parser.add_argument('--technical',action='store_true');args=parser.parse_args()
    app=application(args.technical)
    import uvicorn
    try:uvicorn.run(app,host='127.0.0.1',port=args.port,access_log=False)
    finally:
        db,patch,_=app.state.fixture;patch.undo();db.close()
