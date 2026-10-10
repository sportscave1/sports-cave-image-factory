"""Offline visual/performance fixture. No production connections or providers."""
import os,sys,uuid,json,importlib.util
from pathlib import Path
root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root))
if os.getenv('FLOW_V4_BASELINE')=='1':
    for name in ('crm_thumbnail_store','crm_thumbnail_cache','crm_thumbnail_render','crm_flow_thumbnail','crm_automation_toolbar','crm_flow_page'):
        spec=importlib.util.spec_from_file_location(name,root/'tmp/flow-v4-before'/f'{name}.py')
        module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
from copy import deepcopy
from unittest.mock import Mock,patch
import streamlit as st
from tests.test_crm_simple_editor import document
from tests.test_crm_send_flow import CFG
from tests.test_crm import ADMIN
from crm_automation_definition import new_flow,email_step
import crm_flow_page as page

def discount_document():
    from crm_middle_sections import middle_sections
    from crm_discount_section import section
    doc=document();offer=dict(id='gid://shopify/DiscountCodeNode/11',code='FIXTURE5',value='A$5 off eligible products',type='DiscountCodeBasic')
    doc['recovery_discount']=offer;doc['middle_sections']=middle_sections(doc)+[section(offer)]
    return doc

st.set_page_config(layout='wide',page_title='Flow V4 — local synthetic fixture')
count=int(st.query_params.get('stages',3));identity=str(uuid.uuid5(uuid.NAMESPACE_URL,'flow-v4-'+str(count)))
if st.session_state.get('fixture_identity')!=identity:
    flow=new_flow();flow['emails']=[dict(email_step(discount_document() if i==2 else document(),600 if i==0 else 86400),step_id=str(uuid.uuid5(uuid.UUID(identity),str(i)))) for i in range(count)]
    for i,s in enumerate(flow['emails']):
        s['document']['content']['subject']='Email '+str(i+1)+' — '+s['document']['content']['subject']
    row=dict(id=identity,name='Abandoned Checkout — Wall Preview 1 · synthetic',status='ACTIVE',updated_at=1,trigger_type='abandoned',
             config=dict(revision=1,published_version=10,published_flow=deepcopy(flow),draft=flow,publication={'state':'LIVE'}),
             steps=[dict(step_id=s['step_id'],template_id=s['step_id'],template_version=10) for s in flow['emails']])
    st.session_state.update(fixture_identity=identity,fixture_row=row,fixture_reads=0,fixture_runs=0)
row=st.session_state['fixture_row'];st.session_state['fixture_runs']+=1
store=Mock();store.connect=None
def read_flow(*args):
    st.session_state['fixture_reads']+=1;return deepcopy(row)
store.flow.side_effect=read_flow
store.q.return_value={'updated_at':row['updated_at']}
store.render_settings.return_value=CFG
def template(tid,version):
    s=next(s for s in row['config']['published_flow']['emails'] if s['step_id']==tid)
    return dict(automation_id=identity,step_id=tid,automation_version=version,document=deepcopy(s['document']),render_settings=CFG)
store.template.side_effect=template
def save(user,identity,name,flow,expected):
    assert expected==row['config']['revision']
    row['config']['draft']=deepcopy(flow);row['config']['revision']+=1;row['updated_at']+=1
    return deepcopy(row)
store.save_flow.side_effect=save
store.send.side_effect=AssertionError('Email sending forbidden')
store.request_publish.side_effect=AssertionError('Publication forbidden')
store.lifecycle.side_effect=AssertionError('Live state changes forbidden')
metrics=dict(entered=41,sent=43,delivered=43,opened=17,clicked=4,conversions=0,orders=0,bounced=0)
def analytics(store,key,load):
    if key[0]=='flow-summary':return [metrics],'READY'
    if key[0]=='analytics-steps':return [dict(step_id=s['step_id'],sent=3,opened=2,clicked=1,orders=0,delivered=3,queued=0,bounced=0,failed=0,skipped=0) for s in row['config']['draft']['emails']],'READY'
    return [],'READY'
with st.container(key='crm-automation-editor'):
    if st.session_state.get('automation_composing'):
        st.caption('Editor transition fixture — actual editor tested separately')
        st.text_input('Subject',key='fixture-subject')
        if st.button('Flow'):
            st.session_state['automation_composing']=False;st.rerun()
    else:
        with patch('crm_flow_page.read',side_effect=analytics),patch('crm_automation_publish_state.has_changes',return_value=False):
            page.flow_page(None,store,ADMIN,row)
st.html('<pre id="flow-v4-counters">'+json.dumps(dict(flow_reads=st.session_state['fixture_reads'],full_runs=st.session_state['fixture_runs']))+'</pre>')
