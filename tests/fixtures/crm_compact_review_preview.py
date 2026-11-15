"""Offline modal layout fixture; no database, Shopify, Resend or external assets."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from copy import deepcopy
from unittest.mock import patch
import time
import streamlit as st
from crm_campaign_send_ui import review_dialog
from crm_email_size import campaign_size
from tests.test_crm_simple_editor import document
from tests.test_crm_send_flow import CFG

st.set_page_config(layout='wide')
if 'campaign_editor' not in st.session_state:
    from crm_logic import now
    doc=document();doc['market']='NZ';doc['counts']={'members':4,'eligible':4,'excluded':{},'complete':True,'checked_at':now().isoformat()}
    st.session_state.campaign_editor={'id':'47bb53bc-9a37-4f99-a840-e775073dbce5','version':1,
        'name':'Peter Brock Tribute — 20 Years Remembered','document':doc,'archived_at':None}
    st.session_state.campaign_saved=deepcopy(st.session_state.campaign_editor)

# Capture immutable data before the review thread: it never accesses Streamlit.
report=campaign_size(st.session_state.campaign_editor['document'],CFG)
def finalize(*args):
    time.sleep(1)
    return {'counts':{'eligible':4,'excluded':{}},'blockers':[],'snapshot_id':'offline',
        'tracking_ok':True,'email_size':report}

@st.cache_resource
def guards():
    patches=[patch('crm_campaign_review.review',side_effect=finalize),
        patch('crm_campaign_send_ui.queue_campaign',side_effect=AssertionError('Offline preview cannot send')),
        patch('crm_preview_cache.preview',return_value={'html':'<html><body style="margin:0;padding:18px;font-family:Arial;background:#faf8f2"><h2>SPORTS CAVE</h2><h3>20 years remembered</h3><p>A tribute to a motorsport legend.</p><p>Explore the collector edition.</p></body></html>'}),
        patch('crm_campaign_send_ui.get_resend_marketing_config_status',return_value={
            'sender':'Sports Cave <fixture@example.test>','reply_to':'fixture@example.test','marketing_enabled':True})]
    for guard in patches:guard.start()
    return patches
guards()
if st.button('Open offline review'):
    review_dialog(None,None,{},st.session_state.campaign_editor,'offline_',CFG)
