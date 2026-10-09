"""Offline thumbnail regression fixture; no live database or mail providers."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from copy import deepcopy
from unittest.mock import Mock
import streamlit as st
from tests.test_crm_simple_editor import document
from tests.test_crm_send_flow import CFG
from crm_automation_definition import email_step
import crm_flow_page as page
import crm_flow_thumbnail as thumbs

st.set_page_config(layout='wide')
from contextlib import nullcontext
from unittest.mock import patch
baseline_module=None
if st.query_params.get('baseline'):
    import subprocess,types
    baseline_module=types.ModuleType('baseline_thumbnails')
    exec(compile(subprocess.check_output(['git','show','7c5896a:crm_flow_thumbnail.py']).decode('utf8'),'baseline.py','exec'),baseline_module.__dict__)
steps=[dict(email_step(document(),3600),step_id='stage-'+str(i)) for i in range(1,13)]
row={'id':'11111111-1111-1111-1111-111111111111','name':'Fixture','status':'ARCHIVED','config':{'revision':1,'draft':{'emails':steps}},'steps':[{'step_id':s['step_id'],'template_id':'template-'+s['step_id'],'template_version':int(st.query_params.get('version',7))} for s in steps]}
store=Mock();store.flow.return_value=row;store.render_settings.return_value=CFG
store.template.side_effect=lambda tid,version:{'automation_id':row['id'],'step_id':tid.removeprefix('template-'),'automation_version':version,'document':document(),'render_settings':CFG}
page.step_performance=lambda *a:None
page.refresh_toolbar=lambda:None
with st.container(key='crm-automation-editor'):
    with st.container(key='flow-workspace'):
        st.html(page.STYLE)
        st.title('Automation thumbnail fixture')
        with patch('crm_flow_thumbnail.thumbnail',lambda store,step,row:baseline_module.thumbnail(store,step)) if baseline_module else nullcontext():
            page.sequence(None,store,{},row['id'],'All time')
    st.html('<span data-flow-script="true" style="display:none">thumbnail-controller</span>'+(baseline_module.SCRIPT if baseline_module else thumbs.SCRIPT),unsafe_allow_javascript=True)
