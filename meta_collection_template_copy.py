"""One-shot, paused-only Meta Collection template-copy diagnostic.

This module is deliberately separate from the normal three-ad Posting service.  It
may copy one known-good ad into an existing ad set, then performs read-back checks.
It never creates campaigns, ad sets, images, canvases, or updates the Posting ledger.
"""

from __future__ import annotations

import os

from meta_ads_client import MetaAdsApiError, sanitize_meta_error


COLLECTION_TEMPLATE_AD_ENV_KEY = "META_COLLECTION_TEMPLATE_AD_ID"
INITIAL_COLLECTION_TEMPLATE_AD_ID = "120249557468150554"


class MetaCollectionTemplateCopySafetyError(RuntimeError):
    """A local safety precondition blocked the real-write diagnostic."""


class MetaCollectionTemplateCopyVerificationError(RuntimeError):
    """Meta returned a copy, but its read-back contract was not safe to accept."""

    def __init__(self, message, *, result=None):
        super().__init__(sanitize_meta_error(message))
        self.result = dict(result or {})


def configured_collection_template_ad_id(environ=None):
    """Resolve the dedicated template, with the proven live ad as initial fallback."""
    source = os.environ if environ is None else environ
    return str(
        source.get(COLLECTION_TEMPLATE_AD_ENV_KEY)
        or INITIAL_COLLECTION_TEMPLATE_AD_ID
    ).strip()


def build_paused_template_copy_request(*, target_adset_id, creative_parameters):
    """Build the only write payload allowed by this diagnostic."""
    clean_adset_id = str(target_adset_id or "").strip()
    creative_parameters = dict(creative_parameters or {})
    if not clean_adset_id:
        raise MetaCollectionTemplateCopySafetyError(
            "The failed Posting job has no target Ad Set ID. No Meta copy was made."
        )
    if not creative_parameters:
        raise MetaCollectionTemplateCopySafetyError(
            "The Peter Brock creative overrides are empty. No Meta copy was made."
        )
    return {
        "adset_id": clean_adset_id,
        "status_option": "PAUSED",
        "creative_parameters": creative_parameters,
    }


def sanitized_template_copy_error(error):
    """Return UI-safe Meta diagnostics without credentials or request bodies."""
    if isinstance(error, MetaAdsApiError):
        return {
            "http_status": error.status_code,
            "error_code": error.error_code,
            "error_subcode": error.error_subcode,
            "error_user_title": sanitize_meta_error(error.error_user_title),
            "error_user_msg": sanitize_meta_error(error.error_user_msg),
            "fbtrace_id": str(error.fbtrace_id or "")[:160],
            "safe_error": sanitize_meta_error(error),
        }
    return {"safe_error": sanitize_meta_error(error)}


def _creative_id(ad):
    return str((dict(ad or {}).get("creative") or {}).get("id") or "").strip()


def _ad_snapshot(ad):
    ad = dict(ad or {})
    return {
        "id": str(ad.get("id") or ""),
        "name": str(ad.get("name") or ""),
        "status": str(ad.get("status") or ""),
        "configured_status": str(ad.get("configured_status") or ""),
        "adset_id": str(ad.get("adset_id") or ""),
        "creative_id": _creative_id(ad),
    }


def _link_data(creative):
    return dict(
        (dict(creative or {}).get("object_story_spec") or {}).get("link_data")
        or {}
    )


def _collection_feature_spec(creative):
    return dict(
        (
            (dict(creative or {}).get("degrees_of_freedom_spec") or {}).get(
                "creative_features_spec"
            )
            or {}
        )
    )


def _source_route_values_absent(*, source_creative, copied_creative, expected_creative):
    source_link = _link_data(source_creative)
    copied_link = _link_data(copied_creative)
    expected_link = _link_data(expected_creative)
    triples = (
        (source_link.get("link"), copied_link.get("link"), expected_link.get("link")),
        (source_link.get("message"), copied_link.get("message"), expected_link.get("message")),
        (source_link.get("name"), copied_link.get("name"), expected_link.get("name")),
        (
            source_link.get("image_hash"),
            copied_link.get("image_hash"),
            expected_link.get("image_hash"),
        ),
        (
            dict(source_creative or {}).get("product_set_id"),
            dict(copied_creative or {}).get("product_set_id"),
            dict(expected_creative or {}).get("product_set_id"),
        ),
    )
    return all(
        not (source not in (None, "") and source != expected and copied == source)
        for source, copied, expected in triples
    )


def verify_template_copy_readback(
    *,
    source_ad_before,
    source_ad_after,
    source_creative,
    copied_ad,
    copied_creative,
    source_ad_id,
    target_adset_id,
    expected_creative,
):
    """Verify the copied object is paused, targeted, overridden, and source-safe."""
    source_ad_id = str(source_ad_id or "").strip()
    target_adset_id = str(target_adset_id or "").strip()
    copied_ad = dict(copied_ad or {})
    copied_creative = dict(copied_creative or {})
    expected_creative = dict(expected_creative or {})
    actual_story = dict(copied_creative.get("object_story_spec") or {})
    expected_story = dict(expected_creative.get("object_story_spec") or {})
    actual_link = _link_data(copied_creative)
    expected_link = _link_data(expected_creative)
    actual_features = _collection_feature_spec(copied_creative)
    expected_features = _collection_feature_spec(expected_creative)

    copied_id = str(copied_ad.get("id") or "").strip()
    checks = {
        "new_ad_id": bool(copied_id and copied_id != source_ad_id),
        "target_adset": str(copied_ad.get("adset_id") or "") == target_adset_id,
        "status_paused": str(copied_ad.get("status") or "").upper() == "PAUSED",
        "configured_status_paused": (
            str(copied_ad.get("configured_status") or "").upper() == "PAUSED"
        ),
        "new_creative": bool(
            _creative_id(copied_ad)
            and _creative_id(copied_ad) != _creative_id(source_ad_before)
        ),
        "page_identity": actual_story.get("page_id") == expected_story.get("page_id"),
        "instagram_identity": (
            actual_story.get("instagram_user_id")
            == expected_story.get("instagram_user_id")
        ),
        "instant_experience": actual_link.get("link") == expected_link.get("link"),
        "primary_text": actual_link.get("message") == expected_link.get("message"),
        "headline": actual_link.get("name") == expected_link.get("name"),
        "image_hash": (
            actual_link.get("image_hash") == expected_link.get("image_hash")
            and copied_creative.get("image_hash") == expected_creative.get("image_hash")
        ),
        "cta": actual_link.get("call_to_action") == {"type": "SHOP_NOW"},
        "retailer_item_ids": actual_link.get("retailer_item_ids")
        == ["0", "0", "0", "0"],
        "product_set": copied_creative.get("product_set_id")
        == expected_creative.get("product_set_id"),
        "url_tags": copied_creative.get("url_tags") == expected_creative.get("url_tags"),
        "contextual_multi_ads": copied_creative.get("contextual_multi_ads")
        == expected_creative.get("contextual_multi_ads"),
        "collection_features": actual_features == expected_features,
        "source_route_values_absent": _source_route_values_absent(
            source_creative=source_creative,
            copied_creative=copied_creative,
            expected_creative=expected_creative,
        ),
        "source_ad_unchanged": _ad_snapshot(source_ad_before)
        == _ad_snapshot(source_ad_after),
    }
    result = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "persistent_meta_writes": "ONE PAUSED AD",
        "source_ad_id": source_ad_id,
        "target_adset_id": target_adset_id,
        "copied_ad_id": copied_id,
        "copied_creative_id": _creative_id(copied_ad),
        "copied_status": str(copied_ad.get("status") or ""),
        "copied_configured_status": str(copied_ad.get("configured_status") or ""),
        "copied_effective_status": str(copied_ad.get("effective_status") or ""),
        "checks": checks,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        result["failed_checks"] = failed
        raise MetaCollectionTemplateCopyVerificationError(
            "Meta created or returned a PAUSED template copy, but read-back verification "
            "failed. Further copies are blocked. Failed checks: " + ", ".join(failed) + ".",
            result=result,
        )
    return result


class MetaCollectionTemplateCopyService:
    """Copy and verify at most one source ad for the selected target Ad Set."""

    def __init__(self, client):
        self.client = client

    def create_one_paused_copy(
        self, *, source_ad_id, target_adset_id, creative_parameters
    ):
        source_ad_id = str(source_ad_id or "").strip()
        if not source_ad_id:
            raise MetaCollectionTemplateCopySafetyError(
                f"Configure {COLLECTION_TEMPLATE_AD_ENV_KEY} before running the template copy."
            )
        request = build_paused_template_copy_request(
            target_adset_id=target_adset_id,
            creative_parameters=creative_parameters,
        )
        source_before = dict(self.client.ad(source_ad_id) or {})
        source_creative_id = _creative_id(source_before)
        if not source_creative_id:
            raise MetaCollectionTemplateCopySafetyError(
                "The configured Collection template ad has no readable creative. No copy was made."
            )
        source_creative = dict(self.client.creative(source_creative_id) or {})

        existing = [
            dict(row)
            for row in self.client.ad_copies(source_ad_id)
            if str(dict(row).get("adset_id") or "") == request["adset_id"]
        ]
        if len(existing) > 1:
            raise MetaCollectionTemplateCopySafetyError(
                "More than one template copy already exists in the target Ad Set. "
                "No additional copy was made. Review Ads Manager before continuing."
            )
        if existing:
            copied_ad_id = str(existing[0].get("id") or "").strip()
            created_now = False
        else:
            copied_ad_id = self.client.copy_paused_ad_from_template(
                source_ad_id=source_ad_id,
                target_adset_id=request["adset_id"],
                creative_parameters=request["creative_parameters"],
            )
            created_now = True

        copied_ad = dict(self.client.ad(copied_ad_id) or {})
        # Always re-read the source after Meta returns the copied ad, even if the
        # copied creative itself is unreadable. Source immutability is mandatory.
        source_after = dict(self.client.ad(source_ad_id) or {})
        copied_creative_id = _creative_id(copied_ad)
        if not copied_creative_id:
            raise MetaCollectionTemplateCopyVerificationError(
                "Meta returned a copied ad without a readable creative. Further copies are blocked.",
                result={
                    "status": "FAIL",
                    "persistent_meta_writes": "ONE PAUSED AD" if created_now else "NONE",
                    "source_ad_id": source_ad_id,
                    "target_adset_id": request["adset_id"],
                    "copied_ad_id": copied_ad_id,
                    "checks": {
                        "source_ad_unchanged": _ad_snapshot(source_before)
                        == _ad_snapshot(source_after),
                    },
                },
            )
        copied_creative = dict(self.client.creative(copied_creative_id) or {})
        result = verify_template_copy_readback(
            source_ad_before=source_before,
            source_ad_after=source_after,
            source_creative=source_creative,
            copied_ad=copied_ad,
            copied_creative=copied_creative,
            source_ad_id=source_ad_id,
            target_adset_id=request["adset_id"],
            expected_creative=request["creative_parameters"],
        )
        result["created_now"] = created_now
        result["reconciled_existing_copy"] = not created_now
        return result
