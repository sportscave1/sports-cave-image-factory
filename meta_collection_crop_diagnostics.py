"""Read-only diagnostics for Meta Collection cover crop/placement state.

The production Posting workflow intentionally does not import this module.  It
only reads an existing route ad, its creative/image metadata, and the immutable
source template so crop fixes can be based on Graph evidence rather than UI
labels or guessed creative parameters.
"""

from __future__ import annotations

from copy import deepcopy


class MetaCollectionCropAuditError(RuntimeError):
    """The requested read-only crop audit could not be completed safely."""


def _mapping(value):
    return dict(value) if isinstance(value, dict) else {}


def _creative_id(ad):
    return str(_mapping(_mapping(ad).get("creative")).get("id") or "").strip()


def _link_data(creative):
    story = _mapping(_mapping(creative).get("object_story_spec"))
    return _mapping(story.get("link_data"))


def _nonempty(value):
    return value not in (None, "", (), [], {})


def _image_dimensions(image):
    image = _mapping(image)
    return {
        "width": image.get("width"),
        "height": image.get("height"),
        "original_width": image.get("original_width"),
        "original_height": image.get("original_height"),
    }


def _feature_enrollment(creative, feature_name):
    features = _mapping(
        _mapping(_mapping(creative).get("degrees_of_freedom_spec")).get(
            "creative_features_spec"
        )
    )
    return str(_mapping(features.get(feature_name)).get("enroll_status") or "")


def _creative_snapshot(*, ad, creative, image):
    ad = _mapping(ad)
    creative = _mapping(creative)
    link_data = _link_data(creative)
    creative_hash = str(creative.get("image_hash") or "").strip()
    link_hash = str(link_data.get("image_hash") or "").strip()
    image_hash = str(_mapping(image).get("hash") or "").strip()
    return {
        "ad": {
            "id": str(ad.get("id") or ""),
            "name": str(ad.get("name") or ""),
            "status": str(ad.get("status") or ""),
            "configured_status": str(ad.get("configured_status") or ""),
            "effective_status": str(ad.get("effective_status") or ""),
        },
        "creative": {
            "id": str(creative.get("id") or ""),
            "name": str(creative.get("name") or ""),
            "image_hash": creative_hash,
            "image_crops": deepcopy(_mapping(creative.get("image_crops"))),
            "link_data_image_hash": link_hash,
            "link_data_image_crops": deepcopy(_mapping(link_data.get("image_crops"))),
            "link_data_image_layer_specs": deepcopy(link_data.get("image_layer_specs")),
            "format_transformation_spec": deepcopy(
                creative.get("format_transformation_spec")
            ),
            "asset_feed_spec": deepcopy(creative.get("asset_feed_spec")),
            "platform_customizations": deepcopy(
                creative.get("platform_customizations")
            ),
            "portrait_customizations": deepcopy(
                creative.get("portrait_customizations")
            ),
            "degrees_of_freedom_spec": deepcopy(
                creative.get("degrees_of_freedom_spec")
            ),
            "media_type_automation": _feature_enrollment(
                creative, "media_type_automation"
            ),
            "unavailable_crop_fields": deepcopy(
                _mapping(creative.get("_unavailable_crop_fields"))
            ),
        },
        "meta_image": {
            "hash": image_hash,
            **_image_dimensions(image),
        },
        "route_hash_consistent": bool(
            creative_hash
            and creative_hash == link_hash
            and creative_hash == image_hash
        ),
    }


def _read_ad_snapshot(client, ad_id):
    ad = _mapping(client.ad(str(ad_id or "").strip()))
    creative_id = _creative_id(ad)
    if not creative_id:
        raise MetaCollectionCropAuditError(
            "Meta did not return a creative ID for the requested ad."
        )
    creative = _mapping(client.creative_crop_details(creative_id))
    link_data = _link_data(creative)
    image_hash = str(
        creative.get("image_hash") or link_data.get("image_hash") or ""
    ).strip()
    if not image_hash:
        raise MetaCollectionCropAuditError(
            "Meta did not return an image hash for the requested creative."
        )
    image = _mapping(client.ad_image_details(image_hash))
    return _creative_snapshot(ad=ad, creative=creative, image=image)


def classify_collection_crop_state(*, route, source_template):
    """Classify only states that Graph evidence can distinguish safely."""

    route_creative = _mapping(_mapping(route).get("creative"))
    source_creative = _mapping(_mapping(source_template).get("creative"))
    unavailable = _mapping(route_creative.get("unavailable_crop_fields"))
    route_crop_maps = {
        "creative.image_crops": _mapping(route_creative.get("image_crops")),
        "object_story_spec.link_data.image_crops": _mapping(
            route_creative.get("link_data_image_crops")
        ),
    }
    source_crop_maps = {
        "creative.image_crops": _mapping(source_creative.get("image_crops")),
        "object_story_spec.link_data.image_crops": _mapping(
            source_creative.get("link_data_image_crops")
        ),
    }
    explicit_route_crops = {
        key: value for key, value in route_crop_maps.items() if _nonempty(value)
    }
    inherited_crop_candidates = {
        key: value
        for key, value in explicit_route_crops.items()
        if value == source_crop_maps.get(key) and _nonempty(source_crop_maps.get(key))
    }
    if explicit_route_crops:
        return {
            "case": "CASE_A",
            "reason": "Meta returned explicit crop coordinates on the copied route creative.",
            "explicit_route_crops": explicit_route_crops,
            "inherited_from_template_candidate": bool(inherited_crop_candidates),
            "inherited_crop_candidates": inherited_crop_candidates,
        }

    transformation_fields = (
        "format_transformation_spec",
        "asset_feed_spec",
        "platform_customizations",
        "portrait_customizations",
        "link_data_image_layer_specs",
    )
    active_transformations = {
        key: deepcopy(route_creative.get(key))
        for key in transformation_fields
        if _nonempty(route_creative.get(key))
    }
    if active_transformations:
        return {
            "case": "CASE_B",
            "reason": (
                "Meta returned placement/format transformation state without explicit "
                "image_crops. Inspect these values before changing media automation."
            ),
            "active_transformations": active_transformations,
            "media_type_automation": str(
                route_creative.get("media_type_automation") or ""
            ),
        }

    if unavailable:
        return {
            "case": "UNDETERMINED",
            "reason": (
                "Meta did not expose every optional crop/placement field to this app. "
                "Do not change production media settings from incomplete evidence."
            ),
            "unavailable_crop_fields": unavailable,
            "media_type_automation": str(
                route_creative.get("media_type_automation") or ""
            ),
        }

    media_type_automation = str(
        route_creative.get("media_type_automation")
        or _feature_enrollment(route_creative, "media_type_automation")
        or ""
    ).upper()
    if media_type_automation == "OPT_IN":
        return {
            "case": "UNDETERMINED_CASE_B_OR_CASE_C",
            "reason": (
                "Graph returned no explicit crop or transformation, but media type "
                "automation is enabled. Its presence alone does not prove it caused the "
                "preview crop; a controlled paused comparison is required."
            ),
            "media_type_automation": media_type_automation,
            "media_type_automation_causality_proven": False,
        }

    image = _mapping(_mapping(route).get("meta_image"))
    width = image.get("width") or image.get("original_width")
    height = image.get("height") or image.get("original_height")
    return {
        "case": "CASE_C",
        "reason": (
            "Graph returned no explicit crop or placement transformation. The remaining "
            "cause is Meta fitting one source asset into placement-specific aspect ratios."
        ),
        "source_dimensions": {"width": width, "height": height},
        "media_type_automation": media_type_automation,
        "media_type_automation_causality_proven": False,
    }


def audit_meta_collection_crop_state(*, client, route_ad_id, source_template_ad_id):
    """Return a sanitized GET-only comparison of route and source-template state."""

    clean_route_id = str(route_ad_id or "").strip()
    clean_source_id = str(source_template_ad_id or "").strip()
    if not clean_route_id or not clean_source_id:
        raise MetaCollectionCropAuditError(
            "Both route and source-template ad IDs are required for the crop audit."
        )
    if clean_route_id == clean_source_id:
        raise MetaCollectionCropAuditError(
            "The route ad must be different from the immutable source-template ad."
        )

    route = _read_ad_snapshot(client, clean_route_id)
    source_template = _read_ad_snapshot(client, clean_source_id)
    return {
        "read_only": True,
        "meta_writes": "NONE",
        "route": route,
        "source_template": source_template,
        "classification": classify_collection_crop_state(
            route=route,
            source_template=source_template,
        ),
    }
