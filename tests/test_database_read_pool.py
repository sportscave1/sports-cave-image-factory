import threading
import time
import unittest
from contextlib import contextmanager
from unittest.mock import Mock, MagicMock, patch

import database_read_pool as reads
import os_accounts
import supabase_backend as db


class ReadPoolTests(unittest.TestCase):
    def test_pool_is_bounded_and_reuses_transport_configuration(self):
        with patch.dict(reads._pools, {}, clear=True), patch('psycopg_pool.ConnectionPool') as factory:
            first = reads.pool('postgresql://fixture')
            self.assertIs(first, reads.pool('postgresql://fixture'))
            factory.assert_called_once()
            options = factory.call_args.kwargs
            self.assertEqual((options['min_size'], options['max_size'], options['max_waiting']), (1, 3, 8))
            self.assertTrue(options['kwargs']['autocommit'])
            self.assertIn('statement_timeout=8000', options['kwargs']['options'])
            self.assertIsNone(options['kwargs']['prepare_threshold'])

    def test_simultaneous_readers_get_exclusive_leases_without_serialization(self):
        from psycopg_pool import ConnectionPool
        from psycopg.pq import TransactionStatus

        class Connection:
            closed = False
            info = Mock(transaction_status=TransactionStatus.IDLE)
            pgconn = Mock(transaction_status=TransactionStatus.IDLE)
            _expire_at = float('inf')
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def close(self): self.closed = True

        class Pool(ConnectionPool):
            def _connect(self, timeout=None):
                conn = Connection()
                conn._created_at = time.monotonic()
                conn._pool = self
                return conn

        barrier = threading.Barrier(2)
        borrowed = []
        with Pool('fixture', min_size=0, max_size=2, open=True) as current:
            with patch.object(reads, 'pool', return_value=current):
                def work():
                    with reads.connection('fixture') as conn:
                        borrowed.append(conn)
                        barrier.wait(timeout=2)
                from concurrent.futures import ThreadPoolExecutor
                with ThreadPoolExecutor(max_workers=2) as executor:
                    list(executor.map(lambda _: work(), range(2)))
        self.assertEqual(len(borrowed), 2)
        self.assertIsNot(borrowed[0], borrowed[1])

    def test_inflight_watchdog_finishes_and_timed_out_lease_is_discarded(self):
        entered, cancelled, released = threading.Event(), threading.Event(), threading.Event()
        conn = MagicMock(closed=False)
        conn.close.side_effect = lambda: setattr(conn, 'closed', True)
        def cancel(**kwargs):
            entered.set()
            time.sleep(.03)
            cancelled.set()
        conn.cancel_safe.side_effect = cancel
        @contextmanager
        def lease():
            try: yield conn
            finally:
                self.assertTrue(cancelled.is_set())
                self.assertTrue(conn.closed)
                released.set()
        def query(cur):
            self.assertTrue(entered.wait(1))
            return []
        with patch.object(db, 'read_connection', lease), patch.object(db, '_db_read_deadline_seconds', return_value=.01):
            with self.assertRaises(db.DatabaseReadError) as error:
                db._run_read_operation('orders.deadline-test', query)
        self.assertEqual(error.exception.diagnostic['category'], 'request_timeout')
        self.assertTrue(released.is_set())

    def test_pool_exhaustion_is_bounded_and_not_retried(self):
        from psycopg_pool import PoolTimeout
        with patch.object(db, 'read_connection', side_effect=PoolTimeout()) as lease:
            with self.assertRaises(db.DatabaseReadError) as error:
                db._run_read_operation('orders.pool-test', lambda cur: None)
        self.assertEqual(lease.call_count, 1)
        self.assertEqual(error.exception.diagnostic['category'], 'request_timeout')

    def test_account_reads_query_current_status_and_permissions_every_time(self):
        store = os_accounts.PostgresAccountStore()
        store._schema_ready = True
        conn = Mock()
        conn.cursor.return_value.__enter__ = Mock(return_value=Mock())
        conn.cursor.return_value.__exit__ = Mock(return_value=False)
        cur = conn.cursor.return_value.__enter__.return_value
        cur.fetchone.side_effect = [
            {'id': 'fixture', 'is_active': True, '_page_permissions': ['orders']},
            {'id': 'fixture', 'is_active': False, '_page_permissions': []}]
        @contextmanager
        def lease(*args, **kwargs): yield conn
        with patch.object(store, '_database_url', return_value='fixture'), patch.object(reads, 'connection', lease):
            self.assertTrue(store.get_user('fixture')['is_active'])
            self.assertFalse(store.get_user('fixture')['is_active'])
        self.assertEqual(cur.execute.call_count, 2)
        self.assertIn('os_user_page_permissions', cur.execute.call_args.args[0])

    def test_startup_warms_transports_without_reading_users_or_orders(self):
        with patch.object(reads, 'pool') as pool, patch.object(db, 'is_configured', return_value=True), \
                patch.object(db, '_database_url_with_ssl', return_value='orders-fixture'), \
                patch.object(os_accounts.DEFAULT_STORE, 'is_configured', return_value=True), \
                patch.object(os_accounts.DEFAULT_STORE, '_database_url', return_value='accounts-fixture'), \
                patch.object(os_accounts.DEFAULT_STORE, 'get_user') as get_user:
            reads.warm_application_reads()
        self.assertEqual(pool.call_count, 2)
        get_user.assert_not_called()
