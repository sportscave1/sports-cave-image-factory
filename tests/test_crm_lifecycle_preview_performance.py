"""Offline timing, cache ownership, and background completion regressions."""
from concurrent.futures import Future
from copy import deepcopy
import time
from unittest import TestCase
from unittest.mock import patch
from crm_flow_preview import context,examples,choose,cached_candidate,hydrate,NoPreviewCustomer
from tests.test_crm_flow_customer_preview import preview_wire,document


def complete(fn):
    f=Future();f.set_result(fn());return f


class PreviewPerformanceTests(TestCase):
    def test_native_default_inactivity_matches_existing_delivery_default(self):
        from crm_flow_preview import verify
        from tests.test_crm_flow_customer_preview import AT
        store,shop,row,candidate,operational=preview_wire('win_back',age=130)
        row['config']['draft'].pop('inactive_days')
        with patch('crm_lifecycle_shopify.order_facts',return_value=operational),patch('crm_flow_preview.now',return_value=AT):
            with self.assertRaisesRegex(ValueError,'inactive'):verify(store,shop,row,candidate)

    def test_preview_uses_draft_inactivity_and_never_mutates_published_policy(self):
        from crm_flow_preview import verify
        from tests.test_crm_flow_customer_preview import AT
        store,shop,row,candidate,operational=preview_wire('win_back',age=100)
        row['config']['published_flow']={**deepcopy(row['config']['draft']),'inactive_days':180}
        before=deepcopy(row)
        with patch('crm_lifecycle_shopify.order_facts',return_value=operational),patch('crm_flow_preview.now',return_value=AT):
            self.assertEqual(verify(store,shop,row,candidate)['_customer']['id'],candidate['customer_id'])
        self.assertEqual(before,row)

    def test_first_success_stops_verifying_optional_customers_and_clears_error(self):
        store,shop,row,candidate,_=preview_wire();store.q.side_effect=None
        store.q.return_value=[candidate,{**candidate,'key':'other','customer_id':'other'}]
        with patch('crm_flow_preview.verify',return_value={'key':candidate['key'],'label':'First'}) as verify:
            result=examples(store,shop,row)
        self.assertEqual(verify.call_count,1);self.assertEqual(result['error'],'')
        self.assertEqual(len(result['options']),2)

    def test_last_good_is_retained_refresh_failure_is_actionable_success_clears(self):
        store,_,_,candidate,_=preview_wire();state={};data={'key':candidate['key'],'label':'First'}
        f=Future()
        with patch('crm_flow_preview.examples',return_value={'selected':data,'options':[candidate],'error':''}),patch('crm_campaign_home_cache.POOL.submit',side_effect=complete):
            initial=context(state,store);self.assertIsNotNone(initial['selected'])
        with patch('crm_campaign_home_cache.POOL.submit',return_value=f):
            refreshed=context(state,store,refresh=True)
            self.assertEqual(refreshed['selected']['label'],'First')
            f.set_result({'selected':None,'error':'Scope verification failed','options':[candidate]})
            pin=context(state,store)
            self.assertEqual(pin['selected']['label'],'First');self.assertIn('Scope',pin['error'])
        with patch('crm_flow_preview.examples',return_value={'selected':deepcopy(data),'options':[candidate],'error':''}),patch('crm_campaign_home_cache.POOL.submit',side_effect=complete):
            self.assertEqual(context(state,store,refresh=True)['error'],'')

    def test_warm_reopen_and_switch_to_cached_example_do_not_verify(self):
        store,_,row,candidate,_=preview_wire();state={};data={'key':candidate['key'],'label':'First'}
        with patch('crm_flow_preview.examples',return_value={'selected':data,'options':[candidate],'error':''}) as lookup,patch('crm_campaign_home_cache.POOL.submit',side_effect=complete):
            first=context(state,store)
            other=deepcopy(row);other['id']='another-flow';store.preview_row=other;context(state,store)
            store.preview_row=row;self.assertIs(context(state,store),first)
            with patch('crm_flow_preview.verify') as verify:choose(state,store,candidate['key']);verify.assert_not_called()
            self.assertEqual(lookup.call_count,2)

    def test_slow_customer_switch_runs_off_thread_and_keeps_previous_example(self):
        store,_,_,candidate,_=preview_wire();state={};data={'key':candidate['key'],'label':'First'}
        alternate={**candidate,'key':'second','customer_id':'second'}
        with patch('crm_flow_preview.examples',return_value={'selected':data,'options':[candidate,alternate],'error':''}),patch('crm_campaign_home_cache.POOL.submit',side_effect=complete):context(state,store)
        f=Future()
        with patch('crm_campaign_home_cache.POOL.submit',return_value=f),patch('crm_flow_preview.verify') as verify:
            start=time.perf_counter();choose(state,store,'second');duration=time.perf_counter()-start
            verify.assert_not_called();self.assertLess(duration,.05)
        self.assertEqual(context(state,store)['selected']['label'],'First')
        f.set_result({'selected':{'key':'second','label':'Second'},'error':''})
        self.assertEqual(context(state,store)['selected']['label'],'Second')

    def test_local_seed_requires_verified_profile_and_exact_order_lines(self):
        store,_,row,candidate,_=preview_wire()
        profile=store.preview_shop.customer.return_value
        order=store.preview_shop.orders.return_value['nodes'][0]
        from crm_logic import now
        c={**candidate,'profile':profile,'verified_at':now(),'paid_at':order['createdAt'],
           'order_record':{'shopify_order_id':order['id'],'created_at':order['createdAt'],'financial_status':'PAID','raw_json':order}}
        seed=cached_candidate(row,c)
        self.assertTrue(seed['_cached']);self.assertEqual(seed['_order']['customer']['id'],profile['id'])
        c['profile']={**profile,'id':'another-customer'};self.assertIsNone(cached_candidate(row,c))

    def test_html_edits_reuse_artwork_facts_without_network(self):
        from crm_collector_images import configurations,marker
        store,_,_,candidate,_=preview_wire();doc=document();state={}
        data={'key':candidate['key'],'label':'First','_customer':store.preview_shop.customer.return_value,
              '_order':store.preview_shop.orders.return_value['nodes'][0],'_lifecycle_orders':store.preview_shop.orders.return_value['nodes']}
        pin={'selected':data,'options':[candidate],'error':'','renders':{}}
        facts={'recipient':data['_customer']['id'],'blocks':{marker(configurations(doc)[0]):[{'id':'art','title':'Fixture art','quantity':1,'image':'https://cdn.shopify.com/fixture.png'}]}}
        with patch('crm_flow_preview.context',return_value=pin),patch('crm_collector_resolver.resolve',return_value=facts) as read,patch('crm_campaign_home_cache.POOL.submit',side_effect=complete):
            hydrate(state,store,doc)
            for i in range(4):
                from crm_middle_sections import commit_middle
                doc['middle_sections'][0]['html']=doc['middle_sections'][0]['html'].replace('chosen by you','chosen by you!')
                commit_middle(doc,doc['middle_sections']);hydrate(state,store,doc)
            self.assertEqual(read.call_count,1)
