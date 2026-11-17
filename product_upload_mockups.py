"""Shared Mockups result binding and durable, retry-safe export checkpoints."""
import hashlib
import json
import time
from pathlib import Path
from product_upload_intake import Intakes


def release_transient(result):
    """Only this page's generated web-image run, never a PSD or cloud file."""
    if not result or not result.get('_product_upload_intake'): return
    import mockup_storage
    import shutil
    root=mockup_storage.safe_temp_path(result.get('run_dir'))
    if not root or not root.is_dir() or root.is_symlink(): return
    if any(p.is_symlink() for p in root.rglob('*')): return
    shutil.rmtree(root)


def bind_export(connect, actor, result, kind, *, folder='', export_fingerprint=None):
    import image_factory as factory
    factory.require_complete_product_image_manifest(result['product_image_manifest'])
    with Intakes(connect).locked(result['_product_upload_intake'], actor) as (row, cur):
        if result.get('_staff_full_restart') != row['data'].get('staff_full_restart'):
            raise ValueError('These mockups belong to an earlier reset. Regenerate the current attempt.')
        if row['data']['source']['content_hash'] != result['_product_upload_source_hash']:
            raise ValueError('Export belongs to a previous PSD; it cannot unlock this Shopify handoff.')
        token = result.get('_product_upload_save_token')
        if kind == 'Dropbox':
            export_fingerprint = export_fingerprint or result.get('_product_upload_export_fingerprint')
            if not export_fingerprint:
                raise ValueError('Save All first: an exact save receipt is required.')
            if not token or row['data'].get('mockup_save_token') != token:
                raise ValueError('A newer image set or save operation replaced this save.')
            if row['data'].get('mockup_save_fingerprint') != export_fingerprint:
                raise ValueError('A newer save operation replaced this destination.')
            if result.get('_product_upload_source') and row['data']['source'] != result['_product_upload_source']:
                raise ValueError('Selected PSD changed during saving.')
        row['data'].update(mockups_exported=True, mockups_context=dict(
            design_name=result['product_name'], sport_category=result['sport_category'],
            folder=folder, export_kind=kind,
            images=[dict(role=x['slot_id'], filename=x.get('output_filename',''))
                    for x in factory.product_image_manifest_json(result['product_image_manifest'])]))
        from product_upload_identity import operation
        op = operation(row)
        op['output'] = dict(row['data']['mockups_context'], manifest=factory.product_image_manifest_json(result['product_image_manifest']))
        for fingerprint, saved in row['data'].get('mockup_saves', {}).items():
            if saved.get('state') == 'Complete' and saved.get('target') == folder and (not export_fingerprint or fingerprint==export_fingerprint):
                op['output'].update(folder_id=saved.get('folder_id'), export_fingerprint=fingerprint,
                                    save_token=token, files=saved.get('confirmed') or (saved.get('receipt') or {}).get('successes', []))
        if kind == 'Dropbox':
            from product_upload_source import current_source
            op['output']['webp_source'] = current_source(row)


def save(connect, actor, result, manifest, provider, parent, folder_name, conflict, perform, *, checkpointed=False,
         parent_identity=None, extend_core=None, recheck_complete=False, recover_missing_folder=False):
    """Reserve a destination once, including the existing numbered-folder rule.

    The provider call never occurs under a long DB transaction. Failed/unknown
    transfers retry the exact destination and bytes. An approved core save
    can reserve a fresh destination if its original folder no longer exists.
    """
    import auto_editions as ae
    entries=[dict(name=x['archive_name'],hash=ae.file_hash(x['path'])) for x in manifest]
    fingerprint=hashlib.sha256(json.dumps([entries,parent_identity or parent,folder_name,conflict],sort_keys=True).encode()).hexdigest()
    store=Intakes(connect);key=result['_product_upload_intake'];api=provider.api
    with store.locked(key,actor) as (row,cur):
        if result.get('_staff_full_restart') != row['data'].get('staff_full_restart'):
            raise ValueError('These mockups belong to an earlier reset. Regenerate the current attempt.')
        if row['data']['source']['content_hash'] != result['_product_upload_source_hash']:
            raise ValueError('Selected mockups belong to a previous PSD.')
        if result.get('_product_upload_source') and row['data']['source'] != result['_product_upload_source']:
            raise ValueError('The selected PSD identity/revision changed. Reselect it before saving.')
        saves=row['data'].setdefault('mockup_saves',{})
        old=saves.get(fingerprint)
        token=result.get('_product_upload_save_token')
        if token and row['data'].get('mockup_save_token') != token:
            raise ValueError('A newer image set or save operation replaced this save.')
        if not old and extend_core:
            core = saves.get(extend_core) or {}
            target = core.get('target', '')
            core_manifest = core.get('manifest') or []
            core_names = {entry['name'] for entry in core_manifest}
            if (core.get('state') == 'Saving' or not core.get('folder_id')
                    or core.get('requested_folder') != folder_name
                    or core.get('parent_identity') != parent_identity
                    or len(core_manifest) != 5 or len(core_names) != 5
                    or not all(entry in entries for entry in core_manifest)):
                raise ValueError('The earlier core save no longer matches this package. Use a new destination.')
            old = dict(target=target, folder_id=core['folder_id'], confirmed=core.get('confirmed', []),
                       state='Failed')
        if old and old['state']=='Saving' and time.time()-old['started_at']<600:
            raise ValueError('This exact save is already running. Wait for its receipt before retrying.')
        if old and parent_identity and old.get('folder_id'):
            old = resolve_reserved_folder(api, provider.token, parent, folder_name, old, recover_missing_folder)
        if not token:
            from product_upload_source import invalidate
            token=invalidate(row)
            result['_product_upload_save_token']=token
        result['_product_upload_export_fingerprint']=fingerprint
        row['data']['mockup_save_fingerprint']=fingerprint
        row['data'].update(mockups_exported=False,mockups_context=None,copied=False)
        if old and old['state']=='Complete' and not recheck_complete:
            return dict(old['receipt'],export_fingerprint=fingerprint,save_token=token)
        if old: target=old['target']
        else:
            proposed=api.join_upload_path(parent,api.sanitize_path_component(folder_name,fallback='mockups'))
            existing=api.get_metadata_if_exists(provider.token,proposed)
            if existing and conflict=='cancel': return dict(cancelled=True,destination=proposed,successes=[],failures=[],save_token=token)
            if existing and existing.get('.tag')!='folder': raise ValueError('A file already uses this output name.')
            target=api.numbered_path(provider.token,proposed) if existing and conflict=='numbered' else proposed
        import uuid
        attempt=uuid.uuid4().hex
        saves[fingerprint]=dict(old or {},state='Saving',target=target,started_at=time.time(),attempt=attempt,
                                manifest=entries,requested_folder=folder_name,parent_identity=parent_identity)
    def checkpoint(**changes):
        with store.locked(key,actor) as (row,cur):
            record=row['data']['mockup_saves'][fingerprint]
            if record.get('attempt')!=attempt:raise ValueError('A newer save attempt owns this destination.')
            if row['data'].get('mockup_save_token')!=token:
                raise ValueError('A newer image set or save operation replaced this save.')
            if row['data'].get('mockup_save_fingerprint')!=fingerprint:
                raise ValueError('A newer save operation replaced this destination.')
            if result.get('_product_upload_source') and row['data']['source']!=result['_product_upload_source']:
                raise ValueError('Selected PSD changed during saving. Completed uploads are retained.')
            record.update(changes,started_at=time.time())
    try:
        receipt=perform(target,dict(old or {}),checkpoint) if checkpointed else perform(target)
    except Exception:
        checkpoint(state='Failed')
        raise
    receipt=dict(receipt,export_fingerprint=fingerprint,save_token=token)
    if old and old.get('recreated_folder'):
        receipt['recreated_folder'] = True
    checkpoint(state='Failed' if receipt.get('failures') or receipt.get('cancelled') or
               {x.get('relative_path') for x in receipt.get('successes', [])} != {x['name'] for x in entries}
               else 'Complete',receipt=receipt)
    return receipt


def resolve_reserved_folder(api, token, parent, folder_name, saved, recover_missing):
    """Reuse an owned folder or reserve an empty path for an approved core retry."""
    folder_id = saved['folder_id']
    lookup_options = {'missing_only': True} if recover_missing else {}
    owned = api.get_metadata_if_exists(token, folder_id, **lookup_options)
    if not owned or not (owned.get('path_display') or owned.get('path_lower')):
        # The sport may have been renamed. Use its currently verified path.
        candidate = api.join_upload_path(parent, saved['target'].rsplit('/', 1)[-1])
        at_path = api.get_metadata_if_exists(token, candidate, **lookup_options)
        if at_path and at_path.get('id') == folder_id:
            owned = at_path
        elif not owned and recover_missing:
            target = candidate
            if at_path:
                proposed = api.join_upload_path(parent, folder_name)
                target = api.numbered_path(token, proposed)
            # Keep the save fingerprint but discard every receipt for the old folder.
            return dict(state='Failed', target=target, recreated_folder=True)
    target = api.normalize_dropbox_path((owned or {}).get('path_display') or (owned or {}).get('path_lower') or '')
    if (not owned or owned.get('id') != folder_id or owned.get('.tag') != 'folder'
            or target.rsplit('/', 1)[0].casefold() != parent.casefold()):
        raise ValueError('The reserved product folder moved or is unavailable. Restore it to the selected sport folder before retrying.')
    updated = dict(saved, target=target)
    if saved.get('receipt'):
        updated['receipt'] = dict(saved['receipt'], destination=target)
    return updated
