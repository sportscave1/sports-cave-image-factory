"""Abandoned recovery acceptance tests. Loopback PostgreSQL + fake providers only."""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from unittest import TestCase,skipUnless
from unittest.mock import Mock,patch
import os
from crm_checkout_identity import display_name,identity,recovery_status
from crm_logic import now,date,recipient_hash
from crm_checkout_analytics import details,checkouts,window,reconcile
from tests.test_crm_automation_analytics import AnalyticsTests


class Presentation(TestCase):
    def test_customer_name(self):
        self.assertEqual(identity({'customer':{'firstName':'Joanne','lastName':'Lawrence'}})['name'],'Joanne Lawrence')

    def test_guest_shipping_name(self):
        self.assertEqual(identity({'shippingAddress':{'name':'Guest Collector'}})['name'],'Guest Collector')

    def test_email_fallback(self):
        self.assertEqual(display_name({'analytics':{'name':'Customer 123','email':'guest@example.test'}}),'guest@example.test')

    def test_guest_fallback(self):
        self.assertEqual(display_name({'customer_id':'123','analytics':{'name':'123'}}),'Guest')

    def test_not_sent_red(self):
        self.assertEqual(recovery_status({}),'Not sent')
        self.assertIn("'Not sent':'red'",Path('components/crm_checkout_table/index.html').read_text())

    def test_sent_not_recovered_orange(self):
        self.assertEqual(recovery_status({'sends':[{'status':'ACCEPTED','provider_id':'receipt'}]}),'Not recovered')

    def test_real_recovery_green(self):
        self.assertEqual(recovery_status({'order_id':'gid://shopify/Order/1'}),'Recovered')
        self.assertEqual(recovery_status({'analytics':{'completed_at':now().isoformat()}}),'Recovered')

    def test_enrolled_is_not_sent(self):
        self.assertEqual(recovery_status({'enrollment_id':'1','flow_status':'ACTIVE'}),'Not sent')

    def test_queued_failed_and_uncertain_are_not_sent(self):
        for status in ('PENDING','CLAIMED','SUBMITTING','FAILED','UNCERTAIN','ACCEPTED'):
            self.assertEqual(recovery_status({'sends':[{'status':status}]}),'Not sent')

    def test_cached_recovered_without_evidence_is_not_recovery(self):
        self.assertEqual(recovery_status({'status':'RECOVERED','flow_status':'RECOVERED'}),'Not sent')

    def test_ac_recovery_url_and_legacy_paths(self):
        from crm_shopify_automation_events import key_from_recovery_url,checkout_key
        for prefix in ('','ac/','cn/'):
            self.assertEqual(key_from_recovery_url('https://fixture.myshopify.com/123/checkouts/'+prefix+'token12345/recover','fixture.myshopify.com'),checkout_key('token12345','fixture.myshopify.com'))

    def test_operational_page_has_no_secondary_analytics(self):
        import inspect
        from crm_automation_analytics_ui import checkout_panel,_checkout_panel,content
        panel=inspect.getsource(checkout_panel)+inspect.getsource(_checkout_panel)
        self.assertNotIn('secondary(',panel)
        self.assertNotIn('countdown_html',panel)
        self.assertIn("disabled=not selected",panel)
        self.assertLess(panel.index("'Refresh checkout details'"),panel.index("'Add to flow'"))
        branch=inspect.getsource(content).split("if row['trigger_type']=='abandoned':",1)[1].split('return',1)[0]
        self.assertNotIn('secondary(',branch)


@skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable SQL required')
class Reliability(TestCase):
    setUp=AnalyticsTests.setUp
    prepared=AnalyticsTests.prepared
    published=AnalyticsTests.published
    event=AnalyticsTests.event
    add=AnalyticsTests.add

    def test_historical_enrollment_delay_elapsed_and_idempotent(self):
        a,c=self.prepared()
        old=date(a['activated_at'])-timedelta(days=7)
        c.update(createdAt=old.isoformat(),updatedAt=old.isoformat())
        self.store.q('UPDATE crm_shopify_checkouts SET created_at=%s,activity_at=%s WHERE checkout_key=%s',(old,old,self.key))
        j=self.add(a,c)
        self.assertEqual(date(j['next_due_at']),self.clock)
        with self.assertRaisesRegex(ValueError,'Already in flow'):self.add(a,c)
        self.provider.send.assert_not_called()

    def test_historical_first_email_delay_is_not_restarted(self):
        a,c=self.prepared();a['steps'][0]['delay_seconds']=3600
        self.store.q('UPDATE crm_automations SET steps=%s::jsonb WHERE id=%s',(__import__('json').dumps(a['steps']),a['id']))
        j=self.add(a,c) # Already inactive for two hours, beyond both configured waits.
        self.assertEqual(date(j['next_due_at']),self.clock)

    def test_signed_guest_contact_is_private_and_not_consent_authority(self):
        from crm_webhooks import receive_shopify
        a,c=self.prepared()
        receive_shopify(self.store,'checkouts/update','contact-'+__import__('uuid').uuid4().hex,
          {'token':self.token,'email':'guest@example.test','shipping_address':{'name':'Verified Guest','country_code':'AU'},
           'created_at':c['createdAt'],'updated_at':c['updatedAt']},self.clock,shop_domain='fixture.myshopify.com')
        ledger=self.store.q('SELECT analytics FROM crm_shopify_checkouts WHERE checkout_key=%s',(self.key,),True)
        self.assertEqual(ledger['analytics']['name'],'Verified Guest')
        self.assertEqual(ledger['analytics']['email'],'guest@example.test')
        events=self.store.q("SELECT normalized FROM crm_webhook_events WHERE normalized->>'checkout_key'=%s",(self.key,))
        self.assertNotIn('guest@example.test',str(events))
        self.assertFalse(self.store.q('SELECT id FROM crm_automation_enrollments WHERE automation_id=%s',(a['id'],)))

    def test_admin_timestamp_can_differ_from_webhook(self):
        a,c=self.prepared();c['createdAt']=(date(c['createdAt'])+timedelta(minutes=15)).isoformat()
        self.assertTrue(self.add(a,c))

    def test_recovered_cannot_enroll(self):
        a,c=self.prepared();c['completedAt']=self.clock.isoformat()
        with self.assertRaises(ValueError):self.add(a,c)
        self.provider.send.assert_not_called()

    def test_suppression_and_unsubscribe_are_explicit(self):
        a,c=self.prepared();self.customer['emailMarketingConsent']['marketingState']='UNSUBSCRIBED'
        with self.assertRaisesRegex(ValueError,'Unsubscribed'):self.add(a,c)
        self.customer['emailMarketingConsent']['marketingState']='SUBSCRIBED'
        self.store.suppress(recipient_hash(self.customer['email']),self.customer['id'],'manual','admin')
        with self.assertRaisesRegex(ValueError,'Suppressed'):self.add(a,c)
        self.provider.send.assert_not_called()

    def test_guest_without_customer_id_resolves_verified_email_profile(self):
        a,c=self.prepared();details(self.store,c);c['customer']=None
        self.store.q("UPDATE crm_shopify_checkouts SET customer_id='' WHERE checkout_key=%s",(self.key,))
        self.shop.campaign_email_profiles.return_value=[self.customer]
        self.assertTrue(self.add(a,c))
        self.provider.send.assert_not_called()

    def test_new_checkout_auto_entry_and_persistent_cursor(self):
        from crm_automation_runtime import reconcile as automatic
        a,c=self.prepared();self.store.set_state('checkout-auto-start-v2',{'started_at':(date(c['createdAt'])-timedelta(seconds=1)).isoformat()})
        self.shop.checkouts.return_value={'nodes':[c],'pageInfo':{'hasNextPage':True,'endCursor':'page-two'}}
        automatic(self.engine,a)
        journey=self.store.q('SELECT * FROM crm_automation_enrollments WHERE automation_id=%s',(a['id'],),True)
        self.assertIsNotNone(journey)
        key='reconcile:native:'+str(a['id'])+':'+str(a['config']['published_version'])+':'+str(a['activated_at'])
        self.assertEqual(self.store.state(key)['cursor'],'page-two')
        self.assertNotIn('cursor',self.store.state(self.key))

    def test_restart_preserves_enrollment_and_queue(self):
        from crm_store import Store
        a,c=self.prepared();j=self.add(a,c)
        send=self.store.enqueue('automation:'+str(j['id'])+':0',self.customer['id'],recipient_hash(self.customer['email']),
          {'id':a['steps'][0]['template_id'],'version':a['steps'][0]['template_version']},enrollment_id=j['id'],step_index=0)
        restarted=Store(self.store.connect)
        self.assertEqual(str(restarted.q('SELECT id FROM crm_automation_enrollments WHERE id=%s',(j['id'],),True)['id']),str(j['id']))
        self.assertEqual(restarted.receipt(send['id'])['status'],'PENDING')

    def test_missing_shopify_object_is_retryable_not_recovered(self):
        a,c=self.prepared();j=self.add(a,c);self.shop.checkout.return_value=None
        with self.assertRaisesRegex(ValueError,'verification unavailable'):self.engine.validate(self.customer['id'],j)
        self.assertNotEqual(self.store.q('SELECT status FROM crm_shopify_checkouts WHERE checkout_key=%s',(self.key,),True)['status'],'RECOVERED')

    def test_repair_is_idempotent_never_sends_preserves_order(self):
        a,c=self.prepared();self.store.q("UPDATE crm_shopify_checkouts SET status='RECOVERED',analytics='{\"name\":\"Customer 123\"}' WHERE checkout_key=%s",(self.key,))
        self.assertEqual(details(self.store,c),'Updated')
        self.assertEqual(details(self.store,c),'Unchanged')
        row=checkouts(self.store,a['id'],window('All time',self.clock),self.key)[0]
        self.assertEqual(recovery_status(row),'Not sent')
        self.store.q("UPDATE crm_shopify_checkouts SET order_id='gid://shopify/Order/1' WHERE checkout_key=%s",(self.key,))
        details(self.store,c)
        self.assertEqual(recovery_status(checkouts(self.store,a['id'],window('All time',self.clock),self.key)[0]),'Recovered')
        self.assertFalse(self.store.q('SELECT id FROM crm_automation_enrollments WHERE automation_id=%s',(a['id'],)))
        self.provider.send.assert_not_called()

    def test_order_only_records_do_not_pollute_abandoned_table(self):
        a,c=self.prepared()
        self.assertFalse(checkouts(self.store,a['id'],window('All time',self.clock),self.key))
        details(self.store,c)
        self.assertEqual(len(checkouts(self.store,a['id'],window('All time',self.clock),self.key)),1)

    def test_rollout_does_not_automatically_enroll_existing_backlog(self):
        from crm_automation_runtime import reconcile as automatic
        a,c=self.prepared();self.store.q("DELETE FROM crm_runtime_state WHERE key='checkout-auto-start-v2'")
        self.shop.checkouts.return_value={'nodes':[c],'pageInfo':{'hasNextPage':False}}
        automatic(self.engine,a)
        self.assertFalse(self.store.q('SELECT id FROM crm_automation_enrollments WHERE automation_id=%s',(a['id'],)))

    def queued(self):
        a,c=self.prepared();c['lineItems']={'nodes':[{'title':'Fixture item','quantity':1}]}
        j=self.add(a,c)
        send=self.store.enqueue('automation:'+str(j['id'])+':0',self.customer['id'],recipient_hash(self.customer['email']),
          {'id':a['steps'][0]['template_id'],'version':a['steps'][0]['template_version']},enrollment_id=j['id'],step_index=0)
        return a,c,j,send

    def test_provider_rejection_persisted_and_explicitly_retryable(self):
        from email_service import EmailDeliveryError
        from crm_checkout_identity import retry_send
        from tests.test_crm import ADMIN
        a,c,j,send=self.queued()
        self.provider.send.side_effect=EmailDeliveryError('Fixture rejection',status_code=422)
        self.engine.send_one();receipt=self.store.receipt(send['id'])
        self.assertEqual((receipt['status'],receipt['error_code']),('FAILED','provider_rejected'))
        self.assertIsNone(receipt['provider_email_id'])
        self.assertEqual(recovery_status(checkouts(self.store,a['id'],window('All time',self.clock),self.key)[0]),'Not sent')
        self.assertTrue(retry_send(self.store,ADMIN,send['id']))
        self.provider.send.side_effect=None;self.provider.send.return_value=str(__import__('uuid').uuid4())
        self.engine.send_one()
        self.assertEqual(self.store.receipt(send['id'])['status'],'ACCEPTED')
        self.assertEqual(recovery_status(checkouts(self.store,a['id'],window('All time',self.clock),self.key)[0]),'Not recovered')

    def test_rate_limit_retries_in_existing_queue(self):
        from email_service import EmailDeliveryError
        a,c,j,send=self.queued()
        self.provider.send.side_effect=EmailDeliveryError('Fixture throttled',status_code=429,retryable=True)
        self.engine.send_one();receipt=self.store.receipt(send['id'])
        self.assertEqual((receipt['status'],receipt['error_code']),('PENDING','provider_rate_limited'))
        self.assertGreater(date(receipt['due_at']),now())
        self.assertIsNone(receipt['provider_email_id'])

    def test_unknown_provider_outcome_never_automatically_replayed(self):
        from crm_checkout_identity import retry_send
        from tests.test_crm import ADMIN
        a,c,j,send=self.queued();self.provider.send.side_effect=TimeoutError('Synthetic timeout')
        self.engine.send_one();self.assertEqual(self.store.receipt(send['id'])['status'],'UNCERTAIN')
        self.assertFalse(retry_send(self.store,ADMIN,send['id']))
        self.engine.send_one();self.provider.send.assert_called_once()

    def test_recovery_before_send_blocks_provider(self):
        a,c,j,send=self.queued();c['completedAt']=now().isoformat()
        self.engine.send_one();self.provider.send.assert_not_called()
        self.assertEqual(self.store.receipt(send['id'])['status'],'BLOCKED')

    def test_new_checkout_complete_background_pipeline(self):
        from crm_automation_runtime import reconcile as automatic,advance
        a,c=self.prepared();c['lineItems']={'nodes':[{'title':'Fixture item','quantity':1}]}
        self.store.set_state('checkout-auto-start-v2',{'started_at':(date(c['createdAt'])-timedelta(seconds=1)).isoformat()})
        self.shop.checkouts.return_value={'nodes':[c],'pageInfo':{'hasNextPage':False}}
        automatic(self.engine,a)
        j=self.store.q('SELECT * FROM crm_automation_enrollments WHERE automation_id=%s',(a['id'],),True)
        advance(self.engine,j)
        self.assertEqual(recovery_status(checkouts(self.store,a['id'],window('All time',self.clock),self.key)[0]),'Not sent')
        self.engine.send_one();self.provider.send.assert_called_once()
        self.assertEqual(recovery_status(checkouts(self.store,a['id'],window('All time',self.clock),self.key)[0]),'Not recovered')
        c['completedAt']=now().isoformat();details(self.store,c)
        self.assertEqual(recovery_status(checkouts(self.store,a['id'],window('All time',self.clock),self.key)[0]),'Recovered')

    def test_repair_preserves_successful_send_history(self):
        a,c,j,send=self.queued();self.engine.send_one()
        before=self.store.receipt(send['id'])
        details(self.store,c);details(self.store,c)
        self.assertEqual(self.store.receipt(send['id']),before)
        self.provider.send.assert_called_once()


del AnalyticsTests
