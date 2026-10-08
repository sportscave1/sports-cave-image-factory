"""Local PostgreSQL only; publication never calls a mail transport."""
from copy import deepcopy
import inspect
import os
from time import perf_counter
import unittest
import uuid
from unittest.mock import patch
from crm_automation_store import AutomationStore
from crm_automation_publication import tick,claim,safe_reason
from crm_automation_definition import email_step
from crm_store import StoreUnavailable
from tests.crm_db_fixture import connect
from tests.test_crm import ADMIN
from tests.test_crm_send_flow import CFG,LIVE
from tests.test_crm_simple_editor import document


class PublicationUiTests(unittest.TestCase):
    def test_automation_checkbox_removed_and_request_navigation(self):
        from crm_automation_ui import settings_control,detail
        from crm_automation_toolbar import toolbar
        settings=inspect.getsource(settings_control);editor=inspect.getsource(toolbar)
        self.assertNotIn('This email copy is reviewed',settings)
        self.assertNotIn("['copy_reviewed']",settings)
        self.assertIn('flush_current(force=True)',editor)
        self.assertIn('store.request_publish(user,identity',editor)
        self.assertIn('open_flow(identity)',editor)
        self.assertNotIn('store.publish(',editor)
        self.assertIn("pop('automation_selected'",editor)
        self.assertIn("query_params.pop('automation'",editor)
        self.assertIn("publication.get('state')=='PUBLISHING'",editor)
        from pathlib import Path
        barrier=Path('components/crm_sections/automation_publish.js').read_text()
        self.assertIn('scCampaignFlushSections',barrier)
        self.assertIn("document.activeElement?.blur()",barrier)
        self.assertIn(".st-key-automation-toolbar button",barrier)
        self.assertIn('Publish changes',barrier)
        # Campaign explicit review continues to own its copy confirmation.
        from crm_campaign_send import review
        self.assertIn("doc['copy_reviewed']=True",inspect.getsource(review))

    def test_status_labels_and_safe_errors(self):
        from crm_automation_home import status_html,status_region
        for category,pub,label in [('Draft',{},'Draft'),('Active',{},'Live'),('Paused',{},'Paused'),
          ('Archived',{},'Archived'),('Active',{'state':'PUBLISHING','revision':8},'Publishing'),
          ('Active',{'state':'FAILED','error':'Review the email.'},'Publish failed')]:
            self.assertIn(label,status_html(category,pub))
        code=inspect.getsource(status_region)
        self.assertIn('@settling_fragment',code);self.assertNotIn('summary(',code)
        self.assertNotIn('secret-value',safe_reason(RuntimeError('secret-value')))
        self.assertNotIn('truthful-copy review',safe_reason(ValueError('Subject present and truthful-copy review complete')))


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class PublicationTests(unittest.TestCase):
    def test_multistep_lifestyle_publication_renders_each_email_once(self):
        from crm_campaign_library import insert_saved_template
        import crm_campaign_send
        row=self.draft('abandoned');flow=deepcopy(row['config']['draft'])
        for n in (1,2,3):insert_saved_template(self.store,flow['emails'][0]['document'],f'builtin-lifestyle-image-{n}',1)
        flow['emails'].append(email_step(deepcopy(flow['emails'][0]['document']),86400))
        row=self.store.save_flow(ADMIN,row['id'],row['name'],flow,row['config']['revision'])
        self.job(row)
        with patch('crm_campaign_send.validate_tracking',wraps=crm_campaign_send.validate_tracking) as render,patch('crm_email_size.campaign_size',side_effect=AssertionError('Duplicate rendering')):
            self.run_job()
        live=self.state(row)
        self.assertEqual(live['config']['publication']['state'],'LIVE')
        self.assertEqual(render.call_count,2)
        self.assertEqual(len(live['steps']),2)

    def test_offline_worker_timeout_is_persistent_and_retryable(self):
        from crm_automation_publication import expire
        row=self.draft();job=self.job(row)
        self.store.q("UPDATE crm_automation_publish_jobs SET requested_at=now()-interval '21 minutes' WHERE id=%s",(job['id'],))
        expire(self.store,row['id'])
        failed=self.state(row)
        self.assertEqual(failed['config']['publication']['state'],'FAILED')
        self.assertEqual(failed['config']['published_version'],0)
        self.assertEqual(failed['config']['draft'],row['config']['draft'])
        self.assertIn('timed out',failed['config']['publication']['error'])
        retry=self.job(failed);self.assertNotEqual(job['id'],retry['id'])
        self.run_job();self.assertEqual(self.state(row)['config']['published_version'],1)

    def test_slow_worker_cannot_commit_after_deadline(self):
        import crm_automation_publication as publication
        row=self.draft();job=self.job(row);prepare=publication.prepare
        def delayed(*args,**kwargs):
            result=prepare(*args,**kwargs)
            self.store.q("UPDATE crm_automation_publish_jobs SET requested_at=now()-interval '21 minutes' WHERE id=%s",(job['id'],))
            return result
        with patch.object(publication,'prepare',side_effect=delayed):self.run_job()
        self.assertEqual(self.state(row)['config']['publication']['state'],'FAILED')
        self.assertEqual(self.state(row)['config']['published_version'],0)

    def test_expired_queued_job_is_failed_before_expensive_work(self):
        row=self.draft();job=self.job(row)
        self.store.q("UPDATE crm_automation_publish_jobs SET requested_at=now()-interval '21 minutes' WHERE id=%s",(job['id'],))
        with patch('crm_automation_publication.prepare',side_effect=AssertionError('Expired work must not render')):self.run_job()
        self.assertEqual(self.state(row)['config']['publication']['state'],'FAILED')

    def test_effective_content_noop_and_paused_publication(self):
        from crm_automation_publish_state import has_changes
        row=self.draft();self.job(row);self.run_job();row=self.state(row)
        self.assertFalse(has_changes(self.store,row))
        with patch.object(self.store,'render_settings',side_effect=AssertionError('Live master defaults must not change comparison')):
            self.assertFalse(has_changes(self.store,row))
        version=row['config']['published_version']
        self.assertTrue(self.job(row)['unchanged'])
        same=self.store.publish(ADMIN,row['id'],row['config']['revision'],env=LIVE)
        self.assertEqual(same['config']['published_version'],version)
        self.store.lifecycle(ADMIN,row['id'],'pause');row=self.state(row)
        pause=row['config']['paused_at'];flow=deepcopy(row['config']['draft'])
        flow['emails'][0]['document']['content']['subject']='Changed subject'
        row=self.store.save_flow(ADMIN,row['id'],row['name'],flow,row['config']['revision'])
        self.assertTrue(has_changes(self.store,row));self.job(row);self.run_job();row=self.state(row)
        self.assertEqual(row['status'],'PAUSED');self.assertEqual(row['config']['paused_at'],pause)
        self.assertEqual(row['config']['published_version'],version+1)
        self.assertFalse(has_changes(self.store,row))

    def test_legacy_snapshot_and_opening_checkout_do_not_flag_changes(self):
        from crm_automation_publish_state import has_changes
        from crm_checkout_section import editable
        row=self.draft('abandoned');self.job(row);self.run_job();row=self.state(row)
        self.store.q("UPDATE crm_automations SET config=config-'published_flow' WHERE id=%s",(row['id'],))
        row=self.state(row);self.assertFalse(has_changes(self.store,row))
        flow=deepcopy(row['config']['draft']);flow['emails'][0]['document']=editable(flow['emails'][0]['document'])
        flow['emails'][0]['document']['copy_reviewed']=True
        self.assertFalse(has_changes(self.store,row,flow))
        self.store.q('DELETE FROM crm_automation_publish_jobs WHERE automation_id=%s',(row['id'],))
        self.assertFalse(has_changes(self.store,self.state(row),flow))

    def test_meaningful_settings_changes_detected_independently_of_revision(self):
        from crm_automation_publish_state import has_changes
        row=self.draft();self.job(row);self.run_job();row=self.state(row)
        for field,value in [('trigger','post_purchase'),('reentry_days',7),('exit_on_purchase',True),('inactive_days',90)]:
            flow=deepcopy(row['config']['draft']);flow[field]=value
            self.assertTrue(has_changes(self.store,row,flow),field)
        for field,value in [('enabled',False),('delay_seconds',700)]:
            flow=deepcopy(row['config']['draft']);flow['emails'][0][field]=value
            self.assertTrue(has_changes(self.store,row,flow),field)
        flow=deepcopy(row['config']['draft']);flow['emails'][0]['document']['custom_html']+='<p>Changed</p>'
        self.assertTrue(has_changes(self.store,row,flow))
    def setUp(self):
        self.store=AutomationStore(connect);self.ids=[]
        self.guard=patch('requests.sessions.Session.request',side_effect=AssertionError('External network forbidden'))
        self.guard.start();self.addCleanup(self.guard.stop)
        self.cfg=patch.object(self.store,'render_settings',return_value=deepcopy(CFG));self.cfg.start();self.addCleanup(self.cfg.stop)
        from crm_logic import now
        self.store.set_state('shopify_automation_capabilities',{'checked_at':now().isoformat(),'triggers':{k:'AVAILABLE' for k in ('welcome','post_purchase','abandoned','fulfilled')}})
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for identity in self.ids:
            self.store.q("UPDATE crm_automation_publish_jobs SET state='FAILED' WHERE automation_id=%s AND state IN ('QUEUED','RUNNING')",(identity,))
            self.store.q("UPDATE crm_automations SET status='PAUSED' WHERE id=%s",(identity,))

    def draft(self,kind='welcome'):
        row=self.store.create(ADMIN,kind,'Local publication fixture');self.ids.append(str(row['id']))
        flow=deepcopy(row['config']['draft']);doc=document();doc['copy_reviewed']=False
        if kind=='abandoned':
            from crm_abandoned_checkout import apply_template
            apply_template(doc)
        flow['emails']=[email_step(doc,0)]
        return self.store.save_flow(ADMIN,row['id'],row['name'],flow,1)

    def job(self,row):return self.store.request_publish(ADMIN,row['id'],row['config']['revision'])
    def run_job(self):return tick(AutomationStore(self.store.connect),'local-worker',env=LIVE)
    def state(self,row):return self.store.flow(row['id'])

    def test_fast_request_freezes_only_exact_saved_revision_without_heavy_work(self):
        row=self.draft();started=perf_counter()
        with patch('crm_automation_publication.prepare',side_effect=AssertionError('Heavy work in request')):
            job=self.job(row)
        elapsed=(perf_counter()-started)*1000
        print('Local durable publish acceptance: %.1f ms'%elapsed)
        self.assertLess(elapsed,1000)
        saved=self.state(row);self.assertEqual(saved['status'],'DRAFT')
        self.assertEqual(saved['config']['publication']['state'],'PUBLISHING')
        self.assertTrue(job['snapshot']['flow']['emails'][0]['document']['copy_reviewed'])
        self.assertFalse(saved['config']['draft']['emails'][0]['document']['copy_reviewed'])
        self.assertEqual(job['revision'],row['config']['revision'])
        self.assertEqual(self.store.q('SELECT count(*) AS n FROM crm_template_versions v WHERE content->>\'automation_id\'=%s',(str(row['id']),),True)['n'],0)

    def test_first_abandoned_publication_loads_home_from_empty_cache(self):
        # This suite is explicitly gated to the disposable localhost SQL fixture.
        self.store.q('TRUNCATE crm_automations CASCADE')
        from crm_automation_home_read import identity_read
        from crm_automation_home_data import identities,counts,reporting_window
        from crm_automation_analytics import summary,activity
        read=lambda state:identity_read(state,self.store,('identities',0),lambda bounded:identities(bounded))
        self.assertEqual(read({}),([], 'READY'))
        row=self.draft('abandoned');job=self.job(row)
        pending,phase=read({})
        self.assertEqual(phase,'READY');self.assertEqual(pending[0]['publication']['state'],'PUBLISHING')
        self.run_job()
        live,phase=read({})
        self.assertEqual((phase,live[0]['category'],live[0]['active_version']),('READY','Active','1'))
        self.assertEqual(counts(self.store)['active'],1)
        self.assertEqual(summary(self.store,reporting_window())['sent_emails'],0)
        self.assertEqual(activity(self.store),[])
        self.assertEqual(self.store.q('SELECT count(*) AS n FROM crm_marketing_sends WHERE enrollment_id IS NOT NULL',one=True)['n'],0)
        self.assertEqual(read({})[0][0]['id'],str(row['id']))

    def test_missing_subject_and_revision_mismatch_rejected_before_queue(self):
        row=self.draft();flow=deepcopy(row['config']['draft']);flow['emails'][0]['document']['content']['subject']=''
        row=self.store.save_flow(ADMIN,row['id'],row['name'],flow,row['config']['revision'])
        with self.assertRaisesRegex(ValueError,'Add a subject'):self.job(row)
        with self.assertRaisesRegex(ValueError,'newer draft'):self.store.request_publish(ADMIN,row['id'],1)
        self.assertEqual(self.store.q('SELECT count(*) AS n FROM crm_automation_publish_jobs WHERE automation_id=%s',(row['id'],),True)['n'],0)

    def test_double_click_success_and_worker_duplicate_are_idempotent(self):
        row=self.draft();job=self.job(row);self.assertEqual(self.job(row)['id'],job['id'])
        with patch('crm_automation_publication.prepare',wraps=__import__('crm_automation_publication').prepare) as prepare:
            self.run_job();self.assertEqual(prepare.call_count,1)
        saved=self.state(row);self.assertEqual(saved['status'],'ACTIVE');self.assertEqual(saved['config']['publication']['state'],'LIVE')
        self.assertFalse(self.run_job());self.assertEqual(self.job(row)['id'],job['id'])
        self.assertEqual(self.state(row)['config']['published_version'],1)
        content=self.store.q('SELECT content FROM crm_template_versions WHERE template_id=%s',(saved['steps'][0]['template_id'],),True)['content']
        self.assertTrue(content['document']['copy_reviewed'])
        self.assertEqual(self.store.q('SELECT count(*) AS n FROM crm_automation_enrollments WHERE automation_id=%s',(row['id'],),True)['n'],0)

    def test_all_native_triggers_use_same_job_pipeline(self):
        for kind in ('welcome','post_purchase','abandoned','fulfilled'):
            with self.subTest(kind=kind):
                row=self.draft(kind);self.job(row);self.run_job()
                self.assertEqual(self.state(row)['config']['publication']['state'],'LIVE')

    def test_editing_next_revision_preserves_publication_snapshot_and_history(self):
        row=self.draft();self.job(row);flow=deepcopy(row['config']['draft'])
        flow['emails'][0]['document']['content']['subject']='New revision subject'
        newer=self.store.save_flow(ADMIN,row['id'],row['name'],flow,row['config']['revision'])
        with self.assertRaisesRegex(ValueError,'already publishing'):self.job(newer)
        self.run_job();saved=self.state(row)
        self.assertEqual(saved['config']['draft']['emails'][0]['document']['content']['subject'],'New revision subject')
        v1=self.store.q('SELECT content FROM crm_template_versions WHERE template_id=%s AND version=1',(saved['steps'][0]['template_id'],),True)['content']
        self.assertNotEqual(v1['document']['content']['subject'],'New revision subject')
        self.job(saved);self.run_job()
        self.assertEqual(self.state(row)['config']['published_version'],2)
        self.assertEqual(self.store.q('SELECT content FROM crm_template_versions WHERE template_id=%s AND version=1',(saved['steps'][0]['template_id'],),True)['content'],v1)

    def test_failed_replacement_keeps_existing_live_version_and_actionable_error(self):
        row=self.draft();self.job(row);self.run_job();live=self.state(row)
        flow=deepcopy(live['config']['draft']);flow['emails'][0]['document']['content']['subject']='Updated subject'
        row=self.store.save_flow(ADMIN,row['id'],row['name'],flow,live['config']['revision']);self.job(row)
        with patch('crm_automation_publication.prepare',side_effect=ValueError('Email tracking failure secret=do-not-display')):self.run_job()
        failed=self.state(row);self.assertEqual(failed['status'],'ACTIVE');self.assertEqual(failed['steps'],live['steps'])
        self.assertEqual(failed['config']['published_version'],1);self.assertEqual(failed['config']['publication']['state'],'FAILED')
        self.assertIn('tracking',failed['config']['publication']['error']);self.assertNotIn('secret',failed['config']['publication']['error'])
        retry=self.job(failed);self.assertEqual(retry['state'],'QUEUED');self.run_job()
        self.assertEqual(self.state(row)['config']['published_version'],2)

    def test_restart_reclaims_expired_lease_and_fences_old_owner(self):
        row=self.draft();job=self.job(row);first=claim(self.store,'old-worker')
        self.assertEqual(first['id'],job['id']);self.assertIsNone(claim(self.store,'other-worker'))
        self.store.q("UPDATE crm_automation_publish_jobs SET lease_until=now()-interval '1 second' WHERE id=%s",(job['id'],))
        self.run_job();self.assertEqual(self.state(row)['config']['publication']['state'],'LIVE')
        persisted=self.store.q('SELECT * FROM crm_automation_publish_jobs WHERE id=%s',(job['id'],),True)
        self.assertEqual(persisted['attempts'],2);self.assertEqual(persisted['owner'],'local-worker')

    def test_transient_storage_retry_is_durable(self):
        row=self.draft();job=self.job(row)
        with patch('crm_automation_publication.prepare',side_effect=StoreUnavailable('sensitive DB detail')):self.run_job()
        self.assertEqual(self.store.q('SELECT state FROM crm_automation_publish_jobs WHERE id=%s',(job['id'],),True)['state'],'QUEUED')
        self.store.q('UPDATE crm_automation_publish_jobs SET available_at=now() WHERE id=%s',(job['id'],));self.run_job()
        self.assertEqual(self.state(row)['config']['publication']['state'],'LIVE')

    def test_stale_job_cannot_overwrite_newer_publication(self):
        row=self.draft();job=self.job(row)
        with patch('crm_automation_publication.prepare',side_effect=ValueError('HTML invalid')):self.run_job()
        self.job(self.state(row));self.run_job();live=self.state(row)
        self.store.q("UPDATE crm_automation_publish_jobs SET state='QUEUED',available_at=now() WHERE id=%s",(job['id'],));self.run_job()
        self.assertEqual(self.state(row)['steps'],live['steps']);self.assertEqual(self.state(row)['config']['publication']['state'],'LIVE')

    def test_real_trigger_failure_is_not_bypassed(self):
        row=self.draft('abandoned');self.job(row)
        self.store.set_state('shopify_automation_capabilities',{})
        self.run_job();failed=self.state(row)
        self.assertEqual(failed['status'],'DRAFT');self.assertEqual(failed['config']['publication']['state'],'FAILED')
        self.assertIn('Shopify trigger',failed['config']['publication']['error'])

    def test_queue_rls_and_browser_roles_denied(self):
        result=self.store.q("SELECT relrowsecurity AS enabled FROM pg_class WHERE relname='crm_automation_publish_jobs'",one=True)
        self.assertTrue(result['enabled'])
        for role in ('anon','authenticated'):
            result=self.store.q("SELECT has_table_privilege(%s,'crm_automation_publish_jobs','SELECT') AS allowed",(role,),True)
            self.assertFalse(result['allowed'])

    def test_two_requesters_create_one_job(self):
        from concurrent.futures import ThreadPoolExecutor
        row=self.draft()
        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs=list(pool.map(lambda _:self.job(row),range(2)))
        self.assertEqual(jobs[0]['id'],jobs[1]['id'])
        self.assertEqual(self.store.q('SELECT count(*) AS n FROM crm_automation_publish_jobs WHERE automation_id=%s',(row['id'],),True)['n'],1)

    def test_old_worker_completion_is_fenced_after_lease_reclaim(self):
        import crm_automation_publication as publication
        row=self.draft();job=self.job(row);original=publication.prepare;calls=[]
        def competing(*args,**kwargs):
            calls.append(1)
            if len(calls)==1:
                self.store.q("UPDATE crm_automation_publish_jobs SET lease_until=now()-interval '1 second' WHERE id=%s",(job['id'],))
                tick(self.store,'replacement-worker',env=LIVE)
            return original(*args,**kwargs)
        with patch('crm_automation_publication.prepare',side_effect=competing):self.run_job()
        self.assertEqual(self.state(row)['config']['published_version'],1)
        self.assertEqual(self.store.q('SELECT owner FROM crm_automation_publish_jobs WHERE id=%s',(job['id'],),True)['owner'],'replacement-worker')

    def test_final_transaction_failure_rolls_back_template_versions(self):
        from crm_automation_publication import commit as original
        row=self.draft();self.job(row)
        def interrupted(store,conn,*args,**kwargs):
            execute=conn.execute
            def fault(sql,values=()):
                if sql.startswith('UPDATE crm_automations'):raise ValueError('HTML validation transaction interrupted')
                return execute(sql,values)
            with patch.object(conn,'execute',side_effect=fault):return original(store,conn,*args,**kwargs)
        with patch('crm_automation_publication.commit',side_effect=interrupted):self.run_job()
        self.assertEqual(self.state(row)['config']['publication']['state'],'FAILED')
        self.assertEqual(self.store.q("SELECT count(*) AS n FROM crm_template_versions WHERE content->>'automation_id'=%s",(str(row['id']),),True)['n'],0)

    def test_finished_status_watch_retains_all_caches_and_does_not_rerun(self):
        from crm_automation_home import refresh_publications
        from unittest.mock import Mock
        state={'publication_updates':{},'campaign_home_cache':{('store',('table',None)):('old','old'),('store',('delivery',None)):('valid','metrics')}}
        records=[{'id':'local-id','category':'Drafts','publication':{'job_id':'job','state':'PUBLISHING'}}]
        mock=Mock();mock.q.return_value=[{'id':'local-id','category':'Active','publication':{'job_id':'job','state':'LIVE'}}]
        with patch('crm_automation_ui.home_state',return_value=state),patch('crm_automation_home.st.rerun') as rerun:
            refresh_publications(mock,records,state)
            refresh_publications(mock,records,state)
        self.assertEqual(state['campaign_home_cache'][('store',('table',None))],('old','old'))
        self.assertEqual(state['campaign_home_cache'][('store',('delivery',None))],('valid','metrics'))
        self.assertEqual(records[0]['publication']['state'],'LIVE')
        mock.q.assert_called_once();rerun.assert_not_called()
