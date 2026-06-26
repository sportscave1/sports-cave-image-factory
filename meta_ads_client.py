import json
import os
import re
from datetime import date, timedelta

import requests


DEFAULT_META_API_VERSION = "v20.0"
META_BASE_URL = "https://graph.facebook.com"


class MetaAdsApiError(RuntimeError):
    pass


def sanitize_meta_error(message):
    cleaned = str(message or "")
    for key in ("META_ACCESS_TOKEN", "META_APP_SECRET"):
        value = str(os.getenv(key, "")).strip()
        if value and len(value) >= 6:
            cleaned = cleaned.replace(value, "[redacted]")
    cleaned = re.sub(r"access_token=([^&\s]+)", "access_token=[redacted]", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"(Bearer\s+)[A-Za-z0-9_\-.]+", r"\1[redacted]", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bEAA[A-Za-z0-9_\-]{12,}\b", "[redacted]", cleaned)
    return cleaned


def get_meta_config():
    account_id = str(os.getenv("META_AD_ACCOUNT_ID", "")).strip()
    if account_id and not account_id.startswith("act_"):
        account_id = f"act_{account_id}"
    access_token = str(os.getenv("META_ACCESS_TOKEN", "")).strip()
    api_version = str(os.getenv("META_API_VERSION", DEFAULT_META_API_VERSION)).strip() or DEFAULT_META_API_VERSION
    return {
        "configured": bool(account_id and access_token),
        "ad_account_id": account_id,
        "access_token_present": bool(access_token),
        "app_id_present": bool(str(os.getenv("META_APP_ID", "")).strip()),
        "app_secret_present": bool(str(os.getenv("META_APP_SECRET", "")).strip()),
        "api_version": api_version,
        "access_token": access_token,
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
    }


def _raise_for_meta_error(response):
    if response.ok:
        return
    message = f"Meta API error HTTP {response.status_code}"
    try:
        payload = response.json()
        error = payload.get("error") or {}
        if error.get("message"):
            message = f"{message}: {error.get('message')}"
        if error.get("code"):
            message = f"{message} (code {error.get('code')})"
    except Exception:
        pass
    raise MetaAdsApiError(sanitize_meta_error(message))


def _request(path, params=None, config=None):
    config = config or get_meta_config()
    if not config.get("configured"):
        raise MetaAdsApiError("Meta Ads API is not configured.")
    clean_path = str(path or "").lstrip("/")
    url = f"{META_BASE_URL}/{config['api_version']}/{clean_path}"
    request_params = dict(params or {})
    request_params["access_token"] = config["access_token"]
    response = requests.get(url, params=request_params, timeout=30)
    _raise_for_meta_error(response)
    return response.json()


def _get_next_page(url):
    response = requests.get(url, timeout=30)
    _raise_for_meta_error(response)
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


def fetch_meta_ads(config=None):
    config = config or get_meta_config()
    params = {
        "fields": (
            "id,name,status,effective_status,campaign_id,adset_id,"
            "creative{id,name,thumbnail_url,effective_object_story_id,object_story_id,"
            "object_story_spec,asset_feed_spec,call_to_action_type,link_url,page_id,"
            "instagram_actor_id,image_hash,video_id},created_time,updated_time"
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
