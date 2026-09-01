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
PLANNER_DATA_REFRESH_BRIDGE_KEY = "planner-data-refresh-bridge"
PLANNER_DATA_REFRESH_ROUTES = frozenset({"dashboard", "reporting", "weekly review"})
REPAIR_TOOLBAR_SECTION = "Toolbar / Navigation"
REPAIR_OTHER_SECTION = "Other"


def allowed_routes_for_user(user):
    return tuple(
        page["route"]
        for page in os_accounts.PAGE_REGISTRY
        if os_accounts.can_access_page(user, page["route"])
    )


def daily_planner_timer_scope(user):
    return hashlib.sha256(
        f"sports-cave-planner|{str((user or {}).get('id') or '').strip()}".encode("utf-8")
    ).hexdigest()[:24]


def _repair_section_label(page):
    page = dict(page or {})
    key = str(page.get("key") or "")
    parent_key = str(page.get("parent_key") or "")
    if key == "ads":
        return "Ads — New Ads"
    if parent_key == "ads":
        return f"Ads — {str(page.get('label') or page.get('route') or '').strip()}"
    if page.get("navigation_child") and parent_key:
        parent = os_accounts.PAGE_BY_KEY.get(parent_key) or {}
        return str(parent.get("label") or parent.get("route") or "").strip()
    return str(page.get("label") or page.get("route") or "").strip()


def repair_sections_for_user(user):
    """Derive the compact report taxonomy from the user's current navigation."""

    allowed_routes = set(allowed_routes_for_user(user))
    sections = []
    for page in os_accounts.PAGE_REGISTRY:
        if page.get("route") not in allowed_routes:
            continue
        label = _repair_section_label(page)
        if label and label not in sections:
            sections.append(label)
    for label in (REPAIR_TOOLBAR_SECTION, REPAIR_OTHER_SECTION):
        if label not in sections:
            sections.append(label)
    return tuple(sections)


def repair_section_for_route(route):
    page = os_accounts.PAGE_BY_ROUTE.get(os_accounts.normalise_route(route)) or {}
    return _repair_section_label(page) or REPAIR_OTHER_SECTION


def top_bar_config(user, *, logo_src, current_route, navigation_epoch=0):
    allowed_routes = allowed_routes_for_user(user)
    navigation_route_keys = {
        str(page["label"]): str(page["key"])
        for page in os_accounts.PAGE_REGISTRY
        if page["route"] in allowed_routes
        and page["route"] != os_accounts.DAILY_PLANNER_ROUTE
    }
    navigation_route_labels = {
        str(page["key"]): str(page["label"])
        for page in os_accounts.PAGE_REGISTRY
        if page["route"] in allowed_routes
    }
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
    planner_timer_scope = daily_planner_timer_scope(user)
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
        "navigationRouteLabels": navigation_route_labels,
        "accountsRouteKey": "accounts_access",
        "searchUrl": "/api/os/top-bar/search-index",
        "notificationsUrl": "/api/os/top-bar/notifications",
        "repairRequestsUrl": "/api/os/top-bar/repair-requests",
        "repairSections": repair_sections_for_user(user),
        "repairCurrentSection": repair_section_for_route(current_route),
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


def render_planner_data_refresh_bridge(st_module, *, current_route):
    """Mount one hidden native widget that requests a normal Streamlit rerun."""

    if str(current_route or "").strip().casefold() not in PLANNER_DATA_REFRESH_ROUTES:
        return False
    st_module.button(
        "Refresh planner data",
        key=PLANNER_DATA_REFRESH_BRIDGE_KEY,
    )
    return True


def navigation_complete_html(*, current_route, navigation_epoch=0, status="ready"):
    payload = {
        "routeKey": os_accounts.page_key_for_route(current_route) or "",
        "epoch": int(navigation_epoch or 0),
        "status": str(status or "ready"),
    }
    return (
        "<script>(function(){const p="
        + json.dumps(payload, ensure_ascii=True).replace("</", "<\\/")
        + ";window.parent.SportsCaveTopBar?.completeNavigation?.(p);})();</script>"
    )


def render_navigation_complete(
    components,
    *,
    current_route,
    navigation_epoch=0,
    status="ready",
):
    components.html(
        navigation_complete_html(
            current_route=current_route,
            navigation_epoch=navigation_epoch,
            status=status,
        ),
        height=0,
        width=0,
    )
