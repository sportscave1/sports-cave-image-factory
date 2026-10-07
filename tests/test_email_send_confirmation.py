"""The actual send controller with durable SQL and fake SMTP/IMAP only."""
from contextlib import ExitStack, contextmanager
from email import policy
from email.parser import BytesParser
import os
import unittest
import uuid
from unittest.mock import Mock, patch

from tests import test_support_email_v2 as v2
from tests.email_v2_fixtures import CONFIG, USER, MailboxFixture
from tests.test_email_durable_delivery import Connection
from support_email_compose import default_settings, make_attachment
from support_email_durable import DurableRegistry, MailStore
from support_email_provider import MailboxError
from support_email_workspace import Workspace, reference_key
import support_email_smtp as smtp
import support_email_store as store


class SendConfirmation(unittest.TestCase):
    setUp = v2.WorkspaceTests.setUp
    event = v2.WorkspaceTests.event
    compose = v2.WorkspaceTests.compose
    open = v2.WorkspaceTests.open

    def test_worker_claim_in_progress_keeps_polling_and_never_retries_submission(self):
        draft = self.compose(); op = draft['operation_id']
        self.w.send(op)
        with patch.object(self.w.registry, 'submit', return_value={'status':'in_progress', 'operation_id':op}):
            self.w.advance_send(op)
        self.assertEqual(self.state['send_stage'], 'SENDING')
        self.assertIs(self.state['draft'], draft)

    def test_confirmed_rejection_send_button_can_retry_without_losing_attachment(self):
        draft=self.compose(); old=draft['operation_id']
        draft['attachments']=[make_attachment('proof.txt', b'proof')]
        self.smtp.submit.return_value={'status':'rejected','notice':'Recipient rejected'}
        self.event('send',operation_id=old)
        self.assertIs(self.state['draft'],draft)
        self.smtp.submit.return_value={'status':'accepted'}
        self.w.send(old)
        self.assertNotEqual(draft['operation_id'],old)
        self.w.advance_send(draft['operation_id'])
        self.assertEqual(self.smtp.submit.call_count,2)
        self.assertEqual(len(self.imap.appended),1)
        parsed=BytesParser(policy=policy.default).parsebytes(self.imap.appended[0])
        self.assertEqual(list(parsed.iter_attachments())[0].get_payload(decode=True),b'proof')

    def test_sent_focus_survives_async_pending_read_and_cache_invalidation(self):
        draft=self.compose(); original=self.imap.list_headers; pending=[True]; refreshed=[]
        @contextmanager
        def refresh():
            refreshed.append(True)
            yield
        def read(*args,**kwargs):
            if len(args)>1 and args[1]==self.w.roles['sent'] and pending[0]:
                raise MailboxError('Syncing',code='pending')
            return original(*args,**kwargs)
        self.imap.interactive_refresh=refresh
        with patch.object(self.imap,'list_headers',side_effect=read):
            self.event('send',operation_id=draft['operation_id'])
            mid=self.state['outgoing_mime']['message_id']
            self.assertEqual(self.state['sent_focus'],mid)
            self.assertTrue(self.w.model()['sent_view_pending'])
            pending[0]=False; self.state['load_retry_at']=0; self.w.load()
        self.assertTrue(refreshed)
        self.assertFalse(self.w.model()['sent_view_pending'])
        active=next(m for m in self.state['conversation'] if reference_key(m)==self.state['active_message'])
        self.assertEqual(active['message_id'],mid)

    def test_exact_sent_header_outside_first_page_is_selected(self):
        original=self.imap.list_headers
        def read(*args,**kwargs):
            result=original(*args,**kwargs)
            if len(args)>1 and args[1]==self.w.roles['sent']:
                result['messages']=[]  # Newer unrelated deliveries fill the initial window.
            return result
        draft=self.compose()
        with patch.object(self.imap,'list_headers',side_effect=read):
            self.event('send',operation_id=draft['operation_id'])
        self.assertEqual(len(self.state['threads']),1)
        self.assertEqual(self.state['conversation'][0]['message_id'],self.state['outgoing_mime']['message_id'])


@unittest.skipUnless(os.getenv('EMAIL_TEST_POSTGRES')=='1','Disposable Email PostgreSQL required')
class DurableController(unittest.TestCase):
    def test_new_reply_reply_all_attachment_are_readable_in_sent_after_restart(self):
        for mode in ('new','reply','reply_all'):
            with self.subTest(mode=mode), ExitStack() as stack:
                for name,value in [('load_email_settings',(default_settings(),None)),('load_metadata',{}),('load_orders',[]),('load_assignees',[])]:
                    stack.enter_context(patch.object(store,name,return_value=value))
                stack.enter_context(patch.object(store,'audit'))
                imap=MailboxFixture(3); provider=Mock(); provider.submit.return_value={'status':'accepted'}
                registry=DurableRegistry(MailStore(connect=Connection)); state={}
                w=Workspace(state,USER,CONFIG,v2.SMTP_CONFIG,imap=imap,smtp=provider,registry=registry)
                w.load(); w.open_thread(state['threads'][0]['thread_key'])
                w.handle({'id':str(uuid.uuid4()),'action':'compose','mode':mode,'message_key':state['active_message']})
                draft=state['draft']; draft.update(to='test@example.test',cc='cc@example.test',bcc='hidden@example.test',
                    subject='Exact durable test',html='<p>Exact sent body</p>')
                draft['attachments']=[make_attachment('proof.txt',b'attachment proof')]
                op=draft['operation_id']; w.send(op); w.advance_send(op); w.advance_send(op)
                self.assertEqual(state['folder'],w.roles['sent'])
                self.assertEqual(state['view'],'mail');self.assertIsNone(state['draft'])
                self.assertEqual(state['send_stage'],'SENT')
                self.assertEqual(state['send_result']['status'],'accepted')
                self.assertEqual(len(imap.appended),1); provider.submit.assert_called_once()
                self.assertIn('Exact sent body',str(w.model()['messages']))
                parsed=BytesParser(policy=policy.default).parsebytes(imap.appended[0])
                self.assertEqual(parsed['Message-ID'],state['send_result']['message_id'])
                if mode!='new':self.assertTrue(parsed['In-Reply-To'])
                self.assertEqual(list(parsed.iter_attachments())[0].get_payload(decode=True),b'attachment proof')
                self.assertIn('hidden@example.test',provider.submit.call_args.args[0]['recipients'])
                restart=Workspace({},USER,CONFIG,v2.SMTP_CONFIG,imap=imap,smtp=provider,registry=DurableRegistry(MailStore(connect=Connection)))
                restart.load();restart.state['folder']=w.roles['sent'];restart.load(force=True)
                self.assertEqual(len(restart.state['threads']),1)
                self.assertEqual(restart.state['threads'][0]['messages'][0]['message_id'],parsed['Message-ID'])


if __name__=='__main__':unittest.main()
