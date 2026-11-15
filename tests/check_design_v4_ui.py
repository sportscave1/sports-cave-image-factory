"""Browser/SQL acceptance checks against local fixture servers on 8914/8915 only."""
import json
import re
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright, expect
from tests import design_v4_fixture as fixture

OUT = Path("tmp/design-v4-browser")
OUT.mkdir(exist_ok=True)
results = {}


def snapshot(ids):
    with fixture.connect() as conn:
        return {str(row["id"]): row for row in conn.execute(
            "SELECT * FROM dashboard_tasks WHERE id=ANY(%s::uuid[])", (ids,)).fetchall()}


def action(page, suffix):
    return page.locator(".st-key-design-schedule-actions").get_by_test_id("stButton").get_by_role("button").filter(has_text=suffix)


def count(page, total, selected):
    expect(page.locator(".st-key-design-schedule-actions").get_by_test_id("stCaptionContainer")).to_have_text(re.compile(rf"^{total} designs .* {selected} selected$"))


def marker(page, row=None):
    # Glide draws its checkbox column on a canvas; hit the actual measured grid.
    page.wait_for_timeout(250)  # Allow the native canvas to finish its rerun paint.
    box = page.get_by_test_id("stDataFrame").bounding_box()
    page.mouse.click(box["x"] + 18, box["y"] + (18 if row is None else 53 + 32 * row))


def search(page, value):
    field = page.get_by_role("textbox", name="Search designs", exact=True)
    field.fill(value)
    field.press("Enter")


with sync_playwright() as pw:
    for channel in ("msedge", "chrome"):
        prefix = "V4 acceptance " + uuid4().hex[:8]
        ids = [fixture.seed(f"{prefix} {i:02d}", sport="Motorsport" if i % 2 else "NBA") for i in range(1, 41)]
        unrelated = fixture.seed(prefix + " upload", section=fixture.dashboard.UPLOAD_TASK_GROUP)
        completed = fixture.seed(prefix + " completed", status="complete")
        protected = snapshot([unrelated, completed])
        browser = pw.chromium.launch(channel=channel, headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        context.route("**/*", lambda r: r.continue_() if r.request.url.startswith(("http://127.0.0.1", "ws://127.0.0.1", "data:")) else r.abort())
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto("http://127.0.0.1:8914")
        page.locator(".st-key-design-schedule-actions").wait_for()
        search(page, prefix)
        count(page, 40, 0)
        marker(page)
        count(page, 40, 40)  # More rows than the viewport: full filtered result selected.
        expect(action(page, "Open in Studio")).to_be_disabled()
        expect(action(page, "Complete")).to_be_disabled()
        expect(action(page, "Delete selected")).to_be_enabled()
        marker(page, 0)
        count(page, 40, 39)
        assert "linear-gradient" in page.get_by_test_id("stDataFrame").evaluate("e=>getComputedStyle(e,'::after').backgroundImage")
        page.screenshot(path=str(OUT / f"{channel}-partial-selection.png"))
        marker(page)
        count(page, 40, 40)
        marker(page)
        count(page, 40, 0)

        # Filter changes clear selection; revisiting a tab never restores a hidden selection.
        marker(page, 0)
        count(page, 40, 1)
        page.locator('[class*="st-key-design-schedule-sport"] [role="combobox"]').click()
        page.get_by_role("option", name="NBA", exact=True).click()
        count(page, 20, 0)
        marker(page)
        count(page, 20, 20)
        page.get_by_role("button", name="Collections", exact=True).click()
        expect(action(page, "Delete design")).to_be_disabled()
        page.get_by_role("button", name="Active Designs", exact=True).click()
        page.get_by_role("textbox", name="Search designs", exact=True).wait_for()
        search(page, prefix)
        count(page, 40, 0)

        # Bulk cancellation and commit, with persisted SQL assertions.
        search(page, prefix + " 0")
        count(page, 9, 0)
        marker(page)
        count(page, 9, 9)
        before = snapshot(ids)
        action(page, "Delete selected").click()
        dialog = page.get_by_role("dialog")
        expect(dialog).to_contain_text("Delete 9 designs?")
        expect(dialog).to_contain_text("Artwork files, media and completed orders are preserved")
        dialog.get_by_role("button", name="Cancel", exact=True).click()
        expect(dialog).not_to_be_visible()
        assert snapshot(ids) == before
        count(page, 9, 9)
        action(page, "Delete selected").click()
        page.get_by_role("dialog").get_by_role("button", name="Confirm Delete", exact=True).click()
        expect(page.get_by_role("dialog")).not_to_be_visible()
        count(page, 0, 0)
        after = snapshot(ids)
        assert all(after[i]["status"] == ("deleted" if n < 9 else "open") for n, i in enumerate(ids))
        page.reload()
        page.locator(".st-key-design-schedule-actions").wait_for()
        search(page, prefix)
        count(page, 31, 0)

        # Single-delete still uses the existing named-design confirmation.
        search(page, prefix + " 40")
        count(page, 1, 0)
        marker(page, 0)
        count(page, 1, 1)
        expect(action(page, "Open in Studio")).to_be_enabled()
        action(page, "View/Edit Details").click()
        expect(page.get_by_role("dialog")).to_contain_text("View/Edit Details")
        page.get_by_role("dialog").get_by_test_id("stButton").get_by_role("button", name="Close", exact=True).click()
        action(page, "Complete").click()
        expect(page.get_by_role("dialog")).to_contain_text("Mockups needed?")
        page.get_by_role("dialog").get_by_role("button", name="Cancel", exact=True).click()
        assert snapshot([ids[-1]])[ids[-1]]["status"] == "open"
        action(page, "Open in Studio").click()
        expect(page.locator("#design-studio-workflow")).to_be_attached()
        action(page, "Delete design").click()
        expect(page.get_by_role("dialog")).to_contain_text(prefix + " 40")
        page.get_by_role("dialog").get_by_role("button", name="Delete design", exact=True).click()
        expect(page.get_by_role("dialog")).not_to_be_visible()
        count(page, 0, 0)
        expect(page.locator("#design-studio-workflow")).not_to_be_attached()
        assert snapshot([ids[-1]])[ids[-1]]["status"] == "deleted"
        assert snapshot([unrelated, completed]) == protected

        # Force an audit error inside the SQL transaction: no false success or data loss.
        page.goto("http://127.0.0.1:8914/?delete_failure=1")
        page.locator(".st-key-design-schedule-actions").wait_for()
        search(page, prefix + " 1")
        count(page, 10, 0)
        marker(page)
        count(page, 10, 10)
        failure_before = snapshot(ids)
        action(page, "Delete selected").click()
        page.get_by_role("dialog").get_by_role("button", name="Confirm Delete", exact=True).click()
        expect(page.get_by_role("dialog")).to_contain_text("Deletion could not be confirmed")
        assert snapshot(ids) == failure_before
        page.get_by_role("dialog").get_by_role("button", name="Cancel", exact=True).click()

        page.goto("http://127.0.0.1:8914")
        page.locator(".st-key-design-schedule-actions").wait_for()
        search(page, prefix)
        count(page, 30, 0)
        for label, expected in (("Import CSV", "Import Tasks CSV"), ("Export CSV", "Export Tasks CSV"), ("Add Task", "Add Task")):
            page.get_by_role("button", name=label, exact=True).click()
            expect(page.get_by_role("dialog")).to_contain_text(expected)
            if label == "Export CSV":
                with page.expect_download() as exported:
                    page.get_by_role("dialog").get_by_role("button", name="Download CSV", exact=True).click()
                assert exported.value.suggested_filename.endswith(".csv")
            page.get_by_role("dialog").get_by_test_id("stButton").get_by_role("button", name="Close" if label == "Export CSV" else "Cancel", exact=True).click()
            count(page, 30, 0)
        with page.expect_download() as download:
            page.get_by_role("button", name="CSV Template", exact=True).click()
        assert download.value.suggested_filename.endswith(".csv")
        page.get_by_role("button", name="Generate Ideas", exact=True).click()
        expect(page.get_by_text("Design style mix", exact=True)).to_be_visible()
        page.get_by_role("button", name="Generate Ideas", exact=True).click()
        expect(page.get_by_text("Design style mix", exact=True)).not_to_be_visible()
        count(page, 30, 0)

        layout = {}
        for width in (1440, 900, 390):
            page.set_viewport_size({"width": width, "height": 1000})
            page.wait_for_timeout(300)
            count(page, 30, 0)
            page.screenshot(path=str(OUT / f"{channel}-{width}.png"), full_page=True)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2")
            layout[width] = {"grid": page.get_by_test_id("stDataFrame").bounding_box(),
                             "commands": page.locator(".st-key-design-schedule-actions").bounding_box()}
            controls = page.locator(".st-key-design-schedule-header button").all()
            assert all(item.bounding_box()["width"] >= 80 for item in controls)
            command_labels = page.locator(".st-key-design-schedule-actions [data-testid='stButton'] button p")
            assert command_labels.evaluate_all("els=>els.every(e=>e.scrollWidth <= e.clientWidth + 1)")
            if width == 390:
                page.locator(".st-key-design-schedule-actions").scroll_into_view_if_needed()
                page.screenshot(path=str(OUT / f"{channel}-390-commands.png"))
        assert not errors, errors
        results[channel] = {"checks": "passed", "console_errors": errors, "layout": layout}
        browser.close()

(OUT / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
print(json.dumps(results, indent=2))
