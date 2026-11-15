"""Validate Meta Collection creation paths without persisting Meta objects.

This module is intentionally isolated from the normal Posting service.  Every
request is fail-closed around Meta's ``execution_options=["validate_only"]``
contract so it cannot be accidentally reused as an ordinary creation helper.
"""

from __future__ import annotations

import json
from copy import deepcopy

from meta_ads_client import MetaAdsApiError, MetaPostingClient, _post, sanitize_meta_error


VALIDATE_ONLY_EXECUTION_OPTIONS = ("validate_only",)
ALLOWED_VALIDATE_ONLY_SUFFIXES = ("/adcreatives", "/ads")


class MetaCollectionDiagnosticSafetyError(RuntimeError):
    """The diagnostic request no longer satisfies its no-persistence guard."""


def build_standalone_validate_only_payload(creative_payload):
    """Return Test A's standalone creative payload with validate-only enabled."""
    payload = deepcopy(dict(creative_payload or {}))
    payload["execution_options"] = list(VALIDATE_ONLY_EXECUTION_OPTIONS)
    return payload


def build_inline_ad_validate_only_payload(*, ad_name, adset_id, creative_payload):
    """Return Test B's paused ad payload with a Collection creative inline."""
    inline_creative = deepcopy(dict(creative_payload or {}))
    # A standalone creative name is not part of the inline AdCreative contract.
    inline_creative.pop("name", None)
    return {
        "name": str(ad_name),
        "adset_id": str(adset_id),
        "status": "PAUSED",
        "execution_options": list(VALIDATE_ONLY_EXECUTION_OPTIONS),
        "creative": inline_creative,
    }


def _decode_execution_options(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return None
    return value


def assert_validate_only_transport(path, data):
    """Refuse transmission unless the exact no-persistence guard is present."""
    clean_path = str(path or "").lstrip("/")
    if not any(clean_path.endswith(suffix) for suffix in ALLOWED_VALIDATE_ONLY_SUFFIXES):
        raise MetaCollectionDiagnosticSafetyError(
            "Collection diagnostics may only target Meta adcreatives or ads edges."
        )
    options = _decode_execution_options(dict(data or {}).get("execution_options"))
    if options != list(VALIDATE_ONLY_EXECUTION_OPTIONS):
        raise MetaCollectionDiagnosticSafetyError(
            'Meta Collection diagnostics require execution_options=["validate_only"].'
        )
    if clean_path.endswith("/ads") and str(dict(data or {}).get("status") or "") != "PAUSED":
        raise MetaCollectionDiagnosticSafetyError(
            "Inline ad validation must retain PAUSED status."
        )


def sanitized_collection_request_shape(*, mode, adset_id=""):
    """Describe the transmitted structure without exposing IDs, copy, or hashes."""
    creative = {
        "product_set_id": "<SELECTED_PRODUCT_SET_ID>",
        "image_hash": "<ROUTE_1_META_IMAGE_HASH>",
        "object_story_spec": {
            "page_id": "<CONFIGURED_PAGE_ID>",
            "instagram_user_id": "<CONFIGURED_INSTAGRAM_ACTOR_ID>",
            "link_data": {
                "link": "https://fb.com/canvas_doc/<EXISTING_IA1_ID>",
                "message": "<ROUTE_1_PRIMARY_TEXT>",
                "name": "<ROUTE_1_HEADLINE>",
                "image_hash": "<ROUTE_1_META_IMAGE_HASH>",
                "call_to_action": {"type": "SHOP_NOW"},
                "retailer_item_ids": ["0", "0", "0", "0"],
            },
        },
        "contextual_multi_ads": {"enroll_status": "OPT_IN"},
        "degrees_of_freedom_spec": {
            "creative_features_spec": {
                "image_uncrop": {"enroll_status": "OPT_OUT"},
                "media_type_automation": {"enroll_status": "OPT_IN"},
                "product_browsing": {"enroll_status": "OPT_OUT"},
            }
        },
        "url_tags": "<SPORTS_CAVE_URL_TAGS>",
    }
    if mode == "standalone":
        return {
            "endpoint": "/act_<ACCOUNT_ID>/adcreatives",
            "method": "POST",
            "execution_options": ["validate_only"],
            **creative,
        }
    if mode == "inline_ad":
        return {
            "endpoint": "/act_<ACCOUNT_ID>/ads",
            "method": "POST",
            "name": "Sports Cave validate-only Collection diagnostic",
            "adset_id": "<EXISTING_PETER_BROCK_ADSET_ID>" if adset_id else "<ADSET_ID>",
            "status": "PAUSED",
            "execution_options": ["validate_only"],
            "creative": creative,
        }
    raise ValueError("Unknown Collection diagnostic mode.")


def _sanitize_response_value(value, *, secrets):
    if isinstance(value, dict):
        return {
            str(key): (
                "[redacted]"
                if str(key).casefold() in {"access_token", "app_secret", "input_token"}
                else _sanitize_response_value(item, secrets=secrets)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_sanitize_response_value(item, secrets=secrets) for item in value]
    if isinstance(value, str):
        return sanitize_meta_error(value, extra_secrets=secrets)
    return value


def _safe_result(*, test, endpoint, response=None, error=None, config=None):
    if error is None:
        response = dict(response or {})
        config = dict(config or {})
        secrets = (config.get("access_token"), config.get("page_access_token"))
        return {
            "test": str(test),
            "endpoint": str(endpoint),
            "validated": True,
            "http_status": 200,
            "response": _sanitize_response_value(response, secrets=secrets),
        }
    config = dict(config or {})
    safe_error = sanitize_meta_error(
        error,
        extra_secrets=(config.get("access_token"), config.get("page_access_token")),
    )
    return {
        "test": str(test),
        "endpoint": str(endpoint),
        "validated": False,
        "http_status": getattr(error, "status_code", None),
        "error_code": getattr(error, "error_code", None),
        "error_subcode": getattr(error, "error_subcode", None),
        "error_user_title": sanitize_meta_error(
            getattr(error, "error_user_title", ""),
            extra_secrets=(config.get("access_token"), config.get("page_access_token")),
        ),
        "error_user_msg": sanitize_meta_error(
            getattr(error, "error_user_msg", ""),
            extra_secrets=(config.get("access_token"), config.get("page_access_token")),
        ),
        "fbtrace_id": str(getattr(error, "fbtrace_id", "") or "")[:160],
        "safe_error": safe_error,
    }


class MetaCollectionValidateOnlyProbe:
    """Run the isolated Test A/Test B matrix against Meta validation only."""

    def __init__(self, config):
        self.config = dict(config or {})
        self.ad_account_id = str(self.config.get("ad_account_id") or "")
        if not self.config.get("configured") or not self.ad_account_id:
            raise MetaCollectionDiagnosticSafetyError(
                "Meta Ads API credentials are not available in this environment."
            )

    def _validate(self, *, test, path, payload, json_fields):
        data = MetaPostingClient._graph_data(payload, json_fields=json_fields)
        assert_validate_only_transport(path, data)
        try:
            response = _post(path, data=data, config=self.config)
        except MetaAdsApiError as error:
            return _safe_result(
                test=test, endpoint=f"/{path}", error=error, config=self.config
            )
        return _safe_result(
            test=test, endpoint=f"/{path}", response=response, config=self.config
        )

    def validate_standalone_creative(self, creative_payload):
        path = f"{self.ad_account_id}/adcreatives"
        return self._validate(
            test="A_standalone_adcreative",
            path=path,
            payload=build_standalone_validate_only_payload(creative_payload),
            json_fields=(
                "object_story_spec",
                "contextual_multi_ads",
                "degrees_of_freedom_spec",
                "execution_options",
            ),
        )

    def validate_inline_ad(self, *, ad_name, adset_id, creative_payload):
        path = f"{self.ad_account_id}/ads"
        return self._validate(
            test="B_inline_ad_creative",
            path=path,
            payload=build_inline_ad_validate_only_payload(
                ad_name=ad_name,
                adset_id=adset_id,
                creative_payload=creative_payload,
            ),
            json_fields=("creative", "execution_options"),
        )

    def run_ab(self, *, ad_name, adset_id, creative_payload):
        """Run both tests even when Test A returns a Meta validation error."""
        return (
            self.validate_standalone_creative(creative_payload),
            self.validate_inline_ad(
                ad_name=ad_name,
                adset_id=adset_id,
                creative_payload=creative_payload,
            ),
        )
