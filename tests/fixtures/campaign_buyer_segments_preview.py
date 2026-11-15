"""Real Settings controls with synthetic cached data; no Shopify/DB/email I/O."""
from pathlib import Path
import sys, json
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from unittest.mock import Mock, patch
from contextlib import ExitStack
import streamlit as st
from crm_campaign_content import new_document
from crm_campaign_controls import market_control, timing_control
from crm_html_workspace import composer_styles
from crm_buyer_segments import BUYER_NAMES
st.set_page_config(layout='wide')
composer_styles()
if st.query_params.get('before')=='1':
    import importlib.util
    spec=importlib.util.spec_from_file_location('buyer_before_controls','.tmp-product-sport-tags-v2/buyer-before-controls.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    market_control=module.market_control
doc=st.session_state.setdefault('fixture-document',dict(new_document(),market='Global',market_audience=True,shopify_segment_ids=[]))
shop=Mock(namespace='fixture');store=Mock()
options={f'gid://shopify/Segment/{i+100}':{'name':name,'checked_at':'2026-10-11T00:00:00+00:00','missing':[]} for i,name in enumerate(BUYER_NAMES)}
job=Mock();job.display.return_value={'members':12,'eligible':9,'excluded':{'suppressed':2,'duplicate':1}};job.valid.return_value=True
# Keep fixture patches alive through fragment-only reruns in this isolated server.
# A context manager would undo them before the next dropdown interaction.
stack=st.session_state.setdefault('fixture-patches',ExitStack())
if True:
    stack.enter_context(patch('crm_segment_counts.COUNTS.display',return_value={'counts':{},'pending':False,'error':False}))
    stack.enter_context(patch('crm_buyer_segments.CATALOGUE.display',return_value={'snapshot':options,'pending':False,'error':False}))
    stack.enter_context(patch('crm_campaign_audience_prepare.prepare_session',return_value=job))
    stack.enter_context(patch('crm_campaign_home.arm_home_poll'))
    stack.enter_context(patch('crm_campaign_recovery.flush_current'))
    st.title('Campaign fixture')
    with st.container(width=360,height=680,key='crm-composer-controls'):
        settings,editor,templates=st.tabs(['Settings','Editor','Templates'])
        with settings:
            st.text_input('Campaign name',value='Fixture')
            st.text_input('Subject',value='A sporting moment')
            st.text_input('Preview text',value='For collectors')
            market_control(shop,store,doc,'buyer-fixture-')
            timing_control(doc,'buyer-fixture-')
    if st.button('Fixture save'):st.session_state['fixture-saved']=json.loads(json.dumps(doc))
    if st.button('Fixture reload'):
        st.session_state['fixture-document']=json.loads(json.dumps(st.session_state['fixture-saved']))
        st.session_state.pop('buyer-fixture-buyer-segments',None)
        st.session_state.pop('buyer-fixture-market',None)
        st.rerun()
    st.html('<pre id="buyer-contract">'+json.dumps(doc)+'</pre>')
