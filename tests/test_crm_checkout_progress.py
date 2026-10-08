"""Read-only projection + real disposable SQL/worker integration, fake providers."""
from copy import deepcopy
from datetime import timedelta
import os
import unittest
from unittest.mock import patch
from crm_logic import now,date
from crm_checkout_progress import columns,progress,listing
from crm_checkout_analytics import checkouts,window,details
from tests import test_crm_checkout_queue_repair as queue


class Projection(unittest.TestCase):
    def setUp(self):
        self.at=now();self.steps=[{'step_id':str(i)} for i in range(3)];self.schema=columns(self.steps)
        self.row={'checkout_key':'stable','created_at':self.at,'analytics':{'email':'name@example.test','shopify_abandoned':True},
                  'steps':self.steps,'enrollment_id':'journey','current_step':0,'flow_status':'ACTIVE','automation_status':'ACTIVE',
                  'next_due_at':self.at+timedelta(minutes=10),'sends':[]}
    def labels(self,row=None,schema=None):return [c['label'] for c in progress(row or self.row,schema or self.schema,self.at)]
    def accepted(self,index=0):
        self.row['sends'].append({'enrollment_id':'journey','step':index,'step_id':str(index),'status':'ACCEPTED','provider_id':'receipt'})
    def test_persisted_countdown_only_current_and_waiting(self):
        self.assertEqual(self.labels(),['Countdown','Waiting','Waiting'])
        self.assertEqual(progress(self.row,self.schema,self.at)[0]['due_at'],self.row['next_due_at'].isoformat())
    def test_acceptance_and_next_persisted_schedule(self):
        self.accepted();self.row.update(current_step=1,next_due_at=self.at+timedelta(hours=12))
        self.assertEqual(self.labels(),['Sent ✓','Countdown','Waiting'])
    def test_all_completed_receipts(self):
        for i in range(3):self.accepted(i)
        self.row['flow_status']='COMPLETED';self.assertEqual(self.labels(),['Sent ✓']*3)
    def test_no_provider_receipt_never_sent(self):
        for status in ('ACCEPTED','PENDING','SUBMITTING','UNCERTAIN','FAILED','BLOCKED'):
            self.row['sends']=[{'enrollment_id':'journey','step':0,'status':status}]
            self.assertNotEqual(self.labels()[0],'Sent ✓')
    def test_other_flow_receipt_cannot_mark_current_email_sent(self):
        self.accepted();self.row['sends'][0]['enrollment_id']='other';self.assertEqual(self.labels()[0],'Countdown')
    def test_published_reorder_and_added_steps_match_stable_ids(self):
        self.accepted();schema=columns([self.steps[1],self.steps[0],{'step_id':'new'},{'step_id':'fourth'}])
        self.assertEqual(self.labels(schema=schema),['Waiting','Sent ✓','—','—'])
    def test_disabled_new_entry_preserves_old_frozen_schedule(self):
        schema=columns([dict(s,enabled=False) for s in self.steps])
        self.assertEqual(self.labels(schema=schema)[0],'Countdown')
        self.row['enrollment_id']=None;self.assertEqual(self.labels(schema=schema),['Disabled']*3)
    def test_purchased_preserves_sent_stops_outstanding(self):
        self.accepted();self.row['order_id']='order';self.assertEqual(self.labels(),['Sent ✓','Purchased','Purchased'])
    def test_paused_preserves_receipts(self):
        self.accepted();self.row['automation_status']='PAUSED';self.assertEqual(self.labels(),['Sent ✓','Paused','Paused'])
    def test_pending_states_and_evaluated_ineligibility(self):
        self.row['enrollment_id']=None
        self.assertEqual(self.labels(),['Awaiting worker']*3)
        self.row['analytics']['shopify_abandoned']=False;self.assertEqual(self.labels(),['Qualifying']*3)
        self.row['evaluation']={'reason':'not_recoverable'};self.assertEqual(self.labels(),['Not in flow']*3)
        self.row['evaluation']={'reason':'recovery_opted_out'};self.assertEqual(self.labels(),['Suppressed']*3)
        self.row['evaluation']={'result':'Error: checkout unavailable'};self.assertEqual(self.labels(),['Failed']*3)
    def test_historical_and_missing_contact_not_eligible(self):
        self.row.update(enrollment_id=None,auto_start_at=self.at+timedelta(days=1));self.assertEqual(self.labels(),['Not in flow']*3)
        self.row.pop('auto_start_at');self.row['analytics'].pop('email');self.assertEqual(self.labels(),['Contact needed']*3)
    def test_deferred_queue_deadline_wins(self):
        due=self.at+timedelta(hours=2);self.row['sends']=[{'enrollment_id':'journey','step':0,'status':'PENDING','due_at':due}]
        self.assertEqual(progress(self.row,self.schema,self.at)[0]['due_at'],due.isoformat())
    def test_timezone_identity_no_mutation_and_unbounded_columns(self):
        self.row['analytics']['name']='Customer 123';self.row['created_at']=date('2026-10-08T15:05:00Z');before=deepcopy(self.row)
        item=listing([self.row],self.schema,'Australia/Sydney')[0]
        self.assertEqual(item['customer'],'name@example.test');self.assertEqual(item['created'],'9 Oct');self.assertIn('AEDT',item['created_full'])
        self.assertEqual(self.row,before);self.assertEqual(len(columns([{'step_id':str(i)} for i in range(60)])),60)


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class PersistedProgress(unittest.TestCase):
    setUp=queue.QueueRepair.setUp
    published=queue.QueueRepair.published
    candidates=queue.QueueRepair.candidates
    automatic=queue.QueueRepair.automatic
    def read(self,a,key):return checkouts(self.store,a['id'],window('All time'),key,page_size=51)[0]
    def test_automatic_entry_acceptance_next_step_and_purchase(self):
        from crm_automation_runtime import reconcile,advance
        a,key,c,_=self.automatic();reconcile(self.engine,a)
        row=self.read(a,key);schema=columns(row['published_steps']);self.assertTrue(row['enrollment_id'])
        self.assertEqual(progress(row,schema)[0]['label'],'Countdown')
        j=self.store.q('SELECT * FROM crm_automation_enrollments WHERE id=%s',(row['enrollment_id'],),True)
        advance(self.engine,j);advance(self.engine,j);self.engine.send_one();self.engine.send_one()
        self.provider.send.assert_called_once();advance(self.engine,j)
        row=self.read(a,key);self.assertEqual([c['label'] for c in progress(row,schema)],['Sent ✓','Countdown'])
        self.assertEqual(len(row['sends']),1);self.assertEqual(row['sends'][0]['step_id'],j['steps'][0]['step_id'])
        receipt=row['sends'][0]
        self.store.q("INSERT INTO crm_delivery_events(event_id,provider_id,event_type,occurred_at,send_id) VALUES(%s,%s,'email.delivered',now(),%s)",(str(receipt['id']),receipt['provider_id'],receipt['id']))
        self.assertIsNotNone(self.read(a,key)['sends'][0]['delivered_at'])
        c['completedAt']=now().isoformat();details(self.store,c)
        from crm_shopify_automation_events import recover
        recover(self.store,key);row=self.read(a,key)
        self.assertEqual([c['label'] for c in progress(row,schema)],['Sent ✓','Purchased'])
        self.engine.send_one();self.provider.send.assert_called_once()
    def test_single_paged_read_search_and_published_snapshot_no_documents(self):
        a,keys,_,_=self.candidates(6)
        with patch.object(self.store,'q',wraps=self.store.q) as reads:
            rows=checkouts(self.store,a['id'],window('All time'),page_size=3)
        self.assertEqual(reads.call_count,1);self.assertEqual(len(rows),3)
        self.assertTrue(rows[0]['published_steps']);self.assertNotIn('document',rows[0]['published_steps'][0])
        last=rows[-1];second=checkouts(self.store,a['id'],window('All time'),page_size=3,after=(last['created_at'],last['checkout_key']))
        self.assertFalse({r['checkout_key'] for r in rows}&{r['checkout_key'] for r in second})
        selected=checkouts(self.store,a['id'],window('All time'),page_size=51,search=keys[0])
        self.assertEqual([r['checkout_key'] for r in selected],[keys[0]])
    def test_new_published_column_and_disabled_step_leave_journey_unchanged(self):
        from crm_automation_runtime import reconcile
        from crm_automation_definition import email_step
        from tests.test_crm_simple_editor import document
        from tests.test_crm import ADMIN
        from tests.test_crm_send_flow import LIVE
        a,key,_,_=self.automatic();reconcile(self.engine,a);before=self.read(a,key)
        flow=deepcopy(a['config']['draft']);flow['emails'] += [email_step(document(),3600),email_step(document(),7200)]
        flow['emails'][1]['enabled']=False
        saved=self.store.save_flow(ADMIN,a['id'],a['name'],flow,a['config']['revision'])
        # Draft does not affect the two current published columns.
        self.assertEqual(len(self.read(a,key)['published_steps']),2)
        self.store.publish(ADMIN,a['id'],saved['config']['revision'],env=LIVE)
        after=self.read(a,key);schema=columns(after['published_steps'])
        self.assertEqual([s['label'] for s in schema],['Email 1','Email 2','Email 3','Email 4'])
        self.assertFalse(schema[1]['enabled']);self.assertEqual(progress(after,schema)[-1]['label'],'—')
        self.assertEqual((after['steps'],after['next_due_at']),(before['steps'],before['next_due_at']))
