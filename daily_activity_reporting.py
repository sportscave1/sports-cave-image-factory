import csv
import hashlib
import html
import io
import json
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

import os_accounts
import human_work
import social_media_store


REPORT_PURPOSE = "daily_staff_activity"
REPORT_TIMEZONE = "Australia/Sydney"
SYDNEY_TZ = ZoneInfo(REPORT_TIMEZONE)
SUCCESS_STATUSES = {"", "complete", "completed", "done", "ok", "success", "successful", "uploaded"}
FAILED_STATUSES = {"error", "failed", "failure", "rejected"}
ATTENTION_STATUSES = {
    "attention",
    "incomplete",
    "needs attention",
    "needs_attention",
    "partial",
    "pending",
}
SYSTEM_ACTOR_TYPES = {"automatic", "background", "cron", "scheduled", "system", "webhook"}
EXCLUDED_ACTIONS = {
    "activity",
    "files_downloaded",
    "login",
    "logout",
    "page_loaded",
    "page_refreshed",
    "session_refreshed",
}
EXCLUDED_ACTION_PARTS = (
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
SYSTEM_SOURCES = {
    "shopify_backfill",
    "supabase_ledger",
    "webhook",
}
MEANINGFUL_WORK_ACTIONS = human_work.MEANINGFUL_AUDIT_ACTIONS | human_work.CANONICAL_ACTION_TYPES
SECRET_PATTERN = re.compile(
    r"(?i)\b(api[_ -]?key|authorization|bearer|password|secret|token)\b\s*[:=]\s*\S+"
)
TRACE_PATTERN = re.compile(r"(?is)\btraceback \(most recent call last\):.*")

ACTION_CATEGORIES = {
    "account_created": "Account and access changes",
    "account_updated": "Account and access changes",
    "permissions_changed": "Account and access changes",
    "profile_updated": "Account and access changes",
    "password_changed": "Account and access changes",
    "password_change_failed": "Account and access changes",
    "reporting_permission_changed": "Account and access changes",
    "ad_prompt_generated": "Ads and campaign work",
    "ad_images_saved": "Ads and campaign work",
    "certificate_generated": "Certificates",
    "certificate_uploaded": "Certificates",
    "certificate_generation_failed": "Certificates",
    "certificate_upload_failed": "Certificates",
    "daily_execution_completed": "Daily Execution",
    "daily_execution_created": "Daily Execution",
    "daily_execution_tomorrow_planned": "Daily Execution",
    "daily_execution_archived": "Daily Execution",
    "daily_execution_mip_completed": "Daily Execution",
    "daily_execution_task_completed": "Daily Execution",
    "daily_planner_task_completed": "Daily Execution",
    "daily_planner_task_did_not_finish": "Daily Execution",
    "daily_planner_task_skipped": "Daily Execution",
    "daily_planner_task_reopened": "Daily Execution",
    "design_task_completed": "Prompts and creative work",
    "collection_created": "Products",
    "collection_updated": "Products",
    "design_prompt_saved": "Prompts and creative work",
    "reel_prompt_saved": "Prompts and creative work",
    "reel_video_uploaded": "Social media work",
    "reel_saved": "Social media work",
    "social_day_completed": "Social media work",
    "social_day_reopened": "Social media work",
    "social_plan_created": "Social media work",
    "social_plan_updated": "Social media work",
    "social_post_logged": "Social media work",
    "social_post_marked_live": "Social media work",
    "social_record_corrected": "Social media work",
    "social_weekly_checkin_submitted": "Social media work",
    "mockup_generated": "Mockups",
    "mockup_made": "Mockups",
    "mockup_uploaded": "Mockups",
    "mockup_zip_saved": "Mockups",
    "mockups_saved_dropbox": "Mockups",
    "mockup_pack_exported": "Mockups",
    "mockup_zip_exported": "Mockups",
    "prompt_pack_exported": "Mockups",
    "order_fulfilled": "Orders",
    "order_fulfilled_certificate_generated": "Orders",
    "prodigi_status_updated": "Orders",
    "task_added": "Tasks",
    "task_completed": "Tasks",
    "dashboard_task_added": "Tasks",
    "dashboard_task_completed": "Tasks",
    "product_uploaded": "Products",
    "product_created": "Products",
    "product_updated": "Products",
    "product_media_updated": "Products",
    "product_edition_updated": "Products",
    "edition_product_updated": "Products",
    "edition_product_manual_update": "Products",
    "edition_product_archived": "Products",
    "edition_order_manual_override": "Orders",
    "manual_next_number_lowered": "Products",
    "files_folder_created": "Files",
    "files_uploaded": "Files",
    "files_item_renamed": "Files",
    "files_items_copied": "Files",
    "files_items_moved": "Files",
    "files_moved_to_recycle_bin": "Files",
    "files_downloaded": "Files",
}
ACTION_CATEGORIES.update(
    {
        rule.action_type: rule.area
        for rule in human_work.ACTION_RULES.values()
    }
)

ACTION_PREFIX_CATEGORIES = (
    ("account_", "Account and access changes"),
    ("permission_", "Account and access changes"),
    ("ad_", "Ads and campaign work"),
    ("certificate_", "Certificates"),
    ("daily_execution_", "Daily Execution"),
    ("design_", "Prompts and creative work"),
    ("edition_order_manual_", "Orders"),
    ("edition_product_", "Products"),
    ("files_", "Files"),
    ("mockup_", "Mockups"),
    ("order_", "Orders"),
    ("product_", "Products"),
    ("prompt_", "Prompts and creative work"),
    ("reel_", "Social media work"),
    ("social_", "Social media work"),
    ("shopify_manual_", "Products"),
    ("task_", "Tasks"),
)


@dataclass(frozen=True)
class DigestConfiguration:
    enabled: bool
    timezone_name: str
    send_hour: int


@dataclass(frozen=True)
class ReportPeriod:
    report_date: date
    timezone_name: str
    start_utc: datetime
    end_utc: datetime
    start_local: datetime
    end_local: datetime


def _env_true(value):
    return str(value or "").strip().casefold() in {"1", "true", "yes", "on"}


def load_digest_configuration(environ=None):
    environ = os.environ if environ is None else environ
    timezone_name = str(environ.get("ACTIVITY_DIGEST_TIMEZONE", REPORT_TIMEZONE) or "").strip()
    try:
        ZoneInfo(timezone_name)
    except Exception:
        timezone_name = REPORT_TIMEZONE
    try:
        send_hour = int(environ.get("ACTIVITY_DIGEST_HOUR", "17"))
    except (TypeError, ValueError):
        send_hour = 17
    send_hour = min(max(send_hour, 0), 23)
    return DigestConfiguration(
        enabled=_env_true(environ.get("ACTIVITY_DIGEST_ENABLED", "")),
        timezone_name=timezone_name,
        send_hour=send_hour,
    )


def _aware_utc(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("A timezone-aware datetime is required.")
    return value.astimezone(timezone.utc)


def build_report_period(now=None, *, timezone_name=REPORT_TIMEZONE, report_date=None):
    now_utc = _aware_utc(now or datetime.now(timezone.utc))
    local_tz = ZoneInfo(str(timezone_name or REPORT_TIMEZONE))
    local_now = now_utc.astimezone(local_tz)
    selected_date = report_date or local_now.date()
    if isinstance(selected_date, str):
        selected_date = date.fromisoformat(selected_date)
    start_local = datetime.combine(selected_date, time.min, tzinfo=local_tz)
    if selected_date == local_now.date():
        end_local = local_now
    elif selected_date < local_now.date():
        end_local = datetime.combine(selected_date, time.max, tzinfo=local_tz)
    else:
        raise ValueError("A report cannot include a future date.")
    return ReportPeriod(
        report_date=selected_date,
        timezone_name=local_tz.key,
        start_utc=start_local.astimezone(timezone.utc),
        end_utc=end_local.astimezone(timezone.utc),
        start_local=start_local,
        end_local=end_local,
    )


def production_run_decision(now=None, *, configuration=None):
    configuration = configuration or load_digest_configuration()
    now_utc = _aware_utc(now or datetime.now(timezone.utc))
    local_now = now_utc.astimezone(ZoneInfo(configuration.timezone_name))
    if not configuration.enabled:
        return False, "disabled", local_now.date()
    if local_now.hour < configuration.send_hour:
        return False, "before_send_hour", local_now.date()
    return True, "ready", local_now.date()


def next_expected_send(now=None, *, configuration=None):
    configuration = configuration or load_digest_configuration()
    now_utc = _aware_utc(now or datetime.now(timezone.utc))
    local_tz = ZoneInfo(configuration.timezone_name)
    local_now = now_utc.astimezone(local_tz)
    candidate = datetime.combine(
        local_now.date(),
        time(hour=configuration.send_hour),
        tzinfo=local_tz,
    )
    if candidate <= local_now:
        candidate = datetime.combine(
            local_now.date().fromordinal(local_now.date().toordinal() + 1),
            time(hour=configuration.send_hour),
            tzinfo=local_tz,
        )
    return candidate


def _json_dict(value):
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return {}


def sanitize_report_text(value, *, limit=500):
    text_value = re.sub(r"\s+", " ", str(value or "").strip())
    text_value = SECRET_PATTERN.sub(r"\1=[redacted]", text_value)
    text_value = TRACE_PATTERN.sub("[technical details removed]", text_value)
    return text_value[:limit]


def _row_payload(row):
    row = dict(row or {})
    payload = _json_dict(row.get("new_value"))
    metadata = _json_dict(row.get("activity_metadata") or payload.get("metadata"))
    return payload, metadata


def _action_name(row, payload):
    return sanitize_report_text(
        row.get("activity_action_type")
        or payload.get("action_type")
        or row.get("event_type")
        or "",
        limit=120,
    ).casefold()


def _category_for_action(action):
    if action in ACTION_CATEGORIES:
        return ACTION_CATEGORIES[action]
    for prefix, category in ACTION_PREFIX_CATEGORIES:
        if action.startswith(prefix):
            return category
    return "Other staff work"


def _status_for_activity(action, metadata):
    status = sanitize_report_text(
        metadata.get("result")
        or metadata.get("status")
        or ("failed" if action.endswith("_failed") else "success"),
        limit=50,
    ).casefold()
    if status in FAILED_STATUSES or action.endswith("_failed"):
        return "failed"
    if status in ATTENTION_STATUSES:
        return "attention"
    return "success"


def activity_is_meaningful(row):
    row = dict(row or {})
    payload, metadata = _row_payload(row)
    action = _action_name(row, payload)
    actor_type = sanitize_report_text(
        metadata.get("actor_type") or payload.get("actor_type") or "",
        limit=40,
    ).casefold()
    source = sanitize_report_text(row.get("source") or payload.get("source") or "", limit=100).casefold()
    actor = sanitize_report_text(row.get("actor") or "", limit=100).casefold()
    if not action or action in EXCLUDED_ACTIONS:
        return False
    if any(part in action for part in EXCLUDED_ACTION_PARTS):
        return False
    if metadata.get("is_system") is True or payload.get("is_system") is True:
        return False
    if actor_type in SYSTEM_ACTOR_TYPES or source in SYSTEM_SOURCES:
        return False
    if actor in {"sports_cave_os_sync", "sports_cave_os_cron", "sports_cave_reporting"}:
        return False
    if "auto_allocation" in action and "manual" not in action:
        return False
    if action in ACTION_CATEGORIES or any(action.startswith(prefix) for prefix, _ in ACTION_PREFIX_CATEGORIES):
        return True
    return metadata.get("source_user_initiated") is True


def activity_is_meaningful_work(row):
    """Keep Home work analytics aligned to explicit staff-facing completions."""
    payload, _metadata = _row_payload(row)
    return bool(
        _action_name(row, payload) in MEANINGFUL_WORK_ACTIONS
        and activity_is_meaningful(row)
    )


def _activity_message(row, payload, metadata, action):
    try:
        import sports_cave_dashboard

        entry = sports_cave_dashboard.activity_from_audit_row(row)
        message = entry.get("message") or ""
    except Exception:
        message = (
            row.get("activity_message")
            or payload.get("message")
            or row.get("reason")
            or action.replace("_", " ").title()
        )
    return sanitize_report_text(message, limit=300)


def _activity_item(row, metadata):
    for key in (
        "product",
        "product_title",
        "product_name",
        "order",
        "order_name",
        "filename",
        "name",
        "title",
        "prompt_name",
        "destination",
    ):
        value = metadata.get(key)
        if value not in (None, ""):
            return sanitize_report_text(value, limit=180)
    return sanitize_report_text(row.get("entity_id") or "", limit=180)


def _safe_failure_message(action, item):
    action_label = action[:-7] if action.endswith("_failed") else action
    action_label = re.sub(r"\s+", " ", action_label.replace("_", " ")).strip()
    message = f"{action_label.capitalize() or 'Action'} failed"
    if item:
        message = f"{message}: {item}"
    return sanitize_report_text(message, limit=300)


def classify_activity(row):
    if not activity_is_meaningful(row):
        return None
    row = dict(row or {})
    payload, metadata = _row_payload(row)
    action = _action_name(row, payload)
    created_at = _aware_utc(row.get("created_at"))
    page = sanitize_report_text(
        row.get("activity_page")
        or payload.get("page")
        or row.get("source")
        or "Sports Cave",
        limit=100,
    )
    item = _activity_item(row, metadata)
    status = _status_for_activity(action, metadata)
    details = (
        _safe_failure_message(action, item)
        if status == "failed"
        else _activity_message(row, payload, metadata, action)
    )
    return {
        "id": str(row.get("id") or ""),
        "created_at": created_at,
        "action": action,
        "category": _category_for_action(action),
        "page": page,
        "item": item,
        "details": details,
        "status": status,
        "actor": sanitize_report_text(
            row.get("actor")
            or metadata.get("actor_display")
            or metadata.get("actor_name")
            or "",
            limit=160,
        ),
        "actor_id": sanitize_report_text(metadata.get("actor_id") or "", limit=100),
        "actor_email": os_accounts.normalise_login(metadata.get("actor_email") or metadata.get("email")),
        "metadata": {
            "actor_role": sanitize_report_text(metadata.get("actor_role") or "", limit=40),
            "actor_timezone": sanitize_report_text(metadata.get("actor_timezone") or "", limit=80),
        },
    }


def _normalised_account(account):
    account = dict(account or {})
    return {
        "id": str(account.get("id") or ""),
        "username": str(account.get("username") or "").strip(),
        "email": str(account.get("email") or "").strip(),
        "display_name": str(
            account.get("display_name")
            or account.get("email")
            or account.get("username")
            or "Staff member"
        ).strip(),
        "role": str(account.get("role") or os_accounts.ROLE_WORKER).strip().casefold(),
        "country": str(account.get("country") or "").strip(),
        "timezone": os_accounts.timezone_for_user(account),
        "is_active": bool(account.get("is_active", True)),
    }


def _account_indexes(accounts):
    by_id = {}
    by_email = {}
    by_username = {}
    display_candidates = defaultdict(list)
    for account in accounts:
        if account["id"]:
            by_id[account["id"]] = account
        if account["email"]:
            by_email[os_accounts.normalise_login(account["email"])] = account
        if account["username"]:
            by_username[os_accounts.normalise_login(account["username"])] = account
        display_candidates[os_accounts.normalise_login(account["display_name"])].append(account)
    by_display = {
        key: values[0]
        for key, values in display_candidates.items()
        if key and len(values) == 1
    }
    return by_id, by_email, by_username, by_display


def _activity_account(activity, indexes):
    by_id, by_email, by_username, by_display = indexes
    if activity.get("actor_id") in by_id:
        return by_id[activity["actor_id"]]
    if activity.get("actor_email") in by_email:
        return by_email[activity["actor_email"]]
    actor_key = os_accounts.normalise_login(activity.get("actor"))
    return by_email.get(actor_key) or by_username.get(actor_key) or by_display.get(actor_key)


def _task_finished(task):
    task = dict(task or {})
    status = str(task.get("status") or "").strip().casefold()
    return bool(task.get("completed")) or status in {
        "done",
        "complete",
        "completed",
        "couldnt_finish",
    }


def _task_successful(task):
    task = dict(task or {})
    status = str(task.get("status") or "").strip().casefold()
    return status in {"done", "complete", "completed"} or (
        bool(task.get("completed")) and status != "couldnt_finish"
    )


def _task_row(task, *, kind):
    task = dict(task or {})
    name = sanitize_report_text(task.get("task") or task.get("title") or "", limit=240)
    if not name:
        return None
    status = sanitize_report_text(task.get("status") or "", limit=40).casefold()
    completed = _task_finished(task)
    return {
        "kind": kind,
        "task": name,
        "status": status or ("done" if completed else "outstanding"),
        "completed": completed,
        "successful": _task_successful(task),
        "notes": sanitize_report_text(
            task.get("why") or task.get("details") or task.get("outcome") or "",
            limit=300,
        ),
        "time_blocked": sanitize_report_text(task.get("time_blocked") or task.get("time") or "", limit=80),
        "carried_from": sanitize_report_text(task.get("carried_from") or "", limit=80),
    }


def summarise_daily_execution(sheet, *, report_date):
    sheet = dict(sheet or {})
    if not sheet:
        return {
            "exists": False,
            "report_date": report_date.isoformat(),
            "status": "missing",
            "tasks": [],
            "mips": [],
            "completed_tasks": [],
            "outstanding_tasks": [],
            "moved_tasks": [],
            "completed_count": 0,
            "successful_count": 0,
            "could_not_finish_count": 0,
            "outstanding_count": 0,
            "task_count": 0,
            "completion_percentage": 0,
            "notes": [],
        }
    tasks = []
    for task in (sheet.get("top_tasks") or [])[:3]:
        row = _task_row(task, kind="MIP")
        if row:
            tasks.append(row)
    for task in sheet.get("additional_items") or []:
        row = _task_row(task, kind="Other")
        if row:
            tasks.append(row)
    completed = [task for task in tasks if task["completed"]]
    successful = [task for task in tasks if task["successful"]]
    could_not_finish = [task for task in tasks if task["status"] == "couldnt_finish"]
    outstanding = [task for task in tasks if not task["completed"]]
    moved = [
        task
        for task in tasks
        if task["status"] in {"moved", "carried", "carried_forward", "couldnt_finish"}
        or task.get("carried_from")
    ]
    for carried in (sheet.get("planning_data") or {}).get("carried_forward") or []:
        name = sanitize_report_text(
            (carried or {}).get("task") if isinstance(carried, dict) else carried,
            limit=240,
        )
        if name and all(task["task"] != name for task in moved):
            moved.append(
                {
                    "kind": "Carried",
                    "task": name,
                    "status": "moved",
                    "completed": False,
                    "notes": "",
                    "time_blocked": "",
                    "carried_from": "",
                }
            )
    notes = []
    for value in (
        sheet.get("daily_summary"),
        (sheet.get("review_data") or {}).get("worked_well"),
        (sheet.get("review_data") or {}).get("could_not_finish"),
        sheet.get("tomorrow_intention"),
    ):
        clean = sanitize_report_text(value, limit=400)
        if clean and clean not in notes:
            notes.append(clean)
    task_count = len(tasks)
    completed_count = len(completed)
    return {
        "exists": True,
        "report_date": str(sheet.get("sheet_date") or report_date.isoformat()),
        "status": sanitize_report_text(sheet.get("status") or "active", limit=50),
        "tasks": tasks,
        "mips": [task for task in tasks if task["kind"] == "MIP"],
        "completed_tasks": completed,
        "outstanding_tasks": outstanding,
        "moved_tasks": moved,
        "completed_count": completed_count,
        "successful_count": len(successful),
        "could_not_finish_count": len(could_not_finish),
        "outstanding_count": len(outstanding),
        "task_count": task_count,
        "completion_percentage": round((completed_count / task_count) * 100) if task_count else 0,
        "notes": notes[:5],
    }


def _work_lines(activities):
    grouped = Counter()
    for activity in activities:
        label = activity.get("details") or activity.get("action", "").replace("_", " ").title()
        grouped[(activity.get("category") or "Other staff work", label)] += 1
    lines = []
    for (category, label), count in sorted(
        grouped.items(),
        key=lambda item: (-item[1], item[0][0].casefold(), item[0][1].casefold()),
    )[:8]:
        lines.append(
            {
                "category": category,
                "label": f"{label} (x{count})" if count > 1 else label,
                "count": count,
            }
        )
    return lines


def _staff_summary(account, activities, *, owner):
    timezone_name = account.get("timezone") or REPORT_TIMEZONE
    try:
        local_tz = ZoneInfo(timezone_name)
    except Exception:
        local_tz = SYDNEY_TZ
        timezone_name = REPORT_TIMEZONE
    ordered = sorted(activities, key=lambda row: row["created_at"])
    return {
        **account,
        "is_owner": bool(owner and account.get("id") == owner.get("id")),
        "total_actions": len(ordered),
        "completed_actions": sum(activity["status"] == "success" for activity in ordered),
        "failed_actions": sum(activity["status"] == "failed" for activity in ordered),
        "attention_actions": sum(activity["status"] == "attention" for activity in ordered),
        "last_activity_at": ordered[-1]["created_at"] if ordered else None,
        "last_activity_local": (
            ordered[-1]["created_at"].astimezone(local_tz).isoformat() if ordered else ""
        ),
        "work_lines": _work_lines(ordered),
        "activities": [
            {
                **activity,
                "local_timestamp": activity["created_at"].astimezone(local_tz),
                "staff_timezone": timezone_name,
            }
            for activity in ordered
        ],
    }


def build_report_snapshot(
    *,
    period,
    accounts,
    activity_rows,
    daily_execution_sheet=None,
    social_summaries=None,
    owner_email="",
    recipient="",
    is_test=False,
):
    active_accounts = [
        _normalised_account(account)
        for account in accounts or []
        if bool((account or {}).get("is_active", True))
    ]
    owner_key = os_accounts.normalise_login(owner_email)
    owner = next(
        (
            account
            for account in active_accounts
            if account["role"] == os_accounts.ROLE_ADMIN
            and os_accounts.normalise_login(account["email"]) == owner_key
        ),
        None,
    )
    indexes = _account_indexes(active_accounts)
    activities_by_user = defaultdict(list)
    classified = []
    for row in activity_rows or []:
        try:
            activity = classify_activity(row)
        except (TypeError, ValueError):
            continue
        if not activity:
            continue
        if activity["created_at"] < period.start_utc or activity["created_at"] > period.end_utc:
            continue
        account = _activity_account(activity, indexes)
        if not account:
            continue
        activity["staff_id"] = account["id"]
        activity["staff_name"] = account["display_name"]
        activity["staff_role"] = account["role"]
        activities_by_user[account["id"]].append(activity)
        classified.append(activity)

    staff = [
        _staff_summary(
            account,
            activities_by_user.get(account["id"], []),
            owner=owner,
        )
        for account in active_accounts
    ]
    staff.sort(key=lambda account: (not account["is_owner"], account["display_name"].casefold()))
    supplied_daily_sheet = dict(daily_execution_sheet or {})
    owner_sheet = bool(
        owner
        and supplied_daily_sheet
        and str(supplied_daily_sheet.get("user_id") or "") == str(owner.get("id") or "")
    )
    daily_execution = summarise_daily_execution(
        supplied_daily_sheet if owner_sheet else None,
        report_date=period.report_date,
    )
    for member in staff:
        member["daily_execution"] = daily_execution if member["is_owner"] else None
        social_summary = dict((social_summaries or {}).get(member["id"]) or {})
        member["social_media"] = social_summary or None

    social_overview = social_media_store.reporting_team_overview(social_summaries)

    total_actions = sum(member["total_actions"] for member in staff)
    completed_actions = sum(member["completed_actions"] for member in staff)
    failed_actions = sum(member["failed_actions"] for member in staff)
    attention = []
    for member in staff:
        if member["failed_actions"]:
            attention.append(
                f"{member['display_name']}: {member['failed_actions']} failed action"
                f"{'s' if member['failed_actions'] != 1 else ''}."
            )
        social_summary = member.get("social_media") or {}
        if social_summary.get("blockers"):
            attention.append(
                f"{member['display_name']} reported a Social Media blocker: "
                f"{sanitize_report_text(social_summary['blockers'], limit=180)}"
            )
    if owner is None:
        attention.append("The configured Reporting owner does not match an active admin account.")
    elif not daily_execution["exists"]:
        attention.append("No Daily Execution sheet was created for the configured owner today.")
    elif daily_execution["outstanding_count"]:
        attention.append(
            f"Daily Execution: {daily_execution['outstanding_count']} task"
            f"{'s' if daily_execution['outstanding_count'] != 1 else ''} outstanding."
        )
    if daily_execution.get("could_not_finish_count"):
        attention.append(
            f"Daily Execution: {daily_execution['could_not_finish_count']} task"
            f"{'s' if daily_execution['could_not_finish_count'] != 1 else ''} "
            "closed as could not finish."
        )

    subject_prefix = "[TEST] " if is_test else ""
    subject = (
        f"{subject_prefix}Sports Cave daily staff report - "
        f"{period.report_date.strftime('%d %B %Y')}"
    )
    snapshot = {
        "purpose": REPORT_PURPOSE,
        "report_date": period.report_date.isoformat(),
        "timezone": period.timezone_name,
        "covered_start": period.start_utc,
        "covered_end": period.end_utc,
        "covered_start_local": period.start_local,
        "covered_end_local": period.end_local,
        "recipient": recipient,
        "subject": subject,
        "is_test": bool(is_test),
        "staff": staff,
        "daily_execution": daily_execution,
        "social_media": social_overview,
        "summary": {
            "active_staff_count": len(staff),
            "staff_with_activity": sum(member["total_actions"] > 0 for member in staff),
            "total_actions": total_actions,
            "completed_actions": completed_actions,
            "failed_actions": failed_actions,
            "attention_count": len(attention),
            "daily_execution_completed": daily_execution["successful_count"],
            "daily_execution_outstanding": daily_execution["outstanding_count"],
            "social_media": social_overview,
        },
        "attention": attention,
        "activities": sorted(classified, key=lambda row: row["created_at"]),
    }
    snapshot["html"] = render_report_html(snapshot)
    snapshot["text"] = render_report_text(snapshot)
    snapshot["csv_filename"] = (
        f"sports-cave-daily-staff-report-{period.report_date.isoformat()}"
        f"{'-test' if is_test else ''}.csv"
    )
    snapshot["csv_content"] = render_report_csv(snapshot)
    return snapshot


def _period_label(snapshot):
    start = snapshot["covered_start_local"].strftime("%I:%M %p").lstrip("0")
    end = snapshot["covered_end_local"].strftime("%I:%M %p %Z").lstrip("0")
    return f"{start} to {end} (Australia/Sydney)"


def _html_metric(label, value):
    return (
        '<td style="width:50%;padding:10px;border:1px solid #e6e2d9;">'
        f'<div style="font-size:12px;color:#6b685f;">{html.escape(str(label))}</div>'
        f'<div style="font-size:22px;font-weight:700;color:#171717;">{html.escape(str(value))}</div>'
        "</td>"
    )


def _daily_execution_html(daily):
    if not daily or not daily.get("exists"):
        return (
            '<div style="margin-top:14px;padding:12px;background:#f7f5ef;border-left:3px solid #b58a2a;">'
            "<strong>Daily Execution</strong><br>No Daily Execution sheet was created for this date."
            "</div>"
        )
    task_items = []
    for task in daily.get("tasks") or []:
        marker = (
            "Could not finish"
            if task.get("status") == "couldnt_finish"
            else ("Complete" if task["completed"] else "Outstanding")
        )
        notes = f" - {html.escape(task['notes'])}" if task.get("notes") else ""
        task_items.append(
            f"<li><strong>{html.escape(task['kind'])}:</strong> "
            f"{html.escape(task['task'])} ({marker}){notes}</li>"
        )
    return (
        '<div style="margin-top:14px;padding:12px;background:#f7f5ef;border-left:3px solid #b58a2a;">'
        "<strong>Daily Execution</strong>"
        f"<div style=\"margin-top:4px;\">{daily['completed_count']} of {daily['task_count']} tasks closed "
        f"({daily['completion_percentage']}%)</div>"
        f"<ul style=\"margin:8px 0 0 18px;padding:0;\">{''.join(task_items) or '<li>No tasks were planned.</li>'}</ul>"
        "</div>"
    )


def _social_media_html(social):
    if not social:
        return ""
    status = str(social.get("plan_status") or "not_started").replace("_", " ").title()
    platforms = ", ".join(social.get("platforms") or []) or "None"
    detail_lines = [
        f"Plan: {status}",
        (
            f"MIPs: {int(social.get('mips_completed') or 0)} complete / "
            f"{int(social.get('mips_outstanding') or 0)} outstanding"
        ),
        (
            f"Posts: {int(social.get('posts_logged') or 0)} logged / "
            f"{int(social.get('posts_live') or 0)} live"
        ),
        f"Platforms live: {platforms}",
        f"Execution score: {float(social.get('score') or 0):.1f}/10",
    ]
    notes = []
    for label, key in (
        ("Today's test", "improvement_test"),
        ("Learning", "main_learning"),
        ("Blocker", "blockers"),
    ):
        if social.get(key):
            notes.append(
                f"<div><strong>{label}:</strong> "
                f"{html.escape(sanitize_report_text(social[key], limit=220))}</div>"
            )
    weekly = str(social.get("weekly_headline") or "").strip()
    if weekly:
        notes.append(
            f"<div><strong>Latest weekly check-in:</strong> "
            f"{html.escape(weekly)}</div>"
        )
    return (
        '<div style="margin-top:14px;padding:12px;background:#f7f5ef;border-left:3px solid #b58a2a;">'
        "<strong>Social Media</strong>"
        f'<div style="margin-top:5px;font-size:13px;">{" &nbsp; | &nbsp; ".join(html.escape(line) for line in detail_lines)}</div>'
        f'<div style="margin-top:7px;font-size:13px;">{"".join(notes)}</div>'
        "</div>"
    )


def render_report_html(snapshot):
    summary = snapshot["summary"]
    attention_html = ""
    if snapshot.get("attention"):
        attention_items = "".join(
            f"<li>{html.escape(item)}</li>" for item in snapshot["attention"]
        )
        attention_html = (
            '<div style="margin:18px 0;padding:14px;background:#fff7ed;border:1px solid #e8c58f;">'
            '<div style="font-weight:700;color:#7a3d00;">Attention required</div>'
            f'<ul style="margin:8px 0 0 18px;padding:0;color:#4e3422;">{attention_items}</ul>'
            "</div>"
        )

    staff_sections = []
    for member in snapshot["staff"]:
        location = " / ".join(
            value for value in (member.get("country"), member.get("timezone")) if value
        )
        if member["work_lines"]:
            work = "".join(
                f"<li>{html.escape(line['label'])}</li>"
                for line in member["work_lines"]
            )
        else:
            work = "<li>No recorded activity for this report period</li>"
        failure_line = (
            f'<div style="margin-top:8px;color:#9a3412;font-weight:600;">'
            f"{member['failed_actions']} action"
            f"{'s' if member['failed_actions'] != 1 else ''} require attention.</div>"
            if member["failed_actions"]
            else ""
        )
        daily_html = _daily_execution_html(member.get("daily_execution")) if member["is_owner"] else ""
        social_html = _social_media_html(member.get("social_media"))
        staff_sections.append(
            '<div style="margin:14px 0;padding:16px;border:1px solid #dedbd3;background:#ffffff;">'
            f'<div style="font-size:18px;font-weight:700;color:#171717;">{html.escape(member["display_name"])}</div>'
            f'<div style="font-size:12px;color:#6b685f;margin-top:2px;">'
            f'{html.escape(member["role"].title())}'
            f'{" - " + html.escape(location) if location else ""}</div>'
            '<div style="margin-top:10px;font-size:13px;color:#3f3f3f;">'
            f'{member["total_actions"]} meaningful actions &nbsp; '
            f'{member["completed_actions"]} completed &nbsp; '
            f'{member["failed_actions"]} failed</div>'
            f'<ul style="margin:10px 0 0 18px;padding:0;color:#292929;">{work}</ul>'
            f"{failure_line}{daily_html}{social_html}</div>"
        )

    test_banner = (
        '<div style="padding:10px;background:#fff4cc;color:#6b4b00;font-weight:700;text-align:center;">'
        "TEST EMAIL - this does not mark the production daily report as sent"
        "</div>"
        if snapshot.get("is_test")
        else ""
    )
    return (
        '<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1"></head>'
        '<body style="margin:0;background:#f4f2ed;font-family:Arial,Helvetica,sans-serif;color:#171717;">'
        '<div style="max-width:680px;margin:0 auto;background:#f4f2ed;">'
        f"{test_banner}"
        '<div style="background:#111111;color:#ffffff;padding:22px 20px;border-bottom:3px solid #b58a2a;">'
        '<div style="font-size:12px;letter-spacing:1px;color:#d8b75f;">SPORTS CAVE OS</div>'
        '<div style="font-size:24px;font-weight:700;margin-top:4px;">Daily staff report</div>'
        f'<div style="font-size:13px;color:#dedede;margin-top:6px;">'
        f'{html.escape(snapshot["report_date"])} - {html.escape(_period_label(snapshot))}</div>'
        "</div>"
        '<div style="padding:18px 14px;">'
        '<div style="font-size:18px;font-weight:700;margin-bottom:10px;">At a glance</div>'
        '<table role="presentation" style="width:100%;border-collapse:collapse;background:#ffffff;">'
        f'<tr>{_html_metric("Active staff", summary["active_staff_count"])}'
        f'{_html_metric("Staff with activity", summary["staff_with_activity"])}</tr>'
        f'<tr>{_html_metric("Meaningful actions", summary["total_actions"])}'
        f'{_html_metric("Completed actions", summary["completed_actions"])}</tr>'
        f'<tr>{_html_metric("Failures", summary["failed_actions"])}'
        f'{_html_metric("Daily Execution", f"{summary["daily_execution_completed"]} done / {summary["daily_execution_outstanding"]} open")}</tr>'
        "</table>"
        f"{attention_html}"
        '<div style="font-size:18px;font-weight:700;margin:20px 0 8px;">Staff reports</div>'
        f"{''.join(staff_sections)}"
        '<div style="font-size:11px;color:#77736b;margin:18px 4px 8px;">'
        "Report period is based on Australia/Sydney. The attached CSV contains the detailed meaningful activity records."
        "</div></div></div></body></html>"
    )


def render_report_text(snapshot):
    summary = snapshot["summary"]
    lines = [
        "SPORTS CAVE OS - DAILY STAFF REPORT",
        f"Report date: {snapshot['report_date']}",
        f"Covered period: {_period_label(snapshot)}",
        f"Active staff accounts: {summary['active_staff_count']}",
        f"Staff with activity: {summary['staff_with_activity']}",
        f"Meaningful actions: {summary['total_actions']}",
        f"Completed actions: {summary['completed_actions']}",
        f"Failures: {summary['failed_actions']}",
        (
            "Daily Execution: "
            f"{summary['daily_execution_completed']} complete / "
            f"{summary['daily_execution_outstanding']} outstanding"
        ),
    ]
    if snapshot.get("is_test"):
        lines.insert(0, "TEST EMAIL - production delivery is unchanged")
    if snapshot.get("attention"):
        lines.extend(["", "ATTENTION REQUIRED"])
        lines.extend(f"- {item}" for item in snapshot["attention"])
    lines.extend(["", "STAFF REPORTS"])
    for member in snapshot["staff"]:
        lines.extend(
            [
                "",
                f"{member['display_name']} - {member['role'].title()}",
                (
                    f"{member['total_actions']} meaningful actions; "
                    f"{member['completed_actions']} completed; "
                    f"{member['failed_actions']} failed"
                ),
            ]
        )
        if member["work_lines"]:
            lines.extend(f"- {item['label']}" for item in member["work_lines"])
        else:
            lines.append("- No recorded activity for this report period")
        if member["is_owner"]:
            daily = member.get("daily_execution") or {}
            lines.append("Daily Execution:")
            if not daily.get("exists"):
                lines.append("- No Daily Execution sheet was created for this date.")
            else:
                lines.append(
                    f"- {daily['completed_count']} of {daily['task_count']} tasks closed "
                    f"({daily['completion_percentage']}%)"
                )
                for task in daily.get("tasks") or []:
                    marker = (
                        "Could not finish"
                        if task.get("status") == "couldnt_finish"
                        else ("Complete" if task["completed"] else "Outstanding")
                    )
                    lines.append(f"- {task['kind']}: {task['task']} ({marker})")
        social = member.get("social_media") or {}
        if social:
            lines.extend(
                [
                    "Social Media:",
                    f"- Plan: {str(social.get('plan_status') or 'not_started').replace('_', ' ').title()}",
                    (
                        f"- MIPs: {int(social.get('mips_completed') or 0)} complete / "
                        f"{int(social.get('mips_outstanding') or 0)} outstanding"
                    ),
                    (
                        f"- Posts: {int(social.get('posts_logged') or 0)} logged / "
                        f"{int(social.get('posts_live') or 0)} live"
                    ),
                    f"- Platforms live: {', '.join(social.get('platforms') or []) or 'None'}",
                    f"- Execution score: {float(social.get('score') or 0):.1f}/10",
                ]
            )
            for label, key in (
                ("Today's test", "improvement_test"),
                ("Learning", "main_learning"),
                ("Blocker", "blockers"),
                ("Latest weekly check-in", "weekly_headline"),
            ):
                if social.get(key):
                    lines.append(
                        f"- {label}: {sanitize_report_text(social[key], limit=220)}"
                    )
    lines.extend(
        [
            "",
            "The report period is based on Australia/Sydney.",
            "See the attached CSV for detailed meaningful activity records.",
        ]
    )
    return "\n".join(lines)


def csv_safe_cell(value):
    if isinstance(value, datetime):
        text_value = value.isoformat()
    else:
        text_value = sanitize_report_text(value, limit=2000)
    if text_value.startswith(("=", "+", "-", "@")):
        return "'" + text_value
    return text_value


def render_report_csv(snapshot):
    fieldnames = (
        "Record Type",
        "Timestamp UTC",
        "Local Timestamp",
        "Staff Member",
        "Role",
        "Action",
        "Page/Area",
        "Item or Product",
        "Details",
        "Result/Status",
    )
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    staff_by_id = {member["id"]: member for member in snapshot["staff"]}
    for activity in snapshot["activities"]:
        member = staff_by_id.get(activity.get("staff_id")) or {}
        timezone_name = member.get("timezone") or REPORT_TIMEZONE
        try:
            local_timestamp = activity["created_at"].astimezone(ZoneInfo(timezone_name))
        except Exception:
            local_timestamp = activity["created_at"].astimezone(SYDNEY_TZ)
        row = {
            "Record Type": "Activity",
            "Timestamp UTC": activity["created_at"],
            "Local Timestamp": local_timestamp,
            "Staff Member": member.get("display_name") or activity.get("staff_name") or "",
            "Role": (member.get("role") or activity.get("staff_role") or "").title(),
            "Action": activity.get("action") or "",
            "Page/Area": activity.get("page") or "",
            "Item or Product": activity.get("item") or "",
            "Details": activity.get("details") or "",
            "Result/Status": activity.get("status") or "",
        }
        writer.writerow({key: csv_safe_cell(value) for key, value in row.items()})
    owner = next((member for member in snapshot["staff"] if member.get("is_owner")), None)
    daily = snapshot.get("daily_execution") or {}
    if owner and daily.get("exists"):
        for task in daily.get("tasks") or []:
            row = {
                "Record Type": f"Daily Execution {task['kind']}",
                "Timestamp UTC": snapshot["covered_end"],
                "Local Timestamp": snapshot["covered_end_local"],
                "Staff Member": owner["display_name"],
                "Role": owner["role"].title(),
                "Action": "daily_execution_task",
                "Page/Area": "Daily Execution",
                "Item or Product": task["task"],
                "Details": task.get("notes") or "",
                "Result/Status": (
                    "could not finish"
                    if task.get("status") == "couldnt_finish"
                    else ("complete" if task["completed"] else task.get("status") or "outstanding")
                ),
            }
            writer.writerow({key: csv_safe_cell(value) for key, value in row.items()})
    return output.getvalue()


def deterministic_idempotency_key(snapshot, *, nonce=""):
    identity = "|".join(
        (
            snapshot.get("purpose") or REPORT_PURPOSE,
            snapshot.get("report_date") or "",
            os_accounts.normalise_login(snapshot.get("recipient")),
            "test" if snapshot.get("is_test") else "production",
            str(nonce or ""),
        )
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    prefix = "sports-cave-test" if snapshot.get("is_test") else "sports-cave-daily"
    return f"{prefix}/{snapshot.get('report_date')}/{digest[:32]}"


def collect_report_snapshot(
    *,
    period,
    account_store=None,
    backend=None,
    recipient="",
    is_test=False,
    owner_email=None,
):
    if account_store is None:
        account_store = os_accounts.DEFAULT_STORE
    if backend is None:
        import supabase_backend as backend

    accounts = account_store.list_users()
    if hasattr(backend, "list_human_work_events"):
        try:
            activity_rows = [
                human_work.event_to_activity_row(row)
                for row in backend.list_human_work_events(
                    start_at=period.start_utc,
                    end_at=period.end_utc,
                    limit=None,
                )
            ]
        except Exception:
            activity_rows = backend.list_activity_logs(
                start_at=period.start_utc,
                end_at=period.end_utc,
                limit=None,
            )
    else:
        activity_rows = backend.list_activity_logs(
            start_at=period.start_utc,
            end_at=period.end_utc,
            limit=None,
        )
    owner_email = (
        os_accounts.reporting_owner_email()
        if owner_email is None
        else os_accounts.normalise_login(owner_email)
    )
    owner = next(
        (
            account
            for account in accounts
            if bool(account.get("is_active", True))
            and str(account.get("role") or "").casefold() == os_accounts.ROLE_ADMIN
            and os_accounts.normalise_login(account.get("email")) == owner_email
        ),
        None,
    )
    daily_sheet = (
        backend.get_daily_execution_sheet(owner.get("id"), period.report_date.isoformat())
        if owner
        else {}
    )
    try:
        social_summaries = social_media_store.collect_reporting_social_summaries(
            accounts,
            period.report_date,
        )
    except Exception:
        social_summaries = {}
    return build_report_snapshot(
        period=period,
        accounts=accounts,
        activity_rows=activity_rows,
        daily_execution_sheet=daily_sheet,
        social_summaries=social_summaries,
        owner_email=owner_email,
        recipient=recipient,
        is_test=is_test,
    )
