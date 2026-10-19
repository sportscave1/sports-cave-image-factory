"""Loopback browser acceptance against real mapping/registration and disposable SQL.

No production server, credentials or external provider writes. Synthetic metadata
stands in for Shopify and Dropbox; no PSD bytes are read or moved.
"""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
keep = {k:v for k,v in os.environ.items() if k.upper() in ('PATH','SYSTEMROOT','WINDIR','TEMP','TMP',
    'USERPROFILE','COMSPEC','PATHEXT','PROGRAMFILES','PROGRAMFILES(X86)','LOCALAPPDATA','AUTO_EDITIONS_TEST_PGLITE')}
os.environ.clear(); os.environ.update(keep)
os.environ['PYTHON_DOTENV_DISABLED']='1'

import json
import time
from unittest.mock import Mock
from playwright.sync_api import sync_playwright, expect
from tests.fixtures.product_upload_mapping_ui import fixture
from tests.test_product_upload_mapping import no_jobs
from tests.test_product_upload_intake import ADMIN


def main():
    output=ROOT/'output/product-upload-sync-map'; output.mkdir(parents=True,exist_ok=True)
    results=[]
    with sync_playwright() as playwright:
        for channel,recover in [('chrome',False),('msedge',False),('chrome',True)]:
            with fixture() as local:
                provider=local['env'][2];service=local['service']
                provider.metadata_if_present=Mock(wraps=provider.metadata_if_present)
                browser=playwright.chromium.launch(channel=channel,headless=True)
                page=browser.new_page(viewport={'width':1280,'height':940})
                errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                page.route('**/*',lambda route:route.continue_() if route.request.url.startswith(local['url']) else route.abort())
                page.goto(local['url'])
                frame=page.frame_locator('#handoff')
                expect(frame.locator('#map')).to_be_enabled()
                assert not service.shopify.method_calls and not provider.metadata_if_present.called
                assert not any('mapping-status' in p or p.endswith('/map') for p in local['requests'])
                page.locator('#name').fill('Preserved product name')
                page.locator('#sport').fill('Preserved sport')
                page.evaluate("window.originalFrame=document.querySelector('#handoff')")
                if recover:
                    page.request.post(local['url']+'/fixture/fail')
                started=time.perf_counter()
                frame.locator('#map').click()
                expect(page.get_by_role('dialog',name='Sync & Map')).to_be_visible()
                assert ('upload='+local['key']) in page.url and 'sync_map=1' in page.url
                if recover:
                    expect(page.locator('[data-field="state"]')).to_have_text('Mapping failed',timeout=30000)
                    assert 'Success' not in frame.locator('#mapping-status').inner_text()
                    page.screenshot(path=str(output/'mapping-failed.png'),full_page=True)
                    assert provider.api.move_path.call_count==1
                    page.get_by_role('button',name='Close',exact=True).click()
                    page.reload() # Lost UI/response: the original operation remains durable.
                    frame=page.frame_locator('#handoff');expect(frame.locator('#map')).to_be_enabled()
                    frame.locator('#map').click()
                    expect(page.locator('[data-field="state"]')).to_have_text('Mapping failed',timeout=10000)
                    page.request.post(local['url']+'/fixture/restore')
                    page.locator('[data-field="retry"]').click()
                expect(frame.locator('#mapping-status')).to_have_text('✓ Success — synced and PSD mapped',timeout=30000)
                elapsed=round((time.perf_counter()-started)*1000,2)
                expect(page.locator('[data-field="steps"] li')).to_have_count(6)
                if not recover:
                    assert page.evaluate("window.originalFrame===document.querySelector('#handoff')")
                    expect(page.locator('#name')).to_have_value('Preserved product name')
                    expect(page.locator('#sport')).to_have_value('Preserved sport')
                no_jobs(local['env'])
                assert provider.api.move_path.call_count==1 and not errors, errors
                status=service.status(local['key'],ADMIN)
                page.screenshot(path=str(output/(channel+('-retry' if recover else '')+'.png')),full_page=True)
                page.get_by_role('button',name='Close',exact=True).click()
                page.locator('#below').click();expect(page.locator('#below')).to_have_text('Below control works')
                results.append(dict(browser=channel,recovery=recover,click_to_success_ms=elapsed,
                                    backend=status,requests=local['requests'],move_count=provider.api.move_path.call_count))
                browser.close()
    (output/'results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    print(json.dumps([dict(browser=r['browser'],recovery=r['recovery'],click_to_success_ms=r['click_to_success_ms'],
                           backend_ms=r['backend']['elapsed_ms']) for r in results],indent=2))


if __name__=='__main__':main()
