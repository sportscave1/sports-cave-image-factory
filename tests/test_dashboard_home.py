from datetime import date, datetime, timezone
from pathlib import Path
import unittest
from unittest.mock import patch

import sc_auth
import sports_cave_dashboard


ROOT = Path(__file__).resolve().parents[1]


class FakeDashboardBackend:
    def __init__(self):
        self.tasks = []
        self.activity_rows = []

    def _activity_row(self, event_type, message):
        row = {
            "id": len(self.activity_rows) + 1,
            "event_type": event_type,
            "entity_type": "dashboard_task",
            "entity_id": self.tasks[-1]["id"] if self.tasks else "",
            "new_value": {
                "message": message,
                "page": "Dashboard",
                "action_type": event_type,
                "metadata": {},
            },
            "reason": message,
            "source": "Dashboard",
            "created_at": f"2026-07-21T0{len(self.activity_rows)}:00:00+00:00",
        }
        self.activity_rows.insert(0, row)

    def create_dashboard_task(self, title, section, *, metadata=None):
        task = {
            "id": f"task-{len(self.tasks) + 1}",
            "title": title,
            "section": section,
            "status": "open",
            "created_at": "2026-07-21T00:00:00+00:00",
            "metadata": metadata or {},
        }
        self.tasks.append(task)
        self._activity_row("task_added", f"Added task: {title}")
        return task

    def complete_dashboard_task(self, task_id, *, completed_by="", metadata=None):
        for task in self.tasks:
            if task["id"] == task_id and task["status"] == "open":
                task["status"] = "complete"
                task["completed_at"] = "2026-07-21T01:00:00+00:00"
                self._activity_row("task_completed", f"Completed task: {task['title']}")
                return task
        return None

    def list_dashboard_tasks(self, status="open"):
        if status == "all":
            return list(self.tasks)
        return [task for task in self.tasks if task.get("status") == status]

    def list_activity_logs(self, *, start_at=None, end_at=None, limit=200):
        return self.activity_rows[:limit]


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
    def test_task_add_persists_to_supabase_backend(self):
        backend = FakeDashboardBackend()

        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=backend):
            task = sports_cave_dashboard.add_task("Refresh NFL collection", "Collections to update")
            state = sports_cave_dashboard.load_dashboard_state(include_activity=False)

        self.assertEqual(task["text"], "Refresh NFL collection")
        self.assertEqual(state["tasks"][0]["text"], "Refresh NFL collection")
        self.assertEqual(backend.activity_rows[0]["reason"], "Added task: Refresh NFL collection")

    def test_task_complete_marks_complete_and_writes_activity_log(self):
        backend = FakeDashboardBackend()

        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=backend):
            task = sports_cave_dashboard.add_task("Refresh NFL collection", "Collections to update")
            completed = sports_cave_dashboard.complete_task(task["id"])
            state = sports_cave_dashboard.load_dashboard_state(
                sports_cave_dashboard.ACTIVITY_VIEW_ALL_TIME,
                datetime(2026, 7, 21, tzinfo=timezone.utc),
            )

        self.assertEqual(completed["status"], "complete")
        self.assertEqual(state["tasks"], [])
        self.assertEqual(state["activity_log"][0]["message"], "Completed task: Refresh NFL collection")
        self.assertEqual(state["activity_log"][1]["message"], "Added task: Refresh NFL collection")

    def test_activity_log_filters_today_last_7_days_month_and_all_time(self):
        now = datetime(2026, 7, 21, 10, 30, tzinfo=timezone.utc)
        entries = [
            {"message": "Today", "created_at": "2026-07-21T00:05:00+00:00"},
            {"message": "Seven day edge", "created_at": "2026-07-15T12:00:00+00:00"},
            {"message": "This month", "created_at": "2026-07-01T12:00:00+00:00"},
            {"message": "Older", "created_at": "2026-06-30T23:59:00+00:00"},
        ]

        today = sports_cave_dashboard.filter_activity_entries(entries, sports_cave_dashboard.ACTIVITY_VIEW_TODAY, now)
        last_7_days = sports_cave_dashboard.filter_activity_entries(entries, sports_cave_dashboard.ACTIVITY_VIEW_LAST_7_DAYS, now)
        month = sports_cave_dashboard.filter_activity_entries(entries, sports_cave_dashboard.ACTIVITY_VIEW_MONTH, now)
        all_time = sports_cave_dashboard.filter_activity_entries(entries, sports_cave_dashboard.ACTIVITY_VIEW_ALL_TIME, now)

        self.assertEqual([entry["message"] for entry in today], ["Today"])
        self.assertEqual([entry["message"] for entry in last_7_days], ["Today", "Seven day edge"])
        self.assertEqual([entry["message"] for entry in month], ["Today", "Seven day edge", "This month"])
        self.assertEqual([entry["message"] for entry in all_time], ["Today", "Seven day edge", "This month", "Older"])


class SportsCaveCalendarTests(unittest.TestCase):
    def test_alert_logic_prefers_active_and_upcoming_major_events(self):
        today = date(2026, 7, 21)
        events = [
            {
                "alert_label": "MLB season active",
                "end_date": "2026-08-30",
                "id": "mlb",
                "importance": 5,
                "regions": ["USA", "Canada"],
                "sport": "MLB",
                "start_date": "2026-03-05",
                "title": "MLB season",
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

        self.assertIn("MLB season active", labels)
        self.assertIn("Bathurst week soon", labels)
        self.assertNotIn("Old event", labels)
        self.assertEqual(alerts[0]["label"], "MLB season active")

    def test_calendar_filter_returns_active_and_near_upcoming_only(self):
        today = date(2026, 7, 21)
        events = [
            {
                "end_date": "2026-08-30",
                "id": "active",
                "importance": 4,
                "regions": ["USA"],
                "sport": "MLB",
                "start_date": "2026-03-05",
                "title": "MLB season",
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

    def test_calendar_data_excludes_afl_nrl_and_includes_sales_golf(self):
        events = sports_cave_dashboard.load_calendar_events(ROOT / "data" / "sporting_calendar.json")
        sports = {event.get("sport") for event in events}
        titles = {event.get("title") for event in events}

        self.assertNotIn("AFL", sports)
        self.assertNotIn("NRL", sports)
        self.assertIn("Golf", sports)
        self.assertIn("Sales", sports)
        self.assertIn("Black Friday and Cyber Monday 2027", titles)


class DashboardRenderContractTests(unittest.TestCase):
    def test_dashboard_render_path_avoids_heavy_page_imports(self):
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

    def test_dashboard_no_longer_renders_manual_custom_calendar_ui(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        dashboard_source = source[
            source.index("def get_browser_timezone") : source.index("\n\ndef page_uses_local_database")
        ]

        self.assertNotIn("render_custom_calendar_form", dashboard_source)
        self.assertNotIn("dashboard-add-calendar-event", dashboard_source)
        self.assertNotIn("render_physical_calendar", dashboard_source)
        render_body = dashboard_source[
            dashboard_source.index("def render_lightweight_dashboard_page") :
        ]
        self.assertLess(
            render_body.index("render_sporting_calendar(events, today)"),
            render_body.index("render_activity_log(local_now)"),
        )


if __name__ == "__main__":
    unittest.main()
