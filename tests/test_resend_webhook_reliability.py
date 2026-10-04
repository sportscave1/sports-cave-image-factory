import asyncio
from contextlib import nullcontext
import json
import os
import threading
import time
import unittest
import uuid
from unittest.mock import Mock,patch
import httpx
import webhook_server
import crm_resend_event_worker as worker
from crm_logic import now


class HttpReliabilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_burst_backpressure_and_slow_orders_leave_health_responsive(self):
        started=threading.Event();release=threading.Event();active=0;peak=0;lock=threading.Lock()
        def receipt(*args,**kwargs):
            nonlocal active,peak
            self.assertTrue(kwargs['defer'])
            with lock:active+=1;peak=max(peak,active)
            started.set();release.wait(3)
            with lock:active-=1
        def orders_work(**kwargs):
            release.wait(3)
            return {'shopify_orders_fetched':50}
        with patch('crm_resend.verify_resend',return_value=True),patch('crm_webhooks.receive_resend',side_effect=receipt),patch.object(worker,'log'),patch('supabase_backend.sync_latest_paid_orders_to_supabase',side_effect=orders_work),patch('supabase_backend.is_configured',return_value=True),patch('supabase_backend.shopify_order_reconciliation_lease',return_value=nullcontext(True)):
            import shopify_order_reconciliation_worker as orders
            thread=threading.Thread(target=orders.run_once);thread.start()
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=webhook_server.app),base_url='http://fixture') as client:
                tasks=[asyncio.create_task(client.post('/webhooks/resend/crm',content='{}',headers={'svix-id':'evt_'+str(i)})) for i in range(40)]
                for _ in range(100):
                    if started.is_set():break
                    await asyncio.sleep(.01)
                latencies=[]
                for _ in range(20):
                    at=time.perf_counter();response=await client.get('/healthz');latencies.append(time.perf_counter()-at)
                    self.assertEqual(response.status_code,200)
                release.set();responses=await asyncio.gather(*tasks);thread.join(4)
                self.assertEqual(peak,4);self.assertTrue(any(r.status_code==503 for r in responses))
                self.assertTrue(all(r.status_code in (200,503) for r in responses))
                self.assertLess(max(latencies),1)
                print('Synthetic burst health max_ms=%.2f peak_db_admissions=%d'%(max(latencies)*1000,peak))

    async def test_ack_does_not_wait_for_reconciliation_and_signature_is_preserved(self):
        with patch('crm_resend.verify_resend',return_value=True),patch('crm_webhooks.receive_resend',return_value=True) as receipt,patch('crm_workspace_store.WorkspaceRecords.reconcile_events',side_effect=AssertionError('No processing on HTTP path')):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=webhook_server.app),base_url='http://fixture') as client:
                at=time.perf_counter();response=await client.post('/webhooks/resend/crm',content='{}',headers={'svix-id':'event'})
                self.assertEqual(response.status_code,200);self.assertLess(time.perf_counter()-at,1)
                self.assertTrue(receipt.call_args.kwargs['defer'])
                with patch('crm_resend.verify_resend',return_value=False):
                    response=await client.post('/webhooks/resend/crm',content='{}')
                    self.assertEqual(response.status_code,401)
                self.assertEqual(receipt.call_count,1)

    async def test_failed_commit_is_not_acknowledged(self):
        with patch('crm_resend.verify_resend',return_value=True),patch('crm_webhooks.receive_resend',side_effect=RuntimeError('private-payload')):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=webhook_server.app),base_url='http://fixture') as client:
                response=await client.post('/webhooks/resend/crm',content='{}',headers={'svix-id':'event'})
                self.assertEqual(response.status_code,503);self.assertNotIn('private',response.text)


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable loopback database required')
class DurableReliabilityTests(unittest.TestCase):
    def setUp(self):
        from crm_store import Store
        from tests.crm_db_fixture import connect
        self.store=Store(connect);self.event='evt_'+uuid.uuid4().hex;self.provider=str(uuid.uuid4())
        self.payload={'type':'email.delivered','created_at':now().isoformat(),'data':{'email_id':self.provider}}
        worker._stop.clear()
        self.addCleanup(self.store.q,"DELETE FROM crm_webhook_events WHERE provider='resend' AND event_id=%s",(self.event,))
        self.addCleanup(self.store.q,'DELETE FROM crm_delivery_events WHERE event_id=%s',(self.event,))

    def test_durable_duplicate_restart_and_failure_retry(self):
        from crm_webhooks import receive_resend
        self.assertTrue(receive_resend(self.store,self.event,self.payload,defer=True))
        self.assertFalse(receive_resend(self.store,self.event,self.payload,defer=True))
        self.assertEqual(self.store.q('SELECT count(*) AS n FROM crm_delivery_events WHERE event_id=%s',(self.event,),True)['n'],1)
        with patch('crm_workspace_store.WorkspaceRecords.reconcile_events',side_effect=RuntimeError('temporary')):
            worker.run_once(self.store)
        row=self.store.q("SELECT * FROM crm_webhook_events WHERE provider='resend' AND event_id=%s",(self.event,),True)
        self.assertEqual(row['status'],'PENDING');self.assertEqual(row['attempts'],1)
        self.store.q("UPDATE crm_webhook_events SET lease_until=NULL WHERE provider='resend' AND event_id=%s",(self.event,))
        # Fresh consumer instance needs no in-memory payload or pending task.
        with patch('crm_workspace_store.WorkspaceRecords.reconcile_events') as reconcile:
            worker.run_once(self.store);worker.run_once(self.store)
            reconcile.assert_called_once_with(self.provider)
        self.assertEqual(self.store.q("SELECT status FROM crm_webhook_events WHERE provider='resend' AND event_id=%s",(self.event,),True)['status'],'DONE')
        self.assertFalse(receive_resend(self.store,self.event,self.payload,defer=True))

    def test_atomic_receipt_and_queue_rollback(self):
        from crm_webhooks import receive_resend
        from crm_workspace_store import WorkspaceRecords
        from tests.crm_db_fixture import connect
        class FailQueue:
            def __enter__(self):self.conn=connect();self.conn.__enter__();return self
            def __exit__(self,*args):return self.conn.__exit__(*args)
            def execute(self,sql,args=()):
                if 'INSERT INTO crm_webhook_events' in sql:raise RuntimeError('queue unavailable')
                return self.conn.execute(sql,args)
        with patch.object(WorkspaceRecords,'db',return_value=FailQueue()):
            with self.assertRaises(RuntimeError):receive_resend(self.store,self.event,self.payload,defer=True)
        self.assertIsNone(self.store.q('SELECT event_id FROM crm_delivery_events WHERE event_id=%s',(self.event,),True))

    def test_existing_reconciliation_runs_in_consumer_transaction(self):
        from crm_webhooks import receive_resend
        receive_resend(self.store,self.event,self.payload,defer=True)
        self.assertEqual(worker.run_once(self.store),1)
        self.assertEqual(self.store.q("SELECT status FROM crm_webhook_events WHERE provider='resend' AND event_id=%s",(self.event,),True)['status'],'DONE')

    def test_deferred_receipt_excludes_slow_processing_cost(self):
        from crm_webhooks import receive_resend
        with patch('crm_workspace_store.WorkspaceRecords.reconcile_events',side_effect=lambda *_:time.sleep(.25)) as reconcile:
            at=time.perf_counter();receive_resend(self.store,self.event,self.payload);old=time.perf_counter()-at
            reconcile.reset_mock()
            at=time.perf_counter();receive_resend(self.store,self.event,self.payload,defer=True);new=time.perf_counter()-at
            reconcile.assert_not_called();self.assertLess(new,.20);self.assertGreater(old,.25)
        print('Synthetic receipt old_ms=%.2f deferred_ms=%.2f (250ms reconciliation fixture)'%(old*1000,new*1000))


class ProcessIsolationTests(unittest.TestCase):
    def test_orders_start_one_child_and_stop_waits_for_exit(self):
        import shopify_order_reconciliation_worker as orders
        process=Mock();process.poll.return_value=None
        with patch.object(orders,'enabled',return_value=True),patch.object(orders,'_process',None),patch.object(orders.subprocess,'Popen',return_value=process) as spawn:
            self.assertTrue(orders.start());self.assertFalse(orders.start());spawn.assert_called_once()
            self.assertIn('shopify_order_reconciliation_worker.py',spawn.call_args.args[0][-1])
            orders.stop();process.terminate.assert_called_once();process.wait.assert_called_once_with(timeout=15)

    def test_consumer_stop_joins_without_cancelling_transaction(self):
        thread=Mock();thread.is_alive.return_value=False
        with patch.object(worker,'_thread',thread):worker.stop()
        thread.join.assert_called_once_with(timeout=10);worker._stop.clear()
