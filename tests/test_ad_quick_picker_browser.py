import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def test_searchable_scrollable_picker_submits_exact_identity():
    source=(Path(__file__).resolve().parents[1]/'components/sports_cave_top_bar/index.html').read_text(encoding='utf-8')
    config=dict(appName='Sports Cave OS',uploadScope='fixture-admin',staffUploadProgress=True,currentRouteKey='ads',revision='picker',searchIndex=[],navigationRouteLabels={},navigationRouteKeys={})
    html=source.replace('__SPORTS_CAVE_TOP_BAR_CONFIG__',json.dumps(config))
    products=[dict(id=str(i),name=f'Edition {i:03}',sport='NBA',country='USA') for i in range(400)]
    products.extend([dict(id='a',name='Same title',sport='NBA',country='USA'),dict(id='b',name='Same title',sport='AFL',country='Australia')])
    posts=[]; reads=[];errors=[]; fail_next=[False]
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True)
        try:
            page=browser.new_page(viewport=dict(width=1280,height=900))
            page.on('pageerror',lambda e:errors.append(str(e)))
            def route(r):
                if r.request.url=='https://fixture.test/':r.fulfill(body=html,content_type='text/html')
                elif 'ad-quick-add' in r.request.url:
                    if r.request.method=='POST':
                        posts.append(r.request.post_data_json)
                        if fail_next[0]:
                            fail_next[0]=False;r.fulfill(status=503,json={'error':'Please retry'})
                        else:r.fulfill(json={'ok':True})
                    else:reads.append(1);r.fulfill(json=dict(products=products,sports=['NBA','AFL'],countries=['USA','Australia']))
                else:r.fulfill(json=dict(online=True,jobs=[],queues=dict(upload=dict(display=True),design=dict(jobs=[]),ads=dict(enabled=True,online=True,waiting=0,jobs=[]))))
            page.route('**/*',route);page.goto('https://fixture.test/')
            page.locator('#sc-os-ads-status > summary').click()
            page.locator('#sc-ad-quick > summary').click()
            field=page.locator('#sc-ad-product');field.click()
            expect(page.locator('#sc-ad-products').get_by_role('option')).to_have_count(80)
            assert page.locator('#sc-ad-products').evaluate('(e)=>e.scrollHeight>e.clientHeight && e.clientHeight<=220')
            field.fill('Edition 39');expect(page.locator('#sc-ad-products').get_by_role('option')).to_have_count(14)
            field.press('ArrowDown');field.press('ArrowDown');field.press('Enter')
            expect(field).to_have_value('Edition 391')
            expect(page.locator('#sc-ad-country')).to_have_value('USA')
            page.locator('#sc-ad-submit').click()
            expect(page.locator('#sc-ad-message')).to_have_text('Added to Ads queue')
            assert posts[0]['product']=='391'
            page.locator('#sc-ad-submit').click()
            expect(page.locator('#sc-ad-submit')).to_be_enabled()
            assert posts[1]['request_id']!=posts[0]['request_id']
            fail_next[0]=True
            page.locator('#sc-ad-submit').click()
            expect(page.locator('#sc-ad-message')).to_have_text('Please retry')
            page.locator('#sc-ad-submit').click()
            expect(page.locator('#sc-ad-message')).to_have_text('Added to Ads queue')
            assert posts[2]['request_id']==posts[3]['request_id']
            field.fill('Edition 392')
            page.locator('#sc-ad-submit').click()
            expect(page.locator('#sc-ad-message')).to_have_text('Added to Ads queue')
            assert posts[-1]['product']=='392'
            field.fill('Same title');page.get_by_role('option',name='Same title',exact=True).nth(1).click()
            expect(page.locator('#sc-ad-sport')).to_have_value('AFL')
            field.click();field.press('Escape');expect(page.locator('#sc-ad-products')).to_be_hidden()
            page.set_viewport_size(dict(width=390,height=800));field.click()
            expect(page.locator('#sc-ad-products').get_by_role('option')).to_have_count(80)
            assert len(reads)==1 and not errors
        finally:browser.close()
