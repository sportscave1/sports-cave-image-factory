"""Real section editor + Send test control, with delivery replaced by validation only."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from unittest.mock import Mock, patch
import streamlit as st
from crm_section_ui import middle_editor
from crm_campaign_send_ui import test_control
from crm_campaign_content import preflight, settings
from crm_campaign_issues import preflight_error
from tests.test_crm_modular_catalogue import catalogue_doc, event
from tests.test_crm_resend_marketing import ENV
from tests.test_crm import ADMIN

st.set_page_config(layout='wide')
st.title('Send test preflight — offline, delivery disabled')
if 'campaign_editor' not in st.session_state:
    doc=catalogue_doc();doc['middle_sections'][-1].update(visible=False,products=[])
    event(doc,'add',kind='image')
    st.session_state.campaign_editor={'id':'fixture','document':doc,'name':'Peter Brock fixture','archived_at':None}
editor=st.session_state.campaign_editor
def validation_only(store,user,current,*args,**kwargs):
    from copy import deepcopy
    document=deepcopy(current['document']);document['copy_reviewed']=True
    checks=preflight(document,ENV,settings(ENV))
    raise ValueError(preflight_error(checks) if not checks['test_ready'] else 'Offline validation passed. No email sent.')
import crm_campaign_send_ui
crm_campaign_send_ui.send_test=validation_only  # Remains patched during fragment-only reruns.
with patch('requests.sessions.Session.request',side_effect=AssertionError('No network')):
    test_control(Mock(),ADMIN,editor,'preflight_fixture_')
    middle_editor(editor['document'],'preflight_fixture_',Mock())
