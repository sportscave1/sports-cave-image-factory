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

    def test_schema_check_is_read_only_against_actual_migrations(self):
        import ads_schema
        from types import SimpleNamespace
        ads_schema.reset()
        self.addCleanup(ads_schema.reset)
        ads_schema.ensure(SimpleNamespace(connect=SQLConnection, get_database_url=lambda: 'local-fixture'))

    def test_stale_worker_cannot_overwrite_or_extend_replaced_lease(self):
        from meta_posting_service import PostingBusyError
        client = FakePostingClient(fail_at='ad_2')
        store = SupabasePostingStore()
        request = request_for(submission_id=str(uuid.uuid4()))
        with self.assertRaises(Exception):
            MetaPostingService(client=client,store=store).create_paused_campaign(request)
        previous = store.get(request.submission_id)
        with self.assertRaises(PostingBusyError):
            store.update_stage(request.submission_id, 'CAMPAIGN_CREATED', campaign_id='wrong')
        self.assertEqual(store.get(request.submission_id)['campaign_id'], previous['campaign_id'])

    def test_lost_checkpoint_ack_restart_reuses_committed_objects(self):
        from meta_posting_service import PostingError
        client, store = FakePostingClient(), SupabasePostingStore()
        request = request_for(submission_id=str(uuid.uuid4()))
        update = store.update_stage
        fired = []
        def lose_ack(identity,status,**fields):
            result = update(identity,status,**fields)
            if status == 'IMAGE_UPLOADED' and not fired:
                fired.append(True)
                raise TimeoutError('lost acknowledgement')
            return result
        with patch.object(store,'update_stage',side_effect=lose_ack):
            with self.assertRaises(PostingError):
                MetaPostingService(client=client,store=store).create_paused_campaign(request)
        saved = SupabasePostingStore().get(request.submission_id)
        result = MetaPostingService(client=client,store=SupabasePostingStore()).create_paused_campaign(request)
        self.assertEqual(result['status'],'COMPLETE')
        self.assertEqual(result['campaign_id'],saved['campaign_id'])
        self.assertEqual(client.calls.count('campaign'),1)
        self.assertEqual(client.calls.count('adset'),1)
        self.assertEqual(client.calls.count('ad_image'),3)
        self.assertEqual(len(client.copy_ads),3)

    def test_legacy_hidden_failure_cannot_be_reset_by_retry_reservation(self):
        request = request_for(submission_id=str(uuid.uuid4()))
        store=SupabasePostingStore()
        store.reserve(request)
        store.update_stage(request.submission_id,'FAILED',safe_error='The Meta request failed. Unknown outcome.')
        self.assertFalse(store.reserve(request,retry=True))
        self.assertEqual(store.get(request.submission_id)['status'],'FAILED')

    def test_background_error_cannot_overwrite_complete_checkpoint(self):
        request = request_for(submission_id=str(uuid.uuid4()))
        result = MetaPostingService(client=FakePostingClient(),store=SupabasePostingStore()).create_paused_campaign(request)
        SupabasePostingStore().update_stage(request.submission_id,'AMBIGUOUS',safe_error='late error')
        self.assertEqual(SupabasePostingStore().get(request.submission_id)['status'],'COMPLETE')


if __name__ == '__main__': unittest.main()
