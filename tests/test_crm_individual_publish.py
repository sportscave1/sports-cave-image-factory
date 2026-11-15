"""Real loopback SQL transactions; synthetic content, no providers or customers."""
from copy import deepcopy
import os,unittest
from unittest.mock import patch
from tests.test_crm_email_publication import EmailPublicationTests
from tests.test_crm import ADMIN
from crm_automation_publication import preflight
from crm_automation_publish_state import publication_flow


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class IndividualPublishTests(unittest.TestCase):
    setUp=EmailPublicationTests.setUp
    cleanup=EmailPublicationTests.cleanup
    draft=EmailPublicationTests.draft
    state=EmailPublicationTests.state
    run_job=EmailPublicationTests.run_job
    three=EmailPublicationTests.three
    publish_email=EmailPublicationTests.publish_email
    setUpClass=EmailPublicationTests.setUpClass

    def disabled(self,kind='welcome'):
        row=self.three(kind);flow=deepcopy(row['config']['draft'])
        for step in flow['emails']:step['enabled']=False
        # Unselected, unfinished content must not block the selected email.
        flow['emails'][1]['document']['content']['subject']=''
        return self.store.save_flow(ADMIN,row['id'],row['name'],flow,row['config']['revision'])

    def test_first_disabled_email_all_triggers_safe_retries_and_no_activation(self):
        for kind in ('welcome','post_purchase','fulfilled','win_back','abandoned'):
            with self.subTest(kind=kind):
                row=self.disabled(kind);draft=deepcopy(row['config']['draft']);sid=draft['emails'][0]['step_id']
                job=self.publish_email(row,0)
                self.assertEqual(len(job['snapshot']['flow']['emails']),1)
                self.assertTrue(job['snapshot']['flow']['emails'][0]['enabled'])
                self.assertEqual(job['snapshot']['enable_ids'],[sid])
                self.assertEqual(self.publish_email(row,0)['id'],job['id'])
                pending=self.state(row)
                self.assertEqual(pending['config']['draft'],draft)
                self.assertEqual(pending['status'],'DRAFT')
                self.run_job();done=self.state(row)
                self.assertEqual(done['config']['publication']['state'],'LIVE')
                self.assertEqual(done['status'],'DRAFT');self.assertIsNone(done['activated_at'])
                self.assertEqual([s.get('enabled',True) for s in done['config']['draft']['emails']],[True,False,False])
                self.assertEqual([s['step_id'] for s in done['steps']],[sid])
                self.assertEqual(done['config']['draft']['emails'][1:],draft['emails'][1:])
                self.assertEqual(done['config']['email_publications'][sid]['state'],'LIVE')
                # Lost-response retry after the server's enable/revision commit.
                retry=self.publish_email(row,0)
                self.assertEqual(retry['id'],job['id']);self.assertTrue(retry['unchanged'])
                self.assertEqual(self.store.q('SELECT count(*) AS n FROM crm_automation_publish_jobs WHERE automation_id=%s',(row['id'],),True)['n'],1)
                self.assertEqual(self.store.q('SELECT count(*) AS n FROM crm_automation_enrollments WHERE automation_id=%s',(row['id'],),True)['n'],0)

    def test_active_and_paused_parent_and_other_versions_preserved(self):
        for paused in (False,True):
            row=self.three()
            self.store.request_publish(ADMIN,row['id'],row['config']['revision']);self.run_job()
            if paused:self.store.lifecycle(ADMIN,row['id'],'pause')
            row=self.state(row);prior=deepcopy(row)
            flow=deepcopy(row['config']['draft'])
            flow['emails'][0]['enabled']=False;flow['emails'][2]['enabled']=False
            flow['emails'][0]['document']['content']['subject']='Latest saved replacement'
            flow['emails'][1]['document']['content']['subject']=''
            row=self.store.save_flow(ADMIN,row['id'],row['name'],flow,row['config']['revision'])
            self.publish_email(row,0);self.run_job();done=self.state(row)
            self.assertEqual(done['status'],prior['status']);self.assertEqual(done['activated_at'],prior['activated_at'])
            self.assertEqual(done['steps'][1:],prior['steps'][1:])
            self.assertFalse(done['config']['draft']['emails'][2]['enabled'])
            content=self.store.template(done['steps'][0]['template_id'],done['steps'][0]['template_version'])
            self.assertEqual(content['document']['content']['subject'],'Latest saved replacement')

    def test_failed_replacement_and_retry_keep_previous_version_and_saved_draft(self):
        row=self.three();self.publish_email(row,0);self.run_job();row=self.state(row)
        flow=deepcopy(row['config']['draft']);flow['emails'][0]['document']['content']['subject']='Replacement'
        row=self.store.save_flow(ADMIN,row['id'],row['name'],flow,row['config']['revision']);prior=deepcopy(row)
        job=self.publish_email(row,0)
        with patch('crm_automation_publication.prepare',side_effect=ValueError('Email tracking failure')):self.run_job()
        failed=self.state(row);sid=flow['emails'][0]['step_id']
        self.assertEqual(failed['config']['email_publications'][sid]['state'],'FAILED')
        self.assertEqual(failed['steps'],prior['steps']);self.assertEqual(failed['config']['draft'],flow)
        self.assertEqual(failed['config']['published_version'],prior['config']['published_version'])
        retry=self.publish_email(failed,0);self.assertNotEqual(retry['id'],job['id'])
        self.assertEqual(self.publish_email(failed,0)['id'],retry['id'])
        self.run_job();self.assertEqual(self.state(row)['config']['publication']['state'],'LIVE')

    def test_validation_is_selected_and_not_hidden(self):
        row=self.disabled();sid=row['config']['draft']['emails'][0]['step_id']
        scoped=publication_flow(self.store,row,sid)
        preflight(row,row['config']['revision'],scoped,step_id=sid)
        scoped['emails'][0]['document']['content']['subject']=''
        with self.assertRaisesRegex(ValueError,'subject'):preflight(row,row['config']['revision'],scoped,step_id=sid)
        with self.assertRaisesRegex(ValueError,'Enable at least one'):preflight(row,row['config']['revision'])


if __name__=='__main__':unittest.main()
