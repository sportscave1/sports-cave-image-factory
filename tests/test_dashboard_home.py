from datetime import date, datetime, timezone
from pathlib import Path
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

import sc_auth
import os_accounts
import sports_cave_dashboard
import sports_sales_calendar


ROOT = Path(__file__).resolve().parents[1]


class FakeDashboardBackend:
    def __init__(self):
        self.tasks = []
        self.activity_rows = []
        self.activity_calls = []
        self.task_status_calls = []
        self.edition_products = []
        self.edition_product_calls = []
        self.daily_sheets = []
        self.daily_calls = []

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

    def create_dashboard_task(self, title, section, *, metadata=None, actor="sports_cave_os"):
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

    def complete_dashboard_task(
        self,
        task_id,
        *,
        completed_by="",
        metadata=None,
        actor="sports_cave_os",
    ):
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

    def get_daily_execution_sheet(self, user_id, sheet_date):
        self.daily_calls.append(("get", user_id, sheet_date))
        return next(
            (
                dict(sheet)
                for sheet in self.daily_sheets
                if sheet.get("user_id") == user_id and sheet.get("sheet_date") == sheet_date
            ),
            {},
        )

    def create_daily_execution_sheet(self, *, user_id, user_name, sheet_date, timezone_name, actor="sports_cave_os"):
        existing = self.get_daily_execution_sheet(user_id, sheet_date)
        if existing:
            return existing
        sheet = {
            "id": f"sheet-{len(self.daily_sheets) + 1}",
            "user_id": user_id,
            "user_name": user_name,
            "sheet_date": sheet_date,
            "day_name": "Tuesday",
            "timezone": timezone_name,
            "status": "active",
            "top_tasks": [
                {"task": "", "why": "", "time_blocked": "", "completed": False, "status": ""},
                {"task": "", "why": "", "time_blocked": "", "completed": False, "status": ""},
                {"task": "", "why": "", "time_blocked": "", "completed": False, "status": ""},
            ],
            "additional_items": [],
            "no_grey_zone": {},
            "ratings": {},
            "daily_summary": "",
            "tomorrow_intention": "",
            "generated_prompt": "",
            "created_at": "2026-07-21T00:00:00+00:00",
            "updated_at": "2026-07-21T00:00:00+00:00",
        }
        self.daily_sheets.append(sheet)
        self._activity_row("daily_execution_created", f"Daily Execution sheet created: {sheet_date}")
        self.activity_rows[0]["actor"] = actor
        return dict(sheet)

    def update_daily_execution_top_tasks(self, sheet_id, top_tasks, additional_items=None):
        for sheet in self.daily_sheets:
            if sheet["id"] == sheet_id:
                sheet["top_tasks"] = top_tasks
                if additional_items is not None:
                    sheet["additional_items"] = additional_items
                return dict(sheet)
        return {}

    def set_daily_execution_mip_completed(self, sheet_id, index, completed):
        for sheet in self.daily_sheets:
            if sheet["id"] == sheet_id:
                sheet["top_tasks"][index]["completed"] = completed
                sheet["top_tasks"][index]["status"] = "done" if completed else ""
                self._activity_row("daily_execution_mip_completed", f"Daily task completed: {sheet['top_tasks'][index]['task']}")
                return dict(sheet)
        return {}

    def complete_daily_execution_review(self, sheet_id, review_payload, *, actor="sports_cave_os"):
        for sheet in self.daily_sheets:
            if sheet["id"] == sheet_id:
                sheet["status"] = "completed"
                sheet["no_grey_zone"] = review_payload.get("no_grey_zone") or {}
                sheet["ratings"] = review_payload.get("ratings") or {}
                if "additional_items" in review_payload:
                    sheet["additional_items"] = review_payload.get("additional_items") or []
                sheet["daily_summary"] = review_payload.get("daily_summary") or ""
                sheet["tomorrow_intention"] = review_payload.get("tomorrow_intention") or ""
                sheet["completed_at"] = "2026-07-21T09:00:00+00:00"
                self._activity_row("daily_execution_completed", f"Daily Review completed: {sheet['sheet_date']}")
                self.activity_rows[0]["actor"] = actor
                return dict(sheet)
        return {}

    def update_daily_execution_prompt(self, sheet_id, prompt):
        for sheet in self.daily_sheets:
            if sheet["id"] == sheet_id:
                sheet["generated_prompt"] = prompt
                return dict(sheet)
        return {}

    def list_daily_execution_sheets(self, user_id, start_date, end_date, *, limit=10):
        return [
            dict(sheet)
            for sheet in self.daily_sheets
            if sheet.get("user_id") == user_id and start_date <= sheet.get("sheet_date") <= end_date
        ][:limit]


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

    def test_new_design_completion_creates_upload_task_with_mockup_choice(self):
        backend = FakeDashboardBackend()

        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=backend):
            task = sports_cave_dashboard.add_task(
                "Create New Supercars Design",
                sports_cave_dashboard.DESIGN_TASK_GROUP,
            )
            result = sports_cave_dashboard.complete_design_task_for_upload(
                task["id"],
                task["text"],
                "All mockups",
            )
            state = sports_cave_dashboard.load_dashboard_state(include_activity=False)

        self.assertEqual(result["completed"]["status"], "complete")
        self.assertEqual(result["upload_task"]["section"], sports_cave_dashboard.UPLOAD_TASK_GROUP)
        self.assertEqual(result["upload_task"]["text"], "Create New Supercars Design (all mockups)")
        self.assertEqual([task["text"] for task in state["tasks"]], ["Create New Supercars Design (all mockups)"])
        self.assertEqual([task["section"] for task in state["tasks"]], [sports_cave_dashboard.UPLOAD_TASK_GROUP])
        self.assertEqual(backend.activity_rows[1]["reason"], "Task completed: Create New Supercars Design")

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

    def test_home_activity_log_excludes_automatic_backend_events(self):
        backend = FakeDashboardBackend()
        backend.activity_rows = [
            {
                "id": 1,
                "event_type": "shopify_product_metafield_mirror",
                "reason": "Edition Ops Shopify metafield mirror",
                "source": "edition_ops",
                "actor": "edition_ops",
                "created_at": "2026-07-21T03:00:00+00:00",
            },
            {
                "id": 2,
                "event_type": "edition_order_auto_allocation",
                "reason": "Auto allocation during Shopify order sync.",
                "source": "supabase_ledger",
                "actor": "sports_cave_os_sync",
                "created_at": "2026-07-21T02:00:00+00:00",
            },
            {
                "id": 3,
                "event_type": "task_added",
                "reason": "Task added: Create New NASCAR Design",
                "source": "Dashboard",
                "actor": "nathan",
                "created_at": "2026-07-21T01:00:00+00:00",
                "new_value": {
                    "message": "Task added: Create New NASCAR Design",
                    "page": "Dashboard",
                    "action_type": "task_added",
                    "metadata": {"title": "Create New NASCAR Design"},
                },
            },
            {
                "id": 4,
                "event_type": "mockup_generated",
                "reason": "Mockup made: Veery Elleegant 2021 Melbourne Cup",
                "source": "Mockups",
                "actor": "va",
                "created_at": "2026-07-21T00:00:00+00:00",
            },
        ]
        now = datetime(2026, 7, 21, 10, 30, tzinfo=timezone.utc)

        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=backend):
            entries = sports_cave_dashboard.list_activity_entries(
                sports_cave_dashboard.ACTIVITY_VIEW_ALL_TIME,
                now,
            )

        messages = [entry["message"] for entry in entries]
        self.assertEqual(
            messages,
            [
                "Task added: Create New NASCAR Design",
                "Mockup made: Veery Elleegant 2021 Melbourne Cup",
            ],
        )
        combined = " ".join(messages).casefold()
        self.assertNotIn("metafield", combined)
        self.assertNotIn("auto allocation", combined)
        self.assertNotIn("webhook", combined)

    def test_home_activity_log_hides_structured_system_rows(self):
        self.assertFalse(
            sports_cave_dashboard.home_activity_row_is_visible(
                {
                    "event_type": "product_updated",
                    "reason": "Shopify product metafield updated",
                    "source": "Edition Ops",
                    "new_value": {
                        "message": "Shopify product metafield updated",
                        "metadata": {"is_system": True, "actor_type": "system"},
                    },
                }
            )
        )
        self.assertTrue(
            sports_cave_dashboard.home_activity_row_is_visible(
                {
                    "event_type": "edition_product_updated",
                    "reason": "Edition updated: The Final Crown",
                    "source": "Edition Ops",
                    "actor": "va",
                }
            )
        )

    def test_daily_execution_sheet_creation_logs_with_actor(self):
        backend = FakeDashboardBackend()
        user = {
            "id": "admin-1",
            "display_name": "Nathan",
            "role": "admin",
            "timezone": "Australia/Sydney",
        }

        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=backend), patch(
            "activity_log.get_activity_actor",
            return_value="Nathan",
        ):
            sheet = sports_cave_dashboard.create_daily_execution_sheet(
                user,
                date(2026, 7, 21),
                "Australia/Sydney",
            )

        self.assertEqual(sheet["sheet_date"], "2026-07-21")
        self.assertEqual(sheet["user_name"], "Nathan")
        self.assertEqual(sheet["timezone"], "Australia/Sydney")
        self.assertEqual(backend.activity_rows[0]["event_type"], "daily_execution_created")
        self.assertEqual(backend.activity_rows[0]["actor"], "Nathan")

    def test_daily_execution_mip_checklist_save_and_complete(self):
        backend = FakeDashboardBackend()
        user = {"id": "admin-1", "display_name": "Nathan"}

        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=backend):
            sheet = sports_cave_dashboard.create_daily_execution_sheet(user, date(2026, 7, 21), "Australia/Sydney")
            sheet = sports_cave_dashboard.save_daily_execution_top_tasks(
                sheet["id"],
                [
                    {"task": "Launch offer", "why": "Revenue", "time_blocked": "9-11", "completed": False},
                    {"task": "Upload products", "why": "More SKUs", "time_blocked": "11-1", "completed": False},
                    {"task": "Fix ads", "why": "Traffic", "time_blocked": "2-3", "completed": False},
                ],
            )
            sheet = sports_cave_dashboard.set_daily_execution_mip_completed(sheet["id"], 0, True)

        self.assertEqual(sports_cave_dashboard.daily_execution_filled_task_count(sheet), 3)
        self.assertEqual(sports_cave_dashboard.daily_execution_completed_count(sheet), 1)
        self.assertFalse(sports_cave_dashboard.daily_execution_all_mips_complete(sheet))

    def test_daily_execution_task_statuses_count_as_complete(self):
        sheet = {
            "top_tasks": [
                {"task": "One", "status": "done", "completed": True},
                {"task": "Two", "status": "couldnt_finish", "completed": True},
                {"task": "Three", "status": "", "completed": False},
            ]
        }

        self.assertEqual(sports_cave_dashboard.daily_execution_completed_count(sheet), 2)
        self.assertFalse(sports_cave_dashboard.daily_execution_all_tasks_complete(sheet))

    def test_daily_execution_old_done_records_still_count_as_complete(self):
        sheet = {
            "top_tasks": [
                {"task": "One", "completed": True},
                {"task": "Two", "completed": True},
                {"task": "Three", "completed": True},
            ]
        }

        self.assertTrue(sports_cave_dashboard.daily_execution_all_tasks_complete(sheet))

    def test_daily_execution_all_mips_complete_permits_review(self):
        sheet = {
            "top_tasks": [
                {"task": "One", "completed": True},
                {"task": "Two", "completed": True},
                {"task": "Three", "completed": True},
            ]
        }

        self.assertTrue(sports_cave_dashboard.daily_execution_all_mips_complete(sheet))

    def test_daily_execution_panel_has_today_catchup_and_tomorrow_list_controls(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        panel_source = source[
            source.index("def render_daily_execution_panel") :
            source.index("\n\ndef render_task_group")
        ]

        self.assertIn("Daily Execution", panel_source)
        self.assertIn("Create Today's List", panel_source)
        self.assertIn("Create Tomorrow's List", panel_source)
        self.assertIn("Tomorrow&apos;s list is ready.", panel_source)
        self.assertIn('key="daily-execution-create-tomorrow-list"', panel_source)
        self.assertNotIn("Generate Tomorrow's Execution Prompt", panel_source)
        self.assertNotIn("Create Today's Sheet", panel_source)

    def test_daily_execution_create_sheet_does_not_duplicate_same_date(self):
        backend = FakeDashboardBackend()
        user = {"id": "admin-1", "display_name": "Nathan"}

        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=backend):
            first = sports_cave_dashboard.create_daily_execution_sheet(user, date(2026, 7, 22), "Australia/Sydney")
            second = sports_cave_dashboard.create_daily_execution_sheet(user, date(2026, 7, 22), "Australia/Sydney")

        self.assertEqual(first["id"], second["id"])
        self.assertEqual(len(backend.daily_sheets), 1)

    def test_daily_execution_panel_task_column_labels_are_business_terms(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        panel_source = source[
            source.index("def render_daily_execution_panel") :
            source.index("\n\ndef render_task_group")
        ]

        self.assertIn("**Task**", panel_source)
        self.assertIn("**Details**", panel_source)
        self.assertIn("**Time allocated**", panel_source)
        self.assertIn("**Done / Couldn&apos;t finish**", panel_source)
        self.assertIn("**MIP Task {index}**", panel_source)
        self.assertIn("**Other tasks**", panel_source)
        self.assertIn("Save List", panel_source)
        self.assertIn("Complete today's tasks to unlock review.", panel_source)
        self.assertIn("Today's list has no tasks yet.", panel_source)
        self.assertNotIn("Save MIPs", panel_source)

    def test_daily_execution_additional_items_show_one_blank_row_by_default(self):
        sheet = sports_cave_dashboard._normalise_daily_sheet(
            {
                "id": "sheet-1",
                "user_id": "admin-1",
                "sheet_date": "2026-07-21",
                "top_tasks": [],
                "additional_items": [],
            }
        )

        self.assertEqual(len(sheet["top_tasks"]), 3)
        self.assertEqual(len(sheet["additional_items"]), 1)
        self.assertEqual(sheet["additional_items"][0]["task"], "")

    def test_daily_execution_saves_other_tasks_and_filters_blank_rows(self):
        backend = FakeDashboardBackend()
        user = {"id": "admin-1", "display_name": "Nathan"}

        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=backend):
            sheet = sports_cave_dashboard.create_daily_execution_sheet(user, date(2026, 7, 21), "Australia/Sydney")
            saved = sports_cave_dashboard.save_daily_execution_tasks(
                sheet["id"],
                [
                    {"task": "Launch offer", "why": "Revenue", "time_blocked": "9-11", "status": "done"},
                    {"task": "Upload products", "why": "SKUs", "time_blocked": "11-1", "status": "couldnt_finish"},
                    {"task": "Fix ads", "why": "Traffic", "time_blocked": "2-3", "status": ""},
                ],
                [
                    {"task": "Check inbox", "details": "Customer issue", "time_blocked": "15m", "status": "done"},
                    {"task": "", "details": "", "time_blocked": "", "status": ""},
                ],
            )

        self.assertEqual(len(backend.daily_sheets[0]["additional_items"]), 1)
        self.assertEqual(backend.daily_sheets[0]["additional_items"][0]["task"], "Check inbox")
        self.assertEqual(len(saved["additional_items"]), 2)
        self.assertEqual(saved["additional_items"][0]["status"], "done")
        self.assertEqual(saved["additional_items"][1]["task"], "")

    def test_daily_execution_other_task_statuses_normalise_old_saved_records(self):
        sheet = sports_cave_dashboard._normalise_daily_sheet(
            {
                "id": "sheet-1",
                "user_id": "admin-1",
                "sheet_date": "2026-07-21",
                "top_tasks": [],
                "additional_items": [{"task": "Legacy small task", "completed": True}],
            }
        )

        self.assertEqual(sheet["additional_items"][0]["status"], "done")
        self.assertTrue(sports_cave_dashboard.daily_execution_task_finished(sheet["additional_items"][0]))
        self.assertEqual(sheet["additional_items"][1]["task"], "")

    def test_daily_execution_additional_items_malformed_shapes_do_not_crash(self):
        cases = [
            None,
            [],
            [{"task": "List row", "status": "couldnt_finish"}],
            {"task": "Dict row", "details": "Old object shape", "completed": True},
            '[{"task": "JSON row", "time_blocked": "20m"}]',
            "Plain legacy note",
            42,
        ]
        expected_first_tasks = {
            "List row",
            "Dict row",
            "JSON row",
            "Plain legacy note",
        }

        for value in cases:
            with self.subTest(value=repr(value)):
                sheet = sports_cave_dashboard._normalise_daily_sheet(
                    {
                        "id": "sheet-1",
                        "user_id": "admin-1",
                        "sheet_date": "2026-07-21",
                        "top_tasks": [],
                        "additional_items": value,
                    }
                )
                self.assertEqual(sheet["additional_items"][-1]["task"], "")
                if sheet["additional_items"][0]["task"] in expected_first_tasks:
                    self.assertIn(sheet["additional_items"][0]["task"], expected_first_tasks)

    def test_daily_execution_save_with_mips_and_other_tasks_does_not_raise(self):
        backend = FakeDashboardBackend()
        user = {"id": "admin-1", "display_name": "Nathan"}

        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=backend):
            sheet = sports_cave_dashboard.create_daily_execution_sheet(user, date(2026, 7, 22), "Australia/Sydney")
            saved = sports_cave_dashboard.save_daily_execution_tasks(
                sheet["id"],
                [
                    {"task": "MIP one", "why": "Revenue", "time_blocked": "9am", "status": "done"},
                    {"task": "MIP two", "why": "Products", "time_blocked": "11am", "status": "couldnt_finish"},
                    {"task": "MIP three", "why": "Ads", "time_blocked": "2pm", "status": "done"},
                ],
                [
                    {"task": "Other one", "details": "Small task", "time_blocked": "15m", "status": "done"},
                    {"task": "", "details": "", "time_blocked": "", "status": ""},
                ],
            )
            reloaded = sports_cave_dashboard.get_daily_execution_sheet(user, date(2026, 7, 22))

        self.assertTrue(sports_cave_dashboard.daily_execution_all_tasks_complete(saved))
        self.assertEqual(reloaded["additional_items"][0]["task"], "Other one")
        self.assertEqual(reloaded["additional_items"][1]["task"], "")

    def test_daily_execution_review_saves_ratings_and_reflections(self):
        backend = FakeDashboardBackend()
        user = {"id": "admin-1", "display_name": "Nathan"}
        review = {
            "daily_summary": "Uploaded the products.",
            "tomorrow_intention": "Nail ads.",
            "no_grey_zone": {"avoided": "Email cleanup"},
            "ratings": {"Focus": 8, "Overall Score": 7},
        }

        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=backend), patch(
            "activity_log.get_activity_actor",
            return_value="Nathan",
        ):
            sheet = sports_cave_dashboard.create_daily_execution_sheet(user, date(2026, 7, 21), "Australia/Sydney")
            completed = sports_cave_dashboard.complete_daily_execution_review(sheet["id"], review)

        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["ratings"]["Focus"], 8)
        self.assertEqual(completed["no_grey_zone"]["avoided"], "Email cleanup")
        self.assertEqual(completed["tomorrow_intention"], "Nail ads.")
        self.assertEqual(backend.activity_rows[0]["event_type"], "daily_execution_completed")
        self.assertEqual(backend.activity_rows[0]["actor"], "Nathan")

    def test_tomorrow_execution_prompt_includes_required_context(self):
        today_sheet = {
            "sheet_date": "2026-07-21",
            "status": "active",
            "top_tasks": [
                {"task": "Launch NASCAR drop", "why": "Revenue", "completed": False},
                {"task": "Upload golf product", "why": "More SKUs", "completed": True},
            ],
        }
        yesterday_sheet = {
            "sheet_date": "2026-07-20",
            "status": "completed",
            "top_tasks": [{"task": "Avoided ad testing", "why": "Traffic", "completed": False}],
            "no_grey_zone": {"avoided": "Ad testing"},
        }
        prompt = sports_cave_dashboard.build_tomorrow_execution_prompt(
            today_sheet=today_sheet,
            yesterday_sheet=yesterday_sheet,
            week_sheets=[today_sheet, yesterday_sheet],
            open_tasks=[{"text": "Create Bathurst mockups", "category": "New designs to complete"}],
            activity_entries=[{"message": "Mockup made: Bathurst", "actor": "Nathan"}],
            upcoming_events=[
                {
                    "title": "Black Friday 2026",
                    "sport": "Sales",
                    "regions": ["USA"],
                    "start_date": "2026-11-27",
                    "end_date": "2026-11-27",
                    "importance": 5,
                }
            ],
        )

        self.assertIn("$5,000,000 revenue", prompt)
        self.assertIn("Launch NASCAR drop", prompt)
        self.assertIn("Avoided ad testing", prompt)
        self.assertIn("Create Bathurst mockups", prompt)
        self.assertIn("Mockup made: Bathurst", prompt)
        self.assertIn("Black Friday 2026", prompt)

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

    def test_manual_task_categories_are_daily_dashboard_only(self):
        expected = (
            "Collections to update",
            "New designs to complete",
            "New products to be uploaded (in designs offline not uploaded folder)",
            "Existing product updated — variants working",
        )
        removed = {
            "Mockups for existing product",
            "Product uploaded",
            "Design updated",
            "New design made",
            "New product with mockups uploaded",
        }

        self.assertEqual(sports_cave_dashboard.TASK_GROUPS, expected)
        self.assertTrue(removed.isdisjoint(set(sports_cave_dashboard.TASK_GROUPS)))
        self.assertEqual(
            sports_cave_dashboard.normalize_task_category("New product uploaded — set to Draft"),
            "New products to be uploaded (in designs offline not uploaded folder)",
        )
        self.assertEqual(
            sports_cave_dashboard.normalize_task_category("New products to be uploaded (in designs offline not uploaded folder)"),
            "New products to be uploaded (in designs offline not uploaded folder)",
        )
        self.assertEqual(
            sports_cave_dashboard.normalize_task_category("Mockups for existing product"),
            "Collections to update",
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

    def test_home_greeting_includes_signed_in_user_name(self):
        local_now = datetime(2026, 7, 21, 9, 30, tzinfo=ZoneInfo("Australia/Sydney"))

        greeting = sports_cave_dashboard.greeting_for_account(
            local_now,
            {"display_name": "Nathan", "email": "nathan@sportscave.test"},
        )

        self.assertEqual(greeting, "Good morning, Nathan")

    def test_admin_greeting_uses_australia_sydney_time(self):
        utc_now = datetime(2026, 7, 21, 20, 30, tzinfo=timezone.utc)
        admin = {
            "role": os_accounts.ROLE_ADMIN,
            "display_name": "Nathan",
            "timezone": os_accounts.ADMIN_TIMEZONE,
        }
        local_now = utc_now.astimezone(ZoneInfo(os_accounts.timezone_for_user(admin)))

        self.assertEqual(
            sports_cave_dashboard.greeting_for_account(local_now, admin),
            "Good morning, Nathan",
        )

    def test_worker_greeting_uses_asia_manila_time(self):
        utc_now = datetime(2026, 7, 21, 20, 30, tzinfo=timezone.utc)
        worker = {
            "role": os_accounts.ROLE_WORKER,
            "display_name": "Maria",
            "timezone": os_accounts.WORKER_TIMEZONE,
        }
        local_now = utc_now.astimezone(ZoneInfo(os_accounts.timezone_for_user(worker)))

        self.assertEqual(
            sports_cave_dashboard.greeting_for_account(local_now, worker),
            "Good night, Maria",
        )

    def test_activity_table_record_displays_actor_name(self):
        record = sports_cave_dashboard.activity_table_record(
            {
                "action_type": "mockup_generated",
                "message": "Mockup made: Veery Elleegant 2021 Melbourne Cup",
                "page": "Mockups",
                "actor": "Maria",
                "created_at": "2026-07-21T00:00:00+00:00",
            },
            ZoneInfo("Asia/Manila"),
        )

        self.assertEqual(record["User"], "Maria")
        self.assertEqual(record["Activity"], "Mockup made")

    def test_mockup_upload_activity_is_grouped_with_all_item_details(self):
        entries = [
            {
                "id": "mockup-2",
                "action_type": "mockup_uploaded",
                "message": "Added mockup: 02 - Office (Product Page)",
                "page": "Mockups",
                "actor": "Reina",
                "entity_id": "run-final-crown",
                "created_at": "2026-07-21T02:02:00+00:00",
                "metadata": {"product_name": "The Final Crown Spain World Cup"},
            },
            {
                "id": "mockup-1",
                "action_type": "mockup_uploaded",
                "message": "Added mockup: 01 - Man Cave (Product Page)",
                "page": "Mockups",
                "actor": "Reina",
                "entity_id": "run-final-crown",
                "created_at": "2026-07-21T02:01:00+00:00",
                "metadata": {"product_name": "The Final Crown Spain World Cup"},
            },
            {
                "id": "task-1",
                "action_type": "task_added",
                "message": "Task added: Refresh NASCAR collection",
                "page": "Dashboard",
                "actor": "Nathan",
                "created_at": "2026-07-21T02:00:00+00:00",
                "metadata": {},
            },
        ]

        grouped = sports_cave_dashboard.group_mockup_activity_entries(
            entries,
            ZoneInfo("Australia/Sydney"),
        )

        self.assertEqual(len(grouped), 2)
        mockup_group = next(entry for entry in grouped if entry.get("is_mockup_group"))
        record = sports_cave_dashboard.activity_table_record(mockup_group)
        self.assertEqual(record["Activity"], "Product mockups done")
        self.assertEqual(
            record["Details"],
            "the-final-crown-spain-world-cup — 2 mockups uploaded",
        )
        self.assertEqual(record["User"], "Reina")
        self.assertEqual(
            mockup_group["mockup_items"],
            ["01 - Man Cave (Product Page)", "02 - Office (Product Page)"],
        )
        task_entry = next(entry for entry in grouped if entry.get("id") == "task-1")
        self.assertEqual(task_entry, entries[2])

    def test_mockup_groups_do_not_mix_products_or_users(self):
        entries = [
            {
                "action_type": "mockup_uploaded",
                "message": "Added mockup: 01 - Man Cave",
                "page": "Mockups",
                "actor": "Reina",
                "entity_id": "run-one",
                "created_at": "2026-07-21T03:03:00+00:00",
                "metadata": {"product_name": "Product One"},
            },
            {
                "action_type": "mockup_uploaded",
                "message": "Added mockup: 02 - Office",
                "page": "Mockups",
                "actor": "Reina",
                "entity_id": "run-two",
                "created_at": "2026-07-21T03:02:00+00:00",
                "metadata": {"product_name": "Product Two"},
            },
            {
                "action_type": "mockup_uploaded",
                "message": "Added mockup: 03 - Living Room",
                "page": "Mockups",
                "actor": "Maria",
                "entity_id": "run-three",
                "created_at": "2026-07-21T03:01:00+00:00",
                "metadata": {"product_name": "Product One"},
            },
        ]

        grouped = sports_cave_dashboard.group_mockup_activity_entries(entries)
        mockup_groups = [entry for entry in grouped if entry.get("is_mockup_group")]

        self.assertEqual(len(mockup_groups), 3)
        self.assertEqual(
            {(entry["metadata"]["product_handle"], entry["actor"]) for entry in mockup_groups},
            {("product-one", "Reina"), ("product-two", "Reina"), ("product-one", "Maria")},
        )

    def test_mockup_group_infers_product_from_same_run_summary(self):
        entries = [
            {
                "action_type": "mockup_uploaded",
                "message": "Added mockup: 02 - Office",
                "page": "Mockups",
                "actor": "Reina",
                "entity_id": "run-with-context",
                "created_at": "2026-07-21T04:02:00+00:00",
                "metadata": {"prompt": "02-office-prompt.txt"},
            },
            {
                "action_type": "mockup_uploaded",
                "message": "Added mockup: 01 - Man Cave",
                "page": "Mockups",
                "actor": "Reina",
                "entity_id": "run-with-context",
                "created_at": "2026-07-21T04:01:00+00:00",
                "metadata": {"prompt": "01-man-cave-prompt.txt"},
            },
            {
                "action_type": "mockup_generated",
                "message": "Mockup made: Bathurst Champion",
                "page": "Mockups",
                "actor": "Reina",
                "entity_id": "run-with-context",
                "created_at": "2026-07-21T04:00:00+00:00",
                "metadata": {"product_name": "Bathurst Champion"},
            },
        ]

        grouped = sports_cave_dashboard.group_mockup_activity_entries(entries)
        mockup_group = next(entry for entry in grouped if entry.get("is_mockup_group"))
        record = sports_cave_dashboard.activity_table_record(mockup_group)

        self.assertEqual(record["Details"], "bathurst-champion — 2 mockups uploaded")


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

    def test_calendar_data_includes_requested_sports_and_sales(self):
        events = sports_cave_dashboard.load_calendar_events(ROOT / "data" / "sporting_calendar.json")
        sports = {event.get("sport") for event in events}
        titles = {event.get("title") for event in events}

        self.assertIn("AFL", sports)
        self.assertIn("NRL", sports)
        self.assertIn("Golf", sports)
        self.assertIn("Sales", sports)
        self.assertIn("Black Friday and Cyber Monday 2027", titles)

    def test_calendar_range_and_month_selector_options(self):
        options = sports_sales_calendar.month_options()

        self.assertEqual(sports_sales_calendar.CALENDAR_START, date(2026, 7, 21))
        self.assertEqual(sports_sales_calendar.CALENDAR_END, date(2027, 12, 31))
        self.assertEqual(options[0], date(2026, 7, 1))
        self.assertEqual(options[-1], date(2027, 12, 1))
        self.assertEqual(len(options), 18)
        self.assertEqual(
            [sports_sales_calendar.month_label(month) for month in options],
            [
                "July 2026", "August 2026", "September 2026", "October 2026",
                "November 2026", "December 2026", "January 2027", "February 2027",
                "March 2027", "April 2027", "May 2027", "June 2027", "July 2027",
                "August 2027", "September 2027", "October 2027", "November 2027",
                "December 2027",
            ],
        )

    def test_calendar_market_codes_and_event_kinds_are_valid(self):
        events = sports_cave_dashboard.load_calendar_events(ROOT / "data" / "sporting_calendar.json")

        errors = {
            event.get("id"): sports_sales_calendar.validate_event(event)
            for event in events
            if sports_sales_calendar.validate_event(event)
        }

        self.assertEqual(errors, {})

    def test_confirmed_events_sort_before_tbc_events(self):
        events = [
            {
                "id": "later",
                "markets": ["AU"],
                "sport": "AFL",
                "start_date": "2026-08-20",
                "end_date": "2026-08-20",
                "title": "Later confirmed",
            },
            {
                "id": "tbc",
                "markets": ["AU"],
                "sport": "AFL",
                "date_precision": "month",
                "start_month": "2026-08",
                "title": "August TBC",
            },
            {
                "id": "earlier",
                "markets": ["US"],
                "sport": "NFL",
                "start_date": "2026-08-10",
                "end_date": "2026-08-10",
                "title": "Earlier confirmed",
            },
        ]

        ordered = sports_sales_calendar.sorted_calendar_events(events)

        self.assertEqual([event["id"] for event in ordered], ["earlier", "later", "tbc"])

    def test_tbc_events_never_enter_exact_upcoming_or_alert_logic(self):
        today = date(2027, 5, 1)
        tbc_event = {
            "alert_label": "Final soon",
            "date_precision": "month",
            "id": "tbc-final",
            "importance": 5,
            "markets": ["AU"],
            "regions": ["Australia"],
            "sport": "AFL",
            "start_month": "2027-05",
            "title": "Final - date TBC",
        }

        self.assertEqual(sports_cave_dashboard.event_status(tbc_event, today), "tbc")
        self.assertIsNone(sports_cave_dashboard.days_until_event(tbc_event, today))
        self.assertEqual(sports_cave_dashboard.build_active_alerts([tbc_event], today), [])
        self.assertEqual(sports_sales_calendar.confirmed_upcoming_events([tbc_event], today), [])

    def test_current_calendar_month_uses_australia_sydney_time(self):
        utc_now = datetime(2026, 7, 31, 14, 30, tzinfo=timezone.utc)

        self.assertEqual(sports_sales_calendar.default_month(utc_now), date(2026, 8, 1))

    def test_calendar_selection_is_pure_and_makes_no_backend_query(self):
        events = sports_cave_dashboard.load_calendar_events(ROOT / "data" / "sporting_calendar.json")

        with patch.object(sports_cave_dashboard, "get_supabase_backend") as backend:
            exact, tbc = sports_sales_calendar.events_for_month(events, date(2027, 10, 1))

        backend.assert_not_called()
        self.assertTrue(exact)
        self.assertTrue(tbc)

    def test_activity_table_split_uses_only_first_recognised_colon(self):
        activity, details = sports_cave_dashboard.split_activity_message(
            {
                "action_type": "task_added",
                "message": "Task added: Create NASCAR design: Bathurst era",
            }
        )

        self.assertEqual(activity, "Task added")
        self.assertEqual(details, "Create NASCAR design: Bathurst era")

    def test_unknown_activity_type_keeps_full_original_message(self):
        activity, details = sports_cave_dashboard.split_activity_message(
            {
                "action_type": "custom_moment",
                "message": "Unmapped event: keep this: complete",
            }
        )

        self.assertEqual(activity, "Custom moment")
        self.assertEqual(details, "Unmapped event: keep this: complete")


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
            render_body.index("render_daily_execution_panel(local_now, events, state)"),
            render_body.index("render_activity_log(local_now)"),
        )
        self.assertLess(
            render_body.index("render_activity_log(local_now)"),
            render_body.index("render_sports_sales_calendar(events, local_now)"),
        )

    def test_calendar_helper_has_no_backend_or_network_imports(self):
        source = (ROOT / "sports_sales_calendar.py").read_text(encoding="utf-8")

        for forbidden in ("supabase", "shopify", "requests", "urllib", "streamlit"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source.casefold())

    def test_calendar_month_widget_reruns_only_its_fragment(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        calendar_source = source[
            source.index("@st.fragment\ndef render_sports_sales_calendar") :
            source.index("\n\ndef render_lightweight_dashboard_page")
        ]

        self.assertIn("dashboard-sports-sales-calendar-month", calendar_source)
        for forbidden in (
            "list_activity_entries",
            "load_dashboard_state",
            "get_supabase_backend",
            "shopify",
            "prodigi",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, calendar_source.casefold())

    def test_activity_log_uses_compact_table_columns_not_cards(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        table_source = source[
            source.index("def _activity_table_html") :
            source.index("\n\ndef _calendar_event_pill")
        ]

        for heading in ("Date", "Time", "Activity", "Details", "User", "Area"):
            self.assertIn(f"<th>{heading}</th>", table_source)
        self.assertIn("activity_table_record", table_source)
        self.assertNotIn('<div class="sc-log-row">', table_source)


if __name__ == "__main__":
    unittest.main()
