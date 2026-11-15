"""Offline cleanup guard tests. No connection or SQL execution."""
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from scripts import prepare_google_cleanup_batches as plan


def entry(table='seo_gsc_property_totals_v2', **changes):
    row = dict(workspace_key='sports-cave', property_id='fixture',
               source_date='2026-10-01', search_type='web', data_state='final', clicks=3)
    row.update(changes)
    text = json.dumps(row, sort_keys=True)
    return dict(table=table, row_text=text, row_sha256=plan.digest(text.encode()))


class CleanupBatchTests(unittest.TestCase):
    def test_exact_keys_hash_and_rollback(self):
        sql = plan.batch_sql('seo_gsc_property_totals_v2', [entry()])
        self.assertTrue(all(line.startswith('-- ') for line in sql.splitlines()))
        for key in plan.BASE_KEY:
            self.assertIn(f't.{key}=k.{key}', sql)
        for marker in ('sha256', 'affected <> 1', 'RAISE EXCEPTION', 'ROLLBACK;', "DATE '2025-06-12'"):
            self.assertIn(marker, sql)
        for forbidden in ('COMMIT;', 'TRUNCATE', 'CASCADE', 'DROP '):
            self.assertNotIn(forbidden, sql)

    def test_old_history_is_retained_not_deleted(self):
        old = entry(source_date='2025-06-11')
        self.assertTrue(plan.validate_entry(old)[2])
        with self.assertRaises(ValueError):
            plan.batch_sql(old['table'], [old])
        self.assertFalse(plan.validate_entry(entry(source_date='2025-06-12'))[2])

    def test_rejects_wrong_workspace_table_and_checksum(self):
        bad = entry(); bad['row_sha256'] = '0'*64
        for item in (bad, entry(workspace_key='another'), entry('crm_customers'),
                     entry('seo_reporting_daily_metrics')):
            with self.subTest(item=item['table']), self.assertRaises(ValueError):
                plan.validate_entry(item)

    def test_duplicate_and_oversized_batches_rejected(self):
        for rows in ([], [entry(), entry()], [entry()] * 501):
            with self.assertRaises(ValueError):
                plan.batch_sql('seo_gsc_property_totals_v2', rows)

    def test_no_package_without_restore_evidence_or_exact_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backup, receipt, output = root/'backup.jsonl', root/'receipt.json', root/'plan'
            backup.write_text(json.dumps(entry())+'\n')
            receipt.write_text('{}')
            with self.assertRaisesRegex(ValueError, 'restore'):
                plan.prepare(backup, receipt, output)
            sha = plan.digest(backup.read_bytes())
            receipt.write_text(json.dumps(dict(project=plan.PROJECT, backup_sha256=sha,
                restored_export_sha256=sha, isolated=True, target_project='local-fixture',
                restored_at='2026-10-12', retained_rows=268)))
            with self.assertRaisesRegex(ValueError, 'counts'):
                plan.prepare(backup, receipt, output)
            self.assertFalse(output.exists())

    def test_sql_literal_and_dollar_delimiter_are_escaped(self):
        sql = plan.batch_sql('seo_gsc_property_totals_v2', [entry(property_id="a'$cleanup$\\b")])
        self.assertIn('DO $cleanupx$', sql)
        self.assertIn("a''$cleanup$", sql)
        self.assertIn('standard_conforming_strings = on', sql)

    def test_valid_fixture_produces_exact_key_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backup, receipt, output = root/'backup.jsonl', root/'receipt.json', root/'plan'
            rows = [entry()] + [entry(property_id=str(i), source_date='2025-06-11') for i in range(268)]
            backup.write_text(''.join(json.dumps(row)+'\n' for row in rows))
            sha = plan.digest(backup.read_bytes())
            receipt.write_text(json.dumps(dict(project=plan.PROJECT, backup_sha256=sha,
                restored_export_sha256=sha, isolated=True, target_project='local-fixture',
                restored_at='2026-10-12', retained_rows=268)))
            with patch.object(plan, 'EXPECTED', {'seo_gsc_property_totals_v2': 1}):
                result = plan.prepare(backup, receipt, output)
            self.assertFalse(result['approved'])
            self.assertFalse(result['executed'])
            self.assertEqual(result['batches'][0]['keys'][0]['property_id'], 'fixture')
            self.assertEqual(len(result['batches']), 1)
            self.assertEqual(result['retained_rows'], 268)

    def test_export_is_read_only_and_includes_historical_backup(self):
        sql = plan.export_sql()
        self.assertIn('REPEATABLE READ READ ONLY', sql)
        self.assertIn('ROLLBACK;', sql)
        self.assertNotIn('DELETE', sql)
        self.assertNotIn('source_date >=', sql)
        self.assertEqual(len(plan.KEYS), 6)
        self.assertEqual(sum(plan.EXPECTED.values()), 286509)


if __name__ == '__main__':
    unittest.main()
