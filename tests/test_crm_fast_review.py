"""Offline authoritative audience path, bounded reads and compact modal regressions."""
from copy import deepcopy
from pathlib import Path
import subprocess
import threading
import time
import unittest
from unittest.mock import Mock, MagicMock, patch

from crm_campaign_markets import calculate
from crm_campaign_review_reads import selected_profiles
from crm_campaign_review import start_review
from crm_campaign_send import final_audience
from crm_shopify import Shopify, CapabilityUnavailable
from tests.crm_fixtures import ShopifyFixture, native_customer, page
from tests.test_crm_campaign_v2 import profile, authority
from tests.test_crm_simple_editor import document


def store():
    result=Mock();result.state.return_value={}
    result.active_suppression_hashes.return_value=(set(),set())
    result.recent_marketing_hashes.return_value=set()
    return result


class FastReviewTests(unittest.TestCase):
    def test_four_nz_members_no_store_scan(self):
        shop=authority([profile(i,'NZ') for i in range(1,5)]+[profile(i,'AU') for i in range(5,1005)])
        db=store()
        result=calculate(shop,db,market='NZ')['NZ']
        self.assertEqual(result['eligible'],4)
        shop.campaign_subscribers.assert_not_called()
        self.assertEqual(len(shop.customer_batch.call_args.args[0]),4)
        shop.customer_batch.assert_called_once();shop.campaign_email_profiles.assert_called_once()
        shop.customer.assert_not_called()
        db.active_suppression_hashes.assert_called_once();db.recent_marketing_hashes.assert_called_once()

    def test_101_profiles_use_three_batches(self):
        shop=authority([profile(i,'NZ') for i in range(1,102)])
        self.assertEqual(calculate(shop,store(),market='NZ')['NZ']['eligible'],101)
        self.assertEqual([len(c.args[0]) for c in shop.customer_batch.call_args_list],[50,50,1])
        shop.customer.assert_not_called();shop.campaign_subscribers.assert_not_called()

    def test_duplicate_and_outside_conflicting_consent_match_old_policy(self):
        rows=[profile(1,'NZ'),profile(2,'NZ'),profile(3,'AU',consent='UNSUBSCRIBED'),profile(4,'NZ')]
        rows[1]['email']=rows[0]['email'];rows[2]['email']=rows[3]['email']
        shop=authority(rows)
        result=calculate(shop,store(),market='NZ')['NZ']
        self.assertEqual(result['eligible'],1)
        self.assertEqual(result['excluded'],{'duplicate':1,'conflicting_consent':1})
        self.assertEqual(len(result['recipients']),1)

    def test_missing_batch_or_conflict_identity_fails_closed(self):
        for stage in ('customer_batch','campaign_email_profiles'):
            shop=authority([profile(1,'NZ')])
            getattr(shop,stage).side_effect=None;getattr(shop,stage).return_value=[]
            with self.subTest(stage=stage),self.assertRaises(ValueError):calculate(shop,store(),market='NZ')

    def test_changed_consent_between_reads_fails_closed(self):
        shop=authority([profile(1,'NZ')]);changed=native_customer(profile(1,'NZ',consent='UNSUBSCRIBED'))
        shop.campaign_email_profiles.side_effect=None;shop.campaign_email_profiles.return_value=[changed]
        with self.assertRaisesRegex(ValueError,'changed'):calculate(shop,store(),market='NZ')

    def test_real_adapter_chunks_email_queries_not_n_plus_one(self):
        fixture=ShopifyFixture(101)
        for c in fixture.customers:
            c['defaultAddress']['countryCodeV2']='NZ';c['emailMarketingConsent']['marketingState']='SUBSCRIBED'
        shop=Shopify(transport=fixture)
        result=calculate(shop,store(),market='NZ')['NZ']
        self.assertEqual(result['eligible'],101)
        documents=[doc for doc,v in fixture.calls]
        self.assertEqual(sum('CrmCustomerBatch' in d for d in documents),3)
        self.assertEqual(sum('CrmCampaignEmailProfiles' in d for d in documents),5)
        self.assertFalse(any('CrmCampaignSubscribers' in d for d in documents))
        self.assertFalse(any('query CrmCustomer(' in d for d in documents))

    def test_conflict_pagination_is_complete_and_unstable_fails_closed(self):
        first=native_customer(profile(1));other=native_customer(profile(2,consent='UNSUBSCRIBED'));other['email']=first['email']
        responses=[{'customers':page([first,other],None,1)},{'customers':page([first,other],'1',1)}]
        shop=Shopify(transport=Mock(side_effect=responses))
        self.assertEqual(len(shop.campaign_email_profiles([first['email']])),2)
        responses=[{'customers':{'nodes':[first],'pageInfo':{'hasNextPage':True,'endCursor':'one'}}}]*2
        shop=Shopify(transport=Mock(side_effect=responses))
        with self.assertRaisesRegex(ValueError,'pagination'):shop.campaign_email_profiles([first['email']])

    def test_native_selection_preserves_union_exclusion_and_no_scan(self):
        rows=[profile(i) for i in range(1,5)];shop=authority(rows)
        shop.segment.side_effect=lambda identity,**kw:{'id':identity,'query':identity}
        shop.campaign_member_ids.side_effect=lambda query:{rows[i]['id'] for i in ([0,1,2] if query.endswith('/1') else [2,3])}
        doc=document();doc['market_audience']=False
        doc['audience']={'kind':'Selection','name':'Native','include':[{'kind':'Shopify','name':'One','id':'gid://shopify/Segment/1'}],
            'exclude':[{'kind':'Shopify','name':'Two','id':'gid://shopify/Segment/2'}]}
        result=final_audience(shop,store(),doc)
        self.assertEqual(result['eligible'],2);self.assertEqual(result['excluded'],{'excluded_segment':1})
        shop.customers.assert_not_called();shop.campaign_subscribers.assert_not_called()

    def test_settings_change_invalidates_completed_review(self):
        editor={'id':'fixture','version':1,'name':'Fixture','document':document()}
        with patch('crm_campaign_review.review',return_value={'snapshot_id':'one'}):
            first=start_review(None,Mock(),Mock(),{},editor,deepcopy(editor),{'from':'one'})
            first.future.result(3)
            self.assertIs(start_review(first,Mock(),Mock(),{},editor,editor,{'from':'one'}),first)
            second=start_review(first,Mock(),Mock(),{},editor,editor,{'from':'two'})
            second.future.result(3);self.assertIsNot(first,second)

    def test_independent_suppression_read_overlaps_profile_fetch(self):
        started=threading.Event();shop=authority([profile(1,'NZ')]);db=store()
        db.active_suppression_hashes.side_effect=lambda:started.set() or (set(),set())
        original=shop.customer_batch.side_effect
        shop.customer_batch.side_effect=lambda ids,**kw: (self.assertTrue(started.wait(2)),original(ids,**kw))[1]
        calculate(shop,db,market='NZ')

    def test_safe_stage_logs_contain_no_identity_or_payload(self):
        shop=authority([profile(1,'NZ')])
        with self.assertLogs('crm_campaign_review_reads',level='INFO') as captured:
            calculate(shop,store(),market='NZ')
        logs=' '.join(captured.output)
        self.assertIn('stage=conflict_validation',logs)
        self.assertNotIn('example.test',logs);self.assertNotIn('gid://',logs);self.assertNotIn('token=',logs)

    def test_review_reuses_one_final_render_and_settings_read(self):
        from crm_campaign_send import review
        from crm_email_size import render_production
        from tests.test_crm_send_flow import CFG,LIVE
        doc=document();editor={'id':'47bb53bc-9a37-4f99-a840-e775073dbce5','version':1,'name':'Fixture','document':doc}
        state={'members':1,'eligible':1,'excluded':{},'complete':True,'checked_at':__import__('crm_logic').now().isoformat(),
            'recipients':[{'id':'gid://shopify/Customer/1','hash':'fixture'}],'profiles':{'gid://shopify/Customer/1':native_customer(profile(1))}}
        db=store();db.render_settings.return_value=CFG
        with patch('crm_campaign_send.final_audience',return_value=state),patch('crm_campaign_snapshot.create',return_value='one'), \
             patch('crm_email_size.render_production',wraps=render_production) as rendered:
            result=review(None,db,editor,LIVE)
        self.assertTrue(result['tracking_ok']);self.assertIsNotNone(result['email_size'])
        rendered.assert_called_once();db.render_settings.assert_called_once()

    def test_queue_revalidation_only_removes_reviewed_recipients(self):
        from crm_campaign_send import queue_campaign
        from crm_logic import recipient_hash,now
        from tests.test_crm_send_flow import CFG,LIVE
        from tests.test_crm import ADMIN
        rows=[profile(1),profile(2,consent='UNSUBSCRIBED'),profile(3)]
        shop=authority(rows);doc=document();doc['counts']={'members':2,'eligible':2,'excluded':{},'complete':True,'checked_at':now().isoformat()}
        editor={'id':'47bb53bc-9a37-4f99-a840-e775073dbce5','version':1,'name':'Fixture','document':doc,'archived_at':None}
        recipients=[{'id':c['id'],'hash':recipient_hash(c['email'])} for c in rows[:2]]
        snapshot={'campaign_version':1,'document':doc,'recipients':recipients,'render_settings':CFG,'schedule':{},'created_at':now()}
        db=store();db.q.return_value=None;db.draft.return_value=editor;db.render_settings.return_value=CFG;db.suppressed.return_value=False
        conn=MagicMock();db.db.return_value=MagicMock();db.db.return_value.__enter__.return_value=conn
        writes=[]
        def execute(sql,args):
            result=Mock();result.fetchall.return_value=[]
            result.fetchone.return_value=editor if 'FOR UPDATE' in sql else ({'id':'segment'} if 'INSERT INTO crm_segment_definitions' in sql else None)
            if 'INSERT INTO crm_marketing_sends' in sql:writes.extend(__import__('json').loads(args[2]))
            return result
        conn.execute.side_effect=execute
        with patch('crm_campaign_snapshot.load',return_value=snapshot),patch('crm_campaign_send.production_checks',return_value={'safe':True}):
            result=queue_campaign(shop,db,ADMIN,editor,'47bb53bc-9a37-4f99-a840-e775073dbce5',env=LIVE,snapshot_id='one')
        self.assertEqual(result['recipients'],1);self.assertEqual(result['skipped_after_review'],1)
        self.assertEqual({r['shopify_customer_id'] for r in writes},{c['id'] for c in rows[:2]})
        self.assertEqual([r['status'] for r in writes],['PENDING','BLOCKED'])
        self.assertTrue(shop.customer_batch.call_args.kwargs['fresh'])
        shop.campaign_member_ids.assert_not_called();shop.campaign_subscribers.assert_not_called()

    def test_synthetic_before_after_store_scan(self):
        namespace={}
        from pathlib import Path
        old=Path('tests/fixtures/crm_market_scan_baseline.py').read_text(encoding='utf-8')
        exec(compile(old,'<baseline>','exec'),namespace)
        rows=[profile(i,'NZ' if i<=4 else 'AU') for i in range(1,1001)]
        baseline=authority(rows);baseline.campaign_subscribers.side_effect=lambda after=None:page([native_customer(c) for c in rows],after,250)
        started=time.perf_counter();before=namespace['calculate'](baseline,store(),market='NZ')['NZ'];before_ms=(time.perf_counter()-started)*1000
        optimized=authority(rows);started=time.perf_counter();after=calculate(optimized,store(),market='NZ')['NZ'];after_ms=(time.perf_counter()-started)*1000
        self.assertEqual(before['recipients'],after['recipients'])
        self.assertEqual(baseline.campaign_subscribers.call_count,4);optimized.campaign_subscribers.assert_not_called()
        print(f'Synthetic NZ/4 in 1000 profiles: before scanned=1000 pages=4 ms={before_ms:.1f}; after profiles=4 batches=1 conflict_groups=1 scan_pages=0 ms={after_ms:.1f}')


class CompactReviewTests(unittest.TestCase):
    SCRIPT = '''
import streamlit as st
from copy import deepcopy
from crm_campaign_send_ui import review_dialog
from tests.test_crm_simple_editor import document
if 'campaign_editor' not in st.session_state:
 st.session_state.campaign_editor={'id':'47bb53bc-9a37-4f99-a840-e775073dbce5','version':1,'name':'Fixture','document':document(),'archived_at':None}
 st.session_state.campaign_saved=deepcopy(st.session_state.campaign_editor)
if st.button('Open'):
 review_dialog(None,None,{},st.session_state.campaign_editor,'compact_')
'''

    def test_modal_shell_pending_then_final_count_without_send(self):
        from streamlit.testing.v1 import AppTest
        gate=threading.Event();entered=threading.Event()
        def finish(*args):
            entered.set();gate.wait(3)
            return {'counts':{'eligible':4,'excluded':{}},'blockers':[],'snapshot_id':'one','tracking_ok':True,
                    'email_size':{'html_kb':13.6,'status':'SAFE'}}
        app=AppTest.from_string(self.SCRIPT)
        with patch('crm_campaign_review.review',side_effect=finish), \
             patch('crm_campaign_send_ui.get_resend_marketing_config_status',return_value={'marketing_enabled':True,'sender':'Fixture','reply_to':'Fixture'}), \
             patch('crm_campaign_send_ui.queue_campaign',side_effect=AssertionError('Never send')) as send:
            try:
                app.run();next(b for b in app.button if b.label=='Open').click().run()
                self.assertTrue(entered.wait(1));self.assertFalse(app.exception)
                self.assertTrue(next(b for b in app.button if str(b.key).endswith('confirm_send')).disabled)
                self.assertTrue(any('Verifying' in text.value for text in app.markdown))
                gate.set();app.session_state['compact_review_job'].future.result(3)
                app.run();next(b for b in app.button if b.label=='Open').click().run()
                self.assertFalse(app.exception)
                self.assertFalse(next(b for b in app.button if b.label=='Send to 4 recipients').disabled)
                self.assertTrue(any('13.6 KB' in c.value for c in app.caption))
                self.assertTrue(any('Tracking' in c.value for c in app.caption));send.assert_not_called()
            finally:gate.set()

    def test_session_draft_replacement_blocks_old_review(self):
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_string(self.SCRIPT)
        result={'counts':{'eligible':4,'excluded':{}},'blockers':[],'snapshot_id':'one','tracking_ok':True}
        with patch('crm_campaign_review.review',return_value=result), \
             patch('crm_campaign_review.save_checkpoint',side_effect=lambda db,user,editor:deepcopy(editor)), \
             patch('crm_campaign_send_ui.queue_campaign') as send:
            app.run();next(b for b in app.button if b.label=='Open').click().run()
            previous=app.session_state['compact_review_job'];previous.future.result(3)
            changed=deepcopy(app.session_state['campaign_editor']);changed['document']['content']['subject']='Changed'
            # Invoke the pending fragment's original editor with a replaced session value.
            from crm_campaign_review import identity
            self.assertNotEqual(identity(changed),app.session_state['compact_review_job'].identity)
            app.session_state['campaign_editor']=changed
            app.run();next(b for b in app.button if b.label=='Open').click().run()
            replacement=app.session_state['compact_review_job'];replacement.future.result(3)
            self.assertIsNot(previous,replacement)
            self.assertEqual(replacement.identity,identity(changed))
            self.assertFalse(app.exception);send.assert_not_called()

    def test_scoped_layout_natural_height_bounded_preview(self):
        source=Path('crm_campaign_send_ui.py').read_text(encoding='utf-8')
        shell=source.split('def review_dialog')[1].split('@st.fragment')[0]
        self.assertNotIn('min-height:255',source)
        self.assertNotIn("height=240,border=False",source)
        self.assertIn('height=240)',shell)
        self.assertIn('st.columns([42,58]',shell)
        self.assertIn('@media(max-width:640px)',source)
        self.assertIn('.st-key-crm-review-actions{position:sticky',source)
        fragment=source.split('def review_finalization')[1].split('def _review_finalization')[0]
        self.assertLess(fragment.index('_review_summary('),fragment.index('start_review('))
