"""Preparation failures, retries and exact original bytes; all writes isolated."""
import ast
from contextlib import contextmanager
import json
import logging
import os
from pathlib import Path
import shutil
from time import perf_counter
from types import SimpleNamespace
from unittest.mock import Mock
import uuid
import pytest
import requests
from PIL import Image
from tests.test_product_upload_server_artwork import database, env, ADMIN, source_fixture
from tests.test_product_upload_dropbox import provider_fixture
import product_upload_artwork as artwork


def test_download_failure_is_actionable_logged_and_retry_clears_state(env, tmp_path, monkeypatch, caplog):
    store, sql, provider = env
    row, meta, original = source_fixture(env, tmp_path, monkeypatch)
    key = str(row['id'])
    provider.download.side_effect = requests.ConnectionError('Bearer secret-value https://private/?token=secret-value')
    with caplog.at_level(logging.ERROR), pytest.raises(artwork.PreparationError) as caught:
        artwork.prepare(store.connect, provider, key, ADMIN['id'])
    failed = store.read(key, ADMIN['id'])
    assert failed['data']['state'] == 'Error'
    assert failed['data']['server_artwork']['stage'] == 'retrieve original PSD'
    assert 'download was interrupted' in str(caught.value)
    from product_upload_api import failure
    response = failure(caught.value)
    body = json.loads(response.body)
    assert response.status_code == 503 and body['error'] == body['upload']['reason']
    assert body['upload']['id'] == key
    assert 'secret-value' not in caplog.text + response.body.decode()
    assert 'ConnectionError' in caplog.text and 'provider.download' in caplog.text
    assert failed['data']['server_artwork']['reference'] in caplog.text
    def restarted(metadata, destination):
        current = store.read(key, ADMIN['id'])
        assert current['data']['state'] == 'Preparing' and not current['data']['reason']
        shutil.copyfile(original, destination)
    provider.download.side_effect = restarted
    ready = artwork.prepare(store.connect, provider, key, ADMIN['id'])
    assert ready['data']['state'] == 'Ready' and not ready['data']['reason']
    artwork.prepare(store.connect, provider, key, ADMIN['id'])
    assert provider.download.call_count == 2  # failure + retry; subsequent call reuses verified cache


def test_dropbox_connection_failure_is_recorded_before_download(env,tmp_path,monkeypatch):
    store,sql,provider=env;row,meta,original=source_fixture(env,tmp_path,monkeypatch)
    monkeypatch.setattr('product_upload_services.Dropbox',Mock(side_effect=RuntimeError('private token=credential')))
    with pytest.raises(artwork.PreparationError,match='Dropbox connection could not be opened') as caught:
        artwork.prepare(store.connect,None,str(row['id']),ADMIN['id'])
    assert 'credential' not in str(caught.value)
    assert store.read(str(row['id']),ADMIN['id'])['data']['server_artwork']['stage']=='connect to Dropbox'
    provider.download.assert_not_called()


def test_repeated_prepare_while_active_returns_same_work_without_second_download(env, tmp_path, monkeypatch):
    store, sql, provider = env
    row, meta, original = source_fixture(env, tmp_path, monkeypatch)
    key = str(row['id'])
    observed = []
    def download(metadata, destination):
        duplicate = artwork.prepare(store.connect, provider, key, ADMIN['id'])
        observed.append(duplicate['data']['server_artwork']['state'])
        shutil.copyfile(original, destination)
    provider.download.side_effect = download
    assert artwork.prepare(store.connect, provider, key, ADMIN['id'])['data']['state'] == 'Ready'
    assert observed == ['Preparing'] and provider.download.call_count == 1


def test_late_failed_attempt_does_not_overwrite_new_source_or_attempt(env, tmp_path, monkeypatch):
    store, sql, provider = env
    row, meta, original = source_fixture(env, tmp_path, monkeypatch)
    key = str(row['id'])
    from product_upload_intake import Intakes
    original_locked=Intakes.locked
    calls=0
    @contextmanager
    def locked(self, identity, actor, **kwargs):
        nonlocal calls
        calls+=1
        if calls==2:  # after the failed transaction unwinds, before failure checkpoint
            with original_locked(self, identity, actor) as (current, cur):
                current['data']['source']={**meta,'id':'id:newer'}
                current['data']['server_artwork']=dict(state='Ready',attempt='newer')
                current['data'].update(state='Ready',reason='')
        with original_locked(self, identity, actor, **kwargs) as value:yield value
    monkeypatch.setattr(Intakes,'locked',locked)
    provider.download.side_effect=RuntimeError('Late failure from previous selection')
    with pytest.raises(artwork.PreparationError):artwork.prepare(store.connect, provider, key, ADMIN['id'])
    latest=store.read(key, ADMIN['id'])
    assert latest['data']['source']['id']=='id:newer'
    assert latest['data']['server_artwork']==dict(state='Ready',attempt='newer')
    assert not latest['data']['reason']


@pytest.mark.parametrize('payload', [b'<html>not original PSD</html>', b'8BPSincomplete', b'JPEG thumbnail'])
def test_incomplete_html_or_thumbnail_never_reaches_decoder(env, tmp_path, monkeypatch, payload):
    store, sql, provider = env
    row, meta, original = source_fixture(env, tmp_path, monkeypatch)
    provider.download.side_effect = lambda metadata, destination: Path(destination).write_bytes(payload)
    decoder = Mock(side_effect=AssertionError('Unverified bytes must not decode'))
    monkeypatch.setattr(artwork, 'decode', decoder)
    with pytest.raises(artwork.PreparationError, match='bytes do not match'):
        artwork.prepare(store.connect, provider, str(row['id']), ADMIN['id'])
    decoder.assert_not_called()


def test_sdk_adapter_pins_id_revision_and_streams_complete_response(tmp_path, monkeypatch):
    import dropbox
    import dropbox_integration as integration
    from product_upload_services import Dropbox
    client = dropbox.Dropbox(oauth2_access_token='isolated-token')
    chunks = [b'8BPS', b'full original document bytes']
    response = Mock(iter_content=Mock(return_value=iter(chunks)))
    client.request = Mock(return_value=(object(), response))
    monkeypatch.setattr(integration, 'team_space_client', lambda token: client)
    provider = object.__new__(Dropbox); provider.api = integration; provider.token = 'isolated-token'
    provider.download(dict(id='id:exact', rev='0165e251a26bf2f000000036d367e13'), tmp_path/'original.psd')
    arg = client.request.call_args.args[2]
    assert arg.path == 'id:exact' and arg.rev == '0165e251a26bf2f000000036d367e13'
    assert (tmp_path/'original.psd').read_bytes() == b''.join(chunks)
    response.iter_content.assert_called_once_with(65536)
    response.close.assert_called_once()


@pytest.mark.parametrize('state', ['Selected', 'Preparing', 'Failed'])
def test_generate_is_disabled_until_artwork_ready(env, tmp_path, monkeypatch, state):
    import product_upload_api as api
    import image_factory
    store, sql, provider = env
    row, meta, original = source_fixture(env, tmp_path, monkeypatch); key = str(row['id'])
    with store.locked(key, ADMIN['id']) as (current, cur):current['data']['server_artwork'] = dict(state=state, reason='Verified failure')
    monkeypatch.setattr(api, 'connect', store.connect); monkeypatch.setattr(api, 'Dropbox', lambda: provider)
    seen = []
    def button(label, **kwargs):
        if label == 'Generate Core Shopify Images':seen.append(kwargs['disabled']); return True  # defend even against stale click events
        return False
    st = SimpleNamespace(session_state={'_product_upload_active': key}, subheader=Mock(), text_input=lambda *a, **k:k.get('value', ''),
        selectbox=lambda *a, **k:'Football', button=button, info=Mock(), error=Mock())
    app = SimpleNamespace(_mockups_result=lambda: None, alphabetize_options=lambda values, **k:values,
        SPORT_OPTIONS=['Football'], get_sport_category=lambda a,b:a)
    generate = Mock(side_effect=AssertionError('Not ready'))
    monkeypatch.setattr(image_factory, 'generate_product_images', generate)
    tree = ast.parse((Path(__file__).parents[1]/'product_upload_mockups_ui.py').read_text(encoding='utf-8'))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'render_design')
    scope = dict(st=st, Path=Path, poll_render=Mock())
    exec(compile(ast.Module(body=[fn], type_ignores=[]), 'isolated-render', 'exec'), scope)
    scope['render_design'](app, row, ADMIN)
    assert seen == [True]
    generate.assert_not_called()


def test_readonly_affected_psd_selection_preparation_and_shared_core_engine(env, tmp_path, monkeypatch):
    """Opt in with an already retrieved original; no production credentials or writes."""
    location = os.getenv('PRODUCT_UPLOAD_READONLY_PSD')
    if not location:pytest.skip('Set PRODUCT_UPLOAD_READONLY_PSD to the verified read-only affected PSD')
    from auto_editions import file_hash
    from product_upload_dropbox import select
    import image_factory
    store, sql, provider = env; add = provider_fixture(provider)
    original = Path(location)
    expected = 'c5c9b3192d5cb6a5c42a70ef465f02cae5fcc1d8a2a14fd7fa4b964ec74da72e'
    assert original.stat().st_size == 285917118 and file_hash(original, dropbox=True) == expected
    meta = add('id:u1tYiAa2O-AAAAAAAABw6w', 'the-eleventh-pitch-jake-bauers.psd', '0165e251a26bf2f000000036d367e13')
    meta.update(content_hash=expected, size=original.stat().st_size)
    provider.files[meta['id']] = meta; provider.files[meta['path_display']] = meta
    provider.download = Mock(side_effect=lambda metadata, destination:shutil.copyfile(original, destination))
    monkeypatch.setattr('product_upload_render.Renders.claim', Mock(side_effect=AssertionError('Companion disconnected')))
    monkeypatch.setenv('SPORTS_CAVE_TEMP_DIR', str(tmp_path/'server'))
    monkeypatch.setattr(image_factory.prompt_store, 'get_prompt', lambda key, default='', **kwargs:default)
    monkeypatch.setattr(image_factory.prompt_store, 'get_cached_prompt', lambda key, default='', **kwargs:default)
    started = perf_counter()
    row = select(store.connect, provider, str(uuid.uuid4()), ADMIN['id'], 'DRAFT', meta['id'], meta['rev'])
    row = artwork.prepare(store.connect, provider, str(row['id']), ADMIN['id'])
    prepared = artwork.ready(row, store.connect, provider)
    preparation_ms = round((perf_counter()-started)*1000, 2)
    with Image.open(prepared/'artwork.png') as image:
        assert image.size == (2000, 1414) and image.info['icc_profile']
    started = perf_counter()
    result = image_factory.generate_product_images('The Eleventh Pitch Jake Bauers', 'Baseball', prepared/'artwork.png',
        base_dir=Path(__file__).parents[1], output_root=tmp_path/'generated')
    assert len(result['assets']) >= 5
    assert file_hash(original, dropbox=True) == expected
    metrics = dict(revision=meta['rev'], content_hash=expected, preparation_ms=preparation_ms,
        generation_ms=round((perf_counter()-started)*1000, 2), assets=len(result['assets']),
        boundaries='Exact affected PSD, production Pillow 10.4, actual repository scene templates/shared Mockups engine; disposable SQL and provider metadata, byte copy from verified server-side retrieval. No Companion, original writes or production DB.')
    output = Path(__file__).parents[1]/'output/product-upload-preparation-fix'
    output.mkdir(parents=True, exist_ok=True)
    (output/'real-psd-timings.json').write_text(json.dumps(metrics, indent=2), encoding='utf-8')
