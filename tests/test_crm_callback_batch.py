"""Disposable SQL and fake transport only. No production callbacks or sends."""
from copy import deepcopy
from concurrent.futures import Future
import os
import unittest
import uuid
from unittest.mock import Mock,patch

import crm_resend_event_worker as worker
from crm_workspace_store import WorkspaceRecords


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable loopback database required')
class CallbackBatchTests(unittest.TestCase):
    def setUp(self):
        from tests.test_crm_batch_dispatch import DispatchTests
        self.fixture=DispatchTests();self.fixture.setUp()
        self.store=self.fixture.store;self.events=[];worker._stop.clear()
    def tearDown(self):
        worker._stop.clear()
        for event in self.events:
            self.store.q("DELETE FROM crm_webhook_events WHERE provider='resend' AND event_id=%s",(event,))
            self.store.q('DELETE FROM crm_delivery_events WHERE event_id=%s',(event,))
        self.fixture.tearDown();self.fixture.doCleanups()
    def recipients(self,count):
        from crm_campaign_dispatch import dispatch
        identity=self.fixture.queue(count);dispatch(self.fixture.engine)
        self.store.q("UPDATE crm_campaigns SET status='SENT',sent_at=now() WHERE id=%s",(identity,))
        return identity,self.fixture.sends(identity)
    def enqueue(self,provider,event_type='email.delivered',event=None,bounce=None):
        from crm_webhooks import receive_resend
        from crm_logic import now
        event=event or 'evt_'+uuid.uuid4().hex
        payload={'type':event_type,'created_at':now().isoformat(),'data':{'email_id':provider}}
        if bounce:payload['data']['bounce']={'type':bounce}
        received=receive_resend(self.store,event,payload,defer=True)
        if event not in self.events:self.events.append(event)
        return event,received
    def queue_rows(self):
        return self.store.q("SELECT event_id,status,attempts,error_code FROM crm_webhook_events WHERE provider='resend' AND event_id=ANY(%s) ORDER BY event_id",(self.events,))
    def revision(self):return self.store.state('resend_callback_revision').get('revision')

    def test_bounded_batch_deduplicates_providers_and_preserves_sent_campaign(self):
        from crm_campaign_home_data import rows
        identity,recipients=self.recipients(10)
        before=self.store.q('SELECT * FROM crm_campaigns WHERE id=%s',(identity,),True)
        original_sends=deepcopy(self.fixture.sends(identity))
        kinds=['email.delivered','email.opened','email.clicked']
        for i in range(150):self.enqueue(recipients[i%10]['provider_email_id'],kinds[i%3])
        self.assertFalse(self.enqueue(recipients[0]['provider_email_id'],event=self.events[0])[1])
        calls=[];original=WorkspaceRecords.reconcile_events_many
        def measured(records,ids):calls.append(ids);return original(records,ids)
        with patch.object(WorkspaceRecords,'reconcile_events_many',measured):
            self.assertEqual(worker.run_once(self.store),100)
            self.assertEqual(worker.run_once(self.store),50)
            self.assertEqual(worker.run_once(self.store),0)
        self.assertEqual([len(ids) for ids in calls],[10,10])
        self.assertTrue(all(r['status']=='DONE' for r in self.queue_rows()))
        self.assertTrue(self.revision())
        item=next(r for r in rows(self.store,search=before['name']) if str(r['id'])==str(identity))
        self.assertEqual([item[k] for k in ('delivered','opens','clicks')],[10,10,10])
        self.assertEqual(self.store.q('SELECT * FROM crm_campaigns WHERE id=%s',(identity,),True),before)
        self.assertEqual(self.fixture.sends(identity),original_sends)

    def test_early_callback_is_associated_when_receipt_arrives_and_revision_advances(self):
        from crm_campaign_dispatch import dispatch
        identity=self.fixture.queue(1);provider=str(uuid.uuid4())
        event,_=self.enqueue(provider)
        self.assertEqual(worker.run_once(self.store),1)
        self.assertIsNone(self.store.q('SELECT send_id FROM crm_delivery_events WHERE event_id=%s',(event,),True)['send_id'])
        first=self.revision()
        with patch.object(self.fixture.transport,'send',return_value={'ids':[provider],'status':200,'remaining':'8','retry_after':0}):
            dispatch(self.fixture.engine)
        self.assertTrue(self.store.q('SELECT send_id FROM crm_delivery_events WHERE event_id=%s',(event,),True)['send_id'])
        self.assertNotEqual(first,self.revision())
        self.assertEqual(self.queue_rows()[0]['status'],'DONE')

    def test_poison_event_rolls_back_its_changes_but_healthy_peers_commit(self):
        _,recipients=self.recipients(3)
        for recipient in recipients:self.enqueue(recipient['provider_email_id'])
        poison=recipients[1]['provider_email_id'];marker='callback-failed-'+uuid.uuid4().hex
        original=WorkspaceRecords.reconcile_events_many
        def fail(records,ids):
            if poison in ids:
                records.set_state(marker,{'must_rollback':True})
                raise ValueError('Synthetic private provider data')
            return original(records,ids)
        with patch.object(WorkspaceRecords,'reconcile_events_many',fail):
            self.assertEqual(worker.run_once(self.store),2)
        self.assertEqual(self.store.state(marker),{})
        states=self.queue_rows()
        self.assertEqual(sum(r['status']=='DONE' for r in states),2)
        bad=next(r for r in states if r['status']=='PENDING')
        self.assertEqual(bad['attempts'],1);self.assertEqual(bad['error_code'],'processing_unavailable')
        self.store.q("UPDATE crm_webhook_events SET lease_until=NULL WHERE event_id=%s",(bad['event_id'],))
        self.assertEqual(worker.run_once(self.store),1)
        self.assertTrue(all(r['status']=='DONE' for r in self.queue_rows()))

    def test_failed_outer_commit_retains_queue_and_rolls_back_association_and_revision(self):
        _,recipients=self.recipients(1);event,_=self.enqueue(recipients[0]['provider_email_id'])
        before=self.revision();original=self.store.db
        class FailedCommit:
            def __enter__(self):self.inner=original();return self.inner.__enter__()
            def __exit__(self,typ,*args):
                if typ is None:
                    self.inner.__exit__(RuntimeError,RuntimeError('Commit unavailable'),None)
                    raise RuntimeError('Commit unavailable')
                return self.inner.__exit__(typ,*args)
        with patch.object(self.store,'db',FailedCommit):self.assertEqual(worker.run_once(self.store),0)
        self.assertEqual(self.queue_rows()[0]['status'],'PENDING')
        self.assertEqual(before,self.revision())
        self.assertIsNone(self.store.q('SELECT send_id FROM crm_delivery_events WHERE event_id=%s',(event,),True)['send_id'])
        self.assertEqual(worker.run_once(self.store),1)

    def test_lost_commit_response_is_reconciled_from_queue_without_duplicate_processing(self):
        _,recipients=self.recipients(1);self.enqueue(recipients[0]['provider_email_id'])
        original=self.store.db
        class LostAck:
            def __enter__(self):self.inner=original();return self.inner.__enter__()
            def __exit__(self,typ,*args):
                result=self.inner.__exit__(typ,*args)
                if typ is None:raise TimeoutError('Post-commit response lost')
                return result
        with patch.object(self.store,'db',LostAck):self.assertEqual(worker.run_once(self.store),0)
        self.assertEqual(self.queue_rows()[0]['status'],'DONE')
        revision=self.revision();self.assertEqual(worker.run_once(self.store),0)
        self.assertEqual(revision,self.revision())

    def test_permanent_bounce_and_complaint_stop_state_remains_atomic(self):
        _,recipients=self.recipients(3)
        self.enqueue(recipients[0]['provider_email_id'],'email.bounced',bounce='Permanent')
        self.enqueue(recipients[1]['provider_email_id'],'email.complained')
        self.enqueue(recipients[2]['provider_email_id'],'email.bounced',bounce='Transient')
        self.assertEqual(worker.run_once(self.store),3)
        for recipient in recipients[:2]:self.assertTrue(self.store.suppressed(recipient['shopify_customer_id'],recipient['recipient_hash']))
        last=recipients[2];self.assertFalse(self.store.suppressed(last['shopify_customer_id'],last['recipient_hash']))

    def test_failure_splitting_and_stop_are_bounded_without_dropping_queue(self):
        for _ in range(40):self.enqueue(str(uuid.uuid4()))
        with patch.object(WorkspaceRecords,'reconcile_events_many',side_effect=RuntimeError('Unavailable')) as reconcile:
            self.assertEqual(worker.run_once(self.store),0)
        self.assertLessEqual(reconcile.call_count,worker.MAX_RECONCILIATIONS)
        self.assertTrue(all(r['status']=='PENDING' for r in self.queue_rows()))
        worker._stop.set()
        with patch.object(WorkspaceRecords,'reconcile_events_many') as reconcile:
            self.assertEqual(worker.run_once(self.store),0);reconcile.assert_not_called()


class CallbackPoolTests(unittest.TestCase):
    def test_each_checkout_has_explicit_transaction_and_returns_connection_on_failure(self):
        from crm_callback_store import Connection
        from contextlib import contextmanager
        events=[];conn=Mock()
        @contextmanager
        def transaction():
            events.append('begin')
            try:yield
            except ValueError:events.append('rollback');raise
            else:events.append('commit')
        @contextmanager
        def checkout(**kwargs):
            events.append('checkout')
            try:yield conn
            finally:events.append('return')
        conn.transaction.side_effect=transaction
        pool=Mock();pool.connection.side_effect=checkout
        with patch('crm_callback_store.pool',return_value=pool):
            for fail in (False,True):
                try:
                    with Connection() as borrowed:
                        borrowed.execute('SELECT 1')
                        if fail:raise ValueError('Rollback')
                except ValueError:pass
        self.assertEqual(conn.transaction.call_count,2)
        self.assertEqual(events,['checkout','begin','commit','return','checkout','begin','rollback','return'])
        self.assertIsNone(borrowed.conn)
        pool.connection.assert_called_with(timeout=2)


class CallbackRefreshTests(unittest.TestCase):
    def setUp(self):
        self.store=Mock();self.store.connect='fixture';self.store.q.return_value={'revision':'new'}
        self.state={'campaign_home_callback_revision':'old','campaign_home_window':('fixed','window')}
        def ready(state,store,key,load,**kwargs):
            future=Future();future.set_result(load())
            state.setdefault('campaign_home_cache',{})[(store.connect,key)]=(0,future)
            return future
        self.patch=patch('crm_campaign_callback_refresh.job',side_effect=ready)
        self.patch.start();self.addCleanup(self.patch.stop)
    def cached(self,key,value,pending=False):
        future=Future()
        if not pending:future.set_result(value)
        self.state.setdefault('campaign_home_cache',{})[(self.store.connect,key)]=(0,future)
        return future
    def test_revision_refreshes_only_completed_affected_projections_and_retains_last_good(self):
        from crm_campaign_callback_refresh import watch
        rows=[{'id':'same','status':'SENT','delivered':4}]
        self.cached(('table','filter',0),rows)
        self.cached(('delivery',),{'sent_emails':4,'click_rate':0.,'bounce_rate':0.})
        counts=self.cached(('counts',),{'sent':1})
        attribution=self.cached(('attribution',),{'orders':1})
        watch(self.state,self.store)
        cache=self.state['campaign_home_cache']
        self.assertNotIn(('fixture',('table','filter',0)),cache)
        self.assertNotIn(('fixture',('delivery',)),cache)
        self.assertIs(cache[('fixture',('counts',))][1],counts)
        self.assertIs(cache[('fixture',('attribution',))][1],attribution)
        self.assertEqual(self.state['campaign_home_resolved'][('fixture',('table','filter',0))],rows)
        self.assertEqual(self.state['campaign_home_window'],('fixed','window'))
    def test_frequent_callbacks_do_not_discard_running_read_and_starve_publication(self):
        from crm_campaign_callback_refresh import watch
        future=self.cached(('table','filter',0),None,pending=True)
        watch(self.state,self.store)
        self.assertIs(self.state['campaign_home_cache'][('fixture',('table','filter',0))][1],future)
        self.store.q.return_value={'revision':'newer'};watch(self.state,self.store)
        rows=[{'delivered':5}];future.set_result(rows)
        watch(self.state,self.store)
        self.assertEqual(self.state['campaign_home_resolved'][('fixture',('table','filter',0))],rows)
        self.assertFalse(self.state['campaign_home_callback_dirty'])
    def test_first_callback_after_missing_revision_invalidates_once_and_unchanged_does_not(self):
        from crm_campaign_callback_refresh import watch
        self.state={'campaign_home_callback_revision':None}
        self.cached(('table',),[]);watch(self.state,self.store)
        self.assertNotIn(('fixture',('table',)),self.state['campaign_home_cache'])
        future=self.cached(('table',),[]);watch(self.state,self.store)
        self.assertIs(self.state['campaign_home_cache'][('fixture',('table',))][1],future)

    def test_first_probe_after_table_and_callback_does_not_miss_invalidation(self):
        from crm_campaign_callback_refresh import watch
        self.state={};self.cached(('table',),[{'delivered':0}])
        watch(self.state,self.store)
        self.assertNotIn(('fixture',('table',)),self.state['campaign_home_cache'])
        self.assertEqual(self.state['campaign_home_callback_revision'],'new')

    def test_failed_probe_retains_last_good_table_and_revision(self):
        from crm_campaign_callback_refresh import watch
        future=self.cached(('table',),[{'delivered':7}])
        failed=Future();failed.set_exception(RuntimeError('Unavailable'))
        with patch('crm_campaign_callback_refresh.job',return_value=failed):watch(self.state,self.store)
        self.assertIs(self.state['campaign_home_cache'][('fixture',('table',))][1],future)
        self.assertEqual(self.state['campaign_home_callback_revision'],'old')
