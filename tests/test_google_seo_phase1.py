import asyncio
from datetime import timedelta
import inspect
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

from cryptography.fernet import Fernet

import google_seo
import google_seo_api
import os_accounts
import run_migrations
import seo_page


ROOT = Path(__file__).resolve().parents[1]


def admin_user():
    return {
        "id": "admin-1",
        "display_name": "Nathan",
        "role": os_accounts.ROLE_ADMIN,
        "is_active": True,
        "session_version": 1,
    }


def worker_user():
    return {
        "id": "worker-1",
        "display_name": "Worker",
        "role": os_accounts.ROLE_WORKER,
        "is_active": True,
    }


def config():
    return {
        "client_id": "client-id.example",
        "client_secret": "client-secret.example",
        "redirect_uri": "http://localhost:8501/api/os/google/oauth/callback",
        "encryption_key": Fernet.generate_key().decode("ascii"),
    }


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class FakeUI:
    class Node:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def button(self, *_args, **_kwargs):
            return False

        def markdown(self, *_args, **_kwargs):
            return None

        def metric(self, *_args, **_kwargs):
            return None

        def caption(self, *_args, **_kwargs):
            return None

    def __init__(self):
        self.query_params = {}
        self.session_state = {}

    def columns(self, spec):
        count = spec if isinstance(spec, int) else len(spec)
        return [self.Node() for _ in range(count)]

    def expander(self, *_args, **_kwargs):
        return self.Node()

    def markdown(self, *_args, **_kwargs):
        return None

    def subheader(self, *_args, **_kwargs):
        return None

    def caption(self, *_args, **_kwargs):
        return None

    def info(self, *_args, **_kwargs):
        return None

    def multiselect(self, *_args, **_kwargs):
        return []

    def progress(self, *_args, **_kwargs):
        return None


class MemoryStore:
    def __init__(self, connection=None):
        self.states = {}
        self.connection = dict(connection or {})
        self.saved_authorizations = []
        self.saved_properties = None
        self.saved_selection = None
        self.failures = []
        self.sync_lock_available = True
        self.completed_sync = None

    def store_oauth_state(self, state_hash, *, user_id, return_page, expires_at):
        self.states[state_hash] = {
            "state_hash": state_hash,
            "user_id": user_id,
            "return_page": return_page,
            "expires_at": expires_at,
            "used_at": None,
        }

    def consume_oauth_state(self, state_hash, *, user_id, now):
        row = self.states.get(state_hash)
        if not row:
            raise google_seo.GoogleOAuthStateError(
                "Invalid state.", code="state_invalid", stage="oauth_callback"
            )
        if row.get("used_at"):
            raise google_seo.GoogleOAuthStateError(
                "Used state.", code="state_reused", stage="oauth_callback"
            )
        if row["expires_at"] <= now:
            raise google_seo.GoogleOAuthStateError(
                "Expired state.", code="state_expired", stage="oauth_callback"
            )
        if row["user_id"] != user_id:
            raise google_seo.GoogleOAuthStateError(
                "Mismatched state.", code="state_user_mismatch", stage="oauth_callback"
            )
        row["used_at"] = now
        return dict(row)

    def get_connection_secret(self):
        return dict(self.connection)

    def get_connection(self):
        return dict(self.connection)

    def save_authorization(self, **values):
        self.saved_authorizations.append(dict(values))
        self.connection["encrypted_refresh_token"] = values["encrypted_refresh_token"]

    def save_discovered_properties(self, gsc_properties, ga4_properties):
        self.saved_properties = (list(gsc_properties), list(ga4_properties))
        self.connection["available_gsc_properties"] = list(gsc_properties)
        self.connection["available_ga4_properties"] = list(ga4_properties)

    def save_selection(self, **values):
        self.saved_selection = dict(values)

    def acquire_sync_lock(self, lock_token):
        self.lock_token = lock_token
        return self.sync_lock_available

    def complete_sync(self, lock_token, *, gsc_data_date, ga4_data_date):
        self.completed_sync = (lock_token, gsc_data_date, ga4_data_date)

    def record_failure(self, **values):
        self.failures.append(dict(values))

    def disconnect(self, *, user_id):
        self.disconnected_by = user_id
        self.connection["encrypted_refresh_token"] = None


class GoogleConfigurationAndOAuthTests(unittest.TestCase):
    def test_missing_and_invalid_environment_configuration(self):
        status = google_seo.configuration_status({})
        self.assertFalse(status["ready"])
        self.assertEqual(set(status["missing"]), set(google_seo.GOOGLE_REQUIRED_ENV_VARS))
        invalid = {
            "GOOGLE_OAUTH_CLIENT_ID": "id",
            "GOOGLE_OAUTH_CLIENT_SECRET": "secret",
            "GOOGLE_OAUTH_REDIRECT_URI": "http://example.com/wrong",
            "GOOGLE_TOKEN_ENCRYPTION_KEY": "not-a-fernet-key",
        }
        status = google_seo.configuration_status(invalid)
        self.assertFalse(status["ready"])
        self.assertIn("GOOGLE_OAUTH_REDIRECT_URI", status["invalid"])
        self.assertIn("GOOGLE_TOKEN_ENCRYPTION_KEY", status["invalid"])

    def test_authorization_url_has_exact_read_only_scopes_and_offline_access(self):
        parsed = urlparse(google_seo.build_authorization_url("state-value", config()))
        query = parse_qs(parsed.query)
        self.assertEqual(set(query["scope"][0].split()), set(google_seo.GOOGLE_SCOPES))
        self.assertEqual(len(query["scope"][0].split()), 2)
        self.assertEqual(query["access_type"], ["offline"])
        self.assertEqual(query["prompt"], ["consent"])
        self.assertEqual(query["response_type"], ["code"])
        self.assertEqual(query["state"], ["state-value"])
        self.assertFalse(any("write" in scope for scope in query["scope"][0].split()))

    def test_state_is_hashed_one_time_expiring_and_user_bound(self):
        store = MemoryStore()
        now = google_seo.utc_now()
        url = google_seo.create_oauth_request(store, admin_user(), config(), now=now)
        raw_state = parse_qs(urlparse(url).query)["state"][0]
        self.assertNotIn(raw_state, store.states)
        self.assertIn(google_seo.oauth_state_hash(raw_state), store.states)
        record = google_seo.consume_oauth_state(store, raw_state, admin_user(), now=now)
        self.assertEqual(record["return_page"], "seo")
        with self.assertRaisesRegex(google_seo.GoogleOAuthStateError, "Used"):
            google_seo.consume_oauth_state(store, raw_state, admin_user(), now=now)

        expired = "expired-state"
        store.store_oauth_state(
            google_seo.oauth_state_hash(expired),
            user_id="admin-1",
            return_page="seo",
            expires_at=now - timedelta(seconds=1),
        )
        with self.assertRaisesRegex(google_seo.GoogleOAuthStateError, "Expired"):
            google_seo.consume_oauth_state(store, expired, admin_user(), now=now)

        mismatched = "mismatched-state"
        store.store_oauth_state(
            google_seo.oauth_state_hash(mismatched),
            user_id="another-admin",
            return_page="seo",
            expires_at=now + timedelta(minutes=1),
        )
        with self.assertRaisesRegex(google_seo.GoogleOAuthStateError, "Mismatched"):
            google_seo.consume_oauth_state(store, mismatched, admin_user(), now=now)
        with self.assertRaisesRegex(google_seo.GoogleOAuthStateError, "verified"):
            google_seo.consume_oauth_state(store, "", admin_user(), now=now)

    def test_partial_scope_permission_is_rejected(self):
        with self.assertRaisesRegex(google_seo.GoogleSEOError, "Both Search Console"):
            google_seo.verify_required_scopes({"scope": google_seo.GOOGLE_SCOPES[0]})

    def test_refresh_token_is_encrypted_and_preserved_when_google_omits_it(self):
        settings = config()
        existing = google_seo.encrypt_refresh_token("existing-refresh", settings["encryption_key"])
        store = MemoryStore({"encrypted_refresh_token": existing})
        token_payload = {
            "access_token": "temporary-access",
            "scope": " ".join(google_seo.GOOGLE_SCOPES),
        }

        def get(url, **_kwargs):
            if url == google_seo.GSC_SITES_ENDPOINT:
                return FakeResponse({"siteEntry": [{"siteUrl": "sc-domain:sportscave.com.au"}]})
            return FakeResponse(
                {
                    "accountSummaries": [
                        {
                            "displayName": "Sports Cave",
                            "propertySummaries": [
                                {"property": "properties/123", "displayName": "Sports Cave GA4"}
                            ],
                        }
                    ]
                }
            )

        with patch.object(google_seo, "_record_activity"):
            google_seo.complete_authorization(
                store,
                admin_user(),
                "one-time-code",
                settings,
                request_post=lambda *_args, **_kwargs: FakeResponse(token_payload),
                request_get=get,
            )
        saved = store.saved_authorizations[0]["encrypted_refresh_token"]
        self.assertEqual(saved, existing)
        self.assertNotIn("existing-refresh", saved)
        self.assertEqual(
            google_seo.decrypt_refresh_token(saved, settings["encryption_key"]),
            "existing-refresh",
        )

    def test_new_refresh_token_is_encrypted_before_persistence(self):
        settings = config()
        store = MemoryStore()

        def get(url, **_kwargs):
            if url == google_seo.GSC_SITES_ENDPOINT:
                return FakeResponse({"siteEntry": []})
            return FakeResponse({"accountSummaries": []})

        token_payload = {
            "access_token": "temporary-access",
            "refresh_token": "new-private-refresh",
            "scope": " ".join(google_seo.GOOGLE_SCOPES),
        }
        with patch.object(google_seo, "_record_activity"):
            google_seo.complete_authorization(
                store,
                admin_user(),
                "one-time-code",
                settings,
                request_post=lambda *_args, **_kwargs: FakeResponse(token_payload),
                request_get=get,
            )
        encrypted = store.saved_authorizations[0]["encrypted_refresh_token"]
        self.assertNotEqual(encrypted, "new-private-refresh")
        self.assertNotIn("new-private-refresh", str(store.saved_authorizations))
        self.assertEqual(
            google_seo.decrypt_refresh_token(encrypted, settings["encryption_key"]),
            "new-private-refresh",
        )

    def test_server_route_rejects_stale_account_session_version(self):
        request = SimpleNamespace(
            cookies={google_seo_api.sc_auth.AUTH_COOKIE_NAME: "signed-token"}
        )
        account = {**admin_user(), "session_version": 2}
        with patch.object(
            google_seo_api.sc_auth,
            "validate_user_auth_token",
            return_value=(True, "ok", {"sub": "admin-1", "sv": 1}),
        ), patch.object(
            google_seo_api.sc_auth,
            "validate_auth_token",
            return_value=(False, "invalid"),
        ), patch.object(
            google_seo_api.os_accounts.DEFAULT_STORE,
            "get_user",
            return_value=account,
        ):
            with self.assertRaises(google_seo_api.GoogleSEOAccessError):
                google_seo_api._request_admin(request)

    def test_server_route_rejects_legacy_cookie_after_account_setup(self):
        request = SimpleNamespace(
            cookies={google_seo_api.sc_auth.AUTH_COOKIE_NAME: "legacy-token"}
        )
        with patch.object(
            google_seo_api.sc_auth,
            "validate_user_auth_token",
            return_value=(False, "bad-version", {}),
        ), patch.object(
            google_seo_api.sc_auth,
            "validate_auth_token",
            return_value=(True, "ok"),
        ), patch.object(
            google_seo_api.os_accounts,
            "prepare_account_system",
            return_value={"available": True, "admin": admin_user()},
        ):
            with self.assertRaises(google_seo_api.GoogleSEOAccessError):
                google_seo_api._request_admin(request)

    def test_denied_callback_consumes_state_and_never_exchanges_code(self):
        store = MemoryStore()
        now = google_seo.utc_now()
        raw_state = "denied-state"
        store.store_oauth_state(
            google_seo.oauth_state_hash(raw_state),
            user_id="admin-1",
            return_page="seo",
            expires_at=now + timedelta(minutes=2),
        )
        request = SimpleNamespace(
            cookies={},
            query_params={"state": raw_state, "error": "access_denied"},
        )
        with patch.object(google_seo_api, "_request_admin", return_value=admin_user()), patch.object(
            google_seo, "default_store", return_value=store
        ), patch.object(google_seo, "complete_authorization") as complete:
            response = asyncio.run(google_seo_api.google_oauth_callback(request))
        self.assertIn("google_oauth=denied", response.headers["location"])
        self.assertNotIn("access_denied", response.headers["location"])
        complete.assert_not_called()
        with self.assertRaises(google_seo.GoogleOAuthStateError):
            google_seo.consume_oauth_state(store, raw_state, admin_user(), now=now)

    def test_successful_callback_returns_to_seo_without_raw_parameters(self):
        store = MemoryStore()
        raw_state = "successful-state"
        store.store_oauth_state(
            google_seo.oauth_state_hash(raw_state),
            user_id="admin-1",
            return_page="seo",
            expires_at=google_seo.utc_now() + timedelta(minutes=2),
        )
        request = SimpleNamespace(
            cookies={},
            query_params={"state": raw_state, "code": "private-code"},
        )
        with patch.object(google_seo_api, "_request_admin", return_value=admin_user()), patch.object(
            google_seo, "default_store", return_value=store
        ), patch.object(google_seo, "load_config", return_value=config()), patch.object(
            google_seo, "complete_authorization"
        ) as complete:
            response = asyncio.run(google_seo_api.google_oauth_callback(request))
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/?page=seo&google_oauth=connected")
        self.assertNotIn("private-code", response.headers["location"])
        self.assertNotIn(raw_state, response.headers["location"])
        complete.assert_called_once()


class GooglePropertyAndSyncTests(unittest.TestCase):
    def test_gsc_property_listing_is_safe_and_deduplicated(self):
        response = FakeResponse(
            {
                "siteEntry": [
                    {"siteUrl": "sc-domain:sportscave.com.au", "permissionLevel": "siteOwner"},
                    {"siteUrl": "sc-domain:sportscave.com.au", "permissionLevel": "siteOwner"},
                    {"siteUrl": "https://www.sportscaveshop.com/", "permissionLevel": "siteFullUser"},
                ]
            }
        )
        rows = google_seo.list_gsc_properties(
            "temporary-token",
            request_get=lambda *_args, **_kwargs: response,
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["id"], "sc-domain:sportscave.com.au")

    def test_ga4_account_summary_pagination(self):
        calls = []

        def get(_url, *, params, **_kwargs):
            calls.append(dict(params))
            if not params.get("pageToken"):
                return FakeResponse(
                    {
                        "accountSummaries": [
                            {
                                "displayName": "Sports Cave",
                                "propertySummaries": [
                                    {"property": "properties/100", "displayName": "Main"}
                                ],
                            }
                        ],
                        "nextPageToken": "next-page",
                    }
                )
            return FakeResponse(
                {
                    "accountSummaries": [
                        {
                            "displayName": "Sports Cave",
                            "propertySummaries": [
                                {"property": "properties/200", "displayName": "Store"}
                            ],
                        }
                    ]
                }
            )

        rows = google_seo.list_ga4_properties("temporary-token", request_get=get)
        self.assertEqual([row["id"] for row in rows], ["properties/100", "properties/200"])
        self.assertEqual(calls[1]["pageToken"], "next-page")

    def test_property_selection_is_validated_and_persisted(self):
        store = MemoryStore(
            {
                "available_gsc_properties": [
                    {"id": "sc-domain:sportscave.com.au", "name": "Sports Cave"}
                ],
                "available_ga4_properties": [
                    {"id": "properties/123", "name": "Sports Cave GA4"}
                ],
            }
        )
        with patch.object(google_seo, "_record_activity"):
            google_seo.save_property_selection(
                store,
                admin_user(),
                gsc_site_url="sc-domain:sportscave.com.au",
                ga4_property_id="properties/123",
            )
        self.assertEqual(store.saved_selection["gsc_property"]["id"], "sc-domain:sportscave.com.au")
        self.assertEqual(store.saved_selection["ga4_property"]["id"], "properties/123")
        with self.assertRaises(google_seo.GoogleSEOError):
            google_seo.save_property_selection(
                store,
                admin_user(),
                gsc_site_url="https://wrong.example/",
                ga4_property_id="properties/123",
            )

    def test_connection_mutations_are_admin_only(self):
        store = MemoryStore()
        with self.assertRaises(PermissionError):
            google_seo.create_oauth_request(store, worker_user(), config())
        with self.assertRaises(PermissionError):
            google_seo.save_property_selection(
                store,
                worker_user(),
                gsc_site_url="site",
                ga4_property_id="property",
            )

    def test_duplicate_sync_binding_does_not_call_google(self):
        store = MemoryStore()
        store.sync_lock_available = False
        request_post = Mock()
        request_get = Mock()
        result = google_seo.sync_now(
            store,
            admin_user(),
            config(),
            request_post=request_post,
            request_get=request_get,
        )
        self.assertTrue(result["busy"])
        request_post.assert_not_called()
        request_get.assert_not_called()

    def test_sync_failure_preserves_last_success_and_records_sanitized_state(self):
        store = MemoryStore(
            {
                "gsc_site_url": "sc-domain:sportscave.com.au",
                "ga4_property_id": "properties/123",
                "last_successful_sync_at": "2026-08-12T00:00:00Z",
            }
        )
        with patch.object(
            google_seo,
            "_access_token_for_connection",
            return_value=("temporary", store.connection),
        ), patch.object(
            google_seo,
            "list_gsc_properties",
            return_value=[{"id": "sc-domain:sportscave.com.au"}],
        ), patch.object(
            google_seo,
            "list_ga4_properties",
            return_value=[{"id": "properties/123"}],
        ), patch.object(
            google_seo,
            "latest_gsc_data_date",
            side_effect=google_seo.GoogleSEOError(
                "Google is temporarily unavailable.",
                code="google_network_error",
                stage="gsc_freshness",
            ),
        ), patch.object(google_seo, "_log_safe_error"):
            result = google_seo.sync_now(store, admin_user(), config())
        self.assertFalse(result["ok"])
        self.assertEqual(store.connection["last_successful_sync_at"], "2026-08-12T00:00:00Z")
        self.assertEqual(store.failures[0]["code"], "google_network_error")
        self.assertNotIn("temporary", str(store.failures))

    def test_disconnect_revokes_best_effort_and_always_clears_local_connection(self):
        settings = config()
        encrypted = google_seo.encrypt_refresh_token("private-refresh", settings["encryption_key"])
        store = MemoryStore({"encrypted_refresh_token": encrypted})
        request_post = Mock(return_value=FakeResponse({}, status_code=200))
        with patch.object(google_seo, "_record_activity"):
            result = google_seo.disconnect_google(
                store,
                admin_user(),
                settings,
                request_post=request_post,
            )
        self.assertTrue(result["ok"])
        self.assertTrue(result["revocation_confirmed"])
        self.assertEqual(store.disconnected_by, "admin-1")
        self.assertIsNone(store.connection["encrypted_refresh_token"])
        posted = request_post.call_args.kwargs["data"]
        self.assertEqual(posted["token"], "private-refresh")

    def test_refresh_flow_uses_server_side_refresh_token_grant(self):
        settings = config()
        request_post = Mock(return_value=FakeResponse({"access_token": "short-lived-access"}))
        access = google_seo.refresh_access_token(
            "private-refresh",
            settings,
            request_post=request_post,
        )
        self.assertEqual(access, "short-lived-access")
        payload = request_post.call_args.kwargs["data"]
        self.assertEqual(payload["grant_type"], "refresh_token")
        self.assertEqual(payload["refresh_token"], "private-refresh")


class GoogleStorageAndArchitectureTests(unittest.TestCase):
    def test_migration_is_idempotent_safe_and_stores_only_encrypted_refresh_token(self):
        sql = (ROOT / "migrations" / google_seo.GOOGLE_SEO_MIGRATION).read_text(
            encoding="utf-8"
        )
        self.assertTrue(run_migrations.safe_migration_sql(sql))
        self.assertIn("CREATE TABLE IF NOT EXISTS seo_google_connections", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS seo_google_oauth_states", sql)
        self.assertIn("encrypted_refresh_token", sql)
        self.assertNotIn(" access_token ", sql)
        self.assertIn("workspace_key TEXT PRIMARY KEY", sql)
        self.assertIn("ENABLE ROW LEVEL SECURITY", sql)

    def test_ordinary_overview_render_source_contains_no_google_api_call(self):
        source = inspect.getsource(seo_page._render_overview)
        forbidden = (
            "requests.get",
            "requests.post",
            "list_gsc_properties",
            "list_ga4_properties",
            "refresh_access_token",
        )
        for value in forbidden:
            self.assertNotIn(value, source)
        self.assertIn("get_connection", source)

    def test_ordinary_overview_render_invokes_no_google_http_client(self):
        ui = FakeUI()
        store = MemoryStore(
            {
                "has_refresh_token": False,
                "connection_status": "Not connected",
                "available_gsc_properties": [],
                "available_ga4_properties": [],
            }
        )
        viewer = {**worker_user(), "page_permissions": ["seo"]}
        with patch.object(seo_page, "st", ui), patch.object(
            seo_page,
            "_shopify_health",
            return_value={"status": "Connected", "last_sync": "2026-08-12"},
        ), patch.object(google_seo.requests, "get") as request_get, patch.object(
            google_seo.requests,
            "post",
        ) as request_post:
            seo_page._render_overview({}, viewer, None, store)
        request_get.assert_not_called()
        request_post.assert_not_called()

    def test_callback_routes_are_registered_and_callback_access_logs_are_filtered(self):
        routes = {path: methods for path, _handler, methods in google_seo_api.GOOGLE_SEO_ROUTE_HANDLERS}
        self.assertEqual(routes[google_seo.GOOGLE_OAUTH_CONNECT_PATH], ("GET",))
        self.assertEqual(routes[google_seo.GOOGLE_OAUTH_CALLBACK_PATH], ("GET",))
        server = (ROOT / "sports_cave_server.py").read_text(encoding="utf-8")
        self.assertIn("*GOOGLE_SEO_ROUTE_HANDLERS", server)
        self.assertIn("_GoogleOAuthAccessLogFilter", server)

    def test_ui_and_safe_logging_do_not_emit_credentials_or_tokens(self):
        ui_source = (ROOT / "seo_page.py").read_text(encoding="utf-8")
        self.assertNotIn("GOOGLE_OAUTH_CLIENT_SECRET", ui_source)
        self.assertNotIn("encrypted_refresh_token", ui_source)
        with patch.object(google_seo.logging, "warning") as warning, patch.dict(
            "sys.modules",
            {"supabase_backend": SimpleNamespace(log_app_error=Mock())},
        ):
            google_seo._log_safe_error(
                google_seo.GoogleSEOError(
                    "secret-value-must-not-log",
                    code="safe_code",
                    stage="test",
                ),
                "test",
            )
        rendered = " ".join(str(value) for value in warning.call_args.args)
        self.assertNotIn("secret-value-must-not-log", rendered)

    def test_environment_example_names_all_required_variables_without_values(self):
        source = (ROOT / ".env.example").read_text(encoding="utf-8")
        for name in google_seo.GOOGLE_REQUIRED_ENV_VARS:
            self.assertIn(f"{name}=", source)
        self.assertNotIn("client-secret.example", source)


if __name__ == "__main__":
    unittest.main()
