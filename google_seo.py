"""Secure Phase 1 Google Search Console and GA4 connection services."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import secrets
import threading
import time
from urllib.parse import quote, urlencode, urlparse

from cryptography.fernet import Fernet, InvalidToken
import requests

from activity_log import record_activity_log
import os_accounts


GOOGLE_SCOPES = (
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/analytics.readonly",
)
GOOGLE_OAUTH_CONNECT_PATH = "/api/os/google/connect"
GOOGLE_OAUTH_CALLBACK_PATH = "/api/os/google/oauth/callback"
GOOGLE_AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_REVOCATION_ENDPOINT = "https://oauth2.googleapis.com/revoke"
GSC_SITES_ENDPOINT = "https://www.googleapis.com/webmasters/v3/sites"
GA4_ACCOUNT_SUMMARIES_ENDPOINT = (
    "https://analyticsadmin.googleapis.com/v1beta/accountSummaries"
)
GA4_DATA_ENDPOINT = "https://analyticsdata.googleapis.com/v1beta"
GOOGLE_SEO_MIGRATION = "20260813_google_seo_phase1.sql"
GOOGLE_SEO_WORKSPACE_KEY = "sports-cave"
GOOGLE_OAUTH_STATE_SECONDS = 10 * 60
GOOGLE_HTTP_TIMEOUT_SECONDS = 15
GOOGLE_HTTP_RETRIES = 2
GOOGLE_SYNC_LOCK_SECONDS = 5 * 60
GOOGLE_REQUIRED_ENV_VARS = (
    "GOOGLE_OAUTH_CLIENT_ID",
    "GOOGLE_OAUTH_CLIENT_SECRET",
    "GOOGLE_OAUTH_REDIRECT_URI",
    "GOOGLE_TOKEN_ENCRYPTION_KEY",
)
BASE_DIR = Path(__file__).resolve().parent


class GoogleSEOError(RuntimeError):
    def __init__(
        self,
        message,
        *,
        code="google_seo_error",
        stage="google",
        reconnect_required=False,
        status_code=0,
    ):
        super().__init__(str(message or "Google connection could not be completed."))
        self.public_message = str(message or "Google connection could not be completed.")
        self.code = str(code or "google_seo_error")[:100]
        self.stage = str(stage or "google")[:100]
        self.reconnect_required = bool(reconnect_required)
        self.status_code = int(status_code or 0)


class GoogleConfigurationError(GoogleSEOError):
    pass


class GoogleOAuthStateError(GoogleSEOError):
    pass


class GoogleSEOStoreError(GoogleSEOError):
    pass


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(value):
    if not value:
        return ""
    if isinstance(value, (datetime, date)):
        return value.isoformat().replace("+00:00", "Z")
    return str(value)


def configuration_status(environ=None):
    environ = os.environ if environ is None else environ
    missing = [name for name in GOOGLE_REQUIRED_ENV_VARS if not str(environ.get(name) or "").strip()]
    invalid = []
    redirect_uri = str(environ.get("GOOGLE_OAUTH_REDIRECT_URI") or "").strip()
    if redirect_uri:
        parsed = urlparse(redirect_uri)
        local_http = parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}
        if (
            not parsed.netloc
            or not (parsed.scheme == "https" or local_http)
            or parsed.path != GOOGLE_OAUTH_CALLBACK_PATH
            or parsed.params
            or parsed.query
            or parsed.fragment
        ):
            invalid.append("GOOGLE_OAUTH_REDIRECT_URI")
    encryption_key = str(environ.get("GOOGLE_TOKEN_ENCRYPTION_KEY") or "").strip()
    if encryption_key:
        try:
            Fernet(encryption_key.encode("ascii"))
        except (ValueError, TypeError, UnicodeEncodeError):
            invalid.append("GOOGLE_TOKEN_ENCRYPTION_KEY")
    return {
        "ready": not missing and not invalid,
        "missing": tuple(missing),
        "invalid": tuple(invalid),
    }


def load_config(environ=None):
    environ = os.environ if environ is None else environ
    status = configuration_status(environ)
    if not status["ready"]:
        raise GoogleConfigurationError(
            "Google connection configuration is incomplete.",
            code="configuration_required",
            stage="configuration",
        )
    return {
        "client_id": str(environ["GOOGLE_OAUTH_CLIENT_ID"]).strip(),
        "client_secret": str(environ["GOOGLE_OAUTH_CLIENT_SECRET"]).strip(),
        "redirect_uri": str(environ["GOOGLE_OAUTH_REDIRECT_URI"]).strip(),
        "encryption_key": str(environ["GOOGLE_TOKEN_ENCRYPTION_KEY"]).strip(),
    }


def encrypt_refresh_token(refresh_token, encryption_key):
    token = str(refresh_token or "")
    if not token:
        raise GoogleSEOError(
            "Google did not provide offline access. Reconnect Google and approve both services.",
            code="refresh_token_missing",
            stage="token_storage",
            reconnect_required=True,
        )
    try:
        return Fernet(str(encryption_key).encode("ascii")).encrypt(token.encode("utf-8")).decode("ascii")
    except (ValueError, TypeError, UnicodeEncodeError) as error:
        raise GoogleConfigurationError(
            "Google token encryption is not configured correctly.",
            code="encryption_key_invalid",
            stage="token_storage",
        ) from error


def decrypt_refresh_token(encrypted_token, encryption_key):
    try:
        return Fernet(str(encryption_key).encode("ascii")).decrypt(
            str(encrypted_token or "").encode("ascii")
        ).decode("utf-8")
    except (InvalidToken, ValueError, TypeError, UnicodeError) as error:
        raise GoogleSEOError(
            "Google needs to be reconnected.",
            code="refresh_token_unavailable",
            stage="token_storage",
            reconnect_required=True,
        ) from error


def oauth_state_hash(state):
    return hashlib.sha256(str(state or "").encode("utf-8")).hexdigest()


def build_authorization_url(state, config):
    query = urlencode(
        {
            "client_id": config["client_id"],
            "redirect_uri": config["redirect_uri"],
            "response_type": "code",
            "scope": " ".join(GOOGLE_SCOPES),
            "access_type": "offline",
            "include_granted_scopes": "true",
            "enable_granular_consent": "true",
            "prompt": "consent",
            "state": str(state or ""),
        }
    )
    return f"{GOOGLE_AUTHORIZATION_ENDPOINT}?{query}"


def create_oauth_request(store, user, config, *, return_page="seo", now=None):
    require_admin(user)
    state = secrets.token_urlsafe(32)
    created_at = now or utc_now()
    store.store_oauth_state(
        oauth_state_hash(state),
        user_id=str(user.get("id") or ""),
        return_page=return_page,
        expires_at=created_at + timedelta(seconds=GOOGLE_OAUTH_STATE_SECONDS),
    )
    return build_authorization_url(state, config)


def consume_oauth_state(store, state, user, *, now=None):
    require_admin(user)
    if not state:
        raise GoogleOAuthStateError(
            "Google connection could not be verified. Please try again.",
            code="state_missing",
            stage="oauth_callback",
        )
    return store.consume_oauth_state(
        oauth_state_hash(state),
        user_id=str(user.get("id") or ""),
        now=now or utc_now(),
    )


def require_admin(user):
    if not os_accounts.is_admin(user):
        raise PermissionError("Administrator access is required.")
    return user


def _response_json(response, *, stage, reconnect_required=False):
    status_code = int(getattr(response, "status_code", 0) or 0)
    if not 200 <= status_code < 300:
        raise GoogleSEOError(
            "Google could not complete this request. Please try again.",
            code=f"google_http_{status_code or 'error'}",
            stage=stage,
            reconnect_required=reconnect_required or status_code in {400, 401, 403},
            status_code=status_code,
        )
    try:
        payload = response.json()
    except (TypeError, ValueError) as error:
        raise GoogleSEOError(
            "Google returned an unreadable response. Please try again.",
            code="google_response_invalid",
            stage=stage,
            status_code=status_code,
        ) from error
    return payload if isinstance(payload, dict) else {}


def _request_with_retries(call, *, stage):
    last_error = None
    for attempt in range(GOOGLE_HTTP_RETRIES + 1):
        try:
            response = call()
            status_code = int(getattr(response, "status_code", 0) or 0)
            if status_code == 429 or status_code >= 500:
                if attempt < GOOGLE_HTTP_RETRIES:
                    time.sleep(0.15 * (attempt + 1))
                    continue
            return response
        except (requests.Timeout, requests.ConnectionError) as error:
            last_error = error
            if attempt < GOOGLE_HTTP_RETRIES:
                time.sleep(0.15 * (attempt + 1))
                continue
            break
    raise GoogleSEOError(
        "Google is temporarily unavailable. Please try again.",
        code="google_network_error",
        stage=stage,
    ) from last_error


def exchange_authorization_code(code, config, *, request_post=requests.post):
    if not code:
        raise GoogleSEOError(
            "Google did not return an authorisation code.",
            code="authorization_code_missing",
            stage="token_exchange",
        )
    response = _request_with_retries(
        lambda: request_post(
            GOOGLE_TOKEN_ENDPOINT,
            data={
                "code": str(code),
                "client_id": config["client_id"],
                "client_secret": config["client_secret"],
                "redirect_uri": config["redirect_uri"],
                "grant_type": "authorization_code",
            },
            timeout=GOOGLE_HTTP_TIMEOUT_SECONDS,
        ),
        stage="token_exchange",
    )
    return _response_json(response, stage="token_exchange")


def refresh_access_token(refresh_token, config, *, request_post=requests.post):
    response = _request_with_retries(
        lambda: request_post(
            GOOGLE_TOKEN_ENDPOINT,
            data={
                "refresh_token": str(refresh_token),
                "client_id": config["client_id"],
                "client_secret": config["client_secret"],
                "grant_type": "refresh_token",
            },
            timeout=GOOGLE_HTTP_TIMEOUT_SECONDS,
        ),
        stage="token_refresh",
    )
    payload = _response_json(response, stage="token_refresh", reconnect_required=True)
    access_token = str(payload.get("access_token") or "")
    if not access_token:
        raise GoogleSEOError(
            "Google needs to be reconnected.",
            code="access_token_missing",
            stage="token_refresh",
            reconnect_required=True,
        )
    return access_token


def granted_scopes(token_payload):
    raw = token_payload.get("scope") or ""
    if isinstance(raw, (list, tuple)):
        return tuple(str(item) for item in raw if str(item))
    return tuple(part for part in str(raw).split() if part)


def verify_required_scopes(token_payload):
    granted = set(granted_scopes(token_payload))
    missing = [scope for scope in GOOGLE_SCOPES if scope not in granted]
    if missing:
        raise GoogleSEOError(
            "Both Search Console and Analytics read-only access are required.",
            code="required_scopes_missing",
            stage="scope_verification",
            reconnect_required=True,
        )
    return tuple(scope for scope in GOOGLE_SCOPES if scope in granted)


def _bearer_headers(access_token):
    return {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}


def list_gsc_properties(access_token, *, request_get=requests.get):
    response = _request_with_retries(
        lambda: request_get(
            GSC_SITES_ENDPOINT,
            headers=_bearer_headers(access_token),
            timeout=GOOGLE_HTTP_TIMEOUT_SECONDS,
        ),
        stage="gsc_sites_list",
    )
    payload = _response_json(response, stage="gsc_sites_list")
    properties = []
    seen = set()
    for row in payload.get("siteEntry") or []:
        site_url = str((row or {}).get("siteUrl") or "").strip()
        if not site_url or site_url in seen:
            continue
        seen.add(site_url)
        properties.append(
            {
                "id": site_url,
                "name": site_url,
                "permission_level": str((row or {}).get("permissionLevel") or ""),
            }
        )
    return properties


def list_ga4_properties(access_token, *, request_get=requests.get, max_pages=20):
    properties = []
    seen_properties = set()
    seen_tokens = set()
    page_token = ""
    for _page in range(max(1, int(max_pages))):
        params = {"pageSize": 200}
        if page_token:
            params["pageToken"] = page_token
        response = _request_with_retries(
            lambda params=params: request_get(
                GA4_ACCOUNT_SUMMARIES_ENDPOINT,
                headers=_bearer_headers(access_token),
                params=params,
                timeout=GOOGLE_HTTP_TIMEOUT_SECONDS,
            ),
            stage="ga4_properties_list",
        )
        payload = _response_json(response, stage="ga4_properties_list")
        for account in payload.get("accountSummaries") or []:
            account_name = str((account or {}).get("displayName") or "").strip()
            for row in (account or {}).get("propertySummaries") or []:
                property_id = str((row or {}).get("property") or "").strip()
                if not property_id or property_id in seen_properties:
                    continue
                seen_properties.add(property_id)
                properties.append(
                    {
                        "id": property_id,
                        "name": str((row or {}).get("displayName") or property_id),
                        "account_name": account_name,
                    }
                )
        next_token = str(payload.get("nextPageToken") or "")
        if not next_token or next_token in seen_tokens:
            break
        seen_tokens.add(next_token)
        page_token = next_token
    else:
        raise GoogleSEOError(
            "Google Analytics returned too many property pages. Please try again.",
            code="ga4_pagination_limit",
            stage="ga4_properties_list",
        )
    return properties


def latest_gsc_data_date(access_token, site_url, *, request_post=requests.post, today=None):
    today = today or datetime.now(timezone.utc).date()
    endpoint = f"{GSC_SITES_ENDPOINT}/{quote(str(site_url), safe='')}/searchAnalytics/query"
    response = _request_with_retries(
        lambda: request_post(
            endpoint,
            headers={**_bearer_headers(access_token), "Content-Type": "application/json"},
            json={
                "startDate": (today - timedelta(days=30)).isoformat(),
                "endDate": today.isoformat(),
                "dimensions": ["date"],
                "rowLimit": 100,
                "dataState": "final",
            },
            timeout=GOOGLE_HTTP_TIMEOUT_SECONDS,
        ),
        stage="gsc_freshness",
    )
    payload = _response_json(response, stage="gsc_freshness")
    dates = [
        str((row.get("keys") or [""])[0])
        for row in payload.get("rows") or []
        if (row.get("keys") or [""])[0]
    ]
    return max(dates) if dates else ""


def latest_ga4_data_date(access_token, property_id, *, request_post=requests.post):
    clean_id = str(property_id or "").strip()
    if not clean_id.startswith("properties/"):
        clean_id = f"properties/{clean_id}"
    endpoint = f"{GA4_DATA_ENDPOINT}/{clean_id}:runReport"
    response = _request_with_retries(
        lambda: request_post(
            endpoint,
            headers={**_bearer_headers(access_token), "Content-Type": "application/json"},
            json={
                "dateRanges": [{"startDate": "30daysAgo", "endDate": "today"}],
                "dimensions": [{"name": "date"}],
                "metrics": [{"name": "sessions"}],
                "limit": "100",
            },
            timeout=GOOGLE_HTTP_TIMEOUT_SECONDS,
        ),
        stage="ga4_freshness",
    )
    payload = _response_json(response, stage="ga4_freshness")
    dates = []
    for row in payload.get("rows") or []:
        value = str((((row or {}).get("dimensionValues") or [{}])[0]).get("value") or "")
        if len(value) == 8 and value.isdigit():
            dates.append(f"{value[:4]}-{value[4:6]}-{value[6:]}")
    return max(dates) if dates else ""


def _safe_property_list(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            value = []
    return [dict(row) for row in value or [] if isinstance(row, dict)]


def _safe_connection(row):
    row = dict(row or {})
    for field in ("available_gsc_properties", "available_ga4_properties", "granted_scopes"):
        if field == "granted_scopes":
            value = row.get(field)
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except (TypeError, ValueError, json.JSONDecodeError):
                    value = []
            row[field] = list(value or [])
        else:
            row[field] = _safe_property_list(row.get(field))
    for field in (
        "properties_checked_at",
        "last_successful_sync_at",
        "gsc_data_through_date",
        "ga4_data_through_date",
        "last_error_at",
        "connected_at",
        "disconnected_at",
        "created_at",
        "updated_at",
    ):
        row[field] = _iso(row.get(field))
    return row


class PostgresGoogleSEOStore:
    def __init__(self, backend=None):
        self.backend = backend
        self._schema_ready = False
        self._schema_lock = threading.Lock()

    def _backend(self):
        if self.backend is not None:
            return self.backend
        import supabase_backend

        return supabase_backend

    def ensure_schema(self):
        if self._schema_ready:
            return
        with self._schema_lock:
            if self._schema_ready:
                return
            migration = BASE_DIR / "migrations" / GOOGLE_SEO_MIGRATION
            if not migration.is_file():
                raise GoogleSEOStoreError(
                    "Google SEO storage is unavailable.",
                    code="migration_missing",
                    stage="storage",
                )
            try:
                with self._backend().connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute(migration.read_text(encoding="utf-8"))
                    conn.commit()
            except Exception as error:
                raise GoogleSEOStoreError(
                    "Google SEO storage could not be prepared.",
                    code="storage_unavailable",
                    stage="storage",
                ) from error
            self._schema_ready = True

    def get_connection(self):
        self.ensure_schema()
        try:
            with self._backend().connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT workspace_key, owner_user_id, granted_scopes,
                               connection_status, reconnect_required,
                               gsc_site_url, gsc_property_name,
                               ga4_property_id, ga4_property_name,
                               available_gsc_properties, available_ga4_properties,
                               properties_checked_at, last_successful_sync_at,
                               gsc_data_through_date, ga4_data_through_date,
                               last_error_code, last_error_message, last_error_at,
                               connected_at, disconnected_at, created_at, updated_at,
                               encrypted_refresh_token IS NOT NULL AS has_refresh_token
                        FROM seo_google_connections
                        WHERE workspace_key=%s
                        LIMIT 1
                        """,
                        (GOOGLE_SEO_WORKSPACE_KEY,),
                    )
                    row = cur.fetchone() or {}
            return _safe_connection(row)
        except GoogleSEOError:
            raise
        except Exception as error:
            raise GoogleSEOStoreError(
                "Google connection status could not be loaded.",
                code="storage_read_failed",
                stage="storage",
            ) from error

    def get_connection_secret(self):
        self.ensure_schema()
        with self._backend().connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT encrypted_refresh_token, granted_scopes,
                           gsc_site_url, gsc_property_name,
                           ga4_property_id, ga4_property_name,
                           connection_status, reconnect_required
                    FROM seo_google_connections
                    WHERE workspace_key=%s
                    LIMIT 1
                    """,
                    (GOOGLE_SEO_WORKSPACE_KEY,),
                )
                row = cur.fetchone() or {}
        return _safe_connection(row)

    def store_oauth_state(self, state_hash, *, user_id, return_page, expires_at):
        self.ensure_schema()
        with self._backend().connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM seo_google_oauth_states WHERE expires_at < now() OR used_at < now() - interval '1 day'"
                )
                cur.execute(
                    """
                    INSERT INTO seo_google_oauth_states(
                        state_hash, workspace_key, user_id, return_page, expires_at
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        state_hash,
                        GOOGLE_SEO_WORKSPACE_KEY,
                        str(user_id or "")[:200],
                        str(return_page or "seo")[:100],
                        expires_at,
                    ),
                )
            conn.commit()

    def consume_oauth_state(self, state_hash, *, user_id, now):
        self.ensure_schema()
        with self._backend().connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT state_hash, workspace_key, user_id, return_page,
                           expires_at, used_at
                    FROM seo_google_oauth_states
                    WHERE state_hash=%s
                    FOR UPDATE
                    """,
                    (state_hash,),
                )
                row = cur.fetchone() or {}
                if not row:
                    raise GoogleOAuthStateError(
                        "Google connection could not be verified. Please try again.",
                        code="state_invalid",
                        stage="oauth_callback",
                    )
                if row.get("used_at"):
                    raise GoogleOAuthStateError(
                        "This Google connection request has already been used.",
                        code="state_reused",
                        stage="oauth_callback",
                    )
                expires_at = row.get("expires_at")
                if not expires_at or expires_at <= now:
                    raise GoogleOAuthStateError(
                        "This Google connection request has expired. Please try again.",
                        code="state_expired",
                        stage="oauth_callback",
                    )
                if not secrets.compare_digest(str(row.get("user_id") or ""), str(user_id or "")):
                    raise GoogleOAuthStateError(
                        "Google connection could not be verified for this account.",
                        code="state_user_mismatch",
                        stage="oauth_callback",
                    )
                cur.execute(
                    "UPDATE seo_google_oauth_states SET used_at=%s WHERE state_hash=%s",
                    (now, state_hash),
                )
            conn.commit()
        return _safe_connection(row)

    def save_authorization(self, *, user_id, encrypted_refresh_token, scopes):
        self.ensure_schema()
        with self._backend().connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO seo_google_connections(
                        workspace_key, owner_user_id, encrypted_refresh_token,
                        granted_scopes, connection_status, reconnect_required,
                        connected_at, disconnected_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s::jsonb, 'Needs attention', FALSE, now(), NULL, now())
                    ON CONFLICT (workspace_key) DO UPDATE SET
                        owner_user_id=EXCLUDED.owner_user_id,
                        encrypted_refresh_token=EXCLUDED.encrypted_refresh_token,
                        granted_scopes=EXCLUDED.granted_scopes,
                        connection_status='Needs attention',
                        reconnect_required=FALSE,
                        connected_at=COALESCE(seo_google_connections.connected_at, now()),
                        disconnected_at=NULL,
                        last_error_code='',
                        last_error_message='',
                        last_error_at=NULL,
                        updated_at=now()
                    """,
                    (
                        GOOGLE_SEO_WORKSPACE_KEY,
                        str(user_id or "")[:200],
                        encrypted_refresh_token,
                        json.dumps(list(scopes)),
                    ),
                )
            conn.commit()

    def save_discovered_properties(self, gsc_properties, ga4_properties):
        self.ensure_schema()
        with self._backend().connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE seo_google_connections
                    SET available_gsc_properties=%s::jsonb,
                        available_ga4_properties=%s::jsonb,
                        properties_checked_at=now(),
                        connection_status=CASE
                            WHEN gsc_site_url <> '' AND ga4_property_id <> ''
                                THEN 'Connected'
                            ELSE 'Needs attention'
                        END,
                        reconnect_required=FALSE,
                        last_error_code='', last_error_message='', last_error_at=NULL,
                        updated_at=now()
                    WHERE workspace_key=%s
                    """,
                    (
                        json.dumps(list(gsc_properties)),
                        json.dumps(list(ga4_properties)),
                        GOOGLE_SEO_WORKSPACE_KEY,
                    ),
                )
            conn.commit()

    def save_selection(self, *, user_id, gsc_property, ga4_property):
        self.ensure_schema()
        with self._backend().connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE seo_google_connections
                    SET owner_user_id=%s,
                        gsc_site_url=%s, gsc_property_name=%s,
                        ga4_property_id=%s, ga4_property_name=%s,
                        gsc_data_through_date=CASE
                            WHEN gsc_site_url<>%s THEN NULL ELSE gsc_data_through_date
                        END,
                        ga4_data_through_date=CASE
                            WHEN ga4_property_id<>%s THEN NULL ELSE ga4_data_through_date
                        END,
                        last_successful_sync_at=CASE
                            WHEN gsc_site_url<>%s OR ga4_property_id<>%s
                                THEN NULL
                            ELSE last_successful_sync_at
                        END,
                        connection_status='Connected', reconnect_required=FALSE,
                        last_error_code='', last_error_message='', last_error_at=NULL,
                        updated_at=now()
                    WHERE workspace_key=%s
                      AND encrypted_refresh_token IS NOT NULL
                    RETURNING workspace_key
                    """,
                    (
                        str(user_id or "")[:200],
                        gsc_property["id"],
                        gsc_property["name"],
                        ga4_property["id"],
                        ga4_property["name"],
                        gsc_property["id"],
                        ga4_property["id"],
                        gsc_property["id"],
                        ga4_property["id"],
                        GOOGLE_SEO_WORKSPACE_KEY,
                    ),
                )
                if not cur.fetchone():
                    raise GoogleSEOStoreError(
                        "Google must be connected before selecting properties.",
                        code="connection_missing",
                        stage="property_selection",
                    )
            conn.commit()

    def acquire_sync_lock(self, lock_token, *, now=None):
        self.ensure_schema()
        now = now or utc_now()
        stale_before = now - timedelta(seconds=GOOGLE_SYNC_LOCK_SECONDS)
        with self._backend().connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE seo_google_connections
                    SET sync_lock_token=%s, sync_started_at=%s, updated_at=now()
                    WHERE workspace_key=%s
                      AND encrypted_refresh_token IS NOT NULL
                      AND (
                          sync_lock_token=''
                          OR sync_started_at IS NULL
                          OR sync_started_at < %s
                      )
                    RETURNING workspace_key
                    """,
                    (lock_token, now, GOOGLE_SEO_WORKSPACE_KEY, stale_before),
                )
                acquired = bool(cur.fetchone())
            conn.commit()
        return acquired

    def complete_sync(self, lock_token, *, gsc_data_date, ga4_data_date):
        self.ensure_schema()
        with self._backend().connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE seo_google_connections
                    SET connection_status='Connected', reconnect_required=FALSE,
                        last_successful_sync_at=now(),
                        gsc_data_through_date=COALESCE(%s, gsc_data_through_date),
                        ga4_data_through_date=COALESCE(%s, ga4_data_through_date),
                        last_error_code='', last_error_message='', last_error_at=NULL,
                        sync_lock_token='', sync_started_at=NULL, updated_at=now()
                    WHERE workspace_key=%s AND sync_lock_token=%s
                    """,
                    (
                        gsc_data_date or None,
                        ga4_data_date or None,
                        GOOGLE_SEO_WORKSPACE_KEY,
                        lock_token,
                    ),
                )
            conn.commit()

    def record_failure(self, *, code, message, reconnect_required=False, lock_token=""):
        self.ensure_schema()
        params = [
            bool(reconnect_required),
            str(code or "google_error")[:100],
            str(message or "Google needs attention.")[:300],
            GOOGLE_SEO_WORKSPACE_KEY,
        ]
        lock_clause = ""
        if lock_token:
            lock_clause = " AND sync_lock_token=%s"
            params.append(lock_token)
        with self._backend().connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE seo_google_connections
                    SET connection_status='Needs attention',
                        reconnect_required=%s,
                        last_error_code=%s,
                        last_error_message=%s,
                        last_error_at=now(),
                        sync_lock_token='', sync_started_at=NULL,
                        updated_at=now()
                    WHERE workspace_key=%s{lock_clause}
                    """,
                    params,
                )
            conn.commit()

    def disconnect(self, *, user_id):
        self.ensure_schema()
        with self._backend().connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE seo_google_connections
                    SET owner_user_id=%s,
                        encrypted_refresh_token=NULL,
                        granted_scopes='[]'::jsonb,
                        connection_status='Not connected', reconnect_required=FALSE,
                        gsc_site_url='', gsc_property_name='',
                        ga4_property_id='', ga4_property_name='',
                        available_gsc_properties='[]'::jsonb,
                        available_ga4_properties='[]'::jsonb,
                        properties_checked_at=NULL,
                        last_successful_sync_at=NULL,
                        gsc_data_through_date=NULL,
                        ga4_data_through_date=NULL,
                        last_error_code='', last_error_message='', last_error_at=NULL,
                        sync_lock_token='', sync_started_at=NULL,
                        disconnected_at=now(), updated_at=now()
                    WHERE workspace_key=%s
                    """,
                    (str(user_id or "")[:200], GOOGLE_SEO_WORKSPACE_KEY),
                )
            conn.commit()


_DEFAULT_STORE = None


def default_store():
    global _DEFAULT_STORE
    if _DEFAULT_STORE is None:
        _DEFAULT_STORE = PostgresGoogleSEOStore()
    return _DEFAULT_STORE


def _activity_actor(user):
    return str(
        (user or {}).get("display_name")
        or (user or {}).get("username")
        or (user or {}).get("id")
        or "sports_cave_os"
    )[:200]


def _record_activity(action, message, user, *, metadata=None):
    record_activity_log(
        action,
        "SEO / Overview",
        message,
        entity_type="google_seo_connection",
        entity_id=GOOGLE_SEO_WORKSPACE_KEY,
        metadata={
            "actor_id": (user or {}).get("id") or "",
            "actor_email": (user or {}).get("email") or "",
            "actor_role": (user or {}).get("role") or "",
            "actor_timezone": os_accounts.timezone_for_user(user or {}),
            **dict(metadata or {}),
        },
        actor=_activity_actor(user),
    )


def _log_safe_error(error, operation):
    context = {
        "operation": str(operation or "google_seo")[:100],
        "stage": str(getattr(error, "stage", "google"))[:100],
        "error_code": str(getattr(error, "code", "google_seo_error"))[:100],
        "exception_class": error.__class__.__name__[:100],
        "http_status": int(getattr(error, "status_code", 0) or 0),
    }
    logging.warning("Google SEO operation failed: %s", json.dumps(context, sort_keys=True))
    try:
        import supabase_backend

        supabase_backend.log_app_error(
            "google_seo_operation_failed",
            "Google SEO operation failed.",
            context,
        )
    except Exception:
        pass


def complete_authorization(
    store,
    user,
    code,
    config,
    *,
    request_post=requests.post,
    request_get=requests.get,
):
    require_admin(user)
    token_payload = exchange_authorization_code(code, config, request_post=request_post)
    scopes = verify_required_scopes(token_payload)
    access_token = str(token_payload.get("access_token") or "")
    if not access_token:
        raise GoogleSEOError(
            "Google did not provide temporary access. Please reconnect.",
            code="access_token_missing",
            stage="token_exchange",
            reconnect_required=True,
        )
    existing = store.get_connection_secret()
    refresh_token = str(token_payload.get("refresh_token") or "")
    if refresh_token:
        encrypted_refresh_token = encrypt_refresh_token(refresh_token, config["encryption_key"])
    else:
        encrypted_refresh_token = str(existing.get("encrypted_refresh_token") or "")
        decrypt_refresh_token(encrypted_refresh_token, config["encryption_key"])
    store.save_authorization(
        user_id=user.get("id") or "",
        encrypted_refresh_token=encrypted_refresh_token,
        scopes=scopes,
    )
    try:
        gsc_properties = list_gsc_properties(access_token, request_get=request_get)
        ga4_properties = list_ga4_properties(access_token, request_get=request_get)
        store.save_discovered_properties(gsc_properties, ga4_properties)
        selected_gsc = str(existing.get("gsc_site_url") or "")
        selected_ga4 = str(existing.get("ga4_property_id") or "")
        if selected_gsc and selected_gsc not in {row["id"] for row in gsc_properties}:
            raise GoogleSEOError(
                "The selected Search Console property is no longer accessible.",
                code="gsc_property_inaccessible",
                stage="oauth_callback",
            )
        if selected_ga4 and selected_ga4 not in {row["id"] for row in ga4_properties}:
            raise GoogleSEOError(
                "The selected Analytics property is no longer accessible.",
                code="ga4_property_inaccessible",
                stage="oauth_callback",
            )
    except GoogleSEOError as error:
        store.record_failure(
            code=error.code,
            message=error.public_message,
            reconnect_required=error.reconnect_required,
        )
        _log_safe_error(error, "complete_authorization")
        raise
    reconnected = bool(existing.get("encrypted_refresh_token"))
    _record_activity(
        "google_seo_reconnected" if reconnected else "google_seo_connected",
        "Google Search Console and Analytics reconnected"
        if reconnected
        else "Google Search Console and Analytics connected",
        user,
        metadata={
            "gsc_property_count": len(gsc_properties),
            "ga4_property_count": len(ga4_properties),
            "scope_count": len(scopes),
            "reconnected": reconnected,
        },
    )
    return {
        "gsc_properties": gsc_properties,
        "ga4_properties": ga4_properties,
    }


def _access_token_for_connection(store, config, *, request_post=requests.post):
    connection = store.get_connection_secret()
    encrypted = str(connection.get("encrypted_refresh_token") or "")
    refresh_token = decrypt_refresh_token(encrypted, config["encryption_key"])
    return refresh_access_token(refresh_token, config, request_post=request_post), connection


def access_token_for_connection(store, config, *, request_post=requests.post):
    """Return a short-lived access token without exposing the stored refresh token."""
    return _access_token_for_connection(store, config, request_post=request_post)


def refresh_properties(
    store,
    user,
    config,
    *,
    request_post=requests.post,
    request_get=requests.get,
):
    require_admin(user)
    try:
        access_token, connection = _access_token_for_connection(
            store,
            config,
            request_post=request_post,
        )
        gsc_properties = list_gsc_properties(access_token, request_get=request_get)
        ga4_properties = list_ga4_properties(access_token, request_get=request_get)
        store.save_discovered_properties(gsc_properties, ga4_properties)
        selected_gsc = str(connection.get("gsc_site_url") or "")
        selected_ga4 = str(connection.get("ga4_property_id") or "")
        if selected_gsc and selected_gsc not in {row["id"] for row in gsc_properties}:
            raise GoogleSEOError(
                "The selected Search Console property is no longer accessible.",
                code="gsc_property_inaccessible",
                stage="property_refresh",
            )
        if selected_ga4 and selected_ga4 not in {row["id"] for row in ga4_properties}:
            raise GoogleSEOError(
                "The selected Analytics property is no longer accessible.",
                code="ga4_property_inaccessible",
                stage="property_refresh",
            )
        _record_activity(
            "google_seo_properties_refreshed",
            "Google property access refreshed",
            user,
            metadata={
                "gsc_property_count": len(gsc_properties),
                "ga4_property_count": len(ga4_properties),
            },
        )
        return {"ok": True, "gsc_properties": gsc_properties, "ga4_properties": ga4_properties}
    except GoogleSEOError as error:
        store.record_failure(
            code=error.code,
            message=error.public_message,
            reconnect_required=error.reconnect_required,
        )
        _log_safe_error(error, "refresh_properties")
        _record_activity(
            "google_seo_property_refresh_failed",
            "Google property access needs attention",
            user,
            metadata={"error_code": error.code},
        )
        return {"ok": False, "message": error.public_message, "code": error.code}


def save_property_selection(store, user, *, gsc_site_url, ga4_property_id):
    require_admin(user)
    connection = store.get_connection()
    gsc_by_id = {
        str(row.get("id") or ""): row
        for row in connection.get("available_gsc_properties") or []
    }
    ga4_by_id = {
        str(row.get("id") or ""): row
        for row in connection.get("available_ga4_properties") or []
    }
    if gsc_site_url not in gsc_by_id or ga4_property_id not in ga4_by_id:
        raise GoogleSEOError(
            "Select accessible Search Console and Analytics properties.",
            code="property_selection_invalid",
            stage="property_selection",
        )
    store.save_selection(
        user_id=user.get("id") or "",
        gsc_property=gsc_by_id[gsc_site_url],
        ga4_property=ga4_by_id[ga4_property_id],
    )
    _record_activity(
        "google_seo_properties_selected",
        "Google SEO properties selected",
        user,
        metadata={
            "gsc_site_url": gsc_site_url,
            "ga4_property_id": ga4_property_id,
        },
    )
    return True


def sync_now(
    store,
    user,
    config,
    *,
    request_post=requests.post,
    request_get=requests.get,
):
    require_admin(user)
    lock_token = secrets.token_urlsafe(18)
    if not store.acquire_sync_lock(lock_token):
        return {"ok": False, "busy": True, "message": "A Google sync is already running."}
    try:
        access_token, connection = _access_token_for_connection(
            store,
            config,
            request_post=request_post,
        )
        selected_gsc = str(connection.get("gsc_site_url") or "")
        selected_ga4 = str(connection.get("ga4_property_id") or "")
        if not selected_gsc or not selected_ga4:
            raise GoogleSEOError(
                "Select both Google properties before syncing.",
                code="property_selection_required",
                stage="sync",
            )
        gsc_properties = list_gsc_properties(access_token, request_get=request_get)
        ga4_properties = list_ga4_properties(access_token, request_get=request_get)
        store.save_discovered_properties(gsc_properties, ga4_properties)
        if selected_gsc not in {row["id"] for row in gsc_properties}:
            raise GoogleSEOError(
                "The selected Search Console property is no longer accessible.",
                code="gsc_property_inaccessible",
                stage="sync",
            )
        if selected_ga4 not in {row["id"] for row in ga4_properties}:
            raise GoogleSEOError(
                "The selected Analytics property is no longer accessible.",
                code="ga4_property_inaccessible",
                stage="sync",
            )
        gsc_date = latest_gsc_data_date(
            access_token,
            selected_gsc,
            request_post=request_post,
        )
        ga4_date = latest_ga4_data_date(
            access_token,
            selected_ga4,
            request_post=request_post,
        )
        store.complete_sync(
            lock_token,
            gsc_data_date=gsc_date,
            ga4_data_date=ga4_date,
        )
        _record_activity(
            "google_seo_synced",
            "Google SEO connection checked",
            user,
            metadata={"gsc_data_through_date": gsc_date, "ga4_data_through_date": ga4_date},
        )
        return {"ok": True, "gsc_data_through_date": gsc_date, "ga4_data_through_date": ga4_date}
    except GoogleSEOError as error:
        store.record_failure(
            code=error.code,
            message=error.public_message,
            reconnect_required=error.reconnect_required,
            lock_token=lock_token,
        )
        _log_safe_error(error, "sync_now")
        _record_activity(
            "google_seo_sync_failed",
            "Google SEO connection check needs attention",
            user,
            metadata={"error_code": error.code},
        )
        return {"ok": False, "message": error.public_message, "code": error.code}
    except Exception as error:
        safe_error = GoogleSEOError(
            "Google could not be checked right now. The last successful status was preserved.",
            code="sync_unexpected_error",
            stage="sync",
        )
        store.record_failure(
            code=safe_error.code,
            message=safe_error.public_message,
            lock_token=lock_token,
        )
        _log_safe_error(safe_error, "sync_now")
        _record_activity(
            "google_seo_sync_failed",
            "Google SEO connection check needs attention",
            user,
            metadata={"error_code": safe_error.code},
        )
        return {"ok": False, "message": safe_error.public_message, "code": safe_error.code}


def disconnect_google(store, user, config, *, request_post=requests.post):
    require_admin(user)
    secret = store.get_connection_secret()
    encrypted = str(secret.get("encrypted_refresh_token") or "")
    revoked = False
    if encrypted:
        try:
            refresh_token = decrypt_refresh_token(encrypted, config["encryption_key"])
            response = request_post(
                GOOGLE_REVOCATION_ENDPOINT,
                data={"token": refresh_token},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=GOOGLE_HTTP_TIMEOUT_SECONDS,
            )
            revoked = 200 <= int(getattr(response, "status_code", 0) or 0) < 300
        except (GoogleSEOError, requests.Timeout, requests.ConnectionError):
            revoked = False
    store.disconnect(user_id=user.get("id") or "")
    _record_activity(
        "google_seo_disconnected",
        "Google Search Console and Analytics disconnected",
        user,
        metadata={"revocation_confirmed": revoked},
    )
    return {"ok": True, "revocation_confirmed": revoked}


def connection_status_label(config_status, connection, *, service=""):
    if not config_status.get("ready"):
        return "Configuration required"
    if not connection or not connection.get("has_refresh_token"):
        return "Not connected"
    if connection.get("reconnect_required"):
        return "Needs attention"
    if service == "gsc" and not connection.get("gsc_site_url"):
        return "Needs attention"
    if service == "ga4" and not connection.get("ga4_property_id"):
        return "Needs attention"
    return "Connected" if connection.get("connection_status") == "Connected" else "Needs attention"
