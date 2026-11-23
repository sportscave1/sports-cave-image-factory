"""Container-only real PostgreSQL, actual routes/assets and Chromium workload."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import threading
import time
import uuid

if not Path('/opt/studio/entry.py').is_file() or {p.name for p in Path('/sys/class/net').iterdir()} != {'lo'}:
    raise RuntimeError('Requires the reviewed network-isolated synthetic preview')
sys.path.insert(0, '/tmp/source')
os.environ['DATABASE_URL'] = 'postgresql://studio@127.0.0.1:55432/studio?sslmode=disable'
import psycopg
from psycopg.rows import dict_row
from PIL import Image, ImageDraw
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient
import uvicorn
from playwright.sync_api import sync_playwright
import marketplace_api as api
from marketplace_store import MarketplaceStore, put
from marketplace_dropbox import MarketplaceDropboxStorage

folder = Path('/tmp/marketplace-evidence')
folder.mkdir()
counts = {'db': 0, 'provider': 0, 'provider_bytes': 0, 'db_ms': 0., 'provider_ms': 0.}
mutex = threading.Lock()


def connect():
    start = time.perf_counter()
    conn = psycopg.connect(os.environ['DATABASE_URL'], row_factory=dict_row)
    with mutex:
        counts['db'] += 1
        counts['db_ms'] += (time.perf_counter() - start) * 1000
    return conn


with connect() as conn:
    conn.execute('CREATE TABLE IF NOT EXISTS crm_runtime_state(key TEXT PRIMARY KEY,value JSONB,updated_at TIMESTAMPTZ DEFAULT now())')

objects = {}


class Response:
    status_code = 206
    def __init__(self, data, ref):
        self.data = data
        self.headers = {'Dropbox-API-Result': json.dumps(ref), 'Content-Range': f'bytes 0-{len(data)-1}/{len(data)}'}
    def iter_content(self, chunk_size):
        yield self.data
    def close(self):
        pass


class Transport:
    def get(self, url, **kwargs):
        assert url == 'https://content.dropboxapi.com/2/files/download'
        target = json.loads(kwargs['headers']['Dropbox-API-Arg'])
        ref, data = objects[target['path']]
        assert target['rev'] == ref['rev']
        start = time.perf_counter()
        time.sleep(.120)  # Controlled provider delay, not a live latency claim.
        with mutex:
            counts['provider'] += 1
            counts['provider_bytes'] += len(data)
            counts['provider_ms'] += (time.perf_counter() - start) * 1000
        return Response(data, ref)


storage = MarketplaceDropboxStorage(context={'token': 'synthetic-only', 'namespace': '123'}, http=Transport())
import supabase_backend as backend
import database_read_pool as read_pool
real_read_connection = backend.read_connection
backend.connect = connect
@contextmanager
def measured_read_connection():
    start = time.perf_counter()
    with real_read_connection() as conn:
        with mutex:
            counts['db'] += 1
            counts['db_ms'] += (time.perf_counter()-start)*1000
        yield conn
backend.read_connection = measured_read_connection
store = MarketplaceStore(media_storage=storage)
api.MarketplaceStore = lambda: store
ids = [str(uuid.UUID(int=1000+i)) for i in range(24)]
for number, key in enumerate(ids):
    refs = []
    for index in range(4):
        image = Image.new('RGB', (600, 750), (40+number*5, 70+index*30, 110))
        draw = ImageDraw.Draw(image)
        draw.rectangle((90, 70, 510, 680), outline='gold', width=8)
        draw.text((130, 330), f'SYNTHETIC {number:02d} PHOTO {index}', fill='white')
        out = io.BytesIO()
        image.save(out, format='WEBP', quality=85)
        data = out.getvalue()
        ref = {'provider': 'dropbox', 'id': f'id:fixture-{number}-{index}', 'rev': f'{number*4+index+1:016x}',
               'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        objects[ref['id']] = ref, data
        refs.append(ref)
    row = dict(id=key, title=f'Synthetic collector jersey {number:02d}', category='jerseys', sport='NRL',
               team='Synthetic team', condition='Excellent', description='Synthetic item with four photographs.',
               price_cents=20000+number*100, shipping_cents=1500, location='Synthetic, AU', seller_name='Synthetic collector',
               seller_type='Private collector', seller_email='private@example.invalid', provenance='Synthetic fixture only.',
               status='published', revision=2, history=[], photo_count=4, has_video=False, video_seconds=0,
               published_at=f'2026-11-01T00:00:{23-number:02d}+00:00', media_source={'provider':'dropbox', 'photos':refs})
    with connect() as conn:
        put(conn, 'listing:'+key, row)

app = Starlette(routes=[Route(p, e, methods=list(m)) for p,e,m in api.ROUTES])
server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=8866, log_level='error', access_log=False))
thread = threading.Thread(target=server.run, daemon=True)
thread.start()
deadline = time.monotonic()+10
while not server.started and time.monotonic()<deadline:
    time.sleep(.02)
assert server.started
origin = 'http://127.0.0.1:8866'
result = {'workload': '24 synthetic listings, 4 photos each, real PostgreSQL and Marketplace routes; controlled 120ms Dropbox read',
          'cold_samples_ms': [], 'warm_samples_ms': [], 'cold_costs': [], 'warm_costs': [], 'screenshots': {}, 'checks': []}
result['workflow_phases_ms'] = []


def reset_cache():
    try:
        import marketplace_photo_cache as cache
        cache.PHOTOS.clear()
    except ImportError:
        pass


def snapshot():
    with mutex:
        return dict(counts)


def delta(before):
    after = snapshot()
    return {k: round(after[k]-v, 3) for k,v in before.items()}


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True, chromium_sandbox=True,
        args=['--disable-background-networking','--disable-component-update'])
    context = browser.new_context(viewport={'width':1280, 'height':900}, device_scale_factor=1)
    # Kernel network isolation denies external fonts in both versions. Do not
    # install request interception: Playwright routing disables HTTP caching,
    # unlike a normal browser revisiting the site's cacheable static assets.
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))

    def ready_grid():
        page.wait_for_function('''() => document.querySelectorAll('.listing-card').length === 12''')
        # Demand all twelve lazy photographs without changing the product markup.
        page.evaluate("document.querySelectorAll('.listing-card img').forEach(i=>i.loading='eager')")
        page.wait_for_function("() => [...document.querySelectorAll('.listing-card img')].every(i=>i.complete && i.naturalWidth>0)")

    def workflow():
        start = time.perf_counter()
        page.goto(origin+'/marketplace/browse', wait_until='domcontentloaded')
        ready_grid()
        grid = time.perf_counter()
        page.locator('.listing-card a').first.click()
        page.evaluate("document.querySelectorAll('.gallery img').forEach(i=>i.loading='eager')")
        page.wait_for_function("() => [...document.querySelectorAll('.gallery img')].every(i=>i.complete && i.naturalWidth>0)")
        page.wait_for_function("() => {let i=document.querySelector('#media-photo-0 img');return i && i.complete && i.naturalWidth>0}")
        detail = time.perf_counter()
        page.get_by_role('link', name='View photo 2', exact=True).click()
        page.wait_for_function("() => {let i=document.querySelector('#media-photo-1 img');return i && i.complete && i.naturalWidth>0 && document.querySelector('[data-media-caption]').textContent.includes('2')}")
        assert 'private@example.invalid' not in page.content()
        end = time.perf_counter()
        result['workflow_phases_ms'].append({'grid':round((grid-start)*1000,3), 'detail':round((detail-grid)*1000,3), 'selection':round((end-detail)*1000,3)})
        # Account for late lazy requests before counting provider work or starting
        # the next sample; the fixed idle interval is outside the measured time.
        page.wait_for_load_state('networkidle')
        return round((end-start)*1000, 3)

    for sample in range(3):
        reset_cache()
        before = snapshot()
        result['cold_samples_ms'].append(workflow())
        result['cold_costs'].append(delta(before))
        before = snapshot()
        result['warm_samples_ms'].append(workflow())
        result['warm_costs'].append(delta(before))
    # Full image bytes, markup and desktop/mobile appearance must match baseline.
    for mode, size in [('desktop', {'width':1280,'height':900}), ('mobile', {'width':390,'height':844})]:
        page.set_viewport_size(size)
        for name, path in [('browse','/marketplace/browse'), ('detail','/marketplace/item/'+ids[0])]:
            page.goto(origin+path, wait_until='networkidle')
            page.evaluate("document.querySelectorAll('img').forEach(i=>i.loading='eager')")
            page.wait_for_function("() => [...document.images].every(i=>i.complete && i.naturalWidth>0)")
            page.evaluate('window.scrollTo(0,0)')
            shot = page.screenshot(full_page=True, animations='disabled')
            label = mode+'-'+name
            (folder/(label+'.png')).write_bytes(shot)
            result['screenshots'][label] = hashlib.sha256(shot).hexdigest()
    # Search, sorting, pagination and anonymous contact access remain actual routes.
    page.goto(origin+'/marketplace/browse?q=jersey+00', wait_until='networkidle')
    assert page.locator('.listing-card').count() == 1
    page.goto(origin+'/marketplace/browse?sort=price_high&page=2', wait_until='networkidle')
    assert page.locator('.listing-card').count() == 12
    assert 'jersey 11' in page.locator('.listing-card').first.inner_text()
    page.goto(origin+'/marketplace/contact/'+ids[0], wait_until='networkidle')
    assert 'private@example.invalid' not in page.content()
    reset_cache()
    before = snapshot()
    tabs = [context.new_page() for _ in range(3)]
    for tab in tabs:
        tab.goto(origin+'/marketplace/browse', wait_until='domcontentloaded')
        tab.evaluate("document.querySelectorAll('.listing-card img').forEach(i=>i.loading='eager')")
    for tab in tabs:
        tab.wait_for_function("() => document.querySelectorAll('.listing-card').length===12 && [...document.querySelectorAll('.listing-card img')].every(i=>i.complete && i.naturalWidth>0)")
        tab.wait_for_load_state('networkidle')
        tab.close()
    result['three_tab_costs'] = delta(before)
    assert not errors, errors
    context.close()
    browser.close()
result['checks'].append('Actual Chromium populated browse -> detail -> photo selection, three cold and three warm samples; desktop/mobile screenshots; search/sort/page/privacy; no page errors')

with TestClient(app) as client:
    url = '/marketplace/images/'+ids[0]+'/0.webp'
    expected = objects['id:fixture-0-0'][1]
    reset_cache()
    before = snapshot()
    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(lambda _: client.get(url), range(8)))
    assert all(r.status_code==200 and r.content==expected for r in responses)
    result['concurrent_costs'] = delta(before)
    assert all(r.headers['cache-control']=='no-store' for r in responses)
    assert client.head(url).status_code == 200
    # Withdrawal, pending and database failure must deny even a warmed photo.
    with connect() as conn:
        conn.execute("UPDATE crm_runtime_state SET value=jsonb_set(value,'{status}','\"withdrawn\"') WHERE key=%s", ('marketplace:v1:listing:'+ids[0],))
    assert client.get(url).status_code == 404
    assert client.get('/marketplace/item/'+ids[0]).status_code == 404
    with connect() as conn:
        conn.execute("UPDATE crm_runtime_state SET value=jsonb_set(value,'{status}','\"pending\"') WHERE key=%s", ('marketplace:v1:listing:'+ids[0],))
    assert client.get(url).status_code == 404
    with connect() as conn:
        conn.execute("UPDATE crm_runtime_state SET value=jsonb_set(value,'{status}','\"published\"') WHERE key=%s", ('marketplace:v1:listing:'+ids[0],))
    assert client.get(url).content == expected
    real_connect, real_reads = backend.connect, backend.read_connection
    def failed_connect():
        raise OSError('Synthetic database outage')
    backend.connect = backend.read_connection = failed_connect
    assert client.get(url).status_code == 503
    backend.connect, backend.read_connection = real_connect, real_reads
    assert client.get(url).content == expected
    assert client.get('/marketplace/images/'+ids[0]+'/8.webp').status_code == 404
    # A short repeat-read soak after recovery must retain bounded cache state.
    before = snapshot()
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert all(r.content == expected for r in pool.map(lambda _: client.get(url), range(64)))
    result['soak_costs'] = delta(before)
    try:
        from marketplace_photo_cache import PHOTOS
        assert PHOTOS._bytes <= PHOTOS.max_bytes
        assert len(PHOTOS._values) <= PHOTOS.max_entries
        assert len(PHOTOS._inflight) == 0
        result['cache_retained_bytes'] = PHOTOS._bytes
    except ImportError:
        pass
result['checks'].append('Eight concurrent requests preserve bytes; fresh DB approval on cache hits; withdrawal/pending/DB outage deny; recovery and invalid index checked; no browser caching')
result['photo_bytes'] = sum(len(data) for ref,data in objects.values())
result['read_pool_stats'] = read_pool.stats()
read_pool.close()
server.should_exit = True
thread.join(timeout=5)
assert not thread.is_alive()
print('MARKETPLACE_RESULT='+json.dumps(result), flush=True)
