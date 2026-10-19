"""Product Upload presentation; standalone Mockups keeps its existing renderer."""
from pathlib import Path
from urllib.parse import quote
import hashlib
import streamlit as st


def asset_card(app,result,asset,source):
    from product_upload_gallery import register,render,preview_item
    uploaded=(result.get('product_upload_originals') or {}).get(asset.get('prompt_filename'),{})
    path=uploaded.get('path') or app.get_asset_full_resolution_path(asset)
    url=register(result,asset,source,path) if path else ''
    render(key='product-upload-image-'+result['_product_upload_intake']+'-'+asset['key'],
           items=[preview_item(asset.get('preview_path'),url,asset['label'])])


def core_preview_items(app,result,source):
    from product_upload_gallery import register,preview_item
    items=[]
    generated={a['key']:a for a in result['assets'] if a['asset_group']=='generated'}
    for key in ('black','oak','white','unframed','size-guide'):
        asset=generated.get(key)
        if not asset:continue
        path=app.get_asset_full_resolution_path(asset)
        url=register(result,asset,source,path) if path else ''
        items.append(preview_item(asset.get('preview_path'),url,asset['label']))
    return items


@st.fragment(run_every=.25)
def save_progress(app,key,actor):
    from product_upload_jobs import JOBS
    if st.session_state.get('_product_upload_active')!=key:return
    job=JOBS.snapshot(key,actor,'save')
    if not job:return
    if job['state'] in ('Queued','Running'):
        if job['total']:st.progress(min(1.,job['completed']/job['total']),text=job['stage'])
        else:st.info('Saving to Dropbox · '+job['stage'])
    elif job['state']=='Failed':
        st.error(job['error'])
        marker='product-upload-save-seen-'+key
        if st.session_state.get(marker)!=job['token']:
            st.session_state[marker]=job['token'];st.rerun()
    elif job['state']=='Ready':
        receipt=JOBS.result(key,actor,'save',job['token'])
        result=app._mockups_result()
        if not receipt or not result or result.get('_product_upload_intake')!=key:return
        if st.session_state.get('product-upload-save-applied-'+key)!=job['token']:
            st.session_state['product-upload-save-applied-'+key]=job['token']
            result['product_upload_save_receipt']=receipt
            app._set_mockups_result(result)
            st.rerun()


def save_controls(app,result,row,user,name):
    from product_upload_jobs import JOBS
    from product_upload_export import collection_root,product_folder,transfer
    from product_upload_api import connect,Dropbox
    key=str(row['id']);actor=user['id'];api=app.dropbox_integration
    job=JOBS.snapshot(key,actor,'save')
    running=bool(job and job['state'] in ('Queued','Running'))
    state='product-upload-save-picker-'+key
    try:folder=product_folder(api,name)
    except ValueError:folder=''
    if st.button('Save all',type='primary',disabled=running or not folder,key='product-upload-save-all-'+key):
        st.session_state[state]=True
        # Opening always starts at the configured collection root, never the last PSD folder.
        try:st.session_state['mockups-dropbox-picker-path::product-upload-'+key]=collection_root(api,app._files_team_root(app._files_access_token()))
        except Exception:st.error('Dropbox is unavailable. Check Files access and retry.');return
    if not folder:st.caption('Enter a valid Product name before saving.')
    if st.session_state.get(state):
        if not app.os_accounts.can_access_page(user,'Files'):
            st.error('Files access is required to save to Dropbox.');return
        try:
            token=app._files_access_token();root=app._files_team_root(token)
            base=collection_root(api,root)
            st.markdown('**Choose the destination sport collection**')
            parent=app._render_mockup_folder_picker(token,root,'product-upload-'+key)
            allowed=parent.rsplit('/',1)[0].casefold()==base.casefold() and api.path_is_within_root(parent,base)
            st.caption('Product folder: '+folder)
            manifest=app._mockup_dropbox_manifest(result,(app.ASSET_CATEGORY_CORE,app.ASSET_CATEGORY_PRODUCT,app.ASSET_CATEGORY_SOCIAL))
            if st.button('Save here',disabled=running or not allowed or not folder,key='product-upload-save-confirm-'+key):
                from copy import deepcopy
                scoped=deepcopy(result)
                scoped['_product_upload_source']=dict(row['data']['source'])
                fingerprint=hashlib.sha256(repr((scoped['_product_upload_source'],parent,folder,
                    [(x['archive_name'],str(x['path']),Path(x['path']).stat().st_mtime_ns) for x in manifest])).encode()).hexdigest()
                JOBS.submit(key,actor,'save',fingerprint,
                    lambda progress:transfer(Dropbox(),scoped,manifest,root,parent,folder,connect,actor,progress))
                st.rerun()
            if not allowed:st.caption('Select a sport collection inside product-images.')
            if st.button('Close destination picker',key='product-upload-save-close-'+key):
                st.session_state[state]=False;st.rerun(scope='fragment')
        except Exception:
            st.error('Dropbox destination could not be opened. Check Files access and retry.')
    if job:save_progress(app,key,actor)
    receipt=result.get('product_upload_save_receipt') or {}
    if receipt:
        if receipt.get('failures'):
            st.warning('Save incomplete. Retry Save all in the same collection; confirmed files are checked and skipped.')
            for failure in receipt['failures']:st.caption(failure['relative_path']+': '+failure['error'])
        elif receipt.get('successes'):
            st.success('Saved to Dropbox')
            st.link_button('Open folder','/?page=files&files_path='+quote(receipt['destination'],safe=''))


@st.fragment
def render_outputs(app,result,row,user,name):
    from product_upload_lifestyle import PROMPT_ID,INSTRUCTIONS,FILENAMES,LABELS,scene_texts,compose
    from product_upload_gallery import render,register
    from product_upload_jobs import JOBS
    latest=app._mockups_result()
    if latest and latest.get('run_dir')==result.get('run_dir'):result=latest
    key=str(row['id'])
    if st.session_state.get('_product_upload_active')!=key:return
    if result.get('_product_upload_intake')!=key or result.get('_product_upload_source_hash')!=row['data']['source']['content_hash']:return
    result=app.normalize_generation_result(result)
    result['_product_upload_source']=dict(row['data']['source'])
    app._set_mockups_result(result)
    source=row['data']['source']
    st.success('Mockups ready')
    st.subheader('Generated Previews')
    with st.container(key='product-upload-preview-row'):
        render(key='product-upload-previews-'+key,mode='gallery',items=core_preview_items(app,result,source))
    # Read existing Developer overrides, including legacy IDs, without migrating or
    # writing any shared prompt. Editing belongs exclusively in Developer Studio.
    specs=[dict(prompt_key=PROMPT_ID,default_text=INSTRUCTIONS)]
    for filename in FILENAMES:
        specs.extend(dict(prompt_key='lifestyle::'+suffix,default_text='')
                     for suffix in (app.prompt_key_from_prompt_filename(filename),filename))
    records=app.prompt_store.load_prompt_records(specs,module='lifestyle',force_supabase=True)
    instructions=records[PROMPT_ID]['text']
    warnings={r['warning'] for r in records.values() if r.get('warning')}
    if warnings:st.caption('Saved prompt storage is unavailable; defaults are shown. Reconnect before relying on saved customisations.')
    texts=scene_texts(result,app.current_lifestyle_prompt_text,
                     lambda filename,default:app.image_factory.get_lifestyle_prompt_text(filename,default,local_only=True))
    prompt=compose(instructions,texts)
    st.subheader('Product Page Lifestyle Mockups')
    st.caption('Paste the black frame and master prompt into ChatGPT. Create each mockup separately, then upload it to the matching card.')
    black=next((a for a in result['assets'] if a['key']=='black'),None)
    path=app.get_asset_full_resolution_path(black) if black else None
    url=register(result,black,source,path) if path else ''
    render(key='product-upload-copy-actions-'+key,original=url,prompt=prompt,mode='actions')
    pending=JOBS.snapshot(key,user['id'],'save')
    saving=bool(pending and pending['state'] in ('Queued','Running'))
    with st.container(key='mockups-lifestyle-grid'):
        for filename,label in zip(FILENAMES,LABELS):
            prompt_path=next((Path(p) for p in result['prompt_paths'] if Path(p).name==filename),None)
            if not prompt_path:continue
            with st.container(key='mockups-lifestyle-'+prompt_path.stem):
                st.markdown('**'+label+'**')
                uploaded=st.file_uploader('Upload image from ChatGPT',type=['png','jpg','jpeg','webp'],
                    key=f"lifestyle-upload::{result['run_dir']}::{filename}",disabled=saving)
                try:
                    if not saving:
                        before=app.get_lifestyle_upload_lifecycle(result,prompt_path).get('content_signature')
                        result=app.auto_register_lifestyle_upload(result,prompt_path,uploaded)
                        from product_upload_gallery import retain_upload_original
                        lifecycle=app.get_lifestyle_upload_lifecycle(result,prompt_path)
                        if uploaded is not None and lifecycle.get('status')=='SUCCEEDED':
                            result=retain_upload_original(result,filename,uploaded,lifecycle.get('content_signature'))
                            changed=before!=lifecycle.get('content_signature')
                            if changed:
                                result.pop('product_upload_save_receipt',None)
                                from product_upload_api import connect
                                from product_upload_intake import Intakes
                                with Intakes(connect).locked(key,user['id']) as (current,cur):
                                    current['data'].update(mockups_exported=False,mockups_context=None)
                            app._set_mockups_result(result)
                            if changed:st.rerun()
                except Exception as error:st.error(app._safe_lifestyle_upload_error(error))
                saved=result['lifestyle_mockup_paths'].get(filename)
                if saved:asset_card(app,result,app.build_lifestyle_asset(prompt_path,saved),source)
    result=app.normalize_generation_result(result)
    app._set_mockups_result(result)
    readiness=result['product_image_readiness']
    st.caption(f"{readiness['ready_count']} of {readiness['required_count']} product images ready")
    save_controls(app,result,row,user,st.session_state.get('product-upload-name-'+key,name))
