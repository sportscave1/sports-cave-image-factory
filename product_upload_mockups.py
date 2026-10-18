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


def bind_export(connect, actor, result, kind, *, folder=''):
    import image_factory as factory
    factory.require_complete_product_image_manifest(result['product_image_manifest'])
    with Intakes(connect).locked(result['_product_upload_intake'], actor) as (row, cur):
        if row['data']['source']['content_hash'] != result['_product_upload_source_hash']:
            raise ValueError('Export belongs to a previous PSD; it cannot unlock this Shopify handoff.')
        row['data'].update(mockups_exported=True, mockups_context=dict(
            design_name=result['product_name'], sport_category=result['sport_category'],
            folder=folder, export_kind=kind,
            images=[dict(role=x['slot_id'], filename=x.get('output_filename',''))
                    for x in factory.product_image_manifest_json(result['product_image_manifest'])]))


def save(connect, actor, result, manifest, provider, parent, folder_name, conflict, perform):
    """Reserve a destination once, including the existing numbered-folder rule.

    The provider call never occurs under a long DB transaction. Failed/unknown
    transfers retry the exact destination and bytes, rather than drawing a new
    numbered folder. Existing standalone Mockups behaviour is unaffected.
    """
    import auto_editions as ae
    entries=[dict(name=x['archive_name'],hash=ae.file_hash(x['path'])) for x in manifest]
    fingerprint=hashlib.sha256(json.dumps([entries,parent,folder_name,conflict],sort_keys=True).encode()).hexdigest()
    store=Intakes(connect);key=result['_product_upload_intake'];api=provider.api
    with store.locked(key,actor) as (row,cur):
        if row['data']['source']['content_hash'] != result['_product_upload_source_hash']:
            raise ValueError('Selected mockups belong to a previous PSD.')
        saves=row['data'].setdefault('mockup_saves',{})
        old=saves.get(fingerprint)
        if old and old['state']=='Complete': return old['receipt']
        if old and old['state']=='Saving' and time.time()-old['started_at']<600:
            raise ValueError('This exact save is already running. Wait for its receipt before retrying.')
        if old: target=old['target']
        else:
            proposed=api.join_upload_path(parent,api.sanitize_path_component(folder_name,fallback='mockups'))
            existing=api.get_metadata_if_exists(provider.token,proposed)
            if existing and conflict=='cancel': return dict(cancelled=True,destination=proposed,successes=[],failures=[])
            if existing and existing.get('.tag')!='folder': raise ValueError('A file already uses this output name.')
            target=api.numbered_path(provider.token,proposed) if existing and conflict=='numbered' else proposed
        saves[fingerprint]=dict(state='Saving',target=target,started_at=time.time())
    try:
        receipt=perform(target)
    except Exception:
        with store.locked(key,actor) as (row,cur): row['data']['mockup_saves'][fingerprint]['state']='Failed'
        raise
    with store.locked(key,actor) as (row,cur):
        row['data']['mockup_saves'][fingerprint].update(state='Failed' if receipt.get('failures') else 'Complete',receipt=receipt)
    return receipt
