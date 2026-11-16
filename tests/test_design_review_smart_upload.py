"""Check the Smart Upload decision boundary without touching cloud services."""
import json
from unittest.mock import Mock

import pytest

from design_review_metadata import parse_handoff, read_handoff, review_key
from product_upload_dropbox import REVIEW
from product_upload_intake import action_mode, stored_mode
from product_upload_prompts import build
from psd_directory import REVIEW_METADATA_FOLDER


SOURCE = dict(id='id:Art', rev='abcdef123', path_display=REVIEW + '/Adelaide.psd')
TARGET = 'gid://shopify/Product/123'


def handoff(**fields):
    value = dict(dropbox_file_id=SOURCE['id'], dropbox_revision=SOURCE['rev'],
                 dropbox_path=SOURCE['path_display'], design_title='The Adelaide Century',
                 design_story='A collector edition for the winning century.', sport='Cricket',
                 intended_collections=['cricket-wall-art'], review_status='ready_for_review',
                 upload_intent='new_product', existing_shopify_product_id=None)
    return json.dumps(dict(value, **fields)).encode()


def prompt(selected, details=None):
    return build(selected, 'Adelaide.psd', metadata=details, load=lambda _, default, **kw: default)


def test_new_and_refresh_keep_the_existing_mode_rules():
    new = parse_handoff(handoff(), SOURCE)
    refresh = parse_handoff(handoff(upload_intent='existing_product_refresh',
                                   existing_shopify_product_id='123'), SOURCE)
    assert stored_mode('SMART', new) == 'LIVE'
    assert stored_mode('SMART', refresh) == 'UPDATE'
    assert action_mode(dict(mode='UPDATE', data={'smart_upload': True})) == 'SMART'
    create = prompt('SMART', new)
    update = prompt('SMART', refresh)
    assert create.endswith(prompt('LIVE', new))
    assert update.endswith(prompt('UPDATE', refresh))
    assert 'cricket-wall-art' in create
    assert TARGET in update
    assert 'Set available quantity exactly 20' in create
    assert 'Set available quantity exactly 20' not in update
    assert 'Similarity alone never authorises replacement.' in update


def test_stale_metadata_and_ambiguous_refresh_are_rejected():
    with pytest.raises(ValueError, match='different Dropbox PSD revision'):
        parse_handoff(handoff(dropbox_revision='other'), SOURCE)
    with pytest.raises(ValueError, match='exact existing Shopify product ID'):
        parse_handoff(handoff(upload_intent='existing_product_refresh'), SOURCE)
    assert review_key(SOURCE) != review_key(dict(SOURCE, rev='updated'))


def test_review_checklist_does_not_block_the_smart_prompt():
    details = parse_handoff(handoff(review_status='needs_attention', review_notes='Unverified print bleed'), SOURCE)
    built = prompt('SMART', details)
    assert built.endswith(prompt('LIVE', details))
    assert 'Unverified print bleed' not in built


def test_unverified_refresh_target_does_not_supply_create_instructions():
    built = prompt('SMART', {'refresh_target_pending': True})
    assert 'pause Shopify and PSD mapping' in built
    assert 'Create the Shopify product' not in built


def test_handoff_download_is_identity_checked_and_closed():
    raw = handoff()
    provider = Mock()
    stored = dict(id='id:Sidecar', rev='current', size=len(raw), **{'.tag': 'file'})
    provider.metadata_if_present.return_value = stored
    response = Mock()
    response.iter_content.return_value = iter([raw])
    provider.api.get_file_response.return_value = (stored, response)
    assert read_handoff(provider, SOURCE)['sport'] == 'Cricket'
    provider.metadata_if_present.assert_called_once_with(REVIEW_METADATA_FOLDER + '/Adelaide.upload.json')
    response.close.assert_called_once()
    provider.api.get_file_response.return_value = (dict(stored, rev='changed'), response)
    with pytest.raises(ValueError, match='metadata changed'):
        read_handoff(provider, SOURCE)


@pytest.mark.parametrize('canonical', ('missing', 'different revision', 'different path', 'different ID', 'valid'))
def test_handoff_prefers_matching_json_and_falls_back_to_matching_legacy(canonical):
    from io import BytesIO

    provider = Mock()
    legacy_raw = handoff(design_title='Legacy title')
    fields = {
        'different revision': {'dropbox_revision': 'old', 'upload_intent': 'existing_product_refresh',
                               'existing_shopify_product_id': '123'},
        'different path': {'dropbox_path': REVIEW + '/Different.psd'},
        'different ID': {'dropbox_file_id': 'id:Different'},
    }
    canonical_raw = handoff(design_title='Canonical title', **fields.get(canonical, {}))
    files = {}
    for id_, path, raw in (('legacy', REVIEW, legacy_raw), ('canonical', REVIEW_METADATA_FOLDER, canonical_raw)):
        if id_ == 'canonical' and canonical == 'missing':
            continue
        files[path + '/Adelaide.upload.json'] = (dict(id=id_, rev='rev', size=len(raw), **{'.tag': 'file'}), raw)

    provider.metadata_if_present.side_effect = lambda path: files.get(path, (None, None))[0]

    def download(_, id_):
        entry, raw = next((entry, raw) for entry, raw in files.values() if entry['id'] == id_)
        return entry, Mock(iter_content=lambda **_: BytesIO(raw), close=Mock())

    provider.api.get_file_response.side_effect = download
    title = read_handoff(provider, SOURCE)['design_name']
    assert title == ('Canonical title' if canonical == 'valid' else 'Legacy title')
    if canonical != 'valid':
        del files[REVIEW + '/Adelaide.upload.json']
        if canonical == 'missing':
            assert read_handoff(provider, SOURCE) is None
        elif canonical == 'different revision':
            with pytest.raises(ValueError, match='different Dropbox PSD revision'):
                read_handoff(provider, SOURCE)
            details = read_handoff(provider, SOURCE, allow_stale_sport=True)
            assert details['sport'] == 'Cricket'
            assert details['review_status'] == 'needs_attention'
            assert details['design_name'] == 'Adelaide'
            assert details['refresh_target_pending']
            assert 'upload_intent' not in details and 'shopify_product_id' not in details
        else:
            with pytest.raises(ValueError, match='different Dropbox PSD revision'):
                read_handoff(provider, SOURCE, allow_stale_sport=True)

def test_review_gallery_approval_uses_the_exact_psd_and_seeds_the_intake(monkeypatch):
    from contextlib import contextmanager

    import design_review_page as gallery
    import product_upload_api as api
    import product_upload_jobs as jobs

    entry = dict(SOURCE, name='Adelaide.psd', **{'.tag': 'file'})
    details = parse_handoff(handoff(), entry)
    key = review_key(entry)
    row = dict(id=key, mode='LIVE', data=dict(source=entry, smart_upload=True, metadata=details))
    provider = Mock()
    provider.metadata_if_present.return_value = entry
    actor = 'reviewer'

    @contextmanager
    def locked(upload_id, owner):
        assert (upload_id, owner) == (key, actor)
        yield row, None

    store = Mock(read_review=Mock(return_value=None), locked=locked)
    monkeypatch.setattr(gallery, 'Intakes', lambda _: store)
    monkeypatch.setattr(gallery, 'read_handoff', lambda _, source, **kwargs: details)
    create = Mock(return_value=row)
    monkeypatch.setattr(gallery, 'select', create)
    monkeypatch.setattr(jobs.JOBS, 'snapshot', lambda *args: None)
    assert not gallery.final_psd(dict(entry, name='Adelaide - TRIAL.psd',
                                     path_display=REVIEW + '/Adelaide - TRIAL.psd'))
    assert gallery._review(provider, {'id': actor}, entry, 'approved') == key
    create.assert_called_once_with(api.connect, provider, key, actor, 'SMART', entry['id'], entry['rev'],
                                   reviewed=(entry, details))
    assert row['data']['design_review']['decision'] == 'approved'
    provider.metadata_if_present.return_value = dict(entry, rev='changed')
    with pytest.raises(ValueError, match='PSD changed'):
        gallery._review(provider, {'id': actor}, entry, 'approved')

from tests.test_product_upload_intake import database, env  # noqa: E402,F401


def test_smart_selection_retains_canonical_sport_collections_and_refresh_target(env):
    import uuid
    from io import BytesIO
    from product_upload_dropbox import select
    from tests.test_product_upload_dropbox import provider_fixture
    from tests.test_product_upload_intake import ADMIN

    store, _, provider = env
    source = provider_fixture(provider)(SOURCE['id'], 'Adelaide.psd', SOURCE['rev'])
    raw = handoff(upload_intent='existing_product_refresh', existing_shopify_product_id=TARGET)
    path = REVIEW_METADATA_FOLDER + '/Adelaide.upload.json'
    metadata = dict(id='id:Sidecar', rev='json-revision', size=len(raw), path_display=path, **{'.tag': 'file'})
    provider.files[path] = metadata
    provider.api.get_file_response.return_value = metadata, Mock(iter_content=lambda **_: BytesIO(raw))

    row = select(store.connect, provider, str(uuid.uuid4()), ADMIN['id'], 'SMART', source['id'], source['rev'])

    assert row['mode'] == 'UPDATE'
    details = row['data']['metadata']
    assert (details['sport'], details['intended_collections'], details['shopify_product_id']) == (
        'Cricket', ['cricket-wall-art'], TARGET,
    )


def test_smart_revision_has_one_durable_intake_across_selection_and_mode_switch(env):
    import uuid
    from product_upload_dropbox import select
    from product_upload_intake import public
    from tests.test_product_upload_dropbox import provider_fixture
    from tests.test_product_upload_intake import ADMIN

    store, _, provider = env
    source = provider_fixture(provider)(name='Cricket Adelaide.psd')
    original = select(store.connect, provider, str(uuid.uuid4()), ADMIN['id'], 'LIVE', source['id'], source['rev'])
    smart = store.change_mode(str(original['id']), ADMIN['id'], 'SMART', metadata={'sport': 'Cricket'})
    assert smart['mode'] == 'LIVE' and public(smart)['mode'] == 'SMART'
    chosen = select(store.connect, provider, str(uuid.uuid4()), ADMIN['id'], 'SMART', source['id'], source['rev'])
    assert chosen['id'] == original['id']
    assert store.read_review(review_key(source), ADMIN['id'], source)['id'] == original['id']
    with pytest.raises(ValueError, match='another reviewer'):
        select(store.connect, provider, str(uuid.uuid4()), 'different-reviewer', 'SMART', source['id'], source['rev'])
