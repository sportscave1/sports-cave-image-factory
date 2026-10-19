"""Saved WebP receipts, never a folder search or a new export."""
import hashlib
import json
from pathlib import PurePosixPath
from urllib.parse import urlencode

ORDER = ('black-frame', 'man-cave', 'office', 'living-room', 'size-guide', 'oak-frame', 'white-frame', 'unframed')


def legacy_output(row):
    """Recover only this upload's unique completed receipt; never browse folders."""
    context = row['data'].get('mockups_context') or {}
    images = context.get('images') or []
    if len(images) != len(ORDER) or {x.get('role') for x in images} != set(ORDER):
        raise ValueError('This older upload has no complete saved image manifest. Retry Save all.')
    matches = [(key, value) for key, value in row['data'].get('mockup_saves', {}).items()
               if value.get('state') == 'Complete' and value.get('target') == context.get('folder')]
    if len(matches) != 1:
        raise ValueError('This older upload has no unique saved receipt. Retry Save all.')
    fingerprint, saved = matches[0]
    receipt = saved.get('receipt') or {}
    files = receipt.get('successes') or []
    if receipt.get('failures') or receipt.get('cancelled') or receipt.get('destination') != context.get('folder'):
        raise ValueError('This older upload did not finish saving. Retry Save all.')
    names = [x.get('relative_path') for x in files]
    if not names or len(set(names)) != len(names):
        raise ValueError('The saved receipt contains missing or duplicate files. Retry Save all.')
    # Older releases persisted the authoritative complete receipt without an
    # additional hash manifest. Keep the original record intact on read-back.
    manifest = saved.get('manifest') or [dict(name=name) for name in names]
    output = dict(context, export_fingerprint=fingerprint, files=files,
                  manifest=[dict(slot_id=x['role'], output_filename=x['filename'],
                                 display_label=x['role'].replace('-', ' ').title()) for x in images])
    return output, dict(saved, manifest=manifest)


def package(row, expected=None):
    from product_upload_identity import operation
    if not row or not row['data'].get('mockups_exported'):
        raise ValueError('Save the complete current image package first.')
    output = operation(row).get('output') or {}
    fingerprint = output.get('export_fingerprint')
    saved = row['data'].get('mockup_saves', {}).get(fingerprint) or {}
    if not fingerprint:
        output, saved = legacy_output(row)
        fingerprint = output['export_fingerprint']
    if not fingerprint or saved.get('state') != 'Complete' or saved.get('target') != output.get('folder'):
        raise ValueError('The saved package is unavailable. Retry Save all.')
    manifest = {x['slot_id']: x for x in output.get('manifest', [])}
    receipts = {x['relative_path']: x['metadata'] for x in output.get('files', [])}
    if set(receipts) != {x['name'] for x in saved.get('manifest', [])} or (saved.get('receipt') or {}).get('failures'):
        raise ValueError('The current image package has not finished saving. Retry Save all.')
    items = []
    for role in ORDER:
        spec = manifest.get(role) or {}
        name = spec.get('output_filename', '')
        relative = 'WEBP/' + name
        meta = receipts.get(relative) or {}
        if (not name or PurePosixPath(name).name != name or not name.endswith('.webp')
                or meta.get('name') != name or not all(meta.get(k) for k in ('id', 'rev', 'content_hash', 'size'))):
            raise ValueError('Saved WebP is missing or unverified: ' + (name or role) + '. Retry Save all.')
        path = meta.get('path_display') or meta.get('path_lower') or ''
        if path.casefold() != (output['folder'].rstrip('/') + '/' + relative).casefold():
            raise ValueError('Saved file destination differs: ' + name)
        items.append(dict(role=role, label=spec.get('display_label') or role, name=name, metadata=meta))
    if {x for x in receipts if x.lower().endswith('.webp')} != {'WEBP/' + x['name'] for x in items}:
        raise ValueError('The saved WebP package differs from the eight product images. Retry Save all.')
    if len({x['metadata']['id'] for x in items}) != len(ORDER):
        raise ValueError('The saved package contains duplicate file identities. Retry Save all.')
    version = hashlib.sha256(json.dumps([str(row['id']), fingerprint, items], sort_keys=True).encode()).hexdigest()
    if expected is not None and version != expected:
        raise ValueError('The saved package changed. Use the current files below.')
    return dict(version=version, folder=output['folder'] + '/WEBP', items=items)


def view(row):
    result = package(row)
    for item in result['items']:
        args = dict(id=str(row['id']), version=result['version'], role=item['role'])
        item['preview'] = '/api/product-uploads/saved-image?' + urlencode(dict(args, thumbnail='1'))
        item['original'] = '/api/product-uploads/saved-image?' + urlencode(args)
        item['download'] = '/api/product-uploads/saved-image?' + urlencode(dict(args, download='1'))
        del item['metadata']
    return result


def verified(provider, item):
    expected = item['metadata']
    actual = provider.metadata_if_present(expected['id'])
    if not actual or any(actual.get(k) != expected.get(k) for k in ('id', 'rev', 'content_hash', 'size')):
        raise ValueError(item['name'] + ' is missing or changed in Dropbox. Retry Save all before copying.')
    if (actual.get('path_display') or actual.get('path_lower') or '').casefold() != (expected.get('path_display') or expected.get('path_lower') or '').casefold():
        raise ValueError(item['name'] + ' moved from its saved folder. Restore it before copying.')
    return actual


def native_grant(row, version, provider, user, context):
    import files_upload_api as files
    if not version:
        raise ValueError('Refresh the saved package before preparing files.')
    result = package(row, version)
    root = context['root_path'].rstrip('/')
    selections = []
    for item in result['items']:
        meta = verified(provider, item)
        path = meta.get('path_display') or meta.get('path_lower') or ''
        if not path.casefold().startswith(root.casefold() + '/'):
            raise ValueError('Saved file is outside the approved Dropbox root: ' + item['name'])
        selections.append(dict(path=path[len(root)+1:], id=meta['id'], revision=meta['rev'], tag='file'))
    record = files.NATIVE_TRANSFER_MANAGER.create(access_token=context['access_token'], root_path=root,
                                                   user=user, selections=selections)
    record.purpose = 'product_upload_webp'
    for entry, item in zip(record.items, result['items']):
        entry['content_hash'] = item['metadata']['content_hash']
    return record
