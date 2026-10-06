"""Actual read-cache/UI reducer with safe fabricated background responses."""
from concurrent.futures import Future
from copy import deepcopy
from datetime import timedelta
from time import sleep
import unittest
from unittest.mock import Mock,patch
import streamlit as st
import crm_automation_analytics_ui as analytics
import crm_checkout_enrollment_ui as ui
from crm_logic import now
from crm_checkout_timing_ui import time_to_send


class ProgressTests(unittest.TestCase):
    def test_ack_poll_patch_schedule_then_stop_without_full_reload(self):
        session={};store=Mock();store.connect='safe-fixture';row={'id':'fixture'}
        records=[{'checkout_key':'chosen','sends':[]},{'checkout_key':'unselected','sends':[]}]
        saved=Future();calls=[]
        result={'checkout_key':'chosen','state':'QUEUED','result':'Adding…','requested_at':now().isoformat()}
        def fetch(*args):
            calls.append(args)
            return [{'checkout_key':'chosen','request':dict(result,state='DONE',result='Added to flow'),
                     'enrollment_id':'fixture-enrolled','flow_status':'ACTIVE','current_step':0,
                     'next_due_at':now()+timedelta(minutes=58),'steps':[{}]}]
        with patch.object(st,'session_state',session),patch.object(ui,'submit',return_value=saved),patch.object(ui,'read_requests',side_effect=fetch):
            ui.begin(store,{},'fixture',['chosen'],'slot')
            states,busy=ui.progress(store,row,records,'slot')
            self.assertEqual(states['chosen']['result'],'Adding…');self.assertEqual(busy,{'chosen'})
            self.assertEqual(calls,[])
            saved.set_result([result])
            for _ in range(20):
                states,busy=ui.progress(store,row,records,'slot')
                if not busy:break
                sleep(.01)
            self.assertFalse(busy);self.assertEqual(states['chosen']['result'],'Added to flow')
            self.assertEqual(time_to_send(records[0]),'58m remaining')
            self.assertEqual(records[1],{'checkout_key':'unselected','sends':[]})
            count=len(calls)
            for _ in range(5):ui.progress(store,row,records,'slot')
            self.assertEqual(len(calls),count)
            store.q.assert_not_called() # only the one targeted mocked read, no full reload

    def test_save_failure_is_visible_and_does_not_claim_enrollment(self):
        session={};saved=Future();saved.set_exception(RuntimeError('secret-provider-details'))
        store=Mock();store.connect='fixture'
        with patch.object(st,'session_state',session),patch.object(ui,'submit',return_value=saved):
            ui.begin(store,{},'fixture',['chosen'],'slot')
            states,busy=ui.progress(store,{'id':'fixture'},[{'checkout_key':'chosen'}],'slot')
            self.assertFalse(busy);self.assertEqual(states['chosen']['state'],'FAILED')
            self.assertNotIn('secret',str(states))

    def test_reopen_restores_durable_pending_request(self):
        session={};store=Mock();store.connect='fixture'
        value={'state':'CHECKING','result':'Checking eligibility…','requested_at':now().isoformat()}
        record={'checkout_key':'chosen','enrollment_request':value}
        with patch.object(st,'session_state',session),patch.object(analytics,'read',return_value=(None,'LOADING')):
            states,busy=ui.progress(store,{'id':'fixture'},[deepcopy(record)],'slot')
            self.assertEqual(busy,{'chosen'});self.assertEqual(states['chosen'],value)


if __name__=='__main__':unittest.main()
