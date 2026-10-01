"""Campaign loading-shell regressions using synthetic data and offline UI runs."""
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from streamlit.testing.v1 import AppTest
import email_loading

ROOT = Path(__file__).resolve().parents[1]

SCRIPT = '''
from contextlib import ExitStack
from unittest.mock import Mock, patch
import streamlit as st
from crm_page import render_page
from crm_store import StoreUnavailable
from crm_resend import Config
from crm_campaign_content import settings
from tests.test_crm import ADMIN
from tests.test_crm_simple_editor import document

drafts=Mock()
drafts.setting.return_value={'value':{'smart_hours':16}}
drafts.render_settings.return_value=settings({})
drafts.q.return_value=None
if st.session_state.get('mode') == 'detail_error':
 drafts.render_settings.side_effect=StoreUnavailable('Campaign storage unavailable')
else:
 st.session_state['campaign_editor']={'id':None,'version':None,'name':'Fixture',
   'status':'DRAFT','archived_at':None,'document':document()}

with ExitStack() as stack:
 stack.enter_context(patch('requests.sessions.Session.request',side_effect=AssertionError('No HTTP')))
 stack.enter_context(patch('crm_campaign_page.CampaignStore',return_value=drafts))
 stack.enter_context(patch('email_loading.shell',side_effect=AssertionError('Campaigns must not emit shell')))
 stack.enter_context(patch('crm_tracking_health.control',side_effect=AssertionError('No tracking UI')))
 stack.enter_context(patch('crm_tracking_health.verify',side_effect=AssertionError('No tracking verification')))
 if st.session_state.get('mode') == 'list_error':
  stack.enter_context(patch('crm_campaign_page._campaign_history',side_effect=StoreUnavailable('Campaign storage unavailable')))
 else:
  stack.enter_context(patch('crm_campaign_page.recent_campaigns',side_effect=lambda *a:st.caption('Campaign history fixture')))
 stack.enter_context(patch('crm_campaign_send_ui.test_control',side_effect=lambda *a,**kw:st.button('Send test')))
 stack.enter_context(patch('crm_campaign_send_ui.send_control',side_effect=lambda *a,**kw:st.button('Send now')))
 stack.enter_context(patch('crm_campaign_page.flush_current',return_value=False))
 stack.enter_context(patch('crm_campaign_recovery.flush_current',return_value=False))
 stack.enter_context(patch('crm_recovery_ui.recovery_bridge'))
 stack.enter_context(patch('crm_prompt_ui.prompt_control'))
 stack.enter_context(patch('crm_prompt_ui.field_feedback'))
 stack.enter_context(patch('crm_campaign_controls.market_control'))
 stack.enter_context(patch('crm_html_workspace.composer_canvas',side_effect=lambda *a:st.caption('Preview fixture')))
 render_page('CRM Campaigns',ADMIN,shop=Mock(),store=Mock(),config=Config({}))
'''


class CampaignLoadingTests(unittest.TestCase):
    def assert_no_shell(self, app):
        self.assertFalse(app.exception)
        html='\n'.join(element.proto.body for element in app.get('html'))
        for obsolete in ('EMAIL · CAMPAIGNS', 'sc-email-loading', '+ New campaign',
                         'Find campaign', 'Refresh', '780px'):
            self.assertNotIn(obsolete, html)
        self.assertFalse(app.get('empty'))
        for label in ('Tracking health','Verify tracking setup'):
            self.assertNotIn(label,[button.label for button in app.button])
            self.assertNotIn(label,[popover.label for popover in app.get('popover')])

    def test_success_renders_real_editor_actions_tabs_and_preview(self):
        app=AppTest.from_string(SCRIPT).run()
        self.assert_no_shell(app)
        self.assertFalse(app.error)
        self.assertFalse(app.warning)
        self.assertEqual([tab.label for tab in app.tabs], ['Settings','Editor','Templates'])
        for label in ('Save draft','Send test','Send now'):
            self.assertIn(label, [button.label for button in app.button])
        self.assertIn('Campaign name', [field.label for field in app.text_input])
        self.assertIn('Preview fixture', [caption.value for caption in app.caption])

    def test_detail_and_list_errors_remain_inline_without_shell_or_gap(self):
        for mode in ('detail_error','list_error'):
            with self.subTest(mode=mode):
                app=AppTest.from_string(SCRIPT)
                app.session_state['mode']=mode
                app.run()
                self.assert_no_shell(app)
                if mode == 'detail_error':
                    messages=list(app.error)+list(app.warning)
                    self.assertEqual(len(messages),1)
                    self.assertEqual(messages[0].value,'Campaign storage unavailable')
                    self.assertFalse(app.tabs)
                    self.assertFalse(app.button)
                else:
                    self.assertIn('Campaign list temporarily unavailable.',
                                  [caption.value for caption in app.caption])
                    self.assertFalse(app.error)
                    self.assertFalse(app.warning)
                    self.assertEqual([tab.label for tab in app.tabs], ['Settings','Editor','Templates'])

    def test_no_campaign_placeholder_lifecycle_remains(self):
        source=(ROOT/'crm_campaign_page.py').read_text(encoding='utf-8')
        for obsolete in ('editor_loading','loading.empty()', 'sc-email-loading','780px'):
            self.assertNotIn(obsolete,source)
        self.assertNotIn("'Campaigns':",(ROOT/'email_loading.py').read_text(encoding='utf-8'))

    def test_inbox_and_automations_shells_preserve_controls_and_skeleton(self):
        for page, controls in (('Inbox','+ New mail　　Search mail　　Refresh'),
                               ('Automations','Flow　　Email　　Refresh')):
            with self.subTest(page=page), patch.object(email_loading.st,'empty') as empty:
                slot=email_loading.shell(page)
                self.assertIs(slot,empty.return_value)
                html=slot.html.call_args.args[0]
                self.assertIn('EMAIL · '+page.upper(),html)
                self.assertIn(controls,html)
                self.assertIn('<section><p></p><p></p><p></p></section>',html)
                self.assertIn('class="sc-email-loading"',html)


if __name__=='__main__':
    unittest.main()
