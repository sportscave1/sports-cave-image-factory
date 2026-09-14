"""Complete recovery uses production planner/run logic with a transactional SQL double."""
from contextlib import ExitStack
from copy import deepcopy
import inspect
import unittest
from unittest.mock import patch
import edition_ops
import shopify_sync
import supabase_backend as backend
from tests.test_product_activation_sync import collector
from tests.test_product_webhook_restoration import MemoryDatabase


class CompleteRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.db = MemoryDatabase()
        self.stack.enter_context(patch.object(backend, 'connect', self.db.connect))
        for name in ('start_sync_run', 'finish_sync_run', '_write_product_incremental_sync_state', 'set_app_setting', '_webhook_log'):
            self.stack.enter_context(patch.object(backend, name))
        self.product = collector(shopify_product_id='gid://shopify/Product/10452302823731',
            handle='last-to-first-larry-perkins-russell-ingall-wall-art',
            created_at='2026-09-12T03:54:10Z', updated_at='2026-09-14T00:03:48Z')
        self.fetch = self.stack.enter_context(patch.object(shopify_sync, 'fetch_edition_ops_active_products',
            return_value={'products': [self.product], 'page_count': 1}))
        self.stack.enter_context(patch.object(shopify_sync, 'fetch_product_by_shopify_id', return_value=self.product))
        self.incremental = self.stack.enter_context(patch.object(shopify_sync, 'fetch_newest_products_for_edition_ops',
            side_effect=AssertionError('created_at watermark must not limit manual recovery')))
        self.mirror = self.stack.enter_context(patch.object(shopify_sync, 'sync_complete_product_edition_metafields'))

    def pull(self):
        return backend.reconcile_all_shopify_products_to_edition_ops(config={'configured': True})

    def test_old_draft_before_watermark_recovers_once(self):
        watermark = '2026-09-12T04:04:36Z'
        self.assertLess(self.product['created_at'], watermark)
        first = self.pull()
        before = deepcopy((self.db.rows, self.db.runs))
        second = self.pull()
        self.assertEqual((first['new_products_inserted'], second['new_products_inserted']), (1, 0))
        self.assertEqual(len(self.db.rows), 1)
        self.assertEqual(len(self.db.runs), 1)
        self.assertEqual(before, (self.db.rows, self.db.runs))
        self.assertEqual([self.db.rows[0][k] for k in ('next_edition_number','sold_count','remaining_count')], [1,0,100])
        self.mirror.assert_called_once()
        self.assertTrue(self.mirror.call_args.kwargs['verify'])
        self.assertIsNone(self.fetch.call_args.kwargs['max_products'])

    def test_sold_and_archived_records_completely_unchanged(self):
        self.pull()
        self.db.history = [{"edition_number": 52}]
        for archived in (False, True):
            self.db.rows[0].update(next_edition_number=53, sold_count=52, remaining_count=48,
                active=not archived, is_active=not archived, edition_status='archived' if archived else 'limited_release')
            before = deepcopy((self.db.rows, self.db.runs))
            self.pull()
            self.assertEqual(before, (self.db.rows, self.db.runs))
        self.assertEqual(self.mirror.call_count, 1)

    def test_orphan_history_refuses_initialisation(self):
        self.db.history = [{'edition_number': 52}]
        with self.assertRaisesRegex(RuntimeError, 'history'):
            self.pull()
        self.assertEqual(self.db.rows, [])
        self.assertEqual(self.db.runs, [])
        self.mirror.assert_not_called()

    def test_mirror_failure_keeps_ledger_then_resumes(self):
        self.mirror.side_effect = RuntimeError('fixture read-back timeout')
        first = self.pull()
        self.assertEqual(first['new_products_inserted'], 1)
        self.assertEqual(first['shopify_metafields_failed_pending'], 1)
        self.assertIn(self.product['handle'], first['errors'][0])
        self.assertEqual(self.db.rows[0]['metafields_sync_status'], 'Pending automatic mirror')
        self.mirror.side_effect = None
        second = self.pull()
        self.assertEqual(second['new_products_inserted'], 0)
        self.assertEqual(second['shopify_metafields_pushed'], 1)
        self.assertEqual(len(self.db.runs), 1)
        self.assertEqual(self.db.rows[0]['next_edition_number'], 1)

    def test_manual_button_complete_path_and_unsaved_guard(self):
        source = inspect.getsource(edition_ops._render_pull_new_products_button)
        self.assertIn('backend.reconcile_all_shopify_products_to_edition_ops', source)
        self.assertNotIn('sync_new_shopify_products_to_edition_ops', source)
        self.assertIn('_changed_rows', source)
        self.assertIn('_reload_products_from_supabase', source)

    def test_unresolved_candidate_is_not_no_new_products(self):
        self.product['online_store_url'] = ''
        result = self.pull()
        self.assertTrue(result['errors'])
        summary = edition_ops._format_new_product_pull_summary(result)
        self.assertIn('1 issue(s) requiring review', summary)
        self.assertNotIn('No new products found', summary)

    def test_initial_mirror_requires_fresh_matching_readback(self):
        # Exercise the actual helper rather than the registration-boundary mock.
        self.stack.close()
        product = {**collector(), 'edition_total': 100, 'next_edition_number': 1,
                   'sold_count': 0, 'remaining_count': 100, 'edition_enabled': True}
        inputs = shopify_sync.complete_product_edition_metafield_inputs(product)
        with patch.object(shopify_sync, 'metafields_set', return_value={'metafields': inputs}), patch.object(
            shopify_sync, 'fetch_metafields', return_value={'metafields': inputs}) as read:
            shopify_sync.sync_complete_product_edition_metafields(product, verify=True)
            self.assertTrue(read.called)
        with patch.object(shopify_sync, 'metafields_set', return_value={'metafields': inputs}), patch.object(
            shopify_sync, 'fetch_metafields', return_value={'metafields': []}):
            with self.assertRaisesRegex(shopify_sync.ShopifyAPIError, 'read-back mismatch'):
                shopify_sync.sync_complete_product_edition_metafields(product, verify=True)

class RecoveryDiagnosticsTests(unittest.TestCase):
    def test_receipt_inspection_is_read_only_and_skips_schema_work(self):
        import io
        from unittest.mock import MagicMock
        from scripts import register_shopify_product_webhooks as script
        connection = MagicMock()
        cursor = connection.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = None
        with ExitStack() as stack:
            stack.enter_context(patch.dict('os.environ', {'SPORTS_CAVE_WEBHOOK_BASE_URL': 'https://example.test'}))
            stack.enter_context(patch.object(script.shopify_sync, 'get_config', return_value={}))
            stack.enter_context(patch.object(script.shopify_sync, 'validate_config'))
            for topic in ('create','update'):
                stack.enter_context(patch.object(script.shopify_sync, f'list_products_{topic}_webhook_subscriptions', return_value={'subscriptions': []}))
                stack.enter_context(patch.object(script.shopify_sync, f'ensure_products_{topic}_webhook_subscription', side_effect=AssertionError('No subscription writes')))
            health = stack.enter_context(patch.object(backend, 'get_product_sync_diagnostics', return_value={'supabase_connected': True}))
            stack.enter_context(patch.object(backend, 'connect', return_value=connection))
            stack.enter_context(patch('sys.stdout', new_callable=io.StringIO))
            self.assertEqual(script.main(['--receipts']), 0)
        health.assert_called_once_with(ensure_schema_first=False)
        self.assertEqual(cursor.execute.call_count, 2)
        for call in cursor.execute.call_args_list:
            self.assertTrue(call.args[0].lstrip().startswith('SELECT'))

    def test_live_only_requires_supported_edition_readiness(self):
        import product_upload_modes as modes
        self.assertIn('EDITION OPS READINESS UNVERIFIED', modes.LIVE_FINAL)
        self.assertIn('existing reconciliation service', modes.LIVE_FINAL)
        self.assertNotIn('EDITION OPS OPERATIONAL READINESS', modes.DRAFT_FINAL)

if __name__ == '__main__':
    unittest.main()
