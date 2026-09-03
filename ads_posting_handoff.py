"""Session-local saved Ads packages. This module has no publishing or network path."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from uuid import uuid4

from ads_image_workflow import campaign_image_slots
from posting_import_csv import (
    PostingImportCSVError,
    _batch_from_carousel_rows,
    build_carousel_posting_import_rows,
    canonical_posting_country,
    parse_posting_import_csv,
    posting_product_handle_from_url,
)


SAVED_PACKAGE_KEY = "saved_posting_package"
PENDING_KEY = "ads_saved_package_pending"
CONSUMED_KEY = "ads_saved_package_consumed"
LOADED_KEY = "ads_saved_package_loaded"
VERSION = 1


class SavedPackageError(ValueError):
    pass


def content_hash(value):
    """Hash structured values without copying large immutable image byte buffers."""
    def normalized(item):
        if isinstance(item, bytes):
            return {"sha256": hashlib.sha256(item).hexdigest(), "size": len(item)}
        if isinstance(item, dict):
            return {str(key): normalized(val) for key, val in item.items()}
        if isinstance(item, (list, tuple)):
            return [normalized(val) for val in item]
        return item
    return hashlib.sha256(
        json.dumps(normalized(value), sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def build_saved_package(*, result, source_signature, source_copy, copy_csv, assets, files, folder):
    ad_type = result.get("campaign_type")
    if ad_type not in {"Carousel", "Instant Experience"}:
        raise SavedPackageError("This ad type is not supported by POST NOW.")
    shared = {
        "product_name": str(result.get("product_name") or ""),
        "product_id": str(result.get("product_id") or ""),
        "product_url": str(result.get("product_url") or ""),
        "product_handle": posting_product_handle_from_url(result.get("product_url")),
        "country": canonical_posting_country(result.get("country")),
        "sport_category": str(result.get("category") or ""),
    }
    try:
        if ad_type == "Carousel":
            rows = build_carousel_posting_import_rows(
                **{key: value for key, value in shared.items() if key != "product_id"},
                cards=[
                    {**card, "card_number": card["position"], "primary_text": primary}
                    for card, primary in zip(source_copy["cards"], source_copy["primary_texts"])
                ],
            )
            batch = _batch_from_carousel_rows(rows)
            # Posting's existing contract uses one product URL and fixed SHOP_NOW.
            # Never silently publish a different destination or CTA from the saved card.
            for card in source_copy["cards"]:
                if card.get("destination_url", "").strip() not in {"", shared["product_url"]}:
                    raise SavedPackageError(
                        f"Card {card['position']} has a different destination URL. "
                        "Posting supports one product URL for all five cards."
                    )
                if card.get("cta", "").strip().casefold().replace("_", " ") not in {"", "shop now"}:
                    raise SavedPackageError(
                        f"Card {card['position']} CTA is incompatible with Posting's fixed Shop Now CTA."
                    )
        else:
            # The very CSV bytes just uploaded: same canonical parser/route selection as manual import.
            batch = parse_posting_import_csv(copy_csv)
        batch.update(shared)
    except (PostingImportCSVError, KeyError, TypeError) as error:
        raise SavedPackageError(f"Saved copy cannot be loaded into Posting: {error}") from error
    package = deepcopy({
        "version": VERSION,
        "package_id": str(uuid4()),
        "source": "Creative Refresh" if result.get("workflow_mode") == "creative_refresh" else "New Ads",
        "ad_type": ad_type,
        "context_key": result.get("context_key"),
        "source_signature": source_signature,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "folder": folder,
        "batch": batch,
        "source_copy": source_copy,
        "copy_csv": copy_csv,
        "assets": assets,
        "files": files,
    })
    package["package_hash"] = content_hash(package)
    validate_saved_package(package)
    return package


def validate_saved_package(package):
    if not isinstance(package, dict) or package.get("version") != VERSION:
        raise SavedPackageError("The saved package is missing or has an unsupported version. Save it again.")
    if package.get("ad_type") not in {"Carousel", "Instant Experience"}:
        raise SavedPackageError("The saved package has an unsupported ad type.")
    if not package.get("folder") or not package.get("package_id") or not package.get("copy_csv"):
        raise SavedPackageError("The saved package is missing its Dropbox reference or copy.")
    if content_hash({key: value for key, value in package.items() if key != "package_hash"}) != package.get("package_hash"):
        raise SavedPackageError("The saved package payload is damaged or has changed. Save it again.")
    specs = campaign_image_slots(package["ad_type"])
    assets = package.get("assets") or ()
    if len(assets) != len(specs):
        raise SavedPackageError(f"The saved {package['ad_type']} package needs {len(specs)} images.")
    for spec, asset in zip(specs, assets):
        if asset.get("slot_id") != spec["id"] or asset.get("position") != spec["position"]:
            raise SavedPackageError(f"Saved image mapping is invalid for {spec['label']}.")
        if not asset.get("data") or not asset.get("path"):
            raise SavedPackageError(f"The saved image or Dropbox reference is missing for {spec['label']}.")
        if hashlib.sha256(asset["data"]).hexdigest() != asset.get("processed_hash"):
            raise SavedPackageError(f"The saved image hash is invalid for {spec['label']}.")
    return package


def queue_saved_package(package, *, state):
    validate_saved_package(package)
    state[PENDING_KEY] = {"handoff_id": str(uuid4()), "package": deepcopy(package)}

