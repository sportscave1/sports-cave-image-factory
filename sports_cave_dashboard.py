from datetime import date, datetime, time, timedelta, timezone
from collections import Counter
import json
from pathlib import Path
import re
from time import monotonic

import sports_sales_calendar


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
SPORTING_CALENDAR_PATH = DATA_DIR / "sporting_calendar.json"
COLLECTIONS_TASK_GROUP = "Collections to update"
DESIGN_TASK_GROUP = "New designs to complete"
UPLOAD_TASK_GROUP = "New products to be uploaded (in designs offline not uploaded folder)"
VARIANTS_TASK_GROUP = "Existing product updated — variants working"
LEGACY_UPLOAD_TASK_GROUPS = ("New product uploaded — set to Draft",)
MOCKUP_SCOPE_WEBSITE = "website mockups"
MOCKUP_SCOPE_ALL = "all mockups"
MOCKUP_SCOPE_OPTIONS = (MOCKUP_SCOPE_WEBSITE, MOCKUP_SCOPE_ALL)
TASK_GROUPS = (
    COLLECTIONS_TASK_GROUP,
    DESIGN_TASK_GROUP,
    UPLOAD_TASK_GROUP,
    VARIANTS_TASK_GROUP,
)
REGIONS = ("Australia", "USA", "UK", "Canada", "New Zealand")
ACTIVITY_LOG_LIMIT = 200
TASK_CACHE_TTL_SECONDS = 15
ACTIVITY_CACHE_TTL_SECONDS = 20
CALENDAR_CACHE_TTL_SECONDS = 300
EDITION_PRODUCT_CACHE_TTL_SECONDS = 300
DAILY_EXECUTION_CACHE_TTL_SECONDS = 15
DEFAULT_UPCOMING_DAYS = 60
ACTIVITY_VIEW_TODAY = "Today"
ACTIVITY_VIEW_LAST_7_DAYS = "Last 7 days"
ACTIVITY_VIEW_MONTH = "Month"
ACTIVITY_VIEW_ALL_TIME = "All time"
ACTIVITY_VIEWS = (
    ACTIVITY_VIEW_TODAY,
    ACTIVITY_VIEW_LAST_7_DAYS,
    ACTIVITY_VIEW_MONTH,
    ACTIVITY_VIEW_ALL_TIME,
)
ACTIVITY_VIEW_LIMITS = {
    ACTIVITY_VIEW_TODAY: 50,
    ACTIVITY_VIEW_LAST_7_DAYS: 100,
    ACTIVITY_VIEW_MONTH: 150,
    ACTIVITY_VIEW_ALL_TIME: 200,
}
MOCKUP_ACTIVITY_GROUP_WINDOW = timedelta(minutes=45)
MOCKUP_ACTIVITY_GROUP_ACTIONS = {"mockup_uploaded", "mockup_made"}
_TASK_CACHE = {}
_ACTIVITY_CACHE = {}
_CALENDAR_CACHE = {}
_EDITION_PRODUCT_CACHE = {}
_DAILY_EXECUTION_CACHE = {}


class DashboardStorageError(RuntimeError):
    pass


def utc_now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_json(path, fallback):
    path = Path(path)
    if not path.exists():
        return dict(fallback)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(fallback)
    return data if isinstance(data, dict) else dict(fallback)


def _copy_rows(rows):
    return [dict(row) for row in rows or []]


def _cache_get(cache, key):
    cached = cache.get(key)
    if not cached:
        return None
    expires_at, value = cached
    if expires_at < monotonic():
        cache.pop(key, None)
        return None
    return _copy_rows(value)


def _cache_set(cache, key, value, ttl_seconds):
    cache[key] = (monotonic() + ttl_seconds, _copy_rows(value))
    return _copy_rows(value)


def clear_task_cache():
    _TASK_CACHE.clear()


def clear_activity_cache():
    _ACTIVITY_CACHE.clear()


def clear_daily_execution_cache(user_id=None, sheet_dates=None):
    clean_user_id = str(user_id or "").strip()
    clean_dates = {
        value.isoformat() if isinstance(value, date) else str(value or "").strip()
        for value in (sheet_dates or [])
    }
    if not clean_user_id and not clean_dates:
        _DAILY_EXECUTION_CACHE.clear()
        return
    for key in list(_DAILY_EXECUTION_CACHE):
        key_text = tuple(str(part or "") for part in (key if isinstance(key, tuple) else (key,)))
        if clean_user_id and clean_user_id not in key_text:
            continue
        if not clean_dates:
            _DAILY_EXECUTION_CACHE.pop(key, None)
            continue
        kind = key_text[0] if key_text else ""
        affected = False
        if kind == "daily_execution" and len(key_text) > 2:
            affected = key_text[2] in clean_dates
        elif kind == "daily_home" and len(key_text) > 2:
            home_date = date.fromisoformat(key_text[2])
            affected = any(value in {home_date.isoformat(), (home_date + timedelta(days=1)).isoformat()} for value in clean_dates)
        elif kind == "daily_week" and len(key_text) > 3:
            week_start = date.fromisoformat(key_text[2])
            week_end = date.fromisoformat(key_text[3])
            affected = any(week_start <= date.fromisoformat(value) <= week_end for value in clean_dates)
        elif kind == "daily_archive_detail":
            affected = True
        if affected:
            _DAILY_EXECUTION_CACHE.pop(key, None)


def clear_calendar_cache():
    _CALENDAR_CACHE.clear()


def clear_edition_product_cache():
    _EDITION_PRODUCT_CACHE.clear()


def clear_dashboard_caches():
    clear_task_cache()
    clear_activity_cache()
    clear_daily_execution_cache()
    clear_edition_product_cache()


def get_supabase_backend():
    try:
        import supabase_backend
    except Exception as error:
        raise DashboardStorageError("Dashboard saving is unavailable right now.") from error
    if not supabase_backend.is_configured():
        raise DashboardStorageError("Dashboard saving is not connected right now.")
    return supabase_backend


def _storage_error(error):
    if isinstance(error, DashboardStorageError):
        return str(error)
    return "Dashboard saving is unavailable right now."


def _normalise_task(task):
    task = dict(task or {})
    title = str(task.get("title") or task.get("text") or "").strip()
    section = normalize_task_category(task.get("section") or task.get("category"))
    return {
        **task,
        "id": str(task.get("id") or ""),
        "text": title,
        "title": title,
        "category": section,
        "section": section,
    }


def normalize_task_category(category):
    category = str(category or "").strip()
    if category in LEGACY_UPLOAD_TASK_GROUPS:
        return UPLOAD_TASK_GROUP
    return category if category in TASK_GROUPS else TASK_GROUPS[0]


def normalize_mockup_scope(value):
    text = str(value or "").replace("_", " ").strip().casefold()
    if text in {"all", "all mockup", "all mockups"}:
        return MOCKUP_SCOPE_ALL
    if text in {"website", "web", "website mockup", "website mockups", "just website mockups"}:
        return MOCKUP_SCOPE_WEBSITE
    return MOCKUP_SCOPE_WEBSITE


def upload_task_title_for_design(task_text, mockup_scope):
    title = " ".join(str(task_text or "").split()).strip()
    if not title:
        title = "New design"
    return f"{title} ({normalize_mockup_scope(mockup_scope)})"


def list_tasks(status="open"):
    cache_key = ("tasks", str(status or "open").strip().casefold())
    cached = _cache_get(_TASK_CACHE, cache_key)
    if cached is not None:
        return [_normalise_task(task) for task in cached]
    try:
        backend = get_supabase_backend()
        tasks = [_normalise_task(task) for task in backend.list_dashboard_tasks(status=status)]
        return _cache_set(_TASK_CACHE, cache_key, tasks, TASK_CACHE_TTL_SECONDS)
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error


def add_task(text, category, *, metadata=None):
    task_text = str(text or "").strip()
    if not task_text:
        raise ValueError("Task text is required.")
    try:
        backend = get_supabase_backend()
        from activity_log import get_activity_actor

        task = _normalise_task(
            backend.create_dashboard_task(
                task_text,
                normalize_task_category(category),
                metadata=metadata or {},
                actor=get_activity_actor(),
            )
        )
        clear_task_cache()
        clear_activity_cache()
        return task
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error


def complete_task(task_id, *, metadata=None):
    try:
        backend = get_supabase_backend()
        from activity_log import get_activity_actor

        completed = backend.complete_dashboard_task(
            task_id,
            metadata=metadata or {},
            completed_by=get_activity_actor(),
            actor=get_activity_actor(),
        )
        clear_task_cache()
        clear_activity_cache()
        return _normalise_task(completed) if completed else None
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error


def complete_design_task_for_upload(task_id, task_text, mockup_scope, *, metadata=None):
    scope = normalize_mockup_scope(mockup_scope)
    completed = complete_task(
        task_id,
        metadata={
            **(metadata or {}),
            "next_task_section": UPLOAD_TASK_GROUP,
            "mockup_scope": scope,
        },
    )
    if completed is None:
        return None
    upload_task = add_task(
        upload_task_title_for_design(task_text or completed.get("text") or completed.get("title"), scope),
        UPLOAD_TASK_GROUP,
        metadata={
            "source_task_id": str(task_id or ""),
            "source_task_section": DESIGN_TASK_GROUP,
            "mockup_scope": scope,
        },
    )
    return {"completed": completed, "upload_task": upload_task}


DAILY_EXECUTION_TITLE = "Daily Task Execution Sheet - The 5 Million Dollar Man"
DAILY_EXECUTION_STATUS_PLANNED = "planned"
DAILY_EXECUTION_STATUS_ACTIVE = "active"
DAILY_EXECUTION_STATUS_COMPLETED = "completed"
DAILY_EXECUTION_STATUS_REVIEWED = "reviewed"
DAILY_EXECUTION_STATUS_ARCHIVED = "archived"
DAILY_EXECUTION_REVIEWED_STATUSES = (
    DAILY_EXECUTION_STATUS_COMPLETED,
    DAILY_EXECUTION_STATUS_REVIEWED,
    DAILY_EXECUTION_STATUS_ARCHIVED,
)
DAILY_TASK_STATUS_DONE = "done"
DAILY_TASK_STATUS_COULDNT_FINISH = "couldnt_finish"
DAILY_TASK_FINISHED_STATUSES = (DAILY_TASK_STATUS_DONE, DAILY_TASK_STATUS_COULDNT_FINISH)
DAILY_RATING_FIELDS = (
    "Focus",
    "Attention",
    "Flow Awareness",
    "Emotional Control",
    "Execution",
    "Vision Alignment",
    "Overall Score",
)


def _blank_top_tasks():
    return [
        {"task": "", "why": "", "time_blocked": "", "completed": False, "status": ""}
        for _ in range(3)
    ]


def _blank_additional_items(count=1):
    return [
        {"task": "", "details": "", "time_blocked": "", "completed": False, "status": ""}
        for _ in range(count)
    ]


def _coerce_daily_item_rows(items):
    if items is None:
        return []
    if isinstance(items, str):
        text = items.strip()
        if not text:
            return []
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            return [{"task": text}]
        return _coerce_daily_item_rows(decoded)
    if isinstance(items, dict):
        return [items]
    if isinstance(items, (list, tuple)):
        rows = []
        for item in items:
            if isinstance(item, dict):
                rows.append(item)
            elif isinstance(item, str):
                text = item.strip()
                if text:
                    rows.append({"task": text})
        return rows
    return []


def _normalise_top_tasks(items):
    rows = []
    for item in _coerce_daily_item_rows(items)[:3]:
        item = dict(item or {})
        status = _compact_text(item.get("status") or "").casefold()
        if status not in DAILY_TASK_FINISHED_STATUSES:
            status = DAILY_TASK_STATUS_DONE if bool(item.get("completed")) else ""
        completed = status in DAILY_TASK_FINISHED_STATUSES
        rows.append(
            {
                "task": _compact_text(item.get("task") or item.get("title") or ""),
                "why": _compact_text(item.get("why") or item.get("outcome") or item.get("details") or ""),
                "time_blocked": _compact_text(item.get("time_blocked") or item.get("time") or ""),
                "completed": completed,
                "status": status,
                "completed_at": item.get("completed_at"),
                "carried_from": _compact_text(item.get("carried_from") or ""),
            }
        )
    while len(rows) < 3:
        rows.append({"task": "", "why": "", "time_blocked": "", "completed": False, "status": ""})
    return rows


def _normalise_daily_task_status(item):
    item = dict(item or {})
    status = _compact_text(item.get("status") or "").casefold()
    if status not in DAILY_TASK_FINISHED_STATUSES:
        status = DAILY_TASK_STATUS_DONE if bool(item.get("completed")) else ""
    return status


def _normalise_additional_items(items, *, include_blank=True):
    rows = []
    for item in _coerce_daily_item_rows(items):
        item = dict(item or {})
        status = _normalise_daily_task_status(item)
        completed = status in DAILY_TASK_FINISHED_STATUSES
        row = {
            "task": _compact_text(item.get("task") or item.get("note") or item.get("title") or ""),
            "details": _compact_text(item.get("details") or item.get("why") or item.get("outcome") or ""),
            "time_blocked": _compact_text(item.get("time_blocked") or item.get("time") or item.get("time_allocated") or ""),
            "completed": completed,
            "status": status,
            "completed_at": item.get("completed_at"),
            "carried_from": _compact_text(item.get("carried_from") or ""),
        }
        if _daily_additional_item_has_content(row) or include_blank:
            rows.append(row)
    if include_blank:
        rows = [row for row in rows if _daily_additional_item_has_content(row)]
        rows.append(_blank_additional_items(1)[0])
    return rows


def _daily_additional_item_has_content(item):
    if not isinstance(item, dict):
        item = _coerce_daily_item_rows(item)
        item = item[0] if item else {}
    return bool(
        _compact_text(item.get("task") or "")
        or _compact_text(item.get("details") or "")
        or _compact_text(item.get("time_blocked") or "")
    )


def _normalise_additional_items_for_save(items):
    rows = []
    for item in _normalise_additional_items(items, include_blank=False):
        if _daily_additional_item_has_content(item):
            rows.append(
                {
                    "task": item.get("task") or "",
                    "details": item.get("details") or "",
                    "time_blocked": item.get("time_blocked") or "",
                    "completed": daily_execution_task_finished(item),
                    "status": item.get("status") or "",
                    "completed_at": item.get("completed_at"),
                    "carried_from": item.get("carried_from") or "",
                }
            )
    return rows


def _normalise_daily_sheet(sheet):
    sheet = dict(sheet or {})
    if not sheet:
        return {}
    top_tasks = _normalise_top_tasks(sheet.get("top_tasks") or [])
    additional_items = _normalise_additional_items(sheet.get("additional_items") or [])
    no_grey_zone = sheet.get("no_grey_zone") if isinstance(sheet.get("no_grey_zone"), dict) else {}
    ratings = sheet.get("ratings") if isinstance(sheet.get("ratings"), dict) else {}
    planning_data = sheet.get("planning_data") if isinstance(sheet.get("planning_data"), dict) else {}
    review_data = sheet.get("review_data") if isinstance(sheet.get("review_data"), dict) else {}
    archived_snapshot = sheet.get("archived_snapshot") if isinstance(sheet.get("archived_snapshot"), dict) else {}
    return {
        **sheet,
        "id": str(sheet.get("id") or ""),
        "user_id": str(sheet.get("user_id") or ""),
        "user_name": _compact_text(sheet.get("user_name") or ""),
        "sheet_date": str(sheet.get("sheet_date") or ""),
        "day_name": _compact_text(sheet.get("day_name") or ""),
        "timezone": _compact_text(sheet.get("timezone") or "Australia/Sydney"),
        "status": _compact_text(sheet.get("status") or DAILY_EXECUTION_STATUS_ACTIVE),
        "top_tasks": top_tasks,
        "additional_items": additional_items,
        "no_grey_zone": no_grey_zone,
        "ratings": ratings,
        "planning_data": planning_data,
        "review_data": review_data,
        "archived_snapshot": archived_snapshot,
        "daily_summary": str(sheet.get("daily_summary") or ""),
        "tomorrow_intention": str(sheet.get("tomorrow_intention") or ""),
        "generated_prompt": str(sheet.get("generated_prompt") or ""),
        "activated_at": sheet.get("activated_at"),
        "archived_at": sheet.get("archived_at"),
    }


def daily_execution_user_id(user):
    return str((user or {}).get("id") or "").strip()


def daily_execution_user_name(user):
    return _compact_text(
        (user or {}).get("display_name")
        or (user or {}).get("email")
        or (user or {}).get("username")
        or "Nathan"
    )


def get_daily_execution_sheet(user, sheet_date):
    user_id = daily_execution_user_id(user)
    clean_date = sheet_date.isoformat() if isinstance(sheet_date, date) else str(sheet_date or "")
    cache_key = ("daily_execution", user_id, clean_date)
    cached = _cache_get(_DAILY_EXECUTION_CACHE, cache_key)
    if cached is not None:
        return cached[0] if cached else {}
    try:
        backend = get_supabase_backend()
        sheet = _normalise_daily_sheet(backend.get_daily_execution_sheet(user_id, clean_date))
        _cache_set(_DAILY_EXECUTION_CACHE, cache_key, [sheet] if sheet else [], DAILY_EXECUTION_CACHE_TTL_SECONDS)
        return sheet
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error


def get_daily_execution_home_sheets(user, today):
    user_id = daily_execution_user_id(user)
    clean_today = today.isoformat() if isinstance(today, date) else str(today or "")
    tomorrow = date.fromisoformat(clean_today) + timedelta(days=1)
    cache_key = ("daily_home", user_id, clean_today)
    cached = _cache_get(_DAILY_EXECUTION_CACHE, cache_key)
    if cached is not None:
        by_date = {row.get("sheet_date"): row for row in cached}
        return {
            "today": by_date.get(clean_today, {}),
            "tomorrow": by_date.get(tomorrow.isoformat(), {}),
        }
    try:
        backend = get_supabase_backend()
        if hasattr(backend, "get_daily_execution_home_sheets"):
            rows = backend.get_daily_execution_home_sheets(user_id, clean_today)
            normalised = [_normalise_daily_sheet(row) for row in rows or [] if row]
        else:
            normalised = [
                row
                for row in (
                    get_daily_execution_sheet(user, clean_today),
                    get_daily_execution_sheet(user, tomorrow),
                )
                if row
            ]
        _cache_set(_DAILY_EXECUTION_CACHE, cache_key, normalised, DAILY_EXECUTION_CACHE_TTL_SECONDS)
        by_date = {row.get("sheet_date"): row for row in normalised}
        return {
            "today": by_date.get(clean_today, {}),
            "tomorrow": by_date.get(tomorrow.isoformat(), {}),
        }
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error


def create_daily_execution_sheet(user, sheet_date, timezone_name, *, status=None):
    clean_date = sheet_date.isoformat() if isinstance(sheet_date, date) else str(sheet_date or "")
    try:
        backend = get_supabase_backend()
        from activity_log import get_activity_actor

        kwargs = {
            "user_id": daily_execution_user_id(user),
            "user_name": daily_execution_user_name(user),
            "sheet_date": clean_date,
            "timezone_name": timezone_name,
            "actor": get_activity_actor(),
        }
        if status is not None:
            kwargs["status"] = status
        try:
            raw_sheet = backend.create_daily_execution_sheet(**kwargs)
        except TypeError:
            kwargs.pop("status", None)
            raw_sheet = backend.create_daily_execution_sheet(**kwargs)
        sheet = _normalise_daily_sheet(raw_sheet)
        clear_daily_execution_cache(daily_execution_user_id(user))
        clear_activity_cache()
        return sheet
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error


def save_daily_execution_top_tasks(sheet_id, top_tasks):
    try:
        backend = get_supabase_backend()
        sheet = _normalise_daily_sheet(backend.update_daily_execution_top_tasks(sheet_id, _normalise_top_tasks(top_tasks)))
        clear_daily_execution_cache()
        return sheet
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error


def save_daily_execution_tasks(sheet_id, top_tasks, additional_items, *, user=None):
    try:
        backend = get_supabase_backend()
        sheet = _normalise_daily_sheet(
            backend.update_daily_execution_top_tasks(
                sheet_id,
                _normalise_top_tasks(top_tasks),
                _normalise_additional_items_for_save(additional_items),
            )
        )
        clear_daily_execution_cache(daily_execution_user_id(user) if user else None)
        return sheet
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error


def set_daily_execution_mip_completed(sheet_id, index, completed):
    try:
        backend = get_supabase_backend()
        sheet = _normalise_daily_sheet(backend.set_daily_execution_mip_completed(sheet_id, index, bool(completed)))
        clear_daily_execution_cache()
        clear_activity_cache()
        return sheet
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error


def complete_daily_execution_review(sheet_id, review_payload, *, user=None):
    try:
        backend = get_supabase_backend()
        from activity_log import get_activity_actor

        kwargs = {"actor": get_activity_actor()}
        if user:
            kwargs["user_id"] = daily_execution_user_id(user)
        try:
            raw_sheet = backend.complete_daily_execution_review(sheet_id, review_payload or {}, **kwargs)
        except TypeError:
            kwargs.pop("user_id", None)
            raw_sheet = backend.complete_daily_execution_review(sheet_id, review_payload or {}, **kwargs)
        sheet = _normalise_daily_sheet(raw_sheet)
        clear_daily_execution_cache(daily_execution_user_id(user) if user else None)
        clear_activity_cache()
        return sheet
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error


def save_daily_execution_prompt(sheet_id, prompt):
    try:
        backend = get_supabase_backend()
        sheet = _normalise_daily_sheet(backend.update_daily_execution_prompt(sheet_id, str(prompt or "")))
        clear_daily_execution_cache()
        return sheet
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error


def list_daily_execution_sheets(user, start_date, end_date, *, limit=10):
    try:
        backend = get_supabase_backend()
        rows = backend.list_daily_execution_sheets(
            daily_execution_user_id(user),
            start_date.isoformat() if isinstance(start_date, date) else str(start_date or ""),
            end_date.isoformat() if isinstance(end_date, date) else str(end_date or ""),
            limit=limit,
        )
        return [_normalise_daily_sheet(row) for row in rows or []]
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error


def save_daily_execution_plan(
    user,
    sheet_date,
    timezone_name,
    top_tasks,
    additional_items,
    planning_data,
    *,
    archive_sheet_id=None,
):
    clean_date = sheet_date.isoformat() if isinstance(sheet_date, date) else str(sheet_date or "")
    user_id = daily_execution_user_id(user)
    try:
        backend = get_supabase_backend()
        from activity_log import get_activity_actor

        if hasattr(backend, "save_daily_execution_plan"):
            raw = backend.save_daily_execution_plan(
                user_id=user_id,
                user_name=daily_execution_user_name(user),
                sheet_date=clean_date,
                timezone_name=timezone_name,
                top_tasks=_normalise_top_tasks(top_tasks),
                additional_items=_normalise_additional_items_for_save(additional_items),
                planning_data=dict(planning_data or {}),
                archive_sheet_id=str(archive_sheet_id or "").strip() or None,
                actor=get_activity_actor(),
            )
        else:
            existing = get_daily_execution_sheet(user, clean_date)
            if existing:
                raw = backend.update_daily_execution_top_tasks(
                    existing.get("id"),
                    _normalise_top_tasks(top_tasks),
                    _normalise_additional_items_for_save(additional_items),
                )
            else:
                raw = backend.create_daily_execution_sheet(
                    user_id=user_id,
                    user_name=daily_execution_user_name(user),
                    sheet_date=clean_date,
                    timezone_name=timezone_name,
                    actor=get_activity_actor(),
                )
                raw = backend.update_daily_execution_top_tasks(
                    raw.get("id"),
                    _normalise_top_tasks(top_tasks),
                    _normalise_additional_items_for_save(additional_items),
                )
        affected_dates = [clean_date]
        if archive_sheet_id:
            try:
                affected_dates.append((date.fromisoformat(clean_date) - timedelta(days=1)).isoformat())
            except ValueError:
                pass
        clear_daily_execution_cache(user_id, affected_dates)
        clear_activity_cache()
        return _normalise_daily_sheet(raw)
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error


def list_daily_execution_archive_summaries(user, start_date, end_date, *, limit=8):
    user_id = daily_execution_user_id(user)
    clean_start = start_date.isoformat() if isinstance(start_date, date) else str(start_date or "")
    clean_end = end_date.isoformat() if isinstance(end_date, date) else str(end_date or "")
    cache_key = ("daily_week", user_id, clean_start, clean_end, int(limit))
    cached = _cache_get(_DAILY_EXECUTION_CACHE, cache_key)
    if cached is not None:
        return [_normalise_daily_sheet(row) for row in cached]
    try:
        backend = get_supabase_backend()
        if hasattr(backend, "list_daily_execution_archive_summaries"):
            rows = backend.list_daily_execution_archive_summaries(
                user_id,
                clean_start,
                clean_end,
                limit=limit,
            )
        else:
            rows = backend.list_daily_execution_sheets(user_id, clean_start, clean_end, limit=limit)
        normalised = [_normalise_daily_sheet(row) for row in rows or []]
        _cache_set(_DAILY_EXECUTION_CACHE, cache_key, normalised, DAILY_EXECUTION_CACHE_TTL_SECONDS)
        return normalised
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error


def get_daily_execution_archive_detail(user, sheet_id):
    user_id = daily_execution_user_id(user)
    clean_id = str(sheet_id or "").strip()
    cache_key = ("daily_archive_detail", user_id, clean_id)
    cached = _cache_get(_DAILY_EXECUTION_CACHE, cache_key)
    if cached is not None:
        return _normalise_daily_sheet(cached[0]) if cached else {}
    try:
        backend = get_supabase_backend()
        if hasattr(backend, "get_daily_execution_archive_detail"):
            row = backend.get_daily_execution_archive_detail(user_id, clean_id)
        else:
            row = {}
        normalised = _normalise_daily_sheet(row)
        _cache_set(_DAILY_EXECUTION_CACHE, cache_key, [normalised] if normalised else [], DAILY_EXECUTION_CACHE_TTL_SECONDS)
        return normalised
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error


def daily_execution_completed_count(sheet):
    return sum(1 for task in (sheet or {}).get("top_tasks") or [] if task.get("task") and daily_execution_task_finished(task))


def daily_execution_filled_task_count(sheet):
    return sum(1 for task in (sheet or {}).get("top_tasks") or [] if task.get("task"))


def daily_execution_task_finished(task):
    task = dict(task or {})
    status = _compact_text(task.get("status") or "").casefold()
    return status in DAILY_TASK_FINISHED_STATUSES or bool(task.get("completed"))


def daily_execution_all_tasks_complete(sheet):
    return daily_execution_filled_task_count(sheet) == 3 and daily_execution_completed_count(sheet) == 3


def daily_execution_all_mips_complete(sheet):
    return daily_execution_all_tasks_complete(sheet)


def daily_execution_review_complete(sheet):
    return str((sheet or {}).get("status") or "").strip().casefold() in DAILY_EXECUTION_REVIEWED_STATUSES


def daily_execution_unfinished_tasks(sheet):
    rows = []
    for source, items in (("mip", (sheet or {}).get("top_tasks") or []), ("other", (sheet or {}).get("additional_items") or [])):
        for index, item in enumerate(items):
            item = dict(item or {})
            if item.get("task") and _normalise_daily_task_status(item) == DAILY_TASK_STATUS_COULDNT_FINISH:
                rows.append(
                    {
                        "key": f"{source}:{index}:{_compact_text(item.get('task'))}",
                        "task": _compact_text(item.get("task") or ""),
                        "details": _compact_text(item.get("why") or item.get("details") or ""),
                        "time_blocked": _compact_text(item.get("time_blocked") or ""),
                        "source": source,
                    }
                )
    return rows


def daily_execution_week_bounds(anchor_date):
    day = anchor_date if isinstance(anchor_date, date) else date.fromisoformat(str(anchor_date))
    start = day - timedelta(days=day.weekday())
    return start, start + timedelta(days=6)


def _planned_hours(value):
    text = _compact_text(value or "").casefold()
    if not text:
        return 0.0
    range_match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(?:am|pm)?\s*[-–]\s*(\d{1,2})(?::(\d{2}))?\s*(?:am|pm)?\b", text)
    if range_match:
        start = int(range_match.group(1)) + int(range_match.group(2) or 0) / 60
        end = int(range_match.group(3)) + int(range_match.group(4) or 0) / 60
        if end < start:
            end += 12
        return max(end - start, 0.0)
    number_match = re.search(r"(\d+(?:\.\d+)?)", text)
    if not number_match:
        return 0.0
    amount = float(number_match.group(1))
    if "min" in text or re.search(r"\b\d+(?:\.\d+)?m\b", text):
        return amount / 60
    return amount


def daily_execution_weekly_summary(sheets):
    rows = [_normalise_daily_sheet(sheet) for sheet in sheets or []]
    mip_done = 0
    mip_open = 0
    other_done = 0
    planned_hours = 0.0
    ratings = []
    reasons = []
    carried = []
    wins = []
    blockers = []
    for sheet in rows:
        for task in sheet.get("top_tasks") or []:
            if not task.get("task"):
                continue
            if _normalise_daily_task_status(task) == DAILY_TASK_STATUS_DONE:
                mip_done += 1
            else:
                mip_open += 1
            planned_hours += _planned_hours(task.get("time_blocked"))
        for task in sheet.get("additional_items") or []:
            if not _daily_additional_item_has_content(task):
                continue
            if _normalise_daily_task_status(task) == DAILY_TASK_STATUS_DONE:
                other_done += 1
            planned_hours += _planned_hours(task.get("time_blocked"))
        review = sheet.get("review_data") or {}
        no_grey = sheet.get("no_grey_zone") or {}
        reason = _compact_text(review.get("could_not_finish") or no_grey.get("avoided") or "")
        if reason:
            reasons.append(reason)
            blockers.append(reason)
        win = _compact_text(review.get("worked_well") or review.get("completed") or sheet.get("daily_summary") or "")
        if win:
            wins.append(win)
        score = (sheet.get("ratings") or {}).get("Overall Score")
        try:
            if score is not None and float(score) > 0:
                ratings.append(float(score))
        except (TypeError, ValueError):
            pass
        for item in (sheet.get("planning_data") or {}).get("carried_forward") or []:
            task_name = _compact_text((item or {}).get("task") if isinstance(item, dict) else item)
            if task_name:
                carried.append(task_name)
    reason_counts = Counter(reasons)
    carry_counts = Counter(carried)
    repeated = [name for name, count in carry_counts.most_common() if count > 1]
    return {
        "days_planned": sum(1 for sheet in rows if daily_execution_filled_task_count(sheet) or any(_daily_additional_item_has_content(item) for item in sheet.get("additional_items") or [])),
        "days_reviewed": sum(1 for sheet in rows if daily_execution_review_complete(sheet)),
        "mip_completed": mip_done,
        "mip_not_completed": mip_open,
        "other_completed": other_done,
        "planned_hours": round(planned_hours, 1),
        "unfinished_reasons": [name for name, _count in reason_counts.most_common(3)],
        "average_day_rating": round(sum(ratings) / len(ratings), 1) if ratings else 0,
        "repeated_carryovers": repeated,
        "biggest_wins": wins[:3],
        "main_blockers": blockers[:3],
        "recommended_priorities": repeated[:3] or [name for name, _count in carry_counts.most_common(3)],
    }


def daily_execution_alerts(sheet, local_now, *, user_name="Nathan"):
    alerts = []
    name = _compact_text(user_name or "Nathan")
    if not sheet:
        alerts.append("Today's execution sheet has not been planned.")
        return alerts
    filled = daily_execution_filled_task_count(sheet)
    complete = daily_execution_completed_count(sheet)
    if filled == 0:
        alerts.append("Today's list has no tasks yet.")
    if local_now.hour >= 15 and complete < 2:
        alerts.append("Past 3pm: fewer than 2/3 tasks are complete.")
    if local_now.hour >= 19 and not daily_execution_review_complete(sheet):
        alerts.append("Past 7pm: Daily Review is still open.")
    return alerts


def _sheet_summary(sheet):
    if not sheet:
        return "- No sheet found."
    lines = [f"- {sheet.get('sheet_date')}: {sheet.get('status')}"]
    for index, task in enumerate(sheet.get("top_tasks") or [], start=1):
        if task.get("task"):
            marker = task.get("status") or ("done" if task.get("completed") else "open")
            lines.append(f"  MIP Task {index}: {task.get('task')} ({marker}) - {task.get('why') or 'No details noted'}")
    other_tasks = [
        item for item in (sheet.get("additional_items") or [])
        if _daily_additional_item_has_content(item)
    ]
    for index, item in enumerate(other_tasks[:10], start=1):
        marker = item.get("status") or ("done" if item.get("completed") else "open")
        lines.append(f"  Other task {index}: {item.get('task') or item.get('details')} ({marker})")
    if sheet.get("daily_summary"):
        lines.append(f"  Summary: {_compact_text(sheet.get('daily_summary'))}")
    if sheet.get("tomorrow_intention"):
        lines.append(f"  Tomorrow: {_compact_text(sheet.get('tomorrow_intention'))}")
    no_grey = sheet.get("no_grey_zone") or {}
    avoided = _compact_text(no_grey.get("avoided") or no_grey.get("half_done") or "")
    if avoided:
        lines.append(f"  Avoided/half-done: {avoided}")
    return "\n".join(lines)


def _tasks_summary(tasks):
    lines = []
    for task in (tasks or [])[:25]:
        title = _compact_text(task.get("text") or task.get("title") or "")
        if title:
            lines.append(f"- {title} [{task.get('category') or task.get('section') or 'Task'}]")
    return "\n".join(lines) if lines else "- No open Home tasks loaded."


def _activity_summary(entries):
    lines = []
    for entry in (entries or [])[:40]:
        message = _compact_text(entry.get("message") or "")
        actor = _compact_text(entry.get("actor") or "")
        if message:
            suffix = f" ({actor})" if actor else ""
            lines.append(f"- {message}{suffix}")
    return "\n".join(lines) if lines else "- No activity loaded."


def _event_summary(events):
    lines = []
    for event in (events or [])[:20]:
        title = _compact_text(event.get("title") or "")
        if not title:
            continue
        sport = _compact_text(event.get("sport") or "Event")
        regions = ", ".join(event.get("regions") or event.get("markets") or [])
        date_label = format_event_date_range(event)
        region_text = f", {regions}" if regions else ""
        lines.append(f"- {title} ({sport}{region_text}; {date_label})")
    return "\n".join(lines) if lines else "- No upcoming sports or sales calendar moments loaded."


def build_tomorrow_execution_prompt(
    *,
    today_sheet,
    yesterday_sheet,
    week_sheets,
    open_tasks,
    activity_entries,
    upcoming_events,
):
    incomplete_tasks = []
    for task in (today_sheet or {}).get("top_tasks") or []:
        if task.get("task") and not daily_execution_task_finished(task):
            incomplete_tasks.append(f"- {task.get('task')} - {task.get('why') or 'No details noted'}")
    calendar_summary = _event_summary(upcoming_events or [])
    week_summary = "\n".join(_sheet_summary(sheet) for sheet in (week_sheets or [])[:7]) or "- No recent execution sheets loaded."
    incomplete_text = "\n".join(incomplete_tasks) if incomplete_tasks else "- No incomplete tasks from today."
    return f"""You are Nathan's Sports Cave 12 Week Year execution coach.

Your job is to review the latest Sports Cave OS data and build tomorrow's execution plan.

Primary goal:
Move Sports Cave toward $5,000,000 revenue through daily focused execution.

Use the data below:
- Today's completed and incomplete tasks
- Yesterday's execution sheet
- Last 7 days of execution patterns
- Activity Log
- Open Home dashboard tasks
- Upcoming sales/sporting calendar events
- Notes, wins, lessons, distractions, and avoided tasks

Do not be motivational fluff.
Be direct, commercially honest, and execution-focused.

Identify:
1. What Nathan actually moved forward
2. What was avoided, delayed, or half-done
3. What is noise
4. What matters most for revenue
5. What must be protected tomorrow
6. The top 3 tasks for tomorrow
7. The small supporting tasks that keep momentum moving
8. The one task that would make tomorrow a win even if everything else fails

Create tomorrow's Daily Execution Sheet with:
- Top 3 tasks
- Why each task matters
- Suggested time block
- Additional small tasks
- No Grey Zone warning
- Tomorrow's ONE THING
- A blunt accountability note for Nathan

Rules:
- Prioritise revenue, product uploads, ads, mockups, customer/order issues, website improvements, and bottlenecks.
- Do not overload the day.
- Pick only 3 true priority tasks.
- Small tasks must support the priority tasks.
- If yesterday's same task was avoided, call it out.
- If something is a distraction, say so.
- Keep Nathan moving toward the 12 Week Year and $5M target.

SPORTS CAVE OS DATA

Today's sheet:
{_sheet_summary(today_sheet)}

Incomplete tasks:
{incomplete_text}

Yesterday's sheet:
{_sheet_summary(yesterday_sheet)}

Last 7 days:
{week_summary}

Activity Log:
{_activity_summary(activity_entries)}

Open Home dashboard tasks:
{_tasks_summary(open_tasks)}

Upcoming sports and sales calendar:
{calendar_summary}
"""


def _json_dict(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def humanise_event_type(value):
    text = str(value or "activity").replace("_", " ").strip()
    return text[:1].upper() + text[1:] if text else "Activity"


def clean_activity_source(value):
    source = str(value or "").replace("_", " ").strip()
    if not source:
        return "Sports Cave"
    known = {
        "ads": "Ads",
        "dashboard": "Dashboard",
        "edition ops": "Edition Ops",
        "sports cave os": "Sports Cave",
        "manual app": "Edition Ops",
        "orders": "Orders",
        "prodigi": "Prodigi",
        "social media reels studio": "Social Media Reels Studio",
        "supabase ledger": "Orders",
        "sports cave os manual override": "Edition Ops",
    }
    return known.get(source.casefold(), source[:1].upper() + source[1:])


_TECHNICAL_ACTIVITY_TERMS = (
    "metafield",
    "sync",
    "allocation",
    "schema",
    "api",
    "database",
    "supabase",
    "audit",
    "webhook",
    "payload",
    "mirror",
    "backend",
)

_HOME_SYSTEM_ACTIVITY_EVENT_TYPES = {
    "edition_order_auto_allocation",
    "edition_order_purchase_snapshot_allocation",
    "shopify_order_details_backfill",
    "shopify_product_metafield_mirror",
}

_HOME_SYSTEM_ACTIVITY_SOURCES = {
    "shopify_backfill",
    "supabase_ledger",
    "webhook",
}

_HOME_SYSTEM_ACTIVITY_ACTORS = {
    "sports_cave_os_sync",
}

_HOME_SYSTEM_ACTIVITY_PHRASES = (
    "auto allocation",
    "automatic fulfilment",
    "automatic fulfillment",
    "backend fulfilment",
    "backend fulfillment",
    "edition order auto allocation",
    "metafield mirror",
    "metafield updated",
    "purchase-time shopify edition snapshot",
    "shopify product metafield mirror",
    "shopify product metafield updated",
    "webhook",
)

_ACTIVITY_LABELS = {
    "ad_prompt_generated": "Ad prompt made",
    "certificate_generated": "Certificate generated",
    "certificate_uploaded": "Certificate generated",
    "dashboard_task_added": "Task added",
    "dashboard_task_completed": "Task completed",
    "daily_execution_completed": "Daily Review completed",
    "daily_execution_created": "Daily sheet created",
    "daily_execution_tomorrow_planned": "Tomorrow planned",
    "daily_execution_archived": "Daily sheet archived",
    "daily_execution_mip_completed": "Daily task completed",
    "daily_execution_task_completed": "Daily task completed",
    "design_prompt_saved": "Design prompt saved",
    "edition_product_updated": "Edition updated",
    "edition_updated": "Edition updated",
    "mockup_exported": "Mockup pack exported",
    "mockup_generated": "Mockup made",
    "mockup_made": "Mockup made",
    "mockup_uploaded": "Mockup uploaded",
    "mockup_pack_exported": "Mockup pack exported",
    "mockup_zip_exported": "Mockup pack exported",
    "order_fulfilled": "Order fulfilled",
    "order_fulfilled_certificate_generated": "Order fulfilled",
    "product_edition_updated": "Edition updated",
    "product_uploaded": "Product uploaded",
    "prompt_pack_exported": "Mockup pack exported",
    "reel_prompt_saved": "Reel saved",
    "reel_saved": "Reel saved",
    "reel_video_uploaded": "Reel saved",
    "task_added": "Task added",
    "task_completed": "Task completed",
}

_RECOGNISED_ACTIVITY_PREFIXES = tuple(dict.fromkeys(_ACTIVITY_LABELS.values())) + (
    "Order updated",
)


def _compact_text(value):
    return re.sub(r"\s+", " ", str(value or "").strip())


def _metadata_text(metadata, *keys):
    metadata = metadata or {}
    for key in keys:
        value = metadata.get(key)
        if value not in (None, ""):
            return _compact_text(value)
    return ""


def _text_after_prefix(message, prefixes):
    lower_message = str(message or "").casefold()
    for prefix in prefixes:
        lower_prefix = prefix.casefold()
        if lower_message.startswith(lower_prefix):
            return _compact_text(str(message)[len(prefix) :].strip(" :-"))
    if ":" in str(message or ""):
        return _compact_text(str(message).split(":", 1)[1])
    return ""


def _format_order_ref(value):
    text = _compact_text(value)
    if not text:
        return ""
    if text.casefold().startswith("order "):
        text = text[6:].strip()
    if text and not text.startswith("#"):
        text = f"#{text}"
    return text


def _order_ref_from_activity(message, metadata):
    direct = _metadata_text(
        metadata,
        "order",
        "order_name",
        "shopify_order_name",
        "shopify_order_number",
        "order_number",
    )
    if direct:
        return _format_order_ref(direct)
    match = re.search(r"(#[A-Z]{0,8}\d[\w-]*|\bSC\d[\w-]*\b|\b\d{3,}\b)", str(message or ""), re.IGNORECASE)
    if match:
        return _format_order_ref(match.group(1))
    return ""


def _product_label_from_activity(message, metadata):
    label = _metadata_text(
        metadata,
        "product",
        "product_title",
        "product_name",
        "title",
        "prompt_name",
        "handle",
        "shopify_handle",
        "filename",
    )
    if label:
        return label
    return _text_after_prefix(
        message,
        (
            "Generated ad prompt",
            "Saved design prompt",
            "Saved reel prompt",
            "Uploaded reel video",
            "Generated mockup",
            "Created mockup",
            "Exported mockup pack",
            "Updated edition settings",
            "Generated certificate",
            "Uploaded certificate",
        ),
    )


def _task_label_from_activity(message, metadata):
    return _metadata_text(metadata, "title", "task", "task_title") or _text_after_prefix(
        message,
        ("Added task", "Task added", "Completed task", "Task completed"),
    )


def _message_has_technical_terms(message):
    lowered = str(message or "").casefold()
    return any(term in lowered for term in _TECHNICAL_ACTIVITY_TERMS)


def home_activity_row_is_visible(row):
    row = dict(row or {})
    payload = _json_dict(row.get("new_value"))
    metadata = _json_dict(row.get("activity_metadata") or payload.get("metadata"))
    action_type = _compact_text(
        row.get("activity_action_type") or payload.get("action_type") or row.get("event_type")
    ).casefold()
    source = _compact_text(row.get("source") or payload.get("source")).casefold()
    actor = _compact_text(row.get("actor") or payload.get("actor")).casefold()
    message = _compact_text(row.get("activity_message") or payload.get("message") or row.get("reason"))
    page = _compact_text(row.get("activity_page") or payload.get("page")).casefold()

    actor_type = _compact_text(metadata.get("actor_type") or payload.get("actor_type")).casefold()
    if metadata.get("is_system") is True or payload.get("is_system") is True:
        return False
    if actor_type in {"system", "webhook", "background", "automatic"}:
        return False
    if action_type in _HOME_SYSTEM_ACTIVITY_EVENT_TYPES:
        return False
    if "webhook" in action_type or "metafield_mirror" in action_type:
        return False
    if "auto_allocation" in action_type and "manual" not in action_type:
        return False
    if source in _HOME_SYSTEM_ACTIVITY_SOURCES or actor in _HOME_SYSTEM_ACTIVITY_ACTORS:
        return False

    combined = " ".join(part for part in (action_type, source, actor, page, message.casefold()) if part)
    return not any(phrase in combined for phrase in _HOME_SYSTEM_ACTIVITY_PHRASES)


def clean_activity_message(action_type, message, *, metadata=None, entity_type="", entity_id=""):
    metadata = metadata or {}
    action = str(action_type or "").strip().casefold()
    clean_message = _compact_text(message)
    product_label = _product_label_from_activity(clean_message, metadata)
    order_ref = _order_ref_from_activity(clean_message, metadata)

    if action == "order_fulfilled_certificate_generated" or "fulfilled + certificate generated" in clean_message.casefold():
        return f"Order {order_ref} fulfilled + certificate generated" if order_ref else "Order fulfilled + certificate generated"
    if action in {"task_added", "dashboard_task_added"}:
        task_label = _task_label_from_activity(clean_message, metadata)
        return f"Task added: {task_label}" if task_label else "Task added"
    if action in {"task_completed", "dashboard_task_completed"}:
        task_label = _task_label_from_activity(clean_message, metadata)
        return f"Task completed: {task_label}" if task_label else "Task completed"
    if action in {"certificate_generated", "certificate_uploaded"}:
        if order_ref:
            return f"Certificate generated for Order {order_ref}"
        if product_label:
            return f"Certificate generated: {product_label}"
        return "Certificate generated"
    if action == "order_fulfilled":
        return f"Order {order_ref} fulfilled" if order_ref else "Order fulfilled"
    if action in {"product_edition_updated", "edition_product_updated", "edition_updated"} or (
        "edition ops shopify" in clean_message.casefold() or "metafield" in clean_message.casefold()
    ):
        return f"Edition updated: {product_label}" if product_label and not _message_has_technical_terms(product_label) else "Edition updated"
    if action in {"mockup_generated", "mockup_made"}:
        return f"Mockup made: {product_label}" if product_label else "Mockup made"
    if action in {"mockup_zip_exported", "mockup_pack_exported", "prompt_pack_exported", "mockup_exported"}:
        return f"Mockup pack exported: {product_label}" if product_label else "Mockup pack exported"
    if action == "product_uploaded":
        return f"Product uploaded: {product_label}" if product_label else "Product uploaded"
    if action == "ad_prompt_generated":
        return f"Ad prompt made: {product_label}" if product_label else "Ad prompt made"
    if action == "design_prompt_saved":
        return f"Design prompt saved: {product_label}" if product_label else "Design prompt saved"
    if action in {"reel_prompt_saved", "reel_video_uploaded", "reel_saved"}:
        return f"Reel saved: {product_label}" if product_label else "Reel saved"
    if "auto allocation" in clean_message.casefold():
        return f"Order updated: {order_ref}" if order_ref else "Order updated"
    if not clean_message or _message_has_technical_terms(clean_message):
        return humanise_event_type(action)
    return clean_message


def activity_from_audit_row(row):
    row = dict(row or {})
    payload = _json_dict(row.get("new_value"))
    metadata = _json_dict(row.get("activity_metadata") or payload.get("metadata"))
    message = (
        str(row.get("activity_message") or "").strip()
        or str(payload.get("message") or "").strip()
        or str(row.get("reason") or "").strip()
        or humanise_event_type(row.get("event_type"))
    )
    page = (
        str(row.get("activity_page") or "").strip()
        or str(payload.get("page") or "").strip()
        or clean_activity_source(row.get("source"))
    )
    action_type = (
        str(row.get("activity_action_type") or "").strip()
        or str(payload.get("action_type") or row.get("event_type") or "").strip()
    )
    message = clean_activity_message(
        action_type,
        message,
        metadata=metadata,
        entity_type=row.get("entity_type") or "",
        entity_id=row.get("entity_id") or "",
    )
    return {
        "id": str(row.get("id") or ""),
        "action_type": action_type,
        "message": message,
        "page": page,
        "source": page,
        "created_at": row.get("created_at"),
        "entity_type": row.get("entity_type") or "",
        "entity_id": row.get("entity_id") or "",
        "actor": row.get("actor")
        or metadata.get("actor_name")
        or metadata.get("display_name")
        or metadata.get("email")
        or metadata.get("username")
        or "",
        "metadata": metadata,
    }


def split_activity_message(entry):
    entry = dict(entry or {})
    message = str(entry.get("message") or "").strip()
    action_type = str(entry.get("action_type") or "").strip().casefold()
    activity = _ACTIVITY_LABELS.get(action_type)

    for prefix in _RECOGNISED_ACTIVITY_PREFIXES:
        separator = f"{prefix}:"
        if message.casefold().startswith(separator.casefold()):
            return prefix, message[len(separator) :].lstrip()

    if activity:
        return activity, message
    return humanise_event_type(action_type) if action_type else "Activity", message


def _activity_product_slug(value):
    text = _compact_text(value).casefold()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text


def _mockup_product_label(entry, run_products=None):
    entry = dict(entry or {})
    metadata = entry.get("metadata") or {}
    label = _metadata_text(
        metadata,
        "product_handle",
        "shopify_handle",
        "handle",
        "product_slug",
        "product_name",
        "product_title",
        "product",
    )
    entity_id = _compact_text(entry.get("entity_id"))
    if not label and entity_id and run_products:
        label = _compact_text(run_products.get(entity_id))
    return label


def _mockup_item_label(entry):
    entry = dict(entry or {})
    metadata = entry.get("metadata") or {}
    label = _metadata_text(metadata, "mockup_name", "prompt_label", "scene_name")
    message = _compact_text(entry.get("message"))
    if not label:
        label = _text_after_prefix(
            message,
            (
                "Added mockup",
                "Uploaded mockup",
                "Mockup uploaded",
                "Created mockup",
                "Mockup made",
            ),
        )
    if not label:
        prompt_name = _metadata_text(metadata, "prompt", "prompt_name")
        if prompt_name:
            stem = re.sub(r"-prompt$", "", Path(prompt_name).stem, flags=re.IGNORECASE)
            number_match = re.match(r"^(\d+)[-_ ]+(.*)$", stem)
            if number_match:
                label = f"{number_match.group(1)} - {number_match.group(2).replace('-', ' ').title()}"
            else:
                label = stem.replace("-", " ").title()
    return label or message or "Mockup"


def _mockup_group_sort_key(label):
    match = re.match(r"^\s*(\d+)", str(label or ""))
    return (int(match.group(1)) if match else 10_000, str(label or "").casefold())


def group_mockup_activity_entries(entries, tzinfo=timezone.utc):
    """Group noisy per-image mockup rows without changing stored audit data."""
    source_entries = [dict(entry or {}) for entry in entries or []]
    run_products = {}
    for entry in source_entries:
        if clean_activity_source(entry.get("page") or entry.get("source")).casefold() != "mockups":
            continue
        product_label = _mockup_product_label(entry)
        entity_id = _compact_text(entry.get("entity_id"))
        if entity_id and product_label:
            run_products.setdefault(entity_id, product_label)

    grouped = []
    normal = []
    for entry in source_entries:
        action_type = _compact_text(entry.get("action_type")).casefold()
        area = clean_activity_source(entry.get("page") or entry.get("source"))
        if area.casefold() != "mockups" or action_type not in MOCKUP_ACTIVITY_GROUP_ACTIONS:
            normal.append(entry)
            continue

        created_at = _as_aware_datetime(entry.get("created_at"), timezone.utc)
        local_created_at = created_at.astimezone(tzinfo or timezone.utc) if created_at else None
        local_date = local_created_at.date().isoformat() if local_created_at else ""
        actor = _compact_text(entry.get("actor") or (entry.get("metadata") or {}).get("email"))
        entity_id = _compact_text(entry.get("entity_id"))
        product_label = _mockup_product_label(entry, run_products)
        product_slug = _activity_product_slug(product_label)

        match = None
        for candidate in grouped:
            if candidate["local_date"] != local_date or candidate["actor_key"] != actor.casefold():
                continue
            if candidate["product_slug"] != product_slug:
                continue
            same_run = bool(entity_id and candidate["entity_id"] == entity_id)
            close_in_time = bool(
                created_at
                and candidate["oldest_at"]
                and abs(candidate["oldest_at"] - created_at) <= MOCKUP_ACTIVITY_GROUP_WINDOW
            )
            if same_run or (not entity_id and not candidate["entity_id"] and close_in_time):
                match = candidate
                break

        if match is None:
            match = {
                "actor": actor,
                "actor_key": actor.casefold(),
                "created_at": entry.get("created_at"),
                "latest_at": created_at,
                "oldest_at": created_at,
                "entity_id": entity_id,
                "local_date": local_date,
                "product_label": product_label,
                "product_slug": product_slug,
                "entries": [],
            }
            grouped.append(match)
        elif created_at:
            if match["latest_at"] is None or created_at > match["latest_at"]:
                match["latest_at"] = created_at
                match["created_at"] = entry.get("created_at")
            if match["oldest_at"] is None or created_at < match["oldest_at"]:
                match["oldest_at"] = created_at
        match["entries"].append(entry)

    summaries = []
    for index, group in enumerate(grouped):
        item_labels = sorted(
            (_mockup_item_label(entry) for entry in group["entries"]),
            key=_mockup_group_sort_key,
        )
        count = len(item_labels)
        product_text = group["product_slug"]
        group_actions = {
            _compact_text(entry.get("action_type")).casefold()
            for entry in group["entries"]
        }
        action_word = "uploaded" if group_actions == {"mockup_uploaded"} else "made"
        count_text = (
            f"{count} mockup {action_word}"
            if count == 1
            else f"{count} mockups {action_word}"
        )
        details = f"{product_text} — {count_text}" if product_text else count_text
        summaries.append(
            {
                "id": f"mockup-group-{index}-{group['entity_id'] or group['local_date']}",
                "action_type": "mockup_activity_group",
                "message": f"Product mockups done: {details}",
                "page": "Mockups",
                "source": "Mockups",
                "created_at": group["created_at"],
                "entity_type": "mockup_run",
                "entity_id": group["entity_id"],
                "actor": group["actor"],
                "metadata": {
                    "mockup_count": count,
                    "product_handle": product_text,
                },
                "is_mockup_group": True,
                "mockup_items": item_labels,
            }
        )

    combined = normal + summaries
    combined.sort(
        key=lambda entry: _as_aware_datetime(entry.get("created_at"), timezone.utc)
        or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return combined


def activity_table_record(entry, tzinfo=timezone.utc):
    if entry.get("is_mockup_group"):
        activity = "Product mockups done"
        details = _text_after_prefix(entry.get("message"), ("Product mockups done",))
    else:
        activity, details = split_activity_message(entry)
    created_at = _as_aware_datetime(entry.get("created_at"), timezone.utc)
    if created_at is not None:
        local_created_at = created_at.astimezone(tzinfo or timezone.utc)
        date_text = local_created_at.strftime("%d %b %Y").lstrip("0")
        time_text = local_created_at.strftime("%I:%M %p").lstrip("0")
    else:
        date_text = ""
        time_text = ""
    return {
        "Date": date_text,
        "Time": time_text,
        "Activity": activity,
        "Details": details,
        "User": _compact_text(entry.get("actor") or (entry.get("metadata") or {}).get("email") or ""),
        "Area": clean_activity_source(entry.get("page") or entry.get("source")),
    }


def _as_aware_datetime(value, fallback_tz=timezone.utc):
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=fallback_tz)
    return parsed


def activity_log_bounds(view, local_now, *, month_start=None):
    view = view if view in ACTIVITY_VIEWS else ACTIVITY_VIEW_TODAY
    if view == ACTIVITY_VIEW_ALL_TIME:
        return None, None

    local_now = local_now or datetime.now(timezone.utc)
    tzinfo = local_now.tzinfo or timezone.utc
    today = local_now.date()
    if view == ACTIVITY_VIEW_LAST_7_DAYS:
        start_day = today - timedelta(days=6)
        start = datetime.combine(start_day, time.min, tzinfo)
        end = datetime.combine(today + timedelta(days=1), time.min, tzinfo)
        return start, end
    if view == ACTIVITY_VIEW_MONTH:
        if isinstance(month_start, datetime):
            month_day = month_start.date()
        elif isinstance(month_start, date):
            month_day = month_start
        else:
            month_day = today.replace(day=1)
        start = datetime.combine(month_day.replace(day=1), time.min, tzinfo)
        if start.month == 12:
            next_month = date(start.year + 1, 1, 1)
        else:
            next_month = date(start.year, start.month + 1, 1)
        end = datetime.combine(next_month, time.min, tzinfo)
        return start, end

    start = datetime.combine(today, time.min, tzinfo)
    end = datetime.combine(today + timedelta(days=1), time.min, tzinfo)
    return start, end


def filter_activity_entries(entries, view, local_now, *, month_start=None):
    start, end = activity_log_bounds(view, local_now, month_start=month_start)
    if start is None and end is None:
        return list(entries or [])
    filtered = []
    for entry in entries or []:
        created_at = _as_aware_datetime(entry.get("created_at"), start.tzinfo if start else timezone.utc)
        if created_at is None:
            continue
        if start and created_at < start:
            continue
        if end and created_at >= end:
            continue
        filtered.append(entry)
    return filtered


def activity_limit_for_view(view, limit=None):
    view = view if view in ACTIVITY_VIEWS else ACTIVITY_VIEW_TODAY
    view_limit = ACTIVITY_VIEW_LIMITS.get(view, ACTIVITY_LOG_LIMIT)
    if limit is None:
        return view_limit
    try:
        requested = max(int(limit), 1)
    except (TypeError, ValueError):
        return view_limit
    return min(requested, view_limit)


def list_activity_entries(view=ACTIVITY_VIEW_TODAY, local_now=None, *, month_start=None, limit=None):
    local_now = local_now or datetime.now(timezone.utc)
    start, end = activity_log_bounds(view, local_now, month_start=month_start)
    safe_limit = activity_limit_for_view(view, limit)
    cache_key = (
        "activity",
        view if view in ACTIVITY_VIEWS else ACTIVITY_VIEW_TODAY,
        start.isoformat() if start else "",
        end.isoformat() if end else "",
        safe_limit,
    )
    cached = _cache_get(_ACTIVITY_CACHE, cache_key)
    if cached is not None:
        return cached
    try:
        backend = get_supabase_backend()
        rows = backend.list_activity_logs(start_at=start, end_at=end, limit=safe_limit)
        entries = [activity_from_audit_row(row) for row in rows if home_activity_row_is_visible(row)]
        return _cache_set(_ACTIVITY_CACHE, cache_key, entries, ACTIVITY_CACHE_TTL_SECONDS)
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error


def load_dashboard_state(
    activity_view=ACTIVITY_VIEW_TODAY,
    local_now=None,
    *,
    month_start=None,
    include_activity=True,
):
    state = {"tasks": [], "activity_log": [], "task_error": "", "activity_error": ""}
    try:
        state["tasks"] = list_tasks(status="open")
    except DashboardStorageError as error:
        state["task_error"] = str(error)
    if not include_activity:
        return state
    try:
        state["activity_log"] = list_activity_entries(
            activity_view,
            local_now or datetime.now(timezone.utc),
            month_start=month_start,
        )
    except DashboardStorageError as error:
        state["activity_error"] = str(error)
    return state


def list_existing_edition_products(limit=1000):
    try:
        safe_limit = max(min(int(limit or 1000), 1500), 1)
    except (TypeError, ValueError):
        safe_limit = 1000
    cache_key = ("edition_products", safe_limit)
    cached = _cache_get(_EDITION_PRODUCT_CACHE, cache_key)
    if cached is not None:
        return cached
    try:
        backend = get_supabase_backend()
        if not hasattr(backend, "list_dashboard_edition_products"):
            raise DashboardStorageError("Product list is unavailable right now.")
        products = backend.list_dashboard_edition_products(limit=safe_limit)
        normalised = []
        for product in products or []:
            title = _compact_text(product.get("title") or product.get("product_title") or "")
            handle = _compact_text(product.get("handle") or product.get("shopify_handle") or "")
            if not title and not handle:
                continue
            normalised.append(
                {
                    "title": title or handle,
                    "handle": handle,
                    "category": _compact_text(product.get("category") or product.get("sport") or product.get("product_type") or ""),
                    "status": _compact_text(product.get("status") or ""),
                }
            )
        return _cache_set(_EDITION_PRODUCT_CACHE, cache_key, normalised, EDITION_PRODUCT_CACHE_TTL_SECONDS)
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error


def greeting_for_datetime(local_dt):
    hour = int(local_dt.hour)
    if 5 <= hour < 12:
        return "Good morning :)"
    if 12 <= hour < 17:
        return "Good afternoon :)"
    return "Good night :)"


def greeting_for_account(local_dt, user):
    base = greeting_for_datetime(local_dt).replace(" :)", "").strip()
    name = _compact_text(
        (user or {}).get("display_name")
        or (user or {}).get("email")
        or (user or {}).get("username")
    )
    return f"{base}, {name}" if name else base


def load_calendar_events(path=SPORTING_CALENDAR_PATH):
    path = Path(path)
    try:
        cache_key = (str(path), path.stat().st_mtime)
    except OSError:
        cache_key = (str(path), None)
    cached = _cache_get(_CALENDAR_CACHE, cache_key)
    if cached is not None:
        return cached
    data = _read_json(path, {"events": []})
    events = data.get("events") if isinstance(data.get("events"), list) else []
    return _cache_set(_CALENDAR_CACHE, cache_key, events, CALENDAR_CACHE_TTL_SECONDS)


def parse_event_date(value):
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def event_status(event, today):
    dates = sports_sales_calendar.confirmed_event_dates(event)
    if not dates:
        return "tbc"
    start, end = dates
    if start <= today <= end:
        return "active"
    if today < start:
        return "upcoming"
    return "past"


def days_until_event(event, today):
    dates = sports_sales_calendar.confirmed_event_dates(event)
    return (dates[0] - today).days if dates else None


def _event_matches_region(event, region):
    if not region or region == "All":
        return True
    return region in (event.get("regions") or [])


def _event_matches_sport(event, sport):
    return not sport or sport == "All" or event.get("sport") == sport


def filter_calendar_events(
    events,
    today,
    *,
    region="All",
    sport="All",
    status="Active/upcoming",
    upcoming_days=DEFAULT_UPCOMING_DAYS,
):
    filtered = []
    for event in events:
        if not _event_matches_region(event, region):
            continue
        if not _event_matches_sport(event, sport):
            continue
        current_status = event_status(event, today)
        days_until = days_until_event(event, today)
        if current_status == "tbc" or days_until is None:
            if status != "All":
                continue
            filtered.append(event)
            continue
        if status == "Active" and current_status != "active":
            continue
        if status == "Upcoming" and not (current_status == "upcoming" and days_until <= upcoming_days):
            continue
        if status == "Active/upcoming" and not (
            current_status == "active"
            or (current_status == "upcoming" and days_until <= upcoming_days)
        ):
            continue
        filtered.append(event)

    return sorted(
        filtered,
        key=lambda event: (
            event_status(event, today) == "tbc",
            event_status(event, today) != "active",
            abs(days_until_event(event, today) or 0),
            -int(event.get("importance") or 0),
            event.get("title") or "",
        ),
    )


def build_active_alerts(
    events,
    today,
    *,
    limit=4,
    upcoming_days=DEFAULT_UPCOMING_DAYS,
):
    active_items = []
    upcoming_items = []
    for event in events:
        importance = int(event.get("importance") or 0)
        if importance < 3:
            continue
        status = event_status(event, today)
        days_until = days_until_event(event, today)
        if status == "tbc" or days_until is None:
            continue
        if status == "active":
            score = 1000 + (importance * 20)
            active_items.append((score, event))
        elif status == "upcoming" and days_until <= upcoming_days:
            score = 700 + (importance * 20) - days_until
            upcoming_items.append((score, event))
        else:
            continue

    active_items.sort(key=lambda item: (-item[0], item[1].get("title") or ""))
    upcoming_items.sort(key=lambda item: (-item[0], item[1].get("title") or ""))

    alerts = []
    seen = set()

    def add_event(event):
        label = (event.get("alert_label") or event.get("title") or "").strip()
        if not label or label in seen or len(alerts) >= limit:
            return False
        seen.add(label)
        alerts.append({"label": label, "event": event, "status": event_status(event, today)})
        return True

    for _, event in active_items[:limit]:
        add_event(event)

    if upcoming_items and not any(alert["status"] == "upcoming" for alert in alerts):
        _, upcoming_event = upcoming_items[0]
        if len(alerts) >= limit:
            remove_index = len(alerts) - 1
            upcoming_sport = upcoming_event.get("sport")
            for index, alert in enumerate(alerts):
                event = alert.get("event") or {}
                if event.get("sport") == upcoming_sport and event.get("type") == "Season":
                    remove_index = index
                    break
            removed = alerts.pop(remove_index)
            seen.discard(removed["label"])
        add_event(upcoming_event)

    for _, event in upcoming_items:
        if len(alerts) >= limit:
            break
        add_event(event)

    return alerts


def format_event_date_range(event):
    if sports_sales_calendar.event_is_tbc(event):
        return sports_sales_calendar.format_event_date(event)
    dates = sports_sales_calendar.confirmed_event_dates(event)
    if not dates:
        return "Date TBC"
    start, end = dates
    if start == end:
        return start.strftime("%d %b %Y")
    if start.year == end.year:
        if start.month == end.month:
            return f"{start.strftime('%d')} - {end.strftime('%d %b %Y')}"
        return f"{start.strftime('%d %b')} - {end.strftime('%d %b %Y')}"
    return f"{start.strftime('%d %b %Y')} - {end.strftime('%d %b %Y')}"


def sporting_calendar_prompt_summary(events, today, *, limit=28, upcoming_days=180):
    selected = filter_calendar_events(
        events or [],
        today,
        status="Active/upcoming",
        upcoming_days=upcoming_days,
    )
    if not selected:
        return "- No active or upcoming Sports Cave calendar moments loaded."
    lines = []
    for event in selected[:limit]:
        status = event_status(event, today)
        region_text = ", ".join(event.get("regions") or [])
        lines.append(
            f"- {event.get('title') or 'Sports moment'} ({event.get('sport') or 'Sport'}, "
            f"{region_text}; {format_event_date_range(event)}; {status})"
        )
    if len(selected) > limit:
        lines.append(f"- Plus {len(selected) - limit} more calendar moments in the Sports Cave calendar.")
    return "\n".join(lines)


def edition_products_prompt_summary(products, *, warning=""):
    if warning:
        return warning
    lines = []
    for product in products or []:
        title = _compact_text(product.get("title") or product.get("product_title") or "")
        handle = _compact_text(product.get("handle") or product.get("shopify_handle") or "")
        category = _compact_text(product.get("category") or product.get("sport") or product.get("product_type") or "")
        status = _compact_text(product.get("status") or "")
        if not title and not handle:
            continue
        detail_parts = [part for part in (handle, category, status) if part]
        detail = f" ({'; '.join(detail_parts)})" if detail_parts else ""
        lines.append(f"- {title or handle}{detail}")
    if not lines:
        return "- No existing Edition Ops products were loaded."
    return "\n".join(lines)


def build_design_ideas_prompt(local_now, events, products, *, product_warning=""):
    local_now = local_now or datetime.now(timezone.utc)
    today = local_now.date()
    calendar_summary = sporting_calendar_prompt_summary(events or [], today)
    product_summary = edition_products_prompt_summary(products or [], warning=product_warning)
    today_label = today.strftime("%d %B %Y")
    return f"""Act as Sports Cave's live product research strategist.

Today is {today_label}.

Use live web research to study today's current sports news, trends, major events, anniversaries, finals, rivalries, injuries, returns, retirements, title races, championship moments, awards, transfer/signing stories, and upcoming calendar moments across AU, USA, UK, Canada, and NZ.

Use this Sports Cave sporting calendar context:
{calendar_summary}

Use this existing Edition Ops product list as do-not-duplicate context:
{product_summary}

Sports Cave sells premium framed limited-edition sports collector artwork. Each idea must feel wall-worthy, emotional, nostalgic or culturally relevant, and strong enough to become a best seller.

Do not recommend an existing product unless you label it as REWORK EXISTING PRODUCT and explain the refresh angle.

Recommend exactly 5 ideas.

Cover Sports Cave categories such as Motorsport, NBA, Football/Soccer, Cricket, Tennis, Golf, Rugby Union, Baseball, NFL, Combat, Ice Hockey, Horse Racing, and Other.

Prefer ideas that could become premium limited-edition framed collector pieces. Include classics, legends, rivalries, current trending stars, emotional moments, and country-specific demand.

For each idea, provide:
1. Product title
2. Sport/category
3. Country priority
4. Why this has demand right now
5. Fan emotion
6. Visual direction
7. Best mockup angle
8. Ad hook
9. Suggested task wording to add to the dashboard

Be commercially honest. Prioritise ideas most likely to sell."""


def build_todays_design_ideas_prompt(local_now, events=None):
    product_warning = ""
    products = []
    try:
        products = list_existing_edition_products()
    except DashboardStorageError:
        product_warning = "- Existing Edition Ops product list could not be loaded."
    return build_design_ideas_prompt(
        local_now or datetime.now(timezone.utc),
        events if events is not None else load_calendar_events(),
        products,
        product_warning=product_warning,
    )
