"""Inline controls preserve backend authority and consume events once."""
from copy import deepcopy
from unittest.mock import Mock,patch
import unittest
from crm_automation_definition import new_flow
from crm_flow_inline import step_state,status_options,status_action,save_rename,save_delay
from crm_store import StoreUnavailable


def row():
    flow=new_flow('abandoned')
    return dict(id='fixture',name='Original name',status='DRAFT',steps=[],updated_at='now',
                config=dict(draft=flow,revision=7,published_version=0))


class InlineTests(unittest.TestCase):
    def test_live_requires_published_step_in_active_flow(self):
        r=row();s=r['config']['draft']['emails'][0]
        for enabled in (True,False):
            s['enabled']=enabled
            self.assertEqual(step_state(r,s),'DRAFT')
        r['config']['published_version']=2;r['steps']=[deepcopy(s)];r['steps'][0]['enabled']=True
        r['status']='ACTIVE';self.assertEqual(step_state(r,s),'LIVE')
        r['status']='PAUSED';self.assertEqual(step_state(r,s),'PAUSED')
        r['config']['archived_at']='then';self.assertEqual(step_state(r,s),'DRAFT')
        self.assertEqual(status_options(r,s),['DRAFT'])

    def test_new_step_in_live_flow_is_still_draft_and_locks_remove_publish_resume(self):
        r=row();s=r['config']['draft']['emails'][0];r['status']='ACTIVE';r['config']['published_version']=1
        self.assertEqual(step_state(r,s),'DRAFT')
        r['config']['draft']['lifecycle_version']=1
        self.assertNotIn('Publish flow',status_options(r,s))
        r['status']='PAUSED';self.assertNotIn('Resume flow',status_options(r,s))

    def test_failed_status_action_is_consumed_without_replay(self):
        r=row();s=r['config']['draft']['emails'][0];store=Mock();store.flow.return_value=r
        store.request_publish.side_effect=ValueError('Activation locked')
        state={'action':'Publish flow'}
        with patch('crm_flow_inline.st') as ui,patch('crm_campaign_recovery.flush_current',return_value=True):
            ui.session_state=state
            status_action(store,{},r,s,'action');status_action(store,{},r,s,'action')
        store.request_publish.assert_called_once_with({},'fixture',7)
        self.assertEqual(state['action'],'DRAFT');self.assertEqual(state['flow-inline-error'],'Activation locked')
        store.lifecycle.assert_not_called()

    def test_delay_preserves_all_other_fields_and_uses_existing_save(self):
        r=row();original=deepcopy(r);s=r['config']['draft']['emails'][0]
        store=Mock();store.flow.return_value=deepcopy(r)
        store.flow.return_value.update(name='Renamed in toolbar')
        store.flow.return_value['config']['revision']=8
        state={'amount':3,'unit':'Days'}
        with patch('crm_flow_inline.st') as ui,patch('crm_flow_builder.save',return_value=True) as save:
            ui.session_state=state;save_delay(store,{},r,s,'amount','unit')
        saved=save.call_args.args[3]
        self.assertEqual(saved['emails'][0]['delay_seconds'],259200)
        saved['emails'][0]['delay_seconds']=s['delay_seconds']
        self.assertEqual(saved,r['config']['draft']);self.assertEqual(r,original)
        self.assertEqual(save.call_args.kwargs,{'rerun':False})
        self.assertEqual(save.call_args.args[2]['name'],'Renamed in toolbar')
        self.assertEqual(save.call_args.args[2]['config']['revision'],8)

    def test_failed_delay_restores_input_and_retains_persisted_settings(self):
        r=row();s=r['config']['draft']['emails'][0];state={'amount':99999,'unit':'Days'}
        store=Mock();store.flow.return_value=r
        with patch('crm_flow_inline.st') as ui,patch('crm_flow_builder.save',side_effect=ValueError('Too long')) as save:
            ui.session_state=state;save_delay(store,{},r,s,'amount','unit');save_delay(store,{},r,s,'amount','unit')
        self.assertEqual(state['amount'],0);self.assertEqual(state['unit'],'Minutes');save.assert_called_once()

    def test_replayed_delay_is_a_noop_and_concurrent_delay_is_not_overwritten(self):
        r=row();s=r['config']['draft']['emails'][0];store=Mock()
        fresh=deepcopy(r);store.flow.return_value=fresh
        state={'amount':3,'unit':'Days'}
        with patch('crm_flow_inline.st') as ui,patch('crm_flow_builder.save') as save:
            ui.session_state=state
            fresh['config']['draft']['emails'][0]['delay_seconds']=259200
            save_delay(store,{},r,s,'amount','unit');save.assert_not_called()
            fresh['config']['draft']['emails'][0]['delay_seconds']=900
            save_delay(store,{},r,s,'amount','unit');save.assert_not_called()
        self.assertEqual(fresh['config']['draft']['emails'][0]['delay_seconds'],900)
        self.assertIn('changed',state['flow-inline-error'])

    def test_rename_validation_noop_failed_save_and_success(self):
        r=row();store=Mock();state={'flow-rename':r,'flow-rename-input':'   '}
        with patch('crm_flow_inline.st') as ui,patch('crm_automation_ui.changed'):
            ui.session_state=state;save_rename(store,{},r['id']);store.save_flow.assert_not_called()
            state['flow-rename-input']='New name';store.save_flow.side_effect=StoreUnavailable('Retry')
            save_rename(store,{},r['id']);self.assertEqual(r['name'],'Original name');self.assertIn('flow-rename',state)
            store.save_flow.side_effect=None;save_rename(store,{},r['id'])
            self.assertNotIn('flow-rename',state)
            store.save_flow.assert_called_with({},r['id'],'New name',r['config']['draft'],7)
