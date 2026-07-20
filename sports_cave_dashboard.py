from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import uuid


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DASHBOARD_STATE_PATH = DATA_DIR / "dashboard_state.json"
SPORTING_CALENDAR_PATH = DATA_DIR / "sporting_calendar.json"
TASK_GROUPS = ("Collections to update", "New designs to complete")
CUSTOM_EVENT_SPORTS = (
    "Sales",
    "Custom",
    "NBA",
    "Basketball",
    "MLB",
    "Baseball",
    "NHL",
    "Ice Hockey",
    "NFL",
    "Football",
    "Rugby Union",
    "Cricket",
    "Tennis",
    "Golf",
    "Motorsport",
    "Horse Racing",
    "Combat",
    "Major event",
)
REGIONS = ("Australia", "USA", "UK", "Canada", "New Zealand")
ACTIVITY_LOG_LIMIT = 200
CUSTOM_EVENT_LIMIT = 300
DEFAULT_UPCOMING_DAYS = 60


def utc_now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def blank_dashboard_state():
    return {"tasks": [], "activity_log": [], "custom_events": []}


def _read_json(path, fallback):
    path = Path(path)
    if not path.exists():
        return deepcopy(fallback)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return deepcopy(fallback)
    return data if isinstance(data, dict) else deepcopy(fallback)


def _write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    temp_path.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(path)


def load_dashboard_state(path=DASHBOARD_STATE_PATH):
    state = _read_json(path, blank_dashboard_state())
    tasks = state.get("tasks") if isinstance(state.get("tasks"), list) else []
    activity_log = (
        state.get("activity_log") if isinstance(state.get("activity_log"), list) else []
    )
    custom_events = (
        state.get("custom_events") if isinstance(state.get("custom_events"), list) else []
    )
    return {
        "tasks": tasks,
        "activity_log": activity_log[:ACTIVITY_LOG_LIMIT],
        "custom_events": custom_events[:CUSTOM_EVENT_LIMIT],
    }


def save_dashboard_state(state, path=DASHBOARD_STATE_PATH):
    clean_state = {
        "tasks": list(state.get("tasks") or []),
        "activity_log": list(state.get("activity_log") or [])[:ACTIVITY_LOG_LIMIT],
        "custom_events": list(state.get("custom_events") or [])[:CUSTOM_EVENT_LIMIT],
    }
    _write_json(path, clean_state)
    return clean_state


def add_activity(state, message, *, created_at=None):
    entry = {
        "id": uuid.uuid4().hex,
        "message": str(message or "").strip(),
        "created_at": created_at or utc_now_iso(),
    }
    if not entry["message"]:
        return None
    log_entries = [entry, *list(state.get("activity_log") or [])]
    state["activity_log"] = log_entries[:ACTIVITY_LOG_LIMIT]
    return entry


def record_activity(message, *, path=DASHBOARD_STATE_PATH, created_at=None):
    state = load_dashboard_state(path)
    entry = add_activity(state, message, created_at=created_at)
    save_dashboard_state(state, path)
    return entry


def normalize_task_category(category):
    return category if category in TASK_GROUPS else TASK_GROUPS[0]


def add_task(text, category, *, path=DASHBOARD_STATE_PATH, created_at=None):
    task_text = str(text or "").strip()
    if not task_text:
        raise ValueError("Task text is required.")
    state = load_dashboard_state(path)
    task = {
        "id": uuid.uuid4().hex,
        "text": task_text,
        "category": normalize_task_category(category),
        "created_at": created_at or utc_now_iso(),
    }
    state["tasks"].append(task)
    add_activity(state, f"Added task: {task_text}", created_at=created_at)
    save_dashboard_state(state, path)
    return task


def complete_task(task_id, *, path=DASHBOARD_STATE_PATH, completed_at=None):
    state = load_dashboard_state(path)
    remaining_tasks = []
    completed_task = None
    for task in state.get("tasks") or []:
        if task.get("id") == task_id and completed_task is None:
            completed_task = task
        else:
            remaining_tasks.append(task)

    if completed_task is None:
        return None

    state["tasks"] = remaining_tasks
    add_activity(
        state,
        f"Completed task: {completed_task.get('text', '').strip()}",
        created_at=completed_at,
    )
    save_dashboard_state(state, path)
    return completed_task


def normalize_event_regions(regions):
    clean_regions = []
    for region in regions or []:
        if region in REGIONS and region not in clean_regions:
            clean_regions.append(region)
    return clean_regions or ["Australia"]


def normalize_custom_event_sport(sport):
    return sport if sport in CUSTOM_EVENT_SPORTS else "Custom"


def add_custom_event(
    title,
    start_date,
    end_date,
    regions,
    *,
    sport="Custom",
    notes="",
    path=DASHBOARD_STATE_PATH,
    created_at=None,
):
    event_title = str(title or "").strip()
    if not event_title:
        raise ValueError("Event title is required.")

    start = parse_event_date(start_date)
    end = parse_event_date(end_date or start)
    if end < start:
        raise ValueError("End date must be on or after the start date.")

    state = load_dashboard_state(path)
    event = {
        "alert_label": "",
        "created_at": created_at or utc_now_iso(),
        "custom": True,
        "end_date": end.isoformat(),
        "id": f"custom-{uuid.uuid4().hex}",
        "importance": 3,
        "notes": str(notes or "").strip(),
        "regions": normalize_event_regions(regions),
        "source_url": "",
        "sport": normalize_custom_event_sport(sport),
        "start_date": start.isoformat(),
        "title": event_title,
        "type": "Custom",
    }
    custom_events = [event, *list(state.get("custom_events") or [])]
    state["custom_events"] = custom_events[:CUSTOM_EVENT_LIMIT]
    add_activity(state, f"Added calendar event: {event_title}", created_at=created_at)
    save_dashboard_state(state, path)
    return event


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


def calendar_events_with_custom(events, state):
    return [*list(events or []), *list((state or {}).get("custom_events") or [])]


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
