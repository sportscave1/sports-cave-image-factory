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
from tests.test_product_upload_intake import database, env  # noqa: F401


def source(id_, name, revision='exact', root=REVIEW):
    return {'.tag': 'file', 'id': f'id:{id_}', 'rev': revision, 'name': name,
            'path_display': f'{root}/{name}'}


def test_folder_reaches_last_cursor_and_uses_listed_sidecars(monkeypatch):
    artwork = source('a', 'Final.psd')
    handoff = source('b', 'Final.upload.json')
    trial = source('c', 'Final - EDIT-exact - TRIAL.psd')

    def page(_, __, *, cursor, limit):
        index = int(cursor or '0')
        entries = [artwork] if index == 0 else [handoff, trial] if index == 11 else []
        return dict(entries=entries, has_more=index < 11, cursor=str(index + 1))

    monkeypatch.setattr(api, 'Dropbox', lambda: SimpleNamespace(
        api=SimpleNamespace(list_folder_page=page), token='fixture'))
    details = Mock(return_value=({'design_name': 'Sidecar title'}, ''))
    monkeypatch.setattr(gallery, '_details', details)

    designs, _ = gallery._folder.__wrapped__('fixture')

    assert designs == [(artwork, {'design_name': 'Sidecar title'}, '', True)]
    details.assert_called_once_with('fixture', artwork, handoff)


@pytest.mark.parametrize(('permissions', 'record', 'revision', 'expected'), [
    ({'Files', 'Product Uploads'}, source('a', 'Final.psd'), 'exact', 200),
    ({'Files'}, source('a', 'Final.psd'), 'exact', 403),
    ({'Product Uploads'}, source('a', 'Final.psd'), 'exact', 403),
    ({'Files', 'Product Uploads'}, source('a', 'Final.psd'), 'stale', 409),
    ({'Files', 'Product Uploads'}, source('a', 'Final - TRIAL.psd'), 'exact', 409),
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
    assert '"rev": "exact"' in prompt and '**8F. Replace the original and return it to review**' in prompt
    assert stale.status_code == 409


def test_missing_sport_is_saved_for_the_exact_revision_and_passed_to_mockups(env, monkeypatch):
    from tests.test_product_upload_dropbox import provider_fixture
    from tests.test_product_upload_intake import ADMIN
    import product_upload_export as export
    import product_upload_jobs as jobs

    store, _, provider = env
    record = provider_fixture(provider)(name='Unknown gallery fixture.psd')
    monkeypatch.setattr(api, 'connect', store.connect)
    monkeypatch.setattr(export, 'sport_categories', lambda *args: [{'sport': 'NFL'}])
    generate = Mock()
    monkeypatch.setattr(jobs, 'generate', generate)
    app = SimpleNamespace(_files_access_token=lambda: 'fake', _files_team_root=lambda _: '/fake',
                          dropbox_integration=object(), BASE_DIR='.', MOCKUPS_GENERATION_SEMAPHORE=object(),
                          build_mockup_final_prompt_items=Mock())

    with pytest.raises(ValueError, match='sport could not be resolved'):
        gallery._review(app, provider, ADMIN, record, 'approved')
    key = gallery._review(app, provider, ADMIN, record, 'approved', selected_sport='NFL')
    result = store.read(key, ADMIN['id'])['data']
    assert result['metadata']['sport'] == result['review_sport'] == 'NFL'
    assert result['metadata']['intended_collections'] == ['nfl-wall-art']
    assert result['source']['rev'] == record['rev']
    assert generate.call_args.args[4] == 'NFL'
