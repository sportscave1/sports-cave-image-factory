"""Communication navigation uses the existing routes, renderers and permissions."""
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import crm_navigation

ROOT=Path(__file__).resolve().parents[1]


class EmailNavigationTests(unittest.TestCase):
    def app(self,route='CRM Campaigns'):
        at=AppTest.from_file(str(ROOT/'tests/sidebar_preview_app.py'))
        at.session_state['route']=route
        return at.run(timeout=20)

    def test_exact_children_and_no_separate_crm_or_settings(self):
        at=self.app();self.assertFalse(at.exception)
        children=[b.label for b in at.button if (b.key or '').startswith('sidebar-child::')]
        self.assertEqual(children,['Inbox','Campaigns','Automations'])
        self.assertNotIn('CRM & Marketing',[b.label for b in at.button])
        self.assertNotIn('Settings',[b.label for b in at.button])
        self.assertEqual(crm_navigation.SIDEBAR_ROUTES,('Email','CRM Campaigns','CRM Automations'))

    def test_parent_defaults_to_existing_inbox_and_can_collapse(self):
        at=self.app()
        at.button(key='sidebar-disclosure::email').click().run()
        self.assertEqual(at.session_state['route'],'Email')
        self.assertEqual(at.button(key='sidebar-child::Email').proto.type,'primary')
        at.button(key='sidebar-disclosure::email').click().run()
        self.assertFalse(any((b.key or '').startswith('sidebar-child::') for b in at.button))
        at.button(key='sidebar-disclosure::email').click().run()
        self.assertEqual(at.button(key='sidebar-child::Email').label,'Inbox')

    def test_children_and_legacy_direct_routes_survive_refresh(self):
        for route in ('Email',*crm_navigation.ROUTES):
            at=self.app(route);self.assertFalse(at.exception);at.run()
            self.assertEqual(at.session_state['route'],route)
            self.assertEqual(at.session_state['sidebar-open-group'],'email')
        at=self.app()
        at.button(key='sidebar-child::CRM Automations').click().run()
        self.assertEqual(at.session_state['route'],'CRM Automations')
        self.assertEqual(at.button(key='sidebar-child::CRM Automations').proto.type,'primary')

    def test_existing_mailbox_dispatch_not_replaced(self):
        source=(ROOT/'app.py').read_text(encoding='utf-8')
        self.assertIn('elif current_page == "Email":\n        get_support_email_page().render_page(current_os_user())',source)
        self.assertEqual(crm_navigation.EMAIL_DEFAULT_ROUTE,'Email')

    def test_consent_permissions_not_inferred_from_email_access(self):
        import os_accounts
        user={'id':'test','role':'worker','is_active':True,'page_permissions':['email']}
        self.assertTrue(os_accounts.can_access_page(user,'Email'))
        self.assertFalse(os_accounts.can_access_page(user,'CRM Campaigns'))
        self.assertFalse(os_accounts.can_access_page(user,'CRM Automations'))
        with self.assertRaises(PermissionError):crm_navigation.require(user,'crm_settings_view')


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Requires disposable SQL fixture')
class CampaignSettingsNavigationTests(unittest.TestCase):
    def test_secondary_settings_reuses_forms_without_sending_or_losing_source(self):
        from tests.test_crm_ui import SCRIPT
        at=AppTest.from_string(SCRIPT.replace("'role':'worker'","'role':'admin'"))
        at.session_state['route']='CRM Campaigns'
        with patch.dict(os.environ,{'RESEND_MARKETING_API_KEY':'SECRET-SENTINEL','CRM_MARKETING_ENABLED':'false'}),patch('crm_delivery_panel.send_resend_test_email') as send:
            at.run(timeout=20)
            editor=at.session_state['campaign_editor']
            from crm_middle_sections import apply_event
            apply_event(at.session_state['campaign_editor']['document'],
                        {'type':'html','base':['html-1'],'id':'html-1','html':'<p>Keep source</p>'})
            at.session_state['campaign_settings_open']=True;at.run(timeout=20)
            self.assertFalse(at.exception)
            self.assertTrue(any('Campaign Settings' in m.value for m in at.markdown))
            self.assertEqual(at.session_state['campaign_editor']['document']['custom_html'],'<p>Keep source</p>')
            self.assertIsNone(editor['id'])
            self.assertTrue(any(b.label=='Save internal-test settings' for b in at.button))
            self.assertNotIn('SECRET-SENTINEL',str(at))
            at.run();send.assert_not_called()
            at.session_state['campaign_settings_open']=False;at.run()
            self.assertFalse(at.session_state['campaign_settings_open'])
            self.assertFalse(at.exception)
