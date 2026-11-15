"""Pure progress calculations for persisted SEO import jobs."""

from __future__ import annotations

from datetime import date, datetime, timezone


ACTIVE_STATUSES = {"queued", "running"}
TERMINAL_STATUSES = {"completed", "partial", "failed"}
MINIMUM_RATE_DATES = 2
MINIMUM_RATE_SECONDS = 30


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _as_datetime(value):
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _integer(value):
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def inclusive_date_count(start_date, end_date):
    start = _as_date(start_date)
    end = _as_date(end_date)
    if not start or not end or end < start:
        return 0
    return (end - start).days + 1


def _completed_date_count(run, requested_start, requested_end, total_dates):
    status = str(run.get("status") or "").casefold()
    if status == "queued":
        return 0
    if status == "completed":
        return total_dates
    completed_start = _as_date(run.get("completed_start_date")) or requested_start
    completed_end = max(
        (
            value
            for value in (
                _as_date(run.get("completed_end_date")),
                _as_date(run.get("checkpoint_date")),
            )
            if value
        ),
        default=None,
    )
    if not completed_start or not completed_end:
        return 0
    completed_start = max(completed_start, requested_start)
    completed_end = min(completed_end, requested_end)
    if completed_end < completed_start:
        return 0
    return min((completed_end - completed_start).days + 1, total_dates)


def calculate_sync_progress(run, *, now=None):
    run = dict(run or {})
    now = _as_datetime(now) or datetime.now(timezone.utc)
    status = str(run.get("status") or "not_started").casefold()
    requested_start = _as_date(run.get("requested_start_date"))
    requested_end = _as_date(run.get("requested_end_date"))
    total_dates = inclusive_date_count(requested_start, requested_end)
    completed_dates = (
        _completed_date_count(run, requested_start, requested_end, total_dates)
        if total_dates
        else 0
    )
    if status == "completed":
        percentage = 100.0
    elif total_dates:
        percentage = min(max((completed_dates / total_dates) * 100, 0.0), 100.0)
    else:
        percentage = 0.0

    started_at = _as_datetime(run.get("started_at"))
    finished_at = _as_datetime(run.get("completed_at")) if status in TERMINAL_STATUSES else None
    elapsed_seconds = max(((finished_at or now) - started_at).total_seconds(), 0.0) if started_at else 0.0
    rate_per_minute = None
    eta_seconds = None
    if (
        status == "running"
        and total_dates > completed_dates
        and completed_dates >= MINIMUM_RATE_DATES
        and elapsed_seconds >= MINIMUM_RATE_SECONDS
    ):
        rate_per_minute = completed_dates / (elapsed_seconds / 60)
        if rate_per_minute > 0:
            eta_seconds = ((total_dates - completed_dates) / rate_per_minute) * 60

    return {
        "status": status,
        "percentage": percentage,
        "total_dates": total_dates,
        "completed_dates": completed_dates,
        "current_checkpoint_date": (
            _as_date(run.get("active_slice_date"))
            or _as_date(run.get("checkpoint_date"))
        ),
        "rows_received": _integer(run.get("rows_received")),
        "rows_stored": _integer(run.get("rows_stored", run.get("rows_written"))),
        "elapsed_seconds": elapsed_seconds,
        "rate_per_minute": rate_per_minute,
        "eta_seconds": eta_seconds,
        "last_progress_at": _as_datetime(run.get("updated_at")),
        "range_valid": bool(total_dates),
    }


def format_duration(seconds):
    seconds = max(int(seconds or 0), 0)
    if seconds < 60:
        return f"{seconds} seconds"
    minutes = round(seconds / 60)
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    hours, remaining_minutes = divmod(minutes, 60)
    if remaining_minutes:
        return f"{hours}h {remaining_minutes}m"
    return f"{hours} hour{'s' if hours != 1 else ''}"
