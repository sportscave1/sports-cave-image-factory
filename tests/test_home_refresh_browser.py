"""Run against the isolated home_refresh_fixture on port 18893."""
from playwright.sync_api import sync_playwright, expect


def test_repeated_home_refresh_replaces_panels():
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True)
        try:
            page=browser.new_page()
            page.goto('http://localhost:18893')
            expect(page.locator('.sc-brief-recommendations')).to_have_count(1)
            for width in (1600,390):
                page.set_viewport_size(dict(width=width,height=1000))
                for _ in range(5):
                    page.wait_for_timeout(700)
                    expect(page.locator('.sc-brief-recommendations')).to_have_count(1)
                    expect(page.locator('.sc-meta-brief')).to_have_count(1)
                    expect(page.locator('[data-testid="stException"]')).to_have_count(0)
                page.get_by_role('button',name='Full rerun',exact=True).click()
            expect(page.locator('.sc-legends')).to_have_count(1)
        finally:
            browser.close()
