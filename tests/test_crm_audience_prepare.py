"""Offline preparation domains, stale responses and synthetic scaling evidence."""
from copy import deepcopy
from pathlib import Path
import threading
import time
import unittest
import os
import uuid
from unittest.mock import Mock,patch

from crm_campaign_audience_prepare import prepare,prepare_session,fingerprint
from crm_campaign_review import start_review
from crm_campaign_send import review
from crm_campaign_markets import calculate
from crm_shopify import Shopify
from crm_workspace_store import WorkspaceRecords
from tests.crm_fixtures import ShopifyFixture,native_customer
from tests.test_crm_campaign_v2 import profile,authority
from tests.test_crm_fast_review import store
from tests.test_crm_simple_editor import document
from tests.test_crm_send_flow import CFG,LIVE


def doc():
    result=document();result.update(market='AU',market_audience=True)
    return result


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.shop=authority([profile(1),profile(2)])
        self.store=store();self.doc=doc()
    def ready(self):
        job=prepare(None,self.shop,self.store,self.doc,CFG,debounce=0)
        job.future.result(3);return job

    def test_content_changes_reuse_prepared_audience_and_do_not_save(self):
        job=self.ready()
        changed=deepcopy(self.doc)
        changed['content']['subject']='Other subject'
        changed['content']['preview_text']='Different preview'
        changed['notes']='Different notes';changed['send_timing']={'mode':'schedule','date':'2030-01-01','time':'07:00'}
        self.assertIs(prepare(job,self.shop,self.store,changed,CFG),job)
        self.shop.campaign_member_ids.assert_called_once()
        self.store.save.assert_not_called()
        state=job.result()
        self.assertNotIn('email',state['profiles'][profile(1)['id']])
        self.assertNotIn('defaultEmailAddress',state['profiles'][profile(1)['id']])
        state['recipients'].clear();self.assertEqual(len(job.result()['recipients']),2)

    def test_audience_market_hours_account_sender_changes_invalidate(self):
        original=fingerprint(self.shop,self.doc,CFG)
        for field,value in [('market','NZ'),('smart_hours',24),('audience',{'kind':'Shopify','id':'new'})]:
            changed=deepcopy(self.doc);changed[field]=value
            self.assertNotEqual(original,fingerprint(self.shop,changed,CFG))
        other=authority([]);other.namespace='other-account'
        self.assertNotEqual(original,fingerprint(other,self.doc,CFG))
        self.assertNotEqual(original,fingerprint(self.shop,self.doc,{**CFG,'sender':'other@example.test'}))

    def test_identical_inflight_reused_and_old_response_cannot_replace_current(self):
        gate=threading.Event();entered=threading.Event()
        def fetch(shop,store,document):
            if document['market']=='AU':entered.set();gate.wait(3)
            return {'members':1,'eligible':1,'excluded':{},'complete':True,'checked_at':'fixture','recipients':[],'profiles':{}}
        with patch('crm_campaign_audience_prepare.final_audience',side_effect=fetch) as fetcher:
            session={};editor={'document':self.doc}
            a=prepare_session(session,self.shop,self.store,editor,'fixture',CFG)
            self.assertTrue(entered.wait(2))
            self.assertIs(prepare_session(session,self.shop,self.store,editor,'fixture',CFG),a)
            changed=deepcopy(editor);changed['document']['market']='NZ'
            b=prepare_session(session,self.shop,self.store,changed,'fixture',CFG)
            b.future.result(3);gate.set();a.future.result(3)
            self.assertIs(session['fixtureaudience_job'],b)
            self.assertEqual(fetcher.call_count,2)

    def test_debounce_cancels_obsolete_not_yet_started_work(self):
        with patch('crm_campaign_audience_prepare.final_audience') as fetch:
            a=prepare(None,self.shop,self.store,self.doc,CFG,debounce=10)
            changed={**self.doc,'market':'NZ'}
            b=prepare(a,self.shop,self.store,changed,CFG,debounce=10)
            self.assertTrue(a.future.cancelled());fetch.assert_not_called()
            b.timer.cancel();b.future.cancel()

    def test_expired_snapshot_retains_count_but_cannot_be_used_for_send_review(self):
        a=self.ready();a.completed_at-=61
        with self.assertRaisesRegex(ValueError,'expired'):a.result()
        gate=threading.Event()
        original=self.shop.customer_batch.side_effect
        self.shop.customer_batch.side_effect=lambda ids,**kw: (gate.wait(3),original(ids,**kw))[1]
        b=prepare(a,self.shop,self.store,self.doc,CFG,debounce=0)
        try:self.assertEqual(b.display()['eligible'],2);self.assertFalse(b.valid())
        finally:gate.set();b.future.result(3)

    def test_suppression_unsubscribe_duplicate_and_conflict_fail_closed(self):
        rows=[profile(i) for i in range(1,7)]
        rows[1]['email']=rows[0]['email'];rows[2]=profile(3,consent='UNSUBSCRIBED')
        outside=profile(7,'NZ',consent='UNSUBSCRIBED');outside['email']=rows[3]['email']
        self.store.active_suppression_hashes.return_value=(set(),{rows[4]['id']})
        state=prepare(None,authority(rows+[outside]),self.store,self.doc,CFG,debounce=0).result()
        self.assertEqual(state['eligible'],2)
        self.assertEqual(state['excluded'],{'duplicate':1,'conflicting_consent':1,'local_suppression':1})

    def test_error_persists_without_poll_retry_storm_and_logs_no_pii(self):
        self.shop.customer_batch.side_effect=ValueError('private@example.test token=secret')
        with self.assertLogs('crm_campaign_audience_prepare',level='WARNING') as logs:
            a=prepare(None,self.shop,self.store,self.doc,CFG,debounce=0)
            with self.assertRaises(ValueError):a.result()
        self.assertIs(prepare(a,self.shop,self.store,self.doc,CFG),a)
        self.assertNotIn('private',str(logs.output));self.assertNotIn('secret',str(logs.output))

    def test_prepared_review_creates_current_content_snapshot_without_audience_rebuild(self):
        job=self.ready();self.store.render_settings.return_value=CFG
        editor={'id':'47bb53bc-9a37-4f99-a840-e775073dbce5','version':1,'name':'Fixture','document':self.doc}
        editor['document']['content']['subject']='Current edited subject'
        with patch('crm_campaign_send.final_audience',side_effect=AssertionError('Must reuse')), \
             patch('crm_campaign_snapshot.create',return_value='snapshot') as snapshot:
            result=review(self.shop,self.store,editor,LIVE,audience_job=job)
        self.assertEqual(result['counts']['eligible'],2)
        self.assertEqual(result['document']['content']['subject'],'Current edited subject')
        self.assertEqual(result['snapshot_id'],'snapshot');snapshot.assert_called_once()
        self.shop.customer_batch.assert_called_once()

    def test_subject_change_rebuilds_content_review_only(self):
        job=self.ready()
        editor={'id':'fixture','version':1,'name':'Fixture','document':self.doc}
        with patch('crm_campaign_review.review',return_value={'snapshot_id':'one'}) as reviewed:
            first=start_review(None,self.shop,self.store,{},editor,deepcopy(editor),CFG,job)
            first.future.result(3)
            changed=deepcopy(editor);changed['document']['content']['subject']='Different'
            with patch('crm_campaign_review.save_checkpoint',side_effect=lambda db,user,e:e):
                second=start_review(first,self.shop,self.store,{},changed,changed,CFG,job)
                second.future.result(3)
            self.assertIsNot(first,second)
            self.assertIs(reviewed.call_args.kwargs['audience_job'],job)
        self.shop.campaign_member_ids.assert_called_once()

    def test_fresher_preparation_cannot_be_overridden_by_completed_review(self):
        first=self.ready();editor={'id':'fixture','version':1,'name':'Fixture','document':self.doc}
        with patch('crm_campaign_review.review',return_value={'snapshot_id':'one'}):
            a=start_review(None,self.shop,self.store,{},editor,editor,CFG,first);a.future.result(3)
            first.completed_at-=61
            fresh=prepare(first,self.shop,self.store,self.doc,CFG,debounce=0);fresh.future.result(3)
            b=start_review(a,self.shop,self.store,{},editor,editor,CFG,fresh);b.future.result(3)
            self.assertIsNot(a,b);self.assertIs(b.audience_job,fresh)

    def test_selected_database_reads_are_bounded_and_policy_unchanged(self):
        db=WorkspaceRecords();db.q=Mock(side_effect=[
            [{'recipient_hash':'hash','shopify_customer_id':'id'}],[{'recipient_hash':'recent'}]])
        self.assertEqual(db.selected_suppression_state(['id'],['hash','recent'],16),({'hash'},{'id'},{'recent'}))
        self.assertEqual(db.q.call_count,2)
        self.assertIn('recipient_hash=ANY',db.q.call_args_list[0].args[0])
        self.assertIn("status='ACCEPTED'",db.q.call_args_list[1].args[0])
        self.assertIn('test_send=false',db.q.call_args_list[1].args[0])

    def test_exact_audience_preparation_is_deferred_until_review(self):
        source=Path('crm_campaign_page.py').read_text(encoding='utf-8')
        self.assertNotIn('prepare_session',source)
        self.assertNotIn('prepare_session',Path('crm_campaign_controls.py').read_text(encoding='utf-8'))
        self.assertIn('prepare_session',Path('crm_campaign_send_ui.py').read_text(encoding='utf-8'))

    def test_campaign_switch_retains_only_one_active_audience_cache(self):
        session={};editor={'document':self.doc}
        first=prepare_session(session,self.shop,self.store,editor,'first',CFG);first.future.result(3)
        second=prepare_session(session,self.shop,self.store,editor,'second',CFG)
        self.assertIs(first,second)
        self.assertNotIn('firstaudience_job',session)
        self.assertIs(session['secondaudience_job'],second)

    def test_real_prepared_modal_opens_without_rebuilding_audience(self):
        from streamlit.testing.v1 import AppTest
        self.store.render_settings.return_value=CFG
        editor={'id':'47bb53bc-9a37-4f99-a840-e775073dbce5','version':1,'name':'Fixture','document':self.doc,'archived_at':None}
        app=AppTest.from_string('''
import streamlit as st
from crm_campaign_audience_prepare import prepare_session
from crm_campaign_send_ui import review_dialog
from tests.test_crm_send_flow import CFG
prepare_session(st.session_state,st.session_state.shop,st.session_state.store,st.session_state.campaign_editor,'warm_',CFG)
if st.button('Review'):
 review_dialog(st.session_state.shop,st.session_state.store,{},st.session_state.campaign_editor,'warm_',CFG)
''')
        app.session_state['shop']=self.shop;app.session_state['store']=self.store
        app.session_state['campaign_editor']=editor;app.session_state['campaign_saved']=deepcopy(editor)
        with patch.dict(os.environ,LIVE),patch('crm_campaign_snapshot.create',return_value='snapshot'), \
             patch('crm_campaign_send_ui.queue_campaign',side_effect=AssertionError('No sends')):
            app.run();app.session_state['warm_audience_job'].future.result(3)
            calls=self.shop.customer_batch.call_count
            started=time.perf_counter();next(b for b in app.button if b.label=='Review').click().run()
            open_ms=(time.perf_counter()-started)*1000
            app.session_state['warm_review_job'].future.result(3)
            app.run();next(b for b in app.button if b.label=='Review').click().run()
            self.assertFalse(app.exception)
            self.assertFalse(next(b for b in app.button if b.label=='Send to 2 recipients').disabled)
            self.assertEqual(self.shop.customer_batch.call_count,calls)
            print(f'LOCAL AppTest prepared_modal_open_ms={open_ms:.1f} provider_reads_on_open=0')


class SyntheticScalingTests(unittest.TestCase):
    def test_measured_scaling_and_warm_zero_provider_reads(self):
        baseline={}
        exec(compile(Path('tests/fixtures/crm_audience_reads_baseline.py').read_text(encoding='utf-8'),'<baseline>','exec'),baseline)
        for count in (50,1000,1093,5000,10000):
            wire=ShopifyFixture(count)
            for c in wire.customers:
                c['defaultAddress']['countryCodeV2']='AU';c['emailMarketingConsent']['marketingState']='SUBSCRIBED'
                c['defaultEmailAddress']=native_customer(c)['defaultEmailAddress']
            def transport(query,variables):
                time.sleep(.005) # Simulated 5ms per request; never claim Shopify latency.
                return wire(query,variables)
            shop=Shopify(transport=transport,namespace='synthetic-'+str(count));db=store()
            from crm_campaign_send import final_audience
            wire.calls.clear();started=time.perf_counter()
            with patch('crm_campaign_review_reads.selected_reads',side_effect=baseline['selected_reads']):
                before=final_audience(shop,db,doc())
            before_ms=(time.perf_counter()-started)*1000
            old_calls=len(wire.calls);wire.calls.clear();started=time.perf_counter()
            job=prepare(None,shop,db,doc(),CFG,debounce=0);state=job.result()
            cold_ms=(time.perf_counter()-started)*1000;new_calls=len(wire.calls)
            started=time.perf_counter();self.assertIs(prepare(job,shop,db,doc(),CFG),job);job.result()
            warm_ms=(time.perf_counter()-started)*1000
            self.assertEqual(len(wire.calls),new_calls);self.assertEqual(state['eligible'],count)
            self.assertEqual(before['recipients'],state['recipients'])
            self.assertFalse(any('CrmCampaignSubscribers' in q for q,v in wire.calls))
            self.assertFalse(any('query CrmCustomer(' in q for q,v in wire.calls))
            self.assertTrue(all(len(v['ids'])<=50 for q,v in wire.calls if 'ids' in v))
            print(f'SYNTHETIC recipients={count} latency=5ms old_prepare_ms={before_ms:.1f} old_total_calls={old_calls} cold_prepare_ms={cold_ms:.1f} cold_total_calls={new_calls} warm_ms={warm_ms:.3f} warm_calls=0')


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class LocalSendAcceptanceTests(unittest.TestCase):
    def test_1093_prepared_review_and_bulk_acceptance_is_idempotent_without_transport(self):
        from tests.crm_db_fixture import connect
        from tests.test_crm import ADMIN
        from crm_campaign_store import CampaignStore
        from crm_campaign_send import queue_campaign
        count=1093;wire=ShopifyFixture(count)
        offset=uuid.uuid4().int%1000000000000+1000000000000
        for c in wire.customers:
            c['defaultAddress']['countryCodeV2']='AU';c['emailMarketingConsent']['marketingState']='SUBSCRIBED'
            c['id']='gid://shopify/Customer/'+str(offset+int(c['id'].rsplit('/',1)[-1]))
            c['email']=str(offset)+'-'+c['email']
        def transport(query,variables):
            time.sleep(.005)
            return wire(query,variables)
        sql_calls=[]
        class CountConnection:
            def __init__(self):self.connection=connect()
            def __enter__(self):self.connection.__enter__();return self
            def __exit__(self,*args):return self.connection.__exit__(*args)
            def execute(self,sql,args=()):sql_calls.append(sql);return self.connection.execute(sql,args)
        db=CampaignStore(CountConnection);shop=Shopify(transport=transport,namespace='local-acceptance')
        with patch.object(db,'render_settings',return_value=CFG), \
             patch('requests.sessions.Session.request',side_effect=AssertionError('Live network forbidden')):
            editor=db.save(ADMIN,'Synthetic 1093 '+uuid.uuid4().hex,doc(),env=LIVE)
            started=time.perf_counter();job=prepare(None,shop,db,editor['document'],CFG,debounce=0);job.result()
            cold_ms=(time.perf_counter()-started)*1000;wire.calls.clear()
            started=time.perf_counter();result=review(shop,db,editor,LIVE,audience_job=job)
            warm_review_ms=(time.perf_counter()-started)*1000
            self.assertEqual(len(wire.calls),0);self.assertEqual(result['blockers'],[])
            operation=str(uuid.uuid4());sql_calls.clear();started=time.perf_counter()
            queued=queue_campaign(shop,db,ADMIN,editor,operation,env=LIVE,snapshot_id=result['snapshot_id'])
            acceptance_ms=(time.perf_counter()-started)*1000
            new_sql=len(sql_calls)
            queue_calls=len(wire.calls)
            self.assertEqual(queued['status'],'SENDING');self.assertEqual(queued['recipients'],count)
            self.assertEqual(db.q('SELECT count(*) n FROM crm_marketing_sends WHERE campaign_id=%s',(editor['id'],),True)['n'],count)
            self.assertEqual(db.q("SELECT count(*) n FROM crm_marketing_sends WHERE campaign_id=%s AND provider_email_id IS NOT NULL",(editor['id'],),True)['n'],0)
            again=queue_campaign(shop,db,ADMIN,editor,str(uuid.uuid4()),env=LIVE,snapshot_id=result['snapshot_id'])
            self.assertTrue(again['already_started']);self.assertEqual(len(wire.calls),queue_calls)
            self.assertEqual(queue_calls,22)
            old_editor=db.save(ADMIN,'Baseline 1093 '+uuid.uuid4().hex,doc(),env=LIVE)
            old_review=review(shop,db,old_editor,LIVE,audience_job=job)
            baseline={}
            exec(compile(Path('tests/fixtures/crm_send_queue_baseline.py').read_text(encoding='utf-8'),'<queue baseline>','exec'),baseline)
            sql_calls.clear();wire.calls.clear();started=time.perf_counter()
            old=baseline['queue_campaign'](shop,db,ADMIN,old_editor,str(uuid.uuid4()),env=LIVE,snapshot_id=old_review['snapshot_id'])
            old_ms=(time.perf_counter()-started)*1000;old_sql=len(sql_calls)
            self.assertEqual(old['recipients'],count)
            self.assertEqual(old_sql-new_sql,2184)
            print(f'LOCAL SQL recipients=1093 simulated_graph_latency=5ms cold_prepare_ms={cold_ms:.1f} warm_review_ms={warm_review_ms:.1f} warm_review_graph_calls=0 queue_before_ms={old_ms:.1f} queue_after_ms={acceptance_ms:.1f} queue_sql_before={old_sql} queue_sql_after={new_sql} queue_graph_calls={queue_calls} transport_calls=0 durable_jobs={count}')


if __name__=='__main__':unittest.main()
