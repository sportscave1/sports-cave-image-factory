"""Selected-email publication against disposable PostgreSQL; external I/O forbidden."""
from copy import deepcopy
import os
import unittest
from unittest.mock import patch,Mock
from tests import test_crm_automation_publication as existing
from tests.test_crm import ADMIN
from crm_automation_definition import email_step
from crm_automation_publish_state import has_changes,email_has_changes
from crm_flow_inline import step_state
from crm_automation_publish_confirm import completed


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class EmailPublicationTests(unittest.TestCase):
    setUp=existing.PublicationTests.setUp
    cleanup=existing.PublicationTests.cleanup
    draft=existing.PublicationTests.draft
    state=existing.PublicationTests.state
    run_job=existing.PublicationTests.run_job

    def three(self,kind='post_purchase'):
        row=self.draft(kind);flow=deepcopy(row['config']['draft'])
        flow['emails'] += [email_step(deepcopy(flow['emails'][0]['document']),86400) for _ in range(2)]
        for i,s in enumerate(flow['emails']):s['document']['content']['subject']='Fixture Email '+str(i+1)
        return self.store.save_flow(ADMIN,row['id'],row['name'],flow,row['config']['revision'])

    def publish_email(self,row,index):
        return self.store.request_publish(ADMIN,row['id'],row['config']['revision'],step_id=row['config']['draft']['emails'][index]['step_id'])

    def test_shared_editor_confirmation_and_navigation_all_five_flows(self):
        from streamlit.testing.v1 import AppTest
        for kind in ('abandoned','welcome','post_purchase','win_back','fulfilled'):
            with self.subTest(kind=kind):
                row=self.three(kind);self.publish_email(row,0);self.run_job();row=self.state(row)
                flow=deepcopy(row['config']['draft'])
                flow['emails'][0]['document']['content']['subject']='Unpublished sibling edit'
                flow['emails'][2]['enabled']=False
                row=self.store.save_flow(ADMIN,row['id'],row['name'],flow,row['config']['revision'])
                selected=flow['emails'][1]['step_id'];original=deepcopy(row['steps'])
                source=f'''
import streamlit as st
from tests.test_crm_send_flow import CFG
from tests.test_crm import ADMIN
from tests.crm_db_fixture import connect
from crm_automation_store import AutomationStore
from crm_automation_toolbar import toolbar
class FixtureStore(AutomationStore):
    def render_settings(self,env=None):return CFG
store=FixtureStore(connect);store.step_id={selected!r}
if '_automation_navigation_email' in st.session_state:
    st.write('Flow overview')
else:
    editor=store.draft({str(row['id'])!r})
    st.session_state['automation_editor']=editor
    st.session_state['automation_saved']=editor.copy()
    toolbar(store,ADMIN,{str(row['id'])!r},editor=editor)
'''
                with patch('crm_campaign_recovery.flush_current',return_value=True),patch('crm_campaign_send_ui.test_control'):
                    app=AppTest.from_string(source,default_timeout=20).run()
                    self.assertFalse(app.exception)
                    self.assertEqual(app.button(key='toolbar-publish').label,'Publish Email')
                    app.button(key='toolbar-publish').click().run()
                    self.assertFalse(app.exception)
                    self.assertEqual(app.session_state['automation-confirm-publication'][2],selected)
                    self.assertTrue(any(x.value=='Publish this email now?' for x in app.markdown))
                    self.assertEqual(app.button(key='automation-publication-confirm').label,'Publish')
                    self.assertEqual(len(app.checkbox),0)
                    app.button(key='automation-publication-confirm').click().run()
                    self.assertFalse(app.exception)
                    queued=self.state(row)
                    self.assertEqual(queued['config']['publication']['step_id'],selected)
                    self.assertNotIn('_automation_navigation_email',app.session_state)
                    self.run_job();app.run()
                    self.assertFalse(app.exception)
                    self.assertEqual(app.session_state['_automation_navigation_email'],'')
                    live=self.state(row)
                    self.assertEqual([step_state(live,s) for s in flow['emails']],['LIVE','LIVE','DISABLED'])
                    self.assertEqual(live['steps'][0],original[0])
                    self.assertEqual(live['config']['draft'],flow)

    def test_individual_scope_rejects_sibling_enable_requests(self):
        row=self.three();flow=row['config']['draft'];flow['emails'][2]['enabled']=False
        row=self.store.save_flow(ADMIN,row['id'],row['name'],flow,row['config']['revision'])
        with self.assertRaisesRegex(ValueError,'whole-flow'):
            self.store.request_publish(ADMIN,row['id'],row['config']['revision'],step_id=flow['emails'][0]['step_id'],enable_ids=[flow['emails'][2]['step_id']])
        self.assertEqual(self.state(row)['steps'],[])

    def test_all_flows_publish_only_email_two_reopen_and_immutable_history(self):
        for kind in ('abandoned','welcome','post_purchase','win_back','fulfilled'):
            with self.subTest(kind=kind):
                row=self.three(kind);self.publish_email(row,0);self.run_job();first=self.state(row)
                original=deepcopy(first['steps'][0]);draft=deepcopy(first['config']['draft'])
                draft['emails'][0]['document']['content']['subject']='Unrelated unfinished edit'
                draft['emails'][2]['document']['content']['subject']=''
                saved=self.store.save_flow(ADMIN,row['id'],row['name'],draft,first['config']['revision'])
                job=self.publish_email(saved,1)
                self.assertEqual(self.publish_email(saved,1)['id'],job['id'])
                with self.assertRaisesRegex(ValueError,'already publishing'):self.publish_email(saved,0)
                self.assertEqual([step_state(self.state(row),s) for s in draft['emails']],['LIVE','DRAFT','DRAFT'])
                self.run_job();live=self.state(row)
                self.assertEqual([step_state(live,s) for s in draft['emails']],['LIVE','LIVE','DRAFT'])
                self.assertEqual(live['steps'][0],original)
                self.assertEqual(live['config']['draft'],draft)
                self.assertEqual(live['steps'][1]['template_version'],2)
                self.assertTrue(self.publish_email(live,1)['unchanged'])
                self.assertFalse(email_has_changes(self.store,live,draft['emails'][1]['step_id']))
                self.assertTrue(has_changes(self.store,live))
                history=self.store.q('SELECT version FROM crm_template_versions WHERE template_id=%s',(original['template_id'],))
                self.assertEqual([r['version'] for r in history],[1])
                # Reopen uses persisted rows, not session state or draft enabled flags.
                from crm_automation_store import AutomationStore
                reopened=AutomationStore(self.store.connect).flow(row['id'])
                self.assertEqual([step_state(reopened,s) for s in draft['emails']],['LIVE','LIVE','DRAFT'])
                self.assertEqual(self.store.q('SELECT count(*) AS n FROM crm_automation_enrollments WHERE automation_id=%s',(row['id'],),True)['n'],0)

    def test_same_revision_can_publish_two_distinct_emails(self):
        row=self.three();one=self.publish_email(row,0);self.run_job()
        two=self.publish_email(row,1);self.assertNotEqual(one['id'],two['id']);self.run_job()
        self.assertEqual(len(self.state(row)['steps']),2)

    def test_paused_failure_and_navigation_are_authoritative(self):
        row=self.three();self.publish_email(row,0);self.run_job();self.store.lifecycle(ADMIN,row['id'],'pause')
        row=self.state(row);draft=deepcopy(row['config']['draft']);job=self.publish_email(row,1)
        waiting={'automation-publication-waiting':{'identity':str(row['id']),'job_id':str(job['id'])}}
        self.assertFalse(completed(self.store,self.state(row),waiting))
        with patch('crm_automation_publication.prepare',side_effect=ValueError('Email tracking failure')):self.run_job()
        failed=self.state(row);self.assertFalse(completed(self.store,failed,waiting));self.assertNotIn('automation-publication-toast',waiting)
        self.assertEqual(failed['config']['draft'],draft);self.assertEqual(failed['status'],'PAUSED')
        self.assertEqual([step_state(failed,s) for s in draft['emails']],['PAUSED','DRAFT','DRAFT'])
        job=self.publish_email(failed,1);waiting['automation-publication-waiting']={'identity':str(row['id']),'job_id':str(job['id'])}
        self.run_job();live=self.state(row)
        self.assertTrue(completed(self.store,live,waiting));self.assertTrue(waiting['automation-publication-toast'])
        self.assertFalse(completed(self.store,live,waiting))
        self.assertEqual([step_state(live,s) for s in draft['emails']],['PAUSED','PAUSED','DRAFT'])

    def test_draft_global_settings_and_other_delays_not_promoted(self):
        row=self.three();self.publish_email(row,0);self.run_job();row=self.state(row)
        flow=deepcopy(row['config']['draft']);flow['reentry_days']=7;flow['emails'][0]['delay_seconds']=300
        row=self.store.save_flow(ADMIN,row['id'],row['name'],flow,row['config']['revision'])
        self.publish_email(row,1);self.run_job();live=self.state(row)
        self.assertEqual(live['config']['published']['reentry_days'],0)
        self.assertEqual(live['steps'][0]['delay_seconds'],0)
        self.assertEqual(live['config']['draft'],flow)

    def test_snapshot_equality_cannot_hide_missing_published_email(self):
        row=self.three();self.store.request_publish(ADMIN,row['id'],row['config']['revision']);self.run_job();row=self.state(row)
        row['steps']=row['steps'][:1]
        self.assertTrue(has_changes(self.store,row))
        self.assertTrue(email_has_changes(self.store,row,row['config']['draft']['emails'][1]['step_id']))

    def test_disabled_draft_is_not_live_and_does_not_enable_itself(self):
        row=self.three();flow=deepcopy(row['config']['draft']);flow['emails'][1]['enabled']=False
        row=self.store.save_flow(ADMIN,row['id'],row['name'],flow,row['config']['revision'])
        self.publish_email(row,0);self.run_job();self.publish_email(self.state(row),1);self.run_job();live=self.state(row)
        self.assertEqual([step_state(live,s) for s in flow['emails']],['LIVE','DISABLED','DRAFT'])
        self.assertEqual(len(live['steps']),1)


class ConfirmationTests(unittest.TestCase):
    def test_scope_titles_share_one_dialog_body(self):
        from crm_automation_publish_confirm import confirm,confirmation_body,dismiss
        for selected,title in (('email','Publish Email?'),(None,'Publish All?')):
            with patch('crm_automation_publish_confirm.st.dialog') as dialog:
                confirm(Mock(),ADMIN,'fixture',1,selected)
                dialog.assert_called_once_with(title,width='small',on_dismiss=dismiss)
                dialog.return_value.assert_called_once_with(confirmation_body)

    def test_dialog_open_performs_no_store_calls(self):
        from crm_automation_publish_confirm import confirmation_body
        button=Mock();button.button.return_value=False
        with patch('crm_automation_publish_confirm.st.session_state',{}),patch('crm_automation_publish_confirm.st.html'),patch('crm_automation_publish_confirm.st.write'),patch('crm_automation_publish_confirm.st.columns',return_value=[button,button]):
            store=Mock();confirmation_body(store,ADMIN,'fixture',1,'email','DRAFT');self.assertEqual(store.mock_calls,[])
