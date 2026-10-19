"""Real destination controls, synthetic account/listing/job transport only."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import streamlit as st
import dropbox_integration as api
from product_upload_outputs_ui import save_controls

for key,value in dict(listing_calls=[],submissions=[],job=None,result=dict(
        assets=['prepared-originals'],product_image_readiness={'complete':True})).items():
    st.session_state.setdefault(key,value)


def listing(token,path,**kwargs):
    st.session_state['listing_calls'].append(path)
    assert path=='/Team/04_OUTPUT/product-images'
    return dict(entries=[{'.tag':'folder','name':name,'path_display':path+'/'+name}
                         for name in ('Motorsport Wall Art','Cricket')],has_more=False)


def transfer(provider,result,manifest,root,parent,folder,connect,actor,progress,**kwargs):
    st.session_state['submissions'].append(dict(result=result,manifest=manifest,root=root,parent=parent,folder=folder,**kwargs))


def submit(key,actor,operation,fingerprint,work):
    assert st.session_state['job'] is None
    work(lambda *a:None)
    st.session_state['job']=dict(state='Running',stage='Saving originals',total=None)


jobs=SimpleNamespace(snapshot=lambda *a:st.session_state['job'],submit=submit)
app=SimpleNamespace(dropbox_integration=api,os_accounts=SimpleNamespace(can_access_page=lambda *a:True),
    _files_access_token=lambda:'fixture',_files_team_root=lambda token:'/Team',
    ASSET_CATEGORY_CORE='core',ASSET_CATEGORY_PRODUCT='product',ASSET_CATEGORY_SOCIAL='social',
    _mockup_dropbox_manifest=lambda *a:[dict(archive_name='WEBP/product.webp',path=Path(st.session_state['original_path']),byte_length=27)],
    _set_mockups_result=lambda result:st.session_state.update(result=result))
with patch.object(api,'list_folder_page',listing),patch('product_upload_jobs.JOBS',jobs), \
     patch('product_upload_export.transfer',transfer),patch('product_upload_api.Dropbox',lambda:None):
    save_controls(app,st.session_state['result'],dict(id='fixture',data={'source':{'rev':'fixture'}}),{'id':'fixture'},'Current: Product')
