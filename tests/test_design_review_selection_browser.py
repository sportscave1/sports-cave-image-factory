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
<div data-testid="stColumn"><div data-testid="stCheckbox"><input type="checkbox"></div></div>
<div data-testid="stColumn"><h3 class="sc-review-title" title="Forever Panda – Pablo Sandoval Wall Art">Forever Panda – Pablo Sandoval Wall Art</h3><div class="sc-review-status">Needs attention</div></div>
<div data-testid="stColumn"><a class="sc-review-edit" href="#" aria-label="Edit design"><svg width="18" height="18" viewBox="0 0 24 24"><path d="M4 20 20 4" stroke="currentColor"/></svg></a></div>
<div data-testid="stColumn"><button>Publish now</button></div>
<div data-testid="stColumn"><button>Publish + ad</button></div>
</div></div></div>"""
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        try:
            for width in (950, 660, 390):
                page = browser.new_page(viewport={'width':width, 'height':600})
                page.set_content(css+'<style>body{margin:8px;font-family:Arial}*{box-sizing:border-box}button{font-size:14px;border:1px solid #ccc;border-radius:6px}</style>'+markup)
                controls = [page.get_by_role('link',name='Edit design'), page.get_by_role('button',name='Publish now'), page.get_by_role('button',name='Publish + ad')]
                boxes = [control.bounding_box() for control in controls]
                centers = [box['y']+box['height']/2 for box in boxes]
                assert max(centers)-min(centers) < 2
                assert boxes[0]['x'] < boxes[1]['x'] < boxes[2]['x']
                assert boxes[2]['x']+boxes[2]['width'] <= width
                assert page.locator('h3').evaluate('(el)=>getComputedStyle(el).textOverflow') == 'ellipsis'
                page.close()
        finally:
            browser.close()
