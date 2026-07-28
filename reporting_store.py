import json
from datetime import datetime, timedelta, timezone

import os_accounts


REPORTING_MIGRATION = "20260728_daily_staff_reporting.sql"
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 50


class ReportingStoreError(RuntimeError):
    pass


def _backend():
    import supabase_backend

    return supabase_backend


def _json_value(value, fallback):
    if isinstance(value, type(fallback)):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return fallback
        return decoded if isinstance(decoded, type(fallback)) else fallback
    return fallback


def _json_safe(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _safe_limit(value, default=DEFAULT_PAGE_SIZE):
    try:
        return min(max(int(value), 1), MAX_PAGE_SIZE)
    except (TypeError, ValueError):
        return default


def _require_reporting_access(user):
    if not os_accounts.can_access_reporting(user):
        raise PermissionError("Reporting access is not approved.")
    return user


def schema_status():
    backend = _backend()
    if not backend.is_configured():
        return {"configured": False, "ready": False, "reason": "database_not_configured"}
    try:
        with backend.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        to_regclass('public.activity_report_deliveries') IS NOT NULL AS deliveries,
                        to_regclass('public.activity_report_archives') IS NOT NULL AS archives
                    """
                )
                row = cur.fetchone() or {}
        ready = bool(row.get("deliveries") and row.get("archives"))
        return {
            "configured": True,
            "ready": ready,
            "reason": "ok" if ready else "migration_required",
            "migration": REPORTING_MIGRATION,
        }
    except Exception as error:
        raise ReportingStoreError("Reporting storage could not be checked.") from error


def require_schema():
    status = schema_status()
    if not status.get("ready"):
        raise ReportingStoreError(
            f"Reporting storage is not ready. Apply migrations/{REPORTING_MIGRATION}."
        )
    return status


def _archive_staff(snapshot):
    rows = []
    for member in snapshot.get("staff") or []:
        rows.append(
            {
                "id": member.get("id") or "",
                "display_name": member.get("display_name") or "",
                "role": member.get("role") or "",
                "country": member.get("country") or "",
                "timezone": member.get("timezone") or "",
                "is_owner": bool(member.get("is_owner")),
                "total_actions": int(member.get("total_actions") or 0),
                "completed_actions": int(member.get("completed_actions") or 0),
                "failed_actions": int(member.get("failed_actions") or 0),
                "attention_actions": int(member.get("attention_actions") or 0),
                "last_activity_local": member.get("last_activity_local") or "",
                "work_lines": member.get("work_lines") or [],
                "daily_execution": member.get("daily_execution"),
                "social_media": member.get("social_media"),
            }
        )
    return _json_safe(rows)


def _delivery_by_identity(cur, *, snapshot, idempotency_key):
    cur.execute(
        """
        SELECT *
        FROM activity_report_deliveries
        WHERE idempotency_key=%s
        LIMIT 1
        FOR UPDATE
        """,
        (idempotency_key,),
    )
    row = cur.fetchone()
    if row or snapshot.get("is_test"):
        return row
    cur.execute(
        """
        SELECT *
        FROM activity_report_deliveries
        WHERE purpose=%s
          AND report_date=%s::date
          AND is_test IS FALSE
        LIMIT 1
        FOR UPDATE
        """,
        (
            snapshot.get("purpose"),
            snapshot.get("report_date"),
        ),
    )
    return cur.fetchone()


def _archive_by_delivery(cur, delivery_id):
    cur.execute(
        """
        SELECT *
        FROM activity_report_archives
        WHERE delivery_id=%s
        LIMIT 1
        """,
        (str(delivery_id),),
    )
    return cur.fetchone() or {}


def delivery_claim_decision(delivery, *, stale_before):
    delivery = dict(delivery or {})
    status = str(delivery.get("status") or "").casefold()
    metadata = _json_value(delivery.get("metadata"), {})
    if status == "sent":
        return "already_sent"
    if status == "pending" and delivery.get("locked_at") and delivery["locked_at"] > stale_before:
        return "in_progress"
    if status == "failed" and not bool(metadata.get("retryable")):
        return "permanent_failure"
    return "reclaim"


def claim_delivery(snapshot, *, idempotency_key, stale_after_minutes=20):
    require_schema()
    backend = _backend()
    now_utc = datetime.now(timezone.utc)
    stale_before = now_utc - timedelta(minutes=max(int(stale_after_minutes or 20), 5))
    safe_metadata = {
        "active_staff_count": int((snapshot.get("summary") or {}).get("active_staff_count") or 0),
        "total_actions": int((snapshot.get("summary") or {}).get("total_actions") or 0),
        "attention_count": int((snapshot.get("summary") or {}).get("attention_count") or 0),
        "retryable": True,
    }
    with backend.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO activity_report_deliveries(
                    purpose, report_date, covered_start_at, covered_end_at,
                    report_timezone, recipient, subject, status, provider,
                    idempotency_key, attempt_count, locked_at, metadata, is_test
                )
                VALUES (
                    %s, %s::date, %s, %s, %s, %s, %s, 'pending', 'resend',
                    %s, 1, now(), %s::jsonb, %s
                )
                ON CONFLICT DO NOTHING
                RETURNING *
                """,
                (
                    snapshot.get("purpose"),
                    snapshot.get("report_date"),
                    snapshot.get("covered_start"),
                    snapshot.get("covered_end"),
                    snapshot.get("timezone"),
                    snapshot.get("recipient"),
                    snapshot.get("subject"),
                    idempotency_key,
                    json.dumps(safe_metadata),
                    bool(snapshot.get("is_test")),
                ),
            )
            delivery = cur.fetchone()
            created = bool(delivery)
            if not delivery:
                delivery = _delivery_by_identity(
                    cur,
                    snapshot=snapshot,
                    idempotency_key=idempotency_key,
                )
            if not delivery:
                raise ReportingStoreError("The report delivery could not be claimed.")

            if created:
                cur.execute(
                    """
                    INSERT INTO activity_report_archives(
                        delivery_id, purpose, report_date, covered_start_at, covered_end_at,
                        report_timezone, recipient, subject, status, provider,
                        staff_summaries, daily_execution_summary, report_summary,
                        attention_items, html_snapshot, text_snapshot,
                        csv_filename, csv_content, is_test
                    )
                    VALUES (
                        %s, %s, %s::date, %s, %s, %s, %s, %s, 'pending', 'resend',
                        %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb,
                        %s, %s, %s, %s, %s
                    )
                    RETURNING *
                    """,
                    (
                        delivery.get("id"),
                        snapshot.get("purpose"),
                        snapshot.get("report_date"),
                        snapshot.get("covered_start"),
                        snapshot.get("covered_end"),
                        snapshot.get("timezone"),
                        snapshot.get("recipient"),
                        snapshot.get("subject"),
                        json.dumps(_archive_staff(snapshot)),
                        json.dumps(_json_safe(snapshot.get("daily_execution") or {})),
                        json.dumps(_json_safe(snapshot.get("summary") or {})),
                        json.dumps(_json_safe(snapshot.get("attention") or [])),
                        snapshot.get("html") or "",
                        snapshot.get("text") or "",
                        snapshot.get("csv_filename") or "report.csv",
                        snapshot.get("csv_content") or "",
                        bool(snapshot.get("is_test")),
                    ),
                )
                archive = cur.fetchone() or {}
                claim_status = "claimed"
            else:
                archive = _archive_by_delivery(cur, delivery.get("id"))
                claim_status = delivery_claim_decision(
                    delivery,
                    stale_before=stale_before,
                )
                if claim_status == "reclaim":
                    cur.execute(
                        """
                        UPDATE activity_report_deliveries
                        SET status='pending',
                            attempt_count=attempt_count + 1,
                            locked_at=now(),
                            updated_at=now(),
                            failed_at=NULL,
                            sanitized_error=NULL
                        WHERE id=%s
                        RETURNING *
                        """,
                        (delivery.get("id"),),
                    )
                    delivery = cur.fetchone() or delivery
                    cur.execute(
                        """
                        UPDATE activity_report_archives
                        SET status='pending', updated_at=now()
                        WHERE delivery_id=%s
                        RETURNING *
                        """,
                        (delivery.get("id"),),
                    )
                    archive = cur.fetchone() or archive
                    claim_status = "reclaimed"
        conn.commit()
    return {
        "status": claim_status,
        "should_send": claim_status in {"claimed", "reclaimed"},
        "delivery": dict(delivery or {}),
        "archive": dict(archive or {}),
    }


def mark_delivery_sent(delivery_id, *, provider_message_id, provider_attempts=1):
    require_schema()
    backend = _backend()
    extra_attempts = max(int(provider_attempts or 1) - 1, 0)
    with backend.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE activity_report_deliveries
                SET status='sent',
                    provider_message_id=%s,
                    attempt_count=attempt_count + %s,
                    sent_at=COALESCE(sent_at, now()),
                    failed_at=NULL,
                    sanitized_error=NULL,
                    locked_at=NULL,
                    updated_at=now()
                WHERE id=%s
                RETURNING *
                """,
                (str(provider_message_id or "")[:250], extra_attempts, str(delivery_id)),
            )
            delivery = cur.fetchone()
            if not delivery:
                raise ReportingStoreError("The report delivery record was not found.")
            cur.execute(
                """
                UPDATE activity_report_archives
                SET status='sent',
                    provider_message_id=%s,
                    sent_at=COALESCE(sent_at, now()),
                    updated_at=now()
                WHERE delivery_id=%s
                RETURNING *
                """,
                (str(provider_message_id or "")[:250], str(delivery_id)),
            )
            archive = cur.fetchone() or {}
        conn.commit()
    return {"delivery": dict(delivery), "archive": dict(archive)}


def mark_delivery_failed(
    delivery_id,
    *,
    sanitized_error,
    retryable,
    provider_attempts=1,
):
    require_schema()
    backend = _backend()
    extra_attempts = max(int(provider_attempts or 1) - 1, 0)
    safe_error = str(sanitized_error or "Email delivery failed.")[:500]
    with backend.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE activity_report_deliveries
                SET status='failed',
                    attempt_count=attempt_count + %s,
                    failed_at=now(),
                    sanitized_error=%s,
                    locked_at=NULL,
                    metadata=COALESCE(metadata, '{}'::jsonb) || %s::jsonb,
                    updated_at=now()
                WHERE id=%s
                RETURNING *
                """,
                (
                    extra_attempts,
                    safe_error,
                    json.dumps({"retryable": bool(retryable)}),
                    str(delivery_id),
                ),
            )
            delivery = cur.fetchone()
            if not delivery:
                raise ReportingStoreError("The report delivery record was not found.")
            cur.execute(
                """
                UPDATE activity_report_archives
                SET status='failed', updated_at=now()
                WHERE delivery_id=%s
                RETURNING *
                """,
                (str(delivery_id),),
            )
            archive = cur.fetchone() or {}
        conn.commit()
    return {"delivery": dict(delivery), "archive": dict(archive)}


def _normalise_archive(row):
    row = dict(row or {})
    if not row:
        return {}
    for key, fallback in (
        ("staff_summaries", []),
        ("daily_execution_summary", {}),
        ("report_summary", {}),
        ("attention_items", []),
    ):
        row[key] = _json_value(row.get(key), fallback)
    row["id"] = str(row.get("id") or "")
    row["delivery_id"] = str(row.get("delivery_id") or "")
    return row


def list_archives(
    user,
    *,
    page=1,
    page_size=DEFAULT_PAGE_SIZE,
    start_date=None,
    end_date=None,
    staff_filter="",
    status_filter="",
):
    _require_reporting_access(user)
    require_schema()
    safe_page = max(int(page or 1), 1)
    safe_size = _safe_limit(page_size)
    clauses = []
    params = []
    if start_date:
        clauses.append("report_date >= %s::date")
        params.append(str(start_date))
    if end_date:
        clauses.append("report_date <= %s::date")
        params.append(str(end_date))
    if staff_filter:
        clauses.append("staff_summaries::text ILIKE %s")
        params.append(f"%{str(staff_filter).strip()}%")
    if status_filter and str(status_filter).casefold() != "all":
        clauses.append("status=%s")
        params.append(str(status_filter).strip().casefold())
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.extend([safe_size, (safe_page - 1) * safe_size])
    backend = _backend()
    with backend.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, delivery_id, purpose, report_date, covered_start_at,
                       covered_end_at, report_timezone, recipient, subject, status,
                       provider, provider_message_id, staff_summaries, report_summary,
                       attention_items, is_test, created_at, sent_at
                FROM activity_report_archives
                {where_sql}
                ORDER BY report_date DESC, created_at DESC
                LIMIT %s OFFSET %s
                """,
                params,
            )
            rows = [_normalise_archive(row) for row in cur.fetchall()]
    return rows


def get_archive(user, archive_id):
    _require_reporting_access(user)
    require_schema()
    backend = _backend()
    with backend.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM activity_report_archives
                WHERE id=%s
                LIMIT 1
                """,
                (str(archive_id),),
            )
            return _normalise_archive(cur.fetchone())


def archive_csv(user, archive_id):
    archive = get_archive(user, archive_id)
    if not archive:
        raise ReportingStoreError("The archived report was not found.")
    return {
        "filename": str(archive.get("csv_filename") or "sports-cave-report.csv"),
        "content": str(archive.get("csv_content") or "").encode("utf-8-sig"),
    }


def list_delivery_history(user, *, limit=10):
    _require_reporting_access(user)
    require_schema()
    safe_limit = _safe_limit(limit, default=10)
    backend = _backend()
    with backend.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, purpose, report_date, recipient, subject, status, provider,
                       provider_message_id, attempt_count, created_at, updated_at,
                       sent_at, failed_at, sanitized_error, metadata, is_test
                FROM activity_report_deliveries
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (safe_limit,),
            )
            rows = [dict(row or {}) for row in cur.fetchall()]
    for row in rows:
        row["id"] = str(row.get("id") or "")
        row["metadata"] = _json_value(row.get("metadata"), {})
    return rows


def today_delivery_status(user, report_date):
    _require_reporting_access(user)
    require_schema()
    backend = _backend()
    with backend.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, status, sent_at, failed_at, sanitized_error, provider_message_id,
                       attempt_count, updated_at
                FROM activity_report_deliveries
                WHERE purpose='daily_staff_activity'
                  AND report_date=%s::date
                  AND is_test IS FALSE
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (str(report_date),),
            )
            row = dict(cur.fetchone() or {})
    if row:
        row["id"] = str(row.get("id") or "")
    return row
