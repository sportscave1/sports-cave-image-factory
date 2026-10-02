"""Offline shared-composer ownership and automation Home UI regressions."""
from concurrent.futures import Future
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock,patch
import unittest
from streamlit.testing.v1 import AppTest
from crm_email_editor_context import current,flush_automation
from crm_navigation import navigation_allowed
from tests.test_crm_simple_editor import document

HOME_SCRIPT='''
import streamlit as st
from unittest.mock import Mock,patch
from concurrent.futures import Future
from crm_automation_ui import home
from tests.test_crm import ADMIN
store=Mock();store.connect=None
def job(state,store,key,load):
 value={'all_count':1,'drafts':1,'active':0,'paused':0,'archived':0,'sent_emails':4,'bounce_rate':0.,'click_rate':25.,'orders':1} if key[0]!='table' else [{'id':'00000000-0000-0000-0000-000000000001','name':'Real fixture automation','trigger_type':'welcome','updated_at':'2026-10-02','category':'Drafts','format':'automation_flow_v1','entered':0,'sent':0,'delivered':0,'opened':0,'clicked':0,'orders':0}]
 f=Future();f.set_result(value);state.setdefault('campaign_home_cache',{})[(store.connect,key)]=(None,f);return f
with patch('crm_automation_ui.job',side_effect=job):home(store,ADMIN)
'''


class AutomationUiTests(unittest.TestCase):
    def test_home_shared_kpis_tabs_no_revenue_or_legacy_shell(self):
        app=AppTest.from_string(HOME_SCRIPT).run()
        self.assertFalse(app.exception)
        html='\n'.join(e.proto.body for e in app.get('html'))
        for value in ('Automations','Bounce rate','Real fixture automation','Customer subscribes to email'):self.assertIn(value,html)
        for value in ('Revenue','EMAIL · AUTOMATIONS','sc-email-loading'):self.assertNotIn(value,html)
        self.assertEqual(html.count('class="sc-home-kpi"'),5)
        self.assertTrue(any(b.label=='Delete automation' for b in app.button))
        self.assertTrue(any(b.label=='+ Create automation' for b in app.button))
    def test_editor_context_does_not_overwrite_campaign(self):
        original={'id':'campaign','name':'Campaign','document':document()}
        auto={'id':'automation','name':'Automation','document':document(),'version':1}
        store=Mock();store.save.return_value={**auto,'version':2}
        state={'email_editor_mode':'automation','campaign_editor':deepcopy(original),'automation_editor':auto,'automation_editor_context':(store,{}),'automation_saved':{}}
        self.assertIs(current(state),auto);self.assertTrue(flush_automation(state))
        self.assertEqual(state['campaign_editor'],original)
        self.assertEqual(state['automation_saved']['version'],2)
        self.assertTrue(navigation_allowed(state,'CRM Automations','CRM Campaigns'))
        auto['document']['content']['subject']='Unsaved'
        self.assertFalse(navigation_allowed(state,'CRM Automations','CRM Campaigns'))
        self.assertEqual(state['automation_requested_route'],'CRM Campaigns')
    def test_automation_cache_is_independent_and_summary_survives_definition_change(self):
        from crm_automation_ui import changed
        campaign_value={'sent_emails':4,'orders':1}
        auto_value={'sent_emails':8,'orders':2}
        campaign={'campaign_home_resolved':{(None,('delivery',None)):campaign_value}}
        auto={'campaign_home_cache':{(None,('delivery',None)):(0,Future()),(None,('counts',None)):(0,Future()),(None,('table','Drafts')):(0,Future())},
              'campaign_home_resolved':{(None,('delivery',None)):auto_value}}
        with patch('crm_automation_ui.st.session_state',{'automation_home_state':auto,**campaign}):changed()
        self.assertEqual(list(auto['campaign_home_cache']),[(None,('delivery',None))])
        self.assertEqual(auto['campaign_home_resolved'][(None,('delivery',None))],auto_value)
        self.assertEqual(campaign['campaign_home_resolved'][(None,('delivery',None))],campaign_value)

    def test_home_status_change_only_changes_selected_table_request(self):
        app=AppTest.from_string(HOME_SCRIPT.replace("def job(state,store,key,load):", "def job(state,store,key,load):\n st.session_state.setdefault('requests',[]).append(key)")).run()
        initial=app.session_state['requests']
        self.assertEqual([k[1][0] for k in initial if k[0]=='table'],['All automations'])
        # Streamlit currently exposes segmented controls as button groups.
        group=app.get('button_group')[0]
        group.set_value('Drafts').run()
        self.assertFalse(app.exception)
        self.assertEqual([k[1][0] for k in app.session_state['requests'] if k[0]=='table'],['All automations','Drafts'])

    def test_same_composer_preview_templates_and_test_send_are_called(self):
        source=Path('crm_automation_ui.py').read_text()
        for name in ('composer_form(','test_control(','size_meter(','mode=\'automation\'','composer_canvas('):self.assertIn(name,source)
        self.assertNotIn('text_area(',source)
        self.assertNotIn('market_control(',source)
        self.assertNotIn('timing_control(',source)
        routing=Path('crm_page.py').read_text()
        self.assertNotIn('from crm_flow_editor import flow_workspace',routing)


if __name__=='__main__':unittest.main()
