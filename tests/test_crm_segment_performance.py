"""Deferred aggregate counts, parity and real composer tests. No live I/O."""
import os
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from unittest.mock import Mock,patch
from crm_segment_counts import SegmentCounts,TTL,REVISION_INTERVAL,FAILURE_BACKOFF
from crm_campaign_markets import calculate,country,MARKET_LABELS,COUNTRIES
from crm_audience import evaluate_profiles
from crm_logic import recipient_hash
from tests.test_crm_campaign_v2 import profile,authority
from crm_preview_cache import preview
from tests.test_crm_simple_editor import document
from tests.test_crm_send_flow import CFG

class Queue:
    def __init__(self):self.jobs=[]
    def submit(self,fn,*args):self.jobs.append(lambda:fn(*args))
    def run(self):self.jobs.pop(0)()

class CacheTests(unittest.TestCase):
    def setUp(self):
        self.t=[0];self.queue=Queue();self.shop=Mock(namespace='account');self.store=Mock(connect=None)
        self.store.state.return_value={'version':'one'}
        self.loader=Mock(return_value={m:{'subscribed':i} for i,m in enumerate(MARKET_LABELS)})
        self.cache=SegmentCounts(clock=lambda:self.t[0],executor=self.queue,loader=self.loader)
    def view(self):return self.cache.display(self.shop,self.store)
    def test_initial_returns_placeholder_without_io_and_single_flight(self):
        for _ in range(10):self.assertTrue(self.view()['pending'])
        self.assertEqual(len(self.queue.jobs),1);self.loader.assert_not_called();self.store.state.assert_not_called()
        self.queue.run();self.assertEqual(self.view()['counts']['Global'],3)
        for _ in range(10):self.view()
        self.assertEqual(len(self.queue.jobs),0);self.loader.assert_called_once()
    def test_ttl_revision_poll_does_not_scan_and_expiry_defers(self):
        self.view();self.queue.run();self.t[0]=REVISION_INTERVAL+1
        self.view();self.queue.run();self.loader.assert_called_once()
        self.t[0]=TTL+1;self.view();self.loader.assert_called_once()
        self.queue.run();self.assertEqual(self.loader.call_count,2)
    def test_failure_retains_counts_and_backs_off(self):
        self.view();self.queue.run();self.t[0]=TTL+1;self.loader.side_effect=RuntimeError('SECRET')
        self.view();self.queue.run();state=self.view()
        self.assertEqual(state['counts']['Global'],3);self.assertTrue(state['error']);self.assertNotIn('SECRET',str(state))
        self.assertEqual(len(self.queue.jobs),0)
        self.t[0]+=FAILURE_BACKOFF+1;self.view();self.assertEqual(len(self.queue.jobs),1)
    def test_accounts_are_separate_but_hours_share_counts(self):
        self.view();self.cache.display(Mock(namespace='another'),self.store);self.cache.display(self.shop,self.store,24)
        self.assertEqual(len(self.queue.jobs),2)
    def test_suppression_changes_during_refresh_do_not_publish_stale_values(self):
        self.store.state.side_effect=[{'version':'one'},{'version':'two'}]
        self.view();self.queue.run();self.assertEqual(self.view()['counts'],{})
    def test_fresh_send_bypasses_display_cache(self):
        from crm_campaign_send import final_audience
        doc=document();doc['market_audience']=True
        source=authority([profile(1)])
        store=Mock();store.state.return_value={};store.active_suppression_hashes.return_value=(set(),set());store.recent_marketing_hashes.return_value=set()
        with patch('crm_segment_counts.COUNTS.display',side_effect=AssertionError('Send cannot use display cache')):
            self.assertEqual(final_audience(source,store,doc)['eligible'],1)
            source.campaign_subscribers.return_value['nodes'][0]['emailMarketingConsent']['marketingState']='UNSUBSCRIBED'
            self.assertEqual(final_audience(source,store,doc)['eligible'],0)
        source.campaign_subscribers.assert_not_called()
        self.assertEqual(source.customer_batch.call_count,1)  # Empty membership needs no profiles.
    def test_html_preview_segment_only_change_reuses_safe_html(self):
        doc=document();state={}
        with patch('crm_preview_cache.render_campaign',wraps=__import__('crm_campaign_content').render_campaign) as render:
            first=preview(state,doc,CFG);doc['market']='US';second=preview(state,doc,CFG)
            self.assertEqual(first,second);render.assert_called_once()

class EligibilityTests(unittest.TestCase):
    def test_once_per_profile_and_worldwide_includes_other_country(self):
        rows=[profile(1),profile(2,'US'),profile(3,'GB'),profile(4,'NZ'),profile(5,'CA'),profile(6,consent='UNSUBSCRIBED'),profile(7),profile(8)]
        rows[7]['email']=rows[0]['email']
        store=Mock();store.state.return_value={};store.active_suppression_hashes.return_value=({recipient_hash(rows[6]['email'])},set());store.recent_marketing_hashes.return_value=set()
        from crm_logic import eligibility
        with patch('crm_campaign_markets.country',wraps=country) as normalize,patch('crm_campaign_markets.eligibility',wraps=eligibility) as evaluate:
            result=calculate(authority(rows),store)
        self.assertEqual(normalize.call_count,0);self.assertEqual(evaluate.call_count,len(rows))
        self.assertEqual({k:v['eligible'] for k,v in result.items()},{'AU':1,'US':1,'UK':1,'Global':5,'CA':1,'NZ':1})
    def test_matches_previous_policy_for_cross_country_duplicates_conflicts_and_suppression(self):
        import random
        rng=random.Random(42)
        rows=[profile(i,rng.choice(['AU','US','GB','NZ']),consent=rng.choice(['SUBSCRIBED','SUBSCRIBED','PENDING','UNSUBSCRIBED'])) for i in range(200)]
        for i,c in enumerate(rows):
            c['email']=f'p{i//3}@example.test'
            if i%17==0:c['validEmailAddress']=False
        suppressed={recipient_hash(rows[12]['email'])};ids={rows[50]['id']};recent={recipient_hash(rows[36]['email'])}
        store=Mock();store.state.return_value={};store.active_suppression_hashes.return_value=(suppressed,ids);store.recent_marketing_hashes.return_value=recent
        actual=calculate(authority(rows),store);states={}
        for c in rows:states.setdefault(recipient_hash(c['email']),set()).add(c['emailMarketingConsent']['marketingState'])
        conflicts={h for h,s in states.items() if len(s)>1}
        for market in MARKET_LABELS:
            subset=[c for c in rows if c['emailMarketingConsent']['marketingState']=='SUBSCRIBED' and (market=='Global' or country(c)==COUNTRIES[market])]
            safe=[c for c in subset if recipient_hash(c['email']) not in conflicts]
            previous=evaluate_profiles(safe,set(),set(),suppressed,ids,recent,recipients=True)
            if len(subset)>len(safe):previous['excluded']['conflicting_consent']=len(subset)-len(safe)
            self.assertEqual(actual[market]['eligible'],previous['eligible'])
            self.assertEqual(actual[market]['excluded'],previous['excluded'])
            self.assertEqual(actual[market]['recipients'],previous['recipients'])

@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Local SQL fixture required')
class ComposerTests(unittest.TestCase):
    def test_editor_and_typing_work_while_subscriber_request_is_blocked(self):
        from streamlit.testing.v1 import AppTest
        from tests.test_crm_ui import SCRIPT
        entered=threading.Event();release=threading.Event()
        def slow(*args):entered.set();release.wait(20);return {m:{'subscribed':4} for m in MARKET_LABELS}
        executor=ThreadPoolExecutor(max_workers=1);cache=SegmentCounts(executor=executor,loader=Mock(side_effect=slow))
        try:
            with patch('crm_segment_counts.COUNTS',cache):
                at=AppTest.from_string(SCRIPT.replace("'role':'worker'","'role':'admin'"));at.session_state['route']='CRM Campaigns';at.run(timeout=10)
                self.assertFalse(at.exception);self.assertTrue(entered.wait(2));self.assertFalse(release.is_set())
                self.assertEqual(next(s for s in at.selectbox if s.label=='Segment').options,
                    ['AUSTRALIA · …','USA · …','UK · …','ALL SUBSCRIBERS · …','CANADA · …','NEW ZEALAND · …'])
                self.assertTrue({'Save draft','Send now'}.issubset({b.label for b in at.button}))
                for label in ['Subject','Preview text','Campaign name']:
                    next(t for t in at.text_input if t.label==label).set_value('Edited '+label).run(timeout=10)
                    self.assertFalse(at.exception)
                for tab in ['Editor','Templates','Settings']:
                    at.session_state[at.session_state['campaign_edit_key']+'panel']=tab
                    at.run(timeout=10);self.assertFalse(at.exception)
                with patch('crm_campaign_send_ui.send_test',return_value={'audit_saved':True}) as send:
                    next(t for t in at.text_input if t.label=='Send test email').set_value('manual@example.org')
                    next(b for b in at.button if b.label=='→').click().run(timeout=10)
                    send.assert_called_once();self.assertFalse(release.is_set());self.assertFalse(at.exception)
                cache.loader.assert_called_once()
                self.assertFalse(any('Loading subscribers'  in c.value for c in at.caption))
                release.set();executor.shutdown(wait=True)
                at.run(timeout=10)
                self.assertEqual(next(s for s in at.selectbox if s.label=='Segment').options[0],'AUSTRALIA · 4')
        finally:release.set();executor.shutdown(wait=True)
    def test_list_metadata_excludes_bodies_and_selected_template_loads(self):
        from crm_campaign_store import CampaignStore
        from crm_campaign_library import save_template,library_rows,template_html
        from tests.crm_db_fixture import connect
        from tests.test_crm import ADMIN
        import uuid
        store=CampaignStore(connect);row=store.save(ADMIN,'Metadata '+uuid.uuid4().hex,document())
        listing=store.list_drafts(search=row['name'],metadata=True)[0]
        self.assertEqual(set(listing['document']),{'market','send_timing'})
        template=save_template(store,ADMIN,'Metadata '+uuid.uuid4().hex,'<p>Only load on selection</p>')
        item=next(r for r in library_rows(store) if r['id']==template['id'])
        self.assertEqual(set(item['content']),{'format'})
        self.assertIn('Only load on selection',template_html(store,item))
        before=store.email_defaults(CFG)['header']
        try:
            store.save_email_default(ADMIN,'header','<p>Only selected header</p>',before['version'])
            with patch.object(store,'q',wraps=store.q) as reads:
                store.default_sections(CFG)
                reads.reset_mock()
                self.assertEqual(store.default_sections(CFG)['header'],'<p>Only selected header</p>')
                self.assertEqual(reads.call_count,1)
                self.assertIn('SELECT key,version',reads.call_args.args[0])
        finally:
            current=store.email_defaults(CFG)['header']
            store.save_email_default(ADMIN,'header',before['value']['html'],current['version'])
