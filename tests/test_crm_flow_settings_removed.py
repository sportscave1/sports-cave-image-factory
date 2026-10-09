"""Offline detail-page regression: settings stay authoritative in the backend."""
from copy import deepcopy
import unittest
from streamlit.testing.v1 import AppTest

SCRIPT = """
import streamlit as st
from copy import deepcopy
from unittest.mock import MagicMock, patch
from crm_automation_definition import new_flow
from crm_flow_page import flow_page
from tests.test_crm import ADMIN
trigger=st.session_state.get('fixture_trigger','abandoned')
flow=st.session_state.setdefault('fixture_flow',new_flow(trigger))
flow.update(reentry_days=st.session_state.get('fixture_cooldown',7),exit_on_purchase=True,rules=[{'field':'market','condition':'is','value':'AU'}])
row={'id':'fixture','name':'Abandoned Checkout - Wall Preview 1','status':'DRAFT','trigger_type':trigger,'config':{'draft':flow}}
before=deepcopy(row)
store=MagicMock();store.flow.return_value=row
st.session_state['submitted']=None
def commit(store,user,row,draft):st.session_state['submitted']=draft
with patch('crm_automation_toolbar.toolbar'), patch('crm_flow_page.analytics_controls'), patch('crm_flow_page.checkouts'), patch('crm_flow_page.step_performance'), patch('crm_flow_page.refresh_toolbar'), patch('crm_flow_thumbnail.thumbnail'), patch('crm_flow_page.commit',side_effect=commit):
    flow_page(None,store,ADMIN,row)
assert row==before
store.save_flow.assert_not_called()
st.session_state['flow_reads']=store.flow.call_count
st.session_state['original']=before
"""

class FlowSettingsRemovalTests(unittest.TestCase):
    def app(self,trigger='abandoned',cooldown=7):
        app=AppTest.from_string(SCRIPT)
        app.session_state['fixture_trigger']=trigger
        app.session_state['fixture_cooldown']=cooldown
        app.run()
        self.assertFalse(app.exception)
        return app

    def test_render_and_rerun_preserve_every_flow_type_and_own_configuration(self):
        for trigger,cooldown in [('abandoned',7),('welcome',0),('post_purchase',30),('fulfilled',90),('win_back',7)]:
            with self.subTest(trigger=trigger):
                app=self.app(trigger,cooldown)
                original=deepcopy(app.session_state['original'])
                app.run()
                self.assertFalse(app.exception)
                self.assertEqual(app.session_state['original'],original)
                self.assertEqual(app.session_state['flow_reads'],1)
                labels=[e.label for kind in ('text_input','selectbox','checkbox','button') for e in getattr(app,kind)]
                for removed in ('Flow name','Entry trigger','Re-entry cooldown','Exit after a new purchase','Save flow settings','Apply these entry rules (AND)'):
                    self.assertNotIn(removed,labels)
                self.assertNotIn('Flow Settings',[e.value for e in app.subheader])
                self.assertIn('+ Add Email',labels)
                self.assertIn('Edit Email',labels)
                self.assertIn('Enable this email',labels)

    def test_add_email_preserves_flow_configuration_and_existing_sequence(self):
        app=self.app();original=deepcopy(app.session_state['original']['config']['draft'])
        next(b for b in app.button if b.label=='+ Add Email').click().run()
        self.assertFalse(app.exception)
        draft=app.session_state['submitted']
        self.assertEqual(draft['emails'][:-1],original['emails'])
        self.assertEqual(draft['emails'][-1]['delay_seconds'],86400)
        self.assertEqual({k:v for k,v in draft.items() if k!='emails'},{k:v for k,v in original.items() if k!='emails'})

    def test_step_delay_and_enabled_controls_preserve_flow_settings(self):
        app=self.app();original=deepcopy(app.session_state['original']['config']['draft'])
        app.number_input[0].set_value(12)
        next(s for s in app.selectbox if s.label=='Unit').select('Hours')
        next(c for c in app.checkbox if c.label=='Enable this email').uncheck()
        next(b for b in app.button if b.label=='Save step').click().run()
        self.assertFalse(app.exception)
        draft=app.session_state['submitted']
        self.assertEqual(draft['emails'][0]['delay_seconds'],43200)
        self.assertFalse(draft['emails'][0]['enabled'])
        self.assertEqual({k:v for k,v in draft.items() if k!='emails'},{k:v for k,v in original.items() if k!='emails'})
