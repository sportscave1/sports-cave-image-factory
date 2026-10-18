"""Continuous Product Uploads shell around the original Mockups renderer."""
import sys
import uuid
from pathlib import Path
import streamlit as st


def render_page(app):
    from product_upload_api import connect
    from product_upload_intake import Intakes
    user=app.current_os_user()
    if '_product_upload_visit' not in st.session_state: st.session_state['_product_upload_visit']=uuid.uuid4().hex
    visit=st.session_state['_product_upload_visit']
    component=app.get_components_module().declare_component('product_uploads_workflow',path=str(app.BASE_DIR/'components/product_uploads'))
    event=component(section='upload',refresh=st.session_state.get('_product_upload_linked',''),key='product-upload-input-'+visit,default=None)
    if event and event.get('nonce')!=st.session_state.get('_product_upload_event'):
        previous=st.session_state.get('_product_upload_active')
        st.session_state['_product_upload_event']=event['nonce']
        st.session_state['_product_upload_active']=event.get('id')
        st.session_state['_product_upload_manual']=bool(event.get('manual'))
        st.session_state['_product_upload_mode']=event.get('mode','DRAFT')
        st.session_state['_product_upload_visible']=event.get('visible',True)
        if previous!=event.get('id'):
            from product_upload_mockups import release_transient
            release_transient(st.session_state.get('_product_upload_mockups_result'))
            st.session_state.pop('_product_upload_mockups_result',None)
    key=st.session_state.get('_product_upload_active')
    manual=st.session_state.get('_product_upload_manual',False)
    if manual:
        component(section='handoff',manual=True,mode=st.session_state.get('_product_upload_mode','DRAFT'),key='product-upload-manual-'+visit,default=None)
        return
    if not key: return
    row=Intakes(connect).read(key,user['id'])
    if row and row['data'].get('workflow_version') == 3:
        from product_upload_dropbox import status
        row = status(row, connect)
    if not row or not row['data'].get('basic_validated'): return
    st.html('<style>'+ (app.BASE_DIR/'mockups_page.css').read_text(encoding='utf-8')+'</style>')
    with st.container(key='mockups-workspace'):
        render_design(app,row,user)
    # Hand-off is below the SAME existing lifestyle/export controls. Rendering
    # the text prompt, exports and clipboard never confirms a Shopify product.
    row=Intakes(connect).read(key,user['id'])
    if row['data'].get('mockups_exported'):
        st.caption('Open the saved design folder or downloaded ZIP. Attach the images to ChatGPT, then paste the Shopify prompt below. Copy Prompt copies text only.')
        linked=component(section='handoff',id=key,mode=row['mode'],key='product-upload-handoff-'+visit+'-'+key,default=None)
        if linked and linked.get('id')==key and linked.get('linked') and linked.get('nonce')!=st.session_state.get('_product_upload_linked'):
            st.session_state['_product_upload_linked']=linked['nonce']
            st.rerun()


@st.fragment(run_every=5)
def poll_render(key, actor, state):
    from product_upload_api import connect
    from product_upload_intake import Intakes
    if not st.session_state.get('_product_upload_visible',True):return
    row=Intakes(connect).read(key,actor)
    if row and row['data'].get('workflow_version') == 3:
        from product_upload_dropbox import status
        row = status(row, connect)
    if row and (row['data'].get('server_artwork') or {}).get('state')!=state:st.rerun()


def render_design(app,row,user):
    from product_upload_api import connect,Dropbox
    from product_upload_intake import Intakes
    import image_factory
    key=str(row['id']);row=Intakes(connect).read(key,user['id'])
    if row['data'].get('workflow_version') == 3:
        from product_upload_dropbox import status
        row = status(row, connect)
    if st.session_state.get('_product_upload_active')!=key:return
    result=app._mockups_result()
    if result and result.get('_product_upload_intake')!=key:
        app._set_mockups_result(None);result=None
    st.subheader('Prepare product images')
    name=st.text_input('Product name',value=Path(row['data']['name']).stem,key='product-upload-name-'+key)
    # The original Mockups uses the alphabetised sport list plus Custom, with
    # editable selection. Reuse that list and get_sport_category verbatim.
    from sports_categories import infer_sport_category
    options=app.alphabetize_options(app.SPORT_OPTIONS,last=('Custom',))
    inferred=infer_sport_category([Path(row['data']['name']).stem],default='')
    option=st.selectbox('Sport category',options=options,index=options.index(inferred) if inferred in options else 0,key='product-upload-sport-'+key)
    custom=st.text_input('Custom sport category',key='product-upload-custom-'+key) if option=='Custom' else ''
    sport=app.get_sport_category(option,custom)
    if row['data'].get('workflow_version')!=3:
        st.info('Choose a Dropbox PSD for server preparation. This saved legacy workflow is retained.');return
    spec=row['data'].get('server_artwork') or {}
    generated=bool(result)
    if spec.get('state')!='Ready':st.session_state.pop('product-upload-generate-requested-'+key,None)
    clicked=st.button('Generate Core Shopify Images',type='primary',key='product-upload-generate-'+key,disabled=not name.strip() or not sport or spec.get('state')!='Ready') and spec.get('state')=='Ready'
    if clicked:
        st.session_state['product-upload-generate-requested-'+key]=True
        if generated and (result['product_name']!=name.strip() or result['sport_category']!=sport):
            with Intakes(connect).locked(key,user['id']) as (current,cur):
                if current['data'].get('product_gid'):
                    st.error('This PSD is already linked to Shopify. Remove it to start a separate design workflow.');return
                current['data'].update(mockups_exported=False,mockups_context=None,copied=False,lookup='',choices=[])
            from product_upload_mockups import release_transient
            release_transient(result)
            app._set_mockups_result(None);result=None;generated=False
    if spec.get('state')=='Preparing':
        st.info('Preparing original PSD artwork on the server. Generate Core Shopify Images will be enabled when it is ready.')
        poll_render(key,user['id'],spec['state'])
    elif spec.get('state') in ('Selected','Failed'):
        if spec['state']=='Failed':st.error(spec.get('reason') or 'Artwork preparation failed. Retry preparation; the original and workflow are retained.')
        else:st.info('PSD selected. Prepare its original artwork before generating core images.')
        if st.button('Retry artwork preparation' if spec['state']=='Failed' else 'Prepare artwork',key='product-upload-artwork-retry-'+key):
            st.session_state.pop('product-upload-generation-failed-'+key,None)
            st.session_state.pop('product-upload-generate-requested-'+key,None)
            try:
                from product_upload_artwork import prepare
                prepare(connect,None,key,user['id'],provider_factory=Dropbox)
            except Exception as error:st.error(str(error));return
            st.rerun()
        poll_render(key,user['id'],spec['state'])
    elif spec.get('state')=='Ready':st.info('Artwork ready. Generate Core Shopify Images to continue.')
    failed_key='product-upload-generation-failed-'+key
    if clicked:st.session_state.pop(failed_key,None)
    if st.session_state.get(failed_key):
        st.error(st.session_state[failed_key])
    requested = st.session_state.get('product-upload-generate-requested-'+key)
    if spec.get('state')=='Ready' and requested and not generated and not st.session_state.get(failed_key):
        image_factory.cleanup_stale_temp_runs()
        parent=image_factory.create_temp_run_parent()
        import tempfile
        if not app.MOCKUPS_GENERATION_SEMAPHORE.acquire(blocking=False):
            st.info('Another image generation is running. This PSD render is retained; try again when it finishes.');return
        try:
            with tempfile.TemporaryDirectory(dir=parent,prefix='product-upload-render-') as folder:
                provider=Dropbox()
                from product_upload_artwork import ensure_ready
                row,prepared=ensure_ready(row,connect,provider)
                source=prepared/'artwork.png'
                with st.status('Generating Core Shopify Images…'):
                    result=image_factory.generate_product_images(product_name=name.strip(),sport_category=sport,artwork_file_path=source,
                        base_dir=app.BASE_DIR,output_root=parent,
                        final_prompt_items=app.build_mockup_final_prompt_items(name.strip(),sport))
                from product_upload_artwork import current
                current(provider,row)
                result=app.normalize_generation_result(result)
                result.update(_product_upload_intake=key,_product_upload_actor_id=str(user['id']),_product_upload_source_hash=row['data']['source']['content_hash'])
                latest=Intakes(connect).read(key,user['id'])
                if st.session_state.get('_product_upload_active')!=key or latest['data']['source']!=row['data']['source']:
                    from product_upload_mockups import release_transient
                    release_transient(result);return
                app._set_mockups_result(result)
        except Exception as error:
            st.session_state[failed_key]=str(error);st.error(str(error));return
        finally:app.MOCKUPS_GENERATION_SEMAPHORE.release()
    if result:
        result['_product_upload_actor_id']=str(user['id'])
        app.render_generation_result(result)
        latest=Intakes(connect).read(key,user['id'])
        if latest['data'].get('mockups_exported'):
            if st.button('Continue to Shopify',key='product-upload-continue-'+key):st.rerun()
