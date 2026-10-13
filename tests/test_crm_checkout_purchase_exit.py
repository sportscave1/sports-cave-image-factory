"""Actual disposable SQL; signed synthetic events, no Shopify/provider traffic."""
import os,unittest,uuid
from datetime import timedelta
from unittest.mock import patch
from crm_logic import now
from crm_checkout_purchase_exit import stop_if_purchased,REASON,LABEL
from crm_checkout_progress import progress,columns,listing
from crm_checkout_analytics import checkouts,window,report
from crm_webhooks import receive_shopify
from tests import test_crm_checkout_reliability as fixture
from tests import test_crm_automation_analytics as analytics


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class PurchaseExitTests(unittest.TestCase):
    setUp=analytics.AnalyticsTests.setUp
    published=analytics.AnalyticsTests.published
    prepared=analytics.AnalyticsTests.prepared
    event=analytics.AnalyticsTests.event
    add=analytics.AnalyticsTests.add
    queued=fixture.Reliability.queued

    def setup_journey(self):
        from crm_shopify_automation_events import checkout_key
        self.token='purchase-fixture-'+uuid.uuid4().hex
        self.key=checkout_key(self.token,'fixture.myshopify.com')
        self.customer['id']='gid://shopify/Customer/'+str(uuid.uuid4().int%10**12)
        a,c,j,s=self.queued()
        self.checkout_created=now()-timedelta(hours=2);self.paid=now()-timedelta(minutes=1)
        self.store.q('UPDATE crm_shopify_checkouts SET created_at=%s WHERE checkout_key=%s',(self.checkout_created,self.key))
        return a,c,j,s

    def paid_event(self,*,token='another-checkout-token',customer=None,at=None,cancelled=False,event_id=None):
        self.order='gid://shopify/Order/'+str(uuid.uuid4().int%10**12)
        payload={'id':self.order,'customer':{'id':customer or self.customer['id']},'checkout_token':token,
            'created_at':(at or self.paid).isoformat(),'financial_status':'paid',
            'cancelled_at':self.paid.isoformat() if cancelled else None}
        event_id=event_id or uuid.uuid4().hex
        receive_shopify(self.store,'orders/paid',event_id,payload,at or self.paid,shop_domain='fixture.myshopify.com')
        return event_id,payload

    def test_other_token_purchase_stops_before_checkout_lookup_and_never_attributes(self):
        a,c,j,s=self.setup_journey();self.paid_event()
        self.shop.reset_mock()
        self.shop.customer.side_effect=ValueError('Unavailable customer')
        self.shop.checkout.side_effect=ValueError('Unavailable checkout')
        self.assertEqual(self.engine.validate(self.customer['id'],j)[2],REASON)
        self.shop.customer.assert_not_called();self.shop.checkout.assert_not_called()
        self.assertTrue(stop_if_purchased(self.store,j))
        current=self.store.q('SELECT * FROM crm_automation_enrollments WHERE id=%s',(j['id'],),True)
        self.assertEqual(current['status'],'STOPPED');self.assertIsNone(current['retry_after'])
        self.assertEqual(self.store.receipt(s['id'])['status'],'BLOCKED')
        row=checkouts(self.store,a['id'],window('All time',self.clock),self.key)[0]
        self.assertIsNone(row['order_id']);self.assertNotEqual(row['status'],'RECOVERED')
        self.assertTrue(row['newer_paid_order_verified'])
        self.assertEqual(progress(row,columns(a['steps']))[0]['label'],LABEL)
        self.assertEqual(report(self.store,a['id'],window('All time',self.clock))['conversions'],0)
        self.provider.send.assert_not_called()

    def test_paid_event_retries_idempotent_late_receipt_uses_payment_time(self):
        a,c,j,s=self.setup_journey();event_id,payload=self.paid_event()
        self.assertFalse(receive_shopify(self.store,'orders/paid',event_id,payload,self.paid,shop_domain='fixture.myshopify.com'))
        for _ in range(3):self.assertTrue(stop_if_purchased(self.store,j))
        self.assertEqual(self.store.q('SELECT count(*) AS n FROM crm_marketing_sends WHERE enrollment_id=%s',(j['id'],),True)['n'],1)

    def test_paid_event_without_checkout_token_exits_before_unavailable_order_lookup(self):
        a,c,j,s=self.setup_journey();event_id,_=self.paid_event(token=None)
        event=self.store.q("SELECT * FROM crm_webhook_events WHERE provider='shopify' AND event_id=%s",(event_id,),True)
        self.shop.order.side_effect=ValueError('Unavailable order details')
        with self.assertRaises(ValueError):self.engine._process_event(event)
        self.assertEqual(self.store.q('SELECT status FROM crm_automation_enrollments WHERE id=%s',(j['id'],),True)['status'],'STOPPED')
        self.assertEqual(self.store.receipt(s['id'])['status'],'BLOCKED')
        self.provider.send.assert_not_called()

    def test_earlier_purchase_other_customer_and_cancelled_order_do_not_exit(self):
        for kind in ('before','other','cancelled','later_checkout'):
            with self.subTest(kind=kind):
                a,c,j,s=self.setup_journey()
                self.paid_event(at=self.checkout_created-timedelta(seconds=1) if kind=='before' else None,
                    customer='gid://shopify/Customer/999999' if kind=='other' else None,cancelled=kind=='cancelled')
                if kind=='later_checkout':self.store.q('UPDATE crm_shopify_checkouts SET created_at=%s WHERE checkout_key=%s',(self.paid+timedelta(seconds=1),self.key))
                self.assertFalse(stop_if_purchased(self.store,j))

    def test_cancelled_event_blocks_new_exit_but_never_reopens_stopped_journey(self):
        a,c,j,s=self.setup_journey();_,payload=self.paid_event()
        receive_shopify(self.store,'orders/cancelled',uuid.uuid4().hex,payload,self.paid+timedelta(seconds=1),shop_domain='fixture.myshopify.com')
        self.assertFalse(stop_if_purchased(self.store,j))
        self.paid_event();self.assertTrue(stop_if_purchased(self.store,j))
        receive_shopify(self.store,'orders/cancelled',uuid.uuid4().hex,{'id':self.order,'customer':{'id':self.customer['id']}},self.paid+timedelta(seconds=2),shop_domain='fixture.myshopify.com')
        self.assertTrue(stop_if_purchased(self.store,j))

    def test_submitted_uncertain_and_accepted_receipts_are_preserved(self):
        for status in ('SUBMITTING','UNCERTAIN','ACCEPTED'):
            with self.subTest(status=status):
                a,c,j,s=self.setup_journey()
                self.store.q('UPDATE crm_marketing_sends SET status=%s,first_submitted_at=%s,provider_email_id=%s WHERE id=%s',
                    (status,self.checkout_created+timedelta(minutes=5),str(uuid.uuid4()) if status=='ACCEPTED' else None,s['id']))
                before=self.store.receipt(s['id']);self.paid_event();self.assertTrue(stop_if_purchased(self.store,j))
                self.assertEqual(self.store.receipt(s['id']),before)
                row=checkouts(self.store,a['id'],window('All time',self.clock),self.key)[0]
                labels=[v['label'] for v in progress(row,columns(a['steps']))]
                self.assertNotIn('Recovered ✓',labels)

    def test_submission_boundary_blocks_claimed_send_without_transport(self):
        a,c,j,s=self.setup_journey();claimed=self.store.claim_send(allow_customer=True)
        self.paid_event()
        self.assertIsNone(self.store.begin_send(claimed,'fixture-hash',claimed['recipient_hash']))
        self.assertEqual(self.store.receipt(s['id'])['status'],'BLOCKED')

    def test_exact_token_remains_recovered(self):
        a,c,j,s=self.setup_journey();self.paid_event(token=self.token)
        self.assertFalse(stop_if_purchased(self.store,j))
        row=checkouts(self.store,a['id'],window('All time',self.clock),self.key)[0]
        from crm_checkout_identity import recovered
        self.assertTrue(recovered(row));self.assertEqual(row['order_id'],self.order)

    def test_multiple_checkouts_same_customer_keep_exact_recovery_and_later_cart(self):
        from crm_shopify_automation_events import checkout_key
        from crm_checkout_purchase_exit import stop_customer,proof
        a,c,j,s=self.setup_journey()
        first='first-cart-'+uuid.uuid4().hex;later='later-cart-'+uuid.uuid4().hex
        for token,stamp in ((first,self.checkout_created-timedelta(minutes=15)),(later,self.paid+timedelta(seconds=1))):
            receive_shopify(self.store,'checkouts/create',uuid.uuid4().hex,{'token':token,'customer':{'id':self.customer['id']},
                'created_at':stamp.isoformat(),'updated_at':stamp.isoformat()},stamp,shop_domain='fixture.myshopify.com')
        self.paid_event(token=first)
        stop_customer(self.store,self.customer['id'])
        self.assertEqual(self.store.q('SELECT status FROM crm_automation_enrollments WHERE id=%s',(j['id'],),True)['status'],'STOPPED')
        recovered=self.store.q('SELECT * FROM crm_shopify_checkouts WHERE checkout_key=%s',(checkout_key(first,'fixture.myshopify.com'),),True)
        self.assertEqual(recovered['status'],'RECOVERED');self.assertEqual(recovered['order_id'],self.order)
        new_cart=self.store.q('SELECT * FROM crm_shopify_checkouts WHERE checkout_key=%s',(checkout_key(later,'fixture.myshopify.com'),),True)
        with self.store.db() as conn:self.assertIsNone(proof(conn,new_cart))
        self.assertEqual(new_cart['status'],'OPEN')

    def test_date_and_time_visible_in_sydney(self):
        from crm_logic import date
        row={'checkout_key':'synthetic','created_at':date('2026-10-12T22:25:03Z')}
        value=listing([row],[]) [0]
        self.assertEqual(value['created'],'13 Oct · 9:25 am');self.assertIn('AEDT',value['created_full'])
