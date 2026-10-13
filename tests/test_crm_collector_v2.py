"""Synthetic recipient tests; no remote credentials or production writes."""
from copy import deepcopy
import json
import os
from pathlib import Path
import time
import unittest
from unittest.mock import Mock,patch
from tests.test_crm_collector_personalisation import A,B,P,Q,AT,order,product,wire,context,doc_with
from crm_collector_images import settings,marker,render,configurations
from crm_collector_resolver import resolve,DISCOVERY,PRODUCTS,ORDER
from crm_collector_sports import definition_sport,segment_interests,relevance,search_tags
from crm_collector_stages import STAGES,mapping,document,apply,library_rows
from crm_buyer_segments import BUYER_NAMES,snapshot_key
from product_sport_tags import TAGS


def snapshot(customer=A):
    rows=json.loads(Path('docs/shopify-buyer-segments-observed.json').read_text())['nodes']
    rows=[r for r in rows if r['name'] in BUYER_NAMES]
    return {'timestamp':AT.timestamp(),'bindings':{r['name']:r['id'] for r in rows},
            'segments':{r['id']:{**r,'members':[customer]} for r in rows}}


class SportTests(unittest.TestCase):
    def test_all_28_actual_observed_definitions_are_understood_without_rewriting(self):
        state=snapshot();self.assertEqual(len(state['segments']),28)
        self.assertEqual(len({definition_sport(r) for r in state['segments'].values()}),28)
        self.assertNotIn(None,{definition_sport(r) for r in state['segments'].values()})
        self.assertEqual(sum(' OR ' in r['query'] for r in state['segments'].values()),23)

    def test_fresh_store_scoped_membership_and_stale_fallback(self):
        shop=Mock(namespace='fixture-store');store=Mock();store.state.return_value=snapshot()
        interests,authority=segment_interests(shop,store,A,AT)
        self.assertIn('Formula One',interests);self.assertNotIn('Apparel',interests)
        store.state.assert_called_with(snapshot_key(shop))
        self.assertEqual(segment_interests(shop,store,B,AT)[0],set())
        for age in (301,-1):
            store.state.return_value={**snapshot(),'timestamp':AT.timestamp()-age}
            self.assertEqual(segment_interests(shop,store,A,AT)[0],set())

    def test_changed_or_broadened_definition_never_infers_interest_from_name(self):
        state=snapshot();row=next(iter(state['segments'].values()))
        row['query']="number_of_orders >= 0"
        self.assertIsNone(definition_sport(row))
        row['query']="customer_tags CONTAINS 'interest:Basketball'"
        self.assertIsNone(definition_sport(row))

    def test_specific_then_parent_never_sibling_or_unrelated(self):
        for sport in ('Formula One','NASCAR','MotoGP','Motocross','Rally','Rally Raid','IndyCar','Motorcycle Road Racing'):
            interests={sport,'Motorsport'}
            self.assertEqual(relevance(interests,product(sport=sport)),0)
            self.assertEqual(relevance(interests,product(sport='Motorsport')),1)
            sibling='NASCAR' if sport!='NASCAR' else 'Formula One'
            p=product(sport=sibling);p['tags'].append(TAGS['Motorsport'])
            self.assertIsNone(relevance(interests,p))
            self.assertIsNone(relevance(interests,product(sport='Cricket')))
        self.assertIsNone(relevance({'V8 Supercars','Motorsport'},product(sport='Motorsport')))
        self.assertEqual(search_tags({'Formula One','Motorsport'})[0],TAGS['Formula One'])

    def test_multi_sport_and_unknown_classification(self):
        for sport in ('Basketball','Motorsport','Formula One'):
            self.assertEqual(relevance({'Basketball','Motorsport'},product(sport=sport) | {'tags':[TAGS[sport],TAGS['Motorsport']] if sport=='Formula One' else [TAGS[sport]]}),0)
        self.assertIsNone(relevance({'Cricket'},product(sport='NFL')))
        self.assertIsNone(relevance({'Cricket'},product(sport='Cricket') | {'tags':[]}))

    def test_legacy_interest_and_product_type_never_establish_authority(self):
        shop,store=wire();shop.products.return_value=[product(P)|{'tags':[]}]
        ctx=context();ctx['_customer']['tags']=['interest:Motorsport','SC_SPORT_MOTORSPORT','SC_HIST_MOTORSPORT']
        self.assertEqual(resolve(shop,store,doc_with(settings('Related Products',3,product_ids=[Q])),ctx,A,AT)['blocks'],{})

    def test_fresh_membership_works_for_no_purchase_without_claiming_ownership(self):
        shop,store=wire();shop.namespace='fixture';state=snapshot()
        for row in state['segments'].values():row['members']=[A] if row['name']=='Cricket Buyers' else []
        store.state.return_value=state
        cfg=settings('Related Products',3,product_ids=[P,Q]);ctx=context();ctx['_lifecycle_orders']=[];ctx['_order']={}
        shop.query.side_effect=lambda *args:{'nodes':[product(P,'Cricket'),product(Q,'NFL')]}
        rows=resolve(shop,store,doc_with(cfg),ctx,A,AT)['blocks'][marker(cfg)]
        self.assertEqual([r['id'] for r in rows],[P]);self.assertNotIn('owned',rows[0])

    def test_ranking_and_duplicate_blocks_do_not_repeat_products(self):
        shop,store=wire();shop.products.return_value=[product(P,'Formula One')]
        cfg=settings('Related Products',2,product_ids=[Q,'gid://shopify/Product/3'])
        shop.query.side_effect=lambda *args:{'nodes':[product(Q),product('gid://shopify/Product/3','Formula One')]}
        doc=doc_with(cfg)
        other=settings('Related Products',1,product_ids=[Q])
        doc['middle_sections'][0]['html']+=marker(other)+marker(cfg)
        doc['custom_html']=doc['middle_sections'][0]['html']
        facts=resolve(shop,store,doc,context(),A,AT)['blocks']
        self.assertEqual([r['id'] for r in facts[marker(cfg)]],['gid://shopify/Product/3',Q])
        self.assertEqual(facts[marker(other)],[])
        self.assertEqual(render(doc,facts)['custom_html'].count('<img'),2)

    def test_discovery_is_one_batch_and_availability_fresh(self):
        shop,store=wire();cfg=settings('Related Products',3)
        shop.query.side_effect=lambda query,args,*rest:({'s0':{'nodes':[{'id':Q}]}} if query==DISCOVERY else {'nodes':[product(Q)]})
        result=resolve(shop,store,doc_with(cfg),context(),A,AT)
        self.assertEqual(len(result['blocks'][marker(cfg)]),1)
        self.assertEqual(shop.products.call_count,1);self.assertEqual(shop.query.call_count,2)
        self.assertEqual(shop.query.call_args_list[0].args[-2:],(180,False))
        self.assertEqual(shop.query.call_args_list[1].args[-2:],(0,True))
        store.q.assert_not_called()

    def test_optional_failure_keeps_verified_purchased_cards(self):
        from crm_shopify import CapabilityUnavailable
        shop,store=wire();doc=document('win_back-1')
        def query(q,args,*rest):
            if q==ORDER:return {'order':order()}
            raise CapabilityUnavailable('fixture')
        shop.query.side_effect=query
        blocks=resolve(shop,store,doc,context(),A,AT,allocation_reader=lambda *a:None)['blocks']
        self.assertEqual(len(blocks),1);self.assertTrue(next(iter(blocks.values()))[0]['owned'])
        self.assertEqual(shop.products.call_count,1)  # reused for classification

    def test_wrong_history_identity_is_not_hidden_as_optional_failure(self):
        shop,store=wire();ctx=context();ctx['_lifecycle_orders']=[order(B)]
        with self.assertRaisesRegex(ValueError,'recipient mismatch'):
            resolve(shop,store,document('post_purchase-3'),ctx,A,AT)

    def test_short_budget_is_scoped_and_default_transport_unchanged(self):
        from crm_shopify import Shopify,CapabilityUnavailable
        from crm_collector_transport import bounded
        shop=Shopify(transport=lambda *a:{'ok':True},namespace='fixture')
        scoped=bounded(shop,seconds=-1)
        with self.assertRaises(CapabilityUnavailable):scoped.query('q',{},'fixture')
        self.assertEqual(shop.query('q',{},'fixture'),{'ok':True})
        self.assertFalse(hasattr(shop,'optional_deadline'))

    def test_optional_transport_retains_throttle_gate_with_one_short_attempt(self):
        from crm_shopify import Shopify,CapabilityUnavailable
        from crm_collector_transport import bounded
        response=Mock(status_code=429,headers={'Retry-After':'2'})
        response.json.return_value={}
        def request(*args,**kwargs):
            kwargs['request_post']('https://fixture.invalid/graphql',timeout=kwargs['timeout'])
            raise TimeoutError('synthetic throttle')
        with patch('crm_shopify._NEXT_REQUEST',0),patch('time.monotonic',return_value=100), \
             patch('shopify_sync.graphql_request',side_effect=request) as graphql, \
             patch('requests.post',return_value=response):
            shop=Shopify(namespace='fixture',sleeper=lambda _:None)
            with self.assertRaises(CapabilityUnavailable):bounded(shop).query('q',{},'fixture')
            self.assertEqual(graphql.call_count,1);self.assertEqual(graphql.call_args.kwargs['timeout'],3)
            graphql.reset_mock()
            with self.assertRaises(CapabilityUnavailable):shop.query('q',{},'fixture')
            self.assertEqual(graphql.call_count,3);self.assertEqual(graphql.call_args.kwargs['timeout'],20)

    def test_optional_transport_does_not_wait_indefinitely_for_shared_slot(self):
        from crm_shopify import Shopify,CapabilityUnavailable
        from crm_collector_transport import bounded
        with patch('crm_shopify._LIMIT') as limit:
            limit.acquire.return_value=False
            shop=Shopify(transport=Mock(),namespace='fixture')
            with self.assertRaises(CapabilityUnavailable):bounded(shop).query('q',{},'fixture')
            self.assertGreater(limit.acquire.call_args.kwargs['timeout'],0)
            shop.transport.assert_not_called();limit.release.assert_not_called()


class StageTests(unittest.TestCase):
    def test_ten_mappings_keep_original_timing_and_disabled_four(self):
        from crm_lifecycle_definition import expanded_flow
        from crm_lifecycle_runtime import locked
        self.assertTrue(locked({'config':{'draft':expanded_flow('welcome')}}))
        self.assertEqual(len(mapping()),10)
        for row in mapping():
            step=expanded_flow(row['trigger'])['emails'][row['email']-1]
            self.assertEqual((row['days']*86400,row['anchor'],row['enabled']),
                             (step['delay_seconds'],step['anchor'],step['enabled']))
        self.assertEqual(sum(len(library_rows(t)) for t in ('welcome','post_purchase','win_back')),9)

    def test_explicit_proposal_preserves_branding_rules_and_input_until_called(self):
        from crm_lifecycle_definition import expanded_flow
        from crm_campaign_content import validate_document
        for key,(trigger,n,*_) in STAGES.items():
            flow=expanded_flow(trigger);before=deepcopy(flow);doc=flow['emails'][n-1]['document']
            proposal=document(key);validate_document(proposal);self.assertEqual(flow,before)
            if key=='win_back-4':
                with self.assertRaises(ValueError):apply(doc,key)
                continue
            original=deepcopy(doc);apply(doc,key)
            self.assertEqual(doc.get('html_sections'),original.get('html_sections'))
            for field in ('market','audience','offer','smart_hours'):self.assertEqual(doc[field],original[field])
            self.assertEqual(len(doc['middle_sections']),1)
            self.assertNotIn('lifecycle-recommendations',json.dumps(doc['middle_sections']))
            if key=='post_purchase-2':self.assertIn('Once your certificate is available',doc['custom_html'])
            self.assertEqual(flow['emails'][n-1]['enabled'],before['emails'][n-1]['enabled'])


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable localhost PostgreSQL required')
class StageStorageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.test_crm_lifecycle_expansion import DatabaseTests
        DatabaseTests.setUpClass()

    def test_explicit_use_archives_previous_draft_and_rejects_conflict(self):
        from tests.crm_db_fixture import connect
        from tests.test_crm import ADMIN
        from tests.test_crm_send_flow import CFG
        from crm_automation_store import AutomationStore
        from crm_campaign_library import insert_saved_template
        from crm_collector_stages import PREFIX
        store=AutomationStore(connect)
        with patch.object(store,'render_settings',return_value=CFG):
            for trigger in ('welcome','post_purchase','win_back'):
                store.preview_trigger=trigger
                row=store.create(ADMIN,trigger,lifecycle=True)
                original=deepcopy(row['config']['draft']);proposed=deepcopy(original)
                for n,step in enumerate(proposed['emails'],1):
                    if trigger=='win_back' and n==4:continue
                    insert_saved_template(store,step['document'],PREFIX+f'{trigger}-{n}',2)
                saved=store.save_flow(ADMIN,row['id'],row['name'],proposed,row['config']['revision'])
                old=store.q('SELECT definition FROM crm_lifecycle_revisions WHERE automation_id=%s AND revision=%s',(row['id'],row['config']['revision']),True)
                self.assertEqual(old['definition'],original)
                self.assertEqual(store.flow(row['id'])['config']['draft'],proposed)
                self.assertEqual(saved['status'],'DRAFT');self.assertEqual(saved['steps'],row['steps'])
                self.assertEqual(saved['config']['published_version'],0)
                self.assertEqual(proposed['emails'][-1]['enabled'],original['emails'][-1]['enabled'])
                with self.assertRaisesRegex(ValueError,'newer draft'):
                    store.save_flow(ADMIN,row['id'],row['name'],original,row['config']['revision'])


if __name__=='__main__':unittest.main()
