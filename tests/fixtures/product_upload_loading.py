"""Offline slow-poll browser fixture: no credentials, PSDs or provider calls."""
from pathlib import Path
from types import SimpleNamespace
import ast,sys,time
import streamlit as st
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import product_upload_jobs
st.set_page_config(layout='wide')
st.session_state['_product_upload_active']='fixture'
source=ast.parse((ROOT/'product_upload_mockups_ui.py').read_text(encoding='utf-8'))
fn=next(n for n in source.body if isinstance(n,ast.FunctionDef) and n.name=='poll_generation')
ns={'st':st};exec(compile(ast.Module(body=[fn],type_ignores=[]),'actual-generation-poll','exec'),ns)
if st.query_params.get('fade')!='baseline':
    st.html('<style>'+(ROOT/'product_upload_page.css').read_text()+'</style><span class="product-upload-page-marker"></span>')
st.title('Product Upload generation — isolated loading check')
st.caption('Synthetic job only. Slow polling deliberately exposes stale-content fading.')
mode=st.selectbox('Job state',['Running','Failed','Ready'])
st.button('Generate mockups',disabled=mode=='Running')
st.button('Save all',disabled=True)
if st.button('Slow refresh'):time.sleep(2)
def snapshot(*args):
    time.sleep(.65)
    return dict(state=mode,total=5,completed=2,stage='Preparing previews',previews=[],token=mode,error='Synthetic failure: retry generation')
product_upload_jobs.JOBS.snapshot=snapshot
product_upload_jobs.JOBS.result=lambda *a:dict(_product_upload_source_hash='source',product_name='Fixture',sport_category='Cricket')
app=SimpleNamespace(normalize_generation_result=lambda r:r,_set_mockups_result=lambda r:st.session_state.update(complete=True))
with st.container(key='product-upload-workspace'):
    with st.container(key='product-upload-generation'):
        if st.session_state.get('complete'):st.success('Mockups ready')
        else:ns['poll_generation'](app,'fixture','actor','Fixture','Cricket','source')
st.write('Page stays readable; progress stays inline. No modal or page cover.')
