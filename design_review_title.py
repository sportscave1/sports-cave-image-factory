"""Keep a renamed Review PSD and its Smart Upload metadata together in Dropbox."""
from contextlib import contextmanager, nullcontext
import json
from pathlib import Path, PurePosixPath
import re
from tempfile import TemporaryDirectory

from design_review_metadata import (
    MAX_HANDOFF_BYTES, TITLE_RENAME, _read_sidecar, handoff_paths, is_working_file, read_handoff_record,
)
from product_upload_lifecycle import filename


@contextmanager
def unclaimed_artwork(source):
    from product_upload_api import connect
    from product_upload_intake import smart_claim

    with connect() as conn, conn.cursor() as cursor:
        if smart_claim(cursor, source):
            raise ValueError('This PSD is already in Smart Upload. Its Dropbox filename was kept.')
        yield


def title_destination(source, title):
    path = PurePosixPath(source['path_display'])
    name = filename(title)
    stem = name[:-4]
    version = re.search(r' - v(?:[2-9]|[1-9]\d+)$', path.stem, re.IGNORECASE)
    if version and path.stem[:version.start()].casefold() == stem.casefold():
        return str(path)
    if is_working_file(name):
        raise ValueError('Use a design title that will be visible in the Review gallery.')
    return str(path.with_name(name))


def _matches(actual, expected, fields=('id', 'rev', 'path_display', 'content_hash', 'size')):
    return bool(actual and all(actual.get(field) == expected.get(field) for field in fields))


def _changed_title(provider, source, data, sidecar):
    # The product filename sometimes includes extra context. A mismatch by itself
    # is insufficient to distinguish that convention from an actual title edit.
    had_title = False
    for previous in provider.api.recent_file_revisions(provider.token, sidecar['id']):
        if previous['id'] != sidecar['id'] or previous['rev'] == sidecar['rev']:
            continue
        prior, _ = _read_sidecar(provider, previous, historical=True)
        title = prior.get('design_title')
        if prior.get('dropbox_file_id') == source['id'] and isinstance(title, str) and title.strip():
            had_title = True
            if title.strip() != data['design_title'].strip():
                return True
    # Older artwork can gain its first handoff during an edit. A previous content
    # revision at this exact name distinguishes it from a newly created print.
    return not had_title and any(
        prior['id'] == source['id'] and prior.get('path_display') == source['path_display']
        and prior.get('content_hash') and prior['content_hash'] != source['content_hash']
        for prior in provider.api.recent_file_revisions(provider.token, source['id'])
    )


def _move(provider, item, path):
    if not _matches(provider.metadata_if_present(item['id']), item):
        raise ValueError('A Dropbox file changed before the title could be synchronised.')
    try:
        provider.api.move_path(provider.token, item['id'], path, root_path=provider.context['root_path'])
    except Exception:
        # A timeout can occur after Dropbox commits the move. Inspect by file ID.
        current = provider.metadata_if_present(item['id'])
        if not _matches(current, dict(item, path_display=path), ('id', 'path_display', 'content_hash', 'size')):
            raise
        return current
    current = provider.metadata_if_present(item['id'])
    if not _matches(current, dict(item, path_display=path), ('id', 'path_display', 'content_hash', 'size')):
        raise ValueError('The exact Dropbox file could not be confirmed after renaming.')
    return current


def _write(provider, path, data, existing=None):
    payload = json.dumps(data, ensure_ascii=False).encode('utf-8')
    if len(payload) > MAX_HANDOFF_BYTES:
        raise ValueError('The renamed upload JSON exceeds the supported size.')
    error = None
    with TemporaryDirectory(prefix='sc-review-title-') as directory:
        local = Path(directory) / 'handoff.json'
        local.write_bytes(payload)
        try:
            if existing:
                provider.api.upload_revision(provider.token, path, local, existing['rev'])
            else:
                provider.api.upload_local_file(provider.token, path, local, conflict='cancel')
        except Exception as failure:
            error = failure
    saved = provider.metadata_if_present(path)
    if not saved or (existing and saved['id'] != existing['id']) or _read_sidecar(provider, saved)[0] != data:
        if error:
            raise error
        raise ValueError('The renamed artwork JSON could not be verified.')
    return saved


def _paths(old_path, target, sidecar_path):
    for old, new in zip(handoff_paths(old_path), handoff_paths(target)):
        if sidecar_path.casefold() in (old.casefold(), new.casefold()):
            return old, new
    raise ValueError('The upload JSON is outside the matching Review locations.')


def _finish(provider, source, data, prepared, guard=nullcontext):
    # The prepared JSON records the exact artwork content. This allows a later
    # refresh to finish after a move assigns a new revision or a request times out.
    state = data[TITLE_RENAME]
    old_path = state.get('path')
    if (not isinstance(old_path, str) or not handoff_paths(old_path)
            or PurePosixPath(old_path).parent != PurePosixPath(source['path_display']).parent
            or not source.get('content_hash') or state.get('content_hash') != source['content_hash']
            or data.get('dropbox_file_id') != source['id']):
        raise ValueError('The pending title update no longer matches this PSD. The Dropbox files were kept.')
    target = title_destination(dict(source, path_display=old_path), data['design_title'])
    old_sidecar, target_sidecar = _paths(old_path, target, prepared['path_display'])
    same_name = old_sidecar.casefold() == target_sidecar.casefold()
    if source['path_display'] == old_path and same_name:
        if prepared['id'] != state.get('json_id') or data.get('dropbox_revision') != source['rev']:
            raise ValueError('The PSD or upload JSON changed during the pending title update.')
        with guard(source):
            if not _matches(provider.metadata_if_present(prepared['id']), prepared):
                raise ValueError('The upload JSON changed during the pending title update.')
            source = _move(provider, source, target)
    if source['path_display'] != target or not _matches(provider.metadata_if_present(source['id']), source):
        raise ValueError('The PSD changed before the title update finished. The Dropbox files were kept.')
    if prepared['path_display'] != target_sidecar:
        prepared = _move(provider, prepared, target_sidecar)
    final = dict(data, dropbox_revision=source['rev'], dropbox_path=target)
    if not same_name:
        # Bind the new JSON before removing the previous one. Leave the recovery
        # marker in place until cleanup succeeds so refresh can retry a partial run.
        if final != data:
            prepared = _write(provider, target_sidecar, final, prepared)
        try:
            previous = provider.metadata_if_present(old_sidecar)
            if previous:
                if previous['id'] != state.get('json_id') or previous['rev'] != state.get('json_rev'):
                    raise ValueError('The previous JSON changed during title sync.')
                prior, _ = _read_sidecar(provider, previous)
                if prior.get('dropbox_file_id') != source['id'] or prior.get('dropbox_path') != old_path:
                    raise ValueError('The previous JSON no longer belongs to this PSD.')
                if not _matches(provider.metadata_if_present(source['id']), source):
                    raise ValueError('The artwork changed before the previous upload JSON could be removed.')
                provider.api.delete_path_recoverable(provider.token, old_sidecar,
                                                     root_path=provider.context['root_path'],
                                                     expected_revision=previous['rev'])
        except Exception:
            return source, 'The new title is synced. The previous upload JSON still needs cleanup.'
    final.pop(TITLE_RENAME)
    _write(provider, target_sidecar, final, prepared)
    return source, ''


def resume_review_title(provider, source, candidates, *, guard=nullcontext):
    for sidecar in candidates:
        try:
            data, actual = _read_sidecar(provider, sidecar)
        except ValueError:
            continue
        if isinstance(data.get(TITLE_RENAME), dict):
            return _finish(provider, source, data, actual, guard)
    return source, ''


def sync_review_title(provider, source, *, confirmed=False, candidates=None, guard=nullcontext):
    """Use the exact saved JSON's title as the source of truth. Never overwrite a name collision."""
    record = read_handoff_record(provider, source, candidates=candidates)
    if not record or not isinstance(record[0].get('design_title'), str) or not record[0]['design_title'].strip():
        return source, ''
    data, sidecar = record
    title = data['design_title'].strip()
    target = title_destination(source, title)
    if target == source['path_display'] or (not confirmed and not _changed_title(provider, source, data, sidecar)):
        return source, ''
    with guard(source):
        return _rename(provider, source, data, sidecar, title, target)


def _rename(provider, source, data, sidecar, title, target):
    old_path = source['path_display']
    old_sidecar, target_sidecar = _paths(old_path, target, sidecar['path_display'])
    same_name = old_sidecar.casefold() == target_sidecar.casefold()
    occupied = provider.metadata_if_present(target)
    if occupied and occupied.get('id') != source['id']:
        raise ValueError('Another PSD already uses the new title. The current files were kept.')
    current = provider.metadata_if_present(source['id'])
    if not source.get('content_hash') or not _matches(current, source) or not _matches(provider.metadata_if_present(old_sidecar), sidecar):
        raise ValueError('The PSD or its upload JSON changed. Refresh Design Studio to retry the title sync.')
    renamed_data = dict(data, design_title=title, product_name=title,
                        dropbox_path=old_path if same_name else target)
    renamed_data[TITLE_RENAME] = dict(path=old_path, content_hash=source['content_hash'],
                                     json_id=sidecar['id'], json_rev=sidecar['rev'])
    if same_name:
        prepared = _write(provider, old_sidecar, renamed_data, sidecar)
    else:
        prepared = provider.metadata_if_present(target_sidecar)
        if prepared and _read_sidecar(provider, prepared)[0] != renamed_data:
            raise ValueError('Another upload JSON already uses the new title. The current files were kept.')
        if not prepared:
            prepared = _write(provider, target_sidecar, renamed_data)
        if not _matches(provider.metadata_if_present(old_sidecar), sidecar):
            raise ValueError('The upload JSON changed before the title could be synchronised.')
    source = _move(provider, source, target)
    return _finish(provider, source, renamed_data, prepared)
