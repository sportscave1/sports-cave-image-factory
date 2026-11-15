import inspect
from pathlib import Path
import unittest
from datetime import datetime, timedelta, timezone

import daily_activity_digest
import reporting_store
import run_migrations


ROOT = Path(__file__).resolve().parents[1]


class ReportingStoreTests(unittest.TestCase):
    def test_migration_contains_delivery_archive_uniqueness_and_rls(self):
        path = ROOT / "migrations" / reporting_store.REPORTING_MIGRATION
        sql = path.read_text(encoding="utf-8")

        self.assertTrue(run_migrations.safe_migration_sql(sql))
        self.assertIn("CREATE TABLE IF NOT EXISTS activity_report_deliveries", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS activity_report_archives", sql)
        self.assertIn("UNIQUE (idempotency_key)", sql)
        self.assertIn("idx_activity_report_one_production_per_day", sql)
        self.assertIn(
            "ON activity_report_deliveries (purpose, report_date)",
            sql,
        )
        self.assertIn("WHERE is_test IS FALSE", sql)
        self.assertIn("provider_message_id", sql)
        self.assertIn("attempt_count", sql)
        self.assertIn("sanitized_error", sql)
        self.assertIn("html_snapshot", sql)
        self.assertIn("text_snapshot", sql)
        self.assertIn("csv_content", sql)
        self.assertIn("ENABLE ROW LEVEL SECURITY", sql)

    def test_delivery_claim_decision_handles_sent_pending_stale_and_failures(self):
        now = datetime(2026, 7, 28, 8, 0, tzinfo=timezone.utc)
        stale_before = now - timedelta(minutes=20)

        self.assertEqual(
            reporting_store.delivery_claim_decision(
                {"status": "sent"},
                stale_before=stale_before,
            ),
            "already_sent",
        )
        self.assertEqual(
            reporting_store.delivery_claim_decision(
                {"status": "pending", "locked_at": now - timedelta(minutes=5)},
                stale_before=stale_before,
            ),
            "in_progress",
        )
        self.assertEqual(
            reporting_store.delivery_claim_decision(
                {"status": "pending", "locked_at": now - timedelta(hours=1)},
                stale_before=stale_before,
            ),
            "reclaim",
        )
        self.assertEqual(
            reporting_store.delivery_claim_decision(
                {"status": "failed", "metadata": {"retryable": True}},
                stale_before=stale_before,
            ),
            "reclaim",
        )
        self.assertEqual(
            reporting_store.delivery_claim_decision(
                {"status": "failed", "metadata": {"retryable": False}},
                stale_before=stale_before,
            ),
            "permanent_failure",
        )

    def test_retry_path_reuses_archived_payload_instead_of_new_snapshot(self):
        source = inspect.getsource(reporting_store.claim_delivery)
        delivery_source = inspect.getsource(
            daily_activity_digest._deliver_claimed_report
        )

        self.assertIn("_archive_by_delivery", source)
        self.assertIn("_message_from_archive(archive)", delivery_source)
        self.assertNotIn("snapshot", delivery_source)

    def test_archive_reads_are_bounded_and_server_authorized(self):
        source = inspect.getsource(reporting_store.list_archives)
        csv_source = inspect.getsource(reporting_store.archive_csv)

        self.assertIn("_require_reporting_access(user)", source)
        self.assertIn("LIMIT %s OFFSET %s", source)
        self.assertIn("_safe_limit(page_size)", source)
        self.assertIn("get_archive(user, archive_id)", csv_source)

    def test_production_digest_does_not_write_user_activity_log(self):
        production_source = inspect.getsource(
            daily_activity_digest.run_production_daily_digest
        )
        deliver_source = inspect.getsource(
            daily_activity_digest._deliver_claimed_report
        )

        self.assertNotIn("record_activity_log", production_source)
        self.assertIn("if is_test:", deliver_source)
        self.assertIn("_log_test_action", deliver_source)

    def test_render_cron_is_documented_but_not_added_as_a_service(self):
        docs = (ROOT / "docs" / "DAILY_STAFF_REPORTING.md").read_text(
            encoding="utf-8"
        )
        render = (ROOT / "render.yaml").read_text(encoding="utf-8")

        self.assertIn("Name: sports-cave-daily-activity-report", docs)
        self.assertIn("Schedule: 0 * * * *", docs)
        self.assertIn(
            "Command: python scripts/send_daily_activity_digest.py",
            docs,
        )
        self.assertNotIn("sports-cave-daily-activity-report", render)

    def test_environment_example_contains_placeholders_not_real_secrets(self):
        example = (ROOT / ".env.example").read_text(encoding="utf-8")

        self.assertIn("RESEND_API_KEY=replace_with_render_secret", example)
        self.assertIn("SPORTS_CAVE_REPORTING_OWNER_EMAIL=owner@example.com", example)
        self.assertNotIn("hello@sportscaveshop.com", example)


if __name__ == "__main__":
    unittest.main()
