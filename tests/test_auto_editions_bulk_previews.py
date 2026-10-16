"""Real local image-serving, signed cookies, streamed PNGs and isolated PostgreSQL. No live data."""
import asyncio
from copy import deepcopy
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock,patch

import pytest
from PIL import Image
import auto_editions as ae
import auto_editions_bulk as bulk
from auto_editions_bulk_jobs import PreviewStore
from tests.test_auto_editions_bulk import prepared,review,store,database,pglite_database
from tests.test_auto_editions_bulk_handoff import preview_cases
from tests.test_auto_editions_api import ADMIN


def test_disposable_cache_outage_does_not_break_valid_preview(tmp_path):
    record,assets=prepared(tmp_path);broken=Mock(get=Mock(side_effect=RuntimeError('cache unavailable')),put=Mock(side_effect=RuntimeError('cache unavailable')))
    before=Path('output/bulk-preview-fix/before-auto_editions_bulk.py')
    if before.exists():
        spec=importlib.util.spec_from_file_location('preview_before',before);old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
        with pytest.raises(RuntimeError,match='cache unavailable'):old.ReviewCache().get(record,assets.fetch,store=broken)
    data=bulk.ReviewCache().get(record,assets.fetch,store=broken)
    assert bulk.ReviewCache.valid(data,300)


def test_corrupt_cached_jpeg_is_rebuilt_and_replaced(review):
    db,sql,record,assets=review;cache=PreviewStore(db.connect);key=ae.fingerprint(bulk.thumbnails.key(record))
    cache.put(key,b'not a JPEG');assert cache.get(key)==b'not a JPEG'
    data=bulk.ReviewCache().get(record,assets.fetch,store=cache)
    assert bulk.ReviewCache.valid(data,300) and cache.get(key)==data
    assets.fetch.reset_mock();assert bulk.ReviewCache().get(record,assets.fetch,store=cache)==data;assets.fetch.assert_not_called()


def test_slow_disconnected_preview_builds_are_bounded_and_deduplicated(tmp_path):
    record,assets=prepared(tmp_path);cases=preview_cases(record,9);builds=bulk.PreviewBuilds();gate=threading.Event();entered=threading.Event()
    def slow(*args):entered.set();assert gate.wait(5);return assets.fetch(*args)
    cache=Mock(get=Mock(return_value=None),put=Mock())
    with patch.object(bulk,'thumbnails',bulk.ReviewCache()):
        try:
            started=time.perf_counter()
            assert builds.read(cases[0][2],slow,300,cache) is None
            assert time.perf_counter()-started<.2 and entered.wait(1)
            for _ in range(10):assert builds.read(cases[0][2],slow,300,cache) is None
            assert len(builds.pending)==1
            for _,_,current in cases[1:]:assert builds.read(current,slow,300,cache) is None
            assert len(builds.pending)==8
            # Accepted image work survives loss of its HTTP caller, but owns no approval state.
            gate.set();builds.pool.shutdown(wait=True)
            assert bulk.ReviewCache.valid(builds.read(cases[0][2],slow,300,cache),300)
        finally:gate.set();builds.pool.shutdown(wait=True)


def test_transient_build_failure_can_recover_without_sticky_failure(tmp_path):
    record,assets=prepared(tmp_path);builds=bulk.PreviewBuilds();cache=Mock(get=Mock(return_value=None),put=Mock())
    failed=False
    def fetch(*args):
        nonlocal failed
        if not failed:failed=True;raise RuntimeError('temporary transport failure')
        return assets.fetch(*args)
    with patch.object(bulk,'thumbnails',bulk.ReviewCache()):
        try:
            assert builds.read(record,fetch,300,cache) is None
            future,created=next(iter(builds.pending.values()))
            with pytest.raises(RuntimeError):future.result(timeout=2)
            with pytest.raises(RuntimeError):builds.read(record,fetch,300,cache)
            # Advance only the disposable failure retention, without sleeping or provider calls.
            future.review_finished_at=time.monotonic()-2
            assert builds.read(record,fetch,300,cache) is None
            next(iter(builds.pending.values()))[0].result(timeout=2)
            assert bulk.ReviewCache.valid(builds.read(record,fetch,300,cache),300)
        finally:builds.pool.shutdown(wait=True)


def test_real_http_browser_previews_and_reopen(review,tmp_path):
    import requests
    import uvicorn
    import files_upload_api as files
    import sc_auth
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.responses import FileResponse,HTMLResponse,JSONResponse
    from auto_editions_cloud import DropboxAssets
    from auto_editions_asset_cache import AssetCache
    db,sql,record,_=review
    # Print-sized synthetic PNGs, real RGB ICC and real plaque/number patches.
    m=record['manifest']
    for asset in [m['master'],*m['patches'].values()]:
        path=tmp_path/asset['name']
        with Image.open(path) as image:
            profile=image.info['icc_profile']
            with image.resize((image.width*20,image.height*20)) as enlarged:enlarged.save(path,icc_profile=profile)
        asset['sha256']=ae.file_hash(path)
    for field in ['dimensions','source_dimensions','number_region','plaque_bounds']:m[field]=[n*20 for n in m[field]]
    for receipt in record['receipts']['assets']:receipt['bytes']=(tmp_path/receipt['name']).stat().st_size
    from tests.test_auto_editions_bulk import rebind
    rebind(record);cases=preview_cases(record,40)
    cache=PreviewStore(db.connect);sample=bulk.ReviewCache().get(record,lambda digest,asset,dest:Path(dest).write_bytes((tmp_path/asset['name']).read_bytes()))
    for _,_,current in cases[1:4]:cache.put(ae.fingerprint(bulk.thumbnails.key(current)),sample)
    cache.put(ae.fingerprint(bulk.thumbnails.key(cases[0][2])),b'broken-cache-image')
    downloads=[];image_responses=[]
    async def source(request):
        name=request.path_params['name'];assert name in {a['name'] for a in [m['master'],*m['patches'].values()]}
        downloads.append(name);await asyncio.sleep(.08)
        return FileResponse(tmp_path/name,media_type='image/png')
    async def page(request):return HTMLResponse(Path('components/auto_editions/bulk.html').read_text())
    async def listing(request):
        await bulk.actor(request);body=await request.json();start=body['cursor'];selected=cases[start:start+10]
        for pid,digest,current in selected:bulk.snapshots[(str(ADMIN['id']),pid,digest)]=(time.monotonic()+900,current)
        return JSONResponse(dict(rows=[dict(product_gid=pid,hash=digest,title='Synthetic plaque '+pid.rsplit('/',1)[1],eligible=True,reason='') for pid,digest,_ in selected],next_cursor=start+10 if start+10<len(cases) else None))
    async def progress(request):return JSONResponse(dict(found=False,rows=[],counts={},active=False))
    async def image(request):
        result=await bulk.image_api(request);image_responses.append(result.status_code);return result
    sock=socket.socket();sock.bind(('127.0.0.1',0));url='http://127.0.0.1:'+str(sock.getsockname()[1])
    def streamed(token,path):
        name=path.rsplit('/',1)[1];response=requests.get(url+'/source/'+name,stream=True,timeout=5);response.raise_for_status()
        return dict(size=(tmp_path/name).stat().st_size),response
    assets=DropboxAssets('synthetic-only',SimpleNamespace(get_file_response=streamed))
    app=Starlette(routes=[Route('/',page),Route('/source/{name}',source),Route('/api/auto-editions/bulk/list',listing,methods=['POST']),Route('/api/auto-editions/bulk/previews',bulk.previews_api,methods=['POST']),Route('/api/auto-editions/bulk/image',image),Route('/api/auto-editions/bulk/progress',progress,methods=['POST'])])
    server=uvicorn.Server(uvicorn.Config(app,log_level='error',lifespan='off'));thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True)
    builds=bulk.PreviewBuilds();cache_bytes=bulk.ReviewCache();asset_cache=AssetCache()
    with patch.object(bulk,'current_previews',side_effect=lambda connect,entries:{(p,h) for p,h,_ in entries}),patch.object(sc_auth,'_signing_key',return_value=b'local-preview-fixture'),patch.object(files.os_accounts.DEFAULT_STORE,'get_user',return_value=ADMIN),patch.object(bulk.runtime,'enabled',return_value=True),patch.object(bulk.runtime,'storage',return_value=assets),patch('auto_editions_bulk_runtime.connection',db.connect),patch.object(bulk,'preview_builds',builds),patch.object(bulk,'thumbnails',cache_bytes),patch('auto_editions_asset_cache.prepared_assets',asset_cache):
        thread.start()
        while not server.started:time.sleep(.01)
        try:
            cookie=sc_auth.create_user_auth_token(ADMIN['id'])
            pid,digest,current=cases[5];bulk.snapshots[(str(ADMIN['id']),pid,digest)]=(time.monotonic()+900,current)
            start=time.perf_counter();accepted=requests.get(url+'/api/auto-editions/bulk/image',params=dict(product_gid=pid,hash=digest),cookies={sc_auth.AUTH_COOKIE_NAME:cookie},timeout=2)
            assert accepted.status_code==202 and time.perf_counter()-start<1
            accepted.close()  # Closing the HTTP caller cannot cancel the disposable cache build.
            env={**os.environ,'NODE_PATH':r'C:\Users\hello\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules','SC_PREVIEW_FIXTURE':json.dumps(dict(url=url,cookie=cookie,cookieName=sc_auth.AUTH_COOKIE_NAME,ids=[p for p,_,_ in cases]))}
            result=subprocess.run(['node','tests/test_auto_editions_bulk_previews_ui.cjs'],env=env,text=True,capture_output=True,timeout=120)
            assert result.returncode==0,result.stdout+result.stderr
            print(result.stdout)
            assert 202 in image_responses and 200 in image_responses
            assert len(downloads)<=4,downloads  # Shared verified local bytes; never forty full downloads.
            assert len(asset_cache.entries)==2
            report=json.loads(Path('output/bulk-preview-fix/real-browser.json').read_text());report.update(thumbnail_bytes=len(sample),thumbnail_width=300,source_dimensions=m['dimensions'],source_png_downloads=len(downloads),original_png_bytes=sum((tmp_path/name).stat().st_size for name in downloads))
            timings={}
            for binary in [False,True]:
                start=time.perf_counter();response=requests.post(url+'/api/auto-editions/bulk/previews',json=dict(items=[dict(product_gid=p,hash=h) for p,h,_ in cases[:8]],binary=binary),cookies={sc_auth.AUTH_COOKIE_NAME:cookie},timeout=5);assert response.status_code==200
                timings['binary' if binary else 'base64_json']=dict(milliseconds=round((time.perf_counter()-start)*1000,2),wire_bytes=len(response.content))
            assert timings['binary']['wire_bytes']<timings['base64_json']['wire_bytes']
            report['warm_eight_preview_transport']=timings;Path('output/bulk-preview-fix/real-browser.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
            assert cache.get(ae.fingerprint(bulk.thumbnails.key(cases[0][2])))!=b'broken-cache-image'
        finally:
            builds.pool.shutdown(wait=True);server.should_exit=True;thread.join(5);sock.close()
            if asset_cache.directory:asset_cache.directory.cleanup()
