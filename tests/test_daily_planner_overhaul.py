import json
from pathlib import Path
import unittest

import sports_cave_dashboard
import top_bar_api


ROOT = Path(__file__).resolve().parents[1]


class DailyPlannerOverhaulContractTests(unittest.TestCase):
    def test_home_reporting_and_toolbar_open_one_canonical_modal(self):
        app_source = (ROOT / "app.py").read_text(encoding="utf-8")
        planner_source = (ROOT / "daily_planner.py").read_text(encoding="utf-8")
        component_source = (
            ROOT / "components" / "sports_cave_top_bar" / "index.html"
        ).read_text(encoding="utf-8")

        self.assertIn('OPEN_STATE_KEY = "daily_planner_popup_open"', planner_source)
        self.assertEqual(1, planner_source.count('@st.dialog("Daily Planner", width="large")'))
        self.assertIn("render_daily_planner_overlays(current_os_user())", app_source)
        self.assertIn("daily_planner.open_daily_planner()", app_source)
        self.assertIn('url.searchParams.set("daily_planner", "open")', component_source)
        self.assertIn('id="sc-os-daily-planner"', component_source)
        self.assertIn('aria-label="Open Daily Planner"', component_source)

        reporting_child = app_source[
            app_source.index(f"key=f\"sidebar-child::{{os_accounts.DAILY_PLANNER_ROUTE}}\"") :
            app_source.index("if reporting_weekly_allowed:")
        ]
        self.assertIn("daily_planner.open_daily_planner()", reporting_child)
        self.assertNotIn("set_current_page(", reporting_child)

    def test_timer_migration_is_additive_persistent_and_scoped(self):
        migration = (ROOT / "migrations" / "20260815_daily_execution_task_timers.sql").read_text(
            encoding="utf-8"
        )
        backend_source = (ROOT / "supabase_backend.py").read_text(encoding="utf-8")

        self.assertIn("CREATE TABLE IF NOT EXISTS daily_execution_task_timers", migration)
        self.assertIn("sheet_id UUID NOT NULL REFERENCES daily_execution_sheets(id) ON DELETE CASCADE", migration)
        self.assertIn("deadline_at TIMESTAMPTZ", migration)
        self.assertIn("halfway_notified_at TIMESTAMPTZ", migration)
        self.assertIn("expiry_notified_at TIMESTAMPTZ", migration)
        self.assertIn("outcome_required BOOLEAN NOT NULL DEFAULT false", migration)
        self.assertIn("CREATE UNIQUE INDEX IF NOT EXISTS idx_daily_task_timers_task", migration)
        self.assertIn("idx_daily_task_timers_one_active", migration)
        self.assertIn("FOR UPDATE", backend_source)
        self.assertIn("ON CONFLICT (sheet_id, task_type, task_index)", backend_source)
        self.assertIn("started_at=now()", backend_source)
        self.assertNotIn("remaining_seconds = remaining_seconds -", backend_source)

    def test_timer_events_fire_once_and_outcomes_are_idempotent(self):
        backend_source = (ROOT / "supabase_backend.py").read_text(encoding="utf-8")
        planner_source = (ROOT / "daily_planner.py").read_text(encoding="utf-8")

        self.assertIn("halfway_notified_at IS NULL", backend_source)
        self.assertIn("expiry_notified_at IS NULL", backend_source)
        self.assertIn("outcome_required=true", backend_source)
        self.assertIn("daily_planner_task_halfway", backend_source)
        self.assertIn("daily_planner_task_time_up", backend_source)
        self.assertIn("elapsed = allocated", backend_source)
        self.assertIn("if timer.get(\"outcome\"):", backend_source)
        self.assertIn("DAILY_TIMER_OUTCOME_COMPLETED", backend_source)
        self.assertIn("DAILY_TIMER_OUTCOME_DID_NOT_FINISH", backend_source)
        self.assertIn('task["status"] = "couldnt_finish"', backend_source)
        self.assertIn("Time’s up — did you complete this task?", planner_source)
        self.assertIn('"Completed"', planner_source)
        self.assertIn('"Half complete / Did not finish"', planner_source)
        self.assertIn("daily_planner_alarm_played::", planner_source)
        self.assertIn("Daily Planner sound was blocked by the browser.", planner_source)

    def test_reporting_uses_sydney_periods_and_scrollable_history(self):
        source = (ROOT / "reporting_page.py").read_text(encoding="utf-8")

        self.assertIn("timezone_name = os_accounts.timezone_for_user(user) or daily_activity_reporting.REPORT_TIMEZONE", source)
        self.assertIn("local_today - timedelta(days=6)", source)
        self.assertIn("local_today - timedelta(days=29)", source)
        self.assertIn("end_value < start_value", source)
        self.assertIn("sports_cave_dashboard.list_daily_execution_history", source)
        self.assertIn("st.dataframe(", source)
        self.assertIn("height=min(520", source)
        self.assertIn("row_height=28", source)
        self.assertIn('"Daily Execution History"', source)
        self.assertIn('"Recent Operational Activity"', source)

    def test_notification_bell_allowlist_excludes_alerts_and_generic_activity(self):
        claims = {
            "sub": "admin-1",
            "can_view_activity": True,
            "can_view_all_activity": True,
        }
        rows = [
            {
                "event_type": "daily_planner_task_halfway",
                "created_at": "2026-08-15T01:00:00Z",
                "source": "Daily Planner",
                "new_value": {
                    "message": "Halfway through: Pack order - 05:00 left",
                    "metadata": {"actor_id": "admin-1", "task": "Pack order"},
                },
            },
            {
                "event_type": "activity",
                "created_at": "2026-08-15T01:01:00Z",
                "source": "Sports Cave",
                "new_value": {"message": "Activity"},
            },
            {
                "event_type": "metafield_mirror_completed",
                "created_at": "2026-08-15T01:02:00Z",
                "source": "Connector",
                "new_value": {"message": "Metafield mirror completed"},
            },
        ]

        notifications = top_bar_api.build_notifications(
            claims,
            activity_rows=rows,
            alerts=[{"label": "Afterpay Day soon"}],
        )
        serialised = json.dumps(notifications)

        self.assertEqual(1, len(notifications))
        self.assertIn("Halfway through: Pack order", notifications[0]["title"])
        self.assertNotIn("Afterpay Day soon", serialised)
        self.assertNotIn("Metafield", serialised)
        self.assertNotIn('"Activity"', serialised)

    def test_duration_and_history_helpers_reuse_existing_daily_execution_rows(self):
        sheet = {
            "id": "sheet-1",
            "sheet_date": "2026-08-15",
            "user_name": "Nathan",
            "top_tasks": [
                {"task": "Pack order", "why": "Customer", "time_blocked": "45 minutes"},
            ],
            "additional_items": [
                {"task": "Upload product", "details": "Poster", "time_blocked": "9:00am-10:30am"},
            ],
        }
        rows = sports_cave_dashboard.daily_execution_task_rows(sheet, [])

        self.assertEqual(45 * 60, sports_cave_dashboard.parse_daily_task_duration_seconds("45 minutes"))
        self.assertEqual(90 * 60, sports_cave_dashboard.parse_daily_task_duration_seconds("9:00am-10:30am"))
        self.assertEqual(["top", "additional"], [row["task_type"] for row in rows])
        self.assertEqual(["Pack order", "Upload product"], [row["task"] for row in rows])
        self.assertEqual(["MIP", "Other"], [row["category"] for row in rows])


if __name__ == "__main__":
    unittest.main()
