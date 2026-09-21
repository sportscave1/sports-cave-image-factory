"""Google Demand Gen Beta contracts. No Google or Meta publishing calls live here."""

import csv
import hashlib
import io
import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from uuid import uuid4

from PIL import Image

import ads_image_workflow as images
import dropbox_integration as dropbox


GOOGLE_DEMAND_GEN_PROMPT_V1 = Path(__file__).with_name("prompts").joinpath(
    "google_demand_gen_v1.txt"
).read_text(encoding="utf-8")
PROMPT_VERSION = "GOOGLE_DEMAND_GEN_PROMPT_V1"
RESULT_KEY = "ads_google_result"
WORKFLOW_KEY = "ads_google_image_workflow"
MANIFEST_FILENAME = "google-campaign.json"
TEMPLATE_FILENAME = "sports-cave-google-demand-gen-template.csv"
FILLED_FILENAME = "sports-cave-google-demand-gen.csv"
POSTING_HELP = "Google Ads posting is not connected yet. Save the campaign and upload it manually in Google Ads."
GROUPS = (("right", "PREMIUM SCARCITY — RIGHT ANGLE"),
          ("front", "PREMIUM SCARCITY — STRAIGHT ON"),
          ("left", "PREMIUM SCARCITY — LEFT ANGLE"))
FORMATS = (("square", 1200, 1200, "1:1"), ("landscape", 1200, 628, "1.91:1"),
           ("vertical", 960, 1200, "4:5"))
IMAGE_SLOTS = tuple(
    {"id": f"{route}_{fmt}", "group": group, "route": route,
     "label": f"{g + 1}{'ABC'[f]} — {fmt.upper()}", "format": fmt,
     "width": width, "height": height, "ratio": ratio, "position": g * 3 + f + 1,
     "filename": f"{g * 3 + f + 1:02d}-{route}-{fmt}.jpg"}
    for g, (route, group) in enumerate(GROUPS)
    for f, (fmt, width, height, ratio) in enumerate(FORMATS)
)
CSV_HEADERS = (
    "platform", "campaign_type", "product_name", "category", "country", "product_url", "campaign_moment",
    "campaign_name", "ad_group_name", "ad_name", "campaign_goal", "bidding_strategy", "conversion_goal",
    "product_feed_mode", "product_feed_guidance", "channels", "display_network", "business_name", "cta",
    "audience_name", "custom_search_terms", "demographic_signal", "optimised_targeting",
    *(f"headline_{i}" for i in range(1, 6)), *(f"description_{i}" for i in range(1, 6)),
    "final_url_suffix", *(f"{s['id']}_prompt" for s in IMAGE_SLOTS),
    *(f"{s['id']}_image" for s in IMAGE_SLOTS), "status",
)
FIXED_DEFAULTS = {
    "platform": "google", "campaign_type": "demand_gen", "campaign_goal": "Purchases",
    "bidding_strategy": "Maximise Conversions", "conversion_goal": "Purchase",
    "channels": "All Google channels", "display_network": "Off", "business_name": "Sports Cave",
    "cta": "Shop Now", "optimised_targeting": "On", "status": "draft",
}


class GoogleCampaignError(ValueError):
    pass


def platform_for(record):
    """Missing/null platform is a historical Meta record; unknown platforms fail closed."""
    value = str((record or {}).get("platform") or "meta").strip().lower()
    if value not in {"meta", "google"}:
        raise GoogleCampaignError("Unsupported ad platform.")
    return value


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def product_metadata(selection, category):
    import ads_page as ads
    # Read the same selected Edition Ops row, retaining verified identity fields too.
    return {**dict((selection or {}).get("row") or {}),
            **ads.instant_experience_product_metadata_from_selection(selection, category=category)}


def build_google_prompt(product_name, category, country, product_url, *, campaign_moment=None,
                        product_metadata=None):
    import ads_page as ads
    metadata = dict(product_metadata or {})
    moment = ads.normalize_campaign_moment(campaign_moment, selected_country=country)
    base = ads.resolve_instant_experience_product_context(
        product_name, category, product_metadata=metadata, campaign_moment=moment)
    context = ads.resolve_instant_experience_description_context(
        product_name, category, country=country, product_metadata=metadata, campaign_moment=moment)
    # The legacy Baseball claim path is specific to Meta, not verified product evidence.
    verified_limit = (ads._positive_int_or_none(metadata.get("edition_limit"))
                      or ads._verified_edition_limit_from_text(product_name))
    context.update({
        "PRODUCT_NAME": ads._clean_product_name(product_name), "CATEGORY": category, "COUNTRY": country,
        "PRODUCT_URL": ads._clean_product_url(product_url),
        "CAMPAIGN_MOMENT": json.dumps(moment, ensure_ascii=False) if ads.campaign_moment_has_user_values(moment) else "Not supplied",
        "PROMOTION_OR_OFFER": ads.exact_offer_from_inputs(moment) or "Not supplied",
        "EDITION_LIMIT": verified_limit or "Not verified", "SCARCITY_VERIFIED": bool(verified_limit),
        "PRODUCT_ERA": context.get("ERA") or base.get("product_era"),
        "ARTWORK_MOOD": base.get("artwork_mood"),
    })
    def value_text(value):
        if isinstance(value, bool):
            return str(value).lower()
        if isinstance(value, (list, dict)):
            return json.dumps(value, ensure_ascii=False)
        return str(value or "Not supplied")
    prompt = re.sub(r"\{\{([A-Z_]+)\}\}", lambda m: value_text(context[m[1]]), GOOGLE_DEMAND_GEN_PROMPT_V1)
    context_block = "\n".join(f"{key}: {value_text(context[key])}" for key in (
        "PRODUCT_ERA", "ARTWORK_MOOD", "ATHLETE_NAMES", "TEAM_NAMES", "SIDE_A", "SIDE_B",
        "FEATURED_MOMENT", "RELATIONSHIP_TYPE", "ARTWORK_TYPE"))
    # Inject shared localisation/realism guidance before the main objective, preserving the final STOP.
    guidance = ("\nVERIFIED PRODUCT CONTEXT\n" + context_block + "\n\n"
                + ads.build_country_language_guidance(country) + "\n\n"
                + ads.build_sports_cave_image_realism_rules() + "\n\n")
    return prompt.replace("==================================================\nOBJECTIVE", guidance + "==================================================\nOBJECTIVE", 1)


def new_config():
    return {**FIXED_DEFAULTS, "headlines": [""] * 5, "descriptions": [""] * 5,
            "search_terms": [], "image_slots": {s["id"]: {"prompt": ""} for s in IMAGE_SLOTS}}


def build_result(product_name, category, country, product_url, *, product_id="", campaign_moment=None,
                 product_metadata=None):
    import ads_page as ads
    error = ads.validate_ads_inputs(product_name, category, country, "demand_gen", product_url)
    error = error or ads.validate_campaign_moment(campaign_moment, selected_country=country)
    if error:
        raise GoogleCampaignError(error)
    now = utc_now()
    record = {
        "schema_version": 1, "platform": "google", "campaign_type": "demand_gen",
        "campaign_id": str(uuid4()), "product_id": product_id,
        "product_name": ads._clean_product_name(product_name), "category": category, "country": country,
        "product_url": ads._clean_product_url(product_url),
        "campaign_moment": ads.normalize_campaign_moment(campaign_moment, selected_country=country),
        "product_metadata": dict(product_metadata or {}), "google_config": new_config(),
        "created_at": now, "updated_at": now, "prompt_contract_version": PROMPT_VERSION,
    }
    record["context_key"] = "google-" + record["campaign_id"]
    record["master_prompt"] = build_google_prompt(
        record["product_name"], category, country, record["product_url"],
        campaign_moment=record["campaign_moment"], product_metadata=record["product_metadata"])
    record["generated_prompt"] = record["master_prompt"]
    return record


def new_workflow(record):
    return {"context_key": record["context_key"], "slots": {}, "outcomes": {}, "upload_versions": {}}


def asset_count(workflow):
    return sum(bool((workflow.get("slots", {}).get(s["id"]) or {}).get("valid")) for s in IMAGE_SLOTS)


def completion_label(workflow):
    count = asset_count(workflow)
    return "Complete — 9/9 assets" if count == 9 else f"Incomplete — {count}/9 assets"


def build_csv(record=None, workflow=None, *, template=False):
    row = dict.fromkeys(CSV_HEADERS, "")
    row.update(FIXED_DEFAULTS)
    if record and not template:
        config = record.get("google_config") or new_config()
        row.update({key: config.get(key, "") for key in CSV_HEADERS if key in config})
        row.update({key: record.get(key, "") for key in (
            "platform", "campaign_type", "product_name", "category", "country", "product_url")})
        moment = record.get("campaign_moment") or {}
        row["campaign_moment"] = json.dumps(moment, ensure_ascii=False)
        row["custom_search_terms"] = "; ".join(config.get("search_terms") or [])
        for kind in ("headline", "description"):
            values = config.get(kind + "s") or []
            for i in range(5):
                row[f"{kind}_{i+1}"] = values[i] if i < len(values) else ""
        for spec in IMAGE_SLOTS:
            slot = config.get("image_slots", {}).get(spec["id"]) or {}
            row[f"{spec['id']}_prompt"] = slot.get("prompt", "")
            receipt = (workflow or {}).get("outcomes", {}).get(spec["id"]) or {}
            row[f"{spec['id']}_image"] = receipt.get("path") or slot.get("saved_path", "")
        row["status"] = "complete" if workflow and asset_count(workflow) == 9 else "draft"
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_HEADERS, lineterminator="\r\n")
    writer.writeheader()
    writer.writerow(row)
    return output.getvalue().encode("utf-8-sig")


def parse_csv(data):
    """Validate atomically before changing any UI, result, assets or saved campaign."""
    import ads_page as ads
    try:
        text = bytes(data).decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        headers = reader.fieldnames or []
        if len(headers) != len(set(headers)):
            raise GoogleCampaignError("Duplicate CSV headers are not allowed.")
        missing = set(CSV_HEADERS) - set(headers)
        extra = set(headers) - set(CSV_HEADERS)
        if missing or extra:
            raise GoogleCampaignError("Google CSV headers must match the template exactly. "
                                      + ("Missing: " + ", ".join(sorted(missing)) + ". " if missing else "")
                                      + ("Unexpected: " + ", ".join(sorted(extra)) + "." if extra else ""))
        rows = list(reader)
        if len(rows) != 1:
            raise GoogleCampaignError("Google CSV must contain exactly one campaign row.")
        if None in rows[0] or any(v is None for v in rows[0].values()):
            raise GoogleCampaignError("The campaign row does not match the CSV columns. Quote commas and multiline prompts.")
        row = {key: value.strip() for key, value in rows[0].items()}
    except (UnicodeError, csv.Error) as error:
        raise GoogleCampaignError("Upload a valid UTF-8 Google CSV file.") from error
    if row["platform"] != "google" or row["campaign_type"] != "demand_gen":
        raise GoogleCampaignError("The CSV requires platform=google and campaign_type=demand_gen.")
    for field in ("product_name", "category", "country", "business_name", "cta", "product_url"):
        if not row[field]:
            raise GoogleCampaignError(f"{field} cannot be blank.")
    if not ads.is_valid_product_page_url(row["product_url"]):
        raise GoogleCampaignError(ads.PRODUCT_URL_ERROR)
    if row["category"] not in ads.CATEGORY_OPTIONS[1:] or row["country"] not in ads.COUNTRY_OPTIONS[1:]:
        raise GoogleCampaignError("Select a supported category and country from New Ads.")
    for kind, limit in (("headline", 40), ("description", 90)):
        for index in range(1, 6):
            value = row[f"{kind}_{index}"]
            if not value or len(value) > limit:
                raise GoogleCampaignError(f"{kind}_{index} must contain 1–{limit} characters (received {len(value)}).")
    if min(len(row[f"headline_{i}"]) for i in range(1, 6)) > 30:
        raise GoogleCampaignError("At least one headline must be 30 characters or fewer.")
    for spec in IMAGE_SLOTS:
        if not row[f"{spec['id']}_prompt"]:
            raise GoogleCampaignError(f"{spec['id']}_prompt needs its complete standalone image prompt.")
    terms = [term.strip() for term in row["custom_search_terms"].split(";") if term.strip()]
    if not 12 <= len(terms) <= 20:
        raise GoogleCampaignError("custom_search_terms must contain 12–20 searches separated by semicolons.")
    return row


def import_csv(data, *, current=None, workflow=None, product_rows=()):
    import ads_page as ads
    row = parse_csv(data)
    raw_moment = row["campaign_moment"]
    try:
        moment = json.loads(raw_moment) if raw_moment.startswith("{") else {"name": raw_moment}
    except ValueError as error:
        raise GoogleCampaignError("campaign_moment must be plain text or a valid saved moment object.") from error
    same_product = bool(current) and all(row[k] == current.get(k) for k in (
        "product_name", "product_url", "category", "country"))
    selection = ads.resolve_edition_ops_product_selection(row["product_name"], rows=product_rows)
    metadata = (current.get("product_metadata") if same_product else None) or product_metadata(selection, row["category"])
    record = build_result(row["product_name"], row["category"], row["country"], row["product_url"],
                          campaign_moment=moment, product_metadata=metadata,
                          product_id=(current.get("product_id") if same_product else selection.get("product_id")) or "")
    if same_product:
        for key in ("campaign_id", "context_key", "created_at"):
            record[key] = current[key]
    config = record["google_config"]
    config.update({key: value for key, value in row.items()
                   if key not in {"campaign_moment", "product_name", "category", "country", "product_url"}
                   and not re.match(r"(?:headline|description)_\d+$", key)
                   and not key.endswith(("_prompt", "_image"))})
    config["headlines"] = [row[f"headline_{i}"] for i in range(1, 6)]
    config["descriptions"] = [row[f"description_{i}"] for i in range(1, 6)]
    config["search_terms"] = [v.strip() for v in row["custom_search_terms"].split(";") if v.strip()]
    for spec in IMAGE_SLOTS:
        # CSV filenames are references, never proof of an uploaded image or a download instruction.
        config["image_slots"][spec["id"]] = {"prompt": row[f"{spec['id']}_prompt"],
                                                 "image_reference": row[f"{spec['id']}_image"]}
    record["copy_loaded"] = True
    return record, deepcopy(workflow) if same_product and workflow else new_workflow(record)


def process_image(data, spec, *, original_name=""):
    image = images.prepare_new_ads_package_jpeg(data, original_name=original_name)
    if (image["output_width"], image["output_height"]) != (spec["width"], spec["height"]):
        raise GoogleCampaignError(f"{spec['label']} requires {spec['width']} × {spec['height']} pixels; "
                                  f"received {image['output_width']} × {image['output_height']}. Upload the native composition.")
    return {**image, "valid": True, "slot_id": spec["id"], "filename": spec["filename"]}


def save_campaign(access_token, root, destination, record, workflow):
    """Save images first and commit a JSON manifest last. Incomplete campaigns are valid."""
    if platform_for(record) != "google" or record.get("campaign_type") != "demand_gen":
        raise GoogleCampaignError("This save path only accepts Google Demand Gen campaigns.")
    root, destination = dropbox.normalize_dropbox_path(root), dropbox.normalize_dropbox_path(destination)
    name = images.sanitize_product_filename(record["product_name"], max_length=90)
    folder = workflow.get("saved_folder_path") or f"{destination}/{name}-google-demand-gen-{record['campaign_id']}"
    if not dropbox.path_is_within_root(destination, root) or not dropbox.path_is_within_root(folder, root):
        raise GoogleCampaignError("The selected destination is outside the approved Files folder.")
    dropbox.ensure_folder_path(access_token, folder, root_path=root)
    saved = deepcopy(record)
    saved["updated_at"] = utc_now()
    outcomes = {}
    def upload(filename, data):
        result = dropbox.upload_batch(access_token, folder,
            [{"relative_path": filename, "data": data, "size": len(data)}], conflict="replace")
        if result.get("failures") or len(result.get("successes") or []) != 1:
            raise GoogleCampaignError(f"Could not save {filename}. Retry saving the campaign.")
        receipt = result["successes"][0].get("metadata") or {}
        return {"status": "saved", "filename": filename, "path": receipt.get("path_display") or f"{folder}/{filename}"}
    for spec in IMAGE_SLOTS:
        slot = workflow.get("slots", {}).get(spec["id"]) or {}
        persisted = {"prompt": saved["google_config"]["image_slots"][spec["id"]].get("prompt", "")}
        if slot.get("valid") and slot.get("data"):
            # Validate historical/reopened assets and convert all new saves at the boundary.
            image = process_image(slot["data"], spec, original_name=slot.get("original_name", ""))
            digest = hashlib.sha256(image["data"]).hexdigest()
            # Immutable revision folders keep an earlier manifest usable after a partial save failure.
            relative_path = f"assets/{digest}/{spec['filename']}"
            outcomes[spec["id"]] = upload(relative_path, image["data"])
            persisted.update({"saved_path": outcomes[spec["id"]]["path"], "filename": spec["filename"],
                              "sha256": digest, "width": spec["width"], "height": spec["height"],
                              "content_type": "image/jpeg", "original_name": slot.get("original_name", ""), "complete": True})
        saved["google_config"]["image_slots"][spec["id"]] = persisted
    saved["asset_count"] = len(outcomes)
    saved["status"] = "complete" if len(outcomes) == 9 else "incomplete"
    upload(FILLED_FILENAME, build_csv(saved, {**workflow, "outcomes": outcomes}))
    upload("google-prompt.txt", saved["master_prompt"].encode("utf-8"))
    outcomes["_campaign"] = upload(MANIFEST_FILENAME, json.dumps(saved, ensure_ascii=False, indent=2).encode("utf-8"))
    record.update(saved)
    workflow.update({"outcomes": outcomes, "saved_folder_path": folder, "save_open": False})
    return outcomes


def load_campaign(access_token, root, manifest_path):
    """Read only the selected saved manifest and its contained, hash-checked assets."""
    manifest_path = dropbox.normalize_dropbox_path(manifest_path)
    if not dropbox.path_is_within_root(manifest_path, root):
        raise GoogleCampaignError("Choose a campaign inside the approved Files folder.")
    try:
        record = json.loads(dropbox.get_file_bytes(access_token, manifest_path))
        if (platform_for(record) != "google" or record.get("campaign_type") != "demand_gen"
                or record.get("schema_version") != 1):
            raise GoogleCampaignError("Choose a saved Google Demand Gen campaign.")
        config = record["google_config"]
        if set(config["image_slots"]) != {s["id"] for s in IMAGE_SLOTS}:
            raise GoogleCampaignError("The saved campaign has an invalid nine-slot image mapping.")
        if len(config["headlines"]) != 5 or len(config["descriptions"]) != 5:
            raise GoogleCampaignError("The saved campaign requires five headline and description fields.")
        workflow = new_workflow(record)
        folder = str(PurePosixPath(manifest_path).parent)
        workflow["saved_folder_path"] = folder
        for spec in IMAGE_SLOTS:
            saved = config["image_slots"][spec["id"]]
            if saved.get("saved_path"):
                if not dropbox.path_is_within_root(saved["saved_path"], folder):
                    raise GoogleCampaignError("A saved image path is outside this campaign folder.")
                data = dropbox.get_file_bytes(access_token, saved["saved_path"])
                if hashlib.sha256(data).hexdigest() != saved.get("sha256"):
                    raise GoogleCampaignError(f"{spec['label']} has changed since the campaign was saved.")
                loaded = process_image(data, spec, original_name=saved.get("original_name", ""))
                # Reopening an already saved RGB JPEG must not recompress its pixels.
                with Image.open(io.BytesIO(data)) as original:
                    if original.format == "JPEG" and original.mode == "RGB":
                        loaded.update(data=data, output_size=len(data))
                workflow["slots"][spec["id"]] = loaded
                workflow["outcomes"][spec["id"]] = {"status": "saved", "path": saved["saved_path"], "filename": saved["filename"]}
        workflow["outcomes"]["_campaign"] = {"status": "saved", "path": manifest_path}
        return record, workflow
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise GoogleCampaignError("The saved Google campaign is incomplete or damaged.") from error
