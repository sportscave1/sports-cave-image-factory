"""Opt-in, isolated comparison using a user-selected local PSD; no cloud calls.

PRODUCT_UPLOAD_BENCHMARK_PSD selects a read-only source. Git objects supply the
two released UI implementations without touching either checkout. Auth/Dropbox
are doubles, SQL is disposable PGlite, PSD decode/ICC/preview are real.
"""
import ast
import hashlib
from contextlib import nullcontext
import io
import json
import os
from pathlib import Path
import statistics
import subprocess
import tempfile
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image
from playwright.sync_api import sync_playwright
from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Route
from tests.test_product_upload_intake import database, env, ADMIN
from tests.test_product_upload_dropbox import provider_fixture
from tests.benchmark_product_upload_transfer import local_client

ROOT = Path(__file__).resolve().parents[1]
REVISIONS = {'previous': 'e0a5419b', 'released': 'f5d925e8', 'fixed': None}


def source(label, path):
    ref = REVISIONS[label]
    return subprocess.check_output(['git', 'show', ref+':'+path], cwd=ROOT).decode('utf-8') if ref else (ROOT/path).read_text(encoding='utf-8')


def page_renderer(label, store):
    """Execute the real page's mount decisions, isolating only its upper renderer."""
    node = next(n for n in ast.parse(source(label, 'product_upload_mockups_ui.py')).body
                if isinstance(n, ast.FunctionDef) and n.name == 'render_page')
    calls = []
    state = {'_product_upload_visit': 'benchmark'}
    st = SimpleNamespace(session_state=state, html=lambda *a: None, query_params={},
                         container=lambda **kw: nullcontext(), rerun=lambda: None)
    def component(**kwargs):
        calls.append({k: v for k, v in kwargs.items() if k != 'default'})
    app = SimpleNamespace(BASE_DIR=ROOT, current_os_user=lambda: ADMIN,
                          get_components_module=lambda: SimpleNamespace(declare_component=lambda *a, **kw: component))
    ns = {'st': st, 'render_design': lambda *a: None}
    exec(compile(ast.Module(body=[node], type_ignores=[]), 'page-mount-'+label, 'exec'), ns)
    def render(key):
        calls.clear()
        state['_product_upload_active'] = key
        ns['render_page'](app)
        return list(calls)
    return render


def test_psd_stage_comparison(env, monkeypatch, tmp_path):
    path = Path(os.environ.get('PRODUCT_UPLOAD_BENCHMARK_PSD', ''))
    if not path.is_file(): pytest.skip('Set PRODUCT_UPLOAD_BENCHMARK_PSD to the representative local PSD')
    import auto_editions as ae
    import product_upload_api as api
    import product_upload_artwork as artwork
    import product_upload_jobs as jobs
    import files_upload_api as files
    import image_factory
    import product_upload_prompts as prompts
    for name in ('product_upload_artwork.py','product_upload_dropbox.py','image_factory.py'):
        assert source('previous',name)==source('released',name)==source('fixed',name), name
    store, sql, provider = env
    meta = provider_fixture(provider)(name=path.name)
    meta.update(size=path.stat().st_size, content_hash=ae.file_hash(path, dropbox=True))
    provider.files[meta['id']] = meta
    provider.files[meta['path_display']] = meta
    # Embedded ICC is retained. No live policies, Shopify, or source-folder writes.
    monkeypatch.setattr(api, 'connect', store.connect)
    monkeypatch.setattr(api, 'Dropbox', lambda: provider)
    monkeypatch.setattr(files, '_request_user', lambda *a, **kw: ADMIN)
    monkeypatch.setattr(prompts, 'build', Mock(side_effect=AssertionError('Prompt work before Copy')))
    monkeypatch.setattr(image_factory.prompt_store, 'get_prompt', lambda key, default='', **kw: default)
    monkeypatch.setattr(image_factory.prompt_store, 'get_cached_prompt', lambda key, default='', **kw: default)
    monkeypatch.setattr(files, '_directory_page', lambda *a, **kw: dict(entries=[meta], has_more=False, page_token=''))
    thumbnail = io.BytesIO(); Image.new('RGB', (160, 100), 'navy').save(thumbnail, 'JPEG')
    provider.api.get_psd_thumbnail_bytes.return_value = thumbnail.getvalue()
    runs = []
    # The production server is Linux. Keep the Windows harness below MAX_PATH.
    short_temp = tempfile.TemporaryDirectory(prefix='pu-')
    cache_root = Path(short_temp.name)
    out = ROOT/'output/product-upload-psd-performance'; out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='chrome', headless=True)
        # Alternating labels; cold application derivative cache, warm local disk.
        for trial in range(5):
            labels = list(REVISIONS)
            labels = labels[trial % 3:]+labels[:trial % 3]
            for label in labels:
                manager = jobs.Jobs(); monkeypatch.setattr(jobs, 'JOBS', manager)
                monkeypatch.setenv('SPORTS_CAVE_TEMP_DIR', str(cache_root/f'{label}-{trial}'))
                timings = {}; calls = []; selected_at = [None]
                metadata = provider.metadata_if_present
                def counted_metadata(key):
                    calls.append(('metadata', key)); return metadata(key)
                with monkeypatch.context() as patch:
                    patch.setattr(provider, 'metadata_if_present', counted_metadata)
                    def download(selected, destination, *, progress=None):
                        calls.append(('download', selected['id']))
                        timings['download_start'] = time.perf_counter()
                        with path.open('rb') as src, Path(destination).open('wb') as dst:
                            count = 0
                            while block := src.read(4*1024*1024):
                                dst.write(block); count += len(block)
                                if progress: progress(count, selected['size'])
                        timings['transfer_ms'] = 1000*(time.perf_counter()-timings['download_start'])
                    patch.setattr(provider, 'download', download, raising=False)
                    decode = artwork.decode
                    def timed_decode(*a, **kw):
                        start = time.perf_counter()
                        try: return decode(*a, **kw)
                        finally: timings['decode_icc_png_ms'] = 1000*(time.perf_counter()-start)
                    patch.setattr(artwork, 'decode', timed_decode)
                    mount = page_renderer(label, store)
                    async def layout(request): return JSONResponse(mount(request.query_params.get('id')))
                    async def html(request): return HTMLResponse(source(label, 'components/product_uploads/index.html'))
                    async def script(request):
                        name = {'/product-uploads.js': 'app.js', '/product-upload-mapping.js': 'mapping.js', '/product-upload-package.js': 'package.js'}[request.url.path]
                        return Response(source(label, 'components/product_uploads/'+name), media_type='application/javascript')
                    async def shell(request):
                        return HTMLResponse('''<iframe id="upload" src="/component" style="width:100%;height:440px"></iframe><div id="final"></div><script>
                        const args=new Map(); let id='', serial=0;
                        args.set('upload',{section:'upload'});
                        addEventListener('message',async e=>{
                          const frame=[...document.querySelectorAll('iframe')].find(f=>f.contentWindow===e.source);if(!frame)return;
                          if(e.data.type==='streamlit:componentReady')frame.contentWindow.postMessage({type:'streamlit:render',args:args.get(frame.id)},location.origin);
                          if(e.data.type==='streamlit:setComponentValue'&&frame.id==='upload'){
                            const current=++serial;id=e.data.value.id||'';
                            const layout=await fetch('/fixture/layout?id='+encodeURIComponent(id)).then(r=>r.json());if(current!==serial)return;
                            const handoff=layout.find(x=>x.section==='handoff');let f=document.querySelector('#handoff');
                            if(handoff&&!f){args.set('handoff',handoff);f=document.createElement('iframe');f.id='handoff';f.src='/component';document.querySelector('#final').append(f);}
                            else if(!handoff&&f)f.remove();
                          }
                        });</script>''')
                    app = Starlette(routes=[Route('/', shell), Route('/component', html), Route('/fixture/layout', layout),
                        *[Route(p, script) for p in ('/product-uploads.js','/product-upload-mapping.js','/product-upload-package.js')],
                        *[Route(p, e, methods=list(m)) for p, e, m in api.ROUTES]])
                    with local_client(app) as client:
                        context = browser.new_context(viewport={'width':1280,'height':900})
                        page = context.new_page(); requests = []; errors = []
                        page.add_init_script("window.jank=[];let last=performance.now();function tick(t){window.jank.push(t-last);last=t;requestAnimationFrame(tick)}requestAnimationFrame(tick);")
                        page.on('pageerror', lambda e: errors.append(str(e)))
                        def request(r):
                            requests.append({'path':r.url.split(client.base)[-1], 'frame':r.frame.name or r.frame.url, 'time':time.perf_counter()})
                            if r.url.endswith('/select'): selected_at[0] = time.perf_counter()
                        page.on('request', request)
                        page.goto(client.base)
                        frame = page.frame_locator('#upload')
                        frame.locator('#choose').click()
                        frame.get_by_role('button', name=path.name, exact=True).click()
                        page.wait_for_function("document.querySelector('#upload').contentWindow.productUploadMetrics.selections.some(x=>x.selection_to_mockup_ready_ms!==undefined)", timeout=90000)
                        page.wait_for_function("document.querySelector('#upload').contentWindow.productUploadMetrics.selections.some(x=>x.representation==='prepared-artwork')", timeout=90000)
                        metrics = page.locator('#upload').evaluate('(f)=>f.contentWindow.productUploadMetrics')
                        key = next(x['id'] for x in metrics['selections'] if 'selection_to_bound_ms' in x)
                        job = manager.snapshot(key, ADMIN['id'], 'prepare')
                        counts = {op:sum(op in x['path'] for x in requests) for op in ('/select','/prepare','/state','source-preview','mapping-status','/prompt','saved-package')}
                        result = dict(label=label, trial=trial+1, selection_to_download_start_ms=1000*(timings['download_start']-selected_at[0]),
                            selection_to_bound_ms=next(x['selection_to_bound_ms'] for x in metrics['selections'] if 'selection_to_bound_ms' in x),
                            transfer_ms=timings['transfer_ms'], decode_icc_png_ms=timings['decode_icc_png_ms'], prepare_ms=job['elapsed_ms'],
                            selection_to_artwork_ready_ms=next(x['selection_to_mockup_ready_ms'] for x in metrics['selections'] if 'selection_to_mockup_ready_ms' in x),
                            selection_to_preview_ms=next(x['selection_to_preview_ms'] for x in metrics['selections'] if x.get('representation')=='prepared-artwork'),
                            frame_gap_p95_ms=page.evaluate('jank.sort((a,b)=>a-b)[Math.floor(jank.length*.95)]'),
                            frame_gap_max_ms=page.evaluate('Math.max(...jank)'),
                            counts=counts, download_count=sum(x[0]=='download' for x in calls), metadata_calls=sum(x[0]=='metadata' for x in calls),
                            final_mounted=page.locator('#handoff').count(), stages=job['stages'], errors=errors)
                        ready_row = store.read(key, ADMIN['id'])
                        started = time.perf_counter()
                        generation = jobs.generate(store.connect, ready_row, ADMIN['id'], path.stem, 'Motorsport',
                            lambda:provider, ROOT, threading.Semaphore(1),
                            lambda name,sport:image_factory.build_lifestyle_prompt_items(name,sport,local_only=True))
                        while manager.snapshot(key,ADMIN['id'],'generate')['state'] in ('Queued','Running'):
                            if time.perf_counter()-started>60:raise AssertionError('Generation timed out')
                            time.sleep(.01)
                        outputs=manager.result(key,ADMIN['id'],'generate',generation['token'])
                        assert outputs and len(outputs['assets'])==5, manager.snapshot(key,ADMIN['id'],'generate')
                        assert sum(x[0]=='download' for x in calls)==1
                        result['mockup_generation_ms']=1000*(time.perf_counter()-started)
                        result['selection_to_mockup_files_ready_ms']=1000*(time.perf_counter()-selected_at[0])
                        with Image.open(artwork.folder(ready_row,ready_row['data']['server_artwork']['settings'])/'artwork.png') as image:
                            # Generated ICC profile creation timestamps can differ;
                            # compare decoded pixels, dimensions and mode instead.
                            result['artwork_pixels_sha256']=hashlib.sha256(image.tobytes()).hexdigest()
                            result['artwork_size']=list(image.size);result['artwork_mode']=image.mode
                        assert not errors and result['download_count']==1 and counts['/select']==counts['/prepare']==1
                        assert counts['/prompt']==0
                        if label=='fixed': assert result['final_mounted']==0 and counts['mapping-status']==0
                        runs.append(result); print(json.dumps(result), flush=True)
                        context.close()
                    manager.pool.shutdown()
    report = dict(filename=path.name, bytes=path.stat().st_size, revisions=REVISIONS,
        conditions='Windows local Chrome; real routes, disposable PGlite, same read-only PSD, warm OS file cache, cold derivative cache each run; local disk replay replaces Dropbox network; synthetic early thumbnail; real Pillow ICC decode, prepared preview and five mockups using repository templates; actual render_page mount decisions with upper Streamlit renderer stubbed; processing modules verified byte-identical across revisions.',
        unmeasured=['Live Dropbox/network transfer and Render CPU/load', 'Real Streamlit websocket/rerender latency', 'Shopify transfer'], runs=runs,
        medians={label:{field:round(statistics.median(r[field] for r in runs if r['label']==label),2) for field in
            ('selection_to_bound_ms','selection_to_download_start_ms','transfer_ms','decode_icc_png_ms','prepare_ms','selection_to_artwork_ready_ms','selection_to_preview_ms','mockup_generation_ms','selection_to_mockup_files_ready_ms','frame_gap_p95_ms','frame_gap_max_ms')} for label in REVISIONS})
    assert len({r['artwork_pixels_sha256'] for r in runs})==1
    (out/'benchmark.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report['medians'], indent=2))
