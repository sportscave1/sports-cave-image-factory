import asyncio
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from starlette.requests import Request

import daily_planner
import sports_cave_dashboard
import supabase_backend
import top_bar_security


ROOT = Path(__file__).resolve().parents[1]
CLIENT_PATH = ROOT / "components" / "daily_planner" / "index.html"
USER = {
    "id": "plan-tomorrow-admin",
    "username": "nathan",
    "display_name": "Nathan",
    "role": "admin",
}


def mutation_request(token, payload):
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
            "path": daily_planner.PLANNER_MUTATION_PATH,
            "raw_path": daily_planner.PLANNER_MUTATION_PATH.encode(),
            "query_string": b"",
            "headers": [(b"authorization", f"Bearer {token}".encode())],
            "client": ("127.0.0.1", 1),
            "server": ("127.0.0.1", 8501),
        },
        receive,
    )


class DailyPlannerPlanTomorrowTests(unittest.TestCase):
    def token(self):
        return top_bar_security.create_top_bar_token(
            USER,
            can_manage_daily_planner=True,
            now=1_786_828_800,
            seconds=3600,
        )

    def save(self, top_tasks):
        payload = {
            "action": "save_sheet",
            "work_date": "2026-08-17",
            "top_tasks": top_tasks,
            "additional_items": [{"task": "", "details": "", "time_blocked": ""}],
            "planning_data": {"main_outcome": "Launch the refresh"},
        }
        saved = {
            "id": "sheet-17",
            "sheet_date": "2026-08-17",
            "status": "planned",
            "top_tasks": [row for row in top_tasks if str(row.get("task") or "").strip()],
            "additional_items": [],
            "planning_data": payload["planning_data"],
        }
        request = mutation_request(self.token(), payload)
        with patch("top_bar_security.time.time", return_value=1_786_828_900), patch.object(
            sports_cave_dashboard, "finalise_overdue_daily_planner_days", return_value={}
        ), patch.object(
            sports_cave_dashboard, "save_daily_execution_plan", return_value=saved
        ) as save:
            response = asyncio.run(daily_planner.planner_mutation(request))
        return response, save

    def test_one_major_task_saves_and_blank_slots_are_not_sent_to_storage(self):
        response, save = self.save(
            [
                {"task": "Refresh ads", "why": "Launch approved creatives", "time_blocked": "4"},
                {"task": "", "why": "", "time_blocked": ""},
                {"task": "", "why": "", "time_blocked": ""},
            ]
        )

        body = json.loads(response.body)
        self.assertEqual(200, response.status_code)
        self.assertEqual("sheet-17", body["result"]["id"])
        saved_tasks = save.call_args.args[3]
        self.assertEqual(1, len(saved_tasks))
        self.assertEqual("Refresh ads", saved_tasks[0]["task"])

    def test_two_and_three_major_task_plans_save(self):
        for count in (2, 3):
            with self.subTest(count=count):
                tasks = [
                    {"task": f"Task {index + 1}", "why": "Outcome", "time_blocked": "1"}
                    for index in range(count)
                ]
                tasks.extend({"task": "", "why": "", "time_blocked": ""} for _ in range(3 - count))
                response, save = self.save(tasks)

                self.assertEqual(200, response.status_code)
                self.assertEqual(count, len(save.call_args.args[3]))

    def test_partially_filled_row_requires_its_own_task_name(self):
        response, save = self.save(
            [
                {"task": "Refresh ads", "why": "Outcome", "time_blocked": "4"},
                {"task": "", "why": "", "time_blocked": "2"},
                {"task": "", "why": "", "time_blocked": ""},
            ]
        )

        body = json.loads(response.body)
        self.assertEqual(400, response.status_code)
        self.assertIn("task name", body["error"])
        save.assert_not_called()

    def test_save_normalizer_excludes_blank_slots_but_read_normalizer_restores_editor_slots(self):
        persisted = sports_cave_dashboard._normalise_top_tasks_for_save(
            [
                {"task": "Refresh ads", "why": "Outcome", "time_blocked": "4"},
                {"task": "", "why": "", "time_blocked": ""},
                {"task": "", "why": "", "time_blocked": ""},
            ]
        )
        editor_rows = sports_cave_dashboard._normalise_top_tasks(persisted)

        self.assertEqual(1, len(persisted))
        self.assertEqual(3, len(editor_rows))
        self.assertEqual("Refresh ads", editor_rows[0]["task"])
        self.assertEqual("", editor_rows[1]["task"])
        self.assertEqual("", editor_rows[2]["task"])
        self.assertEqual(1, len(sports_cave_dashboard.daily_execution_task_rows(
            {"id": "sheet-17", "sheet_date": "2026-08-17", "top_tasks": persisted}, []
        )))

    def test_client_save_lifecycle_is_click_only_and_always_released(self):
        source = CLIENT_PATH.read_text(encoding="utf-8")
        action_block = source[
            source.index('if (action === "plan-tomorrow")') :
            source.index('if (action === "reopen-active")')
        ]
        save_block = source[
            source.index("const saveSheet = async () =>") :
            source.index("\n    const timerAction", source.index("const saveSheet = async () =>"))
        ]

        self.assertIn("return loadPlanner", action_block)
        self.assertNotIn("saveSheet", action_block)
        self.assertIn("if (state.saving) return false", save_block)
        self.assertIn("const requestId = ++state.saveRequestId", save_block)
        self.assertIn("saveSignature === state.lastSaveSignature", save_block)
        self.assertIn("state.lastSaveSignature = saveSignature", save_block)
        self.assertIn("finally", save_block)
        self.assertIn("state.saving = false", save_block)
        self.assertIn("state.saveController = null", save_block)
        self.assertIn("clearTimeout(timeout)", save_block)
        self.assertIn("controller.abort()", save_block)
        self.assertIn("state.saveError", save_block)
        self.assertNotIn("await loadPlanner", save_block)

    def test_client_applies_authoritative_sheet_and_rejects_stale_date_response(self):
        source = CLIENT_PATH.read_text(encoding="utf-8")
        save_block = source[
            source.index("const saveSheet = async () =>") :
            source.index("\n    const timerAction", source.index("const saveSheet = async () =>"))
        ]

        self.assertIn('targetDate !== String(state.bundle?.work_date || "")', save_block)
        self.assertIn("state.bundle = {...state.bundle, sheet:savedSheet}", save_block)
        self.assertIn("state.draft = normalDraft(savedSheet)", save_block)
        self.assertIn('showToast("Plan saved."', save_block)
        self.assertIn('data-action="retry-save"', source)
        self.assertIn('state.saving ? "Saving..." : saveLabel', source)
        self.assertIn('bundle.work_date === bundle.today ? "Save today\'s plan" : "Save plan"', source)

    def test_task_fields_have_stable_unique_identity_and_autofill_isolation(self):
        source = CLIENT_PATH.read_text(encoding="utf-8")
        task_row = source[
            source.index("const taskRow =") : source.index("\n    const activeStrip")
        ]

        self.assertIn("_client_key", source)
        self.assertIn("const fieldIdentity", source)
        self.assertIn('name="${identity}"', source)
        self.assertIn('autocomplete="off"', source)
        self.assertIn('fieldAttributes(task,type,"task")', task_row)
        self.assertIn('fieldAttributes(task,type,"time-blocked")', task_row)
        self.assertIn("delete payload._client_key", source)

    def test_identical_row_locked_backend_retry_does_not_write_or_duplicate_audit(self):
        top_tasks = sports_cave_dashboard._normalise_top_tasks_for_save(
            [{"task": "Refresh ads", "why": "Outcome", "time_blocked": "4"}]
        )
        planning_data = {"main_outcome": "Launch the refresh", "planned_for": "2026-08-17"}
        existing = {
            "id": "sheet-17",
            "user_id": USER["id"],
            "user_name": "Nathan",
            "sheet_date": "2026-08-17",
            "timezone": "Australia/Sydney",
            "status": "planned",
            "top_tasks": top_tasks,
            "additional_items": [],
            "planning_data": planning_data,
        }

        class Cursor:
            def __init__(self):
                self.statements = []
                self.row = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def execute(self, sql, _params=()):
                compact = " ".join(sql.split())
                self.statements.append(compact)
                self.row = existing if compact.startswith("SELECT * FROM daily_execution_sheets") else None

            def fetchone(self):
                return self.row

        class Connection:
            def __init__(self):
                self.cursor_instance = Cursor()
                self.commits = 0

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def cursor(self):
                return self.cursor_instance

            def commit(self):
                self.commits += 1

        connection = Connection()
        with patch.object(supabase_backend, "ensure_dashboard_schema"), patch.object(
            supabase_backend, "connect", return_value=connection
        ):
            result = supabase_backend.save_daily_execution_plan(
                user_id=USER["id"],
                user_name="Nathan",
                sheet_date="2026-08-17",
                timezone_name="Australia/Sydney",
                top_tasks=top_tasks,
                additional_items=[],
                planning_data=planning_data,
            )

        statements = connection.cursor_instance.statements
        self.assertEqual("sheet-17", result["id"])
        self.assertEqual(1, connection.commits)
        self.assertFalse(any(statement.startswith("INSERT INTO daily_execution_sheets") for statement in statements))
        self.assertFalse(any(statement.startswith("INSERT INTO audit_logs") for statement in statements))


if __name__ == "__main__":
    unittest.main()
