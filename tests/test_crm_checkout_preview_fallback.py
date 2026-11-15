"""Design fallback never becomes a live enrollment context."""
from copy import deepcopy
from concurrent.futures import Future
import unittest
from unittest.mock import Mock,patch
from crm_checkout_preview import document,legacy,sample
from crm_abandoned_checkout import context,preview_context,publication_document
from crm_automation_store import AutomationStore
from crm_campaign_content import render_campaign
from crm_email_size import render_production,analyze_rendered_email
from tests.test_crm_abandoned_checkout import checkout,native_document
from tests.test_crm_send_flow import CFG

LEGACY='''<table><tr><td><h2>MY CUSTOM HEADLINE</h2>
{% if abandoned_checkout %}{% for item in abandoned_checkout.line_items %}
<p>{{ item.product_title }}</p>{% if item.image_url != blank %}<img src="{{ item.image_url }}">{% endif %}
<p>{{ item.variant_title }}</p>{% endfor %}{% else %}<p>OLD EMPTY CART MESSAGE</p>{% endif %}
<a href="{{ abandoned_checkout.url }}">Complete Your Order</a>
<p>MY CUSTOM OUTRO</p></td></tr></table>'''


class PreviewFallbackTests(unittest.TestCase):
    def setUp(self):
        self.guard=patch('requests.sessions.Session.request',side_effect=AssertionError('No external requests'))
        self.guard.start();self.addCleanup(self.guard.stop)

    def legacy_document(self):
        doc=native_document();doc['middle_sections'].pop(1);doc['middle_sections'][0]['html']=LEGACY
        doc['custom_html']=LEGACY;return doc

    def test_legacy_real_substitution_preserves_sections_and_surrounding_copy(self):
        doc=self.legacy_document();original=deepcopy(doc)
        result,warning=document(doc,context(checkout(items=2)))
        message=render_campaign(result,CFG)
        self.assertTrue(warning);self.assertEqual(doc,original)
        self.assertEqual([s['id'] for s in result['middle_sections']],[s['id'] for s in doc['middle_sections']])
        for text in ('MY CUSTOM HEADLINE','MY CUSTOM OUTRO','Questions about sizing','A$199.50'):self.assertIn(text,message['html'])
        for token in ('{{','{%','OLD EMPTY CART MESSAGE'):self.assertNotIn(token,message['html'])
        self.assertEqual(message['html'].count('Complete Your Order'),1)
        self.assertIn('/checkouts/1/',message['html'])

    def test_known_marker_reuses_same_native_renderer(self):
        doc=self.legacy_document();doc['middle_sections'][0]['html']='<h2>Before</h2><!--SC_ABANDONED_CHECKOUT--><p>After</p>'
        result,warning=document(doc,context(checkout()))
        self.assertFalse(warning);self.assertIn('Before',str(result));self.assertIn('After',str(result))
        self.assertNotIn('SC_ABANDONED_CHECKOUT',str(result))

    def test_incomplete_legacy_token_does_not_blank_surrounding_design(self):
        doc=self.legacy_document();doc['middle_sections'][0]['html']='<h2>Before</h2><p>{{ item.product_title</p><p>After</p>'
        result,warning=document(doc,sample(doc));message=render_production(result,CFG)
        self.assertTrue(warning)
        for text in ('Before','After','Complete Your Order'):self.assertIn(text,message['html'])
        self.assertNotIn('{{',message['html'])

    def test_sample_no_fabricated_price_or_recovery_link_and_size_is_measurable(self):
        doc=native_document();result,_=document(doc,sample(doc))
        message=render_production(result,CFG)
        self.assertIn('Your selected edition',message['html']);self.assertIn('Price unavailable in sample',message['html'])
        self.assertIn('Complete Your Order',message['html']);self.assertNotIn('/checkouts/',message['html'])
        self.assertGreater(analyze_rendered_email(message['html'],message['text'])['html_bytes'],100)

    def test_sample_reuses_available_catalogue_facts_without_request(self):
        doc={'middle_sections':[{'type':'catalogue','products':[{'title':'Verified selected product','image':'https://cdn.shopify.com/fixture.png','price':'245.50','currency':'AUD'}]}]}
        data=sample(doc);self.assertEqual(data['items'][0]['amount'],'245.50')
        self.assertEqual(data['items'][0]['title'],'Verified selected product');self.assertTrue(data['preview_only'])

    def test_legacy_long_title_missing_image_and_variant_uses_same_native_output(self):
        raw=checkout(items=2);item=raw['lineItems']['nodes'][0]
        item.update(title='A long verified product title '+('Collector edition '*30),variantTitle=None,image=None)
        result,_=document(self.legacy_document(),context(raw));message=render_production(result,CFG)
        self.assertIn(item['title'],message['text']);self.assertEqual(message['html'].count('https://cdn.shopify.com/fixture.png'),1)

    def test_store_preview_uses_real_then_labelled_cached_then_sample(self):
        store=AutomationStore(lambda:None);store.preview_shop=Mock();doc=self.legacy_document()
        data=context(checkout())
        for supplied,note,expected in ((data,'','latest abandoned checkout'),(data,'Unavailable','cached latest abandoned checkout'),(None,'Unavailable','Sample abandoned checkout')):
            with patch('crm_abandoned_checkout.preview_context',return_value=(supplied,note)):
                result,label=store.preview_document(doc)
            self.assertIn(expected,label);self.assertIn('Legacy checkout block',store.preview_warning)
            self.assertIn('MY CUSTOM HEADLINE',render_campaign(result,CFG)['html'])

    def test_cached_good_value_survives_refresh_and_provider_error(self):
        good=context(checkout());future=Future();future.set_result(good)
        state={'abandoned_preview':{'future':future,'started':0,'namespace':'configured-shop'}}
        pending=Future();pool=Mock();pool.submit.return_value=pending;capacity=Mock();capacity.acquire.return_value=True
        with patch('crm_campaign_home_cache.POOL',pool),patch('crm_campaign_home_cache.CAPACITY',capacity):
            value,note=preview_context(state,Mock(),refresh=True)
            self.assertEqual(value,good);self.assertIn('Refreshing',note)
            pending.set_exception(RuntimeError('Provider unavailable'))
            value,note=preview_context(state,Mock())
            self.assertEqual(value,good);self.assertIn('unavailable',note)

    def test_cold_provider_error_preview_is_sample_and_visible(self):
        from streamlit import session_state
        store=AutomationStore(lambda:None);store.preview_shop=Mock();failed=Future();failed.set_exception(RuntimeError())
        state={'abandoned_preview':{'future':failed,'started':10**20,'namespace':'configured-shop'}}
        with patch('streamlit.session_state',state):result,label=store.preview_document(native_document())
        self.assertEqual(label,'Previewing: Sample abandoned checkout')
        self.assertIn('YOUR COLLECTION AWAITS',render_campaign(result,CFG)['html'])

    def test_manual_legacy_test_disabled_real_recovery_and_original_unchanged(self):
        store=AutomationStore(lambda:None);store.draft_identity='fixture';store.preview_shop=Mock()
        store.flow=Mock(return_value={'config':{'draft':{'trigger':'abandoned'}}})
        store.preview_shop.abandoned_preview.return_value={'nodes':[checkout()], 'pageInfo':{'hasNextPage':False}}
        doc=self.legacy_document();before=deepcopy(doc);result=store.test_document(doc,'op')
        message=render_production(result,CFG)
        self.assertIn('A$199.50',message['html']);self.assertIn('Recovery action disabled',message['html'])
        self.assertNotIn('/checkouts/1/',message['html']);self.assertEqual(doc,before)

    def test_preview_fallback_cannot_relax_publication_or_live_binding(self):
        from crm_automation_runtime import render
        import uuid
        doc=self.legacy_document()
        with self.assertRaises(ValueError):publication_document(doc,'abandoned')
        payload={'document':native_document(),'render_settings':CFG,'trigger':'abandoned'}
        row={'id':str(uuid.uuid4()),'shopify_customer_id':'gid://shopify/Customer/1'}
        for data in (sample(doc),checkout(customer=2),{**checkout(),'completedAt':'2026-10-02'}):
            with self.assertRaises(ValueError):render(payload,row,'https://example.test/unsubscribe',{'_checkout':data,'_checkout_id':data.get('id')})

    def test_missing_url_or_cart_does_not_blank_design_preview(self):
        store=AutomationStore(lambda:None);store.preview_shop=Mock()
        for raw in ({**checkout(),'abandonedCheckoutUrl':''},{**checkout(),'lineItems':{'nodes':[]}}):
            store.preview_shop.abandoned_preview.return_value={'nodes':[raw],'pageInfo':{'hasNextPage':False}}
            from crm_abandoned_checkout import latest
            self.assertIsNone(latest(store.preview_shop))
            with patch('crm_abandoned_checkout.preview_context',return_value=(None,'')):
                result,label=store.preview_document(self.legacy_document())
            self.assertIn('Sample',label);self.assertIn('MY CUSTOM OUTRO',render_production(result,CFG)['html'])


if __name__=='__main__':unittest.main()
