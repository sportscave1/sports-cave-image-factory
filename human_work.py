import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone


HUMAN_ORIGIN = "human"
DEFAULT_TIMEZONE = "Australia/Sydney"

SENSITIVE_METADATA_KEYS = {
    "api_key",
    "authorization",
    "bearer",
    "password",
    "password_hash",
    "refresh_token",
    "secret",
    "token",
    "access_token",
}
SYSTEM_ACTOR_TYPES = {"automatic", "background", "cron", "scheduled", "system", "webhook"}
SYSTEM_ACTORS = {
    "customer_account",
    "render-cron",
    "seo_import_worker",
    "sports_cave_os",
    "sports_cave_os_cron",
    "sports_cave_os_sync",
    "sports_cave_reporting",
    "webhook",
}
EXCLUDED_ACTIONS = {
    "activity",
    "files_downloaded",
    "login",
    "logout",
    "page_loaded",
    "page_refreshed",
    "session_refreshed",
    "daily_planner_task_started",
    "daily_planner_task_halfway",
    "daily_planner_task_time_up",
    "daily_planner_task_auto_finalised",
    "daily_planner_task_replaced",
    "daily_planner_task_reopened",
    "google_seo_import_completed",
    "google_seo_import_failed",
}
EXCLUDED_ACTION_PARTS = (
    "auto_allocation",
    "cache",
    "health",
    "heartbeat",
    "metafield_mirror",
    "poll",
    "report_delivery",
    "report_generated",
    "report_test_email",
    "reporting_test_email",
    "thumbnail",
    "webhook",
)
FAILED_STATUSES = {"denied", "error", "failed", "failure", "rejected"}
SUCCESS_STATUSES = {
    "",
    "allowed",
    "complete",
    "completed",
    "created",
    "done",
    "generated",
    "ok",
    "published",
    "saved",
    "success",
    "successful",
    "updated",
    "uploaded",
}
PLANNER_ACTIONS = {
    "daily_planner_task_completed",
    "daily_planner_task_did_not_finish",
    "daily_planner_task_skipped",
}
PLANNER_COMPLETED_ACTIONS = {"daily_planner_task_completed"}
PLANNER_DID_NOT_FINISH_ACTIONS = {"daily_planner_task_did_not_finish"}
PLANNER_SKIPPED_ACTIONS = {"daily_planner_task_skipped"}


@dataclass(frozen=True)
class HumanActionRule:
    area: str
    action_type: str
    label: str
    entity_type: str = ""
    outcome: str = ""


def _rule(area, action_type, label, *, entity_type="", outcome=""):
    return HumanActionRule(
        area=area,
        action_type=action_type,
        label=label,
        entity_type=entity_type,
        outcome=outcome,
    )


ACTION_RULES = {
    # Mockups and generated assets.
    "mockup_generated": _rule("Mockups", "mockup_created", "Mockup created", entity_type="mockup_run"),
    "mockup_made": _rule("Mockups", "mockup_created", "Mockup created", entity_type="mockup_run"),
    "mockup_uploaded": _rule("Mockups", "mockup_saved", "Mockup saved", entity_type="mockup_run"),
    "mockup_deleted": _rule("Mockups", "mockup_deleted", "Mockup deleted", entity_type="mockup_run"),
    "mockup_zip_saved": _rule("Mockups", "mockup_pack_saved", "Mockup pack saved", entity_type="mockup_run"),
    "mockups_saved_dropbox": _rule("Mockups", "mockups_saved", "Mockups saved", entity_type="dropbox_folder"),
    "mockup_pack_exported": _rule("Mockups", "mockup_pack_exported", "Mockup pack exported"),
    "mockup_zip_exported": _rule("Mockups", "mockup_pack_exported", "Mockup pack exported"),
    "prompt_pack_exported": _rule("Mockups", "prompt_pack_exported", "Prompt pack exported"),

    # Product, Shopify, collection and edition operations.
    "new_product_prompt_generated": _rule("Product Uploads", "product_upload_completed", "Product upload completed", entity_type="product_upload_prompt"),
    "existing_product_update_prompt_generated": _rule("Product Uploads", "existing_product_updated", "Existing product updated", entity_type="product_upload_prompt"),
    "product_uploaded": _rule("Products", "product_upload_completed", "Product upload completed", entity_type="product"),
    "product_created": _rule("Products", "product_created", "New product created", entity_type="product"),
    "product_updated": _rule("Products", "product_updated", "Existing product updated", entity_type="product"),
    "product_media_updated": _rule("Products", "product_media_updated", "Product media updated", entity_type="product"),
    "product_media_uploaded": _rule("Products", "product_media_uploaded", "Product media uploaded", entity_type="product"),
    "product_assigned_collection": _rule("Products", "product_assigned_collection", "Product assigned to collection", entity_type="product"),
    "product_published": _rule("Products", "product_published", "Product published", entity_type="product"),
    "product_edition_updated": _rule("Products", "product_edition_updated", "Product edition updated", entity_type="product"),
    "edition_product_updated": _rule("Products", "product_edition_updated", "Product edition updated", entity_type="edition_product"),
    "edition_product_manual_update": _rule("Products", "product_edition_updated", "Product edition updated", entity_type="edition_product"),
    "edition_product_archived": _rule("Products", "product_archived", "Product archived", entity_type="edition_product"),
    "collection_created": _rule("Products", "collection_created", "Collection created", entity_type="collection"),
    "collection_updated": _rule("Products", "collection_updated", "Collection updated", entity_type="collection"),
    "shopify_new_products_pulled": _rule("Products", "shopify_new_products_pulled", "Manual Shopify product pull completed"),
    "shopify_catalogue_refreshed": _rule("Products", "shopify_catalogue_refreshed", "Shopify catalogue refreshed"),
    "shopify_product_reconciliation_completed": _rule("Products", "shopify_product_reconciliation_completed", "Shopify product reconciliation completed"),
    "shopify_metafield_pushed": _rule("Products", "shopify_metafield_pushed", "Manual Shopify metafield pushed"),
    "manual_next_number_lowered": _rule("Products", "product_edition_updated", "Product edition updated", entity_type="edition_product"),

    # Design Studio, dashboard tasks and prompt work.
    "task_added": _rule("Design Studio", "design_task_created", "Design Studio task created", entity_type="dashboard_task"),
    "dashboard_task_added": _rule("Design Studio", "design_task_created", "Design Studio task created", entity_type="dashboard_task"),
    "task_imported": _rule("Design Studio", "design_tasks_imported", "Design Studio tasks imported"),
    "task_completed": _rule("Design Studio", "design_task_completed", "Design Studio task completed", entity_type="dashboard_task"),
    "dashboard_task_completed": _rule("Design Studio", "design_task_completed", "Design Studio task completed", entity_type="dashboard_task"),
    "design_task_completed": _rule("Design Studio", "design_task_completed", "Design Studio task completed", entity_type="dashboard_task"),
    "task_design_style_updated": _rule("Design Studio", "design_task_updated", "Design Studio task updated", entity_type="dashboard_task"),
    "task_design_details_updated": _rule("Design Studio", "design_task_updated", "Design Studio task updated", entity_type="dashboard_task"),
    "task_deleted": _rule("Design Studio", "design_task_deleted", "Design Studio task deleted", entity_type="dashboard_task"),
    "design_prompt_saved": _rule("Design Studio", "design_prompt_saved", "Design prompt saved"),

    # Ads and creative campaign work.
    "ad_prompt_generated": _rule("Ads", "ad_copy_saved", "Ad copy saved"),
    "ad_images_saved": _rule("Ads", "ad_creative_saved", "Ad creative saved"),
    "ad_plan_saved": _rule("Ads", "ad_plan_saved", "Ad plan saved"),
    "ad_creative_saved": _rule("Ads", "ad_creative_saved", "Ad creative saved"),
    "ad_creative_approved": _rule("Ads", "ad_creative_approved", "Ad creative approved"),
    "ad_copy_saved": _rule("Ads", "ad_copy_saved", "Ad copy saved"),
    "ad_published": _rule("Ads", "ad_published", "Ad published"),
    "ad_completed": _rule("Ads", "ad_completed", "Ad work completed"),

    # SEO and Growth Intelligence.
    "blog_created": _rule("SEO", "seo_article_saved", "SEO article saved", entity_type="seo_record"),
    "blog_updated": _rule("SEO", "seo_article_saved", "SEO article saved", entity_type="seo_record"),
    "keyword_updated": _rule("SEO", "seo_keyword_mapping_updated", "SEO keyword mapping updated", entity_type="seo_record"),
    "keyword_mapping_updated": _rule("SEO", "seo_keyword_mapping_updated", "SEO keyword mapping updated", entity_type="seo_record"),
    "link_plan_created": _rule("SEO", "seo_recommendation_saved", "SEO recommendation saved", entity_type="seo_record"),
    "link_plan_updated": _rule("SEO", "seo_recommendation_saved", "SEO recommendation saved", entity_type="seo_record"),
    "outreach_created": _rule("SEO", "seo_recommendation_saved", "SEO recommendation saved", entity_type="seo_record"),
    "outreach_updated": _rule("SEO", "seo_recommendation_saved", "SEO recommendation saved", entity_type="seo_record"),
    "gsc_csv_imported": _rule("SEO", "seo_manual_import_completed", "SEO manual import completed", entity_type="seo_record"),
    "seo_article_saved": _rule("SEO", "seo_article_saved", "SEO article saved", entity_type="seo_record"),
    "seo_optimisation_saved": _rule("SEO", "seo_optimisation_saved", "SEO optimisation saved", entity_type="seo_record"),
    "seo_recommendation_saved": _rule("SEO", "seo_recommendation_saved", "SEO recommendation saved", entity_type="seo_record"),
    "seo_recommendation_converted_to_task": _rule("SEO", "seo_task_created", "SEO task created", entity_type="seo_growth_task"),
    "seo_task_saved": _rule("SEO", "seo_task_saved", "SEO task saved", entity_type="seo_growth_task"),
    "seo_task_status_updated": _rule("SEO", "seo_task_completed", "SEO task completed", entity_type="seo_growth_task"),
    "seo_growth_pipeline_queued": _rule("SEO", "seo_growth_pipeline_queued", "Manual SEO sync started", entity_type="seo_growth_pipeline_run"),
    "google_seo_import_queued": _rule("SEO", "google_seo_import_queued", "Manual Google SEO import started", entity_type="seo_sync_run"),
    "seo_phase4_queued": _rule("SEO", "seo_phase4_queued", "Manual SEO Phase 4 sync started", entity_type="seo_phase4_run"),
    "google_seo_properties_selected": _rule("SEO", "google_seo_properties_selected", "Google SEO properties selected", entity_type="google_seo_connection"),
    "google_seo_synced": _rule("SEO", "google_seo_synced", "Manual Google SEO sync completed", entity_type="google_seo_connection"),

    # Social Media.
    "social_day_completed": _rule("Social Media", "social_day_completed", "Social day completed", entity_type="social_daily_plan"),
    "social_day_reopened": _rule("Social Media", "social_day_reopened", "Social day reopened", entity_type="social_daily_plan"),
    "social_plan_created": _rule("Social Media", "social_plan_saved", "Social plan saved", entity_type="social_daily_plan"),
    "social_plan_saved": _rule("Social Media", "social_plan_saved", "Social plan saved", entity_type="social_daily_plan"),
    "social_plan_updated": _rule("Social Media", "social_plan_saved", "Social plan saved", entity_type="social_daily_plan"),
    "social_record_corrected": _rule("Social Media", "social_record_corrected", "Social record corrected"),
    "social_post_logged": _rule("Social Media", "social_content_saved", "Social content saved", entity_type="social_post"),
    "social_post_marked_live": _rule("Social Media", "social_content_published", "Social content published", entity_type="social_post"),
    "social_post_saved": _rule("Social Media", "social_content_saved", "Social content saved", entity_type="social_post"),
    "social_post_updated": _rule("Social Media", "social_content_saved", "Social content saved", entity_type="social_post"),
    "social_weekly_checkin_created": _rule("Social Media", "social_weekly_review_saved", "Social weekly review saved", entity_type="social_weekly_report"),
    "social_weekly_checkin_updated": _rule("Social Media", "social_weekly_review_saved", "Social weekly review saved", entity_type="social_weekly_report"),
    "social_weekly_checkin_submitted": _rule("Social Media", "social_weekly_review_completed", "Social weekly review completed", entity_type="social_weekly_report"),
    "social_weekly_priority_saved": _rule("Social Media", "social_weekly_priority_saved", "Social weekly priority saved", entity_type="social_weekly_priority"),
    "social_content_job_saved": _rule("Social Media", "social_content_saved", "Social content saved", entity_type="social_content_job"),
    "social_media_output_saved": _rule("Social Media", "social_creative_saved", "Social creative saved"),
    "reel_prompt_saved": _rule("Social Media", "social_reel_prompt_saved", "Reel prompt saved"),
    "reel_video_uploaded": _rule("Social Media", "social_reel_video_uploaded", "Reel video uploaded"),
    "reel_saved": _rule("Social Media", "social_reel_saved", "Reel saved"),

    # Orders, certificates and fulfilment.
    "order_fulfilled": _rule("Orders", "order_fulfilled", "Order fulfilled", entity_type="order"),
    "order_fulfilled_certificate_generated": _rule("Orders", "order_fulfilled_certificate_generated", "Order fulfilled + certificate generated", entity_type="order"),
    "manual_fulfilment_override": _rule("Orders", "manual_fulfilment_override", "Manual fulfilment override", entity_type="order"),
    "prodigi_status_updated": _rule("Orders", "order_status_updated", "Order status updated", entity_type="order"),
    "certificate_generated": _rule("Orders", "certificate_generated", "Certificate generated", entity_type="certificate"),
    "certificate_uploaded": _rule("Orders", "certificate_uploaded", "Certificate uploaded", entity_type="certificate"),
    "certificate_generation_failed": _rule("Orders", "certificate_generation_failed", "Certificate generation failed", entity_type="certificate", outcome="failed"),
    "certificate_upload_failed": _rule("Orders", "certificate_upload_failed", "Certificate upload failed", entity_type="certificate", outcome="failed"),

    # Daily Planner terminal outcomes.
    "daily_planner_task_completed": _rule("Daily Planner", "daily_planner_task_completed", "Planner task completed", entity_type="daily_execution_timer", outcome="completed"),
    "daily_planner_task_did_not_finish": _rule("Daily Planner", "daily_planner_task_did_not_finish", "Planner task did not finish", entity_type="daily_execution_timer", outcome="did_not_finish"),
    "daily_planner_task_skipped": _rule("Daily Planner", "daily_planner_task_skipped", "Planner task skipped", entity_type="daily_execution_timer", outcome="skipped"),

    # Files and content-library mutations.
    "files_folder_created": _rule("Files", "files_folder_created", "Folder created", entity_type="dropbox_folder"),
    "files_uploaded": _rule("Files", "files_uploaded", "File uploaded", entity_type="dropbox_file"),
    "files_item_renamed": _rule("Files", "files_item_renamed", "File item renamed", entity_type="dropbox_item"),
    "files_items_copied": _rule("Files", "files_items_copied", "File items copied", entity_type="dropbox_folder"),
    "files_items_moved": _rule("Files", "files_items_moved", "File items moved", entity_type="dropbox_folder"),
    "files_moved_to_recycle_bin": _rule("Files", "files_moved_to_recycle_bin", "Files moved to Recycle Bin", entity_type="dropbox_folder"),

    # Admin actions that materially change access or operations.
    "account_created": _rule("Accounts & Access", "account_created", "Account created", entity_type="os_user"),
    "account_updated": _rule("Accounts & Access", "account_updated", "Account updated", entity_type="os_user"),
    "permissions_changed": _rule("Accounts & Access", "permissions_changed", "Permissions changed", entity_type="os_user"),
    "reporting_permission_changed": _rule("Accounts & Access", "reporting_permission_changed", "Reporting permission changed", entity_type="os_user"),
    "account_permanently_removed": _rule("Accounts & Access", "account_removed", "Account removed", entity_type="os_user"),
}

MEANINGFUL_AUDIT_ACTIONS = frozenset(ACTION_RULES)
CANONICAL_ACTION_TYPES = frozenset(rule.action_type for rule in ACTION_RULES.values())


def json_dict(value):
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def compact_text(value, *, limit=300):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if limit and len(text) > limit:
        return text[: max(limit - 1, 0)].rstrip() + "..."
    return text


def source_action_from_row(row, payload=None):
    payload = json_dict(row.get("new_value")) if payload is None else dict(payload or {})
    return compact_text(
        row.get("activity_action_type")
        or payload.get("action_type")
        or row.get("event_type")
    ).casefold()


def payload_and_metadata(row):
    row = dict(row or {})
    payload = json_dict(row.get("new_value"))
    metadata = json_dict(row.get("activity_metadata") or payload.get("metadata"))
    return payload, metadata


def _safe_metadata_value(value, *, depth=0):
    if depth > 2:
        return compact_text(value, limit=200)
    if isinstance(value, dict):
        return {
            str(key)[:80]: _safe_metadata_value(item, depth=depth + 1)
            for key, item in value.items()
            if str(key).strip().casefold() not in SENSITIVE_METADATA_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_safe_metadata_value(item, depth=depth + 1) for item in list(value)[:25]]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return compact_text(value, limit=500)


def safe_metadata(metadata):
    clean = {}
    for key, value in dict(metadata or {}).items():
        clean_key = str(key or "").strip()
        if not clean_key or clean_key.casefold() in SENSITIVE_METADATA_KEYS:
            continue
        clean[clean_key[:80]] = _safe_metadata_value(value)
    return clean


def _is_system_or_noise(action, row, payload, metadata):
    if not action or action in EXCLUDED_ACTIONS:
        return True
    if "auto_allocation" in action and "manual" not in action:
        return True
    if any(part in action for part in EXCLUDED_ACTION_PARTS):
        return True
    source = compact_text(row.get("source") or payload.get("source")).casefold()
    actor = compact_text(metadata.get("actor_display") or row.get("actor")).casefold()
    actor_type = compact_text(metadata.get("actor_type") or payload.get("actor_type")).casefold()
    if metadata.get("is_system") is True or payload.get("is_system") is True:
        return True
    if actor_type in SYSTEM_ACTOR_TYPES:
        return True
    if source in {"shopify_backfill", "supabase_ledger", "webhook"}:
        return True
    return actor in SYSTEM_ACTORS and not metadata.get("actor_id")


def authenticated_actor(row, metadata):
    actor_id = compact_text(metadata.get("actor_id"), limit=120)
    if not actor_id:
        return {}
    display = compact_text(
        metadata.get("actor_display")
        or metadata.get("actor_name")
        or row.get("actor")
        or metadata.get("actor_email")
        or actor_id,
        limit=160,
    )
    return {
        "user_id": actor_id,
        "staff_display_name": display or "Staff member",
        "staff_role": compact_text(metadata.get("actor_role"), limit=80),
    }


def normalise_outcome(action, metadata, rule=None):
    if rule and rule.outcome:
        return rule.outcome
    raw = compact_text(
        metadata.get("outcome")
        or metadata.get("result")
        or metadata.get("status")
        or metadata.get("certificate_status"),
        limit=80,
    ).casefold()
    if action.endswith("_failed") or raw in FAILED_STATUSES:
        return "failed"
    if raw in {"skipped", "skip"}:
        return "skipped"
    if raw in {"did_not_finish", "did not finish", "couldnt_finish", "could not finish", "unfinished"}:
        return "did_not_finish"
    return "completed" if raw in SUCCESS_STATUSES or not raw else raw.replace(" ", "_")


def actual_seconds_from_metadata(metadata):
    for key in ("actual_seconds", "actual_elapsed_seconds", "focused_seconds", "duration_seconds"):
        try:
            value = int(metadata.get(key))
        except (TypeError, ValueError):
            continue
        if value >= 0:
            return value
    return None


def _item_from_metadata(metadata, row):
    keys = (
        "work_description",
        "task",
        "task_title",
        "title",
        "product_name",
        "product_title",
        "product",
        "campaign",
        "content_name",
        "order",
        "order_name",
        "filename",
        "folder",
        "destination",
        "keyword",
        "target_keyword",
        "target_page",
        "name",
    )
    for key in keys:
        value = compact_text(metadata.get(key), limit=180)
        if value:
            return value
    entity_id = compact_text(row.get("entity_id"), limit=180)
    return entity_id


def _message_from_row(row, payload, action):
    return compact_text(
        row.get("activity_message")
        or payload.get("message")
        or row.get("reason")
        or action.replace("_", " ").title(),
        limit=300,
    )


def _description_for_event(rule, row, payload, metadata, action):
    message = _message_from_row(row, payload, action)
    item = _item_from_metadata(metadata, row)
    if item and item.casefold() not in message.casefold():
        return compact_text(f"{rule.label} - {item}", limit=300)
    if message and not any(part in message.casefold() for part in ("metafield mirror", "webhook", "cache")):
        return message
    return compact_text(f"{rule.label} - {item}" if item else rule.label, limit=300)


def _occurred_at(value):
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def correlation_key_for(row, action, metadata):
    event_key = compact_text(metadata.get("event_key"), limit=220)
    if event_key:
        return event_key
    identity = json.dumps(
        {
            "action": action,
            "entity_type": row.get("entity_type") or "",
            "entity_id": row.get("entity_id") or "",
            "actor_id": metadata.get("actor_id") or "",
            "message": row.get("activity_message")
            or json_dict(row.get("new_value")).get("message")
            or row.get("reason")
            or "",
        },
        ensure_ascii=True,
        sort_keys=True,
        default=str,
    )
    return f"human-work:{hashlib.sha256(identity.encode('utf-8')).hexdigest()}"


def activity_to_human_work_event(row):
    row = dict(row or {})
    payload, metadata = payload_and_metadata(row)
    action = source_action_from_row(row, payload)
    if _is_system_or_noise(action, row, payload, metadata):
        return None
    rule = ACTION_RULES.get(action)
    if not rule:
        return None
    actor = authenticated_actor(row, metadata)
    if not actor:
        return None
    outcome = normalise_outcome(action, metadata, rule)
    try:
        occurred_at = _occurred_at(row.get("created_at") or datetime.now(timezone.utc))
    except (TypeError, ValueError):
        occurred_at = datetime.now(timezone.utc)
    entity_type = compact_text(row.get("entity_type") or rule.entity_type, limit=100)
    entity_id = compact_text(row.get("entity_id"), limit=250)
    safe = safe_metadata(metadata)
    safe.update(
        {
            "source_action_type": action,
            "source_event_type": compact_text(row.get("event_type") or action, limit=100),
        }
    )
    if rule.action_type != action:
        safe["canonical_from"] = action
    return {
        **actor,
        "origin": HUMAN_ORIGIN,
        "area": compact_text(rule.area, limit=100),
        "action_type": compact_text(rule.action_type, limit=100),
        "description": _description_for_event(rule, row, payload, metadata, action),
        "entity_type": entity_type,
        "entity_id": entity_id,
        "source_route": compact_text(
            row.get("activity_page")
            or payload.get("page")
            or row.get("source")
            or rule.area,
            limit=120,
        ),
        "outcome": outcome,
        "occurred_at": occurred_at,
        "actual_seconds": actual_seconds_from_metadata(metadata),
        "correlation_key": correlation_key_for(row, action, metadata),
        "metadata": safe,
        "audit_log_id": row.get("id"),
    }


def event_counts_as_completed(event):
    event = dict(event or {})
    return (
        str(event.get("origin") or "").casefold() == HUMAN_ORIGIN
        and str(event.get("outcome") or "").casefold() == "completed"
    )


def event_is_planner(event):
    event = dict(event or {})
    action = str(event.get("action_type") or "").casefold()
    source = str((event.get("metadata") or {}).get("source_action_type") or "").casefold()
    return action in PLANNER_ACTIONS or source in PLANNER_ACTIONS or event.get("area") == "Daily Planner"


def event_to_activity_row(event):
    event = dict(event or {})
    metadata = safe_metadata(event.get("metadata") or {})
    metadata.update(
        {
            "actor_id": event.get("user_id") or "",
            "actor_display": event.get("staff_display_name") or "",
            "actor_role": event.get("staff_role") or "",
            "status": event.get("outcome") or "",
            "result": event.get("outcome") or "",
            "origin": event.get("origin") or HUMAN_ORIGIN,
            "human_work_event_id": str(event.get("id") or ""),
            "event_key": event.get("correlation_key") or "",
        }
    )
    return {
        "id": event.get("audit_log_id") or event.get("id") or "",
        "event_type": event.get("action_type") or "",
        "entity_type": event.get("entity_type") or "",
        "entity_id": event.get("entity_id") or "",
        "reason": event.get("description") or "",
        "actor": event.get("staff_display_name") or "",
        "source": event.get("source_route") or event.get("area") or "",
        "created_at": event.get("occurred_at"),
        "new_value": {
            "message": event.get("description") or "",
            "page": event.get("area") or event.get("source_route") or "",
            "action_type": event.get("action_type") or "",
            "metadata": metadata,
        },
    }


def table_record(event, tzinfo=timezone.utc):
    event = dict(event or {})
    occurred = event.get("occurred_at")
    try:
        occurred_at = _occurred_at(occurred)
    except (TypeError, ValueError):
        occurred_at = None
    local = occurred_at.astimezone(tzinfo or timezone.utc) if occurred_at else None
    actual_seconds = event.get("actual_seconds")
    try:
        actual_seconds = int(actual_seconds) if actual_seconds is not None else None
    except (TypeError, ValueError):
        actual_seconds = None
    return {
        "Date/time": local.strftime("%d %b %Y, %I:%M %p %Z").lstrip("0") if local else "",
        "Staff member": compact_text(event.get("staff_display_name"), limit=160),
        "Work/task": compact_text(event.get("description") or "Work completed", limit=300),
        "Area": compact_text(event.get("area"), limit=100),
        "Action type": compact_text(event.get("action_type"), limit=100),
        "Outcome/status": compact_text(event.get("outcome") or "completed", limit=80).replace("_", " ").title(),
        "Actual time": format_duration(actual_seconds) if actual_seconds is not None else "",
        "Reference": compact_text(event.get("entity_id"), limit=180),
        "Sort Timestamp": occurred_at or datetime.min.replace(tzinfo=timezone.utc),
    }


def format_duration(seconds):
    try:
        seconds = max(int(seconds), 0)
    except (TypeError, ValueError):
        return ""
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"
