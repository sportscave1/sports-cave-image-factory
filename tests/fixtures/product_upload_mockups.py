"""Actual combined renderer with disposable SQL and explicit native/provider doubles."""
import sys,types,json
from pathlib import Path
from unittest.mock import patch
import streamlit as st
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from product_upload_mockups_preview import STATE
from tests.test_product_upload_intake import ADMIN
store,sql,provider=STATE['env']
st.set_page_config(layout='wide')
source_hash=__import__('hashlib').sha256((ROOT/'app.py').read_bytes()).hexdigest()
if 'fixture-app' not in st.session_state or st.session_state.get('fixture-source-hash')!=source_hash:
    module=types.ModuleType('product_upload_fixture_app_'+str(id(st.session_state)))
    module.__file__=str(ROOT/'app.py');sys.modules[module.__name__]=module
    exec(compile((ROOT/'app.py').read_text(encoding='utf-8').rsplit('main()',1)[0],module.__file__,'exec'),module.__dict__)
    st.session_state['fixture-app']=module
    st.session_state['fixture-source-hash']=source_hash
for retained in list(sys.modules.values()):
    if getattr(retained,'__name__','').startswith('product_upload_fixture_app_'):
        retained.current_os_user=lambda:ADMIN
        retained.record_activity_log=lambda *a,**k:None
app=st.session_state['fixture-app']
app.current_os_user=lambda:ADMIN
app.record_activity_log=lambda *a,**k:None
app._files_access_token=lambda **kw:'synthetic'
app._files_team_root=lambda token:'/Sportscave Team Folder'
if STATE.get('configure_outputs'):STATE['configure_outputs'](app)
else:app._render_mockup_folder_picker=lambda *a:'/Sportscave Team Folder/04_OUTPUT/product-images'
app._save_mockups_to_dropbox_impl=lambda token,user,result,manifest,root,parent,name,conflict:dict(destination=result['_product_upload_save_target'],successes=[dict(relative_path=x['archive_name']) for x in manifest],failures=[])
st.query_params['page']='product_uploads'
st.session_state['current_page']='Product Uploads'
st.session_state['selected_page']='Product Uploads'
app.inject_styles()
app.init_session_state()
st.session_state['current_page']='Product Uploads'
st.session_state['selected_page']='Product Uploads'
with st.sidebar:
    st.caption('Isolated fixture: no production writes; native render is simulated.')
    if st.button('New Product Uploads visit'):
        st.session_state.pop('_product_upload_visit',None)
        for k in ('_product_upload_active','_product_upload_event','_product_upload_manual','_product_upload_mockups_result'):st.session_state.pop(k,None)
    if st.button('Complete isolated render'):
        from product_upload_render import Renders,identity
        from tests.test_auto_editions_colour import icc
        from PIL import Image,ImageDraw
        import auto_editions as ae
        renders=Renders(store.connect);job=renders.claim(ADMIN['id'])
        if job:
            row=store.read(job['id'],ADMIN['id']);path=provider.root/'synthetic-render.png'
            image=Image.new('RGBA',(640,480),(22,60,90,255));ImageDraw.Draw(image).text((170,220),'ISOLATED SPORTS CAVE ART',fill='white');image.save(path,icc_profile=icc())
            receipt=dict(source=identity(row),source_unchanged=True,owned_document_closed=True,native_render=True,colour={'synthetic':True},render_sha256=ae.file_hash(path))
            renders.finish(job['id'],ADMIN['id'],job['token'],receipt,path,provider)
    if st.button('Refresh workflow'):pass
    if st.button('Complete isolated Shopify/preparation'):
        from tests.test_product_upload_handoff import import_synthetic
        row=store.read(st.session_state.get('_product_upload_active'),ADMIN['id'])
        if row and row['data'].get('product_gid'):
            folder=provider.root/'prepared';folder.mkdir(exist_ok=True);import_synthetic(STATE['env'],row,folder)
with patch.object(app,'current_os_user',return_value=ADMIN),patch.object(app.prompt_store,'get_prompt',side_effect=lambda key,default='',**kw:default),patch.object(app,'record_activity_log'),patch.object(app,'_files_access_token',return_value='synthetic'),patch.object(app,'_files_team_root',return_value='/Sportscave Team Folder'),patch.object(app,'_render_mockup_folder_picker',return_value='/Sportscave Team Folder/04_OUTPUT/product-images'),patch.object(app,'_save_mockups_to_dropbox_impl',side_effect=lambda token,user,result,manifest,root,parent,name,conflict:dict(destination=result['_product_upload_save_target'],successes=[dict(relative_path=x['archive_name']) for x in manifest],failures=[])):
    if STATE.get('configure_outputs'):STATE['configure_outputs'](app)
    app.render_product_uploads_page()
