"""Product correction regression fixtures; no Shopify/Meta writes."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import ads_page as ads
import ads_refresh_product as correction
import ads_refresh_generation as generation
import meta_review_handoff as handoff
import meta_review_products as products

BROCK={'shopify_product_id':'101','product_title':'Six Laps Ahead Peter Brock Wall Art','product_handle':'six-laps-ahead-peter-brock-wall-art'}
MURPHY={'shopify_product_id':'202','product_title':'Greg Murphy Lap of the Gods Wall Art','product_handle':'greg-murphy-lap-of-the-gods-wall-art'}
for row in (BROCK,MURPHY):row['online_store_url']='https://www.sportscaveshop.com/products/'+row['product_handle']
ROWS=[BROCK,MURPHY]


class ProductCorrectionTests(unittest.TestCase):
    def setUp(self):
        self.source={'ad_id':'carousel-1','campaign_id':'same-campaign','product_mapping':products.canonical(BROCK),
                     'components':{'primary_text':{'value':'Winning copy'},'headline':{'value':'Winning headline'}}}
        self.state={handoff.ACTIVE:deepcopy(self.source),ads.ADS_ACTIVE_WORKFLOW_MODE_KEY:'creative_refresh'}
        handoff.hydrate_product(self.state,self.source['product_mapping'])
        self.guard=patch.object(ads.st,'session_state',self.state);self.guard.start();self.addCleanup(self.guard.stop)
        guard=patch('requests.sessions.Session.request',side_effect=AssertionError('External network forbidden'));guard.start();self.addCleanup(guard.stop)
    def select(self,row):
        self.state[ads.ADS_PRODUCT_SELECTOR_KEY]=ads._edition_ops_product_selector_identity(row)
        ads._on_ads_product_selector_changed(ROWS)
    def issue(self):return generation.carousel_identity_issue(self.state[ads.ADS_PRODUCT_NAME_KEY],self.state[ads.ADS_PRODUCT_URL_KEY],self.state[handoff.ACTIVE])
    def test_normal_import_remains_selected_without_correction(self):
        self.assertFalse(self.issue());self.assertNotIn('product_correction',self.state[handoff.ACTIVE])
    def test_brock_to_murphy_updates_identity_without_shared_mapping_write(self):
        self.state['ads_category']='Motorsport';self.state['ads_country']='USA'
        with patch('meta_review_store.confirm_product_mapping',side_effect=AssertionError('Shared mapping write')):
            self.select(MURPHY)
        self.assertFalse(self.issue());source=self.state[handoff.ACTIVE]
        self.assertEqual(source['product_id'],'202');self.assertEqual(source['product_handle'],MURPHY['product_handle'])
        self.assertEqual(self.state[ads.ADS_PRODUCT_URL_KEY],MURPHY['online_store_url'])
        self.assertEqual(source['components'],self.source['components'])
        self.assertEqual(self.state['ads_category'],'Motorsport');self.assertEqual(self.state['ads_country'],'USA')
        self.assertEqual(source['product_correction']['original_mapping']['product_id'],'101')
    def test_url_first_explicit_resolution_and_tracking(self):
        self.state[ads.ADS_PRODUCT_URL_KEY]=MURPHY['online_store_url']+'?utm_campaign=refresh&variant=123#details'
        correction.select_from_url(ROWS)
        self.assertFalse(self.issue());self.assertIn('variant=123#details',self.state[ads.ADS_PRODUCT_URL_KEY])
    def test_tracking_retained_but_previous_product_variant_not_carried(self):
        self.state[ads.ADS_PRODUCT_URL_KEY]=BROCK['online_store_url']+'?utm_source=facebook&variant=999#old'
        self.select(MURPHY)
        self.assertEqual(self.state[ads.ADS_PRODUCT_URL_KEY],MURPHY['online_store_url']+'?utm_source=facebook')
    def test_mismatch_and_label_only_change_remain_blocked(self):
        self.state[ads.ADS_PRODUCT_URL_KEY]=MURPHY['online_store_url']
        self.assertIn('Use product from URL',self.issue())
        self.state[ads.ADS_PRODUCT_SELECTOR_KEY]='Invented product label';ads._on_ads_product_selector_changed(ROWS)
        self.assertTrue(self.issue());self.assertEqual(self.state[handoff.ACTIVE]['product_mapping']['product_id'],'101')
    def test_unknown_or_ambiguous_url_does_not_change_identity(self):
        self.state[ads.ADS_PRODUCT_URL_KEY]='https://example.test/products/'+MURPHY['product_handle']
        correction.select_from_url(ROWS)
        self.assertEqual(self.state[handoff.ACTIVE],self.source)
        self.assertIn('could not be matched',self.state['meta-review-product-error'])
    def test_other_ad_and_original_history_are_unchanged(self):
        other=deepcopy(self.source);other['ad_id']='carousel-2'
        self.state['other_saved_refresh']=other
        self.select(MURPHY)
        self.assertEqual(self.state['other_saved_refresh'],other)
        self.assertEqual(self.source['product_mapping']['product_id'],'101')
    def test_reruns_manual_url_and_saved_workspace_keep_corrected_product(self):
        self.select(MURPHY)
        self.state[ads.ADS_PRODUCT_URL_KEY]+='?utm_source=manual';ads._on_ads_product_url_changed()
        for _ in range(3):
            rows=handoff.product_selector_rows(ROWS,self.state)
            ads.prepare_ads_product_selector_state(rows)
            selection=ads.resolve_ads_product_selector_value(self.state[ads.ADS_PRODUCT_SELECTOR_KEY],rows=rows)
            ads.prepare_ads_product_url_state(selection['selected_label'],selection=selection)
            self.assertFalse(self.issue())
        from ads_refresh_saved import dumps,loads
        result={'workflow_mode':'creative_refresh','context_key':'fixture','creative_refresh_context':generation.source_context(self.state[handoff.ACTIVE])}
        restored,_=loads(dumps(result,{'context_key':'fixture'}))
        self.assertEqual(restored['creative_refresh_context']['source_winner']['product_mapping']['product_id'],'202')
        self.assertTrue(self.state[ads.ADS_PRODUCT_URL_KEY].endswith('utm_source=manual'))
    def test_manual_exact_name_resolves_actual_identity(self):
        self.state[ads.ADS_PRODUCT_SELECTOR_KEY]=MURPHY['product_title'];ads._on_ads_product_selector_changed(ROWS)
        self.assertFalse(self.issue());self.assertEqual(self.state[handoff.ACTIVE]['product_id'],'202')


class ProductSelectorUITests(unittest.TestCase):
    def test_import_selector_url_first_and_rerun(self):
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_string('''
import streamlit as st
import ads_page as ads
import ads_refresh_product as correction
import meta_review_handoff as handoff
import meta_review_products as products
from tests.test_ads_refresh_product import ROWS,BROCK
st.session_state[ads.ADS_ACTIVE_WORKFLOW_MODE_KEY]='creative_refresh'
if handoff.ACTIVE not in st.session_state:
    st.session_state[handoff.ACTIVE]={'ad_id':'fixture','product_mapping':products.canonical(BROCK)}
    handoff.hydrate_product(st.session_state,products.canonical(BROCK))
name,selection=ads.render_product_name_input(rows=ROWS)
ads.prepare_ads_product_url_state(name,selection=selection)
st.text_input('Product URL',key=ads.ADS_PRODUCT_URL_KEY,on_change=ads._on_ads_product_url_changed)
st.button('Use product from URL',on_click=correction.select_from_url,args=(ROWS,))
st.button('Rerun')
''').run(timeout=20)
        self.assertFalse(app.exception)
        app.selectbox[0].set_value(ads._edition_ops_product_selector_identity(MURPHY)).run()
        self.assertFalse(app.exception);self.assertEqual(app.text_input[0].value,MURPHY['online_store_url'])
        app.text_input[0].set_value(BROCK['online_store_url']).run()
        app.button[0].click().run();self.assertFalse(app.exception)
        self.assertEqual(app.selectbox[0].value,ads._edition_ops_product_selector_identity(BROCK))
        app.button[1].click().run();self.assertEqual(app.text_input[0].value,BROCK['online_store_url'])


if __name__=='__main__':unittest.main()
