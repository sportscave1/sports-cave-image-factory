"""Performance work must preserve validation and exact authored documents."""
from copy import deepcopy
from unittest.mock import patch
import unittest

class EmailV5Tests(unittest.TestCase):
    def test_asset_updates_equal_full_analysis_without_reparsing(self):
        from crm_email_size import analyze_rendered_email,with_asset_metadata
        html='<p>Text</p><img src="https://cdn.shopify.com/a.png"><img src="https://cdn.shopify.com/b.png">'
        local=analyze_rendered_email(html,'Text');before=deepcopy(local)
        for metadata in ({},{'https://cdn.shopify.com/a.png':2000000},{'https://cdn.shopify.com/a.png':-1,'https://cdn.shopify.com/b.png':0}):
            expected=analyze_rendered_email(html,'Text',metadata)
            with patch('crm_email_size.remote_assets',side_effect=AssertionError('Must reuse parsed assets')):
                self.assertEqual(with_asset_metadata(local,metadata),expected)
            self.assertEqual(local,before)

    def test_closed_test_popover_does_not_run_preflight_and_reopening_checks(self):
        from streamlit.testing.v1 import AppTest
        script='''
import streamlit as st
from unittest.mock import Mock
from crm_campaign_send_ui import test_control
from tests.test_crm_simple_editor import document
from tests.test_crm import ADMIN
from tests.test_crm_send_flow import CFG
editor={'id':None,'name':'Fixture','document':document(),'archived_at':None}
test_control(Mock(),ADMIN,editor,'v5_',cfg=CFG)
'''
        with patch('crm_campaign_content.preflight',return_value={'test_ready':True,'test':{}}) as preflight:
            app=AppTest.from_string(script).run();self.assertFalse(app.exception)
            preflight.assert_not_called();self.assertFalse(app.text_input)
            app.session_state['v5_test_popover']=True;app.run();self.assertFalse(app.exception)
            self.assertGreater(preflight.call_count,0)
            field=next(x for x in app.text_input if x.label=='Send test email');field.set_value('fixture@example.test').run()
            app.session_state['v5_test_popover']=False;app.run()
            app.session_state['v5_test_popover']=True;app.run()
            self.assertEqual(next(x for x in app.text_input if x.label=='Send test email').value,'fixture@example.test')
