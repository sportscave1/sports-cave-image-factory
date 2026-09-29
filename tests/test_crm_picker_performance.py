"""Picker cache, filters, deferred facts and presentation-only regression checks."""
import time
import unittest
from copy import deepcopy
from unittest.mock import Mock, patch
from concurrent.futures import ThreadPoolExecutor
from crm_catalogue import Catalogue, picker_thumbnail, PICKER_COLLECTIONS, PICKER_PRODUCTS
from crm_picker_cache import _CACHE, load
from crm_middle_sections import middle_sections
from tests.test_crm_modular_catalogue import catalogue_doc, sectioned, event

class PickerTests(unittest.TestCase):
    def setUp(self):_CACHE.invalidate()

    def test_new_defaults_and_saved_values(self):
        doc=sectioned();event(doc,'add',kind='catalogue');cfg=doc['middle_sections'][-1]['settings']
        self.assertEqual(cfg['cta'],'Claim Your Edition')
        self.assertEqual(cfg['display'],dict(image=True,title=True,price=False,limit=True,next=True,remaining=True,cta=True))
        old=catalogue_doc();before=deepcopy(old['middle_sections'][-1]);event(old,'add',kind='catalogue')
        self.assertEqual(old['middle_sections'][-2],before)

    def test_collections_pagination_sort_cache_both_types(self):
        shop=Mock(namespace='collections');shop.query.side_effect=[
            {'collections':{'nodes':[{'id':'2','title':'Tennis'}],'pageInfo':{'hasNextPage':True,'endCursor':'next'}}},
            {'collections':{'nodes':[{'id':'1','title':'Motorsport'}],'pageInfo':{'hasNextPage':False,'endCursor':None}}}]
        cat=Catalogue(shop);first=cat.collections();self.assertEqual([r['title'] for r in first['rows']],['Motorsport','Tennis'])
        self.assertEqual(cat.collections(),first);self.assertEqual(shop.query.call_count,2)
        self.assertNotIn('collection_type',PICKER_COLLECTIONS)

    def test_collection_search_active_pagination_no_n_plus_one(self):
        shop=Mock(namespace='products');shop.query.return_value={'products':{'nodes':[{'id':'gid://shopify/Product/1','title':'Brock','handle':'brock','status':'ACTIVE','featuredImage':{'url':'https://cdn.shopify.com/a.jpg'}}], 'pageInfo':{'hasNextPage':False,'endCursor':None}}}
        cat=Catalogue(shop);collection='gid://shopify/Collection/123'
        first=cat.search('brock',collection=collection);cat.search('brock',collection=collection)
        self.assertEqual(shop.query.call_count,1)
        query=shop.query.call_args.args[1]['query'];self.assertIn('collection_id:123',query);self.assertIn('status:active',query);self.assertIn('title:"brock"',query)
        self.assertIn('width=80',first['rows'][0]['image'])
        cat.search('brock',active=False,collection=collection)
        self.assertNotIn('status:',shop.query.call_args.args[1]['query'])
        with patch.object(cat,'_index_search',return_value={'rows':[],'more':False}) as index:
            cat.search('brock');cat.search('brock');index.assert_called_once()
        self.assertEqual(shop.query.call_count,2)
        with self.assertRaises(ValueError):cat.search(collection='123 OR status:draft')
        self.assertNotIn('variants',PICKER_PRODUCTS);self.assertNotIn('description',PICKER_PRODUCTS)

    def test_ttl_stale_fallback_and_concurrent_single_flight(self):
        clock=[100];calls=[]
        def fetch():calls.append(1);time.sleep(.02);return {'rows':[1]}
        with patch('crm_picker_cache.time.monotonic',side_effect=lambda:clock[0]):
            with ThreadPoolExecutor(6) as executor:
                values=list(executor.map(lambda _:load(('one',),fetch),range(6)))
            self.assertEqual(len(calls),1);self.assertTrue(all(v==({'rows':[1]},False) for v in values))
            clock[0]=701
            def fail():raise RuntimeError('secret must not be exposed')
            self.assertEqual(load(('one',),fail),({'rows':[1]},True))
            self.assertEqual(load(('one',),fetch),({'rows':[1]},True));self.assertEqual(len(calls),1)
            clock[0]=762;load(('one',),fetch);self.assertEqual(len(calls),2)

    def test_thumbnail_only_changes_picker(self):
        url='https://cdn.shopify.com/image.jpg?v=7&width=1000'
        result=picker_thumbnail(url);self.assertIn('v=7',result);self.assertIn('width=80',result)
        self.assertEqual(url,'https://cdn.shopify.com/image.jpg?v=7&width=1000')
        self.assertEqual(picker_thumbnail('javascript:alert(1)'), '')

    def test_dialog_filters_preserve_basket_and_resolve_only_on_add(self):
        from streamlit.testing.v1 import AppTest
        import crm_section_ui
        facts=catalogue_doc()['middle_sections'][-1]['products']
        cat=Mock();cat.collections.return_value={'rows':[{'id':'gid://shopify/Collection/1','title':'Motorsport'}]}
        cat.search.return_value={'rows':facts,'more':False}
        cat.resolve.side_effect=lambda ids,*a,**kw:[p for p in facts if p['id'] in ids]
        crm_section_ui._test_catalogue=cat
        script='''import streamlit as st
from crm_section_ui import product_picker,_test_catalogue
from tests.test_crm_modular_catalogue import catalogue_doc
st.session_state.setdefault('doc',catalogue_doc())
st.session_state.setdefault('p_generation','test')
product_picker(st.session_state.doc,st.session_state.doc['middle_sections'][-1]['id'],_test_catalogue,'p_',editor_key='editor_')
'''
        at=AppTest.from_string(script).run();self.assertEqual(at.selectbox[0].value,'');cat.resolve.assert_not_called()
        at.checkbox[1].uncheck().run();self.assertEqual(cat.search.call_count,1)
        at.selectbox[0].select('gid://shopify/Collection/1').run()
        self.assertEqual(len(at.session_state['p_basket']),1)
        at.text_input[0].set_value('brock').run();at.checkbox[0].uncheck().run()
        self.assertEqual(cat.search.call_args.args,('brock',0,False,'gid://shopify/Collection/1'))
        cat.resolve.assert_not_called()
        at.button[-1].click().run();cat.resolve.assert_called_once()
        self.assertEqual(len(cat.resolve.call_args.args[0]),1);self.assertFalse(at.exception)
        self.assertEqual(at.session_state['editor_catalogue_loaded'],('AU',tuple(cat.resolve.call_args.args[0])))

    def test_toggle_render_has_no_product_reads(self):
        from crm_preview_cache import preview
        from crm_campaign_content import settings
        doc=catalogue_doc();state={}
        with patch('crm_catalogue.Catalogue.resolve') as resolve:
            preview(state,doc,settings())
            for field in ('price','limit','remaining'):
                cfg=deepcopy(doc['middle_sections'][-1]['settings']);cfg['display'][field]=not cfg['display'][field]
                event(doc,'settings',id=doc['middle_sections'][-1]['id'],settings=cfg)
                output=preview(state,doc,settings());self.assertIn('Artwork 1',output['html'])
            resolve.assert_not_called()

if __name__=='__main__':unittest.main()
