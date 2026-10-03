"""Deterministic checkout rendering; external requests are forbidden."""
from copy import deepcopy
from concurrent.futures import Future
from pathlib import Path
import unittest
from unittest.mock import Mock,patch
from crm_abandoned_checkout import (BLOCK,apply_template,block_html,complete,context,dynamic,
    hydrate,latest,preview_context,publication_document)
from crm_campaign_content import render_campaign
from crm_middle_sections import validate_middle
from tests.test_crm_simple_editor import document
from tests.test_crm_send_flow import CFG


def checkout(identity=1,customer=1,currency='AUD',items=1):
    return {'id':'gid://shopify/AbandonedCheckout/'+str(identity),'createdAt':'2026-10-01T00:00:00Z',
        'completedAt':None,'abandonedCheckoutUrl':'https://example.test/checkouts/'+str(identity)+'/recover?key=fixture',
        'customer':{'id':'gid://shopify/Customer/'+str(customer),'firstName':'Fixture','lastName':'Collector'},
        'lineItems':{'nodes':[{'id':'line'+str(i),'title':'A collector edition <safe> '+str(i),
            'variantTitle':'Black frame / Large','quantity':2,'image':{'url':'https://cdn.shopify.com/fixture.png'},
            'discountedTotalPriceWithCodeDiscount':{'presentmentMoney':{'amount':'199.50','currencyCode':currency},
                'shopMoney':{'amount':'312','currencyCode':'NZD'}}} for i in range(items)],'pageInfo':{'hasNextPage':False}}}


def native_document():
    doc=document();apply_template(doc);doc['copy_reviewed']=True;return doc


class CheckoutTests(unittest.TestCase):
    def setUp(self):
        self.network=patch('requests.sessions.Session.request',side_effect=AssertionError('External request forbidden'))
        self.network.start();self.addCleanup(self.network.stop)

    def test_native_document_is_typed_and_has_no_customer_data(self):
        doc=native_document();validate_middle(doc['middle_sections']);self.assertTrue(dynamic(doc))
        self.assertEqual([s['type'] for s in doc['middle_sections']],['html',BLOCK,'html'])
        self.assertNotIn('recover',str(doc));self.assertNotIn('{{',str(doc))

    def test_final_render_multi_items_escape_and_buyer_currency(self):
        for currency in ('AUD','USD'):
            with self.subTest(currency=currency):
                original=native_document();before=deepcopy(original);data=context(checkout(currency=currency,items=2))
                rendered=render_campaign(hydrate(original,data),CFG)
                self.assertIn(currency+' 199.50',rendered['html']);self.assertIn('Quantity: 2',rendered['text'])
                self.assertIn('&lt;safe&gt;',rendered['html']);self.assertNotIn('NZD 312',rendered['html'])
                self.assertIn('Complete Your Order',rendered['html']);self.assertEqual(original,before)
                self.assertNotIn('{{',rendered['html']);self.assertNotIn(BLOCK,rendered['html'])

    def test_missing_image_variant_long_title_images_off_plain_text(self):
        raw=checkout();line=raw['lineItems']['nodes'][0];line['image']=None;line['variantTitle']=None
        line['title']='Real product identity — '+('Collector '+ 'edition ')*40
        data=context(raw);output=render_campaign(hydrate(native_document(),data),CFG,images_off=True)
        self.assertIn(line['title'],output['text']);self.assertIn('AUD 199.50',output['text'])
        self.assertNotIn('<img',block_html(data));self.assertNotIn('None',output['html'])

    def test_test_message_disables_only_recovery_and_keeps_real_products(self):
        data=context(checkout());message=render_campaign(hydrate(native_document(),data,test=True),CFG)
        self.assertNotIn(data['recovery_url'],message['html']);self.assertNotIn('/checkouts/1/',message['text'])
        self.assertIn('Recovery action disabled',message['html']);self.assertIn('Black frame',message['text'])

    def test_recovered_empty_partial_bad_urls_or_prices_fail_closed(self):
        for mutate in (lambda c:c.update(completedAt='2026-10-02'),
            lambda c:c['lineItems'].update(nodes=[]),lambda c:c['lineItems']['pageInfo'].update(hasNextPage=True),
            lambda c:c.update(abandonedCheckoutUrl='http://example.test/recover'),
            lambda c:c['lineItems']['nodes'][0].update(quantity=True),
            lambda c:c['lineItems']['nodes'][0]['discountedTotalPriceWithCodeDiscount']['presentmentMoney'].update(amount='NaN'),
            lambda c:c['lineItems']['nodes'][0].update(image={'url':'javascript:alert(1)'})):
            raw=checkout();mutate(raw)
            with self.assertRaises(ValueError):context(raw)

    def test_latest_falls_back_newest_valid_and_no_fake_when_empty(self):
        shop=Mock();invalid=checkout(3);invalid['completedAt']='2026-10-02'
        shop.abandoned_preview.return_value={'nodes':[invalid,checkout(2),checkout(1)],'pageInfo':{'hasNextPage':False}}
        self.assertEqual(latest(shop)['checkout_id'],checkout(2)['id']);shop.customer.assert_not_called()
        shop.abandoned_preview.assert_called_once_with(after=None,fresh=True)
        shop.abandoned_preview.return_value={'nodes':[],'pageInfo':{'hasNextPage':False}}
        self.assertIsNone(latest(shop))

    def test_systemic_failure_not_masked_as_empty_preview(self):
        shop=Mock();shop.abandoned_preview.side_effect=RuntimeError('source unavailable')
        with self.assertRaises(RuntimeError):latest(shop)

    def test_manual_test_without_checkout_or_wrong_trigger_cannot_render(self):
        from crm_automation_store import AutomationStore
        store=AutomationStore(lambda:None);store.draft_identity='local-fixture'
        store.flow=Mock(return_value={'config':{'draft':{'trigger':'abandoned'}}})
        store.preview_shop=Mock();store.preview_shop.abandoned_preview.return_value={'nodes':[],'pageInfo':{'hasNextPage':False}}
        doc=native_document();original=deepcopy(doc)
        with self.assertRaisesRegex(ValueError,'No recent'):store.test_document(doc,'operation')
        self.assertEqual(doc,original)
        store.flow.return_value={'config':{'draft':{'trigger':'welcome'}}}
        store.preview_shop.reset_mock()
        with self.assertRaisesRegex(ValueError,'trigger'):store.test_document(doc,'operation')
        store.preview_shop.abandoned_preview.assert_not_called()

    def test_legacy_liquid_preview_fails_before_shopify_reads(self):
        from crm_automation_store import AutomationStore
        store=AutomationStore(lambda:None);store.preview_shop=Mock()
        doc=document();doc['custom_html']='{{ item.product_title }}'
        with self.assertRaisesRegex(ValueError,'Unresolved'):store.preview_document(doc)
        store.preview_shop.abandoned_preview.assert_not_called()

    def test_bounded_complete_products_and_unstable_pagination(self):
        raw=checkout();raw['lineItems']['pageInfo']={'hasNextPage':True,'endCursor':'next'}
        shop=Mock();shop.checkout_lines.return_value={'nodes':checkout(items=2)['lineItems']['nodes'][1:],'pageInfo':{'hasNextPage':False}}
        result=complete(shop,raw);self.assertEqual(len(result['lineItems']['nodes']),2)
        shop.checkout_lines.assert_called_once_with(raw['id'],'next',fresh=True)
        self.assertEqual(len(raw['lineItems']['nodes']),1)
        shop.checkout_lines.return_value=deepcopy(raw['lineItems'])
        with self.assertRaises(ValueError):complete(shop,raw)

    def test_preview_returns_immediately_and_caches_resolved_context(self):
        future=Future();pool=Mock();pool.submit.return_value=future;capacity=Mock();capacity.acquire.return_value=True
        state={}
        with patch('crm_campaign_home_cache.POOL',pool),patch('crm_campaign_home_cache.CAPACITY',capacity):
            data,note=preview_context(state,Mock());self.assertIsNone(data);self.assertIn('Loading',note)
            data,note=preview_context(state,Mock());self.assertIsNone(data);pool.submit.assert_called_once()
            preview_context(state,Mock(),refresh=True);pool.submit.assert_called_once()
            future.set_result(context(checkout()))
            data,note=preview_context(state,Mock());self.assertEqual(data['checkout_id'],checkout()['id']);self.assertEqual(note,'')
            pool.submit.assert_called_once()

    def test_raw_liquid_rejected_for_publish_and_render(self):
        doc=native_document();doc['middle_sections'][0]['html']='{{ checkout.line_items }}'
        with self.assertRaises(ValueError):publication_document(doc,'abandoned')
        with self.assertRaises(ValueError):hydrate(doc,context(checkout()))
        doc=document();doc['custom_html']='{% for item in checkout.line_items %}'
        with self.assertRaises(ValueError):publication_document(doc,'abandoned')

    def test_publish_removes_runtime_block_only_in_validation_copy(self):
        doc=native_document();copy=deepcopy(doc);safe=publication_document(doc,'abandoned')
        self.assertFalse(dynamic(safe));self.assertEqual(doc,copy)
        with self.assertRaises(ValueError):publication_document(doc,'welcome')

    def test_product_images_responsive_and_uncropped(self):
        from html.parser import HTMLParser
        class Images(HTMLParser):
            def handle_starttag(self,tag,attrs):
                if tag=='img':self.image=dict(attrs)
        parser=Images();parser.feed(block_html(context(checkout())));img=parser.image
        self.assertIn('width:100%',img['style']);self.assertIn('height:auto',img['style']);self.assertTrue(img['alt'])
        for disallowed in ('object-fit:cover','min-width','height="','base64','<script','<iframe'):self.assertNotIn(disallowed,str(img))

    def test_shopify_webp_reuses_existing_safe_png_transform(self):
        raw=checkout();raw['lineItems']['nodes'][0]['image']['url']='https://cdn.shopify.com/s/files/fixture.webp?v=42'
        message=render_campaign(hydrate(native_document(),context(raw)),CFG)
        self.assertIn('format=png',message['html'])
        from crm_campaign_content import preflight
        self.assertTrue(preflight(hydrate(native_document(),context(raw)),cfg=CFG)['test']['Images use durable public JPEG/PNG URLs'])

    def test_live_render_uses_exact_bound_context_and_rejects_mismatch(self):
        from crm_automation_runtime import render
        import uuid
        bound=checkout(2,2);row={'id':str(uuid.uuid4()),'shopify_customer_id':bound['customer']['id']}
        content={'document':native_document(),'render_settings':CFG,'trigger':'abandoned'}
        ctx={'_checkout':bound,'_checkout_id':bound['id']}
        with patch('crm_campaign_send.production_checks',return_value={'safe':True}):
            msg=render(content,row,'https://example.test/unsubscribe',ctx)
            self.assertIn('/checkouts/2/',msg['html']);self.assertNotIn('/checkouts/1/',msg['html'])
            for wrong in ({}, {'_checkout':checkout(1),'_checkout_id':checkout(1)['id']}, {'_checkout':bound,'_checkout_id':checkout(1)['id']}):
                with self.assertRaises(ValueError):render(content,row,'https://example.test/unsubscribe',wrong)

    def test_automation_only_ui_and_no_saved_preview_customer(self):
        source=Path('crm_automation_ui.py').read_text(encoding='utf-8')
        self.assertLess(source.index("st.button('Save draft'"),source.index('live_control(store'))
        self.assertLess(source.index('live_control(store'),source.index('test_control(store'))
        source=Path('crm_campaign_page.py').read_text(encoding='utf-8')
        self.assertIn("if mode!='automation'",source)
        self.assertIn("'abandoned_checkout_products'",Path('components/crm_sections/composer.js').read_text(encoding='utf-8'))


if __name__=='__main__':unittest.main()
