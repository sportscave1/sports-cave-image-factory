"""Real overlapping transactions on the dedicated synthetic PostgreSQL cluster."""
import os
import time
import uuid
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime,timezone
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch
from tests.campaign_real_postgres import connect
from tests import test_crm_campaign_v8 as v8
from tests.test_crm_campaign_v8 import timing
from tests.test_crm import ADMIN
from tests.test_crm_send_flow import LIVE
from crm_campaign_store import CampaignStore
from crm_campaign_schedule import change_pending,schedule_gate,activate_due
from crm_campaign_dispatch import prepare
from crm_logic import now


@unittest.skipUnless(os.getenv('CRM_TEST_REAL_POSTGRES')=='1','Explicit isolated real PostgreSQL required')
class ConcurrentTests(unittest.TestCase):
    def setUp(self):
        self.guard=patch('requests.sessions.Session.request',side_effect=AssertionError('No external I/O'));self.guard.start();self.addCleanup(self.guard.stop)
        self.store=CampaignStore(connect);self.store.db=connect
        self.ids=[]
        self.queue=lambda:v8.DurableTests.queue(self)
        # No test shares active campaigns with another test.
        self.store.q("UPDATE crm_campaigns SET status='PAUSED' WHERE status IN ('SCHEDULED','SENDING')")
        saved=self.queue();self.identity=saved['id']
        self.revision=self.store.state('campaign-timing:'+str(self.identity))['operation_id']
        self.original=self.rows()
        c=self.store.get('campaigns',self.identity)
        self.content=self.store.template(c['template_id'],c['template_version'])
        self.campaign=c

    def rows(self):return self.store.q('SELECT * FROM crm_marketing_sends WHERE campaign_id=%s ORDER BY id',(self.identity,))

    def amend(self,store=None,mode=None,operation=None,user=None):
        with patch.dict(os.environ,LIVE):
            return change_pending(store or self.store,user or ADMIN,self.identity,mode or timing(day='2099-10-12'),operation or str(uuid.uuid4()),confirmed=True,expected_operation_id=self.revision)

    def worker(self,store):
        return prepare(SimpleNamespace(store=store,clock=now),self.campaign,self.content,set())

    def overlap(self,first,second):
        locked=Event();release=Event();pids=[]
        @contextmanager
        def paused_connection():
            with connect() as conn:
                pids.append(conn.info.backend_pid)
                class Proxy:
                    def execute(inner,sql,args=()):
                        result=conn.execute(sql,args)
                        if 'FOR UPDATE' in sql and 'crm_campaigns' in sql and not locked.is_set():
                            locked.set()
                            if not release.wait(8):raise AssertionError('Test lock release timed out')
                        return result
                yield Proxy()
        slow=CampaignStore(connect);slow.db=paused_connection
        with ThreadPoolExecutor(2) as pool:
            a=pool.submit(first,slow)
            self.assertTrue(locked.wait(5),'First transaction did not hold campaign lock')
            b=pool.submit(second,self.store)
            try:
                deadline=time.monotonic()+5
                while time.monotonic()<deadline:
                    waiting=self.store.q("SELECT pid FROM pg_stat_activity WHERE datname='campaign_hardening' AND wait_event_type='Lock'")
                    if waiting:break
                    time.sleep(.02)
                self.assertTrue(waiting,'Second PostgreSQL session never overlapped on the lock')
                self.assertNotIn(waiting[0]['pid'],pids)
            finally:release.set()
            outcomes=[]
            for future in (a,b):
                try:outcomes.append(future.result(12))
                except Exception as exc:outcomes.append(exc)
        self.assert_preserved()
        return outcomes

    def assert_preserved(self):
        rows=self.rows();self.assertEqual(len(rows),3)
        for old,new in zip(self.original,rows):
            for field in ('id','recipient_hash','shopify_customer_id','idempotency_key','template_id','template_version'):
                self.assertEqual(old[field],new[field],field)
        self.assertEqual(self.store.template(self.campaign['template_id'],self.campaign['template_version']),self.content)

    def test_two_administrators_stale_revision(self):
        a,b=self.overlap(lambda s:self.amend(s,user={**ADMIN,'id':'admin-a'}),lambda s:self.amend(s,timing(day='2099-10-13'),user={**ADMIN,'id':'admin-b'}))
        self.assertIsInstance(a,dict);self.assertIsInstance(b,ValueError);self.assertIn('changed elsewhere',str(b))

    def test_simultaneous_duplicate_operation(self):
        op=str(uuid.uuid4())
        a,b=self.overlap(lambda s:self.amend(s,operation=op),lambda s:self.amend(s,operation=op))
        self.assertEqual(a,b);self.assertIsInstance(a,dict)

    def test_edit_then_worker_cannot_claim_future_recipients(self):
        a,b=self.overlap(lambda s:self.amend(s),self.worker)
        self.assertIsInstance(a,dict);self.assertEqual(b,[])
        self.assertTrue(all(r['status']=='PENDING' for r in self.rows()))

    def test_worker_preparation_then_edit(self):
        a,b=self.overlap(self.worker,lambda s:self.amend(s))
        self.assertEqual(a,[]);self.assertIsInstance(b,dict)

    def test_worker_preparation_then_send_now(self):
        a,b=self.overlap(self.worker,lambda s:self.amend(s,{'mode':'now'}))
        self.assertEqual(a,[]);self.assertIsInstance(b,dict)
        self.assertEqual(len(self.worker(self.store)),1)
        self.assert_preserved()

    def test_edit_waits_while_worker_actually_claims_due_recipients(self):
        self.amend(mode={'mode':'now'})
        self.revision=self.store.state('campaign-timing:'+str(self.identity))['operation_id']
        a,b=self.overlap(self.worker,lambda s:self.amend(s))
        self.assertEqual(len(a),1);self.assertIsInstance(b,ValueError)
        self.assertTrue(all(r['status']=='SUBMITTING' for r in self.rows()))

    def test_send_now_then_batch_preparation_and_retry(self):
        a,b=self.overlap(lambda s:self.amend(s,{'mode':'now'}),self.worker)
        self.assertIsInstance(a,dict)
        # PostgreSQL now() is transaction-start time: a worker that began before
        # Send Now may safely defer these just-due rows until its next tick.
        if not b:b=self.worker(self.store)
        self.assertEqual(len(b),1)
        again=self.worker(self.store)
        self.assertEqual(b[0][1]['recipient_ids'],again[0][1]['recipient_ids'])
        self.assertEqual(b[0][1]['request_hash'],again[0][1]['request_hash'])
        self.assertEqual(b[0][1]['idempotency_key'],again[0][1]['idempotency_key'])
        self.assertTrue(all(r['status']=='SUBMITTING' for r in self.rows()))
        with self.assertRaises(ValueError):self.amend()

    def test_send_now_during_outage_gate(self):
        a,b=self.overlap(lambda s:self.amend(s,{'mode':'now'}),lambda s:schedule_gate(s,False,datetime(2099,10,11,tzinfo=timezone.utc)))
        self.assertIsInstance(a,dict);self.assertIsNone(b)
        self.assertTrue(all(r['status']=='PENDING' for r in self.rows()))

    def test_outage_gate_wins_and_edit_rejects(self):
        a,b=self.overlap(lambda s:schedule_gate(s,False,datetime(2099,10,11,tzinfo=timezone.utc)),lambda s:self.amend(s))
        self.assertIsNone(a);self.assertIsInstance(b,ValueError)
        self.assertTrue(all(r['status']=='BLOCKED' for r in self.rows()))

    def test_postponement_during_worker_activation(self):
        a,b=self.overlap(lambda s:self.amend(s),lambda s:activate_due(s,clock=lambda:datetime(2099,10,11,tzinfo=timezone.utc)))
        self.assertIsInstance(a,dict);self.assertEqual(b,0)
        self.assertEqual(self.store.get('campaigns',self.identity)['status'],'SCHEDULED')

    def test_database_error_rolls_back_and_retry_is_idempotent(self):
        op=str(uuid.uuid4())
        def fail(conn,*args):conn.execute('SELECT 1/0')
        with patch.object(self.store,'_history',side_effect=fail):
            with self.assertRaises(Exception):self.amend(operation=op)
        self.assertEqual(self.rows(),self.original)
        self.assertFalse(self.store.state('campaign-timing-operation:'+str(self.identity)+':'+op))
        receipt=self.amend(operation=op)
        self.assertEqual(self.amend(operation=op),receipt)
        self.assert_preserved()

    def test_connection_loss_rolls_back_and_retry_is_safe(self):
        op=str(uuid.uuid4())
        def disconnect(conn,*args):
            with connect() as other:
                other.execute('SELECT pg_terminate_backend(%s)',(conn.info.backend_pid,))
            conn.execute('SELECT 1')
        with patch.object(self.store,'_history',side_effect=disconnect):
            with self.assertRaises(Exception):self.amend(operation=op)
        self.assertEqual(self.rows(),self.original)
        self.assertFalse(self.store.state('campaign-timing-operation:'+str(self.identity)+':'+op))
        receipt=self.amend(operation=op)
        self.assertEqual(self.amend(operation=op),receipt)
        self.assert_preserved()

if __name__=='__main__':unittest.main()
