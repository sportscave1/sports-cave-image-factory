"""Revision-aware application of an inspected Design Studio staging file."""
from contextlib import nullcontext
import json
import logging
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

from design_review_metadata import read_handoff_record
from product_upload_dropbox import REVIEW, approved, within, validate_structure


def _same(actual, expected, keys=('id', 'rev', 'path_display', 'content_hash')):
    return bool(actual and all(actual.get(key) == expected.get(key) for key in keys))


def _staged(provider, original, path, kind, *, allow_missing=False):
    original_path = PurePosixPath(original['path_display'])
    candidate = PurePosixPath(path.strip())
    prefix = f'{original_path.stem} - EDIT-{original["rev"]} - {kind}'
    if (candidate.parent != original_path.parent or candidate.suffix.lower() != '.psd'
            or not (candidate.stem == prefix or candidate.stem.startswith(prefix + ' - '))):
        raise ValueError(f'Choose this revision’s {kind.lower()} PSD from the Review folder.')
    metadata = provider.metadata_if_present(str(candidate))
    if metadata is None and allow_missing:
        return None
    if not metadata or not approved(metadata) or metadata['path_display'] != str(candidate):
        raise ValueError(f'The {kind.lower()} PSD is unavailable.')
    return metadata


def _verify_saved(provider, source):
    with provider.api.get_verified_psd_stream(provider.token, source['id'], source['rev']) as receipt:
        if not _same(receipt, source, ('id', 'rev', 'content_hash', 'size')):
            raise ValueError('The retained PSD could not be reopened at its verified revision.')


def _cleanup(provider, canonical, temporary_files):
    warnings = []
    for temporary in temporary_files:
        path = temporary['path_display']
        try:
            if not _same(provider.metadata_if_present(canonical['id']), canonical):
                raise ValueError('The canonical PSD changed before cleanup.')
            if not _same(provider.metadata_if_present(path), temporary):
                raise ValueError('The temporary PSD changed before cleanup.')
            try:
                provider.api.delete_path_recoverable(provider.token, path, root_path=provider.context['root_path'],
                                                     expected_revision=temporary['rev'])
            except Exception:
                if provider.metadata_if_present(temporary['id']) is not None:
                    raise
            if provider.metadata_if_present(temporary['id']) is not None:
                raise ValueError('Dropbox did not confirm removal of the temporary PSD.')
        except Exception:
            warnings.append(f'Could not remove {PurePosixPath(path).name}.')
    return warnings


def keep_original(provider, original, paths):
    """Retain the exact original and remove only the selected drafts for this revision."""
    if not approved(original) or not within(original['path_display'], REVIEW):
        raise ValueError('Only originals inside the Review folder can be kept here.')
    paths = list(dict.fromkeys(path.strip() for path in paths if path.strip()))
    if not paths:
        raise ValueError('Enter the exact Dropbox paths of the PSD drafts from the completed edit.')
    prefix = f'{PurePosixPath(original["path_display"]).stem} - EDIT-{original["rev"]} - '
    temporary = []
    for line in paths:
        # The Edit run can carry its own receipts through to the fallback control.
        fields = [field.strip() for field in line.split(' | ', 2)]
        path = fields[0]
        if len(fields) not in (1, 3) or (len(fields) == 3 and not all(fields)):
            raise ValueError('Enter a draft path or a path followed by its Dropbox file ID and revision.')
        kind = PurePosixPath(path).stem.removeprefix(prefix).split(' - ', 1)[0]
        if kind not in ('TRIAL', 'STAGING', 'BACKUP'):
            raise ValueError('Choose only trial, staging or backup PSDs for this exact edit revision.')
        draft = _staged(provider, original, path, kind, allow_missing=True)
        if len(fields) == 3:
            _, file_id, revision = fields
            if (draft and (draft['id'], draft['rev']) != (file_id, revision)) or (
                    not draft and provider.metadata_if_present(file_id) is not None):
                raise ValueError('A draft differs from its recorded Dropbox identity or revision.')
        if draft:
            if draft['id'] == original['id'] or (kind == 'BACKUP' and draft.get('content_hash') != original.get('content_hash')):
                raise ValueError('A selected draft or backup could not be verified for this edit.')
            temporary.append(draft)
    if not _same(provider.metadata_if_present(original['id']), original):
        raise ValueError('The original PSD changed. Refresh Design Studio and review the current revision.')
    _verify_saved(provider, original)
    return _cleanup(provider, original, temporary)


def _inspect(original, trial, staged):
    from auto_editions_colour_source import inspect_psd
    from psd_tools import PSDImage

    for path in (original, trial, staged):
        validate_structure(path)
    first, final = (inspect_psd(p) for p in (original, staged))
    for field in ('width', 'height', 'icc', 'mode', 'depth'):
        if first[field] != final[field]:
            raise ValueError('Staging dimensions, colour profile or pixel format differ from the original.')

    def collector(path):
        document = PSDImage.open(path)
        layers = list(document.descendants())
        items = {}
        for name in ('SC_EDITION_PLAQUE', 'SC_EDITION_NUMBER'):
            matches = [layer for layer in layers if layer.is_visible() and layer.name == name]
            if len(matches) != 1:
                raise ValueError(f'The PSD must contain exactly one visible {name} layer.')
            items[name] = matches[0]
        number, plaque = items['SC_EDITION_NUMBER'], items['SC_EDITION_PLAQUE']
        if number.kind != 'type' or not number.text.strip():
            raise ValueError('SC_EDITION_NUMBER must contain editable text.')
        return document, number, plaque

    _, original_number, original_plaque = collector(original)
    document, number, plaque = collector(staged)
    if (number.text != original_number.text or number.layer_id < 0 or number.layer_id != original_number.layer_id
            or plaque.kind != original_plaque.kind or plaque.layer_id < 0 or plaque.layer_id != original_plaque.layer_id):
        raise ValueError('The staged PSD must preserve the original plaque and editable number layers.')
    if not (plaque.left <= number.left < number.right <= plaque.right
            and plaque.top <= number.top < number.bottom <= plaque.bottom):
        raise ValueError('The editable edition number must be aligned inside the plaque.')
    for name, visible in (('ORIGINAL REVIEW SOURCE', False),
                          ('ORIGINAL EDITABLE ARTWORK', False),
                          ('FINAL POLISHED ARTWORK', True)):
        matches = [layer for layer in document if layer.name == name]
        if len(matches) != 1 or matches[0].is_visible() != visible:
            raise ValueError(f'The staged PSD must contain one {name} layer or group with the required visibility.')


def apply(provider, original, trial_path, staged_path, *, title='', review_notes='', title_guard=nullcontext):
    """Replace the exact verified revision and keep its ID even if the title changes."""
    if not approved(original) or not within(original['path_display'], REVIEW):
        raise ValueError('Only originals inside the Review folder can be replaced here.')
    trial = _staged(provider, original, trial_path, 'TRIAL')
    staged = _staged(provider, original, staged_path, 'STAGING')
    current = provider.metadata_if_present(original['id'])
    if not _same(current, original):
        raise ValueError('The original revision changed. The current original and staged result were retained.')
    if any(type(item.get('size')) is not int or not 40 <= item['size'] <= 150 * 1024**2
           for item in (original, trial, staged)):
        raise ValueError('Server replacement supports PSDs up to 150 MiB per file. Keep the staged result for a revision-aware desktop replacement.')
    api, token, root = provider.api, provider.token, provider.context['root_path']
    path = original['path_display']
    record = read_handoff_record(provider, original)
    title = title.strip()
    review_notes = review_notes.strip()
    if review_notes and not record:
        raise ValueError('A matching upload JSON is required to retain unresolved review notes during replacement.')
    if title:
        from design_review_title import title_destination
        title_destination(original, title)
        if not record:
            raise ValueError('A matching upload JSON is required to save a new design title.')
    backup_path = path[:-4] + f' - EDIT-{original["rev"]} - BACKUP.psd'
    from auto_editions import file_hash
    with TemporaryDirectory(prefix='sc-design-edit-') as directory:
        files = [Path(directory) / f'{name}.psd' for name in ('original', 'trial', 'staging')]
        for source, file in zip((original, trial, staged), files):
            provider.download(source, file)
            if file_hash(file, dropbox=True) != source['content_hash']:
                raise ValueError('A downloaded PSD did not match its exact Dropbox revision.')
        _inspect(*files)
        if not _same(provider.metadata_if_present(original['id']), original):
            raise ValueError('The original changed during verification. The staged result was retained.')
        backup = provider.metadata_if_present(backup_path)
        if not backup:
            backup = api.copy_path(token, path, backup_path, root_path=root)
        if not _same(backup, dict(original, path_display=backup_path), ('path_display', 'content_hash')):
            raise ValueError('The original backup could not be verified. The original was retained.')
        for temporary in (trial, staged):
            if not _same(provider.metadata_if_present(temporary['id']), temporary):
                raise ValueError('A trial or staged PSD changed during verification. The original was retained.')
        final = api.upload_revision(token, path, files[2], original['rev'])
        current = provider.metadata_if_present(original['id'])
        if not _same(current, final) or not _same(final, original, ('id', 'path_display')):
            raise ValueError('Replacement identity could not be confirmed. The backup, trial and staged file were retained.')
        try:
            if not _same(final, staged, ('content_hash', 'size')):
                raise ValueError('The canonical copy does not match staging.')
            _verify_saved(provider, final)
        except Exception as error:
            restored = api.upload_revision(token, path, files[0], final['rev'])
            if not _same(restored, original, ('id', 'path_display', 'content_hash', 'size')):
                raise ValueError('Rollback verification is pending. The backup and staged files were retained.') from error
            if record:
                data, sidecar = record
                data['dropbox_revision'] = restored['rev']
                handoff = Path(directory) / 'rollback-handoff.json'
                handoff.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
                try:
                    api.upload_revision(token, sidecar['path_display'], handoff, sidecar['rev'])
                except Exception:
                    logging.getLogger(__name__).warning('Design rollback metadata update failed')
            raise ValueError('Final verification failed. The original was restored and the trial and staged files were retained.') from error
        warnings = []
        metadata_saved = False
        if record:
            data, sidecar = record
            data.update(dropbox_file_id=final['id'], dropbox_revision=final['rev'],
                        dropbox_path=final['path_display'])
            if title:
                data.update(design_title=title, product_name=title)
            if review_notes:
                previous_notes = str(data.get('review_notes') or '').strip()
                data.update(review_status='needs_attention',
                            review_notes='\n'.join(note for note in (previous_notes, review_notes) if note))
            handoff = Path(directory) / 'handoff.json'
            handoff.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
            try:
                api.upload_revision(token, sidecar['path_display'], handoff, sidecar['rev'])
                saved = read_handoff_record(provider, final)
                if not saved or saved[0] != data or saved[1]['id'] != sidecar['id']:
                    raise ValueError('The updated handoff could not be verified against the saved PSD.')
                metadata_saved = True
            except Exception:
                warnings.append('The canonical PSD is verified. Its upload metadata still needs a revision update.')
                logging.getLogger(__name__).warning('Design replacement metadata update failed')
        if not warnings:
            warnings.extend(_cleanup(provider, final, (trial, staged, backup)))
        if title and metadata_saved:
            from design_review_title import sync_review_title
            try:
                final, warning = sync_review_title(provider, final, confirmed=True, guard=title_guard)
                if warning:
                    warnings.append(warning)
            except ValueError as error:
                warnings.append(str(error))
            except Exception:
                logging.getLogger(__name__).exception('Design replacement title sync failed')
                warnings.append('The new title was saved in JSON. Refresh Design Studio to retry the Dropbox rename.')
    return final, backup, warnings
