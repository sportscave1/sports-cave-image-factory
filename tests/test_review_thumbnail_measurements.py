"""Opt-in real-artwork COPIES, disposable SQL, local HTTP provider simulation.

SC_REVIEW_ARTWORK_DIR must contain explicit numbered folders with verified
record.json exports and master/number PNG copies. This never finds live artwork,
loads credentials, scans a catalogue or writes to a provider.
"""
import asyncio
from contextlib import contextmanager
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from tests.test_auto_editions_bulk import review,store,database,pglite_database
from tests.test_auto_editions_api import ADMIN
import auto_editions as ae
import auto_editions_bulk as bulk
from auto_editions_asset_cache import AssetCache
from auto_editions_bulk_jobs import PreviewStore
from auto_editions_review_thumbnails import ReviewBuildStore


@pytest.mark.skipif(not os.getenv('SC_REVIEW_ARTWORK_DIR'),reason='Explicit local artwork copies required for measurements')
def test_before_after_real_artwork_copies(review,monkeypatch):
    import requests,uvicorn,sc_auth,files_upload_api as files
    from starlette.applications import Starlette
    from starlette.responses import FileResponse,HTMLResponse,JSONResponse
    from starlette.routing import Route
    from auto_editions_cloud import DropboxAssets
    db,sql,_,_=review;monkeypatch.setenv('AUTO_EDITIONS_V15_ENABLED','false')
    root=Path(os.environ['SC_REVIEW_ARTWORK_DIR']).resolve();out=Path('output/bulk-thumbnails');cases=[]
    for directory in sorted(root.iterdir()):
        if not directory.is_dir():continue
        record=json.loads((directory/'record.json').read_text());bulk.evidence(record)
        from PIL import Image
        for asset in (record['manifest']['master'],record['manifest']['patches']['1']):
            with Image.open(directory/asset['name']) as image:
                if not image.info.get('icc_profile'):pytest.skip('Local real artwork copies lack required embedded ICC; validation retained.')
        cases.append((record,directory))
    assert 1<=len(cases)<=8
    for record,directory in cases:
        m=record['manifest'];pid=m['source']['product_gid'];fid=m['source']['file_id']
        sql.execute("INSERT INTO edition_products VALUES(%s,%s,%s,%s,%s,37,true,true)",(pid,pid.rsplit('/',1)[1],'Local artwork copy '+directory.name,'local-copy-'+directory.name,m['edition_total']))
        sql.execute("INSERT INTO product_psd_mappings(shopify_product_gid,dropbox_file_id,file_path,source,actor_id) VALUES(%s,%s,%s,'manual','synthetic-admin')",(pid,fid,'/Sportscave Team Folder/02_TASKS/03_DESIGNS-LIVE-ONLINE-UPLOADED/Local.psd'))
        sql.execute("INSERT INTO auto_edition_preparations VALUES(%s,%s::jsonb,%s::jsonb,%s::jsonb,'synthetic-admin',now())",(record['hash'],json.dumps(m),json.dumps(record['proofs']),json.dumps(record['receipts'])))
        sql.execute("INSERT INTO auto_edition_onboarding(product_gid,file_id,status,preparation_hash,source,edition_total) VALUES(%s,%s,'Blocked',%s,%s::jsonb,%s)",(pid,fid,record['hash'],json.dumps(m['source']),m['edition_total']))
    initial=bulk.listing(db.connect,[r['manifest']['source']['product_gid'] for r,_ in cases],ADMIN)
    assert len(initial['rows'])==len(cases) and all(r['eligible'] for r in initial['rows']),initial
    before_path=out/'before/auto_editions_bulk.py'
    assert before_path.is_file(),'Preserved initial working-source baseline is required.'
    # Timing probes only. Preserve all baseline rendering/queue/cache behavior.
    source=before_path.read_text(encoding='utf-8')
    source=source.replace('def get(self,record,fetch,width=300,store=None,cache_checked=False):','def get(self,record,fetch,width=300,store=None,cache_checked=False,queued_at=None):\n        queued_ms=(time.perf_counter()-queued_at)*1000 if queued_at else 0')
    source=source.replace('                # Resize each existing verified asset', '                decode_started=time.perf_counter()\n                # Resize each existing verified asset')
    source=source.replace('                finally:small.close()', '                finally:small.close()\n                measurement_rows.append(dict(hash=digest,queue_wait_ms=queued_ms,decode_compose_ms=(time.perf_counter()-decode_started)*1000))')
    source=source.replace('future=self.pool.submit(thumbnails.get,record,fetch,width,store,True)', 'future=self.pool.submit(thumbnails.get,record,fetch,width,store,True,queued_at=time.perf_counter())')
    # A module object is needed: the functions resolve their original globals.
    import types
    before=types.ModuleType('review_before');exec(compile(source,str(before_path),'exec'),before.__dict__)
    state=dict(module=before,html=(out/'before/components/auto_editions/bulk.html').read_text(encoding='utf-8'),transfer_bytes=0,transfers=0)
    phases=[];all_metrics=[];hits=[]
    async def page(request):return HTMLResponse(state['html'])
    async def listing(request):return await state['module'].list_api(request)
    async def image(request):return await state['module'].image_api(request)
    async def previews(request):
        body=await request.json();response=await state['module'].previews_api(request)
        hits.append(dict(phase=state['phase'],items=len(body['items']),hits=response.body.count(b'Content-Type: image/jpeg')))
        return response
    async def progress(request):return JSONResponse(dict(found=False,rows=[],counts={},active=False))
    lookup={r['hash']:directory for r,directory in cases}
    async def source_file(request):
        digest,name=request.path_params['digest'],request.path_params['name'];assert digest in lookup
        assert name in ('master.png','number-1.png');path=lookup[digest]/name
        state['transfer_bytes']+=path.stat().st_size;state['transfers']+=1
        return FileResponse(path,media_type='image/png')
    sock=socket.socket();sock.bind(('127.0.0.1',0));url='http://127.0.0.1:'+str(sock.getsockname()[1])
    def streamed(token,path):
        digest,name=path.rsplit('/',2)[-2:];response=requests.get(url+'/source/'+digest+'/'+name,stream=True,timeout=20);response.raise_for_status()
        return dict(size=(lookup[digest]/name).stat().st_size),response
    provider_instances=[]
    def storage():
        assets=DropboxAssets('local-fixture',SimpleNamespace(get_file_response=streamed));provider_instances.append(assets);return assets
    app=Starlette(routes=[Route('/',page),Route('/api/auto-editions/bulk/list',listing,methods=['POST']),Route('/api/auto-editions/bulk/previews',previews,methods=['POST']),Route('/api/auto-editions/bulk/image',image),Route('/api/auto-editions/bulk/progress',progress,methods=['POST']),Route('/source/{digest}/{name}',source_file)])
    server=uvicorn.Server(uvicorn.Config(app,log_level='error',lifespan='off'));thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True)
    sql_reads=[]
    @contextmanager
    def connection():
        sql_reads.append(time.perf_counter())
        with db.connect() as conn:yield conn
    original_put=PreviewStore.put
    def timed_put(self,key,data):
        phase=time.perf_counter();original_put(self,key,data);all_metrics.append(dict(persistence_ms=(time.perf_counter()-phase)*1000))
    class TimedCache(bulk.ReviewCache):
        def get(self,*args,**kwargs):
            metrics={};kwargs['metrics']=metrics
            result=super().get(*args,**kwargs);all_metrics.append(metrics);return result
    asset_cache=None;saved=(bulk.thumbnails,bulk.preview_builds)
    with patch.object(sc_auth,'_signing_key',return_value=b'local-artwork-fixture'),patch.object(files.os_accounts.DEFAULT_STORE,'get_user',return_value=ADMIN),patch.object(bulk.runtime,'enabled',return_value=True),patch.object(bulk.runtime,'storage',side_effect=storage),patch('auto_editions_bulk_runtime.connection',connection),patch('supabase_backend.read_connection',connection),patch.object(PreviewStore,'put',timed_put):
        thread.start()
        while not server.started:time.sleep(.01)
        try:
            cookie=sc_auth.create_user_auth_token(ADMIN['id'])
            for name,module in [('before',before),('after_fallback',bulk),('after',bulk)]:
                sql.execute('DELETE FROM auto_edition_review_previews');sql.execute('DELETE FROM auto_edition_review_preview_builds')
                state.update(module=module,html=(out/'before/components/auto_editions/bulk.html').read_text(encoding='utf-8') if name=='before' else Path('components/auto_editions/bulk.html').read_text(encoding='utf-8'),phase=name,transfer_bytes=0,transfers=0)
                module.snapshots.clear();module.measurement_rows=[]
                module.thumbnails=module.ReviewCache() if name=='before' else TimedCache()
                module.preview_builds=module.PreviewBuilds();asset_cache=AssetCache()
                pregeneration=[]
                with patch('auto_editions_asset_cache.prepared_assets',asset_cache):
                    if name=='after':
                        for record,directory in cases:
                            metrics={};bulk.ReviewCache().get(record,None,store=ReviewBuildStore(connection),local_root=directory,metrics=metrics);pregeneration.append(metrics)
                        # Process restart: no in-memory thumbnail or asset bytes survive.
                        module.thumbnails=TimedCache()
                    all_metrics.clear();sql_reads.clear();provider_instances.clear()
                    env={**os.environ,'NODE_PATH':r'C:\Users\hello\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules','SC_REVIEW_MEASURE':json.dumps(dict(url=url,cookie=cookie,cookieName=sc_auth.AUTH_COOKIE_NAME,ids=[r['manifest']['source']['product_gid'] for r,_ in cases],screenshot=str(out/name),result=str(out/(name+'-browser.json'))))}
                    result=subprocess.run(['node','tests/review_thumbnail_measure_ui.cjs'],env=env,capture_output=True,text=True,timeout=120);assert result.returncode==0,result.stdout+result.stderr
                    phases.append(dict(phase=name,browser=json.loads((out/(name+'-browser.json')).read_text()),provider_scope='Loopback HTTP transfer of explicit fixture PNGs, NOT live Dropbox latency',provider_bytes=state['transfer_bytes'],provider_transfers=state['transfers'],metadata_and_cache_connections=len(sql_reads),provider_transfer_ms=sum(a.timings.get('review_provider_transfer_ms',0) for a in provider_instances),verified_asset_cache_hits=sum(a.timings.get('review_asset_cache_hits',0) for a in provider_instances),build_metrics=(module.measurement_rows+list(all_metrics)) if name=='before' else list(all_metrics),pregeneration=pregeneration,delivery_hits=[h for h in hits if h['phase']==name]))
                module.preview_builds.pool.shutdown(wait=True)
                if asset_cache.directory:asset_cache.directory.cleanup()
            report=dict(scope=os.getenv('SC_REVIEW_MEASUREMENT_KIND','Real local artwork copies; synthetic transport receipts and SQL products')+'; isolated HTTP/SQL; no production credentials or writes',dimensions=[r['manifest']['dimensions'] for r,_ in cases],phases=phases)
            (out/'loading-measurements.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
            assert phases[2]['provider_bytes']==0 and phases[2]['provider_transfers']==0
            assert phases[1]['provider_bytes']==phases[0]['provider_bytes']
            assert phases[0]['provider_bytes']>0
        finally:
            bulk.thumbnails,bulk.preview_builds=saved
            server.should_exit=True;thread.join(5);sock.close()
