import asyncio
import json
import os
from datetime import date, datetime
from pathlib import Path
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

import planning_ai
import daily_planner
import run_migrations
import sports_cave_dashboard
import top_bar_security
from starlette.requests import Request


ROOT = Path(__file__).resolve().parents[1]


class FakeResponse:
    status_code = 200

    def __init__(self, draft):
        self.draft = draft

    def json(self):
        return {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": json.dumps(self.draft)}
                    ],
                }
            ]
        }


class FakeClient:
    def __init__(self, draft):
        self.draft = draft
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse(self.draft)


def valid_daily_draft():
    return {
        "main_outcome": "Launch the approved campaign",
        "mips": [
            {
                "title": "Launch campaign",
                "outcome_required": "Campaign live with QA complete",
                "allocated_minutes": 120,
                "weekly_alignment": "Revenue objective",
            }
        ],
        "supporting_tasks": [],
        "defer_delegate_remove": [],
        "reasoning_summary": ["The launch is the nearest measurable result."],
        "capacity": {
            "available_minutes": 240,
            "planned_minutes": 180,
            "reserve_percentage": 25,
            "warning": "",
        },
    }


def planner_help_request(token, payload):
    body = json.dumps(payload).encode()
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
            "method": "POST",
            "scheme": "http",
            "path": daily_planner.PLANNER_PLANNING_HELP_PATH,
            "raw_path": daily_planner.PLANNER_PLANNING_HELP_PATH.encode(),
            "query_string": b"",
            "headers": [(b"authorization", f"Bearer {token}".encode())],
            "client": ("127.0.0.1", 1),
            "server": ("127.0.0.1", 8501),
        },
        receive,
    )


class PlanningAIContractTests(unittest.TestCase):
    def test_exactly_two_compact_help_buttons_and_no_bootstrap_ai_import(self):
        client = (ROOT / "components" / "daily_planner" / "index.html").read_text(encoding="utf-8")
        planner = (ROOT / "daily_planner.py").read_text(encoding="utf-8")

        self.assertEqual(2, client.count('data-action="open-daily-coach">Daily planning help</button>') + client.count('data-action="open-weekly-coach">Weekly planning help</button>'))
        self.assertIn('<div class="section-title"><h2>Daily plan</h2><span class="rule"></span>', client)
        self.assertIn('const weeklyHelp = \'<button class="button small"', client)
        bootstrap_source = planner[planner.index("def _load_sheet_bundle"):planner.index("async def planner_window")]
        self.assertNotIn("planning_ai", bootstrap_source)
        self.assertNotIn("OPENAI", bootstrap_source)

    def test_responses_api_uses_store_false_and_strict_schema(self):
        client = FakeClient(valid_daily_draft())
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key", "OPENAI_PLANNING_MODEL": "test-model"}, clear=False):
            draft = planning_ai.generate_planning_draft("daily", {"account": {"id": "admin-1"}}, client=client)

        self.assertEqual("Launch the approved campaign", draft["main_outcome"])
        url, kwargs = client.calls[0]
        self.assertEqual("https://api.openai.com/v1/responses", url)
        self.assertFalse(kwargs["json"]["store"])
        self.assertEqual("test-model", kwargs["json"]["model"])
        self.assertTrue(kwargs["json"]["text"]["format"]["strict"])
        self.assertEqual("json_schema", kwargs["json"]["text"]["format"]["type"])

    def test_malformed_or_overloaded_structured_output_is_rejected(self):
        malformed = valid_daily_draft()
        malformed["mips"] = malformed["mips"] * 4
        with self.assertRaises(planning_ai.PlanningAIError):
            planning_ai.validate_draft("daily", malformed)

        weekly = {
            "theme": "Launch",
            "quote": {"text": "Do the work", "author": ""},
            "objectives": [{"title": "Launch", "measurable_target": "Three tests", "alignment": "Growth", "tactics": [{"action": "Test", "due_day": "Monday", "estimated_minutes": 30}]}],
            "defer_delegate_remove": [],
            "capacity": {"available_minutes": 600, "planned_minutes": 30, "assessment": "Underloaded"},
            "expected_execution_score": 90,
            "influencing_facts": [],
        }
        with self.assertRaises(planning_ai.PlanningAIError):
            planning_ai.validate_draft("weekly", weekly)

    def test_questions_are_one_at_a_time_and_missing_credentials_are_safe(self):
        self.assertEqual("available_hours", planning_ai.next_question("daily", {})["key"])
        answers = {key: "known" for key, _label in planning_ai.DAILY_QUESTIONS}
        self.assertIsNone(planning_ai.next_question("daily", answers))
        with patch.dict(os.environ, {"OPENAI_API_KEY": "", "OPENAI_PLANNING_MODEL": ""}, clear=False):
            with self.assertRaisesRegex(planning_ai.PlanningAIError, "not configured"):
                planning_ai.generate_planning_draft("daily", {})

    def test_saved_answers_remove_only_the_questions_already_known(self):
        context = {
            "today_plan": {"fixed_event": "Courier at 3", "main_outcome": "Launch"},
            "yesterday_review": {"blockers": "Avoided pricing"},
            "current_week": {},
        }
        questions = planning_ai.questions_for_context("daily", context, {})
        self.assertEqual(
            ["available_hours", "remove_work"],
            [row["key"] for row in questions],
        )

    def test_questions_endpoint_never_calls_the_model_or_writes_a_plan(self):
        user = {
            "id": "account-1",
            "display_name": "Nathan",
            "role": "admin",
            "is_active": True,
            "account_status": "active",
        }
        token = top_bar_security.create_top_bar_token(
            user, can_manage_daily_planner=True, now=1_786_742_400, seconds=3600
        )
        request = planner_help_request(
            token,
            {"kind": "daily", "action": "questions", "target_date": "2026-08-16"},
        )
        with patch("top_bar_security.time.time", return_value=1_786_742_500), patch.object(
            sports_cave_dashboard, "can_manage_daily_planner", return_value=True
        ), patch.object(
            planning_ai, "build_planning_context", return_value={}
        ), patch.object(
            planning_ai, "generate_planning_draft"
        ) as generate, patch.object(
            sports_cave_dashboard, "save_daily_execution_plan"
        ) as save:
            response = asyncio.run(daily_planner.planner_planning_help(request))

        self.assertEqual(200, response.status_code)
        self.assertFalse(generate.called)
        self.assertFalse(save.called)
        self.assertIsNone(json.loads(response.body)["draft"])

    def test_context_is_scoped_to_authenticated_account(self):
        calls = []

        class Backend:
            def list_daily_execution_sheets_for_reporting(self, user_id, start, end, *, limit):
                calls.append(("sheets", user_id, start, end, limit))
                return []

            def list_daily_execution_timers_for_sheets(self, user_id, sheet_ids):
                calls.append(("timers", user_id, tuple(sheet_ids)))
                return []

            def list_daily_planner_cycle_archive(self, user_id, anchor):
                calls.append(("archive", user_id, anchor))
                return {"plans": []}

        user = {"id": "account-1", "display_name": "Nathan", "role": "admin", "is_active": True, "account_status": "active"}
        week = {"cycle": {"id": "cycle-1", "overall_objective": "Grow"}, "plan": {}, "week_number": 2}
        with patch.object(sports_cave_dashboard, "load_daily_planner_week_plan", return_value=week), patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=Backend()), patch.object(sports_cave_dashboard, "list_tasks", return_value=[]), patch.object(sports_cave_dashboard, "load_calendar_events", return_value=[]), patch.object(sports_cave_dashboard, "build_home_weekly_work_snapshot", return_value={"metrics": {}, "completed_work": []}):
            context = planning_ai.build_planning_context(user, "daily", {"available_hours": "4"}, now=datetime(2026, 8, 16, 1, tzinfo=ZoneInfo("Australia/Sydney")))

        self.assertEqual("Nathan", context["account"]["display_name"])
        self.assertNotIn("id", context["account"])
        self.assertTrue(all(call[1] == "account-1" for call in calls))
        self.assertNotIn("api_key", json.dumps(context).casefold())

    def test_context_uses_selected_next_week_without_changing_account_scope(self):
        anchors = []

        class Backend:
            def list_daily_execution_sheets_for_reporting(self, user_id, start, end, *, limit):
                return []

            def list_daily_planner_cycle_archive(self, user_id, anchor):
                anchors.append((user_id, anchor))
                return {"plans": []}

        def week_plan(_user, anchor):
            anchors.append(("week", anchor))
            return {"cycle": {}, "plan": {}, "week_number": 0}

        user = {"id": "account-1", "display_name": "Nathan"}
        with patch.object(sports_cave_dashboard, "load_daily_planner_week_plan", side_effect=week_plan), patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=Backend()), patch.object(sports_cave_dashboard, "list_tasks", return_value=[]), patch.object(sports_cave_dashboard, "load_calendar_events", return_value=[]), patch.object(sports_cave_dashboard, "build_home_weekly_work_snapshot", return_value={"metrics": {}, "completed_work": []}), patch.object(planning_ai, "_saved_business_metrics", return_value={}):
            context = planning_ai.build_planning_context(
                user,
                "weekly",
                {},
                now=datetime(2026, 8, 16, 1, tzinfo=ZoneInfo("Australia/Sydney")),
                target_date=date(2026, 8, 17),
            )

        self.assertEqual("2026-08-17", context["planning_date_sydney"])
        self.assertEqual(["2026-08-17", "2026-08-23"], context["current_week"]["range"])
        self.assertIn(("week", date(2026, 8, 17)), anchors)
        self.assertIn(("account-1", date(2026, 8, 17)), anchors)

    def test_visible_influencing_facts_are_derived_from_saved_context(self):
        client = FakeClient(valid_daily_draft())
        context = {
            "cycle": {"week_number": 3, "overall_objective": "Launch AU range"},
            "current_week": {"theme": "Launch", "objectives": [{"title": "Three tests"}]},
            "today_plan": {"tasks": ["QA launch"]},
            "recent_task_outcomes": {"completed": 4, "did_not_finish": 1, "skipped": 0},
        }
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key", "OPENAI_PLANNING_MODEL": "test-model"}, clear=False):
            draft = planning_ai.generate_planning_draft("daily", context, client=client)
        self.assertIn("12-week cycle week 3", draft["influencing_facts"][0])
        self.assertNotIn("influencing_facts", client.calls[0][1]["json"]["text"]["format"]["schema"]["properties"])


class WeeklyReportingContractTests(unittest.TestCase):
    def test_tactic_execution_score_excludes_blanks(self):
        plan = {"objectives": [{"tactics": [{"action": "A", "status": "completed"}, {"action": "B", "status": "open"}, {"action": "", "status": "completed"}]}]}
        summary = sports_cave_dashboard.weekly_tactic_execution_summary(plan)
        self.assertEqual(2, summary["total"])
        self.assertEqual(50.0, summary["percentage"])

    def test_cycle_progress_has_twelve_sydney_monday_sunday_rows(self):
        class Backend:
            def list_daily_planner_cycle_archive(self, user_id, anchor):
                return {"cycle": {"id": "cycle", "start_date": date(2026, 8, 10), "name": "Q3"}, "plans": [], "monthly_reviews": [], "query_count": 1}

            def list_daily_execution_sheets_for_reporting(self, user_id, start, end, *, limit):
                return []

            def list_daily_execution_timers_for_sheets(self, user_id, ids):
                return []

        user = {"id": "account-1", "role": "admin", "is_active": True, "account_status": "active", "page_permissions": []}
        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=Backend()), patch.object(sports_cave_dashboard.os_accounts, "can_access_reporting", return_value=True):
            result = sports_cave_dashboard.load_twelve_week_progress(user, date(2026, 8, 16))

        self.assertEqual(12, len(result["weeks"]))
        self.assertEqual("2026-08-10", result["weeks"][0]["week_start"])
        self.assertEqual("2026-08-16", result["weeks"][0]["week_end"])
        self.assertEqual("2026-10-26", result["weeks"][-1]["week_start"])

    def test_staff_week_counts_are_deduplicated_upstream_and_role_scoped(self):
        snapshot = {
            "team": [{"staff_id": "worker-1", "staff": "Reina", "last_activity": None}],
            "completed_work": [
                {"staff_id": "worker-1", "staff": "Reina", "timestamp": datetime(2026, 8, 11, 1, tzinfo=ZoneInfo("UTC")), "work": "Upload", "area": "Products", "status": "Completed", "row_id": "activity:key-1"}
            ],
        }
        with patch.object(sports_cave_dashboard, "build_home_weekly_work_snapshot", return_value=snapshot):
            result = sports_cave_dashboard.build_reporting_staff_week_snapshot({}, date(2026, 8, 12))
        self.assertEqual(1, result["staff_rows"][0]["Weekly total"])
        self.assertEqual("Reina", result["staff_rows"][0]["Account"])

    def test_reporting_tables_are_paginated_and_detail_driven(self):
        source = (ROOT / "reporting_page.py").read_text(encoding="utf-8")
        self.assertIn("ACTIVITY_PAGE_SIZE = 25", source)
        self.assertIn("HISTORY_SHEET_PAGE_SIZE = 40", source)
        self.assertIn("list_daily_execution_history_page", source)
        self.assertIn("list_activity_entries_page", source)
        self.assertNotIn("limit=None", source)
        self.assertIn('"Twelve Week Progress"', source)
        self.assertIn('st.markdown("#### Monthly Review")', source)
        self.assertIn('"Staff Weekly Activity"', source)
        self.assertIn('"Open day details"', source)

    def test_daily_history_paginates_database_sheets_without_n_plus_one(self):
        calls = []

        class Backend:
            def list_daily_execution_sheets_for_reporting(self, user_id, start, end, *, limit, offset):
                calls.append(("sheets", user_id, limit, offset))
                return [
                    {"id": f"sheet-{index}", "sheet_date": "2026-08-16", "user_id": "account-1", "user_name": "Nathan", "top_tasks": [], "additional_items": []}
                    for index in range(41)
                ]

            def list_daily_execution_timers_for_sheets(self, user_id, sheet_ids):
                calls.append(("timers", user_id, len(sheet_ids)))
                return []

        user = {"id": "account-1", "role": "admin"}
        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=Backend()), patch.object(sports_cave_dashboard.os_accounts, "can_access_reporting", return_value=True):
            result = sports_cave_dashboard.list_daily_execution_history_page(
                user, date(2026, 8, 1), date(2026, 8, 31), page=2, page_size=40
            )
        self.assertEqual(("sheets", "", 41, 40), calls[0])
        self.assertEqual(("timers", "", 40), calls[1])
        self.assertTrue(result["has_next"])
        self.assertEqual(2, result["query_count"])

    def test_week_plan_migration_is_additive_and_runner_accepts_referential_actions(self):
        migration = (ROOT / "migrations" / "20260816_daily_planner_week_plans.sql").read_text(encoding="utf-8")
        self.assertTrue(run_migrations.safe_migration_sql(migration))
        self.assertIn("UNIQUE (user_id, week_start)", migration)
        self.assertIn("version INTEGER NOT NULL DEFAULT 1", migration)
        self.assertNotIn("CREATE TABLE IF NOT EXISTS", (ROOT / "planning_ai.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
