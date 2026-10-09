"""Fault injection at real service boundaries; all Meta traffic is mocked."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import ads_schema
from meta_ads_client import MetaAdsApiError, MetaAdsAmbiguousResultError
from meta_posting_recovery import KEY, diagnostic, requires_reconciliation
from meta_posting_service import MetaPostingService, PostingError, PostingAmbiguousError
from meta_posting_jobs import PostingJobs
from tests.test_meta_posting import FakePostingClient, FakePostingStore, request_for
from tests.test_meta_posting_jobs import Ledger


class DurableStore(FakePostingStore):
    """Copy values like SQL JSON serialization, not the older fake's aliases."""
    def update_stage(self, identity, status, **fields):
        return deepcopy(super().update_stage(identity, status, **deepcopy(fields)))


class PostingRepairTests(unittest.TestCase):
    def service(self, client, store):
        return MetaPostingService(client=client, store=store)

    def test_rejected_operations_resume_all_three_without_duplicate_objects(self):
        for method in ('create_adset','upload_image','upload_page_photo',
                       'create_canvas_element','create_canvas','instant_experience',
                       'copy_paused_ad_from_template'):
            with self.subTest(method=method):
                store, client = DurableStore(), FakePostingClient()
                original = getattr(client, method)
                with patch.object(client, method, side_effect=MetaAdsApiError('Rejected', error_code=4)):
                    with self.assertRaises(PostingError):
                        self.service(client, store).create_paused_campaign(request_for())
                saved_campaign = store.record.get('campaign_id')
                result = self.service(client, store).create_paused_campaign(request_for())
                self.assertEqual(result['status'], 'COMPLETE')
                self.assertEqual(result['campaign_id'], saved_campaign)
                self.assertEqual(client.calls.count('campaign'), 1)
                self.assertEqual(client.calls.count('adset'), 1)
                self.assertEqual(len(client.copy_ads), 3)
                self.assertEqual([a['meta_ad_configured_status'] for a in result['ad_results']], ['PAUSED']*3)
                self.assertEqual(self.service(client, store).create_paused_campaign(request_for())['status'], 'COMPLETE')
                self.assertEqual(len(client.copy_ads), 3)

    def test_checkpoint_failure_after_resource_creation_reuses_journal_id(self):
        for stage in ('CAMPAIGN_CREATED','ADSET_CREATED','IMAGE_UPLOADED',
                      'PAGE_PHOTO_CREATED','INSTANT_EXPERIENCE_CREATED','AD_CREATED','COMPLETE'):
            with self.subTest(stage=stage):
                store, client = DurableStore(), FakePostingClient()
                update = store.update_stage
                fired = []
                def fail_once(identity, status, **fields):
                    if status == stage and not fired:
                        fired.append(True)
                        raise TimeoutError('private creative payload must not appear')
                    return update(identity, status, **fields)
                with patch.object(store, 'update_stage', side_effect=fail_once):
                    with self.assertRaises(PostingError):
                        self.service(client, store).create_paused_campaign(request_for())
                result = self.service(client, store).create_paused_campaign(request_for())
                self.assertEqual(result['status'], 'COMPLETE')
                self.assertEqual(client.calls.count('campaign'), 1)
                self.assertEqual(client.calls.count('adset'), 1)
                self.assertEqual(client.calls.count('page_photo'), 3)
                self.assertEqual(client.calls.count('canvas'), 3)
                self.assertEqual(len(client.copy_ads), 3)

    def test_uncertain_write_and_restart_never_replay(self):
        for method in ('create_campaign','create_adset','upload_image','upload_page_photo',
                       'create_canvas_element','create_canvas','copy_paused_ad_from_template'):
            with self.subTest(method=method):
                store, client = DurableStore(), FakePostingClient()
                original = getattr(client, method)
                def lost_response(*args, **kwargs):
                    original(*args, **kwargs)
                    raise RuntimeError('unknown response containing private content')
                with patch.object(client, method, side_effect=lost_response):
                    with self.assertRaises(PostingError):
                        self.service(client, store).create_paused_campaign(request_for())
                before = list(client.calls)
                self.assertTrue(requires_reconciliation(store.record))
                with self.assertRaises(PostingAmbiguousError):
                    self.service(client, store).create_paused_campaign(request_for())
                self.assertEqual([c for c in client.calls[len(before):] if not c.startswith('read_')], [])

    def test_generated_start_time_change_does_not_create_another_adset(self):
        from meta_posting_service import build_adset_payload
        store, client = DurableStore(), FakePostingClient()
        update = store.update_stage
        fired=[]
        def fail_once(identity,status,**fields):
            if status=='ADSET_CREATED' and not fired:
                fired.append(True)
                raise TimeoutError('checkpoint failure')
            return update(identity,status,**fields)
        with patch.object(store,'update_stage',side_effect=fail_once):
            with self.assertRaises(PostingError):
                self.service(client,store).create_paused_campaign(request_for())
        def future_payload(**kwargs):
            return {**build_adset_payload(**kwargs),'start_time':'2030-01-01T00:00:00+00:00'}
        with patch('meta_posting_service.build_adset_payload',side_effect=future_payload):
            result=self.service(client,store).create_paused_campaign(request_for())
        self.assertEqual(result['status'],'COMPLETE')
        self.assertEqual(client.calls.count('adset'),1)

    def test_success_response_without_id_is_ambiguous_not_retryable_rejection(self):
        from meta_ads_client import MetaPostingClient
        client=MetaPostingClient(dict(configured=True,ad_account_id='act_123',api_version='v26.0',access_token='test-token',page_id='page-1',page_access_token='test-page'))
        with patch('meta_ads_client._post', return_value={}):
            with self.assertRaises(MetaAdsAmbiguousResultError):
                client.create_campaign({})
            with self.assertRaises(MetaAdsAmbiguousResultError):
                client.upload_page_photo(b'fake',filename='test.jpg',content_type='image/jpeg')

    def test_legacy_hidden_failure_is_not_permission_to_repeat_page_photo(self):
        store, client = DurableStore(), FakePostingClient()
        with patch.object(client, 'upload_page_photo', side_effect=MetaAdsApiError('rejected')):
            with self.assertRaises(PostingError):
                self.service(client, store).create_paused_campaign(request_for())
        store.record['ad_results'][0].pop(KEY)
        store.record['safe_error'] = 'The Meta request failed. Any objects already created remain paused and are listed below.'
        with self.assertRaises(PostingAmbiguousError):
            self.service(client, store).create_paused_campaign(request_for())
        self.assertEqual(client.calls.count('page_photo'), 0)

    def test_diagnostic_has_trace_locations_not_secrets_or_creative_data(self):
        try:
            raise ValueError('customer@example.com secret-token private creative payload')
        except ValueError as error:
            with self.assertLogs('meta_posting_service', 'ERROR') as captured:
                message = diagnostic(error, 'upload_page_photo', request_for().submission_id)
        text = str(captured.output) + message
        for secret in ('customer@example.com','secret-token','private creative payload'):
            self.assertNotIn(secret, text)
        self.assertIn('traceback', text)
        self.assertIn('ValueError', text)
        self.assertIn('upload_page_photo', text)

    def test_resume_checks_actual_paused_status_and_account_before_writes(self):
        from meta_posting_recovery import verify_resume_objects
        from tests.test_meta_posting import existing_target_rows
        from meta_posting_service import PostingValidationError
        campaign, adset = existing_target_rows(campaign_status='PAUSED', adset_status='PAUSED')
        client = SimpleNamespace(ad_account_id='act_123',
            configured_campaign=Mock(return_value=campaign),configured_adset=Mock(return_value=adset))
        record = dict(campaign_id=campaign['id'], adset_id=adset['id'],
                      catalog_id='catalog-1',product_set_id='set-1',pixel_id='pixel-1')
        self.assertEqual(verify_resume_objects(client, record)['campaign']['id'], campaign['id'])
        for field, value in [('configured_status','ACTIVE'),('account_id','another-account')]:
            with self.subTest(field=field):
                changed = dict(campaign, **{field:value})
                client.configured_campaign.return_value = changed
                with self.assertRaises(PostingValidationError):
                    verify_resume_objects(client, record)

    def test_database_outage_after_remote_success_leaves_durable_intent(self):
        store, client = DurableStore(), FakePostingClient()
        update = store.update_stage
        dead = []
        def outage(identity, status, **fields):
            ops = (fields.get('ad_results') or [{}])[0].get(KEY,{})
            if any(o['operation']=='upload_page_photo' and o['state']=='complete' for o in ops.values()):
                dead.append(True)
            if dead:
                raise TimeoutError('database offline')
            return update(identity,status,**fields)
        with patch.object(store,'update_stage',side_effect=outage):
            with self.assertRaises(TimeoutError):
                self.service(client,store).create_paused_campaign(request_for())
        self.assertEqual(client.calls.count('page_photo'),1)
        self.assertTrue(requires_reconciliation(store.record))
        # Simulate a subsequent claim after the failed process lease expired.
        store.record['status']='FAILED'
        with self.assertRaises(PostingAmbiguousError):
            self.service(client,store).create_paused_campaign(request_for())
        self.assertEqual(client.calls.count('page_photo'),1)

    def test_resume_verifies_saved_assets_without_replacement_writes(self):
        from meta_ads_client import MetaPostingClient
        client = SimpleNamespace(config={}, page_access_token='test-only',
            ad_image_details=Mock(return_value={'hash':'image-1'}),
            instant_experience=Mock(return_value={'id':'canvas-1'}),
            creative=Mock(return_value={'id':'creative-1'}),
            ad=Mock(return_value={'id':'ad-1','adset_id':'set-1','configured_status':'PAUSED'}))
        record = {'adset_id':'set-1','ad_results':[dict(meta_image_hash='image-1',
            meta_page_photo_id='photo-1',meta_instant_experience_id='canvas-1',
            meta_creative_id='creative-1',meta_ad_id='ad-1')]}
        with patch('meta_posting_recovery.verify_resume_objects', return_value={}), \
                patch('meta_ads_client._request', return_value={'id':'photo-1'}) as read, \
                patch('meta_ads_client._post', side_effect=AssertionError('No writes allowed')):
            MetaPostingClient.verify_posting_resume(client, record)
            self.assertEqual(read.call_args.args, ('photo-1',))
            for method, invalid in [('ad_image_details', {'hash':'wrong'}),
                                    ('instant_experience', {}), ('creative', {}),
                                    ('ad', {'id':'ad-1','adset_id':'set-1','configured_status':'ACTIVE'})]:
                with self.subTest(method=method):
                    original = getattr(client,method).return_value
                    getattr(client,method).return_value = invalid
                    with self.assertRaises(MetaAdsApiError):
                        MetaPostingClient.verify_posting_resume(client, record)
                    getattr(client,method).return_value = original
            read.return_value = {}
            with self.assertRaises(MetaAdsApiError):
                MetaPostingClient.verify_posting_resume(client, record)

    def test_restart_with_original_inputs_resumes_same_submission(self):
        store, client = Ledger(), FakePostingClient(fail_at='ad_2')
        factory = lambda **kw: self.service(client, kw['store'])
        first = PostingJobs(lambda: store, factory)
        identity = first.submit(request_for())
        first.jobs[identity]['future'].result(timeout=10)
        first.pool.shutdown()
        campaign, adset = store.record['campaign_id'], store.record['adset_id']
        client.fail_at = ''
        second = PostingJobs(lambda: store, factory)
        self.addCleanup(second.pool.shutdown)
        self.assertEqual(second.resume(request_for()), identity)
        second.jobs[identity]['future'].result(timeout=10)
        result = second.snapshot(identity)
        self.assertEqual((result['status'],result['campaign_id'],result['adset_id']), ('COMPLETE',campaign,adset))
        self.assertEqual(len(client.copy_ads), 3)


class AdsSchemaTests(unittest.TestCase):
    def setUp(self):
        ads_schema.reset()
        self.addCleanup(ads_schema.reset)
        self.cursor = Mock()
        self.cursor.fetchall.return_value = [dict(table_name=t,column_name='id') for t in ads_schema.TABLES] + [dict(table_name='meta_posting_submissions',column_name=c) for c in ads_schema.POSTING_COLUMNS]
        cursor_context = Mock(__enter__=Mock(return_value=self.cursor), __exit__=Mock(return_value=False))
        conn = Mock(cursor=Mock(return_value=cursor_context))
        connection_context = Mock(__enter__=Mock(return_value=conn), __exit__=Mock(return_value=False))
        self.backend = SimpleNamespace(connect=Mock(return_value=connection_context),get_database_url=Mock(return_value='test-target'))

    def test_concurrent_progress_checks_use_one_read_and_no_ddl(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _: ads_schema.ensure(self.backend), range(30)))
        self.assertEqual(self.backend.connect.call_count, 1)
        self.assertTrue(self.cursor.execute.call_args.args[0].startswith('SELECT'))

    def test_missing_schema_fails_closed_without_caching_or_migration(self):
        self.cursor.fetchall.return_value = []
        for _ in range(2):
            with self.assertRaisesRegex(RuntimeError, 'schema is incomplete'):
                ads_schema.ensure(self.backend)
        self.assertEqual(self.backend.connect.call_count, 2)
        self.assertTrue(all(c.args[0].startswith('SELECT') for c in self.cursor.execute.call_args_list))

    def test_changed_target_and_expired_cache_revalidate(self):
        ads_schema.ensure(self.backend)
        self.backend.get_database_url.return_value = 'different-target'
        ads_schema.ensure(self.backend)
        with patch('ads_schema.monotonic', return_value=float('inf')):
            ads_schema.ensure(self.backend)
        self.assertEqual(self.backend.connect.call_count, 3)


if __name__ == '__main__':
    unittest.main()
