import json
import logging
import os
import re
from datetime import date, timedelta

import requests


DEFAULT_META_API_VERSION = "v26.0"
META_BASE_URL = "https://graph.facebook.com"
LOGGER = logging.getLogger(__name__)


class MetaAdsApiError(RuntimeError):
    def __init__(
        self,
        message,
        *,
        status_code=None,
        error_code=None,
        error_subcode=None,
        error_type="",
        fbtrace_id="",
        error_user_title="",
        error_user_msg="",
        request_path="",
    ):
        super().__init__(sanitize_meta_error(message))
        self.status_code = status_code
        self.error_code = error_code
        self.error_subcode = error_subcode
        self.error_type = str(error_type or "")
        self.fbtrace_id = str(fbtrace_id or "")[:160]
        self.error_user_title = sanitize_meta_error(error_user_title)[:500]
        self.error_user_msg = sanitize_meta_error(error_user_msg)[:1000]
        self.request_path = str(request_path or "")


class MetaAdsAmbiguousResultError(MetaAdsApiError):
    """The request may have reached Meta, so callers must reconcile before retrying."""


class MetaPageAuthError(MetaAdsApiError):
    """Safe, classified failure while validating Page-owned Meta operations."""

    def __init__(self, message, *, category, **kwargs):
        super().__init__(message, **kwargs)
        self.category = str(category or "page_auth_unavailable")


FACEBOOK_PAGE_ID_ENV_KEYS = (
    "META_FACEBOOK_PAGE_ID",
    "META_PAGE_ID",
    "FACEBOOK_PAGE_ID",
)
INSTAGRAM_ACTOR_ID_ENV_KEYS = (
    "META_INSTAGRAM_ACTOR_ID",
    "META_INSTAGRAM_ACCOUNT_ID",
    "INSTAGRAM_ACTOR_ID",
    "INSTAGRAM_ACCOUNT_ID",
)
PAGE_ACCESS_TOKEN_ENV_KEY = "META_PAGE_ACCESS_TOKEN"
PAGE_POST_PERMISSION = "pages_manage_posts"
PRODUCT_SET_TEMPLATE_GUIDANCE = (
    "The selected Product Set requires a catalogue Collection creative. "
    "Use object_story_spec.template_data with Meta's supported Collection format before retrying."
)


def _first_env_value(keys):
    for key in keys:
        value = str(os.getenv(key, "")).strip()
        if value:
            return value, key
    return "", ""


def sanitize_meta_error(message, extra_secrets=()):
    cleaned = str(message or "")
    protected_values = [
        str(os.getenv(key, "")).strip()
        for key in ("META_ACCESS_TOKEN", PAGE_ACCESS_TOKEN_ENV_KEY, "META_APP_SECRET")
    ]
    protected_values.extend(str(value or "").strip() for value in extra_secrets)
    for value in protected_values:
        if value and len(value) >= 6:
            cleaned = cleaned.replace(value, "[redacted]")
    cleaned = re.sub(r"access_token=([^&\s]+)", "access_token=[redacted]", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"input_token=([^&\s]+)", "input_token=[redacted]", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"(app_secret\s*[=:]\s*)[^&\s,;]+", r"\1[redacted]", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"(access[_ -]?token\s*[=:]\s*)[^&\s,;]+", r"\1[redacted]", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"(Bearer\s+)[A-Za-z0-9_\-.]+", r"\1[redacted]", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bEAA[A-Za-z0-9_\-]{12,}\b", "[redacted]", cleaned)
    return cleaned


def get_meta_config():
    account_id = str(os.getenv("META_AD_ACCOUNT_ID", "")).strip()
    if account_id and not account_id.startswith("act_"):
        account_id = f"act_{account_id}"
    access_token = str(os.getenv("META_ACCESS_TOKEN", "")).strip()
    page_access_token = str(os.getenv(PAGE_ACCESS_TOKEN_ENV_KEY, "")).strip()
    app_id = str(os.getenv("META_APP_ID", "")).strip()
    app_secret = str(os.getenv("META_APP_SECRET", "")).strip()
    configured_api_version = str(os.getenv("META_API_VERSION", "")).strip()
    api_version = configured_api_version or DEFAULT_META_API_VERSION
    page_id, page_id_env = _first_env_value(FACEBOOK_PAGE_ID_ENV_KEYS)
    instagram_actor_id, instagram_actor_id_env = _first_env_value(INSTAGRAM_ACTOR_ID_ENV_KEYS)
    return {
        "configured": bool(account_id and access_token),
        "ad_account_id": account_id,
        "access_token_present": bool(access_token),
        "app_id_present": bool(app_id),
        "app_secret_present": bool(app_secret),
        "app_id": app_id,
        "app_secret": app_secret,
        "api_version": api_version,
        "api_version_source": "META_API_VERSION" if configured_api_version else "default",
        "access_token": access_token,
        "page_access_token": page_access_token,
        "page_access_token_present": bool(page_access_token),
        "page_id": page_id,
        "page_id_env": page_id_env,
        "instagram_actor_id": instagram_actor_id,
        "instagram_user_id": instagram_actor_id,
        "instagram_actor_id_env": instagram_actor_id_env,
    }


def safe_meta_config_status():
    config = get_meta_config()
    return {
        "configured": config["configured"],
        "ad_account_id_present": bool(config["ad_account_id"]),
        "token_present": config["access_token_present"],
        "page_token_present": config["page_access_token_present"],
        "app_id_present": config["app_id_present"],
        "app_secret_present": config["app_secret_present"],
        "app_id": config["app_id"],
        "api_version": config["api_version"],
        "api_version_source": config["api_version_source"],
        "page_id_present": bool(config["page_id"]),
        "page_id_env": config["page_id_env"],
        "instagram_actor_id_present": bool(config["instagram_actor_id"]),
        "instagram_user_id_present": bool(config["instagram_user_id"]),
        "instagram_actor_id_env": config["instagram_actor_id_env"],
    }


def _raise_for_meta_error(response, *, request_path="", secrets=()):
    if response.ok:
        return
    message = f"Meta API error HTTP {response.status_code}"
    error_code = None
    error_subcode = None
    error_type = ""
    fbtrace_id = ""
    error_user_title = ""
    error_user_msg = ""
    try:
        payload = response.json()
        error = payload.get("error") or {}
        if error.get("message"):
            message = f"{message}: {error.get('message')}"
        error_code = error.get("code")
        error_subcode = error.get("error_subcode")
        error_type = str(error.get("type") or "")
        fbtrace_id = str(error.get("fbtrace_id") or "")[:160]
        error_user_title = sanitize_meta_error(
            error.get("error_user_title") or "",
            extra_secrets=secrets,
        )[:500]
        error_user_msg = sanitize_meta_error(
            error.get("error_user_msg") or "",
            extra_secrets=secrets,
        )[:1000]
        if error_user_title:
            message = f"{message} — {error_user_title}"
        if error_user_msg:
            message = f"{message}: {error_user_msg}"
        if error_code is not None:
            message = f"{message} (code {error_code})"
        if error_subcode is not None:
            message = f"{message} (subcode {error_subcode})"
        if error_code == 100 and error_subcode == 1990065:
            message = f"{message} — {PRODUCT_SET_TEMPLATE_GUIDANCE}"
        if fbtrace_id:
            message = f"{message} (fbtrace_id {fbtrace_id})"
    except Exception:
        pass
    raise MetaAdsApiError(
        sanitize_meta_error(message, extra_secrets=secrets),
        status_code=getattr(response, "status_code", None),
        error_code=error_code,
        error_subcode=error_subcode,
        error_type=error_type,
        fbtrace_id=fbtrace_id,
        error_user_title=error_user_title,
        error_user_msg=error_user_msg,
        request_path=request_path,
    )


def _request(path, params=None, config=None, access_token=None):
    config = config or get_meta_config()
    if not config.get("configured") and access_token is None:
        raise MetaAdsApiError("Meta Ads API is not configured.")
    clean_path = str(path or "").lstrip("/")
    url = f"{META_BASE_URL}/{config['api_version']}/{clean_path}"
    request_params = dict(params or {})
    request_params["access_token"] = (
        config.get("access_token") if access_token is None else str(access_token)
    )
    try:
        response = requests.get(url, params=request_params, timeout=30)
    except requests.RequestException as error:
        raise MetaAdsApiError(sanitize_meta_error("Meta is unavailable. Try again shortly.")) from error
    _raise_for_meta_error(
        response,
        request_path=clean_path,
        secrets=(request_params.get("access_token"), request_params.get("input_token")),
    )
    return response.json()


def _post(path, data=None, files=None, config=None, access_token=None):
    config = config or get_meta_config()
    if not config.get("configured") and access_token is None:
        raise MetaAdsApiError("Meta Ads API is not configured.")
    clean_path = str(path or "").lstrip("/")
    url = f"{META_BASE_URL}/{config['api_version']}/{clean_path}"
    request_data = dict(data or {})
    request_data["access_token"] = (
        config.get("access_token") if access_token is None else str(access_token)
    )
    try:
        response = requests.post(url, data=request_data, files=files, timeout=45)
    except (requests.Timeout, requests.ConnectionError) as error:
        raise MetaAdsAmbiguousResultError(
            "Meta did not confirm the result. Sports Cave OS will reconcile it before any retry."
        ) from error
    except requests.RequestException as error:
        raise MetaAdsApiError("The Meta request could not be sent.") from error
    if response.status_code >= 500:
        raise MetaAdsAmbiguousResultError(
            "Meta did not confirm the result. Sports Cave OS will reconcile it before any retry."
        )
    _raise_for_meta_error(
        response,
        request_path=clean_path,
        secrets=(request_data.get("access_token"),),
    )
    try:
        return response.json()
    except ValueError as error:
        raise MetaAdsAmbiguousResultError(
            "Meta returned an unreadable result. Sports Cave OS will reconcile it before any retry."
        ) from error


def _get_next_page(url):
    try:
        response = requests.get(url, timeout=30)
    except requests.RequestException as error:
        raise MetaAdsApiError("Meta is unavailable. Try again shortly.") from error
    _raise_for_meta_error(response, request_path="pagination")
    return response.json()


def _paged_get(path, params=None, config=None, max_pages=25, access_token=None):
    page_count = 0
    rows = []
    payload = _request(path, params=params, config=config, access_token=access_token)
    while True:
        page_count += 1
        rows.extend(payload.get("data") or [])
        next_url = ((payload.get("paging") or {}).get("next") or "").strip()
        if not next_url or page_count >= max_pages:
            break
        payload = _get_next_page(next_url)
    return {"rows": rows, "page_count": page_count}


def test_meta_connection(config=None):
    account = fetch_meta_account(config=config)
    return {
        "connected": True,
        "account_id": account.get("account_id") or account.get("id"),
        "name": account.get("name"),
        "currency": account.get("currency"),
        "timezone_name": account.get("timezone_name"),
    }


def fetch_meta_account(config=None):
    config = config or get_meta_config()
    return _request(
        config["ad_account_id"],
        params={"fields": "account_id,name,currency,timezone_name,business{id,name}"},
        config=config,
    )


def fetch_meta_token_identity(config=None):
    return _request(
        "me",
        params={"fields": "id,name"},
        config=config or get_meta_config(),
    )


def fetch_meta_token_debug(config=None):
    """Read safe token metadata using the already-configured Meta app credentials."""
    config = config or get_meta_config()
    app_id = str(config.get("app_id") or "").strip()
    app_secret = str(config.get("app_secret") or "").strip()
    if not app_id or not app_secret:
        raise MetaAdsApiError("Meta app credentials are not configured for token inspection.")
    payload = _request(
        "debug_token",
        params={"input_token": str(config.get("access_token") or "")},
        config=config,
        access_token=f"{app_id}|{app_secret}",
    )
    return dict(payload.get("data") or {})


def fetch_meta_campaigns(config=None):
    config = config or get_meta_config()
    return _paged_get(
        f"{config['ad_account_id']}/campaigns",
        params={
            "fields": "id,name,status,effective_status,objective,created_time,updated_time",
            "limit": 100,
        },
        config=config,
    )


def fetch_meta_adsets(config=None):
    config = config or get_meta_config()
    return _paged_get(
        f"{config['ad_account_id']}/adsets",
        params={
            "fields": (
                "id,name,status,effective_status,campaign_id,optimization_goal,billing_event,"
                "daily_budget,lifetime_budget,created_time,updated_time"
            ),
            "limit": 100,
        },
        config=config,
    )


def fetch_meta_permissions(config=None, access_token=None):
    config = config or get_meta_config()
    payload = _request(
        "me/permissions",
        params={"fields": "permission,status"},
        config=config,
        access_token=access_token,
    )
    return tuple(
        str(row.get("permission") or "")
        for row in payload.get("data") or []
        if str(row.get("status") or "").casefold() == "granted"
    )


def fetch_meta_page_token_identity(config=None):
    """Resolve the identity represented by the configured Page token."""
    config = config or get_meta_config()
    page_token = str(config.get("page_access_token") or "").strip()
    if not page_token:
        raise MetaPageAuthError(
            "META_PAGE_ACCESS_TOKEN is not configured.",
            category="missing_page_token",
        )
    return _request(
        "me",
        params={"fields": "id,name"},
        config=config,
        access_token=page_token,
    )


def fetch_meta_page_token_debug(config=None):
    """Read safe Page-token metadata without returning or logging the token."""
    config = config or get_meta_config()
    app_id = str(config.get("app_id") or "").strip()
    app_secret = str(config.get("app_secret") or "").strip()
    page_token = str(config.get("page_access_token") or "").strip()
    if not app_id or not app_secret:
        raise MetaPageAuthError(
            "Meta app credentials are not configured for Page-token inspection.",
            category="page_auth_unavailable",
        )
    if not page_token:
        raise MetaPageAuthError(
            "META_PAGE_ACCESS_TOKEN is not configured.",
            category="missing_page_token",
        )
    payload = _request(
        "debug_token",
        params={"input_token": page_token},
        config=config,
        access_token=f"{app_id}|{app_secret}",
    )
    return dict(payload.get("data") or {})


def _classify_meta_error(stage, error):
    safe_message = sanitize_meta_error(error)
    lowered = safe_message.casefold()
    error_code = getattr(error, "error_code", None)
    error_subcode = getattr(error, "error_subcode", None)
    if "version" in lowered and any(
        term in lowered for term in ("unsupported", "deprecated", "no longer", "invalid")
    ):
        return {
            "category": "api_version_unsupported",
            "summary": "Meta unavailable — API version unsupported.",
            "guidance": "Use the app's current central Graph API version setting.",
        }
    if str(error_code) == "200" and "api access blocked" in lowered:
        return {
            "category": "api_access_blocked",
            "summary": "Meta unavailable — Meta has blocked API access for this token/app.",
            "guidance": (
                "This is an app/business/token access block before campaign data can be read; "
                "verify the token's app and the app/System User/ad-account Business assignments."
            ),
        }
    if str(error_code) == "190":
        expired = str(error_subcode) == "463" or "expired" in lowered
        return {
            "category": "expired_token" if expired else "invalid_token",
            "summary": (
                "Meta unavailable — access token expired."
                if expired
                else "Meta unavailable — access token is invalid."
            ),
            "guidance": (
                "Verify the existing system-user token in Meta's Access Token Debugger and Render."
            ),
        }
    if stage in {"ad_account", "campaigns"} and (
        "unsupported get request" in lowered
        or "object with id" in lowered
        or "does not exist" in lowered
    ):
        return {
            "category": "ad_account_not_found_or_unassigned",
            "summary": "Meta unavailable — configured ad account is unavailable to this token.",
            "guidance": (
                "Verify META_AD_ACCOUNT_ID and assign that ad account to the System User in "
                "the same Business Portfolio."
            ),
        }
    if stage in {"ad_account", "campaigns"} and (
        str(error_code) in {"10", "200"}
        or "permission" in lowered
        or "access denied" in lowered
    ):
        return {
            "category": "ad_account_access_denied",
            "summary": "Meta unavailable — ad account access denied.",
            "guidance": (
                "Verify the System User has the configured ad account assigned with permission "
                "to manage campaigns."
            ),
        }
    if stage == "token_identity":
        return {
            "category": "token_identity_unavailable",
            "summary": "Meta unavailable — token identity read failed.",
            "guidance": "The /me result is informational when ad-account reads succeed.",
        }
    if stage == "ad_account":
        return {
            "category": "ad_account_read_failed",
            "summary": "Meta unavailable — ad account read failed.",
            "guidance": "Verify the configured account ID and its System User assignment.",
        }
    if stage == "campaigns":
        return {
            "category": "campaign_read_failed",
            "summary": "Meta unavailable — campaign read failed.",
            "guidance": "Verify the token can read campaigns in the configured ad account.",
        }
    return {
        "category": "connection_check_failed",
        "summary": "Meta unavailable — connection check failed.",
        "guidance": "Review the sanitized Meta response and endpoint below.",
    }


def _failed_connection_check(stage, label, endpoint, error):
    safe_message = sanitize_meta_error(error)
    classification = _classify_meta_error(stage, error)
    LOGGER.warning(
        "Meta Posting read-only check failed at %s (%s), category=%s: %s",
        stage,
        endpoint,
        classification["category"],
        safe_message,
    )
    return {
        "label": label,
        "status": "failed",
        "endpoint": endpoint,
        "message": safe_message,
        "http_status": getattr(error, "status_code", None),
        "error_code": getattr(error, "error_code", None),
        "error_subcode": getattr(error, "error_subcode", None),
        "error_type": str(getattr(error, "error_type", "") or ""),
        "fbtrace_id": str(getattr(error, "fbtrace_id", "") or "")[:160],
        "error_user_title": str(getattr(error, "error_user_title", "") or "")[:500],
        "error_user_msg": str(getattr(error, "error_user_msg", "") or "")[:1000],
        **classification,
    }


def _token_debug_check(config, api_version):
    app_id = str(config.get("app_id") or "").strip()
    app_secret = str(config.get("app_secret") or "").strip()
    if not app_id or not app_secret:
        return {
            "label": "Token/app metadata",
            "status": "unverified",
            "endpoint": f"/{api_version}/debug_token",
            "message": "unavailable — META_APP_ID and META_APP_SECRET are not both configured",
        }
    try:
        metadata = fetch_meta_token_debug(config=config)
    except MetaAdsApiError as error:
        failure = _failed_connection_check(
            "token_metadata",
            "Token/app metadata",
            f"/{api_version}/debug_token",
            error,
        )
        failure["diagnostic_error_category"] = failure.get("category")
        failure["category"] = "token_metadata_unavailable"
        failure["status"] = "unverified"
        failure["diagnostic"] = failure.get("message")
        failure["message"] = "token metadata inspection unavailable"
        failure["summary"] = "Token/app metadata unavailable."
        failure["guidance"] = (
            "Verify META_APP_ID and META_APP_SECRET if the ad-account reads otherwise succeed."
        )
        return failure

    token_app_id = str(metadata.get("app_id") or "")
    token_type = str(metadata.get("type") or "unknown")
    is_valid = metadata.get("is_valid") is True
    app_matches = bool(token_app_id and token_app_id == app_id)
    scopes = tuple(sorted({str(value) for value in metadata.get("scopes") or () if value}))
    if not is_valid:
        status = "failed"
        category = "invalid_token"
        message = "token is not valid"
        guidance = "Verify the existing system-user token in Meta's Access Token Debugger and Render."
    elif not app_matches:
        status = "failed"
        category = "token_app_mismatch"
        message = "token belongs to a different Meta app"
        guidance = "Generate the System User token for the META_APP_ID configured by Sports Cave OS."
    else:
        status = "ok"
        category = "token_metadata_confirmed"
        message = f"valid {token_type} token; app matches META_APP_ID"
        guidance = ""
    return {
        "label": "Token/app metadata",
        "status": status,
        "endpoint": f"/{api_version}/debug_token",
        "message": message,
        "category": category,
        "guidance": guidance,
        "token_type": token_type,
        "token_app_id": token_app_id,
        "configured_app_id": app_id,
        "app_matches": app_matches,
        "is_valid": is_valid,
        "scopes": scopes,
    }


def diagnose_meta_posting_connection(config=None):
    """Run independent, read-only Posting checks and return only safe diagnostics."""
    config = config or get_meta_config()
    api_version = str(config.get("api_version") or DEFAULT_META_API_VERSION)
    api_version_source = str(config.get("api_version_source") or "provided config")
    checks = {}
    campaigns = ()
    version_warning = ""
    if api_version_source == "META_API_VERSION" and api_version != DEFAULT_META_API_VERSION:
        version_warning = (
            f"Render META_API_VERSION overrides the application default; change it from "
            f"{api_version} to {DEFAULT_META_API_VERSION}. This stale override does not by itself "
            "prove the cause of an API access block."
        )

    if config.get("configured"):
        checks["configuration"] = {
            "label": "Meta configuration",
            "status": "ok",
            "message": "OK",
        }
    else:
        checks["configuration"] = {
            "label": "Meta configuration",
            "status": "failed",
            "message": "Ad account or token configuration is missing.",
        }
    checks["token_presence"] = {
        "label": "Access token present",
        "status": "ok" if bool(config.get("access_token")) else "failed",
        "message": "yes" if config.get("access_token") else "no",
    }
    app_id = str(config.get("app_id") or "").strip()
    app_secret_present = bool(config.get("app_secret"))
    checks["app_configuration"] = {
        "label": "Meta app configuration",
        "status": "ok" if app_id and app_secret_present else "unverified",
        "message": (
            f"App ID {app_id}; app secret present"
            if app_id and app_secret_present
            else "META_APP_ID and META_APP_SECRET are not both configured"
        ),
    }
    checks["account_configuration"] = {
        "label": "Configured ad account",
        "status": "ok" if bool(config.get("ad_account_id")) else "failed",
        "message": str(config.get("ad_account_id") or "missing"),
    }

    identities_ready = bool(
        config.get("page_id")
        and (config.get("instagram_user_id") or config.get("instagram_actor_id"))
    )
    checks["identity"] = {
        "label": "Identity configuration",
        "status": "ok" if identities_ready else "failed",
        "message": (
            "configured (API access not yet verified)"
            if identities_ready
            else "Facebook Page or Instagram identity is missing."
        ),
    }
    checks["page_identity"] = {
        "label": "Facebook Page identity",
        "status": "ok" if bool(config.get("page_id")) else "failed",
        "message": "configured" if config.get("page_id") else "missing",
    }
    page_token_present = bool(config.get("page_access_token"))
    checks["page_token"] = {
        "label": "Facebook Page access token",
        "status": "ok" if page_token_present else "failed",
        "message": "configured" if page_token_present else "META_PAGE_ACCESS_TOKEN is missing",
        "category": "page_token_present" if page_token_present else "missing_page_token",
    }
    checks["instagram_identity"] = {
        "label": "Instagram identity",
        "status": "ok" if bool(
            config.get("instagram_user_id") or config.get("instagram_actor_id")
        ) else "failed",
        "message": (
            "configured"
            if config.get("instagram_user_id") or config.get("instagram_actor_id")
            else "missing"
        ),
    }

    if not config.get("configured") or not identities_ready:
        summary = (
            "Meta unavailable — base configuration missing."
            if not config.get("configured")
            else "Meta identity configuration required."
        )
        return {
            "connected": False,
            "posting_ready": False,
            "summary": summary,
            "api_version": api_version,
            "api_version_source": api_version_source,
            "default_api_version": DEFAULT_META_API_VERSION,
            "version_warning": version_warning,
            "checks": checks,
            "page_auth_state": "unverified" if page_token_present else "missing",
            "permission_state": "unverified",
            "permissions": (),
            "campaigns": campaigns,
        }

    page_auth_state = "missing"
    if page_token_present:
        try:
            page_auth = MetaPostingClient(config).validate_page_auth()
            page_auth_state = "confirmed"
            checks["page_auth"] = {
                "label": "Facebook Page authentication",
                "status": "ok",
                "message": "Page identity and pages_manage_posts confirmed",
                "category": "page_auth_confirmed",
                "page_id": str(page_auth.get("page_id") or ""),
                "permission": str(page_auth.get("permission") or ""),
            }
        except MetaPageAuthError as error:
            page_auth_state = "failed"
            checks["page_auth"] = {
                "label": "Facebook Page authentication",
                "status": "failed",
                "message": sanitize_meta_error(error),
                "category": str(error.category or "page_auth_unavailable"),
            }
    else:
        checks["page_auth"] = {
            "label": "Facebook Page authentication",
            "status": "failed",
            "message": "META_PAGE_ACCESS_TOKEN is not configured.",
            "category": "missing_page_token",
        }

    checks["token_metadata"] = _token_debug_check(config, api_version)
    read_checks = (
        (
            "token_identity",
            "Token identity",
            f"/{api_version}/me",
            lambda: fetch_meta_token_identity(config=config),
        ),
        (
            "ad_account",
            "Ad account",
            f"/{api_version}/{config['ad_account_id']}",
            lambda: fetch_meta_account(config=config),
        ),
        (
            "campaigns",
            "Campaign read",
            f"/{api_version}/{config['ad_account_id']}/campaigns",
            lambda: fetch_meta_campaigns(config=config),
        ),
    )
    for stage, label, endpoint, loader in read_checks:
        try:
            result = loader()
            if stage == "campaigns":
                campaigns = tuple(dict(row) for row in result.get("rows") or ())
            checks[stage] = {
                "label": label,
                "status": "ok",
                "endpoint": endpoint,
                "message": "OK",
            }
        except MetaAdsApiError as error:
            failure = _failed_connection_check(stage, label, endpoint, error)
            checks[stage] = failure

    permission_endpoint = f"/{api_version}/me/permissions"
    permissions = ()
    permission_state = "unverified"
    try:
        permissions = tuple(fetch_meta_permissions(config=config))
        if "ads_management" in set(permissions):
            permission_state = "confirmed"
            permission_message = "confirmed"
            permission_status = "ok"
        else:
            permission_state = "missing"
            permission_message = "not granted"
            permission_status = "failed"
        checks["permissions"] = {
            "label": "ads_management",
            "status": permission_status,
            "endpoint": permission_endpoint,
            "message": permission_message,
        }
    except MetaAdsApiError as error:
        safe_message = sanitize_meta_error(error)
        LOGGER.warning(
            "Meta Posting optional permission introspection failed at %s: %s",
            permission_endpoint,
            safe_message,
        )
        checks["permissions"] = {
            "label": "ads_management",
            "status": "unverified",
            "endpoint": permission_endpoint,
            "message": "permission introspection unavailable",
            "diagnostic": safe_message,
            "http_status": getattr(error, "status_code", None),
            "error_code": getattr(error, "error_code", None),
            "error_subcode": getattr(error, "error_subcode", None),
            "error_type": str(getattr(error, "error_type", "") or ""),
            "fbtrace_id": str(getattr(error, "fbtrace_id", "") or "")[:160],
        }

    account_ok = checks.get("ad_account", {}).get("status") == "ok"
    campaigns_ok = checks.get("campaigns", {}).get("status") == "ok"
    token_metadata_category = str(checks.get("token_metadata", {}).get("category") or "")
    token_metadata_blocked = token_metadata_category in {"invalid_token", "token_app_mismatch"}
    connected = account_ok and campaigns_ok and not token_metadata_blocked

    if connected and checks.get("token_identity", {}).get("status") == "failed":
        checks["token_identity"]["status"] = "unverified"
        checks["token_identity"]["summary"] = "Token identity introspection unavailable."

    blocking_failures = [
        checks.get(key, {})
        for key in ("ad_account", "campaigns")
        if checks.get(key, {}).get("status") == "failed"
    ]
    access_blocked = any(
        failure.get("category") == "api_access_blocked" for failure in blocking_failures
    )
    if token_metadata_blocked:
        token_check = checks["token_metadata"]
        summary = (
            "Meta unavailable — access token is invalid."
            if token_metadata_category == "invalid_token"
            else "Meta unavailable — token belongs to a different Meta app."
        )
        diagnosis_category = token_metadata_category
        guidance = (str(token_check.get("guidance") or ""),)
    elif access_blocked:
        summary = "Meta unavailable — Meta has blocked API access for this token/app."
        diagnosis_category = "api_access_blocked"
        guidance = (
            "This is an app/business/token access issue rather than a campaign-read failure.",
            (
                "Verify that the token was generated for the configured Meta app and that the app, "
                "System User, and ad account are owned by or shared with the same Business Portfolio."
            ),
            "Check the Meta App Dashboard for app restrictions and Marketing API access.",
        )
    elif blocking_failures:
        first_failure = blocking_failures[0]
        summary = str(first_failure.get("summary") or "Meta unavailable")
        diagnosis_category = str(first_failure.get("category") or "connection_check_failed")
        guidance = (str(first_failure.get("guidance") or ""),)
    else:
        summary = "Meta connected"
        diagnosis_category = "connected"
        guidance = ()
    if connected and permission_state == "missing":
        summary = "Meta posting permission required"
        diagnosis_category = "ads_management_missing"
        guidance = ("Generate the System User token with ads_management for this app.",)
    elif connected and page_auth_state != "confirmed":
        page_check = checks.get("page_auth") or checks.get("page_token") or {}
        summary = "Meta Page authentication required"
        diagnosis_category = str(page_check.get("category") or "page_auth_unavailable")
        guidance = (
            str(page_check.get("message") or "Configure a valid Facebook Page access token."),
        )
    return {
        "connected": connected,
        "posting_ready": (
            connected and permission_state != "missing" and page_auth_state == "confirmed"
        ),
        "summary": summary,
        "diagnosis_category": diagnosis_category,
        "guidance": tuple(value for value in guidance if value),
        "api_version": api_version,
        "api_version_source": api_version_source,
        "default_api_version": DEFAULT_META_API_VERSION,
        "version_warning": version_warning,
        "checks": checks,
        "page_auth_state": page_auth_state,
        "permission_state": permission_state,
        "permissions": permissions,
        "campaigns": campaigns,
    }


def fetch_meta_campaign_adsets(campaign_id, config=None):
    config = config or get_meta_config()
    return _paged_get(
        f"{str(campaign_id or '').strip()}/adsets",
        params={
            "fields": "id,name,status,effective_status,campaign_id,account_id,created_time",
            "limit": 100,
        },
        config=config,
    )


class MetaPostingClient:
    """Paused-only Marketing API client used by Ads > Posting.

    Read methods are deliberately separate from write methods so page rendering can
    load selectors and diagnostics without creating or mutating Meta objects.
    """

    def __init__(self, config=None):
        self.config = config or get_meta_config()

    @property
    def ad_account_id(self):
        return str(self.config.get("ad_account_id") or "")

    @property
    def page_id(self):
        return str(self.config.get("page_id") or "")

    @property
    def page_access_token(self):
        return str(self.config.get("page_access_token") or "")

    @property
    def instagram_actor_id(self):
        return self.instagram_user_id

    @property
    def instagram_user_id(self):
        return str(
            self.config.get("instagram_user_id")
            or self.config.get("instagram_actor_id")
            or ""
        )

    def permissions(self):
        return fetch_meta_permissions(config=self.config)

    def validate_page_auth(self):
        """Validate Page identity and publishing permission before any Meta write."""
        if not self.page_id:
            raise MetaPageAuthError(
                "Sports Cave Facebook Page identity is not configured.",
                category="missing_page_id",
            )
        if not self.page_access_token:
            raise MetaPageAuthError(
                "META_PAGE_ACCESS_TOKEN is not configured.",
                category="missing_page_token",
            )
        try:
            identity = dict(fetch_meta_page_token_identity(config=self.config) or {})
        except MetaPageAuthError:
            raise
        except MetaAdsApiError as error:
            category = (
                "invalid_page_token"
                if str(getattr(error, "error_code", "")) == "190"
                else "page_auth_unavailable"
            )
            message = (
                "META_PAGE_ACCESS_TOKEN is invalid or expired."
                if category == "invalid_page_token"
                else "The configured Facebook Page token could not be validated."
            )
            raise MetaPageAuthError(message, category=category) from error
        represented_page_id = str(identity.get("id") or "")
        if represented_page_id != self.page_id:
            raise MetaPageAuthError(
                "META_PAGE_ACCESS_TOKEN represents a different Facebook Page.",
                category="page_identity_mismatch",
            )

        metadata = {}
        scopes = set()
        if self.config.get("app_id") and self.config.get("app_secret"):
            try:
                metadata = fetch_meta_page_token_debug(config=self.config)
            except MetaPageAuthError:
                raise
            except MetaAdsApiError as error:
                category = (
                    "invalid_page_token"
                    if str(getattr(error, "error_code", "")) == "190"
                    else "page_auth_unavailable"
                )
                message = (
                    "META_PAGE_ACCESS_TOKEN is invalid or expired."
                    if category == "invalid_page_token"
                    else "The Facebook Page token permissions could not be validated."
                )
                raise MetaPageAuthError(message, category=category) from error
            if metadata.get("is_valid") is not True:
                raise MetaPageAuthError(
                    "META_PAGE_ACCESS_TOKEN is invalid or expired.",
                    category="invalid_page_token",
                )
            token_app_id = str(metadata.get("app_id") or "")
            if token_app_id and token_app_id != str(self.config.get("app_id") or ""):
                raise MetaPageAuthError(
                    "META_PAGE_ACCESS_TOKEN belongs to a different Meta app.",
                    category="page_token_app_mismatch",
                )
            token_type = str(metadata.get("type") or "").strip().upper()
            if token_type and token_type != "PAGE":
                raise MetaPageAuthError(
                    "META_PAGE_ACCESS_TOKEN must be a Facebook Page access token.",
                    category="wrong_page_token_type",
                )
            scopes = {
                str(value or "").strip()
                for value in metadata.get("scopes") or ()
                if str(value or "").strip()
            }
            scopes.update(
                str(scope.get("scope") or scope.get("permission") or "").strip()
                for scope in metadata.get("granular_scopes") or ()
                if str(scope.get("scope") or scope.get("permission") or "").strip()
            )
        else:
            try:
                scopes = set(
                    fetch_meta_permissions(
                        config=self.config,
                        access_token=self.page_access_token,
                    )
                )
            except MetaAdsApiError as error:
                raise MetaPageAuthError(
                    "The Facebook Page token permissions could not be validated.",
                    category="page_auth_unavailable",
                ) from error

        if PAGE_POST_PERMISSION not in scopes:
            raise MetaPageAuthError(
                "The Facebook Page token lacks pages_manage_posts for Page-owned content.",
                category="page_permission_missing",
            )
        target_ids = set()
        for scope in metadata.get("granular_scopes") or ():
            if str(scope.get("scope") or scope.get("permission") or "") != PAGE_POST_PERMISSION:
                continue
            target_ids.update(
                str(value or "").strip()
                for value in scope.get("target_ids") or ()
                if str(value or "").strip()
            )
        if target_ids and self.page_id not in target_ids:
            raise MetaPageAuthError(
                "The Facebook Page token is not assigned the required content task for the configured Page.",
                category="page_task_missing",
            )
        return {
            "ready": True,
            "page_id": represented_page_id,
            "page_name": str(identity.get("name") or ""),
            "permission": PAGE_POST_PERMISSION,
            "token_type": str(metadata.get("type") or "Page"),
        }

    def account(self):
        return fetch_meta_account(config=self.config)

    def page(self):
        return _request(
            self.page_id,
            params={"fields": "id,name"},
            config=self.config,
        )

    def instagram_account(self):
        return _request(
            self.instagram_user_id,
            params={"fields": "id,username,name"},
            config=self.config,
        )

    def campaigns(self):
        return tuple(fetch_meta_campaigns(config=self.config).get("rows") or ())

    def existing_ad_names(self):
        return tuple(
            str(row.get("name") or "")
            for row in fetch_meta_ads(config=self.config).get("rows") or ()
            if str(row.get("name") or "").strip()
        )

    def campaign_adsets(self, campaign_id):
        return tuple(
            fetch_meta_campaign_adsets(campaign_id, config=self.config).get("rows") or ()
        )

    def campaign(self, campaign_id):
        return _request(
            str(campaign_id or ""),
            params={"fields": "id,name,status,effective_status,account_id"},
            config=self.config,
        )

    def catalogs(self, account=None):
        account = dict(self.account() or {}) if account is None else dict(account or {})
        business_id = str((account.get("business") or {}).get("id") or "")
        rows = []
        errors = []
        successful_edges = 0

        def load_edge(parent_id, edge):
            try:
                return _paged_get(
                    f"{parent_id}/{edge}",
                    params={"fields": "id,name,vertical,product_count", "limit": 100},
                    config=self.config,
                ).get("rows") or ()
            except MetaAdsApiError:
                return _paged_get(
                    f"{parent_id}/{edge}",
                    params={"fields": "id,name,vertical", "limit": 100},
                    config=self.config,
                ).get("rows") or ()

        if business_id:
            for edge in ("owned_product_catalogs", "client_product_catalogs"):
                try:
                    rows.extend(load_edge(business_id, edge))
                    successful_edges += 1
                except MetaAdsApiError as error:
                    errors.append(error)
                    LOGGER.info("Optional Meta catalog edge unavailable: %s", edge)
        if self.page_id:
            try:
                rows.extend(load_edge(self.page_id, "product_catalogs"))
                successful_edges += 1
            except MetaAdsApiError as error:
                errors.append(error)
                LOGGER.info("Optional Page catalog edge unavailable")
        if not rows and errors and not successful_edges:
            raise errors[0]
        return tuple({str(row.get("id")): dict(row) for row in rows if row.get("id")}.values())

    def product_sets(self, catalog_id):
        return tuple(
            _paged_get(
                f"{str(catalog_id or '').strip()}/product_sets",
                params={"fields": "id,name,product_catalog{id,name},filter", "limit": 100},
                config=self.config,
            ).get("rows")
            or ()
        )

    def pixels(self):
        return tuple(
            _paged_get(
                f"{self.ad_account_id}/adspixels",
                params={"fields": "id,name,last_fired_time", "limit": 100},
                config=self.config,
            ).get("rows")
            or ()
        )

    def saved_audiences(self):
        return tuple(
            _paged_get(
                f"{self.ad_account_id}/saved_audiences",
                params={"fields": "id,name,targeting", "limit": 100},
                config=self.config,
            ).get("rows")
            or ()
        )

    def custom_audiences(self):
        return tuple(
            _paged_get(
                f"{self.ad_account_id}/customaudiences",
                params={
                    "fields": "id,name,subtype,lookalike_spec,operation_status,delivery_status",
                    "limit": 100,
                },
                config=self.config,
            ).get("rows")
            or ()
        )

    def reference_campaigns(self):
        return tuple(
            _paged_get(
                f"{self.ad_account_id}/campaigns",
                params={
                    "fields": (
                        "id,name,status,effective_status,objective,promoted_object,"
                        "created_time,updated_time"
                    ),
                    "limit": 100,
                },
                config=self.config,
            ).get("rows")
            or ()
        )

    def reference_adsets(self):
        return tuple(
            _paged_get(
                f"{self.ad_account_id}/adsets",
                params={
                    "fields": (
                        "id,name,status,effective_status,campaign_id,optimization_goal,"
                        "promoted_object,campaign{objective}"
                    ),
                    "limit": 100,
                },
                config=self.config,
            ).get("rows")
            or ()
        )

    def reference_data(self):
        warnings = []
        try:
            account = dict(self.account() or {})
        except MetaAdsApiError:
            account = {}
            warnings.append("Meta account details are temporarily unavailable.")
        try:
            catalogs = self.catalogs(account=account)
            catalog_error = {}
        except MetaAdsApiError as error:
            catalogs = ()
            catalog_error = {
                "endpoint": str(error.request_path or "catalog discovery"),
                "http_status": error.status_code,
                "error_code": error.error_code,
                "error_type": str(error.error_type or ""),
                "message": sanitize_meta_error(error),
            }
            warnings.append(
                "Catalog discovery failed at "
                f"{catalog_error['endpoint']}"
                + (f" (Meta code {catalog_error['error_code']})" if catalog_error["error_code"] else "")
                + "."
            )
        try:
            pixels = self.pixels()
        except MetaAdsApiError:
            pixels = ()
            warnings.append("Dataset discovery is unavailable to this token.")
        try:
            saved = self.saved_audiences()
        except MetaAdsApiError:
            saved = ()
            warnings.append("Saved audiences are unavailable to this token.")
        try:
            custom = self.custom_audiences()
        except MetaAdsApiError:
            custom = ()
            warnings.append("Custom audiences are unavailable to this token.")
        try:
            page = dict(self.page() or {})
        except MetaAdsApiError:
            page = {}
            warnings.append("Facebook Page identity could not be refreshed.")
        try:
            instagram = dict(self.instagram_account() or {})
        except MetaAdsApiError:
            instagram = {}
            warnings.append("Instagram identity could not be refreshed.")
        return {
            "account": account,
            "page": page,
            "instagram": instagram,
            "catalogs": tuple(dict(row) for row in catalogs),
            "catalog_error": catalog_error,
            "pixels": tuple(dict(row) for row in pixels),
            "saved_audiences": tuple(dict(row) for row in saved),
            "custom_audiences": tuple(dict(row) for row in custom),
            "warnings": tuple(warnings),
        }

    @staticmethod
    def _graph_data(payload, *, json_fields=()):
        data = {}
        for key, value in dict(payload or {}).items():
            if value is None:
                continue
            data[key] = json.dumps(value) if key in set(json_fields) else value
        return data

    def create_campaign(self, payload):
        result = _post(
            f"{self.ad_account_id}/campaigns",
            data=self._graph_data(
                payload,
                json_fields=("special_ad_categories", "promoted_object"),
            ),
            config=self.config,
        )
        campaign_id = str(result.get("id") or "")
        if not campaign_id:
            raise MetaAdsApiError("Meta did not return a campaign ID.")
        return campaign_id

    def create_adset(self, payload):
        result = _post(
            f"{self.ad_account_id}/adsets",
            data=self._graph_data(payload, json_fields=("promoted_object", "targeting")),
            config=self.config,
        )
        adset_id = str(result.get("id") or "")
        if not adset_id:
            raise MetaAdsApiError("Meta did not return an ad set ID.")
        return adset_id

    def find_campaigns_by_name(self, name):
        expected = str(name or "")
        return tuple(row for row in self.campaigns() if str(row.get("name") or "") == expected)

    def find_adsets_by_name(self, campaign_id, name):
        expected = str(name or "")
        return tuple(
            row
            for row in self.campaign_adsets(campaign_id)
            if str(row.get("name") or "") == expected
        )

    def upload_page_photo(self, image_bytes, *, filename, content_type):
        payload = _post(
            f"{self.page_id}/photos",
            data={"published": "false", "no_story": "true"},
            files={"source": (str(filename or "ad-image"), bytes(image_bytes), str(content_type))},
            config=self.config,
            access_token=self.page_access_token,
        )
        photo_id = str(payload.get("id") or payload.get("post_id") or "")
        if not photo_id:
            raise MetaAdsApiError("Meta did not return a Page photo ID.")
        return photo_id

    def create_canvas_element(self, element_type, specification):
        element_field = str(element_type or "").strip()
        allowed = {"canvas_photo", "canvas_product_set", "canvas_button", "canvas_footer"}
        if element_field not in allowed:
            raise ValueError("Unsupported Instant Experience element type.")
        payload = _post(
            f"{self.page_id}/canvas_elements",
            data={element_field: json.dumps(dict(specification or {}))},
            config=self.config,
            access_token=self.page_access_token,
        )
        element_id = str(payload.get("id") or "")
        if not element_id:
            raise MetaAdsApiError("Meta did not return an Instant Experience element ID.")
        return element_id

    def canvases(self):
        return tuple(
            _paged_get(
                f"{self.page_id}/canvases",
                params={"fields": "id,name,is_published,update_time", "limit": 100},
                config=self.config,
                access_token=self.page_access_token,
            ).get("rows")
            or ()
        )

    def find_canvases_by_name(self, name):
        expected = str(name or "")
        return tuple(row for row in self.canvases() if str(row.get("name") or "") == expected)

    def create_canvas(self, *, name, body_element_ids):
        payload = _post(
            f"{self.page_id}/canvases",
            data={
                "name": str(name),
                "body_element_ids": json.dumps([str(value) for value in body_element_ids]),
                "is_published": "true",
            },
            config=self.config,
            access_token=self.page_access_token,
        )
        canvas_id = str(payload.get("id") or "")
        if not canvas_id:
            raise MetaAdsApiError("Meta did not return an Instant Experience ID.")
        return canvas_id

    def create_collection_creative(self, payload):
        result = _post(
            f"{self.ad_account_id}/adcreatives",
            data=self._graph_data(
                payload,
                json_fields=("object_story_spec", "contextual_multi_ads", "degrees_of_freedom_spec"),
            ),
            config=self.config,
        )
        creative_id = str(result.get("id") or "")
        if not creative_id:
            raise MetaAdsApiError("Meta did not return a creative ID.")
        return creative_id

    def configured_campaign(self, campaign_id):
        return _request(
            str(campaign_id or ""),
            params={"fields": "id,name,status,configured_status,effective_status,account_id"},
            config=self.config,
        )

    def configured_adset(self, adset_id):
        return _request(
            str(adset_id or ""),
            params={"fields": "id,name,status,configured_status,effective_status,campaign_id,account_id"},
            config=self.config,
        )

    def adset(self, adset_id):
        return _request(
            str(adset_id or ""),
            params={"fields": "id,name,status,effective_status,campaign_id,account_id"},
            config=self.config,
        )

    def upload_image(self, image_bytes, *, filename, content_type):
        payload = _post(
            f"{self.ad_account_id}/adimages",
            files={"filename": (str(filename or "ad-image"), bytes(image_bytes), str(content_type))},
            config=self.config,
        )
        images = payload.get("images") or {}
        image = next(iter(images.values()), {}) if isinstance(images, dict) else {}
        image_hash = str(image.get("hash") or "")
        if not image_hash:
            raise MetaAdsApiError("Meta did not return an image reference.")
        return image_hash

    def creatives(self):
        return tuple(
            _paged_get(
                f"{self.ad_account_id}/adcreatives",
                params={"fields": "id,name", "limit": 100},
                config=self.config,
            ).get("rows")
            or ()
        )

    def find_creative_by_name(self, creative_name):
        expected = str(creative_name or "")
        return next(
            (row for row in self.creatives() if str(row.get("name") or "") == expected),
            None,
        )

    def create_creative(self, *, creative_name, image_hash, primary_text, headline, description, destination_url, cta_type, url_tags):
        link_data = {
            "image_hash": str(image_hash),
            "link": str(destination_url),
            "message": str(primary_text),
            "name": str(headline),
            "call_to_action": {
                "type": str(cta_type),
                "value": {"link": str(destination_url)},
            },
        }
        if str(description or "").strip():
            link_data["description"] = str(description)
        story_spec = {
            "page_id": self.page_id,
            "instagram_user_id": self.instagram_user_id,
            "link_data": link_data,
        }
        payload = _post(
            f"{self.ad_account_id}/adcreatives",
            data={
                "name": str(creative_name),
                "object_story_spec": json.dumps(story_spec),
                "url_tags": str(url_tags or ""),
            },
            config=self.config,
        )
        creative_id = str(payload.get("id") or "")
        if not creative_id:
            raise MetaAdsApiError("Meta did not return a creative ID.")
        return creative_id

    def adset_ads(self, adset_id):
        return tuple(
            _paged_get(
                f"{str(adset_id or '')}/ads",
                params={
                    "fields": "id,name,status,configured_status,effective_status,creative{id}",
                    "limit": 100,
                },
                config=self.config,
            ).get("rows")
            or ()
        )

    def find_ad_by_creative(self, adset_id, creative_id):
        expected = str(creative_id or "")
        return next(
            (
                row
                for row in self.adset_ads(adset_id)
                if str((row.get("creative") or {}).get("id") or "") == expected
            ),
            None,
        )

    def create_paused_ad(self, *, ad_name, adset_id, creative_id):
        payload = _post(
            f"{self.ad_account_id}/ads",
            data={
                "name": str(ad_name),
                "adset_id": str(adset_id),
                "creative": json.dumps({"creative_id": str(creative_id)}),
                "status": "PAUSED",
            },
            config=self.config,
        )
        ad_id = str(payload.get("id") or "")
        if not ad_id:
            raise MetaAdsApiError("Meta did not return an ad ID.")
        return ad_id

    def ad(self, ad_id):
        return _request(
            str(ad_id or ""),
            params={"fields": "id,name,status,configured_status,effective_status,creative{id},adset_id"},
            config=self.config,
        )


def fetch_meta_ads(config=None):
    config = config or get_meta_config()
    params = {
        "fields": (
            "id,name,status,effective_status,campaign_id,adset_id,"
            "creative{id,name,thumbnail_url,effective_object_story_id,object_story_id,"
            "object_story_spec,asset_feed_spec,call_to_action_type,link_url,page_id,"
            "instagram_user_id,image_hash,video_id},created_time,updated_time"
        ),
        "limit": 100,
    }
    try:
        return _paged_get(f"{config['ad_account_id']}/ads", params=params, config=config)
    except MetaAdsApiError:
        fallback_params = {
            "fields": "id,name,status,effective_status,campaign_id,adset_id,creative,created_time,updated_time",
            "limit": 100,
        }
        return _paged_get(f"{config['ad_account_id']}/ads", params=fallback_params, config=config)


def _date_range_for_days(days):
    until = date.today()
    since = until - timedelta(days=max(int(days or 7), 1) - 1)
    return since.isoformat(), until.isoformat()


META_INSIGHT_FIELDS = (
    "date_start,date_stop,account_id,campaign_id,campaign_name,adset_id,adset_name,"
    "ad_id,ad_name,spend,impressions,reach,clicks,inline_link_clicks,ctr,cpc,cpm,"
    "frequency,actions,action_values,purchase_roas"
)


def _insight_params(date_preset=None, since=None, until=None, days=None, breakdowns=None):
    params = {
        "level": "ad",
        "time_increment": 1,
        "fields": META_INSIGHT_FIELDS,
        "limit": 100,
    }
    if breakdowns:
        # Keep breakdown reads separate. Do not add action_breakdowns here; combining
        # action_type with geo/platform breakdowns caused Meta API errors.
        params["breakdowns"] = breakdowns
    if date_preset:
        params["date_preset"] = date_preset
    else:
        if days and not (since and until):
            since, until = _date_range_for_days(days)
        params["time_range"] = json.dumps({"since": since, "until": until})
    return params


def fetch_meta_ad_insights(date_preset=None, since=None, until=None, days=None, config=None):
    config = config or get_meta_config()
    params = _insight_params(date_preset=date_preset, since=since, until=until, days=days)
    return _paged_get(f"{config['ad_account_id']}/insights", params=params, config=config)


def fetch_meta_ad_insights_summary(date_preset=None, since=None, until=None, days=None, config=None):
    """Return one range-total row per ad for the read-only Meta Review page."""
    config = config or get_meta_config()
    params = _insight_params(date_preset=date_preset, since=since, until=until, days=days)
    params.pop("time_increment", None)
    return _paged_get(f"{config['ad_account_id']}/insights", params=params, config=config)


def fetch_meta_ad_insights_country(date_preset=None, since=None, until=None, days=None, config=None):
    config = config or get_meta_config()
    params = _insight_params(
        date_preset=date_preset,
        since=since,
        until=until,
        days=days,
        breakdowns="country",
    )
    return _paged_get(f"{config['ad_account_id']}/insights", params=params, config=config)


def fetch_meta_ad_insights_age_gender(date_preset=None, since=None, until=None, days=None, config=None):
    config = config or get_meta_config()
    params = _insight_params(
        date_preset=date_preset,
        since=since,
        until=until,
        days=days,
        breakdowns="age,gender",
    )
    return _paged_get(f"{config['ad_account_id']}/insights", params=params, config=config)


def fetch_meta_ad_insights_platform(date_preset=None, since=None, until=None, days=None, config=None):
    config = config or get_meta_config()
    params = _insight_params(
        date_preset=date_preset,
        since=since,
        until=until,
        days=days,
        breakdowns="publisher_platform,platform_position",
    )
    return _paged_get(f"{config['ad_account_id']}/insights", params=params, config=config)
