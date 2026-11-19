"""Offline coverage for gallery listing and revision-bound image delivery."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

import design_review_page as gallery
import files_upload_api
import product_upload_api as api
from product_upload_dropbox import REVIEW
from psd_directory import REVIEW_METADATA_FOLDER
from tests.test_product_upload_intake import database, env  # noqa: F401


def source(id_, name, revision='exact', root=REVIEW):
    return {'.tag': 'file', 'id': f'id:{id_}', 'rev': revision, 'name': name,
            'path_display': f'{root}/{name}'}


def test_folder_reaches_last_cursor_and_uses_listed_sidecars(monkeypatch):
    artwork = source('a', 'Final.psd')
    legacy = source('b', 'Final.upload.json')
    handoff = source('c', 'Final.upload.json', root=REVIEW_METADATA_FOLDER)
    trial = source('d', 'Final - EDIT-exact - TRIAL.psd')
    folder = {'.tag': 'folder', 'name': 'JSON', 'path_display': REVIEW_METADATA_FOLDER}

    def page(_, path, *, cursor, limit):
        if path == REVIEW_METADATA_FOLDER:
            return dict(entries=[handoff], has_more=False)
        index = int(cursor or '0')
        entries = [artwork] if index == 0 else [legacy, trial, folder] if index == 11 else []
        return dict(entries=entries, has_more=index < 11, cursor=str(index + 1))

    monkeypatch.setattr(api, 'Dropbox', lambda: SimpleNamespace(
        api=SimpleNamespace(list_folder_page=page), token='fixture'))
    details = Mock(return_value=({'design_name': 'Sidecar title'}, ''))
    monkeypatch.setattr(gallery, '_details', details)

    designs, _ = gallery._folder.__wrapped__('fixture')

    assert designs == [(artwork, {'design_name': 'Sidecar title'}, '', True)]
    details.assert_called_once_with('fixture', artwork, (handoff, legacy))


def test_folder_shows_refresh_staging_with_cleanup_pending(monkeypatch):
    staged = source('staged', 'Andrew Johns - REFRESH - STAGING - run.psd')
    sidecar = source('json', 'Andrew Johns - REFRESH - STAGING - run.upload.json', root=REVIEW_METADATA_FOLDER)
    trial = source('trial', 'Andrew Johns - TRIAL.psd')
    ordinary_staging = source('edit', 'Andrew Johns - EDIT-exact - STAGING.psd')
    folder = {'.tag': 'folder', 'path_display': REVIEW_METADATA_FOLDER}
    value = dict(upload_intent='existing_product_refresh', existing_shopify_product_id='123',
                 design_title='Andrew Johns', design_story='Career tribute', sport='Rugby League',
                 intended_collections=['rugby-league'], review_status='ready_for_review', cleanup_status='pending',
                 dropbox_file_id=staged['id'], dropbox_revision=staged['rev'], dropbox_path=staged['path_display'])
    raw = json.dumps(value).encode()
    sidecar['size'] = len(raw)
    provider = SimpleNamespace(token='fixture', api=SimpleNamespace(
        list_folder_page=lambda token, path, **_: dict(
            entries=[sidecar] if path == REVIEW_METADATA_FOLDER else [staged, trial, ordinary_staging, folder]),
        get_file_response=lambda *_: (sidecar, SimpleNamespace(iter_content=lambda **_: iter([raw]), close=lambda: None)),
    ))
    monkeypatch.setattr(api, 'Dropbox', lambda: provider)
    monkeypatch.setattr('product_upload_services.Dropbox', lambda: provider)

    [(artwork, details, reason, editing)], _ = gallery._folder.__wrapped__('staged-refresh-test')

    assert artwork == staged and not reason and not editing
    assert details['review_status'] == 'ready_for_review' and details['cleanup_status'] == 'pending'
    assert not gallery.final_psd(staged)


def test_delete_review_design_moves_only_exact_psd_and_matching_sidecar():
    from design_review_delete import delete_design

    psd = source('art', 'Final.psd')
    central = source('json', 'Final.upload.json', root=REVIEW_METADATA_FOLDER)
    legacy = source('legacy', 'Final.upload.json')
    data = dict(dropbox_file_id=psd['id'], dropbox_revision=psd['rev'], dropbox_path=psd['path_display'])
    contents = {central['id']: json.dumps(data).encode(),
                legacy['id']: json.dumps(dict(data, dropbox_revision='old')).encode()}
    central['size'], legacy['size'] = (len(contents[item['id']]) for item in (central, legacy))
    files = {item['path_display']: item for item in (psd, central, legacy)}
    by_id = {item['id']: item for item in files.values()}

    def read(_, id_):
        return by_id[id_], SimpleNamespace(iter_content=lambda **_: iter([contents[id_]]), close=Mock())

    def remove(_, path, *, root_path, expected_revision):
        assert root_path == REVIEW
        assert files[path]['rev'] == expected_revision
        return files.pop(path)

    def metadata(locator):
        return files.get(by_id.get(locator, {}).get('path_display', locator))

    provider = SimpleNamespace(token='fixture', metadata_if_present=metadata,
                               api=SimpleNamespace(get_file_response=read, delete_path_recoverable=Mock(side_effect=remove)))
    provider.api.delete_path_recoverable.side_effect = OSError('Dropbox unavailable')
    with pytest.raises(OSError):
        delete_design(provider, psd)
    assert len(files) == 3
    provider.api.delete_path_recoverable.reset_mock(side_effect=True)
    provider.api.delete_path_recoverable.side_effect = remove
    warnings = delete_design(provider, psd)
    assert list(files) == [legacy['path_display']]
    assert len(warnings) == 1 and legacy['path_display'] in warnings[0]
    assert [call.args[1] for call in provider.api.delete_path_recoverable.call_args_list] == [
        psd['path_display'], central['path_display']]


@pytest.mark.parametrize('record', [source('a', 'Live.psd', root=REVIEW.rsplit('/', 1)[0]),
                                    source('a', 'Artwork - STAGING.psd'),
                                    source('a', 'Changed.psd', revision='stale')])
def test_delete_review_design_rejects_out_of_scope_or_stale_items(record):
    from design_review_delete import delete_design

    remove = Mock()
    provider = SimpleNamespace(token='fixture', metadata_if_present=lambda _: dict(record, rev='current'),
                               api=SimpleNamespace(delete_path_recoverable=remove))
    with pytest.raises(ValueError):
        delete_design(provider, record)
    remove.assert_not_called()


@pytest.mark.parametrize(('permissions', 'record', 'revision', 'expected'), [
    ({'Files', 'Product Uploads'}, source('a', 'Final.psd'), 'exact', 200),
    ({'Files'}, source('a', 'Final.psd'), 'exact', 403),
    ({'Product Uploads'}, source('a', 'Final.psd'), 'exact', 403),
    ({'Files', 'Product Uploads'}, source('a', 'Final.psd'), 'stale', 409),
    ({'Files', 'Product Uploads'}, source('a', 'Final - TRIAL.psd'), 'exact', 409),
    ({'Files', 'Product Uploads'}, source('a', 'Final - EDIT-exact - STAGING.psd'), 'exact', 409),
    ({'Files', 'Product Uploads'}, source('a', 'Final - REFRESH - STAGING - run.psd'), 'exact', 200),
    ({'Files', 'Product Uploads'}, source('a', 'Final.psd', root='/elsewhere'), 'exact', 409),
])
def test_thumbnail_checks_access_and_exact_review_revision(monkeypatch, permissions, record, revision, expected):
    authentication = Mock(return_value={'id': 'fixture'})
    monkeypatch.setattr(files_upload_api, '_request_user', authentication)
    monkeypatch.setattr(files_upload_api.os_accounts, 'can_access_page', lambda _, page: page in permissions)
    monkeypatch.setattr(files_upload_api.os_accounts, 'can_attach_missing_psd', lambda _: True)
    monkeypatch.setattr(api, 'enabled', lambda: True)
    thumbnail = Mock(return_value=b'synthetic-jpeg')
    monkeypatch.setattr(api, 'Dropbox', lambda: SimpleNamespace(
        api=SimpleNamespace(get_psd_thumbnail_bytes=thumbnail), token='fixture',
        metadata_if_present=lambda _: record))
    app = Starlette(routes=[Route(path, handler, methods=list(methods))
                            for path, handler, methods in api.ROUTES])

    with TestClient(app) as client:
        response = client.get('/api/design-review/thumbnail', params={'id': 'id:a', 'rev': revision})

    assert response.status_code == expected
    assert authentication.call_args.kwargs == {'required_page': 'Design Studio'}
    if expected == 200:
        assert response.content == b'synthetic-jpeg'
        assert response.headers['content-type'] == 'image/jpeg'
        assert response.headers['cache-control'].startswith('private,')
        thumbnail.assert_called_once_with('fixture', 'id:a', revision='exact')
    else:
        thumbnail.assert_not_called()


def test_batched_review_lookup_matches_exact_revisions_and_prefers_smart_upload(env):
    store, sql, _ = env
    first = source('a', 'First.psd')
    second = source('b', 'Second.psd')
    first_key, second_key = map(gallery.review_key, (first, second))
    chosen = str(uuid4())

    def insert(key, actor, data):
        sql.execute('INSERT INTO product_upload_intakes (id, actor_id, mode, data) VALUES (%s,%s,%s,%s::jsonb)',
                    (key, actor, 'LIVE', json.dumps(data)))

    insert(first_key, 'reviewer', {'source': first})
    insert(chosen, 'reviewer', {'smart_upload': True, 'source': first, 'mockups_exported': True})
    insert(str(uuid4()), 'reviewer', {'smart_upload': True, 'source': dict(second, rev='older')})
    insert(str(uuid4()), 'another reviewer', {'smart_upload': True, 'source': second})

    rows = store.read_review_gallery('reviewer', {first_key: first, second_key: second})

    assert list(rows) == [first_key]
    assert str(rows[first_key]['id']) == chosen
    assert rows[first_key]['data']['mockups_exported'] is True
    assert 'source' not in rows[first_key]['data']


def test_edit_endpoint_returns_full_prompt_for_exact_dropbox_source(monkeypatch):
    record = source('edit', 'Design & Story.psd')
    monkeypatch.setattr(api, '_gallery_review_user', AsyncMock())
    monkeypatch.setattr(api, 'Dropbox', lambda: SimpleNamespace(metadata_if_present=lambda key: record if key == record['id'] else None))
    app = Starlette(routes=[Route('/api/design-review/edit-prompt', api.review_edit_prompt)])
    with TestClient(app) as client:
        response = client.get('/api/design-review/edit-prompt', params={'id': record['id'], 'rev': record['rev']})
        stale = client.get('/api/design-review/edit-prompt', params={'id': record['id'], 'rev': 'stale'})
    assert response.status_code == 200
    prompt = response.json()['prompt']
    assert 'https://www.dropbox.com/home' in prompt and '?preview=Design%20%26%20Story.psd' in prompt
    assert record['path_display'] in prompt and record['id'] in prompt
    assert '"rev": "exact"' in prompt
    assert '**4. Return the winner to Review**' in prompt
    assert 'user-requested design changes as the primary brief' in prompt
    assert 'Search online for the exact photograph' in prompt
    assert stale.status_code == 409


def test_refresh_staging_cannot_start_an_edit_prompt(monkeypatch):
    staged = source('staged', 'Final - REFRESH - STAGING - run.psd')
    monkeypatch.setattr(api, '_gallery_review_user', AsyncMock())
    monkeypatch.setattr(api, 'Dropbox', lambda: SimpleNamespace(metadata_if_present=lambda _: staged))
    app = Starlette(routes=[Route('/api/design-review/edit-prompt', api.review_edit_prompt)])
    with TestClient(app) as client:
        response = client.get('/api/design-review/edit-prompt', params={'id': staged['id'], 'rev': staged['rev']})
    assert response.status_code == 409


def test_missing_sport_is_saved_for_the_exact_revision(env, monkeypatch):
    from tests.test_product_upload_dropbox import provider_fixture
    from tests.test_product_upload_intake import ADMIN

    store, _, provider = env
    record = provider_fixture(provider)(name='Unknown gallery fixture.psd')
    monkeypatch.setattr(api, 'connect', store.connect)
    with pytest.raises(ValueError, match='sport could not be resolved'):
        gallery._review(provider, ADMIN, record, 'approved')
    key = gallery._review(provider, ADMIN, record, 'approved', selected_sport='NFL')
    result = store.read(key, ADMIN['id'])['data']
    assert result['metadata']['sport'] == result['review_sport'] == 'NFL'
    assert result['metadata']['intended_collections'] == ['nfl-wall-art']
    assert result['source']['rev'] == record['rev']


def test_first_publish_click_prepares_exact_psd_and_automatically_generates_mockups(env, tmp_path, monkeypatch):
    from io import BytesIO
    from pathlib import Path
    from threading import Semaphore

    import streamlit as st
    from PIL import Image
    from streamlit.testing.v1 import AppTest
    import image_factory
    import product_upload_jobs as jobs
    from auto_editions import file_hash
    from product_upload_dropbox import within
    from tests.test_product_upload_dropbox import provider_fixture
    from tests.test_product_upload_intake import ADMIN
    from tests.test_product_upload_server_artwork import real_psd

    # Importing app in another test can leave its bare-mode login form on Streamlit's root.
    monkeypatch.setattr(st._main, '_form_data', None)
    store, _, provider = env
    record = provider_fixture(provider)(name='Gallery fixture.psd', rev='abc123')
    psd = real_psd(tmp_path / 'fixture.psd')
    record.update(content_hash=file_hash(psd, dropbox=True), size=psd.stat().st_size)
    provider.files[record['id']] = provider.files[record['path_display']] = record
    def download(metadata, destination, **kwargs):
        assert metadata == record
        if provider.download.call_count == 1:
            raise TimeoutError('The first original download timed out')
        Path(destination).write_bytes(psd.read_bytes())

    provider.download = Mock(side_effect=download)
    monkeypatch.setenv('SPORTS_CAVE_TEMP_DIR', str(tmp_path / 'server'))

    folder = {'.tag': 'folder', 'name': 'JSON', 'path_display': REVIEW_METADATA_FOLDER}
    path = REVIEW_METADATA_FOLDER + '/Gallery fixture.upload.json'
    value = dict(dropbox_file_id=record['id'], dropbox_path=record['path_display'], dropbox_revision=record['rev'],
                 sport='Cricket', design_title='Gallery fixture', intended_collections=['cricket'],
                 upload_intent='new_product', review_status='needs_attention', review_notes='Unverified print bleed')

    def install_json():
        raw = json.dumps(value).encode()
        sidecar = {'.tag': 'file', 'id': 'id:json', 'rev': value['dropbox_revision'], 'size': len(raw),
                   'name': 'Gallery fixture.upload.json', 'path_display': path}
        provider.files[path] = sidecar
        provider.api.get_file_response.return_value = (
            sidecar, Mock(iter_content=lambda **_: BytesIO(raw)))

    install_json()
    provider.api.list_folder_page.side_effect = lambda _, path, **kw: dict(
        entries=[provider.files[REVIEW_METADATA_FOLDER + '/Gallery fixture.upload.json']]
        if path == REVIEW_METADATA_FOLDER else [record, folder], has_more=False)
    monkeypatch.setattr(api, 'Dropbox', lambda: provider)
    monkeypatch.setattr('product_upload_services.Dropbox', lambda: provider)
    monkeypatch.setattr(api, 'connect', store.connect)
    provider.api.get_psd_thumbnail_bytes.side_effect = TimeoutError('Preview unavailable')
    scheduled = {}

    def schedule(key, actor, operation, fingerprint, work):
        assert not scheduled, 'The first click must enqueue just one combined job'
        scheduled.update(key=key, actor=actor, operation=operation, fingerprint=fingerprint, work=work)
        return dict(token='automatic-job', state='Queued', stage='Waiting to start', completed=0, total=None, previews=[])

    submit = Mock(side_effect=schedule)
    monkeypatch.setattr(jobs.JOBS, 'submit', submit)
    monkeypatch.setattr(jobs.JOBS, 'snapshot', lambda key, actor, operation: (
        dict(token='automatic-job', state='Queued', stage='Waiting to start', completed=0, total=None, previews=[])
        if (key, actor, operation) == tuple(scheduled.get(field) for field in ('key', 'actor', 'operation')) and scheduled else None))
    asset = tmp_path / 'mockup.webp'
    Image.new('RGB', (10, 10)).save(asset)

    def render(name, sport, ready_path, **kwargs):
        assert name == 'Gallery fixture' and sport == 'Cricket'
        with Image.open(ready_path) as image:
            assert image.size == (640, 480)
        return dict(product_name=name, sport_category=sport, run_dir=tmp_path,
                    assets=[dict(review_path=asset, preview_path=asset, webp_path=asset) for _ in range(5)])

    renderer = Mock(side_effect=render)
    monkeypatch.setattr(image_factory, 'generate_product_images', renderer)
    monkeypatch.setattr(image_factory, 'cleanup_stale_temp_runs', Mock())
    root = '/Fixture'
    category = {'.tag': 'folder', 'id': 'id:cricket', 'name': 'Cricket Wall Art',
                'path_display': root + '/04_OUTPUT/product-images/Cricket Wall Art'}
    folder_api = SimpleNamespace(normalize_dropbox_path=lambda path: path, path_is_within_root=within,
                                 list_folder_page=lambda *a, **kw: dict(entries=[category]),
                                 get_metadata_if_exists=lambda _, id_: category if id_ == category['id'] else None)
    component = Mock(return_value=None)
    app = SimpleNamespace(
        BASE_DIR=Path(gallery.__file__).parent, current_os_user=lambda: ADMIN,
        set_current_page=lambda page, **_: st.session_state.update(fixture_page=page),
        get_components_module=lambda: SimpleNamespace(declare_component=lambda *a, **kw: component),
        os_accounts=SimpleNamespace(can_access_page=lambda *a: True),
        _files_access_token=lambda: 'fixture', _files_team_root=lambda _: root, dropbox_integration=folder_api,
        _mockups_result=lambda: None, MOCKUPS_GENERATION_SEMAPHORE=Semaphore(1),
        build_mockup_final_prompt_items=lambda *args: [],
        ensure_lifestyle_prompts=lambda result: result, rebuild_result_artifacts=lambda result: result,
    )
    monkeypatch.setattr(gallery, '_test_fixture', (app, ADMIN), raising=False)
    ui = AppTest.from_string("""
import streamlit as st
import design_review_page as gallery
from product_upload_mockups_ui import render_page

app, user = gallery._test_fixture
if st.session_state.get('fixture_page') == 'Product Uploads':
    render_page(app)
else:
    gallery._gallery(app, user)
""", default_timeout=25).run()
    assert not ui.exception
    import product_upload_staff_queue as queue
    cursor = env[1]
    cursor.execute((Path(gallery.__file__).parent / 'migrations/20261117110000_product_upload_staff_queue.sql').read_text(encoding='utf-8'))
    cursor.execute((Path(gallery.__file__).parent / 'migrations/20261118070000_product_upload_manual_restart.sql').read_text(encoding='utf-8'))
    cursor.execute('CREATE TABLE IF NOT EXISTS app_settings(key text PRIMARY KEY,value jsonb,updated_at timestamptz DEFAULT now())')
    monkeypatch.setattr(queue, 'connect', store.connect)
    ui.button(key=gallery.review_key(record)+'-approved').click().run()
    assert not ui.exception and not ui.error, [error.value for error in (*ui.exception, *ui.error)]
    assert ui.session_state['_product_upload_notice']['kind'] == 'success'
    assert not scheduled, 'Publish queues work without rendering or navigating in the requester tab'
    token = queue.pair(ADMIN)
    queued = queue.tick(token, {})['job']
    assert queued['id'] == ui.session_state['_product_upload_notice']['id']
    ui.session_state['fixture_page'] = 'Product Uploads'
    ui.query_params['staff_upload_job'] = queued['id']
    ui.run()
    assert not ui.exception and not ui.error, [error.value for error in (*ui.exception, *ui.error)]
    assert ui.session_state['fixture_page'] == 'Product Uploads'
    assert next(box for box in ui.selectbox if box.label == 'Sport category').value == category['id']
    key = gallery.review_key(record)
    assert ui.session_state['_product_upload_active'] == key
    assert component.call_args.kwargs['id'] == key
    assert next(box for box in ui.text_input if box.label == 'Product name').value == 'Gallery fixture'
    assert not ui.warning
    assert not ui.button(key='product-upload-generate-'+key).value
    provider.api.get_psd_thumbnail_bytes.assert_not_called()
    provider.download.assert_not_called()
    ui.run()
    submit.assert_called_once()
    assert scheduled['operation'] == 'generate' and scheduled['fingerprint']['sport'] == 'Cricket'
    progress = Mock()
    result = scheduled['work'](progress)
    assert result['_product_upload_intake'] == key and len(result['assets']) == 5
    progress.assert_any_call('Retrying PSD preparation')
    assert provider.download.call_count == 2
    renderer.assert_called_once()
    saved = store.read(key, ADMIN['id'])
    assert saved['data']['source'] == record
    assert saved['data']['server_artwork']['state'] == 'Ready'
    assert saved['data']['metadata']['sport'] == 'Cricket'
    assert saved['data']['design_review']['decision'] == 'approved'
    assert saved['data']['metadata']['review_status'] == 'needs_attention'
    assert saved['mode'] == 'LIVE' and not saved['data']['metadata'].get('shopify_product_id')
    with pytest.raises(ValueError, match='completed image package'):
        store.copied(key, ADMIN['id'], 'SMART')
    with store.locked(key, ADMIN['id']) as (row, _):
        row['data']['mockups_exported'] = True
    assert store.copied(key, ADMIN['id'], 'SMART')['data']['copied']

    submit.assert_called_once()
