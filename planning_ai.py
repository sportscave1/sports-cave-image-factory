"""Request-triggered planning drafts. This module is never imported by planner bootstrap."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
import os
from zoneinfo import ZoneInfo

import httpx


SYDNEY = ZoneInfo("Australia/Sydney")
DAILY_QUESTIONS = (
    ("available_hours", "How many focused hours are genuinely available today?"),
    ("fixed_commitments", "What fixed commitments cannot move?"),
    ("successful_result", "What single result would make today successful?"),
    ("avoided_work", "What important work are you avoiding?"),
    ("remove_work", "What should be deferred, delegated or removed?"),
)
WEEKLY_QUESTIONS = (
    ("successful_week", "What must be true by Sunday for this week to be successful?"),
    ("constraint_or_opportunity", "What is the biggest current constraint or opportunity?"),
    ("fixed_deadline", "Which deadline cannot move?"),
    ("avoided_work", "What work are you avoiding?"),
    ("remove_work", "What can be stopped, delegated or postponed?"),
    ("focused_capacity", "What is the realistic focused-work capacity?"),
    ("guiding_principle", "What principle or quote should guide the week?"),
)


def _object(properties, required=None):
    return {
        "type": "object",
        "properties": properties,
        "required": required or list(properties),
        "additionalProperties": False,
    }


DAILY_PLAN_SCHEMA = _object(
    {
        "main_outcome": {"type": "string"},
        "mips": {
            "type": "array",
            "minItems": 1,
            "maxItems": 3,
            "items": _object(
                {
                    "title": {"type": "string"},
                    "outcome_required": {"type": "string"},
                    "allocated_minutes": {"type": "integer", "minimum": 1, "maximum": 480},
                    "weekly_alignment": {"type": "string"},
                }
            ),
        },
        "supporting_tasks": {
            "type": "array",
            "maxItems": 8,
            "items": _object(
                {
                    "task": {"type": "string"},
                    "allocated_minutes": {"type": "integer", "minimum": 0, "maximum": 240},
                }
            ),
        },
        "defer_delegate_remove": {
            "type": "array",
            "maxItems": 8,
            "items": _object(
                {
                    "task": {"type": "string"},
                    "recommendation": {"type": "string", "enum": ["defer", "delegate", "remove"]},
                    "reason": {"type": "string"},
                }
            ),
        },
        "reasoning_summary": {"type": "array", "maxItems": 6, "items": {"type": "string"}},
        "capacity": _object(
            {
                "available_minutes": {"type": "integer", "minimum": 0, "maximum": 1440},
                "planned_minutes": {"type": "integer", "minimum": 0, "maximum": 1440},
                "reserve_percentage": {"type": "integer", "minimum": 0, "maximum": 100},
                "warning": {"type": "string"},
            }
        ),
    }
)


WEEKLY_PLAN_SCHEMA = _object(
    {
        "theme": {"type": "string"},
        "quote": _object({"text": {"type": "string"}, "author": {"type": "string"}}),
        "objectives": {
            "type": "array",
            "minItems": 1,
            "maxItems": 3,
            "items": _object(
                {
                    "title": {"type": "string"},
                    "measurable_target": {"type": "string"},
                    "alignment": {"type": "string"},
                    "tactics": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 10,
                        "items": _object(
                            {
                                "action": {"type": "string"},
                                "due_day": {
                                    "type": "string",
                                    "enum": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
                                },
                                "estimated_minutes": {"type": "integer", "minimum": 1, "maximum": 600},
                            }
                        ),
                    },
                }
            ),
        },
        "defer_delegate_remove": {
            "type": "array",
            "maxItems": 10,
            "items": _object(
                {
                    "task": {"type": "string"},
                    "recommendation": {"type": "string", "enum": ["defer", "delegate", "remove"]},
                    "reason": {"type": "string"},
                }
            ),
        },
        "capacity": _object(
            {
                "available_minutes": {"type": "integer", "minimum": 0, "maximum": 10080},
                "planned_minutes": {"type": "integer", "minimum": 0, "maximum": 10080},
                "assessment": {"type": "string"},
            }
        ),
        "expected_execution_score": {"type": "integer", "minimum": 0, "maximum": 100},
    }
)


DAILY_INSTRUCTIONS = """You are the Sports Cave Daily Planning Coach. Return only the requested structured draft.
Use only supplied saved facts and user answers. Never claim work was completed without evidence.
Choose no more than three major execution tasks and make one clearly decisive. Normally use two focused work blocks.
Plan only 70-80% of realistic focused capacity and preserve 20-30% for orders, communication and unexpected work.
Prefer work that advances the current weekly objectives and 12-week objective. Challenge avoidance and low-value busywork.
Do not overload the day because earlier work was missed. Remove, defer or delegate before adding more."""

WEEKLY_INSTRUCTIONS = """You are the Sports Cave Weekly Planning Coach. Return only the requested structured draft.
Use only supplied saved facts and user answers. Never invent business metrics or completed work.
Create one theme, one quote, no more than three measurable objectives, and 7-10 concrete tactics in total.
Objectives must describe measurable results, not vague activity. Align the plan with the 12-week objective.
Challenge avoidance, protect realistic focused capacity, and identify work to defer, delegate or remove."""


class PlanningAIError(RuntimeError):
    def __init__(self, message, *, code="planning_ai_failed", retryable=True):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


def next_question(kind, answers):
    questions = DAILY_QUESTIONS if kind == "daily" else WEEKLY_QUESTIONS
    answers = dict(answers or {})
    for key, label in questions:
        if not str(answers.get(key) or "").strip():
            return {"key": key, "label": label}
    return None


def questions_for_context(kind, context, answers=None):
    """Return only questions that do not already have an authoritative answer."""
    answers = dict(answers or {})
    today_plan = dict((context or {}).get("today_plan") or {})
    yesterday = dict((context or {}).get("yesterday_review") or {})
    current_week = dict((context or {}).get("current_week") or {})
    supplied = {key for key, value in answers.items() if str(value or "").strip()}
    inferred = set()
    if kind == "daily":
        if str(today_plan.get("fixed_event") or "").strip():
            inferred.add("fixed_commitments")
        if str(today_plan.get("main_outcome") or "").strip():
            inferred.add("successful_result")
        if str(yesterday.get("blockers") or "").strip():
            inferred.add("avoided_work")
        questions = DAILY_QUESTIONS
    else:
        if current_week.get("objectives"):
            inferred.add("successful_week")
        if str(current_week.get("quote") or "").strip():
            inferred.add("guiding_principle")
        if str(yesterday.get("blockers") or "").strip():
            inferred.add("avoided_work")
        questions = WEEKLY_QUESTIONS
    return [
        {"key": key, "label": label}
        for key, label in questions
        if key not in supplied and key not in inferred
    ]


def _review_facts(sheet):
    review = dict((sheet or {}).get("review_data") or {})
    return {
        "date": str((sheet or {}).get("sheet_date") or ""),
        "status": str((sheet or {}).get("status") or ""),
        "wins": str(review.get("worked_well") or review.get("completed") or "")[:500],
        "blockers": str(review.get("could_not_finish") or review.get("noise") or "")[:500],
        "lesson": str(review.get("lesson") or review.get("improve_tomorrow") or "")[:500],
    }


def _planning_date(value, fallback):
    if not value:
        return fallback
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _saved_business_metrics(kind):
    if kind != "weekly":
        return {}
    metrics = {}
    try:
        import supabase_backend

        rows = supabase_backend.list_meta_ad_insights(
            date_range="last_30_days", limit=1000
        )
        if rows:
            spend = sum(float(row.get("spend") or 0) for row in rows)
            purchases = sum(float(row.get("purchases") or 0) for row in rows)
            revenue = sum(float(row.get("purchase_value") or 0) for row in rows)
            impressions = sum(float(row.get("impressions") or 0) for row in rows)
            clicks = sum(float(row.get("clicks") or 0) for row in rows)
            metrics["saved_ads_last_30_days"] = {
                "spend": round(spend, 2),
                "purchases": round(purchases, 2),
                "revenue": round(revenue, 2),
                "roas": round(revenue / spend, 2) if spend else 0.0,
                "ctr_percentage": round(clicks / impressions * 100, 2)
                if impressions
                else 0.0,
            }
    except Exception:
        pass
    try:
        import seo_live_analytics

        snapshot = seo_live_analytics.default_reader().snapshot(
            preset="Last 28 days", compare=False
        )
        current = dict(snapshot.get("current") or {})
        allowed = (
            "gsc_clicks",
            "gsc_impressions",
            "ga4_sessions",
            "shopify_orders",
            "shopify_revenue",
            "conversion_rate",
        )
        saved = {
            key: float(current[key])
            for key in allowed
            if current.get(key) is not None
        }
        if saved:
            metrics["saved_search_sales_last_28_days"] = saved
    except Exception:
        pass
    return metrics


def build_planning_context(user, kind, answers, *, now=None, target_date=None):
    import sports_cave_dashboard
    import sports_sales_calendar

    now = now or datetime.now(timezone.utc)
    local_today = now.astimezone(SYDNEY).date()
    plan_date = _planning_date(target_date, local_today)
    week_start, week_end = sports_cave_dashboard.daily_execution_week_bounds(plan_date)
    user_id = sports_cave_dashboard.daily_execution_user_id(user)
    week_bundle = sports_cave_dashboard.load_daily_planner_week_plan(user, plan_date)
    backend = sports_cave_dashboard.get_supabase_backend()
    lookback_start = min(local_today, plan_date) - timedelta(days=28 if kind == "weekly" else 7)
    history_end = max(local_today, plan_date)
    sheets = backend.list_daily_execution_sheets_for_reporting(
        user_id, lookback_start.isoformat(), history_end.isoformat(), limit=60
    )
    sheets = [sports_cave_dashboard._normalise_daily_sheet(row) for row in sheets or []]
    sheet_ids = [row.get("id") for row in sheets if row.get("id")]
    timers = backend.list_daily_execution_timers_for_sheets(user_id, sheet_ids) if sheet_ids else []
    instances = sports_cave_dashboard.daily_execution_weekly_task_instances(
        sheets, timers, today=local_today
    )
    outcomes = {"completed": 0, "did_not_finish": 0, "skipped": 0, "unresolved": 0}
    planned_seconds = 0
    focused_seconds = 0
    carry_forwards = []
    for task in instances:
        outcome = str(task.get("outcome") or "unresolved")
        outcomes[outcome if outcome in outcomes else "unresolved"] += 1
        planned_seconds += int(task.get("allocated_seconds") or 0)
        focused_seconds += int(task.get("actual_elapsed_seconds") or 0)
        if task.get("carried_from"):
            carry_forwards.append(str(task.get("task") or "")[:180])
    current_plan = dict(week_bundle.get("plan") or {})
    cycle = dict(week_bundle.get("cycle") or {})
    today_sheet = next((row for row in sheets if str(row.get("sheet_date")) == plan_date.isoformat()), {})
    yesterday_sheet = next((row for row in sheets if str(row.get("sheet_date")) == (plan_date - timedelta(days=1)).isoformat()), {})
    try:
        dashboard_tasks = sports_cave_dashboard.list_tasks(status="open", limit=12)
    except Exception:
        dashboard_tasks = []
    events = sports_cave_dashboard.build_home_event_rows(
        sports_cave_dashboard.load_calendar_events(), local_today, limit=8
    )
    try:
        weekly_work = sports_cave_dashboard.build_home_weekly_work_snapshot(user, now.astimezone(SYDNEY))
    except Exception:
        weekly_work = {"metrics": {}, "completed_work": []}
    archive = backend.list_daily_planner_cycle_archive(user_id, plan_date)
    historical_plans = archive.get("plans") or []
    weekly_trends = []
    for plan in historical_plans[-4:]:
        score = sports_cave_dashboard.weekly_tactic_execution_summary(plan)
        weekly_trends.append(
            {
                "week_number": int(plan.get("week_number") or 0),
                "theme": str(plan.get("theme") or "")[:200],
                "tactic_execution_percentage": round(score["percentage"], 1),
                "review_submitted": bool(plan.get("review_submitted_at")),
            }
        )
    context = {
        "kind": kind,
        "account": {"display_name": str(user.get("display_name") or user.get("username") or "")[:120]},
        "today_sydney": local_today.isoformat(),
        "planning_date_sydney": plan_date.isoformat(),
        "cycle": {
            "name": str(cycle.get("name") or "")[:200],
            "overall_objective": str(cycle.get("overall_objective") or "")[:1000],
            "week_number": int(week_bundle.get("week_number") or 0),
        },
        "current_week": {
            "range": [week_start.isoformat(), week_end.isoformat()],
            "theme": str(current_plan.get("theme") or "")[:300],
            "quote": str(current_plan.get("quote_text") or "")[:500],
            "objectives": [
                {
                    "title": str(objective.get("title") or "")[:300],
                    "target": str(objective.get("measurable_target") or "")[:500],
                    "tactics": [
                        {
                            "action": str(tactic.get("action") or "")[:300],
                            "status": str(tactic.get("status") or "open"),
                            "due_day": int(tactic.get("due_day") or 0),
                        }
                        for tactic in (objective.get("tactics") or [])[:12]
                    ],
                }
                for objective in (current_plan.get("objectives") or [])[:3]
            ],
        },
        "today_plan": {
            "main_outcome": str((today_sheet.get("planning_data") or {}).get("main_outcome") or "")[:500],
            "fixed_event": str((today_sheet.get("planning_data") or {}).get("fixed_event") or "")[:500],
            "tasks": [row["task"][:300] for row in sports_cave_dashboard.daily_execution_task_rows(today_sheet, [])[:12]],
        },
        "yesterday_review": _review_facts(yesterday_sheet),
        "recent_reviews": [_review_facts(sheet) for sheet in sheets[-7:]],
        "recent_task_outcomes": outcomes,
        "planned_minutes": round(planned_seconds / 60),
        "focused_minutes": round(focused_seconds / 60),
        "repeated_carry_forwards": carry_forwards[:10],
        "dashboard_tasks": [
            {
                "task": str(row.get("task") or row.get("title") or "")[:300],
                "deadline": str(row.get("due_date") or row.get("deadline") or "")[:40],
                "area": str(row.get("section") or row.get("category") or "")[:120],
            }
            for row in dashboard_tasks[:12]
        ],
        "recent_meaningful_work": [
            {
                "work": str(row.get("work") or "")[:300],
                "area": str(row.get("area") or "")[:120],
                "status": str(row.get("status") or "")[:80],
            }
            for row in (weekly_work.get("completed_work") or [])[:12]
        ],
        "work_metrics": dict(weekly_work.get("metrics") or {}),
        "business_metrics": _saved_business_metrics(kind),
        "upcoming_events": [
            {"name": row["name"], "type": row["type"], "start_date": row["start_date"], "status": row["status"]}
            for row in events
        ],
        "weekly_trends": weekly_trends,
        "answers": {str(key): str(value)[:1000] for key, value in dict(answers or {}).items()},
    }
    return context


def context_facts(context):
    """Build the evidence list shown in the UI from saved context, not model text."""
    facts = []
    cycle = dict((context or {}).get("cycle") or {})
    current_week = dict((context or {}).get("current_week") or {})
    today_plan = dict((context or {}).get("today_plan") or {})
    outcomes = dict((context or {}).get("recent_task_outcomes") or {})
    if cycle.get("week_number"):
        facts.append(
            f"12-week cycle week {cycle['week_number']}: "
            f"{cycle.get('overall_objective') or 'no overall objective saved'}"
        )
    if current_week.get("theme") or current_week.get("objectives"):
        facts.append(
            f"Selected week: {current_week.get('theme') or 'no theme'}; "
            f"{len(current_week.get('objectives') or [])} saved objective(s)"
        )
    if today_plan.get("tasks"):
        facts.append(
            f"Selected Daily Plan contains {len(today_plan['tasks'])} saved task(s)"
        )
    total_outcomes = sum(int(value or 0) for value in outcomes.values())
    if total_outcomes:
        facts.append(
            "Recent task outcomes: "
            f"{int(outcomes.get('completed') or 0)} completed, "
            f"{int(outcomes.get('did_not_finish') or 0)} did not finish, "
            f"{int(outcomes.get('skipped') or 0)} skipped"
        )
    if (context or {}).get("planned_minutes") or (context or {}).get("focused_minutes"):
        facts.append(
            f"Recent planned/focused time: {int((context or {}).get('planned_minutes') or 0)} / "
            f"{int((context or {}).get('focused_minutes') or 0)} minutes"
        )
    carry = list((context or {}).get("repeated_carry_forwards") or [])
    if carry:
        facts.append(f"Repeated carry-forward work: {', '.join(carry[:3])}")
    events = list((context or {}).get("upcoming_events") or [])
    if events:
        facts.append(
            "Nearest saved event/calendar items: "
            + ", ".join(str(row.get("name") or "") for row in events[:3])
        )
    metrics = dict((context or {}).get("business_metrics") or {})
    if metrics:
        facts.append("Saved Ads/search/sales aggregates were available for this draft")
    return [" ".join(str(fact).split())[:500] for fact in facts[:10]]


def _response_text(payload):
    refusal = ""
    for output in payload.get("output") or []:
        if output.get("type") != "message":
            continue
        for item in output.get("content") or []:
            if item.get("type") == "refusal":
                refusal = str(item.get("refusal") or "")
            if item.get("type") == "output_text" and item.get("text"):
                return str(item["text"])
    if refusal:
        raise PlanningAIError(
            "Planning help could not produce this draft. Adjust the answers and try again.",
            code="planning_ai_refused",
            retryable=True,
        )
    raise PlanningAIError(
        "Planning help returned no usable draft. Try again.",
        code="planning_ai_empty_output",
        retryable=True,
    )


def validate_draft(kind, draft):
    if not isinstance(draft, dict):
        raise PlanningAIError("Planning help returned an invalid draft.", code="planning_ai_invalid_output")
    if kind == "daily":
        mips = draft.get("mips")
        if not isinstance(mips, list) or not 1 <= len(mips) <= 3:
            raise PlanningAIError("Daily planning help must return one to three major tasks.", code="planning_ai_invalid_output")
        required = {"main_outcome", "supporting_tasks", "defer_delegate_remove", "reasoning_summary", "capacity"}
        if not required.issubset(draft):
            raise PlanningAIError("Daily planning help returned an incomplete draft.", code="planning_ai_invalid_output")
        return draft
    objectives = draft.get("objectives")
    if not isinstance(objectives, list) or not 1 <= len(objectives) <= 3:
        raise PlanningAIError("Weekly planning help must return one to three objectives.", code="planning_ai_invalid_output")
    tactic_count = sum(len(objective.get("tactics") or []) for objective in objectives if isinstance(objective, dict))
    if not 7 <= tactic_count <= 10:
        raise PlanningAIError("Weekly planning help must return seven to ten tactics.", code="planning_ai_invalid_output")
    required = {"theme", "quote", "defer_delegate_remove", "capacity", "expected_execution_score"}
    if not required.issubset(draft):
        raise PlanningAIError("Weekly planning help returned an incomplete draft.", code="planning_ai_invalid_output")
    return draft


def generate_planning_draft(kind, context, *, client=None):
    if kind not in {"daily", "weekly"}:
        raise PlanningAIError("Choose daily or weekly planning help.", code="planning_ai_validation", retryable=False)
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("OPENAI_PLANNING_MODEL", "").strip()
    if not api_key or not model:
        raise PlanningAIError(
            "Planning help is not configured. Set OPENAI_API_KEY and OPENAI_PLANNING_MODEL.",
            code="planning_ai_not_configured",
            retryable=False,
        )
    schema = DAILY_PLAN_SCHEMA if kind == "daily" else WEEKLY_PLAN_SCHEMA
    instructions = DAILY_INSTRUCTIONS if kind == "daily" else WEEKLY_INSTRUCTIONS
    request_payload = {
        "model": model,
        "store": False,
        "instructions": instructions,
        "input": [{"role": "user", "content": json.dumps(context, ensure_ascii=True, separators=(",", ":"))}],
        "max_output_tokens": 5000,
        "text": {
            "format": {
                "type": "json_schema",
                "name": f"sports_cave_{kind}_plan_draft",
                "strict": True,
                "schema": schema,
            }
        },
    }
    timeout = max(5.0, min(float(os.getenv("OPENAI_PLANNING_TIMEOUT_SECONDS", "25")), 60.0))
    own_client = client is None
    client = client or httpx.Client(timeout=timeout)
    try:
        response = client.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=request_payload,
        )
        if response.status_code >= 400:
            raise PlanningAIError(
                "Planning help could not reach the model service. Try again shortly.",
                code="planning_ai_upstream_error",
                retryable=response.status_code >= 429,
            )
        payload = response.json()
        draft = json.loads(_response_text(payload))
        draft = validate_draft(kind, draft)
        draft["influencing_facts"] = context_facts(context)
        return draft
    except PlanningAIError:
        raise
    except (httpx.TimeoutException, httpx.NetworkError) as error:
        raise PlanningAIError(
            "Planning help timed out. Your planner was not changed; try again.",
            code="planning_ai_timeout",
            retryable=True,
        ) from error
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        raise PlanningAIError(
            "Planning help returned an invalid draft. Your planner was not changed; regenerate it.",
            code="planning_ai_invalid_output",
            retryable=True,
        ) from error
    finally:
        if own_client:
            client.close()
