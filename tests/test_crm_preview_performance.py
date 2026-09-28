"""Deterministic preview cache/fragment contracts; no remote services or timing limits."""
from contextlib import contextmanager
from copy import deepcopy
import unittest
from unittest.mock import patch

from crm_preview_cache import preview, KEY, LIMIT, BYTE_LIMIT
from crm_campaign_content import render_campaign, settings
from tests.test_crm_campaign_sections import sectioned
from tests.test_crm_resend_marketing import ENV


class PreviewPerformanceTests(unittest.TestCase):
    def test_cached_html_matches_canonical_without_repeated_sanitizing(self):
        doc=sectioned();cfg=settings(ENV);state={};expected=render_campaign(doc,cfg)
        with patch('crm_preview_cache.render_campaign',wraps=render_campaign) as render:
            result=preview(state,doc,cfg)
            self.assertEqual(result,expected)
            result['html']='Caller mutation'
            for _ in range(5):self.assertEqual(preview(state,doc,cfg),expected)
            render.assert_called_once()

    def test_content_templates_config_images_and_subject_invalidate_immediately(self):
        doc=sectioned();cfg=settings(ENV);state={}
        with patch('crm_preview_cache.render_campaign',wraps=render_campaign) as render:
            preview(state,doc,cfg)
            for change in (lambda:doc.update(custom_html='<p>Edited body</p>'),
                           lambda:doc['html_sections'].update(header='<p>Selected header</p>'),
                           lambda:doc['html_sections'].update(footer='<p>Selected footer</p>'),
                           lambda:doc['content'].update(subject='Edited subject'),
                           lambda:cfg.update(accent='#aabbcc')):
                change();preview(state,doc,cfg)
            preview(state,doc,cfg,images_off=True)
            self.assertEqual(render.call_count,7)
            self.assertLessEqual(len(state[KEY]),LIMIT)
            self.assertLessEqual(sum(item[1] for item in state[KEY].values()),BYTE_LIMIT)

    def test_unrelated_ui_metadata_does_not_regenerate_and_sessions_are_isolated(self):
        doc=sectioned();cfg=settings(ENV);state={}
        with patch('crm_preview_cache.render_campaign',wraps=render_campaign) as render:
            preview(state,doc,cfg)
            doc.update(copy_reviewed=False,notes='Internal only',smart_hours=24)
            preview(state,doc,cfg)
            self.assertEqual(render.call_count,1)
            preview({},doc,cfg)
            self.assertEqual(render.call_count,2)

    def test_loading_only_on_miss_errors_never_cached_and_validation_not_bypassed(self):
        doc=sectioned();cfg=settings(ENV);state={};events=[]
        @contextmanager
        def loading():
            events.append('start')
            try:yield
            finally:events.append('finish')
        with patch('crm_preview_cache.render_campaign',side_effect=ValueError('Bad preview')):
            with self.assertRaises(ValueError):preview(state,doc,cfg,loading=loading)
        self.assertFalse(state[KEY]);self.assertEqual(events,['start','finish'])
        preview(state,doc,cfg,loading=loading);preview(state,doc,cfg,loading=loading)
        self.assertEqual(events,['start','finish']*2)
        doc['audience']={'kind':'unsafe'}
        with self.assertRaises(ValueError):preview(state,doc,cfg)

    def test_preview_fragment_device_changes_do_not_read_database_or_audience(self):
        from streamlit.testing.v1 import AppTest
        from crm_campaign_html import EmailHTML
        import crm_html_workspace as workspace
        script='''
import streamlit as st
from crm_html_workspace import composer_canvas
from tests.test_crm_campaign_sections import sectioned
from crm_campaign_content import settings
from tests.test_crm_resend_marketing import ENV
doc=st.session_state.setdefault('doc',sectioned())
composer_canvas(doc,settings(ENV),'fixture_')
'''
        with patch('crm_store.Store.q',side_effect=AssertionError('Preview must not read database')), \
             patch('crm_audience.selection_page',side_effect=AssertionError('Preview must not calculate audience')):
            at=AppTest.from_string(script).run()
            self.assertFalse(at.exception)
            html=at.get('iframe')[0].proto.srcdoc
            with patch.object(EmailHTML,'feed',side_effect=AssertionError('Viewport must reuse HTML')), \
                 patch.object(workspace.components,'html',wraps=workspace.components.html) as iframe:
                for device,width in [('Mobile',390),('Desktop',600)]:
                    at.button(key='fixture_device_'+device).click().run()
                    self.assertFalse(at.exception)
                    self.assertEqual(at.get('iframe')[0].proto.srcdoc,html)
                    self.assertEqual(iframe.call_args.kwargs['width'],width)

    def test_flow_preview_widths_reuse_html_without_loading_flow_snapshots(self):
        from streamlit.testing.v1 import AppTest
        from crm_campaign_html import EmailHTML
        script='''
import streamlit as st
from crm_html_workspace import flow_preview
from tests.test_crm_campaign_sections import sectioned
from crm_campaign_content import settings
from tests.test_crm_resend_marketing import ENV
flow_preview(st.session_state.setdefault('doc',sectioned()),settings(ENV),'flow_fixture_')
'''
        with patch('crm_store.Store.q',side_effect=AssertionError('Preview must not reload flows')):
            at=AppTest.from_string(script).run()
            self.assertFalse(at.exception)
            html=at.get('iframe')[0].proto.srcdoc
            with patch.object(EmailHTML,'feed',side_effect=AssertionError('Viewport must reuse HTML')):
                for width in (430,390,375,320,600):
                    at.selectbox(key='flow_fixture_width').set_value(width).run()
                    self.assertFalse(at.exception)
                    self.assertEqual(at.get('iframe')[0].proto.srcdoc,html)
                at.selectbox(key='flow_fixture_display').set_value('Plain text').run()
                self.assertFalse(at.exception)
                self.assertTrue(at.text_area[0].value)


if __name__=='__main__':unittest.main()
