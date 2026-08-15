"""Permission-scoped, same-origin APIs for the Sports Cave OS utility bar."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3

from starlette.requests import Request
from starlette.responses import JSONResponse

import os_accounts
import order_action_state
import seo_navigation
import top_bar_security


BASE_DIR = Path(__file__).resolve().parent
LOCAL_SEO_PATH = BASE_DIR / "output" / "_cache" / "seo_workspace.json"
LOCAL_PRODUCT_DB_PATH = BASE_DIR / "data" / "sports_cave_os.db"
SEARCH_INDEX_PATH = "/api/os/top-bar/search-index"
NOTIFICATIONS_PATH = "/api/os/top-bar/notifications"
ORDER_STATUS_PATH = "/api/os/top-bar/order-status"
DAILY_PLANNER_STATUS_PATH = "/api/os/top-bar/daily-planner-status"
_TASK_SEARCH_FIELDS = ("title", "text", "section", "category", "status")
_TASK_METADATA_FIELDS = (
    "sport",
    "team_or_athlete",
    "design_title",
    "moment_or_theme",
    "tags",
)
_PRODUCT_SEARCH_FIELDS = (
    "product_name",
    "product_title",
    "title",
    "live_product_url",
    "public_url",
    "sport_category",
    "sport",
    "status",
    "handle",
    "tags",
)
_ORDER_SEARCH_FIELDS = (
    "order_name",
    "name",
    "order_number",
    "shopify_order_id",
    "fulfillment_status",
    "financial_status",
    "status",
    "tags",
)
_SENSITIVE_TERMS = (
    "password",
    "passcode",
    "secret",
    "token",
    "credential",
    "oauth",
    "api key",
    "private link",
    "refresh key",
)
_WARNING_TERMS = (
    "failed",
    "failure",
    "warning",
    "error",
    "denied",
    "incomplete",
    "conflict",
    "blocked",
    "unavailable",
)
_NOTIFICATION_EVENT_ALLOWLIST = {
    "new_order_received",
    "order_fulfilled",
    "order_fulfilled_certificate_generated",
    "certificate_generated",
    "certificate_uploaded",
    "citation_import_failed",
    "product_uploaded",
    "design_task_completed",
    "task_completed",
    "dashboard_task_completed",
    "daily_execution_mip_completed",
    "daily_execution_mip_could_not_finish",
    "daily_planner_task_started",
    "daily_planner_task_halfway",
    "daily_planner_task_time_up",
    "daily_planner_task_completed",
    "daily_planner_task_did_not_finish",
    "mockup_generated",
    "mockup_made",
    "mockup_pack_exported",
}
_NOTIFICATION_EXCLUDED_TERMS = (
    "afterpay",
    "cricket",
    "golf",
    "tennis",
    "seasonal",
    "campaign",
    "sporting event",
    "metafield",
    "mirror",
    "sync",
    "poll",
    "webhook",
    "health check",
    "cache",
    "migration",
    "reconciliation",
    "debug",
    "downloaded file",
    "activity",
)


def _json(payload, status_code=200):
    return JSONResponse(
        payload,
        status_code=status_code,
        headers={"Cache-Control": "no-store"},
    )


def _claims(request: Request):
    authorization = str(request.headers.get("Authorization") or "").strip()
    token = ""
    if authorization.casefold().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    valid, _reason, claims = top_bar_security.validate_top_bar_token(token)
    if not valid:
        return {}
    return claims


def _text(value, *, limit=240):
    clean = " ".join(str(value or "").split()).strip()
    return clean[:limit]


def _safe_public_url(value):
    clean = _text(value, limit=1000)
    if not clean.casefold().startswith(("https://", "http://")):
        return ""
    if "@" in clean.split("//", 1)[-1].split("/", 1)[0]:
        return ""
    return clean


def _search_result(
    group,
    title,
    *,
    subtitle="",
    route_key="",
    query=None,
    keywords=(),
):
    clean_title = _text(title, limit=180)
    if not clean_title:
        return None
    safe_keywords = [
        _text(value, limit=260)
        for value in keywords
        if _text(value, limit=260)
    ]
    return {
        "group": _text(group, limit=40),
        "title": clean_title,
        "subtitle": _text(subtitle, limit=220),
        "route_key": _text(route_key, limit=100),
        "query": _text(clean_title if query is None else query, limit=180),
        "keywords": safe_keywords,
    }


def _page_results(claims):
    allowed = set(claims.get("allowed_routes") or ())
    results = []
    for page in os_accounts.PAGE_REGISTRY:
        route = str(page.get("route") or "")
        if route not in allowed:
            continue
        label = str(page.get("label") or route)
        result = _search_result(
            "Pages",
            label,
            subtitle="Application page",
            route_key=page.get("key"),
            keywords=(route, page.get("parent_key")),
        )
        if result:
            results.append(result)
    if claims.get("can_view_activity") and "Dashboard" in allowed:
        results.append(
            _search_result(
                "Pages",
                "Activity Log",
                subtitle="Home activity history",
                route_key="dashboard",
                query="Activity Log",
                keywords=("audit", "history", "events"),
            )
        )
    return results


def _postgres_table_rows(
    cur,
    table_name,
    fields,
    *,
    nested_metadata_fields=(),
    limit=300,
):
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", str(table_name or "")):
        return []
    safe_fields = tuple(
        field
        for field in fields
        if re.fullmatch(r"[a-z_][a-z0-9_]*", str(field or ""))
    )
    safe_metadata_fields = tuple(
        field
        for field in nested_metadata_fields
        if re.fullmatch(r"[a-z_][a-z0-9_]*", str(field or ""))
    )
    if not safe_fields:
        return []
    cur.execute("SELECT to_regclass(%s) AS table_name", (f"public.{table_name}",))
    exists = cur.fetchone() or {}
    if not exists.get("table_name"):
        return []
    pairs = [
        f"'{field}', safe.row_json->>'{field}'"
        for field in safe_fields
    ]
    if safe_metadata_fields:
        metadata_pairs = ", ".join(
            f"'{field}', safe.row_json->'metadata'->>'{field}'"
            for field in safe_metadata_fields
        )
        pairs.append(f"'metadata', jsonb_build_object({metadata_pairs})")
    cur.execute(
        f"""
        SELECT jsonb_build_object({", ".join(pairs)}) AS payload
        FROM {table_name} row_data
        CROSS JOIN LATERAL (
            SELECT to_jsonb(row_data) AS row_json
        ) safe
        LIMIT %s
        """,
        (max(1, min(int(limit), 500)),),
    )
    return [dict((row or {}).get("payload") or {}) for row in cur.fetchall()]


def _postgres_account_rows(cur):
    cur.execute("SELECT to_regclass('public.os_users') AS table_name")
    exists = cur.fetchone() or {}
    if not exists.get("table_name"):
        return []
    cur.execute(
        """
        SELECT id, username, display_name, role, country, is_active, account_status
        FROM os_users
        WHERE COALESCE(account_status, '') <> 'removed'
        ORDER BY CASE WHEN role='admin' THEN 0 ELSE 1 END, display_name, username
        LIMIT 300
        """
    )
    return [dict(row or {}) for row in cur.fetchall()]


def _postgres_seo_state(cur):
    specifications = {
        "citations": (
            "platform",
            "username_handle",
            "profile_url",
            "status",
            "category",
            "archived_at",
        ),
        "blog_records": (
            "article_title",
            "sport_topic",
            "primary_keyword",
            "status",
            "url_slug",
            "archived_at",
        ),
        "link_plans": (
            "source_blog",
            "label",
            "sport",
            "status",
            "homepage_url",
            "collection_url",
            "product_url",
            "archived_at",
        ),
        "outreach_records": (
            "site_creator",
            "website",
            "niche",
            "status",
            "target_page",
            "live_url",
            "archived_at",
        ),
        "keywords": (
            "keyword",
            "raw_query",
            "category",
            "sport_player",
            "intent",
            "status",
            "target_url",
            "archived_at",
        ),
    }
    state = {}
    for collection, fields in specifications.items():
        pairs = ", ".join(
            f"'{field}', record->>'{field}'"
            for field in fields
        )
        cur.execute(
            f"""
            SELECT jsonb_build_object({pairs}) AS payload
            FROM seo_workspace_state workspace,
                 LATERAL jsonb_array_elements(
                     COALESCE(workspace.payload->%s, '[]'::jsonb)
                 ) AS record
            WHERE workspace.workspace_key=%s
            LIMIT 500
            """,
            (collection, "sports-cave"),
        )
        state[collection] = [
            dict((row or {}).get("payload") or {})
            for row in cur.fetchall()
        ]
    return state


def _postgres_sources(claims):
    try:
        import supabase_backend

        if not supabase_backend.is_configured():
            return {}
        with supabase_backend.connect() as conn:
            with conn.cursor() as cur:
                sources = {
                    "tasks": _postgres_table_rows(
                        cur,
                        "dashboard_tasks",
                        _TASK_SEARCH_FIELDS,
                        nested_metadata_fields=_TASK_METADATA_FIELDS,
                    ),
                    "products": _postgres_table_rows(
                        cur,
                        "edition_products",
                        _PRODUCT_SEARCH_FIELDS,
                    ),
                    "orders": _postgres_table_rows(
                        cur,
                        "shopify_orders",
                        _ORDER_SEARCH_FIELDS,
                    ),
                }
                if str(claims.get("role") or "") == os_accounts.ROLE_ADMIN:
                    sources["accounts"] = _postgres_account_rows(cur)
                cur.execute(
                    "SELECT to_regclass('public.seo_workspace_state') AS table_name"
                )
                exists = cur.fetchone() or {}
                if exists.get("table_name"):
                    sources["seo"] = _postgres_seo_state(cur)
                return sources
    except Exception:
        return {}


def _local_sources():
    sources = {}
    if LOCAL_SEO_PATH.is_file():
        try:
            sources["seo"] = json.loads(LOCAL_SEO_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    if LOCAL_PRODUCT_DB_PATH.is_file():
        try:
            with sqlite3.connect(LOCAL_PRODUCT_DB_PATH) as conn:
                conn.row_factory = sqlite3.Row
                tables = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                if "products" in tables:
                    columns = {
                        row[1]
                        for row in conn.execute("PRAGMA table_info(products)")
                    }
                    selected = [
                        field for field in _PRODUCT_SEARCH_FIELDS if field in columns
                    ]
                    if selected:
                        order = " ORDER BY updated_at DESC" if "updated_at" in columns else ""
                        sources["products"] = [
                            dict(row)
                            for row in conn.execute(
                                f'SELECT {", ".join(f"[{field}]" for field in selected)} '
                                f"FROM products{order} LIMIT 300"
                            ).fetchall()
                        ]
                if "shopify_orders" in tables:
                    columns = {
                        row[1]
                        for row in conn.execute("PRAGMA table_info(shopify_orders)")
                    }
                    selected = [
                        field for field in _ORDER_SEARCH_FIELDS if field in columns
                    ]
                    if selected:
                        sources["orders"] = [
                            dict(row)
                            for row in conn.execute(
                                f'SELECT {", ".join(f"[{field}]" for field in selected)} '
                                "FROM shopify_orders LIMIT 300"
                            ).fetchall()
                        ]
        except (OSError, sqlite3.DatabaseError):
            pass
    return sources


def load_search_sources(claims):
    """Read existing persistence without running migrations or external connectors."""
    postgres = _postgres_sources(claims)
    local = _local_sources()
    merged = dict(local)
    for key, value in postgres.items():
        if value:
            merged[key] = value
    return merged


def _task_results(rows):
    results = []
    for row in rows or ():
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        title = row.get("title") or row.get("text")
        section = _text(row.get("section") or row.get("category"))
        is_design = "design" in section.casefold()
        result = _search_result(
            "Designs" if is_design else "Tasks",
            title,
            subtitle=" | ".join(filter(None, (section, _text(row.get("status"))))),
            route_key="design_studio" if is_design else "dashboard",
            query="",
            keywords=(
                metadata.get("sport"),
                metadata.get("team_or_athlete"),
                metadata.get("design_title"),
                metadata.get("moment_or_theme"),
                metadata.get("tags"),
            ),
        )
        if result:
            results.append(result)
    return results


def _product_results(rows, *, route_key):
    results = []
    for row in rows or ():
        title = row.get("product_name") or row.get("product_title") or row.get("title")
        public_url = _safe_public_url(
            row.get("live_product_url") or row.get("public_url")
        )
        result = _search_result(
            "Products",
            title,
            subtitle=" | ".join(
                filter(
                    None,
                    (
                        _text(row.get("sport_category") or row.get("sport")),
                        _text(row.get("status")),
                    ),
                )
            ),
            route_key=route_key,
            keywords=(row.get("handle"), row.get("tags"), public_url),
        )
        if result:
            results.append(result)
    return results


def _order_results(rows):
    results = []
    for row in rows or ():
        identifier = (
            row.get("order_name")
            or row.get("name")
            or row.get("order_number")
            or row.get("shopify_order_id")
        )
        title = f"Order {identifier}" if identifier else ""
        result = _search_result(
            "Orders",
            title,
            subtitle=_text(
                row.get("fulfillment_status")
                or row.get("financial_status")
                or row.get("status")
            ),
            route_key="orders",
            keywords=(row.get("tags"),),
        )
        if result:
            results.append(result)
    return results


def _seo_results(state):
    if not isinstance(state, dict):
        return []
    results = []
    specifications = (
        (
            "citations",
            "Citations",
            "seo_citations",
            ("platform",),
            ("username_handle", "profile_url", "status", "category"),
        ),
        (
            "blog_records",
            "Blog Content",
            "seo_blog_content",
            ("article_title",),
            ("sport_topic", "primary_keyword", "status", "url_slug"),
        ),
        (
            "link_plans",
            "Internal Linking",
            "seo_internal_linking",
            ("source_blog", "label"),
            ("sport", "status", "homepage_url", "collection_url", "product_url"),
        ),
        (
            "outreach_records",
            "Backlinks & Outreach",
            "seo_backlinks_outreach",
            ("site_creator",),
            ("website", "niche", "status", "target_page", "live_url"),
        ),
        (
            "keywords",
            "Keyword Research",
            "seo_keyword_research_mapping",
            ("keyword", "raw_query"),
            ("category", "sport_player", "intent", "status", "target_url"),
        ),
    )
    for collection, subtitle, route_key, title_fields, keyword_fields in specifications:
        for row in state.get(collection) or ():
            if not isinstance(row, dict) or row.get("archived_at"):
                continue
            title = next((_text(row.get(field)) for field in title_fields if row.get(field)), "")
            result = _search_result(
                "SEO",
                title,
                subtitle=subtitle,
                route_key=route_key,
                keywords=(row.get(field) for field in keyword_fields),
            )
            if result:
                results.append(result)
    return results


def _account_results(rows, claims):
    source = list(rows or ())
    if not source:
        source = [
            {
                "id": claims.get("sub"),
                "display_name": claims.get("display_name"),
                "username": claims.get("username"),
                "role": claims.get("role"),
                "is_active": True,
            }
        ]
    results = []
    for row in source:
        title = row.get("display_name") or row.get("username")
        status = row.get("account_status") or (
            "Active" if row.get("is_active", True) else "Inactive"
        )
        result = _search_result(
            "Accounts",
            title,
            subtitle=" | ".join(filter(None, (_text(row.get("role")).title(), _text(status)))),
            route_key="accounts_access",
            query="",
            keywords=(row.get("username"), row.get("country")),
        )
        if result:
            results.append(result)
    return results


def build_search_index(claims, sources=None):
    """Build a permission-scoped index from explicitly allowlisted safe fields."""
    sources = dict(sources or {})
    allowed = set(claims.get("allowed_routes") or ())
    results = _page_results(claims)
    if "Dashboard" in allowed:
        results.extend(_task_results(sources.get("tasks")))
    if "Product Uploads" in allowed:
        product_route_key = "products" if "Products" in allowed else "product_uploads"
        results.extend(
            _product_results(
                sources.get("products"),
                route_key=product_route_key,
            )
        )
    if "Orders" in allowed:
        results.extend(_order_results(sources.get("orders")))
    if any(route in allowed for route in seo_navigation.SEO_ROUTES):
        results.extend(_seo_results(sources.get("seo")))
    if "Accounts & Access" in allowed:
        results.extend(_account_results(sources.get("accounts"), claims))
    unique = []
    seen = set()
    for result in results:
        if not result:
            continue
        serialised = json.dumps(result, ensure_ascii=False).casefold()
        if any(term in serialised for term in _SENSITIVE_TERMS):
            continue
        key = (
            result["group"].casefold(),
            result["title"].casefold(),
            result["route_key"].casefold(),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(result)
    return unique


def _route_key_for_area(area):
    clean = _text(area).casefold()
    for page in os_accounts.PAGE_REGISTRY:
        if clean in {
            str(page.get("route") or "").casefold(),
            str(page.get("label") or "").casefold(),
            str(page.get("key") or "").replace("_", " ").casefold(),
        }:
            return str(page.get("key") or "")
    return "dashboard"


def _notification_text(row):
    row = dict(row or {})
    payload = row.get("new_value") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = {}
    message = _text(
        payload.get("message")
        or row.get("reason")
        or row.get("event_type")
        or "Activity update",
        limit=220,
    )
    if any(term in message.casefold() for term in _SENSITIVE_TERMS):
        message = _text(row.get("event_type") or "Protected activity update")
    return message


def _notification_payload(row):
    payload = (row or {}).get("new_value") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = {}
    return payload if isinstance(payload, dict) else {}


def _notification_row_allowed(row):
    row = dict(row or {})
    payload = _notification_payload(row)
    action_type = _text(payload.get("action_type") or row.get("event_type"), limit=120).casefold()
    if action_type not in _NOTIFICATION_EVENT_ALLOWLIST:
        return False
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    message = _notification_text(row)
    combined = " ".join(
        str(value or "").casefold()
        for value in (
            action_type,
            message,
            payload.get("page"),
            row.get("source"),
            metadata.get("page_area"),
        )
    )
    return bool(message and not any(term in combined for term in _NOTIFICATION_EXCLUDED_TERMS))


def _friendly_notification_text(row):
    payload = _notification_payload(row)
    action_type = _text(payload.get("action_type") or (row or {}).get("event_type"), limit=120)
    message = _notification_text(row)
    try:
        import sports_cave_dashboard

        return sports_cave_dashboard.clean_activity_message(
            action_type,
            message,
            metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
            entity_type=(row or {}).get("entity_type") or "",
            entity_id=(row or {}).get("entity_id") or "",
        )
    except Exception:
        return message


def build_notifications(claims, *, activity_rows=(), alerts=()):
    if not claims.get("can_view_activity"):
        return []
    subject = str(claims.get("sub") or "")
    items = []
    seen = set()
    for row in activity_rows or ():
        if not _notification_row_allowed(row):
            continue
        payload = _notification_payload(row)
        metadata = payload.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        actor_id = str(metadata.get("actor_id") or "")
        if not claims.get("can_view_all_activity") and actor_id != subject:
            continue
        message = _friendly_notification_text(row)
        area = _text(payload.get("page") or row.get("source") or "Home")
        dedupe_key = (
            str(metadata.get("event_key") or ""),
            str(row.get("event_type") or ""),
            str(row.get("entity_type") or ""),
            str(row.get("entity_id") or ""),
            message.casefold(),
        )
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        warning = any(term in message.casefold() for term in _WARNING_TERMS)
        items.append(
            {
                "title": message,
                "subtitle": area or "Activity Log",
                "route_key": _route_key_for_area(area),
                "created_at": str(row.get("created_at") or ""),
                "priority": 0 if warning else 2,
            }
        )
    items.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    items.sort(key=lambda item: int(item.get("priority") or 0))
    return [{key: value for key, value in item.items() if key != "priority"} for item in items[:10]]


def load_notification_sources(claims):
    activity_rows = []
    try:
        import supabase_backend

        if supabase_backend.is_configured():
            with supabase_backend.connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT to_regclass('public.audit_logs') AS table_name")
                    exists = cur.fetchone() or {}
                    if exists.get("table_name"):
                        cur.execute(
                            """
                            SELECT to_jsonb(activity) AS payload
                            FROM audit_logs activity
                            ORDER BY created_at DESC
                            LIMIT 24
                            """
                        )
                        activity_rows = [
                            dict((row or {}).get("payload") or {})
                            for row in cur.fetchall()
                        ]
    except Exception:
        activity_rows = []
    return activity_rows, []


async def top_bar_search_index(request: Request):
    claims = _claims(request)
    if not claims:
        return _json({"ok": False, "error": "Access not approved."}, 403)
    index = build_search_index(claims, load_search_sources(claims))
    return _json({"ok": True, "results": index})


async def top_bar_notifications(request: Request):
    claims = _claims(request)
    if not claims:
        return _json({"ok": False, "error": "Access not approved."}, 403)
    activity_rows, alerts = load_notification_sources(claims)
    return _json(
        {
            "ok": True,
            "notifications": build_notifications(
                claims,
                activity_rows=activity_rows,
                alerts=alerts,
            ),
        }
    )


def load_order_status(claims):
    if "Orders" not in set(claims.get("allowed_routes") or ()):
        return {"action_required_count": 0, "badge_label": "", "notification": {}}
    summary = {"action_required_count": 0, "badge_label": ""}
    notification = {}
    supabase_configured = False
    supabase_summary_loaded = False
    try:
        import supabase_backend

        supabase_configured = supabase_backend.is_configured()
        if supabase_configured:
            summary = supabase_backend.get_order_action_summary()
            supabase_summary_loaded = True
    except Exception:
        pass
    if supabase_configured:
        try:
            events = supabase_backend.consume_new_order_notifications(claims.get("sub") or "")
            notification = order_action_state.new_order_notification(events)
        except Exception:
            pass
        if supabase_summary_loaded:
            return {**summary, "notification": notification}
    try:
        import order_allocator

        payload = order_allocator.load_orders_snapshot()
        rows = payload.get("rows") if isinstance(payload, dict) else payload
        count = order_action_state.count_orders_requiring_action(rows or [])
        summary = {
            "action_required_count": count,
            "badge_label": order_action_state.badge_label(count),
        }
    except Exception:
        pass
    return {**summary, "notification": notification}


async def top_bar_order_status(request: Request):
    claims = _claims(request)
    if not claims:
        return _json({"ok": False, "error": "Access not approved."}, 403)
    return _json({"ok": True, **load_order_status(claims)})


def load_daily_planner_status(claims):
    if not claims.get("can_manage_daily_planner"):
        return {"enabled": False, "timer": {}, "events": []}
    user_id = str(claims.get("sub") or "").strip()
    if not user_id:
        return {"enabled": False, "timer": {}, "events": []}
    events = []
    timer = {}
    try:
        import supabase_backend

        if supabase_backend.is_configured():
            events = supabase_backend.reconcile_daily_execution_timers(user_id)
            timer = supabase_backend.get_daily_execution_active_timer(user_id)
    except Exception:
        events = []
        timer = {}
    return {
        "enabled": True,
        "timer": timer or {},
        "events": events or [],
    }


async def top_bar_daily_planner_status(request: Request):
    claims = _claims(request)
    if not claims:
        return _json({"ok": False, "error": "Access not approved."}, 403)
    return _json({"ok": True, **load_daily_planner_status(claims)})


TOP_BAR_ROUTE_HANDLERS = (
    (SEARCH_INDEX_PATH, top_bar_search_index, ("GET",)),
    (NOTIFICATIONS_PATH, top_bar_notifications, ("GET",)),
    (ORDER_STATUS_PATH, top_bar_order_status, ("GET",)),
    (DAILY_PLANNER_STATUS_PATH, top_bar_daily_planner_status, ("GET",)),
)
