"""Sports Cave SEO Growth Intelligence orchestration, reports and workflow."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import time
import uuid

from dotenv import load_dotenv
import requests

from activity_log import record_activity_log
import google_seo
import google_seo_import
import google_seo_phase4
import analytics_reporting
import os_accounts
import seo_live_analytics
import seo_technical_audit
import seo_workspace as seo_workspace


GROWTH_MIGRATION = "20260814_seo_growth_intelligence_v1.sql"
WORKSPACE_KEY = google_seo_phase4.WORKSPACE_KEY
BASE_DIR = Path(__file__).resolve().parent
SNAPSHOT_VERSION = "seo-growth-snapshot-v1"
PROMPT_VERSION = "seo-growth-master-prompt-v1"
REPORT_SCHEMA_VERSION = "seo-growth-report-schema-v1"
OPENAI_RESPONSES_ENDPOINT = "https://api.openai.com/v1/responses"
PIPELINE_LEASE_SECONDS = 30 * 60
PIPELINE_STAGES = (
    ("connection_health", "Connection health"),
    ("gsc_daily_sync", "GSC fourteen-day refresh"),
    ("gsc_fresh_sync", "GSC preliminary current date"),
    ("ga4_daily_sync", "GA4 fourteen-day refresh"),
    ("shopify_pages", "Shopify page refresh"),
    ("shopify_orders", "Shopify order refresh"),
    ("ga4_transactions", "GA4 transaction refresh"),
    ("url_mapping", "URL mapping"),
    ("revenue_reconciliation", "Revenue reconciliation"),
    ("joined_reporting", "Joined reporting snapshots"),
    ("technical_audit", "Technical URL audit"),
    ("opportunities", "Opportunity detection"),
    ("measurements", "28/56/90-day measurements"),
)
ANALYTICS_REFRESH_STAGES = (
    ("schema_check", "Analytics schema"),
    ("gsc_daily_sync", "GSC recent refresh"),
    ("gsc_fresh_sync", "GSC preliminary current date"),
    ("ga4_daily_sync", "GA4 recent refresh"),
    ("ga4_report_contracts", "GA4 report snapshots"),
    ("shopify_saved_data", "Shopify/Supabase saved data"),
    ("url_mapping", "URL mapping"),
    ("revenue_reconciliation", "Revenue reconciliation"),
    ("joined_reporting", "Joined reporting snapshots"),
    ("source_health", "Source health"),
)
ANALYSIS_MODES = (
    "Generate Weekly Growth Report",
    "Find New and Trending Keywords",
    "Find Ranking Gains and Losses",
    "Find Near-Page-One Opportunities",
    "Find Weak CTR Opportunities",
    "Diagnose Landing Pages",
    "Find Product SEO Gaps",
    "Build 90-Day SEO Strategy",
    "Create Weekly VA Plan",
    "Explain These Results",
    "Prepare for ChatGPT",
)
RECOMMENDATION_STATUSES = (
    "draft",
    "awaiting_approval",
    "approved",
    "edited_and_approved",
    "rejected",
    "snoozed",
    "converted_to_task",
    "completed",
    "measuring",
    "measured",
)
TASK_STATUSES = (
    "approved",
    "assigned",
    "in_progress",
    "completed",
    "measuring",
    "measured",
    "cancelled",
)
FORBIDDEN_FIELD_RE = re.compile(
    r"(access_token|refresh_token|oauth|api_key|secret|password|credential|"
    r"customer_(?:name|email|phone|address)|billing|shipping|address|email)",
    re.IGNORECASE,
)
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)


def _activity_actor_metadata_from_identifier(actor):
    clean_actor = str(actor or "").strip()[:200]
    metadata = {"actor_id": clean_actor} if clean_actor else {}
    try:
        account = os_accounts.DEFAULT_STORE.get_user(clean_actor) if clean_actor else {}
    except Exception:
        account = {}
    if account:
        metadata.update(
            {
                "actor_display": account.get("display_name") or account.get("username") or clean_actor,
                "actor_email": account.get("email") or "",
                "actor_role": account.get("role") or "",
                "actor_timezone": os_accounts.timezone_for_user(account),
            }
        )
    return metadata


class SEOGrowthError(RuntimeError):
    def __init__(self, message, *, code="seo_growth_error", retryable=True):
        super().__init__(str(message or "SEO Growth Intelligence could not complete the request."))
        self.public_message = str(message or "SEO Growth Intelligence could not complete the request.")[:300]
        self.code = str(code or "seo_growth_error")[:100]
        self.retryable = bool(retryable)


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0)


def _as_date(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _iso(value):
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _decimal(value):
    try:
        return Decimal(str(value or "0"))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _integer(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _json_safe(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return _iso(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def sanitize_for_chatgpt(value, *, max_list=60):
    """Remove secrets/customer fields and keep snapshots compact enough for prompts."""
    if isinstance(value, dict):
        clean = {}
        for key, item in value.items():
            key_text = str(key or "")
            if FORBIDDEN_FIELD_RE.search(key_text):
                continue
            clean[key_text] = sanitize_for_chatgpt(item, max_list=max_list)
        return clean
    if isinstance(value, (list, tuple, set)):
        return [sanitize_for_chatgpt(item, max_list=max_list) for item in list(value)[:max_list]]
    if isinstance(value, str):
        return EMAIL_RE.sub("[redacted email]", value)[:4000]
    return _json_safe(value)


def _safe_error(error):
    if isinstance(error, SEOGrowthError):
        return error.code, error.public_message
    if isinstance(error, google_seo_phase4.SEOPhase4Error):
        return error.code, error.public_message
    if isinstance(error, google_seo_import.SEOImportError):
        return error.code, error.public_message
    if isinstance(error, google_seo.GoogleSEOError):
        return str(error.code or "google_error")[:100], str(error.public_message)[:300]
    return "seo_growth_failed", "SEO Growth Intelligence could not complete this stage. It is safe to retry."


def _stable_id(prefix, *parts):
    payload = "|".join(str(part or "") for part in parts)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
    return f"{prefix}-{digest}"


def report_json_schema():
    recommendation = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "recommendation_id": {"type": "string"},
            "target_keyword": {"type": "string"},
            "keyword_cluster": {"type": "string"},
            "target_market": {"type": "string"},
            "current_page": {"type": "string"},
            "recommended_page": {"type": "string"},
            "current_position": {"type": ["number", "null"]},
            "previous_position": {"type": ["number", "null"]},
            "impressions": {"type": ["number", "null"]},
            "clicks": {"type": ["number", "null"]},
            "revenue_or_conversion_evidence": {"type": "string"},
            "recommended_action": {"type": "string"},
            "priority": {"type": "string"},
            "reason": {"type": "string"},
            "confidence": {"type": ["number", "null"]},
            "measurement_date": {"type": "string"},
            "requires_approval": {"type": "boolean"},
            "proposed_owner": {"type": "string"},
        },
        "required": [
            "recommendation_id", "target_keyword", "keyword_cluster", "target_market",
            "current_page", "recommended_page", "current_position", "previous_position",
            "impressions", "clicks", "revenue_or_conversion_evidence",
            "recommended_action", "priority", "reason", "confidence",
            "measurement_date", "requires_approval", "proposed_owner",
        ],
    }
    string_list = {"type": "array", "items": {"type": "string"}}
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "report_id": {"type": "string"},
            "report_type": {"type": "string"},
            "date_range": {"type": "string"},
            "comparison_range": {"type": "string"},
            "market": {"type": "string"},
            "device": {"type": "string"},
            "data_through": {"type": "string"},
            "executive_summary": {"type": "string"},
            "important_changes": string_list,
            "trending_searches": string_list,
            "ranking_gains": string_list,
            "ranking_losses": string_list,
            "quick_wins": string_list,
            "landing_page_findings": string_list,
            "revenue_supported_findings": string_list,
            "risks": string_list,
            "recommendations": {"type": "array", "items": recommendation},
            "weekly_plan": string_list,
            "longer_term_strategy": string_list,
            "measurement_requirements": string_list,
            "data_limitations": string_list,
        },
        "required": [
            "report_id", "report_type", "date_range", "comparison_range", "market",
            "device", "data_through", "executive_summary", "important_changes",
            "trending_searches", "ranking_gains", "ranking_losses", "quick_wins",
            "landing_page_findings", "revenue_supported_findings", "risks",
            "recommendations", "weekly_plan", "longer_term_strategy",
            "measurement_requirements", "data_limitations",
        ],
    }


def _coerce_report_list(payload, key):
    value = payload.get(key)
    if isinstance(value, list):
        return [str(item or "")[:1000] for item in value if str(item or "").strip()]
    if str(value or "").strip():
        return [str(value).strip()[:1000]]
    return []


def validate_structured_report(payload):
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, dict):
        raise SEOGrowthError("The OpenAI report did not return a JSON object.", code="invalid_report_schema", retryable=False)
    payload = sanitize_for_chatgpt(payload)
    required = report_json_schema()["required"]
    missing = [field for field in required if field not in payload]
    if missing:
        raise SEOGrowthError(
            "The OpenAI report was missing required fields.",
            code="invalid_report_schema",
            retryable=False,
        )
    for key in (
        "important_changes", "trending_searches", "ranking_gains", "ranking_losses",
        "quick_wins", "landing_page_findings", "revenue_supported_findings", "risks",
        "weekly_plan", "longer_term_strategy", "measurement_requirements",
        "data_limitations",
    ):
        payload[key] = _coerce_report_list(payload, key)
    recommendations = []
    for index, row in enumerate(payload.get("recommendations") or [], start=1):
        if not isinstance(row, dict):
            continue
        clean = dict(row)
        clean.setdefault("recommendation_id", f"recommendation-{index}")
        clean.setdefault("requires_approval", True)
        clean["requires_approval"] = bool(clean.get("requires_approval"))
        recommendations.append(clean)
    payload["recommendations"] = recommendations[:25]
    return payload


def _compact_metrics(metrics):
    metrics = dict(metrics or {})
    wanted = (
        "confirmed_organic_revenue", "ga4_attributed_revenue", "organic_orders",
        "ga4_attributed_purchases", "organic_sessions", "organic_clicks",
        "organic_impressions", "ctr", "average_position", "shopify_confirmed_by_currency",
        "ga4_currencies", "search_scope_note",
    )
    return {key: _json_safe(metrics.get(key)) for key in wanted if key in metrics}


def _compact_rows(rows, fields, *, limit=20):
    result = []
    for row in list(rows or [])[:limit]:
        result.append({field: _json_safe(dict(row).get(field)) for field in fields if field in dict(row)})
    return result


def build_analysis_snapshot(reporting_snapshot, workspace_state, *, analysis_mode, filters):
    reporting_snapshot = dict(reporting_snapshot or {})
    workspace_state = dict(workspace_state or {})
    health = reporting_snapshot.get("health") or {}
    filter_values = dict(filters or reporting_snapshot.get("filters") or {})
    opportunities = _compact_rows(
        reporting_snapshot.get("opportunities") or [],
        ("opportunity_type", "priority_score", "title", "query", "normalized_path", "evidence", "measurement_date"),
        limit=25,
    )
    top_pages = _compact_rows(
        reporting_snapshot.get("top_pages") or [],
        (
            "canonical_url", "title", "page_type", "clicks", "impressions", "average_position",
            "sessions", "attributed_purchases", "confirmed_orders", "confirmed_revenue", "currencies",
        ),
        limit=20,
    )
    top_queries = _compact_rows(
        reporting_snapshot.get("top_queries") or [],
        ("query", "clicks", "impressions", "ctr", "average_position", "commercial_score"),
        limit=30,
    )
    keywords = _compact_rows(
        seo_workspace.active_records(workspace_state, "keywords"),
        (
            "keyword", "buyer_intent", "page_type", "priority", "target_market",
            "target_url", "mapping_status", "notes",
        ),
        limit=40,
    )
    mappings = _compact_rows(
        seo_workspace.active_records(workspace_state, "keyword_mappings"),
        ("primary_keyword", "page_type", "target_page", "supporting_keywords", "market", "mapping_status"),
        limit=40,
    )
    current_work = {
        "approved_weekly_plan": list(workspace_state.get("settings", {}).get("weekly_targets") or seo_workspace.WEEKLY_TARGETS),
        "open_blog_records": _compact_rows(
            seo_workspace.active_records(workspace_state, "blog_records"),
            ("article_title", "primary_keyword", "target_market", "status", "due_date", "owner"),
            limit=20,
        ),
        "open_outreach_records": _compact_rows(
            seo_workspace.active_records(workspace_state, "outreach_records"),
            ("site_creator", "website", "target_page", "status", "owner", "due_date"),
            limit=20,
        ),
    }
    limitations = []
    if not reporting_snapshot.get("ready"):
        limitations.append(str(reporting_snapshot.get("reason") or "Saved reporting snapshot is not ready."))
    if not health.get("reconciliation_through_date"):
        limitations.append("Confirmed Shopify organic revenue is unavailable or not reconciled yet.")
    if filter_values.get("search") in {"Brand", "Non-brand"}:
        limitations.append("Brand and non-brand filters apply to query-level GSC metrics; GA4 and Shopify are page/session datasets.")
    snapshot = {
        "snapshot_version": SNAPSHOT_VERSION,
        "prompt_version": PROMPT_VERSION,
        "analysis_mode": str(analysis_mode or ANALYSIS_MODES[0]),
        "generated_at": _iso(utc_now()),
        "filters": filter_values,
        "data_freshness": {
            "data_status": health.get("data_status") or "",
            "data_through": health.get("common_reporting_date") or "",
            "latest_gsc_date": health.get("latest_gsc_date") or "",
            "latest_ga4_date": health.get("latest_ga4_date") or "",
            "latest_shopify_date": health.get("latest_shopify_date") or "",
            "reconciliation_through_date": health.get("reconciliation_through_date") or "",
            "snapshot_refreshed_at": health.get("reporting_snapshot_refreshed_at") or "",
        },
        "current_metrics": _compact_metrics(reporting_snapshot.get("current")),
        "previous_metrics": _compact_metrics(reporting_snapshot.get("previous")),
        "daily_trend": _compact_rows(
            reporting_snapshot.get("daily_trend") or [],
            (
                "date", "confirmed_organic_revenue", "organic_orders", "organic_sessions",
                "organic_clicks", "organic_impressions", "ctr", "average_position",
            ),
            limit=120,
        ),
        "previous_daily_trend": _compact_rows(
            reporting_snapshot.get("previous_daily_trend") or [],
            (
                "date", "confirmed_organic_revenue", "organic_orders", "organic_sessions",
                "organic_clicks", "organic_impressions", "ctr", "average_position",
            ),
            limit=120,
        ),
        "current_opportunities": opportunities,
        "landing_page_performance": top_pages,
        "search_query_performance": top_queries,
        "existing_keyword_records": keywords,
        "existing_keyword_mappings": mappings,
        "approved_tasks": [],
        "completed_work": current_work,
        "prior_measurement_results": [],
        "known_data_limitations": limitations,
    }
    return sanitize_for_chatgpt(snapshot)


def build_human_summary(snapshot):
    metrics = snapshot.get("current_metrics") or {}
    previous = snapshot.get("previous_metrics") or {}
    freshness = snapshot.get("data_freshness") or {}
    lines = [
        f"Analysis mode: {snapshot.get('analysis_mode') or ''}",
        f"Data through: {freshness.get('data_through') or 'Not available'}",
        f"Current period: {(snapshot.get('filters') or {}).get('start_date') or ''} to {(snapshot.get('filters') or {}).get('end_date') or ''}",
        f"Comparison period: {(snapshot.get('filters') or {}).get('previous_start_date') or ''} to {(snapshot.get('filters') or {}).get('previous_end_date') or ''}",
    ]
    for label, key in (
        ("Confirmed organic revenue", "confirmed_organic_revenue"),
        ("Organic orders", "organic_orders"),
        ("Organic sessions", "organic_sessions"),
        ("Organic clicks", "organic_clicks"),
        ("Organic impressions", "organic_impressions"),
        ("CTR", "ctr"),
        ("Average position", "average_position"),
    ):
        if key in metrics:
            lines.append(f"{label}: {metrics.get(key)} (previous: {previous.get(key)})")
    if snapshot.get("known_data_limitations"):
        lines.append("Known limitations: " + "; ".join(snapshot["known_data_limitations"]))
    return "\n".join(lines)


def build_master_prompt(snapshot):
    return f"""You are analysing Sports Cave SEO growth using only the supplied saved evidence.

ANALYSIS MODE
{snapshot.get('analysis_mode') or ANALYSIS_MODES[0]}

RULES
- Use only the supplied Sports Cave evidence.
- Do not invent rankings, revenue, search volume, dates, products or tasks.
- Separate facts from inference.
- State when evidence is insufficient.
- Prefer improving an existing relevant page before proposing a new page.
- Do not recommend duplicate pages targeting the same search intent.
- Prioritise AU, US and UK appropriately.
- Never publish changes or imply website changes are automatic.
- Never include credentials, tokens, customer information or raw order records.
- Produce a clear owner summary and an actionable weekly plan.
- Every recommendation must say what should be measured after 28, 56 and 90 days.

Return the report using the required structured report fields when the in-app API is used. In manual mode, use the same sections in plain text.

SANITISED SPORTS CAVE EVIDENCE
{json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True)}
"""


def build_analysis_bundle(reporting_snapshot, workspace_state, *, analysis_mode, filters):
    snapshot = build_analysis_snapshot(
        reporting_snapshot,
        workspace_state,
        analysis_mode=analysis_mode,
        filters=filters,
    )
    return {
        "snapshot": snapshot,
        "snapshot_json": json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True),
        "summary": build_human_summary(snapshot),
        "prompt": build_master_prompt(snapshot),
        "analysis_mode": snapshot.get("analysis_mode") or analysis_mode,
        "data_through": (snapshot.get("data_freshness") or {}).get("data_through") or "",
        "snapshot_version": SNAPSHOT_VERSION,
        "prompt_version": PROMPT_VERSION,
    }


class PostgresSEOGrowthStore:
    def __init__(self, phase4_store=None):
        self.phase4_store = phase4_store or google_seo_phase4.default_phase4_store()
        self._schema_ready = False

    def _backend(self):
        return self.phase4_store._backend()

    def ensure_schema(self):
        if self._schema_ready:
            return
        self.phase4_store.ensure_schema()
        migration = BASE_DIR / "migrations" / GROWTH_MIGRATION
        if not migration.is_file():
            raise SEOGrowthError("SEO Growth Intelligence migration is unavailable.", code="migration_missing", retryable=False)
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(migration.read_text(encoding="utf-8"))
            connection.commit()
        self._schema_ready = True

    def queue_pipeline_run(self, *, mode="daily", requested_by="render-cron", run_id=""):
        self.ensure_schema()
        run_id = str(run_id or uuid.uuid4())
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT * FROM seo_growth_pipeline_runs
                    WHERE workspace_key=%s AND status IN ('queued', 'running')
                    ORDER BY created_at LIMIT 1
                    """,
                    (WORKSPACE_KEY,),
                )
                row = cursor.fetchone()
                if not row:
                    cursor.execute(
                        """
                        INSERT INTO seo_growth_pipeline_runs(
                            id, workspace_key, mode, status, requested_by
                        ) VALUES (%s, %s, %s, 'queued', %s)
                        RETURNING *
                        """,
                        (run_id, WORKSPACE_KEY, str(mode or "daily")[:40], str(requested_by or "")[:200]),
                    )
                    row = cursor.fetchone()
            connection.commit()
        return dict(row or {})

    def claim_pipeline_run(self, worker_id, *, lease_seconds=PIPELINE_LEASE_SECONDS):
        self.ensure_schema()
        now = utc_now()
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    WITH candidate AS (
                        SELECT id FROM seo_growth_pipeline_runs
                        WHERE status IN ('queued', 'running')
                          AND (status='queued' OR lease_expires_at IS NULL OR lease_expires_at < %s)
                        ORDER BY created_at
                        FOR UPDATE SKIP LOCKED
                        LIMIT 1
                    )
                    UPDATE seo_growth_pipeline_runs AS run
                    SET status='running', lease_owner=%s,
                        started_at=COALESCE(started_at, %s),
                        lease_expires_at=%s, updated_at=now()
                    FROM candidate
                    WHERE run.id=candidate.id
                    RETURNING run.*
                    """,
                    (
                        now,
                        str(worker_id or "")[:200],
                        now,
                        now + timedelta(seconds=lease_seconds),
                    ),
                )
                row = cursor.fetchone()
            connection.commit()
        return dict(row or {}) if row else None

    def renew_pipeline_lease(self, pipeline_run_id, worker_id, *, lease_seconds=PIPELINE_LEASE_SECONDS):
        now = utc_now()
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE seo_growth_pipeline_runs
                    SET lease_expires_at=%s, updated_at=now()
                    WHERE id=%s AND status='running' AND lease_owner=%s
                    RETURNING id
                    """,
                    (
                        now + timedelta(seconds=lease_seconds),
                        pipeline_run_id,
                        str(worker_id or "")[:200],
                    ),
                )
                row = cursor.fetchone()
            connection.commit()
        return bool(row)

    def start_stage(self, pipeline_run_id, stage_key, stage_order):
        self.ensure_schema()
        stage_id = _stable_id("seo-growth-stage", pipeline_run_id, stage_key)
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO seo_growth_pipeline_stages(
                        id, pipeline_run_id, workspace_key, stage_key, stage_order,
                        status, started_at
                    ) VALUES (%s, %s, %s, %s, %s, 'running', now())
                    ON CONFLICT (pipeline_run_id, stage_key) DO UPDATE SET
                        status='running', error_code='', error_summary='',
                        started_at=COALESCE(seo_growth_pipeline_stages.started_at, now()),
                        updated_at=now()
                    RETURNING *
                    """,
                    (stage_id, pipeline_run_id, WORKSPACE_KEY, stage_key, int(stage_order or 0)),
                )
                row = cursor.fetchone()
            connection.commit()
        return dict(row or {})

    def complete_stage(self, pipeline_run_id, stage_key, *, source_status="healthy", data_through_date=None, rows_processed=0, rows_written=0):
        self.ensure_schema()
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE seo_growth_pipeline_stages
                    SET status='completed', source_status=%s, data_through_date=%s,
                        rows_processed=%s, rows_written=%s,
                        error_code='', error_summary='', completed_at=now(), updated_at=now()
                    WHERE pipeline_run_id=%s AND stage_key=%s
                    RETURNING *
                    """,
                    (
                        str(source_status or "healthy")[:100],
                        _as_date(data_through_date),
                        int(rows_processed or 0),
                        int(rows_written or 0),
                        pipeline_run_id,
                        stage_key,
                    ),
                )
                row = cursor.fetchone()
            connection.commit()
        return dict(row or {})

    def fail_stage(self, pipeline_run_id, stage_key, error):
        self.ensure_schema()
        code, message = _safe_error(error)
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE seo_growth_pipeline_stages
                    SET status='failed', source_status='failed', error_code=%s,
                        error_summary=%s, completed_at=now(), updated_at=now()
                    WHERE pipeline_run_id=%s AND stage_key=%s
                    RETURNING *
                    """,
                    (code, message, pipeline_run_id, stage_key),
                )
                row = cursor.fetchone()
            connection.commit()
        return dict(row or {})

    def complete_pipeline(self, pipeline_run_id, *, status="completed", error_code="", error_summary=""):
        health = {}
        source_health = {}
        try:
            health = self.phase4_store.saved_health()
        except Exception:
            health = {}
        try:
            source_health = seo_live_analytics.PostgresSEOLiveAnalyticsReader(
                self.phase4_store
            ).source_health()
        except Exception:
            source_health = {}
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE seo_growth_pipeline_runs
                    SET status=%s, completed_at=now(), lease_owner='', lease_expires_at=NULL,
                        gsc_data_through_date=%s, ga4_data_through_date=%s,
                        shopify_data_through_date=%s, common_reporting_date=%s,
                        confirmed_revenue_through_date=%s,
                        error_code=%s, error_summary=%s, updated_at=now()
                    WHERE id=%s
                    RETURNING *
                    """,
                    (
                        str(status or "completed")[:40],
                        _as_date((source_health.get("gsc") or {}).get("through_date") or health.get("latest_gsc_date")),
                        _as_date((source_health.get("ga4") or {}).get("through_date") or health.get("latest_ga4_date")),
                        _as_date((source_health.get("shopify") or {}).get("through_date") or health.get("latest_shopify_date")),
                        _as_date(health.get("common_reporting_date")),
                        _as_date(health.get("reconciliation_through_date")),
                        str(error_code or "")[:100],
                        str(error_summary or "")[:300],
                        pipeline_run_id,
                    ),
                )
                row = cursor.fetchone()
            connection.commit()
        return dict(row or {})

    def recent_pipeline_status(self):
        self.ensure_schema()
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT * FROM seo_growth_pipeline_runs
                    WHERE workspace_key=%s
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (WORKSPACE_KEY,),
                )
                run = dict(cursor.fetchone() or {})
                stages = []
                if run.get("id"):
                    cursor.execute(
                        """
                        SELECT stage_key, stage_order, status, source_status,
                               data_through_date, rows_processed, rows_written,
                               error_code, error_summary, started_at, completed_at
                        FROM seo_growth_pipeline_stages
                        WHERE pipeline_run_id=%s
                        ORDER BY stage_order, stage_key
                        """,
                        (run["id"],),
                    )
                    stages = [dict(row) for row in cursor.fetchall() or []]
        return {"run": _json_safe(run), "stages": _json_safe(stages)}

    def save_analysis_snapshot(self, bundle, *, created_by=""):
        self.ensure_schema()
        snapshot = sanitize_for_chatgpt((bundle or {}).get("snapshot") or {})
        snapshot_id = str((bundle or {}).get("snapshot_id") or uuid.uuid4())
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO seo_growth_analysis_snapshots(
                        id, workspace_key, snapshot_version, prompt_version,
                        analysis_mode, filters, data_through, source_snapshot,
                        summary_text, created_by
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING *
                    """,
                    (
                        snapshot_id, WORKSPACE_KEY, SNAPSHOT_VERSION, PROMPT_VERSION,
                        str((bundle or {}).get("analysis_mode") or snapshot.get("analysis_mode") or "")[:100],
                        json.dumps(snapshot.get("filters") or {}),
                        _as_date((bundle or {}).get("data_through")),
                        json.dumps(snapshot),
                        str((bundle or {}).get("summary") or "")[:12000],
                        str(created_by or "")[:200],
                    ),
                )
                row = cursor.fetchone()
            connection.commit()
        return _json_safe(dict(row or {}))

    def list_snapshots(self, *, limit=20):
        self.ensure_schema()
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, snapshot_version, prompt_version, analysis_mode,
                           filters, data_through, summary_text, created_by, created_at
                    FROM seo_growth_analysis_snapshots
                    WHERE workspace_key=%s
                    ORDER BY created_at DESC LIMIT %s
                    """,
                    (WORKSPACE_KEY, int(limit)),
                )
                return [_json_safe(dict(row)) for row in cursor.fetchall() or []]

    def save_report(self, report_payload, *, snapshot_id="", report_type="", model_name="", response_id="", created_by="", status="completed"):
        clean = validate_structured_report(report_payload)
        report_id = str(clean.get("report_id") or uuid.uuid4())
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO seo_growth_reports(
                        id, workspace_key, snapshot_id, report_type, status,
                        model_name, response_id, report_payload, created_by
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING *
                    """,
                    (
                        report_id, WORKSPACE_KEY, snapshot_id or None,
                        str(report_type or clean.get("report_type") or "")[:100],
                        str(status or "completed")[:80],
                        str(model_name or "")[:120],
                        str(response_id or "")[:200],
                        json.dumps(clean),
                        str(created_by or "")[:200],
                    ),
                )
                row = cursor.fetchone()
                for recommendation in clean.get("recommendations") or []:
                    recommendation_id = str(recommendation.get("recommendation_id") or uuid.uuid4())
                    cursor.execute(
                        """
                        INSERT INTO seo_growth_recommendations(
                            id, workspace_key, report_id, status, target_keyword,
                            keyword_cluster, target_market, current_page, recommended_page,
                            current_position, previous_position, impressions, clicks,
                            revenue_or_conversion_evidence, recommended_action,
                            priority, reason, confidence, measurement_date,
                            requires_approval, proposed_owner
                        ) VALUES (%s, %s, %s, 'awaiting_approval', %s, %s, %s, %s, %s,
                                  %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO NOTHING
                        """,
                        (
                            recommendation_id, WORKSPACE_KEY, report_id,
                            str(recommendation.get("target_keyword") or "")[:500],
                            str(recommendation.get("keyword_cluster") or "")[:500],
                            str(recommendation.get("target_market") or "")[:50],
                            str(recommendation.get("current_page") or "")[:1200],
                            str(recommendation.get("recommended_page") or "")[:1200],
                            recommendation.get("current_position"),
                            recommendation.get("previous_position"),
                            _decimal(recommendation.get("impressions")),
                            _decimal(recommendation.get("clicks")),
                            str(recommendation.get("revenue_or_conversion_evidence") or "")[:3000],
                            str(recommendation.get("recommended_action") or "")[:3000],
                            str(recommendation.get("priority") or "")[:40],
                            str(recommendation.get("reason") or "")[:4000],
                            _decimal(recommendation.get("confidence")),
                            _as_date(recommendation.get("measurement_date")),
                            bool(recommendation.get("requires_approval", True)),
                            str(recommendation.get("proposed_owner") or "")[:200],
                        ),
                    )
            connection.commit()
        return _json_safe(dict(row or {}))

    def list_reports(self, *, report_type="All", limit=30):
        self.ensure_schema()
        clauses = ["workspace_key=%s", "archived_at IS NULL"]
        params = [WORKSPACE_KEY]
        if report_type and report_type != "All":
            clauses.append("report_type=%s")
            params.append(report_type)
        params.append(int(limit))
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT id, snapshot_id, report_type, status, model_name,
                           error_code, error_summary, created_by, created_at, updated_at
                    FROM seo_growth_reports
                    WHERE {' AND '.join(clauses)}
                    ORDER BY created_at DESC LIMIT %s
                    """,
                    params,
                )
                return [_json_safe(dict(row)) for row in cursor.fetchall() or []]

    def list_recommendations(self, *, status="All", limit=100):
        self.ensure_schema()
        clauses = ["workspace_key=%s"]
        params = [WORKSPACE_KEY]
        if status and status != "All":
            clauses.append("status=%s")
            params.append(status)
        params.append(int(limit))
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT id, report_id, opportunity_key, status, target_keyword,
                           keyword_cluster, target_market, current_page, recommended_page,
                           impressions, clicks, revenue_or_conversion_evidence,
                           recommended_action, priority, reason, confidence,
                           measurement_date, proposed_owner, approved_by, approved_at,
                           snoozed_until, created_at, updated_at
                    FROM seo_growth_recommendations
                    WHERE {' AND '.join(clauses)}
                    ORDER BY updated_at DESC LIMIT %s
                    """,
                    params,
                )
                return [_json_safe(dict(row)) for row in cursor.fetchall() or []]

    def update_recommendation_status(self, recommendation_id, *, status, actor="", snoozed_until=None):
        if status not in RECOMMENDATION_STATUSES:
            raise SEOGrowthError("Choose a valid recommendation status.", code="invalid_recommendation_status", retryable=False)
        approved = status in {"approved", "edited_and_approved"}
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE seo_growth_recommendations
                    SET status=%s, approved_by=CASE WHEN %s THEN %s ELSE approved_by END,
                        approved_at=CASE WHEN %s THEN now() ELSE approved_at END,
                        snoozed_until=%s, updated_at=now()
                    WHERE workspace_key=%s AND id=%s
                    RETURNING *
                    """,
                    (
                        status, approved, str(actor or "")[:200], approved,
                        _as_date(snoozed_until), WORKSPACE_KEY, recommendation_id,
                    ),
                )
                row = cursor.fetchone()
            connection.commit()
        return _json_safe(dict(row or {}))

    def convert_recommendation_to_task(self, recommendation_id, *, actor="", owner="", due_date=None):
        self.ensure_schema()
        task_id = str(uuid.uuid4())
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM seo_growth_recommendations WHERE workspace_key=%s AND id=%s",
                    (WORKSPACE_KEY, recommendation_id),
                )
                recommendation = dict(cursor.fetchone() or {})
                if not recommendation:
                    raise SEOGrowthError("The selected recommendation no longer exists.", code="recommendation_missing", retryable=False)
                title = str(recommendation.get("recommended_action") or recommendation.get("target_keyword") or "SEO task")[:500]
                evidence = {
                    "target_keyword": recommendation.get("target_keyword") or "",
                    "target_market": recommendation.get("target_market") or "",
                    "impressions": _json_safe(recommendation.get("impressions")),
                    "clicks": _json_safe(recommendation.get("clicks")),
                    "reason": recommendation.get("reason") or "",
                    "revenue_or_conversion_evidence": recommendation.get("revenue_or_conversion_evidence") or "",
                }
                cursor.execute(
                    """
                    INSERT INTO seo_growth_tasks(
                        id, workspace_key, recommendation_id, status, title,
                        target_keyword, target_market, target_page, recommended_action,
                        reason, supporting_evidence, completion_requirements,
                        required_proof, owner, due_date, approved_by, approved_at
                    ) VALUES (%s, %s, %s, 'approved', %s, %s, %s, %s, %s, %s, %s,
                              %s, %s, %s, %s, %s, now())
                    RETURNING *
                    """,
                    (
                        task_id, WORKSPACE_KEY, recommendation_id, title,
                        str(recommendation.get("target_keyword") or "")[:500],
                        str(recommendation.get("target_market") or "")[:50],
                        str(recommendation.get("recommended_page") or recommendation.get("current_page") or "")[:1200],
                        str(recommendation.get("recommended_action") or "")[:3000],
                        str(recommendation.get("reason") or "")[:4000],
                        json.dumps(evidence),
                        "Complete the approved SEO action without publishing unapproved changes.",
                        "Provide the edited draft, target URL, and evidence of completion for owner review.",
                        str(owner or recommendation.get("proposed_owner") or "")[:200],
                        _as_date(due_date),
                        str(actor or "")[:200],
                    ),
                )
                task = dict(cursor.fetchone() or {})
                baseline_date = utc_now().date()
                baseline_metrics = {
                    "target_keyword": recommendation.get("target_keyword") or "",
                    "target_page": recommendation.get("recommended_page") or recommendation.get("current_page") or "",
                    "market": recommendation.get("target_market") or "",
                    "clicks": _json_safe(recommendation.get("clicks")),
                    "impressions": _json_safe(recommendation.get("impressions")),
                    "average_position": _json_safe(recommendation.get("current_position")),
                    "measurement_date": _iso(recommendation.get("measurement_date")),
                }
                for window_days in (28, 56, 90):
                    cursor.execute(
                        """
                        INSERT INTO seo_growth_measurements(
                            id, workspace_key, task_id, recommendation_id,
                            window_days, baseline_date, due_date, baseline_metrics
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (workspace_key, task_id, window_days) DO NOTHING
                        """,
                        (
                            str(uuid.uuid4()), WORKSPACE_KEY, task_id, recommendation_id,
                            window_days, baseline_date,
                            baseline_date + timedelta(days=window_days),
                            json.dumps(baseline_metrics),
                        ),
                    )
                cursor.execute(
                    """
                    UPDATE seo_growth_recommendations
                    SET status='converted_to_task', approved_by=COALESCE(NULLIF(approved_by, ''), %s),
                        approved_at=COALESCE(approved_at, now()), updated_at=now()
                    WHERE workspace_key=%s AND id=%s
                    """,
                    (str(actor or "")[:200], WORKSPACE_KEY, recommendation_id),
                )
            connection.commit()
        activity_metadata = _activity_actor_metadata_from_identifier(actor)
        record_activity_log(
            "seo_recommendation_converted_to_task",
            "SEO / Tasks & Results",
            f"SEO recommendation converted to task: {task.get('title') or ''}",
            entity_type="seo_growth_task",
            entity_id=task_id,
            metadata={**activity_metadata, "recommendation_id": recommendation_id},
            actor=str(activity_metadata.get("actor_display") or actor or "sports_cave_os")[:200],
        )
        return _json_safe(task)

    def list_tasks(self, *, status="All", limit=100):
        self.ensure_schema()
        clauses = ["workspace_key=%s"]
        params = [WORKSPACE_KEY]
        if status and status != "All":
            clauses.append("status=%s")
            params.append(status)
        params.append(int(limit))
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT id, recommendation_id, status, title, target_keyword,
                           target_market, target_page, recommended_action,
                           owner, due_date, approved_by, approved_at, completed_at,
                           updated_at
                    FROM seo_growth_tasks
                    WHERE {' AND '.join(clauses)}
                    ORDER BY due_date NULLS LAST, updated_at DESC LIMIT %s
                    """,
                    params,
                )
                return [_json_safe(dict(row)) for row in cursor.fetchall() or []]

    def update_task_status(self, task_id, *, status, actor=""):
        if status not in TASK_STATUSES:
            raise SEOGrowthError("Choose a valid task status.", code="invalid_task_status", retryable=False)
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE seo_growth_tasks
                    SET status=%s, completed_at=CASE WHEN %s='completed' THEN now() ELSE completed_at END,
                        updated_at=now()
                    WHERE workspace_key=%s AND id=%s
                    RETURNING *
                    """,
                    (status, status, WORKSPACE_KEY, task_id),
                )
                row = cursor.fetchone()
            connection.commit()
        activity_metadata = _activity_actor_metadata_from_identifier(actor)
        record_activity_log(
            "seo_task_status_updated",
            "SEO / Tasks & Results",
            f"SEO task status updated: {status}",
            entity_type="seo_growth_task",
            entity_id=task_id,
            metadata={**activity_metadata, "status": status},
            actor=str(activity_metadata.get("actor_display") or actor or "sports_cave_os")[:200],
        )
        return _json_safe(dict(row or {}))

    def list_measurements(self, *, limit=100):
        self.ensure_schema()
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT measure.id, measure.task_id, task.title, measure.window_days,
                           measure.measurement_status, measure.baseline_date,
                           measure.due_date, measure.measured_at,
                           measure.change_summary, measure.measurement_confidence,
                           measure.known_limitations
                    FROM seo_growth_measurements AS measure
                    LEFT JOIN seo_growth_tasks AS task ON task.id=measure.task_id
                    WHERE measure.workspace_key=%s
                    ORDER BY measure.due_date, measure.window_days LIMIT %s
                    """,
                    (WORKSPACE_KEY, int(limit)),
                )
                return [_json_safe(dict(row)) for row in cursor.fetchall() or []]

    def refresh_due_measurements(self, *, today=None):
        self.ensure_schema()
        today = _as_date(today) or utc_now().date()
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT measure.*, task.target_keyword, task.target_page, task.target_market
                    FROM seo_growth_measurements AS measure
                    JOIN seo_growth_tasks AS task ON task.id=measure.task_id
                    WHERE measure.workspace_key=%s
                      AND measure.measurement_status='scheduled'
                      AND measure.due_date<=%s
                    ORDER BY measure.due_date
                    """,
                    (WORKSPACE_KEY, today),
                )
                rows = [dict(row) for row in cursor.fetchall() or []]
                for row in rows:
                    metrics = self._measurement_metrics(cursor, row)
                    baseline = dict(row.get("baseline_metrics") or {})
                    summary = measurement_change_summary(baseline, metrics)
                    cursor.execute(
                        """
                        UPDATE seo_growth_measurements
                        SET measurement_status=%s, measured_at=now(),
                            measurement_metrics=%s, change_summary=%s,
                            measurement_confidence=%s, known_limitations=%s,
                            updated_at=now()
                        WHERE id=%s
                        """,
                        (
                            summary["result"],
                            json.dumps(metrics),
                            json.dumps(summary),
                            summary["confidence"],
                            summary["known_limitations"],
                            row["id"],
                        ),
                    )
            connection.commit()
        return {"processed": len(rows), "written": len(rows)}

    @staticmethod
    def _measurement_metrics(cursor, row):
        due_date = _as_date(row.get("due_date")) or utc_now().date()
        start_date = due_date - timedelta(days=27)
        keyword = str(row.get("target_keyword") or "").strip()
        target_page = str(row.get("target_page") or "").strip()
        market = str(row.get("target_market") or "").strip().upper()
        clauses = ["workspace_key=%s", "date BETWEEN %s AND %s"]
        params = [WORKSPACE_KEY, start_date, due_date]
        if keyword:
            clauses.append("LOWER(query)=LOWER(%s)")
            params.append(keyword)
        if market in {"AU", "US", "UK"}:
            clauses.append("market_code=%s")
            params.append(market)
        cursor.execute(
            f"""
            SELECT COALESCE(SUM(organic_clicks), 0) AS clicks,
                   COALESCE(SUM(organic_impressions), 0) AS impressions,
                   CASE WHEN SUM(organic_impressions)>0
                        THEN SUM(position_weight)/SUM(organic_impressions) ELSE NULL END AS average_position
            FROM seo_reporting_query_daily
            WHERE {' AND '.join(clauses)}
            """,
            params,
        )
        metrics = dict(cursor.fetchone() or {})
        metrics["start_date"] = start_date.isoformat()
        metrics["end_date"] = due_date.isoformat()
        metrics["target_page"] = target_page
        return _json_safe(metrics)

    def keyword_workspace_rows(self, *, filters, opportunity_type="All", limit=250):
        self.ensure_schema()
        health = self.phase4_store.saved_health()
        through = _as_date(health.get("common_reporting_date"))
        if not through:
            return []
        period = google_seo_phase4.reporting_period(
            filters.get("preset") or "Last 28 days",
            through_date=through,
            custom_start=filters.get("custom_start"),
            custom_end=filters.get("custom_end"),
        )
        reporting_filters = google_seo_phase4.ReportingFilters(
            period,
            market=filters.get("market") or "All markets",
            device=filters.get("device") or "All devices",
            search=filters.get("search") or "All searches",
        )
        countries = sorted(str(value).upper() for value in reporting_filters.country_values())
        devices = sorted(str(value).casefold() for value in reporting_filters.device_values())
        params = []
        where = [
            "query_daily.workspace_key=%s",
            "query_daily.date BETWEEN %s AND %s",
            "query_daily.search_class=%s",
        ]
        if countries:
            where.append("UPPER(query_daily.country_code)=ANY(%s)")
            params.append(countries)
        if devices:
            where.append("LOWER(query_daily.device_category)=ANY(%s)")
            params.append(devices)
        search_class = google_seo_phase4.PostgresSEOReportingReader._search_class(reporting_filters)
        query_params = [WORKSPACE_KEY, period.start_date, period.end_date, search_class, *params]
        opportunity_clause = ""
        if opportunity_type and opportunity_type != "All":
            opportunity_clause = " AND opportunity.opportunity_type=%s"
            query_params.append(opportunity_type)
        query_params.append(int(limit))
        with self._backend().connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    WITH query_metric AS (
                        SELECT query_daily.query, query_daily.canonical_page_key,
                               SUM(query_daily.organic_clicks) AS clicks,
                               SUM(query_daily.organic_impressions) AS impressions,
                               CASE WHEN SUM(query_daily.organic_impressions)>0
                                    THEN SUM(query_daily.organic_clicks)/SUM(query_daily.organic_impressions) ELSE 0 END AS ctr,
                               CASE WHEN SUM(query_daily.organic_impressions)>0
                                    THEN SUM(query_daily.position_weight)/SUM(query_daily.organic_impressions) ELSE 0 END AS average_position
                        FROM seo_reporting_query_daily AS query_daily
                        WHERE {' AND '.join(where)}
                        GROUP BY query_daily.query, query_daily.canonical_page_key
                    )
                    SELECT query_metric.query, query_metric.canonical_page_key,
                           page.canonical_url AS current_page,
                           page.page_type, query_metric.clicks, query_metric.impressions,
                           query_metric.ctr, query_metric.average_position,
                           opportunity.opportunity_key, opportunity.opportunity_type,
                           opportunity.priority_score, opportunity.status AS opportunity_status,
                           opportunity.recommended_action
                    FROM query_metric
                    LEFT JOIN seo_canonical_pages AS page ON page.page_key=query_metric.canonical_page_key
                    LEFT JOIN seo_reporting_opportunities AS opportunity
                      ON opportunity.workspace_key=%s
                     AND opportunity.status IN ('open', 'snoozed')
                     AND (
                         LOWER(opportunity.query)=LOWER(query_metric.query)
                         OR opportunity.canonical_page_key=query_metric.canonical_page_key
                     )
                     {opportunity_clause}
                    WHERE query_metric.query<>''
                    ORDER BY COALESCE(opportunity.priority_score, 0) DESC,
                             query_metric.clicks DESC, query_metric.impressions DESC
                    LIMIT %s
                    """,
                    [*query_params[:-1], WORKSPACE_KEY, *query_params[-(2 if opportunity_clause else 1):]],
                )
                return [_json_safe(dict(row)) for row in cursor.fetchall() or []]


_DEFAULT_STORE = None


def default_store():
    global _DEFAULT_STORE
    if _DEFAULT_STORE is None:
        _DEFAULT_STORE = PostgresSEOGrowthStore()
    return _DEFAULT_STORE


def measurement_change_summary(baseline, current):
    baseline = dict(baseline or {})
    current = dict(current or {})
    clicks_delta = _decimal(current.get("clicks")) - _decimal(baseline.get("clicks"))
    impressions_delta = _decimal(current.get("impressions")) - _decimal(baseline.get("impressions"))
    baseline_position = baseline.get("average_position")
    current_position = current.get("average_position")
    position_delta = None
    if baseline_position not in (None, "") and current_position not in (None, ""):
        position_delta = float(_decimal(current_position) - _decimal(baseline_position))
    has_data = _decimal(current.get("impressions")) > 0 or _decimal(baseline.get("impressions")) > 0
    if not has_data:
        result = "insufficient_data"
    elif clicks_delta > 0 or (position_delta is not None and position_delta < 0):
        result = "improved"
    elif clicks_delta < 0 or (position_delta is not None and position_delta > 0):
        result = "declined"
    else:
        result = "unchanged"
    return {
        "result": result,
        "clicks_change": float(clicks_delta),
        "impressions_change": float(impressions_delta),
        "position_change": position_delta,
        "confidence": "medium" if has_data else "low",
        "known_limitations": (
            "Measured association only. Organic changes can be influenced by seasonality, ranking volatility, demand and external site changes."
        ),
    }


def openai_config_status():
    key_source = "SPORTS_CAVE_OPENAI_API_KEY" if os.getenv("SPORTS_CAVE_OPENAI_API_KEY") else "OPENAI_API_KEY"
    api_key = os.getenv(key_source, "").strip()
    model = (
        os.getenv("SPORTS_CAVE_OPENAI_MODEL", "").strip()
        or os.getenv("OPENAI_MODEL", "").strip()
        or "gpt-5"
    )
    return {"configured": bool(api_key), "key_source": key_source if api_key else "", "model": model}


def _extract_response_text(payload):
    if payload.get("output_text"):
        return str(payload.get("output_text") or "")
    chunks = []
    for item in payload.get("output") or []:
        for content in item.get("content") or []:
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                chunks.append(str(content.get("text")))
    return "\n".join(chunks).strip()


def generate_openai_report(bundle, *, store=None, created_by="", request_post=requests.post):
    config = openai_config_status()
    api_key = os.getenv(config.get("key_source") or "", "").strip()
    snapshot_record = None
    if store is not None:
        try:
            snapshot_record = store.save_analysis_snapshot(bundle, created_by=created_by)
        except Exception:
            snapshot_record = {}
    if not api_key:
        return {
            "ok": False,
            "code": "openai_not_configured",
            "message": "OpenAI is not configured on the server. Use Prepare for ChatGPT.",
            "snapshot": snapshot_record or {},
        }
    payload = {
        "model": config["model"],
        "input": [
            {
                "role": "system",
                "content": "You produce evidence-only Sports Cave SEO reports as strict JSON.",
            },
            {
                "role": "user",
                "content": (bundle or {}).get("prompt") or build_master_prompt((bundle or {}).get("snapshot") or {}),
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "sports_cave_seo_growth_report",
                "schema": report_json_schema(),
                "strict": True,
            }
        },
    }
    try:
        response = request_post(
            OPENAI_RESPONSES_ENDPOINT,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=90,
        )
        if int(getattr(response, "status_code", 0) or 0) >= 400:
            raise SEOGrowthError("OpenAI report generation failed.", code="openai_request_failed")
        response_payload = response.json()
        text = _extract_response_text(response_payload)
        report_payload = validate_structured_report(text)
    except Exception as error:
        code, message = _safe_error(error)
        return {"ok": False, "code": code, "message": message, "snapshot": snapshot_record or {}}
    report_record = {}
    if store is not None:
        report_record = store.save_report(
            report_payload,
            snapshot_id=(snapshot_record or {}).get("id") or "",
            report_type=(bundle or {}).get("analysis_mode") or report_payload.get("report_type") or "",
            model_name=config["model"],
            response_id=str(response_payload.get("id") or ""),
            created_by=created_by,
        )
    return {
        "ok": True,
        "report": report_payload,
        "report_record": report_record,
        "snapshot": snapshot_record or {},
        "model": config["model"],
    }


def queue_growth_pipeline(user, *, store=None, mode="manual"):
    google_seo.require_admin(user)
    store = store or default_store()
    run = store.queue_pipeline_run(
        mode=mode,
        requested_by=str(user.get("id") or "")[:200],
    )
    record_activity_log(
        "seo_growth_pipeline_queued",
        "SEO / Overview",
        "SEO Growth Intelligence daily pipeline queued",
        entity_type="seo_growth_pipeline_run",
        entity_id=str(run.get("id") or ""),
        metadata={
            "actor_id": user.get("id") or "",
            "actor_email": user.get("email") or "",
            "actor_role": user.get("role") or "",
            "actor_timezone": os_accounts.timezone_for_user(user),
            "mode": mode,
        },
        actor=str(user.get("display_name") or user.get("id") or "sports_cave_os")[:200],
    )
    return run


def _stage_result_counts(result):
    result = dict(result or {})
    canonical_counts = dict(result.get("canonical_counts") or {})
    canonical_written = _integer(result.get("canonical_rows_written")) or sum(
        _integer(value) for value in canonical_counts.values()
    )
    return {
        "rows_processed": _integer(result.get("received") or result.get("processed") or result.get("rows_processed")),
        "rows_written": canonical_written or _integer(
            result.get("written") or result.get("rows_written") or result.get("inserted")
        ),
        "data_through_date": (
            result.get("canonical_data_through_date")
            or result.get("common_reporting_date")
            or result.get("latest_stored_data_date")
            or result.get("data_through_date")
        ),
    }


def _analytics_failure_summary(failures):
    labels = dict(ANALYTICS_REFRESH_STAGES)
    messages = []
    for stage_key, error in failures:
        _code, message = _safe_error(error)
        messages.append(f"{labels.get(stage_key, stage_key)}: {message}")
    return "; ".join(messages)[:1000]


def run_daily_analytics_refresh(
    *,
    store=None,
    import_store=None,
    phase4_store=None,
    connection_store=None,
    requested_by="render-cron",
    worker_id="",
    fresh_gsc_refresher=None,
):
    """Refresh saved analytics without running reports, tasks or measurements."""
    phase4_store = phase4_store or google_seo_phase4.default_phase4_store()
    store = store or PostgresSEOGrowthStore(phase4_store)
    import_store = import_store or google_seo_import.default_import_store()
    connection_store = connection_store or google_seo.default_store()
    worker_id = str(worker_id or f"seo-analytics-{secrets.token_hex(6)}")[:200]
    queued = store.queue_pipeline_run(mode="analytics", requested_by=requested_by)
    run = store.claim_pipeline_run(worker_id)
    if not run:
        return {"status": "already_running", "run": queued, "failed_stages": []}
    pipeline_id = run["id"]
    google_worker = google_seo_import.SEOImportWorker(
        import_store=import_store,
        connection_store=connection_store,
        worker_id=f"{worker_id}-google",
    )
    failures = []

    def renew_lease():
        renew = getattr(store, "renew_pipeline_lease", None)
        if callable(renew) and not renew(pipeline_id, worker_id):
            raise SEOGrowthError("The analytics refresh lock was lost.", code="analytics_lock_lost")

    def run_stage(stage_index, key, callback):
        renew_lease()
        store.start_stage(pipeline_id, key, stage_index)
        try:
            result = callback() or {}
            counts = _stage_result_counts(result)
            store.complete_stage(
                pipeline_id,
                key,
                source_status=str(result.get("status") or "healthy"),
                data_through_date=counts["data_through_date"],
                rows_processed=counts["rows_processed"],
                rows_written=counts["rows_written"],
            )
            renew_lease()
            return result
        except Exception as error:
            store.fail_stage(pipeline_id, key, error)
            failures.append((key, error))
            return None

    def schema_check():
        store.ensure_schema()
        return {"status": "ready"}

    def google_source(source):
        google_seo_import.queue_daily_source(
            source,
            import_store=import_store,
            connection_store=connection_store,
            requested_by=requested_by,
        )
        result = google_worker.run_once(source=source) or {"status": "no_pending_run"}
        source_status = str(result.get("status") or "").casefold()
        if source_status not in {"completed", "preliminary"}:
            message = str(
                result.get("error_summary")
                or result.get("error_message")
                or f"{source} canonical sync did not complete."
            )[:300]
            raise SEOGrowthError(
                message,
                code=str(result.get("error_code") or f"{source.casefold()}_sync_failed")[:100],
            )
        return result

    def saved_source_health():
        health = seo_live_analytics.PostgresSEOLiveAnalyticsReader(phase4_store).source_health()
        source_rows = sum(_integer((health.get(key) or {}).get("rows")) for key in ("gsc", "ga4", "shopify"))
        through_dates = [
            _as_date((health.get(key) or {}).get("through_date"))
            for key in ("gsc", "ga4", "shopify")
        ]
        through_dates = [value for value in through_dates if value]
        return {
            "status": "ready" if source_rows else "no_saved_rows",
            "rows_processed": source_rows,
            "data_through_date": max(through_dates).isoformat() if through_dates else "",
        }

    callbacks = {
        "schema_check": schema_check,
        "gsc_daily_sync": lambda: google_source("GSC"),
        "gsc_fresh_sync": fresh_gsc_refresher or (
            lambda: google_seo_import.refresh_gsc_fresh_data(
                import_store=import_store,
                connection_store=connection_store,
            )
        ),
        "ga4_daily_sync": lambda: google_source("GA4"),
        "ga4_report_contracts": lambda: analytics_reporting.refresh_saved_report_contracts(
            connection_store=connection_store,
        ),
        "shopify_saved_data": saved_source_health,
        "url_mapping": phase4_store.map_saved_urls,
        "revenue_reconciliation": phase4_store.reconcile_revenue,
        "joined_reporting": phase4_store.refresh_reporting_snapshots,
        "source_health": saved_source_health,
    }
    try:
        for index, (stage_key, _label) in enumerate(ANALYTICS_REFRESH_STAGES, start=1):
            run_stage(index, stage_key, callbacks[stage_key])
    finally:
        try:
            phase4_store.refresh_health()
        except Exception as error:
            failures.append(("source_health", error))
    status = "partial" if failures else "completed"
    failure_summary = _analytics_failure_summary(failures)
    completed = store.complete_pipeline(
        pipeline_id,
        status=status,
        error_code=failures[0][0] if failures else "",
        error_summary=failure_summary,
    )
    return {
        "status": status,
        "run": _json_safe(completed),
        "failed_stages": sorted({key for key, _error in failures}),
        "error_summary": failure_summary,
    }


def run_daily_growth_pipeline(
    *,
    store=None,
    import_store=None,
    phase4_store=None,
    connection_store=None,
    requested_by="render-cron",
    worker_id="",
    technical_auditor=None,
    fresh_gsc_refresher=None,
):
    phase4_store = phase4_store or google_seo_phase4.default_phase4_store()
    store = store or PostgresSEOGrowthStore(phase4_store)
    import_store = import_store or google_seo_import.default_import_store()
    connection_store = connection_store or google_seo.default_store()
    worker_id = str(worker_id or f"seo-growth-{secrets.token_hex(6)}")[:200]
    queued = store.queue_pipeline_run(mode="daily", requested_by=requested_by)
    run = store.claim_pipeline_run(worker_id)
    if not run:
        return {"status": "already_running", "run": queued}
    pipeline_id = run["id"]
    google_worker = google_seo_import.SEOImportWorker(
        import_store=import_store,
        connection_store=connection_store,
        worker_id=f"{worker_id}-google",
    )
    phase4_worker = google_seo_phase4.SEOPhase4Worker(
        phase4_store=phase4_store,
        connection_store=connection_store,
        worker_id=f"{worker_id}-phase4",
    )
    context = {"google_daily_queued": False, "phase4_daily_queued": False}
    failures = []

    def run_stage(stage_index, key, callback, *, critical=False):
        store.start_stage(pipeline_id, key, stage_index)
        try:
            result = callback() or {}
            counts = _stage_result_counts(result)
            store.complete_stage(
                pipeline_id,
                key,
                source_status=str(result.get("status") or "healthy"),
                data_through_date=counts["data_through_date"],
                rows_processed=counts["rows_processed"],
                rows_written=counts["rows_written"],
            )
            return result
        except Exception as error:
            store.fail_stage(pipeline_id, key, error)
            failures.append((key, error))
            if critical:
                raise
            return None

    def queue_google_once():
        if not context["google_daily_queued"]:
            google_seo_import.queue_daily_runs(
                import_store=import_store,
                connection_store=connection_store,
                requested_by=requested_by,
            )
            context["google_daily_queued"] = True

    def queue_phase4_once():
        if not context["phase4_daily_queued"]:
            google_seo_phase4.queue_daily_pipeline(
                phase4_store=phase4_store,
                connection_store=connection_store,
                requested_by=requested_by,
            )
            context["phase4_daily_queued"] = True

    stage_callbacks = {
        "connection_health": lambda: connection_store.get_connection(),
        "gsc_daily_sync": lambda: (queue_google_once() or google_worker.run_once(source="GSC") or {}),
        "gsc_fresh_sync": fresh_gsc_refresher or (
            lambda: google_seo_import.refresh_gsc_fresh_data(
                import_store=import_store,
                connection_store=connection_store,
            )
        ),
        "ga4_daily_sync": lambda: (queue_google_once() or google_worker.run_once(source="GA4") or {}),
        "shopify_pages": lambda: (queue_phase4_once() or phase4_worker.run_once(source="shopify_pages") or {}),
        "shopify_orders": lambda: (queue_phase4_once() or phase4_worker.run_once(source="shopify_orders") or {}),
        "ga4_transactions": lambda: (queue_phase4_once() or phase4_worker.run_once(source="ga4_transactions") or {}),
        "url_mapping": lambda: (queue_phase4_once() or phase4_worker.run_once(source="mapping") or phase4_store.map_saved_urls()),
        "revenue_reconciliation": lambda: (queue_phase4_once() or phase4_worker.run_once(source="reconciliation") or phase4_store.reconcile_revenue()),
        "joined_reporting": lambda: phase4_store.refresh_reporting_snapshots(),
        "technical_audit": technical_auditor or (
            lambda: seo_technical_audit.run_background_audit(connection_store=connection_store)
        ),
        "opportunities": lambda: phase4_store.refresh_reporting_snapshots(),
        "measurements": lambda: store.refresh_due_measurements(),
    }
    try:
        for index, (stage_key, _label) in enumerate(PIPELINE_STAGES, start=1):
            run_stage(index, stage_key, stage_callbacks[stage_key])
    finally:
        phase4_store.refresh_health()
    status = "partial" if failures else "completed"
    error_code = failures[0][0] if failures else ""
    error_summary = "One or more SEO pipeline stages need attention." if failures else ""
    completed = store.complete_pipeline(
        pipeline_id,
        status=status,
        error_code=error_code,
        error_summary=error_summary,
    )
    return {"status": status, "run": _json_safe(completed), "failed_stages": [key for key, _error in failures]}


def main(argv=None):
    load_dotenv(BASE_DIR / ".env")
    parser = argparse.ArgumentParser(description="Sports Cave saved SEO analytics refresh")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("daily", help="Refresh saved SEO and store analytics")
    worker_parser = subparsers.add_parser("worker", help="Poll for queued SEO analytics refresh runs")
    worker_parser.add_argument("--once", action="store_true")
    worker_parser.add_argument("--poll-seconds", type=int, default=60)
    args = parser.parse_args(argv)
    if args.command == "daily":
        run_daily_analytics_refresh()
        return 0
    if args.command == "worker":
        while True:
            run_daily_analytics_refresh(requested_by="seo-analytics-worker")
            if args.once:
                return 0
            time.sleep(max(15, int(args.poll_seconds or 60)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
