"""Sports Cave OS top-bar component bridge."""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

import os_accounts
import top_bar_security
from daily_planner import PLANNER_WINDOW_PATH


COMPONENT_PATH = (
    Path(__file__).resolve().parent / "components" / "sports_cave_top_bar" / "index.html"
)


def allowed_routes_for_user(user):
    return tuple(
        page["route"]
        for page in os_accounts.PAGE_REGISTRY
        if os_accounts.can_access_page(user, page["route"])
    )


def top_bar_config(user, *, logo_src, current_route, navigation_epoch=0):
    allowed_routes = allowed_routes_for_user(user)
    navigation_route_keys = {
        str(page["label"]): str(page["key"])
        for page in os_accounts.PAGE_REGISTRY
        if page["route"] in allowed_routes
        and page["route"] != os_accounts.DAILY_PLANNER_ROUTE
    }
    if "Reporting" in allowed_routes:
        navigation_route_keys["Overview"] = "reporting"
    planner_enabled = os_accounts.is_admin(user)
    revision_payload = {
        "user_id": str((user or {}).get("id") or ""),
        "session_version": int((user or {}).get("session_version") or 1),
        "role": str((user or {}).get("role") or ""),
        "allowed_routes": allowed_routes,
        "planner_enabled": planner_enabled,
        "can_view_activity": os_accounts.can_view_activity_log(user),
        "can_view_all_activity": os_accounts.is_reporting_owner(user),
    }
    revision = hashlib.sha256(
        json.dumps(revision_payload, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    planner_timer_scope = hashlib.sha256(
        f"sports-cave-planner|{str((user or {}).get('id') or '').strip()}".encode("utf-8")
    ).hexdigest()[:24]
    token = top_bar_security.create_top_bar_token(
        user,
        allowed_routes=allowed_routes,
        can_view_activity=os_accounts.can_view_activity_log(user),
        can_view_all_activity=os_accounts.is_reporting_owner(user),
        can_manage_daily_planner=planner_enabled,
    )
    return {
        "appName": "Sports Cave OS",
        "appSubtitle": "Operations System",
        "userDisplayName": str((user or {}).get("display_name") or "").strip(),
        "logoSrc": str(logo_src or ""),
        "currentRoute": str(current_route or ""),
        "currentRouteKey": os_accounts.page_key_for_route(current_route) or "",
        "navigationEpoch": int(navigation_epoch or 0),
        "navigationRouteKeys": navigation_route_keys,
        "accountsRouteKey": "accounts_access",
        "searchUrl": "/api/os/top-bar/search-index",
        "notificationsUrl": "/api/os/top-bar/notifications",
        "orderStatusUrl": "/api/os/top-bar/order-status",
        "dailyPlannerStatusUrl": "/api/os/top-bar/daily-planner-status",
        "dailyPlannerWindowUrl": PLANNER_WINDOW_PATH,
        "dailyPlannerTimerScope": planner_timer_scope,
        "dailyPlannerEnabled": planner_enabled,
        "ordersEnabled": "Orders" in allowed_routes,
        "authToken": token,
        "revision": revision,
    }


@lru_cache(maxsize=1)
def _component_source():
    return COMPONENT_PATH.read_text(encoding="utf-8")


def component_html(config):
    source = _component_source()
    return source.replace(
        "__SPORTS_CAVE_TOP_BAR_CONFIG__",
        json.dumps(config, ensure_ascii=True).replace("</", "<\\/"),
    )


def render_top_bar(components, user, *, logo_src, current_route, navigation_epoch=0):
    config = top_bar_config(
        user,
        logo_src=logo_src,
        current_route=current_route,
        navigation_epoch=navigation_epoch,
    )
    components.html(component_html(config), height=0, width=0)
