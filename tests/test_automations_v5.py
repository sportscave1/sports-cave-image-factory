"""Behavioural freshness, URL restoration, and failure bounds; no live I/O."""
from copy import deepcopy
from concurrent.futures import Future
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, Mock, patch
from crm_automation_store import AutomationStore
from crm_automation_definition import FORMAT,new_flow
from crm_automation_toolbar import definition
from tests.test_crm import ADMIN,WORKER
ID='00000000-0000-0000-0000-000000000001'
class V5Tests(TestCase):
    def test_metrics_render_when_all_stage_menus_are_closed(self):
        from crm_flow_page import step_performance
        slots={'one':Mock(),'two':Mock()}
        with patch('crm_flow_page.st') as ui,patch('crm_flow_page.read',return_value=([], 'READY')):
            ui.session_state={};ui.button.return_value=False
            step_performance(Mock(),ID,slots,{})
        for slot in slots.values():self.assertIn('data-phase="READY"',slot.html.call_args.args[0])
    def test_warm_display_row_reuses_only_after_fresh_marker(self):
        from crm_automation_ui import current_display_row
        row=dict(id=ID,config=dict(format=FORMAT,draft=new_flow('welcome')),updated_at=1)
        state={'_automation_toolbar_definition':((ID,1),row)};store=Mock();store.q.return_value={'updated_at':1}
        self.assertIs(current_display_row(store,state,ID),row);store.get.assert_not_called()
        store.q.return_value={'updated_at':2};current_display_row(store,state,ID);store.get.assert_called_once()
        store.q.return_value=None;current_display_row(store,state,ID);self.assertEqual(store.get.call_count,2)
    def test_fragment_permission_gate_rejects_denied_actor(self):
        from crm_automation_ui import workspace
        from inspect import unwrap
        with patch('crm_automation_ui.st',MagicMock(session_state={},query_params={})):
            with self.assertRaises(PermissionError):unwrap(workspace)(Mock(),Mock(),SimpleNamespace(user=WORKER))
    def test_parent_snapshot_reused_only_during_render(self):
        row=dict(id=ID,config=dict(format=FORMAT,draft=new_flow('welcome')),updated_at=1)
        store=AutomationStore(Mock());store.get=Mock(return_value=row);store.q=Mock(return_value={'updated_at':1})
        state={}
        with store.display_read_scope():
            store.flow(ID,row=row)
            self.assertEqual(definition(store,state,ID),store.flow(ID,row=row))
            store.q.assert_not_called();store.get.assert_not_called()
        definition(store,state,ID)
        store.q.assert_called_once();store.get.assert_called_once()
    def test_database_operation_invalidates_render_snapshot(self):
        connection=MagicMock();store=AutomationStore(lambda:connection)
        row=dict(id=ID,config=dict(format=FORMAT,draft=new_flow('welcome')))
        with store.display_read_scope():
            store.flow(ID,row=row);self.assertIsNotNone(store.display_snapshot(ID))
            with store.db():pass
            self.assertIsNone(store.display_snapshot(ID))
    def test_url_history_supersedes_session_and_saves_before_switch(self):
        from crm_automation_ui import workspace
        from inspect import unwrap
        workspace=unwrap(workspace)
        for target in (None,'second'):
            state={'automation_selected':ID,'_automation_route_observed':ID,'automation_editor':{'name':'dirty'},'automation_template_view':('old view',),'flow-operational-diagnostics':ID}
            query={'automation':target} if target else {}
            fake=MagicMock(session_state=state,query_params=query)
            fake.text_input.side_effect=lambda *a,**kw:(target or '') if kw['key']=='automation' else ''
            with patch('crm_automation_ui.st',fake),patch('crm_automation_ui.home') as home,patch('crm_automation_ui.editor_dialog') as editor,patch('crm_campaign_recovery.flush_current',return_value=True) as flush:
                workspace(Mock(),Mock(),SimpleNamespace(user=ADMIN))
            flush.assert_called_once_with(force=True)
            self.assertNotIn('automation_editor',state)
            self.assertNotIn('automation_template_view',state)
            self.assertNotIn('flow-operational-diagnostics',state)
            self.assertEqual(state['_automation_route_observed'],target)
            self.assertEqual(editor.call_count,bool(target));self.assertEqual(home.call_count,not bool(target))
    def test_failed_flush_restores_url_and_retains_edits(self):
        from crm_automation_ui import workspace
        from inspect import unwrap
        workspace=unwrap(workspace)
        draft={'name':'dirty'};state={'automation_selected':ID,'_automation_route_observed':ID,'automation_editor':draft};query={'automation':'second'}
        fake=MagicMock(session_state=state,query_params=query)
        fake.text_input.side_effect=lambda *a,**kw:'second' if kw['key']=='automation' else '';fake.rerun.side_effect=RuntimeError('rerun')
        with patch('crm_automation_ui.st',fake),patch('crm_automation_ui.editor_dialog'),patch('crm_campaign_recovery.flush_current',return_value=False):
            with self.assertRaisesRegex(RuntimeError,'rerun'):workspace(Mock(),Mock(),SimpleNamespace(user=ADMIN))
        self.assertEqual(state['_automation_route_restore'],(ID,None));self.assertIs(state['automation_editor'],draft)
        fake.text_input.side_effect=lambda *a,**kw:state.get(kw['key'],'')
        with patch('crm_automation_ui.st',fake),patch('crm_automation_ui.editor_dialog'),patch('crm_campaign_recovery.flush_current') as flush:
            workspace(Mock(),Mock(),SimpleNamespace(user=ADMIN))
        flush.assert_not_called();self.assertEqual(state['automation'],ID)
    def test_optional_analytics_deadline_is_terminal(self):
        from crm_automation_read_cache import resolve
        store=Mock();key=('analytics-steps',ID);token=(store.connect,key);future=Future()
        state={'campaign_home_cache':{token:(None,future)},'automation_read_started':{token:0}}
        with patch('crm_automation_read_cache.monotonic',return_value=21):
            self.assertEqual(resolve(state,store,key,future),(None,'TIMED_OUT'))
        self.assertTrue(future.cancelled())
