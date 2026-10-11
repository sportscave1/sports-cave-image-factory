import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest

class BuyerUiTests(unittest.TestCase):
    def test_controls_default_multiple_remove_clear_and_persist(self):
        app=AppTest.from_file(str(Path('tests/fixtures/campaign_buyer_segments_preview.py'))).run()
        self.addCleanup(app.session_state['fixture-patches'].close)
        self.assertFalse(app.exception)
        location=next(s for s in app.selectbox if s.label=='Location')
        self.assertEqual(location.value,'Global')
        segments=app.multiselect[0];self.assertEqual(segments.value,[]);self.assertEqual(len(segments.options),28)
        segments.set_value(['gid://shopify/Segment/104','gid://shopify/Segment/117']).run()
        self.assertEqual(len(app.session_state['fixture-document']['shopify_segment_ids']),2)
        next(s for s in app.selectbox if s.label=='Location').set_value('AU').run()
        next(b for b in app.button if b.label=='Fixture save').click().run()
        app.multiselect[0].set_value([]).run()
        next(b for b in app.button if b.label=='Fixture reload').click().run()
        self.assertEqual(app.multiselect[0].value,['gid://shopify/Segment/104','gid://shopify/Segment/117'])
        self.assertEqual(next(s for s in app.selectbox if s.label=='Location').value,'AU')
        app.multiselect[0].set_value(['gid://shopify/Segment/104']).run()
        self.assertEqual(len(app.session_state['fixture-document']['shopify_segment_ids']),1)
        app.multiselect[0].set_value([]).run()
        self.assertEqual(app.session_state['fixture-document']['shopify_segment_ids'],[])

    def test_new_compose_defaults_and_existing_restores(self):
        app=AppTest.from_string('''
import streamlit as st
from crm_campaign_page import new_compose,open_editor
from copy import deepcopy
if 'campaign_editor' not in st.session_state:new_compose(sections={'header':'','footer':''})
if st.button('restore'):
 row=deepcopy(st.session_state['campaign_editor']);row['id']='saved'
 row['document'].update(market='AU',shopify_segment_ids=['gid://shopify/Segment/123'],shopify_segment_store='fixture')
 open_editor(row)
''').run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['campaign_editor']['document']['market'],'Global')
        app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['campaign_editor']['document']['market'],'AU')
        self.assertEqual(app.session_state['campaign_editor']['document']['shopify_segment_ids'],['gid://shopify/Segment/123'])
