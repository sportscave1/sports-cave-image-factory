from pathlib import Path
import ast
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest

from streamlit.testing.v1 import AppTest
import os_accounts
from settings_workspace import SECTIONS, section_allowed

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/settings_v2_preview.py"


class SettingsTests(unittest.TestCase):
    def app(self, role="admin", section="General"):
        app = AppTest.from_file(str(FIXTURE))
        app.session_state["fixture-role"] = role
        app.session_state["settings-section"] = section
        app.run(timeout=20)
        self.assertFalse(app.exception)
        return app

    def button(self, app, label):
        return next(b for b in app.button if b.label == label)

    def test_alias_keeps_permission_identity(self):
        for route in ("Settings", "Accounts & Access", "accounts_access"):
            worker = {"role": "worker", "is_active": True, "page_permissions": []}
            self.assertTrue(os_accounts.can_access_page(worker, route))
        self.assertEqual(os_accounts.normalise_route("Settings"), "Accounts & Access")
        self.assertEqual(os_accounts.PAGE_BY_KEY["accounts_access"]["label"], "Settings")

    def test_worker_direct_admin_sections_fail_closed(self):
        for section in ("Credentials", "Users & Access"):
            app = self.app("worker", section)
            self.assertTrue(app.warning)
            self.assertEqual(app.session_state["settings-section"], "General")
            self.assertFalse(any(b.label in ("Credentials", "Users & Access") for b in app.button))
            self.assertFalse(any(i.label == "Temporary password" for i in app.text_input))
        for section in SECTIONS:
            self.assertFalse(section_allowed({"role": "admin", "is_active": False}, section))

    def test_direct_user_renderer_rejects_workers_before_storage(self):
        tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.name == "render_settings_users_section")
        ui = SimpleNamespace(error=Mock())
        namespace = {"st": ui, "os_accounts": os_accounts}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "app.py", "exec"), namespace)
        with patch.object(os_accounts.DEFAULT_STORE, "list_users") as reads:
            namespace[node.name]({"role": "worker", "is_active": True})
            namespace[node.name]({"role": "admin", "is_active": False})
            reads.assert_not_called()
        self.assertEqual(ui.error.call_count, 2)

    def test_general_profile_save_preserves_identity_permissions(self):
        app = self.app("worker")
        before = app.session_state["fixture-store"].get_user("user-2")
        app.text_input(key="my-profile-display-name").set_value("Updated Worker")
        self.button(app, "Save profile").click().run()
        self.assertFalse(app.exception)
        after = app.session_state["fixture-store"].get_user("user-2")
        self.assertEqual(after["display_name"], "Updated Worker")
        for key in ("id", "username", "email", "role", "page_permissions", "password_hash"):
            self.assertEqual(before[key], after[key])
        self.assertTrue(app.text_input(key="my-profile-login-email").disabled)

    def test_password_mismatch_and_success(self):
        app = self.app("worker")
        fields = {i.label: i for i in app.text_input}
        fields["Current password"].set_value("Local password 26!")
        fields["New password"].set_value("Changed password 27!")
        fields["Confirm new password"].set_value("mismatch")
        self.button(app, "Change password").click().run()
        self.assertIn("New passwords must match.", [w.value for w in app.warning])
        next(i for i in app.text_input if i.label == "Confirm new password").set_value("Changed password 27!")
        self.button(app, "Change password").click().run()
        self.assertFalse(app.exception)
        user = app.session_state["fixture-store"].get_user("user-2")
        self.assertTrue(os_accounts.verify_password("Changed password 27!", user["password_hash"]))

    def test_editor_is_closed_until_selected_and_save_keeps_permissions(self):
        app = self.app(section="Users & Access")
        self.assertEqual(len(app.text_input), 0)
        before = app.session_state["fixture-store"].get_user("user-2")
        app.button(key="settings-edit-user-2").click().run()
        self.assertFalse(app.exception)
        app.text_input(key="edit-worker-name::user-2").set_value("Edited Worker")
        self.button(app, "Save account").click().run()
        self.assertFalse(app.exception)
        after = app.session_state["fixture-store"].get_user("user-2")
        self.assertEqual(after["display_name"], "Edited Worker")
        self.assertEqual(after["page_permissions"], before["page_permissions"])
        self.assertEqual(after["password_hash"], before["password_hash"])
        self.assertIn("Account access saved.", [s.value for s in app.success])
        self.button(app, "Close editor").click().run()
        self.assertEqual(len(app.text_input), 0)

    def test_create_worker_defaults_to_no_permissions(self):
        app = self.app(section="Users & Access")
        app.button(key="settings-add-worker").click().run()
        fields = {i.label: i for i in app.text_input}
        fields["Display name"].set_value("New Worker")
        fields["Username"].set_value("newworker")
        fields["Temporary password"].set_value("New worker password 28!")
        self.button(app, "Create account").click().run()
        self.assertFalse(app.exception)
        worker = app.session_state["fixture-store"].find_user_by_login("newworker")
        self.assertEqual(worker["role"], "worker")
        self.assertEqual(worker["page_permissions"], [])

    def test_reporting_is_owner_restricted(self):
        app = self.app("worker", "Reporting")
        self.assertTrue(app.checkbox[0].disabled)
        self.assertFalse(app.checkbox[0].value)
        self.assertTrue(self.button(app, "Save Reporting access").disabled)

    def test_logout_invokes_existing_cleanup(self):
        app = self.app()
        app.button(key="sidebar-logout").click().run()
        self.assertTrue(app.session_state["fixture-logged-out"])
        self.assertTrue(app.session_state["fixture-cookie-cleared"])


if __name__ == "__main__":
    unittest.main()
