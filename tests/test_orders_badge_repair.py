import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock, patch

import order_action_state as actions
import order_refunds as refunds
import orders_page
import top_bar_api
from tests.test_order_refunds import node


class OrdersBadgeRepairTests(unittest.TestCase):
    def row(self, value, **fields):
        return {'shopify_order_id': 'order1', 'financial_status': 'PAID',
                'order_raw_json': {'_orders_refund': refunds.projection(value)}, **fields}

    def test_missing_local_fulfilment_uses_reconciled_shopify_truth(self):
        value = node()
        value['displayFulfillmentStatus'] = 'FULFILLED'
        row = self.row(value, fulfillment_status='')
        self.assertEqual('Complete', actions.final_fulfilment_status(row))
        self.assertFalse(actions.row_requires_action(row))
        self.assertTrue(actions.row_requires_action({**row, 'prodigi_status': 'Submitted'}))

    def test_multiline_partial_refund_counts_order_once_and_ignores_removed_lines(self):
        value = node('PARTIALLY_REFUNDED', 'SUCCESS')
        value['lineItems']['nodes'] = [
            {'id': 'gid://shopify/LineItem/1', 'currentQuantity': 0, 'unfulfilledQuantity': 0},
            {'id': 'gid://shopify/LineItem/2', 'currentQuantity': 1, 'unfulfilledQuantity': 1}]
        removed = self.row(value, financial_status='PARTIALLY_REFUNDED', shopify_line_item_id='1')
        remaining = {**removed, 'shopify_line_item_id': 'gid://shopify/LineItem/2'}
        self.assertFalse(actions.row_requires_action(removed))
        self.assertEqual(1, actions.count_orders_requiring_action([removed, remaining, remaining]))
        self.assertEqual(0, actions.count_orders_requiring_action([removed, {**remaining, 'prodigi_status': 'Complete'}]))

    def test_cancelled_pending_and_confirmed_refund_are_excluded(self):
        cancelled = node()
        cancelled['cancelledAt'] = '2026-10-16T00:00:00Z'
        rows = [self.row(cancelled), self.row(node(status='PENDING', remaining=0)),
                self.row(node('REFUNDED', 'SUCCESS', 0))]
        self.assertEqual(0, actions.count_orders_requiring_action(rows))

    def test_timestamp_only_changes_do_not_invalidate_visibility(self):
        before = refunds.projection(node())
        after = {**before, 'remote_updated_at': '2026-10-17T00:00:00Z'}
        self.assertEqual(refunds.semantic_state(before), refunds.semantic_state(after))
        self.assertNotEqual(refunds.semantic_state(before), refunds.semantic_state({**after, 'blocked': True}))

    def test_duplicate_or_timestamp_only_webhooks_do_not_publish_refresh_events(self):
        value = node()
        previous = {**refunds.projection(value), 'remote_updated_at': '2026-10-15T09:00:00Z'}
        cur = Mock()
        cur.fetchone.return_value = {'refund': previous}
        cur.fetchall.return_value = [{'shopify_order_id': value['id']}]
        cur.rowcount = 1
        conn = Mock()
        conn.cursor.return_value.__enter__ = Mock(return_value=cur)
        conn.cursor.return_value.__exit__ = Mock(return_value=False)
        context = Mock(__enter__=Mock(return_value=conn), __exit__=Mock(return_value=False))
        backend = SimpleNamespace(connect=Mock(return_value=context))
        shopify = SimpleNamespace(shopify_gid=lambda kind, identity: identity,
            graphql_request=Mock(return_value=({'nodes': [value]}, '2026-04')))
        refunds.reconcile([value['id'], value['id']], backend=backend, shopify=shopify)
        self.assertEqual(1, shopify.graphql_request.call_count)
        sql = '\n'.join(call.args[0] for call in cur.execute.call_args_list)
        self.assertNotIn('INSERT INTO app_settings', sql)
        self.assertIn("- 'remote_updated_at'", sql)

    def test_badge_requests_coalesce_and_expire(self):
        gate = threading.Event()
        backend = SimpleNamespace(get_order_action_summary=Mock(
            side_effect=lambda: (gate.wait(2), {'action_required_count': 3})[1]))
        with patch.dict(top_bar_api._ORDER_SUMMARY_DISPLAY_CACHE, {'expires_at': 0, 'value': None}):
            with ThreadPoolExecutor(max_workers=6) as executor:
                futures = [executor.submit(top_bar_api._cached_order_action_summary, backend, now=10) for _ in range(6)]
                gate.set()
                self.assertEqual([3] * 6, [future.result()['action_required_count'] for future in futures])
            self.assertEqual(1, backend.get_order_action_summary.call_count)
            top_bar_api._cached_order_action_summary(backend, now=41)
            self.assertEqual(2, backend.get_order_action_summary.call_count)

    def test_failed_aggregate_never_loads_full_orders_table(self):
        import supabase_backend
        with patch.object(supabase_backend, 'is_configured', return_value=True), patch.object(
                top_bar_api, '_cached_order_action_summary', side_effect=RuntimeError), patch.object(
                supabase_backend, 'consume_new_order_notifications', return_value=[]), patch(
                'order_allocator.load_orders_snapshot') as snapshot:
            result = top_bar_api.load_order_status({'sub': 'test', 'allowed_routes': ['Orders']})
        snapshot.assert_not_called()
        self.assertIsNone(result['action_required_count'])

    def test_independent_link_reads_overlap_and_are_reused_for_table(self):
        import auto_editions_runtime
        started = threading.Event()
        def jpg(rows):
            started.set()
            return {'1': 'saved-link'}
        def mapping(ui):
            self.assertTrue(started.wait(2))
            return {}
        with patch.object(auto_editions_runtime, 'download_links', side_effect=jpg) as links, patch.object(
                orders_page.psd_directory, 'page_directory', side_effect=mapping) as directory:
            resources = orders_page._order_display_resources([])
            self.assertEqual([], orders_page._display_rows([], normalised=True, resources=resources))
        self.assertEqual(1, links.call_count)
        self.assertEqual(1, directory.call_count)


if __name__ == '__main__':
    unittest.main()
