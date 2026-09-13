import copy
import json
import unittest
from contextlib import contextmanager
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import meta_review_products as products
import meta_review_store as store
import meta_review_handoff as handoff
import ads_product_catalog as catalogue
import ads_page
import meta_ads_client as meta
from tests.test_meta_review_va import DurableHandoffTests

CATALOGUE=[
 {'shopify_product_id':'101','product_handle':'mentality-kobe-jordan','product_title':'The Mentality Kobe vs Jordan Wall Art','collections':['NBA'],'online_store_url':'https://sportscave.com.au/products/mentality-kobe-jordan'},
 {'shopify_product_id':'102','product_handle':'legends-kobe-jordan','product_title':'Legends Never Die Kobe vs Jordan Wall Art','category':'NBA','online_store_url':'https://sportscave.com.au/products/legends-kobe-jordan'},
 {'shopify_product_id':'103','product_handle':'greatest-dynasty-michael-jordan','product_title':'Greatest Dynasty Michael Jordan Wall Art','product_type':'NBA'},
]
PACKAGE={'account_id':'123','ad_id':'ad1','creative_id':'cr1','campaign_id':'cam1','adset_id':'set1',
         'campaign_name':'210526 AUS KOBEVJORDAN','components':{}}


class ResolutionTests(unittest.TestCase):
    def test_exact_identity_levels_and_specificity(self):
        for key in ('ad_id','creative_id','campaign_id','adset_id'):
            result=products.resolve(PACKAGE,CATALOGUE,[{key:PACKAGE[key],'product_handle':CATALOGUE[0]['product_handle']}])
            self.assertEqual(result['confidence'],'EXACT'); self.assertEqual(result['product']['product_id'],'101')
        result=products.resolve(PACKAGE,CATALOGUE,[{'campaign_id':'cam1','product_handle':CATALOGUE[1]['product_handle']},
                  {'ad_id':'ad1','product_handle':CATALOGUE[0]['product_handle']}])
        self.assertEqual(result['product']['product_id'],'101')

    def test_posting_product_ids_and_destination_resolve(self):
        for source in ({'meta_ad_id':'ad1','product_id':'101'}, {'meta_creative_id':'cr1','destination_url':CATALOGUE[0]['online_store_url']}):
            result=products.resolve(PACKAGE,CATALOGUE,postings=[source])
            self.assertEqual(result['product']['product_id'],'101')
            self.assertIn('Posting',result['method'])

    def test_url_child_cards_and_ambiguous_products(self):
        url=CATALOGUE[0]['online_store_url']
        for package in ({**PACKAGE,'destination_url':url+'?utm_source=meta'},
                        {**PACKAGE,'destination_url':'https://facebook.com/canvas/1','product_destination_urls':[url,url]}):
            self.assertEqual(products.resolve(package,CATALOGUE)['product']['product_id'],'101')
        result=products.resolve({**PACKAGE,'product_destination_urls':[url,CATALOGUE[1]['online_store_url']]},CATALOGUE)
        self.assertEqual(result['confidence'],'AMBIGUOUS'); self.assertIsNone(result['product'])
        for url in ('https://facebook.com/canvas/1','https://sportscave.com.au.evil.test/products/mentality-kobe-jordan','https://evil.test/products/mentality-kobe-jordan'):
            self.assertEqual(products.product_url_handle(url),'')

    def test_unique_full_title_high_and_athlete_pairs_only_suggestions(self):
        result=products.resolve({**PACKAGE,'campaign_name':CATALOGUE[2]['product_title']},CATALOGUE)
        self.assertEqual(result['confidence'],'HIGH'); self.assertEqual(result['product']['product_id'],'103')
        result=products.resolve(PACKAGE,CATALOGUE)
        self.assertEqual(result['confidence'],'AMBIGUOUS'); self.assertIsNone(result['product'])
        self.assertEqual({p['product_id'] for p in result['candidates']},{'101','102'})

    def test_existing_conflicts_and_unresolved_handles_do_not_guess(self):
        for mappings in ([{'ad_id':'ad1','product_handle':'missing'}],
                         [{'creative_id':'cr1','product_handle':p['product_handle']} for p in CATALOGUE[:2]]):
            result=products.resolve({**PACKAGE,'destination_url':CATALOGUE[0]['online_store_url']},CATALOGUE,mappings)
            self.assertEqual(result['confidence'],'AMBIGUOUS'); self.assertIsNone(result['product'])

    def test_confirmed_notes_remember_creative_campaign_relationship(self):
        mapping={'ad_id':'different','product_handle':CATALOGUE[0]['product_handle'],'notes':json.dumps({'creative_id':'cr1','campaign_id':'cam1'})}
        self.assertEqual(products.resolve(PACKAGE,CATALOGUE,[mapping])['product']['product_id'],'101')

    def test_exact_mapping_skips_posting_lookup_and_never_calls_meta(self):
        with patch.object(catalogue,'load_live_edition_product_rows',return_value=CATALOGUE),patch.object(store,'product_mapping_context',return_value=[{'ad_id':'ad1','product_handle':CATALOGUE[0]['product_handle']}]),patch.object(store,'product_posting_context') as posting,patch.object(meta,'_request') as request:
            result=products.enrich(PACKAGE)
        self.assertEqual(result['product_id'],'101'); posting.assert_not_called(); request.assert_not_called()

    def test_posting_precedes_url_and_unknown_storage_never_name_guesses(self):
        with patch.object(catalogue,'load_live_edition_product_rows',return_value=CATALOGUE),patch.object(store,'product_mapping_context',return_value=[]),patch.object(store,'product_posting_context',return_value=[{'meta_ad_id':'ad1','product_id':'102'}]):
            result=products.enrich({**PACKAGE,'destination_url':CATALOGUE[0]['online_store_url']})
        self.assertEqual(result['product_id'],'102')
        with patch.object(catalogue,'load_live_edition_product_rows',return_value=CATALOGUE),patch.object(store,'product_mapping_context',side_effect=RuntimeError('offline')):
            result=products.enrich({**PACKAGE,'campaign_name':CATALOGUE[2]['product_title']})
        self.assertFalse(result['product_mapping'])


class PersistenceHydrationTests(unittest.TestCase):
    def test_all_fields_cross_tab_and_original_assets_unchanged(self):
        package=DurableHandoffTests().package()
        package.update(PACKAGE,components=package['components'],market='AU',format='CAROUSEL')
        saved={}
        with patch.object(catalogue,'load_live_edition_product_rows',return_value=CATALOGUE),patch.object(store,'product_mapping_context',return_value=[{'ad_id':'ad1','product_handle':CATALOGUE[0]['product_handle']}]),patch.object(store,'save_selection',side_effect=lambda p,*a:(saved.update(copy.deepcopy(p)) or 7)),patch.object(handoff,'archive_image',return_value='original-sha'):
            handoff.queue_link(package)
            with patch.object(store,'load_handoff',return_value=saved):
                state={}
                handoff.load_link(state,{'handoff_id':saved['handoff_token']},{'ad_account_id':'act_123'})
        self.assertEqual(saved['product_id'],'101')
        self.assertEqual(state[ads_page.ADS_PRODUCT_NAME_KEY],CATALOGUE[0]['product_title'])
        self.assertEqual(state[ads_page.ADS_PRODUCT_SELECTOR_KEY],'id::101')
        self.assertEqual(state['ads_category'],'NBA'); self.assertEqual(state['ads_country'],'Australia')
        self.assertEqual(state['ads_campaign_type'],'Carousel')
        self.assertEqual(state[ads_page.ADS_PRODUCT_URL_KEY],CATALOGUE[0]['online_store_url'])
        self.assertEqual(state[ads_page.ADS_CREATIVE_REFRESH_WINNING_PRIMARY_TEXT_KEY],package['components']['primary_text']['value'])
        self.assertEqual(state[ads_page.ADS_CREATIVE_REFRESH_WINNING_HEADLINE_KEY],package['components']['headline']['value'])
        self.assertEqual(state[handoff.ACTIVE]['image_sha256'],'original-sha')

    def test_canonical_category_url_fallback_and_format_precedence(self):
        product=products.canonical(CATALOGUE[2])
        self.assertEqual(product['product_url'],'https://www.sportscaveshop.com/products/greatest-dynasty-michael-jordan')
        self.assertEqual(product['category'],'NBA')
        package=DurableHandoffTests().package(); package.update(product_mapping=product,format='INSTANT EXPERIENCE',carousel=True)
        state={handoff.PENDING:package}; handoff.hydrate(state)
        self.assertEqual(state['ads_campaign_type'],'Instant Experience')

    def test_confirmation_uses_conflict_guard_and_audit(self):
        commands=[]
        class Cursor:
            def execute(self,sql,params): commands.append((sql,params))
            def fetchone(self): return {'ad_id':'ad1'}
        @contextmanager
        def cursor(write=False): yield Cursor()
        with patch.object(store,'cursor',cursor):
            result=store.confirm_product_mapping({**PACKAGE,'handoff_token':'a'*32},products.canonical(CATALOGUE[0]),'operator')
        self.assertEqual(result['product_mapping']['product_id'],'101')
        self.assertIn("COALESCE(ads_product_mapping.product_handle,'') IN ('',EXCLUDED.product_handle)",commands[0][0])
        self.assertTrue(any('Canonical product confirmed' in sql for sql,_ in commands))
        self.assertTrue(any('UPDATE ads_action_log' in sql for sql,_ in commands))

    def test_conflicting_confirmation_does_not_audit_or_update_package(self):
        commands=[]
        class Cursor:
            def execute(self,sql,params): commands.append(sql)
            def fetchone(self): return None
        @contextmanager
        def cursor(write=False): yield Cursor()
        with patch.object(store,'cursor',cursor),self.assertRaisesRegex(ValueError,'conflicting exact'):
            store.confirm_product_mapping(PACKAGE,products.canonical(CATALOGUE[0]))
        self.assertEqual(len(commands),1)

    def test_manual_confirmation_hydrates_and_remembers_without_changing_text(self):
        state={handoff.ACTIVE:PACKAGE,ads_page.ADS_CREATIVE_REFRESH_WINNING_PRIMARY_TEXT_KEY:'untouched'}
        product=products.canonical(CATALOGUE[0])
        with patch.object(store,'confirm_product_mapping',return_value={**PACKAGE,'product_mapping':product}) as save:
            handoff.confirm_selected_product(state,CATALOGUE[0])
            handoff.confirm_selected_product(state,CATALOGUE[0])
        save.assert_called_once()
        self.assertEqual(state['ads_category'],'NBA'); self.assertEqual(state[ads_page.ADS_CREATIVE_REFRESH_WINNING_PRIMARY_TEXT_KEY],'untouched')

    def test_direct_hydration_without_handoff_does_nothing(self):
        state={'ads_product_name':'manual','ads_category':'Cricket'}; before=copy.deepcopy(state)
        self.assertFalse(handoff.hydrate(state)); handoff.confirm_selected_product(state,CATALOGUE[0])
        self.assertEqual(state,before)


class SelectorTests(unittest.TestCase):
    def test_existing_selector_ranks_candidates_and_confirms_selection(self):
        source={**PACKAGE,'product_resolution':{'candidates':[products.canonical(CATALOGUE[1]),products.canonical(CATALOGUE[0])]}}
        with patch.object(store,'confirm_product_mapping',side_effect=lambda p,product,actor:{**p,'product_mapping':product}) as save:
            app=AppTest.from_string('''import streamlit as st
import ads_page as a
from tests.test_meta_review_products import CATALOGUE,PACKAGE
import meta_review_products as p
st.session_state[a.ADS_ACTIVE_WORKFLOW_MODE_KEY]=a.ADS_WORKFLOW_MODE_CREATIVE_REFRESH
st.session_state.setdefault('meta-review-refresh-source',{**PACKAGE,'product_resolution':{'candidates':[p.canonical(CATALOGUE[1]),p.canonical(CATALOGUE[0])]}})
a.render_product_name_input(rows=CATALOGUE)
''').run()
            self.assertFalse(app.exception)
            self.assertEqual(app.selectbox[0].options[0],CATALOGUE[1]['product_title'])
            app.selectbox[0].select('id::102').run()
            self.assertFalse(app.exception)
        self.assertEqual(save.call_args.args[1]['product_id'],'102')
        self.assertEqual(app.session_state['ads_category'],'NBA')

    def test_new_ads_with_old_handoff_source_does_not_persist_mapping(self):
        with patch.object(store,'confirm_product_mapping') as save:
            app=AppTest.from_string('''import streamlit as st
import ads_page as a
from tests.test_meta_review_products import CATALOGUE,PACKAGE
st.session_state[a.ADS_ACTIVE_WORKFLOW_MODE_KEY]=a.ADS_WORKFLOW_MODE_NEW
st.session_state['meta-review-refresh-source']=PACKAGE
a.render_product_name_input(rows=CATALOGUE)
''').run()
            app.selectbox[0].select('id::101').run()
            self.assertFalse(app.exception)
        save.assert_not_called()


if __name__=='__main__': unittest.main()
