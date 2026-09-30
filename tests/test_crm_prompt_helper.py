from copy import deepcopy
from datetime import datetime, timezone
import unittest
from unittest.mock import Mock
from crm_campaign_prompt import build,clean,fingerprint,PURPOSES,campaign_context
from crm_prompt_readers import PromptReader

NOW=datetime(2026,9,30,10,tzinfo=timezone.utc)
DOC={'market':'AU','market_audience':True,'send_timing':{'mode':'now'},'content':{'subject':'Keep','preheader':'Keep preview'},'counts':{'eligible':1085}}
PRODUCT={'id':'gid://shopify/Product/1','title':'Six Laps Ahead Peter Brock Wall Art'}

class Reader:
    def __init__(self,n=4):self.n=n
    def product(self,identity):return {'kind':'Single product','source':'Shopify public product','id':identity,'title':PRODUCT['title'],'url':'https://www.sportscaveshop.com/products/brock','sport_or_product_type':'Motorsport'}
    def availability(self,identity):return {'size':100,'remaining':self.n,'status':'Sold Out Archive' if self.n==0 else 'Final Editions' if self.n<=5 else 'Limited Edition','source':'Edition Ops read-only ledger'}
    def belongs(self,*args):return True

def inputs(purpose='General promotion / product spotlight',details=''):
    return {'kind':'Single product','target':PRODUCT,'purpose':purpose,'details':details,'edition_id':None}

class PromptTests(unittest.TestCase):
    def test_fixed_rules_public_projection_and_no_draft_mutation(self):
        doc=deepcopy(DOC);doc['customer_email']='private@example.test';original=deepcopy(doc)
        result=build(inputs(),doc,Reader(),NOW)
        self.assertEqual(doc,original)
        for text in ('BEGIN FIXED CHATGPT INSTRUCTIONS','QUALITY CHECK AND OUTPUT','at most 89','Preview text','Peter Brock'):
            self.assertIn(text,result['prompt'])
        self.assertNotIn('private@example.test',result['prompt']);self.assertNotIn('1085',result['prompt'])
        self.assertNotIn('{{',result['prompt'])
        self.assertEqual(len(PURPOSES),31)

    def test_manual_collection_projects_only_manual_context(self):
        data={**inputs(),'kind':'Collection','target':{'source':'manual','title':'Motorsport heroes','id':'stale','onlineStoreUrl':'https://wrong.test','description':'stale'}}
        result=build(data,DOC,Reader(),NOW)
        self.assertEqual(result['context']['target'],{'kind':'Collection','source':'manual','title':'Motorsport heroes'})
        self.assertNotIn('stale',result['prompt']);self.assertNotIn('wrong.test',result['prompt'])

    def test_changes_invalidate_fingerprint_and_market_counts_do_not_leak(self):
        original=inputs();value=fingerprint(original,DOC)
        for key,new in [('kind','Collection'),('purpose','Story behind the artwork'),('details','New angle'),('target',{'title':'Other'})]:
            self.assertNotEqual(value,fingerprint({**original,key:new},DOC))
        self.assertNotEqual(value,fingerprint(original,{**DOC,'market':'US'}))
        self.assertEqual(campaign_context({'market':'AU'}),{})

    def test_missing_offer_deadline_context_and_expired_offer(self):
        for purpose,details in [('Discount / sale',''),('Offer ending / last chance','20% off all frames'),('Sporting event / finals / race',''),('Other / custom',''),('VIP / early access',''),('Discount / sale','20% off all frames ends 2020-01-01 12:00 Australia/Sydney')]:
            with self.subTest(purpose=purpose),self.assertRaises(ValueError):build(inputs(purpose,details),DOC,Reader(),NOW)
        result=build(inputs('Offer ending / last chance','20% off all frames, automatic. Ends 2026-10-05 17:00 Australia/Sydney'),DOC,Reader(),NOW)
        self.assertTrue(result['sensitive']);self.assertIn('+11:00',result['expires'])

    def test_ledger_conflicts_sold_out_and_neutral_nonqualifying_stock(self):
        with self.assertRaisesRegex(ValueError,'conflicts'):build(inputs('Low edition stock','Only 3 remaining'),DOC,Reader(4),NOW)
        with self.assertRaisesRegex(ValueError,'Sold out'):build(inputs('Low edition stock'),DOC,Reader(0),NOW)
        unknown=Reader();unknown.availability=Mock(side_effect=ValueError('Cannot verify'))
        with self.assertRaises(ValueError):build(inputs('Low edition stock'),DOC,unknown,NOW)
        neutral=build(inputs('Low edition stock'),DOC,Reader(50),NOW)
        self.assertIn('Neutral precise',neutral['context']['target']['edition']['wording'])
        final=build(inputs('Final editions / retirement notice'),DOC,Reader(0),NOW)
        self.assertIn('Do not infer retirement',final['context']['target']['edition']['wording'])

    def test_collection_scarcity_requires_specific_member_not_collection_count(self):
        data={**inputs('Low edition stock'),'kind':'Collection','target':{'id':'gid://shopify/Collection/2','title':'Racing'}}
        with self.assertRaises(ValueError):build(data,DOC,Reader(),NOW)
        data['edition_id']=PRODUCT['id'];r=Reader();r.belongs=Mock(return_value=False)
        with self.assertRaises(ValueError):build(data,DOC,r,NOW)
        result=build(data,DOC,Reader(),NOW)
        self.assertEqual(result['context']['target']['edition']['edition_title'],PRODUCT['title'])

    def test_scheduled_deadline_uses_recipient_zone_conservatively(self):
        doc={**DOC,'send_timing':{'mode':'schedule','date':'2026-10-05','time':'18:00'}}
        with self.assertRaisesRegex(ValueError,'scheduled'):build(inputs('Offer ending / last chance','20% off all frames until 2026-10-05 17:00 Australia/Sydney'),doc,Reader(),NOW)

    def test_clean_html_and_small_context(self):
        self.assertEqual(clean('<b>Happy</b><script>steal()</script>'),'Happy')
        self.assertEqual(len(clean('x'*1000,100)),100)

    def test_readers_paginate_both_collection_types_and_use_exact_ledger_read(self):
        shop=Mock(namespace='fixture-pages');shop.query.side_effect=[
            {'collections':{'nodes':[{'id':'1','title':'Manual'}],'pageInfo':{'hasNextPage':True,'endCursor':'next'}}},
            {'collections':{'nodes':[{'id':'2','title':'Automated'}],'pageInfo':{'hasNextPage':False,'endCursor':'end'}}}]
        editions=Mock(return_value=[{**{'shopify_product_id':'1','product_title':'Brock','shopify_handle':'brock'}}])
        reader=PromptReader(shop,editions)
        first=reader.collections();second=reader.collections(after=first['cursor'])
        self.assertEqual(second['rows'][0]['title'],'Automated')
        self.assertEqual(shop.query.call_args.args[1]['after'],'next')
        self.assertNotIn('products(',shop.query.call_args.args[0])
        self.assertEqual(reader.products('Brock')['rows'][0]['id'],PRODUCT['id'])
        editions.assert_called_once_with(search='Brock',limit=9,offset=0)

if __name__=='__main__':unittest.main()
