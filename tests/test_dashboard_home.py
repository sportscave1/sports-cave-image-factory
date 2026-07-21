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
        self.activity_calls = []
        self.task_status_calls = []
        self.edition_products = []
        self.edition_product_calls = []

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
        self._activity_row("task_added", f"Task added: {title}")
        return task

    def complete_dashboard_task(self, task_id, *, completed_by="", metadata=None):
        for task in self.tasks:
            if task["id"] == task_id and task["status"] == "open":
                task["status"] = "complete"
                task["completed_at"] = "2026-07-21T01:00:00+00:00"
                self._activity_row("task_completed", f"Task completed: {task['title']}")
                return task
        return None

    def list_dashboard_tasks(self, status="open"):
        self.task_status_calls.append(status)
        if status == "all":
            return list(self.tasks)
        return [task for task in self.tasks if task.get("status") == status]

    def list_activity_logs(self, *, start_at=None, end_at=None, limit=200):
        self.activity_calls.append({"start_at": start_at, "end_at": end_at, "limit": limit})
        return self.activity_rows[:limit]

    def list_dashboard_edition_products(self, *, limit=1000):
        self.edition_product_calls.append(limit)
        return self.edition_products[:limit]


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
    def setUp(self):
        sports_cave_dashboard.clear_dashboard_caches()
        sports_cave_dashboard.clear_calendar_cache()

    def tearDown(self):
        sports_cave_dashboard.clear_dashboard_caches()
        sports_cave_dashboard.clear_calendar_cache()

    def test_task_add_persists_to_supabase_backend(self):
        backend = FakeDashboardBackend()

        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=backend):
            task = sports_cave_dashboard.add_task("Refresh NFL collection", "Collections to update")
            state = sports_cave_dashboard.load_dashboard_state(include_activity=False)

        self.assertEqual(task["text"], "Refresh NFL collection")
        self.assertEqual(state["tasks"][0]["text"], "Refresh NFL collection")
        self.assertEqual(backend.activity_rows[0]["reason"], "Task added: Refresh NFL collection")

    def test_dashboard_task_list_loads_open_tasks_only(self):
        backend = FakeDashboardBackend()
        backend.tasks = [
            {"id": "open-1", "title": "Open task", "section": "Collections to update", "status": "open"},
            {"id": "done-1", "title": "Done task", "section": "Collections to update", "status": "complete"},
        ]

        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=backend):
            state = sports_cave_dashboard.load_dashboard_state(include_activity=False)

        self.assertEqual([task["text"] for task in state["tasks"]], ["Open task"])
        self.assertEqual(backend.task_status_calls, ["open"])
        self.assertEqual(backend.activity_calls, [])

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
        self.assertEqual(state["activity_log"][0]["message"], "Task completed: Refresh NFL collection")
        self.assertEqual(state["activity_log"][1]["message"], "Task added: Refresh NFL collection")

    def test_task_cache_is_cleared_after_add_and_complete(self):
        backend = FakeDashboardBackend()

        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=backend):
            self.assertEqual(sports_cave_dashboard.list_tasks(), [])
            self.assertEqual(sports_cave_dashboard.list_tasks(), [])
            task = sports_cave_dashboard.add_task("Refresh NFL collection", "Collections to update")
            self.assertEqual([item["text"] for item in sports_cave_dashboard.list_tasks()], ["Refresh NFL collection"])
            sports_cave_dashboard.complete_task(task["id"])
            self.assertEqual(sports_cave_dashboard.list_tasks(), [])

        self.assertEqual(len(backend.task_status_calls), 3)

    def test_activity_log_queries_use_view_date_bounds_and_limits(self):
        backend = FakeDashboardBackend()
        now = datetime(2026, 7, 21, 10, 30, tzinfo=timezone.utc)

        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=backend):
            sports_cave_dashboard.list_activity_entries(sports_cave_dashboard.ACTIVITY_VIEW_TODAY, now)
            sports_cave_dashboard.list_activity_entries(sports_cave_dashboard.ACTIVITY_VIEW_LAST_7_DAYS, now)
            sports_cave_dashboard.list_activity_entries(sports_cave_dashboard.ACTIVITY_VIEW_MONTH, now)
            sports_cave_dashboard.list_activity_entries(sports_cave_dashboard.ACTIVITY_VIEW_ALL_TIME, now)

        today_call, week_call, month_call, all_time_call = backend.activity_calls
        self.assertEqual(today_call["limit"], 50)
        self.assertEqual(week_call["limit"], 100)
        self.assertEqual(month_call["limit"], 150)
        self.assertEqual(all_time_call["limit"], 200)
        self.assertEqual(today_call["start_at"], datetime(2026, 7, 21, tzinfo=timezone.utc))
        self.assertEqual(today_call["end_at"], datetime(2026, 7, 22, tzinfo=timezone.utc))
        self.assertEqual(week_call["start_at"], datetime(2026, 7, 15, tzinfo=timezone.utc))
        self.assertEqual(week_call["end_at"], datetime(2026, 7, 22, tzinfo=timezone.utc))
        self.assertEqual(month_call["start_at"], datetime(2026, 7, 1, tzinfo=timezone.utc))
        self.assertEqual(month_call["end_at"], datetime(2026, 8, 1, tzinfo=timezone.utc))
        self.assertIsNone(all_time_call["start_at"])
        self.assertIsNone(all_time_call["end_at"])

    def test_activity_log_cache_is_keyed_by_filter(self):
        backend = FakeDashboardBackend()
        now = datetime(2026, 7, 21, 10, 30, tzinfo=timezone.utc)

        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=backend):
            sports_cave_dashboard.list_activity_entries(sports_cave_dashboard.ACTIVITY_VIEW_TODAY, now)
            sports_cave_dashboard.list_activity_entries(sports_cave_dashboard.ACTIVITY_VIEW_TODAY, now)
            sports_cave_dashboard.list_activity_entries(sports_cave_dashboard.ACTIVITY_VIEW_LAST_7_DAYS, now)

        self.assertEqual(len(backend.activity_calls), 2)

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

    def test_new_task_categories_are_available(self):
        expected = {
            "Collections to update",
            "New designs to complete",
            "Mockups for existing product",
            "Product uploaded",
            "Design updated",
            "New design made",
            "New product with mockups uploaded",
        }

        self.assertTrue(expected.issubset(set(sports_cave_dashboard.TASK_GROUPS)))
        self.assertEqual(
            sports_cave_dashboard.normalize_task_category("New product with mockups uploaded"),
            "New product with mockups uploaded",
        )

    def test_design_ideas_prompt_uses_calendar_and_existing_products(self):
        now = datetime(2026, 7, 21, 10, 30, tzinfo=timezone.utc)
        events = [
            {
                "end_date": "2026-07-26",
                "id": "f1-hungary",
                "importance": 5,
                "regions": ["Australia", "UK", "USA"],
                "sport": "Motorsport",
                "start_date": "2026-07-24",
                "title": "Formula 1 Hungarian Grand Prix 2026",
            }
        ]
        products = [
            {
                "title": "Six Laps Ahead",
                "handle": "six-laps-ahead",
                "category": "Motorsport",
                "status": "Active",
            }
        ]

        prompt = sports_cave_dashboard.build_design_ideas_prompt(now, events, products)

        self.assertIn("Formula 1 Hungarian Grand Prix 2026", prompt)
        self.assertIn("Six Laps Ahead", prompt)
        self.assertIn("six-laps-ahead", prompt)
        self.assertIn("do-not-duplicate", prompt)
        self.assertIn("Do not recommend an existing product", prompt)
        self.assertIn("Recommend exactly 5 ideas", prompt)
        self.assertIn("Golf", prompt)
        self.assertIn("Suggested task wording", prompt)

    def test_design_ideas_prompt_fetches_lightweight_edition_products(self):
        backend = FakeDashboardBackend()
        backend.edition_products = [
            {"title": "The Final Lap", "handle": "the-final-lap", "category": "Motorsport", "status": "Active"}
        ]
        now = datetime(2026, 7, 21, 10, 30, tzinfo=timezone.utc)

        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=backend):
            prompt = sports_cave_dashboard.build_todays_design_ideas_prompt(now, events=[])

        self.assertEqual(backend.edition_product_calls, [1000])
        self.assertIn("The Final Lap", prompt)
        self.assertIn("the-final-lap", prompt)

    def test_activity_log_display_hides_developer_wording(self):
        rows = [
            {
                "event_type": "edition_product_updated",
                "reason": "Edition Ops Shopify metafield mirror",
                "source": "Edition ops",
                "created_at": "2026-07-21T00:00:00+00:00",
            },
            {
                "event_type": "order_allocated",
                "reason": "Auto allocation during Shopify order sync.",
                "source": "Orders",
                "created_at": "2026-07-21T00:00:00+00:00",
            },
        ]

        messages = [sports_cave_dashboard.activity_from_audit_row(row)["message"] for row in rows]
        combined = " ".join(messages).casefold()

        self.assertEqual(messages, ["Edition updated", "Order updated"])
        for term in ("metafield", "sync", "allocation", "supabase", "backend", "payload", "mirror"):
            self.assertNotIn(term, combined)

    def test_fulfilled_order_certificate_activity_display(self):
        entry = sports_cave_dashboard.activity_from_audit_row(
            {
                "event_type": "order_fulfilled_certificate_generated",
                "new_value": {
                    "message": "Order #SC1234 fulfilled + certificate generated",
                    "page": "Prodigi",
                    "action_type": "order_fulfilled_certificate_generated",
                    "metadata": {"order": "#SC1234"},
                },
                "source": "Prodigi",
                "created_at": "2026-07-21T00:00:00+00:00",
            }
        )

        self.assertEqual(entry["message"], "Order #SC1234 fulfilled + certificate generated")


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
            "ensure_schema(",
        ]
        for text in forbidden:
            with self.subTest(text=text):
                self.assertNotIn(text, dashboard_source)

    def test_home_product_prompt_helper_does_not_run_full_schema(self):
        source = (ROOT / "supabase_backend.py").read_text(encoding="utf-8")
        helper_source = source[
            source.index("def list_dashboard_edition_products") : source.index("\n\ndef create_dashboard_task")
        ]

        self.assertNotIn("ensure_schema(", helper_source)
        self.assertIn("SET LOCAL statement_timeout", helper_source)

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
