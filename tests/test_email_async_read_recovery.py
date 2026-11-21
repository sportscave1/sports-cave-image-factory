"""Deterministic queued-read recovery; synthetic data, no sockets or database."""
from concurrent.futures import Future
import unittest
from unittest.mock import Mock

from support_email_provider import MailboxError
from support_email_reads import ReadService


class AsyncReadRecovery(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.reads = ReadService(Mock(), Mock(), clock=lambda: self.now)
        self.reads.pool.shutdown(wait=True)
        self.reads.pool = Mock()
        self.future = Future()
        self.reads.pool.submit.return_value = self.future
        self.addCleanup(self.reads.close)
        self.key = ('read_message', ('INBOX', '1', '42', '<synthetic>'), 0)
        self.loader = Mock()

    def pending(self):
        with self.assertRaises(MailboxError) as caught:
            self.reads.request(self.key, self.loader)
        self.assertEqual(caught.exception.code, 'pending')

    def test_async_failure_is_delivered_before_retry_even_after_ttl(self):
        for code in ('timeout', 'authentication', 'tls', 'deferred', 'busy'):
            with self.subTest(code=code):
                self.future = Future()
                self.reads.pool.submit.return_value = self.future
                self.pending()
                error = MailboxError('Safe synthetic failure', code=code,
                                     stage='tcp', retryable=True, retry_after=45)
                self.future.set_exception(error)
                self.now += 100
                with self.assertRaises(MailboxError) as caught:
                    self.reads.request(self.key, self.loader)
                self.assertIs(caught.exception, error)
                self.assertEqual(caught.exception.retry_after, 45)
                self.assertNotIn(self.key, self.reads.jobs)
        self.assertEqual(self.reads.pool.submit.call_count, 5)

    def test_slow_success_stays_cached_for_full_ttl_after_completion(self):
        self.pending()
        self.now += 60  # Longer than the old creation-based 20 second TTL.
        self.future.set_result({'text': 'Synthetic body'})
        self.now += 19
        result = self.reads.request(self.key, self.loader)
        result['text'] = 'Caller edit'
        self.assertEqual(self.reads.request(self.key, self.loader),
                         {'text': 'Synthetic body'})
        self.reads.pool.submit.assert_called_once()
        self.now += 2
        self.reads.pool.submit.return_value = Future()
        self.pending()
        self.assertEqual(self.reads.pool.submit.call_count, 2)

    def test_pending_polls_share_one_job_and_delivered_failure_can_recover(self):
        for _ in range(50):self.pending()
        self.future.set_exception(MailboxError('Synthetic offline', code='timeout'))
        with self.assertRaises(MailboxError) as caught:
            self.reads.request(self.key, self.loader)
        self.assertEqual(caught.exception.code, 'timeout')
        recovered = Future()
        recovered.set_result({'text': 'Recovered'})
        self.reads.pool.submit.return_value = recovered
        self.assertEqual(self.reads.request(self.key, self.loader), {'text': 'Recovered'})
        self.assertEqual(self.reads.pool.submit.call_count, 2)

    def test_late_completion_cannot_replace_a_new_generation_job(self):
        self.pending()
        self.reads.refresh()
        old = self.future
        replacement = Future()
        self.reads.jobs[self.key] = (replacement, 999)
        old.set_result({'text': 'Obsolete'})
        self.assertIs(self.reads.jobs[self.key][0], replacement)
        self.assertEqual(self.reads.jobs[self.key][1], 999)

    def test_cancelled_job_is_replaced_without_cancelling_an_active_read(self):
        self.pending()
        self.future.cancel()
        self.reads.pool.submit.return_value = Future()
        self.pending()
        self.assertEqual(self.reads.pool.submit.call_count, 2)

    def test_raw_worker_timeout_is_classified_and_released_for_recovery(self):
        self.pending()
        self.future.set_exception(TimeoutError('Synthetic private provider text'))
        with self.assertRaises(MailboxError) as caught:
            self.reads.request(self.key, self.loader)
        self.assertEqual(caught.exception.code, 'timeout')
        self.assertNotIn('private', str(caught.exception))
        self.assertNotIn(self.key, self.reads.jobs)

    def test_wait_timeout_keeps_active_job_instead_of_opening_another_read(self):
        self.pending()
        # Simulate the bounded wait expiring while its worker is still active.
        self.future.result = Mock(side_effect=TimeoutError())
        with self.assertRaises(MailboxError):
            self.reads.request(self.key, self.loader, wait=True)
        self.assertIs(self.reads.jobs[self.key][0], self.future)
        self.reads.pool.submit.assert_called_once()


if __name__ == '__main__':
    unittest.main()
