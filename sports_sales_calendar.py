import calendar
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo


CALENDAR_START = date(2026, 7, 21)
CALENDAR_END = date(2027, 12, 31)
SYDNEY_TIMEZONE = ZoneInfo("Australia/Sydney")
VALID_MARKET_CODES = frozenset({"AU", "UK", "US", "CA", "NZ", "ALL"})
VALID_EVENT_KINDS = frozenset({"sport", "sale"})

_REGION_CODES = {
    "australia": "AU",
    "au": "AU",
    "united kingdom": "UK",
    "uk": "UK",
    "usa": "US",
    "us": "US",
    "united states": "US",
    "canada": "CA",
    "ca": "CA",
    "new zealand": "NZ",
    "nz": "NZ",
    "all": "ALL",
}


def month_options():
    months = []
    current = CALENDAR_START.replace(day=1)
    final = CALENDAR_END.replace(day=1)
    while current <= final:
        months.append(current)
        current = date(current.year + (current.month == 12), (current.month % 12) + 1, 1)
    return tuple(months)


def month_label(month_start):
    return f"{calendar.month_name[month_start.month]} {month_start.year}"


def sydney_date(now=None):
    if now is None:
        return datetime.now(SYDNEY_TIMEZONE).date()
    if isinstance(now, datetime):
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return now.astimezone(SYDNEY_TIMEZONE).date()
    return now


def default_month(now=None):
    current = sydney_date(now).replace(day=1)
    first = CALENDAR_START.replace(day=1)
    final = CALENDAR_END.replace(day=1)
    return min(max(current, first), final)


def month_bounds(month_start):
    start = month_start.replace(day=1)
    if start.month == 12:
        end = date(start.year + 1, 1, 1)
    else:
        end = date(start.year, start.month + 1, 1)
    return start, end


def month_weeks(month_start):
    return calendar.Calendar(firstweekday=calendar.MONDAY).monthdatescalendar(
        month_start.year,
        month_start.month,
    )


def event_is_tbc(event):
    precision = str(event.get("date_precision") or "").strip().casefold()
    return precision in {"month", "tbc"} or bool(event.get("date_tbc")) or not event.get("start_date")


def event_month(event):
    value = str(event.get("start_month") or "").strip()
    if not value and event.get("start_date"):
        value = str(event["start_date"])[:7]
    try:
        return date.fromisoformat(f"{value}-01")
    except ValueError:
        return None


def confirmed_event_dates(event):
    if event_is_tbc(event):
        return None
    try:
        start = date.fromisoformat(str(event["start_date"]))
        end = date.fromisoformat(str(event.get("end_date") or event["start_date"]))
    except (KeyError, TypeError, ValueError):
        return None
    return start, max(start, end)


def event_kind(event):
    explicit = str(event.get("event_kind") or "").strip().casefold()
    if explicit in VALID_EVENT_KINDS:
        return explicit
    return "sale" if str(event.get("sport") or "").strip().casefold() == "sales" else "sport"


def market_codes(event):
    values = event.get("markets") or event.get("regions") or []
    codes = []
    for value in values:
        code = _REGION_CODES.get(str(value or "").strip().casefold())
        if code and code not in codes:
            codes.append(code)
    if "ALL" in codes or set(codes) == {"AU", "UK", "US", "CA", "NZ"}:
        return ("ALL",)
    return tuple(codes)


def event_is_in_range(event):
    if event_is_tbc(event):
        month = event_month(event)
        return bool(month and CALENDAR_START.replace(day=1) <= month <= CALENDAR_END.replace(day=1))
    dates = confirmed_event_dates(event)
    return bool(dates and dates[1] >= CALENDAR_START and dates[0] <= CALENDAR_END)


def event_sort_key(event):
    dates = confirmed_event_dates(event)
    if dates:
        return (0, dates[0], dates[1], str(event.get("title") or "").casefold())
    month = event_month(event) or date.max
    return (1, month, month, str(event.get("title") or "").casefold())


def sorted_calendar_events(events):
    return sorted((event for event in events or [] if event_is_in_range(event)), key=event_sort_key)


def events_for_month(events, selected_month):
    month_start, next_month = month_bounds(selected_month)
    exact = []
    tbc = []
    for event in sorted_calendar_events(events):
        if event_is_tbc(event):
            if event_month(event) == month_start:
                tbc.append(event)
            continue
        start, end = confirmed_event_dates(event)
        if start < next_month and end >= month_start:
            exact.append(event)
    return exact, tbc


def month_event_buckets(events, selected_month):
    month_start, _ = month_bounds(selected_month)
    exact, tbc = events_for_month(events, selected_month)
    buckets = {}
    for event in exact:
        start, _ = confirmed_event_dates(event)
        anchor = max(start, month_start, CALENDAR_START)
        buckets.setdefault(anchor, []).append(event)
    for day_events in buckets.values():
        day_events.sort(key=event_sort_key)
    return buckets, tbc


def format_event_date(event):
    if event_is_tbc(event):
        month = event_month(event)
        return f"{month_label(month)} - date TBC" if month else "Date TBC"
    dates = confirmed_event_dates(event)
    if not dates:
        return "Date TBC"
    start, end = dates
    if start == end:
        return f"{start.day} {start.strftime('%b %Y')}"
    if start.year == end.year and start.month == end.month:
        return f"{start.day}-{end.strftime('%d %b %Y')}"
    if start.year == end.year:
        return f"{start.strftime('%d %b')}-{end.strftime('%d %b %Y')}"
    return f"{start.strftime('%d %b %Y')}-{end.strftime('%d %b %Y')}"


def confirmed_upcoming_events(events, today, *, limit=8):
    upcoming = []
    for event in events or []:
        dates = confirmed_event_dates(event)
        if not dates or dates[1] < today:
            continue
        upcoming.append(event)
    upcoming.sort(key=lambda event: (max(confirmed_event_dates(event)[0], today), event_sort_key(event)))
    return upcoming[: max(int(limit or 0), 0)]


def validate_event(event):
    errors = []
    if event_kind(event) not in VALID_EVENT_KINDS:
        errors.append("invalid event kind")
    codes = market_codes(event)
    if not codes or any(code not in VALID_MARKET_CODES for code in codes):
        errors.append("invalid market code")
    if event_is_tbc(event):
        if event_month(event) is None:
            errors.append("invalid TBC month")
    elif confirmed_event_dates(event) is None:
        errors.append("invalid confirmed date")
    return errors
