"""Product Upload presentation; standalone Mockups keeps its existing renderer."""
from pathlib import Path
import hashlib
import streamlit as st


def package_stamp(source, category, name, manifest):
    return hashlib.sha256(repr((source, category, name,
        [(x['archive_name'], str(x['path']), Path(x['path']).stat().st_size,
          Path(x['path']).stat().st_mtime_ns) for x in manifest])).encode()).hexdigest()


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


def render_save_progress(app,key,actor,*,core=False):
    from product_upload_jobs import JOBS
    if st.session_state.get('_product_upload_active')!=key:return
    job=JOBS.snapshot(key,actor,'save')
    if not job:return
    if job['state'] in ('Queued','Running'):
        if core:
            fraction=min(1.,job['completed']/job['total']) if job['total'] else 0.
            st.progress(.5+.35*fraction,text='Saving generated mockups to Dropbox · '+job['stage'])
        elif job['total']:st.progress(min(1.,job['completed']/job['total']),text=job['stage'])
        else:st.caption('Saving… · '+job['stage'])
    elif job['state']=='Failed':
        st.caption('Save failed · '+job['error'])
        marker='product-upload-save-seen-'+key
        if st.session_state.get(marker)!=job['token']:
            st.session_state[marker]=job['token'];st.rerun()
    elif job['state']=='Ready':
        receipt=JOBS.result(key,actor,'save',job['token'])
        result=app._mockups_result()
        if not receipt or not result or result.get('_product_upload_intake')!=key:return
        if st.session_state.get('product-upload-save-applied-'+key)==job['token']:
            if core and result.get('product_upload_core_receipt')==receipt:
                if receipt.get('cancelled') or receipt.get('failures'):
                    st.caption('Mockups generated · Dropbox save needs attention below.')
                elif len(receipt.get('successes',()))==5 and not receipt.get('generation_receipt'):
                    st.progress(1.,text='Mockups generated and saved to Dropbox')
            return
        from product_upload_api import connect
        from product_upload_intake import Intakes
        current=Intakes(connect).read(key,actor)
        if not current or receipt.get('save_token')!=current['data'].get('mockup_save_token'):
            st.session_state['product-upload-save-applied-'+key]=job['token']
            return
        if st.session_state.get('product-upload-save-applied-'+key)!=job['token']:
            st.session_state['product-upload-save-applied-'+key]=job['token']
            receipt_key = 'product_upload_core_receipt' if receipt.get('core_only') else 'product_upload_save_receipt'
            result[receipt_key]=receipt
            app._set_mockups_result(result)
            st.rerun()


save_progress = st.fragment(run_every=.25)(render_save_progress)


def save_controls(app,result,row,user,name,*,generation_receipt=None):
    from product_upload_chat_handoff import CORE
    from product_upload_jobs import JOBS
    from product_upload_export import product_folder,resolve_category,transfer
    from product_upload_sport import selected,state_key,rebind_result
    from product_upload_api import connect,Dropbox
    key=str(row['id']);actor=user['id'];api=app.dropbox_integration
    job=JOBS.snapshot(key,actor,'save')
    running=bool(job and job['state'] in ('Queued','Running'))
    core_job=bool(job and job.get('token') and job['token']==st.session_state.get('product-upload-core-save-job-'+key))
    choice=selected(key)
    try:folder=product_folder(api,name)
    except ValueError:folder=''
    permitted=app.os_accounts.can_access_page(user,'Files')
    destination=st.session_state.get(state_key(key)+'-saving-destination') if running else None
    receipt=result.get('product_upload_save_receipt') or {}
    numbering_key='product-upload-save-numbered-'+key
    numbering_context=(choice['id'] if choice else None,folder)
    if st.session_state.get(numbering_key+'-context')!=numbering_context:
        st.session_state[numbering_key]=False
        st.session_state[numbering_key+'-context']=numbering_context
    numbered=st.session_state.get(numbering_key,False)
    manifest=app._mockup_dropbox_manifest(result,(app.ASSET_CATEGORY_CORE,app.ASSET_CATEGORY_PRODUCT,app.ASSET_CATEGORY_SOCIAL))
    core_manifest=[entry for entry in manifest if entry.get('product_slot_id') in CORE]
    core_ready=(len(core_manifest)==len(CORE) and all(Path(entry['path']).is_file() for entry in core_manifest))
    core_stamp=package_stamp(row['data']['source'],choice['id'],name,core_manifest) if core_ready and choice else ''
    core_receipt=result.get('product_upload_core_receipt') or {}
    if core_receipt.get('package_stamp')!=core_stamp:
        core_receipt={}
    core_saved=bool(core_receipt and not core_receipt.get('cancelled') and not core_receipt.get('failures')
                    and len(core_receipt.get('successes',()))==len(CORE))
    ready=bool(result.get('product_image_readiness',{}).get('complete') and manifest
        and all(Path(entry['path']).is_file() for entry in manifest))
    stamp=package_stamp(row['data']['source'],choice['id'] if choice else '',name,manifest) if ready else ''
    saved=bool(stamp and receipt.get('package_stamp')==stamp and not receipt.get('failures')
               and not receipt.get('cancelled') and len(receipt.get('successes',()))==len(manifest))
    with st.container(key='product-upload-save-destination'):
        if saved:st.caption('Saving to: '+' / '.join(receipt['destination'].rstrip('/').split('/')[-2:]))
        elif core_saved:st.caption('Saving to: '+' / '.join(core_receipt['destination'].rstrip('/').split('/')[-2:]))
        elif destination:st.caption('Saving to: '+destination)
        elif choice:st.caption('Dropbox destination: '+choice['name']+' / '+(folder or 'Enter Product name'))
    if receipt and not saved and not running and receipt.get('successes') and not receipt.get('failures'):
        result.pop('product_upload_save_receipt',None)
        app._set_mockups_result(result)
        from product_upload_intake import Intakes
        with Intakes(connect).locked(key,actor) as (current,cur):
            from product_upload_source import invalidate
            invalidate(current)
        st.rerun()
    if not folder:st.caption('Enter a valid Product name before saving.')
    disabled=running or not folder or not permitted or not choice or not ready
    with st.container(horizontal=True,vertical_alignment='center',gap='small'):
        save_requested=st.button('Save all',type='primary',disabled=disabled,
                     key='product-upload-save-all-'+key)
        if running and not core_job:st.caption('Saving…')
        elif saved:st.markdown(':green[✓ Saved]')
        elif job and job['state']=='Failed' and not core_job:st.caption('Save failed · retry Save all')
    if receipt.get('cancelled') and not running:
        st.warning('That product folder already exists. Save in a numbered folder or change Product name. Nothing was overwritten.')
        if st.button('Save in a numbered folder',disabled=disabled,key='product-upload-save-numbered-retry-'+key):
            numbered=True;st.session_state[numbering_key]=True;save_requested=True
    approved = (row['data'].get('design_review') or {}).get('decision') == 'approved'
    auto_key = 'product-upload-auto-save-'+key
    if (approved and stamp and not disabled and not saved and not row['data'].get('mockups_exported')
            and st.session_state.get(auto_key) != stamp):
        st.session_state[auto_key] = stamp
        numbered = True
        save_requested = True
    core_requested=False
    if generation_receipt and choice and permitted and not core_ready and not running:
        st.warning('Dropbox save needs all five generated WebPs. Generate the mockups again to replace missing files.')
    if generation_receipt and core_stamp and folder and permitted and not running and not saved and not core_saved and not save_requested:
        attempt_key='product-upload-auto-core-save-'+key
        # Remember the attempt across polling reruns. Recoverable failures use the same save worker.
        if st.session_state.get(attempt_key)!=generation_receipt:
            st.session_state[attempt_key]=generation_receipt
            core_requested=True
        elif core_receipt.get('cancelled'):
            st.warning('That product folder already exists. Use a different Product name or save in a numbered folder.')
            if st.button('Save core WebPs in a numbered folder',key='product-upload-numbered-core-'+key):
                numbered=True
                st.session_state[numbering_key]=True
                core_requested=True
        else:
            if core_receipt.get('failures'):
                st.caption('Core save incomplete. Retrying checks and skips files already confirmed.')
            core_requested=st.button('Retry core WebP save',key='product-upload-retry-core-'+key)
    if save_requested or core_requested:
        from copy import deepcopy
        try:
            token=app._files_access_token();root=app._files_team_root(token)
            resolved=resolve_category(api,token,root,choice['id'])
        except Exception:
            st.session_state[state_key(key)+'-error']='The selected sport folder is missing, inaccessible, or moved. Select an available sport from the reloaded choices above; nothing was saved.'
            st.session_state.pop(state_key(key)+'-folders',None)
            st.session_state.pop(state_key(key)+'-resolved',None)
            st.rerun()
        try:
            # Capture identity, resolved destination, naming and original asset
            # paths together. Worker progress never reads mutable UI state.
            scoped=deepcopy(rebind_result(app,result,name,resolved))
            scoped['_product_upload_source']=dict(row['data']['source'])
            manifest=deepcopy(app._mockup_dropbox_manifest(scoped,(app.ASSET_CATEGORY_CORE,app.ASSET_CATEGORY_PRODUCT,app.ASSET_CATEGORY_SOCIAL)))
            if core_requested:
                manifest=[entry for entry in manifest if entry.get('product_slot_id') in CORE]
            parent=resolved['path'];category_id=resolved['id']
            conflict='numbered' if numbered else 'cancel'
            # Manual Save all continues the exact folder reserved by the core save.
            extend_core=None
            if not core_requested and core_receipt.get('product_folder_id'):
                extend_core=core_receipt['export_fingerprint']
            options=dict(conflict=conflict,category_id=category_id)
            if core_requested:
                options.update(core_only=True,number_on_conflict=approved)
            if extend_core:options['extend_core']=extend_core
            fingerprint=hashlib.sha256(repr((scoped['_product_upload_source'],category_id,parent,folder,conflict,
                [(x['archive_name'],str(x['path']),Path(x['path']).stat().st_mtime_ns) for x in manifest])).encode()).hexdigest()
            stamp=package_stamp(row['data']['source'],category_id,name,manifest)
            from product_upload_intake import Intakes
            with Intakes(connect).locked(key,actor) as (current,cur):
                from product_upload_source import invalidate
                invalidate(current)
                scoped['_product_upload_save_token']=current['data']['mockup_save_token']
            def work(progress):
                receipt=transfer(Dropbox(),scoped,manifest,root,parent,folder,connect,actor,progress,**options)
                return dict(receipt,package_stamp=stamp,core_only=core_requested,
                            generation_receipt=generation_receipt if core_requested else None)
            queued=JOBS.submit(key,actor,'save',fingerprint,work)
            if core_requested:
                st.session_state['product-upload-core-save-job-'+key]=queued['token']
            st.session_state[state_key(key)+'-saving-destination']=resolved['name']+' / '+folder
            scoped.pop('product_upload_core_receipt' if core_requested else 'product_upload_save_receipt',None)
            app._set_mockups_result(scoped)
            st.rerun()
        except Exception as error:
            st.error(str(error) if isinstance(error,ValueError) else 'Save could not start. Your sport selection and images are retained; retry Save all.')
    if job and not core_job:save_progress(app,key,actor)
    receipt=result.get('product_upload_save_receipt') or {}
    if receipt and not running:
        if receipt.get('failures'):
            st.caption('Save incomplete. Retry Save all; confirmed files are checked and skipped.')
            for failure in receipt['failures']:st.caption(failure['relative_path']+': '+failure['error'])


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
    from product_upload_generation_status import status
    from product_upload_sport import selected
    choice=selected(key)
    pending=JOBS.snapshot(key,user['id'],'save')
    saving=bool(pending and pending['state'] in ('Queued','Running'))
    generation=st.session_state.get('product-upload-generation-ack-'+key)
    preview_receipt=None
    if choice and generation:
        state,receipt=status(generation,JOBS.snapshot(key,user['id'],'generate'),
                             st.session_state.get('product-upload-job-applied-'+key),
                             result,key,name,choice['sport'],source['content_hash'])
        if state=='ready':preview_receipt=receipt
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
                     lambda filename,default:app.get_image_factory().get_lifestyle_prompt_text(filename,default,local_only=True))
    prompt=compose(instructions,texts)
    black=next((a for a in result['assets'] if a['key']=='black'),None)
    path=app.get_asset_full_resolution_path(black) if black else None
    url=register(result,black,source,path) if path else ''
    handoff={'pending': True}
    core_receipt=result.get('product_upload_core_receipt') or {}
    core_saved = (len(core_receipt.get('successes', ())) == 5
                  and not core_receipt.get('cancelled') and not core_receipt.get('failures'))
    if core_saved and not saving:
        try:
            from product_upload_chat_handoff import CORE,prepare
            manifest=app._mockup_dropbox_manifest(result,(app.ASSET_CATEGORY_CORE,))
            manifest=[entry for entry in manifest if entry.get('product_slot_id') in CORE]
            if not choice or core_receipt.get('package_stamp')!=package_stamp(source,choice['id'],name,manifest):
                raise ValueError('The confirmed Dropbox save belongs to earlier product details.')
            if warnings:
                raise ValueError('Saved prompt storage is unavailable. Refresh Product Uploads to retry the handoff.')
            handoff=prepare(result,row,core_receipt,prompt)
        except ValueError as error:
            handoff={'error': str(error)}
        except Exception:
            handoff={'error': 'Upload needs all five WebPs confirmed in Dropbox.'}
    automatic_handoff = bool(handoff.get('automatic') and handoff.get('prompt'))
    staff_job = st.query_params.get('staff_upload_job')
    if staff_job:
        from product_upload_staff_queue import advance
        failure = handoff.get('error')
        if core_receipt.get('cancelled') or core_receipt.get('failures'):
            failure = 'Dropbox did not confirm all five core WebPs. Review the save details in Product Uploads.'
        if failure:
            advance(staff_job, user['id'], 7, failure, allowed=[1, 2, 3, 4])
        elif automatic_handoff:
            advance(staff_job, user['id'], 4, allowed=[1, 2, 3, 4])
            handoff['staff_job'] = staff_job
            handoff['prompt'] += (
                '\n\nIf the workflow pauses, place a line at the end of your response with '
                'exactly one of these applicable statuses: SC_UPLOAD_BLOCKED: REFERENCE, '
                'SC_UPLOAD_BLOCKED: GENERATION, SC_UPLOAD_BLOCKED: DROPBOX, '
                'SC_UPLOAD_BLOCKED: SHOPIFY, SC_UPLOAD_BLOCKED: EDITION_SYNC, '
                'SC_UPLOAD_BLOCKED: PSD_MOVE, SC_UPLOAD_BLOCKED: PSD_MAPPING, or '
                'SC_UPLOAD_BLOCKED: APPROVAL. Explain the pending action above that line.'
            )
    if core_saved and not saving and core_receipt.get('generation_receipt'):
        if handoff.get('error'):
            st.progress(.85,text='Mockups saved to Dropbox · ChatGPT handoff needs attention')
            st.warning(handoff['error'])
        elif automatic_handoff:
            render(key='product-upload-copy-actions-'+key,original=url,prompt=prompt,mode='handoff',handoff=handoff)
    st.success('Mockups ready')
    st.subheader('Generated Previews')
    with st.container(key='product-upload-preview-row'):
        render(key='product-upload-previews-'+key,mode='gallery',items=core_preview_items(app,result,source))
    with st.container(key='product-upload-lifestyle-actions'):
        st.html('''<style>
        .st-key-product-upload-lifestyle-actions {gap:10px!important;}
        .product-upload-lifestyle-intro h3 {margin:0!important;padding:0!important;line-height:1.35!important;}
        .product-upload-lifestyle-intro p {margin:7px 0 0!important;padding:0!important;font-size:12px;line-height:1.4!important;overflow-wrap:anywhere;}
        </style><div class="product-upload-lifestyle-intro">
        <h3>Product Page Lifestyle Mockups</h3>
        <p>Paste the black frame and master prompt into ChatGPT. Create each mockup separately, then upload it to the matching card.</p>
        </div>''')
        if not automatic_handoff:
            render(key='product-upload-copy-actions-'+key,original=url,prompt=prompt,mode='actions',handoff=handoff)
    with st.container(key='mockups-lifestyle-grid'):
        for filename,label in zip(FILENAMES,LABELS):
            prompt_path=next((Path(p) for p in result['prompt_paths'] if Path(p).name==filename),None)
            if not prompt_path:continue
            with st.container(key='mockups-lifestyle-'+prompt_path.stem):
                st.markdown('**'+label+'**')
                uploaded=st.file_uploader(f'Upload {label} image from ChatGPT',type=['png','jpg','jpeg','webp'],
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
                                    from product_upload_source import invalidate
                                    invalidate(current)
                            app._set_mockups_result(result)
                            if changed:st.rerun()
                except Exception as error:st.error(app._safe_lifestyle_upload_error(error))
                saved=result['lifestyle_mockup_paths'].get(filename)
                if saved:asset_card(app,result,app.build_lifestyle_asset(prompt_path,saved),source)
    result=app.normalize_generation_result(result)
    app._set_mockups_result(result)
    readiness=result['product_image_readiness']
    st.caption(f"{readiness['ready_count']} of {readiness['required_count']} product images ready")
    save_controls(app,result,row,user,st.session_state.get('product-upload-name-'+key,name),
                  generation_receipt=preview_receipt)
