"""Offline Storefront transport plus actual disposable PostgreSQL persistence."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock
import os
import unittest
import uuid
from crm_smart_catalogue import hydrate,preview,enabled,QUERY,FALLBACK,MARKET_PRODUCTS,_CACHE
from crm_middle_sections import apply_event,middle_sections,validate_middle
from crm_campaign_content import render_campaign,settings
from crm_email_size import analyze_rendered_email,REPRESENTATIVE_UNSUBSCRIBE
from crm_campaign_dispatch import payload
from tests.test_crm_modular_catalogue import catalogue_doc,service
from tests.test_crm_resend_marketing import ENV


def fixture():
    cat=service()
    shop=Mock(namespace='smart-fixture-'+uuid.uuid4().hex)
    def query(q,v,*a):
        if 'Availability' in q:return {'nodes':[dict(id=i,tracksInventory=True,totalInventory=5) for i in v['ids']]}
        return {'nodes':[]}
    shop.query.side_effect=query
    def storefront(q,v):
        seed=int(v.get('product','gid://shopify/Product/1').rsplit('/',1)[-1])
        nodes=[dict(id=f'gid://shopify/Product/{i}',availableForSale=True,onlineStoreUrl='https://shop.example/products/art') for i in range(seed+1,seed+5)]
        return {'productRecommendations':nodes} if q==QUERY else {'products':{'nodes':nodes}}
    shop.storefront_query.side_effect=storefront
    store=Mock(connect=None);store.q.return_value=[]
    return cat,shop,store


class SmartTests(unittest.TestCase):
    def setUp(self):
        self.doc=catalogue_doc();self.section=self.doc['middle_sections'][-1]
        self.section['settings']['smart']=True
        self.cat,self.shop,self.store=fixture()
        self.customer={'id':'gid://shopify/Customer/1','defaultAddress':{'countryCodeV2':'AU'}}

    def resolve(self,seed=1,**kw):
        orders=kw.pop('orders',[{'lineItems':{'nodes':[{'product':{'id':f'gid://shopify/Product/{seed}'},'title':'Motorsport artwork'}]}}])
        return hydrate(self.doc,self.store,self.shop,self.customer,orders=orders,catalogue=self.cat,**kw)

    def test_per_recipient_three_exclusions_and_saved_document_untouched(self):
        original=deepcopy(self.doc);a=self.resolve(1);b=self.resolve(8)
        ids=lambda d:[p['id'] for p in d['middle_sections'][-1]['products']]
        self.assertEqual(ids(a),[f'gid://shopify/Product/{i}' for i in (2,3,4)])
        self.assertEqual(ids(b),[f'gid://shopify/Product/{i}' for i in (9,10,11)])
        self.assertEqual(self.doc,original);self.assertTrue(enabled(self.doc));self.assertFalse(enabled(a))
        self.assertNotEqual(render_campaign(a)['html'],render_campaign(b)['html'])

    def test_old_manual_defaults_and_strict_boolean_roundtrip(self):
        self.section['settings'].pop('smart');self.assertFalse(enabled(self.doc))
        self.assertIs(hydrate(self.doc,None,None,{}),self.doc)
        apply_event(self.doc,{'type':'settings','id':self.section['id'],'base':[s['id'] for s in middle_sections(self.doc)],'settings':{**self.section['settings'],'smart':True}})
        self.assertTrue(enabled(self.doc));validate_middle(self.doc['middle_sections'])
        self.doc['middle_sections'][-1]['settings']['smart']='true'
        with self.assertRaises(ValueError):validate_middle(self.doc['middle_sections'])

    def test_owned_unavailable_duplicate_and_sold_out_editions(self):
        self.shop.storefront_query.side_effect=lambda q,v:{'productRecommendations':[
            {'id':f'gid://shopify/Product/{i}','availableForSale':i!=5,'onlineStoreUrl':'https://shop.example/products/a'} for i in (1,2,2,3,4,5,6)]}
        self.shop.query.side_effect=lambda q,v,*a:{'nodes':[dict(id=i,tracksInventory=True,totalInventory=0 if i.endswith('/4') else 1) for i in v['ids']]}
        resolve=self.cat.resolve
        def products(*a,**kw):
            rows=resolve(*a,**kw)
            for p in rows:
                if p['id'].endswith('/3'):p['edition']['remaining']=0
            return rows
        self.cat.resolve=products
        ids=[p['id'] for p in self.resolve()['middle_sections'][-1]['products']]
        self.assertEqual(ids,['gid://shopify/Product/2','gid://shopify/Product/6'])

    def test_cache_and_api_failure_safe_local_fallback(self):
        self.resolve();self.resolve();self.assertEqual(self.shop.storefront_query.call_count,1)
        _CACHE.clear();self.shop.storefront_query.side_effect=RuntimeError('offline')
        self.store.q.return_value=[{'shopify_product_id':'9'},{'shopify_product_id':'10'}]
        self.assertEqual(len(self.resolve()['middle_sections'][-1]['products']),2)
        self.shop.query.side_effect=RuntimeError('offline')
        self.assertFalse(self.resolve()['middle_sections'][-1]['visible'])

    def test_checkout_seeds_require_same_customer(self):
        checkout={'customer':{'id':'other'},'lineItems':{'nodes':[{'product':{'id':'gid://shopify/Product/8'}}]}}
        self.resolve(orders=[],checkout=checkout)
        self.assertEqual(self.shop.storefront_query.call_args.args[0],FALLBACK)
        _CACHE.clear();checkout['customer']['id']=self.customer['id'];self.resolve(orders=[],checkout=checkout)
        self.assertEqual(self.shop.storefront_query.call_args.args[1]['product'],'gid://shopify/Product/8')

    def test_existing_checkout_visual_variant_string_and_fresh_delivery_facts(self):
        checkout={'customer':{'id':self.customer['id']},'products':[{'product_id':'8','variant':'Framed'}]}
        hydrate(self.doc,self.store,self.shop,self.customer,orders=[],checkout=checkout,catalogue=self.cat,fresh=True)
        self.assertEqual(self.shop.storefront_query.call_args.args[1]['product'],'gid://shopify/Product/8')
        availability=[c for c in self.shop.query.call_args_list if 'Availability' in c.args[0]][0]
        self.assertTrue(availability.args[-1])

    def test_session_visual_facts_survive_copy_edits_without_product_refetch(self):
        from unittest.mock import patch
        self.store.email_mode='automation';state={}
        self.cat.resolve=Mock(wraps=self.cat.resolve)
        orders=[{'lineItems':{'nodes':[{'product':{'id':'gid://shopify/Product/1'}}]}}]
        with patch('crm_smart_catalogue.Catalogue',return_value=self.cat):
            first=preview(state,self.store,self.shop,self.doc,customer=self.customer,orders=orders,revision='same')
            self.doc['middle_sections'][-1]['settings']['headline']='Edited heading'
            second=preview(state,self.store,self.shop,self.doc,customer=self.customer,orders=orders,revision='same')
        self.cat.resolve.assert_called_once()
        self.assertEqual(first['middle_sections'][-1]['products'],second['middle_sections'][-1]['products'])
        self.assertEqual(second['middle_sections'][-1]['settings']['headline'],'Edited heading')

    def test_campaign_cold_preview_uses_existing_background_pool_and_deduplicates(self):
        from threading import Event
        from unittest.mock import patch
        from crm_flow_preview import NoPreviewCustomer
        import crm_smart_catalogue as smart
        self.store.email_mode='campaign';state={};hold=Event();original=smart.hydrate
        orders=[{'lineItems':{'nodes':[{'product':{'id':'gid://shopify/Product/1'}}]}}]
        def load(*a,**kw):hold.wait(2);return original(*a,catalogue=self.cat,**kw)
        try:
            with patch.object(smart,'hydrate',side_effect=load) as work:
                for _ in range(2):
                    with self.assertRaises(NoPreviewCustomer):preview(state,self.store,self.shop,self.doc,customer=self.customer,orders=orders,revision='same')
                hold.set();next(iter(state['campaign_home_cache'].values()))[1].result(timeout=3)
                result=preview(state,self.store,self.shop,self.doc,customer=self.customer,orders=orders,revision='same')
                self.assertEqual(work.call_count,1);self.assertEqual(len(result['middle_sections'][-1]['products']),3)
        finally:hold.set()

    def test_preparation_batch_reuses_product_facts_without_caching_customer_authority(self):
        from unittest.mock import patch
        from crm_smart_catalogue import BatchFacts
        self.cat.resolve=Mock(wraps=self.cat.resolve)
        with patch('crm_smart_catalogue.Catalogue',return_value=self.cat):batch=BatchFacts(self.shop,None)
        ids=['gid://shopify/Product/2'];batch.resolve(ids,'AU',fresh=True);batch.resolve(ids,'AU',fresh=True)
        self.cat.resolve.assert_called_once()
        from crm_lifecycle_shopify import PRODUCT_AVAILABILITY
        for _ in range(2):batch.query(PRODUCT_AVAILABILITY,{'ids':ids},'smart catalogue availability',60,True)
        self.assertEqual(self.shop.query.call_count,1)
        for _ in range(2):batch.customer(self.customer['id'],fresh=True)
        self.assertEqual(self.shop.customer.call_count,2)

    def test_win_back_new_edition_constraint_is_not_relaxed_by_smart_mode(self):
        self.shop.query.side_effect=lambda q,v,*a:{'nodes':[dict(id=i,tracksInventory=False,
            createdAt='2026-02-01T00:00:00Z' if i.endswith('/2') else '2025-01-01T00:00:00Z') for i in v['ids']]}
        result=self.resolve(new_since='2026-01-01T00:00:00Z')
        self.assertEqual([p['id'] for p in result['middle_sections'][-1]['products']],['gid://shopify/Product/2'])

    def test_sport_and_athlete_ranking_does_not_mix_basketball_into_motorsport(self):
        original=self.cat.resolve
        def products(*a,**kw):
            rows=original(*a,**kw)
            titles={'2':'Michael Jordan Basketball','3':'Peter Brock Motorsport','4':'Motorsport artwork','5':'Related edition'}
            for p in rows:p['title']=titles[p['id'].rsplit('/',1)[-1]]
            return rows
        self.cat.resolve=products
        orders=[{'lineItems':{'nodes':[{'product':{'id':'gid://shopify/Product/1'},'title':'Peter Brock Motorsport'}]}}]
        result=self.resolve(orders=orders)
        self.assertEqual([p['id'] for p in result['middle_sections'][-1]['products']],[f'gid://shopify/Product/{i}' for i in (3,4,5)])

    def test_global_unknown_market_does_not_fabricate_australian_prices(self):
        self.doc['market']='Global';self.customer['defaultAddress']={}
        result=self.resolve()
        self.assertFalse(result['middle_sections'][-1]['visible']);self.shop.storefront_query.assert_not_called()

    def test_frozen_dispatch_does_not_share_recommendations_or_change_retry(self):
        a=render_campaign(self.resolve(1),settings(ENV),unsubscribe_url=REPRESENTATIVE_UNSUBSCRIBE,production=True)
        b=render_campaign(self.resolve(8),settings(ENV),unsubscribe_url=REPRESENTATIVE_UNSUBSCRIBE,production=True)
        cfg=SimpleNamespace(sender='Sports Cave <sender@example.test>',reply_to='support@example.test')
        ra={'address':'one@example.test','unsubscribe_url':'https://shop.example/unsubscribe/one','message':a}
        rb={'address':'two@example.test','unsubscribe_url':'https://shop.example/unsubscribe/two','message':b}
        self.assertNotEqual(payload(a,ra,cfg)['html'],payload(a,rb,cfg)['html'])
        self.assertEqual(payload(a,ra,cfg),payload(b,ra,cfg))
        self.assertEqual(analyze_rendered_email(a['html'],a['text'])['html_bytes'],len(a['html'].encode()))

    def test_unsupported_customer_market_never_uses_australian_price(self):
        self.customer['defaultAddress']['countryCodeV2']='DE'
        self.assertFalse(self.resolve()['middle_sections'][-1]['visible'])
        self.assertEqual(self.shop.storefront_query.call_args.args[1]['country'],'DE')
        original=self.shop.storefront_query.side_effect;_CACHE.clear()
        def wire(q,v):
            if q!=MARKET_PRODUCTS:return original(q,v)
            return {'nodes':[dict(id=i,availableForSale=True,onlineStoreUrl='https://shop.example/products/art',
                priceRange={'minVariantPrice':{'amount':'55.00','currencyCode':'EUR'}},
                compareAtPriceRange={'minVariantPrice':{'amount':'65.00','currencyCode':'EUR'}}) for i in v['ids']]}
        self.shop.storefront_query.side_effect=wire
        products=self.resolve()['middle_sections'][-1]['products']
        self.assertEqual(len(products),3)
        self.assertTrue(all(p['currency']=='EUR' and p['price']=='55.00' for p in products))


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class PersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.test_crm_lifecycle_publication import LifecyclePublicationTests
        LifecyclePublicationTests.setUpClass()

    def test_smart_and_manual_save_reopen_and_duplicate(self):
        from tests.crm_db_fixture import connect
        from crm_campaign_store import CampaignStore
        from tests.test_crm import ADMIN
        store=CampaignStore(connect);store.seed();doc=catalogue_doc()
        row=store.save(ADMIN,'Smart persistence fixture',doc)
        self.assertFalse(enabled(store.draft(row['id'])['document']))
        doc['middle_sections'][-1]['settings']['smart']=True
        row=store.save(ADMIN,'Smart persistence fixture',doc,row['id'],row['version'])
        saved=store.draft(row['id']);self.assertTrue(enabled(saved['document']))
        duplicate=store.save(ADMIN,'Smart duplicate fixture',saved['document'])
        self.assertEqual(store.draft(duplicate['id'])['document']['middle_sections'],doc['middle_sections'])

    def test_library_insertion_and_section_duplication_preserve_smart_setting(self):
        from tests.crm_db_fixture import connect
        from crm_campaign_store import CampaignStore
        from crm_campaign_library import insert_saved_template
        from tests.test_crm import ADMIN
        store=CampaignStore(connect);doc=catalogue_doc();doc['middle_sections'][-1]['settings']['smart']=True
        template=store.save_design(ADMIN,'Smart template fixture '+uuid.uuid4().hex,doc)
        target=catalogue_doc();insert_saved_template(store,target,template['id'],template['version'])
        section=next(s for s in target['middle_sections'] if s.get('type')=='catalogue' and s['settings'].get('smart'))
        apply_event(target,{'type':'duplicate','id':section['id'],'base':[s['id'] for s in middle_sections(target)]})
        self.assertEqual(sum(s.get('type')=='catalogue' and s['settings'].get('smart',False) for s in target['middle_sections']),2)
        self.assertEqual(section['products'],doc['middle_sections'][-1]['products'])

    def test_owned_history_does_not_drop_purchases_outside_recent_fifty(self):
        import json
        from tests.crm_db_fixture import connect
        from crm_campaign_store import CampaignStore
        from crm_smart_catalogue import history,lines
        store=CampaignStore(connect);cid='gid://shopify/Customer/'+str(uuid.uuid4().int%100000000000)
        rows=[{'id':str(uuid.uuid4().int%100000000000),'customer':cid,'raw':{'line_items':[{'product_id':i+1}]}} for i in range(55)]
        store.q("""INSERT INTO shopify_orders(shopify_order_id,shopify_customer_id,financial_status,created_at,raw_json)
            SELECT id,customer,'PAID',now(),raw FROM jsonb_to_recordset(%s::jsonb) AS x(id text,customer text,raw jsonb)""",(json.dumps(rows),))
        found={product['product_id'] for order in history(store,{'id':cid}) for product in lines(order)}
        self.assertEqual(found,set(range(1,56)))

    def test_actual_publication_worker_preserves_smart_binding(self):
        from tests.test_crm_lifecycle_publication import LifecyclePublicationTests
        from tests.test_crm import ADMIN
        case=LifecyclePublicationTests();case.setUp()
        try:
            row=case.expanded('post_purchase');flow=deepcopy(row['config']['draft'])
            doc=catalogue_doc();doc['middle_sections'][-1]['settings']['smart']=True
            flow['emails'][0]['document']=doc
            row=case.store.save_flow(ADMIN,row['id'],row['name'],flow,row['config']['revision'])
            case.job(row);case.run_job();live=case.state(row)
            self.assertEqual(live['status'],'ACTIVE')
            self.assertTrue(enabled(live['config']['published_flow']['emails'][0]['document']))
            versions=case.store.q("SELECT content FROM crm_template_versions WHERE content->>'automation_id'=%s",(str(row['id']),))
            self.assertTrue(any(enabled(v['content']['document']) for v in versions))
            self.assertEqual(case.store.q('SELECT count(*) AS n FROM crm_automation_enrollments WHERE automation_id=%s',(row['id'],),True)['n'],0)
        finally:case.doCleanups()

    def test_actual_campaign_preparation_and_batch_dispatch_freeze_each_recipient(self):
        from tests.test_crm_batch_dispatch import DispatchTests,dispatch
        from unittest.mock import patch
        import crm_smart_catalogue as smart
        case=DispatchTests();case.setUp();cat,shop,_=fixture()
        doc=catalogue_doc();doc['middle_sections'][-1]['settings']['smart']=True
        native_hydrate=smart.hydrate;native_histories=smart.histories
        def histories(store,ids):
            import json
            for index,cid in enumerate(ids):
                raw={'lineItems':{'nodes':[{'product':{'id':f'gid://shopify/Product/{1 if index==0 else 8}'}}]}}
                store.q("INSERT INTO shopify_orders(shopify_order_id,shopify_customer_id,financial_status,created_at,raw_json) VALUES(%s,%s,'PAID',now(),%s::jsonb)",(f'gid://shopify/Order/{uuid.uuid4().int%100000000000}',cid,json.dumps(raw)))
            return native_histories(store,ids)
        def hydrated(doc,store,authority,customer,**kw):
            kw.pop('catalogue',None)
            return native_hydrate(doc,store,shop,customer,catalogue=cat,**kw)
        try:
            with patch('tests.test_crm_batch_dispatch.document',return_value=deepcopy(doc)),patch.object(smart,'histories',side_effect=histories),patch.object(smart,'hydrate',side_effect=hydrated):
                identity=case.queue(2)
            shop.storefront_query.side_effect=AssertionError('Dispatch must use frozen content')
            from crm_resend_batch import BatchError
            from crm_logic import now
            from datetime import timedelta
            send_id=case.store.q('SELECT campaign_send_id FROM crm_campaigns WHERE id=%s',(identity,),True)['campaign_send_id']
            case.transport.errors[f'sports-cave/{send_id}/batch/0']=BatchError(429,120)
            self.assertTrue(dispatch(case.engine))
            state=case.states(identity)[0]['value'];state['retry_at']=(now()-timedelta(seconds=1)).isoformat()
            case.store.set_state(f'campaign-batch:{send_id}:0',state)
            self.assertTrue(dispatch(case.engine))
            self.assertEqual(case.transport.calls[0],case.transport.calls[1])
            messages=case.transport.calls[-1][1]
            self.assertEqual(len(messages),2)
            self.assertNotEqual(messages[0]['html'],messages[1]['html'])
            self.assertTrue(any('Artwork 2' in m['html'] for m in messages))
            self.assertTrue(any('Artwork 9' in m['html'] for m in messages))
            self.assertTrue(all(r['status']=='ACCEPTED' for r in case.sends(identity)))
            self.assertFalse(dispatch(case.engine))
        finally:case.tearDown();case.doCleanups()
