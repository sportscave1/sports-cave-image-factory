"""Order-first audience and audited worker enrolment on disposable PostgreSQL."""
import json,os,unittest,uuid
from copy import deepcopy
from datetime import timedelta
from time import perf_counter
from unittest.mock import Mock,patch
from crm_logic import now,date
from crm_lifecycle_audience import listing,enrich_orders,cache_customer
from crm_post_purchase_audience import selection,email_cells
from crm_lifecycle_enrollment_requests import request,tick
from tests import test_crm_lifecycle_expansion as lifecycle
from tests import test_crm_lifecycle_publication as publication
from tests.test_crm import ADMIN


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class OrderAudienceTests(unittest.TestCase):
    setUp=lifecycle.RuntimeTests.setUp
    publish=lifecycle.RuntimeTests.publish
    setUpClass=classmethod(lambda cls:publication.LifecyclePublicationTests.setUpClass())

    def orders(self,count=9):
        row=self.store.create(ADMIN,'post_purchase',lifecycle=True);self.created.append(str(row['id']))
        self.prefix=uuid.uuid4().hex;ids=[]
        for i in range(count):
            customer='gid://shopify/Customer/'+str(uuid.uuid4().int%10**12)
            identity='gid://shopify/Order/'+str(uuid.uuid4().int%10**12);ids.append(identity)
            self.store.q('''INSERT INTO shopify_orders(shopify_order_id,shopify_customer_id,customer_name,customer_email,order_name,financial_status,fulfillment_status,created_at,currency)
              VALUES(%s,%s,%s,%s,%s,'PAID','UNFULFILLED',%s,%s)''',
              (identity,customer,'Fixture purchaser '+str(i),self.prefix+'-'+str(i)+'@example.test',self.prefix+'-'+str(i),now()-timedelta(minutes=i),'AUD' if i%2 else 'USD'))
        return row,ids

    def test_nine_orders_visible_without_profiles_and_all_markets(self):
        row,ids=self.orders();started=perf_counter();rows=listing(self.store,row,search=self.prefix)
        print('Local order-first SQL, nine missing profiles: %.1f ms'%((perf_counter()-started)*1000))
        self.assertEqual({r['key'] for r in rows},set(ids))
        self.assertTrue(all(r['consent']=='UNVERIFIED' and r['email'] and r['name'] for r in rows))
        self.assertEqual(len(listing(self.store,row,search=self.prefix,filter_by='Pending verification')),9)
        self.assertEqual(len(listing(self.store,row,search=self.prefix,filter_by='Paid')),9)
        self.assertEqual(self.store.q('SELECT count(*) AS n FROM crm_automation_enrollments WHERE automation_id=%s',(row['id'],),True)['n'],0)

    def test_refunds_cancelled_and_repeat_orders_remain_visible(self):
        row,ids=self.orders(4)
        self.store.q("UPDATE shopify_orders SET financial_status='REFUNDED' WHERE shopify_order_id=%s",(ids[0],))
        self.store.q("UPDATE shopify_orders SET financial_status='PARTIALLY_REFUNDED' WHERE shopify_order_id=%s",(ids[1],))
        self.store.q('UPDATE shopify_orders SET cancelled_at=now() WHERE shopify_order_id=%s',(ids[2],))
        customer=self.store.q('SELECT shopify_customer_id FROM shopify_orders WHERE shopify_order_id=%s',(ids[3],),True)['shopify_customer_id']
        self.store.q('UPDATE shopify_orders SET shopify_customer_id=%s WHERE shopify_order_id=ANY(%s)',(customer,ids))
        rows=listing(self.store,row,search=self.prefix);self.assertEqual(len(rows),4)
        for status in ('Refunded','Partially refunded','Cancelled'):self.assertEqual(len(listing(self.store,row,search=self.prefix,filter_by=status)),1)
        self.assertEqual(len({r['key'] for r in rows}),4)

    def test_redacted_email_without_cached_profile_cannot_reappear_from_order_fallback(self):
        from crm_logic import recipient_hash
        row,ids=self.orders(1)
        self.store.suppress(recipient_hash(self.prefix+'-0@example.test'),None,'redacted','shopify')
        record=listing(self.store,row,search=self.prefix)[0]
        self.assertEqual(record['name'],'Redacted customer');self.assertEqual(record['email'],'')
        self.assertEqual(record['consent'],'REDACTED');self.assertTrue(record['suppressed'])
        profile=deepcopy(self.customer);profile.update(id=record['customer_id'],email=self.prefix+'-0@example.test',updatedAt=now().isoformat())
        self.assertFalse(cache_customer(self.store,profile,now()))
        self.assertIsNone(self.store.q('SELECT customer_id FROM crm_lifecycle_customers WHERE customer_id=%s',(record['customer_id'],),True))

    def test_new_orders_priority_enrichment_deduplicates_and_never_grants_from_email(self):
        row,ids=self.orders(2)
        seen=[]
        def customer(identity,**kwargs):
            seen.append(identity);c=deepcopy(self.customer);c.update(id=identity,updatedAt=now().isoformat(),createdAt=now().isoformat())
            c['emailMarketingConsent']['marketingState']='UNSUBSCRIBED'
            return c
        self.shop.customer.side_effect=customer
        enrich_orders(self.store,self.shop);enrich_orders(self.store,self.shop)
        own={r['customer_id'] for r in listing(self.store,row,search=self.prefix)}
        self.assertTrue(own.issubset(set(seen)));self.assertEqual(len(seen),len(set(seen)))
        rows=listing(self.store,row,search=self.prefix)
        self.assertTrue(all(r['consent']=='UNSUBSCRIBED' for r in rows))
        self.assertTrue(all(email_cells(r,row['config']['draft'])[0]['label']=='Not eligible' for r in rows))

    def test_selection_persists_across_pages_filters_and_rerenders(self):
        state={};slot='fixture'
        self.assertEqual(selection(state,slot,{'a','b'},{'sequence':1,'selected':['a','b','forged']}),['a','b'])
        self.assertEqual(selection(state,slot,{'c'},{'sequence':2,'selected':['c']}),['a','b','c'])
        self.assertEqual(selection(state,slot,{'a','b'},{'sequence':3,'selected':['b']}),['b','c'])
        self.assertEqual(selection(state,slot,{'c'},{'sequence':3,'selected':[]}),['b','c'])

    def test_draft_bulk_action_is_rejected_without_enrollment(self):
        row,ids=self.orders(1)
        with self.assertRaisesRegex(ValueError,'Publish and activate'):request(self.store,ADMIN,row['id'],ids,confirmed=True)
        self.assertEqual(self.store.q('SELECT count(*) AS n FROM crm_automation_enrollments WHERE automation_id=%s',(row['id'],),True)['n'],0)

    def payment_flow(self):
        row=self.publish('post_purchase');flow=deepcopy(row['config']['draft']);flow['emails'][0]['delay_seconds']=10800
        for step in flow['emails'][1:]:step['enabled']=False
        row=self.store.save_flow(ADMIN,row['id'],row['name'],flow,row['config']['revision'])
        row=self.store.publish(ADMIN,row['id'],row['config']['revision'])
        self.paid=now()-timedelta(minutes=10)
        self.order=lifecycle.order(identity='gid://shopify/Order/'+str(uuid.uuid4().int%10**12))
        self.order.update(createdAt=self.paid.isoformat(),paid_at=self.paid,customer={'id':self.customer['id']},name='#Synthetic')
        self.shop.orders.return_value={'nodes':[self.order],'pageInfo':{'hasNextPage':False}}
        self.store.q("INSERT INTO shopify_orders(shopify_order_id,shopify_customer_id,financial_status,created_at) VALUES(%s,%s,'PAID',%s)",(self.order['id'],self.customer['id'],self.paid))
        self.store.webhook('shopify',uuid.uuid4().hex,'orders/paid',self.order['id'],self.customer['id'],self.paid,normalized={'payload_version':'2026-04','shop':'fixture.myshopify.com'})
        return row

    def test_explicit_manual_order_request_real_worker_preserves_delay_and_disabled_stages(self):
        row=self.payment_flow()
        with self.assertRaises(ValueError):request(self.store,ADMIN,row['id'],[self.order['id']])
        request(self.store,ADMIN,row['id'],[self.order['id']],confirmed=True)
        request(self.store,ADMIN,row['id'],[self.order['id']],confirmed=True)
        self.assertTrue(tick(self.store,self.shop))
        e=self.store.q('SELECT * FROM crm_automation_enrollments WHERE automation_id=%s',(row['id'],),True)
        self.assertIsNotNone(e);self.assertEqual(len(e['steps']),1)
        self.assertLess(abs((date(e['next_due_at'])-(self.paid+timedelta(hours=3))).total_seconds()),.001)
        self.assertFalse(tick(self.store,self.shop));self.provider.send.assert_not_called()

    def test_fresh_unsubscribe_and_pause_block_manual_request_processing(self):
        row=self.payment_flow();request(self.store,ADMIN,row['id'],[self.order['id']],confirmed=True)
        self.customer['emailMarketingConsent']['marketingState']='UNSUBSCRIBED'
        tick(self.store,self.shop)
        self.assertEqual(self.store.q('SELECT count(*) AS n FROM crm_automation_enrollments WHERE automation_id=%s',(row['id'],),True)['n'],0)
        self.store.lifecycle(ADMIN,row['id'],'pause')
        with self.assertRaises(ValueError):request(self.store,ADMIN,row['id'],[self.order['id']],confirmed=True)
        self.provider.send.assert_not_called()

    def test_future_paid_event_worker_metadata_uses_lifecycle_and_no_historical_replay(self):
        from crm_automation_runtime import process_event
        row=self.payment_flow()
        metadata=next(a for a in self.store.active_automations() if a['id']==row['id'])
        self.assertNotIn('draft',metadata['config'])
        old_event={'topic':'orders/paid','object_id':self.order['id'],'occurred_at':self.paid,'normalized':{}}
        process_event(self.engine,old_event,[metadata])
        self.assertEqual(self.store.q('SELECT count(*) AS n FROM crm_automation_enrollments WHERE automation_id=%s',(row['id'],),True)['n'],0)
        self.clock=now()+timedelta(seconds=1)
        new=lifecycle.order(identity='gid://shopify/Order/'+str(uuid.uuid4().int%10**12))
        new.update(createdAt=self.clock.isoformat(),paid_at=None,customer={'id':self.customer['id']},name='#New')
        self.shop.order.return_value=new;self.shop.orders.return_value={'nodes':[new],'pageInfo':{'hasNextPage':False}}
        self.store.webhook('shopify',uuid.uuid4().hex,'orders/paid',new['id'],self.customer['id'],self.clock,normalized={})
        process_event(self.engine,{'topic':'orders/paid','object_id':new['id'],'occurred_at':self.clock,'event_id':'synthetic-new-paid','normalized':{}},[metadata])
        journeys=self.store.q('SELECT * FROM crm_automation_enrollments WHERE automation_id=%s',(row['id'],))
        self.assertEqual(len(journeys),1);self.assertEqual(journeys[0]['trigger_shopify_id'],new['id'])
        self.assertEqual(len(journeys[0]['steps']),1);self.assertEqual(journeys[0]['steps'][0]['delay_seconds'],10800)
        self.provider.send.assert_not_called()

    def test_accepted_receipt_required_for_sent_and_disabled_columns_preserved(self):
        record={'key':'order','consent':'SUBSCRIBED','suppressed':False,'financial_status':'PAID','enrollment_id':'journey',
            'flow_state':'ACTIVE','current_step':0,'steps':[{'step_id':'one'}],'next_due_at':now(),'sends':[]}
        flow={'emails':[{'step_id':'one','enabled':True},{'step_id':'two','enabled':False},{'step_id':'three','enabled':False}]}
        record['sends']=[{'enrollment_id':'journey','step':0,'status':'ACCEPTED'}]
        self.assertNotEqual(email_cells(record,flow)[0]['label'],'Sent ✓')
        record['sends'][0]['provider_id']='synthetic-receipt'
        self.assertEqual([c['label'] for c in email_cells(record,flow)],['Sent ✓','Disabled','Disabled'])
