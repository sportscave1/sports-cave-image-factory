"""Offline reproduction from supplied SC3351 details; no production data access."""
import copy
import json
import sqlite3
import tempfile
import unittest
from contextlib import ExitStack, closing, nullcontext
from pathlib import Path
from unittest.mock import patch, MagicMock

import os_pages as page
import supabase_backend as backend

USER = {'id': 'qa-reviewer', 'email': 'reviewer@example.test', 'role': 'worker',
        'page_permissions': ['prodigi'], 'is_active': True}


def fixture():
    return page.prodigi_tracker_row_from_order({
        'order': '#SC3351', 'channel': 'Etsy', 'customer': 'Carol Cranwell',
        'product': 'Taylor Walker Crows Art', 'edition_number': 2, 'edition_total': 100,
        'variant': 'Unframed / 45 × 62 cm',
    })


class SQLiteConnection:
    """Run the existing dispatch INSERT/UPSERT against a disposable database."""
    def __init__(self, path):
        self.conn = sqlite3.connect(path)
        self.conn.create_function('now', 0, lambda: '2026-10-25T00:00:00+00:00')
    def __enter__(self): return self
    def __exit__(self, *args): self.conn.close()
    def cursor(self): return nullcontext(self)
    def execute(self, sql, args=()):
        self.conn.execute(sql.replace('%s', '?').replace('::jsonb', ''), args)
    def commit(self): self.conn.commit()


class EtsyQATests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.state = {'sports_cave_current_user': dict(USER)}
        self.stack.enter_context(patch.object(page.st, 'session_state', self.state))
        self.stack.enter_context(patch.object(backend, 'is_configured', return_value=True))
        self.stack.enter_context(patch.object(page, 'bump_supabase_cache_version'))
        self.log = self.stack.enter_context(patch.object(page, 'record_activity_log'))
        self.save = self.stack.enter_context(patch.object(backend, 'upsert_prodigi_dispatch_row', return_value={'upserted': 1}))
        self.stack.enter_context(patch.object(page, 'prodigi_generate_upload_certificate_for_row', side_effect=AssertionError('No certificate generation')))

    def complete(self, row=None, **kwargs):
        args = dict(qa_answers={'certificate': 'Yes'}, confirmed=True,
                    reason='Manually checked Etsy artwork, edition and customer requirements')
        args.update(kwargs)
        return page.prodigi_complete_etsy_qa(fixture() if row is None else row, **args)

    def test_sc3351_reproduces_legacy_blockers_and_qa_only_completion(self):
        row = fixture()
        before = copy.deepcopy(row)
        legacy = page.prodigi_manual_override_eligibility(row, {})
        self.assertFalse(legacy['can_complete'])
        self.assertIn('Missing Fulfilment mapping', legacy['original_errors'])
        saved = self.complete(row)
        self.assertEqual(before, row)
        self.assertTrue(saved['qa_completed'])
        self.assertEqual('Complete', page.prodigi_dispatch_table_records([saved])[0]['QA Status'])
        self.assertFalse(page._prodigi_submitted(saved))
        self.assertFalse(page._prodigi_fulfilled(saved))
        self.assertFalse(saved['qa_confirmed'])
        self.assertEqual('No', saved['qa_answers']['certificate'])
        for key in ('submitted_at', 'date_sent_to_prodigi', 'date_shipped', 'date_fulfilled_in_shopify',
                    'tracking_number', 'certificate_status', 'certificate_pdf_url', 'shopify_file_url',
                    'edition_number', 'edition_total', 'prodigi_code', 'prodigi_order_id'):
            self.assertEqual(before[key], saved[key], key)
        self.assertEqual(USER['id'], saved['fulfilment_override_actor_id'])
        self.assertEqual(USER['email'], saved['fulfilment_override_by'])
        self.assertIn('Certificate not uploaded', saved['fulfilment_override_original_errors'])
        self.assertEqual('etsy_manual_qa_override', self.log.call_args.args[0])

    def test_unknown_and_shopify_sources_fail_closed(self):
        for source in ('Shopify', '', 'manual', 'unknown', 'not etsy'):
            with self.subTest(source=source), self.assertRaises(ValueError):
                self.complete({**fixture(), 'channel': source})
        self.save.assert_not_called()

    def test_confirmation_reason_identity_and_authorization_required(self):
        for kwargs in ({'confirmed': False}, {'reason': '  '}, {'reason': 'x' * 1001}):
            with self.assertRaises(ValueError): self.complete(**kwargs)
        with self.assertRaises(ValueError): self.complete({**fixture(), 'row_id': ''})
        for user in ({}, {**USER, 'is_active': False}, {**USER, 'page_permissions': []}):
            self.state['sports_cave_current_user'] = user
            with self.assertRaises(PermissionError): self.complete()
        self.save.assert_not_called()

    def test_existing_certificate_and_shipping_evidence_preserved(self):
        row = {**fixture(), 'certificate_pdf_url': 'https://example.test/existing.pdf',
               'tracking_number': 'existing-tracking', 'date_sent_to_prodigi': '2026-10-20'}
        saved = self.complete(row)
        for key in ('certificate_pdf_url', 'tracking_number', 'date_sent_to_prodigi'):
            self.assertEqual(row[key], saved[key])
        self.assertTrue(page._prodigi_submitted(saved))

    def test_refund_guard_is_not_bypassed(self):
        with self.assertRaisesRegex(ValueError, 'refund'):
            self.complete({**fixture(), '_orders_refund': {'blocked': True}})
        self.save.assert_not_called()

    def test_failed_save_and_duplicate_do_not_report_success(self):
        self.save.return_value = {'upserted': 0}
        with self.assertRaises(RuntimeError): self.complete()
        self.log.assert_not_called()
        with self.assertRaises(ValueError): self.complete({**fixture(), 'prodigi_status': 'Complete'})

    def test_ui_action_saves_and_refreshes_without_certificate_generation(self):
        ui = MagicMock()
        ui.session_state = self.state
        ui.text_input.return_value = 'Reviewed manual Etsy fulfilment'
        ui.checkbox.return_value = True
        ui.button.return_value = True
        with patch.object(page, 'st', ui), patch.object(page, 'prodigi_load_dispatch_rows', return_value=[]) as reload:
            page._render_etsy_qa_override(fixture(), {}, '', 'fixture', '#SC3351')
        self.assertEqual('Manual Override & Complete QA', ui.button.call_args.args[0])
        self.save.assert_called_once()
        reload.assert_called_once()
        ui.rerun.assert_called_once()

    def test_ui_hidden_without_fulfilment_access(self):
        ui = MagicMock()
        ui.session_state = {'sports_cave_current_user': {**USER, 'page_permissions': []}}
        with patch.object(page, 'st', ui):
            page._render_etsy_qa_override(fixture(), {}, '', 'fixture', '#SC3351')
        ui.button.assert_not_called()

    def test_database_roundtrip_and_refresh(self):
        saved = self.complete()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'dispatch.sqlite'
            columns = '''row_id TEXT PRIMARY KEY, shopify_order_id TEXT, shopify_order_name TEXT,
                shopify_line_item_id TEXT, shopify_order_number TEXT, customer_name TEXT,
                product_title TEXT, shopify_variant_title TEXT, edition_number INTEGER,
                sports_cave_frame TEXT, sports_cave_size TEXT, prodigi_product_name TEXT,
                prodigi_product_code TEXT, prodigi_frame_colour TEXT, prodigi_status TEXT,
                date_sent_to_prodigi TEXT, submitted_at TEXT, qa_confirmed INTEGER, qa_notes TEXT,
                notes TEXT, source TEXT, row_json TEXT, updated_at TEXT'''
            with closing(sqlite3.connect(path)) as conn:
                conn.execute('CREATE TABLE prodigi_dispatch_rows (' + columns + ')')
            with patch.object(backend, 'connect', side_effect=lambda: SQLiteConnection(path)), \
                 patch('order_refunds.assert_processing_allowed') as refund_guard:
                result = backend.upsert_prodigi_dispatch_rows([saved], ensure_schema_first=False)
                refund_guard.assert_called_once()
            self.assertEqual(1, result['upserted'])
            with closing(sqlite3.connect(path)) as conn:
                conn.row_factory = sqlite3.Row
                db_row = dict(conn.execute('SELECT * FROM prodigi_dispatch_rows').fetchone())
            refreshed = backend._prodigi_payload_from_db_row(db_row)
            refreshed = page.prodigi_tracker_row_from_order(refreshed, refreshed)
            self.assertEqual('Complete', page._prodigi_status_label(refreshed))
            self.assertEqual(saved['fulfilment_override_original_errors'], refreshed['fulfilment_override_original_errors'])
            self.assertEqual(USER['id'], refreshed['fulfilment_override_actor_id'])
            self.assertFalse(page._prodigi_submitted(refreshed))
            self.assertIsNone(db_row['submitted_at'])
            self.assertEqual('', db_row['date_sent_to_prodigi'])
            self.assertEqual(2, refreshed['edition_number'])
            self.assertIn(refreshed, page.prodigi_dispatch_rows_for_tab([refreshed], 'Last 7 Days'))


if __name__ == '__main__': unittest.main()
