"""Real disposable PostgreSQL publication/activation; no real email or Shopify."""
import json,os,unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch,Mock
from crm_logic import now
from crm_automation_publication import tick
from tests import test_crm_automation_publication as publication_tests
from tests.test_crm_send_flow import LIVE
from tests.test_crm import ADMIN


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class LifecyclePublicationTests(unittest.TestCase):
    setUp=publication_tests.PublicationTests.setUp
    cleanup=publication_tests.PublicationTests.cleanup
    draft=publication_tests.PublicationTests.draft
    job=publication_tests.PublicationTests.job
    state=publication_tests.PublicationTests.state
    run_job=publication_tests.PublicationTests.run_job

    @classmethod
    def setUpClass(cls):
        from tests.crm_db_fixture import connect
        source=Path('migrations/20260625_stage1_supabase_operational_ledger.sql').read_text()
        with connect() as c:
            c.execute(source[source.index('CREATE TABLE IF NOT EXISTS shopify_orders ('):source.index('CREATE TABLE IF NOT EXISTS shopify_order_lines (')])
            for statement in Path('migrations/20261010112655_crm_lifecycle_draft_expansion.sql').read_text().split(';'):
                if statement.strip():c.execute(statement)

    def expanded(self,kind):
        from tests.test_crm_simple_editor import document
        row=self.store.create(ADMIN,kind,lifecycle=True);self.ids.append(str(row['id']))
        flow=deepcopy(row['config']['draft'])
        for step in flow['emails']:step['document']=document()
        return self.store.save_flow(ADMIN,row['id'],row['name'],flow,1)

    def test_all_five_durable_publish_pause_resume_edit_and_immutable_versions(self):
        for kind in ('welcome','post_purchase','win_back','fulfilled','abandoned'):
            with self.subTest(kind=kind):
                row=self.expanded(kind) if kind in ('welcome','post_purchase','win_back') else self.draft(kind)
                snapshot=deepcopy(row['config']['draft']);job=self.job(row)
                self.assertEqual(self.state(row)['status'],'DRAFT')
                self.assertEqual(self.job(row)['id'],job['id'])
                self.run_job();live=self.state(row)
                self.assertEqual(live['status'],'ACTIVE')
                self.assertEqual(live['config']['publication']['state'],'LIVE')
                self.assertEqual(len(live['steps']),sum(s.get('enabled',True) for s in snapshot['emails']))
                self.assertEqual([s['delay_seconds'] for s in live['steps']], [s['delay_seconds'] for s in snapshot['emails'] if s.get('enabled',True)])
                versions=self.store.q("SELECT content FROM crm_template_versions WHERE content->>'automation_id'=%s ORDER BY template_id",(str(row['id']),))
                self.assertTrue(versions)
                self.assertEqual(self.store.q('SELECT count(*) AS n FROM crm_automation_enrollments WHERE automation_id=%s',(row['id'],),True)['n'],0)
                self.store.lifecycle(ADMIN,row['id'],'pause');self.store.lifecycle(ADMIN,row['id'],'resume')
                flow=deepcopy(snapshot);flow['emails'][0]['document']['content']['subject']='Updated future email'
                saved=self.store.save_flow(ADMIN,row['id'],row['name'],flow,row['config']['revision'])
                self.assertEqual(self.state(row)['config']['published_flow'],live['config']['published_flow'])
                self.job(saved);self.run_job()
                self.assertEqual(self.state(row)['config']['published_version'],2)
                old=self.store.q("SELECT content FROM crm_template_versions WHERE version=1 AND content->>'automation_id'=%s ORDER BY template_id",(str(row['id']),))
                self.assertEqual(old,versions)

    def test_missing_history_worker_and_delivery_fail_without_job(self):
        row=self.expanded('win_back')
        caps=self.store.state('shopify_automation_capabilities');caps['scopes'].remove('read_all_orders')
        self.store.set_state('shopify_automation_capabilities',caps)
        with self.assertRaisesRegex(ValueError,'read_all_orders'):self.job(row)
        from tests.crm_publication_fixture import ready
        ready(self.store);self.store.set_state('automation_publication_health',{})
        with self.assertRaisesRegex(ValueError,'publication worker'):self.job(row)
        ready(self.store)
        with patch.dict(os.environ,{'CRM_MARKETING_SEND_ENABLED':'false'}):
            with self.assertRaisesRegex(ValueError,'delivery configuration'):self.job(row)
        self.assertEqual(self.store.q('SELECT count(*) AS n FROM crm_automation_publish_jobs WHERE automation_id=%s',(row['id'],),True)['n'],0)

    def test_readiness_lost_after_acceptance_rolls_back_and_retry_succeeds(self):
        row=self.expanded('post_purchase');job=self.job(row)
        caps=self.store.state('shopify_automation_capabilities');caps['webhooks']['ORDERS_FULFILLED']=False
        self.store.set_state('shopify_automation_capabilities',caps);self.run_job()
        failed=self.state(row)
        self.assertEqual(failed['status'],'DRAFT');self.assertEqual(failed['config']['published_version'],0)
        self.assertIn('ORDERS_FULFILLED',failed['config']['publication']['error'])
        self.assertEqual(self.store.q("SELECT count(*) AS n FROM crm_template_versions WHERE content->>'automation_id'=%s",(str(row['id']),),True)['n'],0)
        from tests.crm_publication_fixture import ready
        ready(self.store);retry=self.job(failed);self.assertNotEqual(retry['id'],job['id'])
        self.run_job();self.assertEqual(self.state(row)['status'],'ACTIVE')

    def test_dynamic_templates_survive_actual_worker_publication(self):
        from crm_campaign_library import insert_saved_template
        from crm_post_purchase_templates import PREFIX
        row=self.expanded('post_purchase');flow=deepcopy(row['config']['draft'])
        for index,key in ((0,'purchased'),(2,'collections')):
            insert_saved_template(self.store,flow['emails'][index]['document'],PREFIX+key,1)
        row=self.store.save_flow(ADMIN,row['id'],row['name'],flow,row['config']['revision'])
        self.job(row);self.run_job();live=self.state(row)
        self.assertEqual(live['config']['publication']['state'],'LIVE')
        texts=[json.dumps(s['document']) for s in live['config']['published_flow']['emails']]
        self.assertIn('SC_COLLECTOR_REPEAT_V1:',texts[0]);self.assertIn('SC_COLLECTOR_REPEAT_V1:',texts[2])
        self.assertEqual(live['config']['draft'],flow)

    def payment_only(self):
        row=self.expanded('post_purchase');flow=deepcopy(row['config']['draft'])
        flow['emails'][0]['delay_seconds']=3*3600
        for step in flow['emails'][1:]:step['enabled']=False
        return self.store.save_flow(ADMIN,row['id'],row['name'],flow,row['config']['revision'])

    def test_payment_only_publishes_without_fulfilment_or_legacy_signer(self):
        row=self.payment_only()
        caps=self.store.state('shopify_automation_capabilities');caps['webhooks']['ORDERS_FULFILLED']=False
        self.store.set_state('shopify_automation_capabilities',caps)
        native_env={**LIVE,'CRM_UNSUBSCRIBE_SECRET':'','CRM_PUBLIC_BASE_URL':''}
        with patch.dict(os.environ,native_env):
            self.job(row);tick(self.store,'native-payment-worker',env=native_env)
        live=self.state(row)
        self.assertEqual(live['status'],'ACTIVE')
        self.assertEqual([s['delay_seconds'] for s in live['steps']],[10800])
        self.assertEqual([s['enabled'] for s in live['config']['published_flow']['emails']],[True,False,False])
        self.assertEqual(self.store.q("SELECT count(*) AS n FROM crm_template_versions WHERE content->>'automation_id'=%s",(str(row['id']),),True)['n'],1)
        self.assertEqual(self.store.q('SELECT count(*) AS n FROM crm_automation_enrollments WHERE automation_id=%s',(row['id'],),True)['n'],0)
        self.store.lifecycle(ADMIN,row['id'],'pause')
        flow=deepcopy(live['config']['draft']);flow['emails'][1]['enabled']=True
        changed=self.store.save_flow(ADMIN,row['id'],row['name'],flow,live['config']['revision'])
        from crm_automation_readiness import blockers
        self.assertTrue(any('ORDERS_FULFILLED' in x for x in blockers(self.store,changed)))
        self.assertEqual(blockers(self.store,changed,published=True),[])
        with self.assertRaisesRegex(ValueError,'ORDERS_FULFILLED'):self.job(changed)
        self.store.lifecycle(ADMIN,row['id'],'resume')
        self.assertEqual(len(self.state(row)['steps']),1)

    def test_draft_disabling_fulfilment_is_not_blocked_by_old_published_sequence(self):
        row=self.expanded('post_purchase');self.job(row);self.run_job();live=self.state(row)
        flow=deepcopy(live['config']['draft'])
        for step in flow['emails'][1:]:step['enabled']=False
        changed=self.store.save_flow(ADMIN,row['id'],row['name'],flow,live['config']['revision'])
        caps=self.store.state('shopify_automation_capabilities');caps['webhooks']['ORDERS_FULFILLED']=False
        self.store.set_state('shopify_automation_capabilities',caps)
        self.job(changed);self.run_job()
        self.assertEqual(len(self.state(row)['steps']),1)

    def test_readiness_loss_after_rendering_still_rolls_back_at_commit(self):
        import crm_automation_publication as publication
        row=self.payment_only();self.job(row);original=publication.prepare
        def prepare_then_lose_worker(*args,**kwargs):
            prepared=original(*args,**kwargs)
            self.store.set_state('automation_publication_health',{})
            return prepared
        with patch.object(publication,'prepare',side_effect=prepare_then_lose_worker):self.run_job()
        self.assertEqual(self.state(row)['status'],'DRAFT')
        self.assertIn('publication worker',self.state(row)['config']['publication']['error'])
        self.assertEqual(self.store.q("SELECT count(*) AS n FROM crm_template_versions WHERE content->>'automation_id'=%s",(str(row['id']),),True)['n'],0)

    def test_completed_delivery_checkpoint_persists_with_actual_worker_lease(self):
        from crm_engine import Engine
        from crm_store import Store
        from crm_resend import Config
        store=Store(self.store.connect);engine=Engine(store,Mock(),config=Config({}))
        engine.owner='local-health-fixture'
        try:
            engine.delivery_checkpoint(force=True)
            health=store.state('automation_delivery_health')
            self.assertEqual(health['status'],'ok')
            self.assertFalse(health['marketing_enabled'])
            self.assertTrue(health['checked_at'])
        finally:
            store.release(engine.owner)
            from tests.crm_publication_fixture import ready
            ready(self.store)

    def test_native_toolbar_requires_confirmation_and_waits_for_worker(self):
        from streamlit.testing.v1 import AppTest
        source='''
import streamlit as st
from tests.test_crm_send_flow import CFG
from tests.test_crm_simple_editor import document
from tests.test_crm import ADMIN
from tests.crm_db_fixture import connect
from crm_automation_store import AutomationStore
from crm_automation_toolbar import toolbar
class FixtureStore(AutomationStore):
    def render_settings(self,env=None):return CFG
store=FixtureStore(connect)
if 'fixture_flow' not in st.session_state:
    row=store.create(ADMIN,'welcome',lifecycle=True)
    flow=row['config']['draft']
    for step in flow['emails']:step['document']=document()
    row=store.save_flow(ADMIN,row['id'],row['name'],flow,1)
    st.session_state['fixture_flow']=str(row['id'])
toolbar(store,ADMIN,st.session_state['fixture_flow'])
'''
        app=AppTest.from_string(source,default_timeout=20).run()
        self.assertFalse(app.exception)
        identity=app.session_state['fixture_flow'];self.ids.append(identity)
        app.button(key='toolbar-publish').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(self.store.q('SELECT count(*) AS n FROM crm_automation_publish_jobs WHERE automation_id=%s',(identity,),True)['n'],0)
        self.assertTrue(any('Future eligible customers' in item.value for item in app.markdown))
        app.button(key='automation-publication-confirm').click().run()
        self.assertFalse(app.exception)
        queued=self.store.flow(identity)
        self.assertEqual(queued['status'],'DRAFT')
        self.assertEqual(queued['config']['publication']['state'],'PUBLISHING')
        tick(self.store,'fixture-worker',env=LIVE)
        app.run();self.assertFalse(app.exception)
        self.assertEqual(self.store.flow(identity)['config']['publication']['state'],'LIVE')
