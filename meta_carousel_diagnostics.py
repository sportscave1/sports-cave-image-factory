"""Read-only and validate-only guards for the Meta v26 Carousel contract.

This module has no persistent creation helper.  It reads the known manual
Sports Cave reference and permits POSTs only when Meta's exact
``execution_options=["validate_only"]`` guard is present.
"""

from __future__ import annotations

from copy import deepcopy
import json

from meta_ads_client import MetaAdsApiError, MetaPostingClient, _post, sanitize_meta_error


MANUAL_CAROUSEL_AD_ID = "120246591193180554"
MANUAL_CAROUSEL_CAMPAIGN_ID = "120246591193170554"
MANUAL_CAROUSEL_ADSET_ID = "120246591193190554"
MANUAL_CAROUSEL_CREATIVE_ID = "2046548402901508"
VALIDATE_ONLY_EXECUTION_OPTIONS = ("validate_only",)
ALLOWED_VALIDATE_ONLY_SUFFIXES = ("/adcreatives", "/ads")


class MetaCarouselDiagnosticSafetyError(RuntimeError):
    """Carousel validation cannot prove its non-persistent safety contract."""


def _status(value):
    return str(value or "").strip().upper()


def validate_manual_carousel_reference_contract(
    contract, *, expected_page_id="", expected_instagram_user_id=""
):
    """Validate the known manual Graph reference and return safe evidence."""

    contract = dict(contract or {})
    ad = dict(contract.get("ad") or {})
    campaign = dict(contract.get("campaign") or {})
    adset = dict(contract.get("adset") or {})
    creative = dict(contract.get("creative") or {})
    failures = []
    if str(ad.get("id") or "") != MANUAL_CAROUSEL_AD_ID:
        failures.append("reference_ad_id")
    if str(ad.get("adset_id") or "") != MANUAL_CAROUSEL_ADSET_ID:
        failures.append("reference_adset_relationship")
    if str(ad.get("campaign_id") or "") != MANUAL_CAROUSEL_CAMPAIGN_ID:
        failures.append("reference_campaign_relationship_from_ad")
    if str((ad.get("creative") or {}).get("id") or "") != MANUAL_CAROUSEL_CREATIVE_ID:
        failures.append("reference_creative_relationship")
    if str(campaign.get("id") or "") != MANUAL_CAROUSEL_CAMPAIGN_ID:
        failures.append("reference_campaign_id")
    if _status(campaign.get("objective")) != "OUTCOME_SALES":
        failures.append("campaign_objective")
    if _status(campaign.get("buying_type")) != "AUCTION":
        failures.append("campaign_buying_type")
    if str(campaign.get("daily_budget") or "") != "2500":
        failures.append("campaign_daily_budget")
    if _status(campaign.get("bid_strategy")) != "LOWEST_COST_WITHOUT_CAP":
        failures.append("campaign_bid_strategy")
    if list(campaign.get("special_ad_categories") or ()):
        failures.append("campaign_special_ad_categories")
    if str(adset.get("id") or "") != MANUAL_CAROUSEL_ADSET_ID:
        failures.append("reference_adset_id")
    if str(adset.get("campaign_id") or "") != MANUAL_CAROUSEL_CAMPAIGN_ID:
        failures.append("reference_campaign_relationship")
    if _status(adset.get("optimization_goal")) != "OFFSITE_CONVERSIONS":
        failures.append("adset_optimization_goal")
    if _status(adset.get("billing_event")) != "IMPRESSIONS":
        failures.append("adset_billing_event")
    promoted = dict(adset.get("promoted_object") or {})
    if not str(promoted.get("pixel_id") or promoted.get("dataset_id") or ""):
        failures.append("adset_pixel")
    if _status(promoted.get("custom_event_type")) != "PURCHASE":
        failures.append("adset_purchase_event")
    if str(promoted.get("product_set_id") or ""):
        failures.append("adset_product_set_absence")
    if promoted.get("smart_pse_enabled") is not False:
        failures.append("adset_smart_pse")
    if adset.get("is_dynamic_creative") is not False:
        failures.append("adset_dynamic_creative")
    if str(creative.get("id") or "") != MANUAL_CAROUSEL_CREATIVE_ID:
        failures.append("reference_creative_id")
    link_data = dict(
        (creative.get("object_story_spec") or {}).get("link_data") or {}
    )
    story = dict(creative.get("object_story_spec") or {})
    if not str(story.get("page_id") or ""):
        failures.append("creative_page_identity")
    if not str(story.get("instagram_user_id") or ""):
        failures.append("creative_instagram_identity")
    if expected_page_id and str(story.get("page_id") or "") != str(expected_page_id):
        failures.append("creative_configured_page_identity")
    if expected_instagram_user_id and str(
        story.get("instagram_user_id") or ""
    ) != str(expected_instagram_user_id):
        failures.append("creative_configured_instagram_identity")
    if not str(link_data.get("link") or ""):
        failures.append("creative_destination")
    if _status((link_data.get("call_to_action") or {}).get("type")) != "SHOP_NOW":
        failures.append("creative_cta")
    children = tuple(dict(row or {}) for row in link_data.get("child_attachments") or ())
    if len(children) != 5:
        failures.append("creative_five_cards")
    if link_data.get("multi_share_end_card") is not True:
        failures.append("creative_end_card")
    if link_data.get("multi_share_optimized") is not True:
        failures.append("creative_optimized")
    for index, child in enumerate(children, start=1):
        if not str(child.get("image_hash") or ""):
            failures.append(f"card_{index}_image_hash")
        if not str(child.get("link") or ""):
            failures.append(f"card_{index}_link")
        if not str(child.get("name") or ""):
            failures.append(f"card_{index}_headline")
        if not str(child.get("description") or ""):
            failures.append(f"card_{index}_description")
        if _status((child.get("call_to_action") or {}).get("type")) != "SHOP_NOW":
            failures.append(f"card_{index}_cta")
    feed = dict(creative.get("asset_feed_spec") or {})
    if len(tuple(feed.get("bodies") or ())) < 5:
        failures.append("creative_primary_text_bodies")
    if _status(feed.get("optimization_type")) != "DEGREES_OF_FREEDOM":
        failures.append("creative_feed_optimization")
    if failures:
        raise MetaCarouselDiagnosticSafetyError(
            "The manual Sports Cave Carousel reference no longer matches the "
            "verified v26 contract. Failed checks: " + ", ".join(failures) + "."
        )
    return {
        "validated": True,
        "reference_ad_id": MANUAL_CAROUSEL_AD_ID,
        "reference_campaign_id": MANUAL_CAROUSEL_CAMPAIGN_ID,
        "reference_adset_id": MANUAL_CAROUSEL_ADSET_ID,
        "reference_creative_id": MANUAL_CAROUSEL_CREATIVE_ID,
        "card_count": len(children),
        "primary_text_count": len(tuple(feed.get("bodies") or ())),
        "has_product_set": False,
        "normalized_readback": {
            "contextual_multi_ads": deepcopy(creative.get("contextual_multi_ads")),
            "degrees_of_freedom_spec": deepcopy(
                creative.get("degrees_of_freedom_spec")
            ),
            "format_transformation_spec": deepcopy(
                creative.get("format_transformation_spec")
            ),
            "portrait_customizations": deepcopy(
                creative.get("portrait_customizations")
            ),
            "unavailable_fields": deepcopy(
                creative.get("_unavailable_reference_fields") or {}
            ),
        },
        "read_only": True,
    }


def reference_carousel_image_hashes(contract):
    creative = dict(dict(contract or {}).get("creative") or {})
    link_data = dict(
        (creative.get("object_story_spec") or {}).get("link_data") or {}
    )
    hashes = tuple(
        str(dict(row or {}).get("image_hash") or "").strip()
        for row in link_data.get("child_attachments") or ()
    )
    if len(hashes) != 5 or not all(hashes):
        raise MetaCarouselDiagnosticSafetyError(
            "The manual Carousel reference did not expose five reusable image hashes "
            "for validate-only testing."
        )
    return hashes


def build_standalone_validate_only_payload(creative_payload):
    payload = deepcopy(dict(creative_payload or {}))
    payload["execution_options"] = list(VALIDATE_ONLY_EXECUTION_OPTIONS)
    return payload


def build_inline_ad_validate_only_payload(*, ad_name, adset_id, creative_payload):
    inline = deepcopy(dict(creative_payload or {}))
    inline.pop("name", None)
    return {
        "name": str(ad_name),
        "adset_id": str(adset_id),
        "status": "PAUSED",
        "execution_options": list(VALIDATE_ONLY_EXECUTION_OPTIONS),
        "creative": inline,
    }


def _decode_options(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return None
    return value


def assert_validate_only_transport(path, data):
    clean_path = str(path or "").lstrip("/")
    if not any(clean_path.endswith(suffix) for suffix in ALLOWED_VALIDATE_ONLY_SUFFIXES):
        raise MetaCarouselDiagnosticSafetyError(
            "Carousel diagnostics may only target Meta adcreatives or ads edges."
        )
    options = _decode_options(dict(data or {}).get("execution_options"))
    if options != list(VALIDATE_ONLY_EXECUTION_OPTIONS):
        raise MetaCarouselDiagnosticSafetyError(
            'Carousel diagnostics require execution_options=["validate_only"].'
        )
    if clean_path.endswith("/ads") and _status(dict(data or {}).get("status")) != "PAUSED":
        raise MetaCarouselDiagnosticSafetyError(
            "Carousel Ad validation must retain PAUSED status."
        )


def _safe_result(*, test, endpoint, response=None, error=None, config=None):
    config = dict(config or {})
    secrets = (config.get("access_token"), config.get("page_access_token"))
    if error is None:
        return {
            "test": str(test),
            "endpoint": str(endpoint),
            "validated": True,
            "http_status": 200,
            "response": {
                str(key): (
                    "[redacted]"
                    if str(key).casefold() in {"access_token", "app_secret", "input_token"}
                    else sanitize_meta_error(value, extra_secrets=secrets)
                    if isinstance(value, str)
                    else value
                )
                for key, value in dict(response or {}).items()
            },
        }
    return {
        "test": str(test),
        "endpoint": str(endpoint),
        "validated": False,
        "http_status": getattr(error, "status_code", None),
        "error_code": getattr(error, "error_code", None),
        "error_subcode": getattr(error, "error_subcode", None),
        "error_user_title": sanitize_meta_error(
            getattr(error, "error_user_title", ""), extra_secrets=secrets
        ),
        "error_user_msg": sanitize_meta_error(
            getattr(error, "error_user_msg", ""), extra_secrets=secrets
        ),
        "safe_error": sanitize_meta_error(error, extra_secrets=secrets),
    }


class MetaCarouselValidateOnlyProbe:
    """Validate one Carousel AdCreative and one PAUSED inline Ad without writes."""

    def __init__(self, config):
        self.config = dict(config or {})
        self.ad_account_id = str(self.config.get("ad_account_id") or "")
        if not self.config.get("configured") or not self.ad_account_id:
            raise MetaCarouselDiagnosticSafetyError(
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

    def run(self, *, ad_name, adset_id, creative_payload):
        creative_path = f"{self.ad_account_id}/adcreatives"
        ad_path = f"{self.ad_account_id}/ads"
        standalone = self._validate(
            test="carousel_standalone_adcreative",
            path=creative_path,
            payload=build_standalone_validate_only_payload(creative_payload),
            json_fields=(
                "object_story_spec",
                "asset_feed_spec",
                "contextual_multi_ads",
                "degrees_of_freedom_spec",
                "execution_options",
            ),
        )
        inline_ad = self._validate(
            test="carousel_inline_paused_ad",
            path=ad_path,
            payload=build_inline_ad_validate_only_payload(
                ad_name=ad_name,
                adset_id=adset_id,
                creative_payload=creative_payload,
            ),
            json_fields=("creative", "execution_options"),
        )
        return {
            "validated": bool(
                standalone.get("validated") and inline_ad.get("validated")
            ),
            "standalone_creative": standalone,
            "inline_ad": inline_ad,
            "persistent_meta_writes": "NONE",
        }
