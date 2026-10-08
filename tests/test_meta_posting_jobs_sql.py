"""Run with META_POSTING_SQL_TEST=1 and the localhost-only fixture on 8890."""
import os
import unittest
import uuid
from unittest.mock import patch

from tests.crm_db_fixture import Connection
from tests.test_meta_posting import FakePostingClient, request_for
from meta_posting_jobs import PostingJobs, confirmed_ads
from meta_posting_service import MetaPostingService, SupabasePostingStore


class Cursor:
    def __init__(self, connection): self.connection = connection
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, sql, args=()): self.result = self.connection.execute(sql, args)
    def fetchone(self): return self.result.fetchone()
    def fetchall(self): return self.result.fetchall()


class SQLConnection(Connection):
    def cursor(self): return Cursor(self)
    def commit(self): pass  # The fixture commits on context exit.


class Backend:
    def ensure_ads_schema(self): pass
    def is_configured(self): return True
    def connect(self): return SQLConnection()


@unittest.skipUnless(os.environ.get('META_POSTING_SQL_TEST') == '1', 'requires local PostgreSQL fixture')
class SQLJobTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, CRM_FIXTURE_SQL_PORT='8890')
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.backend = patch.object(SupabasePostingStore, '_backend', return_value=Backend())
        self.backend.start()
        self.addCleanup(self.backend.stop)

    def test_reservation_hydration_partial_retry_and_durable_results(self):
        client = FakePostingClient(fail_at='ad_2')
        jobs = PostingJobs(service_factory=lambda **kw: MetaPostingService(client=client, **kw))
        self.addCleanup(jobs.pool.shutdown, wait=True)
        request = request_for(submission_id=str(uuid.uuid4()))
        identity = jobs.submit(request)
        jobs.jobs[identity]['future'].result(timeout=20)
        row = jobs.snapshot(identity)
        self.assertEqual(row['status'], 'FAILED', row.get('safe_error'))
        self.assertEqual(confirmed_ads(row), (1, 3))
        first_id = row['ad_results'][0]['meta_ad_id']
        self.assertFalse(SupabasePostingStore().reserve(request))
        client.fail_at = ''
        jobs.retry(identity)
        jobs.jobs[identity]['future'].result(timeout=20)
        row = SupabasePostingStore().get(identity)
        self.assertEqual(row['status'], 'COMPLETE', row.get('safe_error'))
        self.assertEqual(confirmed_ads(row), (3, 3))
        self.assertEqual(row['ad_results'][0]['meta_ad_id'], first_id)
        self.assertFalse(SupabasePostingStore().reserve(request, retry=True))
        self.assertEqual(client.calls.count('campaign'), 1)
        self.assertEqual(client.calls.count('adset'), 1)
        self.assertIn(identity, [r['submission_id'] for r in SupabasePostingStore().recent()])

    def test_pending_reservation_is_atomic_and_retains_original_identity(self):
        request = request_for(submission_id=str(uuid.uuid4()))
        store = SupabasePostingStore()
        self.assertTrue(store.reserve(request))
        self.assertFalse(SupabasePostingStore().reserve(request))
        self.assertEqual(store.get(request.submission_id)['status'], 'VALIDATING')
        self.assertFalse(store.reserve(request, retry=True))


if __name__ == '__main__': unittest.main()
