"""Local performance contracts: identity, paging, threading and completion."""
import asyncio
from concurrent.futures import Future
from copy import deepcopy
import json
import random
import threading
import time
import unittest
import uuid
from unittest.mock import Mock, patch

from tests.email_v2_fixtures import CONFIG, USER, MailboxFixture
from tests.test_email_outlook_v2a import Reliability
from support_email_logic import build_threads
from support_email_provider import MailboxError
from support_email_reads import AsyncInbox, ReadService
from tests.test_email_inbox_reliability import Provider
from tests.fixtures.email_threading_reference import build_threads as reference
import support_email_completion as completion


class Threading(unittest.TestCase):
    def test_matches_original_with_missing_roots_cycles_duplicates_and_fallbacks(self):
        for seed in range(30):
            rng = random.Random(seed)
            rows = MailboxFixture(80).messages
            for i, row in enumerate(rows):
                row['subject'] = rng.choice(['A', 'Re: A', 'Fwd: A', 'B', 'Re: B', ''])
                row['sender']['email'] = rng.choice(['one@example.test', 'two@example.test', CONFIG.address])
                if rng.random() < .5:
                    row['references'] = [f'<fixture-{rng.randrange(100)}@example.test>' for _ in range(rng.randrange(4))]
                if rng.random() < .3:row['in_reply_to'] = [f'<fixture-{rng.randrange(100)}@example.test>']
            rows += deepcopy(rows[:3])
            self.assertEqual(build_threads(deepcopy(rows), CONFIG.address), reference(deepcopy(rows), CONFIG.address))


class PerformanceContracts(unittest.TestCase):
    setUp = Reliability.setUp
    event = Reliability.event

    def test_cursor_fetches_only_next_fifty_and_keeps_new_arrivals_out_of_old_page(self):
        self.event('load_more')
        for future, _ in list(self.reads.jobs.values()):future.result(timeout=3)
        self.w.state.update(load_retry_at=0)
        self.w.load()
        self.assertEqual(len(self.w.state['snapshot']['messages']), 75)
        calls = [c for c in self.provider.calls if c[0]=='headers']
        self.assertEqual(calls[-1][2], 50)
        self.assertEqual(calls[-1][3]['before_uid'], 26)
        self.assertEqual(calls[-1][3]['uidvalidity'], '500')
        self.assertEqual(len({m['uid'] for m in self.w.state['snapshot']['messages']}), 75)
        self.assertFalse(any(c[0]=='body' for c in self.provider.calls))

    def test_metadata_is_after_first_list_and_cannot_open_a_draft(self):
        self.w.state.pop('settings_available', None)
        self.w.state['initial_load_pending'] = True
        with patch('support_email_store.load_email_settings') as settings:
            self.event('load_initial_mailbox')
            settings.assert_not_called()
            self.assertTrue(self.w.model()['threads'])
            self.assertIsNone(self.w.model()['draft'])

    def test_body_action_reuses_inflight_read_despite_changed_flags(self):
        message = self.provider.messages[0]
        started, release = threading.Event(), threading.Event()
        original = self.provider.read_message
        def load(row):
            started.set();release.wait(2);return original(row)
        with patch.object(self.provider, 'read_message', side_effect=load) as read:
            with self.assertRaises(MailboxError):self.w.imap.read_message(message)
            self.assertTrue(started.wait(1))
            changed = dict(message, flags=('\\Seen',), unread=False)
            release.set()
            self.w.imap.read_body_for_action(changed)
            self.assertEqual(read.call_count, 1)

    def test_uid_reuse_never_shares_body_job(self):
        row = self.provider.messages[0]
        key = self.w.imap.body_key(row)
        for field in ('folder', 'uidvalidity', 'uid', 'message_id'):
            self.assertNotEqual(key, self.w.imap.body_key(dict(row, **{field: 'different'})))

    def test_pending_other_folder_does_not_block_cached_inbox(self):
        self.w.state.update(connection_code='pending', recovery_state='waiting', load_retry_at=time.monotonic()+100)
        self.event('folder', folder='INBOX')
        self.assertEqual(len(self.w.model()['threads']), 50)
        self.assertFalse(self.w.model()['read_pending'])

    def test_body_cancels_only_queued_optional_history(self):
        queued, active = Future(), Future()
        active.set_running_or_notify_cancel()
        self.reads.jobs[('related_headers_many', 'queued')] = (queued, time.monotonic()+20)
        self.reads.jobs[('related_headers_many', 'active')] = (active, time.monotonic()+20)
        self.w.imap.read_body_for_action(self.provider.messages[0])
        self.assertTrue(queued.cancelled())
        self.assertFalse(active.cancelled())
        active.set_result([])

    def test_unavailable_settings_cannot_send(self):
        self.event('compose', mode='new')
        self.w.state['settings_available'] = False
        self.event('send', operation_id=self.w.state['draft']['operation_id'])
        self.assertIn('settings', self.w.state['notice'])
        self.assertFalse(self.w.state.get('send_result', {}).get('status') in ('accepted','in_progress'))

    def test_body_paints_before_read_flag_and_stale_flag_event_is_ignored(self):
        self.event('open_thread', thread_key=self.w.state['threads'][0]['thread_key'])
        key = self.w.state['active_message']
        for future, _ in list(self.reads.jobs.values()):future.result(timeout=3)
        self.event('load_visible_body', message_key=key)
        self.assertTrue(any(m['expanded'] for m in self.w.model()['messages']))
        self.assertFalse(any(c[0]=='flag' for c in self.provider.calls))
        self.assertEqual(self.w.state['read_mark_pending'], key)
        self.event('mark_visible_read', message_key=key)
        count = len([c for c in self.provider.calls if c[0]=='flag'])
        self.assertEqual(count, 1)
        self.event('mark_visible_read', message_key=key)
        self.assertEqual(len([c for c in self.provider.calls if c[0]=='flag']), count)


class Completion(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.future = Future()
        self.scope = str(uuid.uuid4())
        self.ticket = completion.issue(self.future, 'actor', self.scope)
        self.request = Mock(headers={'X-Email-Read':self.ticket})
        self.claims = dict(sub='actor', allowed_routes=['Email'], exp=time.time()+60)
        self.patcher = patch('support_email_access.current_email_claims', side_effect=lambda _: self.claims)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.addCleanup(completion.revoke, self.scope)

    async def test_worker_completion_wakes_without_polling_or_content(self):
        task = asyncio.create_task(completion.read_ready(self.request))
        await asyncio.sleep(.01)
        self.assertFalse(task.done())
        self.future.set_result({'secret_body': 'never transport this'})
        response = await asyncio.wait_for(task, 1)
        self.assertEqual(json.loads(response.body), {'ready': True})
        self.assertEqual(response.headers['cache-control'], 'no-store')

    async def test_actor_and_permission_denied(self):
        for claims in ({}, dict(self.claims, sub='other'), dict(self.claims, allowed_routes=[]), dict(self.claims, exp=0)):
            self.claims = claims
            self.assertEqual((await completion.read_ready(self.request)).status_code, 403)

    async def test_revoked_while_waiting_is_denied(self):
        task = asyncio.create_task(completion.read_ready(self.request))
        await asyncio.sleep(.01)
        completion.revoke(self.scope)
        self.future.set_result(None)
        self.assertEqual((await task).status_code, 403)

    async def test_new_selection_invalidates_old_ticket(self):
        completion.issue(Future(), 'actor', self.scope)
        self.assertEqual((await completion.read_ready(self.request)).status_code, 403)

    async def test_expired_and_unknown_ticket_are_denied(self):
        with patch('support_email_completion.time.monotonic', return_value=time.monotonic()+31):
            self.assertEqual((await completion.read_ready(self.request)).status_code, 403)
        self.request.headers={'X-Email-Read':'unknown'}
        self.assertEqual((await completion.read_ready(self.request)).status_code, 403)

    async def test_ticket_registry_is_bounded(self):
        scopes = [str(uuid.uuid4()) for _ in range(270)]
        try:
            for scope in scopes:completion.issue(Future(), 'actor', scope)
            self.assertLessEqual(len(completion._tickets), 256)
        finally:
            for scope in scopes:completion.revoke(scope)

    async def test_duplicate_wait_is_bounded(self):
        task = asyncio.create_task(completion.read_ready(self.request))
        await asyncio.sleep(.01)
        self.assertEqual((await completion.read_ready(self.request)).status_code, 409)
        self.future.set_exception(ValueError('private error'))
        self.assertEqual(json.loads((await task).body), {'ready': True})

    async def test_cancelled_worker_wakes_handler_without_leaking_a_result(self):
        self.future.cancel()
        self.assertEqual(json.loads((await completion.read_ready(self.request)).body), {'ready': True})


del Reliability  # Reuse setup without collecting the imported test class twice.

if __name__ == '__main__':unittest.main()
