import os
from pathlib import Path
import time
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import daily_activity_digest
import os_accounts
import reporting_store


ROOT = Path(__file__).resolve().parents[1]
OWNER_EMAIL = "owner@sportscave.test"


def owner(*, permissions=(), active=True):
    return {
        "id": "owner-1",
        "username": "owner",
        "email": OWNER_EMAIL,
        "display_name": "Nathan",
        "role": "admin",
        "country": "Australia",
        "timezone": "Australia/Sydney",
        "is_active": active,
        "page_permissions": list(permissions),
    }


class MemoryPermissionStore:
    def __init__(self, target):
        self.target = dict(target)
        self.calls = 0

    def set_reporting_permission(self, actor, target_user_id, enabled):
        self.calls += 1
        if (
            str(actor.get("id") or "") != str(target_user_id or "")
            or not os_accounts.can_manage_reporting_permission(actor, self.target)
        ):
            raise PermissionError("denied")
        old_value = os_accounts.REPORTING_PAGE_KEY in os_accounts.permission_keys(self.target)
        page_permissions = set(self.target.get("page_permissions") or [])
        if enabled:
            page_permissions.add(os_accounts.REPORTING_PAGE_KEY)
        else:
            page_permissions.discard(os_accounts.REPORTING_PAGE_KEY)
        self.target["page_permissions"] = sorted(page_permissions)
        return {
            "changed": old_value != bool(enabled),
            "old_value": old_value,
            "new_value": bool(enabled),
            "user": dict(self.target),
            "event_key": f"permission:{int(old_value)}:{int(bool(enabled))}",
        }


class ReportingPermissionTests(unittest.TestCase):
    def test_reporting_is_registered_top_level_but_not_worker_assignable(self):
        page = os_accounts.PAGE_BY_KEY[os_accounts.REPORTING_PAGE_KEY]

        self.assertEqual(page["route"], "Reporting")
        self.assertTrue(page["top_level"])
        self.assertFalse(page["worker_assignable"])
        self.assertNotIn(
            os_accounts.REPORTING_PAGE_KEY,
            {item["key"] for item in os_accounts.worker_assignable_pages()},
        )

    def test_reporting_defaults_unticked_and_bulk_permission_storage_excludes_it(self):
        class RecordingCursor:
            def __init__(self):
                self.calls = []

            def execute(self, sql, parameters):
                self.calls.append((sql, parameters))

        cursor = RecordingCursor()
        selected = os_accounts.PostgresAccountStore._replace_permissions(
            cursor,
            "worker-1",
            ["dashboard", os_accounts.REPORTING_PAGE_KEY],
        )

        self.assertEqual(selected, ["dashboard"])
        self.assertFalse(
            any(
                "INSERT INTO os_user_page_permissions" in sql
                and parameters == ("worker-1", os_accounts.REPORTING_PAGE_KEY)
                for sql, parameters in cursor.calls
            )
        )

    def test_missing_owner_configuration_fails_closed(self):
        candidate = owner(permissions=[os_accounts.REPORTING_PAGE_KEY])

        with patch.dict(
            os.environ,
            {
                "SPORTS_CAVE_REPORTING_OWNER_EMAIL": "",
                "SPORTS_CAVE_ADMIN_EMAIL": "",
            },
            clear=False,
        ):
            self.assertFalse(os_accounts.is_reporting_owner(candidate))
            self.assertFalse(os_accounts.can_access_reporting(candidate))
            self.assertFalse(os_accounts.can_access_page(candidate, "Reporting"))

    def test_admin_email_is_safe_fallback_for_owner_identity(self):
        candidate = owner(permissions=[os_accounts.REPORTING_PAGE_KEY])

        with patch.dict(
            os.environ,
            {
                "SPORTS_CAVE_REPORTING_OWNER_EMAIL": "",
                "SPORTS_CAVE_ADMIN_EMAIL": f"  {OWNER_EMAIL.upper()}  ",
            },
            clear=False,
        ):
            self.assertTrue(os_accounts.is_reporting_owner(candidate))
            self.assertTrue(os_accounts.can_access_reporting(candidate))

    def test_worker_and_non_owner_admin_are_denied_even_with_forged_permission(self):
        worker = {
            **owner(permissions=[os_accounts.REPORTING_PAGE_KEY]),
            "id": "worker-1",
            "email": "worker@sportscave.test",
            "role": "worker",
        }
        other_admin = {
            **owner(permissions=[os_accounts.REPORTING_PAGE_KEY]),
            "id": "admin-2",
            "email": "other-admin@sportscave.test",
        }

        with patch.dict(
            os.environ,
            {"SPORTS_CAVE_REPORTING_OWNER_EMAIL": OWNER_EMAIL},
            clear=False,
        ):
            self.assertFalse(os_accounts.can_access_reporting(worker))
            self.assertFalse(os_accounts.can_access_reporting(other_admin))
            self.assertNotIn("Reporting", os_accounts.allowed_navigation_routes(worker))
            self.assertNotIn("Reporting", os_accounts.allowed_navigation_routes(other_admin))

    def test_owner_must_be_active_admin_and_explicitly_enabled(self):
        with patch.dict(
            os.environ,
            {"SPORTS_CAVE_REPORTING_OWNER_EMAIL": OWNER_EMAIL},
            clear=False,
        ):
            self.assertFalse(os_accounts.can_access_reporting(owner(permissions=[])))
            self.assertFalse(
                os_accounts.can_access_reporting(
                    {
                        **owner(permissions=[os_accounts.REPORTING_PAGE_KEY]),
                        "role": "worker",
                    }
                )
            )
            self.assertFalse(
                os_accounts.can_access_reporting(
                    owner(
                        permissions=[os_accounts.REPORTING_PAGE_KEY],
                        active=False,
                    )
                )
            )
            self.assertTrue(
                os_accounts.can_access_reporting(
                    owner(permissions=[os_accounts.REPORTING_PAGE_KEY])
                )
            )

    def test_owner_can_enable_and_disable_only_its_own_permission(self):
        candidate = owner()
        store = MemoryPermissionStore(candidate)
        with patch.dict(
            os.environ,
            {"SPORTS_CAVE_REPORTING_OWNER_EMAIL": OWNER_EMAIL},
            clear=False,
        ):
            enabled = os_accounts.update_reporting_permission(
                candidate,
                enabled=True,
                store=store,
            )
            self.assertTrue(os_accounts.can_access_reporting(enabled["user"]))
            disabled = os_accounts.update_reporting_permission(
                enabled["user"],
                enabled=False,
                store=store,
            )
            self.assertFalse(os_accounts.can_access_reporting(disabled["user"]))
            with self.assertRaises(PermissionError):
                store.set_reporting_permission(
                    {
                        **candidate,
                        "id": "admin-2",
                        "email": "other@sportscave.test",
                    },
                    "owner-1",
                    True,
                )

    def test_direct_reporting_route_is_denied_to_worker_with_forged_row(self):
        app_test = AppTest.from_file(str(ROOT / "app.py"))
        app_test.session_state["sports_cave_authenticated"] = True
        app_test.session_state["sports_cave_current_user"] = {
            "id": "worker-1",
            "username": "worker",
            "email": "worker@sportscave.test",
            "display_name": "Worker",
            "role": "worker",
            "is_active": True,
            "page_permissions": [os_accounts.REPORTING_PAGE_KEY],
        }
        app_test.session_state["sports_cave_auth_checked_at"] = time.monotonic()
        app_test.session_state["selected_page"] = "Reporting"

        with patch.dict(
            os.environ,
            {"SPORTS_CAVE_REPORTING_OWNER_EMAIL": OWNER_EMAIL},
            clear=False,
        ):
            app_test.run(timeout=20)

        self.assertFalse(app_test.exception)
        self.assertTrue(any(title.value == "Access not approved" for title in app_test.title))

    def test_non_owner_reporting_checkbox_is_locked_and_unticked(self):
        app_test = AppTest.from_file(str(ROOT / "app.py"))
        app_test.session_state["sports_cave_authenticated"] = True
        app_test.session_state["sports_cave_current_user"] = {
            "id": "worker-1",
            "username": "worker",
            "email": "worker@sportscave.test",
            "display_name": "Worker",
            "role": "worker",
            "is_active": True,
            "page_permissions": ["dashboard"],
        }
        app_test.session_state["sports_cave_auth_checked_at"] = time.monotonic()
        app_test.session_state["selected_page"] = "Accounts & Access"

        with patch.dict(
            os.environ,
            {"SPORTS_CAVE_REPORTING_OWNER_EMAIL": OWNER_EMAIL},
            clear=False,
        ):
            app_test.run(timeout=20)

        reporting_boxes = [
            checkbox for checkbox in app_test.checkbox if checkbox.label == "Reporting"
        ]
        self.assertEqual(len(reporting_boxes), 1)
        self.assertFalse(reporting_boxes[0].value)
        self.assertTrue(reporting_boxes[0].disabled)

    def test_archive_and_csv_authorization_happens_before_storage_access(self):
        worker = {
            "id": "worker-1",
            "role": "worker",
            "is_active": True,
            "page_permissions": [os_accounts.REPORTING_PAGE_KEY],
        }

        with patch.object(
            reporting_store,
            "require_schema",
            side_effect=AssertionError("storage must not be reached"),
        ):
            with self.assertRaises(PermissionError):
                reporting_store.list_archives(worker)
            with self.assertRaises(PermissionError):
                reporting_store.get_archive(worker, "archive-1")
            with self.assertRaises(PermissionError):
                reporting_store.archive_csv(worker, "archive-1")

    def test_test_email_action_checks_owner_access_before_configuration_or_data(self):
        worker = {
            "id": "worker-1",
            "role": "worker",
            "is_active": True,
            "page_permissions": [os_accounts.REPORTING_PAGE_KEY],
        }

        with self.assertRaises(PermissionError):
            daily_activity_digest.send_test_daily_digest(worker, nonce="request-1")

    def test_page_source_contains_server_checked_route_and_single_permission_log(self):
        app_source = (ROOT / "app.py").read_text(encoding="utf-8")
        page_source = (ROOT / "reporting_page.py").read_text(encoding="utf-8")

        self.assertIn('elif current_page == "Reporting":', app_source)
        self.assertIn("ensure_current_page_access(current_page)", app_source)
        self.assertIn("if not os_accounts.can_access_reporting(user):", page_source)
        self.assertEqual(
            app_source.count('"reporting_permission_changed"'),
            1,
        )


if __name__ == "__main__":
    unittest.main()
