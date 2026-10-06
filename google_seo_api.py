"""Authenticated same-origin routes for the Google SEO OAuth handshake."""

from __future__ import annotations

import os
from urllib.parse import urlencode

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import RedirectResponse

import google_seo
import os_accounts
import sc_auth


SEO_RETURN_PATH = "/"
SEO_RETURN_PAGE = "seo"


class GoogleSEOAccessError(RuntimeError):
    pass


def _redirect(result, *, status_code=303):
    query = urlencode({"page": SEO_RETURN_PAGE, "google_oauth": str(result or "attention")})
    return RedirectResponse(
        f"{SEO_RETURN_PATH}?{query}",
        status_code=status_code,
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


def _session_version(value):
    try:
        return max(1, int(value or 1))
    except (TypeError, ValueError):
        return 1


def _request_admin(request: Request):
    token = str(request.cookies.get(sc_auth.AUTH_COOKIE_NAME) or "")
    password = sc_auth.DEFAULT_APP_PASSWORD
    extra_secret = str(os.getenv("SPORTS_CAVE_AUTH_SECRET") or "").strip()
    valid, _reason, payload = sc_auth.validate_user_auth_token(
        token,
        password=password,
        extra_secret=extra_secret,
    )
    if valid:
        try:
            user = os_accounts.DEFAULT_STORE.get_user(payload.get("sub"))
        except Exception:
            user = {}
        if (
            os_accounts.is_admin(user)
            and str(payload.get("sub") or "") == str(user.get("id") or "")
            and _session_version(payload.get("sv"))
            == _session_version(user.get("session_version"))
        ):
            return user

    legacy_valid, _legacy_reason = sc_auth.validate_auth_token(
        token,
        password=password,
        extra_secret=extra_secret,
    )
    if legacy_valid:
        try:
            account_status = os_accounts.prepare_account_system()
        except Exception:
            account_status = {"available": False, "admin": {}}
        established_admin = account_status.get("admin") or {}
        if account_status.get("available") and established_admin:
            raise GoogleSEOAccessError("Administrator access is required.")
        if os_accounts.is_admin(established_admin):
            return established_admin
        return {
            "id": "legacy-master-admin",
            "username": "admin",
            "display_name": "Sports Cave Admin",
            "email": "",
            "role": os_accounts.ROLE_ADMIN,
            "is_active": True,
            "session_version": 1,
            "page_permissions": [],
        }
    raise GoogleSEOAccessError("Administrator access is required.")


def _start_connection(request):
    user = _request_admin(request)
    config = google_seo.load_config()
    return google_seo.create_oauth_request(
        google_seo.default_store(),
        user,
        config,
        return_page=SEO_RETURN_PAGE,
    )


async def google_oauth_connect(request: Request):
    try:
        authorization_url = await run_in_threadpool(_start_connection, request)
    except GoogleSEOAccessError:
        return _redirect("access_denied")
    except google_seo.GoogleConfigurationError:
        return _redirect("configuration_required")
    except (google_seo.GoogleSEOError, PermissionError):
        return _redirect("attention")
    return RedirectResponse(
        authorization_url,
        status_code=302,
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


def _complete_callback(request):
    user = _request_admin(request)
    store = google_seo.default_store()
    state_record = google_seo.consume_oauth_state(
        store,
        request.query_params.get("state", ""),
        user,
    )
    if str(state_record.get("return_page") or "") != SEO_RETURN_PAGE:
        raise google_seo.GoogleOAuthStateError(
            "Google connection could not be verified. Please try again.",
            code="state_return_mismatch",
            stage="oauth_callback",
        )
    if request.query_params.get("error"):
        raise google_seo.GoogleSEOError(
            "Google access was not approved. No connection changes were made.",
            code="authorization_denied",
            stage="oauth_callback",
        )
    config = google_seo.load_config()
    google_seo.complete_authorization(
        store,
        user,
        request.query_params.get("code", ""),
        config,
    )


async def google_oauth_callback(request: Request):
    try:
        await run_in_threadpool(_complete_callback, request)
    except GoogleSEOAccessError:
        return _redirect("access_denied")
    except google_seo.GoogleConfigurationError:
        return _redirect("configuration_required")
    except google_seo.GoogleOAuthStateError:
        return _redirect("state_invalid")
    except google_seo.GoogleSEOError as error:
        google_seo._log_safe_error(error, "oauth_callback")
        result = "denied" if error.code == "authorization_denied" else "attention"
        return _redirect(result)
    except PermissionError:
        return _redirect("access_denied")
    except Exception:
        return _redirect("attention")
    return _redirect("connected")


GOOGLE_SEO_ROUTE_HANDLERS = (
    (google_seo.GOOGLE_OAUTH_CONNECT_PATH, google_oauth_connect, ("GET",)),
    (google_seo.GOOGLE_OAUTH_CALLBACK_PATH, google_oauth_callback, ("GET",)),
)
