"""Strict template decoding and actual iframe HTTP recovery; synthetic data only."""
import asyncio
import logging
import os
from pathlib import Path
import socket
import subprocess
import threading
import time
from unittest.mock import AsyncMock, patch

import pytest
from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Route
import uvicorn

import auto_editions_bulk as bulk
from tests.test_auto_editions_api import ADMIN, request

ROOT = Path(__file__).parents[1]
TEMPLATE = ROOT / 'components/auto_editions/bulk.html'


def template_root(tmp_path, content):
    target = tmp_path / 'components/auto_editions/bulk.html'
    target.parent.mkdir(parents=True)
    target.write_bytes(content)
    return target


def legacy_segment():
    # Verified original source defect: CP1252 ellipsis and separator in UTF-8 HTML.
    return b"Loading preview\x85 / \xb7 Loading preview\x85"


def test_repository_template_preserves_utf8_and_repaired_punctuation():
    text = TEMPLATE.read_bytes().decode('utf-8')
    assert 'Loading preview\u2026' in text
    assert "row.reason+' \u00b7 Loading preview\u2026'" in text
    assert 'Loading review metadata\u2026' in text
    assert '\ufffd' not in text


@pytest.mark.parametrize('content', [TEMPLATE.read_bytes(), '<p>Caf\u00e9 \u2026 \u65e5\u672c\u8a9e</p>'.encode('utf-8')])
def test_page_serves_valid_utf8_without_changing_content(tmp_path, content):
    template_root(tmp_path, content)
    with patch.object(bulk, 'Path', return_value=tmp_path/'auto_editions_bulk.py'), patch.object(bulk, 'actor', new=AsyncMock(return_value=ADMIN)), patch.object(bulk, 'approve_one') as approve:
        response = asyncio.run(bulk.page(request()))
    assert response.status_code == 200
    assert response.body.decode('utf-8') == content.decode('utf-8').replace('\r\n', '\n')
    assert response.headers['content-type'].startswith('text/html')
    approve.assert_not_called()


@pytest.mark.parametrize('failure', ['encoding', 'missing', 'permission'])
def test_page_failure_is_readable_html_with_logged_traceback(tmp_path, caplog, failure):
    if failure == 'encoding':
        template_root(tmp_path, b'<p>UTF-8 \xe2\x80\xa6</p>' + legacy_segment())
    user = AsyncMock(side_effect=PermissionError('private diagnostic')) if failure == 'permission' else AsyncMock(return_value=ADMIN)
    with patch.object(bulk, 'Path', return_value=tmp_path/'auto_editions_bulk.py'), patch.object(bulk, 'actor', new=user), patch.object(bulk, 'approve_one') as approve, caplog.at_level(logging.ERROR, logger=bulk.__name__):
        response = asyncio.run(bulk.page(request()))
    assert response.status_code == (403 if failure == 'permission' else 503)
    assert response.headers['content-type'].startswith('text/html')
    text = response.body.decode('utf-8')
    assert 'Retry</button>' in text and 'Close</button>' in text
    assert 'codec' not in text and 'private diagnostic' not in text
    assert response.headers['cache-control'] == 'private, no-store'
    assert caplog.records[-1].exc_info is not None
    if failure == 'encoding':
        assert isinstance(caplog.records[-1].exc_info[1], UnicodeDecodeError)
    approve.assert_not_called()


def test_actual_http_page_retry_items_and_close(tmp_path):
    target = template_root(tmp_path, legacy_segment())
    valid = TEMPLATE.read_bytes()
    state = dict(pages=0, lists=0, writes=0)
    pid = 'gid://shopify/Product/987'
    # Minimal native-grid adapter for the existing, unmodified popup bridge.
    parent = '''<!doctype html><div class="st-key-edition-workspace"><div data-testid="stDataFrame"><canvas width="500" height="100"></canvas></div></div>
<script>window.SportsCaveEditionStatusState={rows:[{product_gid:'gid://shopify/Product/987'}]};
window.SportsCaveEditionStatus={refresh(){}};
const c=document.querySelector('canvas');c.__reactFiberFixture={memoizedProps:{columns:[{title:'Auto Editions'}],rows:1,getCellContent(){}},ref:{current:{getBounds(){return {x:10,width:200}}}}};</script>
<iframe src="/bridge"></iframe>'''

    async def parent_page(req): return HTMLResponse(parent)
    async def bridge(req): return HTMLResponse('<script>'+ (ROOT/'components/edition_auto_status/bulk.js').read_text(encoding='utf-8')+'</script>')
    async def page(req):
        state['pages'] += 1
        response = await bulk.page(req)
        # First real request exercises broken source, retry exercises repaired source.
        target.write_bytes(valid)
        return response
    async def listing(req):
        state['lists'] += 1
        return JSONResponse(dict(rows=[dict(product_gid=pid, hash='a'*64, title='Existing review fixture', eligible=True, reason='')], next_cursor=None, duration_ms=1))
    async def previews(req): return JSONResponse(dict(rows=[]))
    async def image(req):
        import base64
        return Response(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWQAAAABJRU5ErkJggg=='),media_type='image/png')
    async def progress(req): return JSONResponse(dict(found=False, rows=[], counts={}, active=False))
    async def unexpected_write(req):
        state['writes'] += 1
        return Response(status_code=500)
    app = Starlette(routes=[Route('/',parent_page),Route('/bridge',bridge),Route('/auto-editions/bulk',page),Route('/api/auto-editions/bulk/list',listing,methods=['POST']),Route('/api/auto-editions/bulk/previews',previews,methods=['POST']),Route('/api/auto-editions/bulk/image',image),Route('/api/auto-editions/bulk/progress',progress,methods=['POST']),Route('/api/auto-editions/bulk/approve',unexpected_write,methods=['POST'])])
    sock=socket.socket();sock.bind(('127.0.0.1',0));url='http://127.0.0.1:'+str(sock.getsockname()[1])
    server=uvicorn.Server(uvicorn.Config(app,log_level='critical',lifespan='off'))
    thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True)
    script = r'''const {chromium}=require('playwright'),assert=require('node:assert/strict');
    (async()=>{const b=await chromium.launch({channel:'msedge',headless:true});try{
      const p=await b.newPage();const errors=[];p.on('pageerror',e=>errors.push(e.message));await p.goto(process.env.SC_ENCODING_URL);
      const open=async()=>{await p.getByRole('button',{name:'Auto Editions menu: Bulk Review and Sort by'}).click();await p.getByRole('button',{name:'Bulk Review',exact:true}).click();};
      await open();const f=p.frameLocator('iframe[title="Bulk artwork review"]');
      await f.getByRole('alert').waitFor();assert(!(await f.locator('body').innerText()).includes('codec'));
      // An untrusted sibling cannot dismiss the modal.
      await p.evaluate(()=>postMessage({type:'sports-cave-bulk-dismiss'},location.origin));assert.equal(await p.locator('dialog.sc-edition-bulk').count(),1);
      await f.getByRole('button',{name:'Close',exact:true}).click();await p.locator('dialog.sc-edition-bulk').waitFor({state:'detached'});
      await open();await f.locator('#grid figure').waitFor();await f.getByText('Existing review fixture',{exact:true}).waitFor();await f.locator('#grid input:not(:disabled)').waitFor();
      await p.getByRole('button',{name:'Close Bulk Review',exact:true}).click();
      // Intercept only the next document to return the real server-generated failure body;
      // Retry must return to the actual healthy endpoint without changing review state.
      await p.route('**/auto-editions/bulk',async route=>{await route.fulfill({status:503,contentType:'text/html',body:process.env.SC_ENCODING_FAILURE});await p.unroute('**/auto-editions/bulk');});
      await open();await f.getByRole('button',{name:'Retry',exact:true}).click();await f.getByText('Existing review fixture',{exact:true}).waitFor();
      assert.equal(await f.locator('#all').count(),0);assert.equal(errors.length,0);console.log('Actual HTML endpoint, encoding fallback, Retry, Close, source guard and existing review item passed.');
    }finally{await b.close();}})().catch(e=>{console.error(e);process.exitCode=1});'''
    with patch.object(bulk,'Path',return_value=tmp_path/'auto_editions_bulk.py'),patch.object(bulk,'actor',new=AsyncMock(return_value=ADMIN)),patch.object(bulk,'approve_one') as approve:
        failure = asyncio.run(bulk.page(request())).body.decode('utf-8')
        thread.start()
        try:
            deadline=time.monotonic()+10
            while not server.started:
                assert time.monotonic()<deadline
                time.sleep(.01)
            env={**os.environ,'NODE_PATH':r'C:\Users\hello\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules','SC_ENCODING_URL':url,'SC_ENCODING_FAILURE':failure}
            result=subprocess.run(['node','-e',script],env=env,capture_output=True,text=True,encoding='utf-8',timeout=90)
            assert result.returncode==0,result.stdout+result.stderr
            print(result.stdout)
            assert state['pages']==3 and state['lists']==2 and state['writes']==0
            approve.assert_not_called()
        finally:
            server.should_exit=True;thread.join(timeout=10);sock.close()
