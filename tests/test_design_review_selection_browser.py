from pathlib import Path
from playwright.sync_api import sync_playwright


def test_selection_icons_and_refresh_remain_visible_on_desktop_and_mobile():
    css = (Path(__file__).resolve().parents[1] / 'components/design_review_gallery.css').read_text(encoding='utf8')
    markup = """
<div class="st-key-design-review-gallery">
<div class="st-key-design-review-header"><div data-testid="stHorizontalBlock">
<div data-testid="stColumn">Design Studio</div><div data-testid="stColumn">Synced just now</div>
<div data-testid="stColumn"><button>Refresh</button></div></div></div>
<div class="st-key-design-review-selection"><div data-testid="stVerticalBlock"><div data-testid="stHorizontalBlock">
<div data-testid="stColumn">2 selected</div>
<div data-testid="stColumn"><div class="st-key-design-review-enqueue"><button aria-label="Add selected to queue"><span data-testid="stIconMaterial">+</span></button></div></div>
<div data-testid="stColumn"><div class="st-key-design-review-trash"><button aria-label="Delete selected"><span data-testid="stIconMaterial">×</span></button></div></div>
</div></div></div></div>"""
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        try:
            for width in (1440, 390):
                page = browser.new_page(viewport={'width':width, 'height':700})
                page.set_content(css + '<style>body{font-family:Arial;margin:16px}button{font-size:14px}[data-testid="stIconMaterial"]{font-size:18px}</style>' + markup)
                assert page.get_by_role('button', name='Refresh').is_visible()
                queue = page.get_by_role('button', name='Add selected to queue')
                trash = page.get_by_role('button', name='Delete selected')
                assert queue.is_visible() and trash.is_visible()
                assert queue.locator('span').is_visible() and trash.locator('span').is_visible()
                assert queue.bounding_box()['x'] < trash.bounding_box()['x']
                assert trash.bounding_box()['x'] + trash.bounding_box()['width'] <= width
                page.close()
        finally:
            browser.close()


def test_card_pencil_and_publish_buttons_share_one_row():
    css = (Path(__file__).resolve().parents[1] / 'components/design_review_gallery.css').read_text(encoding='utf8')
    markup = """
<div class="st-key-design-review-grid"><div class="st-key-design-review-card-fixture"><div data-testid="stHorizontalBlock">
<div data-testid="stColumn"><div data-testid="stCheckbox"><input type="checkbox" checked></div></div>
<div data-testid="stColumn"><h3 class="sc-review-title" title="Forever Panda – Pablo Sandoval Wall Art">Forever Panda – Pablo Sandoval Wall Art</h3><div class="sc-review-status">Needs attention</div></div>
<div data-testid="stColumn"><a class="sc-review-edit" href="#" aria-label="Edit design"><svg width="18" height="18" viewBox="0 0 24 24"><path d="M4 20 20 4" stroke="currentColor"/></svg></a></div>
<div data-testid="stColumn"><div class="st-key-design-review-delete-fixture"><button>Delete</button></div></div>
<div data-testid="stColumn"><button>Publish now</button></div>
<div data-testid="stColumn"><button>Publish + ad</button></div>
</div></div></div>"""
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        try:
            for width in (950, 660, 390):
                page = browser.new_page(viewport={'width':width, 'height':600})
                page.set_content(css+'<style>body{margin:8px;font-family:Arial}*{box-sizing:border-box}button{font-size:14px;border:1px solid #ccc;border-radius:6px}</style>'+markup)
                controls = [page.get_by_role('link',name='Edit design'), page.get_by_role('button',name='Delete'), page.get_by_role('button',name='Publish now'), page.get_by_role('button',name='Publish + ad')]
                boxes = [control.bounding_box() for control in controls]
                centers = [box['y']+box['height']/2 for box in boxes]
                assert max(centers)-min(centers) < 2
                assert boxes[0]['x'] < boxes[1]['x'] < boxes[2]['x'] < boxes[3]['x']
                assert boxes[-1]['x']+boxes[-1]['width'] <= width
                page.get_by_role('checkbox').uncheck()
                assert not page.get_by_role('button', name='Delete').is_visible()
                assert page.locator('h3').evaluate('(el)=>getComputedStyle(el).textOverflow') == 'ellipsis'
                page.close()
        finally:
            browser.close()


def test_create_design_modal_submits_and_keeps_brief_on_retryable_error():
    import json
    root = Path(__file__).resolve().parents[1]
    script = (root / 'components/design_review_edit.html').read_text(encoding='utf-8')
    markup = '<div class="st-key-design-review-toolbar"><a href="#create-design" data-design-create="true" role="button">Create design</a></div>'
    calls, fail = [], [False]
    def respond(route):
        if route.request.method == 'POST':
            calls.append(route.request.post_data_json)
            route.fulfill(status=409 if fail[0] else 200, content_type='application/json',
                          body=json.dumps({'error': 'Queue unavailable. Retry.'} if fail[0] else {'queued': True}))
        else:
            route.fulfill(content_type='text/html', body=markup + script)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        try:
            page = browser.new_page(viewport={'width':390, 'height':700})
            page.route('https://studio.test/**', respond)
            page.goto('https://studio.test/')
            page.get_by_role('button', name='Create design', exact=True).click()
            dialog = page.get_by_role('dialog')
            assert dialog.is_visible()
            dialog.get_by_role('button', name='Create design').click()
            assert not calls
            dialog.get_by_role('textbox').fill('Anthony Edwards dunk and roar')
            dialog.get_by_role('button', name='Create design').click()
            page.wait_for_function('!document.querySelector("dialog")')
            assert len(calls) == 1 and calls[0]['brief'] == 'Anthony Edwards dunk and roar'
            assert len(calls[0]['request_id']) == 36
            assert 'Design queued. Companion will open' in page.locator('.sc-review-edit-feedback').inner_text()
            fail[0] = True
            page.get_by_role('button', name='Create design', exact=True).click()
            dialog.get_by_role('textbox').fill('Keep this brief for retry')
            dialog.get_by_role('button', name='Create design').click()
            page.wait_for_function('document.querySelector("dialog [role=alert]").textContent.length > 0')
            assert dialog.is_visible()
            assert dialog.get_by_role('alert').inner_text() == 'Queue unavailable. Retry.'
            assert dialog.get_by_role('textbox').input_value() == 'Keep this brief for retry'
        finally:
            browser.close()
