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
