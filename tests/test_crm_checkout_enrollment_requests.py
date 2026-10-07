"""Loopback SQL, fabricated checkout identities, no email transport execution."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
import os
from threading import Event
from time import monotonic, sleep
import unittest
from unittest.mock import Mock, patch
import uuid

from crm_checkout_enrollment_requests import request, read_requests, claim, process, Processor, SharedLookups, request_key
from crm_checkout_analytics import details
from crm_checkout_timing_ui import time_to_send
from crm_logic import now,recipient_hash
from crm_shopify import CapabilityUnavailable
from tests.test_crm import ADMIN, WORKER
from tests.test_crm_automation_analytics import AnalyticsTests
from tests.crm_db_fixture import connect
from crm_automation_store import AutomationStore


class LookupTests(unittest.TestCase):
    def test_overlapping_profiles_share_fresh_lookup_but_never_cache_consent(self):
        entered=Event();release=Event();shop=Mock()
        def fetch(*args,**kwargs):
            entered.set();release.wait(3);return {'id':'fixture','emailMarketingConsent':{'marketingState':'SUBSCRIBED'}}
        shop.customer.side_effect=fetch;shared=SharedLookups(shop)
        with ThreadPoolExecutor(max_workers=2) as pool:
            one=pool.submit(shared.customer,'fixture',fresh=True);self.assertTrue(entered.wait(1))
            two=pool.submit(shared.customer,'fixture',fresh=True);sleep(.03);release.set()
            self.assertEqual(one.result(),two.result())
        self.assertEqual(shop.customer.call_count,1)
        shared.customer('fixture',fresh=True)
        self.assertEqual(shop.customer.call_count,2)


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class RequestTests(unittest.TestCase):
    setUp=AnalyticsTests.setUp
    published=AnalyticsTests.published

    def candidates(self,n=1):
        a=self.published('abandoned',delays=(3600,86400));checkouts={};profiles={}
        for _ in range(n):
            identity=str(uuid.uuid4().int%10**14);customer=deepcopy(self.customer)
            customer.update(id='gid://shopify/Customer/'+identity,email=identity+'@example.test')
            c={'id':'gid://shopify/AbandonedCheckout/'+identity,'createdAt':(now()-timedelta(minutes=90)).isoformat(),
               'updatedAt':(now()-timedelta(minutes=90)).isoformat(),'completedAt':None,'customer':customer,
               'abandonedCheckoutUrl':'https://fixture.myshopify.com/checkouts/'+identity+'/recover'}
            c['lineItems']={'nodes':[{'title':'Fixture artwork','quantity':1}]}
            details(self.store,c);checkouts[c['id']]=c;profiles[customer['id']]=customer
        self.shop.checkout.side_effect=lambda key,**kw:deepcopy(checkouts[key])
        self.shop.customer.side_effect=lambda key,**kw:deepcopy(profiles[key])
        from crm_shopify_automation_events import key_from_recovery_url
        keys=[key_from_recovery_url(c['abandonedCheckoutUrl'],'fixture.myshopify.com') for c in checkouts.values()]
        return a,keys,checkouts,profiles

    def finish(self,a,keys):
        processor=Processor(self.store,self.shop)
        try:
            deadline=monotonic()+10
            while monotonic()<deadline:
                processor.pump()
                values=read_requests(self.store,a['id'],keys)
                if all(r['request']['state'] not in ('QUEUED','CHECKING') for r in values):return values
                sleep(.01)
            self.fail('Requests did not complete')
        finally:processor.pool.shutdown(wait=True)

    def test_single_persists_schedule_without_enqueuing_or_sending(self):
        a,keys,_,_=self.candidates()
        before=self.store.q('SELECT count(*) AS n FROM crm_marketing_sends',one=True)['n']
        self.assertEqual(request(self.store,ADMIN,a['id'],keys)[0]['state'],'QUEUED')
        self.shop.checkout.assert_not_called()
        rows=self.finish(a,keys)
        self.assertEqual(rows[0]['request']['result'],'Added to flow')
        self.assertEqual(time_to_send(rows[0]),'Due now')
        self.assertEqual(self.store.q('SELECT count(*) AS n FROM crm_marketing_sends',one=True)['n'],before)
        self.provider.send.assert_not_called()

    def test_duplicate_request_and_completed_enrollment_are_idempotent(self):
        a,keys,_,_=self.candidates()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:request(self.store,ADMIN,a['id'],keys),range(2)))
        self.assertEqual(results[0][0]['requested_at'],results[1][0]['requested_at'])
        self.finish(a,keys)
        self.assertEqual(request(self.store,ADMIN,a['id'],keys)[0]['result'],'Already in flow')
        self.assertEqual(self.store.q('SELECT count(*) AS n FROM crm_automation_enrollments WHERE automation_id=%s',(a['id'],),True)['n'],1)

    def test_twelve_mixed_rows_and_partial_failure(self):
        a,keys,checkouts,profiles=self.candidates(12)
        customers=list(profiles.values());customers[1]['emailMarketingConsent']['marketingState']='UNSUBSCRIBED'
        self.store.suppress(recipient_hash(customers[2]['email']),customers[2]['id'],'complaint','fixture')
        recovered=list(checkouts.values())[3];recovered['completedAt']=now().isoformat();details(self.store,recovered)
        bad=list(checkouts)[4];original=self.shop.checkout.side_effect
        def fetch(key,**kw):
            if key==bad:raise CapabilityUnavailable('fixture')
            return original(key,**kw)
        self.shop.checkout.side_effect=fetch
        response=request(self.store,ADMIN,a['id'],keys)
        self.assertIn('Suppressed',[r['result'] for r in response]);self.assertIn('Recovered',[r['result'] for r in response])
        rows=self.finish(a,keys);labels=[r['request']['result'] for r in rows]
        self.assertEqual(labels.count('Added to flow'),8)
        for label in ('Opted out','Suppressed','Recovered','Failed — Shopify unavailable'):self.assertIn(label,labels)
        self.assertEqual(self.shop.checkout.call_count,10) # local blocks did not fetch Shopify
        self.provider.send.assert_not_called()

    def test_slow_checkout_does_not_block_other_results_and_bounded_parallelism(self):
        a,keys,checkouts,_=self.candidates(12);slow=list(checkouts)[0];entered=Event();release=Event()
        original=self.shop.checkout.side_effect
        def fetch(key,**kw):
            if key==slow:entered.set();release.wait(5)
            else:sleep(.03)
            return original(key,**kw)
        self.shop.checkout.side_effect=fetch
        start=monotonic();request(self.store,ADMIN,a['id'],keys);ack=monotonic()-start
        processor=Processor(self.store,self.shop)
        try:
            deadline=monotonic()+4;partial=False
            while monotonic()<deadline:
                processor.pump();self.assertLessEqual(len(processor.futures),4)
                rows=read_requests(self.store,a['id'],keys)
                if entered.is_set() and any(r['request']['result']=='Added to flow' for r in rows):partial=True;break
                sleep(.01)
            self.assertTrue(partial);self.assertFalse(release.is_set())
            print(f'PERF 12 selected: durable acknowledgement={ack:.3f}s; independent completion while slow lookup blocked; max_inflight=4')
        finally:release.set();processor.pool.shutdown(wait=True)
        self.finish(a,keys)

    def test_restart_reclaims_lease_and_failure_retry_preserves_reason(self):
        a,keys,_,_=self.candidates();request(self.store,ADMIN,a['id'],keys)
        item=claim(self.store,1,'old-process')[0]
        self.assertEqual(item['value']['result'],'Checking eligibility…')
        self.store.q("UPDATE crm_runtime_state SET value=value || %s::jsonb WHERE key=%s",
                     ('{"lease_until":"2000-01-01T00:00:00Z"}',item['key']))
        restarted=AutomationStore(connect);new=claim(restarted,1,'new-process')[0]
        self.assertEqual(new['value']['owner'],'new-process')
        with patch('crm_automation_analytics._authorized_add_to_flow',side_effect=CapabilityUnavailable('fixture')):
            process(restarted,self.shop,new)
        state=restarted.state(item['key']);self.assertEqual(state['error_code'],'shopify_unavailable')
        request(restarted,ADMIN,a['id'],keys)
        self.assertEqual(restarted.state(item['key'])['history'][-1]['error_code'],'shopify_unavailable')
        self.finish(a,keys)
        process(restarted,self.shop,item) # stale owner must not overwrite completion
        self.assertEqual(restarted.state(item['key'])['result'],'Added to flow')

    def test_only_selected_and_permission_required(self):
        a,keys,_,_=self.candidates(3)
        with self.assertRaises(PermissionError):request(self.store,WORKER,a['id'],keys)
        request(self.store,ADMIN,a['id'],[keys[0]])
        self.assertFalse(self.store.state(request_key(a['id'],keys[1])))
        self.finish(a,[keys[0]])
        self.assertEqual(self.store.q('SELECT count(*) AS n FROM crm_automation_enrollments WHERE automation_id=%s',(a['id'],),True)['n'],1)

    def test_claims_are_disjoint_and_identity_changes_fail_closed(self):
        a,keys,checkouts,_=self.candidates(2)
        request(self.store,ADMIN,a['id'],keys)
        first=claim(self.store,1,'worker-one');second=claim(self.store,1,'worker-two')
        self.assertNotEqual(first[0]['key'],second[0]['key'])
        self.assertEqual(claim(self.store,2,'worker-three'),[])
        c=checkouts[first[0]['value']['checkout_id']]
        c['abandonedCheckoutUrl']='https://fixture.myshopify.com/checkouts/changedtoken123456/recover'
        process(self.store,self.shop,first[0]);process(self.store,self.shop,second[0])
        self.assertEqual(self.store.state(first[0]['key'])['result'],'Failed — identity changed')
        self.assertEqual(self.store.state(second[0]['key'])['result'],'Added to flow')
        self.assertEqual(self.store.q('SELECT count(*) AS n FROM crm_automation_enrollments WHERE automation_id=%s',(a['id'],),True)['n'],1)
        self.provider.send.assert_not_called()

    def test_lost_ack_after_enrollment_commit_restarts_without_duplicate(self):
        a,keys,_,_=self.candidates();request(self.store,ADMIN,a['id'],keys)
        item=claim(self.store,1,'crashed-owner')[0];original=self.store.q
        from crm_store import StoreUnavailable
        def crash(sql,args=(),one=False):
            if sql.startswith('UPDATE crm_runtime_state SET value=value ||'):
                raise StoreUnavailable('fixture failed acknowledgement')
            return original(sql,args,one)
        with patch.object(self.store,'q',side_effect=crash),self.assertRaises(StoreUnavailable):process(self.store,self.shop,item)
        original("UPDATE crm_runtime_state SET value=value || %s::jsonb WHERE key=%s",
                 ('{"lease_until":"2000-01-01T00:00:00Z"}',item['key']))
        restarted=AutomationStore(connect)
        self.assertEqual(claim(restarted,1,'restarted'),[])  # Reconcile actual membership without repeating work.
        self.assertEqual(restarted.state(item['key'])['result'],'Already in flow')
        self.assertEqual(restarted.q('SELECT count(*) AS n FROM crm_automation_enrollments WHERE automation_id=%s',(a['id'],),True)['n'],1)

    def test_batch_sql_statement_count_is_constant(self):
        a,keys,_,_=self.candidates(12)
        from tests.crm_db_fixture import Connection
        original=Connection.execute;calls=[]
        def counted(conn,sql,args=()):calls.append(sql);return original(conn,sql,args)
        with patch.object(Connection,'execute',counted):request(self.store,ADMIN,a['id'],keys)
        statements=[s for s in calls if s not in ('BEGIN','COMMIT')]
        self.assertEqual(len(statements),5)
        self.assertEqual(calls.count('COMMIT'),2)
        self.shop.checkout.assert_not_called();self.shop.customer.assert_not_called()
        self.finish(a,keys)

    def test_profile_old_serial_path_against_bounded_worker(self):
        from crm_automation_analytics import add_to_flow
        from crm_shopify import _LIMIT
        from tests.crm_db_fixture import Connection
        original_execute=Connection.execute;sql=[]
        def counted(conn,statement,args=()):sql.append(statement);return original_execute(conn,statement,args)
        def latency():
            checkout=self.shop.checkout.side_effect;customer=self.shop.customer.side_effect
            def delayed(fn,*args,**kwargs):
                with _LIMIT:sleep(.06);return fn(*args,**kwargs)
            self.shop.checkout.side_effect=lambda *a,**k:delayed(checkout,*a,**k)
            self.shop.customer.side_effect=lambda *a,**k:delayed(customer,*a,**k)
        a,keys,checkouts,_=self.candidates(12);latency();started=monotonic()
        with patch.object(Connection,'execute',counted):
            for identity in checkouts:add_to_flow(self.shop,self.store,ADMIN,a['id'],identity)
        serial=monotonic()-started;old_calls=len(sql);old_commits=sql.count('COMMIT')
        a,keys,_,_=self.candidates(12);latency();started=monotonic()
        request(self.store,ADMIN,a['id'],keys);ack=monotonic()-started
        self.finish(a,keys);parallel=monotonic()-started
        self.assertLess(parallel,serial*.85)
        print(f'PERF controlled 12-row old path: {serial:.3f}s, SQL calls={old_calls}, commits={old_commits}, fresh lookups=24; '
              f'new ack={ack:.3f}s, completed={parallel:.3f}s; same fresh checks, Shopify concurrency capped at 2')


if __name__=='__main__':unittest.main()
