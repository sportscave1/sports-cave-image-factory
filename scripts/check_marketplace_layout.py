"""Offline browser acceptance against an in-process synthetic ASGI app. No server."""
import base64
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

allowed = {'PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'COMSPEC', 'PATHEXT',
           'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'PROGRAMFILES', 'PROGRAMFILES(X86)'}
for key in list(os.environ):
    if key.upper() not in allowed:
        os.environ.pop(key)
os.environ.update(PYTHONDONTWRITEBYTECODE='1', STREAMLIT_BROWSER_GATHER_USAGE_STATS='false')

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient
import marketplace as core
import marketplace_api as api
from marketplace_store import MarketplaceStore
from tests.test_marketplace import FakeDatabase, sample, photograph

OUT = ROOT / '.tmp-marketplace-layout'
OUT.mkdir(exist_ok=True)
store = MarketplaceStore(FakeDatabase().connect)
app = Starlette(routes=[Route(path, endpoint, methods=list(methods)) for path, endpoint, methods in api.ROUTES])
api._RATE.clear()
results = []
with patch.object(api, 'MarketplaceStore', return_value=store), TestClient(app, base_url=core.PUBLIC_ORIGIN) as client, sync_playwright() as p:
    browser = p.chromium.launch(channel='msedge', headless=True)
    context = browser.new_context()
    def route(request_route):
        request = request_route.request
        if request.url.startswith(core.PUBLIC_ORIGIN):
            response = client.request(request.method, request.url, content=request.post_data_buffer,
                                      headers={k: v for k, v in request.headers.items() if k.lower() != 'host'})
            request_route.fulfill(status=response.status_code, headers=dict(response.headers), body=response.content)
        else:
            # No external network, credentials or application worker processes.
            request_route.abort()
    context.route('**/*', route)
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    for width in (1440, 768, 390, 320):
        page.set_viewport_size({'width': width, 'height': 1000})
        page.goto(core.PUBLIC_ORIGIN + '/marketplace')
        page.get_by_role('heading', level=1).wait_for()
        assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'), width
        page.screenshot(path=str(OUT / f'home-{width}.png'), full_page=True)
        results.append({'page': 'home', 'width': width, 'height': page.locator('body').bounding_box()['height'], 'overflow': False})
    page.get_by_role('link', name='Sell an item', exact=True).click()
    page.locator('input[name=price]').fill('200')
    assert '190.00' in page.locator('#fee-quote').inner_text()
    page.screenshot(path=str(OUT / 'sell-320.png'), full_page=True)
    for field, value in sample().items():
        control = page.locator(f'#seller-form [name={field}]')
        if not control.count():
            continue
        if field == 'consent':
            control.check()
        elif field in ('category', 'sport', 'condition', 'seller_type'):
            control.select_option(value)
        else:
            control.fill(str(value))
    image = base64.b64decode(photograph())
    page.locator('#photos').set_input_files([{'name': 'front.jpg', 'mimeType': 'image/jpeg', 'buffer': image},
                                           {'name': 'back.jpg', 'mimeType': 'image/jpeg', 'buffer': image}])
    page.get_by_role('button', name='Submit for review').click()
    page.get_by_role('heading', name='You’re in the review queue.').wait_for()
    row = store.listings()[0]
    store.moderate(row['id'], 'published', 1, 'synthetic-admin')
    for width in (1440, 390, 320):
        page.set_viewport_size({'width': width, 'height': 1000})
        page.goto(core.PUBLIC_ORIGIN + core.listing_url(row))
        assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'), width
        page.screenshot(path=str(OUT / f'item-{width}.png'), full_page=True)
        results.append({'page': 'item', 'width': width, 'overflow': False})
    page.locator('[name=name]').fill('Synthetic buyer')
    page.locator('[name=email]').fill('buyer@example.invalid')
    page.locator('[name=message]').fill('Can I see the tag?')
    page.locator('[name=consent]').check()
    page.get_by_role('button', name='Send enquiry').click()
    page.get_by_role('heading', name='Enquiry received.').wait_for()
    assert len(store.enquiries()) == 1
    assert not errors, errors
    browser.close()
report = {'layouts': results, 'seller_submission': 'passed', 'buyer_enquiry': 'passed', 'javascript_errors': errors}
(OUT / 'results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report))
