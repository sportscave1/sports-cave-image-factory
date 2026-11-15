"""GET-only inspection of an existing Carousel; no create or update operations.

Run in an environment with the existing Sports Cave Meta configuration:
    python scripts/audit_meta_carousel_settings.py --execute [--ad-id ID]

Without --execute, no Graph request is sent. The report records exposed fields
and omissions, not an inferred Ads Manager "All optimisations" state.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from meta_ads_client import (
    MetaAdsApiError,
    _request,
    get_meta_config,
    is_optional_meta_diagnostic_read_error,
    sanitize_meta_error,
)
from meta_carousel_diagnostics import MANUAL_CAROUSEL_AD_ID


def _read_fields(read, config, object_id, required, optional=()):
    """Isolate unsupported optional fields without hiding auth failures."""
    try:
        data = dict(read(object_id, params={"fields": ",".join((*required, *optional))}, config=config) or {})
    except MetaAdsApiError as error:
        if not optional or not is_optional_meta_diagnostic_read_error(error):
            raise
        data = dict(read(object_id, params={"fields": ",".join(required)}, config=config) or {})
        unavailable = {}
        for field in optional:
            try:
                value = dict(read(object_id, params={"fields": f"id,{field}"}, config=config) or {})
            except MetaAdsApiError as field_error:
                if not is_optional_meta_diagnostic_read_error(field_error):
                    raise
                unavailable[field] = {"reason": "unsupported_or_unavailable", "error_code": field_error.error_code}
            else:
                if field in value:
                    data[field] = value[field]
        data["_unavailable_fields"] = unavailable
    unavailable = data.setdefault("_unavailable_fields", {})
    for field in optional:
        if field not in data:
            unavailable.setdefault(field, {"reason": "omitted_by_meta"})
    return data


def _redact(value, config):
    if isinstance(value, dict):
        return {
            key: "[redacted]" if "token" in key.casefold() or "secret" in key.casefold() else _redact(item, config)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact(item, config) for item in value]
    if isinstance(value, str):
        return sanitize_meta_error(value, extra_secrets=[config.get(key) for key in ("access_token", "page_access_token", "app_secret")])
    return value


def audit_carousel_settings(config, *, ad_id=MANUAL_CAROUSEL_AD_ID, read=None):
    """Inspect linked objects and the configured app using Graph GETs only."""
    if not config.get("configured") or not config.get("access_token"):
        raise ValueError("Existing Meta credentials are not configured in this environment.")
    if not str(ad_id).isdigit():
        raise ValueError("The reference ad ID must be numeric.")
    read = _request if read is None else read
    ad = _read_fields(read, config, str(ad_id),
        ("id", "account_id", "campaign_id", "adset_id", "creative{id}", "status", "configured_status", "effective_status"),
        ("tracking_specs", "conversion_domain", "conversion_specs", "tracking_and_conversion_with_defaults", "creative_automation_spec"))
    if str(ad.get("account_id")) != str(config.get("ad_account_id", "")).removeprefix("act_"):
        raise ValueError("The reference ad does not belong to the configured ad account.")
    related = [str(ad.get("campaign_id") or ""), str(ad.get("adset_id") or ""), str((ad.get("creative") or {}).get("id") or "")]
    if not all(value.isdigit() for value in related):
        raise ValueError("The reference ad did not expose its campaign, ad set and creative IDs.")
    campaign_id, adset_id, creative_id = related
    campaign = _read_fields(read, config, campaign_id,
        ("id", "objective", "buying_type", "status", "effective_status"))
    adset = _read_fields(read, config, adset_id,
        ("id", "campaign_id", "promoted_object", "optimization_goal", "billing_event", "status", "effective_status"),
        ("destination_type", "attribution_spec", "is_dynamic_creative"))
    creative = _read_fields(read, config, creative_id,
        ("id", "object_story_spec"),
        ("degrees_of_freedom_spec", "asset_feed_spec", "url_tags", "contextual_multi_ads"))
    app_id = str(config.get("app_id") or "")
    app = {"configured": bool(app_id), "verified": False}
    if app_id:
        if not app_id.isdigit():
            raise ValueError("The configured Meta App ID must be numeric.")
        try:
            observed = dict(read(app_id, params={"fields": "id,name"}, config=config) or {})
        except MetaAdsApiError as error:
            app.update(reason="app_identity_read_unavailable", error_code=error.error_code)
        else:
            app.update(id=observed.get("id"), name=observed.get("name"),
                       verified=str(observed.get("id") or "") == app_id)
    return _redact({
        "read_only": True,
        "persistent_meta_writes": "NONE",
        "api_version": config.get("api_version"),
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "ad": ad, "campaign": campaign, "adset": adset,
        "creative": creative, "configured_app": app,
        "all_optimisations_verified": False,
        "interpretation": "Compare these exposed fields with the known-good Ads Manager state; an omitted field is not proof of opt-out or support.",
    }, config)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Send GET requests only; never create or update an object.")
    parser.add_argument("--ad-id", default=MANUAL_CAROUSEL_AD_ID)
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps({"status": "dry_run", "read_only": True, "requests_sent": 0, "reference_ad_id": args.ad_id}))
        return 0
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    try:
        report = audit_carousel_settings(get_meta_config(), ad_id=args.ad_id)
    except (ValueError, MetaAdsApiError) as error:
        print(json.dumps({"status": "inspection_blocked", "read_only": True, "message": sanitize_meta_error(str(error))}))
        return 2
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
