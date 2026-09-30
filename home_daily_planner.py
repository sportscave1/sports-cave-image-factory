"""Compact Daily Planner execution panel for the Sports Cave OS Home page."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import os_accounts
import top_bar
from daily_planner import (
    PLANNER_BOOTSTRAP_PATH,
    PLANNER_MUTATION_PATH,
    PLANNER_STATUS_PATH,
    PLANNER_WINDOW_PATH,
)


COMPONENT_PATH = (
    Path(__file__).resolve().parent / "components" / "home_daily_planner" / "index.html"
)
ROOT_ID = "sports-cave-home-daily-planner-root"


def compact_planner_config(user):
    top_bar_config = top_bar.top_bar_config(
        user,
        logo_src="",
        current_route="Dashboard",
    )
    return {
        "enabled": bool(top_bar_config.get("dailyPlannerEnabled")),
        "authToken": top_bar_config.get("authToken") or "",
        "timerScope": top_bar_config.get("dailyPlannerTimerScope") or "",
        "bootstrapUrl": PLANNER_BOOTSTRAP_PATH,
        "mutationUrl": PLANNER_MUTATION_PATH,
        "statusUrl": PLANNER_STATUS_PATH,
        "plannerWindowUrl": PLANNER_WINDOW_PATH,
    }


@lru_cache(maxsize=1)
def _component_source():
    return COMPONENT_PATH.read_text(encoding="utf-8")


def component_html(config):
    return _component_source().replace(
        "__SPORTS_CAVE_HOME_PLANNER_CONFIG__",
        json.dumps(config, ensure_ascii=True).replace("</", "<\\/"),
    )


def render_panel(st_module, components, user):
    if not os_accounts.is_admin(user):
        return False
    st_module.markdown(
        f'<div id="{ROOT_ID}" class="sc-home-daily-planner-host"></div>',
        unsafe_allow_html=True,
    )
    components.html(component_html(compact_planner_config(user)), height=0, width=0)
    return True


def render_status(st_module, user, local_now):
    """Render only local markup; the shell supplies its existing timer mirror."""
    from html import escape

    hour = local_now.hour
    greeting = "Good morning" if 5 <= hour < 12 else "Good afternoon" if 12 <= hour < 17 else "Good night"
    name = str((user or {}).get("display_name") or "").strip()
    markup = f'<div id="sc-home-greeting" class="sc-home-greeting">{escape(greeting + ", " + name) if name else ""}</div>'
    if os_accounts.is_admin(user):
        markup += ('<button id="sc-home-active-planner" class="sc-home-active-planner" type="button" hidden>'
                   '<span class="sc-home-active-task"></span><span class="sc-home-active-time"></span>'
                   '<span>Open Planner</span></button>')
    st_module.markdown(markup, unsafe_allow_html=True)
