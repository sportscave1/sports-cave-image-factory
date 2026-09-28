"""Offline Stage 1 tests. Every provider request and audit write is mocked."""
import os
import unittest
import uuid
from unittest.mock import Mock, patch

import crm_resend_marketing as delivery
from crm_resend import Config, MarketingDisabled, Resend
from crm_service import Actions
from crm_engine import Engine
from tests.test_crm import ADMIN, WORKER

ENV = {'RESEND_MARKETING_API_KEY': 'fixture-only-not-a-real-key',
       'RESEND_FROM_EMAIL': 'hello@sportscaveshop.com', 'RESEND_FROM_NAME': 'Sports Cave',
       'RESEND_REPLY_TO': 'replies@example.test', 'CRM_MARKETING_ENABLED': 'false',
       'CRM_MARKETING_SEND_ENABLED': 'true', 'CRM_MARKETING_TEST_ENABLED': 'true'}
RECEIPT = '4b514acc-10d6-4b99-9d53-5399e7098edf'


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.guard = patch('requests.sessions.Session.request', side_effect=AssertionError('Network forbidden'))
        self.guard.start(); self.addCleanup(self.guard.stop)
        self.audit = patch.object(delivery, '_audit', return_value=True).start()
        self.addCleanup(patch.stopall)
        self.session = Mock()
        self.session.post.return_value = Mock(status_code=200, json=lambda: {'id': RECEIPT})

    def send(self, **kwargs):
        args = dict(user=ADMIN, recipient='nathan@example.test', confirmed=True,
                    operation_id=str(uuid.uuid4()), env=ENV, session=self.session)
        args.update(kwargs)
        return delivery.send_resend_test_email(**args)

    def test_missing_key_does_not_fall_back_to_legacy_key(self):
        env = dict(ENV, RESEND_MARKETING_API_KEY='', RESEND_API_KEY='legacy-fixture')
        self.assertFalse(delivery.get_resend_marketing_config_status(env)['configured'])
        self.assertFalse(Config(env).api_key)
        with self.assertRaisesRegex(delivery.DeliveryError, 'configuration'):
            self.send(env=env)
        self.session.post.assert_not_called()

    def test_status_requires_every_config_field_and_never_returns_secret(self):
        status = delivery.get_resend_marketing_config_status(ENV)
        self.assertTrue(status['configured']); self.assertFalse(status['marketing_enabled'])
        self.assertNotIn(ENV['RESEND_MARKETING_API_KEY'], repr(status))
        for field in ('RESEND_MARKETING_API_KEY', 'RESEND_FROM_EMAIL', 'RESEND_FROM_NAME', 'RESEND_REPLY_TO'):
            self.assertFalse(delivery.get_resend_marketing_config_status(dict(ENV, **{field: ''}))['configured'])

    def test_master_false_blocks_legacy_campaign_automation_queue_and_direct_provider(self):
        cfg = Config(ENV)
        self.assertFalse(cfg.enabled); self.assertFalse(cfg.tests_enabled)
        store = Mock()
        actions = Actions(store, ADMIN, cfg)
        for call in (lambda: cfg.require_send(), lambda: cfg.require_send(test=True),
                     lambda: actions.schedule({'id': 'campaign'}, None),
                     lambda: actions.resume({'id': 'campaign'}),
                     lambda: actions.automation({'id': 'flow'}, [], {}, 'ACTIVE'),
                     lambda: actions.test({}, 'nathan@example.test', str(uuid.uuid4())),
                     lambda: Resend(cfg, self.session).send('nathan@example.test', {}, 'key')):
            with self.assertRaises(MarketingDisabled): call()
        self.assertFalse(store.mock_calls)
        engine = Engine.__new__(Engine)
        engine.config, engine.store = cfg, store
        self.assertFalse(engine.send_one())
        store.claim_send.assert_not_called()
        self.session.post.assert_not_called()
        with patch.dict(os.environ, ENV, clear=True):
            with self.assertRaisesRegex(delivery.DeliveryError, 'disabled'):
                delivery.send_marketing_email(segment_id='anything')
        with patch.dict(os.environ, dict(ENV, CRM_MARKETING_ENABLED='true'), clear=True):
            with self.assertRaisesRegex(delivery.DeliveryError, 'Stage 1'):
                delivery.send_marketing_email()

    def test_admin_test_with_master_false_has_fixed_content_and_configured_headers(self):
        result = self.send()
        self.assertEqual(result['message_id'], RECEIPT)
        self.assertEqual(result['message'], 'Test email accepted by Resend')
        self.session.post.assert_called_once()
        args = self.session.post.call_args.kwargs
        self.assertEqual(args['json']['from'], 'Sports Cave <hello@sportscaveshop.com>')
        self.assertEqual(args['json']['reply_to'], ENV['RESEND_REPLY_TO'])
        self.assertEqual(args['json']['to'], ['nathan@example.test'])
        self.assertEqual(args['json']['subject'], delivery.SUBJECT)
        self.assertEqual(args['json']['text'], delivery.TEXT)
        self.assertIn('Live CRM marketing remains disabled.', args['json']['html'])
        self.assertTrue(args['headers']['Idempotency-Key'].startswith('crm-admin-test/'))
        self.assertFalse(args['allow_redirects'])
        self.assertEqual(self.audit.call_args_list[0].args[4], 'requested')
        self.assertEqual(self.audit.call_args_list[1].args[4], 'accepted')

    def test_exactly_one_manual_mailbox_no_customer_or_segment_objects(self):
        for address in ('', 'a@example.test,b@example.test', 'a@example.test;b@example.test',
                        'a@example.test\nBcc:b@example.test', 'Person <a@example.test>',
                        ['a@example.test'], {'email': 'a@example.test'}, {'segment_id': '1'},
                        'gid://shopify/Customer/1', 'a..b@example.test', 'a@-invalid.test'):
            with self.subTest(address=address), self.assertRaises(delivery.DeliveryError):
                self.send(recipient=address)
        with self.assertRaises(TypeError): self.send(segment_id='1')
        with self.assertRaises(TypeError): self.send(template={'html': 'promo'})
        self.session.post.assert_not_called()

    def test_active_admin_and_explicit_confirmation_required(self):
        for user in (WORKER, dict(ADMIN, is_active=False), None):
            with self.assertRaises(PermissionError): self.send(user=user)
        for confirmed in (False, None, 'true', 1):
            with self.assertRaises(delivery.DeliveryError): self.send(confirmed=confirmed)
        self.session.post.assert_not_called()

    def test_errors_never_echo_provider_body_headers_or_exception(self):
        secret = ENV['RESEND_MARKETING_API_KEY']
        for code, category in ((401, 'authentication_failed'), (403, 'sender_rejected'),
                               (422, 'invalid_request'), (429, 'resend_unavailable'), (503, 'resend_unavailable')):
            self.session.post.return_value = Mock(status_code=code, json=lambda: {'message': secret})
            with self.assertLogs(delivery.LOG, level='WARNING') as logs:
                with self.assertRaises(delivery.DeliveryError) as error: self.send()
            self.assertEqual(error.exception.category, category)
            self.assertNotIn(secret, str(error.exception) + repr(logs.output) + repr(self.audit.call_args))
        self.session.post.side_effect = RuntimeError('Authorization: Bearer ' + secret)
        with self.assertLogs(delivery.LOG, level='WARNING') as logs:
            with self.assertRaises(delivery.DeliveryError) as error: self.send()
        self.assertNotIn(secret, str(error.exception) + repr(logs.output))

    def test_malformed_success_cannot_leak_secret_as_message_id(self):
        self.session.post.return_value = Mock(status_code=200, json=lambda: {'id': ENV['RESEND_MARKETING_API_KEY']})
        with self.assertRaises(delivery.DeliveryError) as error: self.send()
        self.assertNotIn(ENV['RESEND_MARKETING_API_KEY'], str(error.exception))

    def test_audit_failure_before_send_blocks_and_after_acceptance_does_not_retry(self):
        self.audit.return_value = False
        with self.assertRaisesRegex(delivery.DeliveryError, 'Audit storage'): self.send()
        self.session.post.assert_not_called()
        self.audit.side_effect = [True, False]
        result = self.send()
        self.assertFalse(result['audit_saved']); self.assertEqual(result['message_id'], RECEIPT)
        self.session.post.assert_called_once()


class PanelTests(unittest.TestCase):
    def app(self, admin=True):
        from streamlit.testing.v1 import AppTest
        script = '''
import streamlit as st
from unittest.mock import Mock, patch
from crm_page import render_page
from crm_store import StoreUnavailable
from crm_resend import Config
from tests.test_crm_resend_marketing import ENV, ADMIN, WORKER, RECEIPT
user = ADMIN if ADMIN_FLAG else dict(WORKER, page_permissions=['crm_automations_manage'])
store=Mock(); store.state.side_effect=StoreUnavailable('not installed')
st.session_state.setdefault('send_calls', 0)
st.session_state['crm_settings_section']='Sending & Compliance'
def send(**kwargs):
    st.session_state['send_calls'] += 1
    st.session_state['send_args'] = kwargs
    return {'message': 'Test email accepted by Resend', 'message_id': RECEIPT, 'audit_saved': True}
with patch.dict('os.environ', ENV, clear=True), patch('crm_delivery_panel.send_resend_test_email', side_effect=send), patch('requests.sessions.Session.request', side_effect=AssertionError('Network forbidden')):
    render_page('CRM Settings', user, shop=Mock(), store=store, config=Config(ENV))
'''.replace('ADMIN_FLAG', repr(admin))
        return AppTest.from_string(script).run()

    def test_page_load_and_rerun_never_send_and_panel_precedes_storage_notice(self):
        at = self.app()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state['send_calls'], 0)
        self.assertEqual(at.text_input[0].value, '')
        self.assertTrue(at.error)
        self.assertTrue(any('Marketing Delivery: DISABLED' in t.value for t in at.text))
        at.run(); self.assertEqual(at.session_state['send_calls'], 0)
        at.text_input[0].set_value('nathan@example.test')
        at.checkbox[0].check()
        next(b for b in at.button if b.label == 'Send Test Email').click().run()
        self.assertFalse(at.exception); self.assertEqual(at.session_state['send_calls'], 1)
        self.assertEqual(at.session_state['send_args']['recipient'], 'nathan@example.test')
        self.assertTrue(at.session_state['send_args']['confirmed'])
        self.assertTrue(any(RECEIPT in t.value for t in at.text))
        at.run(); self.assertEqual(at.session_state['send_calls'], 1)
        self.assertNotIn(ENV['RESEND_MARKETING_API_KEY'], str(at))

    def test_non_admin_sees_no_delivery_form(self):
        at = self.app(False)
        self.assertFalse(at.exception)
        self.assertFalse(at.text_input)
        self.assertFalse(any(b.label == 'Send Test Email' for b in at.button))


class AuditTests(unittest.TestCase):
    def test_existing_audit_writer_receives_only_safe_metadata(self):
        with patch('supabase_backend.record_activity_log', return_value={'id': 'audit'}) as writer:
            self.assertTrue(delivery._audit(ADMIN, 'operation', 'nathan@example.test',
                                          'Sports Cave <hello@sportscaveshop.com>', 'accepted', RECEIPT))
        row = writer.call_args.kwargs
        self.assertEqual(row['action_type'], 'resend_test_send')
        self.assertEqual(row['metadata']['recipient'], 'nathan@example.test')
        self.assertEqual(row['metadata']['message_id'], RECEIPT)
        self.assertEqual(row['metadata']['provider'], 'resend')
        self.assertIn('timestamp', row['metadata'])
        self.assertNotIn(ENV['RESEND_MARKETING_API_KEY'], repr(row))

    def test_audit_exception_is_not_logged_raw(self):
        with patch('supabase_backend.record_activity_log', side_effect=RuntimeError(ENV['RESEND_MARKETING_API_KEY'])):
            with self.assertLogs(delivery.LOG, level='WARNING') as logs:
                self.assertFalse(delivery._audit(ADMIN, 'operation', 'nathan@example.test', 'sender', 'failed'))
        self.assertNotIn(ENV['RESEND_MARKETING_API_KEY'], repr(logs.output))


if __name__ == '__main__': unittest.main()
