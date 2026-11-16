"""Synthetic Design Studio Edit tests. No Dropbox or Shopify access."""
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from auto_editions import file_hash
from design_review_metadata import is_working_file
from design_review_replace import apply
from home_morning_brief_actions import _prompt
from product_upload_dropbox import REVIEW


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
    for start, end in (('**8A. Re-read and review**', '**8D. Prepare'),
                       ('**MANDATORY — MOVE THE PLAQUE', '**8E.')):
        assert edit[edit.index(start):edit.index(end)] == standard[standard.index(start):standard.index(end)]
    assert '12. **Final improvement.**' in edit and 'PASS, CHANGE or UNVERIFIED' in edit
    assert edit.index('Step 7.') < edit.index('Make a **new image-generation call**') < edit.index('Save a separate create-only file')
    assert 'ORIGINAL REVIEW SOURCE' in edit and 'expected revision' in edit
    assert 'gid://shopify/Product/123' in edit and ORIGINAL_PATH in edit
    assert '[Product Title] - TRIAL.psd' not in edit
    assert 'upload_intent (new_product)' not in edit


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
        return dict(current[path], path_display=target)

    api = SimpleNamespace(copy_path=Mock(side_effect=backup), upload_revision=Mock(side_effect=upload),
                          get_verified_psd_stream=verified, delete_path_recoverable=Mock())
    provider = SimpleNamespace(metadata_if_present=lambda key: current.get(key),
                               download=download, token='synthetic', context={'root_path': REVIEW}, api=api)
    validate = Mock()
    monkeypatch.setattr('design_review_replace._inspect', validate)
    return provider, original, trial, staging, current, validate


def test_replace_preserves_id_path_backup_and_cleans_only_exact_temporary_revisions(files):
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
    staged[1] = layer('SC_EDITION_NUMBER', kind='type', ident=99, bbox=(20, 20, 60, 40))
    with pytest.raises(ValueError, match='preserve the original'):
        _inspect('original', 'trial', 'staging')
    staged[1] = layer('SC_EDITION_NUMBER', kind='type', ident=11, bbox=(110, 20, 160, 40))
    with pytest.raises(ValueError, match='aligned'):
        _inspect('original', 'trial', 'staging')
