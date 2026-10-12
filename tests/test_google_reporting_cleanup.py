import unittest
from scripts.google_reporting_cleanup import CANDIDATES, prepare_sql

class CleanupPlanTests(unittest.TestCase):
    def test_plan_is_read_only_and_deletion_statements_are_inert(self):
        sql = prepare_sql()
        executable = '\n'.join(line for line in sql.splitlines() if not line.lstrip().startswith('--'))
        self.assertIn('BEGIN READ ONLY;', executable)
        self.assertIn('ROLLBACK;', executable)
        for word in ('DELETE', 'DROP', 'TRUNCATE', 'COMMIT', 'CASCADE'):
            self.assertNotIn(word, executable)
        self.assertIn("source_date >= DATE '2025-06-12'", sql)

    def test_protected_tables_cannot_enter_allowlist(self):
        for table in ('shopify_orders', 'seo_reporting_opportunities', 'seo_reporting_snapshot_runs', 'seo_reporting_repair_jobs', 'seo_ga4_transactions', 'crm_contacts', 'seo_google_connections'):
            with self.assertRaises(ValueError):
                prepare_sql((table,))
        self.assertEqual(len(CANDIDATES), 10)
