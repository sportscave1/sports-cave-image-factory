"""No network: exercise background execution with the real posting service."""
from copy import deepcopy
from threading import Event, RLock
import unittest
from unittest.mock import Mock

from meta_posting_jobs import PostingJobs, confirmed_ads
from meta_posting_service import MetaPostingService, PostingValidationError
from tests.test_meta_posting import FakePostingClient, FakePostingStore, request_for


class Ledger(FakePostingStore):
    def __init__(self):
        super().__init__()
        self.lock = RLock()

    def reserve(self, request, retry=False):
        with self.lock:
            if not self.record:
                self.record = dict(submission_id=request.submission_id,
                                   request_fingerprint='pending', status='VALIDATING')
                return True
            if retry and self.record['status'] == 'FAILED':
                self.record['status'] = 'VALIDATING'
                return True
            return False

    def claim(self, data, lease_token):
        with self.lock:
            if self.record.get('request_fingerprint') == 'pending':
                self.record = deepcopy(data)
            self.record['status'] = 'VALIDATING'
            return {'claimed': True, 'record': deepcopy(self.record)}

    def get(self, identity):
        with self.lock:
            return deepcopy(self.record)

    def update_stage(self, *args, **kwargs):
        with self.lock:
            return super().update_stage(*args, **kwargs)


class PostingJobTests(unittest.TestCase):
    def make_jobs(self, store=None, client=None, factory=None):
        store = store or Ledger()
        client = client or FakePostingClient()
        factory = factory or (lambda **kw: MetaPostingService(client=client, **kw))
        jobs = PostingJobs(lambda: store, factory)
        self.addCleanup(jobs.pool.shutdown, wait=True)
        return jobs, store, client

    def wait(self, jobs, identity):
        jobs.jobs[identity]['future'].result(timeout=10)
        return jobs.snapshot(identity)

    def test_submission_returns_before_work_finishes_and_duplicate_is_not_dispatched(self):
        entered, release = Event(), Event()
        def run(request):
            entered.set()
            release.wait(5)
        factory = Mock(return_value=Mock(create_paused_campaign=run))
        jobs, store, _ = self.make_jobs(factory=factory)
        identity = jobs.submit(request_for())
        self.assertTrue(entered.wait(2))
        self.assertTrue(jobs.snapshot(identity)['running_here'])
        for _ in range(5):
            self.assertEqual(jobs.submit(request_for()), identity)
        # A second web worker sees the same persistent reservation.
        other, _, _ = self.make_jobs(store=store, factory=factory)
        self.assertEqual(other.submit(request_for()), identity)
        self.assertEqual(factory.call_count, 1)
        release.set()
        self.wait(jobs, identity)

    def test_complete_uses_confirmed_paused_ids_and_survives_new_monitor(self):
        jobs, store, client = self.make_jobs()
        identity = jobs.submit(request_for())
        row = self.wait(jobs, identity)
        self.assertEqual(row['status'], 'COMPLETE')
        self.assertEqual(confirmed_ads(row), (3, 3))
        self.assertTrue(row['campaign_id'])
        self.assertTrue(row['adset_id'])
        self.assertEqual(row['campaign_configured_status'], 'PAUSED')
        self.assertEqual(row['adset_configured_status'], 'PAUSED')
        other, _, _ = self.make_jobs(store=store)
        self.assertEqual(other.snapshot(identity)['ad_results'], row['ad_results'])
        other.submit(request_for())
        self.assertEqual(client.calls.count('campaign'), 1)
        self.assertFalse(other.jobs)

    def test_partial_failure_retry_preserves_resources(self):
        jobs, store, client = self.make_jobs(client=FakePostingClient(fail_at='ad_2'))
        identity = jobs.submit(request_for())
        failed = self.wait(jobs, identity)
        self.assertEqual(failed['status'], 'FAILED')
        self.assertTrue(failed['can_retry'])
        first = failed['ad_results'][0]['meta_ad_id']
        self.assertTrue(first)
        self.assertTrue(failed['safe_error'])
        client.fail_at = ''
        jobs.retry(identity)
        complete = self.wait(jobs, identity)
        self.assertEqual(complete['status'], 'COMPLETE')
        self.assertEqual(complete['ad_results'][0]['meta_ad_id'], first)
        self.assertEqual(complete['campaign_id'], failed['campaign_id'])
        self.assertEqual(complete['adset_id'], failed['adset_id'])
        self.assertEqual(client.calls.count('campaign'), 1)
        self.assertEqual(client.calls.count('adset'), 1)
        self.assertEqual(len(client.copy_ads), 3)

    def test_validation_failure_is_visible_without_meta_calls(self):
        service = Mock()
        service.create_paused_campaign.side_effect = PostingValidationError('Invalid creative')
        jobs, _, _ = self.make_jobs(factory=Mock(return_value=service))
        row = self.wait(jobs, jobs.submit(request_for()))
        self.assertEqual(row['status'], 'FAILED')
        self.assertIn('Invalid creative', row['safe_error'])

    def test_uncertain_failure_is_never_replayed(self):
        service = Mock()
        service.create_paused_campaign.side_effect = RuntimeError('lost response')
        jobs, _, _ = self.make_jobs(factory=Mock(return_value=service))
        identity = jobs.submit(request_for())
        row = self.wait(jobs, identity)
        self.assertEqual(row['status'], 'AMBIGUOUS')
        self.assertFalse(row['can_retry'])
        jobs.submit(request_for(), retry=True)
        self.assertEqual(service.create_paused_campaign.call_count, 1)

    def test_progress_never_counts_an_unverified_or_active_ad(self):
        self.assertEqual(confirmed_ads({'ad_results': [
            {'index': 1, 'meta_ad_id': 'one', 'meta_ad_configured_status': 'PAUSED'},
            {'index': 2, 'meta_ad_id': 'two', 'meta_ad_configured_status': 'ACTIVE'},
            {'index': 3, 'meta_ad_id': 'three'},
        ]}), (1, 3))

    def test_live_operation_and_elapsed_time_are_observations_not_retry_triggers(self):
        from unittest.mock import patch
        entered, release = Event(), Event()
        def factory(**kw):
            def run(request):
                kw['progress_callback']('Uploading images to Meta')
                entered.set()
                release.wait(5)
            return Mock(create_paused_campaign=run)
        with patch('meta_posting_jobs.monotonic', return_value=100):
            jobs, _, _ = self.make_jobs(factory=factory)
            identity = jobs.submit(request_for())
            self.assertTrue(entered.wait(2))
        try:
            with patch('meta_posting_jobs.monotonic', return_value=205):
                row = jobs.snapshot(identity)
            self.assertEqual(row['operation'], 'Uploading images to Meta')
            self.assertEqual(row['elapsed_seconds'], 105)
            self.assertEqual(row['operation_seconds'], 105)
            self.assertFalse(row['can_retry'])
        finally:
            release.set()


if __name__ == '__main__':
    unittest.main()
