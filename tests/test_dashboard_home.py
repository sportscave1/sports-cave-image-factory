from datetime import date
from pathlib import Path
import tempfile
import unittest

import sc_auth
import sports_cave_dashboard


ROOT = Path(__file__).resolve().parents[1]


class SportsCaveAuthTests(unittest.TestCase):
    def test_signed_token_validates_until_expiry(self):
        token = sc_auth.create_auth_token(password="secret", now=1000, days=30)

        self.assertTrue(sc_auth.validate_auth_token(token, password="secret", now=1001)[0])
        self.assertEqual(
            sc_auth.validate_auth_token(token, password="wrong", now=1001),
            (False, "bad-signature"),
        )
        self.assertEqual(
            sc_auth.validate_auth_token(token, password="secret", now=1000 + sc_auth.auth_cookie_max_age()),
            (False, "expired"),
        )

    def test_password_compare_uses_exact_value(self):
        self.assertTrue(sc_auth.password_matches("Sportscaveshop26!"))
        self.assertFalse(sc_auth.password_matches("sportscaveshop26!"))


class SportsCaveDashboardStateTests(unittest.TestCase):
    def test_task_complete_removes_active_task_and_adds_log_entry(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "dashboard_state.json"
            task = sports_cave_dashboard.add_task(
                "Refresh AFL finals collection",
                "Collections to update",
                path=state_path,
                created_at="2026-07-21T00:00:00+00:00",
            )

            created_state = sports_cave_dashboard.load_dashboard_state(state_path)
            self.assertEqual(len(created_state["tasks"]), 1)
            self.assertEqual(created_state["activity_log"][0]["message"], "Added task: Refresh AFL finals collection")

            completed = sports_cave_dashboard.complete_task(
                task["id"],
                path=state_path,
                completed_at="2026-07-21T01:00:00+00:00",
            )

            final_state = sports_cave_dashboard.load_dashboard_state(state_path)
            self.assertEqual(completed["text"], "Refresh AFL finals collection")
            self.assertEqual(final_state["tasks"], [])
            self.assertEqual(
                final_state["activity_log"][0]["message"],
                "Completed task: Refresh AFL finals collection",
            )
            self.assertEqual(
                final_state["activity_log"][1]["message"],
                "Added task: Refresh AFL finals collection",
            )


class SportsCaveCalendarTests(unittest.TestCase):
    def test_alert_logic_prefers_active_and_upcoming_major_events(self):
        today = date(2026, 7, 21)
        events = [
            {
                "alert_label": "AFL season active",
                "end_date": "2026-08-30",
                "id": "afl",
                "importance": 5,
                "regions": ["Australia"],
                "sport": "AFL",
                "start_date": "2026-03-05",
                "title": "AFL Premiership season",
            },
            {
                "alert_label": "Bathurst week soon",
                "end_date": "2026-10-11",
                "id": "bathurst",
                "importance": 5,
                "regions": ["Australia"],
                "sport": "Motorsport",
                "start_date": "2026-10-08",
                "title": "Bathurst 1000",
            },
            {
                "alert_label": "Old event",
                "end_date": "2026-07-12",
                "id": "old",
                "importance": 5,
                "regions": ["UK"],
                "sport": "Tennis",
                "start_date": "2026-06-29",
                "title": "Wimbledon",
            },
        ]

        alerts = sports_cave_dashboard.build_active_alerts(events, today, upcoming_days=90)
        labels = [alert["label"] for alert in alerts]

        self.assertIn("AFL season active", labels)
        self.assertIn("Bathurst week soon", labels)
        self.assertNotIn("Old event", labels)
        self.assertEqual(alerts[0]["label"], "AFL season active")

    def test_calendar_filter_returns_active_and_near_upcoming_only(self):
        today = date(2026, 7, 21)
        events = [
            {
                "end_date": "2026-08-30",
                "id": "active",
                "importance": 4,
                "regions": ["Australia"],
                "sport": "AFL",
                "start_date": "2026-03-05",
                "title": "AFL season",
            },
            {
                "end_date": "2026-08-23",
                "id": "soon",
                "importance": 4,
                "regions": ["USA"],
                "sport": "Tennis",
                "start_date": "2026-08-23",
                "title": "US Open",
            },
            {
                "end_date": "2027-02-14",
                "id": "later",
                "importance": 5,
                "regions": ["USA"],
                "sport": "NFL",
                "start_date": "2027-02-14",
                "title": "Super Bowl",
            },
        ]

        filtered = sports_cave_dashboard.filter_calendar_events(
            events,
            today,
            status="Active/upcoming",
            upcoming_days=60,
        )
        self.assertEqual([event["id"] for event in filtered], ["active", "soon"])


class DashboardRenderContractTests(unittest.TestCase):
    def test_dashboard_render_path_has_no_supabase_or_shopify_fetch(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        dashboard_source = source[
            source.index("def get_browser_timezone") : source.index("\n\ndef page_uses_local_database")
        ]

        forbidden = [
            "supabase_backend",
            "shopify_sync",
            "get_shopify_sync(",
            "get_orders_page(",
            "get_edition_ops(",
            "get_os_pages(",
            "get_ads_page(",
        ]
        for text in forbidden:
            with self.subTest(text=text):
                self.assertNotIn(text, dashboard_source)


if __name__ == "__main__":
    unittest.main()
