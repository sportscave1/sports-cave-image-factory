"""Critical Inbox regressions. Synthetic providers only, no external I/O."""
from copy import deepcopy
import unittest
import uuid
from unittest.mock import Mock, patch

from tests.test_email_inbox_reliability import Provider
from tests.email_v2_fixtures import CONFIG, USER, fixture_smtp
from support_email_workspace import Workspace, reference_key
from support_email_reads import ReadService, AsyncInbox
from support_email_compose import default_settings, new_draft, ComposeError
from support_email_smtp import SendRegistry, SMTPConfiguration


class Reliability(unittest.TestCase):
    def setUp(self):
        for target, value in [('load_email_settings', (default_settings(), None)), ('audit', None)]:
            p = patch('support_email_store.' + target, return_value=value)
            p.start(); self.addCleanup(p.stop)
        p = patch('supabase_backend.connect', side_effect=AssertionError('Real database forbidden'))
        p.start(); self.addCleanup(p.stop)
        self.provider = Provider(75)
        self.store = Mock(); self.store.read_index.return_value = {}
        self.reads = ReadService(self.provider, self.store)
        self.reads.start = Mock(); self.addCleanup(self.reads.close)
        self.reads.sync()
        self.w = Workspace({}, USER, CONFIG, SMTPConfiguration(), imap=AsyncInbox(CONFIG, self.reads),
                           smtp=fixture_smtp(), registry=SendRegistry())
        self.w.load(defer_body=True)

    def event(self, action, **values):
        return self.w.handle(dict(id=str(uuid.uuid4()), action=action, **values))

    def test_fresh_entry_does_not_select_or_open_saved_reply(self):
        db = Mock(); db.list_drafts.return_value = [{'draft_id':str(uuid.uuid4()), 'subject':'Old refund'}]
        self.w.durable = db
        self.w.state['initial_load_pending'] = True
        self.event('load_initial_mailbox')
        self.assertFalse(self.w.state.get('selected'))
        self.assertEqual(self.w.state['view'], 'mail')
        db.restore_draft.assert_not_called()
        self.assertTrue(self.w.model()['discovery_pending'])
        self.event('load_mail_metadata')
        self.assertEqual(len(self.w.model()['recoverable_drafts']), 1)
        self.assertFalse(any(c[0] in {'body','flag'} for c in self.provider.calls))

    def test_noop_sync_preserves_mailbox_version(self):
        version = self.w.state['mailbox_version']
        self.w.live_check(); self.w.live_check()
        self.assertEqual(version, self.w.state['mailbox_version'])

    def test_failed_publication_cannot_restore_old_revision_with_future_clock(self):
        old = deepcopy(self.reads.value)
        message = next(m for m in old['snapshot']['messages'] if m['unread'])
        self.reads.mutate('set_flag', message, '\\Seen', True)
        self.reads.health['mutation_warning'] = True
        old['observed_at'] = __import__('time').time() + 3600
        self.store.read_index.return_value = old
        with patch('support_email_reads.SNAPSHOT_DB.ready', return_value=True):
            self.reads.restore()
        current = next(m for m in self.reads.value['snapshot']['messages'] if m['uid'] == message['uid'])
        self.assertFalse(current['unread'])

    def test_confirmed_flags_survive_stale_snapshot_across_sessions(self):
        message = next(m for m in self.w.state['snapshot']['messages'] if m['unread'])
        for action, flag, enabled in [('mark_read','\\Seen',True),('mark_unread','\\Seen',False),
                                      ('star','\\Flagged',True),('unstar','\\Flagged',False)]:
            self.w.message_action(action, message)
            version = self.w.state['mailbox_version']
            self.w.live_check()
            self.assertEqual(self.w.state['mailbox_version'], version)
            other = Workspace({}, USER, CONFIG, SMTPConfiguration(), imap=AsyncInbox(CONFIG,self.reads), registry=SendRegistry())
            other.load(defer_body=True)
            actual = next(m for m in other.state['snapshot']['messages'] if m['uid'] == message['uid'])
            self.assertEqual(flag in actual['flags'], enabled, action)

    def test_confirmed_archive_does_not_resurrect(self):
        message = self.w.state['snapshot']['messages'][0]
        self.w.message_action('archive', message)
        self.w.live_check()
        self.assertNotIn(message['uid'], [m['uid'] for m in self.w.state['snapshot']['messages']])

    def test_resume_cannot_use_another_conversation(self):
        source = deepcopy(self.provider.messages[0])  # outside the first 50
        draft = new_draft(CONFIG.address, mode='reply', header=source, text='Original quote')
        self.w.state['draft'] = draft
        self.w._select_thread(self.w.state['threads'][0])
        self.event('resume_composer')
        self.assertEqual(draft.get('source_message', {}).get('message_id'), source['message_id'])
        self.assertNotEqual(self.w.state.get('active_message'), reference_key(self.provider.messages[-1]))
        self.assertTrue(all(m['message_id'] == source['message_id'] for m in self.w.state.get('conversation', [])))

    def test_older_edit_revision_cannot_replace_new_text(self):
        draft = new_draft(CONFIG.address); draft.update(edit_revision=5, html='<p>New</p>')
        self.w.state['draft'] = draft
        self.w._sync_draft({'id':draft['id'], 'edit_revision':4, 'html':'<p>Old</p>'})
        self.assertEqual(draft['html'], '<p>New</p>')

    def test_failed_save_does_not_replace_draft_on_new_compose(self):
        draft = new_draft(CONFIG.address); self.w.state['draft'] = draft
        self.w.durable = Mock(); self.w.durable.save_draft.side_effect = ComposeError('This draft changed in another session.')
        self.event('compose', mode='new', draft={'id':draft['id'], 'html':'<p>Keep me</p>', 'edit_revision':1})
        self.assertEqual(self.w.state['draft']['id'], draft['id'])
        self.assertEqual(self.w.state['draft']['html'], '<p>Keep me</p>')
        self.assertEqual(self.w.state.get('draft_save_status'), 'Conflict')

    def test_rejected_mutation_keeps_rows_and_provider_error_is_not_success(self):
        message = self.w.state['snapshot']['messages'][0]
        before = deepcopy(self.reads.value['snapshot'])
        with patch.object(self.provider, 'move_message', side_effect=OSError('synthetic disconnect')):
            self.event('archive', message_key=reference_key(message))
        self.assertEqual(self.reads.value['snapshot'], before)
        self.assertIn('Could not', self.w.state['notice'])

    def test_inflight_old_index_cannot_publish_after_confirmed_mutation(self):
        import threading
        entered, release = threading.Event(), threading.Event()
        original = self.provider.live_changes
        def delayed(*args, **kwargs):
            result = original(*args, **kwargs);entered.set();release.wait(3);return result
        with patch.object(self.provider, 'live_changes', delayed):
            worker=threading.Thread(target=self.reads.sync);worker.start()
            self.assertTrue(entered.wait(2))
            message=next(m for m in self.w.state['snapshot']['messages'] if m['unread'])
            self.w.message_action('mark_read', message)
            release.set();worker.join(3)
        self.w.live_check()
        self.assertFalse(next(m for m in self.w.state['snapshot']['messages'] if m['uid']==message['uid'])['unread'])

    def test_missing_or_uidvalidity_changed_source_never_substitutes(self):
        source=deepcopy(self.provider.messages[0])
        draft=new_draft(CONFIG.address,mode='reply',header=source,text='Preserved original quote')
        for mutate in ('move','delete','validity'):
            with self.subTest(mutate=mutate):
                self.w.state['draft']=deepcopy(draft)
                self.w._select_thread(self.w.state['threads'][0])
                result=[] if mutate in {'move','delete'} else [dict(source,uidvalidity='999')]
                with patch.object(self.provider,'related_headers',return_value=result):self.event('resume_composer')
                self.assertTrue(self.w.model()['draft_source_unavailable'])
                self.assertEqual(self.w.state['conversation'],[])
                self.assertEqual(self.w.state['draft']['quote_html'],draft['quote_html'])
                self.assertEqual(self.w.state['draft']['to'],draft['to'])

    def test_duplicate_validated_signal_is_acknowledged_without_cache_churn(self):
        import time
        version=self.w.state['mailbox_version']
        with patch('support_email_idle.HUB.snapshot',return_value={'version':'signal','mailbox':CONFIG.address.casefold(),'checked_at':time.time()}):
            self.w.live_check('signal');self.w.live_check('signal')
        self.assertEqual(self.w.state['idle_version'],'signal')
        self.assertEqual(self.w.state['mailbox_version'],version)

    def test_unknown_send_cannot_be_replaced_by_new_composer(self):
        draft=new_draft(CONFIG.address);self.w.state.update(draft=draft,send_result={'status':'unknown'})
        self.event('compose',mode='new')
        self.assertIs(self.w.state['draft'],draft)
        self.assertEqual(self.w.state['send_result']['status'],'unknown')

    def test_move_trash_restore_and_copy_use_provider_destination_identity(self):
        message=deepcopy(self.w.state['snapshot']['messages'][0])
        facade=self.w.imap
        for destination in ['Archive','Trash','Customers','INBOX']:
            facade.move_message(message,destination)
            message=deepcopy(next(m for m in self.provider.messages if m['message_id']==message['message_id']))
            self.reads.sync()
            rows=self.reads.index()['messages']
            self.assertEqual(any(m['uid']==message['uid'] for m in rows),destination=='INBOX')
        facade.copy_message(message,'Trash')
        copied=next(m for m in self.provider.messages if m['folder']=='Trash' and m['message_id']==message['message_id'])
        self.assertNotEqual(copied['uid'],message['uid'])
        self.assertTrue(any(m['uid']==message['uid'] for m in self.reads.index()['messages']))

    def test_uidvalidity_reset_does_not_apply_old_flags_to_new_identity(self):
        message=next(m for m in self.w.state['snapshot']['messages'] if m['unread'])
        self.w.message_action('mark_read',message)
        replacement=dict(deepcopy(message),uidvalidity='999',flags=(),unread=True,message_id='<new-identity@example.test>')
        with patch.object(self.provider,'live_changes',return_value=dict(reset=True,flags={},added=[replacement],uidvalidity='999',live_uid=int(replacement['uid']),total=1,checked_at=__import__('time').time())):
            self.reads.sync()
        self.w.live_check()
        self.assertEqual(self.w.state['snapshot']['uidvalidity'],'999')
        self.assertTrue(self.w.state['snapshot']['messages'][0]['unread'])


if __name__ == '__main__': unittest.main()
