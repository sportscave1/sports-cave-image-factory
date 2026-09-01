from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import unittest
from unittest import mock

from starlette.requests import Request

import repair_requests
import top_bar
import top_bar_api


ROOT = Path(__file__).resolve().parents[1]
COMPONENT_PATH = ROOT / "components" / "sports_cave_top_bar" / "index.html"


ADMIN = {
    "sub": "admin-1",
    "id": "admin-1",
    "display_name": "Nathan",
    "username": "nathan",
    "role": "admin",
}
WORKER = {
    "sub": "worker-1",
    "id": "worker-1",
    "display_name": "VA One",
    "username": "va-one",
    "role": "worker",
}
BASE_PAYLOAD = {
    "section": "Ads — Creative Refresh",
    "problem_description": "The generated refresh format differs from New Ads.",
    "desired_result": "Use the same normal three-ad production format.",
    "scope_choice": repair_requests.SCOPE_SECTION_ONLY,
    "scope_notes": "Do not change Ads — Posting.",
}


class MemoryRepairStore:
    def __init__(self, rows=None):
        self.rows = rows if rows is not None else []
        self.counter = len(self.rows)

    def create(self, values):
        self.counter += 1
        row = {
            **values,
            "id": f"repair-{self.counter}",
            "status": repair_requests.STATUS_SUBMITTED,
            "created_at": datetime(2026, 9, 1, 2, self.counter, tzinfo=timezone.utc),
            "completed_at": None,
            "completed_by": None,
            "completed_by_name": "",
            "admin_notes": "",
            "generated_prompt_version": repair_requests.PROMPT_VERSION,
        }
        self.rows.append(row)
        return dict(row)

    def recent(self, *, submitted_by=None, limit=5):
        rows = [
            row for row in self.rows
            if not submitted_by or row.get("submitted_by") == submitted_by
        ]
        return sorted(rows, key=lambda row: row["created_at"], reverse=True)[:limit]

    def complete(self, request_id, *, completed_by, completed_by_name, admin_notes=""):
        for row in self.rows:
            if row["id"] == request_id:
                if row["status"] != repair_requests.STATUS_COMPLETE:
                    row["status"] = repair_requests.STATUS_COMPLETE
                    row["completed_at"] = datetime(2026, 9, 3, 1, 0, tzinfo=timezone.utc)
                    row["completed_by"] = completed_by
                    row["completed_by_name"] = completed_by_name
                    row["admin_notes"] = admin_notes
                return dict(row)
        return {}


def stored_request(**overrides):
    return {
        "id": "repair-1",
        "section": BASE_PAYLOAD["section"],
        "request_type": "repair_improvement",
        "problem_description": BASE_PAYLOAD["problem_description"],
        "desired_result": BASE_PAYLOAD["desired_result"],
        "scope_choice": BASE_PAYLOAD["scope_choice"],
        "scope_notes": BASE_PAYLOAD["scope_notes"],
        "submitted_by": WORKER["id"],
        "submitted_by_name": WORKER["display_name"],
        "submitted_by_role": WORKER["role"],
        "status": repair_requests.STATUS_SUBMITTED,
        "created_at": datetime(2026, 9, 1, 0, 30, tzinfo=timezone.utc),
        "completed_at": None,
        "completed_by": None,
        "completed_by_name": "",
        "admin_notes": "",
        "generated_prompt_version": repair_requests.PROMPT_VERSION,
        **overrides,
    }


class RepairPromptTests(unittest.TestCase):
    def test_builder_includes_all_submitted_context_and_protections(self):
        prompt = repair_requests.build_repair_prompt(stored_request())

        self.assertIn("Ads — Creative Refresh", prompt)
        self.assertIn(BASE_PAYLOAD["problem_description"], prompt)
        self.assertIn(BASE_PAYLOAD["desired_result"], prompt)
        self.assertIn("Yes — this section only", prompt)
        self.assertIn(BASE_PAYLOAD["scope_notes"], prompt)
        self.assertIn("Do not push or deploy until explicitly requested.", prompt)
        self.assertIn("DO NOT PUSH.", prompt)
        self.assertIn("DO NOT DEPLOY.", prompt)

    def test_admin_receives_prompt_but_worker_mirror_never_does(self):
        row = stored_request()

        admin_mirror = repair_requests.request_mirror_for_user(row, ADMIN)
        worker_mirror = repair_requests.request_mirror_for_user(row, WORKER)

        self.assertIn("repair_prompt", admin_mirror)
        self.assertNotIn("repair_prompt", worker_mirror)
        self.assertNotIn("problem_description", worker_mirror)
        self.assertNotIn("scope_notes", worker_mirror)
        self.assertEqual(
            {
                "id", "section", "summary", "status", "submitted_date", "completed_date"
            },
            set(worker_mirror),
        )

    def test_worker_cannot_invoke_prompt_or_completion_server_actions(self):
        store = MemoryRepairStore([stored_request()])

        with self.assertRaises(PermissionError):
            repair_requests.repair_prompt_for_user(stored_request(), WORKER)
        with self.assertRaises(PermissionError):
            repair_requests.mark_request_complete("repair-1", WORKER, store=store)


class RepairPersistenceTests(unittest.TestCase):
    def test_storage_errors_distinguish_missing_schema_from_temporary_database_failure(self):
        class DatabaseError(Exception):
            def __init__(self, sqlstate):
                super().__init__("database error")
                self.sqlstate = sqlstate

        store = repair_requests.PostgresRepairRequestStore()

        self.assertIsInstance(
            store._storage_error(DatabaseError("42P01")),
            repair_requests.RepairRequestStorageMissing,
        )
        self.assertIsInstance(
            store._storage_error(DatabaseError("08006")),
            repair_requests.RepairRequestStorageTemporary,
        )

    def test_submission_is_stored_outside_session_state_and_survives_service_calls(self):
        durable_rows = []
        first_store = MemoryRepairStore(durable_rows)
        created = repair_requests.submit_request(BASE_PAYLOAD, WORKER, store=first_store)
        second_store = MemoryRepairStore(durable_rows)
        recent = repair_requests.recent_requests(WORKER, store=second_store)

        self.assertEqual(created["id"], recent[0]["id"])
        self.assertEqual(1, len(durable_rows))
        source = (ROOT / "repair_requests.py").read_text(encoding="utf-8")
        self.assertNotIn("st.session_state", source)
        self.assertNotIn("json.dump", source)

    def test_admin_can_complete_and_original_request_remains_stored(self):
        rows = [stored_request()]
        store = MemoryRepairStore(rows)

        completed = repair_requests.mark_request_complete(
            "repair-1",
            ADMIN,
            admin_notes="Creative Refresh now shares the New Ads contract.",
            store=store,
        )

        self.assertEqual(repair_requests.STATUS_COMPLETE, completed["status"])
        self.assertEqual("03/09/2026", completed["completed_date"])
        self.assertIsNotNone(rows[0]["completed_at"])
        self.assertEqual(1, len(rows))
        self.assertEqual("repair-1", rows[0]["id"])

    def test_recent_history_is_newest_first_and_never_more_than_five(self):
        start = datetime(2026, 9, 1, tzinfo=timezone.utc)
        rows = [
            stored_request(id=f"repair-{index}", created_at=start + timedelta(minutes=index))
            for index in range(8)
        ]

        recent = repair_requests.recent_requests(ADMIN, store=MemoryRepairStore(rows), limit=99)

        self.assertEqual(5, len(recent))
        self.assertEqual(
            ["repair-7", "repair-6", "repair-5", "repair-4", "repair-3"],
            [item["id"] for item in recent],
        )

    def test_worker_history_is_limited_to_the_signed_in_submitter(self):
        rows = [
            stored_request(id="mine", submitted_by="worker-1"),
            stored_request(id="theirs", submitted_by="worker-2"),
        ]

        recent = repair_requests.recent_requests(WORKER, store=MemoryRepairStore(rows))

        self.assertEqual(["mine"], [item["id"] for item in recent])

    def test_sydney_date_conversion_uses_calendar_date_in_sydney(self):
        self.assertEqual(
            "01/09/2026",
            repair_requests.format_sydney_date("2026-08-31T15:00:00Z"),
        )


class RepairApiTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def request(method):
        return Request(
            {
                "type": "http",
                "method": method,
                "path": top_bar_api.REPAIR_REQUESTS_PATH,
                "headers": [],
                "query_string": b"",
                "server": ("testserver", 80),
                "client": ("testclient", 1),
                "scheme": "http",
            }
        )

    async def test_worker_submission_response_never_serializes_admin_prompt(self):
        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": top_bar_api.REPAIR_REQUESTS_PATH,
                "headers": [],
                "query_string": b"",
                "server": ("testserver", 80),
                "client": ("testclient", 1),
                "scheme": "http",
            }
        )
        store = MemoryRepairStore()
        with mock.patch.object(top_bar_api, "_claims", return_value=WORKER), mock.patch.object(
            top_bar_api,
            "_request_json_object",
            new=mock.AsyncMock(return_value=BASE_PAYLOAD),
        ), mock.patch.object(
            repair_requests,
            "PostgresRepairRequestStore",
            return_value=store,
        ):
            response = await top_bar_api.top_bar_repair_requests(request)

        payload = json.loads(response.body)
        self.assertEqual(201, response.status_code)
        self.assertNotIn("repair_prompt", json.dumps(payload))
        self.assertNotIn("problem_description", json.dumps(payload))

    async def test_missing_database_table_returns_safe_503_instead_of_crashing(self):
        request = self.request("GET")
        with mock.patch.object(top_bar_api, "_claims", return_value=WORKER), mock.patch.object(
            repair_requests,
            "recent_requests",
            side_effect=repair_requests.RepairRequestStorageMissing("missing table"),
        ):
            response = await top_bar_api.top_bar_repair_requests(request)

        self.assertEqual(503, response.status_code)
        safe_body = response.body.decode("utf-8")
        self.assertIn("temporarily unavailable", safe_body)
        self.assertNotIn(repair_requests.MIGRATION_NAME, safe_body)

    async def test_admin_sees_migration_guidance_only_for_a_missing_table(self):
        with mock.patch.object(top_bar_api, "_claims", return_value=ADMIN), mock.patch.object(
            repair_requests,
            "recent_requests",
            side_effect=repair_requests.RepairRequestStorageMissing("missing table"),
        ):
            missing = await top_bar_api.top_bar_repair_requests(self.request("GET"))
        with mock.patch.object(top_bar_api, "_claims", return_value=ADMIN), mock.patch.object(
            repair_requests,
            "recent_requests",
            side_effect=repair_requests.RepairRequestStorageTemporary("connection unavailable"),
        ):
            temporary = await top_bar_api.top_bar_repair_requests(self.request("GET"))

        self.assertEqual(503, missing.status_code)
        self.assertIn(repair_requests.MIGRATION_NAME, missing.body.decode("utf-8"))
        self.assertEqual(503, temporary.status_code)
        self.assertIn("temporarily unavailable", temporary.body.decode("utf-8"))
        self.assertNotIn(repair_requests.MIGRATION_NAME, temporary.body.decode("utf-8"))

    async def test_existing_empty_table_returns_ready_empty_history(self):
        with mock.patch.object(top_bar_api, "_claims", return_value=WORKER), mock.patch.object(
            repair_requests,
            "PostgresRepairRequestStore",
            return_value=MemoryRepairStore(),
        ):
            response = await top_bar_api.top_bar_repair_requests(self.request("GET"))

        payload = json.loads(response.body)
        self.assertEqual(200, response.status_code)
        self.assertTrue(payload["ok"])
        self.assertEqual([], payload["requests"])
        self.assertIn(
            "No repair requests submitted yet.",
            COMPONENT_PATH.read_text(encoding="utf-8"),
        )

    async def test_worker_completion_api_is_server_side_forbidden(self):
        store = MemoryRepairStore([stored_request()])
        with mock.patch.object(top_bar_api, "_claims", return_value=WORKER), mock.patch.object(
            top_bar_api,
            "_request_json_object",
            new=mock.AsyncMock(return_value={"id": "repair-1"}),
        ), mock.patch.object(
            repair_requests,
            "PostgresRepairRequestStore",
            return_value=store,
        ):
            response = await top_bar_api.top_bar_repair_requests(self.request("PATCH"))

        self.assertEqual(403, response.status_code)
        self.assertEqual(repair_requests.STATUS_SUBMITTED, store.rows[0]["status"])

    def test_route_supports_only_the_three_lightweight_operations(self):
        route = next(
            item for item in top_bar_api.TOP_BAR_ROUTE_HANDLERS
            if item[0] == top_bar_api.REPAIR_REQUESTS_PATH
        )
        self.assertEqual(("GET", "POST", "PATCH"), route[2])

    def test_additive_migration_contains_only_the_repair_request_table(self):
        source = (
            ROOT / "migrations" / repair_requests.MIGRATION_NAME
        ).read_text(encoding="utf-8")

        self.assertIn("CREATE TABLE IF NOT EXISTS os_repair_requests", source)
        for field in (
            "section", "problem_description", "desired_result", "scope_choice",
            "scope_notes", "submitted_by", "submitted_by_role", "status",
            "created_at", "completed_at", "completed_by", "admin_notes",
            "generated_prompt_version",
        ):
            self.assertIn(field, source)
        self.assertNotIn("ALTER TABLE", source)


class RepairToolbarTests(unittest.TestCase):
    def test_sections_come_from_navigation_and_current_ads_page_is_preselected(self):
        admin = {**ADMIN, "is_active": True, "page_permissions": []}
        sections = top_bar.repair_sections_for_user(admin)

        self.assertIn("Home", sections)
        self.assertIn("Ads — New Ads", sections)
        self.assertIn("Ads — Creative Refresh", sections)
        self.assertIn("Toolbar / Navigation", sections)
        self.assertEqual("Other", sections[-1])
        self.assertEqual(
            "Ads — Creative Refresh",
            top_bar.repair_section_for_route("Creative Refresh"),
        )

    def test_toolbar_has_one_accessible_hammer_and_preserves_existing_controls(self):
        source = COMPONENT_PATH.read_text(encoding="utf-8")

        self.assertEqual(1, source.count('id="sc-os-repairs"'))
        self.assertIn('title="Repairs &amp; Improvements"', source)
        for control in (
            "sc-os-refresh", "sc-os-daily-planner", "sc-os-notifications",
            "sc-os-profile", "sc-os-settings",
        ):
            self.assertEqual(1, source.count(f'id="{control}"'))

    def test_repair_inbox_is_lazy_and_does_not_navigate_or_poll(self):
        source = COMPONENT_PATH.read_text(encoding="utf-8")
        handler = source[
            source.index("const openRepairPanel") : source.index("const openSearch")
        ]
        install = source[source.index("install(nextConfig)") : source.index("beginNavigation(routeKey")]

        self.assertIn('openPanel("repairs")', handler)
        self.assertIn("loadRepairItems()", handler)
        self.assertNotIn("navigateDocument", handler)
        self.assertNotIn("location", handler)
        self.assertNotIn("repairRequestsUrl", install)
        self.assertNotIn("setInterval", handler)

    def test_top_bar_configuration_does_not_read_repair_storage(self):
        admin = {**ADMIN, "is_active": True, "page_permissions": []}
        with mock.patch.object(
            repair_requests.PostgresRepairRequestStore,
            "recent",
            side_effect=AssertionError("repair storage must remain lazy"),
        ), mock.patch("top_bar_security.create_top_bar_token", return_value="signed"):
            config = top_bar.top_bar_config(
                admin,
                logo_src="logo",
                current_route="Dashboard",
            )

        self.assertEqual(top_bar_api.REPAIR_REQUESTS_PATH, config["repairRequestsUrl"])

    def test_form_draft_survives_reruns_but_submissions_use_the_database_api(self):
        source = COMPONENT_PATH.read_text(encoding="utf-8")

        self.assertIn("scSportsCaveRepairDraft", source)
        self.assertIn('method: "POST"', source)
        self.assertIn('method: "PATCH"', source)
        self.assertIn("Copy Repair Prompt", source)
        self.assertIn("navigator.clipboard.writeText", source)
        self.assertIn('doc.execCommand("copy")', source)
        self.assertIn('event.key === "Escape" && state.activePanel', source)


if __name__ == "__main__":
    unittest.main()
