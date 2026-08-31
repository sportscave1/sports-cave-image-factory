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
        request_path="",
    ):
        super().__init__(sanitize_meta_error(message))
        self.status_code = status_code
        self.error_code = error_code
        self.error_subcode = error_subcode
        self.error_type = str(error_type or "")
        self.request_path = str(request_path or "")


class MetaAdsAmbiguousResultError(MetaAdsApiError):
    """The request may have reached Meta, so callers must reconcile before retrying."""


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


def _first_env_value(keys):
    for key in keys:
        value = str(os.getenv(key, "")).strip()
        if value:
            return value, key
    return "", ""


def sanitize_meta_error(message):
    cleaned = str(message or "")
    for key in ("META_ACCESS_TOKEN", "META_APP_SECRET"):
        value = str(os.getenv(key, "")).strip()
        if value and len(value) >= 6:
            cleaned = cleaned.replace(value, "[redacted]")
    cleaned = re.sub(r"access_token=([^&\s]+)", "access_token=[redacted]", cleaned, flags=re.IGNORECASE)
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
    configured_api_version = str(os.getenv("META_API_VERSION", "")).strip()
    api_version = configured_api_version or DEFAULT_META_API_VERSION
    page_id, page_id_env = _first_env_value(FACEBOOK_PAGE_ID_ENV_KEYS)
    instagram_actor_id, instagram_actor_id_env = _first_env_value(INSTAGRAM_ACTOR_ID_ENV_KEYS)
    return {
        "configured": bool(account_id and access_token),
        "ad_account_id": account_id,
        "access_token_present": bool(access_token),
        "app_id_present": bool(str(os.getenv("META_APP_ID", "")).strip()),
        "app_secret_present": bool(str(os.getenv("META_APP_SECRET", "")).strip()),
        "api_version": api_version,
        "api_version_source": "META_API_VERSION" if configured_api_version else "default",
        "access_token": access_token,
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
        "app_id_present": config["app_id_present"],
        "app_secret_present": config["app_secret_present"],
        "api_version": config["api_version"],
        "api_version_source": config["api_version_source"],
        "page_id_present": bool(config["page_id"]),
        "page_id_env": config["page_id_env"],
        "instagram_actor_id_present": bool(config["instagram_actor_id"]),
        "instagram_user_id_present": bool(config["instagram_user_id"]),
        "instagram_actor_id_env": config["instagram_actor_id_env"],
    }


def _raise_for_meta_error(response, *, request_path=""):
    if response.ok:
        return
    message = f"Meta API error HTTP {response.status_code}"
    error_code = None
    error_subcode = None
    error_type = ""
    try:
        payload = response.json()
        error = payload.get("error") or {}
        if error.get("message"):
            message = f"{message}: {error.get('message')}"
        error_code = error.get("code")
        error_subcode = error.get("error_subcode")
        error_type = str(error.get("type") or "")
        if error_code is not None:
            message = f"{message} (code {error_code})"
        if error_subcode is not None:
            message = f"{message} (subcode {error_subcode})"
    except Exception:
        pass
    raise MetaAdsApiError(
        message,
        status_code=getattr(response, "status_code", None),
        error_code=error_code,
        error_subcode=error_subcode,
        error_type=error_type,
        request_path=request_path,
    )


def _request(path, params=None, config=None):
    config = config or get_meta_config()
    if not config.get("configured"):
        raise MetaAdsApiError("Meta Ads API is not configured.")
    clean_path = str(path or "").lstrip("/")
    url = f"{META_BASE_URL}/{config['api_version']}/{clean_path}"
    request_params = dict(params or {})
    request_params["access_token"] = config["access_token"]
    try:
        response = requests.get(url, params=request_params, timeout=30)
    except requests.RequestException as error:
        raise MetaAdsApiError(sanitize_meta_error("Meta is unavailable. Try again shortly.")) from error
    _raise_for_meta_error(response, request_path=clean_path)
    return response.json()


def _post(path, data=None, files=None, config=None):
    config = config or get_meta_config()
    if not config.get("configured"):
        raise MetaAdsApiError("Meta Ads API is not configured.")
    clean_path = str(path or "").lstrip("/")
    url = f"{META_BASE_URL}/{config['api_version']}/{clean_path}"
    request_data = dict(data or {})
    request_data["access_token"] = config["access_token"]
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
    _raise_for_meta_error(response, request_path=clean_path)
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


def _paged_get(path, params=None, config=None, max_pages=25):
    page_count = 0
    rows = []
    payload = _request(path, params=params, config=config)
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
        params={"fields": "account_id,name,currency,timezone_name"},
        config=config,
    )


def fetch_meta_token_identity(config=None):
    return _request(
        "me",
        params={"fields": "id,name"},
        config=config or get_meta_config(),
    )


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


def fetch_meta_permissions(config=None):
    config = config or get_meta_config()
    payload = _request("me/permissions", params={"fields": "permission,status"}, config=config)
    return tuple(
        str(row.get("permission") or "")
        for row in payload.get("data") or []
        if str(row.get("status") or "").casefold() == "granted"
    )


def _connection_error_summary(stage, error):
    safe_message = sanitize_meta_error(error)
    lowered = safe_message.casefold()
    error_code = getattr(error, "error_code", None)
    if "version" in lowered and any(
        term in lowered for term in ("unsupported", "deprecated", "no longer", "invalid")
    ):
        return "Meta unavailable — API version unsupported."
    if error_code == 190:
        return "Meta unavailable — Meta returned error code 190."
    if stage == "token_identity":
        return "Meta unavailable — token identity read failed."
    if stage == "ad_account":
        if error_code in {10, 200} or "permission" in lowered or "access" in lowered:
            return "Meta unavailable — ad account access denied."
        return "Meta unavailable — ad account read failed."
    if stage == "campaigns":
        return "Meta unavailable — campaign read failed."
    return "Meta unavailable — connection check failed."


def _failed_connection_check(stage, label, endpoint, error):
    safe_message = sanitize_meta_error(error)
    LOGGER.warning(
        "Meta Posting read-only check failed at %s (%s): %s",
        stage,
        endpoint,
        safe_message,
    )
    return {
        "label": label,
        "status": "failed",
        "endpoint": endpoint,
        "message": safe_message,
        "error_code": getattr(error, "error_code", None),
        "summary": _connection_error_summary(stage, error),
    }


def diagnose_meta_posting_connection(config=None):
    """Run independent, read-only Posting checks and return only safe diagnostics."""
    config = config or get_meta_config()
    api_version = str(config.get("api_version") or DEFAULT_META_API_VERSION)
    api_version_source = str(config.get("api_version_source") or "provided config")
    checks = {}
    campaigns = ()

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

    identities_ready = bool(
        config.get("page_id")
        and (config.get("instagram_user_id") or config.get("instagram_actor_id"))
    )
    checks["identity"] = {
        "label": "Identity",
        "status": "ok" if identities_ready else "failed",
        "message": "OK" if identities_ready else "Facebook Page or Instagram identity is missing.",
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
            "checks": checks,
            "permission_state": "unverified",
            "permissions": (),
            "campaigns": campaigns,
        }

    core_failures = []
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
            core_failures.append(failure)

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
            "error_code": getattr(error, "error_code", None),
        }

    connected = not core_failures
    summary = core_failures[0]["summary"] if core_failures else "Meta connected"
    if connected and permission_state == "missing":
        summary = "Meta posting permission required"
    return {
        "connected": connected,
        "posting_ready": connected and permission_state != "missing",
        "summary": summary,
        "api_version": api_version,
        "api_version_source": api_version_source,
        "checks": checks,
        "permission_state": permission_state,
        "permissions": permissions,
        "campaigns": campaigns,
    }


def fetch_meta_campaign_adsets(campaign_id, config=None):
    config = config or get_meta_config()
    return _paged_get(
        f"{str(campaign_id or '').strip()}/adsets",
        params={
            "fields": "id,name,status,effective_status,campaign_id,account_id",
            "limit": 100,
        },
        config=config,
    )


class MetaPostingClient:
    """Paused-only Marketing API client used by Ads > Posting."""

    def __init__(self, config=None):
        self.config = config or get_meta_config()

    @property
    def ad_account_id(self):
        return str(self.config.get("ad_account_id") or "")

    @property
    def page_id(self):
        return str(self.config.get("page_id") or "")

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

    def campaigns(self):
        return tuple(fetch_meta_campaigns(config=self.config).get("rows") or ())

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
