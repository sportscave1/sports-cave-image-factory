from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch
import unittest
import orders_page as orders


class CompactOrdersTests(unittest.TestCase):
    def test_bulk_selection_only_loads_one_stably_identified_detail_panel(self):
        rows=[{'edition_order_id':i,'order':f'#SC{i}'} for i in range(1,51)]
        before=deepcopy(rows);seen=[]
        def choose(label,options,**kwargs):seen.extend(options);return 'allocation:50'
        with patch.object(orders,'st',SimpleNamespace(selectbox=choose)):
            assert orders._selected_detail_rows(rows)==[rows[-1]]
        assert len(seen)==50 and rows==before
        assert orders._selected_detail_rows([rows[0]])==[rows[0]]

    def test_jpg_status_deadline_keeps_the_order_visible_without_claiming_repair(self):
        from concurrent.futures import Future
        from supabase_backend import DatabaseReadError
        future=Future();future.set_exception(DatabaseReadError('deadline exceeded',{}))
        warnings=[];rows=[{'edition_order_id':952,'order':'#SC3522'}]
        with patch.object(orders,'st',SimpleNamespace(warning=warnings.append)), \
             patch.object(orders._ORDERS_LOAD_EXECUTOR,'submit',return_value=future), \
             patch.object(orders.psd_directory,'page_directory',return_value={}):
            resources=orders._order_display_resources(rows)
        assert resources==({}, {'952':'Status unavailable'}) and len(warnings)==1
        display=orders._display_rows(rows,resources=resources)
        assert display[0]['print_jpg']=='Status unavailable'

    def test_initial_layout_waits_for_client_instead_of_exposing_wrong_actions(self):
        class WaitingForClient(Exception): pass
        fake=SimpleNamespace(__name__='streamlit',session_state={},caption=lambda *a:None,
                             stop=lambda: (_ for _ in ()).throw(WaitingForClient()))
        with patch.object(orders,'st',fake),patch.object(orders.components,'declare_component') as declare:
            declare.return_value.return_value=None
            with self.assertRaises(WaitingForClient):orders._responsive_orders_mode()
            self.assertIsNone(declare.return_value.call_args.kwargs['default'])
            self.assertNotIn('orders-narrow-view',fake.session_state)

    def test_layout_survives_component_initialisation_during_rerender(self):
        for previous in (True,False):
            fake=SimpleNamespace(__name__='streamlit',session_state={'orders-narrow-view':previous})
            with patch.object(orders,'st',fake),patch.object(orders.components,'declare_component') as declare:
                declare.return_value.side_effect=lambda **kwargs:kwargs['default']
                orders._responsive_orders_mode()
                self.assertIs(fake.session_state['orders-narrow-view'],previous)

    def setUp(self):
        self.directory_patch=patch.object(orders.psd_directory,'directory',return_value={})
        self.directory_patch.start()
        self.addCleanup(self.directory_patch.stop)

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
