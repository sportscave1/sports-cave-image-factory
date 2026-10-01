"""Offline Shopify membership / freshness contracts. Never sends or mutates Shopify."""
from copy import deepcopy
import unittest
from unittest.mock import Mock
from crm_campaign_segments import sources,count_snapshot,canonical_query,LABELS
from crm_campaign_markets import calculate
from crm_shopify import Shopify,CAMPAIGN_SUBSCRIBERS,CAMPAIGN_MEMBER_IDS,SEGMENTS
from crm_segment_counts import SegmentCounts,TTL,REVISION_INTERVAL
from crm_webhooks import receive_shopify
from crm_logic import now,recipient_hash
from tests.crm_fixtures import ShopifyFixture
from tests.test_crm_campaign_v2 import profile
from tests.test_crm_segment_performance import Queue

class MemoryStore:
    connect=None
    def __init__(self):self.values={};self.version=0;self.events=[];self.suppressed=set()
    def state(self,key):return deepcopy(self.values.get(key,{}))
    def set_state(self,key,value):self.values[key]=deepcopy(value)
    def invalidate(self):self.version+=1;self.set_state('cache_version',{'version':self.version})
    def webhook(self,*args):self.events.append(args);self.invalidate();return True
    def active_suppression_hashes(self):return self.suppressed,set()
    def recent_marketing_hashes(self,hours):return set()

class AudienceSyncTests(unittest.TestCase):
    def setUp(self):
        self.wire=ShopifyFixture(0);self.wire.customers=[profile(1),profile(2,'US'),profile(3,'GB')]
        self.wire.segments=[{'id':'gid://shopify/Segment/42','name':'Australia',
            'query':"customer_countries CONTAINS 'AU' OR customer_tags CONTAINS 'SC_COUNTRY_AU'",'lastEditDate':'2026-09-30T00:00:00Z'}]
        self.shop=Shopify(self.wire,namespace='sync-fixture');self.store=MemoryStore()
        self.clock=[0];self.queue=Queue();self.cache=SegmentCounts(clock=lambda:self.clock[0],executor=self.queue)
    def read(self):
        self.cache.display(self.shop,self.store)
        if self.queue.jobs:self.queue.run()
        return self.cache.display(self.shop,self.store)
    def event(self,topic='customers/update',payload=None):
        receive_shopify(self.store,topic,'fixture-'+str(self.store.version),payload or {'id':1},now())
        self.clock[0]+=REVISION_INTERVAL+1
        return self.read()['counts']
    def test_counts_are_one_batch_and_no_profiles_or_members(self):
        result=self.read()
        self.assertEqual(result['counts'],{'AU':1,'US':1,'UK':1,'Global':3,'CA':0,'NZ':0})
        self.assertEqual(len(self.wire.calls),2)
        self.assertEqual(self.wire.calls[0][0],SEGMENTS)
        self.assertIn('CrmCampaignCounts',self.wire.calls[1][0])
        self.assertNotIn('nodes',self.wire.calls[1][0])
        self.assertEqual(len({r['fetched_at'] for r in result['snapshot'].values()}),1)
        self.assertIsNotNone(result['revision'])
    def test_subscribe_and_unsubscribe_refresh_au_and_global_only(self):
        c=profile(4,consent='NOT_SUBSCRIBED');self.wire.customers.append(c)
        before=self.read()['counts']
        c['emailMarketingConsent']['marketingState']='SUBSCRIBED'
        after=self.event('customers_email_marketing_consent/update',{'customer_id':4})
        self.assertEqual(after,{**before,'AU':2,'Global':4})
        c['emailMarketingConsent']['marketingState']='NOT_SUBSCRIBED'
        self.assertEqual(self.event(),before)
    def test_tag_add_remove_with_no_address(self):
        c=profile(4,'');self.wire.customers.append(c);before=self.read()['counts']
        c['tags']=['SC_COUNTRY_AU'];self.assertEqual(self.event(),{**before,'AU':2})
        c['tags']=[];self.assertEqual(self.event(),before)
    def test_location_transfer_and_no_double_count(self):
        c=self.wire.customers[0];c['tags']=['SC_COUNTRY_AU']
        before=self.read()['counts'];self.assertEqual(before['AU'],1)
        c['tags']=[];c['defaultAddress']['countryCodeV2']='GB'
        self.assertEqual(self.event(),{**before,'AU':0,'UK':2})
    def test_all_fallback_tags(self):
        for i,code in enumerate(('AU','US','GB','CA','NZ'),10):
            c=profile(i,'');c['tags']=['SC_COUNTRY_'+code];self.wire.customers.append(c)
        self.assertEqual(self.read()['counts'],{'AU':2,'US':2,'UK':2,'Global':8,'CA':1,'NZ':1})
    def test_segment_query_change_and_rename_preserve_id(self):
        self.read();segment=self.wire.segments[0]
        segment.update(name='Renamed in Shopify',query="customer_countries CONTAINS 'GB'",lastEditDate='2026-09-30T01:00:00Z')
        self.wire.customers.append(profile(4,'GB'))
        counts=self.event('segments/update',{'id':42})
        self.assertEqual(counts['AU'],2)
        source=self.read()['snapshot']['AU']['source']
        self.assertEqual(source['id'],segment['id']);self.assertIn("'GB'",source['query'])
        self.assertEqual(self.store.events[-1][3],segment['id'])
    def test_deleted_linked_segment_fails_closed_retains_stale(self):
        before=self.read()['counts'];self.wire.segments=[]
        self.event('segments/delete',{'id':42})
        state=self.read();self.assertTrue(state['error']);self.assertEqual(state['counts'],before)
        with self.assertRaises(ValueError):calculate(self.shop,self.store,market='AU')
    def test_ttl_catches_missed_event_and_ui_interactions_reuse_cache(self):
        before=self.read()['counts']
        self.wire.customers.append(profile(4))
        for _ in range(20):self.assertEqual(self.read()['counts'],before)
        self.assertEqual(len(self.wire.calls),2)
        self.clock[0]=TTL+1;self.assertEqual(self.read()['counts']['AU'],2)
        self.assertEqual(len(self.wire.calls),4)
    def test_manual_refresh_bypasses_ttl(self):
        self.read();self.wire.customers.append(profile(4))
        self.cache.refresh(self.shop,self.store)
        self.assertEqual(self.read()['counts']['AU'],2)
    def test_partial_failure_does_not_mix_count_generations(self):
        before=self.read();self.wire.fail=RuntimeError('offline')
        self.clock[0]=TTL+1;after=self.read()
        self.assertEqual(before['snapshot'],after['snapshot']);self.assertTrue(after['error'])
    def test_pagination_above_2000_and_final_consent_suppression_dedupe(self):
        self.wire.customers=[profile(i) for i in range(1,2252)]
        self.wire.customers[-1]['email']=self.wire.customers[0]['email']
        self.store.suppressed={recipient_hash(self.wire.customers[1]['email'])}
        self.assertEqual(self.read()['counts']['AU'],2251)
        self.wire.calls=[]
        result=calculate(self.shop,self.store,market='AU')['AU']
        self.assertEqual(result['members'],2251);self.assertEqual(result['eligible'],2249)
        self.assertEqual(result['excluded'],{'local_suppression':1,'duplicate':1})
        self.assertEqual(sum(d==CAMPAIGN_MEMBER_IDS for d,v in self.wire.calls),10)
        self.assertEqual(sum(d==CAMPAIGN_SUBSCRIBERS for d,v in self.wire.calls),0)
        self.wire.customers[2]['emailMarketingConsent']['marketingState']='UNSUBSCRIBED'
        self.assertEqual(calculate(self.shop,self.store,market='AU')['AU']['eligible'],2248)
    def test_draft_count_is_not_a_source(self):
        from crm_campaign_content import new_document
        doc=new_document();doc['counts']={'members':1038,'eligible':1038}
        self.assertEqual(self.read()['counts']['AU'],1)
        self.assertEqual(doc['market'],'AU')
    def test_canonical_queries_always_require_subscription(self):
        for market in LABELS:self.assertIn("email_subscription_status = 'SUBSCRIBED'",canonical_query(market))
        self.assertIn('SC_COUNTRY_AU',canonical_query('AU'))
    def test_repeated_cursor_rejected(self):
        shop=Shopify(lambda d,v:{'customerSegmentMembers':{'edges':[],'pageInfo':{'hasNextPage':True,'endCursor':'same'},'totalCount':1}})
        with self.assertRaisesRegex(ValueError,'pagination'):shop.campaign_member_ids(canonical_query('AU'))
    def test_segment_catalog_is_fully_paginated(self):
        self.wire.segments=[{'id':f'gid://shopify/Segment/{100+i}','name':f'Other {i}',
            'query':canonical_query('Global'),'lastEditDate':None} for i in range(70)]+self.wire.segments
        self.assertEqual(sources(self.shop,self.store)['AU']['id'],'gid://shopify/Segment/42')
        self.assertEqual(sum(d==SEGMENTS for d,v in self.wire.calls),2)
    def test_update_during_batch_is_discarded_and_retried_without_failure_backoff(self):
        loader=Mock(side_effect=lambda *args:(self.store.invalidate(),count_snapshot(*args))[1])
        self.cache.loader=loader
        state=self.read();self.assertFalse(state['error']);self.assertEqual(state['counts'],{})
        self.cache.loader=count_snapshot
        self.assertEqual(self.read()['counts']['AU'],1)
    def test_ca_nz_are_valid_draft_markets_with_existing_safety_gates(self):
        from tests.test_crm_simple_editor import document
        from crm_campaign_content import validate_document
        from crm_campaign_markets import audience
        for market in ('CA','NZ'):
            doc=document();doc.update(market=market,market_audience=True,audience=audience(market))
            validate_document(doc)
            self.assertEqual(doc['market'],market)
    def test_subscribed_gate_survives_broad_saved_segment(self):
        self.wire.customers.append(profile(4,consent='UNSUBSCRIBED'))
        self.assertEqual(self.read()['counts']['AU'],1)
        self.assertEqual(calculate(self.shop,self.store,market='AU')['AU']['eligible'],1)

if __name__=='__main__':unittest.main()
