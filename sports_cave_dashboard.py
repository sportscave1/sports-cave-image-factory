from datetime import date, datetime, time, timedelta, timezone
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
_TASK_CACHE = {}
_ACTIVITY_CACHE = {}
_CALENDAR_CACHE = {}
_EDITION_PRODUCT_CACHE = {}


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


def clear_calendar_cache():
    _CALENDAR_CACHE.clear()


def clear_edition_product_cache():
    _EDITION_PRODUCT_CACHE.clear()


def clear_dashboard_caches():
    clear_task_cache()
    clear_activity_cache()
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
    "design_prompt_saved": "Design prompt saved",
    "edition_product_updated": "Edition updated",
    "edition_updated": "Edition updated",
    "mockup_exported": "Mockup pack exported",
    "mockup_generated": "Mockup made",
    "mockup_made": "Mockup made",
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
        "actor": row.get("actor") or "",
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


def activity_table_record(entry, tzinfo=timezone.utc):
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
