"""Synthetic browser contracts for the header's existing companion control channel."""
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def test_usage_preserves_defaults_limits_posts_and_recovers_from_failure():
    source=(Path(__file__).parents[1]/'components/sports_cave_top_bar/index.html').read_text(encoding='utf-8')
    config=dict(appName='Sports Cave OS',filesEnabled=True,uploadScope='usage-fixture',staffUploadProgress=True,currentRouteKey='dashboard',revision='usage-fixture',searchIndex=[],navigationRouteLabels={},navigationRouteKeys={})
    html=source.replace('__SPORTS_CAVE_TOP_BAR_CONFIG__',json.dumps(config)).replace('</head>','<style>label {color:black!important} input {color:black;background:black}</style></head>')
    current=dict(mode='Maximum speed',manual_mbps=None,sustainable_mbps=None,headroom_percent=25,background_percent=25,download_mbps=None,paused=False)
    data=dict(control=dict(paused=False),transfer_control=dict(instance='a'*24,age_seconds=2,effective=dict(capability=3,revision='local',settings=current,protection='Maximum speed (uncapped)'),requested=None))
    payload=dict(online=True,jobs=[],queues=dict(upload=dict(enabled=True,waiting=0,display=True),design=dict(enabled=True,waiting=0,jobs=[]),ads=dict(enabled=True,online=True,waiting=0,jobs=[]),editions=dict(enabled=True,online=True,waiting=1,jobs=[])))
    posts=[];reads=[];errors=[];fail=[False];held=[];hold=[True]
    with sync_playwright() as p:
        browser=p.chromium.launch(channel=os.environ.get('STATUS_TEST_BROWSER_CHANNEL','msedge') or None,headless=True)
        try:
            page=browser.new_page(viewport={'width':1600,'height':900})
            page.on('pageerror',lambda e:errors.append(str(e)))
            def respond(route):
                url=route.request.url.split('?')[0]
                if url=='http://fixture.test/':route.fulfill(body=html,content_type='text/html')
                elif url.endswith('/companion-controls'):
                    reads.append(url);route.fulfill(json=data)
                elif url.endswith('/worker-health/control'):
                    body=route.request.post_data_json;posts.append(body)
                    if fail[0]:route.fulfill(status=503,json=dict(error='Temporary fixture error'))
                    elif 'paused' in body:
                        data['control']['paused']=body['paused'];route.fulfill(json=dict(state='Pausing' if body['paused'] else 'Resumed'))
                    else:
                        data['transfer_control']['requested']=dict(revision='request_1',settings=body['transfer_settings'])
                        if hold[0]:held.append(route)
                        else:route.fulfill(json=dict(requested=data['transfer_control']['requested']))
                elif url.endswith('/status'):route.fulfill(json=payload)
                else:route.fulfill(json={})
            page.route('**/*',respond);page.goto('http://fixture.test/')
            page.locator('#sc-os-editions-status > summary').click()
            mode=page.locator('#sc-edition-mode');message=page.locator('#sc-edition-message')
            expect(mode).to_have_value('Maximum speed')
            assert not posts and len(reads)==1
            expect(page.locator('#sc-edition-upload')).to_have_attribute('placeholder','Not used')
            expect(page.locator('#sc-edition-download')).to_have_attribute('placeholder','Uncapped')
            assert page.locator('#sc-edition-usage label').first.evaluate('(el)=>getComputedStyle(el).color')=='rgb(248, 237, 207)'
            assert page.locator('#sc-edition-download').evaluate('(el)=>getComputedStyle(el).backgroundColor')=='rgb(255, 250, 240)'
            expect(page.locator('#sc-os-editions-freshness')).to_contain_text('Last successful status:')
            page.locator('#sc-edition-usage').screenshot(path=os.path.join(os.environ['TEMP'],'edition-usage-readable.png'))
            mode.select_option('Manual');page.locator('#sc-edition-upload').fill('3.5');page.locator('#sc-edition-download').fill('6')
            page.locator('#sc-edition-refresh').click()
            expect(message).to_contain_text('Current:')
            expect(mode).to_have_value('Manual');expect(page.locator('#sc-edition-upload')).to_have_value('3.5')
            page.locator('#sc-edition-apply').click()
            expect(page.locator('#sc-edition-apply')).to_be_disabled()
            page.locator('#sc-edition-apply').evaluate('(el)=>{el.click();el.click();}')
            assert len(posts)==1
            hold[0]=False;held.pop().fulfill(json=dict(requested=data['transfer_control']['requested']))
            expect(message).to_contain_text('awaiting companion acknowledgement')
            assert len(posts)==1 and posts[0]['transfer_settings']==dict(current,mode='Manual',manual_mbps=3.5,download_mbps=6)
            fail[0]=True
            page.locator('#sc-edition-pause').click();expect(message).to_contain_text('Temporary fixture error')
            expect(page.locator('#sc-edition-pause')).to_be_enabled()
            fail[0]=False
            page.locator('#sc-edition-pause').click();expect(message).to_contain_text('current work will finish safely')
            expect(page.locator('#sc-edition-pause')).to_have_text('Resume companion')
            page.locator('#sc-edition-pause').click();expect(message).to_have_text('Companion resumed.')
            assert posts[-1]==dict(paused=False)
            mode.select_option('Balanced');page.locator('#sc-edition-apply').click()
            expect(message).to_contain_text('reliable measured upload rate')
            assert len(posts)==4
            page.locator('#sc-edition-usage').screenshot(path=os.path.join(os.environ['TEMP'],'edition-usage-controls.png'))
            assert errors==[]
        finally:browser.close()
