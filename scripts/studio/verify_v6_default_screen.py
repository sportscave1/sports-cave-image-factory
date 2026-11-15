"""Opt-in local V6 entry-to-edit acceptance using an assigned draft and isolated Docker.

Only this task's tested app.py edit is restored, through V6 Undo with a hash check.
No personal browser profile, production credentials or existing companion is used.
"""
import argparse
import base64
import json
import threading
import time
from http.server import HTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright, expect
import draft_ui
import editor
import studio
from verify_phase4a_browser import Panel
from verify_preview_runtime import request


def main(home, task, owner, report):
    server = draft_ui.DraftServer(home, task, owner, idle_seconds=300)
    state = server.state()
    root = Path(state['task']['worktree_path'])
    before = (root/'app.py').read_bytes()
    panel = HTTPServer(('127.0.0.1', 0), Panel)
    threads = [threading.Thread(target=server.run, daemon=True),
               threading.Thread(target=panel.serve_forever, daemon=True)]
    for thread in threads:
        thread.start()
    change = None
    result = {'scope': 'Local embedded UI and actual synthetic Docker OS; no production changes', 'task': task}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='msedge', headless=True)
            context = browser.new_context(viewport={'width':1440, 'height':900})
            context.route('**/*', lambda r: r.continue_() if r.request.url.startswith(('http://127.0.0.1:', 'data:', 'blob:')) else r.abort())
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            started = time.monotonic()
            page.goto('http://127.0.0.1:'+str(panel.server_port))
            expect(page.locator('#ws-selector')).to_be_visible()
            expect(page.locator('.ws-left')).to_be_visible()
            expect(page.locator('.ws-right')).to_be_visible()
            result['default_workspace_seconds'] = round(time.monotonic()-started, 3)
            page.screenshot(path=str(report.with_name(report.stem+'-default.png')))
            page.locator('#connection-settings summary').click()
            page.locator('#origin').fill(server.origin)
            with page.expect_popup() as popup:
                page.locator('#connect').click()
            local = popup.value
            local.locator('#session').fill(server.origin+'/#'+server.token)
            local.locator('#trust').uncheck()
            local.locator('#approve').click()
            page.locator('#ws-draft-select').select_option(state['draft']['id'])
            page.locator('#ws-open-draft').click()
            expect(page.locator('#ws-selector')).to_be_visible()
            local.locator('#open').click()
            expect(page.locator('#ws-title')).to_have_text(state['draft']['name'])
            assert len(context.pages) == 2, 'A separate local editor must not open'
            page.get_by_role('button', name='Files', exact=True).click()
            page.locator('#ws-list').get_by_role('button', name='app.py', exact=False).click()
            expect(page.locator('#ed-text')).to_be_visible()
            started = time.monotonic()
            page.locator('#ws-start').click()
            expect(page.locator('#ws-image')).to_be_visible(timeout=120000)
            expect(page.locator('#ws-status')).to_contain_text('Preview running', timeout=120000)
            result['cold_preview_seconds'] = round(time.monotonic()-started, 3)
            page.locator('#ed-text').fill('V6 default workspace verification')
            started = time.monotonic()
            page.locator('#ws-save').click()
            expect(page.locator('#ed-status')).to_contain_text('Saved to the actual draft', timeout=60000)
            current = request(server, 'editor-open', path='app.py')
            change = current['history'][-1]
            assert change['after'] == current['hash']
            frame = request(server, 'preview-event', event={'action':'frame'})
            assert 'V6 default workspace verification' in frame['text']
            result['save_and_preview_seconds'] = round(time.monotonic()-started, 3)
            page.screenshot(path=str(report.with_name(report.stem+'-edited.png')))
            page.locator('#ws-undo').click()
            expect(page.locator('#ed-status')).to_contain_text('Saved to the actual draft', timeout=60000)
            # Wait for the original hash, not the status message left by the preceding save.
            expect(page.locator('#ed-text')).not_to_have_value('V6 default workspace verification', timeout=60000)
            assert (root/'app.py').read_bytes() == before
            change = None
            page.get_by_role('button', name='Pages', exact=True).click()
            page.locator('#ws-list').get_by_role('button', name='Developer Studio', exact=False).click()
            expect(page.locator('#ws-status')).to_contain_text('Actual selected OS page', timeout=60000)
            frame = request(server, 'preview-event', event={'action':'frame'})
            for text in ['Developer Studio', 'Pages', 'Drafts', 'Files', 'Properties', 'Styles', 'Source', 'Open Editor']:
                assert text in frame['text'], (text, frame['text'])
            assert 'Development drafts' not in frame['text']
            report.with_name(report.stem+'-os-route.jpg').write_bytes(base64.b64decode(frame['image']))
            page.get_by_role('button', name='Styles', exact=True).click()
            expect(page.locator('#editor-panel')).to_be_hidden()
            page.locator('#ws-inspect').click()
            page.locator('#ws-image').click(position={'x':3, 'y':3})
            expect(page.locator('#ws-inspection')).to_contain_text('read-only')
            page.get_by_role('button', name='Properties', exact=True).click()
            expect(page.locator('#editor-panel')).to_be_hidden()
            page.screenshot(path=str(report.with_name(report.stem+'-pages.png')))
            page.locator('#ws-stop').click()
            expect(page.locator('#ws-status')).to_contain_text('Preview stopped', timeout=30000)
            assert server.preview_runtime.name is None
            result.update(default_three_panels=True, confirmed_embedded_editor=True, visual_save_preview_undo=True,
                          os_developer_studio_route=True, actual_page_selection=True, unsupported_read_only=True,
                          source_restored=True, preview_stopped=True, browser_errors=errors,
                          isolation=server.preview_runtime.evidence)
            assert not errors, errors
            browser.close()
    finally:
        if change:
            current = request(server, 'editor-open', path='app.py')
            if current['hash'] != change['after']:
                raise RuntimeError('Source changed concurrently; refusing to overwrite it during cleanup')
            request(server, 'editor-save', path='app.py', expected_hash=current['hash'],
                    expected_revision=current['revision'], restore={'id':change['id'], 'side':'before'})
        server.stopping = True
        threads[0].join(15)
        panel.shutdown()
        panel.server_close()
    studio.atomic(report, result)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--home', type=Path, required=True)
    parser.add_argument('--task', required=True)
    parser.add_argument('--owner', required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    main(args.home, args.task, args.owner, args.report)
