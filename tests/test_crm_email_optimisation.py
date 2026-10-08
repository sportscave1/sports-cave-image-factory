"""Email-only cache, navigation and snapshot correctness."""
from copy import deepcopy
from concurrent.futures import Future
from unittest import TestCase
from unittest.mock import Mock,MagicMock,patch
from crm_campaign_home_data import invalidate_after_save
from crm_preview_cache import preview
from tests.test_crm_simple_editor import document
from tests.test_crm_send_flow import CFG

class EmailOptimisationTests(TestCase):
    def test_recovery_acknowledged_in_same_render_without_rerun(self):
        from crm_recovery_ui import recovery_bridge
        editor={'id':'one','version':1,'name':'Original','document':document()}
        updated=deepcopy(editor);updated.update(name='Saved',version=2)
        event={'event':'checkpoint','record':{'editor':editor}}
        state={'key-recovery':event}
        with patch('crm_recovery_ui.st',MagicMock(session_state=state)) as ui, \
             patch('crm_recovery_ui.browser_checkpoint',return_value=updated) as save, \
             patch('crm_recovery_ui.preference_key',return_value='scope'), \
             patch('crm_recovery_ui.components.declare_component'), \
             patch('crm_recovery_ui.render_component') as render:
            recovery_bridge(Mock(),{},editor,'key-')
            self.assertEqual(render.call_args.kwargs['ack'],'checkpoint')
            self.assertEqual(render.call_args.kwargs['editor']['name'],'Saved')
            self.assertTrue(render.call_args.kwargs['confirmed'])
            recovery_bridge(Mock(),{},editor,'key-')
            save.assert_called_once();ui.rerun.assert_not_called()

    def test_section_name_preserves_preview_but_content_change_invalidates(self):
        from crm_middle_sections import middle_sections,commit_middle
        from crm_campaign_content import render_campaign
        doc=document();commit_middle(doc,middle_sections(doc));state={}
        with patch('crm_preview_cache.render_campaign',wraps=render_campaign) as render:
            original=preview(state,doc,CFG)
            doc['middle_sections'][0]['name']='Hero / heading'
            self.assertEqual(preview(state,doc,CFG),original);self.assertEqual(render.call_count,1)
            doc['middle_sections'][0]['html']='<p>New design</p>'
            commit_middle(doc,doc['middle_sections'])
            self.assertNotEqual(preview(state,doc,CFG),original);self.assertEqual(render.call_count,2)
        self.assertEqual(doc['middle_sections'][0]['name'],'Hero / heading')

    def test_saved_draft_invalidates_rows_not_delivery_or_attribution(self):
        futures={kind:Future() for kind in ('counts','table','delivery','attribution')}
        state={'campaign_home_cache':{(None,(k,)):(0,f) for k,f in futures.items()},'campaign_home_window':(0,'same window')}
        previous={'id':'one','version':1}
        invalidate_after_save(state,previous,previous)
        self.assertEqual(len(state['campaign_home_cache']),4)
        invalidate_after_save(state,previous,{'id':'one','version':2})
        self.assertTrue(futures['table'].cancelled());self.assertTrue(futures['counts'].cancelled())
        self.assertFalse(futures['delivery'].cancelled());self.assertFalse(futures['attribution'].cancelled())
        self.assertEqual(state['campaign_home_window'],(0,'same window'))

    def test_navigation_keeps_valid_overview_cache(self):
        from crm_campaign_home import request_open,return_home
        state={'campaign_home_cache':{'sentinel':object()}};cached=state['campaign_home_cache']
        with patch('crm_campaign_home.st',MagicMock(session_state=state,query_params={})):
            request_open('one');return_home()
        self.assertIs(state['campaign_home_cache'],cached)

    def test_in_route_navigation_does_not_require_second_app_rerun(self):
        from crm_campaign_page import continue_campaign_leave
        state={'campaign_pending_open':'one'};store=Mock()
        with patch('crm_campaign_page.st',MagicMock(session_state=state)) as ui,patch('crm_campaign_page.open_editor') as opened:
            continue_campaign_leave(store,Mock(),rerun=False)
        opened.assert_called_once_with(store.draft.return_value);ui.rerun.assert_not_called()

    def test_preview_with_saved_defaults_never_reloads_master(self):
        from streamlit.testing.v1 import AppTest
        script='''
import streamlit as st
from unittest.mock import Mock
from crm_html_workspace import composer_canvas
from tests.test_crm_simple_editor import document
from tests.test_crm_send_flow import CFG
doc=document();doc['html_sections']={'header':'<p>Saved header</p>','footer':'<a href="{{UNSUBSCRIBE_URL}}">Unsubscribe</a>'}
store=Mock();store.email_mode='campaign';store.default_sections.side_effect=AssertionError('No master read')
composer_canvas(doc,CFG,'cached-',store)
'''
        app=AppTest.from_string(script).run();self.assertFalse(app.exception)
        self.assertIn('Saved header',app.get('iframe')[0].proto.srcdoc)
