import inspect
import unittest
from unittest.mock import MagicMock, patch

import certificate_engine
import order_allocator
import orders_page
import os_pages
import supabase_backend as backend
from tests.test_manual_expired_edition_entry import eligible_state

REF = 'manual-edition:00000000-0000-0000-0000-000000000001'
ACTOR = {'id': '00000000-0000-0000-0000-000000000002', 'role': 'admin'}
ROW = dict(edition_order_id=REF, edition_number=100, edition_total=100,
           manual_edition_override=True, order='#SC3150', shopify_order_id='1',
           shopify_line_item_id='2', shopify_product_id='3', product='Wall Art',
           product_handle='wall-art', variant='Black / L', shipping_method='Standard')
ANSWERS = dict.fromkeys(('artwork_upload', 'product_option', 'frame', 'size', 'shipping',
                         'sent_to_production', 'final_check', 'edition_number'), 'Yes')


class ManualCertificateControlsTests(unittest.TestCase):
    def test_normal_display_and_certificate_number_unchanged(self):
        row = orders_page._normalise_row({**ROW, 'edition_order_id': '52',
                                        'edition_number': 52, 'manual_edition_override': False})
        self.assertEqual(row['edition'], '#052/100')
        self.assertEqual(certificate_engine.certificate_record_from_order_row(row)['edition_number'], 52)

    def test_manual_display_and_normal_template_number(self):
        row = orders_page._normalise_row(ROW)
        self.assertEqual(row['edition'], 'Not allocated · Manual cert #100/100')
        self.assertFalse(row['has_saved_allocation'])
        self.assertEqual(row['assignment_status'], 'Not allocated')
        record = certificate_engine.certificate_record_from_order_row(row)
        self.assertEqual((record['edition_number'], record['edition_total']), (100, 100))
        self.assertEqual(record['edition_order_id'], REF)
        self.assertEqual(certificate_engine.certificate_metafield_record(record)['edition_order_id'], REF)

    def test_real_reference_wins_over_stale_manual_flag(self):
        row = orders_page._normalise_row({**ROW, 'edition_order_id': '52', 'edition_number': 52})
        self.assertEqual(row['edition'], '#052/100')
        cur = MagicMock()
        self.assertIsNone(backend._manual_order_line_edition_assignment(cur, '52'))
        cur.execute.assert_not_called()

    def test_manual_snapshot_does_not_claim_saved_allocation(self):
        rows = order_allocator._snapshot_rows_from_supabase_order_rows([{
            'shopify_order_id': '1', 'shopify_line_item_id': '2', 'quantity': 1,
            'assignments': [{**ROW, 'allocation_index': 1}],
        }])
        self.assertFalse(rows[0]['has_saved_allocation'])
        self.assertFalse(rows[0]['certificate_generated_at'])

    def test_qa_missing_and_incomplete_blocked(self):
        for value in (None, {}, {'answers': {**ANSWERS, 'frame': 'No'}}):
            cur = MagicMock()
            cur.fetchone.return_value = value
            with self.assertRaisesRegex(ValueError, 'Complete Fulfilment QA'):
                backend._require_manual_certificate_qa(cur, {**ROW, 'id': REF, 'verified_at': '2026-09-13'})

    def test_qa_complete_allowed_and_normal_orders_not_gated_differently(self):
        cur = MagicMock()
        cur.fetchone.return_value = {'answers': ANSWERS}
        backend._require_manual_certificate_qa(cur, {**ROW, 'id': REF, 'verified_at': '2026-09-13'})
        self.assertIn('updated_at >=', cur.execute.call_args.args[0])
        cur.reset_mock()
        backend._require_manual_certificate_qa(cur, {'id': '52'})
        cur.execute.assert_not_called()

    def test_save_only_writes_separate_override(self):
        conn = MagicMock()
        cur = conn.__enter__.return_value.cursor.return_value.__enter__.return_value
        cur.fetchone.return_value = {'id': REF.split(':')[1], 'edition_number': 100, 'edition_total': 100}
        with patch.object(backend, 'connect', return_value=conn), \
             patch.object(backend, '_manual_edition_state_with_cursor', return_value=eligible_state()), \
             patch.object(backend, 'ensure_schema') as ddl:
            backend.save_manual_order_line_edition(source_channel='Shopify', external_order_id='1',
                external_line_item_id='2', expected_product_gid='3', edition_number=100,
                edition_total=100, reason='Legacy checkout', actor=ACTOR)
        ddl.assert_not_called()
        statements = [call.args[0] for call in cur.execute.call_args_list]
        self.assertEqual(len(statements), 1)
        self.assertIn('INSERT INTO manual_order_line_editions', statements[0])
        for forbidden in ('UPDATE edition_products', 'UPDATE edition_runs', 'INSERT INTO edition_orders', 'reservation'):
            self.assertNotIn(forbidden, statements[0])

    def test_duplicate_requires_explicit_confirmation(self):
        with patch.object(backend, 'connect', return_value=MagicMock()), \
             patch.object(backend, '_manual_edition_state_with_cursor', return_value=eligible_state(allocated_numbers=[100])):
            with self.assertRaisesRegex(ValueError, 'Confirm the duplicate'):
                backend.save_manual_order_line_edition(source_channel='shopify', external_order_id='1',
                    external_line_item_id='2', expected_product_gid='3', edition_number=100,
                    edition_total=100, reason='Exception', actor=ACTOR)

    def test_non_integer_rejected_before_connection(self):
        for value in (1.5, True, '1.5'):
            with patch.object(backend, 'connect') as connect, self.assertRaises(ValueError):
                backend.save_manual_order_line_edition(source_channel='shopify', external_order_id='1',
                    external_line_item_id='2', expected_product_gid='3', edition_number=value,
                    edition_total=100, reason='Exception', actor=ACTOR)
            connect.assert_not_called()

    def test_edit_eligibility_and_generated_lock(self):
        state = eligible_state(manual_edition_id='saved', manual_number=100)
        self.assertTrue(backend._manual_edition_eligibility_from_state(state, allow_existing=True)['eligible'])
        self.assertFalse(backend._manual_edition_eligibility_from_state({**state, 'certificate_count': 1}, allow_existing=True)['eligible'])

    def test_normal_generator_used_and_no_allocation_update_for_manual(self):
        for reference, number in ((REF, 100), ('52', 52)):
            cur = MagicMock()
            cur.fetchone.return_value = None
            with patch.object(backend, 'generate_certificate_pdf', return_value='mock.pdf') as pdf, \
                 patch.object(backend, 'generate_certificate_preview_png', return_value='mock.png'), \
                 patch.object(backend, '_upload_certificate_outputs_to_r2'):
                backend._generate_certificate_for_assignment(cur, {**ROW, 'id': reference, 'edition_number': number})
            self.assertEqual(pdf.call_args.kwargs['edition_number'], number)
            sql = '\n'.join(call.args[0] for call in cur.execute.call_args_list)
            self.assertIn('INSERT INTO certificates', sql)
            self.assertEqual('UPDATE edition_orders' in sql, reference != REF)

    def test_fulfilment_saves_qa_before_normal_certificate_job(self):
        events = []
        with patch.object(os_pages, '_prodigi_is_limited_edition', return_value=True), \
             patch.object(os_pages, '_prodigi_certificate_uploaded', return_value=False), \
             patch.object(os_pages, 'prodigi_completion_blockers', return_value=[]), \
             patch.object(os_pages, 'prodigi_save_dispatch_row', side_effect=lambda *a, **k: events.append(k['status'])), \
             patch.object(os_pages.certificate_job, 'run_certificate_job_with_timeout', side_effect=lambda *a, **k: events.append('generate') or {'ok': True}), \
             patch.object(os_pages, 'bump_supabase_cache_version'), patch.object(os_pages.st, 'session_state', {}):
            os_pages.prodigi_generate_upload_certificate_for_row(ROW, config={'configured': True}, qa_answers=ANSWERS)
        self.assertEqual(events, ['QA checked - certificate pending', 'generate'])

    def test_qa_failure_never_invokes_certificate_job(self):
        with patch.object(os_pages, '_prodigi_is_limited_edition', return_value=True), \
             patch.object(os_pages, '_prodigi_certificate_uploaded', return_value=False), \
             patch.object(os_pages, 'prodigi_completion_blockers', return_value=['Frame not checked']), \
             patch.object(os_pages.certificate_job, 'run_certificate_job_with_timeout') as job:
            with self.assertRaisesRegex(ValueError, 'Complete Fulfilment QA'):
                os_pages.prodigi_generate_upload_certificate_for_row(ROW, config={'configured': True}, qa_answers={})
        job.assert_not_called()

    def test_ui_duplicate_warning_disables_save_until_confirmed(self):
        for confirmed in (False, True):
            ui = MagicMock()
            ui.number_input.return_value = 100
            ui.text_area.return_value = 'Legacy checkout'
            ui.checkbox.return_value = confirmed
            ui.button.return_value = False
            with patch.object(orders_page, 'st', ui):
                inspect.unwrap(orders_page._manual_certificate_dialog)(ROW,
                    {'canonical_edition_total': 100, 'allocated_numbers': [100]}, MagicMock(), ACTOR)
            self.assertIn('duplicate certificate number', ui.warning.call_args.args[0])
            save = next(c for c in ui.button.call_args_list if c.args[0] == 'Save Manual Certificate')
            self.assertEqual(save.kwargs['disabled'], not confirmed)

    def test_ui_action_hidden_for_genuine_allocations(self):
        ui = MagicMock()
        ui.session_state = {'sports_cave_current_user': ACTOR}
        with patch.object(orders_page, 'st', ui):
            orders_page._render_manual_edition_entry([{**ROW, 'edition_order_id': '52'}], MagicMock())
        ui.button.assert_not_called()

    def test_upload_metadata_does_not_write_allocation_table(self):
        conn = MagicMock()
        cur = conn.__enter__.return_value.cursor.return_value.__enter__.return_value
        cur.fetchone.return_value = {'id': 1}
        record = certificate_engine.certificate_record_from_order_row(ROW)
        with patch.object(backend, 'connect', return_value=conn), patch.object(backend, 'is_configured', return_value=True):
            backend.upsert_certificate_metadata(record, ensure_schema_first=False)
        sql = '\n'.join(call.args[0] for call in cur.execute.call_args_list)
        self.assertIn('UPDATE certificates', sql)
        self.assertNotIn('UPDATE edition_orders', sql)

    def test_fulfilment_table_identifies_manual_certificate(self):
        record = os_pages.prodigi_dispatch_table_records([ROW])[0]
        self.assertEqual(record['Edition #'], 'Not allocated · Manual cert #100/100')


if __name__ == '__main__':
    unittest.main()
