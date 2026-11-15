import asyncio
import json
from datetime import date
from pathlib import Path
import unittest
from unittest.mock import patch

from starlette.requests import Request

import daily_planner
import run_migrations
import sports_cave_dashboard
import supabase_backend
import top_bar_security


ROOT = Path(__file__).resolve().parents[1]
USER = {
    "id": "planner-bootstrap-admin",
    "username": "nathan",
    "display_name": "Nathan",
    "role": "admin",
    "is_active": True,
    "account_status": "active",
    "page_permissions": [],
}


def planner_request(token="", query_string=b"date=2026-08-16"):
    headers = []
    if token:
        headers.append((b"authorization", f"Bearer {token}".encode()))

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": daily_planner.PLANNER_BOOTSTRAP_PATH,
            "raw_path": daily_planner.PLANNER_BOOTSTRAP_PATH.encode(),
            "query_string": query_string,
            "headers": headers,
            "client": ("127.0.0.1", 1),
            "server": ("127.0.0.1", 8501),
        },
        receive,
    )


def saved_bundle():
    sheet = {
        "id": "sheet-saved",
        "sheet_date": "2026-08-16",
        "status": "active",
        "top_tasks": [{"task": "Pack orders", "status": "", "outcome": ""}],
        "additional_items": [],
        "review_data": {"lesson": "Keep the dispatch block protected."},
    }
    return {
        "work_date": "2026-08-16",
        "today": "2026-08-16",
        "timezone": "Australia/Sydney",
        "sheet": sheet,
        "source_sheet": {"id": "sheet-yesterday", "sheet_date": "2026-08-15"},
        "tasks": [{"task": "Pack orders", "status": "Open"}],
        "active_timer": {},
        "events": [],
        "rollover": {"finalised_dates": ["2026-08-15"]},
        "review_reminder": {},
        "server_now": "2026-08-16T04:00:00+00:00",
        "performance": {"planner_data_ms": 4.0, "initial_api_calls": 1},
    }


class DailyPlannerBootstrapStorageTests(unittest.TestCase):
    def token(self):
        return top_bar_security.create_top_bar_token(
            USER,
            can_manage_daily_planner=True,
            now=1_786_742_400,
            seconds=3600,
        )

    def test_authenticated_bootstrap_returns_authoritative_saved_planner_shape(self):
        request = planner_request(self.token())
        with patch("top_bar_security.time.time", return_value=1_786_742_500), patch.object(
            daily_planner, "_load_sheet_bundle", return_value=saved_bundle()
        ):
            response = asyncio.run(daily_planner.planner_bootstrap(request))

        payload = json.loads(response.body)
        self.assertEqual(200, response.status_code)
        self.assertTrue(payload["ok"])
        self.assertEqual("planner-bootstrap-admin", payload["user"]["id"])
        self.assertEqual("sheet-saved", payload["sheet"]["id"])
        self.assertEqual("Pack orders", payload["tasks"][0]["task"])
        self.assertEqual("2026-08-15", payload["rollover"]["finalised_dates"][0])

    def test_standalone_bootstrap_rejects_missing_or_unapproved_session(self):
        response = asyncio.run(daily_planner.planner_bootstrap(planner_request()))

        self.assertEqual(403, response.status_code)
        self.assertEqual("Access not approved.", json.loads(response.body)["error"])

    def test_bootstrap_runs_rollover_before_loading_saved_date_bundle(self):
        calls = []

        class Backend:
            def load_daily_planner_date_bundle(self, user_id, selected_date):
                calls.append(("load", user_id, selected_date))
                return {
                    "sheet": saved_bundle()["sheet"],
                    "source_sheet": saved_bundle()["source_sheet"],
                    "timers": [],
                    "active_timer": {},
                    "query_count": 1,
                }

        def rollover(_user, local_today):
            calls.append(("rollover", local_today.isoformat()))
            return {"finalised_dates": ["2026-08-15"], "review_reminder": {}}

        with patch.object(
            sports_cave_dashboard, "finalise_overdue_daily_planner_days", side_effect=rollover
        ), patch.object(
            sports_cave_dashboard, "reconcile_daily_planner_timers", return_value=[]
        ), patch.object(
            sports_cave_dashboard, "get_supabase_backend", return_value=Backend()
        ), patch.object(daily_planner, "_task_rows", return_value=saved_bundle()["tasks"]):
            payload = daily_planner._load_sheet_bundle(USER, date(2026, 8, 16))

        self.assertEqual("rollover", calls[0][0])
        self.assertEqual("load", calls[1][0])
        self.assertEqual("sheet-saved", payload["sheet"]["id"])
        self.assertEqual(["2026-08-15"], payload["rollover"]["finalised_dates"])

    def test_missing_outcome_migration_is_reported_by_bootstrap(self):
        class Diagnostic:
            column_name = "completion_method"
            constraint_name = ""

        class MissingColumnError(Exception):
            sqlstate = "42703"
            diag = Diagnostic()

        class Backend:
            def finalise_overdue_daily_execution_sheets(self, *_args, **_kwargs):
                raise MissingColumnError('column "completion_method" does not exist')

        request = planner_request(self.token())
        with patch("top_bar_security.time.time", return_value=1_786_742_500), patch.object(
            sports_cave_dashboard, "get_supabase_backend", return_value=Backend()
        ), patch.object(daily_planner.LOGGER, "exception"):
            response = asyncio.run(daily_planner.planner_bootstrap(request))

        payload = json.loads(response.body)
        self.assertEqual(503, response.status_code)
        self.assertEqual("daily_planner_outcome_migration_required", payload["error_code"])
        self.assertIn("20260815_daily_execution_task_outcomes.sql", payload["error"])
        self.assertTrue(payload["retryable"])
        self.assertNotIn("sheet", payload)

    def test_older_timer_schema_error_names_its_required_migration(self):
        class MissingTableError(Exception):
            sqlstate = "42P01"

        message = sports_cave_dashboard._storage_error(
            MissingTableError('relation "daily_execution_task_timers" does not exist')
        )

        self.assertIn("20260815_daily_execution_task_timers.sql", message)
        self.assertNotIn("Dashboard saving is unavailable", message)

    def test_retry_makes_fresh_bootstrap_and_failure_never_returns_blank_data(self):
        request_one = planner_request(self.token())
        request_two = planner_request(self.token())
        unavailable = sports_cave_dashboard.DashboardStorageError(
            "Dashboard saving is unavailable right now."
        )
        with patch("top_bar_security.time.time", return_value=1_786_742_500), patch.object(
            daily_planner, "_load_sheet_bundle", side_effect=[unavailable, saved_bundle()]
        ) as load, patch.object(daily_planner.LOGGER, "exception"):
            failed = asyncio.run(daily_planner.planner_bootstrap(request_one))
            retried = asyncio.run(daily_planner.planner_bootstrap(request_two))

        failed_payload = json.loads(failed.body)
        retried_payload = json.loads(retried.body)
        self.assertEqual(2, load.call_count)
        self.assertEqual(503, failed.status_code)
        self.assertNotIn("sheet", failed_payload)
        self.assertIn("Retry now", failed_payload["error"])
        self.assertEqual(200, retried.status_code)
        self.assertEqual("sheet-saved", retried_payload["sheet"]["id"])

    def test_client_keeps_saved_state_on_refresh_failure_and_retry_is_fresh(self):
        source = (ROOT / "components" / "daily_planner" / "index.html").read_text(
            encoding="utf-8"
        )
        request_index = source.index("const payload = await requestJson(`/api/os/daily-planner/bootstrap")
        assign_index = source.index("state.bundle = payload", request_index)

        self.assertLess(request_index, assign_index)
        self.assertIn("if (preserveView)", source)
        self.assertIn('if (action === "retry") return loadPlanner', source)
        self.assertNotIn("state.bundle = {}", source[request_index:assign_index])
        self.assertIn("state.historyLoaded = false", source)
        self.assertIn("state.weeklyLoaded = false", source)

    def test_migration_runner_accepts_the_required_additive_outcome_migration(self):
        filename = supabase_backend.DAILY_EXECUTION_OUTCOME_MIGRATION
        migration = ROOT / "migrations" / filename

        self.assertTrue(migration.exists())
        sql = migration.read_text(encoding="utf-8")
        self.assertIn("ADD COLUMN IF NOT EXISTS", sql)
        self.assertTrue(run_migrations.safe_migration_sql(sql))


if __name__ == "__main__":
    unittest.main()
