"""Full-flow publication against isolated SQL, with disabled inclusion consent."""
from copy import deepcopy
import os
import unittest
from unittest.mock import patch
from tests import test_crm_email_publication as existing
from tests.test_crm import ADMIN
from crm_flow_inline import step_state
from crm_automation_publish_state import has_changes
from crm_automation_publish_confirm import completed


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class FlowPublicationTests(unittest.TestCase):
    setUp=existing.EmailPublicationTests.setUp
    cleanup=existing.EmailPublicationTests.cleanup
    draft=existing.EmailPublicationTests.draft
    state=existing.EmailPublicationTests.state
    run_job=existing.EmailPublicationTests.run_job
    three=existing.EmailPublicationTests.three
    publish_email=existing.EmailPublicationTests.publish_email

    def test_complete_sequence_all_triggers_persists_and_no_enrolments(self):
        from crm_automation_store import AutomationStore
        for kind in ('abandoned','welcome','post_purchase','win_back','fulfilled'):
            with self.subTest(kind=kind):
                row=self.three(kind);self.publish_email(row,0);self.run_job();row=self.state(row)
                old=deepcopy(row['steps'][0]);draft=deepcopy(row['config']['draft'])
                self.assertTrue(has_changes(self.store,row))
                job=self.store.request_publish(ADMIN,row['id'],row['config']['revision'])
                self.assertEqual(self.store.request_publish(ADMIN,row['id'],row['config']['revision'])['id'],job['id'])
                waiting={'automation-publication-waiting':{'identity':str(row['id']),'job_id':str(job['id'])}}
                self.assertFalse(completed(self.store,self.state(row),waiting))
                self.run_job();live=AutomationStore(self.store.connect).flow(row['id'])
                self.assertEqual([step_state(live,s) for s in draft['emails']],['LIVE']*3)
                self.assertEqual(len(live['config']['published_flow']['emails']),3)
                self.assertEqual(live['config']['draft'],draft)
                self.assertEqual([s['delay_seconds'] for s in live['steps']],[s['delay_seconds'] for s in draft['emails']])
                self.assertFalse(has_changes(self.store,live))
                self.assertTrue(completed(self.store,live,waiting))
                self.assertIsNotNone(self.store.q('SELECT content FROM crm_template_versions WHERE template_id=%s AND version=%s',(old['template_id'],old['template_version']),True))
                self.assertEqual(self.store.q('SELECT count(*) AS n FROM crm_automation_enrollments WHERE automation_id=%s',(row['id'],),True)['n'],0)

    def disabled(self):
        row=self.three();self.publish_email(row,0);self.run_job();row=self.state(row)
        flow=deepcopy(row['config']['draft'])
        for s in flow['emails'][1:]:s['enabled']=False
        return self.store.save_flow(ADMIN,row['id'],row['name'],flow,row['config']['revision'])

    def test_disabled_requires_explicit_inclusion_and_paused_remains_paused(self):
        row=self.disabled();self.store.request_publish(ADMIN,row['id'],row['config']['revision']);self.run_job();row=self.state(row)
        self.assertEqual([step_state(row,s) for s in row['config']['draft']['emails']],['LIVE','DISABLED','DISABLED'])
        self.store.lifecycle(ADMIN,row['id'],'pause');row=self.state(row)
        ids=[s['step_id'] for s in row['config']['draft']['emails'][1:]]
        self.store.request_publish(ADMIN,row['id'],row['config']['revision'],enable_ids=ids)
        self.run_job();row=self.state(row)
        self.assertEqual([step_state(row,s) for s in row['config']['draft']['emails']],['PAUSED']*3)
        self.assertTrue(all(s.get('enabled',True) for s in row['config']['draft']['emails']))
        self.assertFalse(has_changes(self.store,row))

    def test_failure_and_concurrent_edit_preserve_draft_and_live(self):
        for concurrent in (False,True):
            row=self.disabled();original=deepcopy(row);ids=[s['step_id'] for s in row['config']['draft']['emails'][1:]]
            self.store.request_publish(ADMIN,row['id'],row['config']['revision'],enable_ids=ids)
            if concurrent:
                flow=deepcopy(row['config']['draft']);flow['emails'][1]['name']='Administrator changed draft'
                original=self.store.save_flow(ADMIN,row['id'],row['name'],flow,row['config']['revision'])
                self.run_job()
            else:
                with patch('crm_automation_publication.prepare',side_effect=ValueError('tracking failure')):self.run_job()
            failed=self.state(row)
            self.assertEqual(failed['config']['publication']['state'],'FAILED')
            self.assertEqual(failed['steps'],original['steps'])
            self.assertEqual(failed['config']['published_version'],original['config']['published_version'])
            self.assertEqual(failed['config']['draft'],original['config']['draft'])

    def test_atomic_storage_failure_rolls_back_all_email_versions(self):
        import crm_automation_publication as publication
        row=self.disabled();before=deepcopy(row);ids=[s['step_id'] for s in row['config']['draft']['emails'][1:]]
        self.store.request_publish(ADMIN,row['id'],row['config']['revision'],enable_ids=ids)
        commit=publication.commit
        def reject(*args,**kwargs):
            commit(*args,**kwargs)
            raise ValueError('Synthetic failure after all writes before transaction commit')
        with patch.object(publication,'commit',side_effect=reject):self.run_job()
        after=self.state(row)
        self.assertEqual(after['steps'],before['steps'])
        self.assertEqual(after['config']['draft'],before['config']['draft'])
        self.assertEqual(after['config']['published_flow'],before['config']['published_flow'])
        self.assertEqual(self.store.q("SELECT count(*) AS n FROM crm_template_versions WHERE content->>'automation_id'=%s",(str(row['id']),),True)['n'],1)

    def test_post_purchase_lifecycle_timing_and_revision_history_preserved(self):
        from crm_lifecycle_definition import expanded_flow
        row=self.draft('post_purchase');flow=expanded_flow('post_purchase')
        flow['emails'][0]['delay_seconds']=10800  # Existing user-configured three-hour delay.
        for step in flow['emails']:step['document']=deepcopy(row['config']['draft']['emails'][0]['document'])
        for step in flow['emails'][1:]:step['enabled']=False
        row=self.store.save_flow(ADMIN,row['id'],row['name'],flow,row['config']['revision'])
        before=deepcopy(row['config']['draft']);revision=row['config']['revision']
        ids=[s['step_id'] for s in flow['emails'][1:]]
        self.store.request_publish(ADMIN,row['id'],revision,enable_ids=ids);self.run_job();live=self.state(row)
        expected=deepcopy(before)
        for step in expected['emails']:step['enabled']=True
        self.assertEqual(live['config']['draft'],expected)
        self.assertEqual([(s['delay_seconds'],s['anchor']) for s in live['steps']],[(10800,'payment'),(604800,'delivery'),(3888000,'payment')])
        self.assertEqual(live['config']['published']['fulfilment_fallback_days'],before['fulfilment_fallback_days'])
        self.assertTrue(live['config']['published_flow']['emails'][2]['requires_fulfilment'])
        self.assertEqual(self.store.q('SELECT definition FROM crm_lifecycle_revisions WHERE automation_id=%s AND revision=%s',(row['id'],revision),True)['definition'],before)

    def test_inclusion_reconciles_disabled_draft_even_when_live_content_matches(self):
        row=self.three();self.store.request_publish(ADMIN,row['id'],row['config']['revision']);self.run_job();row=self.state(row)
        flow=deepcopy(row['config']['draft']);flow['emails'][1]['enabled']=False
        row=self.store.save_flow(ADMIN,row['id'],row['name'],flow,row['config']['revision'])
        job=self.store.request_publish(ADMIN,row['id'],row['config']['revision'],enable_ids=[flow['emails'][1]['step_id']])
        self.assertFalse(job.get('unchanged'));self.run_job();row=self.state(row)
        self.assertTrue(row['config']['draft']['emails'][1]['enabled'])
        self.assertFalse(has_changes(self.store,row))
