"""Offline exact-sport, edition authority and recipient rendering contracts."""
from copy import deepcopy
from unittest import TestCase
from unittest.mock import Mock, patch
import json
from pathlib import Path
from crm_catalogue import edition_for,edition_available,catalogue_html,validate_snapshot
from crm_smart_catalogue import hydrate,preview,MARKET_PRODUCTS,FALLBACK,BatchFacts
from crm_smart_candidates import MEMBERSHIPS,COLLECTION_PRODUCTS,SPORT_HANDLES,behaviour
from crm_middle_sections import validate_middle,middle_sections,apply_event
from tests.test_crm_modular_catalogue import catalogue_doc,service,edition,node


def pid(n):return f'gid://shopify/Product/{n}'


class MatchingTests(TestCase):
    def setUp(self):
        self.doc=catalogue_doc();self.cfg=self.doc['middle_sections'][-1]['settings'];self.cfg['smart']=True
        self.customer={'id':'gid://shopify/Customer/1','defaultAddress':{'countryCodeV2':'AU'}}
        self.handles=['v8-supercars-wall-art','nascar-wall-art','motogp-wall-art','formula-one-wall-art','nba','nfl-wall-art','ice-hockey-wall-art']
        self.collections={str(n):[pid(n*100+i) for i in range(18)] for n in range(1,8)}
        self.store=Mock(connect=None);self.store.q.return_value=[]
        self.shop=Mock(namespace=self.id());self.shop.query.side_effect=self.query
        self.shop.storefront_query.side_effect=self.regional
        self.cat=service();self.unavailable=set();self.missing=set()

    def query(self,q,v,*args):
        if q==MEMBERSHIPS:
            return {'nodes':[{'id':i,'collections':{'nodes':[
                {'id':'gid://shopify/Collection/999','handle':'motor-racing-wall-art'},
                {'id':'gid://shopify/Collection/998','handle':'gift-editions'},
                {'id':'gid://shopify/Collection/997','handle':'all-sports-wall-art'},
                {'id':'gid://shopify/Collection/'+str(int(i.rsplit('/',1)[-1])//100),
                 'handle':self.handles[int(i.rsplit('/',1)[-1])//100-1]}]}} for i in v['ids']]}
        if q==COLLECTION_PRODUCTS:
            return {'collection':{'products':{'nodes':[{'id':i} for i in self.collections[v['id'].rsplit('/',1)[-1]]]}}}
        raise AssertionError('Unexpected Shopify query')

    def regional(self,q,v):
        ids=v.get('ids',self.collections['1'])
        rows=[{'id':i,'availableForSale':i not in self.unavailable,'onlineStoreUrl':'https://shop.example/products/art',
               'priceRange':{'minVariantPrice':{'amount':'85','currencyCode':'AUD'}}} for i in ids if i not in self.missing]
        return {'nodes':rows} if q==MARKET_PRODUCTS else {'products':{'nodes':rows}}

    def resolve(self,owned=(100,),**kwargs):
        orders=[{'products':[{'product_id':i} for i in owned]}] if owned else []
        return hydrate(self.doc,self.store,self.shop,self.customer,orders=orders,catalogue=self.cat,**kwargs)

    def products(self,**kwargs):return self.resolve(**kwargs)['middle_sections'][-1]['products']

    def test_each_sport_stays_exact_and_parent_collections_never_queried(self):
        for n in range(1,8):
            with self.subTest(handle=self.handles[n-1]):
                rows=self.products(owned=(n*100,))
                self.assertEqual(len(rows),4)
                self.assertTrue(all(int(p['id'].rsplit('/',1)[-1])//100==n for p in rows))
        calls=[v for q,v,*_ in (c.args for c in self.shop.query.call_args_list) if q==COLLECTION_PRODUCTS]
        self.assertTrue(all(v['id'].rsplit('/',1)[-1] not in ('997','998','999') for v in calls))

    def test_every_audited_specific_sport_is_allowed_but_catchalls_are_not(self):
        audit=json.loads(Path('tests/fixtures/sport_taxonomy_shopify_2026_10_07.json').read_text())
        self.assertTrue(SPORT_HANDLES <= {c['handle'] for c in audit['collections']})
        self.assertNotIn('motor-racing-wall-art',SPORT_HANDLES)
        self.assertFalse(SPORT_HANDLES & {'all-sports-wall-art','gift-editions','best-selling-sports-art','popular','collector-series-art'})

    def test_multiple_collections_balance_and_all_orders_exclude_purchases(self):
        self.store.q.return_value=[{'shopify_customer_id':self.customer['id'],'raw_json':{'products':[{'product_id':101},{'product_id':500}]}}]
        rows=self.products()
        self.assertEqual([p['id'] for p in rows],[pid(102),pid(501),pid(103),pid(502)])

    def test_quantity_1_4_8_12_and_legacy_4(self):
        self.cfg.pop('smart_count',None)
        self.assertEqual(len(self.products()),4)
        self.assertEqual(middle_sections(self.doc)[-1]['settings'].get('smart_count',4),4)
        self.assertNotIn('smart_count',self.cfg)  # Reading a legacy draft does not migrate it.
        for count in (1,4,8,12):
            self.cfg['smart_count']=count;validate_middle(self.doc['middle_sections'])
            rows=self.products();self.assertEqual(len(rows),count);self.assertEqual(len({p['id'] for p in rows}),count)
        for count in (0,13,True,'4',4.5):
            self.cfg['smart_count']=count
            with self.assertRaises(ValueError):validate_middle(self.doc['middle_sections'])

    def test_fewer_eligible_never_fill_with_another_sport_and_zero_hides(self):
        self.cfg['smart_count']=12;self.collections['1']=[pid(100),pid(101),pid(101)]
        self.assertEqual([p['id'] for p in self.products()],[pid(101)])
        self.unavailable={pid(101)}
        self.assertFalse(self.resolve(fresh=True)['middle_sections'][-1]['visible'])
        self.assertTrue(self.doc['middle_sections'][-1]['visible'])

    def test_generic_only_or_deleted_purchase_does_not_allow_global_fallback(self):
        self.shop.query.side_effect=lambda *a:{'nodes':[{'id':pid(100),'collections':{'nodes':[{'id':'999','handle':'motor-racing-wall-art'}]}}]}
        self.assertEqual(self.products(),[]);self.shop.storefront_query.assert_not_called()
        self.customer['numberOfOrders']='2'
        self.assertEqual(self.products(owned=()),[])

    def test_viewed_products_then_their_collections_before_cart(self):
        data={'customer_id':self.customer['id'],'viewed':[pid(103)],'checkout':[pid(501)]}
        rows=self.products(owned=(),behaviour_data=data)
        self.assertEqual(rows[0]['id'],pid(103))
        self.assertTrue(all(p['id'] in self.collections['1'] for p in rows))
        self.collections['1']=[pid(103)]
        rows=self.products(owned=(),behaviour_data=data,fresh=True)
        self.assertEqual([p['id'] for p in rows][:2],[pid(103),pid(501)])

    def test_purchase_restriction_wins_over_views_from_another_sport(self):
        rows=self.products(behaviour_data={'customer_id':self.customer['id'],'viewed':[pid(501)]})
        self.assertTrue(all(p['id'] in self.collections['1'] for p in rows))

    def test_no_signals_use_sales_ranked_products_and_never_random_index(self):
        rows=self.products(owned=())
        self.assertEqual(len(rows),4)
        self.assertEqual(self.shop.storefront_query.call_args_list[0].args[0],FALLBACK)
        reader=self.cat.edition_reader
        self.cat.edition_reader=lambda **kw:[{**r,'sold_count':0,'remaining_count':100,'next_edition_number':1} for r in reader(**kw)]
        self.assertEqual(self.products(owned=(),fresh=True),[])

    def test_sales_ranking_with_merchandising_tie_order(self):
        reader=self.cat.edition_reader
        def editions(**kw):
            rows=reader(**kw)
            for r in rows:
                if r['shopify_product_id']=='104':r.update(sold_count=90,remaining_count=10,next_edition_number=91)
            return rows
        self.cat.edition_reader=editions
        self.assertEqual([p['id'] for p in self.products()],[pid(104),pid(101),pid(102),pid(103)])

    def test_market_filter_applies_to_named_countries_and_missing_products(self):
        self.unavailable={pid(101)};self.missing={pid(102)}
        self.assertEqual(self.products()[0]['id'],pid(103))
        self.assertEqual(self.shop.storefront_query.call_args.args[1]['country'],'AU')

    def test_popular_pagination_skips_exhausted_first_page(self):
        original=self.regional
        def pages(q,v):
            if q!=FALLBACK:return original(q,v)
            if not v.get('after'):return {'products':{'nodes':[{'id':pid(100),'availableForSale':False}],
                'pageInfo':{'hasNextPage':True,'endCursor':'page2'}}}
            return original(q,v)
        self.shop.storefront_query.side_effect=pages
        self.assertEqual(len(self.products(owned=())),4)
        self.assertEqual(sum(c.args[0]==FALLBACK for c in self.shop.storefront_query.call_args_list),2)

    def test_memberships_paginate_past_generic_collections(self):
        original=self.query
        def pages(q,v,*args):
            if q==MEMBERSHIPS:return {'nodes':[{'id':pid(100),'collections':{
                'nodes':[{'id':'parent','handle':'motor-racing-wall-art'}],
                'pageInfo':{'hasNextPage':True,'endCursor':'next'}}}]}
            if 'CrmCollections' in q:return {'product':{'collections':{'nodes':[
                {'id':'gid://shopify/Collection/1','handle':'v8-supercars-wall-art'}]}}}
            return original(q,v,*args)
        self.shop.query.side_effect=pages
        self.assertEqual(len(self.products()),4)

    def test_draft_and_unpublished_products_are_excluded(self):
        original=self.cat.resolve
        def products(*a,**kw):
            rows=original(*a,**kw)
            for p in rows:
                if p['id']==pid(101):p['status']='DRAFT'
                if p['id']==pid(102):p['url']=''
            return rows
        self.cat.resolve=products
        self.assertEqual(self.products()[0]['id'],pid(103))

    def test_preview_customer_and_count_changes_invalidate_but_copy_edits_do_not(self):
        self.store.email_mode='automation';state={}
        with patch('crm_smart_catalogue.Catalogue',return_value=self.cat):
            a=preview(state,self.store,self.shop,self.doc,customer=self.customer,orders=[{'products':[{'product_id':100}]}])
            self.cfg['smart_count']=8
            b=preview(state,self.store,self.shop,self.doc,customer=self.customer,orders=[{'products':[{'product_id':100}]}])
            c=preview(state,self.store,self.shop,self.doc,customer={**self.customer,'id':'gid://shopify/Customer/2'},orders=[{'products':[{'product_id':500}]}])
        self.assertEqual(len(a['middle_sections'][-1]['products']),4)
        self.assertEqual(len(b['middle_sections'][-1]['products']),8)
        self.assertEqual(c['middle_sections'][-1]['products'][0]['id'],pid(501))

    def test_batch_storefront_and_overlapping_product_facts_reused(self):
        with patch('crm_smart_catalogue.Catalogue',return_value=self.cat):batch=BatchFacts(self.shop,None)
        batch.storefront_query(MARKET_PRODUCTS,{'ids':[pid(101)],'country':'AU'})
        batch.storefront_query(MARKET_PRODUCTS,{'ids':[pid(101)],'country':'AU'})
        self.shop.storefront_query.assert_called_once()
        self.cat.resolve=Mock(wraps=self.cat.resolve)
        batch.resolve([pid(101),pid(102)],'AU');batch.resolve([pid(102),pid(103)],'AU')
        self.assertEqual(self.cat.resolve.call_args.args[0],[pid(103)])

    def test_all_five_flow_renderers_bind_actual_recipient_and_quantity(self):
        from crm_automation_runtime import render
        from tests.test_crm_send_flow import LIVE,CFG
        import uuid
        self.doc['copy_reviewed']=True
        for count in (1,4,8,12):
            self.cfg['smart_count']=count
            resolved=self.resolve()
            context={'_smart_document':resolved,'_smart_recipient':self.customer['id']}
            row={'id':str(uuid.uuid4()),'shopify_customer_id':self.customer['id']}
            for kind in ('welcome','post_purchase','fulfilled','win_back','abandoned'):
                with self.subTest(kind=kind,count=count),patch.dict('os.environ',LIVE):
                    content={'document':self.doc,'trigger':kind,'render_settings':CFG}
                    message=render(content,row,'https://example.test/unsubscribe/fixture',context)
                    for i in range(101,101+count):self.assertIn('Artwork '+str(i),message['html'])
                    self.assertNotIn('Artwork '+str(101+count),message['html'])
                    with self.assertRaisesRegex(ValueError,'Recipient Smart'):
                        render(content,{**row,'shopify_customer_id':'other'},'https://example.test/unsubscribe/fixture',context)


class EditionTests(TestCase):
    def setUp(self):self.p=service().resolve([pid(1)])[0]

    def test_authoritative_next_remaining_and_unknown_hidden(self):
        row={**edition(),'next_edition_number':28,'sold_count':27,'remaining_count':73}
        ed=edition_for(self.p,[row]);self.assertEqual((ed['next'],ed['remaining']),(28,73))
        for remaining in (None,100):
            self.p['edition']=edition_for(self.p,[{**row,'remaining_count':remaining}])
            validate_snapshot(self.p)
            section=catalogue_doc()['middle_sections'][-1];section['products']=[self.p]
            html=catalogue_html(section)
            self.assertIn('#028 / 100',html);self.assertNotIn('100 REMAINING',html);self.assertNotIn('SOLD OUT',html)

    def test_status_capacity_and_mirror_conflicts_fail_closed(self):
        for update in ({'run_status':'closed'},{'sold_out':True},{'allocation_blocked':True},
                       {'active':False},{'remaining_count':0},{'next_edition_number':101},
                       {'sold_count':101},{'remaining_count':-1},{'run_next_edition_number':0}):
            self.assertFalse(edition_available(edition_for(self.p,[{**edition(),**update}])))
        self.assertIsNone(edition_for(self.p,[edition()],[{'key':'edition_next_number','value':'28'}]))
        self.assertFalse(edition_available(edition_for(self.p,[edition()],[{'key':'edition_status','value':'sold_out'}])))

    def test_cursor_never_used_as_sales_or_remaining(self):
        ed=edition_for(self.p,[{**edition(),'next_edition_number':52,'sold_count':2,'remaining_count':98}])
        self.assertEqual(ed['next'],52);self.assertEqual(ed['sold'],2);self.assertIsNone(ed['remaining'])

    def test_real_metafield_shape_checked_against_edition_ops(self):
        fields=[{'key':k,'value':str(v)} for k,v in {'edition_total':100,'edition_next_number':37,
            'edition_sold_count':36,'edition_remaining':64,'edition_status':'limited_release','edition_enabled':'true'}.items()]
        self.assertEqual(edition_for(self.p,[edition()],fields)['remaining'],64)

    def test_batched_metafield_reads_and_missing_product_do_not_drop_valid_cards(self):
        cat=service();original=cat.shop.query.side_effect
        def query(q,v,*args):
            result=original(q,v,*args)
            result['nodes']=[p for p in result['nodes'] if p['id']!=pid(2)]
            return result
        cat.shop.query.side_effect=query
        rows=cat.resolve([pid(i) for i in range(1,51)],allow_missing=True)
        self.assertEqual(len(rows),49)
        self.assertTrue(all(len(c.args[1]['ids'])<=20 for c in cat.shop.query.call_args_list))
        with self.assertRaises(ValueError):cat.resolve([pid(1),pid(2)])  # Manual validation is unchanged.

