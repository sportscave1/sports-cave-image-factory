import inspect
from pathlib import Path
import unittest

import reporting_page
import reporting_store


ROOT = Path(__file__).resolve().parents[1]


class ReportingPageContractTests(unittest.TestCase):
    def test_page_contains_required_lightweight_sections(self):
        source = (ROOT / "reporting_page.py").read_text(encoding="utf-8")

        for section in (
            'st.subheader("Today")',
            'st.subheader("Staff Summary")',
            'st.subheader("Daily Execution History")',
            'st.subheader("Sent Reports")',
            'st.subheader("Delivery Health")',
            'st.subheader("Test Email")',
        ):
            self.assertIn(section, source)
        self.assertIn("ARCHIVE_PAGE_SIZE = 15", source)
        self.assertIn('key="reporting-staff-summary-table"', source)

    def test_archive_detail_and_csv_are_loaded_through_authorized_helpers(self):
        source = inspect.getsource(reporting_page._render_sent_reports)

        self.assertIn("reporting_store.list_archives(", source)
        self.assertIn("reporting_store.get_archive(user, selected_id)", source)
        self.assertIn("reporting_store.archive_csv(user, selected_id)", source)
        self.assertIn("st.download_button(", source)
        self.assertIn("components.html(", source)

    def test_delivery_health_uses_public_config_without_api_key_value(self):
        source = inspect.getsource(reporting_page._render_delivery_health)

        self.assertIn("mail_config.public_status()", source)
        self.assertNotIn(".api_key", source)
        self.assertNotIn("RESEND_API_KEY", source)

    def test_test_button_has_session_lock_and_stable_request_nonce(self):
        source = inspect.getsource(reporting_page._render_test_email)

        self.assertIn('"reporting-test-in-progress"', source)
        self.assertIn('"reporting-test-nonce"', source)
        self.assertIn("uuid.uuid4().hex", source)
        self.assertIn("send_test_daily_digest(", source)
        self.assertNotIn(
            'st.session_state["reporting-test-nonce"] = uuid.uuid4().hex',
            source,
        )

    def test_reporting_store_page_size_is_bounded(self):
        self.assertEqual(reporting_store._safe_limit(5000), reporting_store.MAX_PAGE_SIZE)
        self.assertEqual(reporting_store._safe_limit(0), 1)

    def test_reporting_hosts_period_filters_history_activity_and_weekly_review(self):
        source = (ROOT / "reporting_page.py").read_text(encoding="utf-8")

        for label in ("Today", "Last 7 days", "Last 30 days", "Custom"):
            self.assertIn(label, source)
        self.assertIn("Australia/Sydney", source)
        self.assertIn("sports_cave_dashboard.list_daily_execution_history", source)
        self.assertIn("Staff Weekly Activity", source)
        self.assertIn("Human Work Records", source)
        self.assertIn("def render_weekly_review_page", source)


if __name__ == "__main__":
    unittest.main()
