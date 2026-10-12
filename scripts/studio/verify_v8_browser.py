"""Practical V8 lifecycle acceptance on disposable real Git worktrees."""
import argparse
import json
import threading
import time
from http.server import HTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
import draft_ui
import studio
from test_application_drafts import ApplicationDraftTests
from verify_phase4a_browser import Panel


def main(report):
    fixture = ApplicationDraftTests()
    fixture.setUp()
    server = draft_ui.DraftServer(fixture.home, fixture.task["id"], "owner")
    panel = HTTPServer(("127.0.0.1", 0), Panel)
    threads = [threading.Thread(target=server.run, daemon=True),
               threading.Thread(target=panel.serve_forever, daemon=True)]
    for thread in threads:
        thread.start()
    result = {"scope": "Disposable application worktrees and local headless Edge; real API and editor, synthetic provider receipt"}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="msedge", headless=True)
            context = browser.new_context(viewport={"width":1440, "height":900})
            context.route("**/*", lambda r: r.continue_() if r.request.url.startswith(("http://127.0.0.1:", "data:", "blob:")) else r.abort())
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("dialog", lambda d: d.accept(dialog_answer[0]) if d.type == "prompt" else d.accept())
            dialog_answer = [""]
            page.goto("http://127.0.0.1:" + str(panel.server_port))
            expect(page.locator(".ws-left")).to_be_visible()
            expect(page.locator(".ws-right")).to_be_visible()
            page.locator("#connection-settings summary").click()
            page.locator("#origin").fill(server.origin)

            def connect():
                with page.expect_popup() as popup:
                    page.locator("#connect").click()
                local = popup.value
                local.locator("#session").fill(server.origin+"/#"+server.token)
                local.locator("#trust").uncheck()
                local.locator("#approve").click()
                expect(page.locator("#connection")).to_contain_text("connected")
                return local

            local = connect()
            page.get_by_role("button", name="Drafts", exact=True).click()
            expect(page.locator("#ws-list")).not_to_contain_text("V6 technical acceptance")
            page.get_by_role("button", name="Create New Draft", exact=False).click()
            expect(local.locator("#application-confirm")).to_be_visible()
            assert server.catalog()["rows"] == [], "Nothing created before local confirmation"
            local.locator("#application-run").click()
            expect(local.locator("#handoff")).to_be_visible()
            local.locator("#open").click()
            expect(page.locator("#ws-title")).to_have_text("Sports Cave OS copy")
            original = server.catalog()["rows"][0]
            page.get_by_role("button", name="Drafts", exact=True).click()
            dialog_answer[0] = "Summer copy"
            page.get_by_role("button", name="Rename Draft", exact=True).click()
            local.locator("#application-run").click()
            expect(page.locator("#ws-title")).to_have_text("Summer copy")
            renamed = server.catalog()["rows"][0]
            assert renamed["id"] == original["id"] and renamed["branch"] == original["branch"]

            page.get_by_role("button", name="Files", exact=True).click()
            page.locator("#ws-list").get_by_role("button", name="app.py", exact=False).click()
            page.locator("#ed-text").fill("V8 saved copy")
            page.locator("#ws-save").click()
            expect(page.locator("#ed-status")).to_contain_text("Saved to the actual draft")
            page.get_by_role("button", name="Drafts", exact=True).click()
            dialog_answer[0] = ""
            page.get_by_role("button", name="Duplicate Draft", exact=True).click()
            local.locator("#application-run").click()
            expect(local.locator("#handoff")).to_be_visible()
            local.locator("#open").click()
            expect(page.locator("#ws-title")).to_have_text("Sports Cave OS copy 2")
            copied = next(r for r in server.catalog()["rows"] if r["id"] != original["id"])
            page.get_by_role("button", name="Files", exact=True).click()
            page.locator("#ws-list").get_by_role("button", name="app.py", exact=False).click()
            expect(page.locator("#ed-text")).to_have_value("V8 saved copy")
            assert copied["branch"] != original["branch"]

            # Closing/reopening the OS tab retains the buffer, but still requires permission.
            page.locator("#ed-text").fill("Unsaved after reopening")
            page.close()
            page = context.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("dialog", lambda d: d.accept(dialog_answer[0]) if d.type == "prompt" else d.accept())
            page.goto("http://127.0.0.1:" + str(panel.server_port))
            expect(page.locator("#ws-selector")).to_be_visible()
            local.close()
            local = connect()
            expect(local.locator("#handoff")).to_be_visible()
            local.locator("#open").click()
            expect(page.locator("#ws-title")).to_have_text("Sports Cave OS copy 2")
            expect(page.locator("#ed-text")).to_have_value("Unsaved after reopening")
            page.locator("#ws-save").click()
            expect(page.locator("#ed-status")).to_contain_text("Saved to the actual draft")
            page.locator("#ws-tests").click()
            expect(page.locator("#ws-status")).to_contain_text("Focused source checks passed")
            page.get_by_role("button", name="Drafts", exact=True).click()
            page.get_by_role("button", name="Archive / Delete Draft", exact=True).click()
            expect(local.locator("#application-detail")).to_contain_text("has_unfinished_changes")
            local.locator("#application-confirmation").fill("ARCHIVE Sports Cave OS copy 2")
            local.locator("#application-run").click()
            expect(page.locator("#ws-selector")).to_be_visible()
            assert [r["id"] for r in server.catalog()["rows"]] == [original["id"]]
            records = server.catalog(True)["rows"]
            assert {r["id"] for r in records} == {fixture.legacy["id"], copied["id"]}
            registry = studio.read(fixture.home/".studio/registry.json")
            archived = next(d for d in registry["drafts"] if d["id"] == copied["id"])
            assert Path(archived["worktree_path"]).is_dir()
            assert "Unsaved after reopening" in (Path(archived["worktree_path"])/"app.py").read_text(encoding="utf-8")
            result.update(first_setup_local_confirmation=True, application_only_catalog=True,
                          rename_preserves_identity=True, duplicate_copies_real_source=True,
                          reopen_restores_draft_and_unsaved_buffer=True, focused_tests=True,
                          archive_retains_unfinished_source=True, historical_records_retained=True,
                          browser_errors=errors)
            assert not errors, errors
            page.screenshot(path=str(report.with_suffix(".png")))
            browser.close()
    finally:
        server.stopping = True
        threads[0].join(10)
        panel.shutdown()
        panel.server_close()
        fixture.doCleanups()
    studio.atomic(report, result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    main(parser.parse_args().report)
