"""Same synthetic 334 rows, using the user-approved committed V14 table source.

The two baseline modules are extracted locally to ignored output/v15-phase3/
baseline. No production app startup, credentials, database or worker is used.
"""
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
import streamlit as st

root=Path(__file__).parents[1]
for name in ('edition_ops','edition_version_ui'):
    spec=importlib.util.spec_from_file_location(name,root/'output/v15-phase3/baseline'/f'{name}.py')
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
import edition_ops as ops
import edition_version_ui as controls
import edition_versions
from tests.test_edition_ops_stability import _product,_snapshot

st.set_page_config(layout='wide')
ops._configured_supabase_backend=lambda:SimpleNamespace(connect=lambda:(_ for _ in ()).throw(AssertionError('Fixture forbids database access')))
ops._write_snapshot=lambda *args:None
ops.record_activity_log=lambda *args,**kwargs:None
edition_versions.kick=lambda:None
ops.psd_directory.directory=lambda:{'gid://shopify/Product/'+str(i):{'verified':True,'state':'Linked','dropbox_file_id':'id:'+str(i)} for i in range(1,335)}
data=[_product(i) for i in range(1,335)]
ops._load_snapshot=lambda:_snapshot(data)
ops._reload_products_from_supabase=lambda:None
st.session_state['sports_cave_current_user']={'id':'synthetic-reader','role':'worker','is_active':True,'page_permissions':['edition_ops']}
st.session_state['fixture-main-runs']=st.session_state.get('fixture-main-runs',0)+1
st.caption('fixture-main-runs: '+str(st.session_state['fixture-main-runs']))
st.html(controls.STYLE)
with st.container(key='edition-workspace'):controls.table()
