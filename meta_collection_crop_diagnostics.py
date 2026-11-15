"""Read-only diagnostics for Meta Collection cover crop/placement state.

The production Posting workflow intentionally does not import this module.  It
only reads an existing route ad, its creative/image metadata, and the immutable
source template so crop fixes can be based on Graph evidence rather than UI
labels or guessed creative parameters.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re
from urllib.parse import urlsplit, urlunsplit


DEFAULT_PREVIEW_FORMATS = (
    "MOBILE_FEED_STANDARD",
    "FACEBOOK_STORY_MOBILE",
    "FACEBOOK_REELS_MOBILE",
    "INSTAGRAM_STANDARD",
    "INSTAGRAM_STORY",
    "INSTAGRAM_REELS",
)

PREVIEW_COMPARISON_PAIRS = (
    ("FACEBOOK_FEED", "MOBILE_FEED_STANDARD", "INSTAGRAM_STANDARD"),
    ("STORIES", "FACEBOOK_STORY_MOBILE", "INSTAGRAM_STORY"),
    ("REELS", "FACEBOOK_REELS_MOBILE", "INSTAGRAM_REELS"),
)


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


def _safe_url_reference(value):
    """Keep a useful URL reference while stripping signed query material."""

    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = urlsplit(text)
    except ValueError:
        return ""
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.netloc:
        return ""
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _safe_diagnostic_value(value, key_hint=""):
    """Recursively redact secrets and signed URL query strings."""

    key_hint = str(key_hint or "").casefold()
    if any(marker in key_hint for marker in ("access_token", "app_secret", "secret")):
        return "[redacted]"
    if isinstance(value, dict):
        return {
            str(key): _safe_diagnostic_value(item, key)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_safe_diagnostic_value(item, key_hint) for item in value]
    if isinstance(value, str):
        if value.startswith(("http://", "https://")) or any(
            marker in key_hint for marker in ("url", "uri", "href", "src")
        ):
            safe_url = _safe_url_reference(value)
            if safe_url:
                return safe_url
        return re.sub(
            r"([?&](?:access_token|app_secret|sig)=)[^&\s]+",
            r"\1[redacted]",
            value,
            flags=re.IGNORECASE,
        )
    return deepcopy(value)


def _image_dimensions(image):
    image = _mapping(image)
    return {
        "width": image.get("width"),
        "height": image.get("height"),
        "original_width": image.get("original_width"),
        "original_height": image.get("original_height"),
    }


def _preview_snapshot(response):
    response = _mapping(response)
    rows = tuple(response.get("rows") or ())
    unavailable = _mapping(response.get("unavailable"))
    if unavailable:
        return {
            "available": False,
            "response_count": 0,
            "unavailable": deepcopy(unavailable),
        }
    bodies = [str(_mapping(row).get("body") or "") for row in rows]
    iframe_sources = []
    for body in bodies:
        iframe_sources.extend(
            match
            for match in re.findall(r"\bsrc=[\"']([^\"']+)", body, flags=re.IGNORECASE)
            if _safe_url_reference(match)
        )
    transformation_specs = [
        _safe_diagnostic_value(_mapping(row).get("transformation_spec"))
        for row in rows
        if "transformation_spec" in _mapping(row)
    ]
    joined_body = "\n".join(bodies)
    return {
        "available": bool(rows),
        "response_count": len(rows),
        "body_present": any(bool(body) for body in bodies),
        "body_length": len(joined_body),
        "body_sha256": (
            hashlib.sha256(joined_body.encode("utf-8")).hexdigest()
            if joined_body
            else ""
        ),
        "render_references": sorted(
            {_safe_url_reference(value) for value in iframe_sources if value}
        ),
        "transformation_spec": transformation_specs,
        "raw_preview_html_included": False,
    }


def _read_previews(client, ad_id, preview_formats):
    if not preview_formats:
        return {}
    return {
        ad_format: _preview_snapshot(
            client.ad_preview(str(ad_id or "").strip(), ad_format=ad_format)
        )
        for ad_format in preview_formats
    }


def _feature_enrollment(creative, feature_name):
    features = _mapping(
        _mapping(_mapping(creative).get("degrees_of_freedom_spec")).get(
            "creative_features_spec"
        )
    )
    return str(_mapping(features.get(feature_name)).get("enroll_status") or "")


def _creative_features(creative):
    return deepcopy(
        _mapping(
            _mapping(_mapping(creative).get("degrees_of_freedom_spec")).get(
                "creative_features_spec"
            )
        )
    )


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
            "created_time": str(ad.get("created_time") or ""),
            "updated_time": str(ad.get("updated_time") or ""),
        },
        "creative": {
            "id": str(creative.get("id") or ""),
            "name": str(creative.get("name") or ""),
            "image_hash": creative_hash,
            "image_url": _safe_url_reference(creative.get("image_url")),
            "thumbnail_url": _safe_url_reference(creative.get("thumbnail_url")),
            "effective_object_story_id": str(
                creative.get("effective_object_story_id") or ""
            ),
            "image_crops": deepcopy(_mapping(creative.get("image_crops"))),
            "link_data_image_hash": link_hash,
            "link_data_image_crops": deepcopy(_mapping(link_data.get("image_crops"))),
            "link_data_image_layer_specs": deepcopy(link_data.get("image_layer_specs")),
            "link_data_format_option": str(link_data.get("format_option") or ""),
            "link_data_link": _safe_url_reference(link_data.get("link")),
            "link_data_name": str(link_data.get("name") or ""),
            "link_data_message": str(link_data.get("message") or ""),
            "link_data_picture": _safe_url_reference(link_data.get("picture")),
            "link_data_use_flexible_image_aspect_ratio": link_data.get(
                "use_flexible_image_aspect_ratio"
            ),
            "link_data_collection_thumbnails": deepcopy(
                link_data.get("collection_thumbnails")
            ),
            "link_data_customization_rules_spec": deepcopy(
                link_data.get("customization_rules_spec")
            ),
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
            "creative_features_spec": _creative_features(creative),
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
            "url": _safe_url_reference(_mapping(image).get("url")),
            "url_128": _safe_url_reference(_mapping(image).get("url_128")),
            "permalink_url": _safe_url_reference(
                _mapping(image).get("permalink_url")
            ),
            "created_time": str(_mapping(image).get("created_time") or ""),
            "updated_time": str(_mapping(image).get("updated_time") or ""),
            "unavailable_fields": deepcopy(
                _mapping(_mapping(image).get("_unavailable_image_fields"))
            ),
        },
        "route_hash_consistent": bool(
            creative_hash
            and creative_hash == link_hash
            and creative_hash == image_hash
        ),
    }


def _read_ad_snapshot(client, ad_id, *, preview_formats=()):
    ad_reader = getattr(client, "ad_crop_details", None) or client.ad
    ad = _mapping(ad_reader(str(ad_id or "").strip()))
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
    snapshot = _creative_snapshot(ad=ad, creative=creative, image=image)
    snapshot["previews"] = _read_previews(client, ad_id, preview_formats)
    return snapshot


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
        inherited_transformations = {
            key: value
            for key, value in active_transformations.items()
            if value == source_creative.get(key)
            and _nonempty(source_creative.get(key))
        }
        return {
            "case": "CASE_B",
            "reason": (
                "Meta returned placement/format transformation state without explicit "
                "image_crops. Inspect these values before changing media automation."
            ),
            "active_transformations": active_transformations,
            "inherited_from_template_candidate": bool(inherited_transformations),
            "inherited_transformation_candidates": inherited_transformations,
            "media_type_automation": str(
                route_creative.get("media_type_automation") or ""
            ),
        }

    if unavailable:
        return {
            "case": "CASE_F",
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
            "case": "CASE_F",
            "reason": (
                "Graph returned no explicit crop or transformation, but media type "
                "automation is enabled. Its presence alone does not prove it caused the "
                "preview crop; a controlled paused comparison is required."
            ),
            "media_type_automation": media_type_automation,
            "media_type_automation_causality_proven": False,
        }

    return {
        "case": "CASE_F",
        "reason": (
            "Graph returned no explicit crop or placement transformation. Absence of "
            "serialized metadata does not prove normal aspect-ratio cropping or preview-only "
            "behaviour; compare the official placement previews before changing media."
        ),
        "media_type_automation": media_type_automation,
        "media_type_automation_causality_proven": False,
    }


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _route_creative_structure(snapshot):
    creative = _mapping(_mapping(snapshot).get("creative"))
    return {
        key: deepcopy(creative.get(key))
        for key in (
            "image_crops",
            "link_data_image_crops",
            "link_data_image_layer_specs",
            "link_data_format_option",
            "link_data_picture",
            "link_data_use_flexible_image_aspect_ratio",
            "link_data_collection_thumbnails",
            "link_data_customization_rules_spec",
            "format_transformation_spec",
            "asset_feed_spec",
            "platform_customizations",
            "portrait_customizations",
            "degrees_of_freedom_spec",
        )
    }


def _preview_pair_comparison(route):
    previews = _mapping(_mapping(route).get("previews"))
    comparison = {}
    for label, facebook_format, instagram_format in PREVIEW_COMPARISON_PAIRS:
        facebook = _mapping(previews.get(facebook_format))
        instagram = _mapping(previews.get(instagram_format))
        both_available = bool(facebook.get("available")) and bool(
            instagram.get("available")
        )
        comparison[label] = {
            "facebook_format": facebook_format,
            "instagram_format": instagram_format,
            "both_available": both_available,
            "same_preview_response": (
                bool(both_available)
                and str(facebook.get("body_sha256") or "")
                == str(instagram.get("body_sha256") or "")
            ),
            "same_transformation_spec": (
                bool(both_available)
                and _canonical(facebook.get("transformation_spec"))
                == _canonical(instagram.get("transformation_spec"))
            ),
            "visual_assessment_required": True,
        }
    return comparison


def _cross_route_comparison(routes, source_template):
    route_items = list(routes.items())
    structures = {
        ad_id: _route_creative_structure(snapshot)
        for ad_id, snapshot in route_items
    }
    serialized_structures = [_canonical(value) for value in structures.values()]
    source_structure = _route_creative_structure(source_template)
    return {
        "route_order": [ad_id for ad_id, _ in route_items],
        "all_route_hashes_consistent": all(
            bool(_mapping(snapshot).get("route_hash_consistent"))
            for _, snapshot in route_items
        ),
        "route_image_hashes": {
            ad_id: str(_mapping(_mapping(snapshot).get("creative")).get("image_hash") or "")
            for ad_id, snapshot in route_items
        },
        "all_routes_have_identical_crop_transformation_structure": (
            len(set(serialized_structures)) <= 1
        ),
        "route_structure_matches_source_template": {
            ad_id: structure == source_structure
            for ad_id, structure in structures.items()
        },
        "facebook_vs_instagram_preview_responses": {
            ad_id: _preview_pair_comparison(snapshot)
            for ad_id, snapshot in route_items
        },
        "preview_response_note": (
            "Different preview response hashes prove only that Meta returned different "
            "renders; the diagnostic deliberately does not infer visual cropping from HTML."
        ),
    }


def audit_meta_collection_crop_state(
    *, client, route_ad_id, source_template_ad_id, preview_formats=()
):
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

    route = _read_ad_snapshot(
        client,
        clean_route_id,
        preview_formats=tuple(preview_formats or ()),
    )
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


def audit_meta_collection_crop_routes(
    *,
    client,
    route_ad_ids,
    source_template_ad_id,
    preview_formats=DEFAULT_PREVIEW_FORMATS,
):
    """Audit multiple current routes while reading the source template once."""

    clean_source_id = str(source_template_ad_id or "").strip()
    clean_route_ids = tuple(
        str(ad_id or "").strip() for ad_id in route_ad_ids if str(ad_id or "").strip()
    )
    if not clean_source_id or not clean_route_ids:
        raise MetaCollectionCropAuditError(
            "At least one route Ad ID and the source-template Ad ID are required."
        )
    if len(set(clean_route_ids)) != len(clean_route_ids):
        raise MetaCollectionCropAuditError("Route Ad IDs must be unique.")
    if clean_source_id in clean_route_ids:
        raise MetaCollectionCropAuditError(
            "The immutable source-template ad cannot be audited as a copied route."
        )

    source_template = _read_ad_snapshot(client, clean_source_id)
    routes = {
        ad_id: _read_ad_snapshot(
            client,
            ad_id,
            preview_formats=tuple(preview_formats or ()),
        )
        for ad_id in clean_route_ids
    }
    classifications = {
        ad_id: classify_collection_crop_state(
            route=route,
            source_template=source_template,
        )
        for ad_id, route in routes.items()
    }
    return {
        "read_only": True,
        "meta_writes": "NONE",
        "source_template": source_template,
        "routes": routes,
        "classifications": classifications,
        "cross_route_comparison": _cross_route_comparison(
            routes,
            source_template,
        ),
    }
