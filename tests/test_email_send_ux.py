import unittest
import uuid
from unittest.mock import Mock, patch
from email import policy
from email.parser import BytesParser

from tests import test_support_email_v2 as v2
from tests.email_v2_fixtures import MAILBOX, USER, WORKER
from tests.test_support_email import header
import support_email_compose as compose
import support_email_smtp as smtp


class SendUXTests(unittest.TestCase):
    setUp = v2.WorkspaceTests.setUp
    event = v2.WorkspaceTests.event
    open = v2.WorkspaceTests.open
    compose = v2.WorkspaceTests.compose

    def test_acceptance_and_bounded_exact_message_id_checks_survive_reruns(self):
        draft=self.compose(); stages=[];self.w.progress=lambda p,l:stages.append(p)
        self.imap.find_message_id=Mock(return_value=[])
        self.event('send',operation_id=draft['operation_id'])
        self.assertEqual(self.state['send_result']['status'],'accepted')
        self.assertEqual(self.state['sent_result']['status'],'pending')
        self.assertEqual(stages,[15,100]) # The fixture SMTP itself has no transport stages.
        mid=self.state['outgoing_mime']['message_id']
        self.event('auto_check_sent',operation_id=draft['operation_id'])
        self.assertEqual(self.imap.find_message_id.call_count,1) # too soon
        for _ in range(5):
            self.state['sent_check_at']=0
            self.event('auto_check_sent',operation_id=draft['operation_id'])
        self.assertEqual(self.imap.find_message_id.call_count,4)
        self.assertEqual(self.state['sent_checks'],3)
        self.assertTrue(all(c.args[1]==mid for c in self.imap.find_message_id.call_args_list))
        self.imap.find_message_id.return_value=['123']
        self.event('check_sent')
        self.assertEqual(self.w.model()['sent_result']['status'],'present')
        self.event('send',operation_id=draft['operation_id'])
        self.smtp.submit.assert_called_once()
        self.assertFalse(self.imap.appended)

    def test_rejected_and_uncertain_never_reach_100_or_auto_poll(self):
        for status in ('rejected','unknown'):
            with self.subTest(status=status):
                self.state.pop('draft',None);self.state['send_result']={}
                draft=self.compose();stages=[];self.w.progress=lambda p,l:stages.append(p)
                self.smtp.submit.return_value={'status':status,'notice':'fixture'}
                self.imap.find_message_id=Mock()
                self.event('send',operation_id=draft['operation_id'])
                self.assertNotIn(100,stages)
                self.event('auto_check_sent',operation_id=draft['operation_id'])
                self.imap.find_message_id.assert_not_called()

    def test_real_smtp_stage_hooks_are_ordered_and_cannot_change_delivery(self):
        conn=Mock(esmtp_features={});conn.ehlo.return_value=(250,b'ok')
        conn.mail.return_value=(250,b'ok');conn.rcpt.return_value=(250,b'ok');conn.data.return_value=(250,b'ok')
        stages=[]
        result=smtp.SMTPProvider(v2.SMTP_CONFIG,connection_factory=Mock(return_value=conn)).submit(
            {'bytes':b'fixture','recipients':['test@example.test']},mailbox=MAILBOX,progress=lambda p,l:stages.append(p))
        self.assertEqual(result['status'],'accepted');self.assertEqual(stages,[45,60,75,100])
        result=smtp.SMTPProvider(v2.SMTP_CONFIG,connection_factory=Mock(return_value=conn)).submit(
            {'bytes':b'fixture','recipients':['test@example.test']},mailbox=MAILBOX,progress=Mock(side_effect=ValueError))
        self.assertEqual(result['status'],'accepted')

    def test_quote_choice_survives_sync_and_new_reply_resets(self):
        draft=self.compose('reply');self.assertFalse(draft['include_quote'])
        self.w._sync_draft({'id':draft['id'],'include_quote':True})
        self.w.model();self.w.model()
        self.assertTrue(draft['include_quote'])
        self.state['draft']=None
        self.assertFalse(self.compose('reply_all')['include_quote'])


class ReplyQuoteTests(unittest.TestCase):
    def test_acceptance_receipt_cannot_be_downgraded_by_cleanup_interruption(self):
        registry=smtp.SendRegistry();operation=str(uuid.uuid4())
        provider=Mock()
        def accepted_then_interrupted(mime, *, mailbox, progress):
            progress(100,'Sent')
            raise KeyboardInterrupt()
        provider.submit.side_effect=accepted_then_interrupted
        mime={'bytes':b'fixture','message_id':'<fixture@example.test>'}
        with self.assertRaises(KeyboardInterrupt):
            registry.submit(operation,MAILBOX,mime,provider,progress=lambda p,l:None)
        receipt=registry.submit(operation,MAILBOX,mime,provider)
        self.assertEqual(receipt['status'],'accepted')
        provider.submit.assert_called_once()

    def test_defaults_and_saved_choices_for_both_profiles_preserve_headers(self):
        settings=compose.default_settings()
        for user in (USER,WORKER):
            for mode in ('reply','reply_all','forward'):
                draft=compose.new_draft(MAILBOX,mode=mode,header=header(),text='Prior message',
                                        signature=compose.selected_signature(settings,user))
                self.assertEqual(draft['include_quote'],mode=='forward')
                draft.update(to='customer@example.test',subject='Reply fixture',html='<p>Thanks.</p>')
                for choice in (True,False):
                    draft['include_quote']=choice
                    mime=compose.build_mime(draft,MAILBOX,'Sports Cave',settings['signatures'],as_draft=True)
                    restored=compose.edit_mailbox_draft(mime['bytes'],MAILBOX,header())
                    self.assertEqual(restored['include_quote'],choice)
                    self.assertEqual(restored['signature'],draft['signature'])
                    if mode!='forward':
                        message=BytesParser(policy=policy.default).parsebytes(mime['bytes'])
                        self.assertEqual(str(message['In-Reply-To']),draft['in_reply_to'])
                        self.assertEqual(restored['references'],draft['references'])


if __name__=='__main__':unittest.main()
