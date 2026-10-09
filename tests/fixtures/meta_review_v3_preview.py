"""Offline acceptance page. Every Meta/storage operation is replaced by fixtures."""
import copy
import os
import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
if os.environ.get('META_REVIEW_MODULE_ROOT'):
    sys.path.insert(0,os.environ['META_REVIEW_MODULE_ROOT'])
import streamlit as st
import ads_meta_review_page as page
from tests.test_meta_review_search import ROWS
from tests.test_meta_review_live import CONFIG
from tests.test_meta_review import history

st.set_page_config(layout='wide',initial_sidebar_state='collapsed')
st.markdown('<style>header[data-testid="stHeader"]{display:none}</style>',unsafe_allow_html=True)
st.checkbox('Simulate outage',key='fixture-outage')
st.session_state['fixture-run']=st.session_state.get('fixture-run',0)+1
def overview(*args):
    if st.query_params.get('failure') or st.session_state.get('fixture-outage'):
        raise page.meta.MetaAdsApiError('Fixture service temporarily unavailable',error_code=2,error_subcode=1504044)
    return {'account':{'name':'Offline Sports Cave','currency':'AUD'},'campaigns':copy.deepcopy(ROWS)}

with patch.object(page.meta,'get_meta_config',return_value=CONFIG), \
     patch.object(page.live,'load_overview',side_effect=overview), \
     patch.object(page.recency,'load',return_value={'available':False}), \
     patch.object(page.live,'load_campaign',return_value=history()), \
     patch.object(page,'_load_preferences',return_value={'selections':[],'mapping':[]}), \
     patch.object(page.meta,'_request',side_effect=AssertionError('No external reads in preview')):
    page.render_page()
st.caption('Fixture run '+str(st.session_state['fixture-run']))
