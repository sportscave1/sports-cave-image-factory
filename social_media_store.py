import hashlib
import json
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import os_accounts
import social_media


SOCIAL_MEDIA_MIGRATION = "20260728_social_media_hub.sql"
DEFAULT_HISTORY_LIMIT = 15
MAX_HISTORY_LIMIT = 50


class SocialMediaStoreError(RuntimeError):
    pass


def _backend():
    import supabase_backend

    return supabase_backend


def _safe_limit(value, default=DEFAULT_HISTORY_LIMIT):
    try:
        return min(max(int(value), 1), MAX_HISTORY_LIMIT)
    except (TypeError, ValueError):
        return default


def _json_safe(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def request_key(action, actor_user_id, scope, payload):
    identity = json.dumps(
        {
            "action": str(action or ""),
            "actor_user_id": str(actor_user_id or ""),
            "scope": str(scope or ""),
            "payload": _json_safe(payload),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"social/{hashlib.sha256(identity.encode('utf-8')).hexdigest()}"


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
                        to_regclass('public.social_daily_plans') IS NOT NULL AS daily_plans,
                        to_regclass('public.social_posts') IS NOT NULL AS posts,
                        to_regclass('public.social_weekly_reports') IS NOT NULL AS weekly_reports,
                        to_regclass('public.social_action_requests') IS NOT NULL AS action_requests
                    """
                )
                row = cur.fetchone() or {}
        ready = all(
            bool(row.get(key))
            for key in ("daily_plans", "posts", "weekly_reports", "action_requests")
        )
        return {
            "configured": True,
            "ready": ready,
            "reason": "ok" if ready else "migration_required",
            "migration": SOCIAL_MEDIA_MIGRATION,
        }
    except Exception as error:
        raise SocialMediaStoreError("Social Media setup could not be checked.") from error


def require_schema():
    status = schema_status()
    if not status.get("ready"):
        raise SocialMediaStoreError("Social Media setup is not ready.")
    return status


def _clean_account(account):
    account = dict(account or {})
    return {
        **account,
        "id": str(account.get("id") or ""),
        "display_name": str(
            account.get("display_name")
            or account.get("username")
            or account.get("email")
            or "Staff member"
        ),
        "role": str(account.get("role") or os_accounts.ROLE_WORKER).casefold(),
        "timezone": os_accounts.timezone_for_user(account),
        "is_active": bool(account.get("is_active", True)),
    }


def require_social_access(user):
    if not os_accounts.can_access_page(user, social_media.SOCIAL_MEDIA_ROUTE):
        raise PermissionError("Social Media access is not approved.")
    return _clean_account(user)


def authorised_social_staff(viewer, *, account_store=None):
    viewer = require_social_access(viewer)
    if not os_accounts.is_admin(viewer):
        return [viewer]
    store = account_store or os_accounts.DEFAULT_STORE
    accounts = [
        _clean_account(account)
        for account in store.list_users()
        if bool((account or {}).get("is_active", True))
        and os_accounts.can_access_page(account, social_media.SOCIAL_MEDIA_ROUTE)
    ]
    accounts.sort(
        key=lambda account: (
            str(account.get("id")) != str(viewer.get("id")),
            account.get("display_name", "").casefold(),
        )
    )
    return accounts


def resolve_target_account(viewer, target_user_id="", *, account_store=None):
    viewer = require_social_access(viewer)
    clean_target_id = str(target_user_id or viewer.get("id") or "")
    if not os_accounts.is_admin(viewer):
        if clean_target_id != str(viewer.get("id") or ""):
            raise PermissionError("You can only access your own Social Media work.")
        return viewer
    for account in authorised_social_staff(viewer, account_store=account_store):
        if str(account.get("id") or "") == clean_target_id:
            return account
    raise PermissionError("That staff member does not have Social Media access.")


def _claim_request(cur, *, key, actor_user_id, action_type, entity_type):
    clean_key = str(key or "").strip()
    if not clean_key:
        raise SocialMediaStoreError("A request key is required.")
    cur.execute(
        """
        INSERT INTO social_action_requests(
            request_key, actor_user_id, action_type, entity_type
        )
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (request_key) DO NOTHING
        RETURNING *
        """,
        (
            clean_key,
            str(actor_user_id),
            str(action_type or ""),
            str(entity_type or ""),
        ),
    )
    return cur.fetchone()


def _set_request_entity(cur, request_id, entity_id):
    cur.execute(
        """
        UPDATE social_action_requests
        SET entity_id=%s
        WHERE id=%s
        """,
        (str(entity_id), str(request_id)),
    )


def _request_entity_id(cur, request_key_value):
    cur.execute(
        """
        SELECT entity_id
        FROM social_action_requests
        WHERE request_key=%s
        LIMIT 1
        """,
        (str(request_key_value or ""),),
    )
    row = cur.fetchone() or {}
    return str(row.get("entity_id") or "")


def _plan_row(row):
    row = dict(row or {})
    if not row:
        return {}
    for key in ("id", "user_id", "created_by", "updated_by"):
        row[key] = str(row.get(key) or "")
    row["focus_areas"] = list(row.get("focus_areas") or [])
    row["planned_platforms"] = list(row.get("planned_platforms") or [])
    row["execution_score"] = float(row.get("execution_score") or 0)
    return row


def _priority_rows(rows):
    return [
        {
            "id": str(row.get("id") or ""),
            "plan_id": str(row.get("plan_id") or ""),
            "priority_index": int(row.get("priority_index") or 0),
            "task": str(row.get("task") or ""),
            "completed": bool(row.get("completed")),
        }
        for row in rows or ()
    ]


def _post_row(row):
    row = dict(row or {})
    if not row:
        return {}
    for key in ("id", "user_id", "created_by", "updated_by"):
        row[key] = str(row.get(key) or "")
    platforms = row.get("platforms") or []
    if isinstance(platforms, str):
        try:
            platforms = json.loads(platforms)
        except (TypeError, ValueError, json.JSONDecodeError):
            platforms = []
    row["platforms"] = list(platforms or [])
    return row


def _weekly_row(row):
    row = dict(row or {})
    if not row:
        return {}
    for key in ("id", "user_id", "created_by", "updated_by"):
        row[key] = str(row.get(key) or "")
    if row.get("average_execution_score") is not None:
        row["average_execution_score"] = float(row["average_execution_score"])
    return row


def _daily_snapshot_with_cursor(cur, user_id, plan_date):
    cur.execute(
        """
        SELECT *
        FROM social_daily_plans
        WHERE user_id=%s AND plan_date=%s::date
        LIMIT 1
        """,
        (str(user_id), str(plan_date)),
    )
    plan = _plan_row(cur.fetchone())
    priorities = []
    if plan:
        cur.execute(
            """
            SELECT *
            FROM social_daily_priorities
            WHERE plan_id=%s
            ORDER BY priority_index
            """,
            (plan["id"],),
        )
        priorities = _priority_rows(cur.fetchall())
    cur.execute(
        """
        SELECT
            p.*,
            COALESCE(
                jsonb_agg(
                    jsonb_build_object(
                        'id', pp.id,
                        'platform', pp.platform,
                        'status', pp.status,
                        'scheduled_published_at', pp.scheduled_published_at,
                        'public_url', pp.public_url,
                        'reach_views', pp.reach_views,
                        'engagements', pp.engagements,
                        'link_clicks', pp.link_clicks,
                        'saves_shares', pp.saves_shares,
                        'result_note', pp.result_note
                    )
                    ORDER BY pp.platform
                ) FILTER (WHERE pp.id IS NOT NULL),
                '[]'::jsonb
            ) AS platforms
        FROM social_posts p
        LEFT JOIN social_post_platforms pp ON pp.post_id=p.id
        WHERE p.user_id=%s AND p.created_date=%s::date
        GROUP BY p.id
        ORDER BY p.updated_at DESC
        LIMIT 100
        """,
        (str(user_id), str(plan_date)),
    )
    posts = [_post_row(row) for row in cur.fetchall()]
    live_posts = {
        post["id"]
        for post in posts
        if any(platform.get("status") == "Live" for platform in post["platforms"])
    }
    platforms_used = sorted(
        {
            platform.get("platform")
            for post in posts
            for platform in post["platforms"]
            if platform.get("status") == "Live" and platform.get("platform")
        }
    )
    completed_priorities = sum(row["completed"] for row in priorities)
    return {
        "plan": plan,
        "priorities": priorities,
        "posts": posts,
        "summary": {
            "plan_status": plan.get("status") if plan else "not_started",
            "priorities_completed": completed_priorities,
            "priorities_total": len(priorities),
            "priorities_outstanding": len(priorities) - completed_priorities,
            "posts_logged": len(posts),
            "posts_live": len(live_posts),
            "platforms_used": platforms_used,
            "score": float(plan.get("execution_score") or 0) if plan else 0.0,
            "has_blocker": bool(str(plan.get("blockers") or "").strip()) if plan else False,
        },
    }


def get_daily_snapshot(
    viewer,
    *,
    target_user_id="",
    plan_date=None,
    account_store=None,
):
    target = resolve_target_account(
        viewer,
        target_user_id,
        account_store=account_store,
    )
    require_schema()
    selected_date = plan_date or social_media.sydney_today()
    backend = _backend()
    with backend.connect() as conn:
        with conn.cursor() as cur:
            snapshot = _daily_snapshot_with_cursor(cur, target["id"], selected_date)
    snapshot["staff"] = target
    snapshot["plan_date"] = str(selected_date)
    return snapshot


def _activity_result(action_type, entity_type, entity_id, message, metadata, event_key):
    return {
        "action_type": action_type,
        "page": social_media.SOCIAL_MEDIA_ROUTE,
        "message": message,
        "entity_type": entity_type,
        "entity_id": str(entity_id or ""),
        "metadata": _json_safe(metadata),
        "event_key": str(event_key or ""),
    }


def save_daily_plan(
    viewer,
    *,
    target_user_id="",
    payload,
    completing=False,
    request_key_value,
    account_store=None,
):
    target = resolve_target_account(
        viewer,
        target_user_id,
        account_store=account_store,
    )
    plan = social_media.validate_daily_plan(payload, completing=completing)
    require_schema()
    backend = _backend()
    with backend.connect() as conn:
        with conn.cursor() as cur:
            request = _claim_request(
                cur,
                key=request_key_value,
                actor_user_id=viewer.get("id"),
                action_type="social_day_completed" if completing else "social_plan_saved",
                entity_type="social_daily_plan",
            )
            if not request:
                snapshot = _daily_snapshot_with_cursor(
                    cur,
                    target["id"],
                    plan["plan_date"],
                )
                conn.commit()
                return {**snapshot, "duplicate": True, "activity": None}
            cur.execute(
                """
                SELECT *
                FROM social_daily_plans
                WHERE user_id=%s AND plan_date=%s::date
                LIMIT 1
                FOR UPDATE
                """,
                (target["id"], str(plan["plan_date"])),
            )
            existing = cur.fetchone() or {}
            if existing and str(existing.get("status") or "") == "completed" and not completing:
                raise SocialMediaStoreError("Reopen the completed day before updating it.")
            cur.execute(
                """
                INSERT INTO social_daily_plans(
                    user_id, plan_date, timezone, status, focus_areas,
                    content_plan, planned_platforms, planned_post_count,
                    improvement_test, what_worked, what_learned,
                    improve_next, blockers, execution_score,
                    created_by, updated_by, completed_at
                )
                VALUES (
                    %s, %s::date, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    CASE WHEN %s THEN now() ELSE NULL END
                )
                ON CONFLICT (user_id, plan_date)
                DO UPDATE SET
                    timezone=EXCLUDED.timezone,
                    status=EXCLUDED.status,
                    focus_areas=EXCLUDED.focus_areas,
                    content_plan=EXCLUDED.content_plan,
                    planned_platforms=EXCLUDED.planned_platforms,
                    planned_post_count=EXCLUDED.planned_post_count,
                    improvement_test=EXCLUDED.improvement_test,
                    what_worked=EXCLUDED.what_worked,
                    what_learned=EXCLUDED.what_learned,
                    improve_next=EXCLUDED.improve_next,
                    blockers=EXCLUDED.blockers,
                    execution_score=EXCLUDED.execution_score,
                    updated_by=EXCLUDED.updated_by,
                    completed_at=CASE
                        WHEN EXCLUDED.status='completed'
                        THEN COALESCE(social_daily_plans.completed_at, now())
                        ELSE social_daily_plans.completed_at
                    END,
                    updated_at=now()
                RETURNING *
                """,
                (
                    target["id"],
                    str(plan["plan_date"]),
                    target.get("timezone") or social_media.SOCIAL_TIMEZONE,
                    "completed" if completing else "draft",
                    plan["focus_areas"],
                    plan["content_plan"],
                    plan["planned_platforms"],
                    plan["planned_post_count"],
                    plan["improvement_test"],
                    plan["what_worked"],
                    plan["what_learned"],
                    plan["improve_next"],
                    plan["blockers"],
                    plan["score"],
                    viewer.get("id"),
                    viewer.get("id"),
                    bool(completing),
                ),
            )
            saved = _plan_row(cur.fetchone())
            cur.execute(
                "DELETE FROM social_daily_priorities WHERE plan_id=%s",
                (saved["id"],),
            )
            for priority in plan["priorities"]:
                cur.execute(
                    """
                    INSERT INTO social_daily_priorities(
                        plan_id, priority_index, task, completed
                    )
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        saved["id"],
                        priority["priority_index"],
                        priority["task"],
                        priority["completed"],
                    ),
                )
            _set_request_entity(cur, request["id"], saved["id"])
            snapshot = _daily_snapshot_with_cursor(
                cur,
                target["id"],
                plan["plan_date"],
            )
        conn.commit()
    actor_corrected_other = (
        os_accounts.is_admin(viewer)
        and str(viewer.get("id")) != str(target.get("id"))
    )
    if completing:
        action_type = "social_day_completed"
        message = f"Social day completed: {plan['plan_date']}"
    elif actor_corrected_other:
        action_type = "social_record_corrected"
        message = f"Social plan corrected: {target['display_name']}"
    elif existing:
        action_type = "social_plan_updated"
        message = f"Social plan updated: {plan['plan_date']}"
    else:
        action_type = "social_plan_created"
        message = f"Social plan created: {plan['plan_date']}"
    return {
        **snapshot,
        "duplicate": False,
        "activity": _activity_result(
            action_type,
            "social_daily_plan",
            snapshot["plan"].get("id"),
            message,
            {
                "report_date": str(plan["plan_date"]),
                "target_user_id": target["id"],
                "status": snapshot["plan"].get("status"),
                "result": "success",
                "score": snapshot["summary"]["score"],
            },
            request_key_value,
        ),
    }


def reopen_daily_plan(
    viewer,
    *,
    target_user_id="",
    plan_date=None,
    request_key_value,
    account_store=None,
):
    target = resolve_target_account(
        viewer,
        target_user_id,
        account_store=account_store,
    )
    selected_date = plan_date or social_media.sydney_today()
    require_schema()
    backend = _backend()
    with backend.connect() as conn:
        with conn.cursor() as cur:
            request = _claim_request(
                cur,
                key=request_key_value,
                actor_user_id=viewer.get("id"),
                action_type="social_day_reopened",
                entity_type="social_daily_plan",
            )
            if not request:
                snapshot = _daily_snapshot_with_cursor(cur, target["id"], selected_date)
                conn.commit()
                return {**snapshot, "duplicate": True, "activity": None}
            cur.execute(
                """
                UPDATE social_daily_plans
                SET status='draft',
                    reopened_at=now(),
                    updated_by=%s,
                    updated_at=now()
                WHERE user_id=%s
                  AND plan_date=%s::date
                  AND status='completed'
                RETURNING *
                """,
                (viewer.get("id"), target["id"], str(selected_date)),
            )
            reopened = _plan_row(cur.fetchone())
            if not reopened:
                raise SocialMediaStoreError("The completed social day could not be reopened.")
            _set_request_entity(cur, request["id"], reopened["id"])
            snapshot = _daily_snapshot_with_cursor(cur, target["id"], selected_date)
        conn.commit()
    return {
        **snapshot,
        "duplicate": False,
        "activity": _activity_result(
            "social_day_reopened",
            "social_daily_plan",
            reopened["id"],
            f"Completed social plan reopened: {selected_date}",
            {
                "report_date": str(selected_date),
                "target_user_id": target["id"],
                "status": "draft",
                "result": "success",
            },
            request_key_value,
        ),
    }


POST_SELECT = """
    SELECT
        p.*,
        COALESCE(
            jsonb_agg(
                jsonb_build_object(
                    'id', pp.id,
                    'platform', pp.platform,
                    'status', pp.status,
                    'scheduled_published_at', pp.scheduled_published_at,
                    'public_url', pp.public_url,
                    'reach_views', pp.reach_views,
                    'engagements', pp.engagements,
                    'link_clicks', pp.link_clicks,
                    'saves_shares', pp.saves_shares,
                    'result_note', pp.result_note
                )
                ORDER BY pp.platform
            ) FILTER (WHERE pp.id IS NOT NULL),
            '[]'::jsonb
        ) AS platforms
    FROM social_posts p
    LEFT JOIN social_post_platforms pp ON pp.post_id=p.id
"""


def _post_with_cursor(cur, post_id, *, allowed_user_ids=None):
    if not post_id:
        return {}
    clauses = ["p.id=%s"]
    params = [str(post_id)]
    if allowed_user_ids is not None:
        clean_user_ids = [str(user_id) for user_id in allowed_user_ids if user_id]
        if not clean_user_ids:
            return {}
        clauses.append("p.user_id = ANY(%s)")
        params.append(clean_user_ids)
    cur.execute(
        POST_SELECT
        + f"""
        WHERE {' AND '.join(clauses)}
        GROUP BY p.id
        LIMIT 1
        """,
        params,
    )
    return _post_row(cur.fetchone())


def get_post(
    viewer,
    post_id,
    *,
    account_store=None,
):
    viewer = require_social_access(viewer)
    if os_accounts.is_admin(viewer):
        allowed_user_ids = [
            account["id"]
            for account in authorised_social_staff(
                viewer,
                account_store=account_store,
            )
        ]
    else:
        allowed_user_ids = [viewer["id"]]
    require_schema()
    backend = _backend()
    with backend.connect() as conn:
        with conn.cursor() as cur:
            return _post_with_cursor(
                cur,
                post_id,
                allowed_user_ids=allowed_user_ids,
            )


def _list_posts_with_cursor(
    cur,
    *,
    user_id,
    start_date=None,
    end_date=None,
    platform="",
    content_format="",
    status="",
    limit=DEFAULT_HISTORY_LIMIT,
    offset=0,
):
    clauses = ["p.user_id=%s"]
    params = [str(user_id)]
    if start_date:
        clauses.append("p.created_date >= %s::date")
        params.append(str(start_date))
    if end_date:
        clauses.append("p.created_date <= %s::date")
        params.append(str(end_date))
    if platform:
        clauses.append(
            "EXISTS (SELECT 1 FROM social_post_platforms pf WHERE pf.post_id=p.id AND pf.platform=%s)"
        )
        params.append(str(platform))
    if content_format:
        clauses.append("p.content_format=%s")
        params.append(str(content_format))
    if status:
        clauses.append(
            "EXISTS (SELECT 1 FROM social_post_platforms ps WHERE ps.post_id=p.id AND ps.status=%s)"
        )
        params.append(str(status))
    safe_limit = _safe_limit(limit)
    safe_offset = max(int(offset or 0), 0)
    params.extend([safe_limit, safe_offset])
    cur.execute(
        POST_SELECT
        + f"""
        WHERE {' AND '.join(clauses)}
        GROUP BY p.id
        ORDER BY p.created_date DESC, p.updated_at DESC
        LIMIT %s OFFSET %s
        """,
        params,
    )
    return [_post_row(row) for row in cur.fetchall()]


def list_posts(
    viewer,
    *,
    target_user_id="",
    start_date=None,
    end_date=None,
    platform="",
    content_format="",
    status="",
    limit=DEFAULT_HISTORY_LIMIT,
    offset=0,
    account_store=None,
):
    target = resolve_target_account(
        viewer,
        target_user_id,
        account_store=account_store,
    )
    require_schema()
    backend = _backend()
    with backend.connect() as conn:
        with conn.cursor() as cur:
            return _list_posts_with_cursor(
                cur,
                user_id=target["id"],
                start_date=start_date,
                end_date=end_date,
                platform=platform,
                content_format=content_format,
                status=status,
                limit=limit,
                offset=offset,
            )


def _local_timestamp_for_storage(value, timezone_name):
    if value in (None, ""):
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime):
        raise social_media.SocialValidationError("Choose a valid scheduled or published time.")
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo(timezone_name))
    return value.astimezone(timezone.utc)


def save_post(
    viewer,
    *,
    target_user_id="",
    post_id="",
    payload,
    request_key_value,
    account_store=None,
):
    target = resolve_target_account(
        viewer,
        target_user_id,
        account_store=account_store,
    )
    post = social_media.normalise_post(payload)
    require_schema()
    backend = _backend()
    with backend.connect() as conn:
        with conn.cursor() as cur:
            request = _claim_request(
                cur,
                key=request_key_value,
                actor_user_id=viewer.get("id"),
                action_type="social_post_saved",
                entity_type="social_post",
            )
            if not request:
                duplicate_post_id = str(post_id or "") or _request_entity_id(
                    cur,
                    request_key_value,
                )
                duplicate_post = _post_with_cursor(
                    cur,
                    duplicate_post_id,
                    allowed_user_ids=[target["id"]],
                )
                conn.commit()
                return {
                    "post": duplicate_post,
                    "duplicate": True,
                    "activity": None,
                }
            existing = {}
            previous_platforms = {}
            if post_id:
                cur.execute(
                    "SELECT * FROM social_posts WHERE id=%s LIMIT 1 FOR UPDATE",
                    (str(post_id),),
                )
                existing = cur.fetchone() or {}
                if not existing or str(existing.get("user_id") or "") != target["id"]:
                    raise PermissionError("That post is not available for this account.")
                cur.execute(
                    "SELECT platform, status FROM social_post_platforms WHERE post_id=%s",
                    (str(post_id),),
                )
                previous_platforms = {
                    row.get("platform"): row.get("status")
                    for row in cur.fetchall()
                }
                cur.execute(
                    """
                    UPDATE social_posts
                    SET content_name=%s,
                        campaign=%s,
                        content_format=%s,
                        market=%s,
                        created_date=%s::date,
                        notes=%s,
                        updated_by=%s,
                        updated_at=now()
                    WHERE id=%s
                    RETURNING *
                    """,
                    (
                        post["content_name"],
                        post["campaign"],
                        post["content_format"],
                        post["market"],
                        str(post["created_date"]),
                        post["notes"],
                        viewer.get("id"),
                        str(post_id),
                    ),
                )
                saved = cur.fetchone() or {}
            else:
                cur.execute(
                    """
                    INSERT INTO social_posts(
                        user_id, content_name, campaign, content_format,
                        market, created_date, notes, created_by, updated_by
                    )
                    VALUES (%s, %s, %s, %s, %s, %s::date, %s, %s, %s)
                    RETURNING *
                    """,
                    (
                        target["id"],
                        post["content_name"],
                        post["campaign"],
                        post["content_format"],
                        post["market"],
                        str(post["created_date"]),
                        post["notes"],
                        viewer.get("id"),
                        viewer.get("id"),
                    ),
                )
                saved = cur.fetchone() or {}
            saved_id = str(saved.get("id") or post_id)
            selected_platforms = [row["platform"] for row in post["platforms"]]
            cur.execute(
                """
                DELETE FROM social_post_platforms
                WHERE post_id=%s AND NOT (platform = ANY(%s))
                """,
                (saved_id, selected_platforms),
            )
            for platform in post["platforms"]:
                scheduled_at = _local_timestamp_for_storage(
                    platform.get("scheduled_published_at"),
                    target.get("timezone") or social_media.SOCIAL_TIMEZONE,
                )
                cur.execute(
                    """
                    INSERT INTO social_post_platforms(
                        post_id, platform, status, scheduled_published_at,
                        public_url, reach_views, engagements, link_clicks,
                        saves_shares, result_note
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (post_id, platform)
                    DO UPDATE SET
                        status=EXCLUDED.status,
                        scheduled_published_at=EXCLUDED.scheduled_published_at,
                        public_url=EXCLUDED.public_url,
                        reach_views=EXCLUDED.reach_views,
                        engagements=EXCLUDED.engagements,
                        link_clicks=EXCLUDED.link_clicks,
                        saves_shares=EXCLUDED.saves_shares,
                        result_note=EXCLUDED.result_note,
                        updated_at=now()
                    """,
                    (
                        saved_id,
                        platform["platform"],
                        platform["status"],
                        scheduled_at,
                        platform["public_url"],
                        platform["reach_views"],
                        platform["engagements"],
                        platform["link_clicks"],
                        platform["saves_shares"],
                        platform["result_note"],
                    ),
                )
            _set_request_entity(cur, request["id"], saved_id)
            saved_post = _post_with_cursor(
                cur,
                saved_id,
                allowed_user_ids=[target["id"]],
            )
        conn.commit()
    live_platforms = [
        row["platform"]
        for row in post["platforms"]
        if row["status"] == "Live"
    ]
    newly_live = [
        platform
        for platform in live_platforms
        if previous_platforms.get(platform) != "Live"
    ]
    actor_corrected_other = (
        os_accounts.is_admin(viewer)
        and str(viewer.get("id")) != str(target.get("id"))
    )
    if newly_live:
        action_type = "social_post_marked_live"
        message = f"Social post marked live: {post['content_name']}"
    elif actor_corrected_other:
        action_type = "social_record_corrected"
        message = f"Social post corrected: {post['content_name']}"
    elif existing:
        action_type = "social_post_updated"
        message = f"Social post updated: {post['content_name']}"
    else:
        action_type = "social_post_logged"
        message = f"Social post logged: {post['content_name']}"
    return {
        "post": saved_post,
        "duplicate": False,
        "activity": _activity_result(
            action_type,
            "social_post",
            saved_id,
            message,
            {
                "content_name": post["content_name"],
                "platforms": [row["platform"] for row in post["platforms"]],
                "live_platforms": live_platforms,
                "target_user_id": target["id"],
                "status": "success",
                "result": "success",
            },
            request_key_value,
        ),
    }


def _weekly_aggregates(cur, user_id, week_start, week_end):
    cur.execute(
        """
        SELECT
            ROUND(AVG(execution_score), 1) AS average_score,
            COUNT(*) FILTER (WHERE status='completed') AS completed_workdays
        FROM social_daily_plans
        WHERE user_id=%s
          AND plan_date >= %s::date
          AND plan_date <= %s::date
        """,
        (str(user_id), str(week_start), str(week_end)),
    )
    plan_totals = cur.fetchone() or {}
    cur.execute(
        """
        SELECT COUNT(*) AS mips_completed
        FROM social_daily_priorities p
        JOIN social_daily_plans d ON d.id=p.plan_id
        WHERE d.user_id=%s
          AND d.plan_date >= %s::date
          AND d.plan_date <= %s::date
          AND p.completed IS TRUE
        """,
        (str(user_id), str(week_start), str(week_end)),
    )
    mip_totals = cur.fetchone() or {}
    return {
        "average_execution_score": (
            float(plan_totals["average_score"])
            if plan_totals.get("average_score") is not None
            else None
        ),
        "completed_workdays": int(plan_totals.get("completed_workdays") or 0),
        "mips_completed": int(mip_totals.get("mips_completed") or 0),
    }


def _weekly_snapshot_with_cursor(cur, user_id, week_start):
    start, end = social_media.sydney_week_bounds(week_start)
    cur.execute(
        """
        SELECT *
        FROM social_weekly_reports
        WHERE user_id=%s AND week_start=%s::date
        LIMIT 1
        """,
        (str(user_id), str(start)),
    )
    report = _weekly_row(cur.fetchone())
    metrics = []
    if report:
        cur.execute(
            """
            SELECT *
            FROM social_weekly_platform_metrics
            WHERE report_id=%s
            ORDER BY platform
            """,
            (report["id"],),
        )
        metrics = [dict(row or {}) for row in cur.fetchall()]
    cur.execute(
        """
        SELECT r.id
        FROM social_weekly_reports r
        WHERE r.user_id=%s
          AND r.week_start < %s::date
          AND r.status='submitted'
        ORDER BY r.week_start DESC
        LIMIT 1
        """,
        (str(user_id), str(start)),
    )
    previous = cur.fetchone() or {}
    previous_metrics = []
    if previous:
        cur.execute(
            """
            SELECT *
            FROM social_weekly_platform_metrics
            WHERE report_id=%s
            ORDER BY platform
            """,
            (str(previous.get("id")),),
        )
        previous_metrics = [dict(row or {}) for row in cur.fetchall()]
    aggregates = _weekly_aggregates(cur, user_id, start, end)
    if report:
        report["platform_metrics"] = metrics
        report["summary"] = {
            **social_media.weekly_summary(report, previous_metrics),
            **aggregates,
        }
    return {
        "report": report,
        "platform_metrics": metrics,
        "previous_platform_metrics": previous_metrics,
        "aggregates": aggregates,
        "week_start": start,
        "week_end": end,
    }


def get_weekly_snapshot(
    viewer,
    *,
    target_user_id="",
    week_start=None,
    account_store=None,
):
    target = resolve_target_account(
        viewer,
        target_user_id,
        account_store=account_store,
    )
    require_schema()
    selected_start, _end = social_media.sydney_week_bounds(week_start)
    backend = _backend()
    with backend.connect() as conn:
        with conn.cursor() as cur:
            snapshot = _weekly_snapshot_with_cursor(
                cur,
                target["id"],
                selected_start,
            )
    snapshot["staff"] = target
    return snapshot


def save_weekly_report(
    viewer,
    *,
    target_user_id="",
    payload,
    submitting=False,
    request_key_value,
    account_store=None,
):
    target = resolve_target_account(
        viewer,
        target_user_id,
        account_store=account_store,
    )
    report = social_media.normalise_weekly_report(payload)
    if submitting:
        if not report["platform_metrics"]:
            raise social_media.SocialValidationError(
                "Add at least one platform result before submitting."
            )
        if not all(
            report[field]
            for field in ("performed_best", "learned", "test_next")
        ):
            raise social_media.SocialValidationError(
                "Complete the three weekly reflection questions before submitting."
            )
    require_schema()
    backend = _backend()
    with backend.connect() as conn:
        with conn.cursor() as cur:
            request = _claim_request(
                cur,
                key=request_key_value,
                actor_user_id=viewer.get("id"),
                action_type="social_weekly_submitted" if submitting else "social_weekly_saved",
                entity_type="social_weekly_report",
            )
            if not request:
                snapshot = _weekly_snapshot_with_cursor(
                    cur,
                    target["id"],
                    report["week_start"],
                )
                conn.commit()
                return {**snapshot, "duplicate": True, "activity": None}
            aggregates = _weekly_aggregates(
                cur,
                target["id"],
                report["week_start"],
                report["week_end"],
            )
            cur.execute(
                """
                SELECT *
                FROM social_weekly_reports
                WHERE user_id=%s AND week_start=%s::date
                LIMIT 1
                FOR UPDATE
                """,
                (target["id"], str(report["week_start"])),
            )
            existing = cur.fetchone() or {}
            cur.execute(
                """
                INSERT INTO social_weekly_reports(
                    user_id, week_start, week_end, timezone, status,
                    performed_best, learned, test_next,
                    average_execution_score, mips_completed,
                    completed_workdays, created_by, updated_by, submitted_at
                )
                VALUES (
                    %s, %s::date, %s::date, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    CASE WHEN %s THEN now() ELSE NULL END
                )
                ON CONFLICT (user_id, week_start)
                DO UPDATE SET
                    week_end=EXCLUDED.week_end,
                    timezone=EXCLUDED.timezone,
                    status=EXCLUDED.status,
                    performed_best=EXCLUDED.performed_best,
                    learned=EXCLUDED.learned,
                    test_next=EXCLUDED.test_next,
                    average_execution_score=EXCLUDED.average_execution_score,
                    mips_completed=EXCLUDED.mips_completed,
                    completed_workdays=EXCLUDED.completed_workdays,
                    updated_by=EXCLUDED.updated_by,
                    submitted_at=CASE
                        WHEN EXCLUDED.status='submitted'
                        THEN COALESCE(social_weekly_reports.submitted_at, now())
                        ELSE social_weekly_reports.submitted_at
                    END,
                    updated_at=now()
                RETURNING *
                """,
                (
                    target["id"],
                    str(report["week_start"]),
                    str(report["week_end"]),
                    target.get("timezone") or social_media.SOCIAL_TIMEZONE,
                    "submitted" if submitting else "draft",
                    report["performed_best"],
                    report["learned"],
                    report["test_next"],
                    aggregates["average_execution_score"],
                    aggregates["mips_completed"],
                    aggregates["completed_workdays"],
                    viewer.get("id"),
                    viewer.get("id"),
                    bool(submitting),
                ),
            )
            saved = _weekly_row(cur.fetchone())
            selected_platforms = [row["platform"] for row in report["platform_metrics"]]
            if selected_platforms:
                cur.execute(
                    """
                    DELETE FROM social_weekly_platform_metrics
                    WHERE report_id=%s AND NOT (platform = ANY(%s))
                    """,
                    (saved["id"], selected_platforms),
                )
            else:
                cur.execute(
                    "DELETE FROM social_weekly_platform_metrics WHERE report_id=%s",
                    (saved["id"],),
                )
            for metric in report["platform_metrics"]:
                cur.execute(
                    """
                    INSERT INTO social_weekly_platform_metrics(
                        report_id, platform, audience_total, reach_views,
                        engagements, outbound_clicks, posts_published,
                        best_post_url, best_post_result
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (report_id, platform)
                    DO UPDATE SET
                        audience_total=EXCLUDED.audience_total,
                        reach_views=EXCLUDED.reach_views,
                        engagements=EXCLUDED.engagements,
                        outbound_clicks=EXCLUDED.outbound_clicks,
                        posts_published=EXCLUDED.posts_published,
                        best_post_url=EXCLUDED.best_post_url,
                        best_post_result=EXCLUDED.best_post_result,
                        updated_at=now()
                    """,
                    (
                        saved["id"],
                        metric["platform"],
                        metric["audience_total"],
                        metric["reach_views"],
                        metric["engagements"],
                        metric["outbound_clicks"],
                        metric["posts_published"],
                        metric["best_post_url"],
                        metric["best_post_result"],
                    ),
                )
            _set_request_entity(cur, request["id"], saved["id"])
            snapshot = _weekly_snapshot_with_cursor(
                cur,
                target["id"],
                report["week_start"],
            )
        conn.commit()
    corrected = (
        os_accounts.is_admin(viewer)
        and str(viewer.get("id")) != str(target.get("id"))
    )
    if submitting:
        action_type = "social_weekly_checkin_submitted"
        message = f"Weekly social check-in submitted: {report['week_start']}"
    elif corrected:
        action_type = "social_record_corrected"
        message = f"Weekly social check-in corrected: {target['display_name']}"
    else:
        action_type = "social_weekly_checkin_updated" if existing else "social_weekly_checkin_created"
        message = f"Weekly social check-in saved: {report['week_start']}"
    return {
        **snapshot,
        "duplicate": False,
        "activity": _activity_result(
            action_type,
            "social_weekly_report",
            saved["id"],
            message,
            {
                "week_start": str(report["week_start"]),
                "week_end": str(report["week_end"]),
                "platforms": selected_platforms,
                "target_user_id": target["id"],
                "status": saved.get("status"),
                "result": "success",
            },
            request_key_value,
        ),
    }


def team_today_summary(
    viewer,
    *,
    plan_date=None,
    account_store=None,
):
    viewer = require_social_access(viewer)
    if not os_accounts.is_admin(viewer):
        raise PermissionError("Team Social Media summaries are available to administrators.")
    staff = authorised_social_staff(viewer, account_store=account_store)
    require_schema()
    selected_date = plan_date or social_media.sydney_today()
    staff_ids = [account["id"] for account in staff]
    by_id = {
        account["id"]: {
            "staff": account,
            "plan_status": "not_started",
            "priorities_completed": 0,
            "priorities_total": 0,
            "posts_live": 0,
            "platforms_used": [],
            "score": 0.0,
            "has_blocker": False,
        }
        for account in staff
    }
    backend = _backend()
    with backend.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    d.user_id,
                    d.status,
                    d.execution_score,
                    d.blockers,
                    COUNT(p.id) AS priority_total,
                    COUNT(p.id) FILTER (WHERE p.completed IS TRUE) AS priority_completed
                FROM social_daily_plans d
                LEFT JOIN social_daily_priorities p ON p.plan_id=d.id
                WHERE d.user_id = ANY(%s)
                  AND d.plan_date=%s::date
                GROUP BY d.id
                """,
                (staff_ids, str(selected_date)),
            )
            for row in cur.fetchall():
                user_id = str(row.get("user_id") or "")
                if user_id in by_id:
                    by_id[user_id].update(
                        {
                            "plan_status": row.get("status") or "draft",
                            "priorities_completed": int(row.get("priority_completed") or 0),
                            "priorities_total": int(row.get("priority_total") or 0),
                            "score": float(row.get("execution_score") or 0),
                            "has_blocker": bool(str(row.get("blockers") or "").strip()),
                        }
                    )
            cur.execute(
                """
                SELECT
                    p.user_id,
                    COUNT(DISTINCT p.id) FILTER (WHERE pp.status='Live') AS posts_live,
                    ARRAY_AGG(DISTINCT pp.platform)
                        FILTER (WHERE pp.status='Live') AS platforms_used
                FROM social_posts p
                JOIN social_post_platforms pp ON pp.post_id=p.id
                WHERE p.user_id = ANY(%s)
                  AND p.created_date=%s::date
                GROUP BY p.user_id
                """,
                (staff_ids, str(selected_date)),
            )
            for row in cur.fetchall():
                user_id = str(row.get("user_id") or "")
                if user_id in by_id:
                    by_id[user_id].update(
                        {
                            "posts_live": int(row.get("posts_live") or 0),
                            "platforms_used": sorted(row.get("platforms_used") or []),
                        }
                    )
    return list(by_id.values())


def list_history(
    viewer,
    *,
    target_user_id="",
    start_date=None,
    end_date=None,
    platform="",
    content_format="",
    status="",
    limit=DEFAULT_HISTORY_LIMIT,
    offset=0,
    account_store=None,
):
    target = resolve_target_account(
        viewer,
        target_user_id,
        account_store=account_store,
    )
    require_schema()
    safe_limit = _safe_limit(limit)
    safe_offset = max(int(offset or 0), 0)
    clauses = ["user_id=%s"]
    params = [target["id"]]
    if start_date:
        clauses.append("plan_date >= %s::date")
        params.append(str(start_date))
    if end_date:
        clauses.append("plan_date <= %s::date")
        params.append(str(end_date))
    params.extend([safe_limit, safe_offset])
    backend = _backend()
    with backend.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, user_id, plan_date, status, execution_score,
                       blockers, updated_at, completed_at
                FROM social_daily_plans
                WHERE {' AND '.join(clauses)}
                ORDER BY plan_date DESC
                LIMIT %s OFFSET %s
                """,
                params,
            )
            plans = [_plan_row(row) for row in cur.fetchall()]
            posts = _list_posts_with_cursor(
                cur,
                user_id=target["id"],
                start_date=start_date,
                end_date=end_date,
                platform=platform,
                content_format=content_format,
                status=status.title() if status else "",
                limit=safe_limit,
                offset=safe_offset,
            )
            weekly_params = [target["id"]]
            weekly_clauses = ["user_id=%s"]
            if start_date:
                weekly_clauses.append("week_end >= %s::date")
                weekly_params.append(str(start_date))
            if end_date:
                weekly_clauses.append("week_start <= %s::date")
                weekly_params.append(str(end_date))
            weekly_params.extend([safe_limit, safe_offset])
            cur.execute(
                f"""
                SELECT *
                FROM social_weekly_reports
                WHERE {' AND '.join(weekly_clauses)}
                ORDER BY week_start DESC
                LIMIT %s OFFSET %s
                """,
                weekly_params,
            )
            weekly = [_weekly_row(row) for row in cur.fetchall()]
    return {
        "staff": target,
        "daily_plans": plans,
        "posts": posts,
        "weekly_reports": weekly,
        "limit": safe_limit,
        "offset": safe_offset,
    }


def collect_reporting_social_summaries(accounts, report_date):
    social_accounts = [
        _clean_account(account)
        for account in accounts or ()
        if bool((account or {}).get("is_active", True))
        and os_accounts.can_access_page(account, social_media.SOCIAL_MEDIA_ROUTE)
    ]
    if not social_accounts:
        return {}
    try:
        if not schema_status().get("ready"):
            return {}
    except Exception:
        return {}
    account_ids = [account["id"] for account in social_accounts]
    summaries = {
        account["id"]: {
            "plan_status": "not_started",
            "mips_completed": 0,
            "mips_outstanding": 0,
            "posts_logged": 0,
            "posts_live": 0,
            "platforms": [],
            "posts_live_by_platform": {},
            "score": 0.0,
            "improvement_test": "",
            "main_learning": "",
            "blockers": "",
            "weekly_status": "not_started",
            "weekly_headline": "",
            "weekly_platforms": [],
        }
        for account in social_accounts
    }
    backend = _backend()
    with backend.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    d.user_id,
                    d.status,
                    d.execution_score,
                    d.improvement_test,
                    d.what_learned,
                    d.blockers,
                    COUNT(p.id) FILTER (WHERE p.completed IS TRUE) AS completed,
                    COUNT(p.id) FILTER (WHERE p.completed IS FALSE) AS outstanding
                FROM social_daily_plans d
                LEFT JOIN social_daily_priorities p ON p.plan_id=d.id
                WHERE d.user_id = ANY(%s)
                  AND d.plan_date=%s::date
                GROUP BY d.id
                """,
                (account_ids, str(report_date)),
            )
            for row in cur.fetchall():
                user_id = str(row.get("user_id") or "")
                if user_id in summaries:
                    summaries[user_id].update(
                        {
                            "plan_status": row.get("status") or "draft",
                            "mips_completed": int(row.get("completed") or 0),
                            "mips_outstanding": int(row.get("outstanding") or 0),
                            "score": float(row.get("execution_score") or 0),
                            "improvement_test": str(row.get("improvement_test") or ""),
                            "main_learning": str(row.get("what_learned") or ""),
                            "blockers": str(row.get("blockers") or ""),
                        }
                    )
            cur.execute(
                """
                SELECT
                    p.user_id,
                    COUNT(DISTINCT p.id) AS posts_logged,
                    COUNT(DISTINCT p.id) FILTER (WHERE pp.status='Live') AS posts_live,
                    ARRAY_AGG(DISTINCT pp.platform)
                        FILTER (WHERE pp.status='Live') AS platforms
                FROM social_posts p
                JOIN social_post_platforms pp ON pp.post_id=p.id
                WHERE p.user_id = ANY(%s)
                  AND p.created_date=%s::date
                GROUP BY p.user_id
                """,
                (account_ids, str(report_date)),
            )
            for row in cur.fetchall():
                user_id = str(row.get("user_id") or "")
                if user_id in summaries:
                    summaries[user_id].update(
                        {
                            "posts_logged": int(row.get("posts_logged") or 0),
                            "posts_live": int(row.get("posts_live") or 0),
                            "platforms": sorted(row.get("platforms") or []),
                        }
                    )
            cur.execute(
                """
                SELECT
                    p.user_id,
                    pp.platform,
                    COUNT(DISTINCT p.id) AS posts_live
                FROM social_posts p
                JOIN social_post_platforms pp ON pp.post_id=p.id
                WHERE p.user_id = ANY(%s)
                  AND p.created_date=%s::date
                  AND pp.status='Live'
                GROUP BY p.user_id, pp.platform
                """,
                (account_ids, str(report_date)),
            )
            for row in cur.fetchall():
                user_id = str(row.get("user_id") or "")
                if user_id in summaries:
                    summaries[user_id]["posts_live_by_platform"][
                        str(row.get("platform") or "")
                    ] = int(row.get("posts_live") or 0)
            cur.execute(
                """
                WITH latest AS (
                    SELECT DISTINCT ON (user_id)
                        id, user_id, status, week_start, performed_best, learned, test_next
                    FROM social_weekly_reports
                    WHERE user_id = ANY(%s)
                      AND week_start <= %s::date
                    ORDER BY user_id, week_start DESC
                ),
                previous AS (
                    SELECT DISTINCT ON (r.user_id)
                        r.id, r.user_id
                    FROM social_weekly_reports r
                    JOIN latest l ON l.user_id=r.user_id
                    WHERE r.status='submitted'
                      AND r.week_start < l.week_start
                    ORDER BY r.user_id, r.week_start DESC
                )
                SELECT
                    l.*,
                    m.platform,
                    m.posts_published,
                    m.audience_total,
                    m.reach_views,
                    m.engagements,
                    pm.audience_total AS previous_audience_total,
                    pm.reach_views AS previous_reach_views,
                    pm.engagements AS previous_engagements
                FROM latest l
                LEFT JOIN social_weekly_platform_metrics m ON m.report_id=l.id
                LEFT JOIN previous p ON p.user_id=l.user_id
                LEFT JOIN social_weekly_platform_metrics pm
                    ON pm.report_id=p.id AND pm.platform=m.platform
                ORDER BY l.user_id, m.platform
                """,
                (account_ids, str(report_date)),
            )
            for row in cur.fetchall():
                user_id = str(row.get("user_id") or "")
                if user_id in summaries:
                    summary = summaries[user_id]
                    summary["weekly_status"] = str(row.get("status") or "draft")
                    if row.get("platform"):
                        summary["weekly_platforms"].append(
                            {
                                "platform": str(row.get("platform") or ""),
                                "posts_published": row.get("posts_published"),
                                "audience_total": row.get("audience_total"),
                                "audience_change": social_media.metric_change(
                                    row.get("audience_total"),
                                    row.get("previous_audience_total"),
                                ),
                                "reach_views": row.get("reach_views"),
                                "reach_views_change": social_media.metric_change(
                                    row.get("reach_views"),
                                    row.get("previous_reach_views"),
                                ),
                                "engagements": row.get("engagements"),
                                "engagements_change": social_media.metric_change(
                                    row.get("engagements"),
                                    row.get("previous_engagements"),
                                ),
                            }
                        )
            for summary in summaries.values():
                weekly_rows = summary.get("weekly_platforms") or []
                published = sum(
                    int(row.get("posts_published") or 0)
                    for row in weekly_rows
                )
                measured = [row for row in weekly_rows if row.get("audience_total") is not None]
                headline_parts = []
                if weekly_rows:
                    headline_parts.append(f"{published} posts")
                if measured:
                    headline_parts.append(
                        f"{sum(int(row['audience_total']) for row in measured)} total audience"
                    )
                summary["weekly_headline"] = ", ".join(headline_parts)
    return summaries


def reporting_team_overview(social_summaries):
    rows = list((social_summaries or {}).values())
    platform_counts = {}
    for row in rows:
        for platform, count in (row.get("posts_live_by_platform") or {}).items():
            platform_counts[platform] = platform_counts.get(platform, 0) + int(count or 0)
    scored = [float(row.get("score") or 0) for row in rows if row.get("plan_status") != "not_started"]
    return {
        "staff_count": len(rows),
        "completed_days": sum(row.get("plan_status") == "completed" for row in rows),
        "posts_live": sum(int(row.get("posts_live") or 0) for row in rows),
        "posts_live_by_platform": platform_counts,
        "average_score": round(sum(scored) / len(scored), 1) if scored else 0.0,
        "outstanding_mips": sum(int(row.get("mips_outstanding") or 0) for row in rows),
        "blockers": sum(bool(str(row.get("blockers") or "").strip()) for row in rows),
    }
