"""Lightweight, same-origin Daily Planner window and narrow JSON endpoints."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import time
from zoneinfo import ZoneInfo

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

import top_bar_security


BASE_DIR = Path(__file__).resolve().parent
CLIENT_PATH = BASE_DIR / "components" / "daily_planner" / "index.html"
CLIENT_SOURCE = CLIENT_PATH.read_text(encoding="utf-8")
PLANNER_WINDOW_PATH = "/daily-planner"
PLANNER_BOOTSTRAP_PATH = "/api/os/daily-planner/bootstrap"
PLANNER_MUTATION_PATH = "/api/os/daily-planner/mutate"
PLANNER_HISTORY_PATH = "/api/os/daily-planner/history"
PLANNER_WEEKLY_REVIEW_PATH = "/api/os/daily-planner/weekly-review"
PLANNER_STATUS_PATH = "/api/os/daily-planner/status"
PLANNER_TIMEZONE = "Australia/Sydney"
SYDNEY_TZ = ZoneInfo(PLANNER_TIMEZONE)


def _json_safe(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _json(payload, status_code=200):
    return JSONResponse(
        _json_safe(payload),
        status_code=status_code,
        headers={"Cache-Control": "no-store"},
    )


def _claims(request: Request):
    authorization = str(request.headers.get("Authorization") or "").strip()
    token = ""
    if authorization.casefold().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    valid, _reason, claims = top_bar_security.validate_top_bar_token(token)
    if not valid or not claims.get("can_manage_daily_planner"):
        return {}
    return claims


def _user(claims):
    return {
        "id": str(claims.get("sub") or ""),
        "display_name": str(claims.get("display_name") or ""),
        "username": str(claims.get("username") or ""),
        "role": str(claims.get("role") or ""),
        "timezone": PLANNER_TIMEZONE,
        "country": "Australia",
        "is_active": True,
        "account_status": "active",
        "page_permissions": [],
    }


def _request_date(request: Request, key="date", *, default=None):
    value = str(request.query_params.get(key) or "").strip()
    try:
        return date.fromisoformat(value) if value else (default or datetime.now(SYDNEY_TZ).date())
    except ValueError as error:
        raise ValueError("Choose a valid work date.") from error


def _safe_error(error):
    message = " ".join(str(error or "").split()).strip()
    if not message:
        return "Daily Planner could not complete that action."
    blocked = ("database url", "supabase", "postgres", "traceback", "password", "token")
    if any(term in message.casefold() for term in blocked):
        return "Daily Planner storage is unavailable right now."
    return message[:240]


def _mutation_error_payload(error, *, retryable):
    message = _safe_error(error)
    migration = "20260815_daily_execution_task_outcomes.sql"
    if migration.casefold() in message.casefold():
        code = "daily_planner_outcome_migration_required"
    elif retryable:
        code = "daily_planner_outcome_save_failed"
    else:
        code = "daily_planner_validation_failed"
    return {
        "ok": False,
        "error": message,
        "error_code": code,
        "retryable": bool(retryable),
    }


def _task_rows(sheet, timers):
    import sports_cave_dashboard

    return sports_cave_dashboard.daily_execution_task_rows(sheet, timers)


def _load_sheet_bundle(user, selected_date):
    """Load one work date plus the previous date needed for carry-forward."""
    import sports_cave_dashboard

    started = time.perf_counter()
    local_today = datetime.now(SYDNEY_TZ).date()
    rollover = sports_cave_dashboard.finalise_overdue_daily_planner_days(user, local_today)
    events = sports_cave_dashboard.reconcile_daily_planner_timers(user)
    backend = sports_cave_dashboard.get_supabase_backend()
    user_id = sports_cave_dashboard.daily_execution_user_id(user)
    if hasattr(backend, "load_daily_planner_date_bundle"):
        bundle = backend.load_daily_planner_date_bundle(user_id, selected_date.isoformat())
        selected = sports_cave_dashboard._normalise_daily_sheet(bundle.get("sheet") or {})
        previous = sports_cave_dashboard._normalise_daily_sheet(bundle.get("source_sheet") or {})
        timers = bundle.get("timers") or []
        active = bundle.get("active_timer") or {}
        read_queries = int(bundle.get("query_count") or 1)
    else:
        selected = sports_cave_dashboard.get_daily_execution_sheet(user, selected_date)
        previous = sports_cave_dashboard.get_daily_execution_sheet(
            user, selected_date - timedelta(days=1)
        )
        timers = []
        if selected and hasattr(backend, "list_daily_execution_timers_for_sheets"):
            timers = backend.list_daily_execution_timers_for_sheets(user_id, [selected.get("id")])
        active = sports_cave_dashboard.get_active_daily_planner_timer(user)
        read_queries = 4
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    return {
        "work_date": selected_date.isoformat(),
        "today": local_today.isoformat(),
        "timezone": PLANNER_TIMEZONE,
        "sheet": selected or {},
        "source_sheet": previous or {},
        "tasks": _task_rows(selected, timers) if selected else [],
        "active_timer": active or {},
        "events": events or [],
        "rollover": rollover or {},
        "review_reminder": (rollover or {}).get("review_reminder") or {},
        "server_now": datetime.now(timezone.utc).isoformat(),
        "performance": {
            "planner_data_ms": elapsed_ms,
            "initial_api_calls": 1,
            "database_transactions": 2 + read_queries,
        },
    }


async def planner_window(_request: Request):
    return HTMLResponse(
        CLIENT_SOURCE,
        headers={
            "Cache-Control": "public, max-age=300",
            "Content-Security-Policy": (
                "default-src 'self'; style-src 'self' 'unsafe-inline'; "
                "script-src 'self' 'unsafe-inline'; connect-src 'self'; "
                "img-src 'self' data:; frame-ancestors 'self'"
            ),
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "same-origin",
        },
    )


async def planner_bootstrap(request: Request):
    claims = _claims(request)
    if not claims:
        return _json({"ok": False, "error": "Access not approved."}, 403)
    try:
        selected_date = _request_date(request)
        payload = _load_sheet_bundle(_user(claims), selected_date)
    except Exception as error:
        return _json({"ok": False, "error": _safe_error(error)}, 503)
    return _json(
        {
            "ok": True,
            "user": {
                "id": claims.get("sub"),
                "display_name": claims.get("display_name") or claims.get("username"),
                "role": claims.get("role"),
            },
            **payload,
        }
    )


def _clean_tasks(value, *, top=False):
    rows = value if isinstance(value, list) else []
    clean = []
    for row in rows[:3] if top else rows[:50]:
        row = dict(row or {})
        clean.append(
            {
                "task": str(row.get("task") or "").strip()[:500],
                "why" if top else "details": str(
                    (row.get("why") if top else row.get("details")) or ""
                ).strip()[:1000],
                "time_blocked": str(row.get("time_blocked") or "").strip()[:80],
                "status": str(row.get("status") or "").strip().casefold()[:40],
                "completed_at": row.get("completed_at"),
                "finished_at": row.get("finished_at"),
                "outcome": str(row.get("outcome") or "").strip().casefold()[:40],
                "completion_method": str(row.get("completion_method") or "").strip().casefold()[:40],
                "skip_reason": str(row.get("skip_reason") or "").strip()[:500],
                "outcome_reason": str(row.get("outcome_reason") or "").strip()[:500],
                "actual_elapsed_seconds": row.get("actual_elapsed_seconds"),
                "time_saved_seconds": row.get("time_saved_seconds"),
                "completed_before_expiry": bool(row.get("completed_before_expiry")),
                "outcome_version": max(int(row.get("outcome_version") or 0), 0),
                "outcome_history": list(row.get("outcome_history") or [])[-20:],
                "reopened_at": row.get("reopened_at"),
                "carried_from": str(row.get("carried_from") or "").strip()[:20],
            }
        )
    if top:
        while len(clean) < 3:
            clean.append({"task": "", "why": "", "time_blocked": "", "status": ""})
    return clean


async def planner_mutation(request: Request):
    claims = _claims(request)
    if not claims:
        return _json({"ok": False, "error": "Access not approved."}, 403)
    try:
        payload = await request.json()
    except Exception:
        return _json({"ok": False, "error": "The planner request was not valid."}, 400)
    if not isinstance(payload, dict):
        return _json({"ok": False, "error": "The planner request was not valid."}, 400)
    action = str(payload.get("action") or "").strip().casefold()
    user = _user(claims)
    try:
        import sports_cave_dashboard

        local_today = datetime.now(SYDNEY_TZ).date()
        if action != "start_timer":
            sports_cave_dashboard.finalise_overdue_daily_planner_days(user, local_today)

        if action == "save_sheet":
            selected_date = date.fromisoformat(str(payload.get("work_date") or ""))
            top_tasks = _clean_tasks(payload.get("top_tasks"), top=True)
            if any(not row["task"] for row in top_tasks):
                raise ValueError("Add all three MIP tasks before saving the plan.")
            planning = dict(payload.get("planning_data") or {})
            planning_data = {
                "main_outcome": str(planning.get("main_outcome") or "").strip()[:1000],
                "fixed_event": str(planning.get("fixed_event") or "").strip()[:1000],
                "notes": str(planning.get("notes") or "").strip()[:4000],
                "carried_forward": list(planning.get("carried_forward") or [])[:50],
                "planned_for": selected_date.isoformat(),
            }
            result = sports_cave_dashboard.save_daily_execution_plan(
                user,
                selected_date,
                PLANNER_TIMEZONE,
                top_tasks,
                _clean_tasks(payload.get("additional_items")),
                planning_data,
                archive_sheet_id=str(payload.get("archive_sheet_id") or "").strip() or None,
            )
        elif action == "save_tasks":
            result = sports_cave_dashboard.save_daily_execution_tasks(
                str(payload.get("sheet_id") or ""),
                _clean_tasks(payload.get("top_tasks"), top=True),
                _clean_tasks(payload.get("additional_items")),
                user=user,
            )
        elif action == "complete_review":
            sheet_id = str(payload.get("sheet_id") or "").strip()
            sheet = sports_cave_dashboard.get_daily_execution_archive_detail(user, sheet_id)
            if not sheet or sheet.get("id") != sheet_id:
                raise ValueError("That Daily Planner sheet is not available for this account.")
            if not sports_cave_dashboard.daily_execution_all_tasks_complete(sheet):
                unresolved = sports_cave_dashboard.daily_execution_outcome_summary(sheet)[
                    "unresolved_tasks"
                ]
                names = ", ".join(unresolved[:5])
                suffix = f": {names}" if names else "."
                raise ValueError(f"Resolve every planned task before completing the Daily Review{suffix}")
            review = dict(payload.get("review") or {})
            ratings = {
                label: max(0, min(int((review.get("ratings") or {}).get(label) or 0), 10))
                for label in sports_cave_dashboard.DAILY_RATING_FIELDS
            }
            review_data = {
                key: str((review.get("review_data") or {}).get(key) or "").strip()[:4000]
                for key in (
                    "completed", "could_not_finish", "worked_well", "improve_tomorrow",
                    "revenue", "noise", "lesson", "protected", "notes",
                )
            }
            review_data["task_outcome_summary"] = sports_cave_dashboard.daily_execution_outcome_summary(
                sheet
            )
            result = sports_cave_dashboard.complete_daily_execution_review(
                sheet_id,
                {
                    "daily_summary": review_data["completed"],
                    "tomorrow_intention": str(review.get("tomorrow_intention") or "").strip()[:4000],
                    "review_data": review_data,
                    "no_grey_zone": {**review_data, "avoided": review_data["could_not_finish"]},
                    "ratings": ratings,
                },
                user=user,
            )
        elif action == "start_timer":
            result = sports_cave_dashboard.start_daily_planner_timer(
                user,
                str(payload.get("sheet_id") or ""),
                str(payload.get("task_type") or ""),
                int(payload.get("task_index") or 0),
                int(payload.get("allocated_seconds") or 0),
                local_today=local_today,
            )
        elif action == "pause_timer":
            result = sports_cave_dashboard.pause_daily_planner_timer(user, payload.get("timer_id"))
        elif action == "resume_timer":
            result = sports_cave_dashboard.resume_daily_planner_timer(user, payload.get("timer_id"))
        elif action == "reset_timer":
            result = sports_cave_dashboard.stop_daily_planner_timer(user, payload.get("timer_id"))
        elif action == "timer_outcome":
            result = sports_cave_dashboard.apply_daily_planner_timer_outcome(
                user,
                payload.get("timer_id"),
                str(payload.get("outcome") or ""),
            )
        elif action == "task_outcome":
            result = sports_cave_dashboard.apply_daily_planner_task_outcome(
                user,
                str(payload.get("sheet_id") or ""),
                str(payload.get("task_type") or ""),
                int(payload.get("task_index") or 0),
                str(payload.get("outcome") or ""),
                timer_id=str(payload.get("timer_id") or "").strip() or None,
                reason=str(payload.get("reason") or "").strip()[:500],
            )
        else:
            return _json({"ok": False, "error": "Unknown Daily Planner action."}, 400)
    except (TypeError, ValueError) as error:
        return _json(_mutation_error_payload(error, retryable=False), 400)
    except Exception as error:
        return _json(_mutation_error_payload(error, retryable=True), 503)
    return _json({"ok": True, "result": result})


async def planner_status(request: Request):
    claims = _claims(request)
    if not claims:
        return _json({"ok": False, "error": "Access not approved."}, 403)
    try:
        import sports_cave_dashboard

        user = _user(claims)
        events = sports_cave_dashboard.reconcile_daily_planner_timers(user)
        timer = sports_cave_dashboard.get_active_daily_planner_timer(user, reconcile=False)
    except Exception as error:
        return _json({"ok": False, "error": _safe_error(error)}, 503)
    return _json(
        {
            "ok": True,
            "timer": timer or {},
            "events": events or [],
            "server_now": datetime.now(timezone.utc).isoformat(),
        }
    )


async def planner_history(request: Request):
    claims = _claims(request)
    if not claims:
        return _json({"ok": False, "error": "Access not approved."}, 403)
    try:
        start_date = _request_date(request, "start")
        end_date = _request_date(request, "end", default=start_date)
        if end_date < start_date:
            raise ValueError("End date must be on or after the start date.")
        import sports_cave_dashboard

        rows = sports_cave_dashboard.list_daily_execution_history(
            _user(claims), start_date, end_date, limit=5000
        )
    except (TypeError, ValueError) as error:
        return _json({"ok": False, "error": _safe_error(error)}, 400)
    except Exception as error:
        return _json({"ok": False, "error": _safe_error(error)}, 503)
    return _json({"ok": True, "start": start_date, "end": end_date, "rows": rows})


async def planner_weekly_review(request: Request):
    claims = _claims(request)
    if not claims:
        return _json({"ok": False, "error": "Access not approved."}, 403)
    try:
        anchor = _request_date(request, "date")
        import sports_cave_dashboard

        week_start, week_end = sports_cave_dashboard.daily_execution_week_bounds(anchor)
        weekly = sports_cave_dashboard.load_daily_execution_weekly_review(
            _user(claims), week_start, week_end, limit=1000
        )
        sheets = weekly["sheets"]
        timers = weekly["timers"]
        summary = sports_cave_dashboard.daily_execution_weekly_summary(
            sheets,
            timers,
            today=datetime.now(SYDNEY_TZ).date(),
        )
    except Exception as error:
        return _json({"ok": False, "error": _safe_error(error)}, 503)
    return _json(
        {
            "ok": True,
            "week_start": week_start,
            "week_end": week_end,
            "summary": summary,
            "sheets": sheets,
        }
    )


DAILY_PLANNER_ROUTE_HANDLERS = (
    (PLANNER_WINDOW_PATH, planner_window, ("GET", "HEAD")),
    (PLANNER_BOOTSTRAP_PATH, planner_bootstrap, ("GET",)),
    (PLANNER_MUTATION_PATH, planner_mutation, ("POST",)),
    (PLANNER_HISTORY_PATH, planner_history, ("GET",)),
    (PLANNER_WEEKLY_REVIEW_PATH, planner_weekly_review, ("GET",)),
    (PLANNER_STATUS_PATH, planner_status, ("GET",)),
)
