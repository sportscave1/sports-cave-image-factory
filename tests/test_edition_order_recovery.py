import unittest
from unittest.mock import MagicMock, patch
import edition_order_recovery as recovery


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.order = dict(order_name='#SC3232', shopify_order_id='gid://shopify/Order/1', financial_status='PAID', raw_json={'line_items': [{}]})
        self.line = dict(shopify_line_item_id='gid://shopify/LineItem/2', quantity=1, assignment_status='Needs product mapping', product_title='Old title')
        self.product = dict(id=723, shopify_product_gid='gid://shopify/Product/3', product_title='Verified artwork', shopify_handle='verified-artwork', next_edition_number=37, sold_count=0, remaining_count=100, edition_total=100, active_edition_run_id='run')
        self.confirm = '#SC3232:gid://shopify/LineItem/2:723'

    def test_unmapped_requires_exact_confirmation(self):
        with self.assertRaisesRegex(ValueError, 'confirmation'):
            recovery.validate_mapping(self.order, self.line, self.product)
        self.assertEqual(recovery.validate_mapping(self.order, self.line, self.product, self.confirm), self.product['shopify_product_gid'])

    def test_wrong_product_fails_even_with_confirmation(self):
        self.line['shopify_product_id'] = 'gid://shopify/Product/99'
        with self.assertRaisesRegex(ValueError, 'Wrong product'):
            recovery.validate_mapping(self.order, self.line, self.product, self.confirm)

    def test_wrong_handle_fails(self):
        self.line['shopify_handle'] = 'other-tom-brady'
        with self.assertRaisesRegex(ValueError, 'Wrong product'):
            recovery.validate_mapping(self.order, self.line, self.product, self.confirm)

    def test_paid_cancelled_test_safety(self):
        for changes in ({'financial_status': 'REFUNDED'}, {'cancelled_at': '2026-10-04'}, {'test': True}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                recovery.validate_mapping({**self.order, **changes}, self.line, self.product, self.confirm)

    def cursor(self, existing=False):
        cur = MagicMock()
        cur.fetchone.return_value = self.product
        cur.fetchall.side_effect = [[{'id': 1}] if existing else [], [{'result': {'allocation': {'edition_number': 37}, 'was_created': not existing}}]]
        return cur

    def test_late_product_maps_and_audits_current_next(self):
        cur = self.cursor()
        with patch.object(recovery, 'load', return_value=(self.order, self.line, self.product)), patch.object(recovery.backend, '_set_order_line_status') as status:
            result = recovery.apply(cur, '#SC3232', self.line['shopify_line_item_id'], 723, confirmation=self.confirm, expected_next=37)
        self.assertEqual((result['next_before'], result['next_after'], result['created']), (37, 38, 1))
        status.assert_called_once()
        audits = [c for c in cur.execute.call_args_list if 'INSERT INTO edition_adjustments' in c.args[0]]
        self.assertEqual(len(audits), 1)
        self.assertIn(recovery.REASON, audits[0].args[1][-1])

    def test_replay_has_no_audit_mapping_or_counter_write(self):
        cur = self.cursor(existing=True)
        with patch.object(recovery, 'load', return_value=(self.order, self.line, self.product)), patch.object(recovery.backend, '_set_order_line_status') as status:
            result = recovery.apply(cur, '#SC3232', self.line['shopify_line_item_id'], 723, confirmation=self.confirm, expected_next=36)
        self.assertEqual(result['created'], 0)
        status.assert_not_called()
        self.assertFalse(any('INSERT' in c.args[0] for c in cur.execute.call_args_list))

    def test_stale_preview_fails_before_allocator(self):
        cur = self.cursor()
        with patch.object(recovery, 'load', return_value=(self.order, self.line, self.product)), self.assertRaisesRegex(ValueError, 'preview again'):
            recovery.apply(cur, '#SC3232', self.line['shopify_line_item_id'], 723, confirmation=self.confirm, expected_next=36)
        self.assertFalse(any('allocate_edition_line_units_atomic' in c.args[0] for c in cur.execute.call_args_list))

    def test_collision_rolls_back_never_mirrors(self):
        conn = MagicMock()
        conn.__enter__.return_value = conn
        with patch.object(recovery.backend, 'connect', return_value=conn), patch.object(recovery, 'apply', side_effect=ValueError('collision')), patch.object(recovery.backend, 'sync_product_edition_metafields_for_handles') as mirror:
            with self.assertRaises(ValueError):
                recovery.allocate('order', 'line', 723)
        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()
        mirror.assert_not_called()

    def test_mirror_failure_keeps_commit(self):
        conn = MagicMock()
        conn.__enter__.return_value = conn
        with patch.object(recovery.backend, 'connect', return_value=conn), patch.object(recovery, 'apply', return_value={'handle':'art', 'action_id':'repair', 'allocations':[{'edition_number':37}]}), patch.object(recovery.backend, 'sync_product_edition_metafields_for_handles', side_effect=RuntimeError('offline')):
            result = recovery.allocate('order', 'line', 723)
        conn.commit.assert_called_once()
        conn.rollback.assert_not_called()
        self.assertTrue(result['mirror']['errors'])

    def test_admin_ui_requires_preview_and_explicit_confirm(self):
        from streamlit.testing.v1 import AppTest
        app = AppTest.from_string("""
import edition_order_recovery as r
r.render(True, [{'edition_product_id':723, 'product_title':'Verified artwork'}])
""")
        value = dict(order='#SC3232', line_id='gid://shopify/LineItem/2', product_id=723,
                     product='Verified artwork', next=37, confirmation=self.confirm)
        with patch.object(recovery, 'preview', return_value=value), patch.object(recovery, 'allocate') as allocate:
            app.run()
            self.assertFalse(app.exception)
            allocate.assert_not_called()
            app.text_input(key='late-order').set_value('#SC3232')
            app.text_input(key='late-line').set_value('gid://shopify/LineItem/2')
            app.run()
            next(b for b in app.button if b.label == 'Preview allocation').click().run()
            self.assertTrue(app.button(key='late-apply').disabled)
            app.checkbox(key='late-confirm').check().run()
            self.assertFalse(app.button(key='late-apply').disabled)
            allocate.assert_not_called()
            allocate.return_value = {'allocations':[{'edition_number':37,'edition_total':100}], 'mirror':{}}
            with patch('edition_ops._invalidate_edition_ops_cache'):
                app.button(key='late-apply').click().run()
            allocate.assert_called_once_with('#SC3232', 'gid://shopify/LineItem/2', 723, confirmation=self.confirm, expected_next=37)
            self.assertFalse(app.exception)


if __name__ == '__main__':
    unittest.main()
