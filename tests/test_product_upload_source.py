from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock
import pytest

from product_upload_source import current_source, invalidate, prompt_section
from tests.test_product_upload_package import saved_row
from tests.test_product_upload_intake import database, env, ADMIN


def test_exact_numbered_folder_id_dynamic_count_and_existing_order():
    row = saved_row()
    output = row['data']['upload_operation']['output']
    saved = row['data']['mockup_saves']['saved']
    # Additional approved role: no eight-file assumption in the source contract.
    extra = deepcopy(output['files'][0])
    extra['relative_path'] = 'WEBP/extra.webp'
    extra['metadata'].update(id='id:extra', name='extra.webp',
                             path_display=output['folder'] + '/WEBP/extra.webp')
    output['files'].append(extra)
    saved['manifest'].append(dict(name=extra['relative_path']))
    output['manifest'].append(dict(slot_id='extra', output_filename='extra.webp', sort_position=9,
                                   display_label='Extra approved image', variant_mapping={'Frame': 'Black'}))
    output['manifest'].reverse()
    source = current_source(row)
    assert source['expected_webp_count'] == 9
    assert source['folder_path'].endswith('product (2)/WEBP')
    assert source['folder_id'] == 'id:webp-folder'
    assert source['folder_id'] != output['folder_id']
    assert [x['order'] for x in source['files']] == list(range(1, 10))
    assert source['files'][-1]['variant_mapping'] == {'Frame': 'Black'}
    assert 'id:extra' in prompt_section(source)
    del saved['receipt']['webp_folder']
    for entry in output['files']: entry['metadata'].pop('id')
    source = current_source(row)
    assert 'folder_id' not in source and all('file_id' not in x for x in source['files'])
    assert source['folder_path'].endswith('product (2)/WEBP')


@pytest.mark.parametrize('change', ['new-product', 'source-revision', 'images', 'partial', 'cancelled',
                                    'wrong-folder', 'missing', 'duplicate', 'not-complete', 'no-path'])
def test_stale_incomplete_or_ambiguous_sources_cannot_copy(change):
    row = saved_row()
    old = current_source(row)['version']
    output = row['data']['upload_operation']['output']
    saved = row['data']['mockup_saves']['saved']
    if change == 'new-product': row['id'] = '00000000-0000-0000-0000-000000000001'
    elif change == 'source-revision': row['data']['source']['rev'] = 'new'
    elif change == 'images': invalidate(row)
    elif change == 'partial': saved['receipt']['failures'] = ['failed']
    elif change == 'cancelled': saved['receipt']['cancelled'] = True
    elif change == 'wrong-folder': output['files'][0]['metadata']['path_display'] = '/other/black-frame.webp'
    elif change == 'missing': output['files'].pop()
    elif change == 'duplicate': output['files'].append(output['files'][0])
    elif change == 'not-complete': saved['state'] = 'Saving'
    elif change == 'no-path': output['files'][0]['metadata'].pop('path_display')
    with pytest.raises(ValueError): current_source(row, old)


@pytest.mark.parametrize('mode', ['DRAFT', 'LIVE', 'UPDATE'])
def test_complete_prompt_keeps_saved_template_and_mode_rules(mode):
    from product_upload_prompts import build
    from product_upload_prompt_core import product_upload_price_ladder_prompt_text
    row = saved_row()
    load = Mock(side_effect=lambda key, default, **kw: default + '\nDEVELOPER CUSTOM COMMERCIAL COPY')
    text = build(mode, 'Selected.psd', source=current_source(row), load=load)
    assert 'DEVELOPER CUSTOM COMMERCIAL COPY' in text
    assert product_upload_price_ladder_prompt_text() in text
    assert 'DROPBOX SOURCE — EXACT SAVED WEBP MANIFEST' in text
    assert 'product (2)/WEBP' in text and '"expected_webp_count": 8' in text
    assert 'do not need to be attached separately' in text
    assert 'before creating or changing the Shopify product' in text
    assert 'Do not claim an upload succeeded without verification' in text
    assert 'SOURCE CONTEXT — ATTACHED' not in text and 'MISSING - open/select' not in text
    assert '[ENTER PRODUCT NAME ABOVE]' not in text
    assert 'variant' in text.lower() and 'collection' in text.lower()
    assert load.call_args.kwargs['seed_default'] is False
    if mode == 'UPDATE': assert 'Never create a product in Update Existing mode' in text
    elif mode == 'DRAFT': assert 'Status: Draft' in text
    else: assert 'Online Store' in text and 'Active' in text


def test_successful_transfer_captures_webp_folder_metadata(env, tmp_path):
    from tests.test_product_upload_outputs import make_result
    from tests.fixtures.product_upload_outputs_provider import Outputs
    from product_upload_export import transfer
    row, result, manifest = make_result(env, tmp_path)
    api = Outputs()
    api.create_folder('fixture', api.base + '/Baseball', 'Product')
    receipt = transfer(SimpleNamespace(api=api, token='fixture'), result, manifest, api.root,
                       api.base + '/Baseball', 'Product', env[0].connect, ADMIN['id'], lambda *a: None)
    current = env[0].read(row['id'], ADMIN['id'])
    source = current_source(current)
    assert source['folder_path'] == receipt['destination'] + '/WEBP'
    assert source['folder_path'].endswith('/Product (2)/WEBP')
    assert source['folder_id'] == api.files[source['folder_path']]['id']
    assert source['expected_webp_count'] == sum(x['archive_name'].endswith('.webp') for x in manifest)
    assert source == current['data']['upload_operation']['output']['webp_source']


def test_delayed_save_cannot_replace_newer_successful_save(env, tmp_path):
    from tests.test_product_upload_outputs import make_result
    from tests.fixtures.product_upload_outputs_provider import Outputs
    from product_upload_export import transfer
    row, first, manifest = make_result(env, tmp_path)
    second = deepcopy(first)
    api = Outputs()
    provider = SimpleNamespace(api=api, token='fixture')
    def run(result, name, progress):
        return transfer(provider, result, manifest, api.root, api.base + '/Baseball', name,
                        env[0].connect, ADMIN['id'], progress)
    started = False
    def overlap(*args):
        nonlocal started
        if not started:
            started = True
            run(second, 'New product images', lambda *a: None)
    with pytest.raises(ValueError, match='newer image set'):
        run(first, 'Old images', overlap)
    current = env[0].read(row['id'], ADMIN['id'])
    assert current_source(current)['folder_path'].endswith('/New product images/WEBP')


def test_image_change_during_save_cannot_reenable_prompt(env, tmp_path):
    from tests.test_product_upload_outputs import make_result
    from tests.fixtures.product_upload_outputs_provider import Outputs
    from product_upload_export import transfer
    row, result, manifest = make_result(env, tmp_path)
    api = Outputs()
    changed = False
    def edit(*args):
        nonlocal changed
        if not changed:
            changed = True
            with env[0].locked(row['id'], ADMIN['id']) as (current, cur): invalidate(current)
    with pytest.raises(ValueError, match='newer image set'):
        transfer(SimpleNamespace(api=api, token='fixture'), result, manifest, api.root,
                 api.base + '/Baseball', 'Product', env[0].connect, ADMIN['id'], edit)
    with pytest.raises(ValueError): current_source(env[0].read(row['id'], ADMIN['id']))


@pytest.mark.parametrize('change', ['missing-version', 'stale-version', 'changed-during-build', 'mode-during-build'])
def test_copy_api_rechecks_source_after_template_load(monkeypatch, change):
    from contextlib import contextmanager
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient
    import product_upload_api as api, product_upload_prompts
    row = saved_row()
    row['data'].update(basic_validated=True, name='Selected.psd')
    version = current_source(row)['version']
    class Store:
        def __init__(self, *_): pass
        def read(self, *_): return row
        @contextmanager
        def locked(self, *_): yield row, None
    async def actor(*a, **kw): return {'id': 'fixture'}
    def build(*args, **kwargs):
        if change == 'changed-during-build': invalidate(row)
        if change == 'mode-during-build': row['mode'] = 'LIVE'
        return 'complete source prompt'
    monkeypatch.setattr(api, 'actor', actor)
    monkeypatch.setattr(api, 'Intakes', Store)
    monkeypatch.setattr(product_upload_prompts, 'build', build)
    provider = Mock(side_effect=AssertionError('Prompt copy must not call Dropbox'))
    monkeypatch.setattr(api, 'Dropbox', provider)
    body = dict(id=row['id'], mode='DRAFT', source_version=version)
    if change == 'missing-version': body.pop('source_version')
    if change == 'stale-version': body['source_version'] = 'older'
    app = Starlette(routes=[Route(p, e, methods=list(m)) for p, e, m in api.ROUTES])
    with TestClient(app) as client: response = client.post('/api/product-uploads/prompt', json=body)
    assert response.status_code == 409 and 'prompt' not in response.json()
    assert any(word in response.json()['error'] for word in ('changed', 'Save All first'))
    provider.assert_not_called()
