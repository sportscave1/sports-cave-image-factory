"""Synthetic, offline Resend notification delivery and privacy acceptance."""
import asyncio
from copy import deepcopy
from email.utils import formataddr
import json
import threading
import time
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

import marketplace as core
import marketplace_api as api
import marketplace_account_api as customer_api
import marketplace_notifications as alerts
from marketplace_accounts import COOKIE
from marketplace_store import PREFIX
from email_service import EmailDeliveryError, EmailDeliveryResult
from tests.test_marketplace_accounts import Setup, payload, photograph, sample, PAYPAL

ENV = {'RENDER': 'true', 'RESEND_MARKETING_API_KEY': 'synthetic key only',
       'RESEND_FROM_EMAIL': 'hello@example.invalid', 'CRM_MARKETING_ENABLED': 'false'}
SENDER = formataddr(('Sports Cave Marketplace', ENV['RESEND_FROM_EMAIL']))


class Clock:
    def __init__(self): self.value = time.time()
    def __call__(self): return self.value
    def advance(self, seconds): self.value += seconds


class AlertSetup(Setup):
    def setUp(self):
        super().setUp()
        self.clock = Clock()
        self.queue = alerts.NotificationStore(self.db.connect, clock=self.clock)
    def start_chat(self, **values):
        with patch.object(alerts.time, 'time', self.clock):
            return self.store.start(self.buyer['id'], self.item, payload(**values))['id']
    def send(self, thread, uid, **values):
        with patch.object(alerts.time, 'time', self.clock):
            return self.store.send(thread, uid, payload(**values))
    def ready(self):
        self.clock.advance(alerts.GRACE + 1)
        return self.queue.due()
    def claim(self):
        candidates = self.queue.due()
        return self.queue.claim(candidates[0], SENDER) if candidates else None
    def row(self, thread, role='seller'):
        return deepcopy(self.db.values[PREFIX + alerts.channel(thread, role)])


class QueueTests(AlertSetup):
    def test_committed_messages_create_one_small_pending_record_and_no_network(self):
        with patch.object(alerts, 'deliver', side_effect=AssertionError('No send on the request path')):
            thread = self.start_chat(text='PRIVATE BODY NEVER IN EMAIL')
        self.assertEqual(self.queue.due(), [])
        self.assertEqual(len(self.ready()), 1)
        row = self.row(thread)
        self.assertEqual(row['pending_seq'], 1)
        self.assertNotIn('PRIVATE BODY', json.dumps(row))
        self.assertNotIn('@example', json.dumps(row))

    def test_enqueue_failure_rolls_back_message_thread_and_receipt(self):
        before = deepcopy(self.db.values)
        with patch.object(alerts, 'enqueue', side_effect=ValueError('synthetic save failure')):
            with self.assertRaises(ValueError): self.start_chat()
        self.assertEqual(self.db.values, before)

    def test_idempotent_message_retry_does_not_queue_another_alert(self):
        data = payload()
        first = self.store.start(self.buyer['id'], self.item, data)
        before = deepcopy(self.db.values)
        self.assertEqual(self.store.start(self.buyer['id'], self.item, data), first)
        notice_keys = [k for k in before if ':notice:' in k or ':notice-due:' in k]
        self.assertEqual({k: self.db.values[k] for k in notice_keys}, {k: before[k] for k in notice_keys})
        self.assertEqual(len(notice_keys), 2)

    def test_recipient_is_other_participant_never_client_supplied_address(self):
        thread = self.start_chat(email='attacker@example.invalid', recipient='attacker@example.invalid')
        self.ready()
        job = self.claim()
        self.assertEqual(job['attempt']['recipient'], self.seller['email'])
        self.queue.complete(job, receipt='receipt-1')
        self.send(thread, self.seller['id'], text='Reply')
        self.ready()
        self.assertEqual(self.claim()['attempt']['recipient'], self.buyer['email'])

    def test_all_events_have_minimal_links_without_message_or_payment_details(self):
        for kind, (heading, intro) in alerts.EVENTS.items():
            with self.subTest(kind=kind):
                message = alerts.email_message(str(uuid4()), [kind])
                self.assertIn(heading, message.subject)
                self.assertIn('View conversation', message.html)
                self.assertIn(core.PUBLIC_ORIGIN + '/marketplace/inbox/', message.html)
                self.assertIn('/marketplace/account', message.text)
                for absent in ('<img', 'src=', 'paypal.com/invoice', 'amount_cents', 'seller@example', '<script'):
                    self.assertNotIn(absent, message.html)
                self.assertLess(len(message.html.encode()), 1800)

    def test_offers_invoices_and_seller_offer_responses_target_the_correct_role(self):
        thread = self.start_chat(kind='offer', amount='175.00')
        self.ready()
        seller_job = self.claim()
        self.assertIn('New offer', seller_job['attempt']['subject'])
        self.queue.complete(seller_job, receipt='offer-receipt')
        self.send(thread, self.seller['id'], kind='offer_response', offer_seq=1, choice='accepted')
        self.send(thread, self.seller['id'], kind='invoice', amount='190', url=PAYPAL, text='PRIVATE INVOICE NOTE')
        self.ready()
        buyer_job = self.claim()
        self.assertEqual(buyer_job['role'], 'buyer')
        self.assertEqual(buyer_job['attempt']['recipient'], self.buyer['email'])
        self.assertIn('New chat activity', buyer_job['attempt']['subject'])
        for absent in (PAYPAL, 'PRIVATE INVOICE NOTE', '190', self.seller['email']):
            self.assertNotIn(absent, buyer_job['attempt']['html'] + buyer_job['attempt']['text'])

    def test_published_guest_seller_gets_link_but_no_private_message_content(self):
        address = 'guest@example.invalid'
        record = {**core.submission(sample()), 'seller_email': address}
        item = self.store.submit(record, core.prepare_photos([photograph(), photograph()]))['id']
        self.store.moderate(item, 'published', 1, 'synthetic-admin')
        thread = self.store.start(self.buyer['id'], item, payload(text='PRIVATE QUESTION'))['id']
        self.ready()
        job = self.claim()
        self.assertEqual(job['attempt']['recipient'], address)
        self.assertIn('/inbox/' + thread, job['attempt']['text'])
        self.assertNotIn('PRIVATE QUESTION', job['attempt']['html'])

    def test_unverified_guest_contact_cannot_be_rerouted_by_editing_listing_email(self):
        self.db.values[PREFIX + 'listing:' + self.item].pop('seller_user_id', None)
        self.db.values.pop(PREFIX + 'account-email:' + alerts.digest(self.seller['email']))
        thread = self.start_chat()
        self.db.values[PREFIX + 'listing:' + self.item]['seller_email'] = 'different@example.invalid'
        self.ready()
        self.assertIsNone(self.claim())
        self.assertEqual(self.queue.due(), [])

    def test_blocked_conversation_or_participant_suppresses_pending_alert(self):
        for who in ('conversation', 'buyer', 'seller'):
            with self.subTest(who=who):
                # Restore only our synthetic accounts/conversation between cases.
                for uid in (self.buyer['id'], self.seller['id']): self.store.set_account_status(uid, 'active', 'admin')
                thread = self.start_chat()
                self.store.safety(thread, self.buyer['id'], 'unblock')
                self.send(thread, self.buyer['id'], text='Another message')
                if who == 'conversation': self.store.safety(thread, self.seller['id'], 'block')
                else: self.store.set_account_status(getattr(self, who)['id'], 'blocked', 'admin')
                self.ready()
                self.assertIsNone(self.claim())
                self.assertEqual(self.queue.due(), [])
                if who == 'conversation': self.store.safety(thread, self.seller['id'], 'unblock')

    def test_opt_out_suppresses_pending_alert_and_only_future_activity_requeues(self):
        thread = self.start_chat()
        self.store.set_email_notifications(self.seller['id'], False)
        self.ready()
        self.assertIsNone(self.claim())
        self.store.set_email_notifications(self.seller['id'], True)
        self.assertEqual(self.queue.due(), [])
        self.send(thread, self.buyer['id'], text='New activity after enabling alerts')
        self.ready()
        self.assertIsNotNone(self.claim())

    def test_customer_read_cancels_alert_support_read_does_not_and_polling_has_no_extra_writes(self):
        thread = self.start_chat()
        self.store.admin_messages(thread)
        self.assertTrue(self.row(thread).get('due_key'))
        self.store.conversation(thread, self.seller['id'], mark_read=True)
        self.assertFalse(self.row(thread).get('due_key'))
        before = deepcopy(self.db.values)
        self.store.conversation(thread, self.seller['id'], after=1, mark_read=True)
        self.assertEqual(self.db.values, before)
        self.ready()
        self.assertEqual(self.queue.due(), [])

    def test_initial_paginated_read_only_acknowledges_returned_messages(self):
        thread = self.start_chat()
        with patch.object(self.store, '_rate'):
            for index in range(53): self.send(thread, self.buyer['id'], text=str(index))
        first = self.store.conversation(thread, self.seller['id'], mark_read=True)
        self.assertTrue(first['has_more'])
        self.assertEqual(self.row(thread)['read_seq'], 50)
        self.assertTrue(self.row(thread).get('due_key'))
        self.store.conversation(thread, self.seller['id'], after=50, mark_read=True)
        self.assertEqual(self.row(thread)['read_seq'], 54)
        self.assertFalse(self.row(thread).get('due_key'))

    def test_repeat_activity_is_coalesced_during_per_chat_cooldown(self):
        thread = self.start_chat()
        self.ready()
        job = self.claim()
        self.queue.complete(job, receipt='receipt')
        for index in range(5): self.send(thread, self.buyer['id'], text=str(index))
        self.ready()
        self.assertEqual(self.queue.due(), [])
        self.clock.advance(alerts.COOLDOWN)
        self.assertEqual(len(self.queue.due()), 1)
        second = self.claim()
        self.assertEqual(second['attempt']['seq'], 6)
        self.assertNotEqual(second['attempt']['id'], job['attempt']['id'])

    def test_continuing_unread_activity_does_not_postpone_the_first_alert(self):
        thread = self.start_chat()
        for index in range(5):
            self.clock.advance(3)
            self.send(thread, self.buyer['id'], text=str(index))
        self.assertEqual(len(self.queue.due()), 1)
        self.assertEqual(self.claim()['attempt']['seq'], 6)

    def test_delayed_acceptance_keeps_a_full_gap_before_the_next_alert(self):
        thread = self.start_chat()
        self.ready()
        first = self.claim()
        self.queue.complete(first, error=EmailDeliveryError('offline', retryable=True))
        self.send(thread, self.buyer['id'], text='More unread activity')
        self.clock.advance(alerts.COOLDOWN + 1)
        retry = self.claim()
        self.assertEqual(retry['attempt']['id'], first['attempt']['id'])
        self.queue.complete(retry, receipt='delayed-receipt')
        self.ready()
        self.assertEqual(self.queue.due(), [])
        self.clock.advance(alerts.COOLDOWN)
        self.assertEqual(self.claim()['attempt']['seq'], 2)

    def test_provider_failure_preserves_saved_chat_and_retries_exact_frozen_payload(self):
        thread = self.start_chat()
        self.ready()
        first = self.claim()
        frozen = deepcopy(first['attempt'])
        self.queue.complete(first, error=EmailDeliveryError('offline', retryable=True))
        self.send(thread, self.buyer['id'], kind='offer', amount='170')
        self.clock.advance(alerts.RETRY_DELAYS[0] + 1)
        retry = self.claim()
        for field in ('id', 'seq', 'recipient', 'sender', 'subject', 'html', 'text'):
            self.assertEqual(retry['attempt'][field], frozen[field])
        self.queue.complete(retry, receipt='same-provider-receipt')
        self.assertEqual(len(self.store.conversation(thread, self.seller['id'])['messages']), 2)
        self.clock.advance(alerts.COOLDOWN)
        self.assertEqual(self.claim()['attempt']['seq'], 2)

    def test_crash_lease_resumes_same_attempt_and_stale_worker_cannot_complete(self):
        self.start_chat()
        self.ready()
        stale_candidate = self.queue.due()[0]
        first = self.claim()
        self.assertIsNone(self.queue.claim(stale_candidate, SENDER))
        self.assertEqual(self.queue.due(), [])
        self.clock.advance(alerts.LEASE + 1)
        recovered = self.claim()
        self.assertEqual(first['attempt']['id'], recovered['attempt']['id'])
        self.assertFalse(self.queue.complete(first, receipt='stale-receipt'))
        self.assertTrue(self.queue.complete(recovered, receipt='receipt'))

    def test_expired_provider_idempotency_window_is_not_replayed(self):
        thread = self.start_chat()
        self.ready()
        self.claim()
        self.clock.advance(alerts.RETRY_AGE + 1)
        self.assertIsNone(self.claim())
        self.assertEqual(self.row(thread)['last_outcome'], 'uncertain')
        self.assertEqual(self.queue.due(), [])

    def test_retry_limit_and_permanent_provider_rejection_do_not_loop(self):
        thread = self.start_chat()
        self.ready()
        for index in range(6):
            job = self.claim()
            self.assertIsNotNone(job)
            self.queue.complete(job, error=EmailDeliveryError('offline', retryable=True))
            self.clock.advance(2000)
        self.assertEqual(self.queue.due(), [])
        self.assertEqual(self.row(thread)['last_outcome'], 'uncertain')
        self.send(thread, self.buyer['id'], text='Later activity')
        self.ready()
        job = self.claim()
        self.queue.complete(job, error=EmailDeliveryError('rejected', status_code=403))
        self.assertEqual(self.row(thread)['last_outcome'], 'failed')
        self.assertEqual(self.queue.due(), [])

    def test_recipient_budget_covers_multiple_conversations(self):
        self.start_chat()
        self.ready()
        first = self.claim()
        self.queue.complete(first, receipt='one')
        budget = self.db.values[PREFIX + 'notice-budget:' + alerts.digest(self.seller['email'])]
        self.clock.advance(alerts.COOLDOWN)
        budget.update(count=alerts.HOURLY_LIMIT, window=int(self.clock() // 3600))
        thread = self.store.start(self.other['id'], self.item, payload())['id']
        self.ready()
        self.assertIsNone(self.claim())
        self.assertEqual(self.queue.due(), [])
        self.clock.advance(3600)
        self.assertIsNotNone(self.claim())


class TransportTests(AlertSetup):
    def test_provider_acceptance_then_database_outage_does_not_send_a_duplicate(self):
        self.start_chat()
        self.ready()
        accepted = {}
        def provider(job, env):
            accepted.setdefault(job['attempt']['id'], 'one-receipt')
            return accepted[job['attempt']['id']]
        worker = alerts.NotificationWorker(self.queue, environ=ENV, delivery=provider)
        with patch.object(worker.stop, 'wait', return_value=False):
            with patch.object(self.queue, 'complete', side_effect=OSError('synthetic commit outage')):
                with self.assertRaises(OSError): worker.run_once()
            self.clock.advance(alerts.LEASE + 1)
            self.assertEqual(worker.run_once(), 1)
        self.assertEqual(len(accepted), 1)
        self.assertEqual(self.queue.due(), [])

    def test_reuses_paid_resend_when_marketing_is_off_with_one_recipient_and_stable_key(self):
        self.start_chat()
        self.ready()
        job = self.claim()
        provider = Mock()
        provider.send.return_value = EmailDeliveryResult('resend', 'synthetic-provider-receipt', 1)
        factory = Mock(return_value=provider)
        receipt = alerts.deliver(job, ENV, provider_factory=factory)
        config = factory.call_args.args[0]
        self.assertEqual(config.recipient, self.seller['email'])
        self.assertEqual(config.sender, SENDER)
        self.assertEqual(config.api_key, ENV['RESEND_MARKETING_API_KEY'])
        self.assertEqual(factory.call_args.kwargs['max_attempts'], 1)
        self.assertEqual(provider.send.call_args.kwargs['idempotency_key'], 'marketplace-alert/' + job['attempt']['id'])
        self.assertEqual(receipt, 'synthetic-provider-receipt')
        self.assertEqual(provider.send.call_args.args[0].attachments, ())
        with patch('requests.post') as post:
            alerts._NoRedirectSession().post('https://api.resend.com/emails', json={})
            self.assertFalse(post.call_args.kwargs['allow_redirects'])

    def test_worker_network_failure_does_not_propagate_to_chat(self):
        thread = self.start_chat()
        self.ready()
        delivery = Mock(side_effect=EmailDeliveryError('synthetic secret never logged', retryable=True))
        worker = alerts.NotificationWorker(self.queue, environ=ENV, delivery=delivery)
        with patch.object(worker.stop, 'wait', return_value=False), self.assertLogs(alerts.LOG, level='WARNING') as log:
            self.assertEqual(worker.run_once(), 1)
        self.assertNotIn('synthetic secret', '\n'.join(log.output))
        self.assertEqual(self.row(thread)['last_outcome'], 'retry')
        self.assertEqual(len(self.store.conversation(thread, self.buyer['id'])['messages']), 1)


class PreferenceApiTests(AlertSetup):
    def setUp(self):
        super().setUp()
        self.patches = [patch.object(customer_api, 'ChatStore', return_value=self.store),
                        patch('marketplace_accounts.Provider', return_value=self.provider)]
        for item in self.patches: item.start()
        api._RATE.clear()
        self.client = TestClient(Starlette(routes=[Route(p, f, methods=list(m)) for p, f, m in api.ROUTES]), base_url=core.PUBLIC_ORIGIN)
        self.origin = {'Origin': core.PUBLIC_ORIGIN}
    def tearDown(self):
        self.client.close()
        for item in reversed(self.patches): item.stop()
    def login(self, bearer):
        self.client.cookies.set(COOKIE, bearer, domain='sports-cave-image-factory.onrender.com', path='/marketplace')
    def test_preferences_require_verified_session_same_origin_and_ignore_target_uid(self):
        path = '/marketplace/api/auth/notifications'
        self.assertEqual(self.client.post(path, json={'email_notifications': False}, headers=self.origin).status_code, 401)
        self.login(self.bearer)
        self.assertEqual(self.client.post(path, json={'email_notifications': False}).status_code, 403)
        self.assertEqual(self.client.post(path, json={'email_notifications': 'on'}, headers=self.origin).status_code, 400)
        result = self.client.post(path, json={'email_notifications': False, 'user_id': self.seller['id']}, headers=self.origin)
        self.assertEqual(result.status_code, 200)
        self.assertFalse(self.accounts.authenticate(self.bearer)['email_notifications'])
        self.assertTrue(self.accounts.authenticate(self.seller_bearer).get('email_notifications', True))
        self.assertIn('Save email preference', self.client.get('/marketplace/account').text)
    def test_authenticated_poll_acknowledges_only_this_customer_messages(self):
        thread = self.start_chat()
        self.login(self.other_bearer)
        path = '/marketplace/api/conversations/' + thread + '/messages'
        self.assertNotEqual(self.client.get(path).status_code, 200)
        self.assertTrue(self.row(thread).get('due_key'))
        self.login(self.seller_bearer)
        self.assertEqual(self.client.get(path).status_code, 200)
        self.assertFalse(self.row(thread).get('due_key'))


class LifecycleTests(unittest.TestCase):
    def test_worker_is_disabled_for_local_previews_or_master_switch(self):
        self.assertFalse(alerts.enabled({}))
        self.assertFalse(alerts.enabled({**ENV, 'RENDER': 'false'}))
        self.assertFalse(alerts.enabled({**ENV, 'MARKETPLACE_NOTIFICATIONS_ENABLED': 'false'}))
        with patch.dict('os.environ', {}, clear=True), patch.object(alerts, 'NotificationWorker') as worker:
            self.assertIsNone(alerts.start_worker())
            worker.assert_not_called()
    def test_lifespan_starts_once_and_closes_worker_without_handling_other_requests(self):
        factory, worker = Mock(), Mock()
        factory.return_value = worker
        received = []
        async def app(scope, receive, send):
            if scope['type'] != 'lifespan':
                received.append(scope['type']); return
            await receive()
            await send({'type': 'lifespan.startup.complete'})
            await send({'type': 'lifespan.startup.complete'})
            await receive()
            await send({'type': 'lifespan.shutdown.complete'})
        async def exercise():
            messages = iter([{'type': 'lifespan.startup'}, {'type': 'lifespan.shutdown'}])
            async def receive(): return next(messages)
            async def send(message): received.append(message['type'])
            lifecycle = alerts.NotificationLifecycle(app, factory)
            await lifecycle({'type': 'http'}, receive, send)
            await lifecycle({'type': 'lifespan'}, receive, send)
        asyncio.run(exercise())
        factory.assert_called_once()
        worker.close.assert_called_once()
        self.assertIn('http', received)
        self.assertIn('lifespan.shutdown.complete', received)
