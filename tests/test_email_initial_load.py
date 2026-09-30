"""Read-only first-paint contracts, using fabricated mail and loopback CRM only."""
from contextlib import ExitStack
import os
import unittest
import uuid
from unittest.mock import patch

from support_email_workspace import Workspace
from support_email_smtp import SMTPConfiguration, SendRegistry
from support_email_compose import default_settings
from tests.email_v2_fixtures import MailboxFixture, fixture_smtp, USER, CONFIG


class InboxStages(unittest.TestCase):
    def test_shell_then_list_then_body_without_duplicate_reads(self):
        mailbox=MailboxFixture(5);state={'initial_load_pending':True}
        with ExitStack() as stack:
            stack.enter_context(patch('support_email_store.load_email_settings',return_value=(default_settings(),None)))
            stack.enter_context(patch('support_email_store.load_metadata',return_value={}))
            w=Workspace(state,USER,CONFIG,SMTPConfiguration(password='fixture'),
                        imap=mailbox,smtp=fixture_smtp(),registry=SendRegistry())
            self.assertTrue(w.model()['initial_load_pending'])
            self.assertEqual(mailbox.calls,[])
            event={'id':str(uuid.uuid4()),'action':'load_initial_mailbox'}
            w.handle(event);w.handle(event)
            self.assertEqual([c[1] for c in mailbox.calls if c[0]=='headers'],['INBOX'])
            self.assertFalse(any(c[0] in ('body','attachment','flag','move') for c in mailbox.calls))
            model=w.model();self.assertEqual(len(model['threads']),5)
            self.assertEqual(model['body_pending'],model['active_message'])
            w.handle({'id':str(uuid.uuid4()),'action':'load_visible_body','message_key':model['active_message']})
            calls=list(mailbox.calls)
            w.model();w.model()
            self.assertEqual(mailbox.calls,calls)
            w.handle({'id':str(uuid.uuid4()),'action':'load_initial_mailbox'})
            self.assertEqual(mailbox.calls,calls)
            w.handle({'id':str(uuid.uuid4()),'action':'refresh'})
            self.assertEqual(len([c for c in mailbox.calls if c[0]=='headers']),2)


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Requires isolated loopback fixture')
class CRMStages(unittest.TestCase):
    def test_campaign_list_precedes_selected_settings_and_hidden_editor(self):
        from streamlit.testing.v1 import AppTest
        from crm_campaign_store import CampaignStore
        from tests.test_crm_ui import SCRIPT
        calls=[];query=CampaignStore.q
        def record(self,sql,*args,**kwargs):
            calls.append(sql)
            return query(self,sql,*args,**kwargs)
        with patch.object(CampaignStore,'q',record),patch('crm_html_workspace.section_editor') as editor:
            at=AppTest.from_string(SCRIPT);at.session_state['route']='CRM Campaigns';at.run(timeout=20)
            self.assertFalse(at.exception)
            self.assertIn('FROM crm_campaign_drafts d',calls[0])
            self.assertIn('jsonb_build_object',calls[0])
            self.assertFalse(any('crm_campaign_history' in q for q in calls))
            editor.assert_not_called()
            at.session_state[at.session_state['campaign_edit_key']+'panel']='Editor';at.run(timeout=20)
            editor.assert_called_once()

    def test_automations_does_not_load_hidden_template_library(self):
        from streamlit.testing.v1 import AppTest
        from crm_store import Store
        from tests.test_crm_ui import SCRIPT
        calls=[];query=Store.q
        def record(self,sql,*args,**kwargs):
            calls.append(sql)
            return query(self,sql,*args,**kwargs)
        with patch.object(Store,'q',record):
            at=AppTest.from_string(SCRIPT);at.session_state['route']='CRM Automations';at.run(timeout=20)
            self.assertFalse(at.exception)
            self.assertFalse(any('FROM crm_templates' in q and 'template_key=%s' not in q for q in calls))
            self.assertFalse(any('crm_campaign_drafts' in q for q in calls))
            self.assertFalse(any(s.label=='Status' for s in at.selectbox))


if __name__=='__main__':unittest.main()
