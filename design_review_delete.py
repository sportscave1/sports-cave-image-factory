"""Recoverable deletion for exact Review PSD revisions and their handoffs."""

from pathlib import PurePosixPath

from design_review_metadata import _read_sidecar, handoff_paths, is_working_file
from product_upload_dropbox import REVIEW, approved


def _same_file(actual, expected):
    return bool(actual and all(actual.get(key) == expected.get(key)
                               for key in ('id', 'rev', 'path_display')))


def _remove(provider, item):
    try:
        provider.api.delete_path_recoverable(provider.token, item['path_display'], root_path=REVIEW,
                                             expected_revision=item['rev'])
    except Exception:
        # A timeout can occur after Dropbox has committed the delete.
        if provider.metadata_if_present(item['id']) is not None:
            raise


def delete_design(provider, source):
    """Remove a selected PSD and only the JSON bound to that exact selection."""
    if (not approved(source) or not source.get('rev') or is_working_file(source['name'])
            or str(PurePosixPath(source['path_display']).parent).casefold() != REVIEW.casefold()):
        raise ValueError('Select a design directly inside Dropbox Review.')
    if not _same_file(provider.metadata_if_present(source['path_display']), source):
        raise ValueError('The PSD changed in Dropbox. Select its current revision to delete it.')

    sidecars, warnings = [], []
    for path in handoff_paths(source['path_display']):
        try:
            item = provider.metadata_if_present(path)
            if item is None:
                continue
            data, actual = _read_sidecar(provider, item)
            if (actual.get('path_display', '').casefold() != path.casefold()
                    or not _same_file(actual, item)
                    or any(data.get(field) != source[key] for field, key in (
                        ('dropbox_file_id', 'id'), ('dropbox_revision', 'rev'),
                        ('dropbox_path', 'path_display')))):
                raise ValueError('Upload JSON does not match this PSD revision.')
            sidecars.append(actual)
        except Exception:
            warnings.append(f'Kept unverified upload JSON at {path}.')

    _remove(provider, source)
    for item in sidecars:
        path = item['path_display']
        try:
            if not _same_file(provider.metadata_if_present(path), item):
                raise ValueError('Upload JSON changed.')
            _remove(provider, item)
        except Exception:
            warnings.append(f'Could not remove upload JSON at {path}.')
    from design_deletion_status import invalidate
    invalidate()
    return warnings
