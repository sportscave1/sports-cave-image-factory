"""Capture checkbox changes before collection/search reruns replace result widgets."""
import unittest
from unittest.mock import Mock
from streamlit.testing.v1 import AppTest
import crm_section_ui
from tests.test_crm_modular_catalogue import catalogue_doc

class PickerSelectionTests(unittest.TestCase):
    def test_checkbox_and_collection_change_in_same_rerun(self):
        facts=catalogue_doc()['middle_sections'][-1]['products']
        cat=Mock()
        cat.collections.return_value={'rows':[{'id':'gid://shopify/Collection/1','title':'First'},
                                             {'id':'gid://shopify/Collection/2','title':'Second'}]}
        cat.search.side_effect=lambda q,o,a,c:{'rows':[facts[1]] if c.endswith('/2') else [facts[0]],'more':False}
        crm_section_ui._selection_fixture=cat
        self.addCleanup(lambda:delattr(crm_section_ui,'_selection_fixture'))
        at=AppTest.from_string('''import streamlit as st
from crm_section_ui import product_picker,_selection_fixture
from tests.test_crm_modular_catalogue import catalogue_doc
if 'doc' not in st.session_state:
 st.session_state.doc=catalogue_doc()
 st.session_state.doc['middle_sections'][-1]['products']=[]
st.session_state.setdefault('p_generation','fixture')
product_picker(st.session_state.doc,st.session_state.doc['middle_sections'][-1]['id'],_selection_fixture,'p_')
''').run()
        at.checkbox[1].check()
        at.selectbox[0].select('gid://shopify/Collection/2').run()
        self.assertIn(facts[0]['id'],at.session_state['p_basket'])
        at.checkbox[1].check()
        at.selectbox[0].select('gid://shopify/Collection/1').run()
        self.assertEqual(set(at.session_state['p_basket']),{p['id'] for p in facts})
        self.assertTrue(at.checkbox[1].value)
        at.checkbox[1].uncheck()
        at.selectbox[0].select('gid://shopify/Collection/2').run()
        self.assertNotIn(facts[0]['id'],at.session_state['p_basket'])
        self.assertIn(facts[1]['id'],at.session_state['p_basket'])
        cat.resolve.assert_not_called()
        self.assertFalse(at.exception)

    def test_loading_and_verification_failures_retain_basket_and_cancel(self):
        facts=catalogue_doc()['middle_sections'][-1]['products']
        for loading_failure in (True,False):
            with self.subTest(loading_failure=loading_failure):
                cat=Mock()
                cat.collections.return_value={'rows':[]}
                if loading_failure:cat.search.side_effect=RuntimeError('fixture loading failure')
                else:cat.search.return_value={'rows':facts,'more':False}
                cat.resolve.side_effect=RuntimeError('fixture verification failure')
                crm_section_ui._error_fixture=cat
                at=AppTest.from_string("""import streamlit as st
from crm_section_ui import product_picker,_error_fixture
from tests.test_crm_modular_catalogue import catalogue_doc
st.session_state.setdefault('doc',catalogue_doc())
st.session_state.setdefault('p_generation','fixture')
product_picker(st.session_state.doc,st.session_state.doc['middle_sections'][-1]['id'],_error_fixture,'p_')
""").run()
                self.assertTrue(any(b.label=='Cancel' for b in at.button))
                next(b for b in at.button if b.label=='Add selected').click().run()
                self.assertTrue(any('could not be verified with Shopify' in w.value for w in at.warning))
                self.assertEqual(set(at.session_state['p_basket']),{p['id'] for p in facts})
                self.assertEqual(at.session_state['doc']['middle_sections'][-1]['products'],facts)
                self.assertFalse(at.exception)
                del crm_section_ui._error_fixture

    def test_duplicate_collection_titles_resolve_exact_ids(self):
        cat=Mock()
        cat.collections.return_value={'rows':[{'id':'gid://shopify/Collection/1','title':'THE GIFT EDIT'},
                                             {'id':'gid://shopify/Collection/2','title':'THE GIFT EDIT'},
                                             {'id':'gid://shopify/Collection/3','title':'All collections'}]}
        cat.search.return_value={'rows':[],'more':False}
        crm_section_ui._duplicate_fixture=cat
        self.addCleanup(lambda:delattr(crm_section_ui,'_duplicate_fixture'))
        at=AppTest.from_string("""import streamlit as st
from crm_section_ui import product_picker,_duplicate_fixture
from tests.test_crm_modular_catalogue import catalogue_doc
st.session_state.setdefault('doc',catalogue_doc())
st.session_state.setdefault('p_generation','fixture')
product_picker(st.session_state.doc,st.session_state.doc['middle_sections'][-1]['id'],_duplicate_fixture,'p_')
""").run()
        self.assertEqual(len(set(at.selectbox[0].options)),4)
        for identity in ('gid://shopify/Collection/1','gid://shopify/Collection/2','gid://shopify/Collection/3',''):
            at.selectbox[0].select(identity).run()
            self.assertEqual(cat.search.call_args.args[-1],identity)
            self.assertEqual(at.selectbox[0].value,identity)
        self.assertFalse(at.exception)

if __name__=='__main__':unittest.main()
