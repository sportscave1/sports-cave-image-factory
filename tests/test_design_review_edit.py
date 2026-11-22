"""Synthetic Design Studio Edit tests. No Dropbox or Shopify access."""
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from auto_editions import file_hash
from design_collector_assets import COLLECTOR_ASSET_HEADING, COLLECTOR_ASSET_PLACEMENT
from design_review_metadata import is_working_file
from design_review_replace import apply, keep_original
from design_subject_authenticity import EDIT_AUTHENTICITY_CHECK, AUTHENTICITY_CHECK, AUTHENTICITY_HEADING, CREATE_DESIGN_AUTHENTICITY_CHECK
from home_morning_brief_actions import _prompt
from product_upload_dropbox import REVIEW
from psd_directory import REVIEW_METADATA_FOLDER


ORIGINAL_PATH = REVIEW + '/Collector.psd'
ORIGINAL_REV = 'abcdef123'
PREFIX = REVIEW + '/Collector - EDIT-' + ORIGINAL_REV


def test_edit_prioritises_request_and_reuses_shared_creative_stages():
    standard = _prompt('Collector', 'Verified story')
    edit = _prompt('Collector', 'Verified story', edit={
        'source': {'id': 'id:Original', 'rev': ORIGINAL_REV, 'path_display': ORIGINAL_PATH},
        'metadata': {'upload_intent': 'new_product'},
    })
    assert 'USER-REQUESTED DESIGN CHANGES from the Edit text box are the main creative priority' in edit
    assert edit.split('**1.', 1)[1].split('**5.', 1)[0] == standard.split('**1.', 1)[1].split('**5.', 1)[0]
    assert 'one creative image-generation call' in edit
    assert 'Generate two separate full artwork revisions' not in edit
    assert 'three-design scorecard' not in edit or 'without a second generation or three-design scorecard' in edit
    assert 'Target an even border inset of 2%' not in edit
    assert PREFIX + ' - STAGING.psd' in edit
    assert PREFIX + ' - TRIAL.psd' not in edit
    assert ORIGINAL_PATH in edit and 'id:Original' in edit
    assert CREATE_DESIGN_AUTHENTICITY_CHECK in edit
    assert edit.count(AUTHENTICITY_HEADING) == 1
    assert 'hidden ORIGINAL REVIEW SOURCE' in edit
    assert 'Never delete the original first to clear a path' in edit
    assert edit.index('staged PSD and its matching JSON are saved, reopened and verified') < edit.index('Apply the verified staged contents by revision-aware update')
    assert edit.index('Bind the canonical') < edit.index('recoverably delete only this run')
    assert 'one current canonical PSD' in edit and REVIEW_METADATA_FOLDER in edit


def test_refresh_edit_preserves_exact_target_and_uses_the_same_closeout():
    edit = _prompt('Collector', 'Verified story', edit={
        'source': {'id': 'id:Original', 'rev': ORIGINAL_REV, 'path_display': ORIGINAL_PATH},
        'metadata': {'upload_intent': 'existing_product_refresh', 'shopify_product_id': 'gid://shopify/Product/123'},
    })
    assert 'upload_intent (existing_product_refresh)' in edit
    assert 'existing_shopify_product_id ("gid://shopify/Product/123")' in edit
    assert 'upload_intent (new_product)' not in edit
    assert '**Complete the selected Review edit and clean up Dropbox**' in edit
    assert 'Live PSDs, Shopify products and live mappings untouched' in edit
    assert 'Read back the PSD and JSON together' in edit


def test_targeted_edit_overrides_new_design_defaults_before_shared_stages():
    from design_review_prompt import EDIT_EXECUTION_RULES
    source = dict(id='id:Original', rev=ORIGINAL_REV, path_display=ORIGINAL_PATH,
                  size=264 * 1024**2, content_hash='verified-hash')
    prompt = _prompt('Collector', 'Remove the score only; keep everything else the same.',
                     edit=dict(source=source, metadata=dict(upload_intent='new_product')))
    assert prompt.count(EDIT_EXECUTION_RULES) == 1
    assert prompt.index(EDIT_EXECUTION_RULES) < prompt.index('**1.')
    assert '**Start the authorised new-design job**' not in prompt
    assert 'Zero creative generations are required for a local correction' in prompt
    assert 'Skip unrelated bestseller research, image searches' in prompt
    assert 'chunked Dropbox upload sessions' in prompt
    assert 'never flatten, downsample, remove required layers' in prompt
    assert 'report INCOMPLETE with the exact failing operation' in prompt
    assert '"size": 276824064' in prompt and '"content_hash": "verified-hash"' in prompt


def test_edit_inherits_future_shared_creative_updates(monkeypatch):
    import home_morning_brief_actions as actions
    monkeypatch.setattr(actions, 'CREATIVE_REVIEW', 'FUTURE SHARED EDIT CREATIVE RULE')
    edit = _prompt('Collector', 'Verified story', edit={
        'source': {'id': 'id:Original', 'rev': ORIGINAL_REV, 'path_display': ORIGINAL_PATH}, 'metadata': {}})
    assert edit.count('FUTURE SHARED EDIT CREATIVE RULE') == 1
    assert 'upload_intent (new_product)' not in edit
    assert 'never default this edit to new_product' in edit


@pytest.fixture
def files(tmp_path, monkeypatch):
    def metadata(path, id_, rev, content):
        local = tmp_path / id_.removeprefix('id:')
        local.write_bytes(content)
        return dict(id=id_, rev=rev, path_display=path, name=path.rsplit('/', 1)[-1],
                    content_hash=file_hash(local, dropbox=True), size=len(content), **{'.tag': 'file'})

    original = metadata(ORIGINAL_PATH, 'id:Original', ORIGINAL_REV, b'original'*12)
    trial = metadata(PREFIX+' - TRIAL.psd', 'id:Trial', '111111111', b'trial'*12)
    staging = metadata(PREFIX+' - STAGING.psd', 'id:Staging', '222222222', b'staged'*12)
    current = {item['id']: item for item in (original, trial, staging)}
    current.update({item['path_display']: item for item in (original, trial, staging)})
    uploads = []

    def download(item, path):
        path.write_bytes((tmp_path / item['id'].removeprefix('id:')).read_bytes())

    def upload(token, path, file, revision):
        old = current[path]
        if old['rev'] != revision:
            raise ValueError('conflict')
        uploads.append(revision)
        result = metadata(path, old['id'], ('333333333', '444444444')[len(uploads)-1], file.read_bytes())
        current[path] = current[old['id']] = result
        return result

    @contextmanager
    def verified(token, id_, rev):
        yield current[id_]

    def backup(token, path, target, **kwargs):
        result = dict(current[path], id='id:Backup', rev='555555555', path_display=target)
        current[target] = result
        return result

    def delete(token, path, *, root_path, expected_revision):
        item = current[path]
        assert item['rev'] == expected_revision
        del current[path]
        current.pop(item['id'], None)

    api = SimpleNamespace(copy_path=Mock(side_effect=backup), upload_revision=Mock(side_effect=upload),
                          get_verified_psd_stream=verified, delete_path_recoverable=Mock(side_effect=delete))
    provider = SimpleNamespace(metadata_if_present=lambda key: current.get(key),
                               download=download, token='synthetic', context={'root_path': REVIEW}, api=api)
    validate = Mock()
    monkeypatch.setattr('design_review_replace._inspect', validate)
    return provider, original, trial, staging, current, validate


def test_keep_original_removes_only_explicit_drafts_and_is_retryable(files):
    provider, original, trial, staging, current, _ = files
    other = dict(trial, id='id:Other', rev='other', path_display=PREFIX+' - TRIAL - another-run.psd')
    current[other['id']] = current[other['path_display']] = other
    paths = (trial['path_display'], staging['path_display'])
    assert keep_original(provider, original, paths) == []
    assert keep_original(provider, original, paths) == []
    assert current[original['id']] == original and current[other['id']] == other
    assert provider.api.delete_path_recoverable.call_count == 2
    provider.api.upload_revision.assert_not_called()
    provider.api.copy_path.assert_not_called()


def test_keep_original_leaves_drafts_when_canonical_verification_fails(files):
    provider, original, trial, _, _, _ = files
    provider.api.get_verified_psd_stream = Mock(side_effect=ValueError('could not reopen'))
    with pytest.raises(ValueError, match='could not reopen'):
        keep_original(provider, original, [trial['path_display']])
    provider.api.delete_path_recoverable.assert_not_called()


def test_keep_original_rejects_another_revision_before_deleting_any_draft(files):
    provider, original, trial, _, _, _ = files
    stale = trial['path_display'].replace(ORIGINAL_REV, 'earlier')
    with pytest.raises(ValueError, match='this exact edit revision'):
        keep_original(provider, original, [trial['path_display'], stale])
    provider.api.delete_path_recoverable.assert_not_called()


def test_keep_original_checks_recorded_draft_receipts(files):
    provider, original, trial, staging, _, _ = files
    receipts = [trial['path_display'], f"{staging['path_display']} | {staging['id']} | old"]
    with pytest.raises(ValueError, match='differs from its recorded Dropbox identity or revision'):
        keep_original(provider, original, receipts)
    provider.api.delete_path_recoverable.assert_not_called()


def test_replace_preserves_id_and_path_and_cleans_only_exact_temporary_revisions(files):
    provider, original, trial, staging, current, validate = files
    final, backup, warnings = apply(provider, original, trial['path_display'], staging['path_display'])
    assert (final['id'], final['path_display']) == (original['id'], original['path_display'])
    assert final['rev'] != original['rev']
    assert final['content_hash'] == staging['content_hash']
    assert backup['content_hash'] == original['content_hash']
    assert is_working_file(backup['path_display'])
    assert not warnings
    validate.assert_called_once()
    deletes = provider.api.delete_path_recoverable.call_args_list
    assert [(x.args[1], x.kwargs['expected_revision']) for x in deletes] == [
        (trial['path_display'], trial['rev']), (staging['path_display'], staging['rev']),
        (backup['path_display'], backup['rev']),
    ]


def test_cleanup_retains_a_draft_replaced_during_canonical_verification(files):
    provider, original, trial, staging, current, _ = files
    verified = provider.api.get_verified_psd_stream

    @contextmanager
    def verify_and_change_trial(*args):
        with verified(*args) as receipt:
            current[trial['path_display']] = dict(trial, id='id:Different', rev='999999999')
            yield receipt

    provider.api.get_verified_psd_stream = verify_and_change_trial
    _, backup, warnings = apply(provider, original, trial['path_display'], staging['path_display'])
    assert len(warnings) == 1 and trial['name'] in warnings[0]
    assert [x.args[1] for x in provider.api.delete_path_recoverable.call_args_list] == [
        staging['path_display'], backup['path_display'],
    ]


def test_revision_conflict_prevents_all_writes(files):
    provider, original, trial, staging, current, _ = files
    current[original['id']] = dict(original, rev='999999999')
    with pytest.raises(ValueError, match='original revision changed'):
        apply(provider, original, trial['path_display'], staging['path_display'])
    provider.api.copy_path.assert_not_called()
    provider.api.upload_revision.assert_not_called()
    provider.api.delete_path_recoverable.assert_not_called()


def test_failed_post_save_verification_restores_original_and_retains_staging(files):
    provider, original, trial, staging, current, _ = files
    provider.api.get_verified_psd_stream = Mock(side_effect=ValueError('reopen failed'))
    with pytest.raises(ValueError, match='original was restored'):
        apply(provider, original, trial['path_display'], staging['path_display'])
    assert current[ORIGINAL_PATH]['content_hash'] == original['content_hash']
    provider.api.delete_path_recoverable.assert_not_called()


def test_failed_layer_inspection_preserves_original_and_staging(files):
    provider, original, trial, staging, current, validate = files
    validate.side_effect = ValueError('Number must be editable')
    with pytest.raises(ValueError, match='editable'):
        apply(provider, original, trial['path_display'], staging['path_display'])
    provider.api.upload_revision.assert_not_called()
    provider.api.delete_path_recoverable.assert_not_called()

def test_layer_verification_requires_original_number_id_and_alignment(monkeypatch):
    from design_review_replace import _inspect
    from psd_tools import PSDImage

    def layer(name, *, kind='pixel', ident=10, bbox=(0, 0, 100, 100), visible=True):
        return SimpleNamespace(name=name, kind=kind, layer_id=ident, text='001 / 100',
                               left=bbox[0], top=bbox[1], right=bbox[2], bottom=bbox[3],
                               is_visible=lambda: visible)

    badge = layer('SC_EDITION_PLAQUE')
    text = layer('SC_EDITION_NUMBER', kind='type', ident=11, bbox=(20, 20, 60, 40))
    staged = [
        badge, text, layer('ORIGINAL REVIEW SOURCE', visible=False),
        layer('ORIGINAL EDITABLE ARTWORK', visible=False), layer('FINAL POLISHED ARTWORK'),
    ]
    monkeypatch.setattr('design_review_replace.validate_structure', lambda _: None)
    monkeypatch.setattr('auto_editions_colour_source.inspect_psd',
                        lambda _: dict(width=100, height=100, icc=b'synthetic', mode=3, depth=8))
    class Document(list):
        def descendants(self):
            return iter(self)

    monkeypatch.setattr(PSDImage, 'open', lambda p: Document(staged if p == 'staging' else [badge, text]))
    _inspect('original', 'trial', 'staging')
    staged[0] = layer('SC_EDITION_PLAQUE', bbox=(31, 15, 91, 75))
    staged[1] = layer('SC_EDITION_NUMBER', kind='type', ident=11, bbox=(43, 27, 67, 39))
    _inspect('original', 'trial', 'staging')
    staged[1] = layer('SC_EDITION_NUMBER', kind='type', ident=99, bbox=(20, 20, 60, 40))
    with pytest.raises(ValueError, match='preserve the original'):
        _inspect('original', 'trial', 'staging')
    staged[1] = layer('SC_EDITION_NUMBER', kind='type', ident=11, bbox=(110, 20, 160, 40))
    with pytest.raises(ValueError, match='aligned'):
        _inspect('original', 'trial', 'staging')


@pytest.mark.parametrize('refresh', [False, True])
def test_edit_uses_shared_authenticity_and_retains_review_limitations(refresh):
    metadata = {'upload_intent': 'existing_product_refresh', 'shopify_product_id': '123'} if refresh else {}
    prompt = _prompt('Collector', 'Verified story', edit={
        'source': {'id': 'id:Original', 'rev': ORIGINAL_REV, 'path_display': ORIGINAL_PATH}, 'metadata': metadata})
    assert CREATE_DESIGN_AUTHENTICITY_CHECK in prompt
    assert 'Keep inherited source limitations accurately marked needs_attention' in prompt
    assert 'never invent detail or claim missing verification passed' in prompt
    assert 'continue independent work without a new approval pause' in prompt
    assert 'Apply staged replacement' in prompt


def test_replace_carries_missing_source_notes_and_cleans_verified_drafts(files, monkeypatch):
    import json
    provider, original, trial, staged, current, _ = files
    data = {'review_status': 'ready_for_review', 'review_notes': 'Existing note',
            'dropbox_file_id': original['id'], 'dropbox_revision': original['rev'],
            'dropbox_path': original['path_display'], 'sport': 'Hockey'}
    sidecar = {'id': 'id:JSON', 'rev': 'json1', 'path_display': '/Review/JSON/Collector.upload.json'}
    monkeypatch.setattr('design_review_replace.read_handoff_record', lambda *args: (dict(data), dict(sidecar)))
    upload_psd = provider.api.upload_revision.side_effect
    def upload(token, path, file, revision):
        if path == sidecar['path_display']:
            assert revision == sidecar['rev']
            data.update(json.loads(file.read_text(encoding='utf8')))
            sidecar['rev'] = 'json2'
            return dict(sidecar)
        return upload_psd(token, path, file, revision)
    provider.api.upload_revision.side_effect = upload
    final, _, warnings = apply(provider, original, trial['path_display'], staged['path_display'],
                               review_notes='Original photograph unavailable; existing facial features preserved against pre-edit PSD.')
    assert not warnings
    assert data['review_status'] == 'needs_attention'
    assert data['review_notes'].startswith('Existing note\nOriginal photograph unavailable')
    assert data['dropbox_revision'] == final['rev']
    assert data['sport'] == 'Hockey'
    assert provider.api.delete_path_recoverable.call_count == 3
    assert current[original['id']]['content_hash'] == staged['content_hash']


def test_unresolved_notes_require_matching_json_before_replacement(files, monkeypatch):
    provider, original, trial, staged, _, _ = files
    monkeypatch.setattr('design_review_replace.read_handoff_record', lambda *args: None)
    with pytest.raises(ValueError, match='matching upload JSON'):
        apply(provider, original, trial['path_display'], staged['path_display'], review_notes='Source unavailable')
    provider.api.upload_revision.assert_not_called()
    provider.api.copy_path.assert_not_called()
    provider.api.delete_path_recoverable.assert_not_called()


def test_single_generation_replacement_needs_no_trial_and_cleans_only_its_files(files):
    provider, original, trial, staged, current, validate = files
    final, backup, warnings = apply(provider, original, '', staged['path_display'])
    assert not warnings
    assert final['id'] == original['id'] and final['content_hash'] == staged['content_hash']
    assert current[trial['id']] == trial  # An unrelated legacy trial is not this run's output.
    assert [(x.args[1], x.kwargs['expected_revision']) for x in provider.api.delete_path_recoverable.call_args_list] == [
        (staged['path_display'], staged['rev']), (backup['path_display'], backup['rev'])]
    validate.assert_called_once()


def test_large_review_metadata_uses_existing_revision_upload_and_downloads_staging_once(files):
    provider, original, _, staged, current, validate = files
    # Exercise the size guard with the failed run's sizes; the fixture keeps
    # content tiny so this regression test does not allocate hundreds of MiB.
    original['size'] = 250 * 1024**2
    staged['size'] = 264 * 1024**2
    upload = provider.api.upload_revision.side_effect
    def large_receipt(*args):
        result = upload(*args)
        result['size'] = staged['size']
        return result
    provider.api.upload_revision.side_effect = large_receipt
    download = Mock(wraps=provider.download)
    provider.download = download
    final, _, warnings = apply(provider, original, '', staged['path_display'])
    assert not warnings
    assert final['content_hash'] == staged['content_hash']
    assert download.call_count == 2
    assert [call.args[0]['id'] for call in download.call_args_list] == [original['id'], staged['id']]
    assert provider.api.upload_revision.call_args.args[3] == ORIGINAL_REV
    validate.assert_called_once()


@pytest.mark.parametrize('size', [None, True, 39, 1024**3 + 1])
def test_invalid_or_oversized_review_psds_never_start_writes(files, size):
    provider, original, _, staged, _, _ = files
    staged['size'] = size
    with pytest.raises(ValueError, match='up to 1 GiB per file'):
        apply(provider, original, '', staged['path_display'])
    provider.api.copy_path.assert_not_called()
    provider.api.upload_revision.assert_not_called()
    provider.api.delete_path_recoverable.assert_not_called()


@pytest.mark.parametrize('changed_target', [False, True])
def test_single_result_handoff_preserves_product_binding_and_cleans_staging_json(files, monkeypatch, changed_target):
    import json
    provider, original, trial, staged, current, _ = files
    old = dict(design_title='Old Title', design_story='Original story', sport='Basketball',
               upload_intent='existing_product_refresh', existing_shopify_product_id='123',
               design_origin='designs_to_refresh', morning_design_job_id='original-job',
               dropbox_file_id=original['id'], dropbox_revision=original['rev'], dropbox_path=original['path_display'])
    revised = dict(old, design_title='New Title \u2013 Kobe Bryant Wall Art', design_story='Revised story',
                   review_status='needs_attention', review_notes='Source detail remains limited',
                   dropbox_file_id=staged['id'], dropbox_revision=staged['rev'], dropbox_path=staged['path_display'])
    if changed_target:
        revised['existing_shopify_product_id'] = '999'
    sidecar = dict(id='id:JSON', rev='json1', path_display=REVIEW_METADATA_FOLDER+'/Collector.upload.json')
    staging_json = dict(id='id:StagedJSON', rev='stage-json1',
                        path_display=REVIEW_METADATA_FOLDER+'/'+staged['name'][:-4]+'.upload.json')
    current[staging_json['id']] = current[staging_json['path_display']] = staging_json
    monkeypatch.setattr('design_review_replace.read_handoff_record', lambda _, source:
        (dict(revised), dict(staging_json)) if source['id'] == staged['id'] else (dict(old), dict(sidecar)))
    upload = provider.api.upload_revision.side_effect
    def write(token, path, file, revision):
        if path == sidecar['path_display']:
            assert revision == sidecar['rev']
            old.update(json.loads(file.read_text(encoding='utf-8')))
            sidecar['rev'] = 'json2'
            return sidecar
        return upload(token, path, file, revision)
    provider.api.upload_revision.side_effect = write
    monkeypatch.setattr('design_review_title.sync_review_title', lambda _, source, **kwargs: (source, ''))
    if changed_target:
        with pytest.raises(ValueError, match='exact Shopify target'):
            apply(provider, original, '', staged['path_display'])
        provider.api.upload_revision.assert_not_called()
        provider.api.delete_path_recoverable.assert_not_called()
        return
    final, _, warnings = apply(provider, original, '', staged['path_display'])
    assert not warnings
    assert old['design_title'] == revised['design_title'] and old['design_story'] == 'Revised story'
    assert old['existing_shopify_product_id'] == '123' and old['morning_design_job_id'] == 'original-job'
    assert old['design_origin'] == 'designs_to_refresh' and old['review_status'] == 'needs_attention'
    assert old['dropbox_revision'] == final['rev']
    assert staging_json['id'] not in current and staged['id'] not in current
    assert current[trial['id']] == trial
