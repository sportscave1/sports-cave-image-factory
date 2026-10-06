import unittest,time
from types import SimpleNamespace
from concurrent.futures import Future
from unittest.mock import Mock,MagicMock,patch
from crm_automation_home_read import identity_read
import crm_automation_read_cache as cache

class LoadingTests(unittest.TestCase):
    def test_cold_identity_is_direct_normalized_and_bounded(self):
        store=MagicMock();store.connect=None
        connection=store.db.return_value.__enter__.return_value
        connection.execute.return_value.fetchall.return_value=[{'id':42,'updated_at':None,'publication':None}]
        from crm_automation_home_data import identities
        result,phase=identity_read({},store,('identities',0),lambda bounded:identities(bounded))
        self.assertEqual((result[0]['id'],result[0]['publication'],phase),('42',{},'READY'))
        statements=[c.args[0] for c in connection.execute.call_args_list]
        self.assertIn('1500ms',statements[0]);self.assertIn('500ms',statements[1])
        self.assertEqual(len(statements),3)
    def test_empty_is_ready_not_loading(self):
        store=SimpleNamespace(connect=None)
        self.assertEqual(identity_read({},store,('identities',0),lambda _:[]),([], 'READY'))
    def test_error_keeps_stale_rows(self):
        store=SimpleNamespace(connect=None);key=('identities',0);state={}
        identity_read(state,store,key,lambda _:[{'id':'a'}])
        state['automation_identity_cache'][(None,key)]['at']=0
        def fail(_):raise TimeoutError()
        rows,phase=identity_read(state,store,key,fail)
        self.assertEqual((rows[0]['id'],phase),('a','TIMED_OUT'))
    def test_pending_watchdog_is_terminal_until_retry(self):
        store=SimpleNamespace(connect=None);key=('activity',None);f=Future();identity=(None,key)
        state={'campaign_home_cache':{identity:(None,f)},'automation_read_started':{identity:time.monotonic()-21}}
        self.assertEqual(cache.resolve(state,store,key,f),(None,'TIMED_OUT'))
        load=Mock();cache.job(state,store,key,load);load.assert_not_called()
    def test_capacity_denial_cannot_stay_unresolved(self):
        store=SimpleNamespace(connect=None);key=('counts',None);identity=(None,key)
        state={'automation_read_started':{identity:time.monotonic()-21}}
        self.assertEqual(cache.resolve(state,store,key,None),(None,'TIMED_OUT'))
    def test_background_error_is_terminal_not_loading(self):
        store=SimpleNamespace(connect=None);key=('delivery',None);f=Future();f.set_exception(ValueError('private'))
        state={'campaign_home_cache':{(None,key):(None,f)}}
        self.assertEqual(cache.resolve(state,store,key,f),(None,'ERROR'))
    def test_visible_menu_gate_ignores_hidden_topbar_listbox(self):
        import inspect,crm_automation_home as home
        source=inspect.getsource(home.arm_section)
        self.assertIn('getClientRects().length',source)
        self.assertNotIn('document.hidden||document.querySelector(',source)
    def test_publish_handoff_does_not_mutate_wrapped_metrics(self):
        from crm_automation_home import accepted_publication
        rows=[[{'id':'a'}]]
        state={'campaign_home_resolved':{(None,('table',0)):rows}}
        with patch('crm_automation_ui.home_state',return_value=state):
            accepted_publication({'id':'j','automation_id':'a','revision':1,'publication_version':1,'state':'QUEUED'})
        self.assertEqual(rows,[[{'id':'a'}]])
        self.assertEqual(state['publish_handoff']['publication']['state'],'PUBLISHING')
    def test_older_status_result_cannot_settle_new_job(self):
        from crm_automation_home import refresh_publications
        row={'id':'a','publication':{'job_id':'new','state':'PUBLISHING'}}
        with patch('crm_automation_ui.home_state',return_value={}):
            refresh_publications(Mock(),[row],{},updates=[{'id':'a','publication':{'job_id':'old','state':'LIVE'}}])
        self.assertEqual(row['publication']['state'],'PUBLISHING')

if __name__=='__main__':unittest.main()
