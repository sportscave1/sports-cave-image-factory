from pathlib import Path
import time
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import dropbox_integration
import os_accounts
import sc_auth
import sports_cave_dashboard
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
        self.assertEqual(app_test.session_state["selected_page"], "Orders")
        self.assertEqual(app_test.session_state["current_page"], "Orders")

    def test_auth_refresh_does_not_silently_replace_blocked_page_with_home(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        auth_source = source[
            source.index("def _set_authenticated_user") : source.index("\n\ndef _account_system_status")
        ]

        self.assertNotIn('st.session_state["selected_page"] = allowed_routes[0]', auth_source)
        self.assertNotIn("st.session_state.selected_page = allowed_routes[0]", auth_source)

    def test_staff_stays_on_allowed_mockups_page_after_auth_refresh(self):
        worker = {
            "id": "worker-mockups",
            "username": "reina",
            "display_name": "Reina",
            "role": "worker",
            "is_active": True,
            "page_permissions": ["dashboard", "mockups"],
        }
        app_test = AppTest.from_file(str(ROOT / "app.py"))
        app_test.session_state["sports_cave_authenticated"] = True
        app_test.session_state["sports_cave_current_user"] = worker
        app_test.session_state["sports_cave_auth_checked_at"] = 0.0
        app_test.session_state["current_page"] = "Mockups"
        app_test.session_state["selected_page"] = "Mockups"

        with patch.object(os_accounts.DEFAULT_STORE, "get_user", return_value=worker):
            app_test.run(timeout=20)

        self.assertFalse(app_test.exception)
        self.assertEqual(app_test.session_state["current_page"], "Mockups")
        self.assertEqual(app_test.session_state["selected_page"], "Mockups")
        self.assertIn("Mockups", [title.value for title in app_test.title])

    def test_admin_stays_on_mockups_page_after_auth_refresh(self):
        admin = {
            "id": "admin-mockups",
            "username": "nathan",
            "display_name": "Nathan",
            "role": "admin",
            "is_active": True,
            "page_permissions": [],
        }
        app_test = AppTest.from_file(str(ROOT / "app.py"))
        app_test.session_state["sports_cave_authenticated"] = True
        app_test.session_state["sports_cave_current_user"] = admin
        app_test.session_state["sports_cave_auth_checked_at"] = 0.0
        app_test.session_state["current_page"] = "Mockups"
        app_test.session_state["selected_page"] = "Mockups"

        with patch.object(os_accounts.DEFAULT_STORE, "get_user", return_value=admin):
            app_test.run(timeout=20)

        self.assertFalse(app_test.exception)
        self.assertEqual(app_test.session_state["current_page"], "Mockups")
        self.assertEqual(app_test.session_state["selected_page"], "Mockups")
        self.assertIn("Mockups", [title.value for title in app_test.title])

    def test_home_admin_sections_do_not_change_current_page(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        home_source = source[
            source.index("def render_lightweight_dashboard_page") : source.index("\n\ndef page_uses_local_database")
        ]

        self.assertNotIn("set_current_page(", home_source)
        self.assertNotIn("selected_page", home_source)
        self.assertNotIn('session_state["current_page"]', home_source)

    def test_missing_route_defaults_home_only_on_first_load(self):
        worker = {
            "id": "worker-first-load",
            "username": "worker",
            "display_name": "Worker",
            "role": "worker",
            "is_active": True,
            "page_permissions": ["dashboard", "mockups"],
        }
        app_test = AppTest.from_file(str(ROOT / "app.py"))
        app_test.session_state["sports_cave_authenticated"] = True
        app_test.session_state["sports_cave_current_user"] = worker
        app_test.session_state["sports_cave_auth_checked_at"] = time.monotonic()

        with patch.object(
            sports_cave_dashboard,
            "load_dashboard_state",
            return_value={"tasks": [], "activity_log": [], "task_error": "", "activity_error": ""},
        ), patch.object(sports_cave_dashboard, "load_calendar_events", return_value=[]):
            app_test.run(timeout=20)

        self.assertEqual(app_test.session_state["current_page"], "Dashboard")
        app_test.session_state["current_page"] = "Mockups"
        app_test.session_state["selected_page"] = "Dashboard"
        app_test.run(timeout=20)

        self.assertEqual(app_test.session_state["current_page"], "Mockups")
        self.assertEqual(app_test.session_state["selected_page"], "Mockups")

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

    def test_admin_without_server_credentials_sees_clean_files_unavailable(self):
        with patch.dict(
            "os.environ",
            {
                "DROPBOX_APP_KEY": "",
                "DROPBOX_APP_SECRET": "",
                "DROPBOX_REDIRECT_URI": "",
                "DROPBOX_REFRESH_TOKEN": "",
                "DROPBOX_ACCESS_TOKEN": "",
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
        self.assertIn("Files unavailable", text)
        self.assertNotIn("Connection settings", text)

    def test_files_page_uses_server_refresh_token_without_connect_step(self):
        root_metadata = {
            ".tag": "folder",
            "name": dropbox_integration.DROPBOX_ROOT_FOLDER,
            "path_display": "/Sportscave Team Folder",
        }
        file_entry = {
            ".tag": "file",
            "name": "collector.pdf",
            "path_display": "/Sportscave Team Folder/collector.pdf",
            "server_modified": "2026-07-22T01:30:00Z",
            "size": 2048,
        }
        unsorted_entries = [
            file_entry,
            {
                ".tag": "folder",
                "name": "Zulu",
                "path_display": "/Sportscave Team Folder/Zulu",
            },
            {
                ".tag": "file",
                "name": "alpha.jpg",
                "path_display": "/Sportscave Team Folder/alpha.jpg",
                "server_modified": "2026-07-22T02:30:00Z",
                "size": 4096,
            },
            {
                ".tag": "folder",
                "name": "01 Assets",
                "path_display": "/Sportscave Team Folder/01 Assets",
            },
        ]

        with patch.dict(
            "os.environ",
            {
                "DROPBOX_APP_KEY": "app-key",
                "DROPBOX_APP_SECRET": "app-secret",
                "DROPBOX_REDIRECT_URI": "https://example.test/dropbox/callback",
                "DROPBOX_REFRESH_TOKEN": "server-refresh-token",
                "DROPBOX_ACCESS_TOKEN": "fallback-token",
            },
        ), patch.object(
            dropbox_integration,
            "resolve_server_auth",
            return_value={
                "access_token": "access-token",
                "source": "refresh_token",
                "account": {"email": "files@sportscave.test"},
            },
        ) as resolve_server_auth, patch.object(
            dropbox_integration,
            "find_team_folder",
            return_value=root_metadata["path_display"],
        ) as find_team_folder, patch.object(
            dropbox_integration,
            "list_folder",
            return_value=unsorted_entries,
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
            opening_text = self._app_text(app_test)
            self.assertIn("Sportscave Team Folder", opening_text)
            self.assertIn("sc-files-icon-folder", opening_text)
            self.assertNotIn("height: 155px", opening_text)

            app_test.session_state["files_browser_path"] = "/Sportscave Team Folder"
            app_test.run(timeout=20)
            browser_text = self._app_text(app_test)
            self.assertIn("Name", browser_text)
            self.assertIn("Date modified", browser_text)
            self.assertIn("Type", browser_text)
            self.assertIn("Size", browser_text)
            self.assertIn("collector.pdf", browser_text)
            self.assertIn("PDF document", browser_text)
            self.assertIn("2.0 KB", browser_text)
            self.assertLess(browser_text.index("01 Assets"), browser_text.index("Zulu"))
            self.assertLess(browser_text.index("Zulu"), browser_text.index("alpha.jpg"))
            self.assertLess(browser_text.index("alpha.jpg"), browser_text.index("collector.pdf"))
            self.assertIn('target="_blank"', browser_text)
            self.assertIn("files_preview=", browser_text)
            self.assertNotIn("https://dropbox.test/temporary/collector.pdf", browser_text)

            app_test.session_state["files_preview_path"] = (
                "/Sportscave Team Folder/collector.pdf"
            )
            app_test.run(timeout=20)

        text = self._app_text(app_test)
        self.assertFalse(app_test.exception)
        self.assertIn("collector.pdf", text)
        self.assertIn("Open original", text)
        self.assertNotIn("Connect Files", text)
        self.assertNotIn("Test Connection", text)
        self.assertNotIn("Reconnect Files", text)
        self.assertNotIn("Connection settings", text)
        self.assertNotIn("Upload test", text)
        resolve_server_auth.assert_called()
        find_team_folder.assert_called()
        file_open_details.assert_called_once_with(
            "access-token",
            "/Sportscave Team Folder/collector.pdf",
        )

    def test_unsupported_file_preview_requires_explicit_download_action(self):
        psd_entry = {
            ".tag": "file",
            "name": "collector-art.psd",
            "path_display": "/Sportscave Team Folder/collector-art.psd",
            "server_modified": "2026-07-22T01:30:00Z",
            "size": 8192,
        }
        with patch.dict(
            "os.environ",
            {
                "DROPBOX_APP_KEY": "app-key",
                "DROPBOX_APP_SECRET": "app-secret",
                "DROPBOX_REFRESH_TOKEN": "server-refresh-token",
            },
        ), patch.object(
            dropbox_integration,
            "resolve_server_auth",
            return_value={
                "access_token": "access-token",
                "source": "refresh_token",
                "account": {"email": "files@sportscave.test"},
            },
        ), patch.object(
            dropbox_integration,
            "find_team_folder",
            return_value="/Sportscave Team Folder",
        ), patch.object(
            dropbox_integration,
            "file_open_details",
            return_value={
                "metadata": psd_entry,
                "temporary_link": "https://dropbox.test/temporary/collector-art.psd",
            },
        ):
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
            app_test.session_state["files_preview_path"] = psd_entry["path_display"]
            app_test.run(timeout=20)

        text = self._app_text(app_test)
        self.assertFalse(app_test.exception)
        self.assertIn("collector-art.psd", text)
        self.assertIn("Adobe Photoshop", text)
        self.assertIn("Download and open", text)

    def test_files_browses_subfolders_with_breadcrumb_and_empty_folder_state(self):
        root_path = "/Sportscave Team Folder"
        mockups_path = f"{root_path}/05 Mockups"
        folder_entry = {
            ".tag": "folder",
            "name": "05 Mockups",
            "path_display": mockups_path,
        }

        def list_folder(_token, path="", **_kwargs):
            return [folder_entry] if path == root_path else []

        with patch.dict(
            "os.environ",
            {
                "DROPBOX_APP_KEY": "app-key",
                "DROPBOX_APP_SECRET": "app-secret",
                "DROPBOX_REFRESH_TOKEN": "server-refresh-token",
                "DROPBOX_ACCESS_TOKEN": "",
            },
        ), patch.object(
            dropbox_integration,
            "resolve_server_auth",
            return_value={
                "access_token": "shared-access-token",
                "source": "refresh_token",
                "account": {"email": "hello@sportscave.com.au"},
            },
        ), patch.object(
            dropbox_integration,
            "find_team_folder",
            return_value=root_path,
        ), patch.object(
            dropbox_integration,
            "list_folder",
            side_effect=list_folder,
        ):
            app_test = AppTest.from_file(str(ROOT / "app.py"))
            app_test.session_state["sports_cave_authenticated"] = True
            app_test.session_state["sports_cave_current_user"] = {
                "id": "worker-1",
                "username": "reina",
                "display_name": "Reina",
                "role": "worker",
                "timezone": os_accounts.WORKER_TIMEZONE,
                "is_active": True,
                "page_permissions": ["files"],
            }
            app_test.session_state["sports_cave_auth_checked_at"] = time.monotonic()
            app_test.session_state["selected_page"] = "Files"
            app_test.run(timeout=20)

            self.assertEqual(app_test.text_input, [])
            app_test.session_state["files_browser_path"] = root_path
            app_test.run(timeout=20)
            root_text = self._app_text(app_test)
            self.assertIn("05 Mockups", root_text)
            self.assertIn("File folder", root_text)
            self.assertIn("files_path=%2FSportscave%20Team%20Folder%2F05%20Mockups", root_text)
            self.assertRegex(
                root_text,
                r'<a class="sc-files-grid sc-files-row"[^>]+files_path='
                r'%2FSportscave%20Team%20Folder%2F05%20Mockups[^>]+target="_self"',
            )
            folder_row = root_text[root_text.index("05 Mockups") - 600 : root_text.index("05 Mockups") + 600]
            self.assertNotIn('target="_blank"', folder_row)

            app_test.session_state["files_browser_path"] = mockups_path
            app_test.run(timeout=20)
            empty_text = self._app_text(app_test)
            self.assertIn("This folder is empty", empty_text)
            self.assertIn("Files", empty_text)
            self.assertIn("Sportscave Team Folder", empty_text)
            self.assertIn("05 Mockups", empty_text)
            self.assertIn("sc-files-chevron", empty_text)
            self.assertRegex(
                empty_text,
                r'<nav class="sc-files-breadcrumb"[^>]*>.*target="_self"',
            )
            breadcrumb = empty_text[
                empty_text.index('<nav class="sc-files-breadcrumb"') : empty_text.index("</nav>")
            ]
            self.assertNotIn('target="_blank"', breadcrumb)

        self.assertFalse(app_test.exception)

    def test_files_workspace_has_compact_write_controls_and_current_folder_drop_target(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        command_bar = source[
            source.index("def _render_files_command_bar") : source.index("\n\ndef _clear_files_action_query")
        ]
        browser = source[
            source.index("def _render_files_browser") : source.index("\n\ndef render_files_page")
        ]
        upload = source[
            source.index("def _render_files_upload_control") : source.index("\n\ndef _render_files_command_bar")
        ]

        self.assertIn('"New folder"', command_bar)
        self.assertIn('"Upload files"', command_bar)
        self.assertIn('"Upload folder"', command_bar)
        self.assertIn('accept_multiple_files="directory" if directory else True', upload)
        self.assertIn('key="files-drop-target"', browser)
        self.assertIn("current_path", browser)
        self.assertIn("auto_submit=True", browser)
        self.assertIn('"Drop files into this folder"', upload)
        self.assertIn('"files_uploaded"', source)
        self.assertIn('"files_folder_created"', source)
        self.assertIn('"files_item_renamed"', source)

    def test_files_write_operations_remain_behind_files_permission(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        files_page = source[
            source.index("def render_files_page") : source.index("\n\ndef render_selected_page")
        ]

        self.assertIn('os_accounts.can_access_page(user, "Files")', files_page)
        self.assertIn("Access not approved", files_page)

    def test_missing_team_folder_reports_scope_problem_only_to_admin(self):
        with patch.dict(
            "os.environ",
            {
                "DROPBOX_APP_KEY": "app-key",
                "DROPBOX_APP_SECRET": "app-secret",
                "DROPBOX_REFRESH_TOKEN": "server-refresh-token",
            },
        ), patch.object(
            dropbox_integration,
            "resolve_server_auth",
            return_value={
                "access_token": "access-token",
                "source": "refresh_token",
                "account": {"email": "hello@sportscave.com.au"},
            },
        ), patch.object(
            dropbox_integration,
            "find_team_folder",
            side_effect=dropbox_integration.DropboxFolderAccessError(
                "folder not visible",
                reason="not_visible",
            ),
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
        self.assertIn("Files unavailable", text)
        self.assertNotIn("folder not visible", text)
        self.assertNotIn("App Folder access", text)
        self.assertNotIn("Full Dropbox access", text)
        self.assertNotIn("Connection settings", text)

    def test_admin_and_approved_va_use_the_same_server_dropbox_root(self):
        root_path = "/Sportscave Team Folder"
        users = (
            {
                "id": "admin-1",
                "username": "nathan",
                "display_name": "Nathan",
                "role": "admin",
                "timezone": os_accounts.ADMIN_TIMEZONE,
                "is_active": True,
                "page_permissions": [],
            },
            {
                "id": "worker-1",
                "username": "reina",
                "display_name": "Reina",
                "role": "worker",
                "timezone": os_accounts.WORKER_TIMEZONE,
                "is_active": True,
                "page_permissions": ["files"],
            },
        )
        with patch.dict(
            "os.environ",
            {
                "DROPBOX_APP_KEY": "app-key",
                "DROPBOX_APP_SECRET": "app-secret",
                "DROPBOX_REFRESH_TOKEN": "shared-refresh-token",
            },
        ), patch.object(
            dropbox_integration,
            "resolve_server_auth",
            return_value={
                "access_token": "shared-access-token",
                "source": "refresh_token",
                "account": {"email": "hello@sportscave.com.au"},
            },
        ) as resolve_auth, patch.object(
            dropbox_integration,
            "find_team_folder",
            return_value=root_path,
        ) as find_root:
            rendered = []
            for user in users:
                app_test = AppTest.from_file(str(ROOT / "app.py"))
                app_test.session_state["sports_cave_authenticated"] = True
                app_test.session_state["sports_cave_current_user"] = user
                app_test.session_state["sports_cave_auth_checked_at"] = time.monotonic()
                app_test.session_state["selected_page"] = "Files"
                app_test.run(timeout=20)
                rendered.append(self._app_text(app_test))

        self.assertEqual(resolve_auth.call_count, 2)
        self.assertEqual(find_root.call_count, 2)
        self.assertTrue(all("Sportscave Team Folder" in text for text in rendered))

    def test_admin_missing_refresh_token_shows_clean_failure_not_blank_page(self):
        with patch.dict(
            "os.environ",
            {
                "DROPBOX_APP_KEY": "app-key",
                "DROPBOX_APP_SECRET": "app-secret",
                "DROPBOX_REDIRECT_URI": "https://example.test/dropbox/callback",
                "DROPBOX_REFRESH_TOKEN": "",
                "DROPBOX_ACCESS_TOKEN": "",
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

        self.assertFalse(app_test.exception)
        text = self._app_text(app_test)
        self.assertIn("Files unavailable", text)
        self.assertNotIn("DROPBOX_REFRESH_TOKEN", text)
        self.assertNotIn("This page failed to load", text)
        link_labels = [item.label for item in app_test.get("link_button")]
        self.assertNotIn("Connect Files", link_labels)

    def test_invalid_server_refresh_token_shows_clean_error(self):
        with patch.dict(
            "os.environ",
            {
                "DROPBOX_APP_KEY": "app-key",
                "DROPBOX_APP_SECRET": "app-secret",
                "DROPBOX_REFRESH_TOKEN": "bad-refresh-token",
                "DROPBOX_ACCESS_TOKEN": "",
            },
        ), patch.object(
            dropbox_integration,
            "refresh_access_token",
            side_effect=dropbox_integration.DropboxApiError("invalid_grant: token revoked"),
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
        self.assertIn("Files unavailable", text)
        self.assertNotIn("invalid_grant", text)
        self.assertNotIn("bad-refresh-token", text)
        self.assertNotIn("This page failed to load", text)

    def test_admin_access_token_fallback_still_loads_without_technical_warning(self):
        file_entry = {
            ".tag": "file",
            "name": "collector.pdf",
            "path_display": "/Sportscave Team Folder/collector.pdf",
            "server_modified": "2026-07-22T01:30:00Z",
            "size": 2048,
        }

        with patch.dict(
            "os.environ",
            {
                "DROPBOX_APP_KEY": "app-key",
                "DROPBOX_APP_SECRET": "app-secret",
                "DROPBOX_REFRESH_TOKEN": "invalid-refresh-token",
                "DROPBOX_ACCESS_TOKEN": "temporary-access-token",
            },
        ), patch.object(
            dropbox_integration,
            "resolve_server_auth",
            return_value={
                "access_token": "temporary-access-token",
                "source": "access_token",
                "account": {"email": "files@sportscave.test"},
            },
        ), patch.object(
            dropbox_integration,
            "find_team_folder",
            return_value="/Sportscave Team Folder",
        ), patch.object(
            dropbox_integration,
            "list_folder",
            return_value=[file_entry],
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
            app_test.session_state["files_browser_path"] = "/Sportscave Team Folder"
            app_test.run(timeout=20)

        text = self._app_text(app_test)
        self.assertFalse(app_test.exception)
        self.assertIn("collector.pdf", text)
        self.assertNotIn("temporary Dropbox access token", text)
        self.assertNotIn("Reconnect Files", text)
        self.assertNotIn("Connection settings", text)

    def test_staff_access_token_fallback_has_no_token_warning(self):
        file_entry = {
            ".tag": "file",
            "name": "collector.pdf",
            "path_display": "/Sportscave Team Folder/collector.pdf",
            "server_modified": "2026-07-22T01:30:00Z",
            "size": 2048,
        }

        with patch.dict(
            "os.environ",
            {
                "DROPBOX_APP_KEY": "app-key",
                "DROPBOX_APP_SECRET": "app-secret",
                "DROPBOX_REFRESH_TOKEN": "invalid-refresh-token",
                "DROPBOX_ACCESS_TOKEN": "temporary-access-token",
            },
        ), patch.object(
            dropbox_integration,
            "resolve_server_auth",
            return_value={
                "access_token": "temporary-access-token",
                "source": "access_token",
                "account": {"email": "files@sportscave.test"},
            },
        ), patch.object(
            dropbox_integration,
            "find_team_folder",
            return_value="/Sportscave Team Folder",
        ), patch.object(
            dropbox_integration,
            "list_folder",
            return_value=[file_entry],
        ):
            app_test = AppTest.from_file(str(ROOT / "app.py"))
            app_test.session_state["sports_cave_authenticated"] = True
            app_test.session_state["sports_cave_current_user"] = {
                "id": "worker-1",
                "username": "reina",
                "display_name": "Reina",
                "role": "worker",
                "timezone": os_accounts.WORKER_TIMEZONE,
                "is_active": True,
                "page_permissions": ["files"],
            }
            app_test.session_state["sports_cave_auth_checked_at"] = time.monotonic()
            app_test.session_state["selected_page"] = "Files"
            app_test.session_state["files_browser_path"] = "/Sportscave Team Folder"
            app_test.run(timeout=20)

        text = self._app_text(app_test)
        self.assertFalse(app_test.exception)
        self.assertIn("collector.pdf", text)
        self.assertNotIn("temporary Dropbox access token", text)
        self.assertNotIn("refresh token", text.casefold())
        self.assertNotIn("Connection settings", text)

    def test_staff_sees_clean_files_unavailable_when_both_tokens_fail(self):
        with patch.dict(
            "os.environ",
            {
                "DROPBOX_APP_KEY": "app-key",
                "DROPBOX_APP_SECRET": "app-secret",
                "DROPBOX_REFRESH_TOKEN": "invalid-refresh-token",
                "DROPBOX_ACCESS_TOKEN": "invalid-access-token",
            },
        ), patch.object(
            dropbox_integration,
            "resolve_server_auth",
            side_effect=dropbox_integration.DropboxApiError(
                "Dropbox server credentials could not be verified."
            ),
        ):
            app_test = AppTest.from_file(str(ROOT / "app.py"))
            app_test.session_state["sports_cave_authenticated"] = True
            app_test.session_state["sports_cave_current_user"] = {
                "id": "worker-1",
                "username": "reina",
                "display_name": "Reina",
                "role": "worker",
                "timezone": os_accounts.WORKER_TIMEZONE,
                "is_active": True,
                "page_permissions": ["files"],
            }
            app_test.session_state["sports_cave_auth_checked_at"] = time.monotonic()
            app_test.session_state["selected_page"] = "Files"
            app_test.run(timeout=20)

        text = self._app_text(app_test)
        self.assertFalse(app_test.exception)
        self.assertIn("Files unavailable", text)
        self.assertNotIn("token", text.casefold())
        self.assertNotIn("Connection settings", text)

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
            app_test.info,
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

    def test_admin_home_renders_after_daily_execution_save_with_legacy_other_tasks(self):
        class DailyExecutionBackend:
            def is_configured(self):
                return True

            def list_dashboard_tasks(self, status="open"):
                return []

            def list_activity_logs(self, *, start_at=None, end_at=None, limit=200):
                return []

            def list_dashboard_edition_products(self, *, limit=1000):
                return []

            def get_daily_execution_sheet(self, user_id, sheet_date):
                if sheet_date == "2026-07-23":
                    return {}
                return {
                    "id": "sheet-1",
                    "user_id": user_id,
                    "user_name": "Nathan",
                    "sheet_date": sheet_date,
                    "timezone": os_accounts.ADMIN_TIMEZONE,
                    "status": "active",
                    "top_tasks": [
                        {"task": "Launch offer", "why": "Revenue", "time_blocked": "9am", "status": "done"},
                        {"task": "Upload products", "why": "SKUs", "time_blocked": "11am", "status": "couldnt_finish"},
                        {"task": "Fix ads", "why": "Traffic", "time_blocked": "2pm", "completed": True},
                    ],
                    "additional_items": {"task": "Legacy other task", "details": "Reloaded after save", "completed": True},
                    "no_grey_zone": {},
                    "ratings": {},
                    "daily_summary": "",
                    "tomorrow_intention": "",
                    "generated_prompt": "",
                }

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

        with patch.object(sports_cave_dashboard, "get_supabase_backend", return_value=DailyExecutionBackend()):
            app_test.run(timeout=20)

        text = self._app_text(app_test)
        self.assertFalse(app_test.exception)
        self.assertNotIn("This page failed to load", text)
        self.assertIn("**Other tasks**", text)

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
        self.assertIn("if os_accounts.is_admin(user):", dashboard_source)
        self.assertIn("render_daily_execution_panel(local_now, events, state)", dashboard_source)


if __name__ == "__main__":
    unittest.main()
