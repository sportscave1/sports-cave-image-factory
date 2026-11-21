"""Real header controller and CSS, synthetic HTTP only; no app/server imports."""
import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright, expect


def test_two_designs_rotate_in_one_card_without_changing_other_panels():
    source = (Path(__file__).resolve().parents[1] / 'components/sports_cave_top_bar/index.html').read_text(encoding='utf8')
    config = dict(appName='Sports Cave OS', filesEnabled=True, uploadScope='dual-fixture',
                  staffUploadProgress=True, currentRouteKey='dashboard', revision='dual-fixture',
                  searchIndex=[], navigationRouteLabels={}, navigationRouteKeys={})
    designs = [dict(id='first',title='First design',state='running',label='Generating',percent=35,estimated=True),
               dict(id='second',title='Second design',state='running',label='Checking output',percent=80,estimated=True)]
    payload = dict(online=True,jobs=[dict(id='upload',title='Current upload',stage=2,label='Uploading',percent=40)],
                   queues=dict(upload=dict(enabled=True,waiting=0,display=True),
                       design=dict(enabled=True,waiting=3,jobs=designs),
                       ads=dict(enabled=True,online=True,waiting=0,jobs=[dict(id='ad',title='Current ad',state='running',label='Posting',percent=80)])))
    html = source.replace('__SPORTS_CAVE_TOP_BAR_CONFIG__',json.dumps(config))
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge',headless=True)
        try:
            page = browser.new_page(viewport={'width':1600,'height':600})
            page.clock.install()
            page.on('pageerror',lambda error: errors.append(str(error)))
            def respond(route):
                if route.request.url == 'http://fixture.test/':
                    route.fulfill(body=html,content_type='text/html')
                elif route.request.url.split('?')[0].endswith('/status'):
                    route.fulfill(json=payload)
                else:
                    route.fulfill(json={})
            page.route('**/*',respond)
            page.goto('http://fixture.test/')
            title = page.locator('#sc-os-design-title')
            stage = page.locator('#sc-os-design-stage')
            expect(title).to_have_text('First design')
            expect(stage).to_contain_text('2 working · 1/2')
            page.locator('#sc-os-design-status > summary').click()
            expect(page.locator('#sc-os-design-list strong')).to_have_text(['First design','Second design'])
            page.clock.run_for(5100)
            expect(title).to_have_text('Second design')
            expect(stage).to_contain_text('2 working · 2/2')
            expect(page.locator('#sc-os-design-meter')).to_have_attribute('aria-valuetext','Estimated 80% · 2 working · 2/2 · Checking output · 3 waiting')
            expect(page.locator('#sc-os-ads-title')).to_have_text('Current ad')
            expect(page.locator('#sc-os-staff-upload-title')).to_have_text('Current upload')
            # Rotation changes only the summary: it never rebuilds the open popup.
            assert page.locator('#sc-os-design-status').evaluate('(el)=>el.open')
            page.emulate_media(reduced_motion='reduce')
            page.clock.run_for(5000)
            expect(title).to_have_text('First design')
            payload['queues']['design']['jobs'] = [designs[1]]
            page.evaluate("document.dispatchEvent(new CustomEvent('sc-design-edit-queued'))")
            expect(title).to_have_text('Second design')
            expect(stage).not_to_contain_text('2 working')
            page.clock.run_for(5000)
            expect(title).to_have_text('Second design')
            assert not errors
            # A cold reload must initialize the entire controller, not only
            # queue functions evaluated with a pre-created fixture state.
            page.reload()
            expect(page.locator('#sc-os-companion-status')).to_be_visible()
            expect(page.locator('#sc-os-design-title')).to_have_text('Second design')
            expect(page.locator('#sc-os-ads-title')).to_have_text('Current ad')
            expect(page.locator('#sc-os-staff-upload-title')).to_have_text('Current upload')
            assert not errors
        finally:
            browser.close()


def test_four_cards_search_overlay_and_responsive_layout(tmp_path):
    source = (Path(__file__).resolve().parents[1] / 'components/sports_cave_top_bar/index.html').read_text(encoding='utf8')
    payload = dict(online=True, jobs=[dict(id='upload',title='Collector Tribute',stage=2,
        label='Generating mockups',percent=34,detail='',updated_at='fixture')], queues=dict(
        upload=dict(enabled=True,waiting=2,display=True),
        design=dict(enabled=True,waiting=1,jobs=[dict(id='design',title='A Moment in History',
            state='running',label='Generating · time-based estimate',percent=45,estimated=True)]),
        ads=dict(enabled=True,online=True,waiting=0,jobs=[dict(id='ad',title='Broadway Joe',
            state='running',label='Waiting for ad copy and three covers',percent=40)])))
    payload['queues']['editions'] = dict(enabled=True,online=True,waiting=2,jobs=[dict(
        id='edition',title='Edition artwork',state='running',label='Photoshop',percent=0)])
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
            cards = ['#sc-os-design-card','#sc-os-upload-card','#sc-os-ads-card','#sc-os-editions-card']
            for width in (1600,1280,1024,820,600,390):
                page.set_viewport_size({'width':width,'height':700})
                boxes = [page.locator(selector).bounding_box() for selector in cards]
                assert all(box and box['width'] > 75 and box['x'] >= 0 and box['x']+box['width'] <= width+1 for box in boxes), (width,boxes)
                assert all(a['x']+a['width'] <= b['x']+1 or b['x']+b['width'] <= a['x']+1 or a['y']+a['height'] <= b['y']+1 or b['y']+b['height'] <= a['y']+1 for i,a in enumerate(boxes) for b in boxes[i+1:]), (width,boxes)
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
            files = page.locator('#sc-os-files').bounding_box()
            actions = page.locator('.sc-os-topbar-actions').bounding_box()
            design = page.locator('#sc-os-design-card').bounding_box()
            assert files['x']+files['width'] <= actions['x']+1
            assert actions['x']+actions['width'] <= design['x']+1
            for ident,label in [('mobile-search','Search'),('daily-planner','Schedule'),('notifications','Notifications')]:
                button = page.locator('#sc-os-'+ident)
                button.evaluate("el=>el.title='Sports Cave browser v2: %7Bfixture%7D'")
                button.hover()
                assert button.evaluate("el=>{const b=el.getBoundingClientRect();return document.elementFromPoint(b.x+b.width/2,b.y+b.height/2).closest('[title]').title}") == label
            assert page.locator('#sc-os-repairs,#sc-os-profile,#sc-os-settings').count() == 0
            expect(page.locator('#sc-os-editions-meter')).not_to_have_attribute('value')
            page.locator('#sc-os-editions-status > summary').click()
            expect(page.get_by_role('link',name='Open Edition Ops',exact=True)).to_have_attribute('href','/?page=edition_ops')
            page.get_by_role('button',name='Close Auto Editions status',exact=True).click()
            payload['queues']['editions']['online'] = False
            page.evaluate("document.dispatchEvent(new CustomEvent('sc-design-edit-queued'))")
            expect(page.locator('#sc-os-editions-stage')).to_contain_text('companion offline')
            payload['queues']['editions'].update(jobs=[],unavailable=True,waiting=0)
            page.evaluate("document.dispatchEvent(new CustomEvent('sc-design-edit-queued'))")
            expect(page.locator('#sc-os-editions-stage')).to_have_text('Status unavailable · retrying')
            expect(page.locator('#sc-os-editions-status')).to_have_attribute('data-stale','true')
            payload['queues']['editions'].update(online=True,unavailable=False,jobs=[dict(id='edition',title='Edition artwork',state='complete',label='Preparation saved',percent=100)])
            page.evaluate("document.dispatchEvent(new CustomEvent('sc-design-edit-queued'))")
            expect(page.locator('#sc-os-editions-meter')).to_have_attribute('value','100')
            expect(page.locator('#sc-os-editions-status')).to_have_attribute('data-stale','false')
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


def test_publish_receipt_immediately_opens_exact_status_and_refreshes_without_requeueing():
    source = (Path(__file__).resolve().parents[1] / 'components/sports_cave_top_bar/index.html').read_text(encoding='utf8')
    config = dict(appName='Sports Cave OS', filesEnabled=True, uploadScope='publish-fixture',
                  staffUploadProgress=True, currentRouteKey='design_studio', revision='publish-fixture',
                  searchIndex=[], navigationRouteLabels={}, navigationRouteKeys={})
    old = dict(id='old', title='Previous upload', stage=6, label='Published and PSD mapped', percent=100, updated_at='old')
    new = dict(id='new', title='Requested artwork', stage=0, label='Waiting for desktop companion', percent=0, updated_at='new')
    requests, writes = [], []
    payload = dict(online=True, jobs=[old], queues=dict(upload=dict(enabled=True,display=True,waiting=0)))
    html = source.replace('__SPORTS_CAVE_TOP_BAR_CONFIG__',json.dumps(config))
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge',headless=True)
        try:
            page = browser.new_page(viewport={'width':1600,'height':700})
            errors = []
            page.on('pageerror',lambda error: errors.append(str(error)))
            def respond(route):
                if route.request.method != 'GET':
                    writes.append(route.request.url)
                if route.request.url == 'http://fixture.test/':
                    route.fulfill(body=html,content_type='text/html')
                elif route.request.url.split('?')[0].endswith('/status'):
                    requests.append(route.request.url)
                    route.fulfill(json=payload)
                else:
                    route.fulfill(json={})
            page.route('**/*',respond)
            page.goto('http://fixture.test/')
            expect(page.locator('#sc-os-staff-upload-title')).to_have_text('Previous upload')
            before = len(requests)
            payload['jobs'] = [old,new]  # Do not rely on API ordering to focus the request.
            # Exact receipt reads can precede the background queue-count snapshot.
            payload['queues']['upload'].pop('waiting')
            notice = dict(id='new',job_id='new',interaction_id='click-1',title='Requested artwork',open_upload=True,kind='success',text='Request saved')
            page.evaluate('(cfg)=>window.SportsCaveTopBar.install(cfg)',dict(config,uploadNotice=notice))
            expect(page.locator('#sc-os-staff-upload-title')).to_have_text('Requested artwork')
            expect(page.locator('#sc-os-staff-upload-stage')).to_contain_text('Waiting for desktop companion')
            expect(page.get_by_role('button',name='Pause upload queue',exact=True)).to_be_visible()
            expect(page.locator('#sc-os-companion-status')).not_to_contain_text('NaN')
            assert page.locator('#sc-os-staff-uploads').evaluate('(el)=>el.open')
            assert len(requests) > before and any('job_id=new' in url for url in requests)
            # Repeat a deliberate click: reopen status, never submit another upload.
            page.locator('#sc-os-staff-upload-summary').click()
            assert not page.locator('#sc-os-staff-uploads').evaluate('(el)=>el.open')
            notice['interaction_id'] = 'click-2'
            page.evaluate('(cfg)=>window.SportsCaveTopBar.install(cfg)',dict(config,uploadNotice=notice))
            expect(page.locator('#sc-os-staff-upload-title')).to_have_text('Requested artwork')
            assert page.locator('#sc-os-staff-uploads').evaluate('(el)=>el.open')
            # A cancelled pinned receipt must yield the summary to the next active job.
            new.update(stage=7,label='Cancelled',cancelled=True)
            old.update(stage=2,label='Generating mockups',percent=34)
            page.evaluate("document.dispatchEvent(new CustomEvent('sc-design-edit-queued'))")
            expect(page.locator('#sc-os-staff-upload-title')).to_have_text('Previous upload')
            assert not writes and not errors
        finally:
            browser.close()


def test_design_defer_and_cancel_controls_follow_the_next_job_without_enqueuing():
    source=(Path(__file__).resolve().parents[1]/'components/sports_cave_top_bar/index.html').read_text(encoding='utf8')
    config=dict(appName='Sports Cave OS',filesEnabled=True,uploadScope='design-controls',staffUploadProgress=True,
                currentRouteKey='dashboard',revision='design-controls',searchIndex=[],navigationRouteLabels={},navigationRouteKeys={})
    first=dict(id='first',title='Stalled design',state='running',label='Waiting for output',percent=10,updated_at='checkpoint',can_defer=True,can_cancel=True)
    second=dict(id='second',title='Next design',state='waiting',label='Pending',percent=0,can_cancel=True)
    payload=dict(online=True,jobs=[],queues=dict(upload=dict(enabled=True,waiting=0,display=True),design=dict(enabled=True,waiting=1,jobs=[first,second])))
    writes=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True)
        try:
            page=browser.new_page(viewport={'width':1200,'height':750})
            def respond(route):
                if route.request.url=='http://fixture.test/':
                    route.fulfill(body=source.replace('__SPORTS_CAVE_TOP_BAR_CONFIG__',json.dumps(config)),content_type='text/html')
                elif route.request.url.endswith('/api/morning-designs/control'):
                    body=route.request.post_data_json;writes.append(body)
                    first.update(state='pending',label='Pending · queue continues',can_defer=False)
                    second.update(state='running',label='Opening ChatGPT',can_defer=True,updated_at='next')
                    payload['queues']['design']['waiting']=0
                    route.fulfill(json=dict(job=dict(id=body['id'],stage=5)))
                else:route.fulfill(json=payload)
            page.route('**/*',respond);page.goto('http://fixture.test/')
            page.locator('#sc-os-design-status > summary').click()
            page.get_by_role('button',name='Move to pending · Stalled design',exact=True).click()
            expect(page.locator('#sc-os-design-title')).to_have_text('Next design')
            assert writes==[dict(id='first',updated_at='checkpoint',action='defer')]
            expect(page.get_by_role('button',name='Cancel design · Stalled design',exact=True)).to_be_visible()
            expect(page.get_by_role('button',name='Cancel design · Stalled design',exact=True)).to_be_enabled()
            expect(page.get_by_role('button',name='Move to pending · Stalled design',exact=True)).to_have_count(0)
        finally:browser.close()
