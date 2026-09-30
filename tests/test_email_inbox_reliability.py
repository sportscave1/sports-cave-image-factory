"""Read-only fixtures: no provider, production DB, or SMTP access."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import threading
import time
import unittest
from unittest.mock import Mock, patch

from support_email_reads import ReadService, AsyncInbox
from support_email_snapshot import SnapshotStore, encode, decode
from support_email_provider import MailboxError
from support_email_workspace import Workspace
from support_email_compose import default_settings
from support_email_smtp import SMTPConfiguration
from tests.email_v2_fixtures import MailboxFixture, fixture_smtp, USER, CONFIG


class Provider(MailboxFixture):
    configuration = CONFIG
    def discover_folders(self, **kwargs):return super().discover_folders()
    def interactive_refresh(self):
        from contextlib import nullcontext
        return nullcontext()


class InboxReliability(unittest.TestCase):
    def setUp(self):
        self.mail = Provider(60)
        self.store = Mock()
        self.store.read_index.return_value = {}
        self.reads = ReadService(self.mail,self.store)
        self.addCleanup(self.reads.close)
        self.facade = AsyncInbox(CONFIG,self.reads)
        for target,value in [('load_email_settings',(default_settings(),None)),('load_metadata',{}),('audit',None)]:
            patcher=patch('support_email_store.'+target,return_value=value)
            patcher.start();self.addCleanup(patcher.stop)
        self.w = Workspace({},USER,CONFIG,SMTPConfiguration(),imap=self.facade,smtp=fixture_smtp())

    def ready(self):
        self.reads.sync()
        self.reads.start = Mock()  # Deterministic manual clock/ticks for unit tests.

    def finish_jobs(self):
        for future,_ in list(self.reads.jobs.values()):future.result(timeout=3)

    def test_initial_list_is_bounded_metadata_without_bodies_or_enrichment(self):
        self.ready();self.w.load(defer_body=True)
        self.assertEqual(len(self.w.model()['threads']),50)
        self.assertFalse(any(c[0] in ('body','attachment','related','flag') for c in self.mail.calls))
        self.assertEqual(len(self.reads.value['snapshot']['messages']),50)
        self.assertEqual(len([c for c in self.mail.calls if c[0]=='headers']),1)

    def test_snapshot_remains_during_disconnect_and_recovers(self):
        self.ready();self.w.load(defer_body=True)
        before=deepcopy(self.w.model());self.mail.fail=True
        self.reads.sync();self.w.load(force=True,defer_body=True)
        after=self.w.model()
        self.assertEqual(after['threads'],before['threads'])
        self.assertEqual(after['selected'],before['selected'])
        self.assertEqual(len(self.reads.value['snapshot']['messages']),50)
        self.mail.fail=False;self.reads.sync()
        self.assertEqual(self.reads.health['state'],'CONNECTED')

    def test_incremental_sync_uses_uid_delta_after_first_page(self):
        self.ready();self.mail.calls.clear();self.reads.sync()
        self.assertEqual([c[0] for c in self.mail.calls],['live'])
        self.assertEqual(self.reads.value['snapshot']['live_uid'],60)
        self.assertEqual(self.store.save_index.call_count,2)

    def test_coalesces_read_and_does_not_share_socket_or_ui_state(self):
        gate=threading.Event();calls=[]
        self.addCleanup(gate.set)
        def load():calls.append(1);gate.wait(2);return {'body':'fixture'}
        for _ in range(8):
            with self.assertRaises(MailboxError) as raised:self.reads.request(('fixture',),load)
            self.assertEqual(raised.exception.code,'pending')
        gate.set();self.finish_jobs()
        self.assertEqual(self.reads.request(('fixture',),load),{'body':'fixture'})
        self.assertEqual(len(calls),1)

    def test_late_body_cannot_replace_current_selection_and_revisit_cached(self):
        self.ready();self.w.load(defer_body=True)
        first,second=self.w.state['threads'][:2]
        self.w.open_thread(first['thread_key']);self.finish_jobs()
        self.w.open_thread(second['thread_key']);self.finish_jobs()
        current=self.w.state['active_message']
        self.w.handle({'id':'11429b00-2130-4e1d-a6f0-aaf373002031','action':'load_visible_body','message_key':'old'})
        self.assertEqual(self.w.state['active_message'],current)
        self.assertEqual(self.w.state['body_pending'],current)
        self.w.handle({'id':'11429b00-2130-4e1d-a6f0-aaf373002032','action':'load_visible_body','message_key':current})
        self.w.open_thread(second['thread_key']);self.finish_jobs()
        count=len([c for c in self.mail.calls if c[0]=='body'])
        self.w.open_thread(second['thread_key'])
        self.assertEqual(len([c for c in self.mail.calls if c[0]=='body']),count)
        self.assertEqual(self.w.state['selected'],second['thread_key'])

    def test_pending_body_is_not_connection_failure(self):
        self.ready();self.w.load(defer_body=True)
        with patch.object(self.facade,'read_message',side_effect=MailboxError('Loading',code='pending')):
            self.w.open_thread(self.w.state['threads'][0]['thread_key'])
        self.assertFalse(self.w.state.get('recovery_state'))
        self.assertTrue(self.w.model()['body_pending'])
        self.assertFalse(self.w.model()['error'])

    def test_failure_backoff_and_auth_are_not_fast_retry_loops(self):
        with patch.object(self.mail,'list_headers',side_effect=MailboxError('Safe error',code='authentication')):
            self.reads.sync()
        self.assertEqual(self.reads.health['category'],'authentication')
        self.assertGreater(self.reads.health['retry_at']-self.reads.clock(),890)

    def test_database_failure_cannot_erase_fresh_index(self):
        self.store.save_index.side_effect=RuntimeError('unavailable')
        self.ready()
        self.assertEqual(len(self.reads.index()['messages']),50)

    def test_snapshot_round_trip_dates_and_no_body_persistence(self):
        self.ready();store=SnapshotStore();cur=Mock()
        from contextlib import contextmanager
        @contextmanager
        def transaction():yield cur
        store.transaction=transaction
        value=deepcopy(self.reads.value)
        value['snapshot']['messages'][0].update(html='PRIVATE BODY',password='PRIVATE PASSWORD')
        store.save_index(CONFIG,value)
        payload=cur.execute.call_args.args[1][1]
        self.assertNotIn('PRIVATE',payload)
        restored=decode(json.loads(payload))
        self.assertIsInstance(restored['snapshot']['messages'][0]['received_at'],datetime)
        self.assertEqual(len(restored['snapshot']['messages']),50)

    def test_restore_persisted_snapshot_before_remote_failure(self):
        self.ready();saved=deepcopy(self.reads.value)
        self.store.read_index.return_value=saved
        recovered=ReadService(self.mail,self.store)
        self.addCleanup(recovered.close)
        def fail():
            self.assertEqual(recovered.value,saved)
            recovered.stop.set()
        recovered.sync=fail
        recovered.run()
        self.assertEqual(recovered.value,saved)


if __name__=='__main__':unittest.main()
