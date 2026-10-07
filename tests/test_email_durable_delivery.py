"""Real SQL fault tests; opt in only with disposable loopback PostgreSQL running."""
from contextlib import nullcontext
from copy import deepcopy
import os
import json
import threading
import unittest
import uuid
from unittest.mock import Mock, patch

from support_email_durable import MailStore, DurableRegistry, OutboxWorker, decode
from support_email_compose import ComposeError
from tests import crm_db_fixture as db
from tests.email_v2_fixtures import CONFIG


class Connection(db.Connection):
    def cursor(self):return nullcontext(self)
    def execute(self,sql,args=()):
        chunks=sql.split('%s');sql=chunks[0]+''.join('$'+str(i)+part for i,part in enumerate(chunks[1:],1))
        request=db.urllib.request.Request('http://127.0.0.1:8879',
            data=json.dumps({'sql':sql,'args':list(args)},default=str).encode(),headers={'Content-Type':'application/json'})
        try:
            with db.urllib.request.urlopen(request,timeout=20) as response:self.result=db.Cursor(json.load(response))
        except db.urllib.error.HTTPError as error:
            with error:message=json.load(error)['error']
            raise RuntimeError(message) from None
        return self.result
    def fetchone(self):return self.result.fetchone()
    def fetchall(self):return self.result.fetchall()
    def commit(self):pass


@unittest.skipUnless(os.environ.get('EMAIL_TEST_POSTGRES')=='1','Disposable Email PostgreSQL fixture required')
class DurableDelivery(unittest.TestCase):
    def setUp(self):
        self.store=MailStore(connect=Connection)
        self.registry=DurableRegistry(self.store)
        self.mailbox='fixture-'+str(uuid.uuid4())+'@example.test'
        self.op=str(uuid.uuid4())
        self.mime={'bytes':b'Subject: Fixture\r\n\r\nSafe fixture',
                   'message_id':'<'+self.op+'@example.test>','recipients':['fixture@example.test']}
        self.provider=Mock();self.provider.submit.return_value={'status':'accepted'}
        self.imap=Mock();self.imap.find_message_id.return_value=None

    def prepare(self):return self.registry.prepare(self.op,self.mailbox,self.mime,actor='admin',folder='Sent')
    def submit(self):return self.registry.submit(self.op,self.mailbox,self.mime,self.provider)
    def expire(self):
        with self.store.transaction() as cur:
            cur.execute("UPDATE support_email_outbox SET due_at=now()-interval '1 minute' WHERE mailbox=%s",(self.mailbox,))

    def test_repeated_send_and_restart_send_once(self):
        self.prepare();self.assertEqual(self.submit()['status'],'accepted')
        second=DurableRegistry(MailStore(connect=Connection))
        self.assertEqual(second.submit(self.op,self.mailbox,self.mime,self.provider)['status'],'accepted')
        self.provider.submit.assert_called_once()
        self.assertEqual(self.store.get(self.mailbox,self.op)['attempts'],1)

    def test_send_claim_covers_provider_data_deadline(self):
        self.prepare()
        row=self.store.claim(self.mailbox,self.op)
        from datetime import datetime
        start=datetime.fromisoformat(str(row['updated_at']).replace('Z','+00:00'))
        due=datetime.fromisoformat(str(row['due_at']).replace('Z','+00:00'))
        self.assertGreaterEqual((due-start).total_seconds(),300)

    def test_concurrent_registry_claims_send_once(self):
        self.prepare();errors=[]
        def send():
            try:DurableRegistry(self.store).submit(self.op,self.mailbox,self.mime,self.provider)
            except Exception as error:errors.append(error)
        threads=[threading.Thread(target=send) for _ in range(2)]
        for thread in threads:thread.start()
        for thread in threads:thread.join()
        self.assertEqual(errors,[]);self.provider.submit.assert_called_once()

    def test_frozen_mime_cannot_change_on_retry(self):
        self.prepare();changed=dict(self.mime,bytes=b'different')
        self.registry.submit(self.op,self.mailbox,changed,self.provider)
        self.assertEqual(self.provider.submit.call_args.args[0]['bytes'],self.mime['bytes'])

    def test_database_failure_before_send_never_calls_provider(self):
        with patch.object(self.store,'prepare',side_effect=RuntimeError('DB')):
            with self.assertRaises(RuntimeError):self.submit()
        self.provider.submit.assert_not_called()

    def test_database_failure_after_provider_never_resends(self):
        self.prepare()
        with patch.object(self.store,'finish',side_effect=RuntimeError('DB')):
            with self.assertRaises(RuntimeError):self.submit()
        self.assertEqual(self.store.get(self.mailbox,self.op)['status'],'in_progress')
        self.expire();self.store.due(self.mailbox)
        self.submit();self.provider.submit.assert_called_once()

    def test_timeout_after_acceptance_reconciles_without_resend(self):
        self.provider.submit.return_value={'status':'unknown','error_category':'TIMEOUT'}
        self.assertEqual(self.submit()['status'],'unknown')
        self.imap.find_message_id.return_value='42'
        result=DurableRegistry(self.store).reconcile(self.op,self.mailbox,self.imap,'Sent')
        self.assertEqual(result['status'],'accepted')
        self.submit();self.provider.submit.assert_called_once()
        self.assertEqual(self.store.get(self.mailbox,self.op)['copy_status'],'present')

    def test_absent_sent_copy_does_not_prove_rejection(self):
        self.provider.submit.return_value={'status':'unknown'};self.submit()
        self.assertEqual(self.registry.reconcile(self.op,self.mailbox,self.imap,'Sent')['status'],'unknown')
        self.submit();self.provider.submit.assert_called_once()

    def test_accepted_progress_survives_disconnect(self):
        def accepted(mime,*,mailbox,progress):
            progress(100,'Sent');raise OSError('disconnect after acceptance')
        self.provider.submit.side_effect=accepted
        with self.assertRaises(OSError):self.submit()
        self.assertEqual(self.store.get(self.mailbox,self.op)['status'],'accepted')

    def test_rejected_preserves_frozen_content(self):
        self.provider.submit.return_value={'status':'rejected','error_category':'PROVIDER_5XX'}
        self.assertEqual(self.submit()['status'],'rejected')
        row=self.store.get(self.mailbox,self.op)
        self.assertEqual(decode(row['payload'])['bytes'],self.mime['bytes'])
        self.submit();self.provider.submit.assert_called_once()

    def test_queued_worker_restart_delivers_once(self):
        self.prepare()
        config=Mock(address=self.mailbox)
        worker=OutboxWorker(config,Mock(),DurableRegistry(self.store))
        self.assertTrue(worker.tick(self.imap,self.provider))
        self.assertEqual(self.store.get(self.mailbox,self.op)['status'],'accepted')
        self.provider.submit.assert_called_once();self.imap.append_message.assert_called_once()
        self.expire();self.assertFalse(worker.tick(self.imap,self.provider))

    def test_interrupted_send_worker_only_reconciles(self):
        self.prepare();self.store.claim(self.mailbox,self.op);self.expire()
        OutboxWorker(Mock(address=self.mailbox),Mock(),self.registry).tick(self.imap,self.provider)
        self.provider.submit.assert_not_called()
        self.assertEqual(self.store.get(self.mailbox,self.op)['status'],'unknown')

    def test_sent_append_restart_cannot_duplicate(self):
        self.submit()
        self.imap.append_message.side_effect=OSError('lost APPEND acknowledgement')
        first=self.registry.save_sent(self.op,self.mailbox,self.imap,self.mime,'Sent','append')
        self.assertEqual(first['status'],'unknown')
        DurableRegistry(self.store).save_sent(self.op,self.mailbox,self.imap,self.mime,'Sent','append')
        self.imap.append_message.assert_called_once()
        self.imap.find_message_id.return_value='42'
        self.assertEqual(self.registry.save_sent(self.op,self.mailbox,self.imap,self.mime,'Sent','append')['status'],'present')

    def draft(self):
        return {'id':str(uuid.uuid4()),'operation_id':self.op,'to':'fixture@example.test','cc':'','bcc':'',
                'subject':'Saved subject','html':'<p>Unsaved work matters</p>','attachments':[{'data':b'fixture'}],
                'references':['<parent@example.test>']}

    def test_draft_survives_store_restart_with_attachments_and_context(self):
        draft=self.draft();self.store.save_draft(self.mailbox,'admin',draft)
        restored=MailStore(connect=Connection).restore_draft(self.mailbox,'admin')
        self.assertEqual(restored,draft)
        self.assertIsNone(self.store.restore_draft(self.mailbox,'other'))

    def test_stale_tab_cannot_overwrite_or_resurrect_discarded_draft(self):
        draft=self.draft();self.store.save_draft(self.mailbox,'admin',draft);stale=deepcopy(draft)
        draft['html']='new';self.store.save_draft(self.mailbox,'admin',draft)
        with self.assertRaises(ComposeError):self.store.save_draft(self.mailbox,'admin',stale)
        self.store.discard(self.mailbox,'admin',draft['id'])
        with self.assertRaises(ComposeError):self.store.save_draft(self.mailbox,'admin',draft)
        self.assertIsNone(self.store.restore_draft(self.mailbox,'admin'))

    def test_accepted_draft_not_restored_as_unsent(self):
        self.store.save_draft(self.mailbox,'admin',self.draft());self.prepare();self.submit()
        self.assertIsNone(self.store.restore_draft(self.mailbox,'admin'))
        self.assertEqual(self.store.latest_sent(self.mailbox,'admin')['status'],'accepted')

    def test_unique_message_id_and_private_tables(self):
        self.prepare()
        with self.assertRaises(RuntimeError):self.store.prepare(self.mailbox,str(uuid.uuid4()),self.mime)
        with self.store.transaction() as cur:
            cur.execute("SELECT has_table_privilege('anon','support_email_outbox','SELECT') AS allowed")
            self.assertFalse(cur.fetchone()['allowed'])
            cur.execute("SELECT relrowsecurity FROM pg_class WHERE relname='support_email_drafts'")
            self.assertTrue(cur.fetchone()['relrowsecurity'])

    def test_reconciliation_is_bounded(self):
        self.provider.submit.return_value={'status':'unknown'};self.submit()
        for _ in range(6):self.expire();self.assertIsNotNone(self.store.due(self.mailbox))
        self.expire();self.assertIsNone(self.store.due(self.mailbox))

    def test_transient_confirmed_rejections_retry_bounded_with_cooldown(self):
        self.provider.submit.return_value={'status':'rejected','retryable':True,'error_category':'PROVIDER_4XX'}
        self.assertEqual(self.submit()['status'],'in_progress')
        self.submit();self.provider.submit.assert_called_once() # Cooldown honoured.
        self.expire();self.submit();self.expire()
        self.assertEqual(self.submit()['status'],'rejected')
        self.assertEqual(self.provider.submit.call_count,3)
        self.expire();self.assertIsNone(self.store.due(self.mailbox))

    def test_transient_failure_then_recovery_uses_same_mime(self):
        self.provider.submit.return_value={'status':'rejected','retryable':True,'error_category':'NETWORK'}
        self.submit();self.expire();self.provider.submit.return_value={'status':'accepted'}
        self.assertEqual(self.submit()['status'],'accepted')
        self.assertEqual(self.provider.submit.call_count,2)
        self.assertEqual(self.store.get(self.mailbox,self.op)['attempts'],2)

    def test_workspace_preserves_draft_until_sent_folder_is_available(self):
        from dataclasses import replace
        from support_email_workspace import Workspace
        from support_email_smtp import SMTPConfiguration
        from support_email_compose import new_draft
        from tests.email_v2_fixtures import USER
        config=replace(CONFIG,address=self.mailbox)
        w=Workspace({},USER,config,SMTPConfiguration(),imap=self.imap,smtp=self.provider,registry=self.registry)
        draft=new_draft(self.mailbox);draft.update(to='fixture@example.test',subject='Accepted locally',html='<p>Stored reply</p>')
        w.state['draft']=draft
        w.send(draft['operation_id']);self.provider.submit.assert_not_called()
        self.assertEqual(self.store.get(self.mailbox,draft['operation_id'])['status'],'queued')
        with patch.object(w,'audit'):
            w.advance_send(draft['operation_id'])
        self.assertEqual(w.state['send_stage'],'CONFIRMING_SENT_COPY')
        self.assertIs(w.state['draft'],draft)
        self.assertIn('Stored reply',w.state['last_sent']['html'])
        self.imap.find_message_id.assert_not_called();self.imap.append_message.assert_not_called()
        restored=Workspace({},USER,config,SMTPConfiguration(),imap=self.imap,smtp=self.provider,registry=DurableRegistry(self.store))
        restored.restore_draft()
        self.assertEqual(restored.state['last_sent']['operation_id'],draft['operation_id'])
        self.assertIn('Stored reply',restored.state['last_sent']['html'])
        self.assertIsNone(restored.state.get('draft'))

    def test_persistent_inbox_lease_and_cursor_restart(self):
        from dataclasses import replace
        from pathlib import Path
        from support_email_snapshot import SnapshotStore
        from support_email_reads import ReadService
        from support_email_db_guard import SNAPSHOT_DB
        from tests.test_email_inbox_reliability import Provider
        from support_email_provider import MailboxError
        SNAPSHOT_DB.until=0
        self.addCleanup(setattr,SNAPSHOT_DB,'until',0)
        with self.store.transaction() as cur:
            cur.execute('CREATE TABLE IF NOT EXISTS app_sync_state(key text PRIMARY KEY,value jsonb,status text,updated_at timestamptz)')
            for sql in Path('migrations/20260930055619_support_email_inbox_snapshot.sql').read_text().split(';'):
                if sql.strip():cur.execute(sql)
        config=replace(CONFIG,address=self.mailbox)
        provider=Provider(60);provider.configuration=config
        first=SnapshotStore(connect=Connection)
        reads=ReadService(provider,first);self.addCleanup(reads.close)
        reads.sync();saved=deepcopy(reads.value)
        self.assertEqual(len(saved['snapshot']['messages']),50)
        restarted=ReadService(provider,SnapshotStore(connect=Connection));self.addCleanup(restarted.close)
        provider.calls.clear()
        self.assertTrue(first.claim('inbox-index:'+self.mailbox,'fixture-owner'))
        restarted.sync();self.assertEqual(provider.calls,[])
        self.assertEqual(restarted.value['snapshot']['live_uid'],saved['snapshot']['live_uid'])
        persisted=deepcopy(restarted.value)
        first.release('inbox-index:'+self.mailbox,'fixture-owner')
        with patch.object(provider,'live_changes',side_effect=MailboxError('Disconnected',code='network')):
            restarted.sync()
        self.assertEqual(restarted.value,persisted)
        restarted.sync()
        self.assertEqual(len(restarted.value['snapshot']['messages']),50)
        self.assertEqual(restarted.health['state'],'CONNECTED')


if __name__=='__main__':unittest.main()
