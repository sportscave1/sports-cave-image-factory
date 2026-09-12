"""Local-only product lifecycle tests; no Shopify or Supabase credentials used."""

import base64
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import hmac
import json
import threading
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

import edition_ops
import supabase_backend as backend
import webhook_server
from scripts import register_shopify_product_webhooks as registration
from tests.test_edition_ops_stability import _FakeStreamlit, _product, _snapshot


class MemoryDatabase:
    """Stateful SQL boundary double; exercises real planner and write helpers.

    Models transaction rollback/serialization, not a PostgreSQL integration test.
    Unexpected SQL fails the test rather than silently permitting a write.
    """

    def __init__(self):
        self.rows = []
        self.history = []
        self.runs = []
        self.display = {}
        self.lock = threading.Lock()
        self.statements = []
        self.commits = 0

    def connect(self):
        db = self

        class Connection:
            held = False
            def __enter__(self):
                return self

            def __exit__(self, kind, error, tb):
                if self.held:
                    db.rows, db.runs, db.display = self.before
                    db.lock.release()
                    self.held = False

            def cursor(self):
                return Cursor(self)

            def commit(self):
                db.commits += 1
                if self.held:
                    db.lock.release()
                    self.held = False

        class Cursor:
            rowcount = 1
            result = None
            def __init__(self, conn):
                self.conn = conn

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def fetchone(self):
                return self.result

            def fetchall(self):
                return deepcopy(db.rows)

            def execute(self, sql, params=None):
                compact = ' '.join(sql.split())
                db.statements.append(compact)
                if compact.startswith('LOCK TABLE edition_products'):
                    db.lock.acquire()
                    self.conn.held = True
                    self.conn.before = deepcopy((db.rows, db.runs, db.display))
                elif compact.startswith('SELECT * FROM edition_products') and 'FOR UPDATE' in compact:
                    db.lock.acquire()
                    self.conn.held = True
                    self.conn.before = deepcopy((db.rows, db.runs, db.display))
                    self.result = deepcopy(next((r for r in db.rows if r['shopify_product_gid'] == params[0]
                                                 and r.get('metafields_sync_status') == 'Pending automatic mirror'), None))
                elif compact.startswith('SELECT ep.* FROM edition_products'):
                    assert self.conn.held, 'Identity must be read after serialization'
                elif compact.startswith('SELECT EXISTS'):
                    self.result = {'has_history': bool(db.history)}
                elif compact.startswith('INSERT INTO shopify_products'):
                    db.display[params[0]] = params
                elif compact.startswith('INSERT INTO edition_products'):
                    assert '100, 1, 0, 0, 100' in compact
                    row = dict(zip(('shopify_product_id', 'shopify_product_gid', 'shopify_handle', 'product_title'), params[:4]))
                    row.update(id=len(db.rows)+1, edition_total=100, next_edition_number=1,
                               last_assigned_edition=0, sold_count=0, remaining_count=100,
                               active=True, is_active=True, sold_out=False, is_sold_out=False,
                               metafields_sync_status='Pending automatic mirror', edition_status='limited_release',
                               featured_image_url=params[5], edition_name=params[4])
                    db.rows.append(row)
                    self.result = {'shopify_handle': row['shopify_handle']}
                elif compact.startswith('UPDATE edition_products SET'):
                    assignments = compact.split(' SET ', 1)[1].split(' WHERE ', 1)[0].split(', ')
                    row = next(r for r in db.rows if r['id'] == params[-1])
                    if "metafields_sync_status='Synced'" in compact:
                        row['metafields_sync_status'] = 'Synced'
                    index = 0
                    for assignment in assignments:
                        if '%s' in assignment:
                            row[assignment.split('=')[0]] = params[index]
                            index += 1
                elif compact.startswith('UPDATE edition_runs SET'):
                    # Existing helper may update identity/display fields only.
                    assert 'next_edition_number' not in compact
                    assert 'edition_total' not in compact
                elif compact.startswith('WITH new_runs AS'):
                    assert 'next_edition_number=' not in compact
                    for row in db.rows:
                        if row['shopify_handle'] in params[0] and not row.get('active_edition_run_id'):
                            run = {'id': f"run-{row['id']}", 'edition_product_id': row['id'], 'next_edition_number': row['next_edition_number']}
                            db.runs.append(run)
                            row['active_edition_run_id'] = run['id']
                elif compact.startswith(('SAVEPOINT ', 'RELEASE SAVEPOINT ')):
                    pass
                else:
                    raise AssertionError(f'Unexpected SQL: {compact}')

        return Connection()


class ProductLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.db = MemoryDatabase()
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(backend, 'connect', self.db.connect))
        self.stack.enter_context(patch.object(backend, '_set_webhook_app_setting'))
        self.stack.enter_context(patch.object(backend, '_update_webhook_event_status'))
        self.stack.enter_context(patch.object(backend, '_webhook_log'))
        self.global_runs = self.stack.enter_context(patch.object(backend, '_ensure_active_edition_runs_for_products', side_effect=AssertionError('Global counter rewrite forbidden')))
        self.payload = {'id': 987, 'handle': 'new-art', 'title': 'New Art', 'status': 'active'}
        self.fetch_context = threading.local()
        self.canonical = self.stack.enter_context(patch.object(backend.shopify_sync, 'fetch_product_by_shopify_id', side_effect=lambda *a, **k: self.full_product(getattr(self.fetch_context, 'payload', self.payload))))
        self.stack.enter_context(patch.object(backend, '_mirror_pending_registered_product', return_value=False))

    def full_product(self, payload):
        return {**backend._normalize_shopify_product_create_payload(payload),
                'vendor': 'Sports Cave', 'product_type': 'Framed Art',
                'tags': ['Collector Series'], 'online_store_url': 'https://example.com/art',
                '_edition_registration_canonical': True}

    def deliver(self, **changes):
        payload = {**self.payload, **changes}
        self.fetch_context.payload = payload
        return backend.process_product_create_webhook(payload, 'test-event', 'products/update', claim_event=False)

    def test_new_active_product_visible_in_normal_loader_at_one(self):
        result = self.deliver()
        self.assertEqual(result['new_products_inserted'], 1)
        row = self.db.rows[0]
        self.assertEqual((row['next_edition_number'], row['edition_total'], row['sold_count'], row['remaining_count']), (1, 100, 0, 100))
        self.assertEqual(self.db.runs[0]['next_edition_number'], 1)
        cursor = Mock()
        cursor.fetchall.return_value = deepcopy(self.db.rows)
        with patch.object(backend, '_run_read_operation', side_effect=lambda op, read: (read(cursor), {})):
            loaded = backend.list_edition_products_read_only()
        ui_row = edition_ops._row_from_supabase_product(loaded[0])
        self.assertEqual(ui_row['edition_next_number'], 1)
        self.assertEqual(ui_row['edition_remaining'], 100)
        self.assertTrue(ui_row['edition_enabled'])

    def test_existing_53_and_manual_overrides_survive_update_and_stale_run(self):
        self.deliver()
        self.db.rows[0].update(next_edition_number=53, sold_count=52, remaining_count=48,
                               last_assigned_edition=52, allow_counter_history_override=True,
                               active=False, is_active=False)
        protected = deepcopy(self.db.rows[0])
        self.deliver(title='Renamed art', handle='renamed-art')
        for key in ('next_edition_number', 'sold_count', 'remaining_count', 'last_assigned_edition', 'allow_counter_history_override', 'active', 'is_active'):
            self.assertEqual(self.db.rows[0][key], protected[key], key)
        self.assertEqual(self.db.rows[0]['shopify_handle'], 'renamed-art')
        self.global_runs.assert_not_called()

    def test_duplicate_and_concurrent_deliveries_have_one_row_and_run(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.deliver(), range(8)))
        self.assertEqual(sum(r['new_products_inserted'] for r in results), 1)
        self.assertEqual(len(self.db.rows), 1)
        self.assertEqual(len(self.db.runs), 1)
        self.assertEqual(self.db.rows[0]['next_edition_number'], 1)
        self.assertEqual(len(self.db.display), 1)

    def test_new_product_does_not_touch_unrelated_existing_counter(self):
        self.deliver()
        self.db.rows[0].update(next_edition_number=53, sold_count=52, remaining_count=48)
        before = deepcopy(self.db.rows[0])
        self.deliver(id=988, handle='second-art')
        self.assertEqual(self.db.rows[0], before)
        self.assertEqual(self.db.rows[1]['next_edition_number'], 1)

    def test_draft_create_skips_then_active_update_initializes(self):
        result = self.deliver(status='draft')
        self.assertEqual(result['new_products_inserted'], 0)
        self.assertEqual(self.db.rows, [])
        self.deliver()
        self.assertEqual(self.db.rows[0]['next_edition_number'], 1)

    def test_existing_history_unchanged_and_orphan_history_fails_closed(self):
        self.deliver()
        self.db.rows[0]['next_edition_number'] = 53
        self.db.history = [{'edition_number': 52, 'certificate_id': 'cert-52'}]
        before = deepcopy(self.db.history)
        self.deliver(title='Updated art')
        self.assertEqual(self.db.rows[0]['next_edition_number'], 53)
        self.assertEqual(self.db.history, before)
        self.db.rows.clear()
        with self.assertRaisesRegex(RuntimeError, 'history'):
            self.deliver()
        self.assertEqual(self.db.rows, [])
        self.assertEqual(self.db.history, before)

    def test_manual_sync_uses_same_helper_after_webhook_and_skips_drafts(self):
        self.deliver()
        self.db.rows[0]['next_edition_number'] = 53
        product = backend._normalize_shopify_product_create_payload(self.payload)
        with patch.object(backend, '_start_new_product_discovery', return_value=(deepcopy(self.db.rows), {})), patch.object(
            backend.shopify_sync, 'fetch_newest_products_for_edition_ops', return_value={'products': [product], 'has_next_page': False}
        ), patch.object(backend, '_finish_new_product_discovery_state'):
            result = backend.sync_new_shopify_products_to_edition_ops(config={'configured': True})
        self.assertEqual(result['new_products_inserted'], 0)
        self.assertEqual(len(self.db.rows), 1)
        self.assertEqual(self.db.rows[0]['next_edition_number'], 53)
        draft = {**product, 'shopify_product_id': 'gid://shopify/Product/999', 'status': 'DRAFT'}
        backend.upsert_shopify_products_to_edition_products([draft])
        self.assertEqual(len(self.db.rows), 1)

    def test_failed_apply_rolls_back_before_receipt_can_complete(self):
        with patch.object(backend, '_apply_edition_product_incremental_plan', return_value={'errors': ['DB failure']}):
            with self.assertRaisesRegex(RuntimeError, 'DB failure'):
                self.deliver()
        self.assertEqual(self.db.commits, 0)

    def test_full_manual_reconciliation_does_not_run_schema_backfills(self):
        product = backend._normalize_shopify_product_create_payload(self.payload)
        self.deliver()
        self.db.rows[0]['next_edition_number'] = 53
        with ExitStack() as stack:
            schema = stack.enter_context(patch.object(backend, 'ensure_schema', side_effect=AssertionError('No schema backfills')))
            start = stack.enter_context(patch.object(backend, 'start_sync_run', return_value='local-run'))
            stack.enter_context(patch.object(backend, 'finish_sync_run'))
            stack.enter_context(patch.object(backend, 'set_app_setting'))
            stack.enter_context(patch.object(backend, '_write_product_incremental_sync_state'))
            stack.enter_context(patch.object(backend.shopify_sync, 'fetch_edition_ops_active_products', return_value={'products': [product], 'pages': 1}))
            # The outer metadata transaction has no edition writes/lock.
            real_connect = self.db.connect
            metadata_conn = Mock()
            metadata_conn.__enter__ = Mock(return_value=metadata_conn)
            metadata_conn.__exit__ = Mock(return_value=False)
            metadata_conn.cursor.return_value.__enter__ = Mock(return_value=Mock())
            metadata_conn.cursor.return_value.__exit__ = Mock(return_value=False)
            calls = 0
            def connect():
                nonlocal calls
                calls += 1
                return real_connect() if calls == 2 else metadata_conn
            stack.enter_context(patch.object(backend, 'connect', side_effect=connect))
            result = backend.reconcile_all_shopify_products_to_edition_ops(config={'configured': True})
        schema.assert_not_called()
        start.assert_called_once_with('shopify_products_incremental_sync', ensure_schema_first=False)
        self.assertEqual(result['new_products_inserted'], 0)
        self.assertEqual(self.db.rows[0]['next_edition_number'], 53)

    def test_product_routes_verify_real_hmac_before_database_writes(self):
        self.stack.enter_context(patch.object(backend, 'is_configured', return_value=True))
        claim = self.stack.enter_context(patch.object(backend, 'claim_product_create_webhook_receipt', return_value={'webhook_id': 'test-event'}))
        self.stack.enter_context(patch.dict('os.environ', {'SHOPIFY_WEBHOOK_SECRET': 'local-secret', 'SHOPIFY_ORDER_RECONCILIATION_ENABLED': 'false'}))
        body = json.dumps(self.payload).encode()
        signature = base64.b64encode(hmac.new(b'local-secret', body, hashlib.sha256).digest()).decode()
        client = TestClient(webhook_server.app)
        for path in ('products-create', 'products-update'):
            invalid = client.post(f'/webhooks/shopify/{path}', content=body, headers={'X-Shopify-Hmac-Sha256': 'invalid'})
            self.assertEqual(invalid.status_code, 401)
        claim.assert_not_called()
        self.assertEqual(self.db.rows, [])
        valid = client.post('/webhooks/shopify/products-update', content=body, headers={'X-Shopify-Hmac-Sha256': signature})
        self.assertEqual(valid.status_code, 200)
        self.assertEqual(self.db.rows[0]['next_edition_number'], 1)


class DisplayAndRegistrationTests(unittest.TestCase):
    def test_product_processing_does_not_block_health_endpoint(self):
        entered, release = threading.Event(), threading.Event()
        def process(*args, **kwargs):
            entered.set()
            if not release.wait(5):
                raise RuntimeError('Test did not release processing')
            return {}
        with ExitStack() as stack:
            stack.enter_context(patch.object(webhook_server, 'verify_shopify_webhook_hmac', return_value={'ok': True}))
            stack.enter_context(patch.object(backend, 'is_configured', return_value=True))
            stack.enter_context(patch.object(backend, 'claim_product_create_webhook_receipt', return_value={'webhook_id': 'local'}))
            stack.enter_context(patch.object(backend, 'process_product_create_webhook', side_effect=process))
            stack.enter_context(patch.dict('os.environ', {'SHOPIFY_ORDER_RECONCILIATION_ENABLED': 'false'}))
            with TestClient(webhook_server.app) as client, ThreadPoolExecutor(max_workers=2) as pool:
                future = pool.submit(client.post, '/webhooks/shopify/products-update', json={'id': 1, 'handle': 'art'})
                try:
                    self.assertTrue(entered.wait(2))
                    health = pool.submit(client.get, '/healthz')
                    self.assertEqual(health.result(timeout=1).status_code, 200)
                finally:
                    release.set()
                self.assertEqual(future.result(timeout=2).status_code, 200)

    def test_expired_session_refreshes_and_dirty_edits_are_preserved(self):
        old = _product(1)
        st = _FakeStreamlit({edition_ops.ROWS_KEY: [old], edition_ops.ORIGINAL_ROWS_KEY: [old],
                             edition_ops.EDITOR_ROWS_KEY: [old], edition_ops.SNAPSHOT_LOADED_KEY: True,
                             'edition_ops_snapshot_checked_at': 0})
        with patch.object(edition_ops, 'st', st), patch.object(edition_ops, '_load_snapshot', return_value=_snapshot([old, _product(2)])) as load:
            edition_ops._hydrate_from_snapshot_once()
            self.assertEqual(len(st.session_state[edition_ops.ROWS_KEY]), 2)
            load.assert_called_once()
            st.session_state['edition_ops_snapshot_checked_at'] = 0
            st.session_state[edition_ops.EDITOR_KEY] = {'edited_rows': {0: {'edition_next_number': 53}}}
            edition_ops._hydrate_from_snapshot_once()
            load.assert_called_once()
            self.assertEqual(st.session_state[edition_ops.EDITOR_KEY]['edited_rows'][0]['edition_next_number'], 53)

    def test_registration_inspects_both_topics_without_mutation_by_default(self):
        with ExitStack() as stack:
            stack.enter_context(patch.dict('os.environ', {'SPORTS_CAVE_WEBHOOK_BASE_URL': 'https://existing.example'}))
            stack.enter_context(patch.object(registration.shopify_sync, 'get_config', return_value={}))
            stack.enter_context(patch.object(registration.shopify_sync, 'validate_config'))
            ensures = []
            for suffix in ('create', 'update'):
                stack.enter_context(patch.object(registration.shopify_sync, f'products_{suffix}_webhook_callback_url', return_value=f'https://existing.example/webhooks/shopify/products-{suffix}'))
                stack.enter_context(patch.object(registration.shopify_sync, f'list_products_{suffix}_webhook_subscriptions', return_value={'subscriptions': []}))
                ensures.append(stack.enter_context(patch.object(registration.shopify_sync, f'ensure_products_{suffix}_webhook_subscription', return_value={})))
            registration.main([])
            for ensure in ensures:
                ensure.assert_not_called()
            registration.main(['--apply'])
            for ensure in ensures:
                ensure.assert_called_once()


if __name__ == '__main__':
    unittest.main()
