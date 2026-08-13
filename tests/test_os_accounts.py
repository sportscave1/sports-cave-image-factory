import json
from pathlib import Path
import time
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import dropbox_integration
import os_accounts
import sc_auth
import shared_credentials
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

    def create_user(
        self,
        *,
        username,
        email,
        display_name,
        password_hash,
        role,
        page_keys=(),
        country="",
        allow_credential_permissions=False,
    ):
        clean_country = os_accounts.normalise_country(country, role=role)
        self.created_count += 1
        user = {
            "id": f"user-{self.created_count}",
            "username": username,
            "email": email,
            "display_name": display_name,
            "password_hash": password_hash,
            "role": role,
            "country": clean_country,
            "timezone": os_accounts.timezone_for_country(clean_country) or os_accounts.default_timezone_for_role(role),
            "is_active": True,
            "session_version": 1,
            "account_status": os_accounts.ACCOUNT_STATUS_ACTIVE,
            "removed_at": None,
            "removed_by": "",
            "page_permissions": sorted(page_keys),
            "last_login_at": None,
        }
        self.users.append(user)
        return dict(user)

    def find_user_by_login(self, login):
        clean = str(login or "").strip().casefold()
        for user in self.users:
            if os_accounts.account_is_removed(user):
                continue
            if clean in {
                str(user.get("username") or "").casefold(),
                str(user.get("email") or "").casefold(),
            }:
                return dict(user)
        return {}

    def update_last_login(self, user_id):
        for user in self.users:
            if user["id"] == user_id:
                if not os_accounts.account_is_active(user):
                    return {}
                user["last_login_at"] = "2026-07-22T00:00:00+00:00"
                return dict(user)
        return {}

    def get_user(self, user_id, *, include_removed=False):
        for user in self.users:
            if user["id"] == user_id and (include_removed or not os_accounts.account_is_removed(user)):
                return dict(user)
        return {}

    def list_users(self):
        return [dict(user) for user in self.users if not os_accounts.account_is_removed(user)]

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
        country="",
        allow_credential_permissions=False,
    ):
        for user in self.users:
            if user["id"] == user_id and user["role"] == "worker" and not os_accounts.account_is_removed(user):
                clean_country = os_accounts.normalise_country(country, role=user.get("role"))
                user.update(
                    username=username,
                    email=email,
                    display_name=display_name,
                    country=clean_country,
                    timezone=os_accounts.timezone_for_country(clean_country),
                    page_permissions=sorted(page_keys),
                )
                if password_hash:
                    user["password_hash"] = password_hash
                return dict(user)
        raise ValueError("Worker account was not found.")

    def _fresh_admin(self, actor):
        fresh = self.get_user((actor or {}).get("id"))
        if not os_accounts.is_admin(fresh):
            raise PermissionError("Only an active administrator can perform this account action.")
        return fresh

    def remote_logout_user(self, actor, target_user_id):
        clean_actor = self._fresh_admin(actor)
        target = self.get_user(target_user_id, include_removed=True)
        if not target:
            return {
                "changed": False,
                "actor": clean_actor,
                "target": {"id": str(target_user_id or "")},
                "reason": "target_not_found",
            }
        if os_accounts.account_is_removed(target):
            return {
                "changed": False,
                "actor": clean_actor,
                "target": target,
                "reason": "already_removed",
            }
        for user in self.users:
            if user["id"] == target["id"]:
                user["session_version"] = int(user.get("session_version") or 1) + 1
                return {
                    "changed": True,
                    "actor": clean_actor,
                    "target": dict(user),
                    "reason": "logged_out",
                }
        return {
            "changed": False,
            "actor": clean_actor,
            "target": target,
            "reason": "target_not_found",
        }

    def remove_account(self, actor, target_user_id):
        clean_actor = self._fresh_admin(actor)
        target = self.get_user(target_user_id, include_removed=True)
        if not target:
            return {
                "changed": False,
                "actor": clean_actor,
                "target": {"id": str(target_user_id or "")},
                "reason": "target_not_found",
            }
        if os_accounts.account_is_removed(target):
            for user in self.users:
                if user["id"] == target["id"]:
                    user["page_permissions"] = []
                    target = dict(user)
            return {
                "changed": False,
                "actor": clean_actor,
                "target": target,
                "reason": "already_removed",
            }
        if clean_actor["id"] == target["id"]:
            raise PermissionError("You cannot remove your own active account.")
        if target.get("role") == os_accounts.ROLE_ADMIN:
            remaining_admins = [
                user
                for user in self.users
                if user["id"] != target["id"] and os_accounts.is_admin(user)
            ]
            if not remaining_admins:
                raise PermissionError("The final active administrator account cannot be removed.")
        for user in self.users:
            if user["id"] == target["id"]:
                previous = dict(user)
                user.update(
                    username=f"removed-{user['id']}",
                    email="",
                    password_hash="removed-account",
                    is_active=False,
                    account_status=os_accounts.ACCOUNT_STATUS_REMOVED,
                    removed_at="2026-08-10T00:00:00+00:00",
                    removed_by=clean_actor["id"],
                    session_version=int(user.get("session_version") or 1) + 1,
                    page_permissions=[],
                )
                return {
                    "changed": True,
                    "actor": clean_actor,
                    "target": dict(user),
                    "previous_target": previous,
                    "reason": "removed",
                }
        return {
            "changed": False,
            "actor": clean_actor,
            "target": target,
            "reason": "target_not_found",
        }

    def update_profile(self, user_id, *, display_name, country):
        for user in self.users:
            if user["id"] == user_id:
                clean_country = os_accounts.normalise_country(country, role=user.get("role"))
                user.update(
                    display_name=display_name,
                    country=clean_country,
                    timezone=os_accounts.timezone_for_country(clean_country),
                )
                return dict(user)
        raise ValueError("Account was not found.")

    def update_password(self, user_id, *, current_password, new_password):
        for user in self.users:
            if user["id"] == user_id:
                if not os_accounts.verify_password(current_password, user.get("password_hash")):
                    raise ValueError("Current password is incorrect.")
                strength = os_accounts.password_strength_error(new_password)
                if strength:
                    raise ValueError(strength)
                user["password_hash"] = os_accounts.hash_password(new_password)
                return dict(user)
        raise ValueError("Account was not found.")


class PasswordSecurityTests(unittest.TestCase):
    def test_password_hash_verifies_and_rejects_wrong_password(self):
        stored = os_accounts.hash_password("Strong password 26!")

        self.assertTrue(os_accounts.verify_password("Strong password 26!", stored))
        self.assertFalse(os_accounts.verify_password("wrong password", stored))
        self.assertNotIn("Strong password 26!", stored)

    def test_account_cookie_carries_signed_user_identity_session_version_and_expires(self):
        token = sc_auth.create_user_auth_token(
            "user-1",
            password="master",
            now=100,
            days=30,
            session_version=7,
        )

        valid, reason, payload = sc_auth.validate_user_auth_token(
            token,
            password="master",
            now=101,
        )
        self.assertTrue(valid)
        self.assertEqual(reason, "ok")
        self.assertEqual(payload["sub"], "user-1")
        self.assertEqual(payload["sv"], 7)
        self.assertEqual(
            sc_auth.validate_user_auth_token(token, password="master", now=100 + sc_auth.auth_cookie_max_age())[:2],
            (False, "expired"),
        )


class AccountAccessTests(unittest.TestCase):
    def _create_admin(self, store, *, username="nathan", email="nathan@sportscave.test"):
        return store.create_user(
            username=username,
            email=email,
            display_name="Nathan",
            password_hash=os_accounts.hash_password("Admin password 26!"),
            role=os_accounts.ROLE_ADMIN,
            country=os_accounts.COUNTRY_AUSTRALIA,
        )

    def _create_worker(
        self,
        store,
        *,
        username="worker",
        email="worker@sportscave.test",
        page_keys=("dashboard",),
        password="Worker password 26!",
        actor=None,
    ):
        return os_accounts.create_worker_account(
            username=username,
            email=email,
            display_name="Worker",
            password=password,
            page_keys=page_keys,
            store=store,
            actor=actor,
        )

    def test_files_delete_capability_defaults_off_for_workers_and_on_for_admin(self):
        admin = {"role": "admin", "is_active": True, "page_permissions": []}
        worker = {
            "role": "worker",
            "is_active": True,
            "page_permissions": ["files"],
        }

        self.assertTrue(os_accounts.can_delete_files(admin))
        self.assertFalse(os_accounts.can_delete_files(worker))
        self.assertTrue(
            os_accounts.can_delete_files(
                {
                    **worker,
                    "page_permissions": ["files", os_accounts.FILES_DELETE_CAPABILITY],
                }
            )
        )
        self.assertFalse(
            os_accounts.can_delete_files(
                {
                    **worker,
                    "page_permissions": [os_accounts.FILES_DELETE_CAPABILITY],
                }
            )
        )

    def test_activity_log_capability_defaults_off_for_workers_and_on_for_admin(self):
        admin = {"role": "admin", "is_active": True, "page_permissions": []}
        worker = {
            "role": "worker",
            "is_active": True,
            "page_permissions": ["dashboard"],
        }

        self.assertTrue(os_accounts.can_view_activity_log(admin))
        self.assertFalse(os_accounts.can_view_activity_log(worker))
        self.assertTrue(
            os_accounts.can_view_activity_log(
                {
                    **worker,
                    "page_permissions": ["dashboard", os_accounts.ACTIVITY_LOG_CAPABILITY],
                }
            )
        )
        self.assertFalse(
            os_accounts.can_view_activity_log(
                {
                    **worker,
                    "page_permissions": [os_accounts.ACTIVITY_LOG_CAPABILITY],
                }
            )
        )

    def test_prompt_editing_defaults_off_for_workers_and_on_for_admin(self):
        admin = {"role": "admin", "is_active": True, "page_permissions": []}
        worker = {
            "role": "worker",
            "is_active": True,
            "page_permissions": ["product_uploads"],
        }

        self.assertTrue(os_accounts.can_edit_prompts(admin))
        self.assertFalse(os_accounts.can_edit_prompts(worker))
        self.assertTrue(
            os_accounts.can_edit_prompts(
                {
                    **worker,
                    "page_permissions": [
                        "product_uploads",
                        os_accounts.EDIT_PROMPTS_CAPABILITY,
                    ],
                }
            )
        )
        self.assertFalse(
            os_accounts.can_edit_prompts(
                {
                    **worker,
                    "is_active": False,
                    "page_permissions": [os_accounts.EDIT_PROMPTS_CAPABILITY],
                }
            )
        )

    def test_activity_log_capability_is_accepted_by_permission_storage(self):
        class RecordingCursor:
            def __init__(self):
                self.calls = []

            def execute(self, sql, parameters):
                self.calls.append((sql, parameters))

        cursor = RecordingCursor()
        selected = os_accounts.PostgresAccountStore._replace_permissions(
            cursor,
            "worker-1",
            ["dashboard", os_accounts.ACTIVITY_LOG_CAPABILITY, "not-a-permission"],
        )

        self.assertEqual(
            selected,
            ["dashboard", os_accounts.ACTIVITY_LOG_CAPABILITY],
        )
        self.assertTrue(
            any(
                parameters == ("worker-1", os_accounts.ACTIVITY_LOG_CAPABILITY)
                for _, parameters in cursor.calls
            )
        )

    def test_prompt_editing_capability_is_accepted_by_permission_storage(self):
        class RecordingCursor:
            def __init__(self):
                self.calls = []

            def execute(self, sql, parameters):
                self.calls.append((sql, parameters))

        cursor = RecordingCursor()
        selected = os_accounts.PostgresAccountStore._replace_permissions(
            cursor,
            "worker-1",
            ["product_uploads", os_accounts.EDIT_PROMPTS_CAPABILITY, "not-a-permission"],
        )

        self.assertEqual(
            selected,
            [os_accounts.EDIT_PROMPTS_CAPABILITY, "product_uploads"],
        )
        self.assertTrue(
            any(
                parameters == ("worker-1", os_accounts.EDIT_PROMPTS_CAPABILITY)
                for _, parameters in cursor.calls
            )
        )

    def test_credential_capability_requires_explicit_storage_allowance(self):
        class RecordingCursor:
            def __init__(self):
                self.calls = []

            def execute(self, sql, parameters):
                self.calls.append((sql, parameters))

        with self.assertRaises(PermissionError):
            os_accounts.PostgresAccountStore._replace_permissions(
                RecordingCursor(),
                "worker-1",
                ["dashboard", "credential_prodigi"],
            )

        cursor = RecordingCursor()
        selected = os_accounts.PostgresAccountStore._replace_permissions(
            cursor,
            "worker-1",
            ["dashboard", "credential_prodigi", "not-a-permission"],
            allow_credential_permissions=True,
        )

        self.assertEqual(selected, ["credential_prodigi", "dashboard"])
        self.assertTrue(
            any(
                parameters == ("worker-1", "credential_prodigi")
                for _, parameters in cursor.calls
            )
        )

    def test_admin_can_access_all_shared_credentials(self):
        admin = {"id": "admin-1", "role": "admin", "is_active": True, "page_permissions": []}

        self.assertEqual(
            [spec.key for spec in shared_credentials.accessible_credential_specs(admin)],
            ["prodigi", "adobe", "chatgpt"],
        )
        self.assertTrue(
            all(
                shared_credentials.can_access_credential(admin, spec.key)
                for spec in shared_credentials.credential_specs()
            )
        )

    def test_permitted_worker_accesses_only_selected_credentials(self):
        worker = {
            "id": "worker-1",
            "role": "worker",
            "is_active": True,
            "page_permissions": ["credential_prodigi", "credential_chatgpt"],
        }
        store = FakeAccountStore()
        store.users.append(worker)

        with patch("activity_log.record_activity_log"):
            self.assertEqual(
                shared_credentials.read_credential_for_action(
                    worker,
                    "prodigi",
                    shared_credentials.FIELD_PASSWORD,
                    shared_credentials.ACTION_PASSWORD_COPIED,
                    environ={"PRODIGI_PASSWORD": "fake-prodigi-password"},
                    store=store,
                ),
                "fake-prodigi-password",
            )
            with self.assertRaises(shared_credentials.CredentialAccessDenied):
                shared_credentials.read_credential_for_action(
                    worker,
                    "adobe",
                    shared_credentials.FIELD_PASSWORD,
                    shared_credentials.ACTION_PASSWORD_COPIED,
                    environ={"ADOBE_PASSWORD": "fake-adobe-password"},
                    store=store,
                )

        self.assertEqual(
            [spec.key for spec in shared_credentials.accessible_credential_specs(worker)],
            ["prodigi", "chatgpt"],
        )

    def test_unpermitted_worker_cannot_reveal_or_copy_credentials(self):
        worker = {
            "id": "worker-1",
            "role": "worker",
            "is_active": True,
            "page_permissions": [],
        }
        store = FakeAccountStore()
        store.users.append(worker)

        with patch("activity_log.record_activity_log") as audit_log:
            for action in (
                shared_credentials.ACTION_PASSWORD_REVEALED,
                shared_credentials.ACTION_PASSWORD_COPIED,
            ):
                with self.subTest(action=action):
                    with self.assertRaises(shared_credentials.CredentialAccessDenied):
                        shared_credentials.read_credential_for_action(
                            worker,
                            "prodigi",
                            shared_credentials.FIELD_PASSWORD,
                            action,
                            environ={"PRODIGI_PASSWORD": "fake-prodigi-password"},
                            store=store,
                        )

        self.assertTrue(audit_log.called)
        self.assertTrue(
            all(call.args[0] == shared_credentials.ACTION_ACCESS_DENIED for call in audit_log.call_args_list)
        )

    def test_credential_permissions_default_off_for_workers(self):
        store = FakeAccountStore()
        worker = os_accounts.create_worker_account(
            username="worker",
            display_name="Worker",
            password="Worker password 26!",
            page_keys=("dashboard",),
            store=store,
        )

        self.assertEqual(shared_credentials.credential_permission_keys(worker["page_permissions"]), ())
        self.assertEqual(shared_credentials.accessible_credential_specs(worker), ())

    def test_revoked_credential_access_is_denied_on_fresh_check(self):
        worker = {
            "id": "worker-1",
            "username": "worker",
            "display_name": "Worker",
            "role": "worker",
            "is_active": True,
            "page_permissions": ["credential_prodigi"],
        }
        store = FakeAccountStore()
        store.users.append(dict(worker))

        with patch("activity_log.record_activity_log"):
            self.assertEqual(
                shared_credentials.read_credential_for_action(
                    worker,
                    "prodigi",
                    shared_credentials.FIELD_PASSWORD,
                    shared_credentials.ACTION_PASSWORD_REVEALED,
                    environ={"PRODIGI_PASSWORD": "fake-prodigi-password"},
                    store=store,
                ),
                "fake-prodigi-password",
            )
            store.users[0]["page_permissions"] = []
            with self.assertRaises(shared_credentials.CredentialAccessDenied):
                shared_credentials.read_credential_for_action(
                    worker,
                    "prodigi",
                    shared_credentials.FIELD_PASSWORD,
                    shared_credentials.ACTION_PASSWORD_REVEALED,
                    environ={"PRODIGI_PASSWORD": "fake-prodigi-password"},
                    store=store,
                )

    def test_admin_can_remotely_logout_another_user_without_changing_account(self):
        store = FakeAccountStore()
        admin = self._create_admin(store)
        worker = self._create_worker(
            store,
            page_keys=("dashboard", "credential_prodigi"),
            actor=admin,
        )
        original_permissions = list(worker["page_permissions"])

        with patch("activity_log.record_activity_log") as audit_log:
            result = os_accounts.remote_logout_user(admin, worker["id"], store=store)

        refreshed = store.get_user(worker["id"])
        self.assertTrue(result["changed"])
        self.assertEqual(refreshed["session_version"], worker["session_version"] + 1)
        self.assertTrue(refreshed["is_active"])
        self.assertEqual(refreshed["page_permissions"], original_permissions)
        self.assertTrue(audit_log.called)

    def test_remote_logout_invalidates_old_sessions_but_user_can_sign_in_again(self):
        store = FakeAccountStore()
        admin = self._create_admin(store)
        worker = self._create_worker(store, password="Worker password 26!")
        old_session_version = worker["session_version"]

        with patch("activity_log.record_activity_log"):
            os_accounts.remote_logout_user(admin, worker["id"], store=store)

        refreshed = store.get_user(worker["id"])
        self.assertNotEqual(old_session_version, refreshed["session_version"])
        authenticated, reason = os_accounts.authenticate_user(
            "worker",
            "Worker password 26!",
            store=store,
        )
        self.assertEqual(reason, "ok")
        self.assertEqual(authenticated["id"], worker["id"])
        self.assertEqual(authenticated["session_version"], refreshed["session_version"])

    def test_permanent_removal_invalidates_sessions_revokes_credentials_and_blocks_login(self):
        store = FakeAccountStore()
        admin = self._create_admin(store)
        worker = self._create_worker(
            store,
            page_keys=("dashboard", "credential_prodigi"),
            password="Worker password 26!",
            actor=admin,
        )
        old_session_version = worker["session_version"]
        history = {
            "work_logs": [{"user_id": worker["id"], "summary": "Packed orders"}],
            "tasks": [{"completed_by": worker["display_name"]}],
            "audit": [{"actor": worker["display_name"]}],
            "reports": [{"staff_id": worker["id"]}],
        }

        with patch("activity_log.record_activity_log"):
            result = os_accounts.remove_user_account(admin, worker["id"], store=store)

        removed = store.get_user(worker["id"], include_removed=True)
        self.assertTrue(result["changed"])
        self.assertFalse(os_accounts.account_is_active(removed))
        self.assertEqual(removed["account_status"], os_accounts.ACCOUNT_STATUS_REMOVED)
        self.assertGreater(removed["session_version"], old_session_version)
        self.assertEqual(removed["page_permissions"], [])
        self.assertEqual(store.get_user(worker["id"]), {})
        self.assertNotIn(worker["id"], [account["id"] for account in store.list_users()])
        self.assertEqual(os_accounts.authenticate_user("worker", "Worker password 26!", store=store)[1], "invalid")
        self.assertEqual(history["work_logs"][0]["user_id"], worker["id"])
        self.assertEqual(history["tasks"][0]["completed_by"], "Worker")
        with self.assertRaises(shared_credentials.CredentialAccessDenied):
            shared_credentials.read_credential_for_action(
                worker,
                "prodigi",
                shared_credentials.FIELD_PASSWORD,
                shared_credentials.ACTION_PASSWORD_COPIED,
                environ={"PRODIGI_PASSWORD": "removed-user-password"},
                store=store,
            )

    def test_removed_account_email_can_be_recreated_without_inheriting_permissions_or_sessions(self):
        store = FakeAccountStore()
        admin = self._create_admin(store)
        old_worker = self._create_worker(
            store,
            username="reina",
            email="reina@sportscave.test",
            page_keys=("dashboard", "credential_prodigi"),
            actor=admin,
        )

        with patch("activity_log.record_activity_log"):
            os_accounts.remove_user_account(admin, old_worker["id"], store=store)

        new_worker = self._create_worker(
            store,
            username="reina",
            email="reina@sportscave.test",
            page_keys=(),
        )
        self.assertNotEqual(new_worker["id"], old_worker["id"])
        self.assertEqual(new_worker["session_version"], 1)
        self.assertEqual(new_worker["page_permissions"], [])
        self.assertNotIn("credential_prodigi", new_worker["page_permissions"])

    def test_account_actions_require_admin_and_block_self_removal(self):
        store = FakeAccountStore()
        admin = self._create_admin(store)
        worker = self._create_worker(store)

        with patch("activity_log.record_activity_log") as audit_log:
            with self.assertRaises(PermissionError):
                os_accounts.remote_logout_user(worker, admin["id"], store=store)
            with self.assertRaises(PermissionError):
                os_accounts.remove_user_account(worker, admin["id"], store=store)
            with self.assertRaises(PermissionError):
                os_accounts.remove_user_account(admin, admin["id"], store=store)

        self.assertTrue(audit_log.called)
        self.assertTrue(
            any(call.args[0] == os_accounts.ACTION_ADMIN_ACCOUNT_ACTION_DENIED for call in audit_log.call_args_list)
        )

    def test_repeated_logout_and_removal_fail_safely(self):
        store = FakeAccountStore()
        admin = self._create_admin(store)
        worker = self._create_worker(store)

        with patch("activity_log.record_activity_log"):
            first_logout = os_accounts.remote_logout_user(admin, worker["id"], store=store)
            second_logout = os_accounts.remote_logout_user(admin, worker["id"], store=store)
            first_remove = os_accounts.remove_user_account(admin, worker["id"], store=store)
            second_remove = os_accounts.remove_user_account(admin, worker["id"], store=store)

        self.assertTrue(first_logout["changed"])
        self.assertTrue(second_logout["changed"])
        self.assertTrue(first_remove["changed"])
        self.assertFalse(second_remove["changed"])
        self.assertEqual(second_remove["reason"], "already_removed")

    def test_account_removal_audit_payloads_do_not_contain_secrets_or_tokens(self):
        store = FakeAccountStore()
        admin = self._create_admin(store)
        worker = self._create_worker(
            store,
            username="secret-worker",
            email="secret-worker@sportscave.test",
            password="Secret worker password 26!",
            page_keys=("credential_prodigi",),
            actor=admin,
        )
        secret_values = ("Secret worker password 26!", "session-token-value", "credential-secret-value")

        with patch("activity_log.record_activity_log") as audit_log:
            os_accounts.remove_user_account(admin, worker["id"], store=store)

        payload = json.dumps(
            [{"args": call.args, "kwargs": call.kwargs} for call in audit_log.call_args_list],
            default=str,
        )
        for secret in secret_values:
            self.assertNotIn(secret, payload)
        self.assertNotIn("password_hash", payload)
        self.assertNotIn("session-token-value", payload)

    def test_account_access_ui_has_only_logout_and_remove_controls(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        account_source = source[
            source.index("def render_account_access_section") :
            source.index("\n\ndef render_passwords_section")
        ]

        self.assertIn("**Account Access**", account_source)
        self.assertIn('"Log Out User"', account_source)
        self.assertIn('"Remove Account"', account_source)
        self.assertIn("if not os_accounts.is_admin(actor):", account_source)
        self.assertNotIn("Account active", source)
        for forbidden in ("Deactivate Account", "Reactivate Account", "Restore Account", "reactivate"):
            self.assertNotIn(forbidden, account_source)

    def test_account_action_source_uses_session_version_tombstone_and_no_history_deletes(self):
        account_source = (ROOT / "os_accounts.py").read_text(encoding="utf-8")
        app_source = (ROOT / "app.py").read_text(encoding="utf-8")
        migration_source = (ROOT / "migrations" / "20260810_account_access_controls.sql").read_text(encoding="utf-8")

        self.assertIn("session_version", account_source)
        self.assertIn("account_status='removed'", account_source)
        self.assertIn("DELETE FROM os_user_page_permissions", account_source)
        self.assertIn("_active_admin_count", account_source)
        self.assertIn("The final active administrator account cannot be removed.", account_source)
        self.assertIn("_session_user_matches_refreshed_user", app_source)
        self.assertIn("_auth_payload_matches_user", app_source)
        self.assertIn("clear_revealed_credential", app_source)
        self.assertIn("Existing users remain active", migration_source)
        for forbidden_delete in ("DELETE FROM audit_logs", "DELETE FROM dashboard_tasks", "DELETE FROM daily_execution_sheets"):
            self.assertNotIn(forbidden_delete, account_source)
            self.assertNotIn(forbidden_delete, migration_source)

    def test_missing_render_variables_fail_safely(self):
        admin = {"id": "admin-1", "role": "admin", "is_active": True, "page_permissions": []}
        store = FakeAccountStore()
        store.users.append(admin)

        with patch("activity_log.record_activity_log") as audit_log:
            self.assertFalse(
                shared_credentials.credential_field_is_configured(
                    admin,
                    "prodigi",
                    shared_credentials.FIELD_PASSWORD,
                    environ={},
                    store=store,
                )
            )
            self.assertEqual(
                shared_credentials.read_credential_for_action(
                    admin,
                    "prodigi",
                    shared_credentials.FIELD_PASSWORD,
                    shared_credentials.ACTION_PASSWORD_REVEALED,
                    environ={},
                    store=store,
                ),
                "",
            )

        audit_log.assert_not_called()

    def test_credential_values_never_enter_audit_payloads(self):
        admin = {
            "id": "admin-1",
            "email": "admin@sportscave.test",
            "display_name": "Nathan",
            "role": "admin",
            "is_active": True,
            "page_permissions": [],
        }
        store = FakeAccountStore()
        store.users.append(admin)
        credential_username = "shared-login@example.test"
        credential_password = "unit-test-credential-password-value"

        with patch("activity_log.record_activity_log") as audit_log:
            self.assertEqual(
                shared_credentials.read_credential_for_action(
                    admin,
                    "prodigi",
                    shared_credentials.FIELD_USERNAME,
                    shared_credentials.ACTION_USERNAME_COPIED,
                    environ={"PRODIGI_USERNAME": credential_username},
                    store=store,
                ),
                credential_username,
            )
            self.assertEqual(
                shared_credentials.read_credential_for_action(
                    admin,
                    "prodigi",
                    shared_credentials.FIELD_PASSWORD,
                    shared_credentials.ACTION_PASSWORD_COPIED,
                    environ={"PRODIGI_PASSWORD": credential_password},
                    store=store,
                ),
                credential_password,
            )

        payload = json.dumps(
            [
                {"args": call.args, "kwargs": call.kwargs}
                for call in audit_log.call_args_list
            ],
            default=str,
        )
        self.assertNotIn(credential_username, payload)
        self.assertNotIn(credential_password, payload)

    def test_credential_permission_changes_require_admin_actor(self):
        store = FakeAccountStore()
        worker_actor = {
            "id": "worker-actor",
            "role": "worker",
            "is_active": True,
            "page_permissions": ["accounts_access"],
        }
        admin_actor = {
            "id": "admin-1",
            "role": "admin",
            "is_active": True,
            "page_permissions": [],
        }

        with self.assertRaises(PermissionError):
            os_accounts.create_worker_account(
                username="credential-worker",
                display_name="Credential Worker",
                password="Worker password 26!",
                page_keys=("credential_prodigi",),
                store=store,
            )
        with self.assertRaises(PermissionError):
            os_accounts.create_worker_account(
                username="credential-worker",
                display_name="Credential Worker",
                password="Worker password 26!",
                page_keys=("credential_prodigi",),
                store=store,
                actor=worker_actor,
            )

        worker = os_accounts.create_worker_account(
            username="credential-worker",
            display_name="Credential Worker",
            password="Worker password 26!",
            page_keys=("credential_prodigi",),
            store=store,
            actor=admin_actor,
        )
        self.assertIn("credential_prodigi", worker["page_permissions"])

        with self.assertRaises(PermissionError):
            os_accounts.update_worker_account(
                worker["id"],
                username="credential-worker",
                display_name="Credential Worker",
                is_active=True,
                page_keys=("credential_adobe",),
                store=store,
                actor=worker_actor,
            )
        updated = os_accounts.update_worker_account(
            worker["id"],
            username="credential-worker",
            display_name="Credential Worker",
            is_active=True,
            page_keys=("credential_adobe",),
            store=store,
            actor=admin_actor,
        )
        self.assertEqual(updated["page_permissions"], ["credential_adobe"])

    def test_revealed_credential_state_expires_without_storing_value(self):
        worker = {
            "id": "worker-1",
            "role": "worker",
            "is_active": True,
            "page_permissions": ["credential_prodigi"],
        }
        state = {}

        shared_credentials.mark_credential_revealed(state, worker, "prodigi", now=100.0)

        self.assertTrue(shared_credentials.credential_is_revealed(state, worker, "prodigi", now=101.0))
        self.assertNotIn("fake-prodigi-password", json.dumps(state))
        self.assertFalse(shared_credentials.credential_is_revealed(state, worker, "prodigi", now=121.0))
        self.assertNotIn(shared_credentials.REVEAL_STATE_KEY, state)

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

    def test_admin_can_access_every_registered_page_except_owner_only_reporting(self):
        admin = {"role": "admin", "is_active": True, "page_permissions": []}

        self.assertTrue(
            all(
                os_accounts.can_access_page(admin, page["key"])
                for page in os_accounts.PAGE_REGISTRY
                if page["key"] != os_accounts.REPORTING_PAGE_KEY
            )
        )
        self.assertFalse(os_accounts.can_access_page(admin, os_accounts.REPORTING_PAGE_KEY))

    def test_worker_only_sees_and_opens_approved_pages(self):
        worker = {
            "role": "worker",
            "is_active": True,
            "page_permissions": ["dashboard", "mockups"],
        }

        self.assertEqual(os_accounts.allowed_navigation_routes(worker), ("Dashboard", "Mockups"))
        self.assertTrue(os_accounts.can_access_page(worker, "Mockups"))
        self.assertFalse(os_accounts.can_access_page(worker, "Files"))
        self.assertFalse(os_accounts.can_access_page(worker, "Orders"))
        self.assertTrue(os_accounts.can_access_page(worker, "Accounts & Access"))
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
        self.assertTrue(
            os_accounts.can_access_page(
                {**worker, "page_permissions": ["Dashboard", "Dropbox"]},
                "Files",
            )
        )
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

    def test_worker_profile_update_does_not_reactivate_inactive_account(self):
        store = FakeAccountStore()
        worker = os_accounts.create_worker_account(
            username="worker",
            display_name="Worker",
            password="Worker password 26!",
            page_keys=("dashboard",),
            store=store,
        )
        store.users[0]["is_active"] = False

        updated = os_accounts.update_worker_account(
            worker["id"],
            username="worker",
            email="worker@sportscave.test",
            display_name="VA One",
            is_active=True,
            page_keys=("orders",),
            store=store,
        )

        self.assertFalse(updated["is_active"])
        self.assertEqual(store.get_user(worker["id"])["is_active"], False)

    def test_prompt_editing_approval_is_saved_for_new_and_existing_workers(self):
        store = FakeAccountStore()
        worker = os_accounts.create_worker_account(
            username="prompt-editor",
            display_name="Prompt Editor",
            password="Worker password 26!",
            page_keys=("product_uploads", os_accounts.EDIT_PROMPTS_CAPABILITY),
            store=store,
        )

        self.assertTrue(os_accounts.can_edit_prompts(worker))
        self.assertIn(os_accounts.EDIT_PROMPTS_CAPABILITY, worker["page_permissions"])

        updated = os_accounts.update_worker_account(
            worker["id"],
            username="prompt-editor",
            display_name="Prompt Editor",
            is_active=True,
            page_keys=("product_uploads",),
            store=store,
        )

        self.assertFalse(os_accounts.can_edit_prompts(updated))
        self.assertNotIn(os_accounts.EDIT_PROMPTS_CAPABILITY, updated["page_permissions"])

    def test_account_timezones_default_by_role(self):
        self.assertEqual(os_accounts.default_timezone_for_role("admin"), "Australia/Sydney")
        self.assertEqual(os_accounts.default_timezone_for_role("worker"), "Asia/Manila")
        self.assertEqual(os_accounts.default_country_for_role("admin"), "Australia")
        self.assertEqual(os_accounts.default_country_for_role("worker"), "Philippines")
        self.assertEqual(
            os_accounts.timezone_for_user({"role": "admin", "timezone": ""}),
            "Australia/Sydney",
        )
        self.assertEqual(
            os_accounts.timezone_for_user({"role": "worker", "timezone": ""}),
            "Asia/Manila",
        )
        self.assertEqual(
            os_accounts.timezone_for_user({"role": "worker", "country": "Australia", "timezone": ""}),
            "Australia/Sydney",
        )

    def test_profile_country_update_changes_only_self_timezone(self):
        store = FakeAccountStore()
        worker = os_accounts.create_worker_account(
            username="worker",
            display_name="Worker",
            password="Worker password 26!",
            page_keys=("dashboard",),
            store=store,
        )

        updated = os_accounts.update_my_profile(
            worker["id"],
            display_name="VA One",
            country="Australia",
            store=store,
        )

        self.assertEqual(updated["display_name"], "VA One")
        self.assertEqual(updated["country"], "Australia")
        self.assertEqual(updated["timezone"], "Australia/Sydney")
        self.assertEqual(updated["role"], "worker")
        self.assertEqual(updated["page_permissions"], ["dashboard"])

    def test_change_my_password_requires_current_password_and_strength(self):
        store = FakeAccountStore()
        worker = os_accounts.create_worker_account(
            username="worker",
            display_name="Worker",
            password="Worker password 26!",
            page_keys=("dashboard",),
            store=store,
        )

        with self.assertRaises(ValueError):
            os_accounts.change_my_password(
                worker["id"],
                current_password="wrong",
                new_password="New password 27!",
                store=store,
            )
        updated = os_accounts.change_my_password(
            worker["id"],
            current_password="Worker password 26!",
            new_password="New password 27!",
            store=store,
        )

        self.assertTrue(os_accounts.verify_password("New password 27!", updated["password_hash"]))

    def test_account_migration_contains_both_required_tables(self):
        sql = (ROOT / "migrations" / "20260722_os_accounts_access.sql").read_text(encoding="utf-8")
        account_controls_sql = (ROOT / "migrations" / "20260810_account_access_controls.sql").read_text(
            encoding="utf-8"
        )

        self.assertIn("CREATE TABLE IF NOT EXISTS os_users", sql)
        self.assertIn("country TEXT NOT NULL DEFAULT 'Philippines'", sql)
        self.assertIn("timezone TEXT NOT NULL DEFAULT 'Asia/Manila'", sql)
        self.assertIn("Australia", sql)
        self.assertIn("Philippines", sql)
        self.assertIn("Australia/Sydney", sql)
        self.assertIn("Asia/Manila", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS os_user_page_permissions", sql)
        self.assertIn("REFERENCES os_users(id) ON DELETE CASCADE", sql)
        self.assertIn("session_version INTEGER DEFAULT 1", account_controls_sql)
        self.assertIn("account_status TEXT DEFAULT 'active'", account_controls_sql)
        self.assertIn("removed_at TIMESTAMPTZ", account_controls_sql)
        self.assertIn("removed_by UUID", account_controls_sql)
        self.assertIn("Existing users remain active", account_controls_sql)

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
            self.assertNotIn("https://dropbox.test/temporary/collector.pdf", browser_text)
            file_open_details.assert_not_called()

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
        self.assertIn("Use Open to launch Adobe Photoshop", text)
        self.assertIn("Download", text)
        self.assertNotIn("Download and open", text)

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
        ) as list_folder_mock:
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

            self.assertEqual(len(app_test.text_input), 1)
            self.assertEqual(app_test.text_input[0].label, "Search current folder")
            app_test.session_state["files_browser_path"] = root_path
            app_test.run(timeout=20)
            root_text = self._app_text(app_test)
            self.assertIn("05 Mockups", root_text)
            self.assertIn("File folder", root_text)
            self.assertEqual(list_folder_mock.call_count, 1)

            app_test.text_input[0].input("mockups")
            app_test.run(timeout=20)
            self.assertIn("05 Mockups", self._app_text(app_test))
            self.assertEqual(list_folder_mock.call_count, 1)
            app_test.text_input[0].input("")
            app_test.run(timeout=20)
            self.assertEqual(list_folder_mock.call_count, 1)

            app_test.session_state["files_navigation_history"] = [root_path]
            app_test.session_state["files_browser_path"] = mockups_path
            app_test.run(timeout=20)
            empty_text = self._app_text(app_test)
            self.assertIn("This folder is empty", empty_text)
            self.assertIn("Files", empty_text)
            self.assertIn("Sportscave Team Folder", empty_text)
            self.assertIn("05 Mockups", empty_text)
            self.assertEqual(app_test.session_state["files_browser_path"], mockups_path)
            self.assertEqual(list_folder_mock.call_count, 2)

            next(button for button in app_test.button if button.label == "Back").click()
            app_test.run(timeout=20)
            self.assertEqual(app_test.session_state["files_browser_path"], root_path)
            self.assertEqual(list_folder_mock.call_count, 2)

            next(button for button in app_test.button if button.label == "Forward").click()
            app_test.run(timeout=20)
            self.assertEqual(app_test.session_state["files_browser_path"], mockups_path)
            self.assertEqual(list_folder_mock.call_count, 2)

            next(
                button
                for button in app_test.button
                if button.label == "Sportscave Team Folder"
            ).click()
            app_test.run(timeout=20)
            self.assertEqual(app_test.session_state["files_browser_path"], root_path)
            self.assertEqual(list_folder_mock.call_count, 2)

            app_test.session_state["files_navigation_history"] = [root_path]
            app_test.session_state["files_browser_path"] = mockups_path
            app_test.run(timeout=20)
            next(button for button in app_test.button if button.label == "Up").click()
            app_test.run(timeout=20)
            self.assertEqual(app_test.session_state["files_browser_path"], root_path)
            self.assertEqual(list_folder_mock.call_count, 2)

            next(button for button in app_test.button if button.label == "Refresh").click()
            app_test.run(timeout=20)
            self.assertEqual(list_folder_mock.call_count, 3)

        self.assertFalse(app_test.exception)

    def test_files_workspace_has_compact_write_controls_and_current_folder_drop_target(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        component = (ROOT / "components" / "files_chunk_uploader" / "index.html").read_text(
            encoding="utf-8"
        )
        command_bar = source[
            source.index("def _render_files_command_bar") : source.index("\n\ndef _render_files_rename_action")
        ]
        browser = source[
            source.index("def _render_files_browser") : source.index("\n\ndef render_files_page")
        ]
        upload = source[
            source.index("def _render_files_chunk_uploader") : source.index("\n\ndef _render_files_command_bar")
        ]

        self.assertIn("new_folder_requested", component)
        self.assertIn("**New folder**", command_bar)
        self.assertIn(">New</button>", component)
        self.assertIn(">Upload <", component)
        self.assertIn(">Rename</button>", component)
        self.assertIn("More actions", component)
        self.assertIn(">Upload files<", component)
        self.assertIn(">Upload folder<", component)
        self.assertIn("webkitdirectory", component)
        self.assertIn("droppedItems", component)
        self.assertIn("current_path", browser)
        self.assertIn("@st.fragment", source)
        self.assertNotIn("_files_route_url", source)
        self.assertIn("Drop files into this folder", component)
        self.assertIn("_files_chunk_component()", upload)
        self.assertNotIn("st.file_uploader", upload + command_bar + browser)
        self.assertIn('"files_folder_created"', source)
        self.assertIn('"files_item_renamed"', source)

    def test_files_navigation_uses_fragment_state_without_raw_folder_links(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        browser = source[
            source.index("@st.fragment\ndef _render_files_browser") : source.index(
                "\n\ndef render_files_page"
            )
        ]
        details = source[
            source.index("def _render_files_details") : source.index(
                "\n\ndef _files_preview_kind"
            )
        ]
        breadcrumb = source[
            source.index("def _render_files_navigation") : source.index(
                "\n\ndef _files_row_icon"
            )
        ]

        self.assertIn("@st.fragment", browser)
        self.assertIn("_files_directory_entries(access_token, current_path)", browser)
        self.assertIn("on_click=_files_select_item_state", details)
        self.assertNotIn("on_click=_files_open_preview_state", details)
        self.assertNotIn("on_click=_files_navigate_folder_state", details)
        self.assertIn("on_click=_files_navigate_folder_state", breadcrumb)
        self.assertIn('"Back"', breadcrumb)
        self.assertIn('"Forward"', breadcrumb)
        self.assertIn('"Up"', breadcrumb)
        self.assertIn('"Refresh"', breadcrumb)
        self.assertIn('"Search current folder"', breadcrumb)
        self.assertNotIn("href=", details)
        self.assertNotIn("href=", breadcrumb)
        self.assertNotIn("st.query_params", details)
        self.assertNotIn("st.query_params", breadcrumb)

    def test_files_rows_use_windows_selection_open_and_context_menu_contract(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        component = (ROOT / "components" / "files_chunk_uploader" / "index.html").read_text(
            encoding="utf-8"
        )
        details = source[
            source.index("def _render_files_details") : source.index(
                "\n\ndef _files_interaction_rows"
            )
        ]
        preview = source[
            source.index("def _files_open_strategy") : source.index(
                "\n\ndef _files_clear_directory_cache"
            )
        ]

        self.assertIn("on_click=_files_select_item_state", details)
        self.assertIn('addEventListener("dblclick"', component)
        self.assertIn('event.key === "Enter"', component)
        self.assertIn('event.key === "Escape"', component)
        self.assertIn('addEventListener("contextmenu"', component)
        self.assertIn('emitCommand("selection_changed"', component)
        self.assertIn('function openItem(item)', component)
        self.assertIn('sports-cave-files://open?path=', component)
        self.assertIn('contextAction(menu, "Open"', component)
        self.assertIn('contextAction(menu, "Preview"', component)
        self.assertIn('contextAction(menu, "Rename"', component)
        self.assertIn('contextAction(menu, "Download"', component)
        self.assertIn('contextAction(menu, "Properties"', component)
        self.assertIn('window.parent.open(url, "_blank"', component)
        self.assertIn('desktop_available=_files_desktop_open_available', preview)
        self.assertIn('return "desktop"', preview)
        self.assertIn('return "details"', preview)
        self.assertNotIn("Download and open", preview)

    def test_files_explorer_styles_are_compact_neutral_and_scoped(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        component = (ROOT / "components" / "files_chunk_uploader" / "index.html").read_text(
            encoding="utf-8"
        )
        files_css = source[
            source.index(".st-key-files-explorer") : source.index(".sc-task-card")
        ]
        details = source[
            source.index("def _render_files_details") : source.index("\n\ndef _files_preview_kind")
        ]

        self.assertIn("height: 42px", files_css)
        self.assertIn("height: 40px", files_css)
        self.assertIn("height: 36px", files_css)
        self.assertIn("height: calc(100dvh - 0.9rem)", files_css)
        self.assertIn("height: 100dvh", files_css)
        self.assertIn("overflow: hidden", files_css)
        self.assertIn("height: 100%", files_css)
        self.assertNotIn("max-height: calc(100vh - 205px)", files_css)
        self.assertIn("background: transparent !important", files_css)
        self.assertNotIn("var(--sc-gold)", files_css)
        self.assertNotIn("files-breadcrumb-native", files_css)
        self.assertIn("<span role=\"columnheader\">Status</span>", details)
        self.assertNotIn("20MB per file", component)
        self.assertIn('class="menu"', component)
        self.assertIn("Large files supported", component)
        self.assertIn("background: #FFFFFF !important", files_css)
        self.assertIn("background: #DCECF7 !important", files_css)
        navigation_css = files_css[
            files_css.index(".st-key-files-navigation-row") : files_css.index(
                ".st-key-files-command-bar"
            )
        ]
        self.assertNotIn("#D4A54C", navigation_css)
        self.assertNotIn("#E1B23D", navigation_css)
        self.assertIn('.st-key-files-navigation-row div[data-testid="stButton"] button', navigation_css)
        self.assertIn('.st-key-files-address-bar div[data-testid="stButton"] button', navigation_css)
        self.assertIn("st-key-files-row-native-photoshop-", files_css)
        self.assertIn('content: "PS"', files_css)

    def test_files_header_is_removed_only_in_the_files_workspace(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        files_css = source[
            source.index(".st-key-files-explorer") : source.index(".sc-task-card")
        ]

        scoped_header = '.stApp:has(.st-key-files-explorer) header[data-testid="stHeader"]'
        self.assertIn(scoped_header, files_css)
        self.assertIn("pointer-events: none !important", files_css)
        self.assertIn("padding-top: 0.45rem !important", files_css)
        self.assertNotIn("margin-top: -0.2rem", files_css)
        self.assertNotIn('header[data-testid="stHeader"] {\n            display: none', source[: source.index(".st-key-files-explorer")])

    def test_files_search_filters_cached_metadata_without_recursive_dropbox_work(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        filter_helper = source[
            source.index("def _files_filter_entries") : source.index(
                "\n\ndef _files_address_items"
            )
        ]
        browser = source[
            source.index("@st.fragment\ndef _render_files_browser") : source.index(
                "\n\ndef render_files_page"
            )
        ]

        self.assertIn("clean_query", filter_helper)
        self.assertIn("casefold()", filter_helper)
        self.assertIn("dropbox_integration.sort_folder_entries(rows)", filter_helper)
        self.assertNotIn("list_folder", filter_helper)
        self.assertNotIn("recursive", filter_helper)
        self.assertIn("_files_filter_entries(entries, search_query)", browser)
        self.assertIn("No items match your search", browser)

    def test_files_operations_invalidate_only_affected_directory_caches(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        upload = source[
            source.index("def _render_files_chunk_uploader") : source.index(
                "\n\ndef _render_files_command_bar"
            )
        ]
        command_bar = source[
            source.index("def _render_files_command_bar") : source.index(
                "\n\ndef _render_files_rename_action"
            )
        ]
        rename = source[
            source.index("def _render_files_rename_action") : source.index(
                "\n\ndef _files_apply_initial_route"
            )
        ]
        mockup_save = source[
            source.index("def _save_mockups_to_dropbox") : source.index(
                "\n\ndef _open_files_folder"
            )
        ]

        self.assertIn("_files_clear_directory_cache(event_path)", upload)
        self.assertIn("_files_clear_directory_cache(current_path)", command_bar)
        self.assertIn("selected_path", rename)
        self.assertIn("renamed_path", rename)
        self.assertIn("_files_changed_directory_paths(destination, successes)", mockup_save)
        self.assertNotIn('pop("files_directory_cache"', upload + command_bar + rename + mockup_save)

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
        values.extend(str(item.label) for item in app_test.button)
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

    def test_worker_home_renders_activity_log_when_admin_approves_it(self):
        app_test = AppTest.from_file(str(ROOT / "app.py"))
        app_test.session_state["sports_cave_authenticated"] = True
        app_test.session_state["sports_cave_current_user"] = {
            "id": "worker-1",
            "username": "worker",
            "display_name": "Maria",
            "role": "worker",
            "timezone": os_accounts.WORKER_TIMEZONE,
            "is_active": True,
            "page_permissions": ["dashboard", os_accounts.ACTIVITY_LOG_CAPABILITY],
        }
        app_test.session_state["sports_cave_auth_checked_at"] = time.monotonic()
        app_test.session_state["selected_page"] = "Dashboard"

        app_test.run(timeout=20)

        text = self._app_text(app_test)
        self.assertFalse(app_test.exception)
        self.assertIn("Recent operational activity", text)
        self.assertNotIn("Activity log", text)
        self.assertFalse(any(select.label == "User" for select in app_test.selectbox))
        self.assertNotIn("Daily Task Execution Sheet", text)

    def test_accounts_access_exposes_activity_log_permission_tick(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        permission_source = source[
            source.index("def _account_permission_fields") :
            source.index("\n\ndef render_accounts_access_page")
        ]

        self.assertIn('"View activity log"', permission_source)
        self.assertIn("os_accounts.ACTIVITY_LOG_CAPABILITY", permission_source)

    def test_accounts_access_exposes_prompt_editing_permission_tick(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        permission_source = source[
            source.index("def _account_permission_fields") :
            source.index("\n\ndef render_accounts_access_page")
        ]

        self.assertIn('"Edit prompts"', permission_source)
        self.assertIn("os_accounts.EDIT_PROMPTS_CAPABILITY", permission_source)
        self.assertIn("create-worker-permission", source)
        self.assertIn("edit-worker-permission", source)

    def test_accounts_access_exposes_password_access_permission_ticks(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        registry_source = (ROOT / "shared_credentials.py").read_text(encoding="utf-8")
        password_source = source[
            source.index("def _credential_permission_fields") :
            source.index("\n\ndef _country_select")
        ]

        self.assertIn("Password Access", source)
        self.assertIn("credential_prodigi", registry_source)
        self.assertIn("credential_adobe", registry_source)
        self.assertIn("credential_chatgpt", registry_source)
        self.assertIn("create-worker-credential-permission", source)
        self.assertIn("edit-worker-credential-permission", source)
        self.assertIn("actor=user", source)
        self.assertIn("spec.permission_key", password_source)

    def test_passwords_render_masks_before_authorised_reveal(self):
        worker = {
            "id": "worker-credentials",
            "username": "worker",
            "display_name": "Worker",
            "role": "worker",
            "is_active": True,
            "page_permissions": ["credential_prodigi"],
        }
        app_test = AppTest.from_file(str(ROOT / "app.py"))
        app_test.session_state["sports_cave_authenticated"] = True
        app_test.session_state["sports_cave_current_user"] = worker
        app_test.session_state["sports_cave_auth_checked_at"] = time.monotonic()
        app_test.session_state["selected_page"] = "Accounts & Access"

        with patch.object(os_accounts.DEFAULT_STORE, "get_user", return_value=worker), patch.dict(
            "os.environ",
            {
                "PRODIGI_USERNAME": "shared-prodigi-login@example.test",
                "PRODIGI_PASSWORD": "unit-test-prodigi-password-value",
                "ADOBE_USERNAME": "shared-adobe-login@example.test",
                "ADOBE_PASSWORD": "unit-test-adobe-password-value",
                "CHATGPT_USERNAME": "shared-chatgpt-login@example.test",
                "CHATGPT_PASSWORD": "unit-test-chatgpt-password-value",
            },
            clear=False,
        ):
            app_test.run(timeout=20)

        text = self._app_text(app_test)
        self.assertFalse(app_test.exception)
        self.assertIn("Passwords", text)
        self.assertIn("Prodigi", text)
        self.assertIn("shared-prodigi-login@example.test", text)
        self.assertIn(shared_credentials.MASKED_PASSWORD, text)
        self.assertNotIn("unit-test-prodigi-password-value", text)
        self.assertNotIn("Adobe", text)
        self.assertNotIn("ChatGPT", text)

    def test_credential_cards_keep_single_copy_row_and_toast_notifications(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        card_source = source[
            source.index("def _render_credential_card") :
            source.index("\n\ndef _record_credential_permission_changes")
        ]
        clipboard_source = source[
            source.index("def _render_secure_clipboard_write") :
            source.index("\n\ndef _render_revealed_password_value")
        ]

        self.assertIn("copy_cols = st.columns(2", card_source)
        self.assertEqual(card_source.count('"Copy username"'), 1)
        self.assertEqual(card_source.count('"Copy password"'), 1)
        self.assertIn('_show_credential_toast("Username copied to clipboard")', card_source)
        self.assertIn('_show_credential_toast("Password copied to clipboard")', card_source)
        self.assertNotIn("st.success", card_source)
        self.assertIn('reveal_clicked = st.button(\n                " "', card_source)
        self.assertNotIn('"Hide" if password_revealed else "Reveal",', card_source)
        self.assertNotIn("<button", clipboard_source)
        self.assertIn("navigator.clipboard.writeText(copyText)", clipboard_source)
        self.assertIn("height=0", clipboard_source)

    def test_worker_without_password_permissions_sees_empty_state_only(self):
        worker = {
            "id": "worker-no-credentials",
            "username": "worker",
            "display_name": "Worker",
            "role": "worker",
            "is_active": True,
            "page_permissions": [],
        }
        app_test = AppTest.from_file(str(ROOT / "app.py"))
        app_test.session_state["sports_cave_authenticated"] = True
        app_test.session_state["sports_cave_current_user"] = worker
        app_test.session_state["sports_cave_auth_checked_at"] = time.monotonic()
        app_test.session_state["selected_page"] = "Accounts & Access"

        with patch.object(os_accounts.DEFAULT_STORE, "get_user", return_value=worker), patch.dict(
            "os.environ",
            {
                "PRODIGI_USERNAME": "shared-prodigi-login@example.test",
                "PRODIGI_PASSWORD": "unit-test-prodigi-password-value",
                "ADOBE_USERNAME": "shared-adobe-login@example.test",
                "ADOBE_PASSWORD": "unit-test-adobe-password-value",
                "CHATGPT_USERNAME": "shared-chatgpt-login@example.test",
                "CHATGPT_PASSWORD": "unit-test-chatgpt-password-value",
            },
            clear=False,
        ):
            app_test.run(timeout=20)

        text = self._app_text(app_test)
        self.assertFalse(app_test.exception)
        self.assertIn("No shared password access has been assigned.", text)
        self.assertNotIn("Prodigi", text)
        self.assertNotIn("Adobe", text)
        self.assertNotIn("ChatGPT", text)
        self.assertNotIn("shared-prodigi-login@example.test", text)
        self.assertNotIn("unit-test-prodigi-password-value", text)

    def test_prompt_edit_surfaces_use_account_permission_without_developer_passwords(self):
        sources = {
            filename: (ROOT / filename).read_text(encoding="utf-8")
            for filename in (
                "app.py",
                "os_pages.py",
                "design_studio_page.py",
                "social_media_reels_studio_page.py",
            )
        }

        for filename, source in sources.items():
            with self.subTest(filename=filename):
                self.assertNotIn("Developer password", source)
                self.assertNotIn("DEVELOPER_PAGE_PASSWORD", source)
                self.assertNotIn("developer_unlocked", source)

        app_prompt_button = sources["app.py"][
            sources["app.py"].index("def render_prompt_edit_button") :
            sources["app.py"].index("\n\ndef render_prompt_edit_panel")
        ]
        self.assertIn("if not prompt_editing_allowed():", app_prompt_button)
        self.assertIn("return False", app_prompt_button)
        self.assertIn("if can_edit_prompts:", sources["design_studio_page.py"])
        self.assertIn("editing_enabled = bool(can_edit_prompts)", sources["social_media_reels_studio_page.py"])

    def test_product_upload_prompt_edit_buttons_follow_account_permission(self):
        def render_for(user):
            app_test = AppTest.from_file(str(ROOT / "app.py"))
            app_test.session_state["sports_cave_authenticated"] = True
            app_test.session_state["sports_cave_current_user"] = user
            app_test.session_state["sports_cave_auth_checked_at"] = time.monotonic()
            app_test.session_state["current_page"] = "Product Uploads"
            app_test.session_state["selected_page"] = "Product Uploads"
            app_test.run(timeout=20)
            self.assertFalse(app_test.exception)
            return sum(button.label == "\u270e" for button in app_test.button)

        worker = {
            "id": "worker-no-prompt-edit",
            "username": "worker",
            "display_name": "Worker",
            "role": "worker",
            "is_active": True,
            "page_permissions": ["product_uploads"],
        }
        approved_worker = {
            **worker,
            "id": "worker-with-prompt-edit",
            "page_permissions": [
                "product_uploads",
                os_accounts.EDIT_PROMPTS_CAPABILITY,
            ],
        }
        admin = {
            "id": "admin-prompt-edit",
            "username": "nathan",
            "display_name": "Nathan",
            "role": "admin",
            "is_active": True,
            "page_permissions": [],
        }

        self.assertEqual(render_for(worker), 0)
        self.assertEqual(render_for(approved_worker), 2)
        self.assertEqual(render_for(admin), 2)

    def test_admin_home_renders_compact_operational_activity(self):
        owner_email = "owner@sportscave.test"
        app_test = AppTest.from_file(str(ROOT / "app.py"))
        app_test.session_state["sports_cave_authenticated"] = True
        app_test.session_state["sports_cave_current_user"] = {
            "id": "admin-1",
            "username": "nathan",
            "email": owner_email,
            "display_name": "Nathan",
            "role": "admin",
            "timezone": os_accounts.ADMIN_TIMEZONE,
            "is_active": True,
            "page_permissions": [os_accounts.REPORTING_PAGE_KEY],
        }
        app_test.session_state["sports_cave_auth_checked_at"] = time.monotonic()
        app_test.session_state["selected_page"] = "Dashboard"

        with patch.dict(
            "os.environ",
            {"SPORTS_CAVE_REPORTING_OWNER_EMAIL": owner_email},
            clear=False,
        ):
            app_test.run(timeout=20)

        text = self._app_text(app_test)
        self.assertFalse(app_test.exception)
        self.assertIn("Active alerts", text)
        self.assertIn("Recent operational activity", text)
        self.assertNotIn("Daily Task Execution Sheet - The 5 Million Dollar Man", text)

    def test_admin_home_renders_after_daily_execution_save_with_legacy_other_tasks(self):
        class DailyExecutionBackend:
            def is_configured(self):
                return True

            def list_dashboard_tasks(self, status="open", *, limit=200):
                return []

            def list_activity_logs(
                self,
                *,
                start_at=None,
                end_at=None,
                limit=200,
                actor_user_id=None,
                actor_email=None,
            ):
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

        owner_email = "owner@sportscave.test"
        app_test = AppTest.from_file(str(ROOT / "app.py"))
        app_test.session_state["sports_cave_authenticated"] = True
        app_test.session_state["sports_cave_current_user"] = {
            "id": "admin-1",
            "username": "nathan",
            "email": owner_email,
            "display_name": "Nathan",
            "role": "admin",
            "timezone": os_accounts.ADMIN_TIMEZONE,
            "is_active": True,
            "page_permissions": [os_accounts.REPORTING_PAGE_KEY],
        }
        app_test.session_state["sports_cave_auth_checked_at"] = time.monotonic()
        app_test.session_state["selected_page"] = "Reporting"

        with patch.object(
            sports_cave_dashboard,
            "get_supabase_backend",
            return_value=DailyExecutionBackend(),
        ), patch.dict(
            "os.environ",
            {"SPORTS_CAVE_REPORTING_OWNER_EMAIL": owner_email},
            clear=False,
        ):
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
        reporting_source = source[
            source.index('elif current_page == "Reporting"') :
            source.index('elif current_page == "Files"')
        ]

        self.assertIn("if not os_accounts.is_reporting_owner(user):", panel_source)
        self.assertIn("Access not approved", panel_source)
        self.assertNotIn("render_daily_execution_panel", dashboard_source)
        self.assertIn("if os_accounts.is_reporting_owner(reporting_user):", reporting_source)
        self.assertIn("render_daily_execution_panel(local_now, events, {}, show_denied=False)", reporting_source)


if __name__ == "__main__":
    unittest.main()
