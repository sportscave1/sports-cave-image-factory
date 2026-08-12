"""Sports Cave OS top-bar component bridge."""

from __future__ import annotations

import json
from pathlib import Path
import time

import os_accounts
import top_bar_security


COMPONENT_PATH = (
    Path(__file__).resolve().parent / "components" / "sports_cave_top_bar" / "index.html"
)


def allowed_routes_for_user(user):
    return tuple(
        page["route"]
        for page in os_accounts.PAGE_REGISTRY
        if os_accounts.can_access_page(user, page["route"])
    )


def top_bar_config(user, *, logo_src, current_route):
    allowed_routes = allowed_routes_for_user(user)
    token = top_bar_security.create_top_bar_token(
        user,
        allowed_routes=allowed_routes,
        can_view_activity=os_accounts.can_view_activity_log(user),
        can_view_all_activity=os_accounts.is_reporting_owner(user),
    )
    return {
        "appName": "Sports Cave OS",
        "appSubtitle": "Operations System",
        "logoSrc": str(logo_src or ""),
        "currentRoute": str(current_route or ""),
        "accountsRouteKey": "accounts_access",
        "searchUrl": "/api/os/top-bar/search-index",
        "notificationsUrl": "/api/os/top-bar/notifications",
        "orderStatusUrl": "/api/os/top-bar/order-status",
        "ordersEnabled": "Orders" in allowed_routes,
        "authToken": token,
        "revision": str(time.time_ns()),
    }


def component_html(config):
    source = COMPONENT_PATH.read_text(encoding="utf-8")
    return source.replace(
        "__SPORTS_CAVE_TOP_BAR_CONFIG__",
        json.dumps(config, ensure_ascii=True).replace("</", "<\\/"),
    )


def render_top_bar(components, user, *, logo_src, current_route):
    config = top_bar_config(user, logo_src=logo_src, current_route=current_route)
    components.html(component_html(config), height=0, width=0)
