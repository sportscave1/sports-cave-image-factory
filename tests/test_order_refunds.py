import copy
import inspect
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import order_refunds as refunds
import order_action_state as actions
import order_allocator
import orders_page
import supabase_backend


def node(financial='PAID', status=None, remaining=1):
    transactions = [{'kind': 'SALE', 'status': 'SUCCESS'}]
    if status:
        transactions.append({'kind': 'REFUND', 'status': status})
    return {'id': 'gid://shopify/Order/1', 'updatedAt': '2026-10-15T10:05:31Z',
            'displayFinancialStatus': financial, 'transactions': transactions,
            'transactionsCount': {'count': len(transactions)},
            'lineItems': {'nodes': [{'unfulfilledQuantity': remaining}],
                          'pageInfo': {'hasNextPage': False}}}


class RefundTests(unittest.TestCase):
    def row(self, value):
        return {'order_raw_json': {'_orders_refund': refunds.projection(value)}}

    def test_sc3303_paid_pending_and_no_items_is_on_hold(self):
        row = self.row(node(status='PENDING', remaining=0))
        self.assertEqual('Refund Pending', actions.final_fulfilment_status(row))
        self.assertTrue(refunds.blocked(row))
        self.assertFalse(actions.fulfilment_step_is_complete(row))
        self.assertFalse(actions.row_requires_action(row))

    def test_confirmed_full_refund_closes_and_overrides_dispatch(self):
        row = {**self.row(node('REFUNDED', 'SUCCESS', 0)), 'prodigi_status': 'Complete'}
        self.assertEqual('Refunded', actions.final_fulfilment_status(row))
        self.assertTrue(actions.fulfilment_step_is_complete(row))
        self.assertFalse(actions.row_requires_action(row))

    def test_partial_refund_with_remaining_items_stays_actionable(self):
        row = {**self.row(node('PARTIALLY_REFUNDED', 'SUCCESS', 1)),
               'financial_status': 'PARTIALLY_REFUNDED'}
        self.assertFalse(refunds.blocked(row))
        self.assertTrue(actions.row_requires_action(row))
        self.assertNotEqual('Refunded', actions.final_fulfilment_status(row))

    def test_full_financial_refund_with_remaining_items_does_not_close(self):
        self.assertFalse(refunds.projection(node('REFUNDED', 'SUCCESS', 1))['closed'])

    def test_pending_overrides_refunded_financial_status(self):
        self.assertEqual('Refund Pending', refunds.projection(node('REFUNDED', 'PENDING', 0))['status'])

    def test_failed_refund_and_zero_items_is_not_confirmation(self):
        self.assertFalse(refunds.projection(node('PAID', 'FAILURE', 0))['closed'])

    def test_truncated_evidence_never_closes(self):
        for key in ('lineItems', 'transactionsCount'):
            value = node('REFUNDED', 'SUCCESS', 0)
            value.pop(key)
            self.assertFalse(refunds.projection(value)['closed'])
        value = node('REFUNDED', 'SUCCESS', 0)
        value['lineItems']['pageInfo']['hasNextPage'] = True
        self.assertFalse(refunds.projection(value)['closed'])

    def test_projection_is_deterministic_and_does_not_mutate_input(self):
        value = node('REFUNDED', 'SUCCESS', 0)
        before = copy.deepcopy(value)
        self.assertEqual(refunds.projection(value), refunds.projection(value))
        self.assertEqual(before, value)

    def test_snapshot_retains_refund_and_edition_history(self):
        raw = {'shopify_order_id': 'gid://shopify/Order/1', 'order_name': '#SC1',
               **self.row(node('REFUNDED', 'SUCCESS', 0)),
               'assignments': [{'edition_number': 7, 'edition_order_id': 'original',
                                'allocation_index': 1, 'edition_total': 100}]}
        rows = order_allocator._snapshot_rows_from_supabase_order_rows([raw])
        self.assertEqual(7, rows[0]['edition_number'])
        self.assertEqual('Refunded', actions.final_fulfilment_status(rows[0]))

    def test_reconcile_only_writes_orders_and_visibility_marker(self):
        cur = Mock()
        cur.fetchone.return_value = {'refund': None}
        cur.fetchall.return_value = [{'shopify_order_id': 'gid://shopify/Order/1'}]
        conn = Mock()
        conn.cursor.return_value.__enter__ = Mock(return_value=cur)
        conn.cursor.return_value.__exit__ = Mock(return_value=False)
        ctx = Mock(__enter__=Mock(return_value=conn), __exit__=Mock(return_value=False))
        backend = SimpleNamespace(connect=Mock(return_value=ctx))
        shopify = SimpleNamespace(shopify_gid=lambda kind, id: id,
                                  graphql_request=Mock(return_value=({'nodes': [node('REFUNDED', 'SUCCESS', 0)]}, '2026-04')))
        for _ in range(2):
            refunds.reconcile(['gid://shopify/Order/1'], backend=backend, shopify=shopify)
        sql = '\n'.join(call.args[0] for call in cur.execute.call_args_list)
        self.assertNotIn('edition_orders', sql)
        self.assertNotIn('certificates', sql)
        self.assertNotIn('DELETE', sql)
        self.assertNotIn('fulfillment_status=', sql)
        self.assertIn('FOR UPDATE', sql)
        self.assertIn('remote_updated_at', sql)
        self.assertEqual(2, conn.commit.call_count)
        self.assertTrue(all('mutation' not in call.args[0] for call in shopify.graphql_request.call_args_list))

    def test_certificate_and_dispatch_guard(self):
        cur = Mock()
        cur.fetchone.return_value = {'raw_json': {'_orders_refund': {'blocked': True}}}
        with self.assertRaises(ValueError):
            refunds.assert_processing_allowed(cur, 'gid://shopify/Order/1')

    def test_canvas_display_strikes_text_without_altering_data(self):
        fake_streamlit = SimpleNamespace(__name__='streamlit')
        with patch.object(orders_page, 'st', fake_streamlit), patch.object(orders_page, '_display_rows', return_value=[{'order': '#SC1', 'prodigi': 'Refunded', 'edition': '#019'}]):
            styled = orders_page._display_table_payload([])
        self.assertEqual('#SC1', styled.data.iloc[0]['order'])
        self.assertIn('\u0336', styled._display_funcs[(0, 0)]('#SC1'))

    def test_normal_orders_unchanged(self):
        row = self.row(node())
        self.assertFalse(refunds.blocked(row))
        self.assertEqual('Needs certificate', actions.final_fulfilment_status(row))

    def test_refund_ui_styles_and_existing_refresh(self):
        self.assertIn('#c92a2a', orders_page._fulfilment_cell_style('Refunded'))
        self.assertIn('line-through', inspect.getsource(orders_page._display_table_payload))
        self.assertIn('orders_refund_visibility', inspect.getsource(supabase_backend.orders_visibility_marker))
        self.assertIn('order_refunds.reconcile', Path('shopify_order_reconciliation_worker.py').read_text())


if __name__ == '__main__':
    unittest.main()
