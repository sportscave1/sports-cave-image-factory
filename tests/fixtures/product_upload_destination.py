"""Real shared selector and save controls with synthetic Dropbox and jobs."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import streamlit as st
import image_factory as factory
import dropbox_integration as api
from product_upload_outputs_ui import save_controls
from product_upload_sport import render_selector,rebind_result,clear_selection

for key,value in dict(listing_calls=[],metadata_calls=[],submissions=[],job=None).items():
    st.session_state.setdefault(key,value)
base='/Team/04_OUTPUT/product-images'
folders=[{'.tag':'folder','id':'id:'+ident,'name':name,'path_display':base+'/'+name}
         for ident,name in [('motor','Motorsport Wall Art'),('v8','V8 Supercars Wall Art'),('soccer','Soccer Wall Art'),('football','Football Wall Art')]]
if st.session_state.get('renamed'):
    folders[0]=dict(folders[0],name='Motor Racing Wall Art',path_display=base+'/Motor Racing Wall Art')
if st.session_state.get('missing'):folders=folders[1:]

def listing(token,path,**kwargs):
    st.session_state['listing_calls'].append(path)
    assert path==base
    return dict(entries=folders,has_more=False)

def metadata(token,identity):
    st.session_state['metadata_calls'].append(identity)
    return next((f for f in folders if f['id']==identity),None)

def transfer(provider,result,manifest,root,parent,folder,connect,actor,progress,**kwargs):
    st.session_state['submissions'].append(dict(result=result,manifest=manifest,root=root,parent=parent,folder=folder,**kwargs))

def submit(key,actor,operation,fingerprint,work):
    assert st.session_state['job'] is None
    work(lambda *a:None)
    st.session_state['job']=dict(state='Running',stage='Saving originals',total=None)

def normalize(result):
    result=dict(result)
    result['product_image_manifest']=factory.build_product_image_manifest(result['assets'],product_slug=result['product_slug'],sport_slug=result['sport_slug'])
    result['product_image_readiness']={'complete':True}
    return result

def manifest(result,*args):
    ordered=factory.order_assets_by_product_manifest(result['assets'],result['product_image_manifest'])
    return factory.build_asset_zip_manifest(ordered,include_content_hash=False)

if 'result' not in st.session_state:
    asset=factory.build_asset_record(key='black',label='Black',webp_path=Path(st.session_state['original_path']),jpg_path=None,asset_group='generated',zip_group='core')
    st.session_state['result']=normalize(dict(assets=[asset],product_name='Current: Product',product_slug='current-product',sport_category='Football',sport_slug='football',lifestyle_mockup_paths={'uploaded':'retained'}))
jobs=SimpleNamespace(snapshot=lambda *a:st.session_state['job'],submit=submit)
app=SimpleNamespace(dropbox_integration=api,os_accounts=SimpleNamespace(can_access_page=lambda *a:True),
    _files_access_token=lambda:'fixture',_files_team_root=lambda token:'/Team',
    ASSET_CATEGORY_CORE='core',ASSET_CATEGORY_PRODUCT='product',ASSET_CATEGORY_SOCIAL='social',
    _mockup_dropbox_manifest=manifest,normalize_generation_result=normalize,
    get_image_factory=lambda:factory,build_mockup_final_prompt_items=lambda *a:[],
    _set_mockups_result=lambda result:st.session_state.update(result=result))
with patch.object(api,'list_folder_page',listing),patch.object(api,'get_metadata_if_exists',metadata),patch('product_upload_jobs.JOBS',jobs), \
     patch('product_upload_export.transfer',transfer),patch('product_upload_api.Dropbox',lambda:None):
    running=bool(st.session_state['job'])
    name=st.text_input('Product name',value='Current: Product',disabled=running)
    choice=render_selector(app,'fixture',{'id':'fixture'},disabled=running)
    if choice and not running:st.session_state['result']=rebind_result(app,st.session_state['result'],name,choice)
    save_controls(app,st.session_state['result'],dict(id='fixture',data={'source':{'rev':'fixture'}}),{'id':'fixture'},name)
    if st.button('New upload'):
        clear_selection('fixture');st.rerun()
