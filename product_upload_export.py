"""Background orchestration of the SAME Mockups manifest and Dropbox upload service."""
from pathlib import PurePosixPath
import logging


def product_folder(api, name):
    name=str(name or '').strip()
    if not name or not name.strip('. '):raise ValueError('Enter a Product name before saving.')
    clean=api.sanitize_path_component(name, fallback='')
    if not clean or not clean.strip('. '):raise ValueError('Enter a valid Product name before saving.')
    return clean


def collection_root(api, root):
    # Files resolves the configured team root/namespace; do not use a UI breadcrumb.
    return api.normalize_dropbox_path(root.rstrip('/')+'/04_OUTPUT/product-images')


def sport_categories(api, token, root):
    """All immediate output folders, using the authenticated team-space API."""
    base=collection_root(api,root)
    folders={};cursor='';seen=set()
    while True:
        page=api.list_folder_page(token,base,cursor=cursor)
        for entry in page.get('entries',()):
            path=api.normalize_dropbox_path(entry.get('path_display') or entry.get('path_lower') or '')
            if (entry.get('.tag')=='folder' and path.rsplit('/',1)[0].casefold()==base.casefold()
                    and api.path_is_within_root(path,base)):
                name=entry.get('name') or path.rsplit('/',1)[-1]
                folders[path.casefold()]=dict(id=entry.get('id'),path=path,name=name,sport=folder_sport(name))
        if not page.get('has_more'):break
        cursor=page.get('cursor')
        if not cursor or cursor in seen:raise ValueError('Dropbox folder listing is incomplete. Retry Save all.')
        seen.add(cursor)
    return sorted(folders.values(),key=lambda folder:(folder['name'].casefold(),folder['path']))


def folder_sport(name):
    import re
    from sports_categories import normalize_sport_category
    label=re.sub(r'\s+wall art$', '', name, flags=re.I).strip()
    # The shared taxonomy aliases Soccer to Football; these destinations must
    # remain distinct, including their product naming and export identity.
    return 'Soccer' if label.casefold()=='soccer' else normalize_sport_category(label,label)


def resolve_category(api, token, root, category_id):
    if not category_id:raise ValueError('Select a sport category above before continuing.')
    entry=api.get_metadata_if_exists(token,category_id)
    base=collection_root(api,root)
    path=api.normalize_dropbox_path((entry or {}).get('path_display') or (entry or {}).get('path_lower') or '')
    if (not entry or entry.get('id')!=category_id or entry.get('.tag')!='folder'
            or path.rsplit('/',1)[0].casefold()!=base.casefold() or not api.path_is_within_root(path,base)):
        raise ValueError('The selected sport folder is missing, inaccessible, or no longer directly inside product-images. Choose an available sport above.')
    name=entry.get('name') or path.rsplit('/',1)[-1]
    return dict(id=category_id,path=path,name=name,sport=folder_sport(name),root=root)


def transfer(provider, result, manifest, root, parent, folder, connect, actor, progress, *, conflict='numbered', category_id=None):
    from product_upload_mockups import save,bind_export
    import auto_editions as ae
    import mockup_storage
    api=provider.api
    # Product Uploads only: even a retained pre-release run must never transfer
    # its old JPG masters as new final assets. Source PSD storage is separate.
    manifest=[entry for entry in manifest if PurePosixPath(entry['archive_name']).parts[0]=='WEBP'
              and PurePosixPath(entry['archive_name']).suffix.casefold()=='.webp']
    if category_id and resolve_category(api,provider.token,root,category_id)['path']!=parent:
        raise ValueError('The sport folder changed before saving. Refresh the top selection and retry.')
    base=collection_root(api,root)
    parent=api.normalize_dropbox_path(parent)
    if parent.rsplit('/',1)[0].casefold()!=base.casefold() or not api.path_is_within_root(parent,base):
        raise ValueError('Select a sport collection inside product-images before saving.')
    selected=api.get_metadata_if_exists(provider.token,parent)
    if not selected or selected.get('.tag')!='folder':raise ValueError('The selected sport collection is no longer available.')
    clean=product_folder(api,folder)
    total=len(manifest)
    if not total:raise ValueError('No original outputs are ready to save.')

    def perform(target, previous, checkpoint):
        token=provider.token
        owned=previous.get('folder_id')
        if owned:
            current=api.get_metadata_if_exists(token,target)
            if not current or current.get('id')!=owned:raise ValueError('The reserved output folder changed. Choose a new destination; no files were overwritten.')
        else:
            # Atomic provider create, autorename=False. A racing creator causes a
            # recoverable conflict; never merge into an unowned folder.
            created=api.create_folder(token,str(PurePosixPath(target).parent),PurePosixPath(target).name,conflict='cancel')
            if not created or not created.get('id'):raise ValueError('Output destination conflicts with another folder. Choose another collection or product name.')
            checkpoint(folder_id=created['id'])
        successes={x['relative_path']:x for x in previous.get('confirmed',())}
        failures=[]
        for index,entry in enumerate(manifest,1):
            if category_id and resolve_category(api,provider.token,root,category_id)['path']!=parent:
                raise ValueError('The sport folder moved during saving. Refresh the top selection and retry; confirmed files are retained.')
            name=entry['archive_name']
            progress('Saving '+name,index-1,total)
            try:
                expected=ae.file_hash(entry['path'],dropbox=True)
                path=api.join_upload_path(target,name)
                remote=api.get_metadata_if_exists(token,path)
                if remote:
                    if remote.get('content_hash')!=expected or remote.get('size')!=entry['byte_length']:
                        raise ValueError('Destination file differs; it was not overwritten. Choose a new output folder.')
                    receipt=dict(relative_path=name,metadata=remote)
                else:
                    def on_bytes(_index,_total,_name,uploaded,size):
                        progress('Saving '+name,(index-1)+min(1,uploaded/size if size else 1),total)
                    uploaded=api.upload_batch(token,target,[dict(relative_path=name,local_path=entry['path'],size=entry['byte_length'])],
                        conflict='cancel',progress_callback=on_bytes,simple_limit=0,
                        chunk_size=mockup_storage.MOCKUP_DROPBOX_UPLOAD_CHUNK_SIZE)
                    if uploaded.get('failures') or len(uploaded.get('successes',()))!=1:
                        raise ValueError('Dropbox did not confirm this file. Retry Save all; confirmed files will be checked and skipped.')
                    receipt=uploaded['successes'][0]
                    remote=receipt.get('metadata') or {}
                    if remote.get('content_hash')!=expected or remote.get('size')!=entry['byte_length']:
                        raise ValueError('Dropbox verification did not match the original output. Retry to check the stored file.')
                successes[name]=receipt
                checkpoint(confirmed=list(successes.values()))
            except Exception as error:
                logging.getLogger(__name__).warning('product_upload_save_file_failed name=%s error_type=%s',name,type(error).__name__)
                failures.append(dict(relative_path=name,error=str(error) if isinstance(error,ValueError) else 'Dropbox transfer failed. Retry Save all.'))
            progress('Saving '+name,index,total)
        receipt = dict(destination=target,successes=list(successes.values()),failures=failures,cancelled=False)
        return receipt

    if conflict not in ('cancel','numbered'):raise ValueError('Choose a safe output-folder conflict option.')
    receipt=save(connect,actor,result,manifest,provider,parent,clean,conflict,perform,checkpointed=True,parent_identity=category_id)
    if not receipt.get('failures') and len(receipt.get('successes',()))==total:
        import image_factory
        if image_factory.product_image_readiness(result['product_image_manifest'])['complete']:
            from product_upload_source import receipt_source
            source = receipt_source(receipt, image_factory.product_image_manifest_json(result['product_image_manifest']))
            if not receipt.get('webp_folder'):
                # One exact metadata lookup, also for a completed save from an older release.
                # The product folder ID is not the WEBP folder ID.
                try:
                    folder_meta = api.get_metadata_if_exists(provider.token, source['folder_path'])
                except Exception:
                    folder_meta = None  # The confirmed exact path remains usable without an ID.
                if folder_meta and folder_meta.get('.tag') == 'folder' and folder_meta.get('id'):
                    actual = folder_meta.get('path_display') or folder_meta.get('path_lower')
                    if actual and actual.casefold() == source['folder_path'].casefold():
                        receipt['webp_folder'] = dict(path=source['folder_path'], id=folder_meta['id'])
                        from product_upload_intake import Intakes
                        with Intakes(connect).locked(result['_product_upload_intake'], actor) as (current, cur):
                            if (current['data'].get('mockup_save_token') != receipt['save_token'] or
                                    current['data'].get('mockup_save_fingerprint') != receipt['export_fingerprint']):
                                raise ValueError('A newer save operation replaced this destination.')
                            current['data']['mockup_saves'][receipt['export_fingerprint']]['receipt'] = receipt
            bind_export(connect,actor,result,'Dropbox',folder=receipt['destination'],export_fingerprint=receipt.get('export_fingerprint'))
    return receipt
