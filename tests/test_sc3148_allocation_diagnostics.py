"""Regression coverage for incident diagnostics, not a substitute for SQL concurrency tests."""
import io
import json
import unittest
from contextlib import ExitStack, redirect_stdout
from unittest.mock import MagicMock, patch

import supabase_backend as backend
from scripts import audit_sc3148 as audit


class AllocationDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.conn = MagicMock()
        self.conn.__enter__.return_value = self.conn
        self.cur = self.conn.cursor.return_value.__enter__.return_value
        self.args = dict(
            order={"shopify_order_id": audit.ORDER_ID, "order_name": "#SC3148", "source_name": "web",
                   "customer_email": "private@example.invalid", "customer_name": "Private Customer"},
            line_item={"shopify_line_item_id": audit.LINE_ID, "shopify_variant_id": "gid://shopify/ProductVariant/54020683989299"},
            product={"shopify_product_gid": audit.PRODUCT_ID, "handle": audit.HANDLE}, quantity=2,
        )

    def execute(self, rows=None, error=None):
        self.cur.fetchall.return_value = rows or []
        self.cur.execute.side_effect = error
        self.output = io.StringIO()
        with patch.object(backend, "require_atomic_edition_allocation_capability"), \
             patch.object(backend, "connect", return_value=self.conn), redirect_stdout(self.output):
            return backend.allocate_edition_line_units_atomic(**self.args)

    def row(self, ordinal, created=True):
        return {"allocation": {"unit_ordinal": ordinal, "edition_number": 49 + ordinal,
                               "edition_run_id": "run-1"}, "was_created": created}

    def test_quantity_two_is_one_atomic_rpc_and_logs_distinct_units_after_commit(self):
        result = self.execute([self.row(1), self.row(2)])
        self.cur.execute.assert_called_once()
        self.assertEqual(self.cur.execute.call_args.args[1][4], 2)
        self.conn.commit.assert_called_once()
        self.conn.rollback.assert_not_called()
        self.assertEqual(result['created'], 2)
        events = [json.loads(line) for line in self.output.getvalue().splitlines()]
        self.assertEqual([e['edition_number'] for e in events[1:]], [50, 51])
        self.assertNotIn('private@example.invalid', self.output.getvalue())
        self.assertNotIn('Private Customer', self.output.getvalue())

    def test_existing_rpc_units_are_logged_as_idempotent_without_client_counter_writes(self):
        result = self.execute([self.row(1, False), self.row(2, False)])
        self.assertEqual(result['created'], 0)
        self.assertEqual(result['existing'], 2)
        self.assertEqual(self.output.getvalue().count('already_exists'), 2)
        self.assertNotIn('UPDATE', self.cur.execute.call_args.args[0])

    def test_partial_rpc_result_rolls_back_and_never_logs_committed(self):
        with self.assertRaisesRegex(RuntimeError, 'incomplete source line'):
            self.execute([self.row(1)])
        self.conn.rollback.assert_called_once()
        self.conn.commit.assert_not_called()
        self.assertNotIn('atomic_edition_unit_committed', self.output.getvalue())

    def test_duplicate_unit_ordinals_are_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'incomplete source line'):
            self.execute([self.row(1), self.row(1)])
        self.conn.commit.assert_not_called()

    def test_counter_contract_failure_is_actionable_and_redacts_database_details(self):
        with self.assertRaises(RuntimeError):
            self.execute(error=RuntimeError('Atomic edition suffix is not contiguous; private@example.invalid'))
        self.assertIn('counter_contract_mismatch', self.output.getvalue())
        self.assertNotIn('private@example.invalid', self.output.getvalue())
        self.conn.rollback.assert_called_once()
        self.conn.commit.assert_not_called()

    def test_invalid_quantity_cannot_be_silently_clamped_to_one(self):
        for quantity in (0, -1, 101, None):
            with self.subTest(quantity=quantity):
                self.args['quantity'] = quantity
                with self.assertRaises(ValueError):
                    self.execute()
        self.cur.execute.assert_not_called()

    def test_order_webhook_logs_failure_instead_of_completed(self):
        order = {**self.args['order'], 'line_items': [self.args['line_item']]}
        mocks = {
            '_load_single_paid_shopify_order': order,
            'edition_tracking_start_for_processing': None,
            'shopify_order_eligibility': {'eligible': True},
            'list_existing_shopify_order_ids': set(),
            'list_existing_shopify_line_item_ids': set(),
            'process_shopify_order_for_editions': {'errors': ['counter mismatch'], 'changed_handles': []},
        }
        with ExitStack() as stack:
            for name, value in mocks.items():
                stack.enter_context(patch.object(backend, name, return_value=value))
            log = stack.enter_context(patch.object(backend, '_webhook_log'))
            result = backend.process_single_paid_shopify_order_for_editions(order, config={'configured': True})
        self.assertEqual(result['errors'], ['counter mismatch'])
        for event in ('edition_allocation_completed', 'webhook_order_processing_finished'):
            calls = [c for c in log.call_args_list if c.args[0] == event]
            self.assertEqual(calls[-1].args[1], 'failed')


class ReadOnlyIncidentAuditTests(unittest.TestCase):
    def test_render_audit_rolls_back_and_never_runs_repair(self):
        import webhook_server
        conn = MagicMock()
        conn.__enter__.return_value = conn
        with patch.object(backend, 'connect', return_value=conn), \
             patch.object(audit, 'audit', return_value={'products': [], 'snapshot_sha256': 'audit-hash'}), \
             patch.object(webhook_server, '_webhook_log') as log:
            webhook_server._audit_sc3148_read_only()
        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()
        self.assertEqual(log.call_args.args[0], 'sc3148_read_only_audit_complete')

    def test_render_audit_exception_is_redacted(self):
        import webhook_server
        with patch.object(backend, 'connect', side_effect=RuntimeError('secret credentials')), \
             patch.object(webhook_server, '_webhook_log') as log:
            webhook_server._audit_sc3148_read_only()
        self.assertNotIn('secret credentials', str(log.call_args))
        self.assertEqual(log.call_args.args[0], 'sc3148_read_only_audit_failed')

    def test_database_enforces_read_only_before_every_select(self):
        conn = MagicMock()
        cur = conn.cursor.return_value.__enter__.return_value
        cur.fetchall.return_value = []
        result = audit.audit(conn)
        sql_calls = [call.args[0] for call in cur.execute.call_args_list]
        self.assertEqual(sql_calls[0], 'SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        self.assertTrue(all(sql.startswith(('SET ', 'SELECT ')) for sql in sql_calls))
        self.assertEqual(len(result['snapshot_sha256']), 64)
        conn.commit.assert_not_called()
        self.assertIn('other_failed_lines', result)

    def test_missing_configuration_fails_without_schema_or_connections(self):
        with patch.object(backend, 'is_configured', return_value=False), \
             patch.object(backend, 'connect') as connect, patch.object(backend, 'ensure_schema') as schema:
            with self.assertRaisesRegex(SystemExit, 'Database is not configured'):
                audit.main()
        connect.assert_not_called()
        schema.assert_not_called()


if __name__ == '__main__':
    unittest.main()
