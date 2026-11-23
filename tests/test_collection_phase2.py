"""Synthetic private preview checks: no store, database or customer connections."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import io
import os
import threading
from unittest.mock import Mock, MagicMock, patch

from PIL import Image
import pytest
import requests
from starlette.requests import Request

import collector_preview_cache as cache
import collector_vault as vault
import collector_vault_api as api
from collector_collection_offers import render_certificate_frame, FRAME_BOX


ASSET = dict(owner_hash='fixture-owner', certificate_row_id=1, kind='preview',
             storage='r2', bucket='fixture', key='issued.webp', asset_version='v1')


def test_byte_cache_budget_lru_expiry_and_oversize():
    clock = [0]
    c = cache.ByteCache(max_bytes=6, max_entries=2, ttl=5, now=lambda: clock[0])
    c.get_or_load('a', lambda: b'aaa')
    c.get_or_load('b', lambda: b'bb')
    assert c.get_or_load('a', lambda: b'wrong') == b'aaa'
    c.get_or_load('c', lambda: b'ccc')
    assert c.stats() == dict(bytes=6, entries=2, pending=0)
    assert c.get_or_load('b', lambda: b'x') == b'x'  # LRU b was evicted.
    c.get_or_load('large', lambda: b'1234567')
    assert c.stats()['bytes'] <= 6
    clock[0] = 5
    assert c.stats() == dict(bytes=0, entries=0, pending=0)


def test_singleflight_queue_limit_and_failed_load_recovery():
    c = cache.ByteCache(max_bytes=100, max_entries=5, max_pending=1)
    entered, release = threading.Event(), threading.Event()
    calls = []
    def load():
        calls.append(1)
        entered.set()
        assert release.wait(3)
        return b'one'
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(c.get_or_load, 'same', load)
        assert entered.wait(3)
        joined = threading.Event()
        future = c._pending['same']
        result = future.result
        def waiting_result(**kwargs):
            joined.set()
            return result(**kwargs)
        with patch.object(future, 'result', side_effect=waiting_result):
            second = pool.submit(c.get_or_load, 'same', load)
            try:
                assert joined.wait(3)
                with pytest.raises(cache.PreviewBusyError):
                    c.get_or_load('other', load)
            finally:
                release.set()
        assert first.result() == second.result() == b'one'
    assert calls == [1]
    def fail():
        raise ValueError('synthetic')
    with pytest.raises(ValueError):
        c.get_or_load('bad', fail)
    assert c.stats()['pending'] == 0
    assert c.get_or_load('bad', lambda: b'retry') == b'retry'
    with pytest.raises(TypeError):
        c.get_or_load('mutable', lambda: bytearray(b'no'))


def test_colours_share_source_and_warm_outputs_skip_fetch_render_and_signing():
    fetch, render, sign = Mock(return_value=b'issued'), Mock(side_effect=lambda b, c, w: f'{c}-{w}'.encode()), Mock(return_value='fixture-url')
    pipeline = cache.PreviewPipeline(fetch=fetch, render=render)
    with ThreadPoolExecutor(6) as pool:
        outputs = list(pool.map(lambda color: pipeline.framed(ASSET, color, 400, sign), ['black', 'oak', 'white'] * 2))
    assert outputs == [b'black-400', b'oak-400', b'white-400'] * 2
    assert fetch.call_count == sign.call_count == 1
    assert render.call_count == 3
    pipeline.framed(ASSET, 'black', 400, sign)
    assert fetch.call_count == 1 and render.call_count == 3


@pytest.mark.parametrize('change', [dict(owner_hash='other'), dict(certificate_row_id=2), dict(asset_version='v2'), dict(key='changed.webp')])
def test_source_cache_never_crosses_owner_certificate_or_revision(change):
    fetch = Mock(return_value=b'issued')
    pipeline = cache.PreviewPipeline(fetch=fetch, render=lambda *a: b'rendered')
    pipeline.framed(ASSET, 'black', 400, lambda: 'fixture')
    pipeline.framed(dict(ASSET, **change), 'black', 400, lambda: 'fixture')
    assert fetch.call_count == 2


def test_size_and_recipe_invalidate_output_without_refetching_original():
    fetch, render = Mock(return_value=b'issued'), Mock(return_value=b'framed')
    pipeline = cache.PreviewPipeline(fetch=fetch, render=render)
    pipeline.framed(ASSET, 'black', 400, lambda: 'fixture')
    pipeline.framed(ASSET, 'black', 1000, lambda: 'fixture')
    with patch.object(cache, 'RECIPE_VERSION', 'next'):
        pipeline.framed(ASSET, 'black', 400, lambda: 'fixture')
    assert render.call_count == 3 and fetch.call_count == 1
    with pytest.raises(ValueError):
        pipeline.framed(dict(ASSET, owner_hash=''), 'black', 400, lambda: 'fixture')


def test_corrupt_source_is_not_stuck_in_cache():
    fetch = Mock(side_effect=[b'corrupt', b'valid'])
    render = Mock(side_effect=[ValueError('decode'), b'framed'])
    pipeline = cache.PreviewPipeline(fetch=fetch, render=render)
    with pytest.raises(ValueError):
        pipeline.framed(ASSET, 'black', 400, lambda: 'fixture')
    assert pipeline.framed(ASSET, 'black', 400, lambda: 'fixture') == b'framed'
    assert fetch.call_count == 2


def test_upstream_limit_and_failures_close_response_and_hide_source_url():
    response = Mock()
    response.iter_content.return_value = [b'a' * (cache.MAX_SOURCE_BYTES + 1)]
    with patch.object(cache.requests, 'get', return_value=response), pytest.raises(ValueError):
        cache.PreviewPipeline._fetch('https://fixture.invalid/private?secret=hidden')
    response.close.assert_called_once()
    response.reset_mock()
    response.raise_for_status.side_effect = requests.HTTPError('secret=hidden')
    with patch.object(cache.requests, 'get', return_value=response), pytest.raises(cache.PreviewSourceError) as raised:
        cache.PreviewPipeline._fetch('https://fixture.invalid/private?secret=hidden')
    assert 'hidden' not in str(raised.value)
    response.close.assert_called_once()


@pytest.mark.parametrize('width', [400, 1000])
def test_real_render_sizes_preserve_issued_art_and_edges(width):
    stream = io.BytesIO()
    Image.new('RGB', (824, 583), 'red').save(stream, 'PNG')
    for color in ['black', 'oak', 'white']:
        with Image.open(io.BytesIO(render_certificate_frame(stream.getvalue(), color, output_width=width))) as image:
            assert image.size == (width, width)
            x, y, w, h = FRAME_BOX
            for px, py in [(x+20, y+20), (x+w-20, y+h-20)]:
                red, green, blue = image.getpixel((round(px * width / 1000), round(py * width / 1000)))
                assert red > 220 and green < 40 and blue < 40


def request(query=b'token=fixture&frame=black&w=400'):
    return Request(dict(type='http', method='GET', path='/api/collector-vault/asset', query_string=query, headers=[]))


def test_warm_request_still_checks_current_ownership_before_cache():
    pipeline = cache.PreviewPipeline(fetch=lambda _: b'issued', render=lambda *a: b'framed')
    with patch.object(vault, 'resolve_asset_token', side_effect=[ASSET, ASSET, vault.CollectorVaultAuthorizationError('not yours')]) as auth, \
         patch.object(cache, 'PREVIEWS', pipeline), \
         patch.object(api.r2_storage, 'generate_presigned_download_url', return_value='fixture') as sign:
        assert asyncio.run(api.collector_vault_asset(request())).status_code == 200
        assert asyncio.run(api.collector_vault_asset(request())).status_code == 200
        assert asyncio.run(api.collector_vault_asset(request())).status_code == 403
    assert auth.call_count == 3 and sign.call_count == 1


def test_real_signed_asset_resolution_uses_database_owner_and_version():
    from tests.test_collector_vault import _certificate_row, CUSTOMER_A, CUSTOMER_B
    conn = MagicMock()
    cursor = conn.__enter__.return_value.cursor.return_value.__enter__.return_value
    row = dict(_certificate_row(), updated_at='fixture-version')
    cursor.fetchone.side_effect = [row, _certificate_row(CUSTOMER_B)]
    with patch.dict(os.environ, {'COLLECTOR_VAULT_ASSET_SIGNING_SECRET': 'synthetic-only'}), \
         patch.object(vault, '_require_database'), patch.object(vault.supabase_backend, 'connect', return_value=conn):
        token = vault._signed_token(dict(purpose='asset', certificate_row_id=12, kind='preview', customer_hash=vault.customer_hash(CUSTOMER_A)), ttl_seconds=300)
        asset = vault.resolve_asset_token(token)
        assert asset['owner_hash'] == vault.customer_hash(CUSTOMER_A)
        assert asset['asset_version'] == 'fixture-version'
        assert asset['certificate_row_id'] == 12
        with pytest.raises(vault.CollectorVaultAuthorizationError):
            vault.resolve_asset_token(token)


def test_expired_signed_token_is_rejected_even_when_preview_cache_is_warm():
    pipeline = cache.PreviewPipeline(fetch=lambda _: b'issued', render=lambda *a: b'framed')
    pipeline.framed(ASSET, 'black', 400, lambda: 'fixture')
    with patch.dict(os.environ, {'COLLECTOR_VAULT_ASSET_SIGNING_SECRET': 'synthetic-only'}), \
         patch.object(cache, 'PREVIEWS', pipeline), patch.object(vault, '_require_database') as database, \
         patch.object(vault.supabase_backend, 'connect', side_effect=AssertionError('no database access')):
        with patch.object(vault.time, 'time', return_value=1000):
            token = vault._signed_token(dict(purpose='asset', certificate_row_id=1, kind='preview', customer_hash='fixture-owner'), ttl_seconds=60)
        with patch.object(vault.time, 'time', return_value=2000):
            assert asyncio.run(api.collector_vault_asset(request(f'token={token}&frame=black&w=400'.encode()))).status_code == 401
    database.assert_not_called()


def test_blocked_render_leaves_async_loop_responsive():
    entered, release = threading.Event(), threading.Event()
    def render(*args):
        entered.set()
        assert release.wait(3)
        return b'framed'
    pipeline = cache.PreviewPipeline(fetch=lambda _: b'issued', render=render)
    async def exercise():
        task = asyncio.create_task(api.collector_vault_asset(request()))
        try:
            for _ in range(100):
                if entered.is_set():
                    break
                await asyncio.sleep(.005)
            assert entered.is_set() and not task.done()
            # A second coroutine can run while Pillow is blocked in its worker.
            assert await asyncio.sleep(0, result='responsive') == 'responsive'
        finally:
            release.set()
        assert (await task).status_code == 200
    with patch.object(vault, 'resolve_asset_token', return_value=ASSET), patch.object(cache, 'PREVIEWS', pipeline), \
         patch.object(api.r2_storage, 'generate_presigned_download_url', return_value='fixture'):
        asyncio.run(exercise())


@pytest.mark.parametrize('query', [b'token=x&frame=black&w=999', b'token=x&w=400', b'token=x&frame=red'])
def test_bad_preview_options_fail_before_fetch(query):
    with patch.object(vault, 'resolve_asset_token', return_value=ASSET), patch.object(cache, 'PREVIEWS') as previews:
        assert asyncio.run(api.collector_vault_asset(request(query))).status_code == 400
    previews.framed.assert_not_called()
