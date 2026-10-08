from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch
import unittest
import orders_page as orders


class CompactOrdersTests(unittest.TestCase):
    def test_selection_only_normalises_selected_units(self):
        rows=[{'order':'#SC1','allocation_index':i,'edition_number':i} for i in range(1,63)]
        before=deepcopy(rows)
        with patch.object(orders,'_selected_indices_from_state',return_value=[0,61,999,-1]), patch.object(orders,'_normalise_row',wraps=orders._normalise_row) as normalise:
            selected=orders._selected_rows_from_state(rows)
        self.assertEqual(normalise.call_count,2)
        self.assertEqual([r['edition_number'] for r in selected],[1,62])
        self.assertEqual(rows,before)

    def test_normalised_display_matches_original_projection_without_rework(self):
        rows=[{'order':'#SC12','edition_number':5,'edition_total':100,'variant':'Black / 60 x 90 cm','prodigi_status':'Complete'},
              {'order':'#SC12','edition_number':6,'allocation_index':2,'prodigi_status':'Issue'}]
        expected=orders._display_rows(rows)
        normalised=[orders._normalise_row(r) for r in rows]
        with patch.object(orders,'_normalise_row',side_effect=AssertionError('Already normalised')):
            self.assertEqual(orders._display_rows(normalised,normalised=True),expected)

    def test_latest_50_keeps_all_units_without_informational_captions(self):
        rows=[{'order':f'#SC{i//2}','allocation_index':i%2+1} for i in range(100)]
        fake=SimpleNamespace(session_state={orders.ROWS_KEY:rows,orders.META_KEY:{}},caption=lambda *a: self.fail('Unexpected caption'))
        with patch.object(orders,'st',fake),patch.object(orders,'_apply_latest_product_numbers',side_effect=lambda r:r),patch.object(orders,'_developer_mode',return_value=False),patch.object(orders,'_render_top_actions'),patch.object(orders,'_render_orders_table') as table:
            orders._render_orders_data_area()
            self.assertEqual(table.call_args.args[0],rows)


if __name__=='__main__':unittest.main()
