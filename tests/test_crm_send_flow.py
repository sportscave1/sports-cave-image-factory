"""Local SQL + mocked transports only. Never sends customer or internal email."""
from tests.crm_fixtures import TEST_UNSUBSCRIBE_URL
from copy import deepcopy
import os
import uuid
import unittest
from unittest.mock import Mock,patch
from crm_campaign_send import send_test,review,queue_campaign,production_checks,OFF
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
      'CRM_MARKET_REVIEW_VERIFIED':'AU'}
CFG={**settings(ENV),'postal':'Configured fixture address','postal_verified':True,'domain_verified':True,'identity_confirmed':True}

@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class SendFlowTests(unittest.TestCase):
    def setUp(self):
        from tests.crm_fixtures import TestRecipientShop
        customer_patch=patch('crm_test_recipient.Shopify',return_value=TestRecipientShop())
        customer_patch.start();self.addCleanup(customer_patch.stop)
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
        self.assertEqual(payload['json']['html'],render_campaign(e['document'],CFG,production=True,test_tracking=True,unsubscribe_url=TEST_UNSUBSCRIBE_URL)['html'])
        self.assertEqual(self.count('crm_marketing_sends'),before)
    def test_invalid_multiple_and_nonadmin_test_never_calls_provider(self):
        for address,user in [('bad',ADMIN),('first@example.test,second@example.test',ADMIN),('internal@example.test',{**ADMIN,'role':'worker'})]:
            with self.subTest(address=address,user=user['role']),self.assertRaises((ValueError,PermissionError)):
                send_test(self.store,user,self.editor(),address,str(uuid.uuid4()),env=ENV,session=self.provider)
        self.provider.post.assert_not_called()
    def test_subscribed_single_recipient_with_marketing_off_and_on_no_allowlist(self):
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
            reviewed=review(self.shop,self.store,e,LIVE)
            result=queue_campaign(self.shop,self.store,ADMIN,e,operation,env=LIVE,snapshot_id=reviewed['snapshot_id'])
            repeat=queue_campaign(self.shop,self.store,ADMIN,e,str(uuid.uuid4()),env=LIVE)
            self.assertTrue(repeat['already_started'])
            rows=self.store.q('SELECT * FROM crm_marketing_sends WHERE campaign_id=%s',(e['id'],))
            self.assertEqual(len(rows),result['recipients']);self.assertGreater(len(rows),0)
            self.assertEqual(len({r['recipient_hash'] for r in rows}),len(rows))
            from crm_engine import Engine
            from tests.test_crm_batch_dispatch import Transport
            from types import SimpleNamespace
            from crm_campaign_dispatch import dispatch
            transport=Transport();delivery=SimpleNamespace(batch_transport=transport)
            store=Store(connect)
            store.q("UPDATE crm_campaigns SET status='PAUSED' WHERE id<>%s AND status='SENDING'",(e['id'],))
            self.assertTrue(dispatch(Engine(store,self.shop,delivery,Config(LIVE))))
            self.assertEqual(len(transport.calls),1)
            self.assertTrue(all(r['status']=='ACCEPTED' for r in store.q('SELECT status FROM crm_marketing_sends WHERE campaign_id=%s',(e['id'],))))
            message=transport.calls[0][1][0]
            self.assertFalse(message['subject'].startswith('[CAMPAIGN TEST]'))
            self.assertNotIn('sc_test=1',message['html']);self.assertIn('/account/unsubscribe?token=fixture-',message['html'])
            self.assertNotIn('List-Unsubscribe-Post',message['headers'])
            self.assertNotIn('sc_test=1',message['text'])
    def test_native_queue_requires_no_custom_secret_and_missing_url_creates_no_jobs(self):
        env={k:v for k,v in LIVE.items() if k not in ('CRM_UNSUBSCRIBE_SECRET','CRM_PUBLIC_BASE_URL','CRM_ONE_CLICK_UNSUBSCRIBE_VERIFIED')}
        saved=self.saved();reviewed=review(self.shop,self.store,saved,env)
        result=queue_campaign(self.shop,self.store,ADMIN,saved,str(uuid.uuid4()),env=env,snapshot_id=reviewed['snapshot_id'])
        self.assertGreater(result['recipients'],0)
        from tests.crm_fixtures import native_customer
        for i,c in enumerate(self.wire.customers):
            c=native_customer(c);c['defaultEmailAddress']['marketingUnsubscribeUrl']=''
            self.wire.customers[i]=c
        before=self.count('crm_marketing_sends')
        with self.assertRaisesRegex(ValueError,'Missing Shopify marketing unsubscribe URL'):
            review(self.shop,self.store,self.saved(),env)
        self.assertEqual(self.count('crm_marketing_sends'),before)
        self.provider.post.assert_not_called()

    def test_master_flag_alone_does_not_bypass_readiness(self):
        with self.assertRaises((ValueError,MarketingDisabled)):
            queue_campaign(self.shop,self.store,ADMIN,self.saved(),str(uuid.uuid4()),env={**ENV,'CRM_MARKETING_ENABLED':'true'})

    def campaign_user(self):
        return {**ADMIN,'id':'campaign-user-'+uuid.uuid4().hex,'role':'worker','page_permissions':['crm_campaigns_manage']}

    def test_campaign_user_test_without_manual_verification_or_marketing(self):
        user=self.campaign_user();editor=self.editor();before=self.count('crm_marketing_sends')
        with patch.object(self.store,'render_settings',return_value={**CFG,'postal_verified':False,'domain_verified':False,'identity_confirmed':False}):
            result=send_test(self.store,user,editor,'internal@example.test',str(uuid.uuid4()),env={**ENV,'CRM_MARKETING_ENABLED':'false'},session=self.provider)
        self.assertTrue(result['message_id']);self.provider.post.assert_called_once()
        self.assertEqual(self.count('crm_marketing_sends'),before)
        self.assertNotEqual(self.store.draft(editor['id'])['status'],'SENT')

    def test_campaign_user_can_queue_and_schedule_without_attestations(self):
        user=self.campaign_user()
        env={k:v for k,v in LIVE.items() if not k.endswith('_VERIFIED')}
        cfg={**CFG,'postal_verified':False,'domain_verified':False,'identity_confirmed':False}
        for timing,status in [({'mode':'now'},'SENDING'),({'mode':'schedule','date':'2099-10-05','time':'07:00'},'SCHEDULED')]:
            with self.subTest(status=status),patch.object(self.store,'render_settings',return_value=cfg):
                editor=self.editor();editor['document']['send_timing']=timing
                editor=self.store.save(user,editor['name'],editor['document'],env=env)
                checked=review(self.shop,self.store,editor,env)
                self.assertEqual(checked['blockers'],[]);self.assertTrue(checked['snapshot_id'])
                result=queue_campaign(self.shop,self.store,user,editor,str(uuid.uuid4()),env=env,snapshot_id=checked['snapshot_id'])
                self.assertEqual(result['status'],status)
                again=queue_campaign(self.shop,self.store,user,editor,str(uuid.uuid4()),env=env,snapshot_id=checked['snapshot_id'])
                self.assertTrue(again['already_started'])

    def test_no_campaign_permission_or_inactive_user_blocked_at_both_boundaries(self):
        for user in ({},{**self.campaign_user(),'is_active':False},{**self.campaign_user(),'page_permissions':[]}):
            with self.subTest(user=user),self.assertRaises(PermissionError):
                send_test(self.store,user,self.editor(),'internal@example.test',str(uuid.uuid4()),env=ENV,session=self.provider)
            with self.assertRaises(PermissionError):
                queue_campaign(self.shop,self.store,user,self.editor(),str(uuid.uuid4()),env=LIVE)
        self.provider.post.assert_not_called()

    def test_campaign_user_still_requires_master_switch_and_snapshot(self):
        user=self.campaign_user();editor=self.saved()
        with self.assertRaises(MarketingDisabled):
            queue_campaign(self.shop,self.store,user,editor,str(uuid.uuid4()),env={**LIVE,'CRM_MARKETING_ENABLED':'false'})
        with self.assertRaises(ValueError):
            queue_campaign(self.shop,self.store,user,editor,str(uuid.uuid4()),env=LIVE)

    def test_manual_flags_do_not_replace_real_configuration(self):
        editor=self.saved();checked=review(self.shop,self.store,editor,LIVE)
        checks=production_checks(checked['document'],{**CFG,'postal':''},LIVE)
        self.assertNotIn('Business postal address configured',checks)
        checks=production_checks(checked['document'],CFG,{**LIVE,'RESEND_MARKETING_API_KEY':''})
        self.assertFalse(checks['Resend marketing API configured'])
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
        at=AppTest.from_string(SCRIPT)  # Campaign-authorized worker, not admin.
        at.session_state['route']='CRM Campaigns';return at
    def test_single_popover_no_test_accordion_and_lazy_settings(self):
        at=self.app()
        with patch('crm_settings_page.campaign_settings_panel') as panel:
            at.run(timeout=20);self.assertFalse(at.exception)
            self.assertEqual(sum(p.proto.popover.label=='Send test' for p in at.get('popover')),1)
            self.assertFalse(next(p for p in at.get('popover') if p.proto.popover.label=='Send test').proto.popover.disabled)
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
            self.assertTrue(any('Verifying' in m.value or ('recipients' in m.value and 'excluded' in m.value) for m in at.markdown))
            self.assertTrue(any(OFF in s.value for s in at.caption))
            self.assertEqual(sum((b.key or '').endswith('confirm_send') for b in at.button),1)
            self.assertTrue(next(b for b in at.button if (b.key or '').endswith('confirm_send')).disabled)
            job=next(v for k,v in at.session_state.filtered_state.items() if k.endswith('review_job'))
            job.future.result(timeout=20)
        self.assertEqual(store.q('SELECT count(*) n FROM crm_marketing_sends',one=True)['n'],before)
