"""Real header controller and CSS, synthetic HTTP only; no app/server imports."""
import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright, expect


def test_three_cards_search_overlay_and_responsive_layout(tmp_path):
    source = (Path(__file__).resolve().parents[1] / 'components/sports_cave_top_bar/index.html').read_text(encoding='utf8')
    payload = dict(online=True, jobs=[dict(id='upload',title='Collector Tribute',stage=2,
        label='Generating mockups',percent=34,detail='',updated_at='fixture')], queues=dict(
        upload=dict(enabled=True,waiting=2,display=True),
        design=dict(enabled=True,waiting=1,jobs=[dict(id='design',title='A Moment in History',
            state='running',label='Generating · time-based estimate',percent=45,estimated=True)]),
        ads=dict(enabled=True,online=True,waiting=0,jobs=[dict(id='ad',title='Broadway Joe',
            state='running',label='Waiting for ad copy and three covers',percent=40)])))
    config = dict(appName='Sports Cave OS',appSubtitle='Operations System',filesEnabled=True,
        uploadScope='fixture-admin',staffUploadProgress=True,currentRouteKey='ads',revision='fixture',
        searchIndex=[dict(group='Pages',title='Ads',subtitle='New Ads',route_key='ads',aliases=[],keywords=[])],
        navigationRouteLabels={'ads':'Ads','edition_ops':'Edition Ops'},navigationRouteKeys={'Ads':'ads'},
        searchUrl='/api/search', authToken='fixture-only')
    html = source.replace('__SPORTS_CAVE_TOP_BAR_CONFIG__',json.dumps(config))
    html = html.replace('</body>', '<main id="fixture-content" style="padding:180px 24px;background:#faf8f2;min-height:80vh">Synthetic Ads page</main></body>')
    writes, errors = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge',headless=True)
        try:
            page = browser.new_page(viewport={'width':1600,'height':600})
            page.on('pageerror',lambda error: errors.append(str(error)))
            def respond(route):
                request = route.request
                if request.url == 'http://fixture.test/':
                    route.fulfill(body=html,content_type='text/html')
                elif request.url.split('?')[0].endswith('/status'):
                    route.fulfill(json=payload)
                elif request.url.endswith('/queue-control'):
                    data=request.post_data_json
                    writes.append(data)
                    payload['queues'][data['queue']]['enabled']=data['enabled']
                    route.fulfill(json={'enabled':data['enabled']})
                else:
                    route.fulfill(json={})
            page.route('**/*',respond)
            page.goto('http://fixture.test/')
            expect(page.locator('#sc-os-ads-title')).to_have_text('Broadway Joe')
            expect(page.locator('#sc-os-global-search')).to_be_hidden()
            cards = ['#sc-os-design-card','#sc-os-upload-card','#sc-os-ads-card']
            for width in (1600,1280,1024,820,600,390):
                page.set_viewport_size({'width':width,'height':700})
                boxes = [page.locator(selector).bounding_box() for selector in cards]
                assert all(box and box['width'] > 75 and box['x'] >= 0 and box['x']+box['width'] <= width+1 for box in boxes), (width,boxes)
                assert all(boxes[i]['x']+boxes[i]['width'] <= boxes[i+1]['x']+1 for i in range(2)), (width,boxes)
                assert page.evaluate('document.documentElement.scrollWidth') <= width
                # Search floats above the document without resizing the header or cards.
                before = page.locator('#sc-os-companion-status').bounding_box()
                page.get_by_role('button',name='Open search',exact=True).click()
                expect(page.locator('#sc-os-global-search')).to_be_visible()
                assert page.locator('#sc-os-companion-status').bounding_box() == before
                page.keyboard.press('Escape')
                expect(page.locator('#sc-os-global-search')).to_be_hidden()
                expect(page.get_by_role('button',name='Open search',exact=True)).to_be_focused()
            page.set_viewport_size({'width':1600,'height':600})
            page.keyboard.press('Control+k')
            expect(page.locator('#sc-os-global-search')).to_be_focused()
            page.locator('#fixture-content').click()
            expect(page.locator('#sc-os-global-search')).to_be_hidden()
            page.locator('#sc-os-ads-status > summary').click()
            expect(page.get_by_role('button',name='Pause ads queue (0 waiting)',exact=True)).to_be_visible()
            page.get_by_role('button',name='Pause ads queue (0 waiting)',exact=True).click()
            expect(page.get_by_role('button',name='Play ads queue (0 waiting)',exact=True)).to_be_visible()
            assert writes == [dict(queue='ads',enabled=False)]
            page.get_by_role('button',name='Close ads status',exact=True).click()
            assert not page.locator('#sc-os-ads-status').evaluate('(el)=>el.open')
            assert not errors
            output=Path(os.environ.get('SC_TEST_SCREENSHOT_DIR',tmp_path))
            output.mkdir(parents=True,exist_ok=True)
            page.screenshot(path=str(output/'companion-header-desktop.png'))
            page.set_viewport_size({'width':390,'height':700})
            page.screenshot(path=str(output/'companion-header-mobile.png'))
        finally:
            browser.close()
