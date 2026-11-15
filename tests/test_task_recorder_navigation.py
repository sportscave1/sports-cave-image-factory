"""Actual sidebar rendering with the existing synthetic owner fixture."""
from pathlib import Path
from streamlit.testing.v1 import AppTest

import os_accounts

ROOT = Path(__file__).resolve().parents[1]


def test_task_recorder_shares_developer_with_existing_controls():
    page = AppTest.from_file(str(ROOT / "tests/worker_health_nav_fixture.py"), default_timeout=15).run()
    assert not page.exception
    page.button(key="sidebar-disclosure::developer").click().run()
    assert not page.exception
    assert page.session_state["route"] == "Worker Health"
    assert page.button(key="sidebar-child::Task Recorder")
    assert page.button(key="sidebar-child::Image Protection")
    assert any("Developer%20Studio" in link.proto.url for link in page.get("link_button"))
    page.button(key="sidebar-child::Task Recorder").click().run()
    assert not page.exception
    assert page.session_state["route"] == "Task Recorder"
    assert page.button(key="sidebar-child::Task Recorder").proto.type == "primary"
    page.run()
    assert page.session_state["route"] == "Task Recorder"
    assert page.button(key="sidebar-child::Image Protection")


def test_task_recorder_direct_route_and_permissions():
    page = AppTest.from_file(str(ROOT / "tests/worker_health_nav_fixture.py"), default_timeout=15)
    page.query_params["page"] = "Task Recorder"
    page.run()
    assert not page.exception
    assert page.button(key="sidebar-child::Task Recorder").proto.type == "primary"
    assert os_accounts.can_access_page({"role": "admin", "is_active": True}, "Task Recorder")
    assert not os_accounts.can_access_page(
        {"role": "worker", "is_active": True, "page_permissions": ["task_recorder"]},
        "Task Recorder",
    )
    assert not os_accounts.PAGE_BY_KEY["task_recorder"]["worker_assignable"]
