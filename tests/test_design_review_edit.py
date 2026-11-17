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


def test_edit_uses_canonical_prompt_with_exclusive_edit_checkpoints():
    standard = _prompt('Collector', 'Verified story')
    edit = _prompt('Collector', 'Verified story', edit={
        'source': {'id': 'id:Original', 'rev': ORIGINAL_REV, 'path_display': ORIGINAL_PATH},
        'metadata': {'shopify_product_id': 'gid://shopify/Product/123'},
    })
    assert edit.count('**MANDATORY EXECUTION ORDER**') == 1
    for start, end in ((COLLECTOR_ASSET_HEADING, '**8E.'),
                       ('**Recover from tool failures.**', 'Verified story')):
        assert edit[edit.index(start):edit.index(end)] == standard[standard.index(start):standard.index(end)]
    assert '12. **Final improvement.**' in edit and 'PASS, CHANGE or UNVERIFIED' in edit
    assert edit.index('Step 7.') < edit.index('Make a **new image-generation call**') < edit.index('Save a separate create-only file')
    assert 'ORIGINAL REVIEW SOURCE' in edit and 'expected revision' in edit
    assert 'gid://shopify/Product/123' in edit and ORIGINAL_PATH in edit
    assert '[Product Title] - TRIAL.psd' not in edit
    assert 'upload_intent (new_product)' not in edit
    assert 'Photoshop is optional' in edit
    assert 'capable PSD parser plus a rendered preview' in edit
    assert 'Photoshop live-number check pending' not in edit
    assert 'at most two additional image-generation attempts total across both passes' in edit
    assert 'skip it without prompting and use an authorised alternative' in edit
    assert 'Target an even border inset of 2%' in edit
    assert edit.index('Create a separate recoverable backup') < edit.index('Reopen the saved canonical PSD')
    assert edit.index('Reopen the saved canonical PSD') < edit.index('**Update the matching Smart Upload JSON**')
    assert REVIEW_METADATA_FOLDER in edit
    assert 'Preserve the design’s confirmed sport, upload intent, Shopify product ID and collection linkage' in edit
    assert edit.index('compare the rendered current design') < edit.index('Save a separate create-only file')
    assert 'Pass 1 and Pass 2 side by side at 100% and at thumbnail size' in edit
    assert 'collector appeal' in edit and 'Sports Cave style' in edit and 'mean of those three scores' in edit
    assert 'Reject any edit that looks less realistic than the current design' in edit
    assert 'Keep the current design if no edit scores higher' in edit
    assert 'If the current design wins, skip 8E and go directly to its cleanup in 8F' in edit
    assert 'exact trial, staging and rollback backup PSDs' in edit
    assert 'Display the winner and the three-design scorecard' in edit
    assert 'eyes and gaze, eyelids, eyebrows, nose, mouth and teeth' in edit
    assert 'background, border, headline wording and hierarchy, typography, layout' in edit
    assert '8. **Title and placement.**' in edit
    assert 'headline longevity and placement' in edit.replace('\n', ' ')
    assert 'design_title at the canonical PSD path' in edit
    assert edit.index('use the authorised Shopify connection in read-only mode') < edit.index('**STORY-LED COLLECTOR TITLES**')
    assert 'remove an existing signature only when requested' in edit
    assert 'Transform its mask and linked components together' not in edit
    assert edit.count('Inspect the rendered, assembled PSD') == 2
    assert 'or text, dates or statistics are removed, reassess the whole layout' in edit
    assert 'A new layout is optional' in standard and 'A new layout is optional' not in edit
    assert 'Preserve successful typography and layout during source-based restoration.' in edit
    assert 'before recoverably deleting that exact file by ID' in edit
    assert 'Keep original and finish edit' in edit and 'Keep original and finish edit' not in standard
    assert 'three-design scorecard' not in standard
    assert 'REVIEW REPLACEMENT RULE' not in edit
    assert 'Never delete the canonical PSD' in edit
    for prompt in (standard, edit):
        assert COLLECTOR_ASSET_PLACEMENT in prompt
        assert 'reserve quiet space along the bottom' not in prompt
        assert 'reserved bottom space' not in prompt
        assert prompt.count(AUTHENTICITY_HEADING) == 1
        assert 'MANDATORY SUBJECT AUTHENTICITY CHECK' not in prompt
    assert CREATE_DESIGN_AUTHENTICITY_CHECK in standard
    assert EDIT_AUTHENTICITY_CHECK in edit
    assert 'TARGETED AUTHENTICITY RESTORATION' not in edit


def test_refresh_closeout_verifies_staged_pair_before_product_cleanup():
    from home_design_refresh import _refresh_prompt

    refresh = _refresh_prompt(dict(title='Collector', product_id='123', suggestion='Refine', sessions=4),
                              'https://www.sportscaveshop.com/products/collector')
    edit = _prompt('Collector', 'Verified story', edit={
        'source': {'id': 'id:Original', 'rev': ORIGINAL_REV, 'path_display': ORIGINAL_PATH},
        'metadata': {'upload_intent': 'existing_product_refresh',
                     'shopify_product_id': 'gid://shopify/Product/123'},
    })
    assert 'Never delete the canonical PSD' not in edit
    assert 'Apply staged replacement' not in edit
    assert 'Target an even border inset of 2%' in edit
    for prompt in (refresh, edit):
        assert prompt.count('**REVIEW REPLACEMENT RULE**') == 1
        assert prompt.index('Read back both files') < prompt.index('Recoverably delete only')
        assert prompt.index('retain the previous refresh') < prompt.index('Recoverably delete only')
        assert prompt.index('Recoverably delete only') < prompt.index('Rename the staged PSD')
        assert prompt.index('Rename the staged PSD') < prompt.index('Update the moved JSON')
        assert 'exact Shopify product' in prompt and 'its Product GID as the same ID' in prompt
        assert (EDIT_AUTHENTICITY_CHECK if prompt is edit else AUTHENTICITY_CHECK) in prompt
        assert prompt.count(AUTHENTICITY_HEADING) == 1
        assert prompt.index('**IDENTITY OVERRIDES GENERATION CONTINUITY**') < prompt.index(AUTHENTICITY_HEADING)
        assert 'AI warping' in prompt and 'needs_attention' in prompt


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
def test_edit_review_replacement_allows_preserved_subject_with_inherited_limitations(refresh):
    metadata = {'upload_intent': 'existing_product_refresh', 'shopify_product_id': '123'} if refresh else {}
    prompt = _prompt('Collector', 'Verified story', edit={
        'source': {'id': 'id:Original', 'rev': ORIGINAL_REV, 'path_display': ORIGINAL_PATH},
        'metadata': metadata,
    })
    assert EDIT_AUTHENTICITY_CHECK in prompt
    assert 'compare the revision with the exact pre-edit PSD' in prompt
    assert 'If the edit wins and required PSD and collector-layer checks pass, continue verified replacement' in prompt
    assert 'The pre-edit PSD establishes preservation only.' in prompt
    assert 'unresolved or unverified facial fidelity is ineligible' not in prompt
    assert 'If any discrepancy remains unverified' not in prompt
    assert 'preserve any verified PSD it was meant to replace' not in prompt
    assert 'If preservation cannot be verified, a discrepancy is visible' in prompt
    assert 'needs_attention' in prompt
    if refresh:
        assert 'Once the staged pair is verified and ready_for_review' not in prompt
        assert 'Do not relabel that inherited limitation ready_for_review' in prompt
    else:
        assert 'Never delete the canonical PSD to clear the path.' in prompt
        assert 'A create-only Dropbox upload cannot perform a revision-aware replacement' in prompt
        assert 'Unresolved review notes' in prompt
        assert 'After verifying the canonical replacement and its matching JSON' in prompt


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
