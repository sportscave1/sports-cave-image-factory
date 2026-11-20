"""Offline regression for SC3504: edition sequence is independent of sales."""
import socket
import unittest
from unittest.mock import Mock, patch

import supabase_backend as backend


class RecalculationSalesTests(unittest.TestCase):
    def recalculate(self, sold, maximum=93):
        product = dict(id=3, shopify_handle='fixture-art', edition_total=100,
                       next_edition_number=94, sold_count=sold, remaining_count=7)
        run = dict(id='fixture-run', edition_total=100, next_edition_number=94)
        cursor = Mock()
        cursor.fetchone.return_value = product
        with patch.object(socket.socket, 'connect', side_effect=AssertionError('No network')), \
             patch.object(backend, '_max_assigned_for_product', return_value=maximum), \
             patch.object(backend, '_insert_edition_adjustment_with_cursor'):
            result = backend._recalculate_next_edition_number_with_cursor(cursor, product, run)
        writes = [call.args for call in cursor.execute.call_args_list
                  if 'UPDATE edition_products' in call.args[0]]
        return result, writes

    def test_sc3504_remaining_uses_sales_not_highest_issued_number(self):
        result, writes = self.recalculate(92)
        self.assertEqual(result['next_edition_number'], 94)
        self.assertEqual(result['remaining_count'], 8)
        self.assertEqual(writes[0][1][:3], (94, 93, 8))
        self.assertNotIn('sold_count=', writes[0][0])

    def test_offset_numbering_preserves_sales(self):
        result, _ = self.recalculate(2, maximum=51)
        self.assertEqual(result['remaining_count'], 98)
        self.assertEqual(result['next_edition_number'], 52)

    def test_exhausted_numbers_do_not_fabricate_sales_or_reuse_number_100(self):
        result, _ = self.recalculate(2, maximum=100)
        self.assertEqual(result['remaining_count'], 98)
        self.assertEqual(result['next_edition_number'], 101)
        self.assertTrue(result['sold_out'])

    def test_full_sales_blocks_allocation_even_with_lower_number(self):
        result, _ = self.recalculate(100)
        self.assertEqual(result['remaining_count'], 0)
        self.assertTrue(result['sold_out'])

    def test_invalid_sales_fail_before_any_write(self):
        for sold in (None, -1, 101, 'invalid'):
            with self.subTest(sold=sold), patch.object(backend, '_max_assigned_for_product', return_value=93):
                cursor = Mock()
                with self.assertRaisesRegex(ValueError, 'Sales unit count requires review'):
                    backend._recalculate_next_edition_number_with_cursor(
                        cursor, dict(shopify_handle='fixture-art', sold_count=sold),
                        dict(id='fixture-run', edition_total=100))
                cursor.execute.assert_not_called()


if __name__ == '__main__':
    unittest.main()
