"""Offline native editor/prompt fixture. All external HTTP/DB reads forbidden."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from unittest.mock import Mock,patch
from copy import deepcopy
import streamlit as st
from tests.test_crm_simple_editor import document
from tests.test_crm_send_flow import CFG
from tests.test_crm_prompt_helper import Reader,inputs
from crm_campaign_prompt import build
from crm_email_prompt import retain
from crm_email_prompt_ui import email_prompt_control
from crm_html_workspace import section_editor

@st.cache_resource
def guard():
 reader=Reader();catalogue=Mock();catalogue.resolve.return_value=[]
 patches=[patch('requests.sessions.Session.request',side_effect=AssertionError('No external HTTP')),
 patch('supabase_backend.connect',side_effect=AssertionError('No production DB')),
 patch('crm_prompt_readers.PromptReader',return_value=reader),patch('crm_catalogue.Catalogue',return_value=catalogue)]
 for p in patches:p.start()
 return patches
guard()
st.set_page_config(layout='wide')
if 'campaign_editor' not in st.session_state:
 st.session_state.campaign_editor={'id':'offline','recovery_seed':'offline','name':'Collector launch','document':document()}
 editor=st.session_state.campaign_editor
 retain(st.session_state,editor,inputs(),build(inputs(),editor['document'],Reader()))
editor=st.session_state.campaign_editor
st.title('Campaigns · offline editor fixture')
show_ai=st.checkbox('Show AI trigger',value=True)
a,b=st.columns([360,700])
with a:
 st.write('Editor')
 if show_ai:email_prompt_control(None,editor,'offline_')
 section_editor(editor['document'],CFG,'offline_',None,{},None,None)
with b:st.caption('Existing Email Preview position')
