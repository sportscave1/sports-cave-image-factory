"""Local fixtures only: no Shopify, database or email delivery credentials."""
from copy import deepcopy
from datetime import datetime,timezone,timedelta
import json
import os
import unittest
from unittest.mock import Mock,patch

from crm_collector_images import settings,marker,configurations,purchased,render,ACCOUNT
from crm_collector_templates import document,DESIGNS,source
from crm_collector_resolver import resolve,PRODUCTS,ORDER,BESTSELLERS,owned_ids

AT=datetime(2026,10,11,tzinfo=timezone.utc)
A='gid://shopify/Customer/101';B='gid://shopify/Customer/202'
P='gid://shopify/Product/1';Q='gid://shopify/Product/2'
O='gid://shopify/Order/10'
IMAGE='https://cdn.shopify.com/fixture-artwork.jpg'


def order(owner=A):
    return dict(id=O,customer={'id':owner},fullyPaid=True,displayFinancialStatus='PAID',
        lineItems={'nodes':[dict(id='gid://shopify/LineItem/1',title='Fixture collector artwork',variantTitle='Large black frame',product={'id':P})],
                   'pageInfo':{'hasNextPage':False}})


def product(pid=Q,sport='Motorsport',**kwargs):
    return dict(id=pid,title='Fixture '+pid.rsplit('/',1)[-1],status='ACTIVE',publishedInContext=True,
        onlineStoreUrl='https://www.sportscaveshop.com/products/fixture-'+pid.rsplit('/',1)[-1],
        createdAt=AT.isoformat(),productType=sport,tags=[__import__('product_sport_tags').TAGS[sport]],featuredImage={'url':IMAGE},
        variants={'nodes':[{'inventoryPolicy':'DENY','sellableOnlineQuantity':1,'inventoryItem':{'tracked':True}}]},**kwargs)


def doc_with(config):
    doc=document('build-collection')
    doc['middle_sections'][0]['html']=marker(config);doc['custom_html']=marker(config)
    return doc


def wire(products=None,source=None):
    shop=Mock();store=Mock();store.connect=None
    shop.products.return_value=[product(P)]
    shop.query.side_effect=lambda query,args,*rest:({'order':deepcopy(source or order())} if query==ORDER else
      {'collection':{'id':args['id'],'products':{'nodes':[{'id':Q}]}}} if query==BESTSELLERS else {'nodes':deepcopy(products if products is not None else [product()])})
    store.q.return_value=[{'shopify_product_id':Q}]
    return shop,store


def context(source=None):
    return {'_customer':{'id':A,'tags':[],'defaultAddress':{'countryCodeV2':'AU'}},
            '_order':source or order(),'_lifecycle_orders':[source or order()]}


class CollectorTests(unittest.TestCase):
    def test_four_templates_use_existing_contract_and_have_no_added_branding(self):
        from crm_campaign_content import validate_document,render_campaign
        from tests.test_crm_send_flow import CFG
        for key in DESIGNS:
            doc=document(key);before=deepcopy(doc)
            validate_document(doc)
            output=render_campaign(doc,CFG)
            self.assertEqual(before,doc)
            self.assertIn('Sample preview',output['html'])
            self.assertNotIn('SC_COLLECTOR_IMAGE',output['html'])
            self.assertNotIn('<script',output['html'])
            self.assertNotIn('<header',source(key))
            self.assertNotIn('hand-signed',source(key))
            self.assertLess(len(output['html'].encode()),95000)

    def test_account_invitation_never_asserts_certificate_is_ready(self):
        html=source('collected-artwork')
        self.assertIn(ACCOUNT,html)
        self.assertIn('View My Collection',html)
        self.assertIn('Once your certificate is available',html)
        self.assertNotIn('.pdf',html)
        self.assertNotIn('download',html.lower())

    def test_render_is_copy_only_and_caps_ownership_at_two(self):
        cfg=settings('Actual Purchased Product',3);doc=doc_with(cfg);before=deepcopy(doc)
        facts={marker(cfg):[{'title':'Fixture '+str(i),'image':IMAGE,'owned':True} for i in range(4)]}
        output=render(doc,facts)['custom_html']
        self.assertEqual(doc,before);self.assertEqual(output.count('<img'),2)
        self.assertNotIn('Fixture 2',output);self.assertIn('height:auto',output)
        self.assertNotIn('object-fit:cover',output)

    def test_variant_exact_product_only(self):
        o=order();o['lineItems']['nodes'][0]['variant']={'product':{'id':P},'image':{'url':'https://cdn.shopify.com/variant.webp'}}
        result=purchased(o,A,[product(P)],allocation_reader=lambda *a:'#009/50')
        self.assertIn('variant.webp?format=png',result[0]['image']);self.assertEqual(result[0]['edition'],'#009/50')
        o['lineItems']['nodes'][0]['variant']['product']['id']=Q
        self.assertEqual(purchased(o,A,[product(P)])[0]['image'],IMAGE)

    def test_missing_image_and_edition_omit_only_optional_fields(self):
        result=purchased(order(),A,[],allocation_reader=lambda *a:None)
        self.assertEqual(result[0]['title'],'Fixture collector artwork')
        self.assertEqual(result[0]['image'],'');self.assertIsNone(result[0]['edition'])

    def test_wrong_customer_order_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'recipient mismatch'):purchased(order(B),A,[product(P)])
        with self.assertRaisesRegex(ValueError,'identity'):purchased(order(),'',[product(P)])

    def test_cancelled_refunded_partially_refunded_orders_never_render_owned_art(self):
        for state in ('REFUNDED','PARTIALLY_REFUNDED','VOIDED'):
            o=order();o['displayFinancialStatus']=state
            self.assertEqual(purchased(o,A,[product(P)]),[])
        o=order();o['cancelledAt']=AT.isoformat();self.assertEqual(purchased(o,A,[product(P)]),[])

    def test_settings_survive_json_duplicate_edit_and_reload(self):
        from crm_middle_sections import apply_event
        cfg=settings('Related Products',3,product_ids=[Q]);doc=doc_with(cfg)
        reloaded=json.loads(json.dumps(doc))
        apply_event(reloaded,{'type':'duplicate','base':['collector-body'],'id':'collector-body','new_id':'copy'})
        self.assertEqual(configurations(reloaded),[cfg,cfg])
        self.assertEqual(configurations(doc),[cfg])

    def test_static_and_dynamic_blocks_coexist(self):
        dynamic=settings('Related Products',1)
        static=settings('Static Selected Image',image=IMAGE,alt='Fixture static artwork')
        doc=doc_with(dynamic);doc['custom_html']+=marker(static);doc['middle_sections'][0]['html']=doc['custom_html']
        rendered=render(doc,{marker(dynamic):[{'title':'Dynamic fixture','image':IMAGE}]})['custom_html']
        self.assertEqual(rendered.count('<img'),2);self.assertIn('Fixture static artwork',rendered)

    def test_invalid_and_temporary_images_and_broken_markers_rejected(self):
        for image in ('http://example.test/a.jpg','https://cdn.shopify.com/a.jpg?expires=123','javascript:alert(1)'):
            with self.assertRaises(ValueError):settings('Static Selected Image',image=image,alt='fixture')
        doc=doc_with(settings());doc['middle_sections'][0]['html']='<!--SC_COLLECTOR_IMAGE_V1:nothex-->'
        with self.assertRaises(ValueError):configurations(doc)

    def test_recommendations_exclude_owned_and_unrelated_even_when_selected(self):
        cfg=settings('Related Products',3,product_ids=[P,Q,'gid://shopify/Product/3'])
        shop,store=wire([product(P),product(Q),product('gid://shopify/Product/3','Basketball')])
        result=resolve(shop,store,doc_with(cfg),context(),A,AT)['blocks'][marker(cfg)]
        self.assertEqual([p['title'] for p in result],['Fixture 2'])

    def test_no_purchase_no_interest_uses_only_approved_selection(self):
        ctx=context();ctx['_order']={};ctx['_lifecycle_orders']=[]
        shop,store=wire()
        cfg=settings('Featured Collection',3,product_ids=[Q])
        self.assertEqual(len(resolve(shop,store,doc_with(cfg),ctx,A,AT)['blocks'][marker(cfg)]),1)
        self.assertEqual(resolve(shop,store,doc_with(settings('Related Products',3)),ctx,A,AT)['blocks'],{})

    def test_market_is_recipient_country_never_document_fallback(self):
        cfg=settings('Related Products',3,product_ids=[Q]);shop,store=wire();ctx=context()
        for country in ('AU','US','GB','NZ','CA'):
            ctx['_customer']['defaultAddress']['countryCodeV2']=country
            resolve(shop,store,doc_with(cfg),ctx,A,AT)
            self.assertEqual(shop.query.call_args.args[1]['country'],country)
        ctx['_customer']['defaultAddress']={}
        self.assertEqual(resolve(shop,store,doc_with(cfg),ctx,A,AT)['blocks'],{})

    def test_sold_out_unpublished_and_market_unavailable_omitted(self):
        cfg=settings('Related Products',3,product_ids=[Q])
        for change in ({'status':'DRAFT'},{'publishedInContext':False},{'variants':{'nodes':[]}}, {'featuredImage':{}}):
            p=product();p.update(change);shop,store=wire([p])
            self.assertEqual(resolve(shop,store,doc_with(cfg),context(),A,AT)['blocks'][marker(cfg)],[])

    def test_new_release_window_and_bestseller_authority(self):
        cfg=settings('Verified New Releases',3,product_ids=[Q]);p=product();p['createdAt']=(AT-timedelta(days=31)).isoformat()
        shop,store=wire([p]);self.assertEqual(resolve(shop,store,doc_with(cfg),context(),A,AT)['blocks'][marker(cfg)],[])
        cfg=settings('Verified Bestsellers',3,collection_id='gid://shopify/Collection/9');shop,store=wire()
        self.assertEqual(len(resolve(shop,store,doc_with(cfg),context(),A,AT)['blocks'][marker(cfg)]),1)
        self.assertTrue(any(c.args[0]==BESTSELLERS for c in shop.query.call_args_list))

    def test_history_pages_exclude_later_owned_products_and_have_bound(self):
        o=order();o['lineItems']['pageInfo']={'hasNextPage':True,'endCursor':'next'}
        shop=Mock();shop.line_page.return_value={'nodes':[{'product':{'id':Q}}],'pageInfo':{'hasNextPage':False}}
        self.assertEqual(owned_ids(shop,[o],A),{P,Q})
        shop.line_page.return_value=o['lineItems']
        with self.assertRaises(ValueError):owned_ids(shop,[o],A)
        self.assertLessEqual(shop.line_page.call_count,3)

    def test_wrong_fresh_order_and_envelope_recipient_rejected(self):
        cfg=settings('Actual Purchased Product',2);shop,store=wire(source=order(B))
        with self.assertRaisesRegex(ValueError,'verification'):resolve(shop,store,doc_with(cfg),context(),A,AT)
        from crm_automation_runtime import render as deliver
        content={'document':doc_with(cfg),'trigger':'post_purchase'}
        with self.assertRaisesRegex(ValueError,'recipient mismatch'):
            deliver(content,{'id':'fixture','shopify_customer_id':A},'https://example.test/unsubscribe',
                    {'_customer':{'id':A},'_collector_images':{'recipient':B,'blocks':{}}})

    def test_preview_and_recipient_body_share_renderer(self):
        cfg=settings('Actual Purchased Product',2);shop,store=wire();doc=doc_with(cfg)
        facts=resolve(shop,store,doc,context(),A,AT,allocation_reader=lambda *a:None)['blocks']
        preview=render(doc,facts,preview=True)['custom_html'];actual=render(doc,facts)['custom_html']
        self.assertIn(actual,preview);self.assertNotIn('Sample preview',actual)
        self.assertLessEqual(shop.query.call_count,1);self.assertEqual(shop.products.call_count,1)

    def test_unresolved_blocks_cannot_reach_production_renderer(self):
        from crm_campaign_content import render_campaign
        with self.assertRaisesRegex(ValueError,'resolved'):render_campaign(document('collected-artwork'),production=True)

    def test_optional_shopify_outage_omits_artwork_without_sample_leak(self):
        from crm_shopify import CapabilityUnavailable
        shop,store=wire();shop.query.side_effect=CapabilityUnavailable('fixture outage')
        doc=document('collected-artwork');facts=resolve(shop,store,doc,context(),A,AT)
        output=render(doc,facts['blocks'])['custom_html']
        self.assertNotIn('Allan Moffat',output);self.assertNotIn('Sample preview',output)
        self.assertIn('View My Collection',output)

    def test_existing_flows_and_email_four_are_unchanged_by_library(self):
        from crm_lifecycle_definition import expanded_flow
        from crm_lifecycle_runtime import DRAFT_ONLY
        flow=expanded_flow('win_back');before=deepcopy(flow)
        for key in DESIGNS:document(key)
        self.assertTrue(DRAFT_ONLY);self.assertFalse(flow['emails'][3]['enabled']);self.assertEqual(flow,before)

    def test_image_selector_applies_settings_without_catalogue_requests(self):
        from streamlit.testing.v1 import AppTest
        script='''
import streamlit as st
from unittest.mock import Mock,patch
from crm_collector_templates import document
from crm_collector_image_ui import control
from crm_collector_images import configurations
if 'doc' not in st.session_state:st.session_state.doc=document('collected-artwork')
store=Mock();store.preview_trigger='welcome';store.connect=None
shop=Mock()
with patch('crm_section_ui.rerun_editor'):
    control(st.session_state.doc,'fixture_',shop,store)
st.json(configurations(st.session_state.doc))
assert not shop.query.called
'''
        app=AppTest.from_string(script).run()
        self.assertEqual(len(app.exception),0)
        next(s for s in app.selectbox if s.label=='Image block').select('collector-body:0').run()
        next(s for s in app.selectbox if s.label=='Source').select('No Image').run()
        next(b for b in app.button if b.label=='Apply image settings').click().run()
        self.assertEqual(len(app.exception),0)
        self.assertEqual(configurations(app.session_state.doc)[0]['source'],'No Image')

    def test_abandoned_and_post_purchase_have_no_personalise_image_control(self):
        from crm_collector_image_ui import control
        for trigger in ('abandoned','post_purchase'):
            store=Mock();store.preview_trigger=trigger
            with patch('crm_collector_image_ui.st.container') as container:
                control({},'fixture',Mock(),store)
                container.assert_not_called()


if __name__=='__main__':unittest.main()


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable localhost PostgreSQL required')
class CollectorStorageTests(unittest.TestCase):
    def test_template_revision_and_duplicate_keep_dynamic_settings_without_draft_writes(self):
        from tests.crm_db_fixture import connect
        from tests.test_crm import ADMIN
        from crm_campaign_store import CampaignStore
        from crm_campaign_library import insert_saved_template
        from crm_campaign_content import new_document
        store=CampaignStore(connect)
        before=store.q('SELECT id,config,steps,status FROM crm_automations ORDER BY id')
        doc=document('collected-artwork')
        saved=store.save_design(ADMIN,'Collector fixture',doc)
        saved_doc=store.template_document(store.get('templates',saved['id']))
        self.assertEqual(configurations(saved_doc),configurations(doc))
        updated=deepcopy(doc);updated['content']['subject']='Fixture revision two'
        second=store.save_design(ADMIN,'Collector fixture',updated,saved['id'],saved['version'])
        self.assertEqual(second['version'],saved['version']+1)
        old=store.q('SELECT content FROM crm_template_versions WHERE template_id=%s AND version=%s',(saved['id'],saved['version']),True)
        self.assertEqual(old['content']['document'],saved_doc)
        copy=store.save_design(ADMIN,'Collector fixture copy',updated)
        self.assertNotEqual(copy['id'],saved['id'])
        target=new_document();target.update(content_mode='HTML',custom_html='')
        insert_saved_template(store,target,second['id'],second['version'])
        self.assertEqual(configurations(target),configurations(updated))
        self.assertEqual(before,store.q('SELECT id,config,steps,status FROM crm_automations ORDER BY id'))
        with self.assertRaises(ValueError):store.save_design(ADMIN,'stale',doc,saved['id'],saved['version'])
