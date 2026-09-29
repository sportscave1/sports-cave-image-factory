"""Local SQL + mocked transports only. Never sends customer or internal email."""
from copy import deepcopy
import os
import uuid
import unittest
from unittest.mock import Mock,patch
from crm_campaign_send import send_test,review,queue_campaign,production_checks,ATTESTATIONS,OFF
from crm_resend import Config,MarketingDisabled
from crm_resend_marketing import DeliveryError
from crm_campaign_content import settings,render_campaign
from crm_campaign_store import CampaignStore
from crm_store import Store
from crm_shopify import Shopify
from tests.crm_db_fixture import connect
from tests.crm_fixtures import ShopifyFixture
from tests.test_crm_simple_editor import document
from tests.test_crm_resend_marketing import ENV
from tests.test_crm import ADMIN

LIVE={**ENV,'CRM_MARKETING_ENABLED':'true','CRM_MARKETING_SEND_ENABLED':'true',
      'CRM_UNSUBSCRIBE_SECRET':'x'*40,'CRM_PUBLIC_BASE_URL':'https://example.test',
      **{v:'true' for v in ATTESTATIONS.values()},'CRM_MARKET_REVIEW_VERIFIED':'AU'}
CFG={**settings(ENV),'postal':'Configured fixture address','postal_verified':True,'domain_verified':True,'identity_confirmed':True}

@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class SendFlowTests(unittest.TestCase):
    def setUp(self):
        self.store=CampaignStore(connect);self.wire=ShopifyFixture(8);self.shop=Shopify(self.wire)
        self.patch=patch.object(self.store,'render_settings',return_value=deepcopy(CFG));self.patch.start();self.addCleanup(self.patch.stop)
        original=self.store.setting
        self.patch2=patch.object(self.store,'setting',side_effect=lambda key:{'value':{'internal_recipients':['internal@example.test'],'smart_hours':16}} if key=='sending' else original(key))
        self.patch2.start();self.addCleanup(self.patch2.stop)
        self.guard=patch('requests.sessions.Session.request',side_effect=AssertionError('External I/O forbidden'));self.guard.start();self.addCleanup(self.guard.stop)
        self.audit=patch('crm_resend_marketing._audit',return_value=True);self.audit.start();self.addCleanup(self.audit.stop)
        self.provider=Mock();self.provider.post.return_value=Mock(status_code=200,json=lambda:{'id':str(uuid.uuid4())})
    def editor(self):
        doc=document();doc['audience']={'kind':'Rules','name':'Fixture audience','rules':{'field':'orders','op':'gte','value':0}}
        return {'id':None,'version':None,'name':'Send flow '+uuid.uuid4().hex,'document':doc,'archived_at':None}
    def count(self,table):return self.store.q('SELECT count(*) n FROM '+table,one=True)['n']
    def saved(self):
        e=self.editor();return self.store.save(ADMIN,e['name'],e['document'],env=ENV)
    def test_single_test_autosaves_exact_content_and_is_idempotent_without_production_jobs(self):
        e=self.editor();e['document']['copy_reviewed']=False;op=str(uuid.uuid4());before=self.count('crm_marketing_sends')
        first=send_test(self.store,ADMIN,e,'internal@example.test',op,env=ENV,session=self.provider)
        second=send_test(self.store,ADMIN,e,'internal@example.test',op,env=ENV,session=self.provider)
        self.provider.post.assert_called_once();self.assertEqual(first['message_id'],second['message_id'])
        payload=self.provider.post.call_args.kwargs
        self.assertEqual(payload['timeout'],15);self.assertEqual(payload['json']['to'],['internal@example.test'])
        self.assertEqual(payload['json']['html'],render_campaign(e['document'],CFG)['html'])
        self.assertEqual(self.count('crm_marketing_sends'),before)
    def test_invalid_multiple_and_nonadmin_test_never_calls_provider(self):
        for address,user in [('bad',ADMIN),('first@example.test,second@example.test',ADMIN),('internal@example.test',{**ADMIN,'role':'worker'})]:
            with self.subTest(address=address,user=user['role']),self.assertRaises((ValueError,PermissionError)):
                send_test(self.store,user,self.editor(),address,str(uuid.uuid4()),env=ENV,session=self.provider)
        self.provider.post.assert_not_called()
    def test_arbitrary_single_recipient_with_marketing_off_and_on_no_allowlist(self):
        for flag in ('false','true'):
            user={**ADMIN,'id':'test-admin-'+uuid.uuid4().hex}
            env={**ENV,'CRM_MARKETING_ENABLED':flag}
            e=self.editor();operation=str(uuid.uuid4())
            before={table:self.count(table) for table in ('crm_campaigns','crm_marketing_sends')}
            self.provider.reset_mock()
            self.provider.post.return_value=Mock(status_code=200,json=lambda:{'id':str(uuid.uuid4())})
            # No recipient configuration is needed even when the legacy key is absent.
            original=self.store.setting
            with patch.object(self.store,'setting',side_effect=lambda key:{'value':{'smart_hours':16}} if key=='sending' else original(key)):
                first=send_test(self.store,user,e,'any.valid+test@example.org',operation,env=env,session=self.provider)
                again=send_test(self.store,user,e,'any.valid+test@example.org',operation,env=env,session=self.provider)
            self.assertEqual(first['message_id'],again['message_id']);self.provider.post.assert_called_once()
            payload=self.provider.post.call_args.kwargs['json']
            self.assertEqual(payload['to'],['any.valid+test@example.org'])
            self.assertIn('[CAMPAIGN TEST]',payload['subject'])
            self.assertEqual(payload['tags'][0]['value'],'campaign_test')
            self.assertNotIn('/crm/unsubscribe?token=',payload['html'])
            self.assertEqual(before,{table:self.count(table) for table in before})
            self.assertNotIn(__import__('crm_logic').recipient_hash('any.valid+test@example.org'),self.store.recent_marketing_hashes())

    def test_single_recipient_validation_rejects_lists_and_header_injection(self):
        for value in (None,[],['a@example.org'],{'email':'a@example.org'},'a@example.org;b@example.org','a@example.org\r\nBcc: other@example.org'):
            with self.subTest(value=value),self.assertRaises(ValueError):
                send_test(self.store,ADMIN,self.editor(),value,str(uuid.uuid4()),env=ENV,session=self.provider)
        self.provider.post.assert_not_called()

    def test_durable_admin_rate_limit_preserves_receipt_replay(self):
        user={**ADMIN,'id':'rate-admin-'+uuid.uuid4().hex};e=self.editor();op=str(uuid.uuid4())
        send_test(self.store,user,e,'arbitrary@example.org',op,env=ENV,session=self.provider)
        self.store.q("""INSERT INTO crm_internal_tests(id,campaign_id,campaign_version,render_hash,recipient,sender,actor,status)
            SELECT gen_random_uuid(),campaign_id,campaign_version,render_hash,recipient,sender,actor,'FAILED'
            FROM crm_internal_tests CROSS JOIN generate_series(1,59) WHERE id=%s""",(op,))
        with self.assertRaisesRegex(ValueError,'60 per hour'):
            send_test(self.store,user,e,'arbitrary@example.org',str(uuid.uuid4()),env=ENV,session=self.provider)
        send_test(self.store,user,e,'arbitrary@example.org',op,env=ENV,session=self.provider)
        self.provider.post.assert_called_once()
        self.assertEqual(self.store.q('SELECT count(*) n FROM crm_internal_tests WHERE actor=%s',(user['id'],),True)['n'],60)

    def test_provider_failure_is_safe_and_not_automatically_retried(self):
        self.provider.post.side_effect=TimeoutError('SECRET SHOULD NOT APPEAR')
        e=self.editor();op=str(uuid.uuid4())
        with self.assertRaises(DeliveryError) as failure:send_test(self.store,ADMIN,e,'internal@example.test',op,env=ENV,session=self.provider)
        self.assertNotIn('SECRET',str(failure.exception))
        with self.assertRaises(ValueError):send_test(self.store,ADMIN,e,'internal@example.test',op,env=ENV,session=self.provider)
        self.provider.post.assert_called_once()
    def test_review_recalculates_without_queueing_and_off_blocks_before_io(self):
        e=self.editor();before=self.count('crm_marketing_sends');result=review(self.shop,self.store,e,ENV)
        self.assertTrue(result['counts']['complete']);self.assertGreater(sum(result['counts']['excluded'].values()),0)
        self.assertEqual(self.count('crm_marketing_sends'),before)
        with patch('crm_campaign_send.final_audience') as calc,self.assertRaisesRegex(MarketingDisabled,'currently OFF'):
            queue_campaign(self.shop,self.store,ADMIN,e,str(uuid.uuid4()),env=ENV)
        calc.assert_not_called();self.assertEqual(self.count('crm_marketing_sends'),before)
    def test_real_queue_once_and_existing_worker_delivers_snapshot_with_mock_provider(self):
        e=self.saved();operation=str(uuid.uuid4())
        with patch.dict(os.environ,LIVE):
            result=queue_campaign(self.shop,self.store,ADMIN,e,operation,env=LIVE)
            repeat=queue_campaign(self.shop,self.store,ADMIN,e,str(uuid.uuid4()),env=LIVE)
            self.assertTrue(repeat['already_started'])
            rows=self.store.q('SELECT * FROM crm_marketing_sends WHERE campaign_id=%s',(e['id'],))
            self.assertEqual(len(rows),result['recipients']);self.assertGreater(len(rows),0)
            self.assertEqual(len({r['recipient_hash'] for r in rows}),len(rows))
            from crm_engine import Engine
            delivery=Mock();delivery.suppressed.return_value=False;delivery.send.return_value=str(uuid.uuid4())
            store=Store(connect)
            with patch.object(store,'claim_send',return_value=rows[0]) as claim:
                # Exercise normal SQL claim first so begin_send verifies its lease.
                claim.side_effect=None;claim.return_value=store.q("UPDATE crm_marketing_sends SET status='CLAIMED',lease_token=gen_random_uuid(),lease_until=now()+interval '5 minutes' WHERE id=%s RETURNING *",(rows[0]['id'],),True)
                from crm_workspace_store import WorkspaceRecords
                with patch.object(WorkspaceRecords,'frequency_blocked',return_value=False):
                    self.assertTrue(Engine(store,self.shop,delivery,Config(LIVE)).send_one())
            delivery.send.assert_called_once()
            message=delivery.send.call_args.args[1]
            self.assertFalse(message['subject'].startswith('[CAMPAIGN TEST]'))
            self.assertNotIn('sc_test=1',message['html']);self.assertIn('/crm/unsubscribe?token=',message['html'])
            self.assertNotIn('sc_test=1',message['text'])
    def test_master_flag_alone_does_not_bypass_readiness(self):
        with self.assertRaises((ValueError,MarketingDisabled)):
            queue_campaign(self.shop,self.store,ADMIN,self.saved(),str(uuid.uuid4()),env={**ENV,'CRM_MARKETING_ENABLED':'true'})
    def test_changed_draft_and_empty_audience_never_queue(self):
        e=self.saved();e['document']['content']['subject']='Unsaved'
        with self.assertRaises(ValueError):queue_campaign(self.shop,self.store,ADMIN,e,str(uuid.uuid4()),env=LIVE)
        e=self.saved();self.wire.customers=[]
        with self.assertRaises(ValueError):queue_campaign(self.shop,self.store,ADMIN,e,str(uuid.uuid4()),env=LIVE)

class SafeErrorTests(unittest.TestCase):
    def test_unknown_exception_does_not_expose_details(self):
        from crm_campaign_send_ui import safe_error
        self.assertNotIn('secret',safe_error(RuntimeError('password=secret')))

@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class SendFlowUiTests(unittest.TestCase):
    def app(self):
        from streamlit.testing.v1 import AppTest
        from tests.test_crm_ui import SCRIPT
        at=AppTest.from_string(SCRIPT.replace("'role':'worker'","'role':'admin'"))
        at.session_state['route']='CRM Campaigns';return at
    def test_single_popover_no_test_accordion_and_lazy_settings(self):
        at=self.app()
        with patch('crm_settings_page.campaign_settings_panel') as panel:
            at.run(timeout=20);self.assertFalse(at.exception)
            self.assertEqual(sum(p.proto.popover.label=='Send test' for p in at.get('popover')),1)
            self.assertFalse(any(b.label in ('Settings','Send internal test','Send Test Email') for b in at.button))
            self.assertNotIn('Test',[e.label for e in at.expander])
            panel.assert_not_called()
            next(t for t in at.text_input if t.label=='Subject').set_value('Editing').run(timeout=20)
            panel.assert_not_called()
            at.session_state['campaign_settings_open']=True;at.run(timeout=20)
            panel.assert_not_called()
    def test_expanded_settings_has_no_second_test_action(self):
        at=self.app();at.run(timeout=20)
        at.session_state['campaign_settings_open']=True;at.run(timeout=20)
        self.assertFalse(at.exception)
        self.assertFalse(any(b.label in ('Send internal test','Send Test Email','Send test') for b in at.button))
        self.assertEqual(sum(p.proto.popover.label=='Send test' for p in at.get('popover')),1)
    def test_form_submission_routes_to_shared_test_and_reports_success(self):
        at=self.app();at.run(timeout=20)
        with patch('crm_campaign_send_ui.send_test',return_value={'audit_saved':True}) as send:
            next(t for t in at.text_input if t.label=='Send test email').set_value('internal@example.test')
            next(b for b in at.button if b.label=='→').click().run(timeout=20)
            self.assertFalse(at.exception);send.assert_called_once()
            self.assertEqual(send.call_args.args[3],'internal@example.test')
            self.assertTrue(any('Test email sent to internal@example.test' in s.value for s in at.success))
    def test_failed_test_returns_visible_safe_error(self):
        at=self.app();at.run(timeout=20)
        with patch('crm_campaign_send_ui.send_test',side_effect=DeliveryError('sender_rejected')):
            next(t for t in at.text_input if t.label=='Send test email').set_value('internal@example.test')
            next(b for b in at.button if b.label=='→').click().run(timeout=20)
            self.assertTrue(any('Sender/domain rejected' in s.value for s in at.error))
    def test_first_send_now_is_review_only_and_shows_off(self):
        at=self.app();store=CampaignStore(connect);before=store.q('SELECT count(*) n FROM crm_marketing_sends',one=True)['n']
        with patch.dict(os.environ,{'CRM_MARKETING_ENABLED':'false'}):
            at.run(timeout=20)
            next(b for b in at.button if b.label=='Send now').click().run(timeout=20)
            self.assertFalse(at.exception)
            self.assertTrue(any('recipients' in m.value and 'excluded' in m.value for m in at.markdown))
            self.assertTrue(any(OFF in s.value for s in at.info))
            self.assertEqual(sum((b.key or '').endswith('confirm_send') for b in at.button),1)
        self.assertEqual(store.q('SELECT count(*) n FROM crm_marketing_sends',one=True)['n'],before)
