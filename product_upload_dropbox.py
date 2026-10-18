"""Product Upload selection using Files metadata and the shared Mockups renderer.

Review's path was verified against the local team-folder tree on 19 Oct 2026.
The label does not rename the real folder or relax the main-master rules.
"""
import hashlib
import json
import uuid
from pathlib import Path, PurePosixPath
from datetime import datetime, timezone
from product_upload_intake import Intakes, mode, MAX_BYTES
import psd_directory

REVIEW = psd_directory.ROOT + '/99_PSD_NEEDS_REVIEW_DO_NOT_DELETE'
ROOTS = {'review': REVIEW, 'live': psd_directory.ROOT}


def within(path, root):
    return path.casefold() == root.casefold() or path.casefold().startswith(root.casefold() + '/')


def approved(metadata):
    path = metadata.get('path_display', '')
    return bool(metadata.get('.tag') == 'file' and path.lower().endswith('.psd')
                and PurePosixPath(path).name == metadata.get('name')
                and within(path, psd_directory.ROOT)
                and str(metadata.get('id', '')).startswith('id:'))


def verify_roots(provider):
    roots = {}
    for key, path in ROOTS.items():
        meta = provider.metadata_if_present(path)
        if not meta or meta.get('.tag') != 'folder' or not meta.get('id'):
            raise ValueError('The configured ' + key + ' folder is unavailable. Check Files; no folder was created.')
        resolved = provider.metadata_if_present(meta['id'])
        if not resolved or resolved.get('id') != meta['id'] or resolved.get('path_display', '').casefold() != path.casefold():
            raise ValueError('Dropbox folder identity changed. Review its configuration before continuing.')
        roots[key] = dict(id=meta['id'], path=resolved['path_display'])
    return roots


def browse(provider, actor, root='review', path='', page='', search=''):
    import files_upload_api as files
    roots = verify_roots(provider)
    if root not in roots: raise ValueError('Choose Review or Designs Live.')
    base = roots[root]['path']; path = path or base
    meta = provider.metadata_if_present(path)
    if not meta or meta.get('.tag') != 'folder' or not within(meta.get('path_display', ''), base):
        raise ValueError('Choose a folder inside the selected Dropbox area.')
    path = meta['path_display']
    result = files._directory_page(provider.token, path, root_path=provider.context['root_path'],
                                   user_id=str(actor), page_token=page, limit=100, bounded=True)
    # Search covers metadata in each loaded page; Load more continues the search.
    entries = [m for m in result['entries'] if (m.get('.tag') == 'folder' or approved(m))
               and str(search).casefold() in m.get('name', '').casefold()]
    return dict(roots=roots, root=root, path=path, items=[{k:m.get(k) for k in
                ('.tag','id','rev','content_hash','name','path_display','size')} for m in entries],
                next_page=result.get('page_token', ''), has_more=result['has_more'])


def select(connect, provider, key, actor, selected_mode, file_id, revision):
    import auto_editions as ae
    mode(selected_mode); key = str(uuid.UUID(key)); verify_roots(provider)
    meta = provider.metadata_if_present(file_id)
    if not meta or meta.get('id') != file_id or meta.get('rev') != revision or not approved(meta):
        raise ValueError('The selected PSD changed or moved. Refresh the picker and select its current revision.')
    ae.source_identity('gid://shopify/Product/1', meta)
    if type(meta.get('size')) is not int or not 40 <= meta['size'] <= MAX_BYTES:
        raise ValueError('Choose a layered PSD up to 1 GiB.')
    store = Intakes(connect)
    with connect() as conn, conn.cursor() as cur:
        cur.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', ('product-upload:' + key,))
        cur.execute('SELECT * FROM product_upload_intakes WHERE id=%s', (key,))
        old = cur.fetchone()
        if old:
            if old['actor_id'] != str(actor) or old['data'].get('source') != meta or old['mode'] != selected_mode:
                raise ValueError('This selection belongs to a different workflow. Choose the PSD again.')
        else:
            data = dict(workflow_version=3, source=meta, name=meta['name'], size=meta['size'], offset=meta['size'],
                        content_hash=meta['content_hash'], basic_validated=True, copied=False,
                        selected_at=datetime.now(timezone.utc).isoformat(), state='Selected', server_artwork=dict(state='Selected'))
            cur.execute('INSERT INTO product_upload_intakes(id,actor_id,mode,data) VALUES(%s,%s,%s,%s::jsonb)',
                        (key, str(actor), selected_mode, json.dumps(data)))
    return store.read(key, actor)


def validate_structure(path):
    """Seek only PSD framing, reusing the original RGB8/layer/pixel safeguards."""
    from product_upload_intake import inspect_chunk
    state = {'stage':0,'at':0,'carry':''}; size = Path(path).stat().st_size
    with Path(path).open('rb') as source:
        while state['stage'] < 5:
            offset = state['at']; source.seek(offset); block = source.read(65536)
            if not block: raise ValueError('The selected PSD is truncated.')
            state = inspect_chunk(state,block,offset,size)
    return state['document']


def status(row, connect):
    d=row['data'];spec=d.get('server_artwork') or {}
    # Old Companion jobs are historical checkpoints only. A Dropbox workflow
    # must use the server adapter even if it was selected before this correction.
    if not spec:
        spec=dict(state='Selected');d['server_artwork']=spec
    d['state']={'Selected':'Selected','Preparing':'Preparing','Ready':'Ready','Failed':'Error'}.get(spec.get('state'),'Selected')
    d['reason']=spec.get('reason','')
    if d.get('product_gid'):d['state']='Shopify confirmed'
    d['preview_url']='/api/product-uploads/source-preview?id='+str(row['id'])+('&prepared='+spec['settings'] if spec.get('state')=='Ready' else '')
    return row
