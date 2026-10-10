"""Immutable routing and accurate empty-progress regressions; no external I/O."""
import unittest
from streamlit.testing.v1 import AppTest

SCRIPT='''
from unittest.mock import Mock,patch
import streamlit as st
from crm_campaign_page import campaign_workspace
from crm_campaign_progress import summarize
from crm_store import StoreUnavailable
from tests.test_crm import ADMIN
identity='00000000-0000-0000-0000-000000000071'
st.query_params['campaign']=identity
mode=st.session_state.get('mode','SCHEDULED')
row={'id':identity,'name':'Frozen campaign','status':mode,'counts':{'PENDING':3}}
store=Mock();store.connect=None
store.render_settings.side_effect=AssertionError('Immutable view must not load editor settings')
store.draft.side_effect=AssertionError('Immutable view must not fetch HTML')
store.set_state.side_effect=AssertionError('Immutable view must not write recovery state')
def query(sql,*args,**kwargs):
 if mode=='error':raise StoreUnavailable('offline')
 return [row] if sql.startswith('WITH identities') else row
store.q.side_effect=query
with patch('crm_campaign_page.CampaignStore',return_value=store),patch('crm_campaign_page.restore',side_effect=AssertionError('No draft restoration')):
 campaign_workspace(Mock(),store,Mock(user=ADMIN))
st.session_state['reads']=store.q.call_count
'''

class RoutingTests(unittest.TestCase):
    def test_archived_draft_navigation_keeps_the_original_document(self):
        app=AppTest.from_string('''
from unittest.mock import Mock
import streamlit as st
from crm_campaign_page import continue_campaign_leave
from tests.test_crm_simple_editor import document
identity='00000000-0000-0000-0000-000000000072'
store=Mock();store.q.return_value=None
store.draft.return_value={'id':identity,'name':'Archived draft','document':document(),'version':7,'status':'DRAFT','archived_at':'2026-10-01'}
st.session_state['campaign_pending_open']=identity
continue_campaign_leave(store,lambda _:None,rerun=False)
''').run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['campaign_editor']['name'],'Archived draft')
        self.assertEqual(app.session_state['campaign_editor']['version'],7)
        self.assertEqual(app.session_state['campaign_editor']['archived_at'],'2026-10-01')
        self.assertTrue(app.session_state['campaign_editor']['document']['content'])
    def test_published_and_preparing_use_only_metadata_and_progress(self):
        for mode in ('SCHEDULED','PREPARING','SENT','FAILED'):
            with self.subTest(mode=mode):
                app=AppTest.from_string(SCRIPT);app.session_state['mode']=mode;app.run()
                self.assertFalse(app.exception)
                self.assertEqual(app.session_state['reads'],2)
                self.assertEqual(sum(b.label=='← Campaigns' for b in app.button),1)
                self.assertNotIn('campaign_editor',app.session_state)
                self.assertNotIn('campaign_recovery_context',app.session_state)
    def test_database_failure_never_creates_replacement_draft(self):
        app=AppTest.from_string(SCRIPT);app.session_state['mode']='error';app.run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.error),1)
        self.assertNotIn('campaign_editor',app.session_state)
    def test_empty_complete_has_no_progressbar(self):
        app=AppTest.from_string('''
import streamlit as st
from crm_campaign_progress import summarize
from crm_campaign_progress_ui import status_content
status_content(None,'fixture',summarize({'status':'SENT','counts':{}}))
''').run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.get('progress')),0)

if __name__=='__main__':unittest.main()
