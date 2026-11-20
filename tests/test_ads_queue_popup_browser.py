"""Native header in Edge with synthetic endpoints only."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect


def test_compact_controls_and_quick_add(tmp_path):
    source=(Path(__file__).resolve().parents[1]/'components/sports_cave_top_bar/index.html').read_text(encoding='utf8')
    job=dict(id='00000000-0000-0000-0000-000000000001',title='Joe Namath Wall Art',state='failed',stage='failed',
        label='Needs attention',detail='Original prompt not loaded',percent=0,can_play=True,can_cancel=True)
    payload=dict(online=True,jobs=[],queues=dict(upload=dict(enabled=True,waiting=0,display=True),
        design=dict(jobs=[]),ads=dict(enabled=True,online=True,waiting=0,jobs=[job])))
    config=dict(appName='Sports Cave OS',uploadScope='fixture-admin',staffUploadProgress=True,currentRouteKey='ads',
        revision='fixture',searchIndex=[],navigationRouteLabels={'ads':'Ads'},navigationRouteKeys={'Ads':'ads'},authToken='fixture')
    html=source.replace('__SPORTS_CAVE_TOP_BAR_CONFIG__',json.dumps(config))
    html=html.replace('</head>','<style>p {font-size:24px;color:black;} strong {font-size:28px;}</style></head>')
    writes=[];errors=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True)
        page=browser.new_page(viewport={'width':1280,'height':850})
        page.on('pageerror',lambda error:errors.append(str(error)))
        def respond(route):
            req=route.request
            if req.url=='https://fixture.test/':route.fulfill(body=html,content_type='text/html')
            elif req.url.split('?')[0].endswith('/status'):route.fulfill(json=payload)
            elif req.url.endswith('/ad-quick-add') and req.method=='GET':
                route.fulfill(json=dict(products=[dict(id='id:123',name='Joe Namath Wall Art',sport='NFL',country='USA')],sports=['NFL','AFL'],countries=['Australia','USA','Canada'],types=['Instant Experience']))
            elif req.method=='POST':
                writes.append(req.post_data_json)
                if req.post_data_json.get('action')=='delete':payload['queues']['ads']['jobs']=[]
                route.fulfill(json={'id':job['id']})
            else:route.fulfill(json={})
        page.route('**/*',respond);page.goto('https://fixture.test/')
        page.locator('#sc-os-ads-status > summary').click()
        row=page.locator('#sc-os-ads-list article')
        expect(row).to_be_visible()
        assert row.locator('p').evaluate('e=>getComputedStyle(e).fontSize')=='11px'
        assert row.locator('p').evaluate('e=>getComputedStyle(e).color')!='rgb(0, 0, 0)'
        assert row.bounding_box()['height']<100
        page.get_by_role('button',name='Play / resume job · Joe Namath Wall Art',exact=True).click()
        expect(page.locator('#sc-ad-message')).to_have_text('Resuming saved job')
        assert writes[-1]['action']=='play'
        page.get_by_role('button',name='Cancel job · Joe Namath Wall Art',exact=True).click()
        expect(page.locator('#sc-ad-message')).to_have_text('Job cancelled')
        assert writes[-1]['action']=='cancel'
        page.locator('#sc-ad-quick > summary').click()
        expect(page.locator('#sc-ad-message')).to_have_text('Choose a product and check its market.')
        page.locator('#sc-ad-product').fill('Joe Namath Wall Art')
        page.get_by_role('option',name='Joe Namath Wall Art',exact=True).click()
        expect(page.locator('#sc-ad-sport')).to_have_value('NFL')
        expect(page.locator('#sc-ad-country')).to_have_value('USA')
        page.locator('#sc-ad-country').select_option('Canada')
        page.locator('#sc-ad-submit').click()
        expect(page.locator('#sc-ad-message')).to_have_text('Added to Ads queue')
        assert writes[-1]['product']=='id:123' and writes[-1]['country']=='Canada' and writes[-1]['type']=='Instant Experience'
        token=writes[-1]['request_id'];page.locator('#sc-ad-submit').click()
        expect(page.locator('#sc-ad-submit')).to_be_enabled()
        assert writes[-1]['request_id']!=token
        page.screenshot(path=str(tmp_path/'ads-queue-compact.png'))
        page.get_by_role('button',name='Delete from queue · Joe Namath Wall Art',exact=True).click()
        expect(page.locator('#sc-os-ads-list article')).to_have_count(0)
        assert writes[-1]['action']=='delete'
        assert not errors
        browser.close()
