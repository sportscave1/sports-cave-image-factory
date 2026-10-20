"""Continuous Product Uploads shell around the original Mockups renderer."""
import sys
import uuid
import base64
from functools import lru_cache
from pathlib import Path
import streamlit as st


def render_page(app):
    from product_upload_api import connect
    from product_upload_intake import Intakes
    user=app.current_os_user()
    # Install before component/database reads so reruns retain readable content.
    st.html('<style>'+(app.BASE_DIR/'mockups_page.css').read_text(encoding='utf-8')+
            (app.BASE_DIR/'product_upload_page.css').read_text(encoding='utf-8')+
            '</style><span class="product-upload-page-marker" aria-hidden="true"></span>')
    if '_product_upload_visit' not in st.session_state: st.session_state['_product_upload_visit']=uuid.uuid4().hex
    visit=st.session_state['_product_upload_visit']
    component=app.get_components_module().declare_component('product_uploads_workflow',path=str(app.BASE_DIR/'components/product_uploads'))
    resume=None
    requested=st.query_params.get('upload')
    if requested and st.session_state.get('_product_upload_resume_seen')!=requested:
        st.session_state['_product_upload_resume_seen']=requested
        try:
            resume=Intakes(connect).read(str(uuid.UUID(requested)),user['id'])
            if not resume:raise ValueError('Saved upload unavailable to this account.')
        except ValueError as error:
            st.error(str(error))
        # A Sync & Map URL retains only the operation ID across browser refresh.
        # Other existing recovery links remain one-shot; new uploads clear both.
        if st.query_params.get('sync_map')!='1':st.query_params.pop('upload',None)
    event=component(section='upload',**(dict(id=str(resume['id']),mode=resume['mode']) if resume else {}),
                    refresh=st.session_state.get('_product_upload_linked',''),key='product-upload-input-'+visit,default=None)
    if event and event.get('nonce')!=st.session_state.get('_product_upload_event'):
        previous=st.session_state.get('_product_upload_active')
        st.session_state['_product_upload_event']=event['nonce']
        st.session_state['_product_upload_active']=event.get('id')
        st.session_state['_product_upload_manual']=bool(event.get('manual'))
        st.session_state['_product_upload_mode']=event.get('mode','LIVE')
        st.session_state['_product_upload_visible']=event.get('visible',True)
        if previous!=event.get('id'):
            if st.query_params.get('upload')!=event.get('id'):
                st.query_params.pop('upload',None)
                st.query_params.pop('sync_map',None)
            from product_upload_sport import clear_selection
            clear_selection(previous)
            clear_selection(event.get('id'))
            from product_upload_gallery import revoke
            revoke(previous,user['id'])
            from product_upload_jobs import JOBS
            JOBS.cancel(previous,user['id'])
            from product_upload_mockups import release_transient
            release_transient(st.session_state.get('_product_upload_mockups_result'))
            st.session_state.pop('_product_upload_mockups_result',None)
    key=st.session_state.get('_product_upload_active')
    manual=st.session_state.get('_product_upload_manual',False)
    if manual:
        return
    if not key: return
    row=Intakes(connect).read(key,user['id'])
    if row and row['data'].get('workflow_version') == 3:
        from product_upload_dropbox import status
        row = status(row, connect)
    if not row or not row['data'].get('basic_validated'): return
    with st.container(key='product-upload-workspace'):
        with st.container(key='mockups-workspace'):
            render_design(app,row,user)
    # Do not mount a second workflow iframe (polling, mapping, preview effects)
    # until this product's complete Save All result is current. A CSS hide still
    # runs those effects and competed with PSD preparation in the last release.
    row=Intakes(connect).read(key,user['id'])
    if not row or not row['data'].get('mockups_exported'):return
    from product_upload_jobs import JOBS
    if any((JOBS.snapshot(key,user['id'],operation) or {}).get('state') in ('Queued','Running')
           for operation in ('prepare','generate','save')):return
    from product_upload_intake import public
    state=public(row)
    if not state.get('saved_source_version'):return
    linked=component(section='handoff',id=key,mode=row['mode'],source_version=state['saved_source_version'],key='product-upload-handoff-'+visit+'-'+key,default=None)
    if linked and linked.get('id')==key and linked.get('linked') and linked.get('nonce')!=st.session_state.get('_product_upload_linked'):
        st.session_state['_product_upload_linked']=linked['nonce']
        st.rerun()


@st.fragment(run_every=0.25)
def poll_render(key, actor, state):
    from product_upload_jobs import JOBS
    if st.session_state.get('_product_upload_active')!=key:return
    job=JOBS.snapshot(key,actor,'prepare')
    marker='product-upload-prepare-seen-'+key
    if job and job['state'] in ('Ready','Failed') and st.session_state.get(marker)!=job['token']:
        st.session_state[marker]=job['token']
        st.rerun()


@lru_cache(maxsize=80)
def progress_preview(path):
    return base64.b64encode(Path(path).read_bytes()).decode('ascii')


# Leave time for progress paint/terminal result hydration between fragment ticks.
@st.fragment(run_every=1.0)
def poll_generation(app,key,actor,name,sport,source_hash):
    from product_upload_jobs import JOBS
    if st.session_state.get('_product_upload_active')!=key:return
    job=JOBS.snapshot(key,actor,'generate')
    if not job:return
    if job['state'] in ('Queued','Running'):
        if job['total']:
            st.progress(job['completed']/job['total'],text=f"Generating mockups · {job['completed']} of {job['total']}")
        else:
            st.caption('Generating mockups · '+job['stage'])
            st.html('<progress aria-label="Mockup generation progress" style="width:100%;height:7px;accent-color:#b08b40"></progress>')
        if job['previews']:
            # Existing tiny preview bytes, cached once; no repeated PIL resize
            # or full-resolution artwork delivery on every progress tick.
            st.html('<div style="display:flex;flex-wrap:wrap;gap:8px">'+''.join(
                '<img alt="Completed mockup preview" width="140" src="data:image/webp;base64,'+progress_preview(path)+'">'
                for path in job['previews'])+'</div>')
    elif job['state']=='Failed':
        marker='product-upload-generation-seen-'+key
        if st.session_state.get(marker)!=job['token']:
            st.session_state[marker]=job['token'];st.rerun()
        st.error(job['error'])
    elif job['state']=='Ready':
        result=JOBS.result(key,actor,'generate',job['token'])
        if not result or result.get('_product_upload_source_hash')!=source_hash:return
        if result['product_name']!=name.strip() or result['sport_category']!=sport:
            marker='product-upload-generation-seen-'+key
            if st.session_state.get(marker)!=job['token']:
                st.session_state[marker]=job['token'];st.rerun()
            st.info('Product details changed during generation. Generate mockups again for the current details.');return
        if st.session_state.get('product-upload-job-applied-'+key)==job['token']:return
        st.session_state['product-upload-job-applied-'+key]=job['token']
        app._set_mockups_result(app.normalize_generation_result(result))
        st.rerun()


@st.fragment
def render_design(app,row,user):
    from product_upload_api import connect,Dropbox
    from product_upload_intake import Intakes
    from product_upload_jobs import JOBS,generate,prepare
    key=str(row['id'])
    if st.session_state.get('_product_upload_active')!=key:return
    result=app._mockups_result()
    if result and result.get('_product_upload_intake')!=key:
        app._set_mockups_result(None);result=None
    st.subheader('Prepare product images')
    from product_upload_sport import render_selector,selected,rebind_result
    active_jobs=[JOBS.snapshot(key,user['id'],operation) for operation in ('generate','save')]
    busy=any(job and job['state'] in ('Queued','Running') for job in active_jobs)
    with st.container(key='product-upload-details'):
        with st.container(key='product-upload-detail-name'):
            saved_name=(row['data'].get('mockups_context') or {}).get('design_name')
            name=st.text_input('Product name',value=saved_name or Path(row['data']['name']).stem,key='product-upload-name-'+key,disabled=busy)
        with st.container(key='product-upload-detail-sport'):
            choice=render_selector(app,key,user,disabled=busy)
    sport=choice['sport'] if choice else ''
    if result and choice and not busy:
        updated=rebind_result(app,result,name,choice)
        if updated is not result:
            with Intakes(connect).locked(key,user['id']) as (current,cur):
                from product_upload_source import invalidate
                invalidate(current)
            result=updated;app._set_mockups_result(result)
            st.rerun()
    if row['data'].get('workflow_version')!=3:
        st.info('Choose a Dropbox PSD for server preparation. This saved legacy workflow is retained.');return
    spec=row['data'].get('server_artwork') or {}
    pending=JOBS.snapshot(key,user['id'],'generate')
    running=bool(pending and pending['state'] in ('Queued','Running'))
    saving=JOBS.snapshot(key,user['id'],'save')
    running=running or bool(saving and saving['state'] in ('Queued','Running'))
    def queue_generation():
        if spec.get('state')!='Ready' or running or st.session_state.get('_product_upload_active')!=key:return
        active_save=JOBS.snapshot(key,user['id'],'save')
        if active_save and active_save['state'] in ('Queued','Running'):return
        selected_name=st.session_state.get('product-upload-name-'+key,name).strip()
        selection=selected(key)
        if selection:
            from product_upload_export import resolve_category
            from product_upload_sport import state_key
            try:
                token=app._files_access_token()
                selection=resolve_category(app.dropbox_integration,token,app._files_team_root(token),selection['id'])
            except Exception:
                st.session_state[state_key(key)+'-error']='The selected sport folder is unavailable. Select an available sport from the reloaded choices before generating.'
                st.session_state.pop(state_key(key)+'-folders',None)
                st.session_state.pop(state_key(key)+'-resolved',None)
                return
        selected_sport=selection['sport'] if selection else ''
        if not selected_name or not selected_sport:return
        if result and result['product_name']==selected_name and result['sport_category']==selected_sport:
            st.session_state['product-upload-generation-focus-'+key]=uuid.uuid4().hex
            return
        if row['data'].get('product_gid'):
            st.session_state['product-upload-job-error-'+key]='This PSD is already linked to Shopify. Start a separate design workflow.';return
        if result:
            from product_upload_mockups import release_transient
            release_transient(result);app._set_mockups_result(None)
        try:
            def finalize(result):
                result=app.ensure_lifestyle_prompts(result)
                return app.rebuild_result_artifacts(result)
            generate(connect,row,user['id'],selected_name,selected_sport,Dropbox,app.BASE_DIR,
                app.MOCKUPS_GENERATION_SEMAPHORE,app.build_mockup_final_prompt_items,reset_exports=bool(result),finalize=finalize)
            st.session_state['product-upload-generation-focus-'+key]=uuid.uuid4().hex
            st.session_state.pop('product-upload-job-error-'+key,None)
        except Exception as error:st.session_state['product-upload-job-error-'+key]=str(error)
    st.button('Generate mockups',type='primary',key='product-upload-generate-'+key,on_click=queue_generation,
        disabled=running or not name.strip() or not sport or spec.get('state')!='Ready')
    if st.session_state.get('product-upload-job-error-'+key):st.error(st.session_state['product-upload-job-error-'+key])
    preparing=JOBS.snapshot(key,user['id'],'prepare')
    if spec.get('state')!='Ready':
        if preparing and preparing['state']=='Failed':st.error(preparing['error'])
        elif spec.get('state')=='Failed':st.error(spec.get('reason') or 'Artwork preparation failed. Retry preparation; the original and workflow are retained.')
        else:st.info('Downloading/preparing the original PSD. Generate mockups will be enabled when artwork is ready.')
        if st.button('Retry artwork preparation' if spec.get('state')=='Failed' else 'Prepare artwork',key='product-upload-artwork-retry-'+key,
                     disabled=bool(preparing and preparing['state'] in ('Queued','Running'))):
            try:prepare(connect,key,user['id'],Dropbox)
            except Exception as error:st.error(str(error));return
            st.rerun(scope='fragment')
        poll_render(key,user['id'],spec.get('state'))
    elif not running and not result:st.caption('Artwork ready. Generate mockups to continue.')
    with st.container(key='product-upload-generation'):
        if pending and not result:poll_generation(app,key,user['id'],name,sport,row['data']['source']['content_hash'])
        if result:
            result['_product_upload_actor_id']=str(user['id'])
            from product_upload_outputs_ui import render_outputs
            render_outputs(app,result,row,user,name)
            # Mount the scroll helper only after completed output components.
            # Progress ticks and failed jobs must not consume the request.
            from product_upload_layout import focus_generation
            focus_generation(st.session_state.get('product-upload-generation-focus-'+key))
