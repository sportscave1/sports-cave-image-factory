"""Real local PostgreSQL, fake Shopify/provider, no production writes or sends."""
from datetime import timedelta
import json
import os
import unittest
from unittest.mock import patch
from crm_logic import now, date
from crm_checkout_enrollment_requests import request, claim, read_requests, request_key, reconciled_result
from crm_checkout_analytics import details, sync_cache
from crm_automation_runtime import reconcile, advance
from tests.test_crm import ADMIN
from tests.test_crm_checkout_enrollment_requests import RequestTests as Fixture


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class QueueRepair(unittest.TestCase):
    setUp=Fixture.setUp
    published=Fixture.published
    candidates=Fixture.candidates
    finish=Fixture.finish

    def test_expired_intent_is_not_released_as_historical_blast(self):
        a,keys,_,_=self.candidates(9)
        request(self.store,ADMIN,a['id'],keys)
        for key in keys:
            self.store.q("UPDATE crm_runtime_state SET value=value||%s::jsonb WHERE key=%s",
                (json.dumps({'requested_at':(now()-timedelta(days=1)).isoformat()}),request_key(a['id'],key)))
        self.assertEqual(claim(self.store,20,'worker'),[])
        rows=read_requests(self.store,a['id'],keys)
        self.assertTrue(all(r['request']['state']=='FAILED' and not r['enrollment_id'] for r in rows))
        self.provider.send.assert_not_called()
        request(self.store,ADMIN,a['id'],[keys[0]])
        self.assertEqual(len(claim(self.store,20,'explicit-retry')),1)

    def test_membership_reconciles_lost_ack_even_after_expiry(self):
        a,keys,_,_=self.candidates();request(self.store,ADMIN,a['id'],keys)
        row=self.finish(a,keys)[0]
        old={'state':'QUEUED','requested_at':(now()-timedelta(days=1)).isoformat()}
        self.assertEqual(reconciled_result(row,old)['state'],'DONE')
        self.assertEqual(reconciled_result({},old)['state'],'FAILED')

    def test_prefix_claim_ignores_neighbor_keys_and_caps_crash_retries(self):
        a,keys,_,_=self.candidates();request(self.store,ADMIN,a['id'],keys)
        self.store.set_state('checkout-enroll;not-a-request',{'state':'QUEUED','requested_at':now().isoformat()})
        for attempt in range(3):
            item=claim(self.store,10,'worker')[0]
            self.assertEqual(item['value']['attempts'],attempt+1)
            self.store.q("UPDATE crm_runtime_state SET value=value||'{\"lease_until\":\"2000-01-01T00:00:00Z\"}' WHERE key=%s",(item['key'],))
        self.assertEqual(claim(self.store,10,'worker'),[])
        self.assertEqual(self.store.state(item['key'])['state'],'FAILED')
        self.assertEqual(self.store.state('checkout-enroll;not-a-request')['state'],'QUEUED')

    def automatic(self):
        a,keys,checkouts,profiles=self.candidates()
        for checkout in checkouts.values():
            checkout['lineItems']={'nodes':[{'title':'Fixture artwork','quantity':1}]}
        start=now()-timedelta(hours=2)
        self.store.q('UPDATE crm_automations SET activated_at=%s WHERE id=%s',(start,a['id']))
        a=self.store.get('automations',a['id'])
        # Other tests leave disposable historical rows; don't let their fake
        # Shopify IDs consume this test's bounded twenty-candidate worker page.
        self.store.q("UPDATE crm_shopify_checkouts SET analytics=analytics||'{\"shopify_abandoned\":false}' WHERE checkout_key<>%s",(keys[0],))
        self.store.set_state('checkout-auto-start-v2',{'started_at':start.isoformat()})
        self.engine.clock=now
        return a,keys[0],next(iter(checkouts.values())),next(iter(profiles.values()))

    def test_closed_browser_background_entry_due_send_once_and_recovery(self):
        a,key,c,profile=self.automatic()
        reconcile(self.engine,a)
        j=self.store.q('SELECT * FROM crm_automation_enrollments WHERE automation_id=%s',(a['id'],),True)
        self.assertIsNotNone(j)
        self.assertLess(abs((date(j['next_due_at'])-date(c['updatedAt'])-timedelta(seconds=j['steps'][0]['delay_seconds'])).total_seconds()),.001)
        advance(self.engine,j);advance(self.engine,j)
        self.engine.send_one();self.engine.send_one()
        self.provider.send.assert_called_once()
        receipt=self.store.q('SELECT * FROM crm_marketing_sends WHERE enrollment_id=%s',(j['id'],),True)
        self.assertEqual(receipt['status'],'ACCEPTED')
        advance(self.engine,j)
        current=self.store.q('SELECT * FROM crm_automation_enrollments WHERE id=%s',(j['id'],),True)
        self.assertEqual(current['current_step'],1)
        c['completedAt']=now().isoformat();details(self.store,c)
        from crm_shopify_automation_events import recover
        recover(self.store,key)
        self.assertEqual(self.store.q('SELECT status FROM crm_automation_enrollments WHERE id=%s',(j['id'],),True)['status'],'RECOVERED')
        self.assertEqual(self.store.receipt(receipt['id'])['status'],'ACCEPTED')

    def test_missing_email_later_rechecked_without_manual_add(self):
        a,key,c,profile=self.automatic();address=profile['email']
        profile['email']='';c['customer']['email']=''
        details(self.store,c);reconcile(self.engine,a)
        self.assertFalse(self.store.q('SELECT id FROM crm_automation_enrollments WHERE automation_id=%s',(a['id'],)))
        profile['email']=address;c['customer']['email']=address;details(self.store,c)
        self.store.set_state('reconcile:native:'+str(a['id']),{})
        self.store.set_state('checkout-evaluation:'+key+':'+str(a['id']),{})
        # Invoke the next scheduled cycle without waiting five real minutes.
        with patch.object(self.engine,'clock',return_value=now()+timedelta(minutes=6)):
            reconcile(self.engine,a)
        self.assertTrue(self.store.q('SELECT id FROM crm_automation_enrollments WHERE automation_id=%s',(a['id'],)))

    def test_invalid_row_does_not_starve_later_sync_rows(self):
        a,keys,checkouts,_=self.candidates()
        self.store.set_state('checkout-cache-v2',{})
        self.shop.query.return_value={'abandonedCheckouts':{'nodes':[{},*checkouts.values()], 'pageInfo':{'hasNextPage':False}}}
        sync_cache(self.shop,self.store)
        result=self.store.state('checkout-cache-v2')
        self.assertEqual(result['counts']['Failed'],1)
        self.assertEqual(result['counts']['Unchanged'],1)

    def test_rate_limit_is_bounded_and_unknown_outcome_is_not_replayed(self):
        from email_service import EmailDeliveryError
        a,key,c,profile=self.automatic();reconcile(self.engine,a)
        j=self.store.q('SELECT * FROM crm_automation_enrollments WHERE automation_id=%s',(a['id'],),True)
        advance(self.engine,j)
        self.provider.send.side_effect=EmailDeliveryError('Fake throttling',status_code=429,retryable=True)
        for attempt in range(5):
            self.engine.send_one()
            receipt=self.store.q('SELECT * FROM crm_marketing_sends WHERE enrollment_id=%s',(j['id'],),True)
            self.assertEqual(receipt['status'],'PENDING' if attempt<4 else 'FAILED')
            self.assertIsNone(receipt['provider_email_id'])
            self.store.q("UPDATE crm_marketing_sends SET due_at=now()-interval '1 second' WHERE id=%s",(receipt['id'],))
        self.engine.send_one();self.assertEqual(self.provider.send.call_count,5)
        from crm_checkout_identity import retry_send
        self.assertTrue(retry_send(self.store,ADMIN,receipt['id']))
        self.provider.send.side_effect=TimeoutError('Fake uncertain submission')
        self.engine.send_one();self.engine.send_one()
        self.assertEqual(self.store.receipt(receipt['id'])['status'],'UNCERTAIN')
        self.assertEqual(self.provider.send.call_count,6)
        self.assertFalse(retry_send(self.store,ADMIN,receipt['id']))

del Fixture
