"""Synthetic loopback-only Automations visual fixture, never production data."""
import os
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock
import streamlit as st
import requests
from crm_automation_store import AutomationStore
from crm_automation_definition import email_step
from tests.crm_db_fixture import connect
from tests.test_crm import ADMIN
from tests.test_crm_send_flow import LIVE,CFG
from tests.test_crm_simple_editor import document

st.set_page_config(layout='wide',page_title='Local automation fixture')
os.environ.update(LIVE)
requests.sessions.Session.request=lambda *a,**k:(_ for _ in ()).throw(AssertionError('External network forbidden'))
AutomationStore.render_settings=lambda self,env=None:deepcopy(CFG)

@st.cache_resource
def setup():
    store=AutomationStore(connect)
    from crm_logic import now
    store.set_state('shopify_automation_capabilities',{'checked_at':now().isoformat(),'triggers':{k:'AVAILABLE' for k in ('welcome','post_purchase','abandoned','fulfilled')}})
    identities=[]
    for kind,name,state in (('welcome','Welcome series · local fixture','ACTIVE'),('abandoned','Abandoned checkout · local fixture','DRAFT'),('post_purchase','Collector follow-up · local fixture','PAUSED')):
        row=store.create(ADMIN,kind,name);flow=deepcopy(row['config']['draft'])
        flow['emails']=[email_step(document(),0),email_step(document(),86400)]
        row=store.save_flow(ADMIN,row['id'],row['name'],flow,1)
        if state!='DRAFT':row=store.publish(ADMIN,row['id'],row['config']['revision'],env=LIVE)
        if state=='PAUSED':store.lifecycle(ADMIN,row['id'],'pause')
        identities.append(str(row['id']))
    return identities

setup()
from crm_automation_ui import workspace
workspace(Mock(),AutomationStore(connect),SimpleNamespace(user=ADMIN))
