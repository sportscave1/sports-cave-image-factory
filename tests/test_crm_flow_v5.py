"""Disposable PostgreSQL and fake-clock sequence checks. No external delivery."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import inspect,json,os,uuid,unittest
from unittest.mock import Mock,patch
from pathlib import Path
from tests.test_crm import ADMIN
from tests.test_crm_simple_editor import document
from tests.test_crm_send_flow import CFG,LIVE
from crm_automation_definition import new_flow,email_step
from crm_flow_tests import start,tick,cancel,latest,prepare
from crm_store import Store
from tests.crm_db_fixture import connect

ENV={**LIVE,'CRM_MARKETING_TEST_ENABLED':'true','CRM_INTERNAL_TEST_RECIPIENTS':'operator@example.test'}

class FlowV5UIContracts(unittest.TestCase):
    def test_collapsed_panels_do_not_read_or_arm_refresh(self):
        from contextlib import nullcontext
        from types import SimpleNamespace
        import crm_flow_page as page
        ui=Mock();ui.session_state={};ui.expander.side_effect=lambda *a,**k:nullcontext(SimpleNamespace(open=False))
        store=Mock();shop=Mock()
        with patch.object(page,'st',ui),patch.object(page,'checkout_panel') as load,patch.object(page,'arm') as refresh:
            inspect.unwrap(page.checkouts)(shop,store,ADMIN,{'id':'fixture'})
            inspect.unwrap(page.recipient_details)(store,ADMIN,'fixture')
            load.assert_not_called();store.flow.assert_not_called();store.q.assert_not_called();refresh.assert_not_called()
        shop.assert_not_called()

    def test_lazy_panels_and_no_visible_technical_labels(self):
        import crm_flow_page as page
        self.assertIn('if panel.open:checkout_panel',inspect.getsource(page.checkouts))
        self.assertIn('if panel.open:',inspect.getsource(page.recipient_details))
        self.assertIn('paginated=True',inspect.getsource(page.checkouts))
        self.assertNotIn('Draft content (thumbnail: published)',inspect.getsource(page.sequence))
        import crm_flow_thumbnail as thumbs
        self.assertNotIn('escape(label)',inspect.getsource(thumbs.thumbnail))
        import crm_flow_test_ui as ui
        code=inspect.getsource(ui.control)
        self.assertLess(code.index('if not panel.open:return'),code.index('latest('))
        self.assertNotIn('test_flow(',code)

    def test_sample_render_uses_no_provider_or_shopify(self):
        flow=new_flow();flow['emails']=[email_step(document(),600)]
        before=deepcopy(flow)
        with patch('requests.sessions.Session.request',side_effect=AssertionError('External request forbidden')):
            result=prepare(flow,{**CFG,'test_unsubscribe_url':'https://example.test/crm/unsubscribe/test'})
        self.assertEqual(flow,before);self.assertEqual(result[0][1],600)
        self.assertTrue(result[0][2]['subject'].startswith('[FLOW TEST]'))

@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Explicit disposable PostgreSQL fixture required')
class FlowV5SQLTests(unittest.TestCase):
    def setUp(self):
        self.store=Store(connect)
        self.at=datetime(2026,10,10,tzinfo=timezone.utc)
        self.env=patch.dict(os.environ,ENV);self.env.start();self.addCleanup(self.env.stop)
        self.cfg={**CFG,'test_unsubscribe_url':'https://example.test/crm/unsubscribe/test'}
        self.store.render_settings=Mock(return_value=self.cfg)
        self.store.q('TRUNCATE crm_flow_test_stages,crm_flow_tests')
        self.user={**ADMIN,'email':'operator@example.test'}
        self.provider=Mock();self.provider.send.return_value='fixture-provider-id'
        self.identity=str(uuid.uuid4())

    def flow(self,count=3,disabled=None):
        flow=new_flow();flow['timing_version']=2;flow.pop('abandonment_seconds',None)
        flow['emails']=[email_step(document(),[600,43200,86400][i%3]) for i in range(count)]
        if disabled is not None:flow['emails'][disabled]['enabled']=False
        cfg={'revision':1,'draft':flow,'published_flow':deepcopy(flow),'published_version':11,'format':'automation_flow_v1'}
        self.store.q("INSERT INTO crm_automations(id,automation_key,name,trigger_type,status,steps,config) VALUES(%s,%s,'Fixture','abandoned','ACTIVE','[]',%s)",(self.identity,'fixture-'+self.identity,json.dumps(cfg)))
        return flow

    def begin(self,**kwargs):
        return start(self.store,self.user,self.identity,kwargs.pop('recipient','operator@example.test'),kwargs.pop('operation',uuid.uuid4()),kwargs.pop('revision',1),clock=lambda:self.at,**kwargs)

    def stages(self):return latest(self.store,self.user,self.identity)['stages']
    def cycle(self):return tick(self.store,clock=lambda:self.at,transport=self.provider)

    def test_one_three_six_twelve_with_exact_delay_and_restart(self):
        for count in (1,3,6,12):
            self.identity=str(uuid.uuid4());flow=self.flow(count);self.begin()
            for i,stage in enumerate(flow['emails']):
                self.at+=timedelta(seconds=stage['delay_seconds']-1)
                self.assertFalse(self.cycle())
                self.at+=timedelta(seconds=1)
                # A fresh store represents worker restart; schedule is DB authority.
                self.assertTrue(tick(Store(connect),clock=lambda:self.at,transport=self.provider))
                self.assertEqual(self.stages()[i]['status'],'ACCEPTED')
            self.assertFalse(self.cycle())
            # Reset daily limits between independent cardinality fixtures.
            self.store.q('TRUNCATE crm_flow_test_stages,crm_flow_tests')

    def test_disabled_order_duplicate_and_snapshot(self):
        flow=self.flow(3,disabled=1);operation=uuid.uuid4()
        original=self.store.q('SELECT config FROM crm_automations WHERE id=%s',(self.identity,),True)
        first=self.begin(operation=operation);second=self.begin(operation=operation)
        self.assertEqual(first['id'],second['id']);self.assertEqual(len(self.stages()),2)
        self.assertEqual(first['source'],'TEST — LIVE')
        self.assertEqual(original,self.store.q('SELECT config FROM crm_automations WHERE id=%s',(self.identity,),True))
        cfg=deepcopy(original['config']);cfg['draft']['emails'][0]['document']['content']['subject']='Edited draft'
        cfg['revision']=2
        self.store.q('UPDATE crm_automations SET config=%s WHERE id=%s',(json.dumps(cfg),self.identity))
        frozen=self.store.q('SELECT snapshot FROM crm_flow_tests WHERE id=%s',(first['id'],),True)['snapshot']
        self.assertEqual(frozen['flow'],flow)
        draft=self.begin(revision=2);self.assertEqual(draft['source'],'TEST — Draft')

    def test_invalid_unapproved_nonadmin_and_stale_revision(self):
        self.flow()
        for recipient in ('bad','other@example.test','operator@example.test,other@example.test'):
            with self.assertRaises(PermissionError):self.begin(recipient=recipient)
        with self.assertRaises(PermissionError):
            start(self.store,{**self.user,'role':'worker'},self.identity,'operator@example.test',uuid.uuid4(),1)
        with self.assertRaises(ValueError):self.begin(revision=2)
        self.assertEqual(self.store.q('SELECT count(*) AS n FROM crm_flow_tests',one=True)['n'],0)

    def test_cancel_and_no_customer_analytics_writes(self):
        self.flow()
        counts=lambda:[self.store.q('SELECT count(*) AS n FROM '+t,one=True)['n'] for t in ('crm_marketing_sends','crm_automation_enrollments','crm_marketing_events','crm_shopify_checkouts')]
        before=counts();test=self.begin();cancel(self.store,self.user,test['id'],clock=lambda:self.at)
        self.at+=timedelta(days=4);self.assertFalse(self.cycle())
        self.provider.send.assert_not_called();self.assertTrue(all(s['status']=='CANCELLED' for s in self.stages()))
        self.assertEqual(before,counts())

    def test_unknown_provider_result_never_retries_or_advances(self):
        self.flow();self.begin();self.at+=timedelta(seconds=600)
        self.provider.send.side_effect=TimeoutError('unknown')
        self.assertTrue(self.cycle());self.assertEqual(self.stages()[0]['status'],'SUBMITTED')
        self.at+=timedelta(days=3);self.assertFalse(self.cycle())
        self.provider.send.assert_called_once();self.assertEqual(self.stages()[1]['status'],'WAITING')

    def test_explicit_provider_rejection_is_failed(self):
        from email_service import EmailDeliveryError
        self.flow();self.begin();self.at+=timedelta(seconds=600)
        self.provider.send.side_effect=EmailDeliveryError('rejected',status_code=422)
        self.cycle();self.assertEqual(self.stages()[0]['status'],'FAILED')
        self.assertFalse(self.cycle())

    def test_rate_limit_and_revoked_mailbox(self):
        self.flow();self.begin();self.begin()
        with self.assertRaises(ValueError):self.begin()
        self.at+=timedelta(seconds=600)
        with patch.dict(os.environ,{'CRM_INTERNAL_TEST_RECIPIENTS':''}):self.cycle()
        self.provider.send.assert_not_called()

    def test_daily_limit_and_cancel_ownership(self):
        self.flow()
        for i in range(5):
            test=self.begin();cancel(self.store,self.user,test['id'],clock=lambda:self.at)
        with self.assertRaises(ValueError):self.begin()
        with self.assertRaises(PermissionError):cancel(self.store,{**self.user,'id':'another-admin'},test['id'])

    def test_submission_survives_restart_and_rls_denies_browser_roles(self):
        self.flow();self.begin();self.at+=timedelta(seconds=600)
        # Simulate restart immediately after the durable submission fence.
        self.store.q("UPDATE crm_flow_test_stages SET status='SUBMITTED',submitted_at=%s WHERE status='SCHEDULED'",(self.at,))
        self.assertFalse(tick(Store(connect),clock=lambda:self.at,transport=self.provider))
        self.provider.send.assert_not_called()
        for role in ('anon','authenticated'):
            with self.assertRaises(Exception):
                with self.store.db() as conn:
                    conn.execute('SET LOCAL ROLE '+role)
                    conn.execute('SELECT * FROM crm_flow_tests').fetchall()

    def test_database_snapshot_and_message_are_immutable(self):
        self.flow();test=self.begin()
        with self.assertRaises(Exception):self.store.q("UPDATE crm_flow_tests SET snapshot='{}' WHERE id=%s",(test['id'],))
        with self.assertRaises(Exception):self.store.q("UPDATE crm_flow_test_stages SET message='{}' WHERE test_id=%s",(test['id'],))
