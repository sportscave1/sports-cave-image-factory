"""Offline Meta Review presentation fixture: no external reads or writes."""
import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import streamlit as st
import ads_meta_review_page as page
from tests.test_meta_review_search import ROWS
from tests.test_meta_review_live import CONFIG
st.set_page_config(layout='wide')
st.markdown('<style>.stApp{padding-top:64px}header[data-testid="stHeader"]{display:none}</style>',unsafe_allow_html=True)
with st.sidebar:
    st.title('Sports Cave OS')
    st.write('Meta Review · Offline preview')
with patch.object(page.meta,'get_meta_config',return_value=CONFIG),patch.object(page.live,'load_overview',return_value={'account':{'name':'Sports Cave','currency':'AUD'},'campaigns':ROWS}),patch.object(page.recency,'load',return_value={'available':False}):
    page.render_page()
