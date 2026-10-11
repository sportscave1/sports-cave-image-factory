"""V8 audience contracts. Synthetic profiles and Shopify; no live writes."""
import copy
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from pathlib import Path
from crm_buyer_segments import (BUYER_NAMES, audience, member_ids, selected_definitions,
    definitions, synchronize, validate_ids, dispatch_exclusions)
from crm_campaign_content import new_document, validate_document
from crm_campaign_audience_prepare import fingerprint
from crm_logic import recipient_hash
from tests.test_crm_campaign_v2 import profile, authority

S1='gid://shopify/Segment/101'
S2='gid://shopify/Segment/102'

def fixture(market='Global', selected=None):
    rows=[profile(1),profile(2,'US'),profile(3),profile(4,consent='UNSUBSCRIBED'),profile(5)]
    rows[2]['email']=rows[0]['email'].upper()
    shop=authority(rows)
    catalogue={S1:{'id':S1,'name':'Cricket Buyers','query':"customer_tags CONTAINS 'cricket'"},
               S2:{'id':S2,'name':'Motorsport Buyers','query':"customer_tags CONTAINS 'motor'"}}
    shop.segment.side_effect=lambda identity,**kw:catalogue.get(identity)
    store=Mock();store.state.return_value={}
    store.active_suppression_hashes.return_value=({recipient_hash(rows[4]['email'])},set())
    store.recent_marketing_hashes.return_value=set()
    doc=new_document();doc.update(market=market,market_audience=True,shopify_segment_ids=[S1,S2] if selected is None else selected,shopify_segment_store='fixture')
    def ids(query):
        eligible=rows
        if "'AU'" in query:eligible=[r for r in rows if r['defaultAddress']['countryCodeV2']=='AU']
        if "'US'" in query:eligible=[r for r in rows if r['defaultAddress']['countryCodeV2']=='US']
        if "'cricket'" in query and "'motor'" not in query:eligible=[r for r in eligible if r['id'].endswith(('/1','/3'))]
        return {r['id'] for r in eligible}
    shop.campaign_member_ids.side_effect=ids
    return shop,store,doc,rows,catalogue


class BuyerContracts(unittest.TestCase):
    def test_observed_all_28_actual_ids_and_queries(self):
        data=json.loads(Path('docs/shopify-buyer-segments-observed.json').read_text())
        rows={r['name']:r for r in data['nodes']}
        self.assertEqual(len(BUYER_NAMES),28)
        for name in BUYER_NAMES:
            self.assertIn(name,rows);validate_ids([rows[name]['id']])
            self.assertIn('products_purchased',rows[name]['query'])
        self.assertFalse(data['pageInfo']['hasNextPage'])

    def test_location_and_parenthesized_union(self):
        shop,store,doc,_,_=fixture('US')
        result=member_ids(shop,store,doc)
        self.assertEqual(result,{'gid://shopify/Customer/2'})
        query=shop.campaign_member_ids.call_args.args[0]
        self.assertIn("AND ((customer_tags CONTAINS 'cricket') OR (customer_tags CONTAINS 'motor'))",query)
        self.assertIn("'US'",query)

    def test_no_segments_means_no_interest_restriction(self):
        shop,store,doc,rows,_=fixture(selected=[])
        self.assertEqual(len(member_ids(shop,store,doc)),len(rows))
        shop.segment.assert_not_called()

    def test_australia_cricket_and_overlapping_emails(self):
        shop,store,doc,_,_=fixture('AU',[S1])
        result=audience(shop,store,doc)
        self.assertEqual((result['members'],result['eligible']),(2,1))
        self.assertEqual(result['excluded'],{'duplicate':1})

    def test_union_consent_suppression_and_dedup(self):
        shop,store,doc,_,_=fixture()
        result=audience(shop,store,doc)
        self.assertEqual((result['members'],result['eligible']),(5,2))
        self.assertEqual(sum(result['excluded'].values()),3)
        self.assertEqual(len({r['hash'] for r in result['recipients']}),2)

    def test_deleted_segment_never_broadens(self):
        shop,store,doc,_,catalogue=fixture();del catalogue[S1]
        with self.assertRaisesRegex(ValueError,'unavailable'):member_ids(shop,store,doc)
        shop.campaign_member_ids.assert_not_called()
        self.assertEqual(doc['shopify_segment_ids'],[S1,S2])

    def test_rename_keeps_identity(self):
        shop,store,doc,_,catalogue=fixture();catalogue[S1]['name']='Renamed Cricket'
        self.assertEqual(selected_definitions(shop,doc)[0]['id'],S1)

    def test_other_store_rejected(self):
        shop,store,doc,_,_=fixture();doc['shopify_segment_store']='other'
        with self.assertRaisesRegex(ValueError,'store differs'):member_ids(shop,store,doc)
        shop.segment.assert_not_called()

    def test_outage_propagates_not_empty_success(self):
        shop,store,doc,_,_=fixture();shop.campaign_member_ids.side_effect=TimeoutError()
        with self.assertRaises(TimeoutError):audience(shop,store,doc)

    def test_saved_ids_validate_and_affect_preparation(self):
        shop,_,doc,_,_=fixture();validate_document(doc)
        restored=json.loads(json.dumps(doc));self.assertEqual(restored,doc)
        with patch('crm_resend_marketing.get_resend_marketing_config_status',return_value={}):
            before=fingerprint(shop,doc);restored['shopify_segment_ids']=[S1]
            self.assertNotEqual(fingerprint(shop,restored),before)
        legacy=new_document();validate_document(legacy);self.assertEqual(legacy['market'],'AU')
        for invalid in ([S1,S1],['invented'],[{}],S1):
            with self.assertRaises(ValueError):validate_ids(invalid)

    def test_pagination_failure(self):
        shop=Mock();shop.segments.return_value={'nodes':[],'pageInfo':{'hasNextPage':True,'endCursor':'stuck'}}
        with self.assertRaisesRegex(ValueError,'advance'):definitions(shop)

    def test_dispatch_fresh_membership_and_consent_remove_only(self):
        shop,store,doc,rows,_=fixture()
        engine=SimpleNamespace(shop=shop,store=store)
        recipients=[{'id':r['id'],'hash':recipient_hash(r['email'])} for r in (rows[0],rows[1],rows[3],rows[4])]
        shop.campaign_member_ids.return_value={rows[0]['id']};shop.campaign_member_ids.side_effect=None
        blocked=dispatch_exclusions(engine,doc,recipients)
        self.assertEqual(blocked,{r['hash'] for r in recipients[1:]})
        shop.segment.side_effect=TimeoutError()
        with self.assertRaises(TimeoutError):dispatch_exclusions(engine,doc,recipients)


class ProjectionTests(unittest.TestCase):
    def connection(self, previous=None, locked=True):
        conn=Mock()
        def execute(sql,args):
            cur=Mock()
            if 'pg_try' in sql:cur.fetchone.return_value={'locked':locked}
            elif sql.startswith('SELECT value'):cur.fetchone.return_value={'value':previous} if previous else None
            return cur
        conn.execute.side_effect=execute
        store=Mock();store.db.return_value.__enter__=Mock(return_value=conn);store.db.return_value.__exit__=Mock(return_value=False)
        store.state.return_value=previous or {}
        return conn,store

    def test_atomic_sync_exact_definitions_id_projection_and_cache(self):
        from contextlib import nullcontext
        conn=Mock();previous={}
        def execute(sql,args):
            cur=Mock();cur.fetchone.return_value={'locked':True} if 'pg_try' in sql else ({'value':previous} if previous else None)
            if sql.startswith('INSERT'):previous.update(json.loads(args[1]))
            return cur
        conn.execute.side_effect=execute
        store=Mock();store.db.side_effect=lambda:nullcontext(conn)
        shop=Mock(namespace='fixture');shop.segments.return_value={'nodes':[{'id':S1,'name':'Cricket Buyers','query':'saved exact query'}],'pageInfo':{}}
        shop.campaign_member_ids.return_value={'gid://shopify/Customer/1'}
        first=synchronize(shop,store);second=synchronize(shop,store)
        self.assertEqual(first,second);shop.campaign_member_ids.assert_called_once_with('saved exact query')
        self.assertEqual(first['segments'][S1]['members'],['gid://shopify/Customer/1'])
        self.assertEqual(len(first['missing']),27)
        self.assertNotIn('email',json.dumps(first))

    def test_failure_does_not_replace_good_snapshot(self):
        from contextlib import nullcontext
        previous={'timestamp':0,'bindings':{'Cricket Buyers':S1},'segments':{S1:{'name':'Old'}}}
        conn=Mock();conn.execute.return_value.fetchone.side_effect=[{'locked':True},{'value':previous}]
        store=Mock();store.db.side_effect=lambda:nullcontext(conn)
        shop=Mock(namespace='fixture');shop.segments.side_effect=TimeoutError('throttled')
        with self.assertRaises(TimeoutError):synchronize(shop,store)
        self.assertFalse(any(c.args[0].startswith('INSERT') for c in conn.execute.call_args_list))


if __name__=='__main__':unittest.main()
