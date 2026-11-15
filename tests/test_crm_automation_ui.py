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
from unittest.mock import Mock,MagicMock,patch
from concurrent.futures import Future
from crm_automation_ui import home
from tests.test_crm import ADMIN
store=MagicMock();store.connect=None
store.db.return_value.__enter__.return_value.execute.return_value.fetchall.return_value=[{'id':'00000000-0000-0000-0000-000000000001','name':'Real fixture automation','trigger_type':'welcome','updated_at':'2026-10-02','category':'Drafts','format':'automation_flow_v1'}]
def job(state,store,key,load,**kwargs):
 value={'all_count':1,'drafts':1,'active':0,'paused':0,'archived':0,'sent_emails':4,'bounce_rate':0.,'click_rate':25.,'orders':1} if key[0] not in ('table','identities') else [{'id':'00000000-0000-0000-0000-000000000001','name':'Real fixture automation','trigger_type':'welcome','updated_at':'2026-10-02','category':'Drafts','format':'automation_flow_v1','entered':0,'sent':0,'delivered':0,'opened':0,'clicked':0,'orders':0}]
 if key[0]=='delivery':value.update(delivery_rate=99.,open_rate=40.,revenue={'AUD':100},previous={})
 if key[0]=='activity':value=[]
 f=Future()
 if not st.session_state.get('pending'):
  if st.session_state.get('failed') and key[0]=='delivery':f.set_exception(ValueError('Private diagnostic'))
  else:f.set_result([value])
 state.setdefault('campaign_home_cache',{})[(store.connect,key)]=(None,f);return f
with patch('crm_automation_ui.job',side_effect=job):home(store,ADMIN)
'''


class AutomationUiTests(unittest.TestCase):
    def test_flow_management_is_only_in_left_settings_without_main_accordion(self):
        import inspect
        from crm_automation_ui import detail,settings_control,add_email_controls,flow_email_control
        main=inspect.getsource(detail);settings=inspect.getsource(settings_control)
        self.assertNotIn("st.expander('Flow",main)
        self.assertNotIn('auto_timeline_',main)
        self.assertNotIn('add_email_controls(',main)
        self.assertNotIn("st.selectbox('Flow email'",main)
        self.assertIn('flow_email_control(flow',settings)
        self.assertIn('add_email_controls(store,user,editor,key)',settings)
        self.assertIn("st.selectbox('Trigger'",settings)
        self.assertIn("st.number_input('Delay",settings)
        self.assertIn("st.selectbox('Flow email'",inspect.getsource(flow_email_control))
        self.assertIn("st.button('Duplicate email'",inspect.getsource(add_email_controls))

    def test_left_email_switch_flushes_before_selecting_without_saving_flow_definition(self):
        from crm_automation_ui import flow_email_control
        from crm_automation_definition import email_step
        flow={'emails':[email_step(document(),0),email_step(document(),3600)]}
        original=deepcopy(flow);state={'automation_editor':{'id':'flow'},'automation_step':flow['emails'][0]['step_id']}
        with patch('crm_automation_ui.st.selectbox',return_value=1),patch('crm_automation_ui.st.session_state',state),patch('crm_campaign_recovery.flush_current',return_value=True) as flush,patch('crm_automation_ui.st.rerun') as rerun:
            flow_email_control(flow,'flow',flow['emails'][0]['step_id'])
        flush.assert_called_once();rerun.assert_called_once()
        self.assertEqual(state['automation_step'],flow['emails'][1]['step_id']);self.assertNotIn('automation_editor',state)
        self.assertEqual(flow,original)
        blocked={'automation_editor':{'id':'flow'}}
        with patch('crm_automation_ui.st.selectbox',return_value=1),patch('crm_automation_ui.st.session_state',blocked),patch('crm_campaign_recovery.flush_current',return_value=False),patch('crm_automation_ui.st.rerun') as rerun:
            flow_email_control(flow,'flow',flow['emails'][0]['step_id'])
        rerun.assert_not_called();self.assertIn('automation_editor',blocked)

    def test_rendering_left_settings_does_not_change_saved_trigger_delay_or_published_data(self):
        from crm_automation_ui import settings_control
        from crm_automation_definition import new_flow
        flow=new_flow('welcome');flow['rules']=[];flow['emails'][0]['delay_seconds']=73
        row={'config':{'draft':flow,'published':deepcopy(flow),'published_version':2},'status':'ACTIVE'}
        original=deepcopy(row);store=Mock();store.flow.return_value=row;store.step_id=flow['emails'][0]['step_id']
        editor={'id':'flow','name':'Existing automation','version':3,'document':deepcopy(flow['emails'][0]['document'])}
        select=lambda label,options,**kw:options[kw.get('index',0)]
        with patch('crm_automation_ui.st.session_state',{'automation_editor_context':(store,{})}),patch('crm_automation_ui.st.selectbox',side_effect=select),patch('crm_automation_ui.st.number_input',side_effect=lambda *a,**kw:kw['value']),patch('crm_automation_ui.st.checkbox',return_value=editor['document']['copy_reviewed']),patch('crm_automation_ui.st.caption'),patch('crm_automation_ui.st.button',return_value=False),patch('crm_automation_ui.flow_email_control') as selector,patch('crm_automation_ui.add_email_controls') as additions:
            settings_control(editor,'fixture_')
        selector.assert_called_once();additions.assert_called_once();store.save_flow.assert_not_called()
        self.assertEqual(row,original);self.assertEqual(editor['version'],3)

    def test_home_six_kpis_overview_activity_and_action_menu(self):
        app=AppTest.from_string(HOME_SCRIPT).run()
        self.assertFalse(app.exception)
        html='\n'.join(e.proto.body for e in app.get('html'))
        for value in ('Automations','Delivery rate','Open rate','Revenue from automations (30 days)','Real fixture automation','Customer subscribes to email'):self.assertIn(value,html)
        for value in ('EMAIL · AUTOMATIONS','sc-email-loading'):self.assertNotIn(value,html)
        self.assertEqual(html.count('class="sc-auto-kpi"'),6)
        self.assertTrue(any(b.label=='Flow' for b in app.button))
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

    def test_loaded_cards_and_rows_survive_refresh_and_errors(self):
        app=AppTest.from_string(HOME_SCRIPT).run()
        before=' '.join(e.proto.body for e in app.get('html'))
        app.session_state['pending']=True;app.run()
        html=' '.join(e.proto.body for e in app.get('html'))
        self.assertIn('AUD 100.00',html);self.assertIn('Real fixture automation',html)
        app.session_state['pending']=False;app.session_state['failed']=True;app.run()
        self.assertFalse(app.exception)
        html=' '.join(e.proto.body for e in app.get('html'))
        self.assertIn('AUD 100.00',html);self.assertNotIn('Private diagnostic',html)
        app.get('button_group')[0].set_value('Recent Activity').run()
        self.assertFalse(app.exception)
        self.assertIn('AUD 100.00',' '.join(e.proto.body for e in app.get('html')))
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

    def test_home_search_only_changes_selected_table_request(self):
        app=AppTest.from_string(HOME_SCRIPT.replace("def job(state,store,key,load,**kwargs):", "def job(state,store,key,load,**kwargs):\n st.session_state.setdefault('requests',[]).append(key)")).run()
        initial=app.session_state['requests']
        self.assertEqual(list(dict.fromkeys(k[1][0] for k in initial if k[0]=='table')),[''])
        # Streamlit currently exposes segmented controls as button groups.
        group=app.get('button_group')[0]
        app.text_input[0].set_value('Reminder').run()
        self.assertFalse(app.exception)
        self.assertEqual(list(dict.fromkeys(k[1][0] for k in app.session_state['requests'] if k[0]=='table')),['','Reminder'])

    def test_same_composer_preview_templates_and_test_send_are_called(self):
        source=Path('crm_automation_ui.py').read_text(encoding='utf-8')
        for name in ('composer_form(','toolbar(','mode=\'automation\'','composer_canvas('):self.assertIn(name,source)
        self.assertIn('test_control(',Path('crm_automation_toolbar.py').read_text(encoding='utf-8'))
        self.assertIn('automation_size_meter(cache)',Path('crm_abandoned_checkout_ui.py').read_text(encoding='utf8'))
        self.assertNotIn('text_area(',source)
        self.assertNotIn('market_control(',source)
        self.assertNotIn('timing_control(',source)
        routing=Path('crm_page.py').read_text()
        self.assertNotIn('from crm_flow_editor import flow_workspace',routing)


if __name__=='__main__':unittest.main()
