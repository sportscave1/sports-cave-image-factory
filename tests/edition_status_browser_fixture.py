"""Offline-only native grid fixture; use the dedicated fixture server."""
from copy import deepcopy
from types import SimpleNamespace
import streamlit as st
import edition_ops as ops
import edition_version_ui as controls
import edition_versions
import auto_editions_status as status
from tests import edition_status_fixture_state as state
from tests.test_edition_ops_stability import _product,_snapshot

st.set_page_config(layout='wide')
ops._configured_supabase_backend=lambda:SimpleNamespace(connect=lambda:(_ for _ in ()).throw(AssertionError('Fixture forbids database access')))
ops._write_snapshot=lambda *args:None
ops.record_activity_log=lambda *args,**kwargs:None
edition_versions.kick=lambda:None
status.review_operations=lambda connect,data:data
status.batch=lambda connect,ids,**kwargs:{'rows':state.rows(ids),'query_count':1,'duration_ms':0}
ops.psd_directory.directory=lambda:{'gid://shopify/Product/'+str(i):{'verified':True,'state':'Linked','dropbox_file_id':'id:'+str(i)} for i in range(1,335) if state.mapping_overrides.get('gid://shopify/Product/'+str(i),'default') is not None}
data=[_product(i) for i in range(1,335)]
ops._load_snapshot=lambda:_snapshot(data)
ops._reload_products_from_supabase=lambda:None
st.session_state['sports_cave_current_user']={'id':'synthetic-reader','role':'worker','is_active':True,'page_permissions':['edition_ops']}
st.session_state['fixture-main-runs']=st.session_state.get('fixture-main-runs',0)+1
st.caption('fixture-main-runs: '+str(st.session_state['fixture-main-runs']))
st.html(controls.STYLE)
with st.container(key='edition-workspace'):
    controls.table()
