"""Credential-free Streamlit harness for the production component asset path."""
from pathlib import Path
import sys
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from contextlib import contextmanager
from types import SimpleNamespace
import streamlit as st
import streamlit.components.v1 as components
from tests.test_product_upload_package import saved_row
import product_upload_intake as intake
import product_upload_prompts as prompts
from product_upload_prompt_copy import render_copy
from product_upload_source import current_source

if 'row' not in st.session_state:
    st.session_state.row=saved_row()
    st.session_state.row['data'].update(basic_validated=True,name='Synthetic product.psd',mockups_context={'images':[]})
    st.session_state.saved=False
class Store:
    def __init__(self,*a): pass
    def read(self,*a): return st.session_state.row
    @contextmanager
    def locked(self,*a): yield st.session_state.row,None
    def copied(self,key,actor,mode,version):
        assert key==st.session_state.row['id']
        current_source(st.session_state.row,version)
        st.session_state.copied=True
intake.Intakes=Store
original=getattr(prompts, "_fixture_original", prompts.build)
prompts._fixture_original=original
# Bypass shared prompt storage only; preserve actual production prompt composition.
def build(*a,**kw):
    return original(*a,**kw,load=lambda key,default,**options:default)
prompts.build=build
if st.button('Switch product'):
    st.session_state.row=saved_row()
    st.session_state.row['data'].update(basic_validated=True,name='Other product.psd')
    st.session_state.saved=False
if st.button('Save all'):
    st.session_state.row['data']['upload_operation']['output']['files'][0]['metadata']['rev']+='x'
    token=uuid.uuid4().hex
    st.session_state.row['data']['mockup_save_token']=token
    st.session_state.row['data']['upload_operation']['output']['save_token']=token
    st.session_state.saved=True
if st.session_state.saved:
    st.success('✓ Saved')
    render_copy(SimpleNamespace(BASE_DIR=Path(__file__).resolve().parents[1],get_components_module=lambda:components),st.session_state.row,{'id':'fixture'},current_source(st.session_state.row)['version'])
if st.checkbox('Mount workflow assets'):
    components.declare_component('product_uploads_workflow',path=str(Path(__file__).resolve().parents[1]/'components/product_uploads'))(section='handoff',isolated_copy=True,key='workflow')
st.text_area('Paste verification')
