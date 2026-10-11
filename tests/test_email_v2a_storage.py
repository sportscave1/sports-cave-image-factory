"""Disposable SQL ownership, recovery and independent-index regression tests."""
import os, uuid, unittest
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch
from tests.test_email_durable_delivery import Connection
from tests.test_email_inbox_reliability import Provider
from tests.email_v2_fixtures import CONFIG, USER, fixture_smtp
from support_email_compose import new_draft, make_attachment, default_settings, ComposeError
from support_email_durable import MailStore, DurableRegistry
from support_email_snapshot import SnapshotStore
from support_email_reads import ReadService, AsyncInbox
from support_email_workspace import Workspace
from support_email_smtp import SMTPConfiguration

@unittest.skipUnless(os.getenv('EMAIL_TEST_POSTGRES')=='1','Requires disposable loopback SQL')
class Storage(unittest.TestCase):
    def setUp(self):
        self.config=replace(CONFIG,address='v2a-'+str(uuid.uuid4())+'@example.test')
        self.store=MailStore(connect=Connection)
        self.provider=Provider(75);self.provider.configuration=self.config
        self.w=Workspace({},USER,self.config,SMTPConfiguration(),imap=self.provider,smtp=fixture_smtp(),registry=DurableRegistry(self.store))
        for name,value in [('load_email_settings',(default_settings(),None)),('audit',None)]:
            p=patch('support_email_store.'+name,return_value=value);p.start();self.addCleanup(p.stop)
        self.w.load()

    def draft(self):
        draft=new_draft(self.config.address,mode='reply',header=self.provider.messages[0],text='Original outside first 50')
        draft['attachments']=[make_attachment('synthetic.txt',b'untouched attachment')]
        self.store.save_draft(self.config.address,USER['id'],draft)
        return draft

    def test_exact_actor_mailbox_and_multiple_draft_recovery(self):
        first=self.draft();second=self.draft()
        self.assertEqual(len(self.store.list_drafts(self.config.address,USER['id'])),2)
        self.assertIsNone(self.store.restore_draft(self.config.address,'different-actor',first['id']))
        self.assertIsNone(self.store.restore_draft('different@example.test',USER['id'],first['id']))
        self.w.restore_draft(first['id'])
        self.assertEqual(self.w.state['draft']['id'],first['id'])
        self.assertFalse(self.w.model()['draft_source_unavailable'])
        self.assertEqual(self.w.state['draft']['attachments'],first['attachments'])
        self.assertEqual(self.w.state['conversation'][0]['uid'],'1')

    def test_first_keystroke_can_recover_before_first_autosave(self):
        self.w.handle({'id':str(uuid.uuid4()), 'action':'compose', 'mode':'new'})
        draft = deepcopy(self.w.state['draft'])
        self.assertIsNotNone(self.store.restore_draft(self.config.address, USER['id'], draft['id']))
        draft.update(html='<p>First unsaved keystroke</p>', edit_revision=1, attachment_ids=[])
        self.w.state['draft'] = None  # Lost server session, persisted browser journal remains.
        self.w.recover_draft_copy(draft)
        self.assertEqual(self.w.state['draft']['html'], draft['html'])
        self.assertNotEqual(self.w.state['draft']['id'], draft['id'])

    def test_conflict_recovery_forks_without_overwriting_text_or_attachments(self):
        original=self.draft();stale=deepcopy(original)
        original['html']='<p>Other tab</p>';self.store.save_draft(self.config.address,USER['id'],original)
        stale.update(html='<p>Unsaved local edit</p>',edit_revision=3)
        with self.assertRaises(ComposeError):self.store.save_draft(self.config.address,USER['id'],stale)
        self.w.recover_draft_copy(stale)
        copy=self.w.state['draft']
        self.assertNotEqual(copy['id'],original['id'])
        self.assertNotEqual(copy['operation_id'],original['operation_id'])
        self.assertEqual(copy['html'],stale['html'])
        self.assertEqual(copy['attachments'],original['attachments'])
        self.assertEqual(self.store.restore_draft(self.config.address,USER['id'],original['id'])['html'],original['html'])

    def test_pending_send_cannot_be_forked_into_duplicate_send(self):
        draft=self.draft();mime={'bytes':b'Subject: Fixture\r\n\r\nPrivate synthetic text','message_id':'<'+str(uuid.uuid4())+'@example.test>','recipients':['fixture@example.test']}
        self.store.prepare(self.config.address,draft['operation_id'],mime,actor=USER['id'])
        with self.assertRaisesRegex(ComposeError,'saved send operation'):self.w.recover_draft_copy(draft)
        self.w.discover_recovery();warnings=self.w.model()['unresolved_receipts']
        self.assertEqual(warnings[0]['transport_status'],'queued')
        self.assertNotIn('Private synthetic text',str(warnings))
        self.assertEqual(self.store.unresolved_receipts(self.config.address,'other'),[])

    def test_independent_services_merge_confirmed_writes_and_reject_late_snapshot(self):
        from support_email_db_guard import SNAPSHOT_DB
        SNAPSHOT_DB.until=0
        with self.store.transaction() as cur:
            cur.execute('CREATE TABLE IF NOT EXISTS app_sync_state(key text PRIMARY KEY,value jsonb,status text,updated_at timestamptz)')
            for sql in Path('migrations/20260930055619_support_email_inbox_snapshot.sql').read_text().split(';'):
                if sql.strip():cur.execute(sql)
        store=SnapshotStore(connect=Connection)
        first=ReadService(self.provider,store);second=ReadService(self.provider,SnapshotStore(connect=Connection))
        for reads in (first,second):reads.start=Mock();self.addCleanup(reads.close)
        first.sync();second.restore();old=deepcopy(first.value)
        a,b=[m for m in old['snapshot']['messages'] if m['unread']][:2]
        AsyncInbox(self.config,first).set_flag(a,'\\Seen',True)
        AsyncInbox(self.config,second).set_flag(b,'\\Flagged',True)
        old['observed_at'] = __import__('time').time()+3600
        store.save_index(self.config,old)  # Even clock skew cannot let a pre-write revision win.
        current=first.index()['messages']
        self.assertFalse(next(m for m in current if m['uid']==a['uid'])['unread'])
        self.assertIn('\\Flagged',next(m for m in current if m['uid']==b['uid'])['flags'])
        AsyncInbox(self.config,first).move_message(a,'Archive')
        self.assertNotIn(a['uid'],[m['uid'] for m in second.index()['messages']])

    def test_delayed_provider_ack_holds_cross_worker_write_lease(self):
        import threading
        from support_email_provider import MailboxError
        with self.store.transaction() as cur:
            cur.execute('CREATE TABLE IF NOT EXISTS app_sync_state(key text PRIMARY KEY,value jsonb,status text,updated_at timestamptz)')
        store=SnapshotStore(connect=Connection)
        first=ReadService(self.provider,store);second=ReadService(self.provider,SnapshotStore(connect=Connection))
        self.addCleanup(first.close);self.addCleanup(second.close)
        entered,release=threading.Event(),threading.Event();errors=[]
        original=self.provider.set_flag
        def delayed(*args):original(*args);entered.set();release.wait(3)
        message=deepcopy(self.provider.messages[0])
        def write():
            try:first.mutate('set_flag',message,'\\Seen',True)
            except Exception as error:errors.append(error)
        with patch.object(self.provider,'set_flag',side_effect=delayed):
            worker=threading.Thread(target=write);worker.start();self.assertTrue(entered.wait(2))
            with self.assertRaises(MailboxError):second.mutate('set_flag',message,'\\Seen',False)
            release.set();worker.join(3)
        self.assertEqual(errors,[])
        self.assertFalse(self.provider.messages[0]['unread'])

if __name__=='__main__':unittest.main()
