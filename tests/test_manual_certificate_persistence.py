import inspect
import ast
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

import manual_certificate_schema as schema
import orders_page
import order_allocator
import run_migrations
import supabase_backend as backend
from tests.test_manual_expired_edition_entry import eligible_state
from tests.test_manual_certificate_controls import ACTOR, ROW
from tests.test_orders_bounded_reader import ProductionCardinalityDatabase


class PersistenceTests(unittest.TestCase):
    def connection(self, record, *, fail_commit=False):
        conn = MagicMock()
        conn.__enter__.return_value = conn
        cur = conn.cursor.return_value.__enter__.return_value
        cur.fetchone.return_value = record
        cur.fetchall.return_value = [record] if record else []
        if fail_commit:
            conn.commit.side_effect = RuntimeError('Database commit failed')
        return conn, cur

    def save(self):
        return backend.save_manual_order_line_edition(source_channel='Shopify', external_order_id='1',
            external_line_item_id='10', expected_product_gid='3', edition_number=100,
            edition_total=100, reason='Exception', duplicate_confirmed=True, actor=ACTOR)

    def test_save_verified_on_independent_connection(self):
        record = dict(id='00000000-0000-0000-0000-000000000001', edition_number=100,
                      edition_total=100, reason='Exception', duplicate_confirmed=True)
        write, write_cur = self.connection(record)
        read, read_cur = self.connection(record)
        with patch.object(backend, 'connect', side_effect=[write, read]) as connect, \
             patch.object(backend, '_manual_edition_state_with_cursor', return_value=eligible_state()):
            result = self.save()
        self.assertTrue(result['saved'])
        write.commit.assert_called_once()
        self.assertEqual(connect.call_count, 2)
        self.assertIn('SELECT * FROM manual_order_line_editions', read_cur.execute.call_args.args[0])
        self.assertIn('regexp_replace(external_line_item_id', write_cur.execute.call_args.args[0])

    def test_failed_commit_never_reads_or_returns_success(self):
        conn, _ = self.connection({'id': 'saved'}, fail_commit=True)
        with patch.object(backend, 'connect', return_value=conn) as connect, \
             patch.object(backend, '_manual_edition_state_with_cursor', return_value=eligible_state()):
            with self.assertRaisesRegex(RuntimeError, 'commit failed'):
                self.save()
        self.assertEqual(connect.call_count, 1)

    def test_missing_post_commit_readback_is_not_success(self):
        write, _ = self.connection({'id': 'saved'})
        read, _ = self.connection(None)
        with patch.object(backend, 'connect', side_effect=[write, read]), \
             patch.object(backend, '_manual_edition_state_with_cursor', return_value=eligible_state()):
            with self.assertRaisesRegex(RuntimeError, 'could not be verified'):
                self.save()

    def test_numeric_and_gid_read_use_identical_parameters(self):
        queries = []
        for order, line in [('1', '10'), ('gid://shopify/Order/1', 'gid://shopify/LineItem/10')]:
            conn, cur = self.connection(None)
            with patch.object(backend, 'connect', return_value=conn):
                backend.get_manual_order_line_edition(source_channel='Shopify', external_order_id=order,
                    external_line_item_id=line, expected_product_gid='3')
            queries.append(cur.execute.call_args.args[1])
        self.assertEqual(queries[0], queries[1])

    def test_remove_verifies_new_connection(self):
        write, _ = self.connection({'id': ROW['edition_order_id'].split(':')[1]})
        read, cur = self.connection(None)
        with patch.object(backend, 'connect', side_effect=[write, read]):
            backend.remove_manual_order_line_edition(manual_id=ROW['edition_order_id'].split(':')[1], actor=ACTOR)
        self.assertIn('SELECT id FROM manual_order_line_editions', cur.execute.call_args.args[0])

    def test_failed_save_has_no_optimistic_ui_value(self):
        ui = MagicMock()
        ui.session_state = {}
        ui.number_input.return_value = 100
        ui.text_area.return_value = 'Exception'
        ui.checkbox.return_value = True
        ui.button.side_effect = lambda label, **kwargs: label == 'Save Manual Certificate'
        db = MagicMock()
        db.save_manual_order_line_edition.side_effect = RuntimeError('write failed')
        eligibility = backend._manual_edition_eligibility_from_state(eligible_state())
        with patch.object(orders_page, 'st', ui), patch.object(orders_page, '_reload_orders_from_source') as reload:
            inspect.unwrap(orders_page._manual_certificate_dialog)(ROW, eligibility, db, ACTOR)
        reload.assert_not_called()
        ui.rerun.assert_not_called()
        self.assertEqual(ui.session_state, {})
        self.assertIn('write failed', ui.error.call_args.args[0])

    def test_orders_reload_new_session_reads_persisted_manual_row(self):
        class DB(ProductionCardinalityDatabase):
            number = 100
            class Cursor(ProductionCardinalityDatabase.Cursor):
                def fetchone(self):
                    if 'information_schema.tables' in self.sql:
                        return {'exists': True}
                    return super().fetchone()
                def fetchall(self):
                    if 'WITH selected_edition_ids AS' in self.sql:
                        return []
                    if 'FROM manual_order_line_editions manual' in self.sql:
                        return [] if not self.database.number else [{
                            'manual_edition_id': ROW['edition_order_id'].split(':')[1],
                            'shopify_order_id': '1', 'shopify_line_item_id': '10',
                            'shopify_product_id': 'gid://shopify/Product/3', 'source_channel': 'shopify',
                            'edition_number': self.database.number, 'edition_total': 100}]
                    rows = super().fetchall()
                    if 'LEFT JOIN shopify_order_lines li' in self.sql:
                        for row in rows:
                            row.update(shopify_product_id='gid://shopify/Product/3', source_name='Shopify')
                    return rows
            class Connection(ProductionCardinalityDatabase.Connection):
                def cursor(self):
                    return DB.Cursor(self.database)
            def connect(self):
                conn = self.Connection(self)
                self.connections.append(conn)
                return conn
        database = DB(order_count=1, lines_per_order=1)
        for number in (100, 99, None):
            database.number = number
            with patch.object(backend, 'connect', side_effect=database.connect), \
                 patch.object(order_allocator, '_configured_supabase_backend', return_value=backend), \
                 patch.object(orders_page, '_configured_supabase_backend', return_value=backend), \
                 patch.object(orders_page.st, 'session_state', {}):
                payload = orders_page._read_orders_snapshot()
                row = orders_page._normalise_row(payload['rows'][0])
            if number:
                self.assertEqual(f'#{number:03d}/100 · Manual', row['edition'])
            else:
                self.assertNotIn('Manual', row['edition'])
        self.assertGreaterEqual(len(database.connections), 3)


class DeploymentTests(unittest.TestCase):
    def test_failed_migration_prevents_application_listener(self):
        tree = ast.parse(Path('sports_cave_server.py').read_text(encoding='utf-8'))
        main = tree.body[-1]
        self.assertIsInstance(main, ast.If)
        namespace = {'os': MagicMock(), 'run_migrations': MagicMock(),
                     'prepare_google_seo_storage': MagicMock(), 'collector_vault': MagicMock(), 'app': object()}
        namespace['run_migrations'].run_deployment_migrations.side_effect = RuntimeError('migration failed')
        uvicorn = MagicMock()
        with patch.dict('sys.modules', {'uvicorn': uvicorn}):
            with self.assertRaisesRegex(RuntimeError, 'migration failed'):
                exec(compile(ast.Module(body=main.body, type_ignores=[]), '<startup>', 'exec'), namespace)
        uvicorn.run.assert_not_called()
        namespace['prepare_google_seo_storage'].assert_not_called()

    def test_actual_schema_inspection_reports_missing_objects_not_filename(self):
        cur = MagicMock()
        cur.fetchall.return_value = []
        cur.fetchone.return_value = None
        issues = schema.schema_issues(cur)
        self.assertIn('missing column: manual_order_line_editions.duplicate_confirmed', issues)
        self.assertTrue(any('manual_certificate_audit' in issue for issue in issues))
        self.assertTrue(any('trigger' in issue for issue in issues))
        self.assertNotIn('schema_migrations', '\n'.join(c.args[0] for c in cur.execute.call_args_list))

    def test_deployment_rejects_unreviewed_content_before_connecting(self):
        with patch.object(run_migrations, 'REVIEWED_MIGRATION_SHA256', {}), \
             patch.object(run_migrations.psycopg, 'connect') as connect:
            with self.assertRaisesRegex(RuntimeError, 'SHA-reviewed'):
                run_migrations.run_deployment_migrations()
        connect.assert_not_called()

    def test_deployment_failure_propagates_and_does_not_commit(self):
        conn = MagicMock()
        conn.__enter__.return_value = conn
        cur = conn.cursor.return_value.__enter__.return_value
        cur.fetchone.return_value = None
        def execute(sql, *args):
            if 'ALTER TABLE manual_order_line_editions' in sql:
                raise RuntimeError('migration failed')
        cur.execute.side_effect = execute
        with patch.object(run_migrations, 'get_database_url', return_value=('fixture', 'DATABASE_URL')), \
             patch.object(run_migrations.psycopg, 'connect', return_value=conn), \
             patch.object(schema, 'schema_issues', return_value=['missing']), \
             patch.object(run_migrations, '_existing_controls_match', return_value=False):
            with self.assertRaisesRegex(RuntimeError, 'migration failed'):
                run_migrations.run_deployment_migrations()
        conn.commit.assert_not_called()

    def test_transaction_wrappers_do_not_commit_before_tracking(self):
        for name in run_migrations.DEPLOYMENT_MIGRATIONS:
            text = (run_migrations.MIGRATIONS_DIR / name).read_text(encoding='utf-8')
            body = run_migrations._migration_body(text)
            self.assertNotRegex(body, r'(?im)^\s*(BEGIN|COMMIT);')
            self.assertTrue(run_migrations.reviewed_migration_sql(run_migrations.MIGRATIONS_DIR / name, text))
        self.assertFalse(any('allocator' in n or 'cursor' in n for n in run_migrations.DEPLOYMENT_MIGRATIONS))


if __name__ == '__main__':
    unittest.main()
