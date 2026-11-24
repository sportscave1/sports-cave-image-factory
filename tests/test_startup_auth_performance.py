"""Exercise actual auth functions without importing or launching the business app."""
import ast
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import sc_auth

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "synthetic-auth-key"
USER = dict(id="fixture-user", is_active=True, session_version=2)


def auth(*, token="", user=None, status=None, session=None):
    source = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    names = {"is_app_authenticated", "_auth_payload_matches_user", "_session_version"}
    functions = [n for n in source.body if isinstance(n, ast.FunctionDef) and n.name in names]
    status_read = Mock(return_value=status or dict(available=True, admin={}))
    store = Mock()
    store.get_user.return_value = deepcopy(USER if user is None else user)
    state = dict(session or {})
    namespace = dict(st=SimpleNamespace(session_state=state), sc_auth=sc_auth,
        AUTH_REVALIDATE_SECONDS=30, current_auth_cookie=Mock(return_value=token),
        get_app_password=Mock(return_value=PASSWORD), get_auth_extra_secret=Mock(return_value=""),
        _account_system_status=status_read, os_accounts=SimpleNamespace(DEFAULT_STORE=store,
            account_is_active=lambda u: bool(u.get("is_active"))),
        _set_authenticated_user=Mock(), _clear_authenticated_session_state=Mock(),
        clear_auth_cookie=Mock(), current_os_user=Mock(return_value=USER),
        _refresh_session_account_if_due=Mock(return_value=USER),
        set_activity_actor=Mock(), _activity_actor_for_user=lambda u: u["id"],
        _legacy_admin_account=lambda: dict(id="legacy", legacy=True))
    exec(compile(ast.Module(body=functions, type_ignores=[]), "<actual auth>", "exec"), namespace)
    return namespace


def test_new_anonymous_browser_renders_without_credentials_or_account_discovery():
    ns = auth()
    ns["_account_system_status"].side_effect = AssertionError("Anonymous opening must not query bootstrap")
    assert ns["is_app_authenticated"]() is False
    for name in ("get_app_password", "get_auth_extra_secret", "_set_authenticated_user"):
        ns[name].assert_not_called()
    ns["os_accounts"].DEFAULT_STORE.get_user.assert_not_called()


@pytest.mark.parametrize("token", ["malformed", "bad.signature",
    sc_auth.create_user_auth_token("fixture-user", password="wrong-key"),
    sc_auth.create_user_auth_token("fixture-user", password=PASSWORD, now=1, days=1),
    sc_auth.create_auth_token(password=PASSWORD, now=1, days=1)])
def test_invalid_or_expired_tokens_never_read_bootstrap_or_grant_access(token):
    ns = auth(token=token)
    ns["_account_system_status"].side_effect = AssertionError("Unverified token must not query bootstrap")
    assert ns["is_app_authenticated"]() is False
    ns["_set_authenticated_user"].assert_not_called()
    ns["os_accounts"].DEFAULT_STORE.get_user.assert_not_called()


@pytest.mark.parametrize("user,accepted", [
    (USER, True), ({**USER, "is_active": False}, False),
    ({**USER, "session_version": 3}, False), ({**USER, "id": "other"}, False), ({}, False)])
def test_real_signed_user_token_still_requires_current_active_matching_session(user, accepted):
    token = sc_auth.create_user_auth_token(USER["id"], password=PASSWORD, session_version=2)
    ns = auth(token=token, user=user)
    assert ns["is_app_authenticated"]() is accepted
    ns["os_accounts"].DEFAULT_STORE.get_user.assert_called_once_with(USER["id"])
    ns["_account_system_status"].assert_not_called()
    if accepted:
        ns["_set_authenticated_user"].assert_called_once_with(USER)
    else:
        ns["_set_authenticated_user"].assert_not_called()
        ns["clear_auth_cookie"].assert_called_once()


def test_user_lookup_outage_fails_closed():
    ns = auth(token=sc_auth.create_user_auth_token(USER["id"], password=PASSWORD, session_version=2))
    ns["os_accounts"].DEFAULT_STORE.get_user.side_effect = TimeoutError()
    assert ns["is_app_authenticated"]() is False
    ns["_set_authenticated_user"].assert_not_called()


@pytest.mark.parametrize("available,admin,accepted,setup", [
    (True, {}, True, True), (True, USER, False, False),
    (False, USER, True, False), (False, {}, True, False)])
def test_valid_signed_legacy_token_retains_bootstrap_and_migration_rules(available, admin, accepted, setup):
    ns = auth(token=sc_auth.create_auth_token(password=PASSWORD),
              status=dict(available=available, admin=admin))
    assert ns["is_app_authenticated"]() is accepted
    ns["_account_system_status"].assert_called_once()
    assert bool(ns["st"].session_state.get("sports_cave_admin_setup_required")) is setup
    assert ns["_set_authenticated_user"].called is accepted


@pytest.mark.parametrize("refreshed,accepted", [(USER, True), ({}, False)])
def test_authenticated_session_still_revalidates_current_account(refreshed, accepted):
    ns = auth(session=dict(sports_cave_authenticated=True))
    ns["_refresh_session_account_if_due"].return_value = refreshed
    assert ns["is_app_authenticated"]() is accepted
    ns["_refresh_session_account_if_due"].assert_called_once_with(USER, max_age_seconds=30)
    ns["current_auth_cookie"].assert_not_called()
