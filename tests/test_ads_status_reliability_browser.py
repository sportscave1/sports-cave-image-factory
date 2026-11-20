"""Native header with synthetic endpoints: delayed reads and clicks during polling."""
import json
from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright, expect


def header():
    source=(Path(__file__).resolve().parents[1]/'components/sports_cave_top_bar/index.html').read_text(encoding='utf8')
    config=dict(appName='Sports Cave OS',uploadScope='ads-reliability-admin',staffUploadProgress=True,
                currentRouteKey='ads',revision='ads-reliability',searchIndex=[],navigationRouteLabels={},navigationRouteKeys={})
    return source.replace('__SPORTS_CAVE_TOP_BAR_CONFIG__',json.dumps(config)).replace(
        '    const state =','    parentWindow.testRefreshAds = refreshStaffProgress;\n    const state =',1)


def status(jobs=()):
    return dict(online=True,jobs=[],queues=dict(upload=dict(display=True,enabled=True),
        design=dict(jobs=[]),ads=dict(enabled=True,online=True,waiting=0,jobs=list(jobs))))


@pytest.mark.parametrize('empty_first',[False,True])
def test_picker_retries_load_preserves_early_search_and_does_not_move_submit(empty_first):
    reads=[];posts=[];held=[];errors=[]
    product=dict(id='fixture-lebron',name='LeBron – James Wall Art',sport='NBA',country='USA')
    catalog=dict(products=[product],sports=['NBA'],countries=['USA'])
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True)
        try:
            page=browser.new_page(viewport=dict(width=390,height=850),has_touch=True)
            page.on('pageerror',lambda e:errors.append(str(e)))
            def respond(route):
                if route.request.url=='https://fixture.test/':route.fulfill(body=header(),content_type='text/html')
                elif 'ad-quick-add' in route.request.url:
                    if route.request.method=='POST':posts.append(route.request.post_data_json);route.fulfill(json={'ok':True})
                    else:
                        reads.append(route.request.url)
                        if len(reads)==1:
                            route.fulfill(status=200 if empty_first else 503,json={'products':[]} if empty_first else {'error':'Catalog temporarily unavailable'})
                        elif len(reads)==2:held.append(route)
                        else:route.fulfill(json=catalog)
                else:route.fulfill(json=status())
            page.route('**/*',respond);page.goto('https://fixture.test/')
            page.locator('#sc-os-ads-status > summary').click()
            page.locator('#sc-ad-quick > summary').click()
            expect(page.locator('#sc-ad-message')).to_contain_text('No products loaded' if empty_first else 'temporarily unavailable')
            field=page.locator('#sc-ad-product');field.fill('  JAMES  lebron ')
            expect(page.locator('#sc-ad-products')).to_contain_text('Loading products')
            assert len(reads)==2 and len(held)==1
            submit=page.locator('#sc-ad-submit');before=submit.bounding_box()
            held.pop().fulfill(json=catalog)
            expect(field).to_have_value('  JAMES  lebron ')
            option=page.get_by_role('option',name=product['name'],exact=True)
            expect(option).to_be_visible()
            # The overlay must not push Add to queue out from under a press.
            assert submit.bounding_box()['y']==before['y']
            option.tap()
            expect(page.locator('#sc-ad-products')).to_be_hidden()
            expect(field).to_have_value(product['name'])
            submit.tap()
            expect(page.locator('#sc-ad-message')).to_have_text('Added to Ads queue')
            assert len(posts)==1 and posts[0]['product']==product['id']
            page.locator('#sc-ad-reload').click()
            expect(page.locator('#sc-ad-message')).to_have_text('Choose a product and check its market.')
            expect(field).to_have_value(product['name'])
            assert len(reads)==3 and reads[-1].endswith('?refresh=1')
            assert not errors
        finally:browser.close()


def test_stop_click_survives_changing_status_and_failed_delete_restores_stopped_receipt():
    job=dict(id='00000000-0000-0000-0000-000000000001',title='Fixture Ad',state='running',stage='generating',
        label='Generating',detail='Working',percent=40,can_play=False,can_cancel=True,updated_at='2026-11-20T00:00:00+00:00')
    held=[];writes=[];errors=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True)
        try:
            page=browser.new_page(viewport=dict(width=660,height=850))
            page.on('pageerror',lambda e:errors.append(str(e)))
            def respond(route):
                if route.request.url=='https://fixture.test/':route.fulfill(body=header(),content_type='text/html')
                elif route.request.method=='POST':writes.append(route.request.post_data_json);held.append(route)
                else:route.fulfill(json=status([job]))
            page.route('**/*',respond);page.goto('https://fixture.test/')
            page.locator('#sc-os-ads-status > summary').click()
            stop=page.get_by_role('button',name='Cancel job · Fixture Ad',exact=True)
            stop.evaluate('(el)=>{window.savedStop=el;}')
            box=stop.bounding_box();page.mouse.move(box['x']+10,box['y']+10);page.mouse.down()
            job.update(detail='New progress while pointer held',updated_at='2026-11-20T00:00:01+00:00')
            page.evaluate('testRefreshAds(false)')
            assert stop.evaluate('(el)=>el===window.savedStop')
            page.mouse.up()
            expect(page.locator('#sc-os-ads-list')).to_contain_text('Stopping')
            expect(stop).to_be_disabled()
            assert len(writes)==1 and writes[0]['action']=='cancel'
            page.evaluate('testRefreshAds(false)')
            expect(page.locator('#sc-os-ads-list')).to_contain_text('Stopping')
            receipt=dict(job,stage='cancelled',label='Cancelled',control_action='cancel',can_play=True,can_cancel=False)
            held.pop().fulfill(json=dict(id=job['id'],action='cancel',job=receipt))
            expect(page.locator('#sc-ad-message')).to_have_text('Job cancelled')
            page.evaluate('testRefreshAds(false)') # intentionally stale cached running job
            expect(page.locator('#sc-os-ads-list')).to_contain_text('Cancelled')
            expect(stop).to_be_disabled()
            delete=page.get_by_role('button',name='Delete from queue · Fixture Ad',exact=True)
            delete.click();expect(page.locator('#sc-os-ads-list article')).to_have_count(0)
            held.pop().fulfill(status=503,json={'error':'Delete rejected'})
            expect(page.locator('#sc-os-ads-list article')).to_have_count(1)
            expect(page.locator('#sc-os-ads-list')).to_contain_text('Cancelled')
            page.get_by_role('button',name='Delete from queue · Fixture Ad',exact=True).click()
            held.pop().fulfill(json=dict(id=job['id'],action='delete',job=None))
            expect(page.locator('#sc-ad-message')).to_have_text('Removed from queue')
            page.evaluate('testRefreshAds(false)')
            expect(page.locator('#sc-os-ads-list article')).to_have_count(0)
            assert not errors
        finally:browser.close()


def test_timed_out_add_reenables_button_and_retries_same_request():
    writes=[];held=[]
    product=dict(id='fixture',name='Fixture Product',sport='NBA',country='USA')
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True)
        try:
            page=browser.new_page()
            page.clock.install()
            def respond(route):
                if route.request.url=='https://fixture.test/':route.fulfill(body=header(),content_type='text/html')
                elif 'ad-quick-add' in route.request.url:
                    if route.request.method=='POST':
                        writes.append(route.request.post_data_json)
                        if len(writes)==1:held.append(route)
                        else:route.fulfill(json={'ok':True})
                    else:route.fulfill(json=dict(products=[product],sports=['NBA'],countries=['USA']))
                else:route.fulfill(json=status())
            page.route('**/*',respond);page.goto('https://fixture.test/')
            page.locator('#sc-os-ads-status > summary').click();page.locator('#sc-ad-quick > summary').click()
            field=page.locator('#sc-ad-product');field.fill(product['name'])
            page.get_by_role('option',name=product['name'],exact=True).click()
            page.locator('#sc-ad-submit').click()
            expect(page.locator('#sc-ad-submit')).to_be_disabled()
            page.clock.fast_forward(16000)
            expect(page.locator('#sc-ad-message')).to_contain_text('timed out')
            expect(page.locator('#sc-ad-submit')).to_be_enabled()
            page.locator('#sc-ad-submit').click()
            expect(page.locator('#sc-ad-message')).to_have_text('Added to Ads queue')
            assert len(writes)==2 and writes[0]['request_id']==writes[1]['request_id']
        finally:browser.close()
