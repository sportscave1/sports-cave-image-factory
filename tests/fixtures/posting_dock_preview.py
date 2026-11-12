"""Offline styling fixture: no external API calls or posting operations."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from unittest.mock import patch
import streamlit as st
import streamlit.components.v1 as components
import top_bar
import ads_posting_progress as progress
from ads_posting_status_style import install
from tests.test_meta_posting_progress import completed_row

st.set_page_config(layout='wide')
config={'appName':'Sports Cave OS','appSubtitle':'Operations System','logoSrc':'',
        'revision':'fixture','currentRoute':'Ads','currentRouteKey':'ads-new','navigationEpoch':0,
        'navigationRouteKeys':{},'navigationRouteLabels':{},'authToken':'',
        'searchIndex':[],'filesEnabled':True,'ordersEnabled':False,'emailEnabled':False,'dailyPlannerEnabled':False}
components.html(top_bar.component_html(config),height=0,width=0)
install(st)
progress.cleanup_completed()
st.title('Offline posting status preview')
st.text_input('Continue browsing',key='fixture_input')
if st.button('Simulate saving'):
    st.session_state['saving_fixture']=True
if st.button('Hand off to posting'):
    st.session_state['saving_fixture']=False
    progress.track(completed_row()['submission_id'])
if st.button('Verify success'):
    st.session_state['finished_fixture']=True
if st.session_state.get('saving_fixture'):
    with st.container(key='ads_save_progress'):
        st.progress(.6,text='Saving Ad setup notes')
from types import SimpleNamespace
from unittest.mock import Mock
import ads_posting_page as posting
def snapshot(identity):
    row=completed_row()
    if not st.session_state.get('finished_fixture'):
        row={**row,'status':'AD_CREATED','running_here':True,'operation':'Uploading images'}
    return row
progress.JOBS=SimpleNamespace(snapshot=snapshot)
posting._load_recent_posts=Mock()
progress.render_current()
