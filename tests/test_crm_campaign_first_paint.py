"""Offline render priority, selection, and dirty-state regressions."""
from pathlib import Path
import unittest
from streamlit.testing.v1 import AppTest

from tests.test_crm_campaign_loading import SCRIPT

ROOT=Path(__file__).resolve().parents[1]
IDENTITY='00000000-0000-0000-0000-000000000123'

ORDER_SCRIPT='''
from unittest.mock import Mock,patch
from time import perf_counter,sleep
import streamlit as st
from crm_campaign_page import campaign_workspace
drafts=Mock();actions=Mock();actions.user={}
st.session_state['campaign_view']='CAMPAIGN_EDITOR'
events=[];started=perf_counter()
def editor(*args,**kwargs):
 events.append(('editor',perf_counter()-started))
 st.caption('Selected composer')
def history(*args):
 events.append(('history_start',perf_counter()-started))
 sleep(.05)
 st.caption('Campaign history')
 events.append(('history_end',perf_counter()-started))
with patch('crm_campaign_page.CampaignStore',return_value=drafts), patch('crm_campaign_page._selected_campaign',side_effect=editor), patch('crm_campaign_page.recent_campaigns',side_effect=history), patch('crm_tracking_health.control',side_effect=AssertionError('Tracking UI removed')), patch('crm_tracking_health.verify',side_effect=AssertionError('No verification')):
 campaign_workspace(Mock(),Mock(),actions)
st.session_state['events']=events
'''

SELECTION_SCRIPT='''
from copy import deepcopy
from contextlib import ExitStack
from unittest.mock import Mock,patch
import streamlit as st
from crm_campaign_page import campaign_workspace,open_editor
from crm_campaign_content import settings
from tests.test_crm_simple_editor import document
from tests.test_crm import ADMIN
target={'id':'00000000-0000-0000-0000-000000000123','version':1,'name':'Restored campaign','status':'DRAFT','archived_at':None,'document':document()}
old={**deepcopy(target),'id':'00000000-0000-0000-0000-000000000456','name':'Old campaign'}
mode=st.session_state['mode']
st.session_state['campaign_view']='CAMPAIGN_EDITOR'
if 'initialized' not in st.session_state:
 st.session_state['initialized']=True
 if mode in ('switch','dirty_switch','url_switch','dirty_url','session'):
  st.session_state['campaign_editor']=deepcopy(old)
  st.session_state['campaign_saved']=deepcopy(old)
 if mode in ('switch','dirty_switch'):st.session_state['campaign_pending_open']=target['id']
 if mode in ('url','url_switch','dirty_url'):st.query_params['campaign']=target['id']
 if mode in ('dirty_switch','dirty_url'):st.session_state['campaign_editor']['name']='Unsaved changes'
drafts=Mock();drafts.render_settings.return_value=settings({})
drafts.setting.return_value={'value':{'smart_hours':16}}
drafts.q.return_value=None;drafts.draft.return_value=target
actions=Mock();actions.user=ADMIN
def capture_form(*args):st.caption('Composer: '+args[3]['name'])
with ExitStack() as stack:
 stack.enter_context(patch('crm_campaign_page.CampaignStore',return_value=drafts))
 restore=stack.enter_context(patch('crm_campaign_page.restore',return_value=None if mode=='new' else target))
 stack.enter_context(patch('crm_campaign_page.activate'))
 stack.enter_context(patch('crm_campaign_leave_ui.flush_current',return_value=True))
 stack.enter_context(patch('crm_campaign_page.recent_campaigns',side_effect=lambda *a:st.caption('History')))
 stack.enter_context(patch('crm_campaign_page.composer_form',side_effect=capture_form))
 stack.enter_context(patch('crm_campaign_send_ui.test_control'))
 stack.enter_context(patch('crm_campaign_send_ui.send_control'))
 stack.enter_context(patch('crm_tracking_health.control',side_effect=AssertionError('No tracking UI')))
 stack.enter_context(patch('crm_tracking_health.verify',side_effect=AssertionError('No verification')))
 stack.enter_context(patch('requests.sessions.Session.request',side_effect=AssertionError('No HTTP')))
 campaign_workspace(Mock(),Mock(),actions)
 st.session_state['restore_calls']=restore.call_count
 st.session_state['sending_calls']=drafts.setting.call_count
 st.session_state['delivery_calls']=len([c for c in drafts.q.call_args_list if c.args[0].startswith('SELECT * FROM crm_campaigns')])
'''


class FirstPaintTests(unittest.TestCase):
    def test_editor_is_emitted_before_delayed_history(self):
        app=AppTest.from_string(ORDER_SCRIPT).run()
        self.assertFalse(app.exception)
        self.assertEqual([c.value for c in app.caption],['Selected composer'])
        events=app.session_state['events']
        self.assertEqual([e[0] for e in events],['editor'])

    def test_real_composer_precedes_history_and_has_no_tracking_ui(self):
        app=AppTest.from_string(SCRIPT).run()
        self.assertFalse(app.exception)
        captions=[caption.value for caption in app.caption]
        self.assertIn('Preview fixture',captions)
        self.assertNotIn('Campaign history fixture',captions)
        self.assertEqual([t.label for t in app.tabs],['Settings','Editor','Templates'])
        for label in ('Save draft','Send test','Send now'):
            self.assertIn(label,[b.label for b in app.button])

    def test_new_restore_session_and_switch_paths(self):
        for mode,name in (('new','Untitled campaign'),('restore','Restored campaign'),
                          ('url','Restored campaign'),('session','Old campaign'),
                          ('switch','Restored campaign'),('url_switch','Restored campaign')):
            with self.subTest(mode=mode):
                app=AppTest.from_string(SELECTION_SCRIPT)
                app.session_state['mode']=mode;app.run()
                self.assertFalse(app.exception)
                self.assertEqual([c.value for c in app.caption if c.value.startswith(('Composer:','History'))],
                                 ['Composer: '+name])
                self.assertEqual(app.session_state['campaign_editor']['name'],name)
                if mode=='session':
                    self.assertEqual(app.session_state['restore_calls'],0)
                    self.assertEqual(app.session_state['sending_calls'],0)
                    self.assertEqual(app.session_state['delivery_calls'],1)
                if mode=='new':self.assertEqual(app.session_state['sending_calls'],1)

    def test_dirty_switch_and_url_switch_protect_unsaved_edits(self):
        for mode in ('dirty_switch','dirty_url'):
            with self.subTest(mode=mode):
                app=AppTest.from_string(SELECTION_SCRIPT)
                app.session_state['mode']=mode;app.run()
                self.assertFalse(app.exception)
                self.assertEqual(app.session_state['campaign_editor']['name'],'Unsaved changes')
                self.assertIn('Save draft and leave',[b.label for b in app.button])
                self.assertNotIn('History',[c.value for c in app.caption])
                app.button[ next(i for i,b in enumerate(app.button) if b.label=='Discard and leave') ].click().run()
                self.assertFalse(app.exception)
                self.assertEqual(app.session_state['campaign_editor']['name'],'Restored campaign')

    def test_dirty_url_cancel_keeps_current_campaign(self):
        app=AppTest.from_string(SELECTION_SCRIPT)
        app.session_state['mode']='dirty_url';app.run()
        next(b for b in app.button if b.label=='Cancel').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['campaign_editor']['name'],'Unsaved changes')
        self.assertEqual(app.query_params['campaign'] if isinstance(app.query_params['campaign'],list) else [app.query_params['campaign']],['00000000-0000-0000-0000-000000000456'])

    def test_dirty_switch_save_and_leave_uses_existing_flow(self):
        app=AppTest.from_string(SELECTION_SCRIPT)
        app.session_state['mode']='dirty_switch';app.run()
        next(b for b in app.button if b.label=='Save draft and leave').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['campaign_editor']['name'],'Restored campaign')

    def test_campaign_page_has_no_tracking_wiring_and_backend_is_available(self):
        import crm_tracking_health
        source=(ROOT/'crm_campaign_page.py').read_text(encoding='utf-8')
        self.assertNotIn('crm_tracking_health',source)
        for name in ('verify','observations','control'):
            self.assertTrue(callable(getattr(crm_tracking_health,name)))


if __name__=='__main__':unittest.main()

