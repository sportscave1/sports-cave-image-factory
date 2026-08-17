import asyncio
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

import daily_activity_reporting
import daily_planner
import run_migrations
import sports_cave_dashboard
import supabase_backend
import top_bar
import top_bar_api
import top_bar_security
from starlette.requests import Request


ROOT = Path(__file__).resolve().parents[1]
HOME_PLANNER_CLIENT = ROOT / "components" / "home_daily_planner" / "index.html"


def planner_api_request(path, token, *, method="GET", payload=None, query_string=b""):
    body = json.dumps(payload or {}).encode() if payload is not None else b""
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": query_string,
            "headers": [(b"authorization", f"Bearer {token}".encode())],
            "client": ("127.0.0.1", 1),
            "server": ("127.0.0.1", 8501),
        },
        receive,
    )


class DailyPlannerOverhaulContractTests(unittest.TestCase):
    def test_toolbar_and_reporting_open_one_reusable_native_window(self):
        app_source = (ROOT / "app.py").read_text(encoding="utf-8")
        planner_source = (ROOT / "daily_planner.py").read_text(encoding="utf-8")
        component_source = (
            ROOT / "components" / "sports_cave_top_bar" / "index.html"
        ).read_text(encoding="utf-8")

        self.assertNotIn("st.dialog", planner_source)
        self.assertNotIn("render_daily_planner_overlays", app_source)
        self.assertIn('PLANNER_WINDOW_PATH = "/daily-planner"', planner_source)
        self.assertIn('parentWindow.open(url.toString(), "sports_cave_daily_planner", features)', component_source)
        self.assertIn("parentWindow.SportsCaveDailyPlannerWindow", component_source)
        self.assertIn("if (existing && !existing.closed)", component_source)
        self.assertIn('width=950,height=760,resizable=yes,scrollbars=yes', component_source)
        self.assertIn('candidate.textContent.trim() === "Daily Planner"', component_source)
        self.assertIn("event.stopImmediatePropagation()", component_source)
        self.assertIn("Allow popups for Sports Cave OS.", component_source)
        self.assertIn("state.plannerWindow && !state.plannerWindow.closed", component_source)
        self.assertIn('id="sc-os-daily-planner"', component_source)
        self.assertIn('aria-label="Open Daily Planner"', component_source)

        reporting_child = app_source[
            app_source.index(f"key=f\"sidebar-child::{{os_accounts.DAILY_PLANNER_ROUTE}}\"") :
            app_source.index("if reporting_weekly_allowed:")
        ]
        self.assertNotIn("set_current_page(", reporting_child)
        self.assertIn('help="Open Daily Planner in a separate window"', reporting_child)

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
        planner_client = (ROOT / "components" / "daily_planner" / "index.html").read_text(
            encoding="utf-8"
        )

        self.assertIn("halfway_notified_at IS NULL", backend_source)
        self.assertIn("expiry_notified_at IS NULL", backend_source)
        self.assertIn("outcome_required=true", backend_source)
        self.assertIn("daily_planner_task_halfway", backend_source)
        self.assertIn("daily_planner_task_time_up", backend_source)
        self.assertIn("elapsed = allocated", backend_source)
        self.assertIn("if current_terminal:", backend_source)
        self.assertIn("DAILY_TIMER_OUTCOME_COMPLETED", backend_source)
        self.assertIn("DAILY_TIMER_OUTCOME_DID_NOT_FINISH", backend_source)
        self.assertIn('task_status = "couldnt_finish"', backend_source)
        self.assertIn(r"Time\u2019s up \u2014 did you complete this task?", planner_client)
        self.assertIn(">Completed</button>", planner_client)
        self.assertIn(">Half complete / Did not finish</button>", planner_client)
        self.assertIn("if (!state.soundEnabled || state.chimePlaying) return false", planner_client)
        self.assertIn("const playTimeUpChime", planner_client)
        self.assertNotIn("for (let pulse", planner_client)
        self.assertNotIn("5050", planner_client)
        self.assertIn("Sound is blocked. Allow audio for Sports Cave OS", planner_client)

    def test_home_surface_takes_alarm_only_when_planner_popup_is_closed(self):
        home_client = HOME_PLANNER_CLIENT.read_text(encoding="utf-8")
        planner_client = (ROOT / "components" / "daily_planner" / "index.html").read_text(
            encoding="utf-8"
        )
        top_bar_client = (ROOT / "components" / "sports_cave_top_bar" / "index.html").read_text(
            encoding="utf-8"
        )

        self.assertIn("const plannerPopupOpen", home_client)
        self.assertIn('if (kind === "time-up" && plannerPopupOpen()) return false;', home_client)
        self.assertIn('runClaimedSideEffect("time-up", timer, playTimeUpChime)', home_client)
        self.assertIn("state.completionAlertTimerId", home_client)
        self.assertIn("soundBlocked", home_client)
        self.assertIn("showOutcomeClaimed(timer)", planner_client)
        self.assertNotIn('runClaimedPlannerEffect("time-up"', top_bar_client)
        self.assertNotIn("chime:true", top_bar_client)

    def test_lightweight_client_restores_original_sheet_and_lazy_sections(self):
        planner_client = (ROOT / "components" / "daily_planner" / "index.html").read_text(
            encoding="utf-8"
        )

        for label in (
            "Three major execution tasks",
            "Details / outcome required",
            "Other tasks",
            "Main outcome for the day",
            "Appointment, deadline or fixed event",
            "Planning notes",
            "Complete Daily Review",
            "History",
            "Weekly Review",
        ):
            self.assertIn(label, planner_client)
        self.assertIn('if (state.tab === "planner") renderPlanner()', planner_client)
        self.assertIn("else if (state.tab === \"history\")", planner_client)
        self.assertIn("loadWeekly()", planner_client)
        self.assertIn("setInterval(updateTimerDisplays, 1000)", planner_client)
        self.assertNotIn("location.reload", planner_client)

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
        self.assertIn('"Staff Weekly Activity"', source)
        self.assertIn('"Human Work Records"', source)

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
            {
                "event_type": "design_task_completed",
                "created_at": "2026-08-15T01:03:00Z",
                "source": "Design Studio",
                "new_value": {
                    "message": "Design task completed: Cricket campaign artwork",
                    "action_type": "design_task_completed",
                    "metadata": {"actor_id": "admin-1"},
                },
            },
            {
                "event_type": "daily_planner_task_skipped",
                "created_at": "2026-08-15T01:04:00Z",
                "source": "Daily Planner",
                "new_value": {
                    "message": "Daily Planner task skipped: Optional filing",
                    "action_type": "daily_planner_task_skipped",
                    "metadata": {"actor_id": "admin-1"},
                },
            },
        ]

        notifications = top_bar_api.build_notifications(
            claims,
            activity_rows=rows,
            alerts=[{"label": "Afterpay Day soon"}],
        )
        serialised = json.dumps(notifications)

        self.assertEqual(2, len(notifications))
        self.assertTrue(any("Halfway through: Pack order" in row["title"] for row in notifications))
        self.assertTrue(any("Cricket campaign artwork" in row["title"] for row in notifications))
        self.assertNotIn("Afterpay Day soon", serialised)
        self.assertNotIn("Metafield", serialised)
        self.assertNotIn("Optional filing", serialised)
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

    def test_home_events_use_confirmed_dates_live_first_and_expire(self):
        events = [
            {"id": "expired", "title": "Expired sale", "type": "Sale", "start_date": "2026-08-01", "end_date": "2026-08-02", "importance": 5},
            {"id": "live-sport", "title": "Live final", "sport": "AFL", "type": "Finals", "start_date": "2026-08-14", "end_date": "2026-08-16", "importance": 5},
            {"id": "live-sale", "title": "Live sale", "type": "Sale", "start_date": "2026-08-15", "end_date": "2026-08-17", "importance": 4},
            *[
                {"id": f"future-{index}", "title": f"Future {index}", "sport": "Tennis", "type": "Major event", "start_date": f"2026-08-{18 + index:02d}", "end_date": f"2026-08-{18 + index:02d}", "importance": 4}
                for index in range(8)
            ],
        ]

        rows = sports_cave_dashboard.build_home_event_rows(events, date(2026, 8, 15))

        self.assertEqual(8, len(rows))
        self.assertEqual(["Live", "Live"], [row["status"] for row in rows[:2]])
        self.assertNotIn("Expired sale", [row["name"] for row in rows])
        self.assertTrue(all(row["start_date"] and row["end_date"] for row in rows))

    def test_home_weekly_work_is_role_scoped_deduplicated_and_uses_sydney_monday(self):
        now = datetime(2026, 8, 15, 11, 0, tzinfo=ZoneInfo("Australia/Sydney"))
        users = [
            {"id": "admin-1", "display_name": "Nathan", "username": "nathan", "role": "admin", "is_active": True},
            {"id": "worker-1", "display_name": "Reina", "username": "reina", "role": "worker", "is_active": True},
        ]
        sheets = [
            {"id": "sheet-a", "user_id": "admin-1", "user_name": "Nathan", "sheet_date": "2026-08-14", "status": "active", "top_tasks": [{"task": "Publish campaign", "why": "Sale", "time_blocked": "30 minutes", "status": "done", "completed_at": "2026-08-14T01:00:00Z"}], "additional_items": []},
            {"id": "sheet-w", "user_id": "worker-1", "user_name": "Reina", "sheet_date": "2026-08-14", "status": "active", "top_tasks": [{"task": "Prepare products", "why": "Range", "time_blocked": "45 minutes", "status": "couldnt_finish", "finished_at": "2026-08-14T02:00:00Z"}], "additional_items": []},
        ]
        timers = [
            {"sheet_id": "sheet-a", "task_type": "top", "task_index": 0, "outcome": "completed", "outcome_at": "2026-08-14T01:00:00Z", "actual_elapsed_seconds": 1200},
            {"sheet_id": "sheet-w", "task_type": "top", "task_index": 0, "outcome": "did_not_finish", "outcome_at": "2026-08-14T02:00:00Z", "actual_elapsed_seconds": 1500},
        ]
        fulfilled = {
            "id": "activity-1", "event_type": "order_fulfilled_certificate_generated", "entity_type": "order", "entity_id": "SC3013", "source": "Fulfilment", "actor": "Reina", "created_at": "2026-08-14T03:00:00Z",
            "new_value": {"message": "Order #SC3013 fulfilled and certificate generated", "action_type": "order_fulfilled_certificate_generated", "page": "Orders", "metadata": {"actor_id": "worker-1", "event_key": "fulfilled:SC3013", "result": "success"}},
        }
        download = {
            "id": "activity-2", "event_type": "files_downloaded", "entity_type": "file", "entity_id": "secret.psd", "source": "Files", "actor": "Reina", "created_at": "2026-08-14T04:00:00Z",
            "new_value": {"message": "Downloaded file: secret.psd", "action_type": "files_downloaded", "metadata": {"actor_id": "worker-1"}},
        }

        class Backend:
            def __init__(self):
                self.calls = []

            def load_home_weekly_work_bundle(self, user_id, week_start, week_end, start_utc, end_utc, *, include_team):
                self.calls.append((user_id, week_start, week_end, start_utc, end_utc, include_team))
                return {"users": users, "sheets": sheets, "timers": timers, "activities": [fulfilled, dict(fulfilled), download], "query_count": 1}

        backend = Backend()
        admin = {**users[0], "timezone": "Australia/Sydney", "page_permissions": []}
        worker = {**users[1], "timezone": "Asia/Manila", "page_permissions": ["dashboard"]}
        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=backend):
            admin_snapshot = sports_cave_dashboard.build_home_weekly_work_snapshot(admin, now)
            worker_snapshot = sports_cave_dashboard.build_home_weekly_work_snapshot(worker, now)

        self.assertEqual("2026-08-10", admin_snapshot["week_start"])
        self.assertEqual("2026-08-16", admin_snapshot["week_end"])
        self.assertEqual(2, len(admin_snapshot["team"]))
        self.assertEqual(2, admin_snapshot["metrics"]["tasks_completed"])
        self.assertEqual(1, admin_snapshot["metrics"]["planner_tasks_completed"])
        self.assertEqual(1, admin_snapshot["metrics"]["tasks_not_finished"])
        self.assertEqual(2, admin_snapshot["metrics"]["tasks_total"])
        self.assertEqual(50.0, admin_snapshot["metrics"]["completion_percentage"])
        self.assertEqual(1, admin_snapshot["metrics"]["meaningful_actions"])
        self.assertEqual(3, len(admin_snapshot["completed_work"]))
        self.assertEqual(["Reina"], [row["staff"] for row in worker_snapshot["team"]])
        self.assertEqual(0.0, worker_snapshot["metrics"]["completion_percentage"])
        self.assertTrue(all(row["staff_id"] == "worker-1" for row in worker_snapshot["completed_work"]))
        self.assertFalse(backend.calls[1][-1])

    def test_lightweight_route_avoids_full_app_and_sanitises_task_rows(self):
        source = (ROOT / "daily_planner.py").read_text(encoding="utf-8")
        for forbidden in ("import streamlit", "import app", "shopify", "render_lightweight_dashboard_page"):
            self.assertNotIn(forbidden, source.casefold())
        cleaned = daily_planner._clean_tasks([{"task": "Task", "details": None}], top=False)
        self.assertEqual("", cleaned[0]["details"])
        self.assertTrue(daily_activity_reporting.activity_is_meaningful_work({
            "event_type": "product_uploaded",
            "source": "Products",
            "created_at": "2026-08-15T00:00:00Z",
            "new_value": {"message": "Product uploaded", "action_type": "product_uploaded", "metadata": {"actor_id": "admin-1"}},
        }))

    def test_countdown_restores_from_deadline_and_expiry_cannot_be_reset(self):
        now = datetime(2026, 8, 15, 0, 0, tzinfo=timezone.utc)
        running = {
            "status": "running",
            "allocated_seconds": 120,
            "deadline_at": now + timedelta(seconds=60),
        }
        self.assertEqual(60, supabase_backend._daily_timer_remaining_seconds(running, now))
        self.assertEqual(60, supabase_backend._daily_timer_elapsed_seconds(running, now))
        self.assertEqual(45, supabase_backend._daily_timer_remaining_seconds({"status": "paused", "remaining_seconds": 45}, now))
        self.assertEqual(0, supabase_backend._daily_timer_remaining_seconds({"status": "expired", "remaining_seconds": 99}, now))

        source = (ROOT / "supabase_backend.py").read_text(encoding="utf-8")
        pause_source = source[source.index("def pause_daily_execution_task_timer") : source.index("\n\ndef resume_daily_execution_task_timer")]
        stop_source = source[source.index("def stop_daily_execution_task_timer") : source.index("\n\ndef reconcile_daily_execution_timers")]
        self.assertIn("reconcile_daily_execution_timers(clean_user_id, actor=actor)", pause_source)
        self.assertIn("_expire_daily_timer_row", pause_source)
        self.assertIn("status IN ('running', 'paused')", stop_source)
        self.assertNotIn("'expired'", stop_source)

    def test_finish_skip_reopen_are_atomic_idempotent_outcomes(self):
        backend_source = (ROOT / "supabase_backend.py").read_text(encoding="utf-8")
        route_source = (ROOT / "daily_planner.py").read_text(encoding="utf-8")
        client_source = (ROOT / "components" / "daily_planner" / "index.html").read_text(encoding="utf-8")
        migration = (ROOT / "migrations" / "20260815_daily_execution_task_outcomes.sql").read_text(encoding="utf-8")

        outcome_body = backend_source[
            backend_source.index("def apply_daily_execution_task_outcome") :
            backend_source.index("\n\ndef apply_daily_execution_timer_outcome")
        ]
        self.assertIn("FOR UPDATE", outcome_body)
        transition_body = backend_source[
            backend_source.index("def _daily_task_terminal_transition") :
            backend_source.index("\n\ndef apply_daily_execution_task_outcome")
        ]
        self.assertIn("_daily_timer_elapsed_seconds(timer, now_utc)", transition_body)
        self.assertIn('"finished_early"', transition_body)
        self.assertIn('"skipped"', transition_body)
        self.assertIn('"reopen"', outcome_body)
        self.assertIn('"already_applied": True', outcome_body)
        self.assertIn("outcome_version", outcome_body)
        self.assertIn("WHEN %s AND status='finalised' THEN 'reopened'", outcome_body)
        self.assertIn('action == "task_outcome"', route_source)
        self.assertIn('window.confirm("Finish this task now?")', client_source)
        self.assertIn("Skip this task? It will be recorded as not completed.", client_source)
        self.assertIn('data-action="reopen-task"', client_source)
        self.assertIn('data-action="finish-active"', client_source)
        self.assertIn('data-action="skip-active"', client_source)
        self.assertIn("state.bundle.active_timer = {};", client_source)
        self.assertIn(
            "broadcastTimer(clearsActive ? {} : activeTimer(), [], terminalTimerId)",
            client_source,
        )
        self.assertNotIn("state.bundle.active_timer = previousActive;", client_source)
        self.assertIn('action:"task_outcome"', client_source)
        self.assertNotIn('action:"timer_outcome"', client_source)
        self.assertIn('if (!String(task?.task || task?.details || "").trim()) return "";', client_source)
        self.assertIn("ADD COLUMN IF NOT EXISTS completion_method", migration)
        self.assertIn("'completed', 'did_not_finish', 'skipped'", migration)

    def test_finish_transition_uses_real_running_paused_and_unstarted_elapsed_time(self):
        now = datetime(2026, 8, 15, 2, 0, tzinfo=timezone.utc)
        task = {"task": "Prepare campaign", "time_blocked": "2 minutes"}

        running = supabase_backend._daily_task_terminal_transition(
            task,
            {
                "status": "running",
                "allocated_seconds": 120,
                "deadline_at": now + timedelta(seconds=65),
            },
            "completed",
            now_utc=now,
        )["task"]
        paused = supabase_backend._daily_task_terminal_transition(
            task,
            {"status": "paused", "allocated_seconds": 120, "remaining_seconds": 45},
            "completed",
            now_utc=now,
        )["task"]
        expired = supabase_backend._daily_task_terminal_transition(
            task,
            {"status": "expired", "allocated_seconds": 120, "remaining_seconds": 0},
            "completed",
            now_utc=now,
        )["task"]
        unstarted = supabase_backend._daily_task_terminal_transition(
            task,
            {},
            "completed",
            now_utc=now,
        )["task"]

        self.assertEqual("done", running["status"])
        self.assertTrue(running["completed"])
        self.assertEqual("finished_early", running["completion_method"])
        self.assertEqual(55, running["actual_elapsed_seconds"])
        self.assertEqual(65, running["time_saved_seconds"])
        self.assertEqual(75, paused["actual_elapsed_seconds"])
        self.assertEqual(45, paused["time_saved_seconds"])
        self.assertEqual("completed_after_expiry", expired["completion_method"])
        self.assertEqual(120, expired["actual_elapsed_seconds"])
        self.assertFalse(expired["completed_before_expiry"])
        self.assertIsNone(expired["time_saved_seconds"])
        self.assertEqual("completed_manually", unstarted["completion_method"])
        self.assertNotIn("actual_elapsed_seconds", unstarted)
        self.assertEqual("2 minutes", unstarted["time_blocked"])

    def test_skip_transition_preserves_real_elapsed_and_reason_without_completion(self):
        now = datetime(2026, 8, 15, 2, 0, tzinfo=timezone.utc)
        task = {"task": "Upload range"}
        running = supabase_backend._daily_task_terminal_transition(
            task,
            {
                "status": "running",
                "allocated_seconds": 120,
                "deadline_at": now + timedelta(seconds=90),
            },
            "skipped",
            reason="Supplier files unavailable",
            now_utc=now,
        )["task"]
        paused = supabase_backend._daily_task_terminal_transition(
            task,
            {"status": "paused", "allocated_seconds": 120, "remaining_seconds": 80},
            "skipped",
            now_utc=now,
        )["task"]
        unstarted = supabase_backend._daily_task_terminal_transition(
            task,
            {},
            "skipped",
            now_utc=now,
        )["task"]

        self.assertEqual("skipped", running["status"])
        self.assertFalse(running["completed"])
        self.assertEqual(30, running["actual_elapsed_seconds"])
        self.assertEqual("Supplier files unavailable", running["skip_reason"])
        self.assertEqual(40, paused["actual_elapsed_seconds"])
        self.assertEqual("No time available", paused["skip_reason"])
        self.assertNotIn("actual_elapsed_seconds", unstarted)
        self.assertEqual("No time available", unstarted["skip_reason"])

    def test_did_not_finish_transition_is_terminal_without_completion(self):
        task = supabase_backend._daily_task_terminal_transition(
            {"task": "Prepare campaign"},
            {"status": "paused", "allocated_seconds": 120, "remaining_seconds": 35},
            "did_not_finish",
            now_utc=datetime(2026, 8, 15, 2, 0, tzinfo=timezone.utc),
        )["task"]

        self.assertEqual("couldnt_finish", task["status"])
        self.assertEqual("did_not_finish", task["outcome"])
        self.assertEqual("did_not_finish", task["completion_method"])
        self.assertFalse(task["completed"])
        self.assertEqual(85, task["actual_elapsed_seconds"])

    def test_daily_review_summary_counts_all_non_empty_terminal_outcomes(self):
        sheet = {
            "id": "sheet-1",
            "sheet_date": "2026-08-15",
            "top_tasks": [
                {"task": "Complete", "status": "done", "actual_elapsed_seconds": 120},
                {"task": "Attempted", "status": "couldnt_finish", "actual_elapsed_seconds": 60},
                {"task": "Skipped", "status": "skipped"},
            ],
            "additional_items": [
                {"task": "Open task", "status": ""},
                {"task": "", "details": "", "time_blocked": ""},
            ],
        }

        summary = sports_cave_dashboard.daily_execution_outcome_summary(sheet)

        self.assertEqual(4, summary["total_planned"])
        self.assertEqual(1, summary["completed"])
        self.assertEqual(1, summary["did_not_finish"])
        self.assertEqual(1, summary["skipped"])
        self.assertEqual(1, summary["unresolved"])
        self.assertEqual(25.0, summary["completion_percentage"])
        self.assertEqual(["Open task"], summary["unresolved_tasks"])
        self.assertFalse(sports_cave_dashboard.daily_execution_all_tasks_complete(sheet))
        sheet["additional_items"][0]["status"] = "skipped"
        self.assertTrue(sports_cave_dashboard.daily_execution_all_tasks_complete(sheet))

    def test_weekly_completion_excludes_future_and_deduplicates_carry_forward(self):
        sheets = [
            {
                "id": "monday", "user_id": "staff-1", "user_name": "Reina", "sheet_date": "2026-08-10",
                "top_tasks": [{"task": "Campaign", "status": "couldnt_finish"}], "additional_items": [],
            },
            {
                "id": "tuesday", "user_id": "staff-1", "user_name": "Reina", "sheet_date": "2026-08-11",
                "top_tasks": [{"task": "Product upload", "status": "done"}],
                "additional_items": [
                    {"task": "Campaign", "status": "done", "carried_from": "2026-08-10"},
                    {"task": "No time", "status": "skipped"},
                ],
            },
            {
                "id": "wednesday", "user_id": "staff-1", "user_name": "Reina", "sheet_date": "2026-08-12",
                "top_tasks": [{"task": "Campaign", "status": ""}], "additional_items": [],
            },
            {
                "id": "future", "user_id": "staff-1", "user_name": "Reina", "sheet_date": "2026-08-16",
                "top_tasks": [{"task": "Future task", "status": "done"}], "additional_items": [],
            },
        ]

        summary = sports_cave_dashboard.daily_execution_weekly_summary(
            sheets, today=date(2026, 8, 15)
        )

        self.assertEqual(4, summary["total_planned"])
        self.assertEqual(2, summary["completed"])
        self.assertEqual(1, summary["skipped"])
        self.assertEqual(0, summary["did_not_finish"])
        self.assertEqual(1, summary["unresolved"])
        self.assertEqual(50.0, summary["completion_percentage"])
        self.assertEqual(1, len(summary["staff_completion"]))
        self.assertAlmostEqual(
            summary["completion_percentage"],
            summary["staff_completion"][0]["completion_percentage"],
        )

    def test_black_panel_is_removed_at_the_compact_layout_source(self):
        client_source = (ROOT / "components" / "daily_planner" / "index.html").read_text(encoding="utf-8")

        self.assertIn(".compact-only { display: none !important; }", client_source)
        self.assertIn("body.compact .compact-only { display: flex !important; }", client_source)
        self.assertIn('id="compact-view"', client_source)
        self.assertNotIn("<audio", client_source)
        self.assertNotIn("<canvas", client_source)
        self.assertIn("setTimeout(stopChime", client_source)
        self.assertNotIn("Stop Sound", client_source)

    def test_toolbar_countdown_mirror_is_client_side_and_cross_window(self):
        source = (ROOT / "components" / "sports_cave_top_bar" / "index.html").read_text(encoding="utf-8")
        planner_source = (ROOT / "components" / "daily_planner" / "index.html").read_text(encoding="utf-8")
        admin_config = top_bar.top_bar_config(
            {"id": "admin-1", "role": "admin", "is_active": True, "page_permissions": []},
            logo_src="logo",
            current_route="Dashboard",
        )
        other_config = top_bar.top_bar_config(
            {"id": "admin-2", "role": "admin", "is_active": True, "page_permissions": []},
            logo_src="logo",
            current_route="Dashboard",
        )
        safe = top_bar_api._daily_planner_timer_mirror(
            {
                "id": "timer-1", "user_id": "private-user", "task": "Gym", "status": "running",
                "deadline_at": "2026-08-15T02:00:00Z", "remaining_seconds": 60,
            }
        )

        self.assertIn('id="sc-os-planner-timer-pill"', source)
        self.assertIn("BroadcastChannel(\"sports-cave-daily-planner\")", source)
        self.assertIn("scSportsCavePlannerTimerState", source)
        self.assertEqual(1, source.count("setInterval(() =>"))
        self.assertIn("updatePlannerMirror();", source)
        self.assertIn("schedulePlannerStatus(30000)", source)
        self.assertIn("openDailyPlanner({focusActive:true})", source)
        self.assertIn("plannerChannel?.close()", source)
        self.assertIn("parentWindow.navigator.locks.request", source)
        self.assertIn("payload.scope !== state.config.dailyPlannerTimerScope", source)
        self.assertIn('broadcastTimer(mirror, [], "", terminalTimerIds, action === "start_timer" ? mirror.id : "")', planner_source)
        self.assertIn("navigator.locks.request", planner_source)
        self.assertIn("payload.scope !== state.timerScope", planner_source)
        self.assertNotEqual(
            admin_config["dailyPlannerTimerScope"],
            other_config["dailyPlannerTimerScope"],
        )
        self.assertNotIn("admin-1", admin_config["dailyPlannerTimerScope"])
        self.assertNotIn("user_id", safe)
        self.assertEqual("Gym", safe["task"])

    def test_outcome_migration_is_targetable_idempotent_and_runner_safe(self):
        filename = "20260815_daily_execution_task_outcomes.sql"
        path = ROOT / "migrations" / filename
        sql = path.read_text(encoding="utf-8")

        self.assertEqual([path], run_migrations.migration_files(filename))
        self.assertTrue(run_migrations.safe_migration_sql(sql))
        self.assertIn("ADD COLUMN IF NOT EXISTS completion_method", sql)
        self.assertIn("DROP CONSTRAINT IF EXISTS daily_execution_task_timers_outcome_check", sql)
        self.assertFalse(run_migrations.safe_migration_sql("DROP TABLE daily_execution_sheets;"))

    def test_missing_outcome_schema_returns_specific_actionable_error(self):
        class Diagnostic:
            column_name = "completion_method"
            constraint_name = ""

        class MissingColumnError(Exception):
            sqlstate = "42703"
            diag = Diagnostic()

        message = supabase_backend.daily_execution_outcome_schema_error_message(
            MissingColumnError('column "completion_method" does not exist')
        )

        self.assertIn("20260815_daily_execution_task_outcomes.sql", message)
        self.assertNotIn("Dashboard saving is unavailable", message)
        self.assertEqual(message, sports_cave_dashboard._daily_outcome_storage_error(MissingColumnError()))

    def test_expired_completion_api_persists_and_refresh_reads_saved_state(self):
        user = {"id": "admin-local", "username": "nathan", "display_name": "Nathan", "role": "admin"}
        token = top_bar_security.create_top_bar_token(
            user,
            can_manage_daily_planner=True,
            now=1_786_742_400,
            seconds=3600,
        )
        saved_sheet = {
            "id": "sheet-1",
            "sheet_date": "2026-08-15",
            "top_tasks": [{
                "task": "Pack orders",
                "status": "done",
                "outcome": "completed",
                "completion_method": "completed_after_expiry",
                "actual_elapsed_seconds": 120,
                "outcome_version": 1,
            }],
            "additional_items": [],
        }
        saved_result = {
            "sheet": saved_sheet,
            "timer": {
                "id": "timer-1",
                "status": "completed",
                "outcome": "completed",
                "outcome_required": False,
                "actual_elapsed_seconds": 120,
                "allocated_seconds": 120,
                "completion_method": "completed_after_expiry",
                "completed_before_expiry": False,
            },
            "already_applied": False,
        }
        request = planner_api_request(
            daily_planner.PLANNER_MUTATION_PATH,
            token,
            method="POST",
            payload={
                "action": "task_outcome",
                "sheet_id": "sheet-1",
                "task_type": "top",
                "task_index": 0,
                "timer_id": "timer-1",
                "outcome": "completed",
            },
        )
        with patch("top_bar_security.time.time", return_value=1_786_742_500), patch.object(
            sports_cave_dashboard,
            "finalise_overdue_daily_planner_days",
            return_value={"finalised_sheets": [], "review_reminder": {}},
        ), patch.object(
            sports_cave_dashboard,
            "apply_daily_planner_task_outcome",
            return_value=saved_result,
        ) as save:
            response = asyncio.run(daily_planner.planner_mutation(request))

        body = json.loads(response.body)
        self.assertEqual(200, response.status_code)
        self.assertEqual("done", body["result"]["sheet"]["top_tasks"][0]["status"])
        self.assertFalse(body["result"]["timer"]["outcome_required"])
        self.assertEqual("timer-1", save.call_args.kwargs["timer_id"])

        bundle = {
            "work_date": "2026-08-15",
            "today": "2026-08-15",
            "timezone": "Australia/Sydney",
            "sheet": saved_sheet,
            "source_sheet": {},
            "tasks": [],
            "active_timer": {},
            "events": [],
            "server_now": "2026-08-15T00:00:00+00:00",
            "performance": {"planner_data_ms": 0.1, "initial_api_calls": 1, "database_transactions": 2},
        }
        refresh_request = planner_api_request(
            daily_planner.PLANNER_BOOTSTRAP_PATH,
            token,
            query_string=b"date=2026-08-15",
        )
        with patch("top_bar_security.time.time", return_value=1_786_742_500), patch.object(
            daily_planner, "_load_sheet_bundle", return_value=bundle
        ):
            refresh = asyncio.run(daily_planner.planner_bootstrap(refresh_request))
        self.assertEqual("completed", json.loads(refresh.body)["sheet"]["top_tasks"][0]["outcome"])
        self.assertEqual({}, json.loads(refresh.body)["active_timer"])

    def test_outcome_api_failure_keeps_action_retryable_and_names_migration(self):
        user = {"id": "admin-local", "username": "nathan", "display_name": "Nathan", "role": "admin"}
        token = top_bar_security.create_top_bar_token(
            user,
            can_manage_daily_planner=True,
            now=1_786_742_400,
            seconds=3600,
        )
        request = planner_api_request(
            daily_planner.PLANNER_MUTATION_PATH,
            token,
            method="POST",
            payload={
                "action": "task_outcome",
                "sheet_id": "sheet-1",
                "task_type": "top",
                "task_index": 0,
                "timer_id": "timer-1",
                "outcome": "completed",
            },
        )
        message = (
            "Daily Planner outcome storage is out of date. Apply migration "
            "20260815_daily_execution_task_outcomes.sql, then retry."
        )
        with patch("top_bar_security.time.time", return_value=1_786_742_500), patch.object(
            sports_cave_dashboard,
            "finalise_overdue_daily_planner_days",
            return_value={"finalised_sheets": [], "review_reminder": {}},
        ), patch.object(
            sports_cave_dashboard,
            "apply_daily_planner_task_outcome",
            side_effect=sports_cave_dashboard.DashboardStorageError(message),
        ):
            response = asyncio.run(daily_planner.planner_mutation(request))

        body = json.loads(response.body)
        self.assertEqual(503, response.status_code)
        self.assertEqual("daily_planner_outcome_migration_required", body["error_code"])
        self.assertTrue(body["retryable"])
        self.assertEqual(message, body["error"])

    def test_did_not_finish_api_returns_authoritative_terminal_sheet(self):
        user = {"id": "admin-local", "username": "nathan", "display_name": "Nathan", "role": "admin"}
        token = top_bar_security.create_top_bar_token(
            user,
            can_manage_daily_planner=True,
            now=1_786_742_400,
            seconds=3600,
        )
        saved_result = {
            "sheet": {
                "id": "sheet-1",
                "sheet_date": "2026-08-15",
                "top_tasks": [{
                    "task": "Pack orders",
                    "status": "couldnt_finish",
                    "outcome": "did_not_finish",
                    "actual_elapsed_seconds": 120,
                    "outcome_version": 1,
                }],
                "additional_items": [],
            },
            "timer": {
                "id": "timer-1",
                "status": "completed",
                "outcome": "did_not_finish",
                "outcome_required": False,
            },
            "already_applied": False,
        }
        request = planner_api_request(
            daily_planner.PLANNER_MUTATION_PATH,
            token,
            method="POST",
            payload={
                "action": "task_outcome",
                "sheet_id": "sheet-1",
                "task_type": "top",
                "task_index": 0,
                "timer_id": "timer-1",
                "outcome": "did_not_finish",
            },
        )
        with patch("top_bar_security.time.time", return_value=1_786_742_500), patch.object(
            sports_cave_dashboard,
            "finalise_overdue_daily_planner_days",
            return_value={"finalised_sheets": [], "review_reminder": {}},
        ), patch.object(
            sports_cave_dashboard,
            "apply_daily_planner_task_outcome",
            return_value=saved_result,
        ) as save:
            response = asyncio.run(daily_planner.planner_mutation(request))

        body = json.loads(response.body)
        self.assertEqual(200, response.status_code)
        self.assertEqual("couldnt_finish", body["result"]["sheet"]["top_tasks"][0]["status"])
        self.assertEqual("did_not_finish", body["result"]["timer"]["outcome"])
        self.assertEqual("did_not_finish", save.call_args.args[4])

    def test_outcome_client_waits_for_server_and_uses_one_shot_chimes(self):
        planner_source = (ROOT / "components" / "daily_planner" / "index.html").read_text(
            encoding="utf-8"
        )
        topbar_source = (
            ROOT / "components" / "sports_cave_top_bar" / "index.html"
        ).read_text(encoding="utf-8")
        outcome_source = planner_source[
            planner_source.index("const applyTaskOutcome") :
            planner_source.index("const updateTimerDisplays")
        ]

        self.assertLess(outcome_source.index("result = await mutate(request)"), outcome_source.index("stopChime()"))
        self.assertLess(outcome_source.index("result = await mutate(request)"), outcome_source.index("closeOutcomeModal()"))
        self.assertIn("state.outcomeSaving", outcome_source)
        self.assertIn('trigger.textContent = "Saving\\u2026"', planner_source)
        self.assertIn("data-outcome-retry", planner_source)
        self.assertIn("showOutcomeError(error)", outcome_source)
        self.assertIn('runClaimedSideEffect("success"', outcome_source)
        self.assertNotIn('action:"timer_outcome"', planner_source)
        self.assertNotIn("Stop Sound", planner_source)
        self.assertNotIn("Stop Sound", topbar_source)
        self.assertNotIn("for (let pulse", planner_source)
        self.assertNotIn("for (let pulse", topbar_source)
        self.assertNotIn("5050", planner_source)
        self.assertNotIn("5050", topbar_source)
        self.assertIn('runClaimedSideEffect("time-up"', planner_source)
        self.assertNotIn('runClaimedPlannerEffect("time-up"', topbar_source)
        self.assertNotIn("chime:true", topbar_source)
        self.assertIn("sports-cave-planner-open-request", topbar_source)
        self.assertIn("if (!state.plannerTimer.id || state.plannerTimer.outcome) stopPlannerChime()", topbar_source)
        self.assertIn('payload.type !== "sports-cave-planner-data-updated"', topbar_source)
        self.assertIn('["dashboard", "reporting", "weekly review"].includes(route)', topbar_source)
        self.assertIn("offset:.31, duration:.40", planner_source)

    def test_confirmed_outcome_fully_closes_and_cannot_be_reopened_by_stale_timer_state(self):
        planner_source = (ROOT / "components" / "daily_planner" / "index.html").read_text(
            encoding="utf-8"
        )
        topbar_source = (
            ROOT / "components" / "sports_cave_top_bar" / "index.html"
        ).read_text(encoding="utf-8")
        close_source = planner_source[
            planner_source.index("const focusPlannerControls") :
            planner_source.index("const escapeHtml")
        ]
        outcome_source = planner_source[
            planner_source.index("const applyTaskOutcome") :
            planner_source.index("const updateTimerDisplays")
        ]
        show_source = planner_source[
            planner_source.index("const showOutcome =") :
            planner_source.index("const refreshStatus")
        ]
        receive_source = planner_source[
            planner_source.index("const receiveTimerState") :
            planner_source.index("const enableAudio")
        ]
        status_source = planner_source[
            planner_source.index("const refreshStatus") :
            planner_source.index("const scheduleStatus")
        ]

        self.assertIn("outcome?.remove()", close_source)
        self.assertIn("outcome = null", close_source)
        self.assertIn('document.querySelectorAll("[data-planner-outcome-backdrop]")', close_source)
        self.assertIn("view.inert = false", close_source)
        self.assertIn("compactView.inert = false", close_source)
        self.assertIn("requestAnimationFrame", close_source)
        self.assertLess(outcome_source.index("result = await mutate(request)"), outcome_source.index("state.bundle.sheet = result.sheet"))
        self.assertLess(outcome_source.index("state.bundle.sheet = result.sheet"), outcome_source.index("closeOutcomeModal()"))
        self.assertIn("markTimerTerminal(terminalTimerId)", outcome_source)
        self.assertIn("clearTimerEffectClaims(terminalTimerId)", outcome_source)
        self.assertIn("renderCurrent()", outcome_source)
        self.assertIn("{preserveView:true, restoreFocus:true}", outcome_source)
        self.assertIn('showToast(outcomeMessage, "success", 3500)', outcome_source)
        self.assertIn('data-outcome="completed"', show_source)
        self.assertIn('data-outcome="did_not_finish"', show_source)
        self.assertIn("if (showOutcome(timer))", show_source)
        self.assertIn("terminalTimerIds", planner_source)
        self.assertIn("timerEpoch !== state.timerEpoch", planner_source)
        self.assertIn("currentTimerPayload(payload.timer)", status_source)
        self.assertIn("terminal_timer_id", receive_source)
        self.assertIn("if (payload.terminal_timer_id) localStorage.setItem", planner_source)
        self.assertIn("const outcomeVisible = showOutcome(timer)", status_source)
        self.assertIn("plannerTimerWasTerminated(payload.timer)", topbar_source)
        self.assertIn("terminalPlannerTimerIds", topbar_source)
        self.assertIn("dismissPlannerToast()", topbar_source)
        self.assertIn("if (payload.terminal_timer_id) parentWindow.localStorage.setItem", topbar_source)
        self.assertIn("parentWindow.localStorage.removeItem(timerStorageKey())", topbar_source)

    def test_failed_outcome_keeps_retry_and_double_submit_is_suppressed(self):
        planner_source = (ROOT / "components" / "daily_planner" / "index.html").read_text(
            encoding="utf-8"
        )
        outcome_source = planner_source[
            planner_source.index("const applyTaskOutcome") :
            planner_source.index("const updateTimerDisplays")
        ]
        failure_source = outcome_source[
            outcome_source.index("} catch (error) {") :
            outcome_source.index("if (!result?.sheet?.id)")
        ]
        toast_source = planner_source[
            planner_source.index("const showToast") :
            planner_source.index("const showSkeleton")
        ]

        self.assertIn("if (state.outcomeSaving) return null", outcome_source)
        self.assertIn("showOutcomeError(error)", failure_source)
        self.assertIn("showTaskOutcomeRetry(error)", failure_source)
        self.assertNotIn("closeOutcomeModal", failure_source)
        self.assertIn("data-outcome-retry", planner_source)
        self.assertIn("clearTimeout(state.toastTimer)", toast_source)
        self.assertIn("setTimeout(() => toast.classList.add(\"hidden\"), duration)", toast_source)

    def test_legacy_expiry_route_delegates_to_canonical_locked_outcome(self):
        source = (ROOT / "supabase_backend.py").read_text(encoding="utf-8")
        legacy = source[
            source.index("def apply_daily_execution_timer_outcome") :
            source.index("\n\ndef start_sync_run")
        ]
        canonical = source[
            source.index("def apply_daily_execution_task_outcome") :
            source.index("\n\ndef apply_daily_execution_timer_outcome")
        ]

        self.assertIn("return apply_daily_execution_task_outcome(", legacy)
        self.assertNotIn("UPDATE daily_execution_sheets", legacy)
        self.assertIn("FOR UPDATE", canonical)
        self.assertIn('"already_applied": True', canonical)
        self.assertIn("event_key=f\"{event_type}:{event_entity}:v{outcome_version}\"", canonical)

    def test_planner_api_requires_signed_planner_permission(self):
        user = {"id": "admin-local", "username": "nathan", "display_name": "Nathan", "role": "admin"}
        allowed = top_bar_security.create_top_bar_token(
            user,
            can_manage_daily_planner=True,
            now=1_786_742_400,
            seconds=3600,
        )
        denied = top_bar_security.create_top_bar_token(
            {**user, "id": "worker-local", "role": "worker"},
            can_manage_daily_planner=False,
            now=1_786_742_400,
            seconds=3600,
        )

        def request_for(token):
            return Request(
                {
                    "type": "http",
                    "http_version": "1.1",
                    "method": "GET",
                    "scheme": "http",
                    "path": daily_planner.PLANNER_BOOTSTRAP_PATH,
                    "raw_path": daily_planner.PLANNER_BOOTSTRAP_PATH.encode(),
                    "query_string": b"date=2026-08-15",
                    "headers": [(b"authorization", f"Bearer {token}".encode())],
                    "client": ("127.0.0.1", 1),
                    "server": ("127.0.0.1", 8501),
                }
            )

        bundle = {
            "work_date": "2026-08-15",
            "today": "2026-08-15",
            "timezone": "Australia/Sydney",
            "sheet": {},
            "source_sheet": {},
            "tasks": [],
            "active_timer": {},
            "events": [],
            "server_now": "2026-08-15T00:00:00+00:00",
            "performance": {"planner_data_ms": 0.1, "initial_api_calls": 1, "database_transactions": 2},
        }
        with patch("top_bar_security.time.time", return_value=1_786_742_500), patch.object(
            daily_planner, "_load_sheet_bundle", return_value=bundle
        ):
            allowed_response = asyncio.run(daily_planner.planner_bootstrap(request_for(allowed)))
            denied_response = asyncio.run(daily_planner.planner_bootstrap(request_for(denied)))

        self.assertEqual(200, allowed_response.status_code)
        self.assertEqual(403, denied_response.status_code)
        self.assertEqual("admin-local", json.loads(allowed_response.body)["user"]["id"])

    def test_start_timer_replaces_prior_lock_in_one_authoritative_transaction(self):
        backend_source = (ROOT / "supabase_backend.py").read_text(encoding="utf-8")
        client_source = (ROOT / "components" / "daily_planner" / "index.html").read_text(encoding="utf-8")
        start_body = backend_source[
            backend_source.index("def start_daily_execution_task_timer") :
            backend_source.index("\n\ndef pause_daily_execution_task_timer")
        ]
        start_handler = client_source[
            client_source.index('if (action === "start-timer")') :
            client_source.index('if (action === "pause-timer")')
        ]

        self.assertIn("pg_advisory_xact_lock", start_body)
        self.assertIn("_finalise_overdue_daily_execution_sheets_locked", start_body)
        self.assertIn("FOR UPDATE", start_body)
        self.assertIn("replaced_by_next_task", start_body)
        self.assertIn('"preserved_terminal": preserved_terminal', start_body)
        self.assertIn('"replaced_timers": replaced', start_body)
        self.assertIn('"already_started": True', start_body)
        self.assertNotIn("A Daily Planner timer is already active.", start_body)
        self.assertNotIn("window.confirm", start_handler)
        self.assertNotIn('action:"reset_timer"', start_handler)
        self.assertIn('timerAction("start_timer"', start_handler)

    def test_start_timer_route_returns_previous_resolution_and_new_timer(self):
        user = {"id": "admin-local", "username": "nathan", "display_name": "Nathan", "role": "admin"}
        token = top_bar_security.create_top_bar_token(
            user,
            can_manage_daily_planner=True,
            now=1_786_828_800,
            seconds=3600,
        )
        authoritative = {
            "timer": {"id": "timer-b", "status": "running", "task": "Task B"},
            "active_timer": {"id": "timer-b", "status": "running", "task": "Task B"},
            "replaced_timers": [{
                "timer": {"id": "timer-a", "status": "completed", "outcome": "did_not_finish"},
                "outcome": "did_not_finish",
                "audit_reason": "replaced_by_next_task",
            }],
            "rollover": {"finalised_dates": []},
        }
        request = planner_api_request(
            daily_planner.PLANNER_MUTATION_PATH,
            token,
            method="POST",
            payload={
                "action": "start_timer",
                "sheet_id": "sheet-today",
                "task_type": "top",
                "task_index": 1,
                "allocated_seconds": 120,
            },
        )
        class FixedDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 8, 16, 12, 0, tzinfo=tz)

        with patch.object(daily_planner, "datetime", FixedDatetime), patch(
            "top_bar_security.time.time", return_value=1_786_828_900
        ), patch.object(
            sports_cave_dashboard,
            "start_daily_planner_timer",
            return_value=authoritative,
        ) as start:
            response = asyncio.run(daily_planner.planner_mutation(request))

        body = json.loads(response.body)
        self.assertEqual(200, response.status_code)
        self.assertEqual("timer-b", body["result"]["active_timer"]["id"])
        self.assertEqual("did_not_finish", body["result"]["replaced_timers"][0]["outcome"])
        self.assertEqual(date(2026, 8, 16), start.call_args.kwargs["local_today"])

    def test_overdue_rollover_preserves_terminal_tasks_and_is_idempotent(self):
        sheets = [
            {
                "id": "sheet-15",
                "user_id": "admin-1",
                "user_name": "Nathan",
                "sheet_date": date(2026, 8, 15),
                "status": "active",
                "completed_at": None,
                "top_tasks": [
                    {"task": "Completed", "status": "done", "outcome": "completed"},
                    {"task": "Skipped", "status": "skipped", "outcome": "skipped"},
                    {"task": "Still open", "status": ""},
                ],
                "additional_items": [
                    {"task": "Already unfinished", "status": "couldnt_finish", "outcome": "did_not_finish"},
                    {"task": "Paused work", "status": ""},
                    {"task": "", "details": "", "status": ""},
                ],
            }
        ]
        timers = [
            {
                "id": "timer-open", "user_id": "admin-1", "sheet_id": "sheet-15",
                "task_type": "top", "task_index": 2, "status": "running",
                "allocated_seconds": 120, "deadline_at": "2026-08-15T05:00:00+00:00",
                "outcome": None,
            },
            {
                "id": "timer-paused", "user_id": "admin-1", "sheet_id": "sheet-15",
                "task_type": "additional", "task_index": 1, "status": "paused",
                "allocated_seconds": 180, "remaining_seconds": 60, "outcome": None,
            },
        ]

        class Cursor:
            def __init__(self):
                self.rows = []
                self.audit_inserts = 0

            def execute(self, sql, params=()):
                compact = " ".join(sql.split())
                self.rows = []
                if "FROM daily_execution_sheets" in compact and "status IN ('active', 'planned')" in compact:
                    self.rows = [row for row in sheets if row["status"] in {"active", "planned"}]
                elif "FROM daily_execution_task_timers" in compact and "sheet_id=ANY" in compact:
                    self.rows = list(timers)
                elif "UPDATE daily_execution_task_timers" in compact:
                    timer_id = str(params[-2])
                    for timer in timers:
                        if timer["id"] == timer_id and not timer.get("outcome"):
                            timer.update({"status": "completed", "outcome": params[0], "outcome_required": False})
                elif "UPDATE daily_execution_sheets" in compact and "status='finalised'" in compact:
                    sheet_id = str(params[2])
                    for sheet in sheets:
                        if sheet["id"] == sheet_id:
                            sheet["top_tasks"] = json.loads(params[0])
                            sheet["additional_items"] = json.loads(params[1])
                            sheet["status"] = "finalised"
                            self.rows = [sheet]
                elif "FROM audit_logs" in compact:
                    self.rows = []
                elif "INSERT INTO audit_logs" in compact:
                    self.audit_inserts += 1
                elif "FROM daily_execution_sheets" in compact and "status='finalised'" in compact:
                    self.rows = [row for row in reversed(sheets) if row["status"] == "finalised" and not row.get("completed_at")][:1]

            def fetchall(self):
                return list(self.rows)

            def fetchone(self):
                return self.rows[0] if self.rows else None

        cursor = Cursor()
        now = datetime(2026, 8, 15, 14, 5, tzinfo=timezone.utc)
        first = supabase_backend._finalise_overdue_daily_execution_sheets_locked(
            cursor, "admin-1", date(2026, 8, 16), now_utc=now
        )
        second = supabase_backend._finalise_overdue_daily_execution_sheets_locked(
            cursor, "admin-1", date(2026, 8, 16), now_utc=now
        )

        top = sheets[0]["top_tasks"]
        additional = sheets[0]["additional_items"]
        self.assertEqual("done", top[0]["status"])
        self.assertEqual("skipped", top[1]["status"])
        self.assertEqual("couldnt_finish", top[2]["status"])
        self.assertEqual("couldnt_finish", additional[0]["status"])
        self.assertEqual("couldnt_finish", additional[1]["status"])
        self.assertEqual("", additional[2]["status"])
        self.assertEqual(120, additional[1]["actual_elapsed_seconds"])
        self.assertEqual("finalised", sheets[0]["status"])
        self.assertEqual(["timer-open", "timer-paused"], first["cleared_timer_ids"])
        self.assertEqual("2026-08-15", first["review_reminder"]["sheet_date"])
        self.assertEqual([], second["finalised_dates"])
        self.assertEqual("2026-08-15", second["review_reminder"]["sheet_date"])

    def test_sydney_midnight_and_review_reminder_client_contract(self):
        utc_before = datetime(2026, 8, 15, 13, 59, tzinfo=timezone.utc)
        utc_after = datetime(2026, 8, 15, 14, 1, tzinfo=timezone.utc)
        self.assertEqual(date(2026, 8, 15), utc_before.astimezone(ZoneInfo("Australia/Sydney")).date())
        self.assertEqual(date(2026, 8, 16), utc_after.astimezone(ZoneInfo("Australia/Sydney")).date())

        client = (ROOT / "components" / "daily_planner" / "index.html").read_text(encoding="utf-8")
        self.assertIn("Yesterday was automatically finalised.", client)
        self.assertIn("Complete the review for", client)
        self.assertIn('data-action="complete-overdue-review"', client)
        self.assertIn('data-action="dismiss-review-reminder"', client)
        self.assertIn("sessionStorage.setItem", client)
        self.assertIn("state.pendingReviewFocus = reviewDate", client)
        self.assertIn('String(sheet.status || "").toLowerCase() === "finalised"', client)
        self.assertIn("rolloverTimerIds", client)
        self.assertIn("terminal_timer_ids", client)


if __name__ == "__main__":
    unittest.main()
