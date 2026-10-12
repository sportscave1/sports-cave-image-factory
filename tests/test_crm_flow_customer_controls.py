"""Native example-selection controls over isolated synthetic session data."""
from unittest import TestCase
from streamlit.testing.v1 import AppTest

SCRIPT='''
import streamlit as st
from unittest.mock import Mock,patch
from crm_flow_preview import control
if 'pin' not in st.session_state:
    st.session_state.pin={'scope':'fixture','options':[{'key':'one','customer_id':'one','name':'Fixture Ada'}, {'key':'two','customer_id':'two','name':'Fixture Grace'}],'selected':{'key':'one','label':'Fixture Ada'},'error':''}
store=Mock()
store.preview_row={'id':'fixture','config':{'draft':{'trigger':'post_purchase'}}}
store.preview_flow=store.preview_row['config']['draft']
with patch('crm_flow_preview.context',return_value=st.session_state.pin),patch('crm_flow_preview.verify',side_effect=lambda store,shop,row,c:{'key':c['key'],'label':c['name']}):
    control(st.session_state,store,'fixture_')
st.caption('Selected: '+(st.session_state.pin['selected'] or {}).get('label','none'))
assert not store.db.called and not store.enqueue.called
'''


class CustomerControlTests(TestCase):
    def test_switching_examples_updates_selected_customer(self):
        app=AppTest.from_string(SCRIPT).run(timeout=10)
        self.assertEqual(len(app.exception),0)
        app.selectbox[0].select('two').run(timeout=10)
        self.assertEqual(app.session_state.pin['selected']['label'],'Fixture Grace')
        self.assertEqual(len(app.exception),0)

    def test_no_example_has_clear_empty_selection(self):
        script=SCRIPT.replace("'options':[{'key':'one','customer_id':'one','name':'Fixture Ada'}, {'key':'two','customer_id':'two','name':'Fixture Grace'}]", "'options':[]").replace("'selected':{'key':'one','label':'Fixture Ada'}", "'selected':None")
        app=AppTest.from_string(script).run(timeout=10)
        self.assertEqual(len(app.exception),0)
        self.assertTrue(app.selectbox[0].disabled)
