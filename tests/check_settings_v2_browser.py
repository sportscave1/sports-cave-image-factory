"""Run against the isolated settings_v2_preview fixture, never a production URL."""
import json
from pathlib import Path
import sys
from playwright.sync_api import sync_playwright, expect

port = int(sys.argv[1]) if len(sys.argv) > 1 else 8796
output = Path(__file__).resolve().parents[1] / "tmp/settings-v2-evidence"
output.mkdir(parents=True, exist_ok=True)
results = []
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel="msedge")
    page = browser.new_page(viewport={"width": 1440, "height": 960})
    page.goto(f"http://127.0.0.1:{port}")
    expect(page.get_by_role("heading", name="General", exact=True)).to_be_visible()
    expect(page.locator("[data-testid=stException]")).to_have_count(0)
    footer = page.locator(".st-key-sidebar-profile-footer")
    assert footer.bounding_box()["y"] > 750
    assert footer.locator(".st-key-sidebar-row-accounts_access").bounding_box()["y"] < footer.locator("[data-testid=stPopoverButton]").bounding_box()["y"]
    page.screenshot(path=str(output / "desktop.png"))

    trigger = footer.locator("[data-testid=stPopoverButton]")
    assert trigger.locator("p").evaluate("e=>getComputedStyle(e).webkitTextFillColor") == "rgb(238, 238, 235)"
    trigger.click()
    body = page.locator("[data-testid=stPopoverBody]")
    expect(body).to_be_visible()
    page.wait_for_timeout(250)  # Native opening animation.
    assert body.bounding_box()["y"] + body.bounding_box()["height"] < trigger.bounding_box()["y"]
    expect(body.locator("button")).to_have_count(1)
    expect(body.locator("button")).to_contain_text("Log out")
    page.screenshot(path=str(output / "account-menu.png"))
    page.keyboard.press("Escape")
    expect(body).to_have_count(0)
    trigger.click()
    expect(body).to_be_visible()
    page.get_by_role("heading", name="Settings", exact=True).click()
    expect(body).to_have_count(0)
    results.append("Footer ordering, upward anchoring, Escape and outside dismissal")

    page.get_by_role("button", name="Users & Access").click()
    expect(page.get_by_text("2 accounts", exact=False)).to_be_visible()
    expect(page.locator("input")).to_have_count(1)  # Top-bar search only.
    page.screenshot(path=str(output / "users.png"))
    page.get_by_role("button", name="Local Worker", exact=True).click()
    page.get_by_text("Page Access", exact=True).click()
    expect(page.get_by_text("View activity log", exact=True)).to_be_visible()
    content = page.locator(".st-key-settings-content")
    nav = page.locator(".st-key-settings-navigation")
    nav_y = nav.bounding_box()["y"]
    content.evaluate("e=>e.scrollTop=e.scrollHeight")
    assert content.evaluate("e=>e.scrollTop") > 0
    assert nav.bounding_box()["y"] == nav_y
    page.screenshot(path=str(output / "permissions.png"))
    results.append("On-demand user editor; permissions scroll independently of navigation")

    for section in ("Reporting", "Credentials", "Security & Account", "General"):
        page.get_by_role("button", name=section, exact=False).first.click()
        expect(page.get_by_role("heading", name=section, exact=True)).to_be_visible()
        expect(page.locator("[data-testid=stException]")).to_have_count(0)
    results.append("All five Settings sections render")

    for width in (900, 390):
        page.set_viewport_size({"width": width, "height": 844})
        page.wait_for_timeout(250)
        assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
        assert content.bounding_box()["height"] < 600
        assert nav.bounding_box()["y"] + nav.bounding_box()["height"] <= content.bounding_box()["y"]
        page.screenshot(path=str(output / f"general-{width}.png"))
    page.locator("#sc-os-mobile-menu").click()
    expect(page.locator("body")).to_have_class("sc-mobile-nav-open")
    expect(trigger).to_be_visible()
    page.locator("#sc-os-mobile-menu").click()
    results.append("900px and 390px layout, independent scroll and mobile main navigation")

    page.goto(f"http://127.0.0.1:{port}/?role=worker")
    expect(page.get_by_role("heading", name="General", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Users & Access")).to_have_count(0)
    expect(page.get_by_role("button", name="Credentials", exact=True)).to_have_count(0)
    results.append("Worker navigation excludes administrator sections")
    browser.close()
(output / "checks.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
print(json.dumps(results, indent=2))
