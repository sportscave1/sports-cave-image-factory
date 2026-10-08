"""Real PostgreSQL pipeline/rollback checks in a disposable loopback schema."""
import os
import unittest
from unittest.mock import patch
import uuid

import os_accounts


@unittest.skipUnless(os.getenv('LOCAL_ACCOUNT_TEST_DSN'), 'Requires isolated loopback PostgreSQL')
class AccountSchemaPipelineTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        from psycopg import sql
        from psycopg.conninfo import conninfo_to_dict
        from psycopg.rows import dict_row
        dsn = os.environ['LOCAL_ACCOUNT_TEST_DSN']
        self.assertIn(conninfo_to_dict(dsn).get('host'), ('127.0.0.1', 'localhost'))
        self.schema = 'phase2_accounts_' + uuid.uuid4().hex
        self.admin = psycopg.connect(dsn, autocommit=True)
        self.addCleanup(self.admin.close)
        self.admin.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(self.schema)))
        self.addCleanup(lambda: self.admin.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema))))
        self.connect = lambda: psycopg.connect(dsn, row_factory=dict_row,
            options=f'-c search_path={self.schema},public', prepare_threshold=None)
        self.store = os_accounts.PostgresAccountStore()
        patcher = patch.object(self.store, '_connect', side_effect=self.connect)
        patcher.start(); self.addCleanup(patcher.stop)
        configured = patch.object(self.store, 'is_configured', return_value=True)
        configured.start(); self.addCleanup(configured.stop)

    def test_initialise_repeat_and_authoritative_reads(self):
        self.store.ensure_schema()
        self.assertTrue(self.store._schema_ready)
        with self.connect() as conn:
            identity = conn.execute("INSERT INTO os_users(username,display_name,password_hash,role) VALUES ('fixture','Fixture','hash','worker') RETURNING id").fetchone()['id']
            conn.execute("INSERT INTO os_user_page_permissions(user_id,page_key) VALUES (%s,'orders')", (identity,))
        self.store._schema_ready = False  # next process initialisation
        self.store.ensure_schema()
        self.assertEqual(self.store.get_user(identity)['page_permissions'], ['orders'])
        with self.connect() as conn:
            conn.execute("UPDATE os_user_page_permissions SET can_access=false")
            conn.execute("UPDATE os_users SET session_version=2")
        user = self.store.get_user(identity)
        self.assertEqual((user['session_version'], user['page_permissions']), (2, []))

    def test_failed_pipeline_rolls_back_all_changes_and_can_retry(self):
        # A deliberately incompatible existing table fails midway through setup.
        # Earlier queued permission-table creation must be rolled back too.
        with self.connect() as conn:
            conn.execute('CREATE TABLE os_users(id uuid PRIMARY KEY)')
        with self.assertRaises(os_accounts.AccountStorageError): self.store.ensure_schema()
        self.assertFalse(self.store._schema_ready)
        with self.connect() as conn:
            self.assertIsNone(conn.execute("SELECT to_regclass(%s) AS table_name", (self.schema+'.os_user_page_permissions',)).fetchone()['table_name'])
            conn.execute('DROP TABLE os_users')
        self.store.ensure_schema()
        self.assertTrue(self.store._schema_ready)

    def test_automation_identity_read_preserves_timeouts_and_results(self):
        from types import SimpleNamespace
        from crm_automation_home_read import BoundedStore
        store = BoundedStore(SimpleNamespace(db=self.connect))
        record = store.q("SELECT %s::int AS value, current_setting('statement_timeout') AS statement_timeout, current_setting('lock_timeout') AS lock_timeout", (42,), one=True)
        self.assertEqual(record, {'value':42, 'statement_timeout':'1500ms', 'lock_timeout':'500ms'})
        with self.connect() as conn:
            self.assertEqual(conn.execute("SELECT current_setting('statement_timeout') AS timeout").fetchone()['timeout'], '0')


if __name__ == '__main__': unittest.main()
