"""Synthetic 500-product UI fixture. No database, Shopify or certificate writes."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import os
import json
import subprocess
import types
from copy import deepcopy
import streamlit as st
if os.environ.get('EDITION_BASELINE')=='1' and 'edition_ops' not in sys.modules:
    module=types.ModuleType('edition_ops');module.__file__=str(Path(__file__).resolve().parents[2]/'edition_ops.py')
    sys.modules['edition_ops']=module
    exec(compile(subprocess.check_output(['git','show','01bc526:edition_ops.py'],text=True,encoding='utf8'),module.__file__,'exec'),module.__dict__)
import edition_ops as ops
import edition_versions as versions
import design_tracking_page


@st.cache_resource
def fixture():
    data={'loads':0,'saves':0,'archive':0,'creates':0,'reviews':0,'rows':[]}
    for i in range(500):
        data['rows'].append(ops._normalise_row(dict(edition_product_id=str(i+1),shopify_product_gid='gid://shopify/Product/'+str(i+1),
          edition_run_id=f'00000000-0000-0000-0000-{i+1:012d}',run_status='active',
          product_title=f'Artwork {i+1:03d}',handle=f'artwork-{i+1}',edition_label='Original Edition',
          edition_enabled=True,edition_total=100,edition_next_number=10,edition_sold_count=9,edition_remaining=91)))
    return data


data=fixture()
def snapshot():
    data['loads']+=1
    return {'rows':deepcopy(data['rows']),'original_rows':deepcopy(data['rows']),'source':'fixture','cached':False}
def save(rows,**kw):
    data['saves']+=1;result=[]
    for row in rows:
        target=next(r for r in data['rows'] if r['handle']==row['handle'])
        n=row['next_edition_number']
        if n<10:result.append({'ok':False,'key':row['row_key'],'message':'Selected number is behind this release; Start New Edition Version for revised artwork.'})
        else:
            target['edition_next_number']=n;result.append({'ok':True,'key':row['row_key'],'handle':row['handle']})
    return result
backend=types.SimpleNamespace(update_edition_products_batch=save)
ops._configured_supabase_backend=lambda:backend
ops._load_snapshot=snapshot
ops._write_snapshot=lambda *a,**k:None
ops._invalidate_edition_ops_cache=lambda **k:None
ops.record_activity_log=lambda *a,**k:None
ops._render_pull_new_products_button=lambda *a:None
ops._render_advanced_controls=lambda *a,**k:st.caption('Advanced controls fixture')
design_tracking_page.render=lambda:st.caption('Design Tracking fixture · retained')
versions.kick=lambda *a:None
def archive(*a,**k):data['archive']+=1;return []
versions.archive=archive
def details(identity):data['reviews']+=1;return {'version':{},'allocations':[{'edition_number':9,'certificate_status':'Ready'}],'audit':[]}
versions.details=details
st.session_state['sports_cave_current_user']={'id':'00000000-0000-0000-0000-000000000999','role':'admin'}
st.session_state['fixture_full_runs']=st.session_state.get('fixture_full_runs',0)+1
st.set_page_config(layout='wide')
st.sidebar.write('Stable app sidebar')
route=st.sidebar.selectbox('Page',['Edition Ops','Home'])
if route=='Edition Ops':ops.render_page()
else:st.write('Home')
@st.fragment
def counters():
    st.button('Profile snapshot')
    st.session_state['edition-profile-tick']=st.session_state.get('edition-profile-tick',0)+1
    st.html('<pre id="edition-profile" style="white-space:pre-wrap;overflow-wrap:anywhere">'+json.dumps({**{k:v for k,v in data.items() if k!='rows'},'full_runs':st.session_state['fixture_full_runs'],'tick':st.session_state['edition-profile-tick']})+'</pre>')
counters()
