from pathlib import Path
import time
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import dropbox_integration
import os_accounts
import sc_auth
import supabase_backend


ROOT = Path(__file__).resolve().parents[1]


class FakeAccountStore:
    def __init__(self):
        self.users = []
        self.created_count = 0
        self.schema_calls = 0

    def is_configured(self):
        return True

    def ensure_schema(self):
        self.schema_calls += 1

    def first_admin(self):
        return next((dict(user) for user in self.users if user.get("role") == "admin"), {})

    def create_user(self, *, username, email, display_name, password_hash, role, page_keys=()):
        self.created_count += 1
        user = {
            "id": f"user-{self.created_count}",
            "username": username,
            "email": email,
            "display_name": display_name,
            "password_hash": password_hash,
            "role": role,
            "timezone": os_accounts.default_timezone_for_role(role),
            "is_active": True,
            "page_permissions": sorted(page_keys),
            "last_login_at": None,
        }
        self.users.append(user)
        return dict(user)

    def find_user_by_login(self, login):
        clean = str(login or "").strip().casefold()
        for user in self.users:
            if clean in {
                str(user.get("username") or "").casefold(),
                str(user.get("email") or "").casefold(),
            }:
                return dict(user)
        return {}

    def update_last_login(self, user_id):
        for user in self.users:
            if user["id"] == user_id:
                user["last_login_at"] = "2026-07-22T00:00:00+00:00"
                return dict(user)
        return {}

    def get_user(self, user_id):
        return next((dict(user) for user in self.users if user["id"] == user_id), {})

    def update_worker(
        self,
        user_id,
        *,
        username,
        email,
        display_name,
        is_active,
        page_keys,
        password_hash="",
    ):
        for user in self.users:
            if user["id"] == user_id and user["role"] == "worker":
                user.update(
                    username=username,
                    email=email,
                    display_name=display_name,
                    is_active=is_active,
                    timezone=os_accounts.default_timezone_for_role(user.get("role")),
                    page_permissions=sorted(page_keys),
                )
                if password_hash:
                    user["password_hash"] = password_hash
                return dict(user)
        raise ValueError("Worker account was not found.")


class PasswordSecurityTests(unittest.TestCase):
    def test_password_hash_verifies_and_rejects_wrong_password(self):
        stored = os_accounts.hash_password("Strong password 26!")

        self.assertTrue(os_accounts.verify_password("Strong password 26!", stored))
        self.assertFalse(os_accounts.verify_password("wrong password", stored))
        self.assertNotIn("Strong password 26!", stored)

    def test_account_cookie_carries_signed_user_identity_and_expires(self):
        token = sc_auth.create_user_auth_token("user-1", password="master", now=100, days=30)

        valid, reason, payload = sc_auth.validate_user_auth_token(
            token,
            password="master",
            now=101,
        )
        self.assertTrue(valid)
        self.assertEqual(reason, "ok")
        self.assertEqual(payload["sub"], "user-1")
        self.assertEqual(
            sc_auth.validate_user_auth_token(token, password="master", now=100 + sc_auth.auth_cookie_max_age())[:2],
            (False, "expired"),
        )


class AccountAccessTests(unittest.TestCase):
    def test_first_admin_bootstrap_does_not_duplicate_user(self):
        store = FakeAccountStore()

        first = os_accounts.bootstrap_first_admin(
            "owner@sportscave.test",
            "Admin password 26!",
            store=store,
        )
        second = os_accounts.bootstrap_first_admin(
            "other@sportscave.test",
            "Different password 26!",
            store=store,
        )

        self.assertEqual(first["id"], second["id"])
        self.assertEqual(store.created_count, 1)

    def test_admin_can_access_every_registered_page(self):
        admin = {"role": "admin", "is_active": True, "page_permissions": []}

        self.assertTrue(
            all(os_accounts.can_access_page(admin, page["key"]) for page in os_accounts.PAGE_REGISTRY)
        )

    def test_worker_only_sees_and_opens_approved_pages(self):
        worker = {
            "role": "worker",
            "is_active": True,
            "page_permissions": ["dashboard", "mockups"],
        }

        self.assertEqual(os_accounts.allowed_navigation_routes(worker), ("Dashboard", "Mockups"))
        self.assertTrue(os_accounts.can_access_page(worker, "Mockups"))
        self.assertFalse(os_accounts.can_access_page(worker, "Orders"))
        self.assertFalse(os_accounts.can_access_page(worker, "Accounts & Access"))
        self.assertFalse(os_accounts.can_access_page(worker, "Developer"))

    def test_files_can_be_assigned_and_legacy_dropbox_permission_is_preserved(self):
        worker = {
            "role": "worker",
            "is_active": True,
            "page_permissions": ["dashboard", "dropbox"],
        }

        self.assertIn("Files", os_accounts.allowed_navigation_routes(worker))
        self.assertNotIn("Dropbox", os_accounts.allowed_navigation_routes(worker))
        self.assertTrue(os_accounts.can_access_page(worker, "Files"))
        self.assertTrue(os_accounts.can_access_page(worker, "Dropbox"))
        self.assertEqual(os_accounts.normalise_route("Dropbox"), "Files")
        self.assertEqual(os_accounts.page_key_for_route("Dropbox"), "files")

    def test_blocked_worker_cannot_invoke_page_renderer(self):
        worker = {"role": "worker", "is_active": True, "page_permissions": ["dashboard"]}
        rendered = []

        allowed = os_accounts.run_authorized(worker, "Orders", lambda: rendered.append("orders"))

        self.assertFalse(allowed)
        self.assertEqual(rendered, [])

    def test_inactive_user_cannot_login(self):
        store = FakeAccountStore()
        worker = os_accounts.create_worker_account(
            username="worker",
            display_name="Worker",
            password="Worker password 26!",
            page_keys=("dashboard",),
            store=store,
        )
        store.users[0]["is_active"] = False

        authenticated, reason = os_accounts.authenticate_user(
            worker["username"],
            "Worker password 26!",
            store=store,
        )

        self.assertIsNone(authenticated)
        self.assertEqual(reason, "inactive")

    def test_permission_updates_are_saved_with_worker_profile(self):
        store = FakeAccountStore()
        worker = os_accounts.create_worker_account(
            username="worker",
            display_name="Worker",
            password="Worker password 26!",
            page_keys=("dashboard",),
            store=store,
        )

        updated = os_accounts.update_worker_account(
            worker["id"],
            username="worker",
            email="worker@sportscave.test",
            display_name="VA One",
            is_active=True,
            page_keys=("orders", "mockups"),
            store=store,
        )

        self.assertEqual(updated["page_permissions"], ["mockups", "orders"])
        self.assertEqual(updated["display_name"], "VA One")
        self.assertEqual(updated["email"], "worker@sportscave.test")

    def test_account_timezones_default_by_role(self):
        self.assertEqual(os_accounts.default_timezone_for_role("admin"), "Australia/Sydney")
        self.assertEqual(os_accounts.default_timezone_for_role("worker"), "Asia/Manila")
        self.assertEqual(
            os_accounts.timezone_for_user({"role": "admin", "timezone": ""}),
            "Australia/Sydney",
        )
        self.assertEqual(
            os_accounts.timezone_for_user({"role": "worker", "timezone": ""}),
            "Asia/Manila",
        )

    def test_account_migration_contains_both_required_tables(self):
        sql = (ROOT / "migrations" / "20260722_os_accounts_access.sql").read_text(encoding="utf-8")

        self.assertIn("CREATE TABLE IF NOT EXISTS os_users", sql)
        self.assertIn("timezone TEXT NOT NULL DEFAULT 'Asia/Manila'", sql)
        self.assertIn("Australia/Sydney", sql)
        self.assertIn("Asia/Manila", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS os_user_page_permissions", sql)
        self.assertIn("REFERENCES os_users(id) ON DELETE CASCADE", sql)

    def test_app_checks_access_before_local_database_or_page_render(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        main_source = source[source.index("def main():") : source.index("\n\nmain()")]

        access_index = main_source.index("ensure_current_page_access(current_page)")
        database_index = main_source.index("page_uses_local_database(current_page)")
        render_index = main_source.index("render_selected_page(current_page)")
        self.assertLess(access_index, database_index)
        self.assertLess(access_index, render_index)

    def test_blocked_worker_route_renders_access_message_without_page_exception(self):
        app_test = AppTest.from_file(str(ROOT / "app.py"))
        app_test.session_state["sports_cave_authenticated"] = True
        app_test.session_state["sports_cave_current_user"] = {
            "id": "worker-1",
            "username": "worker",
            "display_name": "Worker",
            "role": "worker",
            "is_active": True,
            "page_permissions": ["dashboard"],
        }
        app_test.session_state["sports_cave_auth_checked_at"] = time.monotonic()
        app_test.session_state["selected_page"] = "Orders"

        app_test.run(timeout=20)

        self.assertFalse(app_test.exception)
        self.assertIn("Access not approved", [title.value for title in app_test.title])

    def test_blocked_worker_cannot_render_files_page(self):
        app_test = AppTest.from_file(str(ROOT / "app.py"))
        app_test.session_state["sports_cave_authenticated"] = True
        app_test.session_state["sports_cave_current_user"] = {
            "id": "worker-1",
            "username": "worker",
            "display_name": "Worker",
            "role": "worker",
            "is_active": True,
            "page_permissions": ["dashboard"],
        }
        app_test.session_state["sports_cave_auth_checked_at"] = time.monotonic()
        app_test.session_state["selected_page"] = "Files"

        app_test.run(timeout=20)

        self.assertFalse(app_test.exception)
        self.assertIn("Access not approved", [title.value for title in app_test.title])

    def test_admin_can_render_files_setup_page_without_env_vars(self):
        with patch.dict(
            "os.environ",
            {
                "DROPBOX_APP_KEY": "",
                "DROPBOX_APP_SECRET": "",
                "DROPBOX_REDIRECT_URI": "",
            },
        ):
            app_test = AppTest.from_file(str(ROOT / "app.py"))
            app_test.session_state["sports_cave_authenticated"] = True
            app_test.session_state["sports_cave_current_user"] = {
                "id": "admin-1",
                "username": "nathan",
                "display_name": "Nathan",
                "role": "admin",
                "timezone": os_accounts.ADMIN_TIMEZONE,
                "is_active": True,
                "page_permissions": [],
            }
            app_test.session_state["sports_cave_auth_checked_at"] = time.monotonic()
            app_test.session_state["selected_page"] = "Files"

            app_test.run(timeout=20)

        text = self._app_text(app_test)
        self.assertFalse(app_test.exception)
        self.assertIn("Files", [title.value for title in app_test.title])
        self.assertIn("Files setup is not complete.", text)

    def test_connected_worker_sees_files_browser_without_connection_controls(self):
        root_entry = {
            ".tag": "folder",
            "name": dropbox_integration.DROPBOX_ROOT_FOLDER,
            "path_display": "/Sports Cave OS Assets",
        }
        file_entry = {
            ".tag": "file",
            "name": "collector.pdf",
            "path_display": "/Sports Cave OS Assets/collector.pdf",
            "server_modified": "2026-07-22T01:30:00Z",
            "size": 2048,
        }

        def list_folder(_token, path="", **_kwargs):
            return [root_entry] if not path else [file_entry]

        with patch.dict(
            "os.environ",
            {
                "DROPBOX_APP_KEY": "app-key",
                "DROPBOX_APP_SECRET": "app-secret",
                "DROPBOX_REDIRECT_URI": "https://example.test/dropbox/callback",
            },
        ), patch.object(
            supabase_backend,
            "get_dropbox_connection_status",
            return_value={"connected": True, "account_name": "Sports Cave"},
        ), patch.object(
            supabase_backend,
            "get_dropbox_refresh_token",
            return_value="refresh-token",
        ), patch.object(
            dropbox_integration,
            "refresh_access_token",
            return_value="access-token",
        ), patch.object(
            dropbox_integration,
            "list_folder",
            side_effect=list_folder,
        ), patch.object(
            dropbox_integration,
            "file_open_details",
            return_value={
                "metadata": file_entry,
                "temporary_link": "https://dropbox.test/temporary/collector.pdf",
            },
        ) as file_open_details:
            app_test = AppTest.from_file(str(ROOT / "app.py"))
            app_test.session_state["sports_cave_authenticated"] = True
            app_test.session_state["sports_cave_current_user"] = {
                "id": "worker-1",
                "username": "worker",
                "display_name": "Worker",
                "role": "worker",
                "timezone": os_accounts.WORKER_TIMEZONE,
                "is_active": True,
                "page_permissions": ["files"],
            }
            app_test.session_state["sports_cave_auth_checked_at"] = time.monotonic()
            app_test.session_state["selected_page"] = "Files"
            app_test.run(timeout=20)
            next(button for button in app_test.button if button.label == "Open").click().run(
                timeout=20
            )

        text = self._app_text(app_test)
        button_labels = [button.label for button in app_test.button]
        self.assertFalse(app_test.exception)
        self.assertIn("Files", [title.value for title in app_test.title])
        self.assertIn("collector.pdf", text)
        self.assertIn("Open", button_labels)
        self.assertNotIn("Test Connection", button_labels)
        self.assertNotIn("Reconnect Files", text)
        self.assertNotIn("Upload test", text)
        file_open_details.assert_called_once_with(
            "access-token",
            "/Sports Cave OS Assets/collector.pdf",
        )

    def test_admin_disconnected_state_offers_connect_files(self):
        with patch.dict(
            "os.environ",
            {
                "DROPBOX_APP_KEY": "app-key",
                "DROPBOX_APP_SECRET": "app-secret",
                "DROPBOX_REDIRECT_URI": "https://example.test/dropbox/callback",
            },
        ), patch.object(
            supabase_backend,
            "get_dropbox_connection_status",
            return_value={"connected": False},
        ):
            app_test = AppTest.from_file(str(ROOT / "app.py"))
            app_test.session_state["sports_cave_authenticated"] = True
            app_test.session_state["sports_cave_current_user"] = {
                "id": "admin-1",
                "username": "nathan",
                "display_name": "Nathan",
                "role": "admin",
                "timezone": os_accounts.ADMIN_TIMEZONE,
                "is_active": True,
                "page_permissions": [],
            }
            app_test.session_state["sports_cave_auth_checked_at"] = time.monotonic()
            app_test.session_state["selected_page"] = "Files"
            app_test.run(timeout=20)

        self.assertFalse(app_test.exception)
        self.assertIn("Files are not connected.", self._app_text(app_test))
        link_labels = [item.label for item in app_test.get("link_button")]
        self.assertIn("Connect Files", link_labels)

    @staticmethod
    def _app_text(app_test):
        values = []
        for collection in (
            app_test.title,
            app_test.header,
            app_test.subheader,
            app_test.markdown,
            app_test.caption,
            app_test.warning,
        ):
            values.extend(str(item.value) for item in collection)
        return "\n".join(values)

    def test_worker_home_does_not_render_activity_log(self):
        app_test = AppTest.from_file(str(ROOT / "app.py"))
        app_test.session_state["sports_cave_authenticated"] = True
        app_test.session_state["sports_cave_current_user"] = {
            "id": "worker-1",
            "username": "worker",
            "display_name": "Maria",
            "role": "worker",
            "timezone": os_accounts.WORKER_TIMEZONE,
            "is_active": True,
            "page_permissions": ["dashboard"],
        }
        app_test.session_state["sports_cave_auth_checked_at"] = time.monotonic()
        app_test.session_state["selected_page"] = "Dashboard"

        app_test.run(timeout=20)

        text = self._app_text(app_test)
        self.assertFalse(app_test.exception)
        self.assertNotIn("Today's Execution", text)
        self.assertNotIn("Daily Task Execution Sheet", text)
        self.assertNotIn("Activity log", text)
        self.assertNotIn("dashboard-activity-view", text)

    def test_admin_home_still_renders_activity_log(self):
        app_test = AppTest.from_file(str(ROOT / "app.py"))
        app_test.session_state["sports_cave_authenticated"] = True
        app_test.session_state["sports_cave_current_user"] = {
            "id": "admin-1",
            "username": "nathan",
            "display_name": "Nathan",
            "role": "admin",
            "timezone": os_accounts.ADMIN_TIMEZONE,
            "is_active": True,
            "page_permissions": [],
        }
        app_test.session_state["sports_cave_auth_checked_at"] = time.monotonic()
        app_test.session_state["selected_page"] = "Dashboard"

        app_test.run(timeout=20)

        text = self._app_text(app_test)
        self.assertFalse(app_test.exception)
        self.assertIn("Daily Task Execution Sheet - The 5 Million Dollar Man", text)
        self.assertIn("Activity log", text)

    def test_daily_execution_renderer_has_admin_guard(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        panel_source = source[
            source.index("def render_daily_execution_panel") :
            source.index("\n\ndef render_task_group")
        ]
        dashboard_source = source[
            source.index("def render_lightweight_dashboard_page") :
            source.index("\n\ndef page_uses_local_database")
        ]

        self.assertIn("if not os_accounts.is_admin(user):", panel_source)
        self.assertIn("Access not approved", panel_source)
        self.assertIn("if os_accounts.is_admin(user):\n        render_daily_execution_panel", dashboard_source)


if __name__ == "__main__":
    unittest.main()
