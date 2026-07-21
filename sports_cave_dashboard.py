from datetime import date, datetime, time, timedelta, timezone
import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
SPORTING_CALENDAR_PATH = DATA_DIR / "sporting_calendar.json"
TASK_GROUPS = ("Collections to update", "New designs to complete")
REGIONS = ("Australia", "USA", "UK", "Canada", "New Zealand")
ACTIVITY_LOG_LIMIT = 200
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
    return category if category in TASK_GROUPS else TASK_GROUPS[0]


def list_tasks(status="open"):
    try:
        backend = get_supabase_backend()
        return [_normalise_task(task) for task in backend.list_dashboard_tasks(status=status)]
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error


def add_task(text, category, *, metadata=None):
    task_text = str(text or "").strip()
    if not task_text:
        raise ValueError("Task text is required.")
    try:
        backend = get_supabase_backend()
        return _normalise_task(
            backend.create_dashboard_task(
                task_text,
                normalize_task_category(category),
                metadata=metadata or {},
            )
        )
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error


def complete_task(task_id, *, metadata=None):
    try:
        backend = get_supabase_backend()
        completed = backend.complete_dashboard_task(task_id, metadata=metadata or {})
        return _normalise_task(completed) if completed else None
    except Exception as error:
        raise DashboardStorageError(_storage_error(error)) from error


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
        "sports cave os": "Sports Cave",
        "manual app": "Edition Ops",
        "supabase ledger": "Orders",
        "sports cave os manual override": "Edition Ops",
    }
    return known.get(source.casefold(), source[:1].upper() + source[1:])


def activity_from_audit_row(row):
    row = dict(row or {})
    payload = _json_dict(row.get("new_value"))
    metadata = _json_dict(payload.get("metadata"))
    message = (
        str(payload.get("message") or "").strip()
        or str(row.get("reason") or "").strip()
        or humanise_event_type(row.get("event_type"))
    )
    page = str(payload.get("page") or "").strip() or clean_activity_source(row.get("source"))
    return {
        "id": str(row.get("id") or ""),
        "action_type": str(payload.get("action_type") or row.get("event_type") or "").strip(),
        "message": message,
        "page": page,
        "source": page,
        "created_at": row.get("created_at"),
        "entity_type": row.get("entity_type") or "",
        "entity_id": row.get("entity_id") or "",
        "metadata": metadata,
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


def list_activity_entries(view=ACTIVITY_VIEW_TODAY, local_now=None, *, month_start=None, limit=ACTIVITY_LOG_LIMIT):
    local_now = local_now or datetime.now(timezone.utc)
    start, end = activity_log_bounds(view, local_now, month_start=month_start)
    try:
        backend = get_supabase_backend()
        rows = backend.list_activity_logs(start_at=start, end_at=end, limit=limit)
        return [activity_from_audit_row(row) for row in rows]
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


def greeting_for_datetime(local_dt):
    hour = int(local_dt.hour)
    if 5 <= hour < 12:
        return "Good morning :)"
    if 12 <= hour < 17:
        return "Good afternoon :)"
    return "Good night :)"


def load_calendar_events(path=SPORTING_CALENDAR_PATH):
    data = _read_json(path, {"events": []})
    events = data.get("events") if isinstance(data.get("events"), list) else []
    return events


def parse_event_date(value):
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def event_status(event, today):
    start = parse_event_date(event["start_date"])
    end = parse_event_date(event.get("end_date") or event["start_date"])
    if start <= today <= end:
        return "active"
    if today < start:
        return "upcoming"
    return "past"


def days_until_event(event, today):
    return (parse_event_date(event["start_date"]) - today).days


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
            event_status(event, today) != "active",
            abs(days_until_event(event, today)),
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
    start = parse_event_date(event["start_date"])
    end = parse_event_date(event.get("end_date") or event["start_date"])
    if start == end:
        return start.strftime("%d %b %Y")
    if start.year == end.year:
        if start.month == end.month:
            return f"{start.strftime('%d')} - {end.strftime('%d %b %Y')}"
        return f"{start.strftime('%d %b')} - {end.strftime('%d %b %Y')}"
    return f"{start.strftime('%d %b %Y')} - {end.strftime('%d %b %Y')}"
