"""Offline coverage for the Dropbox title and handoff rename."""
from contextlib import contextmanager
from hashlib import sha256
from io import BytesIO
import json
from pathlib import PurePosixPath
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from design_review_metadata import TITLE_RENAME, handoff_paths, read_gallery_handoff, read_handoff
from design_review_title import resume_review_title, sync_review_title, unclaimed_artwork
from product_upload_dropbox import REVIEW
from tests.test_product_upload_intake import database, env  # noqa: F401


class Dropbox:
    token = 'fixture'
    context = {'root_path': REVIEW.rsplit('/', 1)[0]}

    def __init__(self):
        self.files = {}
        self.history = {}
        self.api = SimpleNamespace(
            get_file_response=self.download, recent_file_revisions=self.revisions,
            move_path=Mock(side_effect=self.move), upload_local_file=Mock(side_effect=self.create),
            upload_revision=Mock(side_effect=self.update), delete_path_recoverable=Mock(side_effect=self.delete),
        )

    def save(self, id_, path, raw):
        rev = f'{len(self.history) + 1:08x}'
        row = dict(id=id_, rev=rev, path_display=path, name=PurePosixPath(path).name,
                   content_hash=sha256(raw).hexdigest(), size=len(raw), **{'.tag': 'file'})
        self.files[id_] = self.history[rev] = row, raw
        return row

    def metadata_if_present(self, locator):
        if locator.startswith('id:'):
            return self.files.get(locator, (None, None))[0]
        return next((row for row, _ in self.files.values()
                     if row['path_display'].casefold() == locator.casefold()), None)

    def download(self, _, locator):
        row, raw = self.history[locator[4:]] if locator.startswith('rev:') else self.files[locator]
        return row, SimpleNamespace(iter_content=lambda **_: iter((raw,)), close=lambda: None)

    def revisions(self, _, id_):
        return [row for row, _ in reversed(self.history.values()) if row['id'] == id_]

    def move(self, _, id_, path, *, root_path):
        occupied = self.metadata_if_present(path)
        if occupied and occupied['id'] != id_:
            raise ValueError('conflict')
        return self.save(id_, path, self.files[id_][1])

    def create(self, _, path, local, *, conflict):
        assert conflict == 'cancel'
        if self.metadata_if_present(path):
            raise ValueError('conflict')
        return self.save(f'id:JSON-{len(self.history)}', path, local.read_bytes())

    def update(self, _, path, local, revision):
        before = self.metadata_if_present(path)
        if before['rev'] != revision:
            raise ValueError('conflict')
        return self.save(before['id'], path, local.read_bytes())

    def delete(self, _, path, *, root_path, expected_revision):
        row = self.metadata_if_present(path)
        assert row['rev'] == expected_revision
        del self.files[row['id']]


def fixture(old='Old Headline', title='New Headline', *, sidecar_index=0, previous_title=None):
    provider = Dropbox()
    source = provider.save('id:Art', f'{REVIEW}/{old}.psd', b'fixture-psd')
    path = handoff_paths(source['path_display'])[sidecar_index]
    data = dict(design_title=previous_title or old, sport='Cricket', design_story='Saved story',
                intended_collections=['cricket-wall-art'], upload_intent='existing_product_refresh',
                existing_shopify_product_id='gid://shopify/Product/51', review_status='ready_for_review',
                dropbox_file_id=source['id'], dropbox_path=source['path_display'], dropbox_revision=source['rev'])
    provider.save('id:JSON', path, json.dumps(data).encode())
    data.update(design_title=title)
    metadata = provider.save('id:JSON', path, json.dumps(data).encode())
    return provider, source, metadata


@pytest.mark.parametrize(('old', 'new', 'index'), [
    ('Old Headline', 'New Headline', 0), ('Old Headline', 'New Headline', 1),
    ('Old Headline', 'Old headline', 0),
])
def test_title_sync_preserves_artwork_identity_and_verified_product_link(old, new, index):
    provider, source, previous = fixture(old, new, sidecar_index=index)
    final, warning = sync_review_title(provider, source)
    target_sidecar = handoff_paths(final['path_display'])[index]
    receipt = provider.metadata_if_present(target_sidecar)
    raw = json.loads(provider.files[receipt['id']][1])
    assert not warning
    assert final['id'] == source['id'] and final['content_hash'] == source['content_hash']
    assert final['rev'] != source['rev'] and final['name'] == new + '.psd'
    assert receipt['path_display'] == target_sidecar
    assert raw['design_title'] == raw['product_name'] == new
    assert raw['dropbox_revision'] == final['rev'] and raw['dropbox_path'] == final['path_display']
    assert TITLE_RENAME not in raw and raw['design_story'] == 'Saved story'
    assert read_handoff(provider, final)['shopify_product_id'] == 'gid://shopify/Product/51'
    assert read_handoff(provider, final)['design_name'] == new
    assert len(provider.files) == 2
    assert sync_review_title(provider, final) == (final, '')


def test_existing_filename_with_unchanged_title_is_preserved():
    provider, source, _ = fixture(previous_title='New Headline')
    assert sync_review_title(provider, source) == (source, '')
    provider.api.move_path.assert_not_called()
    provider.api.upload_local_file.assert_not_called()


def test_existing_smart_upload_claim_keeps_its_exact_dropbox_source(env, monkeypatch):
    store, sql, _ = env
    provider, source, _ = fixture()
    sql.execute('INSERT INTO product_upload_intakes (id, actor_id, mode, data) VALUES (%s,%s,%s,%s::jsonb)',
                (str(uuid4()), 'reviewer', 'LIVE', json.dumps(dict(smart_upload=True, source=source))))
    monkeypatch.setattr('product_upload_api.connect', store.connect)
    with pytest.raises(ValueError, match='already in Smart Upload'):
        sync_review_title(provider, source, guard=unclaimed_artwork)
    provider.api.move_path.assert_not_called()
    provider.api.upload_local_file.assert_not_called()


def test_first_handoff_from_an_edited_legacy_psd_can_sync():
    provider, source, sidecar = fixture()
    provider.history = {source['rev']: provider.files[source['id']], sidecar['rev']: provider.files[sidecar['id']]}
    # Use the same PSD ID to represent an older design revision without a sidecar.
    provider.history['older'] = dict(source, rev='older', content_hash='different'), b'older psd'
    final, warning = sync_review_title(provider, source)
    assert final['name'] == 'New Headline.psd' and not warning


@pytest.mark.parametrize('extension', ['.psd', '.upload.json'])
def test_conflicts_preserve_both_files(extension):
    provider, source, _ = fixture()
    target_path = f'{REVIEW}/New Headline.psd'
    occupied = target_path if extension == '.psd' else handoff_paths(target_path)[0]
    provider.save('id:Other', occupied, b'{}')
    with pytest.raises(ValueError, match='already uses the new title'):
        sync_review_title(provider, source)
    assert len(provider.files) == 3
    provider.api.move_path.assert_not_called()
    provider.api.delete_path_recoverable.assert_not_called()


def test_gallery_resumes_after_dropbox_renames_artwork_before_json_write(monkeypatch):
    import design_review_page as gallery

    provider, source, _ = fixture()
    provider.api.upload_revision.side_effect = OSError('temporary upload failure')
    with pytest.raises(OSError, match='temporary upload failure'):
        sync_review_title(provider, source)
    moved = provider.metadata_if_present(source['id'])
    assert moved['name'] == 'New Headline.psd'
    sidecar = provider.metadata_if_present(handoff_paths(moved['path_display'])[0])
    details = read_gallery_handoff(provider, moved, (sidecar,))
    assert details['title_sync_pending'] and details['review_status'] == 'needs_attention'
    provider.api.upload_revision.side_effect = provider.update
    monkeypatch.setattr(gallery, '_details', lambda *_: (details, ''))
    final, display, warning, _ = gallery._synced_design(provider, 'actor', moved, (sidecar,), False, False)
    assert final == moved and not warning
    assert display['design_name'] == 'New Headline' and display['review_status'] == 'ready_for_review'
    assert len(provider.files) == 2


def test_cleanup_can_resume_after_verified_json_is_saved():
    provider, source, _ = fixture()
    provider.api.delete_path_recoverable.side_effect = OSError('Dropbox unavailable')
    final, warning = sync_review_title(provider, source)
    assert 'still needs cleanup' in warning
    assert read_handoff(provider, final)['design_name'] == 'New Headline'
    sidecar = provider.metadata_if_present(handoff_paths(final['path_display'])[0])
    provider.api.delete_path_recoverable.side_effect = provider.delete
    assert resume_review_title(provider, final, (sidecar,)) == (final, '')
    assert len(provider.files) == 2


def test_apply_staged_replacement_saves_optional_title_as_part_of_the_review(monkeypatch):
    from design_review_replace import apply

    provider, original, _ = fixture(title='Old Headline')
    # Staged replacement verifies the Dropbox-format content hash on download.
    monkeypatch.setattr('auto_editions.file_hash', lambda file, **_: sha256(file.read_bytes()).hexdigest())
    monkeypatch.setattr('design_review_replace._inspect', lambda *args: None)
    original = provider.save(original['id'], original['path_display'], b'original' * 8)
    old_meta = provider.files['id:JSON']
    raw = json.loads(old_meta[1])
    raw['dropbox_revision'] = original['rev']
    provider.save('id:JSON', old_meta[0]['path_display'], json.dumps(raw).encode())
    prefix = original['path_display'][:-4] + ' - EDIT-' + original['rev']
    trial = provider.save('id:Trial', prefix + ' - TRIAL.psd', b'trial' * 10)
    staged = provider.save('id:Stage', prefix + ' - STAGING.psd', b'winner' * 10)
    provider.download = lambda metadata, path: path.write_bytes(provider.files[metadata['id']][1])
    provider.api.copy_path = lambda _, old, new, **kwargs: provider.save('id:Backup', new, provider.files[original['id']][1])

    @contextmanager
    def verified(_, id_, __):
        yield provider.metadata_if_present(id_)

    provider.api.get_verified_psd_stream = verified
    final, _, warnings = apply(provider, original, trial['path_display'], staged['path_display'], title='New Headline')
    assert not warnings and final['name'] == 'New Headline.psd'
    assert final['id'] == original['id'] and final['content_hash'] == staged['content_hash']
    assert read_handoff(provider, final)['design_name'] == 'New Headline'
    assert len(provider.files) == 2
