"""Independent OS processes against opt-in disposable native PostgreSQL."""
from copy import deepcopy
import multiprocessing
import os
import unittest
import uuid

from support_email_compose import ComposeError, new_draft
from support_email_durable import MailStore
from support_email_idle_store import SignalStore, key


def connect():
    import psycopg
    from psycopg.conninfo import conninfo_to_dict
    from psycopg.rows import dict_row
    dsn=os.environ['LOCAL_ACCOUNT_TEST_DSN']
    if conninfo_to_dict(dsn).get('host') not in ('127.0.0.1','localhost'):
        raise ValueError('Only disposable loopback PostgreSQL is permitted')
    return psycopg.connect(dsn,row_factory=dict_row)


def contender(kind, mailbox, value, barrier, results):
    store=MailStore(connect=connect)
    barrier.wait(timeout=10)
    if kind=='outbox':
        results.put(bool(store.claim(mailbox,value)))
    elif kind=='draft':
        try:store.save_draft(mailbox,'synthetic-actor',value);results.put('saved')
        except ComposeError:results.put('conflict')
    else:
        results.put(SignalStore(connect=connect).claim(mailbox,value))


@unittest.skipUnless(os.getenv('LOCAL_ACCOUNT_TEST_DSN'),'Requires disposable native PostgreSQL')
class NativeConcurrency(unittest.TestCase):
    def setUp(self):
        self.mailbox=uuid.uuid4().hex+'@example.test'
        self.store=MailStore(connect=connect)

    def race(self,kind,values):
        ctx=multiprocessing.get_context('spawn')
        barrier=ctx.Barrier(len(values));results=ctx.Queue()
        workers=[ctx.Process(target=contender,args=(kind,self.mailbox,v,barrier,results)) for v in values]
        for worker in workers:worker.start()
        try:
            output=[results.get(timeout=15) for _ in workers]
            for worker in workers:
                worker.join(timeout=10);self.assertEqual(worker.exitcode,0)
            return output
        finally:
            for worker in workers:
                if worker.is_alive():worker.terminate();worker.join()

    def test_concurrent_processes_claim_one_frozen_send(self):
        operation=str(uuid.uuid4())
        self.store.prepare(self.mailbox,operation,dict(bytes=b'Synthetic only',message_id='<'+operation+'>',recipients=['test@example.test']))
        self.assertEqual(sorted(self.race('outbox',[operation]*3)),[False,False,True])
        self.assertEqual(self.store.get(self.mailbox,operation)['attempts'],1)
        # A dead sender's uncertain boundary must never become a fresh send.
        with connect() as conn:
            conn.execute("UPDATE support_email_outbox SET due_at=now()-interval '1 minute' WHERE mailbox=%s",(self.mailbox,))
        self.store.due(self.mailbox)
        self.assertEqual(self.store.get(self.mailbox,operation)['status'],'unknown')
        self.assertFalse(self.store.claim(self.mailbox,operation))

    def test_concurrent_processes_preserve_draft_revision_conflict(self):
        draft=new_draft(self.mailbox,mode='new');self.store.save_draft(self.mailbox,'synthetic-actor',draft)
        copies=[dict(deepcopy(draft),html='<p>Writer '+str(i)+'</p>') for i in range(3)]
        self.assertEqual(sorted(self.race('draft',copies)),['conflict','conflict','saved'])
        saved=self.store.restore_draft(self.mailbox,'synthetic-actor',draft['id'])
        self.assertEqual(saved['_storage_version'],2)
        self.assertIn(saved['html'],[d['html'] for d in copies])
        self.assertIsNone(self.store.restore_draft(self.mailbox,'other-actor',draft['id']))

    def test_process_lease_renewal_loss_and_stale_publication(self):
        self.assertEqual(sorted(self.race('lease',['one','two','three'])),[False,False,True])
        signals=SignalStore(connect=connect)
        with connect() as conn:
            owner=conn.execute('SELECT value FROM app_sync_state WHERE key=%s',(key(self.mailbox,'lease'),)).fetchone()['value']['owner']
        self.assertTrue(signals.renew(self.mailbox,owner))
        self.assertFalse(signals.renew(self.mailbox,'not-owner'))
        with connect() as conn:
            conn.execute("UPDATE app_sync_state SET value=jsonb_set(value,'{until}','0'::jsonb) WHERE key=%s",(key(self.mailbox,'lease'),))
        self.assertTrue(signals.claim(self.mailbox,'replacement'))
        self.assertFalse(signals.renew(self.mailbox,owner))
        status=dict(uidvalidity=1,uidnext=2,unseen=0,messages=1)
        with self.assertRaises(RuntimeError):signals.publish(self.mailbox,owner,status,'stale')
        signals.publish(self.mailbox,'replacement',status,'current')
        self.assertEqual(signals.read(self.mailbox)['version'],'current')


if __name__=='__main__':unittest.main()
