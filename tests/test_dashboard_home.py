from datetime import date, datetime, timedelta, timezone
import copy
import csv
import hashlib
import io
from pathlib import Path
import time as wall_time
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo
from streamlit.testing.v1 import AppTest

import sc_auth
import design_schedule
import os_accounts
import sports_cave_dashboard
import sports_sales_calendar
import supabase_backend


ROOT = Path(__file__).resolve().parents[1]
OWNER_EMAIL = "owner@sportscave.test"


def owner_user():
    return {
        "id": "admin-1",
        "username": "nathan",
        "email": OWNER_EMAIL,
        "display_name": "Nathan",
        "role": "admin",
        "timezone": "Australia/Sydney",
        "is_active": True,
        "page_permissions": [],
    }


def task_csv_bytes(rows):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=sports_cave_dashboard.TASK_IMPORT_CSV_COLUMNS)
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column, "") for column in sports_cave_dashboard.TASK_IMPORT_CSV_COLUMNS})
    return output.getvalue().encode("utf-8")


def representative_nfl_design_rows(count=19):
    styles = (
        ("Legends — Jerseys on Display", True),
        ("Simple Minimalistic", False),
        ("Nostalgic Moment", False),
        ("Rivalry Face-Off", True),
        ("Ultimate Moment", False),
        ("Specific Sporting Moment", False),
    )
    rows = []
    for index in range(1, count + 1):
        style, needs_two = styles[(index - 1) % len(styles)]
        token = chr(64 + index)
        first_subject = f"Player Alpha {token}"
        second_subject = f"Player Beta {token}"
        title = f"NFL COLLECTOR {index:02d}"
        task_title = f"Create NFL design — {title}"
        rows.append(
            {
                "task": task_title,
                "category": sports_cave_dashboard.DESIGN_TASK_GROUP,
                "task_section": sports_cave_dashboard.DESIGN_TASK_GROUP,
                "task_title": task_title,
                "design_style": style,
                "design_title": title,
                "sport": "American Football",
                "principal_subject_one": first_subject,
                "principal_subject_two": second_subject if needs_two else "",
                "team_country": "Team A & Team B" if needs_two else "Team A",
                "season_era": "1990–1999",
                "event_moment": "A real, defining moment — preserved accurately",
                "venue_location": "Historic Stadium, USA",
                "uniform_equipment_livery": "Authentic jersey, helmet & equipment",
                "essential_text": f'"{title}", 1995',
                "special_instructions": (
                    "Use the supplied photograph, preserve the player's face and jersey.\n"
                    "Keep the composition minimal, realistic, 4:3 and inside the border."
                ),
                "league_or_competition": "NFL",
                "team_or_athlete": (
                    f"{first_subject} vs {second_subject}"
                    if needs_two
                    else first_subject
                ),
                "moment_or_theme": "Legacy, rivalry & fan identity",
                "design_description": "Premium collector design with commas, apostrophes and emotion.",
                "priority": "High" if index <= 8 else "Medium",
                "due_date": "",
                "notes": f"Rank {index} of {count}; fills an NFL range gap.",
            }
        )
    return rows


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

    def create_dashboard_task(
        self,
        title,
        section,
        *,
        metadata=None,
        design_style="",
        actor="sports_cave_os",
    ):
        task = {
            "id": f"task-{len(self.tasks) + 1}",
            "title": title,
            "section": section,
            "status": "open",
            "created_at": "2026-07-21T00:00:00+00:00",
            "design_style": design_style,
            "metadata": metadata or {},
        }
        self.tasks.append(task)
        self._activity_row("task_added", f"Task added: {title}")
        return task

    def update_dashboard_task_design_style(self, task_id, design_style, *, actor="sports_cave_os"):
        for task in self.tasks:
            if task["id"] == task_id and task["section"] == sports_cave_dashboard.DESIGN_TASK_GROUP:
                task["design_style"] = design_style
                task.setdefault("metadata", {})["design_style"] = design_style
                return task
        return None

    def update_dashboard_task_design_details(
        self,
        task_id,
        design_style,
        design_details,
        *,
        actor="sports_cave_os",
    ):
        for task in self.tasks:
            if task["id"] == task_id and task["section"] == sports_cave_dashboard.DESIGN_TASK_GROUP:
                task["design_style"] = design_style
                task.setdefault("metadata", {})["design_style"] = design_style
                task["metadata"][sports_cave_dashboard.DESIGN_DETAILS_METADATA_KEY] = dict(
                    design_details
                )
                return task
        return None

    def delete_dashboard_task(
        self,
        task_id,
        *,
        required_section,
        deleted_by="",
        actor="sports_cave_os",
    ):
        for task in self.tasks:
            if (
                task["id"] == task_id
                and task["section"] == required_section
                and task.get("status") == "open"
            ):
                task["status"] = "deleted"
                task.setdefault("metadata", {})["deleted_by"] = deleted_by
                self._activity_row("task_deleted", f"Design task deleted: {task['title']}")
                return task
        return None

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

    def list_dashboard_tasks(self, status="open", *, limit=200):
        self.task_status_calls.append(status)
        if status == "all":
            return list(self.tasks)[:limit]
        return [task for task in self.tasks if task.get("status") == status][:limit]

    def import_dashboard_tasks_batch(self, candidates, *, actor="sports_cave_os"):
        snapshot = copy.deepcopy(self.tasks)
        result = {
            "created_count": 0,
            "reactivated_count": 0,
            "active_duplicate_count": 0,
            "completed_duplicate_count": 0,
            "failed_count": 0,
            "imported_tasks": [],
            "section_counts": {},
        }
        try:
            for candidate in candidates or []:
                key = tuple(candidate.get("duplicate_key") or ())
                matches = [
                    task
                    for task in self.tasks
                    if sports_cave_dashboard._task_existing_duplicate_key(task) == key
                ]
                active = next(
                    (task for task in matches if sports_cave_dashboard._task_import_status_group(task) == "active"),
                    None,
                )
                completed = next(
                    (task for task in matches if sports_cave_dashboard._task_import_status_group(task) == "completed"),
                    None,
                )
                deleted = next(
                    (task for task in matches if sports_cave_dashboard._task_import_status_group(task) == "deleted"),
                    None,
                )
                if active:
                    result["active_duplicate_count"] += 1
                    continue
                if completed:
                    result["completed_duplicate_count"] += 1
                    continue
                if deleted:
                    deleted.update(
                        {
                            "title": candidate["title"],
                            "section": candidate["section"],
                            "status": "open",
                            "completed_at": None,
                            "completed_by": "",
                            "design_style": candidate["metadata"].get("design_style") or "",
                            "metadata": copy.deepcopy(candidate["metadata"]),
                        }
                    )
                    task = deleted
                    result["reactivated_count"] += 1
                else:
                    task = self.create_dashboard_task(
                        candidate["title"],
                        candidate["section"],
                        metadata=copy.deepcopy(candidate["metadata"]),
                        design_style=candidate["metadata"].get("design_style") or "",
                        actor=actor,
                    )
                    result["created_count"] += 1
                result["imported_tasks"].append(task)
                result["section_counts"][candidate["section"]] = (
                    result["section_counts"].get(candidate["section"], 0) + 1
                )
        except Exception:
            self.tasks = snapshot
            raise
        result["imported_count"] = result["created_count"] + result["reactivated_count"]
        return result

    def list_activity_logs(
        self,
        *,
        start_at=None,
        end_at=None,
        limit=200,
        actor_user_id=None,
        actor_email=None,
    ):
        self.activity_calls.append(
            {
                "start_at": start_at,
                "end_at": end_at,
                "limit": limit,
                "actor_user_id": actor_user_id,
                "actor_email": actor_email,
            }
        )
        rows = list(self.activity_rows)
        if actor_user_id or actor_email:
            rows = [
                row
                for row in rows
                if (
                    bool(actor_user_id)
                    and str(((row.get("new_value") or {}).get("metadata") or {}).get("actor_id") or "")
                    == str(actor_user_id)
                )
                or (
                    bool(actor_email)
                    and str(((row.get("new_value") or {}).get("metadata") or {}).get("actor_email") or "").casefold()
                    == str(actor_email).casefold()
                )
            ]
        return rows if limit is None else rows[:limit]

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

    def create_daily_execution_sheet(self, *, user_id, user_name, sheet_date, timezone_name, actor="sports_cave_os", status="active"):
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
            "status": status,
            "top_tasks": [
                {"task": "", "why": "", "time_blocked": "", "completed": False, "status": ""},
                {"task": "", "why": "", "time_blocked": "", "completed": False, "status": ""},
                {"task": "", "why": "", "time_blocked": "", "completed": False, "status": ""},
            ],
            "additional_items": [],
            "no_grey_zone": {},
            "ratings": {},
            "planning_data": {},
            "review_data": {},
            "archived_snapshot": {},
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

    def get_daily_execution_home_sheets(self, user_id, today):
        self.daily_calls.append(("home", user_id, today))
        today_date = date.fromisoformat(str(today))
        wanted = {today_date.isoformat(), (today_date + timedelta(days=1)).isoformat()}
        rows = []
        for sheet in self.daily_sheets:
            if sheet.get("user_id") != user_id or sheet.get("sheet_date") not in wanted:
                continue
            if sheet.get("sheet_date") == today_date.isoformat() and sheet.get("status") == "planned":
                sheet["status"] = "active"
                sheet["activated_at"] = "2026-07-22T00:00:00+10:00"
            rows.append(dict(sheet))
        return rows

    def save_daily_execution_plan(
        self,
        *,
        user_id,
        user_name,
        sheet_date,
        timezone_name,
        top_tasks,
        additional_items,
        planning_data,
        archive_sheet_id=None,
        actor="sports_cave_os",
    ):
        existing = next((sheet for sheet in self.daily_sheets if sheet.get("user_id") == user_id and sheet.get("sheet_date") == sheet_date), None)
        if existing and existing.get("status") == "archived":
            raise ValueError("Archived execution sheets are read-only.")
        if not existing:
            existing = self.create_daily_execution_sheet(
                user_id=user_id,
                user_name=user_name,
                sheet_date=sheet_date,
                timezone_name=timezone_name,
                actor=actor,
                status="planned",
            )
            existing = next(sheet for sheet in self.daily_sheets if sheet["id"] == existing["id"])
        existing["top_tasks"] = top_tasks
        existing["additional_items"] = additional_items
        existing["planning_data"] = planning_data
        if archive_sheet_id:
            source = next((sheet for sheet in self.daily_sheets if sheet.get("id") == archive_sheet_id and sheet.get("user_id") == user_id), None)
            if source and source.get("status") in {"completed", "reviewed"} and not source.get("archived_at"):
                source["archived_snapshot"] = dict(source)
                source["status"] = "archived"
                source["archived_at"] = "2026-07-22T20:00:00+10:00"
                self._activity_row("daily_execution_archived", f"Daily sheet archived: {source['sheet_date']}")
        self._activity_row("daily_execution_tomorrow_planned", f"Tomorrow planned: {sheet_date}")
        self.activity_rows[0]["actor"] = actor
        return dict(existing)

    def update_daily_execution_top_tasks(self, sheet_id, top_tasks, additional_items=None, *, user_id=None):
        for sheet in self.daily_sheets:
            if sheet["id"] == sheet_id and sheet.get("user_id") == user_id:
                sheet["top_tasks"] = top_tasks
                if additional_items is not None:
                    sheet["additional_items"] = additional_items
                return dict(sheet)
        return {}

    def set_daily_execution_mip_completed(self, sheet_id, index, completed, *, outcome=None, user_id=None):
        for sheet in self.daily_sheets:
            if sheet["id"] == sheet_id and sheet.get("user_id") == user_id:
                old_status = sheet["top_tasks"][index].get("status") or ""
                sheet["top_tasks"][index]["completed"] = completed
                sheet["top_tasks"][index]["status"] = outcome or ("done" if completed else "")
                if old_status != sheet["top_tasks"][index]["status"] and sheet["top_tasks"][index]["status"]:
                    event_type = (
                        "daily_execution_mip_could_not_finish"
                        if sheet["top_tasks"][index]["status"] == "couldnt_finish"
                        else "daily_execution_mip_completed"
                    )
                    self._activity_row(event_type, f"Daily task updated: {sheet['top_tasks'][index]['task']}")
                return dict(sheet)
        return {}

    def complete_daily_execution_review(self, sheet_id, review_payload, *, actor="sports_cave_os", user_id=None):
        for sheet in self.daily_sheets:
            if sheet["id"] == sheet_id and (not user_id or sheet.get("user_id") == user_id):
                sheet["status"] = "reviewed"
                sheet["no_grey_zone"] = review_payload.get("no_grey_zone") or {}
                sheet["ratings"] = review_payload.get("ratings") or {}
                sheet["review_data"] = review_payload.get("review_data") or review_payload.get("no_grey_zone") or {}
                if "additional_items" in review_payload:
                    sheet["additional_items"] = review_payload.get("additional_items") or []
                sheet["daily_summary"] = review_payload.get("daily_summary") or ""
                sheet["tomorrow_intention"] = review_payload.get("tomorrow_intention") or ""
                sheet["completed_at"] = "2026-07-21T09:00:00+00:00"
                self._activity_row("daily_execution_completed", f"Daily Review completed: {sheet['sheet_date']}")
                self.activity_rows[0]["actor"] = actor
                return dict(sheet)
        return {}

    def update_daily_execution_prompt(self, sheet_id, prompt, *, user_id=None):
        for sheet in self.daily_sheets:
            if sheet["id"] == sheet_id and sheet.get("user_id") == user_id:
                sheet["generated_prompt"] = prompt
                return dict(sheet)
        return {}

    def list_daily_execution_sheets(self, user_id, start_date, end_date, *, limit=10):
        return [
            dict(sheet)
            for sheet in self.daily_sheets
            if sheet.get("user_id") == user_id and start_date <= sheet.get("sheet_date") <= end_date
        ][:limit]

    def list_daily_execution_archive_summaries(self, user_id, start_date, end_date, *, limit=8):
        self.daily_calls.append(("week", user_id, start_date, end_date, limit))
        return self.list_daily_execution_sheets(user_id, start_date, end_date, limit=limit)

    def get_daily_execution_archive_detail(self, user_id, sheet_id):
        self.daily_calls.append(("detail", user_id, sheet_id))
        return next((dict(sheet) for sheet in self.daily_sheets if sheet.get("user_id") == user_id and sheet.get("id") == sheet_id), {})


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
        self.owner_environment = patch.dict(
            "os.environ",
            {"SPORTS_CAVE_REPORTING_OWNER_EMAIL": OWNER_EMAIL},
            clear=False,
        )
        self.owner_environment.start()
        sports_cave_dashboard.clear_dashboard_caches()
        sports_cave_dashboard.clear_calendar_cache()

    def tearDown(self):
        sports_cave_dashboard.clear_dashboard_caches()
        sports_cave_dashboard.clear_calendar_cache()
        self.owner_environment.stop()

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

    def test_new_design_tasks_are_ordered_oldest_first(self):
        tasks = [
            {
                "id": "newest",
                "text": "Newest design",
                "category": sports_cave_dashboard.DESIGN_TASK_GROUP,
                "created_at": "2026-07-31T09:00:00+00:00",
            },
            {
                "id": "oldest",
                "text": "Oldest design",
                "category": sports_cave_dashboard.DESIGN_TASK_GROUP,
                "created_at": "2026-07-29T09:00:00+00:00",
            },
            {
                "id": "middle",
                "text": "Middle design",
                "category": sports_cave_dashboard.DESIGN_TASK_GROUP,
                "created_at": "2026-07-30T09:00:00Z",
            },
            {
                "id": "second-oldest",
                "text": "Second oldest design",
                "category": sports_cave_dashboard.DESIGN_TASK_GROUP,
                "created_at": "2026-07-29T10:00:00+00:00",
            },
            {
                "id": "second-newest",
                "text": "Second newest design",
                "category": sports_cave_dashboard.DESIGN_TASK_GROUP,
                "created_at": "2026-07-30T10:00:00+00:00",
            },
        ]

        ordered = sports_cave_dashboard.ordered_task_group(
            tasks,
            sports_cave_dashboard.DESIGN_TASK_GROUP,
        )

        self.assertEqual(
            [task["id"] for task in ordered],
            ["oldest", "second-oldest", "middle", "second-newest", "newest"],
        )
        self.assertEqual(
            [
                task["id"]
                for task in ordered[:sports_cave_dashboard.DESIGN_TASK_VISIBLE_LIMIT]
            ],
            ["oldest", "second-oldest", "middle"],
        )

    def test_non_design_task_groups_keep_existing_order(self):
        tasks = [
            {
                "id": "newest",
                "category": sports_cave_dashboard.COLLECTIONS_TASK_GROUP,
                "created_at": "2026-07-31T09:00:00+00:00",
            },
            {
                "id": "oldest",
                "category": sports_cave_dashboard.COLLECTIONS_TASK_GROUP,
                "created_at": "2026-07-29T09:00:00+00:00",
            },
        ]

        ordered = sports_cave_dashboard.ordered_task_group(
            tasks,
            sports_cave_dashboard.COLLECTIONS_TASK_GROUP,
        )

        self.assertEqual([task["id"] for task in ordered], ["newest", "oldest"])

    def test_design_overflow_preview_uses_only_first_five_words(self):
        self.assertEqual(
            sports_cave_dashboard.compact_design_task_preview(
                "The Summer of 41 Williams versus DiMaggio"
            ),
            "The Summer of 41 Williams...",
        )
        self.assertEqual(
            sports_cave_dashboard.compact_design_task_preview("Short design title"),
            "Short design title",
        )

    def test_dashboard_renders_all_designs_in_one_compact_list(self):
        backend = FakeDashboardBackend()
        backend.tasks = [
            {
                "id": f"design-{index}",
                "title": title,
                "section": sports_cave_dashboard.DESIGN_TASK_GROUP,
                "status": "open",
                "created_at": created_at,
            }
            for index, title, created_at in (
                (5, "Newest design five extra preview words", "2026-07-31T09:00:00+00:00"),
                (1, "Oldest design one extra preview words", "2026-07-27T09:00:00+00:00"),
                (3, "Middle design three extra preview words", "2026-07-29T09:00:00+00:00"),
                (2, "Second design two extra preview words", "2026-07-28T09:00:00+00:00"),
                (4, "Fourth design four extra preview words", "2026-07-30T09:00:00+00:00"),
            )
        ]
        app_test = AppTest.from_file(str(ROOT / "app.py"))
        app_test.session_state["sports_cave_authenticated"] = True
        app_test.session_state["sports_cave_current_user"] = owner_user()
        app_test.session_state["sports_cave_auth_checked_at"] = wall_time.monotonic()
        app_test.session_state["selected_page"] = "Design Studio"
        with patch.object(
            sports_cave_dashboard,
            "get_supabase_backend",
            return_value=backend,
        ):
            app_test.run(timeout=20)

        design_tables = [
            item.value
            for item in app_test.get("dataframe")
            if "Design title" in item.value.columns
        ]
        self.assertFalse(app_test.exception)
        self.assertEqual(len(design_tables), 1)
        self.assertEqual(len(design_tables[0]), 5)
        self.assertEqual(
            list(design_tables[0]["Task"]),
            [
                "Oldest design one extra preview words",
                "Second design two extra preview words",
                "Middle design three extra preview words",
                "Fourth design four extra preview words",
                "Newest design five extra preview words",
            ],
        )
        self.assertEqual(len([button for button in app_test.button if button.label == "Complete"]), 1)

    def test_task_cards_render_metadata_normally_and_escape_dynamic_content(self):
        backend = FakeDashboardBackend()
        backend.tasks = [
            {
                "id": "manual-1",
                "title": "Nathan's A&B \"Drop\", <script>alert(1)</script>",
                "section": sports_cave_dashboard.COLLECTIONS_TASK_GROUP,
                "status": "open",
                "created_at": "2026-08-05T02:57:00+00:00",
                "metadata": {},
            },
            {
                "id": "import-1",
                "title": "Serena Williams — The Final Serve",
                "section": sports_cave_dashboard.DESIGN_TASK_GROUP,
                "status": "open",
                "created_at": "2026-08-05T02:57:00+00:00",
                "metadata": {
                    sports_cave_dashboard.TASK_IMPORT_METADATA_KEY: {
                        "task_title": "Serena Williams — The Final Serve",
                        "sport": "Tennis & Finals",
                        "league_or_competition": 'US "Open"',
                        "team_or_athlete": "<script>alert(2)</script>",
                        "design_title": "The Final Serve",
                        "design_description": "Commas, apostrophes, ampersands & <b>tags</b> stay text.",
                    }
                },
            },
        ]
        app_test = AppTest.from_file(str(ROOT / "app.py"))
        app_test.session_state["sports_cave_authenticated"] = True
        app_test.session_state["sports_cave_current_user"] = owner_user()
        app_test.session_state["sports_cave_auth_checked_at"] = wall_time.monotonic()
        app_test.session_state["selected_page"] = "Design Studio"

        with patch.object(
            sports_cave_dashboard,
            "get_supabase_backend",
            return_value=backend,
        ):
            app_test.run(timeout=20)

        self.assertFalse(app_test.exception)
        tables = [item.value for item in app_test.get("dataframe")]
        self.assertEqual(len(tables), 1)
        combined_values = "\n".join(
            str(value)
            for table in tables
            for value in table.astype(str).to_numpy().flatten()
        )
        self.assertIn("Tennis & Finals", combined_values)
        self.assertIn("<script>alert(2)</script>", combined_values)
        self.assertFalse(any("<script>" in str(item.proto.body) for item in app_test.get("html")))
        app_test.session_state["design-schedule-view"] = "Collections"
        with patch.object(
            sports_cave_dashboard,
            "get_supabase_backend",
            return_value=backend,
        ):
            app_test.run(timeout=20)
        collection_values = "\n".join(
            str(value)
            for table in [item.value for item in app_test.get("dataframe")]
            for value in table.astype(str).to_numpy().flatten()
        )
        self.assertIn("Nathan's A&B \"Drop\", <script>alert(1)</script>", collection_values)
        self.assertEqual(len([button for button in app_test.button if button.label == "Complete"]), 1)

    def test_task_complete_marks_complete_and_writes_activity_log(self):
        backend = FakeDashboardBackend()

        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=backend):
            task = sports_cave_dashboard.add_task("Refresh NFL collection", "Collections to update")
            completed = sports_cave_dashboard.complete_task(task["id"])
            state = sports_cave_dashboard.load_dashboard_state(
                sports_cave_dashboard.ACTIVITY_VIEW_ALL_TIME,
                datetime(2026, 7, 21, tzinfo=timezone.utc),
                user=owner_user(),
            )

        self.assertEqual(completed["status"], "complete")
        self.assertEqual(state["tasks"], [])
        self.assertEqual(state["activity_log"][0]["message"], "Task completed: Refresh NFL collection")
        self.assertEqual(state["activity_log"][1]["message"], "Task added: Refresh NFL collection")

    def test_design_task_delete_uses_stable_id_and_preserves_other_sections(self):
        backend = FakeDashboardBackend()
        backend.tasks = [
            {
                "id": "design-keep",
                "title": "Same title",
                "section": sports_cave_dashboard.DESIGN_TASK_GROUP,
                "status": "open",
                "metadata": {},
            },
            {
                "id": "design-delete",
                "title": "Same title",
                "section": sports_cave_dashboard.DESIGN_TASK_GROUP,
                "status": "open",
                "metadata": {},
            },
            {
                "id": "collection-keep",
                "title": "Same title",
                "section": sports_cave_dashboard.COLLECTIONS_TASK_GROUP,
                "status": "open",
                "metadata": {},
            },
        ]

        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=backend):
            deleted = sports_cave_dashboard.delete_design_task(
                "design-delete",
                user=owner_user(),
            )
            repeated = sports_cave_dashboard.delete_design_task(
                "design-delete",
                user=owner_user(),
            )

        self.assertEqual(deleted["id"], "design-delete")
        self.assertEqual(deleted["status"], "deleted")
        self.assertIsNone(repeated)
        self.assertEqual(backend.tasks[0]["status"], "open")
        self.assertEqual(backend.tasks[2]["status"], "open")
        self.assertEqual(
            [row["event_type"] for row in backend.activity_rows],
            ["task_deleted"],
        )

    def test_design_task_delete_requires_existing_task_permission(self):
        worker = {
            "id": "worker-1",
            "role": "worker",
            "is_active": True,
            "page_permissions": [],
        }

        with patch.object(sports_cave_dashboard, "get_supabase_backend") as backend:
            with self.assertRaisesRegex(PermissionError, "permission"):
                sports_cave_dashboard.delete_design_task(
                    "design-1",
                    user=worker,
                )

        backend.assert_not_called()

    def test_deleted_design_does_not_block_csv_reimport(self):
        row = {
            "task": "Create NFL design - THE DRIVE",
            "category": sports_cave_dashboard.DESIGN_TASK_GROUP,
            "design_style": "ultimate_moment",
            "design_title": "THE DRIVE",
            "sport": "NFL",
        }
        existing = {
            "id": "deleted-design",
            "title": row["task"],
            "section": sports_cave_dashboard.DESIGN_TASK_GROUP,
            "status": "deleted",
            "design_style": "ultimate_moment",
            "metadata": {
                sports_cave_dashboard.TASK_IMPORT_METADATA_KEY: row,
            },
        }

        preview = sports_cave_dashboard.preview_task_csv_import(
            task_csv_bytes([row]),
            "designs.csv",
            existing_tasks=[existing],
        )

        self.assertEqual(preview["valid_count"], 1)
        self.assertEqual(preview["duplicate_count"], 0)

    def test_new_design_completion_creates_upload_task_with_mockup_choice(self):
        backend = FakeDashboardBackend()

        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=backend):
            task = sports_cave_dashboard.add_task(
                "Create New Supercars Design",
                sports_cave_dashboard.DESIGN_TASK_GROUP,
                design_style="motorsport_driver_car",
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

    def test_new_design_task_requires_and_persists_a_canonical_style(self):
        backend = FakeDashboardBackend()

        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=backend):
            with self.assertRaisesRegex(ValueError, "Style required"):
                sports_cave_dashboard.add_task(
                    "Create a legends design",
                    sports_cave_dashboard.DESIGN_TASK_GROUP,
                )
            task = sports_cave_dashboard.add_task(
                "Create a legends design",
                sports_cave_dashboard.DESIGN_TASK_GROUP,
                design_style="Legends Jersey Display",
            )

        self.assertEqual(task["design_style"], "legends_jersey_display")
        self.assertEqual(task["metadata"]["design_style"], "legends_jersey_display")

    def test_legacy_design_task_style_can_be_assigned_and_persisted(self):
        backend = FakeDashboardBackend()
        backend.tasks.append(
            {
                "id": "legacy-design",
                "title": "Update old plaque",
                "section": sports_cave_dashboard.DESIGN_TASK_GROUP,
                "status": "open",
                "created_at": "2026-07-21T00:00:00+00:00",
                "metadata": {},
            }
        )

        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=backend):
            updated = sports_cave_dashboard.update_task_design_style(
                "legacy-design",
                "Update Existing Design",
            )

        self.assertEqual(updated["design_style"], "update_existing")
        self.assertEqual(updated["metadata"]["design_style"], "update_existing")

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

    def test_task_csv_export_template_has_exact_headers_and_no_example_rows(self):
        template = sports_cave_dashboard.build_task_import_template_csv()
        decoded = template.decode("utf-8")
        reader = csv.DictReader(io.StringIO(decoded, newline=""))
        rows = list(reader)

        self.assertEqual(reader.fieldnames, list(sports_cave_dashboard.TASK_IMPORT_CSV_COLUMNS))
        self.assertEqual(rows, [])

    def test_non_design_export_leaves_design_studio_columns_blank(self):
        exported = sports_cave_dashboard.build_task_import_template_csv(
            [
                {
                    "id": "collection-1",
                    "title": "Refresh NFL collection",
                    "section": sports_cave_dashboard.COLLECTIONS_TASK_GROUP,
                    "status": "open",
                    "metadata": {"design_style": "minimalist_hero"},
                }
            ]
        )
        row = next(csv.DictReader(io.StringIO(exported.decode("utf-8"), newline="")))

        for column in sports_cave_dashboard.DESIGN_TASK_CSV_COLUMNS:
            self.assertEqual(row[column], "")

    def test_task_csv_preview_preserves_structured_design_fields_and_aliases(self):
        description = (
            'Premium cinematic Sports Cave artwork featuring Serena, commas, "quotes", '
            "apostrophes and line breaks.\nUse restrained US Open lighting."
        )
        csv_data = b"\xef\xbb\xbf" + task_csv_bytes(
            [
                {
                    "task_section": "  new_designs_to_complete  ",
                    "sport": "Tennis",
                    "league_or_competition": "US Open",
                    "team_or_athlete": "Serena Williams",
                    "design_style": "Championship / Achievement",
                    "design_title": "The Final Serve",
                    "moment_or_theme": "Career legacy and final US Open appearance",
                    "design_description": description,
                    "priority": "High",
                    "notes": "GOAT collection candidate",
                }
            ]
        )

        preview = sports_cave_dashboard.preview_task_csv_import(
            csv_data,
            "ideas.csv",
            existing_tasks=[],
        )
        task = preview["tasks"][0]
        details = sports_cave_dashboard.task_import_details({"metadata": task["metadata"]})

        self.assertEqual(preview["valid_count"], 1)
        self.assertEqual(task["section"], sports_cave_dashboard.DESIGN_TASK_GROUP)
        self.assertEqual(task["title"], "The Final Serve")
        self.assertEqual(details["sport"], "Tennis")
        self.assertEqual(details["team_or_athlete"], "Serena Williams")
        self.assertEqual(details["design_description"], description)
        self.assertEqual(sports_cave_dashboard.task_design_style(task), "championship_achievement")
        self.assertEqual(
            sports_cave_dashboard.task_import_summary({"metadata": task["metadata"]}),
            "Tennis · Serena Williams · US Open",
        )

    def test_task_csv_style_round_trip_preserves_the_stable_slug(self):
        source_tasks = [
            {
                "id": "design-1",
                "title": "The Rivals",
                "section": sports_cave_dashboard.DESIGN_TASK_GROUP,
                "status": "open",
                "design_style": "rivalry_faceoff",
                "metadata": {
                    "design_style": "rivalry_faceoff",
                    sports_cave_dashboard.TASK_IMPORT_METADATA_KEY: {
                        "task_title": "The Rivals",
                        "team_or_athlete": "Peter Brock vs Allan Moffat",
                    },
                },
            }
        ]

        exported = sports_cave_dashboard.build_task_import_template_csv(source_tasks)
        preview = sports_cave_dashboard.preview_task_csv_import(
            exported,
            "tasks.csv",
            existing_tasks=[],
        )

        self.assertEqual(preview["valid_count"], 1)
        self.assertEqual(
            sports_cave_dashboard.task_design_style(preview["tasks"][0]),
            "rivalry_faceoff",
        )

    def test_old_csv_without_design_style_is_safe_and_requires_style_for_designs(self):
        columns = [
            column
            for column in sports_cave_dashboard.TASK_IMPORT_CSV_COLUMNS
            if column != "design_style"
        ]
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=columns)
        writer.writeheader()
        writer.writerow(
            {
                "task_section": "Collections to update",
                "task_title": "Refresh NFL collection",
            }
        )
        writer.writerow(
            {
                "task_section": "New designs to complete",
                "task_title": "Legacy design import",
            }
        )

        preview = sports_cave_dashboard.preview_task_csv_import(
            output.getvalue().encode("utf-8"),
            "old-tasks.csv",
            existing_tasks=[],
        )

        self.assertEqual(preview["valid_count"], 1)
        self.assertEqual(preview["invalid_count"], 1)
        self.assertIn("Style required", preview["errors"][0]["errors"][0])

    def test_task_csv_unknown_design_style_is_a_clear_row_error(self):
        preview = sports_cave_dashboard.preview_task_csv_import(
            task_csv_bytes(
                [
                    {
                        "task_section": "New designs to complete",
                        "task_title": "Wrong style",
                        "design_style": "Crowded montage",
                    }
                ]
            ),
            "tasks.csv",
            existing_tasks=[],
        )

        self.assertEqual(preview["valid_count"], 0)
        self.assertTrue(
            preview["errors"][0]["errors"][0].startswith(
                "Unknown design_style: Crowded montage. Accepted styles:"
            )
        )

    def test_task_csv_validation_reports_blank_invalid_and_duplicate_rows(self):
        existing_tasks = [
            {
                "id": "existing",
                "title": "Refresh NFL collection",
                "section": sports_cave_dashboard.COLLECTIONS_TASK_GROUP,
                "status": "open",
                "metadata": {},
            }
        ]
        csv_data = task_csv_bytes(
            [
                {
                    "task_section": "Collections",
                    "task_title": "Refresh NASCAR collection",
                },
                {
                    "task_section": "collections_to_update",
                    "task_title": "Refresh NASCAR collection",
                },
                {
                    "task_section": "Collections to update",
                    "task_title": "Refresh NFL collection",
                },
                {
                    "task_section": "Unknown bucket",
                    "task_title": "Valid title but bad section",
                },
                {
                    "task_section": "designs",
                },
                {},
            ]
        )

        preview = sports_cave_dashboard.preview_task_csv_import(
            csv_data,
            "tasks.csv",
            existing_tasks=existing_tasks,
        )

        self.assertEqual(preview["valid_count"], 1)
        self.assertEqual(preview["duplicate_count"], 2)
        self.assertEqual(preview["invalid_count"], 2)
        self.assertEqual(preview["blank_count"], 1)
        self.assertEqual(
            preview["section_counts"],
            {sports_cave_dashboard.COLLECTIONS_TASK_GROUP: 1},
        )
        self.assertEqual([error["row_number"] for error in preview["errors"]], [5, 6])
        self.assertIn("category", preview["errors"][0]["errors"][0])
        self.assertIn("task is required", preview["errors"][1]["errors"][0])

    def test_task_csv_rejects_unsupported_files_safely(self):
        with self.assertRaisesRegex(sports_cave_dashboard.TaskCSVImportError, ".csv"):
            sports_cave_dashboard.preview_task_csv_import(b"not,csv\n", "tasks.xlsx")

        with self.assertRaisesRegex(sports_cave_dashboard.TaskCSVImportError, "UTF-8"):
            sports_cave_dashboard.preview_task_csv_import(b"\xff\xfe\x00\x00", "tasks.csv")

    def test_task_csv_import_appends_persists_metadata_and_skips_second_import(self):
        backend = FakeDashboardBackend()
        rows = [
            {
                "task_section": "new_designs",
                "task_title": f"Design idea {index}",
                "sport": "Tennis",
                "league_or_competition": "US Open",
                "team_or_athlete": f"Athlete {chr(64 + index)}",
                "principal_subject_one": f"Athlete {chr(64 + index)}",
                "design_title": f"Design idea {index}",
                "moment_or_theme": "Finals moment",
                "design_description": f"Structured brief {index}",
                "priority": "High",
                "design_style": "minimalist_hero",
            }
            for index in range(1, 16)
        ]
        csv_data = task_csv_bytes(rows)

        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=backend), patch(
            "activity_log.record_activity_log"
        ) as record_activity:
            preview = sports_cave_dashboard.preview_task_csv_import(
                csv_data,
                "designs.csv",
                existing_tasks=sports_cave_dashboard.list_tasks(status="all"),
            )
            result = sports_cave_dashboard.import_task_csv_preview(preview)
            state = sports_cave_dashboard.load_dashboard_state(include_activity=False)
            second_preview = sports_cave_dashboard.preview_task_csv_import(
                csv_data,
                "designs.csv",
                existing_tasks=sports_cave_dashboard.list_tasks(status="all"),
            )
            second_result = sports_cave_dashboard.import_task_csv_preview(second_preview)

        self.assertEqual(result["imported_count"], 15)
        self.assertEqual(
            result["section_counts"],
            {sports_cave_dashboard.DESIGN_TASK_GROUP: 15},
        )
        self.assertEqual(len(backend.tasks), 15)
        self.assertEqual(len(state["tasks"]), 15)
        self.assertTrue(
            all(task["section"] == sports_cave_dashboard.DESIGN_TASK_GROUP for task in state["tasks"])
        )
        details = sports_cave_dashboard.task_import_details(state["tasks"][0])
        self.assertEqual(details["sport"], "Tennis")
        self.assertTrue(details["design_description"].startswith("Structured brief"))
        self.assertEqual(second_preview["valid_count"], 0)
        self.assertEqual(second_preview["duplicate_count"], 15)
        self.assertEqual(second_result["imported_count"], 0)
        self.assertEqual(len(backend.tasks), 15)
        record_activity.assert_called_once()
        self.assertEqual(record_activity.call_args.kwargs["metadata"]["filename"], "designs.csv")
        self.assertEqual(record_activity.call_args.kwargs["metadata"]["imported_count"], 15)
        self.assertEqual(record_activity.call_args.kwargs["metadata"]["skipped_count"], 0)

    def test_design_task_csv_round_trip_preserves_every_v2_field_and_multiline_text(self):
        details = {
            "design_title": "The Great Debate, Revisited",
            "sport": "NFL",
            "principal_subject_one": "Joe Montana",
            "principal_subject_two": "Terry Bradshaw",
            "team_country": "49ers / Steelers",
            "season_era": "1970s-1980s",
            "event_moment": "A generational face-off",
            "venue_location": "Dark championship stadium",
            "uniform_equipment_livery": "Authentic period uniforms",
            "essential_text": "MONTANA VS BRADSHAW",
            "special_instructions": "Keep both heroes equal.\nUse a restrained, premium finish.",
        }
        source = {
            "id": "design-round-trip",
            "title": "Create the Montana versus Bradshaw rivalry",
            "section": sports_cave_dashboard.DESIGN_TASK_GROUP,
            "status": "open",
            "design_style": "rivalry_faceoff",
            "metadata": {
                "design_style": "rivalry_faceoff",
                sports_cave_dashboard.DESIGN_DETAILS_METADATA_KEY: details,
            },
        }

        exported = sports_cave_dashboard.build_task_import_template_csv([source])
        exported_reader = csv.DictReader(io.StringIO(exported.decode("utf-8"), newline=""))
        exported_row = next(exported_reader)
        preview = sports_cave_dashboard.preview_task_csv_import(
            exported,
            "round-trip.csv",
            existing_tasks=[],
        )
        imported_details = sports_cave_dashboard.design_task_details(preview["tasks"][0])

        self.assertEqual(
            exported_reader.fieldnames,
            list(sports_cave_dashboard.TASK_IMPORT_CSV_COLUMNS),
        )
        self.assertEqual(exported_row["task"], source["title"])
        self.assertEqual(exported_row["category"], sports_cave_dashboard.DESIGN_TASK_GROUP)
        self.assertEqual(exported_row["design_style"], "rivalry_faceoff")
        self.assertEqual(exported_row["special_instructions"], details["special_instructions"])
        self.assertEqual(preview["valid_count"], 1)
        self.assertEqual(imported_details, details)

    def test_csv_import_populates_all_design_fields_and_converts_display_label(self):
        row = {
            "task": "Brock versus Moffat at Bathurst",
            "category": sports_cave_dashboard.DESIGN_TASK_GROUP,
            "design_style": "  Rivalry Face-Off  ",
            "design_title": "The Mountain Rivals",
            "sport": "Motorsport",
            "principal_subject_one": "Peter Brock",
            "principal_subject_two": "Allan Moffat",
            "team_country": "Australia",
            "season_era": "1970s",
            "event_moment": "Bathurst rivalry",
            "venue_location": "Mount Panorama",
            "uniform_equipment_livery": "Correct period suits and liveries",
            "essential_text": "BROCK VS MOFFAT",
            "special_instructions": "Equal hero scale",
        }

        preview = sports_cave_dashboard.preview_task_csv_import(
            task_csv_bytes([row]),
            "v2.csv",
            existing_tasks=[],
        )
        task = preview["tasks"][0]
        backend = FakeDashboardBackend()
        sports_cave_dashboard.clear_task_cache()
        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=backend), patch(
            "activity_log.record_activity_log"
        ):
            result = sports_cave_dashboard.import_task_csv_preview(preview)

        self.assertEqual(preview["valid_count"], 1)
        self.assertEqual(result["imported_count"], 1)
        self.assertEqual(sports_cave_dashboard.task_design_style(task), "rivalry_faceoff")
        self.assertEqual(
            sports_cave_dashboard.design_task_details(backend.tasks[0]),
            {key: row[key] for key in sports_cave_dashboard.design_studio_styles.DESIGN_DETAIL_KEYS},
        )

    def test_csv_design_validation_covers_subject_limits_and_style_requirements(self):
        cases = (
            (
                {
                    "task": "Michael Jordan, Kobe Bryant and LeBron James collector design",
                    "category": sports_cave_dashboard.DESIGN_TASK_GROUP,
                    "design_style": "ultimate_moment",
                    "principal_subject_one": "Michael Jordan",
                    "principal_subject_two": "Kobe Bryant",
                },
                "exceeds the new Sports Cave limit of two",
            ),
            (
                {
                    "task": "One-sided rivalry",
                    "category": sports_cave_dashboard.DESIGN_TASK_GROUP,
                    "design_style": "rivalry_faceoff",
                    "principal_subject_one": "Joe Montana",
                },
                "requires exactly two",
            ),
            (
                {
                    "task": "Two jersey legends",
                    "category": sports_cave_dashboard.DESIGN_TASK_GROUP,
                    "design_style": "legends_jersey_display",
                    "principal_subject_one": "Lionel Messi",
                },
                "requires exactly two",
            ),
        )
        for row, expected in cases:
            with self.subTest(style=row["design_style"]):
                preview = sports_cave_dashboard.preview_task_csv_import(
                    task_csv_bytes([row]),
                    "invalid-design.csv",
                    existing_tasks=[],
                )
                self.assertEqual(preview["valid_count"], 0)
                self.assertTrue(
                    any(expected in error for error in preview["errors"][0]["errors"])
                )

        permitted = (
            {
                "task": "Update the border only",
                "category": sports_cave_dashboard.DESIGN_TASK_GROUP,
                "design_style": "update_existing",
            },
            {
                "task": "Restore the 1968 finish photograph",
                "category": sports_cave_dashboard.DESIGN_TASK_GROUP,
                "design_style": "vintage_restoration",
                "event_moment": "1968 finish",
            },
        )
        for row in permitted:
            preview = sports_cave_dashboard.preview_task_csv_import(
                task_csv_bytes([row]),
                "permitted-design.csv",
                existing_tasks=[],
            )
            self.assertEqual(preview["valid_count"], 1)

    def test_non_design_and_legacy_csv_formats_remain_compatible(self):
        legacy_columns = (
            "task_section",
            "task_title",
            "sport",
            "league_or_competition",
            "team_or_athlete",
            "design_title",
            "moment_or_theme",
            "design_description",
            "priority",
            "due_date",
            "notes",
        )
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=legacy_columns)
        writer.writeheader()
        writer.writerow(
            {
                "task_section": sports_cave_dashboard.COLLECTIONS_TASK_GROUP,
                "task_title": "Refresh the NFL collection",
                "notes": "Legacy row",
            }
        )

        preview = sports_cave_dashboard.preview_task_csv_import(
            output.getvalue().encode("utf-8"),
            "legacy.csv",
            existing_tasks=[],
        )

        self.assertEqual(preview["valid_count"], 1)
        self.assertEqual(preview["tasks"][0]["title"], "Refresh the NFL collection")
        self.assertEqual(preview["tasks"][0]["section"], sports_cave_dashboard.COLLECTIONS_TASK_GROUP)

    def test_unified_design_details_save_is_atomic_and_refreshes_metadata(self):
        backend = FakeDashboardBackend()
        details = {
            key: ""
            for key in sports_cave_dashboard.design_studio_styles.DESIGN_DETAIL_KEYS
        }
        details.update(
            {
                "design_title": "The Mountain Rivals",
                "sport": "Motorsport",
                "principal_subject_one": "Peter Brock",
                "principal_subject_two": "Allan Moffat",
                "special_instructions": "Keep it minimal",
            }
        )
        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=backend):
            task = sports_cave_dashboard.add_task(
                "Brock versus Moffat rivalry",
                sports_cave_dashboard.DESIGN_TASK_GROUP,
                design_style="rivalry_faceoff",
            )
            updated = sports_cave_dashboard.update_task_design_details(
                task["id"],
                "Rivalry Face-Off",
                details,
            )

        self.assertEqual(updated["design_style"], "rivalry_faceoff")
        self.assertEqual(
            updated["metadata"][sports_cave_dashboard.DESIGN_DETAILS_METADATA_KEY],
            details,
        )

    def test_missing_design_style_column_surfaces_migration_action(self):
        backend = FakeDashboardBackend()
        task = backend.create_dashboard_task(
            "Update old artwork",
            sports_cave_dashboard.DESIGN_TASK_GROUP,
            design_style="update_existing",
        )
        def missing_design_style_column(*args, **kwargs):
            raise RuntimeError('column "design_style" does not exist')

        backend.update_dashboard_task_design_details = missing_design_style_column
        sports_cave_dashboard.clear_task_cache()

        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=backend):
            with self.assertRaisesRegex(
                sports_cave_dashboard.DashboardStorageError,
                "Design Studio V2 database migration",
            ):
                sports_cave_dashboard.update_task_design_details(
                    task["id"],
                    "update_existing",
                    {},
                )

    def test_task_import_details_are_empty_for_legacy_simple_tasks(self):
        simple_task = {
            "id": "legacy",
            "title": "Manual task",
            "section": sports_cave_dashboard.COLLECTIONS_TASK_GROUP,
            "metadata": {},
        }

        self.assertEqual(sports_cave_dashboard.task_import_details(simple_task), {})
        self.assertEqual(sports_cave_dashboard.task_import_summary(simple_task), "")

    def test_activity_log_queries_use_view_date_bounds_without_pagination_limits(self):
        backend = FakeDashboardBackend()
        now = datetime(2026, 7, 21, 10, 30, tzinfo=timezone.utc)

        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=backend):
            sports_cave_dashboard.list_activity_entries(sports_cave_dashboard.ACTIVITY_VIEW_TODAY, now, user=owner_user())
            sports_cave_dashboard.list_activity_entries(sports_cave_dashboard.ACTIVITY_VIEW_LAST_7_DAYS, now, user=owner_user())
            sports_cave_dashboard.list_activity_entries(sports_cave_dashboard.ACTIVITY_VIEW_MONTH, now, user=owner_user())
            sports_cave_dashboard.list_activity_entries(sports_cave_dashboard.ACTIVITY_VIEW_ALL_TIME, now, user=owner_user())

        today_call, week_call, month_call, all_time_call = backend.activity_calls
        self.assertIsNone(today_call["limit"])
        self.assertIsNone(week_call["limit"])
        self.assertIsNone(month_call["limit"])
        self.assertIsNone(all_time_call["limit"])
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
            sports_cave_dashboard.list_activity_entries(sports_cave_dashboard.ACTIVITY_VIEW_TODAY, now, user=owner_user())
            sports_cave_dashboard.list_activity_entries(sports_cave_dashboard.ACTIVITY_VIEW_TODAY, now, user=owner_user())
            sports_cave_dashboard.list_activity_entries(sports_cave_dashboard.ACTIVITY_VIEW_LAST_7_DAYS, now, user=owner_user())

        self.assertEqual(len(backend.activity_calls), 2)

    def test_activity_log_owner_receives_all_users_without_identity_filter(self):
        backend = FakeDashboardBackend()
        backend.activity_rows = [
            {
                "id": 1,
                "event_type": "files_uploaded",
                "actor": "Nathan",
                "created_at": "2026-07-21T01:00:00+00:00",
                "new_value": {"message": "Owner work", "metadata": {"actor_id": "admin-1"}},
            },
            {
                "id": 2,
                "event_type": "files_uploaded",
                "actor": "Reina",
                "created_at": "2026-07-21T00:30:00+00:00",
                "new_value": {"message": "Worker work", "metadata": {"actor_id": "worker-1"}},
            },
        ]

        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=backend):
            entries = sports_cave_dashboard.list_activity_entries(
                sports_cave_dashboard.ACTIVITY_VIEW_ALL_TIME,
                user=owner_user(),
            )

        self.assertEqual([entry["message"] for entry in entries], ["Owner work", "Worker work"])
        self.assertIsNone(backend.activity_calls[0]["actor_user_id"])
        self.assertIsNone(backend.activity_calls[0]["actor_email"])

    def test_activity_log_non_owner_is_scoped_to_authenticated_identity(self):
        backend = FakeDashboardBackend()
        backend.activity_rows = [
            {
                "id": 1,
                "event_type": "files_uploaded",
                "actor": "Nathan",
                "created_at": "2026-07-21T01:00:00+00:00",
                "new_value": {
                    "message": "Owner work",
                    "metadata": {"actor_id": "admin-1", "actor_email": OWNER_EMAIL},
                },
            },
            {
                "id": 2,
                "event_type": "files_uploaded",
                "actor": "Reina",
                "created_at": "2026-07-21T00:30:00+00:00",
                "new_value": {
                    "message": "Worker work",
                    "metadata": {
                        "actor_id": "worker-1",
                        "actor_email": "reina@sportscave.test",
                    },
                },
            },
        ]
        worker = {
            "id": "worker-1",
            "email": "reina@sportscave.test",
            "role": "worker",
            "is_active": True,
            "page_permissions": ["dashboard", os_accounts.ACTIVITY_LOG_CAPABILITY],
        }

        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=backend):
            entries = sports_cave_dashboard.list_activity_entries(
                sports_cave_dashboard.ACTIVITY_VIEW_ALL_TIME,
                user=worker,
            )

        self.assertEqual([entry["message"] for entry in entries], ["Worker work"])
        self.assertEqual(backend.activity_calls[0]["actor_user_id"], "worker-1")
        self.assertEqual(backend.activity_calls[0]["actor_email"], "reina@sportscave.test")

    def test_activity_log_invalid_owner_configuration_fails_closed_to_own_records(self):
        non_owner_admin = {
            **owner_user(),
            "id": "admin-2",
            "email": "other-admin@sportscave.test",
        }
        with patch.dict(
            "os.environ",
            {"SPORTS_CAVE_REPORTING_OWNER_EMAIL": "missing@sportscave.test"},
            clear=False,
        ):
            scope = sports_cave_dashboard.activity_log_access_scope(non_owner_admin)

        self.assertFalse(scope["all_users"])
        self.assertEqual(scope["actor_user_id"], "admin-2")
        self.assertEqual(scope["actor_email"], "other-admin@sportscave.test")

    def test_activity_log_unverified_or_inactive_owner_never_receives_all_users(self):
        configured_email = OWNER_EMAIL
        worker_with_owner_email = {
            "id": "worker-1",
            "email": configured_email,
            "role": "worker",
            "is_active": True,
            "page_permissions": ["dashboard", os_accounts.ACTIVITY_LOG_CAPABILITY],
        }
        inactive_admin = {**owner_user(), "is_active": False}

        self.assertFalse(
            sports_cave_dashboard.activity_log_access_scope(worker_with_owner_email)["all_users"]
        )
        self.assertIsNone(sports_cave_dashboard.activity_log_access_scope(inactive_admin))
        with self.assertRaises(sports_cave_dashboard.DashboardStorageError):
            sports_cave_dashboard.list_activity_entries(
                sports_cave_dashboard.ACTIVITY_VIEW_ALL_TIME,
                user=None,
            )

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
                user=owner_user(),
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
        user = owner_user()

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
        user = owner_user()

        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=backend):
            sheet = sports_cave_dashboard.create_daily_execution_sheet(user, date(2026, 7, 21), "Australia/Sydney")
            sheet = sports_cave_dashboard.save_daily_execution_top_tasks(
                sheet["id"],
                [
                    {"task": "Launch offer", "why": "Revenue", "time_blocked": "9-11", "completed": False},
                    {"task": "Upload products", "why": "More SKUs", "time_blocked": "11-1", "completed": False},
                    {"task": "Fix ads", "why": "Traffic", "time_blocked": "2-3", "completed": False},
                ],
                user=user,
            )
            sheet = sports_cave_dashboard.set_daily_execution_mip_completed(
                sheet["id"],
                0,
                True,
                user=user,
            )

        self.assertEqual(sports_cave_dashboard.daily_execution_filled_task_count(sheet), 3)
        self.assertEqual(sports_cave_dashboard.daily_execution_completed_count(sheet), 1)
        self.assertFalse(sports_cave_dashboard.daily_execution_all_mips_complete(sheet))

    def test_daily_execution_outcome_mapping_closes_only_finished_outcomes(self):
        backend = FakeDashboardBackend()
        user = owner_user()
        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=backend):
            sheet = sports_cave_dashboard.create_daily_execution_sheet(
                user,
                date(2026, 7, 21),
                "Australia/Sydney",
            )
            sheet = sports_cave_dashboard.save_daily_execution_top_tasks(
                sheet["id"],
                [
                    {"task": "Open task"},
                    {"task": "Completed task"},
                    {"task": "Blocked task"},
                ],
                user=user,
            )
            sheet = sports_cave_dashboard.set_daily_execution_mip_completed(
                sheet["id"],
                0,
                False,
                outcome="",
                user=user,
            )
            sheet = sports_cave_dashboard.set_daily_execution_mip_completed(
                sheet["id"],
                1,
                True,
                outcome=sports_cave_dashboard.DAILY_TASK_STATUS_DONE,
                user=user,
            )
            sheet = sports_cave_dashboard.set_daily_execution_mip_completed(
                sheet["id"],
                2,
                True,
                outcome=sports_cave_dashboard.DAILY_TASK_STATUS_COULDNT_FINISH,
                user=user,
            )
            event_count = len(backend.activity_rows)
            repeated = sports_cave_dashboard.set_daily_execution_mip_completed(
                sheet["id"],
                2,
                True,
                outcome=sports_cave_dashboard.DAILY_TASK_STATUS_COULDNT_FINISH,
                user=user,
            )
            reloaded = sports_cave_dashboard.get_daily_execution_sheet(
                user,
                date(2026, 7, 21),
            )

        self.assertFalse(reloaded["top_tasks"][0]["completed"])
        self.assertEqual(reloaded["top_tasks"][0]["status"], "")
        self.assertTrue(reloaded["top_tasks"][1]["completed"])
        self.assertEqual(reloaded["top_tasks"][1]["status"], "done")
        self.assertFalse(reloaded["top_tasks"][2]["completed"])
        self.assertEqual(reloaded["top_tasks"][2]["status"], "couldnt_finish")
        self.assertTrue(sports_cave_dashboard.daily_execution_task_finished(reloaded["top_tasks"][2]))
        self.assertEqual(sports_cave_dashboard.daily_execution_completed_count(repeated), 1)
        self.assertEqual(len(backend.activity_rows), event_count)

    def test_daily_execution_data_helpers_allow_active_admins_and_reject_workers(self):
        backend = FakeDashboardBackend()
        worker = {
            "id": "worker-1",
            "email": "worker@sportscave.test",
            "role": "worker",
            "is_active": True,
        }
        non_owner_admin = {
            "id": "admin-2",
            "email": "admin@sportscave.test",
            "role": "admin",
            "is_active": True,
        }
        inactive_admin = {
            "id": "admin-3",
            "email": "inactive@sportscave.test",
            "role": "admin",
            "is_active": False,
        }

        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=backend):
            self.assertEqual(
                sports_cave_dashboard.get_daily_execution_home_sheets(
                    non_owner_admin,
                    date(2026, 7, 21),
                ),
                {"today": {}, "tomorrow": {}, "carryover_review": {}},
            )
            for user in (worker, inactive_admin):
                with self.subTest(user=user["id"]), self.assertRaises(
                    sports_cave_dashboard.DashboardStorageError
                ):
                    sports_cave_dashboard.get_daily_execution_home_sheets(
                        user,
                        date(2026, 7, 21),
                    )

        self.assertEqual([call[0] for call in backend.daily_calls], ["home"])

    def test_daily_execution_mutations_reject_non_admin_direct_calls(self):
        backend = FakeDashboardBackend()
        worker = {
            "id": "worker-1",
            "email": "worker@sportscave.test",
            "role": "worker",
            "is_active": True,
        }

        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=backend):
            with self.assertRaises(sports_cave_dashboard.DashboardStorageError):
                sports_cave_dashboard.create_daily_execution_sheet(
                    worker,
                    date(2026, 7, 21),
                    "Asia/Manila",
                )
            with self.assertRaises(sports_cave_dashboard.DashboardStorageError):
                sports_cave_dashboard.save_daily_execution_tasks(
                    "forged-sheet-id",
                    [{"task": "Forged"}],
                    [],
                    user=worker,
                )

        self.assertEqual(backend.daily_calls, [])

    def test_daily_execution_terminal_statuses_are_resolved_but_only_done_is_completed(self):
        sheet = {
            "top_tasks": [
                {"task": "One", "status": "done", "completed": True},
                {"task": "Two", "status": "couldnt_finish", "completed": True},
                {"task": "Three", "status": "", "completed": False},
            ]
        }

        self.assertEqual(sports_cave_dashboard.daily_execution_completed_count(sheet), 1)
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

    def test_daily_planner_window_has_today_catchup_and_real_tomorrow_planning(self):
        route_source = (ROOT / "daily_planner.py").read_text(encoding="utf-8")
        client_source = (ROOT / "components" / "daily_planner" / "index.html").read_text(encoding="utf-8")

        self.assertNotIn("st.dialog", route_source)
        self.assertIn("Create ${bundle.work_date === bundle.today ? \"today's\"", client_source)
        self.assertIn("Plan tomorrow", client_source)
        self.assertIn("saveSheet", client_source)
        self.assertIn("archive_sheet_id:archiveSheetId", client_source)
        self.assertNotIn("Tomorrow&apos;s list is ready.", client_source)
        self.assertNotIn("Generate Tomorrow's Execution Prompt", client_source)

    def test_daily_execution_create_sheet_does_not_duplicate_same_date(self):
        backend = FakeDashboardBackend()
        user = owner_user()

        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=backend):
            first = sports_cave_dashboard.create_daily_execution_sheet(user, date(2026, 7, 22), "Australia/Sydney")
            second = sports_cave_dashboard.create_daily_execution_sheet(user, date(2026, 7, 22), "Australia/Sydney")

        self.assertEqual(first["id"], second["id"])
        self.assertEqual(len(backend.daily_sheets), 1)

    def test_daily_planner_task_column_labels_are_business_terms(self):
        panel_source = (ROOT / "components" / "daily_planner" / "index.html").read_text(encoding="utf-8")

        self.assertIn(">Task</span>", panel_source)
        self.assertIn("Details / outcome required", panel_source)
        self.assertIn(">Allocated</span>", panel_source)
        self.assertIn(">Status</span>", panel_source)
        self.assertIn("Three major execution tasks", panel_source)
        self.assertIn("Other tasks", panel_source)
        self.assertIn("Save today's plan", panel_source)
        self.assertIn("Resolve every planned task before completing the review.", panel_source)
        self.assertIn(">Timer</span>", panel_source)
        self.assertIn(">Start</button>", panel_source)
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
        user = owner_user()

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
                user=user,
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
        user = owner_user()

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
                user=user,
            )
            reloaded = sports_cave_dashboard.get_daily_execution_sheet(user, date(2026, 7, 22))

        self.assertTrue(sports_cave_dashboard.daily_execution_all_tasks_complete(saved))
        self.assertEqual(reloaded["additional_items"][0]["task"], "Other one")
        self.assertEqual(reloaded["additional_items"][1]["task"], "")

    def test_daily_execution_review_saves_ratings_and_reflections(self):
        backend = FakeDashboardBackend()
        user = owner_user()
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
            completed = sports_cave_dashboard.complete_daily_execution_review(
                sheet["id"],
                review,
                user=user,
            )

        self.assertEqual(completed["status"], "reviewed")
        self.assertEqual(completed["ratings"]["Focus"], 8)
        self.assertEqual(completed["no_grey_zone"]["avoided"], "Email cleanup")
        self.assertEqual(completed["tomorrow_intention"], "Nail ads.")
        self.assertEqual(backend.activity_rows[0]["event_type"], "daily_execution_completed")
        self.assertEqual(backend.activity_rows[0]["actor"], "Nathan")

    def test_daily_review_submission_lives_inside_daily_planner_window(self):
        route_source = (ROOT / "daily_planner.py").read_text(encoding="utf-8")
        client_source = (ROOT / "components" / "daily_planner" / "index.html").read_text(encoding="utf-8")

        self.assertIn("complete_daily_execution_review", route_source)
        self.assertIn("daily_execution_all_tasks_complete", route_source)
        self.assertIn("Complete Daily Review", client_source)
        self.assertIn("Plan tomorrow", client_source)
        self.assertNotIn("st.dialog", route_source)

    def test_daily_review_ui_requires_a_confirmed_saved_sheet(self):
        route_source = (ROOT / "daily_planner.py").read_text(encoding="utf-8")
        client_source = (ROOT / "components" / "daily_planner" / "index.html").read_text(encoding="utf-8")

        self.assertIn("get_daily_execution_archive_detail", route_source)
        self.assertIn("That Daily Planner sheet is not available for this account.", route_source)
        self.assertIn("reviewed || !tasksResolved", client_source)
        self.assertNotIn("_daily_execution_fragment_rerun()", route_source)

    def test_tomorrow_plan_upserts_one_sheet_and_archives_reviewed_today_once(self):
        backend = FakeDashboardBackend()
        user = owner_user()
        today = date(2026, 7, 22)
        tomorrow = date(2026, 7, 23)
        top_tasks = [
            {"task": f"MIP {index}", "why": "Revenue", "time_blocked": "1 hour", "status": ""}
            for index in range(1, 4)
        ]
        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=backend), patch(
            "activity_log.get_activity_actor", return_value="Nathan"
        ):
            current = sports_cave_dashboard.create_daily_execution_sheet(user, today, "Australia/Sydney")
            current = sports_cave_dashboard.complete_daily_execution_review(
                current["id"],
                {"daily_summary": "Finished", "ratings": {"Overall Score": 8}},
                user=user,
            )
            first = sports_cave_dashboard.save_daily_execution_plan(
                user, tomorrow, "Australia/Sydney", top_tasks, [], {"main_outcome": "Launch"}, archive_sheet_id=current["id"]
            )
            second = sports_cave_dashboard.save_daily_execution_plan(
                user, tomorrow, "Australia/Sydney", top_tasks, [], {"main_outcome": "Launch updated"}, archive_sheet_id=current["id"]
            )

        self.assertEqual(first["id"], second["id"])
        self.assertEqual(len(backend.daily_sheets), 2)
        archived = next(sheet for sheet in backend.daily_sheets if sheet["sheet_date"] == today.isoformat())
        self.assertEqual(archived["status"], "archived")
        self.assertEqual(
            [task.get("task") for task in archived["archived_snapshot"]["top_tasks"]],
            [task.get("task") for task in current["top_tasks"]],
        )
        self.assertEqual(sum(row["event_type"] == "daily_execution_archived" for row in backend.activity_rows), 1)

    def test_unreviewed_sheet_is_not_archived_and_archived_sheet_is_read_only(self):
        backend = FakeDashboardBackend()
        user = owner_user()
        top_tasks = [{"task": f"MIP {index}"} for index in range(1, 4)]
        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=backend), patch(
            "activity_log.get_activity_actor", return_value="Nathan"
        ):
            current = sports_cave_dashboard.create_daily_execution_sheet(user, date(2026, 7, 22), "Australia/Sydney")
            sports_cave_dashboard.save_daily_execution_plan(
                user,
                date(2026, 7, 23),
                "Australia/Sydney",
                top_tasks,
                [],
                {},
                archive_sheet_id=current["id"],
            )
            self.assertEqual(backend.daily_sheets[0]["status"], "active")
            backend.daily_sheets[0]["status"] = "archived"
            with self.assertRaises(sports_cave_dashboard.DashboardStorageError):
                sports_cave_dashboard.save_daily_execution_plan(
                    user, date(2026, 7, 22), "Australia/Sydney", top_tasks, [], {}
                )

    def test_archive_queries_are_scoped_to_signed_in_owner(self):
        backend = FakeDashboardBackend()
        backend.daily_sheets = [
            {"id": "nathan", "user_id": "admin-1", "sheet_date": "2026-07-21", "status": "archived"},
            {"id": "other", "user_id": "admin-2", "sheet_date": "2026-07-21", "status": "archived"},
        ]
        user = owner_user()
        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=backend):
            rows = sports_cave_dashboard.list_daily_execution_archive_summaries(user, date(2026, 7, 20), date(2026, 7, 26))
            blocked_detail = sports_cave_dashboard.get_daily_execution_archive_detail(user, "other")
        self.assertEqual([row["id"] for row in rows], ["nathan"])
        self.assertEqual(blocked_detail, {})

    def test_planned_sheet_becomes_active_on_its_sydney_date(self):
        backend = FakeDashboardBackend()
        backend.daily_sheets.append(
            {
                "id": "tomorrow-1",
                "user_id": "admin-1",
                "user_name": "Nathan",
                "sheet_date": "2026-07-23",
                "timezone": "Australia/Sydney",
                "status": "planned",
                "top_tasks": [],
                "additional_items": [],
            }
        )
        user = owner_user()
        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=backend):
            home = sports_cave_dashboard.get_daily_execution_home_sheets(user, date(2026, 7, 23))
        self.assertEqual(home["today"]["status"], "active")
        self.assertEqual([call[0] for call in backend.daily_calls], ["home"])

    def test_couldnt_finish_tasks_are_selective_carryover_candidates(self):
        sheet = sports_cave_dashboard._normalise_daily_sheet(
            {
                "id": "today",
                "sheet_date": "2026-07-22",
                "top_tasks": [
                    {"task": "Carry me", "status": "couldnt_finish", "why": "Blocked"},
                    {"task": "Done task", "status": "done"},
                ],
                "additional_items": [{"task": "Carry other", "status": "couldnt_finish"}],
            }
        )
        candidates = sports_cave_dashboard.daily_execution_unfinished_tasks(sheet)
        self.assertEqual([item["task"] for item in candidates], ["Carry me", "Carry other"])
        self.assertNotIn("Done task", [item["task"] for item in candidates])

    def test_archive_week_summary_and_detail_are_separate_queries(self):
        backend = FakeDashboardBackend()
        user = owner_user()
        backend.daily_sheets.append(
            {
                "id": "archive-1",
                "user_id": "admin-1",
                "sheet_date": "2026-07-21",
                "status": "archived",
                "top_tasks": [{"task": "Launch", "status": "done", "time_blocked": "2 hours"}],
                "additional_items": [],
                "ratings": {"Overall Score": 8},
            }
        )
        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=backend):
            rows = sports_cave_dashboard.list_daily_execution_archive_summaries(user, date(2026, 7, 20), date(2026, 7, 26))
            self.assertFalse(any(call[0] == "detail" for call in backend.daily_calls))
            detail = sports_cave_dashboard.get_daily_execution_archive_detail(user, "archive-1")
        self.assertEqual(rows[0]["id"], detail["id"])
        self.assertEqual(sum(call[0] == "detail" for call in backend.daily_calls), 1)

    def test_weekly_execution_summary_is_deterministic(self):
        sheets = [
            {
                "id": "one",
                "sheet_date": "2026-07-21",
                "status": "archived",
                "top_tasks": [
                    {"task": "A", "status": "done", "time_blocked": "2 hours"},
                    {"task": "B", "status": "couldnt_finish", "time_blocked": "90m"},
                    {"task": "C", "status": "done", "time_blocked": "1 hour"},
                ],
                "additional_items": [{"task": "Small", "status": "done", "time_blocked": "30m"}],
                "ratings": {"Overall Score": 8},
                "review_data": {"worked_well": "Launch shipped", "could_not_finish": "Supplier delay"},
                "planning_data": {"carried_forward": [{"task": "B"}]},
            },
            {
                "id": "two",
                "sheet_date": "2026-07-22",
                "status": "reviewed",
                "top_tasks": [{"task": "B", "status": "couldnt_finish", "time_blocked": "1 hour"}],
                "additional_items": [],
                "ratings": {"Overall Score": 6},
                "review_data": {"could_not_finish": "Supplier delay"},
                "planning_data": {"carried_forward": [{"task": "B"}]},
            },
        ]
        summary = sports_cave_dashboard.daily_execution_weekly_summary(sheets)
        self.assertEqual(summary["days_planned"], 2)
        self.assertEqual(summary["days_reviewed"], 2)
        self.assertEqual(summary["mip_completed"], 2)
        self.assertEqual(summary["mip_not_completed"], 1)
        self.assertEqual(summary["other_completed"], 1)
        self.assertEqual(summary["total_planned"], 4)
        self.assertEqual(summary["completed"], 3)
        self.assertEqual(summary["did_not_finish"], 1)
        self.assertEqual(summary["completion_percentage"], 75.0)
        self.assertEqual(summary["planned_hours"], 4.5)
        self.assertEqual(summary["average_day_rating"], 7.0)
        self.assertEqual(summary["repeated_carryovers"], ["B"])

    def test_home_execution_bundle_uses_one_backend_query_and_warm_cache(self):
        backend = FakeDashboardBackend()
        user = owner_user()
        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=backend):
            sports_cave_dashboard.get_daily_execution_home_sheets(user, date(2026, 7, 22))
            sports_cave_dashboard.get_daily_execution_home_sheets(user, date(2026, 7, 22))
        self.assertEqual([call[0] for call in backend.daily_calls], ["home"])

    def test_plan_save_invalidates_only_the_affected_execution_week(self):
        backend = FakeDashboardBackend()
        user = owner_user()
        top_tasks = [{"task": f"MIP {index}", "why": "Revenue", "time_blocked": "1h"} for index in range(1, 4)]
        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=backend), patch(
            "activity_log.get_activity_actor", return_value="Nathan"
        ):
            sports_cave_dashboard.list_daily_execution_archive_summaries(user, date(2026, 7, 20), date(2026, 7, 26))
            sports_cave_dashboard.list_daily_execution_archive_summaries(user, date(2026, 7, 27), date(2026, 8, 2))
            sports_cave_dashboard.save_daily_execution_plan(
                user, date(2026, 7, 23), "Australia/Sydney", top_tasks, [], {}
            )
            sports_cave_dashboard.list_daily_execution_archive_summaries(user, date(2026, 7, 20), date(2026, 7, 26))
            sports_cave_dashboard.list_daily_execution_archive_summaries(user, date(2026, 7, 27), date(2026, 8, 2))
        week_calls = [call for call in backend.daily_calls if call[0] == "week"]
        self.assertEqual(len(week_calls), 3)
        self.assertEqual(sum(call[2] == "2026-07-27" for call in week_calls), 1)

    def test_daily_planner_ui_contains_planning_and_reporting_history_flow(self):
        source = (ROOT / "components" / "daily_planner" / "index.html").read_text(encoding="utf-8")
        reporting_source = (ROOT / "reporting_page.py").read_text(encoding="utf-8")
        self.assertIn("Save today's plan", source)
        self.assertIn("Main outcome for the day", source)
        self.assertIn("Appointment, deadline or fixed event", source)
        self.assertIn("Carryover from", source)
        self.assertIn("Daily Execution History", reporting_source)
        self.assertIn("render_weekly_review_page", reporting_source)
        self.assertIn("/api/os/daily-planner/history", source)

    def test_plan_tomorrow_button_opens_editable_window_form(self):
        source = (ROOT / "components" / "daily_planner" / "index.html").read_text(encoding="utf-8")
        self.assertIn("Plan tomorrow", source)
        self.assertIn('loadPlanner(addDays(state.bundle.work_date,1))', source)
        self.assertIn("Save tomorrow's plan", source)
        self.assertIn("Main outcome for the day", source)
        self.assertIn("Appointment, deadline or fixed event", source)

    def test_dashboard_schema_setup_is_not_repeated_on_warm_calls(self):
        calls = []

        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def execute(self, statement, _params=None):
                calls.append(str(statement))

        class Connection:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def cursor(self):
                return Cursor()

            def commit(self):
                return None

        old_ready = supabase_backend._DASHBOARD_SCHEMA_READY
        old_full_ready = supabase_backend._SCHEMA_READY
        try:
            supabase_backend._DASHBOARD_SCHEMA_READY = False
            supabase_backend._SCHEMA_READY = False
            with patch.object(supabase_backend, "is_configured", return_value=True), patch.object(
                supabase_backend, "connect", side_effect=lambda: Connection()
            ):
                supabase_backend.ensure_dashboard_schema()
                first_count = len(calls)
                supabase_backend.ensure_dashboard_schema()
            self.assertGreater(first_count, 0)
            self.assertEqual(len(calls), first_count)
        finally:
            supabase_backend._DASHBOARD_SCHEMA_READY = old_ready
            supabase_backend._SCHEMA_READY = old_full_ready

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

    def test_design_ideas_prompt_uses_selected_sport_mix_and_exact_csv_schema(self):
        mix = sports_cave_dashboard.suggest_design_idea_style_mix("NFL", 10)

        prompt = sports_cave_dashboard.build_new_design_ideas_prompt(
            "NFL",
            10,
            mix,
            exclude_existing=True,
            calendar_relevance=True,
        )

        self.assertIn("exactly 10 new NFL collector-art concepts", prompt)
        self.assertIn("Use the connected Shopify account in read-only mode", prompt)
        self.assertIn("Do not create, edit, publish, archive or delete anything in Shopify", prompt)
        self.assertIn("must not duplicate existing Sports Cave products", prompt)
        self.assertIn("Upcoming anniversaries", prompt)
        self.assertIn(",".join(sports_cave_dashboard.TASK_IMPORT_CSV_COLUMNS), prompt)
        self.assertIn("Every concept must contain either one principal person or two principal people", prompt)
        for style_slug, style_label in sports_cave_dashboard.DESIGN_IDEA_STYLE_FIELDS:
            self.assertIn(
                f"{style_label} (CSV design_style: {style_slug}): {mix[style_slug]}",
                prompt,
            )

    def test_design_ideas_prompt_builder_makes_no_database_or_shopify_call(self):
        mix = sports_cave_dashboard.suggest_design_idea_style_mix(
            "Formula 1 / Motorsport",
            8,
        )

        with patch.object(sports_cave_dashboard, "get_supabase_backend") as backend:
            prompt = sports_cave_dashboard.build_new_design_ideas_prompt(
                "Formula 1 / Motorsport",
                8,
                mix,
            )

        backend.assert_not_called()
        self.assertIn("Formula 1 / Motorsport", prompt)
        self.assertNotIn("DATABASE_URL", prompt)

    def test_suggested_design_mix_is_exact_and_sport_appropriate(self):
        for sport in sports_cave_dashboard.DESIGN_IDEA_SPORTS:
            for total in (1, 10, 30):
                with self.subTest(sport=sport, total=total):
                    mix = sports_cave_dashboard.suggest_design_idea_style_mix(
                        sport,
                        total,
                    )
                    self.assertEqual(sum(mix.values()), total)
                    self.assertEqual(
                        set(mix),
                        set(sports_cave_dashboard.DESIGN_IDEA_STYLE_SLUGS),
                    )

        motorsport = sports_cave_dashboard.suggest_design_idea_style_mix(
            "Formula 1 / Motorsport",
            10,
        )
        nfl = sports_cave_dashboard.suggest_design_idea_style_mix("NFL", 10)
        horse_racing = sports_cave_dashboard.suggest_design_idea_style_mix(
            "Horse Racing",
            10,
        )
        self.assertGreater(
            motorsport["motorsport_driver_car"],
            motorsport["rivalry_faceoff"],
        )
        self.assertEqual(nfl["motorsport_driver_car"], 0)
        self.assertEqual(horse_racing["motorsport_driver_car"], 0)

    def test_design_ideas_prompt_rejects_mismatched_allocation(self):
        with self.assertRaisesRegex(ValueError, "currently allocated 0"):
            sports_cave_dashboard.build_new_design_ideas_prompt(
                "NBA",
                10,
                {},
            )

    def test_design_ideas_prompt_reflects_disabled_research_controls(self):
        mix = sports_cave_dashboard.suggest_design_idea_style_mix("Golf", 4)

        prompt = sports_cave_dashboard.build_new_design_ideas_prompt(
            "Golf",
            4,
            mix,
            exclude_existing=False,
            calendar_relevance=False,
        )

        self.assertIn("Existing-product exclusion is not a mandatory gate", prompt)
        self.assertIn("Do not use current calendar or news relevance", prompt)

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

        self.assertEqual(greeting, "Good morning, Nathan :)")

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
            "Good morning, Nathan :)",
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
            "Good night, Maria :)",
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

    def test_activity_table_record_uses_new_audit_metadata_columns(self):
        record = sports_cave_dashboard.activity_table_record(
            {
                "action_type": "certificate_upload_failed",
                "message": "Certificate upload failed: #SC1234 #012",
                "page": "Orders",
                "actor": "Reina",
                "created_at": "2026-07-21T00:00:00+00:00",
                "metadata": {
                    "product": "Legacy Montana vs Marino",
                    "status": "failed",
                    "error": "Shopify upload failed",
                },
            },
            ZoneInfo("Australia/Sydney"),
        )

        self.assertEqual(record["Action"], "Certificate failed")
        self.assertEqual(record["Page/Area"], "Orders")
        self.assertEqual(record["Item or Product"], "Legacy Montana vs Marino")
        self.assertEqual(record["Result/Status"], "failed")
        self.assertIn("AEST", record["Time"])

    def test_activity_filters_sort_and_search_are_client_side(self):
        records = [
            {
                "Action": "Task completed",
                "User": "Reina",
                "Page/Area": "Dashboard",
                "Item or Product": "NFL",
                "Details": "Finished NFL",
                "Result/Status": "success",
                "Sort Timestamp": datetime(2026, 7, 21, 2, tzinfo=timezone.utc),
            },
            {
                "Action": "Certificate failed",
                "User": "Nathan",
                "Page/Area": "Orders",
                "Item or Product": "SC1234",
                "Details": "Upload failed",
                "Result/Status": "failed",
                "Sort Timestamp": datetime(2026, 7, 21, 1, tzinfo=timezone.utc),
            },
        ]

        filtered = sports_cave_dashboard.filter_activity_records(
            records,
            user="All",
            action="All",
            area="Orders",
            status="failed",
            search="upload",
        )
        sorted_rows = sports_cave_dashboard.sort_activity_records(
            records,
            sports_cave_dashboard.ACTIVITY_SORT_USER_ASC,
        )

        self.assertEqual([row["Action"] for row in filtered], ["Certificate failed"])
        self.assertEqual([row["User"] for row in sorted_rows], ["Nathan", "Reina"])

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


    def test_exact_19_row_design_csv_handles_bom_crlf_quoting_and_optional_blanks(self):
        rows = representative_nfl_design_rows()
        output = io.StringIO(newline="")
        writer = csv.DictWriter(
            output,
            fieldnames=sports_cave_dashboard.TASK_IMPORT_CSV_COLUMNS,
            lineterminator="\r\n",
        )
        writer.writeheader()
        writer.writerows(rows)
        source = b"\xef\xbb\xbf" + output.getvalue().encode("utf-8")

        preview = sports_cave_dashboard.preview_task_csv_import(
            source,
            "sports-cave-nfl-bestseller-designs-import-ready.csv",
            existing_tasks=[],
        )

        self.assertEqual(preview["total_row_count"], 19)
        self.assertEqual(preview["valid_count"], 19)
        self.assertEqual(preview["invalid_count"], 0)
        first = preview["tasks"][0]["values"]
        self.assertEqual(first["task"], rows[0]["task"])
        self.assertEqual(first["design_style"], "legends_jersey_display")
        self.assertEqual(first["venue_location"], "Historic Stadium, USA")
        self.assertIn("\nKeep the composition", first["special_instructions"])
        self.assertEqual(first["due_date"], "")
        solo = preview["tasks"][1]["values"]
        self.assertEqual(solo["principal_subject_two"], "")
        self.assertIn("1990–1999", first["season_era"])
        self.assertIn("—", first["event_moment"])

    def test_soft_deleted_19_row_import_reactivates_then_is_idempotent(self):
        rows = representative_nfl_design_rows()
        source = task_csv_bytes(rows)
        initial_preview = sports_cave_dashboard.preview_task_csv_import(
            source,
            "nfl.csv",
            existing_tasks=[],
        )
        backend = FakeDashboardBackend()
        backend.tasks = [
            {
                "id": f"stable-{index:02d}",
                "title": candidate["title"],
                "section": candidate["section"],
                "status": "deleted",
                "created_at": "2026-08-10T00:00:00+00:00",
                "design_style": candidate["metadata"]["design_style"],
                "metadata": {
                    **copy.deepcopy(candidate["metadata"]),
                    "deleted_at": "2026-08-13T00:00:00+00:00",
                    "deleted_by": "Nathan",
                },
            }
            for index, candidate in enumerate(initial_preview["tasks"], start=1)
        ]
        stable_ids = [task["id"] for task in backend.tasks]

        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=backend), patch(
            "activity_log.record_activity_log"
        ):
            preview = sports_cave_dashboard.preview_task_csv_import(
                source,
                "nfl.csv",
                existing_tasks=sports_cave_dashboard.list_tasks(status="all"),
            )
            first = sports_cave_dashboard.import_task_csv_preview(preview)
            visible = sports_cave_dashboard.list_tasks(status="open")
            second_preview = sports_cave_dashboard.preview_task_csv_import(
                source,
                "nfl.csv",
                existing_tasks=sports_cave_dashboard.list_tasks(status="all"),
            )
            second = sports_cave_dashboard.import_task_csv_preview(second_preview)

        self.assertEqual(preview["reactivate_count"], 19)
        self.assertEqual(preview["new_count"], 0)
        self.assertEqual(first["reactivated_count"], 19)
        self.assertEqual(first["created_count"], 0)
        self.assertEqual(first["failed_count"], 0)
        self.assertEqual([task["id"] for task in backend.tasks], stable_ids)
        self.assertTrue(all(task["status"] == "open" for task in backend.tasks))
        self.assertEqual(len(visible), 19)
        self.assertEqual(second_preview["active_duplicate_count"], 19)
        self.assertEqual(second_preview["valid_count"], 0)
        self.assertEqual(second["imported_count"], 0)
        self.assertEqual(second["active_duplicate_count"], 19)
        self.assertEqual(len(backend.tasks), 19)
        for expected, task in zip(rows, backend.tasks):
            persisted = sports_cave_dashboard.task_csv_values(task)
            self.assertEqual(persisted["design_title"], expected["design_title"])
            self.assertEqual(persisted["special_instructions"], expected["special_instructions"])

    def test_active_and_completed_duplicates_are_classified_without_mutation(self):
        rows = representative_nfl_design_rows(2)
        fresh = sports_cave_dashboard.preview_task_csv_import(task_csv_bytes(rows), "nfl.csv", existing_tasks=[])
        existing = []
        for status, candidate in zip(("open", "complete"), fresh["tasks"]):
            existing.append(
                {
                    "id": f"{status}-id",
                    "title": candidate["title"],
                    "section": candidate["section"],
                    "status": status,
                    "design_style": candidate["metadata"]["design_style"],
                    "metadata": copy.deepcopy(candidate["metadata"]),
                }
            )
        preview = sports_cave_dashboard.preview_task_csv_import(
            task_csv_bytes(rows),
            "nfl.csv",
            existing_tasks=existing,
        )
        self.assertEqual(preview["active_duplicate_count"], 1)
        self.assertEqual(preview["completed_duplicate_count"], 1)
        self.assertEqual(preview["valid_count"], 0)
        self.assertEqual(existing[1]["status"], "complete")

    def test_failed_batch_transaction_never_reports_success(self):
        class FailingBackend(FakeDashboardBackend):
            def import_dashboard_tasks_batch(self, candidates, *, actor="sports_cave_os"):
                raise RuntimeError("database transaction rolled back")

        preview = sports_cave_dashboard.preview_task_csv_import(
            task_csv_bytes(representative_nfl_design_rows(1)),
            "nfl.csv",
            existing_tasks=[],
        )
        with patch.object(
            sports_cave_dashboard,
            "get_supabase_backend",
            return_value=FailingBackend(),
        ):
            with self.assertRaises(sports_cave_dashboard.DashboardStorageError):
                sports_cave_dashboard.import_task_csv_preview(preview)

    def test_task_table_contains_all_design_fields_and_filters_without_mutating_ids(self):
        preview = sports_cave_dashboard.preview_task_csv_import(
            task_csv_bytes(representative_nfl_design_rows(3)),
            "nfl.csv",
            existing_tasks=[],
        )
        tasks = [
            {
                "id": f"id-{index}",
                "title": candidate["title"],
                "section": candidate["section"],
                "status": "open",
                "created_at": f"2026-08-{index + 1:02d}T00:00:00+00:00",
                "design_style": candidate["metadata"]["design_style"],
                "metadata": candidate["metadata"],
            }
            for index, candidate in enumerate(preview["tasks"])
        ]
        table = sports_cave_dashboard.task_table_rows(
            tasks,
            sports_cave_dashboard.DESIGN_TASK_GROUP,
        )
        self.assertEqual(len(table), 3)
        self.assertTrue(set(sports_cave_dashboard.TASK_IMPORT_CSV_COLUMNS).issubset(table[0]))
        self.assertEqual(table[0]["_task_id"], "id-0")
        filtered = sports_cave_dashboard.filter_task_table_rows(
            table,
            search="Historic Stadium",
            design_style="legends_jersey_display",
            sport="American Football",
            priority="High",
        )
        self.assertEqual([row["_task_id"] for row in filtered], ["id-0"])

    def test_batch_backend_uses_one_locked_transaction_and_in_place_reactivation(self):
        source = (ROOT / "supabase_backend.py").read_text(encoding="utf-8")
        batch_source = source[
            source.index("def import_dashboard_tasks_batch") :
            source.index("\n\ndef create_dashboard_task")
        ]
        self.assertIn("LOCK TABLE dashboard_tasks IN SHARE ROW EXCLUSIVE MODE", batch_source)
        self.assertIn("WHERE id=%s AND status IN ('deleted', 'archived')", batch_source)
        self.assertIn("status='open'", batch_source)
        self.assertIn("completed_at=NULL", batch_source)
        self.assertIn("conn.commit()", batch_source)
        self.assertNotIn("DELETE FROM dashboard_tasks", batch_source)


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
    def test_admin_home_renders_events_and_weekly_work_without_design_queries(self):
        backend = FakeDashboardBackend()
        today = datetime.now(ZoneInfo("Australia/Sydney")).date().isoformat()
        backend.daily_sheets = [
            {
                "id": "admin-today",
                "user_id": "admin-1",
                "user_name": "Nathan",
                "sheet_date": today,
                "timezone": "Australia/Sydney",
                "status": "active",
                "top_tasks": [
                    {"task": "Priority one", "status": "done"},
                    {"task": "Priority two", "status": "done"},
                    {"task": "Priority three", "status": "done"},
                ],
                "additional_items": [{"task": "Other task", "status": "done"}],
                "ratings": {},
                "review_data": {},
                "no_grey_zone": {},
            }
        ]
        backend.tasks = [
            {
                "id": "design-hidden-from-home",
                "title": "Hidden design workflow",
                "section": sports_cave_dashboard.DESIGN_TASK_GROUP,
                "status": "open",
                "created_at": "2026-08-13T00:00:00+00:00",
            }
        ]
        app_test = AppTest.from_file(str(ROOT / "app.py"))
        app_test.session_state["sports_cave_authenticated"] = True
        app_test.session_state["sports_cave_current_user"] = owner_user()
        app_test.session_state["sports_cave_auth_checked_at"] = wall_time.monotonic()
        app_test.session_state["selected_page"] = "Dashboard"

        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=backend):
            app_test.run(timeout=20)

        button_labels = {button.label for button in app_test.button}
        self.assertFalse(app_test.exception)
        self.assertEqual(backend.task_status_calls, [])
        self.assertNotIn("Generate Ideas", button_labels)
        self.assertNotIn("Import CSV", button_labels)
        self.assertNotIn("CSV Template", button_labels)
        self.assertNotIn("Export CSV", button_labels)
        self.assertNotIn("Add Task", button_labels)
        self.assertFalse(
            any("Design title" in dataframe.value.columns for dataframe in app_test.dataframe)
        )
        rendered = "\n".join(str(item.value) for item in app_test.markdown)
        self.assertIn("Active &amp; Upcoming Events", rendered)
        self.assertIn("This Week&#x27;s Work", rendered)
        self.assertNotIn("Daily Execution", rendered)
        self.assertNotIn("MIP Task 1", rendered)
        self.assertNotIn("Other tasks", rendered)
        self.assertNotIn("Daily Execution Archive", rendered)
        self.assertNotIn("Recent operational activity", rendered)
        self.assertFalse(any(button.label == "Complete Daily Review" for button in app_test.button))

    def test_non_admin_home_remains_planner_free_with_forged_planner_session_state(self):
        backend = FakeDashboardBackend()
        app_test = AppTest.from_file(str(ROOT / "app.py"))
        app_test.session_state["sports_cave_authenticated"] = True
        app_test.session_state["sports_cave_current_user"] = {
            "id": "worker-1",
            "username": "worker",
            "email": "worker@sportscave.test",
            "display_name": "Worker",
            "role": "worker",
            "timezone": "Asia/Manila",
            "is_active": True,
            "page_permissions": ["dashboard"],
        }
        app_test.session_state["sports_cave_auth_checked_at"] = wall_time.monotonic()
        app_test.session_state["selected_page"] = "Dashboard"
        app_test.session_state["daily_execution_plan_date"] = date.today().isoformat()
        app_test.session_state["daily_execution_review_sheet_id"] = "forged-sheet-id"

        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=backend):
            app_test.run(timeout=20)

        self.assertFalse(app_test.exception)
        self.assertEqual(backend.daily_calls, [])
        rendered = "\n".join(str(item.value) for item in app_test.markdown)
        self.assertIn("Active &amp; Upcoming Events", rendered)
        self.assertIn("This Week&#x27;s Work", rendered)
        self.assertNotIn("Daily Execution", rendered)
        self.assertNotIn("Daily Execution Archive", rendered)
        self.assertNotIn("Sports & Sales Calendar", rendered)
        planner_labels = {
            "Create today's sheet",
            "Save List",
            "Complete Daily Review",
            "Plan tomorrow",
        }
        self.assertFalse(planner_labels.intersection({button.label for button in app_test.button}))

    def test_design_schedule_queries_and_renders_only_the_visible_view(self):
        backend = FakeDashboardBackend()
        backend.tasks = [
            {
                "id": "active-design",
                "title": "Active design",
                "section": sports_cave_dashboard.DESIGN_TASK_GROUP,
                "status": "open",
                "created_at": "2026-08-13T00:00:00+00:00",
            },
            {
                "id": "collection-task",
                "title": "Refresh NFL collection",
                "section": sports_cave_dashboard.COLLECTIONS_TASK_GROUP,
                "status": "open",
                "created_at": "2026-08-13T01:00:00+00:00",
            },
            {
                "id": "completed-design",
                "title": "Completed design",
                "section": sports_cave_dashboard.DESIGN_TASK_GROUP,
                "status": "complete",
                "created_at": "2026-08-12T00:00:00+00:00",
            },
        ]
        sports_cave_dashboard.clear_task_cache()
        app_test = AppTest.from_file(str(ROOT / "app.py"))
        app_test.session_state["sports_cave_authenticated"] = True
        app_test.session_state["sports_cave_current_user"] = owner_user()
        app_test.session_state["sports_cave_auth_checked_at"] = wall_time.monotonic()
        app_test.session_state["selected_page"] = "Design Studio"

        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=backend):
            app_test.run(timeout=20)
            self.assertEqual(backend.task_status_calls, ["open"])
            self.assertEqual(len(app_test.dataframe), 1)
            self.assertIn("Design title", app_test.dataframe[0].value.columns)

            app_test.session_state["design-schedule-view"] = "Collections"
            app_test.run(timeout=20)

        self.assertFalse(app_test.exception)
        self.assertEqual(backend.task_status_calls, ["open", "open"])
        self.assertEqual(len(app_test.dataframe), 1)
        self.assertIn("Refresh NFL collection", app_test.dataframe[0].value["Task"].tolist())
        self.assertNotIn("Active design", app_test.dataframe[0].value["Task"].tolist())

    def test_imported_design_task_handoff_and_unified_save_work_in_streamlit(self):
        backend = FakeDashboardBackend()
        first_details = {
            "design_title": "The Mountain Rivals",
            "sport": "Motorsport",
            "principal_subject_one": "Peter Brock",
            "principal_subject_two": "Allan Moffat",
            "team_country": "Australia",
            "season_era": "1970s",
            "event_moment": "Bathurst rivalry",
            "venue_location": "Mount Panorama",
            "uniform_equipment_livery": "Correct period suits and liveries",
            "essential_text": "BROCK VS MOFFAT",
            "special_instructions": "Equal hero scale",
        }
        backend.tasks.extend(
            [
                {
                    "id": "design-one",
                    "title": "Create Brock versus Moffat rivalry",
                    "section": sports_cave_dashboard.DESIGN_TASK_GROUP,
                    "status": "open",
                    "created_at": "2026-08-13T00:00:00+00:00",
                    "design_style": "rivalry_faceoff",
                    "metadata": {
                        "design_style": "rivalry_faceoff",
                        sports_cave_dashboard.DESIGN_DETAILS_METADATA_KEY: first_details,
                    },
                },
                {
                    "id": "design-two",
                    "title": "Restore archival finish",
                    "section": sports_cave_dashboard.DESIGN_TASK_GROUP,
                    "status": "open",
                    "created_at": "2026-08-13T01:00:00+00:00",
                    "design_style": "vintage_restoration",
                    "metadata": {"design_style": "vintage_restoration"},
                },
            ]
        )
        sports_cave_dashboard.clear_task_cache()
        app_test = AppTest.from_file(str(ROOT / "app.py"))
        app_test.session_state["sports_cave_authenticated"] = True
        app_test.session_state["sports_cave_current_user"] = owner_user()
        app_test.session_state["sports_cave_auth_checked_at"] = wall_time.monotonic()
        app_test.session_state["selected_page"] = "Design Studio"
        app_test.session_state["design-schedule-row::active-designs"] = "design-one"

        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=backend):
            app_test.run(timeout=20)
            next(
                button
                for button in app_test.button
                if button.key == "design-schedule-open::active-designs"
            ).click().run(timeout=20)
            self.assertEqual(
                app_test.session_state.filtered_state.get(
                    design_schedule.SELECTED_DESIGN_TASK_KEY
                ),
                "design-one",
            )
            self.assertTrue(
                {
                    "Design details",
                    "Research Prompt",
                    "Find Images Prompt",
                    "Design Generation Prompt",
                    "Harsh Review",
                }.issubset({expander.label for expander in app_test.expander})
            )
            field_values = {widget.label: widget.value for widget in app_test.text_input}
            text_area_values = {widget.label: widget.value for widget in app_test.text_area}

            self.assertEqual(field_values["Design title"], first_details["design_title"])
            self.assertEqual(field_values["Principal subject one"], "Peter Brock")
            self.assertEqual(field_values["Principal subject two"], "Allan Moffat")
            self.assertEqual(text_area_values["Special instructions"], "Equal hero scale")

            next(
                widget for widget in app_test.text_area if widget.label == "Special instructions"
            ).set_value("Equal heroes with restrained atmosphere")
            next(
                button for button in app_test.button if button.label == "Save design details"
            ).click().run(timeout=20)
            self.assertEqual(
                backend.tasks[0]["metadata"][sports_cave_dashboard.DESIGN_DETAILS_METADATA_KEY][
                    "special_instructions"
                ],
                "Equal heroes with restrained atmosphere",
            )

            app_test.session_state["design-schedule-row::active-designs"] = "design-two"
            app_test.run(timeout=20)
            next(
                button
                for button in app_test.button
                if button.key == "design-schedule-open::active-designs"
            ).click().run(timeout=20)
            second_values = {widget.label: widget.value for widget in app_test.text_input}
            self.assertEqual(second_values["Design title"], "")
            self.assertEqual(second_values["Principal subject one"], "")

            app_test.session_state["design-schedule-row::active-designs"] = "design-one"
            app_test.run(timeout=20)
            next(
                button
                for button in app_test.button
                if button.key == "design-schedule-open::active-designs"
            ).click().run(timeout=20)
            self.assertEqual(
                app_test.session_state.filtered_state.get(
                    design_schedule.SELECTED_DESIGN_TASK_KEY
                ),
                "design-one",
            )
            self.assertTrue(
                {
                    "Research Prompt",
                    "Find Images Prompt",
                    "Design Generation Prompt",
                    "Harsh Review",
                }.issubset({expander.label for expander in app_test.expander})
            )
            self.assertNotIn(
                "design-studio-scroll-to-workflow",
                app_test.session_state.filtered_state,
            )

        self.assertFalse(app_test.exception)

    def test_design_studio_idea_controls_validate_mix_and_prepare_prompt(self):
        backend = FakeDashboardBackend()
        app_test = AppTest.from_file(str(ROOT / "app.py"))
        app_test.session_state["sports_cave_authenticated"] = True
        app_test.session_state["sports_cave_current_user"] = owner_user()
        app_test.session_state["sports_cave_auth_checked_at"] = wall_time.monotonic()
        app_test.session_state["selected_page"] = "Design Studio"

        with patch.object(
            sports_cave_dashboard,
            "get_supabase_backend",
            return_value=backend,
        ):
            app_test.run(timeout=20)
            next(
                button for button in app_test.button if button.label == "Generate Ideas"
            ).click().run(timeout=20)
            next(
                item for item in app_test.selectbox if item.label == "Sport or collection"
            ).select("NBA").run(timeout=20)
            next(
                item for item in app_test.number_input if item.label == "Number of design ideas"
            ).set_value(11).run(timeout=20)
            prepare = next(
                button for button in app_test.button if button.label == "Prepare Design Brief"
            )
            self.assertTrue(prepare.disabled)

            next(
                button for button in app_test.button if button.label == "Suggest Best Mix"
            ).click().run(timeout=20)
            style_labels = {
                label for _slug, label in sports_cave_dashboard.DESIGN_IDEA_STYLE_FIELDS
            }
            allocated = sum(
                int(item.value)
                for item in app_test.number_input
                if item.label in style_labels
            )
            self.assertEqual(allocated, 11)

            next(
                button for button in app_test.button if button.label == "Prepare Design Brief"
            ).click().run(timeout=20)
            prompt = next(
                item for item in app_test.text_area if item.label == "Design brief prompt"
            )
            self.assertIn("exactly 11 new NBA", prompt.value)
            self.assertTrue(prompt.disabled)

        self.assertFalse(app_test.exception)

    def test_design_studio_design_delete_cancel_and_confirm(self):
        backend = FakeDashboardBackend()
        backend.tasks = [
            {
                "id": "design-delete-1",
                "title": "Create NFL design - THE DRIVE",
                "section": sports_cave_dashboard.DESIGN_TASK_GROUP,
                "status": "open",
                "created_at": "2026-08-13T08:00:00+00:00",
                "design_style": "ultimate_moment",
                "metadata": {
                    "design_style": "ultimate_moment",
                    sports_cave_dashboard.DESIGN_DETAILS_METADATA_KEY: {
                        "design_title": "THE DRIVE",
                        "sport": "NFL",
                    },
                },
            }
        ]
        app_test = AppTest.from_file(str(ROOT / "app.py"))
        app_test.session_state["sports_cave_authenticated"] = True
        app_test.session_state["sports_cave_current_user"] = owner_user()
        app_test.session_state["sports_cave_auth_checked_at"] = wall_time.monotonic()
        app_test.session_state["selected_page"] = "Design Studio"
        app_test.session_state["design-schedule-row::active-designs"] = "design-delete-1"

        with patch.object(
            sports_cave_dashboard,
            "get_supabase_backend",
            return_value=backend,
        ):
            app_test.run(timeout=20)
            trigger_key = "design-schedule-delete::active-designs"
            next(button for button in app_test.button if button.key == trigger_key).click().run(
                timeout=20
            )
            self.assertIsNotNone(
                next(
                    button
                    for button in app_test.button
                    if button.key == "design-schedule-delete-confirm::design-delete-1"
                )
            )
            self.assertEqual(backend.tasks[0]["status"], "open")
            next(
                button
                for button in app_test.button
                if button.key == "design-schedule-delete-cancel::design-delete-1"
            ).click().run(timeout=20)
            self.assertEqual(backend.tasks[0]["status"], "open")

            next(button for button in app_test.button if button.key == trigger_key).click().run(
                timeout=20
            )
            next(
                button
                for button in app_test.button
                if button.key == "design-schedule-delete-confirm::design-delete-1"
            ).click().run(timeout=20)

        self.assertEqual(backend.tasks[0]["status"], "deleted")
        self.assertFalse(app_test.exception)

    def test_design_schedule_requires_a_style_and_renders_style_labels(self):
        source = (ROOT / "design_schedule.py").read_text(encoding="utf-8")

        self.assertIn("DESIGN_TASK_TABLE_COLUMNS", source)
        self.assertIn("design_studio_styles.design_style_label", source)
        self.assertIn('"Design style"', source)
        self.assertIn("design_studio_styles.style_slugs()", source)
        self.assertIn("design_style=design_style", source)
        self.assertNotIn('st.form("dashboard-add-task"', source)

    def test_new_design_queue_is_compact_full_width_and_keeps_style_in_details(self):
        render_source = (ROOT / "design_schedule.py").read_text(encoding="utf-8")
        self.assertIn("task_table_rows(tasks, section)", render_source)
        self.assertIn("st.dataframe(", render_source)
        self.assertIn('height=420', render_source)
        self.assertIn('row_height=34', render_source)
        self.assertIn('selection_mode="single-row"', render_source)
        self.assertIn('"View/Edit Details"', render_source)
        self.assertNotIn("DESIGN_TASK_VISIBLE_LIMIT", render_source)
        self.assertNotIn("overflow_tasks", render_source)
        self.assertNotIn('selectbox(\n                "Assign design style"', render_source)
        self.assertNotIn("dashboard_task_card_html(", render_source)

    def test_open_in_studio_does_not_mount_scroll_lock_or_global_table_css(self):
        schedule_source = (ROOT / "design_schedule.py").read_text(encoding="utf-8")
        studio_source = (ROOT / "design_studio_page.py").read_text(encoding="utf-8")
        studio_renderer = studio_source[
            studio_source.index("def render_design_studio_v2") :
            studio_source.index("\n\ndef render_design_studio_page")
        ]

        self.assertNotIn("design-studio-scroll-to-workflow", schedule_source)
        self.assertNotIn("design-studio-scroll-to-workflow", studio_renderer)
        self.assertNotIn("scrollIntoView", studio_renderer)
        self.assertNotIn("components.html(", studio_renderer)
        self.assertNotIn(
            'div[data-testid="stDataFrame"] { max-width: 100%; overflow: hidden; }',
            schedule_source,
        )
        for selector in ("html", "body", ".stApp", ".block-container"):
            self.assertNotIn(f"{selector} {{ overflow: hidden", schedule_source)
            self.assertNotIn(f"{selector} {{ height:", schedule_source)
        self.assertIn("height=420", schedule_source)
        self.assertIn("row_height=34", schedule_source)

    def test_design_idea_and_manual_task_workflows_open_only_from_design_studio(self):
        source = (ROOT / "design_schedule.py").read_text(encoding="utf-8")
        home_source = (ROOT / "app.py").read_text(encoding="utf-8").split(
            "def render_lightweight_dashboard_page", 1
        )[1].split("\n\ndef page_uses_local_database", 1)[0]

        self.assertIn("SCHEDULE_GENERATOR_OPEN_KEY", source)
        self.assertIn('"Generate Ideas"', source)
        self.assertIn('"Sport or collection"', source)
        self.assertIn('"Number of design ideas"', source)
        self.assertIn('"Suggest Best Mix"', source)
        self.assertIn('"Prepare Design Brief"', source)
        self.assertIn("SCHEDULE_ADD_OPEN_KEY", source)
        self.assertNotIn("render_todays_design_ideas", home_source)
        self.assertNotIn("render_dashboard_tasks", home_source)

    def test_design_delete_ui_requires_confirmation_and_uses_material_icon(self):
        source = (ROOT / "design_schedule.py").read_text(encoding="utf-8")
        dialog_source = source[source.index("def _render_delete_dialog") :]
        row_source = source[source.index("def render_design_schedule") :]

        self.assertIn('icon=":material/delete:"', row_source)
        self.assertIn('help="Delete design"', row_source)
        self.assertIn('st.session_state[SCHEDULE_DELETE_TASK_KEY] = selected_row["_task_id"]', row_source)
        self.assertIn('@st.dialog(f\'Delete "{title}"?\')', dialog_source)
        self.assertIn('"It does not delete anything from Shopify."', dialog_source)
        self.assertIn('"Cancel"', dialog_source)
        self.assertIn('"Delete design"', dialog_source)
        self.assertIn("delete_design_task", dialog_source)

    def test_task_csv_controls_are_inline_and_details_are_compact(self):
        source = (ROOT / "design_schedule.py").read_text(encoding="utf-8")
        header_source = source[source.index("def _render_header") :]
        render_source = source[source.index("def render_design_schedule") :]

        self.assertIn("st.columns([2.1, .78, .68, .72, .68, .62]", header_source)
        self.assertIn('"Import CSV"', header_source)
        self.assertIn('"CSV Template"', header_source)
        self.assertIn('"Export CSV"', header_source)
        self.assertIn(".download_button(", header_source)
        self.assertIn("TASK_IMPORT_TEMPLATE_FILENAME", header_source)
        self.assertIn('key="design-schedule-import-trigger"', header_source)
        self.assertIn('key="design-schedule-export-trigger"', header_source)
        self.assertIn('key="design-schedule-add-trigger"', header_source)
        self.assertNotIn('key="design-schedule-import-open"', header_source)
        self.assertIn('st.dialog("Import Tasks CSV", width="large")', source)
        preview_source = source[source.index("def _render_import_preview") : source.index("\n\ndef _render_import_dialog")]
        self.assertIn("st.dataframe", preview_source)
        for label in (
            "Task title",
            "Section",
            "Design style",
            "Principal subject one",
            "Principal subject two",
            "Intended action",
            "Validation result",
        ):
            self.assertIn(f'"{label}"', preview_source)
        self.assertIn("_load_view_tasks(view)", render_source)
        self.assertIn("filter_task_table_rows", render_source)
        self.assertIn("st.dataframe(", render_source)
        self.assertNotIn("dashboard_task_card_html(", render_source)

    def test_design_schedule_import_trigger_opens_without_session_state_collision(self):
        backend = FakeDashboardBackend()
        app_test = AppTest.from_file(str(ROOT / "app.py"))
        app_test.session_state["sports_cave_authenticated"] = True
        app_test.session_state["sports_cave_current_user"] = owner_user()
        app_test.session_state["sports_cave_auth_checked_at"] = wall_time.monotonic()
        app_test.session_state["selected_page"] = "Design Studio"

        with patch.object(
            sports_cave_dashboard,
            "get_supabase_backend",
            return_value=backend,
        ):
            app_test.run(timeout=20)
            next(button for button in app_test.button if button.label == "Import CSV").click().run(
                timeout=20
            )

        self.assertFalse(app_test.exception)
        self.assertTrue(
            any(uploader.label == "Completed task CSV" for uploader in app_test.file_uploader)
        )

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

    def test_design_task_delete_backend_is_scoped_transactional_and_soft(self):
        source = (ROOT / "supabase_backend.py").read_text(encoding="utf-8")
        delete_source = source[
            source.index("def delete_dashboard_task") :
            source.index("\n\ndef complete_dashboard_task")
        ]

        self.assertIn("SET status='deleted'", delete_source)
        self.assertIn("WHERE id=%s AND section=%s AND status='open'", delete_source)
        self.assertIn('event_type="task_deleted"', delete_source)
        self.assertIn("conn.commit()", delete_source)
        self.assertNotIn("DELETE FROM dashboard_tasks", delete_source)
        self.assertNotIn("shopify", delete_source.casefold())

    def test_dashboard_uses_events_and_weekly_work_without_restoring_planner_or_design_workflow(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        dashboard_source = source[
            source.index("def get_browser_timezone") : source.index("\n\ndef page_uses_local_database")
        ]

        self.assertNotIn("render_custom_calendar_form", dashboard_source)
        self.assertNotIn("dashboard-add-calendar-event", dashboard_source)
        self.assertNotIn("render_physical_calendar", dashboard_source)
        render_body = source[
            source.index("def render_lightweight_dashboard_page") :
            source.index("\n\ndef page_uses_local_database")
        ]
        self.assertIn("render_active_upcoming_events(events, today)", render_body)
        self.assertIn("render_home_weekly_work(user, local_now)", render_body)
        self.assertNotIn("render_home_recent_activity(local_now)", render_body)
        self.assertNotIn("can_manage_daily_planner(user)", render_body)
        self.assertNotIn("render_daily_execution_panel", render_body)
        self.assertNotIn("render_daily_execution_archive", render_body)
        self.assertNotIn("render_sports_sales_calendar", render_body)
        self.assertNotIn("render_dashboard_tasks", render_body)
        self.assertNotIn("render_todays_design_ideas", render_body)
        reporting_route = source[
            source.index('elif current_page == "Reporting"') :
            source.index('elif current_page == "Files"')
        ]
        self.assertIn("get_reporting_page().render_page", reporting_route)
        self.assertIn("render_weekly_review_page", reporting_route)
        self.assertIn("os_accounts.DAILY_PLANNER_ROUTE", reporting_route)

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

        for heading in ("Time", "User", "Action", "Page/Area", "Item or Product", "Details", "Result/Status"):
            self.assertIn(f"<th>{heading}</th>", table_source)
        self.assertIn("activity_table_record", table_source)
        self.assertNotIn("Activity page", table_source)
        self.assertNotIn("ACTIVITY_TABLE_PAGE_SIZE", table_source)
        self.assertNotIn('<div class="sc-log-row">', table_source)

    def test_activity_log_overflow_styles_are_scoped_and_keep_full_values_in_titles(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        table_source = source[
            source.index("def _activity_table_html") :
            source.index("\n\ndef render_activity_log")
        ]
        style_source = source[
            source.index(".sc-activity-table-wrap") :
            source.index("@media (max-width: 760px)")
        ]

        self.assertIn('title="{escaped}"', table_source)
        self.assertIn('class="sc-activity-cell-text"', table_source)
        self.assertIn("overflow-wrap: anywhere", style_source)
        self.assertIn("word-break: break-word", style_source)
        self.assertIn("-webkit-line-clamp: 2", style_source)
        self.assertNotIn("\n        table td {", style_source)

    def test_non_owner_activity_log_has_no_filter_toolbar(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        render_source = source[
            source.index("def render_activity_log") :
            source.index("\n\ndef _daily_archive_row_metrics")
        ]

        self.assertIn('render_html_section_title("Activity log" if is_owner else "My Work Log")', render_source)
        self.assertIn("if is_owner:", render_source)
        self.assertIn('st.caption("Your activity for today")', render_source)
        self.assertGreater(
            render_source.index('filter_cols[0].selectbox(\n            "User"'),
            render_source.index("if is_owner:"),
        )


if __name__ == "__main__":
    unittest.main()
