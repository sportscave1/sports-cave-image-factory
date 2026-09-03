"""Paused-only Meta Collection template copying and read-back verification.

The normal three-route Posting service and the one-copy advanced diagnostic share
this narrow boundary.  It can only copy from the configured source ad, can only
target a PAUSED ad, and verifies the source and copied creative after every call.
Campaign, ad-set, image and Instant Experience creation remain outside this module.
"""

from __future__ import annotations

from copy import deepcopy
import os
import time

from meta_ads_client import (
    MetaAdsAmbiguousResultError,
    MetaAdsApiError,
    sanitize_meta_error,
)


COLLECTION_TEMPLATE_AD_ENV_KEY = "META_COLLECTION_TEMPLATE_AD_ID"
INITIAL_COLLECTION_TEMPLATE_AD_ID = "120249557468150554"
RENAME_READBACK_DELAYS_SECONDS = (0.0, 0.4, 0.8, 1.2, 2.0, 2.0, 2.0)
REQUIRED_COLLECTION_FEATURES = {
    # Requested Advantage+ creative defaults (Meta Marketing API v26 names).
    "description_automation": "OPT_IN",
    "inline_comment": "OPT_IN",
    "hide_price": "OPT_IN",
    "enhance_cta": "OPT_IN",
    "image_background_gen": "OPT_OUT",
    # Preserve supplied Sports Cave artwork instead of opting into automatic
    # cropping, touch-ups, generative extension or recomposition.
    "adapt_to_placement": "OPT_OUT",
    "image_auto_crop": "OPT_OUT",
    "image_touchups": "OPT_OUT",
    "image_uncrop": "OPT_OUT",
    "pac_genai_recomposition": "OPT_OUT",
    "pac_recomposition": "OPT_OUT",
    # Proven Collection settings retained from the working template contract.
    "media_type_automation": "OPT_IN",
    "product_browsing": "OPT_OUT",
}


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
            "The route-specific creative overrides are empty. No Meta copy was made."
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
        "effective_status": str(ad.get("effective_status") or ""),
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


def collection_features_match(actual_features):
    """Accept Meta-normalised supersets while enforcing required semantics."""
    actual_features = dict(actual_features or {})
    return all(
        str((actual_features.get(name) or {}).get("enroll_status") or "").upper()
        == expected
        for name, expected in REQUIRED_COLLECTION_FEATURES.items()
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
    expected_ad_name="",
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

    copied_id = str(copied_ad.get("id") or "").strip()
    checks = {
        "new_ad_id": bool(copied_id and copied_id != source_ad_id),
        "target_adset": str(copied_ad.get("adset_id") or "") == target_adset_id,
        "status_paused": str(copied_ad.get("status") or "").upper() == "PAUSED",
        "configured_status_paused": (
            str(copied_ad.get("configured_status") or "").upper() == "PAUSED"
        ),
        "route_ad_name": (
            not str(expected_ad_name or "").strip()
            or str(copied_ad.get("name") or "").strip()
            == str(expected_ad_name or "").strip()
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
        "collection_features": collection_features_match(actual_features),
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
    """Copy or reconcile one uniquely identified route in a target Ad Set."""

    def __init__(self, client, *, sleeper=None, rename_readback_delays=None):
        self.client = client
        self._sleep = sleeper or time.sleep
        self._rename_readback_delays = tuple(
            RENAME_READBACK_DELAYS_SECONDS
            if rename_readback_delays is None
            else rename_readback_delays
        ) or (0.0,)

    def read_source_snapshot(self, source_ad_id):
        """Read the immutable source once for one caller-owned Posting run."""

        source_ad_id = str(source_ad_id or "").strip()
        if not source_ad_id:
            raise MetaCollectionTemplateCopySafetyError(
                f"Configure {COLLECTION_TEMPLATE_AD_ENV_KEY} before running the template copy."
            )
        source_ad = dict(self.client.ad(source_ad_id) or {})
        source_creative_id = _creative_id(source_ad)
        if not source_creative_id:
            raise MetaCollectionTemplateCopySafetyError(
                "The configured Collection template ad has no readable creative. No copy was made."
            )
        source_creative = dict(self.client.creative(source_creative_id) or {})
        return {
            "source_ad_id": source_ad_id,
            "source_ad": deepcopy(source_ad),
            "source_creative": deepcopy(source_creative),
        }

    @staticmethod
    def _validated_source_snapshot(source_ad_id, source_snapshot):
        snapshot = dict(source_snapshot or {})
        source_before = dict(snapshot.get("source_ad") or {})
        source_creative = dict(snapshot.get("source_creative") or {})
        if (
            str(snapshot.get("source_ad_id") or "").strip() != source_ad_id
            or str(source_before.get("id") or "").strip() != source_ad_id
            or not _creative_id(source_before)
            or str(source_creative.get("id") or "").strip()
            != _creative_id(source_before)
        ):
            raise MetaCollectionTemplateCopySafetyError(
                "The per-run Collection template snapshot is invalid. No copy was made."
            )
        return source_before, source_creative

    def _read_back_renamed_ad(self, ad_id, *, expected_ad_name):
        """Poll a copied ad for Meta's bounded, eventually-consistent name update."""
        expected_ad_name = str(expected_ad_name or "").strip()
        copied_ad = {}
        attempts = 0
        for delay in self._rename_readback_delays:
            clean_delay = max(0.0, float(delay or 0.0))
            if clean_delay:
                self._sleep(clean_delay)
            copied_ad = dict(self.client.ad(ad_id) or {})
            attempts += 1
            if str(copied_ad.get("name") or "").strip() == expected_ad_name:
                break
        return copied_ad, attempts

    @staticmethod
    def _route_signature_matches(ad, creative, expected_creative):
        """Match a route without relying on Meta's inherited source-copy name."""
        ad = dict(ad or {})
        creative = dict(creative or {})
        expected_creative = dict(expected_creative or {})
        actual_link = _link_data(creative)
        expected_link = _link_data(expected_creative)
        return bool(
            str(ad.get("id") or "").strip()
            and actual_link.get("link") == expected_link.get("link")
            and actual_link.get("image_hash") == expected_link.get("image_hash")
            and creative.get("image_hash") == expected_creative.get("image_hash")
            and creative.get("product_set_id")
            == expected_creative.get("product_set_id")
            and actual_link.get("message") == expected_link.get("message")
            and actual_link.get("name") == expected_link.get("name")
        )

    def _matching_route_copies(
        self,
        *,
        source_ad_id,
        target_adset_id,
        expected_creative,
        persisted_ad_id="",
    ):
        target_rows = [
            dict(row)
            for row in self.client.ad_copies(source_ad_id)
            if str(dict(row).get("adset_id") or "") == str(target_adset_id)
        ]
        persisted_ad_id = str(persisted_ad_id or "").strip()
        if persisted_ad_id:
            target_rows = [
                row for row in target_rows
                if str(row.get("id") or "").strip() == persisted_ad_id
            ]
            if not target_rows:
                raise MetaCollectionTemplateCopySafetyError(
                    "The persisted route Ad is not a copy of the configured template in "
                    "the target Ad Set. No additional copy was made."
                )
        matches = []
        for row in target_rows:
            ad = dict(self.client.ad(row.get("id")) or {})
            creative_id = _creative_id(ad)
            if not creative_id:
                continue
            creative = dict(self.client.creative(creative_id) or {})
            if self._route_signature_matches(ad, creative, expected_creative):
                matches.append((ad, creative))
        return matches

    def create_or_reconcile_paused_route_copy(
        self,
        *,
        source_ad_id,
        target_adset_id,
        expected_ad_name,
        creative_parameters,
        persisted_ad_id="",
        source_snapshot=None,
    ):
        """Create or reuse exactly one route-specific paused template copy."""
        source_ad_id = str(source_ad_id or "").strip()
        if not source_ad_id:
            raise MetaCollectionTemplateCopySafetyError(
                f"Configure {COLLECTION_TEMPLATE_AD_ENV_KEY} before running the template copy."
            )
        request = build_paused_template_copy_request(
            target_adset_id=target_adset_id,
            creative_parameters=creative_parameters,
        )
        if source_snapshot is None:
            snapshot = self.read_source_snapshot(source_ad_id)
            source_before, source_creative = self._validated_source_snapshot(
                source_ad_id,
                snapshot,
            )
        else:
            source_before, source_creative = self._validated_source_snapshot(
                source_ad_id,
                source_snapshot,
            )

        matches = self._matching_route_copies(
            source_ad_id=source_ad_id,
            target_adset_id=request["adset_id"],
            expected_creative=request["creative_parameters"],
            persisted_ad_id=persisted_ad_id,
        )
        if len(matches) > 1:
            raise MetaCollectionTemplateCopySafetyError(
                f"More than one template copy matches route Ad {expected_ad_name!r}. "
                "No additional copy was made. Review Ads Manager before continuing."
            )
        if matches:
            copied_ad_id = str(matches[0][0].get("id") or "").strip()
            created_now = False
        else:
            try:
                copied_ad_id = self.client.copy_paused_ad_from_template(
                    source_ad_id=source_ad_id,
                    target_adset_id=request["adset_id"],
                    creative_parameters=request["creative_parameters"],
                )
                created_now = True
            except MetaAdsAmbiguousResultError:
                # Meta can persist a copy while losing the response. Reconcile only a
                # uniquely matching route signature; otherwise preserve ambiguity.
                matches = self._matching_route_copies(
                    source_ad_id=source_ad_id,
                    target_adset_id=request["adset_id"],
                    expected_creative=request["creative_parameters"],
                )
                if len(matches) != 1:
                    raise
                copied_ad_id = str(matches[0][0].get("id") or "").strip()
                created_now = False

        copied_ad = dict(self.client.ad(copied_ad_id) or {})
        renamed = False
        if str(copied_ad.get("name") or "").strip() != str(expected_ad_name or "").strip():
            self.client.rename_paused_ad(
                copied_ad_id,
                name=expected_ad_name,
                protected_source_ad_id=source_ad_id,
            )
            renamed = True
            copied_ad, rename_readback_attempts = self._read_back_renamed_ad(
                copied_ad_id,
                expected_ad_name=expected_ad_name,
            )
        else:
            rename_readback_attempts = 0
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
        try:
            result = verify_template_copy_readback(
                source_ad_before=source_before,
                source_ad_after=source_after,
                source_creative=source_creative,
                copied_ad=copied_ad,
                copied_creative=copied_creative,
                source_ad_id=source_ad_id,
                target_adset_id=request["adset_id"],
                expected_creative=request["creative_parameters"],
                expected_ad_name=expected_ad_name,
            )
        except MetaCollectionTemplateCopyVerificationError as error:
            error.result.update(
                {
                    "persistent_meta_writes": "ONE PAUSED AD" if created_now else "NONE",
                    "created_now": created_now,
                    "reconciled_existing_copy": not created_now,
                    "renamed": renamed,
                    "rename_readback_attempts": rename_readback_attempts,
                }
            )
            raise
        result["created_now"] = created_now
        result["reconciled_existing_copy"] = not created_now
        result["renamed"] = renamed
        result["rename_readback_attempts"] = rename_readback_attempts
        return result

    def create_one_paused_copy(
        self,
        *,
        source_ad_id,
        target_adset_id,
        creative_parameters,
        expected_ad_name="Template Copy Test",
    ):
        """Backward-compatible one-route diagnostic entry point."""
        return self.create_or_reconcile_paused_route_copy(
            source_ad_id=source_ad_id,
            target_adset_id=target_adset_id,
            expected_ad_name=expected_ad_name,
            creative_parameters=creative_parameters,
        )
