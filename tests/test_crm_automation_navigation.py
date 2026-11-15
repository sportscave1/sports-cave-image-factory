"""Editor route isolation and request reuse without any production services."""
from copy import deepcopy
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock,Mock,patch
from crm_automation_definition import FORMAT,new_flow
from crm_automation_store import AutomationStore

from tests.test_crm import ADMIN

ID='00000000-0000-0000-0000-000000000001'

class NavigationTests(TestCase):
    def test_editor_route_does_not_mount_or_read_overview_and_retains_cache(self):
        from crm_automation_ui import workspace
        from inspect import unwrap
        workspace=unwrap(workspace)
        cache={'cached':object()}
        state={'automation_selected':ID,'automation_home_state':cache}
        with patch('crm_automation_ui.st',MagicMock(session_state=state,query_params={})),patch('crm_automation_ui.AutomationStore') as factory,patch('crm_automation_ui.home') as home,patch('crm_automation_ui.editor_dialog') as editor:
            workspace(Mock(),Mock(),SimpleNamespace(user=ADMIN))
        home.assert_not_called();factory.return_value.get.assert_not_called()
        editor.assert_called_once();self.assertIs(state['automation_home_state'],cache)

    def test_normalized_record_and_selected_draft_share_read_without_mutation(self):
        row={'id':ID,'name':'Original','status':'DRAFT','config':{'format':FORMAT,'revision':1,'published_version':0,'draft':new_flow('welcome')}}
        original=deepcopy(row);store=AutomationStore(Mock());store.get=Mock(return_value=row)
        loaded=store.get('automations',ID)
        flow=store.flow(ID,row=loaded);store.step_id=flow['config']['draft']['emails'][0]['step_id']
        draft=store.draft(ID,row=flow)
        draft['document']['content']['subject']='Local edit'
        store.get.assert_called_once();self.assertEqual(row,original)
        # Independent fragment reruns still read fresh server state.
        store.flow(ID);self.assertEqual(store.get.call_count,2)

    def test_wrong_record_is_rejected(self):
        store=AutomationStore(Mock())
        with self.assertRaises(ValueError):store.flow(ID,row={'id':'different'})

    def test_icons_have_intrinsic_dimensions_even_without_stylesheet(self):
        from crm_automation_home import icon
        import inspect
        source=inspect.getsource(icon)
        self.assertIn('width="21" height="21"',source)
