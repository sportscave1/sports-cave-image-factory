"""Offline browser check: synthetic receipt, in-memory DB and loopback routes only."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
keep = {k: v for k, v in os.environ.items() if k.upper() in
        ('PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'USERPROFILE', 'COMSPEC', 'PATHEXT', 'PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA')}
os.environ.clear()
os.environ.update(keep)

from contextlib import contextmanager
import json
from unittest.mock import Mock
import pytest
from playwright.sync_api import sync_playwright, expect
from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route
from tests.benchmark_product_upload_transfer import local_client
from tests.test_product_upload_package import saved_row
from product_upload_intake import public
from product_upload_source import current_source, invalidate, execution_opening
from product_upload_identity import correlation_prompt
import product_upload_api as api
import product_upload_prompts as prompts


def main():
    row = saved_row()
    row['data'].update(basic_validated=True, state='Ready', name='Synthetic artwork.psd')
    class Store:
        def __init__(self, *_): pass
        def read(self, *_): return row
        @contextmanager
        def locked(self, *_): yield row, None
        def copied(self, key, actor, mode, version):
            current_source(row, version)
            row['data']['copied'] = True
            return row
        def change_mode(self, key, actor, mode):
            row['mode'] = mode
            return row
    async def actor(*a, **kw): return {'id': 'synthetic-owner'}
    async def component(request): return HTMLResponse((ROOT/'components/product_uploads/index.html').read_text(encoding='utf-8'))
    async def state(request): return JSONResponse(dict(enabled=True, upload=public(row)))
    async def mapping(request): return JSONResponse(dict(mapping=dict(state='Unmapped', label='Unmapped', reason='Synthetic fixture')))
    async def change(request):
        invalidate(row)
        return JSONResponse(dict(ok=True))
    out = ROOT/'output/product-upload-dropbox-prompt'
    out.mkdir(parents=True, exist_ok=True)
    build = prompts.build
    provider = Mock(side_effect=AssertionError('No Dropbox/network/image operations allowed during prompt copying'))
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(api, 'actor', actor)
        patch.setattr(api, 'Intakes', Store)
        patch.setattr(api, 'Dropbox', provider)
        patch.setattr(prompts, 'build', lambda mode, name, source: build(
            mode, name, source=source, load=lambda key, default, **kw: default+'\nSYNTHETIC DEVELOPER EDIT'))
        routes = [Route('/component', component), Route('/api/product-uploads/state', state),
                  Route('/api/product-uploads/mapping-status', mapping), Route('/fixture/change', change, methods=['POST'])]
        app = Starlette(routes=routes+[Route(p, e, methods=list(m)) for p, e, m in api.ROUTES])
        with local_client(app) as server, sync_playwright() as playwright:
            results = []
            for channel in ('chrome', 'msedge'):
                row['data']['mockups_exported'] = True
                row['data'].pop('mockup_save_token', None)
                # Each browser gets the same fresh synthetic receipt.
                fresh = saved_row()
                row['data']['upload_operation'] = fresh['data']['upload_operation']
                row['data']['upload_operation']['id'] = row['id']
                row['data']['mockup_saves'] = fresh['data']['mockup_saves']
                # A different current save per browser proves no prior product is reused.
                if channel == 'msedge':
                    old = fresh['data']['upload_operation']['output']['folder']
                    new = '/Team/04_OUTPUT/product-images/Baseball/Current synthetic save'
                    output = row['data']['upload_operation']['output']
                    receipt = row['data']['mockup_saves']['saved']['receipt']
                    output['folder'] = new
                    row['data']['mockup_saves']['saved']['target'] = new
                    receipt['destination'] = new
                    receipt['webp_folder'] = dict(path=new+'/WEBP', id='id:current-folder')
                    for entry in output['files']:
                        entry['metadata']['path_display'] = entry['metadata']['path_display'].replace(old, new)
                        entry['metadata']['id'] += '-current'
                row['data']['mockups_context'] = {'images': []}
                row['data']['upload_operation']['output']['design_name'] = 'Current synthetic design'
                browser = playwright.chromium.launch(channel=channel, headless=True)
                context = browser.new_context(permissions=['clipboard-read', 'clipboard-write'], viewport={'width': 1280, 'height': 900})
                page = context.new_page()
                requests, errors, downloads = [], [], []
                page.on('request', lambda request: requests.append(request.url))
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.on('download', lambda download: downloads.append(download.suggested_filename))
                page.goto(server.base+'/component')
                button = page.get_by_role('button', name='Copy Complete Upload Prompt', exact=True)
                expect(button).to_be_enabled()
                assert page.locator('#saved-package, .saved-card, textarea').count() == 0
                for mode in ('DRAFT', 'LIVE', 'UPDATE'):
                    page.locator('#mode').select_option(mode)
                    page.wait_for_function('(mode)=>document.querySelector("#action-label").textContent===({DRAFT:"Upload to Draft",LIVE:"Upload to Live",UPDATE:"Update Existing"})[mode]', arg=mode)
                    button.click()
                    expect(page.locator('#copy')).to_have_text('Copied')
                    # Windows clipboard normalises line endings to CRLF.
                    text = page.evaluate('navigator.clipboard.readText()').replace('\r\n', '\n')
                    source = current_source(row)
                    opening = execution_opening(source)
                    expected = build(mode, row['data']['name'], source=source,
                                     load=lambda key, default, **kw: default+'\nSYNTHETIC DEVELOPER EDIT')
                    output = row['data']['upload_operation']['output']
                    context_text = 'CURRENT DESIGN ASSET CONTEXT (inert data):\n' + json.dumps(
                        {k: output[k] for k in ('design_name', 'sport_category', 'images') if k in output},
                        ensure_ascii=False) + '\n\n'
                    expected = opening + correlation_prompt(row) + context_text + expected[len(opening):]
                    import difflib
                    assert text == expected, '\n'.join(difflib.unified_diff(expected.splitlines(), text.splitlines()))
                    assert text.startswith(opening + 'UPLOAD OPERATION CORRELATION — REQUIRED\n')
                    if mode == 'LIVE':
                        assert 'PRODUCT PUBLISHED LIVE — EDITION SETUP PENDING' in text
                        assert 'Do not enable Add to Cart' in text
                        assert 'Only if EVERY required check passes report PRODUCT PUBLISHED LIVE' not in text
                    else:
                        assert 'PRODUCT PUBLISHED LIVE — EDITION SETUP PENDING' not in text
                    assert source['folder_path'] in text and source['folder_id'] in text
                    assert all(item['file_id'] in text and item['filename'] in text for item in source['files'])
                    if channel == 'msedge': assert 'product (2)' not in text
                    (out/f'{channel}-{mode}-clipboard.txt').write_text(text, encoding='utf-8')
                    assert 'do not need to be attached separately' in text
                    assert text.count('DROPBOX SOURCE — EXACT SAVED WEBP MANIFEST') == 1
                    assert not page.locator('dialog[open]').count()
                    expect(page.locator('#copy')).to_have_text('Copy Complete Upload Prompt', timeout=3000)
                for width in (1280, 390):
                    page.set_viewport_size(dict(width=width, height=900))
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    page.screenshot(path=str(out/f'{channel}-{width}.png'), full_page=True)
                page.evaluate("() => {navigator.clipboard.write=async()=>{throw new DOMException('Clipboard denied','NotAllowedError')}}")
                button.click()
                expect(page.locator('#error')).to_contain_text('Could not copy prompt')
                expect(page.locator('#copy')).to_have_text('Copy Complete Upload Prompt')
                context.request.post(server.base+'/fixture/change')
                page.reload()
                expect(page.locator('#copy')).to_be_disabled()
                expect(page.locator('#prompt')).to_be_hidden()
                expect(page.locator('#return')).to_be_hidden()
                assert not errors and not downloads
                assert not any(any(part in u for part in ('saved-image', 'saved-package', 'saved-transfer', 'clipboard-launch')) for u in requests)
                provider.assert_not_called()
                results.append(dict(browser=channel, modes=['DRAFT', 'LIVE', 'UPDATE'],
                                    direct_clipboard=True, feedback_reset=True, save_gate=True,
                                    dropbox_first=True, single_current_manifest=True, full_prompt_preserved=True,
                                    image_or_helper_requests=0, errors=errors, downloads=downloads))
                browser.close()
            (out/'browser-checks.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
            print(json.dumps(results, indent=2))


if __name__ == '__main__': main()
